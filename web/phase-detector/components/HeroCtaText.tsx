// W15-E: A/B experiment "hero_cta_text_v2" — client island that renders
// the experimental CTA text and fires the `experiment_exposed` event.
//
// SSR-safe: defaults to the control text during server render and before
// /api/flags resolves, hydrates with the assigned variant.

"use client";

import { useVariantValue } from "@/lib/flags";

interface Props {
  /** Default text to render during SSR + before flags resolve. */
  fallback?: string;
}

export function HeroCtaText({ fallback = "Browse signals" }: Props) {
  useVariantValue("hero_cta_text_v2", fallback);
  // Historical flag payloads included live-data wording, which is false for
  // this frozen subproduct. Keep exposure measurement while constraining the
  // user-visible promise to the published research boundary.
  return <>Browse frozen snapshots</>;
}
