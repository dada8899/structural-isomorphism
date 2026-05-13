// Human-friendly labels and visual mappings for taxonomy values.
// W6-B: added icons + aria-labels for WCAG 1.4.1 (color is not the only signal).

import type { CriticalPointState, DynamicsFamily } from "./types";

export const DYNAMICS_LABEL: Record<DynamicsFamily, string> = {
  soc: "SOC (self-organized criticality)",
  preferential_attachment: "Preferential attachment",
  fold: "Fold bifurcation",
  hysteresis: "Hysteresis",
  other: "Other",
};

// One-line layperson explanations of each dynamics family.
// Used on /methodology and as tooltip hints.
export const DYNAMICS_EXPLAIN: Record<DynamicsFamily, string> = {
  soc: "系统通过缓慢积累压力 + 突发释放达到临界状态。事件大小服从幂律分布（地震、神经雪崩）。",
  preferential_attachment:
    "强者愈强：节点越受关注越容易获得新连接，最终形成长尾（社交网络、引用图）。",
  fold: "缓慢参数变化下系统突然跳到另一个稳态。失去稳态后不可自行回到原态（湖泊富营养化、生态崩溃）。",
  hysteresis:
    "系统的状态依赖于历史路径。同一参数下可能停在不同状态（交通拥堵 / 自由流、市场牛熊）。",
  other: "其他尚未归类到上述四大族的动力学结构。",
};

export const CPS_LABEL: Record<CriticalPointState, string> = {
  subcritical: "稳定",
  near_critical: "临近",
  supercritical: "过临",
  tipped: "已变",
};

export const CPS_LABEL_EN: Record<CriticalPointState, string> = {
  subcritical: "Subcritical",
  near_critical: "Near critical",
  supercritical: "Supercritical",
  tipped: "Tipped",
};

// Layperson explanations for /methodology and tooltip.
export const CPS_EXPLAIN: Record<CriticalPointState, string> = {
  subcritical: "远离临界点。系统在稳态运行，没有放大反馈。",
  near_critical:
    "接近临界点。小扰动开始被放大，波动率上升，但还没跳到新稳态。",
  supercritical:
    "已经跨过临界点但还没完成切换。系统正在加速向新稳态滑落。",
  tipped: "已经完成相变。回到原稳态需要外部干预（reverse hysteresis）。",
};

// W6-B: WCAG 1.4.1 — icon symbols for non-color encoding.
// Each state has a unique geometric shape, visible regardless of color perception.
export const CPS_ICON: Record<CriticalPointState, string> = {
  subcritical: "●", // filled circle = stable
  near_critical: "▲", // up triangle = warning
  supercritical: "◆", // diamond = critical
  tipped: "✕", // cross = already changed
};

export const CPS_ARIA_LABEL: Record<CriticalPointState, string> = {
  subcritical: "稳定状态：远离临界点",
  near_critical: "临近临界：接近相变",
  supercritical: "过临状态：跨过临界点",
  tipped: "已变：完成相变",
};

// Tailwind-classes map for badges. Use bg + text colors directly so colors
// are statically discoverable by tailwind JIT.
// W6-B: aligned to design system tokens (emerald-600/amber-600/red-600/zinc-900).
export const CPS_BADGE: Record<CriticalPointState, string> = {
  subcritical: "bg-emerald-600 text-white",
  near_critical: "bg-amber-600 text-white",
  supercritical: "bg-red-600 text-white",
  tipped: "bg-zinc-900 text-white",
};

export const CPS_DOT: Record<CriticalPointState, string> = {
  subcritical: "bg-emerald-600",
  near_critical: "bg-amber-600",
  supercritical: "bg-red-600",
  tipped: "bg-zinc-900",
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
