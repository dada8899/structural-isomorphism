"use client";

// W6-E P1 fix: client error boundary so stray errors (e.g. Next.js Server
// Action mismatch from old browser tabs, or transient API failures) don't
// produce a bare "Application error: a client-side exception has occurred"
// screen. Captures the error, logs it (Plausible-friendly), and shows a
// friendly fallback with a retry path.

import { useEffect } from "react";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorBoundary({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log to console for debugging; consider piping to Plausible/Sentry later.
    // eslint-disable-next-line no-console
    console.error("[phase-detector] runtime error captured by error.tsx:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl py-16">
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-6">
        <h2 className="mb-2 text-lg font-semibold tracking-tight text-amber-900">
          页面遇到了一点问题
        </h2>
        <p className="mb-4 text-sm leading-relaxed text-zinc-700">
          这通常是由于浏览器缓存了旧版本的页面资源，与服务端发布的新版本不匹配导致。
          请尝试刷新页面，或返回首页。
        </p>
        {error.digest && (
          <p className="mb-4 text-xs text-zinc-500">
            错误 ID: <code className="font-mono">{error.digest}</code>
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            重试
          </button>
          <a
            href="/"
            className="inline-flex items-center rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400"
          >
            返回首页
          </a>
        </div>
      </div>
    </div>
  );
}
