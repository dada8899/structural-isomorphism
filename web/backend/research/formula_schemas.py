"""Unwired D2 inputs/results. Display text is never executable mathematics."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
import hashlib
import json
import re
import unicodedata
from uuid import UUID


class FormulaInputError(ValueError):
    pass


class FormulaLimit(FormulaInputError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def fields(data, required, optional=()):
    if (type(data) is not dict or len(data) > len(required) + len(optional)
            or not set(required) <= set(data) or set(data) - set(required) - set(optional)):
        raise FormulaInputError("unknown or missing fields")


def bounded(value, cap, minimum=1):
    if type(value) is not str or not minimum <= len(value) <= cap or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\t\n" for c in value):
        raise FormulaInputError("invalid bounded text")
    return value


def integer(value, maximum=2147483647, minimum=1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise FormulaInputError("strict bounded integer required")
    return value


def uuid(value):
    if type(value) is not str or len(value) != 36:
        raise FormulaInputError("UUID required")
    try:
        if str(UUID(value, version=4)) != value:
            raise ValueError()
    except ValueError:
        raise FormulaInputError("canonical UUID4 required") from None
    return value


def name(value):
    if type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value) is None:
        raise FormulaInputError("ASCII symbol required")
    return value


def decimal_text(value):
    # Bound spelling and exponent BEFORE Decimal/Fraction constructs integers.
    if type(value) is not str or len(value) > 64 or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?", value) is None:
        raise FormulaInputError("bounded finite decimal string required")
    exponent = re.search(r"[eE]([+-]?[0-9]+)$", value)
    if exponent and abs(int(exponent.group(1))) > 64:
        raise FormulaLimit("decimal exponent limit")
    d = Decimal(value)
    digits = ''.join(map(str, d.as_tuple().digits)).lstrip('0').rstrip('0')
    if len(digits) > 18 or d != 0 and not -12 <= d.adjusted() <= 12:
        raise FormulaLimit("decimal magnitude or precision limit")
    if d == 0:
        return "0"
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 80, 999, -999
        return str(d.normalize())


def sequence(value, cap):
    if type(value) is not list:
        raise FormulaInputError("JSON array required")
    if len(value) > cap:
        raise FormulaLimit("array limit")
    return value


@dataclass(frozen=True)
class Node:
    op: str
    args: tuple[Node, ...] = ()
    value: str | int | None = None

    @classmethod
    def parse(cls, data, counter=None, depth=1):
        if counter is None:
            counter = [0]
        counter[0] += 1
        if depth > 16 or counter[0] > 128:
            raise FormulaLimit("AST limit")
        if type(data) is not dict or type(data.get("op")) is not str or len(data["op"]) > 16:
            raise FormulaInputError("typed AST node required")
        op = data["op"]
        if op in {"const", "symbol"}:
            key = "value" if op == "const" else "id"
            fields(data, ("op", key))
            return cls(op, value=decimal_text(data[key]) if op == "const" else name(data[key]))
        if op in {"neg", "exp"}:
            fields(data, ("op", "arg"))
            return cls(op, (cls.parse(data["arg"], counter, depth + 1),))
        if op in {"add", "sub", "mul", "div", "eq"}:
            if op == "eq" and depth != 1:
                raise FormulaInputError("equation is a root node only")
            fields(data, ("op", "left", "right"))
            return cls(op, tuple(cls.parse(data[k], counter, depth + 1) for k in ("left", "right")))
        if op == "pow_int":
            fields(data, ("op", "base", "exponent"))
            integer(data["exponent"], 2, -2)
            return cls(op, (cls.parse(data["base"], counter, depth + 1),), data["exponent"])
        if op == "derivative":
            fields(data, ("op", "state_symbol", "time_symbol", "order"))
            if type(data["order"]) is not int or data["order"] != 1:
                raise FormulaInputError("only formal first derivative allowed")
            return cls(op, (cls("symbol", value=name(data["state_symbol"])), cls("symbol", value=name(data["time_symbol"]))), 1)
        raise FormulaInputError("unsupported AST operation")

    def data(self):
        if self.op in {"const", "symbol"}:
            return {"op": self.op, "value" if self.op == "const" else "id": self.value}
        if self.op in {"neg", "exp"}:
            return {"op": self.op, "arg": self.args[0].data()}
        if self.op == "pow_int":
            return {"op": self.op, "base": self.args[0].data(), "exponent": self.value}
        if self.op == "derivative":
            return {"op": self.op, "state_symbol": self.args[0].value, "time_symbol": self.args[1].value, "order": 1}
        return {"op": self.op, "left": self.args[0].data(), "right": self.args[1].data()}


@dataclass(frozen=True)
class Symbol:
    id: str
    role: str
    unit_id: str
    quantity: str
    value: str | None

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "role", "unit_id", "quantity", "value"))
        return cls(name(data["id"]), name(data["role"]), bounded(data["unit_id"], 40),
                   bounded(data["quantity"], 40), None if data["value"] is None else decimal_text(data["value"]))


@dataclass(frozen=True)
class Condition:
    id: str
    statement: str
    declared_satisfied: bool | None

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "statement", "declared_satisfied"))
        if data["declared_satisfied"] is not None and type(data["declared_satisfied"]) is not bool:
            raise FormulaInputError("strict declaration required")
        return cls(name(data["id"]), bounded(data["statement"], 400), data["declared_satisfied"])


@dataclass(frozen=True)
class InitialValue:
    state_symbol: str
    at_time: str
    value: str | None
    declared_satisfied: bool | None

    @classmethod
    def parse(cls, data):
        fields(data, ("state_symbol", "at_time", "value", "declared_satisfied"))
        if data["declared_satisfied"] is not None and type(data["declared_satisfied"]) is not bool:
            raise FormulaInputError("strict initial condition required")
        return cls(name(data["state_symbol"]), decimal_text(data["at_time"]),
                   None if data["value"] is None else decimal_text(data["value"]), data["declared_satisfied"])


@dataclass(frozen=True)
class SourceRef:
    id: str
    revision: int
    content_digest: str
    provenance: str
    locator: str

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "revision", "content_digest", "provenance", "locator"))
        if type(data["content_digest"]) is not str or re.fullmatch(r"[a-f0-9]{64}", data["content_digest"]) is None:
            raise FormulaInputError("source digest required")
        if type(data["provenance"]) is not str or len(data["provenance"]) > 32 or data["provenance"] not in {"curated_reference", "product_excerpt"}:
            raise FormulaInputError("unsupported source provenance")
        return cls(uuid(data["id"]), integer(data["revision"]), data["content_digest"], data["provenance"], bounded(data["locator"], 300))


@dataclass(frozen=True)
class FormulaInput:
    id: str
    revision: int
    family: str
    template_id: str
    original_display: str
    expression: Node
    symbols: tuple[Symbol, ...]
    assumptions: tuple[Condition, ...]
    initial_conditions: tuple[InitialValue, ...]
    boundary_conditions: tuple[Condition, ...]
    source_refs: tuple[SourceRef, ...]
    measure_scope: str

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "revision", "family", "template_id", "original_display", "expression", "symbols", "assumptions", "initial_conditions", "boundary_conditions", "source_refs", "measure_scope"))
        symbols = tuple(Symbol.parse(v) for v in sequence(data["symbols"], 12))
        if len({v.id for v in symbols}) != len(symbols) or len({v.role for v in symbols}) != len(symbols):
            raise FormulaInputError("symbol IDs and role mapping must be bijective")
        assumptions = tuple(Condition.parse(v) for v in sequence(data["assumptions"], 24))
        boundaries = tuple(Condition.parse(v) for v in sequence(data["boundary_conditions"], 24))
        initials = tuple(InitialValue.parse(v) for v in sequence(data["initial_conditions"], 1))
        if len(assumptions) + len(boundaries) + len(initials) > 24:
            raise FormulaLimit("condition limit")
        if len({v.id for v in assumptions + boundaries}) != len(assumptions + boundaries):
            raise FormulaInputError("duplicate condition")
        sources = tuple(SourceRef.parse(v) for v in sequence(data["source_refs"], 20))
        if len({s.id for s in sources}) != len(sources):
            raise FormulaInputError("duplicate source")
        return cls(uuid(data["id"]), integer(data["revision"]), bounded(data["family"], 40), bounded(data["template_id"], 40),
                   bounded(data["original_display"], 2048), Node.parse(data["expression"]), symbols, assumptions, initials, boundaries,
                   sources, bounded(data["measure_scope"], 20))

    def data(self):
        result = asdict(self)
        result["expression"] = self.expression.data()
        return json.loads(canonical(result))


@dataclass(frozen=True)
class FormulaCheckInput:
    research_id: str
    input_revision: int
    task_id: str
    attempt: int
    comparison_scope: str
    left: FormulaInput
    right: FormulaInput | None
    requested_checks: tuple[str, ...]
    sample_points: tuple[str, ...]

    @classmethod
    def parse(cls, data):
        fields(data, ("research_id", "input_revision", "task_id", "attempt", "comparison_scope", "left", "right", "requested_checks", "sample_points"))
        if type(data["comparison_scope"]) is not str or len(data["comparison_scope"]) > 24 or data["comparison_scope"] not in {"expression", "equation_form", "initial_value_problem"}:
            raise FormulaInputError("explicit comparison scope required")
        checks = sequence(data["requested_checks"], 4)
        if not checks or any(type(c) is not str or len(c) > 24 or c not in {"template", "dimensions", "canonical_transform", "bounded_numeric"} for c in checks) or len(set(checks)) != len(checks):
            raise FormulaInputError("fixed unique check kinds required")
        points = tuple(decimal_text(v) for v in sequence(data["sample_points"], 256))
        if len(set(points)) != len(points):
            raise FormulaInputError("duplicate sample point")
        if data["right"] is None and set(checks) - {"template", "dimensions"}:
            raise FormulaInputError("two sides required for comparison")
        left, right = FormulaInput.parse(data["left"]), None if data["right"] is None else FormulaInput.parse(data["right"])
        if right is not None and left.id == right.id and left.data() != right.data():
            raise FormulaInputError("immutable formula id cannot change version or content")
        sources = {}
        for form in (left, right):
            if form:
                for ref in form.source_refs:
                    if ref.id in sources and ref != sources[ref.id]:
                        raise FormulaInputError("source version conflict")
                    sources[ref.id] = ref
        return cls(uuid(data["research_id"]), integer(data["input_revision"]), uuid(data["task_id"]), integer(data["attempt"]), data["comparison_scope"], left, right, tuple(checks), points)

    def data(self):
        return {"research_id": self.research_id, "input_revision": self.input_revision, "task_id": self.task_id, "attempt": self.attempt,
                "comparison_scope": self.comparison_scope, "left": self.left.data(), "right": None if self.right is None else self.right.data(),
                "requested_checks": list(self.requested_checks), "sample_points": list(self.sample_points)}

    @property
    def input_digest(self):
        return digest(self.data())


@dataclass(frozen=True)
class CheckOutcome:
    check_kind: str
    status: str
    relation: str
    reason: str
    trace: tuple[dict, ...] = ()
    samples: tuple[dict, ...] = ()
    tolerance: dict | None = None


@dataclass(frozen=True)
class FormulaCheckResult:
    input_digest: str
    research_id: str
    input_revision: int
    task_id: str
    attempt: int
    comparison_scope: str
    policy_revision: str
    formula_refs: tuple[dict, ...]
    outcomes: tuple[CheckOutcome, ...]
    source_refs: tuple[SourceRef, ...]
    limitations: tuple[str, ...]
    resource_guard: str

    def data(self):
        result = json.loads(canonical(asdict(self)))
        result["output_digest"] = digest(result)
        return result
