// W10-D: newsletter archive metadata (server-side import only).
// One entry per published issue. Keep newest first.

export interface NewsletterIssue {
  number: string; // "001"
  slug: string; // url segment
  subject: string;
  weekLabel: string; // e.g. "2026-W19"
  publishedOn: string; // ISO date when issue went out
  weekStart: string; // first day covered
  weekEnd: string; // last day covered
  summary: string; // one-line teaser for archive index
}

export const ISSUES: NewsletterIssue[] = [
  {
    number: "001",
    slug: "001",
    subject: "Structural Signals #001 — Week of 2026-05-12",
    weekLabel: "2026-W19",
    publishedOn: "2026-05-15",
    weekStart: "2026-05-04",
    weekEnd: "2026-05-10",
    summary:
      "10 phase flips (AFRM, AIG, ALL, BIIB, BLDP, BNTX, COIN, COP, CVX, DDOG), why we use block-bootstrap CIs instead of iid bootstrap, four cross-domain preprints worth reading.",
  },
];

export function getIssue(slug: string): NewsletterIssue | undefined {
  return ISSUES.find((i) => i.slug === slug);
}
