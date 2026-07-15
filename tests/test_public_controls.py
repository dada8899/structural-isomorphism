import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath

import pytest
import yaml

from scripts.check_public_controls import run


ROOT = Path(__file__).resolve().parents[1]

BROWSER_PATH_PATTERN = re.compile(
    r"(?:tests/e2e|web/tests/e2e)/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.py"
)
NODE_PATH_PATTERN = re.compile(
    r"web/frontend/tests/(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.js"
)
MAKE_PATH_PATTERN = re.compile(
    r"(?:tests/e2e|web/tests/e2e|web/frontend/tests)/"
    r"(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|js)"
)
FORBIDDEN_PATH_CHARACTERS = re.compile(r"[#;|&<>$`'\"\\\x00-\x1f\x7f]")

BROWSER_MAKE_SHARDS = [
    (
        "search-ask-analyze-phenomenon",
        "BROWSER_CONTRACT_SEARCH_ASK_ANALYZE_PHENOMENON_TESTS",
    ),
    (
        "discovery-classes-papers",
        "BROWSER_CONTRACT_DISCOVERY_CLASSES_PAPERS_TESTS",
    ),
    (
        "library-auth-reports-favorites",
        "BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS",
    ),
    (
        "secondary-whitespace",
        "BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS",
    ),
]

HARD_STEP_CONDITIONS = {
    (".github/workflows/ci.yml", "browser-beta-surface-contract"): {
        "Run isolated browser surface subgroup": "matrix.pytest_args_isolated != ''",
        "Run JavaScript trust contracts": "matrix.node_tests != ''",
    },
    (".github/workflows/sanity.yml", "sanity"): {"Summary": "always()"},
    (".github/workflows/types-sync.yml", "check"): {
        "Comment on PR with diff": "failure() && github.event_name == 'pull_request'",
    },
    (".github/workflows/beta-perf.yml", "beta-perf-audit"): {
        "Stop local beta server": "always()",
        "Upload beta performance evidence": "always()",
    },
}

HARD_STEP_SHELL_OR_ALLOWLIST = {
    (
        ".github/workflows/beta-perf.yml",
        "beta-perf-audit",
        "Stop local beta server",
    ): ['kill "$(cat /tmp/beta-server.pid)" 2>/dev/null || true'],
}


def _assert_legal_repo_file(token: str, *, root: Path | None = None) -> None:
    repo_root = ROOT if root is None else root
    assert all(part not in {".", ".."} for part in token.split("/")), (
        f"dot segment in contract path: {token}"
    )
    pure_path = PurePosixPath(token)
    assert not pure_path.is_absolute(), f"absolute contract path: {token}"
    assert pure_path.as_posix() == token, f"non-canonical POSIX path: {token}"
    assert ".." not in pure_path.parts, f"parent traversal in contract path: {token}"

    repo_path = repo_root.joinpath(*pure_path.parts)
    assert os.path.lexists(repo_path), f"missing contract path: {token}"
    assert repo_path.is_file(), f"contract path is not a file: {token}"
    assert not repo_path.is_symlink(), f"contract path must not be a symlink: {token}"
    try:
        repo_path.resolve(strict=True).relative_to(repo_root.resolve(strict=True))
    except ValueError as exc:
        raise AssertionError(f"contract path escapes repository: {token}") from exc


def _make_path_list(makefile: str, variable: str) -> list[str]:
    assignment_count = len(
        re.findall(
            rf"^{re.escape(variable)}\s*(?::=|\+=|\?=|=)",
            makefile,
            re.MULTILINE,
        )
    )
    assert assignment_count == 1, (
        f"Makefile must assign variable exactly once: {variable}"
    )
    matches = re.findall(
        rf"^{re.escape(variable)}\s*:=\s*(.*?)(?=^\S|\Z)",
        makefile,
        re.MULTILINE | re.DOTALL,
    )
    assert len(matches) == 1, f"missing canonical Makefile variable: {variable}"
    value = matches[0].replace("\\\n", " ").strip()
    assert not re.search(r"[#;|&<>$`'\"\\]", value)
    paths = value.split()
    assert paths and all(MAKE_PATH_PATTERN.fullmatch(path) for path in paths)
    for path in paths:
        _assert_legal_repo_file(path)
    return paths


def _make_recipe_commands(makefile: str, target: str) -> list[str]:
    matches = re.findall(
        rf"^{re.escape(target)}:[^\n]*\n((?:\t[^\n]*(?:\n|\Z))+)",
        makefile,
        re.MULTILINE,
    )
    headers = re.findall(
        rf"^{re.escape(target)}:[^\n]*(?:\n|\Z)", makefile, re.MULTILINE
    )
    assert len(headers) == 1, f"Makefile must define target exactly once: {target}"
    assert headers == [f"{target}:\n"], f"non-canonical Makefile target: {target}"
    assert len(matches) == 1, f"Makefile must define one recipe: {target}"
    return [line[1:] for line in matches[0].splitlines() if line]


def _ci_job(job_name: str) -> dict[str, object]:
    return _workflow_job(ROOT / ".github/workflows/ci.yml", job_name)


def _workflow_data(workflow_path: Path) -> dict[str, object]:
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict), "CI workflow must be a mapping"
    return workflow


def _workflow_job(workflow_path: Path, job_name: str) -> dict[str, object]:
    workflow = _workflow_data(workflow_path)
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "CI workflow must define jobs"
    job = jobs.get(job_name)
    assert isinstance(job, dict), f"missing CI job: {job_name}"
    return job


def _ci_matrix_rows(job: dict[str, object]) -> list[dict[str, object]]:
    strategy = job.get("strategy")
    assert isinstance(strategy, dict), "hard CI job must define strategy"
    matrix = strategy.get("matrix")
    assert isinstance(matrix, dict), "hard CI job must define a matrix"
    include = matrix.get("include")
    assert isinstance(include, list) and include, "hard CI matrix must define rows"
    assert all(isinstance(row, dict) for row in include)
    return include


def _ci_matrix_paths(
    rows: list[dict[str, object]], field: str, pattern: re.Pattern[str]
) -> list[str]:
    paths: list[str] = []
    for row in rows:
        value = row.get(field)
        assert isinstance(value, str), f"matrix row must define string {field}"
        assert not FORBIDDEN_PATH_CHARACTERS.search(value), (
            f"unsafe character in matrix {field}"
        )
        tokens = value.split()
        assert value == " ".join(tokens), f"non-canonical whitespace in matrix {field}"
        assert all(pattern.fullmatch(token) for token in tokens), (
            f"invalid path token in matrix {field}"
        )
        for token in tokens:
            _assert_legal_repo_file(token)
        paths.extend(tokens)
    return paths


def _named_ci_step(job: dict[str, object], name: str) -> dict[str, object]:
    steps = job.get("steps")
    assert isinstance(steps, list), "hard CI job must define steps"
    matches = [
        step
        for step in steps
        if isinstance(step, dict) and step.get("name") == name
    ]
    assert len(matches) == 1, f"hard CI job must define one {name!r} step"
    return matches[0]


def _assert_hard_job_contract(
    workflow: str,
    job_name: str,
    job: dict[str, object],
    *,
    allowed_job_if: str | None = None,
) -> None:
    if allowed_job_if is None:
        assert "if" not in job, f"hard job condition is forbidden: {job_name}"
    else:
        assert job.get("if") == allowed_job_if
    assert "continue-on-error" not in job, f"hard job may not soft-fail: {job_name}"

    conditions: dict[str, object] = {}
    steps = job.get("steps")
    assert isinstance(steps, list) and steps
    for step in steps:
        assert isinstance(step, dict)
        assert "continue-on-error" not in step
        name = step.get("name")
        run = step.get("run")
        shell_or_lines = (
            [line.strip() for line in run.splitlines() if "||" in line]
            if isinstance(run, str)
            else []
        )
        expected_shell_or = HARD_STEP_SHELL_OR_ALLOWLIST.get(
            (workflow, job_name, name), []
        )
        assert shell_or_lines == expected_shell_or, (
            f"hard job shell fallback is forbidden: {job_name}/{name}"
        )
        if "if" in step:
            assert isinstance(name, str) and name
            assert name not in conditions, f"duplicate conditional step: {name}"
            conditions[name] = step["if"]
    assert conditions == HARD_STEP_CONDITIONS.get((workflow, job_name), {})


def _assert_make_release_closure(makefile: str) -> None:
    expected_assignment_lines = {
        "PY": ["PY ?= $(ROOT)/.venv/bin/python"],
        "OPENAPI_PY": [
            "OPENAPI_PY ?= $(PY)",
            "OPENAPI_PY ?= $(if $(wildcard $(ROOT)/.venv-openapi/bin/python),"
            "$(ROOT)/.venv-openapi/bin/python,$(PY))",
        ],
        "TYPES_PY": ["TYPES_PY ?= $(OPENAPI_PY)"],
        "PYTEST": [
            "PYTEST := PYTHONPATH=$(PACKAGE_PYTHONPATH) $(PY) -m pytest"
        ],
        "BACKEND_PYTEST": [
            "BACKEND_PYTEST := PYTHONPATH=$(ROOT)/web/backend:"
            "$(PACKAGE_PYTHONPATH) $(PY) -m pytest"
        ],
    }
    for variable, expected_lines in expected_assignment_lines.items():
        assignments = [
            line.strip()
            for line in makefile.splitlines()
            if not line.startswith("\t")
            and not line.lstrip().startswith("#")
            and re.search(
                rf"\b{re.escape(variable)}\s*(?::=|\+=|\?=|=)", line
            )
        ]
        definitions = re.findall(
            rf"^(?:(?:override|export|private)\s+)*define\s+"
            rf"{re.escape(variable)}(?:\s*(?::=|\+=|\?=|=))?\s*$",
            makefile,
            re.MULTILINE,
        )
        assert assignments == expected_lines, (
            f"non-canonical release executor: {variable}"
        )
        assert definitions == [], f"define may not replace release executor: {variable}"

    assert not re.search(
        r"^(?!\t).*\b(?:SHELL|\.SHELLFLAGS|MAKEFLAGS|MAKEOVERRIDES|MAKE)\s*"
        r"(?::=|\+=|\?=|=)",
        makefile,
        re.MULTILINE,
    )
    assert not re.search(r"^(?:-?include|sinclude)\b", makefile, re.MULTILINE)
    assert not re.search(r"\$(?:\(|\{)(?:shell|eval|file)\b", makefile)

    phony_lines = re.findall(r"^\.PHONY:\s*(.*)$", makefile, re.MULTILINE)
    assert len(phony_lines) == 1
    phony_targets = set(phony_lines[0].split())
    required_phony = {
        "test-fast", "test-retrieval-contract", "test-product-contracts",
        "test-release-contracts", "test-phase-python-contract",
        "test-frontend-node", "test-browser-contracts",
        "openapi-check", "types-check", "python-syntax-check", "verify-release",
        "llm-scaling-check",
    }
    assert required_phony <= phony_targets

    expected_recipes = {
        "test-fast": ['$(PYTEST) -m "not e2e" -q'],
        "test-retrieval-contract": [
            "$(BACKEND_PYTEST) web/backend/tests/test_retrieval_eval_dataset.py -q"
        ],
        "test-product-contracts": [
            "$(PYTEST) tests/test_public_controls.py tests/test_english_review_tool.py "
            "tests/test_research_claim_gate.py -q"
        ],
        "test-release-contracts": [
            "$(BACKEND_PYTEST) tests --ignore=tests/e2e "
            '-m "not e2e and not slow and not requires_internet and not requires_llm" -q'
        ],
        "test-phase-python-contract": [
            "$(PYTEST) v4/product/d1_phase_detector/tests "
            "v4/product/d1_phase_detector/api/tests -q"
        ],
        "openapi-check": [
            "PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(OPENAPI_PY) "
            "$(ROOT)/scripts/openapi_artifact.py --check"
        ],
        "python-syntax-check": [
            "$(OPENAPI_PY) -I $(ROOT)/scripts/check_python_syntax.py"
        ],
        "llm-scaling-check": [
            "$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/run_validation.py --check",
            "$(LLM_SCALING_PY) $(LLM_SCALING_DIR)/cross_source_alpha_comparison.py --check",
        ],
    }
    for target, recipe in expected_recipes.items():
        assert _make_recipe_commands(makefile, target) == recipe


def _shell_tokens(step: dict[str, object]) -> list[str]:
    run = step.get("run")
    assert isinstance(run, str), "CI command step must define a run string"
    return shlex.split(run.replace("\\\n", " "), comments=False, posix=True)


def _mapping_contains_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(
            _mapping_contains_key(child, key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_mapping_contains_key(child, key) for child in value)
    return False


def _pytest_marker_names(expression: ast.AST) -> set[str]:
    if isinstance(expression, (ast.List, ast.Set, ast.Tuple)):
        return {
            marker
            for item in expression.elts
            for marker in _pytest_marker_names(item)
        }
    if isinstance(expression, ast.Call):
        expression = expression.func
    if (
        isinstance(expression, ast.Attribute)
        and isinstance(expression.value, ast.Attribute)
        and expression.value.attr == "mark"
        and isinstance(expression.value.value, ast.Name)
        and expression.value.value.id == "pytest"
    ):
        return {expression.attr}
    return set()


def _pytestmark_names(statements: list[ast.stmt]) -> set[str]:
    markers: set[str] = set()
    for statement in statements:
        value: ast.AST | None = None
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in statement.targets
        ):
            value = statement.value
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "pytestmark"
        ):
            value = statement.value
        if value is not None:
            markers.update(_pytest_marker_names(value))
    return markers


def _test_marker_sets(tree: ast.Module) -> list[set[str]]:
    module_markers = _pytestmark_names(tree.body)
    tests: list[set[str]] = []
    function_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for statement in tree.body:
        if isinstance(statement, function_types) and statement.name.startswith("test_"):
            markers = set(module_markers)
            for decorator in statement.decorator_list:
                markers.update(_pytest_marker_names(decorator))
            tests.append(markers)
        elif isinstance(statement, ast.ClassDef) and statement.name.startswith("Test"):
            class_markers = module_markers | _pytestmark_names(statement.body)
            for decorator in statement.decorator_list:
                class_markers.update(_pytest_marker_names(decorator))
            for member in statement.body:
                if isinstance(member, function_types) and member.name.startswith("test_"):
                    markers = set(class_markers)
                    for decorator in member.decorator_list:
                        markers.update(_pytest_marker_names(decorator))
                    tests.append(markers)
    return tests


def test_public_control_contract() -> None:
    controls, errors = run()
    assert len(controls) >= 100
    assert errors == []


def test_inventory_has_links_and_buttons() -> None:
    controls, _ = run()
    assert any(item["tag"] == "a" for item in controls)
    assert any(item["tag"] == "button" for item in controls)


def test_product_contract_clean_job_installs_exact_yaml_parser() -> None:
    job = _ci_job("retrieval-eval-contract")
    install_step = _named_ci_step(job, "Install test runner")
    install_tokens = _shell_tokens(install_step)
    assert install_tokens[:4] == ["python", "-m", "pip", "install"]
    assert "PyYAML==6.0.3" in install_tokens
    product_step = _named_ci_step(job, "Validate product and research contracts")
    assert "if" not in product_step and "continue-on-error" not in product_step
    assert _shell_tokens(product_step) == [
        "python",
        "-m",
        "pytest",
        "tests/test_public_controls.py",
        "tests/test_english_review_tool.py",
        "tests/test_research_claim_gate.py",
        "-q",
    ]


def test_phase_auth_browser_job_installs_canonical_runtime_logging() -> None:
    job = _ci_job("browser-product-contract")
    install_step = _named_ci_step(job, "Install browser test dependencies")
    assert "if" not in install_step and "continue-on-error" not in install_step
    assert _shell_tokens(install_step) == [
        "python", "-m", "pip", "install",
        "pytest==9.0.3", "playwright==1.59.0", "pytest-playwright==0.7.2",
        "fastapi==0.115.14",
        "pydantic==2.6.1", "starlette==0.46.2",
        "uvicorn[standard]==0.27.1", "PyJWT==2.12.1", "slowapi==0.1.9",
        "structlog==25.5.0", "python", "-m", "playwright", "install",
        "--with-deps", "chromium",
    ]
    requirements = (
        ROOT / "web/backend/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert "structlog==25.5.0" in requirements


def test_backend_release_job_installs_root_package_fail_closed() -> None:
    job = _ci_job("backend")
    install = _named_ci_step(job, "Install dependencies")
    assert _shell_tokens(install) == [
        "python", "-m", "pip", "install", "--upgrade", "pip",
        "python", "-m", "pip", "install", "-e", ".[dev]",
        "python", "-m", "pip", "install", "pyyaml",
    ]
    assert "||" not in install["run"]


def test_hard_job_contract_rejects_shell_install_fallback() -> None:
    job = {
        "steps": [
            {
                "name": "Install",
                "run": "python -m pip install -e . || python -m pip install pytest",
            }
        ]
    }
    with pytest.raises(AssertionError, match="shell fallback"):
        _assert_hard_job_contract("test.yml", "required", job)


def test_browser_product_job_uses_exact_existing_nodeids() -> None:
    job = _ci_job("browser-product-contract")
    step = _named_ci_step(job, "Verify the explicit workbench decision journey")
    test_path = "tests/e2e/test_full_public_surface.py"
    names = {
        node.name
        for node in ast.parse((ROOT / test_path).read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    selected = [
        "test_beta_workbench_requires_fingerprint_and_explicit_candidate",
        "test_beta_header_exposes_one_dynamic_primary_account_entry",
        "test_beta_header_never_picks_one_of_two_accounts",
    ]
    assert set(selected) <= names
    assert _shell_tokens(step) == [
        "pytest",
        *(f"{test_path}::{name}" for name in selected),
        "-m",
        "e2e and not requires_internet",
        "-v",
    ]
    assert "-k" not in _shell_tokens(step)


def test_release_gate_runs_project_site_and_complete_phase_contracts() -> None:
    docs_job = _ci_job("site-docs-contract")
    docs_step = _named_ci_step(
        docs_job, "Verify every project-site document is published and navigable"
    )
    assert _shell_tokens(docs_step) == [
        "python", "-I", "scripts/check_site_docs.py"
    ]
    assert "if" not in docs_step and "continue-on-error" not in docs_step

    phase_job = _ci_job("phase-python-contract")
    setup_python = [
        step
        for step in phase_job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/setup-python@v5"
    ]
    assert setup_python == [
        {"uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}}
    ]
    install = _named_ci_step(
        phase_job, "Install exact Phase runtime and test dependencies"
    )
    assert _shell_tokens(install) == [
        "python", "-m", "pip", "install",
        "-r", "v4/product/d1_phase_detector/api/requirements.txt",
        "pytest==9.0.3", "httpx==0.27.2",
    ]
    run = _named_ci_step(phase_job, "Run both complete Phase Python test trees")
    assert _shell_tokens(run) == [
        "make", "PY=python", "test-phase-python-contract"
    ]
    for step in (install, run):
        assert "if" not in step and "continue-on-error" not in step


def test_release_dependency_sets_share_one_satisfiable_httpx_contract() -> None:
    requirements = (
        ROOT / "web/backend/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    backend_pins = [line for line in requirements if line.startswith("httpx==")]
    assert len(backend_pins) == 1
    version = backend_pins[0].removeprefix("httpx==")

    for package in ("guarded-llm", "cross-judge", "reject-aware-critic"):
        project = tomllib.loads(
            (ROOT / f"packages/{package}/pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        constraints = [
            dependency.removeprefix("httpx")
            for dependency in project["dependencies"]
            if dependency.startswith("httpx")
        ]
        assert len(constraints) == 1
        minimum_match = re.fullmatch(r">=([0-9]+(?:\.[0-9]+)*)", constraints[0])
        assert minimum_match, f"unsupported httpx constraint syntax: {constraints[0]}"
        current = tuple(int(part) for part in version.split("."))
        minimum = tuple(int(part) for part in minimum_match.group(1).split("."))
        assert current >= minimum, (
            f"backend httpx=={version} conflicts with {package}{constraints[0]}"
        )


def test_types_artifact_is_reproducible_in_make_and_sanity() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    generator = (ROOT / "scripts/gen_ts_types.sh").read_text(encoding="utf-8")
    checker = (ROOT / "scripts/check_ts_types.sh").read_text(encoding="utf-8")
    assert 'OUT="${OUT:-web/phase-detector/lib/api-types.ts}"' in generator
    assert 'OUT="$TMP_OUTPUT" bash scripts/gen_ts_types.sh' in checker
    assert 'cmp -s "$COMMITTED" "$TMP_OUTPUT"' in checker
    assert _make_recipe_commands(makefile, "types-check") == [
        "PY=$(TYPES_PY) bash scripts/check_ts_types.sh"
    ]

    types_job = _workflow_job(ROOT / ".github/workflows/types-sync.yml", "check")
    regenerate = _named_ci_step(types_job, "Regenerate api-types.ts")
    assert "if" not in regenerate and "continue-on-error" not in regenerate
    assert _shell_tokens(regenerate) == ["bash", "scripts/gen_ts_types.sh"]
    diff_step = _named_ci_step(types_job, "Diff committed vs regenerated")
    assert diff_step.get("run") == (
        "if git diff --quiet -- web/phase-detector/lib/api-types.ts; then\n"
        '  echo "drift=false" >> "$GITHUB_OUTPUT"\n'
        '  echo "OK — api-types.ts is in sync with web/backend/schemas.py"\n'
        "else\n"
        '  echo "drift=true" >> "$GITHUB_OUTPUT"\n'
        '  echo "::error::api-types.ts is stale — run \'bash scripts/gen_ts_types.sh\' and commit"\n'
        "  git diff -- web/phase-detector/lib/api-types.ts | head -200\n"
        "  exit 1\n"
        "fi\n"
    )

    sanity_job = _workflow_job(ROOT / ".github/workflows/sanity.yml", "sanity")
    install = _named_ci_step(sanity_job, "Install locked TypeScript generator")
    assert _shell_tokens(install) == [
        "python", "-m", "pip", "install", "-r",
        "scripts/requirements-types.txt", "npm", "ci", "--ignore-scripts",
        "--no-audit", "--no-fund", "--prefix", "scripts/types-generator",
    ]
    check = _named_ci_step(sanity_job, "Leg 3 — reproducible API TypeScript artifact")
    assert _shell_tokens(check) == [
        "make", "PY=python", "types-check",
    ]


def test_sanity_installs_and_runs_root_contract_runtime_fail_closed() -> None:
    workflow_path = ROOT / ".github/workflows/sanity.yml"
    workflow = _workflow_data(workflow_path)
    job = _workflow_job(workflow_path, "sanity")
    install = _named_ci_step(job, "Install root release contract dependencies")
    llm_scaling = _named_ci_step(
        job, "Check LLM scaling artifacts in locked generator environment"
    )
    syntax = _named_ci_step(job, "Leg 3 — Python 3.11 syntax closure")
    contracts = _named_ci_step(job, "Leg 3 — offline root release contracts")

    assert _shell_tokens(install) == [
        "python", "-m", "pip", "install", "-e", ".[dev]",
        "python", "-m", "pip", "install", "playwright==1.59.0",
    ]
    assert _shell_tokens(llm_scaling) == [
        "python", "-m", "venv", "/tmp/structural-llm-scaling-generator",
        "/tmp/structural-llm-scaling-generator/bin/pip", "install", "-r",
        "v4/validation/llm-scaling/requirements-generator.txt",
        "make", "LLM_SCALING_PY=/tmp/structural-llm-scaling-generator/bin/python",
        "llm-scaling-check",
    ]
    assert _shell_tokens(syntax) == [
        "python", "-I", "scripts/check_python_syntax.py"
    ]
    assert all(
        key not in syntax
        for key in ("env", "working-directory", "shell", "continue-on-error", "if")
    )
    assert all(key not in workflow for key in ("env", "defaults"))
    assert all(key not in job for key in ("env", "defaults"))
    assert _shell_tokens(contracts) == [
        "make", "PY=python", "test-release-contracts"
    ]

    positions = {
        step.get("name"): index
        for index, step in enumerate(job["steps"])
        if isinstance(step, dict)
    }
    assert positions["Install root release contract dependencies"] < positions[
        "Check LLM scaling artifacts in locked generator environment"
    ] < positions["Leg 3 — Python 3.11 syntax closure"] < positions[
        "Leg 3 — offline root release contracts"
    ]


def test_readmes_document_llm_scaling_env_before_release_verification() -> None:
    for relative_path in ("README.md", "README-zh.md"):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        assert source.count("make llm-scaling-env") == 1
        assert source.count("make verify-release") == 1
        assert source.index("make llm-scaling-env") < source.index(
            "make verify-release"
        )


def test_sanity_installs_and_runs_reject_aware_critic_explicitly() -> None:
    job = _workflow_job(ROOT / ".github/workflows/sanity.yml", "sanity")
    install = _named_ci_step(job, "Install local packages (editable + dev extras)")
    assert _shell_tokens(install) == [
        "pip", "install", "-e", "packages/soc-pipeline[dev]",
        "pip", "install", "-e", "packages/guarded-llm[dev]",
        "pip", "install", "-e", "packages/cross-judge[dev]",
        "pip", "install", "-e", "packages/reject-aware-critic[dev]",
    ]

    reject_aware = _named_ci_step(
        job, "Leg 4 — packages/reject-aware-critic tests"
    )
    assert reject_aware["working-directory"] == "packages/reject-aware-critic"
    assert _shell_tokens(reject_aware) == [
        "python", "-m", "pytest", "-ra", "-q", "--tb=short",
    ]
    assert "if" not in reject_aware
    assert "continue-on-error" not in reject_aware


def test_release_gate_manifest_binds_internal_and_external_checks() -> None:
    manifest_path = ROOT / ".github/release-gate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_needs = [
        "retrieval-eval-contract",
        "site-docs-contract",
        "phase-python-contract",
        "browser-product-contract",
        "browser-beta-surface-contract",
        "backend",
        "packages",
        "frontend",
    ]
    assert manifest == {
        "schema_version": "release-gate-v1",
        "ci_aggregator": {
            "workflow": ".github/workflows/ci.yml",
            "job": "release-gate-summary",
            "needs": expected_needs,
        },
        "branch_protection_required_checks": [
            {
                "workflow": ".github/workflows/ci.yml",
                "job": "release-gate-summary",
                "context": "release-gate",
            },
            {
                "workflow": ".github/workflows/sanity.yml",
                "job": "sanity",
                "context": "sanity",
            },
            {
                "workflow": ".github/workflows/types-sync.yml",
                "job": "check",
                "context": "check",
            },
            {
                "workflow": ".github/workflows/beta-perf.yml",
                "job": "beta-perf-audit",
                "context": "beta-perf-audit",
            },
        ],
        "external_boundary": (
            "GitHub branch protection must require every listed check; "
            "repository YAML cannot create cross-workflow needs edges."
        ),
    }

    aggregator = _ci_job("release-gate-summary")
    assert aggregator.get("if") == "always()"
    assert aggregator.get("needs") == expected_needs
    assert not _mapping_contains_key(aggregator, "continue-on-error")
    setup_python = [
        step
        for step in aggregator["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/setup-python@v5"
    ]
    assert setup_python == [
        {"uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}}
    ]
    summary_step = _named_ci_step(aggregator, "Require every CI dependency to succeed")
    assert summary_step.get("env") == {"REQUIRED_RESULTS": "${{ toJSON(needs) }}"}
    summary_run = summary_step.get("run")
    assert summary_run == (
        "python - <<'PY'\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "manifest = json.loads(\n"
        '    Path(".github/release-gate-manifest.json").read_text(encoding="utf-8")\n'
        ")\n"
        'expected = set(manifest["ci_aggregator"]["needs"])\n'
        'results = json.loads(os.environ["REQUIRED_RESULTS"])\n'
        "if set(results) != expected:\n"
        '    raise SystemExit(f"release-gate dependency drift: {sorted(results)}")\n'
        "failed = {\n"
        '    name: result.get("result")\n'
        "    for name, result in results.items()\n"
        '    if result.get("result") != "success"\n'
        "}\n"
        "if failed:\n"
        '    raise SystemExit(f"release-gate dependency failure: {failed}")\n'
        'print("all CI-internal release dependencies succeeded")\n'
        "PY\n"
    )

    for dependency in expected_needs:
        _assert_hard_job_contract(
            ".github/workflows/ci.yml", dependency, _ci_job(dependency)
        )

    for required in manifest["branch_protection_required_checks"]:
        workflow_path = ROOT / required["workflow"]
        required_job = _workflow_job(workflow_path, required["job"])
        allowed_job_if = (
            "always()" if required["job"] == "release-gate-summary" else None
        )
        _assert_hard_job_contract(
            required["workflow"],
            required["job"],
            required_job,
            allowed_job_if=allowed_job_if,
        )
        assert required["context"] == required_job.get("name", required["job"])
        workflow = _workflow_data(workflow_path)
        triggers = workflow.get("on", workflow.get(True))
        assert isinstance(triggers, dict)
        for event in ("pull_request", "push"):
            config = triggers.get(event)
            assert config == {"branches": ["main"]}, (
                f"required workflow {workflow_path} must run on every {event}"
            )

    perf_job = _workflow_job(
        ROOT / ".github/workflows/beta-perf.yml", "beta-perf-audit"
    )
    assert "if" not in perf_job
    assert not _mapping_contains_key(perf_job, "continue-on-error")
    perf_conditions = {
        step.get("name"): step["if"]
        for step in perf_job["steps"]
        if isinstance(step, dict) and "if" in step
    }
    assert perf_conditions == {
        "Stop local beta server": "always()",
        "Upload beta performance evidence": "always()",
    }
    perf_units = _named_ci_step(perf_job, "Run deterministic unit contracts")
    assert _shell_tokens(perf_units) == [
        "python",
        "-m",
        "pytest",
        "tests/test_perf_audit.py",
        "tests/test_beta_perf_audit.py",
        "-q",
    ]
    perf_audit = _named_ci_step(
        perf_job, "Audit beta surfaces against the existing product budget"
    )
    assert "if" not in perf_audit
    assert _shell_tokens(perf_audit) == [
        "python",
        "scripts/beta_perf_audit.py",
        "--base",
        "http://127.0.0.1:4173",
        "--runs",
        "3",
        "--budget",
        "perf-budget.json",
        "--out",
        "/tmp/beta-perf-audit.json",
    ]

    decisions = (ROOT / "docs/ci-matrix-decisions.md").read_text(encoding="utf-8")
    assert ".github/release-gate-manifest.json" in decisions
    assert "GitHub Actions cannot express `needs` across workflow files" in decisions
    assert "main-branch protection must require every" in decisions


def test_nightly_backend_matches_supported_matrix_and_installs_fail_closed() -> None:
    job = _workflow_job(ROOT / ".github/workflows/nightly.yml", "backend-full")
    assert job["strategy"] == {
        "fail-fast": False,
        "matrix": {
            "python-version": ["3.10", "3.11", "3.12"],
            "os": ["ubuntu-latest", "macos-latest"],
            "exclude": [{"os": "macos-latest", "python-version": "3.10"}],
        },
    }
    checkout = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/checkout@v5"
    ]
    assert checkout == [{"uses": "actions/checkout@v5", "with": {"lfs": True}}]

    install = _named_ci_step(job, "Install")
    assert install.get("run") == (
        "python -m pip install --upgrade pip\n"
        'python -m pip install -e ".[dev]"\n'
        "python -m pip install \\\n"
        "  -e packages/soc-pipeline \\\n"
        "  -e packages/guarded-llm \\\n"
        "  -e packages/cross-judge \\\n"
        "  -e packages/reject-aware-critic\n"
    )
    assert "||" not in install["run"]
    assert "continue-on-error" not in install
    run = _named_ci_step(job, "Run sanity + integration (incl. slow)")
    assert _shell_tokens(run) == [
        "pytest", "v4/tests", "-v", "-m", "not requires_llm"
    ]


def test_nightly_e2e_reconstructs_the_full_browser_runtime() -> None:
    job = _workflow_job(ROOT / ".github/workflows/nightly.yml", "e2e-full")
    pnpm = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == "pnpm/action-setup@v4"
    ]
    assert pnpm == [{"uses": "pnpm/action-setup@v4", "with": {"version": 10}}]
    node = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/setup-node@v4"
    ]
    assert node == [{
        "uses": "actions/setup-node@v4",
        "with": {
            "node-version": "20",
            "cache": "pnpm",
            "cache-dependency-path": "web/phase-detector/pnpm-lock.yaml",
        },
    }]

    install = _named_ci_step(job, "Install")
    install_tokens = _shell_tokens(install)
    assert install_tokens == [
        "python", "-m", "pip", "install", "--upgrade", "pip",
        "python", "-m", "pip", "install",
        "pytest==9.0.3", "playwright==1.59.0", "pytest-playwright==0.7.2",
        "httpx==0.27.2", "fastapi==0.115.14", "pydantic==2.6.1",
        "starlette==0.46.2", "uvicorn[standard]==0.27.1", "PyJWT==2.12.1",
        "slowapi==0.1.9", "structlog==25.5.0", "Pillow==12.3.0",
        "python", "-m", "playwright", "install", "--with-deps", "chromium",
    ]
    assert "||" not in install["run"]
    phase_install = _named_ci_step(job, "Install Phase browser runtime")
    assert phase_install == {
        "name": "Install Phase browser runtime",
        "working-directory": "web/phase-detector",
        "run": "pnpm install --frozen-lockfile",
    }
    phase_runtime = _named_ci_step(job, "Require the installed Next and axe runtimes")
    assert phase_runtime == {
        "name": "Require the installed Next and axe runtimes",
        "working-directory": "web/phase-detector",
        "run": (
            "test -x node_modules/.bin/next\n"
            "test -s node_modules/axe-core/axe.min.js\n"
        ),
    }
    positions = {
        step.get("name"): index
        for index, step in enumerate(job["steps"])
        if isinstance(step, dict) and isinstance(step.get("name"), str)
    }
    assert positions["Install"] < positions["Install Phase browser runtime"]
    assert positions["Require the installed Next and axe runtimes"] < positions[
        "Run e2e (all markers except requires_llm w/o key)"
    ]


def test_manual_load_defaults_to_capped_beta_and_requires_stress_consent() -> None:
    workflow = _workflow_data(ROOT / ".github/workflows/load-smoke.yml")
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict)
    dispatch = triggers.get("workflow_dispatch")
    assert isinstance(dispatch, dict)
    inputs = dispatch.get("inputs")
    assert isinstance(inputs, dict)
    assert inputs["target"] == {
        "description": "Target environment",
        "required": True,
        "type": "choice",
        "default": "beta",
        "options": ["beta", "custom"],
    }
    assert inputs["unsafe_load_confirmation"] == {
        "description": 'Type "yes" to authorize stress_ramp or an uncapped custom load',
        "required": False,
        "type": "string",
        "default": "",
    }

    job = _workflow_job(ROOT / ".github/workflows/load-smoke.yml", "load-smoke")
    assert job["concurrency"] == {
        "group": "structural-production-beta-load",
        "cancel-in-progress": False,
    }
    setup_python = [
        step
        for step in job["steps"]
        if isinstance(step, dict) and step.get("uses") == "actions/setup-python@v5"
    ]
    assert setup_python == [
        {"uses": "actions/setup-python@v5", "with": {"python-version": "3.11"}}
    ]
    resolve = _named_ci_step(job, "Resolve BASE_URL")
    assert resolve.get("env") == {
        "TARGET": "${{ inputs.target }}",
        "CUSTOM_URL": "${{ inputs.custom_url }}",
    }
    resolve_run = resolve.get("run")
    assert isinstance(resolve_run, str)
    assert "local)" not in resolve_run and "localhost" not in resolve_run
    assert 'BETA_HOST = "beta.structural.bytedance.city"' in resolve_run
    assert 'resolved = f"https://{BETA_HOST}"' in resolve_run
    assert "urlsplit(raw)" in resolve_run
    assert 'canonical_host == BETA_HOST' in resolve_run
    assert "parsed.username is not None or parsed.password is not None" in resolve_run
    assert 'parsed.path not in {"", "/"} or parsed.query or parsed.fragment' in resolve_run
    assert '"%" in parsed.netloc' in resolve_run
    assert 'raw_host.encode("idna").decode("ascii").rstrip(".")' in resolve_run
    assert "label.fullmatch(part)" in resolve_run
    assert "select the beta target so production safety caps apply" in resolve_run
    assert "custom_url must not contain whitespace or control characters" in resolve_run
    assert "${{ inputs.custom_url }}" not in resolve_run
    assert "${{ inputs.target }}" not in resolve_run
    assert 'fail("unsupported target")' in resolve_run
    positions = {
        step.get("name", step.get("uses")): index
        for index, step in enumerate(job["steps"])
        if isinstance(step, dict)
    }
    assert positions["actions/setup-python@v5"] < positions["Resolve BASE_URL"]

    scenario = _named_ci_step(job, "Run scenario(s)")
    assert scenario.get("env") == {
        "BASE_URL": "${{ steps.target.outputs.url }}",
        "TARGET": "${{ inputs.target }}",
        "SCENARIO": "${{ inputs.scenario }}",
        "VUS_OVERRIDE": "${{ inputs.vus_override }}",
        "DURATION_OVERRIDE": "${{ inputs.duration_override }}",
        "UNSAFE_LOAD_CONFIRMATION": "${{ inputs.unsafe_load_confirmation }}",
    }
    scenario_run = scenario.get("run")
    assert isinstance(scenario_run, str)
    assert scenario_run.startswith("set -euo pipefail\n")
    for fragment in (
        'SAFE_CAP=0',
        'if [ "$SCENARIO" != "stress_ramp" ]; then',
        'SAFE_CAP=1',
        'VUS_OVERRIDE=1\n',
        'DURATION_OVERRIDE=20s\n',
        'local args=(--max-redirects 0)',
        'args+=(--vus "$VUS_OVERRIDE")',
        'args+=(--duration "$DURATION_OVERRIDE")',
        'BASE_URL="$BASE_URL" k6 run "${args[@]}" "$script"',
        '[ "$SCENARIO" = "stress_ramp" ] && [ "$UNSAFE_LOAD_CONFIRMATION" != "yes" ]',
        '[ "$TARGET" = "beta" ] || [ "$UNSAFE_LOAD_CONFIRMATION" != "yes" ]',
        'export I_KNOW_WHAT_I_AM_DOING="$UNSAFE_LOAD_CONFIRMATION"',
        '*) echo "ERROR: unsupported scenario"; exit 1 ;;',
    ):
        assert fragment in scenario_run
    assert "I_KNOW_WHAT_I_AM_DOING=yes" not in scenario_run
    assert "BASE_URL=$BASE_URL" not in scenario_run
    assert "threshold breach or error" not in scenario_run
    assert "k6 run" in scenario_run
    assert "|| true" not in scenario_run and "|| echo" not in scenario_run
    assert not re.search(r"k6\s+run[^\n]*\|\|", scenario_run)


@pytest.mark.parametrize(
    "custom_url",
    [
        "https://BETA.structural.bytedance.city",
        "https://beta.structural.bytedance.city:443",
        "https://beta.structural.bytedance.city/.",
        "https://beta.structural.bytedance.city?probe=1",
        "https://beta.structural.bytedance.city./api",
        "https://beta.structural.bytedance.city．/",
        "https://beta.structural.bytedance.city。/",
        "https://beta.structural.bytedance.city｡/",
        "https://beta.structural.bytedance.city．．/",
        "https://user@beta.structural.bytedance.city",
        "https://%62eta.structural.bytedance.city",
        "https://example.invalid/#fragment",
        "https://example.invalid/base?token=secret",
        "https://example.invalid/private-capability",
        "https://example.invalid/has space",
        "javascript://example.invalid",
    ],
)
def test_manual_load_custom_url_parser_rejects_aliases_and_ambiguity(
    tmp_path: Path, custom_url: str,
) -> None:
    job = _workflow_job(ROOT / ".github/workflows/load-smoke.yml", "load-smoke")
    script = _named_ci_step(job, "Resolve BASE_URL")["run"]
    script_path = tmp_path / "resolve.sh"
    script_path.write_text(script, encoding="utf-8")
    output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        PATH=f"{Path(sys.executable).parent}:{environment['PATH']}",
        TARGET="custom",
        CUSTOM_URL=custom_url,
        GITHUB_OUTPUT=str(output),
    )
    completed = subprocess.run(
        ["/bin/bash", str(script_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode != 0, custom_url
    assert not output.exists() or output.read_text(encoding="utf-8") == ""


def test_manual_load_custom_url_parser_emits_one_canonical_url(tmp_path: Path) -> None:
    job = _workflow_job(ROOT / ".github/workflows/load-smoke.yml", "load-smoke")
    script = _named_ci_step(job, "Resolve BASE_URL")["run"]
    script_path = tmp_path / "resolve.sh"
    script_path.write_text(script, encoding="utf-8")
    output = tmp_path / "github-output"
    environment = os.environ.copy()
    environment.update(
        PATH=f"{Path(sys.executable).parent}:{environment['PATH']}",
        TARGET="custom",
        CUSTOM_URL="HTTPS://EXAMPLE.invalid:8443",
        GITHUB_OUTPUT=str(output),
    )
    completed = subprocess.run(
        ["/bin/bash", str(script_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert output.read_text(encoding="utf-8") == (
        "url=https://example.invalid:8443\n"
    )


def _run_load_scenario(
    tmp_path: Path,
    *,
    target: str,
    scenario: str,
    confirmation: str = "",
    vus: str = "",
    duration: str = "",
) -> tuple[subprocess.CompletedProcess[str], str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    job = _workflow_job(ROOT / ".github/workflows/load-smoke.yml", "load-smoke")
    script = _named_ci_step(job, "Run scenario(s)")["run"]
    script_path = tmp_path / "scenario.sh"
    script_path.write_text(script, encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    log = tmp_path / "k6.log"
    fake_k6 = binary_dir / "k6"
    fake_k6.write_text(
        "#!/bin/bash\n"
        "printf 'safety=%s args=%s\\n' \"${I_KNOW_WHAT_I_AM_DOING-}\" \"$*\" >> \"$K6_LOG\"\n",
        encoding="utf-8",
    )
    fake_k6.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        PATH=f"{binary_dir}:{environment['PATH']}",
        K6_LOG=str(log),
        BASE_URL=(
            "https://beta.structural.bytedance.city"
            if target == "beta"
            else "https://example.invalid"
        ),
        TARGET=target,
        SCENARIO=scenario,
        VUS_OVERRIDE=vus,
        DURATION_OVERRIDE=duration,
        UNSAFE_LOAD_CONFIRMATION=confirmation,
    )
    completed = subprocess.run(
        ["/bin/bash", str(script_path)],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return completed, log.read_text(encoding="utf-8") if log.exists() else ""


def test_manual_load_dynamic_caps_and_stress_authority(tmp_path: Path) -> None:
    beta, beta_log = _run_load_scenario(
        tmp_path / "beta", target="beta", scenario="phases_smoke"
    )
    assert beta.returncode == 0, beta.stderr
    assert (
        "args=run --max-redirects 0 --vus 1 --duration 20s "
        "tests/load/phases_smoke.js"
    ) in beta_log

    over, _ = _run_load_scenario(
        tmp_path / "over", target="beta", scenario="phases_smoke", vus="2"
    )
    assert over.returncode != 0

    custom_stress, _ = _run_load_scenario(
        tmp_path / "custom-no", target="custom", scenario="stress_ramp"
    )
    assert custom_stress.returncode != 0

    custom_safe, custom_safe_log = _run_load_scenario(
        tmp_path / "custom-safe", target="custom", scenario="mixed_realistic"
    )
    assert custom_safe.returncode == 0, custom_safe.stderr
    assert "--max-redirects 0 --vus 1 --duration 20s" in custom_safe_log

    custom_uncapped, custom_uncapped_log = _run_load_scenario(
        tmp_path / "custom-uncapped",
        target="custom",
        scenario="mixed_realistic",
        confirmation="yes",
    )
    assert custom_uncapped.returncode == 0, custom_uncapped.stderr
    assert "args=run --max-redirects 0 tests/load/mixed_realistic.js" in custom_uncapped_log

    allowed, allowed_log = _run_load_scenario(
        tmp_path / "custom-yes",
        target="custom",
        scenario="stress_ramp",
        confirmation="yes",
    )
    assert allowed.returncode == 0, allowed.stderr
    assert "safety=yes args=run --max-redirects 0 tests/load/stress_ramp.js" in allowed_log


def test_production_load_jobs_serialize_and_nightly_fails_closed(tmp_path: Path) -> None:
    manual = _workflow_job(ROOT / ".github/workflows/load-smoke.yml", "load-smoke")
    nightly_path = ROOT / ".github/workflows/nightly.yml"
    nightly = _workflow_job(nightly_path, "load-smoke-1vu")
    expected_concurrency = {
        "group": "structural-production-beta-load",
        "cancel-in-progress": False,
    }
    assert manual["concurrency"] == expected_concurrency
    assert nightly["concurrency"] == expected_concurrency

    inspect = _named_ci_step(nightly, "Inspect scripts (parse-check)")["run"]
    assert inspect.startswith("set -euo pipefail\n")
    assert "tests/load/*.js" not in inspect and "|| continue" not in inspect
    inspect_path = tmp_path / "inspect.sh"
    inspect_path.write_text(inspect, encoding="utf-8")
    completed = subprocess.run(
        ["/bin/bash", str(inspect_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode != 0

    run = _named_ci_step(nightly, "Run 1-VU smoke against beta")["run"]
    assert "test -f tests/load/phases_smoke.js" in run
    assert "--vus 1 --duration 20s" in run
    assert "if [ -f" not in run
    upload = _named_ci_step(nightly, "Upload results")
    assert upload["with"]["if-no-files-found"] == "error"
    assert _workflow_job(nightly_path, "summary")["timeout-minutes"] == 5
    assert _ci_job("release-gate-summary")["timeout-minutes"] == 5
    nightly_summary = _workflow_job(nightly_path, "summary")
    notification = _named_ci_step(
        nightly_summary, "Post issue comment (non-success only)"
    )
    assert notification["if"] == (
        "needs.backend-full.result != 'success' || "
        "needs.soc-pipeline-full.result != 'success' || "
        "needs.e2e-full.result != 'success' || "
        "needs.load-smoke-1vu.result != 'success'"
    )
    assert "non-success results" in notification["with"]["script"]


def test_every_github_actions_job_has_a_bounded_timeout() -> None:
    missing: list[str] = []
    invalid: list[str] = []
    for workflow_path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        workflow = _workflow_data(workflow_path)
        jobs = workflow.get("jobs")
        assert isinstance(jobs, dict) and jobs, workflow_path
        for job_name, job in jobs.items():
            assert isinstance(job, dict), f"{workflow_path}:{job_name}"
            timeout = job.get("timeout-minutes")
            label = f"{workflow_path.relative_to(ROOT)}:{job_name}"
            if timeout is None:
                missing.append(label)
            elif not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 90:
                invalid.append(f"{label}={timeout!r}")
    assert missing == []
    assert invalid == []


def test_workflow_dispatch_inputs_never_enter_shell_source() -> None:
    violations: list[str] = []
    for workflow_path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        workflow = _workflow_data(workflow_path)
        for job_name, job in workflow["jobs"].items():
            for step in job.get("steps", []):
                if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                    continue
                run = step["run"]
                if "${{ inputs." in run or "${{ github.event.inputs" in run:
                    violations.append(
                        f"{workflow_path.relative_to(ROOT)}:{job_name}:"
                        f"{step.get('name', '<unnamed>')}"
                    )
    assert violations == []


def test_privileged_dispatch_workflows_validate_inputs_and_use_env() -> None:
    newsletter_path = ROOT / ".github/workflows/newsletter.yml"
    newsletter = _workflow_job(newsletter_path, "generate")
    week = _named_ci_step(newsletter, "Compute ISO week")
    assert week["env"] == {"WEEK_INPUT": "${{ inputs.week }}"}
    assert '^[0-9]{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$' in week["run"]
    generate = _named_ci_step(newsletter, "Generate newsletter")
    assert generate["env"]["SPOTLIGHT_INPUT"] == "${{ inputs.spotlight }}"
    assert "all_spotlight_slugs" in generate["run"]
    assert 'GENERATOR_ARGS+=(--spotlight "$SPOTLIGHT_INPUT")' in generate["run"]
    assert "SPOTLIGHT_FLAG" not in generate["run"]

    release_path = ROOT / ".github/workflows/release-packages.yml"
    release_workflow = _workflow_data(release_path)
    release_inputs = release_workflow.get("on", release_workflow.get(True))[
        "workflow_dispatch"
    ]["inputs"]
    assert release_inputs["dry_run"] == {
        "description": "If true: build + twine check only, no upload",
        "required": False,
        "default": True,
        "type": "boolean",
    }
    resolve = _named_ci_step(
        _workflow_job(release_path, "release"),
        "Resolve target package + version from tag (or input)",
    )
    assert resolve["env"] == {
        "EVENT_NAME": "${{ github.event_name }}",
        "INPUT_PACKAGE": "${{ inputs.package }}",
        "INPUT_DRY_RUN": "${{ inputs.dry_run }}",
    }
    assert "guarded-llm|soc-pipeline|cross-judge|reject-aware-critic" in resolve["run"]
    assert "true|false" in resolve["run"]

    publish_path = ROOT / ".github/workflows/publish-pypi.yml"
    publish_workflow = _workflow_data(publish_path)
    publish_inputs = publish_workflow.get("on", publish_workflow.get(True))[
        "workflow_dispatch"
    ]["inputs"]
    assert publish_inputs["dry_run"] == {
        "description": "If true, build but do not upload (twine check only)",
        "required": False,
        "default": False,
        "type": "boolean",
    }
    publish_job = _workflow_job(publish_path, "build-and-publish")
    publish_summary = _named_ci_step(publish_job, "Summary")
    assert publish_summary["env"]["DRY_RUN"] == "${{ inputs.dry_run }}"
    assert "${{ inputs." not in publish_summary["run"]


def test_privileged_dispatch_payloads_cannot_execute_in_bash(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "injected"
    payload = f"$(touch {marker})"

    def run_step(
        workflow: str,
        job: str,
        step: str,
        environment_overrides: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        workflow_path = ROOT / workflow
        script = _named_ci_step(_workflow_job(workflow_path, job), step)["run"]
        script_path = tmp_path / f"{job}-{step.replace(' ', '-')}.sh"
        script_path.write_text(script, encoding="utf-8")
        environment = os.environ.copy()
        environment.update(
            PATH=f"{Path(sys.executable).parent}:{environment['PATH']}",
            **environment_overrides,
        )
        return subprocess.run(
            ["/bin/bash", str(script_path)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    week = run_step(
        ".github/workflows/newsletter.yml",
        "generate",
        "Compute ISO week",
        {"WEEK_INPUT": payload, "GITHUB_OUTPUT": str(tmp_path / "week-output")},
    )
    assert week.returncode != 0
    assert not marker.exists()

    spotlight = run_step(
        ".github/workflows/newsletter.yml",
        "generate",
        "Generate newsletter",
        {
            "WEEK": "2026-W19",
            "WEEKNUM": "19",
            "SPOTLIGHT_INPUT": payload,
            "GITHUB_OUTPUT": str(tmp_path / "newsletter-output"),
        },
    )
    assert spotlight.returncode != 0
    assert not marker.exists()

    release_resolve = run_step(
        ".github/workflows/release-packages.yml",
        "release",
        "Resolve target package + version from tag (or input)",
        {
            "EVENT_NAME": "workflow_dispatch",
            "INPUT_PACKAGE": payload,
            "INPUT_DRY_RUN": "true",
            "GITHUB_OUTPUT": str(tmp_path / "release-output"),
        },
    )
    assert release_resolve.returncode != 0
    assert not marker.exists()

    pypi_summary = run_step(
        ".github/workflows/publish-pypi.yml",
        "build-and-publish",
        "Summary",
        {
            "PACKAGE": "guarded-llm",
            "REF_NAME": "manual",
            "DRY_RUN": payload,
            "HAS_PYPI_TOKEN": "false",
            "GITHUB_STEP_SUMMARY": str(tmp_path / "pypi-summary"),
        },
    )
    assert pypi_summary.returncode == 0, pypi_summary.stderr
    assert not marker.exists()

    release_summary = run_step(
        ".github/workflows/release-packages.yml",
        "release",
        "Summary",
        {
            "EVENT_NAME": "push",
            "REF_NAME": payload,
            "PKG": "guarded-llm",
            "VER": "0.1.0",
            "DRY_RUN": "false",
            "HAS_PYPI_TOKEN": "false",
            "GITHUB_STEP_SUMMARY": str(tmp_path / "release-summary"),
        },
    )
    assert release_summary.returncode == 0, release_summary.stderr
    assert not marker.exists()


def test_make_release_targets_form_a_fail_closed_recipe_closure() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    _assert_make_release_closure(makefile)

    mutations = [
        makefile.replace(
            "PYTEST := PYTHONPATH=$(PACKAGE_PYTHONPATH) $(PY) -m pytest",
            "PYTEST := true",
            1,
        ),
        makefile.replace(
            "BACKEND_PYTEST := PYTHONPATH=$(ROOT)/web/backend:"
            "$(PACKAGE_PYTHONPATH) $(PY) -m pytest",
            "BACKEND_PYTEST := true",
            1,
        ),
        makefile.replace(
            "$(BACKEND_PYTEST) tests --ignore=tests/e2e "
            '-m "not e2e and not slow and not requires_internet and not requires_llm" -q',
            "@true",
            1,
        ),
        f"{makefile}\nPYTEST = true\n",
        f"{makefile}\noverride BACKEND_PYTEST += true\n",
        f"{makefile}\nexport PYTEST = true\n",
        f"{makefile}\nprivate BACKEND_PYTEST := true\n",
        f"{makefile}\noverride export PYTEST ?= true\n",
        f"{makefile}\ndefine BACKEND_PYTEST\ntrue\nendef\n",
        f"{makefile}\nverify-release: PYTEST = true\n",
        f"{makefile}\nSHELL := /bin/true\n",
        f"{makefile}\ninclude optional-release-overrides.mk\n",
        f"{makefile}\n$(eval PYTEST := true)\n",
    ]
    assert all(mutated != makefile for mutated in mutations)
    for mutated in mutations:
        with pytest.raises(AssertionError):
            _assert_make_release_closure(mutated)


def test_coverage_package_source_and_test_matrix_is_closed() -> None:
    coverage_config = (ROOT / ".coveragerc").read_text(encoding="utf-8")
    source_lines = re.findall(r"^source\s*=\s*(.+)$", coverage_config, re.MULTILINE)
    assert len(source_lines) == 1
    configured_sources = {
        value.strip() for value in source_lines[0].split(",") if value.strip()
    }
    package_sources = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "packages").glob("*/src")
        if path.is_dir()
    }
    assert package_sources
    assert package_sources <= configured_sources

    workflow = (ROOT / ".github/workflows/coverage.yml").read_text(
        encoding="utf-8"
    )
    for source in package_sources:
        package = PurePosixPath(source).parent.name
        assert f"packages/{package}/tests/" in workflow
    assert "for source_dir in packages/*/src; do" in workflow
    assert '--include="$source_dir/*"' in workflow
    assert "--fail-under=1" in workflow


def test_backtest_parquet_extra_is_single_source_and_used_by_sanity() -> None:
    setup_source = (ROOT / "setup.py").read_text(encoding="utf-8")
    assert setup_source.count('"pyarrow==24.0.0"') == 1
    assert 'BACKTEST_REQUIREMENTS = ["pyarrow==24.0.0"]' in setup_source
    assert '"backtest": BACKTEST_REQUIREMENTS' in setup_source
    assert '"dev": ["scikit-learn", "pytest", "black", "ruff", *BACKTEST_REQUIREMENTS]' in setup_source
    assert 'python_requires=">=3.10"' in setup_source
    assert "Programming Language :: Python :: 3.8" not in setup_source
    assert "Programming Language :: Python :: 3.9" not in setup_source
    assert "Programming Language :: Python :: 3.13" in setup_source

    sanity = (ROOT / ".github/workflows/sanity.yml").read_text(encoding="utf-8")
    assert 'python -m pip install -e ".[dev]"' in sanity
    assert "pyarrow==24.0.0" not in sanity


def test_makefile_release_authority_is_independently_frozen() -> None:
    assert hashlib.sha256((ROOT / "Makefile").read_bytes()).hexdigest() == (
        "4b4dfb0608153681fd409d28c3bfd1fea5fecc93aefc550dc6585266d1ffac95"
    )


def test_python_syntax_release_authority_is_independently_frozen() -> None:
    assert hashlib.sha256(
        (ROOT / "scripts/check_python_syntax.py").read_bytes()
    ).hexdigest() == (
        "904a8bf6ddbe9f614d67a3848da4330de5f612be643aeb5f92a4d4dc9444e2e7"
    )


def test_verify_release_dry_run_expands_real_test_and_build_commands() -> None:
    environment = os.environ.copy()
    for variable in (
        "MAKEFLAGS",
        "MAKEOVERRIDES",
        "PYTEST",
        "BACKEND_PYTEST",
        "OPENAPI_PY",
        "TYPES_PY",
    ):
        environment.pop(variable, None)
    completed = subprocess.run(
        ["make", "-n", "--no-print-directory", "PY=python", "verify-release"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    assert output.count("python -m pytest") == 14
    assert "scripts/check_python_syntax.py" in output
    assert "scripts/openapi_artifact.py --check" in output
    assert "PY=python bash scripts/check_ts_types.sh" in output
    assert 'node "$test_file"' in output
    assert "pnpm lint && pnpm build" in output
    assert re.search(r"(?:^|\s)(?:true|false)(?:\s|$)", output) is None


def test_required_browser_workflow_covers_nonenglish_product_surfaces() -> None:
    job = _ci_job("browser-beta-surface-contract")
    assert "if" not in job
    rows = _ci_matrix_rows(job)
    expected_shards = [
        "search-ask-analyze-phenomenon",
        "discovery-classes-papers",
        "library-auth-reports-favorites",
        "secondary-whitespace",
    ]
    shards = [row.get("shard") for row in rows]
    assert shards == expected_shards

    node_tests = _ci_matrix_paths(
        rows, "node_tests", NODE_PATH_PATTERN
    )
    browser_tests = _ci_matrix_paths(
        rows, "pytest_args", BROWSER_PATH_PATTERN
    )
    browser_tests.extend(
        _ci_matrix_paths(
            rows, "pytest_args_isolated", BROWSER_PATH_PATTERN
        )
    )
    executable_contracts = set(node_tests) | set(browser_tests)
    for contract in (
        "tests/e2e/test_search_private_navigation.py",
        "web/frontend/tests/test_analyticsSensitiveRoutes.js",
        "web/frontend/tests/test_askTrust.js",
        "web/frontend/tests/test_analyzeTrust.js",
        "web/frontend/tests/test_buildAnalyzeUrl.js",
        "web/frontend/tests/test_historyPrivacy.js",
        "web/frontend/tests/test_reportTrust.js",
        "tests/e2e/test_phenomenon_evidence_mobile.py",
        "tests/e2e/test_discovery_validation_plan.py",
        "tests/e2e/test_classes_language_mobile.py",
        "tests/e2e/test_papers_public_runtime.py",
        "tests/e2e/test_full_public_surface.py",
        "tests/e2e/test_unified_research_library.py",
        "web/tests/e2e/test_secondary_tools_candidate_journeys.py",
        "web/tests/e2e/test_whitespace.py",
        "web/tests/e2e/test_thank_you_copy.py",
        "web/tests/e2e/test_report_share.py",
        "web/tests/e2e/test_cross_domain_report_claim.py",
    ):
        assert contract in executable_contracts

    install_step = _named_ci_step(job, "Install browser contract dependencies")
    browser_step = _named_ci_step(job, "Run browser surface shard")
    isolated_step = _named_ci_step(job, "Run isolated browser surface subgroup")
    node_step = _named_ci_step(job, "Run JavaScript trust contracts")
    conditional_steps = {
        step.get("name"): step["if"]
        for step in job["steps"]
        if isinstance(step, dict) and "if" in step
    }
    assert conditional_steps == {
        "Run isolated browser surface subgroup": "matrix.pytest_args_isolated != ''",
        "Run JavaScript trust contracts": "matrix.node_tests != ''",
    }
    install_tokens = _shell_tokens(install_step)
    assert install_tokens == [
        "python", "-m", "pip", "install",
        "pytest==9.0.3", "playwright==1.59.0", "pytest-playwright==0.7.2",
        "httpx==0.27.2",
        "fastapi==0.115.14", "pydantic==2.6.1", "starlette==0.46.2",
        "uvicorn[standard]==0.27.1", "PyJWT==2.12.1", "slowapi==0.1.9",
        "structlog==25.5.0", "python", "-m", "playwright", "install",
        "--with-deps", "chromium",
    ]
    browser_tokens = _shell_tokens(browser_step)
    assert "if" not in browser_step
    assert browser_tokens == [
        "pytest", "${{", "matrix.pytest_args", "}}", "-m",
        "e2e and not requires_internet", "-v",
    ]
    assert isolated_step.get("if") == "matrix.pytest_args_isolated != ''"
    isolated_tokens = _shell_tokens(isolated_step)
    assert isolated_tokens == [
        "pytest", "${{", "matrix.pytest_args_isolated", "}}", "-m",
        "e2e and not requires_internet", "-v",
    ]
    assert node_step.get("if") == "matrix.node_tests != ''"
    assert node_step.get("shell") == "bash"
    node_tokens = _shell_tokens(node_step)
    assert node_tokens == [
        "set", "-euo", "pipefail", "for", "test_file", "in", "${{",
        "matrix.node_tests", "}};", "do", "node", "$test_file", "done",
    ]
    assert not _mapping_contains_key(job, "continue-on-error")


@pytest.mark.parametrize(
    "unsafe_character",
    [
        "#",
        ";",
        "|",
        "&",
        "<",
        ">",
        "$",
        "`",
        "'",
        '"',
        "\\",
        "\x00",
        "\x1f",
        "\x7f",
        "\n",
        "\t",
    ],
)
def test_ci_matrix_path_parser_rejects_shell_and_control_characters(
    unsafe_character: str,
) -> None:
    rows = [{"pytest_args": f"tests/e2e/test_safe.py{unsafe_character}"}]
    with pytest.raises(AssertionError):
        _ci_matrix_paths(rows, "pytest_args", BROWSER_PATH_PATTERN)


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "/tests/e2e/test_safe.py",
        "../tests/e2e/test_safe.py",
        "tests/e2e/../test_safe.py",
        "tests/e2e/./test_full_public_surface.py",
        "tests/e2e/test_safe.py.extra",
        "tests/e2e/test_safe.js",
        "tests/e2e/test_safe.py  tests/e2e/test_other.py",
        "tests/e2e/test_safe.py ",
    ],
)
def test_ci_matrix_path_parser_requires_canonical_relative_files(
    unsafe_path: str,
) -> None:
    with pytest.raises(AssertionError):
        _ci_matrix_paths(
            [{"pytest_args": unsafe_path}], "pytest_args", BROWSER_PATH_PATTERN
        )


def test_make_recipe_parser_rejects_duplicate_target_definitions() -> None:
    makefile = "release:\n\t@true\nrelease:\n\t@true\n"
    with pytest.raises(AssertionError):
        _make_recipe_commands(makefile, "release")


def test_make_recipe_parser_rejects_double_colon_target() -> None:
    with pytest.raises(AssertionError):
        _make_recipe_commands("release::\n\t@true\n", "release")


def test_make_path_parser_rejects_a_second_assignment() -> None:
    makefile = (
        "FILES := tests/e2e/test_full_public_surface.py\n"
        "FILES += tests/e2e/test_search_private_navigation.py\n"
    )
    with pytest.raises(AssertionError):
        _make_path_list(makefile, "FILES")


@pytest.mark.parametrize(
    "suffix",
    [" || true", " # hidden bypass", "; true", "\necho bypass"],
)
def test_shell_parser_exposes_appended_commands_and_comments(suffix: str) -> None:
    canonical_run = 'pytest tests/e2e/test_full_public_surface.py -m "e2e" -v'
    canonical_tokens = _shell_tokens({"run": canonical_run})
    assert _shell_tokens({"run": canonical_run + suffix}) != canonical_tokens


def test_contract_path_parser_rejects_a_file_symlink(tmp_path: Path) -> None:
    test_root = tmp_path / "repo"
    contract_dir = test_root / "tests/e2e"
    contract_dir.mkdir(parents=True)
    target = contract_dir / "real.py"
    target.write_text("pass\n", encoding="utf-8")
    (contract_dir / "linked.py").symlink_to(target)

    with pytest.raises(AssertionError, match="symlink"):
        _assert_legal_repo_file("tests/e2e/linked.py", root=test_root)


def test_frontend_node_gate_cannot_silently_skip_a_contract() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    rows = _ci_matrix_rows(_ci_job("browser-beta-surface-contract"))

    disk_tests = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "web/frontend/tests").glob("*.js")
    }
    make_tests = _make_path_list(makefile, "FRONTEND_NODE_TESTS")
    ci_tests = _ci_matrix_paths(
        rows, "node_tests", NODE_PATH_PATTERN
    )

    assert len(make_tests) == len(set(make_tests)), "duplicate Make Node contract"
    assert len(ci_tests) == len(set(ci_tests)), "duplicate CI Node contract"
    assert set(make_tests) == disk_tests
    assert set(ci_tests) == disk_tests
    assert _make_recipe_commands(makefile, "test-frontend-node") == [
        '@set -eu; for test_file in $(FRONTEND_NODE_TESTS); do node "$$test_file"; done'
    ]


def test_hard_browser_gate_has_one_make_and_ci_contract_list() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    rows = _ci_matrix_rows(_ci_job("browser-beta-surface-contract"))
    assert [row.get("shard") for row in rows] == [
        shard for shard, _ in BROWSER_MAKE_SHARDS
    ]

    make_tests: list[str] = []
    ci_tests: list[str] = []
    for row, (shard, make_variable) in zip(rows, BROWSER_MAKE_SHARDS, strict=True):
        assert row.get("shard") == shard
        make_shard = _make_path_list(makefile, make_variable)
        ci_primary = _ci_matrix_paths(
            [row], "pytest_args", BROWSER_PATH_PATTERN
        )
        ci_isolated = _ci_matrix_paths(
            [row], "pytest_args_isolated", BROWSER_PATH_PATTERN
        )
        root_tests = [path for path in make_shard if path.startswith("tests/e2e/")]
        web_tests = [path for path in make_shard if path.startswith("web/tests/e2e/")]
        if root_tests and web_tests:
            assert ci_primary == root_tests, f"mixed-root primary process: {shard}"
            assert ci_isolated == web_tests, f"missing web isolation: {shard}"
        else:
            assert ci_primary == make_shard, f"unexpected primary split: {shard}"
            assert ci_isolated == [], f"unnecessary isolated process: {shard}"
        ci_shard = ci_primary + ci_isolated
        assert len(make_shard) == len(set(make_shard)), (
            f"duplicate Make browser contract in {shard}"
        )
        assert len(ci_shard) == len(set(ci_shard)), (
            f"duplicate CI browser contract in {shard}"
        )
        assert make_shard == ci_shard, f"browser shard drift: {shard}"
        make_tests.extend(make_shard)
        ci_tests.extend(ci_shard)

    assert len(make_tests) == len(set(make_tests)), "cross-shard Make duplicate"
    assert len(ci_tests) == len(set(ci_tests)), "cross-shard CI duplicate"
    assert make_tests == ci_tests
    assert "web/tests/e2e/test_thank_you_copy.py" in make_tests
    marker = '-m "e2e and not requires_internet" -v'
    assert _make_recipe_commands(makefile, "test-browser-contracts") == [
        f"$(PYTEST) $({BROWSER_MAKE_SHARDS[0][1]}) {marker}",
        f"$(PYTEST) $({BROWSER_MAKE_SHARDS[1][1]}) {marker}",
        "$(PYTEST) $(filter tests/e2e/%,$("
        f"{BROWSER_MAKE_SHARDS[2][1]})) {marker}",
        "$(PYTEST) $(filter web/tests/e2e/%,$("
        f"{BROWSER_MAKE_SHARDS[2][1]})) {marker}",
        f"$(PYTEST) $({BROWSER_MAKE_SHARDS[3][1]}) {marker}",
        "$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v",
    ]

    phase_tests = _make_path_list(makefile, "PHASE_REAL_BROWSER_CONTRACT_TESTS")
    assert phase_tests == [
        "web/tests/e2e/test_phase_auth_real.py",
        "web/tests/e2e/test_cookie_consent.py",
    ]
    phase_job = _ci_job("browser-product-contract")
    assert "if" not in phase_job
    assert not any(
        "if" in step
        for step in phase_job["steps"]
        if isinstance(step, dict)
    )
    phase_step = _named_ci_step(
        phase_job, "Verify real Next auth, failure states, mobile controls and axe"
    )
    assert "if" not in phase_step
    assert _shell_tokens(phase_step) == ["pytest", phase_tests[0], "-v"]
    consent_step = _named_ci_step(
        phase_job, "Verify consent-gated official analytics transport"
    )
    assert "if" not in consent_step
    assert _shell_tokens(consent_step) == ["pytest", phase_tests[1], "-v"]

    phase_positions = {
        step.get("name"): index
        for index, step in enumerate(phase_job["steps"])
        if isinstance(step, dict)
    }
    assert phase_positions["Install Phase dependencies"] < phase_positions[
        "Verify consent-gated official analytics transport"
    ]

    assert _make_recipe_commands(makefile, "verify-release") == [
        "$(MAKE) python-syntax-check",
        "$(MAKE) openapi-check",
        "$(MAKE) types-check",
        "$(MAKE) llm-scaling-check",
        "$(MAKE) test-fast",
        "cd web/backend && $(BACKEND_PYTEST) -q",
        "cd packages/guarded-llm && $(PYTEST) tests -q",
        "cd packages/cross-judge && $(PYTEST) tests -q",
        "cd packages/reject-aware-critic && $(PYTEST) tests -q",
        'cd packages/soc-pipeline && $(PYTEST) tests -q -m "not slow"',
        "$(MAKE) test-retrieval-contract",
        "$(MAKE) test-release-contracts",
        "$(MAKE) test-frontend-node",
        "$(MAKE) test-browser-contracts",
        "cd web/phase-detector && pnpm lint && pnpm build",
    ]

    marker_misses: list[str] = []
    for relative_path in make_tests:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        marker_sets = _test_marker_sets(ast.parse(source, filename=relative_path))
        if not any(
            "e2e" in markers and "requires_internet" not in markers
            for markers in marker_sets
        ):
            marker_misses.append(relative_path)
    assert marker_misses == [], (
        "browser contracts without a selectable offline e2e test: "
        f"{marker_misses}"
    )


def test_every_beta_html_document_is_complete() -> None:
    """Fail closed if a mechanical cache/copy rewrite truncates a page."""
    failures: list[str] = []
    for page in sorted((ROOT / "web/frontend").glob("*.html")):
        content = page.read_text(encoding="utf-8")
        if len(content.encode("utf-8")) < 1_000:
            failures.append(f"{page.name}: fewer than 1000 bytes")
        if not content.rstrip().casefold().endswith("</html>"):
            failures.append(f"{page.name}: missing closing </html>")
    assert failures == []


def test_no_beta_page_loads_the_same_script_twice() -> None:
    failures: list[str] = []
    pattern = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
    for page in sorted((ROOT / "web/frontend").glob("*.html")):
        sources = pattern.findall(page.read_text(encoding="utf-8"))
        duplicates = sorted({source for source in sources if sources.count(source) > 1})
        if duplicates:
            failures.append(f"{page.name}: {duplicates}")
    assert failures == []


def test_optional_analytics_never_loads_a_remote_tracker_script() -> None:
    """The consent boundary owns transport; no remote script may run code."""
    failures: list[str] = []
    pattern = re.compile(
        r"<script\b(?P<attrs>[^>]*)\bsrc=[\"']"
        r"https://plausible\.bytedance\.city/[^\"']*[\"'][^>]*>",
        re.I,
    )
    for page in sorted((ROOT / "web/frontend").glob("*.html")):
        for match in pattern.finditer(page.read_text(encoding="utf-8")):
            failures.append(f"{page.name}: remote analytics script is forbidden")
    assert failures == []


def test_every_static_id_is_unique_within_its_page() -> None:
    failures: list[str] = []
    pattern = re.compile(r"\bid=[\"']([^\"']+)[\"']", re.I)
    for page in sorted((ROOT / "web/frontend").glob("*.html")):
        identifiers = pattern.findall(page.read_text(encoding="utf-8"))
        duplicates = sorted(
            {identifier for identifier in identifiers if identifiers.count(identifier) > 1}
        )
        if duplicates:
            failures.append(f"{page.name}: {duplicates}")
    assert failures == []


def test_public_copy_links_directly_to_the_phase_subproduct() -> None:
    sources = [
        ROOT / "web/frontend/about.html",
        ROOT / "web/frontend/assets/data/i18n/content.json",
    ]
    copy = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    assert "https://beta.structural.bytedance.city/phase/" not in copy
    assert "https://phase.bytedance.city/" in copy


def test_beta_native_auth_routes_are_public_contract_routes() -> None:
    checker = (ROOT / "scripts/check_public_controls.py").read_text(encoding="utf-8")
    assert '"/auth/login"' in checker
    assert '"/auth/verify"' in checker


def test_workbench_requires_fingerprint_and_candidate_confirmation() -> None:
    ask = (ROOT / "web/frontend/assets/js/ask.js").read_text(encoding="utf-8")
    analyze = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    handoff = (
        ROOT / "web/frontend/assets/js/utils/buildAnalyzeUrl.js"
    ).read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/index.html").read_text(encoding="utf-8")
    analyze_page = (ROOT / "web/frontend/analyze.html").read_text(encoding="utf-8")
    assert "openFingerprintReview(q)" in ask
    assert "structural_pending_fingerprint" not in ask
    assert "structural_pending_fingerprint" not in analyze
    assert "structural_analyze_handoff:" in handoff
    assert "sessionStorage.removeItem(PREFIX + key); // consume before parsing" in handoff
    assert "var fingerprint = normalizeFingerprint(opts.fingerprint, query);" in handoff
    assert "if (opts.fingerprint != null && !fingerprint) return '';" in handoff
    assert "fingerprint: fingerprint" in handoff
    assert "Math.random" not in handoff
    assert "sessionStorage.getItem(PREFIX + key) !== null" in handoff
    assert "p.set('q'" not in handoff
    assert "payload.fingerprint = confirmedFingerprint" in analyze
    assert "fetch('/api/analyze/stream'" in analyze
    assert "new EventSource" not in analyze
    assert "Opening SSE" not in analyze
    assert '<meta name="referrer" content="no-referrer">' in analyze_page
    assert "item._selectedCandidateId" in ask
    assert "系统不会替你默认选择 Top 1" in ask
    assert "结构匹配线索" in ask
    assert "反证 / 尚缺证据" in ask
    assert "适用边界" in ask
    assert "检索分" in ask
    assert "相似度 " not in ask
    assert 'id="ask-fingerprint-confirm"' in page
    assert "buildFingerprintDraft" in ask
    assert "structural_fingerprint_draft" in ask
    assert "系统只根据你写下的内容生成草案" in page
    assert "用户原文" in page and "待确认" in page and "未知" in page
    assert 'aria-describedby="ask-fingerprint-help"' in page
    assert "persist=0" in ask
    assert 'data-role="save-report-choice"' in ask
    assert "未勾选时不会在服务器保存报告" in ask
    assert "persistFlag === '1'" in analyze
    assert "persistFlag !== '0'" not in analyze


def test_sensitive_streams_are_post_body_only() -> None:
    analyze_api = (ROOT / "web/backend/api/analyze.py").read_text(encoding="utf-8")
    lint_api = (ROOT / "web/backend/api/struct_lint.py").read_text(encoding="utf-8")
    analyze_js = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    lint_js = (ROOT / "web/frontend/assets/js/lint.js").read_text(encoding="utf-8")

    assert re.search(r'@router\.post\(\s*["\']/analyze/stream["\']', analyze_api)
    assert '@router.get("/analyze/stream", include_in_schema=False)' in analyze_api
    assert '@router.post("/struct-lint/stream")' in lint_api
    assert '@router.get("/struct-lint/stream", include_in_schema=False)' in lint_api
    assert "sensitive_get_retired" in analyze_api and "sensitive_get_retired" in lint_api
    assert "ConfigDict(extra=\"forbid\", strict=True)" in analyze_api
    assert "ConfigDict(extra=\"forbid\", strict=True)" in lint_api

    assert "fetch('/api/analyze/stream'" in analyze_js
    assert "fetch('/api/struct-lint/stream'" in lint_js
    assert "method: 'POST'" in analyze_js and "method: 'POST'" in lint_js
    assert "new EventSource" not in analyze_js
    assert "new EventSource" not in lint_js
    assert "/api/analyze/stream?" not in analyze_js
    assert "/api/struct-lint/stream?" not in lint_js


def test_analyze_protocol_spec_matches_the_atomic_v2_contract() -> None:
    spec = (ROOT / "docs/api/analyze-stream-spec.md").read_text(encoding="utf-8")
    for required in (
        "deep-analysis-report-v2",
        "report_validated",
        "section × 9 (canonical order, unique keys)",
        "Web Crypto recomputes the canonical report SHA-256",
        "Query mode never reads or writes the durable generation cache",
        "Only the corresponding-phenomenon description is source-derived",
        "Candidate methods and borrowable insights are model proposals",
        "closed-enum server-controlled",
        "No `report_validated`, `section`, `persisted` or `done` event may follow",
        "115-second",
    ):
        assert required in spec
    for stale in (
        "q_<md5",
        "raw LLM stream chunks",
        "done` follows with a fallback report",
        "honours `X-Forwarded-Host`",
        "render incrementally as `section` events arrive",
    ):
        assert stale not in spec


def test_private_handoff_payload_is_never_logged_or_annotated_for_analytics() -> None:
    handoff = (
        ROOT / "web/frontend/assets/js/utils/buildAnalyzeUrl.js"
    ).read_text(encoding="utf-8")
    ask = (ROOT / "web/frontend/assets/js/ask.js").read_text(encoding="utf-8")
    analyze = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    combined = "\n".join((handoff, ask, analyze))

    assert "query_hash" not in ask
    assert "Opening SSE" not in analyze
    assert "console.log" not in handoff
    assert not re.search(r"(?:plausible|track)\s*\([^\n]*(?:handoff|source_query)", combined)
    assert not re.search(r"console\.(?:log|info|warn|error)\([^\n]*handoff", combined)


def test_report_list_is_an_action_workbench() -> None:
    script = (ROOT / "web/frontend/assets/js/my-reports.js").read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/reports.html").read_text(encoding="utf-8")
    for bucket in ("today", "week", "waiting", "completed"):
        assert f"id: '{bucket}'" in script
    assert "outcome !== 'too_early'" in script
    assert "reportBucket(item)" in script
    assert "按今天、本周、等待推进和已完成分组" in page


def test_phase_build_is_network_independent() -> None:
    layout = (ROOT / "web/phase-detector/app/layout.tsx").read_text(encoding="utf-8")
    assert 'from "next/font/local"' in layout
    assert "next/font/google" not in layout


def test_phase_auth_navigation_is_wired_and_fail_closed() -> None:
    top_nav = (ROOT / "web/phase-detector/components/TopNav.tsx").read_text(encoding="utf-8")
    auth_nav = (ROOT / "web/phase-detector/components/AuthNav.tsx").read_text(encoding="utf-8")
    production_env = (ROOT / "web/phase-detector/.env.production").read_text(encoding="utf-8")
    assert 'import AuthNav from "./AuthNav"' in top_nav
    assert '<AuthNav variant="compact" />' in top_nav
    assert '<AuthNav variant="drawer" />' in top_nav
    assert 'process.env.NEXT_PUBLIC_AUTH_ENABLED !== "true"' in auth_nav
    assert 'href="/auth/login"' in auth_nav
    assert "注册 / 登录" in auth_nav
    assert "min-h-11" in auth_nav
    assert "NEXT_PUBLIC_AUTH_ENABLED=true" in production_env


def test_beta_auth_entry_is_user_visible_and_canonical() -> None:
    chrome = (ROOT / "web/frontend/assets/js/site-chrome.js").read_text(encoding="utf-8")
    backend = (ROOT / "web/backend/main.py").read_text(encoding="utf-8")
    assert '/auth/login?next=%2Freports' in chrome
    assert "登录以同步" in chrome
    assert "我的研究" in chrome
    assert "fetch('/api/auth/me'" in chrome
    assert "credential_conflict" in chrome and "确认账户" in chrome
    assert "site-header__account-cta" in chrome
    assert "site-menu-lang-toggle" in chrome
    assert "async def unified_auth_login" in backend


def test_primary_navigation_starts_at_the_real_workbench() -> None:
    chrome = (ROOT / "web/frontend/assets/js/site-chrome.js").read_text(encoding="utf-8")
    assert "{ href: '/', key: 'nav.start_here', label: '开始研究' }" in chrome
    assert "{ href: '/analyze', key: 'nav.analyze'" not in chrome


def test_my_research_unifies_assets_and_account_rights() -> None:
    page = (ROOT / "web/frontend/reports.html").read_text(encoding="utf-8")
    script = (ROOT / "web/frontend/assets/js/my-reports.js").read_text(encoding="utf-8")
    for identifier in ("research-reports", "research-favorites", "research-account"):
        assert f'id="{identifier}"' in page
    assert "我的研究" in page
    assert "用户结果回填不等于独立机制验证" in page
    assert "fetch('/api/auth/me'" in script
    assert "fetch('/api/me/export'" in script
    assert "fetch('/api/me/delete'" in script
    assert "fetch('/api/auth/logout'" in script
    assert "用户记录有效" in script
    assert ">已验证<" not in script
    assert "[401, 404, 409]" in script
    assert "credentialLocked" in script
    assert "lockCredentialAssets" in script
    assert '<script src="/assets/js/i18n.js?v=20260714n2"></script>' in page
    assert "loadAccount().then(function (identity)" in script
    assert "loadAuthenticatedAssetsAtomically" in script
    assert "Promise.all([" in script


def test_unified_research_bookmarks_are_local_first_and_server_confirmed() -> None:
    analyze = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    reports = (ROOT / "web/frontend/assets/js/my-reports.js").read_text(encoding="utf-8")
    page = (ROOT / "web/frontend/reports.html").read_text(encoding="utf-8")
    privacy = (ROOT / "web/frontend/privacy.html").read_text(encoding="utf-8")

    assert "'/api/favorites/bookmarks'" in analyze
    assert "已保存在本机，登录后同步" in analyze
    assert "已保存在本机，账户同步稍后重试" in analyze
    assert "账户移除未完成，收藏仍然保留" in analyze
    assert "server_bookmark_id" in analyze
    assert "restoreLocalFavorite" in analyze

    assert "normalizeAccountBookmark" in reports
    assert "safeAnalysisHref" in reports
    assert "window.buildAnalyzeUrl" in reports
    assert "searchParams.get('handoff')" in reports
    assert "syncLocalFavorites" in reports
    assert "confirmed_bookmark_ids" in reports
    assert "data-remove-bookmark" in reports
    assert "credentialLocked" in reports
    assert "href: bookmark.href" not in reports
    assert "我的研究收藏库" in page
    assert "min-height:44px" in page
    assert "结构分析收藏" in privacy


def test_docs_header_exposes_canonical_account_entry() -> None:
    homepage = (ROOT / "site/index.html").read_text(encoding="utf-8")
    assert 'class="account-link"' in homepage
    assert 'href="https://beta.structural.bytedance.city/auth/login"' in homepage
    assert ">注册 / 登录</a>" in homepage


def test_public_positioning_matches_frozen_demo_and_null_backtest() -> None:
    phase_paths = [
        "web/phase-detector/app/page.tsx",
        "web/phase-detector/app/zh/page.tsx",
        "web/phase-detector/app/thank-you/page.tsx",
        "web/phase-detector/components/LandingHero.tsx",
        "web/phase-detector/components/LandingHeroZh.tsx",
        "web/phase-detector/components/HowItWorksSteps.tsx",
        "web/phase-detector/components/TrustSignalsRow.tsx",
        "web/phase-detector/components/ExploreCardsGrid.tsx",
        "web/phase-detector/components/WaitlistForm.tsx",
    ]
    phase = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in phase_paths)
    forbidden_phase_claims = (
        "You judge the alpha",
        "alpha 是否成立",
        "你判断 alpha",
        "before they're priced",
        "市场定价前看见翻转",
        "Recent flips",
        "本周状态变化",
        "每周精选",
        "每周日推送",
        "本周新走到",
        "本周回到",
    )
    assert not any(claim in phase for claim in forbidden_phase_claims)
    assert "frozen 597-ticker demo snapshot" in phase.lower()
    assert "NULL" in phase

    seo = (ROOT / "web/phase-detector/lib/seo.ts").read_text(encoding="utf-8")
    nav = (ROOT / "web/phase-detector/components/TopNav.tsx").read_text(encoding="utf-8")
    pricing = (ROOT / "web/phase-detector/app/pricing/page.tsx").read_text(encoding="utf-8")
    assert '"@type": "Offer"' not in seo
    assert "priceCurrency" not in seo
    assert '{ href: "/companies", label: "公司表" }' in nav
    assert '{ href: "/pricing", label: "定价" }' not in nav
    assert "PricingTable" not in pricing


def test_beta_entry_copy_uses_current_counts_timing_and_claim_boundary() -> None:
    paths = [
        "web/frontend/index.html",
        "web/frontend/learn.html",
        "web/frontend/assets/js/home.js",
        "web/frontend/assets/data/i18n/content.json",
    ]
    copy = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in paths)
    for stale in ("100 家", "100家", "1-2 分钟", "1–2 分钟", "完全相同", "exactly the same"):
        assert stale not in copy
    assert "597 个 demo ticker" in copy
    assert "2–3 分钟" in copy
    assert "机制是否一致仍需验证" in copy


def test_phase_privacy_discloses_account_session_storage() -> None:
    privacy = (ROOT / "web/phase-detector/app/privacy/page.tsx").read_text(encoding="utf-8")
    for disclosure in ("账户与登录", "登录链接的哈希", "phase_session", "HttpOnly", "SameSite=Lax"):
        assert disclosure in privacy
    assert "localStorage（不是 cookie）" not in privacy


def test_phase_logout_and_bulk_favorite_failures_are_not_false_successes() -> None:
    auth = (ROOT / "web/phase-detector/lib/auth-client.ts").read_text(encoding="utf-8")
    nav = (ROOT / "web/phase-detector/components/AuthNav.tsx").read_text(encoding="utf-8")
    favorites = (ROOT / "web/phase-detector/app/me/favorites/page.tsx").read_text(encoding="utf-8")
    me_page = (ROOT / "web/phase-detector/app/me/page.tsx").read_text(encoding="utf-8")
    assert "if (!response.ok)" in auth
    assert "setUser(null)" in auth
    assert "退出失败，请重试" in nav
    assert "你仍处于登录状态" in me_page
    assert "failed.add(t)" in favorites
    assert "已保留在列表中" in favorites
    assert "已同步到邮箱账户，可在其他设备登录后查看" in favorites
    assert "当前未登录，收藏仅保存在本设备；登录后会自动合并" in favorites
