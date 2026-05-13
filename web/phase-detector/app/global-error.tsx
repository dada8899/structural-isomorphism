"use client";

// W6-E P1 fix: global error boundary — catches errors thrown in app/layout.tsx
// itself, where the per-route error.tsx cannot help. Must include its own
// <html> + <body>.

import { useEffect } from "react";

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("[phase-detector] global runtime error:", error);
  }, [error]);

  return (
    <html lang="en">
      <body className="min-h-screen bg-white font-sans text-gray-900 antialiased">
        <main className="mx-auto max-w-2xl px-6 py-16">
          <h2 className="mb-2 text-lg font-semibold tracking-tight text-zinc-900">
            页面遇到了严重错误
          </h2>
          <p className="mb-4 text-sm leading-relaxed text-zinc-700">
            请刷新页面重试。如果问题持续，可能是部署中。
          </p>
          {error.digest && (
            <p className="mb-4 text-xs text-zinc-500">
              错误 ID: <code className="font-mono">{error.digest}</code>
            </p>
          )}
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800"
          >
            重试
          </button>
        </main>
      </body>
    </html>
  );
}
