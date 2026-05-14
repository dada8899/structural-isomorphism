"""Tests for the Pydantic-backed SchemaValidator."""

from __future__ import annotations

import pytest

pydantic = pytest.importorskip("pydantic")
from pydantic import BaseModel, Field  # noqa: E402

from guarded_llm import SchemaValidator  # noqa: E402


class Verdict(BaseModel):
    verdict: str
    confidence: float = Field(ge=0.0, le=1.0)


def test_validator_accepts_valid():
    v = SchemaValidator(Verdict)
    ok, err, inst = v.validate({"verdict": "KEEP", "confidence": 0.9})
    assert ok, err
    assert inst.verdict == "KEEP"
    assert inst.confidence == pytest.approx(0.9)


def test_validator_rejects_out_of_range():
    v = SchemaValidator(Verdict)
    ok, err, inst = v.validate({"verdict": "KEEP", "confidence": 1.5})
    assert not ok
    assert "confidence" in err
    assert inst is None


def test_validator_rejects_missing_required():
    v = SchemaValidator(Verdict)
    ok, err, inst = v.validate({"verdict": "KEEP"})
    assert not ok
    assert "confidence" in err


def test_validator_rejects_bad_type():
    v = SchemaValidator(Verdict)
    ok, err, inst = v.validate({"verdict": "KEEP", "confidence": "not-a-number"})
    assert not ok


def test_validator_init_rejects_non_model():
    class NotAModel:
        pass

    with pytest.raises(TypeError):
        SchemaValidator(NotAModel)


def test_validator_init_rejects_instance_instead_of_class():
    with pytest.raises(TypeError):
        SchemaValidator(Verdict(verdict="KEEP", confidence=0.5))  # type: ignore[arg-type]


def test_model_property_returns_class():
    v = SchemaValidator(Verdict)
    assert v.model is Verdict


def test_validator_handles_extra_fields_per_model_config():
    """Default Pydantic v2: extra fields are silently ignored."""
    v = SchemaValidator(Verdict)
    ok, err, inst = v.validate(
        {"verdict": "KEEP", "confidence": 0.5, "extra_junk": 999}
    )
    assert ok, err
    assert inst.verdict == "KEEP"
