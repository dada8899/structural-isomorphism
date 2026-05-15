"use client";

// W15-B (session #10): client-side auth helpers.
//
// useSession() — React hook that:
//   - fetches /api/auth/me on mount
//   - exposes {user, loading, signOut, refresh}
//   - re-fetches on focus so navigation between tabs reflects login state
//
// NOTE: tokens live in HttpOnly cookies. Client-side JS NEVER touches the
// JWT directly; we just talk to /api/auth/* which round-trips the cookie
// for us. This is deliberate: an XSS escape can't steal the session.

import { useCallback, useEffect, useState } from "react";

export interface SessionUser {
  email: string;
  tier: string;
  created_at: string;
}

export interface SessionState {
  user: SessionUser | null;
  loading: boolean;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  "";

async function fetchMe(): Promise<SessionUser | null> {
  try {
    const r = await fetch(`${API_BASE}/api/auth/me`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (r.status !== 200) return null;
    const j = await r.json();
    return j?.user ?? null;
  } catch {
    return null;
  }
}

export function useSession(): SessionState {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    const u = await fetchMe();
    setUser(u);
    setLoading(false);
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Best-effort: cookie was probably already cleared.
    }
    setUser(null);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Re-fetch session when the tab regains focus — covers the case where
  // the user signs in on another tab.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onFocus = () => {
      refresh();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  return { user, loading, signOut, refresh };
}

// One-shot helpers (non-hook) for non-React surfaces.

export async function requestMagicLink(email: string): Promise<{
  ok: boolean;
  error?: string;
  dev_link?: string;
  dev_token?: string;
}> {
  try {
    const r = await fetch(`${API_BASE}/api/auth/request-link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email }),
    });
    return await r.json();
  } catch (e) {
    return { ok: false, error: "network error" };
  }
}

export async function verifyMagicLink(token: string): Promise<{
  ok: boolean;
  user?: SessionUser;
  error?: string;
}> {
  try {
    const r = await fetch(`${API_BASE}/api/auth/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ token }),
    });
    return await r.json();
  } catch (e) {
    return { ok: false, error: "network error" };
  }
}

export function isDevMode(): boolean {
  if (typeof process === "undefined") return false;
  return (
    process.env.NEXT_PUBLIC_AUTH_DEV_MODE === "true" ||
    process.env.NEXT_PUBLIC_AUTH_DEV_MODE === "1"
  );
}
