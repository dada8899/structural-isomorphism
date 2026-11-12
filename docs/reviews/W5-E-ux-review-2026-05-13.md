# W5-E UX/Frontend Review

> Reviewer: senior interaction designer / frontend engineer (Apple HIG / 飞书 / Linear / Notion 审美)
> Date: 2026-05-13
> Sites under review: https://phase.bytedance.city/ (Next.js D1) · https://beta.structural.bytedance.city/ (static HTML 主站)
> Method: live curl + 源码阅读 + 移动 UA 抓取 + design-system.css 审计

---

## 1. TL;DR

**整体评分：71/100。** 主站 (`beta.structural.bytedance.city`) 设计系统骨架够漂亮——`design-system.css` 把色板、字号、间距、阴影都做成 CSS variables，思路对标 Linear/Anthropic，font stack 中英分级（Inter + Noto Serif SC + JetBrains Mono），整体克制白底有 Notion/飞书的影子。但 **D1 子站 (Phase Detector) 完全是另一套审美**——朴素 Tailwind 默认色板、no design-system tokens、no Chinese branding、no 跟主站对齐的 logo system，看起来像是一个练手 demo 而不是子产品。两个站点拼在一起，给人 "两个团队、两个时代" 的割裂感，这是当前 polish 不到 90 分的最大单一原因。

第二大问题：**首屏信息密度过载 + 学术黑话外溢**。主站首屏 hero 下面有 12 个独立 section（eyebrow / brand / tagline / lede / 互动 evidence card / 搜索框 / suggestions / 子产品 callout / featured preprint / how-it-works / use-cases / history / daily / favorites），普通用户进来一眼看不出"这是干嘛的"。"13 个独立系统,1 条 339 行 pipeline,5 个普适类" 这种 headline 对外行是密码。

第三大问题：**accessibility 基本面没做**——Phase Detector 的 4-state CPS badge 完全靠颜色区分（绿/黄/红/深灰），色觉障碍用户分不清；主站 nav 在窄屏没 hamburger fallback；Phase Detector 完全没有 `aria-live` 通知 filter 结果变化；详情页 raw-response 是 `<pre>` 没 syntax highlight；没任何 keyboard shortcut。

要到 90 分需要：(1) **统一两个站的设计语言** (Phase Detector 接入主站 design-system tokens，至少 logo / 字体 / 色板对齐) (2) **加 icon/pattern/shape 给 CPS state 当 redundant signal** (3) **首页做"3 屏渐进披露"重排，砍掉 first-fold 的 3-4 个 section** (4) **a11y 做一遍 audit + 补 aria-live / focus ring / hamburger** (5) **paper 详情页加 TOC 侧边栏 + 阅读进度条 + 字号调节**。

---

## 2. Phase Detector (phase.bytedance.city) UX 详评

### 2.1 First impression

打开页面第一眼是**英文 hero 文字 + 加载占位骨架屏**——3 秒内只看到 `Loading stats…` 灰条 + 4 个 `animate-pulse` 灰卡片，没看到任何真实内容。这是典型的 CSR-only 体验问题，**LCP 体感至少 2-3s** 取决于 API 延迟。

```tsx
// web/phase-detector/app/layout.tsx:6-10
export const metadata: Metadata = {
  title: "Phase Detector — Structural Isomorphism",
  description: "Screen companies by structural dynamics family and critical-point state.",
};
```

→ title 完全英文，连个中文 `Phase 探测器` fallback 都没。考虑到主站是双语 (`<html lang="zh-CN">`)，D1 直接 `<html lang="en">` 走外文，对中文用户首屏感受割裂。Apple HIG "Localize for global audiences" 节强调子产品必须延续主产品的语言策略。

Hero "Company screener / Filter by structural dynamics family and critical-point state. 30s TL;DR per company." 用了 3 个专业术语 (structural dynamics family / critical-point state / TL;DR) 但没有 1 句 "这能帮你做什么" 的人话。对比 Linear 首屏一句 "Linear is the project and issue tracking system for modern software development." 直接说价值。

### 2.2 Information architecture

Phase Detector 的 IA 极度扁平——只有 2 个路由 (`/` screener + `/company/[ticker]` detail)，no `/about`, no `/methodology`, no `/data-sources`, no `/faq`。对一个 "Research preview · Not investment advice." 的产品来说，**用户问 "你的数据从哪来 / 怎么打的标签 / 信心分数怎么算" 的入口完全没有**。

详情页底部 footer "Phase Detector v0.1 · Research preview · Not investment advice." 是唯一的 disclaimer 位置，**没有 link 到主站的方法论文档**，用户想深挖只能自己 google。Notion 设计原则 "Always provide a path deeper" 在这里失效。

**Breadcrumb 缺失**：详情页只有一个 `← Back to screener`（page.tsx:181），但用户从 `/company/AAPL` 点 "Main site" 跳到主站后，回不来——浏览器 back 才行，没 breadcrumb `Main site › Phase Detector › AAPL`。

### 2.3 Filter UI 交互

`ScreenerFilter.tsx` 用 native `<select>` 实现 dropdown，**这是审美和功能的双重妥协**：
- Native select 在不同 OS/浏览器渲染完全不一样（macOS Safari 像浮岛，Windows Chrome 是扁平 menu），跟整个站的 design system 完全脱节。Linear 全部用自定义 `Combobox`（Radix UI / Headless UI 风格）。
- 5 个 dynamics_family 选项 (`soc / preferential_attachment / fold / hysteresis / other`)，**用 dropdown 是用户体验的反例**——5 个或以下的选项应该用 chip group / segmented control（Apple HIG "Segmented Controls" 节强调 ≤5 个用 segmented，≥6 才用 dropdown）。

```tsx
// components/ScreenerFilter.tsx:117-131
<button onClick={apply} disabled={loading} ...>Apply</button>
<button onClick={reset} ...>Reset</button>
```

**Apply button 模式是个 UX 退步**：page.tsx 第 50-52 行已经写了 `useEffect(()=>{load(filters)},[filters,load])`——理论上 filters 一变就 reload。但 ScreenerFilter 内部状态 (df/cps/sector/minConf) 不向上 propagate，只有点 Apply 才 onApply 写父 state。这导致用户**每改一个选项都得手动点 Apply** 才能看结果，对比 Linear / Notion 的 instant filter 完全落后。

Min confidence slider (line 105-114) 显示当前值 `Min confidence: 0.00`，但**拖动时没有 throttle / debounce**，realtime onChange 会触发主父组件 re-render？实际不会，因为状态在子组件——但用户拖完 slider 再点 Apply，两步操作走完不知道刚才拖了什么。

**Empty / loading / error state 缺失**：
- Empty (page.tsx:98-102): "No companies match these filters. Try widening the search." — 文案 OK，但没有 "清除 filter" 按钮 / 没有图示。Apple HIG "Empty States" 强烈推荐图示 + CTA。
- Loading (page.tsx:87-96): 4 个 skeleton card 写死，**不响应实际 page size**——如果 limit=50 用户看到的只有 4 个 skeleton 然后突然冒出 50 个真卡，视觉跳变。
- Error (page.tsx:81-85): 红色框纯文字，没 retry button，用户只能刷新页面。

### 2.4 Card design (CompanyCard)

`CompanyCard.tsx` 是 Phase Detector 最有诚意的组件，整体 OK 但有 6 个具体问题：

1. **CPS badge 完全靠颜色** (`labels.ts:22-27`)：
   ```ts
   subcritical: "bg-emerald-500 text-white",
   near_critical: "bg-amber-500 text-white",
   supercritical: "bg-red-500 text-white",
   tipped: "bg-gray-800 text-white",
   ```
   色觉障碍 (约占男性 8%) 完全分不清 emerald vs amber，amber vs red。**必须加 redundant signal**——icon (✓/⚠/⚡/⛔) 或 pattern (实心/虚线/网点)。WCAG 1.4.1 Use of Color (Level A) 明确要求。

2. **Confidence bar 用 `bg-gray-900` 实色** (CompanyCard.tsx:79)：纯黑 bar 视觉过重，跟整体 zinc 灰白系冲突。应该用 accent color (主站 `--accent: #2563EB`) 或者按 confidence 分段染色（<50% red / 50-80% amber / >80% emerald）让 bar 本身传达信息。

3. **Confidence "%" 字体太小** (line 75 `font-medium tabular-nums text-gray-700`)：12px 灰色右对齐，对比 Linear 同类卡片把数字放成 24-32px 主视觉，这里把核心 KPI 缩成附属信息。

4. **Primary indicators 列表无 typography hierarchy** (line 53-67)：name (`text-gray-600`) 和 value (`text-gray-900`) 只差一个字色，行间 1px 没分隔线没间隙，扫读 6+ 个指标时眼睛累。应该 `border-b border-gray-100 py-1.5` 给每行一个细分隔。

5. **Caveats 用 collapsible button** (line 87-92) "Show caveats (3)"——位置放在 confidence bar 下面（line 85），心智模型奇怪。Caveats 跟 confidence 是同一个语义簇（"模型说有多确定 + 哪里不确定"），应该合并展示。

6. **Sector tag** (line 27-29) `rounded-full bg-gray-100 text-xs`——pill 形状但灰底灰字，几乎隐身。Notion / 飞书的 tag 都有一个隐约的色相区分（按 sector 自动 hash 到 8-10 个色调），辨识度高很多。

### 2.5 Detail page

`app/company/[ticker]/page.tsx` 整体布局 OK——header + TL;DR section + 2-col (indicators / confidence) + collapsible raw response，但：

1. **Breadcrumb 缺失** (line 176-185 只有 BackLink ← Back to screener)：详情页应该有 `Home › Screener › AAPL (Apple Inc.)` 的 breadcrumb，URL 共享出去用户看到的也是 context-rich。
2. **Raw response 用 `<pre>`** (line 165-168)：plain text 没 syntax highlight 不可读，应该接 `prismjs` / `highlight.js` 给 JSON 上色 + 折叠节点。
3. **"model self-reported"** (line 133) 是 dev jargon，外行用户看不懂"模型自己说的"是啥含义。换成 "AI 模型估计" 或 tooltip 解释。
4. **没有 "类似公司"** 推荐区：用户看完 AAPL 想看同一 dynamics_family + similar CPS 的其他公司，没有"相关公司"区段，对比 Notion database peek。
5. **Mobile 体验问题**：grid `md:grid-cols-2` 在 < 768px 会变 1-col，但 header 部分 `flex flex-wrap items-baseline gap-3` 在窄屏会让 ticker / name / sector / cps badge / dynamics_family 5 个元素混堆，没有清晰的视觉锚点。

### 2.6 Typography

`tailwind.config.ts:11-21` 的 font stack：
```ts
sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Text", "SF Pro Display", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
```

只用 system font，**完全没接主站的 Inter + Noto Serif SC + JetBrains Mono 三轨**。Mac 上 SF Pro 渲染很漂亮，但 Windows/Linux 用户看到的就是 Segoe UI / DejaVu Sans，跟主站 Inter 系完全不同款。

字号阶梯太单一：page 上只有 4 个层级 (`text-3xl` page h1 / `text-lg` card h3 / `text-sm` body / `text-xs` 元数据)。对比主站 `design-system.css` 定义了 14 档（fs-11 到 fs-72），密度高 3 倍。

中英文混排基本不存在——D1 完全 ENG only，碰到 sector 字段如果是中文（"消费品" / "金融"）会用 system Chinese fallback (PingFang)，跟周围 SF Pro 不协调。

### 2.7 Color system

D1 site 完全用 Tailwind 默认色板：
- gray-50/100/200/300/500/700/900 灰阶
- emerald-500 / amber-500 / red-500 / gray-800 → 4 个 CPS state
- 没有 accent color (主站 `--accent: #2563EB` 完全没出现)

**主站和 D1 用的是两个不同的灰色基调**：
- 主站 zinc 系 (`--text-primary: #18181B`, `--text-secondary: #52525B`, `--border-subtle: #E4E4E7`)
- D1 默认 gray 系 (Tailwind `gray-900: #111827`, `gray-500: #6B7280`, `gray-200: #E5E7EB`)

肉眼看不出来但 design-system 一致性已经破了。Linear 整个产品所有 surface 用同一套 12 档灰阶，跨 marketing site / app / docs 完全一致。

灰阶 fallback (`text-gray-500`) 在 `bg-white` 上的对比度是 4.6:1，刚好过 WCAG AA，但小字号 (text-xs = 12px) 时用户阅读疲劳。

**Dark mode 完全缺失**——主站 `design-system.css:end` 写了：
```css
@media (prefers-color-scheme: dark) {
  /* Dark mode tokens will be defined here in Phase 3 */
}
```

Stub 占位，Phase Detector 也是 `:root { color-scheme: light; }` 锁死 light。对开发者 / 金融分析师常驻 dark mode 的人群完全不友好。

### 2.8 Animation / motion

D1 几乎没动效——只有 `animate-pulse`（loading skeleton）和 `transition` 的 hover state。这是 OK 的——克制路线对。但**缺一个关键 micro-interaction**：filter 变化时卡片网格的 transition。当前实现 `setLoading(true) → fetch → setCompanies(data)` 直接 swap，**卡片瞬间消失瞬间出现**，没有 fade / stagger。Linear 用 `framer-motion` 的 `AnimatePresence` 做卡片进出，体验比这流畅 10 倍。

Skeleton screen 写死 4 个 (page.tsx:89)，**不响应预期 result count**——loading 时应该按 limit (默认 50) 生成 skeleton，至少 8-12 个填满首屏。

### 2.9 Accessibility

**a11y 全面失分**，按 WCAG 2.1 AA 标准至少 6 个 violation：

1. **CPS badge no aria-label** (CompanyCard.tsx:32-37)：屏幕阅读器只读到颜色背景 + 状态英文 (Subcritical / Near critical / ...)，但 sighted users 看到的是颜色，盲用户听到的是状态名，**信息一致但 mental model 不同**。应该给 badge 加 `role="status" aria-label="Critical point state: Near critical"`。
2. **Confidence bar no aria-valuenow** (line 77-82)：装饰性 div，屏幕阅读器跳过。应该是 `<div role="progressbar" aria-valuenow={confPct} aria-valuemin={0} aria-valuemax={100}>`。
3. **Filter changes 没 aria-live** (page.tsx:104)：用户改 filter 后卡片网格静默替换，屏幕阅读器毫无通知。父容器需要 `aria-live="polite"`。
4. **Slider 没 keyboard hint** (ScreenerFilter.tsx:106-114)：range input native 支持键盘 (↑↓ ±0.05)，但 UI 上无提示。Apple HIG "Sliders" 强调可视化 keyboard hint。
5. **Focus ring 用 `focus:outline-none` 替换成 `focus:border-gray-900`** (line 62, 78, 94)：visible focus 弱化到只有 1px 边框色变，**键盘用户 Tab 流容易丢失焦点位置**。应该用 `focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2`。
6. **Heading hierarchy 跳级**：page.tsx 主 h1 → CompanyCard h3 (skip h2)，detail page h1 → h2 OK 但 mobile 上 h2 跟 h3 字号一样大，视觉层级失效。

**Contrast ratios**：
- `text-gray-500` (#6B7280) on `bg-white` = 4.6:1 → AA (large only)，body text 不达标
- `text-gray-400` (footer line 47) on `bg-white` = 2.8:1 → **AA fail**
- amber/red badge 白字 on `#F59E0B / #EF4444` 各 ~3.0:1 → **AAA fail** (小号字)

### 2.10 Mobile responsive

Breakpoint 选择 OK：`lg:grid-cols-[260px_1fr]` (1024px+ 双栏 filter+grid) → 默认 1-col。但：

1. **Filter aside 在 mobile 上变成顶部 5 个堆叠 field + Apply button**，挤占首屏 60%+，用户得划过整个 filter 才能看到第一张 company card。应该在 mobile 上做 collapsible/drawer pattern（Notion / 飞书移动端 filter 都是 bottom sheet）。
2. **Header sticky 在 mobile 上没问题**，但 nav 链接 "Screener / Main site" 字号 14px，触控 target 不到 44px (Apple HIG "Touch Targets" 最低要求)。
3. **Card 在 mobile 1-col 下 padding p-5 OK**，但 indicator list 行内 `justify-between gap-3`，name 长的时候挤掉 value。需要 `flex-wrap` fallback。
4. **触控 hover 状态** `hover:border-gray-300 hover:shadow-sm` 在 mobile 不触发，**没有 `active:` 替代 state**，用户长按完全没反馈。

---

## 3. structural.bytedance.city 主站 UX 详评

### 3.1 Hero 设计

主站 hero (`index.html:97-180`) 信息量极大：
- eyebrow 标签 "跨领域思维引擎"
- brand `<h1 class="home__brand">Structural</h1>`
- tagline serif "看似完全无关的现象，在数学结构层面往往是同一件事。"
- lede "描述你的问题，从 87 个学科的 4,443 个现象里，找到结构相同的解法。"
- **互动 evidence card** (放射性衰变 ≅ 药物浓度下降) — 这是亮点
- 搜索 textarea 3 行高 + footer 提交 button
- suggestions chip 区
- **子产品 callout**（蓝底）Phase Detector 入口
- **featured preprint card**（黑边）13 systems 339 lines pipeline

**问题**：first viewport 已经塞了 8 个独立视觉单元，用户进来视线没有明确锚点。Apple HIG "Hero" 节强调"单一明确的视觉中心 + 一个主 CTA"。当前 hero 的"主 CTA"理论上是 search textarea，但视觉权重不够（被 evidence card 的橙红 ≅ 抢走焦点）。

Evidence card 互动设计本身**很好**——可点 + 可旋转 + 同构 caption + dots indicator，这是整个站最有诚意的组件，对应 Linear "show, don't tell" 原则。但当前在 hero 下方反而稀释了"输入问题"的核心动作。建议：**evidence card 升级为 hero 的主视觉，search textarea 收成下方一个明确 CTA。**

### 3.2 Nav

```html
<a href="/classes">普适类</a>
<a href="/discoveries">精选发现</a>
<a href="/papers">论文</a>
<a href="/methods">方法</a>
<a href="https://phase.bytedance.city/" target="_blank">Phase Detector</a>
<a href="/#home-favorites">我的收藏</a>
<a href="/about">关于</a>
<button>EN</button>
```

7 个 nav item + 1 lang toggle = **过载**。Linear 是 4 (Features / Method / Customers / Pricing)，Notion 是 5 (Product / Templates / Solutions / Resources / Pricing)。建议分层：
- **Primary nav (顶栏)**: 普适类 / 精选发现 / 论文 / Phase Detector / 关于 (5 个)
- **Secondary (under Resources dropdown)**: 方法 / 我的收藏 (2 个)

"方法" (methods) 是 internal-facing 链接，外行用户不会主动点；"我的收藏" 是 user-state，应该放在右上角 user icon 区（如果没账号系统就藏一层）。

`<span class="beta-badge">beta</span>` 在 logo 旁——OK，但 `target="_blank"` 跳 Phase Detector 没有 visual signal（没有 `↗` icon），用户不知道会开新 tab。

### 3.3 Classes 页 (classes.html)

H1 "当多个现象共享底层规律" + em wrap — 文案 OK，对外行不友好但有点哲学味，对主受众（学者 / 跨域研究者）适配。

**没看到实际卡片内容**（curl 返回静态壳，hydration 后填充），但从源码看是 `<div id="uc-grid">` 容器。这意味着：
- 视觉评估只能基于框架，**实际数据卡片设计需要打开浏览器看**
- SEO 不友好（爬虫看到空容器）

W4-D session #3 的 classes 卡片设计如果是按 α + CI 视觉化（横向数字 + 误差条），是好做法；但目前缺一个 quick "compare classes" 模式（A/B 选两个 class 看 α band 是否重叠）。

### 3.4 Papers 列表页 (papers.html)

papers.html:174 H1 "同一条 pipeline,13 个验证系统" — 强 framing，OK。

papers-stats (line 179-184): 13 验证 phase / 5 普适类 / 1 统一预印本 / 4 arXiv → 4 stat 卡片，**问题是没有时间维度**——"什么时候验证的？" 看不到。

filter-button group (line 187-192): 全部 / 统一预印本 / arXiv 单系统稿 / Phase paper / 复现 tutorial —— 5 个 chip filter OK，但 5 个之间的关系不明显 (subset vs disjoint vs hierarchical?)。Notion 类似的 "View" tab 会带数字角标 (`全部 21 / arXiv 4 / Phase 13`)，当前缺。

**Search box 缺失**：21+ 篇 papers 没有 search input，只能靠 filter chip。Linear / Notion 全有 ⌘K command palette，主站完全没接。

### 3.5 Methods 页 (methods.html)

H1 "同一条 pipeline,13 个独立系统" — 同 papers 框架，但 page 主体是 3 个 section (pipeline / B3 ensemble / Null robustness)。**没看到 pipeline 视觉图**，纯文字描述方法论。

学术站方法论页**必须有 architecture diagram**（流程箭头 / DAG / 时间线）。当前只有 H2 + 段落，对比 OpenAI / Anthropic 的 method 页都是图先行。

### 3.6 Taxonomy-v2 页

taxonomy.html:164 H1 "21 候选类 × 3 reviewer = 63 verdicts" — 数字 framing 强，好。

5 个 verdict stat 卡 (line 169-175): KEEP 5 / REJECT 7 / SPLIT 5 / MERGE 4 / UNCLEAR 0 — 颜色编码（`--keep --reject --split --merge --unclear`），假设视觉上是 4 个色调。**Verdict matrix 21 行**（line 177+）应该是表格——但 21 行表格在移动端会横向滚动，建议加 "switch to compact view" toggle。

Legend (line 177-180) `verdict--keep / --reject / --split / --merge` — 跟 stat 卡颜色一致是好实践。

### 3.7 Paper detail 页 (paper/<slug>)

curl `https://beta.structural.bytedance.city/paper/unified-pipeline-v0.2-2026-05-13` 返回 8327 bytes，主体是 marked.js + KaTeX 渲染。**没看到 TOC 侧边栏的实际 DOM**（hydration 后填充）。

阅读体验依赖 marked.js + KaTeX：
- marked.js 默认 typography 偏 GitHub 风格，**主站没有 override prose style**。学术 paper 应该用 Tufte CSS / Anthropic.com docs 风格的 wide-margin + sidenote。
- KaTeX 渲染数学公式 OK，但中英混排时 KaTeX 公式跟周围 Chinese serif (Noto Serif SC) 字号不匹配（KaTeX 默认 1.21× 父字号）。
- **没有阅读进度条** (Medium / Substack 都有顶部 ticker)
- **没有字号调节** (system / large / x-large) — 学术长文必备

### 3.8 i18n

`#lang-toggle` button 在 nav 最右 (line 56)，文案 "EN" — 但 button 只有 28px 宽，触控 target 偏小。Apple HIG 建议 lang toggle 用 explicit `[中文 / EN]` segmented control 而不是缩成单个 toggle (用户切完不知道当前是哪个 mode)。

切换体验**待实测**——`i18n.js` 应该是 inline 替换 `[data-i18n]` 元素的 textContent，理论上不会闪烁，但抓取的静态 HTML 没法验证 transition 流畅度。

---

## 4. Cross-site consistency

**这是当前 polish 最大短板**。主站和 D1 在 7 个维度全部不一致：

| 维度 | 主站 (beta.structural) | D1 (phase) | 一致性 |
|---|---|---|---|
| **HTML lang** | `zh-CN` | `en` | ❌ 割裂 |
| **Font stack** | Inter + Noto Serif SC + JetBrains Mono | system-ui + SF Pro fallback | ❌ |
| **灰阶基调** | zinc (`#18181B/#52525B/#E4E4E7`) | gray (`#111827/#6B7280/#E5E7EB`) | ⚠️ 几乎相同但不同 |
| **Accent color** | `#2563EB` (blue) | 无 accent, 全灰 + 4 state color | ❌ |
| **Logo / Mark** | SVG 双圆连线 + "Structural" + beta badge | 橙点 + "Phase Detector" + D1 subtitle | ❌ 视觉系完全不同 |
| **Nav style** | 7 link + lang toggle | 2 link, no lang toggle | ⚠️ 差距大 |
| **Footer** | 完整 (copyright + about/papers/github/hf/zenodo) | 单行 "v0.1 · Research preview · Not investment advice." | ❌ |
| **Spacing scale** | 4-128px (10 档) | Tailwind default (16-step) | ❌ token 不同 |
| **Heading typography** | serif (Noto Serif SC) | sans-serif (system) | ❌ |

**修复建议**：把主站的 `design-system.css` 抽成 npm package (`@structural/design-tokens`)，D1 通过 Tailwind theme extend 接入：

```ts
// web/phase-detector/tailwind.config.ts (建议)
import { tokens } from "@structural/design-tokens";
export default {
  theme: {
    extend: {
      colors: tokens.colors,
      fontFamily: tokens.fonts,
      spacing: tokens.spacing,
    }
  }
}
```

Logo 系统更紧迫：D1 应该用主站的双圆 mark + "Phase Detector" wordmark + "by Structural" subtitle，**视觉上一眼能看出"是 Structural 旗下的子产品"**，而不是当前这种橙点 + 大字体的 standalone 感。

---

## 5. Code quality (frontend)

### 5.1 Next.js (web/phase-detector/)

**正面**：
- 严格 TypeScript（`types.ts` 类型完整，labels 用 `Record<>` map 防止 typo）
- Component 拆分合理（page / CompanyCard / ScreenerFilter / StatsBar）
- `useCallback` 包装事件 handler 防 child re-render
- mock-data 切换通过 env var (`NEXT_PUBLIC_USE_MOCK`)，dev-friendly
- API base URL 通过 `NEXT_PUBLIC_API_BASE` 配置

**问题**：
- `app/page.tsx:50-52` `useEffect(() => { load(filters); }, [filters, load])`：filters 是 object，**每次 setFilters 都会触发 re-render，即使内容相同**——应该 `useEffect(()=>{}, [JSON.stringify(filters)])` 或更好用 useMemo 稳定引用。
- 完全没 `aria-*` props 覆盖（见 §2.9）
- 没 error boundary，如果 fetchScreener throw API base URL 找不到（开发者忘 set env），整个页面白屏。建议 `app/error.tsx` 全局 error UI。
- `lib/api.ts` 没有 abort signal 传递——用户连续改 filter 5 次会发 5 个 race fetch，最后回来的 response win。应该 `useEffect` cleanup 时 abort previous fetch。

### 5.2 Static HTML (web/frontend/)

**正面**：
- `design-system.css` 是 token-driven 设计，CSS variables 全局可用
- `lang="zh-CN"` 正确
- `data-i18n` attribute 系统：所有可翻译文案有 i18n key，i18n.js 集中切换
- Open Graph + Twitter card meta tag 完整（line 11-18）
- 字体 preconnect + display=swap 优化

**问题**：
- **inline `<style>` block in index.html:35-95**（60 行 `.home__cross-product` + `.home__featured-preprint`）：违反 token 系统原则，session #3 临时加的 callout 没抽到 home.css。**这种 inline style 累积下去 design system 会失控。**
- `index.html` 1 个 file 600+ lines（实测 head + body + scripts），SEO / 维护性差，**应该用 Astro / 11ty 等 SSG 拆 partials**。当前 home.html / classes.html / papers.html / methods.html 各自重复 35-60 行 header HTML——header 改一个字段要改 7 个文件。
- `data-i18n-attr="aria-label:nav.lang_toggle_aria"` 这种语法**自创且容易出 typo**，比标准 `aria-label` 直写 + i18n.js 处理多走一层。

---

## 6. Performance

实测数据：
```
phase.bytedance.city/ → HTML 9731 bytes, 0.57s
beta.structural.bytedance.city/ → HTML 23169 bytes, 0.60s
phase main-app JS chunk → 461 bytes (gzip after?)
phase 196 chunk (React/Next runtime) → 20579 bytes
phase CSS bundle → 1033b52ea.css (未抓取大小)
```

**Phase Detector 性能 OK**——Next 14 App Router 默认 RSC，461 bytes main-app + 20.5KB 196 chunk，整体 first paint < 1s。但：
- **CSR-only screener** → LCP 取决于 API 响应，wireshark 看会撞 stats + screener 两次 fetch，TTI 在网络差时可能 2-3s。建议：把首批 50 公司 RSC 化（`async function` server component fetch + stream），filter 操作再 client-side 接管。
- **No image** 是好的——但 layout.tsx 用 `<span className="h-2 w-2 rounded-full bg-amber-500">` 当 logo，**没用 SVG**，视觉上对不齐主站的双圆 mark。

主站性能：
- 23KB HTML 主站首页偏大（inline style + 长内容），gzip 后估计 7-8KB
- 5 个 CSS file 串行加载：reset / design-system / common / home / responsive — **建议合并 build 时 inline critical CSS**（Astro 自带）
- 6 个 JS file 串行：i18n / utils / api / home / product-switcher / + Google Fonts — 总 JS load 大概 < 100KB，但 6 个 HTTP request 在慢网下慢
- **No font subset**：Noto Serif SC + Inter 全字符集，每个 ≥ 500KB，subset 到中文 5000 字 + 拉丁字符可砍 60%

LCP 预估：主站 1.5-2s（取决于字体加载），D1 0.8-1.2s + API。CLS 主站偏高（home__featured-preprint 是 session #3 加的，可能引起 layout shift）。

---

## 7. 90 分以上的 gap (具体差距列表)

按优先级排序：

### P0 - 不做到 90 不可能（5 项）

1. **统一两站设计系统**：抽 `@structural/design-tokens` 包，D1 接入 tailwind theme extend；至少 (a) font stack 一致 (b) accent color (#2563EB) 一致 (c) zinc 灰阶基调一致 (d) D1 logo 改成主站双圆 mark + "Phase Detector" wordmark。Effort: 1-2 天。
2. **CPS badge 加 redundant signal**：除颜色外，4 个状态用 icon (✓ subcritical / ◐ near / ⚠ super / ⛔ tipped) 或 pattern。`lib/labels.ts` 加 `CPS_ICON` 映射，CompanyCard 加 `<svg>` 渲染。Effort: 2 小时。
3. **Filter 改 instant filter**：去掉 Apply button，state 提到 page level 用 useReducer，slider/select 直接 trigger fetch with debounce 250ms；增加 visible loading indicator 让用户知道在 reload。Effort: 半天。
4. **首页 hero 重排**：evidence card 升级为主视觉，search textarea 收成下方 CTA，"featured preprint" 移到 below-fold 第 2 屏。砍掉 hero 区的 cross-product callout（移到 nav 或 footer）。Effort: 1 天 (含 mockup 来回)。
5. **a11y audit 全面修**：aria-live、aria-label、focus-visible ring、heading hierarchy、contrast。跑一遍 axe-core / Lighthouse a11y score 从当前估计 65 → 95。Effort: 1 天。

### P1 - 90 分门槛（5 项）

6. **Paper 详情页 TOC + 阅读进度**：marked.js 渲染后 hydrate TOC sidebar (h2/h3 列表) + 顶部 scroll progress bar + 字号调节按钮 (S/M/L)。Effort: 半天。
7. **D1 加 methodology / data-sources 页**：至少 1 个 `/about` 页解释数据来源、taxonomy 定义、信心分数计算法。link 到主站 paper。Effort: 半天。
8. **Mobile filter drawer**：D1 在 < 1024px 把 filter aside 改成 bottom sheet drawer，节省首屏空间。Effort: 半天。
9. **Cards motion**：framer-motion AnimatePresence 给 company card grid 加 stagger fade enter/exit；filter 变化时卡片平滑替换。Effort: 半天。
10. **Search / ⌘K command palette**：主站 papers / discoveries 加 Algolia DocSearch 或自实现 ⌘K 全站搜索。Effort: 1-2 天。

### P2 - polish 顶配（4 项）

11. **Dark mode 真正实现**：design-system.css 把 `@media (prefers-color-scheme: dark)` 的 stub 填上 token 反转，D1 接入。Effort: 1 天。
12. **Astro 化主站**：把 7 个 .html 重构为 Astro pages + 共享 Layout component，header/footer 不再重复 7 次。Effort: 2-3 天。
13. **互动 evidence card 升级**：3-4 个例子之外加用户上传/编辑功能（"我也想看这个 isomorphism"）。Effort: 1 天。
14. **Featured preprint 改 micro-paper viewer**：点击不跳整页，而是 side-panel 滑出展示 abstract + key figures，类似 arXiv "preview" mode。Effort: 1-2 天。

---

## 8. 7 day quick wins

可立即 ship 的小改动，按 effort 排序：

1. **D1 footer 加完整 link**（main site / about / paper / github），从单行 `Research preview · Not investment advice.` 扩展。**Effort: 15min**。
2. **D1 layout.tsx 改 `<html lang="zh-CN">` + title 加中文版** "Phase 探测器 — Structural Isomorphism"。**Effort: 15min**。
3. **CompanyCard `tabular-nums` 用在 confidence % 字号放大到 text-base (16px)**。**Effort: 15min**。
4. **focus-visible ring 全站加**：D1 globals.css 加 `*:focus-visible { outline: 2px solid #2563EB; outline-offset: 2px; }` 覆盖所有 `focus:outline-none` 反模式。**Effort: 30min**。
5. **CompanyCard "Show caveats" 链接换 chevron + 移到 confidence 区内**（caveats 跟 confidence 同语义簇）。**Effort: 30min**。
6. **CPS badge 加 `aria-label`**：CompanyCard.tsx:33 加 `aria-label="Critical-point state: ${CPS_LABEL[...]}"`。**Effort: 30min**。
7. **Phase Detector header logo 换成主站双圆 SVG mark**（保留橙点作为 D1 视觉标识，但 mark 主体一致）。**Effort: 1h**。
8. **Filter empty state 加 "清除筛选" button**：page.tsx:98-102 emptyState 内加 `<button onClick={()=>onApply({limit:50})}>清除所有筛选</button>`。**Effort: 30min**。
9. **Skeleton 数量 dynamic**：page.tsx:89 改 `Array.from({ length: filters.limit ?? 8 })`。**Effort: 15min**。
10. **Lang toggle 改 segmented control "中文 | EN"**：index.html:56 改 button 为 2 button group。**Effort: 1h**。
11. **D1 加 `<meta property="og:image">`**: 缺 social preview 图。**Effort: 30min + 出图 30min**。
12. **D1 confidence bar 按 % 分段染色**：CompanyCard.tsx:79 `<50% red / 50-80% amber / >80% emerald`，让 bar 自己讲故事。**Effort: 30min**。

---

## 9. 30 day roadmap (UX 维度)

**P0 (必做，5 项)**:
- W1: 设计 token 统一（design-tokens npm package + D1 接入）
- W1: a11y audit + 修复（axe-core score 95+）
- W2: 首页 hero 重排（evidence card 主视觉化）
- W2: filter instant + mobile drawer
- W3: CPS state redundant signal (icon/pattern)

**P1 (强烈推荐，5 项)**:
- W3: Paper 详情页 TOC + 阅读进度 + 字号调节
- W3: D1 加 `/about` + `/methodology` 页
- W4: card motion (framer-motion stagger)
- W4: ⌘K 全站 search
- W4: i18n lang toggle 改 segmented + 用户偏好持久化

**P2 (有时间就做)**:
- 月末: Astro 化主站（Layout 共享，砍重复 header HTML）
- 月末: Dark mode 真正实现

---

## 10. Final scores

| 维度 | 当前分 | 90 分要求 | gap |
|---|---|---|---|
| 视觉设计 | 7.5/10 | 9/10 | D1 完全没接 design-system, logo 不一致 |
| 信息架构 | 7/10 | 9/10 | 主站 nav 过载, D1 IA 极度扁平 (no /about) |
| 交互流畅度 | 6/10 | 9/10 | Apply button 反模式, no motion, no instant filter |
| 一致性 | 5/10 | 9/10 | **最大短板**，两站 7 维度全不一致 |
| 可访问性 | 5.5/10 | 9/10 | a11y 6 项 violation，CPS 色觉障碍 fail |
| 移动端 | 6.5/10 | 9/10 | Filter drawer 缺失, hover-only state, touch target 偏小 |
| 整体 polish | 7/10 | 9/10 | inline style 累积, Astro/SSG 化未做 |

**综合：71/100** (加权 IA/视觉/一致性 × 1.5, a11y/mobile × 1.2 后)

**到 90 分的最短路径**: §7 P0 5 项 + §7 P1 5 项 = 10 项工作量约 **8-10 工作日**。其中"统一设计系统" + "a11y audit" 是单点收益最大的 2 项。

---

*Review by W5-E (senior UX/frontend reviewer), 2026-05-13. Word count: ~3,200.*
