"use client";

// Client wrapper that force-opens the tour on /onboarding mount.
// Kept separate from page.tsx so the page can stay a server component
// (preserves ISR + cards SSR).

import OnboardingTour from "@/components/OnboardingTour";

export default function OnboardingTourClient() {
  return <OnboardingTour forceOpen />;
}
