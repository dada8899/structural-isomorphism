"""
不用 LLM，用"已知宏观事件"给拐点分类：
  - 拐点在宏观事件 ±60 天内 → 很可能只是 beta 反应，不是公司自身结构变化
  - 拐点不在任何宏观事件附近 → 更可能是真实的公司结构变化（真信号）

宏观事件列表（2010-2026 重大市场事件）。
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np

# 已知重大市场事件（日期 ± 60 天影响大多数股票）
MACRO_EVENTS = [
    ("2011-08-01", "美国主权评级被标普下调"),
    ("2015-08-01", "中国股灾 + 人民币贬值"),
    ("2016-06-23", "英国脱欧公投"),
    ("2016-11-08", "川普当选"),
    ("2018-02-01", "美股 volmageddon"),
    ("2018-12-01", "Fed 加息 + 科技股恐慌"),
    ("2020-03-01", "COVID crash"),
    ("2020-06-01", "COVID 反弹启动"),
    ("2021-11-01", "Fed 加息预期升温 + 成长股崩"),
    ("2022-01-01", "Fed tightening + 俄乌战争预期"),
    ("2022-06-01", "Fed 暴力加息 + 熊市确认"),
    ("2023-03-01", "硅谷银行危机"),
    ("2023-11-01", "AI 行情启动 + Fed 停止加息"),
]


def is_macro(date_str):
    d = datetime.strptime(date_str[:10], "%Y-%m-%d") if "-" in date_str[:10] else None
    if d is None:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False
    for md_str, desc in MACRO_EVENTS:
        md = datetime.strptime(md_str, "%Y-%m-%d")
        if abs((d - md).days) <= 60:
            return desc
    return False


def main():
    with open(os.path.join(os.path.dirname(__file__), "high_conf_breaks.json")) as f:
        breaks = json.load(f)

    n = len(breaks)
    lines = []
    lines.append("# PELT POC — 宏观事件过滤\n\n")
    lines.append(f"对 {n} 个高置信拐点判断：是不是只是对宏观事件的反应？\n\n")

    macro_driven = 0
    real_signal = 0
    for b in breaks:
        macro = is_macro(b["date"])
        b["macro_event"] = macro if macro else None
        b["is_real_signal"] = not macro and b["regime_change"] != "无明显变化"
        if macro:
            macro_driven += 1
        else:
            real_signal += 1

    # 四象限
    rc_non_macro = sum(1 for b in breaks if not b["macro_event"] and b["regime_change"] != "无明显变化")
    rc_macro = sum(1 for b in breaks if b["macro_event"] and b["regime_change"] != "无明显变化")
    no_rc_non_macro = sum(1 for b in breaks if not b["macro_event"] and b["regime_change"] == "无明显变化")
    no_rc_macro = sum(1 for b in breaks if b["macro_event"] and b["regime_change"] == "无明显变化")

    lines.append("## 🎯 核心筛选结果\n\n")
    lines.append(f"- 总拐点：{n}\n")
    lines.append(f"- **宏观事件驱动**（在 2020-COVID / 2022-Fed / 2023-SVB 等事件 ±60 天）：{macro_driven} = {macro_driven/n*100:.0f}%\n")
    lines.append(f"- **非宏观期拐点**（公司自身结构变化）：{real_signal} = {real_signal/n*100:.0f}%\n\n")

    lines.append("## 📊 四象限\n\n")
    lines.append("| | 股价有 regime 变化 | 股价无变化 |\n|---|---|---|\n")
    lines.append(f"| **非宏观期** | **{rc_non_macro}** 🎯 真信号 | {no_rc_non_macro} |\n")
    lines.append(f"| **宏观事件附近** | {rc_macro}（可能 beta 反应）| {no_rc_macro} |\n\n")

    lines.append(f"**真信号**（非宏观 + regime 变化）：**{rc_non_macro}/{n} = {rc_non_macro/n*100:.0f}%**\n\n")

    # 按公司分组列真信号
    lines.append("## 🎯 筛出的「公司自身」结构信号\n\n")
    lines.append("这些拐点不在宏观事件附近，且股价有真实 regime 变化——最值得深入看的。\n\n")
    real_signals = [b for b in breaks if b["is_real_signal"]]
    by_ticker = defaultdict(list)
    for b in real_signals:
        by_ticker[b["ticker"]].append(b)

    lines.append(f"共 **{len(real_signals)}** 个真信号，来自 **{len(by_ticker)}** 家公司：\n\n")
    lines.append("| 公司 | 日期 | 置信度 | 前 60 天 | 后 60 天 | 类型 |\n|---|---|---|---|---|---|\n")
    for ticker in sorted(by_ticker.keys()):
        for b in by_ticker[ticker]:
            lines.append(
                f"| {ticker} | {b['date']} | {b['avg_score']:.2f} | "
                f"{b['return_before']*100:+.1f}% | {b['return_after']*100:+.1f}% | "
                f"**{b['regime_change']}** |\n"
            )
    lines.append("\n")

    # 宏观期拐点（说明性的）
    lines.append("## ⚠️ 宏观期拐点（可能只是 beta 反应）\n\n")
    macro_breaks = [b for b in breaks if b["macro_event"]]
    macro_event_counts = defaultdict(int)
    for b in macro_breaks:
        macro_event_counts[b["macro_event"]] += 1
    lines.append("| 宏观事件 | 关联拐点数 |\n|---|---|\n")
    for ev, c in sorted(macro_event_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {ev} | {c} |\n")
    lines.append("\n")

    # 最终判断
    lines.append("## ⚖️ 最终判断\n\n")
    true_rate = rc_non_macro / n
    lines.append(f"经过三层过滤（PELT → 多信号交叉 → 宏观事件排除），\n")
    lines.append(f"{rc_non_macro}/{n} = **{true_rate*100:.0f}%** 的拐点是「公司自身结构变化」。\n\n")
    if true_rate >= 0.35:
        lines.append(f"✅ **可用级别**：这个 {rc_non_macro} 个「真信号」拐点可以直接输出给用户，\n")
        lines.append(f"每个都能配一段「为什么是这个时间点」的解释。\n")
    else:
        lines.append(f"⚠️ 真信号比例偏低，需要更多信号（营收、用户数）提升过滤精度。\n")

    path = os.path.join(os.path.dirname(__file__), "REPORT_FINAL.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(lines))

    # 保存 enriched 数据
    with open(os.path.join(os.path.dirname(__file__), "high_conf_breaks_filtered.json"), "w") as f:
        json.dump(breaks, f, ensure_ascii=False, indent=2)

    print(f"报告: {path}")
    print(f"\n=== 最终数字 ===")
    print(f"高置信拐点: {n}")
    print(f"宏观事件驱动: {macro_driven} ({macro_driven/n*100:.0f}%)")
    print(f"公司自身结构信号: {real_signal}")
    print(f"真信号（非宏观 + regime 变化）: {rc_non_macro} ({rc_non_macro/n*100:.0f}%)")


if __name__ == "__main__":
    main()
