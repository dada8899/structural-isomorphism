// W10-D: Newsletter archive index page.
//
// Lists all published Structural Signals issues, newest first. Currently
// just issue #001 — future issues are added to lib/newsletter-data.ts and
// each gets its own /newsletter/<NNN>/page.tsx (we may switch to a
// catch-all dynamic route once we hit ~10 issues).

import type { Metadata } from "next";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import { PageOpenTracker } from "@/components/PageOpenTracker";
import { WaitlistForm } from "@/components/WaitlistForm";
import { ISSUES } from "@/lib/newsletter-data";

export const metadata: Metadata = {
  title: "Newsletter archive — Structural Signals",
  description:
    "Weekly newsletter from structural-isomorphism: phase flips across 1000+ companies, methodology deep-dives, and cross-domain preprints. No marketing, no clickbait.",
  openGraph: {
    title: "Newsletter archive — Structural Signals",
    description:
      "Weekly cross-domain structural signals — phase flips, methodology, papers.",
    type: "website",
  },
};

export default function NewsletterArchivePage() {
  const sorted = [...ISSUES].sort((a, b) =>
    b.publishedOn.localeCompare(a.publishedOn)
  );

  return (
    <article className="mx-auto max-w-3xl px-4 py-10">
      <PageOpenTracker event="newsletter_archive_index" />
      <Breadcrumb
        items={[{ label: "首页", href: "/" }, { label: "Newsletter" }]}
      />

      <header className="mb-8">
        <h1
          className="serif mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
          style={{ fontFamily: "'Noto Serif SC', serif" }}
        >
          Structural Signals — newsletter archive
        </h1>
        <p className="text-base leading-relaxed text-zinc-600">
          Every Monday: phase flips across 1000+ public companies, one
          methodology deep-dive, a few preprints we're reading, and what's
          happening in the repo. Same physics that describes earthquakes,
          neural avalanches, and power-grid cascades.
        </p>
      </header>

      <section className="mb-10 rounded border border-zinc-200 bg-zinc-50 p-5">
        <p className="mb-3 text-sm text-zinc-700">
          📬 Subscribe — no marketing, no clickbait. If we have nothing
          structural to say in a given week, we say that.
        </p>
        <WaitlistForm placement="inline" source="newsletter_archive" />
      </section>

      <ol className="space-y-6 border-t border-zinc-200 pt-6">
        {sorted.map((issue) => (
          <li key={issue.slug} className="border-b border-zinc-100 pb-5">
            <p className="mb-1 text-xs uppercase tracking-wider text-zinc-500">
              Issue #{issue.number} · {issue.publishedOn} · {issue.weekLabel}
            </p>
            <Link
              href={`/newsletter/${issue.slug}`}
              className="serif text-xl font-semibold text-zinc-900 hover:underline"
            >
              {issue.subject}
            </Link>
            <p className="mt-2 text-sm leading-relaxed text-zinc-600">
              {issue.summary}
            </p>
            <p className="mt-2 text-xs text-zinc-500">
              Covers {issue.weekStart} → {issue.weekEnd}
            </p>
          </li>
        ))}
      </ol>

      <p className="mt-10 text-sm text-zinc-500">
        Past issues are also kept in the{" "}
        <a
          href="https://github.com/dada8899/structural-isomorphism/tree/main/docs/community/newsletters"
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
        >
          GitHub archive
        </a>{" "}
        as raw markdown, alongside the MJML email source.
      </p>
    </article>
  );
}
