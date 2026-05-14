import type { Meta, StoryObj } from "@storybook/react";
import { PhaseIndicatorAnimation } from "./PhaseIndicatorAnimation";

/**
 * **PhaseIndicatorAnimation** — landing-page CSS-only 5-state phase
 * indicator. Cycles subtly through the five `critical_point_state` enum
 * values. Zero JS animation loop — pure CSS keyframes so it pauses on
 * `prefers-reduced-motion: reduce`.
 */
const meta: Meta<typeof PhaseIndicatorAnimation> = {
  title: "Landing/PhaseIndicatorAnimation",
  component: PhaseIndicatorAnimation,
  parameters: {
    docs: {
      description: {
        component:
          "5-state animated phase indicator used under the landing-page " +
          "hero. CSS-only keyframes — verify `prefers-reduced-motion: " +
          "reduce` correctly freezes the cycle.",
      },
    },
    layout: "centered",
  },
};

export default meta;
type Story = StoryObj<typeof PhaseIndicatorAnimation>;

export const Default: Story = {};

export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) — verifies the 5 chips fit on a single row without " +
          "wrap.",
      },
    },
  },
};

export const ReducedMotion: Story = {
  parameters: {
    a11y: {
      // Document expectation — the addon doesn't currently swap the
      // `prefers-reduced-motion` media query, but this story is the
      // canonical place to check manually.
      config: {},
    },
    docs: {
      description: {
        story:
          "Manual check: enable OS-level 'Reduce motion' (macOS System " +
          "Settings → Accessibility → Display). The cycle should freeze on " +
          "the first chip while remaining visible.",
      },
    },
  },
};
