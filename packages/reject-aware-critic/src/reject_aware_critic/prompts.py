"""Prompt templates for reject-aware critic verdicts.

Two layers:

  SYSTEM_PROMPTS — vendor-agnostic system messages that anchor the critic
                   to the Clauset-Stumpf-Porter rejection standard, with
                   three reviewer personas (rigorous / lighter / creative
                   dissenter) — direct lift from C4 paper §3 + V4 B3 script.

  build_user_prompt(candidate) — render a CandidateClass into the user
                   message. Output schema is strict JSON; downstream
                   `_parse_verdict` is tolerant of markdown fences and a
                   handful of legacy field-name variants.

The verdict prompt deliberately keeps 4 categories (KEEP/REJECT/SPLIT/MERGE)
plus UNCLEAR so plurality consensus can absorb single-reviewer noise while
preserving SPLIT/MERGE structural actions (cf. C4 §4.3 reject-aware filter).
"""
from __future__ import annotations

from .schemas import CandidateClass

# Three vendor-agnostic reviewer personas. The C4 B3 ensemble uses all three
# on a single vendor (within-vendor multi-decoding). B4 reuses these across
# vendors. Library users can pick one or all.
SYSTEM_PROMPTS: dict[str, str] = {
    "rigorous": (
        "You are a rigorous universality-class critic for cross-domain "
        "dynamical systems. Apply Clauset 2009 + Stumpf-Porter 2012 "
        "standards: shared equation form + shared scaling exponents + "
        "shared critical mechanism. Reject limit-theorem confusions "
        "(CLT/GEV families are not universality classes in the "
        "dynamical-systems sense). Reject mathematical-framework "
        "masquerading (a generic normal form / copula / decomposition is "
        "not a universality class). Output JSON only, no commentary."
    ),
    "lighter": (
        "You are a rigorous universality-class critic. Apply Clauset 2009 "
        "+ Stumpf-Porter 2012 standards: shared equation form + shared "
        "scaling exponents + shared critical mechanism. Output JSON only."
    ),
    "creative_dissenter": (
        "You are a creative dissenter on universality-class taxonomy. "
        "Your job is to surface (a) missed cross-domain analogies that a "
        "rigorous reviewer might over-reject, AND (b) surface-similarity "
        "traps where superficially similar phenomena have incompatible "
        "underlying mechanisms. Be willing to disagree with conventional "
        "rigor when the evidence supports a wider or narrower class. "
        "Output JSON only."
    ),
}

DEFAULT_SYSTEM_PROMPT = SYSTEM_PROMPTS["rigorous"]


# User prompt template. Mirrors the structure from V4 `b3_ensemble.py`
# PROMPT_TEMPLATE but does not depend on any V4-internal YAML layout.
USER_PROMPT_TEMPLATE = """Review this candidate universality class for whether it forms a valid cross-domain universality class in the dynamical-systems sense (shared equation form + shared scaling exponents + shared critical mechanism).

Class id: {class_id}
Display name: {name}
Hub phenomenon: {hub}
Domains: {domains}

Shared equations / normal forms:
{shared_equations_block}

Key invariants:
{invariants_block}

Positive examples (members claimed by upstream curator):
{members_block}

Negative examples / boundary cases:
{negative_examples_block}

Curator notes:
{notes}

Prior verdict (if any): {prior_verdict} (confidence: {prior_confidence})
Prior rationale: {prior_rationale}

Output JSON only, in this exact schema:
{{
  "class_id": "{class_id}",
  "decision": "KEEP" | "REJECT" | "SPLIT" | "MERGE" | "UNCLEAR",
  "confidence": <float 0.0-1.0>,
  "rationale": "<2-4 sentences; cite mechanism + exponent + equation form>",
  "trap_flags": [<zero or more of "mechanism_vs_limit_theorem", "mathematical_framework_masquerading", "surface_similarity_from_heavy_tails", "mechanism_dispersion_monolith", "other">]
}}

Decision guide (apply strictly):
- KEEP: shared mechanism + shared exponents (or shared dynamic equation form) supported by >=3 positive members across genuinely distinct domains.
- REJECT: limit-theorem-only convergence (CLT/GEV/etc.); pure surface similarity; OR members drawn from incompatible mechanisms whose only shared property is a phenomenological observable (e.g. heavy tail).
- SPLIT: real class but heterogeneous in mechanism or exponent band; should be split into 2+ tighter sub-classes.
- MERGE: near-duplicate of another standard class; should be merged.
- UNCLEAR: cannot determine from this brief; needs more empirical data.

Trap flags (set when applicable, in addition to a REJECT or SPLIT verdict):
- "mechanism_vs_limit_theorem": class confuses a generic limit theorem (CLT/GEV/Hopf normal form) for a dynamical universality class.
- "mathematical_framework_masquerading": class is built on a generic mathematical framework (copula, normal form, decomposition) applicable to many incompatible mechanisms.
- "surface_similarity_from_heavy_tails": class members share only phenomenological signatures (heavy tail, scale-free degree distribution) without shared dynamics.
- "mechanism_dispersion_monolith": claimed class lumps together systems whose bistability/criticality mechanisms are mathematically incompatible.
- "other": novel trap pattern not covered above; describe briefly in rationale.

Output ONLY the JSON object, no preamble or commentary outside the JSON.
"""


def _bulleted(items: list[str], fallback: str = "(none)") -> str:
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items:
        return fallback
    return "\n".join(f"- {x}" for x in items)


def build_user_prompt(candidate: CandidateClass) -> str:
    """Render a CandidateClass into the user-message prompt body."""
    return USER_PROMPT_TEMPLATE.format(
        class_id=candidate.class_id,
        name=(candidate.name or candidate.class_id)[:200],
        hub=(candidate.hub or "(unspecified)")[:400],
        domains=", ".join(candidate.domains) if candidate.domains else "(unspecified)",
        shared_equations_block=_bulleted(candidate.shared_equations)[:1500],
        invariants_block=_bulleted(candidate.key_invariants)[:1200],
        members_block=_bulleted(candidate.members[:12], fallback="(none)")[:1500],
        negative_examples_block=_bulleted(candidate.negative_examples[:8], fallback="(none)")[:1000],
        notes=(candidate.notes or "(none)")[:500],
        prior_verdict=candidate.prior_verdict or "(none)",
        prior_confidence=(
            f"{candidate.prior_confidence:.2f}"
            if candidate.prior_confidence is not None
            else "n/a"
        ),
        prior_rationale=(candidate.prior_rationale or "(none)")[:600],
    )
