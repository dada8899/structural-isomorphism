"""Anthropic provider adapter (Claude).

Uses Anthropic's `messages` HTTP endpoint. Talks raw HTTP via `requests`
so we don't force users to install the `anthropic` SDK; if you do install
the SDK you can swap this for a thin wrapper via `register_provider`.

Auth: reads `ANTHROPIC_API_KEY` from env unless `api_key=` kwarg is passed.
"""

from __future__ import annotations

import os
from typing import Any

from ..exceptions import LLMCallError
from . import BaseProvider, register_provider


# Public sticker prices in USD per million tokens (Apr 2026 snapshot).
_DEFAULT_PRICING_USD_PER_M = {
    "claude-sonnet-4.5": (3.0, 15.0),
    "claude-opus-4.5": (15.0, 75.0),
    "claude-haiku-4.5": (1.0, 5.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (0.80, 4.0),
}


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1")
        self.api_version = os.getenv("ANTHROPIC_VERSION", "2023-06-01")
        self.timeout = float(os.getenv("ANTHROPIC_TIMEOUT_S", "120"))

    def call(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        schema: Any = None,
        *,
        temperature: float = 0.0,
        api_key: str | None = None,
        base_url: str | None = None,
        system: str | None = None,
        **kwargs: Any,
    ) -> dict:
        import requests

        key = api_key or self.api_key
        if not key:
            raise LLMCallError(
                "Anthropic API key not set. Pass api_key= or set ANTHROPIC_API_KEY."
            )
        url = (base_url or self.base_url).rstrip("/") + "/messages"

        # Anthropic expects `system` as a separate top-level field, not in messages
        sys_msg = system
        chat_messages: list[dict] = []
        for m in messages:
            if m.get("role") == "system" and sys_msg is None:
                sys_msg = m.get("content", "")
            else:
                chat_messages.append(m)

        body: dict[str, Any] = {
            "model": model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if sys_msg:
            body["system"] = sys_msg
        body.update(kwargs)

        try:
            resp = requests.post(
                url,
                json=body,
                headers={
                    "x-api-key": key,
                    "anthropic-version": self.api_version,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise LLMCallError(f"anthropic http error: {e}") from e

        if resp.status_code != 200:
            raise LLMCallError(
                f"anthropic returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise LLMCallError(f"anthropic response not JSON: {e}") from e

        try:
            # content is a list of blocks: [{"type": "text", "text": "..."}]
            blocks = data.get("content") or []
            text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
            text = "".join(text_parts)
        except (KeyError, TypeError, AttributeError) as e:
            raise LLMCallError(f"anthropic response shape unexpected: {data}") from e

        usage = data.get("usage") or {}
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        cost = _estimate_cost_usd(model, in_tok, out_tok)
        return {"text": text, "cost_usd": cost, "usage": usage, "raw_response": data}


def _estimate_cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    pricing = _DEFAULT_PRICING_USD_PER_M.get(model)
    if pricing is None:
        return 0.0
    in_price, out_price = pricing
    return (in_tok * in_price + out_tok * out_price) / 1_000_000.0


register_provider("anthropic", AnthropicProvider)


__all__ = ["AnthropicProvider"]
