"use client";

// W10-B (session #10): 3-tier pricing table — Free / Pro $19 / Team $99.
// Design references consulted while building this:
//   - Linear.app/pricing  (3-column, "most popular" pill, billing toggle)
//   - Apple iCloud+/storage  (restrained palette, generous vertical rhythm)
//   - Lobehub /pricing  (clear feature parity, no rainbow gradients)
//   - OpenWebUI org page (community vs. team distinction)
//   - Penpot pricing (annual savings highlighted inline)
//
// Anti-patterns avoided (the generic AI-tailwind aesthetic):
//   - No "indigo-to-pink gradient" CTAs
//   - No floating glow / animated mesh background
//   - No emoji-bullet checklists
//   - No "Most Popular" + 4 other badges competing for attention
//
// Color: 1 accent (zinc-900 ink + brand-blue accent on Pro). Everything else
// in zinc-50 / zinc-200 / zinc-700. Real spacing: 32 / 24 / 16 / 8 grid.

import { useEffect, useState } from "react";
import { TIERS, annualPrice, annualSavings, type Interval, type PricingTier } from "@/lib/pricing";

interface PricingTableProps {
  /** Initial interval; defaults to month. */
  defaultInterval?: Interval;
}

function track(event: string, props: Record<string, string | number> = {}) {
  if (typeof window === "undefined") return;
  try {
    const p = (window as unknown as { plausible?: (n: string, o?: object) => void }).plausible;
    if (typeof p === "function") p(event, { props });
  } catch {
    /* swallow — analytics must never block UI */
  }
}

function CheckIcon({ included }: { included: boolean }) {
  if (!included) {
    return (
      <span
        aria-hidden="true"
        className="inline-flex h-4 w-4 items-center justify-center text-zinc-300"
      >
        —
      </span>
    );
  }
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      className="text-zinc-900"
    >
      <path
        d="M3 8.5L6.5 12L13 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TierCard({
  tier,
  interval,
  onStart,
}: {
  tier: PricingTier;
  interval: Interval;
  onStart: (tier: PricingTier) => void;
}) {
  const displayPrice =
    interval === "month" ? tier.monthly : Math.round(annualPrice(tier) / 12);
  const intervalLabel = interval === "month" ? "/月" : "/月（年付）";
  const savings = annualSavings(tier);

  return (
    <div
      className={`relative flex flex-col rounded-2xl border bg-white p-8 ${
        tier.highlight
          ? "border-zinc-900 shadow-[0_8px_24px_-12px_rgba(0,0,0,0.18)]"
          : "border-zinc-200"
      }`}
      data-testid={`tier-${tier.id}`}
    >
      {tier.highlight && (
        <div
          className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-zinc-900 px-3 py-1 text-[11px] font-medium uppercase tracking-wider text-white"
          aria-label="最受欢迎"
        >
          Most popular
        </div>
      )}

      <h2 className="text-base font-semibold tracking-tight text-zinc-900">
        {tier.name}
      </h2>
      <p className="mt-1 text-sm text-zinc-500">{tier.pitch}</p>

      <div className="mt-6 flex items-baseline gap-1">
        <span className="text-4xl font-semibold tracking-tight text-zinc-900">
          ${displayPrice}
        </span>
        <span className="text-sm text-zinc-500">{intervalLabel}</span>
      </div>

      {tier.monthly > 0 && interval === "year" && (
        <p className="mt-1 text-xs text-emerald-700">
          年付省 ${savings}（相当于 2 个月免费）
        </p>
      )}
      {tier.monthly > 0 && interval === "month" && (
        <p className="mt-1 text-xs text-zinc-400">
          年付：${annualPrice(tier)} / 年（省 ${savings}）
        </p>
      )}
      {tier.monthly === 0 && (
        <p className="mt-1 text-xs text-zinc-400">永久免费 · 无需信用卡</p>
      )}

      <button
        type="button"
        onClick={() => {
          track("checkout_started", {
            tier: tier.id,
            interval,
            from: "pricing_page",
          });
          onStart(tier);
        }}
        className={`mt-6 min-h-[44px] w-full rounded-lg px-4 py-3 text-sm font-medium transition focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 focus-visible:ring-offset-2 ${
          tier.highlight
            ? "bg-zinc-900 text-white hover:bg-zinc-700"
            : tier.id === "free"
              ? "border border-zinc-200 bg-white text-zinc-900 hover:bg-zinc-50"
              : "bg-zinc-100 text-zinc-900 hover:bg-zinc-200"
        }`}
        data-testid={`cta-${tier.id}`}
      >
        {tier.cta}
      </button>

      <ul className="mt-8 space-y-2.5 text-sm">
        {tier.features.map((f) => (
          <li
            key={f.label}
            className="flex items-start gap-2"
          >
            <span className="mt-0.5 flex-shrink-0">
              <CheckIcon included={f.included} />
            </span>
            <span className={f.included ? "text-zinc-700" : "text-zinc-400"}>
              {f.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PricingTable({ defaultInterval = "month" }: PricingTableProps) {
  const [interval, setInterval] = useState<Interval>(defaultInterval);
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    setHydrated(true);
  }, []);

  function handleStart(tier: PricingTier) {
    if (tier.id === "free") {
      // Free tier: redirect to home — no checkout step.
      if (typeof window !== "undefined") window.location.href = "/";
      return;
    }
    if (typeof window !== "undefined") {
      window.location.href = `/checkout/mock?tier=${tier.id}&interval=${interval}`;
    }
  }

  return (
    <div data-testid="pricing-table" data-hydrated={hydrated ? "true" : "false"}>
      {/* Interval toggle */}
      <div
        className="mx-auto mb-10 inline-flex rounded-lg border border-zinc-200 bg-white p-1"
        role="tablist"
        aria-label="计费周期"
      >
        <button
          type="button"
          role="tab"
          aria-selected={interval === "month"}
          onClick={() => setInterval("month")}
          className={`min-h-[44px] rounded-md px-4 py-2 text-sm font-medium transition ${
            interval === "month"
              ? "bg-zinc-900 text-white"
              : "text-zinc-600 hover:text-zinc-900"
          }`}
          data-testid="interval-month"
        >
          月付
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={interval === "year"}
          onClick={() => setInterval("year")}
          className={`min-h-[44px] rounded-md px-4 py-2 text-sm font-medium transition ${
            interval === "year"
              ? "bg-zinc-900 text-white"
              : "text-zinc-600 hover:text-zinc-900"
          }`}
          data-testid="interval-year"
        >
          年付
          <span className="ml-1 text-[11px] font-normal text-emerald-700">
            省 2 个月
          </span>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3 md:gap-6 lg:gap-8">
        {TIERS.map((tier) => (
          <TierCard
            key={tier.id}
            tier={tier}
            interval={interval}
            onStart={handleStart}
          />
        ))}
      </div>
    </div>
  );
}
