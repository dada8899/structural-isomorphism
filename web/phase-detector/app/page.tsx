"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { CompanyCard } from "@/components/CompanyCard";
import { ScreenerFilter } from "@/components/ScreenerFilter";
import { SearchHero } from "@/components/SearchHero";
import { StatsBar } from "@/components/StatsBar";
import { WaitlistForm } from "@/components/WaitlistForm";
import { fetchScreener, fetchStats } from "@/lib/api";
import { addToHistory } from "@/lib/history";
import {
  CPS_EXPLAIN,
  CPS_ICON,
  CPS_LABEL_ZH,
  CPS_OPTIONS,
  DYNAMICS_EXPLAIN,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL_ZH,
} from "@/lib/labels";
import { parseQuery } from "@/lib/parse-query";
import type { Company, ScreenerFilters, Stats } from "@/lib/types";

// W6-B: reorganized per W5-E #4 (hero info density) + W5-C #3 (signals surface).
// PR-1 copy sweep (2026-05-14): hero rewritten outcome-first, jargon translated,
// internal codenames (普适类 / 临界点 / STRUCTURAL SIGNALS) stripped from user-visible copy.
// New flow:
//   1. Hero: outcome-first headline + 1 primary CTA
//   2. State legend (●▲◆✕): explain icons BEFORE user sees colored badges
//   3. Signals: highlight 6 companies near state flip
//   4. 5 shared-pattern cards
//   5. Stats bar + filter + grid (under the fold)

export default function ScreenerHomePage() {
  const router = useRouter();
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
        label: DYNAMICS_LABEL_ZH[f],
        explain: DYNAMICS_EXPLAIN[f],
      })),
    [],
  );

  const scrollToScreener = useCallback(() => {
    const el = document.getElementById("screener");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // PR-4: hero search submit. parse-query.ts decides whether we navigate to
  // /company/<ticker> or stay on home with filters applied.
  const handleSearchSubmit = useCallback(
    (raw: string) => {
      const parsed = parseQuery(raw);
      // Persist to localStorage history (sidebar UI lives in PR-5).
      addToHistory({ query: parsed.query, route: parsed.route });
      if (parsed.isTicker) {
        router.push(parsed.route);
        return;
      }
      // Apply filters in-place and scroll to the result grid.
      const next: ScreenerFilters = { limit: 50 };
      if (parsed.filters.critical_point_state)
        next.critical_point_state = parsed.filters.critical_point_state;
      if (parsed.filters.dynamics_family)
        next.dynamics_family = parsed.filters.dynamics_family;
      if (parsed.filters.sector) next.sector = parsed.filters.sector;
      setFilters(next);
      // Also reflect in URL so the search is shareable.
      if (parsed.route.startsWith("/?")) {
        // Next.js client-side update (no full reload).
        router.replace(parsed.route);
      }
      // Defer scroll until next paint so the filter state lands first.
      setTimeout(scrollToScreener, 0);
    },
    [router, scrollToScreener],
  );

  return (
    <div className="space-y-10">
      {/* Hero — outcome-first rewrite (PR-1 copy sweep, 2026-05-14). */}
      <section className="rounded-2xl border border-zinc-200 bg-gradient-to-br from-zinc-50 to-white px-6 py-8 sm:px-8 sm:py-10">
        <h1
          className="mb-3 text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          谁在崩盘边缘？谁在悄悄起飞？
        </h1>
        <p className="mb-3 max-w-2xl text-base leading-relaxed text-zinc-600 md:text-lg">
          100 家全球公司的状态评分，30 秒看懂。
          每家公司给你一句话：它现在在哪个阶段、下一步可能往哪走、什么会让它翻车。
        </p>
        <p className="mb-5 max-w-2xl text-sm leading-relaxed text-zinc-500">
          用同一套数学，解释过地震、银行挤兑、电网瘫痪——现在套到上市公司上。
        </p>
        {/* PR-4: legacy "开始查看 →" CTA replaced by <SearchHero> below.
            Keep secondary methodology link inline so users can still pivot to
            the explainer without scrolling. */}
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/methodology"
            className="inline-flex items-center gap-1 px-2 py-2 text-sm font-medium text-zinc-700 underline-offset-4 hover:text-zinc-900 hover:underline"
          >
            怎么看这张表 →
          </Link>
        </div>
        <p className="mt-4 text-xs text-zinc-500">
          研究预览 · 不是投资建议 · 数据由 AI 抽取，请独立核实
        </p>
      </section>

      {/* PR-4: search hero — Perplexity-style single input with autocomplete.
          Replaces the legacy "开始查看 →" scroll-to-filter CTA. Sits BELOW the
          headline + ABOVE the state legend / signals / family blocks. */}
      <SearchHero onSubmit={handleSearchSubmit} />

      {/* State legend — PR-1 reorder: appears BEFORE signals so user knows
          what ●▲◆✕ + colors mean before seeing colored badges. */}
      <section aria-labelledby="cps-legend">
        <h2
          id="cps-legend"
          className="mb-3 text-base font-semibold tracking-tight text-zinc-900"
        >
          四种状态，先看图例
        </h2>
        <p className="mb-3 text-xs text-zinc-500">
          下面所有公司卡片的彩色徽章，都用这四个符号 + 颜色表示当前所处状态。
        </p>
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
                  {CPS_LABEL_ZH[s]}
                </div>
                <p className="mt-0.5 text-xs leading-snug text-zinc-600">
                  {CPS_EXPLAIN[s]}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Signals: companies near a state flip (PR-1 copy: Chinese-first heading) */}
      {signals.length > 0 && (
        <section
          aria-labelledby="signals-heading"
          className="rounded-xl border border-amber-200 bg-amber-50/50 p-5"
        >
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <h2
              id="signals-heading"
              className="text-base font-semibold tracking-tight text-amber-900"
            >
              <span aria-hidden="true">▲ </span>
              当前发现 · {signals.length} 家公司接近状态翻转
            </h2>
          </div>
          <p className="mb-4 text-sm text-zinc-700">
            下面这些公司正处在
            <strong>临界附近</strong>：波动开始放大、反馈开始自我加强，但还没真正翻面。
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

      {/* 5 shared-pattern cards (was: 动力学族 · 5 个普适类) */}
      <section aria-labelledby="families-heading">
        <h2
          id="families-heading"
          className="mb-3 text-base font-semibold tracking-tight text-zinc-900"
        >
          5 类共享模式 · 公司怎么"动"
        </h2>
        <p className="mb-3 text-xs text-zinc-500">
          所有 100 家公司被归入下面其中一类。点开"看完整方法说明"看每一类的解释。
        </p>
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
            看完整方法说明 →
          </Link>
        </div>
      </section>

      {/* Screener — under the fold per W5-E #4 */}
      <section id="screener" aria-labelledby="screener-heading">
        <div className="mb-3 flex items-baseline justify-between">
          <h2
            id="screener-heading"
            className="text-lg font-semibold tracking-tight text-zinc-900"
          >
            按条件挑公司
          </h2>
          <p className="text-xs text-zinc-500">
            选完条件自动刷新，每张卡片附 30 秒一句话总结
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

      {/* W8-D: waitlist CTA, above footer */}
      <section
        aria-labelledby="waitlist-cta-heading"
        className="rounded-2xl border border-zinc-200 bg-gradient-to-br from-zinc-50 to-white px-6 py-8 sm:px-8"
      >
        <div className="mx-auto max-w-2xl">
          <p
            id="waitlist-cta-heading"
            className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500"
          >
            每周一封《结构信号》
          </p>
          <WaitlistForm
            placement="footer"
            source="phase_detector"
            className="border-0 bg-transparent p-0 shadow-none"
          />
        </div>
      </section>

      {/* Sister-product cross-link — symmetric to Structural's homepage callout. */}
      <a
        href="https://structural.bytedance.city"
        target="_blank"
        rel="noopener"
        className="block rounded-2xl border border-zinc-200 bg-white px-6 py-5 transition hover:border-accent hover:bg-zinc-50 sm:px-8"
      >
        <span className="mb-1 block text-xs font-semibold uppercase tracking-wider text-zinc-500">
          姐妹产品
        </span>
        <span className="block text-sm text-zinc-900">
          想找跨学科的解法？→ <strong>Structural</strong>：把你的难题，换成另一个学科已经解过的题
        </span>
      </a>
    </div>
  );
}
