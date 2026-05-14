"use client";

// W12-E: NetworkBanner + service-worker bootstrap (combined to avoid
// adding another always-mounted client component to the layout).
//
// • Registers /sw.js on mount (best-effort; failure is non-fatal).
// • Listens to window 'online'/'offline' events.
// • Shows a tiny dismissable banner when offline.
// • Flushes queued error reports when coming back online.

import { useEffect, useState } from "react";

import { flushErrorQueue } from "@/lib/error-reporter";

export default function NetworkBanner() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    // 1. Register service worker (production-only by default; dev SW often
    //    misbehaves with HMR — opt in via NEXT_PUBLIC_PHASE_SW_DEV=1).
    if (typeof navigator !== "undefined" && "serviceWorker" in navigator) {
      const allowDev = process.env.NEXT_PUBLIC_PHASE_SW_DEV === "1";
      if (process.env.NODE_ENV === "production" || allowDev) {
        navigator.serviceWorker.register("/sw.js").catch((err) => {
          // eslint-disable-next-line no-console
          console.warn("[phase-detector] SW registration failed:", err);
        });
      }
    }

    // 2. Online/offline listeners.
    const setOnline = () => {
      setOffline(false);
      // Best-effort flush of queued reports.
      flushErrorQueue().catch(() => undefined);
    };
    const setOff = () => setOffline(true);

    if (typeof window !== "undefined") {
      setOffline(navigator.onLine === false);
      window.addEventListener("online", setOnline);
      window.addEventListener("offline", setOff);
    }

    return () => {
      if (typeof window === "undefined") return;
      window.removeEventListener("online", setOnline);
      window.removeEventListener("offline", setOff);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      data-testid="network-banner"
      className="fixed left-1/2 top-2 z-[120] -translate-x-1/2 rounded-full border border-amber-300 bg-amber-50 px-4 py-1.5 text-xs font-medium text-amber-800 shadow-sm"
    >
      <span className="mr-2 inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden="true" />
      Offline mode — showing cached data
      <button
        type="button"
        onClick={() => {
          if (typeof window !== "undefined") window.location.reload();
        }}
        className="ml-3 underline-offset-2 hover:underline"
      >
        Retry
      </button>
    </div>
  );
}
