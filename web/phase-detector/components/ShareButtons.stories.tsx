import type { Meta, StoryObj } from "@storybook/react";
import { ShareButtons } from "./ShareButtons";

/**
 * **ShareButtons** — X (Twitter), LinkedIn, copy-link buttons. Used on
 * company detail + universality detail pages.
 */
const meta: Meta<typeof ShareButtons> = {
  title: "Sharing/ShareButtons",
  component: ShareButtons,
  parameters: {
    docs: {
      description: {
        component:
          "Three-button share row. Copy-link uses the Clipboard API + a " +
          "transient 'Copied' toast.",
      },
    },
    layout: "centered",
  },
  argTypes: {
    url: {
      control: "text",
      description: "Absolute URL to share.",
    },
    text: {
      control: "text",
      description: "Pre-filled tweet / post copy.",
    },
  },
};

export default meta;
type Story = StoryObj<typeof ShareButtons>;

export const Default: Story = {
  args: {
    url: "https://phase.bytedance.city/company/AAPL",
    text: "AAPL — far from critical. Confidence 0.92.",
  },
};

export const LongCopy: Story = {
  args: {
    url: "https://phase.bytedance.city/universality/soc_avalanche",
    text:
      "Self-organized criticality in finance: from sandpiles to DeFi liquidation " +
      "cascades. A worked example of cross-domain isomorphism — same equation, " +
      "different substrate.",
  },
  parameters: {
    docs: {
      description: {
        story:
          "Verifies the X intent URL handles long pre-filled text " +
          "(URL-encoded > 200 chars).",
      },
    },
  },
};
