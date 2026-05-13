// PR-4: deterministic NLU for the Phase Detector hero search box.
//
// Input: free-form user query (CN or EN, no LLM).
// Output: a routing decision the page can act on:
//   - If query is a bare ticker (2-5 ASCII uppercase letters) → /company/<TICKER>
//   - Else: stay on "/" but produce filters (state / family / sector) that
//     match the keywords detected in the query.
//
// Truth source for family + state codes is lib/labels.ts + lib/types.ts.
// Sector slug mapping is best-effort against common ICS sector names returned
// by the backend; misses fall through and the query is preserved as the raw
// string filter (sector free-text).

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
// Keyword → enum maps. Order matters: longer / more specific phrases first
// so "near critical" wins over "critical".
// ---------------------------------------------------------------------------

const STATE_KEYWORDS: Array<[RegExp, CriticalPointState]> = [
  [/(接近临界|临界附近|崩盘边缘|快崩了|near[\s-]?critical|on the edge)/i, "near_critical"],
  [/(失控通道|失控|超临界|supercritical|runaway|out of control)/i, "supercritical"],
  [/(已翻转|翻转|翻面|tipped|already tipped|post[\s-]?tip)/i, "tipped"],
  [/(稳态|稳定|健康|平稳|subcritical|stable|resilient)/i, "subcritical"],
];

const FAMILY_KEYWORDS: Array<[RegExp, DynamicsFamily]> = [
  [/(临界级联|阈值级联|level cascade|threshold cascade|cascade dynamics|soc)/i, "soc"],
  [/(强者愈强|富者愈富|马太效应|rich[\s-]?get[\s-]?richer|preferential attachment|power law|幂律)/i, "preferential_attachment"],
  [/(临界翻转|临界点|tipping point|tipping|fold|scheffer)/i, "fold"],
  [/(回不去|回不来|路径依赖|滞后|hysteresis|memory effect|path dependence)/i, "hysteresis"],
];

// CN keyword → canonical English sector name (matches backend output).
// These are conservative: if user input doesn't match any key here, sector
// stays unset (so the screener won't over-filter on a stray Chinese word).
const SECTOR_KEYWORDS: Array<[RegExp, string]> = [
  [/(银行|金融|银行业|保险|financial|banking|finance|insurance)/i, "Financial"],
  [/(能源|石油|油气|煤|energy|oil|gas|petroleum)/i, "Energy"],
  [/(半导体|芯片|chip|semiconductor)/i, "Semiconductors"],
  [/(科技|互联网|软件|tech|technology|software|internet)/i, "Technology"],
  [/(电商|零售|消费|retail|e-?commerce|consumer)/i, "Retail"],
  [/(汽车|车企|automotive|automobile|auto)/i, "Automotive"],
  [/(医药|医疗|生物|healthcare|pharma|biotech|medical)/i, "Healthcare"],
  [/(地产|房地产|物业|real estate|property|reit)/i, "Real Estate"],
  [/(电信|通信|telecom|communication)/i, "Communication Services"],
  [/(工业|制造|industrial|manufactur)/i, "Industrials"],
  [/(公用|水电|燃气|utilit)/i, "Utilities"],
  [/(原材料|材料|化工|material|chemical)/i, "Materials"],
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
  "能源失控通道",
  "已翻转科技股",
  "稳态消费",
  "AAPL",
  "TSLA",
];
