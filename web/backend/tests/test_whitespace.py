"""Unit + integration tests for A2 Whitespace Map.

Unit: WhitespaceService matrix/leads logic — normal, edge, error cases.
Integration: TestClient against a focused sub-app exposing whitespace.router.

Pattern follows test_report_api.py — minimal sub-app, isolated fixtures,
no full lifespan / model load.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


***REMOVED*** --------- fixtures --------- ***REMOVED***


def _sample_matrix() -> dict:
    """A small but well-formed whitespace_matrix.json payload."""
    return {
        "meta": {"n_classes": 2, "n_domains": 3, "n_leads": 3},
        "classes": [
            {"class_id": "c1", "class_name": "阈值级联类", "rank": 0},
            {"class_id": "c2", "class_name": "二阶振子类", "rank": 1},
        ],
        "domains": ["金融", "医学", "海洋学"],
        "matrix": {
            "c1": {
                "金融": {"state": "filled", "score": 0.31},
                "医学": {"state": "lead", "score": 0.28},
                "海洋学": {"state": "empty", "score": 0.05},
            },
            "c2": {
                "金融": {"state": "lead", "score": 0.20},
                "医学": {"state": "empty", "score": 0.02},
                "海洋学": {"state": "lead", "score": 0.36},
            },
        },
        "leads": [
            {"class_id": "c2", "class_name": "二阶振子类", "domain": "海洋学",
             "score": 0.36, "anchor_id": "p-100", "anchor_name": "海气耦合"},
            {"class_id": "c1", "class_name": "阈值级联类", "domain": "医学",
             "score": 0.28, "anchor_id": "p-200", "anchor_name": "免疫级联"},
            {"class_id": "c2", "class_name": "二阶振子类", "domain": "金融",
             "score": 0.20, "anchor_id": "p-300", "anchor_name": "价格振荡"},
        ],
    }


@pytest.fixture
def matrix_file(tmp_path) -> Path:
    p = tmp_path / "whitespace_matrix.json"
    p.write_text(json.dumps(_sample_matrix(), ensure_ascii=False), encoding="utf-8")
    return p


@pytest.fixture
def service(matrix_file):
    from services.whitespace_service import WhitespaceService
    return WhitespaceService(data_file=matrix_file)


@pytest.fixture
def client(service, monkeypatch):
    """Sub-app exposing only the whitespace router, wired to the fixture service."""
    from api import whitespace as ws_api

    monkeypatch.setattr(ws_api, "_service", service)
    a = FastAPI()
    a.include_router(ws_api.router, prefix="/api")
    return TestClient(a)


***REMOVED*** --------- unit: WhitespaceService --------- ***REMOVED***


def test_get_matrix_normal(service):
    m = service.get_matrix()
    assert service.available is True
    assert len(m["classes"]) == 2
    assert len(m["domains"]) == 3
    assert m["matrix"]["c1"]["金融"]["state"] == "filled"


def test_get_leads_sorted_desc(service):
    """Leads must come back score-descending regardless of input order."""
    out = service.get_leads()
    scores = [x["score"] for x in out["leads"]]
    assert scores == sorted(scores, reverse=True)
    assert out["total"] == 3
    assert out["count"] == 3


def test_get_leads_filter_by_class(service):
    out = service.get_leads(class_id="c2")
    assert out["total"] == 2
    assert all(x["class_id"] == "c2" for x in out["leads"])


def test_get_leads_filter_by_domain(service):
    out = service.get_leads(domain="海洋学")
    assert out["total"] == 1
    assert out["leads"][0]["anchor_id"] == "p-100"


def test_get_leads_limit_clamped(service):
    """limit below 1 or absurdly large is clamped to the [1, 500] band."""
    assert service.get_leads(limit=0)["limit"] == 1
    assert service.get_leads(limit=99999)["limit"] == 500
    ***REMOVED*** limit smaller than total truncates the list.
    out = service.get_leads(limit=1)
    assert out["count"] == 1 and out["total"] == 3


def test_unknown_class_id_returns_empty_leads(service):
    """Edge: a class_id that does not exist yields zero leads, not an error."""
    out = service.get_leads(class_id="does_not_exist")
    assert out["total"] == 0
    assert out["leads"] == []


def test_missing_json_degrades_gracefully(tmp_path):
    """Error case: absent json -> empty payload, available=False, no exception."""
    from services.whitespace_service import WhitespaceService
    svc = WhitespaceService(data_file=tmp_path / "nope.json")
    assert svc.available is False
    assert svc.get_matrix()["classes"] == []
    assert svc.get_leads()["total"] == 0


def test_malformed_json_degrades_gracefully(tmp_path):
    """Error case: corrupt / wrong-shape json -> empty payload, no exception."""
    from services.whitespace_service import WhitespaceService
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json", encoding="utf-8")
    svc = WhitespaceService(data_file=bad)
    assert svc.available is False

    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    svc2 = WhitespaceService(data_file=wrong)
    assert svc2.available is False


***REMOVED*** --------- integration: endpoints --------- ***REMOVED***


def test_endpoint_matrix_success(client):
    r = client.get("/api/whitespace/matrix")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert len(body["classes"]) == 2
    assert "matrix" in body


def test_endpoint_leads_success(client):
    r = client.get("/api/whitespace/leads")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["available"] is True


def test_endpoint_leads_filter_class(client):
    r = client.get("/api/whitespace/leads", params={"class_id": "c1"})
    assert r.status_code == 200
    assert r.json()["total"] == 1


def test_endpoint_leads_unknown_class_empty(client):
    """Edge: unknown class_id -> 200 with empty list (not 404/500)."""
    r = client.get("/api/whitespace/leads", params={"class_id": "ghost"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_endpoint_leads_limit_out_of_range_rejected(client):
    """Param validation: limit outside [1, 500] -> 422 from FastAPI Query."""
    assert client.get("/api/whitespace/leads", params={"limit": 0}).status_code == 422
    assert client.get("/api/whitespace/leads", params={"limit": 9999}).status_code == 422
    ***REMOVED*** valid boundary passes.
    assert client.get("/api/whitespace/leads", params={"limit": 500}).status_code == 200
