"""Tests for X3 COVID-19 Omori-decay validation (2026-05-24).

Source: docs/coverage/expansion-candidates-2026-05-24.md Top-2 L7a.

Three layers per CLAUDE.md "功能验收三层":

1. **smoke**  — fetcher and validator scripts are importable, results.json
   exists and parses. No remote network calls.
2. **schema** — results.json conforms to the documented per-wave +
   aggregate layout; KB-additions JSONL is well-formed with the right
   namespace and field set.
3. **sanity** — pre-Omicron median p is INSIDE the predicted [0.5, 1.5]
   band (this is the load-bearing scientific claim of the X3 entry; if
   it ever drifts out we want CI to scream). Overall median sits within
   the extended [0.5, 2.0] band. ≥10 of the 14 detected waves get
   trusted fits.

Coverage marker: smoke / schema / sanity (per pytest.ini markers).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "covid-omori"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADDITIONS = REPO_ROOT / "data" / "kb-additions-2026-05-24-covid-omori.jsonl"
SESSION_REPORT = REPO_ROOT / "docs" / "sessions" / "X3-covid-omori-validation-2026-05-24.md"
RAW_DIR = VAL_DIR / "raw"

COUNTRIES = ["us", "uk", "india", "brazil", "italy"]
PREDICTED_BAND = (0.5, 1.5)
EXTENDED_BAND = (0.5, 2.0)


# ----------------------------- fixtures ---------------------------------- #


@pytest.fixture(scope="module")
def results() -> dict:
    if not RESULTS.exists():
        pytest.skip(
            f"missing {RESULTS}; run "
            "`python3 v4/validation/covid-omori/fetch_jhu.py && "
            "python3 v4/validation/covid-omori/run_validation.py` first"
        )
    return json.loads(RESULTS.read_text())


@pytest.fixture(scope="module")
def kb_rows() -> list[dict]:
    if not KB_ADDITIONS.exists():
        pytest.skip(f"missing {KB_ADDITIONS}")
    rows: list[dict] = []
    with KB_ADDITIONS.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# ------------------------------- smoke ----------------------------------- #


@pytest.mark.sanity
class TestCovidOmoriSmoke:
    """Files exist, scripts are importable, JSONs parse."""

    def test_run_validation_script_exists(self):
        path = VAL_DIR / "run_validation.py"
        assert path.is_file(), f"missing {path}"

    def test_fetch_script_exists(self):
        path = VAL_DIR / "fetch_jhu.py"
        assert path.is_file(), f"missing {path}"

    def test_results_json_exists(self, results):
        assert isinstance(results, dict)

    def test_verdict_md_exists(self):
        assert VERDICT.is_file(), f"missing {VERDICT}"
        content = VERDICT.read_text()
        assert "COVID-19" in content
        assert "Omori" in content

    def test_session_report_exists(self):
        assert SESSION_REPORT.is_file(), f"missing {SESSION_REPORT}"

    def test_kb_additions_exists(self, kb_rows):
        assert len(kb_rows) > 0


# ------------------------------- schema ---------------------------------- #


@pytest.mark.sanity
class TestCovidOmoriSchema:
    """results.json + KB-additions JSONL conform to documented layout."""

    REQUIRED_TOP_KEYS = {
        "domain",
        "predicted_class",
        "data_window",
        "countries_analysed",
        "fit_window_days",
        "peak_detection",
        "quality_gate",
        "c_grid_days",
        "countries",
        "aggregate",
        "method_refs",
    }

    REQUIRED_AGG_KEYS = {
        "verdict",
        "median_p",
        "q25_p",
        "q75_p",
        "iqr_p",
        "n_waves_total",
        "n_waves_in_band",
        "frac_in_band",
        "predicted_band",
        "pre_omicron_median_p",
        "omicron_era_median_p",
        "per_country_p_mean",
    }

    REQUIRED_WAVE_KEYS = {
        "peak_date",
        "peak_idx",
        "peak_value",
        "p",
        "p_sigma",
        "c_days",
        "logK",
        "R2",
        "n_points",
        "t_range_days",
        "error",
    }

    def test_top_level_keys(self, results):
        missing = self.REQUIRED_TOP_KEYS - set(results.keys())
        assert not missing, f"top-level missing keys: {missing}"

    def test_aggregate_keys(self, results):
        missing = self.REQUIRED_AGG_KEYS - set(results["aggregate"].keys())
        assert not missing, f"aggregate missing keys: {missing}"

    def test_predicted_class(self, results):
        assert "soc_threshold_cascade" in results["predicted_class"]

    def test_predicted_band(self, results):
        band = results["aggregate"]["predicted_band"]
        assert tuple(band) == PREDICTED_BAND

    def test_all_five_countries_present(self, results):
        countries = {c["country"] for c in results["countries"]}
        missing = set(COUNTRIES) - countries
        assert not missing, f"missing countries: {missing}"

    def test_country_record_shape(self, results):
        for c in results["countries"]:
            assert "country" in c
            assert "waves" in c
            assert isinstance(c["waves"], list)
            for w in c["waves"]:
                missing = self.REQUIRED_WAVE_KEYS - set(w.keys())
                assert not missing, (
                    f"{c['country']} wave {w.get('peak_date')} missing: {missing}"
                )

    def test_kb_additions_count_in_target_range(self, kb_rows):
        assert 15 <= len(kb_rows) <= 20, (
            f"task brief mandates 15-20 KB entries; got {len(kb_rows)}"
        )

    def test_kb_additions_ids_unique_and_namespaced(self, kb_rows):
        ids = [r["id"] for r in kb_rows]
        assert len(set(ids)) == len(ids), "duplicate ids"
        for i in ids:
            assert i.startswith("covid-x3-"), f"id outside covid-x3 namespace: {i}"

    def test_kb_additions_required_fields(self, kb_rows):
        for r in kb_rows:
            for k in ("id", "name", "domain", "type_id", "description"):
                assert r.get(k), f"missing/empty {k} on {r.get('id')}"
            assert r["domain"] == "流行病学", (
                f"unexpected domain on {r['id']}: {r['domain']}"
            )

    def test_kb_additions_description_min_length(self, kb_rows):
        # Each entry must carry a concrete quantitative observation; >100 chars.
        for r in kb_rows:
            assert len(r["description"]) >= 100, (
                f"{r['id']} description too short ({len(r['description'])} chars)"
            )

    def test_kb_additions_type_id_diversity(self, kb_rows):
        # X3 spec: span >= 6 distinct type_ids to cover epidemic / SOC /
        # variant biology / public health / measurement bias.
        tids = {r["type_id"] for r in kb_rows}
        assert len(tids) >= 6, (
            f"type_id diversity too low ({len(tids)}): {sorted(tids)}"
        )


# ------------------------------- sanity ---------------------------------- #


@pytest.mark.sanity
class TestCovidOmoriSanity:
    """Load-bearing scientific claims of the X3 entry."""

    def test_at_least_10_trusted_fits(self, results):
        n = results["aggregate"]["n_waves_total"]
        assert n >= 10, (
            f"need >=10 trusted (R²>=0.5) fits across 5 countries; got {n}"
        )

    def test_overall_median_in_extended_band(self, results):
        m = results["aggregate"]["median_p"]
        lo, hi = EXTENDED_BAND
        assert lo <= m <= hi, (
            f"overall median p={m} outside extended band {EXTENDED_BAND}"
        )

    def test_pre_omicron_median_in_predicted_band(self, results):
        """Pre-Omicron pre-Dec-2021 waves recover canonical Omori p ≈ 1.

        This is the headline scientific claim of the X3 validation. If the
        pre-Omicron sub-population's median p drifts outside [0.5, 1.5],
        either the data has changed or the wave-detection / fit pipeline
        has regressed — both warrant investigation, hence a hard assertion.
        """
        pm = results["aggregate"]["pre_omicron_median_p"]
        assert pm is not None, "pre-Omicron median p missing"
        lo, hi = PREDICTED_BAND
        assert lo <= pm <= hi, (
            f"pre-Omicron median p={pm:.3f} outside predicted band "
            f"{PREDICTED_BAND}; expected canonical Omori"
        )

    def test_pre_omicron_close_to_earthquake_omori(self, results):
        """Pre-Omicron p should be within 0.5 of earthquake Omori p≈0.94."""
        pm = results["aggregate"]["pre_omicron_median_p"]
        assert pm is not None
        assert abs(pm - 0.94) < 0.5, (
            f"pre-Omicron p={pm:.3f} departs >0.5 from earthquake Omori 0.94"
        )

    def test_omicron_era_median_higher_than_pre(self, results):
        """Omicron-era median p should be > pre-Omicron, by ≥0.3.

        This validates the stratification — if the two strata have
        statistically indistinguishable p, the pre/post split is not
        meaningful and we should report only the overall median.
        """
        pm = results["aggregate"]["pre_omicron_median_p"]
        om = results["aggregate"]["omicron_era_median_p"]
        assert pm is not None and om is not None
        assert om - pm >= 0.3, (
            f"Omicron-era median p ({om:.3f}) not meaningfully larger than "
            f"pre-Omicron ({pm:.3f}); stratification questionable"
        )

    def test_verdict_is_partial_or_confirmed(self, results):
        """Either verdict is acceptable given the bimodal distribution.

        Both CONFIRMED and PARTIAL count as 'isomorphism survives'; only
        DEVIATING / INCONCLUSIVE are failures.
        """
        v = results["aggregate"]["verdict"]
        assert v in ("CONFIRMED", "PARTIAL"), (
            f"verdict {v} indicates isomorphism failure"
        )

    def test_each_country_has_at_least_one_wave(self, results):
        for c in results["countries"]:
            assert c["n_waves_detected"] >= 1, (
                f"{c['country']}: no major waves detected — peak-finder broken?"
            )

    def test_kb_additions_mention_key_concepts(self, kb_rows):
        """The 18-entry KB block must cover the load-bearing concepts."""
        blob = "\n".join(r["name"] + " " + r["description"] for r in kb_rows).lower()
        # English+Chinese keyword set; need each represented at least once
        required_keywords = [
            "omori",
            "soc",
            "omicron",
            "sars",
            "r0",  # basic reproduction number
            "群体免疫",  # herd immunity
            "超传播",  # super-spreading
        ]
        missing = [k for k in required_keywords if k.lower() not in blob]
        assert not missing, f"KB additions missing keywords: {missing}"
