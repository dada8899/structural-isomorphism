import type { Meta, StoryObj } from "@storybook/react";
import { CheckoutMockForm } from "./CheckoutMockForm";

/**
 * **CheckoutMockForm** — placeholder checkout form. Validates email,
 * submits to a mock endpoint, and shows a success state without ever
 * touching a real PSP. Used until the Stripe integration ships.
 */
const meta: Meta<typeof CheckoutMockForm> = {
  title: "Conversion/CheckoutMockForm",
  component: CheckoutMockForm,
  parameters: {
    docs: {
      description: {
        component:
          "Mock checkout form. Verify: email validation rejects malformed " +
          "addresses, submit is disabled until valid, success state " +
          "replaces the form rather than appending below it.",
      },
    },
    layout: "centered",
  },
};

export default meta;
type Story = StoryObj<typeof CheckoutMockForm>;

export const Default: Story = {};

export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) — verifies the form stays single-column with the " +
          "submit button full-width.",
      },
    },
  },
};
