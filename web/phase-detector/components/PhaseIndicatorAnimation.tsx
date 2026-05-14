"use client";

// W10-C alpha-screener landing: CSS-only animated 5-state phase indicator.
//
// Subtle cycle through the 5 critical-point states. No JS animation loop —
// pure CSS @keyframes so it pauses gracefully in reduced-motion + costs ~0
// LCP weight. Sits under the hero CTAs as visual rhythm without imagery.
//
// States (matches v0.2 BE taxonomy):
//   far_from_critical    → emerald (stable)
//   approaching_critical → amber   (warning)
//   at_critical          → red     (urgent)
//   post_critical_transition → ink (already flipped)
//   unknown              → zinc    (no signal)
//
// Reduced motion: `prefers-reduced-motion: reduce` freezes the cycle on
// the first state so the indicator stays visible but quiet.

import { useId } from "react";

const STATES = [
  { color: "#059669", label: "稳态", icon: "●" },
  { color: "#D97706", label: "临界附近", icon: "▲" },
  { color: "#DC2626", label: "临界点", icon: "◆" },
  { color: "#18181B", label: "已翻转", icon: "✕" },
  { color: "#71717A", label: "未知", icon: "○" },
];

export function PhaseIndicatorAnimation() {
  const uid = useId();
  const anim = `phase-cycle-${uid.replace(/:/g, "")}`;
  return (
    <div
      className="flex items-center justify-center gap-6 sm:gap-10"
      aria-hidden="true"
    >
      {STATES.map((s, i) => (
        <div
          key={s.label}
          className="flex flex-col items-center"
          style={{
            // Each dot's pulse phase-shifts by 0.6s so the row reads as a
            // travelling wave (left → right → loop).
            animation: `${anim} 3s ease-in-out ${i * 0.6}s infinite`,
          }}
        >
          <span
            className="text-2xl leading-none sm:text-3xl"
            style={{ color: s.color }}
          >
            {s.icon}
          </span>
          <span className="mt-2 text-[10px] uppercase tracking-wider text-zinc-400 sm:text-[11px]">
            {s.label}
          </span>
        </div>
      ))}
      {/* Inline keyframes so each instance is independent. The opacity
          dip is small (1 → 0.35 → 1) to avoid flashy motion per CLAUDE.md. */}
      <style jsx>{`
        @keyframes ${anim} {
          0%, 100% { opacity: 1; transform: translateY(0); }
          50% { opacity: 0.35; transform: translateY(-2px); }
        }
        @media (prefers-reduced-motion: reduce) {
          div[style*="animation"] { animation: none !important; }
        }
      `}</style>
    </div>
  );
}
