"""Regression test: every entry in universality-classes.json has a unique class_id.

Background
----------
Session #9 commit bfdf2b0 ("F1: P1 bugs") resolved a duplicate-class_id
defect: the Louvain community-detection step on the B3 consensus graph
produced two Motter-Lai sub-communities and two Gardner-Collins
sub-communities that legitimately differed (distinct domains, members,
ranks, summaries) but collided on `class_id`. The fix suffixed the
lower-rank entries with `_v2`. See
`docs/data/universality-classes-dedupe-2026-05-15.md` for the full
decision record.

This test guards against the regression. The taxonomy file is consumed
by the public Structural Search engine (beta.structural.bytedance.city)
and the Phase Detector universality-class linking widget, both of which
key off `class_id`. A future re-clustering run that re-introduces a
collision must be detected at CI time, not in production.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = (
    REPO_ROOT / "web" / "frontend" / "assets" / "data" / "universality-classes.json"
)


pytestmark = pytest.mark.sanity


def _load_classes() -> list[dict]:
    with TAXONOMY_PATH.open() as fh:
        data = json.load(fh)
    assert isinstance(data, dict), (
        f"expected top-level object in {TAXONOMY_PATH}, got {type(data).__name__}"
    )
    classes = data.get("classes")
    assert isinstance(classes, list), (
        f"expected key 'classes' to be a list in {TAXONOMY_PATH}"
    )
    return classes


def test_taxonomy_file_exists():
    assert TAXONOMY_PATH.is_file(), f"missing taxonomy file: {TAXONOMY_PATH}"


def test_every_class_has_class_id():
    classes = _load_classes()
    missing = [i for i, c in enumerate(classes) if not c.get("class_id")]
    assert not missing, f"classes missing 'class_id' at indices: {missing}"


def test_class_ids_are_unique():
    classes = _load_classes()
    ids = [c["class_id"] for c in classes]
    counts = Counter(ids)
    duplicates = {cid: n for cid, n in counts.items() if n > 1}
    assert not duplicates, (
        f"duplicate class_id values in universality-classes.json: {duplicates}. "
        f"See docs/data/universality-classes-dedupe-2026-05-15.md for resolution policy."
    )


def test_class_ids_are_lowercase_snake_case():
    """Sanity guard: class_id should follow lowercase_snake_case convention."""
    classes = _load_classes()
    bad = [
        c["class_id"]
        for c in classes
        if c["class_id"] != c["class_id"].lower()
        or " " in c["class_id"]
        or "-" in c["class_id"]
    ]
    assert not bad, f"class_id values violating lowercase_snake_case: {bad}"


def test_v2_suffix_classes_have_distinct_content():
    """Any `*_v2` entry must differ from its base in domains or rank.

    This enforces the dedupe policy: we only allow `_v2` suffixes when the
    underlying clusters are genuinely distinct (different Louvain
    sub-communities). A `_v2` that simply duplicates its base entry would
    be a regression.
    """
    classes = _load_classes()
    by_id = {c["class_id"]: c for c in classes}
    for cid, c in by_id.items():
        if not cid.endswith("_v2"):
            continue
        base_id = cid[: -len("_v2")]
        base = by_id.get(base_id)
        if base is None:
            # _v2 without a base entry is allowed (e.g. only the _v2 survived).
            continue
        # Must differ in at least one of: domains, rank, name_en, hub_name.
        diff_fields = [
            f for f in ("domains", "rank", "name_en", "hub_name")
            if c.get(f) != base.get(f)
        ]
        assert diff_fields, (
            f"{cid} is identical to {base_id} on domains/rank/name_en/hub_name "
            f"— if they are truly the same class, merge them instead of suffixing _v2."
        )
