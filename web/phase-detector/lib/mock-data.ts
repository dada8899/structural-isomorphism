// Mock data for dev / fallback when backend API is unavailable.
// Used when NEXT_PUBLIC_USE_MOCK=true.

import type { Company, Stats } from "./types";

export const MOCK_COMPANIES: Company[] = [
  {
    ticker: "NVDA",
    name: "NVIDIA Corp",
    sector: "Semiconductors",
    dynamics_family: "preferential_attachment",
    critical_point_state: "supercritical",
    tldr:
      "Preferential-attachment dynamics across the AI accelerator ecosystem: each new model release reinforces NVDA's CUDA moat. Supercritical regime — share gains are super-linear in installed base.",
    primary_indicators: [
      { name: "CUDA developer count", value: "5M+", note: "10x in 3y" },
      { name: "DC GPU share", value: "~92%", unit: "%" },
      { name: "Gross margin", value: 75.3, unit: "%" },
    ],
    confidence: 0.88,
    caveats: [
      "Concentration risk: hyperscaler capex cycle is the dominant driver.",
      "Custom ASIC (TPU/Trainium/MTIA) progress could shift dynamics class.",
    ],
    updated_at: "2026-05-12",
  },
  {
    ticker: "INTC",
    name: "Intel Corp",
    sector: "Semiconductors",
    dynamics_family: "hysteresis",
    critical_point_state: "near_critical",
    tldr:
      "Hysteresis dynamics: foundry recovery requires sustained capex >> previous era. Near-critical: 18A node ramp is the bifurcation point — either tips back into competitive parity or stalls.",
    primary_indicators: [
      { name: "Foundry capex / revenue", value: 0.39 },
      { name: "18A node yield (est.)", value: "55-65%", unit: "%" },
      { name: "External foundry customers", value: 3 },
    ],
    confidence: 0.62,
    caveats: [
      "18A yield numbers are leaked estimates, not audited.",
      "Hysteresis vs fold-bifurcation classification is borderline.",
    ],
    updated_at: "2026-05-11",
  },
  {
    ticker: "TSLA",
    name: "Tesla Inc",
    sector: "Automotive",
    dynamics_family: "soc",
    critical_point_state: "near_critical",
    tldr:
      "SOC-like avalanche dynamics in EV adoption + autonomy regulatory waves. Near-critical: each L4 robotaxi region adds non-linear value, but cascade timing is fundamentally unpredictable.",
    primary_indicators: [
      { name: "FSD miles driven (cumulative)", value: "1.8B" },
      { name: "Robotaxi cities live", value: 4 },
      { name: "Energy storage GWh", value: 31.4 },
    ],
    confidence: 0.55,
    caveats: [
      "SOC classification depends on whether one treats regulatory approvals as endogenous or exogenous.",
      "Power-law fit of cascade sizes has small N (<50 events).",
    ],
    updated_at: "2026-05-13",
  },
  {
    ticker: "BABA",
    name: "Alibaba Group",
    sector: "E-commerce",
    dynamics_family: "fold",
    critical_point_state: "subcritical",
    tldr:
      "Fold-bifurcation post regulatory reset (2021-2024). Subcritical regime: GMV growth has stabilized at lower equilibrium; no near-term tipping driver visible.",
    primary_indicators: [
      { name: "Take rate", value: 3.2, unit: "%" },
      { name: "Cloud op margin", value: 8.5, unit: "%" },
      { name: "Buyback yield", value: 6.1, unit: "%" },
    ],
    confidence: 0.71,
    caveats: [
      "Fold vs hysteresis is debated — depends on whether 2021 regulatory shock is permanent.",
    ],
    updated_at: "2026-05-10",
  },
  {
    ticker: "SVB",
    name: "(historical) SVB Financial",
    sector: "Banking",
    dynamics_family: "soc",
    critical_point_state: "tipped",
    tldr:
      "Already-tipped case study: deposit-flight avalanche March 2023 fits SOC profile — small trigger (rate-driven HTM mark) → power-law cascade across uninsured deposit base in <48h.",
    primary_indicators: [
      { name: "Uninsured deposit ratio", value: 93.8, unit: "%" },
      { name: "HTM unrealized loss / equity", value: 1.4 },
      { name: "Days to failure post-trigger", value: 2 },
    ],
    confidence: 0.94,
    caveats: [
      "Listed as reference / training example — not an active screener result.",
    ],
    updated_at: "2026-05-01",
  },
  {
    ticker: "GME",
    name: "GameStop Corp",
    sector: "Retail",
    dynamics_family: "preferential_attachment",
    critical_point_state: "subcritical",
    tldr:
      "Preferential-attachment regime via meme-cohort attention dynamics; subcritical now — attention drift away from 2021 cohort, residual amplification too weak to sustain cascades.",
    primary_indicators: [
      { name: "Retail option flow / total", value: 0.18 },
      { name: "Days since last short-squeeze cascade", value: 412 },
    ],
    confidence: 0.48,
    caveats: [
      "Low confidence: attention dynamics are hard to measure ex-ante.",
      "Sample size of comparable cascades is small (<10).",
    ],
    updated_at: "2026-05-09",
  },
];

export const MOCK_STATS: Stats = {
  total_companies: MOCK_COMPANIES.length,
  by_dynamics: [
    { dynamics_family: "soc", count: 2 },
    { dynamics_family: "preferential_attachment", count: 2 },
    { dynamics_family: "fold", count: 1 },
    { dynamics_family: "hysteresis", count: 1 },
  ],
  by_critical_point_state: [
    { critical_point_state: "subcritical", count: 2 },
    { critical_point_state: "near_critical", count: 2 },
    { critical_point_state: "supercritical", count: 1 },
    { critical_point_state: "tipped", count: 1 },
  ],
  by_sector: [
    { sector: "Semiconductors", count: 2 },
    { sector: "Automotive", count: 1 },
    { sector: "E-commerce", count: 1 },
    { sector: "Banking", count: 1 },
    { sector: "Retail", count: 1 },
  ],
};
