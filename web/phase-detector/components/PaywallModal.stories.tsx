import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { PaywallModal } from "./PaywallModal";

/**
 * **PaywallModal** — soft gate when a free user hits the 100-company
 * quota. Design references: Linear, Notion AI, Apple App Store —
 * restrained chrome, no urgency dark patterns.
 */
const meta: Meta<typeof PaywallModal> = {
  title: "Conversion/PaywallModal",
  component: PaywallModal,
  parameters: {
    docs: {
      description: {
        component:
          "Soft paywall modal. Caller owns `open` state — closing emits " +
          "an analytics event with the originating `context`.",
      },
    },
    layout: "fullscreen",
  },
  argTypes: {
    open: { control: "boolean" },
    hit: { control: { type: "number", min: 0, max: 1000, step: 25 } },
    context: { control: "text" },
  },
};

export default meta;
type Story = StoryObj<typeof PaywallModal>;

export const Open: Story = {
  args: { open: true, hit: 100, context: "screener" },
};

export const Closed: Story = {
  args: { open: false, hit: 100, context: "screener" },
  parameters: {
    docs: {
      description: {
        story: "Closed state — modal renders nothing. Smoke test of unmount.",
      },
    },
  },
};

export const HighHitCount: Story = {
  args: { open: true, hit: 500, context: "compare" },
  parameters: {
    docs: {
      description: {
        story:
          "User has hit the gate after viewing many tickers — verifies the " +
          "copy still reads naturally with a 3-digit hit count.",
      },
    },
  },
};

/**
 * Interactive — wire the modal to local React state so the close button
 * actually dismisses it. Use the "Open / Reset" buttons in the canvas.
 */
export const Interactive: Story = {
  render: () => {
    function Demo() {
      const [open, setOpen] = useState(true);
      return (
        <div className="p-8">
          <button
            type="button"
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white"
            onClick={() => setOpen(true)}
          >
            Reopen paywall
          </button>
          <PaywallModal
            open={open}
            onClose={() => setOpen(false)}
            hit={100}
            context="storybook"
          />
        </div>
      );
    }
    return <Demo />;
  },
  parameters: {
    docs: {
      description: {
        story:
          "Fully wired example. Verifies: ESC closes, click-on-scrim closes, " +
          "and the swipe-down dismissal does not crash the SSR markup.",
      },
    },
  },
};
