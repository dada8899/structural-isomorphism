import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import HistorySidebar from "@/components/HistorySidebar";
import "./globals.css";

// W6-B: localized to zh-CN, aligned with main site brand (双圆 logo, Inter + Noto Serif SC).
// PR-1 (2026-05-14): metadata copy rewritten plain-Chinese, jargon stripped.
export const metadata: Metadata = {
  title: "Phase Detector — 100 家公司的状态评分",
  description:
    "100 家全球上市公司的状态评分，30 秒看懂：谁在崩盘边缘，谁在悄悄起飞。用解释地震、银行挤兑的同一套数学。",
  metadataBase: new URL("https://phase.bytedance.city"),
  openGraph: {
    title: "Phase Detector — 100 家公司的状态评分",
    description: "30 秒看懂一家公司当前的状态：稳态、临界附近、失控通道、已翻转。",
    type: "website",
    siteName: "Phase Detector",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <head>
        {/* W6-B: Google Fonts preload (Inter + Noto Serif SC) — matches main site. */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Serif+SC:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
        />
      </head>
      <body className="min-h-screen bg-[#F5F5F4] font-sans text-zinc-900 antialiased lg:pl-60">
        <a href="#main-content" className="skip-link">
          跳到主要内容
        </a>
        <HistorySidebar />
        <header className="sticky top-0 z-[80] border-b border-zinc-200 bg-white/90 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="flex items-center gap-2" aria-label="Phase Detector 首页">
              {/* W6-B: double-circle mark — same as main site (Structural logo). */}
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="6" cy="6" r="3" />
                <circle cx="18" cy="18" r="3" />
                <path d="M8.5 8.5l7 7" />
              </svg>
              <span className="text-sm font-semibold tracking-tight">
                Phase Detector
              </span>
              <span className="ml-2 hidden text-xs text-zinc-500 sm:inline">
                公司状态评分
              </span>
            </Link>
            <nav
              className="flex items-center gap-5 text-sm text-zinc-600"
              aria-label="主导航"
            >
              <Link href="/" className="hover:text-zinc-900">
                公司表
              </Link>
              <Link href="/methodology" className="hover:text-zinc-900">
                方法
              </Link>
              <Link href="/about" className="hover:text-zinc-900">
                关于
              </Link>
              <a
                href="https://structural.bytedance.city"
                target="_blank"
                rel="noopener"
                className="hover:text-zinc-900"
              >
                Structural ↗
              </a>
            </nav>
          </div>
        </header>
        <main id="main-content" className="mx-auto max-w-7xl px-6 py-6">
          {children}
        </main>
        <footer className="mx-auto max-w-7xl border-t border-zinc-200 px-6 py-8 text-xs text-zinc-500">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-4">
              <span className="font-medium text-zinc-700">
                Phase Detector
              </span>
              <Link href="/about" className="hover:text-zinc-900">
                关于
              </Link>
              <Link href="/methodology" className="hover:text-zinc-900">
                方法
              </Link>
              <a
                href="https://github.com/dada8899/structural-isomorphism"
                target="_blank"
                rel="noopener"
                className="hover:text-zinc-900"
              >
                GitHub ↗
              </a>
              <a
                href="https://structural.bytedance.city"
                target="_blank"
                rel="noopener"
                className="hover:text-zinc-900"
              >
                Structural ↗
              </a>
            </div>
            <div className="text-zinc-400">
              研究预览 · 不是投资建议 · AI 抽取的数据，请独立核实
            </div>
          </div>
        </footer>
        {/* Plausible analytics (W4-B G3, 2026-05-13). */}
        <Script
          defer
          data-domain="phase.bytedance.city"
          src="https://plausible.bytedance.city/js/script.js"
          strategy="afterInteractive"
        />
      </body>
    </html>
  );
}
