"""W11-A coverage for guarded_llm.validator (lines 28-31, 52, 81, 83-84)."""
from __future__ import annotations

import pytest

from guarded_llm.validator import SchemaValidator


# Need pydantic to test the happy path
try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


@pytest.mark.skipif(not HAS_PYDANTIC, reason="pydantic not installed")
class TestSchemaValidator:
    def test_init_rejects_non_basemodel(self):
        with pytest.raises(TypeError) as exc:
            SchemaValidator(int)
        assert "BaseModel" in str(exc.value)

    def test_init_rejects_basemodel_instance(self):
        """Passing an instance (not class) is rejected."""

        class Out(BaseModel):
            x: int

        with pytest.raises(TypeError):
            SchemaValidator(Out(x=1))  # type: ignore[arg-type]

    def test_validate_returns_instance_on_success(self):
        class Out(BaseModel):
            verdict: str
            confidence: float

        v = SchemaValidator(Out)
        ok, err, inst = v.validate({"verdict": "KEEP", "confidence": 0.9})
        assert ok is True
        assert err is None
        assert isinstance(inst, Out)
        assert inst.verdict == "KEEP"

    def test_validate_returns_error_on_missing_field(self):
        class Out(BaseModel):
            verdict: str
            confidence: float

        v = SchemaValidator(Out)
        ok, err, inst = v.validate({"verdict": "KEEP"})  # missing confidence
        assert ok is False
        assert err is not None
        assert "confidence" in err
        assert inst is None

    def test_validate_returns_error_on_type_mismatch(self):
        class Out(BaseModel):
            confidence: float

        v = SchemaValidator(Out)
        ok, err, inst = v.validate({"confidence": "not-a-number"})
        assert ok is False
        assert err is not None
        assert inst is None

    def test_validate_nested_error_path(self):
        """Path joining with '.' for nested fields."""

        class Inner(BaseModel):
            v: int

        class Outer(BaseModel):
            inner: Inner

        v = SchemaValidator(Outer)
        ok, err, inst = v.validate({"inner": {"v": "bad"}})
        assert ok is False
        assert err is not None
        # path includes "inner.v"
        assert "inner" in err or "v" in err

    def test_validate_non_dict_input(self):
        """Non-dict input → pydantic raises → caught as error string."""

        class Out(BaseModel):
            x: int

        v = SchemaValidator(Out)
        ok, err, inst = v.validate("not a dict")
        assert ok is False
        # Either ValidationError-shaped or fallback "pydantic error:"
        assert err is not None
        assert inst is None

    def test_validate_completely_unexpected_exception(self):
        """Force a non-ValidationError to hit line 83-84.

        Subclass BaseModel and override model_validate to raise something else.
        """

        class WeirdModel(BaseModel):
            x: int

            @classmethod
            def model_validate(cls, *a, **kw):
                raise RuntimeError("totally unexpected")

        v = SchemaValidator(WeirdModel)
        ok, err, inst = v.validate({"x": 1})
        assert ok is False
        assert err is not None
        assert "pydantic error" in err
        assert "totally unexpected" in err
        assert inst is None

    def test_validate_validation_error_with_no_errors_list(self):
        """If errors() returns [], fallback to str(e) — line 81."""
        from pydantic import ValidationError

        class WeirdEmpty(BaseModel):
            x: int

            @classmethod
            def model_validate(cls, *a, **kw):
                # Construct a fake ValidationError-like obj
                class FakeErr(Exception):
                    def errors(self):
                        return []

                raise FakeErr("manual")

        v = SchemaValidator(WeirdEmpty)
        ok, err, inst = v.validate({"x": 1})
        assert ok is False
        # FakeErr is not ValidationError so goes to general except
        assert err is not None

    def test_model_property(self):
        class Out(BaseModel):
            x: int

        v = SchemaValidator(Out)
        assert v.model is Out


# Test the no-pydantic branch by simulating ImportError
def test_no_pydantic_import_error_path(monkeypatch):
    """Lines 28-31, 52: When pydantic is not available, init raises ImportError."""
    import guarded_llm.validator as mod

    # Simulate pydantic being unavailable
    orig = mod._HAS_PYDANTIC
    monkeypatch.setattr(mod, "_HAS_PYDANTIC", False)
    try:
        with pytest.raises(ImportError) as exc:
            mod.SchemaValidator(object)
        assert "pydantic" in str(exc.value).lower()
    finally:
        monkeypatch.setattr(mod, "_HAS_PYDANTIC", orig)
