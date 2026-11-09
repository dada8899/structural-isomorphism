"""Storage contract with real owner checks and synthetic, isolated schema overlay."""
import sqlite3

import pytest

from web.backend.tests.test_research_persistence import auth, create, login, problem, stack
from research.authorization import AccountIdentity
from research.errors import ResearchError
from research.first_answer import AnswerBody, DDL, read, save
from research.service import ResearchService
from research.store import ResearchStore


def identity(client):
    claims = auth._decode_jwt(client.cookies.get("phase_session"))
    return AccountIdentity(claims["sub"], claims["gen"], claims["jti"], claims["exp"])


def candidate(explanation="在稳定流量附近，波动可能使排队明显增长。"):
    return AnswerBody(
        producer="test-artifact-v1", explanation=explanation,
        assumptions=["单服务台，短时间内服务能力近似不变。"],
        cross_domain_leads=["缓冲区内的积压也可用流入与流出的差描述。"],
        next_check="比较忙时到达间隔与处理时长。",
        references=[{"artifact": "test-catalog-v1", "locator": "queue-01", "label": "排队机制样例"}],
    )


def test_private_answer_snapshot_and_original_retry_across_revisions(stack):
    client, _ = stack
    rid = create(client)
    service = ResearchService(ResearchStore(auth._store()))
    owner = identity(client)
    first = client.get(f"/api/research/{rid}").json()["data"]
    args = dict(input_revision=1, problem_digest=first["current_problem"]["digest"],
                research_version=first["research_version"], key="public-question-one", answer=candidate())

    with pytest.raises(ResearchError) as denied:
        save(service, owner, rid, **args)
    assert denied.value.code == "FEATURE_UNAVAILABLE"

    # Isolated proof of the additive table; production intentionally stays v15.
    with service.store.transaction(write=True) as conn:
        for ddl in DDL:
            conn.execute(ddl)
        conn.execute("UPDATE research_schema SET version=16 WHERE id=1")

    stored = save(service, owner, rid, **args)
    assert stored["status"] == "provisional"
    assert stored == save(service, owner, rid, **args) == read(service, owner, rid, 1)
    with pytest.raises(ResearchError) as conflict:
        save(service, owner, rid, **(args | {"answer": candidate("另一版解释")}))
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    with pytest.raises(ResearchError) as conflict:
        save(service, owner, rid, **(args | {"key": "new-key"}))
    assert conflict.value.code == "ANSWER_EXISTS"

    # The real service object is retained; unintegrated runtime schema v16
    # intentionally cannot be booted via ResearchStore's public constructor.
    from research.schemas import ProblemInput, RevisionRequest
    updated = service.revise(owner, rid, RevisionRequest(
        expected_revision=1, problem=ProblemInput.model_validate(problem("第二版合成问题"))
    ), "revision-two")["data"]
    historical = read(service, owner, rid, 1)
    assert historical == stored | {"is_historical": True}
    assert save(service, owner, rid, **args) == historical
    with pytest.raises(ResearchError) as stale:
        save(service, owner, rid, **(args | {"key": "stale-key"}))
    assert stale.value.code == "VERSION_CONFLICT"
    with pytest.raises(ResearchError) as mismatch:
        save(service, owner, rid, **(args | {"input_revision": 2, "research_version": updated["research_version"],
                                           "key": "wrong-digest"}))
    assert mismatch.value.code == "VERSION_CONFLICT"
    second = save(service, owner, rid, **(args | {"input_revision": 2, "research_version": updated["research_version"],
                   "problem_digest": updated["current_problem"]["digest"], "key": "second-answer"}))
    assert second == read(service, owner, rid, 2)
    assert second["metadata"]["id"] != stored["metadata"]["id"]

    with service.store.transaction(write=True) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="immutable first answer"):
            conn.execute("UPDATE research_first_answers SET body_json='{}' WHERE id=?", (stored["metadata"]["id"],))
        with pytest.raises(sqlite3.IntegrityError, match="replacement forbidden"):
            conn.execute("INSERT OR REPLACE INTO research_first_answers SELECT * FROM research_first_answers WHERE id=?",
                         (second["metadata"]["id"],))

    login(client, "other-owner@example.test")
    stranger = identity(client)
    service._principal(stranger, create=True)
    for action in (lambda: read(service, stranger, rid, 1), lambda: save(service, stranger, rid, **args)):
        with pytest.raises(ResearchError) as unavailable:
            action()
        assert unavailable.value.status == 404

    from research.service import now
    auth._store().revoke(owner.jti, now(), owner.email)
    for action in (lambda: read(service, owner, rid, 1), lambda: save(service, owner, rid, **args)):
        with pytest.raises(ResearchError) as revoked:
            action()
        assert revoked.value.status == 401
