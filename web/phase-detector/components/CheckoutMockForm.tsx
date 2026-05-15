"use client";

// W10-B (session #10): mock Stripe Checkout form.
//
// Design references consulted while building this:
//   - Stripe Checkout (the layout we're mimicking) — pre-filled total at top,
//     email-then-card stack, secure-payment microcopy
//   - Apple Pay sheet (compact form, low chrome)
//   - Penpot subscribe flow (clear "test mode" banner pattern)
//
// What this does (and does NOT do):
//   - Renders a Stripe-shaped form (email + name + card placeholder)
//   - POSTs to /api/checkout/mock
//   - On success → /thank-you?tier=pro&mock=1
//   - On declined → /pricing?error=declined
//   - 🧪 banner makes it obvious this is mock — never confuse a real user
//   - "card number" input only accepts/displays last 4 digits visibly to
//     reinforce "this isn't a real card form"

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { TIERS, annualPrice, getTier, type Interval, type TierId } from "@/lib/pricing";
import { Events, trackEvent } from "@/lib/analytics";
// W15-A: shape of the POST body is generated from Pydantic and lives
// in api-types.ts. Importing it here keeps the request inline in sync
// with the backend without a manual mirror.
import type { CheckoutBody } from "@/lib/api-types";

function isValidEmail(email: string): boolean {
  return /^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$/.test(email);
}

export function CheckoutMockForm() {
  const router = useRouter();
  const params = useSearchParams();

  const tierParam = (params.get("tier") || "pro").toLowerCase() as TierId;
  const intervalParam = (params.get("interval") || "month").toLowerCase() as Interval;
  // Test-only: allow e2e to force a deterministic branch via ?force=success|declined
  const forceParam = (params.get("force") || "").toLowerCase();

  const tier = useMemo(() => {
    const t = getTier(tierParam);
    return t && t.id !== "free" ? t : getTier("pro")!;
  }, [tierParam]);

  const interval: Interval =
    intervalParam === "year" ? "year" : "month";

  const amount =
    interval === "month" ? tier.monthly : annualPrice(tier);

  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [cardLast4, setCardLast4] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Hydration sentinel — set true once React has mounted on the client.
  // E2E checks this attribute on the form root to know when it's safe to fill.
  const [hydrated, setHydrated] = useState(false);

  // Fire pricing-related funnel event when user lands here.
  useEffect(() => {
    setHydrated(true);
    trackEvent(Events.CheckoutStarted, { tier: tier.id, interval });
  }, [tier.id, interval]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!isValidEmail(email)) {
      setError("请输入有效的邮箱地址。");
      return;
    }
    setSubmitting(true);
    // (debug logs removed)
    try {
      // Allow e2e tests to point at an out-of-process backend without
      // requiring a Next.js rewrite (which triggers HMR rebuilds and races
      // with router.push). Production has no window.__API_BASE__ → fetch
      // hits the same-origin /api/* path (nginx proxies to backend).
      const apiBase =
        (typeof window !== "undefined" &&
          (window as unknown as { __API_BASE__?: string }).__API_BASE__) || "";
      // W15-A: body shape mirrors Pydantic `CheckoutBody` from api-types.
      // TS will fail the build if backend schema drops/renames a field.
      const checkoutBody: CheckoutBody = {
        tier: tier.id,
        interval,
        email,
        name,
        card_last4: cardLast4,
        force_status: forceParam || null,
      };
      const resp = await fetch(`${apiBase}/api/checkout/mock`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(checkoutBody),
      });
      const data = await resp.json();
      if (resp.status !== 200) {
        setError(data.error || "结账失败，请重试。");
        setSubmitting(false);
        return;
      }
      if (data.status === "success") {
        trackEvent(Events.CheckoutCompletedMock, {
          tier: tier.id,
          interval,
          amount_usd: amount,
        });
        // Set cookie so /api/usage reports the upgraded tier (mock-side only).
        try {
          document.cookie = `mock_tier=${tier.id}; path=/; max-age=${60 * 60 * 24 * 30}`;
        } catch {
          /* swallow */
        }
        router.push(`/thank-you?tier=${tier.id}&mock=1`);
        return;
      }
      if (data.status === "declined") {
        trackEvent(Events.CheckoutDeclinedMock, {
          tier: tier.id,
          interval,
          reason: data.reason || "card_declined",
        });
        router.push("/pricing?error=declined");
        return;
      }
      setError("意外的响应，请重试。");
      setSubmitting(false);
    } catch (err) {
      setError((err as Error).message || "网络错误，请稍后重试。");
      setSubmitting(false);
    }
  }

  return (
    <article
      className="mx-auto max-w-md"
      data-testid="checkout-mock-form"
      data-hydrated={hydrated ? "true" : "false"}
    >
      {/* Mock banner — must stay loud */}
      <div
        className="mb-6 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        role="status"
        aria-live="polite"
      >
        <strong className="mr-1">🧪 Mock checkout —</strong>
        不会扣任何卡。真 Stripe 接入预计 Q3 2026。
      </div>

      <header className="mb-6">
        <Link
          href="/pricing"
          className="text-xs text-zinc-500 hover:text-zinc-700"
        >
          ← 返回定价页
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900">
          升级到 {tier.name}
        </h1>
        <p className="mt-1 text-sm text-zinc-500">{tier.pitch}</p>
      </header>

      {/* Order summary card */}
      <section
        aria-labelledby="order-summary-heading"
        className="mb-6 rounded-xl border border-zinc-200 bg-white p-5"
      >
        <h2
          id="order-summary-heading"
          className="mb-3 text-xs font-semibold uppercase tracking-wider text-zinc-500"
        >
          订单摘要
        </h2>
        <div className="flex items-center justify-between text-sm">
          <div>
            <div className="font-medium text-zinc-900">
              Phase Detector {tier.name}
            </div>
            <div className="mt-0.5 text-xs text-zinc-500">
              {interval === "month" ? "月度订阅" : "年度订阅（2 个月免费）"}
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-semibold tracking-tight text-zinc-900">
              ${amount}
            </div>
            <div className="text-xs text-zinc-500">
              {interval === "month" ? "/月" : "/年"}
            </div>
          </div>
        </div>
      </section>

      <form onSubmit={onSubmit} noValidate className="space-y-4">
        <div>
          <label
            htmlFor="email"
            className="mb-1.5 block text-xs font-medium text-zinc-700"
          >
            邮箱
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
            data-testid="email-input"
          />
        </div>

        <div>
          <label
            htmlFor="name"
            className="mb-1.5 block text-xs font-medium text-zinc-700"
          >
            持卡人姓名
          </label>
          <input
            id="name"
            type="text"
            autoComplete="cc-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Jane Doe"
            className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
            data-testid="name-input"
          />
        </div>

        <div>
          <label
            htmlFor="card"
            className="mb-1.5 block text-xs font-medium text-zinc-700"
          >
            卡号（占位）
          </label>
          <input
            id="card"
            type="text"
            inputMode="numeric"
            value={cardLast4}
            onChange={(e) => setCardLast4(e.target.value.replace(/\D/g, "").slice(0, 4))}
            placeholder="•••• •••• •••• 4242"
            maxLength={4}
            className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 font-mono text-sm tracking-wider text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-900/10"
            aria-describedby="card-help"
            data-testid="card-input"
          />
          <p id="card-help" className="mt-1 text-xs text-zinc-400">
            Mock 模式：只取后 4 位用于日志，不存任何真实卡号。
          </p>
        </div>

        {error && (
          <div
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"
          >
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 focus-visible:ring-offset-2"
          data-testid="submit-checkout"
        >
          {submitting ? "处理中…" : `订阅 $${amount} ${interval === "month" ? "/月" : "/年"}`}
        </button>

        <p className="mt-2 text-center text-xs text-zinc-400">
          ~10% 的提交会模拟「卡被拒」的真实分支。再试一次即可。
        </p>
      </form>
    </article>
  );
}
