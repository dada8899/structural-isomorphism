"""reject-aware-critic — Multi-vendor LLM critic ensemble for cross-domain universality candidate review.

Public API:

    from reject_aware_critic import (
        Critic, CriticEnsemble,
        CandidateClass, Verdict, EnsembleResult,
        CostBudgetError,
    )

    candidate = CandidateClass(
        class_id="my_class",
        name="My proposed class",
        shared_equations=["dx/dt = f(x)"],
        domains=["physics", "finance"],
        members=["earthquake", "market crash"],
    )

    # single critic (one vendor, one decoding)
    critic = Critic(vendor="deepseek", model="deepseek-chat", temperature=0.0)
    verdict = critic.judge(candidate)
    print(verdict.decision, verdict.trap_flags)

    # B3 ensemble — 3 decodings on 1 vendor
    ensemble = CriticEnsemble.b3(vendor="deepseek")
    result = ensemble.judge(candidate)
    print(result.consensus, result.disagreement_signal)

    # B4 ensemble — 1 critic per vendor (cross-architecture)
    ensemble = CriticEnsemble.b4(vendors=["anthropic", "deepseek", "kimi", "glm"])
    result = ensemble.judge(candidate)

See: https://github.com/dada8899/structural-isomorphism/blob/main/paper/c4-reject-aware-pipeline-2026-05-13.md
"""
from .critic import CostBudgetError, Critic
from .ensemble import DEFAULT_MODELS, CriticEnsemble
from .filters import (
    TRAP_PATTERNS,
    candidate_signature_text,
    detect_traps,
    detect_traps_strict,
    merge_trap_flags,
)
from .prompts import DEFAULT_SYSTEM_PROMPT, SYSTEM_PROMPTS, build_user_prompt
from .schemas import (
    CandidateClass,
    EnsembleResult,
    TrapFlag,
    Verdict,
    VerdictLabel,
)
from ._vendors import (
    VENDORS,
    VendorConfig,
    get_vendor,
    register_mock_responder,
)

__version__ = "0.1.0"

__all__ = [
    # primary API
    "Critic",
    "CriticEnsemble",
    "CandidateClass",
    "Verdict",
    "EnsembleResult",
    "CostBudgetError",
    # schemas / labels
    "VerdictLabel",
    "TrapFlag",
    # prompt utilities
    "SYSTEM_PROMPTS",
    "DEFAULT_SYSTEM_PROMPT",
    "build_user_prompt",
    # filter utilities
    "TRAP_PATTERNS",
    "detect_traps",
    "detect_traps_strict",
    "merge_trap_flags",
    "candidate_signature_text",
    # vendor utilities
    "VENDORS",
    "VendorConfig",
    "get_vendor",
    "register_mock_responder",
    "DEFAULT_MODELS",
    "__version__",
]
