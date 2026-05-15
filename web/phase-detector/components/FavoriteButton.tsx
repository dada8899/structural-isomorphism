"use client";

// W15-C: Star button used on company card, detail page, and /compare columns.
//
// Behaviour:
//  - Filled star = favorited, outline = not favorited
//  - Click toggles state
//  - Anonymous users: store in localStorage (`phase_favorites_anon`)
//    + small prompt directs them to sign in to sync
//  - Optimistic update + rollback on server failure
//  - Plausible events: favorite_added / favorite_removed / favorite_cap_exceeded
//  - Stops propagation: the star sits inside CompanyCard's stretched-link
//    overlay; we don't want clicking it to navigate to the detail page.

import { useCallback, useEffect, useState } from "react";
import { Events, trackEvent } from "@/lib/analytics";
import {
  addFavorite,
  fetchFavorites,
  isSignedIn,
  removeFavorite,
} from "@/lib/favorites";

interface Props {
  ticker: string;
  /** Where the button lives, for analytics props. */
  source: "card" | "detail" | "compare" | "favorites_page";
  /** Optional initial state for SSR/SSR-flicker avoidance (e.g. when
   *  parent already knows from a hydrated list). Defaults to false. */
  initialFavorited?: boolean;
  /** Optional ARIA label override. */
  ariaLabel?: string;
  /** Optional className passthrough. */
  className?: string;
  /** Fired after a successful toggle (used by /me/favorites to remove
   *  the card from the rendered grid). */
  onToggle?: (next: boolean) => void;
}

export function FavoriteButton({
  ticker,
  source,
  initialFavorited = false,
  ariaLabel,
  className,
  onToggle,
}: Props) {
  const [favorited, setFavorited] = useState<boolean>(initialFavorited);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [signedIn, setSignedIn] = useState(false);

  // Hydrate from server (or localStorage if anon) on mount.
  useEffect(() => {
    let cancelled = false;
    setSignedIn(isSignedIn());
    fetchFavorites()
      .then((list) => {
        if (cancelled) return;
        const has = list
          .map((t) => t.toUpperCase())
          .includes(ticker.toUpperCase());
        setFavorited(has);
      })
      .catch(() => {
        // Network failed — leave initial state.
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const handleClick = useCallback(
    async (e: React.MouseEvent<HTMLButtonElement>) => {
      e.preventDefault();
      e.stopPropagation();
      if (busy) return;
      setBusy(true);
      setError(null);
      const previous = favorited;
      const next = !previous;
      // Optimistic update.
      setFavorited(next);
      try {
        if (next) {
          await addFavorite(ticker);
          trackEvent(Events.FavoriteAdded, { ticker, source });
        } else {
          await removeFavorite(ticker);
          trackEvent(Events.FavoriteRemoved, { ticker, source });
        }
        onToggle?.(next);
      } catch (err) {
        // Rollback.
        setFavorited(previous);
        if (err instanceof Error && err.message === "FAVORITES_CAP_EXCEEDED") {
          setError("已达收藏上限,升级后可继续");
          trackEvent(Events.FavoriteCapExceeded, { ticker, source });
        } else {
          setError("操作失败,请稍后再试");
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, favorited, ticker, source, onToggle],
  );

  const label =
    ariaLabel ??
    (favorited ? `取消收藏 ${ticker}` : `收藏 ${ticker}`);

  return (
    <div className={"relative z-10 inline-flex flex-col items-end " + (className ?? "")}>
      <button
        type="button"
        onClick={handleClick}
        aria-pressed={favorited}
        aria-label={label}
        disabled={busy}
        data-testid={`favorite-button-${ticker}`}
        className={
          "inline-flex h-9 w-9 items-center justify-center rounded-full transition-colors " +
          (favorited
            ? "bg-amber-50 text-amber-600 hover:bg-amber-100 dark:bg-amber-900/30 dark:text-amber-300"
            : "bg-zinc-50 text-zinc-400 hover:bg-zinc-100 hover:text-amber-600 dark:bg-zinc-800/50 dark:text-zinc-500") +
          " focus:outline-none focus:ring-2 focus:ring-amber-500 focus:ring-offset-1 disabled:opacity-50"
        }
      >
        {/* Star SVG: filled vs outline */}
        {favorited ? (
          <svg
            viewBox="0 0 20 20"
            fill="currentColor"
            aria-hidden="true"
            className="h-5 w-5"
          >
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.957a1 1 0 00.95.69h4.162c.969 0 1.371 1.24.588 1.81l-3.367 2.446a1 1 0 00-.364 1.118l1.287 3.957c.3.922-.755 1.688-1.54 1.118l-3.366-2.446a1 1 0 00-1.176 0l-3.367 2.446c-.784.57-1.838-.196-1.539-1.118l1.287-3.957a1 1 0 00-.364-1.118L2.05 9.384c-.783-.57-.38-1.81.588-1.81h4.162a1 1 0 00.95-.69l1.286-3.957z" />
          </svg>
        ) : (
          <svg
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.6}
            aria-hidden="true"
            className="h-5 w-5"
          >
            <path
              strokeLinejoin="round"
              d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.286 3.957a1 1 0 00.95.69h4.162c.969 0 1.371 1.24.588 1.81l-3.367 2.446a1 1 0 00-.364 1.118l1.287 3.957c.3.922-.755 1.688-1.54 1.118l-3.366-2.446a1 1 0 00-1.176 0l-3.367 2.446c-.784.57-1.838-.196-1.539-1.118l1.287-3.957a1 1 0 00-.364-1.118L2.05 9.384c-.783-.57-.38-1.81.588-1.81h4.162a1 1 0 00.95-.69l1.286-3.957z"
            />
          </svg>
        )}
      </button>
      {/* Anonymous hint: shown next to the star when user hasn't signed in
          and just added their first local favorite. */}
      {!signedIn && favorited && (
        <span
          className="mt-1 max-w-[160px] text-right text-[10px] leading-tight text-zinc-500"
          role="status"
        >
          已存到本地。登录后将自动同步。
        </span>
      )}
      {error && (
        <span
          className="mt-1 max-w-[160px] text-right text-[10px] leading-tight text-rose-600"
          role="alert"
        >
          {error}
        </span>
      )}
    </div>
  );
}

export default FavoriteButton;
