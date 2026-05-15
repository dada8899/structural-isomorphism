"use client";

// W15-B (session #10): magic-link verification.
//
// Reads ?token=... from URL, POSTs to /api/auth/verify, then redirects to
// /me on success. Failure shows an error + a back-to-login link.
//
// We use `useSearchParams` from next/navigation and a Suspense boundary
// (required in Next 14 App Router for static export compat).

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { verifyMagicLink } from "@/lib/auth-client";

type Phase = "loading" | "success" | "error" | "missing";

function VerifyInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const token = sp.get("token");
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setPhase("missing");
      return;
    }
    let cancelled = false;
    (async () => {
      const r = await verifyMagicLink(token);
      if (cancelled) return;
      if (r.ok) {
        setPhase("success");
        // Small delay so the user sees the success state, then redirect.
        setTimeout(() => router.push("/me"), 600);
      } else {
        setError(r.error || "verify failed");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, router]);

  if (phase === "loading") {
    return (
      <p className="text-sm text-zinc-600" data-testid="auth-verify-loading">
        正在验证登录链接…
      </p>
    );
  }
  if (phase === "success") {
    return (
      <p
        className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
        data-testid="auth-verify-success"
      >
        登录成功，正在跳转…
      </p>
    );
  }
  if (phase === "missing") {
    return (
      <p
        className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700"
        data-testid="auth-verify-missing"
      >
        缺少登录 token。请回到登录页重新请求链接。
      </p>
    );
  }
  return (
    <div data-testid="auth-verify-error">
      <p className="rounded-md bg-rose-50 px-3 py-2 text-sm text-rose-700">
        登录失败：{error}
      </p>
      <p className="mt-4 text-sm">
        <Link
          href="/auth/login"
          className="text-zinc-700 underline"
          data-testid="auth-verify-back-link"
        >
          ← 返回登录页
        </Link>
      </p>
    </div>
  );
}

export default function VerifyPage() {
  return (
    <main className="mx-auto max-w-md px-6 py-16">
      <h1 className="mb-6 text-2xl font-semibold text-zinc-900">登录验证</h1>
      <Suspense fallback={<p className="text-sm text-zinc-500">…</p>}>
        <VerifyInner />
      </Suspense>
    </main>
  );
}
