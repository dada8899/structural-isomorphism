"""Reviewer = one LLM configuration that produces a single Verdict per item.

A Reviewer carries:
  - reviewer_id    : unique tag (used in aggregation tables)
  - model          : vendor model id (e.g. 'deepseek-v4-pro', 'gpt-4o')
  - vendor         : 'deepseek' | 'openai' | 'openrouter' | 'custom'
  - system_prompt  : reviewer persona / judging rubric
  - temperature    : sampling temperature
  - max_tokens     : output cap
  - weight         : (optional) used by weighted aggregation
  - client         : (optional) preconstructed OpenAI-compat client; if None,
                     one is built lazily via vendors.make_client

The `ask(user_prompt)` method makes one chat completion call and returns a
Verdict object. JSON parsing is best-effort (strips markdown fences, finds
outermost {} pair).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from .schema import Verdict
from .vendors import make_client


def _extract_json(raw: str) -> dict | None:
    """Best-effort JSON object extraction from an LLM response string."""
    s = (raw or "").strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1]
        if s.endswith("```"):
            s = s[: -3].rstrip()
    i = s.find("{")
    j = s.rfind("}")
    if i < 0 or j < 0 or j <= i:
        return None
    candidate = s[i : j + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = candidate.replace(",\n}", "\n}").replace(",\n]", "\n]")
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


@dataclass
class Reviewer:
    """One LLM reviewer configuration."""

    reviewer_id: str
    model: str
    vendor: str = "deepseek"
    system_prompt: str = "You are a careful judge. Output strict JSON only."
    temperature: float = 0.0
    max_tokens: int = 2000
    weight: float = 1.0
    client: Any = field(default=None, repr=False)
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = field(default=None, repr=False)

    def _get_client(self) -> Any:
        if self.client is None:
            self.client = make_client(vendor=self.vendor, api_key=self.api_key, base_url=self.base_url)
        return self.client

    def ask(self, user_prompt: str) -> Verdict:
        """Call the LLM once and return a parsed Verdict.

        Network / parse errors are caught and surfaced as Verdict(error=...,
        verdict='ERROR'). Callers can decide whether to retry or skip.
        """
        client = self._get_client()
        t0 = time.time()
        raw: str | None = None
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            # openai-python v1+ response shape; vendor responses follow the same schema
            choice = resp.choices[0]
            raw = (getattr(choice.message, "content", None) or "").strip()
        except Exception as e:
            return Verdict(
                reviewer_id=self.reviewer_id,
                verdict="ERROR",
                confidence=0.0,
                rationale=f"{type(e).__name__}: {e}",
                raw_response=None,
                error=f"{type(e).__name__}: {e}",
                elapsed_s=round(time.time() - t0, 3),
            )

        elapsed = round(time.time() - t0, 3)
        if not raw:
            return Verdict(
                reviewer_id=self.reviewer_id,
                verdict="ERROR",
                confidence=0.0,
                rationale="empty response from LLM",
                raw_response=None,
                error="empty_response",
                elapsed_s=elapsed,
            )

        parsed = _extract_json(raw)
        if parsed is None:
            return Verdict(
                reviewer_id=self.reviewer_id,
                verdict="PARSE_FAIL",
                confidence=0.0,
                rationale=raw[:300],
                raw_response=raw,
                error="parse_fail",
                elapsed_s=elapsed,
            )

        verdict_label = str(parsed.get("verdict", "UNCLEAR")).strip().upper()
        conf_val = parsed.get("confidence", 0.0)
        try:
            conf = float(conf_val) if conf_val is not None else 0.0
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        rationale = str(parsed.get("rationale", ""))[:1000]
        return Verdict(
            reviewer_id=self.reviewer_id,
            verdict=verdict_label,
            confidence=conf,
            rationale=rationale,
            raw_response=raw,
            error=None,
            elapsed_s=elapsed,
        )
