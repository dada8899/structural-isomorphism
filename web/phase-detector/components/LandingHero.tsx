// W10-C alpha-screener landing: editorial hero.
//
// Server component — hero text is in initial HTML for instant LCP. No client
// JS in this file. The animated phase indicator is a sibling client island.
//
// Design intent (per CLAUDE.md Linear/Apple/Bear tier):
//   - Headline: Noto Serif SC, ~52px desktop / ~36px mobile, near-black
//   - Subhead: Inter, ~18px, zinc-600
//   - CTAs: primary indigo solid, secondary outline anchor
//   - No hero image. Phase indicator below CTAs supplies visual rhythm.
//   - White background; max 3 colors (indigo accent + emerald success + zinc neutrals).
//   - Generous whitespace: 96px section padding desktop.

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
            className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500"
          />
          Research preview · 研究预览
        </p>

        <h1
          id="hero-headline"
          data-testid="hero-headline"
          className="max-w-4xl text-balance text-[40px] font-semibold leading-[1.08] tracking-tight text-zinc-900 sm:text-[56px] lg:text-[64px]"
          style={{
            fontFamily: "var(--font-serif), 'Noto Serif SC', 'Charter', 'Times New Roman', serif",
          }}
        >
          Daily structural signals from <span className="text-indigo-700">1000+</span> public companies.
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600 sm:text-xl">
          Each one a hypothesis. Each one with the receipts.
          <br className="hidden sm:inline" /> <span className="text-zinc-900">You judge the alpha.</span>
        </p>

        <p className="mt-3 max-w-2xl text-base leading-relaxed text-zinc-500">
          1000+ 家上市公司，每日结构信号。每条都附凭证。alpha 你自己看，我们不替你下结论。
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-3" data-testid="hero-ctas">
          <Link
            href="/companies"
            data-testid="cta-primary"
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            <HeroCtaText fallback="Browse signals" />
            <span aria-hidden="true">→</span>
          </Link>
          <Link
            href="#how-it-works"
            data-testid="cta-secondary"
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-5 py-3 text-sm font-semibold text-zinc-800 transition hover:border-zinc-400 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            How it works
          </Link>
          <Link
            href="/backtest"
            className="inline-flex items-center gap-1 px-2 py-3 text-sm font-medium text-zinc-600 underline-offset-4 hover:text-zinc-900 hover:underline"
          >
            v0.1 NULL backtest →
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
