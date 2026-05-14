import type { Meta, StoryObj } from "@storybook/react";
import { SparkLine } from "./SparkLine";

/**
 * **SparkLine** — 12-month mini phase-distance trajectory. SSR-friendly
 * pure SVG, deterministic-from-ticker (no network).
 *
 * Five phase variants paint the trajectory differently:
 *   * `far_from_critical`   — hovers low, emerald hint
 *   * `approaching_critical` — drifts upward, amber band crossing
 *   * `at_critical`         — sits in the upper band, red
 *   * `post_critical_transition` — elevated plateau, ink
 *   * `unknown`             — middle band, zinc
 */
const meta: Meta<typeof SparkLine> = {
  title: "Visualization/SparkLine",
  component: SparkLine,
  parameters: {
    docs: {
      description: {
        component:
          "Inline 12-month phase-distance mini-chart used inside CompanyCard. " +
          "Deterministic from the ticker — same ticker always renders the " +
          "same shape across sessions.",
      },
    },
    layout: "centered",
  },
  argTypes: {
    ticker: {
      control: "text",
      description: "Ticker symbol — used as deterministic random seed.",
    },
    currentPhase: {
      control: "select",
      options: [
        "far_from_critical",
        "approaching_critical",
        "at_critical",
        "post_critical_transition",
        "unknown",
      ],
      description: "Critical-point state — sets the band bias.",
    },
    width: { control: { type: "range", min: 80, max: 400, step: 20 } },
    height: { control: { type: "range", min: 24, max: 120, step: 4 } },
    months: { control: { type: "range", min: 3, max: 24, step: 1 } },
  },
};

export default meta;
type Story = StoryObj<typeof SparkLine>;

export const Default: Story = {
  args: {
    ticker: "AAPL",
    currentPhase: "far_from_critical",
    width: 120,
    height: 36,
    months: 12,
  },
};

export const Approaching: Story = {
  args: {
    ticker: "TSLA",
    currentPhase: "approaching_critical",
    width: 200,
    height: 56,
  },
};

export const AtCritical: Story = {
  args: {
    ticker: "GME",
    currentPhase: "at_critical",
    width: 200,
    height: 56,
  },
};

export const PostTransition: Story = {
  args: {
    ticker: "BBBY",
    currentPhase: "post_critical_transition",
    width: 200,
    height: 56,
  },
};

export const Unknown: Story = {
  args: {
    ticker: "PRIVATE",
    currentPhase: "unknown",
    width: 200,
    height: 56,
  },
};

export const Large: Story = {
  args: {
    ticker: "MSFT",
    currentPhase: "approaching_critical",
    width: 360,
    height: 96,
    months: 24,
  },
  parameters: {
    docs: {
      description: {
        story:
          "Larger render (24-month window) showing the line resolution holds " +
          "at desktop sizes.",
      },
    },
  },
};
