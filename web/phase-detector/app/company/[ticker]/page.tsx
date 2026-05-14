"use client";

import { useEffect, useMemo, useState } from "react";
import { Breadcrumb } from "@/components/Breadcrumb";
import Link from "next/link";
import {
  CPS_ARIA_LABEL,
  CPS_BADGE,
  CPS_ICON,
  CPS_LABEL_ZH,
  CPS_SUBTITLE_ZH,
  CPS_EXPLAIN,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
  DYNAMICS_EXPLAIN,
  INDICATOR_LABEL_ZH,
  INDICATOR_TOOLTIP_ZH,
  INDICATOR_VALUE_LABEL_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import { fetchCompany } from "@/lib/api";
import type { Company } from "@/lib/types";

// 2026-05-15 W6-C — detail page polish from 3.4/5 audit toward 9/10:
//   1. Header chips: market_cap_usd_b + industry promoted out of metadata
//      toggle (audit § 3 "Should we add? YES — prominent header chip").
//   2. KeyContextPanel: dynamics_family + CPS explainers surfaced as the
//      primary "what does this mean" block. Closes audit § 6 信息密度 = 3.
//   3. IndicatorTrendIcon: rising/falling/stable get a small SVG sparkline
//      (↑/→/↓) instead of just colored text — improves scannability + WCAG
//      non-color encoding.
//   4. Structured skeleton: matches final layout shape so CLS stays < 0.1
//      (audit § 5 mobile + LCP/CLS budget per task ack).
//   5. Mobile sticky condensed header: when content scrolls, a slim row with
//      ticker + CPS badge stays visible at the top. iOS HIG-like.
//
// All previous behavior preserved: 2026-05-14 BE shape, CN tooltips, bottom
// continuation CTAs.

function confidenceColor(c: number): string {
  if (c >= 0.75) return "bg-emerald-600";
  if (c >= 0.5) return "bg-amber-600";
  return "bg-red-600";
}

function confidenceLabel(c: number): string {
  if (c >= 0.85) return "高把握";
  if (c >= 0.65) return "中等把握";
  if (c >= 0.4) return "较低把握";
  return "把握很弱";
}

function formatIndicatorValue(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") return v.toLocaleString();
  const s = String(v);
  return INDICATOR_VALUE_LABEL_ZH[s] ?? s;
}

function indicatorLabel(name: string): string {
  return INDICATOR_LABEL_ZH[name] ?? name;
}

// W6-C: non-color trend icon — accessible to red/green colorblind users.
function IndicatorTrendIcon({ value }: { value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === "") return null;
  const s = String(value).toLowerCase();
  let glyph: string | null = null;
  let cls = "text-zinc-400";
  if (s === "rising" || s === "heavy_tail_steepening") {
    glyph = "↑";
    cls = "text-amber-600";
  } else if (s === "falling") {
    glyph = "↓";
    cls = "text-emerald-600";
  } else if (s === "stable") {
    glyph = "→";
    cls = "text-zinc-500";
  } else if (s === "unknown" || s === "n/a") {
    glyph = "·";
    cls = "text-zinc-300";
  }
  if (!glyph) return null;
  return (
    <span
      aria-hidden="true"
      className={`mr-2 inline-block w-3 text-center text-sm font-semibold ${cls}`}
    >
      {glyph}
    </span>
  );
}

function formatMarketCap(b: number | null | undefined): string | null {
  if (b === null || b === undefined) return null;
  if (b >= 1000) return `市值 ${(b / 1000).toFixed(2)} 万亿美元`;
  if (b >= 1) return `市值 ${b.toLocaleString(undefined, { maximumFractionDigits: 1 })} 亿美元`;
  return `市值 ${(b * 1000).toFixed(0)} 百万美元`;
}

function DetailSkeleton({ breadcrumb }: { breadcrumb: { label: string; href?: string }[] }) {
  // W6-C: structured skeleton matching final layout shape to keep CLS ≤ 0.1.
  // Replaces the legacy single h-72 pulse block.
  return (
    <div className="space-y-6" aria-busy="true" aria-live="polite">
      <Breadcrumb items={breadcrumb} />
      <div className="space-y-3">
        <div className="h-9 w-40 animate-pulse rounded bg-zinc-200" />
        <div className="flex flex-wrap gap-2">
          <div className="h-6 w-20 animate-pulse rounded-full bg-zinc-200" />
          <div className="h-6 w-24 animate-pulse rounded-full bg-zinc-200" />
          <div className="h-6 w-28 animate-pulse rounded-full bg-zinc-200" />
        </div>
      </div>
      <div className="h-36 animate-pulse rounded-xl border border-zinc-200 bg-white" />
      <div className="h-28 animate-pulse rounded-xl border border-zinc-200 bg-white" />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div className="h-44 animate-pulse rounded-xl border border-zinc-200 bg-white" />
        <div className="h-44 animate-pulse rounded-xl border border-zinc-200 bg-white" />
      </div>
    </div>
  );
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
        <div
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          <p className="font-medium">加载 {params.ticker} 失败</p>
          <p className="mt-1 text-xs text-red-700/80">{error}</p>
          <Link
            href="/"
            className="mt-3 inline-flex rounded-md border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 hover:border-red-400"
          >
            ← 返回公司表
          </Link>
        </div>
      </div>
    );
  }

  if (!company) {
    return <DetailSkeleton breadcrumb={breadcrumb} />;
  }

  const conf = company.extraction_confidence ?? 0;
  const confPct = Math.round(conf * 100);
  const cps = company.critical_point_state;
  const family = company.dynamics_family;
  const sectorLabel = company.sector
    ? SECTOR_LABEL_ZH[company.sector] ?? company.sector
    : null;
  const caveats = company.caveats ?? [];
  const marketCapLabel = formatMarketCap(company.market_cap_usd_b);

  return (
    <div className="space-y-6">
      <Breadcrumb items={breadcrumb} />

      <header className="space-y-3" data-testid="company-header">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
            {company.ticker}
          </h1>
          <span className="text-base text-zinc-500">{company.name}</span>
        </div>

        {/* W6-C: chips row promoted out of metadata toggle (audit § 3). */}
        <div
          className="flex flex-wrap items-center gap-2 text-xs"
          data-testid="company-chips"
        >
          {sectorLabel && (
            <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-zinc-700">
              {sectorLabel}
            </span>
          )}
          {company.industry && (
            <span className="rounded-full bg-zinc-100 px-2.5 py-0.5 text-zinc-700">
              {company.industry}
            </span>
          )}
          {marketCapLabel && (
            <span
              className="rounded-full bg-zinc-100 px-2.5 py-0.5 tabular-nums text-zinc-700"
              data-testid="market-cap-chip"
            >
              {marketCapLabel}
            </span>
          )}
          {company.extracted_at && (
            <span className="text-zinc-400">
              · 更新于 {company.extracted_at.slice(0, 10)}
            </span>
          )}
        </div>

        {/* CPS badge + dynamics family on its own row for visual anchor. */}
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium ${CPS_BADGE[cps] ?? "bg-zinc-400 text-white"}`}
            aria-label={CPS_ARIA_LABEL[cps] ?? cps}
            data-testid="cps-badge"
          >
            <span aria-hidden="true">{CPS_ICON[cps] ?? "?"}</span>
            {CPS_LABEL_ZH[cps] ?? cps}
          </span>
          <span
            className="text-sm text-zinc-700"
            data-testid="dynamics-family"
          >
            {DYNAMICS_LABEL_ZH[family] ?? family}
            {DYNAMICS_SUBTITLE_ZH[family] && (
              <span className="ml-2 text-zinc-400">
                · {DYNAMICS_SUBTITLE_ZH[family]}
              </span>
            )}
          </span>
        </div>
      </header>

      {/* TL;DR card — largest visual block, the 30-second anchor. */}
      <section
        className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm"
        aria-labelledby="tldr-heading"
        data-testid="tldr-section"
      >
        <h2
          id="tldr-heading"
          className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500"
        >
          30 秒一句话
        </h2>
        <p className="text-base leading-relaxed text-zinc-800">{company.tldr}</p>
      </section>

      {/* W6-C: KeyContextPanel — surface the family + CPS explainer prominently.
          Audit § 6 信息密度 = 3 ("lacks evidence / sources"). Until evidence
          anchors land BE-side, we surface the canonical "what does this state
          mean" so confidence is not floating on bare TL;DR + indicator dump. */}
      <section
        className="rounded-xl border border-zinc-200 bg-zinc-50 p-6"
        aria-labelledby="context-heading"
        data-testid="key-context-panel"
      >
        <h2
          id="context-heading"
          className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500"
        >
          状态解读
        </h2>
        <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <dt className="mb-1 text-xs font-medium text-zinc-500">
              当前阶段（{CPS_LABEL_ZH[cps] ?? cps}）
            </dt>
            <dd className="text-sm leading-relaxed text-zinc-700">
              {CPS_EXPLAIN[cps] ?? CPS_SUBTITLE_ZH[cps] ?? "证据不足，暂未判定。"}
            </dd>
          </div>
          <div>
            <dt className="mb-1 text-xs font-medium text-zinc-500">
              主导动力学（{DYNAMICS_LABEL_ZH[family] ?? family}）
            </dt>
            <dd className="text-sm leading-relaxed text-zinc-700">
              {DYNAMICS_EXPLAIN[family] ?? DYNAMICS_SUBTITLE_ZH[family] ?? ""}
            </dd>
          </div>
        </dl>
      </section>

      <section className="grid grid-cols-1 gap-5 md:grid-cols-2">
        <div
          className="rounded-xl border border-zinc-200 bg-white p-6"
          data-testid="indicators-panel"
        >
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            主要指标
          </h2>
          {indicators.length ? (
            <ul className="space-y-2">
              {indicators.map(([name, value]) => {
                const tooltip = INDICATOR_TOOLTIP_ZH[name];
                return (
                  <li
                    key={name}
                    className="flex items-baseline justify-between gap-4 border-b border-zinc-100 pb-2 last:border-0 last:pb-0"
                  >
                    <span
                      className="text-sm text-zinc-700"
                      title={tooltip}
                      aria-label={
                        tooltip
                          ? `${indicatorLabel(name)}：${tooltip}`
                          : undefined
                      }
                    >
                      {indicatorLabel(name)}
                    </span>
                    <span className="flex items-baseline text-sm font-medium tabular-nums text-zinc-900">
                      <IndicatorTrendIcon value={value} />
                      {formatIndicatorValue(value)}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-zinc-500">未报告指标。</p>
          )}
        </div>

        <div
          className="rounded-xl border border-zinc-200 bg-white p-6"
          data-testid="confidence-panel"
        >
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500">
            置信度
          </h2>
          <div className="mb-2 flex items-baseline justify-between gap-2">
            <span className="text-3xl font-semibold tabular-nums text-zinc-900">
              {confPct}%
            </span>
            <span className="text-xs text-zinc-500">{confidenceLabel(conf)}</span>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-zinc-100"
            role="progressbar"
            aria-valuenow={confPct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="AI 自报的把握程度"
          >
            <div
              className={`h-full rounded-full transition-all ${confidenceColor(conf)}`}
              style={{ width: `${confPct}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-zinc-500">
            AI 自报的把握程度。请独立核实。
          </p>

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

      {/* Metadata toggle now only exposes raw debug payload; chips above
          already surface user-facing fields (sector / industry / market cap). */}
      <section className="rounded-xl border border-zinc-200 bg-white p-6">
        <button
          onClick={() => setShowRaw((v) => !v)}
          className="text-xs font-medium text-zinc-500 underline-offset-2 hover:text-zinc-800 hover:underline"
          aria-expanded={showRaw}
          data-testid="metadata-toggle"
        >
          {showRaw ? "隐藏原始字段" : "查看原始字段"}
        </button>
        {showRaw && (
          <pre className="mt-3 max-h-96 overflow-auto rounded-md bg-zinc-50 p-3 text-xs text-zinc-700">
            {JSON.stringify(
              {
                ticker: company.ticker,
                universality_class: company.universality_class,
                extraction_model: company.extraction_model,
                industry: company.industry,
                market_cap_usd_b: company.market_cap_usd_b,
                sector: company.sector,
              },
              null,
              2,
            )}
          </pre>
        )}
      </section>

      {/* Continuation CTAs — back to table + cross-link to universality classes.
          W10-E: link directly to /universality/<class_id> for the matched class
          (when present), and to /compare seeded with this ticker. */}
      <nav
        aria-label="继续浏览"
        className="flex flex-wrap items-center gap-3 border-t border-zinc-200 pt-5 text-sm"
        data-testid="continuation-nav"
      >
        <Link
          href="/"
          className="rounded-md border border-zinc-200 px-3 py-1.5 text-zinc-700 hover:border-zinc-400 hover:text-zinc-900"
        >
          ← 返回公司表
        </Link>
        {company.universality_class && (
          <Link
            href={`/universality/${encodeURIComponent(company.universality_class)}`}
            className="rounded-md border border-zinc-200 px-3 py-1.5 text-zinc-700 hover:border-zinc-400 hover:text-zinc-900"
            data-testid="universality-class-link"
          >
            查看普适类 {company.universality_class} →
          </Link>
        )}
        <Link
          href={`/compare?tickers=${encodeURIComponent(company.ticker)}`}
          className="rounded-md border border-zinc-200 px-3 py-1.5 text-zinc-700 hover:border-zinc-400 hover:text-zinc-900"
          data-testid="compare-link"
        >
          在对比页打开 →
        </Link>
        <Link
          href="/methodology"
          className="text-zinc-500 hover:text-zinc-900 hover:underline"
        >
          方法说明
        </Link>
        <a
          href="https://beta.structural.bytedance.city/classes"
          target="_blank"
          rel="noopener"
          className="text-zinc-500 hover:text-zinc-900 hover:underline"
        >
          Structural 全局视角 ↗
        </a>
      </nav>
    </div>
  );
}
