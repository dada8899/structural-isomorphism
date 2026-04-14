"""Rebuild critical_signals.json from companies_struct.jsonl.

3 signal groups, each picks top N companies by confidence whose dynamics_family
matches the structural archetype.
"""
import json
from pathlib import Path

DATA = Path(__file__).parent.parent / "data"

GROUPS = {
    "runaway_feedback": {
        "title": "🔥 正反馈加速型",
        "desc": "增长机制自我强化。越增长越能吸引资源。典型风险：临界点前所有指标看起来都好，跨过就是断崖式反转。",
        "families": {
            "ODE1_exponential_growth",
            "Self_fulfilling_prophecy",
            "Network_cascade",
            "Power_law_distribution",
        },
        "max": 5,
    },
    "bistable_cusp": {
        "title": "⚖️ 双稳态切换型",
        "desc": "两个稳态并存，系统在某条件触发时会翻转过去就回不来。典型风险：缓慢推动下没有警告，跨过临界点后状态突变。",
        "families": {
            "Bistable_switch",
            "Hysteresis_loop",
            "Fold_bifurcation",
            "Phase_transition_1st",
        },
        "max": 5,
    },
    "critical_slowing_down": {
        "title": "📈 临界放缓型",
        "desc": "系统接近相变，恢复力下降，扰动后回到平衡的时间越来越长。典型风险：方差增大、自相关变高，是相变最早的预警。",
        "families": {
            "Phase_transition_2nd",
            "Hopf_bifurcation",
            "ODE1_logistic",
            "ODE1_saturating",
            "DDE_delayed_feedback",
        },
        "phase_filter": {"approaching_critical", "saturated"},
        "max": 5,
    },
}


def main():
    companies = []
    with open(DATA / "companies_struct.jsonl", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                companies.append(json.loads(line))

    out = {}
    used = set()
    for key, cfg in GROUPS.items():
        def key_of(c):
            return c.get("ticker", "").split(".")[0].upper()
        pool = [c for c in companies
                if c.get("dynamics_family") in cfg["families"]
                and key_of(c) not in used]
        if "phase_filter" in cfg:
            pool = [c for c in pool if c.get("phase_state") in cfg["phase_filter"]]
        pool.sort(key=lambda c: (
            -(c.get("confidence") or 0),
            -(c.get("market_cap_usd") or 0),
        ))
        picks = []
        seen_local = set()
        for c in pool:
            k = key_of(c)
            if k in seen_local:
                continue
            seen_local.add(k)
            picks.append(c)
            if len(picks) >= cfg["max"]:
                break
        for c in picks:
            used.add(key_of(c))
        out[key] = {
            "title": cfg["title"],
            "desc": cfg["desc"],
            "companies": picks,
        }
        print(f"{key}: {len(picks)} → {[c['ticker'] for c in picks]}")

    with open(DATA / "critical_signals.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nWrote critical_signals.json")


if __name__ == "__main__":
    main()
