import type { Metadata } from "next";
import { Suspense } from "react";
import Link from "next/link";
import { Breadcrumb } from "@/components/Breadcrumb";
import { CheckoutSuccessBanner } from "@/components/CheckoutSuccessBanner";
import { ShareButtons } from "@/components/ShareButtons";

export const metadata: Metadata = {
  title: "已加入名单 — Phase Detector",
  description: "你已加入《结构信号》订阅。每周日推送本周公司状态变化。",
  // Block indexing so this page does not show up in search.
  robots: { index: false, follow: false },
};

// W8-D: thank-you page after waitlist signup.
// Server component (no useState etc.) — share buttons live in a small client component.

const SHARE_URL = "https://phase.bytedance.city";
const SHARE_TEXT =
  "我刚订阅了《结构信号》——100 家全球公司的状态评分，用解释地震和银行挤兑的同一套数学。每周日推送。";

export default function ThankYouPage() {
  return (
    <article className="mx-auto max-w-2xl">
      <Breadcrumb items={[{ label: "首页", href: "/" }, { label: "已加入名单" }]} />

      {/* W10-B: tier-specific success banner if user came from mock checkout. */}
      <Suspense fallback={null}>
        <CheckoutSuccessBanner />
      </Suspense>

      <h1
        className="mb-3 text-3xl font-semibold tracking-tight text-zinc-900 md:text-4xl"
        style={{ fontFamily: "'Noto Serif SC', serif" }}
      >
        已加入。
      </h1>

      <p className="mb-3 text-base leading-relaxed text-zinc-700">
        下次发刊是<strong>本周日 22:00 (Asia/Shanghai)</strong>。内容覆盖：
      </p>
      <ul className="mb-6 list-disc space-y-1 pl-6 text-sm text-zinc-700">
        <li>本周新走到「临界附近」的公司（每个附一句解释）</li>
        <li>本周回到「稳态」的公司</li>
        <li>一个深度案例（约 200 字）</li>
        <li>常见问题 + 推荐阅读</li>
      </ul>

      <section
        aria-labelledby="share-heading"
        className="mb-8 rounded-xl border border-zinc-200 bg-white p-5"
      >
        <h2
          id="share-heading"
          className="mb-3 text-sm font-semibold uppercase tracking-wider text-zinc-500"
        >
          顺手分享给一个朋友 →
        </h2>
        <p className="mb-3 text-sm text-zinc-600">
          如果你觉得有用，告诉一个会感兴趣的朋友。复制链接或一键分享：
        </p>
        <ShareButtons url={SHARE_URL} text={SHARE_TEXT} />
      </section>

      <section className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Link
          href="/"
          className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-300 hover:shadow-sm"
        >
          <div className="text-sm font-semibold text-zinc-900">回到首页</div>
          <p className="mt-1 text-xs text-zinc-500">看 100 家公司的当前状态</p>
        </Link>
        <Link
          href="/methodology"
          className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-300 hover:shadow-sm"
        >
          <div className="text-sm font-semibold text-zinc-900">方法论</div>
          <p className="mt-1 text-xs text-zinc-500">共享模式 + 状态判定怎么来</p>
        </Link>
        <Link
          href="/about"
          className="rounded-xl border border-zinc-200 bg-white p-4 transition hover:border-zinc-300 hover:shadow-sm"
        >
          <div className="text-sm font-semibold text-zinc-900">关于</div>
          <p className="mt-1 text-xs text-zinc-500">这个产品 / 研究预览</p>
        </Link>
      </section>

      <p className="text-xs text-zinc-400">
        如果一周后没收到邮件，请检查垃圾邮件文件夹 — 或者在
        <a
          href="https://github.com/dada8899/structural-isomorphism/issues"
          target="_blank"
          rel="noopener"
          className="ml-1 underline-offset-2 hover:underline"
        >
          GitHub Issues
        </a>
        告诉我们。
      </p>
    </article>
  );
}
