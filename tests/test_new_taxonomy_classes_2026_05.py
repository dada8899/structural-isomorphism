"""Sanity-check the 3 new universality-class YAMLs added in Wave 11-E.

Newly added (session #10):
    - fractional_brownian_crossings
    - anderson_localization
    - preisach_hysteresis_cascade

The test exercises:
1. YAML parses cleanly
2. Required fields exist (class_id, status, display_name, hub_phenomenon,
   shared_equation, key_invariants, positive_examples, negative_examples)
3. At least 3 positive + 2 negative examples
4. class_id matches the filename stem
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CLASSES_DIR = REPO_ROOT / "v4" / "taxonomy" / "classes"

NEW_CLASSES = [
    "fractional_brownian_crossings",
    "anderson_localization",
    "preisach_hysteresis_cascade",
]

REQUIRED_FIELDS = (
    "class_id",
    "status",
    "display_name",
    "hub_phenomenon",
    "shared_equation",
    "key_invariants",
    "positive_examples",
    "negative_examples",
)


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_yaml_file_exists(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    assert path.is_file(), f"missing YAML file: {path}"


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_yaml_parses(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    with path.open() as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), f"top-level YAML must be a dict, got {type(data)}"


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_required_fields_present(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    with path.open() as fh:
        data = yaml.safe_load(fh)
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    assert not missing, f"{class_id}.yaml missing required fields: {missing}"


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_class_id_matches_filename(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    with path.open() as fh:
        data = yaml.safe_load(fh)
    assert data["class_id"] == class_id, (
        f"class_id field '{data['class_id']}' does not match filename stem '{class_id}'"
    )


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_minimum_examples(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    with path.open() as fh:
        data = yaml.safe_load(fh)
    pos = data.get("positive_examples") or []
    neg = data.get("negative_examples") or []
    assert len(pos) >= 3, f"{class_id}: need >= 3 positive examples, got {len(pos)}"
    assert len(neg) >= 2, f"{class_id}: need >= 2 negative examples, got {len(neg)}"


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_status_is_valid(class_id: str) -> None:
    path = CLASSES_DIR / f"{class_id}.yaml"
    with path.open() as fh:
        data = yaml.safe_load(fh)
    valid = {"speculative", "emerging", "well-established"}
    assert data["status"] in valid, (
        f"{class_id}: status '{data['status']}' not in {valid}"
    )


@pytest.mark.parametrize("class_id", NEW_CLASSES)
def test_new_class_present_in_universality_classes_json(class_id: str) -> None:
    """The new YAML must also have an entry in universality-classes.json."""
    import json

    json_path = (
        REPO_ROOT / "web" / "frontend" / "assets" / "data" / "universality-classes.json"
    )
    with json_path.open() as fh:
        data = json.load(fh)
    ids = {c["class_id"] for c in data["classes"]}
    assert class_id in ids, (
        f"{class_id} present as YAML but missing from universality-classes.json"
    )
