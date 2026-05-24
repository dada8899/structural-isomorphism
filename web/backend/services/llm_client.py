"""Generic reusable OpenRouter LLM client — Session #18.

Session #18 ships several new product surfaces (A1 method-search, E
structural stress-test, C2 structural lint). Each needs a JSON or text
completion. Rather than every feature growing `llm_service.py` (a
1390-line shared file, and a merge-conflict magnet for parallel work),
they share this thin wrapper.

It reuses the SAME OpenRouter endpoint and the SAME JSON-repair helpers
as `llm_service.py`, so behaviour matches the existing analyze / ask
paths exactly. No new third-party dependency.

All functions degrade gracefully when no API key is configured:
`complete_json` / `complete_text` return None, `stream_text` yields
nothing. Callers MUST handle that (it is the local-dev / test default).
"""
from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator, Optional

from services.llm_service import (
    OPENROUTER_URL,
    _fix_latex_escapes,
    _get_http_client,
    _try_repair_json,
)

logger = logging.getLogger("structural.llm_client")

# Single source of truth for the default model — same one analyze / ask
# use in prod. Honours the ASK_LLM_MODEL env override.
from services.ask_orchestrator import ASK_MODEL as _DEFAULT_MODEL


def _api_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "")


def llm_available() -> bool:
    """True when an OpenRouter key is configured.

    Feature endpoints should check this and surface a clean 503 / fallback
    rather than attempting a call that will certainly fail.
    """
    return bool(_api_key())


def _resolve_model(model: Optional[str]) -> str:
    return model or os.getenv("LLM_MODEL_S18", "") or _DEFAULT_MODEL


async def complete_json(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.4,
    max_tokens: int = 2600,
    timeout: float = 90.0,
) -> Optional[dict]:
    """Run one non-streaming completion and parse the reply as JSON.

    Returns the parsed dict, or None on any failure (no key, network
    error, unrepairable JSON). Never raises — the caller decides how to
    surface a degraded result.
    """
    if not _api_key():
        logger.warning("complete_json called with no OPENROUTER_API_KEY")
        return None
    try:
        client = _get_http_client()
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": _resolve_model(model),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        fixed = _fix_latex_escapes(content)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            logger.warning("complete_json: JSON parse failed, attempting repair")
            return _try_repair_json(fixed)
    except Exception as e:  # noqa: BLE001 — never let an LLM error escape
        logger.error("complete_json failed: %s", e)
        return None


async def complete_text(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.5,
    max_tokens: int = 2000,
    timeout: float = 90.0,
) -> Optional[str]:
    """Run one non-streaming plain-text completion. None on failure."""
    if not _api_key():
        logger.warning("complete_text called with no OPENROUTER_API_KEY")
        return None
    try:
        client = _get_http_client()
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": _resolve_model(model),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.error("complete_text failed: %s", e)
        return None


async def stream_text(
    *,
    system: str,
    user: str,
    model: Optional[str] = None,
    temperature: float = 0.5,
    max_tokens: int = 2600,
    timeout: float = 300.0,
) -> AsyncIterator[str]:
    """Stream a plain-text completion, yielding content deltas.

    Yields nothing when no key is configured. Swallows mid-stream errors
    (logs them) so a partial result still reaches the caller.
    """
    if not _api_key():
        logger.warning("stream_text called with no OPENROUTER_API_KEY")
        return
    try:
        client = _get_http_client()
        async with client.stream(
            "POST",
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
            json={
                "model": _resolve_model(model),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            },
            timeout=timeout,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
    except Exception as e:  # noqa: BLE001
        logger.error("stream_text failed: %s", e)
        return


__all__ = ["llm_available", "complete_json", "complete_text", "stream_text"]
