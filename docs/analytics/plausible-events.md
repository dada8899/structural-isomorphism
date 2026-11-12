# Plausible custom events registry (W8-D)

This is the human-readable catalog of conversion events across Phase Detector
and the main Structural site. The executable authorities are:

- Beta: `web/frontend/assets/js/analytics-consent.js::EVENT_POLICIES`
- Phase Detector: `web/phase-detector/lib/analytics.ts`

An event or property absent from the relevant code allowlist must send
nothing. Update this catalog when adding or renaming a conversion event.

## Conventions

- Event names: `snake_case`, < 30 chars, no PII.
- Props: also `snake_case`. Values must be strings, numbers, or booleans (Plausible coerces).
- Goal in Plausible dashboard: add as a "Custom event" goal for the ones you want in conversion reports.

## Phase Detector goal highlights

| Event | Where fired | Props | Goal? |
|---|---|---|---|
| `screener_filter_applied` | `web/phase-detector/components/ScreenerFilter.tsx` | `family`, `state`, `sector`, `min_confidence` | yes — engagement |
| `company_viewed` | `web/phase-detector/components/CompanyCard.tsx` (detail link click) | `ticker`, `family`, `state` | yes — engagement |
| `waitlist_signup` | `web/phase-detector/components/WaitlistForm.tsx` + `web/frontend/assets/js/waitlist.js` (after `created=true` response) | `source` (e.g. `phase_detector`, `main_site`), `placement` (`hero`, `footer`, `inline`, `home`) | **yes — conversion** |
| `waitlist_duplicate` | same | `source`, `placement` | optional |
| `waitlist_error` | same | `source`, `placement`, `status` (HTTP code or `network`) | yes — track error rate |
| `methodology_opened` | `web/phase-detector/app/methodology/page.tsx` (via `PageOpenTracker`) | — | yes — engagement |
| `about_opened` | `web/phase-detector/app/about/page.tsx` (via `PageOpenTracker`) | — | optional |
| `thank_you_view` | `web/frontend/thank-you.html` (inline script) | `source` | yes — confirms redirect succeeded |
| `thank_you_share` | `web/phase-detector/components/ShareButtons.tsx` + main site thank-you inline script | `channel` (`x`, `linkedin`, `copy_link`) | yes — viral |

The Phase code authority above remains exhaustive. The table below is the
complete Beta allowlist; it is intentionally separate because Beta uses a
stricter property schema and refuses analytics on private research surfaces.

## Beta event catalog (exhaustive)

| Event | Where fired | Allowed props |
|---|---|---|
| `pageview` | consent transport after explicit opt-in on an allowlisted public route | — |
| `thank_you_view` | `thank-you.html` | `source` |
| `thank_you_share` | `thank-you.html` | `channel` |
| `waitlist_signup` | homepage / `waitlist.js` | `source`, `placement` |
| `waitlist_duplicate` | `waitlist.js` | `source` |
| `waitlist_error` | `waitlist.js` | `source`, `status` |
| `newsletter_signup` | `newsletter.js` | `source` |
| `newsletter_duplicate` | `newsletter.js` | `source` |
| `newsletter_error` | `newsletter.js` | `source`, `status` |
| `newsletter_archive_view` | `analytics.js` archive bootstrap | `issue` |
| `newsletter_link_click` | `analytics.js` | `issue`, `destination` |
| `newsletter_unsubscribe_click` | newsletter integration through `analytics.js` | `issue` |
| `input_warn_threshold` | `ask.js` | `limit`, `len` |
| `input_hit_cap` | `ask.js` | `limit` |
| `example_chip_clicked` | `ask.js` | `position` |
| `fingerprint_review_opened` | `ask.js` | `length` |
| `fingerprint_skipped` | `ask.js` | `length` |
| `fingerprint_confirmed` | `ask.js` | `variables`, `constraints`, `unknowns` |
| `ask_submitted` | `ask.js` | `length`, `source` |
| `input_too_long_server` | `ask.js` | `limit`, `received` |
| `retrieval_done` | `ask.js` | `count`, `retrieval_ms`, `latency_ms` |
| `candidate_selected` | `ask.js` | `phenomenon_id`, `position` |
| `candidate_view` | `ask.js` | `count` |
| `kb_cards_received` | `ask.js` | `count`, `latency_ms` |
| `citation_click` | `ask.js` | `phenomenon_id`, `position`, `surface` |
| `first_validated_answer_chunk` | `ask.js` | `latency_ms` |
| `answer_completed` | `ask.js` | `chars`, `citations_count`, `latency_ms` |
| `similar_card_clicked` | `ask.js` | `card_idx` |
| `deep_analysis_triggered` | `ask.js` | `from_thread_item`, `phenomenon_id`, `persist_opt_in` |
| `followup_clicked` | `ask.js` | `question_idx` |
| `discoveries_loaded` | `discoveries.js` | `count`, `latency_ms` |
| `glossary_tooltip_opened` | `glossary.js` | `term` |
| `stress_test_submit` | `stress-test.js` | — |
| `stress_test_result` | `stress-test.js` | `outcome` |
| `stress_test_error` | `stress-test.js` | — |
| `insights_page_viewed` | `insights.js` | — |

Private `analyze`, `report`, and `reports` bundles emit no analytics events.
Their route families, owner ids, share capabilities, auth callbacks, unknown
paths, and malformed or multiply encoded paths are all fail-closed before a
pageview can be installed.

## How to verify in production

Follow the gated acceptance in `plausible-deployment.md` after deployment:

1. In a clean profile, opt in on Beta and trigger one allowlisted event. Its
   expanded Events API payload (`name`, `url`, `domain`, optional `props`) must
   target `beta.structural.bytedance.city`; `url` contains only origin plus
   pathname.
2. In another clean profile, opt in on Phase and trigger one allowlisted event.
   The official NPM transport must target `phase.bytedance.city` and its privacy
   transform must discard unknown fields.
3. Both requests must return `202` without `x-plausible-dropped`.
4. Confirm one fresh event for each hostname in ClickHouse and then in the
   corresponding site's Realtime dashboard. Neither site substitutes for the
   other.

## Adding a new event

Phase Detector:

1. Add the constant and property schema to
   `web/phase-detector/lib/analytics.ts`.
2. Add the literal caller using the exported event constant.
3. Add or extend the privacy-contract test before changing this catalog.
4. Add the Phase event row above and, if it is a conversion, configure the
   goal for the `phase.bytedance.city` site only.

Beta:

1. Add the event and exact property allowlist to
   `web/frontend/assets/js/analytics-consent.js::EVENT_POLICIES`.
2. Add a literal caller; computed event names are forbidden because the
   exhaustive machine contract cannot prove them.
3. Add the event to the exhaustive Beta catalog above in the same change.
4. Run `tests/test_analytics_consent_contract.py`, which proves that the
   policy, literal callers, catalog, and property boundary remain aligned.
5. If it is a conversion, configure the goal for the
   `beta.structural.bytedance.city` site only.

Never add an analytics allowlist or caller to the private `analyze.js`,
`my-reports.js`, or `report.js` bundles. A product event must not be copied
between the Beta and Phase site registries unless both products independently
emit it and each side has its own code-level policy.
