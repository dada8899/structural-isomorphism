"""Canonical spawn entrypoints for synthetic research persistence probes.

Only test process targets live here; application helpers remain in the original
persistence test module. No app, database or process is created on import.
"""
from pathlib import Path
import time

from fastapi.testclient import TestClient
from research.authorization import AuthorizationGate
from research.store import ResearchStore


def _api_process(cookie, path, payload, key, ready, start, result):
    from web.backend.tests.test_research_persistence import app, post

    client = TestClient(app())
    client.cookies.set("phase_session", cookie)
    ready.put(True)
    if not start.wait(15):
        return
    response = post(client, path, payload, key)
    result.put((response.status_code, response.json().get("data", {}).get("research", {}).get("id")))
    client.close()


def _hold_gate(path, principal, acquired):
    from services.auth_store import AuthStore
    gate = AuthorizationGate(ResearchStore(AuthStore(Path(path))))
    with gate.owner_gate(principal):
        acquired.set()
        time.sleep(20)
