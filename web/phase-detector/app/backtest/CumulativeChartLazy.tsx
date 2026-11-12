"use client";

// W13-B (2026-05-15): client-side dynamic import of recharts-based
// CumulativeChart. The /backtest page is a server component, so we wrap
// the dynamic() call in a "use client" boundary. Recharts ships ~80 KB
// gzipped; lazy-loading it drops the backtest First Load JS budget
// below the 200 KB threshold (perf-budget.json).
//
// We render a fixed-height (360px) skeleton placeholder while the chunk
// is in flight so the layout doesn't shift on hydration (CLS protection).
//
// SESSION-28 N9 perf: previous version still triggered recharts chunk
// fetch + parse immediately on hydration (next/dynamic eagerly loads on
// mount), which dominated /backtest mobile TBT (339ms > 200ms budget).
// The chart sits well below the fold (after hero + 8-card stat grid +
// verdict block), so deferring the dynamic import until the container
// is near the viewport removes the long parse task from the initial
// main-thread work without changing visual behavior on scroll.

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

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

// SESSION-28 N9 perf: gate recharts mount on IntersectionObserver so the
// recharts chunk parse never lands inside the initial TBT window. Falls
// back to immediate mount when IO is unavailable (very old browsers,
// SSR-disabled environments) so the chart still works.
export function CumulativeChartLazy({ rows }: { rows: Row[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [shouldMount, setShouldMount] = useState(false);

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") {
      setShouldMount(true);
      return;
    }
    const node = containerRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setShouldMount(true);
            observer.disconnect();
            break;
          }
        }
      },
      // 600px rootMargin = start fetching when user is ~one fold above
      // the chart so it's ready by the time they scroll to it.
      { rootMargin: "600px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} className="h-[360px] w-full">
      {shouldMount ? (
        <CumulativeChart rows={rows} />
      ) : (
        <div
          className="h-[360px] w-full rounded-md border border-zinc-200 bg-zinc-50/50"
          role="status"
          aria-label="加载图表中"
        />
      )}
    </div>
  );
}
