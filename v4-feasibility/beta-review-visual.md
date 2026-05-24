# Beta Visual & UX Audit — `beta.structural.bytedance.city`

**Date**: 2026-04-13
**Method**: Playwright MCP permission denied (browser in use + resize denied) and WebFetch denied. Audit performed via direct read of VPS source (`/root/Projects/structural-isomorphism/web/frontend/`): 7 HTML templates + 10 CSS files + JS init handlers. No live screenshots taken. All pixel values below are from source CSS, not measured in-browser.

---

## Design system (read from `design-system.css`)

| Token | Value |
|---|---|
| `--bg-primary` | `#FAFAF9` (warm off-white) |
| `--text-primary / secondary / tertiary / quaternary` | `#18181B / #52525B / #A1A1AA / #D4D4D8` |
| `--accent` | `#2563EB` (Blue-600) |
| `--font-serif` | `Noto Serif SC`, Songti SC, Times |
| `--font-sans` | `Inter`, PingFang SC, system |
| `--font-mono` | `JetBrains Mono`, SF Mono |
| Spacing scale | 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64 / 96 / 128 (8px grid, clean) |
| Radii | 4 / 6 / 8 / 12 / 16 / 9999 |
| Max content width | 720px narrow, 1080px wide |

The token layer is genuinely well-built — Linear/Perplexity-level discipline. Component CSS does not hardcode values. **This is not where the problems are.**

---

## Per-page findings

### 1. `/` (home) — desktop 1440

**Structure** (from `index.html:44-240`):
- Hero section (`.home__hero`, `min-height: calc(85vh - 64px)`, centered)
- Decorative grid `::before` with radial mask (nice)
- Eyebrow pill → `<h1 class="home__brand serif">Structural</h1>` clamp(48–64px)
- Tagline: serif, clamp(22–28px)
- Lede with inline mono-font stats "87 / 4,475"
- **Hero inline evidence pill** (`.hero-evidence__pair`) — rotating example, 7×14px padding, pill shape
- Large multi-line textarea searchbox (780px max, `1.5px solid var(--text-tertiary)`, rounded 2xl, triple-layer shadow)
- Below-fold: 3 how-it-works cards, 3 use-case cards, daily-grid, favorites (hidden if empty)

**Good**: strong hero hierarchy, tasteful grid backdrop, the inline rotating "核物理 ≅ 药理学 94%" example right above the textarea is a smart credibility anchor.

**Issues**:
- **P1** — The hero stacks **eyebrow + H1 + tagline + lede + evidence pill + textarea + hint** all vertically centered in one viewport. At 1440×900 with 85vh hero + `--space-8` (64px) top padding, content is cramped. `home.css:36` uses `padding: var(--space-8) var(--space-5) var(--space-7)` = 64/24/48 which is OK but the `min-height: 85vh` on top of it pushes the footer scroll-hint off-screen on 900px-high windows.
- **P2** — `.home__lede` uses `var(--fs-15, 15px)` and `color: var(--text-tertiary)` (`#A1A1AA`). Tertiary-on-off-white contrast = **2.8:1**, fails WCAG AA for body text (needs 4.5:1). The numeric `<strong>` inside bumps to secondary (`#52525B`, 7.5:1 ✓), but the surrounding prose does not.
- **P2** — Searchbox footer uses `<kbd>⌘</kbd> + <kbd>Enter</kbd> 提交` but the kbd styling isn't defined in home.css (only in search.css for the editor hint). Inconsistent rendering likely.
- **P2** — `.how-step__text` uses `var(--fs-15, 15px)` + `line-height: 1.75`. Everywhere else body is 14/16. Orphan font size.
- **P2** — `.usecase__title` uses hardcoded `22px`, `.how-step__title` hardcodes `24px`, `.demo-pair__symbol` hardcodes `18px` — **violates the CLAUDE comment "Never use hardcoded values in component CSS"** stated in `design-system.css:3`. Inconsistency with the `--fs-*` scale.

### 2. `/search` — desktop 1440

**Init** (`search.js:643`): if no `?q=` param → **immediate `window.location.href = '/'`**. So the empty-state for `/search` literally doesn't exist in the running app — the user can never see it. Not broken, but means the only reachable states are loading skeleton / results / no-results.

**Reachable empty state** (query returned 0 results, `search.js:199`):
- Magnifier icon 56×56, serif title "没有找到足够相似的现象", helper text, two buttons (primary / ghost).
- Styled at `search.css:514-548` — max-width 560, `padding: var(--space-9) var(--space-5)` (96/24).

**Good**: helpful copy, correct affordances, consistent with tokens.

**Issues**:
- **P0** — **`<main class="search-page">` has NO sticky searchbar on /search**. Look at `search.html:48-51`: only `#search-summary` + `#search-results`. Yet `search.css:10-29` defines `.search-bar` with sticky styling — it's dead CSS. Users on results page cannot re-query without clicking "编辑" on the question header. The editor button is 32×80px in the top-right corner of the question card, visual afterthought.
- **P1** — `.search-question__text` uses `clamp(22px, 2.8vw, 30px)` serif. `.search-summary` wraps it in `max-width: 820px`. The "编辑" button is `position: absolute; top: var(--space-5); right: 0` — on narrow columns it overlaps wrapped question text.
- **P1** — Error state `.search-error` at `search.css:551-572` uses hardcoded reds `#fecaca / #fef2f2 / #991b1b / #b91c1c` — **bypasses `--danger: #DC2626`** defined in design-system. Breaks the token discipline and will drift if tokens change.
- **P2** — `.search-page` has `padding: var(--space-6) 0 var(--space-9)` but the summary and results both add their own `padding: 0 var(--space-5)` internally — double padding management, inconsistent gutters across children if any child forgets.

### 3. `/discoveries` — desktop 1440

**Structure** (`discoveries.html:47-71`): disc-hero (eyebrow pill, huge serif `clamp(48px, 7vw, 88px)` title "那些**隐藏**的联系", lede, stats), disc-filter, disc-list (skeleton initially).

**Good**: the 88px serif title is the boldest typographic statement in the app. Appropriate for a "curated findings" page. Stats row horizontal layout clean.

**Issues**:
- **P1** — `disc-hero__title` at `clamp(48px, 7vw, 88px)` + `line-height: 0.98` — at 1440 = ~100px clamped to 88. With `letter-spacing: -0.03em` (`--ls-tighter`). Chinese characters do not benefit from negative letter-spacing the way Latin does — **at 88px serif CJK with -0.03em, glyphs touch**. Noto Serif SC especially.
- **P2** — `.disc-filter` filter pills (from responsive.css `padding: 5px 10px`) at desktop inherit ambiguous size. On desktop they use unknown base; on mobile (≤768) shrunk to 5/10. Check desktop default.
- **P2** — stats use `gap: var(--space-7)` (48px) between 3 stats. Feels sparse if the row only has 3 numbers. Home/about use tighter gaps.

### 4. `/about` — desktop 1440

**Structure** (`about.html:42-122`): eyebrow, huge serif title `<br>`-broken "万物的形状<br>都在重复", lede, 5 sections with `Why / How / What's Next / Resources / Team` labels.

**Good**: the strongest narrative page. Clear typographic hierarchy, the `<br>`-broken title is intentional. Team card with single avatar is honest and small-indie-project correct.

**Issues**:
- **P2** — `about.css:16` title `font-size: clamp(48px, 6vw, 72px)` ≠ discoveries (88px) ≠ home (`clamp(48px, 5.5vw, 64px)`). **Three different hero-title scales across 3 landing pages** — no systematic type scale decision.
- **P2** — section label uses `var(--font-mono) + 11px + uppercase`, matching discoveries/analyze. Good.
- **P2** — `.about-stats` uses `var(--bg-tertiary)` (pure white `#FFFFFF`) on `--bg-primary` (warm `#FAFAF9`). The tonal shift is ~0.3% — effectively invisible on most monitors. Same issue repeats in `.how-step`, `.usecase`, `.demo-pair`, `.about-team` — all use white card on off-white background. Container affordance is carried entirely by the 1px `--border-subtle: #E4E4E7` border. If a user has low-contrast display or brightness cranked up, the cards disappear.

### 5. `/phenomenon/:id` — desktop 1440

**Critical**: `phenomenon.html:57` is literally `<div id="ph-content"></div>`. `phenomenon.js:762` DOMContentLoaded only calls `loadPhenomenon(id)` **if an id exists in the URL path**. **No else branch, no redirect, no empty state**. Visiting `/phenomenon` or `/phenomenon/` renders header+footer+blank white 100vh. Same for malformed IDs that 404 — handled (`.search-empty` at `phenomenon.js:748`) but only after fetch fails, so there's a flash of blank.

- **P0** — `/phenomenon` with no id = totally blank page between header and footer. Users who land here from a broken share link see nothing.

### 6. `/analyze` — desktop 1440

**Init** (`analyze.js:1084`): if no `?id=` → redirect home ✓. If `id` but no `q` / no `a_id` → redirect to `/phenomenon/{id}` ✓. Good defensive handling.

**Structure** (`analyze.html:1-166` + `analyze.css`): breadcrumb, question header with bridge chip showing "A → B", sticky progress indicator with 8 sections, streamed content areas with skeleton `.wait-indicator`.

**Issues**:
- **P1** — `analyze.html` has **70 lines of `<style>` inline** (lines 19-69) for analyze-actions. Comment says `"analyze.css is off-limits"` — someone worked around the style system instead of adding to it. That rule should be documented or removed.
- **P2** — The sticky `.analyze-progress` at `top: calc(var(--header-height) + var(--space-3))` uses `rgba(250, 250, 249, 0.9)` + `backdrop-filter: blur(12px)`. The header itself uses `rgba(250, 250, 249, 0.85) + saturate(180%) blur(20px)` (common.css:22). **Two different glass-effect formulas stacking** — when scrolling, header blur over page, progress-bar blur over header blur. Firefox will render this inconsistently.

---

## Mobile (375×812)

Responsive CSS exists and is careful (`responsive.css`, 451 lines). Breakpoints: 1024 / 768 / 480.

**Good**:
- Hides GitHub link ≤768 (`responsive.css:42`)
- Stacks all 2-column grids to 1fr
- Reduces `--space-7/8/9/10` by ~30% inside 768 media query (tokens get overridden — elegant)
- Disables `:hover` transforms on `(hover: none)` touch devices
- Honors `prefers-reduced-motion`
- Hides `.disc-item__rank` and `.param-mapping__head` on mobile — understood that "compact table headers" don't fit

**Mobile issues**:
- **P1** — `home.css` searchbox at `--multi` variant uses `padding: var(--space-5) var(--space-5) var(--space-4)` (24/24/16) and a 3-row `<textarea>`. On 375-wide with 16px body padding from container, textarea inner width = 375 − 48 (container) − 48 (wrapper) = **279px**. Chinese at 14px = ~19 chars per line. Placeholder text `"一句话描述你观察到的现象、问题或正在做的研究方向。..."` (30 chars) will wrap immediately and the two-line placeholder becomes 4 lines — looks like the textarea is pre-filled.
- **P1** — `.searchbox__submit--primary` has a text label "深度分析" + arrow icon. On mobile responsive reduces `.searchbox__submit` to 44×44 square (`responsive.css:89-92`) — the text label "深度分析" **will not fit in 44px**. Label will either overflow or get clipped. Need a mobile-specific rule to hide `.searchbox__submit-label` ≤480.
- **P2** — `responsive.css:50-52` shrinks `--space-7/8/9/10` inside `@media (max-width: 768px)`. But `--space-10: 88px` is used as `.home__section { margin-bottom: var(--space-10) }` = 88px gaps between sections on mobile. Too airy for 812px tall screens. 48-56 would be better.
- **P2** — Home inline evidence pill at ≤720 (`home.css:207`) wraps + `white-space: normal` but `.hero-evidence__pair` still has `flex-wrap: wrap; justify-content: center`. With 4 flex children (side, ≅, side, score) on 343px wide, the "≅" symbol risks landing on its own line between the two phenomenon names — visually wrong (reads as "A ≅ | B" instead of "A ≅ B").
- **P2** — Discoveries hero title `clamp(48px, 7vw, 88px)` on 375-wide = **48px** (clamped to min). `responsive.css:270` overrides to `clamp(36px, 10vw, 56px)` = 37.5px. Better. But the `responsive.css:454-456` @≤480 rule only targets `.home__brand`, not `.disc-hero__title` — at 375 wide the discoveries title stays at 37.5px which is still large-for-mobile.

---

## Cross-page consistency issues

1. **Three different hero title scales**: home `clamp(48,5.5vw,64)`, about `clamp(48,6vw,72)`, discoveries `clamp(48,7vw,88)`. No systematic reason given — they read as ad-hoc.
2. **Hardcoded pixel values** in 4 files despite the design-system.css prohibition: `home.css` (`18px, 22px, 24px`), `search.css` error reds, `about.css` team avatar (56px), `analyze.html` inline style block. Tokens exist; components don't use them.
3. **Card background tonality too subtle**: `.how-step / .usecase / .about-stats / .about-team / .demo-pair` all use `--bg-tertiary #FFF` on `--bg-primary #FAFAF9`. Cards are 99.7% identical to the page bg. Carrying the entire affordance on 1px `#E4E4E7` is risky on low-contrast displays.
4. **Glass-morphism stacking**: header + search-page sticky bars + analyze-page progress bar all use different `rgba(250,250,249, α)` + `blur()` recipes. Inconsistent α and blur radii.
5. **No favicon referenced** in any HTML `<head>` (`grep -n favicon /tmp/si-*.html` → 0 hits). Browser tab uses default. Logo SVG is inline-only — no `rel="icon"`.
6. **No OG image** on any page except analyze (`analyze.html:13: /assets/og-image.png`). Home/about/discoveries have no social-share card metadata — shared links will look naked.
7. **Footer copy drift**: home footer shows `关于 / 论文 / GitHub`, search shows `关于 / GitHub` (no 论文), discoveries shows `首页 / 关于 / 论文`, phenomenon shows `关于 / 论文 / GitHub`, about shows `首页 / 论文 / GitHub`. **Every page has a different footer link set.**
8. **Page title drift**: home `Structural — 万物的形状都在重复`, search `搜索 — Structural`, discoveries `精选发现 — Structural`, phenomenon `现象详情 — Structural`, analyze `深度分析 — Structural`, about `关于 — Structural`. Order flip on home only (tagline first vs. last). Pick one pattern.
9. **No mention of `beta` anywhere in the UI**. Site is at `beta.structural.bytedance.city` but neither header badge nor footer mentions it — users can't tell they're on a beta build vs. production.

---

## P0 / P1 / P2 consolidated

### P0 (broken)
1. **`/phenomenon` (no ID) renders blank content area.** No redirect, no empty state. `phenomenon.js:762` missing else branch. **Fix**: redirect to `/` or show a friendly message.
2. **`/search` has dead CSS for `.search-bar`** (80+ lines in `search.css:10-29`) but the HTML template never renders it. Users on results page cannot start a new search without clicking the tiny "编辑" button in the top-right. **Fix**: either render `.search-bar` at the top of `<main>`, or delete the dead CSS.

### P1 (bad UX)
3. **Mobile searchbox submit button text overflow**: "深度分析" label does not fit in 44px submit button ≤768. Hide label on mobile.
4. **Mobile hero evidence pill** risks breaking "A ≅ B" atomicity on wrap. Use `display: grid` with fixed 3-column template at ≤720.
5. **Body text contrast below AA**: `.home__lede` and `.how-step__time` use `--text-tertiary #A1A1AA` on `#FAFAF9` = 2.8:1. Promote to `--text-secondary` for prose.
6. **Analyze page has 70 lines of inline `<style>`** because "analyze.css is off-limits". Either remove that rule or move these styles into common.css as proper tokens.
7. **CJK letter-spacing**: `disc-hero__title` uses `--ls-tighter -0.03em` at 88px serif. Chinese glyphs touch. Override to `ls-normal` for CJK headers specifically.

### P2 (polish)
8. **Three hero title scales** — unify to a single `--fs-hero-lg / md / sm` set in design-system.
9. **Hardcoded px values** in `home.css` (18/22/24px), `search.css` (error reds) — use tokens.
10. **Card bg tonality** too subtle — shift `--bg-tertiary` by 2-3 lumens or rely on shadow instead of the 1px border.
11. **Missing favicon + OG image** on all pages except analyze.
12. **Footer link drift** across 6 pages — make it a shared template.
13. **No `beta` indicator** in UI.
14. **Mobile `--space-10` too generous** (88px between sections on a 812px screen).

---

## Top 5 visual fixes to prioritize

1. **Fix `/phenomenon` blank state** — one-line else branch in `phenomenon.js:762` redirecting to `/` (P0, 2 min).
2. **Render a sticky re-search bar on `/search`** — the CSS already exists; add `<div class="search-bar"><form class="searchbox">...</form></div>` to `search.html:48`. Biggest UX win on the whole site. (P0, 20 min)
3. **Unify footer + add favicon + OG image** — extract shared header/footer partial, add `<link rel="icon">`, add a default OG image. Kills 4 P2 issues in one pass. (P2, 1 hr)
4. **Hide submit label on mobile + fix evidence pill wrap + raise lede contrast to `--text-secondary`** — three surgical responsive.css fixes, massive mobile polish gain. (P1, 30 min)
5. **Move the `analyze.html` inline styles + `search.css` error colors + `home.css` hardcoded font sizes into design-system tokens** — enforce the rule the design system itself states in its header comment. (P2, 1 hr)

---

## What I couldn't verify without a live browser

- Actual rendered Chinese typography quality (Noto Serif SC fallback chain behavior)
- Hover/focus states firing correctly
- Loading spinner animations (`breathe`, `breathGlow`, `shimmer`) smoothness
- Actual contrast ratios as rendered (OS font smoothing affects them)
- JavaScript-rendered empty states for discoveries/analyze streams
- How the `::before` grid backdrop looks with the `radial-gradient` mask on Safari vs Chrome
- Whether the KaTeX fonts load and clash with Inter

If Playwright permissions become available, the priority screenshots to capture are: (a) `/search?q=test` mid-stream to see the 3-timer/3-phase loading UI, (b) `/discoveries` at 1440 to verify the 88px CJK title spacing, (c) `/` at 375 to see the textarea placeholder wrap and submit button overflow.
