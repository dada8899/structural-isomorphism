import type { Meta, StoryObj } from "@storybook/react";
import { PhaseTrajectoryChart } from "./PhaseTrajectoryChart";
import {
  companyApproaching,
  companyAtCritical,
  companyPost,
  companyStable,
  companyUnknown,
} from "../.storybook/fixtures";

/**
 * **PhaseTrajectoryChart** — full-sized SVG line chart for the company
 * detail page. Paints phase bands (stable / approaching / at_critical /
 * post) as horizontal background regions; line is rendered on top.
 *
 * SSR-friendly. Hydration adds: tooltip on hover, brush selection on the
 * x-axis, touch support, keyboard-focusable axis.
 */
const meta: Meta<typeof PhaseTrajectoryChart> = {
  title: "Visualization/PhaseTrajectoryChart",
  component: PhaseTrajectoryChart,
  parameters: {
    docs: {
      description: {
        component:
          "Server-rendered phase-distance trajectory chart. Phase bands " +
          "= background regions, trajectory line = foreground. " +
          "Hydration layer adds interactivity (tooltip + brush).",
      },
    },
    layout: "padded",
  },
  argTypes: {
    months: {
      control: { type: "range", min: 6, max: 36, step: 1 },
      description: "Trailing window size (default 12).",
    },
  },
};

export default meta;
type Story = StoryObj<typeof PhaseTrajectoryChart>;

export const Stable: Story = {
  args: { company: companyStable, months: 12 },
};

export const Approaching: Story = {
  args: { company: companyApproaching, months: 12 },
};

export const AtCritical: Story = {
  args: { company: companyAtCritical, months: 12 },
  parameters: {
    docs: {
      description: {
        story:
          "Trajectory pinned in the upper red band — most visually loud variant.",
      },
    },
  },
};

export const PostTransition: Story = {
  args: { company: companyPost, months: 12 },
};

export const Unknown: Story = {
  args: { company: companyUnknown, months: 12 },
};

export const Long36mWindow: Story = {
  args: { company: companyApproaching, months: 36 },
  parameters: {
    docs: {
      description: {
        story:
          "36-month window — verifies the line stays legible and the " +
          "x-axis ticks don't overlap.",
      },
    },
  },
};
