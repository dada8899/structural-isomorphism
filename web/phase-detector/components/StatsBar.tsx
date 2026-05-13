import {
  CPS_DOT,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
} from "@/lib/labels";
import type { Stats } from "@/lib/types";

// W6-B: align colors with design system (zinc + accent).
// CPS pills now show icon + dot + label for non-color encoding redundancy.

export function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-500">
        正在加载统计…
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <div>
          <span className="text-zinc-500">公司总数</span>{" "}
          <span className="font-semibold tabular-nums">
            {stats.total_companies}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-zinc-500">动力学 · How it moves</span>
          {stats.by_dynamics.map((d) => (
            <span key={d.dynamics_family} className="text-zinc-700">
              <span className="text-zinc-500">
                {DYNAMICS_LABEL_ZH[d.dynamics_family] ?? d.dynamics_family}
              </span>{" "}
              <span className="font-medium tabular-nums">{d.count}</span>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-zinc-500">临界状态 · Critical state</span>
          {stats.by_critical_point_state.map((c) => (
            <span
              key={c.critical_point_state}
              className="flex items-center gap-1.5 text-zinc-700"
              title={CPS_LABEL_ZH[c.critical_point_state]}
            >
              <span
                aria-hidden="true"
                className="font-semibold leading-none"
              >
                {CPS_ICON[c.critical_point_state]}
              </span>
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${CPS_DOT[c.critical_point_state]}`}
              />
              <span className="text-zinc-500">
                {CPS_LABEL_ZH[c.critical_point_state]}
              </span>
              <span className="font-medium tabular-nums">{c.count}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
