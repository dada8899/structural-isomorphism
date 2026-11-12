// W15-C: client-side favorites store + server sync.
//
// Storage model
// -------------
// - Anonymous users: localStorage key `phase_favorites_anon`
//     { v: 1, tickers: string[] }
// - Signed-in users: server (`/api/favorites`) is the source of truth.
//   We do NOT cache server tickers in localStorage to avoid stale state
//   across tabs; pages call fetchFavorites() on mount.
// - Sign-in flow: a one-time `mergeAnonIntoUser()` call POSTs the anon
//   tickers to `/api/favorites/merge`, then clears the anon bucket.
//
// All reads/writes are SSR-safe. Failures never throw to the caller.

const ANON_KEY = "phase_favorites_anon";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const FAVORITES_API_BASE = API_BASE.endsWith("/api")
  ? API_BASE
  : `${API_BASE}/api`;
let sessionAuthenticated: boolean | null = null;
let lastMergeNotice: { merged: number; dropped: number } | null = null;

interface AnonEnvelope {
  v: 1;
  tickers: string[];
}

function readAnon(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(ANON_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Partial<AnonEnvelope>;
    if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.tickers)) return [];
    return parsed.tickers
      .filter((t): t is string => typeof t === "string")
      .map((t) => t.trim().toUpperCase())
      .filter(Boolean);
  } catch {
    return [];
  }
}

function writeAnon(tickers: string[]): void {
  if (typeof window === "undefined") return;
  try {
    const env: AnonEnvelope = {
      v: 1,
      tickers: [...new Set(tickers.map((t) => t.trim().toUpperCase()))].filter(
        Boolean,
      ),
    };
    window.localStorage.setItem(ANON_KEY, JSON.stringify(env));
  } catch {
    // quota / disabled storage — drop silently.
  }
}

function getApiKeyHeader(): Record<string, string> {
  // W15-B-equivalent: if a session-scoped API key exists, attach it.
  // Frontend doesn't yet have full login UX (W15-B follow-up); the
  // contract is: a key in window.localStorage["phase_api_key"] OR
  // NEXT_PUBLIC_API_KEY at build time.
  if (typeof window === "undefined") {
    const k = process.env.NEXT_PUBLIC_API_KEY;
    return k ? { "X-API-Key": k } : {};
  }
  try {
    const k = window.localStorage.getItem("phase_api_key");
    if (k) return { "X-API-Key": k };
  } catch {
    // ignore
  }
  const envKey = process.env.NEXT_PUBLIC_API_KEY;
  return envKey ? { "X-API-Key": envKey } : {};
}

export function isSignedIn(): boolean {
  return sessionAuthenticated === true || Object.keys(getApiKeyHeader()).length > 0;
}

export function markFavoritesSignedOut(): void {
  sessionAuthenticated = false;
}

export function getAnonFavorites(): string[] {
  return readAnon();
}

export function clearAnonFavorites(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ANON_KEY);
  } catch {
    // ignore
  }
}

/** Clear browser-local account state after the server confirms permanent
 * account deletion. This includes the legacy API-key credential so the
 * client cannot continue presenting the deleted account as authenticated. */
export function clearLocalAccountState(): void {
  clearAnonFavorites();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem("phase_api_key");
    } catch {
      // Storage may be unavailable; the authoritative session is HttpOnly
      // and has already been invalidated by the server.
    }
  }
  sessionAuthenticated = false;
  lastMergeNotice = null;
}

export function consumeFavoriteMergeNotice(): {
  merged: number;
  dropped: number;
} | null {
  const notice = lastMergeNotice;
  lastMergeNotice = null;
  return notice;
}

// ---------------- server fetchers ----------------

interface ServerFavorites {
  tickers: string[];
  authenticated: boolean;
}

async function fetchServerFavorites(): Promise<ServerFavorites | null> {
  try {
    const res = await fetch(`${FAVORITES_API_BASE}/favorites`, {
      cache: "no-store",
      headers: getApiKeyHeader(),
      credentials: "include",
    });
    if (!res.ok) {
      if (res.status === 401) sessionAuthenticated = false;
      return null;
    }
    const json = (await res.json()) as {
      tickers?: string[];
      authenticated?: boolean;
    };
    const authenticated = json?.authenticated === true;
    sessionAuthenticated = authenticated;
    return {
      authenticated,
      tickers: Array.isArray(json?.tickers)
        ? json.tickers
        .filter((t): t is string => typeof t === "string")
        .map((t) => t.toUpperCase())
        : [],
    };
  } catch {
    return null;
  }
}

/** GET /api/favorites — authenticated server state is authoritative.
 * Anonymous and unavailable states retain the local bucket. */
export async function fetchFavorites(): Promise<string[]> {
  const server = await fetchServerFavorites();
  if (!server?.authenticated) return readAnon();

  const anon = readAnon();
  if (anon.length === 0) return server.tickers;
  const merged = await mergeAnonIntoUser();
  if (merged) {
    const refreshed = await fetchServerFavorites();
    if (refreshed?.authenticated) return refreshed.tickers;
  }
  return server.tickers;
}

/** Add a ticker. Returns the resolved boolean state (true=favorited). */
export async function addFavorite(ticker: string): Promise<boolean> {
  const t = ticker.trim().toUpperCase();
  if (!t) return false;
  if (sessionAuthenticated === null && Object.keys(getApiKeyHeader()).length === 0) {
    await fetchServerFavorites();
  }
  if (!isSignedIn()) {
    const existing = readAnon();
    if (!existing.includes(t)) {
      writeAnon([...existing, t]);
    }
    return true;
  }
  try {
    const res = await fetch(
      `${FAVORITES_API_BASE}/favorites/${encodeURIComponent(t)}`,
      {
        method: "POST",
        headers: getApiKeyHeader(),
        credentials: "include",
      },
    );
    if (res.status === 201 || res.status === 200) {
      return true;
    }
    if (res.status === 401 && Object.keys(getApiKeyHeader()).length === 0) {
      markFavoritesSignedOut();
      const existing = readAnon();
      if (!existing.includes(t)) writeAnon([...existing, t]);
      return true;
    }
    if (res.status === 429) {
      // Tier cap exceeded — surface this so caller can show paywall.
      throw new Error("FAVORITES_CAP_EXCEEDED");
    }
    throw new Error(`favorite add failed: ${res.status}`);
  } catch (err) {
    if (err instanceof Error && err.message === "FAVORITES_CAP_EXCEEDED") {
      throw err;
    }
    // Network error — rollback handled by caller via optimistic UI.
    throw err;
  }
}

/** Remove a ticker. */
export async function removeFavorite(ticker: string): Promise<boolean> {
  const t = ticker.trim().toUpperCase();
  if (!t) return false;
  if (sessionAuthenticated === null && Object.keys(getApiKeyHeader()).length === 0) {
    await fetchServerFavorites();
  }
  if (!isSignedIn()) {
    const existing = readAnon();
    writeAnon(existing.filter((x) => x !== t));
    return false;
  }
  try {
    const res = await fetch(
      `${FAVORITES_API_BASE}/favorites/${encodeURIComponent(t)}`,
      {
        method: "DELETE",
        headers: getApiKeyHeader(),
        credentials: "include",
      },
    );
    if (res.status === 204 || res.status === 200) {
      return false;
    }
    if (res.status === 401 && Object.keys(getApiKeyHeader()).length === 0) {
      markFavoritesSignedOut();
      writeAnon(readAnon().filter((x) => x !== t));
      return false;
    }
    throw new Error(`favorite remove failed: ${res.status}`);
  } catch (err) {
    throw err;
  }
}

/** Post-login merge. Server union is idempotent; only confirmed accepted
 * entries are removed locally. Cap-dropped entries remain on this device. */
export async function mergeAnonIntoUser(): Promise<{
  merged: number;
  dropped: number;
} | null> {
  if (typeof window === "undefined") return null;
  if (sessionAuthenticated !== true && Object.keys(getApiKeyHeader()).length === 0) {
    const server = await fetchServerFavorites();
    if (!server?.authenticated) return null;
  }
  const anon = readAnon();
  if (anon.length === 0) {
    return { merged: 0, dropped: 0 };
  }
  try {
    const res = await fetch(`${FAVORITES_API_BASE}/favorites/merge`, {
      method: "POST",
      headers: { ...getApiKeyHeader(), "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ tickers: anon }),
    });
    if (!res.ok) return null;
    const json = (await res.json()) as {
      tickers?: string[];
      merged?: string[];
      dropped?: string[];
    };
    const dropped = json?.dropped?.length ?? 0;
    // Keep cap-dropped items locally so a partial merge is never presented as
    // full success and the user's local data is not destroyed.
    writeAnon(json?.dropped ?? []);
    lastMergeNotice = { merged: json?.merged?.length ?? 0, dropped };
    return lastMergeNotice;
  } catch {
    return null;
  }
}
