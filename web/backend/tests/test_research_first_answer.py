"""Actual Main, owned SMTP, private v15/v16 migration and first-answer snapshot."""
import asyncio
import json
import sqlite3
from uuid import UUID

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA, envelope, login, prepared, problem, smtp, source_ready
from web.backend.tests.test_formal_model_startup import startup, encoder, synthetic_readonly_mount


_PRODUCER_FAILURE_CODES = frozenset(("NONE", "INPUT_INVALID", "STORE_BUSY", "STORE_UNAVAILABLE",
    "FEATURE_UNAVAILABLE", "RESEARCH_ERROR_OTHER", "ASSERTION_ERROR", "VALUE_ERROR",
    "TYPE_ERROR", "RUNTIME_ERROR", "OS_ERROR", "OTHER"))


def _producer_failure_code(error):
    from research.errors import ResearchError
    if type(error) is ResearchError:
        return error.code if error.code in {"INPUT_INVALID", "STORE_BUSY", "STORE_UNAVAILABLE", "FEATURE_UNAVAILABLE"} else "RESEARCH_ERROR_OTHER"
    return {AssertionError: "ASSERTION_ERROR", ValueError: "VALUE_ERROR", TypeError: "TYPE_ERROR",
            RuntimeError: "RUNTIME_ERROR", OSError: "OS_ERROR"}.get(type(error), "OTHER")


def _first_answer_timeout(last, worker, producer):
    """Failure-only bounded facts, captured before Main begins retirement."""
    last = last if type(last) is dict else {}
    metadata = last.get("metadata")
    metadata = metadata if type(metadata) is dict else {}
    job = metadata.get("job_id")
    try:
        job = job if type(job) is str and str(UUID(job, version=4)) == job else None
    except ValueError:
        job = None
    status = last.get("status")
    reason = last.get("reason")
    state = {}
    for name, read in (("alive", lambda: worker._thread.is_alive()),
                       ("ready", lambda: worker.ready),
                       ("stopping", lambda: worker._stopping.is_set())):
        try:
            value = read()
            state[name] = value if type(value) is bool else None
        except Exception:
            state[name] = None
    count = lambda name: producer.get(name) if type(producer.get(name)) is int and 0 <= producer[name] <= 2147483647 else None
    error = producer.get("error")
    facts = {"last_status": status if type(status) is str and status in
             {"queued", "running", "failed", "cancelled", "completed", "provisional", "unavailable"} else None,
             "last_reason": reason if type(reason) is str and reason in
             {"interrupted", "unavailable", "insufficient", "needs_clarification", "invalid_answer",
              "cancelled", "revision_changed", "authorization_changed"} else None,
             "job_id": job, "worker": state, "producer_entered": count("entered"),
             "producer_returned": count("returned"),
             "producer_error": error if type(error) is str and error in _PRODUCER_FAILURE_CODES else "OTHER"}
    return AssertionError("background analysis did not reach terminal state; diagnostic=" + json.dumps(facts, sort_keys=True))


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


@pytest.mark.parametrize("schema",[16,17])
def test_actual_main_background_post_reopen_and_cancel(startup, prepared, encoder, monkeypatch, schema):
    import threading
    import time
    from research import first_answer, first_answer_queue, first_answer_supervisor

    main, _, paths, messages = prepared
    path = paths.private_auth_path()
    (path.parent / first_answer_queue.LOCK_NAME).touch(mode=0o600, exist_ok=False)
    first_answer.provision_first_answers_v16(path)
    if schema == 17:
        from research.external_first_answer_catalog import provision_isolated_v17
        from research.external_first_answer_file_writer import approve_isolated_file
        marker = path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
        marker.write_bytes(b"isolated external ledger candidate, no provider\n")
        marker.chmod(0o600)
        provision_isolated_v17(approve_isolated_file(path))

    entered, cancelled = threading.Event(), threading.Event()
    calls = []
    producer = {"entered": 0, "returned": 0, "error": "NONE"}
    local_producer = first_answer_supervisor.produce_background_answer

    def inference_body(question, search, *, cancel):
        assert search.formal is True
        calls.append(question)
        if question.startswith("输入压力"):
            return local_producer(question,search,cancel=cancel)
        if question.startswith("取消"):
            entered.set()
            until = time.monotonic() + 5
            while time.monotonic() < until:
                if cancel.is_set():
                    cancelled.set()
                    return {"status":"unavailable", "reason":"cancelled"}
                time.sleep(.01)
            raise AssertionError("cancel fence was not observed")
        if question.startswith("追问"):
            return {"status":"insufficient", "reason":"needs_clarification", "question":question}
        return {"status":"answered", "content":candidate().model_dump(mode="json", exclude_none=True)}

    def inference(question, search, *, cancel):
        producer["entered"] += 1
        try:
            result = inference_body(question, search, cancel=cancel)
        except BaseException as error:
            producer["error"] = _producer_failure_code(error)
            raise
        producer["returned"] += 1
        return result

    monkeypatch.setattr(first_answer_supervisor, "produce_background_answer", inference)
    origin = {"Origin": BETA}
    transport = httpx.ASGITransport(app=main.app)

    async def run():
        async with main.lifespan(main.app):
            worker = first_answer_supervisor.current(main.app)
            assert worker is not None
            async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
                await login(client, messages)
                for _ in range(12):
                    health = await client.get("/api/health")
                    if health.status_code == 200:
                        break
                    await asyncio.sleep(.1)
                assert health.status_code == 200, health.text
                assert health.json()["checks"]["first_answer"] == "VERIFIER_UNBOUND"
                assert health.json()["checks"]["first_answer_local"] == "ready"
                if schema == 17:
                    assert health.json()["checks"]["external_first_answer"] == "ISSUER_UNBOUND"
                if schema == 17:
                    from api import auth
                    from research.paid_control import _current_scope, _local_answer_scope
                    from research.store import ResearchStore
                    with ResearchStore(auth._store()).transaction(write=True) as conn:
                        with pytest.raises(PermissionError, match="v17 deletion-only scope required"):
                            _current_scope(conn)
                        with pytest.raises(PermissionError, match="local answer writer"):
                            _local_answer_scope(conn)


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
                    raise _first_answer_timeout(got.json(), worker, producer)

                url, body = await make("为什么同样的团队换工具后错误更多？", "async-real-answer")
                assert (await client.post(url, json=body, headers={"Origin":"https://wrong.invalid"})).status_code == 403
                accepted = await client.post(url, json=body, headers=origin)
                assert accepted.status_code == 202, accepted.text
                assert accepted.json()["contract_revision"] == "first-answer-job-v1"
                answered = await read_terminal(url)
                assert answered["status"] == "provisional"
                assert (await client.get(url)).json() == answered
                # A result committed between two read transactions must be
                # returned as a snapshot rather than as a bare completed job.
                original_read = first_answer.read
                checks = []

                def first_read_misses(*args):
                    if not checks:
                        from research.errors import not_found
                        checks.append("first")
                        raise not_found()
                    checks.append("second")
                    return original_read(*args)

                with monkeypatch.context() as race:
                    race.setattr(first_answer, "read", first_read_misses)
                    assert (await client.get(url)).json() == answered
                assert checks == ["first","second"]

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
                url, body = await make("追问这个测试：什么时候改变测量条件？", "async-invalid-clarification")
                assert (await client.post(url, json=body, headers=origin)).status_code == 202
                invalid = await read_terminal(url)
                assert invalid["status"] == "failed" and invalid["reason"] == "invalid_answer"
                url, body = await make("为什么阈值跨过后团队采纳变快？", "async-after-cancel")
                assert (await client.post(url, json=body, headers=origin)).status_code == 202
                assert (await read_terminal(url))["status"] == "provisional"
                url, body = await make("输入压力逐渐上升，达到某个临界范围。只记录了采样时间，没有查看原始曲线。", "async-one-clarification")
                assert (await client.post(url, json=body, headers=origin)).status_code == 202
                clarified = await read_terminal(url)
                assert clarified["status"] == "failed" and clarified["reason"] == "needs_clarification"
                assert clarified["question"].startswith("原始测量在边界两侧")
                assert (await client.get(url)).json() == clarified
                assert len(calls) == 5
                external = url.replace("/first-answer","/external-first-answer")
                key = "e09160ad-396a-4edc-a383-e54c48ba728f"
                write = origin | {"Idempotency-Key":key}
                preview = await client.post(external+"/preview",json=body,headers=origin)
                assert preview.status_code == 503 and preview.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
                assert "exact_question" not in preview.json()
                assert (await client.post(external+"/preview",json={**body,"problem_digest":"0"*64},headers=origin)).status_code == 409
                assert (await client.post(external+"/preview",json=body,headers={"Origin":"https://wrong.invalid"})).status_code == 403
                confirmation = {"purpose":"external-first-answer-question-v1","preview_digest":"b"*64,"request_digest":"c"*64,
                                "upper_units":12000,"confirm_exact_question":True,"confirm_maximum_cost":True,
                                "declares_right_to_send":True}
                sent = await client.post(external+"/confirm",json=confirmation,headers=write)
                assert sent.status_code == 503 and sent.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
                assert (await client.post(external+"/confirm",json={**confirmation,"confirm_maximum_cost":False},headers=write)).status_code == 422
                read = await client.get(external+"/status",headers={"Idempotency-Key":key})
                assert read.status_code == (404 if schema==17 else 503)
                assert (await client.get(external+"/status")).status_code == 422
                returned = await client.get(external+"/result",headers={"Idempotency-Key":key})
                assert returned.status_code == (404 if schema==17 else 503)
                assert "candidate" not in returned.json()

                async with httpx.AsyncClient(transport=transport,base_url=BETA) as other:
                    assert (await other.get(external+"/status",headers={"Idempotency-Key":key})).status_code == 401
                    await login(other,messages,"external-other@example.invalid")
                    assert (await other.get(external+"/status",headers={"Idempotency-Key":key})).status_code == 404
                assert (await client.get(url)).json() == clarified

        assert first_answer_supervisor.current(main.app) is None

    asyncio.run(run())


def test_first_answer_timeout_diagnostic_contains_only_bounded_facts():
    from types import SimpleNamespace
    worker = SimpleNamespace(_thread=SimpleNamespace(is_alive=lambda: False), ready=False,
                             _stopping=SimpleNamespace(is_set=lambda: False))
    job = "97197065-a327-4ef7-bf75-8228635ddad1"
    private = "CANARY_QUESTION_DTO_COOKIE_KEY_ENV"
    last = {"status": "running", "reason": private, "metadata": {"job_id": job, "problem": private},
            "question": private, "cookie": private, "key": private, "env": private}
    with pytest.raises(AssertionError, match="background analysis did not reach terminal state") as failure:
        raise _first_answer_timeout(last, worker, {"entered": 5, "returned": 4, "error": "STORE_BUSY"})
    assert private not in str(failure.value)
    facts = json.loads(str(failure.value).split("; diagnostic=", 1)[1])
    assert facts == {"last_status": "running", "last_reason": None, "job_id": job,
        "worker": {"alive": False, "ready": False, "stopping": False},
        "producer_entered": 5, "producer_returned": 4, "producer_error": "STORE_BUSY"}


def test_first_answer_timeout_diagnostic_never_serializes_unknown_values_or_errors():
    from research.errors import ResearchError
    private = "CANARY_PRIVATE_TEXT"
    assert _producer_failure_code(ValueError(private)) == "VALUE_ERROR"
    assert _producer_failure_code(ResearchError(private, 503, private)) == "RESEARCH_ERROR_OTHER"
    assert _producer_failure_code(ResearchError("INPUT_INVALID", 422, private)) == "INPUT_INVALID"
    assert _producer_failure_code(Exception(private)) == "OTHER"
    failure = _first_answer_timeout({"status": private, "reason": private, "metadata": {"job_id": private}},
        None, {"entered": private, "returned": True, "error": private})
    assert private not in str(failure)
    facts = json.loads(str(failure).split("; diagnostic=", 1)[1])
    assert facts == {"last_status": None, "last_reason": None, "job_id": None,
        "worker": {"alive": None, "ready": None, "stopping": None},
        "producer_entered": None, "producer_returned": None, "producer_error": "OTHER"}
