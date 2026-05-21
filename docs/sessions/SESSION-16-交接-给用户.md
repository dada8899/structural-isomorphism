***REMOVED*** Session ***REMOVED***16 交接文档（人话版）

> 给下个 CC session 的技术版：`SESSION-16-HANDOFF.md` / `SESSION-17-START-PROMPT.md`
> 本文档是给项目负责人看的「人话版」。
> 日期：2026-05-21

---

***REMOVED******REMOVED*** 一句话总结

这个 session 把 **M1.4 报告生成器** 从 0 做到端到端上线 prod，顺手清了 session ***REMOVED***15 那次「5 天哑炮」事故的根因，修了一轮独立审查发现的安全漏洞。**16 个 commit，全部已上线 beta.structural.bytedance.city。**

---

***REMOVED******REMOVED*** 1. 这个 session 做完了什么

***REMOVED******REMOVED******REMOVED*** 主线：M1.4 报告生成器（5 个 PR 全部完成）

之前 `/api/analyze/stream` 能生成 9 段研究报告，但报告**关掉就没了**——不能存、不能分享、不能反馈。现在：

| 能力 | 之前 | 现在 |
|---|---|---|
| 保存报告 | ❌ 只在缓存里 | ✅ 存进数据库，有永久 ID |
| 分享给别人 | ❌ | ✅ 生成 `…/report/share/<token>` 链接，对方无需登录可看 |
| 查看历史 | ❌ | ✅ `/api/reports/mine` 按设备列出（后端就绪，列表页 UI 待做） |
| 反馈有用/没用 | ❌ | ✅ 每段 + 整体 👍/👎 按钮 |

***REMOVED******REMOVED******REMOVED*** 配套修的事

- **`/api/version` 升级**：现在返回 `model` / `git_sha` / `deployed_at`——一条命令 `scripts/dogfood_fingerprint.py` 就能查 prod 跑的是不是最新代码。**这直接堵死了 session ***REMOVED***15「prod 跑老代码 5 天没人发现」的事故**。
- **deploy 流程加 fingerprint 校验**：以后 deploy 完如果 prod 代码跟推的不一致，CI 立即报错，不会再哑炮。
- **q7 预测拦截**：用户问「AI 能不能预测股票」这类问题，现在会礼貌拒答（不硬拗），prod 已验证生效。
- **CI 加 runtime smoke test**：每晚自动装 prod 依赖跑一遍，防依赖漂移。
- **独立 Validator 审查**：派了个独立 agent 审 M1.4 代码，揪出 1 个严重漏洞（分享 token 密钥可被预测）+ 3 个 bug + 6 个小问题，**全部修掉**。

---

***REMOVED******REMOVED*** 2. 当前 prod 状态（已验证）

```
站点    https://beta.structural.bytedance.city
代码    git_sha 5c31bc1 —— 已是最新 main，含 M1.4 全部
模型    deepseek/deepseek-chat:nitro
环境    prod，健康，知识库 4443 条
M1.4    后端 + 前端 + 分享页全部上线，可用
```

---

***REMOVED******REMOVED*** 3. 你需要知道的几件事

1. **那个分享密钥永远不要动**
   这个 session 在 VPS `.env` 里设了 `STRUCTURAL_SHARE_TOKEN_SECRET`。它**一旦 rotate（更换），所有已经分享出去的报告链接全部失效**。已备份在 VPS 的 `.env.bak-*`。别删别改。

2. **报告生成实测很慢**
   实测一份完整报告 prod 上 >180 秒（9 段只生成了 6 段就超时）。不要对用户承诺「1-2 分钟出报告」。这不是 M1.4 引入的——是底层 LLM 调用本来就慢，未来要单独优化。

3. **有几件事只有你能做**（CC 权限够不到）
   - DeepSeek API key 轮换（安全债，建议尽快）
   - PyPI / arXiv / Zenodo / HuggingFace 发布——都缺 token / 账号
   - 这些不影响 M1.4 上线，是独立的发布类工作

---

***REMOVED******REMOVED*** 4. 下一步建议（优先级排序）

| 优先级 | 事项 | 估时 | 谁做 |
|---|---|---|---|
| 高 | M1.4 Playwright e2e——真浏览器把分享+反馈流程跑一遍锁死 | 2-3h | 下个 CC session |
| 中 | "My Reports" 历史列表页（后端已就绪，缺 UI） | 2-3h | 下个 CC session |
| 低 | 清掉剩余 30 个废弃 git 分支（`./scripts/cleanup-stale-branches.sh` 一行） | 5min | 你跑 / CC |
| 低 | V4 跨域同构库扩展 / OSS 对外发布 | 长周期 | 看情况 |

下个 session 起手直接说「读 `docs/sessions/SESSION-17-START-PROMPT.md`」即可。

---

***REMOVED******REMOVED*** 5. 数字总账

- 19 个任务：18 完成 + 1（prod 密钥，已在 session 末解锁）
- 16 个 commit 到 main
- 88/88 M1.4 测试绿（374/374 整套后端绿）
- ~3,900 行净新增（后端 + 前端 + 测试 + 文档）
- Validator 找的 1 P0 + 3 P1 + 6 P2 全修
- 全程没碰 `scripts/train_v2.py`（那是别的 session 的在途工作）

---

***REMOVED******REMOVED*** 6. 关键文件索引

| 文件 | 用途 |
|---|---|
| `docs/sessions/SESSION-17-START-PROMPT.md` | 下个 session 起手 prompt |
| `docs/sessions/SESSION-16-HANDOFF.md` | 技术版完整交接（16 commit 全表） |
| `docs/sessions/M1.4-report-generator-prd.md` | M1.4 设计文档 + 决策 |
| `docs/sessions/M1.4-frontend-integration-guide.md` | 前端集成规格（e2e 场景在 §5） |
| `docs/api/analyze-stream-spec.md` | `/api/analyze/stream` 接口契约 |
| `docs/deployment/env-override-policy.md` | prod `.env` 该有/不该有什么 |
| `scripts/dogfood_fingerprint.py` | 一行命令查 prod 状态 |
| `scripts/cleanup-stale-branches.sh` | 清废弃分支（30 个待清） |
