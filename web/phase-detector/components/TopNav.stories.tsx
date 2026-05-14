import type { Meta, StoryObj } from "@storybook/react";
import TopNav from "./TopNav";

/**
 * **TopNav** — sticky top navigation. Auto-hides on scroll-down, restores
 * on scroll-up. Includes mobile hamburger menu, methodology / pricing /
 * about links, and the language switcher.
 */
const meta: Meta<typeof TopNav> = {
  title: "Chrome/TopNav",
  component: TopNav,
  parameters: {
    docs: {
      description: {
        component:
          "Sticky top navigation with scroll-direction hide/show, mobile " +
          "hamburger, and brand mark. Pulls live pathname from " +
          "`usePathname()` — works inside the @storybook/nextjs router " +
          "shim.",
      },
    },
    layout: "fullscreen",
    nextjs: {
      appDirectory: true,
      navigation: { pathname: "/" },
    },
  },
};

export default meta;
type Story = StoryObj<typeof TopNav>;

export const Default: Story = {};

export const OnInternalPage: Story = {
  parameters: {
    nextjs: { appDirectory: true, navigation: { pathname: "/companies" } },
    docs: {
      description: {
        story:
          "Active state — when the current pathname matches a nav link, " +
          "the matching link should receive the active style.",
      },
    },
  },
};

export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) — hamburger menu visible, full-width links " +
          "hidden until the user opens the drawer.",
      },
    },
  },
};

export const Tablet: Story = {
  parameters: {
    viewport: { defaultViewport: "tablet" },
  },
};
