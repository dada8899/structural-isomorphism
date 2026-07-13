#!/usr/bin/env python3
"""Fail-closed contract for current public copy and research claims."""

from __future__ import annotations

import argparse
import base64
import binascii
import html
import json
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "evaluation/research/current-public-copy-v1.json"

_DEFAULT_IGNORABLE_RANGES = (
    (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F),
    (0xFE00, 0xFE0F), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
)


def _normalize_scan_text(value: str) -> str:
    """Canonicalize compatibility forms and remove invisible splitters."""
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(
        char for char in normalized
        if unicodedata.category(char) != "Cf"
        and ord(char) not in {0x034F, 0x3164, 0xFFA0}
        and not any(start <= ord(char) <= end for start, end in _DEFAULT_IGNORABLE_RANGES)
    )


def load_inventory(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "current-public-copy-v1":
        raise ValueError("current public copy inventory schema mismatch")
    return value


class _LocalDependencyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sources: list[str] = []
        self.stylesheets: list[str] = []
        self.inline_scripts: list[str] = []
        self.inline_styles: list[str] = []
        self._capture: tuple[str, list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        if tag == "script":
            if values.get("src"):
                self.sources.append(values["src"])
            else:
                self._capture = ("script", [])
        elif tag == "style":
            self._capture = ("style", [])
        elif tag == "link" and "stylesheet" in values.get("rel", "").casefold().split():
            if values.get("href"):
                self.stylesheets.append(values["href"])

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._capture[1].append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._capture is None or self._capture[0] != tag:
            return
        value = "".join(self._capture[1])
        (self.inline_scripts if tag == "script" else self.inline_styles).append(value)
        self._capture = None


_JS_ESCAPE = re.compile(r"\\(?:u\{([0-9a-fA-F]+)\}|u([0-9a-fA-F]{4})|x([0-9a-fA-F]{2})|(.))", re.DOTALL)


def _decode_js_escapes(value: str) -> str:
    simple = {"n": "\n", "r": "\r", "t": "\t", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}

    def replace(match: re.Match[str]) -> str:
        codepoint = match.group(1) or match.group(2) or match.group(3)
        if codepoint:
            try:
                return chr(int(codepoint, 16))
            except (ValueError, OverflowError):
                return match.group(0)
        escaped = match.group(4) or ""
        return simple.get(escaped, escaped)

    return _JS_ESCAPE.sub(replace, value)


def _scan_js_literals(text: str) -> list[tuple[int, int, str, str]]:
    """Return quote-aware JS literals while excluding comments."""
    literals: list[tuple[int, int, str, str]] = []
    index = 0
    while index < len(text):
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        quote = text[index]
        if quote not in "'\"`":
            index += 1
            continue
        cursor = index + 1
        while cursor < len(text):
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text[cursor] == quote:
                raw = text[index + 1:cursor]
                literals.append((index, cursor + 1, quote, _decode_js_escapes(raw)))
                index = cursor + 1
                break
            cursor += 1
        else:
            index += 1
    return literals


def _split_top_level(value: str, delimiter: str) -> list[str]:
    parts: list[str] = []
    start = 0
    quote = ""
    escaped = False
    depth = 0
    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "'\"`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}" and depth:
            depth -= 1
        elif char == delimiter and depth == 0:
            parts.append(value[start:index])
            start = index + 1
    parts.append(value[start:])
    return parts


def _strip_wrapping_parentheses(value: str) -> str:
    value = value.strip()
    while value.startswith("(") and value.endswith(")"):
        inner = value[1:-1]
        if len(_split_top_level(inner, ",")) != 1:
            break
        value = inner.strip()
    return value


def _eval_static_js_expr(expression: str, bindings: dict[str, str]) -> str | None:
    expression = _strip_wrapping_parentheses(expression.strip())
    parts = _split_top_level(expression, "+")
    if len(parts) > 1:
        values = [_eval_static_js_expr(part, bindings) for part in parts]
        return None if any(value is None for value in values) else "".join(values)  # type: ignore[arg-type]
    if re.fullmatch(r"[A-Za-z_$][\w$]*", expression):
        return bindings.get(expression)
    literals = _scan_js_literals(expression)
    if len(literals) != 1 or literals[0][0] != 0 or literals[0][1] != len(expression):
        return None
    _, _, quote, value = literals[0]
    if quote != "`":
        return value
    rendered: list[str] = []
    cursor = 0
    for match in re.finditer(r"\$\{([^{}]+)\}", value):
        rendered.append(value[cursor:match.start()])
        interpolation = _eval_static_js_expr(match.group(1), bindings)
        if interpolation is None:
            return None
        rendered.append(interpolation)
        cursor = match.end()
    rendered.append(value[cursor:])
    return "".join(rendered)


def _js_statements(text: str) -> list[str]:
    """Split JS statements, including statements nested in function blocks."""
    statements: list[str] = []
    start = 0
    quote = ""
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            index = len(text) if newline < 0 else newline + 1
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            continue
        if char in "'\"`":
            quote = char
        elif char == ";" or (
            char == "\n"
            and text[start:index].rstrip()
            and text[start:index].rstrip()[-1] not in "=+-*/%,.([{?:\\"
            and text[index + 1:].lstrip()[:1] not in "+-*/%,.)]}"
        ):
            statement = text[start:index].strip()
            if statement:
                statements.append(statement)
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        statements.append(tail)
    return statements


def _call_arguments(statement: str, function: str) -> list[list[str]]:
    calls: list[list[str]] = []
    marker = function + "("
    cursor = 0
    while True:
        start = statement.find(marker, cursor)
        if start < 0:
            return calls
        body_start = start + len(marker)
        quote = ""
        escaped = False
        depth = 0
        for index in range(body_start, len(statement)):
            char = statement[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in "'\"`":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    calls.append(_split_top_level(statement[body_start:index], ","))
                    cursor = index + 1
                    break
                depth -= 1
        else:
            return calls


def _method_calls(statement: str, method: str) -> list[tuple[str, list[str]]]:
    calls: list[tuple[str, list[str]]] = []
    pattern = re.compile(
        rf"([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\.\s*{re.escape(method)}\s*\("
    )
    for match in pattern.finditer(statement):
        receiver = re.sub(r"\s+", "", match.group(1))
        body_start = match.end()
        quote = ""
        escaped = False
        depth = 0
        for index in range(body_start, len(statement)):
            char = statement[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
                continue
            if char in "'\"`":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    calls.append((receiver, _split_top_level(statement[body_start:index], ",")))
                    break
                depth -= 1
    return calls


def _dom_expression_kind(expression: str, dom_bindings: dict[str, str]) -> str | None:
    expression = _strip_wrapping_parentheses(expression.strip())
    if expression in {"document.body", "document.head", "document.documentElement"}:
        return "element"
    if expression in dom_bindings:
        return dom_bindings[expression]
    create = re.fullmatch(r"document\.createElement\(\s*(['\"])([^'\"]+)\1\s*\)", expression)
    if create:
        tag = create.group(2).casefold()
        return tag if tag in {"script", "link"} else "element"
    if re.fullmatch(
        r"document\.(?:querySelector|getElementById|getElementsByName)\([^)]*\)",
        expression,
    ):
        return "element"
    query = re.fullmatch(r"([A-Za-z_$][\w$]*)\.querySelector\([^)]*\)", expression)
    if query and query.group(1) in dom_bindings:
        return "element"
    return None


def _receiver_is_dom(receiver: str, dom_bindings: dict[str, str]) -> bool:
    return receiver in {"document", "document.body", "document.head", "document.documentElement"} or (
        receiver.split(".", 1)[0] in dom_bindings
    )


def _js_analysis(text: str) -> tuple[list[str], list[str]]:
    """Return dependency candidates and strings proven to enter public DOM sinks."""
    dependency_values: list[str] = []
    rendered_values: list[str] = []
    bindings: dict[str, str] = {}
    dom_bindings: dict[str, str] = {}
    for statement in _js_statements(text):
        declaration = re.search(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(.+)$", statement, re.DOTALL)
        if declaration:
            name, expression = declaration.group(1), declaration.group(2)
            rendered = _eval_static_js_expr(expression, bindings)
            if rendered is not None:
                bindings[name] = rendered
            dom_kind = _dom_expression_kind(expression, dom_bindings)
            if dom_kind is not None:
                dom_bindings[name] = dom_kind
        assignment = re.search(
            r"([A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)\s*\.\s*"
            r"(?:textContent|innerText|innerHTML|title|ariaLabel)\s*=\s*(.+)$",
            statement,
            re.DOTALL,
        )
        if assignment and _receiver_is_dom(re.sub(r"\s+", "", assignment.group(1)), dom_bindings):
            rendered = _eval_static_js_expr(assignment.group(2), bindings)
            if rendered is not None:
                rendered_values.append(rendered)
        for method, argument_index in (
            ("insertAdjacentHTML", 1),
            ("insertAdjacentText", 1),
            ("write", 0),
        ):
            for receiver, arguments in _method_calls(statement, method):
                if not _receiver_is_dom(receiver, dom_bindings):
                    continue
                if len(arguments) <= argument_index:
                    continue
                rendered = _eval_static_js_expr(arguments[argument_index], bindings)
                if rendered is not None:
                    rendered_values.append(rendered)
        for receiver, arguments in _method_calls(statement, "setAttribute"):
            if not _receiver_is_dom(receiver, dom_bindings):
                continue
            if len(arguments) < 2:
                continue
            attribute = _eval_static_js_expr(arguments[0], bindings)
            if attribute is None or not (
                attribute.casefold() == "title"
                or attribute.casefold().startswith("aria-")
            ):
                continue
            rendered = _eval_static_js_expr(arguments[1], bindings)
            if rendered is not None:
                rendered_values.append(rendered)
        for receiver, arguments in _method_calls(statement, "append"):
            if not _receiver_is_dom(receiver, dom_bindings):
                continue
            for argument in arguments:
                rendered = _eval_static_js_expr(argument, bindings)
                if rendered is not None:
                    rendered_values.append(rendered)
        for receiver, arguments in _method_calls(statement, "appendChild"):
            if not _receiver_is_dom(receiver, dom_bindings):
                continue
            if not arguments:
                continue
            nested = _method_calls(arguments[0], "createTextNode")
            if nested and nested[0][0] == "document" and nested[0][1]:
                rendered = _eval_static_js_expr(nested[0][1][0], bindings)
                if rendered is not None:
                    rendered_values.append(rendered)

        for function in ("fetch", "require", "import"):
            for arguments in _call_arguments(statement, function):
                if arguments:
                    dependency = _eval_static_js_expr(arguments[0], bindings)
                    if dependency is not None:
                        dependency_values.append(dependency)
        for receiver, arguments in _method_calls(statement, "setAttribute"):
            if receiver not in dom_bindings or len(arguments) < 2:
                continue
            attribute = _eval_static_js_expr(arguments[0], bindings)
            if (
                (dom_bindings[receiver] == "script" and attribute == "src")
                or (dom_bindings[receiver] == "link" and attribute == "href")
            ):
                dependency = _eval_static_js_expr(arguments[1], bindings)
                if dependency is not None:
                    dependency_values.append(dependency)
        asset_assignment = re.search(
            r"([A-Za-z_$][\w$]*)\s*\.\s*(src|href)\s*=\s*(.+)$",
            statement,
            re.DOTALL,
        )
        if asset_assignment:
            receiver, attribute, expression = asset_assignment.groups()
            expected = "src" if dom_bindings.get(receiver) == "script" else "href"
            if dom_bindings.get(receiver) in {"script", "link"} and attribute == expected:
                dependency = _eval_static_js_expr(expression, bindings)
                if dependency is not None:
                    dependency_values.append(dependency)
    for match in re.finditer(
        r"\b(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?(['\"])(.*?)\1",
        text,
    ):
        dependency_values.append(_decode_js_escapes(match.group(2)))
    return (
        list(dict.fromkeys(dependency_values)),
        list(dict.fromkeys(rendered_values)),
    )


def _js_dependency_strings(text: str) -> list[str]:
    return _js_analysis(text)[0]


def _decode_css_escapes(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return match.group(0)
        return match.group(2) or ""

    return re.sub(r"\\([0-9a-fA-F]{1,6})(?:\s)?|\\(.)", replace, value, flags=re.DOTALL)


def _css_strings(text: str) -> list[str]:
    values: list[str] = []
    index = 0
    while index < len(text):
        if text[index] not in "'\"":
            index += 1
            continue
        quote = text[index]
        cursor = index + 1
        raw: list[str] = []
        while cursor < len(text):
            if text[cursor] == "\\" and cursor + 1 < len(text):
                raw.extend((text[cursor], text[cursor + 1]))
                cursor += 2
                continue
            if text[cursor] == quote:
                values.append(_decode_css_escapes("".join(raw)))
                index = cursor + 1
                break
            raw.append(text[cursor])
            cursor += 1
        else:
            index += 1
    return values


def _data_css_text(specifier: str) -> str | None:
    if not specifier.casefold().startswith("data:text/css"):
        return None
    header, separator, payload = specifier.partition(",")
    if not separator:
        return None
    try:
        data = base64.b64decode(payload, validate=True) if ";base64" in header.casefold() else unquote_to_bytes(payload)
        return data.decode("utf-8", errors="replace")
    except (ValueError, binascii.Error):
        return None


def _css_import_specifiers(text: str) -> list[str]:
    without_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    imports: list[str] = []
    for match in re.finditer(
        r"@import\s+(?:url\(\s*(?:(['\"])(.*?)\1|([^)'\"\s]+))\s*\)|(['\"])(.*?)\4)",
        without_comments,
        re.IGNORECASE,
    ):
        imports.append(match.group(2) or match.group(3) or match.group(5))
    return imports


def _css_content_units(text: str) -> list[str]:
    """Resolve statically visible CSS generated content, including adjacent strings."""
    without_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    units: list[str] = []
    for declaration in re.finditer(r"\bcontent\s*:\s*(.*?)(?:;|})", without_comments, re.IGNORECASE | re.DOTALL):
        literals = _css_strings(declaration.group(1))
        if literals:
            units.append("".join(literals))
    for specifier in _css_import_specifiers(without_comments):
        inline = _data_css_text(specifier)
        if inline is not None:
            units.extend(_css_content_units(inline))
    return units


def _render_static_value(value: str) -> list[str]:
    if "<" not in value or ">" not in value:
        return [html.unescape(value)]
    parser = _VisibleUnitParser()
    parser.feed(value)
    parser.close()
    return parser.result()


def _js_render_units(text: str) -> list[str]:
    return [unit for value in _js_analysis(text)[1] for unit in _render_static_value(value)]


def _resolve_local_dependency(root: Path, source: Path, specifier: str) -> Path | None:
    parsed = urlsplit(specifier)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    if parsed.path.startswith("/"):
        candidate = root / "web/frontend" / parsed.path.lstrip("/")
    else:
        candidate = source.parent / parsed.path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"unsafe local dependency {specifier!r} from {source}") from exc
    return resolved


def _public_dependency_paths(root: Path) -> list[str]:
    """Discover public HTML and its local JS/JSON/CSS dependency closure."""
    frontend = root / "web/frontend"
    queue = sorted(frontend.glob("*.html"))
    seen: set[Path] = set()
    discovered: list[str] = []
    while queue:
        target = queue.pop(0).resolve()
        if target in seen:
            continue
        seen.add(target)
        if not target.is_file():
            raise ValueError(f"missing public dependency: {target.relative_to(root)}")
        relative = target.relative_to(root.resolve()).as_posix()
        discovered.append(relative)
        text = target.read_text(encoding="utf-8")
        dependencies: list[str] = []
        if target.suffix.casefold() in {".html", ".htm"}:
            parser = _LocalDependencyParser()
            parser.feed(text)
            parser.close()
            dependencies.extend(parser.sources + parser.stylesheets)
        elif target.suffix.casefold() == ".js":
            for value in _js_dependency_strings(text):
                if urlsplit(value).path.casefold().endswith((".js", ".json", ".css")):
                    dependencies.append(value)
        elif target.suffix.casefold() == ".css":
            dependencies.extend(_css_import_specifiers(text))
        for specifier in dependencies:
            dependency = _resolve_local_dependency(root, target, specifier)
            if dependency is not None:
                if not dependency.is_file():
                    raise ValueError(
                        f"missing local dependency {specifier!r} from {relative}"
                    )
                queue.append(dependency)
    return discovered


def _paths(inventory: dict[str, Any], root: Path) -> list[str]:
    scope = inventory.get("scope")
    if not isinstance(scope, dict):
        raise ValueError("scope must be an object")
    declared = scope.get("runtime_pages", []) + scope.get("current_documents", [])
    if not declared or not all(isinstance(path, str) and path for path in declared):
        raise ValueError("inventory paths must be non-empty strings")
    if len(declared) != len(set(declared)):
        raise ValueError("inventory paths must be unique")
    return list(dict.fromkeys(declared + _public_dependency_paths(root)))


def _json_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in _json_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _json_strings(child)]
    return []


def _json_render_units(value: Any) -> list[str]:
    """Scan each JSON value and every complete renderable container mapping."""
    units: list[str] = []
    if isinstance(value, str):
        return [value]
    children = list(value.values()) if isinstance(value, dict) else value if isinstance(value, list) else []
    if not children:
        return units
    leaves = _json_strings(value)
    if leaves:
        units.extend(("".join(leaves), " ".join(leaves)))
    for child in children:
        units.extend(_json_render_units(child))
    return units


class _VisibleUnitParser(HTMLParser):
    """Collect visible block text while preserving inline text-node boundaries."""

    _BLOCKS = {
        "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "title",
        "summary", "figcaption", "td", "th", "button", "div", "section",
    }
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.units: list[str] = []
        self._visibility: list[bool] = []
        self._frames: list[tuple[str, list[str]]] = []
        self._loose: list[str] = []
        self.text_nodes: list[str] = []
        self.attribute_units: list[str] = []

    @staticmethod
    def _is_hidden(tag: str, attrs: dict[str, str]) -> bool:
        style = re.sub(r"\s+", "", attrs.get("style", "").casefold())
        transform = re.search(r"(?:^|;)transform:([^;]+)", style)
        scale_zero = False
        translated_offscreen = False
        if transform:
            for scale in re.finditer(r"scale(?:x|y|3d)?\(([^)]*)\)", transform.group(1)):
                args = scale.group(1).split(",")
                try:
                    scale_zero = scale_zero or any(float(arg) == 0 for arg in args)
                except ValueError:
                    pass
            for translate in re.finditer(r"translate(?:x|y|3d)?\(([^)]*)\)", transform.group(1)):
                translated_offscreen = translated_offscreen or bool(
                    re.search(r"(?:^|,)[+-]?(?:[1-9]\d{3,}|\d{5,})(?:px|em|rem|vw|vh)(?:,|$)", translate.group(1))
                )
        clipped = bool(
            re.search(r"(?:^|;)clip:rect\((?:0(?:px)?[,]?){4}\)(?:;|$)", style)
            or re.search(r"(?:^|;)clip-path:inset\((?:50|100)%", style)
        )
        collapsed_overflow = (
            "overflow:hidden" in style
            and bool(re.search(
                r"(?:^|;)(?:width|height|max-width|max-height):(?:0|0\.0*|\.0+)"
                r"(?:px|pt|pc|em|rem|%|vh|vw|vmin|vmax)?(?:!important)?(?:;|$)",
                style,
            ))
        )
        return (
            tag in {"script", "style", "template", "noscript"}
            or "hidden" in attrs
            or attrs.get("aria-hidden", "").casefold() == "true"
            or (tag == "input" and attrs.get("type", "").casefold() == "hidden")
            or "display:none" in style
            or "visibility:hidden" in style
            or "opacity:0" in style
            or bool(re.search(r"(?:^|;)font-size:(?:0|0\.0+)(?:px|pt|pc|em|rem|%|vh|vw|vmin|vmax)?(?:!important)?(?:;|$)", style))
            or bool(re.search(r"(?:^|;)font:0(?:[;/]|!important|$)", style))
            or "color:transparent" in style
            or "clip-path:inset(100%)" in style
            or scale_zero
            or translated_offscreen
            or (
                ("position:absolute" in style or "position:fixed" in style)
                and bool(re.search(
                    r"(?:left|right|top|bottom):[+-]?(?:[1-9]\d{3,}|\d{5,})(?:px|em|rem|vw|vh)",
                    style,
                ))
            )
            or clipped
            or collapsed_overflow
            or bool({"hidden", "visually-hidden", "sr-only"} & set(attrs.get("class", "").casefold().split()))
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        visible = (self._visibility[-1] if self._visibility else True) and not self._is_hidden(tag, values)
        if visible and tag == "meta" and values.get("content"):
            self.units.append(values["content"])
            self.attribute_units.append(values["content"])
        if visible:
            for attribute in ("aria-label", "title"):
                if values.get(attribute):
                    self.units.append(values[attribute])
                    self.attribute_units.append(values[attribute])
        if tag in self._VOID:
            return
        self._visibility.append(visible)
        if visible and tag in self._BLOCKS:
            self._frames.append((tag, []))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._visibility and not self._visibility[-1]:
            return
        self._loose.append(data)
        if data.strip():
            self.text_nodes.append(html.unescape(data))
        for _, parts in self._frames:
            parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        visible = self._visibility.pop() if self._visibility else True
        if not visible or tag not in self._BLOCKS:
            return
        for index in range(len(self._frames) - 1, -1, -1):
            frame_tag, parts = self._frames[index]
            if frame_tag == tag:
                self._frames.pop(index)
                value = html.unescape("".join(parts)).strip()
                if value:
                    self.units.append(value)
                break

    def result(self) -> list[str]:
        if self.units:
            return self.units
        value = html.unescape("".join(self._loose)).strip()
        return [value] if value else []


def _visible_claim_units(relative: str, text: str) -> list[str]:
    """Return independent visible semantic units for caveat adjudication."""
    if relative.endswith(".json"):
        try:
            return _json_render_units(json.loads(text))
        except json.JSONDecodeError:
            return [text]
    if relative.endswith((".html", ".htm")):
        visible = _VisibleUnitParser()
        visible.feed(text)
        visible.close()
        dependencies = _LocalDependencyParser()
        dependencies.feed(text)
        dependencies.close()
        runtime = [
            unit
            for script in dependencies.inline_scripts
            for unit in _js_render_units(script)
        ]
        generated = [
            unit
            for style in dependencies.inline_styles
            for unit in _css_content_units(style)
        ]
        generated.extend(
            unit
            for stylesheet in dependencies.stylesheets
            for inline in [_data_css_text(stylesheet)]
            if inline is not None
            for unit in _css_content_units(inline)
        )
        return visible.result() + runtime + generated
    if relative.endswith(".js"):
        return _js_render_units(text)
    if relative.endswith(".css"):
        return _css_content_units(text)
    return [html.unescape(text)]


def _claim_context_units(relative: str, text: str) -> list[str]:
    """Return atomic rendered units; caveats may not jump text/data nodes."""
    if relative.endswith(".json"):
        try:
            return _json_strings(json.loads(text))
        except json.JSONDecodeError:
            return [text]
    if relative.endswith((".html", ".htm")):
        visible = _VisibleUnitParser()
        visible.feed(text)
        visible.close()
        dependencies = _LocalDependencyParser()
        dependencies.feed(text)
        dependencies.close()
        runtime = [
            unit
            for script in dependencies.inline_scripts
            for unit in _js_render_units(script)
        ]
        generated = [
            unit
            for style in dependencies.inline_styles
            for unit in _css_content_units(style)
        ]
        generated.extend(
            unit
            for stylesheet in dependencies.stylesheets
            for inline in [_data_css_text(stylesheet)]
            if inline is not None
            for unit in _css_content_units(inline)
        )
        return visible.text_nodes + visible.attribute_units + runtime + generated
    if relative.endswith(".js"):
        return _js_render_units(text)
    if relative.endswith(".css"):
        return _css_content_units(text)
    return [html.unescape(text)]


def _regex_scan_units(relative: str, text: str) -> list[str]:
    """Return normalized complete visible/renderable units."""
    return [_normalize_scan_text(unit) for unit in _visible_claim_units(relative, text)]


_SENTENCE_BOUNDARY = re.compile(r"[.!?。！？；;\n]+")


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    before = list(_SENTENCE_BOUNDARY.finditer(text, 0, start))
    after = _SENTENCE_BOUNDARY.search(text, end)
    return (before[-1].end() if before else 0, after.start() if after else len(text))


def validate(inventory_path: Path = DEFAULT_INVENTORY, root: Path = ROOT) -> list[str]:
    try:
        inventory = load_inventory(inventory_path)
        paths = _paths(inventory, root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot load inventory: {exc}"]
    errors: list[str] = []
    contents: dict[str, str] = {}
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe inventory path: {relative}")
            continue
        target = root / path
        if not target.is_file():
            errors.append(f"missing public copy surface: {relative}")
            continue
        contents[relative] = target.read_text(encoding="utf-8")
    normalized_contents = {
        relative: _normalize_scan_text(text).casefold()
        for relative, text in contents.items()
    }
    rendered_units = {
        relative: _regex_scan_units(relative, text)
        for relative, text in contents.items()
    }
    context_units = {
        relative: [_normalize_scan_text(unit) for unit in _claim_context_units(relative, text)]
        for relative, text in contents.items()
    }
    forbidden = inventory.get("forbidden_patterns")
    if not isinstance(forbidden, list) or not forbidden:
        errors.append("forbidden_patterns must be a non-empty list")
    else:
        for pattern in forbidden:
            if not isinstance(pattern, str) or not pattern:
                errors.append("forbidden pattern must be a non-empty string")
                continue
            for relative in contents:
                normalized_pattern = _normalize_scan_text(pattern).casefold()
                suffix = Path(relative).suffix.casefold()
                raw_public_copy = suffix not in {".html", ".htm", ".js", ".css", ".json"}
                if (raw_public_copy and normalized_pattern in normalized_contents[relative]) or any(
                    normalized_pattern in unit.casefold()
                    for unit in rendered_units[relative]
                ):
                    errors.append(f"forbidden public claim {pattern!r} in {relative}")
    forbidden_regex = inventory.get("forbidden_regex")
    if not isinstance(forbidden_regex, list) or not forbidden_regex:
        errors.append("forbidden_regex must be a non-empty list")
    else:
        for pattern in forbidden_regex:
            if not isinstance(pattern, str) or not pattern:
                errors.append("forbidden regex must be a non-empty string")
                continue
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error as exc:
                errors.append(f"invalid forbidden regex {pattern!r}: {exc}")
                continue
            for relative in contents:
                rendered = rendered_units[relative]
                if any(compiled.search(fragment) for fragment in rendered):
                    errors.append(f"forbidden public claim regex {pattern!r} in {relative}")
    adjacent_rules = inventory.get("adjacent_context_rules")
    if not isinstance(adjacent_rules, list) or not adjacent_rules:
        errors.append("adjacent_context_rules must be a non-empty list")
    else:
        for index, rule in enumerate(adjacent_rules):
            expected = {"claim_regex", "caveat_regex", "window"}
            if not isinstance(rule, dict) or set(rule) != expected:
                errors.append(f"adjacent_context_rules[{index}] schema mismatch")
                continue
            if not isinstance(rule["window"], int) or not 40 <= rule["window"] <= 500:
                errors.append(f"adjacent_context_rules[{index}] window must be 40..500")
                continue
            try:
                claim = re.compile(rule["claim_regex"], re.IGNORECASE)
                caveat = re.compile(rule["caveat_regex"], re.IGNORECASE)
            except (re.error, TypeError) as exc:
                errors.append(f"invalid adjacent context regex at {index}: {exc}")
                continue
            for relative in contents:
                visible_units = context_units[relative]
                for fragment in visible_units:
                    for match in claim.finditer(fragment):
                        sentence_start, sentence_end = _sentence_bounds(
                            fragment, match.start(), match.end()
                        )
                        start = max(sentence_start, match.start() - rule["window"])
                        end = min(sentence_end, match.end() + rule["window"])
                        bounded = False
                        for caveat_match in caveat.finditer(fragment[start:end]):
                            absolute_start = start + caveat_match.start()
                            absolute_end = start + caveat_match.end()
                            # The caveat must bind this exact occurrence, not a
                            # different entity elsewhere in the same sentence.
                            if absolute_start < match.end() and absolute_end > match.start():
                                bounded = True
                                break
                        if not bounded:
                            errors.append(
                                f"unbounded public claim {match.group(0)!r} in {relative}; "
                                "missing adjacent caveat"
                            )
                if relative.endswith((".html", ".htm", ".json")):
                    atomic_count = sum(len(list(claim.finditer(unit))) for unit in visible_units)
                    rendered_count = max(
                        (len(list(claim.finditer(unit))) for unit in rendered_units[relative]),
                        default=0,
                    )
                    for _ in range(max(0, rendered_count - atomic_count)):
                        errors.append(
                            f"cross-node public claim in {relative}; caveat must share one text node"
                        )
    rules = inventory.get("required_context")
    if not isinstance(rules, list) or not rules:
        errors.append("required_context must be a non-empty list")
    else:
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict) or set(rule) != {"path", "patterns"}:
                errors.append(f"required_context[{index}] schema mismatch")
                continue
            text = contents.get(rule["path"])
            if text is None:
                errors.append(f"required context path is outside inventory: {rule['path']}")
                continue
            for pattern in rule["patterns"]:
                if pattern not in text:
                    errors.append(f"missing required context {pattern!r} in {rule['path']}")
    context_rules = inventory.get("context_rules")
    if not isinstance(context_rules, list) or not context_rules:
        errors.append("context_rules must document ambiguous claim terms")
    readability = inventory.get("readability_contract")
    required_readability = {"first_use", "two_layers", "actionable_states", "buttons", "restatement_test"}
    if not isinstance(readability, dict) or set(readability) != required_readability:
        errors.append("readability_contract must define all five public-copy rules")
    elif not all(isinstance(value, str) and value.strip() for value in readability.values()):
        errors.append("readability_contract rules must be non-empty strings")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()
    errors = validate(args.inventory.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("current public copy claim contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
