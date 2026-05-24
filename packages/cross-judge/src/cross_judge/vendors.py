"""Vendor-specific OpenAI-compatible client factory.

Most modern LLM vendors expose an OpenAI-compatible /v1/chat/completions
endpoint, so a single openai-python client can talk to all of them by
swapping `base_url` + `api_key`. This module centralizes the per-vendor
defaults so callers don't have to memorize base URLs.

Supported vendors (out of the box):
  - deepseek    (default; api.deepseek.com — direct, bypasses CN region-block)
  - openai      (api.openai.com)
  - openrouter  (openrouter.ai/api/v1 — multi-vendor router)
  - custom      (any OpenAI-compatible base_url)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VendorConfig:
    """Vendor-specific connection settings for OpenAI-compatible APIs."""

    name: str
    base_url: str
    api_key_env: str  # environment variable name to read the API key from


VENDORS: dict[str, VendorConfig] = {
    "deepseek": VendorConfig(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "openai": VendorConfig(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "openrouter": VendorConfig(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
}


def get_vendor(name: str) -> VendorConfig:
    """Look up a vendor by name. Raises KeyError on unknown vendor."""
    key = name.lower()
    if key not in VENDORS:
        raise KeyError(
            f"Unknown vendor '{name}'. Known: {sorted(VENDORS)}. "
            f"For arbitrary OpenAI-compatible endpoints, build your own client and pass it directly."
        )
    return VENDORS[key]


def make_client(vendor: str = "deepseek", api_key: str | None = None, base_url: str | None = None) -> Any:
    """Build an OpenAI-compatible client for a vendor.

    Args:
        vendor: One of 'deepseek', 'openai', 'openrouter' (default: deepseek).
        api_key: Explicit API key. If None, read from the vendor's env var.
        base_url: Override base URL (useful for custom endpoints / mock servers).

    Returns:
        An `openai.OpenAI` client instance configured for the vendor.

    Raises:
        RuntimeError: if the API key is missing.
        ImportError: if `openai` package is not installed.
    """
    try:
        from openai import OpenAI
    except ImportError as e:
        raise ImportError(
            "The 'openai' package is required for cross-judge LLM calls. "
            "Install with: pip install 'openai>=1.0'"
        ) from e

    cfg = get_vendor(vendor)
    key = api_key or os.getenv(cfg.api_key_env)
    if not key:
        raise RuntimeError(
            f"Missing API key for vendor '{vendor}'. "
            f"Set {cfg.api_key_env} env var or pass api_key=... explicitly."
        )
    return OpenAI(api_key=key, base_url=base_url or cfg.base_url)
