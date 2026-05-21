"""Unit tests for the Structural Isomorphism MCP server.

All tests use a fake httpx client — no real network calls. We exercise the
pure helper functions and the do_* coroutines with mocked responses.
"""
import asyncio

import httpx
import pytest

import server


***REMOVED*** --- Fake httpx client -------------------------------------------------------


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, status_code=200, json_body=None, text=None):
        self.status_code = status_code
        self._json = json_body
        self.text = text if text is not None else ""

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


class FakeClient:
    """Fake AsyncClient: returns queued responses or raises a queued error."""

    def __init__(self, *, get_result=None, post_result=None):
        self._get_result = get_result
        self._post_result = post_result

    async def get(self, url, **kwargs):
        return self._resolve(self._get_result)

    async def post(self, url, **kwargs):
        return self._resolve(self._post_result)

    @staticmethod
    def _resolve(result):
        if isinstance(result, Exception):
            raise result
        return result


def run(coro):
    return asyncio.run(coro)


***REMOVED*** --- search ------------------------------------------------------------------


def test_search_normal():
    body = {
        "query": "银行挤兑",
        "count": 2,
        "results": [
            {"id": "soc-001", "name": "银行挤兑", "domain": "金融", "type_id": "18",
             "description": "...", "score": 0.9, "relevance": 0.6, "cross_domain": True},
            {"id": "bio-007", "name": "传染病", "domain": "生物", "type_id": "18",
             "description": "...", "score": 0.8, "relevance": 0.55, "cross_domain": True},
        ],
    }
    client = FakeClient(post_result=FakeResponse(200, body))
    out = run(server.do_search(client, "http://x", "银行挤兑", 8))
    assert out["ok"] is True
    assert out["count"] == 2
    assert out["results"][0]["id"] == "soc-001"
    assert out["results"][0]["domain"] == "金融"


def test_search_http_error():
    client = FakeClient(post_result=FakeResponse(405, text="Method Not Allowed"))
    out = run(server.do_search(client, "http://x", "q", 8))
    assert out["ok"] is False
    assert out["error"] == "http_error"
    assert out["status_code"] == 405


def test_search_timeout():
    client = FakeClient(post_result=httpx.TimeoutException("slow"))
    out = run(server.do_search(client, "http://x", "q", 8))
    assert out["ok"] is False
    assert out["error"] == "timeout"


def test_search_empty_results():
    client = FakeClient(post_result=FakeResponse(200, {"query": "zzz", "count": 0, "results": []}))
    out = run(server.do_search(client, "http://x", "zzz", 8))
    assert out["ok"] is True
    assert out["count"] == 0
    assert out["results"] == []


def test_search_top_k_clamped():
    ***REMOVED*** top_k out of range must not raise; clamp handled before request.
    client = FakeClient(post_result=FakeResponse(200, {"query": "q", "count": 0, "results": []}))
    out = run(server.do_search(client, "http://x", "q", 999))
    assert out["ok"] is True


***REMOVED*** --- get_phenomenon ----------------------------------------------------------


def test_get_phenomenon_normal():
    body = {
        "phenomenon": {"id": "soc-001", "name": "银行挤兑", "domain": "金融"},
        "similar": [{"id": "bio-007"}],
        "same_structure": [],
    }
    client = FakeClient(get_result=FakeResponse(200, body))
    out = run(server.do_get_phenomenon(client, "http://x", "soc-001"))
    assert out["ok"] is True
    assert out["phenomenon"]["id"] == "soc-001"
    assert out["similar"][0]["id"] == "bio-007"


def test_get_phenomenon_404():
    client = FakeClient(get_result=FakeResponse(404, text="not found"))
    out = run(server.do_get_phenomenon(client, "http://x", "nope-999"))
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_get_phenomenon_empty_id():
    client = FakeClient(get_result=FakeResponse(200, {}))
    out = run(server.do_get_phenomenon(client, "http://x", "   "))
    assert out["ok"] is False
    assert out["error"] == "bad_request"


def test_get_phenomenon_unreachable():
    client = FakeClient(get_result=httpx.ConnectError("refused"))
    out = run(server.do_get_phenomenon(client, "http://x", "soc-001"))
    assert out["ok"] is False
    assert out["error"] == "unreachable"


***REMOVED*** --- SSE parsing -------------------------------------------------------------


def test_parse_sse_events_multi():
    stream = (
        'event: meta\ndata: {"a": {"id": "soc-001"}, "similarity": 0.7}\n\n'
        'event: section\ndata: {"key": "shared_structure", "data": "S1"}\n\n'
        'event: section\ndata: {"key": "action_plan", "data": "S9"}\n\n'
        'event: done\ndata: {"from_cache": false}\n\n'
    )
    events = server.parse_sse_events(stream)
    assert len(events) == 4
    assert events[0][0] == "meta"
    assert events[1] == ("section", {"key": "shared_structure", "data": "S1"})


def test_parse_sse_events_skips_garbage():
    stream = (
        ': keep-alive comment\n\n'
        'event: section\ndata: not-json\n\n'
        'event: section\ndata: {"key": "k", "data": "v"}\n\n'
    )
    events = server.parse_sse_events(stream)
    ***REMOVED*** comment + bad-json block dropped, only the valid one survives.
    assert events == [("section", {"key": "k", "data": "v"})]


def test_assemble_report_full():
    events = [("meta", {"similarity": 0.7})]
    for key in server.REPORT_SECTION_ORDER:
        events.append(("section", {"key": key, "data": f"content-{key}"}))
    events.append(("done", {"from_cache": False}))
    out = server.assemble_report(events)
    assert out["ok"] is True
    assert out["complete"] is True
    assert out["missing_sections"] == []
    ***REMOVED*** report keys must follow the canonical order.
    assert list(out["report"].keys()) == server.REPORT_SECTION_ORDER


def test_assemble_report_partial():
    events = [
        ("section", {"key": "shared_structure", "data": "S1"}),
        ("section", {"key": "action_plan", "data": "S9"}),
        ("done", {"from_cache": False}),
    ]
    out = server.assemble_report(events)
    assert out["ok"] is True
    assert out["complete"] is False
    assert len(out["missing_sections"]) == 7


def test_assemble_report_error_event():
    events = [
        ("section", {"key": "shared_structure", "data": "S1"}),
        ("error", {"message": "out of scope"}),
    ]
    out = server.assemble_report(events)
    assert out["ok"] is False
    assert out["error"] == "analyze_failed"
    assert out["partial_sections"] == ["shared_structure"]


def test_assemble_report_cached_inline():
    ***REMOVED*** A cached `done` carries the whole report inline (no section events).
    cached = {k: f"c-{k}" for k in server.REPORT_SECTION_ORDER}
    cached["_credibility"] = {"kb_source": True}  ***REMOVED*** underscore key must be dropped
    events = [("meta", {}), ("done", {"from_cache": True, "report": cached})]
    out = server.assemble_report(events)
    assert out["ok"] is True
    assert out["from_cache"] is True
    assert "_credibility" not in out["report"]
    assert out["complete"] is True


def test_assemble_report_empty():
    out = server.assemble_report([("done", {"from_cache": False})])
    assert out["ok"] is False
    assert out["error"] == "empty_report"


***REMOVED*** --- do_analyze --------------------------------------------------------------


def test_do_analyze_normal():
    stream = "".join(
        f'event: section\ndata: {{"key": "{k}", "data": "x"}}\n\n'
        for k in server.REPORT_SECTION_ORDER
    ) + 'event: done\ndata: {"from_cache": false}\n\n'
    client = FakeClient(get_result=FakeResponse(200, text=stream))
    out = run(server.do_analyze(client, "http://x", "为什么会挤兑?", "soc-001"))
    assert out["ok"] is True
    assert out["complete"] is True


def test_do_analyze_404():
    client = FakeClient(get_result=FakeResponse(404, text="Phenomenon not found"))
    out = run(server.do_analyze(client, "http://x", "q?", "bad-id"))
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_do_analyze_timeout():
    client = FakeClient(get_result=httpx.TimeoutException("slow"))
    out = run(server.do_analyze(client, "http://x", "q?", "soc-001"))
    assert out["ok"] is False
    assert out["error"] == "timeout"


def test_do_analyze_empty_stream():
    client = FakeClient(get_result=FakeResponse(200, text=""))
    out = run(server.do_analyze(client, "http://x", "q?", "soc-001"))
    assert out["ok"] is False
    assert out["error"] == "empty_stream"


def test_do_analyze_bad_args():
    client = FakeClient(get_result=FakeResponse(200, text="x"))
    out = run(server.do_analyze(client, "http://x", "  ", "soc-001"))
    assert out["ok"] is False
    assert out["error"] == "bad_request"


***REMOVED*** --- config ------------------------------------------------------------------


def test_get_api_base_default():
    import os
    os.environ.pop("STRUCTURAL_API_BASE", None)
    assert server.get_api_base() == server.DEFAULT_API_BASE


def test_get_api_base_env_override(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_API_BASE", "http://localhost:8000/")
    assert server.get_api_base() == "http://localhost:8000"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
