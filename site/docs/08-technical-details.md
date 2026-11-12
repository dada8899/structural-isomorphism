# 技术细节

## 模型架构

### 基座模型：text2vec-base-chinese

| 属性 | 值 |
|------|-----|
| 架构 | BERT-base (Transformer Encoder) |
| 层数 | 12 |
| 隐藏维度 | 768 |
| 注意力头数 | 12 |
| 参数量 | ~110M |
| 最大序列长度 | 512 tokens |
| 词表大小 | 21,128 |
| 输出 | 768 维句向量 |

### 为什么选这个模型

1. **中文优化**：在中文语义相似度任务上表现优秀，我们的数据是中文的
2. **体积适中**：110M 参数可以在单张消费级 GPU 上训练，不需要多卡
3. **句向量质量**：预训练阶段已经用对比学习优化过句向量表示，在此基础上微调更高效
4. **生态完善**：基于 sentence-transformers 框架，训练和推理代码都很成熟

### 不选大模型的原因

用 GPT-4 或 Claude 做 embedding 虽然可能效果更好，但：
- 每次推理都需要 API 调用，V2 阶段要算 124,750 对相似度，成本太高
- 无法本地部署，受网络和 API 限制
- 768 维向量已经足够捕捉结构信息，不需要更高维度

## 训练方法

### 对比学习框架

使用 sentence-transformers 库的 MultipleNegativesRankingLoss (MNRL)。

**MNRL 的工作原理**：

```
Batch = [(a₁, p₁), (a₂, p₂), ..., (aₙ, pₙ)]

其中 aᵢ 是 anchor（一个科学现象描述）
pᵢ 是 positive（同一数学结构的另一个描述）

对于每个 aᵢ，batch 中所有其他 pⱼ (j≠i) 自动成为负样本

损失 = -log(exp(sim(aᵢ, pᵢ)/τ) / Σⱼ exp(sim(aᵢ, pⱼ)/τ))
```

**优势**：
- 不需要手动构造负样本，batch 内自动生成
- batch 越大，负样本越多，训练信号越丰富
- 梯度效率高

### 训练配置

```python
from sentence_transformers import (
    SentenceTransformer,
    InputExample,
    losses,
    evaluation,
)
from torch.utils.data import DataLoader

# Model
model = SentenceTransformer('shibing624/text2vec-base-chinese')

# Data
train_examples = [
    InputExample(texts=[desc_a, desc_b])  # same type_id
    for desc_a, desc_b in positive_pairs
]
train_dataloader = DataLoader(
    train_examples, shuffle=True, batch_size=64
)

# Loss
train_loss = losses.MultipleNegativesRankingLoss(model)

# Training
model.fit(
    train_objectives=[(train_dataloader, train_loss)],
    epochs=10,
    warmup_steps=100,
    evaluation_steps=500,
    output_path='./checkpoints/structural-iso-v1',
    show_progress_bar=True,
)
```

### 超参数选择依据

| 参数 | 值 | 理由 |
|------|-----|------|
| batch_size | 64 | MNRL 需要较大 batch 提供足够负样本；受限于 GPU 显存 |
| learning_rate | 2e-5 | BERT 微调的标准学习率 |
| epochs | 10 | 数据量不大（1214条），需要多轮训练；通过 early stopping 防止过拟合 |
| warmup_steps | 100 | ~2% 的总步数，标准做法 |
| temperature | 0.05 | MNRL 默认值，控制 softmax 的锐度 |

### 数据拆分

```
总数据：1214 条
├── 训练集：80% = 971 条
├── 验证集：10% = 122 条
└── 测试集：10% = 121 条

拆分策略：按 type_id 分层抽样，确保每种结构在三个集合中都有表示
```

## 数据格式详解

### JSONL 文件结构

```
data/
├── taxonomy.json          # 84种数学结构的定义
├── train.jsonl            # 训练集
├── val.jsonl              # 验证集
├── test.jsonl             # 测试集
└── raw/
    └── generated.jsonl    # 原始生成数据（1260条）
```

### taxonomy.json 示例

```json
{
  "structures": [
    {
      "id": 1,
      "name": "exponential_growth",
      "category": "指数与对数",
      "description": "数量按固定百分比持续增长，增长速度与当前数量成正比",
      "formula": "N(t) = N₀ × e^(rt)",
      "domains_hint": ["人口增长", "复利", "病毒传播", "摩尔定律"]
    },
    {
      "id": 2,
      "name": "exponential_decay",
      "category": "指数与对数",
      "description": "数量按固定比例持续减少，减少速度与当前数量成正比",
      "formula": "N(t) = N₀ × e^(-λt)",
      "domains_hint": ["放射性衰变", "药物代谢", "记忆遗忘", "品牌衰退"]
    }
  ]
}
```

### 训练数据示例

```jsonl
{"type_id": 2, "type_name": "exponential_decay", "domain": "nuclear_physics", "description": "放射性同位素的原子核以恒定的概率发生衰变..."}
{"type_id": 2, "type_name": "exponential_decay", "domain": "pharmacology", "description": "口服药物进入血液循环后，血药浓度随时间呈指数下降..."}
{"type_id": 2, "type_name": "exponential_decay", "domain": "psychology", "description": "新学习的知识如果不复习，遗忘速度先快后慢..."}
{"type_id": 15, "type_name": "negative_feedback", "domain": "ecology", "description": "捕食者-猎物系统中，捕食者增多导致猎物减少..."}
```

## 代码仓库结构

```
structural-isomorphism/
├── data/
│   ├── taxonomy.json
│   ├── train.jsonl
│   ├── val.jsonl
│   └── test.jsonl
├── scripts/
│   ├── generate_data.py       # 用 LLM 生成训练数据
│   ├── quality_check.py       # 数据质量检查
│   ├── prepare_pairs.py       # 构造正样本对
│   ├── train_contrastive.py   # 对比学习训练
│   ├── evaluate.py            # 评估指标计算
│   └── predict.py             # 推理脚本
├── models/                    # 保存的 checkpoint
├── checkpoints/               # 训练中间状态
├── site/                      # 项目网站（本站）
│   ├── index.html
│   ├── read.html
│   └── docs/                  # Markdown 文档
└── taxonomy-v1.md             # 分类体系文档
```

## 评估方法

### 1. Silhouette Score

衡量聚类质量：同一类样本之间的距离应该小，不同类样本之间的距离应该大。

```python
from sklearn.metrics import silhouette_score

# Encode all test samples
embeddings = model.encode(test_descriptions)

# Calculate silhouette score using type_id as labels
score = silhouette_score(embeddings, test_type_ids)
# Target: > 0.3
```

### 2. Retrieval@K

对于每个测试样本，在所有其他测试样本中找最近的 K 个，看有多少属于同一 type_id。

```python
def retrieval_at_k(embeddings, type_ids, k=5):
    from sklearn.metrics.pairwise import cosine_similarity
    sim_matrix = cosine_similarity(embeddings)
    np.fill_diagonal(sim_matrix, -1)  # exclude self

    hits = 0
    total = 0
    for i in range(len(embeddings)):
        top_k_indices = np.argsort(sim_matrix[i])[-k:]
        for j in top_k_indices:
            if type_ids[j] == type_ids[i]:
                hits += 1
        total += k

    return hits / total
# Target: > 0.6
```

### 3. 基线对比

用未微调的原始 text2vec-base-chinese 跑同样的评估，作为基线。微调模型的 Silhouette Score 和 Retrieval@K 应该显著高于基线。

### 4. 定性评估

准备 10 个测试查询，人工评估返回结果的质量：

```
查询：捕食者-猎物的周期性波动
期望：返回经济存货周期、化学振荡等跨域结果
评估：是否跨域？结构是否真的相似？是否有实用价值？
```

## V2 管道过滤逻辑详解

### 向量过滤层

```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# V1 model: structural similarity
struct_embeddings = v1_model.encode(phenomena_descriptions)
struct_sim = cosine_similarity(struct_embeddings)

# General model: semantic distance
general_embeddings = general_model.encode(phenomena_descriptions)
semantic_sim = cosine_similarity(general_embeddings)

# Filter: high structural similarity AND low semantic similarity
candidates = []
for i in range(n):
    for j in range(i+1, n):
        if struct_sim[i][j] > 0.7 and semantic_sim[i][j] < 0.5:
            candidates.append((i, j, struct_sim[i][j], semantic_sim[i][j]))
```

**双模型过滤逻辑**：
- V1 模型（微调后）：评估**结构相似度**——高分意味着底层结构可能相同
- 通用 embedding 模型（未微调）：评估**语义距离**——低分意味着表面上看起来不相关
- 同时满足"结构近 + 语义远"的对才是有趣的候选

### 已知关联过滤

```python
def filter_known_analogies(candidates, knowledge_base):
    filtered = []
    for i, j, s_sim, sem_sim in candidates:
        known_a = set(knowledge_base[i].get('known_analogies', []))
        known_b = set(knowledge_base[j].get('known_analogies', []))
        name_a = knowledge_base[i]['name']
        name_b = knowledge_base[j]['name']

        # Skip if either lists the other as known analogy
        if name_b in known_a or name_a in known_b:
            continue

        # Skip if in same domain
        if knowledge_base[i]['domain'] == knowledge_base[j]['domain']:
            continue

        filtered.append((i, j, s_sim, sem_sim))
    return filtered
```

### LLM 评估 prompt

```
你是一个跨领域结构分析专家。请分析以下两个科学现象是否存在
深层结构同构（不是表面相似，而是底层运作机制的相似）。

现象 A：{name_a}
描述：{desc_a}
领域：{domain_a}

现象 B：{name_b}
描述：{desc_b}
领域：{domain_b}

请从以下五个维度评估（每个维度 1-5 分）：
1. 输入相似度：两个系统接收的"输入"在抽象层面是否相似
2. 转化规则相似度：两个系统的处理/变化机制是否相似
3. 输出相似度：两个系统产生的"输出"在抽象层面是否相似
4. 约束条件相似度：两个系统受到的限制是否相似
5. 趋势方向相似度：两个系统的演化趋势是否相似

然后回答：
- 综合评分（加权平均，转化规则权重 40%，其余各 15%）
- 这个同构是否已经被广泛认知？（已知/部分已知/未知）
- 如果存在有意义的同构，它可能产生什么新的洞察？（1-2句话）
- 是否存在阻断机制？（六种中的哪种）

输出 JSON 格式。
```

### 阻断机制检测

```python
BLOCKING_CHECKS = {
    'shallow': '转化规则评分 < 3 但总分 > 3',
    'saturated': '目标领域已有更成熟的解法',
    'untranslatable': '核心概念标记为"无对应物"',
    'convergent': '两者都已成熟且独立发展',
    'metaphor_trap': '只有隐喻价值无可检验预测',
    'attention_blind': '无阻断因素且确实未知',
}
```

## 部署架构（V1 CLI）

V1 阶段的部署非常简单：

```
用户终端 → Python CLI → 本地模型推理 → 打印结果

不需要服务器、不需要 API、不需要数据库
所有计算在本地完成
```

V2 阶段可能需要 API 调用（LLM 初筛），但核心向量计算仍然在本地。

---

*技术细节文档 | 最后更新：2026-04-11*
