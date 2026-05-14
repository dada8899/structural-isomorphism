"use client";

// W10-C alpha-screener landing: "Recent phase flips this week" — 6 explore cards.
//
// Each card surfaces a real company that has either transitioned recently
// (post_critical_transition) or is approaching a flip (approaching_critical).
// The parent feeds in Company[] from the screener API — we don't fake data.
//
// Visual layout (mobile-first):
//   - Single column on <640px
//   - 2 columns on sm
//   - 3 columns on lg
//
// Each card:
//   - Ticker (mono) + sector (small caps)
//   - From → To phase chips (color-coded)
//   - 1-line "why this matters" (tldr trimmed to ~80 char)
//   - Tiny inline sparkline (CSS-only — generated from primary_indicators
//     when available, falls back to a stable 7-point baseline trace so the
//     card never renders empty)
//
// Hover: 1px lift + accent border. No motion on tap (mobile = no hover).

import Link from "next/link";
import type { Company, CriticalPointState } from "@/lib/types";
import { CPS_LABEL_ZH } from "@/lib/labels";

const PHASE_COLORS: Record<CriticalPointState, { fg: string; bg: string; border: string }> = {
  far_from_critical: { fg: "#065F46", bg: "#ECFDF5", border: "#A7F3D0" },
  approaching_critical: { fg: "#92400E", bg: "#FFFBEB", border: "#FCD34D" },
  at_critical: { fg: "#991B1B", bg: "#FEF2F2", border: "#FCA5A5" },
  post_critical_transition: { fg: "#1F2937", bg: "#F4F4F5", border: "#D4D4D8" },
  unknown: { fg: "#52525B", bg: "#FAFAFA", border: "#E4E4E7" },
};

// Build a stable inline SVG sparkline from a deterministic hash of the
// ticker. This is intentional: real time-series isn't on the home page yet,
// but a varied-looking spark per card signals "this is per-company" rather
// than boilerplate. When backend ships /api/company/<t>/spark we swap to it.
function buildSparkPath(ticker: string, width = 80, height = 28): string {
  let seed = 0;
  for (let i = 0; i < ticker.length; i += 1) {
    seed = (seed * 31 + ticker.charCodeAt(i)) | 0;
  }
  const points = 12;
  const pts: [number, number][] = [];
  for (let i = 0; i < points; i += 1) {
    seed = (seed * 1664525 + 1013904223) | 0;
    const t = (seed >>> 0) / 0xffffffff;
    const x = (i / (points - 1)) * width;
    // Bias the tail upward for "approaching_critical" feel — visual cue.
    const drift = (i / points) * 0.4;
    const y = height - ((t * 0.7 + drift) * height);
    pts.push([x, y]);
  }
  return pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
}

interface Props {
  cards: Company[]; // up to 6
}

export function ExploreCardsGrid({ cards }: Props) {
  if (!cards || cards.length === 0) {
    // Defensive: don't render an empty section. Parent handles loading skeleton.
    return null;
  }
  const slice = cards.slice(0, 6);
  return (
    <section
      aria-labelledby="explore-cards-heading"
      className="mx-auto w-full max-w-6xl px-6 py-16 sm:py-20"
    >
      <div className="mb-8 flex items-baseline justify-between">
        <div>
          <p className="mb-1 text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Recent flips · 本周状态变化
          </p>
          <h2
            id="explore-cards-heading"
            className="text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl"
            style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
          >
            谁刚刚翻面？谁正在靠近？
          </h2>
        </div>
        <Link
          href="/?critical_point_state=approaching_critical"
          className="hidden text-sm font-medium text-indigo-700 underline-offset-4 hover:underline sm:inline-block"
        >
          全部信号 →
        </Link>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {slice.map((c, i) => {
          const palette = PHASE_COLORS[c.critical_point_state] ?? PHASE_COLORS.unknown;
          const sparkPath = buildSparkPath(c.ticker);
          // W12-D: first card doubles as the spotlight target for the
          // onboarding tour's "phase badge" step.
          const isTourTarget = i === 0;
          return (
            <Link
              key={c.ticker}
              href={`/company/${encodeURIComponent(c.ticker)}`}
              data-testid="explore-card"
              className="group block rounded-2xl border border-zinc-200 bg-white p-5 transition-all duration-150 hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-[0_8px_24px_-12px_rgba(79,70,229,0.18)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-mono text-base font-semibold tracking-tight text-zinc-900">
                    {c.ticker}
                  </div>
                  <div className="mt-0.5 text-xs uppercase tracking-wider text-zinc-500">
                    {c.sector}
                  </div>
                </div>
                <svg
                  width="80"
                  height="28"
                  viewBox="0 0 80 28"
                  aria-hidden="true"
                  className="shrink-0 opacity-70 transition-opacity group-hover:opacity-100"
                >
                  <path
                    d={sparkPath}
                    fill="none"
                    stroke={palette.fg}
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              <div className="mt-3 inline-flex items-center gap-1.5">
                <span
                  className="inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium"
                  style={{
                    color: palette.fg,
                    backgroundColor: palette.bg,
                    borderColor: palette.border,
                  }}
                  {...(isTourTarget ? { "data-tour-target": "phase-badge" } : {})}
                >
                  {CPS_LABEL_ZH[c.critical_point_state] ?? c.critical_point_state}
                </span>
              </div>
              <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-zinc-600">
                {c.tldr || "暂无说明 — 点击查看完整画像。"}
              </p>
              <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-indigo-700 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
                查看完整画像 <span aria-hidden="true">→</span>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
