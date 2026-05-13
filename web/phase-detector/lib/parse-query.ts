// Deterministic NLU for the Phase Detector hero search box.
//
// Input: free-form user query (CN or EN, no LLM).
// Output: a routing decision the page can act on:
//   - If query is a bare ticker (2-5 ASCII uppercase letters) → /company/<TICKER>
//   - Else: stay on "/" but produce filters (state / family / sector) that
//     match the keywords detected in the query.
//
// 2026-05-14 P0 fix: keyword maps now emit BE canonical v0.2 enum slugs
// (approaching_critical / at_critical / post_critical_transition / etc.),
// NOT the legacy short forms (near_critical / supercritical / tipped) which
// had zero overlap with the BE and produced empty result sets.

import type { CriticalPointState, DynamicsFamily } from "./types";

export interface ParsedQuery {
  query: string;
  route: string; // "/company/AAPL" or "/" (filters applied via URLSearchParams)
  filters: {
    critical_point_state?: CriticalPointState;
    dynamics_family?: DynamicsFamily;
    sector?: string;
  };
  // True if the query looked like a ticker — page can navigate directly.
  isTicker: boolean;
}

// Bare ticker: 2-5 ASCII uppercase letters, optionally with a single dot suffix
// (BRK.B). We accept lowercase input too — the company page is case-insensitive.
const TICKER_RE = /^[A-Za-z]{1,5}(?:\.[A-Za-z])?$/;

// ---------------------------------------------------------------------------
// Keyword → enum maps. Order matters: longer / more specific phrases first.
//
// CPS mapping rationale (BE has no "supercritical" — closest is at_critical
// for "已越过翻车点仍在加速"; post_critical_transition for "已翻转"):
//   接近临界 / 临界附近 / 崩盘边缘  → approaching_critical
//   失控 / 临界点上 / supercritical → at_critical
//   已翻转 / tipped / 翻车 / 暴雷  → post_critical_transition
//   稳态 / 稳定 / 健康 / 远离      → far_from_critical
// ---------------------------------------------------------------------------

const STATE_KEYWORDS: Array<[RegExp, CriticalPointState]> = [
  [
    /(接近临界|临界附近|崩盘边缘|快崩了|near[\s-]?critical|approaching|on the edge)/i,
    "approaching_critical",
  ],
  [
    /(失控通道|失控|超临界|临界点上|at[\s-]?critical|supercritical|runaway|out of control)/i,
    "at_critical",
  ],
  [
    /(已翻转|翻转|翻面|翻车|暴雷|post[\s-]?critical|tipped|already tipped|post[\s-]?tip)/i,
    "post_critical_transition",
  ],
  [
    /(稳态|稳定|健康|平稳|远离|far[\s-]?from|subcritical|stable|resilient)/i,
    "far_from_critical",
  ],
];

const FAMILY_KEYWORDS: Array<[RegExp, DynamicsFamily]> = [
  [
    /(临界级联|阈值级联|threshold cascade|cascade dynamics|\bsoc\b)/i,
    "soc_threshold_cascade",
  ],
  [
    /(强者愈强|富者愈富|马太效应|rich[\s-]?get[\s-]?richer|preferential attachment|power law|幂律)/i,
    "preferential_attachment",
  ],
  [
    /(临界翻转|临界点|tipping point|\btipping\b|\bfold\b|scheffer)/i,
    "scheffer_fold",
  ],
  [
    /(回不去|回不来|路径依赖|滞后|hysteresis|memory effect|path dependence|preisach)/i,
    "hysteresis_preisach",
  ],
  [
    /(网络级联|连锁反应|network cascade|domino|motter|motter[\s-]?lai)/i,
    "motter_lai_cascade",
  ],
  [
    /(反身性|反身性循环|reflexive|reflexivity|soros)/i,
    "reflexive_fixed_point",
  ],
  [
    /(极端尾部|黑天鹅|尾部风险|extreme value|tail risk|fat[\s-]?tail|black swan)/i,
    "extreme_value_tail",
  ],
  [
    /(线性稳态|近线性|稳态线性|quasi[\s-]?equilibrium|linear equilibrium|steady state)/i,
    "linear_quasi_equilibrium",
  ],
  [
    /(复合|混合|待判定|mixed|unclear)/i,
    "mixed_or_unclear",
  ],
];

// CN keyword → BE canonical sector slug (matches /api/screener?sector=...).
// For broad keywords mapping to many BE sectors, we emit the most common
// canonical (e.g. 银行 → financials_bank). Misses fall through so the
// screener won't over-filter on a stray Chinese word.
const SECTOR_KEYWORDS: Array<[RegExp, string]> = [
  // Banking + finance — bank is the broadest single bucket
  [/(银行业|银行|banking|\bbank\b)/i, "financials_bank"],
  [/(保险业|保险|insurance|reinsurance)/i, "financials_insurance"],
  [/(支付|payments?|fintech)/i, "financials_payments"],
  [/(券商|经纪|broker)/i, "financials_retail_broker"],
  [/(加密|币圈|crypto|bitcoin)/i, "financials_crypto"],
  [/(资管|资产管理|asset[\s-]?mgmt|asset management)/i, "financials_asset_mgmt"],
  [/(金融|finance|financial)/i, "financials_bank"],

  // Energy
  [/(油气|石油|原油|oil|gas|petroleum)/i, "energy_oil_gas"],
  [/(光伏|太阳能|solar)/i, "energy_solar"],
  [/(氢能|hydrogen)/i, "energy_hydrogen"],
  [/(炼化|refining)/i, "energy_refining"],
  [/(中游|midstream|pipeline)/i, "energy_midstream"],
  [/(能源|energy)/i, "energy_oil_gas"],

  // Tech / software
  [/(半导体|芯片|chip|semiconductor)/i, "tech_semiconductor"],
  [/(游戏|gaming|games?)/i, "tech_software_gaming"],
  [/(数据库|database|\bdb\b)/i, "tech_software_db"],
  [/(安全|cybersec|security)/i, "tech_software_security"],
  [/(电动车|电车|ev|electric vehicle)/i, "tech_auto_ev"],
  [/(流媒体|streaming)/i, "tech_internet_streaming"],
  [/(中国互联网|china internet)/i, "tech_internet_china"],
  [/(电商|e-?commerce)/i, "tech_software_ecommerce"],
  [/(互联网|internet)/i, "tech_internet"],
  [/(软件|software)/i, "tech_software"],
  [/(硬件|hardware)/i, "tech_hardware"],
  [/(科技|tech|technology)/i, "tech_software"],

  // Healthcare
  [/(制药|药企|pharma)/i, "healthcare_pharma"],
  [/(医疗器械|devices?)/i, "healthcare_devices"],
  [/(生物|biotech)/i, "biotech"],
  [/(医疗|healthcare|medical)/i, "healthcare_pharma"],

  // Consumer
  [/(汽车|车企|automotive|automobile|\bauto\b)/i, "consumer_auto"],
  [/(必需消费|staples)/i, "consumer_staples"],
  [/(非必需|可选消费|discretionary)/i, "consumer_discretionary"],
  [/(零售|retail)/i, "consumer_discretionary_retail"],
  [/(消费|consumer)/i, "consumer_discretionary"],

  // Other
  [/(航空|航天|aerospace)/i, "industrials_aerospace"],
  [/(工业|industrial|manufactur)/i, "industrials_diversified"],
  [/(电信|通信|telecom|communication)/i, "telecom"],
  [/(媒体|娱乐|media|entertainment)/i, "media_entertainment"],
];

function detect<T>(
  pairs: Array<[RegExp, T]>,
  text: string,
): T | undefined {
  for (const [re, value] of pairs) {
    if (re.test(text)) return value;
  }
  return undefined;
}

/**
 * Parse a free-form query into a route + filter combination.
 * Pure function — safe to call in render / handler / test.
 */
export function parseQuery(input: string): ParsedQuery {
  const query = (input ?? "").trim();
  if (!query) {
    return { query: "", route: "/", filters: {}, isTicker: false };
  }

  // Bare ticker → /company/<ticker>. Uppercase for the URL even if user typed
  // lowercase (company route does case-insensitive match server-side, but
  // uppercase URLs are the canonical form).
  if (TICKER_RE.test(query)) {
    const ticker = query.toUpperCase();
    return {
      query,
      route: `/company/${encodeURIComponent(ticker)}`,
      filters: {},
      isTicker: true,
    };
  }

  const state = detect(STATE_KEYWORDS, query);
  const family = detect(FAMILY_KEYWORDS, query);
  const sector = detect(SECTOR_KEYWORDS, query);

  const filters: ParsedQuery["filters"] = {};
  if (state) filters.critical_point_state = state;
  if (family) filters.dynamics_family = family;
  if (sector) filters.sector = sector;

  // Build query string for the home route. Page reads via useSearchParams.
  const params = new URLSearchParams();
  if (filters.critical_point_state) params.set("state", filters.critical_point_state);
  if (filters.dynamics_family) params.set("family", filters.dynamics_family);
  if (filters.sector) params.set("sector", filters.sector);
  // Always carry the raw query so the page can highlight / log it.
  if (query) params.set("q", query);
  const qs = params.toString();

  return {
    query,
    route: qs ? `/?${qs}` : "/",
    filters,
    isTicker: false,
  };
}

// Curated example queries surfaced as autocomplete fallbacks / chips.
// Plain Chinese, no internal codenames (per PR-1 copy sweep).
export const EXAMPLE_QUERIES: string[] = [
  "银行接近临界",
  "能源临界点上",
  "已翻转科技股",
  "稳态消费",
  "AAPL",
  "TSLA",
];
