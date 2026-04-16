"""
LLM 事件匹配验证
================

对 run_multi.py 找到的 26 个高置信拐点，让 LLM 回答：
"这家公司在这个日期前后发生了什么真实的大事？"

如果 LLM 能具体说出事件（财报 / 政策 / 产品 / CEO 变动等），就是真信号；
说不出或说模糊，就标记为噪声。

用 OpenRouter API（Claude Sonnet 4.5），每次调用约 $0.01，26 个拐点总计约 $0.30。
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    print("❌ 需要设置 OPENROUTER_API_KEY 环境变量")
    sys.exit(1)

INPUT = os.path.join(os.path.dirname(__file__), "high_conf_breaks.json")
OUTPUT = os.path.join(os.path.dirname(__file__), "llm_events.json")

SYSTEM = """你是一个金融研究员。用户会给你一个公司代码和一个日期，
你要回答：在这个日期前后 ±3 个月内，这家公司发生过什么真实的重大事件？

严格规则：
1. 必须是你确实知道的事件。如果不确定，直说"不确定"。
2. 事件要具体（财报数字、产品发布、CEO 变动、政策、并购等），不要"市场情绪变化"这种泛泛而谈。
3. 只输出 JSON，不要其他文字。

输出格式：
{
  "has_event": true/false,
  "confidence": "high" / "medium" / "low",
  "events": [
    {"date": "YYYY-MM", "description": "一句话说清楚发生了什么"}
  ],
  "note": "如果 has_event=false，简述为什么这段时间没明显事件"
}
"""


def call_llm(ticker, name, date_str):
    prompt = f"""公司：{name} ({ticker})
关键日期：{date_str}

请查这家公司在 {date_str} 前后 ±3 个月内（即 {date_str} 的前 3 个月到后 3 个月）发生了什么真实的重大事件。"""

    req_body = {
        "model": "anthropic/claude-sonnet-4.5",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(req_body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://beta.structural.bytedance.city",
            "X-Title": "phase-detector-pelt-poc",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```\s*$", "", content)
        return json.loads(content)
    except Exception as e:
        return {"error": str(e)[:200]}


def main():
    with open(INPUT) as f:
        breaks = json.load(f)
    print(f"共 {len(breaks)} 个高置信拐点，开始 LLM 验证…\n")

    # 缓存已有结果
    results = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT) as f:
            results = {item["key"]: item for item in json.load(f)}

    enriched = []
    for i, b in enumerate(breaks):
        key = f"{b['ticker']}_{b['date']}"
        if key in results and "error" not in results[key]:
            enriched.append(results[key])
            print(f"  [{i+1}/{len(breaks)}] {key} (缓存)")
            continue

        print(f"  [{i+1}/{len(breaks)}] {key}… ", end="", flush=True)
        result = call_llm(b["ticker"], b["name"], b["date"])
        if "error" in result:
            print(f"失败: {result['error']}")
            time.sleep(2)
            result = {"has_event": False, "confidence": "low", "events": [], "note": "LLM 调用失败"}
        else:
            has_event = result.get("has_event", False)
            conf = result.get("confidence", "?")
            n_events = len(result.get("events", []))
            print(f"has_event={has_event} conf={conf} events={n_events}")

        enriched_item = dict(b)
        enriched_item["llm"] = result
        enriched_item["key"] = key
        enriched.append(enriched_item)
        time.sleep(0.5)  # 友好一点

    # 保存
    with open(OUTPUT, "w") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    # 聚合报告
    n = len(enriched)
    with_event = sum(1 for e in enriched if e.get("llm", {}).get("has_event"))
    high_conf_event = sum(
        1 for e in enriched
        if e.get("llm", {}).get("has_event") and e.get("llm", {}).get("confidence") == "high"
    )

    # 交叉：regime change × LLM event
    rc_and_event = sum(
        1 for e in enriched
        if e["regime_change"] != "无明显变化" and e.get("llm", {}).get("has_event")
    )
    rc_no_event = sum(
        1 for e in enriched
        if e["regime_change"] != "无明显变化" and not e.get("llm", {}).get("has_event")
    )
    nrc_and_event = sum(
        1 for e in enriched
        if e["regime_change"] == "无明显变化" and e.get("llm", {}).get("has_event")
    )
    nrc_no_event = sum(
        1 for e in enriched
        if e["regime_change"] == "无明显变化" and not e.get("llm", {}).get("has_event")
    )

    # 写最终报告
    lines = []
    lines.append("# PELT POC 最终验证 — LLM 事件匹配\n")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

    lines.append("## 🎯 核心数字\n\n")
    lines.append(f"- 高置信拐点数：**{n}**\n")
    lines.append(f"- LLM 确认有真实事件：**{with_event}/{n} = {with_event/n*100:.0f}%**\n")
    lines.append(f"- LLM 高置信度事件：**{high_conf_event}/{n} = {high_conf_event/n*100:.0f}%**\n\n")

    lines.append("## 🔬 两个验证信号交叉\n\n")
    lines.append("如果一个拐点同时被 ①股价 regime 变化 ②LLM 事件匹配 确认，才是最可靠的。\n\n")
    lines.append("| | LLM 确认事件 | LLM 无事件 |\n|---|---|---|\n")
    lines.append(f"| **股价 regime 变化** | {rc_and_event} | {rc_no_event} |\n")
    lines.append(f"| **股价无变化** | {nrc_and_event} | {nrc_no_event} |\n\n")

    both_confirmed = rc_and_event
    either_confirmed = rc_and_event + rc_no_event + nrc_and_event
    lines.append(f"- **双重确认**（最可靠）：{both_confirmed}/{n} = {both_confirmed/n*100:.0f}%\n")
    lines.append(f"- **至少一个确认**：{either_confirmed}/{n} = {either_confirmed/n*100:.0f}%\n")
    lines.append(f"- **两个都不确认**（噪声）：{nrc_no_event}/{n} = {nrc_no_event/n*100:.0f}%\n\n")

    # 每个拐点明细（关键：这是给用户看的成果）
    lines.append("## 📋 每个拐点明细\n\n")
    # 按 ticker 分组
    by_ticker = {}
    for e in enriched:
        by_ticker.setdefault(e["ticker"], []).append(e)

    for ticker in sorted(by_ticker.keys()):
        items = by_ticker[ticker]
        if not items:
            continue
        name = items[0]["name"]
        lines.append(f"### {ticker} · {name}\n\n")
        for e in items:
            llm = e.get("llm", {})
            events = llm.get("events", [])
            rc = e["regime_change"]
            rc_sym = "✅" if rc != "无明显变化" else "❌"
            ev_sym = "✅" if llm.get("has_event") else "❌"
            both = "🎯" if rc != "无明显变化" and llm.get("has_event") else ""
            lines.append(f"**{e['date']}** · 股价{rc_sym}（{rc}） · LLM{ev_sym}（{llm.get('confidence','?')}） {both}\n\n")
            if events:
                for ev in events:
                    lines.append(f"  - 📅 {ev.get('date','?')}: {ev.get('description','')}\n")
            elif llm.get("note"):
                lines.append(f"  - 💭 {llm.get('note')}\n")
            lines.append("\n")

    # 保存报告
    report_path = os.path.join(os.path.dirname(__file__), "REPORT_FINAL.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("".join(lines))

    print(f"\n报告: {report_path}")
    print(f"\n=== 最终结论 ===")
    print(f"总拐点: {n}")
    print(f"LLM 确认事件: {with_event} ({with_event/n*100:.0f}%)")
    print(f"双重确认（股价+LLM）: {both_confirmed} ({both_confirmed/n*100:.0f}%)")
    print(f"双重否认（噪声）: {nrc_no_event} ({nrc_no_event/n*100:.0f}%)")


if __name__ == "__main__":
    main()
