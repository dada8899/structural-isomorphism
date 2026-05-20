***REMOVED*** 起手:structural-isomorphism / M1.4 报告生成器后端

> Session ***REMOVED***16 起手 prompt(浓缩版)。完整交接见 `SESSION-15-HANDOFF.md`,事故复盘见 `SESSION-15-INCIDENT-deploy-pipeline.md`,数据 + 决策见 `SESSION-15-VERDICT.md`。

**项目**:`~/Projects/structural-isomorphism/`(repo: `dada8899/structural-isomorphism`, PUBLIC)
**上一 session**:***REMOVED***15。

***REMOVED******REMOVED*** 当前 prod 状态(verified 2026-05-20)

- main:`6cf8205`(PR ***REMOVED***223 frontend search box)→ `4a8f643`(***REMOVED***225 session-15 hotfix)→ `690c77b`(***REMOVED***224 M1.2/M1.3)
- backend: `:nitro` DeepSeek + M1.3 short-circuit + `llm_start` SSE 全部 live
- 起手必跑 fingerprint check:`curl -sN -X POST -H "Content-Type: application/json" -d '{"query":"团队为什么散","lang":"zh"}' --max-time 5 https://beta.structural.bytedance.city/api/ask/stream | head -c 400` — 应看到 `"model": "deepseek/deepseek-chat:nitro"` + `event: llm_start`。看不到立即怀疑 deploy 出问题。

***REMOVED******REMOVED*** 下一站:M1.4 报告生成器后端

**M1.4 目标**(start-prompt 老定义,session ***REMOVED***15 verdict 确认):

> 后端报告生成器,复用 `analyze.py` 的 query-mode + cross-judge,把单条 query 的 SSE 结果聚合成一份可分享的结构化报告。

**第一步建议**:

1. **设计先行**(Phase 0):
   - 读现有 `web/backend/api/analyze.py` 看 query-mode 现状
   - 读 `packages/cross-judge/` 了解多模型 ensemble 接口
   - 草一份 PRD 说清楚:报告字段 schema、生成时机(同步 vs 异步)、存储(DB vs 文件)、分享 URL 设计
   - **不要直接写代码**

2. **关键技术验证**:
   - 一份报告需要多少次 LLM 调用?cost reservation 怎么做?
   - cross-judge ensemble 平均耗时?用户能否容忍同步等待?
   - 异步方案是不是要新加 background task / job queue?

3. **PRD review 后再进开发**

***REMOVED******REMOVED*** M2 / 长尾 backlog(VERDICT 留底,按触发捡)

| ***REMOVED*** | 工程债 | 触发条件 |
|---|---|---|
| A | q7 类 forecasting-intent 漏 gate | 用户首次报"AI 给我预测加密货币" |
| B | `:nitro` provider cold-start | in-scope p95 监控稳定 >10s |
| C | `/api/version` endpoint + dogfood fingerprint check | 任意时间 |
| D | sentence-transformers prod runtime smoke test in CI | 任意时间(防再次 deploy 后炸) |

***REMOVED******REMOVED*** 工作纪律(项目级)

- `scripts/train_v2.py` 是别 session 的 in-flight 改动,**不要动**(commit 边界铁律)
- `.claude/worktrees/agent-a3e2f585dec5d670b/` 残留 worktree harness 自己回收,**不要清**
- 每完成一个模块立即 commit + push(不积累)
- 显式 `git add <file>`,**禁** `git add -A` / `commit -a`
- **数据反常时先怀疑 deploy 没真上线,后怀疑代码**(`feedback_dogfood_must_verify_deploy_fingerprint.md`)

***REMOVED******REMOVED*** 关键文件 / 命令

- `docs/sessions/SESSION-15-HANDOFF.md` — 完整 session ***REMOVED***15 交接
- `docs/sessions/SESSION-15-INCIDENT-deploy-pipeline.md` — 5 个连锁问题复盘
- `docs/sessions/SESSION-15-VERDICT.md` — M1 真实 TTFT 数据 + 决策
- `scripts/dogfood_ttft.py` — 7-query TTFT + 自动 verdict(`.venv/bin/python scripts/dogfood_ttft.py`)
- VPS deploy: `gh workflow run "Deploy Beta Backend"` 自动走 dispatcher(`/root/scripts/deploy-dispatcher.sh`)
- VPS 手动 deploy(应急): `ssh root@43.156.233.71 'bash /root/scripts/deploy-beta-backend.sh'`
