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
  // Skeleton mirrors the loaded layout exactly — same outer chrome, same row
  // structure, same gap rhythm — so when real numbers land the swap is
  // invisible (no height jump, no "正在加载统计…" flash).
  // Three groups: 公司总数 (1 chip), 怎么动 (~3 chips), 当前状态 (~5 chips).
  if (!stats) {
    return (
      <div
        // W12-A: axe `aria-prohibited-attr` — aria-label on generic <div>
        // requires either an explicit role or a non-presentational element.
        // Use role="status" so loading is announced once and the label is
        // accepted by AT (WCAG 4.1.2 + ARIA 1.2 spec § 5.2.7.2).
        role="status"
        className="rounded-lg border border-zinc-200 bg-white px-4 py-3"
        aria-busy="true"
        aria-label="加载统计中"
      >
        <div className="flex flex-wrap items-center gap-x-8 gap-y-2 text-sm">
          {/* 公司总数 */}
          <div className="flex items-center gap-2">
            <span className="h-3 w-12 animate-pulse rounded bg-zinc-100" />
            <span className="h-3 w-8 animate-pulse rounded bg-zinc-200" />
          </div>
          {/* 怎么动 */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="h-3 w-10 animate-pulse rounded bg-zinc-100" />
            {Array.from({ length: 3 }).map((_, i) => (
              <span key={i} className="flex items-center gap-1">
                <span className="h-3 w-12 animate-pulse rounded bg-zinc-100" />
                <span className="h-3 w-5 animate-pulse rounded bg-zinc-200" />
              </span>
            ))}
          </div>
          {/* 当前状态 */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="h-3 w-12 animate-pulse rounded bg-zinc-100" />
            {Array.from({ length: 5 }).map((_, i) => (
              <span key={i} className="flex items-center gap-1.5">
                <span className="h-3 w-3 animate-pulse rounded bg-zinc-200" />
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-zinc-200" />
                <span className="h-3 w-10 animate-pulse rounded bg-zinc-100" />
                <span className="h-3 w-4 animate-pulse rounded bg-zinc-200" />
              </span>
            ))}
          </div>
        </div>
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
