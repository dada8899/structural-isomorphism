import { CPS_DOT, CPS_LABEL, DYNAMICS_LABEL } from "@/lib/labels";
import type { Stats } from "@/lib/types";

export function StatsBar({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm text-gray-500">
        Loading stats…
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
        <div>
          <span className="text-gray-500">Total companies</span>{" "}
          <span className="font-semibold tabular-nums">{stats.total_companies}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-gray-500">By dynamics</span>
          {stats.by_dynamics.map((d) => (
            <span key={d.dynamics_family} className="text-gray-700">
              <span className="text-gray-500">
                {DYNAMICS_LABEL[d.dynamics_family] ?? d.dynamics_family}
              </span>{" "}
              <span className="font-medium tabular-nums">{d.count}</span>
            </span>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-gray-500">By state</span>
          {stats.by_critical_point_state.map((c) => (
            <span key={c.critical_point_state} className="flex items-center gap-1.5 text-gray-700">
              <span className={`h-1.5 w-1.5 rounded-full ${CPS_DOT[c.critical_point_state]}`} />
              <span className="text-gray-500">{CPS_LABEL[c.critical_point_state]}</span>
              <span className="font-medium tabular-nums">{c.count}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
