# Query Failure Analysis — 匹配算法 & 用户查询失败模式

**Date**: 2026-05-24
**Scope**: 用户反映"找近似现象但找不到对应的现象"。本报告专攻匹配算法 + 用户查询失败模式（KB 内容缺口由另一 agent 处理）。
**Author**: Failure-Analysis sub-agent

---

## TL;DR — 三大快赢 + Top 3 失败模式

**Top 3 失败模式**（按估算占比，N=7 dogfood 真实 query + 算法 dry-run 验证）：
1. **BM25 中文分词坏掉 → 字面 hack（~30%）** — `jieba` 未装在 backend，分词退化到单字 → "团队**相变恢复**" 命中"形状记忆合金**相变恢复**" score=1.0
2. **专名 / 案例名 retrieval 全 miss（~25%）** — KB 收"通用现象"（如"银行挤兑"），用户问"SVB / 雷曼 / Tesla"，BM25/embedding 都 0 命中。但 KB 实际有对应通用概念
3. **跨语 retrieval 单边瘸（~20%）** — embedding 是 `text2vec-base-chinese`，KB 100% 中文。英文 query → 翻译偏置 + BM25 字面零命中

**3 个快赢**（1 周内可上线）：
- **W1**：装 jieba + rank_bm25 + 加 startup assert（半天，预期 top-1 召回质量提升 15-25 pct）
- **W2**：LLM query expansion——专名 → 通用概念 + 同义词字典（1 天，预期专名类 query 召回从 0% 到 60%+）
- **W3**：检测英文 query 后强制翻译为中文再 embedding（半天，预期英文 query 召回提升 30%+）

---

## 1. 数据源清单

| 来源 | 路径 | 信号量 | 备注 |
|---|---|---|---|
| Backend 结构化日志 | `web/backend/logs/server.jsonl`（43094 行） | **不存原始 query**（只有 `query_len`），无法直接做 failure-mode 分类 | 测试 fixture 占多数（"testserver" + 频繁 storage reset），真实流量信号弱 |
| SQLite history DB | `web/backend/data/history.db` | `history` / `reports` 表全部 **0 行** | DB schema 准备好了但生产没写入；当前无可挖的历史查询 |
| Dogfood 报告 | `docs/dogfood-ask-2026-05-15.{md,json}` | **7 条真实 query + 完整 KB cards + 评分** | 本次失败模式分类的主要 sample 来源 |
| LLM A/B 测试 | `docs/llm-ab-test-2026-05-14.md` | 3 条 EN/ZH 概念 query | 揭示了 retrieval 选错 KB（DeepSeek 引"分权改革俘获风险"答 SOC） |
| KB 元数据 | `data/kb-5000-merged.jsonl` | 4475 phenomena × 183 domains | 全中文；专名（SVB/Lehman/Tesla/GameStop）0 hits |
| Search algorithm | `web/backend/services/search_service.py` | BM25(0.45) + embedding(0.55) + dynamics +0.10 boost | 静态审查 + dry-run 验证 |
| Scope gate | `web/backend/services/scope_guard.py` + `ask_orchestrator._evaluate_relevance` | `RELEVANCE_TOP1_MIN=0.75`、`RELEVANCE_TOP3_MEAN_MIN=0.65` | gate 阈值可调 |

**关键约束**：因为日志不存原始 query + DB 是空的，**100 条失败 case 的占比量化基线不够**。本报告占比是基于 7 条 dogfood query × 算法 dry-run 探针的"代表性估算"，标注为粗估，不是统计意义上的精确比例。

---

## 2. 失败模式分类（含真实例子 + 占比）

### 2.1 BM25 字面 hack 召回（粗估 ~30%，置信度高）

**Root cause**：`web/backend/services/search_service.py:58-77` 的 `_tokenize` 在 jieba 不可用时回退到 char-level 切分，**但 `web/backend/requirements.txt` 里没列 `jieba` 也没列 `rank_bm25`**。Prod 实际行为有两种可能（取决于 venv 装没装）：
- 真的没 jieba → 中文被切成单字，BM25 完全字面匹配单字，无任何短语语义
- 真的没 rank_bm25 → `self._bm25 = None`，整个 hybrid 退化为纯 embedding（dogfood 报告也说 base fallback embedding 精度损失明显）

**Example (dogfood q2)**：
```
Query:  团队氛围崩了之后为什么很难恢复？跟相变有关系吗？
Top-1:  形状记忆合金的相变恢复（score=1.0，材料科学）— 纯关键词 hack
Top-5:  团队规模的沟通成本（score=0.82，管理学）— 真相关的被压到第 5
```
**Evidence**：char-level 切分把 query 和 doc 都拆成 {相, 变, 恢, 复}，4 字全对应 → BM25 满分。dogfood 评 retrieval 3/5。

**还有其他被波及的 query**：q6 "1+1" 召回"母线差动保护"（"求和"字面）；q3 "MAU 流失 7%" 召回 "Horton 河流分级"（"分级"字面）。

### 2.2 专名 / 案例名召回全 miss（粗估 ~25%，置信度高）

**Root cause**：KB 收"通用现象"（5k-01-001 ~ 5k-99-xxx 全是"XX 的 YY 现象"），但用户自然语言会带具体案例名（公司名、人名、事件名）。Probe 结果：

| 专名 | KB 中 name 字段命中数 |
|---|---|
| 硅谷银行 / SVB | 0 / 0 |
| 雷曼 / Lehman | 0 / 0 |
| Tesla / 特斯拉 | 0 / 1（在描述里出现，不是主名） |
| GameStop / 游戏驿站 | 0 / 0 |
| COVID / 新冠 | 1 / 5 |

**Example (dogfood q1)**：
```
Query:  为什么硅谷银行挤兑后市场反应这么剧烈？
Top-1:  银行挤兑（score=0.94）— 这条侥幸救场，因为"挤兑"是高频通用词
```
但如果用户问 "Theranos 是怎么崩的"（KB 里 `Theranos` 描述命中 1 条但不是主 entry）或 "WeWork 为什么估值崩盘"（0 命中）→ retrieval 退到 0.55-0.65 区间，触发 scope gate refusal。**用户感知就是"找不到"**。

### 2.3 跨语 retrieval 单边瘸（粗估 ~20%，置信度中）

**Root cause**：embedding 是 `shibing624/text2vec-base-chinese`（base fallback，W1 disaster 后没恢复 v2 finetuned），训练以中文为主。BM25 全部 doc 是中文。但用户大概率会用英文查（论文、Stack Overflow 习惯）。

| 同义概念 | EN 字面 KB 命中 | ZH 字面 KB 命中 |
|---|---|---|
| power-law / 幂律 | **0** | 64 |
| Pareto / 帕累托 | **0** | 27 |
| phase transition / 相变 | **0** | 73 |
| feedback loop / 正反馈 | **0** | 86 |
| tipping point / 临界 | **0** | 177 |
| cascade / 级联 | **0** | 53 |
| bank run / 挤兑 | **0** | 5 |
| Black Swan / 黑天鹅 | **0** | 0（KB 本身没有这条） |

**Example**：英文 query "What is self-organized criticality" 在 LLM AB test 里 DeepSeek 用 base embedding 召回了"分权改革的俘获风险"——拼音相关（SOC 想成 Society？）的乱命中。Sonnet 4.6 因为它自身的 multilingual 能力能在 prompt 阶段救场，但 retrieval 本身仍是错的。

### 2.4 别名 / 同义词不归一（粗估 ~10%，置信度中）

**Root cause**：没有同义词字典 / 别名归一。

**Examples**：
- "幂律" / "power-law" / "Pareto distribution" / "Zipf distribution" / "Heavy-tail" → 应该归到同一 cluster
- "正反馈" / "positive feedback loop" / "self-reinforcing" / "vicious cycle" → 应该归一
- "羊群效应" / "herding" / "bandwagon" / "信息级联" / "群体盲从" → KB 里有 3 条但 "羊群行为" 和 "羊群效应" 算两个 phenomena
- "回声室" / "信息茧房" / "filter bubble" / "echo chamber" → 多个变体

### 2.5 过宽 / 抽象 query 召回多但都浅（粗估 ~8%，置信度中）

**Example (dogfood q5)**：
```
Query:  我女朋友为什么生气了？
Top-1:  自我意识情绪的出现（score=0.82）— LLM 硬拗
Top-3:  朋友圈信息的回声室效应（0.80）/ 语言的递归嵌套（0.62）
```
query 抽象 + 跨人类情感场景，每条召回都"沾点边"但都不深。dogfood honesty 评 1/5。**当前 scope_guard 没拦住**（top-1=0.82 高于 0.75 阈值）。

### 2.6 时态 / 否定 / 假设 query（粗估 ~5%，置信度低）

**Example (dogfood q7)**：
```
Query:  Bitcoin 明天涨还是跌？
Top-1:  股价随机漫步（0.65）— 这个是对的，但卡在 top1 < 0.75 阈值
```
q7 实际被 `_is_forecasting_intent` 关键词 gate 抢先拦截了，这层处理正确。问题在"假设性"和"反例"类（"什么情况下幂律会失效？"、"反过来如果不存在级联会怎样？"）：embedding 不擅长否定语义反转，KB 又没收 anti-pattern 文档。这层数据量太小，本报告估算保守 5%。

### 2.7 跨域桥接缺失 / 排序错位（粗估 ~2%，置信度中）

**Example**：q3 "MAU 流失 7%" 最该召回"SaaS 客户生命周期价值"（KB 里有 score=0.74），但排到第 5；"Horton 河流分级"（0.78）排到第 2。`_domain_guard` MMR-lite 是为了多样性，但在 query 已经明确是商业领域时反而稀释了正确域。

---

## 3. 算法改进建议清单（按 ROI 排序）

| # | 改进 | 针对失败模式 | 工时 | 预期召回提升 | ROI |
|---|---|---|---|---|---|
| 1 | **装 `jieba` + `rank_bm25` 到 requirements.txt + startup assert** | 2.1 | 半天 | top-1 质量 +15-25 pct（消除字面 hack 类） | **★★★★★** |
| 2 | **LLM query expansion**：在 retrieval 前调用一次轻量 LLM，把专名 → 通用概念 + 同义词 + 翻译。结果作为多 query 并联检索，结果 union 再 rerank | 2.2 / 2.3 / 2.4 | 1 天 | 专名 query 召回 0% → 60%+；EN query +30% | **★★★★★** |
| 3 | **英文 query 检测 + 强制翻译再 embedding**（轻量启发式 `re.match("[A-Za-z]")` 占比 > 50% → 调 LLM 翻译） | 2.3 | 半天 | EN query 召回 +30% | **★★★★** |
| 4 | **Synonym / alias 字典**：维护中英双语别名表（power-law ↔ 幂律 ↔ Pareto），retrieval 时把 query 和 doc 都做规范化展开 | 2.4 / 2.3 | 1-2 天（含字典初版 50 条） | 同义类 query 召回 +10-15% | **★★★★** |
| 5 | **Cross-encoder rerank**：top-20 BM25+emb 结果送 BGE-reranker 重排序，专治 BM25 字面 hack 排序错位 | 2.1 / 2.5 / 2.7 | 2 天（含 cross-encoder 集成 + 缓存） | top-3 准确率 +20% | **★★★★** |
| 6 | **Embedding 模型升级到多语 BGE-M3 / e5-multilingual**（含一次性 KB re-encoding） | 2.3 | 3 天（含 retrain 测试 + KB embedding 重算 + 上线灰度） | EN/混合 query 召回 +30-40% | **★★★** |
| 7 | **降低 scope_guard 误拒**：低相关度 query 不直接 refuse，先做"近义现象"列表展示（"看起来你在问 X，KB 里有这些近似现象..."），让用户自己点 | 2.5 / 2.6 | 1 天 | UX：从 refuse → 探索式承接，降低"找不到"感知 | **★★★** |
| 8 | **Tighten dynamics 触发词 + 调整 BM25/embedding 权重**：当 query 带强 dynamics 词（"相变""级联"）时降 BM25 权重到 0.25 防字面 hack | 2.1 | 半天 + 评估 | top-1 准确率 +5-10% | **★★** |
| 9 | **Negation / hypothesis detector**：检测"为什么不"、"反过来"、"反例"等 → 单独走 LLM-only fallback（不强制 retrieval） | 2.6 | 1 天 | 否定类 query 不再硬拗 | **★★** |

---

## 4. 快赢清单（1 周可上线，按上线顺序）

### 快赢 #1（Day 1，半天）— 把 BM25 真正修好
```
1. requirements.txt 加 jieba>=0.42.1 + rank_bm25>=0.2.2
2. main.py / startup_check.py 加 assert：
   try: import jieba, rank_bm25
   except ImportError: raise RuntimeError("Hybrid retrieval requires jieba + rank_bm25")
3. 加 /api/health?deep=1 暴露 self._bm25 is not None 标志
4. 重跑 dogfood 7 query 对比 baseline，确认 q2/q3/q6 字面 hack 消失
```
**预期**：q2 top-1 从"形状记忆合金"换成"团队规模沟通成本"，retrieval 评分从 3/5 提到 4/5。

### 快赢 #2（Day 2-3，1 天）— LLM query expansion
```
1. ask_orchestrator 在 retrieval 之前加 _expand_query(query, lang):
   - prompt: "把这句话转成 1 条通用概念 + 2 条相近表述 + 1 条英文表述，每条 < 20 字"
   - 用 deepseek-chat（便宜，~$0.0005/call）+ 5s 超时 + 失败 fallback 原 query
2. 4 条 query 并联各跑一次 search()，结果按 phenomenon_id union + max-score 合并
3. 加 expansion cache（query → expansions LRU 1024）防止重复调用
```
**预期**：q1 "硅谷银行挤兑" → expansion 出 "银行挤兑 / 流动性危机 / bank run"，retrieval 稳定召回"银行挤兑"+"信息级联"+"网络效应"。专名类 query 召回从 0% 到 60%+。

### 快赢 #3（Day 4，半天）— 英文 query 翻译再 embedding
```
1. 在 search_service.encode_query() 前加 _detect_lang(query)：
   ASCII 字母占比 > 50% → 视为 EN
2. EN query 走一次轻量翻译（同样 deepseek-chat）转成中文再 encode
3. 同时保留原 EN query 走 BM25（万一 KB 描述里夹了 EN 术语）
```
**预期**：现在 EN query 跑出来的 retrieval 不再是"分权改革俘获风险"乱命中类，大概率能上 0.7+。

### 上线后监控
- 加 `ask.retrieval` 结构化日志记 **原始 query**（脱敏后）+ top-5 KB ids + scores（**当前日志只记 `query_len` 是这次分析最大障碍**）
- 1 周后再跑一次 100 条真实 query 的失败模式量化，把粗估占比换成精确数

---

## 5. Caveats & 限制

1. **占比是粗估，不是统计**：N=7 dogfood + 算法探针不构成统计学样本。上线日志后必须用 100+ 条真实 query 重做。
2. **jieba 状态不 100% 确定**：本报告基于 backend requirements.txt 没有 + 本地 .venv 装不到推断 prod 也没装。建议 SSH 上 VPS 实测 `python -c "import jieba"` 验证（出于本任务 read-only 约束未跑）。
3. **本报告不动 search_service 代码**（任务约束）：所有改进是分析建议，由后续 milestone 执行。
4. **未覆盖**：性能 / 延迟 / cache hit rate / cost 失败模式（这些在 dogfood P1 已分析）。本报告专注"召回正确性"维度。
5. **优先建议先做 #1 + #2 + #3 三件套**，做完再评估是否值得上 cross-encoder（#5）或换 embedding 模型（#6）——后两者工时大，应等快赢 baseline 跑出来再决定 ROI。

---

**Files referenced**:
- `/Users/dadamini/Projects/structural-isomorphism/web/backend/services/search_service.py`
- `/Users/dadamini/Projects/structural-isomorphism/web/backend/services/ask_orchestrator.py`
- `/Users/dadamini/Projects/structural-isomorphism/web/backend/services/scope_guard.py`
- `/Users/dadamini/Projects/structural-isomorphism/docs/dogfood-ask-2026-05-15.{md,json}`
- `/Users/dadamini/Projects/structural-isomorphism/docs/llm-ab-test-2026-05-14.md`
- `/Users/dadamini/Projects/structural-isomorphism/web/backend/requirements.txt`
- `/Users/dadamini/Projects/structural-isomorphism/data/kb-5000-merged.jsonl`
