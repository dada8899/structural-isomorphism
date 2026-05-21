***REMOVED*** Session ***REMOVED***17 — 全项目优化体检

> 调研日期 2026-05-21。覆盖 `web/backend/`（prod 在跑）、`structural_isomorphism/`（核心库）、
> `scripts/`，以及 `v2/ v3/ v4/` 实验目录速扫。问题分级：P0 阻断 / P1 应修 / P2 锦上添花。

***REMOVED******REMOVED*** 统计

- P0 阻断：4（含已修 1）
- P1 应修：8
- P2 锦上添花：12

***REMOVED******REMOVED*** 1. 安全与隐私

| 问题 | 位置 | 级别 | 根因 | 修法 |
|---|---|---|---|---|
| `.env.bak-v1` 带 `OPENROUTER_API_KEY` 进 git，仓库 PUBLIC | `web/backend/.env.bak-v1`（commit `aa044dd`） | P0 | 历史备份未清理，`.gitignore` 只挡 `*.jsonl.bak` 不挡 `.env.bak*` | ✅ session ***REMOVED***17 已 `git rm --cached` + 补 gitignore（commit `3c90bb7`）。**剩余动作（用户）：轮换 OpenRouter key —— 文件曾在公开仓库，key 视为已泄露** |
| 顶层 `.env` 带 `DEEPSEEK_API_KEY` | `.env` | — | （误报）`.gitignore:33` 已忽略，未进 git | 无需处理 |
| `phase-detector/.env.production` 进 git | `web/phase-detector/.env.production` | — | （误报）只含 `NEXT_PUBLIC_*`，按 Next.js 设计本就暴露给浏览器，非密钥 | 无需处理 |
| CORS `allow_headers="*"` 过宽 | `web/backend/main.py:188` | P1 | 便利优先 | 收敛为显式列表 `["Content-Type","X-Anon-Id","X-API-Key"]`（注意必须含真实 fetch 头，见 memory `feedback_cors_allow_headers_must_match_fetch`） |
| 通用异常处理可能泄露内部路径 | `web/backend/api/search.py:124-126` | P1 | `except Exception` 把真错误透出 | 记 log + 对外返回中性 500 文案 |

***REMOVED******REMOVED*** 2. 性能

| 问题 | 位置 | 级别 | 根因 | 修法 |
|---|---|---|---|---|
| 跨域配对 N² 全比对 | `structural_isomorphism/search.py:152-154` | P0 | `find_cross_domain_pairs()` 对 ~5k 知识库做全量两两比对 | 上近似最近邻（faiss `IndexFlatL2` / annoy / LSH），O(N²)→O(N log N) |
| `/api/version` 同步 subprocess | `web/backend/main.py:323-333` | P1 | git rev-parse 在端点内跑 | 已用 `asyncio.to_thread` 包；建议启动时预计算并缓存 |
| 13MB embedding 每次重启全量入内存 | `web/backend/services/search_service.py:140` | P1 | `np.load` 全读 | 改 `mmap_mode='r'` 或共享内存层 |
| 查询缓存无命中率监控 | `search_service.py:132` | P2 | LRU 1024 但无观测 | 命中率打到结构化日志 |

***REMOVED******REMOVED*** 3. 代码质量与重复

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| 地震/数据抓取逻辑跨 v2/v3/v4 三份复制 | `dataset/` + `v3/` + `v4/validation/soc-earthquake/` | P1 | 抽 `lib/data_fetchers/`，三处共用 |
| 两套站点系统并存 | `site/`（136K）vs `site_mkdocs/`（6.2M） | P1 | 确认 `site/` 已废弃则删；`.gitignore` 已忽略两者，物理目录仍在 |
| 后端主文件超长 | `web/backend/main.py`（~1843 行） | P2 | `/phase/*` 路由拆 `api/phase_routes.py` |
| `requirements.txt` 留过时降级注释 | `web/backend/requirements.txt:7-11` | P1 | 清理 v2.5.0 历史注释，写清当前 5.4+ 的原因 |
| 分享条 section 投票会改写「整体」计数器 | `analyze.js:898-902` `submitFeedback` | P2 | section 投票成功后无条件同步 `analyze-vote-*-count`（整体计数器），UI 语义错位；应只在 `section===''` 时同步 |

***REMOVED******REMOVED*** 4. 工程债

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| TODO 散落未追踪 | `scripts/newsletter_data_sources.py:53` 等 | P2 | 收口到 issue 或 NEXT_SESSION.md |
| `setup.py` 依赖版本过松 | `setup.py:18-26` | P2 | `sentence-transformers>=5.4.0,<6` 对齐后端 |
| `perf-budget.json` 未接 CI | 根目录 | P2 | `perf_check_budget.py` 加入 GitHub Actions |
| `fingerprint` 脚本 docs-only commit 误报 | `scripts/dogfood_fingerprint.py` | P2 | git_sha 精确比对，docs 提交也判 mismatch；建议比对「最近一个非 docs commit」或忽略 docs-only diff |

***REMOVED******REMOVED*** 5. 文档与结构

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| README 路径与实际有出入 | `README.md:31` | P2 | 补最新路径示例 |
| `docs/` 52 个 md 无总索引 | `docs/` | P2 | 建 `docs/INDEX.md` |
| 两份 `.env.example` 不同步 | 顶层 vs `web/backend/` | P2 | 统一 |

***REMOVED******REMOVED*** Top 5（只修 5 个，修这些）

1. **轮换 OpenRouter API key**（P0，用户动作）—— `.env.bak-v1` 已在公开仓库泄露，文件本身已 untrack（`3c90bb7`），但 key 必须在 OpenRouter 控制台轮换。可选：`git filter-repo` 清历史 + force-push（不可逆，需用户拍板；key 一旦公开过，轮换才是真解，清历史是次要）。
2. **N² 跨域配对换近似最近邻**（P0，性能）—— 知识库再涨就会超时，faiss 一次性解决。
3. **CORS `allow_headers` 收敛**（P1，安全）—— 显式列真实 fetch 头。
4. **统一三份数据抓取逻辑**（P1，维护）—— 抽 `lib/data_fetchers/`。
5. **去重 `site/` vs `site_mkdocs/`**（P1，清理）—— 确认废弃后删 `site/`。

***REMOVED******REMOVED*** 既有优点

Pydantic schema 覆盖 API 层 / structlog 结构化日志 + correlation id / e2e 测试体系完善（session ***REMOVED***17 后 14 个 M1.4 e2e）/ 生产 CORS origin 白名单 / async 实践规范 / 模型版本有文档。
