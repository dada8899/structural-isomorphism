"""DeepSeek provider adapter.

Uses DeepSeek's OpenAI-compatible chat completion endpoint. Talks raw HTTP
via `requests` so we don't force users to install the openai SDK.

Auth: reads `DEEPSEEK_API_KEY` from env unless `api_key=` kwarg is passed.
Endpoint: defaults to https://api.deepseek.com/v1/chat/completions
        (override via DEEPSEEK_BASE_URL env or base_url= kwarg).

Cost model: DeepSeek publishes per-million-token pricing on
https://api-docs.deepseek.com/quick_start/pricing — at writing time
deepseek-v4-flash ≈ $0.07/M input, $0.27/M output. These constants are
best-effort and exposed as class attributes for users to override.
"""

from __future__ import annotations

import os
from typing import Any

from ..exceptions import LLMCallError
from . import BaseProvider, register_provider


_DEFAULT_PRICING_USD_PER_M = {
    # model_id -> (input_price_per_M_tokens, output_price_per_M_tokens)
    "deepseek-chat": (0.27, 1.10),
    "deepseek-v4-flash": (0.07, 0.27),
    "deepseek-v4-pro": (0.55, 2.19),
    "deepseek-reasoner": (0.55, 2.19),
}


class DeepSeekProvider(BaseProvider):
    name = "deepseek"

    def __init__(self) -> None:
        self.api_key = os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.timeout = float(os.getenv("DEEPSEEK_TIMEOUT_S", "60"))

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
        import requests  # local import to keep top-level fast

        key = api_key or self.api_key
        if not key:
            raise LLMCallError(
                "DeepSeek API key not set. Pass api_key= or set DEEPSEEK_API_KEY."
            )
        url = (base_url or self.base_url).rstrip("/") + "/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        # Request JSON mode when a schema is present
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
            raise LLMCallError(f"deepseek http error: {e}") from e

        if resp.status_code != 200:
            raise LLMCallError(
                f"deepseek returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise LLMCallError(f"deepseek response not JSON: {e}") from e

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise LLMCallError(f"deepseek response missing choices[0].message.content: {data}") from e

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


register_provider("deepseek", DeepSeekProvider)


__all__ = ["DeepSeekProvider"]
