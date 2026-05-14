"""
AskOrchestrator — Perplexity-like 3-phase SSE backend for /api/ask/stream.

Pipeline:
    Phase A: vector-search the cross-domain KB for top-5 cards (~1-2s).
             Emit `meta` then `kb_cards`.
    Phase B: one LLM call (DeepSeek via OpenRouter) returns a JSON object
             {answer, citations, followups}. Validate with pydantic. Then
             typewriter-emit `answer_chunk` deltas and finally `answer_done`.
    Phase C: pick top-3 of the same KB cards, derive a one-sentence
             "key_metric" snippet from each card's description, emit
             `similar_phenomena`.
    Finalize: emit `followups` then `done`.

Design notes:
- The LLM is invoked once for answer + citations + followups (per spec).
  Splitting would multiply latency and burn quota.
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
from typing import AsyncIterator, Dict, List, Optional

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


def _sse(event: str, data: Dict) -> str:
    """Format a single SSE event line."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        try:
            if self.search is not None:
                cards = self.search.search(query, top_k=TOP_K_CARDS) or []
        except Exception as e:
            logger.warning(f"[ask] vector search failed: {e}")
            cards = []

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
        yield _sse("kb_cards", {"cards": cards_payload, "count": len(cards_payload)})

        # ---- Phase B: LLM synthesize answer + citations + followups -- #
        payload = await self._llm_answer_with_retry(query, cards, lang_norm)

        # Typewriter-emit the answer text.
        answer_text = payload.get("answer", "") if payload else ""
        if answer_text:
            for chunk in self._typewriter_chunks(answer_text):
                yield _sse("answer_chunk", {"delta": chunk})
                # Yield control between chunks so other awaits (search,
                # heartbeats) can run. Skip the sleep when running in
                # tests to keep test runtime tight.
                if TYPEWRITER_SLEEP_S > 0:
                    await asyncio.sleep(TYPEWRITER_SLEEP_S)

        # Sanitize citations against the actual cards range so a
        # hallucinated idx never leaks to the frontend.
        validated_citations = self._validate_citations(payload.get("citations", []), cards)
        yield _sse("answer_done", {
            "full_text": answer_text,
            "citations": validated_citations,
        })

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

    # ---------------- LLM call + retry --------------------------------- #

    async def _llm_answer_with_retry(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
    ) -> Dict:
        """One LLM call; on failure retry once with a stricter reminder.

        Returns a dict {answer, citations, followups}. On total failure
        returns a graceful fallback so the SSE stream can still complete.
        """
        # First attempt — normal prompt.
        prompt = self._build_prompt(query, cards, lang, strict_json=False)
        result = await self._call_llm_once(prompt)
        validated = self._try_validate(result)
        if validated is not None:
            return validated

        # Retry once with a stricter "JSON only, no markdown fences" note.
        logger.warning("[ask] first LLM JSON validate failed; retrying once")
        prompt2 = self._build_prompt(query, cards, lang, strict_json=True)
        result2 = await self._call_llm_once(prompt2)
        validated2 = self._try_validate(result2)
        if validated2 is not None:
            return validated2

        logger.error("[ask] LLM JSON validate failed twice; emitting fallback")
        return self._fallback_payload(query, cards, lang)

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

    def _build_prompt(
        self,
        query: str,
        cards: List[Dict],
        lang: str,
        strict_json: bool,
    ) -> str:
        """Build the single-shot prompt for answer + citations + followups."""
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
