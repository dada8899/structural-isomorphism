// W12-B (session #10, 2026-05-15): /universality/[class_id] dynamic metadata.
//
// Generates per-class title + description from the class_id slug. We don't
// fetch the full class detail at build/request time here (would add a DB
// dep to a metadata function); instead we humanize the slug and let the
// page body fill in the canonical data. This is enough for crawler hints
// + OG card; rich-result eligibility comes from the page-level JSON-LD.

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ class_id: string }> | { class_id: string };
}): Promise<Metadata> {
  const resolved = await Promise.resolve(params);
  const id = resolved.class_id ?? "";
  const human = id
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase()) || "Class";
  return buildMetadata({
    title: `${human} — 普适类详情 — Phase Detector`,
    description: `普适类 ${human} 的定义、不变量、跨域类比，以及当前归入这类的上市公司。`,
    path: `/universality/${id}`,
    ogType: "article",
    ogImage: "/og/universality.png",
  });
}

export default function UniversalityDetailLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <>{children}</>;
}
