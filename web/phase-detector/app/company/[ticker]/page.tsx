"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CPS_BADGE, CPS_LABEL, DYNAMICS_LABEL } from "@/lib/labels";
import { fetchCompany } from "@/lib/api";
import type { Company } from "@/lib/types";

export default function CompanyDetailPage({
  params,
}: {
  params: { ticker: string };
}) {
  const [company, setCompany] = useState<Company | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchCompany(params.ticker)
      .then((c) => {
        if (!cancelled) setCompany(c);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [params.ticker]);

  if (error) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Failed to load {params.ticker}: {error}
        </div>
      </div>
    );
  }

  if (!company) {
    return (
      <div className="space-y-4">
        <BackLink />
        <div className="h-72 animate-pulse rounded-xl border border-gray-200 bg-gray-50" />
      </div>
    );
  }

  const confPct = Math.round(company.confidence * 100);

  return (
    <div className="space-y-6">
      <BackLink />

      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-3xl font-semibold tracking-tight">
            {company.ticker}
          </h1>
          <span className="text-base text-gray-500">{company.name}</span>
          {company.sector && (
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
              {company.sector}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`rounded-full px-2.5 py-1 text-xs font-medium ${CPS_BADGE[company.critical_point_state]}`}
          >
            {CPS_LABEL[company.critical_point_state]}
          </span>
          <span className="text-sm text-gray-600">
            {DYNAMICS_LABEL[company.dynamics_family] ?? company.dynamics_family}
          </span>
          {company.updated_at && (
            <span className="text-xs text-gray-400">
              Updated {company.updated_at}
            </span>
          )}
        </div>
      </header>

      <section className="rounded-xl border border-gray-200 bg-white p-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
          30-second TL;DR
        </h2>
        <p className="text-base leading-relaxed text-gray-800">{company.tldr}</p>
      </section>

      <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Primary indicators
          </h2>
          {company.primary_indicators?.length ? (
            <ul className="space-y-2">
              {company.primary_indicators.map((ind, i) => (
                <li
                  key={`${ind.name}-${i}`}
                  className="flex items-baseline justify-between gap-4 border-b border-gray-100 pb-2 last:border-0 last:pb-0"
                >
                  <span className="text-sm text-gray-700">{ind.name}</span>
                  <span className="text-sm font-medium tabular-nums text-gray-900">
                    {typeof ind.value === "number"
                      ? ind.value.toLocaleString()
                      : ind.value}
                    {ind.unit ? (
                      <span className="ml-0.5 text-gray-500">{ind.unit}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No indicators reported.</p>
          )}
        </div>

        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Confidence
          </h2>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-3xl font-semibold tabular-nums text-gray-900">
              {confPct}%
            </span>
            <span className="text-xs text-gray-500">model self-reported</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
            <div
              className="h-full rounded-full bg-gray-900 transition-all"
              style={{ width: `${confPct}%` }}
            />
          </div>

          {company.caveats && company.caveats.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Caveats
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-gray-600">
                {company.caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {company.raw_response && (
        <section className="rounded-xl border border-gray-200 bg-white p-6">
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-xs font-medium text-gray-500 underline-offset-2 hover:text-gray-800 hover:underline"
          >
            {showRaw ? "Hide raw response" : "Show raw response"}
          </button>
          {showRaw && (
            <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-gray-50 p-3 text-xs text-gray-700">
              {JSON.stringify(company.raw_response, null, 2)}
            </pre>
          )}
        </section>
      )}
    </div>
  );
}

function BackLink() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900"
    >
      <span aria-hidden>←</span> Back to screener
    </Link>
  );
}
