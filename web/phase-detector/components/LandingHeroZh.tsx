// W11-B i18n: Chinese-version landing hero (/zh route).
//
// Mirror of LandingHero.tsx — same structure, fully translated copy. Hero
// headline switches Noto Serif SC to be the primary serif (CN audience).
// CTAs link to canonical EN routes (/companies, /backtest) — no per-locale
// routing for sub-pages yet (Phase 2).

import Link from "next/link";
import { PhaseIndicatorAnimation } from "./PhaseIndicatorAnimation";

export function LandingHeroZh() {
  return (
    <section
      aria-labelledby="hero-headline"
      className="relative overflow-hidden bg-white"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_85%_-10%,_rgba(91,33,182,0.06),_transparent_60%)]"
      />
      <div className="relative mx-auto w-full max-w-5xl px-6 pb-16 pt-16 sm:pb-24 sm:pt-24 lg:pt-32">
        <p
          className="mb-6 inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700"
          data-testid="hero-eyebrow"
        >
          <span
            aria-hidden="true"
            className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-500"
          />
          研究预览 · Research preview
        </p>

        <h1
          id="hero-headline"
          data-testid="hero-headline"
          className="max-w-4xl text-balance text-[40px] font-semibold leading-[1.08] tracking-tight text-zinc-900 sm:text-[56px] lg:text-[64px]"
          style={{
            fontFamily: "var(--font-serif), 'Noto Serif SC', 'Charter', 'Times New Roman', serif",
          }}
        >
          每日 <span className="text-indigo-700">1000+</span> 家上市公司的结构性信号。
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600 sm:text-xl">
          每条都是一个假设。每条都附带证据。
          <br className="hidden sm:inline" /> <span className="text-zinc-900">alpha 是否成立，由你判断。</span>
        </p>

        <p className="mt-3 max-w-2xl text-base leading-relaxed text-zinc-500">
          Daily structural signals from 1000+ public companies. Each one a hypothesis. Each one with the receipts.
        </p>

        <div className="mt-10 flex flex-wrap items-center gap-3" data-testid="hero-ctas">
          <Link
            href="/companies"
            data-testid="cta-primary"
            className="inline-flex items-center gap-2 rounded-lg bg-indigo-700 px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-800 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            浏览公司表
            <span aria-hidden="true">→</span>
          </Link>
          <Link
            href="#how-it-works"
            data-testid="cta-secondary"
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-5 py-3 text-sm font-semibold text-zinc-800 transition hover:border-zinc-400 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            工作原理
          </Link>
          <Link
            href="/backtest"
            className="inline-flex items-center gap-1 px-2 py-3 text-sm font-medium text-zinc-600 underline-offset-4 hover:text-zinc-900 hover:underline"
          >
            v0.1 NULL 回测 →
          </Link>
        </div>

        <div className="mt-14 hidden border-t border-zinc-100 pt-10 sm:block">
          <p className="mb-5 text-center text-[11px] uppercase tracking-[0.18em] text-zinc-400">
            五种状态 · Five phases
          </p>
          <PhaseIndicatorAnimation />
        </div>
      </div>
    </section>
  );
}
