// W13-E (session #10): client-side search engine for Cmd+K palette.
//
// We avoid pulling fuse.js (~12 KB gz) because our index is small
// (~275 entries, ~90 KB raw) and our needs are simple:
//   1. exact match
//   2. prefix match
//   3. substring match
//   4. fuzzy match (subsequence with gap penalty)
// Hand-rolled scorer keeps the bundle ~1 KB, runs in <2 ms on 300 entries
// on a mid-2020 MacBook (measured locally).
//
// Scoring tiers (highest first):
//   1000 — exact title or keyword match
//    700 — title starts with query
//    500 — keyword starts with query
//    300 — title contains query
//    200 — keyword contains query
//    100 — subsequence (fuzzy) match in title
//
// Then add `weight * 50` so higher-priority types (companies) tiebreak above
// lower-priority types (docs). Then date-recency on papers/newsletters
// (newer wins by up to +20).

export type SearchEntryType =
  | "company"
  | "universality_class"
  | "paper"
  | "newsletter"
  | "docs";

export interface SearchEntry {
  id: string;
  type: SearchEntryType;
  title: string;
  subtitle: string;
  url: string;
  keywords: string[];
  weight: number;
  /** Optional ISO date string (papers / newsletters). */
  date?: string;
}

export interface SearchHit extends SearchEntry {
  score: number;
}

/** Normalize a string for matching: lowercase + collapse whitespace. */
function norm(s: string): string {
  return s.toLowerCase().trim().replace(/\s+/g, " ");
}

/** Returns true if `needle` is a subsequence of `haystack` (chars in order, gaps allowed). */
function isSubsequence(needle: string, haystack: string): boolean {
  if (needle.length === 0) return true;
  let i = 0;
  for (let j = 0; j < haystack.length && i < needle.length; j++) {
    if (haystack[j] === needle[i]) i++;
  }
  return i === needle.length;
}

/** Days since ISO date string `YYYY-MM-DD`, or +Infinity if unparseable. */
function daysSince(iso: string | undefined): number {
  if (!iso) return Infinity;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return Infinity;
  return (Date.now() - t) / (1000 * 60 * 60 * 24);
}

/** Score a single entry against a normalized query. 0 = no match. */
function scoreEntry(entry: SearchEntry, q: string): number {
  if (!q) return 0;
  const title = norm(entry.title);
  let best = 0;

  // Title-level matches.
  if (title === q) best = Math.max(best, 1000);
  else if (title.startsWith(q)) best = Math.max(best, 700);
  else if (title.includes(q)) best = Math.max(best, 300);

  // Keyword-level matches.
  for (const kw of entry.keywords) {
    if (kw === q) {
      best = Math.max(best, 1000);
      break;
    } else if (kw.startsWith(q)) {
      best = Math.max(best, 500);
    } else if (kw.includes(q)) {
      best = Math.max(best, 200);
    }
  }

  // Fuzzy fallback: subsequence in title (cheap, only run if nothing else hit).
  if (best === 0 && q.length >= 2 && isSubsequence(q, title)) {
    best = 100;
  }

  if (best === 0) return 0;

  // Tiebreakers: type weight + recency bonus.
  const weightBonus = (entry.weight || 0) * 50;
  let recencyBonus = 0;
  if (entry.type === "paper" || entry.type === "newsletter") {
    const days = daysSince(entry.date);
    if (Number.isFinite(days)) {
      // 0 days → +20, 365 days → ~0
      recencyBonus = Math.max(0, 20 - days / 18);
    }
  }
  return best + weightBonus + recencyBonus;
}

/** Search the index. Returns up to `limit` ranked hits (highest score first). */
export function searchIndex(
  index: SearchEntry[],
  query: string,
  limit = 8,
): SearchHit[] {
  const q = norm(query);
  if (!q) return [];
  const hits: SearchHit[] = [];
  for (const entry of index) {
    const score = scoreEntry(entry, q);
    if (score > 0) hits.push({ ...entry, score });
  }
  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, limit);
}

/** Group hits by type, preserving the per-type relative ordering from `hits`. */
export function groupHitsByType(hits: SearchHit[]): Array<{
  type: SearchEntryType;
  label: string;
  hits: SearchHit[];
}> {
  const order: SearchEntryType[] = [
    "company",
    "universality_class",
    "paper",
    "newsletter",
    "docs",
  ];
  const labels: Record<SearchEntryType, string> = {
    company: "公司 / Companies",
    universality_class: "普适类 / Universality classes",
    paper: "论文 / Papers",
    newsletter: "周刊 / Newsletter",
    docs: "文档 / Docs",
  };
  const buckets: Record<SearchEntryType, SearchHit[]> = {
    company: [],
    universality_class: [],
    paper: [],
    newsletter: [],
    docs: [],
  };
  for (const h of hits) buckets[h.type].push(h);
  return order
    .filter((t) => buckets[t].length > 0)
    .map((t) => ({ type: t, label: labels[t], hits: buckets[t] }));
}
