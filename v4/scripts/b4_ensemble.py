#!/usr/bin/env python3
"""B4 — Heterogeneous-vendor ensemble review of universality-class candidates.

B3 (`v4/scripts/b3_ensemble.py`) addressed only WITHIN-vendor disagreement
(3 DeepSeek configurations varying temperature + model size + system prompt
adversariality). B4 closes the documented B3 limitation by adding
ACROSS-vendor / ACROSS-architecture disagreement:

    Reviewer 1: DeepSeek-v4-pro      (T=0.0, rigorous, direct API)
    Reviewer 2: DeepSeek-v4-flash    (T=0.0, lighter, direct API)
    Reviewer 3: Kimi-K2.5            (T=0.0, OpenRouter)

If OpenRouter is unreachable (CN region-block on certain vendors), the
script transparently falls back to a 3-temperature DeepSeek configuration
that at least probes a wider slice of the in-vendor decision surface:

    Fallback reviewer 3: DeepSeek-v4-pro (T=1.0, "high creativity" persona)

(Note: per session memory, OpenRouter Anthropic/Gemini route is blocked from
CN egress; Kimi is *generally* OK but verify-before-trust applies.)

Inputs:
  - 24 candidate-class yaml files in v4/taxonomy/classes/
  - B1 critic priors from v4/results/layer3_critic.jsonl (same as B3)

Outputs:
  - v4/results/B4_heterogeneous_ensemble.jsonl    (24*3 = 72 raw verdicts)
  - v4/results/B4_ensemble_summary.md             (per-class consensus table)

CLI:
  python3 v4/scripts/b4_ensemble.py [--dry-run] [--limit N] [--no-openrouter]

  --dry-run        : load + prompt-build only; no API calls
  --limit N        : process first N classes only (sample run)
  --no-openrouter  : skip Kimi attempt; go straight to DeepSeek fallback
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

# ---------------------------------------------------------------------------
# Paths

REPO = Path(__file__).resolve().parents[2]
CRITIC_IN = REPO / "v4" / "results" / "layer3_critic.jsonl"
YAML_DIR = REPO / "v4" / "taxonomy" / "classes"
OUT_JSONL = REPO / "v4" / "results" / "B4_heterogeneous_ensemble.jsonl"
OUT_SUMMARY = REPO / "v4" / "results" / "B4_ensemble_summary.md"

# ---------------------------------------------------------------------------
# API config

DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"
OPENROUTER_BASE = "https://openrouter.ai/api/v1/chat/completions"


def _load_dotenv() -> None:
    """Minimal .env loader; we avoid python-dotenv to stay zero-dep."""
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

DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

# ---------------------------------------------------------------------------
# Reviewer roster (cross-architecture)


def build_reviewers(allow_openrouter: bool) -> tuple[list[dict], list[str]]:
    """Return (reviewers, notes). reviewers is a list of reviewer configs.

    Each config has: id, vendor, model, base, temperature, max_tokens, system.
    The third slot is Kimi-K2.5 via OpenRouter if available; else a DeepSeek
    creative-persona fallback.
    """
    notes: list[str] = []
    base_system_rigorous = (
        "You are a rigorous universality-class critic for cross-domain "
        "dynamical systems. Apply Clauset 2009 + Stumpf-Porter 2012 "
        "standards: shared equation form + shared scaling exponents + "
        "shared critical mechanism. Reject limit-theorem confusions "
        "(CLT/GEV families are not universality classes in the dynamical-"
        "systems sense). Output JSON only, no commentary."
    )
    base_system_flash = (
        "You are a rigorous universality-class critic. Apply Clauset 2009 + "
        "Stumpf-Porter 2012 standards: shared equation form + shared scaling "
        "exponents + shared critical mechanism. Output JSON only."
    )
    base_system_third_voice = (
        "You are a cross-domain physicist with strong background in both "
        "statistical mechanics and complex-systems theory. Bring a fresh "
        "perspective on the universality-class taxonomy: flag both surface-"
        "similarity traps AND cases where rigorous reviewers might over-"
        "reject genuine cross-domain analogies. Output JSON only."
    )

    reviewers: list[dict] = [
        {
            "id": "deepseek-pro-rigorous",
            "vendor": "deepseek",
            "model": "deepseek-v4-pro",
            "base": DEEPSEEK_BASE,
            "temperature": 0.0,
            "max_tokens": 4000,
            "system": base_system_rigorous,
        },
        {
            "id": "deepseek-flash-rigorous",
            "vendor": "deepseek",
            "model": "deepseek-v4-flash",
            "base": DEEPSEEK_BASE,
            "temperature": 0.0,
            "max_tokens": 2000,
            "system": base_system_flash,
        },
    ]

    if allow_openrouter and OPENROUTER_KEY:
        reviewers.append(
            {
                "id": "kimi-k2.5-rigorous",
                "vendor": "openrouter",
                "model": "moonshotai/kimi-k2",
                "base": OPENROUTER_BASE,
                "temperature": 0.0,
                "max_tokens": 4000,
                "system": base_system_third_voice,
            }
        )
        notes.append("Third reviewer = Kimi-K2.5 via OpenRouter (cross-architecture)")
    else:
        # Fallback: another DeepSeek slot with very different temperature.
        # This still leaves B4 INTRA-vendor for the third slot, but B4's
        # value-add over B3 is documented as conditional on Kimi reachability.
        reviewers.append(
            {
                "id": "deepseek-pro-high-creativity",
                "vendor": "deepseek",
                "model": "deepseek-v4-pro",
                "base": DEEPSEEK_BASE,
                "temperature": 1.0,
                "max_tokens": 4000,
                "system": base_system_third_voice,
            }
        )
        reason = (
            "OPENROUTER_API_KEY missing" if not OPENROUTER_KEY else "--no-openrouter set"
        )
        notes.append(
            f"OpenRouter Kimi-K2.5 unavailable ({reason}); "
            "fallback to DeepSeek-pro T=1.0 (NOT a true cross-architecture probe)"
        )
    return reviewers, notes


# ---------------------------------------------------------------------------
# Prompt template

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
B1 critic rationale (summarized):
{b1_rationale}

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
# Reuse the b3_ensemble yaml-loader and JSON-extractor
#
# b3_ensemble raises at import time if DEEPSEEK_API_KEY is not set. For B4
# --dry-run we want to load without that requirement (the dry-run does no
# API calls). We temporarily set a placeholder DEEPSEEK_API_KEY for the
# import, then restore. This is purely a module-load gate; B4's real API
# path requires a real key checked separately below.

sys.path.insert(0, str(REPO / "v4" / "scripts"))
_restore_deepseek_key: str | None = None
if not os.environ.get("DEEPSEEK_API_KEY"):
    _restore_deepseek_key = ""  # marker: we set a placeholder
    os.environ["DEEPSEEK_API_KEY"] = "placeholder-for-b3-import-only"
try:
    from b3_ensemble import load_yaml_class, extract_json  # noqa: E402
finally:
    if _restore_deepseek_key is not None:
        # Remove the placeholder we added.
        if os.environ.get("DEEPSEEK_API_KEY") == "placeholder-for-b3-import-only":
            del os.environ["DEEPSEEK_API_KEY"]
        # Re-load any real key from .env (in case it was there).
        _load_dotenv()
        DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")


def load_critic_data() -> list[dict[str, Any]]:
    if not CRITIC_IN.exists():
        # B4 can fall back to enumerating the yaml directory directly.
        rows: list[dict[str, Any]] = []
        for p in sorted(YAML_DIR.glob("*.yaml")):
            rows.append({"class_id": p.stem, "review_verdict": "n/a", "confidence": "n/a"})
        return rows
    rows = []
    with open(CRITIC_IN) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Universal API caller


def call_llm(reviewer: dict, user: str) -> tuple[str | None, str | None]:
    """Call DeepSeek or OpenRouter chat-completions. Returns (content, error)."""
    payload = {
        "model": reviewer["model"],
        "messages": [
            {"role": "system", "content": reviewer["system"]},
            {"role": "user", "content": user},
        ],
        "temperature": reviewer["temperature"],
        "max_tokens": reviewer["max_tokens"],
    }
    if reviewer["vendor"] == "deepseek":
        key = DEEPSEEK_KEY
        if not key:
            return None, "DEEPSEEK_API_KEY not set"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
    elif reviewer["vendor"] == "openrouter":
        key = OPENROUTER_KEY
        if not key:
            return None, "OPENROUTER_API_KEY not set"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/dada8899/structural-isomorphism",
            "X-Title": "structural-isomorphism B4 ensemble",
        }
    else:
        return None, f"unknown vendor: {reviewer['vendor']}"

    req = urllib.request.Request(
        reviewer["base"],
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content", "") or ""
        content = content.strip()
        if not content:
            return None, f"empty content (finish_reason={choice.get('finish_reason')})"
        return content, None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return None, f"HTTP {e.code}: {body}"
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}"
    except Exception as e:  # pragma: no cover
        return None, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Prompt builder (mirror of b3)


def build_user_prompt(class_id: str, b1_row: dict, yaml: dict) -> str:
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
        b1_verdict=b1_row.get("review_verdict", "unknown"),
        b1_conf=b1_row.get("confidence", "unknown"),
        b1_rationale=(
            b1_row.get("members_flagged_reason") or b1_row.get("notes") or "(none)"
        )[:600],
    )


# ---------------------------------------------------------------------------
# Consensus + summary writer


def consensus_of(verdicts: list[str]) -> str:
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    for label in ("KEEP", "REJECT", "SPLIT", "MERGE"):
        if counts.get(label, 0) >= 2:
            return label
    return "UNCLEAR"


def write_summary(
    rows: list[dict],
    reviewer_ids: list[str],
    setup_notes: list[str],
    elapsed_s: float,
    n_errors: int,
    n_parse_fail: int,
) -> None:
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["class_id"], []).append(r)

    lines: list[str] = []
    lines.append("# B4 — Heterogeneous-vendor ensemble review summary\n")
    lines.append(f"**Date**: {time.strftime('%Y-%m-%d')}  ")
    lines.append(f"**Reviewers**: {', '.join(reviewer_ids)}  ")
    lines.append(f"**Classes reviewed**: {len(by_class)}  ")
    lines.append(f"**Total verdicts**: {len(rows)}  ")
    lines.append(f"**Errors**: {n_errors}, **Parse failures**: {n_parse_fail}  ")
    lines.append(f"**Total wall time**: {elapsed_s / 60:.1f} min  ")
    lines.append("")
    lines.append("## Setup notes\n")
    for note in setup_notes:
        lines.append(f"- {note}")
    lines.append("")

    # Per-class verdict table
    lines.append("## Per-class verdict table\n")
    header = "| class_id | " + " | ".join(reviewer_ids) + " | B4 consensus | avg_conf |"
    lines.append(header)
    lines.append("|" + "|".join(["---"] * (header.count("|") - 1)) + "|")

    b4_verdict_counts: dict[str, int] = {}
    for cid in sorted(by_class.keys()):
        recs = by_class[cid]
        per_reviewer: dict[str, dict] = {r["model_id"]: r for r in recs}
        row_verdicts = [
            per_reviewer.get(rid, {}).get("verdict", "MISSING") for rid in reviewer_ids
        ]
        consensus = consensus_of(row_verdicts)
        b4_verdict_counts[consensus] = b4_verdict_counts.get(consensus, 0) + 1
        avg_conf = sum(r.get("confidence", 0.0) for r in recs) / max(1, len(recs))
        lines.append(
            f"| `{cid}` | "
            + " | ".join(row_verdicts)
            + f" | **{consensus}** | {avg_conf:.2f} |"
        )

    lines.append("\n## B4 consensus distribution\n")
    for k in ("KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR"):
        lines.append(f"- **{k}**: {b4_verdict_counts.get(k, 0)}")

    # Comparison hook to B3 (only available if B3 jsonl exists)
    b3_jsonl = REPO / "v4" / "results" / "B3_ensemble_review.jsonl"
    if b3_jsonl.exists():
        lines.append("\n## B3 vs B4 agreement (see B3_taxonomy_v2.jsonl for B3 consensus)\n")
        lines.append("Compare B4 consensus column above with B3 consensus from B3_taxonomy_v2.jsonl.")

    lines.append("\n## Methodology notes\n")
    lines.append(
        "- B4 adds cross-vendor / cross-architecture probe to address the "
        "B3 limitation that 3 DeepSeek reviewers probe within-model "
        "confidence drift but not architectural disagreement."
    )
    lines.append(
        "- If Kimi-K2.5 reachable via OpenRouter, third reviewer is "
        "cross-architecture; else fallback is DeepSeek-pro T=1.0 which is "
        "in-vendor and therefore a WEAKER cross-architecture probe (logged "
        "in setup notes)."
    )
    lines.append(
        "- Consensus rule: majority (>=2/3) for KEEP/REJECT/SPLIT/MERGE; "
        "else UNCLEAR. Identical to B3 for compatibility."
    )
    lines.append("")

    OUT_SUMMARY.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="B4 heterogeneous-vendor ensemble review."
    )
    ap.add_argument("--dry-run", action="store_true", help="No API calls, just build prompts.")
    ap.add_argument("--limit", type=int, default=0, help="Process first N classes only.")
    ap.add_argument(
        "--no-openrouter",
        action="store_true",
        help="Skip Kimi attempt; go straight to in-vendor fallback.",
    )
    args = ap.parse_args()

    reviewers, setup_notes = build_reviewers(allow_openrouter=not args.no_openrouter)
    reviewer_ids = [r["id"] for r in reviewers]
    classes = load_critic_data()
    if args.limit and args.limit > 0:
        classes = classes[: args.limit]

    print(f"[B4] Loaded {len(classes)} candidate classes", file=sys.stderr)
    print(f"[B4] Reviewers: {reviewer_ids}", file=sys.stderr)
    for note in setup_notes:
        print(f"[B4] note: {note}", file=sys.stderr)
    print(
        f"[B4] Expected calls: {len(classes)} x {len(reviewers)} = "
        f"{len(classes) * len(reviewers)}",
        file=sys.stderr,
    )

    if args.dry_run:
        # Just exercise prompt-build path on first class as a smoke test.
        if classes:
            cls = classes[0]
            yaml = load_yaml_class(cls["class_id"])
            prompt = build_user_prompt(cls["class_id"], cls, yaml)
            print(
                f"[B4] DRY_RUN: sample prompt length={len(prompt)} chars",
                file=sys.stderr,
            )
            print(
                f"[B4] DRY_RUN: first class = {cls['class_id']}",
                file=sys.stderr,
            )
        print("[B4] DRY_RUN: skipping API calls. Exit OK.", file=sys.stderr)
        return 0

    if not DEEPSEEK_KEY:
        print(
            "[B4] FATAL: DEEPSEEK_API_KEY not set. "
            "Export it or place in .env then re-run.",
            file=sys.stderr,
        )
        return 1

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    all_rows: list[dict] = []
    n_errors = 0
    n_parse_fail = 0

    with open(OUT_JSONL, "w") as out:
        for ci, cls in enumerate(classes, 1):
            class_id = cls["class_id"]
            yaml = load_yaml_class(class_id)
            user_prompt = build_user_prompt(class_id, cls, yaml)
            print(f"\n[B4] [{ci}/{len(classes)}] {class_id}", file=sys.stderr)

            for r in reviewers:
                t0 = time.time()
                raw, err = call_llm(r, user_prompt)
                elapsed = time.time() - t0
                if raw is None:
                    record = {
                        "class_id": class_id,
                        "model_id": r["id"],
                        "verdict": "ERROR",
                        "confidence": 0.0,
                        "rationale": err or "no content",
                        "elapsed_s": round(elapsed, 1),
                    }
                    n_errors += 1
                else:
                    parsed = extract_json(raw)
                    if parsed is None:
                        record = {
                            "class_id": class_id,
                            "model_id": r["id"],
                            "verdict": "PARSE_FAIL",
                            "confidence": 0.0,
                            "rationale": raw[:300],
                            "elapsed_s": round(elapsed, 1),
                        }
                        n_parse_fail += 1
                    else:
                        verdict = str(parsed.get("verdict", "UNCLEAR")).upper().strip()
                        if verdict.startswith("MERGE"):
                            verdict = "MERGE"
                        if verdict.startswith("SPLIT"):
                            verdict = "SPLIT"
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
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                print(
                    f"  {r['id']:30s} | {record['verdict']:10s} | "
                    f"conf={record['confidence']:.2f} | {elapsed:5.1f}s",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t_start
    print(
        f"\n[B4] Done: {len(all_rows)} verdicts in {elapsed_total / 60:.1f} min "
        f"(errors={n_errors}, parse_fail={n_parse_fail})",
        file=sys.stderr,
    )
    write_summary(all_rows, reviewer_ids, setup_notes, elapsed_total, n_errors, n_parse_fail)
    print(f"[B4] Wrote {OUT_JSONL}", file=sys.stderr)
    print(f"[B4] Wrote {OUT_SUMMARY}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
