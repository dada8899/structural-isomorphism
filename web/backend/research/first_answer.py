"""Versioned, private first-answer snapshots (not yet admitted in schema 15).

A server producer supplies an already-computed candidate. This module neither
reads providers nor turns model output into permission to perform an action.
The migration/admission layer must explicitly adopt DDL before exposing routes.
"""
from datetime import datetime
import hashlib
import json
import re
from typing import Annotated
from uuid import uuid4

from pydantic import Field, StringConstraints, ValidationError, field_validator

from .errors import ResearchError, not_found
from .schemas import StrictObject, bounded_text
from .service import canonical, digest, now

REQUIRED_SCHEMA_VERSION = 16
CONTRACT = "first-answer-v1"
TABLE = "research_first_answers"
MAX_BODY_BYTES = 32768
_DIGEST = re.compile(r"[a-f0-9]{64}")
_KEY = re.compile(r"[A-Za-z0-9_-]{1,128}")

DDL = (
    """CREATE TABLE research_first_answers (
        id TEXT NOT NULL PRIMARY KEY,
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        input_revision INTEGER NOT NULL CHECK(input_revision BETWEEN 1 AND 2147483647),
        problem_digest TEXT NOT NULL CHECK(length(problem_digest)=64 AND problem_digest NOT GLOB '*[^a-f0-9]*'),
        research_version INTEGER NOT NULL CHECK(research_version BETWEEN 1 AND 2147483647),
        key_digest TEXT NOT NULL CHECK(length(key_digest)=64 AND key_digest NOT GLOB '*[^a-f0-9]*'),
        content_digest TEXT NOT NULL CHECK(length(content_digest)=64 AND content_digest NOT GLOB '*[^a-f0-9]*'),
        created_at TEXT NOT NULL,
        body_json TEXT NOT NULL CHECK(json_valid(body_json) AND json_type(body_json)='object' AND length(CAST(body_json AS BLOB))<=32768),
        FOREIGN KEY(research_id,input_revision) REFERENCES research_revisions(research_id,revision),
        UNIQUE(research_id,input_revision),
        UNIQUE(principal_id,research_id,key_digest))""",
    """CREATE TRIGGER research_first_answer_immutable BEFORE UPDATE ON research_first_answers
        BEGIN SELECT RAISE(ABORT,'immutable first answer'); END""",
    """CREATE TRIGGER research_first_answer_no_replace BEFORE INSERT ON research_first_answers
        WHEN EXISTS(SELECT 1 FROM research_first_answers AS prior
            WHERE prior.rowid=NEW.rowid OR prior.id=NEW.id
              OR (prior.research_id=NEW.research_id AND (prior.input_revision=NEW.input_revision
                   OR (prior.principal_id=NEW.principal_id AND prior.key_digest=NEW.key_digest))))
        BEGIN SELECT RAISE(ABORT,'first answer replacement forbidden'); END""",
    """CREATE TRIGGER research_first_answer_current_binding BEFORE INSERT ON research_first_answers
        WHEN NOT EXISTS(SELECT 1 FROM research_controls AS c JOIN research_revisions AS r ON r.research_id=c.id
            JOIN research_principals AS p ON p.id=c.owner_id
            WHERE c.id=NEW.research_id AND c.owner_id=NEW.principal_id
              AND p.status='active' AND p.epoch=c.owner_epoch AND c.lifecycle='active'
              AND c.current_revision=NEW.input_revision AND c.version=NEW.research_version
              AND r.revision=NEW.input_revision AND r.digest=NEW.problem_digest)
        BEGIN SELECT RAISE(ABORT,'first answer input binding changed'); END""",
)

Text = Annotated[str, StringConstraints(min_length=1, max_length=1200)]
StableRef = Annotated[str, StringConstraints(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9._:/-]+$")]


class Reference(StrictObject):
    """A producer-owned lookup reference; storage does not certify evidence."""

    artifact: StableRef
    locator: StableRef
    label: Text

    @field_validator("label")
    @classmethod
    def plain_label(cls, value):
        return bounded_text(value, 1200, 1)


class AnswerBody(StrictObject):
    producer: StableRef
    explanation: Text
    assumptions: Annotated[list[Text], Field(max_length=6)]
    cross_domain_leads: Annotated[list[Text], Field(max_length=6)]
    next_check: Text
    references: Annotated[list[Reference], Field(max_length=12)]

    @field_validator("explanation", "next_check")
    @classmethod
    def plain_text(cls, value):
        if not value.strip():
            raise ValueError("nonempty answer required")
        return bounded_text(value, 1200, 1)

    @field_validator("assumptions", "cross_domain_leads")
    @classmethod
    def plain_list(cls, values):
        return [cls.plain_text(value) for value in values]


def _require_schema(conn):
    marker = conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()
    if marker is None or marker[0] != REQUIRED_SCHEMA_VERSION:
        raise ResearchError("FEATURE_UNAVAILABLE", 503, "当前版本尚不能保存初步分析。")


def _revision_digest(conn, rid, revision):
    row = conn.execute(
        "SELECT problem_json,digest FROM research_revisions WHERE research_id=? AND revision=?", (rid, revision)
    ).fetchone()
    if not row:
        raise not_found()
    try:
        if digest(json.loads(row["problem_json"])) != row["digest"]:
            raise ValueError()
    except (TypeError, ValueError, UnicodeError):
        raise not_found() from None
    return row["digest"]


def _view(conn, control, row):
    try:
        content = AnswerBody.model_validate_json(row["body_json"]).model_dump(mode="json")
        if (canonical(content) != row["body_json"] or digest(content) != row["content_digest"]
                or datetime.strptime(row["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime("%Y-%m-%dT%H:%M:%S.%fZ") != row["created_at"]
                or control["version"] < row["research_version"]
                or control["current_revision"] < row["input_revision"]
                or _revision_digest(conn, row["research_id"], row["input_revision"]) != row["problem_digest"]):
            raise ValueError()
    except (ValueError, TypeError, UnicodeError):
        raise not_found() from None
    metadata = {name: row[name] for name in ("id", "research_id", "input_revision", "problem_digest",
                                             "research_version", "content_digest", "created_at")}
    return {"contract_revision": CONTRACT, "metadata": metadata, "content": content, "status": "provisional",
            "is_historical": row["input_revision"] != control["current_revision"]}


def save(service, identity, rid, *, input_revision, problem_digest, research_version, key, answer):
    """Save the first result for a current revision; never overwrite it."""
    if (type(input_revision) is not int or not 1 <= input_revision <= 2147483647
            or type(research_version) is not int or not 1 <= research_version <= 2147483647
            or type(problem_digest) is not str or not _DIGEST.fullmatch(problem_digest)
            or type(key) is not str or not _KEY.fullmatch(key)
            or type(answer) is not AnswerBody):
        raise ResearchError("INPUT_INVALID", 422, "初步分析输入无效。")
    try:
        content = AnswerBody.model_validate(answer.model_dump(mode="json")).model_dump(mode="json")
        body = canonical(content)
    except (ValidationError, TypeError, ValueError):
        raise ResearchError("INPUT_INVALID", 422, "初步分析内容无效。") from None
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ResearchError("PAYLOAD_LIMIT", 413, "初步分析内容超过保存范围。")
    content_digest, key_digest = digest(content), hashlib.sha256(key.encode()).hexdigest()
    rid, pid = service._id(rid), service._principal(identity)
    with service.authorization.owner_gate(pid) as lease, service.store.transaction(write=True) as conn:
        control = service.authorization.check(conn, identity, pid, rid, scope="write")
        _require_schema(conn)
        existing = conn.execute(
            "SELECT * FROM research_first_answers WHERE principal_id=? AND research_id=? AND key_digest=?",
            (pid, rid, key_digest),
        ).fetchone()
        if existing:
            if (existing["input_revision"], existing["problem_digest"], existing["research_version"], existing["content_digest"]) != (
                    input_revision, problem_digest, research_version, content_digest):
                raise ResearchError("IDEMPOTENCY_CONFLICT", 409, "同一操作标识已用于另一份分析。")
            return _view(conn, control, existing)
        if (control["current_revision"] != input_revision or control["version"] != research_version
                or _revision_digest(conn, rid, input_revision) != problem_digest):
            raise ResearchError("VERSION_CONFLICT", 409, "问题已变化，请先读取当前修订。")
        if conn.execute("SELECT 1 FROM research_first_answers WHERE research_id=? AND input_revision=?", (rid, input_revision)).fetchone():
            raise ResearchError("ANSWER_EXISTS", 409, "当前修订已有初步分析，请读取已保存结果。")
        ref = str(uuid4())
        from .paid_control import _owner_binding
        _owner_binding(conn, service.store, pid, lease)
        conn.execute("""INSERT INTO research_first_answers(id,research_id,principal_id,input_revision,problem_digest,
                         research_version,key_digest,content_digest,created_at,body_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                     (ref, rid, pid, input_revision, problem_digest, research_version, key_digest, content_digest, now(), body))
        row = conn.execute("SELECT * FROM research_first_answers WHERE id=?", (ref,)).fetchone()
        return _view(conn, control, row)


def read(service, identity, rid, revision):
    """Read an authorized exact revision; no computation or provider replay."""
    rid = service._id(rid)
    if type(revision) is not int or not 1 <= revision <= 2147483647:
        raise not_found()
    with service.store.transaction() as conn:
        pid = service._principal_in(conn, identity)
        control = service.authorization.check(conn, identity, pid, rid)
        _require_schema(conn)
        row = conn.execute("""SELECT * FROM research_first_answers
            WHERE principal_id=? AND research_id=? AND input_revision=?""", (pid, rid, revision)).fetchone()
        if not row:
            raise not_found()
        return _view(conn, control, row)
