#!/usr/bin/env python3
"""Dogfood /api/ask/stream on prod with 7 real queries.

Categories:
  1. Cross-domain isomorphism classics (should score high)
  2. Business / product scenarios (mid)
  3. Edge / adversarial (should refuse gracefully, not hallucinate)

SSE format used by this backend (verified 2026-05-14):

    event: meta\n
    data: {...}\n
    \n
    event: kb_cards\n
    data: {"cards": [...]}\n
    \n
    event: answer_chunk\n
    data: {"delta": "..."}\n
    (many of these)
    event: answer_done\n
    data: {"full_text": "..."}\n
    event: similar_phenomena\n
    data: {"phenomena": [...]}\n
    event: followups\n
    data: {"questions": [...]}\n
    event: done\n
    data: {"latency_ms": N}\n

Output:
  docs/dogfood-ask-2026-05-15.json  -- structured per-query results
"""
from __future__ import annotations

import json
import pathlib
import time

import requests

PROD_URL = "https://beta.structural.bytedance.city/api/ask/stream"

QUERIES = [
    # Class 1: cross-domain isomorphism classics
    {
        "id": "q1",
        "category": "cross-domain",
        "text": "为什么硅谷银行挤兑后市场反应这么剧烈？还有哪些类似的级联系统？",
    },
    {
        "id": "q2",
        "category": "cross-domain",
        "text": "团队氛围崩了之后为什么很难恢复？跟相变有关系吗？",
    },
    # Class 2: business / product
    {
        "id": "q3",
        "category": "business",
        "text": "月活用户每月按固定比率掉 7%，怎么看怎么干预？",
    },
    {
        "id": "q4",
        "category": "business",
        "text": "为什么有些谣言会爆，另一些悄悄消散？区别在哪？",
    },
    # Class 3: edge / adversarial
    {
        "id": "q5",
        "category": "edge-irrelevant",
        "text": "我女朋友为什么生气了？",
    },
    {
        "id": "q6",
        "category": "edge-trivial",
        "text": "求 1+1 = ?",
    },
    {
        "id": "q7",
        "category": "edge-prediction",
        "text": "Bitcoin 明天涨还是跌？",
    },
]


def stream_sse(lines):
    """Yield (event_name, data_dict) pairs from an SSE iterator."""
    current_event: str | None = None
    for raw in lines:
        if raw is None:
            continue
        line = raw.rstrip("\r")
        if not line:
            current_event = None
            continue
        if line.startswith("event:"):
            current_event = line[len("event:"):].strip()
            continue
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = {"_raw": payload, "_parse_error": True}
            yield current_event or "?", data


def run_query(q: dict) -> dict:
    payload = {"query": q["text"], "lang": "zh"}
    start = time.time()
    first_byte: float | None = None
    first_answer_chunk: float | None = None
    answer_done_at: float | None = None

    events: list[tuple[str, dict]] = []
    status_code: int | None = None
    error: str | None = None

    try:
        with requests.post(
            PROD_URL,
            json=payload,
            stream=True,
            timeout=120,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            status_code = resp.status_code
            if resp.status_code != 200:
                error = f"HTTP {resp.status_code}: {resp.text[:500]}"
                return {
                    "id": q["id"],
                    "query": q["text"],
                    "category": q["category"],
                    "status_code": status_code,
                    "error": error,
                    "duration_sec": round(time.time() - start, 2),
                }
            lines_iter = resp.iter_lines(decode_unicode=True)
            for evt_name, data in stream_sse(lines_iter):
                now = time.time() - start
                if first_byte is None:
                    first_byte = now
                if evt_name == "answer_chunk" and first_answer_chunk is None:
                    first_answer_chunk = now
                if evt_name == "answer_done":
                    answer_done_at = now
                events.append((evt_name, data))
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    duration = time.time() - start

    # Aggregate by event type
    type_counts: dict[str, int] = {}
    answer_chunks: list[str] = []
    full_text: str = ""
    kb_cards: list[dict] = []
    similar: list[dict] = []
    followups: list[str] = []
    meta: dict = {}
    done_meta: dict = {}

    for name, data in events:
        type_counts[name] = type_counts.get(name, 0) + 1
        if name == "meta":
            meta = data
        elif name == "kb_cards":
            cards = data.get("cards") if isinstance(data, dict) else None
            if isinstance(cards, list):
                kb_cards = cards
        elif name == "answer_chunk":
            d = data.get("delta") if isinstance(data, dict) else None
            if d:
                answer_chunks.append(str(d))
        elif name == "answer_done":
            full_text = data.get("full_text", "") if isinstance(data, dict) else ""
        elif name == "similar_phenomena":
            ph = data.get("phenomena") if isinstance(data, dict) else None
            if isinstance(ph, list):
                similar = ph
        elif name == "followups":
            qs = data.get("questions") if isinstance(data, dict) else None
            if isinstance(qs, list):
                followups = qs
        elif name == "done":
            done_meta = data

    answer_text = full_text or "".join(answer_chunks)

    return {
        "id": q["id"],
        "query": q["text"],
        "category": q["category"],
        "status_code": status_code,
        "error": error,
        "duration_sec": round(duration, 2),
        "first_byte_sec": round(first_byte, 2) if first_byte else None,
        "first_answer_chunk_sec": round(first_answer_chunk, 2) if first_answer_chunk else None,
        "answer_done_sec": round(answer_done_at, 2) if answer_done_at else None,
        "server_latency_ms": done_meta.get("latency_ms"),
        "model": meta.get("model"),
        "event_type_counts": type_counts,
        "n_events": len(events),
        "n_kb_cards": len(kb_cards),
        "n_answer_chunks": len(answer_chunks),
        "answer_text_len": len(answer_text),
        "n_similar_phenomena": len(similar),
        "n_followups": len(followups),
        "answer_text": answer_text,
        "kb_cards": kb_cards,
        "similar_phenomena": similar,
        "followups": followups,
        "meta": meta,
    }


def main() -> None:
    out_path = pathlib.Path("docs/dogfood-ask-2026-05-15.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for q in QUERIES:
        print(f"[run] {q['id']} {q['category']} :: {q['text'][:50]}...", flush=True)
        result = run_query(q)
        print(
            f"  -> status={result.get('status_code')} dur={result.get('duration_sec')}s "
            f"answer_len={result.get('answer_text_len')} kb={result.get('n_kb_cards')} "
            f"sim={result.get('n_similar_phenomena')} fup={result.get('n_followups')} "
            f"err={result.get('error')}",
            flush=True,
        )
        results.append(result)
        time.sleep(2)  # be nice to prod rate limit (5/min anon)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"Wrote {out_path} ({len(results)} results)")


if __name__ == "__main__":
    main()
