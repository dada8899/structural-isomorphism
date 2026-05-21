***REMOVED*** SESSION-17 — 发布前技术健壮性与上线就绪审查

> 角色：资深 SRE / 上线工程师
> 日期：2026-05-21
> 范围：web/backend (FastAPI) + web/frontend（静态）+ 线上 beta https://beta.structural.bytedance.city/
> 方法：读代码 + curl 实测线上 beta
> 关联：本 session 已有 SESSION-17-optimization-audit.md（性能/优化视角），本报告为「上线就绪度」视角，不重复其结论。

---

***REMOVED******REMOVED*** 一句话总评

**技术上「谨慎可发布」** —— 错误处理框架（RFC 7807）、CORS 收敛、输入校验、可观测性（structlog + correlation ID + 健康/版本探针）这些基础设施做得相当扎实，明显高于「半成品」水准。但有 **2 个 P0 必须发布前修**（缺安全响应头、LLM 成本无每日上限），以及一组 P1（限流形同虚设、错误信息泄露、缺隐私政策页）。修完 P0 + 限流后即可对外 beta 发布。

***REMOVED******REMOVED*** 计数

| 严重度 | 数量 |
|--------|------|
| **P0（阻断发布）** | 2 |
| **P1（应修）** | 7 |
| **P2（打磨）** | 6 |

***REMOVED******REMOVED*** Top 风险（按优先级）

1. **LLM 成本无每日预算上限** —— `BudgetExceeded` 异常类已定义却从未被 raise，匿名用户可无限触发 `/api/ask` `/api/analyze`，单次调用 Claude Sonnet 4.6 / DeepSeek 真金白银。配合下条限流失效 = 钱包敞口。
2. **限流对昂贵端点形同虚设** —— `/api/ask/stream` 实测连发 9 次有效请求全部 200，文档声称 5/min。根因见 P1-1：tier 名不匹配导致 `default_anon` 永不生效。
3. **完全没有安全响应头** —— 无 HSTS / X-Frame-Options / X-Content-Type-Options / CSP / Referrer-Policy。点击劫持、MIME 嗅探、降级攻击全部敞开。

---

***REMOVED******REMOVED*** P0 — 阻断发布

***REMOVED******REMOVED******REMOVED*** P0-1 完全缺失安全响应头
- **位置**：nginx 配置（VPS `/etc/nginx/`）/ 或 FastAPI 中间件
- **复现**：`curl -sI https://beta.structural.bytedance.city/` —— 响应中无 `Strict-Transport-Security`、`X-Frame-Options`、`X-Content-Type-Options`、`Content-Security-Policy`、`Referrer-Policy` 任何一个。
- **影响**：页面可被任意站点 `<iframe>` 嵌入做点击劫持；MIME 嗅探可把用户上传/接口响应当脚本执行；无 HSTS 则首访可被 SSL 剥离降级。
- **修法**：在 nginx server 块加（最省事，全站统一）：
  ```nginx
  add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://plausible.bytedance.city https://cdn.jsdelivr.net 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://plausible.bytedance.city" always;
  ```
  CSP 需按实际外链资源（Plausible、jsdelivr 的 swagger-ui）微调，建议先用 `Content-Security-Policy-Report-Only` 跑一周再切强制。

***REMOVED******REMOVED******REMOVED*** P0-2 LLM 端点无每日成本上限（钱包敞口）
- **位置**：`web/backend/api/ask.py`、`api/analyze.py`、`services/ask_orchestrator.py`
- **复现**：代码里 `errors.py` 定义了 `BudgetExceeded` 类，但 `grep -rn "BudgetExceeded" api/ services/` 在业务代码里**零引用**——从未 raise。匿名用户可不断 POST `/api/ask/stream`，每次都真实调用 OpenRouter（Claude Sonnet 4.6）。
- **影响**：恶意脚本或意外爬虫一夜之间可烧掉数百美元 LLM 费用，无任何熔断。对外公开 beta 后这是最现实的事故。
- **修法**：发布前至少加一道粗粒度闸：
  1. 进程级 / Redis 计数器：当日 LLM 调用总次数或累计 token 超阈值 → `raise BudgetExceeded(...)`（类已现成）。
  2. 或先用 OpenRouter 账户侧的硬性消费上限 + 告警兜底（最快，当天可上）。
  3. 中期：按 `anon_id` / IP 做每日配额。

---

***REMOVED******REMOVED*** P1 — 应修

***REMOVED******REMOVED******REMOVED*** P1-1 限流对昂贵端点失效（tier 名不匹配）
- **位置**：`web/backend/services/rate_limit.py` `tier_limit_decorator._resolve_spec()` vs `middleware/rate_limit.py` `TierResolutionMiddleware`
- **根因**：`tier_limit_decorator(default_anon="5/minute")` 里，`default_anon` 这个 per-endpoint 限流值**只在 `tier == "anonymous"` 时返回**。但 `TierResolutionMiddleware` 给匿名请求设的 `CURRENT_TIER` 是 `"free"`，从不是 `"anonymous"`。于是匿名流量走 `free` 分支 → `60/minute`，且 `/api/ask` 不在 decorator 的昂贵端点减半逻辑里（减半只在 middleware 的 `_resolve_limit_spec` 中，那条路径根本没接到这些 endpoint）。
- **复现**：连发 9 次 `POST /api/ask/stream`（有效 body），全部 200，未出现 429。预期应在第 6 次 429。
- **影响**：文档与代码注释声称 `/api/ask` 5/min、`/api/analyze` 10/min 的保护实际是 60/min。直接放大 P0-2 的成本敞口。
- **修法**：`_resolve_spec()` 里把 `free` 也走 `default_anon` 分支（匿名 = free，二者应等价）；或 `TierResolutionMiddleware` 对匿名请求设 `"anonymous"`。两套限流模块（`services/rate_limit.py` 旧 + `middleware/rate_limit.py` 新）并存本身是债，建议合并为一套。

***REMOVED******REMOVED******REMOVED*** P1-2 LLM 失败时原始异常字符串直接回显给用户
- **位置**：`services/ask_orchestrator.py:982` `yield ("error", str(e))`；前端 `web/frontend/assets/js/ask.js:451` `showError(item, data.message ...)`
- **复现**：当 OpenRouter 超时 / 5xx / 网络错误，`str(e)`（httpx 异常文本，可能含上游 URL、超时秒数、连接细节）作为 SSE `error` 事件的 `message` 原样送到前端并显示。
- **影响**：对外泄露内部依赖与基础设施细节；用户看到的是英文技术报错而非友好文案。
- **修法**：orchestrator 里把异常分类映射成稳定错误码（`upstream_timeout` / `upstream_error` / `no_api_key`），只 yield 错误码；完整 `str(e)` 仅 `logger.error`。前端按错误码查本地化文案。注：`errors.py` 对 HTTP 端点已做得很好（DEBUG 关时只回 "An internal error occurred"），但 SSE 流内的错误绕过了这层，需单独补。

***REMOVED******REMOVED******REMOVED*** P1-3 缺隐私政策页面（合规）
- **位置**：`web/frontend/` 无 `privacy.html`；`/privacy` 与 `/privacy.html` 实测均 404。
- **复现**：`curl -o /dev/null -w "%{http_code}" https://beta.structural.bytedance.city/privacy` → 404。
- **影响**：后端已实现 `/api/privacy/export` 和 `/api/privacy/delete`（GDPR 数据导出/删除接口，做得好），但前端没有任何隐私政策页面或入口，用户不知道收集了什么、怎么行使删除权。对外发布的合规缺口。
- **修法**：加一个静态 `privacy.html`，说明：收集 anon-id（localStorage）、查询历史、Plausible 匿名统计（无 cookie）、newsletter email；并给出 `/api/privacy/delete` 的用户可达入口（设置页一个「删除我的数据」按钮）。页脚加链接。
- **注**：Plausible 是 cookieless、不需 cookie 同意横幅，这点不算缺陷；但隐私政策页仍是必需。

***REMOVED******REMOVED******REMOVED*** P1-4 `/docs` 与 `/openapi.json` 在 prod 公开可访问
- **位置**：`main.py` —— FastAPI 默认开放 `/docs` `/redoc` `/openapi.json`，未在 prod 关闭。
- **复现**：`curl -o /dev/null -w "%{http_code}" https://beta.structural.bytedance.city/docs` → 200；`/openapi.json` → 200。
- **影响**：完整 API 表面（含 `/api/admin/*`、内部端点结构、参数）对外暴露，给攻击者递了地图。虽非直接漏洞，但扩大攻击面。
- **修法**：`STRUCTURAL_ENV=prod` 时 `FastAPI(docs_url=None, redoc_url=None, openapi_url=None)`，或用 admin tier 鉴权包一层。OpenAPI 仍可在 CI 导出到 `docs/api/openapi.json` 供内部用。

***REMOVED******REMOVED******REMOVED*** P1-5 API 错误响应格式不统一（部分非 RFC 7807）
- **位置**：路由未匹配时的 Starlette 默认 404
- **复现**：`curl https://beta.structural.bytedance.city/api/report/r_deadbeef00000000` → `{"detail":"not found"}`（小写、无 envelope）；而 `/api/ask/stream` 校验失败返回标准 `application/problem+json`。
- **影响**：前端要处理两套错误结构；`{"detail":...}` 是 Starlette 路由层 404（id 长度不匹配路由），未经 `errors.py` 的 handler。
- **修法**：`errors.py` 的 `StarletteHTTPException` handler 已能转换——确认它对「无匹配路由」的 404 也生效（Starlette 的 404 可能在 handler 注册前触发）。或加一个 catch-all 路由统一兜底。

***REMOVED******REMOVED******REMOVED*** P1-6 `HEAD /` 返回 405
- **位置**：`main.py:432` `@app.get("/")`，未声明 `HEAD`。
- **复现**：`curl -I https://beta.structural.bytedance.city/` → `HTTP/2 405`。
- **影响**：很多健康检查器、CDN、爬虫用 HEAD 探活，405 会被误判为站点异常。
- **修法**：根路由与主要页面路由加 `methods=["GET", "HEAD"]`，或用 `@app.api_route("/", methods=["GET","HEAD"])`。

***REMOVED******REMOVED******REMOVED*** P1-7 robots.txt 允许搜索引擎收录 beta 站
- **位置**：`main.py` robots.txt 端点 / 静态 `robots.txt`
- **复现**：`curl https://beta.structural.bytedance.city/robots.txt` → `User-agent: * / Allow: /`。
- **影响**：beta（未定稿）内容会被 Google 收录，将来正式域名 `structural.bytedance.city` 上线会与 beta 形成重复内容、稀释 SEO 权重。
- **修法**：beta 子域 robots 应 `Disallow: /`，并在 beta 页面加 `<meta name="robots" content="noindex">`；正式域名再放开。

---

***REMOVED******REMOVED*** P2 — 打磨

***REMOVED******REMOVED******REMOVED*** P2-1 OG 图片用相对路径
- `index.html` `<meta property="og:image" content="/assets/og-image.png">` —— OG/Twitter 卡片要求**绝对 URL**，相对路径在微信/Twitter/Slack 抓取时不显示图。改为 `https://beta.structural.bytedance.city/assets/og-image.png`。

***REMOVED******REMOVED******REMOVED*** P2-2 缺结构化数据（JSON-LD）
- 无 `Organization` / `WebSite` / `SoftwareApplication` schema.org 标记。加 JSON-LD 有利于搜索结果富摘要。非阻断。

***REMOVED******REMOVED******REMOVED*** P2-3 `/api/version` 在 `STRUCTURAL_GIT_SHA` 未设时 fork `git` 子进程
- `main.py:329` 兜底跑 `git rev-parse`。prod 实测已通过 `.env.runtime` 注入 SHA（返回 `8f10d388c799`），所以当前不触发；但若部署脚本漏写 `.env.runtime`，每次 `/api/version` 会 fork 进程。建议 prod 缺失时直接返回 `"unknown"`，不 fork。

***REMOVED******REMOVED******REMOVED*** P2-4 无 favicon / apple-touch-icon 检查项
- 建议确认 `favicon.ico`、`apple-touch-icon.png`、`og-image.png` 实际存在且尺寸正确（OG 图建议 1200×630）。

***REMOVED******REMOVED******REMOVED*** P2-5 错误上报端点自身的滥用面
- `/api/error_log` 限 10/min/session、10MB rotated jsonl —— 设计合理。但 session 标识若来自客户端可伪造的 header，攻击者可绕开。建议确认限流 key 是否含 IP。

***REMOVED******REMOVED******REMOVED*** P2-6 `phase/*` 端点用 `urllib` 同步阻塞调用 + `include_in_schema=False`
- `main.py` 里 `/phase/api/redteam`、`/deep-report` 等用同步 `urllib.request.urlopen(timeout=120/180)`，在 async 路由里会**阻塞事件循环**最长 180s。虽然 `phase` 是独立子产品、`include_in_schema=False`，但只要路由挂在同一个 app 上，一个 phase 长请求会拖垮整个 Structural 站的并发。建议改 `httpx.AsyncClient` 或 `run_in_threadpool`，或把 phase 拆成独立进程。

---

***REMOVED******REMOVED*** 做得好的地方（值得保留）

- **RFC 7807 错误框架**（`errors.py`）：HTTP 端点的错误响应统一、结构化，DEBUG 关闭时不泄露 traceback——专业水准。
- **CORS 收敛正确**：`allow_origins` 白名单 + `allow_credentials=False`，实测 evil.com 预检不回 `Access-Control-Allow-Origin`，浏览器会正确拦截。`allow_headers` 显式列举而非 `*`。
- **可观测性**：structlog JSON 行日志 + correlation ID（`X-Request-ID` 实测有回显）+ `/api/health?deep=1` 深度探针 + `/api/version` 版本指纹（git SHA / 部署时间 / 模型）。运维友好。
- **分享 token**：HMAC-SHA256 + `secrets` 生成 + `hmac.compare_digest` 常量时间比较 + prod 强制 `STRUCTURAL_SHARE_TOKEN_SECRET` env（缺失直接 raise，不静默降级）。设计正确。
- **输入校验**：pydantic schema + 8000 字符上限 + 结构化 `input_too_long` 错误。HTML 注入实测被当普通文本处理（前端有 `esc()` 转义），无 XSS。
- **报告越权**：`/api/report/{id}` owner 不匹配返回 404 而非 403，不泄露资源存在性——正确做法。
- **`.env` 已 gitignore 且未被 git 跟踪**（实测 `git ls-files` 无 `.env`）。
- **优雅降级**：LLM 流水线失败时走 `_fallback_payload`，不是直接 500。
- **静态资源**：assets 已启用 brotli 压缩，有 etag。

> 注意：本地 `.env` 文件含真实 `DEEPSEEK_API_KEY`（明文）。文件本身未入库是对的，但提醒不要在截图/日志/对话里复述该 key；建议确认 prod 与本地用不同 key，且该 key 仅用于本地脚本（线上走 OpenRouter）。

---

***REMOVED******REMOVED*** 发布前最小行动清单

| ***REMOVED*** | 项 | 严重度 | 工作量 |
|---|----|--------|--------|
| 1 | nginx 加 5 个安全响应头（HSTS/XFO/XCTO/Referrer/CSP-Report-Only） | P0 | 30 min |
| 2 | LLM 调用加每日总量熔断 + OpenRouter 账户消费上限兜底 | P0 | 2 h |
| 3 | 修 `tier_limit_decorator` 的 free/anonymous 分支，让 5/min 真生效 | P1 | 1 h |
| 4 | SSE `error` 事件改回错误码，不回显 `str(e)` | P1 | 1 h |
| 5 | 加 `privacy.html` + 页脚链接 + 删除数据入口 | P1 | 2 h |
| 6 | prod 关闭 `/docs` `/openapi.json` | P1 | 15 min |
| 7 | beta robots `Disallow: /` + `noindex` | P1 | 15 min |
| 8 | 根路由支持 HEAD | P1 | 15 min |

完成 1–8 后技术上「敢发布」beta。P2 项可上线后迭代。
