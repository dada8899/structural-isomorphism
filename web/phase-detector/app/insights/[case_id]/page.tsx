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
  getInsightCase,
  listInsightCases,
  OUTCOME_BADGE,
  OUTCOME_LABEL,
  type TransferOutcome,
} from "@/lib/insights-data";
import { buildMetadata } from "@/lib/seo";

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

        {/* Transfer-outcome mix */}
        <div className="mt-5">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wider text-zinc-500">
            Historical transfer record (this case)
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
      </header>

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
