"use client";

// W8-D: share buttons for /thank-you. X, LinkedIn, copy-link.

import { useState } from "react";
import { trackEvent } from "@/lib/analytics";

interface Props {
  url: string;
  text: string;
}

export function ShareButtons({ url, text }: Props) {
  const [copied, setCopied] = useState(false);

  const xHref = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`;
  const linkedinHref = `https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`;

  async function onCopy() {
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        setCopied(true);
        trackEvent("thank_you_share", { channel: "copy_link" });
        setTimeout(() => setCopied(false), 2000);
      }
    } catch {
      // Clipboard can fail (HTTP, perms). Fall back to selecting the URL.
      window.prompt("Copy this link", url);
    }
  }

  return (
    <div className="flex flex-wrap gap-2">
      <a
        href={xHref}
        target="_blank"
        rel="noopener"
        onClick={() => trackEvent("thank_you_share", { channel: "x" })}
        className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 transition hover:border-zinc-400"
      >
        分享到 X ↗
      </a>
      <a
        href={linkedinHref}
        target="_blank"
        rel="noopener"
        onClick={() => trackEvent("thank_you_share", { channel: "linkedin" })}
        className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 transition hover:border-zinc-400"
      >
        分享到 LinkedIn ↗
      </a>
      <button
        type="button"
        onClick={onCopy}
        className="inline-flex items-center gap-1.5 rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-xs font-medium text-zinc-700 transition hover:border-zinc-400"
      >
        {copied ? "已复制 ✓" : "复制链接"}
      </button>
    </div>
  );
}
