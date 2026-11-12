import type { Config } from "tailwindcss";

// W6-B: aligned with main site (web/frontend/assets/css/design-system.css).
// Font stack: Inter + Noto Serif SC (matches main site).
// Default Tailwind zinc + accent #2563EB.
// W3-B (session #9, 2026-05-14): fonts now self-hosted via next/font; tailwind references CSS vars.
// W13-A (session #10, 2026-05-15): class-based dark mode + token utilities.
const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "Inter",
          "PingFang SC",
          "-apple-system",
          "BlinkMacSystemFont",
          "Helvetica Neue",
          "Noto Sans SC",
          "sans-serif",
        ],
        serif: [
          "var(--font-noto-serif)",
          "Noto Serif SC",
          "Source Han Serif SC",
          "Songti SC",
          "Times New Roman",
          "serif",
        ],
        mono: [
          "var(--font-jetbrains-mono)",
          "JetBrains Mono",
          "SF Mono",
          "Menlo",
          "Monaco",
          "Courier New",
          "monospace",
        ],
      },
      colors: {
        // W13-A token utilities — `bg-base / text-fg-primary / border-token / ring-token`.
        // Token-backed so dark mode flips automatically; legacy zinc / cps / accent
        // utilities remain available for incremental migration.
        base: "var(--bg-base)",
        elevated: "var(--bg-elevated)",
        overlay: "var(--bg-overlay)",
        "fg-primary": "var(--fg-primary)",
        "fg-secondary": "var(--fg-secondary)",
        "fg-tertiary": "var(--fg-tertiary)",
        "fg-inverse": "var(--fg-inverse)",
        token: "var(--border)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          subtle: "var(--accent-subtle)",
          fg: "var(--accent-fg)",
        },
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        cps: {
          subcritical: "#059669",
          nearcritical: "#D97706",
          supercritical: "#DC2626",
          tipped: "#18181B",
        },
      },
      backgroundColor: {
        base: "var(--bg-base)",
        elevated: "var(--bg-elevated)",
        overlay: "var(--bg-overlay)",
      },
      textColor: {
        "fg-primary": "var(--fg-primary)",
        "fg-secondary": "var(--fg-secondary)",
        "fg-tertiary": "var(--fg-tertiary)",
        "fg-inverse": "var(--fg-inverse)",
      },
      borderColor: {
        token: "var(--border)",
      },
      ringColor: {
        token: "var(--ring)",
      },
    },
  },
  plugins: [],
};
export default config;
