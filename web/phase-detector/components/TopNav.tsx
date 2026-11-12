"use client";

// W6-C: extracted top nav with mobile hamburger.
// Audit § 5 mobile chrome: top nav items wrap onto two lines on 375px
// viewports. Collapse links into a drawer below xl: 1280px, where the full
// navigation can fit without horizontal overflow.
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
import { openCommandPalette } from "./CommandPaletteProvider";
import ThemeToggle from "./ThemeToggle";
import AuthNav from "./AuthNav";
import { useScrollDirection } from "@/lib/useScrollDirection";

const LINKS: { href: string; label: string; external?: boolean }[] = [
  { href: "/companies", label: "公司表" },
  { href: "/compare", label: "对比" },
  { href: "/universality", label: "普适类" },
  { href: "/methodology", label: "方法" },
  { href: "/backtest", label: "Backtest" },
  { href: "/about", label: "关于" },
  {
    href: "https://beta.structural.bytedance.city",
    label: "返回 Structural 主产品 ↗",
    external: true,
  },
];

export default function TopNav() {
  const [open, setOpen] = useState(false);
  const sentinelRef = useRef<HTMLSpanElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLDivElement>(null);
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

  // Auto-close drawer on viewport resize past the desktop breakpoint.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(min-width: 1280px)");
    const onChange = () => {
      if (mq.matches) setOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  // Trap focus and isolate background content while the drawer is modal.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        window.requestAnimationFrame(() => toggleRef.current?.focus());
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    const bodyBackground = Array.from(document.body.children).filter(
      (element): element is HTMLElement =>
        element instanceof HTMLElement
        && element.tagName !== "HEADER"
        && !drawerRef.current?.contains(element),
    );
    const brandHome = document.querySelector<HTMLElement>("[data-phase-brand-home]");
    const background = Array.from(new Set([
      ...bodyBackground,
      ...(brandHome ? [brandHome] : []),
    ]));
    const previousBackgroundState = background.map((element) => ({
      element,
      inert: element.hasAttribute("inert"),
      ariaHidden: element.getAttribute("aria-hidden"),
    }));
    const previousOverflow = document.body.style.overflow;
    for (const element of background) {
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    }
    document.body.style.overflow = "hidden";
    drawerRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      for (const state of previousBackgroundState) {
        if (!state.inert) state.element.removeAttribute("inert");
        if (state.ariaHidden === null) state.element.removeAttribute("aria-hidden");
        else state.element.setAttribute("aria-hidden", state.ariaHidden);
      }
    };
  }, [open]);

  return (
    <>
      {/* Sentinel: lets us reach the <header> ancestor without a ref prop. */}
      <span ref={sentinelRef} className="hidden" aria-hidden="true" />
      <nav
        className="hidden items-center gap-5 text-sm text-zinc-600 xl:flex"
        aria-label="主导航"
      >
        {LINKS.map((l) =>
          l.external ? (
            <a
              key={l.href}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={l.external ? "返回 Structural 主产品 / Back to main product（新标签页）" : undefined}
              className="inline-flex min-h-11 items-center hover:text-zinc-900 focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700"
            >
              {l.label}
            </a>
          ) : (
            <Link key={l.href} href={l.href} className="inline-flex min-h-11 items-center hover:text-zinc-900 focus-visible:rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700">
              {l.label}
            </Link>
          ),
        )}
        {/* W12-D: restart the onboarding tour from anywhere. */}
        <button
          type="button"
          onClick={restartOnboardingTour}
          className="min-h-11 text-zinc-600 hover:text-zinc-900"
          data-testid="tour-restart-link"
        >
          导览
        </button>
        {/* W13-E (session #10): Cmd+K search trigger. */}
        <button
          type="button"
          onClick={() => openCommandPalette("nav-click")}
          aria-label="搜索 (Cmd+K)"
          className="inline-flex min-h-11 items-center gap-1.5 rounded-md border border-zinc-200 px-2 py-1 text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
          data-testid="cmdk-trigger-desktop"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="h-4 w-4"
            aria-hidden="true"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <span className="hidden text-xs md:inline">
            搜索{" "}
            <kbd className="ml-1 rounded border border-zinc-200 bg-zinc-50 px-1 py-0.5 font-mono text-[10px]">
              ⌘K
            </kbd>
          </span>
        </button>
        <AuthNav variant="compact" />
        <LanguageSwitcher />
      </nav>

      <button
        ref={toggleRef}
        type="button"
        aria-label={open ? "关闭菜单" : "打开菜单"}
        aria-expanded={open}
        aria-controls="mobile-nav-drawer"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-zinc-200 text-zinc-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700 xl:hidden"
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
            className="fixed inset-0 top-[57px] z-[78] bg-black/30 xl:hidden"
            onClick={() => {
              setOpen(false);
              window.requestAnimationFrame(() => toggleRef.current?.focus());
            }}
          />
          <div
            ref={drawerRef}
            id="mobile-nav-drawer"
            className="fixed left-0 right-0 top-[57px] z-[79] max-h-[calc(100dvh-57px)] overflow-y-auto overscroll-contain border-b border-zinc-200 bg-white px-6 py-4 shadow-md xl:hidden"
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
                      rel="noopener noreferrer"
                      aria-label="返回 Structural 主产品 / Back to main product（新标签页）"
                      onClick={() => setOpen(false)}
                      className="block min-h-[44px] rounded-md px-3 py-2.5 text-base text-zinc-700 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700"
                      role="menuitem"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <Link
                      href={l.href}
                      onClick={() => setOpen(false)}
                      className="block min-h-[44px] rounded-md px-3 py-2.5 text-base text-zinc-700 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700"
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
                    openCommandPalette("nav-click");
                  }}
                  className="flex min-h-11 w-full items-center gap-2 rounded-md px-3 py-2.5 text-left text-base text-zinc-700 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700"
                  role="menuitem"
                  data-testid="cmdk-trigger-mobile"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="h-4 w-4"
                    aria-hidden="true"
                  >
                    <circle cx="11" cy="11" r="7" />
                    <path d="m21 21-4.3-4.3" />
                  </svg>
                  搜索
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    restartOnboardingTour();
                  }}
                  className="block min-h-11 w-full rounded-md px-3 py-2 text-left text-base text-zinc-700 hover:bg-zinc-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-700"
                  role="menuitem"
                  data-testid="tour-restart-link-mobile"
                >
                  导览
                </button>
              </li>
              <li className="pt-2">
                <LanguageSwitcher />
              </li>
              <li className="border-t border-zinc-100 pt-2">
                <AuthNav variant="drawer" />
              </li>
            </ul>
          </div>
        </>
      )}
    </>
  );
}
