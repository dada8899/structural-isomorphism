// API client for Phase Detector backend (W3-B endpoints).
// Falls back to mock data when NEXT_PUBLIC_USE_MOCK=true.

import type { Company, ScreenerFilters, Stats } from "./types";
import { MOCK_COMPANIES, MOCK_STATS } from "./mock-data";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

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
      c.confidence < filters.min_confidence
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
