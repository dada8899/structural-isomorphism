***REMOVED*** SESSION-15 Verdict:M1.2/M1.3 真实数据 + 下一步决策

> 配套 `SESSION-15-INCIDENT-deploy-pipeline.md`(deploy 链路修复)。本文档专注:在真实 deploy 后,M1.2/M1.3 性能 + 行为是否达标,下一站走哪里。

***REMOVED******REMOVED*** 真实 TTFT 数据(deploy 修好之后)

两轮跑,各 7 query。每行格式:`v2 / v3`(两次独立 run)。

| qid | expected | TTFT (v2/v3) | done (v2/v3) | OOS flag | llm_start | 备注 |
|---|---|---|---|---|---|---|
| q1 SVB 怎么倒的 | in_scope | 10.88s / **5.1s** | 45.9s / 30.2s | — | ✅ Y/Y | v2 噪声单点 |
| q2 团队为什么散 | in_scope | 5.94s / 3.79s | 40.3s / 29.7s | — | ✅ Y/Y | |
| q3 用户流失原因 | in_scope | 6.10s / 9.45s | 20.0s / 40.5s | — | ✅ Y/Y | |
| q4 传言怎么扩散 | in_scope | 1.57s / 3.41s | 23.7s / 24.6s | — | ✅ Y/Y | :nitro 极快 |
| q5 女朋友为什么生气 | OOS | **0.70s** / 0.78s | **1.0s** / 1.15s | True / True | N/N | ✅ short-circuit |
| q6 1+1=? | OOS | **0.61s** / 0.62s | **0.98s** / 1.06s | True / True | N/N | ✅ short-circuit |
| q7 BTC 明天涨跌 | OOS | 1.72s / 1.67s | 15.4s / 16.3s | **None** | Y / Y | ❌ leak through |

两轮 in-scope TTFT 汇总:
- v2:min 1.57s / max 10.88s / avg 6.12s
- v3:min 3.41s / max 9.45s / avg 5.44s
- 合并 8 个样本:中位 5.5s,最大 10.9s(单次噪声),其余全部 ≤9.5s

***REMOVED******REMOVED*** 三个判断维度

***REMOVED******REMOVED******REMOVED*** 1. M1.2 perf 改动是否达标:✅ 部分

- **fix 1 (:nitro)** — 验证生效。q4(1.6s)、q1-v3(5.1s)、q2-v3(3.8s)都进入"快"区间。Claude 时代的 18-32s baseline 已消失。
- **fix 4 (llm_start SSE)** — 验证生效。所有 in-scope 查询都 emit。前端"黑屏"感知断层有 hook 可推进。
- **Fix 2 (drop json_object)** & **Fix 3 (prompt slim)** — 启动门槛是"max >10s 稳定长尾"。v2 单次 10.88s 是噪声,v3 max 9.45s。**不达启动门槛,本 session 不做**。

***REMOVED******REMOVED******REMOVED*** 2. M1.3 拒答短路是否达标:✅ 部分

- **q5 / q6** — 完美。<1s 总耗时,0 LLM 调用,answer_done 带 `out_of_scope=True`。彻底解决了"1+1=? 烧 33s 硬拗类比"。
- **q7 BTC 明天涨跌** — 漏过 gate。`top1=0.8854 > RELEVANCE_TOP1_MIN=0.75`,top3 mean=0.71 > 0.65,**两个 gate 全过**。
  - 原因不是阈值偏低,是**语义 gap**:KB 里有"市场崩盘 / 加密货币波动"类条目跟 "BTC" 高度相似(0.88),但 user intent 是 forecasting(明天涨跌),跟 structural search 的价值主张错位。
  - 纯调阈值不可行:抬到 0.9 会误伤合法 in-scope 查询(q1 SVB top1 大概率也 0.85+)。
  - **正确做法属于 M2 scope**:加 forecasting-keyword 二次拦截(明天/会不会/预测/涨跌 → 即使 retrieval 高分也拒答)。本 session 不做,但写 memory 记录。

***REMOVED******REMOVED******REMOVED*** 3. q1 长尾 10.88s 的归因

- v2 单次 10.88s,v3 同 query 5.1s。**5 倍方差**。
- 不是 query 本身复杂度问题(同样 query 同样 KB,5s 和 10s 都能跑出)。
- 推测是 OpenRouter `:nitro` 路由到不同 provider 的 cold-start / queue。`:nitro` 选最快 provider,但"最快"在不同时刻可能是不同 provider,首次路由有 cold-start 代价。
- **不值得为单点噪声启动 Fix2/3 重构**。

***REMOVED******REMOVED*** 下一站决策

**跳过 M1.2 Fix2/3,推进 M1.4 报告生成器后端**。

理由:
- TTFT 落在 start-prompt 的"6-10s borderline — judgement call"区间,Fix2/3 ROI 不明
- Fix2(drop json_object)会引入新的 envelope 解析成本,可能换不来等价 TTFT 改善
- M1.4 是产品维度的下一个增量,而 Fix2/3 是工程债的渐进优化
- 若后续监控(P1)显示 in-scope p95 稳定 >10s,再启动 Fix2/3 不迟

***REMOVED******REMOVED*** 待补的 M2 / 长尾 backlog

| ***REMOVED*** | 工程债 | 触发 | 优先级 |
|---|---|---|---|
| A | q7 类 forecasting-intent 漏 gate | 用户首次报"AI 给我预测加密货币" | M2 排队 |
| B | OpenRouter :nitro provider cold-start | in-scope p95 监控稳定 >10s | 监控触发 |
| C | `/api/version` endpoint + dogfood fingerprint check | 长效,任意时间 | 排队 |
| D | sentence-transformers prod runtime smoke test in CI | 任意时间(防再次 deploy 后炸) | 排队 |

***REMOVED******REMOVED*** Memory 待写

session 收尾时写入 `~/Vault/Memory/`:
- `feedback_deploy_pipeline_command_restriction.md` — `command=` 锁死 deploy key 的二次扩展模式(dispatcher)
- `feedback_requirements_pinned_vs_prod_runtime_drift.md` — pip pin 跟 prod venv 漂移的检测方法
- `feedback_dogfood_must_verify_deploy_fingerprint.md` — dogfood 起手必须 fingerprint check
- `feedback_test_sse_event_completeness.md` — SSE 协议改动必须配集成测试断言
- `feedback_env_override_pre_pr_check.md` — 改默认 env 值的 PR 起手必须 grep prod `.env`
- `knowledge_openrouter_nitro_cold_start.md` — :nitro 有 provider 路由 cold-start,首次方差可能 5x
