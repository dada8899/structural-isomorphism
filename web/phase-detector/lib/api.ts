// API client for Structural Labs · Phase backend (W3-B endpoints).
// Falls back to mock data when NEXT_PUBLIC_USE_MOCK=true.

import type {
  Company,
  ScreenerFilters,
  Stats,
  UniversalityClassDetail,
  UniversalityClassesResponse,
  UniversalityCompaniesResponse,
  EwsResultFull,
  EwsCard,
  EwsMeta,
  EwsLeaderboardFilters,
} from "./types";
import {
  MOCK_COMPANIES,
  MOCK_STATS,
  MOCK_EWS_LEADERBOARD,
  MOCK_EWS_DETAIL,
  MOCK_EWS_META,
} from "./mock-data";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

function buildQuery(filters: ScreenerFilters): string {
  const params = new URLSearchParams();
  if (filters.dynamics_family) params.set("dynamics_family", filters.dynamics_family);
  if (filters.critical_point_state) params.set("critical_point_state", filters.critical_point_state);
  if (filters.sector) params.set("sector", filters.sector);
  if (typeof filters.min_confidence === "number") {
    params.set("min_confidence", filters.min_confidence.toString());
  }
  if (typeof filters.limit === "number") {
    params.set("limit", filters.limit.toString());
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

function filterMock(filters: ScreenerFilters): Company[] {
  return MOCK_COMPANIES.filter((c) => {
    if (filters.dynamics_family && c.dynamics_family !== filters.dynamics_family) return false;
    if (filters.critical_point_state && c.critical_point_state !== filters.critical_point_state)
      return false;
    if (filters.sector && c.sector !== filters.sector) return false;
    if (
      typeof filters.min_confidence === "number" &&
      c.extraction_confidence < filters.min_confidence
    )
      return false;
    return true;
  }).slice(0, filters.limit ?? 50);
}

// W6-E P1 fix: defensive JSON parse — malformed/empty responses no longer
// throw uncaught, they return null and the caller's catch path handles it.
async function safeJson<T>(res: Response): Promise<T | null> {
  try {
    const text = await res.text();
    if (!text) return null;
    return JSON.parse(text) as T;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn("[api] malformed JSON response:", err);
    return null;
  }
}

export async function fetchScreener(filters: ScreenerFilters): Promise<Company[]> {
  if (USE_MOCK) {
    // Simulate latency so loading state is testable.
    await new Promise((r) => setTimeout(r, 120));
    return filterMock(filters);
  }
  const url = `${API_BASE}/screener${buildQuery(filters)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`screener fetch failed: ${res.status} ${res.statusText}`);
  const json = await safeJson<Company[] | { results: Company[] }>(res);
  if (!json) return [];
  // Accept either array or { results: [] } envelope.
  return Array.isArray(json) ? json : (json.results ?? []);
}

export async function fetchCompany(ticker: string): Promise<Company> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 80));
    const c = MOCK_COMPANIES.find(
      (m) => m.ticker.toLowerCase() === ticker.toLowerCase()
    );
    if (!c) throw new Error(`company ${ticker} not found (mock)`);
    return c;
  }
  const url = `${API_BASE}/company/${encodeURIComponent(ticker)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`company fetch failed: ${res.status} ${res.statusText}`);
  const json = await safeJson<Company>(res);
  if (!json) throw new Error(`company ${ticker} returned empty body`);
  return json;
}

export async function fetchStats(): Promise<Stats> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 40));
    return MOCK_STATS;
  }
  const url = `${API_BASE}/stats`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`stats fetch failed: ${res.status} ${res.statusText}`);
  const json = await safeJson<Stats>(res);
  if (!json) throw new Error("stats returned empty body");
  return json;
}

// ---------------------------------------------------------------------------
// W10-E — Universality class fetchers.
// Mock path: synthesizes a tiny shape from MOCK_COMPANIES so the /compare
// + /universality pages still render in mock mode for screenshot tests.
// ---------------------------------------------------------------------------

export async function fetchUniversalityClasses(): Promise<UniversalityClassesResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 40));
    const ids = Array.from(
      new Set(
        MOCK_COMPANIES.map((c) => c.universality_class).filter(
          (x): x is string => !!x,
        ),
      ),
    );
    return {
      count: ids.length,
      classes: ids.map((id) => ({
        class_id: id,
        display_name: id,
        definition: "Mock universality class",
        status: "emerging",
        exponent_band: [],
        evidence_count: 0,
      })),
    };
  }
  const url = `${API_BASE}/api/universality/classes`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok)
    throw new Error(`universality classes fetch failed: ${res.status} ${res.statusText}`);
  const json = await safeJson<UniversalityClassesResponse>(res);
  if (!json) return { count: 0, classes: [] };
  return json;
}

export async function fetchUniversalityClassDetail(
  classId: string,
): Promise<UniversalityClassDetail> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 40));
    return {
      class_id: classId,
      display_name: classId,
      definition: "Mock universality class definition.",
      status: "emerging",
      key_invariants: ["Mock invariant 1", "Mock invariant 2"],
      shared_equation: "",
      evidence_systems: [],
      negative_examples: [],
      edge_cases: [],
      references: [],
      prototypes: [],
      source: "mock",
    };
  }
  const url = `${API_BASE}/api/universality/classes/${encodeURIComponent(classId)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok)
    throw new Error(
      `universality class detail fetch failed: ${res.status} ${res.statusText}`,
    );
  const json = await safeJson<UniversalityClassDetail>(res);
  if (!json) throw new Error("universality class detail returned empty body");
  return json;
}

// ---------------------------------------------------------------------------
// 2026-05-23 PD-EWS — Early-Warning-Signal endpoints.
// These are the real-data path (rolling AR1 / variance Kendall-tau over real
// OHLCV). The /screener + /company endpoints above stay for back-compat /
// the LLM-narrative side.
// ---------------------------------------------------------------------------

export async function fetchEwsLeaderboard(
  filters: EwsLeaderboardFilters = {},
): Promise<EwsCard[]> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 60));
    return filterMockLeaderboard(filters);
  }
  const p = new URLSearchParams();
  if (filters.market) p.set("market", filters.market);
  if (filters.phase) p.set("phase", filters.phase);
  if (filters.sector) p.set("sector", filters.sector);
  if (typeof filters.min_score === "number") p.set("min_score", String(filters.min_score));
  if (typeof filters.min_confidence === "number")
    p.set("min_confidence", String(filters.min_confidence));
  if (typeof filters.limit === "number") p.set("limit", String(filters.limit));
  const qs = p.toString();
  const url = `${API_BASE}/api/ews/leaderboard${qs ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    // Degrade gracefully — frontend should render a "data refreshing" state
    // rather than crash. The leaderboard JSON might not exist yet on first
    // deploy before the cron has run.
    if (res.status === 404 || res.status === 503) return [];
    throw new Error(`ews leaderboard failed: ${res.status}`);
  }
  const json = await safeJson<EwsCard[]>(res);
  return Array.isArray(json) ? json : [];
}

export async function fetchEwsDetail(ticker: string): Promise<EwsResultFull | null> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 60));
    return MOCK_EWS_DETAIL[ticker.toUpperCase()] ?? null;
  }
  const url = `${API_BASE}/api/ews/${encodeURIComponent(ticker)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (res.status === 404 || res.status === 503) return null;
  if (!res.ok) throw new Error(`ews detail failed: ${res.status}`);
  return safeJson<EwsResultFull>(res);
}

export async function fetchEwsMeta(): Promise<EwsMeta | null> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 20));
    return MOCK_EWS_META;
  }
  const url = `${API_BASE}/api/ews/meta`;
  const res = await fetch(url, { next: { revalidate: 300 } });
  if (!res.ok) return null;
  return safeJson<EwsMeta>(res);
}

function filterMockLeaderboard(filters: EwsLeaderboardFilters): EwsCard[] {
  return MOCK_EWS_LEADERBOARD.filter((r) => {
    if (filters.market && filters.market !== "ALL" && r.market !== filters.market) return false;
    if (filters.phase && r.phase_state !== filters.phase) return false;
    if (filters.sector && r.sector !== filters.sector) return false;
    if (typeof filters.min_score === "number" && r.criticality_score < filters.min_score) return false;
    if (typeof filters.min_confidence === "number" && r.confidence < filters.min_confidence) return false;
    return true;
  }).slice(0, filters.limit ?? 50);
}

export async function fetchUniversalityCompanies(
  classId: string,
): Promise<UniversalityCompaniesResponse> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 40));
    const matching = MOCK_COMPANIES.filter(
      (c) => c.universality_class === classId,
    );
    return {
      class_id: classId,
      display_name: classId,
      count: matching.length,
      companies: matching.map((c) => ({
        ticker: c.ticker,
        name: c.name,
        sector: c.sector,
        industry: c.industry,
        dynamics_family: c.dynamics_family,
        critical_point_state: c.critical_point_state,
        extraction_confidence: c.extraction_confidence,
        tldr: c.tldr,
      })),
    };
  }
  const url = `${API_BASE}/api/universality/companies/${encodeURIComponent(classId)}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok)
    throw new Error(
      `universality companies fetch failed: ${res.status} ${res.statusText}`,
    );
  const json = await safeJson<UniversalityCompaniesResponse>(res);
  if (!json)
    return { class_id: classId, display_name: classId, count: 0, companies: [] };
  return json;
}
