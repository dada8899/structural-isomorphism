// Human-friendly labels and visual mappings for taxonomy values.
//
// 2026-05-14 P0 fix: rewritten against v0.2 BE taxonomy. KEYS = canonical BE
// enum slugs (returned by /api/stats + /api/screener). VALUES = plain-Chinese
// per PR-1 copy style guide (8th-grade reader, no 普适类 / 幂律 jargon when
// avoidable). EN map kept as best-effort for future i18n.

import type { CriticalPointState, DynamicsFamily } from "./types";

export type Lang = "zh-CN" | "en";

// ---------------------------------------------------------------------------
// Dynamics family — primary user-friendly labels (v0.2 taxonomy).
// ---------------------------------------------------------------------------

export const DYNAMICS_LABEL_ZH: Record<DynamicsFamily, string> = {
  soc_threshold_cascade: "临界级联",
  preferential_attachment: "强者愈强",
  scheffer_fold: "临界翻转 (Scheffer)",
  hysteresis_preisach: "回不去效应",
  motter_lai_cascade: "网络级联反应",
  reflexive_fixed_point: "反身性循环",
  extreme_value_tail: "极端尾部",
  linear_quasi_equilibrium: "近线性稳态",
  mixed_or_unclear: "复合/待判定",
};

export const DYNAMICS_LABEL_EN: Record<DynamicsFamily, string> = {
  soc_threshold_cascade: "Threshold cascade",
  preferential_attachment: "Rich-get-richer",
  scheffer_fold: "Tipping point (Scheffer)",
  hysteresis_preisach: "Path dependence",
  motter_lai_cascade: "Network domino",
  reflexive_fixed_point: "Reflexive feedback",
  extreme_value_tail: "Tail risk",
  linear_quasi_equilibrium: "Steady state",
  mixed_or_unclear: "Mixed / unclear",
};

// One-line plain-Chinese subtitle for each dynamics family — shown next to
// the primary label so users always have a human read on the term.
export const DYNAMICS_SUBTITLE_ZH: Record<DynamicsFamily, string> = {
  soc_threshold_cascade: "压力慢慢攒，一下子全连环爆（像地震、银行挤兑）",
  preferential_attachment: "已经强的越来越强（像头部主播、爆款 App）",
  scheffer_fold: "慢慢漂到悬崖边，掉下去就回不来",
  hysteresis_preisach: "上去的路和下来的路不一样（像交通堵车）",
  motter_lai_cascade: "网络里一处出事，沿着连线一路连锁",
  reflexive_fixed_point: "情绪推动价格，价格又反过来推情绪",
  extreme_value_tail: "平时风平浪静，黑天鹅来时一记重击",
  linear_quasi_equilibrium: "基本面驱动，平稳缓慢",
  mixed_or_unclear: "几种模式叠在一起，暂时分不清",
};

export const DYNAMICS_SUBTITLE_EN: Record<DynamicsFamily, string> = {
  soc_threshold_cascade: "Slow buildup → sudden cascade (earthquakes, bank runs)",
  preferential_attachment: "The strong keep gaining (head accounts, viral apps)",
  scheffer_fold: "Drift to a cliff — falling off is one-way",
  hysteresis_preisach: "Going up and coming down trace different paths",
  motter_lai_cascade: "Failure in one node domino-chains across the network",
  reflexive_fixed_point: "Sentiment moves price; price moves sentiment",
  extreme_value_tail: "Calm most days; rare black swans dominate outcomes",
  linear_quasi_equilibrium: "Fundamentals-driven, slow and stable",
  mixed_or_unclear: "Several patterns layered; not yet separable",
};

// One-line layperson explanations of each dynamics family. Used on
// /methodology and as tooltip hints.
export const DYNAMICS_EXPLAIN: Record<DynamicsFamily, string> = {
  soc_threshold_cascade:
    "压力慢慢攒，到了某个点一次性爆发，规模可大可小（地震、雪崩、神经放电都是这样）。",
  preferential_attachment:
    "已经强的越来越强：越多人关注越容易再来新关注，最后头部吃掉大部分（社交网络、引用关系）。",
  scheffer_fold:
    "参数慢慢变，系统突然跳到另一个稳定状态，而且回不去了（湖泊富营养化、生态崩塌）。",
  hysteresis_preisach:
    "走过的路决定现在在哪：同样的条件，可能停在不同状态（交通堵车 vs. 畅通、牛市 vs. 熊市）。",
  motter_lai_cascade:
    "网络中一个节点故障，沿着依赖关系连环触发其他节点失效（电网瘫痪、供应链断裂）。",
  reflexive_fixed_point:
    "Soros 式反身性：信念影响现实，现实又反过来强化信念，形成自我加强的回路。",
  extreme_value_tail:
    "正常波动很小，但偶尔出现的极端事件主导长期结果（保险、再保、加密资产）。",
  linear_quasi_equilibrium:
    "近线性、平稳波动的稳态；可用传统估值/基本面框架解释，没有明显非线性。",
  mixed_or_unclear:
    "证据指向多种动力学，或当前数据不足以确定主导模式，暂列复合。",
};

// Legacy single-language fallback. Kept so any existing import of
// `DYNAMICS_LABEL` continues to compile.
export const DYNAMICS_LABEL: Record<DynamicsFamily, string> = DYNAMICS_LABEL_EN;

// ---------------------------------------------------------------------------
// Critical-point state — user-friendly labels.
// ---------------------------------------------------------------------------

export const CPS_LABEL_ZH: Record<CriticalPointState, string> = {
  far_from_critical: "稳态",
  approaching_critical: "接近临界",
  at_critical: "临界点上",
  post_critical_transition: "已翻转",
  unknown: "未知",
};

export const CPS_LABEL_EN: Record<CriticalPointState, string> = {
  far_from_critical: "Stable",
  approaching_critical: "Approaching tipping",
  at_critical: "At tipping",
  post_critical_transition: "Tipped",
  unknown: "Unknown",
};

export const CPS_SUBTITLE_ZH: Record<CriticalPointState, string> = {
  far_from_critical: "压力小，扛得住",
  approaching_critical: "小风吹就能放大",
  at_critical: "正反馈已经在跑",
  post_critical_transition: "回不到原来的样子了",
  unknown: "证据不足，暂未判定",
};

export const CPS_SUBTITLE_EN: Record<CriticalPointState, string> = {
  far_from_critical: "Low stress, resilient",
  approaching_critical: "Small shocks can amplify",
  at_critical: "Positive feedback is running",
  post_critical_transition: "Cannot return to prior state",
  unknown: "Insufficient evidence to classify",
};

// Layperson explanations for /methodology and tooltip.
export const CPS_EXPLAIN: Record<CriticalPointState, string> = {
  far_from_critical:
    "离翻车点还远。系统稳稳运行，没有自我加强的反馈。",
  approaching_critical:
    "已经在翻车点附近了。小扰动开始被放大，波动变大，但还没真翻面。",
  at_critical:
    "已经越过翻车点但还没翻完。正在加速滑向新的状态。",
  post_critical_transition:
    "已经翻完了。想回到原来的样子，需要外部强力干预。",
  unknown:
    "目前公开信息不足以判断它处在哪个阶段，先标记为未知。",
};

// WCAG 1.4.1 — icon symbols for non-color encoding.
// Each state has a unique geometric shape, visible regardless of color perception.
export const CPS_ICON: Record<CriticalPointState, string> = {
  far_from_critical: "●", // filled circle = stable
  approaching_critical: "▲", // up triangle = warning
  at_critical: "◆", // diamond = critical
  post_critical_transition: "✕", // cross = already changed
  unknown: "?", // question mark = unknown
};

export const CPS_ARIA_LABEL: Record<CriticalPointState, string> = {
  far_from_critical: "稳态：离翻车点还远",
  approaching_critical: "接近临界：已在翻车点附近",
  at_critical: "临界点上：已越过翻车点，仍在加速",
  post_critical_transition: "已翻转：状态已经改变",
  unknown: "未知：证据不足",
};

// Legacy alias — keep existing imports working.
export const CPS_LABEL: Record<CriticalPointState, string> = CPS_LABEL_EN;

// ---------------------------------------------------------------------------
// Sector labels — plain Chinese for the 38 BE sector slugs.
// Source of truth: GET /api/stats by_sector keys (full list pulled
// 2026-05-14). Unknown slugs fall back to the raw slug via the lookup
// helper SECTOR_LABEL_ZH[key] ?? key.
// ---------------------------------------------------------------------------
export const SECTOR_LABEL_ZH: Record<string, string> = {
  biotech: "生物科技",
  consumer_auto: "消费 / 整车",
  consumer_discretionary: "非必需消费",
  consumer_discretionary_retail: "非必需消费 / 零售",
  consumer_staples: "必需消费",
  energy_hydrogen: "能源 / 氢能",
  energy_midstream: "能源 / 中游",
  energy_oil_gas: "油气",
  energy_oilfield_svc: "油田服务",
  energy_refining: "能源 / 炼化",
  energy_solar: "能源 / 光伏",
  financials_asset_mgmt: "资产管理",
  financials_bank: "银行",
  financials_crypto: "金融 / 加密资产",
  financials_fintech: "金融科技",
  financials_insurance: "保险",
  financials_payments: "支付",
  financials_reinsurance: "再保险",
  financials_retail_broker: "零售券商",
  healthcare_devices: "医疗器械",
  healthcare_insurance: "医疗保险",
  healthcare_pharma: "制药",
  healthcare_retail: "医疗零售",
  industrials_aerospace: "航空航天",
  industrials_diversified: "工业 / 多元化",
  media_entertainment: "媒体娱乐",
  tech_auto: "科技 / 汽车",
  tech_auto_ev: "科技 / 电动车",
  tech_hardware: "科技 / 硬件",
  tech_internet: "科技 / 互联网",
  tech_internet_audio: "科技 / 互联网音频",
  tech_internet_china: "科技 / 中国互联网",
  tech_internet_streaming: "科技 / 流媒体",
  tech_marketplace: "科技 / 平台",
  tech_semiconductor: "半导体",
  tech_software: "科技 / 软件",
  tech_software_data: "科技 / 数据平台",
  tech_software_db: "科技 / 数据库",
  tech_software_ecommerce: "科技 / 电商软件",
  tech_software_edge: "科技 / 边缘计算",
  tech_software_gaming: "科技 / 游戏",
  tech_software_obs: "科技 / 可观测性",
  tech_software_security: "科技 / 安全",
  telecom: "电信",
};

// ---------------------------------------------------------------------------
// Display label dispatcher.
// ---------------------------------------------------------------------------

type Field = "dynamics_family" | "critical_point_state" | "sector" | string;

/**
 * Resolve a (field, value) into a user-friendly string. Falls back to the
 * raw value when no mapping exists so the UI never renders empty.
 */
export function displayLabel(
  field: Field,
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
    return map[value as CriticalPointState] ?? value;
  }

  if (field === "sector") {
    return SECTOR_LABEL_ZH[value] ?? value;
  }

  return value;
}

/**
 * Get the plain-Chinese subtitle for a dynamics family or CPS value.
 */
export function displaySubtitle(
  field: Field,
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
// Aligned to design system tokens (emerald-600/amber-600/red-600/zinc-900).
// ---------------------------------------------------------------------------

export const CPS_BADGE: Record<CriticalPointState, string> = {
  far_from_critical: "bg-emerald-600 text-white",
  approaching_critical: "bg-amber-600 text-white",
  at_critical: "bg-red-600 text-white",
  post_critical_transition: "bg-zinc-900 text-white",
  unknown: "bg-zinc-400 text-white",
};

export const CPS_DOT: Record<CriticalPointState, string> = {
  far_from_critical: "bg-emerald-600",
  approaching_critical: "bg-amber-600",
  at_critical: "bg-red-600",
  post_critical_transition: "bg-zinc-900",
  unknown: "bg-zinc-400",
};

export const DYNAMICS_FAMILY_OPTIONS: DynamicsFamily[] = [
  "soc_threshold_cascade",
  "preferential_attachment",
  "scheffer_fold",
  "hysteresis_preisach",
  "motter_lai_cascade",
  "reflexive_fixed_point",
  "extreme_value_tail",
  "linear_quasi_equilibrium",
  "mixed_or_unclear",
];

export const CPS_OPTIONS: CriticalPointState[] = [
  "far_from_critical",
  "approaching_critical",
  "at_critical",
  "post_critical_transition",
  "unknown",
];
