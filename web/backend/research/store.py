"""Research tables in the canonical auth SQLite; no alternate content DB."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .errors import ResearchError

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS research_schema (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)",
    """CREATE TABLE IF NOT EXISTS research_principals (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind='account'),
        normalized_email TEXT, session_generation TEXT,
        epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 2147483647),
        status TEXT NOT NULL CHECK(status IN ('active','revoked','deleting','deleted')),
        created_at TEXT NOT NULL, gate_id TEXT,
        UNIQUE(normalized_email, session_generation))""",
    """CREATE TABLE IF NOT EXISTS research_controls (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES research_principals(id),
        owner_epoch INTEGER NOT NULL CHECK(owner_epoch BETWEEN 1 AND 2147483647),
        acl_epoch INTEGER NOT NULL CHECK(acl_epoch BETWEEN 1 AND 2147483647),
        current_revision INTEGER NOT NULL CHECK(current_revision BETWEEN 1 AND 2147483647),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 2147483647),
        visibility TEXT NOT NULL CHECK(visibility='private'),
        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('active','deleting','deleted')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_grants (
        id TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES research_principals(id),
        principal_epoch INTEGER NOT NULL CHECK(principal_epoch BETWEEN 1 AND 2147483647),
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        acl_epoch INTEGER NOT NULL CHECK(acl_epoch BETWEEN 1 AND 2147483647),
        scopes TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','revoked')),
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_revisions (
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 2147483647),
        problem_json TEXT NOT NULL CHECK(json_valid(problem_json)),
        digest TEXT NOT NULL CHECK(length(digest)=64), created_at TEXT NOT NULL,
        PRIMARY KEY(research_id, revision))""",
    """CREATE TRIGGER IF NOT EXISTS research_revision_no_update
        BEFORE UPDATE ON research_revisions BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""",
    """CREATE TABLE IF NOT EXISTS research_idempotency (
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        operation TEXT NOT NULL, scope_key TEXT NOT NULL, key_digest TEXT NOT NULL,
        request_digest TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json)),
        PRIMARY KEY(principal_id, operation, scope_key, key_digest))""",
    "CREATE INDEX IF NOT EXISTS research_owner_idx ON research_controls(owner_id, lifecycle)",
)

C0_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS research_tasks (
        id TEXT PRIMARY KEY, research_id TEXT REFERENCES research_controls(id) ON DELETE SET NULL,
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        principal_epoch INTEGER, owner_epoch INTEGER, acl_epoch INTEGER,
        grant_id TEXT REFERENCES research_grants(id) ON DELETE SET NULL,
        auth_generation TEXT, input_revision INTEGER, input_digest TEXT, start_version INTEGER NOT NULL,
        execution TEXT NOT NULL CHECK(execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING','COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED')),
        phase TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT 'UNASSESSED',
        stop_requested INTEGER NOT NULL DEFAULT 0 CHECK(stop_requested IN (0,1)),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 2147483647),
        attempt INTEGER NOT NULL DEFAULT 1 CHECK(attempt=1),
        policy_revision TEXT NOT NULL CHECK(policy_revision IN ('c0-fixture-v1','d1-source-only-v1')),
        execution_mode TEXT NOT NULL CHECK(execution_mode IN ('offline_probe','live')),
        reconcile_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS research_one_active_task ON research_tasks(research_id)
        WHERE research_id IS NOT NULL AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')""",
    """CREATE TABLE IF NOT EXISTS research_attempts (
        task_id TEXT PRIMARY KEY REFERENCES research_tasks(id), attempt INTEGER NOT NULL CHECK(attempt=1),
        reason TEXT NOT NULL CHECK(reason='initial'), policy_revision TEXT NOT NULL, input_digest TEXT)""",
    """CREATE TABLE IF NOT EXISTS research_steps (
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES research_tasks(id),
        position INTEGER NOT NULL CHECK(position IN (0,1,2)),
        kind TEXT NOT NULL CHECK(kind IN ('discover_sources','fetch_source','compose_report')),
        state TEXT NOT NULL CHECK(state IN ('PENDING','PREPARED','SENDING','AWAITING_RECEIPT','SUCCEEDED','UNKNOWN','DISCARDED','FAILED')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(version BETWEEN 1 AND 2147483647),
        reservation_id TEXT, UNIQUE(task_id,position))""",
    """CREATE TABLE IF NOT EXISTS research_task_events (
        task_id TEXT NOT NULL REFERENCES research_tasks(id), seq INTEGER NOT NULL,
        state_version INTEGER NOT NULL, kind TEXT NOT NULL, safe_code TEXT,
        at TEXT NOT NULL, PRIMARY KEY(task_id,seq))""",
    """CREATE TABLE IF NOT EXISTS research_step_outputs (
        step_id TEXT PRIMARY KEY REFERENCES research_steps(id), task_id TEXT NOT NULL REFERENCES research_tasks(id),
        note TEXT NOT NULL, execution_mode TEXT NOT NULL CHECK(execution_mode='offline_probe'), created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_funding_accounts (
        id TEXT PRIMARY KEY, binding_id TEXT NOT NULL UNIQUE,
        fixture_port INTEGER NOT NULL CHECK(fixture_port BETWEEN 1 AND 65535),
        mode TEXT NOT NULL CHECK(mode='fixture'), currency TEXT NOT NULL CHECK(currency='USD'),
        scale INTEGER NOT NULL CHECK(scale=6), funding_epoch INTEGER NOT NULL CHECK(funding_epoch>0),
        cap INTEGER NOT NULL CHECK(cap=10000), settled INTEGER NOT NULL DEFAULT 0 CHECK(settled>=0),
        held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0),
        status TEXT NOT NULL CHECK(status IN ('active','unverified','reconciling','blocked')),
        snapshot_id TEXT, version INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS research_balance_snapshots (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        balance INTEGER NOT NULL CHECK(balance BETWEEN 0 AND 9223372036854775807),
        settled_at_observation INTEGER NOT NULL CHECK(settled_at_observation>=0),
        local_settlement_cursor INTEGER NOT NULL CHECK(local_settlement_cursor>=0), observed_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, hard_prepaid INTEGER NOT NULL CHECK(hard_prepaid=1),
        auto_topup_off INTEGER NOT NULL CHECK(auto_topup_off=1), postpaid_off INTEGER NOT NULL CHECK(postpaid_off=1))""",
    """CREATE TABLE IF NOT EXISTS research_price_revisions (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        operation TEXT NOT NULL CHECK(operation IN ('discover_sources','compose_report')),
        currency TEXT NOT NULL CHECK(currency='USD'), scale INTEGER NOT NULL CHECK(scale=6),
        input_rate INTEGER NOT NULL CHECK(input_rate>=0), output_rate INTEGER NOT NULL CHECK(output_rate>=0),
        max_input INTEGER NOT NULL CHECK(max_input>=0), max_output INTEGER NOT NULL CHECK(max_output>=0),
        fixed_units INTEGER NOT NULL CHECK(fixed_units>=0),
        rounding TEXT NOT NULL CHECK(rounding IN ('ceil_total','ceil_components')),
        expires_at TEXT NOT NULL, UNIQUE(account_id,operation))""",
    """CREATE TABLE IF NOT EXISTS research_reservations (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        task_id TEXT NOT NULL REFERENCES research_tasks(id), step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        operation_key TEXT NOT NULL UNIQUE, price_revision TEXT NOT NULL REFERENCES research_price_revisions(id),
        funding_epoch INTEGER NOT NULL, max_cost INTEGER NOT NULL CHECK(max_cost BETWEEN 0 AND 9223372036854775807),
        settled_cost INTEGER CHECK(settled_cost BETWEEN 0 AND 9223372036854775807),
        status TEXT NOT NULL CHECK(status IN ('HELD','SENT','UNKNOWN','SETTLED','RELEASED')),
        version INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS research_dispatch_permits (
        id TEXT PRIMARY KEY, step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        reservation_id TEXT NOT NULL UNIQUE REFERENCES research_reservations(id),
        dispatch_id TEXT NOT NULL UNIQUE, input_digest TEXT,
        state TEXT NOT NULL CHECK(state IN ('prepared','consumed','revoked')),
        expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_billing_receipts (
        id TEXT PRIMARY KEY, reservation_id TEXT NOT NULL REFERENCES research_reservations(id),
        account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        provider_ref TEXT NOT NULL, digest TEXT NOT NULL, cost INTEGER,
        status TEXT NOT NULL CHECK(status IN ('known','nonfinal','anomaly')),
        at TEXT NOT NULL, UNIQUE(account_id,provider_ref))""",
)


class ResearchStore:
    def __init__(self, auth_store):
        self.auth_store = auth_store
        self.path = Path(auth_store.path).resolve()
        # AuthStore already initializes auth tables and WAL with its own lock.
        with self.transaction(write=True) as conn:
            conn.execute(SCHEMA[0])
            row = conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()
            if row is not None and row["version"] not in (1, 2, 3, 4):
                raise ResearchError("SCHEMA_UNSUPPORTED", 503, "研究数据版本暂不支持。")
            for statement in SCHEMA[1:]:
                conn.execute(statement)
            columns = {item["name"] for item in conn.execute("PRAGMA table_info(research_principals)")}
            if "gate_id" not in columns:
                conn.execute("ALTER TABLE research_principals ADD COLUMN gate_id TEXT")
            for principal in conn.execute("SELECT id,normalized_email FROM research_principals WHERE gate_id IS NULL").fetchall():
                if not principal["normalized_email"]:
                    raise ResearchError("SCHEMA_UNSUPPORTED", 503, "研究主体迁移缺少必要绑定。")
                gate_id = self.auth_store.owner_gate_in(conn, principal["normalized_email"], principal["id"])
                conn.execute("UPDATE research_principals SET gate_id=? WHERE id=?", (gate_id, principal["id"]))
            conn.execute("""CREATE TRIGGER IF NOT EXISTS research_principal_gate_required
                BEFORE INSERT ON research_principals WHEN NEW.gate_id IS NULL
                BEGIN SELECT RAISE(ABORT, 'principal gate required'); END""")
            for statement in C0_SCHEMA:
                conn.execute(statement)
            for table in ("research_price_revisions","research_balance_snapshots","research_billing_receipts"):
                conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable
                    BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable accounting record'); END""")
            conn.execute("INSERT INTO research_schema VALUES(1,3) ON CONFLICT(id) DO NOTHING")
        self._migrate_v4()

    def _migrate_v4(self):
        """Controlled SQLite table replacement, never an application session.

        FK enforcement is suspended only on this migration connection, before
        BEGIN. No network/records API uses it. Validate the full graph before
        commit; every failure rolls back the original tables and schema value.
        """
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        conn.row_factory=sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=OFF")
            if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移连接配置失败。")
            conn.execute("BEGIN IMMEDIATE")
            self.auth_store.check_gate_policy(conn)
            version=conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0]
            if version==4:
                from .source_integration import install_schema
                install_schema(conn,existing_required=True)
                conn.commit();return
            if version not in (1,2,3):raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移版本不支持。")
            for name in ("research_tasks","research_steps"):
                ddl=next(sql for sql in C0_SCHEMA if sql.startswith("CREATE TABLE IF NOT EXISTS "+name+" ("))
                previous=conn.execute("SELECT sql FROM sqlite_schema WHERE name=? AND type='table'",(name,)).fetchone()
                old=ddl.replace("IN ('c0-fixture-v1','d1-source-only-v1')","='c0-fixture-v1'").replace("IN ('offline_probe','live')","='offline_probe'")
                old=old.replace("IN (0,1,2)","IN (0,1)").replace("'discover_sources','fetch_source','compose_report'","'discover_sources','compose_report'")
                normalize=lambda sql:"".join(sql.replace("IF NOT EXISTS","").replace('"', '').split()).lower()
                if not previous or normalize(previous[0]) not in {normalize(ddl),normalize(old)}:
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究旧表结构与迁移基准不一致。")
                for extra in conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(name,)):
                    expected=next((sql for sql in C0_SCHEMA if sql.startswith("CREATE UNIQUE INDEX IF NOT EXISTS "+extra["name"]+" ")),None)
                    if extra["type"]!="index" or expected is None or normalize(extra["sql"])!=normalize(expected):
                        raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究旧表附属结构与迁移基准不一致。")
                conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS "+name,"CREATE TABLE "+name+"_v4",1))
                conn.execute(f"INSERT INTO {name}_v4 SELECT * FROM {name}")
            conn.execute("DROP TABLE research_steps")
            conn.execute("DROP TABLE research_tasks")
            conn.execute("ALTER TABLE research_tasks_v4 RENAME TO research_tasks")
            conn.execute("ALTER TABLE research_steps_v4 RENAME TO research_steps")
            for sql in C0_SCHEMA:
                if sql.startswith("CREATE UNIQUE INDEX"):conn.execute(sql)
            from .source_integration import install_schema
            install_schema(conn)
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移关联校验失败。")
            conn.execute("UPDATE research_schema SET version=4 WHERE id=1")
            conn.commit()
        except Exception:
            conn.rollback();raise
        finally:
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移连接恢复失败。")
            finally:
                conn.close()

    @contextmanager
    def transaction(self, *, write=False):
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA secure_delete=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            self.auth_store.check_gate_policy(conn)
            yield conn
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if getattr(exc, "sqlite_errorcode", 0) & 255 in (5, 6):
                raise ResearchError("STORE_BUSY", 503, "保存暂时繁忙，请用原操作重试。", retryable=True) from None
            raise ResearchError("STORE_UNAVAILABLE", 503, "研究存储暂时不可用。") from None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def checkpoint_erasure(self):
        """Do not report erasure while old WAL frames are held by a reader."""
        conn = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            self.auth_store.check_gate_policy(conn)
            conn.execute("PRAGMA busy_timeout=5000")
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result[0] != 0:
                raise ResearchError("STORE_BUSY", 503, "删除等待存储清理完成。", retryable=True)
        finally:
            conn.close()
