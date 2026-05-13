"""Kimi (Moonshot) provider adapter.

OpenAI-compatible chat completions endpoint at https://api.moonshot.cn/v1.
Auth: reads `KIMI_API_KEY` (preferred) or `MOONSHOT_API_KEY` from env.
"""

from __future__ import annotations

import os
from typing import Any

from ..exceptions import LLMCallError
from . import BaseProvider, register_provider


# Approx public pricing snapshot (¥ converted to USD assuming 7 CNY/USD).
_DEFAULT_PRICING_USD_PER_M = {
    "kimi-k2": (0.85, 4.30),
    "kimi-k2.5": (1.0, 5.0),
    "moonshot-v1-8k": (1.71, 1.71),
    "moonshot-v1-32k": (3.43, 3.43),
    "moonshot-v1-128k": (8.57, 8.57),
}


class KimiProvider(BaseProvider):
    name = "kimi"

    def __init__(self) -> None:
        self.api_key = os.getenv("KIMI_API_KEY") or os.getenv("MOONSHOT_API_KEY", "")
        self.base_url = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
        self.timeout = float(os.getenv("KIMI_TIMEOUT_S", "60"))

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
        response_format: dict | None = None,
        **kwargs: Any,
    ) -> dict:
        import requests

        key = api_key or self.api_key
        if not key:
            raise LLMCallError(
                "Kimi API key not set. Pass api_key= or set KIMI_API_KEY."
            )
        url = (base_url or self.base_url).rstrip("/") + "/chat/completions"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            body["response_format"] = response_format
        elif schema is not None:
            body["response_format"] = {"type": "json_object"}
        body.update(kwargs)

        try:
            resp = requests.post(
                url,
                json=body,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise LLMCallError(f"kimi http error: {e}") from e

        if resp.status_code != 200:
            raise LLMCallError(f"kimi returned {resp.status_code}: {resp.text[:500]}")

        try:
            data = resp.json()
        except ValueError as e:
            raise LLMCallError(f"kimi response not JSON: {e}") from e

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMCallError(f"kimi response missing choices[0].message.content: {data}") from e

        usage = data.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = _estimate_cost_usd(model, in_tok, out_tok)
        return {"text": text, "cost_usd": cost, "usage": usage, "raw_response": data}


def _estimate_cost_usd(model: str, in_tok: int, out_tok: int) -> float:
    pricing = _DEFAULT_PRICING_USD_PER_M.get(model)
    if pricing is None:
        return 0.0
    in_price, out_price = pricing
    return (in_tok * in_price + out_tok * out_price) / 1_000_000.0


register_provider("kimi", KimiProvider)


__all__ = ["KimiProvider"]
