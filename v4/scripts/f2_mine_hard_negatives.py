#!/usr/bin/env python3
"""F2 active-learning: mine hard negatives + positives from B3 critic verdicts.

Reads:
    v4/results/B3_ensemble_review.jsonl   (per-model verdicts, used to fetch rationale)
    v4/results/B3_taxonomy_v2.jsonl       (per-class final verdict + b3 consensus)
    v4/taxonomy/classes/*.yaml             (positive_examples per class)

Writes:
    v4/results/active_learning/hard_negatives_v1.jsonl
    v4/results/active_learning/positives_v1.jsonl
    v4/results/active_learning/miner_summary.md

Semantics (see v4/lib/active_learning_design.md §4):
    - REJECT consensus class -> every unordered pair from its positive_examples
      becomes a hard negative (label=0). These pairs were proposed as
      same-class by Layer 3 but the ensemble critic rejected them.
    - KEEP consensus class -> every unordered pair from its positive_examples
      becomes a positive (label=1).
    - SPLIT / MERGE / CONTESTED / MIXED -> dropped from training (ambiguous).

Confidence weighting (see design §5):
    weight = 1.0       if b3_avg_confidence >= 0.9
    weight = 0.7       if 0.75 <= conf < 0.9
    weight = 0.4       if 0.6  <= conf < 0.75
    pair dropped       if conf < 0.6
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("f2_mine")

# ---------------------------------------------------------------------------
# resolve repo root (works whether script is in v4/scripts or symlinked)
# ---------------------------------------------------------------------------
THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
B3_REVIEW = REPO / "v4" / "results" / "B3_ensemble_review.jsonl"
B3_TAXONOMY = REPO / "v4" / "results" / "B3_taxonomy_v2.jsonl"
CLASSES_DIR = REPO / "v4" / "taxonomy" / "classes"
OUT_DIR = REPO / "v4" / "results" / "active_learning"


@dataclass
class TrainingPair:
    """One mined training pair for contrastive fine-tune."""

    text_a: str
    text_b: str
    label: int          # 1 = positive (same class), 0 = hard negative (rejected pair)
    source_class: str
    source_verdict: str  # "KEEP" or "REJECT"
    confidence: float
    weight: float
    rejection_reason: str = ""  # populated for hard negatives only

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def conf_to_weight(conf: float) -> float:
    """Map B3 average confidence to per-pair training weight.

    Returns 0.0 if confidence is too low (caller should drop).
    """
    if conf >= 0.9:
        return 1.0
    if conf >= 0.75:
        return 0.7
    if conf >= 0.6:
        return 0.4
    return 0.0


def load_taxonomy(path: Path) -> list[dict[str, Any]]:
    """Load B3_taxonomy_v2.jsonl (one row per class).

    Each row has class_id, b3_consensus, b3_avg_confidence, final_verdict.
    """
    if not path.exists():
        raise FileNotFoundError(f"B3 taxonomy not found at {path}")
    rows: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_review(path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load B3_ensemble_review.jsonl indexed by class_id (list of per-model rows)."""
    if not path.exists():
        logger.warning("B3 review not found at %s; rejection rationale unavailable", path)
        return {}
    by_class: dict[str, list[dict[str, Any]]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            cid = row.get("class_id")
            if cid:
                by_class.setdefault(cid, []).append(row)
    return by_class


def load_class_yaml(class_id: str, classes_dir: Path) -> dict[str, Any] | None:
    """Load v4/taxonomy/classes/<class_id>.yaml, return None if missing."""
    p = classes_dir / f"{class_id}.yaml"
    if not p.exists():
        logger.warning("YAML missing for class_id=%s at %s", class_id, p)
        return None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def extract_phenomenon_text(example: Any) -> str:
    """Pull a text string from a positive_examples entry.

    Schema varies a bit across classes: usually a dict with `phenomenon` key,
    sometimes `name` / `description`. Falls back to repr to avoid crashes.
    """
    if isinstance(example, dict):
        for key in ("phenomenon", "name", "description"):
            v = example.get(key)
            if v and isinstance(v, str):
                return v.strip()
        return ""
    if isinstance(example, str):
        return example.strip()
    return ""


def consensus_rejection_rationale(review_rows: list[dict[str, Any]]) -> str:
    """Pick the highest-confidence REJECT rationale for a class.

    Returns empty string if no REJECT rows present.
    """
    rejects = [r for r in review_rows if r.get("verdict") == "REJECT"]
    if not rejects:
        return ""
    rejects.sort(key=lambda r: r.get("confidence", 0.0), reverse=True)
    return (rejects[0].get("rationale") or "")[:500]


def mine_pairs(
    taxonomy_rows: list[dict[str, Any]],
    review_by_class: dict[str, list[dict[str, Any]]],
    classes_dir: Path,
) -> tuple[list[TrainingPair], list[TrainingPair], dict[str, int]]:
    """Walk each class; emit positives / hard_negatives + per-bucket counts."""
    positives: list[TrainingPair] = []
    negatives: list[TrainingPair] = []
    stats: Counter[str] = Counter()

    for row in taxonomy_rows:
        cid = row["class_id"]
        consensus = row.get("b3_consensus", "")
        conf = float(row.get("b3_avg_confidence") or 0.0)
        weight = conf_to_weight(conf)

        if consensus not in ("KEEP", "REJECT"):
            stats[f"skip_consensus={consensus}"] += 1
            continue
        if weight == 0.0:
            stats["skip_low_confidence"] += 1
            continue

        yaml_row = load_class_yaml(cid, classes_dir)
        if not yaml_row:
            stats["skip_no_yaml"] += 1
            continue

        positives_list = yaml_row.get("positive_examples") or []
        # Map each positive_example to a clean phenomenon string
        texts: list[str] = []
        for ex in positives_list:
            t = extract_phenomenon_text(ex)
            if t:
                texts.append(t)
        # de-dup while preserving order
        seen: set[str] = set()
        uniq_texts: list[str] = []
        for t in texts:
            if t not in seen:
                seen.add(t)
                uniq_texts.append(t)

        if len(uniq_texts) < 2:
            stats["skip_lt2_positives"] += 1
            continue

        rationale = consensus_rejection_rationale(review_by_class.get(cid, []))
        if consensus == "REJECT":
            for a, b in combinations(uniq_texts, 2):
                negatives.append(
                    TrainingPair(
                        text_a=a,
                        text_b=b,
                        label=0,
                        source_class=cid,
                        source_verdict="REJECT",
                        confidence=conf,
                        weight=weight,
                        rejection_reason=rationale,
                    )
                )
            stats[f"reject_classes"] += 1
            stats["hard_negative_pairs"] += len(list(combinations(uniq_texts, 2)))
        else:  # KEEP
            for a, b in combinations(uniq_texts, 2):
                positives.append(
                    TrainingPair(
                        text_a=a,
                        text_b=b,
                        label=1,
                        source_class=cid,
                        source_verdict="KEEP",
                        confidence=conf,
                        weight=weight,
                    )
                )
            stats["keep_classes"] += 1
            stats["positive_pairs"] += len(list(combinations(uniq_texts, 2)))

    return positives, negatives, dict(stats)


def write_jsonl(path: Path, items: list[TrainingPair]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(item.to_jsonl() + "\n")


def write_summary(
    out_md: Path,
    positives: list[TrainingPair],
    negatives: list[TrainingPair],
    stats: dict[str, int],
) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# F2 Active Learning — Miner Summary")
    lines.append("")
    lines.append(f"- Positives mined: **{len(positives)}**")
    lines.append(f"- Hard negatives mined: **{len(negatives)}**")
    lines.append(f"- Source: `v4/results/B3_taxonomy_v2.jsonl`")
    lines.append("")
    lines.append("## Per-bucket stats")
    lines.append("")
    for k in sorted(stats):
        lines.append(f"- `{k}`: {stats[k]}")
    lines.append("")
    lines.append("## Classes contributing positives (KEEP consensus)")
    lines.append("")
    keep_classes = sorted({p.source_class for p in positives})
    for c in keep_classes:
        n = sum(1 for p in positives if p.source_class == c)
        lines.append(f"- `{c}`: {n} pairs")
    lines.append("")
    lines.append("## Classes contributing hard negatives (REJECT consensus)")
    lines.append("")
    rej_classes = sorted({p.source_class for p in negatives})
    for c in rej_classes:
        n = sum(1 for p in negatives if p.source_class == c)
        lines.append(f"- `{c}`: {n} pairs")
    lines.append("")
    out_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="F2 hard-negative + positive miner")
    parser.add_argument("--review", type=Path, default=B3_REVIEW)
    parser.add_argument("--taxonomy", type=Path, default=B3_TAXONOMY)
    parser.add_argument("--classes-dir", type=Path, default=CLASSES_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--version", type=str, default="v1", help="suffix for output filenames")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    taxonomy_rows = load_taxonomy(args.taxonomy)
    review_by_class = load_review(args.review)

    positives, negatives, stats = mine_pairs(taxonomy_rows, review_by_class, args.classes_dir)

    pos_path = args.out_dir / f"positives_{args.version}.jsonl"
    neg_path = args.out_dir / f"hard_negatives_{args.version}.jsonl"
    summary_path = args.out_dir / "miner_summary.md"

    write_jsonl(pos_path, positives)
    write_jsonl(neg_path, negatives)
    write_summary(summary_path, positives, negatives, stats)

    logger.info("Wrote %d positives -> %s", len(positives), pos_path)
    logger.info("Wrote %d hard negatives -> %s", len(negatives), neg_path)
    logger.info("Wrote summary -> %s", summary_path)
    print(
        json.dumps(
            {
                "positives": len(positives),
                "hard_negatives": len(negatives),
                "stats": stats,
                "out": {
                    "positives": str(pos_path),
                    "hard_negatives": str(neg_path),
                    "summary": str(summary_path),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
