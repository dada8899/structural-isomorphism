# /checkout/mock — Stripe Pro mock (W10-B, session #10)

A simulated Stripe Checkout page. **No real charges happen.** Real Stripe
integration is deferred until PMF signal (target Q3 2026).

## What this directory contains

- `page.tsx` — server component shell that renders `<CheckoutMockForm>` in a
  `<Suspense>` boundary (required by `useSearchParams`).
- `../../components/CheckoutMockForm.tsx` — client component with the form
  state, validation, and `/api/checkout/mock` POST handling.

## How the mock flow works

1. User clicks **Start Pro** / **Start Team** on `/pricing` → navigates to
   `/checkout/mock?tier=pro&interval=month`.
2. Form posts to `/api/checkout/mock` (backend: `web/backend/api/checkout_mock.py`).
3. Backend returns `status: success` ~90% of the time, `status: declined` ~10%
   of the time (simulating real Stripe's card-decline rate).
4. Success → redirect to `/thank-you?tier=pro&mock=1` (shows tier-specific
   success banner).
5. Decline → redirect to `/pricing?error=declined`.
6. All attempts (success + decline) persist to
   `web/backend/data/mock_checkouts.jsonl` as a "would-have-paid" waitlist.

## Test-only overrides (localhost only)

- `?force=success` or `?force=declined` query param → deterministic branch.
  Backend honours this only when the request comes from `127.0.0.1`,
  `localhost`, or the FastAPI `testclient`. Production IPs ignore it.
- `window.__API_BASE__` (set via `add_init_script` in e2e fixtures) → points
  the form's fetch at an out-of-process backend without requiring a
  `next.config.js` rewrite (rewrites trigger HMR rebuilds that race with
  `router.push()`).

## Migration to real Stripe (Q3 2026 target)

When PMF signal arrives:

1. **Replace this page** with a server-side redirect to
   `checkout.stripe.com` via `stripe.checkout.Session.create()` (done in
   `app/checkout/page.tsx`, separate from `/checkout/mock`).
2. **Keep `/checkout/mock` alive** as an internal-only test route gated
   by `?force=…` for QA + e2e.
3. **Migrate** `mock_checkouts.jsonl` → a real `customers` SQLite table.
   Existing mock signups get an `upgrade_offer_token` for "first month
   50% off" — promised on the pricing page disclaimer.
4. **Add webhook receiver** at `/api/stripe/webhook` — separate FastAPI
   router, raw-body signature verification (Stripe-Signature header,
   DO NOT use FastAPI's JSON parser), idempotency on `event_id` to
   dedupe Stripe retries, enqueue-then-200 (don't block).

## Why mock now instead of real Stripe

- **PMF gate**: with < $X MRR signal, the integration tax (webhook
  reliability, dispute handling, dunning, tax compliance, SCA, refunds,
  KYC for payouts) is more risk than reward.
- **Funnel measurement**: we still get the *signal* — paywall modal views,
  checkout starts, completed-mocks, decline simulation. Plausible funnel
  events `pricing_view → checkout_started → checkout_completed_mock`
  reveals if pricing + positioning lands BEFORE we invest in real Stripe.
- **Reversibility**: replacing this page with a Stripe redirect is a
  half-day swap. The opposite (rolling back live Stripe) is not.
