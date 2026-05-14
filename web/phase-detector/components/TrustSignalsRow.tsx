// W10-C alpha-screener landing: trust signals row.
//
// Three quantitative + verifiable claims. Each links to the source so the
// claim is auditable, not marketing fluff. This is the section that
// converts "interesting" → "credible" for someone evaluating an alpha
// product.

import Link from "next/link";

interface Signal {
  label: string;
  value: string;
  href: string;
  hint?: string;
}

// Backtest delta is sourced from /backtest page (W10-A). We currently
// publish the NULL result honestly (p=0.681, alpha not significant). When
// W10-A ships the v0.2 Sharpe lift this value swaps in via env.
const BACKTEST_HEADLINE =
  process.env.NEXT_PUBLIC_BACKTEST_HEADLINE ??
  "v0.1 backtest: p=0.681 (NULL, published)";

const SIGNALS: Signal[] = [
  {
    label: "Cross-domain validation",
    value: "13 systems · Clauset-grade",
    href: "https://github.com/dada8899/structural-isomorphism/blob/main/PREPRINT.md",
    hint: "Earthquakes, bank runs, neural avalanches, wildfires, grid cascades.",
  },
  {
    label: "Honest backtest",
    value: BACKTEST_HEADLINE,
    href: "/backtest",
    hint: "Walk-forward. 500 tickers × 5 years. We publish even when alpha = 0.",
  },
  {
    label: "Open methodology",
    value: "Frozen pipeline · public code",
    href: "/methodology",
    hint: "Code, prompts, calibration data — all on GitHub.",
  },
];

export function TrustSignalsRow() {
  return (
    <section
      aria-labelledby="trust-signals-heading"
      className="border-y border-zinc-200 bg-zinc-50/40"
    >
      <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-20">
        <h2
          id="trust-signals-heading"
          className="sr-only"
        >
          Trust signals
        </h2>
        <div className="mb-10 max-w-2xl">
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Receipts · 凭证
          </p>
          <p
            className="text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl"
            style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
          >
            每一条信号都附带来源。<br className="hidden sm:inline" />你判断 alpha，我们不替你下结论。
          </p>
        </div>
        <ul className="grid grid-cols-1 gap-px overflow-hidden rounded-2xl border border-zinc-200 bg-zinc-200 sm:grid-cols-3">
          {SIGNALS.map((s) => {
            const isInternal = s.href.startsWith("/");
            const inner = (
              <div className="flex h-full flex-col justify-between bg-white p-6 transition-colors hover:bg-indigo-50/40 sm:p-7">
                <div>
                  <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                    {s.label}
                  </div>
                  <div className="mt-2 text-lg font-semibold leading-snug text-zinc-900">
                    {s.value}
                  </div>
                </div>
                {s.hint && (
                  <p className="mt-4 text-sm leading-relaxed text-zinc-600">
                    {s.hint}
                  </p>
                )}
                <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-indigo-700">
                  查看来源 <span aria-hidden="true">→</span>
                </div>
              </div>
            );
            return (
              <li key={s.label} className="h-full">
                {isInternal ? (
                  <Link href={s.href} className="block h-full">
                    {inner}
                  </Link>
                ) : (
                  <a
                    href={s.href}
                    target="_blank"
                    rel="noopener"
                    className="block h-full"
                  >
                    {inner}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
