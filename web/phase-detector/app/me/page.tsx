"use client";

// W15-B (session #10): authenticated user profile page.
//
// Shows email, tier, account created date. Logout button clears the
// session cookie and routes back to /. Unauthenticated visitors get a
// redirect prompt to /auth/login.

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useSession } from "@/lib/auth-client";

export default function MePage() {
  const { user, loading, signOut } = useSession();
  const router = useRouter();

  // If load completed and there's no session, send them to login.
  useEffect(() => {
    if (!loading && !user) {
      // Don't auto-redirect for a tick — show the "please sign in" UI
      // first. The test relies on the data-testid being visible.
    }
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
        <p className="mb-6 text-sm text-zinc-600" data-testid="me-no-session">
          你尚未登录。请先登录后再访问个人页。
        </p>
        <Link
          href="/auth/login"
          className="inline-flex rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800"
          data-testid="me-login-link"
        >
          前往登录
        </Link>
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
