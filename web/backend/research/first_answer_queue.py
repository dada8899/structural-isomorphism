"""Private, revision-bound local first-answer queue, with no credential or text copy."""
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import json
import os
import sqlite3
import stat
import sys
import threading
import unicodedata
from uuid import uuid4

from .errors import ResearchError, not_found
from .first_answer import _DIGEST, _revision_digest
from .service import digest, now

TABLE = "research_first_answer_jobs"
CONTRACT = "first-answer-job-v1"
LOCK_NAME = "research-first-answer-queue.lock"
_COLUMNS = ("id", "research_id", "principal_id", "input_revision", "problem_digest", "research_version",
            "owner_epoch", "acl_epoch", "state", "created_at", "updated_at", "fence", "reason", "result_id", "clarification")
_WRITES = {}
_FACTORY = object()
_FAILURES = frozenset(("interrupted", "unavailable", "insufficient", "needs_clarification", "invalid_answer"))
_FDS = set()
_FDS_LOCK = threading.RLock()


def _close_inherited_fds():
    try:
        for fd in _FDS:
            os.close(fd)
        _FDS.clear()
    finally:
        _FDS_LOCK.release()


os.register_at_fork(before=_FDS_LOCK.acquire, after_in_parent=_FDS_LOCK.release, after_in_child=_close_inherited_fds)


def _sql_row(prefix):
    return "json_array(" + ",".join(prefix + "." + name for name in _COLUMNS) + ")"


_IMMUTABLE = " OR ".join("OLD." + name + " IS NOT NEW." + name for name in (*_COLUMNS[:8], "created_at"))
DDL = (
    """CREATE TABLE research_first_answer_jobs (
        id TEXT NOT NULL PRIMARY KEY,
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        input_revision INTEGER NOT NULL CHECK(input_revision BETWEEN 1 AND 2147483647),
        problem_digest TEXT NOT NULL CHECK(length(problem_digest)=64 AND problem_digest NOT GLOB '*[^a-f0-9]*'),
        research_version INTEGER NOT NULL CHECK(research_version BETWEEN 1 AND 2147483647),
        owner_epoch INTEGER NOT NULL CHECK(owner_epoch>=1),
        acl_epoch INTEGER NOT NULL CHECK(acl_epoch>=1),
        state TEXT NOT NULL CHECK(state IN ('queued','running','failed','completed','cancelled')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        fence TEXT UNIQUE,
        reason TEXT,
        result_id TEXT UNIQUE REFERENCES research_first_answers(id),
        clarification TEXT,
        FOREIGN KEY(research_id,input_revision) REFERENCES research_revisions(research_id,revision),
        UNIQUE(research_id,input_revision),
        CHECK((state='queued' AND fence IS NULL AND reason IS NULL AND result_id IS NULL)
           OR (state='running' AND fence IS NOT NULL AND length(fence)=36 AND reason IS NULL AND result_id IS NULL)
           OR (state='completed' AND fence IS NULL AND reason IS NULL AND result_id IS NOT NULL)
           OR (state='failed' AND fence IS NULL AND reason IS NOT NULL AND
               reason IN ('interrupted','unavailable','insufficient','needs_clarification','invalid_answer') AND result_id IS NULL)
           OR (state='cancelled' AND fence IS NULL AND reason IS NOT NULL AND
               reason IN ('owner_cancelled','revision_changed','authorization_changed') AND result_id IS NULL)),
        CHECK((state='failed' AND reason='needs_clarification' AND clarification IS NOT NULL
               AND length(clarification) BETWEEN 1 AND 240)
           OR ((reason IS NULL OR reason!='needs_clarification') AND clarification IS NULL)))""",
    "CREATE UNIQUE INDEX research_first_answer_single_running ON research_first_answer_jobs(state) WHERE state='running'",
    "CREATE INDEX research_first_answer_job_owner ON research_first_answer_jobs(principal_id,state)",
    "CREATE TRIGGER research_first_answer_job_insert BEFORE INSERT ON research_first_answer_jobs "
    "WHEN NEW.state NOT IN ('queued','completed') OR EXISTS(SELECT 1 FROM research_first_answer_jobs prior "
    "WHERE prior.rowid=NEW.rowid OR prior.id=NEW.id OR (prior.research_id=NEW.research_id AND prior.input_revision=NEW.input_revision)) "
    "OR research_first_answer_job_allowed('INSERT',NULL," + _sql_row("NEW") + ")!=1 "
    "BEGIN SELECT RAISE(ABORT,'first-answer job insert unavailable'); END",
    "CREATE TRIGGER research_first_answer_job_update BEFORE UPDATE ON research_first_answer_jobs WHEN " + _IMMUTABLE +
    " OR NOT ((OLD.state='queued' AND NEW.state IN ('running','cancelled')) OR "
    "(OLD.state='running' AND NEW.state IN ('failed','completed','cancelled'))) OR "
    "research_first_answer_job_allowed('UPDATE'," + _sql_row("OLD") + "," + _sql_row("NEW") + ")!=1 "
    "BEGIN SELECT RAISE(ABORT,'first-answer job transition unavailable'); END",
    "CREATE TRIGGER research_first_answer_job_delete BEFORE DELETE ON research_first_answer_jobs "
    "WHEN research_first_answer_job_allowed('DELETE'," + _sql_row("OLD") + ",NULL)!=1 "
    "BEGIN SELECT RAISE(ABORT,'first-answer job deletion unavailable'); END",
)


def install_hook(conn):
    pid = os.getpid()

    def allowed(operation, old, new):
        permit = _WRITES.get(id(conn))
        if not permit or permit[0] is not conn or pid != os.getpid() or not conn.in_transaction or not permit[1].active:
            return 0
        try:
            permit[5].identity
            return int((operation, tuple(json.loads(old)) if old is not None else None,
                        tuple(json.loads(new)) if new is not None else None) == permit[2:5])
        except (TypeError, ValueError, PermissionError, OSError):
            return 0

    conn.create_function("research_first_answer_job_allowed", 3, allowed)
    conn.create_function("research_first_answer_job_guard_version", 0, lambda: 1 if pid == os.getpid() else 0)


def require_hook(conn):
    try:
        row = conn.execute("SELECT research_first_answer_job_guard_version(),research_first_answer_job_allowed('',NULL,NULL)").fetchone()
    except sqlite3.Error:
        raise ResearchError("SCHEMA_UNSUPPORTED", 503, "初步分析队列守卫不可用。") from None
    if tuple(row) != (1, 0):
        raise ResearchError("SCHEMA_UNSUPPORTED", 503, "初步分析队列守卫不匹配。")


def statement_allowed(conn, action, table, column):
    if table != TABLE or action not in (sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE):
        return True
    permit = _WRITES.get(id(conn))
    return bool(permit and permit[0] is conn and permit[1].active and conn.in_transaction)


@contextmanager
def _write(conn, service, lease, op, old, new):
    from .paid_control import _local_answer_scope, _owner_binding
    frame = sys._getframe(2)
    try:
        if (frame.f_code not in _PRODUCERS or frame.f_globals is not globals()
                or frame.f_locals.get("conn") is not conn or frame.f_locals.get("service") is not service
                or frame.f_locals.get("lease") is not lease):
            raise PermissionError("first-answer job producer unavailable")
    finally:
        del frame
    _owner_binding(conn, service.store, (new or old)[2], lease)
    scope = _local_answer_scope(conn)
    if id(conn) in _WRITES:
        raise PermissionError("nested first-answer job writer")
    _WRITES[id(conn)] = (conn, scope, op, old, new, lease)
    scope.refresh_authorizer()
    try:
        yield
    finally:
        _WRITES.pop(id(conn), None)
        scope.refresh_authorizer()


def _values(row):
    return tuple(row[name] for name in _COLUMNS)


def _row(conn, rid, revision, pid):
    return conn.execute("SELECT * FROM research_first_answer_jobs WHERE research_id=? AND input_revision=? AND principal_id=?",
                        (rid, revision, pid)).fetchone()


def _conflict():
    return ResearchError("REVISION_CONFLICT", 409, "问题已有变化，请重新读取。")


def _binding(revision, problem_digest, version):
    if (type(revision) is not int or not 1 <= revision <= 2147483647
            or type(version) is not int or not 1 <= version <= 2147483647
            or type(problem_digest) is not str or not _DIGEST.fullmatch(problem_digest)):
        raise ResearchError("INPUT_INVALID", 422, "初步分析修订或参数无效。")


def _view(conn, job):
    if _revision_digest(conn, job["research_id"], job["input_revision"]) != job["problem_digest"]:
        raise not_found()
    if job["state"] == "completed":
        answer = conn.execute("SELECT research_id,principal_id,input_revision,problem_digest,research_version "
                              "FROM research_first_answers WHERE id=?", (job["result_id"],)).fetchone()
        if not answer or tuple(answer) != tuple(job[name] for name in _COLUMNS[1:6]):
            raise not_found()
    result = {"contract_revision": CONTRACT, "status": job["state"], "metadata": {
        "job_id": job["id"], **{name: job[name] for name in
        ("research_id", "input_revision", "problem_digest", "research_version", "created_at", "updated_at")}}}
    if job["reason"] is not None:
        result["reason"] = job["reason"]
    if job["result_id"] is not None:
        result["result_id"] = job["result_id"]
    if job["clarification"] is not None:
        result["question"] = _clarification(conn, job, job["clarification"])
    return result


def _transition(conn, service, lease, job, state, *, fence=None, reason=None, result_id=None, clarification=None):
    updated = dict(job) | {"state": state, "updated_at": now(), "fence": fence, "reason": reason,
                           "result_id": result_id, "clarification": clarification}
    with _write(conn, service, lease, "UPDATE", _values(job), _values(updated)):
        changed = conn.execute("UPDATE research_first_answer_jobs SET state=?,updated_at=?,fence=?,reason=?,result_id=?,clarification=? "
                               "WHERE id=? AND state=? AND fence IS ?",
                               (state, updated["updated_at"], fence, reason, result_id, clarification, job["id"], job["state"], job["fence"])).rowcount
    if changed != 1:
        raise _conflict()
    return updated


def _require_queue_schema(conn):
    # Both exact catalogs include the same local queue tables and hooks.
    # External ledger capability is checked independently of this queue.
    row = conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()
    if row is None or row[0] not in (16,17):
        raise ResearchError("FEATURE_UNAVAILABLE",503,"当前版本尚不能使用本地分析队列。")


def enqueue(service, identity, rid, *, input_revision, problem_digest, research_version):
    _binding(input_revision, problem_digest, research_version)
    rid, pid = service._id(rid), service._principal(identity)
    with service.authorization.owner_gate(pid) as lease, service.store.transaction(write=True) as conn:
        control = service.authorization.check(conn, identity, pid, rid, scope="write")
        _require_queue_schema(conn)
        existing = _row(conn, rid, input_revision, pid)
        if existing:
            if (existing["problem_digest"], existing["research_version"]) != (problem_digest, research_version):
                raise _conflict()
            return _view(conn, existing)
        if ((control["current_revision"], control["version"]) != (input_revision, research_version)
                or _revision_digest(conn, rid, input_revision) != problem_digest):
            raise _conflict()
        answer = conn.execute("SELECT id,problem_digest,research_version FROM research_first_answers "
                              "WHERE research_id=? AND principal_id=? AND input_revision=?", (rid, pid, input_revision)).fetchone()
        if answer is not None and (answer["problem_digest"], answer["research_version"]) != (problem_digest, research_version):
            raise _conflict()
        if answer is None:
            count = conn.execute("SELECT count(*),coalesce(sum(principal_id=?),0) FROM research_first_answer_jobs "
                                 "WHERE state IN ('queued','running')", (pid,)).fetchone()
            if count[0] >= 32 or count[1] >= 2:
                raise ResearchError("QUEUE_BUSY", 429, "初步分析当前排队较多，请稍后再试。", retryable=True)
        at = now()
        values = (str(uuid4()), rid, pid, input_revision, problem_digest, research_version, control["owner_epoch"],
                  control["acl_epoch"], "completed" if answer else "queued", at, at, None, None, answer["id"] if answer else None, None)
        with _write(conn, service, lease, "INSERT", None, values):
            conn.execute("INSERT INTO research_first_answer_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
        return _view(conn, dict(zip(_COLUMNS, values)))


def read(service, identity, rid, input_revision):
    rid = service._id(rid)
    if type(input_revision) is not int or not 1 <= input_revision <= 2147483647:
        raise not_found()
    with service.store.transaction() as conn:
        pid = service._principal_in(conn, identity)
        service.authorization.check(conn, identity, pid, rid)
        _require_queue_schema(conn)
        job = _row(conn, rid, input_revision, pid)
        if not job:
            raise not_found()
        return _view(conn, job)


def cancel(service, identity, rid, *, input_revision, problem_digest, research_version, job_id):
    _binding(input_revision, problem_digest, research_version)
    service._id(job_id)
    rid, pid = service._id(rid), service._principal(identity)
    with service.authorization.owner_gate(pid) as lease, service.store.transaction(write=True) as conn:
        service.authorization.check(conn, identity, pid, rid, scope="write")
        _require_queue_schema(conn)
        job = _row(conn, rid, input_revision, pid)
        if not job or job["id"] != job_id:
            raise not_found()
        if (job["problem_digest"], job["research_version"]) != (problem_digest, research_version):
            raise _conflict()
        if job["state"] in ("queued", "running"):
            job = _transition(conn, service, lease, job, "cancelled", reason="owner_cancelled")
        return _view(conn, job)


def _current(conn, job):
    binding = conn.execute("""SELECT c.* FROM research_controls c JOIN research_principals p ON p.id=c.owner_id
        JOIN auth_users u ON u.email=p.normalized_email
        WHERE c.id=? AND c.owner_id=? AND c.owner_epoch=? AND c.acl_epoch=? AND c.lifecycle='active'
          AND p.epoch=c.owner_epoch AND p.status='active' AND u.lifecycle='active'
          AND u.session_generation=p.session_generation
          AND EXISTS (SELECT 1 FROM research_grants g, json_each(g.scopes) scope WHERE g.research_id=c.id
              AND g.principal_id=p.id AND g.principal_epoch=p.epoch AND g.acl_epoch=c.acl_epoch
              AND g.status='active' AND scope.value='write')""",
        (job["research_id"], job["principal_id"], job["owner_epoch"], job["acl_epoch"])).fetchone()
    if not binding:
        return None, "authorization_changed"
    if (binding["current_revision"], binding["version"]) != (job["input_revision"], job["research_version"]):
        return None, "revision_changed"
    try:
        if _revision_digest(conn, job["research_id"], job["input_revision"]) != job["problem_digest"]:
            return None, "revision_changed"
    except ResearchError as error:
        if error.code != "NOT_FOUND":
            raise
        return None, "revision_changed"
    return binding, None


def _clarification(conn, job, question):
    from .local_first_answer_contract import _model_text
    if type(question) is not str or not 1 <= len(question) <= 240:
        raise ResearchError("INPUT_INVALID", 422, "追问内容无效。")
    try:
        question = _model_text(question)
        source = conn.execute("SELECT problem_json FROM research_revisions WHERE research_id=? AND revision=?",
                              (job["research_id"], job["input_revision"])).fetchone()
        original = json.loads(source["problem_json"])["original_input"]
        def comparison(value):
            return "".join(character for character in unicodedata.normalize("NFKC", value).casefold()
                           if not character.isspace() and not unicodedata.category(character).startswith("P"))
        if not comparison(question) or comparison(question) == comparison(original):
            raise ValueError()
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ResearchError("INPUT_INVALID", 422, "追问内容无效。") from None
    return question


@dataclass(frozen=True, slots=True, repr=False)
class Claim:
    id: str
    principal_id: str
    fence: str
    research_id: str
    input_revision: int
    problem_digest: str
    research_version: int


def _lock_identity(entry):
    if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != os.geteuid()
            or stat.S_IMODE(entry.st_mode) != 0o600 or entry.st_nlink != 1):
        raise PermissionError("unsafe first-answer queue lock")
    return entry.st_dev, entry.st_ino


class Worker:
    """One in-process claim atop an actual cross-process exclusive lock."""

    def __init__(self, service, fd, path, *, factory):
        if factory is not _FACTORY:
            raise PermissionError("actual worker lease required")
        self.service, self._fd, self._path = service, fd, path
        self._pid = os.getpid()
        self._identity = _lock_identity(os.fstat(fd))
        self._claim = None
        self._mutex = threading.RLock()
        self._active = True

    def _require(self):
        if (not self._active or self._pid != os.getpid() or _lock_identity(os.fstat(self._fd)) != self._identity
                or _lock_identity(os.lstat(self._path)) != self._identity):
            raise PermissionError("worker lease expired")

    def _reconcile(self):
        self._require()
        service = self.service
        with service.store.transaction() as conn:
            _require_queue_schema(conn)
            old = conn.execute("SELECT id,principal_id FROM research_first_answer_jobs WHERE state='running'").fetchone()
        if old:
            with service.authorization.owner_gate(old["principal_id"]) as lease, service.store.transaction(write=True) as conn:
                job = conn.execute("SELECT * FROM research_first_answer_jobs WHERE id=?", (old["id"],)).fetchone()
                if job and job["state"] == "running":
                    _transition(conn, service, lease, job, "failed", reason="interrupted")

    def claim_next(self):
        """Take the next unsent job; only now read original input into memory."""
        with self._mutex:
            self._require()
            if self._claim is not None:
                raise PermissionError("local answer claim already active")
            service = self.service
            # Do not monopolize the runner when a block of stale entries is seen.
            for _ in range(32):
                with service.store.transaction() as conn:
                    _require_queue_schema(conn)
                    candidate = conn.execute("SELECT id,principal_id FROM research_first_answer_jobs "
                                             "WHERE state='queued' ORDER BY rowid LIMIT 1").fetchone()
                if not candidate:
                    return None
                try:
                    with service.authorization.owner_gate(candidate["principal_id"]) as lease, service.store.transaction(write=True) as conn:
                        job = conn.execute("SELECT * FROM research_first_answer_jobs WHERE id=?", (candidate["id"],)).fetchone()
                        if not job or job["state"] != "queued":
                            continue
                        control, reason = _current(conn, job)
                        if control is None:
                            _transition(conn, service, lease, job, "cancelled", reason=reason)
                            continue
                        source = conn.execute("SELECT problem_json FROM research_revisions WHERE research_id=? AND revision=?",
                                              (job["research_id"], job["input_revision"])).fetchone()
                        question = json.loads(source["problem_json"])["original_input"]
                        if type(question) is not str:
                            _transition(conn, service, lease, job, "cancelled", reason="revision_changed")
                            continue
                        fence = str(uuid4())
                        _transition(conn, service, lease, job, "running", fence=fence)
                        claim = Claim(job["id"], job["principal_id"], fence, job["research_id"], job["input_revision"],
                                      job["problem_digest"], job["research_version"])
                    self._claim = claim
                    return claim, question
                except ResearchError as error:
                    if error.code != "NOT_FOUND":
                        raise
            return None

    def _owned(self, claim):
        self._require()
        if type(claim) is not Claim or self._claim is not claim:
            raise PermissionError("local answer claim unavailable")

    def _claimed_row(self, conn, claim):
        return conn.execute("SELECT * FROM research_first_answer_jobs WHERE id=? AND principal_id=? "
                            "AND state='running' AND fence=?", (claim.id, claim.principal_id, claim.fence)).fetchone()

    def is_current(self, claim):
        """Cancellation probe; no auth/session material or question returned."""
        with self._mutex:
            self._owned(claim)
            with self.service.store.transaction() as conn:
                job = self._claimed_row(conn, claim)
                return bool(job and _current(conn, job)[0] is not None)

    def finish(self, claim, *, answer=None, reason=None, question=None):
        """Atomically store the answer and retire the fenced claim, or fail safely."""
        if ((answer is None) == (reason is None)
                or (reason is not None and (type(reason) is not str or reason not in _FAILURES - {"interrupted"}))
                or ((reason == "needs_clarification") != (question is not None))):
            raise ValueError("exactly one validated answer or bounded failure reason required")
        with self._mutex:
            self._owned(claim)
            service = self.service
            outcome = None
            try:
                with service.authorization.owner_gate(claim.principal_id) as lease, service.store.transaction(write=True) as conn:
                    job = self._claimed_row(conn, claim)
                    if job:
                        control, cancelled = _current(conn, job)
                        if control is None:
                            job = _transition(conn, service, lease, job, "cancelled", reason=cancelled)
                        elif answer is None:
                            clarification = _clarification(conn, job, question) if question is not None else None
                            job = _transition(conn, service, lease, job, "failed", reason=reason, clarification=clarification)
                        else:
                            from .first_answer import _write_queued_result
                            result = _write_queued_result(conn, service, lease, self, claim, answer)
                            job = _transition(conn, service, lease, job, "completed", result_id=result)
                        outcome = _view(conn, job)
            except ResearchError as error:
                if error.code != "NOT_FOUND":
                    # Keep the active fence; an owner may retry the database
                    # commit with the same result, never redo inference.
                    raise
            self._claim = None
            return outcome


@contextmanager
def worker_session(service):
    """Admit one local runner and reconcile previously sent/unknown work."""
    from .service import ResearchService
    from .store import ResearchStore
    if type(service) is not ResearchService or type(service.store) is not ResearchStore:
        raise PermissionError("canonical research service required")
    path = service.store.path.parent / LOCK_NAME
    origin_pid = os.getpid()
    with _FDS_LOCK:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        _FDS.add(fd)
    worker = None
    try:
        _lock_identity(os.fstat(fd))
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = Worker(service, fd, path, factory=_FACTORY)
        worker._reconcile()
        yield worker
    finally:
        if os.getpid() == origin_pid:
            if worker is not None:
                with worker._mutex:
                    worker._active = False
                    worker._claim = None
            with _FDS_LOCK:
                _FDS.remove(fd)
                os.close(fd)


def erase_in(conn, service, lease, pid, job_id):
    from .paid_control import verify_deletion_origin
    job = verify_deletion_origin(conn, store=service.store, lease=lease, job_id=job_id)
    principal = conn.execute("SELECT * FROM research_principals WHERE id=?", (pid,)).fetchone()
    if (not job or job["state"] != "pending" or not principal or principal["status"] != "deleting"
            or principal["normalized_email"] != job["owner_email"]
            or principal["session_generation"] != job["session_generation"]):
        raise PermissionError("first-answer job deletion owner mismatch")
    rows = conn.execute("SELECT * FROM research_first_answer_jobs WHERE principal_id=?", (pid,)).fetchall()
    for row in rows:
        with _write(conn, service, lease, "DELETE", _values(row), None):
            if conn.execute("DELETE FROM research_first_answer_jobs WHERE id=?", (row["id"],)).rowcount != 1:
                raise PermissionError("first-answer job deletion compare failed")
    return len(rows)


_LOCAL_WRITE_CODE = _write.__wrapped__.__code__

_PRODUCERS = {function.__code__ for function in (enqueue, _transition, erase_in)}
