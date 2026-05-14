import type { Meta, StoryObj } from "@storybook/react";
import OnboardingTour from "./OnboardingTour";

/**
 * **OnboardingTour** — first-visit guided tour. Spotlights the screener,
 * a sample company card, and the methodology link. Persists the
 * "completed" flag in localStorage so returning users don't see it again.
 */
const meta: Meta<typeof OnboardingTour> = {
  title: "Onboarding/OnboardingTour",
  component: OnboardingTour,
  parameters: {
    docs: {
      description: {
        component:
          "Onboarding tour overlay. Pass `forceOpen` to bypass the " +
          "localStorage gate (used in Storybook + the 'restart tour' " +
          "settings menu item).",
      },
    },
    layout: "fullscreen",
  },
  argTypes: {
    forceOpen: {
      control: "boolean",
      description:
        "Bypass the localStorage seen-flag and always render the tour.",
    },
  },
};

export default meta;
type Story = StoryObj<typeof OnboardingTour>;

export const ForceOpen: Story = {
  args: { forceOpen: true },
};

export const CustomSteps: Story = {
  args: {
    forceOpen: true,
    steps: [
      {
        id: "welcome",
        title: "Welcome to Phase Detector",
        description:
          "We classify companies by where they sit on a 5-state phase " +
          "trajectory. Take 30 seconds to see what's new.",
      },
      {
        id: "screener",
        title: "Filter the universe",
        description:
          "Use the screener to slice by dynamics family + critical-point " +
          "state.",
        nextLabel: "Got it",
      },
    ],
  },
  parameters: {
    docs: {
      description: {
        story:
          "Custom 2-step tour — verifies the step indicator updates and " +
          'the final step uses the custom "Got it" label.',
      },
    },
  },
};

export const Mobile: Story = {
  args: { forceOpen: true },
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) — verifies the tour panel stays inside the " +
          "viewport at narrow widths.",
      },
    },
  },
};
