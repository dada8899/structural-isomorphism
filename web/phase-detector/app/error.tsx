"use client";

// W12-E: page-level error boundary with auto-reporting + GitHub-issue link.
// Previously (W6-E) we logged to console only. Now:
//   • Auto-POSTs to /api/errors with sessionId + digest (no PII).
//   • "Report this" link pre-fills a GitHub issue.
//   • Graceful retry button preserves the route.
// Stale data (if any was kept in sessionStorage by parent components) remains
// rendered around this boundary — Next.js only swaps the failing segment.

import { useEffect } from "react";

import { buildIssueUrl, reportError } from "@/lib/error-reporter";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorBoundary({ error, reset }: ErrorProps) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[phase-detector] runtime error captured by error.tsx:", error);
    // Fire-and-forget; reporter handles offline + rate limit internally.
    reportError({ error }).catch(() => {
      /* never throw from a boundary */
    });
  }, [error]);

  const issueUrl = typeof window !== "undefined" ? buildIssueUrl(error) : "#";

  return (
    <div className="mx-auto max-w-2xl py-16">
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="mb-2 text-lg font-semibold tracking-tight text-amber-900">
          Something went wrong
        </h2>
        <p className="mb-2 text-sm leading-relaxed text-zinc-700">
          页面遇到了一点问题。这通常是临时网络波动或浏览器缓存的旧版本与新版资源不匹配导致。
        </p>
        <p className="mb-4 text-xs leading-relaxed text-zinc-500">
          We&apos;ve automatically logged this incident. Try the action again, or
          report it if it keeps happening.
        </p>
        {error.digest && (
          <p className="mb-4 text-xs text-zinc-500">
            Error ID: <code className="font-mono">{error.digest}</code>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={reset}
            data-testid="error-retry"
            className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            Try again
          </button>
          <a
            href="/"
            className="inline-flex items-center rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400"
          >
            返回首页
          </a>
          <a
            href={issueUrl}
            target="_blank"
            rel="noopener noreferrer"
            data-testid="error-report"
            className="inline-flex items-center text-sm font-medium text-amber-700 underline-offset-2 hover:underline"
          >
            Report this ↗
          </a>
        </div>
      </div>
    </div>
  );
}
