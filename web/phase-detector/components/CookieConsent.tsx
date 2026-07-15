"use client";

// W14-C (session #10, 2026-05-15): GDPR / e-Privacy cookie consent banner.
//
// Design choices (vs. heavyweight CMPs like OneTrust / Cookiebot):
//   • Self-hosted — no third-party SDK, no IAB TCF token, no consent-server
//     round-trip. Our site is non-tracking by default (Plausible cookieless);
//     consent is a courtesy + GDPR Art.7 belt-and-braces for analytics opt-in.
//   • 3 tiers, not 12 — essential (always on), analytics (Plausible only),
//     marketing (no-op placeholder, checkbox disabled). When/if we add a
//     marketing pixel later, flip the disabled flag without changing the
//     surrounding code.
//   • localStorage, not cookie — we store the user's *choice* about cookies
//     in localStorage on purpose: ironic but standards-compliant (localStorage
//     for non-tracking technical state doesn't require consent under ePD).
//   • DNT (Do Not Track) header → analytics auto-disabled, banner hidden.
//     We treat DNT as an explicit opt-out per Plausible's documented behavior.
//   • The version-pinned official Plausible module is imported ONLY after
//     consent. The legacy self-hosted script cannot enforce transformRequest.
//
// Storage key: `cookie_consent_v1`. Bumping to v2 on schema change forces
// re-prompt (graceful: missing v2 = first-visit).
import { useEffect, useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import type { PlausibleRequestPayload } from "@plausible-analytics/tracker";
import {
  analyticsRouteIsSafe,
  canonicalAnalyticsUrl,
  normalizeAnalyticsPath,
  sanitizeAnalyticsEvent,
} from "@/lib/analytics";

const CONSENT_KEY = "cookie_consent_v1";
const CONSENT_VERSION = 1;
const PLAUSIBLE_DOMAIN = "phase.bytedance.city";
const PLAUSIBLE_ENDPOINT = "https://plausible.bytedance.city/api/event";

type TrackerModule = typeof import("@plausible-analytics/tracker");
type PlausibleWindowBinding = NonNullable<Window["plausible"]> & { s?: string };

let lastPageviewUrl: string | null = null;
let trackerModule: TrackerModule | null = null;
let trackerInitPromise: Promise<TrackerModule> | null = null;
let analyticsTransportEnabled = false;
let transportGeneration = 0;
let analyticsFetchGuardInstalled = false;

const blockedPlausible: NonNullable<Window["plausible"]> = () => undefined;

export type ConsentState = {
  essential: true; // always on
  analytics: boolean;
  marketing: boolean;
  version: number;
  timestamp: number; // ms since epoch
};

type Mode = "hidden" | "banner" | "customize";

/** Returns true if the browser advertises Do Not Track. */
function isDNT(): boolean {
  if (typeof navigator === "undefined") return false;
  // Spec: "1" = opt-out. We also treat "yes" (older spec) as opt-out.
  // We do NOT treat null/unset as opt-out (per the W3C spec).
  const dnt =
    (navigator as Navigator & { doNotTrack?: string }).doNotTrack ||
    (window as Window & { doNotTrack?: string }).doNotTrack ||
    "";
  return dnt === "1" || dnt === "yes";
}

function readConsent(): ConsentState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CONSENT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ConsentState;
    if (parsed.version !== CONSENT_VERSION) return null; // schema bump → re-prompt
    return parsed;
  } catch {
    return null;
  }
}

function writeConsent(c: ConsentState): void {
  try {
    window.localStorage.setItem(CONSENT_KEY, JSON.stringify(c));
  } catch {
    // private mode / quota: silently degrade — banner just re-shows next visit.
  }
}

function privacyTransform(
  payload: PlausibleRequestPayload,
): PlausibleRequestPayload | null {
  const safeUrl = canonicalAnalyticsUrl();
  if (
    !analyticsTransportEnabled ||
    !safeUrl ||
    !payload ||
    typeof payload !== "object" ||
    Array.isArray(payload)
  ) {
    return null;
  }
  const raw = payload as PlausibleRequestPayload;
  const safe: PlausibleRequestPayload = {
    n: "pageview",
    u: safeUrl,
    d: PLAUSIBLE_DOMAIN,
  };
  if (raw.n === "pageview") {
    safe.n = "pageview";
  } else {
    const event = sanitizeAnalyticsEvent(raw.n, raw.p);
    if (!event) return null;
    safe.n = event.name;
    if (event.props) {
      safe.p = Object.fromEntries(
        Object.entries(event.props).map(([key, value]) => [key, String(value)]),
      );
    }
  }
  if (
    (typeof raw.v === "string" && raw.v.length <= 32) ||
    (typeof raw.v === "number" && Number.isFinite(raw.v))
  ) {
    safe.v = raw.v;
  }
  return safe;
}

function ignoredAnalyticsResponse(): Promise<Response> {
  return Promise.resolve(new Response(null, { status: 204 }));
}

type AnalyticsRequestTarget = {
  raw: string;
  url: URL;
};

function normalizedAnalyticsHostname(url: URL): string | null {
  const hostname = url.hostname.toLowerCase().replace(/\.+$/, "");
  return hostname || null;
}

function effectiveAnalyticsPort(url: URL): string {
  if (url.port) return url.port;
  if (url.protocol === "https:") return "443";
  if (url.protocol === "http:") return "80";
  return "";
}

function equivalentAnalyticsAuthority(candidate: URL, expected: URL): boolean {
  return (
    candidate.protocol === expected.protocol &&
    normalizedAnalyticsHostname(candidate) === normalizedAnalyticsHostname(expected) &&
    effectiveAnalyticsPort(candidate) === effectiveAnalyticsPort(expected)
  );
}

function analyticsRequestTarget(
  input: Parameters<typeof fetch>[0],
): AnalyticsRequestTarget | null {
  try {
    let raw: string;
    if (typeof input === "string") {
      raw = input;
    } else {
      // URL and Request objects can originate in another same-origin realm,
      // where `instanceof window.URL` is false. Read their standardized string
      // attributes structurally so an iframe cannot bypass the guard.
      const candidate = input as unknown as {
        href?: unknown;
        url?: unknown;
      };
      if (typeof candidate.url === "string") raw = candidate.url;
      else if (typeof candidate.href === "string") raw = candidate.href;
      else raw = String(input);
    }
    return { raw, url: new URL(raw, window.location.href) };
  } catch {
    return null;
  }
}

function installAnalyticsFetchGuard(): void {
  if (analyticsFetchGuardInstalled || typeof window === "undefined") return;

  const baseFetch = window.fetch.bind(window);
  const guardedFetch: typeof window.fetch = (input, init) => {
    const requestTarget = analyticsRequestTarget(input);
    const protectedEndpoint = new URL(PLAUSIBLE_ENDPOINT);
    if (!requestTarget) return baseFetch(input, init);
    const requestUrl = requestTarget.url;
    const requestHostname = normalizedAnalyticsHostname(requestUrl);
    const protectedHostname = normalizedAnalyticsHostname(protectedEndpoint);
    if (!protectedHostname) {
      return ignoredAnalyticsResponse();
    }
    if (!requestHostname) return baseFetch(input, init);
    if (requestHostname !== protectedHostname) {
      return baseFetch(input, init);
    }
    const equivalentAuthority = equivalentAnalyticsAuthority(
      requestUrl,
      protectedEndpoint,
    );
    const requestPath = normalizeAnalyticsPath(requestUrl.pathname);
    const protectedPath = normalizeAnalyticsPath(protectedEndpoint.pathname);
    // Malformed paths on the analytics origin are never reclassified as
    // unrelated traffic. A proxy may normalize them differently from the
    // browser, so the only safe behavior is to stop them here.
    if (!requestPath || !protectedPath) return ignoredAnalyticsResponse();
    if (requestPath !== protectedPath) return baseFetch(input, init);
    // Any query, fragment or other spelling of the protected endpoint is an
    // attempted boundary bypass. Never reclassify it as unrelated traffic.
    if (
      !equivalentAuthority ||
      requestTarget.raw !== protectedEndpoint.href ||
      requestUrl.href !== protectedEndpoint.href
    ) {
      return ignoredAnalyticsResponse();
    }
    if (!analyticsTransportEnabled || !analyticsRouteIsSafe()) {
      return ignoredAnalyticsResponse();
    }

    // Plausible 0.4.5 sends engagement events through an internal path that
    // bypasses transformRequest. The endpoint guard is the final fail-closed
    // boundary: only POSTed JSON that survives the same allowlist can leave.
    const method = init?.method?.toUpperCase() ?? "GET";
    if (method !== "POST" || typeof init?.body !== "string") {
      return ignoredAnalyticsResponse();
    }
    try {
      const payload = JSON.parse(init.body) as PlausibleRequestPayload;
      const safePayload = privacyTransform(payload);
      if (!safePayload) return ignoredAnalyticsResponse();
      return baseFetch(input, {
        ...init,
        body: JSON.stringify(safePayload),
      });
    } catch {
      return ignoredAnalyticsResponse();
    }
  };

  window.fetch = guardedFetch;
  analyticsFetchGuardInstalled = true;
}

function initializedTracker(): Promise<TrackerModule> {
  if (trackerModule) return Promise.resolve(trackerModule);
  if (!trackerInitPromise) {
    trackerInitPromise = import("@plausible-analytics/tracker")
      .then((tracker) => {
        installAnalyticsFetchGuard();
        const current = window.plausible as PlausibleWindowBinding | undefined;
        if (current?.s !== "npm") {
          tracker.init({
            domain: PLAUSIBLE_DOMAIN,
            endpoint: PLAUSIBLE_ENDPOINT,
            autoCapturePageviews: false,
            captureOnLocalhost: process.env.NODE_ENV !== "production",
            logging: false,
            transformRequest: privacyTransform,
            bindToWindow: true,
          });
        }
        trackerModule = tracker;
        return tracker;
      })
      .catch((error) => {
        trackerInitPromise = null;
        throw error;
      });
  }
  return trackerInitPromise;
}

function loadPlausible(pathname?: string): void {
  if (typeof window === "undefined") return;
  const safeUrl = canonicalAnalyticsUrl(pathname);
  if (!safeUrl) {
    unloadPlausible();
    return;
  }
  analyticsTransportEnabled = true;
  const generation = ++transportGeneration;
  void initializedTracker()
    .then((tracker) => {
      if (generation !== transportGeneration) return;
      if (!analyticsTransportEnabled || canonicalAnalyticsUrl(pathname) !== safeUrl) {
        unloadPlausible();
        return;
      }
      window.plausible = tracker.track as NonNullable<Window["plausible"]>;
      if (lastPageviewUrl !== safeUrl) {
        tracker.track("pageview", { url: safeUrl });
        lastPageviewUrl = safeUrl;
      }
    })
    .catch(() => {
      if (generation === transportGeneration) unloadPlausible();
    });
}

function unloadPlausible(): void {
  analyticsTransportEnabled = false;
  transportGeneration += 1;
  if (typeof window !== "undefined") {
    // The official module has no teardown API. Its transform closes over the
    // disabled flag above, while app calls are replaced with a local no-op.
    window.plausible = blockedPlausible;
  }
  lastPageviewUrl = null;
}

/** Public API: callable from footer "Manage cookies" link to reopen banner. */
export function openCookieConsent(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("cookie-consent:open"));
}

export default function CookieConsent() {
  const pathname = usePathname();
  const [mode, setMode] = useState<Mode>("hidden");
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  // Initial mount: decide whether to show banner.
  useEffect(() => {
    const existing = readConsent();
    const dnt = isDNT();

    if (dnt) {
      // DNT users get no banner; analytics auto-off; record an implicit
      // consent record so we don't ask again. They can still revisit via
      // "Manage cookies".
      if (!existing) {
        writeConsent({
          essential: true,
          analytics: false,
          marketing: false,
          version: CONSENT_VERSION,
          timestamp: Date.now(),
        });
      }
      unloadPlausible();
      setMode("hidden");
      return;
    }

    if (existing) {
      setAnalytics(existing.analytics);
      setMarketing(existing.marketing);
      if (existing.analytics && analyticsRouteIsSafe(pathname)) loadPlausible(pathname);
      else unloadPlausible();
      setMode("hidden");
    } else {
      setMode("banner");
    }
  }, [pathname]);

  useEffect(() => {
    if (analytics && analyticsRouteIsSafe(pathname)) loadPlausible(pathname);
    else unloadPlausible();
  }, [analytics, pathname]);

  // Listen for "reopen" events from footer link.
  useEffect(() => {
    const onOpen = () => {
      const existing = readConsent();
      if (existing) {
        setAnalytics(existing.analytics);
        setMarketing(existing.marketing);
      }
      setMode("customize");
    };
    window.addEventListener("cookie-consent:open", onOpen as EventListener);
    return () =>
      window.removeEventListener("cookie-consent:open", onOpen as EventListener);
  }, []);

  const persistAndApply = useCallback(
    (a: boolean, m: boolean) => {
      writeConsent({
        essential: true,
        analytics: a,
        marketing: m,
        version: CONSENT_VERSION,
        timestamp: Date.now(),
      });
      if (a && analyticsRouteIsSafe(pathname)) loadPlausible(pathname);
      else unloadPlausible();
      // marketing currently no-op (no marketing scripts on the site).
      setAnalytics(a);
      setMarketing(m);
      setMode("hidden");
    },
    [pathname]
  );

  const acceptAll = () => persistAndApply(true, true);
  const essentialOnly = () => persistAndApply(false, false);
  const saveCustom = () => persistAndApply(analytics, marketing);

  if (mode === "hidden") return null;

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-label="Cookie consent"
      data-testid="cookie-consent"
      className="fixed bottom-0 left-0 right-0 z-[200] border-t border-zinc-200 bg-white shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
    >
      <div className="mx-auto w-full min-w-0 max-w-5xl px-4 py-4 sm:px-6">
        {mode === "banner" && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 break-words text-sm text-zinc-700 dark:text-zinc-200">
              <p className="font-medium">关于 cookie 的说明</p>
              <p className="mt-1 text-zinc-600 dark:text-zinc-400">
                我们使用必要的本地存储让站点正常工作。可选择开启
                Plausible（隐私友好、无 cookie）匿名分析帮助我们改进。详见{" "}
                <a href="/privacy" className="underline hover:text-zinc-900 dark:hover:text-white">
                  隐私政策
                </a>
                。
              </p>
            </div>
            <div className="min-w-0 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={essentialOnly}
                data-testid="cookie-essential-only"
                className="min-h-11 rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                仅必要
              </button>
              <button
                type="button"
                onClick={() => setMode("customize")}
                data-testid="cookie-customize"
                className="min-h-11 rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                自定义
              </button>
              <button
                type="button"
                onClick={acceptAll}
                data-testid="cookie-accept-all"
                className="min-h-11 rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                全部接受
              </button>
            </div>
          </div>
        )}

        {mode === "customize" && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
              选择你的 cookie 偏好
            </p>
            <ul className="space-y-2 text-sm">
              <li className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked
                  disabled
                  aria-label="Essential cookies"
                  data-testid="cookie-tier-essential"
                  className="mt-0.5"
                />
                <div>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    必要（始终开启）
                  </span>
                  <p className="text-zinc-600 dark:text-zinc-400">
                    保证页面正常工作的本地存储（主题、会话）。
                  </p>
                </div>
              </li>
              <li>
                <label className="flex min-h-11 cursor-pointer items-start gap-3">
                  <input
                    type="checkbox"
                    checked={analytics}
                    onChange={(e) => setAnalytics(e.target.checked)}
                    data-testid="cookie-tier-analytics"
                    className="mt-0.5"
                  />
                  <span className="block">
                    <span className="block font-medium text-zinc-900 dark:text-zinc-100">
                      分析（可选）
                    </span>
                    <span className="block text-zinc-600 dark:text-zinc-400">
                      Plausible — 自托管、隐私友好、不使用 cookie、不追踪跨站。
                    </span>
                  </span>
                </label>
              </li>
              <li className="flex cursor-not-allowed items-start gap-3">
                <input
                  type="checkbox"
                  checked={marketing}
                  disabled
                  onChange={(e) => setMarketing(e.target.checked)}
                  aria-label="Marketing cookies"
                  data-testid="cookie-tier-marketing"
                  className="mt-0.5"
                />
                <div>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    营销（不使用）
                  </span>
                  <p className="text-zinc-600 dark:text-zinc-400">
                    本站当前未使用任何营销 cookie。
                  </p>
                </div>
              </li>
            </ul>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setMode("banner")}
                className="min-h-11 rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                返回
              </button>
              <button
                type="button"
                onClick={saveCustom}
                data-testid="cookie-save-custom"
                className="min-h-11 rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                保存偏好
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
