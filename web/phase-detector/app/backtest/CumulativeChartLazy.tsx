"use client";

// W13-B (2026-05-15): client-side dynamic import of recharts-based
// CumulativeChart. The /backtest page is a server component, so we wrap
// the dynamic() call in a "use client" boundary. Recharts ships ~80 KB
// gzipped; lazy-loading it drops the backtest First Load JS budget
// below the 200 KB threshold (perf-budget.json).
//
// We render a fixed-height (360px) skeleton placeholder while the chunk
// is in flight so the layout doesn't shift on hydration (CLS protection).

import dynamic from "next/dynamic";

type Row = {
  snapshot_date: string;
  cum_nc_ret: number;
  cum_other_ret: number;
  cum_bench_ret?: number;
};

const CumulativeChart = dynamic(
  () => import("./CumulativeChart").then((m) => ({ default: m.CumulativeChart })),
  {
    ssr: false,
    loading: () => (
      <div
        className="h-[360px] w-full rounded-md border border-zinc-200 bg-zinc-50/50"
        role="status"
        aria-label="加载图表中"
      />
    ),
  },
);

export function CumulativeChartLazy({ rows }: { rows: Row[] }) {
  return <CumulativeChart rows={rows} />;
}
