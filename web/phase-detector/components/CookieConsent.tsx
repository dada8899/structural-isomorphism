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
//   • Plausible script injected client-side ONLY after consent — uses
//     document.createElement so it bypasses Next's <Script> SSR.
//
// Storage key: `cookie_consent_v1`. Bumping to v2 on schema change forces
// re-prompt (graceful: missing v2 = first-visit).
import { useEffect, useState, useCallback } from "react";

const CONSENT_KEY = "cookie_consent_v1";
const CONSENT_VERSION = 1;
const PLAUSIBLE_SCRIPT_ID = "plausible-script";
const PLAUSIBLE_DOMAIN = "phase.bytedance.city";
const PLAUSIBLE_SRC = "https://plausible.bytedance.city/js/script.js";

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

function loadPlausible(): void {
  if (typeof document === "undefined") return;
  if (document.getElementById(PLAUSIBLE_SCRIPT_ID)) return;
  const s = document.createElement("script");
  s.id = PLAUSIBLE_SCRIPT_ID;
  s.defer = true;
  s.dataset.domain = PLAUSIBLE_DOMAIN;
  s.src = PLAUSIBLE_SRC;
  document.head.appendChild(s);
}

function unloadPlausible(): void {
  if (typeof document === "undefined") return;
  const s = document.getElementById(PLAUSIBLE_SCRIPT_ID);
  if (s) s.remove();
  // Note: already-loaded script can't be "unloaded" mid-session. We rely on
  // the user reloading the page to fully drop tracking. Set a flag so any
  // remaining queued plausible() calls become no-ops.
  if (typeof window !== "undefined") {
    (window as Window & { plausible?: unknown }).plausible = function noop() {};
  }
}

/** Public API: callable from footer "Manage cookies" link to reopen banner. */
export function openCookieConsent(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent("cookie-consent:open"));
}

export default function CookieConsent() {
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
      if (existing.analytics) loadPlausible();
      else unloadPlausible();
      setMode("hidden");
    } else {
      setMode("banner");
    }
  }, []);

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
      if (a) loadPlausible();
      else unloadPlausible();
      // marketing currently no-op (no marketing scripts on the site).
      setAnalytics(a);
      setMarketing(m);
      setMode("hidden");
    },
    []
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
      <div className="mx-auto max-w-5xl px-6 py-4">
        {mode === "banner" && (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-zinc-700 dark:text-zinc-200">
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
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={essentialOnly}
                data-testid="cookie-essential-only"
                className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                仅必要
              </button>
              <button
                type="button"
                onClick={() => setMode("customize")}
                data-testid="cookie-customize"
                className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                自定义
              </button>
              <button
                type="button"
                onClick={acceptAll}
                data-testid="cookie-accept-all"
                className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
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
              <li className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={analytics}
                  onChange={(e) => setAnalytics(e.target.checked)}
                  aria-label="Analytics cookies"
                  data-testid="cookie-tier-analytics"
                  className="mt-0.5"
                />
                <div>
                  <span className="font-medium text-zinc-900 dark:text-zinc-100">
                    分析（可选）
                  </span>
                  <p className="text-zinc-600 dark:text-zinc-400">
                    Plausible — 自托管、隐私友好、不使用 cookie、不追踪跨站。
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3 opacity-60">
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
                className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
              >
                返回
              </button>
              <button
                type="button"
                onClick={saveCustom}
                data-testid="cookie-save-custom"
                className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
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
