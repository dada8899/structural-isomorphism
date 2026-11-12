"""Immutable caller-controlled facts and explicitly separate scenario inputs.

The registry is supplied by a trusted importer/caller, never deserialized from
an LLM request here. Its presence is not API authorization or source truth proof.
"""
from dataclasses import asdict, dataclass
from datetime import date
import re
import unicodedata
from urllib.parse import urlsplit
from uuid import UUID

from .financial_policy import FinancialError, FinancialResourceLimit, CURRENCIES, COST_KINDS, COST_TAGS, MILLION_FACTORS, POLICY, YEARS, number, canonical, digest


def text(value, cap=400):
    if type(value) is not str or not 1 <= len(value) <= cap or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\n\t" for c in value):
        raise FinancialError("bounded text required")


def uid(value):
    if type(value) is not str or len(value) != 36:
        raise FinancialError("UUID required")
    try:
        if str(UUID(value, version=4)) != value: raise ValueError()
    except ValueError:
        raise FinancialError("canonical UUID4 required") from None


def label(value):
    if type(value) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value) is None:
        raise FinancialError("local ASCII label required")


def hash_value(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise FinancialError("digest required")


def day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise FinancialError("ISO date required")
    try: return date.fromisoformat(value)
    except ValueError: raise FinancialError("invalid date") from None


def tuple_limit(values, cap):
    if type(values) is not tuple: raise FinancialError("immutable tuple required")
    if len(values) > cap: raise FinancialResourceLimit("object count limit")


def fields(value, required):
    if type(value) is not dict or len(value) != len(required) or set(value) != set(required):
        raise FinancialError("unknown or missing input fields")


def array(value, cap):
    if type(value) is not list: raise FinancialError("JSON array required")
    if len(value) > cap: raise FinancialResourceLimit("array limit")
    return value


def unique(values):
    if len(set(values)) != len(values): raise FinancialError("duplicate identity")


@dataclass(frozen=True)
class Period:
    start: str
    end: str
    grain: str

    def __post_init__(self):
        start, end = day(self.start), day(self.end)
        if start > end or start.year != end.year: raise FinancialError("invalid financial period")
        if self.grain not in {"annual", "interim", "remaining"}: raise FinancialError("period grain required")
        if self.grain == "annual" and (start.month, start.day, end.month, end.day) != (1, 1, 12, 31): raise FinancialError("full annual period required")
        if self.grain == "interim" and ((start.month, start.day) != (1, 1) or (end.month, end.day) == (12, 31)): raise FinancialError("year-to-date interim required")
        if self.grain == "remaining" and ((end.month, end.day) != (12, 31) or (start.month, start.day) == (1, 1)): raise FinancialError("remaining period required")

    @property
    def year(self): return day(self.start).year


@dataclass(frozen=True)
class SourceSnapshot:
    id: str
    kind: str
    url: str
    published_at: str | None
    accessed_at: str | None
    read_scope: str
    source_chain: tuple[str, ...]
    curated_record_digest: str | None
    curated_commit: str | None
    curated_entry_locator: str | None
    raw_response_digest: str | None
    extracted_text_digest: str | None
    retained_original_ref: str | None

    def __post_init__(self):
        uid(self.id); text(self.url, 1600); text(self.read_scope, 700)
        url = urlsplit(self.url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            raise FinancialError("public source URL required, not a local path")
        for value in (self.published_at, self.accessed_at):
            if value is not None: day(value)
        if self.published_at is not None and self.accessed_at is not None and day(self.accessed_at) < day(self.published_at): raise FinancialError("source access precedes publication")
        tuple_limit(self.source_chain, 16); unique(self.source_chain)
        for ref in self.source_chain: uid(ref)
        if self.kind == "curated_record":
            hash_value(self.curated_record_digest)
            if type(self.curated_commit) is not str or re.fullmatch(r"[0-9a-f]{40}", self.curated_commit) is None: raise FinancialError("curated commit required")
            text(self.curated_entry_locator, 240)
            if self.curated_entry_locator.startswith(("/", "~")) or "\\" in self.curated_entry_locator: raise FinancialError("no private absolute locator")
            if any(v is not None for v in (self.raw_response_digest, self.extracted_text_digest, self.retained_original_ref)):
                raise FinancialError("curated table is not original response evidence")
        elif self.kind in {"historical_original", "live_original"}:
            hash_value(self.raw_response_digest); hash_value(self.extracted_text_digest); uid(self.retained_original_ref)
            if any(v is not None for v in (self.curated_record_digest, self.curated_commit, self.curated_entry_locator)):
                raise FinancialError("original snapshot and curated table are distinct provenance kinds")
        else: raise FinancialError("unsupported provenance kind")


@dataclass(frozen=True)
class FinancialAmount:
    value: str | None
    currency: str
    unit: str

    def __post_init__(self):
        if self.currency not in CURRENCIES or self.unit not in MILLION_FACTORS: raise FinancialError("unsupported financial currency or unit")
        if self.value is not None: number(self.value)


@dataclass(frozen=True)
class FinancialObservation:
    id: str
    metric: str
    entity_scope: str
    scope_kind: str
    period: Period
    amount: FinancialAmount
    accounting_basis: str
    evidence_basis: str
    source_refs: tuple[str, ...]
    alternative_refs: tuple[str, ...] = ()

    def __post_init__(self):
        uid(self.id); text(self.entity_scope, 120); text(self.accounting_basis, 240)
        if self.scope_kind not in {"group", "segment", "app"}: raise FinancialError("controlled entity scope kind required")
        if type(self.period) is not Period or type(self.amount) is not FinancialAmount: raise FinancialError("typed period/amount required")
        allowed = {"revenue", "operating_profit", "net_profit", "operating_cost", "operating_expense", "shared_cost", "depreciation", "sbc", "operating_adjustment", "capex"}
        if self.metric not in allowed: raise FinancialError("unsupported metric; GMV is not revenue")
        if self.evidence_basis not in {"disclosed", "media_estimate", "missing", "conflicted"}: raise FinancialError("registry basis required")
        if (self.evidence_basis in {"missing", "conflicted"}) != (self.amount.value is None): raise FinancialError("missing/conflict must remain null")
        if self.amount.value is not None and self.metric not in {"operating_profit", "net_profit", "operating_adjustment"} and number(self.amount.value) < 0: raise FinancialError("negative revenue or cost")
        tuple_limit(self.source_refs, 16); tuple_limit(self.alternative_refs, 8)
        unique(self.source_refs); unique(self.alternative_refs)
        for ref in self.source_refs + self.alternative_refs: uid(ref)
        if self.evidence_basis in {"disclosed", "media_estimate"} and not self.source_refs: raise FinancialError("observation needs controlled source")


@dataclass(frozen=True)
class HistoricalFX:
    id: str
    from_currency: str
    to_currency: str
    period: Period
    kind: str
    rate: str | None
    source_refs: tuple[str, ...]

    def __post_init__(self):
        uid(self.id)
        if self.from_currency not in CURRENCIES or self.to_currency not in CURRENCIES or self.from_currency == self.to_currency: raise FinancialError("explicit FX direction required")
        if type(self.period) is not Period or self.kind not in {"period_average", "spot"}: raise FinancialError("typed historical FX required")
        if self.rate is not None and number(self.rate) <= 0: raise FinancialError("FX must be positive")
        tuple_limit(self.source_refs, 16); unique(self.source_refs)
        for ref in self.source_refs: uid(ref)
        if self.rate is not None and not self.source_refs: raise FinancialError("historical FX needs a controlled source")


@dataclass(frozen=True)
class SourceRegistry:
    sources: tuple[SourceSnapshot, ...]
    observations: tuple[FinancialObservation, ...]
    historical_fx: tuple[HistoricalFX, ...] = ()

    def __post_init__(self):
        for values, cap, cls in ((self.sources, 16, SourceSnapshot), (self.observations, 64, FinancialObservation), (self.historical_fx, 16, HistoricalFX)):
            tuple_limit(values, cap)
            if any(type(v) is not cls for v in values): raise FinancialError("controlled typed registry records required")
        unique([v.id for v in self.sources + self.observations + self.historical_fx])
        source_ids = {s.id for s in self.sources}
        for obj in self.observations + self.historical_fx:
            if set(obj.source_refs) - source_ids: raise FinancialError("source outside registry")
        for source in self.sources:
            if set(source.source_chain) - source_ids or source.id in source.source_chain: raise FinancialError("invalid source chain")
        visited = set()
        def visit(ref, path):
            if ref in path: raise FinancialError("cyclic source chain")
            if ref in visited: return
            for child in next(s for s in self.sources if s.id == ref).source_chain: visit(child, path | {ref})
            visited.add(ref)
        for source in self.sources: visit(source.id, set())
        observations = {o.id: o for o in self.observations}
        for obs in self.observations:
            for ref in obs.alternative_refs:
                if ref not in observations: raise FinancialError("missing alternative")
                alt = observations[ref]
                if ref == obs.id or (alt.entity_scope, alt.scope_kind, alt.metric, alt.period, alt.accounting_basis) != (obs.entity_scope, obs.scope_kind, obs.metric, obs.period, obs.accounting_basis): raise FinancialError("incompatible alternative")

    def observation(self, ref):
        uid(ref)
        found = next((v for v in self.observations if v.id == ref), None)
        if found is None: raise FinancialError("observation outside controlled registry")
        return found

    def data(self): return asdict(self)


@dataclass(frozen=True)
class Parameter:
    id: str
    value: str | None
    unit: str
    currency: str | None
    period: Period
    rationale: str
    source_refs: tuple[str, ...]
    anchor_observation_id: str | None
    independent: bool

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "value", "unit", "currency", "period", "rationale", "source_refs", "anchor_observation_id", "independent"))
        label(data["id"]); text(data["rationale"])
        if data["value"] is not None: number(data["value"])
        if data["unit"] not in set(MILLION_FACTORS) | {"ratio", "fx"}: raise FinancialError("parameter unit")
        if data["unit"] in {"ratio", "fx"}:
            if data["currency"] is not None: raise FinancialError("ratios are not currency amounts")
        elif data["currency"] not in CURRENCIES: raise FinancialError("financial currency required")
        if type(data["independent"]) is not bool: raise FinancialError("strict independent assumption flag")
        if data["anchor_observation_id"] is not None: uid(data["anchor_observation_id"])
        if not data["independent"] and data["anchor_observation_id"] is None: raise FinancialError("not a fact without registry anchor")
        refs = tuple(array(data["source_refs"], 16)); unique(refs)
        for ref in refs: uid(ref)
        fields(data["period"], ("start", "end", "grain"))
        return cls(data["id"], data["value"], data["unit"], data["currency"], Period(**data["period"]), data["rationale"], refs, data["anchor_observation_id"], data["independent"])


@dataclass(frozen=True)
class AnnualValue:
    year: int
    parameter: Parameter

    @classmethod
    def parse(cls, data):
        fields(data, ("year", "parameter"))
        if type(data["year"]) is not int or data["year"] not in YEARS: raise FinancialError("year outside fixed horizon")
        param = Parameter.parse(data["parameter"])
        if param.period != Period(f'{data["year"]}-01-01', f'{data["year"]}-12-31', "annual"): raise FinancialError("annual parameter period mismatch")
        return cls(data["year"], param)


@dataclass(frozen=True)
class CostLine:
    id: str
    kind: str
    label: str
    mode: str
    coverage: tuple[str, ...]
    coverage_basis: str
    values: tuple[AnnualValue, ...]

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "kind", "label", "mode", "coverage", "coverage_basis", "values"))
        label(data["id"]); text(data["label"], 120); text(data["coverage_basis"])
        if data["kind"] not in COST_KINDS or data["mode"] not in {"amount", "revenue_ratio"}: raise FinancialError("cost kind/mode; CAPEX cannot enter operating profit")
        coverage = tuple(array(data["coverage"], 5)); unique(coverage)
        if set(coverage) - COST_TAGS: raise FinancialError("unregistered cost coverage; CAPEX prohibited")
        mandatory = COST_KINDS[data["kind"]]
        if mandatory is None and coverage or mandatory is not None and mandatory not in coverage: raise FinancialError("explicit cost inclusion scope required")
        values = tuple(AnnualValue.parse(v) for v in array(data["values"], 6)); unique([v.year for v in values])
        for item in values:
            p = item.parameter
            if (data["mode"] == "revenue_ratio") != (p.unit == "ratio") or p.unit == "fx": raise FinancialError("cost amount/ratio mismatch")
            if data["kind"] != "operating_adjustment" and p.value is not None and number(p.value) < 0: raise FinancialError("negative cost")
        return cls(data["id"], data["kind"], data["label"], data["mode"], coverage, data["coverage_basis"], values)


@dataclass(frozen=True)
class Scenario:
    id: str
    label: str
    accounting_basis: str
    remaining_revenue: Parameter
    growth: tuple[AnnualValue, ...]
    costs: tuple[CostLine, ...]
    exclusions: tuple[dict, ...]
    allocations: tuple[dict, ...]
    future_fx: tuple[dict, ...]

    @classmethod
    def parse(cls, data):
        fields(data, ("id", "label", "accounting_basis", "remaining_revenue", "growth", "costs", "exclusions", "allocations", "future_fx"))
        label(data["id"]); text(data["label"], 120); text(data["accounting_basis"], 240)
        remaining = Parameter.parse(data["remaining_revenue"])
        if remaining.unit not in MILLION_FACTORS or remaining.period.grain != "remaining" or remaining.period.year != 2026: raise FinancialError("explicit 2026 remaining revenue required")
        if remaining.value is not None and number(remaining.value) < 0: raise FinancialError("negative remaining revenue")
        growth = tuple(AnnualValue.parse(v) for v in array(data["growth"], 5))
        if sorted(v.year for v in growth) != list(YEARS[1:]): raise FinancialError("five complete future years required")
        for v in growth:
            if v.parameter.unit != "ratio" or v.parameter.value is not None and number(v.parameter.value) < -1: raise FinancialError("growth must be >= -1")
        costs = tuple(CostLine.parse(v) for v in array(data["costs"], 16)); unique([v.id for v in costs])
        covered = []
        for cost in costs: covered.extend(cost.coverage)
        unique(covered)
        exclusions = []
        for raw in array(data["exclusions"], 5):
            fields(raw, ("tag", "rationale", "source_refs")); text(raw["rationale"])
            if raw["tag"] not in COST_TAGS: raise FinancialError("invalid exclusion")
            refs = tuple(array(raw["source_refs"], 16)); unique(refs)
            for ref in refs: uid(ref)
            exclusions.append({"tag": raw["tag"], "rationale": raw["rationale"], "source_refs": refs})
        unique(covered + [v["tag"] for v in exclusions])
        allocations = []
        for raw in array(data["allocations"], 8):
            fields(raw, ("category_id", "mode", "values")); label(raw["category_id"])
            if raw["mode"] not in {"amount", "share"}: raise FinancialError("allocation mode")
            values = tuple(AnnualValue.parse(v) for v in array(raw["values"], 6)); unique([v.year for v in values])
            for item in values:
                p = item.parameter
                if (raw["mode"] == "share") != (p.unit == "ratio") or p.unit == "fx": raise FinancialError("allocation unit")
                if p.value is not None and (number(p.value) < 0 or raw["mode"] == "share" and number(p.value) > 1): raise FinancialError("allocation domain")
            allocations.append({"category_id": raw["category_id"], "mode": raw["mode"], "values": values})
        unique([v["category_id"] for v in allocations])
        rates = []
        for raw in array(data["future_fx"], 16):
            fields(raw, ("from_currency", "to_currency", "parameter"))
            if raw["from_currency"] not in CURRENCIES or raw["to_currency"] not in CURRENCIES or raw["from_currency"] == raw["to_currency"]: raise FinancialError("future FX direction")
            p = Parameter.parse(raw["parameter"])
            if p.unit != "fx" or not p.independent or p.value is not None and number(p.value) <= 0: raise FinancialError("explicit positive future FX assumption required")
            if p.period.year not in YEARS or p.period.grain == "interim": raise FinancialError("future FX cannot replace a historical interim rate")
            rates.append({"from_currency": raw["from_currency"], "to_currency": raw["to_currency"], "parameter": p})
        unique([(v["from_currency"], v["to_currency"], v["parameter"].period) for v in rates])
        result = cls(data["id"], data["label"], data["accounting_basis"], remaining, growth, costs, tuple(exclusions), tuple(allocations), tuple(rates))
        unique([p.id for p in result.parameters()])
        return result

    def parameters(self):
        return (self.remaining_revenue,) + tuple(v.parameter for v in self.growth) + tuple(v.parameter for c in self.costs for v in c.values) + tuple(v.parameter for a in self.allocations for v in a["values"]) + tuple(v["parameter"] for v in self.future_fx)


@dataclass(frozen=True)
class FinancialRequest:
    entity_scope: str
    information_cutoff: str
    interim_revenue_ref: str
    baseline_selection_reason: str
    historical_context_refs: tuple[str, ...]
    historical_fx_choices: tuple[dict, ...]
    target_currency: str
    categories: tuple[dict, ...]
    scenarios: tuple[Scenario, ...]
    sensitivity: dict | None
    policy_revision: str

    @classmethod
    def parse(cls, data):
        fields(data, ("entity_scope", "information_cutoff", "interim_revenue_ref", "baseline_selection_reason", "historical_context_refs", "historical_fx_choices", "target_currency", "categories", "scenarios", "sensitivity", "policy_revision"))
        text(data["entity_scope"], 120); day(data["information_cutoff"]); uid(data["interim_revenue_ref"]); text(data["baseline_selection_reason"])
        if data["target_currency"] not in CURRENCIES or data["policy_revision"] != POLICY: raise FinancialError("fixed currency/policy required")
        contexts = tuple(array(data["historical_context_refs"], 16)); unique(contexts)
        for ref in contexts: uid(ref)
        choices = []
        for raw in array(data["historical_fx_choices"], 16):
            fields(raw, ("observation_id", "fx_id")); uid(raw["observation_id"]); uid(raw["fx_id"]); choices.append(dict(raw))
        unique([v["observation_id"] for v in choices])
        categories = []
        for raw in array(data["categories"], 8):
            fields(raw, ("id", "label", "definition", "dimension", "excludes", "kind")); label(raw["id"]); text(raw["label"], 120); text(raw["definition"])
            if raw["dimension"] != "monetization" or raw["kind"] not in {"segment", "unallocated"}: raise FinancialError("do not mix app/geography/GMV with revenue segments")
            excludes = tuple(array(raw["excludes"], 8)); unique(excludes)
            for ref in excludes: label(ref)
            categories.append({**raw, "excludes": excludes})
        unique([v["id"] for v in categories])
        if sum(v["kind"] == "unallocated" for v in categories) != 1: raise FinancialError("explicit unallocated bucket required")
        ids = {v["id"] for v in categories}
        for cat in categories:
            if set(cat["excludes"]) != ids - {cat["id"]}: raise FinancialError("explicit mutually exclusive definitions required")
        scenarios = tuple(Scenario.parse(v) for v in array(data["scenarios"], 3))
        if not scenarios: raise FinancialError("scenario required")
        unique([v.id for v in scenarios])
        for scenario in scenarios:
            for allocation in scenario.allocations:
                if allocation["category_id"] not in {v["id"] for v in categories if v["kind"] == "segment"}: raise FinancialError("allocation category invalid")
        sensitivity = None
        if data["sensitivity"] is not None:
            raw = data["sensitivity"]; fields(raw, ("scenario_id", "parameter_id", "points")); label(raw["scenario_id"]); label(raw["parameter_id"])
            points = tuple(array(raw["points"], 21)); unique(points)
            for point in points: number(point)
            sensitivity = {"scenario_id": raw["scenario_id"], "parameter_id": raw["parameter_id"], "points": points}
        return cls(data["entity_scope"], data["information_cutoff"], data["interim_revenue_ref"], data["baseline_selection_reason"], contexts, tuple(choices), data["target_currency"], tuple(categories), scenarios, sensitivity, POLICY)

    def data(self):
        # Recursive dataclass conversion also copies the local dictionaries, so
        # callers cannot mutate a saved result through a returned JSON view.
        import json
        return json.loads(canonical(asdict(self)))
