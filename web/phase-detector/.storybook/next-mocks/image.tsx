import React from "react";

// Lightweight mock of next/image. Renders a plain <img> so Storybook
// doesn't have to wire up the Next image optimizer. Loses lazy-loading
// magic but is fine for component QA.
interface ImageProps
  extends Omit<
    React.ImgHTMLAttributes<HTMLImageElement>,
    "src" | "width" | "height"
  > {
  src: string | { src: string };
  width?: number | string;
  height?: number | string;
  fill?: boolean;
  priority?: boolean;
  placeholder?: "blur" | "empty";
  blurDataURL?: string;
}

const Image = React.forwardRef<HTMLImageElement, ImageProps>(function Image(
  { src, width, height, fill, priority, placeholder, blurDataURL, ...rest },
  ref,
) {
  const resolvedSrc = typeof src === "string" ? src : src?.src;
  return (
    <img
      ref={ref}
      src={resolvedSrc}
      width={width}
      height={height}
      style={fill ? { width: "100%", height: "100%", objectFit: "cover" } : undefined}
      {...rest}
    />
  );
});

export default Image;
