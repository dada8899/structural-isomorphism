#!/usr/bin/env python3
"""B4 DeepSeek heterogeneous ensemble rerun (session #8, 2026-05-14).

Context: user refused OpenRouter Kimi as cross-architecture probe (CN
region-block on certain vendors). Instead, this rerun uses **3 DeepSeek
direct-API reviewer configurations** as a heterogeneity proxy:

    reviewer_A: deepseek-v4-pro    T=0.0   (deterministic, rigorous baseline)
    reviewer_B: deepseek-v4-flash  T=0.0   (different model class, deterministic)
    reviewer_C: deepseek-v4-pro    T=0.7   (sampled chat, diversity proxy)

NOTE on model IDs: the task spec asked for `deepseek-chat` / `deepseek-reasoner`
(official DeepSeek model names). At runtime, this account's API exposes only
`deepseek-v4-pro` and `deepseek-v4-flash` (verified via `GET /models`). We
substitute v4-pro/v4-flash with 3 temperature/system-prompt variations as the
closest available proxy for the requested 3-model heterogeneous ensemble.

Difference vs existing v4/scripts/b4_ensemble.py:
  - Existing b4_ensemble.py also runs 3-reviewer DeepSeek (when OpenRouter
    unavailable), BUT the third slot is pro T=1.0 with a "cross-domain
    physicist" persona system prompt — explicitly high-creativity. This
    rerun uses pro T=0.7 with a plain "chat baseline" system prompt to
    probe the temperature-driven diversity slice closer to typical chat
    output (less adversarial persona).
  - Cost-guarded: aborts if running spend > $5 USD budget.
  - Per-call retry: 2 retries on JSON parse failure (strict schema).

Input:  v4/results/B3_taxonomy_v2.jsonl  (21 B3 classes)
Output: v4/results/B4_deepseek_ensemble.jsonl  (21*3 = 63 verdicts)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
TAXONOMY_IN = REPO / "v4" / "results" / "B3_taxonomy_v2.jsonl"
YAML_DIR = REPO / "v4" / "taxonomy" / "classes"
DEFAULT_OUT = REPO / "v4" / "results" / "B4_deepseek_ensemble.jsonl"

DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"


def _load_dotenv() -> None:
    """Minimal .env loader — keep zero-dep."""
    env_path = REPO / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

# ---------------------------------------------------------------------------
# Reviewer roster (3 DeepSeek-only configurations)

SYS_RIGOROUS = (
    "You are a rigorous universality-class critic for cross-domain "
    "dynamical systems. Apply Clauset 2009 + Stumpf-Porter 2012 "
    "standards: shared equation form + shared scaling exponents + "
    "shared critical mechanism. Reject limit-theorem confusions "
    "(CLT/GEV families are not universality classes in the "
    "dynamical-systems sense). Output JSON only, no commentary."
)
SYS_FLASH = (
    "You are a rigorous universality-class critic. Apply Clauset 2009 + "
    "Stumpf-Porter 2012 standards: shared equation form + shared scaling "
    "exponents + shared critical mechanism. Output JSON only."
)
SYS_CHAT_BASELINE = (
    "You are a domain expert reviewing candidate universality classes for "
    "cross-domain dynamical-systems taxonomy. Judge each class on "
    "(a) shared dynamic equation / normal form, (b) shared scaling "
    "exponents or critical exponents, (c) shared critical mechanism. "
    "Output strict JSON only."
)

REVIEWERS: list[dict[str, Any]] = [
    {
        "id": "deepseek-v4-pro-T0",
        "model": "deepseek-v4-pro",
        "temperature": 0.0,
        "max_tokens": 4000,
        "system": SYS_RIGOROUS,
    },
    {
        "id": "deepseek-v4-flash-T0",
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "max_tokens": 2000,
        "system": SYS_FLASH,
    },
    {
        "id": "deepseek-v4-pro-T07-chat",
        "model": "deepseek-v4-pro",
        "temperature": 0.7,
        "max_tokens": 4000,
        "system": SYS_CHAT_BASELINE,
    },
]

# DeepSeek published pricing (per 1M tokens, USD); deepseek-v4-* same scale
# as official deepseek-chat: input ~$0.27 / output ~$1.10. We use these as
# rough cost-tracking constants for budget guard.
COST_PER_M_INPUT_USD = 0.27
COST_PER_M_OUTPUT_USD = 1.10
COST_BUDGET_USD = 5.0

PROMPT_TEMPLATE = """Review this candidate universality class for whether it forms a valid cross-domain universality class in the dynamical-systems sense (shared equation form + shared scaling exponents + shared critical mechanism).

Class id: {class_id}
Display name: {display_name}
Hub phenomenon: {hub}
Shared equation / normal form:
{shared_eq}

Key invariants:
{invariants}

Positive examples (members claimed by Layer-3 auto-curator):
{positive_examples}

Negative examples / boundary cases:
{negative_examples}

Notes from yaml:
{notes}

B1 critic prior verdict: {b1_verdict} (confidence: {b1_conf})
B3 consensus prior: {b3_consensus} (avg conf: {b3_conf})

Output JSON only, in this exact schema:
{{
  "class_id": "{class_id}",
  "model_id": "<your-reviewer-id>",
  "verdict": "KEEP" | "REJECT" | "UNCLEAR" | "SPLIT" | "MERGE",
  "confidence": <float 0.0-1.0>,
  "rationale": "<2-4 sentences on why; cite mechanism + exponent + equation form>"
}}

Decision guide:
- KEEP: shared mechanism + shared exponents (or shared dynamic equation form) supported by >= 3 positive members.
- REJECT: limit-theorem only / surface similarity / members from incompatible mechanisms.
- SPLIT: real class but heterogeneous; should be split into 2+ tighter classes.
- MERGE: this class is a near-duplicate of another standard class and should be merged.
- UNCLEAR: cannot determine from this brief; needs more empirical data.

Output ONLY the JSON object, no preamble or explanation outside the JSON.
"""

# ---------------------------------------------------------------------------
# Reuse b3_ensemble yaml-loader and JSON-extractor (already proven). The
# import path requires DEEPSEEK_API_KEY to be set (b3_ensemble checks at
# module-load) which is already true since we _load_dotenv above.

sys.path.insert(0, str(REPO / "v4" / "scripts"))
from b3_ensemble import load_yaml_class, extract_json  # noqa: E402


def load_b3_taxonomy() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with open(TAXONOMY_IN) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_user_prompt(class_id: str, b3_row: dict, yaml: dict) -> str:
    invariants_block = "\n".join(
        f"- {x}" for x in yaml.get("key_invariants", []) or ["(none)"]
    )
    pos_block = "\n".join(
        f"- {x}" for x in (yaml.get("positive_examples") or [])[:8]
    ) or "(none)"
    neg_block = "\n".join(
        f"- {x}" for x in (yaml.get("negative_examples") or [])[:6]
    ) or "(none)"
    return PROMPT_TEMPLATE.format(
        class_id=class_id,
        display_name=yaml.get("display_name", "") or class_id,
        hub=yaml.get("hub", "")[:400],
        shared_eq=(yaml.get("shared_equation") or "(none)")[:800],
        invariants=invariants_block[:1200],
        positive_examples=pos_block[:1200],
        negative_examples=neg_block[:800],
        notes=(yaml.get("notes") or "(none)")[:400],
        b1_verdict=b3_row.get("b1_verdict", "unknown"),
        b1_conf=b3_row.get("b1_confidence", "unknown"),
        b3_consensus=b3_row.get("b3_consensus", "unknown"),
        b3_conf=b3_row.get("b3_avg_confidence", "unknown"),
    )


def call_deepseek(reviewer: dict, user: str, api_key: str) -> tuple[str | None, str | None, dict]:
    """Call DeepSeek chat-completions. Returns (content, error, usage_dict).

    usage_dict has prompt_tokens, completion_tokens, total_tokens (may be empty
    if the API didn't return usage).
    """
    payload = {
        "model": reviewer["model"],
        "messages": [
            {"role": "system", "content": reviewer["system"]},
            {"role": "user", "content": user},
        ],
        "temperature": reviewer["temperature"],
        "max_tokens": reviewer["max_tokens"],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        DEEPSEEK_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    usage_out: dict = {}
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        usage_out = data.get("usage") or {}
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content", "") or ""
        content = content.strip()
        if not content:
            return None, f"empty content (finish_reason={choice.get('finish_reason')})", usage_out
        return content, None, usage_out
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {body}", usage_out
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}", usage_out
    except Exception as e:  # pragma: no cover
        return None, f"{type(e).__name__}: {e}", usage_out


def call_with_retries(
    reviewer: dict, user: str, api_key: str, max_retries: int = 2
) -> tuple[dict | None, str | None, float, dict]:
    """Call DeepSeek with strict JSON parse + 2 retries. Returns (parsed,
    error, elapsed_s, usage). parsed is None if all retries failed."""
    t0 = time.time()
    last_err: str | None = None
    last_usage: dict = {}
    for attempt in range(max_retries + 1):
        raw, err, usage = call_deepseek(reviewer, user, api_key)
        # accumulate usage even if parse fails (we still spent tokens)
        for k, v in (usage or {}).items():
            last_usage[k] = last_usage.get(k, 0) + (v if isinstance(v, (int, float)) else 0)
        if raw is None:
            last_err = err
            if attempt < max_retries:
                time.sleep(0.5 * (attempt + 1))
                continue
            break
        parsed = extract_json(raw)
        if parsed is not None and isinstance(parsed.get("verdict"), str):
            return parsed, None, time.time() - t0, last_usage
        last_err = f"JSON parse fail / missing verdict (raw[:200]={raw[:200]!r})"
        if attempt < max_retries:
            time.sleep(0.5 * (attempt + 1))
            continue
    return None, last_err, time.time() - t0, last_usage


def estimate_cost(usage_total: dict) -> float:
    p = usage_total.get("prompt_tokens", 0) or 0
    c = usage_total.get("completion_tokens", 0) or 0
    return (p / 1_000_000) * COST_PER_M_INPUT_USD + (c / 1_000_000) * COST_PER_M_OUTPUT_USD


def normalize_verdict(v: str) -> str:
    v = (v or "").upper().strip()
    if v.startswith("MERGE"):
        return "MERGE"
    if v.startswith("SPLIT"):
        return "SPLIT"
    if v not in {"KEEP", "REJECT", "MERGE", "SPLIT", "UNCLEAR"}:
        return "UNCLEAR"
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="B4 DeepSeek heterogeneous ensemble rerun.")
    ap.add_argument("--input", default=str(TAXONOMY_IN), help="B3 taxonomy JSONL input")
    ap.add_argument("--output", default=str(DEFAULT_OUT), help="ensemble output JSONL")
    ap.add_argument("--limit", type=int, default=0, help="process first N classes only")
    ap.add_argument("--budget", type=float, default=COST_BUDGET_USD, help="USD cost budget")
    ap.add_argument("--dry-run", action="store_true", help="prompt-build only, no API calls")
    args = ap.parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key and not args.dry_run:
        print("[B4-deepseek] FATAL: DEEPSEEK_API_KEY not set", file=sys.stderr)
        return 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_b3_taxonomy()
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    reviewer_ids = [r["id"] for r in REVIEWERS]
    print(f"[B4-deepseek] Classes: {len(rows)} | Reviewers: {reviewer_ids}", file=sys.stderr)
    print(
        f"[B4-deepseek] Expected calls: {len(rows)} x {len(REVIEWERS)} = "
        f"{len(rows) * len(REVIEWERS)} | Budget: ${args.budget:.2f}",
        file=sys.stderr,
    )

    if args.dry_run:
        if rows:
            yml = load_yaml_class(rows[0]["class_id"])
            p = build_user_prompt(rows[0]["class_id"], rows[0], yml)
            print(f"[B4-deepseek] DRY: prompt len={len(p)} chars", file=sys.stderr)
        return 0

    t_start = time.time()
    all_rows: list[dict] = []
    usage_total: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    n_errors = 0
    n_parse_fail = 0
    n_retries = 0
    aborted = False

    with open(out_path, "w") as fout:
        for ci, b3_row in enumerate(rows, 1):
            class_id = b3_row["class_id"]
            yml = load_yaml_class(class_id)
            user_prompt = build_user_prompt(class_id, b3_row, yml)
            print(f"\n[B4-deepseek] [{ci}/{len(rows)}] {class_id}", file=sys.stderr)

            for r in REVIEWERS:
                # Budget guard before each call
                current_cost = estimate_cost(usage_total)
                if current_cost > args.budget:
                    print(
                        f"[B4-deepseek] BUDGET EXCEEDED ${current_cost:.4f} > "
                        f"${args.budget:.2f}, abort",
                        file=sys.stderr,
                    )
                    aborted = True
                    break

                parsed, err, elapsed, usage = call_with_retries(
                    r, user_prompt, api_key, max_retries=2
                )
                for k, v in (usage or {}).items():
                    if isinstance(v, (int, float)):
                        usage_total[k] = usage_total.get(k, 0) + v

                if parsed is None:
                    record = {
                        "class_id": class_id,
                        "model_id": r["id"],
                        "verdict": "ERROR" if "JSON" not in (err or "") else "PARSE_FAIL",
                        "confidence": 0.0,
                        "rationale": (err or "")[:300],
                        "elapsed_s": round(elapsed, 1),
                    }
                    if record["verdict"] == "ERROR":
                        n_errors += 1
                    else:
                        n_parse_fail += 1
                else:
                    verdict = normalize_verdict(str(parsed.get("verdict", "UNCLEAR")))
                    try:
                        conf = float(parsed.get("confidence", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        conf = 0.0
                    record = {
                        "class_id": class_id,
                        "model_id": r["id"],
                        "verdict": verdict,
                        "confidence": conf,
                        "rationale": str(parsed.get("rationale", ""))[:500],
                        "elapsed_s": round(elapsed, 1),
                    }
                all_rows.append(record)
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
                fout.flush()
                running_cost = estimate_cost(usage_total)
                print(
                    f"  {r['id']:30s} | {record['verdict']:10s} | "
                    f"conf={record['confidence']:.2f} | {elapsed:5.1f}s | "
                    f"spent=${running_cost:.4f}",
                    file=sys.stderr,
                )
            if aborted:
                break

    elapsed_total = time.time() - t_start
    final_cost = estimate_cost(usage_total)
    print(
        f"\n[B4-deepseek] Done: {len(all_rows)} verdicts in "
        f"{elapsed_total/60:.1f} min | cost=${final_cost:.4f} | "
        f"errors={n_errors} parse_fail={n_parse_fail} retries={n_retries}"
        + (" | ABORTED(budget)" if aborted else ""),
        file=sys.stderr,
    )
    # Also write a tiny meta line at end for downstream tooling
    print(f"[B4-deepseek] tokens: {usage_total}", file=sys.stderr)
    return 0 if not aborted else 2


if __name__ == "__main__":
    sys.exit(main())
