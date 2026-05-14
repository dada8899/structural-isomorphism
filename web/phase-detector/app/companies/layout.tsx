// W12-B (session #10, 2026-05-15): /companies metadata layout.
//
// page.tsx is a client component (uses useRouter, useEffect, useState),
// so it can't export `metadata` directly. This server-component layout
// holds the per-route SEO metadata and renders children unchanged.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "公司清单 — Phase Detector",
  description:
    "100+ 家上市公司的状态评分一览：按动力学家族 / 临界点状态 / 行业筛选。每条都有可追溯的指标和原始资料链接。",
  path: "/companies",
  ogImage: "/og/companies.png",
});

export default function CompaniesLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
