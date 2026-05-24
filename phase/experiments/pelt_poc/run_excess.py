"""
PELT POC — 超额收益（alpha）版
==============================

用公司相对 SPY 的超额收益做 PELT，去掉市场 beta。

信号：
  A. 超额 YoY 收益（公司 YoY - SPY YoY）
  B. 超额滚动波动率（公司 - SPY 的日收益差，算滚动 std）
  C. 超额滚动夏普比

这样找到的拐点更可能是"公司自身结构变化"而非"跟着市场崩"。
"""
import os
import sys
import warnings
from datetime import datetime
from collections import defaultdict
import json

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from run_poc import (
    fetch_price_history,
    run_pelt,
    top_k_breaks,
    validate_break_point,
)
from run_multi import (
    find_breaks_with_scores,
    cross_signal_filter,
)
from run_scale import TICKERS

SPY_CACHE_M = None
SPY_CACHE_D = None


def get_spy():
    global SPY_CACHE_M, SPY_CACHE_D
    if SPY_CACHE_M is None:
        SPY_CACHE_M, SPY_CACHE_D = fetch_price_history("SPY", years=15)
    return SPY_CACHE_M, SPY_CACHE_D


def compute_excess_yoy(price, spy_price):
    """公司 YoY 收益 减 SPY YoY 收益 = 超额 YoY。"""
    if price.empty or spy_price.empty:
        return pd.DataFrame()
    c = price.copy().sort_values("date").reset_index(drop=True)
    s = spy_price.copy().sort_values("date").reset_index(drop=True)
    c["date"] = pd.to_datetime(c["date"])
    s["date"] = pd.to_datetime(s["date"])

    merged = pd.merge_asof(c, s, on="date", suffixes=("_co", "_spy"), direction="nearest")
    merged["co_yoy"] = merged["price_co"].pct_change(12)
    merged["spy_yoy"] = merged["price_spy"].pct_change(12)
    merged["excess_yoy"] = merged["co_yoy"] - merged["spy_yoy"]
    merged = merged.dropna(subset=["excess_yoy"])
    return merged[["date", "excess_yoy"]].rename(columns={"excess_yoy": "value"})


def compute_excess_vol_monthly(price_daily, spy_daily, window=60):
    """日度超额收益（co - spy）的 60 日滚动波动率，聚合月末。"""
    if price_daily.empty or spy_daily.empty:
        return pd.DataFrame()
    c = price_daily.copy().sort_values("date").reset_index(drop=True)
    s = spy_daily.copy().sort_values("date").reset_index(drop=True)
    c["date"] = pd.to_datetime(c["date"])
    s["date"] = pd.to_datetime(s["date"])
    m = pd.merge_asof(c, s, on="date", suffixes=("_co", "_spy"), direction="nearest")
    m["co_ret"] = m["price_co"].pct_change()
    m["spy_ret"] = m["price_spy"].pct_change()
    m["excess_ret"] = m["co_ret"] - m["spy_ret"]
    m["vol"] = m["excess_ret"].rolling(window).std()
    m = m.dropna(subset=["vol"]).set_index("date")
    out = m["vol"].resample("ME").last().dropna()
    return out.reset_index().rename(columns={"vol": "value"})


def compute_excess_sharpe_monthly(price_daily, spy_daily, window=60):
    if price_daily.empty or spy_daily.empty:
        return pd.DataFrame()
    c = price_daily.copy().sort_values("date").reset_index(drop=True)
    s = spy_daily.copy().sort_values("date").reset_index(drop=True)
    c["date"] = pd.to_datetime(c["date"])
    s["date"] = pd.to_datetime(s["date"])
    m = pd.merge_asof(c, s, on="date", suffixes=("_co", "_spy"), direction="nearest")
    m["co_ret"] = m["price_co"].pct_change()
    m["spy_ret"] = m["price_spy"].pct_change()
    m["excess_ret"] = m["co_ret"] - m["spy_ret"]
    m["mean_ex"] = m["excess_ret"].rolling(window).mean()
    m["vol"] = m["excess_ret"].rolling(window).std()
    m["sharpe"] = m["mean_ex"] / (m["vol"] + 1e-9)
    m = m.dropna(subset=["sharpe"]).set_index("date")
    out = m["sharpe"].resample("ME").last().dropna()
    return out.reset_index().rename(columns={"sharpe": "value"})


def validate_excess(price_daily, spy_daily, break_date, window_days=60):
    """类似 validate_break_point，但用超额收益。"""
    if price_daily.empty or spy_daily.empty:
        return None
    bd = pd.Timestamp(break_date)
    c = price_daily.sort_values("date").reset_index(drop=True).copy()
    s = spy_daily.sort_values("date").reset_index(drop=True).copy()
    c["date"] = pd.to_datetime(c["date"])
    s["date"] = pd.to_datetime(s["date"])

    before_c = c[(c["date"] >= bd - pd.Timedelta(days=window_days)) & (c["date"] < bd)]
    after_c = c[(c["date"] >= bd) & (c["date"] < bd + pd.Timedelta(days=window_days))]
    before_s = s[(s["date"] >= bd - pd.Timedelta(days=window_days)) & (s["date"] < bd)]
    after_s = s[(s["date"] >= bd) & (s["date"] < bd + pd.Timedelta(days=window_days))]
    if len(before_c) < 5 or len(after_c) < 5 or len(before_s) < 5 or len(after_s) < 5:
        return None

    co_ret_before = before_c["price"].iloc[-1] / before_c["price"].iloc[0] - 1
    co_ret_after = after_c["price"].iloc[-1] / after_c["price"].iloc[0] - 1
    spy_ret_before = before_s["price"].iloc[-1] / before_s["price"].iloc[0] - 1
    spy_ret_after = after_s["price"].iloc[-1] / after_s["price"].iloc[0] - 1

    excess_before = co_ret_before - spy_ret_before
    excess_after = co_ret_after - spy_ret_after

    # 超额收益的 regime change 判断
    if np.sign(excess_before) != np.sign(excess_after) and abs(excess_before - excess_after) > 0.08:
        regime = "超额趋势反转"
    elif abs(excess_after - excess_before) > 0.12:
        regime = f"超额{'加速' if abs(excess_after) > abs(excess_before) else '减速'}"
    else:
        regime = "无明显变化"

    return {
        "excess_before": float(excess_before),
        "excess_after": float(excess_after),
        "co_before": float(co_ret_before),
        "co_after": float(co_ret_after),
        "spy_before": float(spy_ret_before),
        "spy_after": float(spy_ret_after),
        "regime_change": regime,
    }


def analyze_excess(ticker, name, fam, spy_m, spy_d):
    price, price_daily = fetch_price_history(ticker, years=15)
    if price.empty or price_daily.empty:
        return None

    ex_yoy = compute_excess_yoy(price, spy_m)
    ex_vol = compute_excess_vol_monthly(price_daily, spy_d)
    ex_sharpe = compute_excess_sharpe_monthly(price_daily, spy_d)

    breaks_by_sig = {
        "yoy": find_breaks_with_scores(ex_yoy, pen=6.0),
        "vol": find_breaks_with_scores(ex_vol, pen=3.0),
        "sharpe": find_breaks_with_scores(ex_sharpe, pen=2.0),
    }

    high_conf = cross_signal_filter(breaks_by_sig, window_days=120, min_signals=2)

    validations = []
    for hc in high_conf:
        v = validate_excess(price_daily, spy_d, hc["date"], window_days=60)
        if v:
            v.update(hc)
            v["ticker"] = ticker
            v["name"] = name
            v["family"] = fam
            validations.append(v)

    return {
        "ticker": ticker,
        "name": name,
        "family": fam,
        "high_conf": validations,
        "raw_counts": {sig: len(items) for sig, items in breaks_by_sig.items()},
    }


MACRO_EVENTS = [
    ("2011-08-01", "标普评级下调"),
    ("2015-08-01", "中国股灾"),
    ("2016-06-23", "英国脱欧"),
    ("2016-11-08", "川普当选"),
    ("2018-02-01", "Volmageddon"),
    ("2018-12-01", "Fed 加息恐慌"),
    ("2020-03-01", "COVID crash"),
    ("2020-06-01", "COVID 反弹"),
    ("2021-11-01", "成长股崩"),
    ("2022-01-01", "Fed tightening"),
    ("2022-06-01", "熊市确认"),
    ("2023-03-01", "硅谷银行危机"),
    ("2023-11-01", "AI 行情 + Fed 停加息"),
]


def is_macro(date_str):
    if hasattr(date_str, "strftime"):
        d = date_str
    else:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
    for md_str, desc in MACRO_EVENTS:
        md = datetime.strptime(md_str, "%Y-%m-%d")
        if abs((d - md).days) <= 60:
            return desc
    return None


def main():
    spy_m, spy_d = get_spy()
    print(f"SPY 数据：月度 {len(spy_m)} 点，日度 {len(spy_d)} 点\n")

    results = []
    print(f"跑 {len(TICKERS)} 家公司（超额收益版）…\n")
    for ticker, name, fam in TICKERS:
        if ticker == "SPY":
            continue
        print(f"  [{ticker:6}] {name}… ", end="", flush=True)
        try:
            r = analyze_excess(ticker, name, fam, spy_m, spy_d)
            if r is None:
                print("数据不足")
                continue
            hc = r["high_conf"]
            rc = sum(1 for v in hc if v["regime_change"] != "无明显变化")
            print(f"原始 {r['raw_counts']} → 高置信 {len(hc)}，{rc} 有 regime")
            results.append(r)
        except Exception as e:
            print(f"失败: {e}")

    all_hc = []
    for r in results:
        for v in r["high_conf"]:
            v["macro_event"] = is_macro(v["date"])
            all_hc.append(v)

    n = len(all_hc)
    if n == 0:
        print("无高置信拐点")
        return

    rc = sum(1 for v in all_hc if v["regime_change"] != "无明显变化")
    macro_driven = sum(1 for v in all_hc if v["macro_event"])
    non_macro = sum(1 for v in all_hc if not v["macro_event"])
    real_signal = sum(1 for v in all_hc
                     if not v["macro_event"] and v["regime_change"] != "无明显变化")

    lines = []
    lines.append("# PELT POC 最终版 — 超额收益（alpha）信号\n\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

    lines.append("## 🎯 三版对比\n\n")
    lines.append("| 版本 | 高置信拐点 | regime 变化 | 非宏观真信号 | 真信号比例 |\n|---|---|---|---|---|\n")
    lines.append("| 单信号原始版 | 48 | 26 | — | — |\n")
    lines.append("| 多信号交叉版 | 26 | 16 | — | — |\n")
    lines.append("| 多信号+宏观过滤 | 26 | 16 | 3 | 12% |\n")
    lines.append(f"| **超额收益版** | **{n}** | **{rc}** | **{real_signal}** | **{real_signal/n*100:.0f}%** |\n\n")

    lines.append("## 📊 核心指标\n\n")
    lines.append(f"- 总拐点: {n}\n")
    lines.append(f"- 有超额 regime 变化: {rc} = {rc/n*100:.0f}%\n")
    lines.append(f"- 宏观期拐点: {macro_driven} = {macro_driven/n*100:.0f}%\n")
    lines.append(f"- **非宏观真信号**: {real_signal} = **{real_signal/n*100:.0f}%**\n\n")

    lines.append("## 🎯 筛出的公司真信号（核心成果）\n\n")
    lines.append("下面这些拐点不在宏观事件附近，且公司超额收益有真实 regime 变化——最值得看。\n\n")
    lines.append("| 公司 | 日期 | 置信度 | 公司前 60 天 | SPY 同期 | 超额前 | 公司后 60 天 | SPY 后 | 超额后 | 判断 |\n")
    lines.append("|---|---|---|---|---|---|---|---|---|---|\n")
    for v in all_hc:
        if v["macro_event"] or v["regime_change"] == "无明显变化":
            continue
        lines.append(
            f"| {v['ticker']} | {v['date'].strftime('%Y-%m')} | {v['avg_score']:.2f} | "
            f"{v['co_before']*100:+.1f}% | {v['spy_before']*100:+.1f}% | **{v['excess_before']*100:+.1f}%** | "
            f"{v['co_after']*100:+.1f}% | {v['spy_after']*100:+.1f}% | **{v['excess_after']*100:+.1f}%** | "
            f"{v['regime_change']} |\n"
        )
    lines.append("\n")

    # 按 family 分层真信号
    fam_stats = defaultdict(lambda: {"n": 0, "real": 0, "tickers": set()})
    for r in results:
        fam = r["family"]
        for v in r["high_conf"]:
            fam_stats[fam]["n"] += 1
            if not v["macro_event"] and v["regime_change"] != "无明显变化":
                fam_stats[fam]["real"] += 1
            fam_stats[fam]["tickers"].add(r["ticker"])
    lines.append("## 🏷️ 按 dynamics_family 看真信号出现率\n\n")
    lines.append("| Family | 总拐点 | 真信号 | 比例 | 公司 |\n|---|---|---|---|---|\n")
    for fam, st in sorted(fam_stats.items(), key=lambda x: -(x[1]["real"] / max(x[1]["n"], 1))):
        if st["n"] == 0:
            continue
        lines.append(
            f"| {fam} | {st['n']} | {st['real']} | "
            f"**{st['real']/st['n']*100:.0f}%** | {', '.join(sorted(st['tickers']))} |\n"
        )
    lines.append("\n")

    # 最终判断
    lines.append("## ⚖️ 判断\n\n")
    lift_vs_12 = (real_signal / n) / 0.12 if real_signal > 0 else 0
    if real_signal / n >= 0.40:
        lines.append(f"✅ **有显著提升**：{real_signal/n*100:.0f}%（相比原版 12% 提升 {lift_vs_12:.1f}x）\n")
        lines.append("超额收益确实能去掉大部分 beta 噪声。可以上 MVP。\n")
    elif real_signal / n >= 0.25:
        lines.append(f"🟡 **中等提升**：{real_signal/n*100:.0f}%（相比原版 12%）\n")
        lines.append("方向对，但还可以加财务指标（营收/毛利率）做最后一层 boost。\n")
    else:
        lines.append(f"❌ **提升不够**：{real_signal/n*100:.0f}%\n")
        lines.append("说明 PELT 这条路整体有问题，需要换算法（比如 critical slowing down 双信号）。\n")

    path = os.path.join(os.path.dirname(__file__), "REPORT_EXCESS.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))

    print(f"\n报告: {path}")
    print(f"\n=== 最终数字 ===")
    print(f"高置信拐点: {n}")
    print(f"超额 regime 变化: {rc} ({rc/n*100:.0f}%)")
    print(f"非宏观真信号: {real_signal} ({real_signal/n*100:.0f}%)")
    print(f"相比原版 12% 真信号比例：{(real_signal/n)/0.12:.1f}x" if real_signal else "")


if __name__ == "__main__":
    main()
