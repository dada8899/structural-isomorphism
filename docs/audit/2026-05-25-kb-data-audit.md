# KB Data Quality Audit — 2026-05-25

> Audit agent: read-only 检查 KB 数据完整性 + Wave 2 (19 jsonl)、Wave 3 B (200) 、Wave 3 C (300) 的实际质量。
> 范围：`data/kb-5000-merged.jsonl` + `data/kb-additions-2026-05-25-*.jsonl` (20 个) + `data/kb-reproducible-data-layer-2026-05-25.jsonl` + `docs/v04-validation-plan/per-class/` (18) + `v4/validation/` (57) + `docs/wave3-c-longtail/` + `dataset_card.md` + `docs/sessions/C1-unified-preprint-draft-v0.4.md` + `scripts/merge_data_layer.py`。
> **本报告只读，未改任何文件，未 commit/push。**

## TL;DR

- **整体打分：7.2/10**。数据文件本身 valid + 结构完整 + ID 不冲突，但有 4 处 P0 / 5 处 P1 在文档、命名约定与"宣传数字"之间存在 drift。
- **P0 (4)**：
  1. **KB 总数 5,388 是错的**：dataset_card.md L64 + C1 v0.4 paper §3.5 abstract 都把 Wave 3B (200) 当成净新增条目，但 Wave 3B 是对已有条目的 data_layer 注解扩展（200/200 在主 KB 已存在）。真实净新增上限 = 4888 + 300 (Wave 3C) + 145 (Wave 2 未合并) = **5,333**（且尚未真正合并到主 KB；磁盘上的主 KB 仍是 4,888 行）。
  2. **dataset_card.md L67 宣称的字段 `data_provenance ∈ {REAL, SYNTHETIC, MIXED}` 不存在**：扫了 1,128 条 additions+layer 条目，0 条带 `data_provenance` 字段。最近的字段是 Wave 3B 内部 `data_layer.validation_status ∈ {empirical, synthetic, anchor, pending}`。文档承诺了一个不存在的 schema。
  3. **Wave 2 KB additions 有 56/145 (~39%) type_id 不在主 KB 84 个范围内**：6 个文件把 type_id 写成 `"6"`、`"7"`（应为 `"06"`、`"07"` 零填充）或者 full class 名（如 `"extreme_value_tail_class"`、`"rfp"`、`"scale_free_percolation_class"`、`"gardner_collins_toggle_switch"`、`"markov_chain_memory_fidelity_class"`）。这些直接 merge 到主 KB 会破坏 type_id schema 的一致性。
  4. **paper §3.5 abstract 多处数字 round 后没核**：5388 / 4888+200+300 在四份文档（paper §3.5 abstract L30、paper §6 L449、dataset_card L57、dataset_card L64、SESSION-23-HANDOFF L34）一致 propagate；任一份订正都会让另外三份继续矛盾。
- **P1 (5)**：见 §H + 各 Section。
- **P2**：长尾文档 boilerplate suffix 在 区块链/内分泌学/公共卫生/植物学/半导体 共 ~140 条（47%）出现 50 字以上的同一段 padding 文本；详见 §D。

---

## Section A: Main KB (`data/kb-5000-merged.jsonl`)

| 指标 | 期望 | 实测 | 状态 |
|---|---|---|---|
| 行数 | 4888 | **4888** | ✅ |
| valid JSONL（json.loads 全过） | 100% | 0 parse error | ✅ |
| 必填字段 `id/name/domain/type_id/description` 全有 | 100% | 0 missing-field row | ✅ |
| id 唯一 | 100% | 4888 unique / 4888 total | ✅ |
| unique `domain` | 215 | **215** | ✅ |
| unique `type_id` | 84 | **84** | ✅ |
| type_id schema | 全 `"01"`–`"84"` 零填充 | 全 `"01"`–`"84"` | ✅ |

主 KB 健康。

---

## Section B: Wave 2 KB additions (19 个 `kb-additions-2026-05-25-*.jsonl`)

### B.1 文件计数

任务文档说"18 个 KB additions"，实际目录里**有 19 个 Wave 2 jsonl + 1 个 Wave 3 C long-tail batch = 20 个 `2026-05-25` 文件**。多出来的 19th 是 `manna-sandpile.jsonl`（8 条），它没有对应 `docs/v04-validation-plan/per-class/` brief，但有 `v4/validation/manna-sandpile/` 目录。属于 P1：要么把 manna-sandpile 升格为 19th 班级 brief，要么从 jsonl 列表里移除（manna-sandpile 应属于 SOC 验证而非 v0.4 18 班级）。

### B.2 逐文件计数

| 文件 (短名) | 行数 |
|---|---:|
| adverse-selection | 8 |
| anderson-localization | 7 |
| delay-differential-debt | 8 |
| extreme-value-tail | 8 |
| fractional-brownian-crossings | 8 |
| gardner-collins-toggle | 8 |
| gardner-collins-toggle-v2 | 7 |
| hysteresis-first-order | 6 |
| leaky-integrate-fire | 8 |
| manna-sandpile (多出来的) | 8 |
| markov-memory-fidelity | 8 |
| percolation-connectivity | 6 |
| preisach-hysteresis-cascade | 7 |
| reaction-diffusion | 8 |
| reflexive-fixed-point | 8 |
| scale-free-percolation | 8 |
| schelling-credible-commitment | 8 |
| second-order-damped-osc | 8 |
| tail-copula-contagion | 8 |
| **合计** | **145** |

### B.3 内容校验

| 指标 | 实测 | 状态 |
|---|---|---|
| 每行 valid JSON | 145/145 | ✅ |
| 5 必填字段 | 145/145 | ✅ |
| schema 统一 (`description, domain, id, name, type_id`) | 145/145 单一 schema | ✅ |
| id 唯一（W2 内） | 145 unique | ✅ |
| id 与主 KB 冲突 | **0** | ✅ |
| description ≥ 100 字 | 145/145 | ✅ |
| **type_id 在主 KB 84 个范围内** | **89/145**（56 条不在！） | ❌ **P0** |

### B.4 type_id schema drift（**P0**）

| 错误 type_id 值 | 出现次数 | 涉及文件 |
|---|---:|---|
| `"6"`（应为 `"06"`） | 8 | tail-copula-contagion |
| `"7"`（应为 `"07"`） | 8 | delay-differential-debt |
| `"extreme_value_tail_class"` (full class name string) | 8 | extreme-value-tail |
| `"gardner_collins_toggle_switch"` | 8 | gardner-collins-toggle (v1) |
| `"markov_chain_memory_fidelity_class"` | 8 | markov-memory-fidelity |
| `"rfp"` (full class name) | 8 | reflexive-fixed-point |
| `"scale_free_percolation_class"` | 8 | scale-free-percolation |

**这意味着**：6 个 Wave 2 sub-agent 把"class_id"误写到了 `type_id` 字段。可能的修复路径：
- (a) 加 `class_id` 字段保留分类信息，把 `type_id` 重写为正确的 `"01"`–`"84"`；或
- (b) 写一个 normalisation step（一次性 sed/python）：`"6" → "06"`、`"7" → "07"`、把 full-name string 改成对应的 numeric type_id。

如果直接 `cat` 这 6 个文件 merge 到主 KB，会让主 KB 的 `unique type_id` 从 84 增到 91（多了 7 个 schema-illegal 值），所有下游分析（type_id 分组、grep、API）都会失败。

### B.5 命名一致性

19 个 jsonl 文件命名格式统一：`kb-additions-2026-05-25-<short-class>.jsonl`。但与 `docs/v04-validation-plan/per-class/<class>_<...>.md` 的 brief 名 stem 经过 underscore→hyphen 转换还不能直接对齐（详见 §F）。

---

## Section C: Wave 3 B `data/kb-reproducible-data-layer-2026-05-25.jsonl`

### C.1 数量 + 字段

| 指标 | spec/期望 | 实测 | 状态 |
|---|---|---|---|
| 行数 | 200 | **200** | ✅ |
| id 唯一 | 200 | 200 | ✅ |
| id 全部在主 KB（"0 orphans"）| 0 orphans | **0 orphans** | ✅ |
| **id 与主 KB 是 join 关系，不是 net 新增** | — | **200/200 已在主 KB** | ⚠️ **影响 §H 数字** |
| `data_layer` 字段存在 | 200/200 | 200/200 | ✅ |
| `dataset_url` not null | 171 | **171** | ✅ |
| `dataset_doi` not null | 67 | **67** | ✅ |
| `validation_status == "empirical"` | 34 | **34** | ✅ |
| schema 统一 (6 顶层字段) | 200/200 | 200/200 | ✅ |
| `data_layer` 子字段统一 (14 个) | 200/200 | 200/200 | ✅ |

### C.2 validation_status 分布

| status | count |
|---|---:|
| pending | 160 |
| empirical | 34 |
| synthetic | 5 |
| anchor | 1 |

### C.3 selection_tier / hub 分布

| tier | count |
|---|---:|
| 1 | 107 |
| 2 | 82 |
| 3 | 11 |

`is_hub_member=True` 共 11 条。

### C.4 dataset_license 分布（top 10）

| license | count |
|---|---:|
| CC-BY-4.0 | 42 |
| CC-BY-NC-SA | 23 |
| Synthetic / model-based | 20 |
| NASA Public Domain | 19 |
| JHU TDB academic use | 16 |
| **Unknown** | **9** |
| Public Domain (US Govt) | 8 |
| DataCenterHub TOS | 6 |
| Yahoo TOS (research) | 4 |
| Public Domain (US DOE) | 4 |

**问题**：顶层 `license` 字段 = None for all 200。`license` 信息只在 `data_layer.dataset_license` 里。dataset_card 没有 documented 这点；任何 downstream 拿顶层 license 的人会 0 命中。

### C.5 sample URL 真实性检查（不发 HTTP，只看格式）

抽 10 个 `dataset_url`，格式都是真实 URL（`https://`），来源主要为 finance.yahoo.com / dune.com / data.transportation.gov / fdic.gov 等公开数据站点。**未发现 placeholder / mock URL**。

### C.6 description 长度

200 条里 **54 条**（27%） description < 100 字。原因：data layer 直接继承主 KB description，而主 KB 一些早期条目（如 `5k-01-***`、`kb5k02-***`）描述本来就短。这不是 Wave 3 B 的产出 bug，但 §C 的 description 不应被 Wave 3 B 评价（它没生成新的 description）。

---

## Section D: Wave 3 C `data/kb-additions-2026-05-25-long-tail-batch.jsonl`

### D.1 数量 + 字段

| 指标 | spec/期望 | 实测 | 状态 |
|---|---|---|---|
| 行数 | 300 | **300** | ✅ |
| id 唯一 | 300 | 300 | ✅ |
| id 与主 KB 冲突 | 0 | 0 | ✅ |
| 5 必填字段 | 300/300 | 300/300 | ✅ |
| schema 统一 | 300/300 | 单一 schema | ✅ |
| description ≥ 150 字 | 300/300 | **300/300** | ✅ |
| **type_id 全在主 KB 84 个内** | 100% | **100%** | ✅ |

### D.2 domain 分布

每域 30 条，完美一致：

| domain | count |
|---|---:|
| 复分析 | 30 |
| 数论 | 30 |
| 群体遗传学 | 30 |
| 植物学 | 30 |
| 内分泌学 | 30 |
| 半导体 | 30 |
| 流体力学/声学 | 30 |
| 公共卫生 | 30 |
| 生物物理 | 30 |
| 区块链 | 30 |

### D.3 type_id 分布（所有都在主 KB 84 个 type_id 内）

| type_id | count |
|---|---:|
| 06 | 1 |
| 07 | 120 |
| 10 | 6 |
| 11 | 6 |
| 12 | 2 |
| 13 | 7 |
| 14 | 3 |
| 17 | 4 |
| 18 | 2 |
| 20 | 22 |
| 22 | 8 |
| 23 | 41 |
| 24 | 2 |
| 26 | 2 |
| 32 | 35 |
| 35 | 7 |
| 37 | 4 |
| 38 | 2 |
| 40 | 1 |
| 47 | 1 |
| 60 | 10 |
| 65 | 5 |
| 67 | 9 |

`07` (自洽方程 S 形序参量) + `23` (渗流阈值导电网络) + `32` (Langevin SDE) 三大类合计 196/300 (65%) — 与长尾域的特点（多为热力学/相变/随机过程基底）一致。

### D.4 每域 name 不重复

10/10 域 30/30 unique name，0 duplicate。✅

### D.5 文献引用真实性（抽 10 条样本）

10/10 都含具体 Author + Year 引用（如 Stark 1971-80、Bloch 1925、Newell-Price Lancet 2006、Boron-Boulpaep 2017、Bond-Keeley 2005 TREE、Charlesworth-Morgan-Charlesworth 1993、Wiles 1995 Ann. Math、Liu arXiv:2206.11974 2022、Tao-Vu、Wolf Lancet 2014）。**未发现 placeholder 引用**。

### D.6 Boilerplate suffix 检测（**P2 — 质量隐忧**）

扫描 description 末尾 50 字符的 collision，发现 6 段固定模板被反复追加用以达到 150 字阈值：

| 模板片段（末 50 字） | 出现次数 | 主要域 |
|---|---:|---|
| `...NICE等机构定期更新指南。低中收入国(LMIC)与高收入国(HIC)实施挑战不同，需上下文化策略。` | 23/300 | 公共卫生 / 内分泌学 |
| `...学(MRI/CT/超声)综合判断。治疗策略涵盖激素替代、受体调节、外科切除与靶向药物，需个体化方案。` | 19/300 | 内分泌学 |
| `...array等手段，DNS/LES数值模拟提供精细结构。工业应用涵盖航空、声学、能源、环境等多领域。` | 19/300 | 流体力学/声学 |
| `...、应变工程综合调控。代工厂(TSMC/Samsung/Intel)的工艺节点演进直接映射该参数空间。` | 17/300 | 半导体 |
| `...与作物育种、抗逆性改良工程紧密关联。结构上跨植物-动物-微生物呈现保守性，是发育生物学跨界范式之一。` | 15/300 | 植物学 |
| `...rail of Bits)与formal verification (Certora)是核心防御层。` | 13/300 | 区块链 |
| `...有相应实验工具。理论模型常用统计力学、随机过程、连续介质力学融合描述。是分子机器与活物质研究的核心。` | 11/300 | 生物物理 |

合计 ~117/300 (39%) 条目带这种"通用收尾段"。Substring 命中（不止末尾）：
- "成本效益(QALY/DALY)" → 23 条
- "低中收入国(LMIC)" → 23 条
- "审计公司(OpenZeppelin/Trail of Bits)" → 13 条

**影响**：description 字数硬性 ≥ 150 的合规没问题，但**最后 30–50 字属于 padding 而非领域信息**。如果用 description 做 embedding 检索，这些 padding 会污染相似度（尤其同域内 30 条共享 padding 文本，会被算成"高度相似"）。

**建议修复路径**：
- (a) 把这 ~117 条 description 拉出来人工或 LLM-rewrite，把末尾 padding 换成具体的"该机制对应的关键测量量 / 验证文献"；
- (b) 或在 embedding 流程里加 description 末 50 字 strip 处理（cheap workaround）。

### D.7 per-domain 文档

`docs/wave3-c-longtail/per-domain/` 下确实 10 个 `.md` 文件（每域一个），每个 ~50 行，包含「子主题切分 (1-10/11-20/21-30)」「与已 verified universality class 的关联」「type_id 分布」「质量备注」。抽查 `复分析.md`、`区块链.md` 内容真实、有 30 条对应说明。✅

`docs/wave3-c-longtail/INDEX.md` 存在。

---

## Section E: v04-validation-plan 一致性

### E.1 文件计数

| 目录 | 期望 | 实测 |
|---|---|---|
| `docs/v04-validation-plan/per-class/` | 16–18 个 | **18** ✅ |
| `v4/validation/` | — | 57（含 27 个 SOC 验证 + 18 个 v0.4 班级 + 12 个其他/pre-reg/null）|

### E.2 18 个 per-class brief vs v4/validation/ 对齐

经 `-class`/`-switch`/`-transition`/`-threshold` 后缀模糊匹配后，**18/18 brief 都能找到对应的 `v4/validation/<dir>/`**。

| brief 文件名 stem | matched v4/validation dir |
|---|---|
| adverse_selection_unraveling_class | adverse-selection-unraveling |
| anderson_localization | anderson-localization |
| delay_differential_debt | delay-differential-debt |
| extreme_value_tail_class | extreme-value-tail |
| fractional_brownian_crossings | fractional-brownian-crossings |
| gardner_collins_toggle_switch | gardner-collins-toggle |
| gardner_collins_toggle_switch_v2 | gardner-collins-toggle-v2 |
| hysteresis_first_order_transition | hysteresis-first-order |
| leaky_integrate_fire_threshold_class | leaky-integrate-fire |
| markov_chain_memory_fidelity_class | markov-memory-fidelity |
| percolation_connectivity | percolation-connectivity |
| preisach_hysteresis_cascade | preisach-hysteresis-cascade |
| reaction_diffusion_steady_state_class | reaction-diffusion-steady-state |
| reflexive_fixed_point_class | reflexive-fixed-point |
| scale_free_percolation_class | scale-free-percolation |
| schelling_credible_commitment | schelling-credible-commitment |
| second_order_damped_oscillator | second-order-damped-oscillator |
| tail_copula_contagion | tail-copula-contagion |

### E.3 alpha-band drift（P1）

抽查 `leaky_integrate_fire_threshold_class.md` (brief) vs `v4/validation/leaky-integrate-fire/verdict.md`:
- **Brief** 声称 3 个 member：Piezo1 mechanotransduction / hedonic treadmill / token bucket，pre-reg band τ_relax/T_event ∈ [3, 30]。
- **Verdict** 实际跑了 5 个 member：`lif_synthetic` / `allen_brain_neural` / `financial_bursts` / `hydraulic_burst` / `sensor_cascade`，pre-reg band 同 [3, 30] 但 2/5 命中，verdict = **PARTIAL-shifted-band**，observed [1.02, 6.48]。

**brief member list 与 verdict member list 完全不同**（3 个 vs 5 个，且 0 重叠）。这是 P1 — pre-reg 阶段写的 3 个 members 后来在执行阶段被替换成另外 5 个，没人回头更新 brief。

`anderson_localization`、`delay_differential_debt`、`markov_chain_memory_fidelity_class` brief vs verdict member 大致一致，verdict 与 brief 期望一致（anderson PASS、DDE REJECT-confirmed、markov REJECT-CONFIRMED）。

---

## Section F: 命名约定审计

### F.1 Wave 2 KB additions JSONL 命名

19 个文件命名格式统一：`kb-additions-2026-05-25-<short-class>.jsonl`（`<short-class>` 是 brief stem 去掉 `_class`/`_switch`/`_transition`/`_threshold` 后缀的 hyphen 版）。**格式一致 ✅**。

但与 brief stem 不是 1:1：`leaky-integrate-fire` jsonl 对应 `leaky_integrate_fire_threshold_class.md`、`markov-memory-fidelity` jsonl 对应 `markov_chain_memory_fidelity_class.md` —— 推荐 brief 和 jsonl 都走 short form（去后缀）以减少 audit 时的模糊匹配。

### F.2 v4/validation/ 目录命名

57 个目录用 hyphen-snake，stem 与 jsonl 同形式（去后缀的 short form）。**与 jsonl 命名一致 ✅**。但与 brief stem 仍然要走 `_class/_switch/_transition` 后缀剥离才能匹配（P2 噪声）。

### F.3 id 前缀约定（**P1 — 不一致**）

抽样 Wave 2 各 jsonl 的 id prefix：

| 文件 | id 前缀 |
|---|---|
| gardner-collins-toggle | `toggle-x3-001` |
| reflexive-fixed-point | `reflexive-w2a-001` |
| tail-copula-contagion | `tail-copula-contagion-x4-001` |
| extreme-value-tail | `extreme-value-tail-001` |
| scale-free-percolation | `scale-free-percolation-001` |
| markov-memory-fidelity | `markov-memory-fidelity-001` |
| delay-differential-debt | `delay-differential-debt-x1-001` |
| long-tail-batch | `longtail-complex-analysis-NNN`/`longtail-number-theory-NNN`... |

**至少 4 种不同 id 前缀规约**：
- `<class>-w2a-NNN` (Wave 2 a 标志)
- `<class>-x1-NNN`、`<class>-x3-NNN`、`<class>-x4-NNN`（wave-ID 编号）
- `<class>-NNN`（无 wave tag）
- `toggle-x3-NNN`（用 short 别名 + wave-ID）

建议未来定一个规范：`<class-short>-<wave>-NNN`（如 `<class>-w2-NNN`），统一前缀。

---

## Section G: KB merge 流程

### G.1 `scripts/merge_data_layer.py`

| 检查项 | 结果 |
|---|---|
| import + argparse 正常 | ✅ |
| `python3 scripts/merge_data_layer.py --dry-run` 跑通 | ✅（见下） |

dry-run 输出：

```
=== merge_data_layer ===
kb        : data/kb-5000-merged.jsonl  (4888 rows)
layer     : data/kb-reproducible-data-layer-2026-05-25.jsonl  (200 rows)
matched   : 200
overwrite : 0 (kb rows already had data_layer)
untouched : 4688 (no matching layer id)
orphans   : 0 (layer rows with no kb id)
status_dist (post-merge): {'no_data_layer': 4688, 'pending': 160, 'synthetic': 5, 'empirical': 34, 'anchor': 1}
```

✅ merge 流程逻辑正确，0 orphans 与 spec 一致。**merge 之后还是 4888 行**（因为 Wave 3 B 是给 200 个现有条目加 `data_layer` 字段，不是新增条目）—— 这印证了 §H 的数字 discrepancy。

### G.2 Wave 2 + Wave 3 C 的 net-add merge helper

**缺**：没有一个统一脚本把 19 个 Wave 2 jsonl + 1 个 Wave 3 C long-tail jsonl 合并到主 KB。注释说 "Wave 2/3 都不动主 KB"，所以可能是有意为之，但 paper / dataset_card 把这些数字"加进 KB"了，等于 paper 在描述一个**尚未发生的 merge**。

**建议**：要么补 `scripts/merge_kb_additions.py`（带 type_id schema normalisation！见 B.4），要么在 paper / dataset_card 明确写"作为可选增量提供，主 KB 未合并"。

### G.3 主 KB 当前还是 4888（**确认**）

`wc -l data/kb-5000-merged.jsonl` = 4888。无合并产物 `data/kb-5000-merged-with-layer.jsonl`（merge_data_layer.py 默认输出路径）存在。

---

## Section H: 数字 cross-check (**P0 — 5,388 是错的**)

### H.1 几份文档中的"KB total"

| 文档 | 行号 | 声称 |
|---|---|---|
| `docs/sessions/SESSION-23-HANDOFF.md` | L34 | KB entries 4,888 → **5,388**（+500：Wave 3B +200 + Wave 3C +300）|
| `dataset_card.md` | L57, L63–64 | 5,088 → **5,388**（Wave 3B +200, Wave 3C +300）|
| `docs/sessions/C1-unified-preprint-draft-v0.4.md` | L30, L85, L449 | KB 4,888 → **5,388** entries（4,888 + 200 + ~300）|

**3 份文档全在重复 +500 这个数。**

### H.2 实测数字

| 项 | 文件 | 行数 | 与主 KB 关系 | 是否合并 |
|---|---|---:|---|---|
| 主 KB | kb-5000-merged.jsonl | **4,888** | — | — |
| Wave 3 B 数据层 | kb-reproducible-data-layer-2026-05-25.jsonl | 200 | **全部 id 已在主 KB**（注解非新增） | 通过 merge_data_layer.py 加 `data_layer` 字段（dry-run OK，未应用）|
| Wave 3 C 长尾 | kb-additions-2026-05-25-long-tail-batch.jsonl | 300 | **0/300 在主 KB**（净新增）| **未合并** |
| Wave 2 (2026-05-25, 19 个 jsonl) | 各班级 jsonl | 145 | **0/145 在主 KB**（净新增）| **未合并** |
| Wave 2026-05-24 additions (16 个 jsonl) | 各域 jsonl | 483 | **413/483 已在主 KB**（70 条净未合并）| 部分合并 |

### H.3 正确的算账

| 场景 | KB 行数 |
|---|---:|
| 当前主 KB（磁盘真实状态） | **4,888** |
| 若 merge Wave 3 B data layer（merge_data_layer.py）| **4,888**（不增加行数，加字段）|
| 若 merge Wave 3 C 长尾（300 条净新增）| 4,888 + 300 = **5,188** |
| 若 merge Wave 3 C + Wave 2（145 条净新增）| 4,888 + 300 + 145 = **5,333** |
| 若 merge Wave 3 C + Wave 2 + 2026-05-24 未合并的 70 条 | 4,888 + 300 + 145 + 70 = **5,403** |
| **文档宣称值** | **5,388** |
| 文档宣称值的算式 | 4,888 + 200 (Wave 3B 错算成新增) + 300 (Wave 3C) = 5,388 |

### H.4 结论

**5,388 在数学上等于 4,888 + 200 + 300，但 200 那部分是错算的**：Wave 3 B 并不增加 KB 行数，它只给已有 200 条加 metadata。

正确的"全合并"上限是 5,333（不含 2026-05-24 未合并的 70 条；含则 5,403）。**5,388 在任何 merge 场景下都不会出现**。

**推荐订正方案**（按代价从低到高）：
- (a) **最低代价**：把 paper §3.5 / dataset_card L64 / SESSION-23-HANDOFF L34 的 "5,388" 改成 "5,333" 并加注释 "（200 Wave 3B 为已有条目的 data_layer 注解扩展，不计入行数；300 Wave 3C 长尾 + 145 Wave 2 班级 sub-agent KB extension 共 +445 净新增）"。
- (b) **次低代价**：真把 Wave 3 C (300) + Wave 2 (145) merge 到主 KB（先 normalise Wave 2 的 type_id schema 见 B.4），并写一份 `5333` 的 dataset_card。
- (c) 最少要在 paper 里把 "5,388 entries" 改成 "4,888 KB rows + 200 data_layer annotations + 300 long-tail additions + 145 v0.4 class anchors = 5,388 KB+annotation records" 之类不歧义的措辞。

---

## Section I: 数据 license 合规

### I.1 Wave 3 B (200 entries)

| 类型 | count |
|---|---:|
| 开放/CC 类（CC-BY-4.0 / CC-BY-NC-SA / Public Domain / ODbL / CC0 / NIH Public / NORC public）| 约 110 |
| 政府公开域（NASA / US Govt / NOAA / US DOE / US EPA / US DOL / NTSB / US DOT）| 约 45 |
| 学术使用 TOS（JHU TDB / DataCenterHub / CBOE / Allen Institute / SNAP / Pushshift / CoW / NBER / Yahoo / Crunchbase paid / OECD / IUCN / Addgene）| 约 36 |
| **Unknown** | **9** |
| Synthetic / 模型生成（不需 license）| 20 |

### I.2 风险点

- **9 条 dataset_license == "Unknown"**（P1）：这些条目要么补 license 元数据，要么标 "license-uncertain" 让下游用 reservation 限制。
- **Crunchbase TOS (paid for full)** 1 条：商用 + 付费访问。建议 dataset_card 显式标注"该条目仅引用，不分发数据"。
- **Yahoo TOS / CBOE TOS / CoW academic use**：academic-only TOS 的条目（共约 8 条）需要在 dataset_card 加"非学术用途禁止"的明确语。

### I.3 整体合规

未发现明显违法/侵权来源；未发现 placeholder URL（如 `example.com`）；未发现 raw scraping 来源（如 unauthorised crawl）。**整体 license 合规风险低**，9 条 Unknown + 少数学术 TOS 是可以补救的标注问题。

---

## Section J: 其他小发现

- `data/kb-additions-2026-05-25-manna-sandpile.jsonl` 是第 19 个 Wave 2 jsonl，但**无对应 per-class brief**（虽然有 `v4/validation/manna-sandpile/` 目录）。这是 brief vs jsonl 数量从 18 vs 19 的来源。
- `data/kb-5000-merged.jsonl.bak-session22` 备份存在（4888 行同步前的快照），便于回滚。
- `gardner-collins-toggle/` (v1) 与 `gardner-collins-toggle-v2/` (v2) 是同一班级的两个验证 run。两者各有独立 verdict.md。dataset_card / paper 应明确说明 v0.4 verdict 用的是 v1 还是 v2（否则 reader 不知道 verdict 表里的 gardner-collins-toggle 指哪个）。
- Wave 3 B `validation_status="synthetic"` 的 5 条全部 `dataset_url=None`（合理，因为本质是模型生成数据）。
- 没有任何文件包含字段 `data_provenance`（dataset_card L67 提到的 schema 不存在 — **P0** 见 TL;DR）。

---

## P0 / P1 / P2 fixes

### P0（必修）

1. **统一 KB 计数措辞**（H.4 (a) 方案最低代价）：dataset_card L57/L63–64 + paper L30/L85/L449 + SESSION-23-HANDOFF L34 全部把 "5,388" 重新校准（要么改 5,333 + 解释，要么明确 "annotation records vs net rows" 区分）。**不订正会让外审 / 复现者直接发现"jsonl 行数对不上"。**
2. **删掉或落实 `data_provenance` 字段**：dataset_card L67 声称 "(from Wave 3B onward) `data_provenance` ∈ {REAL, SYNTHETIC, MIXED}" 完全不存在。要么 (a) 删掉这句，要么 (b) 真的给 Wave 3 B/C 200 + 300 + 145 条加这个字段（推荐 (a)）。
3. **Wave 2 KB additions 的 type_id schema drift**：56/145 条 type_id 不是合法 `"01"`–`"84"`。直接 merge 会污染主 KB。修：写一个 `scripts/normalise_wave2_type_id.py` 把 `"6"→"06"`、`"7"→"07"`、full-name string → numeric type_id。merge 前必跑。
4. **paper §3.5 abstract 数字**：连带 issue #1，paper L30/L85/L449 + L449 abstract 全部 propagate 同一个 5388。

### P1（高优）

5. **leaky_integrate_fire_threshold_class brief member list 与 verdict member list 0 重叠**（E.3）：brief 写的是 Piezo1 + hedonic + token-bucket（3 member），verdict 跑的是 lif_synthetic + allen_brain + financial_bursts + hydraulic_burst + sensor_cascade（5 member）。修：更新 brief 反映实际跑的 5 member（或加 "pre-reg member list was revised at execution time" 的 amendment 段）。
6. **manna-sandpile 在 Wave 2 jsonl 但不在 18 per-class brief**：要么把它升格为 brief（19th 班级），要么从 Wave 2 jsonl 移除（搬到 SOC validation 目录下）。
7. **id 前缀规约不一**（F.3）：8 种以上不同 id 前缀格式。未来 Wave 4+ 拍一个 standard：`<class-short>-w<wave>-NNN`。
8. **Wave 3 B 9 条 dataset_license == "Unknown"**（I.2）：补完整 license 信息或显式标 license-uncertain。
9. **没有 merge_kb_additions.py 帮 net-adders 合并**（G.2）：写一个统一脚本帮 Wave 2 145 + Wave 3 C 300 + 2026-05-24 未合并 70 条 一次性 merge 到主 KB（先做 type_id normalisation）。

### P2（可选优化）

10. **Wave 3 C 长尾 ~117/300 条带 boilerplate suffix**（D.6）：6 段固定 padding 文本被反复追加。embedding-pipeline 应至少 strip 末 50 字，或人工/LLM rewrite 替换为具体测量量 / 文献。
11. **gardner-collins-toggle v1 vs v2 在 verdict 表里要明确指代**（J）。
12. **dataset_card 顶层 `license` 字段全 None**，license 信息只在 `data_layer.dataset_license`。文档应澄清。
13. **brief stem 与 jsonl 命名仍需后缀剥离才能匹配**（F.2）：未来统一 short form。

---

## Audit metadata

- 审计时间：2026-05-25
- 审计工具：python3 (json / glob / collections / re) + bash (wc / ls / grep)
- 主要数据源（read-only access only）：
  - `data/kb-5000-merged.jsonl`
  - `data/kb-additions-2026-05-25-*.jsonl` (20 files)
  - `data/kb-additions-2026-05-24-*.jsonl` (16 files, for cross-check)
  - `data/kb-reproducible-data-layer-2026-05-25.jsonl`
  - `docs/v04-validation-plan/per-class/*.md` (18 files)
  - `docs/wave3-c-longtail/per-domain/*.md` (10 files)
  - `v4/validation/*/verdict.md` (sample: leaky-integrate-fire, markov-memory-fidelity, anderson-localization, delay-differential-debt)
  - `dataset_card.md`
  - `docs/sessions/SESSION-23-HANDOFF.md`
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md`
  - `scripts/merge_data_layer.py`
- 输出文件：仅本报告（`docs/audit/2026-05-25-kb-data-audit.md`），未修改其他任何文件。
