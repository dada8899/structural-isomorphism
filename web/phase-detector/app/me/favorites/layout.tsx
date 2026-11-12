import type { Metadata } from "next";
import type { ReactNode } from "react";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: "我的收藏",
  description: "查看和管理当前账户收藏的冻结公司研究快照。",
  path: "/me/favorites",
  noindex: true,
});

export default function FavoritesLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
