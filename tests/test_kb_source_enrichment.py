from __future__ import annotations

import json
from datetime import date

import pytest

from scripts.kb_source_enrichment import (
    REVIEW_SCHEMA,
    atomic_json,
    build_bundle,
    merge_reviews,
    read_jsonl,
    validate_bundle,
    validate_reviews,
)


def write_kb(path):
    rows = [
        {"id": "a", "name": "A", "domain": "金融", "type_id": "01", "description": "该机制通常导致风险增加约20%。"},
        {"id": "b", "name": "B", "domain": "物理", "type_id": "02", "description": "简单候选描述。"},
    ]
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def review(task, bundle, reviewer="r1", **changes):
    row = {
        "schema_version": REVIEW_SCHEMA, "task_id": task["task_id"], "kb_id": task["kb_id"],
        "description_sha256": task["description_sha256"],
        "bundle_fingerprint": bundle["metadata"]["review_fingerprint"], "reviewer_id": reviewer,
        "reviewed_at": date.today().isoformat(), "source_review": "accepted",
        "source_url": "https://example.org/source", "citation": "Author. Complete source title. 2020.",
        "license": "source-specific", "provenance_class": "literature-derived", "note": "checked",
    }
    row.update(changes); return row


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_bundle_is_stable_prioritized_and_content_bound(tmp_path):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    first = build_bundle(kb, batch_size=2)
    assert first == build_bundle(kb, batch_size=2)
    assert first["tasks"][0]["kb_id"] == "a"
    assert validate_bundle(first, kb)
    kb.write_text(kb.read_text().replace("20%", "21%"))
    with pytest.raises(ValueError, match="drift or fingerprint"):
        validate_bundle(first, kb)


def test_accepted_review_requires_source_fields_and_hash(tmp_path):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    bundle = build_bundle(kb, batch_size=2); task = bundle["tasks"][0]
    assert len(validate_reviews([review(task, bundle)], bundle)) == 1
    with pytest.raises(ValueError, match="content hash"):
        validate_reviews([review(task, bundle, description_sha256="0" * 64)], bundle)
    with pytest.raises(ValueError, match="HTTPS"):
        validate_reviews([review(task, bundle, source_url="http://example.org")], bundle)
    with pytest.raises(ValueError, match="complete citation"):
        validate_reviews([review(task, bundle, citation="short")], bundle)


def test_insufficient_is_honest_and_cannot_retain_source_claims(tmp_path):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    bundle = build_bundle(kb, batch_size=1); task = bundle["tasks"][0]
    row = review(task, bundle, source_review="insufficient", source_url=None, citation=None,
                 license=None, provenance_class=None, note="No defensible source found.")
    assert validate_reviews([row], bundle)
    with pytest.raises(ValueError, match="must not retain source claims"):
        validate_reviews([{**row, "source_url": "https://example.org"}], bundle)


def test_two_matching_reviewers_promote_and_conflicts_stay_candidate(tmp_path):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    bundle = build_bundle(kb, batch_size=2); task = bundle["tasks"][0]
    one, two = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    write_jsonl(one, [review(task, bundle, "r1")]); write_jsonl(two, [review(task, bundle, "r2")])
    merged, conflicts, report = merge_reviews([one, two], bundle)
    assert merged[0]["evidence_level"] == "source_backed"
    assert merged[0]["reviewers"] == ["r1", "r2"]
    assert conflicts == [] and report["source_backed_count"] == 1
    write_jsonl(two, [review(task, bundle, "r2", source_url="https://example.org/other")])
    merged, conflicts, report = merge_reviews([one, two], bundle)
    assert merged[0]["evidence_level"] == "candidate"
    assert len(conflicts) == 1 and report["conflict_queue_count"] == 1

    three = tmp_path / "three.jsonl"
    write_jsonl(two, [review(task, bundle, "r2")])
    write_jsonl(three, [review(
        task, bundle, "r3", source_review="insufficient", source_url=None,
        citation=None, license=None, provenance_class=None,
        note="The description overstates the source.",
    )])
    merged, conflicts, report = merge_reviews([one, two, three], bundle)
    assert merged[0]["evidence_level"] == "candidate"
    assert len(conflicts) == 1 and report["source_backed_count"] == 0


def test_duplicate_keys_nan_symlinks_and_overwrite_fail_closed(tmp_path):
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text('{"task_id":"a","task_id":"b"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        read_jsonl(duplicate)
    duplicate.write_text('{"score":NaN}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="non-finite"):
        read_jsonl(duplicate)

    link = tmp_path / "reviews-link.jsonl"
    link.symlink_to(duplicate)
    with pytest.raises(ValueError, match="non-symlink"):
        read_jsonl(link)
    linked_dir = tmp_path / "linked-dir"
    real_dir = tmp_path / "real-dir"; real_dir.mkdir()
    linked_dir.symlink_to(real_dir, target_is_directory=True)
    nested = linked_dir / "nested.jsonl"
    duplicate.replace(real_dir / "nested.jsonl")
    with pytest.raises(ValueError, match="non-symlink"):
        read_jsonl(nested)

    output = tmp_path / "output.json"
    atomic_json(output, {"first": True})
    with pytest.raises(FileExistsError, match="--overwrite"):
        atomic_json(output, {"second": True})
    assert json.loads(output.read_text()) == {"first": True}
    atomic_json(output, {"second": True}, overwrite=True)
    assert json.loads(output.read_text()) == {"second": True}


def test_reviewer_identity_and_scope_note_are_consensus_bound(tmp_path):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    bundle = build_bundle(kb, batch_size=1); task = bundle["tasks"][0]
    with pytest.raises(ValueError, match="reviewer_id"):
        validate_reviews([review(task, bundle, " r1")], bundle)
    with pytest.raises(ValueError, match="review note"):
        validate_reviews([review(task, bundle, note="  ")], bundle)

    one, two = tmp_path / "one.jsonl", tmp_path / "two.jsonl"
    write_jsonl(one, [review(task, bundle, "r1", note="supports only the acute case")])
    write_jsonl(two, [review(task, bundle, "r2", note="supports chronic and acute cases")])
    merged, conflicts, _ = merge_reviews([one, two], bundle)
    assert merged[0]["evidence_level"] == "candidate"
    assert len(conflicts) == 1


@pytest.mark.parametrize("url", [
    "https://user:pass@example.org/source",
    "https://example.org/source#unchecked-fragment",
    "https:///missing-host",
])
def test_accepted_url_rejects_ambiguous_or_credentialed_forms(tmp_path, url):
    kb = tmp_path / "kb.jsonl"; write_kb(kb)
    bundle = build_bundle(kb, batch_size=1); task = bundle["tasks"][0]
    with pytest.raises(ValueError, match="HTTPS"):
        validate_reviews([review(task, bundle, source_url=url)], bundle)
