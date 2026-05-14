// next/font/google mock. Returns a font object with `variable` + `className`
// set to empty strings — components that drop the CSS variable into a
// className stay valid (just no custom font applied in Storybook).

type FontResult = {
  className: string;
  variable: string;
  style: { fontFamily: string };
};

function makeFont(): FontResult {
  return {
    className: "",
    variable: "",
    style: { fontFamily: "system-ui, sans-serif" },
  };
}

export const Inter = () => makeFont();
export const Noto_Serif_SC = () => makeFont();
export const JetBrains_Mono = () => makeFont();

// Catch-all so dynamic font imports don't blow up.
const handler: ProxyHandler<Record<string, unknown>> = {
  get: (_target, _prop) => () => makeFont(),
};

const proxy = new Proxy({}, handler) as Record<string, () => FontResult>;
export default proxy;
