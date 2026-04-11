---
title: 管道设计
description: V2异常探测器的完整管道架构——从知识库到发现报告
---

# V2 管道设计：异常探测器

## 整体架构

```
知识库(500个现象)
    ↓
[Step 1] Embedding 编码（V1模型）
    ↓
[Step 2] 全对相似度计算
    ↓
[Step 3] 过滤：同领域配对（移除）
    ↓
[Step 4] 过滤：同类型配对（移除）
    ↓
[Step 5] 过滤：已知类比（移除）
    ↓
[Step 6] LLM 筛选（可选）
    ↓
[Step 7] 排序 & 输出报告
```

## 各步骤详解

### Step 1: Embedding 编码

使用V1训练好的模型，将500个现象的描述编码为768维向量：

```python
model = SentenceTransformer("models/structural-v1")
descriptions = [item['description'] for item in kb]
embeddings = model.encode(descriptions, show_progress_bar=True)
```

### Step 2: 全对相似度

计算 500×500 的余弦相似度矩阵（实际只需上三角，124,750对）：

```python
sim_matrix = util.cos_sim(embeddings, embeddings).numpy()
```

只保留相似度 > 阈值（默认0.70）的配对。

### Step 3-4: 基础过滤

- **移除同领域**：如果两个现象属于同一领域（如都是物理学），移除。同领域的结构相似不算"跨域发现"。
- **移除同类型**：如果两个现象已被标注为同一结构类型，移除。已知的同构不算"发现"。

### Step 5: 已知类比过滤

维护一个"已知跨域类比"列表，移除已被广泛记录的结构映射：

```python
KNOWN_ANALOGIES = {
    frozenset(["自然选择", "市场竞争"]),
    frozenset(["热力学熵", "信息熵"]),
    frozenset(["传染病", "计算机病毒"]),
    frozenset(["免疫系统", "入侵检测"]),
    ...
}
```

这一步确保输出的是**未被发现的**跨域连接。

### Step 6: LLM 筛选（可选）

对剩余的候选配对，用 LLM 做进一步评估：
- 这个配对是否真的有结构同构（而非表面类似）？
- 这个同构有没有被忽略的阻断机制？
- 这个迁移有没有可操作的研究方向？

### Step 7: 输出报告

最终输出按相似度排序的发现报告：

```
## #1 | Similarity: 0.923

A: 布朗运动 (物理学)
  Structure type: 29-随机游走
  微小粒子悬浮在流体中...

B: 基因漂变 (遗传学)  
  Structure type: 不同
  小种群中等位基因频率的随机变化...

---
```

## 三类预期产出

### 1. 已知但不显然的连接
两个领域确实共享结构，学术界已有文献记录，但不是常识。
- 价值：整理和确认
- 预计占比：~40%

### 2. 可能的新连接
结构相似度高，但查找不到明确的学术文献将二者联系起来。
- 价值：值得深入调研
- 预计占比：~50%

### 3. 潜在发现
结构高度匹配，跨域距离大，且确认没有已知文献。
- 价值：可能是真正的新发现，值得写论文
- 预计占比：~10%

## 运行方式

```bash
python scripts/v2_pipeline.py --threshold 0.70 --top-n 50
```

参数说明：
- `--threshold`：相似度阈值（默认0.70）
- `--top-n`：输出前N个结果（默认50）

输出文件：
- `results/discoveries.md`：可读报告
- `results/discoveries.jsonl`：结构化数据
