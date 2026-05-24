import React from "react";

// Drop-in mock of `next/link`. We don't have a real router in Storybook,
// so links degrade to plain <a>. `prefetch` / `replace` / `scroll` props
// are accepted and ignored.
export interface LinkProps
  extends Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href"> {
  href: string | { pathname?: string };
  prefetch?: boolean;
  replace?: boolean;
  scroll?: boolean;
  shallow?: boolean;
  passHref?: boolean;
  legacyBehavior?: boolean;
  locale?: string | false;
}

const Link = React.forwardRef<HTMLAnchorElement, LinkProps>(function Link(
  { href, prefetch, replace, scroll, shallow, passHref, legacyBehavior, locale, children, ...rest },
  ref,
) {
  const resolvedHref =
    typeof href === "string" ? href : href?.pathname ?? "#";
  return (
    <a ref={ref} href={resolvedHref} {...rest}>
      {children}
    </a>
  );
});

export default Link;
