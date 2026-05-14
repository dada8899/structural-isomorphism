# Cmd+K Search — design notes (W13-E, 2026-05-15)

Wave 13-E (session #10) ships a site-wide command palette across
`phase-detector` (and reused, eventually, on `beta.structural`). This doc
captures the design choices, trade-offs, and forward roadmap.

## Why a client-side index

We considered three architectures:

1. **Server search endpoint** (FastAPI + SQLite FTS5 or `pg_trgm`)
2. **Search-as-a-service** (Algolia, Typesense Cloud)
3. **Static client-side index** (this PR)

We picked option 3 because:

- The total corpus is ~275 entries / ~90 KB raw JSON (~28 KB gzipped).
  That's smaller than a single hero image and well within the budget of a
  one-time fetch on first Cmd+K open. After the first open, results are
  zero-latency.
- A server endpoint would need its own deployment + cache invalidation
  path. Nginx already serves static files with HTTP cache. Adding a
  search service just to query 275 short documents is over-engineering.
- Algolia / Typesense would tie us to an external vendor for what is
  effectively a read-only manifest. Their free tier is generous but the
  ergonomics (records vs. our internal model) drift over time.
- Client-side keeps the operation transparent and auditable: the same
  JSON file the index ships with is what gets searched. No surprise
  ranking changes from a remote service.

The build script is `scripts/build_search_index.py`. It is idempotent
(deterministic ordering, stable IDs) and intended to run on every
commit via either a pre-commit hook or the next deploy script.

## Index size & build time trade-offs

| Aspect            | Current  | Threshold                           |
| ----------------- | -------- | ----------------------------------- |
| Entry count       | ~275     | Comfortable up to ~5,000            |
| Raw JSON size     | ~90 KB   | Re-evaluate when >300 KB raw        |
| Gzipped over wire | ~28 KB   | Browsers cache after first fetch    |
| Build time        | <1 s     | Re-evaluate when >5 s               |
| Search latency    | <2 ms    | Hand-rolled scorer on 275 entries   |

Entry sources today (counts in parentheses):

- Companies (100) — `v4/product/d1_phase_detector/companies.jsonl`
- Universality classes (37) — `v4/taxonomy/classes/*.yaml`
- Papers + section anchors (40) — `paper/*.md`
- Newsletters (1) — `docs/community/newsletters/issue-*.md`
- Docs pages (97) — `docs/**/*.md`

When companies grow to ~1,000 (the long-term goal) the index would still
be ~600 KB raw / ~120 KB gzipped — borderline. At that point we move to
a chunked index (group by sector) or transition to a server endpoint.
The signal to switch: first-open fetch time exceeds 200 ms on cellular.

## Scoring

Hand-rolled scorer (`web/phase-detector/lib/search.ts`):

1. exact match (title or keyword) — 1000
2. title prefix — 700
3. keyword prefix — 500
4. title substring — 300
5. keyword substring — 200
6. fuzzy subsequence — 100

Plus tiebreakers:

- `weight * 50` (company > class > paper > newsletter > docs)
- recency bonus on papers/newsletters (newer wins, up to +20 over a year)

No external library — fuse.js would add ~12 KB gzipped for behavior we
don't need. The hand-rolled implementation is <1 KB.

## Keyboard

- Cmd+K (Mac) / Ctrl+K (Win/Linux) — open everywhere, including inside
  text inputs (the modifier disambiguates from regular typing)
- Bare `/` — opens only when NOT focused inside a text input
- Esc — close
- Arrow Up/Down — navigate
- Enter — activate
- Tab — focus trap inside dialog

## Plausible events

- `search_opened` (props: `source` = "shortcut" | "nav-click" | "deep-link")
- `search_query` (props: `query_length`, `result_count`) — debounced 350 ms
- `search_result_click` (props: `result_type`, `result_position`)

We deliberately do not log raw queries — Plausible is cookie-less and we
keep it that way. Aggregate query length distribution + result-count
histograms tell us enough about whether the index covers user intent.

## Accessibility

- `role="dialog"` + `aria-modal="true"`
- Input is `role="combobox"` + `aria-controls` + `aria-activedescendant`
- Results are `role="listbox"` + per-item `role="option"`
- Focus trap on Tab; Esc closes; arrow keys navigate
- `aria-live="polite"` announces "X 条结果" / "no matches"
- WCAG 1.4.4 (text resize) preserved — we use `100dvh` not `100vh` so
  iOS Safari's URL bar collapse doesn't crop the modal

## Mobile

- < 640 px: full-screen overlay (rounded corners off, no margin)
- ≥ 640 px: centered modal, 600 px wide, 10 vh top margin
- Soft keyboard pushes content because we use `100dvh`

## Future: semantic search

Today's index is lexical only. Two known weaknesses:

- "earthquake" should also surface `soc_threshold_cascade` even though
  the user typed in English and the class name is Chinese
- Methodology questions ("how do you compute critical state?") should
  pull in the relevant ## sections of `paper/paper.md`

Roadmap:

1. Build a small embedding index (`sentence-transformers/all-MiniLM-L6-v2`,
   384-dim) at index-build time. Vectors are stored alongside the
   entries (~1.5 KB / entry).
2. At search time, run the lexical scorer first. If top-result score
   < threshold, fall back to a cosine-similarity lookup against the
   embedding index. We can do this client-side with a tiny WASM or
   purely-JS vector library, or move to a server endpoint at that point.
3. Decision gate: only invest if dogfooding shows users typing
   long-form intent (>15 chars on average) more than 10% of the time.

For now, lexical is the right depth-for-cost trade. Two hours of
implementation gets us 90% of the win.
