// Human-friendly labels and visual mappings for taxonomy values.

import type { CriticalPointState, DynamicsFamily } from "./types";

export const DYNAMICS_LABEL: Record<DynamicsFamily, string> = {
  soc: "SOC (self-organized criticality)",
  preferential_attachment: "Preferential attachment",
  fold: "Fold bifurcation",
  hysteresis: "Hysteresis",
  other: "Other",
};

export const CPS_LABEL: Record<CriticalPointState, string> = {
  subcritical: "Subcritical",
  near_critical: "Near critical",
  supercritical: "Supercritical",
  tipped: "Tipped",
};

// Tailwind-classes map for badges. Use bg + text colors directly so colors
// are statically discoverable by tailwind JIT.
export const CPS_BADGE: Record<CriticalPointState, string> = {
  subcritical: "bg-emerald-500 text-white",
  near_critical: "bg-amber-500 text-white",
  supercritical: "bg-red-500 text-white",
  tipped: "bg-gray-800 text-white",
};

export const CPS_DOT: Record<CriticalPointState, string> = {
  subcritical: "bg-emerald-500",
  near_critical: "bg-amber-500",
  supercritical: "bg-red-500",
  tipped: "bg-gray-800",
};

export const DYNAMICS_FAMILY_OPTIONS: DynamicsFamily[] = [
  "soc",
  "preferential_attachment",
  "fold",
  "hysteresis",
  "other",
];

export const CPS_OPTIONS: CriticalPointState[] = [
  "subcritical",
  "near_critical",
  "supercritical",
  "tipped",
];
