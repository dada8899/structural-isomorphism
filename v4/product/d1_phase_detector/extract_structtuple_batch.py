#!/usr/bin/env python3
"""D1 — batch StructTuple extraction at 500-company scale.

Thin wrapper around ``extract_structtuple.extract_one`` (re-uses the same
prompt, DeepSeek call, and V4 guardrail stack), specialised for the 500-row
S&P 500 expansion. Differences vs. the original CLI in
``extract_structtuple.py``:

* Defaults: ``--input v4/product/d1_phase_detector/companies_500_input.jsonl``,
  ``--output companies_500.jsonl``, ``--model deepseek-v4-flash`` (cheaper,
  fast enough for 500-row batch).
* ``--dry-run`` prints the prompt for the first N rows and skips the API
  call entirely — useful for verifying the pipeline before paying.
* ``--limit N`` (default ``50``) lets the caller sample without forgetting to
  cap; pass ``--limit 0`` to mean "process all rows".
* Resume support: if the output file exists and contains successful rows,
  those tickers are skipped (idempotent re-runs on rate-limit recovery).
* Lighter retry policy and finer-grained progress logging suited for long
  unattended runs (500 rows × ~5-30s per call).

Cost: at deepseek-v4-flash (~$0.0001 / 1k in, $0.0003 / 1k out) and ~750 in
+ 500 out tokens per call, full 500 rows ~= $0.30. Even at v4-pro it stays
under $5 well within the standing auto-mode budget.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]

# Wire the guarded_llm package (editable install path may be stale across
# worktrees, so we hard-add the in-repo src dir as a fallback).
_GUARDED_SRC = REPO_ROOT / "packages" / "guarded-llm" / "src"
if _GUARDED_SRC.exists() and str(_GUARDED_SRC) not in sys.path:
    sys.path.insert(0, str(_GUARDED_SRC))

# Auto-load .env (DEEPSEEK_API_KEY) so the script works without manual `export`.
_ENV_FILE = REPO_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        k, v = _line.split("=", 1)
        k, v = k.strip(), v.strip().strip("\"'")
        os.environ.setdefault(k, v)

# We need to import extract_structtuple, but it raises at import time if the
# DeepSeek key is missing — which we want to gate on --dry-run. So fall back
# to importing make_prompt only when dry-running.
sys.path.insert(0, str(HERE))


def _load_real_extractor():
    """Import the real extractor module. Raises at import if no key."""
    import extract_structtuple as ex  # noqa: WPS433

    return ex


def _load_prompt_only():
    """Import only ``make_prompt`` for dry-run, bypassing the API-key check."""
    # We can't import extract_structtuple directly without DEEPSEEK_API_KEY,
    # so re-implement make_prompt's import by reading the file in module form.
    import importlib.util
    import os

    # Set a dummy key just for import-time so we can pull make_prompt.
    placeholder = False
    if "DEEPSEEK_API_KEY" not in os.environ:
        os.environ["DEEPSEEK_API_KEY"] = "dry-run-placeholder"
        placeholder = True

    mod_name = "extract_structtuple_dryrun"
    spec = importlib.util.spec_from_file_location(
        mod_name, HERE / "extract_structtuple.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass-decorated classes can look up their
    # owning module on Python 3.14+.
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    finally:
        if placeholder:
            os.environ.pop("DEEPSEEK_API_KEY", None)
    return mod


def load_companies(path: Path) -> list[dict]:
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def load_existing_results(path: Path) -> dict[str, dict]:
    """Return ticker -> record for any successful rows already in output."""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("ok") and rec.get("ticker"):
                out[rec["ticker"]] = rec
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="D1 batch StructTuple extractor (S&P 500 expansion)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=HERE / "companies_500_input.jsonl",
        help="input jsonl with {ticker, company_name, sector, ...} rows",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "companies_500.jsonl",
        help="output jsonl (one struct_tuple record per row)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help=(
            "process only first N rows AFTER skipping resumed tickers. "
            "0 = no limit (process the entire input). Default 50 for sample."
        ),
    )
    parser.add_argument(
        "--model",
        default="deepseek-v4-flash",
        help="DeepSeek model (default deepseek-v4-flash for batch cost).",
    )
    parser.add_argument(
        "--as-of",
        default="2026-05-13",
        help="as_of_date for StructTuple (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="don't call the LLM; just print the prompts for the first --limit rows",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="ignore any rows already in --output and overwrite",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=0.5,
        help="seconds to sleep between successive LLM calls (rate-limit headroom)",
    )
    args = parser.parse_args()

    if not args.input.exists():
        print(f"[D1-batch] input not found: {args.input}", file=sys.stderr)
        return 2

    companies = load_companies(args.input)
    print(f"[D1-batch] loaded {len(companies)} rows from {args.input}", file=sys.stderr)

    # Resume bookkeeping.
    existing: dict[str, dict] = {}
    if not args.no_resume and not args.dry_run:
        existing = load_existing_results(args.output)
        if existing:
            print(
                f"[D1-batch] resume mode: {len(existing)} successful rows already "
                f"present in {args.output}; skipping those tickers.",
                file=sys.stderr,
            )

    queue = [c for c in companies if c["ticker"] not in existing]
    if args.limit and args.limit > 0:
        queue = queue[: args.limit]
    print(f"[D1-batch] queue size after limit/resume: {len(queue)}", file=sys.stderr)

    # ---------------- DRY RUN ----------------
    if args.dry_run:
        mod = _load_prompt_only()
        for i, company in enumerate(queue, 1):
            prompt = mod.make_prompt(company, as_of=args.as_of)
            print(f"\n=== [{i}/{len(queue)}] {company['ticker']} ===", file=sys.stderr)
            print(prompt)
        print(
            f"\n[D1-batch] DRY RUN done: would have called LLM for {len(queue)} rows.",
            file=sys.stderr,
        )
        return 0

    # ---------------- LIVE RUN ----------------
    ex = _load_real_extractor()

    mode = "a" if (existing and not args.no_resume) else "w"
    n_ok = 0
    n_fail = 0
    total_in = 0
    total_out = 0
    t_start = time.time()

    with args.output.open(mode) as out:
        for i, company in enumerate(queue, 1):
            t0 = time.time()
            res = ex.extract_one(company, model=args.model, as_of=args.as_of)
            elapsed = time.time() - t0
            usage = res.get("usage") or {}
            in_tok = usage.get("prompt_tokens", 0) or 0
            out_tok = usage.get("completion_tokens", 0) or 0
            total_in += in_tok
            total_out += out_tok

            record = {
                "ticker": company["ticker"],
                "expected_dynamics_family_a_priori": company.get(
                    "expected_dynamics_family_a_priori"
                ),
                "ok": res["ok"],
                "attempts": res["attempts"],
                "elapsed_s": res["elapsed_s"],
                "usage": res["usage"],
                "struct_tuple": res["struct_tuple"],
                "errors": res["errors"],
                "model": args.model,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

            if res["ok"]:
                n_ok += 1
                st = res["struct_tuple"] or {}
                print(
                    f"[D1-batch] [{i}/{len(queue)}] {company['ticker']:6s} OK  "
                    f"family={st.get('dynamics_family'):30s} "
                    f"state={st.get('critical_point_state'):24s} "
                    f"conf={st.get('confidence', 0):.2f} {elapsed:.1f}s",
                    file=sys.stderr,
                )
            else:
                n_fail += 1
                print(
                    f"[D1-batch] [{i}/{len(queue)}] {company['ticker']:6s} FAIL "
                    f"errors={res['errors']}",
                    file=sys.stderr,
                )
            if args.sleep_between:
                time.sleep(args.sleep_between)

    elapsed_total = time.time() - t_start
    print(
        f"\n[D1-batch] done. ok={n_ok} fail={n_fail} elapsed={elapsed_total:.1f}s "
        f"in_tokens={total_in} out_tokens={total_out} model={args.model}",
        file=sys.stderr,
    )
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
