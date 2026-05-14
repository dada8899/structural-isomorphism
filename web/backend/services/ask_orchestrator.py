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


# DeepSeek as the default driver for /ask. Spec D-renai-10 tagged DeepSeek
# as the temporary fast/cheap default for high-volume synthesis flows.
# Override via env when we want to A/B against Claude / Kimi.
ASK_MODEL = os.getenv("ASK_LLM_MODEL", "deepseek/deepseek-chat")

# How many KB hits to surface to the user as citation candidates.
TOP_K_CARDS = 5
# How many of those also surface as "similar phenomena" rows below the answer.
TOP_K_SIMILAR = 3
# Typewriter cadence — emit answer in roughly N-character chunks to keep
# the network event count modest while still feeling alive.
TYPEWRITER_CHARS_PER_CHUNK = 8
# Small delay between typewriter chunks so the frontend renders smoothly
# without buffering the whole stream. Tuned for SSE through nginx.
TYPEWRITER_SLEEP_S = 0.025

# ---- Out-of-scope rejection guardrail (W5-A) -----------------------------
# Dogfood report 2026-05-15 (docs/dogfood-ask-2026-05-15.md) caught 3 edge
# queries (q5 "女朋友为什么生气" / q6 "1+1=?" / q7 "BTC 明天涨跌") where the
# system硬拗 isomorphism answers despite low retrieval scores. q6 burned
# 33s producing 494 chars of forced analogy.
#
# We layer two cheap signals:
#   - top-1 cosine < RELEVANCE_TOP1_MIN  → low relevance
#   - top-3 mean   < RELEVANCE_TOP3_MEAN_MIN → low relevance
#   - empty cards                         → low relevance (trivial)
# A "low_relevance" flag is then injected into the LLM prompt so the model
# can degrade gracefully (decline + redirect) instead of forcing an answer.
#
# Threshold rationale from dogfood data:
#   q1 (SVB):      top-1=0.94  top-3=0.85+ → above
#   q2 (team):     top-1=1.00  top-3=0.94  → above (false-negative ok; KW hack)
#   q3 (churn):    top-1≈0.92  top-3=0.83  → above
#   q4 (rumor):    top-1=0.93  top-3=0.88  → above
#   q5 (gf):       top-1=0.82  top-3=0.747 → top-3 GATE TRIPS
#   q6 (1+1):     top-1=0.70  top-3=0.597 → BOTH GATES TRIP
#   q7 (BTC):     top-1=0.65  top-3=0.63  → BOTH GATES TRIP
# Env override knobs let us re-tune in prod without redeploy.
RELEVANCE_TOP1_MIN = float(os.getenv("ASK_RELEVANCE_TOP1_MIN", "0.75"))
RELEVANCE_TOP3_MEAN_MIN = float(os.getenv("ASK_RELEVANCE_TOP3_MEAN_MIN", "0.65"))


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

    # Key we are hunting for, including the closing quote so we don't
    # match `"answer_extra"`. We tolerate any whitespace between the key
    # close-quote and the colon.
    _KEY = '"answer"'

    def __init__(self) -> None:
        self.state = self.SCANNING
        # Rolling buffer used only while SCANNING for `"answer"`. Capped at
        # 256 chars so a runaway preamble can't blow memory.
        self._scan_tail = ""
        # Pending escape sequence handler — set when we hit `\` inside the
        # string. Forms: "esc" (next single-char escape) | "uXXXX" partial.
        self._pending_esc: Optional[str] = None

    def feed(self, chunk: str) -> str:
        """Push a chunk of raw JSON text. Return any newly-emittable answer chars."""
        out_parts: List[str] = []
        for ch in chunk:
            piece = self._step(ch)
            if piece:
                out_parts.append(piece)
            if self.state == self.DONE:
                # Drop the rest of the chunk — caller will keep feeding
                # for the buffer copy but we don't emit anything more.
                break
        return "".join(out_parts)

    def _step(self, ch: str) -> str:  # noqa: C901  (state machine reads cleaner inline)
        if self.state == self.SCANNING:
            self._scan_tail = (self._scan_tail + ch)[-len(self._KEY):]
            if self._scan_tail == self._KEY:
                self.state = self.AFTER_KEY
            return ""

        if self.state == self.AFTER_KEY:
            # Look for `:` then the opening `"`. Skip whitespace between.
            if ch == '"':
                self.state = self.IN_VALUE
            # Any non-whitespace, non-`:`, non-`"` char here means the
            # response shape is off-spec; we let the full json.loads at
            # end-of-stream report it. Stay AFTER_KEY in case it normalizes.
            return ""

        if self.state == self.IN_VALUE:
            # Handle pending escape from previous char.
            if self._pending_esc is not None:
                return self._consume_escape(ch)
            if ch == "\\":
                self._pending_esc = "esc"
                return ""
            if ch == '"':
                # Unescaped closing quote → end of answer string value.
                self.state = self.DONE
                return ""
            return ch

        # DONE — ignore everything else.
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
                # Expect 4 hex digits to follow.
                self._pending_esc = "u"
                return ""
            # Unknown escape — drop the backslash, keep the char.
            self._pending_esc = None
            return ch
        if pending.startswith("u"):
            # Accumulate up to 4 hex digits.
            buf = pending + ch
            if len(buf) >= 5:  # "u" + 4 digits
                hex_digits = buf[1:5]
                try:
                    self._pending_esc = None
                    return chr(int(hex_digits, 16))
                except ValueError:
                    self._pending_esc = None
                    return ""  # malformed → silently drop
            self._pending_esc = buf
            return ""
        # Unknown pending state — reset.
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
    # Try to cut at the first natural sentence boundary, EN or ZH.
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

    # ------------------------------------------------------------------ #
    # Public entry — async generator yielding SSE-formatted strings.
    # ------------------------------------------------------------------ #

    async def stream(self, query: str, lang: str = "zh") -> AsyncIterator[str]:
        """Run the full 3-phase pipeline. Caller is FastAPI StreamingResponse."""
        started = time.monotonic()
        started_iso = _now_iso()
        lang_norm = (lang or "zh").lower()
        if lang_norm not in ("zh", "en"):
            lang_norm = "zh"

        # ---- Phase A: vector search ---------------------------------- #
        # We don't currently invoke the LLM rewrite gate here — the /ask
        # surface is a single-box Perplexity-style flow, so we keep the
        # user's query verbatim to minimize latency.
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

        # Always emit the kb_cards event (possibly empty) so the frontend
        # can transition from "searching" to "ready". Cards keep only the
        # display-safe fields; descriptions stay short.
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
        # W5-B: explicit `retrieval_done` event marking the user-visible
        # transition from "搜索中…" to "找到 N 篇 → 正在生成"。Frontend
        # paints citation placeholder cards on this event so the user has
        # a concrete signal well before the LLM produces its first token.
        # Kept alongside the legacy `kb_cards` event so older clients keep
        # working without change.
        yield _sse("retrieval_done", {
            "count": len(cards_payload),
            "retrieval_ms": retrieval_ms,
            # Lightweight precis — name + domain + idx so a citation card
            # placeholder can render. Full descriptions still go via the
            # subsequent kb_cards event.
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

        # ---- Relevance gate (W5-A) ---------------------------------- #
        # Inspect the retrieval scores. If the query is clearly outside
        # the KB's coverage, we still call the LLM (UX wants one coherent
        # SSE stream regardless), but we tell the LLM to politely decline
        # rather than硬拗 isomorphism content. This is a code-layer
        # guardrail per the global "不信任 LLM 输出" rule — we don't let
        # the LLM alone decide whether to honor scope.
        low_relevance, relevance_reason = self._evaluate_relevance(cards)
        if low_relevance:
            logger.info(
                f"[ask] low-relevance query gated; reason={relevance_reason} "
                f"top1={(cards[0].get('score') if cards else None)}"
            )

        # ---- Phase B: LLM synthesize answer + citations + followups -- #
        # W5-A + W5-B combined: streaming pipeline carries the low_relevance
        # flag through to the prompt builder so the LLM degrades gracefully
        # on out-of-scope queries while still streaming chunk-by-chunk.
        # W14-D: structured `ask.llm.start` log line — model + low_relevance
        # + retrieval count so a single grep on `request_id` reconstructs
        # the whole pipeline timeline.
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.llm.start",
                model=self.model,
                kb_count=len(cards_payload),
                low_relevance=low_relevance,
            )
        except Exception:
            pass
        llm_started = time.monotonic()
        payload: Dict
        raw_buffer = ""
        first_chunk_sent = False
        try:
            async for kind, value in self._stream_llm_answer_with_retry(
                query, cards, lang_norm, low_relevance=low_relevance,
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

        # W14-D: structured `ask.llm.complete` event. We don't have token
        # counts in-band (the SSE stream doesn't surface them), so latency
        # + answer length is the best proxy until we plumb token usage
        # through llm_service.
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.llm.complete",
                latency_ms=int((time.monotonic() - llm_started) * 1000),
                answer_len=len(answer_text),
            )
        except Exception:
            pass

        # If we never streamed any answer chars (e.g. fallback path, or the
        # JSON-string-extractor never matched `"answer"` because the model
        # produced a wonky envelope), fall back to one typewriter pass so
        # the frontend isn't stuck on its "正在思考..." placeholder.
        if not first_chunk_sent and answer_text:
            for chunk in self._typewriter_chunks(answer_text):
                yield _sse("answer_chunk", {"delta": chunk})
                if TYPEWRITER_SLEEP_S > 0:
                    await asyncio.sleep(TYPEWRITER_SLEEP_S)

        # Sanitize citations against the actual cards range so a
        # hallucinated idx never leaks to the frontend.
        validated_citations = self._validate_citations(payload.get("citations", []), cards)
        answer_done_payload = {
            "full_text": answer_text,
            "citations": validated_citations,
        }
        if low_relevance:
            # Surface the gate decision so the UI can render an
            # "out-of-scope" badge / softer styling and so analytics can
            # track how often we degrade.
            answer_done_payload["out_of_scope"] = True
            answer_done_payload["scope_reason"] = relevance_reason
        yield _sse("answer_done", answer_done_payload)

        # ---- Phase C: similar phenomena ------------------------------ #
        similar = self._build_similar_phenomena(cards[:TOP_K_SIMILAR])
        yield _sse("similar_phenomena", {"phenomena": similar})

        # ---- Followups ----------------------------------------------- #
        followups = list(payload.get("followups", []))[:3] if payload else []
        # Pad/trim defensively — schema requires >=2, but a fallback path
        # might pass empty. Surface at most 3, drop blanks.
        followups = [q.strip() for q in followups if isinstance(q, str) and q.strip()][:3]
        yield _sse("followups", {"questions": followups})

        # ---- Done ---------------------------------------------------- #
        latency_ms = int((time.monotonic() - started) * 1000)
        # W14-D: emit final `ask.response` event so a single grep on the
        # request_id reconstructs full lifecycle (request → retrieval →
        # llm.start → llm.complete → response).
        try:
            from logging_config import get_logger as _glog

            _glog("structural.ask").info(
                "ask.response",
                latency_ms=latency_ms,
                citation_count=len(validated_citations),
                out_of_scope=bool(low_relevance),
            )
        except Exception:
            pass
        yield _sse("done", {"latency_ms": latency_ms})

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

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

    # ---------------- Relevance gating (W5-A) --------------------------- #

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

    # ---------------- LLM call + retry --------------------------------- #

    async def _llm_answer_with_retry(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
        low_relevance: bool = False,
    ) -> Dict:
        """One LLM call; on failure retry once with a stricter reminder.

        Returns a dict {answer, citations, followups}. On total failure
        returns a graceful fallback so the SSE stream can still complete.

        Kept for backward compatibility / non-streaming code paths (tests
        currently still drive this via `_call_llm_once` mocks). The hot
        path in `stream()` uses `_stream_llm_answer_with_retry` instead.
        """
        # First attempt — normal prompt.
        prompt = self._build_prompt(
            query, cards, lang, strict_json=False, low_relevance=low_relevance,
        )
        result = await self._call_llm_once(prompt)
        validated = self._try_validate(result)
        if validated is not None:
            return validated

        # Retry once with a stricter "JSON only, no markdown fences" note.
        logger.warning("[ask] first LLM JSON validate failed; retrying once")
        prompt2 = self._build_prompt(
            query, cards, lang, strict_json=True, low_relevance=low_relevance,
        )
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
        low_relevance: bool = False,
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
        # ---- Attempt 1: stream + extract --------------------------------
        prompt = self._build_prompt(query, cards, lang, strict_json=False, low_relevance=low_relevance)
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

        # ---- Attempt 2: depends on whether we already streamed answer ---
        if emitted_any:
            # Already showed text to user. Re-call (non-streaming) for a
            # second shot at valid citations/followups, but preserve the
            # already-emitted answer string by overriding `answer` with
            # whatever we managed to accumulate via the extractor.
            logger.warning("[ask] stream JSON validate failed; retry (no re-stream)")
            prompt2 = self._build_prompt(query, cards, lang, strict_json=True, low_relevance=low_relevance)
            result2 = await self._call_llm_once(prompt2)
            validated2 = self._try_validate(result2)
            if validated2 is not None:
                # Keep what the user already saw on screen.
                streamed_answer = self._best_effort_extract_answer(accumulated)
                if streamed_answer:
                    validated2 = dict(validated2)
                    validated2["answer"] = streamed_answer
                yield ("done", validated2)
                return
        else:
            # Nothing user-visible yet — safe to fully re-stream.
            logger.warning("[ask] stream emitted nothing; retry with strict_json")
            prompt2 = self._build_prompt(query, cards, lang, strict_json=True, low_relevance=low_relevance)
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

            # Final tier: if streaming failed entirely (e.g. no API key,
            # network refused) fall back to the legacy non-streaming
            # `_call_llm_once` path. This preserves compatibility with
            # mocks that only patch `_call_llm_once` AND keeps prod from
            # giving up if the streaming endpoint flakes.
            if stream2_errored or not accumulated2:
                logger.warning("[ask] streaming retry empty; falling back to non-stream")
                try:
                    result3 = await self._call_llm_once(prompt2)
                except Exception as e:
                    logger.error(f"[ask] non-stream fallback failed: {e}")
                    result3 = None
                validated4 = self._try_validate(result3)
                if validated4 is not None:
                    # Typewriter emission of the recovered answer so the
                    # frontend isn't stuck on its placeholder.
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
        # Last resort — walk the chars through the extractor to reconstruct.
        ext = _AnswerFieldExtractor()
        return ext.feed(text)

    def _try_validate(self, raw: Optional[str]) -> Optional[Dict]:
        """Parse + pydantic-validate the LLM JSON. None on any failure."""
        if not raw:
            return None
        text = raw.strip()
        # Strip stray markdown fences the model occasionally adds.
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
        # Use model_dump so downstream code works with plain dicts.
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
                    # DeepSeek + OpenRouter both honor response_format on
                    # most builds; the strict-mode retry also reminds in
                    # the prompt to be JSON-only.
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
                        # OpenRouter occasionally emits non-JSON keepalive
                        # comments — skip silently.
                        continue
                    delta = (
                        chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                        or ""
                    )
                    if not delta:
                        continue
                    # Always forward raw chunk so the caller can accumulate
                    # the full JSON for final pydantic validation.
                    yield ("raw_chunk", delta)
                    # Extract any answer-field chars unlocked by this delta.
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
        low_relevance: bool = False,
    ) -> str:
        """Build the single-shot prompt for answer + citations + followups.

        When `low_relevance` is True, the prompt switches to an
        out-of-scope branch that asks the model to decline politely and
        redirect the user — instead of硬拗 isomorphism analogies on
        edge / trivial / prediction queries.
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

        # ---- Out-of-scope branch (W5-A) --------------------------------
        # Triggered when our retrieval-score gate decided the KB doesn't
        # really cover this query. We want a short, honest, redirecting
        # answer — not a forced cross-domain analogy. The JSON schema
        # stays identical so downstream emission code is unchanged; we
        # only re-frame the instructions and relax the citation rule.
        if low_relevance:
            if lang == "en":
                scope_intro = (
                    "The user's query is OUTSIDE the typical coverage of this "
                    "structural-isomorphism knowledge base. The retrieved KB "
                    "items are weakly related at best. Do NOT force an "
                    "isomorphism analogy."
                )
                scope_rules = (
                    "Write a SHORT (60-180 chars) answer that:\n"
                    "  1) politely says this question is outside the KB's "
                    "coverage (this KB focuses on cross-disciplinary "
                    "structural isomorphism — e.g. earthquakes, bank runs, "
                    "neural avalanches share a common math)\n"
                    "  2) gives ONE concrete redirect — what kind of source / "
                    "discipline / tool would actually answer this\n"
                    "  3) does NOT pretend the retrieved KB items are "
                    "relevant. Do not cite them with [n] markers.\n"
                    "Followups should be 3 questions that DO fit the KB scope "
                    "(structural isomorphism / cascades / phase transitions / "
                    "network dynamics), so the user can pivot productively."
                )
            else:
                scope_intro = (
                    "用户的问题超出本「结构同构」知识库的典型覆盖范围。"
                    "下方召回的 KB 现象相关性都很弱。不要硬拗跨域类比。"
                )
                scope_rules = (
                    "请写一段简短（60-180 字）的回复，包含：\n"
                    "  1) 委婉说明这个问题不在 Structural 当前覆盖范围（"
                    "Structural 专注跨学科结构同构，如地震 / 银行挤兑 / "
                    "神经放电的共同数学）\n"
                    "  2) 给出 1 句具体建议——哪个学科 / 工具 / 资源更适合\n"
                    "  3) 不要把召回的 KB 现象当真，不要使用 [n] 引用标记\n"
                    "followups 必须给 3 个真正落在结构同构 / 级联 / 相变 / "
                    "网络动力学范围内的问题，让用户能转向有意义的探索方向。"
                )

            return f"""你是一个跨学科结构同构搜索引擎。{scope_intro}

用户问题：
{query}

下方是 vector 检索召回的 KB 现象（仅供参考，相关性低）：
{cards_block}

{lang_clause}

{scope_rules}

请输出严格 JSON（schema 不变）：
{{
  "answer": "60-180 字短回复：承认超出范围 + 给重定向建议",
  "citations": [
    {{"idx": 1, "kb_id": "对应 KB 现象的 id（schema 要求至少 1 条；填 idx=1 即可，不要在 answer 文本中使用 [1] 标记）", "label": "out-of-scope"}}
  ],
  "followups": ["真正落在结构同构范围内的问题1?", "问题2?", "问题3?"]
}}

要求：
- answer 长度 20-2000 字符；out-of-scope 模式下不需要在文本中插入 [n] 引用标记
- citations 数组至少 1 条以满足 schema（label 写 out-of-scope 即可）
- followups 必须 2-5 条，全部围绕结构同构 / 跨域结构 / 级联 / 相变 / 网络动力学{strict_block}"""

        # ---- Normal in-scope prompt -----------------------------------
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
        # Build a single citation pointing at card 1 if any cards exist.
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
