"use client";

// W6-C: extracted top nav with mobile hamburger.
// Audit § 5 mobile chrome: top nav items wrap onto two lines on 375px
// viewports. Collapse links into a drawer below sm: 640px, keep horizontal
// row on ≥ sm.
// W11-B (session #10): EN | 中 language switcher appended after the link
// row on desktop, inside the drawer on mobile.
// W12-C (session #10): slide-on-scroll-up / off-scroll-down on mobile.
// The sticky header's parent <header> element gets a `data-nav-hidden`
// attribute toggled by useScrollDirection so we can drive the CSS
// transform without breaking the existing layout.

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import LanguageSwitcher from "./LanguageSwitcher";
import { restartOnboardingTour } from "./OnboardingTour";
import ThemeToggle from "./ThemeToggle";
import { useScrollDirection } from "@/lib/useScrollDirection";

const LINKS: { href: string; label: string; external?: boolean }[] = [
  { href: "/", label: "公司表" },
  { href: "/compare", label: "对比" },
  { href: "/universality", label: "普适类" },
  { href: "/methodology", label: "方法" },
  { href: "/backtest", label: "Backtest" },
  { href: "/pricing", label: "定价" }, // W10-B (session #10)
  { href: "/about", label: "关于" },
  {
    href: "https://beta.structural.bytedance.city/classes",
    label: "Structural ↗",
    external: true,
  },
];

export default function TopNav() {
  const [open, setOpen] = useState(false);
  const sentinelRef = useRef<HTMLSpanElement>(null);
  const dir = useScrollDirection({ threshold: 96 });

  // W12-C: toggle a data-attr on the closest <header> so CSS can hide it.
  // We don't manipulate styles directly; we let .sticky-nav-hide handle it.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const header = sentinelRef.current?.closest("header");
    if (!header) return;
    // Don't hide while mobile drawer is open (would be jarring).
    if (open) {
      header.removeAttribute("data-nav-hidden");
      return;
    }
    if (dir === "down") header.setAttribute("data-nav-hidden", "true");
    else header.removeAttribute("data-nav-hidden");
  }, [dir, open]);

  // Auto-close drawer on viewport resize past sm breakpoint.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 640px)");
    const onChange = () => {
      if (mq.matches) setOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Close drawer on Escape.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {/* Sentinel: lets us reach the <header> ancestor without a ref prop. */}
      <span ref={sentinelRef} className="hidden" aria-hidden="true" />
      <nav
        className="hidden items-center gap-5 text-sm text-[var(--fg-secondary)] sm:flex"
        aria-label="主导航"
      >
        {LINKS.map((l) =>
          l.external ? (
            <a
              key={l.href}
              href={l.href}
              target="_blank"
              rel="noopener"
              className="hover:text-[var(--fg-primary)]"
            >
              {l.label}
            </a>
          ) : (
            <Link key={l.href} href={l.href} className="hover:text-zinc-900">
              {l.label}
            </Link>
          ),
        )}
        {/* W12-D: restart the onboarding tour from anywhere. */}
        <button
          type="button"
          onClick={restartOnboardingTour}
          className="text-[var(--fg-secondary)] hover:text-[var(--fg-primary)]"
          data-testid="tour-restart-link"
        >
          导览
        </button>
        <LanguageSwitcher />
        {/* W13-A: 3-state theme toggle (system/light/dark). */}
        <ThemeToggle />
      </nav>

      <button
        type="button"
        aria-label={open ? "关闭菜单" : "打开菜单"}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-[var(--border)] text-[var(--fg-secondary)] sm:hidden"
        data-testid="mobile-nav-toggle"
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          {open ? (
            <>
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </>
          ) : (
            <>
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </>
          )}
        </svg>
      </button>

      {open && (
        <>
          <div
            aria-hidden="true"
            className="fixed inset-0 top-[57px] z-[78] bg-black/30 sm:hidden"
            onClick={() => setOpen(false)}
          />
          <div
            id="mobile-nav-drawer"
            className="fixed left-0 right-0 top-[57px] z-[79] border-b border-[var(--border)] bg-[var(--bg-base)] px-6 py-4 shadow-md sm:hidden"
            role="menu"
            aria-label="主导航（移动）"
          >
            <ul className="flex flex-col gap-1">
              {LINKS.map((l) => (
                <li key={l.href}>
                  {l.external ? (
                    <a
                      href={l.href}
                      target="_blank"
                      rel="noopener"
                      onClick={() => setOpen(false)}
                      className="block min-h-[44px] rounded-md px-3 py-2.5 text-base text-[var(--fg-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--fg-primary)]"
                      role="menuitem"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <Link
                      href={l.href}
                      onClick={() => setOpen(false)}
                      className="block min-h-[44px] rounded-md px-3 py-2.5 text-base text-[var(--fg-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--fg-primary)]"
                      role="menuitem"
                    >
                      {l.label}
                    </Link>
                  )}
                </li>
              ))}
              <li>
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    restartOnboardingTour();
                  }}
                  className="block w-full rounded-md px-3 py-2 text-left text-base text-[var(--fg-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--fg-primary)]"
                  role="menuitem"
                  data-testid="tour-restart-link-mobile"
                >
                  导览
                </button>
              </li>
              <li className="pt-2">
                <LanguageSwitcher />
              </li>
              <li className="pt-2">
                <ThemeToggle compact />
              </li>
            </ul>
          </div>
        </>
      )}
    </>
  );
}
