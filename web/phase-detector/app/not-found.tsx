// W17 polish (session #11+): Chinese-localized 404 page.
//
// Replaces Next.js's default English 404 with site-styled Chinese copy.
// Provides two CTAs: back to home (Link) and back to previous page
// (history.back via client component button). Uses zinc palette + dark-
// mode-aware utility classes consistent with other pages (error.tsx,
// offline/page.tsx, me/page.tsx).

"use client";

import Link from "next/link";

export default function NotFound() {
  function goBack() {
    if (typeof window !== "undefined" && window.history.length > 1) {
      window.history.back();
    } else if (typeof window !== "undefined") {
      window.location.href = "/";
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-20" data-testid="not-found-page">
      <p className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        404
      </p>
      <h1 className="mb-3 text-3xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">
        页面没找到
      </h1>
      <p className="mb-8 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        你访问的地址不存在，可能已被移动或拼写有误。试试回到首页，或返回上一页继续浏览。
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Link
          href="/"
          data-testid="not-found-home"
          className="inline-flex items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white"
        >
          回到首页
        </Link>
        <button
          type="button"
          onClick={goBack}
          data-testid="not-found-back"
          className="inline-flex items-center rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition hover:border-zinc-400 dark:border-zinc-700 dark:text-zinc-200 dark:hover:border-zinc-500"
        >
          返回上一页
        </button>
      </div>
    </main>
  );
}
