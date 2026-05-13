// Mock data for dev / fallback when backend API is unavailable.
// Used when NEXT_PUBLIC_USE_MOCK=true.
// Aligned to backend canonical enums (PR-7, 2026-05-14).

import type { Company, Stats } from "./types";

export const MOCK_COMPANIES: Company[] = [
  {
    ticker: "NVDA",
    name: "NVIDIA Corp",
    sector: "tech_semiconductors",
    industry: null,
    market_cap_usd_b: 3000.0,
    dynamics_family: "preferential_attachment",
    critical_point_state: "at_critical",
    universality_class: null,
    extraction_confidence: 0.88,
    extraction_model: null,
    extracted_at: "2026-05-12T00:00:00+00:00",
    tldr:
      "强者愈强 dynamics across the AI accelerator ecosystem: each new model release reinforces NVDA's CUDA moat. Share gains are super-linear in installed base.",
    primary_indicators: {
      cuda_dev_count: "5M+",
      dc_gpu_share_pct: 92,
      gross_margin_pct: 75.3,
    },
    caveats: ["Concentration risk: hyperscaler capex cycle dominates."],
  },
  {
    ticker: "INTC",
    name: "Intel Corp",
    sector: "tech_semiconductors",
    industry: null,
    market_cap_usd_b: 130.0,
    dynamics_family: "hysteresis_preisach",
    critical_point_state: "approaching_critical",
    universality_class: null,
    extraction_confidence: 0.62,
    extraction_model: null,
    extracted_at: "2026-05-11T00:00:00+00:00",
    tldr:
      "回不去效应：foundry recovery requires sustained capex >> previous era. 18A node ramp is the bifurcation point — either tips back into competitive parity or stalls.",
    primary_indicators: {
      foundry_capex_to_rev: 0.39,
      node_yield_pct: 60,
      external_foundry_customers: 3,
    },
    caveats: ["18A yield numbers are leaked estimates, not audited."],
  },
  {
    ticker: "TSLA",
    name: "Tesla Inc",
    sector: "tech_auto_ev",
    industry: null,
    market_cap_usd_b: 800.0,
    dynamics_family: "soc_threshold_cascade",
    critical_point_state: "approaching_critical",
    universality_class: null,
    extraction_confidence: 0.55,
    extraction_model: null,
    extracted_at: "2026-05-13T00:00:00+00:00",
    tldr:
      "临界级联-like dynamics in EV adoption + autonomy regulatory waves. Each L4 robotaxi region adds non-linear value, but cascade timing is fundamentally unpredictable.",
    primary_indicators: {
      fsd_miles_cumulative_b: 1.8,
      robotaxi_cities_live: 4,
      energy_storage_gwh: 31.4,
    },
    caveats: ["Classification depends on whether regulatory approvals are endogenous or exogenous."],
  },
  {
    ticker: "BABA",
    name: "Alibaba Group",
    sector: "consumer_discretionary",
    industry: null,
    market_cap_usd_b: 220.0,
    dynamics_family: "scheffer_fold",
    critical_point_state: "far_from_critical",
    universality_class: null,
    extraction_confidence: 0.71,
    extraction_model: null,
    extracted_at: "2026-05-10T00:00:00+00:00",
    tldr:
      "临界翻转 post regulatory reset (2021-2024). GMV growth has stabilized at a lower equilibrium; no near-term tipping driver visible.",
    primary_indicators: {
      take_rate_pct: 3.2,
      cloud_op_margin_pct: 8.5,
      buyback_yield_pct: 6.1,
    },
    caveats: ["Fold vs hysteresis is debated — depends on whether 2021 regulatory shock is permanent."],
  },
  {
    ticker: "SVB",
    name: "(historical) SVB Financial",
    sector: "financials_bank",
    industry: null,
    market_cap_usd_b: 0.0,
    dynamics_family: "soc_threshold_cascade",
    critical_point_state: "post_critical_transition",
    universality_class: null,
    extraction_confidence: 0.94,
    extraction_model: null,
    extracted_at: "2026-05-01T00:00:00+00:00",
    tldr:
      "Already-tipped case study: deposit-flight 级联反应 March 2023 fits 临界级联 profile — small trigger (rate-driven HTM mark) → power-law cascade across uninsured deposit base in <48h.",
    primary_indicators: {
      uninsured_deposit_pct: 93.8,
      htm_loss_over_equity: 1.4,
      days_to_failure: 2,
    },
    caveats: ["Reference / training example — not an active screener result."],
  },
  {
    ticker: "GME",
    name: "GameStop Corp",
    sector: "consumer_discretionary_retail",
    industry: null,
    market_cap_usd_b: 8.0,
    dynamics_family: "preferential_attachment",
    critical_point_state: "far_from_critical",
    universality_class: null,
    extraction_confidence: 0.48,
    extraction_model: null,
    extracted_at: "2026-05-09T00:00:00+00:00",
    tldr:
      "强者愈强 regime via meme-cohort attention dynamics; now far from critical — attention drift away from 2021 cohort, residual amplification too weak to sustain cascades.",
    primary_indicators: {
      retail_option_flow_pct: 18,
      days_since_last_cascade: 412,
    },
    caveats: ["Attention dynamics are hard to measure ex-ante; sample size small (<10)."],
  },
];

export const MOCK_STATS: Stats = {
  total: MOCK_COMPANIES.length,
  by_dynamics_family: {
    soc_threshold_cascade: 2,
    preferential_attachment: 2,
    scheffer_fold: 1,
    hysteresis_preisach: 1,
    motter_lai_cascade: 0,
    reflexive_fixed_point: 0,
    extreme_value_tail: 0,
    linear_quasi_equilibrium: 0,
    mixed_or_unclear: 0,
  },
  by_critical_point_state: {
    far_from_critical: 2,
    approaching_critical: 2,
    at_critical: 1,
    post_critical_transition: 1,
    unknown: 0,
  },
  by_universality_class: {},
  by_sector: {
    tech_semiconductors: 2,
    tech_auto_ev: 1,
    consumer_discretionary: 1,
    consumer_discretionary_retail: 1,
    financials_bank: 1,
  },
};
