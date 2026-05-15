"use client";

// W13-E (session #10): Cmd+K command palette.
//
// Site-wide instant search across companies / universality classes / papers /
// newsletters / docs. Client-side index loaded lazily from /search-index.json
// on first open (cached afterwards).
//
// Trigger sources:
//   - Cmd+K (Mac) / Ctrl+K (Win/Linux) — global keydown
//   - Search icon in TopNav (component below imports this)
//   - /search deep-link page (auto-opens on mount)
//
// Accessibility:
//   - role="dialog" + aria-modal="true"
//   - input has role="combobox" with aria-controls + aria-activedescendant
//   - results list has role="listbox"; each option has role="option"
//   - focus trapped within the dialog; Esc closes; arrow keys navigate
//   - screen reader hears "X results" via aria-live polite region
//
// Mobile:
//   - < 640px: full-screen overlay
//   - ≥ 640px: modal centered, 600px wide
//   - softKeyboard adapts via `100dvh` not `100vh`

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { trackEvent } from "@/lib/analytics";
import {
  type SearchEntry,
  type SearchHit,
  groupHitsByType,
  searchIndex,
} from "@/lib/search";
import { listInsightCases } from "@/lib/insights-data";

/**
 * Insight cases are static, in-repo, and tiny — merge them into the index
 * at component-load time rather than baking them into search-index.json.
 * This keeps the JSON purely build-output and lets the cases live with
 * their data file.
 *
 * Keyword set is generous: case ID, title, domain names, universality
 * class name, and the synthesis answer-shaped one-liner — so a query
 * like "kuaishou" or "growth" or "platform" hits the viral-content case
 * even though those words aren't in the title.
 */
function insightCaseSearchEntries(): SearchEntry[] {
  return listInsightCases().map((c) => {
    const kwBlob = [
      c.id,
      c.title,
      c.subtitle,
      c.domains.a,
      c.domains.b,
      c.universality_class_name,
      c.synthesis.best_current_answer,
    ]
      .join(" ")
      .toLowerCase();
    return {
      id: `insight-${c.id}`,
      type: "insight_case" as const,
      title: c.title,
      subtitle: c.synthesis.best_current_answer.slice(0, 180),
      url: `/insights/${c.id}`,
      keywords: Array.from(
        new Set(kwBlob.split(/[^a-z0-9一-鿿]+/).filter((w) => w.length >= 2)),
      ).slice(0, 40),
      weight: 6, // above docs (4), below companies (10) — high-value editorial
    };
  });
}

const RECENT_KEY = "phase:cmdk:recent";
const RECENT_MAX = 5;

// Trending queries — hardcoded for now (could be server-fed later).
// Pick 5 representative entry-points across types.
const TRENDING: Array<{ label: string; query: string }> = [
  { label: "AAPL", query: "AAPL" },
  { label: "Cascade in your platform", query: "viral cascade" },
  { label: "Liquidation risk", query: "liquidation defi" },
  { label: "Scheffer fold", query: "scheffer" },
  { label: "Newsletter #001", query: "issue 001" },
];

function loadRecent(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((s) => typeof s === "string").slice(0, RECENT_MAX) : [];
  } catch {
    return [];
  }
}

function pushRecent(q: string): void {
  if (typeof window === "undefined") return;
  const trimmed = q.trim();
  if (!trimmed) return;
  try {
    const prev = loadRecent();
    const next = [trimmed, ...prev.filter((p) => p !== trimmed)].slice(0, RECENT_MAX);
    window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore — localStorage may be unavailable
  }
}

function TypeIcon({ type, className }: { type: string; className?: string }) {
  // Tiny inline SVGs keep us off icon-font deps.
  const cls = className ?? "h-4 w-4 shrink-0 text-zinc-500";
  switch (type) {
    case "company":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          <path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M9 13h.01M9 17h.01M15 9h.01M15 13h.01M15 17h.01" />
        </svg>
      );
    case "universality_class":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          <circle cx="6" cy="6" r="3" />
          <circle cx="18" cy="18" r="3" />
          <path d="M8.5 8.5l7 7" />
        </svg>
      );
    case "insight_case":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          {/* A lightbulb-ish icon: idea applied to a problem. */}
          <path d="M9 18h6M10 22h4" />
          <path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V18h6v-1.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2z" />
        </svg>
      );
    case "paper":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <path d="M14 2v6h6M8 13h8M8 17h8M8 9h2" />
        </svg>
      );
    case "newsletter":
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="M3 7l9 6 9-6" />
        </svg>
      );
    case "docs":
    default:
      return (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={cls} aria-hidden="true">
          <path d="M4 4h11a3 3 0 0 1 3 3v13H7a3 3 0 0 1-3-3z" />
          <path d="M4 17a3 3 0 0 1 3-3h11" />
        </svg>
      );
  }
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  /** "shortcut" | "nav-click" | "deep-link" — for Plausible tracking. */
  source?: string;
}

export default function CommandPalette({ open, onClose, source }: CommandPaletteProps) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState<SearchEntry[] | null>(null);
  const [activeIdx, setActiveIdx] = useState(0);
  const [recent, setRecent] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Track open event (once per open).
  const lastOpenTracked = useRef(false);
  useEffect(() => {
    if (!open) {
      lastOpenTracked.current = false;
      return;
    }
    if (lastOpenTracked.current) return;
    lastOpenTracked.current = true;
    trackEvent("search_opened", { source: source ?? "shortcut" });
  }, [open, source]);

  // Lazy-load the search index on first open.
  useEffect(() => {
    if (!open || index !== null || loadError) return;
    let cancelled = false;
    fetch("/search-index.json", { credentials: "same-origin" })
      .then((r) => {
        if (!r.ok) throw new Error(`status ${r.status}`);
        return r.json() as Promise<SearchEntry[]>;
      })
      .then((data) => {
        if (cancelled) return;
        // Session #12 W17: merge in static insight cases so /insights is
        // searchable from Cmd+K. The cases live in lib/insights-data
        // (in-repo), so we avoid round-tripping them through the static
        // search-index.json.
        const baseline = Array.isArray(data) ? data : [];
        setIndex([...insightCaseSearchEntries(), ...baseline]);
      })
      .catch((e) => {
        if (cancelled) return;
        setLoadError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [open, index, loadError]);

  // Load recent on open.
  useEffect(() => {
    if (!open) return;
    setRecent(loadRecent());
  }, [open]);

  // Focus input when opening.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [open]);

  // Reset state on close.
  useEffect(() => {
    if (open) return;
    setQuery("");
    setActiveIdx(0);
  }, [open]);

  // Lock body scroll while open.
  useEffect(() => {
    if (typeof document === "undefined") return;
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Compute hits (memoized).
  const hits: SearchHit[] = useMemo(() => {
    if (!index || !query.trim()) return [];
    return searchIndex(index, query, 8);
  }, [index, query]);

  const groups = useMemo(() => groupHitsByType(hits), [hits]);

  // Track query event (debounced — 350 ms after typing settles).
  useEffect(() => {
    if (!open) return;
    if (!query.trim()) return;
    const t = setTimeout(() => {
      trackEvent("search_query", {
        query_length: query.length,
        result_count: hits.length,
      });
    }, 350);
    return () => clearTimeout(t);
  }, [open, query, hits.length]);

  // Reset active index when results change.
  useEffect(() => {
    setActiveIdx(0);
  }, [hits.length, query]);

  const goTo = useCallback(
    (hit: SearchHit, position: number) => {
      trackEvent("search_result_click", {
        result_type: hit.type,
        result_position: position,
      });
      pushRecent(query.trim() || hit.title);
      onClose();
      router.push(hit.url);
    },
    [onClose, router, query],
  );

  // Keyboard navigation inside the dialog.
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, Math.max(0, hits.length - 1)));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(0, i - 1));
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const target = hits[activeIdx];
        if (target) goTo(target, activeIdx);
        return;
      }
      // Focus trap: Tab cycles within dialog (input + result buttons).
      if (e.key === "Tab") {
        const root = dialogRef.current;
        if (!root) return;
        const focusables = root.querySelectorAll<HTMLElement>(
          'input, [data-cmdk-item], button:not([disabled])',
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [hits, activeIdx, goTo, onClose],
  );

  if (!open) return null;

  const showEmpty = !query.trim();
  const activeId = hits[activeIdx] ? `cmdk-opt-${hits[activeIdx].id}` : undefined;

  // Compute a flat ordering so activeIdx maps to a single hit. We use the
  // ungrouped `hits` array — group rendering preserves order, so position N
  // in `hits` corresponds visually to position N when reading top-down.
  let renderPos = -1;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="搜索 / Search"
      data-testid="cmdk-dialog"
      ref={dialogRef}
      onKeyDown={onKeyDown}
      className="fixed inset-0 z-[100] flex items-start justify-center"
      style={{ height: "100dvh" }}
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="关闭搜索"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/40 backdrop-blur-sm"
        tabIndex={-1}
      />

      {/* Panel */}
      <div
        className="relative mt-0 flex w-full max-w-[600px] flex-col overflow-hidden border-zinc-200 bg-white shadow-xl sm:mt-[10vh] sm:rounded-xl sm:border"
        style={{ maxHeight: "100dvh" }}
      >
        {/* Input row */}
        <div className="flex items-center gap-3 border-b border-zinc-200 px-4 py-3">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-5 w-5 text-zinc-400"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜公司、普适类、论文、周刊、文档…"
            aria-label="搜索内容"
            role="combobox"
            aria-expanded={hits.length > 0}
            aria-controls="cmdk-listbox"
            aria-activedescendant={activeId}
            aria-autocomplete="list"
            data-testid="cmdk-input"
            className="flex-1 bg-transparent text-base text-zinc-900 outline-none placeholder:text-zinc-400"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded border border-zinc-200 px-1.5 py-0.5 text-xs text-zinc-500 hover:bg-zinc-50"
          >
            Esc
          </button>
        </div>

        {/* Live announce for SR */}
        <div className="sr-only" aria-live="polite" aria-atomic="true">
          {query.trim()
            ? hits.length === 0
              ? "没有匹配结果"
              : `${hits.length} 条结果`
            : ""}
        </div>

        {/* Body */}
        <div
          id="cmdk-listbox"
          role="listbox"
          aria-label="搜索结果"
          className="max-h-[60vh] overflow-y-auto"
          style={{ overscrollBehavior: "contain" }}
        >
          {showEmpty ? (
            <div className="px-4 py-4 text-sm">
              {recent.length > 0 && (
                <div className="mb-4">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
                    最近搜索 / Recent
                  </div>
                  <ul className="flex flex-col">
                    {recent.map((r) => (
                      <li key={r}>
                        <button
                          type="button"
                          data-cmdk-item
                          onClick={() => setQuery(r)}
                          className="block w-full rounded px-2 py-1.5 text-left text-zinc-700 hover:bg-zinc-50"
                        >
                          {r}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div>
                <div className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-400">
                  热门 / Trending
                </div>
                <ul className="flex flex-col">
                  {TRENDING.map((t) => (
                    <li key={t.query}>
                      <button
                        type="button"
                        data-cmdk-item
                        onClick={() => setQuery(t.query)}
                        className="block w-full rounded px-2 py-1.5 text-left text-zinc-700 hover:bg-zinc-50"
                      >
                        {t.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : loadError ? (
            <div className="px-4 py-6 text-sm text-rose-600">
              加载搜索索引失败：{loadError}
            </div>
          ) : !index ? (
            <div className="px-4 py-6 text-sm text-zinc-500">加载中…</div>
          ) : hits.length === 0 ? (
            <div className="px-4 py-6 text-sm text-zinc-500">
              没有匹配 “{query}” 的结果
            </div>
          ) : (
            <ul className="flex flex-col">
              {groups.map((g) => (
                <li key={g.type}>
                  <div className="px-4 py-1 text-[11px] font-medium uppercase tracking-wider text-zinc-400">
                    {g.label}
                  </div>
                  <ul>
                    {g.hits.map((hit) => {
                      renderPos += 1;
                      const isActive = renderPos === activeIdx;
                      const optId = `cmdk-opt-${hit.id}`;
                      const pos = renderPos;
                      return (
                        <li key={hit.id}>
                          <button
                            type="button"
                            id={optId}
                            role="option"
                            aria-selected={isActive}
                            data-cmdk-item
                            data-testid={`cmdk-result-${hit.type}`}
                            onMouseEnter={() => setActiveIdx(pos)}
                            onClick={() => goTo(hit, pos)}
                            className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm ${
                              isActive ? "bg-zinc-100" : "hover:bg-zinc-50"
                            }`}
                          >
                            <TypeIcon type={hit.type} />
                            <span className="flex min-w-0 flex-1 flex-col">
                              <span className="truncate font-medium text-zinc-900">
                                {hit.title}
                              </span>
                              <span className="truncate text-xs text-zinc-500">
                                {hit.subtitle}
                              </span>
                            </span>
                            {isActive && (
                              <span
                                aria-hidden="true"
                                className="hidden shrink-0 rounded border border-zinc-200 px-1.5 py-0.5 text-[10px] text-zinc-500 sm:inline"
                              >
                                Enter ↵
                              </span>
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer hints */}
        <div className="hidden items-center justify-between border-t border-zinc-100 px-4 py-2 text-[11px] text-zinc-400 sm:flex">
          <span>↑↓ 导航 · ↵ 打开 · Esc 关闭</span>
          <span>{hits.length > 0 ? `${hits.length} 条结果` : ""}</span>
        </div>
      </div>
    </div>
  );
}
