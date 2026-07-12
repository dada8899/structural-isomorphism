"use client";

// W15-B (session #10): authenticated user profile page.
//
// Shows email, tier, account created date. Logout button clears the
// session cookie and routes back to /. Unauthenticated visitors get a
// redirect prompt to /auth/login.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth-client";
import { clearLocalAccountState } from "@/lib/favorites";

// Auto-redirect delay before sending unauthed visitors to /auth/login.
// Keep the data-testid="me-no-session" element rendered during this window
// so the e2e test (which asserts the testid) still passes.
const REDIRECT_DELAY_MS = 2000;
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";
const ACCOUNT_API_BASE = API_BASE.endsWith("/api") ? API_BASE : `${API_BASE}/api`;
const EXPORT_SCHEMA_VERSION = "phase-account-export-v1";

type RequestState = "idle" | "working" | "success" | "error";

function safeTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return new Date().toISOString().replace(/[:.]/g, "-");
  return date.toISOString().replace(/[:.]/g, "-");
}

export default function MePage() {
  const { user, loading, signOut, clearLocalSession } = useSession();
  const router = useRouter();
  const [redirecting, setRedirecting] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const [exportState, setExportState] = useState<RequestState>("idle");
  const [exportMessage, setExportMessage] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [deleteState, setDeleteState] = useState<RequestState>("idle");
  const [deleteMessage, setDeleteMessage] = useState("");
  const [deletedAt, setDeletedAt] = useState("");
  const exportInFlight = useRef(false);
  const deleteInFlight = useRef(false);

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

  // Successful deletion clears the hook's user state. Render the confirmed
  // completion before the generic signed-out branch so users never see a
  // misleading "not logged in" redirect after an irreversible action.
  if (deleteState === "success") {
    return (
      <main className="mx-auto max-w-2xl px-5 py-12 sm:px-6 sm:py-16" data-testid="account-deleted">
        <p className="mb-3 text-sm font-medium text-emerald-700">删除完成</p>
        <h1 className="text-2xl font-semibold text-zinc-900">你的账户已永久删除</h1>
        <p className="mt-4 max-w-xl text-sm leading-6 text-zinc-600">
          账户资料、服务器收藏和有效登录会话已删除；这台设备上的匿名收藏也已清理。
          如需再次使用账户功能，可以重新注册。
        </p>
        <p className="mt-3 text-xs text-zinc-500" data-testid="account-deleted-at">
          完成时间：{new Date(deletedAt).toLocaleString("zh-CN")}
        </p>
        <a
          href="/"
          className="mt-8 inline-flex min-h-11 items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          data-testid="account-deleted-home"
        >
          返回首页
        </a>
      </main>
    );
  }

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
            className="inline-flex min-h-11 items-center rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800"
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
    setLogoutError(false);
    try {
      await signOut();
      router.push("/");
    } catch {
      setLogoutError(true);
    }
  }

  async function onExport() {
    if (exportInFlight.current) return;
    exportInFlight.current = true;
    setExportState("working");
    setExportMessage("");
    try {
      const response = await fetch(`${ACCOUNT_API_BASE}/me/export`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`export failed: ${response.status}`);
      const payload = await response.json();
      if (payload?.ok !== true || typeof payload?.exported_at !== "string") {
        throw new Error("invalid export response");
      }
      const downloadedAt = new Date().toISOString();
      const document = {
        schema_version: EXPORT_SCHEMA_VERSION,
        downloaded_at: downloadedAt,
        export: payload,
      };
      const blob = new Blob([JSON.stringify(document, null, 2) + "\n"], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download = `phase-account-export-${safeTimestamp(payload.exported_at)}.json`;
      link.click();
      URL.revokeObjectURL(url);
      setExportState("success");
      setExportMessage("数据已导出为 JSON 文件。文件包含导出时间和格式版本。");
    } catch {
      setExportState("error");
      setExportMessage("导出失败。你的账户和登录状态没有变化，请稍后重试。");
    } finally {
      exportInFlight.current = false;
    }
  }

  async function onDeleteAccount() {
    if (deleteConfirmation !== "DELETE" || deleteInFlight.current) return;
    deleteInFlight.current = true;
    setDeleteState("working");
    setDeleteMessage("");
    try {
      const response = await fetch(`${ACCOUNT_API_BASE}/me/delete`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ confirmation: deleteConfirmation }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || payload?.ok !== true || typeof payload?.deleted_at !== "string") {
        throw new Error(`delete failed: ${response.status}`);
      }
      clearLocalAccountState();
      clearLocalSession();
      setDeletedAt(payload.deleted_at);
      setDeleteState("success");
    } catch {
      // The server did not confirm deletion. Keep the visible session and all
      // local data so the UI never claims an irreversible action succeeded.
      setDeleteState("error");
      setDeleteMessage("删除失败。账户仍然保留，你也没有退出登录，请稍后重试。");
    } finally {
      deleteInFlight.current = false;
    }
  }

  // Format created_at as YYYY-MM-DD.
  let createdAt = user.created_at;
  try {
    createdAt = new Date(user.created_at).toISOString().slice(0, 10);
  } catch {
    // Already a string; leave as-is.
  }

  return (
    <main className="mx-auto max-w-2xl px-5 py-12 sm:px-6 sm:py-16">
      <h1 className="text-2xl font-semibold text-zinc-900">账户设置</h1>
      <p className="mt-2 text-sm leading-6 text-zinc-600">
        查看账户资料，导出你的数据，或管理登录状态。
      </p>

      <dl className="mt-8 grid grid-cols-1 gap-5 rounded-xl border border-zinc-200 bg-white p-5 sm:grid-cols-2 sm:p-6">
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

      <section className="mt-8 rounded-xl border border-zinc-200 bg-white p-5 sm:p-6" aria-labelledby="data-heading">
        <h2 id="data-heading" className="text-base font-semibold text-zinc-900">你的数据</h2>
        <p className="mt-2 text-sm leading-6 text-zinc-600">
          下载账户资料和已关联资产的 JSON 副本。导出不会修改或删除任何数据。
        </p>
        <button
          type="button"
          onClick={onExport}
          disabled={exportState === "working"}
          className="mt-4 inline-flex min-h-11 items-center rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:cursor-wait disabled:opacity-60"
          data-testid="me-export"
        >
          {exportState === "working" ? "正在准备…" : "导出我的数据"}
        </button>
        {exportMessage && (
          <p role={exportState === "error" ? "alert" : "status"} className={`mt-3 text-sm ${exportState === "error" ? "text-rose-700" : "text-emerald-700"}`} data-testid="me-export-message">
            {exportMessage}
          </p>
        )}
      </section>

      <section className="mt-8 rounded-xl border border-rose-200 bg-white p-5 sm:p-6" aria-labelledby="danger-heading">
        <h2 id="danger-heading" className="text-base font-semibold text-zinc-900">危险操作</h2>
        {!deleteOpen ? (
          <>
            <p className="mt-2 text-sm leading-6 text-zinc-600">
              永久删除账户、服务器端账户资产和所有有效会话。此操作无法撤销。
            </p>
            <button
              type="button"
              onClick={() => setDeleteOpen(true)}
              className="mt-4 inline-flex min-h-11 items-center rounded-md border border-rose-300 px-4 py-2 text-sm font-medium text-rose-700 hover:bg-rose-50"
              data-testid="me-delete-open"
            >
              删除账户…
            </button>
          </>
        ) : (
          <div className="mt-4" data-testid="me-delete-confirmation">
            <p id="delete-warning" className="text-sm font-medium leading-6 text-rose-800">
              这是永久操作。删除后无法恢复账户资料、服务器收藏或现有登录会话。
            </p>
            <label htmlFor="delete-confirmation" className="mt-4 block text-sm text-zinc-700">
              输入 <span className="font-mono font-semibold">DELETE</span> 确认
            </label>
            <input
              id="delete-confirmation"
              value={deleteConfirmation}
              onChange={(event) => setDeleteConfirmation(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="delete-warning"
              className="mt-2 min-h-11 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 font-mono text-base text-zinc-900 focus:border-rose-500 focus:outline-none focus:ring-2 focus:ring-rose-200"
              data-testid="me-delete-input"
            />
            <div className="mt-4 flex flex-col-reverse gap-3 sm:flex-row">
              <button
                type="button"
                onClick={() => { setDeleteOpen(false); setDeleteConfirmation(""); setDeleteMessage(""); setDeleteState("idle"); }}
                disabled={deleteState === "working"}
                className="inline-flex min-h-11 items-center justify-center rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:opacity-60"
                data-testid="me-delete-cancel"
              >
                取消
              </button>
              <button
                type="button"
                onClick={onDeleteAccount}
                disabled={deleteConfirmation !== "DELETE" || deleteState === "working"}
                className="inline-flex min-h-11 items-center justify-center rounded-md bg-rose-700 px-4 py-2 text-sm font-medium text-white hover:bg-rose-800 disabled:cursor-not-allowed disabled:opacity-50"
                data-testid="me-delete-submit"
              >
                {deleteState === "working" ? "正在永久删除…" : "永久删除我的账户"}
              </button>
            </div>
            {deleteMessage && <p role="alert" className="mt-3 text-sm text-rose-700" data-testid="me-delete-error">{deleteMessage}</p>}
          </div>
        )}
      </section>

      <section className="mt-8 border-t border-zinc-200 pt-6" aria-labelledby="session-heading">
        <h2 id="session-heading" className="text-base font-semibold text-zinc-900">登录状态</h2>
        <button type="button" onClick={onLogout} className="mt-3 inline-flex min-h-11 items-center rounded-md border border-zinc-300 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50" data-testid="me-logout">
          退出登录
        </button>
        {logoutError && <p role="alert" className="mt-3 text-sm text-rose-700">退出失败，你仍处于登录状态，请重试。</p>}
      </section>
    </main>
  );
}
