"use client";

// W12-E: root-level error boundary — catches errors thrown in app/layout.tsx
// itself, where the per-route error.tsx cannot help. Must include its own
// <html> + <body>. Kept intentionally minimal: no fancy fonts / SVG imports,
// because the parent layout's runtime is presumed broken.
//
// Auto-reports via /api/errors using only fetch + plain HTML (no @/ aliases —
// if the bundler is borked we still want this to render).

import { useEffect } from "react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

async function _report(error: Error & { digest?: string }) {
  try {
    let sessionId = "no-storage";
    try {
      sessionId = window.localStorage.getItem("phase.sessionId") || "no-id";
    } catch {
      /* no-op */
    }
    await fetch("/api/errors", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: String(error?.message || "global error").slice(0, 500),
        stack: (error?.stack || "").slice(0, 4000),
        digest: error?.digest,
        url: window.location.origin + window.location.pathname,
        userAgent: navigator.userAgent.slice(0, 300),
        timestamp: Math.floor(Date.now() / 1000),
        sessionId,
        fatal: true,
      }),
      keepalive: true,
    });
  } catch {
    /* swallow — we're in a fatal path */
  }
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[phase-detector] global runtime error:", error);
    _report(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-white font-sans text-gray-900 antialiased">
        <main className="mx-auto max-w-2xl px-6 py-16">
          <h2 className="mb-2 text-lg font-semibold tracking-tight text-zinc-900">
            Something went seriously wrong
          </h2>
          <p className="mb-4 text-sm leading-relaxed text-zinc-700">
            页面遇到了严重错误。请刷新页面重试。如果问题持续，可能是部署中。
          </p>
          {error.digest && (
            <p className="mb-4 text-xs text-zinc-500">
              Error ID: <code className="font-mono">{error.digest}</code>
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
