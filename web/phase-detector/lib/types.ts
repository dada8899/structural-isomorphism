// Shared types for Structural Labs · Phase frontend.
//
// 2026-05-14 P0 fix: schema realigned to backend canonical (W3-B v0.2 taxonomy).
// Backend = source of truth. FE enums + Stats shape now mirror exactly what
// GET /api/stats and GET /api/screener return. Previously the FE used a
// legacy short-name vocabulary (soc / fold / hysteresis / subcritical /
// near_critical / supercritical / tipped) that did not exist in any BE
// response, so every filter selection returned [] in production.

// ---------------------------------------------------------------------------
// Dynamics family — 9-state v0.2 taxonomy as returned by /api/screener.
// ---------------------------------------------------------------------------
export type DynamicsFamily =
  | "soc_threshold_cascade"
  | "preferential_attachment"
  | "scheffer_fold"
  | "hysteresis_preisach"
  | "motter_lai_cascade"
  | "reflexive_fixed_point"
  | "extreme_value_tail"
  | "linear_quasi_equilibrium"
  | "mixed_or_unclear";

// ---------------------------------------------------------------------------
// Critical-point state — 5-state v0.2 taxonomy.
// ---------------------------------------------------------------------------
export type CriticalPointState =
  | "far_from_critical"
  | "approaching_critical"
  | "at_critical"
  | "post_critical_transition"
  | "unknown";

// Primary indicators are returned as a free-form object (key → value). We
// keep `value` permissive because BE may emit string labels (e.g. "rising")
// or numeric values for the same indicator name across companies.
export type PrimaryIndicators = Record<string, string | number | null>;

export interface Company {
  ticker: string;
  name: string;
  sector: string;
  industry?: string | null;
  market_cap_usd_b?: number | null;
  dynamics_family: DynamicsFamily;
  critical_point_state: CriticalPointState;
  universality_class?: string | null;
  extraction_confidence: number; // 0..1
  extraction_model?: string | null;
  extracted_at?: string | null;
  // 30-second TL;DR — 1-3 sentences, plain English.
  tldr: string;
  primary_indicators: PrimaryIndicators | null;
  caveats?: string[] | null;
}

export interface ScreenerFilters {
  dynamics_family?: DynamicsFamily | "";
  critical_point_state?: CriticalPointState | "";
  sector?: string;
  min_confidence?: number;
  limit?: number;
}

// ---------------------------------------------------------------------------
// Stats — shape returned by GET /api/stats.
//   total (NOT total_companies)
//   by_dynamics_family (NOT by_dynamics)
//   by_critical_point_state, by_sector, by_universality_class are Records,
//   not arrays — this was the source of the .map() crash.
// ---------------------------------------------------------------------------
export interface Stats {
  total: number;
  by_dynamics_family: Partial<Record<DynamicsFamily, number>>;
  by_critical_point_state: Partial<Record<CriticalPointState, number>>;
  by_sector: Record<string, number>;
  by_universality_class: Record<string, number>;
}

// ---------------------------------------------------------------------------
// W10-E — Universality class taxonomy types.
// Backend: /api/universality/{classes, classes/<id>, companies/<id>}
// ---------------------------------------------------------------------------

// Card-sized payload returned by GET /api/universality/classes.
export interface UniversalityClassCard {
  class_id: string;
  display_name: string;
  display_name_zh?: string | null;
  definition: string;
  status: "well-established" | "emerging" | "speculative" | "unknown" | string;
  exponent_band: string[]; // first ≤3 key invariants — short for cards
  evidence_count: number;
}

export interface UniversalityClassesResponse {
  count: number;
  classes: UniversalityClassCard[];
}

// Full payload returned by GET /api/universality/classes/{class_id}.
export interface UniversalityEvidenceSystem {
  phenomenon: string;
  evidence: string;
  verified_at?: string;
  paper?: string | null;
}

export interface UniversalityNegativeExample {
  phenomenon: string;
  reason: string;
}

export interface UniversalityEdgeCase {
  phenomenon: string;
  debate: string;
}

export interface UniversalityClassDetail {
  class_id: string;
  display_name: string;
  display_name_zh?: string | null;
  definition: string;
  status: string;
  key_invariants: string[];
  shared_equation: string;
  evidence_systems: UniversalityEvidenceSystem[];
  negative_examples: UniversalityNegativeExample[];
  edge_cases: UniversalityEdgeCase[];
  references: string[];
  prototypes: string[];
  source: string;
}

// Mini-company row from GET /api/universality/companies/{class_id}.
export interface UniversalityCompanyTag {
  ticker: string;
  name: string;
  sector?: string | null;
  industry?: string | null;
  dynamics_family?: DynamicsFamily;
  critical_point_state?: CriticalPointState;
  extraction_confidence?: number;
  tldr?: string | null;
}

export interface UniversalityCompaniesResponse {
  class_id: string;
  display_name: string;
  count: number;
  companies: UniversalityCompanyTag[];
}

// ---------------------------------------------------------------------------
// EWS (Early-Warning-Signal) types — 2026-05-23 PD-EWS.
//
// The EWS layer replaces the LLM-vibe "critical_point_state" / fake PRNG
// trajectory with values computed from real OHLCV by
// `v4/product/d1_phase_detector/ews.py`. Two-market aware (US + HK).
// ---------------------------------------------------------------------------

export type Market = "US" | "HK";
export type Currency = "USD" | "HKD";

export interface EwsTimeSeries {
  name: string;                       // "ar1" | "var"
  dates: string[];                    // ISO yyyy-mm-dd, ascending
  values: (number | null)[];          // None where the window hasn't filled
  tau: number | null;                 // Kendall tau over trailing window
  tau_p: number | null;               // approximate two-sided p-value
  n_trend: number;
}

export interface EwsResultFull {
  ticker: string;
  as_of: string;
  n_returns: number;
  window: number;
  trend_window: number;
  ar1: EwsTimeSeries;
  var: EwsTimeSeries;
  criticality_score: number;          // 0..100
  phase_state: CriticalPointState;
  confidence: number;                 // 0..1
  notes: string[];

  // Enrichment from the pipeline
  name?: string | null;
  name_zh?: string | null;
  sector?: string | null;
  market?: Market;
  currency?: Currency;
  indices?: string[] | null;
  adr_ticker?: string | null;
  llm_dynamics_family?: DynamicsFamily | null;
  llm_tldr?: string | null;
  price_provenance?: "live" | "demo" | "missing";
}

// Lighter card payload for leaderboard / screener rows.
export interface EwsCard {
  ticker: string;
  name?: string | null;
  name_zh?: string | null;
  sector?: string | null;
  market?: Market;
  currency?: Currency;
  criticality_score: number;
  phase_state: CriticalPointState;
  confidence: number;
  as_of?: string | null;
  tau_ar1?: number | null;
  tau_var?: number | null;
  price_provenance?: "live" | "demo" | "missing";
}

export interface EwsMeta {
  version: string;
  generated_at?: string;
  n_tickers: number;
  n_critical?: number;
  n_approaching?: number;
  n_post?: number;
  by_market?: Partial<Record<Market, number>>;
  price_provenance: "live" | "demo" | "missing" | "live+synth_fallback" | "unknown";
  period?: string;
  interval?: string;
  msg?: string;
}

export interface EwsLeaderboardFilters {
  market?: Market | "ALL";
  phase?: CriticalPointState;
  sector?: string;
  min_score?: number;
  min_confidence?: number;
  limit?: number;
}
