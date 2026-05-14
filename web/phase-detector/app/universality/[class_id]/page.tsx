"use client";

// W10-E /universality/[class_id] — class detail page.
//
// Pulls one universality class from /api/universality/classes/<id>,
// joins with /api/universality/companies/<id> for the live ticker
// list. Renders the canonical fields from the YAML taxonomy:
//
//   * Full definition (hub_phenomenon)
//   * Pre-registered exponent band (key_invariants)
//   * Cross-domain analogues (prototypes + evidence_systems)
//   * Vuong / KS / LR test summaries (inline in evidence text)
//   * Companies currently in this pattern (from DB)
//   * Negative examples + edge cases
//   * References / citations
//
// CTA: "compare top 5 in this class" → /compare?tickers=<...>

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { UniversalityAnalogueMap } from "@/components/UniversalityAnalogueMap";
import {
  fetchUniversalityClassDetail,
  fetchUniversalityCompanies,
} from "@/lib/api";
import {
  CPS_DOT,
  CPS_LABEL_ZH,
  DYNAMICS_LABEL_ZH,
  SECTOR_LABEL_ZH,
} from "@/lib/labels";
import type {
  UniversalityClassDetail,
  UniversalityCompaniesResponse,
} from "@/lib/types";

const STATUS_BADGE: Record<string, string> = {
  "well-established": "bg-emerald-100 text-emerald-800 ring-emerald-200",
  emerging: "bg-amber-100 text-amber-800 ring-amber-200",
  speculative: "bg-zinc-100 text-zinc-700 ring-zinc-200",
  unknown: "bg-zinc-50 text-zinc-500 ring-zinc-200",
};

function Section({
  title,
  description,
  children,
  testid,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  testid?: string;
}) {
  return (
    <section
      data-testid={testid}
      className="space-y-3 rounded-lg border border-zinc-200 bg-white p-5"
    >
      <header>
        <h2 className="text-base font-semibold text-zinc-900">{title}</h2>
        {description && (
          <p className="text-xs text-zinc-500">{description}</p>
        )}
      </header>
      <div>{children}</div>
    </section>
  );
}

function CompaniesPanel({
  detail,
  companies,
  loading,
}: {
  detail: UniversalityClassDetail;
  companies: UniversalityCompaniesResponse | null;
  loading: boolean;
}) {
  const list = companies?.companies ?? [];
  const topFive = list.slice(0, 5).map((c) => c.ticker);
  const compareHref =
    topFive.length >= 2
      ? `/compare?tickers=${topFive.join(",")}`
      : null;

  return (
    <Section
      title="当前匹配的公司"
      description="数据库中标记为该普适类的公司，按抽取置信度排序"
      testid="universality-companies-panel"
    >
      {loading && <div className="text-sm text-zinc-500">加载中…</div>}
      {!loading && list.length === 0 && (
        <p className="text-sm text-zinc-500">
          暂无公司匹配此类。随着数据集扩展会自动出现。
        </p>
      )}
      {!loading && list.length > 0 && (
        <>
          <ul className="divide-y divide-zinc-100">
            {list.slice(0, 12).map((c) => {
              const conf = c.extraction_confidence ?? 0;
              const sectorLabel = c.sector
                ? SECTOR_LABEL_ZH[c.sector] ?? c.sector
                : null;
              return (
                <li key={c.ticker}>
                  <Link
                    href={`/company/${encodeURIComponent(c.ticker)}`}
                    className="flex items-center justify-between gap-3 py-2 hover:bg-zinc-50"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      {c.critical_point_state && (
                        <span
                          aria-hidden="true"
                          className={`inline-block h-2 w-2 rounded-full ${
                            CPS_DOT[c.critical_point_state] ?? "bg-zinc-300"
                          }`}
                        />
                      )}
                      <span className="font-medium text-zinc-900">
                        {c.ticker}
                      </span>
                      <span className="truncate text-xs text-zinc-500">
                        {c.name}
                      </span>
                    </div>
                    <div className="flex shrink-0 items-center gap-2 text-[11px] text-zinc-400">
                      {sectorLabel && (
                        <span className="rounded bg-zinc-100 px-1.5 py-0.5">
                          {sectorLabel}
                        </span>
                      )}
                      <span>{(conf * 100).toFixed(0)}%</span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
          {compareHref && (
            <div className="mt-3 border-t border-zinc-100 pt-3 text-right">
              <Link
                href={compareHref}
                className="inline-flex items-center gap-1 rounded-md bg-zinc-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-zinc-700"
                data-testid="universality-compare-cta"
              >
                并排对比前 5 家 →
              </Link>
            </div>
          )}
        </>
      )}
    </Section>
  );
}

export default function UniversalityDetailPage() {
  const params = useParams<{ class_id: string }>();
  const classId = params?.class_id
    ? decodeURIComponent(
        Array.isArray(params.class_id) ? params.class_id[0] : params.class_id,
      )
    : "";

  const [detail, setDetail] = useState<UniversalityClassDetail | null>(null);
  const [companies, setCompanies] =
    useState<UniversalityCompaniesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingCompanies, setLoadingCompanies] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!classId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchUniversalityClassDetail(classId)
      .then((d) => {
        if (cancelled) return;
        setDetail(d);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "fetch failed");
        setLoading(false);
      });
    setLoadingCompanies(true);
    fetchUniversalityCompanies(classId)
      .then((r) => {
        if (cancelled) return;
        setCompanies(r);
        setLoadingCompanies(false);
      })
      .catch(() => {
        if (cancelled) return;
        setCompanies(null);
        setLoadingCompanies(false);
      });
    return () => {
      cancelled = true;
    };
  }, [classId]);

  const statusBadgeClass = useMemo(
    () => STATUS_BADGE[detail?.status ?? "unknown"] ?? STATUS_BADGE.unknown,
    [detail],
  );

  if (loading) {
    return (
      <div className="space-y-4">
        {/* W12-A: axe `page-has-heading-one` — ensure every loading state still
         * exposes an <h1> landmark so screen readers can announce the page. */}
        <h1 className="sr-only">普适类详情加载中</h1>
        <div className="text-xs text-zinc-500">
          <Link href="/universality" className="hover:text-zinc-900">
            ← 返回普适类列表
          </Link>
        </div>
        <div className="text-sm text-zinc-500" role="status" aria-live="polite">
          加载中…
        </div>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <h1 className="sr-only">普适类未找到</h1>
        <div className="text-xs text-zinc-500">
          <Link href="/universality" className="hover:text-zinc-900">
            ← 返回普适类列表
          </Link>
        </div>
        <div
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
          role="alert"
        >
          没找到这个普适类：{classId}
          {error && <div className="mt-1 text-xs text-amber-700">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <nav className="text-xs text-zinc-500">
        <Link href="/universality" className="hover:text-zinc-900">
          ← 普适类列表
        </Link>
      </nav>

      <header
        className="space-y-3 rounded-lg border border-zinc-200 bg-white p-5"
        data-testid="universality-detail-header"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-zinc-900">
              {detail.display_name}
            </h1>
            {detail.display_name_zh &&
              detail.display_name_zh !== detail.display_name && (
                <p className="text-sm text-zinc-600">{detail.display_name_zh}</p>
              )}
            <p className="mt-1 font-mono text-[11px] text-zinc-400">
              {detail.class_id}
            </p>
          </div>
          <span
            className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-medium uppercase ring-1 ring-inset ${statusBadgeClass}`}
          >
            {detail.status}
          </span>
        </div>
        {detail.definition && (
          <p className="text-sm leading-relaxed text-zinc-700">
            {detail.definition}
          </p>
        )}
      </header>

      {/* W11-D: cross-domain analogue map — force-directed graph of evidence
          systems + prototypes colored by domain. Renders above the canonical
          text sections so the visual relationship is the first thing readers
          see after the header. */}
      <Section
        title="跨领域类比图"
        description="该类的实证系统按所属领域聚合；点击节点可跳转到对应公司或证据"
        testid="analogue-map-section"
      >
        <UniversalityAnalogueMap detail={detail} />
      </Section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {detail.key_invariants.length > 0 && (
            <Section
              title="预登记的关键不变量"
              description="判断系统是否属于此类的核心标志"
              testid="universality-invariants"
            >
              <ul className="space-y-2">
                {detail.key_invariants.map((inv, i) => (
                  <li
                    key={i}
                    className="rounded bg-zinc-50 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-700"
                  >
                    {inv}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.shared_equation && (
            <Section
              title="共享方程"
              description="该类系统的主方程或临界条件"
              testid="universality-equation"
            >
              <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-zinc-50 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-700">
                {detail.shared_equation}
              </pre>
            </Section>
          )}

          {detail.evidence_systems.length > 0 && (
            <Section
              title="实证系统（跨领域类比）"
              description="经过验证或候选的实例 — 含 Vuong / KS / LR 检验结果（如有）"
              testid="universality-evidence"
            >
              <ul className="space-y-3">
                {detail.evidence_systems.map((ev, i) => (
                  <li
                    key={i}
                    className="rounded-md border border-zinc-100 bg-zinc-50/50 p-3"
                  >
                    <div className="text-sm font-medium text-zinc-900">
                      {ev.phenomenon}
                    </div>
                    {ev.evidence && (
                      <p className="mt-1 text-xs leading-relaxed text-zinc-600">
                        {ev.evidence}
                      </p>
                    )}
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-400">
                      {ev.verified_at && <span>状态：{ev.verified_at}</span>}
                      {ev.paper && (
                        <span className="font-mono">{ev.paper}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.prototypes.length > 0 && (
            <Section title="经典原型" testid="universality-prototypes">
              <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {detail.prototypes.map((p, i) => (
                  <li
                    key={i}
                    className="rounded bg-zinc-50 px-2 py-1.5 text-xs text-zinc-700"
                  >
                    · {p}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.negative_examples.length > 0 && (
            <Section
              title="反例（看起来像但其实不是）"
              description="生成机制不同 → 不归入此类"
              testid="universality-negatives"
            >
              <ul className="space-y-2">
                {detail.negative_examples.map((n, i) => (
                  <li key={i} className="text-xs leading-relaxed">
                    <span className="font-medium text-zinc-900">
                      {n.phenomenon}
                    </span>
                    <span className="text-zinc-500"> — {n.reason}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.edge_cases.length > 0 && (
            <Section
              title="边界争议"
              description="社区仍在讨论的归类问题"
              testid="universality-edges"
            >
              <ul className="space-y-2">
                {detail.edge_cases.map((e, i) => (
                  <li key={i} className="text-xs leading-relaxed">
                    <span className="font-medium text-zinc-900">
                      {e.phenomenon}
                    </span>
                    <span className="text-zinc-500"> — {e.debate}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {detail.references.length > 0 && (
            <Section
              title="引用文献"
              description={`数据来源：${detail.source}`}
              testid="universality-references"
            >
              <ul className="space-y-1.5">
                {detail.references.map((r, i) => (
                  <li key={i} className="text-[11px] text-zinc-600">
                    {r}
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>

        <aside className="space-y-6">
          <CompaniesPanel
            detail={detail}
            companies={companies}
            loading={loadingCompanies}
          />

          <Section title="进一步探索" testid="universality-further">
            <ul className="space-y-2 text-xs">
              <li>
                <Link
                  href="/compare"
                  className="text-zinc-700 underline hover:text-zinc-900"
                >
                  在 /compare 并排对比公司
                </Link>
              </li>
              <li>
                <Link
                  href="/universality"
                  className="text-zinc-700 underline hover:text-zinc-900"
                >
                  浏览全部普适类
                </Link>
              </li>
              <li>
                <Link
                  href="/methodology"
                  className="text-zinc-700 underline hover:text-zinc-900"
                >
                  了解分类方法
                </Link>
              </li>
            </ul>
          </Section>
        </aside>
      </div>
    </div>
  );
}
