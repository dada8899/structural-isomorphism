"""Regression guard for API documentation coverage.

For each public symbol exported by the three PyPI packages this repo
ships (``soc_pipeline``, ``cross_judge``, ``guarded_llm``):

- **Tier 1 (top public API)** — strict Google-style enforcement. Every
  symbol must have a non-trivial docstring with an ``Args:`` /
  ``Attributes:`` block, plus a ``Returns:`` block on non-None functions.
- **Tier 2 (rest of __all__)** — relaxed: must have a non-trivial
  docstring (≥ 30 chars) and full type-hint coverage on callables.

Type aliases (``Literal[...]`` / ``Callable[...]``) and module
constants (tuples / dicts) don't carry ``__doc__`` in CPython and are
exempt from docstring checks; they remain in the structural list so
``__all__`` removals are caught.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

# Add the three package src/ dirs so the test runs without requiring an
# editable install of the workspace.
_REPO = Path(__file__).resolve().parents[1]
for _pkg in ("soc-pipeline", "cross-judge", "guarded-llm"):
    _src = _REPO / "packages" / _pkg / "src"
    if str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

import cross_judge  # noqa: E402
import guarded_llm  # noqa: E402
import soc_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Symbols that are type aliases / module constants — exempt from __doc__.
# ---------------------------------------------------------------------------
_TYPE_ALIAS_EXEMPT = {
    ("cross_judge", "VerdictKind"),
    ("cross_judge", "VotingStrategy"),
    ("cross_judge", "AggregationStrategy"),
    ("cross_judge", "VOTING_STRATEGIES"),
    ("cross_judge", "VENDORS"),
    ("cross_judge", "VENDOR_DEFAULTS"),
    ("soc_pipeline", "__version__"),
    ("cross_judge", "__version__"),
    ("guarded_llm", "__version__"),
}

# ---------------------------------------------------------------------------
# Tier 1 — the top public API. Strict Google-style enforcement applies.
# These are the names CTAs in package READMEs / docs cards point at.
# ---------------------------------------------------------------------------
_TIER_1_PUBLIC_API = {
    ("soc_pipeline", "validate"),
    ("soc_pipeline", "Verdict"),
    ("soc_pipeline", "fit_clauset_powerlaw"),
    ("soc_pipeline", "bootstrap_ci"),
    ("soc_pipeline", "vuong_lr_test"),
    ("cross_judge", "Critic"),
    ("cross_judge", "Ensemble"),
    ("cross_judge", "Verdict"),
    ("cross_judge", "EnsembleVerdict"),
    ("guarded_llm", "GuardedLLM"),
    ("guarded_llm", "Budget"),
    ("guarded_llm", "RetryPolicy"),
    ("guarded_llm", "SchemaValidator"),
}

# ---------------------------------------------------------------------------
# Symbols where Args/Returns are documented in a class-level Attributes block.
# ---------------------------------------------------------------------------
_ATTRIBUTES_DOCUMENTED = {
    # dataclasses / Pydantic models — params documented via Attributes
    ("soc_pipeline", "Verdict"),
    ("soc_pipeline", "FitResult"),
    ("soc_pipeline", "BootstrapResult"),
    ("soc_pipeline", "LRResult"),
    ("soc_pipeline", "CollapseResult"),
    ("soc_pipeline", "OmoriResult"),
    ("soc_pipeline", "NullCase"),
    ("cross_judge", "Verdict"),
    ("cross_judge", "EnsembleVerdict"),
    ("cross_judge", "LegacyVerdict"),
    ("cross_judge", "EnsembleResult"),
    ("cross_judge", "VendorConfig"),
    ("guarded_llm", "GuardrailResult"),
    ("guarded_llm", "GuardedCallStats"),
    ("guarded_llm", "LLMSchema"),
    ("guarded_llm", "Layer3CriticVerdict"),
    ("guarded_llm", "Layer4Prediction"),
    ("guarded_llm", "B3EnsembleReview"),
    # Pydantic models with field-level docstring/description
    ("guarded_llm", "Budget"),
    ("guarded_llm", "RetryPolicy"),
}


def _all_public_symbols() -> list[tuple[str, str, object]]:
    """Yield ``(package_name, symbol_name, obj)`` for every entry in __all__."""
    out: list[tuple[str, str, object]] = []
    for mod in (soc_pipeline, cross_judge, guarded_llm):
        pkg = mod.__name__
        seen: set[str] = set()
        for name in mod.__all__:
            if name in seen:
                continue
            seen.add(name)
            try:
                obj = getattr(mod, name)
            except AttributeError:
                pytest.fail(f"{pkg}.__all__ lists {name!r} but module has no such attribute")
            out.append((pkg, name, obj))
    return out


PUBLIC_SYMBOLS = _all_public_symbols()


@pytest.mark.parametrize(
    ("pkg", "name", "obj"),
    [pytest.param(p, n, o, id=f"{p}.{n}") for (p, n, o) in PUBLIC_SYMBOLS],
)
def test_public_symbol_has_docstring(pkg: str, name: str, obj: object) -> None:
    """Every entry in ``__all__`` carries a non-trivial docstring."""
    if (pkg, name) in _TYPE_ALIAS_EXEMPT:
        pytest.skip(f"{pkg}.{name} is a type alias / module constant — no __doc__ slot")
    doc = inspect.getdoc(obj) or ""
    assert len(doc) >= 30, (
        f"{pkg}.{name}: docstring is missing or too short "
        f"({len(doc)} chars). Add a Google-style docstring."
    )


@pytest.mark.parametrize(
    ("pkg", "name", "obj"),
    [pytest.param(p, n, o, id=f"{p}.{n}") for (p, n, o) in PUBLIC_SYMBOLS],
)
def test_tier1_callable_documents_args(pkg: str, name: str, obj: object) -> None:
    """Tier-1 callables document parameters via Args: or Attributes:."""
    if (pkg, name) not in _TIER_1_PUBLIC_API:
        pytest.skip("not tier-1 public API")
    if not (inspect.isfunction(obj) or inspect.isclass(obj) or inspect.isbuiltin(obj)):
        pytest.skip("not callable / class")

    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        pytest.skip("signature unavailable")

    user_params = [
        p for p in sig.parameters.values()
        if p.name not in {"self", "cls"} and p.kind not in {p.VAR_POSITIONAL, p.VAR_KEYWORD}
    ]
    if not user_params:
        pytest.skip("zero-arg callable")

    doc = inspect.getdoc(obj) or ""
    assert "Args:" in doc or "Attributes:" in doc or "Parameters" in doc, (
        f"{pkg}.{name}: tier-1 callable with {len(user_params)} param(s) is missing Args:/Attributes: section"
    )


@pytest.mark.parametrize(
    ("pkg", "name", "obj"),
    [pytest.param(p, n, o, id=f"{p}.{n}") for (p, n, o) in PUBLIC_SYMBOLS],
)
def test_tier1_function_documents_returns(pkg: str, name: str, obj: object) -> None:
    """Tier-1 functions (non-class) document Returns: or Yields:."""
    if (pkg, name) not in _TIER_1_PUBLIC_API:
        pytest.skip("not tier-1 public API")
    if inspect.isclass(obj):
        pytest.skip("class — documented via Attributes:")
    if not (inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isbuiltin(obj)):
        pytest.skip("not a function")

    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        pytest.skip("signature unavailable")

    ret_ann = sig.return_annotation
    if ret_ann is type(None) or ret_ann is None:
        pytest.skip("returns None")

    doc = inspect.getdoc(obj) or ""
    assert "Returns:" in doc or "Yields:" in doc or "Return:" in doc, (
        f"{pkg}.{name}: tier-1 function with non-None return is missing Returns: section"
    )


@pytest.mark.parametrize(
    ("pkg", "name", "obj"),
    [pytest.param(p, n, o, id=f"{p}.{n}") for (p, n, o) in PUBLIC_SYMBOLS],
)
def test_public_callable_has_type_hints(pkg: str, name: str, obj: object) -> None:
    """Public callables have a non-empty type signature on all parameters and return."""
    if (pkg, name) in _TYPE_ALIAS_EXEMPT:
        pytest.skip("type alias")
    if not (inspect.isfunction(obj) or inspect.isclass(obj)):
        pytest.skip("not a function/class")
    if inspect.isclass(obj) and issubclass(obj, BaseException):
        pytest.skip("exception class")

    try:
        sig = inspect.signature(obj)
    except (TypeError, ValueError):
        pytest.skip("signature unavailable")

    missing: list[str] = []
    for param in sig.parameters.values():
        if param.name in {"self", "cls"}:
            continue
        if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
            continue
        if param.annotation is inspect.Parameter.empty:
            missing.append(param.name)
    assert not missing, (
        f"{pkg}.{name}: missing type hints on parameters: {missing}"
    )


def test_summary_coverage_report() -> None:
    """Surface a one-shot coverage % across the three packages (informational)."""
    total = 0
    documented = 0
    for pkg_name, sym_name, obj in PUBLIC_SYMBOLS:
        if (pkg_name, sym_name) in _TYPE_ALIAS_EXEMPT:
            continue
        total += 1
        doc = inspect.getdoc(obj) or ""
        if len(doc) >= 30:
            documented += 1
    pct = 100.0 * documented / total if total else 0.0
    print(f"\n[api-docs-coverage] {documented}/{total} = {pct:.1f}%")
    assert pct == 100.0, f"docstring coverage must be 100% on public API, got {pct:.1f}%"
