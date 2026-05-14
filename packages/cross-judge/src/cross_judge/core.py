"""Critic — one LLM configuration that produces a single Verdict per query.

Critic is the v0.1 PyPI public surface. It wraps:
  - name              : unique critic identifier
  - model             : vendor model id (e.g. 'deepseek-v4-pro', 'gpt-4o')
  - prompt_template   : a str.format-style template with `{query}` and optional
                        keys from the `context` dict at .judge() time
  - vendor            : 'deepseek' | 'openai' | 'openrouter' | 'custom'
  - api_key / base_url: explicit overrides; defaults read from env vars
  - temperature       : sampling temperature
  - max_tokens        : output cap
  - http_client       : (optional) httpx.Client to inject for tests / mocking

The .judge(query, context) method makes one chat completion call and returns
a Verdict object. JSON parsing is best-effort. Network / parse errors are
caught and surfaced as Verdict(kind='ERROR', error=...).

Design choice — standalone httpx client, no openai-python dep:
  At v0.1 we ship a minimal httpx-based POST to /v1/chat/completions to
  avoid version-coupling the package to openai-python's API surface (which
  has had multiple breaking releases in 2024-2025). Users who prefer the
  openai client can install cross-judge[openai] and inject their own
  via the `http_client` parameter.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .verdict import Verdict

# Vendor → (base URL, env var) registry. Centralized so callers don't memorize.
VENDOR_DEFAULTS: dict[str, tuple[str, str]] = {
    "deepseek": ("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
}


def _extract_json(raw: str) -> dict | None:
    """Best-effort JSON object extraction from an LLM response string.

    Strips markdown code fences, finds the outermost {..} pair, tolerates
    trailing commas inside objects / arrays.
    """
    s = (raw or "").strip()
    if s.startswith("```"):
        parts = s.split("\n", 1)
        if len(parts) == 2:
            s = parts[1]
        if s.endswith("```"):
            s = s[:-3].rstrip()
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
class Critic:
    """One LLM critic configuration.

    Args:
        name: unique critic identifier (e.g. 'claude-strict', 'deepseek-creative').
            Used in EnsembleVerdict.verdicts and disagreement diagnostics.
        model: vendor model id (e.g. 'deepseek-v4-pro', 'gpt-4o',
            'anthropic/claude-sonnet-4.5' via openrouter).
        prompt_template: A str.format() template with `{query}` and any keys
            from the context dict passed to .judge(). Must instruct the LLM
            to return strict JSON with `verdict` (or `kind`), `confidence`,
            `reasoning` (or `rationale`) fields.
        vendor: 'deepseek' (default) / 'openai' / 'openrouter' / 'custom'.
            For 'custom', pass base_url explicitly.
        system_prompt: optional system message ('' = none).
        temperature: sampling temperature (default 0.0 for deterministic judging).
        max_tokens: output cap.
        api_key: explicit API key (else read from env var per vendor).
        base_url: explicit base URL override.
        http_client: inject an httpx.Client (or compatible mock) for testing.
        timeout: per-request timeout in seconds.

    Example:
        critic = Critic(
            name="claude-strict",
            model="anthropic/claude-sonnet-4.5",
            vendor="openrouter",
            prompt_template="Judge: {query}\\nOutput JSON: ...",
        )
        v = critic.judge("Is this isomorphic to power-law?", context={})
    """

    name: str
    model: str
    prompt_template: str = "Judge the following query:\n{query}\n\nOutput JSON with kind (KEEP/REJECT/SPLIT/MERGE), confidence (0-1), reasoning."
    vendor: str = "deepseek"
    system_prompt: str = "You are a careful judge. Output strict JSON only."
    temperature: float = 0.0
    max_tokens: int = 2000
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = field(default=None, repr=False)
    http_client: Any = field(default=None, repr=False)
    timeout: float = 60.0

    def _resolved_base_url(self) -> str:
        if self.base_url:
            return self.base_url
        if self.vendor in VENDOR_DEFAULTS:
            return VENDOR_DEFAULTS[self.vendor][0]
        raise ValueError(
            f"Unknown vendor '{self.vendor}'. Pass base_url=... explicitly for custom vendors."
        )

    def _resolved_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        if self.vendor in VENDOR_DEFAULTS:
            env = VENDOR_DEFAULTS[self.vendor][1]
            key = os.getenv(env)
            if not key:
                raise RuntimeError(
                    f"Missing API key for vendor '{self.vendor}'. "
                    f"Set {env} env var or pass api_key=... explicitly."
                )
            return key
        raise RuntimeError(
            f"Missing api_key for vendor '{self.vendor}'. Pass api_key=... explicitly."
        )

    def _get_client(self) -> Any:
        if self.http_client is None:
            self.http_client = httpx.Client(timeout=self.timeout)
        return self.http_client

    def _render_prompt(self, query: str, context: dict[str, Any] | None) -> str:
        ctx = dict(context or {})
        ctx.setdefault("query", query)
        try:
            return self.prompt_template.format(**ctx)
        except KeyError as e:
            raise KeyError(
                f"prompt_template missing required key {e} in context. "
                f"Provided keys: {sorted(ctx)}"
            ) from e

    def judge(self, query: str, context: dict[str, Any] | None = None) -> Verdict:
        """Run this critic on one query and return a Verdict.

        Args:
            query: the item to judge.
            context: additional template variables (merged into prompt_template).

        Returns:
            Verdict — kind/confidence/reasoning. Errors surfaced as
            Verdict(kind='ERROR', error=...) rather than raised exceptions.
        """
        user_prompt = self._render_prompt(query, context)
        client = self._get_client()
        url = self._resolved_base_url().rstrip("/") + "/chat/completions"

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        t0 = time.time()
        raw: str | None = None
        try:
            api_key = self._resolved_api_key()
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            resp = client.post(url, json=payload, headers=headers)
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
            data = resp.json()
            raw = (data["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:
            return Verdict(
                kind="ERROR",
                confidence=0.0,
                reasoning=f"{type(e).__name__}: {e}",
                critic_id=self.name,
                raw_response=None,
                error=f"{type(e).__name__}: {e}",
                elapsed_s=round(time.time() - t0, 3),
            )

        elapsed = round(time.time() - t0, 3)
        if not raw:
            return Verdict(
                kind="ERROR",
                confidence=0.0,
                reasoning="empty response from LLM",
                critic_id=self.name,
                raw_response=None,
                error="empty_response",
                elapsed_s=elapsed,
            )

        return self._parse_verdict(raw, elapsed)

    def _parse_verdict(self, raw: str, elapsed: float) -> Verdict:
        """Parse a raw LLM response into a Verdict.

        Accepts either {kind, confidence, reasoning} (new schema) or the
        legacy {verdict, confidence, rationale} schema.
        """
        parsed = _extract_json(raw)
        if parsed is None:
            return Verdict(
                kind="PARSE_FAIL",
                confidence=0.0,
                reasoning=raw[:300],
                critic_id=self.name,
                raw_response=raw,
                error="parse_fail",
                elapsed_s=elapsed,
            )

        kind_val = parsed.get("kind", parsed.get("verdict", "UNCLEAR"))
        kind = str(kind_val).strip().upper()
        conf_val = parsed.get("confidence", 0.0)
        try:
            conf = float(conf_val) if conf_val is not None else 0.0
        except (TypeError, ValueError):
            conf = 0.0
        conf = max(0.0, min(1.0, conf))
        reasoning = str(parsed.get("reasoning", parsed.get("rationale", "")))[:1000]
        return Verdict(
            kind=kind,
            confidence=conf,
            reasoning=reasoning,
            critic_id=self.name,
            raw_response=raw,
            error=None,
            elapsed_s=elapsed,
        )

    @classmethod
    def from_yaml_prompt(
        cls,
        name: str,
        model: str,
        yaml_path: str,
        **kwargs: Any,
    ) -> "Critic":
        """Build a Critic from a YAML prompt file shipped under prompts/.

        YAML schema (versioned):
            version: "0.1"
            system_prompt: "..."
            user_prompt_template: "Judge: {query}\\n..."
        """
        import yaml

        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            name=name,
            model=model,
            prompt_template=data.get("user_prompt_template", ""),
            system_prompt=data.get("system_prompt", "You are a careful judge."),
            **kwargs,
        )
