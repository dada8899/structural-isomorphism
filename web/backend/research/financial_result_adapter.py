"""Pure FinancialResult consumer boundary; no DB, ACL grant, network or signing.

Core must load server-owned registry/expectation records after current ACL checks,
then recheck ACL/CAS in its own write transaction. Nothing here grants access.
"""
from dataclasses import asdict, dataclass, fields as dataclass_fields
from datetime import datetime
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN
import hashlib
import json
import re
import time
from typing import Callable

from .financial_evaluator import FinancialSnapshot, evaluate_financial
from .financial_policy import (POLICY, YEARS, MAX_JSON, MAX_ABS, FinancialError,
                               FinancialResourceLimit, canonical, digest, arithmetic_context)
from .financial_schemas import (SourceRegistry, SourceSnapshot, FinancialObservation,
    FinancialAmount, HistoricalFX, Period, FinancialRequest, uid, hash_value, fields)

PRODUCER_COMMIT = "7e0780ba30d163180efc5584e65ef138b1571f27"
RESULT_TYPE = "financial_scenario_v1"
_monotonic: Callable[[], float] = time.monotonic
_MAX_NODES, _MAX_DEPTH = 20000, 32


class _Budget:
    def __init__(self):
        self.deadline = _monotonic() + 2.0

    def check(self):
        if _monotonic() > self.deadline:
            raise FinancialResourceLimit("adapter cooperative deadline")


def _revision(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise FinancialError("strict revision required")


def _bounded(value, cap=MAX_JSON, *, budget=None):
    """Limit shape/string bytes before recursively serializing caller objects."""
    budget = budget or _Budget()
    stack, count, string_bytes = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > _MAX_NODES or depth > _MAX_DEPTH:
            raise FinancialResourceLimit("JSON shape limit")
        budget.check()
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise FinancialError("JSON string key required")
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(item) in (list, tuple):
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            try:
                string_bytes += len(item.encode("utf-8"))
            except UnicodeError:
                raise FinancialError("invalid Unicode") from None
            if string_bytes > cap:
                raise FinancialResourceLimit("JSON byte limit")
        elif item is not None and type(item) not in (int, bool):
            raise FinancialError("strict JSON primitives required")
        elif type(item) is int and item.bit_length() > 64:
            raise FinancialResourceLimit("JSON integer limit")
    raw = canonical(value)
    if len(raw.encode("utf-8")) > cap:
        raise FinancialResourceLimit("JSON byte limit")
    budget.check()
    return raw


def _parse(raw, cap=MAX_JSON, *, budget=None):
    if type(raw) is not str or len(raw) > cap:
        raise FinancialResourceLimit("JSON byte limit")
    try:
        if len(raw.encode("utf-8")) > cap:
            raise FinancialResourceLimit("JSON byte limit")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise FinancialError("duplicate JSON key")
                result[key] = value
            return result
        def rejected(_):
            raise FinancialError("non-integer JSON number")
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=rejected,
                           parse_constant=rejected,
                           parse_int=lambda value: int(value) if len(value.lstrip("-")) <= 20 else rejected(value))
        _bounded(value, cap, budget=budget)
        return value
    except (RecursionError, UnicodeError, json.JSONDecodeError):
        raise FinancialError("invalid bounded JSON") from None


@dataclass(frozen=True)
class FinancialRegistryRef:
    id: str
    revision: int
    digest: str

    def __post_init__(self):
        uid(self.id); _revision(self.revision); hash_value(self.digest)


@dataclass(frozen=True)
class SourceRecordRef:
    id: str
    revision: int

    def __post_init__(self):
        uid(self.id); _revision(self.revision)


@dataclass(frozen=True)
class FinancialSourceBinding:
    financial_snapshot_id: str
    registry_ref: FinancialRegistryRef
    snapshot_digest: str
    source_record_ref: SourceRecordRef | None = None

    def __post_init__(self):
        uid(self.financial_snapshot_id); hash_value(self.snapshot_digest)
        if type(self.registry_ref) is not FinancialRegistryRef or (
            self.source_record_ref is not None and type(self.source_record_ref) is not SourceRecordRef
        ):
            raise FinancialError("typed source mapping required")


@dataclass(frozen=True)
class FinancialResultBinding:
    research_id: str
    input_revision: int
    input_digest: str  # Research ProblemRevision digest, NOT executor input_digest.
    request_digest: str  # Complete POST body, including expected research version.
    registry_ref: FinancialRegistryRef
    policy_revision: str = POLICY
    producer_commit: str = PRODUCER_COMMIT

    def __post_init__(self):
        uid(self.research_id); _revision(self.input_revision)
        hash_value(self.input_digest); hash_value(self.request_digest)
        if (type(self.registry_ref) is not FinancialRegistryRef or self.policy_revision != POLICY
                or self.producer_commit != PRODUCER_COMMIT):
            raise FinancialError("unsupported financial binding")


@dataclass(frozen=True)
class ServerFinancialRegistryRecord:
    """Core-supplied input, not an authorization capability or HTTP DTO."""
    research_id: str
    ref: FinancialRegistryRef
    registry: SourceRegistry
    source_bindings: tuple[FinancialSourceBinding, ...]


@dataclass(frozen=True, init=False)
class ResolvedFinancialRegistry:
    research_id: str
    ref: FinancialRegistryRef
    _registry_json: str
    _mapping_json: str

    def __init__(self, *args, **kwargs):
        raise TypeError("use server registry resolver; no JSON trust constructor")


@dataclass(frozen=True, init=False)
class ServerFinancialCandidate:
    binding: FinancialResultBinding
    canonical_snapshot: str
    snapshot_digest: str
    _operation_json: str
    u2_goal_status: str

    def __init__(self, *args, **kwargs):
        raise TypeError("only controlled financial evaluation creates a candidate")

    def _storage_fields(self):
        """Unsigned content for Core's later ACL/CAS writer, never an auth proof."""
        return {"type": RESULT_TYPE, "binding": asdict(self.binding),
                "canonical_snapshot": self.canonical_snapshot,
                "snapshot_digest": self.snapshot_digest,
                "calculation_status": "calculated_under_assumptions",
                "u2_goal_status": self.u2_goal_status, "model_analysis_ran": False}


def _internal(cls, **values):
    value = object.__new__(cls)
    for name, item in values.items():
        object.__setattr__(value, name, item)
    return value


def _record(cls, value):
    fields(value, tuple(f.name for f in dataclass_fields(cls)))
    return cls(**value)


def _registry(data):
    fields(data, ("sources", "observations", "historical_fx"))
    if any(type(data[k]) is not list for k in data):
        raise FinancialError("registry arrays required")
    observations = []
    for item in data["observations"]:
        item = dict(item)
        item["period"] = _record(Period, item["period"])
        item["amount"] = _record(FinancialAmount, item["amount"])
        item["source_refs"] = tuple(item["source_refs"])
        item["alternative_refs"] = tuple(item["alternative_refs"])
        observations.append(_record(FinancialObservation, item))
    sources = []
    for item in data["sources"]:
        item = dict(item); item["source_chain"] = tuple(item["source_chain"])
        sources.append(_record(SourceSnapshot, item))
    rates = []
    for item in data["historical_fx"]:
        item = dict(item); item["period"] = _record(Period, item["period"])
        item["source_refs"] = tuple(item["source_refs"])
        rates.append(_record(HistoricalFX, item))
    return SourceRegistry(tuple(sources), tuple(observations), tuple(rates))


def resolve_financial_registry(binding, ref, server_record):
    """Pure resolver called AFTER Core loads and authorizes a server record.

    It does not inspect accounts, validate grants or claim source authenticity.
    Core must recheck those in commit/read; a dataclass alone grants nothing.
    """
    if (type(binding) is not FinancialResultBinding or type(ref) is not FinancialRegistryRef
            or type(server_record) is not ServerFinancialRegistryRecord
            or server_record.research_id != binding.research_id
            or server_record.ref != ref or binding.registry_ref != ref
            or type(server_record.registry) is not SourceRegistry
            or type(server_record.source_bindings) is not tuple):
        raise FinancialError("server registry binding mismatch")
    budget = _Budget()
    raw = _bounded(server_record.registry.data(), budget=budget)
    registry = _registry(_parse(raw, budget=budget))
    if digest(registry.data()) != ref.digest:
        raise FinancialError("registry digest mismatch")
    mapped = {}
    sources = {s.id: s for s in registry.sources}
    for link in server_record.source_bindings:
        if (type(link) is not FinancialSourceBinding or link.registry_ref != ref
                or link.financial_snapshot_id in mapped or link.financial_snapshot_id not in sources
                or link.snapshot_digest != digest(asdict(sources[link.financial_snapshot_id]))):
            raise FinancialError("source mapping mismatch")
        mapped[link.financial_snapshot_id] = asdict(link)
    if set(mapped) != set(sources):
        raise FinancialError("complete source mapping required")
    mappings = _bounded(list(mapped.values()), budget=budget)
    return _internal(ResolvedFinancialRegistry, research_id=binding.research_id,
                     ref=ref, _registry_json=raw, _mapping_json=mappings)


def _operation(data, binding, *, budget):
    raw = _bounded(data, 64 * 1024, budget=budget)
    operation = _parse(raw, 64 * 1024, budget=budget)
    fields(operation, ("input_revision", "expected_research_version", "registry_ref", "request"))
    _revision(operation["input_revision"]); _revision(operation["expected_research_version"])
    registry_ref = _record(FinancialRegistryRef, operation["registry_ref"])
    if (operation["input_revision"] != binding.input_revision
            or registry_ref != binding.registry_ref
            or digest(operation) != binding.request_digest):
        raise FinancialError("operation request binding mismatch")
    FinancialRequest.parse(operation["request"])
    return operation, raw


def _resolved_registry(resolved, binding, budget):
    if (type(resolved) is not ResolvedFinancialRegistry or resolved.ref != binding.registry_ref
            or resolved.research_id != binding.research_id):
        raise FinancialError("resolved registry scope mismatch")
    data = _parse(resolved._registry_json, budget=budget)
    if digest(data) != binding.registry_ref.digest:
        raise FinancialError("resolved registry changed")
    return _registry(data)


def _decimal_output(value):
    if (type(value) is not str or len(value) > 256
            or not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]{1,3})?", value)):
        raise FinancialError("invalid derived decimal")
    number = Decimal(value)
    if not number.is_finite() or number.copy_abs() > MAX_ABS or len(number.as_tuple().digits) > 50 or abs(number.as_tuple().exponent) > 249:
        raise FinancialError("derived decimal outside policy")
    return number


def _cell(value, *, scoped, currency, observation_ids, parameter_ids, expected_unit):
    required = {"raw_value", "display", "observation_refs", "parameter_refs"}
    optional = {"unit", "basis", "reasons"} if scoped else set()
    if not scoped:
        required |= {"currency", "unit", "basis", "reasons"}
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        raise FinancialError("invalid cell shape")
    if scoped and "currency" in value:
        raise FinancialError("scoped currency must be inherited")
    unit = value.get("unit", "million")
    if unit != expected_unit or (not scoped and value["currency"] != (None if unit == "ratio" else currency)):
        raise FinancialError("cell currency or unit mismatch")
    basis = value.get("basis", "derived_conditional")
    if basis not in {"derived_conditional", "disclosed", "media_estimate", "scenario_assumption", "missing", "conflicted"}:
        raise FinancialError("unknown cell basis")
    for key, allowed in (("observation_refs", observation_ids), ("parameter_refs", parameter_ids)):
        refs = value[key]
        if type(refs) is not list or any(type(r) is not str for r in refs) or len(refs) != len(set(refs)) or set(refs) - allowed:
            raise FinancialError("cell reference outside input")
    reasons = value.get("reasons", [])
    if type(reasons) is not list or any(type(r) is not str or len(r) > 1000 for r in reasons):
        raise FinancialError("invalid cell reasons")
    if value["raw_value"] is None:
        if value["display"] is not None or basis not in {"missing", "conflicted"}:
            raise FinancialError("missing amount is not zero")
    else:
        if basis in {"missing", "conflicted"}:
            raise FinancialError("missing basis with numeric value")
        raw = _decimal_output(value["raw_value"])
        with arithmetic_context() as context:
            context.prec = 80
            shown = raw.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        shown = format(Decimal(0) if shown == 0 else shown, ".6f")
        if value["display"] != shown:
            raise FinancialError("display differs from stored exact amount")


def _validate_snapshot(raw, registry, request, binding, budget):
    """Whitelist and references, not a second financial calculation or ACL proof."""
    data = _parse(raw, budget=budget)
    fields(data, ("policy_revision", "input_digest", "registry_digest", "target_currency",
        "amount_unit", "display_quantization", "calculation_precision", "request_snapshot",
        "registry_snapshot", "historical_context", "categories", "scenarios", "sensitivity",
        "operations_used", "qualifications", "decimal50_inexact_encountered"))
    if raw != canonical(data):
        raise FinancialError("snapshot is not canonical")
    # These are distinct domains; the Research input digest is deliberately not compared here.
    executor_input_digest = digest({"request": request.data(), "registry": registry.data()})
    if (data["input_digest"] != executor_input_digest or data["registry_digest"] != binding.registry_ref.digest
            or data["registry_snapshot"] != json.loads(canonical(registry.data())) or data["request_snapshot"] != request.data()
            or data["categories"] != list(request.data()["categories"])
            or data["policy_revision"] != POLICY or data["target_currency"] != request.target_currency
            or data["amount_unit"] != "million" or data["display_quantization"] != "6 decimals HALF_EVEN"
            or type(data["calculation_precision"]) is not int or data["calculation_precision"] != 50
            or type(data["decimal50_inexact_encountered"]) is not bool
            or type(data["operations_used"]) is not int or not 0 <= data["operations_used"] < 5000):
        raise FinancialError("snapshot input or policy binding mismatch")
    ids = {o.id for o in registry.observations} | {f.id for f in registry.historical_fx}
    params = {s.id + ":" + p.id for s in request.scenarios for p in s.parameters()}
    def cell(v, scoped, currency, unit="million"):
        budget.check()
        _cell(v, scoped=scoped, currency=currency, observation_ids=ids, parameter_ids=params, expected_unit=unit)
    base_currency = registry.observation(request.interim_revenue_ref).amount.currency
    expected_historic = [registry.observation(ref) for ref in (request.interim_revenue_ref,) + request.historical_context_refs]
    if type(data["historical_context"]) is not list or len(data["historical_context"]) != len(expected_historic):
        raise FinancialError("invalid historical context")
    for item, observation in zip(data["historical_context"], expected_historic):
        fields(item, ("observation", "target_value"))
        if item["observation"] != json.loads(canonical(asdict(observation))):
            raise FinancialError("historical observation changed")
        cell(item["target_value"], False, request.target_currency)
    if type(data["scenarios"]) is not list or len(data["scenarios"]) != len(request.scenarios):
        raise FinancialError("scenario count mismatch")
    for result, scenario in zip(data["scenarios"], request.scenarios):
        fields(result, ("id", "label", "accounting_basis", "bridge", "years", "parameter_basis", "exclusions", "qualification"))
        if (result["id"] != scenario.id or result["label"] != scenario.label
                or result["accounting_basis"] != scenario.accounting_basis
                or result["parameter_basis"] != "scenario_assumption"
                or result["exclusions"] != request.data()["scenarios"][list(request.scenarios).index(scenario)]["exclusions"]
                or result["qualification"] != ("source_linked_conditional_unreviewed" if all(p.source_refs for p in scenario.parameters()) else "mechanical_assumption_demonstration_not_validated_forecast")):
            raise FinancialError("scenario metadata mismatch")
        bridge = result["bridge"]
        fields(bridge, ("interim", "remaining_assumption", "target_interim", "target_remaining", "qualification"))
        if bridge["qualification"] != "2026E, never annualized historical actual":
            raise FinancialError("invalid bridge qualification")
        for key in ("interim", "remaining_assumption", "target_interim", "target_remaining"):
            cell(bridge[key], False, request.target_currency if key.startswith("target") else base_currency)
        if type(result["years"]) is not list or len(result["years"]) != 6:
            raise FinancialError("invalid horizon")
        for row, year in zip(result["years"], YEARS):
            fields(row, ("year", "period", "basis", "native_currency", "target_currency", "native", "target"))
            if (type(row["year"]) is not int or row["year"] != year or row["period"] != {"start":f"{year}-01-01","end":f"{year}-12-31","grain":"annual"}
                    or row["basis"] != ("bridge_estimate" if year == 2026 else "conditional_scenario")
                    or row["native_currency"] != base_currency or row["target_currency"] != request.target_currency):
                raise FinancialError("year scope mismatch")
            for kind, currency in (("native", base_currency), ("target", request.target_currency)):
                values = row[kind]
                if kind == "native" and base_currency == request.target_currency:
                    if values != {"same_as":"target"}: raise FinancialError("invalid same_as alias")
                    continue
                fields(values, ("revenue", "operating_profit", "net_profit", "cost_bridge", "composition"))
                for metric in ("revenue", "operating_profit", "net_profit"):
                    cell(values[metric], True, currency)
                if values["net_profit"]["raw_value"] is not None:
                    raise FinancialError("unsupported net profit projection")
                costs = values["cost_bridge"]
                if type(costs) is not list or len(costs) != len(scenario.costs):
                    raise FinancialError("cost bridge mismatch")
                for cost, expected in zip(costs, scenario.costs):
                    fields(cost, ("id", "kind", "coverage", "coverage_basis", "value"))
                    if any(cost[k] != v for k,v in {"id":expected.id,"kind":expected.kind,"coverage":list(expected.coverage),"coverage_basis":expected.coverage_basis}.items()):
                        raise FinancialError("cost scope mismatch")
                    cell(cost["value"], True, currency)
                composition = values["composition"]
                fields(composition, ("coverage", "rows", "rounding_delta_million", "scope"))
                if composition["coverage"] not in {"group_missing","undefined_zero_revenue","unallocated_only","partial","declared_scenario_partition_complete_not_audited"} or composition["scope"] != "unallocated includes all unmodelled revenue; missing named categories are not extra summands":
                    raise FinancialError("invalid composition scope")
                expected_categories = [c["id"] for c in request.categories if c["kind"] != "unallocated"] + [c["id"] for c in request.categories if c["kind"] == "unallocated"]
                if type(composition["rows"]) is not list or len(composition["rows"]) != len(expected_categories):
                    raise FinancialError("composition rows mismatch")
                for part, category in zip(composition["rows"], expected_categories):
                    fields(part, ("category_id", "amount", "share", "included_in_allocated_sum"))
                    if part["category_id"] != category or type(part["included_in_allocated_sum"]) is not bool or part["included_in_allocated_sum"] != (part["amount"].get("raw_value") is not None):
                        raise FinancialError("composition inclusion mismatch")
                    cell(part["amount"], True, currency); cell(part["share"], True, currency, "ratio")
                    if part["share"].get("unit") != "ratio": raise FinancialError("share is not an amount")
                if composition["rounding_delta_million"] is not None:
                    _decimal_output(composition["rounding_delta_million"])
    qualifications = ["bounded pure evaluator, not an OS sandbox or API/source-authenticity verification", "caller-controlled registry basis is not verified by this module", "all projected values conditional; no calibrated probabilities", "no historical operating margin or profit backfill", "missing net profit bridge remains missing"]
    if any(s.published_at is None or s.accessed_at is None for s in registry.sources):
        qualifications.append("source_publication_or_access_time_unknown")
    if any(o.evidence_basis == "conflicted" for o in registry.observations):
        qualifications.append("registry_contains_conflicts_not_averaged_or_silently_zeroed")
    if data["qualifications"] != qualifications:
        raise FinancialError("qualifications changed")
    _sensitivity(data["sensitivity"], request, registry, budget)
    return data


def _sensitivity(rows, request, registry, budget):
    expected = request.sensitivity
    if type(rows) is not list or len(rows) != (len(expected["points"]) if expected else 0):
        raise FinancialError("sensitivity scope mismatch")
    if not expected: return
    for row, point in zip(rows, expected["points"]):
        budget.check()
        fields(row, ("parameter_ref", "point", "case_input_digest", "years", "target_revenue", "target_operating_profit"))
        if row["parameter_ref"] != expected["scenario_id"]+":"+expected["parameter_id"] or row["point"] != point or row["years"] != list(YEARS):
            raise FinancialError("sensitivity metadata mismatch")
        variant = request.data(); variant["sensitivity"] = None
        def change(value):
            if type(value) is dict:
                for key, child in value.items():
                    if key == "value" and value.get("id") == expected["parameter_id"]: value[key] = point
                    else: change(child)
            elif type(value) is list:
                for child in value: change(child)
        for scenario in variant["scenarios"]:
            if scenario["id"] == expected["scenario_id"]: change(scenario)
        if row["case_input_digest"] != digest({"request":FinancialRequest.parse(variant).data(),"registry":registry.data()}):
            raise FinancialError("sensitivity input binding mismatch")
        for key in ("target_revenue", "target_operating_profit"):
            if type(row[key]) is not list or len(row[key]) != 6:
                raise FinancialError("sensitivity horizon mismatch")
            for value in row[key]:
                if value is not None: _decimal_output(value)


def _goal_status(data):
    # This pure adapter never grants A008 acceptance. Incomplete inputs are explicit.
    deficient = any(s["qualification"].startswith("mechanical_") for s in data["scenarios"])
    deficient |= any(row["target"][metric]["raw_value"] is None or row["target"]["composition"]["coverage"] in {"group_missing","undefined_zero_revenue","unallocated_only","partial"}
                     for s in data["scenarios"] for row in s["years"] for metric in ("revenue","operating_profit"))
    return "not_met" if deficient else "not_assessed"


def evaluate_financial_candidate(operation, resolved_registry, binding):
    if type(binding) is not FinancialResultBinding:
        raise FinancialError("server result binding required")
    budget = _Budget()
    operation, operation_json = _operation(operation, binding, budget=budget)
    registry = _resolved_registry(resolved_registry, binding, budget)
    request = FinancialRequest.parse(operation["request"])
    _bounded({"request":request.data(),"registry":registry.data()}, budget=budget)
    budget.check()
    snapshot = evaluate_financial(request.data(), registry)
    budget.check()
    data = _validate_snapshot(snapshot._canonical_json, registry, request, binding, budget)
    candidate = _internal(ServerFinancialCandidate, binding=binding,
        canonical_snapshot=snapshot._canonical_json, snapshot_digest=snapshot.digest,
        _operation_json=operation_json, u2_goal_status=_goal_status(data))
    # Metadata is added only by Core's later real commit. It must cap the full row too.
    _bounded(candidate._storage_fields(), budget=budget)
    return candidate


@dataclass(frozen=True)
class FinancialResultExpectation:
    """Core's separately loaded immutable row metadata, not client assertions."""
    id: str
    binding: FinancialResultBinding
    snapshot_digest: str
    created_at: str
    research_version_at_commit: int

    def __post_init__(self):
        uid(self.id); hash_value(self.snapshot_digest); _revision(self.research_version_at_commit)
        if type(self.binding) is not FinancialResultBinding or self.research_version_at_commit < 2:
            raise FinancialError("invalid saved result metadata")
        if type(self.created_at) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", self.created_at):
            raise FinancialError("strict UTC creation time required")
        try: datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
        except ValueError: raise FinancialError("invalid creation time") from None


def _verify_result(record, resolved_registry, expected, budget):
    if type(expected) is not FinancialResultExpectation:
        raise FinancialError("separate server result expectation required")
    fields(record, ("id", "type", "binding", "snapshot_digest", "canonical_snapshot", "calculation_status", "u2_goal_status", "model_analysis_ran", "created_at", "research_version_at_commit"))
    _bounded(record, budget=budget)
    for key, value in {"id":expected.id,"binding":asdict(expected.binding),"snapshot_digest":expected.snapshot_digest,"created_at":expected.created_at,"research_version_at_commit":expected.research_version_at_commit}.items():
        if canonical(record[key]) != canonical(value): raise FinancialError("saved metadata mismatch")
    if (record["type"] != RESULT_TYPE or record["calculation_status"] != "calculated_under_assumptions"
            or record["model_analysis_ran"] is not False or record["u2_goal_status"] not in {"not_met","not_assessed"}
            or type(record["canonical_snapshot"]) is not str
            or hashlib.sha256(record["canonical_snapshot"].encode()).hexdigest() != expected.snapshot_digest):
        raise FinancialError("saved result digest or kind mismatch")
    snapshot_data = _parse(record["canonical_snapshot"], budget=budget)
    # Local commits advance the research version by exactly one; no task is created.
    operation = {"input_revision":expected.binding.input_revision,
        "expected_research_version":expected.research_version_at_commit-1,
        "registry_ref":asdict(expected.binding.registry_ref),"request":snapshot_data.get("request_snapshot")}
    _operation(operation, expected.binding, budget=budget)
    registry = _resolved_registry(resolved_registry, expected.binding, budget)
    try:
        data = _validate_snapshot(record["canonical_snapshot"], registry,
                                  FinancialRequest.parse(operation["request"]), expected.binding, budget)
    except (KeyError, TypeError, AttributeError, IndexError, DecimalException):
        raise FinancialError("invalid stored financial structure") from None
    if record["u2_goal_status"] != _goal_status(data):
        raise FinancialError("saved qualification mismatch")
    return data


def prepare_financial_record(candidate, resolved_registry, *, result_id, created_at, research_version_at_commit):
    """Serialize a computed candidate only; no signature, authority or DB commit.

    Core supplies ID/time/version inside its own final ACL/CAS transaction and
    must persist the immutable expectation separately from snapshot bytes.
    """
    if type(candidate) is not ServerFinancialCandidate:
        raise FinancialError("computed server candidate required")
    expected = FinancialResultExpectation(result_id, candidate.binding,
        candidate.snapshot_digest, created_at, research_version_at_commit)
    record = {**candidate._storage_fields(), "id":result_id, "created_at":created_at,
              "research_version_at_commit":research_version_at_commit}
    _verify_result(record, resolved_registry, expected, _Budget())
    return json.loads(_bounded(record))


def project_financial_result(record, resolved_registry, expected, *, current_input_revision, view="summary"):
    """Validate persisted content then project; no recomputation, storage or ACL claim.

    Core must supply expectation from its authorized immutable metadata, never
    derive it from this untrusted record or a client digest/trusted flag.
    """
    if view not in {"summary","table","chart"}:
        raise FinancialError("unsupported financial view")
    _revision(current_input_revision)
    if type(expected) is not FinancialResultExpectation or current_input_revision < expected.binding.input_revision:
        raise FinancialError("current input revision mismatch")
    budget = _Budget()
    copied = _parse(_bounded(record, budget=budget), budget=budget)
    data = _verify_result(copied, resolved_registry, expected, budget)
    sources = [{k:v for k,v in s.items() if k != "retained_original_ref"} for s in data["registry_snapshot"]["sources"]]
    mappings = [{k:v for k,v in m.items() if k != "registry_ref"}
                for m in _parse(resolved_registry._mapping_json, budget=budget)]
    gap_codes = set()
    stack = [data]
    while stack:
        budget.check()
        item = stack.pop()
        if type(item) is dict:
            if "reasons" in item: gap_codes.update(item["reasons"])
            stack.extend(item.values())
        elif type(item) is list: stack.extend(item)
    evidence = {"sources":sources,"source_bindings":mappings,"observations":data["registry_snapshot"]["observations"],
        "historical_fx":data["registry_snapshot"]["historical_fx"],"assumptions":data["request_snapshot"],
        "qualifications":data["qualifications"]}
    snapshot = FinancialSnapshot(copied["canonical_snapshot"])  # AFTER full validation and expected digest.
    parsed_request = FinancialRequest.parse(data["request_snapshot"])
    if view == "summary":
        payload = {"information_cutoff":data["request_snapshot"]["information_cutoff"],
            "sources":[{k:s[k] for k in ("id","kind","read_scope","source_chain")} for s in sources],
            "scenarios":[{"id":s["id"],"label":s["label"],"qualification":s["qualification"],
                "years":[{"year":r["year"],"available":{m:r["target"][m]["raw_value"] is not None for m in ("revenue","operating_profit","net_profit")},
                    "composition_coverage":r["target"]["composition"]["coverage"]} for r in s["years"]]} for s in data["scenarios"]],
            "qualifications":data["qualifications"],"gap_codes":sorted(gap_codes),"assumption_refs":[s.id+":"+p.id for s in parsed_request.scenarios for p in s.parameters()]}
    elif view == "table":
        payload = {"scenarios":snapshot.table(),"historical_context":data["historical_context"],"evidence":evidence}
    else:
        payload = {"chart_spec":snapshot.chart_spec(),"evidence":evidence}
    result = {"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{
        "result_id":expected.id,"type":RESULT_TYPE,"input_revision":expected.binding.input_revision,
        "input_digest":expected.binding.input_digest,"request_digest":expected.binding.request_digest,
        "registry_digest":expected.binding.registry_ref.digest,"policy_revision":POLICY,
        "snapshot_digest":expected.snapshot_digest,"created_at":expected.created_at,
        "is_historical":current_input_revision != expected.binding.input_revision,
        "calculation_status":"calculated_under_assumptions","u2_goal_status":copied["u2_goal_status"],
        "model_analysis_ran":False,"view":view,"payload":payload}}
    _bounded(result, budget=budget)
    return result
