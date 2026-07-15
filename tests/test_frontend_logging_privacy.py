"""Static privacy gate for browser-side operational telemetry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, NamedTuple

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC_STRING = re.compile(r'^\s*(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')\s*$')
CONSOLE_METHODS = {"error", "warn", "log", "debug", "info"}


class _Token(NamedTuple):
    kind: str
    value: str
    start: int
    end: int


def _skip_quoted(source: str, start: int) -> int:
    quote = source[start]
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
            continue
        if source[index] == quote:
            return index + 1
        index += 1
    return len(source)


def _skip_comment(source: str, start: int) -> int:
    if source.startswith("//", start):
        newline = source.find("\n", start + 2)
        return len(source) if newline < 0 else newline + 1
    end = source.find("*/", start + 2)
    return len(source) if end < 0 else end + 2


def _skip_regex(source: str, start: int) -> int:
    index = start + 1
    in_character_class = False
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == "[":
            in_character_class = True
        elif char == "]":
            in_character_class = False
        elif char == "/" and not in_character_class:
            index += 1
            while index < len(source) and source[index].isalpha():
                index += 1
            return index
        elif char in "\r\n":
            break
        index += 1
    raise AssertionError("unterminated regular expression literal")


def _previous_nonspace(source: str, start: int) -> str:
    index = start - 1
    while index >= 0 and source[index].isspace():
        index -= 1
    return source[index] if index >= 0 else ""


def _template_expression_end(source: str, start: int) -> int:
    depth = 1
    index = start
    while index < len(source):
        char = source[index]
        if char in "'\"":
            index = _skip_quoted(source, index)
            continue
        if char == "`":
            index, _expressions = _template_parts(source, index)
            continue
        if source.startswith("//", index) or source.startswith("/*", index):
            index = _skip_comment(source, index)
            continue
        if char == "/" and _previous_nonspace(source, index) in "([{:;,=!?&|":
            index = _skip_regex(source, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("unterminated template expression")


def _template_parts(source: str, start: int) -> tuple[int, list[tuple[int, int]]]:
    expressions: list[tuple[int, int]] = []
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
            continue
        if source[index] == "`":
            return index + 1, expressions
        if source.startswith("${", index):
            expression_start = index + 2
            expression_end = _template_expression_end(source, expression_start)
            expressions.append((expression_start, expression_end))
            index = expression_end + 1
            continue
        index += 1
    raise AssertionError("unterminated template literal")


def _call_end(source: str, opening: int) -> int:
    depth = 0
    index = opening
    while index < len(source):
        char = source[index]
        if char in "'\"`":
            index = _skip_quoted(source, index)
            continue
        if source.startswith("//", index) or source.startswith("/*", index):
            index = _skip_comment(source, index)
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise AssertionError("unterminated console call")


def _tokens(source: str, base_offset: int = 0) -> list[_Token]:
    tokens: list[_Token] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char in "'\"":
            end = _skip_quoted(source, index)
            raw = source[index:end]
            tokens.append(
                _Token("string", raw, base_offset + index, base_offset + end)
            )
            index = end
            continue
        if char == "`":
            end, expressions = _template_parts(source, index)
            for expression_start, expression_end in expressions:
                tokens.extend(
                    _tokens(
                        source[expression_start:expression_end],
                        base_offset + expression_start,
                    )
                )
            index = end
            continue
        if source.startswith("//", index) or source.startswith("/*", index):
            index = _skip_comment(source, index)
            continue
        if char == "/" and (
            not tokens
            or tokens[-1].value in {
                "(", "[", "{", ",", ":", ";", "=", "!", "?", "=>",
                "return", "case", "throw", "||", "&&", "??",
            }
        ):
            end = _skip_regex(source, index)
            tokens.append(
                _Token(
                    "regex", source[index:end],
                    base_offset + index, base_offset + end,
                )
            )
            index = end
            continue
        identifier = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", source[index:])
        if identifier:
            end = index + len(identifier.group(0))
            tokens.append(
                _Token(
                    "identifier", identifier.group(0),
                    base_offset + index, base_offset + end,
                )
            )
            index = end
            continue
        punctuator = next(
            (item for item in ("===", "!==", "=>", "...", "?.", "&&", "||", "??")
             if source.startswith(item, index)),
            char,
        )
        end = index + len(punctuator)
        tokens.append(
            _Token(
                "punctuator", punctuator,
                base_offset + index, base_offset + end,
            )
        )
        index = end
    return tokens


def _console_privacy_violations(source: str) -> tuple[int, list[tuple[int, str]]]:
    """Allow only direct console.method("fixed category") calls.

    Every other reference to the console capability is rejected. This closes
    optional/computed/parenthesized calls and alias/destructure indirection
    without depending on a Node parser during Python-only CI.
    """
    tokens = _tokens(source)
    violations: list[tuple[int, str]] = []
    seen = 0
    for index, token in enumerate(tokens):
        line = source.count("\n", 0, token.start) + 1
        if (
            token.kind == "string"
            and token.value in {'"console"', "'console'"}
            and index >= 2
            and tokens[index - 1].value == "["
            and tokens[index - 2].value in {"window", "globalThis"}
        ):
            violations.append((line, "computed global console capability"))
            continue
        if token.kind != "identifier" or token.value != "console":
            continue

        previous = tokens[index - 1].value if index else ""
        direct = (
            previous not in {".", "?."}
            and index + 3 < len(tokens)
            and tokens[index + 1].value == "."
            and tokens[index + 2].kind == "identifier"
            and tokens[index + 2].value in CONSOLE_METHODS
            and tokens[index + 3].value == "("
        )
        if not direct:
            violations.append((line, "indirect or aliased console capability"))
            continue

        seen += 1
        opening = tokens[index + 3].start
        end = _call_end(source, opening)
        arguments = source[opening + 1 : end]
        if not STATIC_STRING.fullmatch(arguments):
            violations.append((line, f"non-constant console payload: {arguments.strip()[:100]}"))
    return seen, violations


def _production_sources() -> Iterator[Path]:
    yield from sorted((ROOT / "web/frontend/assets/js").rglob("*.js"))
    for directory in ("app", "components", "lib"):
        base = ROOT / "web/phase-detector" / directory
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".js", ".ts", ".tsx"}:
                continue
            if ".stories." in path.name or ".test." in path.name or ".spec." in path.name:
                continue
            yield path


def test_production_console_calls_are_content_free_constants() -> None:
    violations: list[str] = []
    seen = 0
    for path in _production_sources():
        source = path.read_text(encoding="utf-8")
        file_seen, file_violations = _console_privacy_violations(source)
        seen += file_seen
        relative = path.relative_to(ROOT)
        violations.extend(
            f"{relative}:{line}: {reason}" for line, reason in file_violations
        )

    assert seen >= 20, "scanner unexpectedly found too few production console calls"
    assert not violations, "raw browser console telemetry:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    (
        "globalThis.console.error(secret);",
        "window.console.error(secret);",
        "console?.error(secret);",
        "console.error?.(secret);",
        "(console.error)(secret);",
        "const leak = console.error; leak(secret);",
        "const {error: leak} = console; leak(secret);",
        "const sink = console; sink.error(secret);",
        'console["error"](secret);',
        "console[level](secret);",
        'window["console"]["error"](secret);',
        "`${console.error(secret)}`;",
    ),
)
def test_console_gate_rejects_every_indirect_or_dynamic_form(source: str) -> None:
    _seen, violations = _console_privacy_violations(source)
    assert violations, source


def test_console_gate_accepts_only_one_fixed_category_argument() -> None:
    seen, violations = _console_privacy_violations(
        'console.warn("[privacy] fixed category");'
    )
    assert seen == 1
    assert violations == []


def test_phase_error_reporting_never_collects_error_or_device_content() -> None:
    reporter = (ROOT / "web/phase-detector/lib/error-reporter.ts").read_text(
        encoding="utf-8"
    )
    global_boundary = (ROOT / "web/phase-detector/app/global-error.tsx").read_text(
        encoding="utf-8"
    )

    for forbidden in (
        "phase.sessionId",
        "navigator.userAgent",
        "window.location.href",
        "window.location.pathname",
        "error?.message",
        "error?.stack",
        "error?.digest",
    ):
        assert forbidden not in reporter
        assert forbidden not in global_boundary

    assert "message: safeErrorType(input.error)" in reporter
    assert "message: errorType" in global_boundary
    assert "writeQueue(queue);\n  if (typeof navigator" in reporter
    assert "body: JSON.stringify(report)" in reporter
    assert "Add only details you are comfortable sharing publicly" in reporter
    assert "export function buildIssueUrl(): string" in reporter
    assert "Opaque error ID" not in reporter
    assert "new Date().toISOString()" not in reporter
    assert "**Browser**" not in reporter
    assert "**URL**" not in reporter
