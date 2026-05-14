import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { Inter, Noto_Serif_SC, JetBrains_Mono } from "next/font/google";
import HistorySidebar from "@/components/HistorySidebar";
import JsonLd from "@/components/JsonLd";
import NetworkBanner from "@/components/NetworkBanner";
import TopNav from "@/components/TopNav";
import OnboardingTour from "@/components/OnboardingTour";
import CommandPaletteProvider from "@/components/CommandPaletteProvider";
import { ThemeProvider } from "@/components/ThemeProvider";
import CookieConsent from "@/components/CookieConsent";
import ManageCookiesButton from "@/components/ManageCookiesButton";
import { organizationSchema, websiteSchema } from "@/lib/seo";
import "./globals.css";

// W12-C (session #10): mobile polish.
// viewport-fit=cover lets us use env(safe-area-inset-*) for iOS notch.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  maximumScale: 5,
  userScalable: true,
  themeColor: "#F5F5F4",
};

// W3-B (session #9): self-host fonts via next/font (latin subset only).
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600", "700"],
  variable: "--font-inter",
});
const notoSerifSC = Noto_Serif_SC({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
  variable: "--font-noto-serif",
  preload: false,
});
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500"],
  variable: "--font-jetbrains-mono",
});

// W6-B: localized to zh-CN, aligned with main site brand.
export const metadata: Metadata = {
  title: {
    default: "Phase Detector — 100 家公司的状态评分",
    template: "%s — Phase Detector",
  },
  description:
    "100 家全球上市公司的状态评分，30 秒看懂：谁在崩盘边缘，谁在悄悄起飞。",
  metadataBase: new URL("https://phase.bytedance.city"),
  alternates: { canonical: "https://phase.bytedance.city/" },
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "Phase",
    statusBarStyle: "default",
  },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/icons/icon-192.png", sizes: "192x192" }],
  },
  openGraph: {
    title: "Phase Detector — 100 家公司的状态评分",
    description: "30 秒看懂一家公司当前的状态。",
    type: "website",
    siteName: "Phase Detector",
    url: "https://phase.bytedance.city/",
    images: [
      {
        url: "/og/home.png",
        width: 1200,
        height: 630,
        alt: "Phase Detector — 100 家公司的状态评分",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Phase Detector — 100 家公司的状态评分",
    description: "30 秒看懂一家公司当前的状态。",
    images: ["/og/home.png"],
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={`${inter.variable} ${notoSerifSC.variable} ${jetbrainsMono.variable}`}
    >
      <body className="min-h-screen bg-[#F5F5F4] font-sans text-zinc-900 antialiased lg:pl-60 safe-area-body dark:bg-zinc-950 dark:text-zinc-100">
        <ThemeProvider>
          <a href="#main-content" className="skip-link">
            跳到主要内容
          </a>
          {/* W12-E: SW register + offline banner. */}
          <NetworkBanner />
          <HistorySidebar />
          <header className="sticky top-0 z-[80] border-b border-zinc-200 bg-white/90 backdrop-blur safe-area-top dark:border-zinc-800 dark:bg-zinc-900/90">
            <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
              <Link
                href="/"
                className="flex items-center gap-2"
                aria-label="Phase Detector 首页"
              >
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
              <TopNav />
            </div>
          </header>
          <main id="main-content" className="mx-auto max-w-7xl px-6 py-6">
            {children}
          </main>
          <footer className="mx-auto max-w-7xl border-t border-zinc-200 px-6 py-8 text-xs text-zinc-500 safe-area-bottom dark:border-zinc-800 dark:text-zinc-400">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-4">
                <span className="font-medium text-zinc-700 dark:text-zinc-300">
                  Phase Detector
                </span>
                <Link href="/about" className="hover:text-zinc-900 dark:hover:text-white">
                  关于
                </Link>
                <Link href="/methodology" className="hover:text-zinc-900 dark:hover:text-white">
                  方法
                </Link>
                {/* W14-C: privacy + cookie controls in footer */}
                <Link href="/privacy" className="hover:text-zinc-900 dark:hover:text-white">
                  隐私
                </Link>
                <ManageCookiesButton />
                <a
                  href="https://github.com/dada8899/structural-isomorphism"
                  target="_blank"
                  rel="noopener"
                  className="hover:text-zinc-900 dark:hover:text-white"
                >
                  GitHub ↗
                </a>
                <a
                  href="https://beta.structural.bytedance.city/classes"
                  target="_blank"
                  rel="noopener"
                  className="hover:text-zinc-900 dark:hover:text-white"
                >
                  Structural ↗
                </a>
              </div>
              <div className="text-zinc-400 dark:text-zinc-500">
                研究预览 · 不是投资建议 · AI 抽取的数据，请独立核实
              </div>
            </div>
          </footer>
          {/* W12-D onboarding tour. */}
          <OnboardingTour />
          {/* W13-E Cmd+K command palette. */}
          <CommandPaletteProvider />
          {/* W14-C: cookie consent banner. Renders nothing if already
              answered or DNT. Plausible is loaded by this component, not
              via a <Script> tag, so it's gated behind consent. */}
          <CookieConsent />
          {/* W12-B site-wide structured data: WebSite + Organization. */}
          <JsonLd id="ld-website" schema={websiteSchema()} />
          <JsonLd id="ld-organization" schema={organizationSchema()} />
        </ThemeProvider>
      </body>
    </html>
  );
}
