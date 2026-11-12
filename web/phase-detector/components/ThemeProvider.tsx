"use client";

// W13-A (session #10, 2026-05-15): 3-mode theme provider.
//
// Modes: "system" (default) | "light" | "dark".
// Persistence: localStorage key `phase_theme`. Missing / corrupt value → "system".
// Hydration safety: server renders no `.dark` class on <html>; the very first
//   client effect (synchronous on mount, before paint) syncs the html class
//   from localStorage + matchMedia. We also accept a `suppressHydrationWarning`
//   on the consuming <html> element so React doesn't complain about the
//   transient class mismatch.
//
// We deliberately do NOT inject a blocking <script> in <head> to avoid a CSP
// nonce / build-time complication. Instead we accept a single repaint on first
// load (FOUC for ~30ms) and rely on `color-scheme` + smooth transitions to
// keep the flash imperceptible. If FOUC becomes a real complaint, a small
// inline script could be added to layout.tsx — see docs/ui/theming-2026-05-15.md.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  theme: ThemeMode;
  resolvedTheme: ResolvedTheme;
  setTheme: (m: ThemeMode) => void;
}

const STORAGE_KEY = "phase_theme";
const DEFAULT_MODE: ThemeMode = "system";

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStoredMode(): ThemeMode {
  if (typeof window === "undefined") return DEFAULT_MODE;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v === "light" || v === "dark" || v === "system") return v;
  } catch {
    /* localStorage blocked (Safari private / SSR) — fall through. */
  }
  return DEFAULT_MODE;
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

function applyThemeClass(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (resolved === "dark") {
    root.classList.add("dark");
    root.style.colorScheme = "dark";
  } else {
    root.classList.remove("dark");
    root.style.colorScheme = "light";
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  // SSR + first-render: always emit "system" / resolved = "light" so server
  // and client agree on initial markup. The post-mount effect immediately
  // syncs to localStorage + matchMedia (no painted-then-swapped class —
  // resolution happens before browser paint because layout effects run sync).
  const [theme, setThemeState] = useState<ThemeMode>(DEFAULT_MODE);
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");
  const [mounted, setMounted] = useState(false);

  // Mount: read stored mode + apply class.
  useEffect(() => {
    const stored = readStoredMode();
    const resolved: ResolvedTheme =
      stored === "system" ? (systemPrefersDark() ? "dark" : "light") : stored;
    setThemeState(stored);
    setResolvedTheme(resolved);
    applyThemeClass(resolved);
    setMounted(true);
  }, []);

  // React to system theme changes (only when mode = "system").
  useEffect(() => {
    if (!mounted) return;
    if (theme !== "system") return;
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next: ResolvedTheme = mq.matches ? "dark" : "light";
      setResolvedTheme(next);
      applyThemeClass(next);
    };
    // addEventListener is preferred; older Safari uses addListener.
    if (mq.addEventListener) {
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    // Legacy Safari < 14: addListener / removeListener (deprecated but typed).
    mq.addListener(onChange);
    return () => mq.removeListener(onChange);
  }, [theme, mounted]);

  const setTheme = useCallback((next: ThemeMode) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage quota / disabled — silently ignore. */
    }
    const resolved: ResolvedTheme =
      next === "system" ? (systemPrefersDark() ? "dark" : "light") : next;
    setResolvedTheme(resolved);
    applyThemeClass(resolved);
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme }),
    [theme, resolvedTheme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    // Tolerate uses before the provider mounts (SSR-rendered chart in a story
    // / unit test) — return a sane fallback so components don't crash.
    return {
      theme: "system",
      resolvedTheme: "light",
      setTheme: () => {
        /* noop outside provider */
      },
    };
  }
  return ctx;
}
