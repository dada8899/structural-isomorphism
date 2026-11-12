# /discoveries CLS verification — W3-B skeleton effectiveness

**Date**: 2026-05-14
**Session**: #8 (W1-B frontend polish)
**Tool**: Playwright Chromium + PerformanceObserver `layout-shift`
**Script**: `scripts/measure_cls_discoveries.py`
**Page**: `https://beta.structural.bytedance.city/discoveries`
**Viewport**: 1280×800 desktop, headless Chromium
**Measurement**: navigate → networkidle → wait 3s → 1px scroll tick → read `__clsValue`

## TL;DR

| Phase                                   | CLS     | Web Vitals rating  |
|-----------------------------------------|---------|--------------------|
| Pre W1-B (W3-B skeleton only)           | 0.2186  | NEEDS IMPROVEMENT  |
| Post W1-B (skeleton tuning + min-heights)| 0.1967  | NEEDS IMPROVEMENT  |
| Target (Web Vitals "good")              | < 0.10  | GOOD               |

W1-B reduced CLS by **0.0219 absolute (-10%)**. The page is still above the 0.1 "good" threshold because of one dominant shift not addressable from CSS alone (web-font swap of `Noto Serif SC` on the hero `<h1>`).

## Top shift contributors (post W1-B)

| Rank | Value  | Time   | Source (top node)                                  | Cause                                                                                                    |
|------|--------|--------|----------------------------------------------------|----------------------------------------------------------------------------------------------------------|
| #1   | 0.1845 | 1115ms | `MAIN.disc-page` (descendant glyph reflow)         | Web-font swap of `Noto Serif SC` on `.disc-hero__title` — system fallback baseline ≠ web-font baseline. |
| #2   | 0.0078 | 1580ms | `#disc-filter` (dy=+34px)                          | Filter skeleton was overshooting actual rendered height; tuned to 2 rows (was 3).                       |
| #3   | 0.0025 | 1533ms | `#disc-filter` (dy=-20px)                          | Intermediate render between skeleton and final.                                                          |
| #4   | 0.0018 | 1949ms | text inside `.disc-hero__eyebrow` (dy=+2px)        | Sub-pixel reflow from font metrics.                                                                      |
| #5   | ~0     | 10460ms| #text (dy=-3px)                                    | Cosmetic, not a real shift (rounding).                                                                   |

Shift #1 alone is **94% of total CLS**. Without it, CLS would be 0.012 — well under the "good" 0.1 threshold.

## Pre-vs-post shift breakdown

| Shift                                  | Pre W1-B | Post W1-B | Δ        |
|----------------------------------------|----------|-----------|----------|
| Hero h1 font swap (MAIN.disc-page)     | 0.1845   | 0.1845    | unchanged|
| disc-filter → final filter render      | 0.0244   | 0.0078    | **-0.0166** |
| disc-filter intermediate               | 0.0079   | 0.0025    | **-0.0054** |
| Misc text reflow (eyebrow, text shifts)| 0.0018   | 0.0019    | ±0       |
| **Total**                              | **0.2186** | **0.1967** | **-0.0219** |

## What W1-B changed

1. **`disc-filter` skeleton: 3 rows → 2 rows** (matches real render — `.disc-tier-tabs` + 1 `.disc-filter-row`)
   - File: `web/frontend/discoveries.html` + `web/frontend/assets/js/discoveries.js`
2. **`.disc-filter` min-height: 160px** reserved (CSS `min-height` guard)
   - File: `web/frontend/assets/css/discoveries.css`
3. **`.disc-hero__stats` min-height: 80px + flex `align-items: center`** (matches skeleton)
   - File: `web/frontend/assets/css/discoveries.css`

## What still needs fixing (out of W1-B scope)

The dominant remaining CLS source is **`Noto Serif SC` web-font swap on hero `<h1>`**.

**Concrete fix proposal for next session**:

1. **Self-host Noto Serif SC subset** (CJK + ASCII), preload as binary:
   ```html
   <link rel="preload" href="/assets/fonts/noto-serif-sc-subset.woff2"
         as="font" type="font/woff2" crossorigin>
   ```
   Replace the Google Fonts `<link>` for `Noto Serif SC` with a self-hosted `@font-face`:
   ```css
   @font-face {
     font-family: "Noto Serif SC";
     src: url("/assets/fonts/noto-serif-sc-subset.woff2") format("woff2");
     font-display: optional;       /* don't swap — render fallback if not ready in 100ms */
     size-adjust: 96%;             /* match system-ui PingFang SC baseline */
     ascent-override: 90%;
     descent-override: 22%;
   }
   ```
2. Alternatively (cheaper but lower-quality): downgrade hero `<h1>` to system stack:
   ```css
   .disc-hero__title {
     font-family: -apple-system, "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
   }
   ```
   Removes web-font shift entirely; loses brand serif look. Not recommended.

Expected outcome: dominant shift → ≤0.005 → **total CLS ≈ 0.015 ("GOOD")**.

## Reproducibility

```bash
cd /Users/dadamini/Projects/structural-isomorphism
./.venv/bin/python scripts/measure_cls_discoveries.py
```

Output prints full shift JSON + `== CLS: X.XXXX  (GOOD|NEEDS IMPROVEMENT|POOR)` summary line. Run multiple times — CLS can vary ±0.02 between runs due to network conditions affecting font load timing.
