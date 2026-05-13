"""Schema definitions for guarded-llm.

Two interchangeable styles:

1. **Dataclass schemas** — the legacy V4 style, used by the
   structural-isomorphism project. A schema class defines a `.validate(d)`
   classmethod returning `(ok, err, instance)`. See `Layer3CriticVerdict`,
   `Layer4Prediction`, `B3EnsembleReview`.

2. **LLMSchema** — a JSON Schema wrapper for callers who prefer the
   industry-standard JSON Schema spec. Instantiate with a dict and call
   `.validate(d)` for the same `(ok, err, instance_dict)` triple.

Both styles plug into `guardrailed_llm_call` because the orchestrator only
relies on the `.validate()` shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

try:
    import jsonschema  # type: ignore
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# MERGE_WITH(<token>) where <token> is a class-id-ish identifier
_MERGE_WITH_RE = re.compile(r"^MERGE_WITH\(([A-Za-z0-9_.\-]+)\)$")


def _require_keys(d: dict, required: list[str]) -> str | None:
    """Return error message if required keys missing, else None."""
    if not isinstance(d, dict):
        return f"expected object, got {type(d).__name__}"
    missing = [k for k in required if k not in d]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    return None


def _check_type(value: Any, name: str, expected: type | tuple[type, ...]) -> str | None:
    """Return error message if value not of expected type, else None.

    Note: bool is a subclass of int, so we reject bool when expecting int.
    """
    if expected is int and isinstance(value, bool):
        return f"field '{name}' expected int, got bool"
    if isinstance(expected, tuple):
        if (int in expected or float in expected) and isinstance(value, bool):
            return f"field '{name}' expected {expected}, got bool"
    if not isinstance(value, expected):
        exp_name = (
            expected.__name__
            if isinstance(expected, type)
            else "/".join(t.__name__ for t in expected)
        )
        return f"field '{name}' expected {exp_name}, got {type(value).__name__}"
    return None


# ---------------------------------------------------------------------------
# JSON Schema wrapper (new public API)
# ---------------------------------------------------------------------------


class LLMSchema:
    """Generic JSON Schema wrapper compatible with guardrailed_llm_call.

    Example:
        >>> schema = LLMSchema({
        ...     "type": "object",
        ...     "properties": {
        ...         "verdict": {"type": "string", "enum": ["KEEP", "REJECT"]},
        ...         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        ...     },
        ...     "required": ["verdict", "confidence"],
        ... })
        >>> ok, err, inst = schema.validate({"verdict": "KEEP", "confidence": 0.9})
        >>> assert ok and inst == {"verdict": "KEEP", "confidence": 0.9}

    Notes:
      - The returned `instance` is just the validated dict (no class wrapping).
      - Requires `jsonschema>=4.0`; if not installed the constructor raises.
    """

    def __init__(self, schema: dict[str, Any]):
        if not _HAS_JSONSCHEMA:
            raise ImportError(
                "LLMSchema requires `jsonschema>=4.0`. "
                "Install with `pip install jsonschema` or `pip install guarded-llm[dev]`."
            )
        if not isinstance(schema, dict):
            raise TypeError(f"schema must be a dict, got {type(schema).__name__}")
        # Eagerly validate the meta-schema so misconfiguration surfaces early.
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.exceptions.SchemaError as e:
            raise ValueError(f"invalid JSON Schema: {e.message}") from e
        self._schema = schema
        self._validator = jsonschema.Draft202012Validator(schema)

    @property
    def schema(self) -> dict[str, Any]:
        return self._schema

    def validate(self, d: Any) -> tuple[bool, str | None, Any]:
        """Validate `d` against this schema.

        Returns (ok, error_message_or_none, validated_instance_or_none).
        """
        errors = sorted(self._validator.iter_errors(d), key=lambda e: list(e.absolute_path))
        if not errors:
            return True, None, d
        first = errors[0]
        path = ".".join(str(p) for p in first.absolute_path) or "<root>"
        msg = f"{path}: {first.message}"
        return False, msg, None


def validate_response(d: Any, schema: "LLMSchema | type") -> tuple[bool, str | None, Any]:
    """Validate a parsed dict against either an LLMSchema or a dataclass schema class."""
    if isinstance(schema, LLMSchema):
        return schema.validate(d)
    if hasattr(schema, "validate"):
        return schema.validate(d)
    return False, f"schema {schema!r} has no .validate() method", None


# ---------------------------------------------------------------------------
# Legacy dataclass schemas (used by structural-isomorphism V4 pipeline)
# ---------------------------------------------------------------------------


@dataclass
class Layer3CriticVerdict:
    """B1 critic pass output per class.

    review_verdict: "KEEP" | "SPLIT" | "REJECT" | "MERGE_WITH(<other_class_id>)"
    confidence:     "low" | "medium" | "high"
    """

    class_id: str
    review_verdict: str
    confidence: str
    flagged_count: int
    reasoning: str

    REVIEW_VERDICTS: tuple[str, ...] = field(
        default=("KEEP", "SPLIT", "REJECT"), init=False, repr=False
    )
    CONFIDENCES: tuple[str, ...] = field(
        default=("low", "medium", "high"), init=False, repr=False
    )

    @classmethod
    def validate(cls, d: Any) -> tuple[bool, str | None, "Layer3CriticVerdict | None"]:
        err = _require_keys(
            d,
            ["class_id", "review_verdict", "confidence", "flagged_count", "reasoning"],
        )
        if err:
            return False, err, None

        for k in ("class_id", "review_verdict", "confidence", "reasoning"):
            e = _check_type(d[k], k, str)
            if e:
                return False, e, None

        e = _check_type(d["flagged_count"], "flagged_count", int)
        if e:
            return False, e, None
        if d["flagged_count"] < 0:
            return False, "field 'flagged_count' must be >= 0", None

        verdict = d["review_verdict"]
        valid_verdicts = ("KEEP", "SPLIT", "REJECT")
        if verdict not in valid_verdicts and not _MERGE_WITH_RE.match(verdict):
            return (
                False,
                f"field 'review_verdict' must be one of {valid_verdicts} "
                f"or 'MERGE_WITH(<class_id>)'; got '{verdict}'",
                None,
            )

        if d["confidence"] not in ("low", "medium", "high"):
            return (
                False,
                f"field 'confidence' must be one of (low, medium, high); "
                f"got '{d['confidence']}'",
                None,
            )

        return (
            True,
            None,
            cls(
                class_id=d["class_id"],
                review_verdict=verdict,
                confidence=d["confidence"],
                flagged_count=d["flagged_count"],
                reasoning=d["reasoning"],
            ),
        )


@dataclass
class Layer4Prediction:
    """A predicted observation in a target system."""

    class_id: str
    target_system: str
    physical_quantity: str
    predicted_band: list[float]
    evidence_url: str | None = None
    journal_target: str | None = None

    @classmethod
    def validate(cls, d: Any) -> tuple[bool, str | None, "Layer4Prediction | None"]:
        err = _require_keys(
            d,
            ["class_id", "target_system", "physical_quantity", "predicted_band"],
        )
        if err:
            return False, err, None

        for k in ("class_id", "target_system", "physical_quantity"):
            e = _check_type(d[k], k, str)
            if e:
                return False, e, None

        band = d["predicted_band"]
        if not isinstance(band, list):
            return (
                False,
                f"field 'predicted_band' expected list, got {type(band).__name__}",
                None,
            )
        if len(band) != 2:
            return (
                False,
                f"field 'predicted_band' must be [low, high] (2 elements); got len={len(band)}",
                None,
            )
        for i, v in enumerate(band):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return (
                    False,
                    f"field 'predicted_band[{i}]' expected number, got {type(v).__name__}",
                    None,
                )
        low, high = float(band[0]), float(band[1])
        if low > high:
            return (
                False,
                f"field 'predicted_band' requires low <= high; got [{low}, {high}]",
                None,
            )

        evidence_url = d.get("evidence_url")
        if evidence_url is not None and not isinstance(evidence_url, str):
            return (
                False,
                f"field 'evidence_url' expected str or null, got {type(evidence_url).__name__}",
                None,
            )
        journal_target = d.get("journal_target")
        if journal_target is not None and not isinstance(journal_target, str):
            return (
                False,
                f"field 'journal_target' expected str or null, got {type(journal_target).__name__}",
                None,
            )

        return (
            True,
            None,
            cls(
                class_id=d["class_id"],
                target_system=d["target_system"],
                physical_quantity=d["physical_quantity"],
                predicted_band=[low, high],
                evidence_url=evidence_url,
                journal_target=journal_target,
            ),
        )


@dataclass
class B3EnsembleReview:
    """One model's verdict on one class in an N-model ensemble vote."""

    class_id: str
    model_id: str
    verdict: str  # KEEP / REJECT / UNCLEAR
    confidence: float  # 0.0 - 1.0
    rationale: str

    VERDICTS: tuple[str, ...] = field(
        default=("KEEP", "REJECT", "UNCLEAR"), init=False, repr=False
    )

    @classmethod
    def validate(cls, d: Any) -> tuple[bool, str | None, "B3EnsembleReview | None"]:
        err = _require_keys(
            d, ["class_id", "model_id", "verdict", "confidence", "rationale"]
        )
        if err:
            return False, err, None

        for k in ("class_id", "model_id", "verdict", "rationale"):
            e = _check_type(d[k], k, str)
            if e:
                return False, e, None

        conf = d["confidence"]
        if isinstance(conf, bool) or not isinstance(conf, (int, float)):
            return (
                False,
                f"field 'confidence' expected number, got {type(conf).__name__}",
                None,
            )
        conf = float(conf)
        if not (0.0 <= conf <= 1.0):
            return (
                False,
                f"field 'confidence' must be in [0.0, 1.0]; got {conf}",
                None,
            )

        valid = ("KEEP", "REJECT", "UNCLEAR")
        if d["verdict"] not in valid:
            return (
                False,
                f"field 'verdict' must be one of {valid}; got '{d['verdict']}'",
                None,
            )

        return (
            True,
            None,
            cls(
                class_id=d["class_id"],
                model_id=d["model_id"],
                verdict=d["verdict"],
                confidence=conf,
                rationale=d["rationale"],
            ),
        )


# ---------------------------------------------------------------------------
# Dispatch helper (legacy name; kept for backwards compat with v4/lib path)
# ---------------------------------------------------------------------------


def validate(d: Any, schema_cls: type) -> tuple[bool, str | None, Any]:
    """Dispatch to schema_cls.validate(d). Convenience wrapper."""
    return validate_response(d, schema_cls)


__all__ = [
    "LLMSchema",
    "validate_response",
    "Layer3CriticVerdict",
    "Layer4Prediction",
    "B3EnsembleReview",
    "validate",
]
