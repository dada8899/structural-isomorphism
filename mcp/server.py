"""MCP server for the Structural Isomorphism cross-domain engine.

Exposes the "find structural isomorphism" capability over the Model Context
Protocol (stdio transport) so any MCP-aware agent can call it.

Tools:
  - search_isomorphism   : POST /api/search       — structurally similar phenomena
  - get_phenomenon       : GET  /api/phenomenon   — single phenomenon detail
  - analyze_isomorphism  : GET  /api/analyze/stream (SSE) — full 9-section report
  - find_isomorphism     : search + analyze in one shot

Backend base URL is configurable via the STRUCTURAL_API_BASE env var.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# --- Configuration ----------------------------------------------------------

DEFAULT_API_BASE = "https://beta.structural.bytedance.city"


def get_api_base() -> str:
    """Return the backend base URL, honouring STRUCTURAL_API_BASE."""
    return os.environ.get("STRUCTURAL_API_BASE", DEFAULT_API_BASE).rstrip("/")


# The deep-analysis report is LLM-generated and takes ~3-4 minutes.
ANALYZE_TIMEOUT_S = 360.0
# search / phenomenon are fast pure lookups.
QUICK_TIMEOUT_S = 30.0

# The 9 sections a complete analysis report should contain, in render order.
REPORT_SECTION_ORDER = [
    "shared_structure",
    "your_problem_breakdown",
    "target_domain_intro",
    "structural_mapping",
    "borrowable_insights",
    "how_to_combine",
    "research_directions",
    "risks_and_limits",
    "action_plan",
]


# --- Error helper ------------------------------------------------------------


def _error(kind: str, message: str, **extra: Any) -> dict:
    """Build a structured error payload (never raise to the MCP layer)."""
    out = {"ok": False, "error": kind, "message": message}
    out.update(extra)
    return out


# --- Core logic (pure, testable; no MCP / no global state) -------------------


def parse_search_response(payload: dict) -> dict:
    """Normalise the /api/search JSON into a compact result list."""
    results = []
    for r in payload.get("results", []) or []:
        results.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "domain": r.get("domain"),
                "type_id": r.get("type_id"),
                "description": r.get("description"),
                "score": r.get("score"),
                "relevance": r.get("relevance"),
                "cross_domain": r.get("cross_domain"),
            }
        )
    return {
        "ok": True,
        "query": payload.get("query"),
        "count": payload.get("count", len(results)),
        "out_of_scope": payload.get("out_of_scope", False),
        "scope_reason": payload.get("scope_reason"),
        "results": results,
    }


async def do_search(client: httpx.AsyncClient, base: str, query: str, top_k: int) -> dict:
    """Call POST /api/search and return a structured result or error dict."""
    top_k = max(1, min(int(top_k), 30))
    try:
        resp = await client.post(
            f"{base}/api/search",
            json={"query": query, "top_k": top_k},
            timeout=QUICK_TIMEOUT_S,
        )
    except httpx.TimeoutException:
        return _error("timeout", f"Search request timed out after {QUICK_TIMEOUT_S}s")
    except httpx.HTTPError as exc:
        return _error("unreachable", f"Cannot reach backend: {exc}")

    if resp.status_code != 200:
        return _error(
            "http_error",
            f"Backend returned HTTP {resp.status_code}",
            status_code=resp.status_code,
            body=resp.text[:500],
        )
    try:
        return parse_search_response(resp.json())
    except (ValueError, json.JSONDecodeError):
        return _error("bad_response", "Backend returned non-JSON body", body=resp.text[:500])


async def do_get_phenomenon(client: httpx.AsyncClient, base: str, phenomenon_id: str) -> dict:
    """Call GET /api/phenomenon/{id} and return a structured result or error."""
    if not phenomenon_id or not phenomenon_id.strip():
        return _error("bad_request", "phenomenon_id must be a non-empty string")
    pid = phenomenon_id.strip()
    try:
        resp = await client.get(f"{base}/api/phenomenon/{pid}", timeout=QUICK_TIMEOUT_S)
    except httpx.TimeoutException:
        return _error("timeout", f"Phenomenon request timed out after {QUICK_TIMEOUT_S}s")
    except httpx.HTTPError as exc:
        return _error("unreachable", f"Cannot reach backend: {exc}")

    if resp.status_code == 404:
        return _error("not_found", f"Phenomenon '{pid}' not found")
    if resp.status_code != 200:
        return _error(
            "http_error",
            f"Backend returned HTTP {resp.status_code}",
            status_code=resp.status_code,
            body=resp.text[:500],
        )
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        return _error("bad_response", "Backend returned non-JSON body", body=resp.text[:500])
    return {
        "ok": True,
        "phenomenon": data.get("phenomenon"),
        "similar": data.get("similar", []),
        "same_structure": data.get("same_structure", []),
    }


def parse_sse_events(text: str) -> list[tuple[str, dict]]:
    """Parse a raw SSE stream body into a list of (event_type, data) tuples.

    Each SSE record is `event: <type>\\ndata: <json>\\n\\n`. Records with an
    unparseable data line are skipped silently (defensive against keep-alive
    comments and partial frames).
    """
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = "message"
        data_lines: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        try:
            data = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            continue
        events.append((event_type, data))
    return events


def assemble_report(events: list[tuple[str, dict]]) -> dict:
    """Turn a list of SSE (type, data) events into a complete report dict.

    Honours meta / section / error / done events. `text` events (incremental
    deltas) are ignored because `section` events carry the final block.
    """
    meta: dict | None = None
    sections: dict[str, Any] = {}
    error: dict | None = None
    done_seen = False
    from_cache = False

    for event_type, data in events:
        if event_type == "meta":
            meta = data
        elif event_type == "section":
            key = data.get("key")
            if key:
                sections[key] = data.get("data")
        elif event_type == "error":
            error = data
        elif event_type == "done":
            done_seen = True
            from_cache = bool(data.get("from_cache"))
            # A cached done event carries the whole report inline.
            cached = data.get("report")
            if cached and isinstance(cached, dict) and not sections:
                for k, v in cached.items():
                    if not k.startswith("_"):
                        sections[k] = v

    if error:
        return _error(
            "analyze_failed",
            error.get("message") or error.get("reason") or "Analysis failed",
            partial_sections=sorted(sections.keys()),
        )
    if not sections:
        return _error(
            "empty_report",
            "Analysis produced no sections",
            done=done_seen,
        )

    ordered = {k: sections[k] for k in REPORT_SECTION_ORDER if k in sections}
    # Keep any extra sections the backend may emit beyond the known 9.
    for k, v in sections.items():
        if k not in ordered:
            ordered[k] = v
    missing = [k for k in REPORT_SECTION_ORDER if k not in sections]
    return {
        "ok": True,
        "from_cache": from_cache,
        "complete": len(missing) == 0,
        "missing_sections": missing,
        "meta": meta,
        "report": ordered,
    }


async def do_analyze(
    client: httpx.AsyncClient,
    base: str,
    question: str,
    phenomenon_id: str,
    lang: str = "zh",
) -> dict:
    """Call GET /api/analyze/stream, consume the full SSE stream, assemble it."""
    if not question or not question.strip():
        return _error("bad_request", "question must be a non-empty string")
    if not phenomenon_id or not phenomenon_id.strip():
        return _error("bad_request", "phenomenon_id must be a non-empty string")
    lang = (lang or "zh").lower()
    if lang not in ("zh", "en"):
        lang = "zh"

    params = {"text_a": question.strip(), "b_id": phenomenon_id.strip(), "lang": lang}
    try:
        resp = await client.get(
            f"{base}/api/analyze/stream",
            params=params,
            timeout=ANALYZE_TIMEOUT_S,
        )
    except httpx.TimeoutException:
        return _error("timeout", f"Analysis timed out after {ANALYZE_TIMEOUT_S}s")
    except httpx.HTTPError as exc:
        return _error("unreachable", f"Cannot reach backend: {exc}")

    if resp.status_code == 404:
        return _error("not_found", f"Phenomenon '{phenomenon_id}' not found")
    if resp.status_code != 200:
        return _error(
            "http_error",
            f"Backend returned HTTP {resp.status_code}",
            status_code=resp.status_code,
            body=resp.text[:500],
        )
    events = parse_sse_events(resp.text)
    if not events:
        return _error("empty_stream", "Analysis stream contained no events")
    return assemble_report(events)


# --- MCP server + tool registration ------------------------------------------

mcp = FastMCP("structural-isomorphism")


@mcp.tool()
async def search_isomorphism(query: str, top_k: int = 8) -> dict:
    """Find phenomena that share a deep STRUCTURAL pattern with the query.

    Use this when a problem in one domain might have a known analogue in
    another (e.g. a bank run is structurally a positive-feedback cascade,
    also seen in epidemics, traffic jams, and forest fires). Returns a
    ranked list of cross-domain phenomena, each with id/name/domain/
    description/score/relevance. Pass a phenomenon id to get_phenomenon or
    analyze_isomorphism for deeper work.

    Args:
        query: A phenomenon, problem, or question in natural language
               (Chinese or English). Max 500 chars.
        top_k: Number of results to return, 1-30. Default 8.
    """
    base = get_api_base()
    async with httpx.AsyncClient() as client:
        return await do_search(client, base, query, top_k)


@mcp.tool()
async def get_phenomenon(phenomenon_id: str) -> dict:
    """Fetch full detail for one phenomenon by its id.

    Returns the phenomenon (id/name/domain/type_id/description) plus its
    nearest similar phenomena and same-structure siblings. Get ids from
    search_isomorphism first.

    Args:
        phenomenon_id: The phenomenon id, e.g. "soc-001".
    """
    base = get_api_base()
    async with httpx.AsyncClient() as client:
        return await do_get_phenomenon(client, base, phenomenon_id)


@mcp.tool()
async def analyze_isomorphism(question: str, phenomenon_id: str, lang: str = "zh") -> dict:
    """Produce a deep cross-domain transfer report for a question.

    Given the user's question and a target phenomenon id (from
    search_isomorphism), this generates a full 9-section report that maps
    the structure of the known phenomenon onto the user's problem:
    shared_structure, your_problem_breakdown, target_domain_intro,
    structural_mapping, borrowable_insights, how_to_combine,
    research_directions, risks_and_limits, action_plan.

    This is a slow, LLM-heavy call — it may take 3-4 minutes. Use it only
    when the user wants a thorough analysis, not a quick lookup.

    Args:
        question: The user's original question / problem in natural language.
        phenomenon_id: Target phenomenon id to borrow structure from.
        lang: Output language, "zh" (default) or "en".
    """
    base = get_api_base()
    async with httpx.AsyncClient() as client:
        return await do_analyze(client, base, question, phenomenon_id, lang)


@mcp.tool()
async def find_isomorphism(question: str, lang: str = "zh") -> dict:
    """One-shot: search for the best structural analogue, then analyze it.

    Convenience tool that runs search_isomorphism on the question, picks the
    top-ranked phenomenon, and runs the full analyze_isomorphism report on
    it. Use when the user just wants "find me a structural analogue and
    explain it" without manually choosing a phenomenon id. Slow (3-4 min)
    because it includes the deep analysis step.

    Args:
        question: The user's question / problem in natural language.
        lang: Output language, "zh" (default) or "en".
    """
    base = get_api_base()
    async with httpx.AsyncClient() as client:
        search = await do_search(client, base, question, top_k=8)
        if not search.get("ok"):
            return search
        if search.get("out_of_scope"):
            return _error(
                "out_of_scope",
                search.get("scope_reason") or "Query is out of scope for structural search",
            )
        results = search.get("results") or []
        if not results:
            return _error("no_match", "No structural analogue found for this question")
        best = results[0]
        report = await do_analyze(client, base, question, best["id"], lang)
        if isinstance(report, dict):
            report["matched_phenomenon"] = {
                "id": best.get("id"),
                "name": best.get("name"),
                "domain": best.get("domain"),
                "relevance": best.get("relevance"),
            }
        return report


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
