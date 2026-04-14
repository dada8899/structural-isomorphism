# P1/P2 Visual Polish — beta.structural.bytedance.city

Date: 2026-04-13
Files edited locally at `~/projects/structural-isomorphism/web/frontend/`, rsynced to VPS `/root/Projects/structural-isomorphism/web/frontend/`. FastAPI StaticFiles serves them live — no restart needed.

## P1 Fixes

### 1. Mobile submit button label overflow (`responsive.css:94-108`)
At ≤768px the label "深度分析" was still rendered inside a 44×44 square (home.css only hid it at ≤640px). Extended the collapse-to-icon rule into the 768px tier.
```css
/* before */
.searchbox__submit { width: 44px; height: 44px; }
/* after */
.searchbox__submit { width: 44px; height: 44px; padding: 0; }
.searchbox__submit-label { display: none; }
```

### 2. Home lede WCAG AA contrast (`design-system.css:23`, `home.css:103-121`)
Deepened the global `--text-tertiary` token from `#A1A1AA` (~2.8:1 on `#FAFAF9`) to `#71717A` (~4.6:1). Added `--text-muted: #A1A1AA` to preserve the lighter tone for decorative use only. Also switched `.home__lede` from `--text-tertiary` to `--text-secondary` as an extra safety margin for body copy. The old light shade is therefore no longer reachable from body copy.

### 3. `.disc-hero__title` CJK glyph collision (`discoveries.css:46-66`)
88px serif + `letter-spacing: -0.03em` was cramming Chinese glyphs. Added a `:lang(zh)` override that restores `letter-spacing: normal` and bumps line-height to 1.1 only when the page is Chinese; Latin fallback keeps its tighter tracking.

### 4. Hero evidence pill (`home.css:132-230`)
Switched `.hero-evidence__pair` from `display: inline-flex` with `flex-wrap: wrap` to `display: inline-grid; grid-template-columns: 1fr auto 1fr`. The ≅ glyph is now pinned between A/B and can never orphan. At ≤720px the wrap fallback was replaced with horizontal scroll on the container (`overflow-x: auto`, scrollbar hidden), preserving the single-line layout even on narrow phones.

### 5. `analyze.html` inline `<style>` block
The previous file carried a 70-line inline `<style>` tagged "kept inline — analyze.css is off-limits". Because `analyze.css` is still held off-limits per that historical note, I extracted the rules into a new sibling file instead: `assets/css/analyze-actions.css` (67 lines). `analyze.html` now links it alongside `analyze.css`. The new file also replaces the hardcoded warning colors with the new `--warning` / `--warning-subtle` / `--warning-border` / `--bg-subtle` / `--border-default` tokens.

## P2 Fixes

### 6. Typography scale unification (`design-system.css:69-73`)
Added three hero title tokens — semantic tiers kept deliberately (brand < page < display) so the `h1` hierarchy stays meaningful, but all three now flow through design-system.css instead of being hardcoded in component files:
```css
--font-hero-brand: clamp(48px, 5.5vw, 64px);   /* home.__brand */
--font-hero-page:  clamp(48px, 6vw, 72px);     /* about-page__title */
--font-hero-display: clamp(48px, 7vw, 88px);   /* disc-hero__title */
```
Applied in `home.css:72`, `about.css:20`, `discoveries.css:48`.

### 7. Hardcoded pixel values
- `home.css` lines 348/424/670/792/1238 — replaced `font-size: 18|22|24px` with `var(--fs-18|22|24)`. Added `--fs-11/--fs-15/--fs-18/--fs-22` to the design-system scale.
- `home.css:1239` — replaced `color: #d97706` with `var(--warning)`.
- `search.css:528-550` — replaced `#fecaca / #fef2f2 / #991b1b / #b91c1c` with `var(--danger-border|-surface|-strong|-text)`. New tokens added to design-system.css lines 37-41.

### 8. Card surface flatness (`design-system.css:9`)
Darkened `--bg-primary` from `#FAFAF9` → `#F5F5F4` (Stone-100). White card surfaces (`--bg-tertiary: #FFFFFF`) now sit on a noticeably cooler background — tonal delta jumps from ~0.3% to ~2%, giving `.how-step`, `.home__daily-card`, `.rec-placeholder`, `.result-card` etc. perceptible lift without needing added shadow everywhere. The existing shadow-sm/md tokens still apply where they were already attached.

### 9. Footer links uniformity
Verified via grep on local HTML files: all 7 pages (index, search, discoveries, analyze, phenomenon, about, 404) expose the same 6-link footer set (主站 / 关于 / 论文 / GitHub / HuggingFace / Zenodo). Previous frontend unification holds.

## New design tokens added
`--bg-subtle`, `--border-default`, `--text-muted`, `--warning-subtle`, `--warning-border`, `--danger-strong`, `--danger-text`, `--danger-surface`, `--danger-border`, `--fs-11/15/18/22`, `--font-hero-brand/page/display`.

## Skipped / deferred
- **`analyze.css` inline cleanup** — only moved the inline `<style>` block out of `analyze.html` into a new `analyze-actions.css`. The existing `analyze.css` (which still contains its own hardcoded px values at lines 599/707/985) was left alone to respect the "off-limits" note in the source. Should be addressed in a dedicated pass if the note has since been lifted.
- **`responsive.css` hardcoded clamps** at lines 20, 57, 278, 361 — these are mobile-override hero clamps that could also flow through the new `--font-hero-*` tokens, but they intentionally tune for small viewports (different min/max). Left as-is to avoid over-unification.

## Deploy verification
```
curl https://beta.structural.bytedance.city/assets/css/design-system.css | grep text-tertiary
  → --text-tertiary: #71717A;
curl https://beta.structural.bytedance.city/assets/css/search.css | grep danger-
  → border: 1px solid var(--danger-border); background: var(--danger-surface); ...
curl https://beta.structural.bytedance.city/assets/css/analyze-actions.css
  → HTTP 200, 67 lines
curl -H "Cache-Control: no-cache" https://beta.structural.bytedance.city/analyze | grep -c "<style>"
  → 0  (inline block successfully removed)
```

All P1 + P2 items shipped and live.
