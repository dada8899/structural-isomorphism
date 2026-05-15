// Shared fixtures for stories. Mirrors the BE canonical schema in lib/types.ts
// so stories don't drift if the backend contract evolves — they reuse the
// same types, just with sample data.
import type {
  Company,
  Stats,
  UniversalityClassDetail,
} from "@/lib/types";
// W15-A: pull one fixture's type from the auto-generated api-types so a
// backend rename breaks Storybook visibly + early.
import type { CheckoutBody } from "@/lib/api-types";

// W15-A: example POST body matching the generated `CheckoutBody`.
// Stories or future MSW handlers consume this rather than inlining a
// duplicate object literal that could drift from Pydantic.
export const checkoutBodyValid: CheckoutBody = {
  tier: "pro",
  interval: "month",
  email: "qa@example.com",
  name: "QA Tester",
  card_last4: "4242",
  force_status: null,
};

export const checkoutBodyDeclined: CheckoutBody = {
  ...checkoutBodyValid,
  card_last4: "0002",
  force_status: "declined",
};

export const companyStable: Company = {
  ticker: "AAPL",
  name: "Apple Inc.",
  sector: "tech",
  industry: "Consumer Electronics",
  market_cap_usd_b: 3520,
  dynamics_family: "preferential_attachment",
  critical_point_state: "far_from_critical",
  universality_class: "scale_free_network",
  extraction_confidence: 0.92,
  extraction_model: "kimi-k2.5",
  extracted_at: "2026-05-14T10:30:00Z",
  tldr:
    "Mature consumer-electronics platform with strong ecosystem lock-in. " +
    "Network effects keep it well clear of any near-term phase transition.",
  primary_indicators: {
    revenue_growth_yoy: 0.08,
    operating_margin: 0.31,
    ecosystem_health: "strong",
  },
  caveats: ["Hardware refresh cycle sensitivity is not modeled."],
};

export const companyApproaching: Company = {
  ticker: "TSLA",
  name: "Tesla, Inc.",
  sector: "auto",
  industry: "Electric Vehicles",
  market_cap_usd_b: 880,
  dynamics_family: "scheffer_fold",
  critical_point_state: "approaching_critical",
  universality_class: "saddle_node_bifurcation",
  extraction_confidence: 0.71,
  extraction_model: "kimi-k2.5",
  extracted_at: "2026-05-14T10:30:00Z",
  tldr:
    "EV demand growth is decelerating while competition intensifies. " +
    "Margin compression signal is consistent with approaching a fold bifurcation.",
  primary_indicators: {
    margin_trend: "compressing",
    demand_yoy: -0.02,
    competitive_pressure: "rising",
  },
  caveats: ["FSD revenue assumptions remain speculative."],
};

export const companyAtCritical: Company = {
  ticker: "GME",
  name: "GameStop Corp.",
  sector: "retail",
  industry: "Specialty Retail",
  market_cap_usd_b: 8.4,
  dynamics_family: "reflexive_fixed_point",
  critical_point_state: "at_critical",
  universality_class: "reflexive_feedback",
  extraction_confidence: 0.58,
  extraction_model: "deepseek-v4-pro",
  extracted_at: "2026-05-14T10:30:00Z",
  tldr:
    "Cash-heavy balance sheet plus social-driven equity activity puts the " +
    "company at a reflexive fixed point — outcome depends on sentiment regime.",
  primary_indicators: {
    cash_ratio: 0.42,
    short_interest_pct: 0.18,
    sentiment_volatility: "high",
  },
  caveats: ["Highly path-dependent; not a fundamentals-only call."],
};

export const companyPost: Company = {
  ticker: "BBBY",
  name: "Bed Bath & Beyond (post)",
  sector: "retail",
  industry: "Home Furnishings",
  market_cap_usd_b: 0.05,
  dynamics_family: "soc_threshold_cascade",
  critical_point_state: "post_critical_transition",
  universality_class: "soc_avalanche",
  extraction_confidence: 0.81,
  extraction_model: "kimi-k2.5",
  extracted_at: "2026-05-14T10:30:00Z",
  tldr:
    "Already past the transition — Chapter 11 cascade completed. Included " +
    "as a worked example of post-critical state classification.",
  primary_indicators: {
    liquidity: "exhausted",
    fcf: -2.1,
  },
  caveats: ["Historical case, not actively traded."],
};

export const companyUnknown: Company = {
  ticker: "PRIVATE-XYZ",
  name: "Example Private Co.",
  sector: "unknown",
  industry: null,
  market_cap_usd_b: null,
  dynamics_family: "mixed_or_unclear",
  critical_point_state: "unknown",
  universality_class: null,
  extraction_confidence: 0.21,
  extraction_model: "kimi-k2.5",
  extracted_at: "2026-05-14T10:30:00Z",
  tldr:
    "Insufficient public information to classify with confidence. Shown " +
    "for the low-confidence visual state.",
  primary_indicators: null,
  caveats: [
    "Confidence below 0.30 — model abstained on phase classification.",
    "Re-run when next 10-K is available.",
  ],
};

export const statsSample: Stats = {
  total: 5212,
  by_dynamics_family: {
    soc_threshold_cascade: 812,
    preferential_attachment: 1340,
    scheffer_fold: 654,
    hysteresis_preisach: 410,
    motter_lai_cascade: 296,
    reflexive_fixed_point: 188,
    extreme_value_tail: 240,
    linear_quasi_equilibrium: 980,
    mixed_or_unclear: 292,
  },
  by_critical_point_state: {
    far_from_critical: 3120,
    approaching_critical: 1140,
    at_critical: 412,
    post_critical_transition: 280,
    unknown: 260,
  },
  by_sector: {
    tech: 1340,
    finance: 920,
    healthcare: 810,
    energy: 640,
    industrials: 520,
    consumer: 540,
    materials: 240,
    other: 202,
  },
  by_universality_class: {
    scale_free_network: 1340,
    soc_avalanche: 812,
    saddle_node_bifurcation: 654,
    pitchfork_bifurcation: 320,
    transcritical_bifurcation: 198,
    hopf_bifurcation: 188,
  },
};

export const universalityDetailSample: UniversalityClassDetail = {
  class_id: "soc_avalanche",
  display_name: "Self-Organized Criticality (Avalanche)",
  display_name_zh: "自组织临界（雪崩）",
  definition:
    "Systems where slow loading and abrupt threshold-driven cascades produce " +
    "power-law-distributed event sizes without external fine-tuning.",
  status: "well_established",
  key_invariants: [
    "Power-law event-size distribution",
    "1/f noise in the driving variable",
    "Critical exponent τ ≈ 1.5 (mean-field)",
  ],
  shared_equation: "P(s) ~ s^{-τ}",
  evidence_systems: [
    {
      domain: "physics",
      name: "Bak-Tang-Wiesenfeld sandpile",
      citation: "Bak, Tang & Wiesenfeld 1987",
    },
    {
      domain: "biology",
      name: "Neural avalanches",
      citation: "Beggs & Plenz 2003",
    },
    {
      domain: "finance",
      name: "DeFi liquidation cascades",
      citation: "Aave V2 / Maker / Compound 2020-2024",
    },
  ],
  negative_examples: [
    { name: "Linear regulators", reason: "No threshold-driven cascade." },
  ],
  edge_cases: [
    {
      name: "Power-law tail without 1/f noise",
      note: "Often heavy-tailed but not SOC.",
    },
  ],
  references: [
    "Bak P. (1996) How Nature Works",
    "Aschwanden M. (2011) Self-Organized Criticality in Astrophysics",
  ],
  prototypes: ["sandpile", "forest_fire", "OFC_earthquake"],
  source: "v0.2 taxonomy + W11-A audit",
};
