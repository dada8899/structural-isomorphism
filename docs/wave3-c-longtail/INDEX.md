# Wave 3 C — long-tail KB backfill INDEX

10 sparse domains × 30 entries = **300** new entries.

- Date: 2026-05-25
- Source file: `data/kb-additions-2026-05-25-long-tail-batch.jsonl`
- Schema: 与 `data/kb-5000-merged.jsonl` 一致（`id`/`name`/`domain`/`type_id`/`description`）
- 主 KB 未被修改；本 batch 等待用户后续 merge

## Selection (data-driven)

每个 domain 选择前先扫描 `kb-5000-merged.jsonl` 的 domain 计数（215 个 domain，最稀疏的 50+ 个 ≤ 2 条）。最终 10 个 domain 按"sciences (5) + engineering/applied (2) + health/social (2) + emerging tech (1)"分布：

| Domain | Pre-existing | Added | Total | Bucket | Top type_id link |
|---|---:|---:|---:|---|---|
| 复分析 (complex-analysis) | 1 | 30 | 31 | sciences | 07 (mean-field self-consistency, 10) |
| 数论 (number-theory) | 18 | 30 | 48 | sciences | 07 (12) / 60 (asymptotic-free RG, 6) |
| 群体遗传学 (pop-genetics) | 1 | 30 | 31 | sciences | 32 (Langevin SDE, 14) / 07 (14) |
| 植物学 (botany) | 1 | 30 | 31 | sciences | 20 (homeotic switch, 12) |
| 内分泌学 (endocrinology) | 1 | 30 | 31 | sciences | 07 (17) / 22 (NF-κB time-delay osc, 6) |
| 半导体 (semiconductor) | 1 | 30 | 31 | applied/engineering | 07 (10) / 20 (4) / 24 (Anderson loc, 2) |
| 流体力学/声学 (fluid-acoustics) | 1 | 30 | 31 | applied/engineering | 13 (dissipative soliton limit cycle, 7) |
| 公共卫生 (public-health) | 1 | 30 | 31 | health/social | 07 (20) / 23 (percolation threshold, 6) |
| 生物物理 (biophysics) | 1 | 30 | 31 | health/social | 07 (8) / 11 (LIF threshold osc, 6) |
| 区块链 (blockchain) | 6 | 30 | 36 | emerging tech | 07 (16) / 23 (7) / 65 (Myerson auction, 5) |

**总计**: 31 (复分析 from 1→31) … 48 (数论 from 18→48)；最低 baseline 由 1 提升到 31。

## Quality gates met

- ✅ 300 / 300 条 description ≥ 150 字（min=150, median=195, max=277, p90=226）
- ✅ 300 / 300 条 type_id 在现有 84 个 KB type_id 内（实际用了 23 个 unique type_id）
- ✅ 每 domain 内 30 条 name 不重复（脚本检查 0 dup）
- ✅ 每条 description 含具体公式 / 标度律 / 典型常数 / 关键参考文献（Author Year 格式）
- ✅ 每条非 placeholder：含 phenomenon 名 + 机制 + 标度律或数值 + 参考

## Cross-class linkages (top hubs)

| type_id | KB 中代表 | 本 batch 引用次数 | 关联的 verified universality class |
|---|---|---:|---|
| 07 | 平均场自洽方程 S 形序参量 | 120 | mean-field universality（普适基础） |
| 23 | 渗流阈值导电网络转变 | 41 | `percolation_connectivity` (verified Wave 2) |
| 32 | 朗之万方程随机微分动力学 | 35 | `markov_chain_memory_fidelity_class`, `delay_differential_debt` 相关 |
| 20 | 同源异形基因前后轴决定 | 22 | `gardner_collins_toggle_switch` (verified) |
| 60 | 渐近自由 | 10 | RG scaling 普适层 |
| 67 | 分形盒计数非整数维度 | 9 | `fractional_brownian_crossings` (verified) |
| 22 | NF-κB 振荡时滞负反馈 | 8 | 时滞振荡普适层 |
| 65 | Myerson 最优拍卖 | 5 | mechanism design 普适层 |
| 24 | 安德森局域化 | 2 | `anderson_localization` (verified Wave 2C) |
| 47 | 多巴胺预测误差信号 | 1 | reward prediction error universality |

## Recommended cross-domain hub candidates (Wave 3.1 follow-up)

按"现象-class 强 link + 跨学科 anchor"挑出本 batch 中潜在 hub 节点：

1. **Liquidation cascade DeFi** (区块链 #8) — link 到 `soc_threshold_cascade` (largest hub on-chain liquidity crisis)
2. **Eigen quasispecies error threshold** (群体遗传学 #18 / 生物物理 #17) — link 到 percolation_connectivity 阈值层
3. **Liquid-liquid phase separation biomolecular** (生物物理 #19) — link 到 `scheffer_fold_bifurcation` (verified 蛋白质相分离)
4. **R_0 herd immunity threshold** (公共卫生 #1-#2) — link 到 `sir_contagion_network_class` (verified)
5. **Schramm-Loewner Evolution SLE_κ** (复分析 #11) — bridge 数学物理与 percolation_connectivity
6. **Selective sweep** (群体遗传学 #11) — 群体水平的 percolation-like 固定
7. **Microtubule dynamic instability** (生物物理 #30) — 细胞内的双稳-级联
8. **Anderson localization 2DEG** (半导体 #1) — 已 verified anderson_localization 的固态实例
9. **MEV maximum extractable value** (区块链 #4) — `schelling_credible_commitment` 类延伸
10. **Erdős-Kac 正态分布** (数论 #8) — 概率数论与 Langevin 高斯化的跨界桥

## Recommended next 10 sparse domains for Wave 3.1

按 pre-existing ≤ 5 + 学科覆盖差异挑选下一轮：

1. **海洋生物学** (pre=1) — marine ecology / coral bleaching threshold
2. **气候学 / 气候模拟** (pre=1 each) — tipping point / Scheffer fold bifurcation 强 link
3. **数理逻辑** (pre=1) — Gödel / forcing / model theory
4. **图论** (pre=1) — Ramsey / extremal / random graphs
5. **数学物理** (pre=1) — gauge theory / integrable systems
6. **调和分析** (pre=1) — Calderón-Zygmund / restriction estimates
7. **统计学** (pre=1) — high-dim / nonparametric / sequential
8. **几何学** (pre=1) — differential / algebraic / Ricci flow
9. **动物行为学** (pre=1) — collective behavior / ESS
10. **海洋生态 / 森林生态** (pre=1 each) — ecosystem regime shifts

或按"emerging tech 缺口"补：**量子信息** (pre=0)、**机器人学** (need check)、**机器学习理论** (need check)。

## Files

```
docs/wave3-c-longtail/
├── INDEX.md                          (this file)
└── per-domain/
    ├── 复分析.md
    ├── 数论.md
    ├── 群体遗传学.md
    ├── 植物学.md
    ├── 内分泌学.md
    ├── 半导体.md
    ├── 流体力学-声学.md
    ├── 公共卫生.md
    ├── 生物物理.md
    └── 区块链.md
```

data/
└── kb-additions-2026-05-25-long-tail-batch.jsonl   (300 entries)
