// Error reporter — fire-and-forget POST to /api/errors with offline queue.
//
// W12-E: used by app/error.tsx and app/global-error.tsx auto-reporting.
// Privacy guarantees:
//   • No localStorage contents sent
//   • Query string stripped from URL
//   • sessionId is a random opaque uuid stored in localStorage (no PII)
//   • User-Agent is included (the browser sends it anyway)

const SESSION_KEY = "phase.sessionId";
const QUEUE_KEY = "phase.errorQueue";
const MAX_QUEUE = 20;
const ENDPOINT = "/api/errors";

export interface ErrorReport {
  message: string;
  stack?: string;
  digest?: string;
  url?: string;
  userAgent?: string;
  timestamp?: number; // unix seconds
  sessionId?: string;
}

function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  try {
    let id = window.localStorage.getItem(SESSION_KEY);
    if (!id) {
      // RFC4122-ish v4. Avoid crypto.randomUUID for older Safari.
      id = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      });
      window.localStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return "no-storage";
  }
}

function stripQuery(url: string | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url, "http://_");
    return u.origin === "http://_" ? u.pathname : `${u.origin}${u.pathname}`;
  } catch {
    return url.split("?")[0];
  }
}

function readQueue(): ErrorReport[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, MAX_QUEUE) : [];
  } catch {
    return [];
  }
}

function writeQueue(q: ErrorReport[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(QUEUE_KEY, JSON.stringify(q.slice(0, MAX_QUEUE)));
  } catch {
    /* storage full — drop silently */
  }
}

async function send(report: ErrorReport): Promise<boolean> {
  try {
    const r = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
      // Don't hold up navigation if the page is unloading.
      keepalive: true,
    });
    return r.ok;
  } catch {
    return false;
  }
}

/** Report an error. Queues to localStorage if offline; auto-flushes on next call. */
export async function reportError(input: {
  error: Error & { digest?: string };
  url?: string;
}): Promise<void> {
  const report: ErrorReport = {
    message: String(input.error?.message || "unknown error").slice(0, 500),
    stack: (input.error?.stack || "").slice(0, 4000),
    digest: input.error?.digest,
    url: stripQuery(input.url ?? (typeof window !== "undefined" ? window.location.href : undefined)),
    userAgent:
      typeof navigator !== "undefined" ? (navigator.userAgent || "").slice(0, 300) : undefined,
    timestamp: Math.floor(Date.now() / 1000),
    sessionId: getSessionId(),
  };

  // If offline, queue and bail.
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    const q = readQueue();
    q.push(report);
    writeQueue(q);
    return;
  }

  // Otherwise try to flush queue + send current.
  const q = readQueue();
  const remaining: ErrorReport[] = [];
  for (const queued of q) {
    const ok = await send(queued);
    if (!ok) remaining.push(queued);
  }
  await send(report);
  writeQueue(remaining);
}

/** Manually flush queued reports — invoke on "online" event. */
export async function flushErrorQueue(): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return;
  const q = readQueue();
  if (!q.length) return;
  const remaining: ErrorReport[] = [];
  for (const queued of q) {
    const ok = await send(queued);
    if (!ok) remaining.push(queued);
  }
  writeQueue(remaining);
}

/** Build a GitHub issue URL pre-filled with error context. */
export function buildIssueUrl(error: Error & { digest?: string }): string {
  const title = encodeURIComponent(`[user-report] ${(error?.message || "error").slice(0, 80)}`);
  const body = encodeURIComponent(
    [
      "<!-- Auto-generated from Phase Detector error boundary -->",
      "",
      `**Digest**: \`${error?.digest || "n/a"}\``,
      `**URL**: ${stripQuery(typeof window !== "undefined" ? window.location.href : "") || "n/a"}`,
      `**Time**: ${new Date().toISOString()}`,
      "",
      "**What happened**:",
      "<!-- describe what you were doing -->",
      "",
      "**Browser**: " + (typeof navigator !== "undefined" ? navigator.userAgent : ""),
    ].join("\n")
  );
  return `https://github.com/dada8899/structural-isomorphism/issues/new?title=${title}&body=${body}`;
}
