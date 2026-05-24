"""Sanity-check the X3 city-zipf empirical validation (2026-05-24).

Three layers per spec:

1. Smoke   — raw data + results.json exist, parse, and are non-empty.
2. Schema  — KB additions JSONL has valid id/name/domain/type_id/description
             fields; no overlap with the X1 Urban agent's definitional entries
             at urb-011..urb-015.
3. Sanity  — fitted Zipf exponent s is inside [0.5, 2.0] for every country,
             consistent with cross-country empirical literature.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CITY_ZIPF_DIR = REPO_ROOT / "v4" / "validation" / "city-zipf"
RAW_DIR = CITY_ZIPF_DIR / "raw"
RESULTS = CITY_ZIPF_DIR / "results.json"

KB_FILE = REPO_ROOT / "data" / "kb-additions-2026-05-24-city-zipf-empirical.jsonl"
KB_URBAN = REPO_ROOT / "data" / "kb-additions-2026-05-24-urban-social.jsonl"

EXPECTED_COUNTRIES = ["united_states", "china", "india", "germany", "brazil"]


# ---- Layer 1: smoke ----


def test_raw_dir_exists() -> None:
    assert RAW_DIR.is_dir(), f"missing {RAW_DIR}; run fetch_cities.py"


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_raw_country_file_exists(country: str) -> None:
    p = RAW_DIR / f"{country}.jsonl"
    assert p.is_file(), f"missing {p}; run fetch_cities.py"


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_raw_country_min_rows(country: str) -> None:
    p = RAW_DIR / f"{country}.jsonl"
    rows = []
    with p.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    # Germany has only ~80 cities >= 100k; everyone else is 100.
    min_expected = 50 if country == "germany" else 100
    assert len(rows) >= min_expected, (
        f"{country}: got {len(rows)} rows, expected >= {min_expected}"
    )


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_raw_country_schema(country: str) -> None:
    p = RAW_DIR / f"{country}.jsonl"
    with p.open() as fh:
        for ln, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            assert set(r.keys()) >= {"rank", "name", "population"}, (
                f"{country} line {ln} missing keys: {set(r.keys())}"
            )
            assert isinstance(r["rank"], int) and r["rank"] > 0
            assert isinstance(r["population"], int) and r["population"] > 0
            assert isinstance(r["name"], str) and r["name"]


def test_results_json_exists_and_parses() -> None:
    assert RESULTS.is_file(), f"missing {RESULTS}; run run_validation.py"
    d = json.loads(RESULTS.read_text())
    assert "countries" in d and "overall_verdict" in d
    assert set(d["countries"].keys()) == set(EXPECTED_COUNTRIES)


# ---- Layer 2: schema (KB additions) ----


def _load_kb(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_kb_file_exists() -> None:
    assert KB_FILE.is_file(), f"missing {KB_FILE}"


def test_kb_size() -> None:
    rows = _load_kb(KB_FILE)
    assert 5 <= len(rows) <= 20, (
        f"KB file should have 5-20 entries (task spec), got {len(rows)}"
    )


def test_kb_schema() -> None:
    REQUIRED = {"id", "name", "domain", "type_id", "description"}
    rows = _load_kb(KB_FILE)
    for r in rows:
        assert set(r.keys()) >= REQUIRED, f"row {r.get('id')} missing keys"
        assert r["id"].startswith("cze-"), f"id must start with cze-: {r['id']}"
        assert r["domain"] == "城市科学", f"domain mismatch: {r['domain']}"
        assert isinstance(r["type_id"], str) and len(r["type_id"]) == 2
        assert int(r["type_id"]) >= 1 and int(r["type_id"]) <= 84
        assert len(r["description"]) >= 100, (
            f"description too short for {r['id']}: {len(r['description'])} chars"
        )


def test_kb_ids_unique() -> None:
    rows = _load_kb(KB_FILE)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), f"duplicate ids in KB: {ids}"


def test_kb_no_overlap_with_urban_x1() -> None:
    """The X1 Urban agent already added definitional entries at urb-011..015.

    Our empirical entries (cze-*) must not overlap by id and must not duplicate
    the textual content (which would be redundant).
    """
    cze_rows = _load_kb(KB_FILE)
    if not KB_URBAN.is_file():
        pytest.skip(f"X1 urban file {KB_URBAN} not present; nothing to compare")
    urb_rows = _load_kb(KB_URBAN)
    cze_ids = {r["id"] for r in cze_rows}
    urb_ids = {r["id"] for r in urb_rows}
    assert cze_ids.isdisjoint(urb_ids), (
        f"id collision with X1 Urban entries: {cze_ids & urb_ids}"
    )
    # textual non-duplication: names should differ
    cze_names = {r["name"] for r in cze_rows}
    urb_names = {r["name"] for r in urb_rows}
    assert cze_names.isdisjoint(urb_names), (
        f"name collision with X1 Urban entries: {cze_names & urb_names}"
    )


# ---- Layer 3: sanity on s ----


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_zipf_s_in_sanity_band(country: str) -> None:
    """Fitted Zipf s must be in [0.5, 2.0] — outside this, something is wrong.

    Soo (2005) cross-country meta has s ∈ [0.78, 1.88]; we widen by 0.3 to give
    pre-registered slack and catch only catastrophic failures (e.g. data load
    bugs that flip the sign of the slope).
    """
    d = json.loads(RESULTS.read_text())
    f = d["countries"][country]
    s = f["s_zipf"]
    assert 0.5 <= s <= 2.0, (
        f"{country}: s = {s:.3f} outside [0.5, 2.0] sanity band — "
        f"likely data pipeline error or fit divergence"
    )


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_clauset_alpha_in_sanity_band(country: str) -> None:
    """Clauset α must be in [1.5, 3.5] — generic empirical preferential-attachment band.

    Newman 2005 survey: α ∈ [1.8, 3.5] for canonical PA systems; we extend slack to 1.5.
    """
    d = json.loads(RESULTS.read_text())
    f = d["countries"][country]
    alpha = f["alpha"]
    assert 1.5 <= alpha <= 3.5, (
        f"{country}: alpha = {alpha:.3f} outside [1.5, 3.5] sanity band"
    )


@pytest.mark.parametrize("country", EXPECTED_COUNTRIES)
def test_r2_above_threshold(country: str) -> None:
    """log-log fit R² must be high — Zipf functional form is famous for being clean."""
    d = json.loads(RESULTS.read_text())
    f = d["countries"][country]
    assert f["r2"] >= 0.85, (
        f"{country}: R² = {f['r2']:.3f} < 0.85 — log-log linearity broken"
    )


def test_overall_verdict_present() -> None:
    d = json.loads(RESULTS.read_text())
    assert d["overall_verdict"] in {"PASS", "PASS (with caveats)", "INCONCLUSIVE", "FAIL"}, (
        f"unexpected overall_verdict: {d['overall_verdict']}"
    )


def test_anchor_block_complete() -> None:
    """Cross-system anchor block must include language Zipf + firm size + wealth."""
    d = json.loads(RESULTS.read_text())
    anchors = d["cross_system_anchors"]
    expected = {"language_zipf_english", "firm_size_us", "wealth_us_top"}
    assert expected.issubset(anchors.keys()), (
        f"missing cross-system anchors: {expected - set(anchors.keys())}"
    )
