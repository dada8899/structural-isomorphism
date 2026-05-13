"use client";

// PR-4: Perplexity-style search hero for Phase Detector home page.
//
// Sits between the H1/subhead and the signal blocks. Replaces the legacy
// "开始查看 →" scroll-to-filter CTA with a real search input + autocomplete.
//
// Sources for autocomplete (debounced 180ms, max 8 items):
//   A) Tickers from the 97 companies in the screener (lazy-fetched once on
//      mount and cached on the component).
//   B) Curated example queries from lib/parse-query.ts.
//   C) Recent searches from localStorage (lib/history.ts).
//
// Submit semantics:
//   - parse-query.ts decides the route ("/company/X" vs "/?...").
//   - Parent owns navigation + history write — we only call onSubmit.

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { fetchScreener } from "@/lib/api";
import { EXAMPLE_QUERIES } from "@/lib/parse-query";
import { getHistory, type HistoryEntry } from "@/lib/history";

interface Props {
  onSubmit: (rawQuery: string) => void;
  // Optional placeholder override (defaults to PR-4 spec).
  placeholder?: string;
}

interface Suggestion {
  label: string;
  // What gets submitted when the user picks this item.
  value: string;
  kind: "ticker" | "example" | "history";
  hint?: string;
}

const DEBOUNCE_MS = 180;
const MAX_SUGGESTIONS = 8;
const DEFAULT_PLACEHOLDER =
  "搜公司或问题 — 比如『哪些能源公司接近翻转？』或『AAPL』";
const CHIP_QUERIES = EXAMPLE_QUERIES.slice(0, 4);

export function SearchHero({ onSubmit, placeholder }: Props) {
  const [value, setValue] = useState("");
  const [debounced, setDebounced] = useState("");
  const [tickers, setTickers] = useState<Array<{ ticker: string; sector?: string }>>([]);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Lazy-fetch screener tickers once for prefix match.
  useEffect(() => {
    let cancelled = false;
    fetchScreener({ limit: 200 })
      .then((rows) => {
        if (cancelled) return;
        setTickers(
          rows.map((r) => ({ ticker: r.ticker, sector: r.sector })),
        );
      })
      .catch(() => {
        // non-fatal — autocomplete just won't include tickers.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Pull recent searches from localStorage once on mount.
  useEffect(() => {
    setHistory(getHistory().slice(0, 8));
  }, []);

  // Debounce the input → suggestions trigger.
  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value.trim()), DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [value]);

  // Close dropdown when clicking outside.
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    window.addEventListener("mousedown", handleClick);
    return () => window.removeEventListener("mousedown", handleClick);
  }, []);

  const suggestions = useMemo<Suggestion[]>(() => {
    const q = debounced.toLowerCase();
    const out: Suggestion[] = [];
    const seen = new Set<string>();

    // 1) Ticker prefix match (only when user has typed at least 1 char).
    if (q.length > 0) {
      for (const t of tickers) {
        if (out.length >= MAX_SUGGESTIONS) break;
        const lt = t.ticker.toLowerCase();
        if (lt.startsWith(q) || (q.length >= 2 && lt.includes(q))) {
          const key = `ticker:${t.ticker}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({
            label: t.ticker,
            value: t.ticker,
            kind: "ticker",
            hint: t.sector,
          });
        }
      }
    }

    // 2) Example queries — match by substring when typing, full list when empty.
    for (const ex of EXAMPLE_QUERIES) {
      if (out.length >= MAX_SUGGESTIONS) break;
      const match = q.length === 0 || ex.toLowerCase().includes(q);
      if (!match) continue;
      const key = `example:${ex}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ label: ex, value: ex, kind: "example" });
    }

    // 3) Recent searches (only show when input is empty — keeps the dropdown
    // focused on relevant matches once the user is typing).
    if (q.length === 0) {
      for (const h of history) {
        if (out.length >= MAX_SUGGESTIONS) break;
        const key = `history:${h.query.toLowerCase()}`;
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({
          label: h.query,
          value: h.query,
          kind: "history",
          hint: "最近搜索",
        });
      }
    }

    return out.slice(0, MAX_SUGGESTIONS);
  }, [debounced, tickers, history]);

  // Reset highlight when suggestion list changes.
  useEffect(() => {
    setHighlight(0);
  }, [suggestions.length]);

  const submit = useCallback(
    (raw: string) => {
      const q = raw.trim();
      if (!q) return;
      setOpen(false);
      onSubmit(q);
      // Refresh local history snapshot so the next focus shows it.
      setTimeout(() => setHistory(getHistory().slice(0, 8)), 0);
    },
    [onSubmit],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (suggestions.length === 0) return;
        setOpen(true);
        setHighlight((h) => (h + 1) % suggestions.length);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (suggestions.length === 0) return;
        setOpen(true);
        setHighlight((h) => (h - 1 + suggestions.length) % suggestions.length);
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (open && suggestions[highlight]) {
          submit(suggestions[highlight].value);
        } else if (value.trim()) {
          submit(value);
        }
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    },
    [open, suggestions, highlight, value, submit],
  );

  return (
    <section
      aria-label="搜索公司"
      className="rounded-2xl border border-zinc-200 bg-white px-5 py-6 sm:px-8 sm:py-7"
    >
      <div ref={containerRef} className="mx-auto w-full max-w-[720px]">
        <div className="relative">
          <label htmlFor="phase-search" className="sr-only">
            搜索公司或问题
          </label>
          <div className="flex items-center rounded-xl border border-zinc-300 bg-white px-4 transition focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="mr-2 shrink-0 text-zinc-400"
              aria-hidden="true"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="M21 21l-4.3-4.3" />
            </svg>
            <input
              id="phase-search"
              ref={inputRef}
              type="text"
              role="combobox"
              aria-expanded={open}
              aria-controls="phase-search-listbox"
              aria-autocomplete="list"
              autoComplete="off"
              value={value}
              placeholder={placeholder ?? DEFAULT_PLACEHOLDER}
              className="h-14 flex-1 bg-transparent text-base text-zinc-900 placeholder:text-zinc-400 focus:outline-none"
              onChange={(e) => {
                setValue(e.target.value);
                setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              onKeyDown={handleKeyDown}
            />
            {value && (
              <button
                type="button"
                aria-label="清除搜索"
                onClick={() => {
                  setValue("");
                  setDebounced("");
                  inputRef.current?.focus();
                }}
                className="ml-2 rounded p-1 text-zinc-400 transition hover:bg-zinc-100 hover:text-zinc-700"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {open && suggestions.length > 0 && (
            <ul
              id="phase-search-listbox"
              role="listbox"
              className="absolute left-0 right-0 top-[calc(100%+6px)] z-20 max-h-80 overflow-y-auto rounded-xl border border-zinc-200 bg-white py-1 shadow-lg"
            >
              {suggestions.map((s, i) => (
                <li
                  key={`${s.kind}:${s.value}:${i}`}
                  role="option"
                  aria-selected={i === highlight}
                  className={`flex cursor-pointer items-center justify-between gap-3 px-4 py-2 text-sm ${
                    i === highlight
                      ? "bg-accent/5 text-zinc-900"
                      : "text-zinc-700 hover:bg-zinc-50"
                  }`}
                  onMouseEnter={() => setHighlight(i)}
                  onMouseDown={(e) => {
                    // mousedown (not click) so it fires before the input blurs.
                    e.preventDefault();
                    submit(s.value);
                  }}
                >
                  <div className="flex items-center gap-2 truncate">
                    <KindIcon kind={s.kind} />
                    <span className="truncate">{s.label}</span>
                  </div>
                  {s.hint && (
                    <span className="shrink-0 text-xs text-zinc-400">
                      {s.hint}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Try-one-of-these chip row (gap 12px = gap-3). */}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span className="text-xs text-zinc-500">试试看：</span>
          {CHIP_QUERIES.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => {
                setValue(q);
                submit(q);
              }}
              className="rounded-full border border-zinc-200 bg-white px-3 py-1 text-xs text-zinc-700 transition hover:border-accent hover:text-accent"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

function KindIcon({ kind }: { kind: Suggestion["kind"] }) {
  if (kind === "ticker") {
    return (
      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded bg-accent/10 text-[10px] font-semibold text-accent">
        T
      </span>
    );
  }
  if (kind === "history") {
    return (
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-zinc-400"
        aria-hidden="true"
      >
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5" />
        <path d="M12 7v5l3 2" />
      </svg>
    );
  }
  // example
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0 text-zinc-400"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v4l3 2" />
    </svg>
  );
}
