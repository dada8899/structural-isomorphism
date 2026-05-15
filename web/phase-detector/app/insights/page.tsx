// Session #12 W17 experiment — /insights index.
//
// Cross-domain "insight cases" library. Companion to /universality (which
// is taxonomy-first) — this route is case-first: each card is one curated
// pair of domains + what transferred + what didn't + a falsifiable
// 30-90 day prediction the user can run.
//
// Server-rendered (no client JS needed on the index). Each detail page
// is at /insights/[case_id].
//
// This is the path-C MVP from the four-agent feasibility validation in
// session #12: structured case-study library with mechanism mapping and
// public ledger seed, NOT an LLM that tells the user what to do.

import type { Metadata } from "next";
import Link from "next/link";
import { listInsightCases, OUTCOME_BADGE, OUTCOME_LABEL } from "@/lib/insights-data";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "Insight cases · 跨域转移案例库 — Phase Detector",
  description:
    "Curated cross-domain case studies with explicit mechanism mapping, documented historical transfers (succeeded / partial / failed / open), and a 30-90 day falsifiable prediction per case. Honest about where transfer fails. Not advice.",
  path: "/insights",
});

export default function InsightsIndexPage() {
  const cases = listInsightCases();

  // Count outcomes across all cases so the index page surfaces the honest
  // mix up-front rather than letting visitors infer "all green" from
  // selective scrolling.
  const counts = { succeeded: 0, partial: 0, failed: 0, open: 0 };
  for (const c of cases) {
    for (const t of c.documented_transfers) {
      counts[t.outcome] += 1;
    }
  }

  return (
    <article className="mx-auto max-w-5xl">
      <header className="mb-10">
        <p className="mb-2 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
          Insight cases · 跨域转移案例库
        </p>
        <h1
          className="mb-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          Same math, different domain.<br className="hidden sm:inline" />{" "}
          <span className="text-zinc-600">
            What actually transferred — and what didn&apos;t.
          </span>
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-zinc-600 sm:text-base">
          Each case below pairs two domains that share a mathematical
          structure. We show the variable-level mapping, the documented
          historical transfer attempts (with citations), the failure modes,
          and one falsifiable 30-90 day prediction you can run on your own
          system. This is a structured analogy library — <strong>not</strong>{" "}
          a recommendation engine. Where transfer has been tried and failed,
          the failure is shown at the same visual weight as the successes.
        </p>
        <p className="mt-3 max-w-2xl text-xs leading-relaxed text-zinc-500">
          每个案例展示一对共享数学结构的领域：显式变量映射 + 已发表的历史转移尝试（成功/部分/失败/未测）+ 失败边界 + 一个 30-90 天可证伪的预测。本页是结构化类比库，**不是**操作建议。
        </p>

        {/* Honest outcome counter — surfaces the failure / open ratio so
            visitors don't infer "all transfer works" from a cherry-picked
            scroll. */}
        <ul
          className="mt-6 flex flex-wrap gap-2 text-xs"
          aria-label="Outcome mix across all documented transfers in the library"
        >
          <li className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.succeeded}`}>
            <span className="font-semibold tabular-nums">{counts.succeeded}</span>
            <span>{OUTCOME_LABEL.succeeded}</span>
          </li>
          <li className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.partial}`}>
            <span className="font-semibold tabular-nums">{counts.partial}</span>
            <span>{OUTCOME_LABEL.partial}</span>
          </li>
          <li className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.failed}`}>
            <span className="font-semibold tabular-nums">{counts.failed}</span>
            <span>{OUTCOME_LABEL.failed}</span>
          </li>
          <li className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.open}`}>
            <span className="font-semibold tabular-nums">{counts.open}</span>
            <span>{OUTCOME_LABEL.open}</span>
          </li>
        </ul>
      </header>

      <section
        aria-labelledby="cases-heading"
        className="mb-12 space-y-4"
        data-testid="insight-cases-grid"
      >
        <h2 id="cases-heading" className="sr-only">
          Case library
        </h2>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {cases.map((c) => {
            const transferMix = c.documented_transfers.reduce(
              (acc, t) => {
                acc[t.outcome] += 1;
                return acc;
              },
              { succeeded: 0, partial: 0, failed: 0, open: 0 },
            );
            return (
              <li key={c.id}>
                <Link
                  href={`/insights/${c.id}`}
                  data-testid="insight-case-card"
                  data-case-id={c.id}
                  className="group flex h-full flex-col gap-3 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm transition hover:border-zinc-300 hover:shadow-md"
                >
                  <header>
                    <p className="mb-1 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
                      {c.universality_class_name}
                    </p>
                    <h3
                      className="text-base font-semibold leading-snug tracking-tight text-zinc-900 group-hover:text-zinc-700"
                      style={{ fontFamily: "'Noto Serif SC', serif" }}
                    >
                      {c.domains.a}
                      <br />
                      <span className="text-zinc-500">↕</span>
                      <br />
                      {c.domains.b}
                    </h3>
                  </header>

                  <p className="line-clamp-3 text-xs leading-relaxed text-zinc-600">
                    {c.subtitle}
                  </p>

                  {/* Per-case transfer-outcome mix */}
                  <ul className="mt-auto flex flex-wrap gap-1.5 text-[11px]">
                    {(["succeeded", "partial", "failed", "open"] as const).map(
                      (k) =>
                        transferMix[k] > 0 && (
                          <li
                            key={k}
                            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ring-1 ring-inset ${OUTCOME_BADGE[k]}`}
                          >
                            <span className="font-semibold tabular-nums">
                              {transferMix[k]}
                            </span>
                            <span>{OUTCOME_LABEL[k]}</span>
                          </li>
                        ),
                    )}
                  </ul>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section
        aria-labelledby="method-heading"
        className="mb-16 rounded-xl border border-zinc-200 bg-zinc-50/40 p-5"
      >
        <h2
          id="method-heading"
          className="mb-2 text-base font-semibold text-zinc-900"
        >
          How we author these cases — and what we deliberately don&apos;t do
        </h2>
        <ul className="space-y-1.5 text-sm leading-relaxed text-zinc-700">
          <li>
            <strong className="font-semibold">No LLM-generated prescriptions.</strong>{" "}
            Every &quot;outcome&quot; in a case is sourced from an external
            citation or from this project&apos;s own published result (including
            our own Phase Detector NULL backtest, which appears as a{" "}
            <span className={`mx-0.5 inline-flex items-center rounded px-1.5 py-0.5 text-[10px] ring-1 ring-inset ${OUTCOME_BADGE.failed}`}>
              Failed
            </span>{" "}
            row in the earthquake ↔ DeFi case).
          </li>
          <li>
            <strong className="font-semibold">No &quot;you should do X&quot;.</strong>{" "}
            We show variable mappings and historical outcomes; we don&apos;t
            tell you which intervention to deploy in your domain. The four-
            agent feasibility review (UX / PM / scholar / architect /
            real-user, in <code>docs/sessions/SESSION-12-PRELAUNCH-AUDIT.md</code>) explicitly
            rejected the prescriptive direction.
          </li>
          <li>
            <strong className="font-semibold">Each case includes one falsifiable prediction.</strong>{" "}
            You can test it on your own data in 30-90 days and the result
            goes to a public ledger so the library learns from real-world
            applications instead of confabulating.
          </li>
          <li>
            <strong className="font-semibold">Failures shown at full weight.</strong>{" "}
            Where transfer was attempted and failed in the literature, that
            row is in the same table as the successes — not buried in a
            disclaimer.
          </li>
        </ul>
      </section>
    </article>
  );
}
