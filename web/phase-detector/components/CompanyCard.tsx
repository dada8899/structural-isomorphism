"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CPS_BADGE,
  CPS_LABEL,
  DYNAMICS_LABEL,
} from "@/lib/labels";
import type { Company } from "@/lib/types";

export function CompanyCard({ company }: { company: Company }) {
  const [showCaveats, setShowCaveats] = useState(false);
  const confPct = Math.round(company.confidence * 100);

  return (
    <article className="flex flex-col gap-4 rounded-xl border border-gray-200 bg-white p-5 transition hover:border-gray-300 hover:shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h3 className="truncate text-lg font-semibold tracking-tight">
              {company.ticker}
            </h3>
            <span className="truncate text-sm text-gray-500">{company.name}</span>
          </div>
          {company.sector && (
            <span className="mt-1 inline-block rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
              {company.sector}
            </span>
          )}
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${CPS_BADGE[company.critical_point_state]}`}
          title={CPS_LABEL[company.critical_point_state]}
        >
          {CPS_LABEL[company.critical_point_state]}
        </span>
      </header>

      <div className="text-xs text-gray-500">
        <span className="font-medium text-gray-700">
          {DYNAMICS_LABEL[company.dynamics_family] ?? company.dynamics_family}
        </span>
      </div>

      <p className="text-sm leading-relaxed text-gray-700">{company.tldr}</p>

      {company.primary_indicators?.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Primary indicators
          </div>
          <ul className="space-y-1">
            {company.primary_indicators.map((ind, i) => (
              <li
                key={`${ind.name}-${i}`}
                className="flex items-baseline justify-between gap-3 text-sm"
              >
                <span className="text-gray-600">{ind.name}</span>
                <span className="font-medium tabular-nums text-gray-900">
                  {typeof ind.value === "number"
                    ? ind.value.toLocaleString()
                    : ind.value}
                  {ind.unit ? <span className="ml-0.5 text-gray-500">{ind.unit}</span> : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-gray-500">Confidence</span>
          <span className="font-medium tabular-nums text-gray-700">{confPct}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
          <div
            className="h-full rounded-full bg-gray-900 transition-all"
            style={{ width: `${confPct}%` }}
          />
        </div>
      </div>

      {company.caveats && company.caveats.length > 0 && (
        <div>
          <button
            onClick={() => setShowCaveats((v) => !v)}
            className="text-xs font-medium text-gray-500 underline-offset-2 hover:text-gray-800 hover:underline"
          >
            {showCaveats ? "Hide caveats" : `Show caveats (${company.caveats.length})`}
          </button>
          {showCaveats && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-gray-600">
              {company.caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mt-auto pt-1">
        <Link
          href={`/company/${encodeURIComponent(company.ticker)}`}
          className="inline-flex items-center gap-1 text-sm font-medium text-gray-900 hover:underline"
        >
          See full report
          <span aria-hidden>→</span>
        </Link>
      </div>
    </article>
  );
}
