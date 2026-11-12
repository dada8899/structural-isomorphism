import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "对比 — Structural Labs · Phase",
  description:
    "2-5 家公司并排对比：CPS 状态、共享模式匹配、30 天小时间线。URL 即可分享。",
  path: "/compare",
  ogImage: "/og/compare.png",
});

export default function CompareLayout({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-zinc-900">公司对比</h1>
        <p className="max-w-3xl text-sm text-zinc-600">
          一行排开 2-5 家公司，并排看它们的当前状态、命中的普适模式、近 30 日轨迹。
          可以从地址栏拷贝分享。
        </p>
      </header>
      {children}
    </div>
  );
}
