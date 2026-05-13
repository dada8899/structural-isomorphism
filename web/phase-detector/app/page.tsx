"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CompanyCard } from "@/components/CompanyCard";
import { ScreenerFilter } from "@/components/ScreenerFilter";
import { StatsBar } from "@/components/StatsBar";
import { fetchScreener, fetchStats } from "@/lib/api";
import {
  CPS_EXPLAIN,
  CPS_ICON,
  CPS_LABEL,
  CPS_OPTIONS,
  DYNAMICS_EXPLAIN,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL,
} from "@/lib/labels";
import type { Company, ScreenerFilters, Stats } from "@/lib/types";

// W6-B: reorganized per W5-E #4 (hero info density) + W5-C #3 (STRUCTURAL SIGNALS surface).
// New flow:
//   1. Hero: tagline + 1 primary CTA (anchor to filters)
//   2. STRUCTURAL SIGNALS: highlight 6 companies near critical point
//   3. 6 family overview cards
//   4. Stats bar + filter + grid (under the fold)

export default function ScreenerHomePage() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [signals, setSignals] = useState<Company[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filters, setFilters] = useState<ScreenerFilters>({ limit: 50 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Initial stats fetch (independent from screener).
  useEffect(() => {
    let cancelled = false;
    fetchStats()
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch((err) => {
        if (!cancelled) {
          // eslint-disable-next-line no-console
          console.warn("stats fetch failed:", err);
        }
      });
    // W6-B: fetch signals — companies near or past critical point.
    fetchScreener({ critical_point_state: "near_critical", limit: 6 })
      .then((s) => {
        if (!cancelled) setSignals(s);
      })
      .catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("signals fetch failed:", err);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const load = useCallback(async (f: ScreenerFilters) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchScreener(f);
      setCompanies(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      setCompanies([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filters);
  }, [filters, load]);

  const handleApply = useCallback((next: ScreenerFilters) => {
    setFilters(next);
  }, []);

  const familyOverview = useMemo(
    () =>
      DYNAMICS_FAMILY_OPTIONS.map((f) => ({
        family: f,
        label: DYNAMICS_LABEL[f],
        explain: DYNAMICS_EXPLAIN[f],
      })),
    [],
  );

  return (
    <div className="space-y-10">
      {/* Hero — simplified per W5-E #4 */}
      <section className="pt-2">
        <h1
          className="serif mb-2 text-3xl font-semibold leading-tight tracking-tight text-zinc-900 md:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          Phase Detector
        </h1>
        <p className="mb-3 text-base text-zinc-600 md:text-lg">
          按<strong className="text-zinc-900">结构动力学族</strong>和
          <strong className="text-zinc-900">临界点状态</strong>筛选公司。30 秒
          TL;DR，看清谁接近相变。
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <a
            href="#screener"
            className="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            开始筛选 ↓
          </a>
          <Link
            href="/methodology"
            className="inline-flex items-center gap-1 px-2 py-2 text-sm font-medium text-zinc-700 hover:text-zinc-900"
          >
            了解方法 →
          </Link>
        </div>
      </section>

      {/* STRUCTURAL SIGNALS — surface near-critical companies (W5-C #3) */}
      {signals.length > 0 && (
        <section
          aria-labelledby="signals-heading"
          className="rounded-xl border border-amber-200 bg-amber-50/50 p-5"
        >
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2
              id="signals-heading"
              className="text-sm font-semibold uppercase tracking-wider text-amber-900"
            >
              <span aria-hidden="true">▲ </span>
              STRUCTURAL SIGNALS
            </h2>
            <span className="text-xs text-zinc-500">
              {signals.length} 家公司接近临界点
            </span>
          </div>
          <p className="mb-4 text-sm text-zinc-700">
            根据 100 家公司的结构抽取，以下公司当前处于
            <strong>临近临界</strong>状态——波动率上升、放大反馈开始显现，但尚未跳到新稳态。
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {signals.map((c) => (
              <Link
                key={c.ticker}
                href={`/company/${encodeURIComponent(c.ticker)}`}
                className="rounded-lg border border-amber-200 bg-white p-3 transition hover:border-amber-400 hover:shadow-sm"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-semibold tracking-tight text-zinc-900">
                    {c.ticker}
                  </span>
                  <span className="text-xs text-zinc-500">{c.sector}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-zinc-600">
                  {c.tldr}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* 6 Family overview */}
      <section aria-labelledby="families-heading">
        <h2
          id="families-heading"
          className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500"
        >
          动力学族 · 5 个普适类
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {familyOverview.map((f) => (
            <div
              key={f.family}
              className="rounded-lg border border-zinc-200 bg-white p-4"
            >
              <div className="mb-1 text-sm font-semibold text-zinc-900">
                {f.label}
              </div>
              <p className="text-xs leading-relaxed text-zinc-600">
                {f.explain}
              </p>
            </div>
          ))}
        </div>
        <div className="mt-3">
          <Link
            href="/methodology"
            className="text-xs font-medium text-zinc-600 hover:text-zinc-900 hover:underline"
          >
            查看完整方法论 →
          </Link>
        </div>
      </section>

      {/* CPS legend — W6-B: surface icons + colors + meanings here */}
      <section aria-labelledby="cps-legend">
        <h2
          id="cps-legend"
          className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500"
        >
          临界点状态图例
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {CPS_OPTIONS.map((s) => (
            <div
              key={s}
              className="flex items-start gap-3 rounded-lg border border-zinc-200 bg-white p-3"
            >
              <span
                className="text-2xl leading-none"
                style={{
                  color:
                    s === "subcritical"
                      ? "#059669"
                      : s === "near_critical"
                        ? "#D97706"
                        : s === "supercritical"
                          ? "#DC2626"
                          : "#18181B",
                }}
                aria-hidden="true"
              >
                {CPS_ICON[s]}
              </span>
              <div>
                <div className="text-sm font-medium text-zinc-900">
                  {CPS_LABEL[s]}
                </div>
                <p className="mt-0.5 text-xs leading-snug text-zinc-600">
                  {CPS_EXPLAIN[s]}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Screener — under the fold per W5-E #4 */}
      <section id="screener" aria-labelledby="screener-heading">
        <div className="mb-3 flex items-baseline justify-between">
          <h2
            id="screener-heading"
            className="text-lg font-semibold tracking-tight text-zinc-900"
          >
            公司筛选器
          </h2>
          <p className="text-xs text-zinc-500">
            选择条件后自动应用，每张卡片含 30 秒 TL;DR
          </p>
        </div>

        <div className="mb-4">
          <StatsBar stats={stats} />
        </div>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[260px_1fr]">
          <ScreenerFilter
            initial={filters}
            stats={stats}
            onApply={handleApply}
            loading={loading}
          />

          <section aria-live="polite">
            {error && (
              <div
                className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                role="alert"
              >
                筛选加载失败：{error}
              </div>
            )}

            {!error && loading && companies.length === 0 && (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div
                    key={i}
                    className="h-56 animate-pulse rounded-xl border border-zinc-200 bg-zinc-50"
                  />
                ))}
              </div>
            )}

            {!error && !loading && companies.length === 0 && (
              <div className="rounded-lg border border-zinc-200 bg-zinc-50 px-6 py-12 text-center text-sm text-zinc-500">
                没有公司匹配这些筛选条件。请尝试放宽条件或
                <button
                  onClick={() => handleApply({ limit: 50 })}
                  className="ml-1 font-medium text-zinc-700 underline-offset-2 hover:underline"
                >
                  清除筛选
                </button>
                。
              </div>
            )}

            {!error && companies.length > 0 && (
              <>
                <div className="mb-2 text-xs text-zinc-500">
                  显示 {companies.length} 家公司
                  {loading && <span className="ml-2">· 筛选中…</span>}
                </div>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-2">
                  {companies.map((c) => (
                    <CompanyCard key={c.ticker} company={c} />
                  ))}
                </div>
              </>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
