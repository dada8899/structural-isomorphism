import type { Meta, StoryObj } from "@storybook/react";
import { UniversalityAnalogueMap } from "./UniversalityAnalogueMap";
import { universalityDetailSample } from "../.storybook/fixtures";

/**
 * **UniversalityAnalogueMap** — force-laid graph of evidence systems
 * organized by domain (physics / biology / finance / social / tech).
 * Renders to deterministic SVG so it is SSR-safe.
 */
const meta: Meta<typeof UniversalityAnalogueMap> = {
  title: "Visualization/UniversalityAnalogueMap",
  component: UniversalityAnalogueMap,
  parameters: {
    docs: {
      description: {
        component:
          "Force-directed graph of cross-domain analogues for a single " +
          "universality class. Layout is deterministic — same input → " +
          "same picture across SSR / hydration.",
      },
    },
    layout: "padded",
  },
  argTypes: {
    skipAnimation: {
      control: "boolean",
      description:
        "If true, render the relaxed final positions immediately — used by " +
        "screenshot tests + `prefers-reduced-motion: reduce` users.",
    },
  },
};

export default meta;
type Story = StoryObj<typeof UniversalityAnalogueMap>;

export const Default: Story = {
  args: { detail: universalityDetailSample },
};

export const NoAnimation: Story = {
  args: { detail: universalityDetailSample, skipAnimation: true },
  parameters: {
    docs: {
      description: {
        story: "Skips the relaxation animation. Matches the SSR initial paint.",
      },
    },
  },
};

export const FewerNodes: Story = {
  args: {
    detail: {
      ...universalityDetailSample,
      evidence_systems: universalityDetailSample.evidence_systems.slice(0, 2),
    },
  },
  parameters: {
    docs: {
      description: {
        story:
          "Verifies the layout when only 2 evidence systems exist — the " +
          "graph should still center inside the SVG viewport.",
      },
    },
  },
};
