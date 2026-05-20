***REMOVED*** SESSION-15 事故复盘:Deploy 哑炮 5 天 + 连锁 5 个问题

> 日期:2026-05-20。触发场景:PR ***REMOVED***224 (M1.2/M1.3) merge 后做 dogfood TTFT 验证,数据反常 → 顺藤摸下去发现 deploy pipeline 5 天哑炮 + 连锁 4 个长期债。

***REMOVED******REMOVED*** TL;DR

PR ***REMOVED***224 合并后,从主战场( `dogfood_ttft.py` 测 7 条 query)反推出 5 个相互嵌套的问题。最深层的 **deploy 哑炮** 让上层每个症状(数据反常、模型不对、event 没 emit)都被错误归因。下次起手,**dogfood 测出反常 → 不要先怀疑代码,先怀疑 deploy 是不是真上线**。

---

***REMOVED******REMOVED*** 5 个问题(从根因到表象)

***REMOVED******REMOVED******REMOVED*** ***REMOVED***1 — P0 Deploy infra 哑炮 5 天 ❌→✅

**症状**:`Deploy Beta Backend` workflow 5 天来全部 status=success,但 backend code 没真上线。`/root/Projects/structural-isomorphism/web/backend/services/ask_orchestrator.py` 自 2026-05-15 01:30 起没被修改过(md5 vs source: 完全不同)。`structural-web.service` 自 5/15 起没重启过(`Active: ... since Fri 2026-05-15 01:30:40 CST; 5 days ago`)。

**根因**:VPS `~/.ssh/authorized_keys` 第 3 条:

```
restrict,command="/root/scripts/deploy-phase-detector.sh" ssh-ed25519 ... gh-actions-phase-detector@structural-iso
```

`command=` 是 SSH 强约束——**不管客户端发什么命令,服务端只跑这个**。`Deploy Beta Backend` workflow 发的是 `bash scripts/deploy-vps.sh`,但 SSH 强制改跑 phase-detector 部署脚本。

证据:deploy 26166560517 的日志里所有行都带 `[deploy-phase-detector 2026-05-20T13:44:05Z]` 前缀,且 `Verify prod health` 步骤永远 pass 因为它检测的是早就活着的旧 service。

**为什么没人发现**:
- workflow 总是 ✅ 绿(deploy-phase-detector.sh 本身跑得很好)
- 健康检查 `/api/health` 永远 200(老 service 在跑)
- 后端代码改动较少时,没有 user-facing 信号能区分"新代码生效"vs"老代码还在"

**修复**:见 task ***REMOVED***8。需要再加一条 deploy key 走另一个 `command=` 限制(指向 `deploy-vps.sh`),让 backend workflow 用新 key。当前权宜:手动 `ssh + bash scripts/deploy-vps.sh` 触发真部署。

**memory**:`feedback_deploy_pipeline_dumb_5days.md` — 把这条经验固化:`gh actions deploy` 用 `command=` 限制的 deploy key 时,**每个独立 deploy 目标都要有自己的 key + 自己的 command 脚本**。

---

***REMOVED******REMOVED******REMOVED*** ***REMOVED***2 — P0 `requirements.txt` 漂移到 prod runtime ❌→✅

**症状**:手动跑 `bash scripts/deploy-vps.sh` 后,service 起不来。第一波报错 `ModuleNotFoundError: No module named 'structlog'`。装 structlog 后,`No module named 'jwt'`。批量装 `pip install -r requirements.txt`,把 `sentence-transformers` 从 prod 跑了一直在跑的 5.4.0 **强降到 2.5.0**(requirements.txt 里 pin 的版本),模型加载失败:

```
You try to use a model that was created with version 5.5.0,
however, your version is 2.5.0.
RuntimeError: Could not load any model.
```

**根因**:`web/backend/requirements.txt` 长期被忽略——prod 装包靠 ad-hoc 手动 `pip install`,requirements.txt 跟实际 venv 的版本严重漂移:

| package | requirements.txt | prod venv 实际 | 模型需要 |
|---|---|---|---|
| sentence-transformers | 2.5.0 | 5.4.0 | 5.5.0+ |
| structlog | 25.5.0 | 缺 | ≥ 25.x |
| pyjwt | 2.12.1 | 缺 | ≥ 2.x |

**修复(本 PR)**:`requirements.txt` 改成 `sentence-transformers>=5.4.0,<6` + `torch>=2.2.0,<3`,留下中文注释解释 2026-05-20 为什么这么 pin。后续需要 prod 一次 `pip install -r requirements.txt` 全量复跑校验。

**memory**:`feedback_requirements_pinned_vs_prod_runtime_drift.md` — 凡是 `==X.Y.Z` 死 pin 的依赖,deploy 必须有"装完一次性 import smoke test 拉起 service",否则一个手抖 ad-hoc upgrade 就会让 requirements.txt 永久过期。

---

***REMOVED******REMOVED******REMOVED*** ***REMOVED***3 — P1 `ASK_LLM_MODEL` env 覆盖让 :nitro 从未生效 ❌→pending

**症状**:dogfood 第一轮的 SSE `meta` event 显示 `"model": "anthropic/claude-sonnet-4.6"`,不是 PR ***REMOVED***224 commit `2936f4d` 改的 `deepseek/deepseek-chat:nitro`。

**根因**:`web/backend/services/ask_orchestrator.py` 第 50 行:

```python
ASK_MODEL = os.getenv("ASK_LLM_MODEL", "deepseek/deepseek-chat:nitro")
```

VPS 上 `web/backend/.env` 里有 `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6`,**完全覆盖** PR 默认值。即使 deploy 没哑炮(***REMOVED***1),`:nitro` 的 TTFT 优化也不会生效。

**修复**:Task ***REMOVED***9。`unset ASK_LLM_MODEL` 或者从 `.env` 删掉那行,让 PR 默认值生效。

**memory**:复用现有 `feedback_pydantic_settings_shell_env_priority.md` 的教训扩展——**任何 `.env` 改动必须写进 `.env.example` 并 commit**,否则 prod 跟 repo 的 config 漂移会让代码改动看似生效实则不生效。

---

***REMOVED******REMOVED******REMOVED*** ***REMOVED***4 — P1 第一轮 dogfood 数据完全无效 ❌→需重跑

**结论**:第一轮 `docs/sessions/session-15-ttft.json` 的数据**整份扔掉**。打的是 5 天前的旧代码 + Claude Sonnet,不是 PR ***REMOVED***224 的 :nitro + DeepSeek + M1.3 短路。Verdict "max=11.36s → 启 Fix2/3" **不能信**。

**重跑 prerequisite**:
1. Prod 恢复(task ***REMOVED***6)
2. `:nitro` 真生效(task ***REMOVED***9)
3. `_build_refusal_payload` + `llm_start` SSE 都真在跑(deploy 完跑 `curl | grep '^event:'` 看到 `llm_start` 字样为准)

**memory**:`feedback_dogfood_must_verify_deploy_first.md` — dogfood 前必须做一次 deployment fingerprint check:抓一条 meta event,看 model / version / build hash 跟期望对上,**对不上立即停**,不要分析"为什么数据反常",先怀疑没真上线。

---

***REMOVED******REMOVED******REMOVED*** ***REMOVED***5 — P2 测试漏断言 SSE event(漏过 ***REMOVED***224 review)❌→✅

**症状**:`test_ask_streaming.py::test_full_event_sequence_streaming_path` 验了 retrieval_done / kb_cards / answer_chunk / answer_done / similar_phenomena / followups / done,**唯独没断言 `llm_start`**。所以即使 PR ***REMOVED***224 commit `5090e4c` 真没写 `yield _sse("llm_start", ...)` (实际写了,但流程上是漏的),49 个测试还能全绿。`test_structlog_format.py` 里有一个 `ask.llm.start` 引用,但那只验证 log 行格式,跟 SSE event 完全不同。

**修复(本 PR)**:`test_full_event_sequence_streaming_path` 加 `llm_start` 到 required list + 加 ordering 断言(retrieval_done < llm_start < first answer_chunk)+ 加 payload 必含 `model` 字段。47→48 测试,全绿。

**memory**:`feedback_test_sse_event_completeness.md` — SSE 协议改动(加事件、改 payload 字段)必须配对一个集成测试断言事件在流里出现 + ordering 对。"加了 log 行" ≠ "加了 SSE event",两件事。

---

***REMOVED******REMOVED*** 矫正动作(已落或排队)

| ***REMOVED*** | 动作 | 状态 |
|---|---|---|
| 6 | `pip install sentence-transformers>=5.4.0` 恢复 prod | DONE(本 session) |
| 7 | `requirements.txt` 改 pin + 加注释 | DONE(本 PR) |
| - | `test_ask_streaming.py` 加 `llm_start` 断言 | DONE(本 PR) |
| 8 | 加第二条 deploy key + 自己的 command 脚本 | 排队 |
| 9 | unset VPS `.env` 里的 `ASK_LLM_MODEL` | 排队 |
| 10 | 重跑 dogfood TTFT against real M1.2/M1.3 code | 等 6/8/9 全部就绪 |
| - | 把 5 条 memory 写到 `~/Vault/Memory/Memory/` | 排队 |

***REMOVED******REMOVED*** 长效防御:加一条 deployment fingerprint check

每次 deploy 完,workflow 末尾跑一个 fingerprint endpoint(暂用 `/api/health` 加版本字段,或新增 `/api/version`):

```
GET /api/version
{
  "git_sha": "690c77b...",
  "deployed_at": "2026-05-20T13:43:46Z",
  "ask_model": "deepseek/deepseek-chat:nitro"
}
```

dogfood 脚本起手第一件事是抓这个 endpoint + 跟 GH Actions workflow ID 对账,**不对上不跑 dogfood**。这把 ***REMOVED***1 + ***REMOVED***3 + ***REMOVED***4 三条链路全锁住。
