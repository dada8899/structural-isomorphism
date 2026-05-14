import type { Meta, StoryObj } from "@storybook/react";
import { PricingTable } from "./PricingTable";

/**
 * **PricingTable** — three-tier pricing card (Free / Pro / Team).
 * Monthly / yearly toggle, annual savings callout, primary-action CTA per
 * tier.
 *
 * Interactive state: the monthly/yearly toggle updates prices in place
 * and emits an analytics event.
 */
const meta: Meta<typeof PricingTable> = {
  title: "Conversion/PricingTable",
  component: PricingTable,
  parameters: {
    docs: {
      description: {
        component:
          "Three-tier pricing card with monthly / yearly toggle. " +
          "Default interval is selectable via the `defaultInterval` prop.",
      },
    },
    layout: "padded",
  },
  argTypes: {
    defaultInterval: {
      control: "radio",
      options: ["month", "year"],
      description: "Which interval is selected on first render.",
    },
  },
};

export default meta;
type Story = StoryObj<typeof PricingTable>;

export const Monthly: Story = {
  args: { defaultInterval: "month" },
};

export const Yearly: Story = {
  args: { defaultInterval: "year" },
  parameters: {
    docs: {
      description: {
        story:
          "Yearly default — verifies the savings badge renders and the " +
          "displayed prices are the annual-discounted values.",
      },
    },
  },
};

export const MobileMonthly: Story = {
  args: { defaultInterval: "month" },
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) — verifies the three tiers stack vertically and " +
          "the toggle stays accessible.",
      },
    },
  },
};
