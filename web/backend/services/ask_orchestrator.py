"""
AskOrchestrator — Perplexity-like 3-phase SSE backend for /api/ask/stream.

Pipeline:
    Phase A: vector-search the cross-domain KB for top-5 cards (~1-2s).
             Emit `meta` → `retrieval_done` → `kb_cards`.
    Phase B: one LLM call (DeepSeek via OpenRouter) returns a JSON object
             {answer, citations, followups}. With STREAMING enabled we
             incrementally extract the `answer` string field as the JSON
             arrives and forward each delta as `answer_chunk` ASAP, so the
             user sees text within ~3-5s instead of waiting 18-32s for the
             whole non-streaming completion. After the stream finishes we
             validate the full JSON with pydantic for citations + followups.
    Phase C: pick top-3 of the same KB cards, derive a one-sentence
             "key_metric" snippet from each card's description, emit
             `similar_phenomena`.
    Finalize: emit `followups` then `done`.

Design notes:
- The LLM is invoked once for answer + citations + followups (per spec).
  Splitting would multiply latency and burn quota.
- W5-B: switched the LLM call from blocking POST to streaming chat
  completions. We use a small JSON-string-extractor state machine to pull
  out the `answer` field characters as they arrive (rather than waiting
  for the closing brace), because OpenRouter's `response_format=json_object`
  guarantees a valid JSON envelope but only at the end of stream.
- On JSON parse / pydantic validation failure we retry exactly once with
  a stricter "JSON-only, no markdown fences" reminder. Second failure
  emits a fallback `answer_done` so the frontend never hangs.
- All output is async-generator of SSE-formatted strings, ready to be
  wired into FastAPI's StreamingResponse.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional, Tuple

from pydantic import ValidationError

from services.ask_schemas import AskAnswerPayload
from services.llm_service import LLMService, _get_http_client, OPENROUTER_URL

logger = logging.getLogger("structural.ask_orchestrator")


***REMOVED*** DeepSeek as the default driver for /ask. The `:nitro` suffix tells
***REMOVED*** OpenRouter to route to the highest-throughput provider available, which
***REMOVED*** cuts time-to-first-token from a 8-25s tail down to ~2-6s (M1.2 fix 1 —
***REMOVED*** first-token latency硬伤). Same model, fastest provider — no answer
***REMOVED*** quality change. Override via env (ASK_LLM_MODEL) to A/B against Claude /
***REMOVED*** Kimi, or drop the suffix to let OpenRouter balance on price.
ASK_MODEL = os.getenv("ASK_LLM_MODEL", "deepseek/deepseek-chat:nitro")

***REMOVED*** How many KB hits to surface to the user as citation candidates.
TOP_K_CARDS = 5
***REMOVED*** How many of those also surface as "similar phenomena" rows below the answer.
TOP_K_SIMILAR = 3
***REMOVED*** Typewriter cadence — emit answer in roughly N-character chunks to keep
***REMOVED*** the network event count modest while still feeling alive.
TYPEWRITER_CHARS_PER_CHUNK = 8
***REMOVED*** Small delay between typewriter chunks so the frontend renders smoothly
***REMOVED*** without buffering the whole stream. Tuned for SSE through nginx.
TYPEWRITER_SLEEP_S = 0.025

***REMOVED*** ---- Out-of-scope rejection guardrail (W5-A) -----------------------------
***REMOVED*** Dogfood report 2026-05-15 (docs/dogfood-ask-2026-05-15.md) caught 3 edge
***REMOVED*** queries (q5 "女朋友为什么生气" / q6 "1+1=?" / q7 "BTC 明天涨跌") where the
***REMOVED*** system硬拗 isomorphism answers despite low retrieval scores. q6 burned
***REMOVED*** 33s producing 494 chars of forced analogy.
***REMOVED***
***REMOVED*** We layer two cheap signals:
***REMOVED***   - top-1 cosine < RELEVANCE_TOP1_MIN  → low relevance
***REMOVED***   - top-3 mean   < RELEVANCE_TOP3_MEAN_MIN → low relevance
***REMOVED***   - empty cards                         → low relevance (trivial)
***REMOVED*** When any signal trips, `stream()` short-circuits (M1.3): it emits a
***REMOVED*** local, honest refusal and skips the LLM call entirely — never硬拗.
***REMOVED***
***REMOVED*** Threshold rationale from dogfood data:
***REMOVED***   q1 (SVB):      top-1=0.94  top-3=0.85+ → above
***REMOVED***   q2 (team):     top-1=1.00  top-3=0.94  → above (false-negative ok; KW hack)
***REMOVED***   q3 (churn):    top-1≈0.92  top-3=0.83  → above
***REMOVED***   q4 (rumor):    top-1=0.93  top-3=0.88  → above
***REMOVED***   q5 (gf):       top-1=0.82  top-3=0.747 → top-3 GATE TRIPS
***REMOVED***   q6 (1+1):     top-1=0.70  top-3=0.597 → BOTH GATES TRIP
***REMOVED***   q7 (BTC):     top-1=0.65  top-3=0.63  → BOTH GATES TRIP
***REMOVED*** Env override knobs let us re-tune in prod without redeploy.
RELEVANCE_TOP1_MIN = float(os.getenv("ASK_RELEVANCE_TOP1_MIN", "0.75"))
RELEVANCE_TOP3_MEAN_MIN = float(os.getenv("ASK_RELEVANCE_TOP3_MEAN_MIN", "0.65"))

***REMOVED*** Session ***REMOVED***16 — forecasting-intent gate (SESSION-15-VERDICT backlog A).
***REMOVED*** Some forecasting queries score high enough to bypass the retrieval gate
***REMOVED*** above (e.g. "AI 能不能预测加密货币" retrieves "科技泡沫" / "投资判断" with
***REMOVED*** decent cosine), yet the intent is the one thing Structural absolutely can
***REMOVED*** not honour: predicting future prices / movements. We add a tiny keyword
***REMOVED*** layer that runs BEFORE the retrieval gate so it short-circuits regardless
***REMOVED*** of score. Two-layer defence: the score gate (probabilistic) + the intent
***REMOVED*** keyword gate (deterministic). Either trip is enough.
***REMOVED***
***REMOVED*** Keep this list short and specific. Over-matching false-positives ("预测"
***REMOVED*** inside "预测临界相变能不能提前预警" — which IS in scope) are avoided by
***REMOVED*** pairing "predict / 预测" with financial-asset markers.
_FORECAST_KEYWORDS_ZH = (
    "预测加密", "预测股", "预测币", "预测涨跌", "预测走势", "预测行情",
    "明天涨", "明天跌", "明天会涨", "明天会跌",
    "下周涨", "下周跌", "下个月涨", "下个月跌",
    "什么时候涨", "什么时候跌",
    "买什么股", "买哪只", "推荐股票", "推荐币", "推荐基金",
    "BTC 明天", "BTC明天", "比特币明天",
    "AI 能不能预测", "ai 能不能预测", "AI能预测", "AI 预测股", "AI预测股",
    "涨到多少", "跌到多少", "目标价",
)
_FORECAST_KEYWORDS_EN = (
    "predict crypto", "predict stock", "predict price",
    "rise tomorrow", "fall tomorrow", "go up tomorrow", "go down tomorrow",
    "rise next week", "fall next week",
    "next week's price", "next month's price",
    "stock pick", "stock picks", "which stock to buy",
    "buy or sell", "buy bitcoin tomorrow", "buy btc tomorrow",
    "price target", "price prediction", "forecast price",
    "can ai predict", "ai predict stock", "ai predict crypto",
)


def _is_forecasting_intent(query: str, lang: str) -> bool:
    """Cheap keyword check for forecasting / price-prediction intent.

    Runs BEFORE the retrieval gate. Returns True iff the query text contains
    a phrase we deterministically refuse (regardless of how well it retrieves).
    Substring match on a lowercased / NFKC-normalised query; deliberately
    permissive — false positives here are cheap (one extra refusal) while
    false negatives are expensive (a hallucinated forecast in prod).
    """
    if not query:
        return False
    q = query.lower().strip()
    kws = _FORECAST_KEYWORDS_EN if lang == "en" else _FORECAST_KEYWORDS_ZH
    return any(k.lower() in q for k in kws)


def _sse(event: str, data: Dict) -> str:
    """Format a single SSE event line."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _AnswerFieldExtractor:
    """Stream-parse the `answer` string field out of a JSON object as bytes arrive.

    The LLM returns one JSON object shaped like
        {"answer": "....", "citations": [...], "followups": [...]}
    With OpenRouter `response_format=json_object` the model is forced to
    produce valid JSON, but it still streams character by character. We want
    to forward each character INSIDE the `answer` string to the user the
    moment it lands, without waiting for the closing `"`.

    State machine (minimal — only what we need):
        SCANNING  → looking for `"answer"` key
        AFTER_KEY → saw the key, looking for `:` then opening `"`
        IN_VALUE  → inside the string literal; every char (handling \\ escapes)
                    gets emitted via feed()'s return value
        DONE      → saw the unescaped closing `"`; no more chars to emit

    Returned chars are already unescaped (\\n → newline, \\" → ", \\uXXXX
    → char, etc.) so the frontend can render them directly.

    NOT a full JSON parser — we deliberately keep this tiny because we
    still parse the complete buffer with `json.loads` at end-of-stream for
    citations + followups validation. This is purely a forwarder.
    """

    SCANNING = 0
    AFTER_KEY = 1
    IN_VALUE = 2
    DONE = 3

    ***REMOVED*** Key we are hunting for, including the closing quote so we don't
    ***REMOVED*** match `"answer_extra"`. We tolerate any whitespace between the key
    ***REMOVED*** close-quote and the colon.
    _KEY = '"answer"'

    def __init__(self) -> None:
        self.state = self.SCANNING
        ***REMOVED*** Rolling buffer used only while SCANNING for `"answer"`. Capped at
        ***REMOVED*** 256 chars so a runaway preamble can't blow memory.
        self._scan_tail = ""
        ***REMOVED*** Pending escape sequence handler — set when we hit `\` inside the
        ***REMOVED*** string. Forms: "esc" (next single-char escape) | "uXXXX" partial.
        self._pending_esc: Optional[str] = None

    def feed(self, chunk: str) -> str:
        """Push a chunk of raw JSON text. Return any newly-emittable answer chars."""
        out_parts: List[str] = []
        for ch in chunk:
            piece = self._step(ch)
            if piece:
                out_parts.append(piece)
            if self.state == self.DONE:
                ***REMOVED*** Drop the rest of the chunk — caller will keep feeding
                ***REMOVED*** for the buffer copy but we don't emit anything more.
                break
        return "".join(out_parts)

    def _step(self, ch: str) -> str:  ***REMOVED*** noqa: C901  (state machine reads cleaner inline)
        if self.state == self.SCANNING:
            self._scan_tail = (self._scan_tail + ch)[-len(self._KEY):]
            if self._scan_tail == self._KEY:
                self.state = self.AFTER_KEY
            return ""

        if self.state == self.AFTER_KEY:
            ***REMOVED*** Look for `:` then the opening `"`. Skip whitespace between.
            if ch == '"':
                self.state = self.IN_VALUE
            ***REMOVED*** Any non-whitespace, non-`:`, non-`"` char here means the
            ***REMOVED*** response shape is off-spec; we let the full json.loads at
            ***REMOVED*** end-of-stream report it. Stay AFTER_KEY in case it normalizes.
            return ""

        if self.state == self.IN_VALUE:
            ***REMOVED*** Handle pending escape from previous char.
            if self._pending_esc is not None:
                return self._consume_escape(ch)
            if ch == "\\":
                self._pending_esc = "esc"
                return ""
            if ch == '"':
                ***REMOVED*** Unescaped closing quote → end of answer string value.
                self.state = self.DONE
                return ""
            return ch

        ***REMOVED*** DONE — ignore everything else.
        return ""

    def _consume_escape(self, ch: str) -> str:
        """Handle the char immediately following a `\\` inside the string."""
        pending = self._pending_esc or ""
        if pending == "esc":
            simple = {
                '"': '"',
                "\\": "\\",
                "/": "/",
                "b": "\b",
                "f": "\f",
                "n": "\n",
                "r": "\r",
                "t": "\t",
            }
            if ch in simple:
                self._pending_esc = None
                return simple[ch]
            if ch == "u":
                ***REMOVED*** Expect 4 hex digits to follow.
                self._pending_esc = "u"
                return ""
            ***REMOVED*** Unknown escape — drop the backslash, keep the char.
            self._pending_esc = None
            return ch
        if pending.startswith("u"):
            ***REMOVED*** Accumulate up to 4 hex digits.
            buf = pending + ch
            if len(buf) >= 5:  ***REMOVED*** "u" + 4 digits
                hex_digits = buf[1:5]
                try:
                    self._pending_esc = None
                    return chr(int(hex_digits, 16))
                except ValueError:
                    self._pending_esc = None
                    return ""  ***REMOVED*** malformed → silently drop
            self._pending_esc = buf
            return ""
        ***REMOVED*** Unknown pending state — reset.
        self._pending_esc = None
        return ch


def _safe_snippet(description: str, max_len: int = 140) -> str:
    """Pick the first sentence-ish slice of the KB description as a metric label.

    We strip newlines and clip on the first 句号 / period / semicolon so the
    "similar_phenomena" payload reads like a single bullet line rather
    than a wall of text. Falls back to truncation if no terminator hit.
    """
    if not description:
        return ""
    text = description.replace("\n", " ").strip()
    ***REMOVED*** Try to cut at the first natural sentence boundary, EN or ZH.
    for sep in ("。", "；", ". ", "; "):
        i = text.find(sep)
        if 0 < i < max_len:
            return text[: i + 1].strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


class AskOrchestrator:
    """Stateless per-request orchestrator. Reuses the global httpx client
    via LLMService._get_http_client(), so instantiation is cheap."""

    def __init__(
        self,
        search_service,
        llm: Optional[LLMService] = None,
        model: Optional[str] = None,
    ) -> None:
        self.search = search_service
        self.llm = llm or LLMService()
        self.model = model or ASK_MODEL

    ***REMOVED*** ------------------------------------------------------------------ ***REMOVED***
    ***REMOVED*** Public entry — async generator yielding SSE-formatted strings.
    ***REMOVED*** ------------------------------------------------------------------ ***REMOVED***

    async def stream(self, query: str, lang: str = "zh") -> AsyncIterator[str]:
        """Run the full 3-phase pipeline. Caller is FastAPI StreamingResponse."""
        started = time.monotonic()
        started_iso = _now_iso()
        lang_norm = (lang or "zh").lower()
        if lang_norm not in ("zh", "en"):
            lang_norm = "zh"

        ***REMOVED*** ---- Phase A: vector search ---------------------------------- ***REMOVED***
        ***REMOVED*** We don't currently invoke the LLM rewrite gate here — the /ask
        ***REMOVED*** surface is a single-box Perplexity-style flow, so we keep the
        ***REMOVED*** user's query verbatim to minimize latency.
        rewritten = query
        yield _sse("meta", {
            "query": query,
            "rewritten": rewritten,
            "started_at": started_iso,
            "model": self.model,
            "lang": lang_norm,
        })

        cards: List[Dict] = []
        retrieval_started = time.monotonic()
        try:
            if self.search is not None:
                cards = self.search.search(query, top_k=TOP_K_CARDS) or []
        except Exception as e:
            logger.warning(f"[ask] vector search failed: {e}")
            cards = []
        retrieval_ms = int((time.monotonic() - retrieval_started) * 1000)

        ***REMOVED*** Always emit the kb_cards event (possibly empty) so the frontend
        ***REMOVED*** can transition from "searching" to "ready". Cards keep only the
        ***REMOVED*** display-safe fields; descriptions stay short.
        cards_payload = [
            {
                "id": c.get("id", ""),
                "name": c.get("name", ""),
                "domain": c.get("domain", ""),
                "type_id": c.get("type_id", ""),
                "score": c.get("score", 0.0),
                "description": (c.get("description") or "")[:240],
            }
            for c in cards
        ]
        ***REMOVED*** W5-B: explicit `retrieval_done` event marking the user-visible
        ***REMOVED*** transition from "搜索中…" to "找到 N 篇 → 正在生成"。Frontend
        ***REMOVED*** paints citation placeholder cards on this event so the user has
        ***REMOVED*** a concrete signal well before the LLM produces its first token.
        ***REMOVED*** Kept alongside the legacy `kb_cards` event so older clients keep
        ***REMOVED*** working without change.
        yield _sse("retrieval_done", {
            "count": len(cards_payload),
            "retrieval_ms": retrieval_ms,
            ***REMOVED*** Lightweight precis — name + domain + idx so a citation card
            ***REMOVED*** placeholder can render. Full descriptions still go via the
            ***REMOVED*** subsequent kb_cards event.
            "candidates": [
                {
                    "idx": i + 1,
                    "id": c.get("id", ""),
                    "name": c.get("name", ""),
                    "domain": c.get("domain", ""),
                    "score": c.get("score", 0.0),
                }
                for i, c in enumerate(cards_payload)
            ],
        })
        yield _sse("kb_cards", {"cards": cards_payload, "count": len(cards_payload)})

        ***REMOVED*** ---- Relevance gate → out-of-scope refusal (W5-A → M1.3) ----- ***REMOVED***
        ***REMOVED*** Inspect the retrieval scores. If the query is clearly outside
        ***REMOVED*** the KB's coverage we SHORT-CIRCUIT here: emit a local, honest
        ***REMOVED*** refusal and never call the LLM. The relevance gate has always
        ***REMOVED*** been an accurate detector; M1.3 adds the missing execution
        ***REMOVED*** branch that actually acts on it. Pre-M1.3 the flag was only a
        ***REMOVED*** soft hint fed into the prompt, so an out-of-scope query still
        ***REMOVED*** burned a full 18-32s LLM call (dogfood q6 "1+1=?" → 33s of
        ***REMOVED*** forced analogy). Refusing locally drops that to ~1-3s and kills
        ***REMOVED*** the "硬拗类比" failure mode outright — a code-layer guardrail
        ***REMOVED*** per the global "不信任 LLM 输出" rule.
        ***REMOVED*** Two-layer scope gate (session ***REMOVED***16):
        ***REMOVED***   (1) forecasting-intent keyword gate — deterministic, runs first
        ***REMOVED***   (2) retrieval-score gate — probabilistic, runs second
        ***REMOVED*** Either trip refuses. The intent gate catches the "AI 能不能预测股票"
        ***REMOVED*** class of query that retrieves OK but is the one thing we must not
        ***REMOVED*** answer.
        if _is_forecasting_intent(query, lang_norm):
            low_relevance, relevance_reason = True, "forecasting_intent"
        else:
            low_relevance, relevance_reason = self._evaluate_relevance(cards)
        if low_relevance:
            logger.info(
                "[ask] low-relevance query refused locally; "
                f"reason={relevance_reason} "
                f"top1={(cards[0].get('score') if cards else None)}"
            )
            refusal = self._build_refusal_payload(
                query, cards, lang_norm, relevance_reason,
            )
            refusal_text = refusal["answer"]
            for chunk in self._typewriter_chunks(refusal_text):
                yield _sse("answer_chunk", {"delta": chunk})
                if TYPEWRITER_SLEEP_S > 0:
                    await asyncio.sleep(TYPEWRITER_SLEEP_S)
            yield _sse("answer_done", {
                "full_text": refusal_text,
                "citations": [],
                "out_of_scope": True,
                "scope_reason": relevance_reason,
                ***REMOVED*** `refused` marks a hard local refusal (no LLM call) so the
                ***REMOVED*** frontend / analytics can tell it apart from the legacy
                ***REMOVED*** soft `out_of_scope` flag.
                "refused": True,
            })
            ***REMOVED*** No "similar phenomena": the gate already decided the
            ***REMOVED*** retrieved cards aren't genuinely related, so surfacing them
            ***REMOVED*** would contradict the refusal text.
            yield _sse("similar_phenomena", {"phenomena": []})
            yield _sse("followups", {"questions": refusal["followups"]})
            refusal_latency_ms = int((time.monotonic() - started) * 1000)
            try:
                from logging_config import get_logger as _glog

                _glog("structural.ask").info(
                    "ask.response",
                    latency_ms=refusal_latency_ms,
                    citation_count=0,
                    out_of_scope=True,
                    refused=True,
                )
            except Exception:
                pass
            yield _sse("done", {"latency_ms": refusal_latency_ms})
            return

        ***REMOVED*** ---- Phase B: LLM synthesize answer + citations + followups -- ***REMOVED***
        ***REMOVED*** Reached only for in-scope queries — out-of-scope ones were
        ***REMOVED*** refused above (M1.3) without ever calling the LLM.
        ***REMOVED*** W14-D: structured `ask.llm.start` log line — model + retrieval
        ***REMOVED*** count so a single grep on `request_id` reconstructs the whole
        ***REMOVED*** pipeline timeline.
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.llm.start",
                model=self.model,
                kb_count=len(cards_payload),
            )
        except Exception:
            pass
        ***REMOVED*** M1.2 fix 4: tell the frontend the LLM call is starting so its
        ***REMOVED*** progress indicator can advance — closes the perceived "black
        ***REMOVED*** screen" gap between `retrieval_done` and the first `answer_chunk`.
        yield _sse("llm_start", {
            "model": self.model,
            "kb_count": len(cards_payload),
        })
        llm_started = time.monotonic()
        payload: Dict
        raw_buffer = ""
        first_chunk_sent = False
        try:
            async for kind, value in self._stream_llm_answer_with_retry(
                query, cards, lang_norm,
            ):
                if kind == "answer_delta":
                    if value:
                        if not first_chunk_sent:
                            first_chunk_sent = True
                            logger.info(
                                "[ask] first answer chunk emitted at %dms",
                                int((time.monotonic() - started) * 1000),
                            )
                        yield _sse("answer_chunk", {"delta": value})
                elif kind == "raw_chunk":
                    raw_buffer += value
                elif kind == "done":
                    payload = value
                    break
            else:
                payload = self._fallback_payload(query, cards, lang_norm)
        except Exception as e:
            logger.error(f"[ask] streaming LLM pipeline failed: {e}")
            payload = self._fallback_payload(query, cards, lang_norm)

        answer_text = payload.get("answer", "") if payload else ""

        ***REMOVED*** W14-D: structured `ask.llm.complete` event. We don't have token
        ***REMOVED*** counts in-band (the SSE stream doesn't surface them), so latency
        ***REMOVED*** + answer length is the best proxy until we plumb token usage
        ***REMOVED*** through llm_service.
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.llm.complete",
                latency_ms=int((time.monotonic() - llm_started) * 1000),
                answer_len=len(answer_text),
            )
        except Exception:
            pass

        ***REMOVED*** If we never streamed any answer chars (e.g. fallback path, or the
        ***REMOVED*** JSON-string-extractor never matched `"answer"` because the model
        ***REMOVED*** produced a wonky envelope), fall back to one typewriter pass so
        ***REMOVED*** the frontend isn't stuck on its "正在思考..." placeholder.
        if not first_chunk_sent and answer_text:
            for chunk in self._typewriter_chunks(answer_text):
                yield _sse("answer_chunk", {"delta": chunk})
                if TYPEWRITER_SLEEP_S > 0:
                    await asyncio.sleep(TYPEWRITER_SLEEP_S)

        ***REMOVED*** Sanitize citations against the actual cards range so a
        ***REMOVED*** hallucinated idx never leaks to the frontend.
        validated_citations = self._validate_citations(payload.get("citations", []), cards)
        ***REMOVED*** In-scope path only — out-of-scope queries were refused above and
        ***REMOVED*** returned (M1.3), so `answer_done` here never carries out_of_scope.
        yield _sse("answer_done", {
            "full_text": answer_text,
            "citations": validated_citations,
        })

        ***REMOVED*** ---- Phase C: similar phenomena ------------------------------ ***REMOVED***
        similar = self._build_similar_phenomena(cards[:TOP_K_SIMILAR])
        yield _sse("similar_phenomena", {"phenomena": similar})

        ***REMOVED*** ---- Followups ----------------------------------------------- ***REMOVED***
        followups = list(payload.get("followups", []))[:3] if payload else []
        ***REMOVED*** Pad/trim defensively — schema requires >=2, but a fallback path
        ***REMOVED*** might pass empty. Surface at most 3, drop blanks.
        followups = [q.strip() for q in followups if isinstance(q, str) and q.strip()][:3]
        yield _sse("followups", {"questions": followups})

        ***REMOVED*** ---- Done ---------------------------------------------------- ***REMOVED***
        latency_ms = int((time.monotonic() - started) * 1000)
        ***REMOVED*** W14-D: emit final `ask.response` event so a single grep on the
        ***REMOVED*** request_id reconstructs full lifecycle (request → retrieval →
        ***REMOVED*** llm.start → llm.complete → response).
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.response",
                latency_ms=latency_ms,
                citation_count=len(validated_citations),
                out_of_scope=False,
            )
        except Exception:
            pass
        yield _sse("done", {"latency_ms": latency_ms})

    ***REMOVED*** ------------------------------------------------------------------ ***REMOVED***
    ***REMOVED*** Internals
    ***REMOVED*** ------------------------------------------------------------------ ***REMOVED***

    def _typewriter_chunks(self, text: str) -> List[str]:
        """Split the answer into N-character chunks for typewriter effect.

        Pure-function so the test path can call it without awaiting.
        """
        if not text:
            return []
        step = max(1, TYPEWRITER_CHARS_PER_CHUNK)
        return [text[i : i + step] for i in range(0, len(text), step)]

    def _validate_citations(self, raw_citations: List[Dict], cards: List[Dict]) -> List[Dict]:
        """Drop citations whose idx is out of range and rewrite kb_id from cards.

        The LLM sometimes invents kb_ids; we trust only the idx as the
        spine of the citation, and look up the canonical kb_id from the
        cards list we ourselves built. Out-of-range idx → dropped.
        """
        out: List[Dict] = []
        seen_idx = set()
        max_idx = len(cards)
        for c in raw_citations:
            try:
                idx = int(c.get("idx"))
            except (TypeError, ValueError):
                continue
            if idx < 1 or idx > max_idx or idx in seen_idx:
                continue
            seen_idx.add(idx)
            canonical = cards[idx - 1]
            out.append({
                "idx": idx,
                "kb_id": canonical.get("id", ""),
                "label": str(c.get("label") or canonical.get("name") or "")[:200],
            })
        return out

    def _build_similar_phenomena(self, cards: List[Dict]) -> List[Dict]:
        """Project the top-N cards into the `similar_phenomena` shape.

        `key_metric` is a one-line summary derived from the KB description.
        Per spec, "metric 可以从现有 v4/results/ 或 KB 数据中取，简化：
        直接从 KB 现象数据的 description 字段提取一句概括，不一定要精确数字".
        """
        out: List[Dict] = []
        for c in cards:
            desc = c.get("description") or ""
            out.append({
                "name": c.get("name", ""),
                "domain": c.get("domain", ""),
                "key_metric": _safe_snippet(desc, max_len=140),
                "kb_id": c.get("id", ""),
                "score": c.get("score", 0.0),
            })
        return out

    ***REMOVED*** ---------------- Relevance gating (W5-A) --------------------------- ***REMOVED***

    def _evaluate_relevance(self, cards: List[Dict]) -> tuple[bool, str]:
        """Decide whether the retrieved KB is too thin to support an answer.

        Returns (low_relevance, reason_label). The reason label is short
        and goes into structured logs; the LLM prompt itself does NOT
        carry the threshold values, only the boolean flag, so we don't
        encourage the model to game scores.

        Three trip conditions (any one is enough):
          - no cards at all
          - top-1 score below RELEVANCE_TOP1_MIN
          - top-3 mean below RELEVANCE_TOP3_MEAN_MIN

        Scores are read from the KB card dicts; missing scores are treated
        as 0.0 so that a misbehaving search backend errs on the safe side
        (degrades to honest decline rather than over-confident hallucination).
        """
        if not cards:
            return True, "no_cards"

        def _score(c: Dict) -> float:
            try:
                return float(c.get("score") or 0.0)
            except (TypeError, ValueError):
                return 0.0

        top1 = _score(cards[0])
        if top1 < RELEVANCE_TOP1_MIN:
            return True, f"top1_below_{RELEVANCE_TOP1_MIN}"

        top3 = cards[:3]
        if len(top3) >= 1:
            mean3 = sum(_score(c) for c in top3) / len(top3)
            if mean3 < RELEVANCE_TOP3_MEAN_MIN:
                return True, f"top3_mean_below_{RELEVANCE_TOP3_MEAN_MIN}"

        return False, "ok"

    ***REMOVED*** ---------------- LLM call + retry --------------------------------- ***REMOVED***

    async def _llm_answer_with_retry(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
    ) -> Dict:
        """One LLM call; on failure retry once with a stricter reminder.

        Returns a dict {answer, citations, followups}. On total failure
        returns a graceful fallback so the SSE stream can still complete.

        Kept for backward compatibility / non-streaming code paths (tests
        currently still drive this via `_call_llm_once` mocks). The hot
        path in `stream()` uses `_stream_llm_answer_with_retry` instead.
        """
        ***REMOVED*** First attempt — normal prompt.
        prompt = self._build_prompt(query, cards, lang, strict_json=False)
        result = await self._call_llm_once(prompt)
        validated = self._try_validate(result)
        if validated is not None:
            return validated

        ***REMOVED*** Retry once with a stricter "JSON only, no markdown fences" note.
        logger.warning("[ask] first LLM JSON validate failed; retrying once")
        prompt2 = self._build_prompt(query, cards, lang, strict_json=True)
        result2 = await self._call_llm_once(prompt2)
        validated2 = self._try_validate(result2)
        if validated2 is not None:
            return validated2

        logger.error("[ask] LLM JSON validate failed twice; emitting fallback")
        return self._fallback_payload(query, cards, lang)

    async def _stream_llm_answer_with_retry(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
    ) -> AsyncIterator[Tuple[str, object]]:
        """Streaming variant — yields tuples driving the SSE pipeline.

        Yield protocol:
            ("answer_delta", str)  → newly-emittable answer-string chars
            ("raw_chunk", str)     → raw JSON chunk (caller may ignore)
            ("done", dict)         → validated/fallback payload at end

        Strategy:
        1. First attempt streams; if the final JSON validates, done.
        2. If first attempt failed validation:
            - If we already streamed answer chars (DONE > IN_VALUE state),
              we KEEP what we sent (don't yank text out of the user's view)
              and use `_try_validate` retry once for citations/followups.
              The retry runs in NON-streaming mode (no further answer_delta).
            - If we never emitted any answer_delta (e.g. envelope malformed
              before the `answer` field arrived), we retry in streaming mode
              with strict_json=True.
        3. After two failures total, yield ("done", fallback).
        """
        ***REMOVED*** ---- Attempt 1: stream + extract --------------------------------
        prompt = self._build_prompt(query, cards, lang, strict_json=False)
        accumulated = ""
        emitted_any = False
        async for kind, value in self._call_llm_stream(prompt):
            if kind == "answer_delta":
                if value:
                    emitted_any = True
                    yield ("answer_delta", value)
            elif kind == "raw_chunk":
                accumulated += value
                yield ("raw_chunk", value)
            elif kind == "error":
                logger.warning(f"[ask] streaming attempt 1 errored: {value}")
                break

        validated = self._try_validate(accumulated)
        if validated is not None:
            yield ("done", validated)
            return

        ***REMOVED*** ---- Attempt 2: depends on whether we already streamed answer ---
        if emitted_any:
            ***REMOVED*** Already showed text to user. Re-call (non-streaming) for a
            ***REMOVED*** second shot at valid citations/followups, but preserve the
            ***REMOVED*** already-emitted answer string by overriding `answer` with
            ***REMOVED*** whatever we managed to accumulate via the extractor.
            logger.warning("[ask] stream JSON validate failed; retry (no re-stream)")
            prompt2 = self._build_prompt(query, cards, lang, strict_json=True)
            result2 = await self._call_llm_once(prompt2)
            validated2 = self._try_validate(result2)
            if validated2 is not None:
                ***REMOVED*** Keep what the user already saw on screen.
                streamed_answer = self._best_effort_extract_answer(accumulated)
                if streamed_answer:
                    validated2 = dict(validated2)
                    validated2["answer"] = streamed_answer
                yield ("done", validated2)
                return
        else:
            ***REMOVED*** Nothing user-visible yet — safe to fully re-stream.
            logger.warning("[ask] stream emitted nothing; retry with strict_json")
            prompt2 = self._build_prompt(query, cards, lang, strict_json=True)
            accumulated2 = ""
            stream2_errored = False
            async for kind, value in self._call_llm_stream(prompt2):
                if kind == "answer_delta":
                    if value:
                        yield ("answer_delta", value)
                elif kind == "raw_chunk":
                    accumulated2 += value
                    yield ("raw_chunk", value)
                elif kind == "error":
                    logger.warning(f"[ask] streaming attempt 2 errored: {value}")
                    stream2_errored = True
                    break
            validated3 = self._try_validate(accumulated2)
            if validated3 is not None:
                yield ("done", validated3)
                return

            ***REMOVED*** Final tier: if streaming failed entirely (e.g. no API key,
            ***REMOVED*** network refused) fall back to the legacy non-streaming
            ***REMOVED*** `_call_llm_once` path. This preserves compatibility with
            ***REMOVED*** mocks that only patch `_call_llm_once` AND keeps prod from
            ***REMOVED*** giving up if the streaming endpoint flakes.
            if stream2_errored or not accumulated2:
                logger.warning("[ask] streaming retry empty; falling back to non-stream")
                try:
                    result3 = await self._call_llm_once(prompt2)
                except Exception as e:
                    logger.error(f"[ask] non-stream fallback failed: {e}")
                    result3 = None
                validated4 = self._try_validate(result3)
                if validated4 is not None:
                    ***REMOVED*** Typewriter emission of the recovered answer so the
                    ***REMOVED*** frontend isn't stuck on its placeholder.
                    answer4 = validated4.get("answer", "")
                    if answer4:
                        for chunk in self._typewriter_chunks(answer4):
                            yield ("answer_delta", chunk)
                    yield ("done", validated4)
                    return

        logger.error("[ask] LLM JSON validate failed twice; emitting fallback")
        yield ("done", self._fallback_payload(query, cards, lang))

    def _best_effort_extract_answer(self, raw: str) -> str:
        """Try to pluck the `answer` field out of a possibly-incomplete JSON.

        Used when attempt 1 emitted answer chars but the full envelope didn't
        validate — we want to keep what the user already saw and merge in
        the retry's citations/followups. Returns "" if nothing extractable.
        """
        if not raw:
            return ""
        text = raw.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                ans = obj.get("answer")
                if isinstance(ans, str):
                    return ans
        except json.JSONDecodeError:
            pass
        ***REMOVED*** Last resort — walk the chars through the extractor to reconstruct.
        ext = _AnswerFieldExtractor()
        return ext.feed(text)

    def _try_validate(self, raw: Optional[str]) -> Optional[Dict]:
        """Parse + pydantic-validate the LLM JSON. None on any failure."""
        if not raw:
            return None
        text = raw.strip()
        ***REMOVED*** Strip stray markdown fences the model occasionally adds.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"[ask] JSON decode failed: {e}; head={text[:200]!r}")
            return None
        try:
            payload = AskAnswerPayload.model_validate(parsed)
        except ValidationError as e:
            logger.warning(f"[ask] pydantic validate failed: {e.errors()[:2]}")
            return None
        ***REMOVED*** Use model_dump so downstream code works with plain dicts.
        return payload.model_dump()

    async def _call_llm_once(self, prompt: str) -> Optional[str]:
        """Single non-streaming chat call to OpenRouter, returns raw content."""
        api_key = self.llm.api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("[ask] no OPENROUTER_API_KEY; cannot call LLM")
            return None
        try:
            client = _get_http_client()
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1800,
                    ***REMOVED*** DeepSeek + OpenRouter both honor response_format on
                    ***REMOVED*** most builds; the strict-mode retry also reminds in
                    ***REMOVED*** the prompt to be JSON-only.
                    "response_format": {"type": "json_object"},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"[ask] LLM call failed: {e}")
            return None

    async def _call_llm_stream(
        self,
        prompt: str,
    ) -> AsyncIterator[Tuple[str, str]]:
        """Streaming chat call to OpenRouter.

        Yields tuples:
            ("answer_delta", str)  — newly-emittable answer field chars
            ("raw_chunk", str)     — raw model-content chunk (drives accumulator)
            ("error", str)         — non-fatal error message; caller falls back

        Implementation mirrors `LLMService.stream_mapping`: POST with
        `stream: True`, iterate `resp.aiter_lines()`, parse `data: <json>`
        OpenAI-style SSE deltas, extract `choices[0].delta.content` and
        push it through `_AnswerFieldExtractor` so we can forward the
        `answer` field characters as soon as they arrive (rather than
        waiting for the closing `}`).
        """
        api_key = self.llm.api_key or os.getenv("OPENROUTER_API_KEY", "")
        if not api_key:
            logger.warning("[ask] no OPENROUTER_API_KEY; cannot call LLM (stream)")
            yield ("error", "no_api_key")
            return

        extractor = _AnswerFieldExtractor()
        try:
            client = _get_http_client()
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1800,
                    "response_format": {"type": "json_object"},
                    "stream": True,
                },
                timeout=120.0,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        ***REMOVED*** OpenRouter occasionally emits non-JSON keepalive
                        ***REMOVED*** comments — skip silently.
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        or ""
                    )
                    if not delta:
                        continue
                    ***REMOVED*** Always forward raw chunk so the caller can accumulate
                    ***REMOVED*** the full JSON for final pydantic validation.
                    yield ("raw_chunk", delta)
                    ***REMOVED*** Extract any answer-field chars unlocked by this delta.
                    emitted = extractor.feed(delta)
                    if emitted:
                        yield ("answer_delta", emitted)
        except Exception as e:
            logger.error(f"[ask] LLM stream failed: {e}")
            yield ("error", str(e))

    def _build_prompt(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
        strict_json: bool,
    ) -> str:
        """Build the single-shot prompt for answer + citations + followups.

        Always the in-scope synthesis prompt: out-of-scope queries are
        refused locally in `stream()` (M1.3) and never reach the LLM, so
        the old `low_relevance` prompt branch was removed as dead code.
        """
        if not cards:
            cards_block = "（无 KB 召回结果，请基于通识尝试回答；citations 字段可填 idx=1 并 kb_id 留空也可以）"
        else:
            lines = []
            for i, c in enumerate(cards, 1):
                name = c.get("name", "")
                domain = c.get("domain", "")
                desc = (c.get("description") or "")[:240]
                lines.append(f"{i}. {name}（{domain}）— {desc}")
            cards_block = "\n".join(lines)

        lang_clause = (
            "请用中文输出 `answer` / `followups` / `citations.label` 三个字段的文字内容。"
            if lang == "zh"
            else "Output answer / followups / citations.label in English. JSON keys stay ASCII."
        )

        strict_block = (
            "\n\n严格要求：只输出一个 JSON 对象，不要 markdown 代码块、不要前言后语。"
            if strict_json
            else ""
        )

        ***REMOVED*** ---- In-scope synthesis prompt --------------------------------
        return f"""你是一个跨学科结构同构搜索引擎。用户问了一个复杂问题，你需要：

1. 基于以下 KB 现象（已 vector 召回，按相似度排序），给出 200-400 字短答案，解释问题的"结构本质"
2. 在答案中用 [1] [2] [3] 标注引用（对应下方 KB 现象的编号）
3. 列出 3 个深入的追问建议（followups），每个 8-30 字，能让用户继续探索

用户问题：
{query}

KB 现象列表（结构相似度排序）：
{cards_block}

{lang_clause}

请输出严格 JSON（schema 如下）：
{{
  "answer": "200-400 字短答案，内含 [1][2] 引用",
  "citations": [
    {{"idx": 1, "kb_id": "对应 KB 现象的 id（从上面列表里取）", "label": "一句话标签，不超过 30 字"}}
  ],
  "followups": ["问题1?", "问题2?", "问题3?"]
}}

要求：
- citations 至少 1 条，最多 10 条；idx 必须是上面 KB 现象列表里的有效编号（1-based）
- followups 必须 2-5 条字符串
- answer 长度 20-2000 字符；包含至少一个 [1] 之类的引用标记{strict_block}"""

    def _build_refusal_payload(
        self, query: str, cards: List[Dict], lang: str, scope_reason: str,
    ) -> Dict:
        """Build an out-of-scope refusal locally — NO LLM call (M1.3).

        Returned shape: {answer, followups}. `citations` is deliberately
        omitted; the refusal path emits an empty citation list because the
        retrieved cards were judged not genuinely relevant.

        Wording adapts to `scope_reason` (from `_evaluate_relevance`):
        `no_cards` means nothing matched at all, while `top1_below_*` /
        `top3_mean_below_*` mean cards exist but score weakly. `followups`
        are 3 demo questions firmly inside the KB's scope (structural
        isomorphism / cascades / phase transitions / network dynamics) so
        the user can pivot productively instead of hitting a dead end.

        `query` / `cards` are accepted for signature parity with
        `_fallback_payload` and possible future tailoring; not used today.
        """
        no_cards = scope_reason == "no_cards"
        forecasting = scope_reason == "forecasting_intent"
        if lang == "en":
            if forecasting:
                answer = (
                    "Structural can't forecast asset prices or market "
                    "movements — that's not a structural-isomorphism question, "
                    "it's a prediction question, and no analytical tool "
                    "(AI or otherwise) reliably solves it. What Structural "
                    "can help with is the *shape* of how shocks propagate: "
                    "cascade dynamics, critical phase transitions, network "
                    "fragility. Re-phrase your question that way and the "
                    "knowledge base will have something useful."
                )
            elif no_cards:
                answer = (
                    "This question doesn't match anything in Structural's "
                    "knowledge base. Structural is built for cross-disciplinary "
                    "structural isomorphism — how earthquakes, bank runs and "
                    "neural avalanches share the same underlying math. For "
                    "calculations, factual lookups or personal questions, a "
                    "more specialised tool will serve you better."
                )
            else:
                answer = (
                    "This question falls outside Structural's knowledge base — "
                    "the retrieved phenomena are only weakly related to it. "
                    "Structural is built for cross-disciplinary structural "
                    "isomorphism, e.g. how earthquakes, bank runs and neural "
                    "avalanches share the same underlying math. A domain-"
                    "specific source or tool would answer this better."
                )
            followups = [
                "Why do bank runs and forest fires spread in structurally similar ways?",
                "Can critical phase transitions be detected before they happen?",
                "How does network topology determine the scale of cascading failures?",
            ]
        else:
            if forecasting:
                answer = (
                    "Structural 不预测资产价格、不预测涨跌——这不是结构同构问题，"
                    "是预测问题，没有任何分析工具（包括 AI）能可靠地做到。"
                    "Structural 能帮的是「冲击如何传播」的结构层面：级联动力学、"
                    "临界相变、网络脆弱性。把问题改写成这个层面（比如「银行挤兑"
                    "的级联机制是什么」、「市场恐慌怎么扩散」），知识库就能给你"
                    "有用的答案。"
                )
            elif no_cards:
                answer = (
                    "这个问题没有匹配到 Structural 知识库里的任何现象。"
                    "Structural 擅长的是跨学科的结构同构——比如地震、银行挤兑、"
                    "神经放电背后共用同一套数学规律。数学计算、事实查询或个人"
                    "生活类的问题，换用更对口的工具会更靠谱。"
                )
            else:
                answer = (
                    "这个问题超出了 Structural 知识库的覆盖范围，检索到的现象"
                    "与它的结构相关性都很弱。Structural 擅长的是跨学科的结构"
                    "同构——比如地震、银行挤兑、神经放电背后共用同一套数学规律。"
                    "这类问题建议换用更对口的工具或学科资源。"
                )
            followups = [
                "为什么银行挤兑和森林大火的蔓延方式如此相似？",
                "临界相变能不能提前预警？地震和股灾有共同的前兆信号吗？",
                "网络拓扑结构如何决定级联失败的规模？",
            ]
        return {"answer": answer, "followups": followups}

    def _fallback_payload(self, query: str, cards: List[Dict], lang: str) -> Dict:
        """Emit a minimum-viable payload when the LLM never produces valid JSON.

        Schema-shaped to satisfy downstream emission code (citation validation,
        followups slicing). The frontend can display this as a degraded state.
        """
        if lang == "en":
            answer = (
                "Sorry — the cross-domain synthesizer is temporarily unavailable. "
                f"Your question was: “{query[:120]}”. "
                "Try refining the wording or pick one of the related phenomena below."
            )
            followups = [
                "What time scale does this play out on?",
                "Which discipline has the most mature toolkit for this?",
                "Where would this analogy break down?",
            ]
        else:
            answer = (
                "抱歉，跨领域结构同构合成器暂时不可用。"
                f"你的问题是：「{query[:120]}」。"
                "可以尝试缩窄描述，或直接点击下方的相关现象查看类比线索。"
            )
            followups = [
                "这个现象通常在什么时间尺度上展开？",
                "哪个学科对它有最成熟的分析工具？",
                "在什么边界条件下这种类比会失效？",
            ]
        ***REMOVED*** Build a single citation pointing at card 1 if any cards exist.
        if cards:
            citations = [{
                "idx": 1,
                "kb_id": cards[0].get("id", ""),
                "label": cards[0].get("name", "") or "related phenomenon",
            }]
        else:
            citations = [{"idx": 1, "kb_id": "", "label": "fallback"}]
        return {
            "answer": answer,
            "citations": citations,
            "followups": followups,
        }
