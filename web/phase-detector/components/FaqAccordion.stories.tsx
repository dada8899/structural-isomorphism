import type { Meta, StoryObj } from "@storybook/react";
import { FaqAccordion } from "./FaqAccordion";

/**
 * **FaqAccordion** — landing-page FAQ. 6-8 questions, click to expand.
 * Uses native `<details>` so it works without JS and is keyboard-accessible.
 */
const meta: Meta<typeof FaqAccordion> = {
  title: "Landing/FaqAccordion",
  component: FaqAccordion,
  parameters: {
    docs: {
      description: {
        component:
          "FAQ accordion built on native `<details>`. Verify: keyboard " +
          "navigation (Tab + Enter), screen reader announces open/closed " +
          "state, no JS required for basic operation.",
      },
    },
    layout: "padded",
  },
};

export default meta;
type Story = StoryObj<typeof FaqAccordion>;

export const Default: Story = {};

export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile" },
  },
};

export const DarkBackground: Story = {
  parameters: {
    backgrounds: { default: "dark" },
    docs: {
      description: {
        story:
          "On a dark background — surfaces any hard-coded light-only text " +
          "colors in the question / answer copy.",
      },
    },
  },
};
