// Feature flags + experiments client — session #10 W15-E.
//
// Fetches /api/flags once on mount, caches in a React context. SSR-safe:
// server-rendered HTML uses defaults (all flags false, all variants
// 'control'); hydrates with real values after mount.
//
// Anonymous identity: a stable UUID stored in localStorage under
// 'anon-id'. Sent as X-Anon-Id header. Authenticated users get bucketed
// by their real id (backend reads request.state.user_id).
//
// Why this design:
//   - Single network call per page load (not per useFlag).
//   - Context = global cache, no per-hook re-fetch.
//   - SSR returns defaults so hydration mismatch is bounded (only flag-gated
//     UI flips on mount; treat that as a 1-frame transition, not a bug).
//
// Usage:
//   <FlagsProvider>...</FlagsProvider>  (already wired in app/layout.tsx)
//   const enabled = useFlag('new_pricing_layout');
//   const variant = useExperiment('hero_cta_text_v2'); // 'control' | 'treatment'
//   const text    = useVariantValue('hero_cta_text_v2'); // 'Browse signals' | ...

"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { trackEvent } from "./analytics";

export interface FlagsState {
  flags: Record<string, boolean>;
  experiments: Record<string, string>;
  variants: Record<string, string>;
  loaded: boolean;
}

const DEFAULT_STATE: FlagsState = {
  flags: {},
  experiments: {},
  variants: {},
  loaded: false,
};

const FlagsContext = createContext<FlagsState>(DEFAULT_STATE);

const ANON_ID_KEY = "anon-id";

function getOrCreateAnonId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = window.localStorage.getItem(ANON_ID_KEY);
    if (!id) {
      // Cheap RFC4122-like; crypto.randomUUID() is fine in modern browsers
      // but fall back to Math.random() string for very old engines.
      id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `anon-${Math.random().toString(36).slice(2)}-${Date.now()}`;
      window.localStorage.setItem(ANON_ID_KEY, id);
    }
    return id;
  } catch {
    // localStorage blocked (private mode etc.) — return ephemeral id.
    return `anon-ephemeral-${Math.random().toString(36).slice(2)}`;
  }
}

interface FlagsProviderProps {
  children: ReactNode;
  /** Optional override for SSR or testing. */
  initial?: Partial<FlagsState>;
  /** Override the API base URL (defaults to relative /api). */
  apiBase?: string;
}

export function FlagsProvider({
  children,
  initial,
  apiBase = "",
}: FlagsProviderProps) {
  const [state, setState] = useState<FlagsState>(() => ({
    ...DEFAULT_STATE,
    ...initial,
  }));

  useEffect(() => {
    let cancelled = false;
    const anonId = getOrCreateAnonId();
    const headers: Record<string, string> = {};
    if (anonId) headers["X-Anon-Id"] = anonId;

    fetch(`${apiBase}/api/flags`, { headers, credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        setState({
          flags: data.flags ?? {},
          experiments: data.experiments ?? {},
          variants: data.variants ?? {},
          loaded: true,
        });
      })
      .catch(() => {
        // Network/JSON failure: stay on defaults. Don't crash the page.
        if (!cancelled) {
          setState((s) => ({ ...s, loaded: true }));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [apiBase]);

  const value = useMemo(() => state, [state]);
  return <FlagsContext.Provider value={value}>{children}</FlagsContext.Provider>;
}

/** Return whether a feature flag is enabled. Default false during SSR + before fetch. */
export function useFlag(name: string): boolean {
  const ctx = useContext(FlagsContext);
  return Boolean(ctx.flags[name]);
}

/** Return the experiment variant name (e.g. 'control' / 'treatment'). */
export function useExperiment(name: string): string {
  const ctx = useContext(FlagsContext);
  return ctx.experiments[name] ?? "control";
}

/**
 * Return the resolved variant content (e.g. the CTA text string).
 * Falls back to `fallback` during SSR/before fetch, or if experiment missing.
 *
 * Also fires a Plausible `experiment_exposed` event the first time this user
 * is exposed to the experiment in this session — so we can measure exposure
 * vs. downstream conversions.
 */
export function useVariantValue(name: string, fallback: string): string {
  const ctx = useContext(FlagsContext);
  const value = ctx.variants[name];
  const variant = ctx.experiments[name];

  useEffect(() => {
    if (!ctx.loaded || !variant) return;
    // De-dupe exposure events per session (Plausible already dedupes pageviews,
    // but custom events fire every time — so we gate on sessionStorage).
    try {
      const key = `exp-exposed:${name}`;
      if (typeof window !== "undefined" && !window.sessionStorage.getItem(key)) {
        window.sessionStorage.setItem(key, "1");
        trackEvent("experiment_exposed", { experiment: name, variant });
      }
    } catch {
      // sessionStorage blocked — fire once per mount as fallback.
      trackEvent("experiment_exposed", { experiment: name, variant });
    }
  }, [ctx.loaded, name, variant]);

  return value ?? fallback;
}

/** Test/storybook helper: render with explicit flags. */
export function FlagsTestProvider({
  children,
  flags,
  experiments,
  variants,
}: {
  children: ReactNode;
  flags?: Record<string, boolean>;
  experiments?: Record<string, string>;
  variants?: Record<string, string>;
}) {
  const value: FlagsState = {
    flags: flags ?? {},
    experiments: experiments ?? {},
    variants: variants ?? {},
    loaded: true,
  };
  return <FlagsContext.Provider value={value}>{children}</FlagsContext.Provider>;
}
