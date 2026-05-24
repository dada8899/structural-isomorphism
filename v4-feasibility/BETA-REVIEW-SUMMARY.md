# Beta 站综合审查报告

**站点**: https://beta.structural.bytedance.city  
**审查日期**: 2026-04-14  
**审查维度**: 7（API / 后端代码 / 文案 / 数据质量 / 视觉设计 / 浏览器功能 / 产品体验）  
**审查 agent**: 7 个 Opus 4.6 独立并行

---

## 一句话总结

**Beta 站结构完整、代码规整，但一堆 P0/P1 问题让它"内部可用，不能公开"**——主要问题是**延迟 17 秒 + 文案陈旧 + 数据质量偏弱 + 7 页 footer 全不一样**。

---

## 所有 P0 严重问题（必修，共 8 个）

| # | 类别 | 问题 | 影响 | 推荐修复 |
|---|---|---|---|---|
| **1** | 数据质量 | 搜索 **avg relevance 2.38/5**，延迟反馈 / 流言传播 / superconductor 几乎零命中 | 核心功能不可用 | 重新 encode + 概念扩展 + domain-collapse 守卫 |
| **2** | API 性能 | **搜索 latency 5-18 秒**，首页 headline 查询 17.7s | 用户以为站点挂了 | LLM 评估异步化；返回结果后再 stream 评分 |
| **3** | 浏览器功能 | `/api/daily` 返回的 3 对现象 `id` 全为空 | 首页"今日推荐"卡片点击死链 | 修 daily.py 返回 ID |
| **4** | 文案 | **所有页面"19 A 级"硬编码，API 已返回 39（V2+V3 合并）** | 数字不一致伤信任 | 一处改完全站 |
| **5** | 文案 | **现象总数 4475（硬编码）vs API 4443（真实）** — 3 处 | 数字不一致 | 从 API 读取 |
| **6** | 产品体验 | **首页 demo query "团队规模变大后效率下降" 返回语言学/天体力学** | First impression death | 换成已验证可工作的示例 |
| **7** | 浏览器 | `/phenomenon/fake-id` 返回 200 + 空页面 | SPA 路由 bug | 404 fallback |
| **8** | 视觉 | `/phenomenon`（无 ID）**白屏** | 直接破 | 重定向到 `/` 或加空状态 |

## 重要 P1（应修，共 15 个）

### 性能 / 后端
- `main.py:38` + `search_service.py:28` 默认 `kb_file="kb-5000-merged.jsonl"`（V1）—— `.env` 丢失就回滚到 V1
- `llm_service.py:174` 硬编码 `claude-haiku-4.5`，绕过 `LLM_MODEL` env
- `llm_service.py` 每次请求新建 `httpx.AsyncClient`（4 处），无连接池
- `mapping.py:71-72,102-103` O(N) id→index 线性扫描，4443 KB 每次请求都跑
- `examples.py` 每次首页加载跑 6 次 embedding 搜索（本该启动时缓存）
- `search_service.py:107` 同步 `encode_texts` 阻塞 event loop 100-500ms
- 查询 embedding 从不缓存

### 安全
- **CORS `allow_origins=["*"]` + `allow_credentials=True`**（无效组合）
- **无 rate limiting** — `/analyze/stream` 一次烧 16K Sonnet tokens × 300s
- `synthesize.py` prompt injection 风险：客户端提供的 `results[].name` 直接插入 Haiku prompt

### 数据/API
- `similarity` 字段在 daily/mapping/analyze 不一致：有的返回原始 dot product (`9.5258`)，有的 0-1 浮点
- `/api/*` 404 handler 返回 60 行 HTML 404 页面（应返回 JSON）
- `/api/synthesize` 23s 无缓存（mapping 有缓存）
- 垃圾查询 `!@#$%^&*()_+` 返回 5 个分数 8.9-9.5 的"结果"（无 score floor）

### 文案/品牌
- `analyze.html` OG image 返回 **HTTP 404**
- `about.html` v0.1 vs `discoveries.html` V2 管道 vs `index.html` "V2" — 版本叙述前后矛盾
- 5/7 页面无 meta description
- 无 favicon（全站）
- **6 个页面 footer 链接集合全不一样**
- 无"beta"标识（子域名是 beta 但站内不说）
- 无到主站 `structural.bytedance.city` 的反向链接
- HuggingFace / Zenodo / 具体 GitHub repo 零链接

### 视觉
- `/search` 有 80+ 行"sticky re-search bar"死 CSS，从未渲染 → 用户无法重新查询
- 移动端"深度分析"按钮溢出 44px 方框
- `home__lede` / `how-step__time` 对比度 **2.8:1**（不过 WCAG AA）
- `analyze.html` 内联 70 行 CSS（有注释说"analyze.css is off-limits"—— 代码异味）
- `disc-hero__title` 88px 衬体字 `ls -0.03em` 导致中文字符碰撞

## P2 打磨项（~20 个，见分报告）

---

## 每个 agent 的判决

| Agent | 核心判决 |
|---|---|
| **API** | 11 端点全跑通，无 500。3 个 P1：latency、similarity 归一化、404 handler |
| **后端代码** | 代码规整，结构思路清晰。但 3 类风险：CORS + 无 rate limiting + V1 残留默认值 |
| **文案** | 5 个 P0 陈旧数字 + OG image 404 + "4475" / "19 A 级" 和后端数据不一致 |
| **数据质量** | **avg relevance 2.38 / 5（低）**，avg latency 6.45s（P0），"延迟反馈" 等关键查询返回垃圾 |
| **视觉设计** | Token layer 做得好（Linear/Perplexity 水准），但死 CSS 和 footer 不一致泄露工匠缺席 |
| **浏览器功能** | 8 路由全加载，/daily id 空是最大 bug，17s 延迟是最大 UX 悬崖 |
| **产品体验** | **"不能公开分享，内部可用"**。再打磨 1 周可上线 |

---

## 优先级排序（按修复 ROI）

### 🔴 今天/明天（P0，<1 天修完所有 8 个）

1. **修 daily API 的空 id**（`daily.py`, ~5 行）
2. **文案统一**：4475 → 4443, "19 A 级" → "39 A 级", v0.1 → V2+V3, 移除"团队规模变大..."示例（全局查找替换, ~10 处）
3. **修 404 handler**：`/api/*` 返回 JSON 而不是 HTML 页面（~10 行）
4. **修 `/phenomenon` 白屏**：无 ID 时重定向到 `/`（~3 行）
5. **修 `/phenomenon/{fake-id}` 路由**：API 404 → 前端 404 页面（~5 行）
6. **删掉 demo query "团队规模变大"**，换 "为什么市场崩盘" 或 "延迟反馈"（已验证召回好）

### 🟡 本周（P1 精选，~1-2 天）

7. **latency 砍半**：把 LLM assessment 从搜索路径异步化
   - 先返回 retrieval 结果（<1s）
   - SSE stream 评分和 coaching
   - 预期 latency 从 6.5s → 0.8s
8. **召回质量**：为 "延迟反馈 / 流言 / 相变" 等核心词加 concept expansion（LLM 查询改写）
9. **Rate limiting**：`/analyze/stream` 和 `/synthesize` 加限流（10 req/min per IP）
10. **CORS 紧**：`allow_origins` 限定到本站 + GitHub Pages（如有）
11. **统一 header/footer partial**：防止 6 页 footer 全不同
12. **加 favicon + og-image**（30 分钟美工）
13. **Homepage 加"V3 is here"banner**：链接到 v3-full-run 文档

### 🟢 下周（P2 打磨）

14. 视觉设计系统 token 化所有硬编码像素
15. 移动端按钮 label 修正
16. 对比度提升到 4.5:1
17. 移除 `/search` 死 CSS + 正确实现 sticky re-search bar
18. 主站反向链接 + HuggingFace + Zenodo + 具体 GitHub repo 链接

---

## 结论

- **Beta 站现状**：MVP 级别，**不能公开**，但**可以内部用**
- **核心阻塞**：(1) 17s 搜索延迟 (2) avg relevance 2.38（需要 concept expansion）(3) 文案数字全错
- **预计上线时间**：**1 周**集中修 P0 + 精选 P1，可以公开 soft launch
- **长期提升**：re-encode 知识库、训练更好的召回模型、加入 LLM pairwise rerank
- **风险**：目前 V3 的实际研究价值（20 个 A 级发现）在 beta 上几乎**看不到**——首页 banner 必须调整

## 7 份详细分报告文件

- `v4-feasibility/beta-review-api.md` (76 行)
- `v4-feasibility/beta-review-backend.md` (110 行)
- `v4-feasibility/beta-review-browser.md` (95 行)
- `v4-feasibility/beta-review-copy.md` (62 行)
- `v4-feasibility/beta-review-data.md` (66 行)
- `v4-feasibility/beta-review-product.md` (88 行)
- `v4-feasibility/beta-review-visual.md` (184 行)
- `v4-feasibility/BETA-REVIEW-SUMMARY.md` (本文件)
