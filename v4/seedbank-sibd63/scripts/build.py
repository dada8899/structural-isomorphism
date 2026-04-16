#!/usr/bin/env python3
"""
Build SIBD-63: consolidate 63 A-level cross-domain structural isomorphism
discoveries from V1 / V2 / V3 pipelines into a single unified dataset.

Inputs:
  - v3/results/v1v2v3-transformation-labeled.jsonl  (canonical 63 set, V1 tier-1 + V2 A + V3 A, zero overlap)
  - results/v2m-a-rated.jsonl   (V2 source with a_domain, b_domain)
  - v3/results/v3-a-rated.jsonl (V3 source with shared_equation, variable_mapping)

Output:
  - SIBD-63.jsonl      (unified schema, 63 lines)
  - SIBD-63-schema.json (JSON schema definition)

Each unified record includes:
  seed_id, pipeline, rank_in_pipeline,
  a_name, a_domain, b_name, b_domain,
  shared_equation, variable_mapping, equations (list),
  isomorphism_depth, isomorphism_confidence,
  literature_status, paper_title, target_venue,
  practical_value, risk, blocking_mechanisms, execution_plan,
  time_estimate, solo_feasible, impact_scope,
  final_score, one_line_verdict,
  transformation_primitives, is_deep
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = Path(__file__).resolve().parents[1]

MERGED = ROOT / "v3" / "results" / "v1v2v3-transformation-labeled.jsonl"
V2_FILE = ROOT / "results" / "v2m-a-rated.jsonl"
V3_FILE = ROOT / "v3" / "results" / "v3-a-rated.jsonl"


def _norm_name(s: str) -> str:
    """Loose match key for joining across files."""
    if not s:
        return ""
    return re.sub(r"\s+", "", s).lower()


def load_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    return rows


def main():
    merged = load_jsonl(MERGED)
    v2_rows = load_jsonl(V2_FILE)
    v3_rows = load_jsonl(V3_FILE)

    v2_by_pair = {(_norm_name(r.get("a_name")), _norm_name(r.get("b_name"))): r for r in v2_rows}
    v3_by_pair = {(_norm_name(r.get("a_name")), _norm_name(r.get("b_name"))): r for r in v3_rows}

    print(f"Loaded {len(merged)} merged rows ({sum(1 for r in merged if r.get('_source')=='v1')} v1, "
          f"{sum(1 for r in merged if r.get('_source')=='v2')} v2, "
          f"{sum(1 for r in merged if r.get('_source')=='v3')} v3)")

    unified = []
    seen_pairs = set()
    for i, rec in enumerate(merged, start=1):
        pipeline = rec.get("_source", "?")
        a_raw = rec.get("a_name", "")
        b_raw = rec.get("b_name", "")
        key = (_norm_name(a_raw), _norm_name(b_raw))
        if key in seen_pairs:
            print(f"  skip duplicate pair: {a_raw} ↔ {b_raw}")
            continue
        seen_pairs.add(key)

        # Pull richer fields from V2 / V3 where available
        extra = {}
        if pipeline == "v2":
            extra = v2_by_pair.get(key, {})
        elif pipeline == "v3":
            extra = v3_by_pair.get(key, {})

        # Some V3 equations come as single field 'shared_equation';
        # V2 has a list 'equations'; V1 has text 'equations'. Normalize.
        equations_list = []
        if "shared_equation" in rec or "shared_equation" in extra:
            eq = rec.get("shared_equation") or extra.get("shared_equation")
            if eq:
                equations_list.append(str(eq))
        v1v2_eqs = rec.get("equations") or extra.get("equations")
        if isinstance(v1v2_eqs, list):
            for eq in v1v2_eqs:
                if eq and str(eq) not in equations_list:
                    equations_list.append(str(eq))
        elif isinstance(v1v2_eqs, str) and v1v2_eqs:
            if v1v2_eqs not in equations_list:
                equations_list.append(v1v2_eqs)

        row = {
            # Identity / provenance
            "seed_id": f"SIBD-{pipeline}-{i:03d}",
            "pipeline": pipeline,
            "rank_in_pipeline": rec.get("rank"),
            # Pair
            "a_name": a_raw,
            "a_domain": rec.get("a_domain") or extra.get("a_domain") or "",
            "b_name": b_raw,
            "b_domain": rec.get("b_domain") or extra.get("b_domain") or "",
            # Structure
            "shared_equation": rec.get("shared_equation") or extra.get("shared_equation") or "",
            "variable_mapping": rec.get("variable_mapping") or extra.get("variable_mapping") or "",
            "equations": equations_list,
            "isomorphism_depth": rec.get("isomorphism_depth") or extra.get("isomorphism_depth"),
            "isomorphism_confidence": rec.get("isomorphism_confidence") or extra.get("isomorphism_confidence"),
            # Publishability
            "paper_title": rec.get("paper_title") or extra.get("paper_title") or "",
            "target_venue": rec.get("target_venue") or extra.get("target_venue") or "",
            "literature_status": rec.get("literature_status") or extra.get("literature_status") or "",
            "literature_detail": rec.get("literature_detail") or extra.get("literature_detail") or "",
            "practical_value": rec.get("practical_value") or extra.get("practical_value") or "",
            "risk": rec.get("risk") or extra.get("risk") or "",
            "blocking_mechanisms": rec.get("blocking_mechanisms") or extra.get("blocking_mechanisms") or [],
            "execution_plan": rec.get("execution_plan") or extra.get("execution_plan") or [],
            "time_estimate": rec.get("time_estimate") or extra.get("time_estimate") or "",
            "solo_feasible": rec.get("solo_feasible") if rec.get("solo_feasible") is not None else extra.get("solo_feasible"),
            "impact_scope": rec.get("impact_scope") or extra.get("impact_scope") or "",
            "impact_detail": rec.get("impact_detail") or extra.get("impact_detail") or "",
            # Scoring
            "final_score": rec.get("final_score") or extra.get("final_score"),
            "one_line_verdict": rec.get("one_line_verdict") or "",
            "rating": rec.get("rating") or extra.get("rating") or "A",
            # Transformation analysis (from V4 transformation labeling)
            "transformation_primitives": rec.get("primitives") or [],
            "transformation_depth": rec.get("transformation_depth"),
            "is_deep": rec.get("is_deep"),
            # Full text analysis (for attribution / context)
            "full_analysis": rec.get("full_analysis") or extra.get("full_analysis") or "",
        }
        unified.append(row)

    out_path = OUT_DIR / "SIBD-63.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in unified:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"Wrote {len(unified)} unified records to {out_path}")

    # Schema
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://doi.org/10.5281/zenodo.PLACEHOLDER/SIBD-63-schema.json",
        "title": "SIBD-63 Seed Record Schema",
        "description": "Each line in SIBD-63.jsonl encodes a single A-level cross-domain structural isomorphism discovery.",
        "type": "object",
        "required": ["seed_id", "pipeline", "a_name", "b_name", "final_score"],
        "properties": {
            "seed_id": {"type": "string", "description": "Stable identifier, format SIBD-{pipeline}-{NNN}."},
            "pipeline": {"type": "string", "enum": ["v1", "v2", "v3"], "description": "Which of the three independent pipelines surfaced this isomorphism."},
            "rank_in_pipeline": {"type": ["integer", "null"], "description": "Rank assigned by the pipeline's own scoring (lower = higher rank)."},
            "a_name": {"type": "string", "description": "Natural-language name of the first phenomenon."},
            "a_domain": {"type": "string", "description": "Domain label of phenomenon A (may be empty for v1 records)."},
            "b_name": {"type": "string", "description": "Natural-language name of the second phenomenon."},
            "b_domain": {"type": "string", "description": "Domain label of phenomenon B (may be empty for v1 records)."},
            "shared_equation": {"type": "string", "description": "Compact statement of the shared mathematical structure (v3 only)."},
            "variable_mapping": {"type": ["string", "object"], "description": "Mapping of variables between A and B (v3 only; may be stringified JSON)."},
            "equations": {"type": "array", "items": {"type": "string"}, "description": "All equations associated with the pair from any pipeline."},
            "isomorphism_depth": {"type": ["integer", "null"], "description": "Depth score 1-5, 5 = structure matches at multiple independent layers."},
            "isomorphism_confidence": {"type": ["number", "null"], "description": "Calibrated confidence in [0,1] that the isomorphism is real-not-coincidental."},
            "paper_title": {"type": "string", "description": "Suggested publication title."},
            "target_venue": {"type": "string", "description": "Suggested target journal / conference."},
            "literature_status": {"type": "string", "enum": ["", "unexplored", "partial", "established", "未有先例", "未发表", "未探索", "部分探索", "已有文献"], "description": "Prior-art status."},
            "literature_detail": {"type": "string", "description": "Free-text discussion of prior art."},
            "practical_value": {"type": "string", "description": "Why the finding matters beyond academic novelty."},
            "risk": {"type": "string", "description": "Why the isomorphism might not survive empirical test."},
            "blocking_mechanisms": {"type": "array", "items": {"type": "string"}, "description": "Specific obstacles the user should plan for."},
            "execution_plan": {"type": ["array", "string"], "description": "Step-by-step plan for the seeded empirical paper."},
            "time_estimate": {"type": "string", "description": "Expected person-effort (e.g. '3-4 months')."},
            "solo_feasible": {"type": ["boolean", "null"], "description": "Whether a single researcher can realistically complete the paper."},
            "impact_scope": {"type": "string", "description": "Expected scope of impact."},
            "impact_detail": {"type": "string", "description": "Free-text impact discussion."},
            "final_score": {"type": "number", "description": "Aggregated 5-dimensional score."},
            "one_line_verdict": {"type": "string", "description": "One-line characterization, written by the deep-analysis LLM."},
            "rating": {"type": "string", "enum": ["A", "A+", "B+"], "description": "All records in SIBD-63 are A-grade by construction."},
            "transformation_primitives": {"type": "array", "items": {"type": "string"}, "description": "V4 cross-domain transformation primitives used (if labeled)."},
            "transformation_depth": {"type": ["integer", "null"], "description": "How deep a structural transformation is required to map A to B."},
            "is_deep": {"type": ["boolean", "null"], "description": "True if more than surface-level isomorphism."},
            "full_analysis": {"type": "string", "description": "Full LLM deep-analysis text."}
        }
    }
    (OUT_DIR / "SIBD-63-schema.json").write_text(json.dumps(schema, indent=2, ensure_ascii=False))
    print(f"Wrote schema to {OUT_DIR / 'SIBD-63-schema.json'}")

    # Summary stats
    print("\n=== Dataset summary ===")
    from collections import Counter
    pl = Counter(r["pipeline"] for r in unified)
    print(f"  pipelines: {dict(pl)}")
    doms_a = Counter(r["a_domain"] for r in unified if r["a_domain"])
    doms_b = Counter(r["b_domain"] for r in unified if r["b_domain"])
    all_doms = sum((doms_a, doms_b), Counter())
    print(f"  unique domains (a + b): {len(all_doms)}")
    print(f"  top 8 domains: {dict(all_doms.most_common(8))}")
    scores = [r["final_score"] for r in unified if r.get("final_score") is not None]
    if scores:
        print(f"  score range: [{min(scores)}, {max(scores)}], mean {sum(scores)/len(scores):.2f}")
    with_eq = sum(1 for r in unified if r["shared_equation"])
    print(f"  records with explicit shared_equation: {with_eq}/{len(unified)}")


if __name__ == "__main__":
    main()
