// Human-friendly labels and visual mappings for taxonomy values.
//
// W6-B: added icons + aria-labels for WCAG 1.4.1 (color is not the only signal).
// W6-D rewrite (2026-05-13): added bilingual user-friendly labels + plain
// English subtitles. Reference: docs/reviews/W5-F-copywriter-review-2026-05-13.md
// § 3.2 ("Filter labels"). Goal — keep technical terms but pair them with a
// human sentence the way Robinhood pairs "Buying Power" with "$X available
// to invest".
//
// PR-1 copy sweep (2026-05-14): jargon translated per /tmp/copy-style-guide.md
// translation table — 阈值级联 → 临界级联, 富者愈富 → 强者愈强,
// 路径依赖 → 回不去效应, 普适类 → 共享模式, 滞后 → 回不去效应,
// 失控通道/已翻转 simplified for 8th-grade reader.

import type { CriticalPointState, DynamicsFamily } from "./types";

export type Lang = "zh-CN" | "en";

// ---------------------------------------------------------------------------
// Dynamics family — primary user-friendly labels (per W5-F translation table).
// ---------------------------------------------------------------------------

export const DYNAMICS_LABEL_ZH: Record<DynamicsFamily, string> = {
  soc: "临界级联",
  preferential_attachment: "强者愈强",
  fold: "临界翻转",
  hysteresis: "回不去效应",
  other: "其他",
};

export const DYNAMICS_LABEL_EN: Record<DynamicsFamily, string> = {
  soc: "Threshold cascade",
  preferential_attachment: "Rich-get-richer",
  fold: "Tipping point",
  hysteresis: "Path dependence",
  other: "Other",
};

// One-line plain-Chinese subtitle for each dynamics family — shown next to
// the primary label so users always have a human read on the term.
export const DYNAMICS_SUBTITLE_ZH: Record<DynamicsFamily, string> = {
  soc: "压力慢慢攒，一下子全连环爆（像地震、银行挤兑）",
  preferential_attachment: "已经强的越来越强（像头部主播、爆款 App）",
  fold: "慢慢漂到悬崖边，掉下去就回不来",
  hysteresis: "上去的路和下来的路不一样（像交通堵车）",
  other: "未归入上述四类",
};

export const DYNAMICS_SUBTITLE_EN: Record<DynamicsFamily, string> = {
  soc: "Slow buildup → sudden cascade (earthquakes, bank runs)",
  preferential_attachment: "The strong keep gaining (GitHub stars, Wikipedia traffic)",
  fold: "Drift to a cliff — falling off is one-way",
  hysteresis: "Going up and coming down trace different paths",
  other: "Not assigned to a primary family",
};

// One-line layperson explanations of each dynamics family (W6-B).
// Used on /methodology and as tooltip hints.
// PR-1: rewritten plain-Chinese, no 普适类 / 幂律 / 自组织 jargon (幂律保留是大众词).
export const DYNAMICS_EXPLAIN: Record<DynamicsFamily, string> = {
  soc: "压力慢慢攒，到了某个点一次性爆发，规模可大可小（地震、雪崩、神经放电都是这样）。",
  preferential_attachment:
    "已经强的越来越强：越多人关注越容易再来新关注，最后头部吃掉大部分（社交网络、引用关系）。",
  fold: "参数慢慢变，系统突然跳到另一个稳定状态，而且回不去了（湖泊富营养化、生态崩塌）。",
  hysteresis:
    "走过的路决定现在在哪：同样的条件，可能停在不同状态（交通堵车 vs. 畅通、牛市 vs. 熊市）。",
  other: "暂未归入上面四类的其他结构。",
};

// Legacy single-language fallback (English technical name). Kept so any
// existing import of `DYNAMICS_LABEL` continues to compile.
export const DYNAMICS_LABEL: Record<DynamicsFamily, string> = DYNAMICS_LABEL_EN;

// ---------------------------------------------------------------------------
// Critical-point state — user-friendly labels.
// ---------------------------------------------------------------------------

// PR-1: kept plain-Chinese labels (稳态 / 临界附近 / 失控通道 / 已翻转) —
// these are already audience-friendly. EN map below also plain-English.
export const CPS_LABEL_ZH: Record<CriticalPointState, string> = {
  subcritical: "稳态",
  near_critical: "临界附近",
  supercritical: "失控通道",
  tipped: "已翻转",
};

export const CPS_LABEL_EN: Record<CriticalPointState, string> = {
  subcritical: "Stable",
  near_critical: "On the edge",
  supercritical: "Runaway",
  tipped: "Tipped",
};

export const CPS_SUBTITLE_ZH: Record<CriticalPointState, string> = {
  subcritical: "压力小，扛得住",
  near_critical: "小风吹就能放大",
  supercritical: "正反馈已经在跑",
  tipped: "回不到原来的样子了",
};

export const CPS_SUBTITLE_EN: Record<CriticalPointState, string> = {
  subcritical: "Low stress, resilient",
  near_critical: "Small shocks can amplify",
  supercritical: "Positive feedback is running",
  tipped: "Cannot return to prior state",
};

// Layperson explanations for /methodology and tooltip (W6-B).
// PR-1: rewritten plain-Chinese (8th-grade level), no 相变 / reverse hysteresis jargon.
export const CPS_EXPLAIN: Record<CriticalPointState, string> = {
  subcritical: "离翻车点还远。系统稳稳运行，没有自我加强的反馈。",
  near_critical:
    "已经在翻车点附近了。小扰动开始被放大，波动变大，但还没真翻面。",
  supercritical:
    "已经越过翻车点但还没翻完。正在加速滑向新的状态。",
  tipped: "已经翻完了。想回到原来的样子，需要外部强力干预。",
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
  subcritical: "稳态：离翻车点还远",
  near_critical: "临界附近：接近翻车点",
  supercritical: "失控通道：已经越过翻车点",
  tipped: "已翻转：状态已经改变",
};

// Legacy alias — keep existing imports working.
export const CPS_LABEL: Record<CriticalPointState, string> = CPS_LABEL_EN;

// ---------------------------------------------------------------------------
// Display label dispatcher.
// ---------------------------------------------------------------------------

type Field =
  | "dynamics_family"
  | "critical_point_state"
  // Extended fields (forward-compat with v0.2 taxonomy — currently aliased to
  // the closest existing DynamicsFamily). Calling displayLabel with one of
  // these returns the same user-friendly label.
  | "universality_class"
  | "soc_threshold_cascade"
  | "preferential_attachment"
  | "hysteresis_preisach"
  | "scheffer_fold"
  | "motter_lai_cascade"
  | "extreme_value_tail"
  | "linear_quasi_equilibrium"
  | "reflexive_fixed_point"
  | "mixed";

// Forward-compatible alias table — maps extended taxonomy IDs that don't
// exist in the current `DynamicsFamily` union onto user-friendly labels
// independent of that union. This lets the UI render extended labels coming
// out of v0.2 ingest without first widening the type.
// PR-1: 普适类 → 共享模式; 阈值级联 → 临界级联; 富者愈富 → 强者愈强;
// 滞后效应 → 回不去效应; 网络级联 → 网络级联反应; 反身性 keeps (大众有认知).
const EXTENDED_LABELS_ZH: Record<string, string> = {
  universality_class: "共享模式",
  soc_threshold_cascade: "临界级联",
  preferential_attachment: "强者愈强",
  hysteresis_preisach: "回不去效应",
  scheffer_fold: "临界翻转",
  motter_lai_cascade: "网络级联反应",
  extreme_value_tail: "极端尾部风险",
  linear_quasi_equilibrium: "线性平衡",
  reflexive_fixed_point: "反身性",
  mixed: "混合型",
};

const EXTENDED_LABELS_EN: Record<string, string> = {
  universality_class: "Pattern family",
  soc_threshold_cascade: "Cascade dynamics",
  preferential_attachment: "Rich get richer",
  hysteresis_preisach: "Memory effects",
  scheffer_fold: "Tipping point",
  motter_lai_cascade: "Network domino",
  extreme_value_tail: "Tail risk",
  linear_quasi_equilibrium: "Steady state",
  reflexive_fixed_point: "Reflexive feedback",
  mixed: "Mixed signals",
};

// Extra CPS states surfaced by W5-F mapping (not in the strict union yet —
// returned as strings so the UI can render them without a schema change).
const EXTENDED_CPS_ZH: Record<string, string> = {
  far_from_critical: "稳态",
  approaching: "接近",
  at_critical: "临界",
  post_critical: "过临",
  unknown: "未知",
};

const EXTENDED_CPS_EN: Record<string, string> = {
  far_from_critical: "Far from tipping",
  approaching: "Approaching tipping",
  at_critical: "At tipping",
  post_critical: "Post-tipping",
  unknown: "Unknown",
};

/**
 * Resolve a (field, value) into a user-friendly string. Falls back to the
 * raw value when no mapping exists so the UI never renders empty.
 *
 * @param field   schema field name
 * @param value   raw enum value coming from the API
 * @param lang    "zh-CN" (default) or "en"
 */
export function displayLabel(
  field: Field | string,
  value: string,
  lang: Lang = "zh-CN",
): string {
  if (!value) return "";

  if (field === "dynamics_family") {
    const map = lang === "zh-CN" ? DYNAMICS_LABEL_ZH : DYNAMICS_LABEL_EN;
    return map[value as DynamicsFamily] ?? value;
  }

  if (field === "critical_point_state") {
    const map = lang === "zh-CN" ? CPS_LABEL_ZH : CPS_LABEL_EN;
    if (value in map) return map[value as CriticalPointState];
    const ext = lang === "zh-CN" ? EXTENDED_CPS_ZH : EXTENDED_CPS_EN;
    return ext[value] ?? value;
  }

  // Extended fields — look up by field name first (semantic field label),
  // then by value (treats the value itself as the taxonomy ID).
  const ext = lang === "zh-CN" ? EXTENDED_LABELS_ZH : EXTENDED_LABELS_EN;
  if (typeof field === "string" && field in ext) return ext[field];
  if (value in ext) return ext[value];
  return value;
}

/**
 * Get the plain-English subtitle for a dynamics family or CPS value.
 * Returns empty string when no subtitle is defined.
 */
export function displaySubtitle(
  field: Field | string,
  value: string,
  lang: Lang = "zh-CN",
): string {
  if (!value) return "";

  if (field === "dynamics_family") {
    const map = lang === "zh-CN" ? DYNAMICS_SUBTITLE_ZH : DYNAMICS_SUBTITLE_EN;
    return map[value as DynamicsFamily] ?? "";
  }

  if (field === "critical_point_state") {
    const map = lang === "zh-CN" ? CPS_SUBTITLE_ZH : CPS_SUBTITLE_EN;
    return map[value as CriticalPointState] ?? "";
  }

  return "";
}

// ---------------------------------------------------------------------------
// Tailwind class maps for badges (statically discoverable by JIT).
// W6-B: aligned to design system tokens (emerald-600/amber-600/red-600/zinc-900).
// ---------------------------------------------------------------------------

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
