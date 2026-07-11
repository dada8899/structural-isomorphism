"""Tests for the out-of-scope query gate — launch P1-3.

`services.scope_guard.is_out_of_scope` deterministically declines obviously
trivial / off-topic input (arithmetic, greetings, trivia) so the product
never硬拗 a 9-section isomorphism report for "1+1 等于几".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.scope_guard import is_out_of_scope  # noqa: E402


# --------- arithmetic: must be refused --------- #


@pytest.mark.parametrize("q", [
    "1+1",
    "1+1=?",
    "1+1 等于几",
    "1+1等于几",
    "2 * 3",
    "(4-2)/2",
    "100 / 4 = ?",
    "7 - 3 是多少",
    "2^10",
    "１＋１",  # full-width digits/operator — NFKC folds them
])
def test_arithmetic_is_out_of_scope(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "arithmetic"


# --------- chit-chat / greetings: must be refused --------- #


@pytest.mark.parametrize("q", [
    "你好", "您好", "在吗", "你是谁", "谢谢", "再见",
    "hi", "hello", "hey", "thanks", "bye", "who are you",
    "你好！", "hello?", "  hi  ",
])
def test_chitchat_is_out_of_scope(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "chitchat"


# --------- trivia: must be refused --------- #


@pytest.mark.parametrize("q", [
    "今天几号", "现在几点", "今天星期几",
    "what time is it", "what's the weather",
    # Session #17 V3.3 — the canonical bug example. "今天天气怎么样" leads
    # with "今天", so the bare "天气怎么样" prefix used to miss it.
    "今天天气怎么样", "今天天气怎么样？", "今天的天气如何",
])
def test_trivia_is_out_of_scope(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "trivia"


# --------- empty input --------- #


@pytest.mark.parametrize("q", ["", "   ", "\n\t", None])
def test_empty_is_out_of_scope(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "empty"


# --------- genuine cross-domain questions: must PASS --------- #


@pytest.mark.parametrize("q", [
    "为什么银行挤兑和森林大火的蔓延方式如此相似？",
    "临界相变能不能提前预警？",
    "网络拓扑结构如何决定级联失败的规模？",
    "How do bank runs and forest fires spread in structurally similar ways?",
    "Why does a power grid cascade fail like a neural avalanche?",
    # A real question that merely opens with a greeting word — must pass
    # because it is longer than the short-query threshold.
    "hello, why do teams fall apart over time like radioactive decay?",
    # A real question that contains a number — NOT pure arithmetic.
    "我的月活每月掉 30%，这和什么物理现象结构同构？",
    # "test" is intentionally NOT chit-chat (ambiguous probe) — must pass.
    "test",
])
def test_genuine_questions_pass(q):
    oos, reason = is_out_of_scope(q)
    assert oos is False, f"genuine question wrongly refused: {q!r} ({reason})"
    assert reason == "ok"


def test_bare_number_is_not_arithmetic():
    """A lone number (no operator) is not refused as arithmetic — it's
    just weak input the retrieval gate can handle."""
    oos, reason = is_out_of_scope("42")
    assert reason != "arithmetic"


@pytest.mark.parametrize("q", [
    "股票价格涨跌为什么形成周期振荡？",
    "How do stock prices rise and fall in an endogenous cycle?",
    "供应链级联风险应该怎么做结构化分析？",
])
def test_structural_questions_are_not_over_refused(q):
    oos, reason = is_out_of_scope(q)
    assert oos is False
    assert reason == "ok"


def test_food_words_do_not_overmatch_business_language():
    for query in (
        "菜鸟团队遇到增长瓶颈应该怎么做？",
        "红烧商业模式为什么形成正反馈，应该怎么做？",
    ):
        oos, reason = is_out_of_scope(query)
        assert oos is False
        assert reason == "ok"


def test_finance_words_do_not_overmatch_structural_analysis():
    oos, reason = is_out_of_scope("推荐一个比特币与银行挤兑的结构类比。")
    assert oos is False
    assert reason == "ok"


@pytest.mark.parametrize("q", ["推荐一只值得买入的股票", "比特币现在值得投资吗？"])
def test_transactional_finance_requests_are_refused(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "forecasting_intent"


@pytest.mark.parametrize("q", [
    "Pick a crypto guaranteed to rise next week and explain its mechanism.",
    "预测明天股价并分析结构机制",
])
def test_explicit_forecasts_cannot_use_structural_analysis_as_bypass(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "forecasting_intent"


@pytest.mark.parametrize("q", ["茅台涨到多少？", "特斯拉目标价是多少？"])
def test_price_target_forecasts_are_refused(q):
    oos, reason = is_out_of_scope(q)
    assert oos is True
    assert reason == "forecasting_intent"
