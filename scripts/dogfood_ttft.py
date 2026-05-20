***REMOVED***!/usr/bin/env python3
"""Session ***REMOVED***15 M1.2/M1.3 dogfood — measure TTFT (time to first answer_chunk)
and verify out-of-scope queries hit the local-refusal short-circuit.

Usage:
    python3 scripts/dogfood_ttft.py [--host https://beta.structural.bytedance.city]

7 queries (4 in-scope / 3 out-of-scope). For each:
  * Record time from POST to first `answer_chunk` event (TTFT, in-scope only)
  * Record time to `answer_done` (full response)
  * Record `out_of_scope` flag in answer_done payload
  * Record whether `llm_start` was emitted (M1.2 fix4 verification)

Output: table to stdout + machine-readable JSON to docs/sessions/session-15-ttft.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

QUERIES = [
    ***REMOVED*** in-scope (q1-q4): expected to retrieve KB cards + run LLM
    ("q1", "in_scope", "SVB 怎么倒的"),
    ("q2", "in_scope", "团队为什么散"),
    ("q3", "in_scope", "用户流失原因"),
    ("q4", "in_scope", "传言怎么扩散"),
    ***REMOVED*** out-of-scope (q5-q7): expected to short-circuit with refusal
    ("q5", "out_of_scope", "女朋友为什么生气"),
    ("q6", "out_of_scope", "1+1=?"),
    ("q7", "out_of_scope", "BTC 明天涨跌"),
]


def parse_sse_event(buffer: str) -> tuple[str | None, str | None, str]:
    """Split off first complete SSE event from buffer.

    Returns (event_name, data_json, remaining_buffer). If no complete event,
    returns (None, None, buffer).
    """
    sep = buffer.find("\n\n")
    if sep < 0:
        return None, None, buffer
    block, rest = buffer[:sep], buffer[sep + 2:]
    event_name = None
    data_lines: list[str] = []
    for line in block.split("\n"):
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    return event_name, "\n".join(data_lines) if data_lines else None, rest


def probe_one(host: str, qid: str, expected: str, query: str) -> dict[str, Any]:
    """Stream /api/ask/stream and record timing milestones."""
    url = f"{host}/api/ask/stream"
    payload = {"query": query, "lang": "zh"}
    result: dict[str, Any] = {
        "qid": qid,
        "expected": expected,
        "query": query,
        "ttft_s": None,
        "t_answer_done_s": None,
        "events_seen": [],
        "out_of_scope": None,
        "scope_reason": None,
        "llm_start_seen": False,
        "error": None,
    }
    t0 = time.monotonic()
    try:
        with httpx.stream("POST", url, json=payload, timeout=60.0) as r:
            if r.status_code != 200:
                result["error"] = f"HTTP {r.status_code}: {r.read().decode()[:200]}"
                return result
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while True:
                    event, data, buf = parse_sse_event(buf)
                    if event is None:
                        break
                    result["events_seen"].append(event)
                    if event == "answer_chunk" and result["ttft_s"] is None:
                        result["ttft_s"] = round(time.monotonic() - t0, 3)
                    elif event == "llm_start":
                        result["llm_start_seen"] = True
                    elif event == "answer_done":
                        result["t_answer_done_s"] = round(time.monotonic() - t0, 3)
                        if data:
                            try:
                                payload_obj = json.loads(data)
                                result["out_of_scope"] = payload_obj.get("out_of_scope")
                                result["scope_reason"] = payload_obj.get("scope_reason")
                            except json.JSONDecodeError:
                                pass
                if result["t_answer_done_s"] is not None:
                    break
    except Exception as exc:  ***REMOVED*** noqa: BLE001 — top-level probe guard
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="https://beta.structural.bytedance.city")
    parser.add_argument("--out", default="docs/sessions/session-15-ttft.json")
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    for qid, expected, query in QUERIES:
        print(f"[{qid}] {expected:13s} '{query}' ...", flush=True)
        r = probe_one(args.host, qid, expected, query)
        results.append(r)
        if r["error"]:
            print(f"  ✗ ERROR: {r['error']}")
        else:
            ttft = f"{r['ttft_s']}s" if r["ttft_s"] is not None else "—"
            done = f"{r['t_answer_done_s']}s" if r["t_answer_done_s"] is not None else "—"
            oos = r["out_of_scope"]
            llm = "Y" if r["llm_start_seen"] else "N"
            print(
                f"  TTFT={ttft:8s} done={done:8s} out_of_scope={oos} llm_start={llm}"
                f" events={','.join(r['events_seen'])}"
            )

    ***REMOVED*** Summary table
    print("\n" + "=" * 72)
    print(f"{'qid':4s} {'expected':14s} {'TTFT':>9s} {'done':>9s} {'OOS':>5s} {'llm':>4s}  query")
    print("-" * 72)
    for r in results:
        ttft = f"{r['ttft_s']}s" if r["ttft_s"] is not None else "—"
        done = f"{r['t_answer_done_s']}s" if r["t_answer_done_s"] is not None else "—"
        oos = str(r["out_of_scope"])
        llm = "Y" if r["llm_start_seen"] else "N"
        print(f"{r['qid']:4s} {r['expected']:14s} {ttft:>9s} {done:>9s} {oos:>5s} {llm:>4s}  {r['query']}")

    ***REMOVED*** Persist JSON
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nJSON: {out_path}")

    ***REMOVED*** Verdict per M1 spec
    in_scope = [r for r in results if r["expected"] == "in_scope"]
    out_of_scope_qs = [r for r in results if r["expected"] == "out_of_scope"]
    in_scope_ttfts = [r["ttft_s"] for r in in_scope if r["ttft_s"] is not None]
    refused_correctly = [r for r in out_of_scope_qs if r["out_of_scope"] is True]

    print("\nVerdict:")
    if in_scope_ttfts:
        print(f"  in-scope TTFT: min={min(in_scope_ttfts)}s max={max(in_scope_ttfts)}s "
              f"avg={round(sum(in_scope_ttfts) / len(in_scope_ttfts), 2)}s")
        if max(in_scope_ttfts) <= 6.0:
            print("  ✓ in-scope ≤6s clean — skip M1.2 Fix2/3, proceed to M1.4")
        elif max(in_scope_ttfts) > 10.0:
            print("  ✗ in-scope >10s long tail — start M1.2 Fix2 (drop json_object) + Fix3 (prompt slim)")
        else:
            print("  ~ in-scope 6-10s borderline — judgement call")
    print(f"  out-of-scope refusals: {len(refused_correctly)}/{len(out_of_scope_qs)}")
    if len(refused_correctly) < len(out_of_scope_qs):
        print("  ✗ some out-of-scope queries leaked through — tune ASK_RELEVANCE_TOP1_MIN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
