"""
PELT POC 多信号版 — 3 个信号交叉验证 + (可选) LLM 事件匹配。

信号：
  A. YoY 股价变化（月度）
  B. 60 日滚动波动率（月度聚合）
  C. 60 日滚动夏普比 = 收益 / 波动率（月度聚合）

规则：
  高置信拐点 = 3 信号里 ≥2 个在 ±60 天内都报警

跑法：python3 run_multi.py [--llm]
"""
import os
import sys
import json
import warnings
from datetime import datetime
from collections import defaultdict

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
from run_scale import TICKERS


def compute_rolling_vol_monthly(price_daily, window=60):
    """从日度股价算 60 日滚动波动率，再聚合到月度。"""
    if price_daily.empty:
        return pd.DataFrame()
    df = price_daily.sort_values("date").reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ret"] = df["price"].pct_change()
    df["vol"] = df["ret"].rolling(window).std()
    df = df.dropna(subset=["vol"])
    if df.empty:
        return pd.DataFrame()
    # 月末值
    df = df.set_index("date")
    monthly = df["vol"].resample("ME").last().dropna()
    return monthly.reset_index().rename(columns={"vol": "value"})


def compute_rolling_sharpe_monthly(price_daily, window=60):
    """60 日滚动夏普比 = 均值收益 / 波动率，聚合月度。"""
    if price_daily.empty:
        return pd.DataFrame()
    df = price_daily.sort_values("date").reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ret"] = df["price"].pct_change()
    df["mean_ret"] = df["ret"].rolling(window).mean()
    df["vol"] = df["ret"].rolling(window).std()
    df["sharpe"] = df["mean_ret"] / (df["vol"] + 1e-9)
    df = df.dropna(subset=["sharpe"])
    if df.empty:
        return pd.DataFrame()
    df = df.set_index("date")
    monthly = df["sharpe"].resample("ME").last().dropna()
    return monthly.reset_index().rename(columns={"sharpe": "value"})


def find_breaks_with_scores(series, pen, k=4, min_score=1.5):
    """跑 PELT + 置信度过滤，返回 [(date, score), ...]."""
    if len(series) < 10:
        return []
    values = series["value"].values if "value" in series.columns else series["yoy"].values
    raw = run_pelt(values, pen=pen)
    top = top_k_breaks(values, raw, k=k, min_score=min_score)
    return [(series["date"].iloc[b], score) for b, score in top]


def cross_signal_filter(breaks_by_signal, window_days=60, min_signals=2):
    """找出在 ≥min_signals 个信号上都有报警的拐点。

    breaks_by_signal: {'yoy': [(date, score), ...], 'vol': [...], 'sharpe': [...]}
    返回: [(representative_date, avg_score, signals_agreed)]
    """
    all_breaks = []
    for sig, items in breaks_by_signal.items():
        for d, s in items:
            all_breaks.append((d, s, sig))
    if not all_breaks:
        return []
    all_breaks.sort(key=lambda x: x[0])

    # 聚类：相邻 ±60 天的拐点归为一组
    clusters = []
    for d, s, sig in all_breaks:
        placed = False
        for c in clusters:
            # 若 d 与 cluster 中任何 point 的时差 ≤ window_days
            if any(abs((d - cd).days) <= window_days for cd, _, _ in c):
                c.append((d, s, sig))
                placed = True
                break
        if not placed:
            clusters.append([(d, s, sig)])

    # 只保留包含 ≥min_signals 种不同信号源的 cluster
    result = []
    for c in clusters:
        unique_sigs = set(sig for _, _, sig in c)
        if len(unique_sigs) >= min_signals:
            # 取 cluster 的中间日期（或最高分的日期）
            c_sorted = sorted(c, key=lambda x: -x[1])
            top_date = c_sorted[0][0]
            avg_score = np.mean([s for _, s, _ in c])
            result.append({
                "date": top_date,
                "avg_score": avg_score,
                "signals": sorted(unique_sigs),
                "n_signals": len(unique_sigs),
            })
    return result


def analyze_ticker(ticker, name, fam):
    price, price_daily = fetch_price_history(ticker, years=15)
    if price.empty or price_daily.empty:
        return None

    yoy = compute_price_growth_yoy(price)
    vol = compute_rolling_vol_monthly(price_daily)
    sharpe = compute_rolling_sharpe_monthly(price_daily)

    breaks_by_sig = {
        "yoy": find_breaks_with_scores(yoy, pen=6.0),
        "vol": find_breaks_with_scores(vol, pen=3.0),
        "sharpe": find_breaks_with_scores(sharpe, pen=2.0),
    }

    # 多信号交叉过滤 — 窗口放宽到 120 天（4 个月）
    high_conf = cross_signal_filter(breaks_by_sig, window_days=120, min_signals=2)

    # 对每个高置信拐点做 60 天前后验证
    validations = []
    for hc in high_conf:
        v = validate_break_point(price_daily, hc["date"], window_days=60)
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
        "breaks_by_signal": breaks_by_sig,
        "high_conf": validations,
    }


def main():
    results = []
    print(f"跑 {len(TICKERS)} 家公司（多信号版）…\n")
    for ticker, name, fam in TICKERS:
        print(f"  [{ticker:6}] {name}… ", end="", flush=True)
        try:
            r = analyze_ticker(ticker, name, fam)
            if r is None:
                print("数据不足")
                continue
            raw_counts = {sig: len(items) for sig, items in r["breaks_by_signal"].items()}
            hc = r["high_conf"]
            rc = sum(1 for v in hc if v["regime_change"] != "无明显变化")
            print(
                f"原始信号 yoy={raw_counts['yoy']}, vol={raw_counts['vol']}, sharpe={raw_counts['sharpe']} "
                f"→ 高置信 {len(hc)} 个，{rc} 有 regime 变化"
            )
            results.append(r)
        except Exception as e:
            print(f"失败: {e}")
            continue

    # 聚合
    all_hc = []
    for r in results:
        all_hc.extend(r["high_conf"])

    n = len(all_hc)
    if n == 0:
        print("\n没有高置信拐点，参数可能太严。")
        return

    regime_changes = sum(1 for v in all_hc if v["regime_change"] != "无明显变化")
    sign_flips = sum(
        1 for v in all_hc
        if np.sign(v["return_before"]) != np.sign(v["return_after"])
        and abs(v["return_before"]) > 0.02
        and abs(v["return_after"]) > 0.02
    )
    ret_diffs = [abs(v["return_after"] - v["return_before"]) for v in all_hc]

    # 按信号数分组
    by_n_sig = defaultdict(list)
    for v in all_hc:
        by_n_sig[v["n_signals"]].append(v)

    # 输出
    lines = []
    lines.append("# PELT POC 多信号版 — 25 家公司\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

    lines.append("## 🎯 对比：单信号 vs 多信号\n\n")
    lines.append("| 版本 | 拐点数 | 有 regime 变化 | 比例 |\n|---|---|---|---|\n")
    lines.append(f"| 单信号（YoY only）| 48 | 26 | **54.2%** |\n")
    lines.append(f"| **多信号（≥2 个信号一致）** | **{n}** | **{regime_changes}** | **{regime_changes/n*100:.1f}%** |\n\n")

    lift = (regime_changes/n - 0.542) / 0.542 * 100 if n > 0 else 0
    if regime_changes / n >= 0.70:
        verdict = f"✅ **大幅提升**：从 54% 到 {regime_changes/n*100:.0f}%（+{lift:.0f}%），信号显著变强"
    elif regime_changes / n >= 0.60:
        verdict = f"🟡 **小幅提升**：{regime_changes/n*100:.0f}%（+{lift:.0f}%），方向对但幅度小"
    else:
        verdict = f"❌ **没提升**：{regime_changes/n*100:.0f}%，多信号过滤没用"
    lines.append(f"{verdict}\n\n")

    lines.append("## 📊 按信号一致数分层\n\n")
    lines.append("| 一致信号数 | 样本 | 有 regime 变化 | 比例 |\n|---|---|---|---|\n")
    for k in sorted(by_n_sig.keys()):
        vs = by_n_sig[k]
        rc = sum(1 for v in vs if v["regime_change"] != "无明显变化")
        lines.append(f"| {k} 信号一致 | {len(vs)} | {rc} | **{rc/len(vs)*100:.1f}%** |\n")
    lines.append("\n")

    # regime 类型
    type_counts = defaultdict(int)
    for v in all_hc:
        type_counts[v["regime_change"]] += 1
    lines.append("## 🔬 Regime 变化类型\n\n")
    lines.append("| 类型 | 数量 | 比例 |\n|---|---|---|\n")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {t} | {c} | {c/n*100:.1f}% |\n")
    lines.append("\n")

    # 按 family
    fam_stats = defaultdict(lambda: {"n": 0, "rc": 0, "tickers": set()})
    for r in results:
        fam = r["family"]
        for v in r["high_conf"]:
            fam_stats[fam]["n"] += 1
            if v["regime_change"] != "无明显变化":
                fam_stats[fam]["rc"] += 1
            fam_stats[fam]["tickers"].add(r["ticker"])
    lines.append("## 🏷️ 按 dynamics_family 分层\n\n")
    lines.append("| Family | 拐点 | 有 regime 变化 | 比例 | 公司 |\n|---|---|---|---|---|\n")
    for fam, st in sorted(fam_stats.items(), key=lambda x: -(x[1]["rc"] / max(x[1]["n"], 1))):
        if st["n"] == 0:
            continue
        lines.append(
            f"| {fam} | {st['n']} | {st['rc']} | "
            f"**{st['rc']/st['n']*100:.0f}%** | {', '.join(sorted(st['tickers']))} |\n"
        )
    lines.append("\n")

    # 每家公司明细
    lines.append("## 📋 每家公司高置信拐点\n\n")
    for r in results:
        hc = r["high_conf"]
        if not hc:
            continue
        lines.append(f"### {r['ticker']} · {r['name']}（{r['family']}）\n\n")
        lines.append("| 日期 | 置信度 | 信号 | 前 60 天 | 后 60 天 | 判断 |\n|---|---|---|---|---|---|\n")
        for v in hc:
            lines.append(
                f"| {v['date'].strftime('%Y-%m')} | {v['avg_score']:.2f} | "
                f"{'+'.join(v['signals'])} | "
                f"{v['return_before']*100:+.1f}% | {v['return_after']*100:+.1f}% | "
                f"**{v['regime_change']}** |\n"
            )
        lines.append("\n")

    # 保存原始数据给 LLM 步骤用
    hc_data = [
        {
            "ticker": v["ticker"],
            "name": v["name"],
            "family": v["family"],
            "date": v["date"].strftime("%Y-%m-%d"),
            "avg_score": v["avg_score"],
            "n_signals": v["n_signals"],
            "signals": v["signals"],
            "return_before": v["return_before"],
            "return_after": v["return_after"],
            "regime_change": v["regime_change"],
        }
        for v in all_hc
    ]
    with open(os.path.join(os.path.dirname(__file__), "high_conf_breaks.json"), "w") as f:
        json.dump(hc_data, f, ensure_ascii=False, indent=2, default=str)

    path = os.path.join(os.path.dirname(__file__), "REPORT_MULTI.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))
    print(f"\n报告写入: {path}")
    print(f"高置信拐点数据: high_conf_breaks.json")
    print(f"\n=== 核心结论 ===")
    print(f"高置信拐点: {n}（上轮单信号 48）")
    print(f"regime 变化: {regime_changes} / {n} = {regime_changes/n*100:.1f}% （上轮 54%）")


if __name__ == "__main__":
    main()
