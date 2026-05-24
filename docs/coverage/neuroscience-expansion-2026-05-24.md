# Neuroscience KB 跨 type_id 补足 — 2026-05-24（X1 第 2 顺位）

> X1 报告把 **neuroscience 跨 type_id 补足** 列为 Top 2 ★★★ 扩展项：当前 53 条几乎只覆盖 type_id 23 / 42；指数衰减 / 扩散 / 时滞反馈 / 混沌 / 一阶相变 / 网络级联 6 个高频 type_id 在 neuroscience × type_id cell 上全 = 0。本轮补 **80 条**，全部含真实学术引用 + 至少一个定量观察。

---

## 0. 交付物（路径）

| 文件 | 用途 |
|---|---|
| `data/kb-additions-2026-05-24-neuroscience.jsonl` | 80 条新条目（JSONL，同 schema） |
| `scripts/update_kb_embeddings_neuroscience.py` | 增量 embedding 计算脚本（幂等 + 自动 .bak） |
| `web/backend/tests/test_kb_neuroscience_coverage.py` | sanity test：5 个关键 query 必须召回 |
| `docs/coverage/neuroscience-expansion-2026-05-24.md` | 本报告 |

> **不会自动合入主 KB**：本轮新条目以独立 jsonl 增量形式交付。合入 `data/kb-expanded.jsonl` 是单独运维步骤（保持 commit 边界清晰）。

---

## 1. 分类统计

### 1.1 按 X1 报告点名的 9 大类（spec ↔ delivered）

| 大类 | spec | delivered | type_id | 说明 |
|---|---|---|---|---|
| 指数衰减 / 时间常数 | 10 | **10** | 06 | 突触 EPSC τ / 膜 RC / fEPSP / 受体脱敏 / LTP / 钙瞬变 / GABA-A IPSC / 工作记忆 |
| 扩散 / 反应扩散 | 10 | **10** | 32 | Turing 方向柱 / 行波 / SD / 钙波 / 神经递质 / BOLD PSF / gamma 前沿 / 癫痫扩散 / pinwheel / K+ buffering |
| 时滞反馈 / 振荡 | 10 | **10** | 13 | 生理震颤 / gamma / theta / alpha / 呼吸 / circadian / 睡眠 90min / HRV Mayer / hippus / STN-GPe beta |
| 混沌 / 非线性动力学 | 10 | **10** | 23 | HR / Hopf / EEG / 嗅球 KIII / Morris-Lecar / 癫痫预警 / HRV / edge-of-chaos / 纺锤波 / 气味识别 |
| 一阶相变 | 8 | **8** | 25 | 麻醉 / sleep-wake / 癫痫起始 / 神经元双稳态 / 工作记忆持续放电 / 脑死亡 / criticality at edge / Up-Down |
| 网络级联 | 10 | **12** | 21 | 癫痫雪崩 / SOC 幂律 / synfire chain / 卒中 SD / 连接组失稳 / 偏头痛 aura / α-syn 朊样 / 流行病模型 / 血流响应 / tonotopic / 癫痫病灶 / traveling pulse |
| 认知 / 行为现象 | 10 | **10** | 08/03/06/11 | 反应时幂律 / 学习幂律 / Ebbinghaus / Stevens / Hick / Fitts / Weber-Fechner / 工作记忆 4±1 / Miller 7±2 / 任务切换 |
| 病理 / 临床 | 10 | **9** | 06/07/13/21/23/26/32 | PD 震颤 / AD 斑块 / 偏头痛 aura / 卒中阈值 / HD CAG / 癫痫招募 / ALS 指数死亡 / MS 级联 / Epileptor |
| 跨尺度 | 5 | **1** | 73 | IIT Φ 跨尺度（其余 4 个跨尺度题材已分散到上面 8 类的高跨度条目里，避免人为重复） |
| **合计** | **83** | **80** | | spec 求和 83，本轮严格按用户上限 **80 条**交付 |

> **关于"跨尺度 5 条 → 实交 1 条"**：跨尺度本质不是新现象而是"跨多尺度同一现象"。强行凑 5 条会与已有 8 大类高度重复。改为：除显式列入 cross_scale 的 IIT Φ（neuro-x1-080）外，跨尺度属性通过 9 条多尺度题材在描述中显式标注（如 neuro-x1-013 SD 单细胞→组织、neuro-x1-053 hub→全脑、neuro-x1-072 Aβ 蛋白→认知）。

### 1.2 按 type_id 分布（新增条目）

| type_id | 中文名 | 本轮新增 | 此前 neuroscience × type_id |
|---|---|---|---|
| 06 | 指数衰减 | 13 | 0 → **13** |
| 21 | 网络级联 | 13 | 0 → **13** |
| 32 | 扩散 / 反应扩散 | 11 | 0 → **11** |
| 13 | 时滞反馈 | 11 | 0 → **11** |
| 23 | 混沌 | 11 | 已有少量 → +11 |
| 25 | 一阶相变 | 8 | 0 → **8** |
| 08 | 幂律 | 3 | 已有 → +3 |
| 03 | 对数律 | 3 | 0 → **3** |
| 26 | 阈值机制 | 3 | 0 → **3** |
| 11 | 容量上限 | 2 | 0 → **2** |
| 07 | 指数增长 | 1 | 0 → **1** |
| 73 | 跨尺度涌现 | 1 | 0 → **1** |

→ **X1 报告里点名的 6 个空白 type_id（06/13/21/23/25/32）全部填补**，每类至少 8 条。

### 1.3 按 domain 拆分

| domain | 条数 |
|---|---|
| 神经科学 | 69 |
| 认知神经科学 | 11 |

> 全部归在 X1 audit 的 `neuroscience` 学科类下（53 条 → 133 条，提升 ~150%）。

### 1.4 描述质量

| 指标 | 值 |
|---|---|
| 平均描述长度 | 171.3 字（spec ≥ 50） |
| 最短描述 | 137 字 |
| 含数值/频段/时间常数的条目 | 80/80 (100%) |
| 含真实学术引用的条目 | 80/80 (100%) |
| ID 与 name 是否与现有 KB 冲突 | 无 |

---

## 2. Top 10 ROI 同构对子（X1 §3 对子表的 neuroscience 侧补强）

按"用户最可能搜 × 这次补足后两侧都能召回 × 跨域结构 isomorphism 经典度"打分：

| # | neuroscience 侧（本轮新增） | 跨域对侧（KB 已有） | 同构结构 |
|---|---|---|---|
| **1** | 癫痫雪崩级联（neuro-x1-049/050）— SOC 幂律 P(s) ∝ s^(-1.5) | flash crash / liquidity shock（已有 7-18 条） | **SOC 临界级联** — 经典对子之一 |
| **2** | 突触 EPSC 指数衰减（neuro-x1-001）τ ≈ 2-5 ms | 放射性衰变 / 用户留存衰减（已有 124 条） | **单指数衰减** — 跨 12 个数量级时间尺度普适 |
| **3** | EEG 混沌动力学（neuro-x1-033）D2 ≈ 5-8 | 心率混沌 / 湍流间歇（已有 ~30 条） | **低维混沌 + Lyapunov > 0** |
| **4** | gamma 振荡（neuro-x1-022）40 Hz I-I 反馈 | Mackey-Glass / 经济周期 / 化学振荡（已有） | **延迟微分方程振荡 f ≈ 1/4τ** |
| **5** | Ebbinghaus 遗忘曲线（neuro-x1-063）R = e^(-t/τ) | 商品促销热度衰减 / 病毒传播尾部（已有） | **记忆/兴趣指数衰减** |
| **6** | 麻醉意识相变（neuro-x1-041）一阶跳变 | 水冰相变 / 失业率突然跳升 / 银行挤兑（已有） | **双稳态 + saddle-node 跳变** |
| **7** | spreading depression（neuro-x1-013）2-6 mm/min 行波 | 化学钙波 / 森林火灾前沿 / 谣言传播（已有） | **反应扩散行波 c ≈ √(Dτ)** |
| **8** | 学习幂律 T = a·N^(-b)（neuro-x1-062）b ≈ 0.2-0.5 | 经验曲线 / 制造业产能曲线（已有） | **practice 幂律 / 经验曲线** |
| **9** | 帕金森静止性震颤 4-6 Hz（neuro-x1-071）STN 反馈 | 桥梁颤振 / 飞机 PIO 振荡（已有工程类） | **闭环时滞反馈失稳** |
| **10** | α-synuclein 朊样级联（neuro-x1-055）Braak 6 阶段 | 谣言 SIR / 朊病毒 / 文化漂变（部分已有） | **模板诱导级联扩散** |

> 这 10 对里 **2 / 5 / 6 / 7 / 8** 是用户日常搜索高频路径（"大脑 ↔ 市场"、"记忆 ↔ 兴趣"、"麻醉 ↔ 相变"），此前 neuroscience 侧的召回率 ≈ 0。

---

## 3. 数据来源汇总

| 来源类别 | 引用次数 | 代表期刊 / 工具 |
|---|---|---|
| Nature Neurosci / Neuron / Nat Rev Neurosci | ~28 | Cardin 2009 / Sabatini 2002 / Saper 2010 / Muller 2018 |
| J Neurosci / J Physiol | ~14 | Beggs & Plenz 2003 / Dittman 2000 / Bliss & Lomo 1973 |
| PNAS / Science / Lancet | ~12 | Tononi 2008 / Smith 1991 / Hadjikhani 2001 |
| 经典专著 / 教科书 | ~10 | Koch Biophysics 1999 / Buzsáki Rhythms / Izhikevich 2007 |
| 临床 / 流行病学 | ~9 | Bateman 2012 NEJM / Mashour 2014 Anesthesiology / Jack 2010 Lancet Neurol |
| 心理物理学经典 | ~7 | Ebbinghaus 1885 / Miller 1956 / Stevens 1957 / Fitts 1954 / Weber-Fechner |

→ 数据集层面引用：OpenNeuro（隐式，通过 Muller 2018 / Iasemidis 2003 LFP 实测）、Allen Brain Atlas（皮层方向柱）、Neuroelectro（突触常数）、ModelDB（HR / Morris-Lecar 模型参数）。

---

## 4. 后续运维 checklist

- [ ] **合并到主 KB（待用户确认 commit 边界）**：`cat data/kb-additions-2026-05-24-neuroscience.jsonl >> data/kb-expanded.jsonl`，或在 SearchService 加载层 chain-load
- [ ] **运行 embedding 增量脚本**：`PYTHONPATH=. .venv/bin/python scripts/update_kb_embeddings_neuroscience.py`（生成 .bak 后追加到 `web/data/kb_embeddings.npy`）
- [ ] **运行 sanity test**：`pytest web/backend/tests/test_kb_neuroscience_coverage.py -v`（不依赖真实模型，使用 BM25 + 关键词 fallback 验证 5 个查询）
- [ ] **回归全套测试**：`pytest web/backend/tests -m "not slow and not requires_internet and not requires_llm"`（781 个测试不应受影响）

---

## 5. 一句话总结

> X1 报告指出 neuroscience × 6 个核心 type_id 全 = 0；本轮 80 条按 X1 spec 全覆盖，每条含真实学术引用 + 定量观察，使 neuroscience cell 从 53 → 133 条（+150%），重点对子 "大脑 ↔ 市场 / 工程 / 记忆 ↔ 兴趣 / 麻醉 ↔ 相变" 现可双侧召回。质量优先：平均描述 171 字，所有引用可核查，无 ID/name 冲突，最严的"50 字 + 定量"门槛 100% 通过。

— end —
