"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { SparkLine } from "@/components/SparkLine";
import { Events, trackEvent } from "@/lib/analytics";
import {
  CPS_ARIA_LABEL,
  CPS_BADGE,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import type { Company } from "@/lib/types";

// 2026-05-14 P0 fix: read BE-canonical fields (extraction_confidence,
// sector slug, primary_indicators as Record). Display labels come from
// label maps that now key on BE enum slugs.
//
// W6-B: confidence bar tiered color — 0-0.5 red / 0.5-0.75 amber / 0.75+ emerald.
function confidenceColor(c: number): string {
  if (c >= 0.75) return "bg-emerald-600";
  if (c >= 0.5) return "bg-amber-600";
  return "bg-red-600";
}

// Format indicator values: numbers get toLocaleString; null → "—".
function formatIndicatorValue(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}

export function CompanyCard({ company }: { company: Company }) {
  const [showCaveats, setShowCaveats] = useState(false);
  const conf = company.extraction_confidence ?? 0;
  const confPct = Math.round(conf * 100);

  // primary_indicators is a Record<string, string | number | null> now —
  // flatten to a list for rendering, drop empty values.
  const indicators = useMemo(() => {
    const raw = company.primary_indicators;
    if (!raw || typeof raw !== "object") return [];
    return Object.entries(raw).filter(
      ([, v]) => v !== null && v !== undefined && v !== "",
    );
  }, [company.primary_indicators]);

  const sectorLabel = company.sector
    ? SECTOR_LABEL_ZH[company.sector] ?? company.sector
    : null;

  const cps = company.critical_point_state;
  const family = company.dynamics_family;
  const caveats = company.caveats ?? [];

  // W4-B (session #9): Stretched-link pattern — whole card is clickable to
  // /company/[ticker]. Root <article> is relative; an absolutely-positioned
  // <Link> overlay (::after via aria-hidden span) covers the card surface.
  // Inner interactive elements (caveats <button>, "查看完整报告" footer Link)
  // are raised via `relative z-10` so they remain independently clickable.
  // Rationale: <button>/<a> cannot legally nest inside <a> per HTML5 spec,
  // so we cannot simply wrap the entire <article> in a <Link>.
  return (
    <article className="group relative flex flex-col gap-4 rounded-xl border border-zinc-200 bg-white p-5 transition-colors hover:border-blue-300 hover:bg-zinc-50 hover:shadow-sm focus-within:ring-2 focus-within:ring-blue-500 focus-within:ring-offset-2">
      {/* Stretched link overlay — clickable surface for whole card. */}
      <Link
        href={`/company/${encodeURIComponent(company.ticker)}`}
        aria-label={`查看 ${company.ticker} ${company.name} 完整详情`}
        className="absolute inset-0 z-0 rounded-xl focus:outline-none"
        onClick={() =>
          trackEvent(Events.CompanyViewed, {
            ticker: company.ticker,
            family,
            state: cps,
            source: "card_surface",
          })
        }
      >
        <span className="sr-only">查看 {company.ticker} 详情</span>
      </Link>
      <header className="pointer-events-none relative z-[1] flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <h3 className="truncate text-lg font-semibold tracking-tight text-zinc-900 transition-colors group-hover:text-blue-700">
              {company.ticker}
            </h3>
            <span className="truncate text-sm text-zinc-500">
              {company.name}
            </span>
          </div>
          {sectorLabel && (
            <span className="mt-1 inline-block rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
              {sectorLabel}
            </span>
          )}
        </div>
        {/* WCAG 1.4.1 — icon + color + text label (triple redundancy). */}
        <span
          className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${CPS_BADGE[cps] ?? "bg-zinc-400 text-white"}`}
          title={CPS_ARIA_LABEL[cps] ?? cps}
          aria-label={CPS_ARIA_LABEL[cps] ?? cps}
        >
          <span aria-hidden="true" className="text-sm leading-none">
            {CPS_ICON[cps] ?? "?"}
          </span>
          <span>{CPS_LABEL_ZH[cps] ?? cps}</span>
        </span>
      </header>

      <div className="pointer-events-none relative z-[1] text-xs text-zinc-500">
        <span className="font-medium text-zinc-700">
          {DYNAMICS_LABEL_ZH[family] ?? family}
        </span>
        {DYNAMICS_SUBTITLE_ZH[family] && (
          <span className="ml-2 text-gray-500">
            · {DYNAMICS_SUBTITLE_ZH[family]}
          </span>
        )}
      </div>

      <p className="pointer-events-none relative z-[1] text-sm leading-relaxed text-zinc-700">
        {company.tldr}
      </p>

      {/* W11-D: animated sparkline — reveals on scroll into view, segments
          colored by phase band. Pointer events are auto so hover tooltip
          works while the stretched link still navigates on click of empty
          card surface. */}
      <div className="relative z-10 flex items-center justify-between gap-3">
        <span className="text-xs text-zinc-500">近 12 月趋势</span>
        <SparkLine
          ticker={company.ticker}
          currentPhase={cps}
          width={120}
          height={32}
        />
      </div>

      {indicators.length > 0 && (
        <div className="pointer-events-none relative z-[1]">
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            主要指标
          </div>
          <ul className="space-y-1">
            {indicators.map(([name, value]) => (
              <li
                key={name}
                className="flex items-baseline justify-between gap-3 text-sm"
              >
                <span className="text-zinc-600">{name}</span>
                <span className="font-medium tabular-nums text-zinc-900">
                  {formatIndicatorValue(value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="pointer-events-none relative z-[1]">
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
            className={`h-full rounded-full transition-all ${confidenceColor(conf)}`}
            style={{ width: `${confPct}%` }}
          />
        </div>
      </div>

      {caveats.length > 0 && (
        <div className="relative z-10">
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setShowCaveats((v) => !v);
            }}
            className="pointer-events-auto text-xs font-medium text-zinc-500 underline-offset-2 hover:text-zinc-800 hover:underline"
            aria-expanded={showCaveats}
          >
            {showCaveats
              ? "隐藏注意事项"
              : `展开注意事项 (${caveats.length})`}
          </button>
          {showCaveats && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-600">
              {caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="relative z-10 mt-auto pt-1">
        <Link
          href={`/company/${encodeURIComponent(company.ticker)}`}
          className="pointer-events-auto inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline"
          style={{ color: "#2563EB" }}
          onClick={(e) => {
            // Stop the surface link's onClick from double-firing the same
            // event; the stretched link below would also navigate, but it's
            // a separate anchor at z-0 — clicking the explicit footer link
            // should still register its own analytics tag.
            e.stopPropagation();
            trackEvent(Events.CompanyViewed, {
              ticker: company.ticker,
              family,
              state: cps,
              source: "card_footer_link",
            });
          }}
        >
          查看完整报告
          <span aria-hidden="true">→</span>
        </Link>
      </div>
    </article>
  );
}
