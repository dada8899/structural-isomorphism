"""Pydantic-based SchemaValidator.

A thin wrapper around a `pydantic.BaseModel` subclass that exposes the same
`(ok, error, instance)` triple as `LLMSchema`. Use this when you want strict
typed Python objects back from the LLM call rather than raw dicts.

Example::

    from pydantic import BaseModel
    from guarded_llm import SchemaValidator

    class Verdict(BaseModel):
        verdict: str
        confidence: float

    validator = SchemaValidator(Verdict)
    ok, err, inst = validator.validate({"verdict": "KEEP", "confidence": 0.9})
    assert inst.verdict == "KEEP"          # real Pydantic instance
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, ValidationError  # type: ignore
    _HAS_PYDANTIC = True
except ImportError:
    BaseModel = None  # type: ignore
    ValidationError = Exception  # type: ignore
    _HAS_PYDANTIC = False


class SchemaValidator:
    """Wrap a `pydantic.BaseModel` to fit guarded-llm's `(ok, err, instance)` API.

    Args:
        model: a Pydantic v2 BaseModel subclass.

    Example::

        class Out(BaseModel):
            verdict: str
            confidence: float

        v = SchemaValidator(Out)
        v.validate({"verdict": "KEEP", "confidence": 0.9})  # -> (True, None, Out(...))
    """

    def __init__(self, model: Any):
        if not _HAS_PYDANTIC:
            raise ImportError(
                "SchemaValidator requires `pydantic>=2`. "
                "Install with `pip install pydantic`."
            )
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(
                f"model must be a pydantic.BaseModel subclass, got {model!r}"
            )
        self._model = model

    @property
    def model(self) -> type:
        return self._model

    def validate(self, d: Any) -> tuple[bool, str | None, Any]:
        """Validate `d` against the Pydantic model.

        Returns (ok, error_message_or_none, model_instance_or_none).
        """
        try:
            inst = self._model.model_validate(d)
        except ValidationError as e:
            # Pretty-print the first error path so it's useful in retry hints
            errs = e.errors()
            if errs:
                first = errs[0]
                path = ".".join(str(p) for p in first.get("loc", [])) or "<root>"
                msg = f"{path}: {first.get('msg', 'validation error')}"
            else:
                msg = str(e)
            return False, msg, None
        except Exception as e:
            return False, f"pydantic error: {e}", None
        return True, None, inst


__all__ = ["SchemaValidator"]
