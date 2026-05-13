"use client";

// W8-D: waitlist signup form.
//
// Submits to {API_BASE}/api/waitlist (form-encoded so non-JSON consumers
// like the main static site can use the same endpoint). On success →
// router.push("/thank-you"). On dup → friendly inline message.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Events, trackEvent } from "@/lib/analytics";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

type Placement = "hero" | "footer" | "inline";

interface Props {
  placement?: Placement;
  source?: string;
  /** Override the post-submit redirect (default: "/thank-you"). */
  redirectTo?: string;
  className?: string;
}

type Status = "idle" | "loading" | "ok" | "duplicate" | "error";

export function WaitlistForm({
  placement = "inline",
  source = "phase_detector",
  redirectTo = "/thank-you",
  className,
}: Props) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (status === "loading") return;
    const trimmed = email.trim();
    if (!trimmed) {
      setStatus("error");
      setErrorMsg("请输入邮箱");
      return;
    }

    setStatus("loading");
    setErrorMsg(null);

    try {
      const form = new URLSearchParams();
      form.set("email", trimmed);
      form.set("source", source);
      form.set("placement", placement);
      if (typeof document !== "undefined" && document.referrer) {
        form.set("referrer", document.referrer);
      }

      const res = await fetch(`${API_BASE}/api/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
      });

      if (!res.ok) {
        const body = await res.text().catch(() => "");
        trackEvent(Events.WaitlistError, { source, placement, status: res.status });
        setStatus("error");
        setErrorMsg(
          res.status === 422 ? "邮箱格式不正确" : `提交失败：${res.status} ${body || ""}`
        );
        return;
      }

      const data = (await res.json()) as { created?: boolean; msg?: string };
      if (data.created) {
        trackEvent(Events.WaitlistSignup, { source, placement });
        setStatus("ok");
        // Defer router.push so the success state flashes (UX nicety).
        setTimeout(() => router.push(redirectTo), 250);
      } else {
        trackEvent(Events.WaitlistDuplicate, { source, placement });
        setStatus("duplicate");
      }
    } catch (err) {
      trackEvent(Events.WaitlistError, {
        source,
        placement,
        status: "network",
      });
      setStatus("error");
      setErrorMsg(err instanceof Error ? err.message : "网络错误");
    }
  }

  const submitting = status === "loading";

  return (
    <form
      onSubmit={onSubmit}
      className={
        className ??
        "rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm"
      }
      noValidate
      aria-labelledby="waitlist-heading"
    >
      <h3
        id="waitlist-heading"
        className="text-lg font-semibold tracking-tight text-zinc-900"
        style={{ fontFamily: "'Noto Serif SC', serif" }}
      >
        每周一封《结构信号》→
      </h3>
      <p className="mt-1 text-sm text-zinc-600">
        每周日推送：本周哪些公司刚走到临界附近、哪些回到稳态，附一个深度案例。
        <span className="ml-1 text-xs text-zinc-400">
          免费 · 一封邮件 · 可随时退订
        </span>
      </p>

      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor={`waitlist-email-${placement}`}>
          Email
        </label>
        <input
          id={`waitlist-email-${placement}`}
          type="email"
          name="email"
          autoComplete="email"
          required
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting || status === "ok"}
          className="flex-1 rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm focus:border-zinc-900 focus:outline-none focus:ring-1 focus:ring-zinc-900 disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={submitting || status === "ok"}
          className="inline-flex items-center justify-center gap-1 rounded-md bg-zinc-900 px-5 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "提交中…" : status === "ok" ? "已加入 ✓" : "加入"}
        </button>
      </div>

      {/* Status messages */}
      {status === "duplicate" && (
        <p className="mt-3 text-xs text-zinc-600" role="status">
          ✓ 这个邮箱已经在名单上了。下次发刊见。
        </p>
      )}
      {status === "error" && errorMsg && (
        <p className="mt-3 text-xs text-red-600" role="alert">
          {errorMsg}
        </p>
      )}
      {status === "ok" && (
        <p className="mt-3 text-xs text-emerald-700" role="status">
          ✓ 已加入，正在跳转…
        </p>
      )}

      <p className="mt-3 text-[11px] text-zinc-400">
        不会用于其他用途。退订只需点击邮件页脚的链接。
      </p>
    </form>
  );
}
