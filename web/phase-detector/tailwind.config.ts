import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "SF Pro Display",
          "system-ui",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      colors: {
        cps: {
          subcritical: "***REMOVED***10B981",
          nearcritical: "***REMOVED***F59E0B",
          supercritical: "***REMOVED***EF4444",
          tipped: "***REMOVED***1F2937",
        },
      },
    },
  },
  plugins: [],
};
export default config;
