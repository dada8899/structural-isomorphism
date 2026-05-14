// W10-D: SSR newsletter issue #001 page.
//
// The markdown source lives in docs/community/newsletters/issue-001-2026-05-15.md
// (single source of truth — same file ships to email and to web). We read it
// at build time and render via lib/render-markdown.ts.

import fs from "node:fs";
import path from "node:path";
import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import JsonLd from "@/components/JsonLd";
import { NewsletterLinkTracker } from "@/components/NewsletterLinkTracker";
import { PageOpenTracker } from "@/components/PageOpenTracker";
import { WaitlistForm } from "@/components/WaitlistForm";
import { getIssue } from "@/lib/newsletter-data";
import { renderMarkdown } from "@/lib/render-markdown";
import { articleSchema, buildMetadata } from "@/lib/seo";

const ISSUE_SLUG = "001";

export const metadata: Metadata = buildMetadata({
  title: "Structural Signals #001 — Week of 2026-05-12",
  description:
    "10 phase flips, why we use block-bootstrap CIs instead of iid bootstrap, and four cross-domain preprints worth reading. First issue of the weekly Structural Signals newsletter.",
  path: "/newsletter/001",
  ogType: "article",
  ogImage: "/og/newsletter.png",
});

// Resolve the markdown file relative to the workspace root. Next builds the
// page at the phase-detector cwd, so we walk up three levels:
//   web/phase-detector/app/newsletter/001/page.tsx  → ../../../..
function readIssueMarkdown(): string {
  const cwd = process.cwd();
  // Try a few candidate locations because Next's cwd can be either the
  // package dir (dev) or the monorepo root (CI).
  const candidates = [
    path.join(cwd, "..", "..", "docs", "community", "newsletters", "issue-001-2026-05-15.md"),
    path.join(cwd, "..", "docs", "community", "newsletters", "issue-001-2026-05-15.md"),
    path.join(cwd, "docs", "community", "newsletters", "issue-001-2026-05-15.md"),
  ];
  for (const c of candidates) {
    try {
      return fs.readFileSync(c, "utf8");
    } catch {
      // try next
    }
  }
  // Fallback: shipped-with-page copy (kept in sync by CI). This keeps the
  // page renderable even when run from a build context without the docs tree.
  return [
    "# Structural Signals #001 — Week of 2026-05-12",
    "",
    "_Issue body unavailable in this build (markdown not found on disk)._",
    "_See [GitHub archive](https://github.com/dada8899/structural-isomorphism/tree/main/docs/community/newsletters) for the full text._",
  ].join("\n");
}

export default function NewsletterIssue001Page() {
  const issue = getIssue(ISSUE_SLUG);
  if (!issue) {
    return (
      <article className="mx-auto max-w-3xl px-4 py-10">
        <p>Issue not found.</p>
      </article>
    );
  }

  const markdown = readIssueMarkdown();
  // Strip the H1 from markdown — we render our own masthead above.
  const stripped = markdown.replace(/^# .*\n+/m, "");
  const html = renderMarkdown(stripped);

  return (
    <article className="mx-auto max-w-3xl px-4 py-10">
      {/* W12-B: Article schema for issue #001. */}
      <JsonLd
        id="ld-newsletter-001"
        schema={articleSchema({
          headline: issue.subject,
          description: issue.summary,
          url: `https://phase.bytedance.city/newsletter/${issue.slug}`,
          datePublished: issue.publishedOn,
        })}
      />
      <PageOpenTracker
        event="newsletter_archive_view"
        props={{ issue: issue.number }}
      />
      <NewsletterLinkTracker issueNumber={issue.number} />
      <Breadcrumb
        items={[
          { label: "首页", href: "/" },
          { label: "Newsletter", href: "/newsletter" },
          { label: `#${issue.number}` },
        ]}
      />

      <header className="mb-8 border-b border-zinc-200 pb-6">
        <p className="mb-2 text-xs uppercase tracking-wider text-zinc-500">
          Issue #{issue.number} · Published {issue.publishedOn} · {issue.weekLabel}
        </p>
        <h1
          className="serif mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          {issue.subject}
        </h1>
        <p className="text-base leading-relaxed text-zinc-600">
          {issue.summary}
        </p>
      </header>

      {/* Top subscribe form */}
      <section className="mb-10 rounded border border-zinc-200 bg-zinc-50 p-5">
        <p className="mb-3 text-sm text-zinc-700">
          📬 Get next Monday's issue delivered. No marketing, no clickbait — if
          we have nothing structural to say in a given week, we say that.
        </p>
        <WaitlistForm placement="inline" source={`newsletter_${issue.number}_top`} />
      </section>

      {/* Rendered markdown body */}
      <div
        className="newsletter-body"
        // The markdown source is project-authored, not user input. We still
        // escape raw < > & inside text nodes via renderMarkdown.
        dangerouslySetInnerHTML={{ __html: html }}
      />

      {/* Bottom subscribe form */}
      <section className="mt-12 rounded border border-zinc-200 bg-zinc-50 p-5">
        <p className="mb-3 text-sm text-zinc-700">
          Want this in your inbox next Monday?
        </p>
        <WaitlistForm
          placement="footer"
          source={`newsletter_${issue.number}_bottom`}
        />
      </section>

      <nav className="mt-10 flex justify-between border-t border-zinc-200 pt-6 text-sm">
        <Link href="/newsletter" className="text-zinc-600 hover:text-zinc-900">
          ← All issues
        </Link>
        <a
          href="https://github.com/dada8899/structural-isomorphism/tree/main/docs/community/newsletters"
          className="text-zinc-600 hover:text-zinc-900"
          target="_blank"
          rel="noopener noreferrer"
        >
          GitHub archive →
        </a>
      </nav>
    </article>
  );
}
