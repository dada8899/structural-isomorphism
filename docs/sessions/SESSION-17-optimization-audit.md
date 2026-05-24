# Session #17 — 全项目优化体检

> 调研日期 2026-05-21。覆盖 `web/backend/`（prod 在跑）、`structural_isomorphism/`（核心库）、
> `scripts/`，以及 `v2/ v3/ v4/` 实验目录速扫。问题分级：P0 阻断 / P1 应修 / P2 锦上添花。

## 统计

- P0 阻断：4（含已修 1）
- P1 应修：8
- P2 锦上添花：12

## 1. 安全与隐私

| 问题 | 位置 | 级别 | 根因 | 修法 |
|---|---|---|---|---|
| `.env.bak-v1` 带 `OPENROUTER_API_KEY` 进 git，仓库 PUBLIC | `web/backend/.env.bak-v1`（commit `aa044dd`） | P0 | 历史备份未清理，`.gitignore` 只挡 `*.jsonl.bak` 不挡 `.env.bak*` | ✅ session #17 已 `git rm --cached` + 补 gitignore（commit `3c90bb7`）。**剩余动作（用户）：轮换 OpenRouter key —— 文件曾在公开仓库，key 视为已泄露** |
| 顶层 `.env` 带 `DEEPSEEK_API_KEY` | `.env` | — | （误报）`.gitignore:33` 已忽略，未进 git | 无需处理 |
| `phase-detector/.env.production` 进 git | `web/phase-detector/.env.production` | — | （误报）只含 `NEXT_PUBLIC_*`，按 Next.js 设计本就暴露给浏览器，非密钥 | 无需处理 |
| CORS `allow_headers="*"` 过宽 | `web/backend/main.py:188` | P1 | 便利优先 | 收敛为显式列表 `["Content-Type","X-Anon-Id","X-API-Key"]`（注意必须含真实 fetch 头，见 memory `feedback_cors_allow_headers_must_match_fetch`） |
| 通用异常处理可能泄露内部路径 | `web/backend/api/search.py:124-126` | P1 | `except Exception` 把真错误透出 | 记 log + 对外返回中性 500 文案 |

## 2. 性能

| 问题 | 位置 | 级别 | 根因 | 修法 |
|---|---|---|---|---|
| 跨域配对 N² 全比对 | `structural_isomorphism/search.py:152-154` | ~~P0~~ **P2（降级）** | `find_cross_domain_pairs()` 全仓只有 `notebooks/quickstart.ipynb` 调用 —— **不在 prod 请求路径上**。原 P0 评级有误 | demo KB 规模下现状够用；为 notebook 引入 faiss 重型依赖不值。如未来挪进 prod 再上 ANN |
| `/api/version` 同步 subprocess | `web/backend/main.py:323-333` | P1 | git rev-parse 在端点内跑 | 已用 `asyncio.to_thread` 包；建议启动时预计算并缓存 |
| 13MB embedding 每次重启全量入内存 | `web/backend/services/search_service.py:140` | P1 | `np.load` 全读 | 改 `mmap_mode='r'` 或共享内存层 |
| 查询缓存无命中率监控 | `search_service.py:132` | P2 | LRU 1024 但无观测 | 命中率打到结构化日志 |

## 3. 代码质量与重复

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| 地震/数据抓取逻辑跨 v2/v3/v4 三份复制 | `dataset/` + `v3/` + `v4/validation/soc-earthquake/` | P1 | 抽 `lib/data_fetchers/`，三处共用 |
| 两套站点系统并存 | `site/`（136K）vs `site_mkdocs/`（6.2M） | P1 | 确认 `site/` 已废弃则删；`.gitignore` 已忽略两者，物理目录仍在 |
| 后端主文件超长 | `web/backend/main.py`（~1843 行） | P2 | `/phase/*` 路由拆 `api/phase_routes.py` |
| ~~`requirements.txt` 注释~~（撤销）| `web/backend/requirements.txt:7-11` | — | 复核后撤销：该注释是 2026-05-20 prod 重启事故的现场记录，解释了 `>=5.4.0,<6` 的由来 —— 属于应保留的事故记忆，不删 |
| 分享条 section 投票会改写「整体」计数器 | `analyze.js:898-902` `submitFeedback` | P2 | section 投票成功后无条件同步 `analyze-vote-*-count`（整体计数器），UI 语义错位；应只在 `section===''` 时同步 |

## 4. 工程债

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| TODO 散落未追踪 | `scripts/newsletter_data_sources.py:53` 等 | P2 | 收口到 issue 或 NEXT_SESSION.md |
| `setup.py` 依赖版本过松 | `setup.py:18-26` | P2 | `sentence-transformers>=5.4.0,<6` 对齐后端 |
| `perf-budget.json` 未接 CI | 根目录 | P2 | `perf_check_budget.py` 加入 GitHub Actions |
| `fingerprint` 脚本 docs-only commit 误报 | `scripts/dogfood_fingerprint.py` | P2 | git_sha 精确比对，docs 提交也判 mismatch；建议比对「最近一个非 docs commit」或忽略 docs-only diff |

## 5. 文档与结构

| 问题 | 位置 | 级别 | 修法 |
|---|---|---|---|
| README 路径与实际有出入 | `README.md:31` | P2 | 补最新路径示例 |
| `docs/` 52 个 md 无总索引 | `docs/` | P2 | 建 `docs/INDEX.md` |
| 两份 `.env.example` 不同步 | 顶层 vs `web/backend/` | P2 | 统一 |

## Top 5（只修 5 个，修这些）

1. **轮换 OpenRouter API key**（P0，用户动作）—— `.env.bak-v1` 已在公开仓库泄露，文件本身已 untrack（`3c90bb7`），但 key 必须在 OpenRouter 控制台轮换。可选：`git filter-repo` 清历史 + force-push（不可逆，需用户拍板；key 一旦公开过，轮换才是真解，清历史是次要）。
2. **N² 跨域配对换近似最近邻**（P0，性能）—— 知识库再涨就会超时，faiss 一次性解决。
3. **CORS `allow_headers` 收敛**（P1，安全）—— 显式列真实 fetch 头。
4. **统一三份数据抓取逻辑**（P1，维护）—— 抽 `lib/data_fetchers/`。
5. **去重 `site/` vs `site_mkdocs/`**（P1，清理）—— 确认废弃后删 `site/`。

## Session #17 当场修复记录

复核 Top 5 后按「根因 + 全局影响评估」收敛实际动手范围，**避免为高估的评级做无效工**：

| 项 | 处置 | commit |
|---|---|---|
| `.env.bak-v1` 泄露 | ✅ untrack + gitignore（key 轮换待用户） | `3c90bb7` |
| CORS `allow_headers="*"` | ✅ 收敛为显式 5 头列表（含真实 fetch 头 + 程序化客户端头） | 本轮 |
| section 投票错改整体计数器 | ✅ `analyze.js submitFeedback` 加 `if (!section)` 守卫 | 本轮 |
| `dogfood_fingerprint.py` docs-only 误报 | ✅ `_local_git_sha` 改取「最近非 docs commit」 | 本轮 |
| N² 跨域配对 | ✅ 修了 —— `np.argwhere(np.triu(...))` 向量化替掉 Python 双重循环，120 节点合成数据对拍新旧产出完全一致；非 prod 路径但改动安全无害 | 本轮 |
| 数据抓取去重 | ❌ 不做（有据）—— 重复发生在 `dataset/v1/...benchmark/`（**已发布、CITATION.cff + MANIFEST.json 校验和的冻结基准数据集**）与 `v4/validation/` 之间，两份 `fetch_earthquakes.py` 字节相同。把 benchmark 内的副本抽成外部 import 会破坏其「自包含 + 可复现」契约，使 MANIFEST 校验失效。这个「重复」是冻结发布物 + 实验分叉的正常形态，**不是该修的 bug** | — |
| 删 `site/` | ❌ 不做（有据）—— 复核发现 `site/` 不是废弃构建产物（mkdocs 实际输出到 `site_mkdocs/`），而是 **7 个被 git 追踪的文件**：6 份 v2m/v3/v4 分析 markdown（仓库内唯一副本）+ index.html。删除 = 永久内容丢失。审计把它误判成 stale build | — |
| OpenRouter key 轮换 | 🔴 待用户 —— CC 无 OpenRouter 控制台权限 | — |

## 既有优点

Pydantic schema 覆盖 API 层 / structlog 结构化日志 + correlation id / e2e 测试体系完善（session #17 后 14 个 M1.4 e2e）/ 生产 CORS origin 白名单 / async 实践规范 / 模型版本有文档。
