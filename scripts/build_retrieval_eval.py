#!/usr/bin/env python3
"""Build the canonical bilingual retrieval evaluation set.

The source cases live in this file so reviewers can audit paired Chinese and
English intent labels together. The generated JSONL is deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "evaluation" / "retrieval-v1.jsonl"


# slug, zh query, en query, accepted type ids, require cross-domain, note
IN_SCOPE = [
    ("linear-response", "广告预算增加一倍时，合格线索数量是否也近似增加一倍？", "If ad spend doubles, will qualified leads increase roughly in direct proportion?", ["01"], True, "linear input-output response"),
    ("adaptation-tolerance", "用户持续收到同一种促销刺激后为什么越来越无感？", "Why do users become less responsive after repeated exposure to the same promotion?", ["03"], True, "adaptation and tolerance"),
    ("distance-decay", "配送中心离客户越远，服务影响为什么快速衰减？", "Why does service influence decay rapidly as customers get farther from a distribution hub?", ["04"], True, "distance decay"),
    ("chain-reaction", "一个供应商违约怎样触发整条供应链的连锁崩溃？", "How can one supplier default trigger a chain reaction across an entire supply network?", ["05", "42", "68"], True, "cascade or chain reaction"),
    ("exponential-decay", "一次营销活动带来的新增关注为什么会按固定比例逐周消退？", "Why does attention from a campaign decay by a roughly fixed fraction each week?", ["06"], True, "exponential decay"),
    ("bounded-growth", "产品早期用户高速增长，接近市场上限后为什么自然放缓？", "Why does product adoption grow fast early on and slow as it approaches market capacity?", ["07"], True, "bounded or logistic growth"),
    ("acceleration", "团队积累自动化工具后，交付速度为什么会持续加速？", "Why can delivery speed keep accelerating as a team accumulates automation tools?", ["08"], True, "accumulated acceleration"),
    ("sunk-cost", "项目已经投入很多钱，为什么这不该成为继续投入的理由？", "Why should money already spent not justify continuing a failing project?", ["09"], False, "sunk-cost bias"),
    ("restoring-force", "库存偏离目标值后，补货机制如何把它拉回平衡点？", "How can replenishment pull inventory back toward equilibrium after a deviation?", ["10", "20"], True, "restoring force or negative feedback"),
    ("periodic-cycle", "为什么内容流量会形成稳定的周期性高峰和低谷？", "Why can content traffic settle into recurring peaks and troughs?", ["11", "13"], True, "periodic dynamics"),
    ("resonance", "为什么固定节奏的小促销会在特定用户周期上产生异常大的效果？", "Why can small periodic promotions create an outsized response at a particular user rhythm?", ["12"], True, "resonance"),
    ("oscillatory-feedback", "供需双方反复过度调整，为什么价格会持续振荡？", "Why do repeated over-corrections by supply and demand make prices oscillate?", ["13", "20"], True, "oscillatory feedback"),
    ("interference", "两项单独有效的政策叠加后为何可能相互抵消？", "Why can two individually effective policies cancel each other when combined?", ["14"], True, "interference"),
    ("diffusion", "新工作方式如何从一个小团队逐步扩散到整个组织？", "How does a new working practice diffuse from one small team across an organization?", ["15", "42"], True, "diffusion"),
    ("pattern-formation", "没有中央指挥时，社区中为何会自发形成稳定的功能分区？", "How can stable functional zones emerge in a community without central coordination?", ["16"], True, "reaction-diffusion or self-organized pattern"),
    ("relative-motion", "信息发布者和受众移动速度不同时，感知频率为什么会变化？", "Why does perceived frequency change when a signal source and its audience move relative to each other?", ["17"], True, "relative-motion frequency shift"),
    ("runaway-feedback", "负面评论越多越被推荐，曝光又产生更多负评，为什么会失控？", "Why can negative reviews become a runaway loop when engagement drives more exposure?", ["18", "05"], True, "positive feedback"),
    ("dynamic-equilibrium", "平台补贴和商家供给如何在相互调整中形成动态平衡？", "How can platform subsidies and merchant supply reach a dynamic equilibrium through mutual adjustment?", ["19"], True, "dynamic equilibrium"),
    ("negative-feedback", "客服排队变长就自动增派人手，缩短后再回收资源，这是什么结构？", "What structure adds support capacity when queues grow and removes it after queues shrink?", ["20"], True, "negative feedback"),
    ("hysteresis", "品牌信任崩塌后，即使质量恢复，为什么口碑也不会沿原路立即回来？", "Why does brand trust fail to return immediately along the same path after quality recovers?", ["21"], True, "hysteresis and path dependence"),
    ("memory", "一次严重故障为什么会让组织在多年后仍保持过度谨慎？", "Why can one severe outage leave an organization overly cautious for years?", ["22", "75"], True, "persistent memory"),
    ("threshold", "用户活跃度低于某个点后，为什么留存会突然断崖式下降？", "Why can retention collapse abruptly after engagement falls below a threshold?", ["23", "25"], True, "threshold response"),
    ("nucleation", "新文化为什么常从少数稳定小团体开始，然后快速成形？", "Why does a new culture often nucleate in a few stable clusters before spreading rapidly?", ["24"], True, "nucleation"),
    ("phase-transition", "团队规模只增加一点，协作方式为什么会突然发生质变？", "Why can a small increase in team size suddenly change the mode of coordination?", ["25", "26"], True, "phase transition"),
    ("turbulence", "需求波动超过一定程度后，排期为什么从可预测变得高度混乱？", "Why does scheduling become turbulent and unpredictable after demand volatility passes a limit?", ["27"], True, "turbulence"),
    ("state-transition", "客户如何在忠诚、观望和流失状态之间按概率迁移？", "How do customers probabilistically transition among loyal, inactive, and churned states?", ["30"], True, "Markov state transition"),
    ("aggregation-normality", "许多独立小误差叠加后，为什么总体波动接近钟形分布？", "Why does the sum of many independent small errors approach a bell-shaped distribution?", ["34"], True, "central-limit aggregation"),
    ("conservation-transfer", "预算从一个部门转到另一个部门时，怎样追踪总量守恒？", "How can total budget be conserved and traced when resources move between departments?", ["37"], True, "conservation and transfer"),
    ("small-world", "为什么大型组织里任意两个人常能通过很少的中间人建立联系？", "Why can any two people in a large organization often connect through only a few intermediaries?", ["40"], True, "small-world connectivity"),
    ("preferential-attachment", "头部创作者为什么会因为已有粉丝更多而继续获得更多关注？", "Why do leading creators keep gaining attention partly because they already have more followers?", ["41"], True, "preferential attachment"),
    ("contagion", "恐慌如何通过社交关系从少数人传播到整个群体？", "How does panic spread from a few people through social ties to a whole population?", ["42", "05"], True, "network contagion"),
    ("catalyst", "为什么一个不被消耗的中间机制能显著加快组织变革？", "How can an intermediary mechanism accelerate organizational change without being consumed?", ["44"], True, "catalysis"),
    ("loss-aversion", "为什么失去一百元带来的痛苦通常大于得到一百元的快乐？", "Why does losing one hundred dollars usually hurt more than gaining the same amount feels good?", ["47"], False, "loss aversion"),
    ("resource-scheduling", "有限算力应如何在高优先级和低优先级任务之间调度？", "How should limited compute be scheduled across high- and low-priority tasks?", ["50"], True, "resource scheduling"),
    ("commons", "每个人都多用一点公共资源，为什么最终会让所有人受损？", "Why does each person taking a little more from a shared resource eventually harm everyone?", ["51"], True, "tragedy of the commons"),
    ("selection", "多个产品方案竞争时，适应用户环境的方案为什么逐渐占优势？", "Why do product variants better adapted to user conditions gradually dominate competitors?", ["52"], True, "selection"),
    ("adverse-selection", "平台无法识别质量时，为什么优质卖家会退出而劣质卖家留下？", "Why do high-quality sellers leave when a platform cannot distinguish quality, leaving worse sellers behind?", ["53"], True, "adverse selection"),
    ("divide-conquer", "一个超大分析任务如何拆成独立小任务并行计算后再合并？", "How can a large analysis be split into independent tasks, computed in parallel, and merged?", ["54"], True, "divide and conquer"),
    ("entropy", "信息在多次转述中为什么越来越难恢复到最初的精确状态？", "Why does information become harder to restore exactly after repeated retellings?", ["55", "59"], True, "irreversibility and information loss"),
    ("sampling-aliasing", "每周只看一次指标，为什么会把日内周期误判成长期趋势？", "Why can weekly sampling mistake an intraday cycle for a long-term trend?", ["57"], True, "sampling aliasing"),
]


# slug, zh query, en query, expected reason
OUT_OF_SCOPE = [
    ("arithmetic", "1 + 1 等于几？", "What is 1 + 1?", "arithmetic"),
    ("greeting", "你好，今天过得怎么样？", "Hello, how are you today?", "chitchat"),
    ("capital-trivia", "法国的首都是哪里？", "What is the capital of France?", "trivia"),
    ("weather", "北京明天天气怎么样？", "What will the weather be in Beijing tomorrow?", "trivia"),
    ("translation", "把苹果翻译成英文。", "Translate the word apple into Chinese.", "trivia"),
    ("stock-forecast", "特斯拉明天会涨还是会跌？", "Will Tesla stock rise or fall tomorrow?", "forecasting_intent"),
    ("crypto-pick", "推荐一个下周一定上涨的加密货币。", "Pick a cryptocurrency guaranteed to rise next week.", "forecasting_intent"),
    ("recipe", "西红柿炒鸡蛋怎么做？", "How do I cook scrambled eggs with tomatoes?", "trivia"),
    ("empty-whitespace", "   ", "\t", "empty"),
    ("punctuation", "？？！！", "...?!", "empty"),
]


def _record(case_id: str, pair_id: str, language: str, query: str, **labels: object) -> dict:
    return {
        "id": case_id,
        "pair_id": pair_id,
        "language": language,
        "query": query,
        "labels": labels,
    }


def build() -> list[dict]:
    rows: list[dict] = []
    for index, (slug, zh, en, type_ids, cross_domain, note) in enumerate(IN_SCOPE, 1):
        pair_id = f"in-{index:02d}-{slug}"
        labels = {
            "out_of_scope": False,
            "scope_reason": "ok",
            "accepted_type_ids": type_ids,
            "require_cross_domain": cross_domain,
            "min_relevant_at_5": 1,
            "note": note,
        }
        rows.append(_record(f"{pair_id}-zh", pair_id, "zh", zh, **labels))
        rows.append(_record(f"{pair_id}-en", pair_id, "en", en, **labels))
    for index, (slug, zh, en, reason) in enumerate(OUT_OF_SCOPE, 1):
        pair_id = f"oos-{index:02d}-{slug}"
        labels = {
            "out_of_scope": True,
            "scope_reason": reason,
            "accepted_type_ids": [],
            "require_cross_domain": False,
            "min_relevant_at_5": 0,
            "note": "must refuse without retrieval results",
        }
        rows.append(_record(f"{pair_id}-zh", pair_id, "zh", zh, **labels))
        rows.append(_record(f"{pair_id}-en", pair_id, "en", en, **labels))
    return rows


def main() -> None:
    rows = build()
    if len(rows) != 100:
        raise RuntimeError(f"expected 100 rows, got {len(rows)}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    OUTPUT.write_text(payload, encoding="utf-8")
    print(f"wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
