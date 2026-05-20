***REMOVED*** Session ***REMOVED***14 交接文档

> 2026-05-20。接 session ***REMOVED***13(`SESSION-13-HANDOFF.md`)。供下个 session 起手用。

***REMOVED******REMOVED*** 1. 当前状态快照

| Item | Value |
|---|---|
| repo | `dada8899/structural-isomorphism` — PUBLIC |
| main HEAD | 同 session ***REMOVED***13(三个 PR 都未 merge) |
| PR ***REMOVED***222 | session ***REMOVED***13 — CI 修复 — CI 全绿,待 merge |
| PR ***REMOVED***223 | session ***REMOVED***13 — 首页搜索框方案 A — 待 merge |
| **PR ***REMOVED***224** | **session ***REMOVED***14 — M1.2 fix1/fix4 + M1.3 拒答门 — 47 测试全绿,待 merge** |

***REMOVED******REMOVED*** 2. Session ***REMOVED***14 做了什么

PR ***REMOVED***224(4 commits)。M1.2 / M1.3 体验硬伤修复。

| Commit | 内容 |
|---|---|
| `2936f4d` | **M1.2 fix 1** ASK_MODEL → `deepseek/deepseek-chat:nitro`(TTFT 8-25s→~2-6s,同模型不改答案) |
| `5090e4c` | **M1.3** 真拒答门:out-of-scope 在 `stream()` 本地短路、零 LLM 调用、`_build_refusal_payload` 构造、`answer_done.refused=true`。**M1.2 fix 4** `llm_start` SSE 事件 |
| `9b3f7ff` | 清理 `_build_prompt` low_relevance 死代码(~70 行)+ 沿链参数传递 |
| `297ca77` | 归档 session ***REMOVED***13 文档(HANDOFF / PRODUCT-DIRECTION / M1-experience-fix-research) |

测试:`test_out_of_scope.py` 重写——新增 `RefusalPayloadTests`(6 例纯函数)+ `OutOfScopeStreamTests` 验证零 LLM 调用 / SSE 序列完整 / typewriter 还原。47 ask 测试全绿,ruff 无告警。

***REMOVED******REMOVED*** 3. 用户已拍板决策

按 M1.1 调研报告 §硬伤 1 的"实施顺序建议":**M1.2 Fix1 先单独上线实测 TTFT,再决定 Fix2/3 是否做、做多少**。Fix2/3 暂停。

***REMOVED******REMOVED*** 4. 待用户手动

- merge PR *****REMOVED***222** + *****REMOVED***223** + *****REMOVED***224**:GitHub 网页 "Squash and merge"
- 触发 `deploy-beta-backend` workflow 部署
- 实测 `:nitro` 后的 TTFT 真实分布:
  - dogfood 7 条 query 跑一遍,看首 `answer_chunk` 延迟分布
  - q1-q4(in-scope)预期 TTFT ~2-6s(原 8-25s)
  - q5-q7(out-of-scope)预期首 token ~1-3s + `answer_done.refused=true`

***REMOVED******REMOVED*** 5. 下个 session 起手

根据 TTFT 实测结果分两条路:

- **TTFT 已 ≤6s 且无长尾**:M1.2 Fix2/3 降级或跳过,直接转 **M1.4/M1.5 报告生成器**
- **TTFT 仍有 >10s 长尾**:启 **M1.2 Fix2**(去 json_object 模式)+ **Fix3**(prompt 瘦身)
  - Fix2 的 followups 来源设计待拍板,推荐方案:答案后加 `---FOLLOWUPS---` 分隔符,LLM 在正文后续写 3 条 followups,保留 LLM 质量、单次调用、`_AnswerFieldExtractor` 简化为分隔符前/后两段
  - 另两方案:(b)本地从 KB 派生(质量降)、(c)二次 LLM 调用(成本/延迟升)

***REMOVED******REMOVED*** 6. 遗留

- `scripts/train_v2.py` 工作树有未提交改动(session ***REMOVED***13 起手即存在,***REMOVED***14 按 commit 边界铁律未动)— 需确认归属
- agent 隔离 worktree `.claude/worktrees/agent-a3e2f585dec5d670b` 残留(同 session ***REMOVED***13)
- 三层测试 layer 3(真实环境 e2e):***REMOVED***224 的拒答路径零 OpenRouter $,合并部署后随 §4 dogfood 复跑即可低成本完成
