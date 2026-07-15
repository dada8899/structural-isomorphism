// Plausible custom events helper (W8-D).
//
// CookieConsent imports the pinned Plausible module only after opt-in. It exposes a global
// `window.plausible(name, opts)` function. We wrap it so:
//   1. Pages never crash if the module is blocked / not loaded.
//   2. Event names are typed and centrally listed (search-friendly).
//   3. Events, properties, routes and transmitted URLs are allowlisted.

declare global {
  interface Window {
    plausible?: (
      event: string,
      opts?: {
        props?: Record<string, string | number | boolean>;
        callback?: () => void;
        url?: string;
      }
    ) => void;
  }
}

export type EventProps = Record<string, string | number | boolean | undefined | null>;

// Centralized event name registry. Keep names snake_case, < 30 chars.
// When adding a new event, also add it to docs/analytics/plausible-events.md.
export const Events = {
  ScreenerFilterApplied: "screener_filter_applied",
  CompanyViewed: "company_viewed",
  WaitlistSignup: "waitlist_signup",
  WaitlistDuplicate: "waitlist_duplicate",
  WaitlistError: "waitlist_error",
  MethodologyOpened: "methodology_opened",
  AboutOpened: "about_opened",
  NewsletterArchiveView: "newsletter_archive_view",
  NewsletterArchiveIndex: "newsletter_archive_index",
  NewsletterLinkClick: "newsletter_link_click",
  PricingView: "pricing_view",
  CheckoutStarted: "checkout_started",
  CheckoutCompletedMock: "checkout_completed_mock",
  CheckoutDeclinedMock: "checkout_declined_mock",
  PaywallModalView: "paywall_modal_view",
  PaywallModalClick: "paywall_modal_click",
  // W15-E: A/B experiment exposure (fired once per session per experiment).
  ExperimentExposed: "experiment_exposed",
  // W15-C — favorites / bookmarks.
  FavoriteAdded: "favorite_added",
  FavoriteRemoved: "favorite_removed",
  FavoriteCapExceeded: "favorite_cap_exceeded",
  SearchOpened: "search_opened",
  SearchQuery: "search_query",
  SearchResultClick: "search_result_click",
  ThankYouShare: "thank_you_share",
  ResearchPreviewInterest: "research_preview_interest",
  TourStarted: "tour_started",
  TourNextStep: "tour_next_step",
  TourSkipped: "tour_skipped",
  TourCompleted: "tour_completed",
  TourRestartedFromNav: "tour_restarted_from_nav",
} as const;

export type EventName = (typeof Events)[keyof typeof Events];

const EVENT_PROP_ALLOWLIST: Readonly<Record<EventName, readonly string[]>> = {
  screener_filter_applied: ["family", "state", "sector", "min_confidence"],
  company_viewed: ["ticker", "family", "state", "source"],
  waitlist_signup: ["source", "placement"],
  waitlist_duplicate: ["source", "placement"],
  waitlist_error: ["source", "placement", "status"],
  methodology_opened: [],
  about_opened: [],
  newsletter_archive_view: ["issue"],
  newsletter_archive_index: [],
  newsletter_link_click: ["issue", "destination"],
  pricing_view: [],
  checkout_started: ["tier", "interval"],
  checkout_completed_mock: ["tier", "interval", "amount_usd"],
  checkout_declined_mock: ["tier", "interval", "reason"],
  paywall_modal_view: ["hit", "context"],
  paywall_modal_click: ["action", "context"],
  experiment_exposed: ["experiment", "variant"],
  favorite_added: ["ticker", "source"],
  favorite_removed: ["ticker", "source"],
  favorite_cap_exceeded: ["ticker", "source"],
  search_opened: ["source"],
  search_query: ["query_length", "result_count"],
  search_result_click: ["result_type", "result_position"],
  thank_you_share: ["channel"],
  research_preview_interest: ["tier", "interval", "from"],
  tour_started: ["source"],
  tour_next_step: ["step"],
  tour_skipped: ["step"],
  tour_completed: [],
  tour_restarted_from_nav: [],
};

const SENSITIVE_ROUTE = /^\/(?:auth(?:\/|$)|me(?:\/|$)|privacy(?:\/|$)|checkout(?:\/|$)|thank-you(?:\/|$)|onboarding(?:\/|$)|search(?:\/|$)|reports?(?:\/|$)|analyze(?:\/|$))/i;
const ENCODED_BYTE = /%[0-9A-Fa-f]{2}/;
const PATH_CONTROL = /[\u0000-\u001f\u007f]/;
const MAX_PATH_DECODE_ROUNDS = 3;

/**
 * Decode a browser pathname with the same fail-closed boundary used by the
 * analytics transport guard. Nginx matches locations after percent decoding,
 * dot-segment resolution and slash normalization, so an ambiguous spelling
 * must never be classified as a distinct public route.
 */
export function normalizeAnalyticsPath(pathname: unknown): string | null {
  if (typeof pathname !== "string" || !pathname.startsWith("/")) return null;

  let decoded = pathname;
  for (let round = 0; round < MAX_PATH_DECODE_ROUNDS; round += 1) {
    let next: string;
    try {
      next = decodeURIComponent(decoded);
    } catch {
      return null;
    }
    if (next === decoded) break;
    decoded = next;
  }

  if (
    ENCODED_BYTE.test(decoded) ||
    PATH_CONTROL.test(decoded) ||
    decoded.includes("\\") ||
    decoded.includes("?") ||
    decoded.includes("#") ||
    decoded.includes("//")
  ) {
    return null;
  }
  const segments = decoded.split("/");
  if (segments.some((segment) => segment === "." || segment === "..")) {
    return null;
  }
  return decoded;
}

export function analyticsRouteIsSafe(pathname?: string): boolean {
  const current = pathname ?? (typeof window !== "undefined" ? window.location.pathname : "");
  const normalized = normalizeAnalyticsPath(current);
  return normalized !== null && !SENSITIVE_ROUTE.test(normalized);
}

export function canonicalAnalyticsUrl(pathname?: string): string | null {
  if (typeof window === "undefined") return null;
  const normalized = normalizeAnalyticsPath(pathname ?? window.location.pathname);
  if (!normalized || SENSITIVE_ROUTE.test(normalized)) return null;
  try {
    const candidate = new URL(normalized, window.location.origin);
    if (candidate.origin !== window.location.origin || !candidate.pathname.startsWith("/")) {
      return null;
    }
    return `${window.location.origin}${candidate.pathname}`;
  } catch {
    return null;
  }
}

function isEventName(name: string): name is EventName {
  return Object.prototype.hasOwnProperty.call(EVENT_PROP_ALLOWLIST, name);
}

function cleanProps(
  name: EventName,
  props?: unknown,
): Record<string, string | number | boolean> | undefined {
  if (!props || typeof props !== "object" || Array.isArray(props)) return undefined;
  const allowed = new Set(EVENT_PROP_ALLOWLIST[name]);
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(props as Record<string, unknown>)) {
    if (!allowed.has(key) || value === undefined || value === null || value === "") continue;
    if (typeof value === "string") out[key] = value.slice(0, 80);
    else if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
    else if (typeof value === "boolean") out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

export type SanitizedAnalyticsEvent = {
  name: EventName;
  props?: Record<string, string | number | boolean>;
};

export function sanitizeAnalyticsEvent(
  name: unknown,
  props?: unknown,
): SanitizedAnalyticsEvent | null {
  if (typeof name !== "string" || !isEventName(name)) return null;
  const cleaned = cleanProps(name, props);
  return { name, ...(cleaned ? { props: cleaned } : {}) };
}

export function trackEvent(name: string, props?: EventProps): void {
  if (typeof window === "undefined") return;
  const event = sanitizeAnalyticsEvent(name, props);
  if (!event) return;
  const safeUrl = canonicalAnalyticsUrl();
  if (!safeUrl) return;
  const plausible = window.plausible;
  if (typeof plausible !== "function") return;
  try {
    plausible(event.name, {
      ...(event.props ? { props: event.props } : {}),
      url: safeUrl,
    });
  } catch {
    // Analytics must never break the page.
  }
}
