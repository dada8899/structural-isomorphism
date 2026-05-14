// Shared types for Phase Detector frontend.
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
