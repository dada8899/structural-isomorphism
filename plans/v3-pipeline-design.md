# V3 Pipeline 设计草案

> 目标：突破 V2 (embedding) 的天花板——让"真正的数学同构"和"表面相似"在系统层面可区分。

## 1. 问题诊断：为什么 V2 碰到天花板

V2 成绩：4533 候选 → 94 五分（2.1% 密度）→ 19 A 级（深度分析后 20% 命中）

**embedding 本身的三个缺陷**：

1. **状态空间坍缩**：text2vec 把"两个变量非线性反馈到饱和"的 PDE 骨架和"两个关键词共现的文学隐喻"投影到相近区域。语义相似 ≠ 结构同构
2. **数学不变量不可见**：余弦相似无法区分"共享 $dx/dt = f(x) - g(x)y$"和"都含'反馈'二字"
3. **领域专业术语稀释**：训练语料中稀有的术语（如 Greitzer 方程、Preisach 算子）被降权，反而让表面泛化词（"阈值""反馈"）主导相似度

根本矛盾：embedding 是**统计关联**工具，而结构同构是**代数结构**问题。这一层不改，深度分析后命中率天花板约 20%。

## 2. 两个候选方向（择一或串联）

### 方向 A：结构化表征 — StructTuple（推荐）

每个现象由 LLM 抽取为结构化六元组：

```
StructTuple = (
    state_vars: List[str],         # 状态变量，如 ["温度T", "放热速率r"]
    dynamics: str,                  # 标准方程族：ODE1/ODE2/DDE/PDE/Markov/Percolation
    feedback_topology: str,         # 反馈拓扑：positive_loop / negative_loop / delayed_loop / bistable
    timescale: float,               # 特征时间（对数刻度，s）
    boundary_behavior: str,         # 边界行为：runaway / saturation / limit_cycle / bifurcation
    invariants: List[str]           # 守恒量 / 对称性 / 幂律指数
)
```

**匹配策略**：两个现象的 StructTuple 先做精确字段匹配（dynamics、feedback_topology、boundary_behavior），再对 state_vars/invariants 做语义子集检查。**字段级匹配无法被"共享关键词"欺骗**。

**架构**：
```
Phenomenon text
    │
    ├── LLM extractor (Kimi/Opus, 1-shot per phenomenon)
    │       ↓
    │   StructTuple (JSON)
    │       ↓
    │   Stored in KB alongside description
    │
    └── Query phenomenon → StructTuple → structured match across KB
                                     → top-K candidates
                                     → V2 embedding rerank (tiebreak)
                                     → deep analysis
```

**预期指标**：
- 在同样 94 pool 上深度分析命中率：20% → 预计 **35-45%**
- 跨域召回：不降（因为 StructTuple 是高层抽象，跨域 phenomena 更容易匹配到同一 dynamics 家族）
- LLM 抽取成本：4443 现象 × ~400 tokens in + 200 out ≈ 2.7M tokens total，用 Kimi K2.5 大约 $3-5

### 方向 B：LLM 交叉编码器 rerank（作为后置滤网）

V2 已给出 4533 对。用 Opus 做 **pairwise yes/no**：

```
Prompt: "给定两个现象描述，判断是否存在严格的数学同构（共享 PDE/ODE 或守恒律）。
返回 JSON {isomorphic: bool, shared_equation: str|null, confidence: float}"
```

**取样策略**：不在 4533 全量上跑（成本高），而是在 StructTuple 初筛后的 top-1000 上跑。

**预期效果**：
- 4533 → StructTuple 匹配 → 1000 → LLM rerank → 200 高置信对
- 在这 200 上做深度分析，命中率可预期 **50-60%**（因为 LLM 已经看过 pair，而不是只看单个现象）

## 3. 推荐架构：A + B 串联

```
4443 KB ── LLM extractor ──→ KB + StructTuple (one-time cost)
                                  │
Query phenomenon ─── StructTuple ─┘
                                  │
                                  ↓
                          Structured match
                          (字段级硬约束)
                                  │
                                  ↓
                          Top-1000 candidates
                                  │
                                  ↓
                          LLM pairwise rerank
                          (shared_equation check)
                                  │
                                  ↓
                          Top-200 high-confidence pairs
                                  │
                                  ↓
                          Deep analysis (5-dim rubric)
                                  │
                                  ↓
                          A-level candidates
```

## 4. 实施计划（2-3 周，Solo + Mac M4）

| Week | 任务 | 产出 |
|---|---|---|
| W1 D1-D2 | 设计 StructTuple schema；写 LLM extractor prompt；在 50 现象上测试 | prompt + 50 样本验证 |
| W1 D3-D5 | 批量抽取 4443 现象 StructTuple；处理错误/重试；人工抽查 100 个 | kb-expanded-struct.jsonl |
| W2 D1-D2 | 写结构化匹配器（字段硬约束 + embedding tiebreak） | match_structural.py |
| W2 D3-D5 | 在整个 KB 上跑一遍，产出 top-1000 对 | v3-structural-top1000.jsonl |
| W3 D1-D3 | LLM pairwise rerank（1000 对，每对 1 次 API call） | v3-rerank-top200.jsonl |
| W3 D4-D5 | 深度分析 + 对比 V2 效果 | v3-deep-analysis.jsonl + evaluation report |

## 5. 预期指标提升

| 指标 | V2 | V3 (预期) | 机制 |
|---|---|---|---|
| Top 200 A 级命中率 | ~10% (19/200 等比外推) | **30-40%** | 结构化 + LLM rerank 双重过滤 |
| 跨域召回不丢 | — | ≥V2 | StructTuple 是高层抽象，跨域天然友好 |
| 计算成本 | 0（已跑完）| $10-20 LLM API | 一次性预处理 + 选择性 rerank |
| 解释性 | 低（黑盒 embedding）| **高**（每对都有 shared_equation 字段）| 论文写作直接受益 |

## 6. 风险 + 回退

- **风险 1**：LLM 抽取 StructTuple 不稳定 → 同一现象多次抽取结果差异大  
  缓解：对 20% 样本做两次抽取对比，方差大的现象做投票取中位数
- **风险 2**：字段级匹配过严，召回塌陷  
  缓解：字段匹配保留"近似档"（如 ODE1 和 ODE2 算 70% 相似），而非硬 01
- **风险 3**：LLM rerank 成本超预算  
  缓解：限制在 top-1000 内；若 Kimi 便宜，先全量 rerank 确认上限

**回退方案**：若 V3 最终效果不显著，保留 V2 作为主管道，V3 方向 A 的 StructTuple 仍可作为论文"结构化发现"方法论的独立贡献。

## 7. 成功标准

- 在 4443 KB 上跑完完整 pipeline
- 深度分析后 A 级命中率 ≥ V2 的 1.5 倍（即 ≥30%）
- 至少 5 个新发现不在 V1 tier-1 或 V2 A 级中
- 产出可复现的结构化 KB（v4+ 可直接用）

---

*草案版本：2026-04-13*
*实施前需确认：(1) LLM 预算；(2) 是否与 V2 并行运行还是替代；(3) 首批 50 现象抽取结果人工验收*
