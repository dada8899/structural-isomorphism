import type { MetadataRoute } from "next";
import { ISSUES } from "@/lib/newsletter-data";

// W3-D (2026-05-14): static sitemap for the Phase Detector product.
// Company-specific pages (/company/[ticker]) are not enumerated here yet —
// when the universe stabilizes we can shift to a dynamic sitemap that reads
// app/api/companies/route.ts.
//
// W10-D (2026-05-15): added newsletter archive (/newsletter) and per-issue
// pages from lib/newsletter-data.ts.
export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://phase.bytedance.city";
  const lastModified = new Date();

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
    {
      url: `${base}/`,
      lastModified,
      changeFrequency: "weekly",
      priority: 1.0,
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
    ...newsletterEntries,
  ];
}
