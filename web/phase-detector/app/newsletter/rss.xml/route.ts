import { NextResponse } from "next/server";
import { ISSUES } from "@/lib/newsletter-data";
import { SITE_URL } from "@/lib/seo";

// W12-B (session #10, 2026-05-15): RSS 2.0 feed for Structural Signals newsletter.
//
// Url: https://phase.bytedance.city/newsletter/rss.xml
// Source of truth: lib/newsletter-data.ts (same data as the archive index).
//
// Why RSS 2.0 specifically:
//   * Wide reader support (Feedly, NetNewsWire, Inoreader, Reeder).
//   * Atom would also work; RSS 2.0 chosen for compatibility w/ email
//     aggregators (Mailbrew, Stoop) that still prefer the older format.
//
// Cache: 1h `revalidate` matches the rest of the static API surface.

export const dynamic = "force-static";
export const revalidate = 3600;

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function rfc822(dateIso: string): string {
  const d = new Date(dateIso);
  return d.toUTCString();
}

export async function GET() {
  const sorted = [...ISSUES].sort((a, b) =>
    b.publishedOn.localeCompare(a.publishedOn),
  );
  const buildDate = rfc822(
    sorted.length > 0 ? sorted[0].publishedOn : new Date().toISOString(),
  );
  const items = sorted
    .map((issue) => {
      const url = `${SITE_URL}/newsletter/${issue.slug}`;
      return [
        "    <item>",
        `      <title>${escapeXml(issue.subject)}</title>`,
        `      <link>${url}</link>`,
        `      <guid isPermaLink="true">${url}</guid>`,
        `      <pubDate>${rfc822(issue.publishedOn)}</pubDate>`,
        `      <description>${escapeXml(issue.summary)}</description>`,
        "    </item>",
      ].join("\n");
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Structural Signals — Phase Detector newsletter</title>
    <link>${SITE_URL}/newsletter</link>
    <atom:link href="${SITE_URL}/newsletter/rss.xml" rel="self" type="application/rss+xml" />
    <description>Weekly cross-domain structural signals: phase flips across 1000+ companies, methodology, preprints. No marketing, no clickbait.</description>
    <language>zh-CN</language>
    <lastBuildDate>${buildDate}</lastBuildDate>
${items}
  </channel>
</rss>
`;

  return new NextResponse(xml, {
    status: 200,
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
