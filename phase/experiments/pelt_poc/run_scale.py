"""
PELT POC 扩展版 — 跑 25 家公司，聚合统计验证指标的稳定性。

目标：验证上一轮 7 家公司跑出来的"50% 拐点对应真实 regime 变化"是巧合还是真信号。
如果 25 家跑出来还在 45-55% 区间 → 算法有真实底子
如果跌到 30-40% → 放弃 PELT 单一信号
如果升到 60%+ → 可以上 MVP
"""
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from run_poc import (
    fetch_price_history,
    compute_price_growth_yoy,
    run_pelt,
    top_k_breaks,
    validate_break_point,
)

# 跨 family、跨 sector 挑的 25 家
# (ticker, name_zh, expected_family) — family 只是标签，不影响算法
TICKERS = [
    # 大科技 / 成长股
    ("AAPL", "苹果", "ODE1_saturating"),
    ("MSFT", "微软", "ODE1_linear"),
    ("GOOGL", "谷歌", "ODE1_saturating"),
    ("AMZN", "亚马逊", "ODE1_logistic"),
    ("META", "Meta", "Phase_transition_2nd"),
    ("NVDA", "NVIDIA", "ODE1_exponential_growth"),
    ("NFLX", "Netflix", "ODE1_saturating"),
    # EV / 消费
    ("TSLA", "Tesla", "Bistable_switch"),
    ("PTON", "Peloton", "Fold_bifurcation"),
    ("SHOP", "Shopify", "ODE1_logistic"),
    ("SBUX", "Starbucks", "ODE1_linear"),
    ("CMG", "Chipotle", "ODE1_logistic"),
    ("BYND", "Beyond Meat", "Fold_bifurcation"),
    # 金融
    ("JPM", "摩根大通", "ODE1_linear"),
    ("GS", "高盛", "ODE2_damped_oscillation"),
    ("V", "Visa", "ODE1_linear"),
    # 能源 / 周期
    ("XOM", "埃克森美孚", "ODE2_damped_oscillation"),
    ("CVX", "雪佛龙", "ODE2_damped_oscillation"),
    ("FCX", "自由港麦克莫兰", "ODE2_damped_oscillation"),
    # 老牌 / 衰退
    ("INTC", "英特尔", "ODE1_exponential_decay"),
    ("IBM", "IBM", "ODE1_linear"),
    ("T", "AT&T", "ODE1_linear"),
    # 社交 / 博弈
    ("SNAP", "Snap", "Phase_transition_2nd"),
    ("PINS", "Pinterest", "ODE1_saturating"),
    ("GME", "GameStop", "Self_fulfilling_prophecy"),
]


def analyze_one(ticker, name):
    price, price_daily = fetch_price_history(ticker, years=15)
    if price.empty or price_daily.empty:
        return None
    yoy = compute_price_growth_yoy(price)
    if len(yoy) < 10:
        return None

    raw_breaks = run_pelt(yoy["yoy"].values, pen=6.0)
    top = top_k_breaks(yoy["yoy"].values, raw_breaks, k=4, min_score=1.5)
    break_dates = [(yoy["date"].iloc[b], score) for b, score in top]

    validations = []
    for b_date, score in break_dates:
        v = validate_break_point(price_daily, b_date, window_days=60)
        if v:
            v["date"] = b_date
            v["score"] = score
            v["ticker"] = ticker
            v["name"] = name
            validations.append(v)
    return validations


def main():
    all_v = []
    per_ticker = {}

    print(f"跑 {len(TICKERS)} 家公司…\n")
    for ticker, name, fam in TICKERS:
        print(f"  [{ticker:6}] {name}… ", end="", flush=True)
        try:
            vs = analyze_one(ticker, name)
            if vs is None:
                print("数据不足，跳过")
                continue
            per_ticker[ticker] = (name, fam, vs)
            all_v.extend(vs)
            regime_changes = sum(1 for v in vs if v["regime_change"] != "无明显变化")
            print(f"{len(vs)} 拐点，{regime_changes} 个有 regime 变化")
        except Exception as e:
            print(f"失败: {e}")
            continue

    # 聚合统计
    n = len(all_v)
    if n == 0:
        print("\n没有有效数据。")
        return

    sign_flips = sum(
        1 for v in all_v
        if np.sign(v["return_before"]) != np.sign(v["return_after"])
        and abs(v["return_before"]) > 0.02
        and abs(v["return_after"]) > 0.02
    )
    regime_changes = sum(1 for v in all_v if v["regime_change"] != "无明显变化")
    ret_diffs = [abs(v["return_after"] - v["return_before"]) for v in all_v]
    vol_ratios = [v["vol_after"] / (v["vol_before"] + 1e-6) for v in all_v]

    # 分类型
    type_counts = {}
    for v in all_v:
        t = v["regime_change"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # 按 score 分层：高分（>3）、中分（2-3）、低分（1.5-2）的 regime change 比例
    tiers = {"高分 (>3)": [], "中分 (2-3)": [], "低分 (1.5-2)": []}
    for v in all_v:
        s = v["score"]
        if s > 3:
            tiers["高分 (>3)"].append(v)
        elif s > 2:
            tiers["中分 (2-3)"].append(v)
        else:
            tiers["低分 (1.5-2)"].append(v)

    # 输出
    out = []
    out.append(f"# PELT POC 扩展版 — 25 家公司聚合结果\n")
    out.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    out.append(f"样本：{len(per_ticker)}/{len(TICKERS)} 家公司有足够数据\n")
    out.append(f"总拐点数：{n}\n\n")

    out.append(f"## 🎯 核心指标\n\n")
    out.append(f"| 指标 | 数字 | 比例 |\n")
    out.append(f"|-----|-----|-----|\n")
    out.append(f"| 总拐点数 | {n} | — |\n")
    out.append(f"| **有显著 regime 变化** | **{regime_changes}** | **{regime_changes/n*100:.1f}%** |\n")
    out.append(f"| 趋势反转（涨跌方向翻转）| {sign_flips} | {sign_flips/n*100:.1f}% |\n")
    out.append(f"| 拐点前后累计收益差（中位数）| {np.median(ret_diffs)*100:.1f}pp | — |\n")
    out.append(f"| 拐点前后波动率比（中位数）| {np.median(vol_ratios):.2f}x | — |\n\n")

    out.append(f"## 📊 Regime 变化类型分布\n\n")
    out.append(f"| 类型 | 数量 | 比例 |\n|---|---|---|\n")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        out.append(f"| {t} | {c} | {c/n*100:.1f}% |\n")
    out.append("\n")

    out.append(f"## 🔬 按置信度分层（更重要）\n\n")
    out.append(f"高置信拐点是不是更靠谱？\n\n")
    out.append(f"| 分层 | 样本数 | 有 regime 变化 | 比例 |\n|---|---|---|---|\n")
    for tier_name, vs in tiers.items():
        if not vs:
            continue
        rc = sum(1 for v in vs if v["regime_change"] != "无明显变化")
        out.append(f"| {tier_name} | {len(vs)} | {rc} | **{rc/len(vs)*100:.1f}%** |\n")
    out.append("\n")

    # 按 family 统计
    out.append(f"## 🏷️ 按 dynamics_family 分层\n\n")
    out.append(f"不同类型公司的拐点是否更显著？\n\n")
    fam_stats = {}
    for ticker, (name, fam, vs) in per_ticker.items():
        if fam not in fam_stats:
            fam_stats[fam] = {"n": 0, "rc": 0, "tickers": []}
        fam_stats[fam]["n"] += len(vs)
        fam_stats[fam]["rc"] += sum(1 for v in vs if v["regime_change"] != "无明显变化")
        fam_stats[fam]["tickers"].append(ticker)
    out.append(f"| Family | 拐点总数 | 有 regime 变化 | 比例 | 公司 |\n|---|---|---|---|---|\n")
    for fam, st in sorted(fam_stats.items(), key=lambda x: -x[1]["rc"] / max(x[1]["n"], 1)):
        if st["n"] == 0:
            continue
        out.append(
            f"| {fam} | {st['n']} | {st['rc']} | "
            f"**{st['rc']/st['n']*100:.0f}%** | {', '.join(st['tickers'])} |\n"
        )
    out.append("\n")

    # 每家公司明细
    out.append(f"## 📋 每家公司明细\n\n")
    for ticker, (name, fam, vs) in per_ticker.items():
        if not vs:
            continue
        rc = sum(1 for v in vs if v["regime_change"] != "无明显变化")
        out.append(f"### {ticker} · {name}（{fam}）\n\n")
        out.append(f"{len(vs)} 个拐点，{rc} 个有 regime 变化\n\n")
        out.append(f"| 日期 | 置信度 | 前 60 天 | 后 60 天 | 判断 |\n|---|---|---|---|---|\n")
        for v in vs:
            out.append(
                f"| {v['date'].strftime('%Y-%m')} | {v['score']:.2f} | "
                f"{v['return_before']*100:+.1f}% | {v['return_after']*100:+.1f}% | "
                f"**{v['regime_change']}** |\n"
            )
        out.append("\n")

    # 最终判断
    out.append(f"## ⚖️ 最终判断\n\n")
    rc_rate = regime_changes / n
    if rc_rate >= 0.60:
        out.append(f"✅ **算法可用**：{rc_rate*100:.0f}% 的拐点对应真实 regime 变化，可以上 MVP。\n")
    elif rc_rate >= 0.45:
        out.append(f"⚠️ **弱可用**：{rc_rate*100:.0f}% regime 变化比例。7 家样本的 50% 稳住了，说明算法底子在。")
        out.append(f"但单一信号不够做付费产品，下一步需要加 **多指标交叉验证** 或 **领域事件匹配**。\n")
    else:
        out.append(f"❌ **信号不够**：{rc_rate*100:.0f}% regime 变化比例。7 家样本的 50% 是巧合，")
        out.append(f"这条路走不通，需要换算法（比如 critical slowing down 的方差+自相关双信号）。\n")

    report = "".join(out)
    path = os.path.join(os.path.dirname(__file__), "REPORT_SCALE.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告写入: {path}")
    print(f"\n=== 核心数字 ===")
    print(f"总拐点数: {n}")
    print(f"有 regime 变化: {regime_changes} ({regime_changes/n*100:.1f}%)")
    print(f"趋势反转: {sign_flips} ({sign_flips/n*100:.1f}%)")


if __name__ == "__main__":
    main()
