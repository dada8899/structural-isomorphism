"use client";

// PD-EWS Leaderboard — the new primary screener experience.
//
// Drives off the real CSD signal (`/api/ews/leaderboard`) rather than the
// LLM-vibe `/screener`. Two-market aware (US / HK / ALL), defaults to
// "approaching + at + post" sort so users see what's *actually moving*
// first, not an alphabetical wall of stable names.
//
// Honest about provenance: shows "演示数据" / "真实价格" badge sourced
// from the meta endpoint so users know whether they're looking at the
// VPS-refreshed nightly run or the bundled bootstrap snapshot.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchEwsLeaderboard, fetchEwsMeta } from "@/lib/api";
import type {
  EwsCard,
  EwsMeta,
  CriticalPointState,
  Market,
} from "@/lib/types";
import { CPS_BADGE, CPS_ICON, CPS_LABEL_ZH, SECTOR_LABEL_ZH } from "@/lib/labels";

const PHASE_OPTIONS: { value: CriticalPointState | "ALL"; label: string }[] = [
  { value: "ALL", label: "全部" },
  { value: "at_critical", label: "临界点上" },
  { value: "approaching_critical", label: "接近临界" },
  { value: "post_critical_transition", label: "已翻转" },
  { value: "far_from_critical", label: "稳态" },
];

const MARKET_OPTIONS: { value: Market | "ALL"; label: string }[] = [
  { value: "ALL", label: "美 + 港" },
  { value: "US", label: "美股 US" },
  { value: "HK", label: "港股 HK" },
];

function tauColor(tau?: number | null): string {
  if (tau == null) return "text-zinc-400";
  if (tau >= 0.4) return "text-red-700";
  if (tau >= 0.2) return "text-amber-700";
  if (tau <= -0.2) return "text-emerald-700";
  return "text-zinc-500";
}

function fmtTau(tau?: number | null): string {
  if (tau == null) return "—";
  return (tau > 0 ? "+" : "") + tau.toFixed(2);
}

export function EwsLeaderboardPanel() {
  const [market, setMarket] = useState<Market | "ALL">("ALL");
  const [phase, setPhase] = useState<CriticalPointState | "ALL">("ALL");
  const [rows, setRows] = useState<EwsCard[]>([]);
  const [meta, setMeta] = useState<EwsMeta | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const cards = await fetchEwsLeaderboard({
        market,
        phase: phase === "ALL" ? undefined : phase,
        limit: 60,
      });
      setRows(cards);
    } finally {
      setLoading(false);
    }
  }, [market, phase]);

  useEffect(() => {
    fetchEwsMeta().then(setMeta);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const phaseCounts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of rows) out[r.phase_state] = (out[r.phase_state] ?? 0) + 1;
    return out;
  }, [rows]);

  const provenanceBadge =
    meta?.price_provenance === "live"
      ? { txt: "真实价格 · 每日刷新", cls: "bg-emerald-100 text-emerald-800" }
      : meta?.price_provenance === "live+synth_fallback"
        ? { txt: "真实+部分演示", cls: "bg-amber-100 text-amber-800" }
        : meta?.price_provenance === "demo"
          ? { txt: "演示数据 · 非实时市场信号", cls: "bg-zinc-200 text-zinc-700" }
          : { txt: "数据准备中", cls: "bg-zinc-100 text-zinc-600" };

  return (
    <section
      id="ews-leaderboard"
      data-testid="ews-leaderboard"
      className="rounded-2xl border border-zinc-200 bg-white p-5 sm:p-7"
      aria-labelledby="ews-lb-heading"
    >
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2
            id="ews-lb-heading"
            className="text-xl font-semibold tracking-tight text-zinc-900 sm:text-2xl"
            style={{ fontFamily: "var(--font-serif), 'Noto Serif SC', serif" }}
          >
            临界减速排行 (CSD Leaderboard)
          </h2>
          <p className="mt-1 max-w-prose text-sm text-zinc-600">
            按标注的数据来源计算 AR1 + 方差 Kendall 趋势；当前生产快照为 demo。
            <strong className="text-zinc-900"> 两个指标同时上升 </strong>
            才算 CSD 警报；单边不上分（避免假阳）。
            涵盖<strong className="text-zinc-900"> 美股 S&amp;P 500 + 港股 HSI/HSTECH</strong>，
            ADR 双重上市以港股主板为准（BABA→9988、JD→9618 等）。
          </p>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${provenanceBadge.cls}`}>
          {provenanceBadge.txt}
        </span>
      </div>

      {/* Filter row */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="inline-flex items-center rounded-md border border-zinc-200 p-0.5 text-xs">
          {MARKET_OPTIONS.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMarket(m.value)}
              className={`rounded px-2.5 py-1 transition ${
                market === m.value
                  ? "bg-zinc-900 text-white"
                  : "text-zinc-600 hover:text-zinc-900"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="inline-flex items-center rounded-md border border-zinc-200 p-0.5 text-xs">
          {PHASE_OPTIONS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setPhase(p.value)}
              className={`rounded px-2.5 py-1 transition ${
                phase === p.value
                  ? "bg-zinc-900 text-white"
                  : "text-zinc-600 hover:text-zinc-900"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-zinc-500">
          {loading ? "加载中…" : `${rows.length} 条结果`}
          {!loading && rows.length > 0 && (
            <>
              {" · "}
              临界 {phaseCounts.at_critical ?? 0} · 接近{" "}
              {phaseCounts.approaching_critical ?? 0} · 已翻 {phaseCounts.post_critical_transition ?? 0}
            </>
          )}
        </span>
      </div>

      {/* Result table */}
      {rows.length === 0 && !loading ? (
        <div className="rounded-md border border-dashed border-zinc-300 bg-zinc-50/60 p-6 text-sm text-zinc-600">
          当前筛选无匹配。试试切到 &ldquo;全部&rdquo; 或换市场。
        </div>
      ) : (
        <div
          className="overflow-x-auto"
          role="region"
          aria-label="EWS 结果表，可横向滚动"
          tabIndex={0}
        >
          <table className="w-full min-w-[640px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wider text-zinc-500">
                <th className="py-2 pr-3 font-medium">Ticker</th>
                <th className="px-3 font-medium">市场</th>
                <th className="px-3 font-medium">板块</th>
                <th className="px-3 font-medium">阶段</th>
                <th className="px-3 text-right font-medium">CSD 分数</th>
                <th className="px-3 text-right font-medium">AR1 τ</th>
                <th className="px-3 text-right font-medium">方差 τ</th>
                <th className="px-3 text-right font-medium">置信</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr
                  key={r.ticker}
                  className="border-b border-zinc-100 transition hover:bg-zinc-50"
                >
                  <td className="py-2 pr-3">
                    <Link
                      href={`/company/${encodeURIComponent(r.ticker)}`}
                      className="font-medium text-zinc-900 hover:text-indigo-700 hover:underline"
                    >
                      {r.ticker}
                    </Link>
                    {r.name_zh ? (
                      <div className="text-xs text-zinc-500">{r.name_zh}</div>
                    ) : r.name ? (
                      <div className="text-xs text-zinc-500">{r.name}</div>
                    ) : null}
                  </td>
                  <td className="px-3">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${
                        r.market === "HK"
                          ? "bg-rose-100 text-rose-800"
                          : "bg-indigo-100 text-indigo-800"
                      }`}
                    >
                      {r.market ?? "—"}
                    </span>
                  </td>
                  <td className="px-3 text-xs text-zinc-600">
                    {r.sector ? SECTOR_LABEL_ZH[r.sector] ?? r.sector : "—"}
                  </td>
                  <td className="px-3">
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        CPS_BADGE[r.phase_state] ?? "bg-zinc-200 text-zinc-700"
                      }`}
                    >
                      <span aria-hidden>{CPS_ICON[r.phase_state] ?? "?"}</span>
                      {CPS_LABEL_ZH[r.phase_state] ?? r.phase_state}
                    </span>
                  </td>
                  <td className="px-3 text-right tabular-nums">
                    {Math.round(r.criticality_score)}
                  </td>
                  <td className={`px-3 text-right tabular-nums ${tauColor(r.tau_ar1)}`}>
                    {fmtTau(r.tau_ar1)}
                  </td>
                  <td className={`px-3 text-right tabular-nums ${tauColor(r.tau_var)}`}>
                    {fmtTau(r.tau_var)}
                  </td>
                  <td className="px-3 text-right tabular-nums text-zinc-600">
                    {Math.round((r.confidence ?? 0) * 100)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-4 text-[11px] leading-relaxed text-zinc-500">
        方法：每条 ticker 的近 ~2 年日线 → 60 天滑窗 AR1 与方差 →
        滑窗 250 天的 Kendall-τ 趋势检验（先 stride 子采样去除滑窗重叠造成的伪显著）→
        AR1 与方差 <strong>同时</strong> 正向且 p&lt;0.01 才计入复合分。
        我们曾用 LLM 给每家公司贴一个 &ldquo;动力学族&rdquo; 标签，那个版本
        backtest 显示无 alpha（p≈0.68）；这个 CSD 引擎是真实可测量的物理量，
        且对美股、港股结构平等。
        <strong className="text-zinc-700"> 不是投资建议。</strong>
      </p>
    </section>
  );
}

export default EwsLeaderboardPanel;
