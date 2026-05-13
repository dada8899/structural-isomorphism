// Shared types for Phase Detector frontend
// Schema mirrors W3-B backend API responses.

export type DynamicsFamily =
  | "soc"
  | "preferential_attachment"
  | "fold"
  | "hysteresis"
  | "other";

export type CriticalPointState =
  | "subcritical"
  | "near_critical"
  | "supercritical"
  | "tipped";

export interface PrimaryIndicator {
  name: string;
  value: string | number;
  unit?: string;
  // Optional short hint shown next to the indicator.
  note?: string;
}

export interface Company {
  ticker: string;
  name: string;
  sector?: string;
  dynamics_family: DynamicsFamily;
  critical_point_state: CriticalPointState;
  // 30-second TL;DR — 1-3 sentences, plain English.
  tldr: string;
  primary_indicators: PrimaryIndicator[];
  confidence: number; // 0..1
  caveats?: string[];
  // For detail page: raw model JSON or extra fields.
  raw_response?: Record<string, unknown>;
  updated_at?: string;
}

export interface ScreenerFilters {
  dynamics_family?: DynamicsFamily | "";
  critical_point_state?: CriticalPointState | "";
  sector?: string;
  min_confidence?: number;
  limit?: number;
}

export interface SectorBreakdown {
  sector: string;
  count: number;
}

export interface DynamicsBreakdown {
  dynamics_family: DynamicsFamily;
  count: number;
}

export interface CpsBreakdown {
  critical_point_state: CriticalPointState;
  count: number;
}

export interface Stats {
  total_companies: number;
  by_dynamics: DynamicsBreakdown[];
  by_critical_point_state: CpsBreakdown[];
  by_sector: SectorBreakdown[];
}
