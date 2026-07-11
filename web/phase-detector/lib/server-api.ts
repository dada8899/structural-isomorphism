import "server-only";

import { companyFromEws } from "./company-data";
import { MOCK_COMPANIES, MOCK_EWS_DETAIL } from "./mock-data";
import type { Company, EwsResultFull } from "./types";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
const INTERNAL_BASE = process.env.PHASE_API_INTERNAL_BASE ?? "http://127.0.0.1:8200";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${INTERNAL_BASE}${path}`, {
    cache: "no-store",
    signal: AbortSignal.timeout(3000),
  });
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}`);
  return (await response.json()) as T;
}

export async function loadServerEws(ticker: string): Promise<EwsResultFull | null> {
  const normalized = ticker.toUpperCase();
  if (USE_MOCK) return MOCK_EWS_DETAIL[normalized] ?? null;
  try {
    return await fetchJson<EwsResultFull>(`/api/ews/${encodeURIComponent(normalized)}`);
  } catch (error) {
    if (error instanceof Error && error.message.includes("HTTP 404")) return null;
    throw error;
  }
}

export async function loadServerCompany(ticker: string): Promise<Company> {
  const normalized = ticker.toUpperCase();
  if (USE_MOCK) {
    const company = MOCK_COMPANIES.find((item) => item.ticker.toUpperCase() === normalized);
    if (company) return company;
    const ews = MOCK_EWS_DETAIL[normalized];
    if (ews) return companyFromEws(ews);
    throw new Error(`company ${normalized} not found (mock)`);
  }
  return fetchJson<Company>(`/company/${encodeURIComponent(normalized)}`);
}
