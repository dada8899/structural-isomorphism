#!/usr/bin/env node
// Session #12 W17 — aggregate transfer-ledger reports.
//
// Reads the live GitHub Issues API for issues labeled `transfer-ledger`,
// parses each body for the case URL + verdict, and writes
// `web/phase-detector/data/transfer-ledger-counts.json`.
//
// Invoked by .github/workflows/transfer-ledger-aggregate.yml whenever
// a transfer-ledger issue is opened, edited, closed, labeled, or commented.
// Designed to be idempotent and safe to re-run.
//
// Usage:
//   GITHUB_REPOSITORY=owner/repo GITHUB_TOKEN=xxx node scripts/aggregate-transfer-ledger.mjs
//
// In CI both env vars are auto-injected by the workflow.

import { writeFile, readFile } from "node:fs/promises";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, "..");
const OUT_PATH = resolve(
  REPO_ROOT,
  "web/phase-detector/data/transfer-ledger-counts.json",
);

const REPO = process.env.GITHUB_REPOSITORY || "dada8899/structural-isomorphism";
const TOKEN = process.env.GITHUB_TOKEN;
const API_BASE = "https://api.github.com";
const LABEL = "transfer-ledger";
const PER_PAGE = 100;

// Verdict normalization. The issue template asks the user to write
// "pass | fail | inconclusive" but we accept the common variants too.
const VERDICT_PATTERNS = [
  { re: /\bverdict\s*:\s*(?:pass|passed|✅|succeeded|success)\b/i, key: "pass" },
  { re: /\bverdict\s*:\s*(?:fail(?:ed)?|❌|rejected)\b/i, key: "fail" },
  {
    re: /\bverdict\s*:\s*(?:inconclusive|partial|unclear|maybe|undetermined)\b/i,
    key: "inconclusive",
  },
];

// Extract the case ID from the issue body. Accepts either a /insights/<id>
// URL or a "case-id: <id>" line. The case ID is lowercase-kebab.
const CASE_ID_PATTERNS = [
  /\/insights\/([a-z0-9-]+)/i,
  /case[\s_-]*id\s*[:=]\s*([a-z0-9-]+)/i,
];

function parseCaseId(body) {
  if (!body) return null;
  for (const p of CASE_ID_PATTERNS) {
    const m = body.match(p);
    if (m && m[1]) return m[1];
  }
  return null;
}

function parseVerdict(body) {
  if (!body) return null;
  for (const v of VERDICT_PATTERNS) {
    if (v.re.test(body)) return v.key;
  }
  return null;
}

async function fetchAllLedgerIssues() {
  const issues = [];
  for (let page = 1; page <= 50; page++) {
    const url = `${API_BASE}/repos/${REPO}/issues?state=all&labels=${LABEL}&per_page=${PER_PAGE}&page=${page}`;
    const headers = { Accept: "application/vnd.github+json" };
    if (TOKEN) headers.Authorization = `Bearer ${TOKEN}`;
    const r = await fetch(url, { headers });
    if (!r.ok) {
      // 404 is normal when the repo has zero ledger issues yet.
      if (r.status === 404) break;
      throw new Error(`GitHub API ${r.status}: ${await r.text()}`);
    }
    const batch = await r.json();
    if (!Array.isArray(batch) || batch.length === 0) break;
    // The /issues endpoint includes pull requests — filter them out.
    issues.push(...batch.filter((i) => !i.pull_request));
    if (batch.length < PER_PAGE) break;
  }
  return issues;
}

function aggregate(issues) {
  const out = {};
  let unparsed = 0;
  for (const i of issues) {
    const caseId = parseCaseId(i.body || "") || parseCaseId(i.title || "");
    const verdict = parseVerdict(i.body || "");
    if (!caseId || !verdict) {
      unparsed += 1;
      continue;
    }
    if (!out[caseId]) {
      out[caseId] = { pass: 0, fail: 0, inconclusive: 0, total: 0 };
    }
    out[caseId][verdict] += 1;
    out[caseId].total += 1;
  }
  return { counts_by_case: out, unparsed_count: unparsed };
}

async function main() {
  // Allow CI to pass --dry-run to print without writing.
  const dryRun = process.argv.includes("--dry-run");

  const issues = await fetchAllLedgerIssues();
  const { counts_by_case, unparsed_count } = aggregate(issues);

  const payload = {
    _meta: {
      schema_version: 1,
      generated_at: new Date().toISOString(),
      generated_by: "scripts/aggregate-transfer-ledger.mjs",
      total_issues_inspected: issues.length,
      unparsed_count,
      source: `https://github.com/${REPO}/issues?q=is%3Aissue+label%3A${LABEL}`,
    },
    counts_by_case,
  };

  // Stable shape: keep keys deterministic for clean diffs.
  payload.counts_by_case = Object.fromEntries(
    Object.entries(payload.counts_by_case).sort(([a], [b]) => a.localeCompare(b)),
  );

  const json = JSON.stringify(payload, null, 2) + "\n";

  if (dryRun) {
    console.log(json);
    return;
  }

  // Skip write if nothing changed apart from generated_at — avoids
  // flooding the repo with commits for every webhook event.
  let prev = null;
  try {
    prev = JSON.parse(await readFile(OUT_PATH, "utf8"));
  } catch {
    // file doesn't exist yet — fine
  }
  if (prev) {
    const prevWithoutMeta = JSON.stringify(prev.counts_by_case || {});
    const nextWithoutMeta = JSON.stringify(payload.counts_by_case);
    if (prevWithoutMeta === nextWithoutMeta) {
      console.log("transfer-ledger: no change in counts; skipping write");
      // Still emit a marker so the workflow can `if: steps.x.outputs.changed`.
      if (process.env.GITHUB_OUTPUT) {
        const fs = await import("node:fs");
        fs.appendFileSync(process.env.GITHUB_OUTPUT, "changed=false\n");
      }
      return;
    }
  }

  await writeFile(OUT_PATH, json, "utf8");
  console.log(`transfer-ledger: wrote ${OUT_PATH}`);
  console.log(`  total issues inspected: ${issues.length}`);
  console.log(`  cases with reports:     ${Object.keys(counts_by_case).length}`);
  console.log(`  unparsed issues:        ${unparsed_count}`);

  if (process.env.GITHUB_OUTPUT) {
    const fs = await import("node:fs");
    fs.appendFileSync(process.env.GITHUB_OUTPUT, "changed=true\n");
  }
}

main().catch((e) => {
  console.error("transfer-ledger aggregation failed:", e);
  process.exit(1);
});
