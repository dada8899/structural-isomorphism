# Session #5 Starter — 交接文档

> Session #4 完成时间：2026-05-14 09:18 CST
> Main HEAD：`b75c5b0`
> 累计 PRs (session #4)：7 个 merged (#46-52)
> 用户身份：达达 (dada8899)，repo PUBLIC
>
> Session #5 起手第一件事：读本文件，运行 §0 起手扫描，然后按 §3 优先级队列推进。

---

## §0 起手 60 秒 — 环境 + 同步扫描

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -5         # HEAD 应该是 b75c5b0 或更新
gh auth status                # 必须 ✓ logged in dada8899
ls .env                       # 本地 DeepSeek key 在这里（gitignored）
```

### 凭证状态

| 凭证 | 位置 | 状态 |
|---|---|---|
| DeepSeek API key (rotated) | `~/Projects/structural-isomorphism/.env` | ✅ 本地 |
| DeepSeek key on VPS | `systemctl show phase-detector-api -p Environment` | ⚠️ 未确认是否更新（用户 rotate 后 VPS 端可能仍是旧 key） |
| GitHub auth | gh CLI | ✅ |
| Repo visibility | PUBLIC | ✅ |
| PYPI_TOKEN | 无 | ❌ 需用户在 pypi.org 创建 |
| ZENODO_ACCESS_TOKEN | 无 | ❌ 需用户在 zenodo.org 创建 |
| arXiv account | n/a | ❌ 用户 web 操作 |

### 关键路径

- 本地 repo：`~/Projects/structural-isomorphism`
- VPS Structural deploy：`/root/Projects/structural-isomorphism/` (非 git 仓库，rsync 部署)
- VPS Phase Detector deploy：`/root/Projects/structural-isomorphism-v4/` (git 仓库，git pull + pnpm build)
- 服务：`structural-web.service` (FastAPI, 5004) + `phase-detector-web.service` (Next.js, 3210) + `phase-detector-api.service` (FastAPI)

### 部署命令（如有变更）

```bash
# Structural 静态前端 + 后端
rsync -av --delete --exclude='.DS_Store' web/frontend/ root@43.156.233.71:/root/Projects/structural-isomorphism/web/frontend/
rsync -av web/backend/main.py root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/main.py
ssh root@43.156.233.71 'systemctl restart structural-web'

# Phase Detector Next.js
ssh root@43.156.233.71 '
cd /root/Projects/structural-isomorphism-v4 && git pull --ff-only
cd web/phase-detector
export NVM_DIR="/root/.nvm" && . "$NVM_DIR/nvm.sh"
pnpm build && systemctl restart phase-detector-web
'
```

---

## §1 Session #4 落地清单（不要重复做）

7 个 PR 全部 merged 到 main + 部署上线 + 实测 verified：

| PR | 主题 | Lines |
|---|---|---|
| #46 | W6-D abstract rewrite + CITATION rebrand + README placeholder | +51/-16 |
| #47 | 全站 copy sweep — V1/V2/V3/V4 sprawl 全清，outcome-first 重写 | +454/-519 |
| #48 | History sidebar — Structural (vanilla JS, 327 LOC) | +456/-2 |
| #49 | Phase Detector SearchHero + parse-query.ts NLU | +679/-8 |
| #50 | History sidebar — Phase Detector (TSX, 190 LOC) | +234/-2 |
| #51 | Cross-link symmetry polish (主站 → Structural ↗ + 姐妹产品) | +17/-2 |
| #52 | 关键修复：Phase filter enum + /start-here 404 + 研究报告卡片删 + cross-link 域名 + analyze breadcrumb + 流式 typewriter preview | +752/-477 |

**总计**：38 文件改动，+2643 / -1026

### 已生效的能力

1. 双站 hero 已 outcome-first（"把你的难题，换成另一个学科已经解过的题" / "谁在崩盘边缘？谁在悄悄起飞？"）
2. Phase Detector 有 Perplexity-style SearchHero（ticker / 中文自然语言 → filter 或 /company/X）
3. 两站均有 history sidebar（localStorage 50 条，desktop 左轨道 / mobile 抽屉）
4. Phase filter 修复了 enum drift（前后端对齐，27 公司可筛 approaching_critical）
5. /start-here 不再 404（后端加路由 + start-here.html 文件已在 frontend dir）
6. analyze 页 breadcrumb 含 `/classes` 确定性返回
7. 流式生成 typewriter preview（chunk.content 实时绘制）
8. V1/V2/V3/V4 + Phase 1-13 + 01-05 pipeline + StructTuple + 模型名（deepseek-v4-pro 等）全站 0 leak（除研究文档 paper.html / papers.html / taxonomy-v2.html 三个 researcher-facing 页面例外）

### Multi-dimensional 打分

总分从 **37.8% → 84.4%**（+47 pts）。9 个维度详细见 session #4 末汇报。新增维度"流式生成体验" 2 → 7。

---

## §2 Defer 到 session #5 的事

按重要性排序：

### P0 — 关键剩余（建议 session #5 起手做）

1. **TL;DR card + analyze 页 section 重排**（user 强需求 + 显眼收益）
   - 当前：analyze 页 §8 "本周行动 / 如果只能做一件事" 是 user 最想看的"答案"，但藏在 8 个理论 section 之后
   - 目标：把 `action_plan.if_time_short` 提升到首屏 TL;DR card；把 §8 + §4 (可借用工具) 放在 §0 (formal math) 之前
   - 文件：`web/frontend/assets/js/analyze.js` SECTIONS 数组 (line 9-19) + `web/frontend/analyze.html` 新增 TL;DR 容器
   - 评估：1.5-2h，纯前端
   - 来源：session #4 Agent C deep-dive 报告

2. **/synthesize endpoint SSE 改造**
   - 当前：`web/backend/api/synthesize.py` 全 blocking，前端 `api.js:85` `synthesize()` 等完整 JSON 才渲染
   - 目标：后端包装为 streaming，前端用 EventSource，main_insight 逐字打出（Perplexity-style）
   - 文件：`web/backend/api/synthesize.py` + `web/frontend/assets/js/api.js` + `web/frontend/assets/js/search.js:171,618`
   - 评估：后端 1.5-2h + 前端 1h
   - 来源：session #4 Agent C "synthesize 全 blocking" 发现

### P1 — 显眼但可缓

3. **Shared CSS tokens 5-var 集中化 + GlossaryTooltip 组件**
   - 双站 design tokens 各自定义；提取 `--brand-ink/paper/accent/line/muted` 到 `web/shared/tokens.css` 服务两站
   - GlossaryTooltip：7 个核心物理 jargon term 加 `?` hover 解释
   - 评估：3-4h（design + 双栈实现）
   - 来源：session #4 UX designer agent 推荐

4. **HuggingFace footer URL 漏出 `v3-structtuple`**
   - footer 链接 hover preview 露出旧 path 片段
   - 修复：包装 `<a>` 文本为 `HuggingFace 数据集` 即可，URL 保留
   - 文件：`web/frontend/index.html` 或 footer partial
   - 评估：5 分钟

5. **Phase Detector 首页 loading flash** "正在加载统计…"
   - SSR 首屏渲染 stats，或加 skeleton rows
   - 文件：`web/phase-detector/app/page.tsx` + `lib/api.ts`
   - 评估：1-1.5h

### P2 — 长期但已 staged

6. **PyPI publish — soc-pipeline + guarded-llm**
   - artifact 已就绪：`packages/soc-pipeline/dist/` + `packages/guarded-llm/dist/`（twine check PASSED）
   - 阻塞：需 user 到 pypi.org 创建 token
   - 等 user 拿 `PYPI_TOKEN` 给 session #5

7. **Zenodo mint DOI for dataset/v1**
   - artifact 已就绪：`/tmp/structural-isomorphism-dataset-v1-2026-05-14.tar.gz` 32MB, sha256 `075378c9ad48b08f611f6b418b7e2acace2064d0d02f8c496f1b4c50759c1793`
   - 阻塞：需 user 到 zenodo.org 创建 token

8. **arXiv submission — C1 v0.3.1 + 4 solo C2 + C4**
   - PDF 已就绪：`/tmp/arxiv-pdfs-2026-05-14/` 共 6 个 PDF（c1-unified-v0.3.1 + c2-01..04 + c4-reject-aware）
   - 阻塞：user web 操作（arXiv 无 API）

9. **GitHub release v0.3.0 / v0.3.1**
   - 等 arXiv ID 拿到后做完整 release notes
   - 或直接 stub release（不带 arXiv ID）

10. **VPS DeepSeek key 同步**
    - 用户已 rotate key，本地 `.env` 已更新，但 VPS `/etc/environment` 可能还是旧 key
    - 检查：`ssh root@43.156.233.71 'systemctl show phase-detector-api -p Environment'`
    - 如果是旧 key，需要 user 提供新 key（或继续用旧 key 直到出错）

---

## §3 Session #5 起手推荐顺序

```
1. §0 起手扫描（git pull / gh auth / .env / VPS DeepSeek key）
2. 用户确认 session #5 是否 PYPI + Zenodo 发布优先 (P2 #6-#9)
   还是 UX 第二轮 (P0 #1-#2 + P1 #3-#5) 优先

如果用户选 UX 第二轮：
  3a. TL;DR card + section 重排（P0 #1）
  3b. /synthesize SSE 改造（P0 #2）
  3c. Shared CSS tokens + GlossaryTooltip（P1 #3）
  3d. 多 agent verification + 打分 +5 分
  3e. ship

如果用户选发布路径：
  3f. 用户在 pypi.org + zenodo.org 创建 token
  3g. 执行 SESSION-4-STARTER.md §2 Step 5/6/7/8/9
```

---

## §4 项目结构速查

```
~/Projects/structural-isomorphism/
├── web/
│   ├── frontend/          # Structural 静态 HTML+JS (13 页)
│   │   ├── index.html     # 首页（hero + examples + waitlist + sister-product callout）
│   │   ├── classes.html   # /classes 共享模式（user 认为这是"真首页"）
│   │   ├── search.html, analyze.html, discoveries.html ...
│   │   ├── start-here.html  # /start-here 长文（PR-7 修复了 routing）
│   │   └── assets/
│   │       ├── js/        # i18n / utils / search / analyze / history-sidebar / ...
│   │       └── css/
│   ├── phase-detector/    # Phase Detector Next.js
│   │   ├── app/page.tsx   # 首页（含 SearchHero）
│   │   ├── app/layout.tsx # 顶栏 + footer + HistorySidebar
│   │   ├── app/company/[ticker]/page.tsx
│   │   ├── app/about, methodology, thank-you
│   │   ├── components/{SearchHero, HistorySidebar, ScreenerFilter, ...}
│   │   └── lib/{types, labels, api, parse-query, history, mock-data}.ts
│   └── backend/           # FastAPI (port 5004)
│       ├── main.py        # 主路由 (PR-7 新增 /start-here)
│       └── api/{analyze, synthesize, ...}.py
├── packages/
│   ├── soc-pipeline/dist/  # PyPI artifacts (twine check PASSED, 待 publish)
│   └── guarded-llm/dist/
├── dataset/v1/             # 99MB, 244 文件, 待 Zenodo
├── paper/
│   ├── v0-unified-pipeline-2026-05-13.md  # C1 unified v0.3.1
│   ├── arxiv-drafts/2026-05-13/01..04_*.md  # 4 solo C2
│   └── c4-reject-aware-pipeline-2026-05-13.md
└── docs/sessions/
    ├── HANDOFF.md
    ├── SESSION-4-STARTER.md  # session #3 末交给 #4 的清单
    └── SESSION-5-STARTER.md  # 本文件
```

---

## §5 不可逆操作清单（注意！）

session #5 任何动作都要先确认：

| 动作 | 可逆 | 备注 |
|---|---|---|
| 改前端 / 后端 / 文档代码 | ✅ | git 可回退 |
| 部署到 VPS | ✅ | 重新部署 PR 之前的 commit 即可回滚 |
| `gh pr merge --squash` | ✅ | git revert 可撤 |
| `git push origin main` | ✅ | force-push 才不可逆，普通 push 可 revert |
| **PyPI upload** | ❌ | 同 version 不可重新上传，只可 yank |
| **Zenodo DOI publish** | ❌ | DOI 永久 |
| **arXiv submit** | ⚠️ | 有 withdraw 但不鼓励 |
| **git-filter-repo + force-push** | ❌ | 重写历史不可逆（session #4 已决策 Path A：rotate key only，不 scrub） |
| **delete repo / branch on GitHub** | ❌ | 需用户授权 |

---

## §6 已知 quirks

1. **/index.html 404**（clean URL `/` 200）— canonical URL 唯一，非 bug
2. **/start-here.html 404**（clean URL `/start-here` 200）— 同上
3. **paper.html / papers.html / taxonomy-v2.html 保留物理 jargon + LaTeX** — researcher-facing 例外，PR-1 style guide §F 决策
4. **/root/Projects/structural-isomorphism 不是 git 仓库** — Structural 通过 rsync 部署
5. **DeepSeek key in PUBLIC git history**（commits `aa044dd / 3e7bd95 / a88dbef / fb9a41d / ed9d73e`）— Path A 决策：rotate-only，不 scrub。OpenRouter key (`sk-or-v1-af9ae735...`) 也在 history，**待 user 确认是否已在 OpenRouter 平台 revoke**
6. **`/tmp/secret-replacements.txt`** 保留为 artifact，但 force-push scrub 不执行

---

## §7 Session #5 起手 prompt 模板

如果用户想换 prompt 直接告诉 session #5 Claude：

```
读 docs/sessions/SESSION-5-STARTER.md。

[option A — 继续 UX 优化]
按 §2 P0 项目 1 (TL;DR card + section 重排) 起手，
然后 P0 项目 2 (synthesize SSE)，然后 P1 polish。
全权 auto mode。

[option B — 发布路径]
我准备好了 PYPI_TOKEN=xxx 和 ZENODO_ACCESS_TOKEN=xxx。
按 SESSION-4-STARTER.md §2 Step 5/6 起手，
然后 §2 Step 7/8/9 等我投完 arXiv 再做。
```

---

**Session #4 结束**。HEAD `b75c5b0`，7 PRs，UX 总分 37.8% → 84.4%（+47 pts）。

Next session 入口：本文件 §0 → §3。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
