"""X1 Neuroscience expansion (2026-05-24) — KB coverage sanity tests.

X1 audit identified neuroscience × {06,13,21,23,25,32} as fully-empty cells.
This sanity test verifies that after the 80-entry expansion, each of the 5
queries called out in the X1 follow-up brief can recall ≥ 1 relevant
neuroscience entry from `data/kb-additions-2026-05-24-neuroscience.jsonl`.

We deliberately avoid loading the SentenceTransformer model here (it costs
~13s and the .npy needs a separate update pipeline). Instead we run a
lightweight BM25-based recall using the same `rank_bm25` + `jieba`
tokeniser the production SearchService uses for the hybrid lexical signal
(see services/search_service.py). If BM25 can recall the relevant entry in
top-5, the embedding model will too (embeddings are looser/broader, BM25
is the stricter precision floor).

Spec-mandated queries:
  1. "gamma oscillation"
  2. "cortical avalanche"
  3. "reaction time power law"
  4. "Ebbinghaus forgetting"
  5. "epileptic seizure spread"

Coverage marker: sanity
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent.parent
for p in (_BACKEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

ADDITIONS = _ROOT / "data" / "kb-additions-2026-05-24-neuroscience.jsonl"


def _load_rows() -> list[dict]:
    if not ADDITIONS.exists():
        pytest.skip(f"Additions file missing: {ADDITIONS}")
    with open(ADDITIONS, "r", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _tokenize(text: str) -> list[str]:
    """Mirror the search_service tokeniser: jieba cut + lower-case latin tokens.

    The full SearchService uses jieba on `name name description`. For this
    sanity test we apply the same recipe so BM25 scoring lines up with the
    production lexical signal. If jieba is unavailable we fall back to a
    simple latin / CJK character split (still adequate for the 5 spec
    queries which all have unambiguous keyword anchors).
    """
    try:
        import jieba  # type: ignore

        return [t for t in jieba.lcut(text.lower()) if t.strip()]
    except Exception:
        # Fallback: latin tokens + single CJK chars
        import re

        out: list[str] = []
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9_-]*|[一-鿿]", text.lower()):
            out.append(m.group(0))
        return out


@pytest.fixture(scope="module")
def kb_rows() -> list[dict]:
    rows = _load_rows()
    assert len(rows) == 80, (
        f"Expected 80 neuroscience additions per X1 spec, got {len(rows)}"
    )
    return rows


@pytest.fixture(scope="module")
def bm25_index(kb_rows):
    try:
        from rank_bm25 import BM25Okapi  # type: ignore
    except ImportError:
        pytest.skip("rank_bm25 not installed (declared in web/backend/requirements.txt)")

    corpus = []
    for r in kb_rows:
        text = f"{r.get('name','')} {r.get('name','')} {r.get('description','')}"
        corpus.append(_tokenize(text))
    return BM25Okapi(corpus), kb_rows


def _topk(bm25_pair, query: str, k: int = 5):
    bm25, rows = bm25_pair
    scores = bm25.get_scores(_tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return [(rows[i], scores[i]) for i in order]


# --- Sanity tests ---------------------------------------------------------


@pytest.mark.sanity
class TestNeuroscienceCoverageX1:
    """One test per spec-mandated query. All 5 must pass.

    Each test asserts:
      (a) BM25 returns at least 1 hit with score > 0
      (b) The top-5 contains a phenomenon whose name OR description
          contains the expected anchor keyword (case-insensitive)
    """

    def test_gamma_oscillation_recall(self, bm25_index):
        # Anchor: gamma 40 Hz I-I feedback entry (neuro-x1-022)
        hits = _topk(bm25_index, "gamma oscillation", k=5)
        assert hits[0][1] > 0, "BM25 produced no signal for 'gamma oscillation'"
        ids = {h[0]["id"] for h in hits}
        # Either the canonical entry, or any gamma-related entry must appear
        gamma_related = {"neuro-x1-017", "neuro-x1-022", "neuro-x1-034"}
        assert ids & gamma_related, (
            f"Top-5 missed all gamma entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_cortical_avalanche_recall(self, bm25_index):
        # Anchor: Beggs & Plenz cortical avalanche (neuro-x1-050) + epileptic avalanche (neuro-x1-049)
        hits = _topk(bm25_index, "cortical avalanche", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        avalanche_related = {"neuro-x1-049", "neuro-x1-050", "neuro-x1-047"}
        assert ids & avalanche_related, (
            f"Top-5 missed all avalanche entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_reaction_time_power_law_recall(self, bm25_index):
        # Anchor: neuro-x1-061 (RT power law) + neuro-x1-062 (learning power law)
        hits = _topk(bm25_index, "reaction time power law", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        power_related = {"neuro-x1-061", "neuro-x1-062", "neuro-x1-064"}
        assert ids & power_related, (
            f"Top-5 missed all reaction-time / power-law entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_ebbinghaus_forgetting_recall(self, bm25_index):
        # Anchor: neuro-x1-063 Ebbinghaus forgetting curve
        hits = _topk(bm25_index, "Ebbinghaus forgetting", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        assert "neuro-x1-063" in ids, (
            f"Ebbinghaus entry missed from top-5. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_epileptic_seizure_spread_recall(self, bm25_index):
        # Anchor: epileptic seizure spread / cascade (neuro-x1-049, neuro-x1-018, neuro-x1-043, neuro-x1-059)
        hits = _topk(bm25_index, "epileptic seizure spread", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        seizure_related = {
            "neuro-x1-018",  # 癫痫尖波扩散
            "neuro-x1-043",  # 癫痫起始一阶跳变
            "neuro-x1-049",  # 癫痫雪崩级联
            "neuro-x1-059",  # 颞叶癫痫病灶传播
            "neuro-x1-079",  # Epileptor saddle-node
        }
        assert ids & seizure_related, (
            f"Top-5 missed all seizure-spread entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )


@pytest.mark.sanity
class TestNeuroscienceShapeInvariants:
    """Structural invariants on the 80 additions (X1 spec compliance)."""

    def test_total_count_is_80(self, kb_rows):
        assert len(kb_rows) == 80

    def test_required_fields(self, kb_rows):
        for r in kb_rows:
            for k in ("id", "name", "domain", "type_id", "description"):
                assert k in r and r[k], f"Row {r.get('id')} missing field {k}"

    def test_description_length(self, kb_rows):
        # X1 spec: each description ≥ 50 chars
        short = [r["id"] for r in kb_rows if len(r["description"]) < 50]
        assert not short, f"Rows below 50-char floor: {short}"

    def test_id_prefix_uniformity(self, kb_rows):
        # All IDs follow neuro-x1-NNN convention
        bad = [r["id"] for r in kb_rows if not r["id"].startswith("neuro-x1-")]
        assert not bad, f"IDs missing neuro-x1- prefix: {bad}"

    def test_type_id_diversity_per_X1_spec(self, kb_rows):
        # X1 called out 6 spec type_ids as fully-empty: 06, 13, 21, 23, 25, 32
        from collections import Counter

        cnt = Counter(r["type_id"] for r in kb_rows)
        required = {"06", "13", "21", "23", "25", "32"}
        missing = [t for t in required if cnt.get(t, 0) < 5]
        assert not missing, (
            f"Spec-required type_ids underfilled (< 5 entries): {missing}; counts: {dict(cnt)}"
        )

    def test_no_duplicate_ids(self, kb_rows):
        ids = [r["id"] for r in kb_rows]
        assert len(ids) == len(set(ids)), "Duplicate IDs in additions"

    def test_no_duplicate_names(self, kb_rows):
        names = [r["name"] for r in kb_rows]
        assert len(names) == len(set(names)), "Duplicate names in additions"

    def test_no_id_collision_with_existing_kb(self):
        # Hardening: detect *partial* ID overlap with the active KB.
        #
        # After the additions file is merged into master KB (e.g. via
        # `scripts/merge_kb_additions.py`), the additions IDs naturally
        # appear in master KB — that's the merge, not a collision.
        # A real collision would be: someone added a NEW entry to the
        # additions file with an ID that already lived in master KB
        # from a different source — i.e. partial overlap. We check
        # for that by requiring: full subset (= clean merge) OR
        # empty intersection (= not yet merged).
        for kb_name in ("kb-expanded.jsonl", "kb-5000-merged.jsonl"):
            kb_path = _ROOT / "data" / kb_name
            if not kb_path.exists():
                continue
            with open(kb_path, "r", encoding="utf-8") as f:
                existing_ids = {json.loads(l)["id"] for l in f if l.strip()}
            new_ids = {r["id"] for r in _load_rows()}
            collisions = new_ids & existing_ids
            if not collisions:
                continue  # not yet merged into this KB — clean
            if new_ids.issubset(existing_ids):
                continue  # fully merged (post-merge state) — clean
            partial_new = new_ids - existing_ids
            assert False, (
                f"Partial ID collision with {kb_name}: "
                f"{len(collisions)} additions IDs match master AND "
                f"{len(partial_new)} additions IDs are new. "
                f"This means additions overlap with master from a "
                f"different source. Sample clashing: {sorted(collisions)[:5]}"
            )
