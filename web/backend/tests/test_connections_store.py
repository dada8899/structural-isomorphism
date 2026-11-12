"""ConnectionsStore + ConnectionsMatcher 单元测试（G-MVP, Session #19）。

覆盖：指纹 CRUD、可见性默认 L0、非法值降级、owner 隔离、
list_discoverable 排除 L0、匹配引擎跨域过滤 / 相似度阈值 /
普适类加成 / N 人计数。
"""
from __future__ import annotations

import numpy as np
import pytest

from services.connections_store import (
    ConnectionsStore,
    DEFAULT_VISIBILITY,
)
from services.connections_match import ConnectionsMatcher, encode_to_blob


# ---------------- fixtures ------------------------------------------- #


@pytest.fixture
def store(tmp_path):
    return ConnectionsStore(tmp_path / "test_conn.db")


def _vec(seed: int, dim: int = 16) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim).astype("<f4")


# ---------------- ConnectionsStore: CRUD ----------------------------- #


def test_create_and_get_fingerprint(store):
    fid = store.create_fingerprint(
        user_email="a@x.com",
        problem_summary="30 人公司效率塌陷",
        b_id="bio-001",
        domain="organization",
        type_id="T1",
        universality_class="delay-debt",
    )
    assert fid.startswith("fp_")
    row = store.get_fingerprint(fid)
    assert row is not None
    assert row["user_email"] == "a@x.com"
    assert row["problem_summary"] == "30 人公司效率塌陷"
    # 默认可见性最严 L0。
    assert row["visibility_level"] == DEFAULT_VISIBILITY == "L0"


def test_create_with_bad_visibility_downgrades_to_l0(store):
    fid = store.create_fingerprint(
        user_email="a@x.com",
        problem_summary="p",
        visibility_level="SUPER_PUBLIC",  # 非法
    )
    assert store.get_fingerprint(fid)["visibility_level"] == "L0"


def test_list_by_user_newest_first(store):
    f1 = store.create_fingerprint(user_email="a@x.com", problem_summary="p1")
    f2 = store.create_fingerprint(user_email="a@x.com", problem_summary="p2")
    store.create_fingerprint(user_email="other@x.com", problem_summary="p3")
    rows = store.list_by_user("a@x.com")
    assert len(rows) == 2
    assert {r["id"] for r in rows} == {f1, f2}


def test_set_visibility_owner_only(store):
    fid = store.create_fingerprint(user_email="a@x.com", problem_summary="p")
    # 非 owner 改不动。
    assert store.set_visibility(fid, "intruder@x.com", "L2") is False
    assert store.get_fingerprint(fid)["visibility_level"] == "L0"
    # owner 能改。
    assert store.set_visibility(fid, "a@x.com", "L1") is True
    assert store.get_fingerprint(fid)["visibility_level"] == "L1"


def test_set_visibility_rejects_illegal_level(store):
    fid = store.create_fingerprint(user_email="a@x.com", problem_summary="p")
    assert store.set_visibility(fid, "a@x.com", "L9") is False
    assert store.get_fingerprint(fid)["visibility_level"] == "L0"


def test_delete_fingerprint_owner_only(store):
    fid = store.create_fingerprint(user_email="a@x.com", problem_summary="p")
    assert store.delete_fingerprint(fid, "intruder@x.com") is False
    assert store.get_fingerprint(fid) is not None
    assert store.delete_fingerprint(fid, "a@x.com") is True
    assert store.get_fingerprint(fid) is None


def test_delete_all_for_user(store):
    store.create_fingerprint(user_email="a@x.com", problem_summary="p1")
    store.create_fingerprint(user_email="a@x.com", problem_summary="p2")
    store.create_fingerprint(user_email="b@x.com", problem_summary="p3")
    n = store.delete_all_for_user("a@x.com")
    assert n == 2
    assert store.list_by_user("a@x.com") == []
    assert len(store.list_by_user("b@x.com")) == 1


def test_list_discoverable_excludes_l0(store):
    store.create_fingerprint(
        user_email="a@x.com", problem_summary="p_l0", visibility_level="L0"
    )
    f1 = store.create_fingerprint(
        user_email="b@x.com", problem_summary="p_l1", visibility_level="L1"
    )
    f2 = store.create_fingerprint(
        user_email="c@x.com", problem_summary="p_l2", visibility_level="L2"
    )
    rows = store.list_discoverable()
    assert {r["id"] for r in rows} == {f1, f2}
    assert store.count_discoverable() == 2


def test_list_discoverable_excludes_self(store):
    store.create_fingerprint(
        user_email="me@x.com", problem_summary="mine", visibility_level="L1"
    )
    other = store.create_fingerprint(
        user_email="other@x.com", problem_summary="theirs", visibility_level="L1"
    )
    rows = store.list_discoverable(exclude_user="me@x.com")
    assert {r["id"] for r in rows} == {other}


def test_schema_self_heal_on_existing_db(tmp_path):
    # 旧表只有 id —— 再开 ConnectionsStore 应增量补齐列。
    db = tmp_path / "old.db"
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE structural_fingerprints (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()
    store = ConnectionsStore(db)  # 不应抛
    fid = store.create_fingerprint(user_email="a@x.com", problem_summary="p")
    assert store.get_fingerprint(fid)["user_email"] == "a@x.com"


# ---------------- ConnectionsMatcher --------------------------------- #


def _fp(fid, user, domain, ucls, vec, ucls_field=None):
    """构造一个匹配用 fingerprint dict。"""
    return {
        "id": fid,
        "user_email": user,
        "problem_summary": f"problem of {fid}",
        "b_id": None,
        "domain": domain,
        "type_id": "T1",
        "universality_class": ucls_field if ucls_field is not None else ucls,
        "visibility_level": "L1",
        "embedding": encode_to_blob(vec),
    }


def test_match_filters_same_domain():
    matcher = ConnectionsMatcher(search_service=None)
    base = _vec(1)
    target = _fp("t", "me@x.com", "organization", "delay-debt", base)
    # 候选：同领域（应被过滤）。embedding 几乎相同。
    same_domain = _fp("c1", "x@x.com", "organization", "delay-debt", base + 0.001)
    out = matcher.match(target, [same_domain])
    assert out == []  # 同域 → domain_distance 0 → 过滤


def test_match_keeps_cross_domain_high_sim():
    matcher = ConnectionsMatcher(search_service=None)
    base = _vec(2)
    target = _fp("t", "me@x.com", "organization", "delay-debt", base)
    cross = _fp("c1", "x@x.com", "ecology", "delay-debt", base + 0.0001)
    out = matcher.match(target, [cross])
    assert len(out) == 1
    assert out[0]["fingerprint_id"] == "c1"
    assert out[0]["domain_distance"] == 1
    assert out[0]["structural_similarity"] > 0.9
    # 同普适类 → 加成生效。
    assert out[0]["same_universality_class"] is True
    assert out[0]["combined_score"] > out[0]["structural_similarity"]


def test_match_filters_low_similarity():
    matcher = ConnectionsMatcher(search_service=None)
    target = _fp("t", "me@x.com", "organization", "delay-debt", _vec(3))
    # 完全无关向量 → 相似度低 → 过滤。
    far = _fp("c1", "x@x.com", "ecology", "delay-debt", _vec(999))
    out = matcher.match(target, [far], sim_min=0.5)
    assert out == []


def test_match_excludes_same_user():
    matcher = ConnectionsMatcher(search_service=None)
    base = _vec(4)
    target = _fp("t", "me@x.com", "organization", "delay-debt", base)
    # 同一用户的另一个跨域指纹 —— 不该匹配到自己。
    own = _fp("c1", "me@x.com", "ecology", "delay-debt", base)
    out = matcher.match(target, [own])
    assert out == []


def test_match_ranks_by_combined_score():
    matcher = ConnectionsMatcher(search_service=None)
    base = _vec(5)
    target = _fp("t", "me@x.com", "organization", "delay-debt", base)
    # 同类（加成） vs 异类（无加成），相似度都高。
    same_cls = _fp("c1", "a@x.com", "ecology", "delay-debt", base + 0.0001)
    diff_cls = _fp("c2", "b@x.com", "ecology", "other-class", base + 0.0001)
    out = matcher.match(target, [same_cls, diff_cls])
    assert len(out) == 2
    # 同普适类的应排前。
    assert out[0]["fingerprint_id"] == "c1"
    assert out[0]["same_universality_class"] is True
    assert out[1]["same_universality_class"] is False


def test_count_structural_neighbors():
    matcher = ConnectionsMatcher(search_service=None)
    base = _vec(6)
    target = _fp("t", "me@x.com", "organization", "delay-debt", base)
    cands = [
        _fp("c1", "a@x.com", "ecology", "delay-debt", base + 0.0001),
        _fp("c2", "b@x.com", "finance", "delay-debt", base + 0.0002),
        _fp("c3", "c@x.com", "organization", "delay-debt", base),  # 同域，不计
    ]
    assert matcher.count_structural_neighbors(target, cands) == 2


def test_match_handles_missing_embedding():
    matcher = ConnectionsMatcher(search_service=None)
    target = _fp("t", "me@x.com", "organization", "delay-debt", _vec(7))
    no_emb = _fp("c1", "x@x.com", "ecology", "delay-debt", _vec(8))
    no_emb["embedding"] = None  # 损坏 / 缺失
    out = matcher.match(target, [no_emb])
    assert out == []  # 相似度 0 → 过滤，不抛
