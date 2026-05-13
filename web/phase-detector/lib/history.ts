// PR-4: localStorage-backed search history for Phase Detector hero search.
//
// Storage shape under key "phase_history":
//   { v: 1, entries: HistoryEntry[], pinned: number[] }
//
// - entries kept in most-recent-first order, FIFO trim at MAX_ENTRIES (50).
// - pinned is a list of entry IDs (timestamps) capped at MAX_PINNED (10);
//   sidebar UI consumes this in PR-5, here we only manage storage.
// - All reads/writes are guarded — SSR, disabled storage, quota errors must
//   never break the page.

export interface HistoryEntry {
  // ms epoch — also serves as stable ID.
  ts: number;
  query: string;
  // Resolved route from parse-query (e.g. "/company/AAPL" or "/?state=near_critical").
  route: string;
  // Optional — how many results the submit produced (null if not measured).
  resultCount?: number | null;
}

const STORAGE_KEY = "phase_history";
const MAX_ENTRIES = 50;
const MAX_PINNED = 10;

interface Envelope {
  v: 1;
  entries: HistoryEntry[];
  pinned: number[]; // ts values
}

function emptyEnvelope(): Envelope {
  return { v: 1, entries: [], pinned: [] };
}

function readEnvelope(): Envelope {
  if (typeof window === "undefined") return emptyEnvelope();
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyEnvelope();
    const parsed = JSON.parse(raw) as Partial<Envelope>;
    if (!parsed || parsed.v !== 1 || !Array.isArray(parsed.entries)) {
      return emptyEnvelope();
    }
    return {
      v: 1,
      entries: parsed.entries.filter(
        (e): e is HistoryEntry =>
          !!e && typeof e.ts === "number" && typeof e.query === "string",
      ),
      pinned: Array.isArray(parsed.pinned)
        ? parsed.pinned.filter((p): p is number => typeof p === "number")
        : [],
    };
  } catch {
    return emptyEnvelope();
  }
}

function writeEnvelope(env: Envelope): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(env));
  } catch {
    // quota / disabled storage — silently drop.
  }
}

export function addToHistory(
  entry: Omit<HistoryEntry, "ts"> & { ts?: number },
): void {
  if (!entry.query?.trim()) return;
  const env = readEnvelope();
  const next: HistoryEntry = {
    ts: entry.ts ?? Date.now(),
    query: entry.query.trim(),
    route: entry.route,
    resultCount: entry.resultCount ?? null,
  };
  // Dedupe: drop any prior entry with the same query (case-insensitive).
  const dedup = env.entries.filter(
    (e) => e.query.toLowerCase() !== next.query.toLowerCase(),
  );
  dedup.unshift(next);
  // Trim FIFO, but always keep pinned entries.
  const trimmed: HistoryEntry[] = [];
  for (const e of dedup) {
    if (trimmed.length >= MAX_ENTRIES && !env.pinned.includes(e.ts)) continue;
    trimmed.push(e);
  }
  writeEnvelope({ ...env, entries: trimmed });
}

export function getHistory(): HistoryEntry[] {
  return readEnvelope().entries;
}

export function clearHistory(): void {
  const env = readEnvelope();
  // Preserve pinned entries.
  const kept = env.entries.filter((e) => env.pinned.includes(e.ts));
  writeEnvelope({ ...env, entries: kept });
}

export function pinEntry(ts: number): void {
  const env = readEnvelope();
  if (env.pinned.includes(ts)) return;
  if (env.pinned.length >= MAX_PINNED) return;
  writeEnvelope({ ...env, pinned: [...env.pinned, ts] });
}

export function unpinEntry(ts: number): void {
  const env = readEnvelope();
  if (!env.pinned.includes(ts)) return;
  writeEnvelope({ ...env, pinned: env.pinned.filter((p) => p !== ts) });
}

export function getPinnedIds(): number[] {
  return readEnvelope().pinned;
}
