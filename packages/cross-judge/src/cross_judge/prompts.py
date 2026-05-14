"""Default judge prompt templates.

These are minimal generic prompts. Real projects should typically write
domain-specific system + user prompts. See `examples/` for a research-grade
prompt (B3/B4 universality-class review) used in the structural-isomorphism
project.
"""
from __future__ import annotations

DEFAULT_SYSTEM_PROMPT = (
    "You are a careful judge. Read the item and output a strict JSON object "
    "with the schema described in the user message. Output JSON only, no "
    "commentary, no markdown fences."
)


DEFAULT_USER_PROMPT_TEMPLATE = """Judge the following item.

Item:
{item}

Output JSON only, exact schema:
{{
  "verdict": "<one of: {labels}>",
  "confidence": <float 0.0-1.0>,
  "rationale": "<1-3 sentences>"
}}
"""


def render_user_prompt(item: str, labels: list[str]) -> str:
    """Render the default user prompt with a list of allowed labels."""
    return DEFAULT_USER_PROMPT_TEMPLATE.format(
        item=item,
        labels=" | ".join(labels),
    )
