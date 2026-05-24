# 24 条 tier-1 发现真实性审计

> 启动日期：2026-04-13
> 状态：待执行
> 预算：~$15，一天跑完
> 依赖：无
> 阻塞：V3 Phase 2 及之后

## 目标

把 `results/exp-final-*/tier1.jsonl` 里的 24 条发现过三层漏斗，分类：

- (a) 已在文献中被明确提出的类比 → 排除
- (b) 表面相似但深层不同的假同构 → 排除
- (c) 真的新但无解释力 → 标"灵感"
- (d) 真的新且能产生新预测 → 写进论文

## 输入

`results/exp-final-*/tier1.jsonl`（24 条，每条含：现象 A、现象 B、结构签名、LLM 生成的同构描述）

---

## Layer 1：LLM 文献查重

**用 3 个异构模型独立判决**：
- `anthropic/claude-opus-4.1`
- `google/gemini-2.5-pro`（via OpenRouter）
- `moonshotai/kimi-k2.5`（via OpenRouter）

> 注：原计划用 GPT-5，但 OpenRouter 上 GPT-5 的 reasoning tokens 会吃掉 content 导致返回空，
> 已换成 Kimi K2.5 作为第 3 个异构源（中文旗舰，独立训练语料，差异视角足够）。

### Prompt 模板

```
你是一位跨学科研究专家，精通物理、生物、经济、信息论、社会学等领域的文献。

判断下面这个"跨域结构同构"是否已在学术文献中被明确提出过。

现象 A（来自 [领域]）：[描述]
现象 B（来自 [领域]）：[描述]
同构描述：[两者如何在结构上对应]

请做三件事：
1. 在你知识范围内，搜索是否有论文/著作/科普作品明确讨论过 A 和 B 的类比
2. 如果有，列出至少 2 个引用（作者 + 年份 + 核心论点）
3. 严格按以下 JSON 输出（不要任何 markdown 包裹）：

{
  "verdict": "KNOWN | WEAK_KNOWN | UNKNOWN | UNCERTAIN",
  "citations": ["..."],
  "reasoning": "..."
}

verdict 定义：
- KNOWN：明确被提出过，业内公认
- WEAK_KNOWN：有零星提及但未系统化
- UNKNOWN：在你知识范围内未见
- UNCERTAIN：记忆模糊，建议人工核查
```

### 通过规则

- ≥2 模型判 KNOWN → 排除
- 3 模型都判 UNKNOWN → 进 Layer 2
- 其它组合 → 进 Layer 2 但打 `flag_ambiguous`

### 输出

- `validation/layer1-results.jsonl`：每条发现 × 3 模型判决
- `validation/layer1-survivors.jsonl`：通过 Layer 1 的发现

**预算**：24 × 3 × ~5k tok ≈ $3

---

## Layer 2：多模型盲评

对 Layer 1 幸存者，用 5 个异构模型盲评：
- `anthropic/claude-opus-4.1`
- `google/gemini-2.5-pro`
- `moonshotai/kimi-k2.5`
- `deepseek/deepseek-r1`
- `z-ai/glm-5`

### 三问 Prompt

```
评审下面这个跨域结构同构。不要问这是谁提出的，只看内容本身。

现象 A：[描述]
现象 B：[描述]
同构描述：[描述]

回答三个问题，每题 1-5 分评分 + 理由：

Q1 深层 vs 表面：数学/机制层面的深层同构（5）还是仅因措辞相似（1）？
Q2 解释力：能帮理解 B 领域中原本难解的现象（5）还是只是"看着像"（1）？
Q3 预测力种子：能否基于此同构生成至少一个"B 领域尚未验证但可证伪"的预测（5）还是只能事后解释（1）？

严格 JSON：
{
  "Q1": {"score": 1-5, "reason": "..."},
  "Q2": {"score": 1-5, "reason": "..."},
  "Q3": {"score": 1-5, "reason": "..."},
  "overall_novelty": "真新 | 表面新 | 疑似已知"
}
```

### 通过规则

- 5 模型 Q1+Q2+Q3 均分 ≥12/15
- 且 ≥3 模型在 Q3 给出 ≥4
- → 进 Layer 3

### 输出

- `validation/layer2-scores.jsonl`
- `validation/layer2-survivors.jsonl`

**预算**：~15 × 5 × ~8k tok ≈ $6

---

## Layer 3：预测力测试 ★ 论文价值分水岭

对 Layer 2 幸存者（预计 5-10 个），用 Opus 生成候选预测，用户+Scholar 审核。

### 预测生成 Prompt

```
基于下面这个结构同构：
[同构描述]

A 领域已知 X：[描述]
请推理：B 领域应该存在结构对应的 Y（具体指出 Y 是什么）

要求：
- Y 必须是可观测/可实验的具体命题
- Y 必须"非平凡"——如果没有这个同构就不会被预测出来
- Y 必须可证伪——能说清楚怎样算证伪

给出 3 个候选 Y，按"新奇度 × 可证伪性"排序。严格 JSON 输出。
```

### 人工评审

对每个候选 Y，用户 + Scholar / arXiv 搜索：
- **已被验证** → 有预测力 ✅ 进论文 Discovery 案例
- **部分被验证** → 写进论文 Related Findings
- **未被验证** → 作为"开放预测"写进论文 Discussion

### 硬门槛

**如果 24 条发现导不出 ≥1 个"强预测"**（被验证或值得立项的），V3 定位必须从"求解引擎"降级为"灵感工具"。这个结论本身比任何发现都重要——它决定论文走学术路线还是科普路线。

### 输出

- `validation/layer3-predictions.md`：每个幸存发现 + 3 预测 + 人工评审结论
- `validation/tier1-final.md`：最终分类（已知/灵感/有预测力），作为论文 Discovery 章节原始素材

**预算**：~8 × Opus × ~20k tok ≈ $4

---

## 执行

### 交付代码
- `scripts/validate_tier1.py`（三层子命令独立运行：`--layer 1|2|3`）
- 复用现有 OpenRouter 客户端 + API key（见 `.env`）
- 失败重试 + token 统计 + 中间结果保存

### 执行顺序
1. Layer 1 先跑（~30 min）→ 用户看结果决定是否继续
2. Layer 2（~2 h）
3. Layer 3 生成候选预测（~1 h）→ **切人工评审**
4. 人工评审结果写回 `tier1-final.md`

### 对 V3 的反哺

Layer 2+3 产出的"真新"发现，作为 V3 变形预测器训练数据的"现代案例"补充（占比 ~10-20%），用来对冲科学史老案例的分布偏差。
