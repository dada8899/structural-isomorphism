// Plausible custom events helper (W8-D).
//
// The Plausible script is injected via app/layout.tsx (W4-B). It exposes a
// global `window.plausible(name, opts)` function. We wrap it so:
//   1. Pages never crash if the script is blocked / not loaded.
//   2. Event names are typed and centrally listed (search-friendly).
//   3. Props are auto-coerced to strings (Plausible only accepts string props).

declare global {
  interface Window {
    plausible?: (
      event: string,
      opts?: { props?: Record<string, string | number | boolean>; callback?: () => void }
    ) => void;
  }
}

export type EventProps = Record<string, string | number | boolean | undefined | null>;

function cleanProps(props?: EventProps): Record<string, string | number | boolean> | undefined {
  if (!props) return undefined;
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(props)) {
    if (v === undefined || v === null || v === "") continue;
    out[k] = v;
  }
  return Object.keys(out).length ? out : undefined;
}

export function trackEvent(name: string, props?: EventProps): void {
  if (typeof window === "undefined") return;
  const plausible = window.plausible;
  if (typeof plausible !== "function") return;
  try {
    const cleaned = cleanProps(props);
    plausible(name, cleaned ? { props: cleaned } : undefined);
  } catch {
    // Analytics must never break the page.
  }
}

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
} as const;

export type EventName = (typeof Events)[keyof typeof Events];
