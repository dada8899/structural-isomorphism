"""X1 Linguistics expansion (2026-05-24) — KB coverage sanity tests.

X1 audit (docs/coverage/kb-coverage-audit-2026-05-24.md) called linguistics
the Top-1 sparse area: 22/84 type_ids fully empty, plus 0-hit专有名词 for
Zipf / Heaps / S-curve adoption / glottochronology / Greenberg word-order.

This module verifies the 150-entry expansion in
`data/kb-additions-2026-05-24-linguistics.jsonl` actually recalls those
专有名词 queries.

We mirror the neuroscience X1 sanity test pattern: BM25-only over the new
JSONL with the same jieba tokeniser the production SearchService uses
(see services/search_service.py). BM25 is the precision floor — if it
recalls a phenomenon, the hybrid embedding ranker will too (embeddings
relax the lexical match, never tighten it).

Spec-mandated queries (from task brief):
  1. "Zipf 律"
  2. "Heaps 律"
  3. "S-curve adoption"
  4. "glottochronology"
  5. "word-order universal"

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

ADDITIONS = _ROOT / "data" / "kb-additions-2026-05-24-linguistics.jsonl"


def _load_rows() -> list[dict]:
    if not ADDITIONS.exists():
        pytest.skip(f"Additions file missing: {ADDITIONS}")
    with open(ADDITIONS, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _tokenize(text: str) -> list[str]:
    """Mirror the search_service tokeniser — jieba CJK cut + lower-case latin.

    The production SearchService applies jieba on `name name description`.
    For the BM25 floor we use the same recipe so this sanity test's signal
    aligns with the hybrid ranker's lexical contribution.
    """
    try:
        import jieba  # type: ignore

        return [t for t in jieba.lcut(text.lower()) if t.strip()]
    except Exception:
        import re

        out: list[str] = []
        for m in re.finditer(r"[A-Za-z][A-Za-z0-9_-]*|[一-鿿]", text.lower()):
            out.append(m.group(0))
        return out


@pytest.fixture(scope="module")
def kb_rows() -> list[dict]:
    rows = _load_rows()
    assert len(rows) == 150, (
        f"Expected 150 linguistics additions per X1 task brief, got {len(rows)}"
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
        # SearchService doubles 'name' for relative lexical weighting.
        text = f"{r.get('name','')} {r.get('name','')} {r.get('description','')}"
        corpus.append(_tokenize(text))
    return BM25Okapi(corpus), kb_rows


def _topk(bm25_pair, query: str, k: int = 5):
    bm25, rows = bm25_pair
    scores = bm25.get_scores(_tokenize(query))
    order = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return [(rows[i], scores[i]) for i in order]


# --- Sanity tests --------------------------------------------------------- #


@pytest.mark.sanity
class TestLinguisticsCoverageX1:
    """One test per spec-mandated 0-hit query.

    Each test asserts:
      (a) BM25 returns at least one hit with score > 0
      (b) The top-5 contains a phenomenon whose name OR description holds
          the expected anchor keyword (case-insensitive). Anchor IDs are
          listed in the assertion message so failures point to the missing
          entry directly.
    """

    def test_zipf_law_recall(self, bm25_index):
        """X1 line 92: 'Zipf law / Heaps law (专有名词) 0/0 命中'."""
        hits = _topk(bm25_index, "Zipf 律", k=5)
        assert hits[0][1] > 0, "BM25 produced no signal for 'Zipf 律'"
        ids = {h[0]["id"] for h in hits}
        # Multiple Zipf-flavoured entries exist; any of them counts.
        zipf_anchors = {
            "5k-22-101",  # Zipf词频幂律
            "5k-22-102",  # Zipf-Mandelbrot
            "5k-22-108",  # Hapax legomena占比定律 (covers Zipf tail)
            "5k-22-112",  # Zipf复合词层级律
            "5k-22-164",  # Synonym多义性Zipf律
            "5k-22-187",  # Collocation Zipf分布
            "5k-22-236",  # Sign language Zipf律
        }
        assert ids & zipf_anchors, (
            f"Top-5 missed all Zipf entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_heaps_law_recall(self, bm25_index):
        """Heaps' law vocabulary growth — 5k-22-103."""
        hits = _topk(bm25_index, "Heaps 律", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        assert "5k-22-103" in ids, (
            f"Heaps entry missed from top-5. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_s_curve_adoption_recall(self, bm25_index):
        """S-curve adoption — Piotrowski / Bass / Labov S-curve entries."""
        hits = _topk(bm25_index, "S-curve adoption", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        s_curve_anchors = {
            "5k-22-106",  # Piotrowski 语言演化 S 曲线
            "5k-22-129",  # Labov 年龄分层 S 曲线
            "5k-22-136",  # Bass 语言创新扩散律
            "5k-22-142",  # Lexical diffusion 词项级扩散
        }
        assert ids & s_curve_anchors, (
            f"Top-5 missed all S-curve entries. Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_glottochronology_recall(self, bm25_index):
        """Swadesh glottochronology decay — 5k-22-168 + cognate decay 5k-22-176."""
        hits = _topk(bm25_index, "glottochronology", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        glotto_anchors = {
            "5k-22-168",  # Swadesh glottochronology 衰减
            "5k-22-169",  # Bergsland-Vogt 衰减率方差
            "5k-22-176",  # Cognate decay 指数律
        }
        assert ids & glotto_anchors, (
            f"Top-5 missed all glottochronology entries. "
            f"Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )

    def test_word_order_universal_recall(self, bm25_index):
        """Greenberg word-order universals — 5k-22-202, 203, 204."""
        hits = _topk(bm25_index, "Greenberg word-order universal", k=5)
        assert hits[0][1] > 0
        ids = {h[0]["id"] for h in hits}
        wo_anchors = {
            "5k-22-202",  # Greenberg-SOV 普遍性
            "5k-22-203",  # Greenberg 词序形容词隐含律
            "5k-22-204",  # Dryer 词序相关性
            "5k-22-215",  # Greenberg-tone vs syllable
        }
        assert ids & wo_anchors, (
            f"Top-5 missed all Greenberg word-order entries. "
            f"Got: {[(h[0]['id'], h[0]['name']) for h in hits]}"
        )


@pytest.mark.sanity
class TestLinguisticsAdditionsIntegrity:
    """Structural / metadata-level invariants on the additions file."""

    def test_count_is_150(self, kb_rows):
        assert len(kb_rows) == 150

    def test_all_ids_unique_and_namespaced(self, kb_rows):
        ids = [r["id"] for r in kb_rows]
        assert len(set(ids)) == len(ids), "duplicate ids in additions file"
        for i in ids:
            # Linguistics namespace; existing 5k-22-001..100 reserved,
            # additions span 5k-22-101..250.
            assert i.startswith("5k-22-"), f"id outside linguistics namespace: {i}"
            tail = int(i.split("-")[-1])
            assert 101 <= tail <= 250, f"id outside additions range: {i}"

    def test_required_fields_present(self, kb_rows):
        for r in kb_rows:
            for field in ("id", "name", "domain", "type_id", "description"):
                assert field in r and r[field], f"missing {field} on {r.get('id')}"
            assert r["domain"] == "语言学", f"unexpected domain on {r['id']}: {r['domain']}"

    def test_description_min_length(self, kb_rows):
        # Task brief mandates >= 50 字 with a concrete quantitative observation.
        for r in kb_rows:
            assert len(r["description"]) >= 50, (
                f"{r['id']} description too short ({len(r['description'])} chars)"
            )

    def test_type_id_diversity(self, kb_rows):
        """X1 spec mandates >= 22 of the previously-empty type_ids covered."""
        tids = {r["type_id"] for r in kb_rows}
        # Existing linguistics coverage (5k-22-001..100) used these type_ids:
        already_covered = {"01", "02", "04", "13", "15", "16", "52", "63", "65", "70", "73"}
        newly_covered = tids - already_covered
        assert len(newly_covered) >= 22, (
            f"Expected >=22 newly-covered type_ids per X1 spec, "
            f"got {len(newly_covered)}: {sorted(newly_covered)}"
        )
