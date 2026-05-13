#!/usr/bin/env python3
"""D1 — StructTuple extraction via DeepSeek direct API + LLM guardrail stack.

For each company row in `companies.jsonl`, send a prompt to DeepSeek (v4-pro
by default), validate the returned JSON through the V4 guardrail stack
(`state_machine_fix` + local `StructTuple.validate`), and write parsed
records to an output JSONL.

The StructTuple schema is NOT in `v4/lib/llm_schemas.py` (those are the
B1/B3 critic schemas). We define a local dataclass `StructTuple` here with
the same `.validate(d) -> (ok, err, instance)` shape so it plugs directly
into `validate_json` from the guardrail module.

CLI:
    python3 extract_structtuple.py <input.jsonl> <output.jsonl> [--limit N] [--model M]

Model defaults to `deepseek-v4-pro` (better quality + reasoning) per D1 brief.

Direct DeepSeek API is used to bypass OpenRouter CN region-block. Key is
embedded inline — this is a research / internal-only script; rotate via
session #N+ if it ever gets pushed.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Wire v4/lib into sys.path so we can import the shared guardrail utilities.
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "v4" / "lib"))

from llm_guardrail import state_machine_fix, validate_json  # noqa: E402

# ---------------------------------------------------------------------------
# DeepSeek API config
# ---------------------------------------------------------------------------

DEEPSEEK_KEY = "sk-ad62cc6d8ada4bd0a92847b6b1d0ae1f"
DEEPSEEK_BASE = "https://api.deepseek.com/v1/chat/completions"

DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 2500

DYNAMICS_FAMILIES = (
    "preferential_attachment",
    "hysteresis_preisach",
    "scheffer_fold",
    "motter_lai_cascade",
    "soc_threshold_cascade",
    "reflexive_fixed_point",
    "extreme_value_tail",
    "linear_quasi_equilibrium",
    "mixed_or_unclear",
)

CRITICAL_STATES = (
    "far_from_critical",
    "approaching_critical",
    "at_critical",
    "post_critical_transition",
    "unknown",
)

SYSTEM_PROMPT = (
    "You are a structural-dynamics analyst. Given a company description, "
    "classify it into one of nine universality classes describing its "
    "growth / risk dynamics (preferential_attachment, hysteresis_preisach, "
    "scheffer_fold, motter_lai_cascade, soc_threshold_cascade, "
    "reflexive_fixed_point, extreme_value_tail, linear_quasi_equilibrium, "
    "mixed_or_unclear), report a critical-point state, and ground your "
    "judgment in 2-5 verifiable public facts. Output JSON only, no preamble."
)


# ---------------------------------------------------------------------------
# Local schema with validate() classmethod (compatible with llm_guardrail)
# ---------------------------------------------------------------------------


@dataclass
class EvidenceAnchor:
    fact: str
    source: str
    metric_value: str | None = None


@dataclass
class EarlyWarningIndicators:
    ar1_trend: str | None = None
    variance_trend: str | None = None
    tail_exponent_drift: str | None = None


@dataclass
class StructTuple:
    """StructTuple — structural fingerprint of a company at a point in time.

    Validate via `StructTuple.validate(d) -> (ok, err, instance)`.
    Compatible with the V4 guardrail stack.
    """

    ticker: str
    as_of_date: str
    dynamics_family: str
    critical_point_state: str
    structural_summary: str
    confidence: float
    evidence_anchors: list[EvidenceAnchor]
    company_name: str | None = None
    early_warning_indicators: EarlyWarningIndicators | None = None
    v4_class_alignment: dict[str, float] = field(default_factory=dict)

    REQUIRED: tuple[str, ...] = field(
        default=(
            "ticker",
            "as_of_date",
            "dynamics_family",
            "critical_point_state",
            "structural_summary",
            "confidence",
            "evidence_anchors",
        ),
        init=False,
        repr=False,
    )

    @classmethod
    def validate(cls, d: Any) -> tuple[bool, str | None, "StructTuple | None"]:
        if not isinstance(d, dict):
            return False, f"expected object, got {type(d).__name__}", None
        missing = [k for k in cls.REQUIRED if k not in d]
        if missing:
            return False, f"missing required field(s): {', '.join(missing)}", None

        ticker = d["ticker"]
        if not isinstance(ticker, str) or not ticker.strip():
            return False, "ticker must be non-empty string", None

        as_of_date = d["as_of_date"]
        if not isinstance(as_of_date, str) or len(as_of_date) != 10:
            return False, f"as_of_date must be YYYY-MM-DD, got {as_of_date!r}", None

        dynamics_family = d["dynamics_family"]
        if dynamics_family not in DYNAMICS_FAMILIES:
            return (
                False,
                f"dynamics_family {dynamics_family!r} not in enum {DYNAMICS_FAMILIES}",
                None,
            )

        critical_point_state = d["critical_point_state"]
        if critical_point_state not in CRITICAL_STATES:
            return (
                False,
                f"critical_point_state {critical_point_state!r} not in enum",
                None,
            )

        summary = d["structural_summary"]
        if not isinstance(summary, str):
            return False, "structural_summary must be string", None
        if len(summary) > 600:
            return False, f"structural_summary too long: {len(summary)} > 600", None

        conf = d["confidence"]
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            return False, f"confidence not coercible to float: {conf!r}", None
        if not (0.0 <= conf_f <= 1.0):
            return False, f"confidence out of [0,1]: {conf_f}", None

        anchors_raw = d["evidence_anchors"]
        if not isinstance(anchors_raw, list):
            return False, "evidence_anchors must be array", None
        if not (2 <= len(anchors_raw) <= 5):
            return (
                False,
                f"evidence_anchors length {len(anchors_raw)} not in [2,5]",
                None,
            )
        anchors: list[EvidenceAnchor] = []
        for i, a in enumerate(anchors_raw):
            if not isinstance(a, dict):
                return False, f"evidence_anchors[{i}] not an object", None
            if "fact" not in a or "source" not in a:
                return False, f"evidence_anchors[{i}] missing fact/source", None
            if not isinstance(a["fact"], str) or not isinstance(a["source"], str):
                return False, f"evidence_anchors[{i}] fact/source must be string", None
            anchors.append(
                EvidenceAnchor(
                    fact=a["fact"],
                    source=a["source"],
                    metric_value=a.get("metric_value"),
                )
            )

        ewi_raw = d.get("early_warning_indicators")
        ewi: EarlyWarningIndicators | None = None
        if isinstance(ewi_raw, dict):
            ewi = EarlyWarningIndicators(
                ar1_trend=ewi_raw.get("ar1_trend"),
                variance_trend=ewi_raw.get("variance_trend"),
                tail_exponent_drift=ewi_raw.get("tail_exponent_drift"),
            )

        alignment_raw = d.get("v4_class_alignment") or {}
        alignment: dict[str, float] = {}
        if isinstance(alignment_raw, dict):
            for k, v in alignment_raw.items():
                try:
                    alignment[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue

        inst = cls(
            ticker=ticker.strip(),
            as_of_date=as_of_date,
            dynamics_family=dynamics_family,
            critical_point_state=critical_point_state,
            structural_summary=summary,
            confidence=conf_f,
            evidence_anchors=anchors,
            company_name=d.get("company_name"),
            early_warning_indicators=ewi,
            v4_class_alignment=alignment,
        )
        return True, None, inst

    def to_dict(self) -> dict:
        out: dict = {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "as_of_date": self.as_of_date,
            "dynamics_family": self.dynamics_family,
            "critical_point_state": self.critical_point_state,
            "structural_summary": self.structural_summary,
            "confidence": self.confidence,
            "evidence_anchors": [
                {"fact": a.fact, "source": a.source, "metric_value": a.metric_value}
                for a in self.evidence_anchors
            ],
        }
        if self.early_warning_indicators is not None:
            out["early_warning_indicators"] = {
                "ar1_trend": self.early_warning_indicators.ar1_trend,
                "variance_trend": self.early_warning_indicators.variance_trend,
                "tail_exponent_drift": self.early_warning_indicators.tail_exponent_drift,
            }
        if self.v4_class_alignment:
            out["v4_class_alignment"] = self.v4_class_alignment
        return out


# ---------------------------------------------------------------------------
# DeepSeek call (style copied from v4/scripts/b3_ensemble.py)
# ---------------------------------------------------------------------------


def call_deepseek(
    model: str,
    system: str,
    user: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> tuple[str | None, str | None, dict | None]:
    """POST to DeepSeek chat-completions.

    Returns (content, error, usage). content is None on error. usage is the
    api `usage` field (prompt_tokens / completion_tokens / total_tokens),
    available even on success.
    """
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        DEEPSEEK_BASE,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {DEEPSEEK_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content", "") or ""
        usage = data.get("usage")
        content = content.strip()
        if not content:
            return None, f"empty content (finish_reason={choice.get('finish_reason')})", usage
        return content, None, usage
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:400]
        return None, f"HTTP {e.code}: {body}", None
    except urllib.error.URLError as e:
        return None, f"URLError: {e.reason}", None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", None


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def make_prompt(company: dict, as_of: str = "2026-05-13") -> str:
    cap = company.get("market_cap_bn_usd")
    cap_str = f"~${cap}B market cap" if cap else "market cap unknown"
    return f"""Analyze company {company['ticker']} ({company.get('company_name', company['ticker'])}, sector {company.get('sector', 'unknown')}, {cap_str}).

Output a StructTuple JSON describing its structural dynamics. Use exactly one of these `dynamics_family` enum values:

- preferential_attachment: network effects, winner-takes-most, scale-free growth (FAANG, exchanges, payment rails)
- hysteresis_preisach: first-order phase transitions, sticky regimes that resist reversal (regulated industries, regimes that shifted and won't snap back)
- scheffer_fold: fold bifurcation, bistable regimes, can collapse suddenly to lower attractor (over-leveraged firms, fashion brands losing identity)
- motter_lai_cascade: network-cascade vulnerability where one failure propagates (large banks, supply chains, interconnected insurers)
- soc_threshold_cascade: self-organized criticality with power-law event sizes (commodities, insurance, energy markets)
- reflexive_fixed_point: Soros reflexivity, narrative-driven feedback loops between price and fundamentals (meme stocks, crypto-linked, story stocks)
- extreme_value_tail: heavy-tail outliers without shared mechanism (catastrophe reinsurance, lottery-like payoffs)
- linear_quasi_equilibrium: mature mean-reverting business, no critical dynamics (utilities, staples, mature consumer brands)
- mixed_or_unclear: ambiguous; explain in summary

For `critical_point_state` use one of: far_from_critical | approaching_critical | at_critical | post_critical_transition | unknown.

Required JSON output schema (output ONLY this object, no preamble):

{{
  "ticker": "{company['ticker']}",
  "company_name": "{company.get('company_name', company['ticker'])}",
  "as_of_date": "{as_of}",
  "dynamics_family": "<one of the 9 enums above>",
  "critical_point_state": "<one of the 5 enums above>",
  "structural_summary": "<30-second TL;DR human-readable; max 600 chars>",
  "confidence": <float 0.0-1.0>,
  "evidence_anchors": [
    {{"fact": "<concrete public fact>", "source": "<10-K / news / market data / etc>", "metric_value": "<optional numeric>"}},
    {{"fact": "<another fact>", "source": "<source>", "metric_value": "<optional>"}}
  ],
  "early_warning_indicators": {{
    "ar1_trend": "<rising|stable|falling|n/a>",
    "variance_trend": "<rising|stable|falling|n/a>",
    "tail_exponent_drift": "<heavy_tail_steepening|stable|heavy_tail_thinning|n/a>"
  }}
}}

Constraints:
- evidence_anchors MUST have between 2 and 5 entries.
- structural_summary MUST be <=600 characters.
- confidence MUST be between 0.0 and 1.0.
- Output the JSON object only; no markdown fences, no explanation outside JSON.
"""


# ---------------------------------------------------------------------------
# Extraction (single + batch)
# ---------------------------------------------------------------------------


def extract_one(
    company: dict,
    model: str = DEFAULT_MODEL,
    as_of: str = "2026-05-13",
    max_retries: int = 2,
) -> dict:
    """Run guardrailed extraction for one company.

    Returns a dict with:
        ok: bool
        struct_tuple: dict | None (parsed StructTuple as dict if ok)
        errors: list[str]
        usage: dict | None (token counts from the most recent attempt)
        elapsed_s: float
        attempts: int
    """
    errors: list[str] = []
    last_err: str | None = None
    last_usage: dict | None = None
    t0 = time.time()
    attempts_done = 0

    for attempt in range(max_retries):
        attempts_done = attempt + 1
        user_prompt = make_prompt(company, as_of=as_of)
        if last_err:
            user_prompt += (
                f"\n\nPrevious attempt failed validation: {last_err}. "
                "Re-output the JSON only, fixing the issue."
            )

        raw, err, usage = call_deepseek(
            model=model,
            system=SYSTEM_PROMPT,
            user=user_prompt,
        )
        if usage is not None:
            last_usage = usage
        if raw is None:
            err_msg = f"attempt {attempts_done}: llm call failed: {err}"
            errors.append(err_msg)
            last_err = err
            continue

        cleaned = state_machine_fix(raw)
        ok, verr, parsed = validate_json(cleaned, StructTuple)
        if ok and parsed is not None:
            return {
                "ok": True,
                "struct_tuple": parsed.to_dict(),
                "errors": errors,
                "usage": last_usage,
                "elapsed_s": round(time.time() - t0, 2),
                "attempts": attempts_done,
            }
        err_msg = f"attempt {attempts_done}: {verr}"
        errors.append(err_msg)
        last_err = verr

    return {
        "ok": False,
        "struct_tuple": None,
        "errors": errors,
        "usage": last_usage,
        "elapsed_s": round(time.time() - t0, 2),
        "attempts": attempts_done,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="D1 StructTuple extractor")
    parser.add_argument("input", help="path to companies.jsonl")
    parser.add_argument("output", help="path to output jsonl")
    parser.add_argument("--limit", type=int, default=None, help="only process first N rows")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"DeepSeek model (default {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--as-of",
        default="2026-05-13",
        help="as_of_date for StructTuple (YYYY-MM-DD)",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        print(f"[D1] input not found: {in_path}", file=sys.stderr)
        return 2

    companies = []
    with in_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                companies.append(json.loads(line))
    if args.limit:
        companies = companies[: args.limit]

    print(f"[D1] Loaded {len(companies)} companies. Model={args.model}.", file=sys.stderr)

    n_ok = 0
    n_fail = 0
    total_in_tokens = 0
    total_out_tokens = 0
    total_elapsed = 0.0

    with out_path.open("w") as out:
        for i, company in enumerate(companies, 1):
            print(
                f"[D1] [{i}/{len(companies)}] {company['ticker']}...",
                file=sys.stderr,
            )
            res = extract_one(company, model=args.model, as_of=args.as_of)
            if res["usage"]:
                total_in_tokens += res["usage"].get("prompt_tokens", 0) or 0
                total_out_tokens += res["usage"].get("completion_tokens", 0) or 0
            total_elapsed += res["elapsed_s"]

            record = {
                "ticker": company["ticker"],
                "expected_dynamics_family_a_priori": company.get(
                    "expected_dynamics_family_a_priori"
                ),
                "ok": res["ok"],
                "attempts": res["attempts"],
                "elapsed_s": res["elapsed_s"],
                "usage": res["usage"],
                "struct_tuple": res["struct_tuple"],
                "errors": res["errors"],
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()

            if res["ok"]:
                n_ok += 1
                st = res["struct_tuple"]
                exp = company.get("expected_dynamics_family_a_priori")
                actual = st["dynamics_family"]
                match = "MATCH" if exp == actual else ("(no prior)" if exp is None else "DIFFER")
                print(
                    f"    OK  family={actual:30s} state={st['critical_point_state']:25s} "
                    f"conf={st['confidence']:.2f} expected={exp} [{match}]",
                    file=sys.stderr,
                )
            else:
                n_fail += 1
                print(f"    FAIL  errors={res['errors']}", file=sys.stderr)

    print(
        f"\n[D1] Done. ok={n_ok} fail={n_fail} total_elapsed={total_elapsed:.1f}s "
        f"in_tokens={total_in_tokens} out_tokens={total_out_tokens}",
        file=sys.stderr,
    )
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
