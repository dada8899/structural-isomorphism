import type { StorybookConfig } from "@storybook/react-webpack5";
import path from "path";
import type webpack from "webpack";

// Storybook 8 + React + webpack5 builder (NOT @storybook/nextjs).
//
// Why not @storybook/nextjs?
//   In our pnpm + Next 14.2.15 setup, @storybook/nextjs's deep coupling
//   to Next's bundled `next/dist/compiled/webpack` causes
//   `Cache.shutdown … reading 'tap' of undefined` at the end of every
//   build. We use plain @storybook/react-webpack5 and provide our own
//   small shims for next/image + next/link + next/navigation (see
//   `.storybook/preview.ts` + `.storybook/next-mocks/`).
//
// Tradeoffs:
//   * No automatic next/font support — Storybook falls back to system fonts.
//     Production fonts are loaded by next/font; this is documented in the
//     Introduction story.
//   * next/image renders as <img>. Sufficient for component QA.
//   * next/navigation hooks are stubbed to return reasonable defaults.

const config: StorybookConfig = {
  stories: [
    "../.storybook/intro.mdx",
    "../components/**/*.stories.@(ts|tsx|js|jsx|mdx)",
  ],
  addons: [
    "@storybook/addon-essentials", // controls + actions + docs + viewport + backgrounds
    "@storybook/addon-interactions",
    "@storybook/addon-a11y",
  ],
  framework: {
    name: "@storybook/react-webpack5",
    options: {},
  },
  staticDirs: ["../public"],
  typescript: {
    check: false,
    reactDocgen: "react-docgen-typescript",
    reactDocgenTypescriptOptions: {
      shouldExtractLiteralValuesFromEnum: true,
      propFilter: (prop) =>
        prop.parent ? !/node_modules/.test(prop.parent.fileName) : true,
    },
  },
  docs: {},
  core: {
    disableTelemetry: true,
    disableWhatsNewNotifications: true,
  },
  webpackFinal: async (config) => {
    config.cache = false;
    config.resolve = config.resolve ?? {};
    config.resolve.alias = {
      ...(config.resolve.alias as Record<string, string> | undefined),
      // Path aliases — mirror the Next.js project's tsconfig `@/*` mapping.
      "@": path.resolve(__dirname, ".."),
      // Mock next/* modules so SSR/router hooks resolve at runtime.
      "next/image$": path.resolve(__dirname, "next-mocks/image.tsx"),
      "next/link$": path.resolve(__dirname, "next-mocks/link.tsx"),
      "next/navigation$": path.resolve(
        __dirname,
        "next-mocks/navigation.tsx",
      ),
      "next/font/google$": path.resolve(
        __dirname,
        "next-mocks/font-google.tsx",
      ),
      "next/script$": path.resolve(__dirname, "next-mocks/script.tsx"),
    };
    config.module = config.module ?? {};
    config.module.rules = config.module.rules ?? [];

    // Babel-loader for TS / TSX / JS / JSX. Uses .storybook/babel.config.js.
    config.module.rules.push({
      test: /\.(ts|tsx|js|jsx)$/,
      exclude: /node_modules/,
      use: [
        {
          loader: "babel-loader",
          options: {
            configFile: path.resolve(__dirname, "babel.config.js"),
            babelrc: false,
            cacheDirectory: true,
          },
        },
      ],
    });

    // PostCSS + Tailwind: extend Storybook's default CSS rule (which uses
    // css-loader + style-loader) by inserting postcss-loader before
    // css-loader. We find the rule by its `test` for /\.css$/.
    const cssRule = config.module.rules.find(
      (r): r is webpack.RuleSetRule =>
        typeof r === "object" &&
        r !== null &&
        r.test instanceof RegExp &&
        r.test.test("foo.css"),
    );
    if (cssRule && Array.isArray(cssRule.use)) {
      cssRule.use.push({
        loader: "postcss-loader",
        options: {
          postcssOptions: {
            plugins: ["tailwindcss", "autoprefixer"],
          },
        },
      });
    }

    config.resolve!.extensions = [
      ...(config.resolve!.extensions ?? []),
      ".ts",
      ".tsx",
    ];

    return config;
  },
};

export default config;
