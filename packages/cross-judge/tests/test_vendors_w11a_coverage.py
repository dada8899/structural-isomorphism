"""W11-A coverage for cross_judge.vendors (lines 51-57, 75-90)."""
from __future__ import annotations

import pytest

from cross_judge.vendors import VENDORS, VendorConfig, get_vendor, make_client


def test_get_vendor_deepseek():
    cfg = get_vendor("deepseek")
    assert cfg.name == "deepseek"
    assert "deepseek.com" in cfg.base_url
    assert cfg.api_key_env == "DEEPSEEK_API_KEY"


def test_get_vendor_openai():
    cfg = get_vendor("openai")
    assert cfg.name == "openai"
    assert cfg.api_key_env == "OPENAI_API_KEY"


def test_get_vendor_openrouter():
    cfg = get_vendor("openrouter")
    assert cfg.api_key_env == "OPENROUTER_API_KEY"


def test_get_vendor_case_insensitive():
    cfg = get_vendor("DEEPSEEK")
    assert cfg.name == "deepseek"


def test_get_vendor_unknown_raises_keyerror():
    with pytest.raises(KeyError) as exc:
        get_vendor("acme")
    assert "Unknown vendor" in str(exc.value)


def test_vendor_config_immutable():
    """VendorConfig is frozen dataclass."""
    cfg = VENDORS["deepseek"]
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.name = "changed"


def test_vendors_dict_keys():
    assert set(VENDORS.keys()) == {"deepseek", "openai", "openrouter"}


# --- make_client -----------------------------------------------------------


def test_make_client_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError) as exc:
        make_client(vendor="deepseek")
    assert "Missing API key" in str(exc.value)
    assert "DEEPSEEK_API_KEY" in str(exc.value)


def test_make_client_with_explicit_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    try:
        client = make_client(vendor="deepseek", api_key="sk-test")
    except ImportError as e:
        pytest.skip(f"openai package not installed: {e}")
    assert client is not None
    # Verify base_url got set from vendor config
    assert "deepseek.com" in str(client.base_url)


def test_make_client_with_explicit_base_url(monkeypatch):
    try:
        client = make_client(
            vendor="openai", api_key="sk-test", base_url="https://custom.local/v1"
        )
    except ImportError as e:
        pytest.skip(f"openai package not installed: {e}")
    assert "custom.local" in str(client.base_url)


def test_make_client_env_var_used(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
    try:
        client = make_client(vendor="deepseek")
    except ImportError as e:
        pytest.skip(f"openai package not installed: {e}")
    assert client is not None


def test_make_client_unknown_vendor_raises(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    with pytest.raises(KeyError):
        make_client(vendor="acme-fake", api_key="sk-x")
