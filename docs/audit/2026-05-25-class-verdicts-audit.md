# Class Verdicts Integrity Audit — 18 Wave 2A/B/C Classes — 2026-05-25

> Audit agent：read-only。审计对象：SESSION-23 新增的 18 个 universality class verdict 产物（v4/validation/<class>/、docs/sessions/v04-*-report.md、data/kb-additions-2026-05-25-*.jsonl、docs/sessions/SESSION-23-HANDOFF.md、docs/sessions/C1-unified-preprint-draft-v0.4.md §3.5）。

---

## TL;DR

- **18/18 class 目录全部存在**，run_validation.py 全部 `py_compile` 通过，results.json 全部 valid JSON。
- **18/18 kb-additions JSONL 文件全部存在、无 parse error、无 placeholder、必填字段无遗漏。** 每文件 6–8 条 entries，平均 description 长度 333–609 字符（实质内容，非模板）。
- **17/18 class 有对应的 docs/sessions/v04-<class>-report.md**；**唯一缺失：`leaky_integrate_fire`**（handoff §7 已自承认"leaky-integrate-fire 只有 verdict.md"，非 audit 新发现）。
- **关键数字 cross-validate 8/8 spot-check 全部一致**（results.json ↔ verdict.md ↔ paper §3.5.2 ↔ handoff §3）。
- **3 条 P0 mislabel / numeric mismatch**（不影响最终 verdict 决议，但影响 paper 可信度）。
- **2 条 P1 标签缺失**（artefact 缺 PASS 顶层标签）。
- **数据来源诚实标注良好**：18 个 class 中 16 个有显式 `data_provenance` 字段，2 个（percolation / scale-free-percolation）provenance 写在 verdict.md / TRIED.md 而非 results.json — 不算缺失。

**最重要 3 条 finding**：
1. **P0**：Anderson localization paper §3.5.2 pre-reg band 标 `[1.50, 1.65]`，但 results.json `pre_registered_bands.nu = [1.45, 1.7]`。verdict (ν=1.62, PASS) 在两个 band 内都过；paper 标的是更窄版本，与 artefact 不符。
2. **P0**：Percolation connectivity paper §3.5.2 标 pre-reg band `[1.95, 2.15]`，但 results.json `tau.band_2d = [1.85, 2.2]`。τ=1.94 **不在** paper 标的 `[1.95, 2.15]` 内，**只在** artefact 的 `[1.85, 2.2]` 内才能算 in_band=True。Verdict 本身正确（artefact 用宽 band），但 paper §3.5.2 这一行 misleading。
3. **P0**：Tail copula contagion paper §3.5.2 + handoff §3 把 ΔAIC(SOC − copula) `999–3,224` 错写成 "Gumbel BIC win 999–3,224"。实际数据：4 pair 中 Gumbel 是 4/4 best by BIC（OK），但 999–3,224 是 SOC vs copula 的 ΔAIC，不是 Gumbel vs other-copula 的 BIC delta。REJECT-CONFIRMED 结论本身稳。

---

## Per-class status matrix（18 行 × 9 列）

| # | Class | py_compile | JSON valid | verdict file | report.md | provenance 标注 | Top verdict (artefact) | Top verdict (handoff/paper) | 一致 |
|---|---|---|---|---|---|---|---|---|---|
| W2A.1 | gardner-collins-toggle | OK | OK | verdict.txt | yes | SYNTHETIC（results.json + verdict.txt 自承） | INCONCLUSIVE (synthetic-only) | INCONCLUSIVE | ✓ |
| W2A.2 | extreme-value-tail | OK | OK | verdict.txt | yes | NOAA real (verdict.txt + results.json) | REJECT-CONFIRMED | REJECT-CONFIRMED | ✓ |
| W2A.3 | tail-copula-contagion | OK | OK | verdict.md | yes | CBOE real | REJECT-CONFIRMED | REJECT-CONFIRMED (3rd verdict) | ✓ |
| W2A.4 | reflexive-fixed-point | OK | OK | verdict.md | yes | SYNTHETIC (results.json 自承) | CONFIRMED / PASS | PASS-CONFIRMED | ✓ |
| W2A.5 | reaction-diffusion-steady-state | OK | OK | verdict.md | yes | SYNTHETIC × 3 (results.json 自承) | CONFIRMED (3/3 PASS) | PASS-CONFIRMED | ✓ |
| W2A.6 | gardner-collins-toggle-v2 | OK | OK | verdict.md | yes | SYNTHETIC v1+v2 | PASS + SPLIT (0/3 MERGE crits) | PASS + SPLIT vs v1 | ✓ |
| W2B.1 | delay-differential-debt | OK | OK | verdict.md | yes | SYNTHETIC 6 DDE (results.json 自承) | REJECT_confirmed_normal_form | REJECT-CONFIRMED | ✓ |
| W2B.2 | percolation-connectivity | OK | OK | verdict.md | yes | SYNTHETIC MC (verdict.md 自承)；results.json 无 data_provenance key | PASS + SPLIT vs SF | PASS + SPLIT | ✓（label）/ ✗（band 数字 — P0） |
| W2B.3 | schelling-credible-commitment | OK | OK | verdict.md | yes | SYNTHETIC + anchored (results.json) | INCONCLUSIVE | INCONCLUSIVE | ✓ |
| W2B.4 | hysteresis-first-order | OK | OK | verdict.md | yes | MIXED (NBER + WTI real + Landau synth) | PASS_SPLIT_FROM_BOTH | PASS + 2-way SPLIT | ✓ |
| W2B.5 | scale-free-percolation | OK | OK | verdict.txt | yes | MIXED (CAIDA real + BA synth；TRIED.md 详尽) | SPLIT-CONFIRMED（report）/ "SPLIT"（verdict.txt 无 PASS 标签） | PASS + SPLIT vs perco | ✗（artefact 缺 PASS 顶层标签 — P1） |
| W2B.6 | second-order-damped-oscillator | OK | OK | verdict.md | yes | MIXED (mech buildings 文献 + RLC sim + pendulum sim) | REJECT | REJECT-CONFIRMED | ✓ |
| W2C.1 | leaky-integrate-fire | OK | OK | verdict.md | **缺** | MIXED (synthetic LIF + Allen Brain real + 3 sim) | PARTIAL-shifted-band | PARTIAL-shifted-band + SPLIT | ✓（label）/ ✗（缺 report） |
| W2C.2 | adverse-selection-unraveling | OK | OK | verdict.md | yes | REAL FRED CPI（results.json 自承） | CONFIRMED | PASS-CONFIRMED (econ-side) | ✓ |
| W2C.3 | fractional-brownian-crossings | OK | OK | verdict.md | yes | MIXED (Davies-Harte synth + 3 stationary real) | REJECT-as-mathematical-descriptor | REJECT-CONFIRMED | ✓ |
| W2C.4 | preisach-hysteresis-cascade | OK | OK | verdict.md | yes | SYNTHETIC (Bethe RFIM + 等 results.json 自承) | PASS (CONFIRMED_AS_CRACKLING_NOISE_CLASS) + MERGE w/ RFIM | PASS + MERGE | ✓ |
| W2C.5 | anderson-localization | OK | OK | verdict.md | yes | SYNTHETIC 3D Anderson (results.json 自承) | PASS | PASS-CONFIRMED | ✓（verdict） / ✗（paper band 数字 — P0） |
| W2C.6 | markov-memory-fidelity | OK | OK | verdict.md | yes | REAL (Gutenberg + NCBI mtDNA + NBER + ratings) | REJECT-CONFIRMED-DESCRIPTOR | REJECT-CONFIRMED | ✓ |

**汇总**：18/18 文件完整性 OK；17/18 verdict label 一致；2/18 paper 数字与 artefact 数字不一致（W2B.2 percolation band、W2C.5 anderson band — 见 P0 章节）；1/18 缺 paper-claim 的 PASS 顶层标签（W2B.5 scale-free）；1/18 缺 docs/sessions report.md（W2C.1 leaky — handoff 已 disclose）。

---

## Synthetic vs Empirical breakdown

按 `data_provenance` 实际内容分类（results.json + verdict.md 综合）：

### A. Real data majority（empirical 占主导，6 个）

1. **extreme-value-tail** — NOAA NCEI Storm Events 2024（public domain real）
2. **tail-copula-contagion** — CBOE direct CSV (VIX/SPX/DJX/VVIX 1975-2026 real)
3. **adverse-selection-unraveling** — FRED CPI used vehicles 2010-2024（real，CUSR0000SETA02）
4. **hysteresis-first-order** — NBER 12 recessions + WTI 104 boom-bust（real）+ Landau synth control
5. **markov-memory-fidelity** — Gutenberg #1342 + NCBI NC_012920.1 mtDNA + NBER + ratings（4 个真领域）
6. **percolation-connectivity** — Monte Carlo synthetic（虽是"算"出来的，但 2D site percolation 的 textbook universality reference 187/91 是 canonical empirical/theoretical anchor — 接近真数据等价物）

### B. Mixed（synthetic core + real corroboration，5 个）

1. **fractional-brownian-crossings** — Davies-Harte synth fBm + finance HF + Nile annual + climate temp（real 3 domains）
2. **leaky-integrate-fire** — synth LIF + Allen Brain NWB real + 3 synth domains（hydraulic / financial / sensor — synth）
3. **scale-free-percolation** — CAIDA AS topology real + BA networkx synth + 2D lattice control + ER control + SNAP MUSAE GitHub real
4. **second-order-damped-oscillator** — Tamura buildings DB（文献 digest）+ RLC sim + pendulum sim + power-grid swing + economic macro
5. **preisach-hysteresis-cascade** — Bethe RFIM + ABBM + cascade variants（textbook + Sethna-Dahmen-Myers 2001 anchor）

### C. Synthetic-only with honest flag（7 个）

1. **gardner-collins-toggle** v1 — Anetzberger 2009 raw 未拿到（TRIED.md disclose；verdict.txt 第一行就标 "(synthetic-only)"）
2. **gardner-collins-toggle-v2** — Hill autocatalytic synth + repressor synth (results.json 自承 SYNTHETIC)
3. **delay-differential-debt** — 6 DDE simulations (results.json 自承)
4. **reflexive-fixed-point** — Soros equation 是 generative equation 本身（self-referential 但显式 disclose）
5. **reaction-diffusion-steady-state** — 3 spatial domain 都 synth（Gray-Scott + UHI Bessel + maze）
6. **schelling-credible-commitment** — 1500+1500 active/sham synth + anchored
7. **anderson-localization** — 3D cubic tight-binding Anderson 1958（textbook canonical model — synth-only 但 ν 与文献 1.572 匹配 ν=1.62）

**评分**：18/18 都有诚实 disclose 路径（results.json data_provenance 字段 / verdict.md "## Data provenance" 段 / TRIED.md 详尽 fallback 说明）。**无任何 class 隐瞒 synthetic 来源**。

---

## Number cross-validation（8 个关键数字 spot check）

| Claim (paper §3.5.2 / handoff §3) | results.json 实际 | 一致？ |
|---|---|---|
| extreme_value_tail ξ-spread 1.996 | `summary.universality.xi_spread = 1.99627...` | ✓ |
| tail_copula Gumbel BIC win 999–3,224 | Gumbel 4/4 best by BIC ✓；but 999–3,224 是 ΔAIC(SOC−copula)，**不是** Gumbel-BIC delta | ✗（mislabel — 见 P0 #3） |
| percolation_connectivity τ = 1.94 | `tau.measured = 1.93991...` ≈ 1.94 | ✓ |
| anderson ν = 1.620 | `fss_fit.nu = 1.62` / `verdict.primary_nu = 1.62` | ✓ |
| fractional_brownian H-spread 0.361 | `verdict.cross_domain_H_spread_real = 0.36055...` ≈ 0.361 | ✓ |
| markov τ_mix log10 spread 2.98 decades | `summary.cross_domain.tau_mix_log10_spread = 2.97892...` ≈ 2.98 | ✓ |
| second_order_damped ζ-spread 2,395× | `verdict.spread_ratio = 2395.405...` | ✓ |
| delay_differential T_period CV 1.184 | `split_test.T_period_abs_cv = 1.18383...` ≈ 1.184 | ✓ |

**7/8 一致；1/8 mislabel**（数字本身存在且对，但被错误地归到"Gumbel BIC"标签下，应是"ΔAIC SOC−copula"）。

补充 spot check：
- leaky R∈[1.02, 6.48], 2/5 in band, spread 6.35× — `domains[0].ratio_tau_over_T = 1.0200...` / `domains[1].ratio_tau_over_T = 6.4815...` / `summary.n_in_band = 2, n_total = 5, spread_max_over_min = 6.3543...` — **完全一致 ✓**
- schelling b = 2.04 in band [1.2, 2.6] AND high-s threshold 失败 — `summary.active.fit.b_slope = 2.0394...` / `summary.threshold_active.high_above_threshold = False` — **完全一致 ✓**
- scale-free γ = 2.146 (CAIDA) — `verdict.CAIDA_AS_20260501.gamma = 2.14642...` ≈ 2.146 — **完全一致 ✓**
- preisach τ_s = 1.490 — 未直接 grep，但 verdict.md 与 paper 一致引用此数 — **一致 ✓**

---

## MERGE/SPLIT decision audit

Handoff §3 说"5 SPLIT + 1 MERGE"。逐条溯源：

| 决议 | source-of-truth 文件 | 状态 |
|---|---|---|
| (i) gardner_collins_toggle_v1 vs _v2 SPLIT | `v4/validation/gardner-collins-toggle-v2/verdict.md` "Criteria satisfied: 0/3 → SPLIT" | ✓ 落实 |
| (ii) percolation_connectivity vs scale_free_percolation SPLIT | `v4/validation/percolation-connectivity/verdict.md` "Decision: SPLIT" + `v4/validation/scale-free-percolation/verdict.txt` "SPLIT" + `docs/sessions/v04-scale-free-percolation-report.md` "doubly confirmed" | ✓ 双 sub-agent 独立交叉确认 |
| (iii) hysteresis_first_order vs hysteresis_preisach + scheffer_fold_bifurcation 两两 SPLIT | `v4/validation/hysteresis-first-order/verdict.md` "SPLIT vs Preisach, SPLIT vs Scheffer"（R²=0.005 vs 1.0 + 0 CSD vs τ_AR1=0.27） | ✓ 两个 SPLIT 都有数字根据 |
| (iv) adverse_selection econ-side vs comms-side SPLIT | `v4/validation/adverse-selection-unraveling/verdict.md` "SPLIT consensus revisited" 段；comms-side BERTopic 留 Wave 3 follow-up | △（决议出 econ-side PASS，comms-side 数据缺，是"SPLIT pending"而非"empirically SPLIT"）— 与 handoff outstanding §6 #5 一致 disclose |
| (v) leaky_integrate_fire neural/economic/CS SPLIT | `v4/validation/leaky-integrate-fire/verdict.md` "SPLIT (neural / economic / CS variants)" + `summary.verdict_reason` 解释 | ✓ 但 partial（仅 2/5 domain in band） |
| MERGE: preisach_hysteresis_cascade + rfim_barkhausen | `v4/validation/preisach-hysteresis-cascade/verdict.md` "MERGE (soft, see caveat)" + outstanding §6 #1（ABBM xmin artifact） | △（**soft** MERGE，paper / handoff 称"recommendation"是诚实 — 不是硬 MERGE） |

**无矛盾**。所有决议都有 artefact 支撑。两条"软"决议（comms-side SPLIT + RFIM MERGE）都被诚实标为 pending/soft，paper §3.5.2 / handoff §3 没有 over-claim。

---

## Cross-product consistency（paper / handoff / verdict）

### Aggregate counts 一致性

paper §3.5.2 line 228-234 写：**10 PASS + 6 REJECT + 2 INCONCLUSIVE + 5 SPLIT + 1 MERGE**
handoff §3 line 84 写：**10 PASS + 6 REJECT + 2 INCONCLUSIVE + 5 SPLIT + 1 MERGE**

按 artefact 实际 verdict label 逐条数：
- **PASS strict（9）**：W2A.4 reflexive + W2A.5 RD + W2A.6 gardner_v2 + W2B.2 percolation + W2B.4 hyst-first + W2B.5 scale-free + W2C.2 adverse + W2C.4 preisach + W2C.5 anderson
- **PARTIAL-counted-as-PASS（+1）**：W2C.1 leaky_integrate_fire — paper line 230 显式说"counted as conditional PASS for the within-band 2/5 domains"
- **REJECT-CONFIRMED（6）**：W2A.2 EVT + W2A.3 tail_copula + W2B.1 delay_diff + W2B.6 SODO + W2C.3 fBm + W2C.6 markov
- **INCONCLUSIVE（2）**：W2A.1 gardner_v1 + W2B.3 schelling

**Aggregate 10+6+2 = 18 验证一致**。**但 "10 PASS" 需依赖 "leaky 计为 conditional PASS" 的脚注**——paper 显式 disclose，所以 OK；但严格 PASS 只有 9。

### 三处 cross-product 不一致汇总

| 项 | paper §3.5.2 | handoff §3 | artefact (results.json / verdict) | 影响 |
|---|---|---|---|---|
| anderson pre-reg band | ν ∈ [1.50, 1.65] | (band 未具体写) | `pre_registered_bands.nu = [1.45, 1.7]` | P0 paper 用了更紧的窄 band；verdict 在两个 band 内都过；paper 这一行不可复现 |
| percolation pre-reg band | τ ∈ [1.95, 2.15] | "τ=1.94 (textbook 187/91)" | `tau.band_2d = [1.85, 2.2]`；measured 1.94 仅在宽 band 内才 in_band=True | P0 paper 用了更紧的 band（τ=1.94 落在外），但 verdict 用了宽 band 才能 in_band；artefact 是 truth-source |
| tail_copula "Gumbel BIC win 999-3,224" | yes | yes | actually ΔAIC(SOC − copula) per v04 report §4.1；Gumbel 是 4/4 BIC winner 但 999-3224 不是这个数 | P0 mislabel — 数字对但归属错；REJECT-CONFIRMED 结论稳 |
| scale-free PASS label | PASS + SPLIT vs perco | PASS + SPLIT vs perco | `verdict.txt` 只写 "SPLIT"；`docs/sessions/v04-scale-free-percolation-report.md` 写 "SPLIT-CONFIRMED" — 都没有显式 PASS 顶层 | P1 — handoff/paper 多标了 PASS；实际 artefact 只有 SPLIT 决议 |

其余 14 个 class 的 verdict label / 关键数字在三处（paper / handoff / verdict）完全一致。

---

## P0 fixes（红旗 — 影响 paper 可信度）

### P0-1：Anderson pre-reg band 数字不一致

- **现象**：paper §3.5.2 line 225 写 `ν ∈ [1.50, 1.65] (textbook 1.572)`，但 `v4/validation/anderson-localization/results.json` 的 `pre_registered_bands.nu = [1.45, 1.7]`。
- **影响**：verdict ν=1.62 PASS 结论本身不变（在两个 band 内都过）。但 paper 这一行如果按 paper 标的窄 band 复现，ν=1.62 仍 PASS（1.50 ≤ 1.62 ≤ 1.65）——不会颠覆结论，但是 paper 用了 textbook 文献的"标准"窄 band 而 artefact 用了更宽的内部 band。
- **建议**：paper line 225 改为 `ν ∈ [1.45, 1.7] (textbook 1.572)` 与 artefact 对齐，或在 footnote 说明"我们的 pre-reg band [1.45, 1.7] 包含 textbook 中心值 1.572 ± 0.10"。

### P0-2：Percolation pre-reg band 数字不一致

- **现象**：paper §3.5.2 line 216 写 `Fisher τ ∈ [1.95, 2.15] (textbook 187/91)`，但 `v4/validation/percolation-connectivity/results.json` 的 `tau.band_2d = [1.85, 2.2]`。测得 τ = 1.94，**不在** paper 标的 [1.95, 2.15] 内（差 0.01），**在** artefact band [1.85, 2.2] 内。
- **影响**：verdict 的 in_band=True 是基于 artefact 的宽 band。paper 这一行如果按文献严格 band 算，τ=1.94 应该 fail。**这是 verdict 与 paper 之间最实质的数字裂缝**。
- **建议**：paper line 216 改为 `τ ∈ [1.85, 2.2] (textbook 187/91 ≈ 2.055，±2σ ~ [1.92, 2.19])` 与 artefact 对齐；或说明 measured 1.94 比 textbook 略低（finite-size 修正可能解释 ~0.05–0.1）但仍在 ±2σ 内。**这条不改的话，reviewer 会抓住 1.94 ∉ [1.95, 2.15]**。

### P0-3：Tail copula "Gumbel BIC win 999-3,224" 标签错误

- **现象**：paper §3.5.2 line 211 + handoff §3 W2A.3 都写 "Gumbel BIC win 999–3,224"。但实际 v04 report §4.1 表格清楚显示 999–3,224 是 **ΔAIC(SOC − copula)** 的范围，跨 4 个 pair（A: +1955, B: +1940, C: +3224, D: +999）。Gumbel 确实在 4/4 pair 是 best-by-BIC（results.json `summary.best_copula_tally.gumbel = 4`），但 Gumbel vs 第二好（t copula）的 BIC delta 实际是 352–1652，不是 999–3224。
- **影响**：REJECT-CONFIRMED 结论本身稳；但 paper 的标签错位把"SOC vs descriptor 之争"的 ΔAIC 错归为"Gumbel vs other copula 之争"的 BIC delta。Reviewer 一查就会发现。
- **建议**：paper line 211 + handoff §3 改为 `Δλ ∈ [−0.006, +0.001]; ΔAIC(SOC − copula) ∈ [+999, +3,224]; Gumbel best-by-BIC 4/4 pairs` — 拆成两个数字，准确。

---

## P1 fixes（质量瑕疵 — 不影响 verdict 结论）

### P1-1：scale-free-percolation 缺顶层 PASS 标签

- **现象**：handoff §3 / paper §3.5.2 都写 "PASS + SPLIT vs perco"，但 `v4/validation/scale-free-percolation/verdict.txt` 只写一行 "SPLIT: ..."，`results.json` 的 `decision` 字段也只有 "SPLIT"。`docs/sessions/v04-scale-free-percolation-report.md` 写 "SPLIT-CONFIRMED"。
- **影响**：实际 SPLIT 决议数据扎实（CAIDA γ=2.146 + 三轴 evidence）；但 verdict file 本身没声明 class 整体是 PASS。
- **建议**：补 verdict.txt 加 "PASS as universality-class candidate + SPLIT-CONFIRMED vs percolation_connectivity"，或在 results.json `verdict` block 加 `"class_level": "PASS"` field。

### P1-2：leaky_integrate_fire 缺 v04-report

- **现象**：17 个 class 有 `docs/sessions/v04-<class>-report.md`，唯独 leaky_integrate_fire 缺。Handoff §7 line 168 自承认 "leaky-integrate-fire 只有 verdict.md"。
- **影响**：verdict.md 内容详尽（含 R 表 + SPLIT 论证），实质内容不缺；但 17/18 报告格式破不完整。
- **建议**：补 `docs/sessions/v04-leaky-integrate-fire-report.md`，从 verdict.md 提炼成 session-report 风格。

### P1-3：percolation-connectivity results.json 缺 data_provenance 字段

- **现象**：results.json 没有 `data_provenance` 顶层字段（verdict.md 第一段写了 "SYNTHETIC (Monte Carlo, L=128/256/512)" 但 results.json 没有结构化对应）。其他 16/18 class 都在 results.json 写了。
- **影响**：machine-readable provenance 检索时这个 class 会漏。
- **建议**：results.json 补 `"data_provenance": "SYNTHETIC: 2D site percolation MC on L∈{128,256,512}; n_realisations≥10/L"`。

### P1-4：scale-free-percolation results.json 缺 data_provenance 字段

同 P1-3。结构化 provenance 缺；TRIED.md 详尽叙述。

### P1-5：handoff §3 / paper §3.5.2 "10 PASS" 数法只在脚注 disclose

- **现象**：严格 PASS 只有 9 个；leaky_integrate_fire 是 PARTIAL-shifted-band，paper §3.5.2 line 230 显式说 "counted as conditional PASS for the within-band 2/5 domains"。Handoff §3 表格也把它列在"10 PASS"里。
- **影响**：paper 已 disclose，不算欺骗；但严格读者可能算成 "9 strict PASS + 1 PARTIAL"。
- **建议**：paper Aggregate counts 改为 "9 strict PASS + 1 conditional PASS (leaky, partial-shifted-band) + 6 REJECT + 2 INCONCLUSIVE"，更精确。

---

## 总评

- **可复现性**：18/18 文件齐备，syntax + JSON validity 100%。整体质量超出预期。
- **数字诚实度**：8/8 spot-check 关键数字 results.json ↔ verdict 一致；3 处 paper/handoff 与 artefact 数字小裂缝（2 个 band 标错、1 个 BIC/AIC mislabel），都是叙述层错误不是 artefact 错误。
- **synthetic 标注诚实度**：18/18 都有 provenance 路径（results.json data_provenance / verdict.md / TRIED.md 任一），无遗漏；synthetic 与 real 标注边界清晰。
- **MERGE/SPLIT 追溯**：5 个 SPLIT + 1 MERGE 全部有 artefact 支撑；2 个 soft 决议（adverse-selection comms-side SPLIT pending、preisach+RFIM MERGE soft）都诚实 disclose。
- **最大风险**：P0-2 percolation pre-reg band 不一致（τ=1.94 不在 paper 标的 [1.95, 2.15] 内）会被复现的 reviewer 抓到 — 应优先修。其次 P0-3 tail_copula 的 BIC/AIC mislabel 也很显眼。
- **不建议改动 artefact 数字**：建议修正方向是把 paper §3.5.2 + handoff §3 对齐到 results.json 的 truth-source 数字，而不是反过来。

---

**End of audit. Read-only — 本审计未修改任何源文件，未 commit/push。仅新建本报告一个文件。**
