// W12-D (session #10, 2026-05-15): /onboarding/ deep-link page.
//
// Useful for marketing-email landings — bypasses the localStorage seen
// flag and forces the tour open on mount. The page is otherwise identical
// to the landing (we re-render the hero + cards as the visual backdrop)
// so the tour spotlights land on real content.

import type { Metadata } from "next";
import OnboardingTourClient from "./OnboardingTourClient";
import { LandingHero } from "@/components/LandingHero";
import { ExploreCardsGrid } from "@/components/ExploreCardsGrid";
import { WaitlistForm } from "@/components/WaitlistForm";
import { MOCK_COMPANIES } from "@/lib/mock-data";
import type { Company } from "@/lib/types";

export const metadata: Metadata = {
  title: "导览 — Phase Detector",
  description: "4 步快速了解 Phase Detector 怎么用。",
  robots: { index: false, follow: false }, // not for SEO — only direct links.
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

async function fetchExploreCards(): Promise<Company[]> {
  if (USE_MOCK) {
    return MOCK_COMPANIES.slice(0, 6);
  }
  try {
    const r = await fetch(`${API_BASE}/screener?limit=6`, {
      next: { revalidate: 600 },
    });
    if (!r.ok) return [];
    const data = await r.json();
    return Array.isArray(data) ? data : data?.results ?? [];
  } catch {
    return [];
  }
}

export const revalidate = 600;

export default async function OnboardingPage() {
  const cards = await fetchExploreCards();
  return (
    <div className="-mx-6 -my-6 sm:-mx-6">
      <LandingHero />
      {cards.length > 0 && <ExploreCardsGrid cards={cards} />}
      <section
        aria-labelledby="onboarding-waitlist-heading"
        className="mx-auto w-full max-w-3xl px-6 py-20 sm:py-24"
        data-tour-target="waitlist-form"
      >
        <div className="rounded-3xl border border-zinc-200 bg-gradient-to-br from-white via-white to-indigo-50/40 p-8 sm:p-12">
          <h2
            id="onboarding-waitlist-heading"
            className="mb-3 text-2xl font-semibold tracking-tight text-zinc-900 sm:text-3xl"
          >
            订阅《结构信号》
          </h2>
          <WaitlistForm placement="footer" source="phase_detector_onboarding" />
        </div>
      </section>
      {/* Force-open the tour on this page (bypasses the seen flag). */}
      <OnboardingTourClient />
    </div>
  );
}
