"use client";

// W15-B (session #10): authenticated user profile page.
//
// Shows email, tier, account created date. Logout button clears the
// session cookie and routes back to /. Unauthenticated visitors get a
// redirect prompt to /auth/login.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";

// Auto-redirect delay before sending unauthed visitors to /auth/login.
// Keep the data-testid="me-no-session" element rendered during this window
// so the e2e test (which asserts the testid) still passes.
const REDIRECT_DELAY_MS = 2000;

export default function MePage() {
  const { user, loading, signOut } = useSession();
  const router = useRouter();
  const [redirecting, setRedirecting] = useState(false);

  // After load completes, if there is no session, show the "please sign in"
  // card briefly and then auto-redirect to /auth/login for better UX.
  useEffect(() => {
    if (loading || user) return;
    setRedirecting(true);
    const t = setTimeout(() => {
      router.push("/auth/login");
    }, REDIRECT_DELAY_MS);
    return () => clearTimeout(t);
  }, [loading, user, router]);

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <p className="text-sm text-zinc-500" data-testid="me-loading">
          加载中…
        </p>
      </main>
    );
  }

  if (!user) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-16">
        <h1 className="mb-3 text-2xl font-semibold text-zinc-900">未登录</h1>
        <p className="mb-3 text-sm text-zinc-600" data-testid="me-no-session">
          你尚未登录。即将跳转到登录页…
        </p>
        <div className="flex items-center gap-3" data-testid="me-redirect-spinner">
          <span
            aria-hidden="true"
            className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-zinc-300 border-t-zinc-700"
          />
          <a
            href="/auth/login"
            className="inline-flex rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800"
            data-testid="me-login-link"
          >
            立即登录
          </a>
          {redirecting && (
            <span className="text-xs text-zinc-500">2 秒后自动跳转</span>
          )}
        </div>
      </main>
    );
  }

  async function onLogout() {
    await signOut();
    router.push("/");
  }

  // Format created_at as YYYY-MM-DD.
  let createdAt = user.created_at;
  try {
    createdAt = new Date(user.created_at).toISOString().slice(0, 10);
  } catch {
    // Already a string; leave as-is.
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <h1 className="mb-8 text-2xl font-semibold text-zinc-900">个人</h1>

      <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            邮箱
          </dt>
          <dd className="mt-1 text-base text-zinc-900" data-testid="me-email">
            {user.email}
          </dd>
        </div>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            账户层级
          </dt>
          <dd className="mt-1 text-base text-zinc-900" data-testid="me-tier">
            {user.tier}
          </dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            创建时间
          </dt>
          <dd
            className="mt-1 text-base text-zinc-900"
            data-testid="me-created-at"
          >
            {createdAt}
          </dd>
        </div>
      </dl>

      <button
        type="button"
        onClick={onLogout}
        className="mt-10 rounded-md border border-zinc-300 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
        data-testid="me-logout"
      >
        退出登录
      </button>
    </main>
  );
}
