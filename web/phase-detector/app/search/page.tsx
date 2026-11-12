// W13-E (session #10): /search deep-link page.
//
// Visiting /search auto-opens the Cmd+K palette so deep-links from external
// sources (newsletter "search this", docs "find") drop the user directly
// into search mode without needing the keyboard shortcut.
//
// Renders a minimal landing under the palette so non-JS visitors still see
// a static page (the palette JS auto-opens on mount).

import type { Metadata } from "next";
import SearchAutoOpen from "./SearchAutoOpen";

export const metadata: Metadata = {
  title: "搜索 / Search",
  description: "全站搜索：公司、普适类、论文、周刊、文档。",
  robots: { index: false, follow: true },
};

export default function SearchPage() {
  return (
    <div className="mx-auto max-w-2xl py-10 text-center">
      <h1 className="text-2xl font-semibold text-zinc-900">搜索 / Search</h1>
      <p className="mt-2 text-sm text-zinc-500">
        快捷键 <kbd className="rounded border border-zinc-200 bg-zinc-50 px-1 py-0.5 font-mono text-[11px]">⌘K</kbd>{" "}
        / <kbd className="rounded border border-zinc-200 bg-zinc-50 px-1 py-0.5 font-mono text-[11px]">Ctrl+K</kbd>{" "}
        随时唤起站内搜索。
      </p>
      <SearchAutoOpen />
    </div>
  );
}
