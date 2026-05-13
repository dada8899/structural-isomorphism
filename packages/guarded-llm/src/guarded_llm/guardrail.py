"""LLM output guardrail: 3-layer validation + retry + state-machine fixer.

Defense stack for noisy LLM JSON output:

    raw LLM text
        |
        v
    Layer 0: extract — strip markdown fences, locate JSON envelope
        |
        v
    Layer 1: state-machine fix — patch common drift bugs
              (trailing commas, single quotes, unescaped interior
               quotes, comments, NaN/Infinity, BOM)
        |
        v
    Layer 2: json.loads — structural validity
        |
        v
    Layer 3: schema validate — dataclass / JSON-Schema check
        |
        v
    retry policy (up to N attempts):
        on fail -> regenerate prompt with hint: "Previous output failed
        validation: <error>. Output JSON only."
        |
        v
    graceful failure -> return GuardrailResult(parsed=None, errors=[...])
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .exceptions import BudgetExceededError
from .schemas import LLMSchema, validate_response


# ---------------------------------------------------------------------------
# Layer 0 + 1: extraction and state-machine fixer
# ---------------------------------------------------------------------------

# Strip ```json ... ``` and ``` ... ``` fences (greedy: take outermost block).
_FENCE_RE = re.compile(
    r"```(?:json|javascript|js)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE
)

# Locate the outermost { ... } or [ ... ] envelope (used after fence strip).
_JSON_OBJ_RE = re.compile(r"(\{.*\}|\[.*\])", re.DOTALL)


def _strip_fences_and_locate(raw: str) -> str:
    """Pull JSON body out of markdown fences / surrounding chatter."""
    s = raw.strip()
    if s.startswith("﻿"):
        s = s.lstrip("﻿")

    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    if not (s.startswith("{") or s.startswith("[")):
        m = _JSON_OBJ_RE.search(s)
        if m:
            s = m.group(1).strip()
    return s


def _strip_comments(s: str) -> str:
    """Remove // line and /* block */ comments (only outside strings)."""
    out = []
    i, n = 0, len(s)
    in_str = False
    str_quote = ""
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue

        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "/":
                j = s.find("\n", i)
                i = n if j == -1 else j
                continue
            if nxt == "*":
                j = s.find("*/", i + 2)
                i = n if j == -1 else j + 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _replace_nan_infinity(s: str) -> str:
    """Replace bare NaN / Infinity / -Infinity tokens with null at value positions."""
    out = []
    i, n = 0, len(s)
    in_str = False
    str_quote = ""
    tokens = (
        ("-Infinity", "null"),
        ("Infinity", "null"),
        ("NaN", "null"),
    )
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue
        matched = False
        for tok, repl in tokens:
            if s.startswith(tok, i):
                prev = "".join(out).rstrip()
                prev_ok = (not prev) or prev[-1] in ":,[ \n\t\r"
                nxt_idx = i + len(tok)
                nxt_ok = nxt_idx >= n or s[nxt_idx] in ",}] \n\t\r"
                if prev_ok and nxt_ok:
                    out.append(repl)
                    i += len(tok)
                    matched = True
                    break
        if matched:
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _remove_trailing_commas(s: str) -> str:
    """Remove trailing commas before } or ] (outside strings)."""
    out = []
    i, n = 0, len(s)
    in_str = False
    str_quote = ""
    while i < n:
        ch = s[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == str_quote:
                in_str = False
                str_quote = ""
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and s[j] in " \n\t\r":
                j += 1
            if j < n and s[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _single_to_double_quotes(s: str) -> str:
    """Convert single-quoted strings to double-quoted (only when not already
    inside a double-quoted string)."""
    out = []
    i, n = 0, len(s)
    in_double = False
    in_single = False
    while i < n:
        ch = s[i]
        if in_double:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(s[i + 1])
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if in_single:
            if ch == "\\" and i + 1 < n:
                if s[i + 1] == "'":
                    out.append("'")
                else:
                    out.append(ch)
                    out.append(s[i + 1])
                i += 2
                continue
            if ch == "'":
                out.append('"')
                in_single = False
                i += 1
                continue
            if ch == '"':
                out.append('\\"')
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            out.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    if in_single:
        out.append('"')
    return "".join(out)


def _fix_unescaped_interior_quotes(s: str) -> str:
    """Heuristic: fix lines like  "key": "value with "interior" quotes" """
    out = []
    i, n = 0, len(s)
    in_str = False
    while i < n:
        ch = s[i]
        if not in_str:
            out.append(ch)
            if ch == '"':
                in_str = True
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(s[i + 1])
            i += 2
            continue
        if ch == '"':
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ",}]:":
                out.append(ch)
                in_str = False
                i += 1
                continue
            out.append("\\")
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def state_machine_fix(raw: str) -> str:
    """Best-effort repair of common LLM JSON drift bugs.

    Applies, in order:
        1. fence strip + JSON envelope locate
        2. comment strip
        3. NaN / Infinity -> null
        4. single-quote -> double-quote
        5. unescaped interior quote escape
        6. trailing comma removal

    Never raises; hands back its best guess.
    """
    if not isinstance(raw, str):
        return str(raw)
    s = _strip_fences_and_locate(raw)
    s = _strip_comments(s)
    s = _replace_nan_infinity(s)
    s = _single_to_double_quotes(s)
    s = _fix_unescaped_interior_quotes(s)
    s = _remove_trailing_commas(s)
    return s


# ---------------------------------------------------------------------------
# Layer 2 + 3: parse + schema validate
# ---------------------------------------------------------------------------


def validate_json(raw_or_dict: Any, schema_cls: Any) -> tuple[bool, str | None, Any]:
    """Parse + schema-validate.

    Accepts a raw string (json.loads first) or an already-parsed dict/list.
    Schema can be either a dataclass schema class or an LLMSchema instance.
    Returns (success, error_or_none, instance_or_none).
    """
    if isinstance(raw_or_dict, (dict, list)):
        parsed = raw_or_dict
    else:
        try:
            parsed = json.loads(raw_or_dict)
        except json.JSONDecodeError as e:
            return False, f"json parse error: {e.msg} (line {e.lineno} col {e.colno})", None
        except Exception as e:
            return False, f"json parse error: {e}", None

    return validate_response(parsed, schema_cls)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class GuardrailResult:
    """Outcome of a guarded LLM call.

    Attributes:
        parsed: validated instance (dict for LLMSchema, dataclass for legacy schemas)
                or None if all retries failed
        errors: per-attempt error strings (empty if first try succeeded)
        attempts: number of LLM calls actually made
        cost_usd: estimated cumulative cost in USD (provider-reported, may be 0)
        raw_outputs: raw text returned by each attempt (for debugging)
    """

    parsed: Any
    errors: list[str] = field(default_factory=list)
    attempts: int = 0
    cost_usd: float = 0.0
    raw_outputs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.parsed is not None


# ---------------------------------------------------------------------------
# Retry orchestrator
# ---------------------------------------------------------------------------


def _legacy_call(
    prompt_fn: Callable[[str | None], str],
    llm_caller: Callable[[str], str],
    schema_cls: Any,
    max_retries: int,
) -> tuple[Any | None, list[str]]:
    """Legacy (prompt_fn, llm_caller) API path.

    Preserved so existing V4 callers in structural-isomorphism keep working.
    Returns the old (parsed, errors) tuple.
    """
    if max_retries < 1:
        return None, ["max_retries must be >= 1"]

    errors: list[str] = []
    last_err: str | None = None
    for attempt in range(max_retries):
        try:
            prompt = prompt_fn(last_err)
        except Exception as exc:
            errors.append(f"attempt {attempt + 1}: prompt_fn raised: {exc}")
            return None, errors

        try:
            raw = llm_caller(prompt)
        except Exception as exc:
            err = f"attempt {attempt + 1}: llm_caller raised: {exc}"
            errors.append(err)
            last_err = err
            continue

        cleaned = state_machine_fix(raw)
        ok, err, parsed = validate_json(cleaned, schema_cls)
        if ok:
            return parsed, errors
        err_msg = f"attempt {attempt + 1}: {err}"
        errors.append(err_msg)
        last_err = err

    return None, errors


def _provider_call(
    provider: str,
    model: str,
    messages: list[dict],
    schema: Any,
    max_retries: int,
    max_tokens: int,
    budget_cap_usd: float | None,
    retry_backoff_s: float,
    **kwargs: Any,
) -> GuardrailResult:
    """New provider-aware API path.

    Routes to a registered provider in `guarded_llm.providers`, runs the full
    guardrail loop, tracks cost, and returns a GuardrailResult.
    """
    from .providers import get_provider  # local import to avoid circular

    prov = get_provider(provider)
    result = GuardrailResult(parsed=None)
    last_err: str | None = None

    for attempt in range(max_retries):
        # Inject retry hint into last user message if we've seen an error
        attempt_messages = list(messages)
        if last_err is not None and attempt_messages:
            hint = (
                f"\n\nPrevious output failed validation: {last_err}\n"
                "Output valid JSON only — no prose, no markdown fences."
            )
            last = dict(attempt_messages[-1])
            if last.get("role") == "user":
                last["content"] = last.get("content", "") + hint
                attempt_messages[-1] = last
            else:
                attempt_messages.append({"role": "user", "content": hint.strip()})

        result.attempts += 1
        try:
            call_out = prov.call(
                messages=attempt_messages,
                model=model,
                max_tokens=max_tokens,
                schema=schema,
                **kwargs,
            )
        except Exception as exc:
            err = f"attempt {attempt + 1}: provider {provider!r} raised: {exc}"
            result.errors.append(err)
            last_err = err
            if attempt + 1 < max_retries and retry_backoff_s > 0:
                time.sleep(retry_backoff_s)
            continue

        raw = call_out.get("text", "") if isinstance(call_out, dict) else str(call_out)
        cost = float(call_out.get("cost_usd", 0.0)) if isinstance(call_out, dict) else 0.0
        result.raw_outputs.append(raw)
        result.cost_usd += cost

        if budget_cap_usd is not None and result.cost_usd > budget_cap_usd:
            raise BudgetExceededError(
                f"cumulative cost ${result.cost_usd:.4f} > cap ${budget_cap_usd:.4f}",
                spent_usd=result.cost_usd,
                cap_usd=budget_cap_usd,
            )

        cleaned = state_machine_fix(raw)
        ok, err, parsed = validate_json(cleaned, schema)
        if ok:
            result.parsed = parsed
            return result
        err_msg = f"attempt {attempt + 1}: {err}"
        result.errors.append(err_msg)
        last_err = err
        if attempt + 1 < max_retries and retry_backoff_s > 0:
            time.sleep(retry_backoff_s)

    return result


def guardrailed_llm_call(
    prompt_fn: Callable[[str | None], str] | None = None,
    llm_caller: Callable[[str], str] | None = None,
    schema_cls: Any = None,
    max_retries: int = 3,
    *,
    provider: str | None = None,
    model: str | None = None,
    messages: list[dict] | None = None,
    schema: Any = None,
    max_tokens: int = 2048,
    budget_cap_usd: float | None = None,
    retry_backoff_s: float = 0.0,
    **kwargs: Any,
) -> Any:
    """Run an LLM call wrapped in the full guardrail stack.

    Two call styles supported:

    **Legacy (positional, kept for backwards compat with v4/lib):**

        parsed, errors = guardrailed_llm_call(prompt_fn, llm_caller, MySchema, max_retries=3)

    **Provider (keyword, new public API):**

        result = guardrailed_llm_call(
            provider="deepseek",
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "..."}],
            schema=my_schema,
            max_retries=3,
            budget_cap_usd=0.05,
        )
        if result.ok:
            print(result.parsed)

    The provider style returns a `GuardrailResult` with cost / attempts /
    raw_outputs metadata. The legacy style returns the (parsed, errors) tuple
    unchanged from v4/lib/llm_guardrail.py.
    """
    # Provider-style: keyword args route here
    if provider is not None or messages is not None:
        if provider is None or model is None or messages is None or schema is None:
            raise ValueError(
                "provider-style call requires provider=, model=, messages=, schema="
            )
        return _provider_call(
            provider=provider,
            model=model,
            messages=messages,
            schema=schema,
            max_retries=max_retries,
            max_tokens=max_tokens,
            budget_cap_usd=budget_cap_usd,
            retry_backoff_s=retry_backoff_s,
            **kwargs,
        )

    # Legacy style
    if prompt_fn is None or llm_caller is None or schema_cls is None:
        raise ValueError(
            "legacy call requires prompt_fn, llm_caller, schema_cls positional args"
        )
    return _legacy_call(prompt_fn, llm_caller, schema_cls, max_retries)


__all__ = [
    "state_machine_fix",
    "validate_json",
    "guardrailed_llm_call",
    "GuardrailResult",
]
