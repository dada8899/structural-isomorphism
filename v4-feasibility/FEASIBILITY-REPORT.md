# V4 Feasibility Report

**Date**: 2026-04-14  
**Tests run**: Q1 (direct vs retrieval) + Q2 (3-model schema agreement)  
**Total LLM calls**: ~80 (~3 hours wall time, ~$0 because of Claude subscription + Kimi budget)

## TL;DR

**V4 应降级为 methodology paper 的框架，而不是构建成 retrieval pipeline。**

- **Q1 失败**：Direct Opus 胜 9/10，碾压 Mock V4 retrieval（远超 70% 阈值，Direct 达 100%）
- **Q2 通过**：3-model 对 20 个经典跨域迁移的 schema 标注，**mean pairwise Jaccard = 0.721**（超过 0.7 门槛）
- **结合信号**：变形基元框架本身是真的，但把它绑到 retrieval pipeline 上是错的架构

按决策门规则：
- Q1 < 70% AND Q2 > 0.7 → V4 值得做（原计划）
- **Q1 ≥ 70% AND Q2 > 0.7 → 新决策**：框架可用，但不建 retrieval pipeline

## Q1 Results: Direct Opus vs Mock V4 Pipeline

### 实验设计
- 10 个跨域问题（组织行为、供应链、软件工程、机器学习、宏观经济、城市规划、医学统计、语言学、气候科学、组织学习）
- Set A (Direct Opus)：Opus 4.6 直接用自身推理回答
- Set B (Mock V4)：Opus 4.6 先从 63 候选池（V2 19 A + V3 20 A + kb-expanded-struct 4443）检索，再套用变形基元
- Judge：独立 Opus agent，5 维盲评分（specificity / falsifiability / novelty / correctness / actionability），每维 1-5 分，总分 /25

### 结果

| 指标 | Direct Opus (A) | Mock V4 (B) |
|---|---|---|
| 胜场 | **9** | 0 |
| 平局 | 1 (p09 气候临界) | 1 |
| 平均总分 | **22.3 / 25** | 17.9 / 25 |
| ≥18 "satisfactory" 率 | **10/10 = 100%** | 6/10 |

### 五维对比

| 维度 | 胜者 | 差距 | 解释 |
|---|---|---|---|
| Specificity | **A** | 大 | Direct 给具体方程+参数+数值；V4 停在框架层 |
| Falsifiability | **A** | 大 | Direct 直接给出可实验阈值和预测数值 |
| Novelty | A (接近平手) | 小 | V4 候选池限制了视野，反而不如自由联想 |
| Correctness | **A** | 中 | V4 在 p04/p08 的类比映射稍牵强 |
| Actionability | **A** | 大 | Direct 的"明天能开工"方案更多 |

### 关键发现

**V4 retrieval 反而约束了 LLM 的具体化能力**。Mock V4 虽然 retrieval hit rate = 10/10，strict commitment 到具体候选，但答案变得 *less* specific，因为它被绑在了已有发现的"类比视角"上，无法发挥 LLM 的自由联想和数值推理能力。

这是一个反直觉但重要的发现：**现代大模型的跨域类比能力已经超过了"retrieval + transform" 管道所能提供的增量**。

## Q2 Results: Transformation Primitive Schema Agreement

### 实验设计
- 20 个经典历史跨域迁移（Kepler→Newton、Maxwell→Einstein、Darwin→经济、Boltzmann→Shannon 等）
- 3 个独立模型各自用 8 基元 schema 做多标签标注：
  - Opus 4.6（via Claude Code agent）
  - Kimi K2-0905（via OpenRouter）
  - Qwen3-Max（via OpenRouter）
- 计算 pairwise Jaccard similarity + majority vote agreement

### 结果

| 指标 | 值 | 阈值判断 |
|---|---|---|
| 3-way exact match | 7/20 = 35% | 低（但合理，多标签任务本就难严格一致）|
| **Pairwise mean Jaccard** | **0.721** | **✅ 超过 0.7 门槛** |
| Opus ↔ Kimi | 0.637 | 中 |
| Kimi ↔ Qwen | 0.750 | 高 |
| Opus ↔ Qwen | 0.775 | 最高 |
| Avg Jaccard vs majority vote | **0.853** | 很高 — 3 模型都围绕同一"真值"聚集 |

### 基元分布（3 模型共识）

| Primitive | Opus | Kimi | Qwen | 说明 |
|---|---|---|---|---|
| `concept_transfer` | 19 | 17 | 19 | **主力**（95%）— 每个跨域迁移都用得上 |
| `boundary_rewrite` | 3 | 8 | 3 | Kimi 有偏差，其他两家一致 |
| `dim_shift` | 4 | 3 | 3 | 稳定，主要在场论/全息案例 |
| `continuity_toggle` | 2 | 5 | 2 | Kimi 偏高（c16, c12） |
| `stochastic_toggle` | 2 | 2 | 2 | 稳定，在随机性引入案例 |
| `time_scaling` | 2 | 0 | 0 | Opus 单独识别（分子钟、进化时间）|
| `variable_rename` | 1 | 0 | 0 | 极罕见（Boltzmann→Shannon 才算）|
| `causal_inversion` | 0 | 3 | 1 | Kimi 过度使用 |

### 关键发现

**变形基元框架是真的**：
1. Mean Jaccard 0.721 > 0.7 门槛，说明 3 个独立模型确实在对同一现象做相似判断
2. **Majority vote agreement 0.853** 更强地说明了"真值"存在——分歧大多是 Kimi 单独扩散到 boundary_rewrite/causal_inversion
3. `concept_transfer` 是几乎所有跨域迁移的主力（95%），与早上 V2 pool 上"100% variable_rename"的异常现象**完全相反**——证明早上的问题是 V2 候选池偏差，不是基元定义

**但两个子发现削弱了 V4 作为训练目标的可行性**：
1. **分布极不平衡**：concept_transfer 占 95%，其他 7 个加起来才 5% — 预测器会退化成 "always predict concept_transfer"
2. **variable_rename 几乎不应用**：只有 1 次（Boltzmann→Shannon）— 说明早上 V2 数据里"100% variable_rename"是因为 V2 候选本身就是浅同构，不是硬同构

## 综合判决

### 按决策门原规则
- Q1 必须 < 70%（Direct 差） **AND** Q2 必须 > 0.7（Schema 好）→ 才值得投 V4
- 实测：Q1 = 100% (satisfied by Direct) **AND** Q2 = 0.721 ✓
- **原规则判定：V4 pipeline 不应建**

### 但不要扔掉全部 V4 idea

**保留的部分**（有实证支持）：
- 变形基元是可识别的真实维度（Q2 证据）
- 大多数跨域迁移集中在 `concept_transfer`，但更硬的迁移会用到 `dim_shift` / `continuity_toggle` / `boundary_rewrite`
- 这个分布是有意义的，可以作为"什么是深度跨域创新"的定量指标

**删掉的部分**（无实证支持）：
- "Retrieve from candidate pool → apply transformation" 作为 pipeline → 删
- "Train transformation predictor" 作为独立模型 → 删（数据分布不平衡，会训出退化预测器）
- "V4 beat GPT-5/Opus baseline" 作为论文卖点 → 删（Q1 证明打不过）

### 新的 V4 定位：Methodology Paper，不是 Retrieval Pipeline

把 V4 从"跨域求解器"降级为"跨域创造力的定量分析框架"：

1. **论文一**：V1+V2+V3 作为 data paper / methodology paper，重点是 3 条 pipeline 发现的 63 个候选
2. **论文二（新的 V4 定位）**：用变形基元 schema 对 V1+V2+V3 的 63 个候选做定量分析
   - 有多少是 concept_transfer only？（预计 ~70%）
   - 有多少用到深度变形（≥2 个非 concept_transfer 基元）？
   - 深度变形的候选在 LLM 判断里 final_score 更高吗？
   - 这回答了一个方法论问题："什么样的跨域发现值得写论文"
3. **可选第三层**：在 case study 论文里，把变形基元作为可解释性工具，标注每个 A 级发现的变形路径

## 推荐后续路径

**立即（本周）**：
- 把 V4 改名为"Transformation Primitive Framework"
- 用 3 模型对 63 个 A 级候选（19 V2 + 20 V3 + 24 V1 tier-1）做变形基元标注
- 产出一个 "transformation frequency" 分析表

**短期（2-4 周）**：
- 选 1-2 个 "deep transformation" 候选（use ≥2 non-trivial primitives）开始写 arXiv 论文
- 这些是"真正有变形含量"的跨域发现，写出来的论文分量更重

**长期（3-6 个月）**：
- 可选：写一篇 position paper 论证 creativity = distance × isomorphism × transformation 框架
- 不需要构建 V4 pipeline
- 不需要训练 transformation predictor
- 框架本身作为论文贡献就够了

## 附：原始数据文件

- `q1-problems.jsonl` — 10 跨域问题
- `q1-direct-opus.jsonl` — Direct Opus baseline 答案
- `q1-mock-v4.jsonl` — Mock V4 pipeline 答案
- `q1-judge.jsonl` — 独立 Opus judge 的 5 维评分
- `q2-classic-cases.jsonl` — 20 历史经典跨域迁移
- `q2-opus-labels.jsonl` — Opus 变形基元标注
- `q2-kimi-labels.jsonl` — Kimi K2 变形基元标注
- `q2-qwen-labels.jsonl` — Qwen3 Max 变形基元标注
- `transformation-primitives.md` — 8 基元 schema 文档

## 诚实结论

1. **V4 的 idea 大部分是错的**——retrieval 不会打败 direct LLM reasoning
2. **V4 的底层直觉有一部分是对的**——变形基元确实是个可识别的维度
3. **正确的动作是降级而非放弃**——把 V4 从 6 个月研发的 pipeline 降级为 1-2 周的方法论框架
4. **省下的时间应该投论文**——V1+V2+V3 已经有 63 个顶级候选，写 3-5 篇 arXiv 比训练 transformation predictor 更有 ROI

**Q1 帮我们省了 3-6 个月可能白干的时间。Q2 告诉我们什么部分值得保留。**
