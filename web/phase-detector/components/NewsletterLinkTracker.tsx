"use client";

// W10-D: track outbound newsletter link clicks via Plausible.
// Hangs a single delegated listener on the article element rather than per-<a>.
//
// Pairs with PageOpenTracker (W8-D) for `newsletter_archive_view` mount event.

import { useEffect } from "react";
import { trackEvent } from "@/lib/analytics";

interface Props {
  issueNumber: string;
}

export function NewsletterLinkTracker({ issueNumber }: Props) {
  // Note: React 18 strict mode mounts effects twice; cleanup-then-re-add is
  // the standard pattern. We don't gate with a ref because the cleanup
  // function removes the listener cleanly between mounts.
  useEffect(() => {
    const handler = (e: Event) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const a = target.closest("a") as HTMLAnchorElement | null;
      if (!a) return;
      if (!a.href) return;
      // Only outbound links (different origin) are interesting for the
      // analytics question we care about ("which CTAs do readers click?").
      let isOutbound = false;
      try {
        const dest = new URL(a.href, window.location.href);
        isOutbound = dest.origin !== window.location.origin;
      } catch {
        return;
      }
      if (!isOutbound) return;
      trackEvent("newsletter_link_click", {
        issue: issueNumber,
        url: a.href,
      });
    };

    document.addEventListener("click", handler, { capture: true });
    return () =>
      document.removeEventListener("click", handler, { capture: true });
  }, [issueNumber]);

  return null;
}
