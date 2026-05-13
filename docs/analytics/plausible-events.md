# Plausible custom events registry (W8-D)

This is the authoritative list of custom Plausible events fired across the
Phase Detector + main Structural site. Update this doc when adding or
renaming events.

## Conventions

- Event names: `snake_case`, < 30 chars, no PII.
- Props: also `snake_case`. Values must be strings, numbers, or booleans (Plausible coerces).
- Goal in Plausible dashboard: add as a "Custom event" goal for the ones you want in conversion reports.

## Event catalog

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

## How to verify in production

After deploy:

1. Open phase.bytedance.city in incognito with devtools → Network tab
2. Apply a filter → check the request to `https://plausible.bytedance.city/api/event`
3. Confirm payload has `n=screener_filter_applied` and the `props` JSON
4. Repeat for waitlist signup and company detail click

## Adding a new event

1. Add the constant to `web/phase-detector/lib/analytics.ts::Events`
2. Call `trackEvent(Events.NewEventName, { ... })` at the call site
3. Add a row to the table above
4. (Optional) Add as a Goal in Plausible → Settings → Goals
