# V4 Downscoped: Transformation-Primitive Analysis on 63 A-Level Candidates

> Generated 2026-04-13. Input: V1 top-24 + V2 A-level (19) + V3 A-level (20) = 63 unique cross-domain candidates.

## 1. Methodology

### 1.1 Background

V4 was originally planned as a model-training project — fitting a classifier that predicts "which transformation a cross-domain transfer uses" from historical cases. In the Q1 feasibility sprint we ran a 3-model (Claude / Kimi / DeepSeek) labeling agreement test and measured 0.721 agreement on the 8-primitive schema. The schema is workable, but training a full model was judged over-budget for the current phase.

**V4 is therefore downscoped to a one-shot quantitative analysis tool**: instead of training a predictor, we take the finished 8-primitive schema and apply it as an additional scoring dimension to the 63 candidates already surfaced by V1/V2/V3. The output is not a model — it is a new column (`transformation_depth`) stapled onto existing discoveries, usable for deciding which papers to write first.

### 1.2 Schema (8 primitives)

Source: `/Users/wanqh/Projects/structural-isomorphism/v4-feasibility/transformation-primitives.md`

| ID | Primitive | Meaning |
|---|---|---|
| 1 | `variable_rename` | Same math, only unit/symbol differs |
| 2 | `concept_transfer` | Reinterpret a quantity in a new domain |
| 3 | `causal_inversion` | Swap cause/effect |
| 4 | `continuity_toggle` | Continuous ↔ discrete |
| 5 | `boundary_rewrite` | Change boundary/topology/domain |
| 6 | `dim_shift` | Change effective dimensionality |
| 7 | `stochastic_toggle` | Add/remove noise |
| 8 | `time_scaling` | Time-regime shift |

### 1.3 Depth definition

- **`primitive_count`** = number of **non-trivial** primitives (everything except `concept_transfer`)
- **`transformation_depth`** = same as primitive_count, on a 0–7 scale
- **Shallow**: depth = 0 (pure `concept_transfer`, i.e. rename-by-analogy only)
- **Medium**: depth = 1 (one real transformation applied)
- **Deep**: depth ≥ 2 (at least two genuine non-trivial transformations)

`concept_transfer` is counted but **does not contribute to depth** — every cross-domain pair trivially contains it; counting it would make all candidates look deep.

### 1.4 Labeling protocol

Labels were assigned by direct reasoning over each candidate's `equations`/`shared_equation`/`variable_mapping` fields. Labeling rules followed the schema's explicit caveat: `variable_rename` is reserved for literal unit-only changes, and `concept_transfer` is preferred whenever any reinterpretation happens. **No inflation**: when in doubt, the smaller primitive set was chosen.

### 1.5 Deduplication

Raw input: 24 + 19 + 20 = 63. Deduplication was attempted bidirectionally by `frozenset({a_name, b_name})`, which removed zero pairs. One near-duplicate survived: `地震静态应力触发 ↔ DeFi清算连锁瀑布效应` and `清算级联的链上流动性危机 ↔ 地震静态应力触发` are functionally the same pair with different b_name variants of "DeFi cascade" — both kept in the ranking but flagged in Section 4.

## 2. Primitive Distribution Across 63 Candidates

| Primitive | Count | % |
|---|---:|---:|
| `concept_transfer` | 63 | 100.0% |
| `variable_rename` | 0 | 0.0% |
| `time_scaling` | 8 | 12.7% |
| `dim_shift` | 7 | 11.1% |
| `boundary_rewrite` | 6 | 9.5% |
| `causal_inversion` | 5 | 7.9% |
| `continuity_toggle` | 5 | 7.9% |
| `stochastic_toggle` | 4 | 6.3% |

**Key observations**:

1. `concept_transfer` is universal (100%) — as expected, every cross-domain transfer is at minimum a conceptual reinterpretation.
2. `variable_rename` is **unused** (0%). This confirms the schema's rule that rename is reserved for trivial unit swaps; no candidate in the 63 qualifies — all involve at least a reinterpretation.
3. `time_scaling` is the most common non-trivial primitive (12.7%), followed by `dim_shift` (11.1%) and `boundary_rewrite` (9.5%). Temporal and topological rewrites dominate, consistent with cross-domain transfers across radically different characteristic scales.
4. `stochastic_toggle` is rarest (6.3%) — likely because most of our candidates were pre-selected for mathematical structure, which already abstracts over noise.

## 3. Shallow vs Deep Split

| Category | Count | % |
|---|---:|---:|
| Shallow (depth = 0) | 33 | **52.4%** |
| Medium (depth = 1) | 25 | **39.7%** |
| Deep (depth ≥ 2) | 5 | **7.9%** |

**Interpretation**: just over half of our A-level candidates are shallow analogies — they share a common equation but bring no non-trivial transformation with them. These are perfectly publishable as technical notes or connection papers, but their originality lives in the *act of noticing* rather than in any extra mathematical work. The 5 deep candidates are where there is genuine transformation mass; these contain work beyond the connection itself, and therefore justify full-length papers.

## 4. Top 5 Deep-Transformation Candidates

> Ranked by `transformation_depth` ≥ 2. Tie-broken by source rank/score.

### #1 — Earthquake Static Stress Triggering ↔ DeFi Liquidation Cascade *(V3)*

- **Pair**: `地震静态应力触发` × `DeFi清算连锁瀑布效应`
- **Primitives**: `concept_transfer` + **`dim_shift`** + **`boundary_rewrite`** (depth = 2)
- **Why deep**: Coulomb stress transfer is a genuine 3D tensor field on a geological fault network with real spatial coordinates. Mapping it to DeFi requires (a) collapsing the stress tensor to a scalar "distance-to-liquidation" in an **abstract risk-factor space** (dim_shift: 3D → 1D), and (b) rewriting the fault-network topology as a borrower-collateral graph (boundary_rewrite: geological contiguity → lending-graph contiguity). Without these two rewrites the analogy degenerates to "both are cascades"; with them, it becomes a quantitatively testable hypothesis where DeFi provides high-frequency samples to validate Stein–King triggering theory on non-seismic systems.
- **Execution hint**: scrape on-chain liquidations, reconstruct an Omori-law decay curve, fit the Coulomb-type kernel `ΔCFS > ΔCFS_c`, compare against 1992 Landers aftershock sequence.
- **Venue**: *Nature Physics* / *PNAS* / *JGR Solid Earth*.

### #2 — On-chain Liquidation ↔ Earthquake Static Stress *(V3, reversed pair)*

- **Pair**: `清算级联的链上流动性危机` × `地震静态应力触发`
- **Primitives**: identical to #1 (depth = 2)
- **Note**: this is the **reversed direction** of #1 — V3 surfaced it as a distinct pair because the `shared_equation` is framed differently (`sum_j K_ij * delta_j > threshold_i` instead of `ΔCFS > ΔCFS_c`). For publication purposes, **#1 and #2 collapse to a single paper**; treat this as a "both directions validated" signal rather than two independent candidates.

### #3 — Intersection Spillback Lock ↔ Power Grid Cascade Failure *(V3)*

- **Pair**: `路口溢流锁死` × `电网连锁故障`
- **Primitives**: `concept_transfer` + **`boundary_rewrite`** + **`dim_shift`** (depth = 2)
- **Why deep**: Motter–Lai cascade is a pure load-redistribution model, but traffic and grids have fundamentally different load-redistribution kernels — **traffic operates on a 2D planar road network with conservative capacity** (cars can't teleport), while **power flow is non-planar with Kirchhoff constraints** (load redistribution is governed by admittance, not geometry). Applying Motter–Lai across the two requires explicit topology rewriting (planar ↔ non-planar) and effective-coupling dim change (geometric ↔ electrical). The shared equation hides non-trivial adjustments.
- **Execution hint**: collect real urban spillback data from a Chinese tier-1 city, re-derive Motter–Lai on Kirchhoff-constrained digraphs, benchmark against 2003 Northeast blackout.
- **Venue**: *Physical Review Research* / *Transportation Research Part B*.

### #4 — Path Integral Duality ($d \to d+1$) ↔ Neural Tangent Kernel (infinite-width limit) *(V1)*

- **Pair**: `路径积分对偶(d维量子→d+1维经典)` × `神经切线核(无限宽NN→核回归)`
- **Primitives**: `concept_transfer` + **`dim_shift`** + **`continuity_toggle`** (depth = 2)
- **Why deep**: both sides are **exact mathematical limits**, not analogies. Path-integral duality literally adds a temporal dimension (imaginary time) to turn a d-dimensional quantum problem into a (d+1)-dimensional classical statistical problem. NTK literally sends network width to infinity, turning a finite-parameter neural net into a kernel regression on an infinite-dimensional feature space. The dim_shift and continuity_toggle are not metaphors — they are provable limit theorems. The depth label here is conservative; this is arguably the **theoretically deepest** pair in the whole set.
- **Execution hint**: write a unified "structural limit" perspective paper. Show that both limits are Feynman–Kac-type and derive a common dictionary between NTK and path integral observables.
- **Venue**: *Communications in Mathematical Physics* / *Journal of Machine Learning Research*.

### #5 — Amazon Rainforest Tipping ↔ Rural Depopulation Collapse *(V3)*

- **Pair**: `热带雨林临界点` × `人口空洞化与乡村系统性衰退`
- **Primitives**: `concept_transfer` + **`time_scaling`** + **`boundary_rewrite`** (depth = 2)
- **Why deep**: both are Scheffer-type fold bifurcations with positive feedback (transpiration–precipitation for rainforest; population–services for villages). But the characteristic timescales are **century-scale vs decade-scale** (time_scaling is load-bearing — early-warning-signal detection windows differ by an order of magnitude), and the "domain boundary" concept must be rewritten: a rainforest boundary is a geographic edge governed by physical climate, while a village boundary is an administrative unit governed by migration economics (boundary_rewrite). The shared normal-form equation hides these two genuine rewrites.
- **Execution hint**: compare EWS (variance, AC1) on Amazon NDVI time series against Chinese county-level population time series; test whether the time-scaling ratio predicts warning-window length.
- **Venue**: *Nature Sustainability* / *PNAS*.

## 5. Which Should Be Written First?

**Recommendation**: the five deep candidates rank as follows in terms of "best first arXiv paper":

1. **#4 Path Integral × NTK** — theoretically cleanest, uses only pencil-and-paper, suitable as a pure-theory perspective. **Lowest execution risk**.
2. **#1 Earthquake × DeFi** — highest surprise value, data is freely available on-chain, but requires genuine geophysics collaboration for comparison. **Highest impact if it lands**.
3. **#5 Rainforest × Rural Collapse** — policy-relevant, two big datasets already exist, EWS methodology is standard. **Highest societal impact**.
4. **#3 Traffic × Grid** — solid and quantitative but less surprising — the Motter–Lai community will likely receive it as "incremental". **Safest workshop paper**.

Candidates #1 and #2 should be merged into a single submission, not two.

## 6. Conclusion

52.4% of our A-level candidates are shallow (concept_transfer only); 39.7% apply exactly one non-trivial transformation; only 7.9% — five pairs — involve two or more genuine structural rewrites. V4's downscoped analysis adds `transformation_depth` as a cheap but load-bearing scoring dimension: it cleanly separates *noticing that two things are analogous* from *actually performing non-trivial work during the transfer*.

The five deep pairs contain measurable mathematical mass beyond the connection itself — they should be the first targets for full-length arXiv papers. The 33 shallow pairs remain valuable as short connection notes or as seed material for a future "catalog of analogies" paper, but should not be treated as first-priority research targets.

---

## Appendix A — Full 63 Ranked by Transformation Depth

> Format: `rank | depth | source | A ↔ B | primitives`

| # | d | src | Pair | Primitives |
|---:|---:|:---:|---|---|
| 1 | 2 | v3 | 地震静态应力触发 ↔ DeFi清算连锁瀑布效应 | ct+dim+bnd |
| 2 | 2 | v3 | 清算级联的链上流动性危机 ↔ 地震静态应力触发 | ct+dim+bnd |
| 3 | 2 | v3 | 路口溢流锁死 ↔ 电网连锁故障 | ct+bnd+dim |
| 4 | 2 | v1 | 路径积分对偶(d→d+1) ↔ 神经切线核 | ct+dim+cont |
| 5 | 2 | v3 | 热带雨林临界点 ↔ 人口空洞化与乡村系统性衰退 | ct+time+bnd |
| 6 | 1 | v1 | Phi累积故障检测器 ↔ 梯度裁剪 | ct+stoch |
| 7 | 1 | v1 | CRISPR间隔获取 ↔ 文件系统Journaling | ct+cont |
| 8 | 1 | v1 | 轨道稳定子定理 ↔ LoRA低秩微调 | ct+dim |
| 9 | 1 | v2 | 永冻土甲烷延迟反馈 ↔ 灭绝债务 | ct+time |
| 10 | 1 | v1 | 二级价格歧视 ↔ H∞鲁棒控制 | ct+causal |
| 11 | 1 | v2 | 免疫超优势选择 ↔ 模型集成 | ct+stoch |
| 12 | 1 | v3 | 葡萄日烧 ↔ 珊瑚白化 | ct+time |
| 13 | 1 | v2 | 灭绝债务 ↔ 厄尔尼诺延迟振子 | ct+time |
| 14 | 1 | v2 | 全球失衡镜像对称 ↔ 扰动前馈补偿 | ct+causal |
| 15 | 1 | v2 | 放热反应温度曲线 ↔ 影子银行信用乘数 | ct+bnd |
| 16 | 1 | v2 | 信任建立崩塌 ↔ 珊瑚白化滞后恢复 | ct+causal |
| 17 | 1 | v2 | 薄壁件数控加工颤振 ↔ 算法稳定币死亡螺旋 | ct+time |
| 18 | 1 | v1 | RCU读写无锁 ↔ TCP TIME_WAIT | ct+time |
| 19 | 1 | v1 | Polycomb S型扩散 ↔ 止损流动性螺旋 | ct+bnd |
| 20 | 1 | v1 | 杠杆顺周期 ↔ AMM恒定乘积 | ct+causal |
| 21 | 1 | v1 | LDPC消息传递 ↔ 扩散语言模型去噪 | ct+cont |
| 22 | 1 | v1 | 横断面患病率 ↔ 相关性制度切换 | ct+time |
| 23 | 1 | v1 | 肥大细胞脱颗粒 ↔ 链上清算级联 | ct+stoch |
| 24 | 1 | v2 | CRISPR间隔数 ↔ VC幂律收益 | ct+stoch |
| 25 | 1 | v2 | 限流令牌桶 ↔ Piezo1机械门控 | ct+cont |
| 26 | 1 | v3 | 沉默螺旋 ↔ 逆向选择 | ct+causal |
| 27 | 1 | v3 | 对乙酰氨基酚毒性 ↔ 肿瘤铁死亡 | ct+dim |
| 28 | 1 | v2 | 湖泊富营养化 ↔ 蛋白质相分离 | ct+dim |
| 29 | 1 | v2 | Piezo1适应 ↔ 享乐跑步机参考点 | ct+time |
| 30 | 1 | v3 | Th1/Th2极化 ↔ 合成基因拨动开关 | ct+cont |
| 31 | 0 | v1 | TLB地址翻译 ↔ KV缓存推理 | ct |
| 32 | 0 | v1 | 量子误差缓解 ↔ 量化感知训练 | ct |
| 33 | 0 | v2 | 半导体激光器驰豫振荡 ↔ 稳定币锚定 | ct |
| 34 | 0 | v1 | 健康工人效应 ↔ 分布外泛化 | ct |
| 35 | 0 | v2 | 渗流阈值 ↔ 技术采纳鸿沟 | ct |
| 36 | 0 | v3 | 闪崩流动性螺旋 ↔ 链上清算级联 | ct |
| 37 | 0 | v3 | 保证金螺旋 ↔ 链上清算级联 | ct |
| 38 | 0 | v3 | 链上清算级联 ↔ 银行挤兑 | ct |
| 39 | 0 | v2 | 湖泊富营养化 ↔ 绿色撒哈拉 | ct |
| 40 | 0 | v3 | 链上清算级联 ↔ 对手方风险传染 | ct |
| 41 | 0 | v2 | 交通拥堵非线性 ↔ 热固性树脂凝胶点 | ct |
| 42 | 0 | v2 | 生态系统突变 ↔ 热固性树脂凝胶点 | ct |
| 43 | 0 | v3 | 闪崩流动性螺旋 ↔ DeFi清算瀑布 | ct |
| 44 | 0 | v2 | 费托合成相重构 ↔ 热固性树脂凝胶点 | ct |
| 45 | 0 | v1 | 非寿险链梯法 ↔ 洪水路由Muskingum | ct |
| 46 | 0 | v1 | 抵押品再质押 ↔ 清算瀑布级联 | ct |
| 47 | 0 | v1 | 二度价格歧视 ↔ RLHF | ct |
| 48 | 0 | v1 | 跨市场Spoofing ↔ 闪电贷预言机操纵 | ct |
| 49 | 0 | v1 | 竞争风险生存分析 ↔ 压力测试损失聚合 | ct |
| 50 | 0 | v1 | In-Band Metadata路由 ↔ TraceID/SRv6 | ct |
| 51 | 0 | v1 | 多基因风险评分 ↔ 档案模糊匹配 | ct |
| 52 | 0 | v1 | LLM能力涌现相变 ↔ CDO相关性陷阱 | ct |
| 53 | 0 | v1 | 量子误差缓解 ↔ 任务向量算术 | ct |
| 54 | 0 | v1 | 信号博弈分离均衡 ↔ RLHF | ct |
| 55 | 0 | v2 | 技术采用跨越鸿沟 ↔ 热固性树脂凝胶点 | ct |
| 56 | 0 | v3 | 高层建筑风振TMD ↔ 电力系统PSS | ct |
| 57 | 0 | v3 | 次级制裁连锁 ↔ 供应链牛鞭效应 | ct |
| 58 | 0 | v3 | DeFi清算瀑布 ↔ 社会网络级联失效 | ct |
| 59 | 0 | v3 | 保证金螺旋 ↔ 银行挤兑 | ct |
| 60 | 0 | v3 | 供应链级联断裂 ↔ 金融风险传染 | ct |
| 61 | 0 | v2 | 认知失调一致性 ↔ Lyapunov稳定性 | ct |
| 62 | 0 | v3 | 士气崩溃阈值 ↔ 社会证明从众阈值 | ct |
| 63 | 0 | v3 | 政策扩散竞争学习 ↔ VC跟投信号级联 | ct |

Abbreviations: `ct` = concept_transfer, `dim` = dim_shift, `bnd` = boundary_rewrite, `time` = time_scaling, `causal` = causal_inversion, `cont` = continuity_toggle, `stoch` = stochastic_toggle.

---

## Appendix B — Output files

- `/Users/wanqh/Projects/structural-isomorphism/v3/results/v1v2v3-transformation-labeled.jsonl` — 63 candidates with full original fields + `primitives` + `primitive_count` + `transformation_depth` + `primitive_rationale` + `is_shallow` + `is_deep`
- `/Users/wanqh/Projects/structural-isomorphism/site/docs/v4-transformation-analysis.md` — this report
