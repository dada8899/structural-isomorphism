# Mobile Design System — Phase Detector

**Status:** v1 baseline shipped in W12-C (session #10, 2026-05-15).
Applies to `web/phase-detector/`. Sister beta site (`web/frontend/`) inherits
the same primitives via `web/shared/tokens.css`.

This is the **rule book** for everything mobile in Phase Detector. If you
add or change a UI primitive, update this file in the same PR.

---

## 1. Touch targets

**Rule:** Every clickable / tappable element must be **≥44 × 44 CSS px**.

Source: Apple HIG ("Minimum tappable area"), WCAG 2.5.5 Level AAA, Android
Material guideline (48dp ≈ 44 CSS px).

### How to comply

| Pattern | Implementation |
|---|---|
| Icon-only button | `inline-flex h-11 w-11 items-center justify-center …` |
| Small filter pill / chip | Wrap with `.touch-target-44` (pseudo-element expander) |
| Solid CTA | `min-h-[44px] px-4 py-3 …` |
| Text link in body copy | Add `py-2 -my-2 inline-block` to grow the hit zone without growing visual height |
| Whole-card link | Use absolute-positioned `<Link className="absolute inset-0 z-0">…` (already used in `CompanyCard`) |

### Common offenders (audited W12-C)

- `<button>` with `py-1.5` (35px tall) → bumped to `py-2 min-h-[44px]`
- Pricing interval toggle (`py-1.5`) → bumped
- ScreenerFilter reset button → bumped
- Mobile-nav drawer items → `min-h-[44px]`
- Paywall modal close X (`p-1`) → 11×11 → `h-11 w-11`
- Hamburger toggle (`h-9 w-9`) → `h-11 w-11`

---

## 2. Safe-area handling (iOS notch / Dynamic Island / home indicator)

**Viewport meta** (set globally in `app/layout.tsx`):

```
viewport-fit: cover
initial-scale: 1
maximum-scale: 5     ← do NOT lock to 1
user-scalable: true  ← pinch-zoom MUST stay on for charts + dense data
```

**CSS utilities** (defined in `app/globals.css`):

- `.safe-area-top` — `padding-top: env(safe-area-inset-top, 0)`
- `.safe-area-bottom` — same for bottom
- `.safe-area-left` / `.safe-area-right`
- `.safe-area-body` — left + right combined

Apply to:
- The sticky `<header>` (notch padding)
- The `<footer>` (home-indicator clearance)
- The `<body>` (gutter on landscape phones)

On non-iOS, `env(safe-area-inset-*)` evaluates to `0` — these utilities are
free no-ops on Android / desktop.

---

## 3. Scroll behavior

### Smooth anchor scrolling

`html { scroll-behavior: smooth; }` in `globals.css`. Wrapped in
`@media (prefers-reduced-motion: reduce)` to honor user preference.

### Sticky-nav slide pattern

Below `sm: 640px`, the top header **slides up out of view when scrolling
down** and reveals on scroll-up. Implemented via:
- `useScrollDirection` hook (rAF-throttled scroll listener)
- TopNav toggles `data-nav-hidden="true"` on the closest `<header>`
- CSS handles the `transform: translateY(-100%)` transition (220 ms easing)

Disabled at sm+ (desktop header always visible) and while the mobile drawer
is open.

### Pull-to-refresh

`usePullToRefresh()` in `lib/useSwipe.ts`. Wire on `/companies` and
`/newsletter` (any list page where freshness matters). Threshold default
**80 px** drag from the very top of the page (`scrollY === 0`).

---

## 4. Pinch-zoom

**Enabled globally.** Charts (PhaseTrajectoryChart, UniversalityAnalogueMap,
SparkLine) and dense data tables need pinch-zoom for legibility.

For aggressive zoom inside scroll-locked containers, opt in with
`className="allow-pinch-zoom"` (sets `touch-action: pinch-zoom`).

### Wide tables on mobile

Wrap `<table>` in `<div className="table-scroll-mobile">` for momentum
horizontal scroll on touch devices (`-webkit-overflow-scrolling: touch`).
Tailwind doesn't ship this by default.

---

## 5. Gestures

All gestures use `PointerEvent` via the `useSwipe()` hook in
`lib/useSwipe.ts`. We deliberately **don't ship Hammer.js** (~7 kB gz) —
left/right/up/down swipes are easy enough to build natively, and PointerEvent
is the spec everyone supports now.

### Vocabulary

| Gesture | Page | Action |
|---|---|---|
| Swipe ← | `/company/[ticker]` | Navigate to next ticker |
| Swipe → | `/company/[ticker]` | Navigate to previous ticker |
| Swipe ↓ on modal | `PaywallModal` | Close (iOS sheet pattern, drag handle visible) |
| Pull-to-refresh | `/companies`, `/newsletter` | Re-fetch list |

### Thresholds (defaults)

- Distance: **50 px** (60 px for ticker swipe — slight buffer to avoid
  accidental fires while scrolling)
- Max duration: **600 ms**
- Min velocity: **0.2 px/ms**

Below threshold ⇒ no-op. Vertical scroll is preserved (we only
`preventDefault` on a *confirmed* horizontal swipe).

---

## 6. Breakpoints (Tailwind)

| Name | Width | Typical device |
|---|---|---|
| (default) | < 640 px | Phones, portrait |
| `sm:` | ≥ 640 px | Large phones landscape |
| `md:` | ≥ 768 px | iPad portrait |
| `lg:` | ≥ 1024 px | iPad landscape, small laptop |
| `xl:` | ≥ 1280 px | Desktop |

### Multi-column layouts

For browse pages (`/companies`, `/universality`):
- 1 col on phones
- 2 col on `sm:` (large phone landscape + iPad portrait)
- 3 col on `lg:` (iPad landscape, laptop)

For the ExploreCardsGrid on the landing page: same.

If you need a tighter tablet-portrait jump, add a `md:grid-cols-2` *between*
the `sm:` and `lg:` lines — but only when designed-for, not by reflex.

---

## 7. Mobile-first visualizations

Re-audited in W12-C:

- **PhaseTrajectoryChart** — sized via container `aspectRatio: 2/1` on
  mobile, 3/1 on desktop. Tooltips clamp to viewport edge.
- **UniversalityAnalogueMap** — force-directed graph has touch-friendly
  zoom controls (pinch-zoom enabled). Node count capped to 50 on mobile.
- **SparkLine** — pointer-events auto, IntersectionObserver-revealed.

When in doubt: pinch-zoom enabled means charts can stay information-dense
without needing a mobile-only stripped-down variant.

---

## 8. Performance

Mobile budget (Lighthouse, slow-4G throttle, Moto G4):

- LCP: **< 2500 ms** (CWV "good") — gated by `test_mobile_lcp.py`
- CLS: **< 0.1** — gated by Lighthouse CI
- TBT: **< 200 ms**

Bundle audit pass in W12-C: phase-detector compressed JS < 200 kB.
Images: `loading="lazy"` on offscreen, `fetchpriority="high"` on hero.

---

## 9. Reduced motion

`@media (prefers-reduced-motion: reduce)` kills all `animation-duration`
and `transition-duration` globally (set in `globals.css`). Critical state
changes still render — we just don't animate them. Respect users.

---

## 10. Testing

- **Unit:** `useSwipe` and `useScrollDirection` are pure hook logic →
  testable with `@testing-library/react` + jsdom.
- **Visual regression:** `web/tests/e2e/test_mobile_visual.py` —
  **32 cases** (4 viewports × 8 pages). Baseline lives in
  `web/tests/e2e/screenshots/mobile-visual/baseline/`. Update via
  `UPDATE_VISUAL_BASELINES=1 pytest …`. Diff threshold: 5% pixel
  delta.
- **Real-device manual:** before any release, walk every page on a
  physical iPhone (SE + Pro Max) and an iPad. Auto tests catch
  regressions; real fingers catch new bugs.

---

## 11. Changelog

| Date | Session | Author | Change |
|---|---|---|---|
| 2026-05-15 | #10 W12-C | sub-agent C | v1 baseline: touch targets, safe-area, swipe nav, smooth scroll, pinch-zoom, slide-on-scroll header, mobile-visual regression suite |
