"use client";

// W12-C (session #10): touch-swipe hook using PointerEvent.
//
// Why PointerEvent (not TouchEvent / Hammer.js):
//   - PointerEvent is the unified web spec for touch / mouse / pen.
//   - Hammer.js (~7kb gz) is overkill for left/right/up/down swipes.
//   - TouchEvent is iOS-specific and conflicts with mouse-drag testing.
//
// Threshold defaults follow Apple HIG (44pt) + a velocity floor so a slow
// careful drag doesn't count as a "swipe". Tunable via opts.
//
// Cancellable: returning true from a handler does NOT preventDefault — the
// caller decides whether the browser should still scroll (we usually want
// vertical scroll to keep working, so we only preventDefault on confirmed
// horizontal swipe).

import { useEffect, useRef } from "react";

export interface SwipeOpts {
  /** Min px distance to count as a swipe. Default 50. */
  threshold?: number;
  /** Max ms between pointerdown→pointerup. Default 600. */
  maxDurationMs?: number;
  /** Min |dx/dt| px/ms required. Default 0.2. */
  minVelocity?: number;
  /** Called on horizontal swipe. */
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  /** Called on vertical swipe. */
  onSwipeUp?: () => void;
  onSwipeDown?: () => void;
  /** If true (default), preventDefault on confirmed horizontal swipe to
   *  stop the browser from also firing a click. */
  preventDefaultOnHorizontal?: boolean;
}

/**
 * Attach swipe handlers to a ref'd element.
 *
 * Usage:
 *   const ref = useRef<HTMLDivElement>(null);
 *   useSwipe(ref, {
 *     onSwipeLeft: () => router.push(nextTicker),
 *     onSwipeRight: () => router.push(prevTicker),
 *   });
 *   return <div ref={ref}>…</div>;
 */
export function useSwipe<T extends HTMLElement>(
  ref: React.RefObject<T | null>,
  opts: SwipeOpts,
): void {
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const threshold = opts.threshold ?? 50;
    const maxDurationMs = opts.maxDurationMs ?? 600;
    const minVelocity = opts.minVelocity ?? 0.2;
    const preventDefaultOnHorizontal = opts.preventDefaultOnHorizontal ?? true;

    let startX = 0;
    let startY = 0;
    let startT = 0;
    let active = false;

    const onPointerDown = (e: PointerEvent) => {
      // Only track primary touches/clicks. Mouse middle/right or multi-finger
      // gestures get ignored (browser handles pinch/zoom natively).
      if (e.pointerType === "mouse" && e.button !== 0) return;
      startX = e.clientX;
      startY = e.clientY;
      startT = Date.now();
      active = true;
    };

    const onPointerUp = (e: PointerEvent) => {
      if (!active) return;
      active = false;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      const dt = Date.now() - startT;
      if (dt > maxDurationMs) return;
      const absDx = Math.abs(dx);
      const absDy = Math.abs(dy);
      const velocity = Math.max(absDx, absDy) / Math.max(dt, 1);
      if (velocity < minVelocity) return;

      const o = optsRef.current;
      // Horizontal swipe wins if dx dominates AND clears threshold.
      if (absDx > absDy && absDx >= threshold) {
        if (preventDefaultOnHorizontal) e.preventDefault();
        if (dx < 0) o.onSwipeLeft?.();
        else o.onSwipeRight?.();
      } else if (absDy > absDx && absDy >= threshold) {
        if (dy < 0) o.onSwipeUp?.();
        else o.onSwipeDown?.();
      }
    };

    const onPointerCancel = () => {
      active = false;
    };

    // passive: false on pointerup so preventDefault() works.
    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointerup", onPointerUp, { passive: false });
    el.addEventListener("pointercancel", onPointerCancel);

    return () => {
      el.removeEventListener("pointerdown", onPointerDown);
      el.removeEventListener("pointerup", onPointerUp);
      el.removeEventListener("pointercancel", onPointerCancel);
    };
    // re-bind only if these scalar opts change; handler funcs are pulled
    // off optsRef so we don't churn listeners on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    ref,
    opts.threshold,
    opts.maxDurationMs,
    opts.minVelocity,
    opts.preventDefaultOnHorizontal,
  ]);
}

/**
 * Pull-to-refresh hook. Triggers `onRefresh` when the user drags down from
 * the very top of the page by at least `threshold` px.
 *
 * Uses `window.scrollY === 0` as the precondition, so it only fires when
 * we're truly at the top — won't interfere with mid-page scroll.
 */
export interface PullToRefreshOpts {
  /** Min drag distance to trigger. Default 80. */
  threshold?: number;
  /** Called when pull-to-refresh fires. Should return a promise. */
  onRefresh: () => void | Promise<void>;
  /** Disable PTR (e.g. while a refresh is already in flight). */
  disabled?: boolean;
}

export function usePullToRefresh(opts: PullToRefreshOpts): {
  isPulling: boolean;
  pullDistance: number;
} {
  const stateRef = useRef({ isPulling: false, pullDistance: 0 });
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    if (typeof window === "undefined") return;
    const threshold = opts.threshold ?? 80;
    let startY = 0;
    let pulling = false;

    const onTouchStart = (e: TouchEvent) => {
      if (optsRef.current.disabled) return;
      if (window.scrollY > 0) return;
      startY = e.touches[0].clientY;
      pulling = true;
    };

    const onTouchMove = (e: TouchEvent) => {
      if (!pulling) return;
      const dy = e.touches[0].clientY - startY;
      if (dy < 0) {
        pulling = false;
        return;
      }
      stateRef.current.pullDistance = dy;
    };

    const onTouchEnd = () => {
      if (!pulling) return;
      pulling = false;
      const dy = stateRef.current.pullDistance;
      stateRef.current.pullDistance = 0;
      if (dy >= threshold && !optsRef.current.disabled) {
        void optsRef.current.onRefresh();
      }
    };

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [opts.threshold, opts.disabled]);

  return stateRef.current;
}
