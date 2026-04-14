"""
LLM Service — OpenRouter 调用，生成结构映射和行动建议。
"""
import json
import logging
import os
from typing import Dict, Optional

import httpx

logger = logging.getLogger("structural.llm")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Shared module-level client so we reuse the underlying TCP / TLS connection
# pool across all LLM calls. Creating a fresh AsyncClient per call adds
# ~100-300ms of TLS handshake overhead, which adds up for a multi-call flow.
# The client has no default timeout — each call passes its own (short for
# assess, long for streaming) via `timeout=` kwarg to the request method.
_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None or _HTTP_CLIENT.is_closed:
        _HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(300.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            http2=False,
        )
    return _HTTP_CLIENT


class LLMService:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4.6")
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set; LLM calls will fail.")

    async def rewrite_query(self, query: str) -> Optional[str]:
        """Backward-compat wrapper — just the rewritten string."""
        result = await self.assess_and_rewrite(query)
        return result.get("rewritten") or query

    async def assess_and_rewrite(self, query: str) -> Dict:
        """
        Combined query rewrite + worthiness assessment in a single LLM call.
        Returns a dict:
        {
            "rewritten": str,                  # phenomenon-style description
            "worth_score": int,                # 1-5, higher = more analyzable
            "category": str,                   # 现象描述/元问题/命令式/闲聊/太抽象/个人事务/学术方向
            "coaching": str | None,            # advice when worth_score < 3, else None
            "rewrite_suggestion": str | None,  # concrete rewritten query when score < 3
        }
        On any failure, returns a permissive fallback (worth_score=4) so the
        user is never silently blocked due to an LLM error.
        """
        fallback = {
            "rewritten": query,
            "worth_score": 4,
            "category": "现象描述",
            "coaching": None,
            "rewrite_suggestion": None,
        }
        # Only short-circuit on truly empty input. Even 3-char queries like
        # "为什么" should hit the LLM gate so they don't silently slip through.
        if not self.api_key or len(query.strip()) < 2:
            return fallback

        prompt = f"""你是 Structural（一个跨领域结构同构搜索引擎）的输入预检员。用户输入了一个问题，请同时做两件事：

1. 评估这个输入对 Structural 的适配度（worth_score 1-5）
2. 把它改写成客观的现象描述（60-120 字）以便检索

# Structural 是什么
Structural 接收用户描述的"现象"——某种行为模式、动力学、变化趋势、临界点——然后从 4475 个跨学科现象中找出**结构相同**的对应物（比如生态学/物理学/经济学里的同构案例），合成一份跨学科迁移分析报告。

# 适合 Structural 的输入
- 现象描述：「团队规模变大后效率反而下降」「市场越成熟创新越慢」
- 学术研究方向：「无序到有序的相变现象」「群体智能的涌现机制」
- 行为/动力学问题：「为什么短视频会让人上瘾」「为什么有些市场必然赢家通吃」

# 不适合 Structural 的输入（worth_score 应 ≤ 2）
- **命令式 prompt**：「帮我写一篇关于 XX 的论文」「给我一个商业计划书」
- **元问题**：「Structural 怎么用」「这个产品是干嘛的」
- **闲聊**：「你好」「在吗」「天气怎么样」
- **太抽象**：「为什么」「怎么办」（少于 8 字且无具体现象）
- **纯个人事务**：「我同事昨天惹我生气了」「我妈做的菜变咸了」（私人琐事，无可迁移结构）
- **纯事实查询**：「北京到上海多远」「水的沸点是多少」（百科类，不是同构问题）
- **要求生成内容**：「写首诗」「翻译这段话」

# 用户输入
{query}

# 请输出严格 JSON（不要 markdown 代码块）
{{
  "rewritten": "<60-120 字的客观现象描述。如用户已经在描述现象，微调润色即可。如果输入完全不适合改写，原样返回>",
  "worth_score": <1-5 的整数>,
  "category": "<必须是以下之一：现象描述 / 学术方向 / 元问题 / 命令式 / 闲聊 / 太抽象 / 个人事务 / 纯事实>",
  "coaching": "<仅当 worth_score < 3 时填写：一句话告诉用户为什么不适合，30 字以内。否则为 null>",
  "rewrite_suggestion": "<仅当 worth_score < 3 时填写：给用户一个具体的、Structural 适合分析的改写示例，要保留用户的原始意图，30-60 字。否则为 null>"
}}"""

        try:
            client = _get_http_client()
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-haiku-4.5",  # fast + cheap
                    "messages": [
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 600,
                    "response_format": {"type": "json_object"},
                },
                timeout=15.0,
            )
            if True:
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                # Strip stray markdown fences if the model added them
                if content.startswith("```"):
                    content = content.strip("`").lstrip("json").strip()
                parsed = json.loads(content)

                # Validate + clamp
                rewritten = (parsed.get("rewritten") or query).strip().strip('"「」').strip() or query
                try:
                    worth = int(parsed.get("worth_score", 4))
                except (TypeError, ValueError):
                    worth = 4
                worth = max(1, min(5, worth))
                category = parsed.get("category") or "现象描述"
                coaching = parsed.get("coaching")
                suggestion = parsed.get("rewrite_suggestion")
                if worth >= 3:
                    coaching = None
                    suggestion = None

                logger.info(
                    "Query assess: '%s' -> worth=%d cat=%s rewritten='%s'",
                    query[:60], worth, category, rewritten[:60],
                )
                return {
                    "rewritten": rewritten,
                    "worth_score": worth,
                    "category": category,
                    "coaching": coaching,
                    "rewrite_suggestion": suggestion,
                }
        except Exception as e:
            logger.warning(f"Query assess failed: {e}")
            return fallback

    async def stream_mapping(
        self,
        a: Dict,
        b: Dict,
        similarity: float,
    ):
        """
        Stream mapping generation. Yields SSE-formatted chunks as the LLM generates text.
        Each chunk: {"type": "text", "content": "..."} or {"type": "done", "mapping": {...}}
        """
        if not self.api_key:
            yield {"type": "done", "mapping": self._fallback_mapping(a, b, similarity)}
            return

        prompt = self._build_prompt(a, b, similarity)

        try:
            client = _get_http_client()
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2500,
                    "response_format": {"type": "json_object"},
                    "stream": True,
                },
                timeout=180.0,
            ) as resp:
                resp.raise_for_status()
                accumulated = ""
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                        delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if delta:
                            accumulated += delta
                            yield {"type": "text", "content": delta, "total_length": len(accumulated)}
                    except json.JSONDecodeError:
                        continue

                # Parse the final JSON
                try:
                    parsed = json.loads(accumulated)
                    normalized = self._normalize(parsed)
                    yield {"type": "done", "mapping": normalized}
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse final JSON: {e}. Content: {accumulated[:500]}")
                    yield {"type": "done", "mapping": self._fallback_mapping(a, b, similarity)}
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield {"type": "error", "message": str(e)}
            yield {"type": "done", "mapping": self._fallback_mapping(a, b, similarity)}

    async def generate_mapping(
        self,
        a: Dict,
        b: Dict,
        similarity: float,
    ) -> Optional[Dict]:
        """
        给定两个现象 a, b，生成结构映射分析。
        返回结构：
        {
            "structure_name": "指数衰减",
            "formula": "Y = Y_0 e^{-kt}",
            "core_insight": "一句话解释",
            "parameter_mapping": [
                {"a_term": "...", "a_symbol": "...", "b_term": "...", "b_symbol": "..."},
                ...
            ],
            "action_suggestions": [
                {"title": "...", "description": "...", "scenario": "..."},
                ...
            ],
            "why_important": "..."
        }
        """
        if not self.api_key:
            return self._fallback_mapping(a, b, similarity)

        prompt = self._build_prompt(a, b, similarity)

        try:
            client = _get_http_client()
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 2500,
                    "response_format": {"type": "json_object"},
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return self._normalize(parsed)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._fallback_mapping(a, b, similarity)

    def _build_prompt(self, a: Dict, b: Dict, similarity: float) -> str:
        return f"""分析以下两个来自不同领域的现象，它们被模型识别为结构同构（相似度 {similarity:.2f}）：

现象 A：{a.get('name', '')}
领域：{a.get('domain', '')}
描述：{a.get('description', '')}

现象 B：{b.get('name', '')}
领域：{b.get('domain', '')}
描述：{b.get('description', '')}

请输出一个 JSON 对象，包含以下字段：

1. "structure_name": 共享的数学/结构类型名称（中文，如"指数衰减"、"网络效应"、"相变"）
2. "formula": 该结构的核心数学公式（LaTeX 格式，不含 $ 符号）
3. "core_insight": 一句话说明为什么这两个现象本质上是同一件事（不超过 40 字）
4. "parameter_mapping": 数组，3-5 个参数对应关系，每个对象包含：
   - "a_term": A 领域中的概念名（如"原子核数量"）
   - "a_symbol": A 领域中的数学符号（如"N"）
   - "b_term": B 领域中对应的概念名
   - "b_symbol": B 领域中对应的数学符号
   - "note": 这对参数为什么对应（一句话）
5. "action_suggestions": 数组，3 条"从 A 领域借用到 B 领域"的可执行建议，每条包含：
   - "title": 建议标题（简短）
   - "description": 具体做什么（2-3 句）
   - "scenario": 适用场景（一句）
6. "why_important": 这个映射对 B 领域的实际价值（一段话，2-3 句）

要求：
- 所有内容用中文
- 参数映射必须在数学上真实成立
- 行动建议必须具体、可执行，不要说空话
- 不要客套话，不要"综上所述"之类
- 输出严格的 JSON，不含 markdown 代码块标记"""

    def _normalize(self, data: Dict) -> Dict:
        """确保字段完整，避免前端崩溃。"""
        return {
            "structure_name": data.get("structure_name", "未识别结构"),
            "formula": data.get("formula", ""),
            "core_insight": data.get("core_insight", ""),
            "parameter_mapping": data.get("parameter_mapping", []) or [],
            "action_suggestions": data.get("action_suggestions", []) or [],
            "why_important": data.get("why_important", ""),
        }

    def _fallback_mapping(self, a: Dict, b: Dict, similarity: float) -> Dict:
        """LLM 失败时的降级映射（静态）。"""
        return {
            "structure_name": "结构分析暂不可用",
            "formula": "",
            "core_insight": f"两个现象具有 {similarity:.0%} 的结构相似度。",
            "parameter_mapping": [],
            "action_suggestions": [],
            "why_important": "详细的结构映射正在生成中，请稍后刷新。",
        }

    async def synthesize_answer(
        self,
        query: str,
        rewritten_query: Optional[str],
        top_results: list,
    ) -> Optional[Dict]:
        """
        Given a user query and the top search results (KB phenomena),
        generate a synthesized answer with:
        - main_insight: overall structural analysis
        - why_these_matter: why these cross-domain results help
        - primary_recommendation: the SINGLE most valuable result to look at first,
                                  with reasoning and expected takeaway
        - alternative_angles: 2 additional results that offer different perspectives
        - relevance_snippets: one-line explanation for all top results

        This drives the results page from "N equal cards" to "clear recommendation +
        supporting options", solving the "I don't know which one to click" problem.
        """
        if not self.api_key or not top_results:
            return None

        # Take top 5 for synthesis
        top5 = top_results[:5]
        results_block = ""
        for i, r in enumerate(top5, 1):
            results_block += f"\n[{i}] {r.get('name', '')}（领域：{r.get('domain', '')}）\n    {r.get('description', '')[:220]}\n"

        prompt = f"""用户的问题是：
"{query}"
{f'改写后的现象描述：' + rewritten_query if rewritten_query and rewritten_query != query else ''}

我们的跨学科知识库返回了以下结构最相似的现象：
{results_block}

你的任务是给用户一份**有明确引导**的回答。用户是专业人士，他不想要"这有 5 个选项你自己挑"，他想要"我建议你先看这个，因为..."。

请输出严格的 JSON：

{{
  "main_insight": "综合分析这些跨领域证据，告诉用户你发现了什么本质结构（2-3 句话，用 \\n\\n 分段）",

  "why_these_matter": "为什么这些其他领域的现象能真正帮到用户（1-2 句）",

  "primary_recommendation": {{
    "result_index": 1,
    "reason": "为什么这个是**最值得先看**的。不是因为相似度高，而是因为它在用户的问题上能提供最直接、最可操作的答案。2-3 句。",
    "what_youll_learn": "看完它你会得到什么具体的东西（一句话，很具体，不要抽象）"
  }},

  "alternative_angles": [
    {{
      "result_index": 2,
      "angle_label": "必须**严格**是以下四个字符串之一：'对立面' | '时间尺度差异' | '微观机制' | '跨尺度类比'",
      "reason": "为什么这个视角也值得看，具体说清它带来什么增量（1-2 句）"
    }},
    {{
      "result_index": 3,
      "angle_label": "必须**严格**是以下四个字符串之一：'对立面' | '时间尺度差异' | '微观机制' | '跨尺度类比'（且与上一条不同）",
      "reason": "..."
    }}
  ],

  "relevance_snippets": [
    {{"index": 1, "snippet": "这个现象和用户问题的关系（50 字内）"}},
    {{"index": 2, "snippet": "..."}},
    {{"index": 3, "snippet": "..."}},
    {{"index": 4, "snippet": "..."}},
    {{"index": 5, "snippet": "..."}}
  ]
}}

重要要求：
- 中文
- `primary_recommendation` 必须有实质理由，不能泛泛地说"相似度高"
- `primary_recommendation.what_youll_learn` 必须具体可执行。比如"一套预测团队效率拐点的 3 参数模型"，不要"一些启发"
- `alternative_angles` 必须和 primary 有**不同的角度**，不是同样的东西
- `alternative_angles[*].angle_label` **必须严格等于**这四个字符串之一（不得改写、不得添加后缀）：
    1. 对立面 —— 反面/counter-case，能推翻或挑战 primary 结论的情况
    2. 时间尺度差异 —— 同一结构在更长/更短时间尺度上表现出不同动态
    3. 微观机制 —— zoom-in 到底层机制，揭示 primary 没讲清楚的微观因果
    4. 跨尺度类比 —— 个体↔群体、micro↔macro 的同构，让 primary 结论在另一尺度复现
- 从这 4 个角度里挑**信息量最大的 2 个**（两个 label 不能相同），选不出第二个时就选最能补充 primary 的
- 每个 relevance_snippet 不超过 50 字
- 不要 markdown 代码块
- 不说"综上所述"、"希望能帮到你"这种废话
- JSON 字符串内部不要用 ASCII 双引号 " ，需要时用中文引号「」或单引号 '"""

        try:
            client = _get_http_client()
            resp = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "anthropic/claude-haiku-4.5",
                    "messages": [
                        {"role": "system", "content": "你是跨学科研究助手。你的任务是给用户明确的引导，告诉他先看哪个、为什么、能得到什么。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.4,
                    "max_tokens": 2500,
                    "response_format": {"type": "json_object"},
                },
                timeout=60.0,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            fixed = _fix_latex_escapes(content)
            try:
                parsed = json.loads(fixed)
            except json.JSONDecodeError:
                logger.warning(f"Synthesize JSON parse failed, trying repair")
                parsed = _try_repair_json(fixed)
            return parsed
        except Exception as e:
            logger.error(f"Synthesize failed: {e}")
            return None

    async def stream_deep_analysis(
        self,
        a: Dict,
        b: Dict,
        similarity: float,
        user_query: Optional[str] = None,
    ):
        """
        Stream a full deep-analysis research report.
        Yields SSE-style chunks:
          {"type": "text", "content": "...", "total_length": N}
          {"type": "done", "report": {...}}
          {"type": "error", "message": "..."}
        """
        if not self.api_key:
            yield {"type": "done", "report": self._fallback_deep_report(a, b, similarity)}
            return

        prompt = build_deep_analysis_prompt(a, b, similarity, user_query)

        try:
            client = _get_http_client()
            async with client.stream(
                "POST",
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": DEEP_ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.35,
                    "max_tokens": 16000,
                    "response_format": {"type": "json_object"},
                    "stream": True,
                },
                timeout=300.0,
            ) as resp:
                    resp.raise_for_status()
                    accumulated = ""
                    emitted_keys = set()
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                accumulated += delta
                                yield {
                                    "type": "text",
                                    "content": delta,
                                    "total_length": len(accumulated),
                                }
                                # Check if any new top-level section has been completed
                                try:
                                    completed = find_complete_top_sections(accumulated)
                                    for key, value in completed:
                                        if key not in emitted_keys:
                                            emitted_keys.add(key)
                                            yield {
                                                "type": "section",
                                                "key": key,
                                                "data": value,
                                            }
                                except Exception as e:
                                    logger.debug(f"Streaming section parse skip: {e}")
                        except json.JSONDecodeError:
                            continue

                    # Final: parse whole JSON with LaTeX fix, fallback to repair
                    final_report = None
                    fixed = _fix_latex_escapes(accumulated)
                    try:
                        final_report = json.loads(fixed)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Primary JSON parse failed: {e}. Trying repair...")
                        final_report = _try_repair_json(fixed)
                        if final_report:
                            logger.info("Repaired partial JSON successfully")

                    if final_report is None:
                        logger.error(f"JSON repair failed. Head: {accumulated[:300]}")
                        final_report = self._fallback_deep_report(a, b, similarity)
                    else:
                        # Emit any remaining sections that weren't caught during streaming
                        # (e.g., the very last one if the parser was more conservative)
                        for key in final_report:
                            if key not in emitted_keys:
                                yield {
                                    "type": "section",
                                    "key": key,
                                    "data": final_report[key],
                                }
                                emitted_keys.add(key)

                    yield {"type": "done", "report": final_report}
        except Exception as e:
            logger.error(f"Deep analysis stream failed: {e}")
            yield {"type": "error", "message": str(e)}
            yield {"type": "done", "report": self._fallback_deep_report(a, b, similarity)}

    def _fallback_deep_report(self, a: Dict, b: Dict, similarity: float) -> Dict:
        """降级：返回一个空结构的报告，让前端不崩溃。"""
        return {
            "shared_structure": {
                "name": "结构分析暂不可用",
                "formal_expression": "",
                "intuition": f"两个现象的嵌入相似度为 {similarity:.2f}。详细分析暂时无法生成，请稍后重试。",
            },
            "your_problem_breakdown": {
                "summary": "",
                "key_variables": [],
                "dynamics": "",
                "why_stuck": "",
            },
            "target_domain_intro": {
                "domain_name": a.get("domain", ""),
                "what_it_studies": "",
                "corresponding_phenomenon": {
                    "name": a.get("name", ""),
                    "plain_description": a.get("description", ""),
                    "discovery_history": "",
                },
                "key_thinkers": [],
                "mature_tools": [],
            },
            "structural_mapping": {"rationale": "", "parameter_map": []},
            "borrowable_insights": [],
            "how_to_combine": {"steps": [], "assumptions_to_verify": [], "boundary_conditions": ""},
            "research_directions": {
                "literature_status": "未知",
                "status_explanation": "",
                "if_novel_opportunity": None,
                "suggested_references": [],
            },
            "risks_and_limits": [],
            "action_plan": {
                "intro": "",
                "if_time_short": None,
                "this_week": [],
                "next_week_followup": "",
            },
        }


def _fix_latex_escapes(text: str) -> str:
    """
    Sanitize common LLM JSON-output mistakes inside string values:

    1. Raw LaTeX backslashes (`\\frac`, `\\partial`, etc.) not double-escaped
    2. Unescaped ASCII double quotes inside Chinese strings (e.g. `"这种"赢家通吃"的机制"`)

    Walks the text with a string-state machine. When inside a string:
    - Single backslashes followed by letters get doubled
    - ASCII `"` that aren't followed by structural characters (`,:]}` + whitespace + EOF)
      are treated as internal quotes and escaped as `\\"`
    """
    out = []
    i = 0
    n = len(text)
    in_string = False

    def is_terminator_ahead(idx: int) -> bool:
        """Does the '"' at position idx act as a string terminator?
        Look ahead past whitespace — if the next char is a structural JSON token,
        this is a real closing quote; otherwise it's a stray internal quote.
        """
        j = idx + 1
        while j < n and text[j] in " \t\n\r":
            j += 1
        if j >= n:
            return True
        return text[j] in ",:]}"

    while i < n:
        ch = text[i]
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        # === Inside a string ===
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "\\":
                out.append("\\\\")
                i += 2
                continue
            if nxt in '"/bfnrtu':
                # Valid JSON escape — keep
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            # Invalid escape (LaTeX command) — double it
            out.append("\\\\")
            i += 1
            continue

        if ch == '"':
            if is_terminator_ahead(i):
                # Real closing quote
                out.append(ch)
                in_string = False
            else:
                # Stray internal quote — escape it
                out.append("\\\"")
            i += 1
            continue

        # Other chars — pass through
        out.append(ch)
        i += 1

    return "".join(out)


def _find_string_end(text: str, start: int) -> int:
    """Find the index of the closing quote of a JSON string starting at `start`."""
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i
        i += 1
    return -1


def _find_value_end(text: str, start: int) -> int:
    """Find the exclusive end index of a complete JSON value beginning at `start`. Returns -1 if incomplete."""
    i = start
    n = len(text)
    if i >= n:
        return -1
    ch = text[i]

    if ch == '"':
        end = _find_string_end(text, i + 1)
        return end + 1 if end >= 0 else -1
    if ch == "{" or ch == "[":
        depth = 1
        i += 1
        in_string = False
        escape = False
        while i < n and depth > 0:
            c = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if c == "\\":
                escape = True
                i += 1
                continue
            if c == '"':
                in_string = not in_string
                i += 1
                continue
            if in_string:
                i += 1
                continue
            if c == "{" or c == "[":
                depth += 1
            elif c == "}" or c == "]":
                depth -= 1
            i += 1
        return i if depth == 0 else -1
    if ch in "-0123456789":
        i += 1
        while i < n and text[i] in "-+0123456789.eE":
            i += 1
        return i
    # Literals
    for literal in ("true", "false", "null"):
        if text[i : i + len(literal)] == literal:
            return i + len(literal)
    return -1


def find_complete_top_sections(text: str) -> "list[tuple[str, object]]":
    """
    Parse a potentially incomplete JSON object and return a list of (key, value) pairs
    for all top-level keys whose values are fully parsed.

    Used during streaming — as new text arrives, more sections become 'complete' and
    can be yielded to the frontend for progressive rendering.
    """
    # Fix LaTeX escapes in place first — LLMs often emit \frac instead of \\frac
    text = _fix_latex_escapes(text)

    stripped = text.lstrip()
    if not stripped.startswith("{"):
        return []

    # Find the '{' position in the original string
    offset = len(text) - len(stripped)
    i = offset + 1
    n = len(text)
    completed = []

    while i < n:
        # Skip whitespace and commas
        while i < n and text[i] in " \t\n\r,":
            i += 1
        if i >= n:
            break
        if text[i] == "}":
            break
        # Expect a string key
        if text[i] != '"':
            break
        key_start = i + 1
        key_end = _find_string_end(text, i + 1)
        if key_end < 0:
            break
        key = text[key_start:key_end]
        i = key_end + 1
        # Skip whitespace before ':'
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n or text[i] != ":":
            break
        i += 1
        # Skip whitespace before value
        while i < n and text[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        # Read value
        value_start = i
        value_end = _find_value_end(text, i)
        if value_end < 0:
            break  # incomplete value — stop scanning
        value_text = text[value_start:value_end]
        try:
            value = json.loads(value_text)
            completed.append((key, value))
        except json.JSONDecodeError:
            # Malformed — stop
            break
        i = value_end

    return completed


def _try_repair_json(text: str) -> Optional[Dict]:
    """
    尝试修复被截断的 JSON（比如 LLM 输出被 max_tokens 切断）。
    策略：
    1. 找最后一个完整的值位置（逗号或右括号之前）
    2. 截断未完成的部分
    3. 补齐未闭合的括号/引号
    """
    if not text or not text.strip().startswith("{"):
        return None

    s = text.strip()

    # Track bracket depth and string state
    depth_stack = []  # stack of '{' or '['
    in_string = False
    escape = False
    last_safe = -1  # last position where we can safely cut (after , or value)

    for i, ch in enumerate(s):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            if not in_string:
                # Just closed a string — could be a safe cut point
                last_safe = i
            continue
        if in_string:
            continue
        if ch == "{" or ch == "[":
            depth_stack.append(ch)
        elif ch == "}" or ch == "]":
            if depth_stack:
                depth_stack.pop()
                last_safe = i
        elif ch == "," and len(depth_stack) > 0:
            last_safe = i

    if last_safe < 0:
        return None

    # Cut at last_safe
    candidate = s[: last_safe + 1]

    # If we cut at a comma, remove the trailing comma to avoid invalid JSON
    candidate = candidate.rstrip()
    while candidate.endswith(","):
        candidate = candidate[:-1].rstrip()

    # Recompute depth stack for the candidate
    depth_stack = []
    in_string = False
    escape = False
    for ch in candidate:
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"' and not escape:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{" or ch == "[":
            depth_stack.append(ch)
        elif ch == "}" or ch == "]":
            if depth_stack:
                depth_stack.pop()

    # Close any remaining brackets
    for opener in reversed(depth_stack):
        candidate += "}" if opener == "{" else "]"

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


SYSTEM_PROMPT = """你是跨领域结构同构分析专家。你的任务是找到看似无关的现象背后共享的数学结构，并把一个领域的成熟方法翻译到另一个领域。

你的风格：
- 精确，不含糊
- 具体，不抽象
- 有数学严谨性，但用普通人能懂的语言表达
- 从不说废话"""


DEEP_ANALYSIS_SYSTEM_PROMPT = """你是一位资深的跨学科研究助手，专门帮助**专业用户**（研究者、资深产品经理、战略顾问、工程师）把一个领域里陌生的成熟成果迁移到他们自己的问题上。

你的用户是各自领域的专家，但对你要介绍的另一个领域是外行。所以你要同时扮演两个角色：
1. **结构分析师**：用数学/结构语言重新拆解用户熟悉的问题
2. **领域翻译官**：把用户陌生的领域用"专业但可懂"的方式讲清楚

你的产出是一份**结构化的研究报告**，不是对话式回答，不是参数对照表。每一份报告要能直接辅助用户做研究、写方案、或者解决具体问题。

核心原则：
- **精确**：不用含糊的"可能、大概、或许"
- **具体**：宁可举实例也不堆抽象词
- **引用**：提到任何历史人物/论文/理论都说明年份和核心贡献
- **诚实**：不知道的就说不知道；迁移有风险的就明确说
- **专业**：用户是专家，不要过度简化；但遇到另一领域的术语必须解释
- **不说废话**：没有"综上所述"、"希望对你有帮助"这种

你的输出必须是一个严格的 JSON 对象，不要包裹 markdown 代码块。"""


def build_deep_analysis_prompt(a: Dict, b: Dict, similarity: float, user_query: Optional[str] = None) -> str:
    """
    Build the prompt for the deep analysis (8-section research report).

    a = SOURCE domain (KB phenomenon, user is unfamiliar with)
    b = TARGET (either user's query in query mode, or another KB phenomenon)
    user_query = the original user question in query mode (for more natural phrasing)
    """
    is_query_mode = b.get("id") == "__query__"
    target_label = "你的问题" if is_query_mode else f"{b.get('domain', '')} · {b.get('name', '')}"

    user_question_block = ""
    if is_query_mode and user_query:
        user_question_block = f"""

用户的原始问题（这是他在意的、想解决的）：
「{user_query}」

这是一个专业用户。他是自己领域的专家，但对 SOURCE 领域（{a.get('domain', '')}）是外行。
你要做的是：把 SOURCE 领域成熟的东西翻译并迁移到他的问题上。
"""
    elif is_query_mode:
        user_question_block = f"""

用户正在描述一个他在自己领域遇到的问题（TARGET 侧描述就是他的问题）。
他是自己领域的专家，但对 SOURCE 领域（{a.get('domain', '')}）是外行。
"""

    return f"""分析下面两个现象的跨学科结构同构，并生成一份完整的迁移研究报告。

SOURCE（源领域 — 有成熟答案的已知领域）:
名称: {a.get('name', '')}
领域: {a.get('domain', '')}
描述: {a.get('description', '')}

TARGET（目标 — 用户想应用的地方）:
名称: {b.get('name', '')}
领域: {b.get('domain', '')}
描述: {b.get('description', '')}

结构相似度: {similarity:.2f}{user_question_block}

请生成严格符合以下 JSON schema 的结构化报告：

{{
  "shared_structure": {{
    "name": "共享的数学/结构类型名称（中文）",
    "formal_expression": "核心数学表达（LaTeX 格式，不含 $ 符号）",
    "intuition": "用外行话讲清楚这个结构是什么——不要公式，不要术语。3-4 句话，让完全不懂数学的人也能理解为什么这两件事本质上一样。"
  }},

  "your_problem_breakdown": {{
    "summary": "一段话（3-5 句）从结构角度重述 TARGET 的问题。用 TARGET 领域的语言，但强调结构特征。让用户看完说'原来我的问题可以这样看'。",
    "key_variables": [
      {{
        "name": "变量在 TARGET 领域里的名称",
        "description": "它在这个问题中是什么、代表什么",
        "role": "state | parameter | input | constraint | output"
      }}
    ],
    "dynamics": "变量之间如何互动产生用户观察到的现象。2-3 句。",
    "why_stuck": "为什么 TARGET 领域常规的做法解决不了这个问题。这是用户最想知道的——因为他已经试过常规做法了。"
  }},

  "target_domain_intro": {{
    "domain_name": "SOURCE 的学科名称",
    "what_it_studies": "这个学科在研究什么。2-3 句，普通人能懂。包括它的历史地位。",
    "corresponding_phenomenon": {{
      "name": "SOURCE 里对应现象的标准名称",
      "plain_description": "用讲故事的方式描述这个现象。4-6 句。让完全不懂这个学科的人也能看懂并产生直觉。",
      "discovery_history": "这个现象的发现历史和关键节点，具体到年份和人物。"
    }},
    "key_thinkers": [
      {{
        "name": "关键人物姓名",
        "year": "年份",
        "contribution": "他的一句话贡献"
      }}
    ],
    "mature_tools": [
      {{
        "name": "工具/定理/方程/方法的名称",
        "brief": "它在 SOURCE 里解决什么问题。一句话，带数学形式（LaTeX 不含 $）如果有的话。"
      }}
    ]
  }},

  "structural_mapping": {{
    "rationale": "2-3 句说明为什么这两个看似无关的现象在数学层面是同一件事。这是全文的逻辑中枢。",
    "parameter_map": [
      {{
        "source_concept": "SOURCE 中的变量/概念",
        "source_explanation": "这个变量在 SOURCE 中的具体含义（一句话）",
        "target_concept": "TARGET 中的对应变量",
        "target_explanation": "这个变量在 TARGET 中是什么",
        "isomorphism_reason": "为什么它们在结构上对应"
      }}
    ]
  }},

  "borrowable_insights": [
    {{
      "tool": "SOURCE 中的具体工具/方程/方法/原理名称（要能 Google 到、有明确作者或命名，不要'一种启发式'这种模糊指称）",
      "what_it_solves_in_source": "它在 SOURCE 里用来解决什么问题。2-3 句。要讲清楚'没有这个工具之前大家怎么卡住的'和'这个工具解决了什么'。",
      "translated_to_target": "把它翻译到 TARGET 的语境下对应什么——变量一一对应地说清楚，不要泛泛地说'类比地'。2-3 句。",
      "concrete_application": "在用户的具体情况下，这个工具该怎么用。**必须用 markdown 无序列表格式输出，正好 4 个 bullet**，每行以 `- **标签**：` 开头。4 个标签固定为：(a) 数据信号 (b) 参数估计 (c) 判断阈值 (d) 本周动作。示例（保持完全相同的格式）：\\n- **数据信号**：过去 8 周的每日任务完成率，至少 56 个时间点\\n- **参数估计**：用 SciPy 的 curve_fit 拟合 $N(t)=N_0 e^{{-kt}}$，拿到 $k$ 和 95% 置信区间\\n- **判断阈值**：连续 4 周 $k<0.1$ 判定团队进入稳态；$k>0.3$ 触发干预\\n- **本周动作**：把现有数据扔到 Excel 用 LINEST 函数先粗算一遍，看趋势是否符合指数衰减。\\n注意：每个 bullet 内部不要换行，不要嵌套子列表，不要加额外段落。"
    }}
  ],

  "how_to_combine": {{
    "steps": [
      "每一步必须是**可以在今天或本周开始做的物理动作**，不要'思考'、'理解'、'意识到'这类心智活动。每步格式：[动作动词]+[明确对象]+[完成标准]。示例：'收集过去 6 周每日任务完成率数据，至少 42 个样本点，存成 CSV'、'用 SciPy curve_fit 拟合指数模型，拿到 $k$ 和 95% 置信区间'、'设定触发线：若 $k$ 连续 2 周置信区间上界 < 0.05 则启动 B 方案'",
      "具体步骤2（遵循同样的格式）",
      "具体步骤3（遵循同样的格式）"
    ],
    "assumptions_to_verify": [
      "必须是**可证伪的**假设，不要'团队需要更多沟通'这种无法证伪的。示例：'相邻两周完成率残差服从正态分布（用 Shapiro-Wilk 检验，p>0.05 才成立）'",
      "需要验证的假设2"
    ],
    "boundary_conditions": "这个迁移在什么条件下成立、什么条件下会失效。给出至少一个**具体的数值或规模阈值**，比如'团队规模 < 15 人时成立；超过后网络效应主导，需换模型'。"
  }},

  "research_directions": {{
    "literature_status": "已广泛讨论 | 部分探索 | 未有先例 — 选一个最贴切的",
    "status_explanation": "这个跨学科联系在学术界的现状。哪些人做过类似工作。如果'未有先例'，明确说出来。",
    "if_novel_opportunity": "如果是部分探索或未有先例：这可能是什么级别的研究机会。建议的起点（验证路径、合作方向、可能感兴趣的期刊或领域）。如果已广泛讨论，这里填 null。",
    "suggested_references": [
      {{
        "title": "参考文献/书/关键论文",
        "note": "为什么读它"
      }}
    ]
  }},

  "risks_and_limits": [
    {{
      "risk_name": "这种迁移可能失败的一个具体原因",
      "severity": "高 | 中 | 低",
      "explanation": "为什么这个风险存在，在什么条件下会暴露"
    }}
  ],

  "action_plan": {{
    "intro": "1-2 句话告诉用户：基于上面的分析，这是一份精简的执行清单。强调'不要再重复前面的内容，只看这里就能开始做'。",
    "if_time_short": {{
      "title": "如果你只能做一件事——动作标题，6-12 字",
      "rationale": "1 句话说明为什么是这一件最重要（最高杠杆 / 最低成本验证假设 / 不做就没法做后续）"
    }},
    "this_week": [
      {{
        "rank": 1,
        "title": "动作标题（动作动词+对象，6-14 字，例如'拉过去 8 周完成率数据'）",
        "how": "怎么做——2-3 步内说清，不要超过 4 步。每步动词开头，可执行。",
        "verification": "验证指标——用什么数据/数字/信号确认这一步做完且有效。要可量化。",
        "expected_impact": "预期产出——做完之后你会知道什么 / 决定什么 / 改变什么",
        "estimated_time": "估时——例如 '30 min' / '半天' / '本周内 2-3 小时'",
        "category": "diagnostic | intervention | measurement | experiment"
      }}
    ],
    "next_week_followup": "1-2 句话告诉用户下周该回头看什么——例如'拿到 k 值后回到这份报告的 §5，决定要不要触发 B 方案'"
  }}
}}

写作要求（必须全部满足）：
- 所有内容用中文
- `shared_structure.intuition` 必须让一个聪明的非技术用户秒懂
- `your_problem_breakdown` 要让用户感觉"你真的理解了我的问题"
- `target_domain_intro.corresponding_phenomenon.plain_description` 要有叙事感，不要教科书式
- `borrowable_insights` 至少 3 个，每个都要有 `concrete_application`
- `how_to_combine.steps` 必须是可执行的动作，不是"思考一下"这种空话
- `research_directions` 如果是未有先例，要给用户一种"这件事值得做"的判断
- 不说废话，不说"综上所述"
- 严格的 JSON，不要包在 markdown 代码块里

`action_plan` 段（极其重要，这是用户读完后唯一可能记住的东西）：
- `this_week` 必须正好包含 **5 项**——前 3 项 rank 1/2/3 是"必做"，后 2 项 rank 4/5 是"optional"
- 每项的 `title` 严格 6-14 字，动作动词开头（"拉数据"、"拟合"、"设置"、"约谈"、"画图"），禁止"思考"、"理解"、"评估"这类心智动词
- `verification` 必须可量化：数字、阈值、信号、二元判断之一
- `if_time_short` 必须从 `this_week` 的 rank=1 中选出，且 title 完全一致或更精简
- 整段不要重复前 8 段已经说过的话——只输出"明天上班就能干"的清单
- 5 项动作之间要有逻辑序（先收数据→再建模→再设触发线→再干预→再观察），不要 5 个独立无关的事

**数学公式的写法（极重要）：**
- 任何数学表达、公式、变量符号，都必须用 `$...$`（行内）或 `$$...$$`（独立展示）包裹
- 行内例子：每次给药剂量 `$C_0$` 决定峰值浓度；增长率 `$r = dN/dt \\cdot 1/N$`
- 独立展示例子：`$$N(t) = N_0 e^{{-kt}}$$`
- `shared_structure.formal_expression` 字段**例外**：直接写 LaTeX，不要 `$` 符号
- 变量、参数、数学常量都要包。不要写裸的 `\\frac`、`\\partial`
- 纯概念名词（如"承载容量"、"增长率"）不需要包

**JSON 合法性（极重要）：**
- 字符串值内部绝对不能出现未转义的 ASCII 双引号 `"`。如需强调或引用，用中文引号 「」 或 『』，或用单引号 '
- 字符串值内的反斜杠（如 LaTeX 命令 \\frac、\\partial）必须写成双反斜杠 `\\\\frac`
- 换行一律用 `\\n`，不要直接换行
- 每个字段后面必须有逗号（除了最后一个）
- 务必输出可被 `json.loads()` 直接解析的合法 JSON"""
