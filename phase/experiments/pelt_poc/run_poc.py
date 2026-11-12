"""
PELT Structural Break POC
==========================

Goal: 验证"用 PELT 算法自动找公司收入曲线里的结构拐点"是否靠谱。

方法：
1. 挑 5-8 家我们心里有数的公司（每家都有一个"应该被检测出来"的相变）
2. 从 yfinance 拉 10-15 年的季度营收
3. 算 YoY 营收增长率
4. 跑 PELT，看它找到的拐点是不是跟我们预期的对上
5. 画图 + 输出中文结论

跑法: python3 run_poc.py
"""
import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import ruptures as rpt

# macOS 上的中文字体
import platform
if platform.system() == "Darwin":
    plt.rcParams["font.sans-serif"] = ["PingFang SC", "Hiragino Sans GB", "STHeiti", "Arial Unicode MS"]
else:
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 每家公司我们"心里预期"应该出现的结构拐点 —— 用来事后打分
# 格式: (ticker, 公司名, 业务指标描述, 预期拐点年份 + 文字描述)
CASES = [
    ("NFLX", "Netflix",
     "从 DVD 租赁转流媒体 + 全球扩张后饱和",
     [("2011", "DVD/Qwikster 事件 + 流媒体转型"),
      ("2015", "全球扩张期启动，加速增长"),
      ("2022", "订阅用户负增长，饱和显现")]),
    ("TSLA", "Tesla",
     "交付量从小众爆发到主流",
     [("2018", "Model 3 量产爬坡，交付拐点"),
      ("2021", "全球扩张进入超级增长")]),
    ("PTON", "Peloton",
     "COVID 红利 + 崩塌",
     [("2020", "疫情居家需求爆发"),
      ("2021", "疫情消退需求崩塌")]),
    ("NVDA", "NVIDIA",
     "从游戏显卡转数据中心/AI",
     [("2016", "数据中心业务起飞"),
      ("2018", "挖矿泡沫 + 破裂"),
      ("2023", "AI 需求大爆发")]),
    ("SHOP", "Shopify",
     "电商 SaaS 从小卖家到企业级",
     [("2020", "COVID 电商大爆发"),
      ("2022", "需求正常化后回调")]),
    ("SBUX", "Starbucks",
     "成熟连锁，理论上不该有明显结构断点",
     [("—", "预期不应该有强信号（对照组）")]),
    ("META", "Meta",
     "Facebook 主站饱和 + 广告生意成熟",
     [("2018", "DAU 在美国/加拿大饱和"),
      ("2022", "用户流向 TikTok 流失期")]),
]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)


def fetch_quarterly_revenue(ticker, years=15):
    """从 yfinance 拉季度营收，回退到 earnings 或 financials。

    yfinance 的 quarterly data 一般只有最近 4-8 个季度，所以我们还叠加年度数据
    补足长历史。
    """
    cache_path = os.path.join(DATA_DIR, f"{ticker}_revenue.csv")
    if os.path.exists(cache_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        return df

    tk = yf.Ticker(ticker)
    rows = []

    # 1. Quarterly (last ~8 quarters)
    try:
        q = tk.quarterly_financials
        if q is not None and not q.empty and "Total Revenue" in q.index:
            for col, val in q.loc["Total Revenue"].items():
                if pd.notna(val):
                    rows.append({"date": pd.to_datetime(col), "revenue": float(val), "source": "quarterly"})
    except Exception as e:
        print(f"  [{ticker}] quarterly_financials failed: {e}")

    # 2. Annual (further back)
    try:
        a = tk.financials
        if a is not None and not a.empty and "Total Revenue" in a.index:
            for col, val in a.loc["Total Revenue"].items():
                if pd.notna(val):
                    rows.append({"date": pd.to_datetime(col), "revenue": float(val), "source": "annual"})
    except Exception as e:
        print(f"  [{ticker}] financials failed: {e}")

    # 3. Income statement (older)
    try:
        inc = tk.income_stmt
        if inc is not None and not inc.empty and "Total Revenue" in inc.index:
            for col, val in inc.loc["Total Revenue"].items():
                if pd.notna(val):
                    rows.append({"date": pd.to_datetime(col), "revenue": float(val), "source": "income_stmt"})
    except Exception:
        pass

    if not rows:
        return pd.DataFrame(columns=["date", "revenue", "source"])

    df = pd.DataFrame(rows).drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
    df.to_csv(cache_path, index=False)
    return df


def fetch_price_history(ticker, years=15):
    """拉 15 年的月度股价（用于 YoY 和拐点检测） + 日度股价（用于拐点前后验证）。"""
    cache_path = os.path.join(DATA_DIR, f"{ticker}_price.csv")
    daily_path = os.path.join(DATA_DIR, f"{ticker}_price_daily.csv")

    if os.path.exists(cache_path) and os.path.exists(daily_path):
        df = pd.read_csv(cache_path, parse_dates=["date"])
        daily = pd.read_csv(daily_path, parse_dates=["date"])
        return df, daily

    tk = yf.Ticker(ticker)

    # 月度（长序列，用于 PELT）
    hist_m = tk.history(period="max", interval="1mo")
    df = pd.DataFrame(columns=["date", "price"])
    if hist_m is not None and not hist_m.empty:
        df = hist_m[["Close"]].reset_index()
        df.columns = ["date", "price"]
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
        df = df[df["date"] >= cutoff].reset_index(drop=True)
        df.to_csv(cache_path, index=False)

    # 日度（短窗口内 60 天 = 40+ 交易日，用于验证）
    hist_d = tk.history(period="max", interval="1d")
    daily = pd.DataFrame(columns=["date", "price"])
    if hist_d is not None and not hist_d.empty:
        daily = hist_d[["Close"]].reset_index()
        daily.columns = ["date", "price"]
        daily["date"] = pd.to_datetime(daily["date"]).dt.tz_localize(None)
        cutoff = pd.Timestamp.now() - pd.DateOffset(years=years)
        daily = daily[daily["date"] >= cutoff].reset_index(drop=True)
        daily.to_csv(daily_path, index=False)

    return df, daily


def compute_price_growth_yoy(price_df):
    """从月度股价算 YoY 价格变化 — 作为营收增速的代理信号。"""
    if price_df.empty:
        return pd.DataFrame()
    df = price_df.sort_values("date").reset_index(drop=True).copy()
    df["price_yoy"] = df["price"].pct_change(12)
    df = df.dropna(subset=["price_yoy"])
    return df[["date", "price_yoy"]].rename(columns={"price_yoy": "yoy"})


def compute_yoy_growth(revenue_df):
    """把营收时序（季度或年度混合）算成 YoY 增长率。"""
    if revenue_df.empty:
        return pd.DataFrame()
    df = revenue_df.sort_values("date").reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    # 对齐到季度：annual 数据重采样成 QE
    q = df["revenue"].resample("QE").last().dropna()
    if len(q) < 8:
        # 数据太稀疏，改用年度
        y = df["revenue"].resample("YE").last().dropna()
        if len(y) < 5:
            return pd.DataFrame()
        yoy = (y / y.shift(1) - 1.0).dropna()
        return yoy.reset_index().rename(columns={"revenue": "yoy"})

    yoy = (q / q.shift(4) - 1.0).dropna()
    return yoy.reset_index().rename(columns={"revenue": "yoy"})


def run_pelt(values, pen=3.0, model="rbf"):
    """在一维数值序列上跑 PELT，返回 break 的位置（索引）。

    pen 越大 → 越保守（找的拐点越少）；rbf 模型能检测均值+方差变化。
    """
    if len(values) < 8:
        return []
    signal = np.asarray(values).reshape(-1, 1)
    algo = rpt.Pelt(model=model, min_size=6).fit(signal)
    breaks = algo.predict(pen=pen)
    # ruptures 返回的最后一个 index 是序列末尾，不是真的断点；去掉
    return [b - 1 for b in breaks[:-1]]


def score_breaks(values, break_indices):
    """给每个拐点算一个"置信度"：拐点前后均值差 / 整体波动 × sqrt(样本数)。

    越大 = 拐点前后差异越显著，越可能是真实结构变化。
    返回 [(index, score), ...] 按 score 降序。
    """
    if not break_indices or len(values) < 8:
        return []
    values = np.asarray(values)
    global_std = np.std(values) + 1e-9
    scored = []
    for i, b in enumerate(break_indices):
        # 前后窗口：从前一个拐点到这个，这个到下一个拐点
        left_start = break_indices[i - 1] if i > 0 else 0
        right_end = break_indices[i + 1] if i + 1 < len(break_indices) else len(values)
        left = values[left_start:b]
        right = values[b:right_end]
        if len(left) < 3 or len(right) < 3:
            continue
        mean_diff = abs(np.mean(right) - np.mean(left))
        n_min = min(len(left), len(right))
        # T 统计量近似：差异 / 波动 × 样本平方根
        score = (mean_diff / global_std) * np.sqrt(n_min)
        scored.append((b, float(score)))
    return sorted(scored, key=lambda x: -x[1])


def top_k_breaks(values, break_indices, k=4, min_score=1.5):
    """只保留置信度最高的 k 个拐点，且置信度 >= min_score。"""
    scored = score_breaks(values, break_indices)
    kept = [(b, s) for b, s in scored if s >= min_score][:k]
    return sorted(kept, key=lambda x: x[0])  # 按时间重排


def plot_company(ticker, name, revenue_df, yoy_df, price_df, breaks_yoy, breaks_price, expected, out_path):
    fig, axes = plt.subplots(3, 1, figsize=(11, 10), sharex=True,
                              gridspec_kw={"height_ratios": [2, 2, 2.5]})

    # 顶部：营收绝对值
    ax1 = axes[0]
    if not revenue_df.empty:
        ax1.plot(revenue_df["date"], revenue_df["revenue"] / 1e9, "o-", color="#1f77b4", markersize=4)
    ax1.set_ylabel("季度营收 (十亿 USD)")
    ax1.set_title(f"{ticker} · {name} — 结构拐点检测 POC", fontsize=13, loc="left", fontweight="bold")
    ax1.grid(True, alpha=0.3)

    # 中间：YoY 增长率 + PELT 找到的拐点
    ax2 = axes[1]
    if not yoy_df.empty:
        ax2.plot(yoy_df["date"], yoy_df["yoy"] * 100, "o-", color="#2ca02c", markersize=4)
        ax2.axhline(0, color="gray", lw=0.6, linestyle="--")
        for b in breaks_yoy:
            if b < len(yoy_df):
                d = yoy_df["date"].iloc[b]
                ax2.axvline(d, color="red", alpha=0.5, lw=1.5)
                ax2.text(d, ax2.get_ylim()[1] * 0.85, d.strftime("%Y-%m"),
                         rotation=90, color="red", fontsize=8, va="top")
    ax2.set_ylabel("YoY 营收增长率 (%)")
    ax2.grid(True, alpha=0.3)

    # 底部：股价（log scale）+ PELT 在股价上的拐点
    ax3 = axes[2]
    if not price_df.empty:
        ax3.plot(price_df["date"], price_df["price"], "-", color="#ff7f0e", lw=1)
        ax3.set_yscale("log")
        for b in breaks_price:
            if b < len(price_df):
                d = price_df["date"].iloc[b]
                ax3.axvline(d, color="red", alpha=0.5, lw=1.5)
                ax3.text(d, ax3.get_ylim()[1] * 0.6, d.strftime("%Y-%m"),
                         rotation=90, color="red", fontsize=8, va="top")
    ax3.set_ylabel("股价 (USD, log)")
    ax3.set_xlabel("日期")
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    plt.tight_layout()
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close()


def validate_break_point(price_df, break_date, window_days=60):
    """给一个拐点日期，看拐点前后 60 天的股价表现：

    返回 dict:
      - return_before: 前 60 天的累计收益
      - return_after: 后 60 天的累计收益
      - vol_before: 前 60 天的日收益波动率
      - vol_after: 后 60 天的日收益波动率
      - regime_change: "趋势反转" / "波动率突增" / "继续同向" / "无明显变化"
    """
    if price_df.empty or break_date is None:
        return None
    df = price_df.sort_values("date").reset_index(drop=True).copy()
    df["date"] = pd.to_datetime(df["date"])

    bd = pd.Timestamp(break_date)
    before = df[(df["date"] >= bd - pd.Timedelta(days=window_days)) & (df["date"] < bd)]
    after = df[(df["date"] >= bd) & (df["date"] < bd + pd.Timedelta(days=window_days))]
    if len(before) < 2 or len(after) < 2:
        return None

    ret_before = float(before["price"].iloc[-1] / before["price"].iloc[0] - 1.0)
    ret_after = float(after["price"].iloc[-1] / after["price"].iloc[0] - 1.0)

    # 月度序列的日收益近似：用 pct_change
    ret_b_series = before["price"].pct_change().dropna()
    ret_a_series = after["price"].pct_change().dropna()
    vol_before = float(ret_b_series.std()) if len(ret_b_series) > 1 else 0.0
    vol_after = float(ret_a_series.std()) if len(ret_a_series) > 1 else 0.0

    # 判断类型
    if np.sign(ret_before) != np.sign(ret_after) and abs(ret_before - ret_after) > 0.10:
        regime = "趋势反转"
    elif vol_after > vol_before * 1.5:
        regime = "波动率突增"
    elif abs(ret_after - ret_before) > 0.15:
        regime = f"趋势{'加速' if abs(ret_after) > abs(ret_before) else '减速'}"
    else:
        regime = "无明显变化"

    return {
        "return_before": ret_before,
        "return_after": ret_after,
        "vol_before": vol_before,
        "vol_after": vol_after,
        "regime_change": regime,
    }


def score_vs_expected(detected_dates, expected):
    """PELT 找到的拐点日期 vs 我们预期的年份，看命中率。"""
    if expected == [("—", "预期不应该有强信号（对照组）")]:
        # 对照组：找到越少越好
        return ("对照组", f"检出 {len(detected_dates)} 个拐点（期望 ≤1 个才算好）")

    hits = []
    misses = []
    detected_years = set(d.year for d in detected_dates)
    for year, desc in expected:
        if year == "—":
            continue
        try:
            y = int(year)
        except Exception:
            continue
        # ±1 年算命中
        if any(abs(dy - y) <= 1 for dy in detected_years):
            hits.append(f"{year}✓ {desc}")
        else:
            misses.append(f"{year}✗ {desc}")
    return (f"{len(hits)}/{len(expected)} 命中", hits + misses)


def main():
    report_lines = []
    all_validations = []  # for aggregate stats
    report_lines.append("# PELT 结构拐点 POC — 中文结论\n")
    report_lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    report_lines.append("## 方法\n")
    report_lines.append("1. 从 yfinance 拉每家公司季度+年度营收\n")
    report_lines.append("2. 算 YoY 同比营收增长率\n")
    report_lines.append("3. 用 PELT（惩罚式线性时间算法，model=rbf）自动找「均值或方差明显变化」的拐点\n")
    report_lines.append("4. 和「我们心里预期的拐点」对比（±1 年算命中）\n\n")

    for ticker, name, desc, expected in CASES:
        print(f"\n=== {ticker} {name} ===")
        report_lines.append(f"## {ticker} · {name}\n")
        report_lines.append(f"**业务描述**：{desc}\n")

        rev = fetch_quarterly_revenue(ticker)
        price, price_daily = fetch_price_history(ticker)
        # yfinance 免费版营收历史不全。用 YoY 股价变化当代理（同 sector 同向性强）
        yoy_from_rev = compute_yoy_growth(rev)
        yoy_from_price = compute_price_growth_yoy(price)
        # 优先用营收；数据不够就退回股价
        yoy = yoy_from_rev if len(yoy_from_rev) >= 8 else yoy_from_price
        yoy_source = "营收 YoY" if len(yoy_from_rev) >= 8 else "股价 YoY（营收数据不足时的代理）"
        report_lines.append(f"**信号源**：{yoy_source}（{len(yoy)} 个数据点）\n")

        if yoy.empty:
            print(f"  [{ticker}] YoY 数据为空，跳过")
            report_lines.append(f"**结果**：数据不足，无法分析。\n\n")
            continue

        # 保守参数：先让 PELT 找候选，再用置信度过滤出 top-4
        pen_yoy = 6.0 if yoy_source.startswith("股价") else 4.0
        raw_breaks_yoy = run_pelt(yoy["yoy"].values, pen=pen_yoy)
        top_yoy = top_k_breaks(yoy["yoy"].values, raw_breaks_yoy, k=4, min_score=1.5)
        breaks_yoy_idx = [b for b, _ in top_yoy]
        yoy_scores = {b: s for b, s in top_yoy}

        raw_breaks_price = run_pelt(np.log(price["price"].values) if not price.empty else np.array([]), pen=5.0)
        top_price = top_k_breaks(np.log(price["price"].values), raw_breaks_price, k=4, min_score=1.5) if not price.empty else []
        breaks_price_idx = [b for b, _ in top_price]

        yoy_break_dates = [yoy["date"].iloc[i] for i in breaks_yoy_idx if i < len(yoy)]
        price_break_dates = [price["date"].iloc[i] for i in breaks_price_idx if i < len(price)]

        # 对每个 YoY 拐点做"后 60 天验证" —— 用日度数据，窗口内有 40+ 交易日
        validations = []
        for i, b_date in enumerate(yoy_break_dates):
            v = validate_break_point(price_daily, b_date, window_days=60)
            if v:
                v["date"] = b_date
                v["score"] = yoy_scores.get(breaks_yoy_idx[i], 0.0)
                v["ticker"] = ticker
                validations.append(v)
                all_validations.append(v)

        # 输出图
        img_path = os.path.join(OUT_DIR, f"{ticker}.png")
        plot_company(ticker, name, rev, yoy, price, breaks_yoy_idx, breaks_price_idx, expected, img_path)

        # 评分
        score_label, detail = score_vs_expected(yoy_break_dates, expected)

        report_lines.append(f"**预期拐点**：\n")
        for y, d in expected:
            report_lines.append(f"  - {y}: {d}\n")
        report_lines.append(f"\n**PELT 在 YoY 上找到的高置信度拐点**（Top 4，按置信度打分）：\n\n")
        if validations:
            report_lines.append("| 拐点日期 | 置信度 | 前 60 天累计 | 后 60 天累计 | 前波动率 | 后波动率 | 判断 |\n")
            report_lines.append("|---|---|---|---|---|---|---|\n")
            for v in validations:
                report_lines.append(
                    f"| {v['date'].strftime('%Y-%m')} | {v['score']:.2f} | "
                    f"{v['return_before']*100:+.1f}% | {v['return_after']*100:+.1f}% | "
                    f"{v['vol_before']*100:.1f}% | {v['vol_after']*100:.1f}% | "
                    f"**{v['regime_change']}** |\n"
                )
        else:
            report_lines.append("（未找到高置信度拐点）\n")

        report_lines.append(f"\n**PELT 在股价上找到的拐点**：")
        if price_break_dates:
            report_lines.append(" " + ", ".join(d.strftime("%Y-%m") for d in price_break_dates))
        else:
            report_lines.append(" （无）")
        report_lines.append(f"\n\n**命中评分**：{score_label}\n")
        if isinstance(detail, list):
            for d in detail:
                report_lines.append(f"  - {d}\n")
        else:
            report_lines.append(f"  - {detail}\n")
        report_lines.append(f"\n![{ticker} chart](out/{ticker}.png)\n\n---\n\n")

        print(f"  YoY 拐点: {[d.strftime('%Y-%m') for d in yoy_break_dates]}")
        print(f"  Price 拐点: {[d.strftime('%Y-%m') for d in price_break_dates]}")
        print(f"  评分: {score_label}")

    # 聚合统计：所有拐点的前后表现对比
    if all_validations:
        report_lines.insert(5, "\n## 🔬 关键验证：拐点真的有投资意义吗？\n\n")
        report_lines.insert(6, "对所有找到的高置信度拐点，统计「拐点前 60 天」vs「拐点后 60 天」的股价表现：\n\n")

        n = len(all_validations)
        ret_diffs = [abs(v["return_after"] - v["return_before"]) for v in all_validations]
        vol_ratios = [v["vol_after"] / (v["vol_before"] + 1e-6) for v in all_validations]
        sign_flips = sum(1 for v in all_validations
                          if np.sign(v["return_before"]) != np.sign(v["return_after"])
                          and abs(v["return_before"]) > 0.02
                          and abs(v["return_after"]) > 0.02)
        regime_changes = sum(1 for v in all_validations if v["regime_change"] != "无明显变化")

        report_lines.insert(7,
            f"- **总拐点数**：{n}\n"
            f"- **趋势反转（涨跌方向翻转）**：{sign_flips}/{n} = {sign_flips/n*100:.0f}%\n"
            f"- **有显著 regime 变化（趋势反转/波动率突增/趋势加速）**：{regime_changes}/{n} = {regime_changes/n*100:.0f}%\n"
            f"- **拐点前后累计收益差值中位数**：{np.median(ret_diffs)*100:.1f} 个百分点\n"
            f"- **拐点前后波动率比值中位数**：{np.median(vol_ratios):.2f}x（>1 表示拐点后更不稳）\n\n"
        )

        if regime_changes / n > 0.5:
            report_lines.insert(8, "**✅ 信号有效**：超过 50% 的拐点对应真实的 regime change，不是噪声。\n\n")
        elif regime_changes / n > 0.3:
            report_lines.insert(8, "**⚠️ 信号弱可用**：30-50% 的拐点对应 regime change，需要进一步过滤。\n\n")
        else:
            report_lines.insert(8, "**❌ 信号噪声大**：<30% 的拐点有真实意义，这个方向需要重新设计。\n\n")
        report_lines.insert(9, "---\n\n")

    # 最终报告
    report_path = os.path.join(os.path.dirname(__file__), "REPORT.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("".join(report_lines))
    print(f"\n报告已写入: {report_path}")


if __name__ == "__main__":
    main()
