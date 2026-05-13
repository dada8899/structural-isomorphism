import {
  CPS_DOT,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
} from "@/lib/labels";
import type {
  CriticalPointState,
  DynamicsFamily,
  Stats,
} from "@/lib/types";

// 2026-05-14 P0 fix: Stats is now Record-shaped (not arrays). Iterate via
// Object.entries — the previous `.map()` call was the source of the
// production crash that wiped out the entire sector <select>.
//
// W6-B: aligned colors with design system (zinc + accent); CPS pills show
// icon + dot + label for non-color encoding redundancy.

export function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-500">
        正在加载统计…
      </div>
    );
  }

  const dynamicsEntries = Object.entries(stats.by_dynamics_family ?? {}) as Array<
    [DynamicsFamily, number]
  >;
  const cpsEntries = Object.entries(stats.by_critical_point_state ?? {}) as Array<
    [CriticalPointState, number]
  >;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <div>
          <span className="text-zinc-500">公司总数</span>{" "}
          <span className="font-semibold tabular-nums">{stats.total}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-zinc-500">怎么动</span>
          {dynamicsEntries.map(([family, count]) => (
            <span key={family} className="text-zinc-700">
              <span className="text-zinc-500">
                {DYNAMICS_LABEL_ZH[family] ?? family}
              </span>{" "}
              <span className="font-medium tabular-nums">{count}</span>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-zinc-500">当前状态</span>
          {cpsEntries.map(([state, count]) => (
            <span
              key={state}
              className="flex items-center gap-1.5 text-zinc-700"
              title={CPS_LABEL_ZH[state] ?? state}
            >
              <span
                aria-hidden="true"
                className="font-semibold leading-none"
              >
                {CPS_ICON[state] ?? "?"}
              </span>
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${CPS_DOT[state] ?? "bg-zinc-300"}`}
              />
              <span className="text-zinc-500">
                {CPS_LABEL_ZH[state] ?? state}
              </span>
              <span className="font-medium tabular-nums">{count}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
