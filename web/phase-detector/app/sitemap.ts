import type { MetadataRoute } from "next";

// W3-D (2026-05-14): static sitemap for the Phase Detector product.
// Company-specific pages (/company/[ticker]) are not enumerated here yet —
// when the universe stabilizes we can shift to a dynamic sitemap that reads
// app/api/companies/route.ts.
export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://phase.bytedance.city";
  const lastModified = new Date();
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
  ];
}
