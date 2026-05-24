"""ConnectionsP3Store — G 方向 P3（双向同意 match + 引荐 + 消息）数据访问层。

Session #22 G-P3。延续 SESSION-19 的 ConnectionsStore 模式（同一 history.db、
自动建表、加列自愈、薄 sqlite 封装），但分到独立文件——P1/P2 是「指纹 +
匿名计数」（隐私零暴露），P3 才进入「身份交换 + 消息」，业务边界完全不同。

四张表：
    match_requests        —— 双向同意 match（A → B 发兴趣，B 接受才解锁）
    referrals             —— 引荐（X 撮合 A 和 B；A、B 各自需 accept）
    connections_messages  —— matched 用户之间的异步信箱（≤500 字）
    connections_prefs     —— 每用户的 block / mute_referrals / messages_open

设计依据：docs/sessions/SESSION-18-G-connect-people-design.md §3.3。
所有写入路径都假定调用方（API 层）已校验登录态 + 业务约束；本层只关数据
完整性（外键级 owner 校验、enum 合法化、time 戳）。
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("structural.connections.p3")

# 合法状态枚举
MATCH_REQUEST_STATUS = ("pending", "accepted", "declined")
REFERRAL_PARTY_STATUS = ("pending", "accepted", "declined")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    return "mr_" + uuid.uuid4().hex[:16]


def new_referral_id() -> str:
    return "rf_" + uuid.uuid4().hex[:16]


def new_message_id() -> str:
    return "msg_" + uuid.uuid4().hex[:16]


_SCHEMA = """
CREATE TABLE IF NOT EXISTS match_requests (
    id                  TEXT PRIMARY KEY,
    from_user_email     TEXT NOT NULL,
    to_user_email       TEXT NOT NULL,
    to_fingerprint_id   TEXT NOT NULL,
    note                TEXT,
    status              TEXT NOT NULL DEFAULT 'pending',
    created_at          TEXT NOT NULL,
    responded_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_mr_to_pending
    ON match_requests(to_user_email, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mr_from
    ON match_requests(from_user_email, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_mr_active_pair
    ON match_requests(from_user_email, to_user_email, to_fingerprint_id)
    WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS referrals (
    id              TEXT PRIMARY KEY,
    referrer_email  TEXT NOT NULL,
    referee_a_email TEXT NOT NULL,
    referee_b_email TEXT NOT NULL,
    reason          TEXT,
    status_a        TEXT NOT NULL DEFAULT 'pending',
    status_b        TEXT NOT NULL DEFAULT 'pending',
    created_at      TEXT NOT NULL,
    completed_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_rf_a
    ON referrals(referee_a_email, status_a, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_b
    ON referrals(referee_b_email, status_b, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_referrer
    ON referrals(referrer_email, created_at DESC);

CREATE TABLE IF NOT EXISTS connections_messages (
    id          TEXT PRIMARY KEY,
    from_email  TEXT NOT NULL,
    to_email    TEXT NOT NULL,
    body        TEXT NOT NULL,
    sent_at     TEXT NOT NULL,
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_cm_inbox
    ON connections_messages(to_email, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_cm_outbox
    ON connections_messages(from_email, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_cm_rate
    ON connections_messages(from_email, sent_at);

CREATE TABLE IF NOT EXISTS connections_prefs (
    user_email          TEXT NOT NULL,
    blocked_email       TEXT,
    mute_referrals      INTEGER NOT NULL DEFAULT 0,
    messages_open       INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY (user_email, blocked_email)
);
CREATE INDEX IF NOT EXISTS idx_cp_user
    ON connections_prefs(user_email);
"""

_MR_COLUMNS = (
    ("from_user_email", "TEXT"),
    ("to_user_email", "TEXT"),
    ("to_fingerprint_id", "TEXT"),
    ("note", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("created_at", "TEXT"),
    ("responded_at", "TEXT"),
)

_RF_COLUMNS = (
    ("referrer_email", "TEXT"),
    ("referee_a_email", "TEXT"),
    ("referee_b_email", "TEXT"),
    ("reason", "TEXT"),
    ("status_a", "TEXT NOT NULL DEFAULT 'pending'"),
    ("status_b", "TEXT NOT NULL DEFAULT 'pending'"),
    ("created_at", "TEXT"),
    ("completed_at", "TEXT"),
)

_CM_COLUMNS = (
    ("from_email", "TEXT"),
    ("to_email", "TEXT"),
    ("body", "TEXT"),
    ("sent_at", "TEXT"),
    ("read_at", "TEXT"),
)

_CP_COLUMNS = (
    ("user_email", "TEXT"),
    ("blocked_email", "TEXT"),
    ("mute_referrals", "INTEGER NOT NULL DEFAULT 0"),
    ("messages_open", "INTEGER NOT NULL DEFAULT 1"),
    ("updated_at", "TEXT"),
)


class ConnectionsP3Store:
    """match_requests + referrals + messages + prefs 的薄 SQLite 封装。

    与 ConnectionsStore 共用 history.db；自动建表 + 加列自愈。
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # --- 连接 / schema --------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error as e:  # pragma: no cover
            logger.warning("connections_p3 pragma failed: %s", e)
        return conn

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                self._migrate_columns(conn)
                conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            logger.error("connections_p3 schema init failed: %s", e)
            raise

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        """旧表缺列时增量补齐，沿用 ConnectionsStore 模式。"""
        for table, cols in (
            ("match_requests", _MR_COLUMNS),
            ("referrals", _RF_COLUMNS),
            ("connections_messages", _CM_COLUMNS),
            ("connections_prefs", _CP_COLUMNS),
        ):
            existing = {
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }
            if not existing:
                continue
            for col, col_def in cols:
                if col not in existing:
                    logger.warning(
                        "connections_p3: %s missing %r — adding", table, col
                    )
                    conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"
                    )

    # ============================================================
    # MATCH REQUESTS
    # ============================================================

    def create_match_request(
        self,
        *,
        from_user_email: str,
        to_user_email: str,
        to_fingerprint_id: str,
        note: Optional[str] = None,
    ) -> Optional[str]:
        """新建一条 pending match request。

        返回 mr_id，或 None 表示「已存在同样的 pending」（去重，避免 spam）。
        强制 from != to（不能跟自己 match）。
        """
        if from_user_email.lower() == to_user_email.lower():
            return None
        rid = new_request_id()
        ts = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO match_requests (
                        id, from_user_email, to_user_email,
                        to_fingerprint_id, note, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        rid, from_user_email, to_user_email,
                        to_fingerprint_id, note, ts,
                    ),
                )
        except sqlite3.IntegrityError:
            # 唯一索引命中 → 已有同样 pending → 不重复创建
            logger.info(
                "match_request dedup hit from=%s to=%s fp=%s",
                from_user_email, to_user_email, to_fingerprint_id,
            )
            return None
        logger.info(
            "match_request_created id=%s from=%s to=%s fp=%s",
            rid, from_user_email, to_user_email, to_fingerprint_id,
        )
        return rid

    def get_match_request(self, rid: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM match_requests WHERE id = ?", (rid,)
            ).fetchone()
            return dict(row) if row else None

    def list_pending_for_user(self, email: str) -> list[dict]:
        """当前用户作为接收方的待处理 requests。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM match_requests
                WHERE to_user_email = ? AND status = 'pending'
                ORDER BY created_at DESC
                """,
                (email,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_sent_for_user(self, email: str) -> list[dict]:
        """当前用户作为发起方的 requests（所有状态）。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM match_requests
                WHERE from_user_email = ?
                ORDER BY created_at DESC
                """,
                (email,),
            ).fetchall()
            return [dict(r) for r in rows]

    def respond_match_request(
        self, rid: str, responder_email: str, accept: bool
    ) -> bool:
        """B 接受或拒绝 A 的 request。只有 to_user_email 能动作。

        只动 pending 状态——拒绝重复响应 / 别人代答。
        """
        new_status = "accepted" if accept else "declined"
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE match_requests
                SET status = ?, responded_at = ?
                WHERE id = ? AND to_user_email = ? AND status = 'pending'
                """,
                (new_status, _now(), rid, responder_email),
            )
            return cur.rowcount > 0

    def list_accepted_matches(self, email: str) -> list[dict]:
        """当前用户已 match 的对方（双向：自己发的 + 别人发的，accepted 的全部）。

        返回 [{ id, other_email, to_fingerprint_id, note, created_at, responded_at }, ...]
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, from_user_email, to_user_email,
                       to_fingerprint_id, note, created_at, responded_at,
                       CASE WHEN from_user_email = ? THEN to_user_email
                            ELSE from_user_email END AS other_email,
                       CASE WHEN from_user_email = ? THEN 'sent'
                            ELSE 'received' END AS direction
                FROM match_requests
                WHERE status = 'accepted'
                  AND (from_user_email = ? OR to_user_email = ?)
                ORDER BY responded_at DESC
                """,
                (email, email, email, email),
            ).fetchall()
            return [dict(r) for r in rows]

    def are_matched(self, email_a: str, email_b: str) -> bool:
        """A 和 B 之间是否存在 accepted match（任一方向）。"""
        if email_a.lower() == email_b.lower():
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM match_requests
                WHERE status = 'accepted'
                  AND ((from_user_email = ? AND to_user_email = ?)
                    OR (from_user_email = ? AND to_user_email = ?))
                LIMIT 1
                """,
                (email_a, email_b, email_b, email_a),
            ).fetchone()
            return row is not None

    # ============================================================
    # REFERRALS
    # ============================================================

    def create_referral(
        self,
        *,
        referrer_email: str,
        referee_a_email: str,
        referee_b_email: str,
        reason: Optional[str] = None,
    ) -> Optional[str]:
        """X 撮合 A 和 B。返回 rf_id 或 None 表示参数非法。

        约束：三方互不相同（X != A, X != B, A != B）。
        """
        emails = {referrer_email.lower(), referee_a_email.lower(), referee_b_email.lower()}
        if len(emails) != 3:
            return None
        rid = new_referral_id()
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO referrals (
                    id, referrer_email, referee_a_email, referee_b_email,
                    reason, status_a, status_b, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', 'pending', ?)
                """,
                (
                    rid, referrer_email, referee_a_email, referee_b_email,
                    reason, ts,
                ),
            )
        logger.info(
            "referral_created id=%s X=%s A=%s B=%s",
            rid, referrer_email, referee_a_email, referee_b_email,
        )
        return rid

    def get_referral(self, rid: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM referrals WHERE id = ?", (rid,)
            ).fetchone()
            return dict(row) if row else None

    def list_referrals_for_user(self, email: str) -> list[dict]:
        """当前用户相关的所有 referrals（作为 X / A / B 任一）。

        每行追加 role 字段：referrer / referee_a / referee_b。
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *,
                  CASE
                    WHEN referrer_email = ? THEN 'referrer'
                    WHEN referee_a_email = ? THEN 'referee_a'
                    WHEN referee_b_email = ? THEN 'referee_b'
                  END AS role
                FROM referrals
                WHERE referrer_email = ?
                   OR referee_a_email = ?
                   OR referee_b_email = ?
                ORDER BY created_at DESC
                """,
                (email, email, email, email, email, email),
            ).fetchall()
            return [dict(r) for r in rows]

    def respond_referral(
        self, rid: str, responder_email: str, accept: bool
    ) -> tuple[bool, Optional[dict]]:
        """A 或 B 响应一个 referral。

        返回 (success, referral_row)。row 含最新 status_a/status_b。referrer
        无 response 动作（只能看 + 看完成通知）。
        """
        new_status = "accepted" if accept else "declined"
        ts = _now()
        with self._connect() as conn:
            ref = conn.execute(
                "SELECT * FROM referrals WHERE id = ?", (rid,)
            ).fetchone()
            if ref is None:
                return False, None
            ref = dict(ref)
            if responder_email == ref["referee_a_email"]:
                col = "status_a"
                cur_status = ref["status_a"]
            elif responder_email == ref["referee_b_email"]:
                col = "status_b"
                cur_status = ref["status_b"]
            else:
                # 不是当事人——referrer 也不能动 status
                return False, None
            if cur_status != "pending":
                return False, ref
            # 写入
            conn.execute(
                f"UPDATE referrals SET {col} = ? WHERE id = ?",
                (new_status, rid),
            )
            # 双向 accept → 标记 completed
            ref[col] = new_status
            if ref["status_a"] == "accepted" and ref["status_b"] == "accepted":
                conn.execute(
                    "UPDATE referrals SET completed_at = ? "
                    "WHERE id = ? AND completed_at IS NULL",
                    (ts, rid),
                )
                ref["completed_at"] = ts
            return True, ref

    # ============================================================
    # MESSAGES
    # ============================================================

    MESSAGE_DAILY_LIMIT = 10

    def count_messages_sent_today(
        self, from_email: str, *, now_iso: Optional[str] = None
    ) -> int:
        """统计 from_email 在过去 24h 发出的消息数（频率限制窗口）。"""
        from datetime import datetime, timedelta, timezone

        ref = (
            datetime.fromisoformat(now_iso)
            if now_iso
            else datetime.now(timezone.utc)
        )
        cutoff = (ref - timedelta(hours=24)).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM connections_messages "
                "WHERE from_email = ? AND sent_at >= ?",
                (from_email, cutoff),
            ).fetchone()
            return int(row[0]) if row else 0

    def create_message(
        self,
        *,
        from_email: str,
        to_email: str,
        body: str,
    ) -> str:
        """新建一条消息。调用方必须先验证：
          1) from/to 已 matched
          2) to 未 block from
          3) to 没关 messages
          4) from 24h 内 < 10 条
          5) body ≤ 500 字 + 已通过内容过滤
        本层只负责落库。
        """
        mid = new_message_id()
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO connections_messages (
                    id, from_email, to_email, body, sent_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (mid, from_email, to_email, body, ts),
            )
        logger.info(
            "connection_message_sent id=%s from=%s to=%s len=%d",
            mid, from_email, to_email, len(body),
        )
        return mid

    def list_inbox(self, email: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM connections_messages "
                "WHERE to_email = ? ORDER BY sent_at DESC",
                (email,),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_message(self, mid: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM connections_messages WHERE id = ?", (mid,)
            ).fetchone()
            return dict(row) if row else None

    def mark_read(self, mid: str, recipient_email: str) -> bool:
        """收件人标记已读。非收件人调用 → False（隐私边界）。"""
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE connections_messages
                SET read_at = ?
                WHERE id = ? AND to_email = ? AND read_at IS NULL
                """,
                (_now(), mid, recipient_email),
            )
            if cur.rowcount > 0:
                return True
            # 是否已读过了？（区分「不存在/非收件人」vs「已读过」——后者也算 ok）
            existing = conn.execute(
                "SELECT to_email FROM connections_messages WHERE id = ?",
                (mid,),
            ).fetchone()
            return bool(existing and existing[0] == recipient_email)

    # ============================================================
    # PREFERENCES (block / mute / messages_open)
    # ============================================================

    def is_blocked(self, user_email: str, other_email: str) -> bool:
        """user_email 是否 block 了 other_email。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM connections_prefs "
                "WHERE user_email = ? AND blocked_email = ?",
                (user_email, other_email),
            ).fetchone()
            return row is not None

    def set_block(self, user_email: str, other_email: str, block: bool) -> None:
        ts = _now()
        with self._connect() as conn:
            if block:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO connections_prefs (
                        user_email, blocked_email, updated_at
                    ) VALUES (?, ?, ?)
                    """,
                    (user_email, other_email, ts),
                )
            else:
                conn.execute(
                    "DELETE FROM connections_prefs "
                    "WHERE user_email = ? AND blocked_email = ?",
                    (user_email, other_email),
                )

    def _get_global_prefs_row(
        self, conn: sqlite3.Connection, user_email: str
    ) -> Optional[sqlite3.Row]:
        """读 user_email 的全局 prefs 行（blocked_email IS NULL/''）。

        我们用 PK = (user_email, blocked_email)，全局开关存到 blocked_email=''
        的特殊行——既复用同一张表，又避免与具体 block 行冲突。
        """
        return conn.execute(
            "SELECT * FROM connections_prefs "
            "WHERE user_email = ? AND blocked_email = ''",
            (user_email,),
        ).fetchone()

    def get_user_prefs(self, user_email: str) -> dict:
        """返回 {mute_referrals: bool, messages_open: bool, blocked_emails: list}。"""
        with self._connect() as conn:
            row = self._get_global_prefs_row(conn, user_email)
            if row:
                mute = bool(row["mute_referrals"])
                msg_open = bool(row["messages_open"])
            else:
                mute = False
                msg_open = True
            blocks = [
                r["blocked_email"]
                for r in conn.execute(
                    "SELECT blocked_email FROM connections_prefs "
                    "WHERE user_email = ? AND blocked_email != ''",
                    (user_email,),
                ).fetchall()
            ]
            return {
                "mute_referrals": mute,
                "messages_open": msg_open,
                "blocked_emails": blocks,
            }

    def set_user_prefs(
        self,
        user_email: str,
        *,
        mute_referrals: Optional[bool] = None,
        messages_open: Optional[bool] = None,
    ) -> dict:
        """更新全局 prefs（只动给值的字段）。返回最新 prefs 视图。"""
        ts = _now()
        with self._connect() as conn:
            row = self._get_global_prefs_row(conn, user_email)
            if row is None:
                conn.execute(
                    """
                    INSERT INTO connections_prefs (
                        user_email, blocked_email,
                        mute_referrals, messages_open, updated_at
                    ) VALUES (?, '', ?, ?, ?)
                    """,
                    (
                        user_email,
                        1 if (mute_referrals is True) else 0,
                        0 if (messages_open is False) else 1,
                        ts,
                    ),
                )
            else:
                fields = []
                vals: list = []
                if mute_referrals is not None:
                    fields.append("mute_referrals = ?")
                    vals.append(1 if mute_referrals else 0)
                if messages_open is not None:
                    fields.append("messages_open = ?")
                    vals.append(1 if messages_open else 0)
                if fields:
                    fields.append("updated_at = ?")
                    vals.extend([ts, user_email])
                    conn.execute(
                        f"UPDATE connections_prefs SET {', '.join(fields)} "
                        f"WHERE user_email = ? AND blocked_email = ''",
                        vals,
                    )
        return self.get_user_prefs(user_email)

    # ============================================================
    # PRIVACY: delete + export
    # ============================================================

    def delete_all_for_user(self, user_email: str) -> dict:
        """删除某用户在 P3 四张表里的全部记录（参与方任一）。

        返回每张表删除的行数。供 /api/privacy/delete 调用，对齐 SESSION-21 §6
        把 structural_fingerprints 接入 DSAR 删除范围的模式。
        """
        with self._connect() as conn:
            n_mr = conn.execute(
                "DELETE FROM match_requests "
                "WHERE from_user_email = ? OR to_user_email = ?",
                (user_email, user_email),
            ).rowcount
            n_rf = conn.execute(
                "DELETE FROM referrals "
                "WHERE referrer_email = ? "
                "   OR referee_a_email = ? "
                "   OR referee_b_email = ?",
                (user_email, user_email, user_email),
            ).rowcount
            n_cm = conn.execute(
                "DELETE FROM connections_messages "
                "WHERE from_email = ? OR to_email = ?",
                (user_email, user_email),
            ).rowcount
            n_cp = conn.execute(
                "DELETE FROM connections_prefs "
                "WHERE user_email = ? OR blocked_email = ?",
                (user_email, user_email),
            ).rowcount
        return {
            "match_requests": int(n_mr or 0),
            "referrals": int(n_rf or 0),
            "connections_messages": int(n_cm or 0),
            "connections_prefs": int(n_cp or 0),
        }

    def export_all_for_user(self, user_email: str) -> dict:
        """DSAR 导出：把 user_email 参与的 P3 四张表全部行返回。

        与 delete_all_for_user 对称（凡能删的就能拿回）。
        """
        with self._connect() as conn:
            mr = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM match_requests "
                    "WHERE from_user_email = ? OR to_user_email = ? "
                    "ORDER BY created_at DESC",
                    (user_email, user_email),
                ).fetchall()
            ]
            rf = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM referrals "
                    "WHERE referrer_email = ? "
                    "   OR referee_a_email = ? "
                    "   OR referee_b_email = ? "
                    "ORDER BY created_at DESC",
                    (user_email, user_email, user_email),
                ).fetchall()
            ]
            cm = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM connections_messages "
                    "WHERE from_email = ? OR to_email = ? "
                    "ORDER BY sent_at DESC",
                    (user_email, user_email),
                ).fetchall()
            ]
            cp = [
                dict(r) for r in conn.execute(
                    "SELECT * FROM connections_prefs "
                    "WHERE user_email = ? OR blocked_email = ?",
                    (user_email, user_email),
                ).fetchall()
            ]
        return {
            "match_requests": mr,
            "referrals": rf,
            "connections_messages": cm,
            "connections_prefs": cp,
        }


# ============================================================
# Content filter — URL / phone / email blocked for anti-spam
# ============================================================

import re

_RE_URL = re.compile(
    r"(?:https?://|www\.|[A-Za-z0-9._%+-]+\.(?:com|cn|net|org|io|app|dev|me"
    r"|info|biz|co|xyz|top|club|site|tech|store|online|shop|live|fun|today"
    r"|news|tv|cc|gov|edu)/?)\S*",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Phone: 7+ digit run (with optional separators) — catches CN mobile (11),
# US (10), international with country code. Conservative on false positives.
_RE_PHONE = re.compile(r"(?:\+?\d[\s\-\.]?){7,}")
# Common social-platform handles (we treat as PII leak channel)
_RE_HANDLE = re.compile(
    r"(?:微信|wechat|weixin|qq|telegram|whatsapp|line|kakao|微信号|手机号)\s*[:：]?\s*\S+",
    re.IGNORECASE,
)


def detect_pii_leak(text: str) -> Optional[str]:
    """检查消息正文是否包含 URL / 电话 / email / 社交账号。

    返回触发的类别名（首个命中），或 None。检查顺序对 email-vs-url 有讲究：
    email 含 @ + 顶级域，URL 正则也会顺手命中其右半部分（a@b.com 的 b.com）。
    所以**先查 email**，再查 URL，避免把 email 误归类为 URL。
    """
    if _RE_EMAIL.search(text):
        return "email"
    if _RE_URL.search(text):
        return "url"
    if _RE_PHONE.search(text):
        return "phone"
    if _RE_HANDLE.search(text):
        return "handle"
    return None


__all__ = [
    "ConnectionsP3Store",
    "MATCH_REQUEST_STATUS",
    "REFERRAL_PARTY_STATUS",
    "new_request_id",
    "new_referral_id",
    "new_message_id",
    "detect_pii_leak",
]
