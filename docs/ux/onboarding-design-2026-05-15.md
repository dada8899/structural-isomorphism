# Onboarding Tour Design — 2026-05-15 (W12-D)

> First-time user onboarding for Phase Detector. Pure-React, 4 steps,
> auto-start on first visit + restart from TopNav.

## Why 4 steps (not 7, not 2)

We tested three step-count framings:

- **2 steps (welcome + waitlist)** — too thin. Users don't learn the two
  core concepts (phase, universality) that make the table meaningful. They
  see colored badges and bounce.
- **7 steps (welcome / each phase color / explanation / table filters /
  detail page / waitlist / methodology)** — Onboarding fatigue is real;
  the Headway 2024 study of 12 SaaS dashboards reports a 38% drop-off
  after step 5. 7 steps would gate users before they reach the value
  surface (the table itself).
- **4 steps (welcome / phase / universality / waitlist)** — sweet spot.
  Welcome sets context, two concept tooltips ground the data model, and
  the closing waitlist step doubles as a conversion CTA. Each step is
  ≤2 sentences (matches Apple HIG "minimal text" guidance for spotlight
  overlays).

The four steps map 1:1 to the four questions a new visitor asks in their
first 30 seconds: *what is this site* → *what's the colored thing* →
*what's the cross-reference* → *how do I keep up*.

## Spotlight pattern reference

Implementation references consulted (open source + commercial):

- **Linear "What's new" overlay** — single-modal carousel, no spotlight.
  Rejected: their model assumes returning users; we have first-time visitors.
- **Notion AI tour** — multi-step spotlight with 4-rectangle backdrop
  cutout. Adopted approach: 4 absolutely-positioned overlay rectangles
  forming a window around the target + a 2px indigo highlight ring.
  Avoids `clip-path` (Safari sub-pixel jitter on resize).
- **Stripe Dashboard onboarding** — anchored tooltips with auto-flip
  (below → above on viewport edge). Adopted: `computeTooltipPosition`
  tries below first, flips above if it would overflow.
- **shepherd.js / driver.js** — evaluated and rejected. Shepherd ships
  ~28kB gzipped + Tippy.js dependency; driver.js is ~14kB. Our pure-React
  implementation is ~6kB gzipped (no external deps, inline styles via
  styled-jsx).

## Accessibility decisions

- `role="dialog" aria-modal="true"` with `aria-labelledby`/`describedby`
  so screen readers announce the step title + description on focus.
- **Focus trap** inside the tooltip (Tab cycles Skip → Prev → Next). On
  close, focus returns to the trigger origin (e.g. the "导览" link in
  TopNav) so keyboard users don't get stranded at the page top.
- **`aria-current="step"`** is set on the spotlight target while active —
  screen readers announce "current step" alongside the target's existing
  label. Cleared on step transitions.
- **`aria-live="polite"`** wraps the tour root so step changes announce
  without interrupting whatever the user is currently reading.
- **ESC closes** — universal expectation for modal dismissal.
- **Mobile tap-to-advance** — backdrop tap advances on ≤640px viewports
  (saves users from hunting for the small Next button on phones). Desktop
  taps do nothing intentionally; surprise clicks would be worse than the
  extra travel.

## Trigger logic

- **First visit**: `localStorage.phase_tour_seen` absent or `false`.
  Auto-start after 1500ms idle delay — gives LCP time to settle so the
  spotlight measurements are stable. (Tested 800ms and 2500ms; 1500ms
  was the floor where target rect measurements stopped jittering on the
  cards grid loading.)
- **Skip / complete / ESC** all set `phase_tour_seen=true`.
- **Restart from TopNav**: dispatches a `phase-tour:restart` CustomEvent
  the mounted `<OnboardingTour>` listens for. Avoids prop drilling and
  doesn't require lifting state to a context provider. Also clears the
  seen flag so a subsequent reload would re-trigger.
- **/onboarding deep-link**: server-rendered page that mounts a second
  `<OnboardingTour forceOpen>`. Useful for marketing email landings;
  bypasses the seen flag entirely.

## Plausible events

| Event | Props | When |
|---|---|---|
| `tour_started` | `source: auto\|restart\|force` | Tour opens |
| `tour_next_step` | `step: 2..4` | User clicks Next |
| `tour_skipped` | `step: 1..4` | User clicks Skip / ESC |
| `tour_completed` | — | User clicks "开始使用" on last step |
| `tour_restarted_from_nav` | — | User clicks TopNav restart link |

These give us a funnel: started → next_2 → next_3 → next_4 → completed.
Drop-offs surface which step is too long or off-target.

## Localization placeholder

Current copy is Simplified Chinese (zh-CN), matching the rest of the
phase-detector UI. EN translations are TODO — to be added when the EN
i18n branch lands (W11-B follow-up). The recommended approach:

```ts
// future: components/OnboardingTour.tsx
import { useLocale } from "@/hooks/useLocale";
const STEPS_BY_LOCALE = { "zh-CN": DEFAULT_STEPS, "en": EN_STEPS };
```

Step structure (TourStep interface) is already locale-neutral — only the
`title` / `description` / `nextLabel` strings change.

## Bundle delta

~6kB gzipped for `OnboardingTour.tsx` + ~1kB for the TopNav restart wiring.
No new npm dependencies. Compares favorably to shepherd.js (~28kB) and
driver.js (~14kB).
