"""Regression: slowapi rate-limit decorator must not lose the handler's
`__globals__` namespace (the prod 502 root cause).

ROOT CAUSE
----------
`services.rate_limit.tier_limit_decorator` returns `limiter.limit(...)`.
slowapi builds its wrapper with `functools.wraps(func)` — but `functools.wraps`
canNOT copy `__globals__` (a function's `__globals__` is bound to its code
object). So the wrapper's `__globals__` points at `slowapi.extension`, not at
the handler's own module.

FastAPI resolves a route's parameter annotations with
`get_typed_signature(call)`:
  * FastAPI 0.110.0 (prod, pinned in web/backend/requirements.txt):
        globalns = getattr(call, "__globals__", {})   # NO inspect.unwrap
  * FastAPI 0.136.x (local .venv):
        unwrapped = inspect.unwrap(call); globalns = unwrapped.__globals__

When a handler module carries `from __future__ import annotations` (PEP 563),
its parameter annotations are stringified (`req: "DiagnoseRequest"`). On the
prod FastAPI the stringified annotation is evaluated against the *slowapi*
namespace, which has no `DiagnoseRequest` -> `NameError` at app construction
-> startup crash -> nginx 502.

The previous session patched the symptom by deleting `from __future__ import
annotations` from two handlers. This test pins the *mechanism*: the decorator
must produce a wrapper whose annotation-resolution namespace is the handler's
own module — independent of FastAPI version and independent of PEP 563.

WHAT THIS TEST ASSERTS
----------------------
1. `_handler_globalns(wrapper)` (replicating BOTH FastAPI resolution paths)
   contains the handler module's local Pydantic model symbol.
2. A fully PEP-563 handler decorated with `tier_limit_decorator`, mounted on
   a real FastAPI app, builds without raising — using the 0.110.0 (no-unwrap)
   resolution path explicitly, so the test reproduces prod regardless of the
   FastAPI version installed locally.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import ForwardRef

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.rate_limit import _ENABLED, tier_limit_decorator  # noqa: E402

# A PEP-563 handler module: annotations are stringified, local Pydantic model
# lives ONLY in this module's namespace. This is exactly the shape that broke
# diagnose.py / stress_test.py in prod.
_HANDLER_SRC = """
from __future__ import annotations

from fastapi import Request
from pydantic import BaseModel


class LocalOnlyModel(BaseModel):
    payload: str


async def handler(request: Request, req: LocalOnlyModel):
    return {"ok": True}
"""


def _make_pep563_handler():
    """Build a fresh handler module that uses PEP 563 + a local Pydantic model."""
    mod = types.ModuleType("pep563_handler_fixture")
    exec(compile(_HANDLER_SRC, "pep563_handler_fixture.py", "exec"), mod.__dict__)
    return mod, mod.__dict__["handler"]


def _resolve_globalns_0110(call) -> dict:
    """Replicate FastAPI 0.110.0 `get_typed_signature`: NO inspect.unwrap.

    This is the prod path that actually crashes.
    """
    return getattr(call, "__globals__", {})


def _resolve_globalns_0136(call) -> dict:
    """Replicate FastAPI 0.136.x `get_typed_signature`: follows `__wrapped__`."""
    import inspect

    return getattr(inspect.unwrap(call), "__globals__", {})


pytestmark = pytest.mark.skipif(
    not _ENABLED, reason="slowapi unavailable — decorator is a no-op, nothing to test"
)


def test_wrapper_globalns_contains_handler_model_0110_path():
    """Prod (0.110.0) resolution path must see the handler's local model.

    This is the assertion that FAILS against the unfixed decorator: the
    wrapper's raw `__globals__` is slowapi's namespace, which lacks
    `LocalOnlyModel`.
    """
    _mod, handler = _make_pep563_handler()
    wrapped = tier_limit_decorator(default_anon="10/minute")(handler)

    globalns = _resolve_globalns_0110(wrapped)
    assert "LocalOnlyModel" in globalns, (
        "FastAPI 0.110.0 resolves annotations against wrapper.__globals__ "
        "directly. The rate-limit wrapper must carry the handler module's "
        "namespace, otherwise PEP-563 stringified annotations crash at "
        "app construction (prod 502 root cause)."
    )


def test_wrapper_globalns_contains_handler_model_0136_path():
    """Newer-FastAPI resolution path must also resolve cleanly."""
    _mod, handler = _make_pep563_handler()
    wrapped = tier_limit_decorator(default_anon="10/minute")(handler)

    globalns = _resolve_globalns_0136(wrapped)
    assert "LocalOnlyModel" in globalns


def test_stringified_annotation_resolves_both_fastapi_paths():
    """The actual failure point: evaluating the stringified annotation.

    `req: LocalOnlyModel` is stored as the string "LocalOnlyModel" under
    PEP 563. FastAPI turns it into a ForwardRef and evaluates it against the
    resolved globalns. Both prod (0.110.0) and local (0.136.x) paths must
    produce the real model class, not raise NameError.
    """
    _mod, handler = _make_pep563_handler()
    wrapped = tier_limit_decorator(default_anon="10/minute")(handler)

    assert handler.__annotations__["req"] == "LocalOnlyModel", (
        "sanity: handler must actually use PEP 563 (stringified annotation)"
    )

    import typing

    for label, resolver in (
        ("0.110.0", _resolve_globalns_0110),
        ("0.136.x", _resolve_globalns_0136),
    ):
        globalns = resolver(wrapped)
        ref = ForwardRef("LocalOnlyModel")
        try:
            # typing._eval_type is what FastAPI's evaluate_forwardref calls
            # under the hood; cross-version stable for resolving a bare name.
            resolved = typing._eval_type(ref, globalns, globalns, ())
        except NameError as exc:  # pragma: no cover - this IS the regression
            pytest.fail(
                f"FastAPI {label} annotation resolution crashed: {exc!r}. "
                "The rate-limit wrapper lost the handler's __globals__."
            )
        assert resolved.__name__ == "LocalOnlyModel"


def test_pep563_handler_mounts_on_fastapi_app():
    """End-to-end: a PEP-563 handler + rate-limit decorator must mount.

    We force the FastAPI 0.110.0 (no-unwrap) resolution path so this test
    reproduces the prod crash even though the local .venv ships a newer
    FastAPI that would mask the bug via `inspect.unwrap`.
    """
    import fastapi.dependencies.utils as fastapi_utils
    from fastapi import FastAPI

    _mod, handler = _make_pep563_handler()
    wrapped = tier_limit_decorator(default_anon="10/minute")(handler)

    original = fastapi_utils.get_typed_signature

    def _get_typed_signature_0110(call):
        """0.110.0 behaviour: globalns from call.__globals__, no unwrap."""
        import inspect

        signature = inspect.signature(call)
        globalns = getattr(call, "__globals__", {})
        typed_params = [
            inspect.Parameter(
                name=p.name,
                kind=p.kind,
                default=p.default,
                annotation=fastapi_utils.get_typed_annotation(p.annotation, globalns),
            )
            for p in signature.parameters.values()
        ]
        return inspect.Signature(typed_params)

    fastapi_utils.get_typed_signature = _get_typed_signature_0110
    try:
        app = FastAPI()
        # add_api_route triggers annotation resolution — this is where the
        # prod app crashed at startup.
        app.add_api_route("/_pep563_probe", wrapped, methods=["POST"])
    finally:
        fastapi_utils.get_typed_signature = original

    route_paths = {r.path for r in app.routes}
    assert "/_pep563_probe" in route_paths
