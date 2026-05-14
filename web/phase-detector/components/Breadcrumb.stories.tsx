import type { Meta, StoryObj } from "@storybook/react";
import { Breadcrumb } from "./Breadcrumb";

/**
 * **Breadcrumb** — small trail of links above the page title. Uses the
 * BE-canonical 5-state phase taxonomy on universality detail pages.
 */
const meta: Meta<typeof Breadcrumb> = {
  title: "Chrome/Breadcrumb",
  component: Breadcrumb,
  parameters: {
    docs: {
      description: {
        component:
          "Linked trail of crumbs. Items are passed as `BreadcrumbItem[]`. " +
          "The final item should be the current page and is not linked.",
      },
    },
    layout: "padded",
  },
  argTypes: {
    items: {
      description: "BreadcrumbItem[] — last item is treated as the current page.",
    },
  },
};

export default meta;
type Story = StoryObj<typeof Breadcrumb>;

export const TwoLevels: Story = {
  args: {
    items: [
      { label: "Home", href: "/" },
      { label: "Companies" },
    ],
  },
};

export const ThreeLevels: Story = {
  args: {
    items: [
      { label: "Home", href: "/" },
      { label: "Companies", href: "/companies" },
      { label: "AAPL" },
    ],
  },
};

export const FourLevelsDeep: Story = {
  args: {
    items: [
      { label: "Home", href: "/" },
      { label: "Universality", href: "/universality" },
      { label: "SOC Avalanche", href: "/universality/soc_avalanche" },
      { label: "Evidence systems" },
    ],
  },
  parameters: {
    docs: {
      description: {
        story:
          "Deep breadcrumb — verifies wrap behavior on narrow viewports.",
      },
    },
  },
};

export const MobileLong: Story = {
  args: {
    items: [
      { label: "Home", href: "/" },
      { label: "Companies", href: "/companies" },
      { label: "AAPL — Apple Inc." },
    ],
  },
  parameters: {
    viewport: { defaultViewport: "mobile" },
  },
};
