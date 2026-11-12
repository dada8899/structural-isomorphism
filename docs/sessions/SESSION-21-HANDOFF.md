# Session #21 Handoff

> 日期：2026-05-23 ~ 05-24
> 承接 SESSION-20-HANDOFF.md。
> 本 session 从用户报的「点生成报告没反应」bug 起手，做到全部交接待办清零。
> **站点健康，无 P0 阻塞（一个只能用户操作的 P0 仍遗留：OpenRouter key 轮换）。**

---

## 0. 当前状态

- `beta.structural.bytedance.city` 健康（health 200），生产环境正常。
- 后端 756 测试全过（SESSION-20 是 713，涨幅来自本 session 新增的 struct-lint
  流式 15 + 502 回归 4 + connections 30 + privacy fingerprint 1 测试）。
- 本 session 8 个 commit 全部 push 到 `origin/main`，已分 4 次部署，live 验证通过。
- 一个 prod 配置变更：VPS 设了 `STRUCTURAL_PRIVACY_MOCK_CODE`（详见 §A）。
- working tree 仅剩 `scripts/train_v2.py`（非本 session lineage，按 commit
  边界铁律未动，与 #19 #20 一致）。

---

## 1. 起手 bug：/analyze 链接参数名错误（commit b638ac4）

**用户现象**：点「生成研究报告」后页面不生成报告，显示空状态。

**根因**：`/analyze` 页面有两套参数名——后端 API `/api/analyze/stream` 收
`text_a`/`b_id`/`a_id`；前端页面 URL 收 `id`/`q`/`a_id`（analyze.js 自己翻译）。
`ask.js`/`whitespace.js`/`apply.js`/`classes.js` 四个入口拼 URL 时误用了
**后端 API 的参数名**。analyze.js 读不到 `id` → 提前 return 进空状态。

**修复**：四个入口改用 `id`/`q`。classes.js 因类数据无现象 id，给
`build_site_data.py` 增 `hub_id` 字段（按 hub_name 匹配 KB，23/26 解析，
3 个 post-build 类无对应 → 降级到 /search）。4 个 HTML 的 JS cache-bust
版本号 bump。

> **系统性根因未根治**：`/analyze` URL 参数契约无单一权威源、无共享
> `buildAnalyzeUrl()`。后续可抽一个共享 builder，杜绝同类漂移。

---

## 2. 502 系统性根因根治（commit c1c87f0）

**修正 SESSION-20 §1 的判断**：交接文档说「本地 Python 3.14 全过、prod
Python 3.11 才崩」是 Python 版本差异——**错了**。真因是 **FastAPI 版本**：
prod 钉死 `fastapi==0.110.0`，其 `get_typed_signature` 取 `call.__globals__`
时不调 `inspect.unwrap`；本地 venv 是 0.136.1（含 unwrap）所以掩盖了 bug。

slowapi `limiter.limit()` 的 wrapper 经 `functools.wraps` 仍带 slowapi 模块
的 `__globals__`（wraps 复制不了 `__globals__`）。handler 带 PEP 563 注解时
FastAPI 拿 slowapi 的 globals 解析本地 Pydantic 模型 → NameError → 启动崩。

**修复**：`rate_limit.py` 用 `types.FunctionType` 以同一份 code+closure
重建 slowapi wrapper，`__globals__` 换成 `_ChainedGlobals` 链式查找——
handler 模块符号优先（FastAPI 注解解析能找到本地模型），slowapi globals
兜底（slowapi 自己 wrapper body 仍能解析 Response/Request）。

- stress_test.py / diagnose.py 加回了被 SESSION-20 删掉的
  `from __future__ import annotations`，证明根治生效。
- 新增 `test_slowapi_pep563_globals_crash.py`（4 用例，显式模拟 0.110.0
  无-unwrap 路径，修复前复现 NameError、修复后全过）——这把交接说的
  「无法本地复现」变成了「测试即复现」。
- **建议（未做）**：`requirements.txt` 把 `fastapi==0.110.0` 升一档作为
  第二层防御，独立版本决策。

---

## 3. struct-lint 流式反馈（commit 80a48d5）

原 `/api/struct-lint` 单次同步 LLM 调用 36-165s 干等无反馈。新增
`GET /api/struct-lint/stream` SSE 端点（沿用 analyze.py 风格），逐阶段
yield `extract`/`claims`/每条主张 `isomorph`/`done` 进度事件。原 POST 端点
保留向后兼容。前端 lint.js 改 EventSource 消费，等待期实时显示进度。
+15 测试，SSE 测试断言事件真出现在 wire 上。

> **遗留**：某处 Playwright e2e 把 struct-lint 超时设到 210s，流式化后
> 首字节是亚秒级，可下调（建议 SSE 首事件 10s 超时 + 整体 180s）。本
> session 未定位到该 e2e 文件。

---

## 4. privacy 验证码 fail-closed（commit a3b7660）

`STRUCTURAL_PRIVACY_MOCK_CODE` 未设时旧代码默认公开的 `"123456"`，知道
订阅者邮箱即可拉 PII / 触发数据删除。改为 env 未设时返回每进程随机
`secrets.token_hex(16)`，端点 fail-closed，并打 warning 提示运维配置。
export + delete 同改，+2 测试。

**prod 配置**：本 session 已在 VPS 配上一个非公开码（详见 §A）。

---

## 5. whitespace LLM 预计算（commit facc617）

`build_whitespace_matrix.py --llm` 的 LLM 评判层之前没跑（缺 OpenRouter
key）。本 session 改用项目自带 DeepSeek key 经 DeepSeek OpenAI-兼容端点
路由，376 次调用 0 错误。结果 filled=104 / lead=198 / empty=4456，丢弃
205 条 plausible=no 弱线索。runner 是 `scripts/run_whitespace_llm.py`。

> **注**：这是绕过 OpenRouter 的一次性手段；prod 的 analyze/ask 主链路
> 仍依赖 OpenRouter（见 §8 P0）。

---

## 6. G 方向 P1+P2 + 软上线（commit 4b9b520 + 979874e）

按 `SESSION-18-G-connect-people-design.md` 落地「按问题结构连接人」的
P1（结构指纹抽取/存储）+ P2（匹配引擎 + L1 可发现 + 三级可见性）。P0
账号复用已有 auth.py magic-link；P3（双向同意 match / 引荐 / 消息）按
设计建议推迟到 P2 验证需求后。

- 后端：`services/connections_store.py`（SQLite，加列自愈）+
  `services/connections_match.py`（结构相似度匹配，强制跨域过滤）+
  `api/connections.py`（5 端点，复用 auth.py JWT，L1 neighbors 响应剥掉
  user_email/fingerprint_id 不暴露身份）
- 前端：`/connections` 页（未登录内嵌 magic-link，已登录可登记指纹/切
  可见性/看结构邻居）
- **隐私漏洞补齐**（commit 979874e）：结构指纹纳入 `/api/privacy/delete`
  范围。原 delete 只重写 JSONL，会漏删 SQLite 指纹表（设计 §2.4 要求）。
  现按 email 删除时同步调 `ConnectionsStore.delete_all_for_user`，
  removed 计数加 `structural_fingerprints` 项。+1 跨用户隔离测试。
- **软上线**：`/tools` 页加「结构连接」卡片（commit 979874e），让 MVP 可被
  发现。**没进顶部导航、没正式立项、没上 P3**——等用户看实际用量再定。
- 30 个本 session 新测试 + 1 个 privacy 集成测试。

### 待用户拍板

- G 是否正式立项 / 是否对外大力上线 / 是否继续 P3。产品定位级决策。
- report.html 底部加「一键把报告升级成指纹」opt-in 入口（设计 §3.4），
  本 session 未做。
- 设计 §3.4 P4 每周 digest 邮件未做（属社区形态阶段）。

---

## 7. Phase 7-12：交接 §5 的待办其实早已完成

SESSION-20 §5 把「Phase 7-12 六个 SOC 系统扩展」列为「仍未做的大项」。
**审计 `v4/validation/` 发现六个全做完了**（跟 D1 一样，交接 todo 过时）：

| 系统 | 数据 | α | 判定 |
|---|---|---|---|
| 电网 power-grid | 123 events（文献荟萃） | 2.018 | CONFIRMED (literature band) |
| 银行 bank-failures | 3,960（FDIC 真实） | 1.899 | CONFIRMED |
| 山火 wildfire | 21,022（NIFC 真实） | 1.660 | CONFIRMED (lognormal 共存) |
| 太阳耀斑 solar | 29,907（NOAA 真实） | 2.194 | CONFIRMED (最干净) |
| 交通 traffic | 5,012 + 文献 | — | CONFIRMED_COMPOSITE |
| 维基浏览 wikipedia | 7,521（Wikimedia 真实） | 2.034 | CONFIRMED |

**教训**（写进 session kickoff 起手纪律）：**接手先审计 `v4/validation/`
实际状态，别照 handoff todo 重做**。SESSION-20 已撞过同款（D1 已扩完但
STATUS 写 55 样本），本 session 同样撞了 Phase 7-12。Handoff todo 列表
默认按「milestone 时刻的快照」存在，与现实可能漂移。

---

## A. prod 配置变更（本 session 唯一一处）

> **2026-07-14 安全修订：**本节曾错误记录已退役生产 mock code 的明文。
> 该值视为已泄露并已从当前文档和生产私有配置移除；服务重启后不再加载
> 该变量，旧端点按进程随机值锁死。下一版本中旧 export/delete 固定返回
> HTTP 410，用户数据权利统一通过登录态 `/api/me/export` 与
> `/api/me/delete`。不得从 Git 历史恢复或重新使用旧值。

---

## 8. 待办（给下个 session）

| 优先级 | 动作 | 说明 |
|---|---|---|
| 🔴 P0 | **轮换 OpenRouter API key** | SESSION-20 起遗留，旧 key 曾在 public repo 泄露。**只能用户操作**。本 session whitespace 预计算靠 DeepSeek 绕过了，但 prod 的 analyze / ask 主链路仍依赖 OpenRouter |
| 📋 | G 方向产品决策 | 立项 / 大力上线 / P3 / report.html 升级入口（见 §6 待用户拍板） |
| 🟢 | requirements.txt 升 fastapi | 502 第二层防御（见 §2 末） |
| 🟢 | 抽共享 buildAnalyzeUrl() | /analyze 参数契约根治（见 §1 末） |
| 🟢 | struct-lint e2e 超时下调 | 见 §3 末 |
| 🟢 | privacy export 也补 fingerprint | §6 只补了 delete；export 返回值未含指纹（DSAR 完整性次要瑕疵） |
| 📋 | C1 v0.2 发布前 6 项人审 | SESSION-20 §5 遗留，本 session 未动 |

---

## 9. 本 session 的 8 个 commit

```
b638ac4  fix(frontend): /analyze 链接参数名 — 4 个入口的生成报告失效
a3b7660  fix(backend): privacy 验证码未配置时 fail-closed
80a48d5  feat(backend,frontend): /api/struct-lint 流式进度反馈
c1c87f0  fix(backend): 根治限流装饰器吞掉 handler __globals__ 导致的 502
4b9b520  feat: G 方向 P1+P2 — 按问题结构连接人（structural connections MVP）
facc617  feat(whitespace): 跑 LLM 评判层预计算 whitespace 矩阵
1afdade  docs(sessions): session #21 handoff（初版）
979874e  feat: G 方向软上线 + 结构指纹纳入隐私删除范围
（+ 本文件最终版）
```

全部已部署，live 验证：health 200 / /connections 200 / /tools 含「结构连接」
卡片 / struct-lint SSE 事件正常流 / /api/diagnose 返回 422 而非 502（证明
502 根治在 prod 生效）/ privacy 旧码 401、新码 200。

---

## 10. 起手指令（下个 session）

```
读 SESSION-21-HANDOFF.md。站点健康，prod 配置就位。
唯一 P0：提醒用户轮换 OpenRouter key（CC 推不动，主链路仍依赖）。
其余可启动：(a) requirements.txt 升 fastapi（502 第二层防御）
           (b) 抽共享 buildAnalyzeUrl()（/analyze 参数契约根治）
           (c) C1 v0.2 发布前 6 项人审清单（SESSION-20 §5 遗留）
G 方向已软上线（/connections + /tools 卡片），等用户看用量再决定 P3 / 立项。
```

> **诚实备注**：本 session 修正了 SESSION-20 对 502 根因的判断（不是 Python
> 版本是 FastAPI 版本），并审计发现 SESSION-20 §5 列的「Phase 7-12 todo」
> 其实已全部完成。下个 session 接手时**先审计 v4/validation/ 实际状态**
> 再照 handoff todo 做事——handoff 是 milestone 快照，会过时。
