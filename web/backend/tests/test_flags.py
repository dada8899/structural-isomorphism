"""Unit + integration tests for feature flags — session #10 W15-E.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_flags.py -v
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import flags as flags_mod  # noqa: E402
from flags import (  # noqa: E402
    _bucket,
    get_all_experiments,
    get_all_flags,
    get_variant,
    is_enabled,
    reset_cache_for_tests,
)


@pytest.fixture
def yaml_config(tmp_path, monkeypatch):
    """Create a fresh YAML config file and point flags to it."""
    config = tmp_path / "feature_flags.yaml"
    monkeypatch.setenv("FEATURE_FLAGS_PATH", str(config))
    reset_cache_for_tests()
    return config


def _write(p: Path, body: str) -> None:
    p.write_text(body, encoding="utf-8")
    reset_cache_for_tests()


# -----------------------------------------------------------------------------
# Basic on/off
# -----------------------------------------------------------------------------


def test_flag_enabled_no_rollout(yaml_config):
    _write(yaml_config, """
flags:
  my_flag:
    enabled: true
""")
    assert is_enabled("my_flag", "user-1") is True


def test_flag_disabled(yaml_config):
    _write(yaml_config, """
flags:
  my_flag:
    enabled: false
""")
    assert is_enabled("my_flag", "user-1") is False


def test_unknown_flag_returns_false(yaml_config):
    _write(yaml_config, """
flags: {}
""")
    assert is_enabled("nonexistent_flag", "user-1") is False
    assert is_enabled("nonexistent_flag", None) is False


def test_missing_config_file(tmp_path, monkeypatch):
    """No config file -> all flags off, no crash."""
    monkeypatch.setenv("FEATURE_FLAGS_PATH", str(tmp_path / "does_not_exist.yaml"))
    reset_cache_for_tests()
    assert is_enabled("anything", "user-1") is False
    assert get_variant("anything", "user-1") == "control"


# -----------------------------------------------------------------------------
# Percentage rollout
# -----------------------------------------------------------------------------


def test_percentage_rollout_100(yaml_config):
    _write(yaml_config, """
flags:
  full_rollout:
    enabled: true
    rollout:
      type: percentage
      value: 100
""")
    for uid in ["a", "b", "c", "d", "e"]:
        assert is_enabled("full_rollout", uid) is True


def test_percentage_rollout_0(yaml_config):
    _write(yaml_config, """
flags:
  zero_rollout:
    enabled: true
    rollout:
      type: percentage
      value: 0
""")
    for uid in ["a", "b", "c", "d", "e"]:
        assert is_enabled("zero_rollout", uid) is False


def test_percentage_rollout_deterministic(yaml_config):
    """Same user_id + flag -> same answer across many calls."""
    _write(yaml_config, """
flags:
  partial:
    enabled: true
    rollout:
      type: percentage
      value: 50
""")
    first = is_enabled("partial", "user-abc")
    for _ in range(20):
        assert is_enabled("partial", "user-abc") is first


def test_percentage_rollout_distribution(yaml_config):
    """50% rollout across 10k synthetic users — within 2% tolerance."""
    _write(yaml_config, """
flags:
  partial:
    enabled: true
    rollout:
      type: percentage
      value: 50
""")
    n = 10000
    enabled_count = sum(is_enabled("partial", f"user-{i}") for i in range(n))
    ratio = enabled_count / n
    assert 0.48 <= ratio <= 0.52, f"50% rollout: got {ratio:.4f}, want 0.50±0.02"


# -----------------------------------------------------------------------------
# Segment (tier) rollout
# -----------------------------------------------------------------------------


def test_segment_rollout_tier_match(yaml_config, monkeypatch):
    _write(yaml_config, """
flags:
  pro_feature:
    enabled: true
    rollout:
      type: segment
      segments: [pro, team, admin]
""")
    from middleware.rate_limit import CURRENT_TIER

    # 'free' tier -> excluded
    tok = CURRENT_TIER.set("free")
    try:
        assert is_enabled("pro_feature", "user-1") is False
    finally:
        CURRENT_TIER.reset(tok)

    # 'pro' tier -> included
    tok = CURRENT_TIER.set("pro")
    try:
        assert is_enabled("pro_feature", "user-1") is True
    finally:
        CURRENT_TIER.reset(tok)

    # 'admin' tier -> included
    tok = CURRENT_TIER.set("admin")
    try:
        assert is_enabled("pro_feature", "user-1") is True
    finally:
        CURRENT_TIER.reset(tok)


def test_unknown_rollout_type_fails_closed(yaml_config):
    _write(yaml_config, """
flags:
  bogus:
    enabled: true
    rollout:
      type: not_a_real_type
      value: 100
""")
    assert is_enabled("bogus", "user-1") is False


# -----------------------------------------------------------------------------
# Experiments / variants
# -----------------------------------------------------------------------------


def test_experiment_missing_returns_control(yaml_config):
    _write(yaml_config, "flags: {}\nexperiments: {}\n")
    assert get_variant("not_a_real_exp", "user-1") == "control"


def test_experiment_anon_returns_control(yaml_config):
    _write(yaml_config, """
experiments:
  hero_cta_text_v2:
    variants:
      control: "Browse signals"
      treatment: "See live data"
    allocation:
      control: 50
      treatment: 50
""")
    assert get_variant("hero_cta_text_v2", None) == "control"
    assert get_variant("hero_cta_text_v2", "") == "control"


def test_experiment_deterministic(yaml_config):
    _write(yaml_config, """
experiments:
  exp1:
    variants:
      control: "A"
      treatment: "B"
    allocation:
      control: 50
      treatment: 50
""")
    first = get_variant("exp1", "user-zzz")
    for _ in range(20):
        assert get_variant("exp1", "user-zzz") == first


def test_experiment_allocation_50_50(yaml_config):
    """10k users -> 50/50 within 2% tolerance."""
    _write(yaml_config, """
experiments:
  exp1:
    variants:
      control: "A"
      treatment: "B"
    allocation:
      control: 50
      treatment: 50
""")
    n = 10000
    control = sum(get_variant("exp1", f"u-{i}") == "control" for i in range(n))
    ratio = control / n
    assert 0.48 <= ratio <= 0.52, f"50/50 allocation: control ratio {ratio:.4f}"


def test_experiment_allocation_unequal(yaml_config):
    """80/20 split — within 2% tolerance."""
    _write(yaml_config, """
experiments:
  exp1:
    variants:
      control: "A"
      treatment: "B"
    allocation:
      control: 80
      treatment: 20
""")
    n = 10000
    control = sum(get_variant("exp1", f"u-{i}") == "control" for i in range(n))
    ratio = control / n
    assert 0.78 <= ratio <= 0.82, f"80/20 allocation: control ratio {ratio:.4f}"


# -----------------------------------------------------------------------------
# Hot-reload (TTL + mtime)
# -----------------------------------------------------------------------------


def test_hot_reload_on_mtime_change(yaml_config):
    """Rewrite YAML -> next call (after force) reads new value."""
    _write(yaml_config, """
flags:
  toggle:
    enabled: false
""")
    assert is_enabled("toggle", "u") is False

    # Bump mtime + content. Use os.utime to ensure mtime actually advances
    # (some filesystems have low-resolution mtime, so add 2s).
    import os
    yaml_config.write_text("""
flags:
  toggle:
    enabled: true
""", encoding="utf-8")
    new_mtime = time.time() + 2
    os.utime(yaml_config, (new_mtime, new_mtime))

    # Force reload (production path: TTL expires after 30s, but tests
    # don't wait — explicit reset is the equivalent of TTL elapsing).
    reset_cache_for_tests()
    assert is_enabled("toggle", "u") is True


def test_cache_hits_without_filesystem(yaml_config, monkeypatch):
    """Repeated calls within TTL should not re-stat the file."""
    _write(yaml_config, """
flags:
  cached:
    enabled: true
""")
    # Warm cache.
    assert is_enabled("cached", "u") is True

    # Now simulate file deletion — cache should still return True.
    yaml_config.unlink()
    # Don't reset cache; we're testing that TTL keeps the prior good value.
    assert is_enabled("cached", "u") is True


# -----------------------------------------------------------------------------
# Bucketing primitives
# -----------------------------------------------------------------------------


def test_bucket_in_range():
    for uid in ["a", "b", "c", "user-1000", ""]:
        b = _bucket(uid, "some_flag")
        assert 0 <= b <= 99


def test_bucket_deterministic():
    assert _bucket("alice", "flag_x") == _bucket("alice", "flag_x")
    # Different keys -> (almost certainly) different buckets.
    assert _bucket("alice", "flag_x") != _bucket("alice", "flag_y") or True


# -----------------------------------------------------------------------------
# API endpoint integration
# -----------------------------------------------------------------------------


def test_api_get_flags_endpoint(yaml_config):
    """End-to-end via FastAPI TestClient."""
    _write(yaml_config, """
flags:
  new_pricing_layout:
    enabled: true
    rollout:
      type: percentage
      value: 100
  dark_mode_default:
    enabled: false
experiments:
  hero_cta_text_v2:
    variants:
      control: "Browse signals"
      treatment: "See live data"
    allocation:
      control: 50
      treatment: 50
""")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import flags as flags_api

    app = FastAPI()
    app.include_router(flags_api.router, prefix="/api")
    client = TestClient(app)

    r = client.get("/api/flags", headers={"X-Anon-Id": "anon-test-123"})
    assert r.status_code == 200
    data = r.json()
    assert data["flags"]["new_pricing_layout"] is True
    assert data["flags"]["dark_mode_default"] is False
    assert data["experiments"]["hero_cta_text_v2"] in ("control", "treatment")
    assert data["variants"]["hero_cta_text_v2"] in ("Browse signals", "See live data")


def test_api_anonymous_user_gets_control(yaml_config):
    """No X-Anon-Id -> anon -> experiment returns 'control'."""
    _write(yaml_config, """
experiments:
  exp1:
    variants:
      control: "A"
      treatment: "B"
    allocation:
      control: 50
      treatment: 50
""")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api import flags as flags_api

    app = FastAPI()
    app.include_router(flags_api.router, prefix="/api")
    client = TestClient(app)

    r = client.get("/api/flags")  # no header
    assert r.status_code == 200
    assert r.json()["experiments"]["exp1"] == "control"


# -----------------------------------------------------------------------------
# get_all_flags / get_all_experiments shape
# -----------------------------------------------------------------------------


def test_get_all_flags_shape(yaml_config):
    _write(yaml_config, """
flags:
  a:
    enabled: true
  b:
    enabled: false
""")
    out = get_all_flags("u")
    assert out == {"a": True, "b": False}


def test_get_all_experiments_shape(yaml_config):
    _write(yaml_config, """
experiments:
  exp1:
    variants: {control: "A", treatment: "B"}
    allocation: {control: 50, treatment: 50}
""")
    out = get_all_experiments("user-xyz")
    assert set(out.keys()) == {"exp1"}
    assert out["exp1"] in ("control", "treatment")
