"use client";

// W15-B (session #10): magic-link login page.
//
// Flow:
//   1. User enters email + clicks "Send sign-in link"
//   2. POST /api/auth/request-link
//   3. UI flips to "check your inbox" state
//   4. In NEXT_PUBLIC_AUTH_DEV_MODE=true, the magic link is shown inline
//      so local dev can click through without configuring SMTP.
//
// We deliberately do NOT auto-redirect after request — the user needs to
// open their email and click the link, which takes them to /auth/verify.

import { useState } from "react";
import Link from "next/link";
import { requestMagicLink, isDevMode } from "@/lib/auth-client";

type Phase = "idle" | "submitting" | "sent" | "error";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setDevLink(null);
    setPhase("submitting");
    const r = await requestMagicLink(email.trim());
    if (!r.ok) {
      setError(r.error || "request failed");
      setPhase("error");
      return;
    }
    if (isDevMode() && r.dev_link) {
      setDevLink(r.dev_link);
    }
    setPhase("sent");
  }

  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="mb-2 text-2xl font-semibold text-zinc-900">登录</h1>
      <p className="mb-8 text-sm text-zinc-600">
        输入邮箱即可，我们发送一次性登录链接。无需密码。
      </p>

      {phase !== "sent" && (
        <form onSubmit={onSubmit} className="space-y-4" data-testid="auth-login-form">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-zinc-700">
              邮箱
            </span>
            <input
              type="email"
              required
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-zinc-300 px-3 py-2 text-base text-zinc-900 outline-none focus:border-zinc-500 focus:ring-2 focus:ring-zinc-200"
              data-testid="auth-login-email"
              placeholder="you@example.com"
            />
          </label>
          <button
            type="submit"
            disabled={phase === "submitting" || !email.trim()}
            className="inline-flex w-full items-center justify-center rounded-md bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50"
            data-testid="auth-login-submit"
          >
            {phase === "submitting" ? "发送中…" : "发送登录链接"}
          </button>
          {error && (
            <p
              role="alert"
              className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700"
              data-testid="auth-login-error"
            >
              {error}
            </p>
          )}
        </form>
      )}

      {phase === "sent" && (
        <div
          className="rounded-md border border-emerald-200 bg-emerald-50 p-4"
          data-testid="auth-login-sent"
        >
          <p className="mb-1 text-sm font-medium text-emerald-900">
            链接已发送
          </p>
          <p className="text-sm text-emerald-800">
            请打开 <strong>{email}</strong> 收件箱，点击链接即可登录。
            链接 15 分钟内有效。
          </p>
          {devLink && (
            <div className="mt-4 border-t border-emerald-200 pt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-emerald-700">
                Dev 模式
              </p>
              <a
                href={devLink}
                className="break-all text-xs text-emerald-900 underline"
                data-testid="auth-login-dev-link"
              >
                {devLink}
              </a>
            </div>
          )}
        </div>
      )}

      <p className="mt-12 text-xs text-zinc-500">
        没有账户？这个链接也会自动创建一个。
        <br />
        <Link href="/" className="text-zinc-700 underline">
          返回首页
        </Link>
      </p>
    </main>
  );
}
