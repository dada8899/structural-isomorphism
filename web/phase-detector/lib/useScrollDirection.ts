"use client";

// W12-C (session #10): rAF-throttled scroll-direction detector.
// Used by sticky headers: hide when scrolling down past N px, reveal on up.
// Mobile native pattern (iOS Safari toolbar, Twitter/X header).

import { useEffect, useState } from "react";

export type ScrollDirection = "up" | "down";

export function useScrollDirection(options?: {
  /** Px from top before we start hiding. Default 64. */
  threshold?: number;
}): ScrollDirection {
  const [dir, setDir] = useState<ScrollDirection>("up");

  useEffect(() => {
    if (typeof window === "undefined") return;
    const threshold = options?.threshold ?? 64;
    let lastY = window.scrollY;
    let ticking = false;

    const update = () => {
      const y = window.scrollY;
      if (Math.abs(y - lastY) < 6) {
        ticking = false;
        return;
      }
      if (y < threshold) {
        setDir("up");
      } else {
        setDir(y > lastY ? "down" : "up");
      }
      lastY = y;
      ticking = false;
    };

    const onScroll = () => {
      if (!ticking) {
        window.requestAnimationFrame(update);
        ticking = true;
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [options?.threshold]);

  return dir;
}
