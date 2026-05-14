// W12-B (session #10, 2026-05-15): /universality archive metadata layout.
//
// Wraps the client-rendered class explorer. The dynamic per-class detail
// page also lives under this segment; it has its own layout.tsx for
// per-class metadata.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "普适类清单 — Phase Detector",
  description:
    "26+ 个跨域普适类：每一类背后是同一组方程、同一族不变量。点开任意一类，看哪些公司当下处在这个模式里。",
  path: "/universality",
  ogImage: "/og/universality.png",
});

export default function UniversalityLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
