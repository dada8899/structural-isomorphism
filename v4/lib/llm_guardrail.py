"""LLM output guardrail: 3-layer validation + retry + state-machine fixer.

Defense stack for noisy LLM JSON output (V4 Layer 3+):

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
    Layer 3: schema validate — Pydantic-like field/type/enum check
              (defined in llm_schemas.py)
        |
        v
    retry policy (up to N attempts):
        on fail -> regenerate prompt with hint: "Previous output failed
        validation: <error>. Output JSON only."
        |
        v
    graceful failure -> return (None, errors)

The fixer is best-effort; we never *invent* fields, just clean up syntax
that LLMs commonly emit incorrectly.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable


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
    # Strip UTF-8 BOM if present
    if s.startswith("﻿"):
        s = s.lstrip("﻿")

    m = _FENCE_RE.search(s)
    if m:
        s = m.group(1).strip()

    # If body still has leading chatter, grab outermost JSON envelope.
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

        # Not in string
        if ch in ('"', "'"):
            in_str = True
            str_quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = s[i + 1]
            if nxt == "/":
                # line comment
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
    """Replace bare NaN / Infinity / -Infinity tokens with null.

    Only at JSON value positions (preceded by ':' or ',' or '[' optionally
    with whitespace), not inside strings.
    """
    # Track string state and replace literal tokens at value positions.
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
        # Try token match
        matched = False
        for tok, repl in tokens:
            if s.startswith(tok, i):
                # Boundary check: previous non-space char must be one of : , [
                # and next char must be terminator , } ] or whitespace.
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
            # Look ahead past whitespace
            j = i + 1
            while j < n and s[j] in " \n\t\r":
                j += 1
            if j < n and s[j] in "}]":
                # skip the comma
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _single_to_double_quotes(s: str) -> str:
    """Convert single-quoted strings to double-quoted (only when not already
    inside a double-quoted string).

    Handles:
        {'a': 'b'}   -> {"a": "b"}

    Limitations: doesn't handle escaped single quotes within single-quoted
    strings perfectly, but covers the LLM-drift case (LLMs almost never emit
    \\' inside their hallucinated single-quote strings).
    """
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
            # We're inside a single-quoted span we are rewriting to double-quoted.
            if ch == "\\" and i + 1 < n:
                # Preserve any escape, but if it's \', emit ' (just the char).
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
                # Escape an inner double quote
                out.append('\\"')
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        # Not in any string
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
    # Unterminated single-quoted run — close it
    if in_single:
        out.append('"')
    return "".join(out)


def _fix_unescaped_interior_quotes(s: str) -> str:
    """Heuristic: fix lines like  "key": "value with "interior" quotes"

    Algorithm: walk the buffer, track whether we're inside a JSON string.
    When inside a string, if we hit a `"` that is NOT followed (after
    whitespace) by `,`, `}`, `]`, or `:`, treat it as an unescaped
    interior quote and escape it.
    """
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
        # In string
        if ch == "\\" and i + 1 < n:
            out.append(ch)
            out.append(s[i + 1])
            i += 2
            continue
        if ch == '"':
            # Look ahead: is this a real string-terminator?
            j = i + 1
            while j < n and s[j] in " \t\r\n":
                j += 1
            if j >= n or s[j] in ",}]:":
                # Real terminator
                out.append(ch)
                in_str = False
                i += 1
                continue
            # Unescaped interior quote — escape it
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

    The function never raises; it just hands back its best guess.
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


def validate_json(raw_or_dict: Any, schema_cls: type) -> tuple[bool, str | None, Any]:
    """Parse + schema-validate.

    Accepts either a raw string (will json.loads) or an already-parsed dict.
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

    if not hasattr(schema_cls, "validate"):
        return False, f"schema_cls {schema_cls!r} has no .validate() classmethod", None
    return schema_cls.validate(parsed)


# ---------------------------------------------------------------------------
# Retry orchestrator
# ---------------------------------------------------------------------------


def guardrailed_llm_call(
    prompt_fn: Callable[[str | None], str],
    llm_caller: Callable[[str], str],
    schema_cls: type,
    max_retries: int = 3,
) -> tuple[Any | None, list[str]]:
    """Run an LLM call wrapped in the full guardrail stack.

    Args:
        prompt_fn: callable taking optional `last_error` hint (or None on first
            attempt) and returning the prompt string to send.
        llm_caller: callable taking a prompt string and returning raw LLM
            output text.
        schema_cls: a class with a `.validate(d) -> (ok, err, instance)`
            classmethod (e.g. from llm_schemas).
        max_retries: maximum number of LLM calls (default 3).

    Returns:
        (parsed_instance_or_none, list_of_error_strings)

        - If validation eventually succeeds: (instance, [errs from earlier attempts])
        - If all attempts fail: (None, [errs from all attempts])
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


__all__ = [
    "state_machine_fix",
    "validate_json",
    "guardrailed_llm_call",
]
