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
const MERGED_FLAG_KEY = "phase_favorites_merged_v1";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

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
  return Object.keys(getApiKeyHeader()).length > 0;
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

// ---------------- server fetchers ----------------

/** GET /api/favorites — returns server's source of truth. Falls back to
 * the anon bucket when offline / not signed in. */
export async function fetchFavorites(): Promise<string[]> {
  if (!isSignedIn()) {
    return readAnon();
  }
  try {
    const res = await fetch(`${API_BASE}/api/favorites`, {
      cache: "no-store",
      headers: getApiKeyHeader(),
    });
    if (!res.ok) return readAnon();
    const json = (await res.json()) as { tickers?: string[] };
    if (Array.isArray(json?.tickers)) {
      return json.tickers
        .filter((t): t is string => typeof t === "string")
        .map((t) => t.toUpperCase());
    }
    return [];
  } catch {
    return readAnon();
  }
}

/** Add a ticker. Returns the resolved boolean state (true=favorited). */
export async function addFavorite(ticker: string): Promise<boolean> {
  const t = ticker.trim().toUpperCase();
  if (!t) return false;
  if (!isSignedIn()) {
    const existing = readAnon();
    if (!existing.includes(t)) {
      writeAnon([...existing, t]);
    }
    return true;
  }
  try {
    const res = await fetch(
      `${API_BASE}/api/favorites/${encodeURIComponent(t)}`,
      {
        method: "POST",
        headers: getApiKeyHeader(),
      },
    );
    if (res.status === 201 || res.status === 200) {
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
  if (!isSignedIn()) {
    const existing = readAnon();
    writeAnon(existing.filter((x) => x !== t));
    return false;
  }
  try {
    const res = await fetch(
      `${API_BASE}/api/favorites/${encodeURIComponent(t)}`,
      {
        method: "DELETE",
        headers: getApiKeyHeader(),
      },
    );
    if (res.status === 204 || res.status === 200) {
      return false;
    }
    throw new Error(`favorite remove failed: ${res.status}`);
  } catch (err) {
    throw err;
  }
}

/** One-time post-login merge. Idempotent via localStorage flag. */
export async function mergeAnonIntoUser(): Promise<{
  merged: number;
  dropped: number;
} | null> {
  if (!isSignedIn()) return null;
  if (typeof window === "undefined") return null;
  try {
    if (window.localStorage.getItem(MERGED_FLAG_KEY) === "1") return null;
  } catch {
    // ignore — proceed (worst case: re-merge, which is idempotent server-side)
  }
  const anon = readAnon();
  if (anon.length === 0) {
    try {
      window.localStorage.setItem(MERGED_FLAG_KEY, "1");
    } catch {
      // ignore
    }
    return { merged: 0, dropped: 0 };
  }
  try {
    const res = await fetch(`${API_BASE}/api/favorites/merge`, {
      method: "POST",
      headers: { ...getApiKeyHeader(), "Content-Type": "application/json" },
      body: JSON.stringify({ tickers: anon }),
    });
    if (!res.ok) return null;
    const json = (await res.json()) as {
      tickers?: string[];
      dropped?: string[];
    };
    const finalCount = json?.tickers?.length ?? 0;
    const dropped = json?.dropped?.length ?? 0;
    // Success — clear anon bucket + mark merged.
    clearAnonFavorites();
    try {
      window.localStorage.setItem(MERGED_FLAG_KEY, "1");
    } catch {
      // ignore
    }
    return { merged: finalCount - (finalCount - anon.length), dropped };
  } catch {
    return null;
  }
}
