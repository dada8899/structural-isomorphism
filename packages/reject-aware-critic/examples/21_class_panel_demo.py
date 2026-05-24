"""Simplified demo: run B3 ensemble over a 3-class slice of the C4 paper panel.

This demo uses the offline `mock` vendor so it runs in CI with no API keys.
To run against real LLMs, replace the Critic vendor= with 'deepseek' (or
'anthropic'/'kimi'/'glm' via OpenRouter) and set the corresponding env var.

The 3 candidates here are picked from the C4 paper §4.3 four prototype
demotions to illustrate the reject-aware filter:

  - delay_differential_debt          (mechanism vs limit theorem)
  - tail_copula_contagion            (mathematical framework masquerading)
  - hysteresis_preisach_monolith     (mechanism dispersion monolith)

Run:
    python examples/21_class_panel_demo.py
"""
from __future__ import annotations

import json

from reject_aware_critic import (
    CandidateClass,
    CriticEnsemble,
    register_mock_responder,
)


CANDIDATES = [
    CandidateClass(
        class_id="delay_differential_debt",
        name="Delay Differential Debt Dynamics",
        hub="Hopf bifurcation in delayed feedback systems",
        shared_equations=["dx/dt = f(x(t - tau))"],
        key_invariants=["delay tau", "Hopf frequency at bifurcation"],
        domains=["macroeconomics", "neuroscience", "ecology"],
        members=[
            "sovereign debt cycle",
            "delayed neural oscillation",
            "predator-prey lag dynamics",
        ],
        negative_examples=["instantaneous feedback systems"],
        notes="Candidate built on the generic DDE normal form.",
        prior_verdict="KEEP",
        prior_confidence=0.7,
        prior_rationale="B1 voted KEEP on shared equation form.",
    ),
    CandidateClass(
        class_id="tail_copula_contagion",
        name="Tail Copula Contagion",
        hub="Joint tail dependence in coupled risk systems",
        shared_equations=["C(u,v) = P(F_X<=u, F_Y<=v)"],
        key_invariants=["tail dependence coefficient lambda_U"],
        domains=["finance", "epidemiology", "ecology"],
        members=[
            "DeFi liquidation cascade",
            "epidemic super-spreader event",
            "ecological collapse cascade",
        ],
        negative_examples=["independent shock systems"],
        notes="Tail copula is a statistical coupling, applicable to many mechanisms.",
        prior_verdict="KEEP",
        prior_confidence=0.6,
    ),
    CandidateClass(
        class_id="hysteresis_preisach_monolith",
        name="Preisach Hysteresis (monolithic)",
        hub="Hysteron-decomposition bistability",
        shared_equations=["P(H) = sum w_i hysteron_i(H)"],
        key_invariants=["switching threshold distribution"],
        domains=["materials", "traffic", "ecology"],
        members=[
            "magnetic hysteresis",
            "traffic first-order transition",
            "ecological regime shift",
        ],
        notes="Lumps together magnetic, traffic, and ecological mechanisms.",
        prior_verdict="SPLIT",
    ),
]


def _register_demo_responders() -> None:
    """Register canned mock responses keyed by class_id."""
    canned = {
        "delay_differential_debt": {
            "decision": "REJECT",
            "confidence": 0.88,
            "rationale": (
                "The DDE normal form is a generic Hopf normal form, "
                "not a critical-mechanism universality class. This is a "
                "mechanism vs limit theorem confusion."
            ),
            "trap_flags": ["mechanism_vs_limit_theorem"],
        },
        "tail_copula_contagion": {
            "decision": "REJECT",
            "confidence": 0.82,
            "rationale": (
                "Tail copula is a mathematical framework masquerading as a "
                "universality class — applicable to many incompatible mechanisms."
            ),
            "trap_flags": ["mathematical_framework_masquerading"],
        },
        "hysteresis_preisach_monolith": {
            "decision": "REJECT",
            "confidence": 0.75,
            "rationale": (
                "The class lumps together incompatible bistability mechanisms — "
                "category error and mechanism dispersion monolith."
            ),
            "trap_flags": ["mechanism_dispersion_monolith"],
        },
    }

    def _responder(model, messages, temperature, max_tokens):
        # Find the class_id in the user message (last message).
        user_content = messages[-1].get("content", "")
        for cid, payload in canned.items():
            if cid in user_content:
                return json.dumps(payload), {
                    "prompt_tokens": 800,
                    "completion_tokens": 120,
                }
        # default fallback
        return (
            json.dumps({"decision": "UNCLEAR", "confidence": 0.5, "rationale": "n/a"}),
            {"prompt_tokens": 800, "completion_tokens": 50},
        )
    register_mock_responder("demo", _responder)


def main() -> int:
    _register_demo_responders()
    ensemble = CriticEnsemble.b3(vendor="mock", model="mock-model",
                                 mock_responder="demo")
    print(f"Running B3 ensemble ({len(ensemble.critics)} critics) "
          f"on {len(CANDIDATES)} candidates...\n")
    for cand in CANDIDATES:
        result = ensemble.judge(cand)
        print(f"=== {cand.class_id} ===")
        print(f"  consensus            : {result.consensus}")
        print(f"  consensus_confidence : {result.consensus_confidence:.2f}")
        print(f"  disagreement_signal  : {result.disagreement_signal:.2f}")
        print(f"  trap_flags_union     : {result.trap_flags_union}")
        print(f"  total_cost_usd       : ${result.total_cost_usd:.4f}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
