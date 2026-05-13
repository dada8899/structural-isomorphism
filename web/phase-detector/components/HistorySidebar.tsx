"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  getHistory,
  clearHistory,
  type HistoryEntry,
} from "@/lib/history";
import { EXAMPLE_QUERIES } from "@/lib/parse-query";

// Perplexity-style history sidebar for Phase Detector.
// Desktop ≥1024px: 240px left rail, collapsible to 56px (state in localStorage).
// Mobile <1024px: off-canvas drawer behind floating hamburger trigger.
// Reads from lib/history.ts (writer wired in SearchHero submit + parse-query route).

const COLLAPSED_KEY = "phase_sidebar_collapsed";

function timeAgo(ts: number): string {
  const diffSec = Math.floor((Date.now() - ts) / 1000);
  if (diffSec < 60) return "刚刚";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} 分钟前`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} 小时前`;
  if (diffSec < 604800) return `${Math.floor(diffSec / 86400)} 天前`;
  const d = new Date(ts);
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

function removeFromHistory(ts: number): void {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem("phase_history");
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.entries)) return;
    parsed.entries = parsed.entries.filter(
      (e: HistoryEntry) => e && e.ts !== ts,
    );
    if (Array.isArray(parsed.pinned)) {
      parsed.pinned = parsed.pinned.filter((id: number) => id !== ts);
    }
    window.localStorage.setItem("phase_history", JSON.stringify(parsed));
  } catch {
    /* quota / private mode */
  }
}

export default function HistorySidebar() {
  const [entries, setEntries] = useState<HistoryEntry[]>([]);
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);

  const refresh = useCallback(() => {
    setEntries(getHistory());
  }, []);

  useEffect(() => {
    setHydrated(true);
    try {
      if (window.localStorage.getItem(COLLAPSED_KEY) === "1") {
        setCollapsed(true);
      }
    } catch {
      /* ignore */
    }
    refresh();

    // Cross-tab + page-visibility re-render.
    const onStorage = (ev: StorageEvent) => {
      if (ev.key === "phase_history") refresh();
    };
    const onVis = () => {
      if (!document.hidden) refresh();
    };
    window.addEventListener("storage", onStorage);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("storage", onStorage);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [refresh]);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  const handleDelete = (ts: number) => {
    removeFromHistory(ts);
    refresh();
  };

  const handleClear = () => {
    if (window.confirm("确定清空所有历史？")) {
      clearHistory();
      refresh();
    }
  };

  if (!hydrated) return null;

  const isEmpty = entries.length === 0;

  return (
    <>
      {/* Mobile floating trigger */}
      <button
        type="button"
        aria-label="打开历史"
        onClick={() => setDrawerOpen(true)}
        className="fixed bottom-5 left-4 z-[95] flex h-11 w-11 items-center justify-center rounded-full bg-zinc-900 text-white shadow-lg hover:bg-accent lg:hidden"
      >
        <span aria-hidden>☰</span>
      </button>

      {/* Mobile backdrop */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-[89] bg-black/30 lg:hidden"
          onClick={() => setDrawerOpen(false)}
        />
      )}

      <aside
        aria-label="最近的查询"
        className={[
          "fixed left-0 top-0 bottom-0 z-[90] flex flex-col border-r border-zinc-200 bg-zinc-50 transition-[width,transform] duration-200",
          collapsed ? "lg:w-14" : "lg:w-60",
          "w-[280px]",
          drawerOpen ? "translate-x-0 shadow-2xl" : "-translate-x-full lg:translate-x-0",
        ].join(" ")}
      >
        <div className="flex flex-shrink-0 items-center justify-between border-b border-zinc-200 px-4 py-3">
          {!collapsed && (
            <span className="text-[13px] font-semibold tracking-wide text-zinc-900">
              最近的查询
            </span>
          )}
          <button
            type="button"
            aria-label={collapsed ? "展开" : "收起"}
            title={collapsed ? "展开" : "收起"}
            onClick={() => {
              if (drawerOpen) setDrawerOpen(false);
              else toggleCollapsed();
            }}
            className="ml-auto rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900"
          >
            <span aria-hidden>{collapsed ? "›" : "‹"}</span>
          </button>
        </div>

        {!collapsed && (
          <>
            <div className="flex-1 overflow-y-auto px-2 pb-4 pt-2">
              {isEmpty ? (
                <div className="px-3 py-2">
                  <p className="mb-3 text-xs leading-relaxed text-zinc-500">
                    你用过的查询会出现在这里。试试看：
                  </p>
                  {EXAMPLE_QUERIES.slice(0, 4).map((q) => (
                    <Link
                      key={q}
                      href={`/?q=${encodeURIComponent(q)}`}
                      onClick={() => setDrawerOpen(false)}
                      className="mb-2 block rounded-lg border border-zinc-200 bg-white px-3 py-2.5 text-[13px] leading-snug text-zinc-900 hover:border-accent hover:text-accent"
                    >
                      {q}
                    </Link>
                  ))}
                </div>
              ) : (
                entries.map((entry) => (
                  <div
                    key={entry.ts}
                    className="group relative mb-0.5 rounded-lg border border-transparent hover:border-zinc-200 hover:bg-white"
                  >
                    <Link
                      href={entry.route || `/?q=${encodeURIComponent(entry.query)}`}
                      onClick={() => setDrawerOpen(false)}
                      className="block px-3 py-2.5"
                    >
                      <div className="line-clamp-2 text-[13px] leading-snug text-zinc-900">
                        {entry.query}
                      </div>
                      <div className="mt-1 text-[11px] text-zinc-400">
                        {timeAgo(entry.ts)}
                      </div>
                    </Link>
                    <button
                      type="button"
                      aria-label="删除"
                      title="删除"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleDelete(entry.ts);
                      }}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-sm leading-none text-zinc-400 opacity-0 hover:bg-red-50 hover:text-red-600 group-hover:opacity-100"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="flex-shrink-0 border-t border-zinc-200 px-4 py-2.5">
              <button
                type="button"
                onClick={handleClear}
                className="text-[11px] text-zinc-500 hover:text-red-600"
              >
                清空历史
              </button>
            </div>
          </>
        )}
      </aside>
    </>
  );
}
