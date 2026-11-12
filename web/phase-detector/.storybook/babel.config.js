// Storybook-only Babel config. Lives inside .storybook/ so it does not
// interfere with Next.js's SWC compiler (Next ignores config files inside
// dotfile folders).
module.exports = {
  presets: [
    [
      "@babel/preset-env",
      {
        targets: { esmodules: true },
      },
    ],
    ["@babel/preset-react", { runtime: "automatic" }],
    "@babel/preset-typescript",
  ],
};
