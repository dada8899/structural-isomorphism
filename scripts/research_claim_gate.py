#!/usr/bin/env python3
"""Fail-closed consistency gate for research headline claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "evaluation/research/claim-evidence-ledger-v1.json"
REQUIRED_CLAIM_FIELDS = {
    "claim_id", "headline", "exact_wording", "scope", "status", "evidence",
    "command", "environment", "seed", "result_figure_table", "provenance",
    "independence", "caveats",
}
ALLOWED_STATUSES = {
    "reviewer-readable-do-not-submit", "internal-draft", "withdrawn", "submitted"
}
PLACEHOLDER_ID = re.compile(
    r"(?:doi(?:\s+id)?\s*[:=]?\s*(?:tbd|todo|placeholder|xx+)|"
    r"arxiv(?:\s+id)?\s*[:=]?\s*(?:tbd|todo|placeholder|xx+)|"
    r"10\.\d{4,9}/(?:tbd|todo|placeholder|xx+))",
    re.IGNORECASE,
)
ABSOLUTE_UNIVERSALITY = re.compile(
    r"\b(?:universal(?:ity)?\s+(?:over|across)\s+all|universally\s+valid|"
    r"universal[-\s]+across[-\s]+matter|proves?\s+(?:a\s+)?universal(?:ity)?|"
    r"universal\s+law\s+of\s+all)\b",
    re.IGNORECASE,
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(ledger_path: Path, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read ledger: {exc}"]

    if ledger.get("manuscript_status") != "reviewer-readable-do-not-submit":
        errors.append("manuscript_status must remain reviewer-readable-do-not-submit")
    if ledger.get("external_review_completed") is not False:
        errors.append("external_review_completed must be false without auditable external review")
    if ledger.get("review_status") != "internal-review-only":
        errors.append("review_status must be internal-review-only")

    claims = ledger.get("claims")
    if not isinstance(claims, list) or not claims:
        return errors + ["claims must be a non-empty list"]
    seen: set[str] = set()
    for index, claim in enumerate(claims):
        label = claim.get("claim_id", f"claim[{index}]") if isinstance(claim, dict) else f"claim[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{label}: must be an object")
            continue
        missing = REQUIRED_CLAIM_FIELDS - claim.keys()
        if missing:
            errors.append(f"{label}: missing fields {sorted(missing)}")
            continue
        claim_id = claim["claim_id"]
        if not _nonempty(claim_id) or claim_id in seen:
            errors.append(f"{label}: claim_id must be non-empty and unique")
        seen.add(claim_id)
        if claim["status"] not in ALLOWED_STATUSES:
            errors.append(f"{label}: invalid status {claim['status']!r}")
        for field in ("exact_wording", "scope", "command", "environment",
                      "result_figure_table", "provenance", "independence"):
            if not _nonempty(claim[field]):
                errors.append(f"{label}: {field} must be non-empty")
        if claim["headline"] is not True:
            errors.append(f"{label}: ledger v1 contains headline claims only")
        if not isinstance(claim["caveats"], list) or not claim["caveats"] or not all(_nonempty(x) for x in claim["caveats"]):
            errors.append(f"{label}: caveats must be a non-empty string list")
        wording = f"{claim['exact_wording']} {claim['scope']}"
        if ABSOLUTE_UNIVERSALITY.search(wording):
            errors.append(f"{label}: prohibited absolute universality wording")
        evidence = claim["evidence"]
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label}: headline claim has no evidence")
            continue
        for item in evidence:
            if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
                errors.append(f"{label}: evidence must contain exactly path and sha256")
                continue
            if not _nonempty(item["path"]):
                errors.append(f"{label}: evidence path must be a non-empty string")
                continue
            path = Path(item["path"])
            if path.is_absolute() or ".." in path.parts:
                errors.append(f"{label}: evidence path must stay repository-relative")
                continue
            target = root / path
            if not target.is_file():
                errors.append(f"{label}: missing evidence {item['path']}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])):
                errors.append(f"{label}: invalid sha256 for {item['path']}")
            elif actual != item["sha256"]:
                errors.append(f"{label}: hash mismatch for {item['path']}")

    manuscript_value = ledger.get("manuscript")
    if not _nonempty(manuscript_value):
        errors.append("manuscript path must be a non-empty string")
        manuscript = None
    else:
        manuscript_path = Path(manuscript_value)
        if manuscript_path.is_absolute() or ".." in manuscript_path.parts:
            errors.append("manuscript path must stay repository-relative")
            manuscript = None
        else:
            manuscript = root / manuscript_path
    if manuscript is not None and not manuscript.is_file():
        errors.append("manuscript path is missing")
    elif manuscript is not None:
        text = manuscript.read_text(encoding="utf-8")
        if PLACEHOLDER_ID.search(text):
            errors.append("manuscript contains placeholder DOI/arXiv identifier")
    serialized = json.dumps(ledger, ensure_ascii=False)
    if PLACEHOLDER_ID.search(serialized):
        errors.append("ledger contains placeholder DOI/arXiv identifier")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    args = parser.parse_args()
    errors = validate(args.ledger.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("research claim gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
