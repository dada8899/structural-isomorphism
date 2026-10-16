"""All values and provenance objects below are synthetic, not ByteDance data."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from web.backend.research.financial_schemas import SourceSnapshot, SourceRegistry, FinancialObservation, FinancialAmount, HistoricalFX, Period
from web.backend.research.financial_policy import POLICY, COST_TAGS, FinancialError, FinancialResourceLimit, Meter, number, json_cap
from web.backend.research.financial_evaluator import evaluate_financial, FinancialSnapshot


def uid(): return str(uuid4())
def fy(year): return {"start": f"{year}-01-01", "end": f"{year}-12-31", "grain": "annual"}


def source():
    return SourceSnapshot(uid(), "curated_record", "https://example.org/synthetic-financial-fixture", "2026-08-01", "2026-10-17",
        "Synthetic manually curated table entry, not an actual article or original-byte verification", (), "a" * 64, "b" * 40,
        "synthetic_table.md#entry1:L1-L2", None, None, None)


def parameter(name, value, *, year=2026, unit="ratio", currency=None, period=None):
    return {"id": name, "value": value, "unit": unit, "currency": currency, "period": period or fy(year),
            "rationale": "Explicit synthetic independent scenario assumption", "source_refs": [], "anchor_observation_id": None, "independent": True}


def annual_values(prefix, value, *, unit="ratio", currency=None):
    return [{"year": year, "parameter": parameter(f"{prefix}_{year}", value, year=year, unit=unit, currency=currency)} for year in range(2026, 2032)]


def fixture(currency="CNY"):
    s = source()
    revenue = FinancialObservation(uid(), "revenue", "synthetic_group", "group", Period("2026-01-01", "2026-06-30", "interim"), FinancialAmount("40", currency, "million"), "synthetic_consolidated_basis", "media_estimate", (s.id,))
    op = FinancialObservation(uid(), "operating_profit", "synthetic_group", "group", revenue.period, FinancialAmount(None, currency, "million"), revenue.accounting_basis, "missing", ())
    net = FinancialObservation(uid(), "net_profit", "synthetic_group", "group", revenue.period, FinancialAmount(None, currency, "million"), revenue.accounting_basis, "conflicted", (s.id,))
    registry = SourceRegistry((s,), (revenue, op, net))
    scenario = {"id": "base", "label": "Synthetic conditional case", "accounting_basis": revenue.accounting_basis,
                "remaining_revenue": parameter("remaining", "60", unit="million", currency=currency, period={"start": "2026-07-01", "end": "2026-12-31", "grain": "remaining"}),
                "growth": [{"year": year, "parameter": parameter(f"g_{year}", "0.1", year=year)} for year in range(2027, 2032)],
                "costs": [{"id": "all_costs", "kind": "operating_cost", "label": "Synthetic complete cost envelope", "mode": "revenue_ratio", "coverage": sorted(COST_TAGS),
                           "coverage_basis": "Explicitly assumes all listed cost categories are included once", "values": annual_values("cost", "0.85")}],
                "exclusions": [], "allocations": [], "future_fx": []}
    data = {"entity_scope": revenue.entity_scope, "information_cutoff": "2026-10-17", "interim_revenue_ref": revenue.id,
            "baseline_selection_reason": "Select synthetic media-estimate candidate; not a disclosed company forecast",
            "historical_context_refs": [op.id, net.id], "historical_fx_choices": [], "target_currency": "CNY",
            "categories": [{"id": "advertising", "label": "Synthetic advertising", "definition": "Declared scenario advertising only", "dimension": "monetization", "excludes": ["unallocated"], "kind": "segment"},
                           {"id": "unallocated", "label": "Other/unallocated", "definition": "Everything not explicitly modelled; not disclosed business detail", "dimension": "monetization", "excludes": ["advertising"], "kind": "unallocated"}],
            "scenarios": [scenario], "sensitivity": None, "policy_revision": POLICY}
    return data, registry


def rows(snapshot): return snapshot.table()[0]["years"]
def allocation(value, *, mode="amount", category="advertising"):
    return {"category_id": category, "mode": mode, "values": annual_values("allocation", value, unit="ratio" if mode == "share" else "million", currency=None if mode == "share" else "CNY")}


def future_fx(period, value, name, *, from_currency="USD", to_currency="CNY"):
    return {"from_currency": from_currency, "to_currency": to_currency, "parameter": parameter(name, value, unit="fx", period=period)}


class FinancialTests(unittest.TestCase):
    def test_independent_decimal_golden_bridge_and_five_year_chain(self):
        data, registry = fixture()
        snapshot = evaluate_financial(data, registry)
        result = rows(snapshot)
        expected = ["100", "110", "121", "133.1", "146.41", "161.051"]
        self.assertEqual([r["year"] for r in result], list(range(2026, 2032)))
        with localcontext() as context:
            context.prec = 50
            for row, value in zip(result, expected):
                self.assertEqual(Decimal(row["target"]["revenue"]["raw_value"]), Decimal(value))
                self.assertEqual(Decimal(row["target"]["operating_profit"]["raw_value"]), Decimal(value) - Decimal(value) * Decimal("0.85"))
        self.assertEqual(result[0]["target"]["operating_profit"]["display"], "15.000000")
        self.assertEqual(result[0]["basis"], "bridge_estimate")
        self.assertNotEqual(result[0]["target"]["revenue"]["raw_value"], "80")

    def test_missing_historical_profit_does_not_block_explicit_future_costs(self):
        data, registry = fixture()
        out = evaluate_financial(data, registry).export()["snapshot"]
        self.assertIsNone(out["historical_context"][1]["observation"]["amount"]["value"])
        self.assertEqual(out["historical_context"][1]["observation"]["evidence_basis"], "missing")
        self.assertEqual(out["historical_context"][2]["observation"]["evidence_basis"], "conflicted")
        self.assertEqual(out["scenarios"][0]["years"][1]["target"]["operating_profit"]["display"], "16.500000")
        self.assertIsNone(out["scenarios"][0]["years"][1]["target"]["net_profit"]["display"])
        self.assertIn("mechanical", out["scenarios"][0]["qualification"])

    def test_unit_multipliers_preserve_original_data(self):
        data, registry = fixture()
        original = registry.observations[0]
        changed = replace(original, amount=FinancialAmount("0.04", "CNY", "billion"))
        registry = SourceRegistry(registry.sources, (changed,) + registry.observations[1:])
        data["scenarios"][0]["remaining_revenue"].update(value="60000", unit="thousand")
        snapshot = evaluate_financial(data, registry)
        self.assertEqual(rows(snapshot)[0]["target"]["revenue"]["display"], "100.000000")
        self.assertEqual(snapshot.export()["snapshot"]["registry_snapshot"]["observations"][0]["amount"], {"value": "0.04", "currency": "CNY", "unit": "billion"})

    def test_historical_and_future_fx_are_separate_and_period_exact(self):
        data, registry = fixture("USD")
        historical = HistoricalFX(uid(), "USD", "CNY", registry.observations[0].period, "period_average", "7", (registry.sources[0].id,))
        registry = replace(registry, historical_fx=(historical,))
        data["historical_fx_choices"] = [{"observation_id": registry.observations[0].id, "fx_id": historical.id}]
        scenario = data["scenarios"][0]
        scenario["future_fx"] = [future_fx(scenario["remaining_revenue"]["period"], "7", "fx_remaining")] + [future_fx(fy(y), "7.1", f"fx_{y}") for y in range(2027, 2032)]
        result = rows(evaluate_financial(data, registry))
        self.assertEqual(result[0]["native"]["revenue"]["display"], "100.000000")
        self.assertEqual(result[0]["target"]["revenue"]["display"], "700.000000")
        self.assertEqual(result[1]["target"]["revenue"]["display"], "781.000000")
        bad = replace(historical, kind="spot")
        with self.assertRaisesRegex(FinancialError, "same-period average"):
            evaluate_financial(data, replace(registry, historical_fx=(bad,)))
        bad = replace(historical, period=Period("2025-01-01", "2025-12-31", "annual"))
        with self.assertRaises(FinancialError): evaluate_financial(data, replace(registry, historical_fx=(bad,)))

    def test_missing_fx_keeps_native_and_does_not_rewrite_history(self):
        data, registry = fixture("USD")
        data["scenarios"][0]["future_fx"] = [future_fx(fy(y), "7", f"fx_{y}") for y in range(2027, 2032)]
        result = rows(evaluate_financial(data, registry))
        self.assertEqual(result[0]["native"]["revenue"]["display"], "100.000000")
        self.assertIsNone(result[0]["target"]["revenue"]["display"])
        self.assertEqual(result[1]["target"]["revenue"]["display"], "770.000000")
        self.assertEqual(registry.observations[0].amount.currency, "USD")

    def test_future_fx_positive_and_no_implicit_inverse(self):
        data, registry = fixture("USD")
        for rate in ("0", "-1"):
            data["scenarios"][0]["future_fx"] = [future_fx(fy(2027), rate, "bad_fx")]
            with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data["scenarios"][0]["future_fx"] = [future_fx(fy(2027), "0.14", "wrong_direction", from_currency="CNY", to_currency="USD")]
        self.assertIsNone(rows(evaluate_financial(data, registry))[1]["target"]["revenue"]["display"])
        data["scenarios"][0]["future_fx"] = [future_fx({"start": "2026-01-01", "end": "2026-06-30", "grain": "interim"}, "7", "not_future")]
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        with self.assertRaises(FinancialError): HistoricalFX(uid(), "USD", "CNY", registry.observations[0].period, "period_average", "7", ())

    def test_growth_negative_one_is_zero_but_less_is_rejected(self):
        data, registry = fixture()
        data["scenarios"][0]["growth"][0]["parameter"]["value"] = "-1"
        self.assertEqual(rows(evaluate_financial(data, registry))[1]["target"]["revenue"]["display"], "0.000000")
        data["scenarios"][0]["growth"][0]["parameter"]["value"] = "-1.01"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)

    def test_cost_ratio_over_one_produces_legal_loss(self):
        data, registry = fixture()
        data["scenarios"][0]["costs"][0]["values"] = annual_values("loss_cost", "1.2")
        self.assertEqual(rows(evaluate_financial(data, registry))[0]["target"]["operating_profit"]["display"], "-20.000000")

    def test_absolute_cost_and_signed_adjustment_follow_operating_bridge(self):
        data, registry = fixture()
        line = data["scenarios"][0]["costs"][0]
        line["mode"] = "amount"
        line["values"] = annual_values("absolute", "85", unit="million", currency="CNY")
        data["scenarios"][0]["costs"].append({"id": "adjust", "kind": "operating_adjustment", "label": "Explicit negative operating adjustment", "mode": "amount", "coverage": [], "coverage_basis": "Separate synthetic adjustment", "values": annual_values("adjust", "-5", unit="million", currency="CNY")})
        self.assertEqual(rows(evaluate_financial(data, registry))[0]["target"]["operating_profit"]["display"], "10.000000")

    def test_mixed_currency_costs_can_be_sufficient_in_target_only(self):
        data, registry = fixture("USD")
        scenario = data["scenarios"][0]
        scenario["costs"][0]["mode"] = "amount"
        scenario["costs"][0]["values"] = annual_values("cny_cost", "85", unit="million", currency="CNY")
        scenario["future_fx"] = [future_fx(fy(y), "7", f"fx_{y}") for y in range(2027, 2032)]
        result = rows(evaluate_financial(data, registry))[1]
        self.assertIsNone(result["native"]["operating_profit"]["display"])
        self.assertEqual(result["target"]["operating_profit"]["display"], "685.000000")

    def test_display_rounding_delta_is_not_a_negative_unallocated_plug(self):
        data, registry = fixture()
        data["scenarios"][0]["allocations"] = [allocation("0.0000005")]
        result = rows(evaluate_financial(data, registry))[0]["target"]["composition"]
        self.assertEqual(result["rows"][0]["amount"]["display"], "0.000000")
        self.assertEqual(result["rows"][1]["amount"]["display"], "100.000000")
        self.assertGreaterEqual(Decimal(result["rows"][1]["amount"]["raw_value"]), 0)
        self.assertIsNotNone(result["rounding_delta_million"])

    def test_duplicate_depreciation_and_missing_cost_coverage(self):
        data, registry = fixture()
        line = {"id": "depr", "kind": "depreciation", "label": "Duplicate depreciation", "mode": "amount", "coverage": ["depreciation"], "coverage_basis": "Synthetic duplicate", "values": annual_values("depr", "1", unit="million", currency="CNY")}
        data["scenarios"][0]["costs"].append(line)
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data["scenarios"][0]["costs"] = data["scenarios"][0]["costs"][:1]
        data["scenarios"][0]["costs"][0]["coverage"].remove("depreciation")
        result = rows(evaluate_financial(data, registry))[0]["target"]
        self.assertIsNone(result["operating_profit"]["display"])
        self.assertEqual(result["revenue"]["display"], "100.000000")
        data["scenarios"][0]["exclusions"] = [{"tag": "depreciation", "rationale": "Explicit synthetic assumption of no depreciation, not a historical fact", "source_refs": []}]
        self.assertEqual(rows(evaluate_financial(data, registry))[0]["target"]["operating_profit"]["display"], "15.000000")

    def test_capex_and_net_profit_cannot_be_operating_cost_or_revenue(self):
        data, registry = fixture()
        data["scenarios"][0]["costs"][0]["kind"] = "capex"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data, registry = fixture()
        data["interim_revenue_ref"] = registry.observations[2].id
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        capex = replace(registry.observations[0], id=uid(), metric="capex")
        registry = replace(registry, observations=registry.observations + (capex,))
        data["interim_revenue_ref"] = registry.observations[0].id
        data["scenarios"][0]["costs"][0]["values"][0]["parameter"]["anchor_observation_id"] = capex.id
        with self.assertRaisesRegex(FinancialError, "CAPEX/net profit"):
            evaluate_financial(data, registry)

    def test_zero_revenue_computed_share_is_null_not_zero(self):
        data, registry = fixture()
        registry = replace(registry, observations=(replace(registry.observations[0], amount=FinancialAmount("0", "CNY", "million")),) + registry.observations[1:])
        data["scenarios"][0]["remaining_revenue"]["value"] = "0"
        data["scenarios"][0]["allocations"] = [allocation("0.5", mode="share")]
        composition = rows(evaluate_financial(data, registry))[0]["target"]["composition"]
        self.assertEqual(composition["coverage"], "undefined_zero_revenue")
        self.assertTrue(all(v["share"]["display"] is None for v in composition["rows"]))

    def test_segment_overcoverage_fails_and_unallocated_is_not_fake_detail(self):
        data, registry = fixture()
        data["scenarios"][0]["allocations"] = [allocation("110")]
        with self.assertRaisesRegex(FinancialError, "segments exceed"):
            evaluate_financial(data, registry)
        data["scenarios"][0]["allocations"] = []
        composition = rows(evaluate_financial(data, registry))[0]["target"]["composition"]
        self.assertEqual(composition["coverage"], "unallocated_only")
        self.assertIsNone(composition["rows"][0]["amount"]["display"])
        self.assertEqual(composition["rows"][1]["amount"]["display"], "100.000000")

    def test_scope_definitions_do_not_mix_app_and_revenue_dimensions(self):
        data, registry = fixture()
        data["categories"][0]["dimension"] = "app"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data, registry = fixture()
        app = replace(registry.observations[0], scope_kind="app")
        with self.assertRaisesRegex(FinancialError, "group revenue baseline"):
            evaluate_financial(data, replace(registry, observations=(app,) + registry.observations[1:]))
        data, registry = fixture()
        data["categories"][0]["excludes"] = []
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)

    def test_missing_cost_and_conflict_propagate_without_zero_filling(self):
        data, registry = fixture()
        data["scenarios"][0]["costs"][0]["values"][1]["parameter"]["value"] = None
        result = rows(evaluate_financial(data, registry))
        self.assertIsNone(result[1]["target"]["operating_profit"]["display"])
        self.assertEqual(result[1]["target"]["revenue"]["display"], "110.000000")
        baseline = replace(registry.observations[0], evidence_basis="conflicted", amount=FinancialAmount(None, "CNY", "million"))
        result = rows(evaluate_financial(data, replace(registry, observations=(baseline,) + registry.observations[1:])))
        self.assertEqual(result[-1]["native"]["revenue"]["basis"], "conflicted")
        self.assertIsNone(result[-1]["target"]["revenue"]["display"])

    def test_known_observation_cannot_be_overridden_without_independent_flag(self):
        data, registry = fixture()
        observed = replace(registry.observations[0], id=uid(), period=Period("2026-07-01", "2026-12-31", "remaining"), amount=FinancialAmount("60", "CNY", "million"))
        registry = replace(registry, observations=registry.observations + (observed,))
        p = data["scenarios"][0]["remaining_revenue"]
        p.update(anchor_observation_id=observed.id, independent=False, value="61")
        with self.assertRaisesRegex(FinancialError, "known value changed"):
            evaluate_financial(data, registry)
        p["independent"] = True
        self.assertEqual(rows(evaluate_financial(data, registry))[0]["native"]["revenue"]["display"], "101.000000")
        self.assertEqual(registry.observation(observed.id).amount.value, "60")

    def test_curated_provenance_never_masquerades_as_original_bytes(self):
        data, registry = fixture()
        s = registry.sources[0]
        self.assertIsNone(s.raw_response_digest)
        with self.assertRaisesRegex(FinancialError, "not original response"):
            replace(s, raw_response_digest=s.curated_record_digest)
        original = replace(s, kind="historical_original", curated_record_digest=None, curated_commit=None, curated_entry_locator=None,
                           raw_response_digest="c" * 64, extracted_text_digest="d" * 64, retained_original_ref=uid())
        export = evaluate_financial(data, replace(registry, sources=(original,))).export()
        self.assertEqual(export["snapshot"]["registry_snapshot"]["sources"][0]["kind"], "historical_original")
        self.assertEqual(export["snapshot"]["registry_snapshot"]["sources"][0]["raw_response_digest"], "c" * 64)

    def test_model_cannot_submit_disclosed_basis_or_replace_registry(self):
        data, registry = fixture()
        data["scenarios"][0]["remaining_revenue"]["basis"] = "disclosed"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        with self.assertRaises(FinancialError): evaluate_financial({}, {"observations": []})

    def test_table_graph_digest_and_prior_snapshot_are_immutable(self):
        data, registry = fixture()
        old_input, old_registry = deepcopy(data), deepcopy(registry.data())
        snapshot = evaluate_financial(data, registry)
        before = snapshot.digest
        chart = snapshot.chart_spec()
        self.assertEqual(chart["snapshot_digest"], before)
        revenue = next(v for v in chart["series"] if v["metric"] == "revenue")
        self.assertEqual(revenue["values"], [r["target"]["revenue"]["display"] for r in rows(snapshot)])
        revenue["values"][0] = "fake"
        changed = deepcopy(data); changed["scenarios"][0]["growth"][0]["parameter"]["value"] = "0.2"
        self.assertNotEqual(evaluate_financial(changed, registry).digest, before)
        self.assertEqual(snapshot.digest, before)
        self.assertEqual(evaluate_financial(data, registry).digest, before)
        self.assertEqual((data, registry.data()), (old_input, old_registry))

    def test_single_parameter_sensitivity_21_points_keeps_other_inputs(self):
        data, registry = fixture()
        data["sensitivity"] = {"scenario_id": "base", "parameter_id": "g_2027", "points": [str(Decimal(i)/100) for i in range(21)]}
        snapshot = evaluate_financial(data, registry).export()["snapshot"]
        sensitivity = snapshot["sensitivity"]
        self.assertEqual(len(sensitivity), 21)
        self.assertEqual(sensitivity[0]["target_revenue"][-1], "146.410000")
        self.assertEqual(sensitivity[-1]["target_revenue"][-1], "175.692000")
        self.assertEqual(data["scenarios"][0]["growth"][0]["parameter"]["value"], "0.1")
        self.assertLessEqual(snapshot["operations_used"], 5000)

    def test_fx_sensitivity_does_not_compound_target_currency_growth(self):
        data, registry = fixture("USD")
        data["scenarios"][0]["future_fx"] = [future_fx(fy(y), "7", f"fx_{y}") for y in range(2027, 2032)]
        data["sensitivity"] = {"scenario_id": "base", "parameter_id": "fx_2027", "points": ["6", "8"]}
        cases = evaluate_financial(data, registry).export()["snapshot"]["sensitivity"]
        self.assertEqual((cases[0]["target_revenue"][1], cases[1]["target_revenue"][1]), ("660.000000", "880.000000"))
        self.assertEqual((cases[0]["target_revenue"][2], cases[1]["target_revenue"][2]), ("847.000000", "847.000000"))

    def test_period_overlap_and_accounting_basis_mismatch_rejected(self):
        data, registry = fixture()
        data["scenarios"][0]["remaining_revenue"]["period"]["start"] = "2026-06-01"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data, registry = fixture(); data["scenarios"][0]["accounting_basis"] = "different_scope"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)

    def test_bool_nan_huge_numbers_unknown_operation_and_limits(self):
        for value in (True, 1.0, "NaN", "Infinity", "1e999999999", "9"*100000, "1.1234567890123456789012345"):
            with self.assertRaises(FinancialError): number(value)
        data, registry = fixture(); data["operation"] = "eval"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)
        data, registry = fixture(); data["scenarios"] *= 4
        with self.assertRaises(FinancialResourceLimit): evaluate_financial(data, registry)
        data, registry = fixture(); data["sensitivity"] = {"scenario_id": "base", "parameter_id": "g_2027", "points": [str(i) for i in range(22)]}
        with self.assertRaises(FinancialResourceLimit): evaluate_financial(data, registry)

    def test_preflight_huge_spelling_never_constructs_decimal(self):
        for value in ("9"*100000, "1e999999999", "1e999", "NaN", True):
            with patch("web.backend.research.financial_policy.Decimal", side_effect=AssertionError("must reject before construction")):
                with self.assertRaises(FinancialError): number(value)

    def test_global_decimal_context_cannot_change_engine_results(self):
        data, registry = fixture()
        expected = evaluate_financial(data, registry).digest
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(evaluate_financial(data, registry).digest, expected)

    def test_three_scenarios_are_conditional_not_probability_bands(self):
        data, registry = fixture()
        base = data["scenarios"][0]
        for sid, growth in (("slower", "0.05"), ("faster", "0.2")):
            candidate = deepcopy(base); candidate["id"] = sid
            for entry in candidate["growth"]: entry["parameter"]["value"] = growth
            data["scenarios"].append(candidate)
        snapshot = evaluate_financial(data, registry)
        self.assertEqual(len(snapshot.table()), 3)
        self.assertFalse(snapshot.chart_spec()["probability_calibrated"])
        self.assertEqual(snapshot.table()[2]["years"][-1]["target"]["revenue"]["display"], "248.832000")

    def test_three_scenarios_five_categories_fit_cap_without_duplicate_same_currency(self):
        data, registry = fixture()
        ids = ["advertising", "commerce", "consumer", "enterprise", "unallocated"]
        data["categories"] = [{"id": i, "label": i, "definition": "Synthetic mutually exclusive monetization scenario", "dimension": "monetization", "excludes": [j for j in ids if j != i], "kind": "unallocated" if i == "unallocated" else "segment"} for i in ids]
        data["scenarios"][0]["allocations"] = [{"category_id": i, "mode": "share", "values": annual_values("alloc_" + i, "0.25")} for i in ids[:-1]]
        base = deepcopy(data["scenarios"][0])
        data["scenarios"] = [{**deepcopy(base), "id": i} for i in ("base", "slower", "faster")]
        snapshot = evaluate_financial(data, registry)
        encoded = snapshot.export()
        self.assertLessEqual(len(json.dumps(encoded, ensure_ascii=False, separators=(",", ":")).encode()), 128 * 1024)
        self.assertEqual(encoded["snapshot"]["scenarios"][0]["years"][0]["native"], {"same_as": "target"})
        table = snapshot.table()
        self.assertEqual(table[0]["years"][0]["native"], table[0]["years"][0]["target"])
        table[0]["years"][0]["native"]["revenue"]["display"] = "fake"
        self.assertNotEqual(table[0]["years"][0]["native"], table[0]["years"][0]["target"])

    def test_source_cutoff_and_unknown_time_qualification(self):
        data, registry = fixture()
        future = replace(registry.sources[0], published_at="2026-11-01", accessed_at="2026-11-01")
        with self.assertRaises(FinancialError): evaluate_financial(data, replace(registry, sources=(future,)))
        unknown = replace(registry.sources[0], published_at=None)
        out = evaluate_financial(data, replace(registry, sources=(unknown,))).export()["snapshot"]
        self.assertIn("source_publication_or_access_time_unknown", out["qualifications"])
        data["information_cutoff"] = "2027-01-01"
        with self.assertRaises(FinancialError): evaluate_financial(data, registry)

    def test_utf8_input_and_snapshot_export_caps_are_real_byte_limits(self):
        with self.assertRaises(FinancialResourceLimit): json_cap({"value": "测" * 50000})
        with self.assertRaises(FinancialResourceLimit): FinancialSnapshot("x" * (128 * 1024 + 1))
        data, registry = fixture()
        export = evaluate_financial(data, registry).export()
        self.assertLessEqual(len(json.dumps(export, ensure_ascii=False).encode()), 128 * 1024)

    def test_cooperative_step_deadline_and_operation_limits_are_explicit(self):
        with patch("web.backend.research.financial_policy.time.monotonic", side_effect=[0.0, 3.0]):
            m = Meter()
            with self.assertRaises(FinancialResourceLimit): m.tick()
        m = Meter()
        with self.assertRaises(FinancialResourceLimit):
            for _ in range(5001): m.tick()


if __name__ == "__main__":
    unittest.main()
