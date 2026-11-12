# V3 Phase 0 验证报告

**日期**：2026-04-13  
**样本**：50 个随机现象（seed=42）自 4443 现象扩展 KB  
**模型**：Kimi K2.5（`moonshotai/kimi-k2-0905`）vs Opus 4（`anthropic/claude-opus-4`）

## 核心发现

### ✅ 可行性：StructTuple 抽取管道跑通

- Kimi 和 Opus 都能按 schema 输出 **零格式错误**
- 每样本耗时 Kimi ~7s / Opus ~10s
- 50 样本全量跑完 Kimi ~6 分钟 / Opus ~8 分钟

### ⚠️ 重大发现：40% 的现象**不是动力学系统**

| 指标 | Kimi | Opus |
|---|---|---|
| `dynamics_family != Unknown` | 30/50 = **60%** | 32/50 = **64%** |
| 抽取平均置信度 | 0.71 | 0.75 |
| `dynamics_family` 一致率 | — | 64% (K vs O) |

**Unknown 原因分析**（来自 LLM 的 notes 字段）：
1. **静态优化/权衡**：如"涡扇旁通比"、"密封间隙泄漏流"——这些是设计空间里的 tradeoff，没有时间演化
2. **离散阶段序列**：如"通过仪式三阶段"、"焙烤褐变三阶段"——多阶段但不是连续微分方程
3. **静态相关性**：如"购物推车膨胀"、"具身认知效应"——因果关系但无动力学
4. **结构特征**：如"核磁矩"、"核纤层"、"金属-载体相互作用"——静态结构描述
5. **诊断标志物**：如"ctDNA 片段化特征"——状态分类而非动力学

**结论**：KB 包含两类不同的"现象"——
- **动力学系统**（~60%）：有状态变量、时间演化、方程骨架（V3 适用）
- **静态结构模式**（~40%）：有结构但没时间动力学（V3 不适用）

### ✅ 好消息：60% 动力学子集的交叉匹配质量很高

Opus 在 32 个可匹配现象中找到 **31 个共享 dynamics_family 的配对**，其中 **30 个跨域**。手工检查部分样例：

- `DDE_delayed_feedback`: 供应链牛鞭效应 × 文学经典的延迟认可 × 干旱持续效应 ✅ 真跨域延迟反馈
- `Bistable_switch`: 胰岛素信号通路 × 丘脑皮层意识状态 ✅ 真跨域双稳态
- `Network_cascade`: DeFi 清算级联 × 新兴市场传染 ✅ 真跨域级联
- `PDE_diffusion`: 光催化载流子 × 壤中流侧向传输 ✅ 真扩散 PDE
- `ODE2_undamped_oscillation`: 放热反应温度 × 债务-通缩螺旋 ✅ **新发现！**未被 V1/V2 捕捉到的潜在同构

### ⚠️ 警示：Kimi vs Opus 一致率仅 64%

18 个样本在 `dynamics_family` 上两模型分歧。分歧类型：
- **模糊边界**（~10 个）：`Stochastic_process` vs `Game_theoretic_equilibrium` 等，本身就有歧义
- **Opus 更精细**（~5 个）：`Hysteresis_loop` / `ODE2_damped_oscillation` / `Phase_transition_2nd` 这些细分类 Kimi 容易退化到 `ODE1_saturating`
- **Kimi 误判**（~3 个）：如 NMR 信号 Kimi 给 `ODE1_exponential_decay`，Opus 给 `ODE2_damped_oscillation`（Opus 对）

**判断**：质量差距存在但不是 2x。Kimi 适合批量首轮抽取 + Opus 抽查 10% 修正关键错误。

## 成本估算（修正版）

| 模型 | 4443 现象 | 成本 | 耗时 |
|---|---|---|---|
| Kimi（主力） | 4443 × ~600 tokens | ~$5 | ~10 小时（串行）/ ~1 小时（8 并发）|
| Opus（抽查 10%）| 444 × ~800 tokens | ~$8 | ~1 小时 |
| **总计** | | **~$13** | **~2 小时（并行）** |

## Schema 需要调整的地方

1. **加 `is_dynamical` 前置判断**：先让 LLM 判断是否是动力学现象，不是就不做后续字段抽取
2. **扩展 `dynamics_family` 枚举**（+3 项）：
   - `Hysteresis_loop` 和 `Phase_transition_2nd` 需要更明确的判断指引
   - 加 `Static_optimization_tradeoff`（涡扇旁通比型）作为非动力学的回收筐
3. **加平行结构维度**（可选）：为 40% 静态现象加 `structural_pattern` 字段，enum: static_tradeoff / multi_stage_sequence / static_correlation / threshold_classification / stability_condition

## 决策点：Phase 0 → Phase 1 走哪条路

### 方案 A：窄口径 V3（推荐）⭐
- 只对 60% 动力学子集做 StructTuple 匹配
- 4443 现象 → ~2700 可匹配
- 预期产出：匹配对数 ~2700² / 30 家族 ≈ 20 万 pair → LLM rerank 后 top-200
- 工作量：Phase 1-5 按原计划走，只是基数缩到 60%
- 优点：pipeline 简单、schema 稳定、能快速验证 V3 是否比 V2 好
- 缺点：40% KB 被漏掉

### 方案 B：宽口径 V3（并行结构+动力学）
- 加 `structural_pattern` 平行轴，两个维度都做匹配
- 4443 现象全部覆盖
- 优点：完整
- 缺点：schema 复杂度翻倍，Phase 1 再调 3-5 天，总时间 +1 周

### 方案 C：V3 暂停
- Phase 0 已证明 60% 动力学子集有希望
- 但没有证明"V3 一定比 V2 好"
- 可以把资源转去写论文，V3 后续再说

## 推荐路径

**方案 A + 小样本对比验证**：

1. Schema 微调（加 `is_dynamical` 判断，1 天）
2. 先在 **现有 50 个 Opus 样本上**跑结构化匹配器，看能否召回 V2 找到的同构
3. 看匹配器效果：如果 60% 动力学子集的 V3 匹配明显优于 V2 embedding（命中率至少 1.5×），走 Phase 1 全量
4. 如果不明显，回到写论文

**关键判断点**：Phase 0.5 的对比实验——在 50 样本规模上验证 V3 > V2，再决定是否投入 18 天全量跑。

## 下一步

等用户决定：
- [ ] 方案 A：走窄口径，先做 Phase 0.5 小样本对比
- [ ] 方案 B：走宽口径，扩展 schema
- [ ] 方案 C：暂停 V3，回去写论文

## 产出文件

- `v3/sample-kimi-50.jsonl` — Kimi 抽取结果
- `v3/sample-opus-50.jsonl` — Opus 抽取结果
- `v3/struct_tuple_schema.md` — schema v0.1
- `v3/extract_prompt.txt` — LLM extractor prompt
- `v3/extract_structtuple.py` — extractor script
