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


def _has_unshadowed_stdlib_sys(tree: ast.AST) -> bool:
    """Recognize the stdlib exception query without exempting a logger alias."""
    if not isinstance(tree, ast.Module):
        return False
    imported = any(
        isinstance(node, ast.Import)
        and any(alias.name == "sys" and alias.asname in (None, "sys") for alias in node.names)
        for node in tree.body
    )
    if not imported:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "sys" and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.arg) and node.arg == "sys":
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == "sys":
            return False
        if isinstance(node, ast.ExceptHandler) and node.name == "sys":
            return False
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "sys":
            return False
        if isinstance(node, ast.MatchMapping) and node.rest == "sys":
            return False
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = alias.asname or alias.name.split(".")[0]
                if bound == "sys" and not (isinstance(node, ast.Import) and alias.name == "sys"):
                    return False
                if isinstance(node, ast.ImportFrom) and alias.name == "*":
                    return False
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "sys" and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("setattr", "delattr") and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "sys":
            return False
    return True


def _logging_calls(tree: ast.AST):
    stdlib_sys = _has_unshadowed_stdlib_sys(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if (stdlib_sys and node.func.attr == "exception"
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "sys"
                and not node.args and not node.keywords):
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


def test_stdlib_active_exception_query_is_not_operational_logging() -> None:
    tree = ast.parse("import sys\ndef cleanup(primary):\n    return sys.exception() is primary\n")
    assert list(_logging_calls(tree)) == []
    tree = ast.parse("import sys\nlogger.exception('structural.cleanup_failed')\nsys.exception()\n")
    calls = list(_logging_calls(tree))
    assert len(calls) == 1 and calls[0].func.value.id == "logger"


def test_sys_name_or_attribute_shadowing_keeps_exception_calls_under_review() -> None:
    sources = (
        "sys.exception()",
        "import sys\nsys = logger\nsys.exception()",
        "import sys\ndef f(sys):\n    sys.exception()",
        "import sys\nfrom logging import logger as sys\nsys.exception()",
        "import sys\ndef sys(): pass\nsys.exception()",
        "import sys\nsys.exception = logger.exception\nsys.exception()",
        "import sys\nsetattr(sys, 'exception', logger.exception)\nsys.exception()",
        "import sys\nfrom other import *\nsys.exception()",
        "import sys\nsys.exception('structural.event')",
        "import sys\nsys.exception(error_type='X')",
        "import sys\nmatch logger:\n    case sys:\n        sys.exception()",
        "import sys\nmatch [logger]:\n    case [*sys]:\n        sys.exception()",
        "import sys\nmatch {'logger': logger}:\n    case {**sys}:\n        sys.exception()",
    )
    for source in sources:
        calls = list(_logging_calls(ast.parse(source)))
        assert any(call.func.attr == "exception" for call in calls), source
