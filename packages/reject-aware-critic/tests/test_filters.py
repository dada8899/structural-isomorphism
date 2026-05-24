"""Tests for reject-aware trap-flag filter (filters.py).

One case per prototype trap from C4 paper §4.3, plus combination cases.
"""
from __future__ import annotations

from reject_aware_critic import (
    CandidateClass,
    candidate_signature_text,
    detect_traps,
    detect_traps_strict,
    merge_trap_flags,
)


class TestDetectTraps:
    def test_mechanism_vs_limit_theorem(self):
        text = "This is just a central limit theorem effect, not a real universality class."
        flags = detect_traps(text)
        assert "mechanism_vs_limit_theorem" in flags

    def test_mathematical_framework_masquerading(self):
        text = (
            "The candidate is a mathematical framework masquerading as a class; "
            "the copula framework applies to many mechanisms."
        )
        flags = detect_traps(text)
        assert "mathematical_framework_masquerading" in flags

    def test_surface_similarity_from_heavy_tails(self):
        text = "These systems only share a heavy-tail; pure surface similarity."
        flags = detect_traps(text)
        assert "surface_similarity_from_heavy_tails" in flags

    def test_mechanism_dispersion_monolith(self):
        text = "The Preisach monolith lumps together incompatible mechanisms — a category error."
        flags = detect_traps(text)
        assert "mechanism_dispersion_monolith" in flags

    def test_no_match_returns_empty(self):
        flags = detect_traps("A perfectly fine universality class with shared exponents.")
        assert flags == []

    def test_empty_input(self):
        assert detect_traps("") == []
        assert detect_traps(None) == []  # type: ignore[arg-type]

    def test_multiple_traps_in_one_rationale(self):
        text = (
            "Limit theorem confusion AND heavy-tail surface similarity — "
            "this is a mathematical framework masquerading as a class."
        )
        flags = detect_traps(text)
        assert "mechanism_vs_limit_theorem" in flags
        assert "surface_similarity_from_heavy_tails" in flags
        assert "mathematical_framework_masquerading" in flags

    def test_no_duplicate_per_flag(self):
        text = "limit theorem limit-theorem limit theorem"
        flags = detect_traps(text)
        assert flags.count("mechanism_vs_limit_theorem") == 1


class TestDetectTrapsStrict:
    def test_clt_word_boundary(self):
        # "CLT" as a standalone word triggers
        flags = detect_traps_strict("This is a CLT artifact.")
        assert "mechanism_vs_limit_theorem" in flags

    def test_clt_not_inside_longer_word(self):
        # "cluster" / "occult" should not trigger CLT word-boundary match
        flags = detect_traps_strict("The cluster occult registers fine.")
        assert flags == []

    def test_gev_standalone(self):
        flags = detect_traps_strict("GEV asymptotics suggest a limit theorem.")
        # base detect_traps already picks 'limit theorem'; GEV also fires
        assert "mechanism_vs_limit_theorem" in flags


class TestMergeTrapFlags:
    def test_declared_only(self):
        merged = merge_trap_flags(["mechanism_vs_limit_theorem"], [])
        assert merged == ["mechanism_vs_limit_theorem"]

    def test_detected_only(self):
        merged = merge_trap_flags([], ["other"])
        assert merged == ["other"]

    def test_dedup(self):
        merged = merge_trap_flags(
            ["mechanism_vs_limit_theorem"],
            ["mechanism_vs_limit_theorem", "other"],
        )
        assert merged == ["mechanism_vs_limit_theorem", "other"]


class TestCandidateSignatureText:
    def test_basic(self):
        c = CandidateClass(
            class_id="test_class",
            name="Test Class",
            hub="hub phenomenon",
            shared_equations=["x = y"],
            members=["a", "b"],
        )
        sig = candidate_signature_text(c)
        assert "test_class" in sig
        assert "Test Class" in sig
        assert "hub phenomenon" in sig
        assert "x = y" in sig
        assert "a" in sig

    def test_runs_through_detect(self):
        c = CandidateClass(
            class_id="bad_class",
            name="Bad",
            notes="This is a limit theorem masquerading as a universality class.",
        )
        sig = candidate_signature_text(c)
        flags = detect_traps(sig)
        assert "mechanism_vs_limit_theorem" in flags
