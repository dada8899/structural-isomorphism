# Session #26 Handoff — Search-box Perplexity-form redesign + final state

> 日期：2026-05-28
> 承接：`SESSION-25-HANDOFF.md` (HEAD baseline `beecb25`)
> **4 commits push origin/main** — Variant B 集成 + ink-dark 蓝色修复 + mockups 归档
> 距 SESSION-25 末 2 天，主题是首页搜索框 UX 重做（不再是 v0.5 paper readiness）

---

## 0. 当前状态 (main HEAD `855948b`，pending +1 handoff commit)

- **origin/main**: synced, 0 race
- prod live: `https://beta.structural.bytedance.city/` HTTP 200, 全部 CSS 值生效
- working tree: 只有 `scripts/train_v2.py` + `v4/results/active_learning/simulation_report.md`（别 session in-flight, §2.6 全程未碰）
- 部署链：本 session 触发 2 次 `Deploy Beta Backend` workflow，均 `completed success`
- backend / API / data 零改动；纯 frontend CSS + 1 行 JS 改动

---

## 1. SESSION-26 commits (4 个，时间倒序)

```
855948b  fix(web/home): remove blue from search-box submit — ink-dark replaces accent
a043568  docs(design): preserve search-box redesign mockups (Variant A + B + 16 screenshots)
6b058f9  feat(web/home): redesign hero search box — Perplexity-form Variant B (warm-ink + white-card)
beecb25  ← SESSION-25 baseline (handoff doc)
```

### 1.1 `6b058f9` — Variant B 集成

| 文件 | 变化 |
|---|---|
| `web/frontend/assets/css/ask.css` | `.ask-main` body.is-home override + `.ask-empty` widen + `.ask-searchbox` Variant B 整套 |
| `web/frontend/assets/js/ask.js` | `syncSubmitState()` 新增 `form.classList.toggle('is-filled', hasText)` |
| `web/frontend/index.html` | `<body>` 加 `is-home` class + placeholder 改对话短句 |

具体 token diff（vs SESSION-25 末态）:

| 维度 | Before | After (Variant B) |
|---|---|---|
| Hero 背景 | 冷灰 `#F5F5F4` | 暖墨渐变 `#F7F4ED → #F4F0E6` + 顶部 radial 柔光 |
| max-width | 660px | **768px**（Perplexity 视觉锚定） |
| padding | 18/20/12 | **24/28/20** |
| border-radius | 16px | **20px** |
| input font-size | 18px | **20px** + letter-spacing `-0.005em` |
| input min-height | 56px | 60px |
| placeholder | 长说明句（"描述一个你卡了很久的难题..."） | **"问一个跨领域的问题..."** |
| ⌘+Enter 提示 | focus 才显示（opacity 0→1） | **常驻 opacity 0.85** |
| 顶边 | 平 | **letterpress 高光** 1px white-70% via `::before` |
| submit 尺寸 | 44×44 | **48×48** |
| submit hover | 静态 → 实色 | hover translateY(-1px) + 阴影 render |
| focus 反馈 | 仅 border + 阴影深一档 | + **整卡上浮 1px** |
| 过渡曲线 | 0.15s linear | **200-220ms cubic-bezier(0.4, 0, 0.2, 1)** |

### 1.2 `a043568` — mockup 设计资产归档

`web/frontend/redesign-mockups/` 完整保留 Variant A + B 的 standalone HTML + 16 张 Playwright 截图 + 比对 README + 复跑脚本。21 MB（node_modules 已 gitignored）。用途：未来重做参照、设计决策审计、对外分享。

### 1.3 `855948b` — 去蓝色（用户反馈"框里的蓝色"）

`web/frontend/assets/css/ask.css` 中 submit 按钮所有蓝色引用全部替换为 ink-dark：

| 状态 | Before | After |
|---|---|---|
| 空态 bg | `var(--brand-accent-soft)` 浅蓝 | `rgba(58, 50, 30, 0.06)` 暖墨浅底 |
| 空态 color | `var(--brand-accent)` `#2563EB` | `#71717A` 中性灰 |
| hover bg | `#2563EB` 实蓝 | `#27272A` ink-dark |
| hover shadow | `rgba(37, 99, 235, 0.24)` 蓝阴影 | `rgba(58, 50, 30, 0.18)` 暖墨阴影 |
| is-filled bg | `#2563EB` | `#27272A` |
| is-filled hover | `#1D4ED8` 深蓝 | `#18181B` 深 ink |

整个搜索框现在 100% 在 ink/paper 色系内，无任何 saturated 色入侵。

---

## 2. 设计决策回顾（含历史教训）

### 2.1 为什么 Variant B 而非 A？

| 维度 | Variant A | **Variant B（shipped）** |
|---|---|---|
| Hero 背景 | 中性偏冷 `#FAFAF9` | 暖墨渐变 `#F7F4ED → #F4F0E6` |
| 卡片对比 | 白卡 on 偏白，**靠阴影戏法** | 白卡 on 暖墨，**靠对比度** |
| 工具气质 | Apple/Notion 极简 | Bear/Anthropic 工具感 |
| 风险 | 阴影依赖屏幕 gamma，不同显示器读起来不同 | 整站色温飞地，需要后续页面跟进暖墨 |

选 B 因为：
- 对比度 > 阴影戏法（物理可靠 > 视觉魔术）
- 用户喜好（Bear / Notion / Manus）都是暖中性纸路数
- Structural 是给 PM/分析师的认知工具，工具感 > 消费感

### 2.2 三次 submit 按钮迭代史

| 版本 | Submit 设计 | 用户反馈 |
|---|---|---|
| SESSION-17 attempt #1 | 实色高饱和蓝圆 | "harsh, jarring" → 改 |
| SESSION-17 attempt #2 | soft-fill 浅蓝圆角方 → solid 蓝 on hover | "less ugly but still not Apple-tier" |
| **SESSION-26 (this)** | 暖墨浅底 → ink-dark `#27272A` 实色 on hover/filled + 暖墨阴影 | **去蓝完成** |

**教训**：Variant B 的 "暖墨纸感" 跟 saturated 蓝色 CTA 是色系冲突。一开始没意识到 mockup 里的蓝是历史包袱，集成后用户立刻指出。下次做色系类设计，**先看整体调色板的色系一致性**，再决定 accent。

### 2.3 placeholder 长 vs 短

旧 placeholder 是 "描述一个你卡了很久的难题，比如：用户每月稳定流失 7%，拉新和召回都不管用"（~30 字 + 1 具体例子）。
新 placeholder 是 "问一个跨领域的问题..."（10 字对话式）。
具体例子已经在下面的 chip 区（"SVB 挤兑级联" / "月活衰减干预" 等）。**避免 placeholder 承担 chip 区的职责**。

### 2.4 submit "is-filled" 的 Perplexity 启发

`syncSubmitState()` 不仅控制 `disabled`，还 toggle `.is-filled` class。CSS 用这个 class 让 submit 在用户输入文字的瞬间就变 ink-dark 实色（不用 hover）。这是 Perplexity 最像 Apple 的细节：**ready-to-fire 状态明确，键鼠用户都能立刻 commit 一次性 submit**。

---

## 3. 关键文件路径速查

| 类别 | 路径 |
|---|---|
| **本 handoff 文件** | `docs/sessions/SESSION-26-HANDOFF.md` |
| Prod 入口 HTML | `web/frontend/index.html` |
| 搜索框 CSS | `web/frontend/assets/css/ask.css`（line 16-220 为 SESSION-26 主战场） |
| Submit JS toggle | `web/frontend/assets/js/ask.js`（line 133-145） |
| Variant A 原型 | `web/frontend/redesign-mockups/variant-a-perplexity-white.html` |
| Variant B 原型 | `web/frontend/redesign-mockups/variant-b-perplexity-ink.html` |
| Playwright 截图脚本 | `web/frontend/redesign-mockups/_screenshot.mjs` |
| 集成验证脚本 | `web/frontend/redesign-mockups/_verify_integration.mjs` |
| Prod 验证脚本 | `web/frontend/redesign-mockups/_verify_prod.mjs` |
| 全套截图（mockup 12 + integration 4 + prod 3） | `web/frontend/redesign-mockups/screenshots/` |

---

## 4. 仍待用户的 9 项操作（**完全不变** vs SESSION-25）

```
🔴 #0  API key 轮换 (5 min)        ← S17 OpenRouter 泄漏 7 天未换
🔴 #1+#2 PyPI 第4包 (3 min)
🟡 #3  Zenodo DOI (10 min)
🟡 #4  arXiv 三投 (45 min)         ← 最大学术杠杆
🟡 #5  8 outreach 邮件 (30 min)
🟢 #6  HN launch (拍板)
🟢 #7  Stripe live (建议暂不)
```

完整 bundle：`USER-ACTIONS-2026-05-26-SESSION-25.md`（仍是 source of truth）。

**最紧急 #0**：S17 那个 OpenRouter key 在公开 repo 泄漏现在已 7 天。SESSION-26 没动这件事 — 任何下个 session 都应该把这件事重新顶到 priority 0。

---

## 5. 下个 Session 起手指令

```
读：
  docs/sessions/SESSION-26-HANDOFF.md (本文件)
  docs/sessions/SESSION-25-HANDOFF.md (paper readiness 主线)
  docs/sessions/SESSION-24-HANDOFF.md (前置方法学增量)
  USER-ACTIONS-2026-05-26-SESSION-25.md (9 项用户操作)

当前 main HEAD: <final commit sha after this handoff>
SESSION-26 = pure UX redesign session（首页搜索框 Variant B + ink-dark）
SESSION-25 + earlier = paper readiness 主线（19 classes + v0.5 skeleton 85%）

working tree 仅 scripts/train_v2.py + v4/results/active_learning/simulation_report.md
别 session in-flight, §2.6 全程未碰。

立即可启动 (按 ROI, CC 全程可推):
  (i)   merge sec-{4,5,6}-update.md 进 v05-draft-skeleton.md (~1h)
  (ii)  §7.1 v0.4-inheritance limitations prose 完整 re-type (~2h)
  (iii) inline figures (Markdown image refs) + §8 inline reference 合并 (~30 min)
  (iv)  v0.5 draft 整体 review pass (~1h) → submission-ready
  (v)   bib [DOI: pending] librarian 验证 pass (~2h)
  (vi)  Pythia HellaSwag/WikiText-103 用 lm-eval-harness 真测 (~6h, optional)
  (vii) Schelling US §301 instrument 自然实验扩展 (~6h, optional)

UX/前端 续作候选 (如用户继续不满意搜索框或其他页面):
  (viii) /analyze 报告页 visual polish 跟进 (Variant B 色系延伸)
  (ix)   /search 二级页跟暖墨 hero 色系是否一致
  (x)    chip 区视觉升级（目前用旧样式，跟新 searchbox 反差大）

等用户拍板:
  - 9 项用户操作清单（#0 API key 必做 → 其余 cascade）
  - 三投并行 vs 分步保守 (D1 bundle vs 分阶)
  - HN launch 时机（arXiv 后）
  - Variant B 暖墨色系是否扩到其他页面（飞地风险）
```

---

## 6. §2.6 边界守护回顾

- ✅ `scripts/train_v2.py` 别 session in-flight 全程未碰
- ✅ `v4/results/active_learning/simulation_report.md` 别 session in-flight 全程未碰
- ✅ 4 commits 每个单文件 explicit `git add`（无 `-A` / `-a`）
- ✅ 每 commit 立即 push（无积累）
- ✅ 远端无 race（origin/main 线性 advance）
- ✅ Sub-agent (frontend-design) 写到独立目录 `web/frontend/redesign-mockups/`，主 session sequential commit，零冲突
- ✅ 部署链 push → workflow → prod 透明，无 force-push / 无 manual VPS 干预
- ✅ 用户反馈 "去蓝色" 后没硬 revert 整个 V-B，做 surgical fix（只动 submit 按钮 CSS）

---

## 7. 与 SESSION-25 的关系

SESSION-25 是 **v0.5 paper submission readiness** 主线（19 classes / 16,244 words skeleton / 5 figures / 3 pre-regs / bibliography / outreach / triple-bundle）。
SESSION-26 是 **首页 UX redesign 分支**（4 commits / 仅 frontend / 用户驱动）。

两者**正交**：SESSION-26 没动 v0.5 paper 任何文件；SESSION-25 没动 frontend。

下个 session 选哪条线接：
- 接 paper 主线 → 走 §5 候选 (i)-(vii)
- 接 UX 主线 → 走 §5 候选 (viii)-(x)
- 切别项目 → 显式说一声（NLN-HK / Renai / Shadow AI / Claude Work）

---

## 8. 累计 commit 总账（SESSION-22 → SESSION-26）

| Session | Commits | 主题 |
|---|---|---|
| SESSION-22 | 26 | v0.3 close-out + v0.4 launch |
| SESSION-23 | 34 | v0.4 batch + 18 class verdict matrix + KB 5333 promote |
| SESSION-24 | 12 | outstanding closure + 3 new methodologies |
| SESSION-25 | 20 | v0.5 readiness + 19 classes + UNIVERSAL-ACROSS-MATTER |
| **SESSION-26** | **4** | **首页搜索框 Variant B + 去蓝 ink-dark** |
| **Cumulative** | **96** | (origin/main HEAD 855948b + this handoff) |

---

**End of SESSION-26 Final Handoff.**

整个 session ~2 小时 wall-clock（含设计 + 集成 + 2 次部署 + 用户反馈 + ink-dark surgical fix）。从用户说"首页搜索框体验还是很差"到收尾：派 frontend-design agent 出 2 个 variation → 用户选 B + 立刻上线 → 集成到 ask.css/index.html + auto-deploy → 用户反馈"框里的蓝色"→ surgical ink-dark fix → re-deploy → 用户确认"好没问题了"。CC 物理边界全部触到（前端代码、构建、部署、Playwright 验证）。剩用户 9 项独立操作不变。
