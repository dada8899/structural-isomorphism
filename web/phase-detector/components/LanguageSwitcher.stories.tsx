import type { Meta, StoryObj } from "@storybook/react";
import LanguageSwitcher from "./LanguageSwitcher";

/**
 * **LanguageSwitcher** — toggles between `/` (en) and `/zh` (zh). Lives
 * in the TopNav. Persists the user choice to localStorage so a returning
 * user lands on their preferred locale.
 */
const meta: Meta<typeof LanguageSwitcher> = {
  title: "Chrome/LanguageSwitcher",
  component: LanguageSwitcher,
  parameters: {
    docs: {
      description: {
        component:
          "EN / ZH switcher. Uses `usePathname()` + `useRouter()` from " +
          "next/navigation — the @storybook/nextjs framework shims both, " +
          "so navigation parameters under `parameters.nextjs.navigation` " +
          "drive which locale is rendered active.",
      },
    },
    layout: "centered",
    nextjs: { appDirectory: true, navigation: { pathname: "/" } },
  },
};

export default meta;
type Story = StoryObj<typeof LanguageSwitcher>;

export const English: Story = {
  parameters: {
    nextjs: { appDirectory: true, navigation: { pathname: "/" } },
  },
};

export const Chinese: Story = {
  parameters: {
    nextjs: { appDirectory: true, navigation: { pathname: "/zh" } },
    docs: {
      description: {
        story:
          "Active locale = zh. Verifies the active highlight + the link " +
          "target switches to `/` (drop /zh prefix).",
      },
    },
  },
};

export const OnInternalPage: Story = {
  parameters: {
    nextjs: { appDirectory: true, navigation: { pathname: "/companies" } },
    docs: {
      description: {
        story:
          "On `/companies` — the zh link should target `/zh/companies`, " +
          "not `/zh`.",
      },
    },
  },
};
