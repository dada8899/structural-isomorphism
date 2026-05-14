import type { Preview } from "@storybook/react";
import "../app/globals.css";

// Project-wide viewports. Mirrors the breakpoints we care about for
// phase-detector (small handset → wide desktop). Matches Tailwind's
// default md / lg / xl thresholds plus an explicit 320px narrow.
const viewports = {
  mobile: {
    name: "Mobile (375)",
    styles: { width: "375px", height: "667px" },
    type: "mobile",
  },
  mobileNarrow: {
    name: "Mobile narrow (320)",
    styles: { width: "320px", height: "568px" },
    type: "mobile",
  },
  tablet: {
    name: "Tablet (768)",
    styles: { width: "768px", height: "1024px" },
    type: "tablet",
  },
  desktop: {
    name: "Desktop (1280)",
    styles: { width: "1280px", height: "800px" },
    type: "desktop",
  },
  large: {
    name: "Large (1536)",
    styles: { width: "1536px", height: "960px" },
    type: "desktop",
  },
};

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
      expanded: true,
    },
    layout: "fullscreen",
    backgrounds: {
      default: "page",
      values: [
        { name: "page", value: "#ffffff" },
        { name: "muted", value: "#fafafa" },
        { name: "dark", value: "#18181b" },
      ],
    },
    viewport: {
      viewports,
      defaultViewport: "responsive",
    },
    a11y: {
      element: "#storybook-root",
      manual: false,
      config: {},
      options: {
        runOnly: {
          type: "tag",
          values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        },
      },
    },
    docs: {
      toc: true,
    },
  },
  decorators: [
    (Story, context) => {
      // Expose `parameters.nextjs.navigation` to the next/navigation mock.
      const nav = (context.parameters as { nextjs?: { navigation?: unknown } })
        .nextjs?.navigation;
      if (typeof window !== "undefined") {
        (window as unknown as { __SB_NAV__?: unknown }).__SB_NAV__ = nav;
      }
      return Story();
    },
  ],
};

export default preview;
