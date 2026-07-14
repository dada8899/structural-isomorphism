// Content-free error reporter — fire-and-forget POST to /api/errors.
//
// Error messages, stacks, URLs, browser fingerprints, account/session IDs,
// and arbitrary values never enter the network payload or offline queue.
// Older queue entries are reduced to the same allowlisted envelope before
// they can be retried.

const QUEUE_KEY = "phase.errorQueue";
const MAX_QUEUE = 20;
const ENDPOINT = "/api/errors";

const SAFE_ERROR_TYPES = new Set([
  "ChunkLoadError",
  "Error",
  "NetworkError",
  "RangeError",
  "ReferenceError",
  "SyntaxError",
  "TypeError",
  "URIError",
]);

export interface ErrorReport {
  // The compatibility API calls this field `message`, but the client sends
  // only an allowlisted error class. It never sends Error.message.
  message: string;
  timestamp: number;
  fatal: boolean;
}

function safeErrorType(value: unknown): string {
  let candidate = "";
  if (value instanceof Error) {
    candidate = value.name;
  } else if (typeof value === "string") {
    // Legacy offline entries stored the raw message. Keep only an exact,
    // allowlisted class prefix and discard the remainder.
    candidate = value.split(":", 1)[0].trim();
  } else if (value && typeof value === "object") {
    const name = (value as { name?: unknown }).name;
    if (typeof name === "string") candidate = name;
  }
  return SAFE_ERROR_TYPES.has(candidate) ? candidate : "ClientError";
}

function safeTimestamp(value: unknown): number {
  if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) {
    return value;
  }
  return Math.floor(Date.now() / 1000);
}

function sanitizeReport(value: unknown): ErrorReport | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  return {
    message: safeErrorType(record.message),
    timestamp: safeTimestamp(record.timestamp),
    fatal: record.fatal === true,
  };
}

function readQueue(): ErrorReport[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(QUEUE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .slice(0, MAX_QUEUE)
      .map(sanitizeReport)
      .filter((entry): entry is ErrorReport => entry !== null);
  } catch {
    return [];
  }
}

function writeQueue(queue: ErrorReport[]): void {
  if (typeof window === "undefined") return;
  try {
    const sanitized = queue
      .slice(0, MAX_QUEUE)
      .map(sanitizeReport)
      .filter((entry): entry is ErrorReport => entry !== null);
    if (sanitized.length) {
      window.localStorage.setItem(QUEUE_KEY, JSON.stringify(sanitized));
    } else {
      window.localStorage.removeItem(QUEUE_KEY);
    }
  } catch {
    /* storage unavailable — drop silently */
  }
}

async function send(value: ErrorReport): Promise<boolean> {
  const report = sanitizeReport(value);
  if (!report) return false;
  try {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
      keepalive: true,
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** Report an error without collecting its content or browser context. */
export async function reportError(input: {
  error: Error;
  fatal?: boolean;
}): Promise<void> {
  const report: ErrorReport = {
    message: safeErrorType(input.error),
    timestamp: Math.floor(Date.now() / 1000),
    fatal: input.fatal === true,
  };

  const queue = readQueue();
  // Rewrite immediately so any pre-hardening queue loses raw fields even
  // while offline.
  writeQueue(queue);
  if (typeof navigator !== "undefined" && navigator.onLine === false) {
    queue.push(report);
    writeQueue(queue);
    return;
  }

  const remaining: ErrorReport[] = [];
  for (const queued of queue) {
    const ok = await send(queued);
    if (!ok) remaining.push(queued);
  }
  if (!(await send(report))) remaining.push(report);
  writeQueue(remaining);
}

/** Sanitize and, when online, flush queued content-free reports. */
export async function flushErrorQueue(): Promise<void> {
  const queue = readQueue();
  // This is also the migration path for legacy queue entries.
  writeQueue(queue);
  if (typeof navigator !== "undefined" && navigator.onLine === false) return;
  if (!queue.length) return;

  const remaining: ErrorReport[] = [];
  for (const queued of queue) {
    const ok = await send(queued);
    if (!ok) remaining.push(queued);
  }
  writeQueue(remaining);
}

/** Build a user-initiated issue URL without pre-filling error or device data. */
export function buildIssueUrl(): string {
  const title = encodeURIComponent("[user-report] Structural Phase incident");
  const body = encodeURIComponent(
    [
      "<!-- Add only details you are comfortable sharing publicly. -->",
      "",
      "**What happened**:",
      "<!-- describe the action and expected result -->",
    ].join("\n")
  );
  return `https://github.com/dada8899/structural-isomorphism/issues/new?title=${title}&body=${body}`;
}
