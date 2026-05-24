# Session #20 Handoff

> 日期：2026-05-22 ~ 05-23
> 承接 SESSION-19-HANDOFF.md（当时站点 502）。
> 本 session 从修 502 起手，做到全项目审查 + 4 个 roadmap 大项落地。
> **站点健康，无 P0 阻塞。** 起手第一件事见 §6。

---

## 0. 当前状态

- `beta.structural.bytedance.city` 健康（health 200），生产环境正常。
- 后端 713 测试全过；post_deploy e2e 22 个全过；MCP 23 测试全过。
- 本 session 12 个 commit 全部 push 到 `origin/main`。前端改动已部署，
  live `git_sha` = `4afd443`（之后的 commit 均为 docs/v4 研究产物，不需部署）。
- working tree 仅剩 `scripts/train_v2.py`（非本 session lineage，按 commit
  边界铁律未动，与 #19 一致）。

---

## 1. 修复 502（commit 50fa312）

**根因**（与 SESSION-19 写的"Python 3.11 兼容性"不同——那是表象）：
slowapi `limiter.limit()` 返回的 wrapper 函数定义在 slowapi 模块里，其
`__globals__` 指向 slowapi 命名空间。`from __future__ import annotations`
（PEP 563）把 `req: DiagnoseRequest` 注解字符串化后，FastAPI 用
`get_type_hints()` 在 slowapi 的 `__globals__` 里解析不到本地定义的
`StressTestRequest` / `DiagnoseRequest` 模型 → 应用启动崩溃 → nginx 502。

**修复**：删掉 `stress_test.py` / `diagnose.py` 的 `from __future__ import
annotations`，注解变回真实类对象就无需解析。

> **系统性隐患（未修，列入 §5）**：未来任何"有 `from __future__ import
> annotations` + 本地 Pydantic 模型 + `@tier_limit_decorator`"的 handler
> 都会复发。彻底修法是改 `tier_limit_decorator` 或在 CI 用 prod Python 跑。
> 没动它是因为：rate_limit.py 是共享关键文件，无法在本地复现 prod 环境，
> 改它属于"猜"。本地 Python 3.14 测试全过、prod Python 3.11 才崩——又一例
> 本地/prod runtime 漂移。

---

## 2. 全项目功能审查 + 修复

5 个 agent 分集群（核心流程 / 工具 / 科学页 / 账户系统 / 可理解性）逐端点
curl 实测：

### 修复的 bug
- **discoveries P0 数据 bug**（commit bf6e167）：`discoveries.py` 加载了过时的
  `a_discoveries.json`（19 条 V2、无 pipeline 字段），导致 hero 计数显示 19
  （文案写 39）、V2/V3 filter 永远空列表。改为加载 `a_discoveries_merged.json`
  （39 条）。
- **404.html 重复 `data-i18n`**（commit bf6e167）：HTML 解析器静默丢弃第二个；
  desc 段漏绑 i18n。
- **2 个 post_deploy e2e 失败**（commit 4ea5928）：`test_home_brand_h1` 改为
  断言首页价值主张标语（首页 h1 已有意改成标语，测试陈旧）；struct-lint e2e
  timeout 60s → 210s（单次同步 LLM 调用 p99 延迟实测 165s）。

核心流程 / 工具 / 账户系统三个集群逐端点实测，未发现真 bug。

### 可理解性改造（commit 4ea5928）
- 重写 about / index / start-here / tools 文案，让首次访客看懂项目和每个工具
  是做什么的；大白话优先、术语配一句解释。
- "结构 lint" → "策略文档体检"（about/tools/lint.html + lint.js 报错文案）。
- 普适类数字统一到 23（跨领域），与 `/classes` 权威页对齐。
- main.py：补 `/thank-you` 路由（waitlist.js 跳转原本 404）+ 裸 `/report` 路由。

### 移动端优化（commit 3263959）
- analyze 操作按钮在窄屏不再逐字换行（工具条换行 + `white-space:nowrap`）。
- chip / filter 按钮 / 页脚链接触控目标提到 40-44px；桌面端零影响。

### B2 数值预测置信区间（commit 4afd443）
- 24 条 Layer 4 预测 / 49 个数值 band 全部加 95% 区间。方法按 band 实际情况
  选：有 σ 用解析正态 CI；无 σ 用三角先验蒙特卡洛可信区间（诚实标注为先验型、
  非频率派 CI——目标数据未采集）；能匹配已验证 SOC 系统的附真实 bootstrap CI。
- 产出 `v4/results/layer4_predictions_with_ci.jsonl` + `B2_ci_summary.md`。

---

## 3. 四个 roadmap 大项 —— 全部落地

所有 LLM 调用走 `.env` 的 `DEEPSEEK_API_KEY`，总成本 < $1。

### Phase 6 — GitHub 事件级联 SOC 验证（commit bb4164e）
- 第 6 个跨域系统。级联定义：一个热点 issue（响度 = comments+reactions >
  μ+2σ）触发后 30 天内同仓库衍生 issue/PR 的爆发波。
- 真实 GraphQL 数据：29,400 事件 / 25 个大型 OSS repo / 823 个级联。
- **判定 FAIL（稳健）**：级联规模 α=1.696 落在预注册带内，但 Clauset 模型对比
  以压倒性显著度否决幂律（lognormal R=-11.86，exponential R=-14.63）。
  Omori 时间衰减成立（p=0.358, R²=0.95）但规模轴是 lognormal 不是幂律。
  5 组窗口×σ 敏感性扫描确认 FAIL 处处成立。
- **这是诚实负结果**：GitHub 协作是排期驱动、不是自组织临界。
- 产物：`v4/validation/soc-github-cascade/`（fetch 脚本 + events.jsonl +
  analyze.py + cascade_results.json + README + FINDINGS.md）。

### B1 — Layer 3 critic pass 定稿（commit 883da67）
- 21 候选类 → **11 个站得住的 active 普适类**（3 REJECT 是统计极限定理伪装；
  4 SPLIT；4 变体 MERGE）。
- 78 条反例库（near-miss + false-positive 成员）；剔 9 个 false-positive 成员。
- 3 个 critic 悬而未决的类用 DeepSeek V4-pro 补判定下。
- 产物：`v4/scripts/b1_finalize_taxonomy.py`、`v4/results/B1_final_taxonomy.jsonl`、
  `v4/results/B1_final_summary.md`。

### D1 — Phase Detector 500 家（commit b282947）
- 实为前序 session 已扩完（STATUS.md 过时写"55 样本"）。本 session 端到端验证：
  500/500 提取成功、0 失败、字段齐全。
- 回测仍是 **null result**：near-critical Sharpe 0.238 vs other 0.318，
  t=-0.41, p=0.68。相结构信号在更大样本下依然无可辨别的预测力。
- **这是诚实负结果**，未做任何美化。

### C1 — 统一预印本 v0.2（commit f296267）
- `docs/sessions/C1-unified-preprint-draft-v0.2.md`（~7,800 词）。v0.1 的 7 个
  [TODO] 全部闭合。
- 重大发现：**arxiv-02 论文有符号解读错误**——其 Table 1 的 R=-6.12 按 Clauset
  约定实际偏向 lognormal，但摘要却写"power-law dominates"。S&P 500 的 SOC
  判定其实靠 inverse-cubic 指数带吻合（α=2.998），不靠否定 lognormal。
- 范围决策：C1 = 聚焦版 5 系统论文，13 系统 v0.2 是姊妹论文。
- 文末留 6 项发布前人审 checklist（见 §5）。

---

## 4. 本 session 的 12 个 commit

```
50fa312  fix(backend): 删 __future__ annotations — 502 修复
bf6e167  fix(backend,frontend): discoveries 39 条数据 + 404 i18n
4ea5928  feat(frontend): 可理解性改造 + /thank-you + /report 路由
3263959  fix(frontend): 移动端触控目标 + analyze 工具条
4afd443  feat(v4): B2 — Layer 4 预测 95% 区间
6188c6d  docs(sessions): C1 预印本草稿 v0.1
5ff186f  docs(sessions): session #20 handoff（初版）
bb4164e  feat(v4): Phase 6 — GitHub 级联 vs SOC（判定 FAIL）
883da67  feat(v4): B1 — Layer 3 taxonomy critic pass 定稿
f296267  docs(sessions): C1 预印本草稿 v0.2
b282947  docs(v4): D1 — 修正 STATUS + 记录 500 家 null result
6bb8438  docs(sessions): 更新 #20 handoff
（+ 本文件最终版）
```

---

## 5. 待办

| 优先级 | 动作 | 说明 |
|---|---|---|
| 🔴 P0 | 轮换 OpenRouter API key | 旧 key 曾在 public repo 泄露（#17 起遗留）。**只能用户操作**：登录 OpenRouter 控制台重新生成 → 更新 `.env` + VPS 环境变量 |
| 🟡 | whitespace LLM 预计算 | `OPENROUTER_API_KEY=... .venv/bin/python scripts/build_whitespace_matrix.py --llm`，~400 次调用。**阻塞在 key 轮换之后** |
| 🟡 | privacy export mock code | `STRUCTURAL_PRIVACY_MOCK_CODE` 默认是公开的 `123456`，知道订阅邮箱即可拉到明文 IP。Phase-2 真 OTP 前 prod 应设非公开值或脱敏 IP |
| 📋 | C1 v0.2 发布前 6 项人审 checklist | 见草稿文末：Zenodo DOI 核对、pipeline canonical release tag、[待核] 引用条目、Phase 2 lognormal 措辞编辑签字、是否同投姊妹论文、领域专家 review。另建议给 arxiv-02 发单篇勘误 |
| 🟢 | `tier_limit_decorator` 保留 `__globals__` | 502 系统性根因（见 §1）。或 CI 改用 prod Python 跑测试 |
| 🟢 | classes 页 23/26 数字 | 标题"23 跨领域" + 统计卡"26 等价类总数"并存，建议明确标注子集关系 |

### 仍未做的大项
- **G 方向**：按问题结构连接人，独立立项，设计文档 `SESSION-18-G-connect-people-design.md`。
- **Phase 7-12**：其余 SOC 系统扩展（电网/银行/社交/山火/太阳耀斑/交通），各 2-4 天。

---

## 6. 起手指令（下个 session）

```
读 SESSION-20-HANDOFF.md。站点健康，无 P0 阻塞。
Phase 6 / B1 / D1 / C1 本 session 已落地（见 §3 §4）。
优先级：
  (1) 提醒用户轮换 OpenRouter key（CC 推不动，是唯一 P0）
  (2) key 轮换后跑 whitespace LLM 预计算
  (3) C1 v0.2 文末 6 项发布前 checklist 找用户拍板
  (4) 可启动 G 方向 或 Phase 7-12
```

> **诚实备注**：Phase 6 是 FAIL、D1 是 null result。这两个负结果没有为了
> "做完"而美化——跟项目 Phase 5 null 验证的精神一致，一个真的 FAIL 比假的
> PASS 有价值。下个 session 接手时按真实结论推进。

---

## 7. 已知非阻塞事项（agent 审查发现，未改）

- `conftest.py` 手写 `page`/`browser` fixture 与已装的 `pytest-playwright`
  插件同名 fixture 冗余（靠作用域覆盖，能用）。
- `/api/struct-lint` 单次同步 LLM 调用慢（36-165s+）无流式反馈，用户干等。
  后续可考虑 SSE 或异步轮询。
- `content.json` 里 `page.about.why.*` 4 个 i18n key 因 about 改版成孤儿；
  about 新"Use"段无 i18n key（切英文该段保持中文）。
- `scripts/newsletter_data_sources.py` `fetch_top_ask_queries()` 是 W10 有意
  TODO（ask 日志未经公共 API 暴露），newsletter 生成器对空列表有兜底。

---

## 8. 架构速查

| 层 | 位置 | 说明 |
|---|---|---|
| 后端 | `web/backend/main.py` | FastAPI + 14 组 router，port 5004（prod）/ 8000（local） |
| KB 引擎 | `web/backend/services/search_service.py` | 4443 现象，BM25+embedding |
| LLM 客户端 | `web/backend/services/llm_client.py` | OpenRouter，default deepseek/deepseek-chat:nitro |
| 前端 | `web/frontend/` | 纯 HTML/JS/CSS，FastAPI FileResponse 托管 |
| MCP | `mcp/server.py` | 4 tools via FastMCP |
| v4 研究代码 | `v4/` | lib（pipeline）/ validation（Phase 1-6）/ scripts / results / product |
| SOC pipeline | `packages/soc-pipeline/` | 权威实现；`v4/lib/soc_pipeline.py` 是 deprecation shim |
| 测试 | `web/backend/tests/`（713）+ `web/tests/e2e/` | pytest + Playwright |
| VPS | root@43.156.233.71 | structural-web.service，venv Python 3.11 + Pydantic 2.6.1 |
| 部署 | `gh workflow run "Deploy Beta Backend" --ref main` | rsync 到 VPS |
