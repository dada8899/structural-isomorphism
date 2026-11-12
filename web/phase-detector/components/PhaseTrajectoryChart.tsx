"use client";

// 2026-05-23 PD-EWS rewrite.
//
// PhaseTrajectoryChart now renders the *real* critical-slowing-down
// indicators computed by `v4/product/d1_phase_detector/ews.py`:
//
//   * rolling lag-1 autocorrelation (AR1) of daily log-returns
//   * rolling variance of those returns
//
// Both series are plotted on a dual-y-axis (left=AR1 in [-1,1], right=var
// normalised to its own observed max). When both rise together over the
// trailing window, the underlying system is showing the textbook CSD
// fingerprint — that is what the criticality score is summarising.
//
// Honest fallback: if no EWS data is provided (`ewsDetail` is null), we
// render an inline "数据准备中" notice with an explanatory link, rather
// than the old PRNG-fake trajectory.

import { useEffect, useMemo, useRef, useState } from "react";
import type { EwsResultFull } from "@/lib/types";
import { useTheme } from "./ThemeProvider";

interface Props {
  /** EWS payload (full per-ticker form). Pass null while loading or if the
   *  ticker hasn't been ingested yet — we'll render a meaningful empty state. */
  ewsDetail: EwsResultFull | null;
  /** Optional ticker fallback for the empty state copy. */
  ticker?: string;
  className?: string;
}

const W = 640;
const H = 220;
const PAD = { top: 16, right: 40, bottom: 32, left: 44 };

// Light tint bands for the AR1 axis ranges that map to "warning zones".
// AR1 > 0.5 means strong persistence which, combined with rising variance,
// is the CSD red flag.
const BAND_DEFS: Array<{ from: number; to: number; fill: string; label: string }> = [
  { from: -1, to: 0.3, fill: "rgba(16, 185, 129, 0.08)", label: "稳态" },
  { from: 0.3, to: 0.6, fill: "rgba(245, 158, 11, 0.10)", label: "接近临界" },
  { from: 0.6, to: 1, fill: "rgba(239, 68, 68, 0.10)", label: "临界点上" },
];

function fmtDate(iso: string): string {
  // expect yyyy-mm-dd
  return iso.slice(0, 7);
}

function fmtTau(tau: number | null): string {
  if (tau == null) return "—";
  return tau.toFixed(2);
}

export function PhaseTrajectoryChart({ ewsDetail, ticker, className }: Props) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";
  const ar1Color = isDark ? "#FAFAFA" : "#18181B";
  const varColor = isDark ? "#A78BFA" : "#3B82F6";
  const chartGrid = isDark ? "#27272A" : "#E4E4E7";
  const axisLabelColor = isDark ? "#A1A1AA" : "#71717A";
  const tooltipBg = isDark ? "#18181B" : "#FFFFFF";
  const tooltipBorder = isDark ? "#27272A" : "#E4E4E7";
  const tooltipFg = isDark ? "#FAFAFA" : "#18181B";
  const tooltipFgMuted = isDark ? "#D4D4D8" : "#52525B";

  // All hooks must run on every render (Rules of Hooks). We do the
  // empty-state check AFTER hooks fire, returning JSX from a single
  // branch at the end.
  const points = useMemo(() => {
    const ar1 = ewsDetail?.ar1;
    const v = ewsDetail?.var;
    if (!ar1 || !v) return [];
    const aVals = ar1.values ?? [];
    const vVals = v.values ?? [];
    const dates = ar1.dates ?? [];
    const n = Math.min(aVals.length, vVals.length, dates.length);
    const out: { date: string; ar1: number | null; var: number | null }[] = [];
    for (let i = 0; i < n; i += 1) {
      if (aVals[i] == null && vVals[i] == null) continue;
      out.push({ date: dates[i], ar1: aVals[i], var: vVals[i] });
    }
    return out;
  }, [ewsDetail]);

  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [mounted, setMounted] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  // --- empty / degenerate states ---
  if (!ewsDetail || !ewsDetail.ar1 || !ewsDetail.ar1.dates?.length) {
    return (
      <div className={className} data-testid="phase-trajectory-empty">
        <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50/60 p-6 text-sm text-zinc-600">
          <p className="mb-2 font-medium text-zinc-800">
            {ticker ?? "该公司"} 的 EWS 时序数据准备中
          </p>
          <p>
            当前研究预览使用 demo provenance；数据准备完成后即可查看。
            <strong className="text-zinc-900"> 图表不会把演示数据标记为真实行情。</strong>
          </p>
        </div>
      </div>
    );
  }

  if (points.length < 2) {
    return (
      <div className={className} data-testid="phase-trajectory-empty">
        <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50/60 p-6 text-sm text-zinc-600">
          样本不足以画出趋势（n={ewsDetail.n_returns}）。
        </div>
      </div>
    );
  }

  const ar1Series = ewsDetail.ar1;
  const varSeries = ewsDetail.var;

  // y-axis ranges
  const varMax = Math.max(
    ...points.map((p) => (p.var == null ? 0 : Math.abs(p.var))),
  ) || 1;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const xStep = innerW / Math.max(1, points.length - 1);
  const xScale = (i: number) => PAD.left + i * xStep;

  // AR1 axis: [-0.4, 1.0] gives good range for daily returns AR(1)
  const AR1_MIN = -0.4;
  const AR1_MAX = 1.0;
  const yAr1 = (v: number) =>
    PAD.top + (1 - (Math.max(AR1_MIN, Math.min(AR1_MAX, v)) - AR1_MIN) / (AR1_MAX - AR1_MIN)) * innerH;
  const yVar = (v: number) =>
    PAD.top + (1 - Math.max(0, Math.min(varMax, v)) / varMax) * innerH;

  const ar1Path = points
    .map((p, i) =>
      p.ar1 == null ? "" : `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yAr1(p.ar1).toFixed(1)}`,
    )
    .filter(Boolean)
    .join(" ");

  const varPath = points
    .map((p, i) =>
      p.var == null ? "" : `${i === 0 ? "M" : "L"}${xScale(i).toFixed(1)},${yVar(p.var).toFixed(1)}`,
    )
    .filter(Boolean)
    .join(" ");

  const idxFromEvent = (e: { clientX: number }) => {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const xRel = ((e.clientX - rect.left) / rect.width) * W - PAD.left;
    const idx = Math.round(xRel / xStep);
    if (idx >= 0 && idx < points.length) return idx;
    return null;
  };

  const hover = hoverIdx == null ? null : points[hoverIdx];

  // Provenance & summary line
  const liveStr =
    ewsDetail.price_provenance === "live" ? "真实价格" : "演示数据";

  return (
    <div
      className={className}
      data-testid="phase-trajectory-chart"
      style={{ width: "100%", maxWidth: W }}
    >
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-zinc-900">
          临界减速指标（trailing {points.length} 个交易日 · {liveStr}）
        </h3>
        <div className="flex items-center gap-4 text-[11px] text-zinc-500">
          <span className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-[2px] w-4" style={{ background: ar1Color }} />
            AR1 τ={fmtTau(ar1Series.tau)}
          </span>
          <span className="inline-flex items-center gap-1">
            <span aria-hidden className="inline-block h-[2px] w-4" style={{ background: varColor }} />
            方差 τ={fmtTau(varSeries.tau)}
          </span>
        </div>
      </div>
      <div
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
          aria-label={`${ewsDetail.ticker} 临界减速 (AR1 + 方差) 趋势`}
          style={{
            display: "block",
            touchAction: "none",
            userSelect: "none",
            cursor: mounted ? "crosshair" : "default",
          }}
          onPointerMove={mounted ? (e) => setHoverIdx(idxFromEvent(e)) : undefined}
          onPointerLeave={mounted ? () => setHoverIdx(null) : undefined}
        >
          {/* AR1 axis bands */}
          {BAND_DEFS.map((b, i) => (
            <rect
              key={i}
              x={PAD.left}
              y={yAr1(b.to)}
              width={innerW}
              height={Math.abs(yAr1(b.from) - yAr1(b.to))}
              fill={b.fill}
            />
          ))}

          {/* AR1 zero & 0.5 threshold lines */}
          {[0, 0.5].map((t) => (
            <line
              key={t}
              x1={PAD.left}
              x2={PAD.left + innerW}
              y1={yAr1(t)}
              y2={yAr1(t)}
              stroke={chartGrid}
              strokeDasharray="3 3"
              strokeWidth={1}
            />
          ))}

          {/* Left axis (AR1) labels */}
          {[-0.4, 0, 0.5, 1].map((v) => (
            <text
              key={`a${v}`}
              x={PAD.left - 6}
              y={yAr1(v) + 3}
              fontSize={10}
              fill={axisLabelColor}
              textAnchor="end"
            >
              {v.toFixed(1)}
            </text>
          ))}

          {/* Right axis (var) labels */}
          {[0, varMax / 2, varMax].map((v, i) => (
            <text
              key={`v${i}`}
              x={W - PAD.right + 6}
              y={yVar(v) + 3}
              fontSize={10}
              fill={axisLabelColor}
              textAnchor="start"
            >
              {v.toExponential(1)}
            </text>
          ))}

          {/* X labels every Nth tick */}
          {points.map((p, i) => {
            const stride = Math.max(1, Math.floor(points.length / 6));
            if (i % stride !== 0) return null;
            return (
              <text
                key={`x${i}`}
                x={xScale(i)}
                y={H - PAD.bottom + 14}
                fontSize={10}
                fill={axisLabelColor}
                textAnchor="middle"
              >
                {fmtDate(p.date)}
              </text>
            );
          })}

          {/* var line */}
          <path d={varPath} fill="none" stroke={varColor} strokeWidth={1.5} strokeOpacity={0.85} />
          {/* AR1 line */}
          <path d={ar1Path} fill="none" stroke={ar1Color} strokeWidth={1.75} />

          {/* Hover crosshair */}
          {hoverIdx != null && hover && (
            <line
              x1={xScale(hoverIdx)}
              x2={xScale(hoverIdx)}
              y1={PAD.top}
              y2={H - PAD.bottom}
              stroke={varColor}
              strokeDasharray="2 2"
              strokeWidth={1}
            />
          )}
        </svg>

        {hover && hoverIdx != null && (
          <div
            role="tooltip"
            style={{
              position: "absolute",
              left: `${(xScale(hoverIdx) / W) * 100}%`,
              top: 0,
              transform: xScale(hoverIdx) / W > 0.6 ? "translate(-100%, 0)" : "translate(8px, 0)",
              pointerEvents: "none",
              background: tooltipBg,
              border: `1px solid ${tooltipBorder}`,
              padding: "6px 10px",
              fontSize: 12,
              borderRadius: 6,
              minWidth: 140,
              zIndex: 5,
              boxShadow: isDark ? "0 4px 12px rgba(0,0,0,0.6)" : "0 4px 12px rgba(0,0,0,0.08)",
            }}
          >
            <div style={{ fontWeight: 600, color: tooltipFg }}>{fmtDate(hover.date)}</div>
            <div style={{ color: tooltipFgMuted, fontSize: 11, marginTop: 2 }}>
              AR1: <strong>{hover.ar1 == null ? "—" : hover.ar1.toFixed(3)}</strong>
            </div>
            <div style={{ color: tooltipFgMuted, fontSize: 11 }}>
              方差: <strong>{hover.var == null ? "—" : hover.var.toExponential(2)}</strong>
            </div>
          </div>
        )}
      </div>
      <p className="mt-2 hidden text-[11px] leading-relaxed text-zinc-500 sm:block">
        左轴：滑窗 lag-1 自相关（AR1）。右轴：滑窗方差。两个指标
        <strong className="text-zinc-700"> 同时单调上行 </strong>
        是 Scheffer/Dakos &ldquo;临界减速&rdquo;的标志。τ 是 Kendall 趋势检验值
        （取了 stride 子采样去重叠的伪显著），趋势越强 |τ| 越接近 1。
      </p>
    </div>
  );
}

export default PhaseTrajectoryChart;
