"use client";

// W10-B (session #10): client-only banner that reads `?tier=…&mock=1` from
// /thank-you and renders a tier-specific success message. We layer this on
// top of the existing thank-you page (waitlist signup) so the page serves
// both flows without a second route.

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

export function CheckoutSuccessBanner() {
  const params = useSearchParams();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return null;

  const tier = (params.get("tier") || "").toLowerCase();
  const isMock = params.get("mock") === "1";
  if (!isMock || (tier !== "pro" && tier !== "team")) return null;

  const tierName = tier === "pro" ? "Pro" : "Team";

  return (
    <section
      aria-labelledby="checkout-success-heading"
      className="mb-8 rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4"
      data-testid="checkout-success-banner"
    >
      <h2
        id="checkout-success-heading"
        className="text-sm font-semibold text-emerald-900"
      >
        🎉 升级到 {tierName} 成功（mock）
      </h2>
      <p className="mt-1 text-sm leading-relaxed text-emerald-900/85">
        你已被记入「先于 Stripe」waitlist。真 Stripe
        上线时（预计 Q3 2026）会优先发邀请，并享首月 50% off。
        在那之前，你的访问已按 {tierName} 配额开放
        （Pro: 1000+ ticker / Team: 5000+ ticker + 5 seat）。
      </p>
    </section>
  );
}
