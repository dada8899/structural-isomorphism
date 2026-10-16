"""Fixed U2 arithmetic policy. Business amounts never use billing Money."""
from decimal import Context, Decimal, ROUND_HALF_EVEN, Underflow, localcontext
import hashlib
import json
import re
import time

POLICY = "financial-scenario-v1-candidate"
YEARS = (2026, 2027, 2028, 2029, 2030, 2031)
FUTURE_YEARS = YEARS[1:]
MAX_JSON = 128 * 1024
MAX_OPERATIONS = 5000
DEADLINE_SECONDS = 2.0
MAX_ABS = Decimal("1e18")
CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-200, Emax=200)
CONTEXT.traps[Underflow] = True
MILLION_FACTORS = {"unit": Decimal("0.000001"), "thousand": Decimal("0.001"), "million": Decimal(1), "billion": Decimal(1000)}
CURRENCIES = {"CNY", "USD"}
COST_TAGS = {"base_operating_cost", "base_operating_expense", "shared_cost", "depreciation", "sbc"}
COST_KINDS = {"operating_cost": "base_operating_cost", "operating_expense": "base_operating_expense", "shared_cost": "shared_cost", "depreciation": "depreciation", "sbc": "sbc", "operating_adjustment": None}


class FinancialError(ValueError):
    pass


class FinancialResourceLimit(FinancialError):
    pass


def number(value):
    # Limits precede Decimal construction; no float/bool, huge exponent or
    # arbitrary precision coefficient reaches an arithmetic implementation.
    if type(value) is not str or len(value) > 64:
        raise FinancialError("strict bounded decimal text required")
    match = re.fullmatch(r"-?(0|[1-9][0-9]*)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]{1,3}))?", value)
    if not match:
        raise FinancialError("invalid finite decimal text")
    if abs(int(match[3] or "0")) > 18 or len((match[1] + (match[2] or "")).lstrip("0").rstrip("0")) > 24:
        raise FinancialResourceLimit("input precision or exponent limit")
    parsed = Decimal(value)
    if parsed and not -18 <= parsed.adjusted() <= 18:
        raise FinancialResourceLimit("input magnitude limit")
    if parsed.copy_abs() > MAX_ABS:
        raise FinancialResourceLimit("input absolute limit")
    return parsed


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def json_cap(value):
    encoded = canonical(value)
    if len(encoded.encode()) > MAX_JSON:
        raise FinancialResourceLimit("JSON byte limit")
    return encoded


class Meter:
    """Cooperative bounded steps, not an OS sandbox or a hard CPU interrupt."""
    def __init__(self):
        self.deadline = time.monotonic() + DEADLINE_SECONDS
        self.operations = 0

    def tick(self):
        self.operations += 1
        if self.operations > MAX_OPERATIONS or time.monotonic() > self.deadline:
            raise FinancialResourceLimit("operation or step deadline limit")

    def calculate(self, op, a, b):
        self.tick()
        if type(a) is not Decimal or type(b) is not Decimal:
            raise FinancialError("internal Decimal operands required")
        if op == "add": result = a + b
        elif op == "sub": result = a - b
        elif op == "mul": result = a * b
        elif op == "div":
            if b == 0: raise FinancialError("zero denominator")
            result = a / b
        else: raise FinancialError("unregistered arithmetic operation")
        if not result.is_finite() or abs(result) > MAX_ABS:
            raise FinancialResourceLimit("computed magnitude limit")
        self.tick()
        return result

    def display(self, value):
        self.tick()
        if value is None: return None
        with localcontext():
            # Display rounding must not be reported as calculation rounding.
            result = value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        return format(Decimal(0) if result == 0 else result, ".6f")


def arithmetic_context():
    return localcontext(CONTEXT.copy())
