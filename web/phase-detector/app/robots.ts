import type { MetadataRoute } from "next";

// W3-D (2026-05-14): SEO basics — allow crawling, disallow API routes,
// point to sitemap.xml served at the site root.
// W12-B (2026-05-15): expanded disallow list (checkout/, _next/, api/).
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/checkout/", "/_next/", "/thank-you/"],
      },
    ],
    sitemap: "https://phase.bytedance.city/sitemap.xml",
    host: "https://phase.bytedance.city",
  };
}
