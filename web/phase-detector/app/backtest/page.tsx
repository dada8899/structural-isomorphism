import type { Metadata } from "next";
import Link from "next/link";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { CumulativeChart } from "./CumulativeChart";
import JsonLd from "@/components/JsonLd";
import { buildMetadata, datasetSchema } from "@/lib/seo";

// Wave 2 (2026-05-14): /backtest transparency page.
// Wave 10 (2026-05-15): updated to v0.1 1000-ticker walk-forward numbers.
//
// Framing intent (locked by user 2026-05-14, reaffirmed 2026-05-15):
//   This page reports a NULL backtest outcome (Sharpe lift = -0.07,
//   p = 0.569 at 1-month hold; lift = -0.51 at 6-month hold). It is NOT
//   marketed as an alpha screener. The narrative is pre-registration
//   discipline: "we said we'd run this test on 1000 tickers, we ran it,
//   here are the numbers, here is what they do and do not say."
//   Publishing the null is the feature. Per W7-D Track A this confirms
//   the pivot to structured-research-narrative positioning.
//
// Data is loaded from public/backtest/{result.json,cumulative.csv} at request
// time so production deploys can drop new files without rebuilds. The same
// files are also exposed via /api/backtest-result and /api/backtest-cumulative.

// W12-B (2026-05-15): OG card + canonical + dataset JSON-LD embedded in page body.
export const metadata: Metadata = buildMetadata({
  title: "Backtest 透明度报告 — Phase Detector",
  description:
    "Walk-forward backtest v0.1 on 927 SP500 + Russell-1000-supplement tickers, 59 monthly snapshots, 2020-2025. Sharpe lift -0.07 vs benchmark (p = 0.569). Alpha NOT detected at scale. 我们公开发布零结果。",
  path: "/backtest",
  ogImage: "/og/backtest.png",
});

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
    n_universe_covered?: number;
    start?: string;
    end?: string;
    period?: string;
  };
  v01_extensions?: {
    engine?: string;
    universe_composition?: {
      sp500: number;
      russell_supplement: number;
      total_input: number;
      covered: number;
      coverage_pct: number;
    };
    benchmark_ew?: {
      sharpe_annualised: number;
      mean_monthly: number;
      max_drawdown: number;
      hit_rate: number;
      cumulative_return: number;
    };
    sharpe_lift?: number;
    verdict?: string;
  };
  last_updated?: string;
  generated_at: string;
};

type CumRow = {
  snapshot_date: string;
  mean_nc_ret: number;
  mean_other_ret: number;
  mean_bench_ret?: number;
  n_nc: number;
  n_other: number;
  cum_nc_ret: number;
  cum_other_ret: number;
  cum_bench_ret?: number;
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
    const hasBench = idx("mean_bench_ret") >= 0;
    const rows: CumRow[] = [];
    for (let i = 1; i < lines.length; i++) {
      const cols = lines[i].split(",");
      if (cols.length < header.length) continue;
      rows.push({
        snapshot_date: cols[idx("snapshot_date")],
        mean_nc_ret: Number(cols[idx("mean_nc_ret")]),
        mean_other_ret: Number(cols[idx("mean_other_ret")]),
        mean_bench_ret: hasBench ? Number(cols[idx("mean_bench_ret")]) : undefined,
        n_nc: Number(cols[idx("n_nc")]),
        n_other: Number(cols[idx("n_other")]),
        cum_nc_ret: Number(cols[idx("cum_nc_ret")]),
        cum_other_ret: Number(cols[idx("cum_other_ret")]),
        cum_bench_ret: hasBench ? Number(cols[idx("cum_bench_ret")]) : undefined,
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
  const lift = result.v01_extensions?.sharpe_lift;
  const benchSharpe = result.v01_extensions?.benchmark_ew?.sharpe_annualised;
  const universe = result.v01_extensions?.universe_composition;
  const lastUpdatedStr = result.last_updated ?? result.generated_at;
  const lastUpdated = lastUpdatedStr ? new Date(lastUpdatedStr) : null;
  const periodLabel = result.period_months === 1 ? "monthly" : `${result.period_months}-month`;

  return (
    <div className="space-y-12 py-4">
      {/* W12-B: Dataset schema for rich result eligibility. */}
      <JsonLd
        id="ld-backtest-dataset"
        schema={datasetSchema({
          name: "Phase Detector walk-forward backtest v0.1",
          description: `Walk-forward backtest of ${ticksFetched} U.S. equity tickers across ${result.n_snapshots} monthly snapshots. Published null outcome (Sharpe lift = ${num(lift ?? NaN, 3)}, p = ${num(result.p_value, 3)}).`,
          url: "https://phase.bytedance.city/backtest",
          distributionUrl: "https://phase.bytedance.city/api/backtest-result",
        })}
      />
      {/* Hero */}
      <header className="space-y-3 border-b border-zinc-200 pb-8">
        <div className="flex flex-wrap items-center gap-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
          <span>Transparency report v0.1 · {result.snapshot_anchor}</span>
          {lastUpdated ? (
            <span className="rounded-full border border-zinc-200 bg-white px-2 py-0.5 text-[10px] normal-case tracking-normal text-zinc-600">
              Last updated {lastUpdated.toISOString().slice(0, 10)}
            </span>
          ) : null}
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900 sm:text-4xl">
          Walk-forward backtest — {ticksFetched.toLocaleString()} tickers ({universe?.sp500 ?? 500} SP500 + {universe?.russell_supplement ?? 0} Russell 1000 supplement)
        </h1>
        <p className="max-w-3xl text-base text-zinc-600">
          We pre-registered a single hypothesis: companies labelled{" "}
          <span className="font-medium text-zinc-900">near_critical</span> by
          the Phase Detector should produce a different risk-adjusted forward
          return than the rest of a ~1000-ticker U.S. equity universe across
          a 5-year walk-forward (2020-2025). The result is{" "}
          <span className="font-medium text-zinc-900">
            alpha NOT detected at scale
          </span>{" "}
          — Sharpe lift = {num(lift ?? NaN, 3)} (p = {num(result.p_value, 3)}).
          Per <Link href="https://github.com/dada8899/structural-isomorphism/blob/main/docs/future/W7-D-product-value-roadmap-2026-05-13.md" className="underline">W7-D Track A</Link>, this confirms the pivot to{" "}
          <span className="font-medium text-zinc-900">
            structured-research-narrative positioning
          </span>. We publish the null openly.
        </p>
      </header>

      {/* Stats card grid */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">Headline numbers ({periodLabel} forward hold)</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Sharpe lift vs benchmark"
            value={lift != null && Number.isFinite(lift) ? `${lift >= 0 ? "+" : ""}${num(lift, 3)}` : "—"}
            note="near_critical − benchmark EW"
            emphasis="warn"
          />
          <StatCard
            label="p-value (paired t)"
            value={num(result.p_value, 3)}
            note="two-sided · 59 months"
            emphasis="warn"
          />
          <StatCard
            label="benchmark Sharpe"
            value={num(benchSharpe ?? NaN, 2)}
            note="annualised EW universe"
          />
          <StatCard
            label="snapshots"
            value={result.n_snapshots.toLocaleString()}
            note={`monthly · ${periodStart} → ${periodEnd}`}
          />
          <StatCard
            label="near_critical cohort"
            value={result.n_near_critical.toLocaleString()}
            note="SP500 tickers · LLM-labelled"
          />
          <StatCard
            label="other (stable) cohort"
            value={result.n_other.toLocaleString()}
            note="far_from + post_critical"
          />
          <StatCard
            label="Sharpe — near_critical"
            value={num(result.sharpe_nc, 2)}
            note={`mean ${pct(result.mean_return_nc, 2)}/mo · σ ${pct(result.std_nc, 1)}`}
          />
          <StatCard
            label="Sharpe — other (stable)"
            value={num(result.sharpe_other, 2)}
            note={`mean ${pct(result.mean_return_other, 2)}/mo · σ ${pct(result.std_other, 1)}`}
            emphasis="good"
          />
        </div>
      </section>

      {/* Verdict block */}
      <section className="rounded-lg border border-amber-200 bg-amber-50/60 p-6">
        <div className="text-xs font-medium uppercase tracking-wider text-amber-700">
          Verdict · W7-D Track A month-3 decision gate
        </div>
        <div className="mt-2 text-xl font-semibold text-zinc-900">
          Sharpe lift {lift != null && lift >= 0 ? "+" : ""}{num(lift ?? NaN, 3)} · p = {num(result.p_value, 3)} &rarr; NULL hypothesis NOT rejected
        </div>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-zinc-700">
          Across {result.n_snapshots} monthly snapshots from {periodStart} to{" "}
          {periodEnd} ({ticksFetched}/{ticksTotal} tickers fetched), the
          Phase Detector&rsquo;s <em>near_critical</em> cohort (Sharpe {num(result.sharpe_nc, 2)})
          underperforms the equal-weight benchmark (Sharpe {num(benchSharpe ?? NaN, 2)})
          by {lift != null ? num(Math.abs(lift), 3) : "—"} Sharpe units — well
          below the W7-D{" "}
          <Link href="https://github.com/dada8899/structural-isomorphism/blob/main/docs/future/W7-D-product-value-roadmap-2026-05-13.md" className="underline">+0.5 Sharpe-lift threshold</Link>{" "}
          that would justify alpha-screener positioning. The <em>other</em>{" "}
          (stable) cohort marginally outperforms benchmark (Sharpe{" "}
          {num(result.sharpe_other, 2)}, lift +0.155, p = 0.801), but no
          comparison clears α = 0.05. The headline test (paired t-test on
          monthly cohort-minus-benchmark differences) confirms: <strong>on
          this specification, the Phase Detector label does not carry
          tradable directional information</strong>. Per the W7-D
          pre-committed pivot plan, we proceed with structured-research-
          narrative positioning, with this backtest result published as the
          credibility moat.
        </p>
      </section>

      {/* Chart */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">
          Cumulative monthly group means (vs benchmark)
        </h2>
        <p className="max-w-3xl text-sm text-zinc-600">
          Compounded equal-weight monthly mean returns for each cohort,
          anchored at 2020-12-31. The three curves move together — the
          headline paired t-test confirms the visual: no persistent
          separation. Note <em>near_critical</em> exhibits the largest
          drawdowns (2022 tightening; H1 2025 vol shock).
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
            every snapshot from 2020-12 onward. The model may have used
            information unavailable at the historical snapshot date. A
            per-snapshot label refresh (re-classify each company as of each T)
            is the strict-causality version of this test and remains the
            single most expensive — and most likely to flip the result —
            experiment we have not yet run.
          </li>
          <li>
            <strong>Russell 1000 supplement is a curated 501-name sample,
            not the official R1000.</strong> FTSE Russell licenses
            membership; we cannot redistribute the full list. Our supplement
            is sector-balanced and large/mid-cap, but it is not point-in-time
            R1000 reconstitution. True point-in-time membership would mitigate
            this.
          </li>
          <li>
            <strong>Survivorship bias.</strong> 74/1001 tickers were dropped
            due to delisting / yfinance edge cases. We did not include
            historically-listed-then-delisted tickers in our universe,
            biasing benchmark return upward by ~1–2% annually.
          </li>
          <li>
            <strong>Static labels on R1000 supplement (no labels at all).</strong>{" "}
            Only the 500 SP500 tickers carry LLM <em>critical_point_state</em>{" "}
            labels. The heuristic price-regime cohort uses a 90-day vol +
            180-day drawdown placebo — a baseline, not a Phase Detector test.
          </li>
          <li>
            <strong>Horizon sweep was minimal.</strong> 1-month and 6-month
            forward holds reported; no full 3/12/24-month grid. Any post-hoc
            sweep (horizon × threshold × sector × dynamics-family) needs
            Benjamini-Hochberg correction.
          </li>
          <li>
            <strong>No transaction costs, borrow costs, or sector
            neutralisation.</strong> Pure equal-weighted long-only cohort
            means. Real portfolio implementations would face additional
            decay.
          </li>
        </ol>
      </section>

      {/* What's next */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-zinc-900">What&rsquo;s next</h2>
        <p className="max-w-3xl text-sm text-zinc-600">
          The null result is informative but specification-bound. Per W7-D,
          we proceed with structured-research-narrative positioning. Backlog
          (priority-ranked, cheapest first) for v0.2 if positioning traction
          warrants:
        </p>
        <ol className="list-decimal space-y-3 pl-5 text-sm text-zinc-700">
          <li>
            <strong>Sector-stratified test (cheap, 1 day).</strong> Run the
            paired t-test within each GICS sector. The signal may live in
            healthcare or tech and be diluted in financials/utilities.
            Benjamini-Hochberg correction over 11 sectors.
          </li>
          <li>
            <strong>dynamics_family stratified test (cheap, 1 day).</strong>{" "}
            9 families × 2 cohorts = 18 tests, BH-adjusted. The signal may
            live in <em>motter_lai_cascade</em> or <em>scheffer_fold</em>{" "}
            companies specifically.
          </li>
          <li>
            <strong>Confidence-filtered cohort (cheap, 0.5 day).</strong>{" "}
            Restrict <em>near_critical</em> to <code className="rounded bg-zinc-100 px-1 text-xs">confidence ≥ 0.8</code>{" "}
            labels only (54% of universe). Reduces cohort size but may
            sharpen signal.
          </li>
          <li>
            <strong>Per-snapshot label refresh (expensive, $500–$1k LLM
            cost, 2–3 days).</strong> Re-classify each company at each
            historical T using only information available at that T. Removes
            the leakage risk noted above. This is the single most likely
            experiment to flip the result.
          </li>
          <li>
            <strong>Russell 2000 universe (medium cost).</strong> True
            small-cap is where phase transitions should bite. R2000 = 2000
            names, fetch cost ~10 min, label cost ~$2–$5k if we LLM-classify
            the new 2000 tickers.
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
