"""Reject-aware trap-flag filter.

Implements the keyword/pattern-based detector for the 4 prototype traps
described in C4 paper §4.3, plus an `other` escape valve. The detector
runs on a Verdict's rationale (and optionally on a CandidateClass
description) to ADD trap_flags the LLM forgot to set.

This is a deterministic, defensive layer — `Critic` always trusts the LLM's
self-declared trap_flags but augments them with detected patterns so that a
rationale mentioning "central limit theorem" without setting the
`mechanism_vs_limit_theorem` flag still surfaces the trap downstream.

Patterns are intentionally conservative; false-positive flagging just adds
extra signal in `EnsembleResult.trap_flags_union`, never overrides verdict.
"""
from __future__ import annotations

import re
from typing import Iterable

from .schemas import CandidateClass, TrapFlag

# Lower-case substring patterns. Match runs on lower-cased text.
# Keep patterns tight — favor specificity over recall to avoid false flags.
TRAP_PATTERNS: dict[TrapFlag, list[str]] = {
    "mechanism_vs_limit_theorem": [
        "limit theorem",
        "limit-theorem",
        "central limit",
        "clt ",
        " clt.",
        " clt,",
        "gev family",
        "extreme value",
        "hopf normal form",
        "hopf bifurcation normal form",
        "delay-differential normal form",
        "generic normal form",
    ],
    "mathematical_framework_masquerading": [
        "masquerading",
        "mathematical framework",
        "generic framework",
        "copula framework",
        "decomposition framework",
        "applicable to many mechanisms",
        "framework, not a universality",
        "framework but not a universality",
        "not a dynamical universality",
    ],
    "surface_similarity_from_heavy_tails": [
        "surface similarity",
        "surface-similarity",
        "heavy tail",
        "heavy-tail",
        "scale-free degree",
        "phenomenological signature",
        "phenomenological observable",
        "only shared property",
    ],
    "mechanism_dispersion_monolith": [
        "monolith",
        "incompatible mechanism",
        "mechanism dispersion",
        "lumps together",
        "category error",
        "different bistability",
        "different critical mechanisms",
        "different critical mechanism",
    ],
}


def detect_traps(text: str) -> list[TrapFlag]:
    """Scan free-text (rationale, notes, ...) and return matched trap flags.

    Returns a list with stable order (matches TRAP_PATTERNS dict order) and
    no duplicates.
    """
    if not text:
        return []
    low = text.lower()
    flags: list[TrapFlag] = []
    for flag, patterns in TRAP_PATTERNS.items():
        for pat in patterns:
            if pat in low:
                flags.append(flag)
                break
    return flags


# Whole-word fallback for ambiguous short strings ("CLT") — used as a
# second pass to reduce noise on inputs that happen to contain substrings.
_WORD_BOUNDARY_PATTERNS: dict[TrapFlag, list[str]] = {
    "mechanism_vs_limit_theorem": [r"\bclt\b", r"\bgev\b"],
}


def detect_traps_strict(text: str) -> list[TrapFlag]:
    """Stricter variant that uses regex word boundaries for short tokens.

    Catches "CLT" and "GEV" as standalone words while ignoring them inside
    longer identifiers like "cluster" or "register".
    """
    if not text:
        return []
    base = detect_traps(text)
    low = text.lower()
    extras: list[TrapFlag] = []
    for flag, patterns in _WORD_BOUNDARY_PATTERNS.items():
        if flag in base:
            continue
        for pat in patterns:
            if re.search(pat, low):
                extras.append(flag)
                break
    # preserve dict ordering of base, then extras
    return base + [f for f in extras if f not in base]


def merge_trap_flags(declared: Iterable[TrapFlag], detected: Iterable[TrapFlag]) -> list[TrapFlag]:
    """Combine LLM-declared flags with detector-augmented flags (dedup, stable order)."""
    out: list[TrapFlag] = []
    seen: set[str] = set()
    for src in (declared, detected):
        for f in src:
            if f and f not in seen:
                seen.add(f)
                out.append(f)
    return out


def candidate_signature_text(candidate: CandidateClass) -> str:
    """Concatenate the candidate's user-visible fields into one text blob.

    Used so the filter can run on the candidate description itself (not just
    on a verdict rationale) — useful for pre-filtering before LLM calls.
    """
    parts: list[str] = [
        candidate.class_id,
        candidate.name,
        candidate.hub,
        " ".join(candidate.shared_equations),
        " ".join(candidate.key_invariants),
        " ".join(candidate.domains),
        " ".join(candidate.members),
        " ".join(candidate.negative_examples),
        candidate.notes,
        candidate.prior_rationale or "",
    ]
    return "\n".join(p for p in parts if p)
