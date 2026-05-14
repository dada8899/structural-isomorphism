import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Wave 2 (2026-05-14): expose walk-forward cumulative-return time series.
// Data source: public/backtest/cumulative.csv. Parsed to JSON for client.

export const dynamic = "force-static";
export const revalidate = 3600;

type Row = {
  snapshot_date: string;
  mean_nc_ret: number;
  mean_other_ret: number;
  n_nc: number;
  n_other: number;
  cum_nc_ret: number;
  cum_other_ret: number;
};

function parseCsv(text: string): Row[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].split(",").map((s) => s.trim());
  const idx = (k: string) => header.indexOf(k);
  const iDate = idx("snapshot_date");
  const iMeanNc = idx("mean_nc_ret");
  const iMeanOther = idx("mean_other_ret");
  const iNNc = idx("n_nc");
  const iNOther = idx("n_other");
  const iCumNc = idx("cum_nc_ret");
  const iCumOther = idx("cum_other_ret");
  const rows: Row[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(",");
    if (cols.length < header.length) continue;
    rows.push({
      snapshot_date: cols[iDate],
      mean_nc_ret: Number(cols[iMeanNc]),
      mean_other_ret: Number(cols[iMeanOther]),
      n_nc: Number(cols[iNNc]),
      n_other: Number(cols[iNOther]),
      cum_nc_ret: Number(cols[iCumNc]),
      cum_other_ret: Number(cols[iCumOther]),
    });
  }
  return rows;
}

export async function GET() {
  try {
    const filePath = path.join(
      process.cwd(),
      "public",
      "backtest",
      "cumulative.csv",
    );
    const raw = await readFile(filePath, "utf8");
    const rows = parseCsv(raw);
    return NextResponse.json(
      { rows },
      { headers: { "Cache-Control": "public, max-age=3600" } },
    );
  } catch (err) {
    return NextResponse.json(
      { error: "backtest_cumulative_unavailable", detail: String(err) },
      { status: 500 },
    );
  }
}
