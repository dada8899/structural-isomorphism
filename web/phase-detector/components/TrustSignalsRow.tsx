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

// Backtest headline mirrors web/phase-detector/public/backtest/result.json:
//   sharpe_lift = -0.072, t_stat = 0.573, p_value = 0.569 (Welch t-test,
//   near_critical_llm cohort vs equal-weight benchmark, n_months=59).
// When W10-A v0.2 ships an updated number, edit the value below + the
// /backtest page metadata in the same PR — both must agree.

const SIGNALS: Signal[] = [
  {
    label: "Within-class robustness",
    value: "13 systems · Clauset-grade",
    href: "https://github.com/dada8899/structural-isomorphism/blob/main/paper/anti-phacking-unified-2026-05-15.md",
    hint: "Earthquakes, bank runs, neural avalanches, wildfires, grid cascades — all within the SOC universality class.",
  },
  {
    label: "Honest backtest",
    value: "Sharpe lift −0.07, p = 0.57 (NULL, published)",
    href: "/backtest",
    hint: "Walk-forward, 927 / 1000 tickers covered, 59 monthly snapshots over 2020–2025. We publish even when alpha = 0.",
  },
  {
    label: "Open methodology",
    value: "Frozen 339-LOC pipeline · public code",
    href: "/methodology",
    hint: "Code, prompts, pre-registered exponent bands — all on GitHub. MIT + CC-BY-4.0.",
  },
];

export function TrustSignalsRow() {
  return (
    <section
      aria-labelledby="trust-signals-heading"
      className="border-y border-zinc-200 bg-zinc-50/40"
    >
      <div className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-20">
        <div className="mb-10 max-w-2xl">
          <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Verifiable claims · 凭证
          </p>
          <h2
            id="trust-signals-heading"
            className="text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl"
            style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
          >
            Every claim links to its source.<br className="hidden sm:inline" />{" "}
            <span className="text-zinc-600">每条信号都附带来源，你自己判断。</span>
          </h2>
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
