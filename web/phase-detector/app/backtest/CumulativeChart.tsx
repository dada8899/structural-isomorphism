"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// Wave 2 (2026-05-14): two-series cumulative return chart on /backtest.
// Inputs are pre-parsed rows from /api/backtest-cumulative.

type Row = {
  snapshot_date: string;
  cum_nc_ret: number;
  cum_other_ret: number;
};

export function CumulativeChart({ rows }: { rows: Row[] }) {
  // Down-sample x-axis tick density: show year boundaries only.
  const yearTicks = rows
    .map((r) => r.snapshot_date)
    .filter((d) => d.endsWith("-01-01") || d.endsWith("-06-01"));

  return (
    <div className="h-[360px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={rows}
          margin={{ top: 16, right: 24, bottom: 24, left: 8 }}
        >
          <CartesianGrid stroke="#E4E4E7" strokeDasharray="3 3" />
          <XAxis
            dataKey="snapshot_date"
            ticks={yearTicks}
            tickFormatter={(v: string) => v.slice(0, 7)}
            tick={{ fill: "#52525B", fontSize: 12 }}
            stroke="#A1A1AA"
          />
          <YAxis
            tickFormatter={(v: number) => v.toFixed(1)}
            tick={{ fill: "#52525B", fontSize: 12 }}
            stroke="#A1A1AA"
            label={{
              value: "cumulative return (sum of monthly group means)",
              angle: -90,
              position: "insideLeft",
              fill: "#71717A",
              fontSize: 11,
              dy: 100,
            }}
          />
          <Tooltip
            contentStyle={{
              background: "white",
              border: "1px solid #E4E4E7",
              borderRadius: 6,
              fontSize: 12,
            }}
            formatter={(value, name) => [
              typeof value === "number" ? value.toFixed(3) : String(value),
              String(name),
            ]}
            labelFormatter={(label) => `snapshot ${label}`}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            iconType="line"
          />
          <Line
            type="monotone"
            dataKey="cum_nc_ret"
            name="near_critical group"
            stroke="#DC2626"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="cum_other_ret"
            name="other group"
            stroke="#2563EB"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
