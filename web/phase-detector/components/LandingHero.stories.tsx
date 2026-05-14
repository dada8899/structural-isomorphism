import type { Meta, StoryObj } from "@storybook/react";
import { LandingHero } from "./LandingHero";

/**
 * **LandingHero** — top-of-page hero for the English landing route (`/`).
 *
 * Renders the value proposition, primary CTA (try the screener), and a
 * secondary CTA (read the methodology). It is a server component with no
 * props — variations come from the page composition, not from prop
 * surfaces.
 */
const meta: Meta<typeof LandingHero> = {
  title: "Landing/LandingHero",
  component: LandingHero,
  parameters: {
    docs: {
      description: {
        component:
          "Marketing hero for the English landing page. No props — what " +
          "you see is what production renders at the top of `/`.",
      },
    },
    layout: "fullscreen",
  },
};

export default meta;
type Story = StoryObj<typeof LandingHero>;

export const Default: Story = {};

export const MobileViewport: Story = {
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) viewport — verifies the hero stack collapses to " +
          "a single column with the CTA stacked under the headline.",
      },
    },
  },
};

export const DarkBackground: Story = {
  parameters: {
    backgrounds: { default: "dark" },
    docs: {
      description: {
        story:
          "Hero on a dark background. Useful for spotting any hard-coded " +
          "light-only colors in the headline / sub-headline.",
      },
    },
  },
};
