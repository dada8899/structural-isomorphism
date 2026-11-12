"use client";

// W12-E: offline fallback page served by the service worker when:
//   • Network is offline AND
//   • No cache hit for the requested HTML route.
//
// Shows the latest cached phase snapshot if it's available in localStorage
// (CompanyCard / ScreenerFilter typically mirror their fetch results there
// for instant re-mount — we read read-only here, no writes).

import { useEffect, useState } from "react";

interface CachedPhase {
  ticker: string;
  name?: string;
  phase?: string;
  score?: number;
  updatedAt?: string;
}

function readCachedPhases(): CachedPhase[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem("phase.lastSnapshot");
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, 20);
  } catch {
    return [];
  }
}

export default function OfflinePage() {
  const [cached, setCached] = useState<CachedPhase[]>([]);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    setCached(readCachedPhases());
  }, []);

  function handleRetry() {
    setRetrying(true);
    if (typeof window !== "undefined") {
      window.location.reload();
    }
  }

  return (
    <div className="mx-auto max-w-2xl py-12" data-testid="offline-page">
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          <span className="inline-flex h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
          <h1 className="text-lg font-semibold tracking-tight text-zinc-900">
            You&apos;re offline
          </h1>
        </div>
        <p className="mb-4 text-sm leading-relaxed text-zinc-600">
          网络连接不可用。下方显示的是浏览器最近缓存的快照（只读）。重新联网后点击重试可以刷新到最新数据。
        </p>
        <button
          type="button"
          onClick={handleRetry}
          disabled={retrying}
          data-testid="offline-retry"
          className="mb-6 inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:opacity-60"
        >
          {retrying ? "Retrying…" : "Try again"}
        </button>

        {cached.length > 0 ? (
          <div>
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Latest cached snapshot
            </h2>
            <ul className="divide-y divide-zinc-100 rounded-lg border border-zinc-100">
              {cached.map((row) => (
                <li
                  key={row.ticker}
                  data-testid="offline-cached-row"
                  className="flex items-center justify-between px-3 py-2 text-sm"
                >
                  <div className="flex flex-col">
                    <span className="font-mono text-xs text-zinc-500">{row.ticker}</span>
                    {row.name && <span className="text-zinc-800">{row.name}</span>}
                  </div>
                  <div className="text-right text-xs text-zinc-600">
                    {row.phase && <div>{row.phase}</div>}
                    {typeof row.score === "number" && (
                      <div className="font-mono">{row.score.toFixed(2)}</div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {cached[0]?.updatedAt && (
              <p className="mt-2 text-xs text-zinc-400">
                Snapshot taken {cached[0].updatedAt}
              </p>
            )}
          </div>
        ) : (
          <p className="text-xs text-zinc-400">
            No cached data found — visit a few company pages with a connection to
            populate offline mode.
          </p>
        )}
      </div>
    </div>
  );
}
