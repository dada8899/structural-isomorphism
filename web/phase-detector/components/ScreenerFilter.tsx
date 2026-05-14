"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Events, trackEvent } from "@/lib/analytics";
import {
  CPS_ICON,
  CPS_LABEL_ZH,
  CPS_OPTIONS,
  CPS_SUBTITLE_ZH,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import type {
  CriticalPointState,
  DynamicsFamily,
  ScreenerFilters,
  Stats,
} from "@/lib/types";

// W6-B: reactive filter (W5-E P0).
// - State propagates immediately on change via 300ms debounce.
// - No Apply button (immediate feedback). Only "重置" remains.
// - Loading indicator shown inline while parent fetches.

interface Props {
  initial: ScreenerFilters;
  stats: Stats | null;
  onApply: (filters: ScreenerFilters) => void;
  loading?: boolean;
}

const DEBOUNCE_MS = 300;

export function ScreenerFilter({ initial, stats, onApply, loading }: Props) {
  const [df, setDf] = useState<DynamicsFamily | "">(
    initial.dynamics_family ?? "",
  );
  const [cps, setCps] = useState<CriticalPointState | "">(
    initial.critical_point_state ?? "",
  );
  const [sector, setSector] = useState<string>(initial.sector ?? "");
  const [minConf, setMinConf] = useState<number>(initial.min_confidence ?? 0);

  // 2026-05-14 P0 fix: by_sector is now Record<slug, count> (BE canonical),
  // not an array. The previous `.map()` call threw at render → wiped out
  // the entire sector <select>. Sort by descending count for relevance,
  // then alphabetically by display label as tiebreaker.
  const sectors = useMemo(() => {
    const raw = Object.entries(stats?.by_sector ?? {});
    return raw
      .map(([slug, count]) => ({
        slug,
        count,
        label: SECTOR_LABEL_ZH[slug] ?? slug,
      }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "zh-CN"));
  }, [stats?.by_sector]);

  // Skip the very first apply on mount — parent already has `initial`.
  const isFirstRun = useRef(true);

  // W6-B: debounced reactive apply.
  // W8-D: also fire Plausible custom event when a filter change actually
  // produces a new query (not on initial mount).
  useEffect(() => {
    if (isFirstRun.current) {
      isFirstRun.current = false;
      return;
    }
    const handle = setTimeout(() => {
      onApply({
        dynamics_family: df || undefined,
        critical_point_state: cps || undefined,
        sector: sector || undefined,
        min_confidence: minConf > 0 ? minConf : undefined,
        limit: 50,
      });
      trackEvent(Events.ScreenerFilterApplied, {
        family: df || "any",
        state: cps || "any",
        sector: sector || "any",
        min_confidence: minConf,
      });
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [df, cps, sector, minConf]);

  function reset() {
    setDf("");
    setCps("");
    setSector("");
    setMinConf(0);
    // Reset is immediate — bypass debounce.
    onApply({ limit: 50 });
  }

  const hasActiveFilter = df || cps || sector || minConf > 0;

  return (
    // W12-A: axe `landmark-complementary-is-top-level` flagged the nested
    // <aside>. The filter panel is a sub-region of the companies <main>, not
    // tangentially-related content, so a `region` with aria-labelledby is the
    // semantically-correct landmark here.
    <section
      role="region"
      aria-labelledby="screener-filter-heading"
      className="space-y-5 rounded-lg border border-zinc-200 bg-white p-5"
    >
      <div className="flex items-center justify-between">
        <h2
          id="screener-filter-heading"
          className="text-xs font-semibold uppercase tracking-wider text-zinc-500"
        >
          筛选条件
        </h2>
        {loading && (
          <span
            className="text-xs text-zinc-400"
            role="status"
            aria-live="polite"
          >
            正在筛选…
          </span>
        )}
      </div>

      <Field label="怎么动（共享模式）">
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          value={df}
          onChange={(e) => setDf(e.target.value as DynamicsFamily | "")}
          aria-label="按共享模式筛选"
        >
          <option value="">任意</option>
          {DYNAMICS_FAMILY_OPTIONS.map((f) => (
            <option key={f} value={f}>
              {DYNAMICS_LABEL_ZH[f]}
            </option>
          ))}
        </select>
        {df && (
          <p className="mt-1 text-xs text-gray-500">{DYNAMICS_SUBTITLE_ZH[df]}</p>
        )}
      </Field>

      <Field label="当前状态">
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          value={cps}
          onChange={(e) => setCps(e.target.value as CriticalPointState | "")}
          aria-label="按当前状态筛选"
        >
          <option value="">任意</option>
          {CPS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {CPS_ICON[s]}  {CPS_LABEL_ZH[s]}
            </option>
          ))}
        </select>
        {cps && (
          <p className="mt-1 text-xs text-gray-500">{CPS_SUBTITLE_ZH[cps]}</p>
        )}
      </Field>

      <Field label="行业">
        {/* While stats is null, the sector list comes back empty (it's
            keyed off stats.by_sector). Disable the select + show a
            "加载中" placeholder so the user knows it's not broken — they
            see structure but can't pick yet. Other selects (动态 / 状态)
            don't need this because their options are hardcoded constants. */}
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none disabled:cursor-wait disabled:bg-zinc-50 disabled:text-zinc-400"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          aria-label="按行业筛选"
          disabled={!stats}
          aria-busy={!stats}
        >
          {!stats ? (
            <option value="">加载行业列表中…</option>
          ) : (
            <>
              <option value="">全部</option>
              {sectors.map((s) => (
                <option key={s.slug} value={s.slug}>
                  {s.label} ({s.count})
                </option>
              ))}
            </>
          )}
        </select>
      </Field>

      <Field label={`最低置信度：${minConf.toFixed(2)}`}>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={minConf}
          onChange={(e) => setMinConf(parseFloat(e.target.value))}
          className="w-full accent-blue-600"
          aria-label={`最低置信度滑块，当前 ${minConf.toFixed(2)}`}
        />
      </Field>

      <div className="flex items-center justify-between pt-2">
        <span className="text-xs text-zinc-400">
          {hasActiveFilter ? "已应用筛选条件" : "无筛选条件"}
        </span>
        <button
          onClick={reset}
          disabled={!hasActiveFilter}
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-xs text-zinc-700 transition hover:border-zinc-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          重置
        </button>
      </div>
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium text-zinc-600">{label}</span>
      {children}
    </label>
  );
}
