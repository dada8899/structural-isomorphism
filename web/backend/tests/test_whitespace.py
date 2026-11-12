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


# --------- fixtures --------- #


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
             "score": 0.36, "anchor_id": "p-100", "anchor_name": "海气耦合",
             "signal": {"type_match": 0.72, "embedding_cos": 0.11,
                        "used_type_signature": True},
             "plausible": "yes", "rationale": "海气耦合具二阶振子结构。",
             "research_question": "海洋学中的厄尔尼诺振荡是否符合阻尼二阶振子模型？"},
            {"class_id": "c1", "class_name": "阈值级联类", "domain": "医学",
             "score": 0.28, "anchor_id": "p-200", "anchor_name": "免疫级联",
             "signal": {"type_match": 0.50, "embedding_cos": 0.08,
                        "used_type_signature": True},
             "plausible": "maybe", "rationale": "免疫级联可能存在阈值触发。",
             "research_question": "医学中的细胞因子风暴是否存在阈值触发的雪崩？"},
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


# --------- unit: WhitespaceService --------- #


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
    # limit smaller than total truncates the list.
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


# --------- integration: endpoints --------- #


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
    # valid boundary passes.
    assert client.get("/api/whitespace/leads", params={"limit": 500}).status_code == 200


# --------- integration: LLM-enriched vs degraded json shapes --------- #


def test_endpoint_leads_passes_through_llm_fields(client):
    """Integration: when the json carries LLM fields (plausible / rationale /
    research_question), the leads endpoint surfaces them unchanged."""
    body = client.get("/api/whitespace/leads").json()
    enriched = [x for x in body["leads"] if x.get("plausible")]
    assert len(enriched) == 2  # two fixture leads have LLM verdicts
    yes = next(x for x in enriched if x["plausible"] == "yes")
    assert yes["rationale"]
    assert "二阶振子" in yes["research_question"]
    assert {x["plausible"] for x in enriched} == {"yes", "maybe"}


def test_endpoint_leads_degraded_no_llm_fields(tmp_path, monkeypatch):
    """Integration: a json with NO LLM fields (build ran without a key) still
    serves leads cleanly — old fields intact, LLM fields simply absent."""
    from services.whitespace_service import WhitespaceService
    from api import whitespace as ws_api

    no_llm = {
        "meta": {"n_classes": 1, "n_domains": 1, "n_leads": 1,
                 "llm_layer_ran": False},
        "classes": [{"class_id": "c1", "class_name": "阈值级联类"}],
        "domains": ["医学"],
        "matrix": {"c1": {"医学": {"state": "lead", "score": 0.4}}},
        "leads": [{"class_id": "c1", "class_name": "阈值级联类", "domain": "医学",
                   "score": 0.4, "anchor_id": "p-1", "anchor_name": "免疫级联",
                   "signal": {"type_match": 0.5, "embedding_cos": 0.1,
                              "used_type_signature": True}}],
    }
    p = tmp_path / "no_llm.json"
    p.write_text(json.dumps(no_llm, ensure_ascii=False), encoding="utf-8")
    svc = WhitespaceService(data_file=p)
    monkeypatch.setattr(ws_api, "_service", svc)
    a = FastAPI()
    a.include_router(ws_api.router, prefix="/api")
    cl = TestClient(a)

    body = cl.get("/api/whitespace/leads").json()
    assert body["available"] is True
    assert body["total"] == 1
    lead = body["leads"][0]
    assert lead["anchor_name"] == "免疫级联"          # old field intact
    assert "plausible" not in lead                     # LLM field absent
    assert "research_question" not in lead


# --------- unit: build script signal + LLM-verdict guardrails --------- #
#
# The build script imports `structural_isomorphism.model` lazily inside
# main(), so importing the module is cheap and model-free.

def _build_module():
    import importlib.util
    script = (Path(__file__).resolve().parents[3]
              / "scripts" / "build_whitespace_matrix.py")
    spec = importlib.util.spec_from_file_location("build_whitespace_matrix", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_histogram_normalizes_and_handles_empty():
    b = _build_module()
    h = b.histogram(["a", "a", "b", ""])  # "" ignored
    assert abs(sum(h.values()) - 1.0) < 1e-9
    assert h["a"] == pytest.approx(2 / 3)
    assert b.histogram([]) == {}            # edge: no type_ids
    assert b.histogram(["", "", ""]) == {}  # edge: all blank


def test_type_enrichment_rewards_concentration_not_common_types():
    """A domain enriched in a class's *characteristic* (rare-baseline)
    type_id scores high; a domain heavy in a globally-common type_id does
    not, even though the class also has it."""
    b = _build_module()
    sig = {"rare": 0.5, "common": 0.5}
    baseline = {"rare": 0.05, "common": 0.5}  # 'rare' is rare globally
    enriched = b.type_enrichment(sig, {"rare": 0.8, "common": 0.2}, baseline)
    generic = b.type_enrichment(sig, {"rare": 0.0, "common": 1.0}, baseline)
    assert enriched > generic
    # edge: empty signature / profile / baseline -> 0.0, no exception.
    assert b.type_enrichment({}, {"x": 1.0}, baseline) == 0.0
    assert b.type_enrichment(sig, {}, baseline) == 0.0
    assert b.type_enrichment(sig, {"rare": 1.0}, {}) == 0.0


def test_squash_enrichment_bounded_and_monotone():
    b = _build_module()
    assert b.squash_enrichment(0.0) == 0.0
    assert 0.0 < b.squash_enrichment(1.0) < b.squash_enrichment(10.0) < 1.0
    assert b.squash_enrichment(-5.0) == 0.0  # negative clamped


def test_coerce_llm_verdict_enum_and_malformed():
    """LLM-output guardrail: plausible coerced to the enum, malformed
    verdicts rejected (None), 'no' flagged for dropping."""
    b = _build_module()
    ok = b._coerce_llm_verdict(
        {"plausible": "YES", "rationale": "r", "research_question": "q"})
    assert ok["plausible"] == "yes" and ok["research_question"] == "q"
    # 'no' -> minimal dict signalling a drop.
    assert b._coerce_llm_verdict({"plausible": "no"}) == {"plausible": "no"}
    # malformed -> None (rejected).
    assert b._coerce_llm_verdict({"plausible": "banana"}) is None
    assert b._coerce_llm_verdict("not a dict") is None
    assert b._coerce_llm_verdict(None) is None
    assert b._coerce_llm_verdict({}) is None


def test_coerce_llm_verdict_missing_research_question():
    """A yes/maybe verdict with no research_question is kept (empty string),
    so the caller can substitute a templated fallback."""
    b = _build_module()
    v = b._coerce_llm_verdict({"plausible": "maybe", "rationale": "r"})
    assert v["plausible"] == "maybe"
    assert v["research_question"] == ""          # caller fills the fallback
    # the templated fallback is non-empty and mentions class + domain.
    fb = b._fallback_research_question("阈值级联类", "医学", "免疫级联")
    assert "阈值级联类" in fb and "医学" in fb


def test_coerce_llm_verdict_missing_rationale_gets_placeholder():
    b = _build_module()
    v = b._coerce_llm_verdict({"plausible": "yes", "research_question": "q"})
    assert v["rationale"]  # non-empty placeholder, never blank


def test_run_llm_layer_mocked(monkeypatch):
    """Integration (mocked): the LLM layer never calls a real endpoint —
    complete_json is monkeypatched. Verifies verdicts are wired per class
    and a None reply (network fail) is skipped, not crashed on."""
    import asyncio
    b = _build_module()

    calls = {"n": 0}

    async def fake_complete_json(**kwargs):
        calls["n"] += 1
        # second candidate of c1 simulates a network/parse failure.
        if calls["n"] == 2:
            return None
        return {"plausible": "yes", "rationale": "结构吻合",
                "research_question": "具体问题？"}

    import services.llm_client as llm_client
    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)

    classes = [{"class_id": "c1", "name_zh": "阈值级联类", "hub_name": "h"}]
    candidates = {"c1": [{"domain": "医学", "anchor": {"name": "a", "description": "d"}},
                         {"domain": "金融", "anchor": None}]}
    verdicts = asyncio.run(b.run_llm_layer(classes, candidates))
    assert "医学" in verdicts["c1"]                 # first candidate judged
    assert verdicts["c1"]["医学"]["plausible"] == "yes"
    assert "金融" not in verdicts["c1"]              # None reply -> skipped
