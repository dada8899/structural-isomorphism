"use client";

// W10-B (session #10): paywall modal — soft gate when free user tries to
// access tickers beyond the 100-company free quota.
//
// Design references consulted:
//   - Linear "out of free seats" modal — calm, single primary action
//   - Notion AI paywall — explains WHY you're hitting the gate, not just
//     "upgrade"
//   - Apple App Store "redownload" sheet — restrained chrome, no urgency dark
//     pattern
//
// Anti-patterns avoided:
//   - "Limited time!" countdown
//   - "Most users upgrade" social-proof manipulation
//   - Locked content blurred behind a clickable scrim ("dark patterns" per
//     EU DSA Article 25)

import { useEffect } from "react";
import Link from "next/link";
import { Events, trackEvent } from "@/lib/analytics";

interface Props {
  /** Controls visibility. Caller owns the open state. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
  /** How many companies the user has hit so far (e.g. 100). For copy. */
  hit?: number;
  /** Where the user was when they hit the gate, for analytics. */
  context?: string;
}

export function PaywallModal({ open, onClose, hit = 100, context = "screener" }: Props) {
  // Fire view event once per open transition.
  useEffect(() => {
    if (!open) return;
    trackEvent(Events.PaywallModalView, { hit, context });
  }, [open, hit, context]);

  // Escape to close, focus trap is browser-default for dialog role.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    // Lock body scroll while modal open.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="paywall-modal-title"
      className="fixed inset-0 z-[100] flex items-end justify-center px-4 py-6 sm:items-center"
      data-testid="paywall-modal"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div className="relative w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-2xl">
        <button
          type="button"
          onClick={onClose}
          aria-label="关闭"
          className="absolute right-4 top-4 rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>

        <div className="mb-4 inline-flex h-10 w-10 items-center justify-center rounded-full bg-zinc-100">
          {/* lock icon, single line, no flair */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" className="text-zinc-700" aria-hidden="true">
            <rect x="3" y="11" width="18" height="11" rx="2" />
            <path d="M7 11V7a5 5 0 0110 0v4" />
          </svg>
        </div>

        <h2
          id="paywall-modal-title"
          className="mb-1.5 text-lg font-semibold tracking-tight text-zinc-900"
        >
          升级到 Pro，解锁 1000+ ticker
        </h2>
        <p className="mb-5 text-sm leading-relaxed text-zinc-600">
          Free 套餐覆盖 {hit} 家全球大盘股。如果你的研究覆盖中型股、亚洲市场、
          港股美股双重上市，Pro（$19/月）一键解锁完整库。
        </p>

        <ul className="mb-6 space-y-1.5 text-sm text-zinc-700">
          <li className="flex items-start gap-2">
            <span className="mt-1 inline-block h-1 w-1 flex-shrink-0 rounded-full bg-zinc-700" />
            1000+ ticker 全量访问
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 inline-block h-1 w-1 flex-shrink-0 rounded-full bg-zinc-700" />
            历史相位翻转 API
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 inline-block h-1 w-1 flex-shrink-0 rounded-full bg-zinc-700" />
            周三 newsletter 抢先看
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-1 inline-block h-1 w-1 flex-shrink-0 rounded-full bg-zinc-700" />
            导出 CSV / Markdown
          </li>
        </ul>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Link
            href="/pricing"
            onClick={() =>
              trackEvent(Events.PaywallModalClick, { action: "see_pricing", context })
            }
            className="flex-1 rounded-lg bg-zinc-900 px-4 py-2.5 text-center text-sm font-medium text-white transition hover:bg-zinc-700"
            data-testid="paywall-see-pricing"
          >
            查看定价
          </Link>
          <button
            type="button"
            onClick={() => {
              trackEvent(Events.PaywallModalClick, { action: "dismiss", context });
              onClose();
            }}
            className="flex-1 rounded-lg border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50"
            data-testid="paywall-dismiss"
          >
            稍后再说
          </button>
        </div>

        <p className="mt-4 text-center text-xs text-zinc-400">
          研究预览阶段：当前 mock checkout，不会扣款。
        </p>
      </div>
    </div>
  );
}
