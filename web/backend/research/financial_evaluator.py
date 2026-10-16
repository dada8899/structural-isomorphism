"""Bounded pure financial scenarios. No storage, network, LLM or billing calls."""
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal, Inexact, DecimalException
import json

from .financial_policy import POLICY, YEARS, COST_TAGS, MILLION_FACTORS, FinancialError, FinancialResourceLimit, Meter, arithmetic_context, canonical, digest, json_cap, number
from .financial_schemas import SourceRegistry, FinancialRequest, Scenario, Period, Parameter, day


@dataclass(frozen=True)
class Cell:
    value: Decimal | None
    currency: str | None
    unit: str = "million"
    basis: str = "derived_conditional"
    reasons: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    parameters: tuple[str, ...] = ()


def annual(year): return Period(f"{year}-01-01", f"{year}-12-31", "annual")


class _Evaluation:
    def __init__(self, request, registry, meter):
        self.r, self.registry, self.m = request, registry, meter
        self.base = registry.observation(request.interim_revenue_ref)
        self.native = self.base.amount.currency
        self.fx_choices = {v["observation_id"]: v["fx_id"] for v in request.historical_fx_choices}

    def validate(self):
        cutoff = day(self.r.information_cutoff)
        if cutoff.year != 2026: raise FinancialError("fixed 2026 bridge and future horizon require a 2026 information cutoff")
        for source in self.registry.sources:
            for stamp in (source.published_at, source.accessed_at):
                if stamp is not None and day(stamp) > cutoff: raise FinancialError("source after information cutoff")
        if self.base.metric != "revenue" or self.base.scope_kind != "group" or self.base.entity_scope != self.r.entity_scope:
            raise FinancialError("group revenue baseline required, not app/GMV/net profit")
        if self.base.period.grain != "interim" or self.base.period.year != 2026 or day(self.base.period.end) > cutoff:
            raise FinancialError("2026 observed interim period required")
        source_ids = {v.id for v in self.registry.sources}
        historic_ids = {self.base.id} | set(self.r.historical_context_refs)
        consumed_ids = historic_ids | {p.anchor_observation_id for s in self.r.scenarios for p in s.parameters() if p.anchor_observation_id is not None}
        for ref in consumed_ids:
            obs = self.registry.observation(ref)
            if obs.evidence_basis == "disclosed" and day(obs.period.end) > cutoff:
                raise FinancialError("future period is not historical actual")
        for ref in historic_ids:
            obs = self.registry.observation(ref)
            if obs.scope_kind != "group" or obs.entity_scope != self.r.entity_scope: raise FinancialError("mixed entity scope")
        for choice in self.r.historical_fx_choices:
            if choice["observation_id"] not in historic_ids: raise FinancialError("FX choice outside selected historical observations")
            obs = self.registry.observation(choice["observation_id"])
            rate = next((v for v in self.registry.historical_fx if v.id == choice["fx_id"]), None)
            if rate is None or rate.kind != "period_average" or rate.period != obs.period:
                raise FinancialError("historical flow needs same-period average FX, never spot/future")
            if (rate.from_currency, rate.to_currency) != (obs.amount.currency, self.r.target_currency): raise FinancialError("historical FX direction mismatch")
        for scenario in self.r.scenarios:
            if scenario.accounting_basis != self.base.accounting_basis: raise FinancialError("accounting basis mismatch")
            if day(scenario.remaining_revenue.period.start) != day(self.base.period.end) + timedelta(days=1):
                raise FinancialError("interim and remainder must be adjacent, nonoverlapping")
            for p in scenario.parameters():
                if set(p.source_refs) - source_ids: raise FinancialError("parameter source outside registry")
                if p.anchor_observation_id is not None:
                    obs = self.registry.observation(p.anchor_observation_id)
                    if not p.independent:
                        if obs.accounting_basis != scenario.accounting_basis:
                            raise FinancialError("anchor accounting basis mismatch requires independent assumption")
                        if (p.unit not in MILLION_FACTORS or obs.evidence_basis in {"missing", "conflicted"}
                                or p.period != obs.period or p.currency != obs.amount.currency
                                or obs.scope_kind != "group" or obs.entity_scope != self.r.entity_scope or p.value is None):
                            raise FinancialError("proposed fact does not match immutable observation")
                        a = self.m.calculate("mul", number(p.value), MILLION_FACTORS[p.unit])
                        b = self.m.calculate("mul", number(obs.amount.value), MILLION_FACTORS[obs.amount.unit])
                        if a != b: raise FinancialError("known value changed without independent assumption")
            if not scenario.remaining_revenue.independent:
                if self.registry.observation(scenario.remaining_revenue.anchor_observation_id).metric != "revenue": raise FinancialError("revenue anchor metric mismatch")
            cost_anchors = set()
            for cost in scenario.costs:
                for item in cost.values:
                    p = item.parameter
                    if p.anchor_observation_id:
                        obs = self.registry.observation(p.anchor_observation_id)
                        if obs.metric in {"capex", "net_profit"}: raise FinancialError("CAPEX/net profit cannot be a direct operating cost input")
                        if not p.independent and obs.metric != cost.kind: raise FinancialError("cost anchor metric mismatch")
                        if not p.independent:
                            key = item.year, obs.id
                            if key in cost_anchors: raise FinancialError("cost observation counted twice")
                            cost_anchors.add(key)
            for allocation in scenario.allocations:
                if any(not v.parameter.independent for v in allocation["values"]): raise FinancialError("future segmentation must remain an explicit scenario partition")
            for exclusion in scenario.exclusions:
                if set(exclusion["source_refs"]) - source_ids: raise FinancialError("exclusion source outside registry")

    def record(self, cell, *, scoped=False):
        self.m.tick()
        result = {"raw_value": None if cell.value is None else str(cell.value), "display": self.m.display(cell.value),
                "currency": cell.currency, "unit": cell.unit, "basis": cell.basis, "reasons": list(cell.reasons),
                "observation_refs": list(cell.observations), "parameter_refs": list(cell.parameters)}
        if scoped:
            del result["currency"]
            if cell.unit == "million": del result["unit"]
            if cell.basis == "derived_conditional": del result["basis"]
            if not cell.reasons: del result["reasons"]
        return result

    @staticmethod
    def refs(*cells):
        return tuple(sorted({v for c in cells for v in c.observations})), tuple(sorted({v for c in cells for v in c.parameters}))

    def combine(self, a, b, operation):
        if a.currency != b.currency or a.unit != b.unit: raise FinancialError("mixed currency/unit arithmetic")
        obs, params = self.refs(a, b)
        if a.value is None or b.value is None:
            return Cell(None, a.currency, a.unit, "conflicted" if "conflicted" in {a.basis, b.basis} else "missing",
                        tuple(sorted(set(a.reasons + b.reasons))), obs, params)
        return Cell(self.m.calculate(operation, a.value, b.value), a.currency, a.unit, observations=obs, parameters=params)

    def observation(self, obs):
        if obs.amount.value is None:
            return Cell(None, obs.amount.currency, basis=obs.evidence_basis, reasons=("observation_" + obs.evidence_basis,), observations=(obs.id,))
        return Cell(self.m.calculate("mul", number(obs.amount.value), MILLION_FACTORS[obs.amount.unit]), obs.amount.currency,
                    basis=obs.evidence_basis, observations=(obs.id,))

    def missing(self, cell, currency, reason):
        return Cell(None, currency, cell.unit, "conflicted" if cell.basis == "conflicted" else "missing", tuple(sorted(set(cell.reasons + (reason,)))), cell.observations, cell.parameters)

    def historical(self, obs):
        cell = self.observation(obs)
        if cell.currency == self.r.target_currency: return cell
        ref = self.fx_choices.get(obs.id)
        rate = next((v for v in self.registry.historical_fx if v.id == ref), None)
        if rate is None or rate.rate is None: return self.missing(cell, self.r.target_currency, "historical_fx_missing")
        if cell.value is None: return self.missing(cell, self.r.target_currency, "historical_value_missing")
        return Cell(self.m.calculate("mul", cell.value, number(rate.rate)), self.r.target_currency, observations=tuple(sorted(set(cell.observations + (rate.id,)))))

    def future(self, cell, currency, period, scenario):
        if cell.currency == currency: return cell
        fx = next((v for v in scenario.future_fx if (v["from_currency"], v["to_currency"], v["parameter"].period) == (cell.currency, currency, period)), None)
        if fx is None or fx["parameter"].value is None: return self.missing(cell, currency, "future_fx_assumption_missing")
        if cell.value is None: return self.missing(cell, currency, "amount_missing")
        p = fx["parameter"]
        return Cell(self.m.calculate("mul", cell.value, number(p.value)), currency, observations=cell.observations,
                    parameters=tuple(sorted(set(cell.parameters + (scenario.id + ":" + p.id,)))))

    def money_parameter(self, p, currency, scenario):
        refs = (scenario.id + ":" + p.id,)
        obs = (p.anchor_observation_id,) if not p.independent else ()
        if p.value is None: cell = Cell(None, p.currency, basis="missing", reasons=("parameter_missing:" + p.id,), observations=obs, parameters=refs)
        else: cell = Cell(self.m.calculate("mul", number(p.value), MILLION_FACTORS[p.unit]), p.currency, basis="scenario_assumption", observations=obs, parameters=refs)
        return self.future(cell, currency, p.period, scenario)

    def scale(self, cell, p, scenario, *, growth=False):
        params = tuple(sorted(set(cell.parameters + (scenario.id + ":" + p.id,))))
        if cell.value is None or p.value is None: return Cell(None, cell.currency, basis="conflicted" if cell.basis == "conflicted" else "missing", reasons=tuple(sorted(set(cell.reasons + ("rate_or_base_missing",)))), observations=cell.observations, parameters=params)
        rate = number(p.value)
        if growth: rate = self.m.calculate("add", Decimal(1), rate)
        return Cell(self.m.calculate("mul", cell.value, rate), cell.currency, observations=cell.observations, parameters=params)

    def profit(self, revenue, scenario, year, *, details=True):
        value = revenue
        rendered, covered = [], set()
        for line in scenario.costs:
            covered.update(line.coverage)
            item = next((v for v in line.values if v.year == year), None)
            if item is None: cost = Cell(None, revenue.currency, basis="missing", reasons=("cost_line_missing:" + line.id,))
            elif line.mode == "revenue_ratio": cost = self.scale(revenue, item.parameter, scenario)
            else: cost = self.money_parameter(item.parameter, revenue.currency, scenario)
            value = self.combine(value, cost, "add" if line.kind == "operating_adjustment" else "sub")
            if details: rendered.append({"id": line.id, "kind": line.kind, "coverage": list(line.coverage), "coverage_basis": line.coverage_basis, "value": self.record(cost, scoped=True)})
        covered.update(v["tag"] for v in scenario.exclusions)
        if COST_TAGS - covered: value = self.missing(value, revenue.currency, "incomplete_cost_coverage:" + ",".join(sorted(COST_TAGS - covered)))
        return value, rendered

    def composition(self, revenue, scenario, year, *, compact=False):
        result, total, known = [], Cell(Decimal(0), revenue.currency), 0
        for cat in self.r.categories:
            if cat["kind"] == "unallocated": continue
            allocation = next((v for v in scenario.allocations if v["category_id"] == cat["id"]), None)
            item = next((v for v in allocation["values"] if v.year == year), None) if allocation else None
            if item is None: amount = Cell(None, revenue.currency, basis="missing", reasons=("segment_not_allocated",))
            elif allocation["mode"] == "share": amount = self.scale(revenue, item.parameter, scenario)
            else: amount = self.money_parameter(item.parameter, revenue.currency, scenario)
            if amount.value is not None:
                total = self.combine(total, amount, "add"); known += 1
            if not compact:
                share = self.share(amount, revenue)
                result.append({"category_id": cat["id"], "amount": self.record(amount, scoped=True), "share": self.record(share, scoped=True), "included_in_allocated_sum": amount.value is not None})
        if revenue.value is not None and total.value > revenue.value: raise FinancialError("segments exceed group revenue; no negative unallocated plug")
        if compact: return None
        residue = self.combine(revenue, total, "sub")
        bucket = next(v for v in self.r.categories if v["kind"] == "unallocated")
        result.append({"category_id": bucket["id"], "amount": self.record(residue, scoped=True), "share": self.record(self.share(residue, revenue), scoped=True), "included_in_allocated_sum": residue.value is not None})
        if revenue.value is None: coverage = "group_missing"
        elif revenue.value == 0: coverage = "undefined_zero_revenue"
        elif known == 0: coverage = "unallocated_only"
        elif known < len(self.r.categories)-1 or residue.value != 0: coverage = "partial"
        else: coverage = "declared_scenario_partition_complete_not_audited"
        rounding_delta = None
        if revenue.value is not None:
            rounded_sum = Decimal(0)
            for row in result:
                if row["included_in_allocated_sum"]: rounded_sum = self.m.calculate("add", rounded_sum, Decimal(row["amount"]["display"]))
            rounding_delta = self.m.display(self.m.calculate("sub", Decimal(self.m.display(revenue.value)), rounded_sum))
        return {"coverage": coverage, "rows": result, "rounding_delta_million": rounding_delta,
                "scope": "unallocated includes all unmodelled revenue; missing named categories are not extra summands"}

    def share(self, amount, group):
        obs, params = self.refs(amount, group)
        if amount.value is None or group.value is None: return Cell(None, None, "ratio", "missing", ("share_input_missing",), obs, params)
        if group.value == 0: return Cell(None, None, "ratio", "missing", ("zero_revenue_denominator",), obs, params)
        return Cell(self.m.calculate("div", amount.value, group.value), None, "ratio", observations=obs, parameters=params)

    def scenario(self, scenario, *, compact=False):
        h1 = self.observation(self.base)
        h2 = self.money_parameter(scenario.remaining_revenue, self.native, scenario)
        native_revenue = self.combine(h1, h2, "add")
        target_h1 = self.historical(self.base)
        target_h2 = self.money_parameter(scenario.remaining_revenue, self.r.target_currency, scenario)
        target_revenue = self.combine(target_h1, target_h2, "add")
        bridge = {} if compact else {"interim": self.record(h1), "remaining_assumption": self.record(h2), "target_interim": self.record(target_h1),
                                    "target_remaining": self.record(target_h2), "qualification": "2026E, never annualized historical actual"}
        years = []
        for year in YEARS:
            self.m.tick()
            if year > 2026:
                p = next(v.parameter for v in scenario.growth if v.year == year)
                native_revenue = self.scale(native_revenue, p, scenario, growth=True)
                target_revenue = self.future(native_revenue, self.r.target_currency, annual(year), scenario)
            row = {"year": year, "period": asdict(annual(year)), "basis": "bridge_estimate" if year == 2026 else "conditional_scenario", "native_currency": self.native, "target_currency": self.r.target_currency}
            if compact:
                op, _ = self.profit(target_revenue, scenario, year, details=False)
                self.composition(native_revenue, scenario, year, compact=True)
                self.composition(target_revenue, scenario, year, compact=True)
                row["target"] = {"revenue": self.record(target_revenue), "operating_profit": self.record(op)}
                years.append(row)
                continue
            for name, revenue in (("native", native_revenue), ("target", target_revenue)):
                if name == "native" and self.native == self.r.target_currency:
                    continue
                op, costs = self.profit(revenue, scenario, year)
                row[name] = {"revenue": self.record(revenue, scoped=True), "operating_profit": self.record(op, scoped=True),
                             "net_profit": self.record(Cell(None, revenue.currency, basis="missing", reasons=("no_net_profit_projection_bridge",)), scoped=True),
                             "cost_bridge": costs, "composition": self.composition(revenue, scenario, year)}
            if self.native == self.r.target_currency:
                row["native"] = {"same_as": "target"}
            years.append(row)
        return {"id": scenario.id, "label": scenario.label, "accounting_basis": scenario.accounting_basis, "bridge": bridge, "years": years, "parameter_basis": "scenario_assumption",
                "exclusions": list(scenario.exclusions), "qualification": "source_linked_conditional_unreviewed" if all(p.source_refs for p in scenario.parameters()) else "mechanical_assumption_demonstration_not_validated_forecast"}


@dataclass(frozen=True)
class FinancialSnapshot:
    _canonical_json: str

    def __post_init__(self):
        from .financial_policy import MAX_JSON
        if type(self._canonical_json) is not str or len(self._canonical_json) > MAX_JSON or len(self._canonical_json.encode()) > MAX_JSON:
            raise FinancialResourceLimit("snapshot byte limit")

    @property
    def digest(self):
        import hashlib
        return hashlib.sha256(self._canonical_json.encode()).hexdigest()

    def table(self):
        scenarios = json.loads(self._canonical_json)["scenarios"]
        def materialize(value, currency):
            if type(value) is list:
                for child in value: materialize(child, currency)
            elif type(value) is dict:
                if {"raw_value", "display"} <= value.keys():
                    value.setdefault("basis", "derived_conditional")
                    value.setdefault("reasons", [])
                    value.setdefault("unit", "million")
                    value.setdefault("currency", None if value["unit"] == "ratio" else currency)
                else:
                    for child in value.values(): materialize(child, currency)
        for scenario in scenarios:
            for row in scenario["years"]:
                if row["native"] == {"same_as": "target"}:
                    row["native"] = json.loads(canonical(row["target"]))
                materialize(row["target"], row["target_currency"])
                materialize(row["native"], row["native_currency"])
        return scenarios

    def chart_spec(self):
        # Read-only extraction of already-rendered table cells: no second
        # financial calculation, interpolation, fitting or float conversion.
        data = json.loads(self._canonical_json)
        series = []
        for scenario in data["scenarios"]:
            for metric in ("revenue", "operating_profit", "net_profit"):
                series.append({"scenario_id": scenario["id"], "metric": metric, "currency": data["target_currency"], "unit": "million",
                               "years": [r["year"] for r in scenario["years"]], "values": [r["target"][metric]["display"] for r in scenario["years"]]})
            for category in data["categories"]:
                series.append({"scenario_id": scenario["id"], "metric": "segment_revenue", "category_id": category["id"], "currency": data["target_currency"], "unit": "million",
                               "years": [r["year"] for r in scenario["years"]],
                               "values": [next(v["amount"]["display"] for v in r["target"]["composition"]["rows"] if v["category_id"] == category["id"]) for r in scenario["years"]]})
        return {"snapshot_digest": self.digest, "series": series, "connect_nulls": False, "probability_calibrated": False,
                "value_kind": "absolute_amounts_display_rounded", "sensitivity": data["sensitivity"]}

    def export(self):
        result = {"snapshot": json.loads(self._canonical_json), "snapshot_digest": self.digest, "chart_spec": self.chart_spec()}
        json_cap(result)
        return result


def evaluate_financial(data, registry):
    """Typed pure evaluator only; caller must supply controlled facts/permissions.
    No implicit defaults, facts from LLM, DB connection or currency exchange API.
    """
    if type(registry) is not SourceRegistry: raise FinancialError("controlled SourceRegistry required")
    request = FinancialRequest.parse(data)
    json_cap({"request": request.data(), "registry": registry.data()})
    meter = Meter()
    try:
        with arithmetic_context() as context:
            engine = _Evaluation(request, registry, meter); engine.validate()
            scenarios = [engine.scenario(v) for v in request.scenarios]
            sensitivity = []
            if request.sensitivity is not None:
                selection = request.sensitivity
                scenario = next((v for v in request.scenarios if v.id == selection["scenario_id"]), None)
                p = next((v for v in scenario.parameters() if v.id == selection["parameter_id"]), None) if scenario else None
                allowed = {v.parameter.id for v in scenario.growth} | {v.parameter.id for c in scenario.costs for v in c.values} | {v["parameter"].id for v in scenario.future_fx} if scenario else set()
                if p is None or p.id not in allowed or not p.independent: raise FinancialError("sensitivity requires one independent growth/cost/FX parameter")
                def changed(value, target_id, point):
                    if type(value) is dict:
                        return {k: (point if k == "value" and value.get("id") == target_id else changed(v, target_id, point)) for k, v in value.items()}
                    if type(value) is list: return [changed(v, target_id, point) for v in value]
                    return value
                base = request.data()
                for point in selection["points"]:
                    meter.tick()
                    variant = json.loads(canonical(base))
                    variant["sensitivity"] = None
                    variant["scenarios"] = [changed(v, p.id, point) if v["id"] == scenario.id else v for v in variant["scenarios"]]
                    parsed = FinancialRequest.parse(variant)
                    other = _Evaluation(parsed, registry, meter); other.validate()
                    rows = other.scenario(next(v for v in parsed.scenarios if v.id == scenario.id), compact=True)["years"]
                    sensitivity.append({"parameter_ref": scenario.id + ":" + p.id, "point": point, "case_input_digest": digest({"request": parsed.data(), "registry": registry.data()}),
                                        "years": [r["year"] for r in rows], "target_revenue": [r["target"]["revenue"]["display"] for r in rows],
                                        "target_operating_profit": [r["target"]["operating_profit"]["display"] for r in rows]})
            historical = [{"observation": asdict(registry.observation(ref)), "target_value": engine.record(engine.historical(registry.observation(ref)))} for ref in (request.interim_revenue_ref,) + request.historical_context_refs]
            payload = {"policy_revision": POLICY, "input_digest": digest({"request": request.data(), "registry": registry.data()}), "registry_digest": digest(registry.data()),
                       "target_currency": request.target_currency, "amount_unit": "million", "display_quantization": "6 decimals HALF_EVEN", "calculation_precision": 50,
                       "request_snapshot": request.data(), "registry_snapshot": registry.data(), "historical_context": historical, "categories": list(request.categories),
                       "scenarios": scenarios, "sensitivity": sensitivity, "operations_used": meter.operations,
                       "qualifications": ["bounded pure evaluator, not an OS sandbox or API/source-authenticity verification", "caller-controlled registry basis is not verified by this module", "all projected values conditional; no calibrated probabilities", "no historical operating margin or profit backfill", "missing net profit bridge remains missing"],
                       "decimal50_inexact_encountered": context.flags[Inexact]}
            if any(s.published_at is None or s.accessed_at is None for s in registry.sources):
                payload["qualifications"].append("source_publication_or_access_time_unknown")
            if any(o.evidence_basis == "conflicted" for o in registry.observations):
                payload["qualifications"].append("registry_contains_conflicts_not_averaged_or_silently_zeroed")
            snapshot = FinancialSnapshot(json_cap(payload))
            snapshot.export(); meter.tick()
            return snapshot
    except DecimalException:
        raise FinancialResourceLimit("Decimal arithmetic condition") from None
