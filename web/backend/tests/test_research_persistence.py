"""Actual HTTP/auth/SQLite lifecycle; all identities and payloads are synthetic."""
from __future__ import annotations

import copy
import subprocess
import json
import multiprocessing
import os
import signal
import sqlite3
from contextlib import closing
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import jwt

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
# Expose the canonical spawn module without changing backend-first precedence.
PROJECT_ROOT = BACKEND.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
from web.backend.tests.research_process_fixture import _api_process, _hold_gate, _run_owned_probe
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import auth, research, sso
from research.authorization import AuthorizationGate
from research.store import ResearchStore


def app():
    instance = FastAPI()
    instance.include_router(auth.router, prefix="/api")
    instance.include_router(research.router, prefix="/api")
    return instance


def problem(text="合成排队问题：午间等待时间为什么增加？"):
    return {"entry": "phenomenon", "original_input": text, "objective": "缩短合成等待时间",
            "summary": "合成排队现象与等待时间的结构描述", "variables": [],
            "constraints": ["仅为离线测试"], "unknowns": ["到达规律尚未确认"], "confirmed": False}


def envelope(data):
    return {"schema_version": "structure-research-v1", "contract_revision": "b1-candidate-01", "data": data}


def post(client, path, data, key=None):
    return client.post(path, json=envelope(data), headers={"Idempotency-Key": key or str(uuid4()), "Origin": "http://testserver"})


def login(client, email="research-a@example.test"):
    response = client.post("/api/auth/request-link", json={"email": email}, headers={"Origin": "http://testserver"})
    assert response.status_code == 200, response.text
    verified = client.post("/api/auth/verify", json={"token": response.json()["dev_token"]}, headers={"Origin": "http://testserver"})
    assert verified.status_code == 200, verified.text
    return client.cookies.get("phase_session")


@pytest.fixture
def stack(tmp_path, monkeypatch):
    for name, value in {
        "AUTH_DATA_DIR": str(tmp_path / "auth"), "AUTH_ENABLED": "true", "AUTH_DEV_MODE": "true",
        "JWT_SECRET": "research-synthetic-auth-secret-32-characters", "AUTH_LINK_BASE_URL": "http://testserver",
        "STRUCTURAL_SSO_SECRET": "research-synthetic-sso-secret-32-characters", "STRUCTURAL_RESEARCH_ENABLED": "true",
        "STRUCTURAL_ENV": "test", "STRUCTURAL_LOG_FILE": str(tmp_path / "server.jsonl"),
        "STRUCTURAL_SSO_DATA_DIR": str(tmp_path / "sso"), "ADMIN_NOTIFICATION_EMAIL": "",
        "STRUCTURAL_SSO_BETA_ORIGIN": "http://testserver", "STRUCTURAL_SSO_PHASE_ORIGIN": "http://phase.test",
        "STRUCTURAL_FAVORITES_PATH": str(tmp_path / "favorites.jsonl"),
        "STRUCTURAL_PRIVACY_HMAC_KEY": "0123456789abcdef" * 4,
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(auth, "_data_dir", lambda: tmp_path / "auth")
    with TestClient(app()) as client:
        login(client)
        yield client, tmp_path / "auth" / "auth.sqlite3"


def create(client, key="create-one"):
    response = post(client, "/api/research", {"problem": problem()}, key)
    assert response.status_code == 200, response.text
    return response.json()["data"]["research"]["id"]


def test_saved_revisions_reopen_and_migrate_same_auth_db(stack):
    client, path = stack
    rid = create(client)
    changed = post(client, f"/api/research/{rid}/revisions", {"expected_revision": 1, "problem": problem("第二版合成问题")}, "revision-two")
    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["research_version"] == 2
    # Recreate application and stores, preserving actual disk contents/session.
    with TestClient(app()) as reopened:
        reopened.cookies.update(client.cookies)
        response = reopened.get(f"/api/research/{rid}")
        data = response.json()["data"]
        assert [r["revision"] for r in data["revisions"]] == [1, 2]
        assert data["revisions"][0]["original_input"] == problem()["original_input"]
        assert data["current_problem"]["original_input"] == "第二版合成问题"
        assert data["execution"] is None and data["evidence"] == "UNASSESSED"
        assert response.headers["cache-control"] == "no-store"
        assert not data["capabilities"]["execution"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM auth_users").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM research_revisions").fetchone()[0] == 2
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE research_revisions SET problem_json='{}'")
    assert list(path.parent.glob("*.sqlite3")) == [path]


def test_idempotency_conflicts_and_stale_revision_do_not_overwrite(stack):
    client, path = stack
    first = post(client, "/api/research", {"problem": problem()}, "same")
    assert first.status_code == 200
    assert post(client, "/api/research", {"problem": problem()}, "same").json() == first.json()
    assert post(client, "/api/research", {"problem": problem("变更内容")}, "same").status_code == 409
    rid = first.json()["data"]["research"]["id"]
    body = {"expected_revision": 1, "problem": problem("新修订")}
    second = post(client, f"/api/research/{rid}/revisions", body, "rev")
    assert second.status_code == 200
    assert post(client, f"/api/research/{rid}/revisions", body, "rev").json() == second.json()
    assert post(client, f"/api/research/{rid}/revisions", body, "other").status_code == 409
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM research_idempotency").fetchone()[0] == 2


def test_other_account_unknown_id_and_expired_session_are_not_private(stack):
    client, _ = stack
    rid = create(client)
    original_cookie = client.cookies.get("phase_session")
    with TestClient(app()) as other:
        login(other, "research-b@example.test")
        known, unknown = other.get(f"/api/research/{rid}"), other.get(f"/api/research/{uuid4()}")
        assert known.status_code == unknown.status_code == 404
        assert known.json()["error"]["code"] == unknown.json()["error"]["code"]
        assert problem()["original_input"] not in known.text
        assert post(other, f"/api/research/{rid}/revisions", {"expected_revision": 1, "problem": problem()}).status_code == 404
    assert client.post("/api/auth/logout", headers={"Origin": "http://testserver"}).status_code == 200
    client.cookies.set("phase_session", original_cookie)
    assert client.get(f"/api/research/{rid}").status_code == 401
    assert post(client, "/api/research", {"problem": problem()}, "create-one").status_code == 401


def test_same_email_new_generation_never_inherits_old_research(stack):
    client, _ = stack
    rid = create(client)
    old_cookie = client.cookies.get("phase_session")
    # Controlled auth incarnation transition, not an account-deletion acceptance.
    auth._store().delete_account_data("research-a@example.test")
    login(client)
    assert client.cookies.get("phase_session") != old_cookie
    assert client.get(f"/api/research/{rid}").status_code == 404
    new_id = create(client, key="create-one")
    assert new_id != rid
    client.cookies.set("phase_session", old_cookie)
    assert client.get(f"/api/research/{rid}").status_code == 401


def trusted_sso(email):
    subject, timestamp, jti = sso._subject_id(email), int(time.time()), str(uuid4())
    sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3").issue(
        "binding-" + jti, subject, "free", timestamp + 120, email=email,
    )
    return jwt.encode({"iss":"http://testserver", "aud":"structural-beta-session",
                       "sub":subject, "tier":"free", "jti":jti, "iat":timestamp,
                       "issued_ns":time.time_ns(), "exp":timestamp+3600}, sso._secret(), algorithm="HS256")


@pytest.mark.parametrize("credentials,expected", [
    ("direct-only", 200), ("same-identity", 200),
    ("different-identity", 409), ("invalid-sso", 401),
    ("sso-only", 401), ("invalid-direct", 401),
])
def test_unified_credentials_fail_closed_before_research_reads_writes_and_replay(stack, credentials, expected):
    client, path = stack
    rid = create(client)
    if credentials == "different-identity":
        with TestClient(app()) as other:
            login(other, "research-b@example.test")
        client.cookies.set("structural_beta_session", trusted_sso("research-b@example.test"))
    elif credentials == "invalid-sso":
        client.cookies.set("structural_beta_session", "invalid-synthetic-sso")
    elif credentials in {"same-identity", "sso-only", "invalid-direct"}:
        client.cookies.set("structural_beta_session", trusted_sso("research-a@example.test"))
    if credentials == "sso-only":
        client.cookies.delete("phase_session")
    elif credentials == "invalid-direct":
        client.cookies.delete("phase_session")
        client.cookies.set("phase_session", "invalid-synthetic-direct")
    me = client.get("/api/auth/me")
    assert me.status_code == (200 if credentials == "sso-only" else expected)
    with sqlite3.connect(path) as conn:
        before = tuple(conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                       for table in ("research_controls", "research_revisions", "research_idempotency"))
    responses = [
        client.get(f"/api/research/{rid}"),
        post(client, "/api/research", {"problem":problem()}, "create-one"),
        post(client, "/api/research", {"problem":problem()}, "new-create"),
        post(client, f"/api/research/{rid}/revisions", {"expected_revision":1,"problem":problem("第二修订")}, "new-revise"),
    ]
    assert [r.status_code for r in responses] == [expected] * 4
    if expected != 200:
        for response in responses:
            assert problem()["original_input"] not in response.text
        with sqlite3.connect(path) as conn:
            after = tuple(conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                          for table in ("research_controls", "research_revisions", "research_idempotency"))
        assert after == before


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(owner_id=str(uuid4())),
    lambda b: b.update(schema_version="unknown-v99"),
    lambda b: b.update(contract_revision="future"),
    lambda b: b["data"]["problem"].update(confirmed=1),
    lambda b: b["data"]["problem"].update(summary="短"),
    lambda b: b["data"]["problem"].update(original_input="a" * 4001),
    lambda b: b["data"]["problem"].update(objective="unsafe\u202evalue"),
    lambda b: b["data"]["problem"].update(unknowns=["a"] * 13),
    lambda b: b["data"]["problem"].update(variables=[{"id":"x","label":"x","role":"state","unit_id":"bad","observation":None,"provenance":"user_assumed"}]),
    lambda b: b["data"]["problem"].update(variables=[{"id":"x","label":"x","role":"state","unit_id":None,"observation":None,"provenance":"user_assumed"}] * 2),
])
def test_strict_inputs_do_not_persist_or_echo_bad_content(stack, mutation):
    client, path = stack
    body = envelope({"problem": problem("PRIVATE-SYNTHETIC-CANARY")})
    mutation(body)
    response = client.post("/api/research", json=body, headers={"Idempotency-Key": "invalid"})
    assert response.status_code == 422
    assert "PRIVATE-SYNTHETIC-CANARY" not in response.text
    assert "input" not in response.json()["error"] and "ctx" not in response.json()["error"]
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM research_controls").fetchone()[0] == 0


@pytest.mark.parametrize("raw", [
    '{"schema_version":"structure-research-v1","schema_version":"structure-research-v1"}',
    '{"nested":{"x":1,"x":2}}', '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}',
    '{"x":"\\ud800"}', '{broken',
])
def test_duplicate_keys_nonfinite_and_malformed_json_are_safe(stack, raw):
    client, _ = stack
    response = client.post("/api/research", content=raw, headers={"Content-Type":"application/json", "Idempotency-Key":"bad-json"})
    assert response.status_code == 422


def test_limit_origin_missing_key_and_boolean_revision(stack):
    client, _ = stack
    response = client.post("/api/research", content=b" " * 65537, headers={"Content-Type":"application/json", "Idempotency-Key":"too-big"})
    assert response.status_code == 413
    assert client.post("/api/research", json=envelope({"problem":problem()})).status_code == 422
    assert client.post("/api/research", json=envelope({"problem":problem()}), headers={"Origin":"https://outside.test", "Idempotency-Key":"outside"}).status_code == 403
    rid = create(client)
    for value in (True, 1.0, "1", 0, 2147483648):
        assert post(client, f"/api/research/{rid}/revisions", {"expected_revision":value,"problem":problem()}).status_code == 422


def test_disabled_and_production_cannot_be_opted_in(stack, monkeypatch):
    client, _ = stack
    monkeypatch.setenv("STRUCTURAL_RESEARCH_ENABLED", "false")
    assert post(client, "/api/research", {"problem":problem()}).status_code == 503
    monkeypatch.setenv("STRUCTURAL_RESEARCH_ENABLED", "true")
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    assert post(client, "/api/research", {"problem":problem()}).status_code == 503


def test_storage_failure_rolls_back_revision_and_idempotency(stack,monkeypatch):
    client, path = stack
    rid = create(client)
    connect=sqlite3.connect;inserted=[]
    class FaultConnection(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if sql.startswith('INSERT INTO research_revisions') and args and args[0][1]==2:
                inserted.append(True);raise sqlite3.OperationalError('synthetic failure')
            return result
    with monkeypatch.context() as failed:
        failed.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=FaultConnection,**k))
        response = post(client, f"/api/research/{rid}/revisions", {"expected_revision":1,"problem":problem("第二修订")}, "failed-rev")
    assert inserted
    assert response.status_code == 503 and "synthetic" not in response.text
    current = client.get(f"/api/research/{rid}").json()["data"]
    assert current["research_version"] == 1 and len(current["revisions"]) == 1
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT count(*) FROM research_idempotency").fetchone()[0] == 1


def test_grant_and_epoch_checks_apply_before_replay(stack):
    client, path = stack
    rid = create(client)
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE research_grants SET scopes='[\"read\"]'")
    assert client.get(f"/api/research/{rid}").status_code == 200
    assert post(client, f"/api/research/{rid}/revisions", {"expected_revision":1,"problem":problem()}).status_code == 404
    with sqlite3.connect(path) as conn:
        conn.execute("UPDATE research_principals SET epoch=epoch+1")
    assert post(client, "/api/research", {"problem":problem()}, "create-one").status_code == 404



@pytest.mark.parametrize("operation", ["same-create", "competing-revision"])
def test_two_real_api_processes_serialize_and_keep_one_revision(stack, operation):
    client, path = stack
    rid = create(client)
    context = multiprocessing.get_context("spawn")
    ready, result, start = context.Queue(), context.Queue(), context.Event()
    processes = []
    try:
        for number in range(2):
            endpoint = "/api/research" if operation == "same-create" else f"/api/research/{rid}/revisions"
            payload = {"problem":problem()} if operation == "same-create" else {"expected_revision":1,"problem":problem(str(number))}
            key = "concurrent-create" if operation == "same-create" else f"revision-{number}"
            process = context.Process(target=_api_process, args=(client.cookies.get("phase_session"), endpoint, payload, key, ready, start, result))
            process.start()
            processes.append(process)
        assert ready.get(timeout=15) and ready.get(timeout=15)
        start.set()
        responses = [result.get(timeout=20), result.get(timeout=20)]
        if operation == "same-create":
            assert [r[0] for r in responses] == [200, 200]
            assert responses[0][1] == responses[1][1]
        else:
            assert sorted(r[0] for r in responses) == [200, 409]
            with sqlite3.connect(path) as conn:
                assert conn.execute("SELECT count(*) FROM research_revisions WHERE research_id=?", (rid,)).fetchone()[0] == 2
    finally:
        start.set()
        for process in processes:
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join(5)
        ready.close()
        result.close()



def test_os_gate_excludes_another_process_and_recovers_after_process_exit(stack):
    client, path = stack
    rid = create(client)
    with sqlite3.connect(path) as conn:
        principal = conn.execute("SELECT owner_id FROM research_controls WHERE id=?", (rid,)).fetchone()[0]
    gate = AuthorizationGate(ResearchStore(auth._store()))
    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    process = context.Process(target=_hold_gate, args=(str(path), principal, acquired))
    process.start()
    try:
        assert acquired.wait(15)
        with pytest.raises(Exception) as error:
            with gate.owner_gate(principal, timeout=.1):
                pytest.fail("entered held OS gate")
        assert error.value.code == "STORE_BUSY"
        lock = path.parent / "research-locks" / (principal + ".lock")
        inode = lock.stat().st_ino
        process.terminate()
        process.join(5)
        with gate.owner_gate(principal, timeout=1):
            assert lock.stat().st_ino == inode
    finally:
        if process.is_alive():
            process.terminate()
        process.join(5)


def test_canonical_spawn_targets_survive_backend_tests_cache_and_root_first_import():
    program = r"""
import importlib, pathlib, sys
backend = pathlib.Path.cwd()
root = backend.parents[1]
sys.path[:] = [str(backend)] + [p for p in sys.path if p not in ('', str(root), str(backend))]
original = importlib.import_module('tests.test_research_persistence')
assert pathlib.Path(sys.modules['tests'].__file__).resolve() == backend / 'tests/__init__.py'
# The persistence fixture adds a canonical import root at the end, not first.
sys.path.remove(str(root))
importlib.import_module('tests.test_universality_endpoints')
assert sys.path[0] == str(root)
assert original.__name__ == 'tests.test_research_persistence'
assert original._api_process.__module__ == 'web.backend.tests.research_process_fixture'
assert original._hold_gate.__module__ == 'web.backend.tests.research_process_fixture'
import pytest
raise SystemExit(pytest.main([
    'tests/test_research_persistence.py::test_two_real_api_processes_serialize_and_keep_one_revision',
    'tests/test_research_persistence.py::test_os_gate_excludes_another_process_and_recovers_after_process_exit',
    '-q', '-p', 'no:cacheprovider', '--show-capture=no', '--tb=short',
]))
"""
    result = _run_owned_probe(program, BACKEND)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '3 passed' in result.stdout


def test_owned_probe_timeout_cleans_descendant_after_parent_already_exited(tmp_path, monkeypatch):
    manifest = tmp_path / 'owned-process.json'
    program = (
        'import json,os,pathlib,subprocess,sys; '
        'child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); '
        f'pathlib.Path({str(manifest)!r}).write_text(json.dumps({{"child":child.pid,"group":os.getpgrp()}})); '
        'os._exit(0)'
    )
    communicate = subprocess.Popen.communicate
    registered = []

    def timeout_after_parent_exit(process, *args, **kwargs):
        if process.args == [sys.executable, '-c', program]:
            assert kwargs['timeout'] == 120
            process.wait(timeout=5)
            assert process.returncode == 0
            record = json.loads(manifest.read_text())
            assert record['group'] == process.pid
            assert os.getpgid(record['child']) == process.pid
            registered.append(process)
            # Exercise a real pipe timeout with a test-only short wait; the
            # supervisor itself still passed its unchanged 120-second limit.
            return communicate(process, timeout=.05)
        return communicate(process, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, 'communicate', timeout_after_parent_exit)
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            _run_owned_probe(program, tmp_path)
        child = json.loads(manifest.read_text())['child']
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = subprocess.run(['ps', '-p', str(child), '-o', 'stat='], capture_output=True, text=True).stdout.strip()
            if not state or state.startswith('Z'):
                break
            time.sleep(.01)
        assert not state or state.startswith('Z'), 'owned descendant is still live'
        assert len(registered) == 1 and registered[0].stdout.closed and registered[0].stderr.closed
    finally:
        if manifest.exists():
            try:
                os.killpg(json.loads(manifest.read_text())['group'], signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_owned_probe_normal_completion_does_not_kill_another_session(tmp_path):
    with subprocess.Popen(
        [sys.executable, '-c', 'import time;time.sleep(30)'], start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ) as unrelated:
        try:
            group = os.getpgid(unrelated.pid)
            result = _run_owned_probe('print("normal owned result")', tmp_path)
            assert result.returncode == 0 and result.stdout == 'normal owned result\n'
            assert unrelated.poll() is None and os.getpgid(unrelated.pid) == group
        finally:
            unrelated.terminate()
            unrelated.wait(timeout=5)
