"""Four finite templates; exact arithmetic is stdlib Fraction, not a CAS."""
from decimal import Decimal
from fractions import Fraction
import math

from .formula_schemas import FormulaInputError, FormulaLimit, decimal_text, digest

POLICY = "formula-policy-v1-d2-candidate"
CORPUS_DIGEST = "5adc721f04f80c7d0069e1c5e13201fab10b6648674491f3ca6557a2e039e0d6"
CORPUS_LOCATORS = {"little": {"SOURCE_CORPUS.md#Q1", "SOURCE_CORPUS.md#Q3"}, "mm1": {"SOURCE_CORPUS.md#Q2", "SOURCE_CORPUS.md#Q3"},
                   "passive_decay": {"SOURCE_CORPUS.md#T1"}, "linear_stable": {"SOURCE_CORPUS.md#L1", "SOURCE_CORPUS.md#L2"}}
ABS_TOL, REL_TOL = 1e-10, 1e-8
MAX_VALUE = Fraction(10**12)

# (M,L,T,I,Theta), with semantic tags/time bases checked separately below.
UNITS = {
    "one": (0, 0, 0, 0, 0), "count": (0, 0, 0, 0, 0),
    "s": (0, 0, 1, 0, 0), "workday": (0, 0, 1, 0, 0),
    "count_per_s": (0, 0, -1, 0, 0), "inverse_s": (0, 0, -1, 0, 0),
    "count_per_workday": (0, 0, -1, 0, 0), "inverse_workday": (0, 0, -1, 0, 0),
    "K": (0, 0, 0, 0, 1), "J_per_K": (1, 2, -2, 0, -1), "K_per_W": (-1, -2, 3, 0, 1),
    "V": (1, 2, -3, -1, 0), "A": (0, 0, 0, 1, 0), "ohm": (1, 2, -3, -2, 0), "F": (-1, -2, 4, 2, 0),
}
TEMPLATES = {"little": "queue_flow", "mm1": "queue_flow", "passive_decay": "first_order_storage", "linear_stable": "local_recovery"}
LITTLE = ("same_boundary", "finite_long_run_means", "effective_arrivals", "same_population")
MM1 = LITTLE + ("poisson_arrivals", "independent_exponential_service", "single_server", "fcfs", "infinite_capacity", "no_abandonment", "constant_parameters", "stable_regime")
PASSIVE = ("constant_parameters", "no_external_input", "positive_parameters")
LOCAL = ("constant_parameters", "no_external_input", "positive_parameters", "stable_equilibrium", "local_linear", "small_perturbation", "fixed_equilibrium")


class PolicyIssue(Exception):
    def __init__(self, status, reason):
        self.status, self.reason = status, reason


def rational(value):
    # Revalidate before integer construction even for a future direct caller.
    return limit(Fraction(Decimal(decimal_text(value))))


def limit(value):
    if value.numerator.bit_length() > 256 or value.denominator.bit_length() > 256 or abs(value) > MAX_VALUE:
        raise FormulaLimit("rational intermediate limit")
    return value


def calc(op, a, b=None):
    if op == "add": result = a + b
    elif op == "sub": result = a - b
    elif op == "mul": result = a * b
    elif op == "div":
        if b == 0: raise PolicyIssue("failed", "division_by_zero")
        result = a / b
    else: raise FormulaInputError("unregistered arithmetic")
    return limit(result)


def s(role): return ("symbol", role)
def c(value): return ("const", Fraction(value))
def neg(value): return ("neg", value)
def div(a, b): return ("div", a, b)
def mul(*values): return ("mul", *sorted(values, key=repr))
def eq(a, b): return ("eq", a, b)
def derivative(state): return ("derivative", s(state), s("t"))


def normalized(node, symbols, stage="commute"):
    """Only literal constant folds, alias bijection and add/mul commutation.

    Does not cancel unknown denominators, differentiate or simplify strings.
    """
    if node.op == "symbol":
        if node.value not in symbols: raise PolicyIssue("unsupported", "undeclared_symbol")
        return s(symbols[node.value].role)
    if node.op == "const": return ("const", rational(node.value))
    args = tuple(normalized(n, symbols, stage) for n in node.args)
    if node.op == "derivative": return (node.op, *args)
    if stage == "rename_bijection":
        return (node.op, *args, node.value) if node.op == "pow_int" else (node.op, *args)
    if node.op == "neg":
        return ("const", limit(-args[0][1])) if args[0][0] == "const" else neg(args[0])
    if node.op in {"add", "sub", "mul", "div"} and all(a[0] == "const" for a in args):
        return ("const", calc(node.op, args[0][1], args[1][1]))
    if node.op in {"add", "mul"} and stage in {"associate", "commute"}:
        flat = []
        for arg in args:
            flat.extend(arg[1:] if arg[0] == node.op else (arg,))
        return (node.op, *(sorted(flat, key=repr) if stage == "commute" else flat))
    if node.op == "pow_int":
        if args[0][0] == "const":
            value = args[0][1]
            if value == 0 and node.value <= 0: raise PolicyIssue("failed", "undefined_power")
            return ("const", limit(value ** node.value))
        return (node.op, args[0], node.value)
    return (node.op, *args)


def recognize(form):
    if TEMPLATES.get(form.template_id) != form.family:
        raise PolicyIssue("unsupported", "family_or_template")
    symbols = {v.id: v for v in form.symbols}
    tree = normalized(form.expression, symbols)
    if form.template_id == "little":
        choices = {"l": eq(s("l"), mul(s("lambda"), s("w")))}
    elif form.template_id == "mm1":
        difference = ("sub", s("mu"), s("lambda"))
        choices = {"rho": eq(s("rho"), div(s("lambda"), s("mu"))),
                   "w": eq(s("w"), div(c(1), difference)),
                   "wq": eq(s("wq"), div(s("lambda"), mul(s("mu"), difference))),
                   "l": eq(s("l"), mul(s("lambda"), s("w"))),
                   "lq": eq(s("lq"), mul(s("lambda"), s("wq")))}
    elif form.template_id == "passive_decay":
        d = derivative("x")
        choices = {"x": eq(mul(s("c"), d), div(neg(s("x")), s("r"))),
                   "x_alt": eq(mul(s("c"), d), neg(div(s("x"), s("r")))),
                   "x_solved": eq(d, div(neg(s("x")), mul(s("r"), s("c")))),
                   "tau": eq(s("tau"), mul(s("r"), s("c")))}
        for index, denominator in enumerate((s("tau"), mul(s("r"), s("c")))):
            for variant, exponent in enumerate((div(neg(s("t")), denominator), neg(div(s("t"), denominator)))):
                choices[f"solution_{index}_{variant}"] = eq(s("x"), mul(s("x0"), ("exp", exponent)))
    else:
        choices = {"delta": eq(derivative("delta"), neg(mul(s("k"), s("delta")))),
                   "delta_alt": eq(derivative("delta"), mul(neg(s("k")), s("delta"))),
                   "tau": eq(s("tau"), div(c(1), s("k")))}
        for index, exponent in enumerate((neg(mul(s("k"), s("t"))), mul(neg(s("k")), s("t")),
                                           div(neg(s("t")), s("tau")), neg(div(s("t"), s("tau"))))):
            choices[f"solution_{index}"] = eq(s("delta"), mul(s("delta0"), ("exp", exponent)))
    for output, pattern in choices.items():
        if tree == pattern:
            return output.split("_")[0], tree
    raise PolicyIssue("unsupported", "outside_finite_template_forms")


def roles(form):
    return {v.role: v for v in form.symbols}


def form_kind(form):
    output, _ = recognize(form)
    return "timescale" if output == "tau" else "solution" if output == "solution" else "ode_or_relation"


def basis(unit):
    if unit in {"workday", "count_per_workday", "inverse_workday"}: return "workday"
    if unit in {"s", "count_per_s", "inverse_s"}: return "s"
    return None


def dimensions(form):
    if TEMPLATES.get(form.template_id) != form.family:
        raise PolicyIssue("unsupported", "family_or_template")
    syms = {v.id: v for v in form.symbols}
    for sym in form.symbols:
        if sym.unit_id not in UNITS: raise PolicyIssue("unsupported", "unregistered_unit")
    def visit(node):
        if node.op == "symbol":
            if node.value not in syms: raise PolicyIssue("unsupported", "undeclared_symbol")
            return UNITS[syms[node.value].unit_id], basis(syms[node.value].unit_id)
        if node.op == "const": return UNITS["one"], None
        parts = [visit(n) for n in node.args]
        if node.op == "neg": return parts[0]
        if node.op == "exp":
            if parts[0][0] != UNITS["one"]: raise PolicyIssue("failed", "exp_requires_dimensionless_argument")
            return UNITS["one"], None
        if node.op == "pow_int":
            vector = tuple(v * node.value for v in parts[0][0])
            if any(abs(v) > 8 for v in vector): raise FormulaLimit("dimension exponent limit")
            return vector, parts[0][1] if node.value else None
        (a, at), (b, bt) = parts
        if at and bt and at != bt: raise PolicyIssue("failed", "mixed_time_basis")
        if node.op in {"add", "sub", "eq"}:
            if a != b: raise PolicyIssue("failed", "dimension_mismatch")
            return a, at or bt
        sign = 1 if node.op == "mul" else -1
        vector = tuple(x + sign * y for x, y in zip(a, b))
        if any(abs(v) > 8 for v in vector): raise FormulaLimit("dimension exponent limit")
        return vector, at or bt
    visit(form.expression)
    r = roles(form)
    def require(role, unit, quantity):
        if role not in r: raise PolicyIssue("inconclusive", "missing_role:" + role)
        if r[role].unit_id not in unit or r[role].quantity != quantity:
            raise PolicyIssue("failed", "unit_or_semantic_role:" + role)
    if form.template_id in {"little", "mm1"}:
        if form.measure_scope not in {"system", "queue"}: raise PolicyIssue("unsupported", "queue_measure_scope")
        require("lambda", {"count_per_s", "count_per_workday"}, "effective_arrival_rate")
        tb = basis(r["lambda"].unit_id)
        for role, sym in r.items():
            specs = {"lambda": ({"count_per_" + tb}, "effective_arrival_rate"),
                     "mu": ({"count_per_" + tb}, "service_capacity"), "rho": ({"one"}, "ratio"),
                     "l": ({"count"}, "queue_count" if form.template_id == "little" and form.measure_scope == "queue" else "system_count"),
                     "w": ({tb}, "queue_wait" if form.template_id == "little" and form.measure_scope == "queue" else "system_time"),
                     "wq": ({tb}, "queue_wait"), "lq": ({"count"}, "queue_count")}
            if role not in specs: raise PolicyIssue("unsupported", "extra_role")
            require(role, *specs[role])
        if form.template_id == "mm1": require("mu", {"count_per_" + tb}, "service_capacity")
    elif form.template_id == "passive_decay":
        kind = form_kind(form)
        if kind != "timescale":
            require("x", {"K", "V"}, "state_difference"); require("t", {"s"}, "time")
        thermal = r.get("x").unit_id == "K" if "x" in r else r.get("r") is not None and r["r"].unit_id == "K_per_W"
        rc = kind != "solution" or "r" in r or "c" in r
        if rc:
            if thermal:
                require("r", {"K_per_W"}, "thermal_resistance"); require("c", {"J_per_K"}, "thermal_capacity")
            else:
                require("r", {"ohm"}, "electrical_resistance"); require("c", {"F"}, "electrical_capacity")
        expected = {"tau", "r", "c"} if kind == "timescale" else {"x", "t"} | ({"r", "c"} if rc else {"tau"})
        if kind == "solution":
            expected.add("x0"); require("x0", {r["x"].unit_id}, "initial_state_difference")
            if "tau" in r: expected.add("tau")
        if "tau" in expected: require("tau", {"s"}, "time_constant")
        if set(r) != expected: raise PolicyIssue("unsupported", "extra_role")
    elif form.template_id == "linear_stable":
        kind = form_kind(form)
        rate = kind != "solution" or "k" in r
        if rate: require("k", {"inverse_s"}, "recovery_rate")
        expected = {"tau", "k"} if kind == "timescale" else {"delta", "t"} | ({"k"} if rate else {"tau"})
        if kind != "timescale":
            require("delta", {"one", "K", "V"}, "local_state_difference"); require("t", {"s"}, "time")
        if kind == "solution":
            expected.add("delta0"); require("delta0", {r["delta"].unit_id}, "initial_local_state_difference")
            if "tau" in r: expected.add("tau")
        if "tau" in expected: require("tau", {"s"}, "time_constant")
        if set(r) != expected: raise PolicyIssue("unsupported", "extra_role")
    else: raise PolicyIssue("unsupported", "family_or_template")
    if form.template_id in {"passive_decay", "linear_stable"} and form_kind(form) != "timescale":
        state = "x" if form.template_id == "passive_decay" else "delta"
        if r[state].value is not None or r["t"].value is not None:
            raise PolicyIssue("unsupported", "state_values_require_initial_or_sample_fields")
    return True


def declarations(form):
    return {v.id: v.declared_satisfied for v in form.assumptions + form.boundary_conditions}


def prerequisites(form, scope, *, numeric=False):
    r, d = roles(form), declarations(form)
    if scope == "expression" and not numeric:
        # Expression identity does not assert a queue's stochastic assumptions
        # or an IVP. Only denominators actually present need to be nonzero.
        values = {k: None if v.value is None else rational(v.value) for k, v in r.items()}
        if form.template_id == "mm1":
            output, _ = recognize(form)
            if output in {"rho", "wq"}:
                if values.get("mu") == 0: raise PolicyIssue("failed", "division_by_zero")
                if values.get("mu") is None and d.get("stable_regime") is not True: raise PolicyIssue("inconclusive", "denominator_nonzero_unknown")
            if output in {"w", "wq"}:
                if values.get("mu") is None or values.get("lambda") is None:
                    if d.get("stable_regime") is not True: raise PolicyIssue("inconclusive", "denominator_nonzero_unknown")
                elif values["mu"] == values["lambda"]: raise PolicyIssue("failed", "division_by_zero")
        if form.template_id in {"passive_decay", "linear_stable"}:
            denominator_roles = set()
            def denominators(node):
                if node.op == "div":
                    def collect(term):
                        if term.op == "symbol": denominator_roles.add({s.id: s.role for s in form.symbols}[term.value])
                        for child in term.args: collect(child)
                    collect(node.args[1])
                for child in node.args: denominators(child)
            denominators(form.expression)
            for key in denominator_roles:
                if values.get(key) == 0: raise PolicyIssue("failed", "division_by_zero")
                if values.get(key) is None and d.get("positive_parameters") is not True: raise PolicyIssue("inconclusive", "denominator_nonzero_unknown")
        return values
    elif form.template_id == "little": required = LITTLE
    elif form.template_id == "mm1": required = MM1
    elif form.template_id == "passive_decay":
        thermal = r["x"].unit_id == "K" if "x" in r else r["r"].unit_id == "K_per_W"
        required = PASSIVE + (("lumped_state", "constant_environment") if thermal else ("ideal_isolated_rc",))
    else: required = LOCAL
    if (form.template_id in {"passive_decay", "linear_stable"} and form_kind(form) == "solution" and "tau" in r
            and ("r" in r or "k" in r)):
        required += ("tau_definition",)
    # No natural-language boundary interpreter: an additional declared boundary
    # is not silently discarded. Even a true flag cannot make an unknown
    # spatial/time restriction executable; that requires a registered policy.
    for extra in form.assumptions + form.boundary_conditions:
        if extra.declared_satisfied is False:
            raise PolicyIssue("failed", "precondition_contradicted:" + extra.id)
    for extra in form.assumptions + form.boundary_conditions:
        if extra.id not in required:
            raise PolicyIssue("inconclusive" if extra.declared_satisfied is None else "unsupported", "additional_condition_not_implemented:" + extra.id)
    for key in required:
        if d.get(key) is False: raise PolicyIssue("failed", "precondition_contradicted:" + key)
        if d.get(key) is not True: raise PolicyIssue("inconclusive", "precondition_unknown:" + key)
    values = {k: None if v.value is None else rational(v.value) for k, v in r.items()}
    if form.template_id == "little":
        if any(v is not None and v < 0 for v in values.values()): raise PolicyIssue("failed", "negative_queue_quantity")
    elif form.template_id == "mm1":
        arrival, service = values.get("lambda"), values.get("mu")
        if arrival is not None and arrival < 0 or service is not None and service <= 0:
            raise PolicyIssue("failed", "queue_rate_domain")
        if arrival is not None and service is not None and arrival >= service:
            raise PolicyIssue("failed", "no_mm1_steady_state")
        if any(v is not None and v < 0 for v in values.values()): raise PolicyIssue("failed", "negative_queue_quantity")
    else:
        for key in (("r", "c") if "r" in values else ("k",) if "k" in values else ("tau",)):
            if values[key] is not None and values[key] <= 0: raise PolicyIssue("failed", "nonpositive_decay_parameter")
        if "tau" in values:
            if values["tau"] is not None and values["tau"] <= 0: raise PolicyIssue("failed", "nonpositive_time_constant")
            parameters = ("r", "c") if form.template_id == "passive_decay" else ("k",)
            if values["tau"] is not None and all(values.get(key) is not None for key in parameters):
                expected = calc("mul", values["r"], values["c"]) if form.template_id == "passive_decay" else calc("div", Fraction(1), values["k"])
                if values["tau"] != expected: raise PolicyIssue("failed", "time_constant_definition_conflict")
    if scope == "initial_value_problem":
        if form.template_id in {"little", "mm1"}: raise PolicyIssue("unsupported", "algebraic_relation_has_no_ivp")
        if form_kind(form) == "timescale": raise PolicyIssue("unsupported", "timescale_relation_has_no_ivp")
        if len(form.initial_conditions) != 1: raise PolicyIssue("inconclusive", "initial_condition_missing")
        initial = form.initial_conditions[0]
        state = r["x" if form.template_id == "passive_decay" else "delta"].id
        if initial.state_symbol != state: raise PolicyIssue("failed", "initial_state_mismatch")
        if rational(initial.at_time) != 0: raise PolicyIssue("unsupported", "initial_time_not_zero")
        if initial.declared_satisfied is False: raise PolicyIssue("failed", "initial_condition_contradicted")
        if initial.declared_satisfied is not True or initial.value is None: raise PolicyIssue("inconclusive", "initial_condition_unknown")
        if form_kind(form) == "solution":
            amplitude = values["x0" if form.template_id == "passive_decay" else "delta0"]
            if amplitude is not None and amplitude != rational(initial.value):
                raise PolicyIssue("failed", "closed_form_initial_value_conflict")
    return values


def initial(form):
    return rational(form.initial_conditions[0].value)


def numeric_result(form, point, scope):
    kind = form_kind(form)
    if scope == "expression" and form.template_id in {"passive_decay", "linear_stable"} and kind == "ode_or_relation":
        raise PolicyIssue("unsupported", "formal_derivative_not_a_numeric_expression")
    values = prerequisites(form, scope, numeric=True)
    if form.template_id in {"little", "mm1"}:
        output, _ = recognize(form)
        required = ("lambda", "w") if form.template_id == "little" else ("lambda", "mu")
        if any(values.get(key) is None for key in required): raise PolicyIssue("inconclusive", "numeric_parameter_missing")
        if form.template_id == "little": prediction = calc("mul", values["lambda"], values["w"])
        else:
            lam, mu = values["lambda"], values["mu"]
            gap = calc("sub", mu, lam)
            w = calc("div", Fraction(1), gap)
            wq = calc("div", lam, calc("mul", mu, gap))
            for role, predicted in (("w", w), ("wq", wq)):
                if values.get(role) is not None and values[role] != predicted:
                    raise PolicyIssue("failed", "provided_intermediate_breaks_mm1_relation")
            prediction = {"rho": calc("div", lam, mu), "w": w, "wq": wq, "l": calc("mul", lam, w), "lq": calc("mul", lam, wq)}[output]
        observed = values.get(output)
        if observed is not None and observed != prediction: raise PolicyIssue("failed", "provided_output_breaks_exact_relation")
        return {"value": str(prediction), "given_output": None if observed is None else str(observed), "arithmetic": "exact_rational"}
    supplied_tau = kind == "solution" and values.get("tau") is not None
    required = ("tau",) if supplied_tau else ("r", "c") if "r" in values else ("k",) if "k" in values else ("tau",)
    if any(values[k] is None for k in required): raise PolicyIssue("inconclusive", "numeric_parameter_missing")
    tau = values["tau"] if supplied_tau else calc("mul", values["r"], values["c"]) if "r" in values else calc("div", Fraction(1), values["k"]) if "k" in values else values["tau"]
    if kind == "timescale":
        return {"value": str(tau), "unit_id": "s", "meaning": "time_constant_only_not_an_ivp", "arithmetic": "exact_rational"}
    at = rational(point)
    if not 0 <= at <= 20: raise FormulaLimit("normalized time limit")
    physical_time = calc("mul", tau, at)
    exponent = -float(at)
    if not -100 <= exponent <= 0: raise FormulaLimit("exponent limit")
    value = math.exp(exponent)
    actual = None
    amplitude = None
    if scope == "initial_value_problem" or kind == "solution":
        amplitude = initial(form) if scope == "initial_value_problem" else values["x0" if form.template_id == "passive_decay" else "delta0"]
        if amplitude is None: raise PolicyIssue("inconclusive", "closed_form_amplitude_missing")
        actual = float(amplitude) * value
        if not math.isfinite(actual) or abs(actual) > 10**12: raise FormulaLimit("numeric output limit")
        value = 0.0 if amplitude == 0 else value
    return {"value": format(value, ".17g"), "physical_time": str(physical_time), "tau": str(tau),
            "actual_state": None if actual is None else format(actual, ".17g"),
            "arithmetic": "bounded_exp", "meaning": ("zero_solution_no_state_normalization" if amplitude == 0 else "normalized_initial_state") if amplitude is not None else "unit_response_kernel_only"}


def comparison(left, right, scope):
    lo, lt = recognize(left); ro, rt = recognize(right)
    dimensions(left); dimensions(right)
    prerequisites(left, scope); prerequisites(right, scope)
    decay = {"passive_decay", "linear_stable"}
    if scope == "expression":
        lu = {v.role: (v.unit_id, v.quantity, v.value) for v in left.symbols}
        ru = {v.role: (v.unit_id, v.quantity, v.value) for v in right.symbols}
        if lt != rt or lu != ru:
            raise PolicyIssue("inconclusive", "literal_expressions_require_same_units_parameters_and_roles")
        relation = "algebraic_identity"
    elif left.template_id in decay and right.template_id in decay:
        lk, rk = form_kind(left), form_kind(right)
        if "timescale" in {lk, rk}:
            if lk != rk: raise PolicyIssue("unsupported", "timescale_and_dynamics_are_distinct_objects")
            relation = "partial_structure"  # two time-constant definitions, not full dynamics
        elif scope == "initial_value_problem" and (initial(left) == 0) != (initial(right) == 0):
            raise PolicyIssue("failed", "zero_nonzero_initial_problems_not_equivalent")
        elif scope == "equation_form" and lk != rk:
            relation = "partial_structure"  # general ODE vs solution family; no IVP claim
        else:
            relation = "local_approximation" if "linear_stable" in {left.template_id, right.template_id} else "conditional_model_equivalence"
    elif left.template_id == right.template_id and lo == ro and left.measure_scope == right.measure_scope:
        if basis(roles(left)["lambda"].unit_id) != basis(roles(right)["lambda"].unit_id):
            raise PolicyIssue("inconclusive", "no_implicit_workday_conversion")
        relation = "conditional_model_equivalence"
    else:
        raise PolicyIssue("unsupported", "unregistered_template_pair_or_measure_scope")
    before = digest({"left": left.expression.data(), "right": right.expression.data(), "scope": scope})
    trace = []
    for stage in ("rename_bijection", "constant_fold", "associate", "commute"):
        output = digest({"left": repr(normalized(left.expression, {s.id: s for s in left.symbols}, stage)),
                         "right": repr(normalized(right.expression, {s.id: s for s in right.symbols}, stage)), "scope": scope})
        trace.append({"kind": stage, "input_digest": before, "output_digest": output, "precondition_ids": []})
        before = output
    if scope != "expression" and left.template_id in decay and right.template_id in decay and "timescale" not in {form_kind(left), form_kind(right)}:
        if any(form.template_id == "passive_decay" and form_kind(form) == "ode_or_relation" for form in (left, right)):
            trace.append({"kind": "divide_nonzero", "input_digest": trace[-1]["output_digest"],
                          "output_digest": digest({"left_rate": "1/(r*c)" if "r" in roles(left) else "k" if "k" in roles(left) else "1/tau",
                                                  "right_rate": "1/(r*c)" if "r" in roles(right) else "k" if "k" in roles(right) else "1/tau"}),
                          "precondition_ids": ["positive_parameters"]})
        trace.append({"kind": "positive_time_scale", "input_digest": trace[-1]["output_digest"],
                      "output_digest": digest({"equation": "d(state)/ds=-state", "state_unit": "unchanged", "scope": scope}), "precondition_ids": ["positive_parameters", "constant_parameters", "no_external_input"]})
        if scope == "initial_value_problem":
            trace.append({"kind": "substitute_constant" if initial(left) == 0 else "state_normalize",
                          "input_digest": trace[-1]["output_digest"], "output_digest": digest({"initial": 0 if initial(left) == 0 else 1}),
                          "precondition_ids": ["left_initial_value", "right_initial_value"]})
    return relation, tuple(trace)
