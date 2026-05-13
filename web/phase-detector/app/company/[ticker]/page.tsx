"use client";

import { useEffect, useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import {
  CPS_ARIA_LABEL,
  CPS_BADGE,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import { fetchCompany } from "@/lib/api";
import type { Company } from "@/lib/types";

// 2026-05-14 P0 fix: BE shape uses extraction_confidence / extracted_at /
// primary_indicators-as-Record. Replaced the legacy confidence/updated_at/
// array shape that no longer matches /api/screener.

function confidenceColor(c: number): string {
  if (c >= 0.75) return "bg-emerald-600";
  if (c >= 0.5) return "bg-amber-600";
  return "bg-red-600";
}

function formatIndicatorValue(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}

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

  const indicators = useMemo(() => {
    const raw = company?.primary_indicators;
    if (!raw || typeof raw !== "object") return [];
    return Object.entries(raw).filter(
      ([, v]) => v !== null && v !== undefined && v !== "",
    );
  }, [company?.primary_indicators]);

  const breadcrumb = [
    { label: "首页", href: "/" },
    { label: "公司", href: "/" },
    { label: params.ticker },
  ];

  if (error) {
    return (
      <div className="space-y-4">
        <Breadcrumb items={breadcrumb} />
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          加载 {params.ticker} 失败：{error}
        </div>
      </div>
    );
  }

  if (!company) {
    return (
      <div className="space-y-4">
        <Breadcrumb items={breadcrumb} />
        <div className="h-72 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50" />
      </div>
    );
  }

  const conf = company.extraction_confidence ?? 0;
  const confPct = Math.round(conf * 100);
  const cps = company.critical_point_state;
  const family = company.dynamics_family;
  const sectorLabel = company.sector
    ? SECTOR_LABEL_ZH[company.sector] ?? company.sector
    : null;
  const caveats = company.caveats ?? [];

  return (
    <div className="space-y-6">
      <Breadcrumb items={breadcrumb} />

      <header className="space-y-2">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
            {company.ticker}
          </h1>
          <span className="text-base text-zinc-500">{company.name}</span>
          {sectorLabel && (
            <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600">
              {sectorLabel}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${CPS_BADGE[cps] ?? "bg-zinc-400 text-white"}`}
            aria-label={CPS_ARIA_LABEL[cps] ?? cps}
          >
            <span aria-hidden="true">{CPS_ICON[cps] ?? "?"}</span>
            {CPS_LABEL_ZH[cps] ?? cps}
          </span>
          <span className="text-sm text-zinc-600">
            {DYNAMICS_LABEL_ZH[family] ?? family}
            {DYNAMICS_SUBTITLE_ZH[family] && (
              <span className="ml-2 text-zinc-400">
                · {DYNAMICS_SUBTITLE_ZH[family]}
              </span>
            )}
          </span>
          {company.extracted_at && (
            <span className="text-xs text-zinc-400">
              更新于 {company.extracted_at.slice(0, 10)}
            </span>
          )}
        </div>
      </header>

      <section className="rounded-xl border border-zinc-200 bg-white p-6">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          30 秒一句话
        </h2>
        <p className="text-base leading-relaxed text-zinc-800">
          {company.tldr}
        </p>
      </section>

      <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="rounded-xl border border-zinc-200 bg-white p-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            主要指标
          </h2>
          {indicators.length ? (
            <ul className="space-y-2">
              {indicators.map(([name, value]) => (
                <li
                  key={name}
                  className="flex items-baseline justify-between gap-4 border-b border-zinc-100 pb-2 last:border-0 last:pb-0"
                >
                  <span className="text-sm text-zinc-700">{name}</span>
                  <span className="text-sm font-medium tabular-nums text-zinc-900">
                    {formatIndicatorValue(value)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-zinc-500">未报告指标。</p>
          )}
        </div>

        <div className="rounded-xl border border-zinc-200 bg-white p-6">
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            置信度
          </h2>
          <div className="mb-2 flex items-baseline justify-between">
            <span className="text-3xl font-semibold tabular-nums text-zinc-900">
              {confPct}%
            </span>
            <span className="text-xs text-zinc-500">AI 自报的把握程度</span>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-zinc-100"
            role="progressbar"
            aria-valuenow={confPct}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <div
              className={`h-full rounded-full transition-all ${confidenceColor(conf)}`}
              style={{ width: `${confPct}%` }}
            />
          </div>

          {caveats.length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                注意事项
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-600">
                {caveats.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </section>

      {company.universality_class && (
        <section className="rounded-xl border border-zinc-200 bg-white p-6">
          <button
            onClick={() => setShowRaw((v) => !v)}
            className="text-xs font-medium text-zinc-500 underline-offset-2 hover:text-zinc-800 hover:underline"
            aria-expanded={showRaw}
          >
            {showRaw ? "隐藏元数据" : "查看元数据"}
          </button>
          {showRaw && (
            <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-zinc-50 p-3 text-xs text-zinc-700">
              {JSON.stringify(
                {
                  universality_class: company.universality_class,
                  extraction_model: company.extraction_model,
                  industry: company.industry,
                  market_cap_usd_b: company.market_cap_usd_b,
                },
                null,
                2,
              )}
            </pre>
          )}
        </section>
      )}
    </div>
  );
}
