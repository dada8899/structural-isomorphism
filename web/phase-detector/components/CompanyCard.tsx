"use client";

import Link from "next/link";
import { useState } from "react";
import {
  CPS_ARIA_LABEL,
  CPS_BADGE,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
} from "@/lib/labels";
import type { Company } from "@/lib/types";

// W6-B: confidence bar tiered color (W5-E quick win).
// 0-0.5 → red, 0.5-0.75 → amber, 0.75-1.0 → emerald.
function confidenceColor(c: number): string {
  if (c >= 0.75) return "bg-emerald-600";
  if (c >= 0.5) return "bg-amber-600";
  return "bg-red-600";
}

export function CompanyCard({ company }: { company: Company }) {
  const [showCaveats, setShowCaveats] = useState(false);
  const confPct = Math.round(company.confidence * 100);

  return (
    <article className="flex flex-col gap-4 rounded-xl border border-zinc-200 bg-white p-5 transition hover:border-zinc-300 hover:shadow-sm">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h3 className="truncate text-lg font-semibold tracking-tight text-zinc-900">
              {company.ticker}
            </h3>
            <span className="truncate text-sm text-zinc-500">
              {company.name}
            </span>
          </div>
          {company.sector && (
            <span className="mt-1 inline-block rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
              {company.sector}
            </span>
          )}
        </div>
        {/* W6-B: triple-redundant CPS badge — icon + color + text label.
            WCAG 1.4.1 (color is not the only signal). */}
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${CPS_BADGE[company.critical_point_state]}`}
          title={CPS_ARIA_LABEL[company.critical_point_state]}
          aria-label={CPS_ARIA_LABEL[company.critical_point_state]}
        >
          <span aria-hidden="true" className="text-sm leading-none">
            {CPS_ICON[company.critical_point_state]}
          </span>
          <span>{CPS_LABEL_ZH[company.critical_point_state]}</span>
        </span>
      </header>

      <div className="text-xs text-zinc-500">
        <span className="font-medium text-zinc-700">
          {DYNAMICS_LABEL_ZH[company.dynamics_family] ?? company.dynamics_family}
        </span>
        {DYNAMICS_SUBTITLE_ZH[company.dynamics_family] && (
          <span className="ml-2 text-gray-500">
            · {DYNAMICS_SUBTITLE_ZH[company.dynamics_family]}
          </span>
        )}
      </div>

      <p className="text-sm leading-relaxed text-zinc-700">{company.tldr}</p>

      {company.primary_indicators?.length > 0 && (
        <div>
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            主要指标
          </div>
          <ul className="space-y-1">
            {company.primary_indicators.map((ind, i) => (
              <li
                key={`${ind.name}-${i}`}
                className="flex items-baseline justify-between gap-3 text-sm"
              >
                <span className="text-zinc-600">{ind.name}</span>
                <span className="font-medium tabular-nums text-zinc-900">
                  {typeof ind.value === "number"
                    ? ind.value.toLocaleString()
                    : ind.value}
                  {ind.unit ? (
                    <span className="ml-0.5 text-zinc-500">{ind.unit}</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* W6-B: confidence bar with tiered color + larger numeric font (W5-E #6). */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs text-zinc-500">置信度</span>
          <span className="text-base font-semibold tabular-nums text-zinc-800">
            {confPct}%
          </span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-zinc-100"
          role="progressbar"
          aria-valuenow={confPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`置信度 ${confPct}%`}
        >
          <div
            className={`h-full rounded-full transition-all ${confidenceColor(company.confidence)}`}
            style={{ width: `${confPct}%` }}
          />
        </div>
      </div>

      {company.caveats && company.caveats.length > 0 && (
        <div>
          <button
            onClick={() => setShowCaveats((v) => !v)}
            className="text-xs font-medium text-zinc-500 underline-offset-2 hover:text-zinc-800 hover:underline"
            aria-expanded={showCaveats}
          >
            {showCaveats
              ? "隐藏注意事项"
              : `展开注意事项 (${company.caveats.length})`}
          </button>
          {showCaveats && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600">
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
          className="inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
          style={{ color: "#2563EB" }}
        >
          查看完整报告
          <span aria-hidden="true">→</span>
        </Link>
      </div>
    </article>
  );
}
