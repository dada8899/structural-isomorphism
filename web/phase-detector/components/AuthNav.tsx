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
import { useState } from "react";
import { useSession } from "@/lib/auth-client";

interface Props {
  /** Visual variant — `compact` is for desktop nav, `drawer` for mobile menu. */
  variant?: "compact" | "drawer";
}

export default function AuthNav({ variant = "compact" }: Props) {
  if (process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true") return null;
  return <EnabledAuthNav variant={variant} />;
}

function EnabledAuthNav({ variant = "compact" }: Props) {
  const { user, loading, signOut } = useSession();
  const router = useRouter();
  const [signOutError, setSignOutError] = useState(false);

  async function onSignOut() {
    setSignOutError(false);
    try {
      await signOut();
      router.refresh();
    } catch {
      setSignOutError(true);
    }
  }

  if (loading) {
    return (
      <Link
        href="/auth/login"
        className={
          variant === "drawer"
            ? "block min-h-11 w-full rounded-md border border-zinc-300 px-3 py-2.5 text-left text-base font-medium text-zinc-800"
            : "inline-flex min-h-11 items-center rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-800 hover:bg-zinc-50"
        }
        data-testid="auth-nav-loading"
      >
        注册 / 登录
      </Link>
    );
  }

  if (!user) {
    return (
      <Link
        href="/auth/login"
        className={
          variant === "drawer"
            ? "block min-h-11 w-full rounded-md border border-zinc-300 px-3 py-2.5 text-left text-base font-medium text-zinc-800 hover:bg-zinc-50"
            : "inline-flex min-h-11 items-center rounded-md border border-zinc-300 px-3 text-sm font-medium text-zinc-800 hover:bg-zinc-50"
        }
        data-testid="auth-nav-signin"
      >
        注册 / 登录
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
        {signOutError && (
          <span role="alert" className="px-3 text-xs text-rose-700">
            退出失败，请重试
          </span>
        )}
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
      {signOutError && (
        <span role="alert" className="text-xs text-rose-700">
          退出失败，请重试
        </span>
      )}
    </span>
  );
}
