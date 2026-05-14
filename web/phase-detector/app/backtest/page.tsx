import type { Metadata } from "next";
import Link from "next/link";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { CumulativeChart } from "./CumulativeChart";

// Wave 2 (2026-05-14): /backtest transparency page.
//
// Framing intent (locked by user 2026-05-14):
//   This page reports a NULL backtest outcome (p = 0.681). It is NOT marketed
//   as an alpha screener. The narrative is pre-registration discipline:
//   "we said we'd run this test, we ran it, here are the numbers, here is
//   what they do and do not say." Publishing the null is the feature.
//
// Data is loaded from public/backtest/{result.json,cumulative.csv} at request
// time so production deploys can drop new files without rebuilds. The same
// files are also exposed via /api/backtest-result and /api/backtest-cumulative.

export const metadata: Metadata = {
  title: "Backtest 透明度报告 — Phase Detector",
  description:
    "Walk-forward backtest on 500 SP500 tickers, 54 monthly snapshots, 26,583 observations. Alpha NOT detected (p = 0.681). 我们公开发布零结果。",
};

export const dynamic = "force-static";
export const revalidate = 3600;

type BacktestResult = {
  version: string;
  mode: string;
  snapshot_anchor: string;
  period_months: number;
  n_snapshots: number;
  n_near_critical: number;
  n_other: number;
  mean_return_nc: number;
  mean_return_other: number;
  std_nc: number;
  std_other: number;
  sharpe_nc: number;
  sharpe_other: number;
  t_stat: number;
  p_value: number;
  prices_meta?: {
    yfinance_tickers?: number;
    n_total_tickers?: number;
    start?: string;
    end?: string;
    period?: string;
  };
  generated_at: string;
};

type CumRow = {
  snapshot_date: string;
  mean_nc_ret: number;
  mean_other_ret: number;
  n_nc: number;
  n_other: number;
  cum_nc_ret: number;
  cum_other_ret: number;
};

async function loadResult(): Promise<BacktestResult | null> {
  try {
    const p = path.join(process.cwd(), "public", "backtest", "result.json");
    return JSON.parse(await readFile(p, "utf8")) as BacktestResult;
  } catch {
    return null;
  }
}

async function loadCumulative(): Promise<CumRow[]> {
  try {
    const p = path.join(process.cwd(), "public", "backtest", "cumulative.csv");
    const text = await readFile(p, "utf8");
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];
    const header = lines[0].split(",").map((s) => s.trim());
    const idx = (k: string) => header.indexOf(k);
    const rows: CumRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(",");
      if (cols.length < header.length) continue;
      rows.push({
        snapshot_date: cols[idx("snapshot_date")],
        mean_nc_ret: Number(cols[idx("mean_nc_ret")]),
        mean_other_ret: Number(cols[idx("mean_other_ret")]),
        n_nc: Number(cols[idx("n_nc")]),
        n_other: Number(cols[idx("n_other")]),
        cum_nc_ret: Number(cols[idx("cum_nc_ret")]),
        cum_other_ret: Number(cols[idx("cum_other_ret")]),
      });
    }
    return rows;
  } catch {
    return [];
  }
}

function pct(x: number, digits = 2): string {
  if (!Number.isFinite(x)) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

function num(x: number, digits = 2): string {
  if (!Number.isFinite(x)) return "—";
  return x.toFixed(digits);
}

export default async function BacktestPage() {
  const result = await loadResult();
  const rows = await loadCumulative();

  if (!result) {
    return (
      <div className="py-16 text-center text-zinc-500">
        Backtest data not available. Check{" "}
        <code className="rounded bg-zinc-100 px-1.5 py-0.5 text-xs">
          public/backtest/result.json
        </code>
        .
      </div>
    );
  }

  const ticksFetched = result.prices_meta?.yfinance_tickers ?? 0;
  const ticksTotal = result.prices_meta?.n_total_tickers ?? 500;
  const periodStart = result.prices_meta?.start ?? "—";
  const periodEnd = result.prices_meta?.end ?? "—";

  return (
    <div className="space-y-12 py-4">
      {/* Hero */}
      <header className="space-y-3 border-b border-zinc-200 pb-8">
        <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Transparency report · {result.snapshot_anchor}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl">
          Walk-forward backtest — 500 SP500 tickers
        </h1>
        <p className="max-w-3xl text-base text-zinc-600">
          We pre-registered a single hypothesis: companies labelled{" "}
          <span className="font-medium text-zinc-900">near_critical</span> by
          the Phase Detector should show a different 6-month forward return
          than the rest. We ran the test on five years of monthly SP500 prices.
          The result is{" "}
          <span className="font-medium text-zinc-900">
            alpha NOT detected
          </span>{" "}
          (p = {num(result.p_value, 3)}). We publish this.
        </p>
      </header>

      {/* Stats card grid */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">Headline numbers</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Welch's t-statistic"
            value={num(result.t_stat, 3)}
            note="near_critical − other"
          />
          <StatCard
            label="p-value"
            value={num(result.p_value, 3)}
            note="two-sided"
            emphasis="warn"
          />
          <StatCard
            label="n near_critical"
            value={result.n_near_critical.toLocaleString()}
            note={`observations across ${result.n_snapshots} snapshots`}
          />
          <StatCard
            label="n other"
            value={result.n_other.toLocaleString()}
            note="far_from + post_critical"
          />
          <StatCard
            label="mean 6mo return — near_critical"
            value={pct(result.mean_return_nc)}
            note={`σ = ${pct(result.std_nc, 1)}`}
          />
          <StatCard
            label="mean 6mo return — other"
            value={pct(result.mean_return_other)}
            note={`σ = ${pct(result.std_other, 1)}`}
          />
          <StatCard
            label="Sharpe — near_critical"
            value={num(result.sharpe_nc, 2)}
            note="annualised"
          />
          <StatCard
            label="Sharpe — other"
            value={num(result.sharpe_other, 2)}
            note="annualised"
            emphasis="good"
          />
        </div>
      </section>

      {/* Verdict block */}
      <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-6">
        <div className="text-xs font-medium uppercase tracking-wider text-amber-700">
          Verdict
        </div>
        <div className="mt-2 text-xl font-semibold text-zinc-900">
          p = {num(result.p_value, 3)} &rarr; NULL hypothesis NOT rejected
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-700">
          Across {result.n_snapshots} monthly snapshots from {periodStart} to{" "}
          {periodEnd} ({ticksFetched}/{ticksTotal} SP500 tickers fetched), the
          mean 6-month forward return of <em>near_critical</em>-labelled
          companies ({pct(result.mean_return_nc)}) is statistically
          indistinguishable from the rest ({pct(result.mean_return_other)}).
          The two distributions differ by only 27 basis points — within
          sampling noise. <em>near_critical</em> dispersion is higher (σ ={" "}
          {pct(result.std_nc, 1)} vs {pct(result.std_other, 1)}), which gives
          it a <strong>worse</strong> risk-adjusted return
          (Sharpe {num(result.sharpe_nc, 2)} vs{" "}
          {num(result.sharpe_other, 2)}). On this specification, the Phase
          Detector label does not carry tradable directional information.
        </p>
      </section>

      {/* Chart */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">
          Cumulative monthly group means
        </h2>
        <p className="max-w-3xl text-sm text-zinc-600">
          Sum of equal-weighted monthly mean returns for each group, anchored
          at the first snapshot. Both curves drift up together — the headline
          test (Welch on flat-pooled observations) confirms the visual: no
          persistent separation.
        </p>
        <div className="rounded-lg border border-zinc-200 bg-white p-4">
          {rows.length > 0 ? (
            <CumulativeChart rows={rows} />
          ) : (
            <div className="py-12 text-center text-sm text-zinc-500">
              cumulative.csv unavailable
            </div>
          )}
        </div>
        <p className="text-xs text-zinc-500">
          Raw data:{" "}
          <Link
            href="/api/backtest-cumulative"
            className="underline hover:text-zinc-900"
          >
            /api/backtest-cumulative
          </Link>{" "}
          ·{" "}
          <Link
            href="/api/backtest-result"
            className="underline hover:text-zinc-900"
          >
            /api/backtest-result
          </Link>
        </p>
      </section>

      {/* Pre-registered limitations */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">
          Pre-registered limitations
        </h2>
        <p className="max-w-3xl text-sm text-zinc-600">
          These caveats were known before the test ran. They define what this
          result can and cannot say.
        </p>
        <ol className="list-decimal space-y-3 pl-5 text-sm text-zinc-700">
          <li>
            <strong>Label leakage risk.</strong> All 500 Wave 1 StructTuples
            were classified once at 2026-05-14, then applied retroactively to
            every snapshot from 2021-06 onward. The model may have used
            information unavailable at the historical snapshot date. A
            per-snapshot label refresh (re-classify each company as of each T)
            is the strict-causality version of this test and has not yet been
            run.
          </li>
          <li>
            <strong>SP500 universe.</strong> All 500 companies are large-cap US
            survivors. Phase-transition signals may be more detectable in
            stressed segments (small-cap, EM, distressed credit). A null on
            blue-chips does not generalise to those.
          </li>
          <li>
            <strong>6-month horizon only.</strong> The original hypothesis
            named 6 months; we tested 6 months. We did not sweep horizons
            (3 / 12 / 24mo) to look for the regime where the label matters
            most. That is exploratory, not pre-registered.
          </li>
          <li>
            <strong>13% threshold for near_critical.</strong>{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs">
              near_critical = approaching_critical ∪ at_critical
            </code>{" "}
            gives 65/500 ≈ 13% of the universe. Tightening the threshold (e.g.{" "}
            <em>at_critical</em> only, ~3%) or loosening it changes the cell
            sizes and the test power. We did not optimise this knob.
          </li>
          <li>
            <strong>Horizon sensitivity.</strong> No multiple-testing
            correction was applied because only one hypothesis was registered.
            Any post-hoc sweep (horizon × threshold × sector) needs
            Benjamini-Hochberg or similar before being reported as evidence.
          </li>
        </ol>
      </section>

      {/* What's next */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">What&rsquo;s next</h2>
        <p className="max-w-3xl text-sm text-zinc-600">
          The null result is informative but specification-bound. Four
          experiments we consider worth running before declaring the label
          economically irrelevant:
        </p>
        <ol className="list-decimal space-y-3 pl-5 text-sm text-zinc-700">
          <li>
            <strong>Per-snapshot label refresh.</strong> Re-classify each
            company at each historical T using only information available at
            that T. Removes the leakage risk in (1) above. This is the
            single most expensive experiment and the one most likely to flip
            the result.
          </li>
          <li>
            <strong>Smid-cap universe.</strong> Repeat the test on Russell 2000
            or a synthetic small + mid-cap basket. Phase-transition labels are
            most plausible where distress is real, not in the blue-chip
            survivor pool.
          </li>
          <li>
            <strong>dynamics_family stratified test.</strong> Run the test
            within each dynamics class (queueing-collapse / debt-deflation /
            information-cascade / contagion / homeostatic-overshoot) rather
            than pooled. The signal may live in a single family and be drowned
            out in the aggregate.
          </li>
          <li>
            <strong>Horizon sensitivity sweep.</strong> 3 / 6 / 12 / 24 month
            forward returns, with appropriate multiple-testing correction.
            Tells us whether the null is horizon-specific or universal.
          </li>
        </ol>
      </section>

      {/* Footer / methodology link */}
      <section className="border-t border-zinc-200 pt-6 text-sm text-zinc-500">
        <p>
          Method, label definitions, and the raw Wave 1 StructTuples are on the{" "}
          <Link
            href="/methodology"
            className="text-zinc-700 underline hover:text-zinc-900"
          >
            methodology page
          </Link>
          . Backtest code is open-source in the{" "}
          <a
            href="https://github.com/dada8899/structural-isomorphism/tree/main/v4/product/d1_phase_detector"
            target="_blank"
            rel="noopener"
            className="text-zinc-700 underline hover:text-zinc-900"
          >
            GitHub repository
          </a>
          . This page is a research preview; nothing here is investment
          advice.
        </p>
        <p className="mt-2 text-xs text-zinc-400">
          Generated at {result.generated_at} · backtest version{" "}
          {result.version} · mode {result.mode}
        </p>
      </section>
    </div>
  );
}

function StatCard({
  label,
  value,
  note,
  emphasis,
}: {
  label: string;
  value: string;
  note?: string;
  emphasis?: "good" | "warn";
}) {
  const valueColor =
    emphasis === "good"
      ? "text-emerald-700"
      : emphasis === "warn"
        ? "text-amber-700"
        : "text-zinc-900";
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wider text-zinc-500">
        {label}
      </div>
      <div className={`mt-2 text-2xl font-semibold tabular-nums ${valueColor}`}>
        {value}
      </div>
      {note ? (
        <div className="mt-1 text-xs text-zinc-500">{note}</div>
      ) : null}
    </div>
  );
}
