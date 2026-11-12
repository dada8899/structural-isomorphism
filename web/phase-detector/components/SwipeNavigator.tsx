"use client";

// W12-C (session #10): touch-swipe navigation between sibling tickers.
//
// Renders an invisible <div> that captures left/right swipes on the
// /company/[ticker] page and pushes the next / previous ticker via
// next/router. List is fetched once on mount from /screener and cached
// in module-scope so subsequent mounts are instant.

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchScreener } from "@/lib/api";
import { useSwipe } from "@/lib/useSwipe";

let cachedTickers: string[] | null = null;

interface Props {
  currentTicker: string;
  children: React.ReactNode;
}

export default function SwipeNavigator({ currentTicker, children }: Props) {
  const router = useRouter();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [tickers, setTickers] = useState<string[]>(cachedTickers ?? []);

  // Fetch tickers once across the app lifetime; cheap fallback.
  useEffect(() => {
    if (cachedTickers) return;
    let cancelled = false;
    fetchScreener({})
      .then((rows) => {
        if (cancelled) return;
        const list = rows.map((r) => r.ticker).filter(Boolean);
        cachedTickers = list;
        setTickers(list);
      })
      .catch(() => {
        /* swipe just no-ops if list unavailable */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const { prev, next } = useMemo(() => {
    if (!tickers.length) return { prev: null as string | null, next: null as string | null };
    const i = tickers.indexOf(currentTicker);
    if (i < 0) return { prev: null, next: null };
    return {
      prev: i > 0 ? tickers[i - 1] : null,
      next: i < tickers.length - 1 ? tickers[i + 1] : null,
    };
  }, [tickers, currentTicker]);

  useSwipe(wrapRef, {
    threshold: 60,
    onSwipeLeft: () => {
      if (next) router.push(`/company/${encodeURIComponent(next)}`);
    },
    onSwipeRight: () => {
      if (prev) router.push(`/company/${encodeURIComponent(prev)}`);
    },
  });

  return (
    <div ref={wrapRef} data-testid="swipe-navigator">
      {children}
      {/* Visual affordance — bottom hint on mobile only. */}
      {(prev || next) && (
        <div
          className="mt-6 flex items-center justify-between text-xs text-zinc-400 sm:hidden"
          aria-hidden="true"
        >
          <span>{prev ? `← ${prev}` : ""}</span>
          <span className="text-[10px] uppercase tracking-widest">滑动切换</span>
          <span>{next ? `${next} →` : ""}</span>
        </div>
      )}
    </div>
  );
}
