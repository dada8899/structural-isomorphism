import type { Meta, StoryObj } from "@storybook/react";
import { StatsBar } from "./StatsBar";
import { statsSample } from "../.storybook/fixtures";

/**
 * **StatsBar** — at-a-glance counts above the screener. Total universe
 * size + per-state counts (far / approaching / at / post / unknown).
 */
const meta: Meta<typeof StatsBar> = {
  title: "Screener/StatsBar",
  component: StatsBar,
  parameters: {
    docs: {
      description: {
        component:
          "Compact stats summary. Pass `null` while loading — the bar " +
          "renders skeleton placeholders.",
      },
    },
    layout: "padded",
  },
};

export default meta;
type Story = StoryObj<typeof StatsBar>;

export const Loaded: Story = {
  args: { stats: statsSample },
};

export const Loading: Story = {
  args: { stats: null },
  parameters: {
    docs: {
      description: {
        story:
          "Loading state (`stats === null`) — verifies skeleton placeholders " +
          "match the loaded layout (no CLS).",
      },
    },
  },
};

export const SmallUniverse: Story = {
  args: {
    stats: {
      ...statsSample,
      total: 42,
      by_critical_point_state: {
        far_from_critical: 20,
        approaching_critical: 12,
        at_critical: 4,
        post_critical_transition: 4,
        unknown: 2,
      },
    },
  },
  parameters: {
    docs: {
      description: {
        story:
          "Small numbers — verifies the percentage / proportion rendering " +
          "doesn't divide-by-zero when total is small.",
      },
    },
  },
};
