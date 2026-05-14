import type { MetadataRoute } from "next";

// W3-D (2026-05-14): SEO basics — allow crawling, disallow API routes,
// point to sitemap.xml served at the site root.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: "/api/",
    },
    sitemap: "https://phase.bytedance.city/sitemap.xml",
  };
}
