"""Real private Main, offline migration, owner bindings, and durable job transitions."""
import asyncio
import json
import sqlite3
import subprocess
import sys

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA, envelope, login, prepared, problem, smtp
from web.backend.tests.test_research_first_answer import candidate, identity


def test_queue_owner_claim_recovery_completion_and_erasure(prepared, monkeypatch):
    main, _, paths, messages = prepared
    from api import auth
    from research import first_answer, first_answer_queue as queue
    from research.errors import ResearchError
    from research.service import ResearchService
    from research.store import ResearchStore

    path = paths.private_auth_path()
    lock = path.parent / queue.LOCK_NAME
    lock.touch(mode=0o600, exist_ok=False)
    origin = {"Origin": BETA}
    transport = httpx.ASGITransport(app=main.app)
    receipt = first_answer.provision_first_answers_v16(path)
    assert receipt["first_answer_queue_protocol"] == 1
    assert first_answer.provision_first_answers_v16(path) == receipt

    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
                await login(client, messages)
                service = ResearchService(ResearchStore(auth._store()))
                owner = identity(client)

                async def make(index):
                    text = f"公开合成样例 {index}：为何排队时间变化？"
                    response = await client.post("/api/research",
                        json=envelope({"problem": problem() | {"original_input": text}}),
                        headers=origin | {"Idempotency-Key": f"queue-create-{index}"})
                    assert response.status_code == 200, response.text
                    saved = response.json()["data"]
                    return saved["research"]["id"], {
                        "input_revision": 1, "problem_digest": saved["current_problem"]["digest"],
                        "research_version": saved["research_version"]}, text

                first, second, third = [await make(index) for index in range(3)]
                rid1, args1, text1 = first
                rid2, args2, text2 = second
                rid3, args3, text3 = third
                one = queue.enqueue(service, owner, rid1, **args1)
                two = queue.enqueue(service, owner, rid2, **args2)
                assert one["status"] == two["status"] == "queued"
                assert one == queue.enqueue(service, owner, rid1, **args1) == queue.read(service, owner, rid1, 1)
                with pytest.raises(ResearchError) as full:
                    queue.enqueue(service, owner, rid3, **args3)
                assert full.value.code == "QUEUE_BUSY"
                with pytest.raises(ResearchError) as stale:
                    queue.enqueue(service, owner, rid1, **(args1 | {"research_version": 2}))
                assert stale.value.code == "REVISION_CONFLICT"

                with service.store.transaction(write=True) as conn:
                    job_rows = [dict(row) for row in conn.execute("SELECT * FROM research_first_answer_jobs")]
                    job_text = json.dumps(job_rows, ensure_ascii=False)
                    assert not any(value in job_text for value in (text1, text2, owner.email, owner.generation, owner.jti))
                    assert set(job_rows[0]) == set(queue._COLUMNS)
                    for sql in ("DELETE FROM research_first_answer_jobs",
                                "UPDATE research_first_answer_jobs SET state='running'",
                                "INSERT OR REPLACE INTO research_first_answer_jobs SELECT * FROM research_first_answer_jobs"):
                        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                            conn.execute(sql)

                async with httpx.AsyncClient(transport=transport, base_url=BETA) as other:
                    await login(other, messages, "queue-foreign@example.invalid")
                    foreign = identity(other)
                    service._principal(foreign, create=True)
                    for action in (lambda: queue.read(service, foreign, rid1, 1),
                                   lambda: queue.enqueue(service, foreign, rid1, **args1),
                                   lambda: queue.cancel(service, foreign, rid1, job_id=one["metadata"]["job_id"], **args1)):
                        with pytest.raises(ResearchError) as denied:
                            action()
                        assert denied.value.status == 404

                with queue.worker_session(service) as runner:
                    claimed, raw = runner.claim_next()
                    assert (claimed.research_id, raw) == (rid1, text1)
                    assert runner.is_current(claimed)
                    assert queue.read(service, owner, rid1, 1)["status"] == "running"
                    with pytest.raises(PermissionError):
                        runner.claim_next()
                    with pytest.raises(BlockingIOError):
                        with queue.worker_session(service):
                            pytest.fail("second process must not reconcile active work")
                    result = subprocess.run([sys.executable, "-I", "-B", "-c",
                        "import fcntl,os,sys; fd=os.open(sys.argv[1],os.O_RDONLY); "
                        "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)", str(lock)],
                        check=False, capture_output=True, timeout=6)
                    assert result.returncode != 0 and b"BlockingIOError" in result.stderr
                    # Simulate a Main exit with no complete local result receipt.
                with queue.worker_session(service) as runner:
                    interrupted = queue.read(service, owner, rid1, 1)
                    assert (interrupted["status"], interrupted["reason"]) == ("failed", "interrupted")
                    assert interrupted == queue.enqueue(service, owner, rid1, **args1)
                    claimed2, raw2 = runner.claim_next()
                    assert (claimed2.research_id, raw2) == (rid2, text2)
                    original_transition = queue._transition
                    def fail_commit(*args, **kwargs):
                        if args[4] == "completed":
                            raise ResearchError("STORE_BUSY", 503, "synthetic write failure", retryable=True)
                        return original_transition(*args, **kwargs)
                    with monkeypatch.context() as fault:
                        fault.setattr(queue, "_transition", fail_commit)
                        with pytest.raises(ResearchError, match="STORE_BUSY"):
                            runner.finish(claimed2, answer=candidate())
                    with pytest.raises(ResearchError, match="NOT_FOUND"):
                        first_answer.read(service, owner, rid2, 1)
                    assert runner.is_current(claimed2)
                    completed = runner.finish(claimed2, answer=candidate())
                    assert completed["status"] == "completed"
                    saved = first_answer.read(service, owner, rid2, 1)
                    assert saved["metadata"]["id"] == completed["result_id"]
                    assert (await client.get(f"/api/research/{rid2}/revisions/1/first-answer")).json() == saved
                    assert runner.claim_next() is None

                    three = queue.enqueue(service, owner, rid3, **args3)
                    claimed3, raw3 = runner.claim_next()
                    assert (claimed3.research_id, raw3) == (rid3, text3)
                    cancelled = queue.cancel(service, owner, rid3, job_id=three["metadata"]["job_id"], **args3)
                    assert (cancelled["status"], cancelled["reason"]) == ("cancelled", "owner_cancelled")
                    assert not runner.is_current(claimed3)
                    assert runner.finish(claimed3, answer=candidate()) is None
                    assert cancelled == queue.enqueue(service, owner, rid3, **args3)
                    with pytest.raises(ResearchError, match="NOT_FOUND"):
                        first_answer.read(service, owner, rid3, 1)

                    old, old_args, _ = await make(4)
                    queue.enqueue(service, owner, old, **old_args)
                    change = await client.post(f"/api/research/{old}/revisions", json=envelope({
                        "expected_revision": 1, "problem": problem() | {"original_input": "替换后的公开合成问题"},
                    }), headers=origin | {"Idempotency-Key": "queue-revise-old"})
                    assert change.status_code == 200, change.text
                    assert runner.claim_next() is None
                    assert queue.read(service, owner, old, 1)["reason"] == "revision_changed"

                    followup_rid, followup_args, original = await make(6)
                    queue.enqueue(service, owner, followup_rid, **followup_args)
                    followup_claim, _ = runner.claim_next()
                    for unsuitable in (original, "https://fake.invalid/"):
                        with pytest.raises(ResearchError, match="INPUT_INVALID"):
                            runner.finish(followup_claim, reason="needs_clarification", question=unsuitable)
                    question = "高峰时段的处理人员是否减少？"
                    followup = runner.finish(followup_claim, reason="needs_clarification", question=question)
                    assert (followup["status"], followup["reason"], followup["question"]) == (
                        "failed", "needs_clarification", question)
                    assert queue.read(service, owner, followup_rid, 1) == followup

                    doomed, doomed_args, _ = await make(5)
                    queue.enqueue(service, owner, doomed, **doomed_args)
                    doomed_claim, _ = runner.claim_next()
                    deleted = await client.post("/api/me/delete", json={"confirmation": "DELETE"}, headers=origin)
                    assert deleted.status_code == 200, deleted.text
                    assert not runner.is_current(doomed_claim)
                    assert runner.finish(doomed_claim, answer=candidate()) is None
                with service.store.transaction() as conn:
                    assert conn.execute("SELECT count(*) FROM research_first_answer_jobs").fetchone()[0] == 0
                    assert conn.execute("SELECT count(*) FROM research_first_answers").fetchone()[0] == 0
                with pytest.raises(ResearchError) as revoked:
                    queue.read(service, owner, rid2, 1)
                assert revoked.value.status == 401

    asyncio.run(run())
