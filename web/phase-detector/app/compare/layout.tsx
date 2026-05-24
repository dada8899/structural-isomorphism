// W12-B (session #10, 2026-05-15): /compare metadata layout.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "对比 — Phase Detector",
  description:
    "2-5 家公司并排对比：CPS 状态、共享模式匹配、30 天小时间线。URL 即可分享。",
  path: "/compare",
  ogImage: "/og/compare.png",
});

export default function CompareLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
