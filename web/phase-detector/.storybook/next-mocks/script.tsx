import React from "react";

// next/script mock — renders a plain <script>. Strategy / onLoad / onReady
// callbacks are accepted (and ignored).
interface ScriptProps extends React.ScriptHTMLAttributes<HTMLScriptElement> {
  strategy?: "afterInteractive" | "beforeInteractive" | "lazyOnload" | "worker";
  onLoad?: () => void;
  onReady?: () => void;
  onError?: () => void;
  id?: string;
}

const Script: React.FC<ScriptProps> = ({
  strategy,
  onLoad,
  onReady,
  onError,
  ...rest
}) => {
  return <script {...rest} />;
};

export default Script;
