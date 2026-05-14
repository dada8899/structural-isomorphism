"use client";

// W11-D — SparkLine.
//
// Tiny inline trajectory shown inside CompanyCard / list rows. Upgrades
// over the legacy CSS-only spark in ExploreCardsGrid:
//   * IntersectionObserver — line draws via stroke-dashoffset animation
//     only when the card scrolls into view. Off-screen cards stay static
//     so the screener feels smooth even with 50+ cards.
//   * Phase-band segment coloring — each segment of the line is colored
//     by the (synthesized) phase at that timestamp so the eye sees the
//     trajectory bend through red / amber / green zones.
//   * Hover tooltip — month + value + phase, like the big chart but
//     compact.
//   * Respects prefers-reduced-motion (no transition).
//
// Data is synthesized deterministically from the ticker until BE ships
// /api/company/<t>/spark. Phase-band coloring uses the same thresholds
// as PhaseTrajectoryChart (0.33 / 0.66) so the visual vocabulary is
// consistent across the site.

import { useEffect, useMemo, useRef, useState } from "react";
import type { CriticalPointState } from "@/lib/types";

export interface SparkLineProps {
  ticker: string;
  // Current phase — used as the bias for the synthesized series so the
  // trace ends in the visually correct zone. When BE ships real series
  // we drop the synthesis path and accept points: number[] directly.
  currentPhase?: CriticalPointState;
  width?: number;
  height?: number;
  months?: number;
  className?: string;
}

const PHASE_BIAS: Record<CriticalPointState, number> = {
  far_from_critical: 0.18,
  approaching_critical: 0.55,
  at_critical: 0.82,
  post_critical_transition: 0.68,
  unknown: 0.42,
};

const BAND_STROKE: Array<{ from: number; to: number; color: string; label: string }> = [
  { from: 0, to: 0.33, color: "#10B981", label: "稳态" },
  { from: 0.33, to: 0.66, color: "#F59E0B", label: "接近临界" },
  { from: 0.66, to: 1.01, color: "#EF4444", label: "临界点上" },
];

function hash32(s: string): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return h >>> 0;
}

function makeRng(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) | 0;
    return ((s >>> 0) % 1000000) / 1000000;
  };
}

interface Pt {
  v: number;
  monthOffset: number; // 0 = oldest, N-1 = current
}

function buildSeries(ticker: string, phase: CriticalPointState, months: number): Pt[] {
  const rng = makeRng(hash32(ticker + ":" + phase));
  const target = PHASE_BIAS[phase] ?? 0.4;
  let prev = Math.max(0.05, Math.min(0.95, target - 0.35 - rng() * 0.1));
  const out: Pt[] = [];
  for (let i = 0; i < months; i += 1) {
    const t = i / Math.max(1, months - 1);
    const drift = (target - prev) * 0.2;
    const noise = (rng() - 0.5) * 0.08;
    prev = Math.max(0, Math.min(1.02, prev + drift + noise + t * 0.012));
    out.push({ v: prev, monthOffset: i });
  }
  return out;
}

function bandFor(v: number): { color: string; label: string } {
  for (const b of BAND_STROKE) {
    if (v >= b.from && v < b.to) return { color: b.color, label: b.label };
  }
  return { color: "#71717A", label: "未知" };
}

function fmtMonthLabel(offsetFromOldest: number, months: number): string {
  const now = new Date();
  const ago = months - 1 - offsetFromOldest;
  const d = new Date(now.getFullYear(), now.getMonth() - ago, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function SparkLine({
  ticker,
  currentPhase = "unknown",
  width = 96,
  height = 32,
  months = 12,
  className,
}: SparkLineProps) {
  const series = useMemo(
    () => buildSeries(ticker, currentPhase, months),
    [ticker, currentPhase, months],
  );

  const rootRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState<number | null>(null);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && window.matchMedia) {
      const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
      setReduceMotion(mql.matches);
    }
  }, []);

  useEffect(() => {
    if (!rootRef.current) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true);
          }
        });
      },
      { threshold: 0.2, rootMargin: "40px" },
    );
    observer.observe(rootRef.current);
    return () => observer.disconnect();
  }, []);

  const padX = 2;
  const padY = 3;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const step = innerW / Math.max(1, series.length - 1);

  // Build segment list — each segment is colored by the phase band of its
  // midpoint value.
  const segments = useMemo(() => {
    const segs: Array<{
      d: string;
      color: string;
      label: string;
      idxA: number;
      idxB: number;
    }> = [];
    for (let i = 0; i < series.length - 1; i += 1) {
      const a = series[i];
      const b = series[i + 1];
      const ax = padX + i * step;
      const ay = padY + (1 - a.v) * innerH;
      const bx = padX + (i + 1) * step;
      const by = padY + (1 - b.v) * innerH;
      const mid = (a.v + b.v) / 2;
      const { color, label } = bandFor(mid);
      segs.push({
        d: `M${ax.toFixed(1)},${ay.toFixed(1)}L${bx.toFixed(1)},${by.toFixed(1)}`,
        color,
        label,
        idxA: i,
        idxB: i + 1,
      });
    }
    return segs;
  }, [series, padX, padY, step, innerH]);

  const totalLen = useMemo(() => {
    let len = 0;
    for (let i = 0; i < series.length - 1; i += 1) {
      const dx = step;
      const dy = ((series[i].v - series[i + 1].v) * innerH);
      len += Math.sqrt(dx * dx + dy * dy);
    }
    return len;
  }, [series, step, innerH]);

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!rootRef.current) return;
    const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const xRel = ((e.clientX - rect.left) / rect.width) * width - padX;
    const idx = Math.max(0, Math.min(series.length - 1, Math.round(xRel / step)));
    setHovered(idx);
  };

  const hoverPt = hovered !== null ? series[hovered] : null;
  const hoverBand = hoverPt ? bandFor(hoverPt.v) : null;

  return (
    <div
      ref={rootRef}
      className={className}
      data-testid="sparkline"
      data-ticker={ticker}
      data-visible={visible ? "true" : "false"}
      style={{ position: "relative", display: "inline-block", width, height }}
    >
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        role="img"
        aria-label={`${ticker} 近 ${months} 月趋势`}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHovered(null)}
        style={{ display: "block", overflow: "visible" }}
      >
        {/* Faint background baseline */}
        <line
          x1={padX}
          x2={padX + innerW}
          y1={padY + innerH * 0.5}
          y2={padY + innerH * 0.5}
          stroke="#E4E4E7"
          strokeWidth={0.5}
          strokeDasharray="2 2"
        />

        <g
          style={{
            strokeDasharray: reduceMotion ? "none" : totalLen.toFixed(1),
            strokeDashoffset: visible || reduceMotion ? 0 : totalLen.toFixed(1),
            transition: reduceMotion
              ? "none"
              : "stroke-dashoffset 800ms cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        >
          {segments.map((s, i) => (
            <path
              key={i}
              d={s.d}
              fill="none"
              stroke={s.color}
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
        </g>

        {hovered !== null && hoverPt && (
          <circle
            cx={padX + hovered * step}
            cy={padY + (1 - hoverPt.v) * innerH}
            r={2.5}
            fill={hoverBand?.color ?? "#18181B"}
            stroke="white"
            strokeWidth={1}
          />
        )}
      </svg>

      {hovered !== null && hoverPt && hoverBand && (
        <div
          data-testid="sparkline-tooltip"
          role="tooltip"
          style={{
            position: "absolute",
            bottom: height + 4,
            left: Math.max(0, Math.min(width - 100, padX + hovered * step - 50)),
            background: "white",
            border: "1px solid #E4E4E7",
            boxShadow: "0 2px 6px rgba(0,0,0,0.08)",
            padding: "4px 6px",
            fontSize: 10,
            borderRadius: 4,
            whiteSpace: "nowrap",
            zIndex: 10,
            pointerEvents: "none",
          }}
        >
          <span style={{ fontWeight: 600, color: "#18181B" }}>
            {fmtMonthLabel(hovered, months)}
          </span>
          <span style={{ color: "#52525B" }}>
            {" · "}
            {hoverPt.v.toFixed(2)}
          </span>
          <span style={{ color: hoverBand.color, marginLeft: 4 }}>
            {hoverBand.label}
          </span>
        </div>
      )}
    </div>
  );
}

export default SparkLine;
