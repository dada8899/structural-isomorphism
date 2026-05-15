// Landing hero — editorial, Linear/Apple/Bear tier.
//
// Server component — hero text is in initial HTML for instant LCP. No client
// JS in this file. The animated phase indicator is a sibling client island.
//
// Session #12 (W16 audit): re-framed away from "Daily structural signals"
// (which scanned as alpha-screener) to "Same math as earthquakes, applied
// to public companies" + NULL backtest stated in the subhead. Tertiary
// "v0.1 NULL backtest" link removed from the CTA row because the NULL
// number now lives in the subhead and in the TrustSignalsRow.
//
// Design intent:
//   - Headline: Noto Serif SC, 40px mobile → 52-56px desktop, near-black
//   - Subhead: Inter, ~18-20px, zinc-600 with NULL stat highlighted
//   - CTAs: primary indigo solid (Explore companies), secondary outline
//     (Read the methodology) — exactly two
//   - Phase indicator below CTAs supplies visual rhythm; no hero image
//   - White background; max 3 colors (indigo accent + emerald + zinc)
//   - Generous whitespace: 96px section padding desktop

import Link from "next/link";
import { PhaseIndicatorAnimation } from "./PhaseIndicatorAnimation";
// W15-E: A/B experiment on primary CTA text. Client island; fallback ensures
// no hydration mismatch (server renders "Browse signals", client may swap
// to "See live data" for treatment-bucket users).
import { HeroCtaText } from "./HeroCtaText";

export function LandingHero() {
  return (
    <section
      aria-labelledby="hero-headline"
      className="relative overflow-hidden bg-white"
    >
      {/* Subtle gradient corner — single-color radial, no busy textures. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_85%_-10%,_rgba(91,33,182,0.06),_transparent_60%)]"
      />
      <div className="relative mx-auto w-full max-w-5xl px-6 pb-16 pt-16 sm:pb-24 sm:pt-24 lg:pt-32">
        {/* Eyebrow */}
        <p
          className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
          data-testid="hero-eyebrow"
        >
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-500 motion-safe:animate-pulse"
          />
          Cross-domain universality · Research preview
        </p>

        <h1
          id="hero-headline"
          data-testid="hero-headline"
          className="max-w-4xl text-balance text-[40px] font-semibold leading-[1.08] tracking-tight text-zinc-900 sm:text-[52px] lg:text-[56px]"
          style={{
            fontFamily: "var(--font-serif), 'Noto Serif SC', 'Charter', 'Times New Roman', serif",
          }}
        >
          The same math that explains earthquakes,{" "}
          <span className="text-indigo-700">applied to 1000+ public companies.</span>
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600 sm:text-xl">
          A cross-domain universality classifier, applied daily to listed equities.
          <br className="hidden sm:inline" />{" "}
          <span className="text-zinc-900">
            v0.1 backtest is NULL (Sharpe lift −0.07, p = 0.57) — published openly.
          </span>
        </p>

        <p className="mt-3 max-w-2xl text-base leading-relaxed text-zinc-500">
          同一套数学解释过地震、银行挤兑、电网级联——现在用来给上市公司打相位标签。Backtest 零结果，公开发表。研究预览，非投资建议。
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-3" data-testid="hero-ctas">
          <Link
            href="/companies"
            data-testid="cta-primary"
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            <HeroCtaText fallback="Explore companies" />
            <span aria-hidden="true">→</span>
          </Link>
          <Link
            href="/methodology"
            data-testid="cta-secondary"
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-5 py-3 text-sm font-semibold text-zinc-800 transition hover:border-zinc-400 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            Read the methodology
          </Link>
        </div>

        {/* Phase indicator visualization — CSS-only, hidden on tiny mobiles. */}
        <div className="mt-14 hidden border-t border-zinc-100 pt-10 sm:block">
          <p className="mb-5 text-center text-[11px] uppercase tracking-[0.18em] text-zinc-400">
            Five phases · 五种状态
          </p>
          <PhaseIndicatorAnimation />
        </div>
      </div>
    </section>
  );
}
