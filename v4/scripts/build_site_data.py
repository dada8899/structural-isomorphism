#!/usr/bin/env python3
"""
V4 Layer 5 (Product): Build frontend-friendly JSON from candidate_classes.jsonl.

Input:
  - v4/results/candidate_classes.jsonl (from hub_detect.py)
  - v4/taxonomy/universality_classes.yaml (physics prototype mapping)

Output:
  - web/frontend/assets/data/universality-classes.json

Strategy:
  - Filter to top N by size × domains × avg_score.
  - Hand-curate metadata (Chinese name, physics prototype, invariants,
    predictions) for the top classes. Unknown clusters keep raw data
    with placeholder taxonomy.
  - Group members by domain for cleaner display.
"""

import json
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = REPO_ROOT / "v4" / "results" / "candidate_classes.jsonl"
LAYER3_AUTO = REPO_ROOT / "v4" / "results" / "layer3_auto_curated.jsonl"
LAYER4_PREDICTIONS = REPO_ROOT / "v4" / "results" / "layer4_predictions.jsonl"
OUT_FILE = REPO_ROOT / "web" / "frontend" / "assets" / "data" / "universality-classes.json"

# ---------------------------------------------------------------------------
# Curated metadata — for the top classes we know.
# Keys are the hub node display names from candidate_classes.jsonl.
# Provenance filter helps when multiple overlapping classes share a hub.
# ---------------------------------------------------------------------------

CURATED = {
    # SOC mega-cluster (connected_component top 1)
    ("清算级联的链上流动性危机", "connected_component"): {
        "class_id": "soc_threshold_cascade",
        "name_zh": "阈值级联 / 自组织临界类",
        "name_en": "Self-Organized Criticality (threshold cascade)",
        "physics_prototype": "Bak-Tang-Wiesenfeld 沙堆模型 (1987)",
        "taxonomy_match": "soc_threshold_cascade",
        "confidence": "high",
        "summary_zh": (
            "一组耦合的阈值元件，每个元件局部独立积累压力，当一个元件跨越阈值就触发破裂，"
            "破裂通过耦合把压力转移给邻居。当平均分支因子 ξ → 1 时系统处于分支过程临界点，"
            "此时级联规模服从幂律分布，时间衰减服从 Omori 律。"
        ),
        "invariants": [
            "Gutenberg-Richter 幂律: P(s) ∝ s^(-τ), τ ≈ 1.5",
            "Omori 衰减律: n(t) ∝ 1/t^p, p ≈ 1",
            "分支过程临界: 平均分支因子 ξ → 1",
            "标度不变: 系统无特征尺度",
            "等待时间 Pareto 尾",
        ],
        "predictions": [
            {
                "target": "USGS 全球地震目录 2020-2025, M ≥ 4.45 (37,281 事件)",
                "prediction": "Gutenberg-Richter b = 1.084 ± 0.005 (bootstrap CI [1.073, 1.094]), 能量幂律 τ = 1.72, Omori p = 0.941 ± 0.017 (R² = 0.993)",
                "test_method": "Aki 1965 MLE + Shi-Bolt 1982 uncertainty + 500-bootstrap CI + Clauset 2009 power-law fit + Omori log-linear regression",
                "data_source": "USGS FDSN Event API (5 年 × M ≥ 3.5 = 84,808 events)",
                "sample_size": "84,808 events / 580 main shocks / 24,680 aftershocks",
                "paper_target": "Layer 5 Phase 1 — pipeline validation (物理 ground truth)",
                "status": "✅ 已验证 (2026-04-15)",
                "rationale": "SOC 普适类的黄金参考. 在真实全球地震数据上完整复现 b ≈ 1 + Omori p ≈ 1. 验证了分析 pipeline 的正确性.",
                "paper_url": "/paper/soc-earthquake-2026-04-15",
                "paper_title": "Recovering SOC Universality on a Global Earthquake Catalog",
            },
            {
                "target": "S&P 500 daily returns 1990-2025 (9,060 交易日)",
                "prediction": "Inverse cubic law α = 2.998 ± 0.041 (Gopikrishnan 1998, 拒绝 lognormal p < 10⁻⁹); Omori 日尺度 p = 0.286 ± 0.034 (R² = 0.71, 318 主震 3σ, Weber 2007 daily band [0.3, 0.6] 内)",
                "test_method": "同一 pipeline 交叉验证 — Clauset 2009 幂律拟合 on |r| + Omori log-linear regression on stacked post-shock volatility",
                "data_source": "Yahoo Finance ^GSPC (yfinance 1.2.0)",
                "sample_size": "9,060 daily log returns / 2,327 tail events / 318 main shocks",
                "paper_target": "Layer 5 Phase 2 — 第一个非物理系统跨域验证",
                "status": "✅ 已验证 (2026-04-15)",
                "rationale": "项目首次非物理系统 SOC 验证. 同一 earthquake pipeline 零调参应用到 S&P 500, 精确复现 Gopikrishnan 1998 inverse cubic law (α=3.00) + Weber 2007 daily-scale Omori (p=0.29). 功能形式 (幂律尾 + Omori 弛豫) 跨域一致, 绝对指数因微观观测量定义而异——这正是普适类理论预测的行为.",
                "paper_url": "/paper/soc-stockmarket-2026-04-15",
                "paper_title": "Cross-Domain SOC Validation: Inverse Cubic Law and Omori Decay on S&P 500",
            },
            {
                "target": "DeFi 清算级联",
                "prediction": "清算 USD 规模分布服从 τ = 1.5 ± 0.2 的幂律",
                "test_method": "MLE 拟合 + Kolmogorov-Smirnov 检验",
                "data_source": "DeFiLlama Liquidations (2020-2026) — Cloudflare 反爬阻挡, 需 Graph API key",
                "sample_size": "N ≥ 50,000 events",
                "paper_target": "Nature Physics / PRL / PNAS",
                "status": "🚧 待验证 (数据源解锁中)",
            },
            {
                "target": "DeFi 清算级联",
                "prediction": "大清算后的次生清算频率衰减服从 Omori 1/t^p, p ∈ [0.8, 1.2]",
                "test_method": "时间窗口分组统计 + 幂律拟合",
                "data_source": "Dune Analytics 逐块清算事件",
                "paper_target": "同上",
                "status": "🚧 待验证",
            },
        ],
    },
    # Hysteresis cluster (connected_component top 2)
    ("热固性树脂凝胶点渗流相变", "connected_component"): {
        "class_id": "hysteresis_preisach",
        "name_zh": "磁滞 / 一阶相变类",
        "name_en": "Hysteresis / First-order Transition (Preisach)",
        "physics_prototype": "Preisach 磁滞模型 (1935) + Scheffer 双稳态 (2001)",
        "taxonomy_match": "hysteresis_first_order_transition",
        "confidence": "medium",
        "summary_zh": (
            "系统存在双稳态或多稳态，状态变化有明显的滞后环——升高参数到 A 点才从低态跳到高态，"
            "降低参数到 B < A 才跳回。典型数学结构是 Preisach 算子与双稳态分岔的组合。"
        ),
        "invariants": [
            "双稳态分岔 (saddle-node / fold)",
            "滞后环面积 = 能量耗散",
            "Preisach 密度 μ(α,β) 描述分布式滞后",
            "临界点的标度律",
        ],
        "predictions": [],
    },
    # Scheffer fold bifurcation cluster (connected_component top 3)
    ("蛋白质相分离的临界浓度阈值", "connected_component"): {
        "class_id": "scheffer_fold_bifurcation",
        "name_zh": "Scheffer 突变 / Fold 分岔类",
        "name_en": "Fold Bifurcation / Scheffer Regime Shift",
        "physics_prototype": "Scheffer regime shift (2001) + catastrophe theory",
        "taxonomy_match": "fold_bifurcation_regime_shift",
        "confidence": "high",
        "summary_zh": (
            "具有双稳态的非线性系统，控制参数缓慢变化到 fold 分岔点时系统状态突然跳变，"
            "且跳变不可逆——这就是 tipping point。共享方程是 Scheffer 标准式。"
        ),
        "invariants": [
            "Fold 分岔 normal form: dx/dt = r - bx + x²/(h²+x²)",
            "tipping point 不可逆性",
            "临界减速 (critical slowing down) 作为预警信号",
            "分岔点附近涨落变大",
        ],
        "predictions": [],
    },
    # Motter-Lai sub-community (louvain of #1)
    ("建筑结构的渐进倒塌", "louvain_community"): {
        "class_id": "motter_lai_network_cascade",
        "name_zh": "Motter-Lai 网络级联类",
        "name_en": "Motter-Lai Network Cascade",
        "physics_prototype": "Motter-Lai model (2002) for network cascading failure",
        "taxonomy_match": "soc_threshold_cascade",  # sub-class of SOC
        "confidence": "high",
        "summary_zh": (
            "SOC 巨簇经 Louvain 社区发现自动拆出的一个亚类——专门描述物理基础设施网络上的级联失效。"
            "每个节点有容量 C_i，当前负载 L_i，失效后负载按权重 w_ij 分配给邻居，"
            "若接收者超过容量则连锁失效。"
        ),
        "invariants": [
            "级联规模分布: P(s) ∝ s^(-τ)",
            "关键容限比 α = C/L 决定鲁棒性",
            "单点故障攻击曲线",
            "小世界 + 无尺度拓扑加剧级联",
        ],
        "predictions": [],
    },
    # Diamond-Dybvig sub-community (louvain of #1)
    ("银行挤兑", "louvain_community"): {
        "class_id": "diamond_dybvig_self_fulfilling",
        "name_zh": "Diamond-Dybvig 自实现挤兑类",
        "name_en": "Diamond-Dybvig Self-Fulfilling Runs",
        "physics_prototype": "Diamond-Dybvig (1983) + Morris-Shin global games",
        "taxonomy_match": "multistable_self_fulfilling",
        "confidence": "high",
        "summary_zh": (
            "系统有多个 Nash 均衡，参与者的预期通过协调博弈选择均衡。"
            "相信崩溃 → 采取行动 → 崩溃成真。挤兑型现象的数学本质。"
        ),
        "invariants": [
            "多重均衡 (multiple Nash equilibria)",
            "自我实现预期",
            "Global game 上的阈值信念 θ*",
            "基本面与恐慌驱动的挤兑事前不可区分",
        ],
        "predictions": [
            {
                "target": "DeFi 借贷协议挤兑",
                "prediction": "大规模提款事件可被 global game 阈值信念模型参数化识别",
                "test_method": "Goldstein-Pauzner 反向参数识别 + 社交媒体时间戳",
                "data_source": "Aave/Compound 提款日志 + Twitter/Telegram 情绪",
                "paper_target": "Journal of Finance / JFE",
                "status": "待验证",
            }
        ],
    },
    # Tail copula cluster
    ("相关性崩溃的尾部传染效应", "connected_component"): {
        "class_id": "tail_copula_contagion",
        "name_zh": "尾部相关 / Copula 传染类",
        "name_en": "Tail Copula Contagion",
        "physics_prototype": "Copula extreme value theory + Minsky moments",
        "taxonomy_match": None,  # new class, not in seed
        "confidence": "medium",
        "summary_zh": (
            "平常状态下相关性低、多元化有效的系统，在极端压力下相关性跳涨到接近 1。"
            "尾部依赖系数 λ_tail 在压力期非零——copula 的尾部重合是金融和气候的共同失败模式。"
        ),
        "invariants": [
            "尾部相关系数 λ_tail = lim P(X>q|Y>q)",
            "Minsky 稳定性悖论",
            "Diversification illusion breakdown",
            "压力期的 copula 结构突变",
        ],
        "predictions": [],
    },
    # Toggle switch cluster
    ("Th1/Th2极化与疾病偏向", "connected_component"): {
        "class_id": "gardner_collins_toggle_switch",
        "name_zh": "双稳态 Toggle Switch 类",
        "name_en": "Gardner-Collins Bistable Toggle",
        "physics_prototype": "Gardner-Collins-Cantor toggle switch (2000 Nature)",
        "taxonomy_match": None,  # new class, not in seed
        "confidence": "high",
        "summary_zh": (
            "两个相互抑制的元件构成开关，具有两个稳定状态。只要初始条件不同，系统被锁定在不同的状态。"
            "合成生物学的经典开关结构，在免疫、发育、细胞周期里反复出现。"
        ),
        "invariants": [
            "Mutual repression: du/dt = α/(1+v^n) - u",
            "双稳态空间分离",
            "随机噪声下的状态锁定",
            "Hill 系数 n > 1 是双稳态存在的必要条件",
        ],
        "predictions": [],
    },
    # Credible commitment cluster
    ("进入威慑与产能过度承诺", "connected_component"): {
        "class_id": "schelling_credible_commitment",
        "name_zh": "可信承诺 / 时间不一致类",
        "name_en": "Schelling Credible Commitment",
        "physics_prototype": "Schelling 1960 credible commitment + Kydland-Prescott 时间不一致",
        "taxonomy_match": None,  # new class, not in seed
        "confidence": "high",
        "summary_zh": (
            "理性主体面临承诺难题：最优事前策略在事后会被背叛。只有承诺不可逆（沉没成本、声誉、"
            "自缚机制）才能让承诺可信。跨越国际关系、产业组织、货币政策的共同数学结构。"
        ),
        "invariants": [
            "时间不一致性 (time inconsistency)",
            "承诺价值 > 灵活价值 iff 沉没成本 > 背叛收益",
            "自缚 (self-binding) 作为可信机制",
            "声誉均衡 (reputation equilibrium)",
        ],
        "predictions": [],
    },
}


def coerce_equations(raw_eqs, limit=4):
    """Deduplicate, truncate, and structure shared equations for display."""
    seen = set()
    out = []
    for eq in raw_eqs:
        if not eq:
            continue
        eq = eq.strip()
        if not eq or eq in seen:
            continue
        seen.add(eq)
        out.append({"raw": eq[:320]})
        if len(out) >= limit:
            break
    return out


def group_members_by_domain(members):
    by_domain = defaultdict(list)
    unlabeled = []
    for m in members:
        domains = m.get("domains") or []
        name = m.get("name") or m.get("id")
        if not domains:
            unlabeled.append(name)
            continue
        for d in domains:
            by_domain[d].append(name)
    result = [
        {"domain": d, "names": sorted(set(names))}
        for d, names in sorted(by_domain.items(), key=lambda kv: -len(kv[1]))
    ]
    if unlabeled:
        result.append({"domain": "未标注", "names": sorted(set(unlabeled))})
    return result


def load_layer3_auto():
    """Load LLM-generated curation from layer3_auto_curated.jsonl.
    Returns dict keyed by (hub_name, provenance)."""
    if not LAYER3_AUTO.exists():
        return {}
    out = {}
    with LAYER3_AUTO.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (rec.get("hub_name"), rec.get("provenance"))
            out[key] = rec
    return out


def load_layer4_predictions():
    """Load LLM-generated predictions from layer4_predictions.jsonl.
    Returns dict keyed by hub_name (unique enough across all 23 classes)."""
    if not LAYER4_PREDICTIONS.exists():
        return {}
    out = {}
    with LAYER4_PREDICTIONS.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            hub = rec.get("hub_name")
            if hub:
                out[hub] = rec.get("predictions", [])
    return out


def build():
    with CANDIDATES.open("r", encoding="utf-8") as f:
        raw = [json.loads(line) for line in f if line.strip()]

    layer3 = load_layer3_auto()
    layer4 = load_layer4_predictions()

    classes = []
    for rec in raw:
        hub_name = (rec.get("hub") or {}).get("name")
        provenance = rec.get("provenance")

        # Priority: manual CURATED > layer3 auto > unnamed
        manual = CURATED.get((hub_name, provenance))
        auto = layer3.get((hub_name, provenance))
        source = "manual" if manual else ("llm" if auto else "none")
        curated = manual or auto or {}

        item = {
            "class_id": curated.get("class_id") or f"auto_{rec.get('provenance','')}_{rec.get('index','')}",
            "name_zh": curated.get("name_zh") or f"未命名等价类 ({hub_name})",
            "name_en": curated.get("name_en") or "",
            "rank": rec.get("index"),
            "provenance": provenance,
            "hub_name": hub_name,
            "hub_degree": (rec.get("hub") or {}).get("degree_inside_class"),
            "size": rec.get("size"),
            "n_domains": rec.get("n_domains"),
            "domains": rec.get("domains", []),
            "edges_internal": rec.get("edges_internal"),
            "avg_edge_score": rec.get("avg_edge_score"),
            "max_edge_score": rec.get("max_edge_score"),
            "physics_prototype": curated.get("physics_prototype") or "",
            "taxonomy_match": curated.get("taxonomy_match"),
            "confidence": curated.get("confidence") or "unclassified",
            "summary_zh": curated.get("summary_zh") or "",
            "shared_equations_raw": coerce_equations(rec.get("shared_equations_sample", [])),
            "invariants": curated.get("invariants", []),
            "predictions": (curated.get("predictions", []) or layer4.get(hub_name, [])),
            "notes": curated.get("notes", "") if source == "llm" else "",
            "members_by_domain": group_members_by_domain(rec.get("members", [])),
            "is_curated": bool(manual or auto),
            "curation_source": source,
        }
        classes.append(item)

    # Sort: manual > llm > uncurated, then by size * n_domains * avg_score
    def rank(c):
        source_priority = {"manual": 0, "llm": 1, "none": 2}
        score_key = -(c["size"] * c["n_domains"] * (c["avg_edge_score"] or 1))
        return (source_priority.get(c["curation_source"], 3), score_key)

    classes.sort(key=rank)

    payload = {
        "meta": {
            "generated_at": "2026-04-15",
            "source": "v4/results/candidate_classes.jsonl",
            "total_classes": len(classes),
            "manual_curated": sum(1 for c in classes if c["curation_source"] == "manual"),
            "llm_curated": sum(1 for c in classes if c["curation_source"] == "llm"),
            "curated_classes": sum(1 for c in classes if c["is_curated"]),
            "version": "0.2",
        },
        "stats": {
            "n_equivalence_classes": len(classes),
            "n_cross_domain": sum(1 for c in classes if c["n_domains"] >= 2),
            "max_members": max((c["size"] for c in classes), default=0),
            "max_domains": max((c["n_domains"] for c in classes), default=0),
            "largest_hub": classes[0]["hub_name"] if classes else None,
        },
        "classes": classes,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"=== V4 Site Data Build ===")
    print(f"Total candidate classes: {len(classes)}")
    print(f"Manual curated: {payload['meta']['manual_curated']}  LLM curated: {payload['meta']['llm_curated']}")
    print(f"Output: {OUT_FILE.relative_to(REPO_ROOT)}")
    print()
    print("All classes in site feed:")
    tag_map = {"manual": "●", "llm": "◐", "none": "○"}
    for c in classes:
        tag = tag_map.get(c["curation_source"], "?")
        print(f"  {tag} {c['name_zh']} — size={c['size']:2d} domains={c['n_domains']:2d} avg={c['avg_edge_score']}")


if __name__ == "__main__":
    build()
