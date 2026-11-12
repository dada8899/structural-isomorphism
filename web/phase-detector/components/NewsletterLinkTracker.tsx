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

function coarseDestination(url: URL): string {
  const host = url.hostname.toLowerCase();
  if (host === "github.com" || host.endsWith(".github.com")) return "code_host";
  if (host === "arxiv.org" || host.endsWith(".arxiv.org")) return "research_archive";
  if (host === "sec.gov" || host.endsWith(".sec.gov")) return "regulator";
  return url.protocol === "https:" ? "external_https" : "external_other";
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
      let dest: URL;
      try {
        dest = new URL(a.href, window.location.href);
      } catch {
        return;
      }
      if (dest.origin === window.location.origin) return;
      trackEvent("newsletter_link_click", {
        issue: issueNumber,
        destination: coarseDestination(dest),
      });
    };

    document.addEventListener("click", handler, { capture: true });
    return () =>
      document.removeEventListener("click", handler, { capture: true });
  }, [issueNumber]);

  return null;
}
