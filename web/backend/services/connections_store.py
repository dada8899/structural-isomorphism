"""ConnectionsStore — G 方向「按问题结构连接人」的数据访问层。

Session ***REMOVED***19 G-MVP（P1 指纹抽取 + P2 匹配引擎 / L1 可发现）。

设计依据：docs/sessions/SESSION-18-G-connect-people-design.md §3。本 MVP 落
P1 + P2，不做 P3（双向同意 match 流程 / 引荐 / 消息）。

存储：复用 history.db（与 reports / report_followup 同一 SQLite 文件），
新增一张表 `structural_fingerprints`。一个用户可登记多个指纹（解多个
问题）。表自动建 + 加列自愈，沿用 report_store 的模式。

可见性三级（设计 §3.3，默认最严）：
    L0  私密         —— 指纹只属于自己，不参与任何发现
    L1  结构可发现   —— 参与匿名计数（「N 人在解结构相同的问题」）
    L2  可引荐       —— 允许进入 match 流程（P3，本 MVP 不实现交流载体）

指纹向量（embedding）由调用方用 SearchService.encode_query() 算好后以
float32 BLOB 存入；匹配时复用 SearchService._cosine()（已正确处理未
L2-归一化的向量）。
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("structural.connections")

***REMOVED*** 合法可见性级别。默认 L0（最严）。
VISIBILITY_LEVELS = ("L0", "L1", "L2")
DEFAULT_VISIBILITY = "L0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_fingerprint_id() -> str:
    return "fp_" + uuid.uuid4().hex[:16]


***REMOVED*** structural_fingerprints —— 一个用户可有多个指纹。
***REMOVED*** embedding 存 float32 little-endian 裸字节（np.ndarray.astype('<f4').tobytes()）。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS structural_fingerprints (
    id                 TEXT PRIMARY KEY,
    user_email         TEXT NOT NULL,
    source_report_id   TEXT,
    b_id               TEXT,
    domain             TEXT,
    type_id            TEXT,
    universality_class TEXT,
    problem_summary    TEXT NOT NULL,
    embedding          BLOB,
    visibility_level   TEXT NOT NULL DEFAULT 'L0',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fp_user
    ON structural_fingerprints(user_email, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fp_visibility
    ON structural_fingerprints(visibility_level);
"""

***REMOVED*** 表必须有的列。CREATE TABLE IF NOT EXISTS 在旧表上是 no-op，所以这里
***REMOVED*** 显式列出，加列自愈（沿用 report_store 的 _migrate 模式）。
_FP_COLUMNS = (
    ("user_email", "TEXT"),
    ("source_report_id", "TEXT"),
    ("b_id", "TEXT"),
    ("domain", "TEXT"),
    ("type_id", "TEXT"),
    ("universality_class", "TEXT"),
    ("problem_summary", "TEXT"),
    ("embedding", "BLOB"),
    ("visibility_level", "TEXT NOT NULL DEFAULT 'L0'"),
    ("created_at", "TEXT"),
    ("updated_at", "TEXT"),
)


class ConnectionsStore:
    """structural_fingerprints 表的薄 SQLite 封装。

    自动建表 + 加列自愈。与 ReportStore 复用同一 history.db。
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    ***REMOVED*** --- 连接 / schema --------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as e:  ***REMOVED*** pragma: no cover
            logger.warning("connections_store WAL pragma failed: %s", e)
        return conn

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                ***REMOVED*** 先迁移：旧表可能缺列，建索引前补齐避免 OperationalError。
                self._migrate_columns(conn)
                conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            logger.error("connections_store schema init failed: %s", e)
            raise

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        """旧表缺列时增量补齐。ALTER TABLE ADD COLUMN 只加不改。"""
        existing = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(structural_fingerprints)"
            ).fetchall()
        }
        if not existing:
            return  ***REMOVED*** 表不存在 → 交给 CREATE TABLE
        for col, col_def in _FP_COLUMNS:
            if col not in existing:
                logger.warning(
                    "connections_store: fingerprints table missing %r — adding",
                    col,
                )
                conn.execute(
                    f"ALTER TABLE structural_fingerprints "
                    f"ADD COLUMN {col} {col_def}"
                )

    ***REMOVED*** --- 写 -------------------------------------------------------------

    def create_fingerprint(
        self,
        *,
        user_email: str,
        problem_summary: str,
        embedding: Optional[bytes] = None,
        source_report_id: Optional[str] = None,
        b_id: Optional[str] = None,
        domain: Optional[str] = None,
        type_id: Optional[str] = None,
        universality_class: Optional[str] = None,
        visibility_level: str = DEFAULT_VISIBILITY,
    ) -> str:
        """登记一个指纹。返回 fingerprint id。

        visibility_level 非法值一律降级为最严 L0（不信任输入）。
        """
        if visibility_level not in VISIBILITY_LEVELS:
            logger.warning(
                "create_fingerprint: bad visibility %r → forcing L0",
                visibility_level,
            )
            visibility_level = DEFAULT_VISIBILITY
        fid = new_fingerprint_id()
        ts = _now()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO structural_fingerprints (
                    id, user_email, source_report_id, b_id, domain,
                    type_id, universality_class, problem_summary, embedding,
                    visibility_level, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fid, user_email, source_report_id, b_id, domain,
                    type_id, universality_class, problem_summary, embedding,
                    visibility_level, ts, ts,
                ),
            )
        logger.info(
            "connections.fingerprint_created id=%s user=%s vis=%s",
            fid, user_email, visibility_level,
        )
        return fid

    def set_visibility(self, fid: str, user_email: str, level: str) -> bool:
        """改可见性。只有 owner 能改。返回是否命中一行。

        非法 level 拒绝（返回 False，不静默降级——这是用户显式动作）。
        """
        if level not in VISIBILITY_LEVELS:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE structural_fingerprints
                SET visibility_level = ?, updated_at = ?
                WHERE id = ? AND user_email = ?
                """,
                (level, _now(), fid, user_email),
            )
            return cur.rowcount > 0

    def delete_fingerprint(self, fid: str, user_email: str) -> bool:
        """删除指纹。只有 owner 能删。返回是否命中一行。"""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM structural_fingerprints "
                "WHERE id = ? AND user_email = ?",
                (fid, user_email),
            )
            return cur.rowcount > 0

    def delete_all_for_user(self, user_email: str) -> int:
        """删某用户的全部指纹。供 /api/privacy/delete 调用。返回删除行数。"""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM structural_fingerprints WHERE user_email = ?",
                (user_email,),
            )
            return cur.rowcount

    ***REMOVED*** --- 读 -------------------------------------------------------------

    def get_fingerprint(self, fid: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM structural_fingerprints WHERE id = ?", (fid,)
            ).fetchone()
            return dict(row) if row else None

    def list_by_user(self, user_email: str) -> list[dict]:
        """列出某用户的全部指纹，新的在前。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM structural_fingerprints "
                "WHERE user_email = ? ORDER BY created_at DESC",
                (user_email,),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_discoverable(
        self, *, exclude_user: Optional[str] = None
    ) -> list[dict]:
        """列出所有 L1/L2（可发现）指纹。

        匹配引擎从这里取候选集。exclude_user 用于排除自己。
        L0 永不出现在结果里。
        """
        with self._connect() as conn:
            if exclude_user:
                rows = conn.execute(
                    "SELECT * FROM structural_fingerprints "
                    "WHERE visibility_level IN ('L1','L2') "
                    "AND user_email != ?",
                    (exclude_user,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM structural_fingerprints "
                    "WHERE visibility_level IN ('L1','L2')"
                ).fetchall()
            return [dict(r) for r in rows]

    def count_discoverable(self) -> int:
        """L1/L2 指纹总数，用于 /insights 之类的聚合展示。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM structural_fingerprints "
                "WHERE visibility_level IN ('L1','L2')"
            ).fetchone()
            return int(row[0]) if row else 0


__all__ = [
    "ConnectionsStore",
    "VISIBILITY_LEVELS",
    "DEFAULT_VISIBILITY",
    "new_fingerprint_id",
]
