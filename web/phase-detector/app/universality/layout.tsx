// W12-B (session #10, 2026-05-15): /universality archive metadata layout.
//
// Wraps the client-rendered class explorer. The dynamic per-class detail
// page also lives under this segment; it has its own layout.tsx for
// per-class metadata.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "普适类候选 — Structural Labs · Phase",
  description:
    "冻结快照中的跨域结构候选：查看定义、证据、反例与来源；不代表外部复现，也不提供预测能力。",
  path: "/universality",
  ogImage: "/og/universality.png",
});

export default function UniversalityLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
