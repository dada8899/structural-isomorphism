import type { MetadataRoute } from "next";
import { ISSUES } from "@/lib/newsletter-data";
import {
  PHASE_DETECTOR_TICKERS,
  PHASE_DETECTOR_UNIVERSALITY_CLASSES,
} from "@/lib/sitemap-data";

// W3-D (2026-05-14): static sitemap for the Phase Detector product.
// W10-D (2026-05-15): added newsletter archive entries.
// W12-B (2026-05-15): expanded to include /companies, /compare, /pricing,
//   /universality + per-class detail pages, /company/[ticker] for all
//   100 tracked tickers. Total ≈ 130 URLs covering every routable page
//   in the app.
//
// Edit `lib/sitemap-data.ts` to add/remove tickers + classes. When the
// universe stabilizes we'll switch to fetching from /api/companies +
// /api/universality/classes at build time.
export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://phase.bytedance.city";
  const lastModified = new Date();

  const staticEntries: MetadataRoute.Sitemap = [
    {
      url: `${base}/`,
      lastModified,
      changeFrequency: "weekly",
      priority: 1.0,
    },
    {
      url: `${base}/companies`,
      lastModified,
      changeFrequency: "daily",
      priority: 0.95,
    },
    {
      url: `${base}/compare`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.7,
    },
    {
      url: `${base}/universality`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.85,
    },
    {
      url: `${base}/methodology`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.9,
    },
    {
      url: `${base}/backtest`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.9,
    },
    {
      url: `${base}/about`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.7,
    },
    {
      url: `${base}/pricing`,
      lastModified,
      changeFrequency: "monthly",
      priority: 0.75,
    },
  ];

  const tickerEntries: MetadataRoute.Sitemap = PHASE_DETECTOR_TICKERS.map(
    (ticker) => ({
      url: `${base}/company/${ticker}`,
      lastModified,
      changeFrequency: "daily" as const,
      priority: 0.6,
    }),
  );

  const classEntries: MetadataRoute.Sitemap =
    PHASE_DETECTOR_UNIVERSALITY_CLASSES.map((classId) => ({
      url: `${base}/universality/${classId}`,
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.65,
    }));

  const newsletterEntries: MetadataRoute.Sitemap = [
    {
      url: `${base}/newsletter`,
      lastModified,
      changeFrequency: "weekly",
      priority: 0.8,
    },
    ...ISSUES.map((i) => ({
      url: `${base}/newsletter/${i.slug}`,
      lastModified: new Date(i.publishedOn),
      changeFrequency: "yearly" as const,
      priority: 0.6,
    })),
  ];

  return [
    ...staticEntries,
    ...tickerEntries,
    ...classEntries,
    ...newsletterEntries,
  ];
}
