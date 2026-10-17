"""Transactional SQLite storage for passwordless authentication."""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

try:
    from .privacy_identifiers import opaque_identifier
except ImportError:
    from privacy_identifiers import opaque_identifier


_INITIALIZATION_LOCK = threading.RLock()
_PRIVATE_AUTH_PATHS = vars(sqlite3).setdefault('_structural_private_auth_paths_v1',set())
_RATE_BUCKET_KEY_RE = re.compile(
    r"^(?:global:magic-link-email|[a-z][a-z0-9_.-]{1,63}:v2:[0-9a-f]{64})$"
)


def _require_private_rate_bucket(key: str) -> None:
    if not _RATE_BUCKET_KEY_RE.fullmatch(key):
        raise ValueError("rate-limit writes require a v2 HMAC or global bucket")

_BASE_SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS auth_users (
        email TEXT PRIMARY KEY, tier TEXT NOT NULL, created_at TEXT NOT NULL,
        session_generation TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS magic_tokens (
        token_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
        created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
        consumed_at TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS revoked_sessions (
        jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL, email TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS auth_rate_requests (
        email TEXT NOT NULL, requested_at INTEGER NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS idx_auth_rate
        ON auth_rate_requests(email, requested_at)""",
    """CREATE TABLE IF NOT EXISTS auth_notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL, email TEXT NOT NULL,
        created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT, delivered_at TEXT, claimed_at INTEGER,
        UNIQUE(kind, email)
    )""",
    """CREATE TABLE IF NOT EXISTS account_deletion_epochs (
        owner_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS auth_owner_gates (
        owner_key TEXT PRIMARY KEY, gate_id TEXT NOT NULL UNIQUE
    )""",
    """CREATE TABLE IF NOT EXISTS auth_owner_gate_policy (
        id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS auth_deletion_jobs (
        id TEXT PRIMARY KEY, owner_key TEXT NOT NULL, gate_id TEXT NOT NULL,
        cleanup_binding TEXT NOT NULL,
        database_binding TEXT NOT NULL,
        owner_email TEXT, session_generation TEXT,
        state TEXT NOT NULL CHECK(state IN ('pending','scrubbing','completed')),
        research_erased INTEGER NOT NULL DEFAULT 0 CHECK(research_erased IN (0,1)),
        legacy_attempted INTEGER NOT NULL DEFAULT 0 CHECK(legacy_attempted IN (0,1)),
        legacy_receipt_json TEXT CHECK(legacy_receipt_json IS NULL OR json_valid(legacy_receipt_json)),
        research_counts_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT, created_at TEXT NOT NULL, completed_at TEXT
    )""",
    """CREATE UNIQUE INDEX IF NOT EXISTS auth_one_pending_deletion
        ON auth_deletion_jobs(owner_key) WHERE state!='completed'""",
)


def _is_sqlite_lock_error(exc: sqlite3.OperationalError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    if isinstance(code, int) and code & 0xFF in {
        getattr(sqlite3, "SQLITE_BUSY", 5),
        getattr(sqlite3, "SQLITE_LOCKED", 6),
    }:
        return True
    return "locked" in str(exc).lower() or "busy" in str(exc).lower()


def _ensure_wal_mode(path: Path, timeout_seconds: float = 10.0) -> None:
    """Select WAL once, retrying only cross-process SQLite lock contention."""
    deadline = time.monotonic() + timeout_seconds
    delay = 0.01
    last_lock_error: sqlite3.OperationalError | None = None
    last_mode: str | None = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            detail = f"; last mode was {last_mode}" if last_mode else ""
            raise RuntimeError(
                f"auth database WAL initialization timed out{detail}"
            ) from last_lock_error

        bootstrap = sqlite3.connect(
            path,
            timeout=min(remaining, 1.0),
            isolation_level=None,
        )
        try:
            bootstrap.execute(
                "PRAGMA busy_timeout=%d" % max(1, int(min(remaining, 1.0) * 1000))
            )
            last_mode = str(
                bootstrap.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower()
            if last_mode == "wal":
                return
            last_mode = str(
                bootstrap.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            ).lower()
            if last_mode == "wal":
                return
            raise RuntimeError(
                f"auth database refused WAL journal mode: {last_mode}"
            )
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_lock_error(exc):
                raise
            last_lock_error = exc
        finally:
            bootstrap.close()

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            continue
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 0.25)


class DeletedCredentialError(ValueError):
    """A credential predates the owner's latest account deletion."""


def _formal_auth_mode():
    from .runtime_paths import RuntimePathError
    raw=os.getenv('STRUCTURAL_ENV','dev')
    if raw.strip().lower()=='prod' and raw.lower()!='prod':
        raise RuntimePathError('private auth profile contains invalid whitespace')
    return raw.lower()=='prod'


def _auth_sql_tokens(sql):
    if __package__=='web.backend.services':from ..research.store import ResearchStore
    else:from research.store import ResearchStore
    managed={'auth_users','magic_tokens','revoked_sessions','auth_rate_requests','idx_auth_rate',
             'auth_notification_outbox','account_deletion_epochs','auth_owner_gates','auth_owner_gate_policy','sqlite_sequence'}
    return tuple(('word',value.lower()) if kind=='quoted_identifier' and value.lower() in managed else (kind,value)
                 for kind,value in ResearchStore._normalize_sql(sql))


def _auth_metadata(conn,*,allowed=None):
    objects={};columns={};indexes={}
    for kind,name,target,sql in conn.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema'):
        # Core owns these exact scopes; check_current_structure validates them.
        if name.startswith('research_') or target.startswith('research_') or target=='auth_deletion_jobs':continue
        objects[name]=(kind,target,_auth_sql_tokens(sql) if sql is not None else None)
    if allowed is not None and objects not in [form[0] for form in allowed]:
        raise RuntimeError('private Auth schema objects are incomplete or unknown')
    for name,(kind,target,sql) in objects.items():
        quoted='"'+name.replace('"','""')+'"'
        if kind=='table':
            columns[name]=tuple(tuple(r) for r in conn.execute('PRAGMA main.table_xinfo('+quoted+')'))
        elif kind=='index':
            indexes[name]=tuple(tuple(r) for r in conn.execute('PRAGMA main.index_xinfo('+quoted+')'))
    return objects,columns,indexes


_LEGACY_AUTH_DDL = (
    'CREATE TABLE IF NOT EXISTS auth_users (email TEXT PRIMARY KEY, tier TEXT NOT NULL, created_at TEXT NOT NULL, session_generation TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS magic_tokens (token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT)',
    'CREATE TABLE IF NOT EXISTS revoked_sessions (jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL, email TEXT)',
    'CREATE TABLE IF NOT EXISTS auth_rate_requests (email TEXT NOT NULL, requested_at INTEGER NOT NULL)',
    'CREATE INDEX IF NOT EXISTS idx_auth_rate ON auth_rate_requests(email, requested_at)',
    'CREATE TABLE IF NOT EXISTS auth_notification_outbox (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, email TEXT NOT NULL, created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, delivered_at TEXT, claimed_at INTEGER, UNIQUE(kind, email))',
    'CREATE TABLE IF NOT EXISTS account_deletion_epochs (owner_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS auth_owner_gates (owner_key TEXT PRIMARY KEY, gate_id TEXT NOT NULL UNIQUE)',
    'CREATE TABLE IF NOT EXISTS auth_owner_gate_policy (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL)',
)


def _build_auth_contracts(declarations, *, registration=False):
    from .sqlite_utils import ClosingConnection
    forms=[]
    for nullable_generation in (False,True):
        with sqlite3.connect(':memory:',isolation_level=None,factory=ClosingConnection) as conn:
            for ddl in declarations:
                if nullable_generation and ddl.startswith('CREATE TABLE IF NOT EXISTS auth_users'):
                    ddl=ddl.replace('session_generation TEXT NOT NULL','session_generation TEXT')
                conn.execute(ddl)
            conn.execute(_AUTH_LIFECYCLE_SQL)
            if registration:
                from .auth_registration import AUTH_REGISTRATION_DDL
                for ddl in AUTH_REGISTRATION_DDL:conn.execute(ddl)
            forms.append(_auth_metadata(conn))
    return tuple(forms)


@lru_cache(maxsize=1)
def _legacy_auth_contracts():
    return _build_auth_contracts(_LEGACY_AUTH_DDL)


@lru_cache(maxsize=1)
def _auth_final_contracts():
    return _build_auth_contracts(tuple(ddl for ddl in _BASE_SCHEMA_STATEMENTS if 'auth_deletion_jobs' not in ddl),registration=True)


_AUTH_LIFECYCLE_SQL="ALTER TABLE auth_users ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','deleting'))"


class AuthStore:
    @staticmethod
    def check_offline_auth_metadata(conn):
        if not isinstance(conn,sqlite3.Connection) or not conn.in_transaction:
            raise PermissionError('actual SQLite metadata transaction required')
        legacy=_legacy_auth_contracts();current=_auth_final_contracts()
        metadata=_auth_metadata(conn,allowed=legacy+current)
        if metadata in legacy:return 'legacy_auth'
        if metadata in current:return 'auth-provision-v1'
        raise RuntimeError('private Auth complete metadata differs')

    def expected_owner_gate_identity(self,gate_id):
        from .auth_registration import expected_owner_gate_identity
        return expected_owner_gate_identity(self,gate_id)

    def _require_legacy_mutation(self):
        if getattr(self,'_private_auth',False) or _formal_auth_mode():
            raise PermissionError('private account mutation requires controlled registration')

    def __init__(self, path: Path):
        self.path = Path(path)
        self._private_auth = _formal_auth_mode()
        if not self._private_auth and self.path in _PRIVATE_AUTH_PATHS:
            raise PermissionError('a captured private Auth path cannot be reopened as development')
        self._storage_identity = None
        if self._private_auth:
            self._storage_identity = self.preflight_private(self.path)
            _PRIVATE_AUTH_PATHS.add(self.path)
            return
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        # WAL selection and schema migration are one-time mutable operations.
        # Serialise constructors and avoid asking every request connection to
        # renegotiate journal mode while another thread owns a write lock.
        with _INITIALIZATION_LOCK:
            _ensure_wal_mode(self.path)

        with _INITIALIZATION_LOCK, self._connection(bootstrap=True) as conn:
            # BEGIN IMMEDIATE is the cross-process migration lock. All schema
            # inspection happens after it is acquired so a process that waited
            # for another migrator cannot act on stale PRAGMA table_info data.
            conn.execute("BEGIN IMMEDIATE")
            try:
                for statement in _BASE_SCHEMA_STATEMENTS:
                    conn.execute(statement)
                self.check_gate_policy(conn, initialize=True)
                revoked_columns = {
                    row[1]
                    for row in conn.execute(
                        "PRAGMA table_info(revoked_sessions)"
                    ).fetchall()
                }
                if "email" not in revoked_columns:
                    conn.execute("ALTER TABLE revoked_sessions ADD COLUMN email TEXT")
                user_columns = {
                    row[1]
                    for row in conn.execute("PRAGMA table_info(auth_users)").fetchall()
                }
                if "session_generation" not in user_columns:
                    conn.execute(
                        "ALTER TABLE auth_users ADD COLUMN session_generation TEXT"
                    )
                    conn.execute(
                        "UPDATE auth_users "
                        "SET session_generation=lower(hex(randomblob(16))) "
                        "WHERE session_generation IS NULL"
                    )
                if "lifecycle" not in user_columns:
                    conn.execute(_AUTH_LIFECYCLE_SQL)
                deletion_columns = {row[1] for row in conn.execute("PRAGMA table_info(auth_deletion_jobs)")}
                if "legacy_attempted" not in deletion_columns:
                    conn.execute("ALTER TABLE auth_deletion_jobs ADD COLUMN legacy_attempted INTEGER NOT NULL DEFAULT 0 CHECK(legacy_attempted IN (0,1))")
                    # An older pending job may already have committed legacy
                    # deletes. Missing a receipt is not proof of no attempt.
                    conn.execute("UPDATE auth_deletion_jobs SET legacy_attempted=1")
                if "legacy_receipt_json" not in deletion_columns:
                    conn.execute("ALTER TABLE auth_deletion_jobs ADD COLUMN legacy_receipt_json TEXT CHECK(legacy_receipt_json IS NULL OR json_valid(legacy_receipt_json))")
                epoch_columns = {
                    row[1]
                    for row in conn.execute(
                        "PRAGMA table_info(account_deletion_epochs)"
                    ).fetchall()
                }
                if "email" in epoch_columns:
                    # Migrate the brief pre-release schema without retaining
                    # raw deleted-account identifiers in the security marker.
                    rows = conn.execute(
                        "SELECT email,deleted_at FROM account_deletion_epochs"
                    ).fetchall()
                    conn.execute(
                        "ALTER TABLE account_deletion_epochs "
                        "RENAME TO account_deletion_epochs_raw"
                    )
                    conn.execute(
                        "CREATE TABLE account_deletion_epochs("
                        "owner_hash TEXT PRIMARY KEY,deleted_at TEXT NOT NULL)"
                    )
                    conn.executemany(
                        "INSERT INTO account_deletion_epochs(owner_hash,deleted_at) VALUES(?,?)",
                        [(_email_hash(row["email"]), row["deleted_at"]) for row in rows],
                    )
                    conn.execute("DROP TABLE account_deletion_epochs_raw")
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    @property
    def storage_identity(self):
        return self._storage_identity

    @classmethod
    def preflight_private(cls,path):
        from .sqlite_utils import connect_private_auth
        if __package__=='web.backend.services':from ..research.store import ResearchStore
        else:from research.store import ResearchStore
        conn=connect_private_auth(path,readonly=True)
        identity=conn.private_storage_identity
        try:
            conn.execute('BEGIN')
            allowed=_auth_final_contracts()
            if _auth_metadata(conn,allowed=allowed) not in allowed:
                raise RuntimeError('private Auth final columns or indexes differ')
            ResearchStore.check_current_structure(conn)
            rows=[tuple(row) for row in conn.execute('SELECT id,fingerprint FROM auth_owner_gate_policy')]
            if len(rows)!=1 or type(rows[0][0]) is not int or rows[0][0]!=1:
                raise RuntimeError('private Auth policy control row is missing or ambiguous')
            cls.check_gate_policy(conn,initialize=False)
            return identity
        finally:
            conn.close()

    @contextmanager
    def _connection(self, *, bootstrap=False) -> Iterator[sqlite3.Connection]:
        from .sqlite_utils import connect_private_auth
        current_formal=_formal_auth_mode()
        if current_formal and not getattr(self,'_private_auth',False):
            raise RuntimeError('a development Auth object cannot become a private runtime object')
        formal=getattr(self,'_private_auth',False) or current_formal
        if formal:
            if bootstrap:raise RuntimeError('private Auth bootstrap is a separate controlled operation')
            conn=connect_private_auth(self.path,expected_identity=self.storage_identity)
        else:
            conn=sqlite3.connect(self.path,timeout=10,isolation_level=None)
        try:
            conn.row_factory = sqlite3.Row
            if __package__=='web.backend.services':
                from ..research.financial_guard import install_default_hook
            else:
                from research.financial_guard import install_default_hook
            install_default_hook(conn)
            if formal:
                from .auth_registration import install_hook
                install_hook(conn)
            conn.execute("PRAGMA busy_timeout=10000")
            conn.execute("PRAGMA secure_delete=ON")
            if formal:
                conn.execute('PRAGMA foreign_keys=ON')
                if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:
                    raise RuntimeError('private Auth foreign keys unavailable')
            if not bootstrap:
                self.check_gate_policy(conn)
            yield conn
        finally:
            conn.close()

    def record_rate_request(self, email: str, limit: int, window_seconds: int = 3600) -> bool:
        _require_private_rate_bucket(email)
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM auth_rate_requests WHERE requested_at < ?", (now - window_seconds,))
            count = conn.execute(
                "SELECT COUNT(*) FROM auth_rate_requests WHERE email=? AND requested_at>=?",
                (email, now - window_seconds),
            ).fetchone()[0]
            if count >= limit:
                conn.rollback()
                return False
            conn.execute("INSERT INTO auth_rate_requests VALUES (?, ?)", (email, now))
            conn.commit()
            return True

    def record_rate_requests(
        self, buckets: list[tuple[str, int]], window_seconds: int = 3600,
    ) -> bool:
        """Atomically admit one request against every supplied rate bucket.

        A request is recorded only when all buckets have capacity. This keeps
        the per-address and global mail circuit breakers race-safe across
        multiple workers sharing the SQLite store.
        """
        for key, _limit in buckets:
            _require_private_rate_bucket(key)
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM auth_rate_requests WHERE requested_at < ?",
                (now - window_seconds,),
            )
            for key, limit in buckets:
                count = conn.execute(
                    "SELECT COUNT(*) FROM auth_rate_requests "
                    "WHERE email=? AND requested_at>=?",
                    (key, now - window_seconds),
                ).fetchone()[0]
                if count >= limit:
                    conn.rollback()
                    return False
            conn.executemany(
                "INSERT INTO auth_rate_requests VALUES (?, ?)",
                [(key, now) for key, _limit in buckets],
            )
            conn.commit()
            return True

    def record_rate_requests_with_legacy(
        self,
        buckets: list[tuple[str, tuple[str, ...], int]],
        window_seconds: int = 3600,
    ) -> bool:
        """Admit v2 buckets after atomically upgrading bounded legacy keys."""
        for key, _legacy_keys, _limit in buckets:
            _require_private_rate_bucket(key)
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM auth_rate_requests WHERE requested_at < ?",
                (now - window_seconds,),
            )
            for key, legacy_keys, _limit in buckets:
                for legacy_key in legacy_keys:
                    if legacy_key != key:
                        conn.execute(
                            "UPDATE auth_rate_requests SET email=? WHERE email=?",
                            (key, legacy_key),
                        )
            for key, _legacy_keys, limit in buckets:
                count = conn.execute(
                    "SELECT COUNT(*) FROM auth_rate_requests "
                    "WHERE email=? AND requested_at>=?",
                    (key, now - window_seconds),
                ).fetchone()[0]
                if count >= limit:
                    conn.rollback()
                    return False
            conn.executemany(
                "INSERT INTO auth_rate_requests VALUES (?, ?)",
                [(key, now) for key, _legacy_keys, _limit in buckets],
            )
            conn.commit()
            return True

    def add_token(self, token_hash: str, email: str, created_at: str, expires_at: str, *, request=None) -> None:
        if getattr(self,'_private_auth',False) or _formal_auth_mode():
            from .auth_registration import add_token
            return add_token(self,token_hash,email,created_at,expires_at,request=request)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.require_registration_allowed(conn, email)
            conn.execute(
                "INSERT INTO magic_tokens(token_hash,email,created_at,expires_at) VALUES(?,?,?,?)",
                (token_hash, email, created_at, expires_at),
            )
            conn.commit()

    def consume_token(self, token_hash: str, consumed_at: str) -> tuple[Optional[dict], str]:
        self._require_legacy_mutation()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM magic_tokens WHERE token_hash=?", (token_hash,)).fetchone()
            if not row:
                conn.rollback()
                return None, "invalid"
            if row["consumed_at"]:
                conn.rollback()
                return None, "used"
            updated = conn.execute(
                "UPDATE magic_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL",
                (consumed_at, token_hash),
            ).rowcount
            if updated != 1:
                conn.rollback()
                return None, "used"
            conn.commit()
            return dict(row), "ok"

    def ensure_user_and_notification(self, email: str, tier: str, created_at: str) -> tuple[dict, bool]:
        self._require_legacy_mutation()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.require_registration_allowed(conn, email)
            created = conn.execute(
                "INSERT OR IGNORE INTO auth_users(email,tier,created_at,session_generation) "
                "VALUES(?,?,?,lower(hex(randomblob(16))))",
                (email, tier, created_at),
            ).rowcount == 1
            user = dict(conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone())
            if created:
                conn.execute(
                    "INSERT OR IGNORE INTO auth_notification_outbox(kind,email,created_at) VALUES('new_user',?,?)",
                    (email, created_at),
                )
            conn.commit()
            return user, created

    def ensure_user_from_token(
        self, email: str, tier: str, created_at: str, token_created_at: str,
    ) -> tuple[dict, bool]:
        """Create/login atomically unless the credential predates deletion."""
        self._require_legacy_mutation()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self.require_registration_allowed(conn, email)
            deleted_at = _deletion_epoch_for_email(conn, email)
            if deleted_at and token_created_at <= deleted_at:
                conn.rollback()
                raise DeletedCredentialError("credential predates account deletion")
            created = conn.execute(
                "INSERT OR IGNORE INTO auth_users(email,tier,created_at,session_generation) "
                "VALUES(?,?,?,lower(hex(randomblob(16))))",
                (email, tier, created_at),
            ).rowcount == 1
            user = dict(conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone())
            if created:
                conn.execute(
                    "INSERT OR IGNORE INTO auth_notification_outbox(kind,email,created_at) "
                    "VALUES('new_user',?,?)", (email, created_at),
                )
            conn.commit()
            return user, created

    def user(self, email: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def owner_key(email: str) -> str:
        return opaque_identifier("account-owner.gate", email, kind="email")

    @staticmethod
    def check_gate_policy(conn, *, initialize=False):
        fingerprint = opaque_identifier("account-owner.policy", "single-host-gate-v1", kind="opaque")
        rows = conn.execute("SELECT id,fingerprint FROM auth_owner_gate_policy").fetchall()
        if not rows and initialize:
            if conn.execute("SELECT 1 FROM auth_owner_gates LIMIT 1").fetchone():
                raise RuntimeError("account owner gate policy is missing")
            conn.execute("INSERT INTO auth_owner_gate_policy VALUES(1,?)", (fingerprint,))
        elif (len(rows)!=1 or type(rows[0]["id"]) is not int or rows[0]["id"]!=1
              or rows[0]["fingerprint"] != fingerprint):
            raise RuntimeError("account owner gate configuration mismatch")

    @classmethod
    def require_registration_allowed(cls, conn, email):
        pending = conn.execute("SELECT 1 FROM auth_deletion_jobs WHERE owner_key=? AND state!='completed'", (cls.owner_key(email),)).fetchone()
        user = conn.execute("SELECT lifecycle FROM auth_users WHERE email=?", (email,)).fetchone()
        if pending is not None or (user is not None and user["lifecycle"] != "active"):
            raise DeletedCredentialError("account deletion is pending")

    @classmethod
    def owner_gate_in(cls, conn, email: str, preferred: str | None = None) -> str:
        # The direct Research principal/deletion callers must not bypass the
        # existing-only formal owner_gate_id path, including after downgrade.
        import sys
        from .sqlite_utils import PrivateAuthConnection
        native_types=(PrivateAuthConnection,)+tuple(candidate for name in
            ('services.sqlite_utils','web.backend.services.sqlite_utils')
            if (module:=sys.modules.get(name)) is not None
            and isinstance(candidate:=getattr(module,'PrivateAuthConnection',None),type) and candidate is not PrivateAuthConnection)
        private_native=isinstance(conn,native_types)
        if _formal_auth_mode() or private_native:
            from .runtime_paths import PrivateAuthFile,private_auth_path,RuntimePathError
            if not private_native or not conn.in_transaction:
                raise RuntimePathError('private owner mapping requires an active native transaction')
            path=private_auth_path()
            database=next((row[2] for row in conn.execute('PRAGMA database_list') if row[1]=='main'),None)
            if database is None or Path(database)!=path:
                raise RuntimePathError('private owner mapping database differs')
            witness=PrivateAuthFile.acquire(path)
            try:
                if witness.file_identity!=conn.private_storage_identity:
                    raise RuntimePathError('private owner mapping identity differs')
                cls.check_gate_policy(conn,initialize=False)
                row=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(cls.owner_key(email),)).fetchone()
                if row is None or type(row['gate_id']) is not str:
                    raise RuntimePathError('private owner gate mapping is not provisioned')
                try:canonical=str(uuid.UUID(row['gate_id'],version=4))
                except ValueError:raise RuntimePathError('private owner gate identifier is invalid') from None
                if canonical!=row['gate_id']:raise RuntimePathError('private owner gate identifier is invalid')
                witness.check()
                return canonical
            finally:witness.close()
        key = cls.owner_key(email)
        row = conn.execute("SELECT gate_id FROM auth_owner_gates WHERE owner_key=?", (key,)).fetchone()
        if row is not None:
            return row["gate_id"]
        # Preserve already-created research lock inodes during the v1 upgrade.
        has_principals = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_principals'").fetchone()
        if preferred is None and has_principals:
            principal = conn.execute("SELECT id FROM research_principals WHERE normalized_email=? ORDER BY created_at,id LIMIT 1", (email,)).fetchone()
            preferred = principal["id"] if principal else None
        gate_id = preferred or str(uuid.uuid4())
        conn.execute("INSERT INTO auth_owner_gates VALUES(?,?)", (key, gate_id))
        return gate_id

    def owner_gate_id(self, email: str) -> str:
        current=_formal_auth_mode();captured=getattr(self,'_private_auth',False)
        if current and not captured:raise RuntimeError('development Auth cannot become private')
        if captured:
            from .sqlite_utils import connect_private_auth
            from .runtime_paths import private_auth_path,RuntimePathError
            if self.path!=private_auth_path() or self.storage_identity is None:
                raise RuntimePathError('private owner gate has no captured Auth identity')
            conn=connect_private_auth(self.path,readonly=True,expected_identity=self.storage_identity)
            try:
                conn.execute('BEGIN');self.check_gate_policy(conn,initialize=False)
                row=conn.execute('SELECT gate_id FROM auth_owner_gates WHERE owner_key=?',(self.owner_key(email.strip().lower()),)).fetchone()
                if row is None or type(row['gate_id']) is not str:
                    raise RuntimePathError('private owner gate mapping is not provisioned')
                try:canonical=str(uuid.UUID(row['gate_id'],version=4))
                except ValueError:raise RuntimePathError('private owner gate identifier is invalid') from None
                if canonical!=row['gate_id']:raise RuntimePathError('private owner gate identifier is invalid')
                return canonical
            finally:conn.close()
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            result = self.owner_gate_in(conn, email.strip().lower())
            conn.commit()
            return result

    def deletion_pending(self, email: str) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM auth_deletion_jobs WHERE owner_key=? AND state!='completed'", (self.owner_key(email),)).fetchone() is not None

    def account_deletion_epoch(self, email: str) -> Optional[str]:
        """Return the retained owner-hash epoch without exposing raw identity."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            deleted_at = _deletion_epoch_for_email(conn, email)
            conn.commit()
            return deleted_at

    def export_account_data(self, email: str) -> dict:
        """Return every auth-store row linked to ``email``, excluding hashes."""
        if getattr(self,'_private_auth',False) or _formal_auth_mode():
            with self._connection() as conn:
                conn.execute('BEGIN')
                user=conn.execute('SELECT * FROM auth_users WHERE email=?',(email,)).fetchone()
                if not user:return {'account':None,'registration_events':[]}
                events=conn.execute('SELECT kind,state,created_at,updated_at,closed_reason FROM auth_registration_operations WHERE owner_key=? AND target_generation=? ORDER BY created_at,id',
                    (self.owner_key(email),user['session_generation'])).fetchall()
                return {'account':{key:user[key] for key in ('email','tier','created_at')},'registration_events':[dict(row) for row in events]}
        with self._connection() as conn:
            user = conn.execute(
                "SELECT email,tier,created_at FROM auth_users WHERE email=?", (email,)
            ).fetchone()
            tokens = conn.execute(
                "SELECT created_at,expires_at,consumed_at FROM magic_tokens "
                "WHERE email=? ORDER BY created_at", (email,)
            ).fetchall()
            notifications = conn.execute(
                "SELECT kind,created_at,attempts,last_error,delivered_at "
                "FROM auth_notification_outbox WHERE email=? ORDER BY id", (email,)
            ).fetchall()
            revocations = conn.execute(
                "SELECT revoked_at FROM revoked_sessions WHERE email=? ORDER BY revoked_at",
                (email,),
            ).fetchall()
            conn.execute("BEGIN IMMEDIATE")
            deletion_epoch = _deletion_epoch_for_email(conn, email)
            conn.commit()
            return {
                "account": dict(user) if user else None,
                "magic_link_events": [dict(row) for row in tokens],
                "registration_notifications": [dict(row) for row in notifications],
                "revoked_session_events": [dict(row) for row in revocations],
                "prior_deletion_security_event": (
                    {"deleted_at": deletion_epoch, "retention": "security"}
                    if deletion_epoch else None
                ),
            }

    def delete_account_data(
        self,
        email: str,
        *,
        rate_keys: tuple[str, ...] = (),
    ) -> dict:
        """Atomically remove all auth rows linked to an account."""
        if getattr(self,'_private_auth',False) or _formal_auth_mode():
            from .auth_registration import delete_account_data
            return delete_account_data(self,email,rate_keys=rate_keys)
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            deleted_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO account_deletion_epochs(owner_hash,deleted_at) VALUES(?,?) "
                "ON CONFLICT(owner_hash) DO UPDATE SET deleted_at=excluded.deleted_at",
                (_email_hash(email), deleted_at),
            )
            counts = {
                "magic_link_events": conn.execute(
                    "DELETE FROM magic_tokens WHERE email=?", (email,)
                ).rowcount,
                "registration_notifications": conn.execute(
                    "DELETE FROM auth_notification_outbox WHERE email=?", (email,)
                ).rowcount,
                "rate_limit_events": conn.execute(
                    "DELETE FROM auth_rate_requests WHERE email IN ("
                    + ",".join("?" for _ in (email, *rate_keys))
                    + ")",
                    (email, *rate_keys),
                ).rowcount,
                "revoked_session_events": conn.execute(
                    "DELETE FROM revoked_sessions WHERE email=?", (email,)
                ).rowcount,
                "account": conn.execute(
                    "DELETE FROM auth_users WHERE email=?", (email,)
                ).rowcount,
                "security_deletion_epoch": "retained without raw email",
            }
            conn.commit()
            return counts

    def revoke(self, jti: str, revoked_at: str, email: Optional[str] = None) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO revoked_sessions(jti,revoked_at,email) VALUES(?,?,?)",
                (jti, revoked_at, email),
            )

    def is_revoked(self, jti: str) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM revoked_sessions WHERE jti=?", (jti,)).fetchone() is not None

    def claim_notifications(self, limit: int = 50) -> list[dict]:
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM auth_notification_outbox WHERE delivered_at IS NULL "
                "AND (claimed_at IS NULL OR claimed_at<?) ORDER BY id LIMIT ?",
                (now - 300, limit),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                marks = ",".join("?" for _ in ids)
                conn.execute(
                    f"UPDATE auth_notification_outbox SET claimed_at=? WHERE id IN ({marks})",
                    (now, *ids),
                )
            conn.commit()
            return [dict(row) for row in rows]

    def pending_notification_count(self) -> int:
        with self._connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM auth_notification_outbox WHERE delivered_at IS NULL"
            ).fetchone()[0]

    def mark_notification(self, item_id: int, *, delivered_at: Optional[str], error: Optional[str]) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE auth_notification_outbox SET attempts=attempts+1,last_error=?,delivered_at=?,claimed_at=NULL WHERE id=?",
                (error, delivered_at, item_id),
            )


def _email_hash(email: str) -> str:
    return opaque_identifier("account-deletion.email", email, kind="email")


def _legacy_email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _deletion_epoch_for_email(
    conn: sqlite3.Connection,
    email: str,
) -> Optional[str]:
    """Read v2/legacy epochs and opportunistically collapse them into v2."""
    current = _email_hash(email)
    legacy = _legacy_email_hash(email)
    rows = conn.execute(
        "SELECT owner_hash,deleted_at FROM account_deletion_epochs "
        "WHERE owner_hash IN (?,?)",
        (current, legacy),
    ).fetchall()
    if not rows:
        return None
    deleted_at = max(str(row["deleted_at"]) for row in rows)
    conn.execute(
        "INSERT INTO account_deletion_epochs(owner_hash,deleted_at) VALUES(?,?) "
        "ON CONFLICT(owner_hash) DO UPDATE SET deleted_at=excluded.deleted_at",
        (current, deleted_at),
    )
    if legacy != current:
        conn.execute(
            "DELETE FROM account_deletion_epochs WHERE owner_hash=?",
            (legacy,),
        )
    return deleted_at
