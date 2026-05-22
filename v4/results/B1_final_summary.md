***REMOVED*** B1 — Layer-3 Critic Pass: Final Authoritative Taxonomy

**Date**: 2026-05-22
**Candidates reviewed**: 21
**Active universality classes (final)**: 11

***REMOVED******REMOVED*** 一句话总结

21 个候选普适类经 Layer-3 critic 逐条审查 + ensemble 交叉核验后，收口为 **11 个站得住的 active 普适类**：3 个被 REJECT（统计极限定理伪装 / 博弈论概念簇，不是动力学普适类），4 个被 SPLIT（机制不纯，拆成更紧的子类），4 个 provenance 重复变体被 MERGE 进规范类。反例库共 78 条，并从成员列表剔除 9 个 false-positive 成员。

***REMOVED******REMOVED*** 权威性说明

- **权威基准 = B1 critic**（人工逐条审查，`layer3_critic.jsonl`）。本脚本只是把已有的 critic 结论固化成结构化清单，没有推翻 critic 判断。
- B3 / B4 ensemble 是**辅助视角**。特别注意 B4 DeepSeek 用了极严苛 prompt，把几乎所有类都判 REJECT（连 scheffer / second_order_damped 这种铁打 KEEP 也 REJECT），因此 B4 **不作权威**，只用于给真正悬而未决的 merge 问题做 tie-break。
- DeepSeek V4 补判**只对悬而未决的类调用**（critic 自己用 'possibly/could/consider/subtle' 犹豫措辞、且 ensemble 又不同意），不全量重跑。

***REMOVED******REMOVED*** 最终 11 个 Active 普适类

| ***REMOVED*** | class_id | 中文名 | critic verdict | 干净成员 | 反例 | 来源 |
|---|---|---|---|---|---|---|
| 1 | `scheffer_fold_bifurcation` | Scheffer 折叠分岔类 | KEEP (high) | 9 | 13 | critic |
| 2 | `motter_lai_network_cascade` | Motter-Lai 负载重分配网络级联类 | KEEP (high) | 3 | 8 | critic |
| 3 | `tail_copula_contagion` | 尾部 Copula 传染类 | KEEP (medium) | 4 | 5 | critic |
| 4 | `delay_differential_debt` | 延迟反馈与债务累积类 | KEEP (medium) | 3 | 5 | critic |
| 5 | `percolation_connectivity` | 渗流临界相变与 tipping point 类 | KEEP (high) | 2 | 6 | critic |
| 6 | `preferential_attachment` | 偏好连接幂律分布类 | KEEP (high) | 2 | 6 | critic |
| 7 | `reaction_diffusion_steady_state_class` | 稳态反应-扩散梯度场类 | KEEP (high) | 3 | 5 | critic |
| 8 | `second_order_damped_oscillator` | 二阶阻尼振子类 | KEEP (high) | 3 | 5 | critic |
| 9 | `reflexive_fixed_point_class` | 反身性不动点与测量反馈类 | KEEP (medium) | 3 | 5 | critic+DeepSeek |
| 10 | `scale_free_percolation_class` | 无标度网络渗流与级联类 | KEEP (medium) | 2 | 6 | critic+DeepSeek |
| 11 | `gardner_collins_toggle_switch` | Hill 超敏正反馈双稳态开关类 | KEEP (high) | 7 | 14 | critic |

***REMOVED******REMOVED******REMOVED*** 每个 active 类为什么留下

**1. Scheffer 折叠分岔类** (`scheffer_fold_bifurcation`)

- 机制原型: Saddle-node (fold) bifurcation in a slow variable with positive feedback giving bistability + critical slowing down
- 合并了 provenance 重复变体: hysteresis_first_order_transition_fertility
- 干净成员 9 个；剔除 false-positive 4 个: 形状记忆合金马氏体逆变, 果胶凝胶网络, 淀粉糊化, 热障涂层的热应力分岔
- 反例库 13 条

**2. Motter-Lai 负载重分配网络级联类** (`motter_lai_network_cascade`)

- 机制原型: Motter-Lai (2002) & Eisenberg-Noe clearing (2001)
- 合并了 provenance 重复变体: motter_lai_network_cascade_social
- 干净成员 3 个（无 false positive）
- 反例库 8 条

**3. 尾部 Copula 传染类** (`tail_copula_contagion`)

- 机制原型: Lower-tail dependence in a copula: asymptotic dependence coefficient λ_L = lim P(U<u|V<u)
- 干净成员 4 个；剔除 false-positive 1 个: 冰期终结的非线性触发
- 反例库 5 条

**4. 延迟反馈与债务累积类** (`delay_differential_debt`)

- 机制原型: Volterra delay equation (1928) / Mackey-Glass (1977)
- 干净成员 3 个（无 false positive）
- 反例库 5 条

**5. 渗流临界相变与 tipping point 类** (`percolation_connectivity`)

- 机制原型: Broadbent-Hammersley percolation (1957) / Granovetter threshold model (1978)
- 干净成员 2 个；剔除 false-positive 1 个: 主动管理与指数化的流动性外部性
- 反例库 6 条

**6. 偏好连接幂律分布类** (`preferential_attachment`)

- 机制原型: Yule (1925) / Simon (1955) / Barabási-Albert (1999)
- 干净成员 2 个；剔除 false-positive 1 个: 足球联赛积分的幂律分布
- 反例库 6 条

**7. 稳态反应-扩散梯度场类** (`reaction_diffusion_steady_state_class`)

- 机制原型: Fick (1855) / Poisson equation / French flag morphogen (Wolpert 1969)
- 干净成员 3 个（无 false positive）
- 反例库 5 条

**8. 二阶阻尼振子类** (`second_order_damped_oscillator`)

- 机制原型: Hooke + Newton (17C) / LCR circuit
- 干净成员 3 个（无 false positive）
- 反例库 5 条

**9. 反身性不动点与测量反馈类** (`reflexive_fixed_point_class`)

- 机制原型: Muth rational expectations (1961) / Soros reflexivity / Goodhart (1975)
- 干净成员 3 个（无 false positive）
- 反例库 5 条
- DeepSeek supplemental: INDEPENDENT (conf 0.7) — The reflexive fixed-point class centers on self-fulfilling expectations and social feedback loops driving multistability, whereas hysteresis_first_order_transition_fertility involves discontinuous phase transitions with path-dependent memory effects. Under Clauset/Stumpf-Porter criteria, the critical mechanisms differ (expectation dynamics vs. nucleation/barrier crossing), and no shared scaling exponents or governing equations are evident; merging would dilute conceptual specificity.

**10. 无标度网络渗流与级联类** (`scale_free_percolation_class`)

- 机制原型: Cohen-Erez-ben-Avraham-Havlin (2000) & Barabási-Albert (1999)
- 干净成员 2 个；剔除 false-positive 1 个: 网络安全险的相关性难题
- 反例库 6 条
- DeepSeek supplemental: INDEPENDENT (conf 0.9) — Scale-free percolation concerns critical behavior (e.g., threshold vanishing, non-mean-field exponents for 2<γ<3) on fixed heterogeneous networks, while preferential attachment describes the dynamical growth rule that generates the degree distribution. Their equation forms (order parameter vs. attachment kernel) and critical mechanisms differ fundamentally, so they are distinct universality classes.

**11. Hill 超敏正反馈双稳态开关类** (`gardner_collins_toggle_switch`)

- 机制原型: Gardner-Cantor-Collins toggle switch (2000) / Griffith Hill switch (1968)
- 合并了 provenance 重复变体: gardner_collins_toggle_switch_Th1Th2, gardner_collins_toggle_switch_apoptosis
- 干净成员 7 个；剔除 false-positive 1 个: 胰岛素信号通路与发育时序门控
- 反例库 14 条

***REMOVED******REMOVED*** 被 REJECT 的 3 个候选（站不住，不进 active 清单）

- **`schelling_credible_commitment`** (confidence medium)
  - Schelling credible-commitment is a GAME-THEORETIC equilibrium-selection phenomenon, not a dynamical universality class. The shared 'equation' (payoff(commit) > payoff(flexible) iff sunk_cost > defection_gain) is a static inequality, not a scaling law or critical exponent. (1) 时间不一致性 is the Kydland-Prescott problem about policy reoptimization, distinct from Schelling commitment (no sunk cost device
- **`extreme_value_tail_class`** (confidence high)
  - EVT (Fisher-Tippett-Gnedenko + Pickands-Balkema-de Haan) is a STATISTICAL LIMIT THEOREM, analogous to CLT — it tells you that IF X_i are iid with regularly varying tail, THEN max(X_i) converges to GEV. It is NOT a universality class in the dynamical/critical-phenomena sense; it has no 'shared mechanism' beyond 'tails are regularly varying'. Every member of this class shares a statistical descripto
- **`markov_chain_memory_fidelity_class`** (confidence high)
  - First-order Markov property is a VERY GENERIC statistical structure that any memoryless or near-memoryless process exhibits — like CLT and EVT, it is a limit theorem (the property of being well-approximated by a Markov chain is preserved across an enormous diversity of mechanisms). Calling this a universality class is a category error: ALL of (a) DNA methylation inheritance via DNMT1, (b) X-inacti

***REMOVED******REMOVED*** 被 SPLIT 的 4 个候选（机制不纯，拆解后不作单一 active 类）

- **`hysteresis_preisach`** (confidence medium)
  - 拆分方案: Split into (a) Preisach-Mayergoyz distributed hysteron class (magnetism, soil-moisture retention, possibly DeFi liquidation cycles) — keeps the ∫∫μ(α,β) machinery; (b) Maxwell first-order transition with simple hysteresis (gelation, traffic phase transition, liquefaction) — uses Landau φ⁴ or Ginzburg-Landau free energy.
- **`leaky_integrate_fire_threshold_class`** (confidence medium)
  - 拆分方案: Keep neuronal LIF + token-bucket (both true integrate-fire-reset). Move Piezo1 to mechano-gating class (separate). Move hedonic adaptation to a 'continuous setpoint-adaptation' class (no firing).
- **`adverse_selection_unraveling_class`** (confidence high)
  - 拆分方案: Split into (a) genuine Akerlof economic adverse selection (lemons, insurance, credit) — keeps E[q|p] mechanism; (b) social conformity-driven opinion homogenization (silent spiral, echo chamber, filter bubble) — uses opinion dynamics models like Deffuant or DeGroot, not Akerlof.
- **`sir_contagion_network_class`** (confidence medium)
  - 拆分方案: Split into (a) true SIR with recovery (epidemics, rumor with stifling, marketing-fatigue) — needs R₀, γ; (b) financial cascade with NO recovery (already in motter_lai_network_cascade class). Then this class becomes a true SIR class. Without split, this class conflates SIR with SI/M-L.

***REMOVED******REMOVED*** 被 MERGE 的 4 个变体（provenance 重复，并入规范类）

- `gardner_collins_toggle_switch_Th1Th2` → 并入 `gardner_collins_toggle_switch`
- `gardner_collins_toggle_switch_apoptosis` → 并入 `gardner_collins_toggle_switch`
- `hysteresis_first_order_transition_fertility` → 并入 `scheffer_fold_bifurcation`
- `motter_lai_network_cascade_social` → 并入 `motter_lai_network_cascade`

***REMOVED******REMOVED*** LLM 补判记录

识别出 3 个悬而未决的类（critic 犹豫 + ensemble 分歧）：

- **`reflexive_fixed_point_class`**: critic hedged merge ('Consider merging with hysteresis_first_order_transition_fertility — both share b...'); B3=KEEP, B4=REJECT
  - DeepSeek V4 判定: **INDEPENDENT** (merge_target=None, conf=0.7)
  - 理由: The reflexive fixed-point class centers on self-fulfilling expectations and social feedback loops driving multistability, whereas hysteresis_first_order_transition_fertility involves discontinuous phase transitions with path-dependent memory effects. Under Clauset/Stumpf-Porter criteria, the critica
- **`hysteresis_first_order_transition_fertility`**: critic hedged merge ('Possibly with scheffer_fold_bifurcation (both are fold/saddle-node + positive fe...'); B3=MERGE, B4=REJECT
  - DeepSeek V4 判定: **MERGE** (merge_target=scheffer_fold_bifurcation, conf=0.9)
  - 理由: Both classes share the same normal form equation dx/dt = r + x^2 (or equivalent cubic-like nonlinearity) for a saddle-node bifurcation, with identical critical slowing down exponents (relaxation time ~ |r - r_c|^{-1/2}) and the same underlying mechanism of positive feedback-induced bistability. The 
- **`scale_free_percolation_class`**: critic hedged merge ('Could merge with preferential_attachment (same topology root) but distinct empha...'); B3=REJECT, B4=REJECT
  - DeepSeek V4 判定: **INDEPENDENT** (merge_target=None, conf=0.9)
  - 理由: Scale-free percolation concerns critical behavior (e.g., threshold vanishing, non-mean-field exponents for 2<γ<3) on fixed heterogeneous networks, while preferential attachment describes the dynamical growth rule that generates the degree distribution. Their equation forms (order parameter vs. attac

***REMOVED******REMOVED*** 反例库规模

- 总计 **78 条反例**，分两类：
  - near_miss: critic 精选的「表面像但机制不同」的近似现象
  - false_positive_member: 从候选成员列表中被剔除的 9 个机制不匹配成员
- 反例库已结构化写入 B1_final_taxonomy.jsonl 每个 active 类的 negative_examples 字段。

***REMOVED******REMOVED*** 输出文件

- `v4/results/B1_final_taxonomy.jsonl` — 每个 active 类一行（id / 中英文名 / 机制原型 / 不变量 / 干净成员 / 反例库 / verdict 来源）
- `v4/results/B1_final_summary.md` — 本文件
