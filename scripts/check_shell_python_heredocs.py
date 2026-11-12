#!/usr/bin/env python3
"""Compile Python embedded in shell heredocs before release.

``bash -n`` validates only the surrounding shell grammar.  It deliberately
does not parse a heredoc body as Python, so an indentation or syntax error can
otherwise survive every shell check and fail only during deployment.

The gate also rejects unquoted Python heredoc delimiters.  Values must cross
the shell/Python boundary through argv or the environment; allowing shell
expansion inside Python source makes both static compilation and escaping
unsafe.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".venv-openapi",
    "node_modules",
    "venv",
}
DELIMITER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PY_VARIABLE_RE = re.compile(r"\$(?:\{)?PY(?:\})?(?![A-Za-z0-9_])")


@dataclass(frozen=True)
class PythonHeredoc:
    path: Path
    declaration_line: int
    start_line: int
    delimiter: str
    quoted: bool
    strip_tabs: bool
    command: str
    source: str


@dataclass(frozen=True)
class HeredocIssue:
    path: Path
    line: int
    message: str

    def render(self, root: Path | None = None) -> str:
        try:
            display = self.path.relative_to(root) if root is not None else self.path
        except ValueError:
            display = self.path
        return f"{display}:{self.line}: {self.message}"


@dataclass(frozen=True)
class _Declaration:
    delimiter: str
    quoted: bool
    strip_tabs: bool


def _comment_starts(line: str, index: int) -> bool:
    """Return whether ``#`` starts a shell comment at this position."""

    if index == 0:
        return True
    return line[index - 1].isspace() or line[index - 1] in ";|&(){}"


def _declarations(line: str) -> list[_Declaration]:
    """Find heredoc declarations outside shell quotes and comments.

    This is intentionally a small lexer rather than a regular expression: a
    Python string such as ``python -c 'value << other'`` must not be mistaken
    for a heredoc.  It accepts bare, single-quoted, double-quoted, and
    backslash-quoted identifier delimiters, which covers the portable forms
    used by this repository.
    """

    found: list[_Declaration] = []
    index = 0
    quote: str | None = None
    while index < len(line):
        character = line[index]
        if quote is not None:
            if character == "\\" and quote == '"':
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character == "#" and _comment_starts(line, index):
            break
        if not line.startswith("<<", index) or line.startswith("<<<", index):
            index += 1
            continue

        cursor = index + 2
        strip_tabs = cursor < len(line) and line[cursor] == "-"
        if strip_tabs:
            cursor += 1
        while cursor < len(line) and line[cursor] in " \t":
            cursor += 1

        quoted = False
        delimiter = ""
        if cursor < len(line) and line[cursor] in {"'", '"'}:
            marker = line[cursor]
            quoted = True
            end = line.find(marker, cursor + 1)
            if end != -1:
                delimiter = line[cursor + 1 : end]
                cursor = end + 1
        elif cursor < len(line) and line[cursor] == "\\":
            quoted = True
            match = DELIMITER_RE.match(line, cursor + 1)
            if match:
                delimiter = match.group(0)
                cursor = match.end()
        else:
            match = DELIMITER_RE.match(line, cursor)
            if match:
                delimiter = match.group(0)
                cursor = match.end()

        if delimiter and DELIMITER_RE.fullmatch(delimiter):
            found.append(
                _Declaration(
                    delimiter=delimiter,
                    quoted=quoted,
                    strip_tabs=strip_tabs,
                )
            )
            index = cursor
        else:
            index += 2
    return found


def _command_context(lines: Sequence[str], line_index: int) -> str:
    start = line_index
    while start > 0 and lines[start - 1].rstrip("\r\n").rstrip().endswith("\\"):
        start -= 1
    return "".join(lines[start : line_index + 1])


def _is_python(command: str, delimiter: str) -> bool:
    normalized = delimiter.upper()
    return (
        normalized == "PY"
        or normalized.startswith("PYTHON")
        or normalized.startswith("PYEOF")
        or "python" in command.casefold()
        or PY_VARIABLE_RE.search(command) is not None
    )


def extract_python_heredocs(path: Path) -> tuple[list[PythonHeredoc], list[HeredocIssue]]:
    """Extract Python heredocs and report unterminated Python bodies."""

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    blocks: list[PythonHeredoc] = []
    issues: list[HeredocIssue] = []
    line_index = 0
    while line_index < len(lines):
        first_declarations = _declarations(lines[line_index])
        if not first_declarations:
            line_index += 1
            continue

        # A heredoc body starts after the complete logical command, not
        # necessarily after the physical line containing ``<<``.  Production
        # deploys use ``python <<'PY' \\`` followed by an ``|| abort`` clause;
        # treating that clause as Python was precisely the kind of blind spot
        # this gate is meant to eliminate.
        header_end = line_index
        while (
            header_end + 1 < len(lines)
            and lines[header_end].rstrip("\r\n").rstrip().endswith("\\")
        ):
            header_end += 1

        declarations: list[tuple[int, _Declaration]] = [
            (line_index, declaration) for declaration in first_declarations
        ]
        for continuation_index in range(line_index + 1, header_end + 1):
            declarations.extend(
                (continuation_index, declaration)
                for declaration in _declarations(lines[continuation_index])
            )

        command = _command_context(lines, header_end)
        body_index = header_end + 1
        for declaration_line_index, declaration in declarations:
            source_start_line = body_index + 1
            body: list[str] = []
            while body_index < len(lines):
                raw = lines[body_index]
                comparable = raw.rstrip("\r\n")
                if declaration.strip_tabs:
                    comparable = comparable.lstrip("\t")
                if comparable == declaration.delimiter:
                    break
                body.append(raw.lstrip("\t") if declaration.strip_tabs else raw)
                body_index += 1
            else:
                if _is_python(command, declaration.delimiter):
                    issues.append(
                        HeredocIssue(
                            path=path,
                            line=declaration_line_index + 1,
                            message=(
                                "unterminated Python heredoc "
                                f"{declaration.delimiter!r}"
                            ),
                        )
                    )
                return blocks, issues

            if _is_python(command, declaration.delimiter):
                blocks.append(
                    PythonHeredoc(
                        path=path,
                        declaration_line=declaration_line_index + 1,
                        start_line=source_start_line,
                        delimiter=declaration.delimiter,
                        quoted=declaration.quoted,
                        strip_tabs=declaration.strip_tabs,
                        command=command,
                        source="".join(body),
                    )
                )
            body_index += 1
        line_index = body_index
    return blocks, issues


def validate_shell_script(path: Path) -> tuple[list[PythonHeredoc], list[HeredocIssue]]:
    blocks, issues = extract_python_heredocs(path)
    for block in blocks:
        if not block.quoted:
            issues.append(
                HeredocIssue(
                    path=path,
                    line=block.declaration_line,
                    message=(
                        "shell-interpolated Python heredoc is forbidden; "
                        "pass values through argv or environment variables"
                    ),
                )
            )
            continue
        try:
            compile(
                block.source,
                f"{path}:{block.start_line}",
                "exec",
            )
        except (SyntaxError, ValueError, OverflowError) as exc:
            relative_line = getattr(exc, "lineno", None) or 1
            message = getattr(exc, "msg", None) or str(exc)
            issues.append(
                HeredocIssue(
                    path=path,
                    line=block.start_line + relative_line - 1,
                    message=f"embedded Python does not compile: {message}",
                )
            )
    return blocks, issues


def shell_scripts(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.sh")):
        if not any(part in SKIP_DIRECTORIES for part in path.relative_to(root).parts):
            yield path


def validate_repository(root: Path) -> tuple[list[PythonHeredoc], list[HeredocIssue]]:
    blocks: list[PythonHeredoc] = []
    issues: list[HeredocIssue] = []
    for path in shell_scripts(root):
        path_blocks, path_issues = validate_shell_script(path)
        blocks.extend(path_blocks)
        issues.extend(path_issues)
    return blocks, issues


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=ROOT)
    arguments = parser.parse_args(argv)
    root = arguments.root.resolve()
    blocks, issues = validate_repository(root)
    if issues:
        for issue in issues:
            print(issue.render(root))
        return 1
    print(f"shell Python heredoc gate ok: {len(blocks)} blocks compiled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
