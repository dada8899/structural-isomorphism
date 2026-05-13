#!/usr/bin/env python3
"""B3 — Multi-model ensemble review of universality-class candidates.

Calls DeepSeek API directly (bypass OpenRouter CN region-block) with
3 reviewer configurations (v4-pro rigorous T=0.0 / v4-flash rigorous T=0.0 /
v4-pro creative T=0.6) and aggregates verdicts per class.

For each of the 21 candidate universality classes (curated by Layer 3 LLM
auto-curator and reviewed by the B1 critic), this script invokes three
DeepSeek reviewers in independent calls. Outputs:

  v4/results/B3_ensemble_review.jsonl   # 21*3 = 63 raw verdicts
  v4/results/B3_ensemble_summary.md     # per-class consensus table
  v4/results/B3_taxonomy_v2.jsonl       # merged B1 + B3 final taxonomy v2

Limitation: same-model-family ensemble probes within-model confidence drift
(temperature + reasoning-length variations), not cross-architecture
disagreement. Kimi / GLM-5 cross-family ensemble deferred — OpenRouter is
region-blocked from CN and backup-router base URLs are unverified.
"""

from __future__ import annotations

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
AUTO_CURATED = REPO / "v4" / "results" / "layer3_auto_curated.jsonl"
YAML_DIR = REPO / "v4" / "taxonomy" / "classes"
OUT_JSONL = REPO / "v4" / "results" / "B3_ensemble_review.jsonl"
OUT_SUMMARY = REPO / "v4" / "results" / "B3_ensemble_summary.md"
TAXONOMY_OUT = REPO / "v4" / "results" / "B3_taxonomy_v2.jsonl"

# ---------------------------------------------------------------------------
# DeepSeek API config

DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    raise RuntimeError(
        "DEEPSEEK_API_KEY env var is not set. "
        "Get a key at https://platform.deepseek.com and export it before running:\n"
        "    export DEEPSEEK_API_KEY='sk-...'\n"
        "Or copy .env.example to .env and source it. See "
        "docs/security/api-key-rotation-runbook.md for the rotation runbook."
    )

REVIEWERS = [
    {
        "id": "deepseek-pro-rigorous",
        "model": "deepseek-v4-pro",
        "temperature": 0.0,
        "max_tokens": 4000,
        "system": (
            "You are a rigorous universality-class critic for cross-domain "
            "dynamical systems. Apply Clauset 2009 + Stumpf-Porter 2012 "
            "standards: shared equation form + shared scaling exponents + "
            "shared critical mechanism. Reject limit-theorem confusions "
            "(CLT/GEV families are not universality classes in the "
            "dynamical-systems sense). Output JSON only, no commentary."
        ),
    },
    {
        "id": "deepseek-flash-rigorous",
        "model": "deepseek-v4-flash",
        "temperature": 0.0,
        "max_tokens": 2000,
        "system": (
            "You are a rigorous universality-class critic. Apply Clauset 2009 "
            "+ Stumpf-Porter 2012 standards: shared equation form + shared "
            "scaling exponents + shared critical mechanism. Output JSON only."
        ),
    },
    {
        "id": "deepseek-pro-creative",
        "model": "deepseek-v4-pro",
        "temperature": 0.6,
        "max_tokens": 4000,
        "system": (
            "You are a creative dissenter on universality-class taxonomy. "
            "Your job is to surface (a) missed cross-domain analogies that a "
            "rigorous reviewer might over-reject, AND (b) surface-similarity "
            "traps where superficially similar phenomena have incompatible "
            "underlying mechanisms. Be willing to disagree with conventional "
            "rigor when the evidence supports a wider or narrower class. "
            "Output JSON only."
        ),
    },
]

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
- KEEP: shared mechanism + shared exponents (or shared dynamic equation form) supported by ≥3 positive members.
- REJECT: limit-theorem only / surface similarity / members from incompatible mechanisms.
- SPLIT: real class but heterogeneous; should be split into 2+ tighter classes.
- MERGE: this class is a near-duplicate of another standard class and should be merged.
- UNCLEAR: cannot determine from this brief; needs more empirical data.

Output ONLY the JSON object, no preamble or explanation outside the JSON.
"""

# ---------------------------------------------------------------------------
# Data loading


def load_yaml_class(class_id: str) -> dict[str, Any]:
    """Minimal yaml loader — we only need a few fields, so we parse manually
    instead of pulling in PyYAML (avoids dependency drift)."""
    path = YAML_DIR / f"{class_id}.yaml"
    if not path.exists():
        return {}
    text = path.read_text()
    out: dict[str, Any] = {
        "display_name": "",
        "hub": "",
        "shared_equation": "",
        "key_invariants": [],
        "positive_examples": [],
        "negative_examples": [],
        "notes": "",
    }
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("display_name:"):
            out["display_name"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("hub_phenomenon:"):
            out["hub"] = line.split(":", 1)[1].strip().strip('"')
        elif line.startswith("shared_equation:"):
            # collect block scalar
            i += 1
            buf = []
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                buf.append(lines[i].strip())
                i += 1
            out["shared_equation"] = "\n".join(buf).strip()
            continue
        elif line.startswith("key_invariants:"):
            i += 1
            inv: list[str] = []
            while i < len(lines) and lines[i].startswith("  - "):
                inv.append(lines[i][4:].strip().strip('"'))
                i += 1
            out["key_invariants"] = inv
            continue
        elif line.startswith("positive_examples:"):
            i += 1
            ex: list[str] = []
            cur_phen = None
            while i < len(lines) and (
                lines[i].startswith("  - ") or lines[i].startswith("    ")
            ):
                if lines[i].startswith("  - phenomenon:"):
                    cur_phen = lines[i].split(":", 1)[1].strip().strip('"')
                    ex.append(cur_phen)
                i += 1
            out["positive_examples"] = ex
            continue
        elif line.startswith("negative_examples:"):
            i += 1
            ex2: list[str] = []
            while i < len(lines) and (
                lines[i].startswith("  - ") or lines[i].startswith("    ")
            ):
                if lines[i].startswith("  - phenomenon:"):
                    p = lines[i].split(":", 1)[1].strip().strip('"')
                    ex2.append(p)
                i += 1
            out["negative_examples"] = ex2
            continue
        elif line.startswith("notes:"):
            # block scalar starting with |
            i += 1
            buf2 = []
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                buf2.append(lines[i].strip())
                i += 1
            out["notes"] = "\n".join(buf2).strip()
            continue
        i += 1
    return out


def load_critic_data() -> list[dict[str, Any]]:
    rows = []
    with open(CRITIC_IN) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# DeepSeek call


def call_deepseek(
    model: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str | None, str | None]:
    """Returns (content_text, error_msg). content_text is None on error."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        DEEPSEEK_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
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


def extract_json(raw: str) -> dict | None:
    """Best-effort extract JSON object from raw string (strip markdown fences,
    find outermost {...} pair, parse)."""
    s = raw.strip()
    # strip leading ```json or ``` fences
    if s.startswith("```"):
        # remove first fence line
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1]
        # remove trailing ``` if present
        if s.endswith("```"):
            s = s[: -3].rstrip()
    # locate JSON object
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < 0 or j <= i:
        return None
    candidate = s[i : j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # try to be lenient: remove trailing commas
        cleaned = candidate.replace(",\n}", "\n}").replace(",\n]", "\n]")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Main loop


def build_user_prompt(class_id: str, b1_row: dict, yaml: dict) -> str:
    invariants_block = "\n".join(f"- {x}" for x in yaml.get("key_invariants", []) or ["(none)"])
    pos_block = "\n".join(f"- {x}" for x in (yaml.get("positive_examples") or [])[:8]) or "(none)"
    neg_block = "\n".join(f"- {x}" for x in (yaml.get("negative_examples") or [])[:6]) or "(none)"
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
        b1_rationale=(b1_row.get("members_flagged_reason") or b1_row.get("notes") or "(none)")[:600],
    )


def main() -> int:
    classes = load_critic_data()
    print(f"[B3] Loaded {len(classes)} candidate classes from B1 critic JSONL", file=sys.stderr)
    print(f"[B3] Reviewers: {[r['id'] for r in REVIEWERS]}", file=sys.stderr)
    print(f"[B3] Expected calls: {len(classes)} x {len(REVIEWERS)} = {len(classes) * len(REVIEWERS)}", file=sys.stderr)

    t_start = time.time()
    all_rows: list[dict] = []
    n_errors = 0
    n_parse_fail = 0

    with open(OUT_JSONL, "w") as out:
        for ci, cls in enumerate(classes, 1):
            class_id = cls["class_id"]
            yaml = load_yaml_class(class_id)
            user_prompt = build_user_prompt(class_id, cls, yaml)
            print(f"\n[B3] [{ci}/{len(classes)}] {class_id}", file=sys.stderr)

            for r in REVIEWERS:
                t0 = time.time()
                raw, err = call_deepseek(
                    r["model"], r["system"], user_prompt, r["temperature"], r["max_tokens"]
                )
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
                        conf_val = parsed.get("confidence")
                        try:
                            conf = float(conf_val) if conf_val is not None else 0.0
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
                    f"  {r['id']:25s} | {record['verdict']:10s} | "
                    f"conf={record['confidence']:.2f} | {elapsed:5.1f}s",
                    file=sys.stderr,
                )

    elapsed_total = time.time() - t_start
    print(
        f"\n[B3] Done: {len(all_rows)} verdicts in {elapsed_total/60:.1f} min "
        f"(errors={n_errors}, parse_fail={n_parse_fail})",
        file=sys.stderr,
    )

    write_summary(all_rows, classes, elapsed_total, n_errors, n_parse_fail)
    write_taxonomy_v2(all_rows, classes)
    print(f"[B3] Wrote {OUT_JSONL}", file=sys.stderr)
    print(f"[B3] Wrote {OUT_SUMMARY}", file=sys.stderr)
    print(f"[B3] Wrote {TAXONOMY_OUT}", file=sys.stderr)
    return 0


def consensus_of(verdicts: list[str]) -> str:
    counts: dict[str, int] = {}
    for v in verdicts:
        counts[v] = counts.get(v, 0) + 1
    # priority order: majority KEEP/REJECT > SPLIT/MERGE > else UNCLEAR
    for label in ("KEEP", "REJECT", "SPLIT", "MERGE"):
        if counts.get(label, 0) >= 2:
            return label
    return "UNCLEAR"


def write_summary(rows: list[dict], classes_in: list[dict], elapsed_s: float,
                  n_errors: int, n_parse_fail: int) -> None:
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["class_id"], []).append(r)

    reviewer_ids = [r["id"] for r in REVIEWERS]
    b1_by_class = {c["class_id"]: c for c in classes_in}

    lines: list[str] = []
    lines.append("# B3 — Multi-model ensemble review summary\n")
    lines.append("**Date**: 2026-05-13  ")
    lines.append("**Reviewers**: 3 (deepseek-v4-pro rigorous T=0.0, deepseek-v4-flash rigorous T=0.0, deepseek-v4-pro creative T=0.6)  ")
    lines.append(f"**Classes reviewed**: {len(by_class)}  ")
    lines.append(f"**Total verdicts**: {len(rows)}  ")
    lines.append(f"**Errors**: {n_errors}, **Parse failures**: {n_parse_fail}  ")
    lines.append(f"**Total wall time**: {elapsed_s/60:.1f} min  ")
    lines.append("")

    # Per-class table
    lines.append("## Per-class verdict table\n")
    header = "| class_id | B1 | " + " | ".join(reviewer_ids) + " | B3 consensus | avg_conf |"
    lines.append(header)
    lines.append("|" + "|".join(["---"] * (header.count("|") - 1)) + "|")

    b3_verdict_counts: dict[str, int] = {}
    for cid in sorted(by_class.keys()):
        recs = by_class[cid]
        per_reviewer: dict[str, dict] = {r["model_id"]: r for r in recs}
        row_verdicts = [per_reviewer.get(rid, {}).get("verdict", "MISSING") for rid in reviewer_ids]
        consensus = consensus_of(row_verdicts)
        b3_verdict_counts[consensus] = b3_verdict_counts.get(consensus, 0) + 1
        avg_conf = sum(r.get("confidence", 0.0) for r in recs) / max(1, len(recs))
        b1_verdict = b1_by_class.get(cid, {}).get("review_verdict", "?")
        lines.append(
            f"| `{cid}` | {b1_verdict} | "
            + " | ".join(row_verdicts)
            + f" | **{consensus}** | {avg_conf:.2f} |"
        )

    # Aggregate stats
    lines.append("\n## B3 consensus distribution\n")
    for k in ("KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR"):
        lines.append(f"- **{k}**: {b3_verdict_counts.get(k, 0)}")

    # Raw verdict distribution
    verdict_counts: dict[str, int] = {}
    for r in rows:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1
    lines.append("\n## Raw verdict distribution (across all 63 calls)\n")
    for k in sorted(verdict_counts, key=lambda x: -verdict_counts[x]):
        lines.append(f"- **{k}**: {verdict_counts[k]}")

    # B1 vs B3 agreement
    lines.append("\n## B1 critic vs B3 ensemble agreement\n")
    agree = 0
    disagree = 0
    for cid in by_class:
        b1 = b1_by_class.get(cid, {}).get("review_verdict", "")
        recs = by_class[cid]
        b3_cons = consensus_of([per["verdict"] for per in recs])
        b1_simple = "KEEP" if b1.startswith("KEEP") else ("REJECT" if b1.startswith("REJECT") else ("SPLIT" if b1.startswith("SPLIT") else ("MERGE" if b1.startswith("MERGE") else "OTHER")))
        if b1_simple == b3_cons:
            agree += 1
        else:
            disagree += 1
    lines.append(f"- Agree (B1 simplified == B3 consensus): **{agree}** / {len(by_class)}")
    lines.append(f"- Disagree: **{disagree}** / {len(by_class)}")

    # Methodology
    lines.append("\n## Methodology notes\n")
    lines.append("- 3 DeepSeek-only reviewers (same vendor, different model/temperature configurations).")
    lines.append("- v4-pro @ T=0.0 = main rigorous reviewer (full chain-of-thought reasoning).")
    lines.append("- v4-flash @ T=0.0 = faster light-weight reviewer (less reasoning depth, similar prompt).")
    lines.append("- v4-pro @ T=0.6 = creative dissenter system prompt (probes confidence drift via temperature + adversarial role).")
    lines.append("- Cross-family ensemble (Kimi / GLM-5) NOT yet wired due to OpenRouter CN region-block + unverified backup-router base URLs.")
    lines.append("- **Limitation**: same-model-family ensemble probes within-model confidence drift, not architectural disagreement. Will be addressed in B4+ with verified cross-vendor router.")
    lines.append("- Consensus rule: majority (≥2/3) for KEEP/REJECT/SPLIT/MERGE; else UNCLEAR.")
    lines.append("")

    OUT_SUMMARY.write_text("\n".join(lines))


def write_taxonomy_v2(rows: list[dict], classes_in: list[dict]) -> None:
    """Merge B1 critic + B3 ensemble into final taxonomy v2 (one record per class)."""
    b1_by_class = {c["class_id"]: c for c in classes_in}
    by_class: dict[str, list[dict]] = {}
    for r in rows:
        by_class.setdefault(r["class_id"], []).append(r)

    with open(TAXONOMY_OUT, "w") as out:
        for cid in sorted(by_class.keys()):
            b1_full = b1_by_class.get(cid, {})
            b1_verdict = b1_full.get("review_verdict", "MISSING")
            b1_conf = b1_full.get("confidence", "n/a")
            b3_recs = by_class[cid]
            b3_verdicts = [r["verdict"] for r in b3_recs]
            b3_confs = [r["confidence"] for r in b3_recs]
            b3_cons = consensus_of(b3_verdicts)
            b3_avg_conf = sum(b3_confs) / max(1, len(b3_confs))

            # final verdict logic
            b1_simple = (
                "KEEP" if b1_verdict.startswith("KEEP")
                else "REJECT" if b1_verdict.startswith("REJECT")
                else "SPLIT" if b1_verdict.startswith("SPLIT")
                else "MERGE" if b1_verdict.startswith("MERGE")
                else "OTHER"
            )
            if b1_simple == "KEEP" and b3_cons == "KEEP":
                final = "KEEP_strong"
            elif b1_simple == "REJECT" and b3_cons == "REJECT":
                final = "REJECT_strong"
            elif b1_simple == "SPLIT" and b3_cons == "SPLIT":
                final = "SPLIT_strong"
            elif b1_simple == "MERGE" and b3_cons == "MERGE":
                final = "MERGE_strong"
            elif b1_simple == "KEEP" and b3_cons in ("REJECT", "SPLIT"):
                final = f"CONTESTED(B1=KEEP,B3={b3_cons})"
            elif b1_simple == "REJECT" and b3_cons == "KEEP":
                final = "CONTESTED(B1=REJECT,B3=KEEP)"
            elif b1_simple in ("SPLIT", "MERGE"):
                # structural action from B1; B3 KEEP/REJECT becomes annotation
                final = f"{b1_verdict}+B3={b3_cons}"
            elif b3_cons == "UNCLEAR":
                final = f"NEEDS_MORE_DATA(B1={b1_simple},B3=UNCLEAR)"
            else:
                final = f"MIXED(B1={b1_simple},B3={b3_cons})"

            record = {
                "class_id": cid,
                "b1_verdict": b1_verdict,
                "b1_confidence": b1_conf,
                "b3_verdicts": b3_verdicts,
                "b3_confidences": [round(x, 2) for x in b3_confs],
                "b3_consensus": b3_cons,
                "b3_avg_confidence": round(b3_avg_conf, 2),
                "final_verdict": final,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    sys.exit(main())
