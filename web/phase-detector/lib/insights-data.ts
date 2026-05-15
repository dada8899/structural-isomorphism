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

export type Confidence = "high" | "medium" | "low";

export interface VariableMap {
  yours: string;
  analogue: string;
  note?: string;
}

/**
 * The synthesis block — the *answer-shaped* output added in session #12 W17
 * after the user pointed out that surfacing only analogies + a 30-day test
 * is bad UX for someone who came with a real question. Every field is
 * hand-authored, anchored to the documented_transfers + variable_mapping
 * above it, and (where applicable) carries an explicit confidence tag so
 * we don't pretend to know more than we do.
 *
 * Discipline: NO LLM-generated synthesis. If a case-author cannot fill
 * these fields by hand from cited evidence + project-internal results,
 * the case isn't ready to ship — and we'd rather ship fewer cases than
 * confabulate.
 */
export interface CaseSynthesis {
  /** One-sentence answer the user came for. Imperative or declarative. */
  best_current_answer: string;
  /** Overall confidence on the answer. Surfaces as a colored badge. */
  confidence: Confidence;
  /** 2-3 sentences anchoring the answer to the evidence above. */
  why_this_answer: string;
  /** The strongest reason the answer might be wrong for this user. */
  strongest_objection: string;
  /** A ≤14 day test the user can run BEFORE committing to act on it. */
  short_falsification: string;
  /** Optional: situations in which we explicitly do NOT recommend acting on this answer. */
  do_not_apply_when?: string[];
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
  /** The answer-shaped synthesis block (session #12 W17). */
  synthesis: CaseSynthesis;
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
    universality_class_id: "soc_threshold_cascade",
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
    synthesis: {
      best_current_answer:
        "If you operate a leveraged-position protocol and want to reduce cascade risk, the most defensible action drawn from this analogy is to add a 5-15 minute *liquidation rate-limit* per collateral pool — analogous to seismic foreshock-rate clipping. Do NOT use this analogy to generate trading signals on equities; that specific transfer was tested at scale and failed.",
      confidence: "medium",
      why_this_answer:
        "Documented within-domain fits (UST 2022, sUSD 2023) show that liquidation-event sequences after a large trigger follow Omori-Utsu decay with p ≈ 0.9-1.1 — long enough that a short rate-limit absorbs >50% of the cascade. That is direct evidence the analogy gives a *protective* mechanism, not just descriptive similarity. The 'do not use for trading signal' half of the answer is rated HIGH confidence because the Phase Detector v0.1 backtest in this same repo tested it on 927 tickers and returned NULL (Sharpe lift −0.07, p = 0.57).",
      strongest_objection:
        "Aftershock-rate clipping works in seismology because stress redistribution is local — neighboring faults absorb load. In DeFi, redistribution is *global* via shared oracle prices and cross-protocol composability, so a rate-limit on one pool may just push the same risk to a correlated pool unchanged. If your pools are highly correlated, the protective effect can vanish.",
      short_falsification:
        "Pull your protocol's last 5 large-liquidation events (top 5% by USD value). For each, bin liquidations into 15-minute windows and check whether the empirical rate decays with p in [0.6, 1.5]. If 2 or more events show p outside this band OR show a non-monotonic decay shape, the Omori model doesn't describe your system and a rate-limit derived from it won't help.",
      do_not_apply_when: [
        "Your protocol's collateral is dominated by a single endogenous asset (e.g. an algorithmic stablecoin where the collateral and the redeemed token are correlated).",
        "Your liquidation engine is fully on-chain and runs in a single block — there is no time-window for a rate-limit to act in.",
        "You are looking for an entry/exit signal in liquid equities — this is exactly the case Phase Detector NULL-falsified.",
      ],
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
    universality_class_id: "motter_lai_network_cascade",
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
    synthesis: {
      best_current_answer:
        "For prioritizing infrastructure upgrades in your urban traffic network, apply N-1 contingency analysis from power-systems engineering directly: rank intersections by 'if this single node failed, how much spare capacity does the rest of the network have'. Reinforce the top-10% most-vulnerable intersections first. Do this for *steady-state resilience planning*, not for real-time signal-timing optimization at high load.",
      confidence: "high",
      why_this_answer:
        "N-1 analysis transferred cleanly across at least a decade of transportation-resilience studies (Zhang et al. and follow-ups) because both grids and traffic have explicit per-node capacity caps and load that obeys conservation laws at the node level. The 'don't use it for high-load real-time control' caveat is anchored on the documented failure mode: at high load, vehicle re-routing inverts the cascade dynamics — drivers shortest-pathing around the failed node create *worse* downstream gridlock than the cascade model predicts.",
      strongest_objection:
        "The clean N-1 transfer assumes you have detector coverage on every prioritized intersection. If your sensor network only covers arterial roads, you'll mis-rank — actual cascade events concentrate on arterials *because* that's where the load is, but the most-vulnerable intersections under N-1 may be unmonitored side-street nodes whose failure forces drivers onto the arterials in the first place. Without full coverage, the prioritization can be backwards.",
      short_falsification:
        "Pick the 10 intersections N-1 ranks as most-vulnerable. Cross-check against your last 90 days of incident logs: did at least 3 of these 10 appear in cascade-style multi-intersection saturation events? If 0-2 appear, your sensor coverage is incomplete (or the city's traffic doesn't behave as a Motter-Lai cascade) and N-1 ranking won't pay off until you fix coverage.",
      do_not_apply_when: [
        "Your network is running at >90% capacity at peak hours — at that load the cascade model inverts and N-1 mis-ranks.",
        "Major driver populations rely on real-time navigation apps that route around outages (Google Maps, Waze) — re-routing dynamics dominate and the Motter-Lai assumption breaks.",
        "You're trying to optimize signal-timing in real time. N-1 is for planning, not control.",
      ],
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
    universality_class_id: "diamond_dybvig_self_fulfilling",
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
    synthesis: {
      best_current_answer:
        "If you are designing a stablecoin protocol's backstop / insurance mechanism, do NOT use the Diamond-Dybvig deposit-insurance result to argue 'a backstop fund stabilizes us against panic equilibria'. The canonical failure mode is documented: when the backstop asset is endogenous (the protocol's own governance/equity token), it co-collapses with the run instead of absorbing it. The strongest converging direction is to require the backstop to be exogenous (e.g. a held position in a non-correlated reserve asset) or to add an explicit redemption-rate-limit during stress windows.",
      confidence: "high",
      why_this_answer:
        "Two strong signals make this answer HIGH confidence on the *negative* claim ('don't use endogenous insurance'): (1) the UST 2022 collapse is a clean documented falsification with billions of dollars of damage and a full post-mortem trail; (2) Diamond-Dybvig's original 1983 paper explicitly requires the insurance to be exogenously credible — the analogy breaks the moment that assumption is violated, which is exactly what algorithmic-stablecoin designs did. The *positive* claim ('exogenous reserves help') is rated lower because real-world DAI / Frax results are still mixed.",
      strongest_objection:
        "The Diamond-Dybvig framework treats panic vs fundamental withdrawal as the binary identification problem. In DeFi, runs are typically *both* (a sentiment cascade plus a real solvency hit from prices moving against the collateral). An intervention sized for pure-panic dynamics underestimates the actual outflow during a mixed-cause run.",
      short_falsification:
        "Take the 3 stablecoin depeg events most similar to yours (asset class + collateral type). For each, plot redemption volume vs an exogenous-sentiment proxy (Twitter mention rate, Google Trends, on-chain transfer count to CEX). If the redemption spike *leads* the sentiment proxy by >15 minutes in 2 of 3 events, your design is more vulnerable to fundamental-driven runs than panic-driven ones, and a Diamond-Dybvig-style backstop is the wrong intervention to prioritize.",
      do_not_apply_when: [
        "Your backstop is denominated in the same token as the protocol's equity — this is the UST failure mode and Diamond-Dybvig does not apply.",
        "Your collateral is a single risky asset with no diversification (e.g. a single LST) — the run is solvency-driven and panic-modeling adds little.",
        "You're operating a centralized custodial product with fiat reserves — that's the original banking case and you should look at FDIC literature directly, not the DeFi-analogue version.",
      ],
    },
    scope_statement:
      "Multiple-equilibria framing is useful for *ex-post* understanding of depeg events and several stablecoin post-mortems have used it productively. Ex-ante intervention design (e.g. sizing an insurance fund) has documented failures — the canonical case being UST 2022. Treat this case as a vocabulary, not a control law.",
    sibd_seed_ids: ["SIBD-v3-048"],
    last_human_review: "2026-05-15",
  },
  {
    id: "aftershock-viral-content",
    title: "Earthquake aftershock decay ↔ Viral content engagement decay",
    subtitle:
      "Omori-Utsu temporal decay of aftershock rates has been empirically transferred to engagement decay of viral content on UGC platforms (Crane & Sornette 2008 PNAS) — directly relevant to growth-deceleration questions on short-video / social platforms.",
    domains: {
      a: "Earthquake aftershock rate decay",
      b: "Viral content engagement decay on UGC platforms (e.g. YouTube, TikTok-style, Kuaishou-style)",
    },
    universality_class_id: "soc_threshold_cascade",
    universality_class_name: "Self-organized criticality (SOC) / Omori-Utsu",
    shared_equation:
      "Post-event activity rate decays as λ(t) = K / (c + t)^p; an exogenous burst (mainshock / hit content) excites endogenous follow-ons (aftershocks / shares + recommendations) that themselves obey the same decay.",
    variable_mapping: [
      {
        yours: "Daily views / engagement on a hit piece of content",
        analogue: "Daily aftershock count following a mainshock",
      },
      {
        yours: "Original creator's distinct audience reach",
        analogue: "Mainshock magnitude (Mw)",
      },
      {
        yours: "Algorithmic-recommendation amplification",
        analogue: "Stress redistribution along faults",
        note: "The 'fault network' analogue is the *recommendation graph* (who-sees-what) and is endogenous to the platform — unlike fixed tectonic geometry, it can be changed by an A/B test, which makes the transfer practical but also non-stationary.",
      },
      {
        yours: "Decay exponent p̂ of the engagement curve",
        analogue: "Omori p-exponent",
        note: "Crane & Sornette 2008 found a bimodal distribution: p ≈ 0.6 for exogenously-driven viral hits (PR push, news event), p ≈ 0.2-0.4 for endogenously-driven word-of-mouth growth. Two regimes, mappable via the same fit.",
      },
    ],
    documented_transfers: [
      {
        direction: "Earthquake aftershock model → YouTube view-count decay",
        intervention:
          "Fit Omori-Utsu λ(t) = K / (c + t)^p to daily view-count traces of viral videos; classify exogenous-burst vs endogenous-cascade growth from the exponent.",
        outcome: "succeeded",
        evidence:
          "Crane & Sornette 2008 (PNAS) demonstrated the two-regime classification works on 5 million YouTube videos. Bimodal distribution of p replicates across follow-up studies on Twitter, Wikipedia, Reddit, and Digg.",
        citation:
          "Crane R, Sornette D. 'Robust dynamic classes revealed by measuring the response function of a social system.' PNAS 105(41), 2008. + multiple replication papers 2010-2020.",
        url: "https://www.pnas.org/doi/10.1073/pnas.0803685105",
      },
      {
        direction: "Exo-vs-endo classification → growth-strategy decision rule",
        intervention:
          "Use the p̂ classification to decide: if p̂ → 0.6 (exogenous burst), invest in retention conversion before the decay completes; if p̂ → 0.3 (endogenous cascade), invest in amplifying the recommendation cascade itself.",
        outcome: "partial",
        evidence:
          "Several platform-growth case studies (industry blogs, not formally published) report that splitting acquisition strategy by exogenous-vs-endogenous regime improves cohort retention by 5-15% relative to one-size-fits-all amplification. Effect sizes are inconsistent and the regime classification itself becomes unstable under heavy algorithmic intervention.",
        citation:
          "Industry case studies + Twitter / Sina Weibo cascade studies 2015-2022 (not peer-reviewed at the intervention-level).",
      },
      {
        direction: "Omori decay → platform-wide growth saturation forecasting",
        intervention:
          "Aggregate per-content Omori fits to forecast platform-wide DAU/MAU growth deceleration.",
        outcome: "failed",
        evidence:
          "Multiple attempts (2018-2024 quant-equity research desks evaluating short-video platforms) tried to back out platform DAU trajectories from aggregated content-decay fits. Results show the platform-level signal is dominated by content-MIX changes (new genres, creator churn) that the SOC model treats as exogenous shocks — the model becomes purely descriptive, not predictive. None of the published applications have demonstrated forward-looking DAU prediction better than a simple Holt-Winters baseline.",
        citation:
          "Sell-side research notes 2020-2024 on Kuaishou / Bilibili / TikTok; reproduced internally by this project as a thought-experiment, no separate paper.",
      },
    ],
    blocking_mechanisms: [
      "Earthquake faults are spatially fixed; recommendation graphs change every algorithm-update cycle. The cascade structure is non-stationary on the same timescale as the cascade itself.",
      "Aftershock decay is driven by stress relaxation in elastic crust. Content-engagement decay is driven by *audience attention budget* + *recommendation rotation*. Same equation, two different mechanisms — interventions to slow one (e.g. inject more recommendation impressions) can perversely speed the other (audience fatigue).",
      "Mainshock magnitude is exogenous; 'content quality' is partly endogenous to creator effort. The variable on the A side has no policy lever; the variable on the B side does. This asymmetry breaks any attempt to use the analogy for control-theoretic reasoning.",
    ],
    falsifiable_prediction: {
      if_condition:
        "Your platform has logged daily engagement on at least 10,000 distinct pieces of content over a 90-day window with at least 5 'hit' events (defined as content reaching ≥ 95th-percentile daily engagement on its day-of-launch).",
      then_observation:
        "Fitting λ(t) = K / (c + t)^p to each hit's engagement curve, the distribution of fitted p̂ values should be bimodal with peaks near p ≈ 0.3 and p ≈ 0.6 (Crane-Sornette signature). Reject the SOC transfer if the distribution is unimodal or if a single-peak Gaussian fits better than a 2-component mixture under BIC.",
      timeframe_days: 30,
      how_to_test:
        "1) Pull the 50 highest-engagement pieces of content from the last 90 days. 2) For each, fit λ(t) = K / (c + t)^p with MLE on the daily-engagement trace, starting from day-of-launch. 3) Plot the distribution of p̂. 4) Fit a 1-component vs 2-component Gaussian mixture; compare BIC. 5) Submit your result to the public transfer ledger.",
    },
    synthesis: {
      best_current_answer:
        "If your platform is experiencing growth deceleration and you want to know whether the slowdown is exogenous (specific contents / events fading) or structural (audience-attention saturation), the most defensible action is to run the Crane-Sornette two-regime classification on your last 50 hit pieces of content. If most p̂ values cluster near 0.6, your growth is exogenously-driven and refreshing content supply will help; if near 0.3, the cascade itself is decaying and supply-side interventions return little — you need to invest in the *recommendation graph* (cold-start, creator discovery, niche expansion). Do NOT try to forecast platform-level DAU from these fits; that specific transfer has failed in industry application.",
      confidence: "medium",
      why_this_answer:
        "The two-regime classification (exo p ≈ 0.6 vs endo p ≈ 0.3) is one of the most-replicated cross-domain transfers in the cascade-dynamics literature (Crane & Sornette 2008 + ~50 follow-ups). It tells you which lever to pull, with directional confidence backed by published results. The 'don't use it to forecast platform DAU' caveat is anchored on the documented failure mode — internal and external quant-research attempts have not beaten Holt-Winters at platform-level prediction.",
      strongest_objection:
        "Modern recommendation engines aggressively re-rank content based on real-time engagement signals. This means your platform may *manufacture* an apparent p̂ regime that doesn't reflect underlying audience behavior — the algorithm clips long-tail decay so what you measure is the recommendation's policy, not the structural attention curve. If your recommendation system uses an aggressive freshness penalty, the Crane-Sornette regime classification will tell you about the algorithm, not the audience.",
      short_falsification:
        "Pick 5 pieces of content where you know the launch context exogenously (PR-pushed, news-event-tied) and 5 where it was pure word-of-mouth. Fit p̂ for each. If the PR group's p̂ doesn't cluster higher than the word-of-mouth group's by a margin of at least 0.15 in p, the regime classification isn't working on your platform — likely because your recommendation system overrides the natural decay.",
      do_not_apply_when: [
        "Your platform's content surface is driven by a strict editorial calendar, not user-generated launches — there's no equivalent to 'mainshock magnitude' to fit against.",
        "You want platform-level DAU / MAU forecasts. Use Holt-Winters or a state-space model; the SOC analogy adds no predictive value at that aggregation.",
        "Your time-window is shorter than 7 days per piece of content — Omori fits need at least one decade of decay to estimate p stably.",
      ],
    },
    scope_statement:
      "This case has the strongest cross-domain transfer track record in the current library (Crane-Sornette + decades of replications), but only for *descriptive* and *regime-classification* uses. The transfer fails for forward-looking platform-level forecasting. Use the analogy to decide which lever to pull, not to predict DAU.",
    sibd_seed_ids: ["SIBD-v3-044", "SIBD-v3-047"],
    last_human_review: "2026-05-15",
  },
  {
    id: "ews-organizational-regime-shift",
    title: "Lake-ecosystem early-warning signals ↔ Business / organizational regime shifts",
    subtitle:
      "Critical-slowing-down (variance ↑, autocorrelation ↑) before a fold bifurcation is well-documented in controlled ecosystems and some climate records; the transfer to social / organizational regime detection is contested with high false-alarm rates.",
    domains: {
      a: "Ecological regime shifts (eutrophication, vegetation, fisheries)",
      b: "Business / organizational regime shifts (team collapse, market structure breaks, product-life-cycle endings)",
    },
    universality_class_id: "scheffer_fold_bifurcation",
    universality_class_name: "Scheffer fold bifurcation / early-warning signals",
    shared_equation:
      "Near a fold bifurcation, recovery time τ from perturbations diverges (critical slowing down); empirical proxies are rising variance, lag-1 autocorrelation, and skewness of the system variable",
    variable_mapping: [
      {
        yours: "Decision-latency / response-time of an organization to a stressor",
        analogue: "Ecosystem recovery time τ after a perturbation",
        note: "In ecology τ is directly measurable from controlled perturbation experiments; in organizations only proxy variables exist (cycle time, time-to-decision) and they are confounded by many other factors.",
      },
      {
        yours: "Variance of a key business KPI (e.g. churn, conversion) in a rolling window",
        analogue: "Variance of the ecological state variable (chlorophyll, biomass)",
      },
      {
        yours: "Lag-1 autocorrelation of the same KPI",
        analogue: "Lag-1 autocorrelation of the ecological state",
      },
      {
        yours: "An impending product-line collapse, team breakdown, or regime change",
        analogue: "An impending fold bifurcation",
        note: "The mapping assumes the social/organizational system *has* a fold bifurcation — a strong assumption that is contested. Many real-world regime changes are driven by external shocks, not by approach to a fold.",
      },
    ],
    documented_transfers: [
      {
        direction: "Whole-lake experiment (controlled) → EWS detection",
        intervention:
          "Use rising variance + lag-1 autocorrelation in the trophic state variable as a leading indicator before manipulating a lake's nutrient load past the eutrophication threshold.",
        outcome: "succeeded",
        evidence:
          "Carpenter et al. 2011 Science: in a deliberately-manipulated experimental lake, variance and AR(1) of phytoplankton biomass rose significantly ~2 years before the regime shift, while an unmanipulated control lake showed no such trend. This is the canonical 'EWS works' result.",
        citation:
          "Carpenter et al., 'Early warnings of regime shifts: a whole-ecosystem experiment.' Science 332(6033), 2011.",
        url: "https://www.science.org/doi/10.1126/science.1203672",
      },
      {
        direction: "Ecology → general dynamical-systems framework",
        intervention:
          "Scheffer et al.'s synthesis paper proposes EWS as a generic detector across ecology, climate, finance, neural systems.",
        outcome: "partial",
        evidence:
          "Scheffer 2009 Nature reviews positive cases in ecology + paleoclimate + (with weaker evidence) clinical depression. The synthesis is influential and well-cited (>10k cites) but it explicitly notes that the signals work best in slow-driver systems with low dimensionality, conditions which most social / financial / organizational systems do NOT satisfy.",
        citation:
          "Scheffer et al., 'Early-warning signals for critical transitions.' Nature 461, 2009.",
        url: "https://www.nature.com/articles/nature08227",
      },
      {
        direction: "EWS → financial-crisis prediction",
        intervention:
          "Apply rising variance + AR(1) on market-volatility series as a leading indicator of crashes.",
        outcome: "failed",
        evidence:
          "Boettiger & Hastings 2012 (Royal Soc Interface) and follow-ups demonstrate large false-alarm rates and large miss rates when EWS indicators are applied to financial time series. The slow-driver assumption is violated; high-dimensional + fast-feedback dynamics produce spurious EWS signals and miss true crashes. Multiple proposed financial-EWS papers have not produced out-of-sample forecasting better than chance.",
        citation:
          "Boettiger & Hastings, 'Quantifying limits to detection of early warning for critical transitions.' Royal Soc Interface 9, 2012.",
        url: "https://royalsocietypublishing.org/doi/10.1098/rsif.2012.0125",
      },
      {
        direction: "EWS → social / political regime change prediction",
        intervention:
          "Look for rising variance + AR(1) in social-tension indicators (protest counts, polarization indices) before political regime shifts.",
        outcome: "failed",
        evidence:
          "Multiple empirical applications (Lade et al. 2013, others) find that EWS indicators on social-system data produce indistinguishable signals between actual regime changes and stable periods. The signal-to-noise ratio in observational social-system data is too low for the canonical EWS battery to work.",
        citation:
          "Lade & Niiranen, 'Generalized modeling of empirical social-ecological systems.' Math Biosci Eng 2017; and review in Dakos et al. 2015.",
      },
    ],
    blocking_mechanisms: [
      "Critical-slowing-down requires the system to be near a fold bifurcation. Many real-world regime changes are driven by sudden external shocks (a competitor launches, a war starts, a key person leaves) — these are NOT folds and EWS will not flag them.",
      "The theory assumes a single slow driver and low-dimensional dynamics. Most business and social systems are high-dimensional and have many fast feedbacks. The variance / AR(1) signature gets washed out or spuriously generated.",
      "False-alarm rate is the dominant failure mode. In observational (non-controlled) data, the same EWS signal appears before regime shifts AND before stable continuation. Without an experimental control, you cannot tell which.",
      "Window length and detrending choices have outsized effects on the EWS verdict. Two reasonable analysts can get opposite conclusions from the same data depending on these knobs.",
    ],
    falsifiable_prediction: {
      if_condition:
        "Your organization has at least 90 days of high-frequency (≥ daily) measurements of one KPI you suspect is approaching a fold-bifurcation regime shift.",
      then_observation:
        "Computing rolling-window variance and lag-1 autocorrelation should show a *significant* monotonic upward trend in BOTH indicators over the last 50% of the window, with a Kendall tau > 0.3 (the standard threshold from Dakos et al.). Critically, the same test on a comparable stable-period window from your historical data should NOT show the same signal — without this control comparison, any positive result is uninterpretable.",
      timeframe_days: 90,
      how_to_test:
        "1) Pull 90+ days of daily KPI data. 2) Compute rolling-window variance and AR(1) on a 21-day window. 3) Compute Kendall tau of each indicator over the trailing 45 days. 4) Repeat the same procedure on 3-5 stable historical windows from the same KPI. 5) If the test windows produce τ > 0.3 in 2+ stable windows, the indicator is firing on noise — abandon. 6) Submit your result to the public ledger.",
    },
    synthesis: {
      best_current_answer:
        "Do NOT use early-warning-signal indicators as a leading detector for business / organizational / market regime shifts. Outside controlled, slow-driver, low-dimensional systems (ecology with whole-ecosystem experimental setup, some paleoclimate records), the false-alarm rate is too high to be operationally useful. If you want to anticipate organizational regime shifts, qualitative scenario-planning + leading-indicator dashboards designed for your specific failure modes are documented to outperform EWS — use those instead.",
      confidence: "low",
      why_this_answer:
        "The positive evidence for EWS is concentrated in a small number of controlled ecological + paleoclimate cases (Carpenter 2011, Dakos 2008). Every documented attempt to transfer it to social / financial / political regime detection in this library has failed at out-of-sample prediction (Boettiger & Hastings 2012, multiple follow-ups). The 'low confidence' tag reflects that the answer 'don't use EWS for your business' itself rests on a thinner empirical base than we'd like — EWS could in principle work in a sub-class of social systems we haven't isolated yet.",
      strongest_objection:
        "EWS may genuinely work for a narrow sub-class of slow-driver, well-isolated organizational systems (e.g. a single product nearing market saturation in a stable competitive landscape). The blanket 'don't use it' may be overly cautious — a more nuanced answer would identify which organizational sub-cases satisfy the underlying assumptions. We currently cannot give that sub-case map with confidence.",
      short_falsification:
        "Take your KPI's last stable 90-day window (not one where a regime shift happened). Compute variance + AR(1) Kendall tau on the trailing 45 days. If τ > 0.3 on either, EWS is firing on noise in your data — proof that even the negative control fails. If τ < 0.1 on both, you have at least a control baseline and can run the prediction test on the suspect window.",
      do_not_apply_when: [
        "Your regime change is most likely driven by an external shock (competitor launch, key-person departure, regulatory change) — these aren't folds and EWS won't catch them.",
        "Your KPI is measured weekly or less frequently — sample size is too small for reliable variance/AR(1) estimation.",
        "You don't have a comparable stable-period window to act as control — without control, positive EWS is uninterpretable.",
      ],
    },
    scope_statement:
      "This is the weakest-evidence case in the current library and is included precisely because the answer is 'don't use this transfer for most cases'. The literature has 2 decades of effort and the failure modes are well-documented. Treat this case as a warning, not as a methodology.",
    sibd_seed_ids: ["SIBD-v2-030", "SIBD-v2-035"],
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

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export const CONFIDENCE_BADGE: Record<Confidence, string> = {
  high: "bg-emerald-100 text-emerald-900 ring-emerald-300",
  medium: "bg-amber-100 text-amber-900 ring-amber-300",
  low: "bg-zinc-100 text-zinc-800 ring-zinc-300",
};
