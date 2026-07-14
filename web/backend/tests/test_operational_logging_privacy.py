"""Static privacy contract for production operational logging."""
from __future__ import annotations

import ast
import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
LOG_METHODS = {"critical", "debug", "error", "exception", "info", "log", "warning"}
EVENT_RE = re.compile(
    r"^(?:http|auth|account_data|ask|analyze|billing|checkout|llm|retrieval|history|"
    r"privacy|waitlist|newsletter|sentry|startup|shutdown|log|structural)"
    r"\.[a-z0-9_.-]{1,95}$"
)
SAFE_FIELDS = {
    "candidate_count",
    "count",
    "elapsed_ms",
    "env",
    "error_type",
    "expansion_used",
    "fused_count",
    "incident_id",
    "kb_count",
    "latency_ms",
    "method",
    "model",
    "provider_attempted",
    "remaining",
    "request_id",
    "retryable",
    "route_template",
    "safe_path_enabled",
    "sent",
    "status_code",
    "tier",
    "total_recall",
    "translation_used",
}

def _production_files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if "tests" not in path.relative_to(BACKEND_ROOT).parts
        and "data" not in path.relative_to(BACKEND_ROOT).parts
    )


def _logging_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in LOG_METHODS:
            yield node


def _is_reviewed_observability_gateway(relative: Path, call: ast.Call) -> bool:
    """Permit the one legacy stdlib bridge whose formatter rebuilds fields."""
    if relative != Path("services/observability.py"):
        return False
    if not isinstance(call.func.value, ast.Name) or call.func.value.id != "_logger":
        return False
    if call.func.attr != "info" or len(call.args) != 1:
        return False
    if not isinstance(call.args[0], ast.Name) or call.args[0].id != "event":
        return False
    if len(call.keywords) != 1 or call.keywords[0].arg != "extra":
        return False
    return ast.dump(call.keywords[0].value, include_attributes=False) == ast.dump(
        ast.Dict(
            keys=[ast.Constant(value="fields")],
            values=[ast.Name(id="fields", ctx=ast.Load())],
        ),
        include_attributes=False,
    )


def test_production_logging_is_content_free_and_allowlisted() -> None:
    issues: list[str] = []
    for path in _production_files():
        relative = path.relative_to(BACKEND_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(relative))
        for call in _logging_calls(tree):
            if _is_reviewed_observability_gateway(relative, call):
                continue
            location = f"{relative}:{call.lineno}"
            method = call.func.attr
            if method in {"exception", "log"}:
                issues.append(f"{location}: forbidden logger.{method}")
            if len(call.args) != 1:
                issues.append(f"{location}: event must be the sole positional argument")
            elif not isinstance(call.args[0], ast.Constant) or not isinstance(
                call.args[0].value, str
            ):
                issues.append(f"{location}: event must be a constant string")
            elif not EVENT_RE.fullmatch(call.args[0].value):
                issues.append(f"{location}: event is not an allowlisted dotted name")
            for keyword in call.keywords:
                if keyword.arg not in SAFE_FIELDS:
                    issues.append(
                        f"{location}: non-allowlisted field {keyword.arg or '**kwargs'}"
                    )
    assert not issues, "\n" + "\n".join(issues)
