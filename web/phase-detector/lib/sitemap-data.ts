// W12-B (session #10, 2026-05-15): sitemap enumeration data.
//
// Tickers + universality class IDs that should appear in sitemap.xml.
// In production these will be fetched from the API; for static export
// the lists are checked into git. Keep in sync with backend taxonomy.

// Top-100 U.S. equity tickers covered by Phase Detector v0.1.
// Source: SP500 + Russell-1000 supplement from public/backtest/ universe.
// Edit this list when the universe changes.
export const PHASE_DETECTOR_TICKERS: string[] = [
  // Mega-cap tech
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO", "ORCL", "ADBE",
  // Semis + hardware
  "INTC", "AMD", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "MRVL", "ARM",
  // SaaS / software
  "CRM", "NOW", "SNOW", "DDOG", "PLTR", "MDB", "NET", "OKTA", "ZS", "CRWD",
  // Financials
  "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "AXP", "SCHW", "USB",
  // Energy
  "XOM", "CVX", "COP", "EOG", "PXD", "SLB", "OXY", "MPC", "PSX", "VLO",
  // Healthcare / biotech
  "JNJ", "UNH", "PFE", "MRK", "ABBV", "TMO", "DHR", "LLY", "AMGN", "BIIB",
  // Consumer + retail
  "WMT", "COST", "HD", "LOW", "TGT", "NKE", "SBUX", "MCD", "BKNG", "CMG",
  // Communication / media
  "DIS", "NFLX", "CMCSA", "T", "VZ", "TMUS", "CHTR", "WBD", "PARA", "FOX",
  // Industrials
  "BA", "CAT", "GE", "HON", "LMT", "RTX", "UNP", "UPS", "FDX", "DE",
  // Other notable (crypto/fintech/EV)
  "COIN", "SQ", "PYPL", "SOFI", "AFRM", "RBLX", "U", "RIVN", "LCID", "ABNB",
];

// Universality class IDs from v4/taxonomy/universality_classes.yaml.
// Kept in sync manually until we wire a build step that reads the YAML.
export const PHASE_DETECTOR_UNIVERSALITY_CLASSES: string[] = [
  "soc_threshold_cascade",
  "multistable_self_fulfilling",
  "equilibrium_critical_ising",
  "reaction_diffusion_turing",
  "delay_differential_debt",
  "kuramoto_sync",
  "preferential_attachment",
  "lotka_volterra_predator_prey",
  "kpz_surface_growth",
  "information_bottleneck_capacity",
  "second_order_damped_oscillator",
  "percolation_connectivity",
];
