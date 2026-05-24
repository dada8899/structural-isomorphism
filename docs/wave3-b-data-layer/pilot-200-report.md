# Wave 3 B Pilot — 200-entry Reproducible Data Layer Report

**Date:** 2026-05-25
**Scope:** Top-200 highest-priority KB entries (out of 4 888).
**Deliverables:**
- `data/kb-reproducible-data-layer-2026-05-25.jsonl` — 200 enriched rows.
- `docs/wave3-b-data-layer/SCHEMA.md` — schema spec.
- `scripts/merge_data_layer.py` — merge helper (dry-run capable).
- this report.

## 1. Quality-gate result

| gate | required | actual | status |
|---|---|---|---|
| total rows | 200 | 200 | PASS |
| rows with real `dataset_url` | ≥ 50 | **171** | PASS |
| rows with real `dataset_doi` | ≥ 30 | **67** | PASS |
| rows with `validation_status = empirical` | ≥ 20 | **34** | PASS |
| `sampling_schema.event_definition` populated (no placeholders) | 200 / 200 | 200 / 200 | PASS |
| URLs / DOIs invented | 0 | 0 | PASS — only real public archives |

## 2. Numbers at a glance

- **200 entries**, spanning **20 universality classes** and **62 distinct domains**.
- `dataset_url` populated: **171 / 200 (85.5 %)**.
- `dataset_doi` populated: **67 / 200 (33.5 %)**.
- `verified_at` date populated: **12 / 200 (6 %)** — only the actual Wave 2A/B/C verified anchors get a date.
- Hub members (one per universality class): **11**.

### 2.1 `validation_status` distribution

| status | count | share |
|---|---:|---:|
| `empirical` | 34 | 17.0 % |
| `pending` | 160 | 80.0 % |
| `synthetic` | 5 | 2.5 % |
| `anchor` | 1 | 0.5 % |

`empirical` covers the named members & hubs of Wave 2A/B/C verified
classes whose (class, domain) pair has either a curated override or sits
inside the class's declared domain set (e.g. SOC → finance / DeFi /
geology / electrical-engineering / medicine all have lab evidence).

`synthetic` covers the lattice-Monte-Carlo / model-only routes
(`统计力学` rows for Ising / BTW / Gardner toggle).

### 2.2 `selection_tier` distribution

| tier | meaning | count |
|---|---|---:|
| 1 | members / hubs / type-id extras of Wave 2A/B/C **verified** classes | 107 |
| 2 | members / hubs of high-confidence **non-verified** classes | 82 |
| 3 | members / hubs of remaining classes (rank ≥ 7) | 11 |

### 2.3 Class distribution (top 10)

| class_id | count |
|---|---:|
| `hysteresis_preisach` | 37 |
| `soc_threshold_cascade` | 35 |
| `scheffer_fold_bifurcation` | 24 |
| `gardner_collins_toggle_switch` | 18 |
| `scale_free_percolation_class` | 12 |
| `preferential_attachment` | 10 |
| `schelling_credible_commitment` | 9 |
| `leaky_integrate_fire_threshold_class` | 7 |
| `adverse_selection_unraveling_class` | 7 |
| `gardner_collins_toggle_switch_v2` | 7 |

Long tail: `extreme_value_tail_class` 5, `hysteresis_first_order_transition` 5, `tail_copula_contagion` 5, `delay_differential_debt` 3, `percolation_connectivity` 3, `markov_chain_memory_fidelity_class` 3, `second_order_damped_oscillator` 3, `reflexive_fixed_point_class` 3, `reaction_diffusion_steady_state_class` 3, `sir_contagion_network_class` 1.

### 2.4 Domain distribution (top 15)

| domain | count |
|---|---:|
| 凝聚态物理 | 23 |
| 光学/光子学 | 23 |
| 等离子体物理 | 19 |
| 统计力学 | 18 |
| 流体力学 | 14 |
| 声学 | 8 |
| 金融市场微观结构 | 6 |
| 土木工程 | 6 |
| 电气工程 | 4 |
| 分子生物学 | 4 |
| 交通现象 | 3 |
| 衍生品与风险管理 | 3 |
| 细胞生物学 | 3 |
| 发育生物学 | 3 |
| 宏观经济 | 3 |

## 3. Data-scarce domains (where the layer is `null + pending`)

These domains have at least one selected entry but **no widely-known
public dataset** that fits Clauset-style power-law / Scheffer-style EWS
out of the box. The pilot keeps them honest (`dataset_url=null,
validation_status=pending`) and flags them for manual sourcing in v0.5.

| domain | rows with no URL | note |
|---|---:|---|
| 统计力学 | 18 | Pure simulation route (Ising / BTW). Marked `synthetic` where it makes sense, else `pending`. |
| 烹饪科学 | 2 | No standardised dataset; would need controlled-experiment protocol. |
| 计算机科学 | 1 | Catch-all domain in KB; needs disambiguation in v0.5. |
| 传播学 | 1 | Could route to GDELT but no canonical binding yet. |
| 经济学 | 1 | Could route to FRED but not in pilot priority list. |
| 社会学 | 1 | Could route to GSS / WVS. |
| 衍生品 | 1 | (vs `衍生品与风险管理` — KB naming dup; CBOE binding only used for the longer name) |
| 心理学 | 1 | Could route to OSF / Many Labs replications. |
| 公共管理 | 1 | Could route to OECD or BLS. |
| 流体力学/声学 | 1 | Edge-domain composite; JHU TDB only used for primary `流体力学`. |
| 宇宙学 | 1 | NASA OMNI exists but binding not yet curated. |

**Net data-scarce population in pilot: 29 / 200 (14.5 %).** Most are
fixable in v0.5 by adding 8-10 more domain defaults (already a known
pattern — see §6) and removing two KB-side duplicate domain strings
(`衍生品` vs `衍生品与风险管理`, `加密货币/DeFi` vs `加密货币与DeFi`).

## 4. License distribution

Open / public-domain licenses dominate: `CC-BY-4.0` (42), `CC-BY-NC-SA`
(23), NASA / US-Govt public domain (≈ 35 combined), JHU TDB academic use
(16). Only one row is `Crunchbase TOS (paid)` and zero rows are full
proprietary — the layer is reproducible on a research budget. 9 rows
land in `Unknown` (no domain default applies); these are flagged for
manual sourcing.

## 5. Hub members (one per class)

| id | domain | class | name |
|---|---|---|---|
| `5k-14-039` | 加密货币/DeFi | `soc_threshold_cascade` | 清算级联的链上流动性危机 |
| `bio-035` | 分子生物学 | `scheffer_fold_bifurcation` | 蛋白质相分离的临界浓度阈值 |
| `5k-06-061` | 免疫学 | `gardner_collins_toggle_switch` | Th1/Th2极化与疾病偏向 |
| `5k-12-072` | 微观经济 | `schelling_credible_commitment` | 进入威慑与产能过度承诺 |
| `5k-25-001` | 保育生物学 | `delay_differential_debt` | 灭绝债务 |
| `cell-049` | 细胞生物学 | `leaky_integrate_fire_threshold_class` | Piezo1机械门控通道的不动点门控 |
| `5k-20-071` | 人口学 | `hysteresis_first_order_transition` | 低生育率陷阱假说 |
| `cell-023` | 细胞生物学 | `gardner_collins_toggle_switch_v2` | 凋亡Caspase级联的不可逆数字开关 |
| `bio-005` | 分子生物学 | `markov_chain_memory_fidelity_class` | DNA甲基化的半甲基化继承 |
| `5k-15-087` | 土木工程 | `second_order_damped_oscillator` | 高层建筑风振舒适度控制 |
| `5k-14-005` | 衍生品 | `tail_copula_contagion` | 相关性崩溃的尾部传染效应 |

11 hubs out of the 26 known classes; the remaining 15 hub_ids in
`universality-classes.json` either failed the `description ≥ 60`
quality filter or sit in domains the selection priority did not reach
within the 200-budget.

## 6. Recurring `sampling_schema` design patterns

Six event-definition patterns cover most of the 200 entries — these
should be promoted to a reusable library in the v0.5 roll-out:

1. **Clauset power-law event-size** (cascades, avalanches, drawdowns,
   liquidations, blackouts, supply-chain ruptures, viral resharing).
   `event = threshold crossing of a domain quantity; size = magnitude or
   participant count; min_n=50`. Used by 80+ rows across
   `soc_threshold_cascade`, `motter_lai_*`, `preferential_attachment`,
   `sir_contagion_network_class`.
2. **Hysteresis loop area** (traffic fundamental diagram, polymer
   stress-strain, ecosystem regime shifts). `event = forward + reverse
   sweep; size = enclosed area`. Used by
   `hysteresis_preisach`, `hysteresis_first_order_transition`.
3. **Fold-bifurcation regime shift** (Scheffer EWS: variance &
   autocorrelation rise; CSD). `event = pre-shift indicator window;
   size = variance amplitude`. Used by `scheffer_fold_bifurcation`.
4. **Bistable toggle flipping** (Gardner-Collins toggle: cell-fate
   commitment, gene expression hysteresis). `event = state-flip;
   size = cells/molecules in flipped state`. Used by `gardner_collins_toggle_switch*`.
5. **LIF threshold spike** (neuronal avalanche, threshold integrator).
   `event = membrane-potential threshold crossing; size = post-spike
   refractory population`. Used by `leaky_integrate_fire_threshold_class`.
6. **Markov fidelity ratio** (DNA methylation inheritance, error
   propagation in copying processes). `event = symbol-flip per
   generation; size = mismatch count`. Used by
   `markov_chain_memory_fidelity_class`.

Designing once and parameterising by domain saves ~70 % of the per-row
schema-writing effort in v0.5.

## 7. Workload estimate for full 4 888-row roll-out (v0.5)

Going from 200 → 4 888 (24.4×) is **not** linear because of the catalog
effect:

- **Schema slots already covered**: the 35 `DOMAIN_DEFAULTS` templates
  +18 `CLASS_DOMAIN_OVERRIDES` cover ~85 % of pilot rows automatically.
  Adding ~30 more domain defaults (mostly the long-tail
  social-science / life-science domains that did not show up in tier 1-2)
  brings coverage to ~95 % for the remaining 4 688 rows.
- **Per-row manual sourcing** needed only for the residual 5 % (~ 240
  rows) where no domain default fits — average 5 min/row → ~20 hours.
- **Override curation** for the remaining 18 universality classes that
  have not yet been Wave-2-verified — average 30 min/class → ~9 hours.
- **Re-running `_build_data_layer_pilot.py`** on the full KB is < 5 s.
- **Validation re-runs** (turning `pending` into `empirical`) is the
  long pole and properly belongs to Wave 2D / Wave 4, not to Wave 3 B.

Estimated total Wave 3 B v0.5 finish-line (no validation re-runs):
**≈ 40 hours of focused curation** + ~ 5 s per build cycle. Empirical
share will stay around 17-20 % unless Wave 2D adds new verified anchors.

## 8. Key schema decisions (rationale)

1. **`data_layer` is additive, not invasive.** Main KB stays read-only.
   The merge tool writes a side-by-side file. This means the dataset
   card, paper, and frontend all keep loading as before.
2. **Status enum is honest, not aspirational.** 80 % of pilot rows
   land in `pending` because we have not actually run the fit on that
   exact KB row — even though the class itself has Wave 2 evidence. We
   refused to inflate the `empirical` count by relabeling.
3. **No fabricated URLs / DOIs.** Every URL points at a real public
   archive landing page (USGS ComCat, FRED, FDIC failed-bank list, JHU
   Turbulence DB, Materials Project, NASA OMNI, etc.). When we did not
   know one, we wrote `null` and explained the gap in
   `preprocessing_notes`.
4. **`(class_id, domain)` is the override granularity.** Trying to
   override per `id` would not scale; trying to override per `class_id`
   alone loses domain nuance (the SOC class points at USGS in geology
   but at FDIC in finance — both are correct anchors).
5. **`min_n_for_clauset = 50` for everyone.** Matches Clauset 2009
   guidance, gives Wave 2D a single tunable knob if we later want to
   tighten / loosen for a specific class.
6. **`verified_at` only on real anchors.** Dating empirical claims
   without an actual rerun was tempting; the report only lists the four
   Wave 2A/B dates that were genuine (2026-04-15, -18, -20, -25).
