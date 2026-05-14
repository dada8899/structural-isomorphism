# Session #6 Starter — 交接文档

> Session #5 完成时间：2026-05-14 12:30 CST（约）
> Main HEAD：`4b9f888`
> 累计 PRs (session #5)：9 个 merged (#54-#62)
> 用户身份：达达 (dada8899)，repo PUBLIC
>
> Session #6 起手第一件事：读本文件 §0，运行起手扫描，然后按 §3 的优先级队列推进。

---

## §0 起手 60 秒 — 环境 + 同步扫描

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -5         # HEAD 应该是 4b9f888 或更新
gh auth status               # 必须 ✓ logged in dada8899
ls .env                      # 本地 DeepSeek key（gitignored）
```

### 凭证状态

| 凭证 | 位置 | 状态 |
|---|---|---|
| DeepSeek API key (rotated) | `~/Projects/structural-isomorphism/.env` | ✅ 本地 |
| DeepSeek key on VPS | `systemctl show phase-detector-api -p Environment` | ⚠️ 未确认（用户 rotate 后 VPS 端可能仍是旧 key，session #5 没碰）|
| GitHub auth (gh CLI) | keyring | ✅ |
| Repo visibility | PUBLIC | ✅ |
| OpenRouter key (Haiku 4.5 / synthesize endpoint) | VPS env | ✅ 工作中 |
| PYPI_TOKEN | 无 | ❌ 需用户在 pypi.org 创建 |
| ZENODO_ACCESS_TOKEN | 无 | ❌ 需用户在 zenodo.org 创建 |
| arXiv account | n/a | ❌ 用户 web 操作（无 API）|

### 关键路径（活的产线）

| 角色 | 域名 | 部署位置 | service |
|---|---|---|---|
| **Structural app** (FastAPI) — 用户实际访问 | `beta.structural.bytedance.city` | `/root/Projects/structural-isomorphism/web/{frontend,backend}/` | `structural-web` (5004) |
| Structural 学术老站 (静态 HTML，仅 / + /paper-zh.html) | `structural.bytedance.city` | `/root/Projects/structural-isomorphism/site/` | nginx 直供 |
| **Phase Detector** (Next.js) | `phase.bytedance.city` | `/root/Projects/structural-isomorphism-v4/web/phase-detector/` (git 仓库) | `phase-detector-web` (3210) + `phase-detector-api` |

> **⚠️ 注意路径区分**：rsync 部署去的是 `web/frontend/`，活的产线是 `beta.` 子域。`structural.` 主域是 4 月遗留的学术静态页，不要 rsync 到 `/site/`。Session #5 PR-1 部署时撞过这个坑（详见 §6 quirks）。

### 部署命令（session #5 验证过）

```bash
# Structural 前端 + 后端 → beta.structural.bytedance.city
cd ~/Projects/structural-isomorphism
rsync -av --delete --exclude='.DS_Store' web/frontend/ \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/frontend/

# 后端改了的话也 rsync
rsync -av web/backend/api/<changed>.py \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/api/<changed>.py
rsync -av web/backend/services/<changed>.py \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/services/<changed>.py

ssh root@43.156.233.71 'systemctl restart structural-web && sleep 2 && systemctl is-active structural-web'

# Phase Detector → phase.bytedance.city
ssh root@43.156.233.71 '
cd /root/Projects/structural-isomorphism-v4 && git pull --ff-only origin main
cd web/phase-detector
export NVM_DIR="/root/.nvm" && . "$NVM_DIR/nvm.sh"
pnpm build && systemctl restart phase-detector-web && sleep 1 && systemctl is-active phase-detector-web
'
```

> **Backend rsync 多文件陷阱**：`rsync -av a.py b.py target/path.py` 会失败（多源单 dest）。每次只 rsync 一个文件 OR 整目录。

---

## §1 Session #5 落地清单（不要重复做）

9 个 PR 全部 merged 到 main + 部署上线 + smoke 通过：

| PR | 主题 | Files / LOC |
|---|---|---|
| #54 | TL;DR 卡片 + /synthesize SSE + footer "HuggingFace 数据集" | 20 files, +669/-61 |
| #55 | 共享品牌 token (5-var canonical) + SSE markdown fence-strip | 22 files, +547/-41 |
| #56 | StatsBar skeleton — 干掉 "正在加载统计…" flash | 1 file, +38/-2 |
| #57 | GlossaryTooltip — 7 jargon hover 解释 (auto-wrap) | 13 files, +413 |
| #58 | /search 立即出卡，不等 synth | 2 files, +43/-19 |
| #59 | daily-grid skeleton + sector dropdown disabled-while-loading | 4 files, +96/-26 |
| #60 | hero-evidence__desc line-clamp:3 + min-height (无高度抖动) | 1 file, +11 |
| #61 | /analyze 在 meta arrival 隐藏 loading block | 2 files, +26/-14 |
| #62 | 修 PR-8 在 error/retry 路径的 regression | 3 files, +41/-18 |

**总计**：68 文件改动，+1884 / -181 LOC。

### 已生效的能力

1. **/analyze 答案前置**：TL;DR 卡片直接显示 `action_plan.if_time_short`；section 顺序重排（action_plan + borrowable_insights 在 shared_structure 之前）
2. **/search Perplexity-style 流式**：`main_insight` 字符级打字 + blinking caret + rewritten-search 中途 abort 安全
3. **/search 立即可读**：vector results ~200ms 即出卡，不等 synth；synth done 后 rebuild 加 primary_recommendation 标注
4. **GlossaryTooltip**：临界翻转/级联/放缓/边缘 + 普适类 + 标度律 + 临界假说 7 词 hover 解释；MutationObserver 兼容 SSE 动态内容；mobile tap-toggle + Esc + 键盘导航
5. **跨站设计 token 中心化**：`web/shared/tokens.css` 5-var canonical + 2 mirror + sync 脚本（drift detection）
6. **4 处 layout-shift 全部 reserve**：StatsBar / daily-grid / sector dropdown / hero-evidence 高度
7. **/analyze loading 噪音降低**：原 4 个 "still working" 信号 → 3 个；保留 error/retry 路径的可恢复性

### Multi-dimensional 打分（粗估）

session #4 末 84.4% → session #5 末预计 **88-90%**（+4-6 pts），主要在：
- 流式生成体验（synth 端从 "等完才出" → "字符流"）
- 首屏可见性（TL;DR 卡 + instant cards）
- Layout 稳定性（4 处 CLS 修）
- Jargon 可学习性（GlossaryTooltip）

session #6 起手如果走多 agent verification，可补充打分。

---

## §2 Defer 到 session #6 的事

按重要性排序：

### P0 — 发布路径（等用户给凭证）

1. **PyPI publish — `soc-pipeline` + `guarded-llm`**
   - artifact 已就绪：`packages/soc-pipeline/dist/` + `packages/guarded-llm/dist/`（twine check PASSED）
   - 阻塞：需 user 到 pypi.org 创建 token
   - 用户给 `PYPI_TOKEN` 后，session #4 SESSION-4-STARTER.md §2 Step 5 直接跑

2. **Zenodo mint DOI for dataset/v1**
   - artifact 已就绪：`/tmp/structural-isomorphism-dataset-v1-2026-05-14.tar.gz` 32MB
   - sha256: `075378c9ad48b08f611f6b418b7e2acace2064d0d02f8c496f1b4c50759c1793`
   - ⚠️ `/tmp` 在重启会失（VPS Mac 都一样）；先验证文件还在，没在的话从 dataset/v1 重新打包
   - 阻塞：需 user 到 zenodo.org 创建 token

3. **arXiv submission — C1 v0.3.1 + 4 solo C2 + C4**
   - PDF 已就绪：`/tmp/arxiv-pdfs-2026-05-14/` 共 6 个 PDF — 同 `/tmp` 风险，需先验证
   - 阻塞：user web 操作（arXiv 无 API）

4. **GitHub release v0.3.0 / v0.3.1**
   - 等 arXiv ID 拿到后做完整 release notes
   - 或直接 stub release（不带 arXiv ID）

5. **VPS DeepSeek key 同步**（如果用户 rotate 过）
   - 检查：`ssh root@43.156.233.71 'systemctl show phase-detector-api -p Environment | grep -i deepseek'`
   - 如果是旧 key，需要 user 提供新 key（或继续用旧 key 直到出错）

### P1 — UX 第三轮（自助可推进，无凭证依赖）

6. **/analyze 端到端真实环境测试**
   - PR #54-#62 全部部署但 session #5 没用浏览器跑过完整流（只 curl SSE 头几个 chunk）
   - Playwright MCP 跑一遍：触发一个 query → 等 60s 完整生成 → 验证 TL;DR 卡填充 + 9 sections 顺序 + GlossaryTooltip 在 dynamic content 上能 wrap
   - 估计 30 min

7. **/search 端到端真实环境测试**
   - 同上：搜一个真实 query → 验证 instant cards + typewriter caret + synth done 后的 rebuild 不闪
   - 截图保留比对

8. **mobile 视口审计 (375px)**
   - 没在 session #5 跑过。重点检查：
     - TL;DR 卡 mobile 布局（CSS 已写 `.analyze-tldr` 768px 切单列）
     - GlossaryTooltip arrow 在 viewport 边缘的位置
     - 新 skeleton 在 mobile 是否正确缩
   - 估计 1h

9. **Plausible analytics 自定义事件**（如果时间够）
   - W4-B G3 阶段已埋了 `data-domain`，但没显式自定义事件（`tldr_card_shown` / `synth_streaming_started` / `glossary_tooltip_opened`）
   - 加上后能量化 PR-1/2/4 真实使用率
   - 估计 1.5h

10. **/discoveries 页 layout shift**
    - PR-6 修了 homepage 的 daily-grid，但 `/discoveries` 完整列表页 (#disc-hero-stats / #disc-filter / #disc-list) 没修
    - 同模式 skeleton 抽出去服用即可（PR-6 新加的 `.skeleton-bar` 可复用）
    - 估计 30 min

### P2 — 长期 staged

11. **GlossaryTooltip 第二批词汇**（content review 后）
    - 当前只 7 词。session #5 选词基于 grep "在用户页出现"
    - 候选追加：相变 / 标度形式 / 涌现 / 反馈环 / 阈值效应（约 5 词）
    - 触发：用户基于真实 read-through 反馈或 Plausible 事件指出 "这个词不懂"
    - 估计 30 min（纯加 entries 到 GLOSSARY map）

12. **Phase Detector SSR for stats**（PR-3 deferred）
    - 当前 stats 异步 fetch，PR-3 用 skeleton 兜底
    - SSR via Server Component wrapper 是更彻底的方案，但需重构 page.tsx 的 client-server 边界
    - 估计 2-3h（需要把 useState/useEffect 的 filters/search 抽到子组件）

---

## §3 Session #6 起手推荐顺序

```
1. §0 起手扫描（git pull / gh auth / .env / VPS service status）
2. 验证 /tmp artifact 是否还在 (PyPI dist + Zenodo tar + arXiv PDFs)
   - 在：用户给 token 时直接跑发布
   - 不在：从 packages/ 重 build + dataset/v1 重打包

3. 用户决策：本 session 走哪条路？
   A. 发布优先（P0 #1-#5 + #4）— 需要用户先给 token
   B. UX 第三轮（P1 #6-#10）— 自助可推
   C. 双轨：先做 P1 #6+#7 验证 session #5 的 9 PRs 没 regression，
            等用户给 token 中途再切发布
```

**默认推荐 C**：先 30min Playwright e2e 跑 /analyze + /search，确认 PR #54-#62 真实可用 + 截图存档，再视用户授权切别的轨。

---

## §4 项目结构速查（session #5 后）

```
~/Projects/structural-isomorphism/
├── web/
│   ├── frontend/              # Structural 静态 HTML+JS (14 user pages + 3 researcher)
│   │   ├── index.html         # 首页（hero-evidence 自动轮播 + daily-grid skeleton + cross-product）
│   │   ├── classes.html       # 共享模式
│   │   ├── search.html        # 搜索结果 (instant cards + SSE typewriter)
│   │   ├── analyze.html       # 深度分析 (TL;DR card + 9 sections, action_plan first)
│   │   ├── discoveries.html, methods.html, about.html, papers.html, ...
│   │   ├── start-here.html    # /start-here 长文
│   │   └── assets/
│   │       ├── js/            # i18n / utils / api (SSE) / search / analyze / glossary / 
│   │       │                    history-sidebar / home / classes / discoveries / phenomenon
│   │       └── css/           # design-system / common / search / analyze / glossary / 
│   │                            shared-tokens (mirror) / responsive / home
│   ├── phase-detector/        # Phase Detector Next.js (phase.bytedance.city)
│   │   ├── app/page.tsx       # 首页（含 SearchHero）
│   │   ├── app/layout.tsx     # 顶栏 + footer + HistorySidebar
│   │   ├── app/company/[ticker]/page.tsx
│   │   ├── app/{about,methodology,thank-you}
│   │   ├── app/globals.css    # 引 ./shared-tokens.css (mirror) + Tailwind
│   │   ├── app/shared-tokens.css  # ← byte-identical mirror of web/shared/tokens.css
│   │   ├── components/{SearchHero, HistorySidebar, ScreenerFilter, StatsBar, ...}
│   │   └── lib/{types, labels, api, parse-query, history, mock-data}.ts
│   ├── shared/                # ← session #5 PR-2 新增
│   │   ├── tokens.css         # canonical 5-var brand palette (--brand-ink/paper/accent/line/muted)
│   │   ├── sync-tokens.sh     # cp tokens.css 到 frontend + phase-detector mirrors，verify byte-identical
│   │   └── README.md
│   └── backend/               # FastAPI (port 5004)
│       ├── main.py
│       └── api/{analyze, synthesize, search, suggest, daily, examples, mapping, phenomenon, discoveries}.py
│         (synthesize.py 暴露 POST /synthesize + POST /synthesize/stream — 后者是 PR-1 SSE)
├── packages/
│   ├── soc-pipeline/dist/     # PyPI artifacts (twine check PASSED, 待 publish)
│   └── guarded-llm/dist/
├── dataset/v1/                # 99MB, 244 文件, 待 Zenodo
├── paper/
│   ├── v0-unified-pipeline-2026-05-13.md  # C1 unified v0.3.1
│   ├── arxiv-drafts/2026-05-13/01..04_*.md
│   └── c4-reject-aware-pipeline-2026-05-13.md
└── docs/sessions/
    ├── HANDOFF.md
    ├── SESSION-4-STARTER.md   # 仍 valid 的 publishing runbook (PyPI/Zenodo/arXiv 步骤)
    ├── SESSION-5-STARTER.md   # session #4 末 → #5 的入口
    └── SESSION-6-STARTER.md   # 本文件
```

---

## §5 不可逆操作清单（session #6 任何动作前确认）

| 动作 | 可逆 | 备注 |
|---|---|---|
| 改前端 / 后端 / 文档代码 | ✅ | git 可回退 |
| 部署到 VPS（rsync + restart） | ✅ | rsync 上一个 commit 即可回滚 |
| `gh pr merge --squash` | ✅ | git revert 可撤 |
| `git push origin main` | ✅ | force-push 才不可逆 |
| **PyPI upload** | ❌ | 同 version 不可重新上传，只可 yank |
| **Zenodo DOI publish** | ❌ | DOI 永久 |
| **arXiv submit** | ⚠️ | 有 withdraw 但不鼓励 |
| **git-filter-repo + force-push** | ❌ | 重写历史不可逆（Path A 决策：rotate key only，不 scrub） |
| **delete repo / branch on GitHub** | ❌ | 需用户授权 |
| **修改 web/shared/tokens.css** | ✅ | 必跑 `web/shared/sync-tokens.sh` 同步 mirrors，否则双站 drift |

---

## §6 已知 quirks（session #5 新增 + 老的）

### 老的（session #4 留下）
1. **/index.html 404**（clean URL `/` 200）— canonical URL 唯一，非 bug
2. **/start-here.html 404**（clean URL `/start-here` 200）— 同上
3. **paper.html / papers.html / taxonomy-v2.html 保留物理 jargon + LaTeX** — researcher-facing 例外，PR-1 §F style guide。**Session #5 PR-4 的 GlossaryTooltip 也跳过这 3 页**
4. **/root/Projects/structural-isomorphism 不是 git 仓库** — Structural 通过 rsync 部署
5. **DeepSeek key 在 PUBLIC git history**（commits `aa044dd / 3e7bd95 / a88dbef / fb9a41d / ed9d73e`）— Path A 决策：rotate-only，不 scrub
6. **`/tmp/secret-replacements.txt`** 保留为 artifact，但 force-push scrub 不执行

### Session #5 新增

7. **`structural.bytedance.city` 主域 ≠ 活的产线**：主域 nginx serves `/root/Projects/structural-isomorphism/site/` (4 月学术静态页，仅 / + paper-zh.html 等)。活的产线是 `beta.structural.bytedance.city`，FastAPI 服务 5004 端口。Session #5 PR-1 部署时撞过这个坑——`curl https://structural.bytedance.city/api/synthesize/stream` 返回 405 不是 bug，因为主域 nginx 不 proxy /api。

8. **rsync 多源单 dest 会失败**：`rsync a.py b.py target/path.py` —— 只 rsync 一个文件或整目录。Session #5 PR-1 部署时撞到，Backend 改 2 个文件需 2 次 rsync。

9. **OpenRouter Haiku 4.5 偶尔输出 ```json ... ``` 包裹 JSON**：尽管 prompt 明令禁止。`stream_synthesize_answer` 已加 fence-strip（PR-2），但**未来如果换模型或加新 endpoint 调 OpenRouter**，记得复用 `assess_query` line 156-158 的 fence-strip 逻辑。

10. **GlossaryTooltip 只 wrap FIRST occurrence per page**：故意设计（避免视觉噪音）。如果用户反馈 "第二次提到没解释"，是 by design。改成 ALL occurrence 风险是页面会被点点点点点点淹没。

11. **`web/shared/tokens.css` 改了必须跑 sync-tokens.sh**：3 处文件（canonical + 2 mirror）必须 byte-identical。CI 没强制（TODO），靠人肉纪律。修改 brand color 时务必：
    ```bash
    edit web/shared/tokens.css
    ./web/shared/sync-tokens.sh   # 自动 cp + verify
    git add web/shared/tokens.css web/frontend/assets/css/shared-tokens.css web/phase-detector/app/shared-tokens.css
    git commit
    ```

12. **`#analyze-loading` 在 meta arrival 后 hidden 不 removed**（PR-9 修 PR-8 regression）：error / retry 事件需要这个节点存在以重新画错误。如果未来重构 analyze.js，**不要轻易 .remove() 这个节点**，hidden 即可。

13. **`/api/synthesize/stream` 的 SSE 是 POST**（不是 GET）：因为 `results` 数组太大不适合放 query string。前端用 `fetch().body.getReader()` 手动 parse SSE，不能用 EventSource。任何接入这个端点的新代码都要用 `StructuralAPI.synthesizeStream()` helper。

---

## §7 Session #6 起手 prompt 模板

如果用户想换 prompt 直接告诉 session #6 Claude：

```
[option C — 推荐：双轨]
读 docs/sessions/SESSION-6-STARTER.md。
按 §3 起手扫描 + §2 P1 #6 #7 用 Playwright MCP 跑一遍 /analyze + /search e2e
（验证 session #5 9 个 PR 真实可用），存截图。
等我准备好 token 再切发布路径。

[option B — 自助 UX 第三轮]
读 docs/sessions/SESSION-6-STARTER.md。
按 §3 直接做 P1 #6 #7 #8（e2e + mobile audit），
有时间继续 #9 #10。全权 auto mode。

[option A — 发布路径]
读 docs/sessions/SESSION-6-STARTER.md。
我准备好了 PYPI_TOKEN=xxx 和 ZENODO_ACCESS_TOKEN=xxx。
按 §2 P0 #1-#5 顺序跑（先验证 /tmp artifact 还在，
不在的话先重 build + 重打包 dataset）。
```

---

**Session #5 结束**。HEAD `4b9f888`，9 PRs，UX 总分预计 84.4% → 88-90%（+4-6 pts）。

Next session 入口：本文件 §0 → §3。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
