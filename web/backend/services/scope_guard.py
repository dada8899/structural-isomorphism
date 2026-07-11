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

# Pure-arithmetic: an expression made only of digits, operators, spaces,
# parentheses and an optional "= / 等于 / equals ?" tail. Matches
# "1+1", "1+1=?", "2 * 3", "(4-2)/2 等于几". Requires at least one
# operator so a bare "42" or a year like "2024" does NOT trip.
_ARITHMETIC_RE = re.compile(
    r"^[\s\d\+\-\*/×÷\^\.\(\)]*[\+\-\*/×÷\^][\s\d\+\-\*/×÷\^\.\(\)]*"
    r"(?:[=＝]|equals?|等于)?\s*[\?？]?\s*(?:几|多少|是多少)?\s*$",
    re.IGNORECASE,
)

# Bare greetings / chit-chat openers. Matched as the WHOLE (short) query
# only — "hello" alone is chit-chat, but "hello, why do bank runs cascade"
# is a real question and must pass.
# NOTE: "test" / "测试" are intentionally NOT here. They are ambiguous —
# a user may legitimately probe the product with "test" — and treating
# them as chit-chat would over-refuse. The retrieval-score gate handles
# them if they genuinely retrieve nothing.
_CHITCHAT_PHRASES = {
    # zh
    "你好", "您好", "在吗", "在不在", "你是谁", "你叫什么", "你会什么",
    "你能做什么", "谢谢", "谢谢你", "再见", "哈喽", "嗨",
    "你好吗", "早上好", "晚上好", "下午好",
    # en
    "hi", "hello", "hey", "yo", "thanks", "thank you", "bye", "goodbye",
    "who are you", "what are you", "what can you do", "good morning",
    "good evening", "how are you", "ping",
}

# Short factual-trivia / definition questions that are NOT cross-domain
# structural questions. Kept short + specific to avoid catching real
# questions. Matched as a leading prefix on a short query.
_TRIVIA_PREFIXES_ZH = (
    "今天几号", "今天星期几", "现在几点", "天气怎么样", "明天天气",
    # Session #17 V3.3 — the canonical bug example "今天天气怎么样" started
    # with "今天" so the bare "天气怎么样" prefix never matched it. Add the
    # explicit "今天天气" / "今天的天气" leads so the weather-trivia class
    # is actually caught.
    "今天天气", "今天的天气",
)
_TRIVIA_PREFIXES_EN = (
    "what time is it", "what's the date", "what is the date",
    "what day is it", "what's the weather", "what is the weather",
)

_HARD_FORECAST_PATTERNS = (
    re.compile(r"(?:预测|明天|下周|一定).*(?:股价|股票|加密货币|币|涨|跌|价格)"),
    re.compile(r"(?:股价|股票|加密货币|币|价格).*(?:预测|明天|下周|一定)"),
    re.compile(r"\b(?:predict|forecast|guaranteed)\b.*\b(?:stock|tesla|crypto|cryptocurrency|price|rise|fall)\b", re.I),
    re.compile(r"\bwill\b.*\b(?:stock|tesla|crypto|cryptocurrency|price)\b.*\b(?:tomorrow|next week|rise|fall)\b", re.I),
    re.compile(r"(?:茅台|特斯拉|股票|股价|比特币|btc|加密货币).*(?:涨到多少|跌到多少|目标价)"),
    re.compile(r"(?:股票|基金|比特币|btc|加密货币).*(?:值得投资|值得买入|该不该买)"),
)

_SOFT_FINANCE_RECOMMENDATION_PATTERNS = (
    re.compile(r"推荐.*(?:股票|基金|加密货币|币)"),
    re.compile(r"(?:股票|基金|加密货币|币).*推荐"),
    re.compile(r"\b(?:pick|recommend)\b.*\b(?:stock|fund|crypto|cryptocurrency|coin)\b", re.I),
)

_STRUCTURAL_ANALYSIS_RE = re.compile(
    r"(?:结构类比|结构同构|结构相似|结构机制|机制分析|正反馈|负反馈|级联|临界相变|"
    r"structural\s+(?:analogy|isomorphism|similarity|mechanism)|mechanism|cascade)",
    re.I,
)
_TRANSACTIONAL_FINANCE_RE = re.compile(
    r"(?:买入|卖出|持仓|建仓|清仓|值得投资|投资标的|推荐.*(?:股票|基金|币种)|"
    r"\b(?:buy|sell|hold|invest(?:ment)?|portfolio)\b)",
    re.I,
)

_GENERAL_TRIVIA_PATTERNS = (
    re.compile(r"^.+的首都(?:是哪里|是什么|在哪)[？?]?$"),
    re.compile(r"^(?:what is|what's) the capital of .+[？?]?$", re.I),
    re.compile(r"^.+(?:明天|今天).*(?:天气|气温).*[？?]?$"),
    re.compile(r"^what (?:will|is).*(?:weather|temperature).*[？?]?$", re.I),
    re.compile(r"^(?:把|请把).+(?:翻译成|译成).+[。.!！]?$"),
    re.compile(r"^translate .+ into .+[.!]?$", re.I),
    re.compile(r"^(?=.*(?:西红柿炒鸡蛋|炒鸡蛋|红烧|清蒸|煲汤|烘焙|食谱|菜谱|做饭|烹饪|料理)).*(?:怎么做|如何做|做法是什么)[？?]?$", re.I),
    re.compile(r"^how (?:do|can) i (?:cook|make|prepare) .+[？?]?$", re.I),
)

# A query longer than this is assumed to carry real intent — the
# chit-chat / trivia prefix checks only apply to SHORT queries so we
# never decline a substantive question that merely opens with "hi,".
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

    # Punctuation/symbol-only input carries no analysable phenomenon.
    if not any(ch.isalnum() or "一" <= ch <= "鿿" for ch in q):
        return True, "empty"

    # Forecasting is product-wide policy, not an ask-only exception. Keep the
    # deterministic high-precision patterns here so search/analyze/ask agree.
    structural_analysis = bool(_STRUCTURAL_ANALYSIS_RE.search(q))
    if any(pattern.search(q) for pattern in _HARD_FORECAST_PATTERNS):
        return True, "forecasting_intent"
    soft_recommendation = any(
        pattern.search(q) for pattern in _SOFT_FINANCE_RECOMMENDATION_PATTERNS
    )
    if soft_recommendation and (not structural_analysis or _TRANSACTIONAL_FINANCE_RE.search(q)):
        return True, "forecasting_intent"

    # Common arithmetic wording wraps the expression in a natural-language
    # prefix/suffix. Strip those wrappers before applying the strict regex.
    arithmetic_candidate = re.sub(r"^(?:what is|what's|calculate|请问|计算)\s*", "", q)
    arithmetic_candidate = re.sub(r"\s*(?:等于几|是多少|equals what)\s*[?？]?$", "", arithmetic_candidate)

    # 1. Pure arithmetic — "1+1", "2*3=?", "(4-2)/2 等于几".
    #    Strip trailing punctuation the regex tail already tolerates.
    if _ARITHMETIC_RE.match(q) or _ARITHMETIC_RE.match(arithmetic_candidate):
        # Guard: the expression must actually contain a digit (the regex
        # alone could match a lone operator).
        if any(ch.isdigit() for ch in arithmetic_candidate):
            return True, "arithmetic"

    if not structural_analysis and any(pattern.match(q) for pattern in _GENERAL_TRIVIA_PATTERNS):
        return True, "trivia"

    stripped = q.rstrip("?？!！.。,，~ ")
    if stripped.startswith(("你好", "您好", "hello", "hi ")) and any(
        marker in stripped for marker in ("怎么样", "好吗", "how are you")
    ):
        return True, "chitchat"

    # 2 & 3 only apply to short queries — a long query carries real intent.
    if len(q) <= _SHORT_QUERY_CHARS:
        # 2. Bare chit-chat / greeting.
        if stripped in _CHITCHAT_PHRASES:
            return True, "chitchat"
        # 3. Trivia / definition prefixes.
        for p in _TRIVIA_PREFIXES_ZH + _TRIVIA_PREFIXES_EN:
            if q.startswith(p):
                return True, "trivia"

    return False, "ok"


__all__ = ["is_out_of_scope"]
