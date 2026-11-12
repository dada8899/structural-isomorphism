import type { Meta, StoryObj } from "@storybook/react";
import { CompanyCard } from "./CompanyCard";
import {
  companyApproaching,
  companyAtCritical,
  companyPost,
  companyStable,
  companyUnknown,
} from "../.storybook/fixtures";

/**
 * **CompanyCard** — the unit of display on the screener grid and on
 * company detail pages. Encodes phase classification, confidence, sector,
 * and a 30-second TL;DR.
 *
 * Variants exist for each of the five `critical_point_state` enum values
 * so visual regressions on phase color / confidence bar tier can be
 * caught quickly.
 */
const meta: Meta<typeof CompanyCard> = {
  title: "Screener/CompanyCard",
  component: CompanyCard,
  parameters: {
    docs: {
      description: {
        component:
          "Screener row / detail-page card. Five canonical variants cover " +
          "each phase state and each confidence tier (red < 0.5, amber " +
          "< 0.75, emerald ≥ 0.75).",
      },
    },
    layout: "padded",
  },
  argTypes: {
    company: {
      description:
        "A Company record from the BE canonical schema (see lib/types.ts).",
    },
  },
};

export default meta;
type Story = StoryObj<typeof CompanyCard>;

export const Stable: Story = {
  args: { company: companyStable },
  parameters: {
    docs: {
      description: {
        story:
          "Phase = `far_from_critical`, confidence 0.92 (emerald tier). " +
          "Baseline happy-path render.",
      },
    },
  },
};

export const Approaching: Story = {
  args: { company: companyApproaching },
  parameters: {
    docs: {
      description: {
        story:
          "Phase = `approaching_critical`, confidence 0.71 (amber tier). " +
          "Verify the amber confidence bar and approaching-critical badge.",
      },
    },
  },
};

export const AtCritical: Story = {
  args: { company: companyAtCritical },
  parameters: {
    docs: {
      description: {
        story:
          "Phase = `at_critical`, confidence 0.58 (amber tier). The most " +
          "visually loud state — full-saturation red badge.",
      },
    },
  },
};

export const Post: Story = {
  args: { company: companyPost },
  parameters: {
    docs: {
      description: {
        story:
          "Phase = `post_critical_transition`. Subdued ink color — the " +
          "event already happened.",
      },
    },
  },
};

export const LowConfidenceUnknown: Story = {
  args: { company: companyUnknown },
  parameters: {
    docs: {
      description: {
        story:
          "Phase = `unknown`, confidence 0.21 (red tier). Caveats > 1, " +
          "verifies caveat disclosure expand/collapse interaction.",
      },
    },
  },
};

export const MobileApproaching: Story = {
  args: { company: companyApproaching },
  parameters: {
    viewport: { defaultViewport: "mobile" },
    docs: {
      description: {
        story:
          "Mobile (375px) viewport — verifies the card stays readable at " +
          "narrow widths without horizontal scroll.",
      },
    },
  },
};
