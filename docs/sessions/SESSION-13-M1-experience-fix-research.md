# M1.1 — 问答体验硬伤根因调研

> 2026-05-20 · session #13 · 供 M1.2 / M1.3 实施直接照此执行。
> 主战场文件：`web/backend/services/ask_orchestrator.py`（+ `llm_service.py`、`api/ask.py` 注释同步）。

---

## 硬伤 1：首 token 延迟 18–32 秒

### 根因

`AskOrchestrator.stream()`（`ask_orchestrator.py:272`）完全串行，首个 `answer_chunk` 必须等前序步骤跑完。三段拆解：

- **检索（`search.search`，第 297 行）：1–3s，次因。** `SearchService` 是 `app_state` 启动单例，模型加载 / KB embedding 不在请求路径。请求内只做 query 编码（200–600ms，有 lru_cache）+ 4475 条向量点积 + BM25 + domain guard。`meta` 事件第 285 行已先 emit，慢的是 `meta` 之后到 `answer_chunk` 之间。
- **KB cards 组装（306–340 行）：<10ms，可忽略。**
- **LLM 首字节：18–32s 主因。** ① prompt 巨大且每次现拼（`_build_prompt` 第 886 行，in-scope 约 2000–3500 tokens），DeepSeek prefill 数秒；② `response_format: json_object`（`_call_llm_stream` 第 809 行）强制先吐 JSON 信封，`_AnswerFieldExtractor` 要等 `"answer":"` 才进 IN_VALUE，叠加约束解码开销；③ 检索 1–3s 硬串在 LLM 前（cards 是 prompt 前置）；④ DeepSeek via OpenRouter TTFT 高负载 8–25s 常态，是 18–32s 方差主因。

**结论**：18–32s ≈ 检索 1–3s +（OpenRouter/DeepSeek 长 TTFT 8–25s）+ JSON 信封前缀。

### 修复方案（按性价比）

| # | 方案 | 改哪 | 工作量 |
|---|---|---|---|
| 1 | **换快模型** — `ASK_MODEL` 默认值改 `deepseek-chat:nitro`（强制最快 provider）或换 Kimi/MiniMax 级快模型 | `ask_orchestrator.py:54` | 10 分钟，立即见效（TTFT 8–25s→2–6s）|
| 2 | **去 `json_object` 模式** — LLM 直接流式吐纯 markdown 正文，`answer_chunk` 转发 raw delta，`_AnswerFieldExtractor` 下线；citations 改从答案文本正则抽 `[n]` + 复用 `_validate_citations`（第 487 行）反查 cards | `_call_llm_stream`(843–852)、`_build_prompt`(886) | 0.5–1 天 |
| 3 | **检索 emit 提前 + prompt 瘦身** — 固定指令抽模块级常量、移到 system message、正文压到 150 字内（prefill 减半）；检索一返回立即 emit `retrieval_done`（已有，323 行）解耦感知延迟 | `_build_prompt`(886)、`stream`(280–301) | 2–4h |
| 4 | **加 `llm_start` 事件** — POST 前多 emit 一个事件，前端进度条推进，消除「18s 黑屏」体感断层 | `_call_llm_stream` 第 642 行前 | 1h |

合计约 **1.5–2 人天**，方案 1 可立即上线。

---

## 硬伤 2：out-of-scope 不拒答

### 根因

`_evaluate_relevance`（第 534 行）判定逻辑本身对（阈值 top-1<0.75 / top-3 mean<0.65 经 dogfood 校准，"1+1=?" 会正确 trip）。问题是**结果只当软信号**：第 349 行算出 `low_relevance` 后，第 379 行 `_stream_llm_answer_with_retry` 照常调 LLM，"拒答"全靠 `_build_prompt`（930–992 行）求 LLM 配合写委婉文案——违反「不信任 LLM 输出」，且仍烧一次完整 LLM 调用。`out_of_scope` 只是 `answer_done` 里的展示 flag。

**一句话**：relevance gate 是检测器，缺一条「检测为真 → 短路 LLM」的执行分支。

### 修复方案

核心：`stream()`（342–453 行）在第 349 行 `_evaluate_relevance` 之后、LLM 调用之前，插入**不调 LLM 的本地拒答短路分支**：

```
low_relevance, relevance_reason = self._evaluate_relevance(cards)
if low_relevance:
    payload = self._build_refusal_payload(query, cards, lang_norm, relevance_reason)
    for chunk in self._typewriter_chunks(payload["answer"]):   # 复用 477 行
        yield _sse("answer_chunk", {"delta": chunk}); await asyncio.sleep(TYPEWRITER_SLEEP_S)
    yield _sse("answer_done", {"full_text": payload["answer"], "citations": [],
               "out_of_scope": True, "scope_reason": relevance_reason, "refused": True})
    yield _sse("similar_phenomena", {"phenomena": []})
    yield _sse("followups", {"questions": payload["followups"]})
    yield _sse("done", {"latency_ms": ...}); return
```

**新增 `_build_refusal_payload`**（放 `_fallback_payload` 第 1023 行附近）：纯本地、不调 LLM。`answer` 按 lang 出中/英诚实文案（「这个问题不在 Structural 知识库覆盖范围内，Structural 擅长跨学科结构同构……数学计算/事实查询/个人琐事请换工具」），按 `scope_reason`（no_cards / top1_below / top3_mean_below）微调措辞；`followups` 给 3 个确定在 KB 范围内的示范问题；`citations` 空。

**事件结构**：复用现有序列，前端零改造可工作；`answer_done` 新增 `refused: true` 区分硬拒答 vs 旧软标签。因不调 LLM，out-of-scope 场景首 token 从 18–32s 直接降到 1–3s——**与硬伤 1 协同**。

**阈值**：不调，复用现有值（dogfood 校准过）。升级后重跑 dogfood 7 条 + 补 10–15 条边界 query 实测，确认无误杀正常跨域问题；误杀可调 env 旋钮 `ASK_RELEVANCE_TOP1_MIN` / `ASK_RELEVANCE_TOP3_MEAN_MIN`。

**清理**：`_build_prompt` 的 low_relevance 分支（930–992 行约 60 行）+ `low_relevance` 参数传递链成死代码，确认无测试依赖后删除。

合计约 **1 人天**（核心 60–80 行 0.5 天 + 清理 2h + 单测/集成测/dogfood 0.5 天）。

---

## 实施顺序建议

M1.2（硬伤 1）方案 1 先单独上线试 TTFT → 方案 2/3/4 一并做。M1.3（硬伤 2）独立，可与 M1.2 并行。两者都在 `ask_orchestrator.py`，注意 commit 边界拆清。
