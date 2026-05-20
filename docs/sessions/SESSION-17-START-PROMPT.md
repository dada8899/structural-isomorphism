# 起手:structural-isomorphism / M1.4 PR #5 (frontend share + feedback)

> Session #17 起手 prompt(浓缩版)。完整交接见 `SESSION-16-HANDOFF.md`,M1.4 设计见 `M1.4-report-generator-prd.md`,前端规格见 `M1.4-frontend-integration-guide.md`。

**项目**:`~/Projects/structural-isomorphism/`(repo: `dada8899/structural-isomorphism`, PUBLIC)
**上一 session**:#16。

---

## 当前 prod 状态(verified 2026-05-21)

main HEAD:`8543bc1` (test isolation fix) → 12 个 commit 走完 M1.4 backend slice。

**起手第一件事:fingerprint check**
```bash
python3 ~/Projects/structural-isomorphism/scripts/dogfood_fingerprint.py
```
应看到 ✅。看不到立刻怀疑 deploy 没真上线(session #15 血泪教训)。

**第二件事:确认 P0 已解锁** —— 上一 session 留了一个用户必须做的 P0:
```bash
# SSH VPS,看 .env 是否已设 share token secret
ssh root@43.156.233.71 'grep STRUCTURAL_SHARE_TOKEN_SECRET /root/Projects/structural-isomorphism/web/backend/.env || echo "[MISSING - generate first]"'
```
如果 MISSING:
```bash
# 用户生成 + 注入(只做一次,rotate 会破坏所有现有 share URL):
ssh root@43.156.233.71 'python3 -c "import secrets; print(\"STRUCTURAL_SHARE_TOKEN_SECRET=\" + secrets.token_hex(32))" >> /root/Projects/structural-isomorphism/web/backend/.env && systemctl restart structural-web'
```

---

## 下一站:M1.4 PR #5 — 前端 share + feedback

**目标**:把 backend 已经做完的 persist + share + feedback endpoint 接到前端。

**完整规格在**:`docs/sessions/M1.4-frontend-integration-guide.md`(202 行)。三件套:
1. `analyze.html` 加 "💾 Save & share" 复选框 + SSE `persisted` 事件处理 + share bar 渲染
2. 新 `report.html` 页面(`/report/share/<token>` + `/report/<id>` 两条路由共用)
3. 每个 section 加 👍/👎 按钮 + 整体 👍/👎 + 5 个 Plausible 事件

**估时**:< 1 天。所有 backend endpoint + 87 个测试已就绪。

---

## M2 / 长尾 backlog(按触发捡)

| # | 工程债 | 触发 |
|---|---|---|
| A | Validator P2:`text_a` max_length / async-blocking subprocess in /api/version dev path / payload size validation | M1.4 PR #5 后顺手 |
| B | cleanup-stale-branches.sh 一键删 36 merged | 任意时间(用户确认) |
| C | 124 unmerged stale branch 按 heuristic 删 | 同上,逐条判断 |
| D | cross-judge v1.1 异步 critique pass | 报告周量 ≥ 100 |
| E | "My reports" 列表页(`/api/reports/mine` endpoint 已就绪) | 用户问起 |

---

## 用户授权阻塞(CC 推不动)

| 优先级 | 动作 | 阻塞 |
|---|---|---|
| 🔴 P0 | 设 `STRUCTURAL_SHARE_TOKEN_SECRET` in prod .env | M1.4 share 在 prod 拒绝工作 |
| 🟡 P1 | DeepSeek API key rotate | 安全债 |
| 🟡 P1 | PYPI_TOKEN | 3 包发布 |
| 🟡 P1 | arXiv 上传 5 papers | 学术 outreach |

---

## 工作纪律(项目级,持续)

- `scripts/train_v2.py` 是别 session in-flight,**不要动**(git status 会显示 M,跳过)
- `.claude/worktrees/agent-a3e2f585dec5d670b/` harness 自己回收,**不要清**
- 每完成一个 PR 立即 commit + push(不积累)
- 显式 `git add <file>`,**禁** `git add -A` / `commit -a`
- **数据反常先怀疑 deploy 没真上线,后怀疑代码**
- M1.4 PR #5 上线后,派 4 个 reviewer(marketing / UX / security / i18n)+ Validator 独立审

---

## 关键文件 / 命令

- `docs/sessions/SESSION-16-HANDOFF.md` — 完整 session #16 交接(12 commits 全表)
- `docs/sessions/M1.4-frontend-integration-guide.md` — PR #5 的"该怎么写"
- `docs/api/analyze-stream-spec.md` — 最新 wire format(含 `persisted` 事件)
- `docs/deployment/env-override-policy.md` — prod env 该有 / 不该有什么
- `scripts/dogfood_fingerprint.py` — 一行命令查 prod 状态
- VPS deploy: `gh workflow run "Deploy Beta Backend"` 自动走 dispatcher,失败会在新加的 fingerprint verify step 中立即报错
