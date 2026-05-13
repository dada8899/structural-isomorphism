"""Provider adapters for guarded-llm.

A provider is a thin adapter over a vendor SDK / HTTP endpoint. Each one
exposes a single `call(...)` method returning a dict with at least:

    {"text": "<raw assistant content>", "cost_usd": <float>}

To register a new provider, subclass `BaseProvider` and call
`register_provider("name", YourProvider)` at import time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):
    """Interface every provider adapter implements."""

    name: str = ""

    @abstractmethod
    def call(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        schema: Any = None,
        **kwargs: Any,
    ) -> dict:
        """Send `messages` to the LLM and return {"text": str, "cost_usd": float}."""
        ...


# Registry: provider-name -> BaseProvider subclass
PROVIDERS: dict[str, type[BaseProvider]] = {}


def register_provider(name: str, cls: type[BaseProvider]) -> None:
    """Add (or override) a provider in the registry."""
    if not issubclass(cls, BaseProvider):
        raise TypeError(f"{cls!r} must subclass BaseProvider")
    PROVIDERS[name] = cls


def get_provider(name: str) -> BaseProvider:
    """Instantiate and return the provider named `name`.

    Raises ValueError if the provider isn't registered.
    """
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name!r}. Registered: {sorted(PROVIDERS.keys())}"
        )
    return PROVIDERS[name]()


def list_providers() -> list[str]:
    """Return the sorted list of registered provider names."""
    return sorted(PROVIDERS.keys())


# Eagerly import built-in providers so they self-register
from . import deepseek  # noqa: E402, F401
from . import anthropic  # noqa: E402, F401
from . import openai  # noqa: E402, F401
from . import kimi  # noqa: E402, F401


__all__ = [
    "BaseProvider",
    "PROVIDERS",
    "register_provider",
    "get_provider",
    "list_providers",
]
