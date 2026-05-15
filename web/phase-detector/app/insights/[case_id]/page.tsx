// Session #12 W17 experiment — /insights/[case_id] detail page.
//
// Each case study renders five blocks in this order:
//   1. Header — domain pair, universality class, shared equation
//   2. Variable mapping table — explicit "yours ↔ analogue" rows
//   3. Documented transfers table — succeeded / partial / failed / open
//      with citations; failures shown at the same weight as successes
//   4. Blocking mechanisms — boundary conditions where transfer breaks
//   5. Falsifiable micro-prediction — what to test in 30-90 days
//
// Each block has an explicit scope-statement footer so a cold visitor
// can't infer "this is advice".

import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  CONFIDENCE_BADGE,
  CONFIDENCE_LABEL,
  getInsightCase,
  listInsightCases,
  OUTCOME_BADGE,
  OUTCOME_LABEL,
  type TransferOutcome,
} from "@/lib/insights-data";
import { buildMetadata } from "@/lib/seo";
import ledgerCounts from "@/data/transfer-ledger-counts.json";

interface LedgerSnapshot {
  _meta?: {
    schema_version?: number;
    generated_at?: string | null;
    total_issues_inspected?: number;
    source?: string;
  };
  counts_by_case: Record<
    string,
    { pass: number; fail: number; inconclusive: number; total: number }
  >;
}

const LEDGER = ledgerCounts as LedgerSnapshot;

interface PageProps {
  params: { case_id: string };
}

export function generateStaticParams() {
  return listInsightCases().map((c) => ({ case_id: c.id }));
}

export function generateMetadata({ params }: PageProps): Metadata {
  const c = getInsightCase(params.case_id);
  if (!c) {
    return buildMetadata({
      title: "Insight case not found",
      description: "This insight case does not exist.",
      path: `/insights/${params.case_id}`,
    });
  }
  return buildMetadata({
    title: `${c.domains.a} ↔ ${c.domains.b} — Insight case`,
    description: c.subtitle,
    path: `/insights/${c.id}`,
  });
}

function OutcomeBadge({ outcome }: { outcome: TransferOutcome }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${OUTCOME_BADGE[outcome]}`}
    >
      {OUTCOME_LABEL[outcome]}
    </span>
  );
}

export default function InsightCaseDetailPage({ params }: PageProps) {
  const c = getInsightCase(params.case_id);
  if (!c) notFound();

  const transferMix = c.documented_transfers.reduce(
    (acc, t) => {
      acc[t.outcome] += 1;
      return acc;
    },
    { succeeded: 0, partial: 0, failed: 0, open: 0 } as Record<TransferOutcome, number>,
  );

  return (
    <article className="mx-auto max-w-4xl space-y-10">
      <nav aria-label="Breadcrumb" className="text-xs text-zinc-500">
        <Link href="/insights" className="hover:text-zinc-900">
          ← All insight cases
        </Link>
      </nav>

      {/* 1. HEADER */}
      <header>
        <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
          Insight case · {c.universality_class_name}
        </p>
        <h1
          className="mb-3 text-3xl font-semibold leading-tight tracking-tight text-zinc-900 sm:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          {c.title}
        </h1>
        <p className="max-w-prose text-sm leading-relaxed text-zinc-600 sm:text-base">
          {c.subtitle}
        </p>

        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div className="rounded-lg border border-zinc-200 bg-white p-4">
            <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              Domain A
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900">
              {c.domains.a}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 bg-white p-4">
            <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              Domain B
            </p>
            <p className="mt-1 text-sm font-medium text-zinc-900">
              {c.domains.b}
            </p>
          </div>
        </div>

        <div className="mt-5 rounded-lg border border-zinc-200 bg-zinc-50/60 p-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            Shared mathematical structure
          </p>
          <p className="mt-1 font-mono text-xs leading-relaxed text-zinc-800 sm:text-sm">
            {c.shared_equation}
          </p>
          <Link
            href={`/universality/${c.universality_class_id}`}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:text-indigo-900"
          >
            Class detail · {c.universality_class_name} →
          </Link>
        </div>

        {/* Transfer-outcome mix — curated literature + user-reported */}
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              Curated literature record
            </p>
            <ul className="flex flex-wrap gap-2 text-xs">
              {(["succeeded", "partial", "failed", "open"] as const).map(
                (k) =>
                  transferMix[k] > 0 && (
                    <li
                      key={k}
                      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE[k]}`}
                    >
                      <span className="font-semibold tabular-nums">
                        {transferMix[k]}
                      </span>
                      <span>{OUTCOME_LABEL[k]}</span>
                    </li>
                  ),
              )}
            </ul>
          </div>
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
              User-reported transfer ledger
            </p>
            {(() => {
              const ledger = LEDGER.counts_by_case[c.id];
              if (!ledger || ledger.total === 0) {
                return (
                  <p className="text-xs leading-relaxed text-zinc-500">
                    No user reports yet.{" "}
                    <a
                      href={`https://github.com/dada8899/structural-isomorphism/issues/new?labels=transfer-ledger&template=transfer-ledger.md&title=%5Btransfer-ledger%5D+${c.id}%3A+%3Cpass%7Cfail%7Cinconclusive%3E`}
                      target="_blank"
                      rel="noopener"
                      className="font-medium text-indigo-700 underline underline-offset-2 hover:text-indigo-900"
                    >
                      Be the first to submit one →
                    </a>
                  </p>
                );
              }
              return (
                <>
                  <ul className="flex flex-wrap gap-2 text-xs">
                    <li
                      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.succeeded}`}
                    >
                      <span className="font-semibold tabular-nums">
                        {ledger.pass}
                      </span>
                      <span>Passed</span>
                    </li>
                    <li
                      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.partial}`}
                    >
                      <span className="font-semibold tabular-nums">
                        {ledger.inconclusive}
                      </span>
                      <span>Inconclusive</span>
                    </li>
                    <li
                      className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 ring-1 ring-inset ${OUTCOME_BADGE.failed}`}
                    >
                      <span className="font-semibold tabular-nums">
                        {ledger.fail}
                      </span>
                      <span>Failed</span>
                    </li>
                  </ul>
                  <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
                    {ledger.total} report{ledger.total > 1 ? "s" : ""} ·{" "}
                    <a
                      href={`https://github.com/dada8899/structural-isomorphism/issues?q=is%3Aissue+label%3Atransfer-ledger+${c.id}`}
                      target="_blank"
                      rel="noopener"
                      className="text-indigo-700 underline underline-offset-2 hover:text-indigo-900"
                    >
                      view on GitHub
                    </a>
                    {" · "}
                    <a
                      href={`https://github.com/dada8899/structural-isomorphism/issues/new?labels=transfer-ledger&template=transfer-ledger.md&title=%5Btransfer-ledger%5D+${c.id}%3A+%3Cpass%7Cfail%7Cinconclusive%3E`}
                      target="_blank"
                      rel="noopener"
                      className="text-indigo-700 underline underline-offset-2 hover:text-indigo-900"
                    >
                      submit yours
                    </a>
                  </p>
                </>
              );
            })()}
          </div>
        </div>
      </header>

      {/* SYNTHESIS — the answer-shaped block. Session #12 W17 added this
          after a user pointed out that surfacing only analogies + a 30-day
          test felt like deliver-homework, not deliver-value. */}
      <section
        aria-labelledby="synthesis-heading"
        className="space-y-4 rounded-2xl border-2 border-indigo-300 bg-gradient-to-br from-indigo-50/70 via-white to-white p-6 shadow-sm sm:p-8"
        data-testid="case-synthesis"
      >
        <header className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-indigo-700">
              Best current converging answer
            </p>
            <span
              className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${CONFIDENCE_BADGE[c.synthesis.confidence]}`}
              data-testid="synthesis-confidence"
            >
              {CONFIDENCE_LABEL[c.synthesis.confidence]}
            </span>
          </div>
          <h2
            id="synthesis-heading"
            className="text-lg font-semibold leading-snug text-zinc-900 sm:text-xl"
            style={{ fontFamily: "'Noto Serif SC', serif" }}
          >
            {c.synthesis.best_current_answer}
          </h2>
        </header>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-lg bg-white/70 p-4 ring-1 ring-zinc-200">
            <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-600">
              Why this answer
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-zinc-700">
              {c.synthesis.why_this_answer}
            </p>
          </div>
          <div className="rounded-lg bg-amber-50/60 p-4 ring-1 ring-amber-200">
            <p className="text-[11px] font-medium uppercase tracking-wider text-amber-800">
              Strongest objection (read this)
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-amber-900">
              {c.synthesis.strongest_objection}
            </p>
          </div>
        </div>

        <div className="rounded-lg border border-zinc-200 bg-white/70 p-4">
          <p className="text-[11px] font-medium uppercase tracking-wider text-zinc-600">
            14-day check (before you commit to acting on this)
          </p>
          <p className="mt-1.5 text-sm leading-relaxed text-zinc-700">
            {c.synthesis.short_falsification}
          </p>
        </div>

        {c.synthesis.do_not_apply_when && c.synthesis.do_not_apply_when.length > 0 && (
          <div className="rounded-lg border border-rose-200 bg-rose-50/40 p-4">
            <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-rose-800">
              Do NOT apply this answer when…
            </p>
            <ul className="space-y-1 text-sm leading-relaxed text-rose-900">
              {c.synthesis.do_not_apply_when.map((d, i) => (
                <li key={i} className="flex gap-2">
                  <span aria-hidden="true" className="select-none">×</span>
                  <span>{d}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="border-t border-zinc-200 pt-3 text-xs leading-relaxed text-zinc-500">
          This block is hand-authored from the evidence shown below — no
          LLM in the path. The mapping, documented transfers, blocking
          mechanisms, and falsifiable prediction are all auditable below.
          The confidence badge reflects how strongly the evidence supports
          this specific answer, not the broader analogy.
        </p>
      </section>

      {/* 2. VARIABLE MAPPING */}
      <section aria-labelledby="mapping-heading" className="space-y-3">
        <header>
          <h2
            id="mapping-heading"
            className="text-xl font-semibold tracking-tight text-zinc-900"
          >
            1. Variable-level mapping
          </h2>
          <p className="text-xs text-zinc-500">
            Explicit correspondence between concepts in your domain (A) and
            the analogue domain (B). The <em>note</em> column flags where
            the mapping is rank-reductive or otherwise lossy.
          </p>
        </header>
        <div className="overflow-x-auto rounded-lg border border-zinc-200">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 text-left text-[11px] uppercase tracking-wider text-zinc-500">
              <tr>
                <th className="px-4 py-2 font-medium">In your domain (A)</th>
                <th className="px-4 py-2 font-medium">In the analogue (B)</th>
                <th className="px-4 py-2 font-medium">Caveat</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white">
              {c.variable_mapping.map((m, i) => (
                <tr key={i} className="align-top">
                  <td className="px-4 py-3 text-zinc-900">{m.yours}</td>
                  <td className="px-4 py-3 text-zinc-900">{m.analogue}</td>
                  <td className="px-4 py-3 text-xs text-zinc-600">
                    {m.note ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* 3. DOCUMENTED TRANSFERS */}
      <section aria-labelledby="transfers-heading" className="space-y-3">
        <header>
          <h2
            id="transfers-heading"
            className="text-xl font-semibold tracking-tight text-zinc-900"
          >
            2. Documented transfer attempts
          </h2>
          <p className="text-xs text-zinc-500">
            Every row below has a citation. Failures are shown at the same
            visual weight as successes — that is deliberate.
          </p>
        </header>
        <ul className="space-y-3">
          {c.documented_transfers.map((t, i) => (
            <li
              key={i}
              className="rounded-lg border border-zinc-200 bg-white p-4"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <OutcomeBadge outcome={t.outcome} />
                <span className="text-xs text-zinc-500">{t.direction}</span>
              </div>
              <p className="mb-1.5 text-sm font-medium text-zinc-900">
                Intervention: {t.intervention}
              </p>
              <p className="mb-2 text-sm leading-relaxed text-zinc-700">
                {t.evidence}
              </p>
              <p className="text-xs text-zinc-500">
                Source:{" "}
                {t.url ? (
                  <a
                    href={t.url}
                    target="_blank"
                    rel="noopener"
                    className="text-indigo-700 underline underline-offset-2 hover:text-indigo-900"
                  >
                    {t.citation}
                  </a>
                ) : (
                  t.citation
                )}
              </p>
            </li>
          ))}
        </ul>
      </section>

      {/* 4. BLOCKING MECHANISMS */}
      <section aria-labelledby="blocking-heading" className="space-y-3">
        <header>
          <h2
            id="blocking-heading"
            className="text-xl font-semibold tracking-tight text-zinc-900"
          >
            3. Where transfer can break
          </h2>
          <p className="text-xs text-zinc-500">
            Boundary conditions and mechanism differences that have caused
            this analogy to misfire in published work. Read before
            attempting transfer.
          </p>
        </header>
        <ul className="space-y-2 rounded-lg border border-amber-200 bg-amber-50/40 p-4 text-sm leading-relaxed text-amber-900">
          {c.blocking_mechanisms.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span aria-hidden="true" className="select-none">·</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* 5. FALSIFIABLE PREDICTION */}
      <section aria-labelledby="prediction-heading" className="space-y-3">
        <header>
          <h2
            id="prediction-heading"
            className="text-xl font-semibold tracking-tight text-zinc-900"
          >
            4. A falsifiable {c.falsifiable_prediction.timeframe_days}-day prediction
          </h2>
          <p className="text-xs text-zinc-500">
            Instead of advice, the case offers one prediction you can
            check on your own data. The result — pass or fail — is what
            tells you whether the analogy holds in your specific system.
          </p>
        </header>
        <div className="space-y-3 rounded-lg border border-indigo-200 bg-indigo-50/30 p-5">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-indigo-700">
              If
            </p>
            <p className="mt-1 text-sm leading-relaxed text-zinc-900">
              {c.falsifiable_prediction.if_condition}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-indigo-700">
              Then expect (within {c.falsifiable_prediction.timeframe_days} days)
            </p>
            <p className="mt-1 text-sm leading-relaxed text-zinc-900">
              {c.falsifiable_prediction.then_observation}
            </p>
          </div>
          <div>
            <p className="text-[11px] font-medium uppercase tracking-wider text-indigo-700">
              How to test
            </p>
            <p className="mt-1 text-sm leading-relaxed text-zinc-700">
              {c.falsifiable_prediction.how_to_test}
            </p>
          </div>
          <p className="border-t border-indigo-200 pt-3 text-xs leading-relaxed text-zinc-600">
            The public-ledger submission endpoint is{" "}
            <em>not yet live</em> — for now, results can be reported by
            opening an issue at{" "}
            <a
              href="https://github.com/dada8899/structural-isomorphism/issues/new?labels=transfer-ledger&template=transfer-ledger.md"
              target="_blank"
              rel="noopener"
              className="font-medium text-indigo-700 underline underline-offset-2 hover:text-indigo-900"
            >
              github.com/dada8899/structural-isomorphism/issues
            </a>
            . When enough reports accumulate, this case&apos;s success-rate
            history will be displayed inline.
          </p>
        </div>
      </section>

      {/* SCOPE STATEMENT — always shown, never collapsed */}
      <section
        aria-labelledby="scope-heading"
        className="rounded-lg border border-zinc-300 bg-zinc-100/60 p-4"
      >
        <h2
          id="scope-heading"
          className="mb-1 text-sm font-semibold text-zinc-900"
        >
          Scope statement
        </h2>
        <p className="text-sm leading-relaxed text-zinc-700">
          {c.scope_statement}
        </p>
        <p className="mt-2 text-xs leading-relaxed text-zinc-500">
          Sourced from SIBD-63 seed{c.sibd_seed_ids.length > 1 ? "s" : ""}:{" "}
          {c.sibd_seed_ids.join(", ")} · Last human review:{" "}
          {c.last_human_review} · This page does not constitute investment,
          medical, legal, or operational advice.
        </p>
      </section>
    </article>
  );
}
