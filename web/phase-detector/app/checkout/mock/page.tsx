import type { Metadata } from "next";
import { Suspense } from "react";
import { CheckoutMockForm } from "@/components/CheckoutMockForm";

// W10-B (session #10): mock Stripe Checkout. NOT a real payment page.
// See `web/backend/api/checkout_mock.py` for the simulated endpoint behaviour.
//
// Migration plan (Q3 2026 or PMF signal, whichever comes first):
//   1. Replace this page with a server-side redirect to checkout.stripe.com
//      using stripe.checkout.Session.create() — done in app/checkout/page.tsx
//   2. Keep `/checkout/mock` alive as an internal-only test route gated by
//      ?force=success|declined for QA + e2e
//   3. mock_checkouts.jsonl → migrated to `customers` SQLite table; existing
//      records get an `upgrade_offer_token` for "first month 50% off" pre-PMF
//      mock signups
//
// Webhook design notes (deferred work):
//   - POST /api/stripe/webhook needs raw body for signature verification
//     (Stripe-Signature header) — DO NOT use FastAPI's json parser
//   - Idempotency key on (event_id) to dedupe Stripe retries
//   - Async: webhook handler enqueues, doesn't block the 200 response

export const metadata: Metadata = {
  title: "结账 — Phase Detector",
  description: "Mock checkout 测试页 — 不会扣款。",
  robots: { index: false, follow: false },
};

export default function CheckoutMockPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-md py-16 text-center text-sm text-zinc-500">
          加载结账表单…
        </div>
      }
    >
      <CheckoutMockForm />
    </Suspense>
  );
}
