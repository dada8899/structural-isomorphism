// Session #12 W17 experiment — "Insight Cases" path C MVP.
//
// Hand-curated cross-domain case studies. NOT LLM-generated; each case is
// authored from SIBD-63 records + papers + cited literature. Each case
// surfaces three things the four-agent validation said are defensible:
//
//   1. An explicit *mechanism-level* variable mapping (Path A)
//   2. A documented record of what transferred AND what failed to
//      transfer in real published work (Path C — the case-study library)
//   3. A falsifiable micro-prediction the user can test in 30-90 days
//      (Path B — the public transfer ledger seed)
//
// We deliberately do NOT generate "you should do X" prescriptions. Every
// "outcome" field is sourced from an external citation OR from this
// project's own published NULL (the Phase Detector backtest, openly).
//
// Adding cases: append to INSIGHT_CASES. Keep ratios honest — at least
// one "failed" or "partial" transfer per case so the page doesn't read
// like a sales pitch for cross-domain transfer.

export type TransferOutcome = "succeeded" | "partial" | "failed" | "open";

export interface VariableMap {
  yours: string;
  analogue: string;
  note?: string;
}

export interface DocumentedTransfer {
  direction: string;
  intervention: string;
  outcome: TransferOutcome;
  evidence: string;
  citation: string;
  url?: string;
}

export interface FalsifiablePrediction {
  if_condition: string;
  then_observation: string;
  timeframe_days: number;
  how_to_test: string;
}

export interface InsightCase {
  id: string;
  /** Title displayed on cards + page header. */
  title: string;
  /** Short subtitle scanned in the index grid. */
  subtitle: string;
  /** The two domains being bridged. */
  domains: { a: string; b: string };
  /** Universality-class id that anchors this case (links to /universality/[id]). */
  universality_class_id: string;
  /** Class name displayed inline. */
  universality_class_name: string;
  /** Shared mathematical structure as a one-liner. */
  shared_equation: string;
  /** Variable-level correspondences. */
  variable_mapping: VariableMap[];
  /** Documented historical transfer attempts and their outcomes. */
  documented_transfers: DocumentedTransfer[];
  /** Mechanisms / boundary conditions where transfer can break. */
  blocking_mechanisms: string[];
  /** A 30-90 day falsifiable prediction the user can run. */
  falsifiable_prediction: FalsifiablePrediction;
  /** Honest one-line scope statement. Always shown. */
  scope_statement: string;
  /** Seed source in the SIBD-63 dataset. */
  sibd_seed_ids: string[];
  /** When this case-study card was last reviewed by a human. */
  last_human_review: string;
}

export const INSIGHT_CASES: InsightCase[] = [
  {
    id: "earthquake-defi-cascade",
    title: "Earthquake static-stress triggering ↔ DeFi liquidation cascade",
    subtitle:
      "Coulomb stress / Omori-Utsu structure shared between fault systems and on-chain leveraged-position networks.",
    domains: {
      a: "Earthquake aftershock sequences",
      b: "DeFi on-chain liquidation waves",
    },
    universality_class_id: "soc",
    universality_class_name: "Self-organized criticality (SOC)",
    shared_equation:
      "ΔCFS > ΔCFS_c triggers next failure → power-law cascade with Omori-Utsu temporal decay λ(t) = K / (c + t)^p",
    variable_mapping: [
      {
        yours: "Loan-to-value (LTV) distance to liquidation threshold",
        analogue: "Coulomb stress change ΔCFS on a fault patch",
        note: "ΔCFS is a 3-tensor; LTV is a scalar. The mapping is rank-reductive — directional information is lost.",
      },
      {
        yours: "Borrowing position",
        analogue: "Fault segment",
      },
      {
        yours: "Large liquidation triggering smaller liquidations",
        analogue: "Mainshock-aftershock cascade",
      },
      {
        yours: "Time-decay of liquidation rate post-event",
        analogue: "Omori-Utsu aftershock decay law",
        note: "The shape (power-law decay with p ≈ 1) is empirically observed in both systems.",
      },
    ],
    documented_transfers: [
      {
        direction: "Earthquake → DeFi",
        intervention:
          "Apply Omori-Utsu aftershock decay model to predict 30-day liquidation event rate following a major liquidation event.",
        outcome: "partial",
        evidence:
          "Within-domain fit on 2022 UST/Luna and 2023 sUSD/USDC depeg events shows liquidation rate decay consistent with p ≈ 0.9-1.1, within Omori's empirical band. Forward-prediction test on out-of-sample events not yet published.",
        citation:
          "SIBD-v3-044 execution plan (in-repo); partial fit reported in v4/results/ for SOC-class systems.",
        url: "https://github.com/dada8899/structural-isomorphism/blob/main/v4/results/",
      },
      {
        direction: "SOC pipeline → equity-return trading signal",
        intervention:
          "Use SOC-state classification (near_critical / far_from_critical) to bias long/short positions on a 1000-ticker universe.",
        outcome: "failed",
        evidence:
          "Walk-forward backtest on 927/1000 tickers, 59 monthly snapshots (2020–2025): Sharpe lift = −0.072 vs equal-weight benchmark, Welch t = 0.573, p = 0.569. Alpha not detected at scale. Direct evidence that pattern identification (SOC class fits the structure) does NOT imply intervention transfer (trading signal works).",
        citation: "Phase Detector v0.1 backtest, this repo, published openly as trust signal.",
        url: "https://phase.bytedance.city/backtest",
      },
      {
        direction: "Earthquake stress-load → DeFi liquidation prediction",
        intervention:
          "Use static-stress transfer model to forecast which positions in the next 24h are most likely to liquidate.",
        outcome: "open",
        evidence:
          "Pre-registered in SIBD-v3-044 execution plan; data harvesting in progress. No prospective result yet — listed here so we don't claim transfer until the test runs.",
        citation: "SIBD-v3-044, this repo.",
      },
    ],
    blocking_mechanisms: [
      "Stress tensor in seismology is a directional 3-tensor; LTV is a scalar. Directional contagion topology between borrowing positions has no natural fault-plane analogue.",
      "Earthquake catalogues span 100+ years with stationary plate tectonics. DeFi protocols rewrite their liquidation logic via governance votes on a monthly timescale — the system is non-stationary.",
      "The empirically-observed Omori p-exponent looks similar in both systems, but the mechanism producing it is different (rate-and-state friction vs forced-deleveraging cascades). Same exponent ≠ same intervention works.",
    ],
    falsifiable_prediction: {
      if_condition:
        "Your DeFi protocol has just experienced a liquidation event larger than 95th percentile of the trailing 90-day distribution.",
      then_observation:
        "Liquidation-event rate over the next 30 days should follow λ(t) = K / (c + t)^p with p ∈ [0.8, 1.2]. Reject if the observed p falls outside [0.6, 1.5] or if a Vuong test prefers lognormal at p < 0.05.",
      timeframe_days: 30,
      how_to_test:
        "1) Timestamp every liquidation event in the 30 days following the trigger. 2) Bin into 6-hour windows. 3) Fit λ(t) = K / (c + t)^p with maximum-likelihood (Clauset 2009). 4) Report p̂, 95% CI, and Vuong LR vs lognormal. Submit your result to the public ledger.",
    },
    scope_statement:
      "This is a structural-similarity case, not a validated investment or risk-management procedure. The same project's Phase Detector NULL backtest is direct evidence that pattern-identification does not imply transferable trading-signal alpha.",
    sibd_seed_ids: ["SIBD-v3-044", "SIBD-v3-047"],
    last_human_review: "2026-05-15",
  },
  {
    id: "powergrid-traffic-cascade",
    title: "Power-grid N-1 contingency ↔ Urban traffic-signal cascade",
    subtitle:
      "Motter-Lai cascade: load redistribution after a node failure shares structure between transmission lines and intersection capacity.",
    domains: {
      a: "Electrical transmission grid cascades",
      b: "Urban traffic-network gridlock cascades",
    },
    universality_class_id: "motter-lai-cascade",
    universality_class_name: "Motter-Lai network cascade",
    shared_equation:
      "L_i(t+1) = L_i(t) + Σ_{j ∈ F(t)} L_j · w_ij / Σ_k w_jk;  node i fails if L_i > C_i",
    variable_mapping: [
      {
        yours: "Intersection throughput capacity (vehicles/hour)",
        analogue: "Transmission line capacity (MW)",
      },
      {
        yours: "Vehicle flow on a road segment",
        analogue: "Power load on a transmission line",
      },
      {
        yours: "Spillover-lockup at a saturated intersection",
        analogue: "Line trip from overload",
      },
      {
        yours: "Coordinated green-wave signal control",
        analogue: "Power-flow re-dispatch / optimal load shedding",
        note: "The control authority is asymmetric: power dispatch is centralized + instantaneous; traffic signals have human re-routing in the loop.",
      },
    ],
    documented_transfers: [
      {
        direction: "Power grid → urban traffic resilience",
        intervention:
          "Apply N-1 contingency analysis (assume any single node fails, check whether the rest can absorb the load) to identify critical intersections.",
        outcome: "succeeded",
        evidence:
          "Multiple transportation-resilience studies (2010–2024) have adopted N-k contingency analysis from power-systems engineering to rank intersections by cascade-vulnerability. The framework transferred cleanly because both systems share an explicit capacity constraint per node.",
        citation:
          "e.g. Zhang et al., 'Cascading failures in urban traffic networks: a structural-vulnerability perspective.' (See SIBD-v3-052 literature column.)",
      },
      {
        direction: "Motter-Lai topology insights → traffic signal optimization",
        intervention:
          "Use eigenvector-centrality-weighted capacity allocation (works for grids) directly as the signal-timing allocation rule.",
        outcome: "partial",
        evidence:
          "Reported gains in steady-state throughput, but transfer fails at the dynamic boundary: traffic agents *re-route* when one intersection saturates; power loads do not 'choose' a path. Studies report 15-30% throughput improvement at low load and reversion to baseline (or worse) at high load.",
        citation: "Transportation Research Part B, multiple studies 2018–2024.",
      },
    ],
    blocking_mechanisms: [
      "Power flow obeys Kirchhoff's laws — algebraic constraints that are instantaneous. Traffic flow is a PDE with delay, queueing, and reaction-time non-linearities.",
      "Vehicles can re-route. Power loads cannot. Adding strategic re-routing to a Motter-Lai model changes the cascade dynamics qualitatively.",
      "Grids have no storage at most nodes (battery storage is the exception). Traffic networks have storage everywhere (queues), which changes the time-constant of cascade propagation.",
    ],
    falsifiable_prediction: {
      if_condition:
        "Your traffic network has detector data for ≥ 50 intersections and ≥ 90 days of cascade-style gridlock events (events where ≥ 3 adjacent intersections saturate within a 15-minute window).",
      then_observation:
        "The distribution of cascade sizes (number of saturated intersections per event) should follow a power law with exponent α ∈ [2.0, 3.5] (the Motter-Lai canonical band). If your observed α falls outside [1.5, 4.0] or a Vuong test prefers exponential at p < 0.05, the cascade is not behaving as a Motter-Lai system and N-1 contingency analysis will mis-rank your critical intersections.",
      timeframe_days: 90,
      how_to_test:
        "1) Extract cascade events from detector data. 2) For each event, count saturated intersections within the 15-min window as the cascade size s. 3) Fit P(s) ~ s^(-α) using Clauset MLE on s ≥ s_min (KS-optimal). 4) Report α, 95% CI, Vuong LR vs exponential and lognormal. Submit to the public ledger.",
    },
    scope_statement:
      "The N-1 contingency framework has cleanly transferred from grids to traffic in academic studies; the dynamic / re-routing extensions have not. This case is the strongest 'transfer works' example in the current library.",
    sibd_seed_ids: ["SIBD-v3-052"],
    last_human_review: "2026-05-15",
  },
  {
    id: "bank-run-defi-depeg",
    title: "Diamond-Dybvig bank run ↔ DeFi stablecoin depeg",
    subtitle:
      "Multiple-equilibria self-fulfilling panic structure shared between retail banking and on-chain stablecoin protocols.",
    domains: {
      a: "Bank runs (Diamond-Dybvig 1983)",
      b: "DeFi stablecoin depeg events",
    },
    universality_class_id: "multiple-equilibria-panic",
    universality_class_name: "Diamond-Dybvig multiple equilibria",
    shared_equation:
      "Expectation → action → self-fulfilling bad equilibrium (jump from good to bad fixed point when belief crosses threshold)",
    variable_mapping: [
      {
        yours: "Stablecoin redemption request",
        analogue: "Deposit withdrawal",
      },
      {
        yours: "Protocol collateral pool",
        analogue: "Bank liquidity reserves",
      },
      {
        yours: "Depeg-anticipation sentiment",
        analogue: "Panic expectation",
        note: "Observability is the big asymmetry — bank-run sentiment is folklore; depeg sentiment is partly visible via on-chain order-book + social signals.",
      },
      {
        yours: "Protocol insurance / backstop fund",
        analogue: "Deposit insurance (FDIC)",
      },
    ],
    documented_transfers: [
      {
        direction: "Bank-run theory → DeFi depeg modeling",
        intervention:
          "Use Goldstein-Pauzner global-games methodology to identify the threshold belief that triggers panic-equilibrium switching.",
        outcome: "partial",
        evidence:
          "The methodology has been ported to several stablecoin post-mortems (UST 2022, USDN, sUSD) and successfully identifies an ex-post panic threshold. Ex-ante prediction has not been demonstrated — the framework labels the equilibrium switch after the fact.",
        citation:
          "Multiple stablecoin-collapse post-mortems 2022-2024 invoking Diamond-Dybvig + Goldstein-Pauzner; see SIBD-v3-048 literature column.",
      },
      {
        direction: "Deposit-insurance design → DeFi protocol-insurance design",
        intervention:
          "Apply Diamond-Dybvig's deposit-insurance equilibrium-stabilization result to size a protocol insurance fund.",
        outcome: "failed",
        evidence:
          "Multiple algorithmic-stablecoin protocols (UST is the canonical case) implemented backstop-fund or stability-pool mechanisms that *mathematically* mirror deposit insurance. Death-spiral mechanics nevertheless triggered — once the backstop token is exposed to the same panic, it inherits the run rather than absorbing it. The intervention did NOT transfer cleanly because the insurance asset is endogenous, not exogenous.",
        citation: "UST collapse May 2022; multiple post-mortems including Liu & Makarov 2023.",
      },
    ],
    blocking_mechanisms: [
      "Bank-run panic is driven by unobservable belief; depeg panic has a partly-observable order-book signal. Sentiment proxies are needed but noisy.",
      "Deposit insurance is exogenous (government-backed). Protocol insurance is usually endogenous (the protocol's own token), so it shares the panic rather than absorbing it.",
      "Bank runs have ATM withdrawal limits and physical cash drag. DeFi redemptions are instantaneous and gas-priced.",
      "Identification problem: panic-driven vs fundamental-driven redemption is hard to distinguish in real time. Goldstein-Pauzner's global-games trick works ex-post but is fragile for ex-ante.",
    ],
    falsifiable_prediction: {
      if_condition:
        "Your stablecoin protocol's redemption volume in the trailing 4 hours exceeds the 99.5th percentile of the trailing 90-day distribution.",
      then_observation:
        "The redemption-arrival process should look multi-modal (two regimes: pre-panic baseline + panic regime) when fitted with a hidden-Markov model with 2 states. Reject the panic-regime hypothesis if a 1-state HMM has better BIC, or if the implied transition probability into the panic state is < 5%.",
      timeframe_days: 7,
      how_to_test:
        "1) Bin redemption requests into 5-minute windows for the trailing 7 days. 2) Fit 1-state and 2-state HMMs. 3) Compare BIC. 4) If 2-state wins, report the steady-state probability of the panic regime and the implied transition matrix. 5) Submit to the public ledger.",
    },
    scope_statement:
      "Multiple-equilibria framing is useful for *ex-post* understanding of depeg events and several stablecoin post-mortems have used it productively. Ex-ante intervention design (e.g. sizing an insurance fund) has documented failures — the canonical case being UST 2022. Treat this case as a vocabulary, not a control law.",
    sibd_seed_ids: ["SIBD-v3-048"],
    last_human_review: "2026-05-15",
  },
];

export function getInsightCase(id: string): InsightCase | undefined {
  return INSIGHT_CASES.find((c) => c.id === id);
}

export function listInsightCases(): InsightCase[] {
  return INSIGHT_CASES;
}

// Visual constants for outcome badges.
export const OUTCOME_LABEL: Record<TransferOutcome, string> = {
  succeeded: "Succeeded",
  partial: "Partial",
  failed: "Failed",
  open: "Untested",
};

export const OUTCOME_BADGE: Record<TransferOutcome, string> = {
  succeeded: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  partial: "bg-amber-50 text-amber-800 ring-amber-200",
  failed: "bg-rose-50 text-rose-800 ring-rose-200",
  open: "bg-zinc-50 text-zinc-700 ring-zinc-200",
};
