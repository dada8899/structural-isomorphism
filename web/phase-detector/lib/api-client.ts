// Typed fetch wrappers for the structural-isomorphism backend.
//
// W15-A (session #10, 2026-05-15): demonstrates the pattern of
// consuming the auto-generated `./api-types.ts` shapes instead of
// hand-rolled `interface` declarations sprinkled across components.
//
// Why a thin client (rather than e.g. tanstack-query)?
//   1. Phase-detector currently uses raw fetch in `./api.ts` — a thin
//      typed shim is the smallest possible bridge to the generated
//      types without disrupting callers.
//   2. The verbs covered here (/api/companies, /api/phases,
//      /api/checkout/mock) are the three pulled out for the W15-A
//      demonstration — extending the pattern is mechanical.
//   3. SSE endpoints (e.g. /api/ask/stream) need a streaming reader,
//      not fetch().then(json) — keep them in their own dedicated
//      helpers and reuse the generated types there too.

import type {
  CheckoutBody,
  CheckoutResponse,
  CompaniesResponse,
  PhasesResponse,
} from "./api-types";

const API_BASE =
  (typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE) ||
  "http://localhost:8000";

/** Shared options applied to every typed call. */
type TypedFetchOpts = {
  signal?: AbortSignal;
  /** Override API base for tests; defaults to NEXT_PUBLIC_API_BASE. */
  baseUrl?: string;
};

/**
 * Internal: typed fetch wrapper.
 *
 * - Always sets `Accept: application/json`.
 * - On non-2xx, throws an Error whose `message` is the upstream JSON
 *   `detail`/`title` if available, else the HTTP status line.
 * - Returns `null` on empty bodies (matches `safeJson` semantics in
 *   the legacy `./api.ts`).
 */
async function typedJson<T>(
  url: string,
  init: RequestInit,
  opts?: TypedFetchOpts,
): Promise<T | null> {
  const base = opts?.baseUrl ?? API_BASE;
  const res = await fetch(`${base}${url}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    signal: opts?.signal,
  });

  const text = await res.text();
  if (!res.ok) {
    let detail: string | undefined;
    try {
      const body = text ? (JSON.parse(text) as Record<string, unknown>) : null;
      if (body && typeof body === "object") {
        detail = (body.detail as string) ?? (body.title as string);
      }
    } catch {
      /* fall through with raw text */
    }
    throw new Error(detail ?? `${res.status} ${res.statusText}`);
  }
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

/** GET /api/companies — typed via {@link CompaniesResponse}. */
export async function getCompanies(
  query: { sector?: string; limit?: number } = {},
  opts?: TypedFetchOpts,
): Promise<CompaniesResponse | null> {
  const params = new URLSearchParams();
  if (query.sector) params.set("sector", query.sector);
  if (typeof query.limit === "number") params.set("limit", String(query.limit));
  const qs = params.toString();
  return typedJson<CompaniesResponse>(
    `/api/companies${qs ? `?${qs}` : ""}`,
    { method: "GET" },
    opts,
  );
}

/** GET /api/phases — typed via {@link PhasesResponse}. */
export async function getPhases(
  opts?: TypedFetchOpts,
): Promise<PhasesResponse | null> {
  return typedJson<PhasesResponse>("/api/phases", { method: "GET" }, opts);
}

/** POST /api/checkout/mock — body typed via {@link CheckoutBody}. */
export async function postCheckoutMock(
  body: CheckoutBody,
  opts?: TypedFetchOpts,
): Promise<CheckoutResponse | null> {
  return typedJson<CheckoutResponse>(
    "/api/checkout/mock",
    { method: "POST", body: JSON.stringify(body) },
    opts,
  );
}

// Re-export the underlying types as a convenience so call sites can
// `import { CheckoutBody, postCheckoutMock } from "@/lib/api-client"`.
export type {
  CheckoutBody,
  CheckoutResponse,
  CompaniesResponse,
  PhasesResponse,
};
