"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useSession } from "@/lib/auth-client";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const BASE = API_BASE.endsWith("/api") ? API_BASE : `${API_BASE}/api`;
const BETA_ORIGIN = process.env.NEXT_PUBLIC_STRUCTURAL_BETA_ORIGIN
  ?? "https://beta.structural.bytedance.city";
const BETA_CALLBACK = `${BETA_ORIGIN.replace(/\/$/, "")}/auth/callback`;
const VALUE = /^[A-Za-z0-9_-]{32,128}$/;

function ConnectInner() {
  const params = useSearchParams();
  const { user, loading } = useSession();
  const [error, setError] = useState("");
  const [working, setWorking] = useState(false);
  const state = params.get("state") ?? "";
  const nonce = params.get("nonce") ?? "";
  const audience = params.get("audience") ?? "";
  const valid = audience === "structural-beta" && VALUE.test(state) && VALUE.test(nonce);

  useEffect(() => {
    if (valid) sessionStorage.setItem("structural_sso_request", JSON.stringify({ state, nonce, audience }));
  }, [valid, state, nonce, audience]);

  async function connect() {
    setWorking(true);
    setError("");
    try {
      const response = await fetch(`${BASE}/sso/issue`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audience, state, nonce }),
      });
      const payload = await response.json();
      if (!response.ok || payload?.ok !== true || typeof payload?.code !== "string") {
        throw new Error("issue failed");
      }
      const target = new URL(BETA_CALLBACK);
      target.searchParams.set("code", payload.code);
      target.searchParams.set("state", state);
      window.location.replace(target.toString());
    } catch {
      setWorking(false);
      setError("连接失败。没有账户数据被移动，请返回 beta 后重试。");
    }
  }

  if (!valid) return <p role="alert" className="text-sm text-rose-700">连接请求无效或已丢失，请从 beta 的“我的报告”重新开始。</p>;
  if (loading) return <p className="text-sm text-zinc-600">正在检查登录状态…</p>;
  if (!user) return (
    <div>
      <p className="text-sm leading-6 text-zinc-600">请先在此浏览器登录 Phase。登录完成后返回这个页面继续；beta 报告不会在登录前移动。</p>
      <a href="/auth/login" target="_blank" rel="noopener noreferrer" className="mt-5 inline-flex min-h-11 items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white">在新标签页登录</a>
    </div>
  );
  return (
    <div>
      <p className="text-sm leading-6 text-zinc-600">将为 beta 创建独立的安全登录状态。只有原浏览器匿名标识下的报告会在你确认后归入账户；公开分享链接不能用于认领。</p>
      <button type="button" onClick={connect} disabled={working} className="mt-5 inline-flex min-h-11 items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60" data-testid="sso-connect-submit">
        {working ? "正在安全连接…" : "继续并返回 beta"}
      </button>
      {error && <p role="alert" className="mt-4 text-sm text-rose-700">{error}</p>}
    </div>
  );
}

export default function ConnectPage() {
  return <main className="mx-auto max-w-lg px-5 py-12 sm:px-6 sm:py-16"><p className="mb-2 text-sm font-medium text-violet-700">Structural 账户</p><h1 className="mb-6 text-2xl font-semibold text-zinc-900">连接 beta 的研究报告</h1><Suspense fallback={<p>正在加载…</p>}><ConnectInner /></Suspense></main>;
}
