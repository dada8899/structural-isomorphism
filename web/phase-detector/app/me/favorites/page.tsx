"use client";

// W15-C: /me/favorites — list of bookmarked companies for the current user.
//
// Behaviour:
//  - Hydrates from GET /api/favorites on mount (or localStorage if anon)
//  - Each ticker is hydrated with full Company shape via /api/company/{t}
//    so we can show current_phase + flip date
//  - "Remove all" button with a confirm dialog
//  - Empty state with a CTA to /companies
//  - FavoriteButton in each card removes the entry from the page
//    immediately via onToggle

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import { Events, trackEvent } from "@/lib/analytics";
import { fetchCompany } from "@/lib/api";
import {
  clearAnonFavorites,
  fetchFavorites,
  isSignedIn,
  removeFavorite,
} from "@/lib/favorites";
import {
  CPS_BADGE,
  CPS_ICON,
  CPS_LABEL_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import type { Company } from "@/lib/types";

interface RowState {
  ticker: string;
  /** null = loading; undefined = fetch failed (we still show the row). */
  company: Company | null | undefined;
}

export default function FavoritesPage() {
  const [rows, setRows] = useState<RowState[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  // Initial hydrate.
  useEffect(() => {
    let cancelled = false;
    setSignedIn(isSignedIn());

    (async () => {
      setLoading(true);
      try {
        const tickers = await fetchFavorites();
        if (cancelled) return;
        if (tickers.length === 0) {
          setRows([]);
          setLoading(false);
          return;
        }
        // Render the rows first as "loading" so the layout doesn't jump,
        // then hydrate each with company details in parallel.
        const seeded: RowState[] = tickers.map((t) => ({
          ticker: t,
          company: null,
        }));
        setRows(seeded);
        setLoading(false);

        await Promise.allSettled(
          tickers.map(async (t, idx) => {
            try {
              const c = await fetchCompany(t);
              if (cancelled) return;
              setRows((prev) => {
                const next = [...prev];
                if (next[idx]) {
                  next[idx] = { ticker: t, company: c };
                }
                return next;
              });
            } catch {
              if (cancelled) return;
              setRows((prev) => {
                const next = [...prev];
                if (next[idx]) {
                  next[idx] = { ticker: t, company: undefined };
                }
                return next;
              });
            }
          }),
        );
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "加载失败");
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleRemoveAll = useCallback(async () => {
    setConfirmClear(false);
    const tickers = rows.map((r) => r.ticker);
    if (signedIn) {
      for (const t of tickers) {
        try {
          await removeFavorite(t);
          trackEvent(Events.FavoriteRemoved, {
            ticker: t,
            source: "favorites_page_bulk",
          });
        } catch {
          // continue on error so a single failure doesn't strand others
        }
      }
    } else {
      clearAnonFavorites();
    }
    setRows([]);
  }, [rows, signedIn]);

  // ---------------- empty state ----------------
  if (!loading && rows.length === 0) {
    return (
      <section className="mx-auto max-w-3xl px-4 py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
          我的收藏
        </h1>
        <div
          className="mt-8 rounded-xl border border-dashed border-zinc-300 bg-white p-10 text-center"
          data-testid="favorites-empty"
        >
          <p className="text-base text-zinc-600">还没有收藏任何公司</p>
          <p className="mt-1 text-sm text-zinc-500">
            在公司卡片或详情页点击星标即可加入收藏。
          </p>
          <Link
            href="/companies"
            className="mt-6 inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            浏览公司
          </Link>
        </div>
        {!signedIn && (
          <p className="mt-4 text-center text-xs text-zinc-500">
            登录后可在多设备间同步收藏。
          </p>
        )}
      </section>
    );
  }

  // ---------------- list state ----------------
  return (
    <section
      className="mx-auto max-w-5xl px-4 py-10"
      data-testid="favorites-page"
    >
      <header className="mb-6 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
            我的收藏
          </h1>
          <p className="mt-1 text-sm text-zinc-500" data-testid="favorites-count">
            共 {rows.length} 家公司
          </p>
        </div>
        <button
          type="button"
          onClick={() => setConfirmClear(true)}
          disabled={loading || rows.length === 0}
          data-testid="favorites-remove-all"
          className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
        >
          清空收藏
        </button>
      </header>

      {error && (
        <div
          className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
          role="alert"
        >
          {error}
        </div>
      )}

      {confirmClear && (
        <div
          role="alertdialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
        >
          <div className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl">
            <h2 className="text-base font-semibold text-zinc-900">
              清空全部收藏？
            </h2>
            <p className="mt-1 text-sm text-zinc-600">
              此操作不可撤销。是否继续？
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmClear(false)}
                className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-700 hover:bg-zinc-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleRemoveAll}
                data-testid="favorites-confirm-remove-all"
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              >
                确认清空
              </button>
            </div>
          </div>
        </div>
      )}

      <ul
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
        data-testid="favorites-grid"
      >
        {rows.map((row) => (
          <li key={row.ticker}>
            <FavoriteCard
              ticker={row.ticker}
              company={row.company}
              onRemoved={() => {
                setRows((prev) => prev.filter((r) => r.ticker !== row.ticker));
              }}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface FavoriteCardProps {
  ticker: string;
  company: Company | null | undefined;
  onRemoved: () => void;
}

function FavoriteCard({ ticker, company, onRemoved }: FavoriteCardProps) {
  // Loading state — skeleton.
  if (company === null) {
    return (
      <div
        className="flex h-32 animate-pulse flex-col rounded-lg border border-zinc-200 bg-white p-4"
        data-testid={`favorite-card-loading-${ticker}`}
      >
        <div className="h-5 w-20 rounded bg-zinc-200" />
        <div className="mt-2 h-3 w-32 rounded bg-zinc-200" />
        <div className="mt-auto h-6 w-24 rounded bg-zinc-200" />
      </div>
    );
  }

  // Fetch failed — still render with ticker only.
  if (company === undefined) {
    return (
      <div
        className="flex flex-col gap-2 rounded-lg border border-zinc-200 bg-white p-4"
        data-testid={`favorite-card-${ticker}`}
      >
        <div className="flex items-start justify-between">
          <Link
            href={`/company/${encodeURIComponent(ticker)}`}
            className="font-semibold text-zinc-900"
          >
            {ticker}
          </Link>
          <FavoriteButton
            ticker={ticker}
            source="favorites_page"
            initialFavorited
            onToggle={(next) => {
              if (!next) onRemoved();
            }}
          />
        </div>
        <p className="text-xs text-zinc-500">公司详情加载失败</p>
      </div>
    );
  }

  const cps = company.critical_point_state;
  const sectorLabel = company.sector
    ? SECTOR_LABEL_ZH[company.sector] ?? company.sector
    : null;
  const flipDate = company.extracted_at
    ? new Date(company.extracted_at).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
    : null;

  return (
    <article
      data-testid={`favorite-card-${ticker}`}
      className="flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 transition-colors hover:border-blue-300 hover:bg-zinc-50"
    >
      <header className="flex items-start justify-between gap-2">
        <Link
          href={`/company/${encodeURIComponent(company.ticker)}`}
          className="min-w-0 flex-1"
        >
          <div className="truncate font-semibold text-zinc-900">
            {company.ticker}
          </div>
          <div className="truncate text-xs text-zinc-500">{company.name}</div>
        </Link>
        <FavoriteButton
          ticker={company.ticker}
          source="favorites_page"
          initialFavorited
          onToggle={(next) => {
            if (!next) onRemoved();
          }}
        />
      </header>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${
            CPS_BADGE[cps] ?? "bg-zinc-400 text-white"
          }`}
        >
          <span aria-hidden="true">{CPS_ICON[cps] ?? "?"}</span>
          <span>{CPS_LABEL_ZH[cps] ?? cps}</span>
        </span>
        {sectorLabel && (
          <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-zinc-600">
            {sectorLabel}
          </span>
        )}
      </div>

      {flipDate && (
        <div className="text-xs text-zinc-500">
          最近评估:{" "}
          <time dateTime={company.extracted_at ?? undefined}>{flipDate}</time>
        </div>
      )}
    </article>
  );
}
