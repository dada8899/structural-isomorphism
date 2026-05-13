"use client";

import { useEffect, useRef, useState } from "react";
import {
  CPS_ICON,
  CPS_LABEL,
  CPS_OPTIONS,
  DYNAMICS_FAMILY_OPTIONS,
  DYNAMICS_LABEL,
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

  const sectors = stats?.by_sector?.map((s) => s.sector) ?? [];

  // Skip the very first apply on mount — parent already has `initial`.
  const isFirstRun = useRef(true);

  // W6-B: debounced reactive apply.
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
    <aside className="space-y-5 rounded-lg border border-zinc-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
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

      <Field label="动力学族">
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          value={df}
          onChange={(e) => setDf(e.target.value as DynamicsFamily | "")}
          aria-label="按动力学族筛选"
        >
          <option value="">全部</option>
          {DYNAMICS_FAMILY_OPTIONS.map((f) => (
            <option key={f} value={f}>
              {DYNAMICS_LABEL[f]}
            </option>
          ))}
        </select>
      </Field>

      <Field label="临界点状态">
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          value={cps}
          onChange={(e) => setCps(e.target.value as CriticalPointState | "")}
          aria-label="按临界点状态筛选"
        >
          <option value="">全部</option>
          {CPS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {CPS_ICON[s]}  {CPS_LABEL[s]}
            </option>
          ))}
        </select>
      </Field>

      <Field label="行业">
        <select
          className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
          aria-label="按行业筛选"
        >
          <option value="">全部</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
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
    </aside>
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
