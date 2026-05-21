"""Out-of-scope query detection (launch P1-3).

Structural answers ONE kind of question: "what cross-domain structural
analogue does the knowledge base hold for this phenomenon?". Anything
else — simple arithmetic, greetings / chit-chat, factual trivia — must be
politely declined, not force-fitted into a 9-section isomorphism report.

Two product surfaces need this gate:
  * /api/ask/stream      — already has a retrieval-score relevance gate
                           + a forecasting-intent keyword gate
                           (services/ask_orchestrator.py). This module
                           ADDS a deterministic "trivial / chit-chat"
                           layer that runs even when a junk query happens
                           to retrieve a KB card with a decent cosine.
  * /api/analyze/stream  — the deep-report generator had NO scope gate at
                           all: "1+1 等于几" + any b_id produced a full
                           report. This module is the gate it now calls.

Design — same philosophy as the existing forecasting-intent gate:
  * Deterministic substring / regex match on a normalised query.
  * Deliberately permissive on the refuse side for the OBVIOUS junk
    classes (pure arithmetic, bare greetings) — a false positive is one
    polite decline; a false negative is a burned LLM call + a credibility
    hit ("验证型产品硬拗 = 信任崩").
  * Conservative: only fires on clearly trivial input. A real
    cross-domain question that merely contains a number is NOT caught
    here — the retrieval-score gate handles genuine relevance.
"""

from __future__ import annotations

import re
import unicodedata

***REMOVED*** Pure-arithmetic: an expression made only of digits, operators, spaces,
***REMOVED*** parentheses and an optional "= / 等于 / equals ?" tail. Matches
***REMOVED*** "1+1", "1+1=?", "2 * 3", "(4-2)/2 等于几". Requires at least one
***REMOVED*** operator so a bare "42" or a year like "2024" does NOT trip.
_ARITHMETIC_RE = re.compile(
    r"^[\s\d\+\-\*/×÷\^\.\(\)]*[\+\-\*/×÷\^][\s\d\+\-\*/×÷\^\.\(\)]*"
    r"(?:[=＝]|equals?|等于)?\s*[\?？]?\s*(?:几|多少|是多少)?\s*$",
    re.IGNORECASE,
)

***REMOVED*** Bare greetings / chit-chat openers. Matched as the WHOLE (short) query
***REMOVED*** only — "hello" alone is chit-chat, but "hello, why do bank runs cascade"
***REMOVED*** is a real question and must pass.
***REMOVED*** NOTE: "test" / "测试" are intentionally NOT here. They are ambiguous —
***REMOVED*** a user may legitimately probe the product with "test" — and treating
***REMOVED*** them as chit-chat would over-refuse. The retrieval-score gate handles
***REMOVED*** them if they genuinely retrieve nothing.
_CHITCHAT_PHRASES = {
    ***REMOVED*** zh
    "你好", "您好", "在吗", "在不在", "你是谁", "你叫什么", "你会什么",
    "你能做什么", "谢谢", "谢谢你", "再见", "哈喽", "嗨",
    "你好吗", "早上好", "晚上好", "下午好",
    ***REMOVED*** en
    "hi", "hello", "hey", "yo", "thanks", "thank you", "bye", "goodbye",
    "who are you", "what are you", "what can you do", "good morning",
    "good evening", "how are you", "ping",
}

***REMOVED*** Short factual-trivia / definition questions that are NOT cross-domain
***REMOVED*** structural questions. Kept short + specific to avoid catching real
***REMOVED*** questions. Matched as a leading prefix on a short query.
_TRIVIA_PREFIXES_ZH = (
    "今天几号", "今天星期几", "现在几点", "天气怎么样", "明天天气",
    ***REMOVED*** Session ***REMOVED***17 V3.3 — the canonical bug example "今天天气怎么样" started
    ***REMOVED*** with "今天" so the bare "天气怎么样" prefix never matched it. Add the
    ***REMOVED*** explicit "今天天气" / "今天的天气" leads so the weather-trivia class
    ***REMOVED*** is actually caught.
    "今天天气", "今天的天气",
)
_TRIVIA_PREFIXES_EN = (
    "what time is it", "what's the date", "what is the date",
    "what day is it", "what's the weather", "what is the weather",
)

***REMOVED*** A query longer than this is assumed to carry real intent — the
***REMOVED*** chit-chat / trivia prefix checks only apply to SHORT queries so we
***REMOVED*** never decline a substantive question that merely opens with "hi,".
_SHORT_QUERY_CHARS = 24


def _normalise(text: str) -> str:
    """NFKC-fold, lowercase, strip — full/half-width digits unify."""
    return unicodedata.normalize("NFKC", text or "").lower().strip()


def is_out_of_scope(query: str) -> tuple[bool, str]:
    """Return (out_of_scope, reason) for a free-text query.

    reason ∈ {"arithmetic", "chitchat", "trivia", "ok"}. Only fires on
    clearly trivial / off-topic input; genuine relevance is the retrieval
    gate's job. Empty / whitespace-only input is treated as out-of-scope
    ("empty") — there is nothing to analyse.
    """
    q = _normalise(query)
    if not q:
        return True, "empty"

    ***REMOVED*** 1. Pure arithmetic — "1+1", "2*3=?", "(4-2)/2 等于几".
    ***REMOVED***    Strip trailing punctuation the regex tail already tolerates.
    if _ARITHMETIC_RE.match(q):
        ***REMOVED*** Guard: the expression must actually contain a digit (the regex
        ***REMOVED*** alone could match a lone operator).
        if any(ch.isdigit() for ch in q):
            return True, "arithmetic"

    ***REMOVED*** 2 & 3 only apply to short queries — a long query carries real intent.
    if len(q) <= _SHORT_QUERY_CHARS:
        ***REMOVED*** 2. Bare chit-chat / greeting.
        stripped = q.rstrip("?？!！.。,，~ ")
        if stripped in _CHITCHAT_PHRASES:
            return True, "chitchat"
        ***REMOVED*** 3. Trivia / definition prefixes.
        for p in _TRIVIA_PREFIXES_ZH + _TRIVIA_PREFIXES_EN:
            if q.startswith(p):
                return True, "trivia"

    return False, "ok"


__all__ = ["is_out_of_scope"]
