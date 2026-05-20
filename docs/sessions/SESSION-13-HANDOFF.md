# Session #13 交接文档

> 2026-05-20。供下个 session 起手用。上个交接见 `SESSION-12-HANDOFF.md`（已过时，以本文为准）。

## 1. 当前状态快照

| Item | Value |
|---|---|
| repo | `dada8899/structural-isomorphism` — PUBLIC |
| main HEAD | session-12 handoff commit 后未变（session #13 的改动都在 PR 里，未 merge） |
| PR #222 | CI 修复（4 commit + backlog doc）— **CI 全绿，待 merge** |
| PR #223 | 首页搜索框方案 A — 待 CI / 待 merge |
| prod | beta backend 2026-05-20 deploy success（5 天来首次）|

## 2. Session #13 做了什么

- **6 项 CI 清尾**（handoff §5 Option B）→ PR #222。每项实测复现根因，纠正了 handoff 的错误猜测：
  - ask.py coverage 54.3% = `coverage.yml` 缺 `python-dotenv`+`pyyaml`
  - soc-pipeline 5 测试失败 = `__init__.py` import 覆盖 bug（pandas_accessor 的 Verdict 静默 shadow validate.py 的）
  - frontend CI 死 = `ci.yml` 用 npm 但项目是 pnpm，`package-lock.json` 不存在
  - mkdocstrings 升 1.x；storybook 核实无需改
- **deploy-beta-backend** 手动 trigger 验证 F12 fix → success
- **首页搜索框方案 A**（克制收敛版）→ PR #223
- **产品化方向调研**（3 路 agent）→ 见下方文件

## 3. 关键文件入口

| 文件 | 用途 |
|---|---|
| `SESSION-13-BACKLOG.md` | session #13 后完整 backlog，5 类 ~35 项，含 top 5 优先级 |
| `SESSION-13-PRODUCT-DIRECTION.md` | 产品化延伸方案：定位重构 / 楔子人群 / 三层漏斗 / 路线图 |
| `SESSION-13-M1-experience-fix-research.md` | M1 体验硬伤根因调研 + 修复方案（实施直接照此） |

## 4. 下一步：M1 — 修体验硬伤 + 跨域类比报告生成器

用户已拍板的产品化第一步。任务清单（task tracker）M1.1–M1.5：

- **M1.1** 体验硬伤根因调研 — ✅ 完成（`SESSION-13-M1-experience-fix-research.md`）
- **M1.2** 修首 token 延迟（18–32s）— 待做。先改 `ASK_MODEL` 换快模型（10min 立即见效），再去 JSON 模式 / prompt 瘦身。~1.5–2 人天
- **M1.3** out-of-scope 真拒答门 — 待做。`stream()` 加本地拒答短路分支。~1 人天
- **M1.4** 报告生成器后端 — 复用 `analyze.py` query-mode + cross-judge 质量闸门
- **M1.5** 报告生成器前端 + PDF 导出 + 分享链接

起手顺序：M1.2 / M1.3 先（体验硬伤是留存前提，都在 `ask_orchestrator.py`，注意 commit 边界）→ M1.4 → M1.5。按项目流程分模块写、每模块测试通过再下一个。

## 5. 待用户手动

- merge PR **#222**（全绿）+ **#223**：GitHub 网页 "Squash and merge"
- 可选：`/permissions` 配 `Bash(gh pr merge:*)` / `Bash(gh workflow run:*)`，让 CC 以后能直接 merge/deploy（auto-mode classifier 对这类高危操作硬拦，不认 AskUserQuestion 授权）

## 6. 遗留

- `scripts/train_v2.py` 工作树有未提交改动（session #13 起手即存在，非本 session 产生，未动）— 需确认归属
- agent 隔离 worktree `.claude/worktrees/agent-a3e2f585dec5d670b` 残留（locked，内部有 LFS smudge 退化但未污染任何 commit）— harness 回收
