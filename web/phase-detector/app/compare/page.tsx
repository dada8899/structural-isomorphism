"use client";

// W10-E /compare — side-by-side ticker comparison page.
//
// URL contract: /compare?tickers=AAPL,TSLA,JPM   (2-5 comma-separated)
//   * State is fully captured in the URL so the page is shareable.
//   * Adding/removing tickers triggers a router replace, not a push, so
//     browser back navigation stays clean.
//
// Layout: each ticker is a column with:
//   * Ticker + company name + sector chip
//   * CPS badge (color-coded by critical-point state)
//   * 5 shared-pattern rows (highlighted if matched)
//   * 30-day mini-timeline placeholder (we render the badge sequence as
//     a horizontal stripe — exact daily data lives in /api/timeline,
//     which is out of scope for W10-E; we synthesize a 30-cell strip
//     from the company's current CPS so the layout is honest about what
//     we have today.)
//   * 1-line narrative pulled from `company.tldr`
//
// Empty state: helpful copy + autocomplete picker.

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { fetchCompany, fetchScreener } from "@/lib/api";
import {
  CPS_BADGE,
  CPS_DOT,
  CPS_ICON,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
  DYNAMICS_SUBTITLE_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import type { Company, DynamicsFamily } from "@/lib/types";

const MAX_TICKERS = 5;
const MIN_TICKERS = 0; // empty is allowed (shows picker + empty state)

// 5 shared-pattern rows — the 5 most common universality patterns we
// visualize in the company grid. Each row highlights green when matched.
const PATTERN_ROWS: { id: DynamicsFamily; label: string; hint: string }[] = [
  { id: "soc_threshold_cascade", label: "临界级联", hint: DYNAMICS_SUBTITLE_ZH.soc_threshold_cascade },
  { id: "preferential_attachment", label: "强者愈强", hint: DYNAMICS_SUBTITLE_ZH.preferential_attachment },
  { id: "scheffer_fold", label: "临界翻转", hint: DYNAMICS_SUBTITLE_ZH.scheffer_fold },
  { id: "reflexive_fixed_point", label: "反身性循环", hint: DYNAMICS_SUBTITLE_ZH.reflexive_fixed_point },
  { id: "hysteresis_preisach", label: "回不去效应", hint: DYNAMICS_SUBTITLE_ZH.hysteresis_preisach },
];

function parseTickers(raw: string | null): string[] {
  if (!raw) return [];
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((t) => t.trim().toUpperCase())
        .filter((t) => t.length > 0 && t.length <= 10 && /^[A-Z0-9.-]+$/.test(t)),
    ),
  ).slice(0, MAX_TICKERS);
}

function cpsBadgeClass(state: string | undefined): string {
  if (!state) return "bg-zinc-100 text-zinc-700";
  // CPS_BADGE only contains color hints; fall back to amber if unknown.
  return (
    CPS_BADGE[state as keyof typeof CPS_BADGE] ??
    "bg-zinc-100 text-zinc-700 ring-zinc-200"
  );
}

function MiniTimelineStrip({ state }: { state: string | undefined }) {
  // 30-cell horizontal stripe. Today we paint all cells with the current
  // CPS color since per-day timeline data is not yet exposed in the
  // /screener payload. This is honest about the limitation but keeps
  // the visual slot reserved for when /timeline lands as a contract.
  const cells = Array.from({ length: 30 }, (_, i) => i);
  const cls = state
    ? CPS_DOT[state as keyof typeof CPS_DOT] ?? "bg-zinc-300"
    : "bg-zinc-200";
  return (
    <div className="flex h-2 w-full gap-[1px]" aria-label="30 天状态时间线（占位）">
      {cells.map((i) => (
        <div key={i} className={`h-full flex-1 rounded-[1px] ${cls}`} />
      ))}
    </div>
  );
}

function CompareColumn({ company }: { company: Company }) {
  const cps = company.critical_point_state;
  const family = company.dynamics_family;
  const sectorLabel = company.sector
    ? SECTOR_LABEL_ZH[company.sector] ?? company.sector
    : null;

  return (
    <article
      data-testid="compare-column"
      data-ticker={company.ticker}
      className="flex min-w-[240px] flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm"
    >
      <header className="space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <Link
            href={`/company/${encodeURIComponent(company.ticker)}`}
            className="text-base font-semibold text-zinc-900 hover:text-zinc-700"
          >
            {company.ticker}
          </Link>
          {sectorLabel && (
            <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[11px] text-zinc-600">
              {sectorLabel}
            </span>
          )}
        </div>
        <div className="text-xs text-zinc-500">{company.name}</div>
      </header>

      <div
        className={`inline-flex w-fit items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${cpsBadgeClass(
          cps,
        )}`}
        aria-label={`当前状态 ${CPS_LABEL_ZH[cps] ?? cps}`}
      >
        <span aria-hidden="true">{CPS_ICON[cps] ?? "·"}</span>
        <span>{CPS_LABEL_ZH[cps] ?? cps}</span>
      </div>

      {/* 5 shared-pattern rows: highlight match */}
      <div className="space-y-1">
        <div className="mb-1 text-[11px] uppercase tracking-wide text-zinc-400">
          普适模式
        </div>
        {PATTERN_ROWS.map((p) => {
          const matched = p.id === family;
          return (
            <div
              key={p.id}
              data-pattern-row={p.id}
              data-matched={matched ? "true" : "false"}
              className={`flex items-center gap-2 rounded px-2 py-1 text-xs ${
                matched
                  ? "bg-emerald-50 text-emerald-900 ring-1 ring-emerald-200"
                  : "text-zinc-500"
              }`}
            >
              <span
                aria-hidden="true"
                className={`inline-block h-1.5 w-1.5 rounded-full ${
                  matched ? "bg-emerald-600" : "bg-zinc-300"
                }`}
              />
              <span className="font-medium">{p.label}</span>
              {matched && (
                <span className="ml-auto text-[10px] text-emerald-700">命中</span>
              )}
            </div>
          );
        })}
      </div>

      {/* 30-day timeline */}
      <div className="space-y-1">
        <div className="text-[11px] uppercase tracking-wide text-zinc-400">
          近 30 日状态
        </div>
        <MiniTimelineStrip state={cps} />
      </div>

      {/* TL;DR narrative */}
      {company.tldr && (
        <p className="line-clamp-3 text-xs leading-relaxed text-zinc-600">
          {company.tldr}
        </p>
      )}

      <div className="mt-auto text-[11px] text-zinc-400">
        动力学：{DYNAMICS_LABEL_ZH[family] ?? family}
      </div>
    </article>
  );
}

function TickerPicker({
  current,
  onAdd,
}: {
  current: string[];
  onAdd: (t: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [pool, setPool] = useState<Company[]>([]);
  const [loading, setLoading] = useState(false);

  // Lazy-load company list once on first focus.
  const ensurePool = useCallback(async () => {
    if (pool.length > 0 || loading) return;
    setLoading(true);
    try {
      const list = await fetchScreener({ limit: 200 });
      setPool(list);
    } catch {
      setPool([]);
    } finally {
      setLoading(false);
    }
  }, [pool.length, loading]);

  const matches = useMemo(() => {
    const q = query.trim().toUpperCase();
    if (!q) return [] as Company[];
    return pool
      .filter(
        (c) =>
          (c.ticker.toUpperCase().includes(q) ||
            c.name.toUpperCase().includes(q)) &&
          !current.includes(c.ticker.toUpperCase()),
      )
      .slice(0, 8);
  }, [query, pool, current]);

  const atLimit = current.length >= MAX_TICKERS;

  return (
    <div className="relative w-full max-w-md">
      <input
        type="text"
        value={query}
        disabled={atLimit}
        onFocus={ensurePool}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={
          atLimit ? `已达 ${MAX_TICKERS} 个上限` : "添加 ticker（例如 AAPL）"
        }
        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 disabled:bg-zinc-50 disabled:text-zinc-400"
        data-testid="compare-picker-input"
      />
      {matches.length > 0 && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 top-full z-10 mt-1 max-h-64 overflow-y-auto rounded-md border border-zinc-200 bg-white shadow-lg"
        >
          {matches.map((c) => (
            <li key={c.ticker}>
              <button
                type="button"
                onClick={() => {
                  onAdd(c.ticker.toUpperCase());
                  setQuery("");
                }}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-zinc-50"
              >
                <span className="font-medium text-zinc-900">{c.ticker}</span>
                <span className="truncate text-xs text-zinc-500">{c.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CompareInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raw = searchParams.get("tickers");
  const tickers = useMemo(() => parseTickers(raw), [raw]);

  const [companies, setCompanies] = useState<Company[]>([]);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    if (tickers.length === 0) {
      setCompanies([]);
      setErrors({});
      return;
    }
    setLoading(true);
    Promise.all(
      tickers.map(async (t) => {
        try {
          const c = await fetchCompany(t);
          return { ok: true as const, t, c };
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : "fetch failed";
          return { ok: false as const, t, err: msg };
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      const ok: Company[] = [];
      const errs: Record<string, string> = {};
      for (const r of results) {
        if (r.ok) ok.push(r.c);
        else errs[r.t] = r.err;
      }
      setCompanies(ok);
      setErrors(errs);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [tickers.join(",")]);

  const updateTickers = useCallback(
    (next: string[]) => {
      const clean = Array.from(new Set(next.map((t) => t.toUpperCase())))
        .filter((t) => t)
        .slice(0, MAX_TICKERS);
      const qs = clean.length > 0 ? `?tickers=${clean.join(",")}` : "";
      router.replace(`/compare${qs}`);
    },
    [router],
  );

  const addTicker = useCallback(
    (t: string) => updateTickers([...tickers, t]),
    [tickers, updateTickers],
  );

  const removeTicker = useCallback(
    (t: string) => updateTickers(tickers.filter((x) => x !== t)),
    [tickers, updateTickers],
  );

  const hasTickers = tickers.length >= 1;

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-zinc-900">公司对比</h1>
        <p className="max-w-3xl text-sm text-zinc-600">
          一行排开 2-5 家公司，并排看它们的当前状态、命中的普适模式、近 30 日轨迹。
          可以从地址栏拷贝分享。
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3 rounded-md border border-zinc-200 bg-white p-4">
        <TickerPicker current={tickers} onAdd={addTicker} />
        {hasTickers && (
          <div className="flex flex-wrap items-center gap-2">
            {tickers.map((t) => (
              <span
                key={t}
                className="inline-flex items-center gap-1 rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-800"
                data-testid="compare-chip"
              >
                {t}
                <button
                  type="button"
                  aria-label={`移除 ${t}`}
                  onClick={() => removeTicker(t)}
                  className="ml-1 text-zinc-500 hover:text-zinc-900"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
      </div>

      {!hasTickers && (
        <div
          data-testid="compare-empty-state"
          className="rounded-lg border border-dashed border-zinc-300 bg-white p-10 text-center"
        >
          <p className="text-sm text-zinc-500">
            添加 ticker 即可并排对比公司的结构状态。
          </p>
          <p className="mt-2 text-xs text-zinc-400">
            URL 示例：<code className="rounded bg-zinc-100 px-1.5 py-0.5">/compare?tickers=AAPL,TSLA,JPM</code>
          </p>
        </div>
      )}

      {hasTickers && loading && (
        <div className="text-sm text-zinc-500">加载中…</div>
      )}

      {hasTickers && !loading && Object.keys(errors).length > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
          {Object.entries(errors).map(([t, e]) => (
            <div key={t}>
              <strong>{t}</strong>：{e}
            </div>
          ))}
        </div>
      )}

      {hasTickers && companies.length > 0 && (
        <div
          data-testid="compare-grid"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5"
        >
          {companies.map((c) => (
            <CompareColumn key={c.ticker} company={c} />
          ))}
        </div>
      )}

      <footer className="border-t border-zinc-200 pt-4 text-xs text-zinc-500">
        看完了？{" "}
        <Link href="/universality" className="text-zinc-900 underline hover:text-zinc-700">
          浏览全部普适类
        </Link>{" "}
        或返回{" "}
        <Link href="/" className="text-zinc-900 underline hover:text-zinc-700">
          公司表
        </Link>
        。
      </footer>
    </div>
  );
}

export default function ComparePage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-semibold text-zinc-900">公司对比</h1>
          </header>
          <div className="text-sm text-zinc-500">加载中…</div>
        </div>
      }
    >
      <CompareInner />
    </Suspense>
  );
}
