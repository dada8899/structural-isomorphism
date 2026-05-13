import type { Config } from "tailwindcss";

// W6-B: aligned with main site (web/frontend/assets/css/design-system.css).
// Font stack: Inter + Noto Serif SC (matches main site).
// Default Tailwind zinc + accent #2563EB.
const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "PingFang SC",
          "-apple-system",
          "BlinkMacSystemFont",
          "Helvetica Neue",
          "Noto Sans SC",
          "sans-serif",
        ],
        serif: [
          "Noto Serif SC",
          "Source Han Serif SC",
          "Songti SC",
          "Times New Roman",
          "serif",
        ],
        mono: [
          "JetBrains Mono",
          "SF Mono",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
      },
      colors: {
        accent: {
          DEFAULT: "#2563EB",
          hover: "#1D4ED8",
          subtle: "rgba(37, 99, 235, 0.08)",
        },
        cps: {
          subcritical: "#059669",
          nearcritical: "#D97706",
          supercritical: "#DC2626",
          tipped: "#18181B",
        },
      },
    },
  },
  plugins: [],
};
export default config;
