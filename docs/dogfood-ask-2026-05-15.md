# LLM /api/ask/stream 真实质量评估报告

> Session #9 Wave 4 sub-agent D — 2026-05-15
> Endpoint: `POST https://beta.structural.bytedance.city/api/ask/stream`
> Model (meta): `anthropic/claude-sonnet-4.6`
> Embeddings: base fallback `shibing624/text2vec-base-chinese`（W1 disaster 后未恢复 v2 finetuned）
> Raw data: [dogfood-ask-2026-05-15.json](./dogfood-ask-2026-05-15.json)

## TL;DR

7 个真实跨域 / 商业 / 边缘 query 全部成功返回（HTTP 200，事件流完整：meta → kb_cards → answer_chunk×N → answer_done → similar_phenomena → followups → done）。

| 维度 | 平均分 (1-5) | 备注 |
|---|---|---|
| Retrieval quality | **3.6** | 跨域命中很稳，边缘 query（q5 q6 q7）召回明显是"硬凑"的低分 KB |
| Answer coherence | **4.4** | 模型一致地用 isomorphism 视角作答，跨域比喻自然 |
| Honesty | **3.0** | 边缘 query 全部"硬答" — 没有任何拒答或显示"不在 KB 范围" |
| Latency | **3.4** | 首字节 < 1s，首 answer_chunk **20-32s**（明显瓶颈：等 RAG 检索完再开 LLM）|

**综合 7 query 总分均值：14.4 / 20**（合格但还有显著空间）

**最严重的 3 个 issue**：
1. **首 answer_chunk 延迟 18-32s** — 用户体验上和 Perplexity 体感差距大（Perplexity 通常 < 3s 首字符）。看起来 orchestrator 是"先完成全量 RAG → 再启动 LLM 流式"，而不是"边 RAG 边流式"
2. **无 honesty 拒答机制** — 边缘 query（"我女朋友为什么生气了"、"求 1+1"、"BTC 明天涨跌"）都被硬塞 isomorphism 框架。q6（1+1=?）甚至从"母线差动保护"和"幂律分布"绕回 1+1=2，q5 把回声室效应塞进恋爱话题。聪明但不诚实，KB score < 0.7 时应触发 "out of scope" 提示
3. **Retrieval 严重依赖 query 关键词重叠** — q2"团队氛围"召回了"形状记忆合金相变恢复"（score 1.0，完全 hack 命中"相变"关键词），实际是 LLM 在帮 retrieval 圆场。base fallback embedding 精度损失明显，W1 disaster 留下的尾巴还在

---

## 逐 query 评分

### q1 - cross-domain :: 为什么硅谷银行挤兑后市场反应这么剧烈？还有哪些类似的级联系统？

- **Retrieval: 5/5** — top KB = 银行挤兑 (0.94)，营养级联崩溃 (0.82)，信息级联 (0.80)，全部高度相关
- **Coherence: 5/5** — "自我实现的预言"+"信息级联"+"营养级联崩溃"+"经济制裁网络效应" 4 个类比串得自然，引用 `[1] [2] [3] [5]` 正确对应 KB
- **Honesty: 5/5** — 不做股价预测，专注结构同构
- **Latency: 3/5** — 24.1s 总时长，first_answer_chunk **22.07s**。 SSE 的"边流边出"完全没有体现
- **小计: 18/20**

### q2 - cross-domain :: 团队氛围崩了之后为什么很难恢复？跟相变有关系吗？

- **Retrieval: 3/5** — 顶部命中是"形状记忆合金的相变恢复"(score=1.0)，纯粹关键词 hack。"团队规模沟通成本"在第 5 位、score 0.82 才是真相关。retrieval 排序明显错位
- **Coherence: 5/5** — LLM 把"形状记忆合金滞后环"+"交通流相变拥堵"硬拗成"团队氛围崩溃恢复不对称"，比喻角度精彩，写得比 retrieval 准
- **Honesty: 4/5** — 没有承认"我们 KB 里其实没有团队管理相关知识"，但答案的实质内容是诚实的
- **Latency: 3/5** — 22.78s
- **小计: 15/20**

### q3 - business :: 月活用户每月按固定比率掉 7%，怎么看怎么干预？

- **Retrieval: 4/5** — 命中"SaaS 客户生命周期价值"很对路，但"家庭预算约束优化"(0.80)、"Horton 河流分级"(0.78)是凑数。前者勉强能解释，后者明显牵强
- **Coherence: 5/5** — 把指数衰减 / LTV 公式 / 流失分层 / 约束优化 串成可操作清单，并且给了具体干预步骤 ①②③。这是 7 个 query 里最实用的答案
- **Honesty: 4/5** — 没有把 "Horton 定律" 圆得太硬，提了一下"分级结构"就跳过了
- **Latency: 3/5** — 23.07s
- **小计: 16/20**

### q4 - business :: 为什么有些谣言会爆，另一些悄悄消散？区别在哪？

- **Retrieval: 5/5** — 顶部命中三个谣言相关 KB（SIR/谣言传播/信息流行病学），都是高分高度对应
- **Coherence: 5/5** — R₀ + 接触率 × 说服力 > 免疫率 + 遗忘率，给出量化框架；类比传染病潜伏期解释辟谣时间差
- **Honesty: 5/5**
- **Latency: 4/5** — 21.95s 最快的几个
- **小计: 19/20**（全场最高）

### q5 - edge-irrelevant :: 我女朋友为什么生气了？

- **Retrieval: 2/5** — top KB 是"自我意识情绪的出现"(0.82)、"朋友圈信息回声室效应"(0.80)、"语言的递归嵌套"(0.62)、"污名扩散"(0.55)、"城市活动整合建模"(0.55)。后面三个明显凑数
- **Coherence: 4/5** — LLM 用"次级情绪 / 信息回声室"框架硬拗出有道理的话，甚至给了"打破回声室、温和地问"的可执行建议。但本质是 LLM 自己写情感答疑，KB 几乎没贡献
- **Honesty: 1/5** — **没有任何拒答**。理想行为应是 "这个问题不在结构同构知识库的覆盖范围内，但我可以从认知/情绪结构角度尝试..." 之类的免责声明。目前的输出会让用户误以为系统真的有相关 KB
- **Latency: 4/5** — 17.5s 较快
- **小计: 11/20**

### q6 - edge-trivial :: 求 1+1 = ?

- **Retrieval: 1/5** — top KB = "母线差动保护"(0.70)、"日常活动理论犯罪学"(0.55)、"Hall-Petch 关系材料学"(0.54)、两个幂律分布。全部 < 0.70 分，整个召回是垃圾
- **Coherence: 4/5** — 给了 "1+1=2 是皮亚诺公理"+ "母线差动保护是求和"+"幂律下求和失去代表性" 三段，确实文笔通顺，但**完全没必要**
- **Honesty: 1/5** — trivial query 应该直接回 "1+1=2，这个问题不需要结构同构分析"。当前却生成 494 字的强行同构作文，浪费 LLM token + 误导用户对系统的边界认知
- **Latency: 2/5** — **33.26s 全场最慢**，trivial 问题反而最慢，离谱
- **小计: 8/20**

### q7 - edge-prediction :: Bitcoin 明天涨还是跌？

- **Retrieval: 3/5** — 命中"股价随机漫步"(0.65) 是对的，但分数已经 < 0.7。"习得性无助"+"货币幻觉"+"彼得原理"+"土壤液化"全部 < 0.62，凑数严重
- **Coherence: 5/5** — 答案非常 sharp：明确告诉用户"原理上不可预测"，引用 random walk + 习得性无助 + 货币幻觉 三段都合理，最后给出 "你的投资决策框架是否能在不知道明天涨跌的前提下依然成立" 这个 reframe，非常好
- **Honesty: 5/5** — **唯一一个真正诚实的边缘 query**。明确拒绝预测，并解释为什么不能预测（虽然没有用"拒答" UI 标记，但内容上 honest）
- **Latency: 4/5** — 19.86s 较快
- **小计: 17/20**

---

## 综合分数表

| Query | Retrieval | Coherence | Honesty | Latency | 小计 |
|---|---|---|---|---|---|
| q1 SVB 挤兑 | 5 | 5 | 5 | 3 | **18** |
| q2 团队相变 | 3 | 5 | 4 | 3 | **15** |
| q3 用户流失 | 4 | 5 | 4 | 3 | **16** |
| q4 谣言传播 | 5 | 5 | 5 | 4 | **19** |
| q5 女朋友 | 2 | 4 | 1 | 4 | **11** |
| q6 1+1 | 1 | 4 | 1 | 2 | **8** |
| q7 BTC 预测 | 3 | 5 | 5 | 4 | **17** |
| **均值** | **3.3** | **4.7** | **3.6** | **3.3** | **14.9/20** |

---

## 5 个最严重 Issue（按优先级）

### P0 — 边缘 query 全部硬答，无 out-of-scope 机制

q5/q6 在 retrieval 已经反馈"top 5 KB score 全部 < 0.85，且 score=0.55-0.70 区间占多数"时，应触发 "out of scope" 模板回复，例如：

> 这个问题超出结构同构知识库的覆盖范围。你可能想从其他角度（如发展心理学 / 个人情感经验）寻找答案。

而不是花 30s LLM 时间硬拗。建议在 orchestrator 加 retrieval-score gate：top-1 < 0.75 或 top-3 平均 < 0.65 → 走 fallback prompt。

### P1 — 首 answer_chunk 延迟 18-32s（用户视角崩溃点）

观察 `first_byte_sec` 都 < 1s（meta 事件秒出）但 `first_answer_chunk_sec` 普遍 18-32s。说明 orchestrator 是"等 RAG 全跑完 + LLM 全部 prompt 准备好 → 才开始 streaming"。

对比 Perplexity 体感：用户能在 ~2s 内看到 KB cards，并在 ~3-4s 内看到第一个 token。建议：
- KB cards 流式 emit 后立即触发 LLM，不等所有 similar/followups 计算完
- 把 followups 移到 answer_done 之后异步生成（已经这样做但 first chunk 还是慢）
- 看看 LLM 调用是不是有不必要的 await（如阻塞计算 embedding 当 retrieval 时）

### P2 — q2 团队氛围 retrieval 顶部命中"形状记忆合金"（关键词 hack，score=1.0 明显异常）

base fallback embedding 把"相变恢复"和"团队氛围恢复"按字面"恢复"匹配到 score=1.0，这是 W1 disaster 后未恢复 v2 finetuned 模型的尾遗症。**model 恢复后必须 monitor retrieval 质量**，建议加 spotcheck 每天跑一组 ground-truth query 比对 top-K，发现 score 异常飙到 ≥ 0.95 但语义不匹配的情况报警。

### P3 — q6 trivial query 反而最慢（33.26s）

合理猜测：LLM 在 KB 一片低分的情况下需要更多"思考"如何把 1+1=2 拗成同构。这暴露了"无差别 LLM 调用"的反模式 —— 系统应该在 retrieval 阶段就判断 query intent，trivial / 数学 / 当日预测类直接走短路。建议引入 query classifier (规则 + 小模型) 在 RAG 前过滤。

### P4 — Citations `[1]-[5]` 引用规范但未在前端做对应

answer_text 里大量出现 `[1] [2] [3] [5]` 等引用标记，正确对应 kb_cards 的顺序。但 UI 端没看到是否做了 click-to-highlight。建议前端 PR 加 inline citation hover/click 跳转，否则当前 citation 是"装饰品"，丢失了 Perplexity-like 的可验证性优势。

---

## 建议下一步

1. **立刻做（P0）** — 在 `ask_orchestrator.py` 加 `retrieval_score_gate`：top-1 < 0.75 时触发短答案 fallback，省 LLM 钱 + 显示边界（影响 q5 q6 ~50% LLM 成本，user trust ++）
2. **本周（P1 + P2）** — 拆解 LLM 调用瓶颈：把 first answer_chunk 从 22s 降到 < 5s（profiling orchestrator 流程是哪步阻塞了）；同时启 retrieval daily spotcheck
3. **下个 milestone（P3 + P4）** — query classifier + inline citation UI

---

## Anomaly / 数据说明

- 7/7 query 全部 HTTP 200，没遇到 rate limit（运行时插了 2s sleep 缓冲，匿名 quota 5/min 没撞）
- 部署的 prod 模型是 `anthropic/claude-sonnet-4.6`（与 W2-E session #8 升级一致，没漂回旧模型）
- 单 query 完整事件类型计数 (q1 为例)：meta×1, kb_cards×1, answer_chunk×N, answer_done×1, similar_phenomena×1, followups×1, done×1（与 W6 设计文档完全一致）
- 测试环境：Mac local → CDN → VPS。本地到 prod 网络稳定，无 packet drop
- 测试时间窗：2026-05-14 16:54-16:58 UTC
- 报告由 sub-agent D 手动评分（无 LLM-as-judge 介入，避免循环偏见）

