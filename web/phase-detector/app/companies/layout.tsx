// W12-B (session #10, 2026-05-15): /companies metadata layout.
//
// page.tsx is a client component (uses useRouter, useEffect, useState),
// so it can't export `metadata` directly. This server-component layout
// holds the per-route SEO metadata and renders children unchanged.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "公司冻结快照 — Structural Labs · Phase",
  description:
    "597 个 demo ticker 的冻结结构研究快照：可筛选、附来源、公开 NULL 回测，不提供预测能力。",
  path: "/companies",
  ogImage: "/og/companies.png",
});

export default function CompaniesLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
