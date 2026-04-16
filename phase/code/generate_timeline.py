"""
批量生成 20 家公司的历史相位快照。

每家公司：
  - LLM 输出 3-4 个关键相位切换点
  - 每个点一个 struct tuple（phase_state / dynamics_family / 关键数据）
  - 每次切换的触发条件说明

输出: phase/data/timeline_snapshots.jsonl（每行一个公司）

跑法：python3 generate_timeline.py [TICKER1 TICKER2 ...]
不带参数默认跑全部 20 家。
"""
import json
import os
import sys
import time
import urllib.request
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
OUT = DATA / "timeline_snapshots.jsonl"

API_KEY = os.environ.get("OPENROUTER_API_KEY")
if not API_KEY:
    # try to read from VPS-style .env
    env_path = ROOT.parent / "web" / "backend" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
if not API_KEY:
    print("ERROR: OPENROUTER_API_KEY not set"); sys.exit(1)

# 20 家公司清单（ticker + 中文名 + 行业 hint）
COMPANIES = [
    ("NFLX", "Netflix", "流媒体/内容订阅"),
    ("NVDA", "NVIDIA", "GPU/AI 数据中心"),
    ("PDD", "拼多多/Temu", "电商"),
    ("TSLA", "Tesla", "电动车"),
    ("PTON", "Peloton", "健身订阅"),
    ("1211.HK", "比亚迪 BYD", "新能源车/电池"),
    ("SHOP", "Shopify", "电商 SaaS"),
    ("3690.HK", "美团", "本地生活/即时零售"),
    ("SNOW", "Snowflake", "云数仓 SaaS"),
    ("LI", "理想汽车", "新能源车"),
    ("AAPL", "Apple", "消费电子"),
    ("AMZN", "Amazon", "电商 + AWS 云"),
    ("META", "Meta / Facebook", "社交 + 广告"),
    ("GOOGL", "Alphabet / Google", "搜索 + 广告"),
    ("MSFT", "Microsoft", "企业软件 + 云"),
    ("INTC", "Intel", "x86 芯片"),
    ("600519.SS", "贵州茅台", "白酒"),
    ("700.HK", "腾讯", "游戏 + 社交 + 广告"),
    ("ASML", "ASML", "光刻机"),
    ("BABA", "阿里巴巴", "电商 + 云 + 物流"),
]

SYS_PROMPT = """你是一个公司历史研究员，擅长用结构动力学的视角划分公司的发展阶段。

用户给你一家公司，你要找出 3-4 个「结构相位切换点」——不是任意年份，而是公司从一种动力学结构明显切换到另一种的真实节点。

**什么叫"结构相位切换"**：
- 从高速增长进入饱和（如 Netflix 2022 订户开始负增长）
- 从双稳态翻转到主流（如 Tesla 2018 Model 3 量产后从 niche → 主流）
- 从增长转衰退（如 Intel 2020s 从 x86 主导被 AMD / ARM 蚕食）
- 从一条增长曲线切到第二条（如 Amazon 2015 从电商为主切到云为主）

**不算结构切换的**：
- 季度业绩波动
- 短期股价涨跌
- 单一产品发布（除非开启新曲线）

**输出**：JSON 数组，每家公司 3-4 个快照，按年份从早到晚。

每个快照格式：
```json
{
  "year": 2015,
  "period_label": "2015-2018 全球扩张期",
  "phase_state": "growth_phase / stable / saturated / approaching_critical / post_transition / unstable / contracting",
  "dynamics_family": "ODE1_exponential_growth / ODE1_logistic / ODE1_saturating / Bistable_switch / Fold_bifurcation / Phase_transition_2nd / Self_fulfilling_prophecy / Hysteresis_loop / Hopf_bifurcation / Network_cascade / ODE1_linear / ODE1_exponential_decay / Heavy_tail_extremal / Power_law_distribution / PDE_reaction_diffusion / Game_theoretic_equilibrium",
  "one_line": "这个时期公司处于什么状态，一句话（≤30 字）",
  "canonical_equation": "对应的方程，如 dN/dt = r*N*(1-N/K)",
  "key_metrics": {
    "revenue_usd_b": 5.5,
    "key_number": "MAU 2亿",
    "stock_price": "$80",
    "other": "行业地位：全球第 2"
  },
  "trigger_to_next": "从这个阶段切到下个阶段的触发条件（如果是最后一个快照则为 null）。格式: '触发指标 + 阈值'，如 '全球订户 YoY 增速跌破 10%'",
  "why_this_phase": "为什么这时候是这个相位（2-3 句话，要有具体年份和数字）"
}
```

**硬规则**：
1. 每家公司 3-4 个快照，不多不少
2. 最后一个快照是"当前"（2025-2026）
3. 快照之间必须是真正不同的 phase_state 或 dynamics_family
4. key_metrics 要给真实数字（有年份）
5. trigger_to_next 要具体可观测（"DAU 突破 20 亿"，不要"市场环境变化"）
6. 不要凭空捏造数字，不确定时给个区间范围并说明
7. 只输出 JSON 数组，不要其他文字
"""


def call_llm(company_name, ticker, industry):
    user_msg = f"""公司: {company_name} ({ticker})
行业: {industry}

请给出这家公司从上市以来到 2026 年的 3-4 个结构相位切换点。只输出 JSON 数组，不要任何前置说明。"""

    req_body = {
        "model": "anthropic/claude-sonnet-4.5",
        "messages": [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 3000,
    }
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(req_body).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://beta.structural.bytedance.city",
            "X-Title": "phase-detector-timeline",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"].strip()
    # 去 markdown 代码块
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    return json.loads(content)


def main():
    selected = sys.argv[1:] if len(sys.argv) > 1 else [c[0] for c in COMPANIES]
    existing = {}
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                existing[d["ticker"]] = d

    results = dict(existing)
    for ticker, name, industry in COMPANIES:
        if ticker not in selected:
            continue
        if ticker in results and "snapshots" in results[ticker]:
            print(f"[skip] {ticker} (already in cache)")
            continue
        print(f"[gen ] {ticker} {name}… ", end="", flush=True)
        try:
            snapshots = call_llm(name, ticker, industry)
            results[ticker] = {
                "ticker": ticker,
                "name": name,
                "industry": industry,
                "snapshots": snapshots,
            }
            print(f"{len(snapshots)} snapshots ✓")
        except Exception as e:
            print(f"FAILED: {e}")
            time.sleep(1)
            continue
        time.sleep(0.5)

    # 按公司清单顺序写入
    with OUT.open("w", encoding="utf-8") as f:
        for ticker, name, industry in COMPANIES:
            if ticker in results:
                f.write(json.dumps(results[ticker], ensure_ascii=False) + "\n")
    print(f"\n写入 {OUT} — {len(results)} 家公司")


if __name__ == "__main__":
    main()
