"""Session ***REMOVED***17 V2 + V3 — SearchService unified-similarity / cross-domain tests.

V3 — the信任 bugs:
  * relevance_score() must always return a value in [0, 1] even when the
    KB embedding is NOT L2-normalized (the kb_v2_embeddings.npy bug that
    made meta.similarity return 9.5 / 4.76).
  * search() now exposes the SAME relevance口径 on every result, so the
    analyze scope gate cannot self-contradictorily reject a result search
    ranked highly.

V2 — smart source selection:
  * each search result carries cross_domain + surface_domain so the
    frontend can recommend genuine cross-domain candidates.

The model load is ~13s; this whole module shares one SearchService via a
session-scoped fixture to amortise it.

Run:
    PYTHONPATH=web/backend:. .venv/bin/python -m pytest \
        web/backend/tests/test_search_service_v2v3.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent.parent
for p in (_BACKEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from services.search_service import SearchService  ***REMOVED*** noqa: E402


***REMOVED*** A tiny synthetic KB: 3 同域 (组织管理) + 3 跨域 phenomena. Mirrors the
***REMOVED*** Session ***REMOVED***17 实测 case — a 留存 query has 组织管理 as its surface domain.
_TINY_KB = """\
{"id": "p1", "name": "用户留存衰减", "domain": "组织管理", "type_id": "06", "description": "新用户在产品使用早期快速流失，留存率每月持续下降，越到后期流失速度反而趋缓。"}
{"id": "p2", "name": "团队协作效率塌陷", "domain": "组织管理", "type_id": "07", "description": "团队规模扩大后沟通成本急剧上升，整体效率不升反降。"}
{"id": "p3", "name": "组织决策迟滞", "domain": "组织管理", "type_id": "08", "description": "层级增多导致决策链条变长，反馈延迟，响应速度下降。"}
{"id": "p4", "name": "磁滞损耗", "domain": "电气工程", "type_id": "06", "description": "铁磁材料在交变磁场中反复磁化与退磁，能量以热的形式不可逆地损耗。"}
{"id": "p5", "name": "减速器效率级联", "domain": "机械工程", "type_id": "07", "description": "多级齿轮减速器中每一级都有效率损失，整体效率是各级效率的连乘。"}
{"id": "p6", "name": "放射性衰变", "domain": "核物理", "type_id": "06", "description": "不稳定原子核自发释放粒子，释放速度只取决于当前剩余的不稳定原子数量。"}
"""


@pytest.fixture(scope="module")
def svc(tmp_path_factory):
    """One SearchService for the whole module — amortises the ~13s model load."""
    d = tmp_path_factory.mktemp("kb")
    (d / "tiny_kb.jsonl").write_text(_TINY_KB, encoding="utf-8")
    return SearchService(data_dir=str(d), kb_file="tiny_kb.jsonl")


***REMOVED*** --------- V3.1 — _cosine: legal range even for un-normalized input --------- ***REMOVED***


class TestCosineLegality:
    def test_identical_vectors(self):
        v = np.array([1.0, 2.0, 3.0])
        assert SearchService._cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal(self):
        assert SearchService._cosine(
            np.array([1.0, 0.0]), np.array([0.0, 1.0])
        ) == pytest.approx(0.0)

    def test_antiparallel(self):
        assert SearchService._cosine(
            np.array([1.0, 0.0]), np.array([-3.0, 0.0])
        ) == pytest.approx(-1.0)

    def test_unnormalized_parallel_is_still_one(self):
        """The kb_v2_embeddings.npy bug: a norm-18 vector parallel to a
        norm-1 vector must still be cosine 1.0, NOT 18.0."""
        small = np.array([1.0, 0.0, 0.0])
        big = np.array([18.0, 0.0, 0.0])
        assert SearchService._cosine(small, big) == pytest.approx(1.0)

    def test_zero_vector_is_zero(self):
        assert SearchService._cosine(
            np.array([1.0, 0.0]), np.zeros(2)
        ) == 0.0

    @pytest.mark.parametrize("seed", range(8))
    def test_random_vectors_always_in_range(self, seed):
        rng = np.random.default_rng(seed)
        ***REMOVED*** Deliberately un-normalized, arbitrary magnitude.
        a = rng.normal(size=64) * rng.uniform(0.1, 30)
        b = rng.normal(size=64) * rng.uniform(0.1, 30)
        c = SearchService._cosine(a, b)
        assert -1.0 <= c <= 1.0


***REMOVED*** --------- V3.2 — relevance_score: unified [0,1]口径 --------- ***REMOVED***


class TestRelevanceScore:
    def test_relevance_in_unit_range(self, svc):
        rel = svc.relevance_score("用户留存率每月持续下降", "p1")
        assert 0.0 <= rel <= 1.0

    def test_relevant_query_scores_high(self, svc):
        """A genuinely matching query → relevance well above orthogonal 0.5."""
        rel = svc.relevance_score("用户留存率每月持续下降", "p1")
        assert rel > 0.6

    def test_unknown_phenomenon_returns_zero(self, svc):
        assert svc.relevance_score("anything", "no-such-id") == 0.0

    def test_search_relevance_matches_relevance_score口径(self, svc):
        """V3.2 contract: the relevance a result carries in search() is the
        SAME transform relevance_score() applies — so analyze's scope gate
        (which calls relevance_score) cannot contradict search."""
        q = "用户留存率每月持续下降"
        results = svc.search(q, top_k=6)
        by_id = {r["id"]: r for r in results}
        assert "p1" in by_id
        ***REMOVED*** Same query, same phenomenon → identical relevance value.
        assert by_id["p1"]["relevance"] == pytest.approx(
            svc.relevance_score(q, "p1"), abs=1e-3
        )


***REMOVED*** --------- V2 — cross-domain detection --------- ***REMOVED***


class TestCrossDomainDetection:
    def test_results_carry_v2_fields(self, svc):
        results = svc.search("用户留存率每月下降", top_k=6)
        assert results, "expected non-empty results"
        for r in results:
            assert "relevance" in r
            assert "cross_domain" in r
            assert "surface_domain" in r
            assert isinstance(r["cross_domain"], bool)

    def test_surface_domain_inferred_for_clustered_query(self, svc):
        """A 留存/组织 query pulls a 组织管理 cluster — surface domain detected."""
        results = svc.search("用户留存率每月下降团队效率", top_k=6)
        assert results[0]["surface_domain"] == "组织管理"

    def test_same_domain_results_flagged_not_cross(self, svc):
        results = svc.search("用户留存率每月下降团队效率", top_k=6)
        org = [r for r in results if r["domain"] == "组织管理"]
        assert org, "expected some 组织管理 results"
        for r in org:
            assert r["cross_domain"] is False

    def test_cross_domain_results_flagged_cross(self, svc):
        results = svc.search("用户留存率每月下降团队效率", top_k=6)
        non_org = [r for r in results if r["domain"] != "组织管理"]
        for r in non_org:
            assert r["cross_domain"] is True

    def test_no_surface_domain_defaults_cross_true(self, svc):
        """When no domain dominates the pool, surface_domain is None and
        every result defaults to cross_domain=True (no false penalty)."""
        ***REMOVED*** A vague query that won't cluster strongly into one domain.
        results = svc.search("能量损耗", top_k=6)
        if results and results[0]["surface_domain"] is None:
            assert all(r["cross_domain"] for r in results)
