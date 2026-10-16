"""Real D2 exports with independent arithmetic expectations; no network/model.

Core consumers do not prove product isolation. Linux-only combined AS/CPU/wall
tests are explicitly skipped on hosts that must fail closed at the entrypoint.
"""
from copy import deepcopy
import hashlib
from decimal import localcontext
import math
import multiprocessing
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from web.backend.research.formula_schemas import FormulaCheckInput, FormulaInputError, FormulaLimit, Node, decimal_text, digest
from web.backend.research.formula_policy import CORPUS_DIGEST, calc, rational
from web.backend.research.formula_check import FormulaChecker, evaluate_fixed_templates, _guard_probe


def uid(): return str(uuid4())
def sym(value): return {"op": "symbol", "id": value}
def const(value): return {"op": "const", "value": str(value)}
def binary(op, a, b): return {"op": op, "left": a, "right": b}
def neg(a): return {"op": "neg", "arg": a}
def derivative(state, clock): return {"op": "derivative", "state_symbol": state, "time_symbol": clock, "order": 1}


LITTLE = ["same_boundary", "finite_long_run_means", "effective_arrivals", "same_population"]
MM1 = LITTLE + ["poisson_arrivals", "independent_exponential_service", "single_server", "fcfs", "infinite_capacity", "no_abandonment", "constant_parameters", "stable_regime"]
PASSIVE = ["constant_parameters", "no_external_input", "positive_parameters"]
LOCAL = PASSIVE + ["stable_equilibrium", "local_linear", "small_perturbation", "fixed_equilibrium"]


def side(template="little", prefix="a", *, electrical=False, values=None, amplitude="10", output="w"):
    specs, assumptions, initial = {}, [], []
    names = lambda role: prefix + "_" + role
    s = lambda role: sym(names(role))
    if template == "little":
        family, locator = "queue_flow", "Q1"
        specs = {"l": ("count", "system_count", None), "lambda": ("count_per_s", "effective_arrival_rate", "2"), "w": ("s", "system_time", "3")}
        equation = binary("eq", s("l"), binary("mul", s("lambda"), s("w")))
        assumptions = LITTLE
    elif template == "mm1":
        family, locator = "queue_flow", "Q2"
        specs = {"lambda": ("count_per_s", "effective_arrival_rate", "2"), "mu": ("count_per_s", "service_capacity", "3")}
        gap = binary("sub", s("mu"), s("lambda"))
        if output == "w":
            specs["w"] = ("s", "system_time", None); rhs = binary("div", const(1), gap)
        elif output == "rho":
            specs["rho"] = ("one", "ratio", None); rhs = binary("div", s("lambda"), s("mu"))
        elif output == "wq":
            specs["wq"] = ("s", "queue_wait", None); rhs = binary("div", s("lambda"), binary("mul", s("mu"), gap))
        elif output == "l":
            specs["l"] = ("count", "system_count", None); specs["w"] = ("s", "system_time", None); rhs = binary("mul", s("lambda"), s("w"))
        else:
            specs["lq"] = ("count", "queue_count", None); specs["wq"] = ("s", "queue_wait", None); rhs = binary("mul", s("lambda"), s("wq"))
        equation = binary("eq", s(output), rhs)
        assumptions = MM1
    elif template == "passive_decay":
        family, locator = "first_order_storage", "T1"
        specs = {"x": ("V" if electrical else "K", "state_difference", None), "t": ("s", "time", None),
                 "r": ("ohm" if electrical else "K_per_W", "electrical_resistance" if electrical else "thermal_resistance", "3" if electrical else "2"),
                 "c": ("F" if electrical else "J_per_K", "electrical_capacity" if electrical else "thermal_capacity", "2" if electrical else "3")}
        equation = binary("eq", binary("mul", s("c"), derivative(names("x"), names("t"))), binary("div", neg(s("x")), s("r")))
        assumptions = PASSIVE + (["ideal_isolated_rc"] if electrical else ["lumped_state", "constant_environment"])
        if amplitude is not None:
            initial = [{"state_symbol": names("x"), "at_time": "0", "value": amplitude, "declared_satisfied": True}]
    else:
        family, locator = "local_recovery", "L1"
        specs = {"delta": ("one", "local_state_difference", None), "t": ("s", "time", None), "k": ("inverse_s", "recovery_rate", "0.5")}
        equation = binary("eq", derivative(names("delta"), names("t")), neg(binary("mul", s("k"), s("delta"))))
        assumptions = LOCAL
        if amplitude is not None:
            initial = [{"state_symbol": names("delta"), "at_time": "0", "value": amplitude, "declared_satisfied": True}]
    return {"id": uid(), "revision": 1, "family": family, "template_id": template, "original_display": "Fixture typed equation; display is not parsed.",
            "expression": equation,
            "symbols": [{"id": names(role), "role": role, "unit_id": unit, "quantity": quantity, "value": (values or {}).get(role, value)} for role, (unit, quantity, value) in specs.items()],
            "assumptions": [{"id": name, "statement": "Declared model condition: " + name, "declared_satisfied": True} for name in assumptions],
            "initial_conditions": initial, "boundary_conditions": [], "source_refs": [{"id": uid(), "revision": 1, "content_digest": CORPUS_DIGEST, "provenance": "curated_reference", "locator": "SOURCE_CORPUS.md#" + locator}], "measure_scope": "system"}


def request(left=None, right=None, *, scope="equation_form", checks=None, points=None):
    return {"research_id": uid(), "input_revision": 1, "task_id": uid(), "attempt": 1,
            "comparison_scope": scope, "left": left or side(), "right": right or side(prefix="b"),
            "requested_checks": checks or ["template", "dimensions", "canonical_transform", "bounded_numeric"],
            "sample_points": (["0"] if (left or {}).get("template_id", "little") in {"little", "mm1"} else ["0", "1", "20"]) if points is None else points}


def core(data):
    return evaluate_fixed_templates(FormulaCheckInput.parse(data))


def outcomes(result): return {v.check_kind: v for v in result.outcomes}


def condition(form, key, value):
    next(v for v in form["assumptions"] if v["id"] == key)["declared_satisfied"] = value


class FormulaConsumers(unittest.TestCase):
    def test_queue_positive_consumer_with_exact_golden_values(self):
        result = core(request())
        self.assertTrue(all(v.status == "passed" for v in result.outcomes))
        self.assertEqual(outcomes(result)["bounded_numeric"].samples[0]["left"]["value"], "6")
        expected = {"w": "1", "wq": "2/3", "rho": "2/3", "l": "2", "lq": "4/3"}
        for output, value in expected.items():
            result = core(request(side("mm1", output=output), side("mm1", "b", output=output)))
            self.assertEqual(outcomes(result)["bounded_numeric"].samples[0]["left"]["value"], value)
        self.assertEqual(result.resource_guard, "pure_core_not_a_sandbox")

    def test_thermal_electrical_positive_consumer_keeps_units_and_amplitudes(self):
        result = core(request(side("passive_decay"), side("passive_decay", "b", electrical=True, amplitude="5"), scope="initial_value_problem"))
        self.assertTrue(all(v.status == "passed" for v in result.outcomes))
        self.assertEqual(outcomes(result)["canonical_transform"].relation, "conditional_model_equivalence")
        sample = outcomes(result)["bounded_numeric"].samples[1]
        self.assertEqual((sample["left"]["tau"], sample["right"]["tau"]), ("6", "6"))
        self.assertAlmostEqual(float(sample["left"]["actual_state"]), 10 / math.e)
        self.assertAlmostEqual(float(sample["right"]["actual_state"]), 5 / math.e)
        self.assertNotEqual(sample["left"]["actual_state"], sample["right"]["actual_state"])

    def test_local_positive_consumer_does_not_predict_reality(self):
        result = core(request(side("linear_stable", amplitude="2"), side("linear_stable", "b", values={"k": "0.25"}, amplitude="3"), scope="initial_value_problem"))
        sample = outcomes(result)["bounded_numeric"].samples[1]
        self.assertEqual(sample["left"]["tau"], "2")
        self.assertAlmostEqual(float(sample["left"]["actual_state"]), 2 / math.e)
        self.assertEqual(outcomes(result)["canonical_transform"].relation, "local_approximation")
        self.assertTrue(any("collapse date" in v for v in result.limitations))

    def test_queue_counterexample_at_and_above_stability_boundary(self):
        for lam in ("3", "4"):
            result = core(request(side("mm1", values={"lambda": lam}), side("mm1", "b")))
            self.assertEqual(outcomes(result)["template"].status, "passed")
            self.assertEqual(outcomes(result)["dimensions"].status, "passed")
            self.assertEqual(outcomes(result)["canonical_transform"].reason, "no_mm1_steady_state")
            self.assertEqual(outcomes(result)["bounded_numeric"].status, "failed")

    def test_same_equation_zero_nonzero_pair_has_different_scope_results(self):
        data = request(side("passive_decay", amplitude="0"), side("passive_decay", "b", amplitude="2"))
        equation = core(data)
        self.assertEqual(outcomes(equation)["canonical_transform"].status, "passed")
        data["comparison_scope"] = "initial_value_problem"
        ivp = core(data)
        self.assertEqual(outcomes(ivp)["canonical_transform"].relation, "not_equivalent")
        self.assertEqual(outcomes(ivp)["canonical_transform"].status, "failed")
        self.assertNotEqual(equation.input_digest, ivp.input_digest)
        self.assertEqual(ivp.comparison_scope, "initial_value_problem")

    def test_missing_initial_only_blocks_initial_problem_not_other_checks(self):
        data = request(side("passive_decay", amplitude=None), side("passive_decay", "b", amplitude=None))
        self.assertTrue(all(v.status == "passed" for v in core(data).outcomes))
        data["comparison_scope"] = "initial_value_problem"
        o = outcomes(core(data))
        self.assertEqual((o["template"].status, o["dimensions"].status), ("passed", "passed"))
        self.assertEqual((o["canonical_transform"].status, o["bounded_numeric"].status), ("inconclusive", "inconclusive"))

    def test_negative_nonzero_initial_normalization_is_legal(self):
        result = core(request(side("passive_decay", amplitude="-10"), side("passive_decay", "b", electrical=True, amplitude="-5"), scope="initial_value_problem"))
        self.assertTrue(all(v.status == "passed" for v in result.outcomes))
        self.assertIn("state_normalize", [s["kind"] for s in outcomes(result)["canonical_transform"].trace])
        self.assertLess(float(outcomes(result)["bounded_numeric"].samples[1]["left"]["actual_state"]), 0)

    def test_both_zero_initials_do_not_divide_by_zero(self):
        result = core(request(side("passive_decay", amplitude="0"), side("passive_decay", "b", electrical=True, amplitude="0"), scope="initial_value_problem"))
        self.assertTrue(all(v.status == "passed" for v in result.outcomes))
        self.assertNotIn("state_normalize", [s["kind"] for s in outcomes(result)["canonical_transform"].trace])
        self.assertEqual(outcomes(result)["bounded_numeric"].samples[1]["left"]["actual_state"], "0")
        self.assertEqual(outcomes(result)["bounded_numeric"].samples[1]["left"]["meaning"], "zero_solution_no_state_normalization")

    def test_local_counterexample_negative_rate_and_external_driver(self):
        for k in ("0", "-1"):
            result = core(request(side("linear_stable", values={"k": k}), side("linear_stable", "b")))
            self.assertEqual(outcomes(result)["canonical_transform"].reason, "nonpositive_decay_parameter")
        form = side("linear_stable")
        condition(form, "no_external_input", None)
        self.assertEqual(outcomes(core(request(form, side("linear_stable", "b"))))["canonical_transform"].status, "inconclusive")

    def test_expression_identity_is_separate_from_model_assumptions(self):
        left, right = side("mm1"), side("mm1", "b")
        for form in (left, right):
            for entry in form["assumptions"]: entry["declared_satisfied"] = None
        data = request(left, right, scope="expression", checks=["dimensions", "canonical_transform"])
        result = core(data)
        self.assertEqual(outcomes(result)["canonical_transform"].relation, "algebraic_identity")
        data["comparison_scope"] = "equation_form"
        self.assertEqual(outcomes(core(data))["canonical_transform"].status, "inconclusive")

    def test_cross_physical_units_are_not_literal_expression_identity(self):
        data = request(side("passive_decay"), side("passive_decay", "b", electrical=True), scope="expression", checks=["canonical_transform"])
        result = core(data)
        self.assertEqual(result.outcomes[0].status, "inconclusive")
        self.assertNotEqual(result.outcomes[0].relation, "algebraic_identity")

    def test_cross_family_decay_retains_local_scope(self):
        result = core(request(side("passive_decay"), side("linear_stable", "b")))
        self.assertEqual(outcomes(result)["canonical_transform"].relation, "local_approximation")

    def test_little_boundary_and_population_must_be_explicit(self):
        for key in LITTLE:
            left = side(); condition(left, key, None)
            result = core(request(left))
            self.assertEqual(outcomes(result)["canonical_transform"].reason, "precondition_unknown:" + key)
        left = side(); left["symbols"][2]["quantity"] = "queue_wait"
        self.assertEqual(outcomes(core(request(left)))["dimensions"].status, "failed")

    def test_workday_does_not_implicitly_convert_to_seconds(self):
        left = side()
        next(v for v in left["symbols"] if v["role"] == "lambda")["unit_id"] = "count_per_workday"
        self.assertEqual(outcomes(core(request(left)))["dimensions"].reason, "mixed_time_basis")
        next(v for v in left["symbols"] if v["role"] == "w")["unit_id"] = "workday"
        self.assertEqual(outcomes(core(request(left)))["canonical_transform"].reason, "no_implicit_workday_conversion")

    def test_unknown_unit_is_unsupported_not_not_equivalent(self):
        left = side(); left["symbols"][0]["unit_id"] = "unregistered"
        o = outcomes(core(request(left)))["dimensions"]
        self.assertEqual((o.status, o.relation), ("unsupported", "undetermined"))

    def test_zero_arrivals_compute_zero_without_reverse_division(self):
        result = core(request(side(values={"lambda": "0"}), side("little", "b", values={"lambda": "0"})))
        self.assertEqual(outcomes(result)["bounded_numeric"].samples[0]["left"]["value"], "0")

    def test_numeric_disagreement_or_missing_inputs_do_not_make_identity(self):
        result = core(request(side(), side("little", "b", values={"lambda": "3"})))
        self.assertEqual(outcomes(result)["bounded_numeric"].status, "failed")
        self.assertEqual(outcomes(result)["bounded_numeric"].relation, "undetermined")
        result = core(request(side(values={"w": None})))
        self.assertEqual(outcomes(result)["bounded_numeric"].status, "inconclusive")
        result = core(request(side(values={"l": "7"})))
        self.assertEqual(outcomes(result)["bounded_numeric"].reason, "provided_output_breaks_exact_relation")
        result = core(request(side("mm1", values={"w": "2"}, output="l"), side("mm1", "b", output="l")))
        self.assertEqual(outcomes(result)["bounded_numeric"].reason, "provided_intermediate_breaks_mm1_relation")

    def test_literal_expression_only_checks_its_actual_denominators(self):
        data = request(side("passive_decay", values={"c": "0"}), side("passive_decay", "b", values={"c": "0"}), scope="expression", checks=["canonical_transform"])
        self.assertEqual(core(data).outcomes[0].relation, "algebraic_identity")
        data["comparison_scope"] = "equation_form"
        self.assertEqual(core(data).outcomes[0].status, "failed")

    def test_shape_and_unit_checks_do_not_require_initial_conditions(self):
        left = side("passive_decay", amplitude=None)
        data = request(left, scope="initial_value_problem", checks=["template", "dimensions"])
        data["right"] = None
        self.assertTrue(all(v.status == "passed" for v in core(data).outcomes))

    def test_scope_is_mandatory_and_hashed_in_both_results(self):
        data = request()
        before = core(data)
        changed = deepcopy(data); changed["comparison_scope"] = "expression"
        self.assertNotEqual(before.input_digest, core(changed).input_digest)
        self.assertEqual(before.data()["comparison_scope"], "equation_form")
        self.assertIn("output_digest", before.data())
        self.assertEqual((before.research_id, before.input_revision, before.task_id, before.attempt), (data["research_id"], 1, data["task_id"], 1))
        self.assertEqual(before.formula_refs[0]["id"], data["left"]["id"])
        del data["comparison_scope"]
        with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)

    def test_exact_trace_is_a_digest_chain_with_permitted_operations(self):
        result = core(request(side("passive_decay"), side("passive_decay", "b", electrical=True), scope="initial_value_problem"))
        trace = outcomes(result)["canonical_transform"].trace
        for a, b in zip(trace, trace[1:]): self.assertEqual(a["output_digest"], b["input_digest"])
        self.assertTrue(all(v["kind"] in {"rename_bijection", "constant_fold", "associate", "commute", "divide_nonzero", "positive_time_scale", "state_normalize", "substitute_constant"} for v in trace))

    def test_curated_source_version_is_not_product_fetch(self):
        result = core(request())
        self.assertEqual(result.source_refs[0].content_digest, "5adc721f04f80c7d0069e1c5e13201fab10b6648674491f3ca6557a2e039e0d6")
        self.assertEqual(result.source_refs[0].provenance, "curated_reference")
        data = request(); data["left"]["source_refs"][0]["content_digest"] = "f" * 64
        self.assertTrue(all(v.status == "unsupported" for v in core(data).outcomes))

    def test_parameter_and_normalized_domain_bounds(self):
        for key in ("r", "c"):
            result = core(request(side("passive_decay", values={key: "-1"}), side("passive_decay", "b")))
            self.assertEqual(outcomes(result)["canonical_transform"].status, "failed")
        result = core(request(side("passive_decay"), side("passive_decay", "b"), points=["21"]))
        self.assertEqual(outcomes(result)["bounded_numeric"].status, "resource_limit")
        result = core(request(side(values={"lambda": "1e12", "w": "1e12"}), side()))
        self.assertEqual(outcomes(result)["bounded_numeric"].status, "resource_limit")

    def test_unknown_template_and_unregistered_variation_do_not_invoke_solver(self):
        left = side(); left["template_id"] = "arbitrary_queue_network"
        self.assertTrue(all(v.status == "unsupported" for v in core(request(left)).outcomes))
        left = side(); left["expression"]["right"] = {"op": "exp", "arg": sym("a_lambda")}
        self.assertEqual(outcomes(core(request(left)))["template"].status, "unsupported")

    def test_decimal_preflight_precedes_large_integer_construction(self):
        for value in ("9" * 100000, "1e999999999", "1e999", "NaN", "Infinity", True, 1.0):
            with patch("web.backend.research.formula_schemas.Decimal", side_effect=AssertionError("must not construct")):
                with self.assertRaises(FormulaInputError): decimal_text(value)
        self.assertEqual(decimal_text("-0.000"), "0")
        with self.assertRaises(FormulaLimit): decimal_text("1.234567890123456789")
        with localcontext() as context:
            context.prec = 2
            self.assertEqual(decimal_text("1.23456789"), "1.23456789")
            self.assertEqual(str(rational("1.23456789")), "123456789/100000000")

    def test_numeric_tolerance_is_explicit_and_cannot_be_user_overridden(self):
        data = request(side("passive_decay"), side("passive_decay", "b"))
        o = outcomes(core(data))["bounded_numeric"]
        self.assertEqual(o.tolerance["absolute"], "1e-10")
        self.assertEqual(o.tolerance["relative"], "1e-8")
        data["tolerance"] = {"absolute": "100"}
        with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)

    def test_queue_fixed_case_is_not_repeated_as_time_series_validation(self):
        result = core(request(points=["0", "1"]))
        self.assertEqual(outcomes(result)["bounded_numeric"].status, "unsupported")
        self.assertEqual(outcomes(result)["bounded_numeric"].relation, "undetermined")

    def test_malicious_ast_bool_and_nonfinite_values_rejected(self):
        mutations = [dict(op="call", name="eval"), dict(op="symbol", id="__import__"), dict(op="const", value=True),
                     dict(op="pow_int", base=const(1), exponent=True), dict(op="derivative", state_symbol="x", time_symbol="t", order=2)]
        for node in mutations:
            data = request(); data["left"]["expression"] = node
            with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)
        data = request(); data["probe"] = "probe_cpu"
        with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)

    def test_ast_depth_count_and_fraction_intermediate_limits(self):
        node = sym("a_lambda")
        for _ in range(18): node = neg(node)
        with self.assertRaises(FormulaLimit): Node.parse(node)
        node = const(1)
        for _ in range(7): node = binary("add", node, deepcopy(node))
        with self.assertRaises(FormulaLimit): Node.parse(node)
        value = rational("1e-12")
        with self.assertRaises(FormulaLimit):
            for _ in range(10): value = calc("mul", value, rational("1e-12"))

    def test_claimed_source_versions_and_alias_bijections_cannot_conflict(self):
        data = request(); data["right"]["source_refs"][0]["id"] = data["left"]["source_refs"][0]["id"]
        data["right"]["source_refs"][0]["revision"] = 2
        with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)
        data = request(); data["left"]["symbols"][0]["role"] = data["left"]["symbols"][1]["role"]
        with self.assertRaises(FormulaInputError): FormulaCheckInput.parse(data)


class ResourceBoundaryTests(unittest.TestCase):
    def test_exported_entry_fails_closed_on_unsupported_memory_guard(self):
        result = FormulaChecker.check(request(), still_authorized=lambda: True)
        if sys.platform == "linux":
            self.assertTrue(all(v.status == "passed" for v in result.outcomes))
            self.assertIn("baseline_plus_128mib", result.resource_guard)
        else:
            self.assertTrue(all(v.status == "unsupported" and v.reason == "memory_guard_unavailable" for v in result.outcomes))
            self.assertEqual(result.resource_guard, "not_executed")

    def test_revoke_before_execution_does_not_run_math(self):
        result = FormulaChecker.check(request(), still_authorized=lambda: False)
        self.assertTrue(all(v.reason == "access_ended" for v in result.outcomes))

    def test_revoke_after_spawn_discards_late_result_and_reaps(self):
        before = {p.pid for p in multiprocessing.active_children()}
        calls = [0]
        def authorized():
            calls[0] += 1
            return calls[0] == 1
        result = FormulaChecker.check(request(), still_authorized=authorized)
        self.assertTrue(all(v.reason == "access_ended" for v in result.outcomes))
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_actual_cpu_fault_probe_is_killed_and_reaped(self):
        before = {p.pid for p in multiprocessing.active_children()}
        state = _guard_probe("probe_cpu")
        self.assertEqual(state, "cpu_limited")
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_actual_wall_fault_probe_is_stopped_and_reaped(self):
        before = {p.pid for p in multiprocessing.active_children()}
        start = time.monotonic()
        self.assertEqual(_guard_probe("probe_wall"), "limited")
        self.assertGreaterEqual(time.monotonic() - start, 1.7)
        self.assertLess(time.monotonic() - start, 3.5)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    @unittest.skipUnless(sys.platform == "linux", "combined RLIMIT_AS extra-memory fault probe requires Linux; never claim Mac verified")
    def test_actual_extra_memory_fault_probe(self):
        self.assertEqual(_guard_probe("probe_memory"), "memory_limited")

    @unittest.skipUnless(sys.platform == "linux", "guarded positive consumers require supported Linux memory guard")
    def test_three_positive_consumers_through_guarded_entry(self):
        for data in (request(), request(side("passive_decay"), side("passive_decay", "b", electrical=True), scope="initial_value_problem"),
                     request(side("linear_stable"), side("linear_stable", "b"), scope="initial_value_problem")):
            result = FormulaChecker.check(data, still_authorized=lambda: True)
            self.assertTrue(all(v.status == "passed" for v in result.outcomes))


if __name__ == "__main__":
    unittest.main()
