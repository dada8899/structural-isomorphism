/* tslint:disable */
/* eslint-disable */
/**
/* This file was automatically generated from pydantic models by running pydantic2ts.
/* Do not modify it by hand - just update the pydantic models and then re-run the script
*/

/**
 * `answer_done` event payload. `out_of_scope=true` means the
 * retrieval relevance gate failed — frontend should soften the UI.
 */
export interface AnswerDone {
  text: string;
  out_of_scope?: boolean;
  scope_reason?: string | null;
  citations?: string[];
}
/**
 * First SSE event from /api/ask/stream — echoes the rewritten query
 * and the planned downstream steps. Frontend renders this as the
 * 'thinking about: <query>' line.
 */
export interface AskMeta {
  rewritten: string;
  steps?: string[];
}
/**
 * Body for POST /api/ask/stream — Perplexity-like SSE endpoint.
 */
export interface AskRequest {
  query: string;
  lang?: "zh" | "en";
}
export interface AssessRequest {
  query: string;
  lang?: string;
}
/**
 * Mock-Stripe checkout body. `force_status` is a test-only override
 * honoured for localhost callers only.
 */
export interface CheckoutBody {
  tier: string;
  interval?: string;
  email: string;
  name?: string | null;
  card_last4?: string | null;
  force_status?: string | null;
}
/**
 * Response shape from POST /api/checkout/mock.
 */
export interface CheckoutResponse {
  status: "success" | "declined" | "error";
  order_id?: string | null;
  message?: string | null;
}
export interface CompaniesResponse {
  items?: Company[];
  total?: number;
}
/**
 * A single company row in the screener. Mirrors the inline
 * `Company` shape from `web/phase-detector/lib/types.ts` — listed here
 * so the generated TS file owns the canonical shape.
 */
export interface Company {
  ticker: string;
  name: string;
  sector: string;
  dynamics_family: string;
  critical_point_state: string;
  extraction_confidence: number;
  signals?: string[];
}
/**
 * Cookie-consent record persisted on the client + mirrored on the
 * server when the user opts in. W14-C surface model.
 */
export interface CookieConsent {
  necessary?: boolean;
  analytics?: boolean;
  marketing?: boolean;
  timestamp?: number | null;
}
/**
 * GET /api/daily — today's curated discoveries.
 */
export interface DailyResponse {
  date: string;
  discoveries?: {
    [k: string]: unknown;
  }[];
}
/**
 * GET /api/discoveries — A-grade + tier-2 structural discoveries.
 */
export interface DiscoveriesResponse {
  count?: number;
  discoveries?: {
    [k: string]: unknown;
  }[];
  tier2_count?: number;
  tier2?: {
    [k: string]: unknown;
  }[];
  stats?: {
    [k: string]: unknown;
  };
  [k: string]: unknown;
}
/**
 * POST /api/errors — accepted/rate_limited/storage_failure envelope.
 *
 * `accepted=true` ⇒ persisted to disk and `stored_at` is set.
 * `accepted=false` ⇒ `reason` is set (`rate_limited` / `storage_failure`).
 */
export interface ErrorAcceptedResponse {
  accepted: boolean;
  stored_at?: string | null;
  reason?: string | null;
  [k: string]: unknown;
}
/**
 * Client-side error envelope. All optional fields are size-capped
 * in the backend; mirrored here for the typed-frontend contract.
 */
export interface ErrorReportBody {
  message: string;
  stack?: string | null;
  digest?: string | null;
  url?: string | null;
  userAgent?: string | null;
  timestamp?: number | null;
  sessionId?: string | null;
  fatal?: boolean | null;
}
/**
 * GET /api/examples — handpicked example phenomenon pairs.
 *
 * Items are intentionally loose (raw KB rows are reshaped at render
 * time) so we keep `List[Dict[str, Any]]` instead of pinning a strict
 * KB-row shape.
 */
export interface ExamplesResponse {
  examples?: {
    [k: string]: unknown;
  }[];
}
/**
 * GET /api/flags — resolved feature flags + experiment variants.
 */
export interface FlagsResponse {
  flags?: {
    [k: string]: unknown;
  };
  experiments?: {
    [k: string]: unknown;
  };
  variants?: {
    [k: string]: string;
  };
  [k: string]: unknown;
}
/**
 * GET /api/health — liveness/deep-probe response.
 */
export interface HealthResponse {
  status?: string;
  kb_size?: number;
  llm_model?: string;
  checks?: {
    [k: string]: string;
  } | null;
}
/**
 * A single history row returned by GET /api/history.
 */
export interface HistoryRecord {
  id: number;
  query: string;
  kind: string;
  result_summary?: string | null;
  created_at: string;
}
/**
 * Body for POST /api/history — records one user query.
 */
export interface HistoryRecordRequest {
  query: string;
  kind: string;
  result_summary?: {
    [k: string]: unknown;
  } | null;
}
/**
 * GET /api/history response envelope.
 */
export interface HistoryResponse {
  items?: HistoryRecord[];
  total?: number;
}
/**
 * A single retrieved phenomenon card surfaced in `kb_cards` event.
 */
export interface KBCard {
  id: string;
  name: string;
  domain: string;
  score: number;
  snippet?: string | null;
}
export interface MappingRequest {
  a_id: string;
  b_id: string;
  lang?: string;
}
/**
 * GET /api/newsletter/count — current subscriber count (anon-safe).
 */
export interface NewsletterCountResponse {
  count?: number;
}
/**
 * Universality class / phase descriptor.
 */
export interface Phase {
  id: string;
  name: string;
  domain: string;
  description: string;
  company_count?: number;
}
export interface PhasesResponse {
  items?: Phase[];
  total?: number;
}
/**
 * POST /api/privacy/delete — irreversible right-to-be-forgotten.
 */
export interface PrivacyDeleteRequest {
  email: string;
  code: string;
  session_id?: string | null;
}
/**
 * Counts of records removed across each store.
 */
export interface PrivacyDeleteResponse {
  email: string;
  newsletter_removed?: number;
  checkouts_removed?: number;
  error_log_removed?: number;
}
/**
 * Query params for GET /api/privacy/export. Phase 1 mock code = '123456'.
 */
export interface PrivacyExportRequest {
  email: string;
  code: string;
  session_id?: string | null;
}
/**
 * Self-service DSAR (data subject access request) bundle.
 */
export interface PrivacyExportResponse {
  email: string;
  generated_at: string;
  newsletter?: {
    [k: string]: unknown;
  }[];
  checkouts?: {
    [k: string]: unknown;
  }[];
  error_log?: {
    [k: string]: unknown;
  }[];
}
/**
 * RFC 7807-style error envelope returned by every failing endpoint.
 * Frontend can rely on `type` + `code` being present.
 */
export interface ProblemDetailEnvelope {
  type: string;
  title: string;
  status: number;
  code: string;
  detail?: string | null;
  instance?: string | null;
}
export interface SearchRequest {
  query: string;
  top_k?: number;
  rewrite?: boolean;
  lang?: string;
}
export interface SearchResponse {
  query: string;
  count: number;
  results?: SearchResult[];
}
export interface SearchResult {
  id: string;
  name: string;
  domain: string;
  type_id: string;
  description: string;
  score: number;
}
export interface SubscribeBody {
  email: string;
  source?: string | null;
}
export interface SynthesizeRequest {
  query: string;
  rewritten_query?: string | null;
  results?: {
    [k: string]: unknown;
  }[];
  lang?: string;
}
/**
 * Final verdict assembled from /api/ask/stream — exported for
 * fixtures + Storybook stories so they stay in lockstep with API.
 */
export interface Verdict {
  summary: string;
  confidence: number;
  similar_phenomena?: KBCard[];
  followups?: string[];
}
/**
 * GET /api/version — build & version metadata.
 */
export interface VersionResponse {
  semver: string;
  git_sha: string;
  build_date: string;
  python_version: string;
  env: string;
}
/**
 * GET /api/whoami — debug helper reflecting the resolved auth tier.
 */
export interface WhoAmIResponse {
  tier: string;
  api_key_supplied: boolean;
}
