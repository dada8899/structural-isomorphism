"""Vendor adapter: route critic calls to OpenAI-compatible chat-completions endpoints.

All real-network vendors are accessed through the same OpenAI-compatible
/v1/chat/completions surface. OpenRouter is the recommended bridge for
Anthropic / Kimi / GLM since they all expose OpenAI-compatible endpoints
behind it.

Vendor registry:

  deepseek    https://api.deepseek.com/v1           DEEPSEEK_API_KEY
  anthropic   via OpenRouter                        ANTHROPIC_API_KEY or OPENROUTER_API_KEY
  openrouter  https://openrouter.ai/api/v1          OPENROUTER_API_KEY
  kimi        via OpenRouter (moonshotai/*)         OPENROUTER_API_KEY
  glm         via OpenRouter (zhipuai/*)            OPENROUTER_API_KEY
  openai      https://api.openai.com/v1             OPENAI_API_KEY
  mock        in-process stub (for tests / CI)      no key

The `mock` vendor returns a deterministic canned response for offline tests.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx


@dataclass
class VendorConfig:
    """Vendor connection metadata."""

    name: str
    base_url: str  # without trailing /chat/completions
    env_var: str  # env var name for API key
    # Approximate per-1k-token cost USD (input, output). Conservative upper
    # bounds; used by Critic for the cost-budget guardrail. Real costs vary
    # by model; users can override per-Critic via cost_per_1k_in/out.
    default_cost_per_1k_in: float = 0.001
    default_cost_per_1k_out: float = 0.003
    extra_headers: dict[str, str] = field(default_factory=dict)


VENDORS: dict[str, VendorConfig] = {
    "deepseek": VendorConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        env_var="DEEPSEEK_API_KEY",
        default_cost_per_1k_in=0.0002,
        default_cost_per_1k_out=0.0008,
    ),
    "openrouter": VendorConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        default_cost_per_1k_in=0.003,
        default_cost_per_1k_out=0.015,
        extra_headers={
            "HTTP-Referer": "https://github.com/dada8899/structural-isomorphism",
            "X-Title": "reject-aware-critic",
        },
    ),
    "openai": VendorConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        env_var="OPENAI_API_KEY",
        default_cost_per_1k_in=0.0025,
        default_cost_per_1k_out=0.01,
    ),
    # The next three all default to routing via OpenRouter (since CN egress
    # often blocks direct Anthropic / Moonshot / Zhipu calls). Library users
    # with direct vendor accounts can pass base_url= override at Critic init.
    "anthropic": VendorConfig(
        name="anthropic",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        default_cost_per_1k_in=0.003,
        default_cost_per_1k_out=0.015,
        extra_headers={
            "HTTP-Referer": "https://github.com/dada8899/structural-isomorphism",
            "X-Title": "reject-aware-critic",
        },
    ),
    "kimi": VendorConfig(
        name="kimi",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        default_cost_per_1k_in=0.0006,
        default_cost_per_1k_out=0.0025,
        extra_headers={
            "HTTP-Referer": "https://github.com/dada8899/structural-isomorphism",
            "X-Title": "reject-aware-critic",
        },
    ),
    "glm": VendorConfig(
        name="glm",
        base_url="https://openrouter.ai/api/v1",
        env_var="OPENROUTER_API_KEY",
        default_cost_per_1k_in=0.0005,
        default_cost_per_1k_out=0.002,
        extra_headers={
            "HTTP-Referer": "https://github.com/dada8899/structural-isomorphism",
            "X-Title": "reject-aware-critic",
        },
    ),
    "mock": VendorConfig(
        name="mock",
        base_url="mock://local",
        env_var="",  # no key needed
        default_cost_per_1k_in=0.0,
        default_cost_per_1k_out=0.0,
    ),
}


def get_vendor(name: str) -> VendorConfig:
    """Look up a vendor by name; raise KeyError on unknown vendor."""
    key = (name or "").strip().lower()
    if key not in VENDORS:
        raise KeyError(
            f"Unknown vendor '{name}'. Known: {sorted(VENDORS)}. "
            f"For custom endpoints pass base_url=... at Critic init."
        )
    return VENDORS[key]


def resolve_api_key(vendor: VendorConfig, explicit: str | None = None) -> str:
    """Return an API key, preferring explicit > env var."""
    if explicit:
        return explicit
    if not vendor.env_var:
        return ""  # mock vendor — no key required
    key = os.getenv(vendor.env_var)
    if not key:
        raise RuntimeError(
            f"Missing API key for vendor '{vendor.name}'. "
            f"Set env var {vendor.env_var} or pass api_key=... at Critic init."
        )
    return key


# ----- mock vendor support ---------------------------------------------------
#
# MockResponder is a callable: (model, messages, temperature, max_tokens) ->
# (content_text, usage_dict). usage_dict has prompt_tokens / completion_tokens.
# Default responder returns an UNCLEAR verdict so tests can override per-case.

MockResponder = Callable[[str, list[dict], float, int], tuple[str, dict]]


def _default_mock_responder(
    model: str, messages: list[dict], temperature: float, max_tokens: int
) -> tuple[str, dict]:
    payload = {
        "decision": "UNCLEAR",
        "confidence": 0.5,
        "rationale": "mock vendor default response",
        "trap_flags": [],
    }
    return json.dumps(payload), {"prompt_tokens": 100, "completion_tokens": 50}


_MOCK_RESPONDERS: dict[str, MockResponder] = {"default": _default_mock_responder}


def register_mock_responder(name: str, responder: MockResponder) -> None:
    """Register a named mock responder. Tests use this to inject canned replies."""
    _MOCK_RESPONDERS[name] = responder


def get_mock_responder(name: str = "default") -> MockResponder:
    return _MOCK_RESPONDERS.get(name, _default_mock_responder)


# ----- HTTP call ------------------------------------------------------------


def call_chat_completion(
    vendor: VendorConfig,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    *,
    base_url_override: str | None = None,
    timeout: float = 180.0,
    http_client: httpx.Client | None = None,
    mock_responder_name: str = "default",
) -> tuple[str | None, dict, str | None]:
    """Call an OpenAI-compatible chat-completion endpoint.

    Returns (content, usage_dict, error). content is None on error.

    usage_dict has prompt_tokens / completion_tokens / total_tokens when
    the server reports them; otherwise estimated heuristically (chars / 4).
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    if vendor.name == "mock":
        responder = get_mock_responder(mock_responder_name)
        try:
            content, usage = responder(model, messages, temperature, max_tokens)
        except Exception as e:  # pragma: no cover
            return None, {}, f"{type(e).__name__}: {e}"
        if not content:
            # Mirror the real-vendor behavior so empty mock responses also
            # surface as ERROR rather than as a PARSE_FAIL further downstream.
            return None, usage or {}, "empty content from mock vendor"
        return content, usage, None

    base = (base_url_override or vendor.base_url).rstrip("/")
    url = f"{base}/chat/completions"
    headers: dict[str, str] = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(vendor.extra_headers)
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    own_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout)
    try:
        resp = client.post(url, json=payload, headers=headers, timeout=timeout)
        if hasattr(resp, "status_code") and resp.status_code >= 400:
            body = ""
            try:
                body = resp.text[:300]
            except Exception:  # pragma: no cover
                body = "<unreadable body>"
            return None, {}, f"HTTP {resp.status_code}: {body}"
        try:
            data = resp.json()
        except Exception as e:
            return None, {}, f"json decode failed: {e}"
        try:
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content", "") or ""
            content = content.strip()
        except (KeyError, IndexError) as e:
            return None, {}, f"unexpected response shape: {e}"
        if not content:
            finish = choice.get("finish_reason", "?")
            return None, {}, f"empty content (finish_reason={finish})"
        usage = data.get("usage", {}) or {}
        return content, usage, None
    except httpx.HTTPError as e:
        return None, {}, f"{type(e).__name__}: {e}"
    except Exception as e:  # pragma: no cover
        return None, {}, f"{type(e).__name__}: {e}"
    finally:
        if own_client:
            try:
                client.close()
            except Exception:  # pragma: no cover
                pass


def estimate_cost_usd(usage: dict, vendor: VendorConfig,
                      cost_in_per_1k: float | None = None,
                      cost_out_per_1k: float | None = None) -> float:
    """Approximate USD cost from a usage dict + vendor defaults."""
    cin = cost_in_per_1k if cost_in_per_1k is not None else vendor.default_cost_per_1k_in
    cout = cost_out_per_1k if cost_out_per_1k is not None else vendor.default_cost_per_1k_out
    pt = float(usage.get("prompt_tokens", 0) or 0)
    ct = float(usage.get("completion_tokens", 0) or 0)
    return (pt / 1000.0) * cin + (ct / 1000.0) * cout


def estimate_usage_from_text(system_prompt: str, user_prompt: str, response: str) -> dict:
    """Rough token estimate when the server doesn't report usage (chars / 4)."""
    in_chars = len(system_prompt or "") + len(user_prompt or "")
    out_chars = len(response or "")
    return {
        "prompt_tokens": max(1, in_chars // 4),
        "completion_tokens": max(1, out_chars // 4),
        "total_tokens": max(1, (in_chars + out_chars) // 4),
    }
