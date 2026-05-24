// W12-B (session #10, 2026-05-15): /company/[ticker] dynamic metadata layout.
//
// Dynamic metadata: title uses the uppercased ticker; description copy
// stays template. Per-company live data lives in the page body — including
// the Article JSON-LD which is emitted client-side once data is fetched.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ ticker: string }> | { ticker: string };
}): Promise<Metadata> {
  const resolved = await Promise.resolve(params);
  const ticker = (resolved.ticker ?? "").toUpperCase();
  return buildMetadata({
    title: `${ticker} — 状态评分 — Phase Detector`,
    description: `${ticker} 当前的相位评分 + 关键指标 + 30 天轨迹。AI 抽取的公开资料，每条都有原文链接。`,
    path: `/company/${ticker}`,
    ogType: "article",
    ogImage: "/og/company.png",
  });
}

export default function CompanyDetailLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <>{children}</>;
}
