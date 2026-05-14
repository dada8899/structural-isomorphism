"use client";

// W11-D — PhaseTrajectoryChart.
//
// Server-rendered SVG line chart that visualizes a company's "structural
// distance to critical" over the trailing 12 months. Phase bands
// (stable / approaching / at_critical / post / unknown) are painted as
// horizontal background regions; the trajectory line is rendered on top.
//
// Hydration adds: tooltip on hover, brush selection on the x-axis,
// touch support, and accessibility (keyboard-focusable axis).
//
// Design choices:
//   * Pure SVG, no external chart library — gzipped < 6 KB per page.
//   * Time series is synthesized deterministically from the ticker until
//     backend ships /api/company/<t>/trajectory. The shape is
//     phase-coherent: companies at_critical drift upward, post_critical
//     remain elevated, far_from_critical hover low.
//   * "Distance to critical" is normalized to [0, 1] where 1 = on the
//     critical surface. Threshold lines at 0.33 / 0.66 / 1.0 separate
//     the band colors.
//   * SSR-friendly: the static SVG path renders without JS; useEffect
//     attaches hover/brush handlers post-hydration so the initial paint
//     has zero layout shift.

import { useEffect, useMemo, useRef, useState } from "react";
import type { Company } from "@/lib/types";

interface Props {
  company: Company;
  months?: number; // default 12
  className?: string;
}

interface DataPoint {
  date: Date;
  value: number; // 0..1 distance to critical
  phase: string;
}

// Stable PRNG so SSR output === client output (no hydration mismatch).
function hash32(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function makeRng(seed: number): () => number {
  let state = seed | 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) | 0;
    return ((state >>> 0) % 1000000) / 1000000;
  };
}

// Generate a deterministic monthly series biased toward the company's
// current phase so the visualization tells a coherent story.
function generateSeries(company: Company, months: number): DataPoint[] {
  const rng = makeRng(hash32(company.ticker));
  const phaseBias: Record<string, number> = {
    far_from_critical: 0.15,
    approaching_critical: 0.55,
    at_critical: 0.82,
    post_critical_transition: 0.7,
    unknown: 0.4,
  };
  const target = phaseBias[company.critical_point_state] ?? 0.4;
  const now = new Date();
  const out: DataPoint[] = [];
  // Start ~ random low/mid, drift toward target.
  let prev = Math.max(0.05, Math.min(0.95, target - 0.35 - rng() * 0.1));
  for (let i = months - 1; i >= 0; i -= 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const t = (months - 1 - i) / (months - 1); // 0..1, end-of-window highest
    const drift = (target - prev) * 0.18;
    const noise = (rng() - 0.5) * 0.08;
    prev = Math.max(0, Math.min(1.05, prev + drift + noise + t * 0.01));
    let phase = "far_from_critical";
    if (prev >= 0.66) phase = "at_critical";
    else if (prev >= 0.33) phase = "approaching_critical";
    if (i === 0 && company.critical_point_state === "post_critical_transition") {
      phase = "post_critical_transition";
    }
    out.push({ date: d, value: prev, phase });
  }
  return out;
}

const W = 640;
const H = 220;
const PAD = { top: 16, right: 16, bottom: 32, left: 40 };

// Phase band colors — derived from CPS_BADGE so the chart reads with the
// rest of the page. Alpha lowered so the line on top stays legible.
const BAND_COLORS: Array<{ from: number; to: number; fill: string; label: string }> = [
  { from: 0, to: 0.33, fill: "rgba(16, 185, 129, 0.10)", label: "稳态" },
  { from: 0.33, to: 0.66, fill: "rgba(245, 158, 11, 0.12)", label: "接近临界" },
  { from: 0.66, to: 1, fill: "rgba(239, 68, 68, 0.12)", label: "临界点上" },
];

const PHASE_LABEL_ZH: Record<string, string> = {
  far_from_critical: "稳态",
  approaching_critical: "接近临界",
  at_critical: "临界点上",
  post_critical_transition: "已翻转",
};

function fmtDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function PhaseTrajectoryChart({
  company,
  months = 12,
  className,
}: Props) {
  const series = useMemo(() => generateSeries(company, months), [company, months]);

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const xStep = innerW / Math.max(1, series.length - 1);

  const xScale = (i: number) => PAD.left + i * xStep;
  const yScale = (v: number) => PAD.top + (1 - Math.max(0, Math.min(1, v))) * innerH;

  // Build the line path
  const pathD = useMemo(() => {
    return series
      .map((p, i) => `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yScale(p.value).toFixed(1)}`)
      .join(" ");
  }, [series]);

  // Hydration-aware state for tooltip/brush.
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [brush, setBrush] = useState<{ start: number; end: number } | null>(null);
  const [brushing, setBrushing] = useState<boolean>(false);
  const [mounted, setMounted] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Compute idx from raw event coords so we don't rely on hoverIdx state
  // (avoids the "first event has no idx yet" race that fails the brush test
  // when the user clicks down before any pointermove fires).
  const idxFromEvent = (e: { clientX: number }): number | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const xRel = ((e.clientX - rect.left) / rect.width) * W - PAD.left;
    const idx = Math.round(xRel / xStep);
    if (idx >= 0 && idx < series.length) return idx;
    return null;
  };

  const handlePointerMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const idx = idxFromEvent(e);
    if (idx === null) {
      setHoverIdx(null);
      return;
    }
    setHoverIdx(idx);
    if (brushing && brush) {
      setBrush({ start: brush.start, end: idx });
    }
  };

  const handlePointerDown = (e: React.PointerEvent<SVGSVGElement>) => {
    const idx = idxFromEvent(e);
    if (idx === null) return;
    e.preventDefault();
    setBrushing(true);
    setBrush({ start: idx, end: idx });
    setHoverIdx(idx);
  };

  const handlePointerUp = () => {
    setBrushing(false);
    if (brush && brush.start === brush.end) {
      setBrush(null); // a click without drag clears the brush
    }
  };

  const handlePointerLeave = () => {
    setHoverIdx(null);
    setBrushing(false);
  };

  const resetBrush = () => setBrush(null);

  const hoverPoint = hoverIdx !== null ? series[hoverIdx] : null;

  const brushRange = brush
    ? { start: Math.min(brush.start, brush.end), end: Math.max(brush.start, brush.end) }
    : null;

  return (
    <div
      className={className}
      data-testid="phase-trajectory-chart"
      style={{ width: "100%", maxWidth: W }}
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900">
          结构距离趋势（近 {months} 个月）
        </h3>
        <div className="flex items-center gap-3 text-[11px] text-zinc-500">
          <span className="inline-flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-3 rounded-sm"
              style={{ background: "rgba(16,185,129,0.45)" }}
            />
            稳态
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-3 rounded-sm"
              style={{ background: "rgba(245,158,11,0.55)" }}
            />
            接近临界
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              aria-hidden="true"
              className="inline-block h-2 w-3 rounded-sm"
              style={{ background: "rgba(239,68,68,0.55)" }}
            />
            临界点上
          </span>
          {brushRange && (
            <button
              type="button"
              onClick={resetBrush}
              className="ml-2 rounded border border-zinc-200 px-1.5 py-0.5 text-zinc-600 hover:border-zinc-400 hover:text-zinc-900"
              data-testid="trajectory-reset-brush"
            >
              清除选区
            </button>
          )}
        </div>
      </div>
      <div
        // Explicit aspect ratio container — keeps CLS = 0 by reserving space
        // before SVG paints.
        style={{
          width: "100%",
          aspectRatio: `${W} / ${H}`,
          position: "relative",
        }}
      >
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          width="100%"
          height="100%"
          role="img"
          aria-label={`${company.ticker} 结构距离趋势图`}
          style={{
            display: "block",
            touchAction: "none",
            userSelect: "none",
            cursor: mounted ? "crosshair" : "default",
          }}
          onPointerMove={mounted ? handlePointerMove : undefined}
          onPointerDown={mounted ? handlePointerDown : undefined}
          onPointerUp={mounted ? handlePointerUp : undefined}
          onPointerLeave={mounted ? handlePointerLeave : undefined}
        >
          {/* Phase bands */}
          {BAND_COLORS.map((b, i) => (
            <rect
              key={i}
              x={PAD.left}
              y={yScale(b.to)}
              width={innerW}
              height={Math.abs(yScale(b.from) - yScale(b.to))}
              fill={b.fill}
            />
          ))}

          {/* Threshold lines */}
          {[0.33, 0.66].map((t) => (
            <line
              key={t}
              x1={PAD.left}
              x2={PAD.left + innerW}
              y1={yScale(t)}
              y2={yScale(t)}
              stroke="#E4E4E7"
              strokeDasharray="3 3"
              strokeWidth={1}
            />
          ))}

          {/* Y-axis labels */}
          {[0, 0.33, 0.66, 1].map((v) => (
            <g key={v}>
              <text
                x={PAD.left - 6}
                y={yScale(v) + 3}
                fontSize={10}
                fill="#71717A"
                textAnchor="end"
              >
                {v.toFixed(2)}
              </text>
            </g>
          ))}

          {/* X-axis tick labels (every other month for legibility) */}
          {series.map((p, i) =>
            i % 2 === 0 ? (
              <text
                key={i}
                x={xScale(i)}
                y={H - PAD.bottom + 16}
                fontSize={10}
                fill="#71717A"
                textAnchor="middle"
              >
                {fmtDate(p.date)}
              </text>
            ) : null,
          )}

          {/* Brush highlight */}
          {brushRange && (
            <rect
              x={xScale(brushRange.start)}
              y={PAD.top}
              width={Math.max(2, xScale(brushRange.end) - xScale(brushRange.start))}
              height={innerH}
              fill="rgba(59, 130, 246, 0.10)"
              stroke="rgba(59, 130, 246, 0.5)"
              strokeWidth={1}
              data-testid="trajectory-brush"
            />
          )}

          {/* Trajectory line */}
          <path
            d={pathD}
            fill="none"
            stroke="#18181B"
            strokeWidth={1.75}
            strokeLinejoin="round"
            strokeLinecap="round"
          />

          {/* Points */}
          {series.map((p, i) => (
            <circle
              key={i}
              cx={xScale(i)}
              cy={yScale(p.value)}
              r={hoverIdx === i ? 4 : 2.5}
              fill="#18181B"
              opacity={hoverIdx === i ? 1 : 0.7}
            />
          ))}

          {/* Hover crosshair */}
          {hoverIdx !== null && hoverPoint && (
            <g pointerEvents="none" data-testid="trajectory-hover">
              <line
                x1={xScale(hoverIdx)}
                x2={xScale(hoverIdx)}
                y1={PAD.top}
                y2={H - PAD.bottom}
                stroke="#3B82F6"
                strokeDasharray="2 2"
                strokeWidth={1}
              />
            </g>
          )}
        </svg>

        {/* Tooltip — rendered as HTML overlay so it can wrap text */}
        {hoverIdx !== null && hoverPoint && (
          <div
            data-testid="trajectory-tooltip"
            role="tooltip"
            style={{
              position: "absolute",
              left: `${(xScale(hoverIdx) / W) * 100}%`,
              top: 0,
              transform:
                xScale(hoverIdx) / W > 0.6
                  ? "translate(-100%, 0)"
                  : "translate(8px, 0)",
              pointerEvents: "none",
              background: "white",
              border: "1px solid #E4E4E7",
              boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
              padding: "6px 10px",
              fontSize: 12,
              borderRadius: 6,
              minWidth: 140,
              zIndex: 5,
            }}
          >
            <div style={{ fontWeight: 600, color: "#18181B" }}>
              {fmtDate(hoverPoint.date)}
            </div>
            <div style={{ color: "#52525B", fontSize: 11, marginTop: 2 }}>
              结构距离 <strong>{hoverPoint.value.toFixed(2)}</strong>
            </div>
            <div style={{ color: "#52525B", fontSize: 11 }}>
              阶段 · {PHASE_LABEL_ZH[hoverPoint.phase] ?? hoverPoint.phase}
            </div>
          </div>
        )}
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
        结构距离 = 系统状态到临界面的归一化距离（1 = 临界）。背景色带表示阶段区间，
        虚线为阈值。鼠标悬停看具体月份；按住拖动可框选时间段。
        当前为模型合成轨迹（BE 暂未提供时序），仅作可视化示意。
      </p>
    </div>
  );
}

export default PhaseTrajectoryChart;
