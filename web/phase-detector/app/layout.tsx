import type { Metadata } from "next";
import Link from "next/link";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "Phase Detector — Structural Isomorphism",
  description:
    "Screen companies by structural dynamics family and critical-point state.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white font-sans text-gray-900 antialiased">
        <header className="sticky top-0 z-10 border-b border-gray-200 bg-white/85 backdrop-blur">
          <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
            <Link href="/" className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full bg-amber-500" />
              <span className="text-sm font-semibold tracking-tight">
                Phase Detector
              </span>
              <span className="ml-2 hidden text-xs text-gray-500 sm:inline">
                Structural Isomorphism · D1
              </span>
            </Link>
            <nav className="flex items-center gap-5 text-sm text-gray-600">
              <Link href="/" className="hover:text-gray-900">
                Screener
              </Link>
              <a
                href="https://structural.bytedance.city"
                target="_blank"
                rel="noopener"
                className="hover:text-gray-900"
              >
                Main site
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-6">{children}</main>
        <footer className="mx-auto max-w-7xl px-6 py-10 text-xs text-gray-400">
          Phase Detector v0.1 · Research preview · Not investment advice.
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
