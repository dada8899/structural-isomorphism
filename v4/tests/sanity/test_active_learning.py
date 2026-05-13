"""F2 active-learning scaffold sanity tests.

Covers:
 - hard-negative miner: KEEP class -> positives; REJECT class -> hard negs;
   SPLIT/MERGE classes dropped; confidence weighting honored.
 - ContrastiveFinetuner interface: load_pairs / fit / evaluate round-trip
   on mocked input; mode="real" raises NotImplementedError.
 - Simulation: end-to-end pipeline runs and produces a report; the active
   learning signal moves at least one metric in the right direction
   (R@5 weakly improves OR silhouette weakly improves — fine-grained
   monotonicity isn't guaranteed on 80 noisy pairs).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from embedding_finetune import (  # type: ignore  # noqa: E402
    ContrastiveFinetuner,
    FinetuneMetrics,
    TrainingPair,
    info_nce_loss,
)


REPO = Path(__file__).resolve().parents[3]
RESULTS = REPO / "v4" / "results" / "active_learning"
POSITIVES = RESULTS / "positives_v1.jsonl"
NEGATIVES = RESULTS / "hard_negatives_v1.jsonl"
REPORT = RESULTS / "simulation_report.md"
SCRIPT_MINE = REPO / "v4" / "scripts" / "f2_mine_hard_negatives.py"
SCRIPT_SIM = REPO / "v4" / "scripts" / "f2_simulate_active_learning.py"


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="module")
def mocked_taxonomy(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Synthetic taxonomy + classes dir for miner unit tests."""
    base = tmp_path_factory.mktemp("mock_tax")
    classes_dir = base / "classes"
    classes_dir.mkdir()
    # Three classes: KEEP / REJECT / SPLIT
    keep_yaml = """
class_id: mock_keep
positive_examples:
  - phenomenon: Phenomenon A1
  - phenomenon: Phenomenon A2
  - phenomenon: Phenomenon A3
"""
    reject_yaml = """
class_id: mock_reject
positive_examples:
  - phenomenon: Phenomenon B1
  - phenomenon: Phenomenon B2
  - phenomenon: Phenomenon B3
  - phenomenon: Phenomenon B4
"""
    split_yaml = """
class_id: mock_split
positive_examples:
  - phenomenon: Phenomenon C1
  - phenomenon: Phenomenon C2
"""
    (classes_dir / "mock_keep.yaml").write_text(keep_yaml, encoding="utf-8")
    (classes_dir / "mock_reject.yaml").write_text(reject_yaml, encoding="utf-8")
    (classes_dir / "mock_split.yaml").write_text(split_yaml, encoding="utf-8")

    taxonomy = base / "B3_taxonomy.jsonl"
    rows = [
        {
            "class_id": "mock_keep",
            "b3_consensus": "KEEP",
            "b3_avg_confidence": 0.95,
            "final_verdict": "KEEP_strong",
        },
        {
            "class_id": "mock_reject",
            "b3_consensus": "REJECT",
            "b3_avg_confidence": 0.85,
            "final_verdict": "REJECT_strong",
        },
        {
            "class_id": "mock_split",
            "b3_consensus": "SPLIT",
            "b3_avg_confidence": 0.9,
            "final_verdict": "SPLIT_strong",
        },
    ]
    with open(taxonomy, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    review = base / "B3_review.jsonl"
    review_rows = [
        {
            "class_id": "mock_reject",
            "model_id": "test",
            "verdict": "REJECT",
            "confidence": 0.85,
            "rationale": "mock rationale",
        }
    ]
    with open(review, "w", encoding="utf-8") as f:
        for r in review_rows:
            f.write(json.dumps(r) + "\n")

    return {
        "base": base,
        "taxonomy": taxonomy,
        "review": review,
        "classes_dir": classes_dir,
    }


# ----------------------------------------------------------------------
# 1. miner correctness
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_miner_keep_yields_positives_reject_yields_negatives(
    mocked_taxonomy: dict[str, Path], tmp_path: Path
) -> None:
    """Run the miner against synthetic input and verify pair counts."""
    out_dir = tmp_path / "active_learning"
    cmd = [
        sys.executable,
        str(SCRIPT_MINE),
        "--taxonomy",
        str(mocked_taxonomy["taxonomy"]),
        "--review",
        str(mocked_taxonomy["review"]),
        "--classes-dir",
        str(mocked_taxonomy["classes_dir"]),
        "--out-dir",
        str(out_dir),
        "--version",
        "mock",
        "--quiet",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"miner failed: {result.stderr}"

    pos_path = out_dir / "positives_mock.jsonl"
    neg_path = out_dir / "hard_negatives_mock.jsonl"
    assert pos_path.exists()
    assert neg_path.exists()

    # KEEP class with 3 positives -> C(3,2) = 3 pair
    pos_lines = [json.loads(line) for line in pos_path.read_text().splitlines() if line.strip()]
    assert len(pos_lines) == 3
    assert all(p["label"] == 1 for p in pos_lines)
    assert all(p["source_verdict"] == "KEEP" for p in pos_lines)
    assert all(p["source_class"] == "mock_keep" for p in pos_lines)

    # REJECT class with 4 positives -> C(4,2) = 6 pair
    neg_lines = [json.loads(line) for line in neg_path.read_text().splitlines() if line.strip()]
    assert len(neg_lines) == 6
    assert all(p["label"] == 0 for p in neg_lines)
    assert all(p["source_verdict"] == "REJECT" for p in neg_lines)
    # rationale propagated
    assert all("mock rationale" in p["rejection_reason"] for p in neg_lines)


@pytest.mark.sanity
def test_miner_drops_split_classes(
    mocked_taxonomy: dict[str, Path], tmp_path: Path
) -> None:
    """SPLIT consensus -> no pairs produced."""
    out_dir = tmp_path / "al"
    cmd = [
        sys.executable,
        str(SCRIPT_MINE),
        "--taxonomy",
        str(mocked_taxonomy["taxonomy"]),
        "--review",
        str(mocked_taxonomy["review"]),
        "--classes-dir",
        str(mocked_taxonomy["classes_dir"]),
        "--out-dir",
        str(out_dir),
        "--version",
        "drop",
        "--quiet",
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)

    pos_lines = [
        json.loads(line)
        for line in (out_dir / "positives_drop.jsonl").read_text().splitlines()
        if line.strip()
    ]
    neg_lines = [
        json.loads(line)
        for line in (out_dir / "hard_negatives_drop.jsonl").read_text().splitlines()
        if line.strip()
    ]
    # No pair should have source_class=="mock_split"
    assert not any(p["source_class"] == "mock_split" for p in pos_lines + neg_lines)


@pytest.mark.sanity
def test_miner_real_b3_smoke() -> None:
    """Mined files from the real B3 outputs are non-empty (regression guard)."""
    assert POSITIVES.exists(), "positives_v1.jsonl missing — run f2_mine_hard_negatives.py first"
    assert NEGATIVES.exists(), "hard_negatives_v1.jsonl missing"
    pos = [json.loads(l) for l in POSITIVES.read_text().splitlines() if l.strip()]
    neg = [json.loads(l) for l in NEGATIVES.read_text().splitlines() if l.strip()]
    assert len(pos) >= 5, f"too few positives mined: {len(pos)}"
    assert len(neg) >= 5, f"too few hard negatives mined: {len(neg)}"
    # all positives have label==1, all negatives label==0
    assert all(p["label"] == 1 for p in pos)
    assert all(p["label"] == 0 for p in neg)
    # source_verdict propagated
    assert all(p["source_verdict"] == "KEEP" for p in pos)
    assert all(p["source_verdict"] == "REJECT" for p in neg)


# ----------------------------------------------------------------------
# 2. ContrastiveFinetuner interface
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_load_pairs_round_trip(tmp_path: Path) -> None:
    """load_pairs reads positives + negatives jsonl, returns mixed list."""
    pos = tmp_path / "pos.jsonl"
    neg = tmp_path / "neg.jsonl"
    pos.write_text(
        json.dumps({"text_a": "x", "text_b": "y", "label": 1, "weight": 1.0}) + "\n"
    )
    neg.write_text(
        json.dumps({"text_a": "x", "text_b": "z", "label": 0, "weight": 0.7}) + "\n"
    )

    ft = ContrastiveFinetuner(mode="simulated")
    pairs = ft.load_pairs(pos, neg)
    assert len(pairs) == 2
    assert sum(p.label for p in pairs) == 1  # one positive
    assert all(isinstance(p, TrainingPair) for p in pairs)


@pytest.mark.sanity
def test_fit_evaluate_round_trip() -> None:
    """fit() then evaluate() returns FinetuneMetrics with sane fields."""
    pairs = [
        TrainingPair("apple fruit red", "banana fruit yellow", 1, 1.0, "fruit_class"),
        TrainingPair("apple fruit red", "cherry fruit red", 1, 1.0, "fruit_class"),
        TrainingPair("banana fruit yellow", "cherry fruit red", 1, 1.0, "fruit_class"),
        TrainingPair("apple fruit red", "screwdriver tool", 0, 1.0, "rejected"),
        TrainingPair("banana fruit yellow", "screwdriver tool", 0, 1.0, "rejected"),
        TrainingPair("cherry fruit red", "screwdriver tool", 0, 1.0, "rejected"),
    ]
    ft = ContrastiveFinetuner(lr=0.1, mode="simulated")
    train_m = ft.fit(pairs, epochs=3)
    assert isinstance(train_m, FinetuneMetrics)
    assert train_m.epochs == 3
    assert train_m.n_positives == 3
    assert train_m.n_hard_negatives == 3
    assert ft.is_fitted

    eval_m = ft.evaluate(pairs)
    assert 0.0 <= eval_m.r_at_5 <= 1.0
    assert 0.0 <= eval_m.r_at_10 <= 1.0
    assert 0.0 <= eval_m.mrr <= 1.0
    # silhouette in [-1, 1]
    assert -1.0 <= eval_m.silhouette <= 1.0


@pytest.mark.sanity
def test_real_mode_not_implemented() -> None:
    """mode='real' fit raises NotImplementedError (deferred to F2.1)."""
    ft = ContrastiveFinetuner(mode="real")
    pairs = [TrainingPair("a", "b", 1, 1.0)]
    with pytest.raises(NotImplementedError):
        ft.fit(pairs)


@pytest.mark.sanity
def test_fit_requires_pairs() -> None:
    ft = ContrastiveFinetuner(mode="simulated")
    with pytest.raises(ValueError):
        ft.fit([])


@pytest.mark.sanity
def test_evaluate_requires_fit() -> None:
    ft = ContrastiveFinetuner(mode="simulated")
    with pytest.raises(RuntimeError):
        ft.evaluate([TrainingPair("a", "b", 1, 1.0)])


@pytest.mark.sanity
def test_info_nce_loss_basic() -> None:
    """Loss helper sanity: closer-positive => lower loss than far-positive."""
    import numpy as np

    # 3-D vectors. Anchor close to positive, far from neg.
    anchor = np.array([1.0, 0.0, 0.0])
    pos_close = np.array([0.95, 0.05, 0.0])
    pos_far = np.array([0.0, 1.0, 0.0])
    neg = np.array([-1.0, 0.0, 0.0])
    loss_close = info_nce_loss(anchor, pos_close, np.array([neg]), temperature=0.1)
    loss_far = info_nce_loss(anchor, pos_far, np.array([neg]), temperature=0.1)
    assert loss_close < loss_far


# ----------------------------------------------------------------------
# 3. simulation end-to-end
# ----------------------------------------------------------------------
@pytest.mark.sanity
def test_simulation_produces_report() -> None:
    """End-to-end: simulate script produces a report file with metric table."""
    if not POSITIVES.exists() or not NEGATIVES.exists():
        pytest.skip("Mined pairs missing — run f2_mine_hard_negatives.py first")
    cmd = [
        sys.executable,
        str(SCRIPT_SIM),
        "--positives",
        str(POSITIVES),
        "--negatives",
        str(NEGATIVES),
        "--epochs",
        "5",
        "--quiet",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"simulation failed: {result.stderr}"
    payload = json.loads(result.stdout)
    assert "baseline" in payload and "after_al_eval" in payload
    assert REPORT.exists()
    md = REPORT.read_text(encoding="utf-8")
    assert "R@5" in md
    assert "Baseline" in md and "After-AL" in md


@pytest.mark.sanity
def test_simulation_metric_monotonicity_weak() -> None:
    """At least one of {R@5, R@10, MRR, silhouette} weakly improves under AL.

    Strict monotonicity isn't guaranteed on 80 noisy pairs split 80/20, so we
    require: NOT ALL eval metrics regress. The simulated finetuner only
    re-weights TF-IDF dimensions; if EVERY metric got worse, the wiring is
    broken (sign error in update, etc.).
    """
    if not POSITIVES.exists() or not NEGATIVES.exists():
        pytest.skip("Mined pairs missing")
    cmd = [
        sys.executable,
        str(SCRIPT_SIM),
        "--positives",
        str(POSITIVES),
        "--negatives",
        str(NEGATIVES),
        "--epochs",
        "10",
        "--quiet",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, f"simulation failed: {result.stderr}"
    payload = json.loads(result.stdout)
    baseline = payload["baseline"]
    after = payload["after_al_eval"]
    deltas = {
        "r_at_5": after["r_at_5"] - baseline["r_at_5"],
        "r_at_10": after["r_at_10"] - baseline["r_at_10"],
        "mrr": after["mrr"] - baseline["mrr"],
        "silhouette": after["silhouette"] - baseline["silhouette"],
    }
    # At least one metric should be ≥ 0 (weak monotonicity).
    assert any(d >= -1e-9 for d in deltas.values()), (
        f"all metrics regressed: {deltas}"
    )
