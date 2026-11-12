#!/usr/bin/env python3
"""Minimal cross-judge example: 3 reviewers vote on a synthetic classification.

Usage:
    # Mock mode (no API key, no network):
    python examples/classify_taxonomy.py --mock

    # Live mode (requires DEEPSEEK_API_KEY in env):
    export DEEPSEEK_API_KEY='sk-...'
    python examples/classify_taxonomy.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from cross_judge import JudgePanel, Reviewer


SYSTEM_RIGOROUS = (
    "You are a careful classifier. Read the item and decide if it is "
    "'BIOLOGICAL', 'PHYSICAL', or 'AMBIGUOUS'. Output strict JSON only."
)

SYSTEM_DISSENTER = (
    "You are a creative dissenter. Argue for the less-obvious classification "
    "if it has any merit. Output strict JSON only."
)


def build_user_prompt(item: str) -> str:
    return f"""Classify the following item.

Item: {item}

Allowed labels: BIOLOGICAL | PHYSICAL | AMBIGUOUS

Output strict JSON only (no markdown fences):
{{
  "verdict": "BIOLOGICAL"|"PHYSICAL"|"AMBIGUOUS",
  "confidence": 0.0-1.0,
  "rationale": "<one sentence>"
}}
"""


def build_live_panel() -> JudgePanel:
    reviewers = [
        Reviewer(
            reviewer_id="ds-pro-T0",
            model="deepseek-v4-pro",
            vendor="deepseek",
            temperature=0.0,
            max_tokens=512,
            system_prompt=SYSTEM_RIGOROUS,
        ),
        Reviewer(
            reviewer_id="ds-flash-T0",
            model="deepseek-v4-flash",
            vendor="deepseek",
            temperature=0.0,
            max_tokens=512,
            system_prompt=SYSTEM_RIGOROUS,
        ),
        Reviewer(
            reviewer_id="ds-pro-T07",
            model="deepseek-v4-pro",
            vendor="deepseek",
            temperature=0.7,
            max_tokens=512,
            system_prompt=SYSTEM_DISSENTER,
        ),
    ]
    return JudgePanel(reviewers=reviewers, strategy="majority")


def build_mock_panel() -> JudgePanel:
    """Build a panel whose Reviewers carry pre-baked mock clients (no network)."""
    from dataclasses import dataclass

    @dataclass
    class _Msg:
        content: str

    @dataclass
    class _Choice:
        message: _Msg

    @dataclass
    class _Resp:
        choices: list

    class _Completions:
        def __init__(self, verdict: str, conf: float):
            self.verdict = verdict
            self.conf = conf

        def create(self, **_k: Any) -> _Resp:
            body = json.dumps(
                {"verdict": self.verdict, "confidence": self.conf, "rationale": "mock"}
            )
            return _Resp(choices=[_Choice(message=_Msg(content=body))])

    class _Chat:
        def __init__(self, verdict: str, conf: float):
            self.completions = _Completions(verdict, conf)

    class _MockClient:
        def __init__(self, verdict: str, conf: float):
            self.chat = _Chat(verdict, conf)

    reviewers = [
        Reviewer(reviewer_id="mock-A", model="m", client=_MockClient("BIOLOGICAL", 0.9)),
        Reviewer(reviewer_id="mock-B", model="m", client=_MockClient("BIOLOGICAL", 0.8)),
        Reviewer(reviewer_id="mock-C", model="m", client=_MockClient("PHYSICAL", 0.5)),
    ]
    return JudgePanel(reviewers=reviewers, strategy="majority")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="Use offline mock clients")
    args = parser.parse_args()

    items = [
        ("metabolic-network", "A network of biochemical reactions in E. coli cells."),
        ("crystal-lattice", "A repeating periodic arrangement of atoms in a copper crystal."),
        ("river-delta", "Sediment branching patterns at the Mississippi river delta."),
    ]

    if args.mock:
        panel = build_mock_panel()
    else:
        if not os.getenv("DEEPSEEK_API_KEY"):
            print("DEEPSEEK_API_KEY not set; re-run with --mock or export the key.", file=sys.stderr)
            return 2
        panel = build_live_panel()

    for item_id, text in items:
        result = panel.ask(item_id=item_id, user_prompt=build_user_prompt(text))
        print(f"\n=== {item_id} ===")
        print(f"  consensus: {result.consensus} (avg_conf={result.avg_confidence:.2f}, disagree={result.disagreement})")
        for v in result.verdicts:
            tag = "OK" if v.error is None else f"ERR/{v.error}"
            print(f"   - {v.reviewer_id:12s} {v.verdict:12s} conf={v.confidence:.2f}  [{tag}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
