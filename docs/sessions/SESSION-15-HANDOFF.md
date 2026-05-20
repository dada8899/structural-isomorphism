***REMOVED*** SESSION-15 交接文档(2026-05-20)

> Session ***REMOVED***15 起点是 ***REMOVED***14 的 dogfood 验证。中途撞见 deploy 5 天哑炮 + 4 个连锁问题,session 实际工作量从"跑 7 条 query"扩展到"修整条 deploy pipeline + ship 3 个 PR"。详细复盘见 `SESSION-15-INCIDENT-deploy-pipeline.md`,数据 + 决策见 `SESSION-15-VERDICT.md`。

***REMOVED******REMOVED*** 本 session 真实 ship 的东西

main 上 4 个 PR(老到新):

```
cd19782 PR ***REMOVED***222  fix(ci): CI fixes (session ***REMOVED***14 遗留)
690c77b PR ***REMOVED***224  feat(ask): M1.2/M1.3 — :nitro + short-circuit + llm_start
4a8f643 PR ***REMOVED***225  fix(session-15): deploy pipeline hotfix
6cf8205 PR ***REMOVED***223  feat(frontend): redesign home search box (scheme A)
```

***REMOVED******REMOVED*** prod 当前状态(verified)

| 检查 | 结果 |
|---|---|
| `/api/health` | HTTP 200 |
| `meta.model` in SSE stream | `deepseek/deepseek-chat:nitro` ✅ |
| `event: llm_start` in stream | ✅ |
| q5/q6 OOS short-circuit | <1s 完成,0 LLM 调用 ✅ |
| 首页 placeholder 新文案 | "问点复杂的——它可能在另一个学科已经被解过" ✅ |
| Deploy dispatcher 路由(push 触发) | ***REMOVED***225 + ***REMOVED***223 各跑一次成功 ✅ |

***REMOVED******REMOVED*** 5 个修过的连锁问题(全活,详见 INCIDENT)

1. **P0 Deploy 5 天哑炮** — VPS `~/.ssh/authorized_keys` 把 GH Actions deploy key `command=` 锁死跑 phase-detector.sh,backend deploy workflow 全是假绿。修法:新加 `/root/scripts/deploy-dispatcher.sh` 按 `$SSH_ORIGINAL_COMMAND` 路由 + 新加 `/root/scripts/deploy-beta-backend.sh` + `authorized_keys` 改指向 dispatcher(`.bak-2026-05-20` 留 root)。
2. **P0 requirements.txt 死 pin 漂移** — `sentence-transformers==2.5.0` pin 跟 prod 实跑 5.4.0 漂移,任意 `pip install -r` 会反向降级炸服务。修法:改 `>=5.4.0,<6` range pin + 中文注释。
3. **P1 ASK_LLM_MODEL env 覆盖** — VPS `.env` 里 `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6` 完全覆盖 PR ***REMOVED***224 的 `:nitro` 默认值。修法:VPS `.env` 注释掉那行,`.env.bak-2026-05-20` 留 root,restart service 验证 model 字段切到 `:nitro`。
4. **P1 第一轮 dogfood 数据无效** — 打的是 5/15 老代码,verdict 不能信。修法:deploy 真上线后重跑 v2 + v3,得到真实 TTFT 分布。
5. **P2 SSE event 测试漏断言** — `test_ask_streaming` 没断言 `llm_start` 真出现。修法:加 required event + ordering(retrieval_done < llm_start < answer_chunk)+ payload `model` 字段断言。

***REMOVED******REMOVED*** dogfood 真实数据(两轮)

| qid | query | TTFT (v2/v3) | done (v2/v3) | OOS | llm_start |
|---|---|---|---|---|---|
| q1 | SVB 怎么倒的 | 10.88 / 5.10 | 45.9 / 30.2 | — | ✅ |
| q2 | 团队为什么散 | 5.94 / 3.79 | 40.3 / 29.7 | — | ✅ |
| q3 | 用户流失原因 | 6.10 / 9.45 | 20.0 / 40.5 | — | ✅ |
| q4 | 传言怎么扩散 | 1.57 / 3.41 | 23.7 / 24.6 | — | ✅ |
| q5 | 女朋友为什么生气 | 0.70 / 0.78 | 1.0 / 1.15 | True | N(短路) |
| q6 | 1+1=? | 0.61 / 0.62 | 0.98 / 1.06 | True | N(短路) |
| q7 | BTC 明天涨跌 | 1.72 / 1.67 | 15.4 / 16.3 | **None** | ✅(应短路却没) |

合并 8 个 in-scope 样本:median 5.5s,max 10.9s(单次噪声)。

***REMOVED******REMOVED*** 决策结论(VERDICT)

**跳过 M1.2 Fix2/3,下一站 M1.4 报告生成器后端。**

理由:TTFT 落在 start-prompt 的"6-10s borderline judgement call"区间,Fix2/3 重构 ROI 不明;q5/q6 short-circuit 完美;q7 forecasting-intent 漏 gate 是 M2 scope(纯调阈值不可行,要加 keyword 二次拦截)。

***REMOVED******REMOVED*** 6 个新 memory(全局,~/.claude 下)

- `feedback_deploy_pipeline_command_restriction.md`
- `feedback_requirements_pinned_vs_prod_runtime_drift.md`
- `feedback_dogfood_must_verify_deploy_fingerprint.md`
- `feedback_test_sse_event_completeness.md`
- `feedback_env_override_pre_pr_check.md`
- `knowledge_openrouter_nitro_cold_start.md`

MEMORY.md 新加 `Feedback — Deploy / Runtime` 段落。

***REMOVED******REMOVED*** M2 / 长尾 backlog(VERDICT 末尾留底)

| ***REMOVED*** | 工程债 | 触发条件 |
|---|---|---|
| A | q7 类 forecasting-intent 漏 gate | 用户首次报"AI 给我预测加密货币" |
| B | `:nitro` provider cold-start | in-scope p95 监控稳定 >10s |
| C | `/api/version` endpoint + dogfood fingerprint check | 任意时间 |
| D | sentence-transformers prod runtime smoke test in CI | 任意时间(防再次 deploy 后炸) |

***REMOVED******REMOVED*** 工作纪律(下个 session 起手必读)

- `scripts/train_v2.py` 是别 session 的 in-flight 改动,**不要动**(commit 边界铁律)
- `.claude/worktrees/agent-a3e2f585dec5d670b/` 残留 worktree harness 自己回收,不要清
- 每完成一个模块立即 commit + push(不积累)
- 显式 `git add <file>`,**禁** `git add -A` / `commit -a`
- 数据反常时先怀疑 deploy,后怀疑代码(详见 `feedback_dogfood_must_verify_deploy_fingerprint.md`)

***REMOVED******REMOVED*** 下个 session 入口

1. 读 `docs/sessions/SESSION-16-START-PROMPT.md`(浓缩版,可直接贴进新 CC)
2. 或直接进 M1.4 设计:报告生成器后端
3. M2 backlog 4 条按触发条件捡

***REMOVED******REMOVED*** 关键文件路径

- `docs/sessions/SESSION-15-INCIDENT-deploy-pipeline.md` — 5 个连锁问题全链路复盘
- `docs/sessions/SESSION-15-VERDICT.md` — 真实数据 + 决策
- `docs/sessions/session-15-ttft-v{2,3}.json` — 两轮 dogfood raw data
- `scripts/dogfood_ttft.py` — 复用脚本,新 session 也能跑(`.venv/bin/python scripts/dogfood_ttft.py`)
- `web/backend/services/ask_orchestrator.py` — M1 战场,line 421 `yield _sse("llm_start", ...)`
- `web/backend/requirements.txt` — ST pin 已改成 range
- VPS `/root/scripts/deploy-dispatcher.sh` + `deploy-beta-backend.sh` — 新建,git 之外
- VPS `~/.ssh/authorized_keys` — `command=` 已切到 dispatcher,`.bak-2026-05-20` 备份
