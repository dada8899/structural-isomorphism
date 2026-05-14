"use client";

// W11-B i18n: EN | 中 language switcher.
//
// Click EN  → strip /zh prefix, go to canonical EN URL
// Click 中  → prepend /zh prefix
// Persists choice in localStorage; on next visit auto-redirects to the
// user's preferred locale (only if they're on the *other* locale, no loops).

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

const LS_KEY = "phase-detector-locale";

function getCurrentLocale(pathname: string): "en" | "zh" {
  if (pathname === "/zh" || pathname.startsWith("/zh/")) return "zh";
  return "en";
}

function targetEnHref(pathname: string): string {
  if (pathname === "/zh") return "/";
  if (pathname.startsWith("/zh/")) return pathname.replace(/^\/zh/, "") || "/";
  return pathname;
}

function targetZhHref(pathname: string): string {
  if (pathname === "/zh" || pathname.startsWith("/zh/")) return pathname;
  if (pathname === "/") return "/zh";
  return "/zh" + pathname;
}

export default function LanguageSwitcher() {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const current = getCurrentLocale(pathname);

  // Auto-redirect: if user previously chose a locale and is currently on the
  // other one, redirect once. Guarded by sessionStorage-style flag so refresh
  // doesn't loop.
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stored = window.localStorage.getItem(LS_KEY);
      if (!stored) return;
      const flag = "phase-detector-locale-redirected";
      if (window.sessionStorage.getItem(flag)) return;
      if (stored === "zh" && current === "en") {
        window.sessionStorage.setItem(flag, "1");
        router.replace(targetZhHref(pathname));
      } else if (stored === "en" && current === "zh") {
        window.sessionStorage.setItem(flag, "1");
        router.replace(targetEnHref(pathname));
      }
    } catch {
      // localStorage / sessionStorage may be unavailable (SSR / privacy mode).
    }
  }, [pathname, current, router]);

  const onPick = (locale: "en" | "zh") => {
    try {
      window.localStorage.setItem(LS_KEY, locale);
    } catch {
      // ignore
    }
  };

  const enHref = targetEnHref(pathname);
  const zhHref = targetZhHref(pathname);

  return (
    <div
      className="flex items-center text-xs font-medium"
      role="group"
      aria-label="Language / 语言"
      data-testid="lang-switcher"
    >
      <Link
        href={enHref}
        onClick={() => onPick("en")}
        aria-current={current === "en" ? "page" : undefined}
        data-testid="lang-en"
        className={
          current === "en"
            ? "rounded-l border border-zinc-300 bg-zinc-900 px-2 py-1 text-white"
            : "rounded-l border border-zinc-200 bg-white px-2 py-1 text-zinc-600 hover:text-zinc-900"
        }
      >
        EN
      </Link>
      <Link
        href={zhHref}
        onClick={() => onPick("zh")}
        aria-current={current === "zh" ? "page" : undefined}
        data-testid="lang-zh"
        className={
          current === "zh"
            ? "rounded-r border border-l-0 border-zinc-300 bg-zinc-900 px-2 py-1 text-white"
            : "rounded-r border border-l-0 border-zinc-200 bg-white px-2 py-1 text-zinc-600 hover:text-zinc-900"
        }
      >
        中
      </Link>
    </div>
  );
}
