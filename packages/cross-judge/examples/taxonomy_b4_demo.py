#!/usr/bin/env python3
"""Reproduce a small slice of B4 (universality-class ensemble review) via cross-judge.

This demo mirrors the v4/scripts/b4_deepseek_ensemble.py pipeline of the
structural-isomorphism project, but uses cross-judge as the thin wrapper
instead of hand-rolled urllib calls.

Pipeline parity points:
  - 3 DeepSeek reviewers (pro T=0.0, flash T=0.0, pro T=0.7 chat-baseline)
  - Same system prompts (rigorous / rigorous-light / chat-baseline)
  - Same user prompt template (truncated for demo)
  - Same KEEP/REJECT/UNCLEAR/SPLIT/MERGE vocabulary
  - majority consensus aggregation

Run:
    python examples/taxonomy_b4_demo.py --mock        # offline demo
    python examples/taxonomy_b4_demo.py               # live, requires DEEPSEEK_API_KEY
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from cross_judge import JudgePanel, Reviewer


# Verbatim from v4/scripts/b4_deepseek_ensemble.py
SYS_RIGOROUS = (
    "You are a rigorous universality-class critic for cross-domain "
    "dynamical systems. Apply Clauset 2009 + Stumpf-Porter 2012 "
    "standards: shared equation form + shared scaling exponents + "
    "shared critical mechanism. Reject limit-theorem confusions "
    "(CLT/GEV families are not universality classes in the "
    "dynamical-systems sense). Output JSON only, no commentary."
)
SYS_FLASH = (
    "You are a rigorous universality-class critic. Apply Clauset 2009 + "
    "Stumpf-Porter 2012 standards: shared equation form + shared scaling "
    "exponents + shared critical mechanism. Output JSON only."
)
SYS_CHAT_BASELINE = (
    "You are a domain expert reviewing candidate universality classes for "
    "cross-domain dynamical-systems taxonomy. Judge each class on "
    "(a) shared dynamic equation / normal form, (b) shared scaling "
    "exponents or critical exponents, (c) shared critical mechanism. "
    "Output strict JSON only."
)

USER_PROMPT_TEMPLATE = """Review this candidate universality class.

Class id: {class_id}
Display name: {display_name}
Hub phenomenon: {hub}

Output JSON only:
{{
  "verdict": "KEEP" | "REJECT" | "UNCLEAR" | "SPLIT" | "MERGE",
  "confidence": <float 0-1>,
  "rationale": "<2 sentences>"
}}
"""

# Synthetic demo classes (subset; real b4 has 21 from B3 taxonomy v2)
DEMO_CLASSES = [
    {
        "class_id": "self-organized-criticality",
        "display_name": "Self-organized criticality (SOC)",
        "hub": "Slowly driven systems exhibiting scale-invariant avalanche statistics.",
    },
    {
        "class_id": "directed-percolation",
        "display_name": "Directed percolation",
        "hub": "Absorbing-state phase transitions with power-law cluster statistics.",
    },
    {
        "class_id": "extreme-value-confounder",
        "display_name": "Extreme value (CLT cousin)",
        "hub": "Limit-theorem family — NOT a true dynamical universality class.",
    },
]


def build_live_panel() -> JudgePanel:
    reviewers = [
        Reviewer(
            reviewer_id="deepseek-v4-pro-T0",
            model="deepseek-v4-pro",
            vendor="deepseek",
            temperature=0.0,
            max_tokens=4000,
            system_prompt=SYS_RIGOROUS,
        ),
        Reviewer(
            reviewer_id="deepseek-v4-flash-T0",
            model="deepseek-v4-flash",
            vendor="deepseek",
            temperature=0.0,
            max_tokens=2000,
            system_prompt=SYS_FLASH,
        ),
        Reviewer(
            reviewer_id="deepseek-v4-pro-T07-chat",
            model="deepseek-v4-pro",
            vendor="deepseek",
            temperature=0.7,
            max_tokens=4000,
            system_prompt=SYS_CHAT_BASELINE,
        ),
    ]
    # Tiebreaker priority matches b4: KEEP/REJECT > SPLIT/MERGE > UNCLEAR
    return JudgePanel(
        reviewers=reviewers,
        strategy="majority",
        strategy_kwargs={"priority": ["KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR"]},
    )


def build_mock_panel() -> JudgePanel:
    """Mock 3 reviewers with pre-canned verdicts mimicking b4 output."""

    @dataclass
    class _Msg:
        content: str

    @dataclass
    class _Choice:
        message: _Msg

    @dataclass
    class _Resp:
        choices: list

    # Pre-canned verdict pattern indexed by call number (round-robins per reviewer).
    # Each reviewer judges 3 items, so call_count tracks position.
    class _MockCompletions:
        def __init__(self, verdicts_for_3_items: list[dict[str, Any]]):
            self._scripted = verdicts_for_3_items
            self._idx = 0

        def create(self, **_k: Any) -> _Resp:
            v = self._scripted[self._idx % len(self._scripted)]
            self._idx += 1
            body = json.dumps(v)
            return _Resp(choices=[_Choice(message=_Msg(content=body))])

    class _Chat:
        def __init__(self, scripted):
            self.completions = _MockCompletions(scripted)

    class _MockClient:
        def __init__(self, scripted):
            self.chat = _Chat(scripted)

    # Rigorous pro: KEEP, KEEP, REJECT
    pro_script = [
        {"verdict": "KEEP", "confidence": 0.92, "rationale": "SOC has shared 1/f^a + avalanche exponent."},
        {"verdict": "KEEP", "confidence": 0.88, "rationale": "DP has shared exponents β, ν⊥, ν∥."},
        {"verdict": "REJECT", "confidence": 0.95, "rationale": "Limit theorem, not dynamical universality."},
    ]
    # Rigorous flash: matches pro
    flash_script = [
        {"verdict": "KEEP", "confidence": 0.85, "rationale": "Accept SOC."},
        {"verdict": "KEEP", "confidence": 0.80, "rationale": "Accept DP."},
        {"verdict": "REJECT", "confidence": 0.90, "rationale": "Reject — limit-theorem confusion."},
    ]
    # Chat baseline T=0.7: mostly agrees but more lenient on the bad one
    chat_script = [
        {"verdict": "KEEP", "confidence": 0.78, "rationale": "Plausible class."},
        {"verdict": "UNCLEAR", "confidence": 0.50, "rationale": "Need more empirical support."},
        {"verdict": "UNCLEAR", "confidence": 0.45, "rationale": "Edge case — could be defended."},
    ]

    reviewers = [
        Reviewer(reviewer_id="deepseek-v4-pro-T0", model="deepseek-v4-pro",
                 system_prompt=SYS_RIGOROUS, client=_MockClient(pro_script)),
        Reviewer(reviewer_id="deepseek-v4-flash-T0", model="deepseek-v4-flash",
                 system_prompt=SYS_FLASH, client=_MockClient(flash_script)),
        Reviewer(reviewer_id="deepseek-v4-pro-T07-chat", model="deepseek-v4-pro",
                 system_prompt=SYS_CHAT_BASELINE, client=_MockClient(chat_script)),
    ]
    return JudgePanel(
        reviewers=reviewers,
        strategy="majority",
        strategy_kwargs={"priority": ["KEEP", "REJECT", "SPLIT", "MERGE", "UNCLEAR"]},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use offline mock clients")
    args = parser.parse_args()

    if args.mock:
        panel = build_mock_panel()
    else:
        if not os.getenv("DEEPSEEK_API_KEY"):
            print("DEEPSEEK_API_KEY not set; re-run with --mock or export the key.", file=sys.stderr)
            return 2
        panel = build_live_panel()

    print("=== B4 demo: 3 DeepSeek reviewers × 3 candidate classes ===\n")
    results = []
    for cls in DEMO_CLASSES:
        prompt = USER_PROMPT_TEMPLATE.format(**cls)
        r = panel.ask(item_id=cls["class_id"], user_prompt=prompt, meta=cls)
        results.append(r)
        print(f"[{cls['class_id']}]")
        print(f"  → consensus: {r.consensus} (avg_conf={r.avg_confidence:.2f}, "
              f"disagree={r.disagreement})")
        for v in r.verdicts:
            tag = "OK" if v.error is None else f"ERR/{v.error}"
            print(f"     - {v.reviewer_id:28s} {v.verdict:10s} conf={v.confidence:.2f} [{tag}]")
        print()

    # Quick summary like B4 output
    print("=== Consensus distribution ===")
    dist: dict[str, int] = {}
    for r in results:
        dist[r.consensus] = dist.get(r.consensus, 0) + 1
    for label, n in sorted(dist.items()):
        print(f"  {label}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
