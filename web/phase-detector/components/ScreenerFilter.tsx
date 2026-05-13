"use client";

import { useState } from "react";
import {
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

interface Props {
  initial: ScreenerFilters;
  stats: Stats | null;
  onApply: (filters: ScreenerFilters) => void;
  loading?: boolean;
}

export function ScreenerFilter({ initial, stats, onApply, loading }: Props) {
  const [df, setDf] = useState<DynamicsFamily | "">(initial.dynamics_family ?? "");
  const [cps, setCps] = useState<CriticalPointState | "">(
    initial.critical_point_state ?? "",
  );
  const [sector, setSector] = useState<string>(initial.sector ?? "");
  const [minConf, setMinConf] = useState<number>(initial.min_confidence ?? 0);

  const sectors = stats?.by_sector?.map((s) => s.sector) ?? [];

  function apply() {
    onApply({
      dynamics_family: df || undefined,
      critical_point_state: cps || undefined,
      sector: sector || undefined,
      min_confidence: minConf > 0 ? minConf : undefined,
      limit: 50,
    });
  }

  function reset() {
    setDf("");
    setCps("");
    setSector("");
    setMinConf(0);
    onApply({ limit: 50 });
  }

  return (
    <aside className="space-y-5 rounded-lg border border-gray-200 bg-white p-5">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Filters
        </h2>
      </div>

      <Field label="Dynamics family">
        <select
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
          value={df}
          onChange={(e) => setDf(e.target.value as DynamicsFamily | "")}
        >
          <option value="">Any</option>
          {DYNAMICS_FAMILY_OPTIONS.map((f) => (
            <option key={f} value={f}>
              {DYNAMICS_LABEL[f]}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Critical-point state">
        <select
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
          value={cps}
          onChange={(e) => setCps(e.target.value as CriticalPointState | "")}
        >
          <option value="">Any</option>
          {CPS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {CPS_LABEL[s]}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Sector">
        <select
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-gray-900 focus:outline-none"
          value={sector}
          onChange={(e) => setSector(e.target.value)}
        >
          <option value="">Any</option>
          {sectors.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </Field>

      <Field label={`Min confidence: ${minConf.toFixed(2)}`}>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={minConf}
          onChange={(e) => setMinConf(parseFloat(e.target.value))}
          className="w-full accent-gray-900"
        />
      </Field>

      <div className="flex gap-2 pt-2">
        <button
          onClick={apply}
          disabled={loading}
          className="flex-1 rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-gray-800 disabled:opacity-50"
        >
          {loading ? "Applying…" : "Apply"}
        </button>
        <button
          onClick={reset}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 transition hover:border-gray-400"
        >
          Reset
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
      <span className="text-xs font-medium text-gray-600">{label}</span>
      {children}
    </label>
  );
}
