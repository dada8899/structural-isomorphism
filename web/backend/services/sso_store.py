"""Transactional replay ledger for cross-origin account exchange codes."""
from __future__ import annotations

import sqlite3
import os,re
from functools import lru_cache
import time
from pathlib import Path

from .sqlite_utils import ClosingConnection,connect_private_sso


_SSO_TABLE_DDL = ('CREATE TABLE IF NOT EXISTS consumed_sso_codes(jti TEXT PRIMARY KEY, consumed_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)', 'CREATE TABLE IF NOT EXISTS issued_sso_codes(jti TEXT PRIMARY KEY, subject_id TEXT NOT NULL, tier TEXT NOT NULL, expires_at INTEGER NOT NULL, consumed_at INTEGER, email TEXT, issued_ns INTEGER)', 'CREATE TABLE IF NOT EXISTS revoked_sso_subjects(subject_id TEXT PRIMARY KEY, revoked_at INTEGER NOT NULL)', 'CREATE TABLE IF NOT EXISTS sso_subject_email_bindings(subject_id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, bound_at INTEGER NOT NULL)')
_SSO_ALTER_DDL = ('ALTER TABLE issued_sso_codes ADD COLUMN email TEXT', 'ALTER TABLE issued_sso_codes ADD COLUMN issued_ns INTEGER')


def _formal_sso_mode():
    from .runtime_paths import RuntimePathError
    raw=os.getenv('STRUCTURAL_ENV','dev')
    if raw.strip().lower()=='prod' and raw.lower()!='prod':raise RuntimePathError('private SSO profile contains invalid whitespace')
    return raw.lower()=='prod'


def _sql_tokens(sql):
    # Literal-preserving tokens; normalize only optional IF NOT EXISTS and
    # simple managed SSO object quoting, never flatten string literal content.
    tokens=[]
    managed={ddl.split()[5].split('(')[0] for ddl in _SSO_TABLE_DDL}
    for value in re.findall(r"\s+|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|.",sql,re.S):
        if value.isspace():continue
        if value.startswith("'"):tokens.append(('literal',value))
        elif value[0] in ('"','`','['):
            name=value[1:-1]
            tokens.append(('token',name.lower()) if name.lower() in managed else ('quoted',name))
        else:tokens.append(('token',value.lower()))
    optional=[('token','if'),('token','not'),('token','exists')]
    return tuple(v for i,v in enumerate(tokens) if not any(tokens[j:j+3]==optional and j<=i<j+3 for j in range(max(0,i-2),i+1)))


def _metadata(conn,allowed=None):
    objects={};columns={};indexes={}
    rows=list(conn.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema'))
    for kind,name,target,sql in rows:objects[name]=(kind,target,_sql_tokens(sql) if sql is not None else None)
    if allowed is not None and objects not in [form[0] for form in allowed]:return objects,columns,indexes
    known={ddl.split()[5].split('(')[0] for ddl in _SSO_TABLE_DDL}
    if any(target not in known for _,_,target,_ in rows):return objects,columns,indexes
    for kind,name,target,sql in rows:
        quoted='"'+name.replace('"','""')+'"'
        if kind=='table':
            columns[name]=tuple(tuple(v) for v in conn.execute('PRAGMA main.table_xinfo('+quoted+')'))
        elif kind=='index':
            indexes[name]=tuple(tuple(v) for v in conn.execute('PRAGMA main.index_xinfo('+quoted+')'))
    return objects,columns,indexes


@lru_cache(maxsize=1)
def _final_sso_contracts():
    forms=[]
    # Exactly the constructor's declared creation/ALTER histories, including
    # legacy issued_ns already present when the email ALTER was applied.
    for removed in ((),('email',),('issued_ns',),('email','issued_ns')):
        with sqlite3.connect(':memory:',isolation_level=None,factory=ClosingConnection) as conn:
            for ddl in _SSO_TABLE_DDL:
                if 'issued_sso_codes(' in ddl:
                    if 'email' in removed:ddl=ddl.replace(', email TEXT','')
                    if 'issued_ns' in removed:ddl=ddl.replace(', issued_ns INTEGER','')
                conn.execute(ddl)
            for field,ddl in zip(('email','issued_ns'),_SSO_ALTER_DDL):
                if field in removed:conn.execute(ddl)
            forms.append(_metadata(conn))
    return tuple(forms)


class SsoReplayStore:
    def __init__(self,path:Path):
        self.path=Path(path);self._private_sso=_formal_sso_mode();self._storage_identity=None
        if self._private_sso:
            self._storage_identity=self.preflight_private(self.path)
            return
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self._connect() as conn:
            for ddl in _SSO_TABLE_DDL[:3]:conn.execute(ddl)
            columns={row[1] for row in conn.execute('PRAGMA table_info(issued_sso_codes)')}
            for name,ddl in zip(('email','issued_ns'),_SSO_ALTER_DDL):
                if name not in columns:conn.execute(ddl)
            conn.execute(_SSO_TABLE_DDL[3])

    @property
    def storage_identity(self):return self._storage_identity

    @classmethod
    def preflight_private(cls,path):
        conn=connect_private_sso(path,readonly=True);identity=conn.private_storage_identity
        try:
            conn.execute('BEGIN')
            allowed=_final_sso_contracts()
            if _metadata(conn,allowed=allowed) not in allowed:
                raise RuntimeError('private SSO schema is incomplete or unsupported')
            return identity
        finally:conn.close()

    def _connect(self)->sqlite3.Connection:
        current=_formal_sso_mode()
        if current and not self._private_sso:raise RuntimeError('development SSO object cannot become formal')
        conn=(connect_private_sso(self.path,expected_identity=self.storage_identity)
              if self._private_sso or current else sqlite3.connect(self.path,timeout=10,
                    isolation_level=None,factory=ClosingConnection))
        try:
            conn.execute('PRAGMA busy_timeout=10000')
            if not (self._private_sso or current):conn.execute('PRAGMA journal_mode=WAL')
            return conn
        except BaseException:
            conn.close();raise

    def consume_once(self, jti: str, expires_at: int) -> bool:
        """Atomically consume a non-expired code identifier exactly once."""
        now = int(time.time())
        if not jti or expires_at < now:
            return False
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM consumed_sso_codes WHERE expires_at < ?", (now,))
            inserted = conn.execute(
                "INSERT OR IGNORE INTO consumed_sso_codes(jti,consumed_at,expires_at) "
                "VALUES(?,?,?)", (jti, now, expires_at),
            ).rowcount
            conn.commit()
            return inserted == 1

    def issue(
        self, jti: str, subject_id: str, tier: str, expires_at: int,
        email: str | None = None,
    ) -> None:
        if not jti or not subject_id:
            raise ValueError("jti and subject_id are required")
        issued_ns = time.time_ns()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if email:
                conn.execute(
                    "INSERT INTO sso_subject_email_bindings(subject_id,email,bound_at) "
                    "VALUES(?,?,?) ON CONFLICT(subject_id) DO UPDATE SET "
                    "email=excluded.email,bound_at=excluded.bound_at",
                    (subject_id, email.strip().lower(), time.time_ns()),
                )
            conn.execute(
                "INSERT INTO issued_sso_codes("
                "jti,subject_id,tier,expires_at,email,issued_ns) "
                "VALUES(?,?,?,?,?,?)",
                (
                    jti, subject_id, tier, expires_at,
                    email.strip().lower() if email else None, issued_ns,
                ),
            )
            conn.commit()

    def consume_issued(self, jti: str) -> dict | None:
        now = int(time.time())
        if not jti:
            return None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT subject_id,tier,expires_at,consumed_at,email,issued_ns "
                "FROM issued_sso_codes WHERE jti=?",
                (jti,),
            ).fetchone()
            if not row or row[3] is not None or int(row[2]) < now:
                conn.rollback()
                return None
            updated = conn.execute(
                "UPDATE issued_sso_codes SET consumed_at=? WHERE jti=? AND consumed_at IS NULL",
                (now, jti),
            ).rowcount
            conn.commit()
        return {
            "subject_id": row[0], "tier": row[1], "email": row[4],
            "issued_ns": int(row[5]) if row[5] is not None else None,
        } if updated == 1 else None

    def lookup_issued(self, jti: str) -> dict | None:
        """Read an exchange owner before entering its account transaction."""
        now = int(time.time())
        if not jti:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT subject_id,tier,expires_at,consumed_at,email,issued_ns "
                "FROM issued_sso_codes WHERE jti=?",
                (jti,),
            ).fetchone()
        if not row or row[3] is not None or int(row[2]) < now:
            return None
        return {
            "subject_id": row[0], "tier": row[1], "email": row[4],
            "issued_ns": int(row[5]) if row[5] is not None else None,
        }

    def export_issued_for_subject(self, subject_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT jti,subject_id,tier,expires_at,consumed_at,email,issued_ns "
                "FROM issued_sso_codes WHERE subject_id=? ORDER BY jti",
                (subject_id,),
            ).fetchall()
        columns = (
            "jti", "subject_id", "tier", "expires_at", "consumed_at",
            "email", "issued_ns",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def delete_issued_for_subject(self, subject_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(
                "DELETE FROM issued_sso_codes WHERE subject_id=?", (subject_id,)
            ).rowcount

    def restore_issued(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO issued_sso_codes("
                "jti,subject_id,tier,expires_at,consumed_at,email,issued_ns) "
                "VALUES(?,?,?,?,?,?,?)",
                [
                    (
                        row["jti"], row["subject_id"], row["tier"],
                        row["expires_at"], row.get("consumed_at"),
                        row.get("email"), row.get("issued_ns"),
                    )
                    for row in rows
                ],
            )

    def email_for_subject(self, subject_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email FROM sso_subject_email_bindings WHERE subject_id=?",
                (subject_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def export_subject_binding(self, subject_id: str) -> dict:
        email = self.email_for_subject(subject_id)
        return {"exists": email is not None, "email": email}

    def delete_subject_binding(self, subject_id: str) -> dict:
        snapshot = self.export_subject_binding(subject_id)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM sso_subject_email_bindings WHERE subject_id=?", (subject_id,)
            )
        return snapshot

    def restore_subject_binding(self, subject_id: str, snapshot: dict) -> None:
        email = snapshot.get("email") if snapshot.get("exists") else None
        if not email:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sso_subject_email_bindings(subject_id,email,bound_at) "
                "VALUES(?,?,?)", (subject_id, email, time.time_ns()),
            )

    def revoke_subject(self, subject_id: str, revoked_at: int | None = None) -> int:
        if not subject_id:
            raise ValueError("subject_id is required")
        epoch = time.time_ns() if revoked_at is None else int(revoked_at)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO revoked_sso_subjects(subject_id,revoked_at) VALUES(?,?) "
                "ON CONFLICT(subject_id) DO UPDATE SET revoked_at=MAX(revoked_at,excluded.revoked_at)",
                (subject_id, epoch),
            )
        return epoch

    def subject_revoked_at(self, subject_id: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,)
            ).fetchone()
        return int(row[0]) if row else None

    def restore_subject_revocation(self, subject_id: str, previous: int | None, applied: int) -> None:
        """Compensate only our own epoch; never erase a newer concurrent revoke."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revoked_at FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,)
            ).fetchone()
            if row and int(row[0]) == applied:
                if previous is None:
                    conn.execute("DELETE FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,))
                else:
                    conn.execute(
                        "UPDATE revoked_sso_subjects SET revoked_at=? WHERE subject_id=?",
                        (previous, subject_id),
                    )
            conn.commit()
