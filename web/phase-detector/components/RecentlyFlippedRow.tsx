"use client";

import Link from "next/link";
import { CPS_ICON, CPS_LABEL_ZH } from "@/lib/labels";
import type { Company } from "@/lib/types";

// W3-C session #9: lightweight first-fold row showing companies that have
// already transitioned (critical_point_state = post_critical_transition).
// Mirrors the structure of the "approaching critical" signals block above
// it, but with a different visual tone (cool zinc instead of warm amber)
// — these are post-event retrospectives, not live signals.
//
// Empty handling: parent passes [] when BE has no flipped data; we render
// nothing (no fake placeholders).
export function RecentlyFlippedRow({ companies }: { companies: Company[] }) {
  if (!companies || companies.length === 0) return null;

  return (
    <section
      aria-labelledby="recently-flipped-heading"
      className="rounded-xl border border-zinc-200 bg-zinc-50/60 p-5"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2
          id="recently-flipped-heading"
          className="text-base font-semibold tracking-tight text-zinc-900"
        >
          <span aria-hidden="true">{CPS_ICON.post_critical_transition} </span>
          最近翻过去了 · {companies.length} 家公司已完成状态翻转
        </h2>
      </div>
      <p className="mb-4 text-sm text-zinc-700">
        下面这些公司已经
        <strong>从临界点翻向新状态</strong>：可以作为复盘样本，看翻转前后的指标变化。
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {companies.map((c) => (
          <Link
            key={c.ticker}
            href={`/company/${encodeURIComponent(c.ticker)}`}
            className="rounded-lg border border-zinc-200 bg-white p-3 transition hover:border-zinc-400 hover:shadow-sm"
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="font-semibold tracking-tight text-zinc-900">
                {c.ticker}
              </span>
              <span className="inline-flex items-center gap-1 text-xs text-zinc-600">
                <span aria-hidden="true">
                  {CPS_ICON[c.critical_point_state] ?? ""}
                </span>
                <span>
                  {CPS_LABEL_ZH[c.critical_point_state] ?? c.critical_point_state}
                </span>
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-zinc-600">{c.tldr}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}
