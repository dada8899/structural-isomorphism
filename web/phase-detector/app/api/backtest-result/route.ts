import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

// Wave 2 (2026-05-14): expose walk-forward backtest summary JSON.
// Data source: public/backtest/result.json (mirrored from
// v4/product/d1_phase_detector/backtest_result.json at deploy time).
// Framed as a transparency report — NULL result is the intended finding.

export const dynamic = "force-static";
export const revalidate = 3600; // 1h

export async function GET() {
  try {
    const filePath = path.join(
      process.cwd(),
      "public",
      "backtest",
      "result.json",
    );
    const raw = await readFile(filePath, "utf8");
    const data = JSON.parse(raw);
    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, max-age=3600" },
    });
  } catch (err) {
    return NextResponse.json(
      { error: "backtest_result_unavailable", detail: String(err) },
      { status: 500 },
    );
  }
}
