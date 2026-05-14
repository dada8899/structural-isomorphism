"use client";

// W14-C: tiny client button that dispatches the cookie-consent:open event.
// Lives alone (not inline in privacy/page.tsx) because Server Components
// can't ship onClick handlers — and we keep page.tsx server-rendered for SEO.
import { openCookieConsent } from "./CookieConsent";

export default function ManageCookiesButton() {
  return (
    <button
      type="button"
      data-testid="manage-cookies-button"
      onClick={openCookieConsent}
      className="rounded border border-zinc-300 px-3 py-1.5 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
    >
      管理 cookie 偏好
    </button>
  );
}
