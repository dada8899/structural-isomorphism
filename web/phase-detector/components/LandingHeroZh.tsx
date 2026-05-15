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
            className="inline-block h-1.5 w-1.5 rounded-full bg-indigo-500 motion-safe:animate-pulse"
          />
          跨域普适性 · 研究预览
        </p>

        <h1
          id="hero-headline"
          data-testid="hero-headline"
          className="max-w-4xl text-balance text-[40px] font-semibold leading-[1.08] tracking-tight text-zinc-900 sm:text-[52px] lg:text-[56px]"
          style={{
            fontFamily: "var(--font-serif), 'Noto Serif SC', 'Charter', 'Times New Roman', serif",
          }}
        >
          同一套数学，从地震延伸到 <span className="text-indigo-700">1000+ 家上市公司</span>。
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-relaxed text-zinc-600 sm:text-xl">
          一个跨域普适性分类器，每天对上市公司打相位标签。
          <br className="hidden sm:inline" />{" "}
          <span className="text-zinc-900">
            v0.1 回测零结果（Sharpe lift −0.07，p = 0.57），公开发表。
          </span>
        </p>

        <p className="mt-3 max-w-2xl text-base leading-relaxed text-zinc-500">
          Same math, applied to listed equities. v0.1 backtest is NULL (p = 0.57), published openly. Research preview, not investment advice.
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
            href="/methodology"
            data-testid="cta-secondary"
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-300 bg-white px-5 py-3 text-sm font-semibold text-zinc-800 transition hover:border-zinc-400 hover:bg-zinc-50 focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:ring-offset-2"
          >
            阅读方法论
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
