"""Actual Main, owned SMTP, private v15/v16 migration and first-answer snapshot."""
import asyncio
import sqlite3

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA, envelope, login, prepared, problem, smtp, source_ready
from web.backend.tests.test_formal_model_startup import startup, encoder, synthetic_readonly_mount


def candidate(explanation="在稳定流量附近，波动可能使排队明显增长。"):
    from research.first_answer import AnswerBody
    return AnswerBody(
        producer="test-artifact-v1", explanation=explanation,
        assumptions=["单服务台，短时间内服务能力近似不变。"],
        cross_domain_leads=["缓冲区内的积压也可用流入与流出的差描述。"],
        next_check="比较忙时到达间隔与处理时长。",
        references=[{"artifact": "test-catalog-v1", "locator": "queue-01", "label": "排队机制样例"}],
    )


def identity(client):
    from api import auth
    from research.authorization import AccountIdentity
    claims = auth._decode_jwt(client.cookies.get("phase_session"))
    return AccountIdentity(claims["sub"], claims["gen"], claims["jti"], claims["exp"])


def test_actual_main_first_answer_migration_reopen_and_erasure(prepared, monkeypatch):
    main, admission, paths, messages = prepared
    from api import auth
    from research.errors import ResearchError
    from research.first_answer import read, save, provision_first_answers_v16
    from research.service import ResearchService
    from research.store import ResearchStore
    path = paths.private_auth_path()
    transport = httpx.ASGITransport(app=main.app)
    origin = {"Origin": BETA}

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
            async with main.lifespan(main.app):
                await login(client, messages)
                response = await client.post("/api/research", json=envelope({"problem": problem()}),
                                             headers=origin | {"Idempotency-Key": "create-first-answer"})
                assert response.status_code == 200, response.text
                original = response.json()["data"]
                rid = original["research"]["id"]
                root = f"/api/research/{rid}"
                answer_url = root + "/revisions/1/first-answer"
                closed = await client.get(answer_url)
                assert closed.status_code == 503 and closed.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
                assert closed.headers["cache-control"] == "no-store"
            # A fault after DDL and marker CAS leaves the original v15
            # catalog and private records intact; no startup repair is needed.
            def reject_new_catalog(cls, conn):
                assert conn.execute("SELECT version FROM research_schema").fetchone()[0] == 16
                raise PermissionError("synthetic migration validation failure")
            with monkeypatch.context() as fault:
                fault.setattr(ResearchStore, "_check_v16", classmethod(reject_new_catalog))
                with pytest.raises(PermissionError, match="synthetic migration validation failure"):
                    provision_first_answers_v16(path)
            with auth._store()._connection() as conn:
                assert conn.execute("SELECT version FROM research_schema").fetchone()[0] == 15
                assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_first_answers'").fetchone() is None
            receipt = provision_first_answers_v16(path)
            assert receipt["schema_version"] == 16
            assert provision_first_answers_v16(path) == receipt
            async with main.lifespan(main.app):
                assert admission.safe_status(main.app)["base"] == "ready"
                await source_ready(main, admission)
                assert (await client.get(root)).json()["data"]["current_problem"] == original["current_problem"]
                missing = await client.get(answer_url)
                assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"
                service = ResearchService(ResearchStore(auth._store()))
                assert service.runtime_capability_facts().profile.research_schema == 16
                owner = identity(client)
                args = dict(input_revision=1, problem_digest=original["current_problem"]["digest"],
                            research_version=original["research_version"], key="sample-answer-one", answer=candidate())
                stored = save(service, owner, rid, **args)
                assert stored["status"] == "provisional"
                assert stored == save(service, owner, rid, **args)
                opened = await client.get(answer_url)
                assert opened.json() == stored and opened.headers["cache-control"] == "no-store"
                assert (await client.get(answer_url + "?revision=2")).status_code == 422
                assert (await client.post(answer_url, json=stored, headers=origin)).status_code == 422
                for changes, code in (({"answer": candidate("另一版解释")}, "IDEMPOTENCY_CONFLICT"),
                                      ({"key": "new-key"}, "ANSWER_EXISTS")):
                    with pytest.raises(ResearchError) as conflict:
                        save(service, owner, rid, **(args | changes))
                    assert conflict.value.code == code

                second_problem = problem() | {"original_input": "第二版合成问题"}
                changed = await client.post(root + "/revisions",
                    json=envelope({"expected_revision": 1, "problem": second_problem}),
                    headers=origin | {"Idempotency-Key": "revision-two"})
                assert changed.status_code == 200, changed.text
                updated = changed.json()["data"]
                historical = stored | {"is_historical": True}
                assert (await client.get(answer_url)).json() == historical
                assert save(service, owner, rid, **args) == historical
                for changes in ({"key": "stale-key"}, {"input_revision": 2, "key": "wrong-digest",
                                                     "research_version": updated["research_version"]}):
                    with pytest.raises(ResearchError) as stale:
                        save(service, owner, rid, **(args | changes))
                    assert stale.value.code == "VERSION_CONFLICT"
                second = save(service, owner, rid, **(args | {"input_revision": 2,
                    "research_version": updated["research_version"], "problem_digest": updated["current_problem"]["digest"],
                    "key": "second-answer"}))
                assert second == read(service, owner, rid, 2)
                assert second["metadata"]["id"] != stored["metadata"]["id"]

                with service.store.transaction(write=True) as conn:
                    for statement in ("UPDATE research_first_answers SET body_json='{}'",
                                      "INSERT OR REPLACE INTO research_first_answers SELECT * FROM research_first_answers",
                                      "DELETE FROM research_first_answers"):
                        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                            conn.execute(statement)
                async with httpx.AsyncClient(transport=transport, base_url=BETA) as other:
                    assert (await other.get(answer_url)).status_code == 401
                    await login(other, messages, "other-first-answer@example.invalid")
                    assert (await other.get(answer_url)).status_code == 404

                deleted = await client.post("/api/me/delete", json={"confirmation": "DELETE"}, headers=origin)
                assert deleted.status_code == 200, deleted.text
                with service.store.transaction() as conn:
                    assert conn.execute("SELECT count(*) FROM research_first_answers").fetchone()[0] == 0
                    assert conn.execute("SELECT state FROM auth_deletion_jobs").fetchone()[0] == "completed"
                with pytest.raises(ResearchError) as revoked:
                    read(service, owner, rid, 1)
                assert revoked.value.status == 401
            with sqlite3.connect(path) as conn:
                conn.execute("DROP TRIGGER research_first_answer_guard_delete")
            with pytest.raises(ResearchError) as bad_catalog:
                provision_first_answers_v16(path)
            assert bad_catalog.value.code == "SCHEMA_UNSUPPORTED"

    asyncio.run(run())


def test_actual_main_background_post_reopen_and_cancel(startup, prepared, encoder, monkeypatch):
    import threading
    import time
    from research import first_answer, first_answer_queue, first_answer_supervisor

    main, _, paths, messages = prepared
    path = paths.private_auth_path()
    (path.parent / first_answer_queue.LOCK_NAME).touch(mode=0o600, exist_ok=False)
    first_answer.provision_first_answers_v16(path)
    entered, cancelled = threading.Event(), threading.Event()
    calls = []

    def inference(question, search, *, cancel):
        assert search.formal is True
        calls.append(question)
        if question.startswith("取消"):
            entered.set()
            until = time.monotonic() + 5
            while time.monotonic() < until:
                if cancel.is_set():
                    cancelled.set()
                    return {"status":"unavailable", "reason":"cancelled"}
                time.sleep(.01)
            raise AssertionError("cancel fence was not observed")
        return {"status":"answered", "content":candidate().model_dump(mode="json", exclude_none=True)}

    monkeypatch.setattr(first_answer_supervisor, "produce_background_answer", inference)
    origin = {"Origin": BETA}
    transport = httpx.ASGITransport(app=main.app)

    async def run():
        async with main.lifespan(main.app):
            assert first_answer_supervisor.current(main.app) is not None
            async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
                await login(client, messages)

                async def make(question, key):
                    made = await client.post("/api/research", json=envelope({"problem":problem() | {"original_input":question}}),
                                             headers=origin | {"Idempotency-Key":key})
                    assert made.status_code == 200, made.text
                    row = made.json()["data"]
                    return "/api/research/" + row["research"]["id"] + "/revisions/1/first-answer", {
                        "problem_digest":row["current_problem"]["digest"], "research_version":row["research_version"],
                    }

                async def read_terminal(url):
                    for _ in range(40):
                        got = await client.get(url)
                        assert got.status_code == 200, got.text
                        if got.json()["status"] not in ("queued","running"):
                            return got.json()
                        await asyncio.sleep(.1)
                    raise AssertionError("background analysis did not reach terminal state")

                url, body = await make("为什么同样的团队换工具后错误更多？", "async-real-answer")
                assert (await client.post(url, json=body, headers={"Origin":"https://wrong.invalid"})).status_code == 403
                accepted = await client.post(url, json=body, headers=origin)
                assert accepted.status_code == 202, accepted.text
                assert accepted.json()["contract_revision"] == "first-answer-job-v1"
                answered = await read_terminal(url)
                assert answered["status"] == "provisional"
                assert (await client.get(url)).json() == answered
                assert (await client.post(url, json=body, headers=origin)).json() == answered

                url, body = await make("取消这个测试：为什么相同的流量有更长等待？", "async-real-cancel")
                accepted = await client.post(url, json=body, headers=origin)
                assert accepted.status_code == 202, accepted.text
                job_id = accepted.json()["metadata"]["job_id"]
                assert await asyncio.to_thread(entered.wait, 4)
                stopped = await client.request("DELETE", url, json={**body, "job_id":job_id}, headers=origin)
                assert stopped.status_code == 200 and stopped.json()["status"] == "cancelled", stopped.text
                assert await asyncio.to_thread(cancelled.wait, 3)
                assert (await client.get(url)).json() == stopped.json()
                assert (await client.post(url, json=body, headers=origin)).json() == stopped.json()
                assert len(calls) == 2
        assert first_answer_supervisor.current(main.app) is None

    asyncio.run(run())
