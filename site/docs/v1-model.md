---
title: 模型训练
description: V1 embedding模型的训练配置、方法和进度
---

# V1 模型训练

## 基座模型

| 参数 | 值 |
|------|-----|
| 模型名称 | shibing624/text2vec-base-chinese |
| 参数量 | 110M |
| 架构 | BERT-base |
| 最大序列长度 | 128 tokens |
| 输出维度 | 768 |
| 预训练任务 | 中文语义相似度 |

选择理由：
1. 中文表现好（训练数据以中文为主）
2. 参数量适中（可在 MPS/CPU 上训练）
3. 已经对语义相似度做过预训练（不需要从头学"什么是相似"）
4. 社区活跃，有成熟的 sentence-transformers 支持

## 训练方法

### 对比学习（Contrastive Learning）

使用 `MultipleNegativesRankingLoss`：

```python
from sentence_transformers import SentenceTransformer, losses

model = SentenceTransformer("shibing624/text2vec-base-chinese")
loss = losses.MultipleNegativesRankingLoss(model)
```

**核心思想**：
- 正例对：同一结构类型的不同领域描述 → 拉近
- 负例对：不同结构类型的描述（batch 内自动构建）→ 推远
- 训练目标：让模型学会"结构相同 = 向量接近"，不管领域和措辞有多不同

### 训练配置

```python
EPOCHS = 10
BATCH_SIZE = 16      # MPS 内存限制
SEED = 42
BASE_MODEL = "shibing624/text2vec-base-chinese"
```

### 训练数据加载

```python
# Build positive pairs from same-type descriptions
for type_id, descriptions in type_descriptions.items():
    for i in range(len(descriptions)):
        for j in range(i + 1, len(descriptions)):
            pairs.append({
                "sentence1": descriptions[i],
                "sentence2": descriptions[j],
                "label": 1.0,
            })
```

84种类型 × 平均14.5条描述 → 约 8000+ 正例对

## 训练环境

| 参数 | 值 |
|------|-----|
| 硬件 | MacBook Pro (Apple Silicon) |
| 加速器 | MPS |
| 训练框架 | sentence-transformers |
| Python | 3.11 |
| PyTorch | 2.x |

## 训练进度

- [x] 数据准备（1214条，4轮审计）
- [x] 基座模型选择
- [x] 训练脚本编写（`scripts/train.py`）
- [ ] 模型训练（进行中）
- [ ] 评估脚本运行
- [ ] 模型效果分析

## 预期效果

模型训练完成后，应该能够：

1. **同类聚集**：同一结构类型的描述在向量空间中聚集
2. **异类分离**：不同结构类型的描述被分开
3. **跨域匹配**：物理学的"指数衰减"描述和心理学的"遗忘曲线"描述距离很近
4. **抗干扰**：不会因为领域术语相似而误判（如"信息熵"和"热力学熵"虽然都有"熵"字，但结构确实相同）

## 模型输出路径

```
models/structural-v1/
```

训练完成后，此目录包含完整的 sentence-transformer 模型文件，可直接加载使用。
