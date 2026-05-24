# Visualization architecture — 2026-05-15 (W11-D)

> Three new interactive visualizations shipped for `/company/[ticker]`,
> `/universality/[class_id]`, and the `/companies` screener. This doc
> captures the choices, the bundle/perf trade-offs, and a recipe for
> adding a new viz.

## TL;DR

- **No external chart library** — every viz is hand-written SVG +
  React state. We considered `d3` modules and `@observablehq/plot`;
  both lose on bundle size vs. our needs (≤ 13 nodes, ≤ 24 line
  points, no axes orchestration beyond labels).
- **Three components** under `web/phase-detector/components/`:
  - `PhaseTrajectoryChart.tsx` — 12-month structural-distance line
    with phase bands, hover tooltip, drag-to-brush selection.
  - `UniversalityAnalogueMap.tsx` — force-directed graph of evidence
    systems + prototypes around a center class node.
  - `SparkLine.tsx` — 12-point trajectory with phase-band segment
    colors, IntersectionObserver reveal, hover tooltip.
- All three are SSR-safe (deterministic seeded layout), respect
  `prefers-reduced-motion`, and reserve aspect-ratio space so CLS = 0.

## Why not @observablehq/plot or d3?

`@observablehq/plot` is a great library — declarative, well-tested,
~80 kB unminified. But:

1. It pulls in d3 transitively (`d3-array`, `d3-scale`, `d3-shape`,
   `d3-interpolate`, `d3-format`, `d3-time`). Even with tree-shaking
   that's ~25 kB gzipped just for the chart-rendering primitives.
2. Our data is small — 12 monthly points for the trajectory, ≤ 13
   nodes for the analogue map. Hand-writing the SVG path is < 30
   lines per chart, no library required.
3. We need consistent design-system colors (phase bands, CPS badges,
   sector labels). Plot's default theme conflicts with our zinc/amber/
   emerald palette — overriding via marks costs the same code as
   writing SVG from scratch.
4. d3-force was the one piece I considered keeping: its quadtree
   makes large-graph repulsion cheap. For 13 nodes my hand-rolled
   O(n²) repulsion is < 0.05 ms per iteration — d3-force is overkill
   and adds ~10 kB gzipped.

Net: **0 kB** added to the bundle for charting library; we pay only
for the components themselves.

## Bundle sizes (production build, gzipped estimate)

Measured from `next build` route weights minus the page's pre-W11-D
baseline:

| Route                          | Total | Δ (this PR) |
|--------------------------------|-------|-------------|
| `/company/[ticker]`            | 11.4 kB | +5.8 kB (PhaseTrajectoryChart) |
| `/companies`                   | 19.0 kB | +4.2 kB (SparkLine × N cards) |
| `/universality/[class_id]`     | 11.1 kB | +6.1 kB (UniversalityAnalogueMap) |

After gzip these are roughly 35-40% of the wire size:
**PhaseTrajectoryChart ≈ 2.3 kB**, **SparkLine ≈ 1.7 kB**,
**UniversalityAnalogueMap ≈ 2.5 kB** gzipped. All under the 50 kB
per-viz budget by 20×.

## Component composition

```
/company/[ticker]/page.tsx
  └── PhaseTrajectoryChart      (synthesized series → SVG)

/universality/[class_id]/page.tsx
  └── UniversalityAnalogueMap   (detail.evidence_systems + prototypes
                                  → buildGraph → relax simulation → SVG)

/companies/page.tsx
  └── CompanyCard
       └── SparkLine            (synthesized series, IO-revealed
                                  segment-colored SVG)
```

All three live in `components/` (not in a `viz/` subfolder) to match
the existing convention where every reusable React component is flat
under one directory. If we add 5+ more visualizations we will pull
them into `components/viz/`.

## Performance trade-offs

1. **No canvas, no WebGL** — SVG is plenty for ≤ ~200 nodes/points.
   Switching to canvas would add 5-10 kB of canvas-rendering code
   and lose accessibility (no native SVG `role="img"` semantics).
2. **Synthesized data until BE ships time-series** — every viz
   accepts a `Company` or `UniversalityClassDetail` and derives the
   shape it needs. When `/api/company/<ticker>/trajectory` lands,
   we swap `generateSeries(company)` for a passed-in array; the
   render code is unchanged.
3. **IntersectionObserver for SparkLine reveal** — saves the
   stroke-dashoffset animation on cards that are off-screen.
   Without IO, opening `/companies` with 50 cards would trigger
   50 simultaneous animations (negligible CPU but still wasteful).
4. **Verlet-style force simulation runs 80 iterations on SSR + 10×10
   on hydration** — the SSR pass guarantees the static layout is
   reasonable before JS loads; the hydration ticks smooth it out.
   The simulation stops at 100 iterations total; no rAF loop after
   that. For 13 nodes this is < 1 ms total CPU.
5. **CLS = 0** — every chart container has `aspect-ratio`. The SVG
   uses `viewBox` so it scales without changing the parent's
   reserved space.

## Recipe: adding a new viz

1. **Pick the data**. If it's < 1 kB JSON and SVG-shaped (line, dots,
   small graph), keep going. For real-time streams, scientific
   plots with axes, or > 200 marks, reach for `@observablehq/plot`
   (~15 kB gzipped) instead.
2. **Synthesize first**. Write a `buildSeries(input, params)` that
   produces deterministic data from a seed so SSR === CSR. Use the
   `hash32 + mulberry-style PRNG` pattern in `PhaseTrajectoryChart`
   or `SparkLine` as the template.
3. **SVG with viewBox**. Compute coordinates in a fixed virtual
   space (e.g. 640×220) and let CSS `width: 100%` + `aspect-ratio`
   scale it. Never set absolute pixel `width`/`height` on the SVG.
4. **Reserve space**. Wrap the SVG in a div with `aspectRatio: W/H`
   so the page reserves layout before paint → CLS = 0.
5. **Test ids**. Every interactive element gets `data-testid=`:
   the root, the hover tooltip, the brush rect, etc. The Playwright
   tests in `web/tests/e2e/test_viz_interactions.py` lean on these.
6. **Accessibility**. SVG root gets `role="img"` + `aria-label`.
   Interactive nodes get `role="button"` + `tabIndex={0}` +
   keyboard handlers. Decorative icons get `aria-hidden`.
7. **prefers-reduced-motion**. Wrap any CSS transition in a check
   against the media query result; see `SparkLine`'s `reduceMotion`
   state. Reduced motion = no animation, just final state.
8. **Phase-band consistency**. Use the same threshold (0.33 / 0.66)
   and color tokens (`emerald-500`, `amber-500`, `red-500`) across
   any new viz that surfaces structural-distance. The vocabulary
   of "稳态 / 接近临界 / 临界点上" should always read the same.

## Files

- `web/phase-detector/components/PhaseTrajectoryChart.tsx`
- `web/phase-detector/components/UniversalityAnalogueMap.tsx`
- `web/phase-detector/components/SparkLine.tsx`
- `web/phase-detector/app/company/[ticker]/page.tsx` (integration)
- `web/phase-detector/app/universality/[class_id]/page.tsx` (integration)
- `web/phase-detector/components/CompanyCard.tsx` (integration)
- `web/tests/e2e/test_viz_interactions.py` (e2e)

## Deferred for a follow-up

- Real time-series from BE — needs `/api/company/<t>/trajectory`
  endpoint shipping numeric points. Once present, drop the
  synthesized series and accept points as a prop.
- 13-node guarantee on the analogue map — depends on the YAML
  taxonomy filling evidence_systems + prototypes for every class.
  Currently `mixed_or_unclear` and a few thin classes render with
  4-6 nodes. Acceptable per spec ("13 empirical systems" → "as
  many as the class has, capped at 13").
- Color-blind palette tokens — the phase bands use red/amber/green
  which fail Daltonism. The icon glyphs (`●▲◆✕`) provide
  redundant encoding on badges; we should extend that to the
  trajectory line and sparkline (dashed pattern per band).
