"use client";

// W15-B (session #10): auth widget for the top nav.
//
// Shows either:
//   - "Sign in" link when no session
//   - "<email>" link to /me + "Sign out" button when signed in
//
// Designed to slot into TopNav without coupling — it's a standalone
// component that any chrome surface can mount.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";

interface Props {
  /** Visual variant — `compact` is for desktop nav, `drawer` for mobile menu. */
  variant?: "compact" | "drawer";
}

export default function AuthNav({ variant = "compact" }: Props) {
  const { user, loading, signOut } = useSession();
  const router = useRouter();

  async function onSignOut() {
    await signOut();
    router.refresh();
  }

  if (loading) {
    return (
      <span
        className="text-xs text-zinc-400"
        data-testid="auth-nav-loading"
        aria-live="polite"
      >
        …
      </span>
    );
  }

  if (!user) {
    return (
      <Link
        href="/auth/login"
        className={
          variant === "drawer"
            ? "block w-full rounded-md px-3 py-2.5 text-left text-base text-zinc-700 hover:bg-zinc-50"
            : "text-sm text-zinc-600 hover:text-zinc-900"
        }
        data-testid="auth-nav-signin"
      >
        登录
      </Link>
    );
  }

  if (variant === "drawer") {
    return (
      <div className="flex flex-col gap-1" data-testid="auth-nav-signed-in">
        <Link
          href="/me"
          className="block rounded-md px-3 py-2.5 text-base text-zinc-700 hover:bg-zinc-50"
          data-testid="auth-nav-email"
        >
          {user.email}
        </Link>
        <button
          type="button"
          onClick={onSignOut}
          className="block rounded-md px-3 py-2 text-left text-sm text-zinc-500 hover:bg-zinc-50 hover:text-zinc-900"
          data-testid="auth-nav-signout"
        >
          退出登录
        </button>
      </div>
    );
  }

  return (
    <span className="flex items-center gap-2" data-testid="auth-nav-signed-in">
      <Link
        href="/me"
        className="text-sm text-zinc-700 hover:text-zinc-900"
        data-testid="auth-nav-email"
      >
        {user.email}
      </Link>
      <button
        type="button"
        onClick={onSignOut}
        className="text-xs text-zinc-500 hover:text-zinc-900"
        data-testid="auth-nav-signout"
      >
        退出
      </button>
    </span>
  );
}
