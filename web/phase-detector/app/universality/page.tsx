"use client";

// W10-E /universality — class explorer.
//
// Lists every universality class (loaded from the YAML taxonomy on the
// backend) as a searchable + filterable card. Click → detail page.
//
// Filters:
//   * free-text query against class_id + display_name + definition
//   * status filter (well-established / emerging / speculative / all)
//
// Design language matches the rest of the app: white cards, restrained
// palette, mobile-responsive grid. Sort: well-established → emerging →
// speculative → unknown, then alphabetical.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fetchUniversalityClasses } from "@/lib/api";
import type { UniversalityClassCard } from "@/lib/types";

type StatusFilter =
  | "all"
  | "well-established"
  | "emerging"
  | "speculative"
  | "unknown";

const STATUS_LABEL: Record<StatusFilter, string> = {
  all: "全部",
  "well-established": "已确立",
  emerging: "新兴",
  speculative: "推测中",
  unknown: "未分类",
};

const STATUS_BADGE: Record<string, string> = {
  "well-established": "bg-emerald-100 text-emerald-800 ring-emerald-200",
  emerging: "bg-amber-100 text-amber-800 ring-amber-200",
  speculative: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  unknown: "bg-zinc-50 text-zinc-500 ring-zinc-200",
};

function statusBadge(status: string): string {
  return STATUS_BADGE[status] ?? STATUS_BADGE.unknown;
}

function ClassCard({ cls }: { cls: UniversalityClassCard }) {
  return (
    <Link
      href={`/universality/${encodeURIComponent(cls.class_id)}`}
      data-testid="universality-class-card"
      data-class-id={cls.class_id}
      className="group flex flex-col gap-3 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition hover:border-zinc-300 hover:shadow-md"
    >
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-zinc-900 group-hover:text-zinc-700">
            {cls.display_name}
          </h3>
          {cls.display_name_zh && cls.display_name_zh !== cls.display_name && (
            <p className="truncate text-xs text-zinc-500">{cls.display_name_zh}</p>
          )}
        </div>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ring-1 ring-inset ${statusBadge(
            cls.status,
          )}`}
        >
          {cls.status}
        </span>
      </header>

      <p className="line-clamp-3 text-xs leading-relaxed text-zinc-600">
        {cls.definition || "(暂无定义)"}
      </p>

      {cls.exponent_band.length > 0 && (
        <ul className="space-y-0.5">
          {cls.exponent_band.slice(0, 2).map((band, i) => (
            <li
              key={i}
              className="line-clamp-1 text-[11px] font-mono text-zinc-500"
              title={band}
            >
              · {band}
            </li>
          ))}
        </ul>
      )}

      <footer className="mt-auto flex items-center justify-between text-[11px] text-zinc-400">
        <span>{cls.evidence_count} 个实证系统</span>
        <span className="text-zinc-500 group-hover:text-zinc-700">查看 →</span>
      </footer>
    </Link>
  );
}

export default function UniversalityExplorerPage() {
  const [classes, setClasses] = useState<UniversalityClassCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");

  useEffect(() => {
    let cancelled = false;
    fetchUniversalityClasses()
      .then((r) => {
        if (cancelled) return;
        setClasses(r.classes ?? []);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "fetch failed");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return classes.filter((c) => {
      if (status !== "all" && c.status !== status) return false;
      if (!q) return true;
      return (
        c.class_id.toLowerCase().includes(q) ||
        c.display_name.toLowerCase().includes(q) ||
        (c.display_name_zh ?? "").toLowerCase().includes(q) ||
        c.definition.toLowerCase().includes(q)
      );
    });
  }, [classes, query, status]);

  // Stat counts for filter chips
  const counts = useMemo(() => {
    const m: Record<string, number> = { all: classes.length };
    for (const c of classes) m[c.status] = (m[c.status] ?? 0) + 1;
    return m;
  }, [classes]);

  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold text-zinc-900">普适类浏览</h1>
        <p className="max-w-3xl text-sm text-zinc-600">
          所有跨领域同构的结构模式。点开任意一条看完整定义、关键不变量、
          实证系统、文献来源，以及当前匹配的公司。
        </p>
      </header>

      <section className="space-y-3 rounded-md border border-zinc-200 bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索类名 / 定义 / 关键词…"
            className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm placeholder:text-zinc-400 focus:border-zinc-500 focus:outline-none focus:ring-1 focus:ring-zinc-500 sm:max-w-md"
            data-testid="universality-search-input"
          />
          <div className="flex flex-wrap gap-1">
            {(Object.keys(STATUS_LABEL) as StatusFilter[]).map((s) => {
              const active = status === s;
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStatus(s)}
                  className={`rounded-md px-2.5 py-1 text-xs ring-1 ring-inset transition ${
                    active
                      ? "bg-zinc-900 text-white ring-zinc-900"
                      : "bg-white text-zinc-700 ring-zinc-200 hover:bg-zinc-50"
                  }`}
                  data-testid={`universality-filter-${s}`}
                >
                  {STATUS_LABEL[s]}
                  {counts[s] !== undefined && (
                    <span className="ml-1 text-[10px] opacity-70">
                      {counts[s]}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {loading && <div className="text-sm text-zinc-500">加载中…</div>}

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          加载失败：{error}
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-md border border-dashed border-zinc-300 bg-white p-10 text-center text-sm text-zinc-500">
          没有匹配到普适类。试试清空筛选或换个关键词。
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <div
          data-testid="universality-grid"
          data-card-count={filtered.length}
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        >
          {filtered.map((c) => (
            <ClassCard key={c.class_id} cls={c} />
          ))}
        </div>
      )}

      <footer className="border-t border-zinc-200 pt-4 text-xs text-zinc-500">
        想并排对比公司？{" "}
        <Link href="/compare" className="text-zinc-900 underline hover:text-zinc-700">
          打开 /compare
        </Link>
        。
      </footer>
    </div>
  );
}
