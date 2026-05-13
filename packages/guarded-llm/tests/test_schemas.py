"""Tests for the LLMSchema (JSON Schema wrapper) public API."""

from __future__ import annotations

import pytest

from guarded_llm import LLMSchema, validate_response


@pytest.fixture
def simple_schema():
    return LLMSchema(
        {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["KEEP", "REJECT"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["verdict", "confidence"],
        }
    )


def test_schema_accepts_valid(simple_schema):
    ok, err, inst = simple_schema.validate({"verdict": "KEEP", "confidence": 0.9})
    assert ok
    assert err is None
    assert inst == {"verdict": "KEEP", "confidence": 0.9}


def test_schema_rejects_unknown_enum(simple_schema):
    ok, err, inst = simple_schema.validate({"verdict": "MAYBE", "confidence": 0.5})
    assert not ok
    assert "verdict" in err
    assert inst is None


def test_schema_rejects_out_of_range(simple_schema):
    ok, err, inst = simple_schema.validate({"verdict": "KEEP", "confidence": 1.5})
    assert not ok
    assert "confidence" in err


def test_schema_rejects_missing_required(simple_schema):
    ok, err, inst = simple_schema.validate({"verdict": "KEEP"})
    assert not ok
    assert "confidence" in err or "required" in err.lower()


def test_schema_rejects_wrong_root_type(simple_schema):
    ok, err, inst = simple_schema.validate("not an object")
    assert not ok
    assert err is not None


def test_schema_accepts_optional_field(simple_schema):
    ok, err, inst = simple_schema.validate(
        {"verdict": "REJECT", "confidence": 0.1, "tags": ["a", "b"]}
    )
    assert ok, err
    assert inst["tags"] == ["a", "b"]


def test_schema_rejects_invalid_schema_input():
    with pytest.raises(ValueError, match="invalid JSON Schema"):
        LLMSchema({"type": "not_a_real_type"})


def test_schema_rejects_non_dict_schema():
    with pytest.raises(TypeError):
        LLMSchema("not a dict")  # type: ignore[arg-type]


def test_validate_response_routes_llmschema(simple_schema):
    ok, err, inst = validate_response(
        {"verdict": "KEEP", "confidence": 0.9}, simple_schema
    )
    assert ok, err
    assert inst["verdict"] == "KEEP"


def test_validate_response_routes_dataclass_schema():
    from guarded_llm import Layer3CriticVerdict

    ok, err, inst = validate_response(
        {
            "class_id": "x",
            "review_verdict": "KEEP",
            "confidence": "high",
            "flagged_count": 0,
            "reasoning": "ok",
        },
        Layer3CriticVerdict,
    )
    assert ok, err
    assert inst.class_id == "x"


def test_validate_response_rejects_bad_schema_arg():
    class NotASchema:
        pass

    ok, err, inst = validate_response({}, NotASchema)
    assert not ok
    assert "validate" in err


def test_schema_property_exposes_dict():
    s = LLMSchema({"type": "object", "properties": {"a": {"type": "string"}}})
    assert s.schema == {"type": "object", "properties": {"a": {"type": "string"}}}


def test_nested_object_validation():
    s = LLMSchema(
        {
            "type": "object",
            "properties": {
                "outer": {
                    "type": "object",
                    "properties": {"inner": {"type": "integer", "minimum": 0}},
                    "required": ["inner"],
                },
            },
            "required": ["outer"],
        }
    )
    ok, err, inst = s.validate({"outer": {"inner": 5}})
    assert ok
    ok, err, inst = s.validate({"outer": {"inner": -1}})
    assert not ok
    assert "inner" in err
