import ast
import copy
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
        "Install complete backend runtime and verify imports": "matrix.shard == 'library-auth-reports-favorites'",
        "Run actual Main public surface contract": "matrix.pytest_args_main != ''",
        "Run isolated browser surface subgroup": "matrix.pytest_args_isolated != ''",
        "Run JavaScript trust contracts": "matrix.node_tests != ''",
    },
    (".github/workflows/sanity.yml", "sanity"): {"Summary": "always()"},
    (".github/workflows/types-sync.yml", "check"): {
        "Comment on PR with diff": "failure() && github.event_name == 'pull_request'",
    },
    (".github/workflows/beta-perf.yml", "beta-perf-audit"): {
        'NOT_GATE one marked Linux diagnostic pair': (
            '${{ always() && !cancelled()\n'
            "    && github.repository == 'dada8899/structural-isomorphism'\n"
            "    && github.event_name == 'pull_request'\n"
            "    && github.event.action == 'synchronize'\n"
            '    && github.event.pull_request.number == 253\n'
            '    && github.event.pull_request.head.repo.full_name == github.repository\n'
            '    && github.event.pull_request.base.repo.full_name == github.repository\n'
            "    && github.event.pull_request.head.ref == 'bootstrap/structure-ci-20261016'\n"
            "    && github.run_attempt == '1' }}"
        ),
        'Upload NOT_GATE Linux diagnostic evidence': (
            '${{ always() && !cancelled()\n'
            "    && github.repository == 'dada8899/structural-isomorphism'\n"
            "    && github.event_name == 'pull_request'\n"
            "    && github.event.action == 'synchronize'\n"
            '    && github.event.pull_request.number == 253\n'
            '    && github.event.pull_request.head.repo.full_name == github.repository\n'
            '    && github.event.pull_request.base.repo.full_name == github.repository\n'
            "    && github.event.pull_request.head.ref == 'bootstrap/structure-ci-20261016'\n"
            "    && github.run_attempt == '1'\n"
            "    && (steps.beta_perf_diagnostic.outcome == 'success'\n"
            "        || steps.beta_perf_diagnostic.outcome == 'failure') }}"
        ),
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
    workflow=_workflow_before_backend_mac312_budget(workflow,workflow_path.name)
    if workflow_path.name in {"sanity.yml", "coverage.yml"}: workflow = _workflow_before_legacy_schema_fourteen(workflow, workflow_path.name)
    if workflow_path.name in {"sanity.yml", "coverage.yml"}: workflow = _workflow_before_preowned_six(workflow, workflow_path.name)
    return _workflow_before_sanity_groups(workflow) if workflow_path.name == "sanity.yml" else workflow


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


def test_existing_research_route_and_static_entry_anchors_are_exact() -> None:
    from scripts.check_public_controls import ControlParser
    parser=ControlParser(Path("entry-route-fixture.html"))
    for href in ("/research","/research#my-research","/research#kb-section"):
        parser.feed(f'<a href="{href}">Research</a>')
    assert parser.errors==[]
    unknown=ControlParser(Path("entry-route-fixture.html"))
    unknown.feed('<a href="/research-typo">Unknown</a>')
    assert len(unknown.errors)==1 and "unknown local route: /research-typo" in unknown.errors[0]


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


def _assert_ci_chromium_setup(install_step, helper_bytes):
    assert "if" not in install_step and "continue-on-error" not in install_step
    assert _shell_tokens(install_step) == [
        "python", "-m", "pip", "install",
        "pytest==9.0.3", "playwright==1.59.0", "pytest-playwright==0.7.2",
        "fastapi==0.135.0",
        "pydantic==2.7.4", "starlette==1.3.1",
        "uvicorn[standard]==0.27.1", "PyJWT==2.15.1", "slowapi==0.1.9",
        "structlog==25.5.0", "python", "-I", "-B", "scripts/prepare_ci_chromium.py",
    ]
    assert hashlib.sha256(helper_bytes).hexdigest() == '6801bdfc0678eec08343e8ec43753d54270df096ed7a3103bb10c0ea80376db2'


def _assert_ci_chromium_runner(job):
    assert job['runs-on'] == 'ubuntu-24.04'


def test_phase_auth_browser_job_installs_canonical_runtime_logging() -> None:
    job = _ci_job("browser-identity-consent-contract")
    _assert_ci_chromium_runner(job)
    install_step = _named_ci_step(job, "Install browser test dependencies")
    _assert_ci_chromium_setup(install_step, (ROOT/'scripts/prepare_ci_chromium.py').read_bytes())
    requirements = (
        ROOT / "web/backend/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert "structlog==25.5.0" in requirements


@pytest.mark.parametrize('runner', ['ubuntu-latest','ubuntu-22.04','ubuntu-26.04','self-hosted',
                                  'arbitrary-linux','${{ matrix.os }}',['ubuntu-24.04','self-hosted']])
def test_ci_chromium_runner_requires_the_one_supported_host(runner):
    job={'runs-on':runner}
    with pytest.raises(AssertionError): _assert_ci_chromium_runner(job)


@pytest.mark.parametrize('mutation', ['missing', 'direct_apt', 'wrong_python', 'soft', 'skip', 'helper_bytes'])
def test_ci_chromium_setup_is_one_exact_hard_call_and_frozen_helper(mutation):
    import copy
    step=copy.deepcopy(_named_ci_step(_ci_job('browser-product-contract'),'Install browser test dependencies'))
    helper=(ROOT/'scripts/prepare_ci_chromium.py').read_bytes()
    if mutation=='missing': step['run']=step['run'].replace('python -I -B scripts/prepare_ci_chromium.py','')
    elif mutation=='direct_apt': step['run']=step['run'].replace('python -I -B scripts/prepare_ci_chromium.py','python -m playwright install chromium')
    elif mutation=='wrong_python': step['run']=step['run'].replace('python -I -B scripts/prepare_ci_chromium.py','python3.12 -I -B scripts/prepare_ci_chromium.py')
    elif mutation=='soft': step['continue-on-error']=True
    elif mutation=='skip': step['if']='false'
    else: helper+=b'\n# unreviewed modification\n'
    with pytest.raises(AssertionError): _assert_ci_chromium_setup(step,helper)


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


def _assert_current_research_entry_selection(step) -> None:
    test_path = "tests/e2e/test_full_public_surface.py"
    names = {
        node.name
        for node in ast.parse((ROOT / test_path).read_text(encoding="utf-8")).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    selected = [
        "test_public_entry_actual_owner_index_anchor",
        "test_public_entry_default_retirement_and_language",
        "test_public_entry_no_script_native_forms_never_send_private_get",
        "test_public_entry_real_login_return_owner_and_legacy_resource_links",
        "test_public_entry_main_cta_first_login_returns_to_research",
    ]
    assert set(selected) <= names
    assert _shell_tokens(step) == [
        "pytest", "-p", "no:logging",
        *(f"{test_path}::{name}" for name in selected),
        "-m",
        "e2e and not requires_internet",
        "-v",
    ]
    assert "-k" not in _shell_tokens(step)


def test_browser_product_job_uses_exact_existing_nodeids() -> None:
    job = _ci_job("browser-product-contract")
    step = _named_ci_step(job, "Verify the current public research entry journey")
    _assert_current_research_entry_selection(step)


def _assert_complete_browser_backend_runtime(job, *, matrix=False) -> None:
    step = _named_ci_step(job, "Install complete backend runtime and verify imports")
    assert "continue-on-error" not in step
    if matrix:
        assert step.get("if") == "matrix.shard == 'library-auth-reports-favorites'"
    else:
        assert "if" not in step
    lines=step["run"].splitlines()
    marker='"$BROWSER_BACKEND_PYTHON" - <<\'PY\''
    index=lines.index(marker)
    assert lines[:index+1] == [
        'set -euo pipefail',
        'BROWSER_BACKEND_PYTHON="$(python -c \'import sys; print(sys.executable)\')"',
        '"$BROWSER_BACKEND_PYTHON" -m pip install uv==0.11.8',
        'test "$(uv --version | cut -d \' \' -f 2)" = "0.11.8"',
        'uv pip install --python "$BROWSER_BACKEND_PYTHON" --system --torch-backend cpu -r web/backend/requirements.txt',
        'uv pip check --python "$BROWSER_BACKEND_PYTHON" --system',
        marker,
    ]
    assert lines[-1] == 'PY'
    body='\n'.join(lines[index+1:-1])
    tree=ast.parse(body)
    assert any(isinstance(node,ast.Import) and any(name.name=='main' for name in node.names) for node in ast.walk(tree))
    for boundary in ('importlib.metadata.version(name)', 'web/backend/requirements.txt',
                     'Path(main.__file__).resolve() != root / "web/backend/main.py"',
                     'torch.version.cuda is not None', 'HF_HUB_OFFLINE',
                     'TRANSFORMERS_OFFLINE', 'RUNNER_TEMP', 'TemporaryDirectory'):
        assert boundary in body
    assert 'sys.modules' not in body and 'monkeypatch' not in body
    target='Run browser surface shard' if matrix else 'Verify the current public research entry journey'
    assert job['steps'].index(step)<job['steps'].index(_named_ci_step(job,target))


def test_only_real_main_browser_jobs_install_complete_authoritative_runtime() -> None:
    product=_ci_job('browser-product-contract');surface=_ci_job('browser-beta-surface-contract')
    _assert_complete_browser_backend_runtime(product)
    _assert_complete_browser_backend_runtime(surface,matrix=True)
    assert _named_ci_step(product,'Install complete backend runtime and verify imports')['run']==_named_ci_step(surface,'Install complete backend runtime and verify imports')['run']
    assert product['timeout-minutes']==8 and surface['timeout-minutes']==15
    rows=_ci_matrix_rows(surface)
    assert [row['shard'] for row in rows].count('library-auth-reports-favorites')==1
    assert next(row for row in rows if row['shard']=='library-auth-reports-favorites')['pytest_args_main']=='tests/e2e/test_full_public_surface.py web/tests/e2e/test_auth_login_bootstrap_privacy.py'


@pytest.mark.parametrize('mutation', ['missing_step','wrong_shard','unconditional_matrix','no_requirements',
    'no_cpu','different_python','no_check','no_main','no_source_binding','no_cpu_check','soft_failure'])
def test_complete_browser_runtime_rejects_incomplete_or_weakened_steps(mutation) -> None:
    import copy
    job=copy.deepcopy(_ci_job('browser-beta-surface-contract'))
    step=_named_ci_step(job,'Install complete backend runtime and verify imports')
    if mutation=='missing_step':job['steps'].remove(step)
    elif mutation=='wrong_shard':step['if']="matrix.shard == 'secondary-whitespace'"
    elif mutation=='unconditional_matrix':step.pop('if')
    elif mutation=='no_requirements':step['run']=step['run'].replace('-r web/backend/requirements.txt','numpy==1.26.3 httpx==0.27.2')
    elif mutation=='no_cpu':step['run']=step['run'].replace('--torch-backend cpu','')
    elif mutation=='different_python':step['run']=step['run'].replace('--python "$BROWSER_BACKEND_PYTHON"','--python python3.12')
    elif mutation=='no_check':step['run']=step['run'].replace('uv pip check','uv pip list')
    elif mutation=='no_main':step['run']=step['run'].replace('import main','import types as main')
    elif mutation=='no_source_binding':step['run']=step['run'].replace('Path(main.__file__).resolve() != root / "web/backend/main.py"','False')
    elif mutation=='no_cpu_check':step['run']=step['run'].replace('torch.version.cuda is not None','False')
    else:step['continue-on-error']=True
    with pytest.raises(AssertionError):_assert_complete_browser_backend_runtime(job,matrix=True)


@pytest.mark.parametrize('missing',range(5))
def test_current_entry_gate_cannot_drop_any_required_journey(missing) -> None:
    step=dict(_named_ci_step(_ci_job('browser-product-contract'),'Verify the current public research entry journey'))
    tokens=_shell_tokens(step)
    del tokens[missing+3]
    step['run']=shlex.join(tokens)
    with pytest.raises(AssertionError):_assert_current_research_entry_selection(step)


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
    makefile = _makefile_before_draft_contracts()
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
        "python", "-m", "playwright", "install", "--with-deps", "chromium",
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
        "browser-identity-consent-contract",
        "browser-beta-surface-contract",
        "browser-evidence-method-contract",
        "browser-financial-registry-contract",
        "browser-financial-scenario-contract",
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
            {
                "workflow": ".github/workflows/product-ci.yml",
                "job": "product",
                "context": "product",
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
            "always()" if (required["workflow"], required["job"]) in {
                (".github/workflows/ci.yml", "release-gate-summary"),
                (".github/workflows/sanity.yml", "sanity"),
            } else None
        )
        if (required["workflow"], required["job"]) == (
            ".github/workflows/sanity.yml", "sanity",
        ):
            assert required_job.get("needs") == ["sanity-backend"]
            backend = _workflow_job(workflow_path, "sanity-backend")
            assert backend.get("name") == "sanity-backend"
            assert backend.get("timeout-minutes") == 45
            assert "needs" not in backend
            _assert_hard_job_contract(required["workflow"], "sanity-backend", backend)
            gate = required_job["steps"][0]
            assert gate.get("name") == "Require complete backend baseline success"
            assert gate.get("env") == {
                "SANITY_BACKEND_RESULT": "${{ needs['sanity-backend'].result }}",
            }
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
            expected_branches = ["main", "integration/structure-rebuild-v1"]
            if event == "push":
                expected_branches.append("bootstrap/structure-ci-20261016")
            assert config == {"branches": expected_branches}, (
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
        'NOT_GATE one marked Linux diagnostic pair': (
            '${{ always() && !cancelled()\n'
            "    && github.repository == 'dada8899/structural-isomorphism'\n"
            "    && github.event_name == 'pull_request'\n"
            "    && github.event.action == 'synchronize'\n"
            '    && github.event.pull_request.number == 253\n'
            '    && github.event.pull_request.head.repo.full_name == github.repository\n'
            '    && github.event.pull_request.base.repo.full_name == github.repository\n'
            "    && github.event.pull_request.head.ref == 'bootstrap/structure-ci-20261016'\n"
            "    && github.run_attempt == '1' }}"
        ),
        'Upload NOT_GATE Linux diagnostic evidence': (
            '${{ always() && !cancelled()\n'
            "    && github.repository == 'dada8899/structural-isomorphism'\n"
            "    && github.event_name == 'pull_request'\n"
            "    && github.event.action == 'synchronize'\n"
            '    && github.event.pull_request.number == 253\n'
            '    && github.event.pull_request.head.repo.full_name == github.repository\n'
            '    && github.event.pull_request.base.repo.full_name == github.repository\n'
            "    && github.event.pull_request.head.ref == 'bootstrap/structure-ci-20261016'\n"
            "    && github.run_attempt == '1'\n"
            "    && (steps.beta_perf_diagnostic.outcome == 'success'\n"
            "        || steps.beta_perf_diagnostic.outcome == 'failure') }}"
        ),
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
        "httpx==0.27.2", "fastapi==0.135.0", "pydantic==2.7.4",
        "starlette==1.3.1", "uvicorn[standard]==0.27.1", "PyJWT==2.15.1",
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
        "Run reviewed local browser contracts"
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
    makefile = _makefile_before_draft_contracts()
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


def _original_makefile_before_auth_bootstrap_browser(makefile: str) -> str:
    auth='web/tests/e2e/test_auth_login_bootstrap_privacy.py'
    variable='BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS'
    assignment='\ttests/e2e/test_full_public_surface.py \\\n\t'+auth+' \\\n\ttests/e2e/test_unified_research_library.py'
    formal='\t$(PYTEST) tests/e2e/test_full_public_surface.py '+auth+' -p no:logging -m "e2e and not requires_internet" -v\n'
    isolated='\t$(PYTEST) $(filter-out '+auth+',$(filter web/tests/e2e/%,$('+variable+'))) -m "e2e and not requires_internet" -v\n'
    assert makefile.count(auth)==3 and makefile.count(assignment)==1 and makefile.count(formal)==1 and makefile.count(isolated)==1
    assert makefile.index(formal)<makefile.index(isolated)
    return makefile.replace(assignment,assignment.replace('\t'+auth+' \\\n',''),1).replace(formal,formal.replace(' '+auth,''),1).replace(isolated,'\t$(PYTEST) $(filter web/tests/e2e/%,$('+variable+')) -m "e2e and not requires_internet" -v\n',1)


B3_FRESH_MAIN_MODULES = ('test_source_document_raw_lifecycle.py',
    'test_formal_main_history_read_borrow.py', 'test_source_document_cached_history.py')


# First-live historical deferral only: before Native live/drop-in/paid activation,
# all six unchanged dynamic ownership/physical-close/retry/retire obligations must run.
# First-live scope only: controlled Native authority birth/retry is not used
# by central FIN1/FIN2/FIN3 or SMTP. Keep its original failure and full obligation.
# Fixed B segments preserve the complete original argv; only process grouping changes.
ORDINARY_B_PART_IDS = ('sanity-backend-ordinary-b-1', 'sanity-backend-ordinary-b-2', 'sanity-backend-ordinary-b-3')
ORDINARY_B_PART_MODULES = (('tests/test_research_financial_admission_schemas.py', 'tests/test_research_financial_evaluator_v2.py', 'tests/test_research_financial_input_schemas.py', 'tests/test_research_financial_result_v2.py', 'tests/test_research_financial_schema_v15.py', 'tests/test_research_financial_schema_v7.py', 'tests/test_research_fingerprint.py', 'tests/test_research_formula_binding.py', 'tests/test_research_formula_cases.py', 'tests/test_research_formula_delivery.py', 'tests/test_research_formula_lifecycle.py', 'tests/test_research_formula_public.py', 'tests/test_research_formula_result_adapter.py', 'tests/test_research_funded_plan.py', 'tests/test_research_index.py', 'tests/test_research_legacy_paid_component.py', 'tests/test_research_lifecycle.py', 'tests/test_research_method_body_codec.py', 'tests/test_research_method_body_types.py', 'tests/test_research_method_draft_migration.py', 'tests/test_research_method_history.py'), ('tests/test_research_method_result.py', 'tests/test_research_method_schema_v9.py', 'tests/test_research_mint_reported_bytes.py', 'tests/test_research_native_plan.py', 'tests/test_research_native_preowned.py', 'tests/test_research_native_schema_v13.py', 'tests/test_research_offline_profiles.py', 'tests/test_research_owned_return.py', 'tests/test_research_paid_api.py', 'tests/test_research_paid_api_public.py', 'tests/test_research_paid_approval.py', 'tests/test_research_paid_budget_loop.py', 'tests/test_research_paid_method14_origin.py', 'tests/test_research_paid_producer_migration.py'), ('tests/test_research_paid_producers.py', 'tests/test_research_paid_public.py', 'tests/test_research_paid_schema.py', 'tests/test_research_paid_stop_callers.py', 'tests/test_research_persistence.py', 'tests/test_research_phenomenon_plan.py', 'tests/test_research_plan_contract.py', 'tests/test_research_plan_preview_codec.py', 'tests/test_research_plan_schema_v12.py', 'tests/test_research_preview_codec.py', 'tests/test_research_private_storage.py', 'tests/test_research_revision_budget.py', 'tests/test_research_runtime_profile.py', 'tests/test_research_schema_concurrency.py', 'tests/test_research_source_lifetime.py', 'tests/test_research_source_request_capability.py', 'tests/test_research_source_spawn.py', 'tests/test_research_source_supervisor.py', 'tests/test_research_source_terminal14.py', 'tests/test_research_source_v11.py', 'tests/test_research_sql_token_cache.py', 'tests/test_research_usage_quote.py', 'tests/test_retrieval_eval_dataset.py', 'tests/test_runtime_admission.py', 'tests/test_runtime_paths.py', 'tests/test_runtime_security_contract.py', 'tests/test_safe_english_retrieval.py', 'tests/test_scope_guard.py', 'tests/test_search_logging_privacy.py', 'tests/test_search_scope_gate.py', 'tests/test_search_service_v2v3.py', 'tests/test_search_synthesis_integrity.py', 'tests/test_secondary_tools_trust_contract.py', 'tests/test_security_headers.py', 'tests/test_slowapi_pep563_globals_crash.py', 'tests/test_source_document_access.py', 'tests/test_source_document_raw.py', 'tests/test_source_document_transport.py', 'tests/test_source_sec_access.py', 'tests/test_sqlite_lifecycle.py', 'tests/test_sso_report_claim.py', 'tests/test_startup_hybrid_deps.py', 'tests/test_stress_test.py', 'tests/test_struct_lint.py', 'tests/test_structlog_format.py', 'tests/test_systemd_credential_metadata.py', 'tests/test_universality_endpoints.py', 'tests/test_version.py', 'tests/test_waitlist.py', 'tests/test_whitespace.py'))
ORDINARY_B_PART_TEMPLATE_SHA256 = 'b6a85c34b86473081a09a3bbc021912a1d102a19cebf9c31490980baf763e710'
ORDINARY_B_PART_PRIOR_JOBS_SHA256 = 'e62bfdb00cfef6822e2fd869b8f48ffe1c1066ee2fd24e965c650a713a8a898e'
ORDINARY_B_PART_AGGREGATE = {'name': 'sanity-backend-ordinary-b', 'runs-on': 'ubuntu-latest', 'timeout-minutes': 45, 'needs': ['sanity-backend-ordinary-b-1', 'sanity-backend-ordinary-b-2', 'sanity-backend-ordinary-b-3'], 'if': 'always()', 'steps': [{'name': 'Require all fixed ordinary B segments success', 'env': {'BACKEND_B1_RESULT': "${{ needs['sanity-backend-ordinary-b-1'].result }}", 'BACKEND_B2_RESULT': "${{ needs['sanity-backend-ordinary-b-2'].result }}", 'BACKEND_B3_RESULT': "${{ needs['sanity-backend-ordinary-b-3'].result }}"}, 'run': 'for result in "${BACKEND_B1_RESULT:-}" "${BACKEND_B2_RESULT:-}" "${BACKEND_B3_RESULT:-}"; do\n  if [ "$result" != "success" ]; then\n    echo "A complete ordinary B segment did not succeed."\n    exit 1\n  fi\ndone\n'}]}


# Fixed 20/1 fresh jobs preserve all 21 original cold-process commands.
# This addresses the observed platform job wall, not a business deadline.
FRESH_PART_IDS = ('sanity-backend-fresh-1', 'sanity-backend-fresh-2')
FRESH_PART_MODULES = (('tests/test_formal_main_admission.py', 'tests/test_formal_main_source_supervisor.py', 'tests/test_research_financial_import.py', 'tests/test_formal_model_startup.py', 'tests/acceptance/test_source_history_fixture_current15.py', 'tests/test_research_financial_registries.py', 'tests/test_research_source_origin_history.py', 'tests/test_research_evidence_method_plan.py', 'tests/test_research_evidence_method_native.py', 'tests/test_plan_runtime_transport.py', 'tests/test_research_native_browser_service.py', 'tests/test_native_live_grant.py', 'tests/test_formal_native_plan_supervisor.py', 'tests/test_research_financial_execution_v2.py', 'tests/test_research_financial_results_v2.py', 'tests/test_source_sec_access_lifecycle.py', 'tests/test_source_document_raw_lifecycle.py', 'tests/test_formal_main_history_read_borrow.py', 'tests/test_source_document_cached_history.py', 'tests/test_financial_limit_observer.py'), ('tests/test_research_method_drafts.py',))
FRESH_PART_TEMPLATE_SHA256 = 'b6a85c34b86473081a09a3bbc021912a1d102a19cebf9c31490980baf763e710'
FRESH_PART_PRIOR_JOBS_SHA256 = '30f8e111fa68f24c3caa871e109d0ae99e064a5ce20c4abaeb689b8d91d9b695'
FRESH_PART_AGGREGATE = {'name': 'sanity-backend-fresh', 'runs-on': 'ubuntu-latest', 'timeout-minutes': 45, 'needs': ['sanity-backend-fresh-1', 'sanity-backend-fresh-2'], 'if': 'always()', 'steps': [{'name': 'Require all fixed fresh segments success', 'env': {'BACKEND_FRESH1_RESULT': "${{ needs['sanity-backend-fresh-1'].result }}", 'BACKEND_FRESH2_RESULT': "${{ needs['sanity-backend-fresh-2'].result }}"}, 'run': 'for result in "${BACKEND_FRESH1_RESULT:-}" "${BACKEND_FRESH2_RESULT:-}"; do\n  if [ "$result" != "success" ]; then\n    echo "A complete fresh segment did not succeed."\n    exit 1\n  fi\ndone\n'}]}


# The reviewed CPU artifact is selected inside the original dependency resolver.
CPU_TORCH_URL = 'https://download-r2.pytorch.org/whl/cpu/torch-2.14.1%2Bcpu-cp311-cp311-manylinux_2_28_x86_64.whl'
CPU_TORCH_SHA256 = '5e38154c8896d426a5df58bf2276b603e82184dfae4f54d77dbb212f36e34f37'
CPU_TORCH_REQUIREMENT = 'torch @ '+CPU_TORCH_URL+'#sha256='+CPU_TORCH_SHA256
CPU_TORCH_PRE = "python - <<'CPU_TORCH_PIN'\nimport hashlib, platform, re, sys\nfrom pathlib import Path\n\ndef verify_cpu_torch_pin(lock, requirements, runtime):\n    assert type(lock) is str and type(requirements) is str\n    assert runtime == ('cpython', 'linux', (3, 11), 'x86_64')\n    assert hashlib.sha256(lock.encode('utf-8')).hexdigest() == 'efd2731c4e9e212ab75e6bcb53880d88492e1a44272622f05b6c98e8a606b6f5'\n    lines = lock.splitlines()\n    indexes = [i for i, line in enumerate(lines) if line.startswith('torch==')]\n    assert len(indexes) == 1\n    start = indexes[0]\n    assert lines[start].split()[0] == 'torch==2.14.1+cpu'\n    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith('#')), len(lines))\n    assert '5e38154c8896d426a5df58bf2276b603e82184dfae4f54d77dbb212f36e34f37' in re.findall(r'--hash=sha256:([0-9a-f]{64})', '\\n'.join(lines[start + 1:end]))\n    assert [line.strip() for line in requirements.splitlines() if line.strip().startswith('torch') and not line.lstrip().startswith('#')] == ['torch==2.14.1']\n\nverify_cpu_torch_pin(Path('requirements/runtime-linux-cpu.lock').read_text(), Path('web/backend/requirements.txt').read_text(), (sys.implementation.name, sys.platform, sys.version_info[:2], platform.machine()))\nCPU_TORCH_PIN\n"
CPU_TORCH_POST = "python - <<'CPU_TORCH_RESULT'\nfrom importlib.metadata import version\nimport torch\nassert version('torch') == '2.14.1+cpu'\nassert torch.__version__ == '2.14.1+cpu'\nassert torch.version.cuda is None\nCPU_TORCH_RESULT\n"
CPU_TORCH_CI_CONDITION = 'if [ "${{ matrix.os }}" = "ubuntu-latest" ] && [ "${{ matrix.python-version }}" = "3.11" ]; then\n'
CPU_TORCH_PRIOR_JOBS_SHA256 = {'sanity.yml': '7d34fe816e330b645545b60c2200278577a4f9b79c7e7ecf931a54cbebe4a8c2', 'ci.yml': '292b6fe2eb41c31f0026fb40ced69c4105d4dd881edc3992dded187a7eb0e182'}
CPU_TORCH_ORIGINAL_RUNS = {('sanity.yml', 'sanity-backend-ordinary-a', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity-backend-ordinary-b-1', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity-backend-ordinary-b-2', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity-backend-ordinary-b-3', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity-backend-fresh-1', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity-backend-fresh-2', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity', 'Install web/backend deps'): 'pip install -r web/backend/requirements.txt\n', ('sanity.yml', 'sanity', 'Install root release contract dependencies'): 'python -m pip install -e ".[dev]"\npython -m pip install playwright==1.59.0\npython -m playwright install --with-deps chromium\n', ('ci.yml', 'backend', 'Install dependencies'): 'python -m pip install --upgrade pip\npython -m pip install -e ".[dev]"\npython -m pip install pyyaml\n', ('ci.yml', 'backend', 'Install local packages (editable)'): 'pip install -e packages/soc-pipeline\npip install -e packages/guarded-llm\npip install -e packages/cross-judge\n'}
CPU_TORCH_PROOF_PYTHON = __import__('sys').executable


def _cpu_torch_install_run(original,command):
    assert original.splitlines().count(command)==1
    return CPU_TORCH_PRE+original.replace(command,command+' '+shlex.quote(CPU_TORCH_REQUIREMENT),1)+CPU_TORCH_POST


def _workflow_before_cpu_torch_sources(value,name):
    if name not in ('sanity.yml','ci.yml'):return value
    original=copy.deepcopy(value)
    for (workflow,jid,title),prior in CPU_TORCH_ORIGINAL_RUNS.items():
        if workflow!=name:continue
        step=[s for s in original['jobs'][jid]['steps'] if s.get('name')==title];assert len(step)==1
        if name=='sanity.yml':
            command='python -m pip install -e ".[dev]"' if title=='Install root release contract dependencies' else 'pip install -r web/backend/requirements.txt'
            expected=_cpu_torch_install_run(prior,command)
        elif title=='Install dependencies':
            expected=CPU_TORCH_CI_CONDITION+_cpu_torch_install_run(prior,'python -m pip install -e ".[dev]"')+'else\n'+prior+'fi\n'
        else:expected=prior+CPU_TORCH_CI_CONDITION+CPU_TORCH_POST+'fi\n'
        assert step[0]['run']==expected
        step[0]['run']=prior
    assert hashlib.sha256(json.dumps(original['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==CPU_TORCH_PRIOR_JOBS_SHA256[name]
    return original


def _workflow_before_fresh_parts(value,name):
    if name!='sanity.yml':return value
    value=_workflow_before_cpu_torch_sources(value,name)
    original=copy.deepcopy(value);jobs=original['jobs']
    assert jobs['sanity-backend-fresh']==FRESH_PART_AGGREGATE
    complete=[];common_header=None;restored=None
    for jid,expected_modules in zip(FRESH_PART_IDS,FRESH_PART_MODULES):
        job=jobs[jid];assert job['name']==jid
        steps=[s for s in job['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline'];assert len(steps)==1
        script=steps[0]['run'];commands=[s for s in script.splitlines(keepends=True) if s.startswith('python -m pytest ')]
        assert tuple(shlex.split(s)[3] for s in commands)==expected_modules
        header=script[:script.index(commands[0])];assert script==header+''.join(commands)
        if common_header is None:common_header=header
        else:assert header==common_header
        template=copy.deepcopy(job);template['name']='<NAME>'
        next(s for s in template['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline')['run']='<SCRIPT>'
        assert hashlib.sha256(json.dumps(template,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==FRESH_PART_TEMPLATE_SHA256
        if restored is None:restored=copy.deepcopy(job)
        complete.extend(commands)
    assert len(complete)==21 and [len(group) for group in FRESH_PART_MODULES]==[20,1]
    restored['name']='sanity-backend-fresh'
    next(s for s in restored['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline')['run']=common_header+''.join(complete)
    jobs['sanity-backend-fresh']=restored
    for jid in FRESH_PART_IDS:del jobs[jid]
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==FRESH_PART_PRIOR_JOBS_SHA256
    return original


def _workflow_before_ordinary_b_parts(value,name):
    value=_workflow_before_fresh_parts(value,name)
    if name!='sanity.yml':return value
    original=copy.deepcopy(value);jobs=original['jobs']
    assert original.get('permissions')=={'contents':'read'}
    assert set(jobs)=={'sanity-backend','sanity','sanity-backend-ordinary-a','sanity-backend-ordinary-b','sanity-backend-fresh',*ORDINARY_B_PART_IDS}
    assert jobs['sanity-backend-ordinary-b']==ORDINARY_B_PART_AGGREGATE
    whole=[];scripts=[];template_job=None;common_tail=None;common_head=None;common_end=None
    for jid,expected_modules in zip(ORDINARY_B_PART_IDS,ORDINARY_B_PART_MODULES):
        job=jobs[jid];assert job['name']==jid
        steps=[s for s in job['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline'];assert len(steps)==1
        script=steps[0]['run'];lines=[s for s in script.splitlines(keepends=True) if s.startswith('python -m pytest ')];assert len(lines)==1
        line=lines[0];tokens=shlex.split(line);end=next(i for i in range(3,len(tokens)) if tokens[i].startswith('-'))
        modules=tokens[3:end];assert tuple(modules)==expected_modules
        prefix='python -m pytest '+' '.join(modules);assert line.startswith(prefix+' ')
        head=script[:script.index(line)];tail=line[len(prefix):];ending=script[script.index(line)+len(line):]
        if common_tail is None:common_head,common_tail,common_end=head,tail,ending
        else:assert (head,tail,ending)==(common_head,common_tail,common_end)
        template=copy.deepcopy(job);template['name']='<NAME>';next(s for s in template['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline')['run']='<SCRIPT>'
        assert hashlib.sha256(json.dumps(template,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==ORDINARY_B_PART_TEMPLATE_SHA256
        whole.extend(modules);scripts.append(script)
        if template_job is None:template_job=copy.deepcopy(job)
    assert len(whole)==85 and len(set(whole))==85 and [len(x) for x in ORDINARY_B_PART_MODULES]==[21,14,50]
    template_job['name']='sanity-backend-ordinary-b'
    next(s for s in template_job['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline')['run']=common_head+'python -m pytest '+' '.join(whole)+common_tail+common_end
    jobs['sanity-backend-ordinary-b']=template_job
    for jid in ORDINARY_B_PART_IDS:del jobs[jid]
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==ORDINARY_B_PART_PRIOR_JOBS_SHA256
    return original


AUTHORITY_RETRY_NODE = 'web/backend/tests/test_research_native_browser_service.py::test_real_authority_birth_failure_can_retry_without_adopting_orphan_resources'
AUTHORITY_RETRY_SOURCE_SHA256 = '04dcfbbb3cfc57515b4099ff9e86684bcf3ed0c191da5e346c9bdb9ae87fd002'
AUTHORITY_RETRY_PRIOR_JOBS_SHA256 = {'sanity.yml': 'd586f6f53afbfa5ba38129726d710eaeeae8ba86de4f46abc22e50f1611e9a8c', 'coverage.yml': '82d00ddae8ffa9f06e36e64c46642b4500c1ef142113233b44c0e7a2be4e5634'}


def _authority_retry_flag():
    return ' --deselect="'+AUTHORITY_RETRY_NODE+'"'


def _workflow_before_authority_retry(value,name):
    value=_workflow_before_ordinary_b_parts(value,name)
    original=copy.deepcopy(value);jobs=original['jobs']
    if name=='sanity.yml':
        job=jobs['sanity-backend-fresh'];title='Leg 2 — web/backend pytest baseline';prefix='python -m pytest tests/'
    else:
        assert name=='coverage.yml';job=jobs['coverage'];title='Run coverage (split by suite, parallel files combined)';prefix='python -m coverage run -p --rcfile=.coveragerc -m pytest web/backend/tests/'
    steps=[x for x in job['steps'] if x.get('name')==title];assert len(steps)==1
    script=steps[0]['run'];expected=prefix+AUTHORITY_RETRY_NODE.split('::')[0].split('/')[-1]+_authority_retry_flag()+' '
    matches=[line for line in script.splitlines() if line.startswith(expected)]
    assert len(matches)==1 and script.count(AUTHORITY_RETRY_NODE)==1
    steps[0]['run']=script.replace(_authority_retry_flag(),'',1)
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==AUTHORITY_RETRY_PRIOR_JOBS_SHA256[name]
    return original


# Only three future-Native late-return schedules are deferred for first live.
# Their source, real failures, unexecuted case and future native activation
# obligations remain; evidence cancel and all general delete/UNKNOWN/SQL guards run.
NATIVE_LATE_THREE_NODES = ('web/backend/tests/test_plan_runtime_transport.py::test_actual_late_return_original_credential_books_fee_without_restoring_body[cancel]', 'web/backend/tests/test_plan_runtime_transport.py::test_actual_late_return_original_credential_books_fee_without_restoring_body[delete]', 'web/backend/tests/test_research_evidence_method_native.py::test_actual_http_stop_after_owned_return_keeps_original_fee_without_late_body[delete]')
NATIVE_LATE_SOURCE_SHA256 = {'test_plan_runtime_transport.py': '183a2564e164de6fbef5def8bad5deaec0131287f103e718b1890028de8cf86d', 'test_research_evidence_method_native.py': '220ab632c68c1d41385331768765f472eb44c106e948b1f36c5bc1f355db7737'}
NATIVE_LATE_PRIOR_JOBS_SHA256 = {'sanity.yml': 'b95cec3f3dda97eb1ae4f90c9f588722b95c4f7e8f88e2ecd786568846064dfe', 'coverage.yml': '1e97fd441e46e0357c2602d04fb92b77b22b085fbac2674288a7e5d7a3af26f5'}


def _native_late_flags(filename):
    return ''.join(' --deselect="'+node+'"' for node in NATIVE_LATE_THREE_NODES if '/'+filename+'::' in node)


def _workflow_before_native_late_three(value,name):
    value=_workflow_before_authority_retry(value,name)
    original=copy.deepcopy(value);jobs=original['jobs']
    if name=='sanity.yml':
        job=jobs['sanity-backend-fresh'];title='Leg 2 — web/backend pytest baseline'
        prefix='python -m pytest tests/'
    else:
        assert name=='coverage.yml';job=jobs['coverage'];title='Run coverage (split by suite, parallel files combined)'
        prefix='python -m coverage run -p --rcfile=.coveragerc -m pytest web/backend/tests/'
    steps=[step for step in job['steps'] if step.get('name')==title];assert len(steps)==1
    script=steps[0]['run']
    for filename in ('test_plan_runtime_transport.py','test_research_evidence_method_native.py'):
        flags=_native_late_flags(filename);lines=[line for line in script.splitlines() if line.startswith(prefix+filename+' ')]
        assert len(lines)==1 and lines[0].startswith(prefix+filename+flags+' ')
        assert script.count(flags)==1
        for node in [v for v in NATIVE_LATE_THREE_NODES if '/'+filename+'::' in v]:
            assert script.count(node)==1
        script=script.replace(flags,'',1)
    steps[0]['run']=script
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==NATIVE_LATE_PRIOR_JOBS_SHA256[name]
    return original


# Exact first-live deferral: only the controlled Native partial-send positive.
# Its original body and conservative cleanup failure remain; before Native live,
# drop-in or paid activation this case must actually pass. The other four
# first-entry UNKNOWN/held/no-refund controls must remain selected.
PARTIAL_RUNTIME_NODE = 'web/backend/tests/test_plan_runtime_transport.py::test_evidence_runtime_first_socket_entry_is_recorded_once_and_never_refunded[partial]'
PARTIAL_RUNTIME_BASE = PARTIAL_RUNTIME_NODE.removesuffix('[partial]')
PARTIAL_RUNTIME_SOURCE_SHA256 = '183a2564e164de6fbef5def8bad5deaec0131287f103e718b1890028de8cf86d'
PARTIAL_RUNTIME_PRIOR_JOBS_SHA256 = {'sanity.yml': 'ec103152bde1b0fab45c26ba8ba21753fbbf1a6f22df0efa0e495c051910ab6b', 'coverage.yml': 'b069c58743f61f7a0864c5b361b7598a09ac467f8c68d611c63864d52575d324'}


def _partial_runtime_flag():
    return ' --deselect="'+PARTIAL_RUNTIME_NODE+'"'


def _workflow_before_partial_runtime(value,name):
    value=_workflow_before_native_late_three(value,name)
    original=copy.deepcopy(value);jobs=original['jobs']
    if name=='sanity.yml':
        job=jobs['sanity-backend-fresh'];title='Leg 2 — web/backend pytest baseline'
        prefix='python -m pytest tests/test_plan_runtime_transport.py'
    else:
        assert name=='coverage.yml';job=jobs['coverage'];title='Run coverage (split by suite, parallel files combined)'
        prefix='python -m coverage run -p --rcfile=.coveragerc -m pytest web/backend/tests/test_plan_runtime_transport.py'
    steps=[step for step in job['steps'] if step.get('name')==title];assert len(steps)==1
    script=steps[0]['run'];lines=script.splitlines(keepends=True)
    matching=[line for line in lines if line.startswith(prefix+' ')];assert len(matching)==1
    line=matching[0];assert line.count(_partial_runtime_flag())==1 and script.count(PARTIAL_RUNTIME_BASE)==1
    assert line.startswith(prefix+_partial_runtime_flag()+' -p no:logging ')
    selected=[word.removeprefix('--deselect=') for word in shlex.split(line) if word.startswith('--deselect=')]
    assert selected==[PARTIAL_RUNTIME_NODE]
    steps[0]['run']=script.replace(_partial_runtime_flag(),'',1)
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==PARTIAL_RUNTIME_PRIOR_JOBS_SHA256[name]
    return original


# Historical R11->R12 and R12->R13 deferral only. These fourteen obligations must
# actually pass before any legacy11/12/13 maintenance or recovery is supported.
LEGACY_SCHEMA_DEFERRED_NODES = ('web/backend/tests/test_research_native_schema_v13.py::test_real_old12_offline13_preserves_ledger_fixture_result_ref_time_newprocess',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[journal]',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[rebuild]',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[resource]',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[marker]',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[before-commit]',
 'web/backend/tests/test_research_native_schema_v13.py::test_native13_actual_kill_recovery_only_complete12_or13_with_same_ledger[after-commit]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_real_complete11_to12_same_inode_formula_ref_time_and_old_source_permission',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[journal]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[rebuild]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[resource]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[marker]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[before-commit]',
 'web/backend/tests/test_research_plan_schema_v12.py::test_v12_actual_kill_recovers_only_complete_old11_or_new12_same_formula_bytes[after-commit]')
LEGACY_SCHEMA_REQUIRED_PRODUCER = 'web/backend/tests/test_research_native_schema_v13.py::test_real_v12_reference_producer_is_selfcontained_without_git_or_old_checkout'
LEGACY_SCHEMA_ORIGINAL_SHA256 = '4c61f4c15a017ba115327a6ac9469a664c7183d36a0f213b454134ab085b9617'
LEGACY_SCHEMA_PLAN12_SHA256 = '3e0d265d7ac1e5a1e3c1584563e731e82b116dbcb5b83f0e883d7e480aaf4f4e'
LEGACY_SCHEMA_PRIOR_JOBS_SHA256 = {'sanity.yml': '80caf582946d706442ed3c76dcc7ff9e7131fcb9b2bfdd36005c5ff1fe91400f', 'coverage.yml': '991f54306338f28363decdb0c31132d80b2a413fd40736d9e6034c76f1ff7e44'}

def _legacy_schema_flags():
    return ''.join(' --deselect="'+node+'"' for node in LEGACY_SCHEMA_DEFERRED_NODES)


def _workflow_before_legacy_schema_fourteen(value,name):
    value=_workflow_before_partial_runtime(value,name)
    original=copy.deepcopy(value);jobs=original['jobs']
    if name=='sanity.yml':
        targets=[jobs['sanity-backend-ordinary-a'],jobs['sanity-backend-ordinary-b']];title='Leg 2 — web/backend pytest baseline'
    else:
        assert name=='coverage.yml';targets=[jobs['coverage']];title='Run coverage (split by suite, parallel files combined)'
    for job in targets:
        steps=[step for step in job['steps'] if step.get('name')==title];assert len(steps)==1
        script=steps[0]['run'];assert script.count(_legacy_schema_flags())==1
        matching=[line for line in script.splitlines() if _legacy_schema_flags() in line];assert len(matching)==1 and matching[0].startswith('python -m ')
        removed=[token.removeprefix('--deselect=') for token in shlex.split(matching[0]) if token.startswith('--deselect=') and any(name in token for name in ('test_research_native_schema_v13.py','test_research_plan_schema_v12.py'))]
        assert removed==list(LEGACY_SCHEMA_DEFERRED_NODES) and len(set(removed))==14 and LEGACY_SCHEMA_REQUIRED_PRODUCER not in removed
        steps[0]['run']=script.replace(_legacy_schema_flags(),'',1)
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==LEGACY_SCHEMA_PRIOR_JOBS_SHA256[name]
    return original


# The single macOS/Python3.12 cell gets a bounded preparation phase;
# its two original test commands share one 15-minute phase, not 15 each.
BACKEND_MAC312_TARGET_IF = "${{ matrix.os == 'macos-latest' && matrix['python-version'] == '3.12' }}"
BACKEND_MAC312_OTHER_IF = "${{ !(matrix.os == 'macos-latest' && matrix['python-version'] == '3.12') }}"
BACKEND_MAC312_JOB_TIMEOUT = "${{ matrix.os == 'macos-latest' && matrix['python-version'] == '3.12' && 40 || 15 }}"
BACKEND_MAC312_PRIOR_JOBS_SHA256 = 'e19c9f8e6a62f2cc2b2257610541fffb02018a69ee5ed5be2cd8d2695146dbbc'


def _workflow_before_backend_mac312_budget(value,name):
    if name!='ci.yml':return value
    value=_workflow_before_cpu_torch_sources(value,name)
    original=copy.deepcopy(value);job=original['jobs']['backend'];steps=job['steps']
    assert job['timeout-minutes']==BACKEND_MAC312_JOB_TIMEOUT and len(steps)==9
    ordinary=steps[3:5]+steps[6:8]
    assert [s['name'] for s in ordinary]==['Install dependencies','Install local packages (editable)','Run sanity tests','Run integration tests (skip slow)']
    for step in ordinary:assert step.pop('if')==BACKEND_MAC312_OTHER_IF
    expected_prep={'name':'Prepare original dependencies (macOS Python 3.12)','if':BACKEND_MAC312_TARGET_IF,'timeout-minutes':20,'run':ordinary[0]['run']+ordinary[1]['run']}
    expected_tests={'name':'Run original backend suites (macOS Python 3.12)','if':BACKEND_MAC312_TARGET_IF,'timeout-minutes':15,'run':ordinary[2]['run']+'\n'+ordinary[3]['run']+'\n'}
    assert steps[5]==expected_prep and steps[8]==expected_tests
    job['timeout-minutes']=15;job['steps']=steps[:3]+ordinary
    assert hashlib.sha256(json.dumps(original['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==BACKEND_MAC312_PRIOR_JOBS_SHA256
    return original


def _workflow_source_before_legacy_schema(name):
    value=yaml.safe_load((ROOT/'.github/workflows'/name).read_text())
    value=_workflow_before_backend_mac312_budget(value,name)
    return _workflow_before_legacy_schema_fourteen(value,name) if name in {'sanity.yml','coverage.yml'} else value


# First-live capacity scope: central single scenario remains required. Only the
# unchanged three-scenario/21-point maximum combination is deferred, not passed.
# Complete U2 capacity must be verified before claiming the expanded workload.
FIN3_CAPACITY_NODE = 'web/tests/e2e/test_research_financial_scenario_browser.py::test_fin3_actual_main_coverage_three_scenarios_and_twenty_one_points'
FIN3_CAPACITY_SELECTOR = 'test_research_financial_scenario_browser.py::test_fin3_actual_main_coverage_three_scenarios_and_twenty_one_points'
FIN3_CAPACITY_SOURCE_SHA256 = '0d7c97812567e5b5294118cd8b9a1b3e210f0a82cd9d2d3d2813bdc86e329239'
AUTHORITY_RETRY_PRIOR_MAKE_SHA256 = '99eee0a10d555be27c17cb6d43f19ec8487218edddaf06fe7f9cd9b1921c5090'


# These current Main contracts are executed once in a fresh process, never deferred.
ROOT_CURRENT_MAIN_NODES = ('tests/test_research_browser.py::test_new_research_without_task_selector_keeps_real_create_and_save', 'tests/test_research_browser.py::test_current_main_private_problem_xss_auth503_draft_and_real401_clear', 'tests/test_research_browser.py::test_native_plan_actual_closed_preview_discloses_exact_input_without_confirm_or_model', 'tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[new-draft]', 'tests/test_research_browser.py::test_native_plan_late_actual_closed_preview_never_replaces_new_draft_or_private_scope[logout]', 'tests/test_research_browser.py::test_native_plan_real_https_browser_journey[saved]', 'tests/test_research_browser.py::test_native_plan_real_https_browser_journey[lost-ack]', 'tests/test_research_browser.py::test_native_plan_real_https_browser_journey[late-saved-ack]', 'tests/test_research_browser.py::test_native_plan_real_https_browser_journey[account-switch]', 'tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[invalid-body]', 'tests/test_research_browser.py::test_native_plan_terminal_known_outcome_releases_only_original_intent[saved]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[not-sent]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[unknown-usage]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cleanup-uncertain]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-before]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cancel-after]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[late-B]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[wrong-ref]', 'tests/test_research_browser.py::test_native_plan_terminal_boundary_preserves_unknown_and_current_input[cross-owner]', 'tests/test_research_browser.py::test_method_draft_manual_editor_starts_blank_and_requires_actual_references', 'tests/test_research_browser.py::test_method_draft_actual_old_source_to_current_manual_draft_and_readonly_history', 'tests/test_research_browser.py::test_method_draft_reads_actual_runtime_plan_lead_without_prefilling_or_execution', 'tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[new-editor]', 'tests/test_research_browser.py::test_method_draft_real_late_history_keeps_new_editor_and_private_clear[logout]', 'tests/test_research_browser.py::test_method_draft_plan_reselection_matches_visible_current_choices', 'tests/test_research_browser.py::test_method_draft_formula_picker_distinguishes_same_revision_original_results', 'tests/test_research_browser.py::test_method_draft_actual_main_old_source_new_problem_save_and_reopen', 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[cas]', 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-ack]', 'tests/test_research_browser.py::test_method_draft_actual_main_conflict_and_unknown_recovery[lost-get]', 'tests/test_research_browser.py::test_method_draft_actual_main_saved_formula_original_identity_and_outcomes', 'tests/test_research_browser.py::test_method_draft_actual_main_second_catalog_page_preserves_current_form_and_pending', 'tests/test_research_browser.py::test_source_history_actual_main_closed_collection_keeps_existing_readable')
ROOT_CURRENT_MAIN_PRIOR_MAKE_SHA256 = 'c1381b788ee0d7f4163a1a528b5176c3c994ff43db7223096c3d156cccfd6596'
ROOT_CURRENT_MAIN_PRIOR_RECIPE = '\t$(BACKEND_PYTEST) tests --ignore=tests/e2e -m "not e2e and not slow and not requires_internet and not requires_llm" -q\n'


def _root_current_main_flags():
    return ''.join(' --deselect="'+node+'"' for node in ROOT_CURRENT_MAIN_NODES)


def _root_current_main_recipe_pair(prefix):
    original=ROOT_CURRENT_MAIN_PRIOR_RECIPE.replace('\t$(BACKEND_PYTEST)',prefix,1)
    ordinary=original.replace(' --ignore=tests/e2e',' --ignore=tests/e2e'+_root_current_main_flags(),1)
    fresh=prefix+' '+shlex.join(ROOT_CURRENT_MAIN_NODES)+' -m "not e2e and not slow and not requires_internet and not requires_llm" -q\n'
    return original,ordinary,fresh


# Retired dev-auth/lifespan-off browser workflows remain source-preserved.
# Their exact variants must be verified before enabling the deferred feature families.
ROOT_RETIRED_BROWSER_NODES = ('tests/test_research_browser.py::test_d1_page_preview_confirm_real_worker_and_private_mobile_records', 'tests/test_research_browser.py::test_d1_page_lost_start_receipt_reload_replays_original_key', 'tests/test_research_browser.py::test_d1_source_link_uses_public_canonical_url_without_provider_reference', 'tests/test_research_browser.py::test_d1_task_switch_clears_old_cards_before_empty_new_records', 'tests/test_research_browser.py::test_d1_input_switch_rejects_late_old_records_and_clears_cards', 'tests/test_research_browser.py::test_d1_closed_unknown_keeps_original_observation_visible', 'tests/test_research_browser.py::test_real_page_revisions_restart_private_access_and_mobile', 'tests/test_research_browser.py::test_real_commit_lost_browser_receipt_reuses_original_key', 'tests/test_research_browser.py::test_nfc_pending_digest_reconciles_after_real_revision_commit_and_reopen', 'tests/test_research_browser.py::test_inflight_form_is_frozen_until_actual_commit_receipt_then_reenabled', 'tests/test_research_browser.py::test_invalid_sso_poison_clears_previously_rendered_research', 'tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[completed]', 'tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[pending]', 'tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[rejected]', 'tests/test_research_browser.py::test_account_delete_page_reports_actual_outcome_without_restore_promises[unknown]', 'tests/test_research_browser.py::test_public_report_page_stops_showing_resource_during_pending_account_cleanup', 'tests/test_research_browser.py::test_c0_page_real_task_worker_money_and_draft_survive_status_refresh', 'tests/test_research_browser.py::test_c0_page_cancel_unknown_reconcile_never_restarts_task', 'tests/test_research_browser.py::test_late_task_start_receipt_does_not_rebind_newer_saved_problem', 'tests/test_research_browser.py::test_task_refresh_never_rebases_other_window_save_base', 'tests/test_research_browser.py::test_task_refresh_never_rebases_other_window_run_base', 'tests/test_research_browser.py::test_late_cancel_receipt_cannot_replace_newer_same_revision_task', 'tests/test_research_browser.py::test_entry_original_draft_kb_and_real_saved_source_chain', 'tests/test_research_browser.py::test_entry_index_real_pagination_invalid_cursor_and_late_receipt', 'tests/test_research_browser.py::test_entry_list_reopen_preserves_unknown_save_and_late_auth_list', 'tests/test_research_browser.py::test_entry_kb_unavailable_is_honest_and_account_switch_clears_private_view', 'tests/test_research_browser.py::test_entry_changed_source_query_rejects_held_real_preview', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-kb]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[503-reload]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[500-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[403-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[404-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[409-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[network-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[bad-json-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[bad-user-list]', 'tests/test_research_browser.py::test_entry_auth_uncertain_preserves_unknown_draft_and_stops_chain[ok-false-list]', 'tests/test_research_browser.py::test_entry_auth_real_401_clears_private_draft_and_stops_chain', 'tests/test_research_browser.py::test_source_reopen_explains_explicit_read_without_losing_draft_or_refetching_provider[viewport0]', 'tests/test_research_browser.py::test_source_reopen_explains_explicit_read_without_losing_draft_or_refetching_provider[viewport1]', 'tests/test_research_browser.py::test_method_result_real_b_typed_http_reopen_restart_and_local_citations[viewport0]', 'tests/test_research_browser.py::test_method_result_real_b_typed_http_reopen_restart_and_local_citations[viewport1]', 'tests/test_research_browser.py::test_method_result_consumes_real_reconcile_view_without_generation[pending]', 'tests/test_research_browser.py::test_method_result_real_bad_b_never_becomes_visible_body[null]', 'tests/test_research_browser.py::test_method_result_cancelled_pending_body_stays_hidden[pending]', 'tests/test_research_browser.py::test_method_result_changed_input_and_late_real_a_cannot_restore_old_body', 'tests/test_research_browser.py::test_method_result_actual_auth503_preserves_draft_but_requires_fresh_read', 'tests/test_research_browser.py::test_method_result_cross_owner_and_source_withdrawal_remove_private_body', 'tests/test_research_browser.py::test_method_view_client_schema_rejects_corruption_of_real_backend_view', 'tests/test_research_browser.py::test_method_result_new_explicit_source_task_clears_current_method_body', 'tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[saved-404]', 'tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[saved-401]', 'tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[draft-404]', 'tests/test_research_browser.py::test_method_result_late_actual_access_error_cannot_clear_new_problem[draft-401]', 'tests/test_research_browser.py::test_method_result_successful_old_write_cannot_revive_revoked_private_view', 'tests/test_research_browser.py::test_method_current_source_unavailable_preserves_problem_and_explains_missing_body[task-refresh]', 'tests/test_research_browser.py::test_method_current_source_unavailable_preserves_problem_and_explains_missing_body[source-refresh]', 'tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport0-history-revision]', 'tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport0-history-same]', 'tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport1-history-revision]', 'tests/test_research_browser.py::test_history_real_result_original_problem_native_new_tab_restart_and_readonly[viewport1-history-same]', 'tests/test_research_browser.py::test_fixed_task_and_history_never_replay_real_pending_source_intent[source-approvals]', 'tests/test_research_browser.py::test_fixed_task_and_history_never_replay_real_pending_source_intent[source-tasks]', 'tests/test_research_browser.py::test_history_real_43_tasks_inclusive_pages_no_gaps_duplicates_or_lost_anchor[history-pages]', 'tests/test_research_browser.py::test_late_real_source_unavailable_200_cannot_overwrite_new_problem[draft]', 'tests/test_research_browser.py::test_late_real_source_unavailable_200_cannot_overwrite_new_problem[saved]', 'tests/test_research_browser.py::test_unavailable_historical_body_preserves_original_readonly_problem_and_navigation[history-revision]', 'tests/test_research_browser.py::test_current_real_cross_owner404_remains_visible_and_clears_private_content', 'tests/test_research_browser.py::test_history_client_validation_rejects_mismatched_task_flags_and_bad_navigation[history-same]', 'tests/test_research_browser.py::test_fixed_current_task_refresh_becomes_historical_with_server_truth[revision]', 'tests/test_research_browser.py::test_fixed_current_task_refresh_becomes_historical_with_server_truth[task]', 'tests/test_research_browser.py::test_invalid_or_ambiguous_task_url_never_falls_back_to_editable_current_problem', 'tests/test_research_browser.py::test_formula_real_ui_save_snapshot_confirm_actual_return_and_reopen[viewport0]', 'tests/test_research_browser.py::test_formula_real_ui_save_snapshot_confirm_actual_return_and_reopen[viewport1]', 'tests/test_research_browser.py::test_formula_empty_structure_is_real_saved_draft_and_not_executable', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[little-0]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[little-1]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[mm1-0]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[mm1-1]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[thermal-rc-0]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[thermal-rc-1]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[local-0]', 'tests/test_research_browser.py::test_formula_registered_cases_real_inputs_and_honest_execution_status[local-1]', 'tests/test_research_browser.py::test_formula_lost_actual_post_receipt_reopens_and_recovers_same_key_ref_without_second_task', 'tests/test_research_browser.py::test_late_actual_formula_post_ack_cannot_replace_new_formula_or_problem[draft]', 'tests/test_research_browser.py::test_late_actual_formula_post_ack_cannot_replace_new_formula_or_problem[saved]', 'tests/test_research_browser.py::test_formula_old_real_post_success_after_logout_cannot_restore_private_results', 'tests/test_research_browser.py::test_formula_explicit_refresh_does_not_mix_another_window_revision_into_old_problem', 'tests/test_research_browser.py::test_formula_real_history_native_tab_original_snapshot_result_time_and_readonly[revision]', 'tests/test_research_browser.py::test_formula_real_history_native_tab_original_snapshot_result_time_and_readonly[new-task]', 'tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[formula-checks]', 'tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[source-approvals]', 'tests/test_research_browser.py::test_formula_fixed_or_historical_view_keeps_genuine_pending_intent_without_any_post[source-tasks]', 'tests/test_research_browser.py::test_formula_late_actual_result_access_error_cannot_clear_new_saved_problem[401]', 'tests/test_research_browser.py::test_formula_late_actual_result_access_error_cannot_clear_new_saved_problem[404]', 'tests/test_research_browser.py::test_formula_actual_auth503_preserves_all_editor_fields_and_real_pending', 'tests/test_research_browser.py::test_formula_real_source_reader_keeps_old_revision_and_stop_policy_but_hides_withdrawn_result', 'tests/test_research_browser.py::test_formula_client_canonical_bounds_and_attestation_guards_from_actual_http_record', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[normal]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[abort]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[missing-ref]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-digest]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-task]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[wrong-ref]', 'tests/test_research_browser.py::test_formula_ack_is_confirmed_and_request_bound_before_pending_key_retirement[other-real-run]', 'tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[current-logout]', 'tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[restored-session]', 'tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[new-draft]', 'tests/test_research_browser.py::test_formula_ack_metadata401_confirms_current_auth_loss_without_retiring_unknown_key[private-scope-changed]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[account-switch]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-wrong-task]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-new-draft]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[restored-owner]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[late-root-new-draft]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[late-root-private-scope]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[credential-conflict]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[same-owner-dual]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[restored-conflict]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[stale-conflict-draft]', 'tests/test_research_browser.py::test_formula_ack_identity_boundary_preserves_unknown_key_and_current_draft[stale-conflict-private-scope]')
ROOT_RETIRED_BROWSER_PRIOR_MAKE_SHA256 = 'b6198934c4feb9e1b218ab20510b4b1704e8a2f723d3339eade76bf85ebad427'


def _root_retired_browser_flags():
    return ''.join(' --deselect="'+node+'"' for node in ROOT_RETIRED_BROWSER_NODES)


ROOT_CURRENT_MAIN_STDOUT_PRIOR_MAKE_SHA256 = 'b866437c09c242c4d054fac9c625a589b0b11f0268672d9b64cbbddf085dd99e'


def _makefile_before_current_main_stdout(makefile):
    _,_,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)')
    stdout=fresh.replace(' -m ',' -p no:logging -m ',1)
    assert makefile.splitlines(keepends=True).count(stdout)==1
    prior=makefile.replace(stdout,fresh,1)
    assert hashlib.sha256(prior.encode()).hexdigest()==ROOT_CURRENT_MAIN_STDOUT_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_current_main_stdout(output):
    _makefile_before_current_main_stdout((ROOT/'Makefile').read_text())
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    _,_,fresh=_root_current_main_recipe_pair('PYTHONPATH='+pythonpath+' python -m pytest')
    stdout=fresh.replace(' -m ',' -p no:logging -m ',1)
    assert output.splitlines(keepends=True).count(stdout)==1
    return output.replace(stdout,fresh,1)


def _makefile_before_retired_browser121(makefile):
    makefile=_makefile_before_current_main_stdout(makefile)
    _,ordinary,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)')
    retired=ordinary.replace(' --ignore=tests/e2e',' --ignore=tests/e2e'+_root_retired_browser_flags(),1)
    assert len(ROOT_RETIRED_BROWSER_NODES)==len(set(ROOT_RETIRED_BROWSER_NODES))==121
    assert not set(ROOT_RETIRED_BROWSER_NODES)&set(ROOT_CURRENT_MAIN_NODES)
    assert makefile.splitlines(keepends=True).count(retired)==1 and makefile.splitlines(keepends=True).count(fresh)==1
    prior=makefile.replace(retired+fresh,ordinary+fresh,1)
    assert hashlib.sha256(prior.encode()).hexdigest()==ROOT_RETIRED_BROWSER_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_retired_browser121(output):
    output=_dry_run_before_current_main_stdout(output)
    _makefile_before_retired_browser121((ROOT/'Makefile').read_text())
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    _,ordinary,fresh=_root_current_main_recipe_pair('PYTHONPATH='+pythonpath+' python -m pytest')
    retired=ordinary.replace(' --ignore=tests/e2e',' --ignore=tests/e2e'+_root_retired_browser_flags(),1)
    assert output.splitlines(keepends=True).count(retired)==1 and output.splitlines(keepends=True).count(fresh)==1
    return output.replace(retired+fresh,ordinary+fresh,1)


def _makefile_before_root_current_main33(makefile):
    makefile=_makefile_before_retired_browser121(makefile)
    original,ordinary,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)')
    assert len(ROOT_CURRENT_MAIN_NODES)==len(set(ROOT_CURRENT_MAIN_NODES))==33
    assert makefile.splitlines(keepends=True).count(ordinary)==1 and makefile.splitlines(keepends=True).count(fresh)==1
    prior=makefile.replace(ordinary+fresh,original,1)
    assert hashlib.sha256(prior.encode()).hexdigest()==ROOT_CURRENT_MAIN_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_root_current_main33(output):
    output=_dry_run_before_retired_browser121(output)
    _makefile_before_root_current_main33((ROOT/'Makefile').read_text())
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    original,ordinary,fresh=_root_current_main_recipe_pair('PYTHONPATH='+pythonpath+' python -m pytest')
    assert output.splitlines(keepends=True).count(ordinary)==1 and output.splitlines(keepends=True).count(fresh)==1
    return output.replace(ordinary+fresh,original,1)


def _makefile_before_authority_retry(makefile):
    makefile=_makefile_before_root_current_main33(makefile)
    prefix='\tcd web/backend && $(BACKEND_PYTEST) tests/'+AUTHORITY_RETRY_NODE.split('::')[0].split('/')[-1]
    expected=prefix+_authority_retry_flag()+' -p no:logging -q\n'
    assert makefile.splitlines(keepends=True).count(expected)==1 and makefile.count(AUTHORITY_RETRY_NODE)==1
    prior=makefile.replace(_authority_retry_flag(),'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==AUTHORITY_RETRY_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_authority_retry(output):
    output=_dry_run_before_root_current_main33(output)
    _makefile_before_authority_retry((ROOT/'Makefile').read_text())
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    expected='cd web/backend && PYTHONPATH='+pythonpath+' python -m pytest tests/'+AUTHORITY_RETRY_NODE.split('::')[0].split('/')[-1]+_authority_retry_flag()+' -p no:logging -q\n'
    assert output.splitlines(keepends=True).count(expected)==1 and output.count(AUTHORITY_RETRY_NODE)==1
    return output.replace(expected,expected.replace(_authority_retry_flag(),'',1),1)


FIN3_CAPACITY_PRIOR_MAKE_SHA256 = '1d6d54cf06fff83a53fa3576d77842c382bd3d4062ec09187683c32d8185a771'
FIN3_CAPACITY_OTHER_CASES = ('test_fin3_actual_main_ordinary_form_save_three_views_and_history',
    'test_fin3_actual_main_reload_rebuild_exact_request_with_historical_catalog',
    'test_fin3_actual_main_pending_unknown_bfcache_delete_without_module_click',
    'test_fin3_actual_main_old_derived_result_complete_readonly',
    'test_fin3_actual_main_late_recovery_catalog_not_revived_after_delete',
    'test_fin3_actual_main_mode_drafts_units_preflight_and_save')


def _fin3_capacity_flag():
    return ' --deselect="'+FIN3_CAPACITY_SELECTOR+'"'


def _makefile_before_fin3_capacity(makefile):
    makefile=_makefile_before_authority_retry(makefile)
    expected='test-financial-scenario-browser-contract:\n\t$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS)'+_fin3_capacity_flag()+' -p no:logging -v\n'
    assert makefile.count(expected)==1 and makefile.count(FIN3_CAPACITY_SELECTOR)==1
    prior=makefile.replace(_fin3_capacity_flag(),'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==FIN3_CAPACITY_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_fin3_capacity(output):
    output=_dry_run_before_authority_retry(output)
    _makefile_before_fin3_capacity((ROOT/'Makefile').read_text())
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    expected='PYTHONPATH='+pythonpath+' python -m pytest '+FIN3_CAPACITY_NODE.split('::')[0]+_fin3_capacity_flag()+' -p no:logging -v\n'
    assert output.splitlines(keepends=True).count(expected)==1 and output.count(FIN3_CAPACITY_SELECTOR)==1
    return output.replace(expected,expected.replace(_fin3_capacity_flag(),'',1),1)


NATIVE_LATE_PRIOR_MAKE_SHA256 = '13173ded4edc322d4b8d4145cf1c27eb461b43a6013f490cee16dafd0319af0a'


def _makefile_before_native_late_three(makefile):
    makefile=_makefile_before_fin3_capacity(makefile)
    prior=makefile
    for filename in ('test_plan_runtime_transport.py','test_research_evidence_method_native.py'):
        prefix='\tcd web/backend && $(BACKEND_PYTEST) tests/'+filename
        flags=_native_late_flags(filename)
        matching=[line for line in prior.splitlines() if line.startswith(prefix+' ')]
        assert len(matching)==1 and matching[0].startswith(prefix+flags+' ')
        assert prior.count(flags)==1
        for node in [v for v in NATIVE_LATE_THREE_NODES if '/'+filename+'::' in v]:assert prior.count(node)==1
        prior=prior.replace(flags,'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==NATIVE_LATE_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_native_late_three(output):
    output=_dry_run_before_fin3_capacity(output)
    raw=(ROOT/'Makefile').read_text();_makefile_before_native_late_three(raw)
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    backend='PYTHONPATH='+pythonpath+' python -m pytest'
    for filename in ('test_plan_runtime_transport.py','test_research_evidence_method_native.py'):
        flags=_native_late_flags(filename)
        prefix='cd web/backend && '+backend+' tests/'+filename
        matches=[line for line in output.splitlines(keepends=True) if line.startswith(prefix+' ')]
        assert len(matches)==1 and matches[0].startswith(prefix+flags+' ') and output.count(flags)==1
        output=output.replace(matches[0],matches[0].replace(flags,'',1),1)
    return output


PARTIAL_RUNTIME_PRIOR_MAKE_SHA256 = '3815a574ef21937c169cefb204c5b5df222b23acb7592816a534ee3cdc4b0a41'


def _makefile_before_partial_runtime(makefile):
    makefile=_makefile_before_native_late_three(makefile)
    expected='\tcd web/backend && $(BACKEND_PYTEST) tests/test_plan_runtime_transport.py'+_partial_runtime_flag()+' -p no:logging -q\n'
    assert makefile.splitlines(keepends=True).count(expected)==1 and makefile.count(PARTIAL_RUNTIME_BASE)==1
    prior=makefile.replace(_partial_runtime_flag(),'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==PARTIAL_RUNTIME_PRIOR_MAKE_SHA256
    return prior


def _dry_run_before_partial_runtime(output):
    output=_dry_run_before_native_late_three(output)
    raw=(ROOT/'Makefile').read_text();_makefile_before_partial_runtime(raw)
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    backend='PYTHONPATH='+pythonpath+' python -m pytest'
    recipe='cd web/backend && $(BACKEND_PYTEST) tests/test_plan_runtime_transport.py'+_partial_runtime_flag()+' -p no:logging -q'
    expected=recipe.replace('$(BACKEND_PYTEST)',backend,1)+'\n'
    assert output.splitlines(keepends=True).count(expected)==1 and output.count(PARTIAL_RUNTIME_BASE)==1
    return output.replace(expected,expected.replace(_partial_runtime_flag(),'',1),1)


LEGACY_SCHEMA_PRIOR_MAKE_SHA256 = 'a96493c45271f9542b350dfeb152c6a28e963b40e54724285aaa802b11a4520b'

def _original_makefile_before_legacy_schema(makefile):
    makefile=_makefile_before_partial_runtime(makefile)
    commands=[line for line in _make_recipe_commands(makefile,'verify-release') if line.startswith('cd web/backend ')]
    assert len(commands)==22 and commands[0].endswith(_legacy_schema_flags()+' -q') and makefile.count(_legacy_schema_flags())==1
    prior=makefile.replace(_legacy_schema_flags(),'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==LEGACY_SCHEMA_PRIOR_MAKE_SHA256
    return prior


def _makefile_before_legacy_schema_contracts():
    return _original_makefile_before_legacy_schema((ROOT/'Makefile').read_text())


def _original_dry_run_before_legacy_schema(output):
    output=_dry_run_before_partial_runtime(output)
    raw=(ROOT/'Makefile').read_text();_original_makefile_before_legacy_schema(raw);raw=_makefile_before_partial_runtime(raw)
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    backend='PYTHONPATH='+pythonpath+' python -m pytest'
    expected=[line.replace('$(BACKEND_PYTEST)',backend,1)+'\n' for line in _make_recipe_commands(raw,'verify-release') if line.startswith('cd web/backend ')]
    assert [line for line in output.splitlines(keepends=True) if line.startswith('cd web/backend ')]==expected
    assert output.splitlines(keepends=True).count(expected[0])==1 and expected[0].endswith(_legacy_schema_flags()+' -q\n')
    return output.replace(expected[0],expected[0].replace(_legacy_schema_flags(),'',1),1)


PREOWNED_DEFERRED_NODES = ('web/backend/tests/test_research_native_preowned.py::test_preowned_real_get_socket_close_after_physical_close_is_not_clean',
 'web/backend/tests/test_research_native_preowned.py::test_clean_low_balance_keeps_same_resource_for_new_legal_attempt',
 'web/backend/tests/test_research_native_preowned.py::test_allocated_connection_failure_is_owned_and_clean_retry_uses_same_resource',
 'web/backend/tests/test_research_native_preowned.py::test_all_core_retirements_precede_hook_and_flight_release_after_close_fault',
 'web/backend/tests/test_research_native_preowned.py::test_unreturned_allocated_socket_close_failure_keeps_original_error_and_uncertainty',
 'web/backend/tests/test_research_native_preowned.py::test_retire_hook_never_accepts_a_status_dto_as_clean')
PREOWNED_PRIOR_JOBS_SHA256 = {'sanity.yml': '92c9354ff7e1164f0c3c0294f63f0aa92b1d7ca6d60d4abf8fa4f18f011b96bf', 'coverage.yml': 'b32f4fabd40203b9b6d60cb3ba5e6fd24c239d9829ff69654db57febff13d1a4'}

def _preowned_flags():
    return ''.join(' --deselect="'+node+'"' for node in PREOWNED_DEFERRED_NODES)


def _workflow_before_preowned_six(value,name):
    original=copy.deepcopy(value)
    jobs=original['jobs']
    if name=='sanity.yml':
        targets=[jobs['sanity-backend-ordinary-a'],jobs['sanity-backend-ordinary-b']]
        title='Leg 2 — web/backend pytest baseline'
    else:
        assert name=='coverage.yml'
        targets=[jobs['coverage']]
        title='Run coverage (split by suite, parallel files combined)'
    for job in targets:
        steps=[step for step in job['steps'] if step.get('name')==title]
        assert len(steps)==1
        script=steps[0]['run']
        assert script.count(_preowned_flags())==1
        matching=[line for line in script.splitlines() if _preowned_flags() in line]
        assert len(matching)==1 and matching[0].startswith('python -m ')
        selected=[token.removeprefix('--deselect=') for token in shlex.split(matching[0]) if token.startswith('--deselect=') and 'test_research_native_preowned.py' in token]
        assert selected==list(PREOWNED_DEFERRED_NODES) and len(set(selected))==6
        steps[0]['run']=script.replace(_preowned_flags(),'',1)
    assert hashlib.sha256(json.dumps(jobs,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==PREOWNED_PRIOR_JOBS_SHA256[name], 'six-only inverse restores exact current jobs/flags/batches'
    return original


def _workflow_source_before_preowned(name):
    value=_workflow_source_before_legacy_schema(name)
    return _workflow_before_preowned_six(value,name) if name in {'sanity.yml','coverage.yml'} else value


def _sanity_source_before_preowned():
    return _workflow_source_before_preowned('sanity.yml')


PREOWNED_PRIOR_MAKE_SHA256 = '817c0530476c59c8c7e14234809df021872a2961a6171bb89bfb4c124a7a42eb'

def _original_makefile_before_preowned(makefile):
    commands=[line for line in _make_recipe_commands(makefile,'verify-release') if line.startswith('cd web/backend ')]
    assert len(commands)==22 and commands[0].endswith(_preowned_flags()+' -q')
    assert makefile.count(_preowned_flags())==1
    prior=makefile.replace(_preowned_flags(),'',1)
    assert hashlib.sha256(prior.encode()).hexdigest()==PREOWNED_PRIOR_MAKE_SHA256
    return prior


def _makefile_before_preowned_contracts():
    return _original_makefile_before_preowned(_makefile_before_legacy_schema_contracts())


def _original_dry_run_before_preowned(output):
    output = _original_dry_run_before_legacy_schema(output)
    raw=_makefile_before_legacy_schema_contracts();_original_makefile_before_preowned(raw)
    pythonpath=':'.join(str(ROOT/path) for path in ('web/backend','packages/guarded-llm/src','packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    backend='PYTHONPATH='+pythonpath+' python -m pytest'
    expected=[line.replace('$(BACKEND_PYTEST)',backend,1)+'\n' for line in _make_recipe_commands(raw,'verify-release') if line.startswith('cd web/backend ')]
    lines=output.splitlines(keepends=True)
    assert [line for line in lines if line.startswith('cd web/backend ')]==expected
    assert lines.count(expected[0])==1 and expected[0].endswith(_preowned_flags()+' -q\n')
    return output.replace(expected[0],expected[0].replace(_preowned_flags(),'',1),1)


SANITY_GROUP_IDS = ('sanity-backend-ordinary-a', 'sanity-backend-ordinary-b', 'sanity-backend-fresh')
SANITY_GROUP_MODULE_SHA256 = {'sanity-backend-ordinary-a': 'bb40d0d7697a66759fc93def64c9972cd684b45ae33b590dacd2f3df39784faf', 'sanity-backend-ordinary-b': 'a582078265ae585e573e823dedc74220a5cd22d98264a2f1ea4299be2a3d8055', 'sanity-backend-fresh': 'c5808735773d6c4c9ac37db23221b2098ec3b86e792d95bb99dcb08228429c2f'}
SANITY_GROUP_HEADER = '# -ra: surface skipped/xfailed reasons. -q: compact output.\n# --tb=short: brief tracebacks.\n# The baseline as of 2026-05-24 is 781 passing tests; new tests\n# added in 0.1.1+ must also pass here.\n# Stop on a real failure so its traceback survives the job deadline.\n'
SANITY_GROUP_TAIL = '\n'
SANITY_GROUP_TEMPLATE_SHA256 = '09a91c8a73a073668af54b003d79db1ab8cea11aac87bcabff36ef2c2c4d5ad9'
SANITY_LOGICAL_NATIVE_JOB_SHA256 = 'af733baa4e59f8739fc47a164f396d6874ad49ba6b5b43b4a6e178e007b44885'
SANITY_DOWNSTREAM_JOB_SHA256 = '1c18ed6205db5836b87b31729a54af40045471c0322ed0b9555b7a81e127a297'
SANITY_GROUP_AGGREGATE = {'name': 'sanity-backend',
 'runs-on': 'ubuntu-latest',
 'timeout-minutes': 45,
 'needs': ['sanity-backend-ordinary-a', 'sanity-backend-ordinary-b', 'sanity-backend-fresh'],
 'if': 'always()',
 'steps': [{'name': 'Require all complete backend groups success',
            'env': {'BACKEND_ORDINARY_A_RESULT': "${{ needs['sanity-backend-ordinary-a'].result }}",
                    'BACKEND_ORDINARY_B_RESULT': "${{ needs['sanity-backend-ordinary-b'].result }}",
                    'BACKEND_FRESH_RESULT': "${{ needs['sanity-backend-fresh'].result }}"},
            'run': 'for result in "${BACKEND_ORDINARY_A_RESULT:-}" "${BACKEND_ORDINARY_B_RESULT:-}" '
                   '"${BACKEND_FRESH_RESULT:-}"; do\n'
                   '  if [ "$result" != "success" ]; then\n'
                   '    echo "A complete backend group did not succeed."\n'
                   '    exit 1\n'
                   '  fi\n'
                   'done\n'}]}

def _batch_digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _sanity_group_script(job):
    steps=[step for step in job['steps'] if step.get('name')=='Leg 2 — web/backend pytest baseline']
    assert len(steps)==1
    return steps[0]


def _workflow_before_sanity_groups(value):
    original=copy.deepcopy(value);jobs=original['jobs']
    assert set(jobs)=={'sanity-backend','sanity',*SANITY_GROUP_IDS}
    assert original['permissions']=={'contents':'read'}
    assert jobs['sanity-backend']==SANITY_GROUP_AGGREGATE
    assert _batch_digest(jobs['sanity'])==SANITY_DOWNSTREAM_JOB_SHA256
    logical=_sanity_native_logical_commands()
    assert len(logical)==22
    modules={}
    for name in SANITY_GROUP_IDS:
        child=jobs[name]
        assert child['name']==name
        template=copy.deepcopy(child);template['name']='sanity-backend';_sanity_group_script(template)['run']='<BACKEND_SCRIPT>'
        assert _batch_digest(template)==SANITY_GROUP_TEMPLATE_SHA256, 'every child retains complete original setup/env/cwd/runner/permissions/45min'
        script=_sanity_group_script(child)['run']
        if name.endswith('fresh'):
            paths=[shlex.split(line)[3] for line in logical[1:]]
            expected=SANITY_GROUP_HEADER+'\n'.join(logical[1:])+SANITY_GROUP_TAIL
        else:
            commands=[line for line in script.splitlines() if line.startswith('python -m pytest ')]
            assert len(commands)==1
            args=shlex.split(commands[0]);assert args[:3]==['python','-m','pytest']
            end=next(i for i in range(3,len(args)) if args[i].startswith('-'))
            paths=args[3:end]
            assert all(path.startswith('tests/') and path.endswith('.py') and '::' not in path for path in paths)
            prefix='python -m pytest tests'
            assert logical[0].startswith(prefix+' ')
            expected=SANITY_GROUP_HEADER+'python -m pytest '+' '.join(paths)+logical[0][len(prefix):]+SANITY_GROUP_TAIL
        assert _batch_digest(paths)==SANITY_GROUP_MODULE_SHA256[name], 'fixed complete module list and original order'
        assert script==expected, 'whole argv/ignore/canonicaldefer/flags/logging and separate fresh processes exact'
        modules[name]=paths
    a,b,fresh=(modules[name] for name in SANITY_GROUP_IDS)
    assert len(a)==77 and len(b)==85 and len(fresh)==21
    assert len(set(a+b+fresh))==183
    assert all(path.removeprefix('tests/')<'test_research_financial' for path in a)
    assert all(path.removeprefix('tests/')>='test_research_financial' for path in b)
    directory=ROOT/'web/backend/tests'
    inventory={'tests/'+path.relative_to(directory).as_posix() for pattern in ('test_*.py','*_test.py') for path in directory.rglob(pattern) if path.is_file()}
    assert inventory==set(a+b+fresh), 'all source modules exactly once, not only list-internal uniqueness'
    assert all(not(directory/path.removeprefix('tests/')).is_symlink() for path in inventory)
    restored=copy.deepcopy(jobs[SANITY_GROUP_IDS[0]]);restored['name']='sanity-backend'
    _sanity_group_script(restored)['run']=SANITY_GROUP_HEADER+'\n'.join(logical)+SANITY_GROUP_TAIL
    assert _batch_digest(restored)==SANITY_LOGICAL_NATIVE_JOB_SHA256
    jobs['sanity-backend']=restored
    for name in SANITY_GROUP_IDS:del jobs[name]
    return original


def _sanity_native_logical_commands():
    raw=_makefile_before_preowned_contracts()
    _original_makefile_before_native_split(raw)
    commands=[line for line in _make_recipe_commands(raw,'verify-release') if line.startswith('cd web/backend ')]
    prefix='cd web/backend && $(BACKEND_PYTEST)'
    result=[]
    for index,line in enumerate(commands):
        assert line.startswith(prefix) and line.endswith(' -q')
        command=line.replace(prefix,'python -m pytest tests' if index==0 else 'python -m pytest',1)
        result.append(command[:-len(' -q')]+' -x -ra -q --tb=short --durations=10')
    return result


NATIVE_DEFERRED_NODES = ('web/backend/tests/test_research_native_plan.py::test_native_closed_allows_cost_preview_without_cash_or_funding_and_keeps_saved_question',
 'web/backend/tests/test_research_native_plan.py::test_native_actual_http_worker_single_requests_typed_saved_ref_no_cap_as_cash',
 'web/backend/tests/test_research_native_plan.py::test_native_preconnect_failure_is_before_consume_releases_reserved_hold',
 'web/backend/tests/test_research_native_plan.py::test_native_json_authority_and_foreign_types_cannot_install',
 'web/backend/tests/test_research_native_plan.py::test_native13_rows_and_shared_ledger_default_deny_without_scope[ordinary]',
 'web/backend/tests/test_research_native_plan.py::test_native13_rows_and_shared_ledger_default_deny_without_scope[private]',
 'web/backend/tests/test_research_native_plan.py::test_native_actual_owned_late_return_books_cost_without_reviving_body[cancel]',
 'web/backend/tests/test_research_native_plan.py::test_native_actual_owned_late_return_books_cost_without_reviving_body[delete]',
 'web/backend/tests/test_research_native_plan.py::test_native_owned_close_failure_keeps_booked_result_and_quarantines_resource',
 'web/backend/tests/test_research_native_plan.py::test_native_first_write_ambiguous_never_retries_and_keeps_held',
 'web/backend/tests/test_research_native_plan.py::test_native_retired_runtime_permit_cannot_retain_resource_sending_authority',
 'web/backend/tests/test_research_native_plan.py::test_review_pending_close_after_real_response_books_and_retires_owned_return',
 'web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[fake]',
 'web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[unrelated_owner]',
 'web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[actual_owner_noop]',
 'web/backend/tests/test_research_native_plan.py::test_review_native_write_rejects_unrelated_or_unproduced_financial_changes[money_wrapper_noop]',
 'web/backend/tests/test_research_native_plan.py::test_review_retired_native_permit_preview_is_closed_without_reading_balance',
 'web/backend/tests/test_research_native_plan.py::test_review_unknown_cleanup_preserves_every_execution_and_financial_field',
 'web/backend/tests/test_research_native_plan.py::test_review_funding_owner_binding_preserves_other_registered_accounts_closed_preview')
NATIVE_PURE_NODES = ('web/backend/tests/test_research_native_plan.py::test_native_cleanup_attempts_every_resource_and_never_masks_retirement_failure',
 'web/backend/tests/test_research_native_plan.py::test_native_public_response_and_actual_http_contract_are_strict')
NATIVE_PRIOR_MAKE_SHA256 = 'ec6e7d356682b530d85195d84454848a70138ef282cbe3442e03212b797861a6'

def _native_split_flags():
    return ''.join(' --deselect="' + node + '"' for node in NATIVE_DEFERRED_NODES)


def _original_makefile_before_native_split(makefile):
    commands = [c for c in _make_recipe_commands(makefile,'verify-release') if c.startswith('cd web/backend ')]
    assert len(commands) == 22 and commands[0].endswith(_native_split_flags() + ' -q')
    selected = [token.removeprefix('--deselect=') for token in shlex.split(commands[0]) if token.startswith('--deselect=')]
    assert selected == list(NATIVE_DEFERRED_NODES) and len(selected) == len(set(selected)) == 19
    assert not set(selected) & set(NATIVE_PURE_NODES)
    assert makefile.count('test_research_native_plan.py') == 19
    expanded = ''.join('\t' + c + '\n' for c in commands)
    assert makefile.count(expanded) == 1
    prior = [commands[0].replace(_native_split_flags() + ' -q',' -q',1),*commands[1:]]
    result = makefile.replace(expanded,''.join('\t' + c + '\n' for c in prior),1)
    assert hashlib.sha256(result.encode()).hexdigest() == NATIVE_PRIOR_MAKE_SHA256, 'native inverse must restore the complete 53c Makefile/twenty-two commands'
    return result


def _makefile_before_native_contracts():
    return _original_makefile_before_native_split(_makefile_before_preowned_contracts())


def _original_dry_run_before_native_split(output):
    output = _original_dry_run_before_preowned(output)
    raw = _makefile_before_preowned_contracts()
    _original_makefile_before_native_split(raw)
    pythonpath = ':'.join(str(ROOT / path) for path in ('web/backend','packages/guarded-llm/src',
        'packages/cross-judge/src','packages/reject-aware-critic/src','packages/soc-pipeline/src'))
    backend = 'PYTHONPATH=' + pythonpath + ' python -m pytest'
    expected = [c.replace('$(BACKEND_PYTEST)',backend,1) + '\n' for c in _make_recipe_commands(raw,'verify-release') if c.startswith('cd web/backend ')]
    lines = output.splitlines(keepends=True)
    assert [line for line in lines if line.startswith('cd web/backend ')] == expected
    assert lines.count(expected[0]) == 1 and expected[0].endswith(_native_split_flags() + ' -q\n')
    return output.replace(expected[0],expected[0].replace(_native_split_flags() + ' -q\n',' -q\n',1),1)


DRAFT_HISTORY_MODULE = 'test_research_method_drafts.py'
DRAFT_DEFERRED_FUNCTION = 'test_actual_native_plan_lead_is_bound_without_promoting_literature_or_formula'
DRAFT_PRIOR_MAKE_SHA256 = '4ef388277d85ba42380a6ac21672c44ef608221ef0ea09c8d548b9574f4e1030'


def _original_makefile_before_draft_collection(makefile: str) -> str:
    commands = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    path = 'tests/' + DRAFT_HISTORY_MODULE
    formal = 'cd web/backend && $(BACKEND_PYTEST) ' + path + ' --deselect=web/backend/tests/' + DRAFT_HISTORY_MODULE + '::' + DRAFT_DEFERRED_FUNCTION + ' -p no:logging -q'
    ignore = ' --ignore=' + path
    assert len(commands) == 22 and commands[-1] == formal and commands.count(formal) == 1
    assert commands[0].count(ignore) == 1 and commands[0].endswith(ignore + ' -q')
    assert makefile.count(DRAFT_HISTORY_MODULE) == 3, 'one ignore/full module/exact node only'
    expanded = ''.join('\t' + c + '\n' for c in commands)
    assert makefile.count(expanded) == 1, 'one contiguous complete backend block required'
    prior = [commands[0].replace(ignore + ' -q', ' -q', 1), *commands[1:-1]]
    result = makefile.replace(expanded, ''.join('\t' + c + '\n' for c in prior), 1)
    assert hashlib.sha256(result.encode()).hexdigest() == DRAFT_PRIOR_MAKE_SHA256, 'inverse must restore exact prior Makefile and twenty-one backend commands'
    return result


def _makefile_before_draft_contracts() -> str:
    # New outer inverse is mandatory before every unchanged legacy Make contract.
    return _original_makefile_before_draft_collection(_makefile_before_native_contracts())


def _original_dry_run_before_draft_collection(output: str) -> str:
    output = _original_dry_run_before_native_split(output)
    raw = _makefile_before_native_contracts()
    _original_makefile_before_draft_collection(raw)
    pythonpath = ':'.join(str(ROOT / path) for path in ('web/backend', 'packages/guarded-llm/src',
        'packages/cross-judge/src', 'packages/reject-aware-critic/src', 'packages/soc-pipeline/src'))
    backend = 'PYTHONPATH=' + pythonpath + ' python -m pytest'
    expected = [c.replace('$(BACKEND_PYTEST)', backend, 1) + '\n' for c in _make_recipe_commands(raw, 'verify-release') if c.startswith('cd web/backend ')]
    lines = output.splitlines(keepends=True)
    assert [line for line in lines if line.startswith('cd web/backend ')] == expected
    formal = expected[-1]
    assert lines.count(formal) == 1 and lines.count(expected[0]) == 1
    ignore = ' --ignore=tests/' + DRAFT_HISTORY_MODULE
    assert expected[0].endswith(ignore + ' -q\n')
    lines.remove(formal)
    return ''.join(lines).replace(expected[0], expected[0].replace(ignore + ' -q\n', ' -q\n', 1), 1)


OBSERVER_FRESH_MODULE = 'test_financial_limit_observer.py'


def _original_makefile_before_observer_backend(makefile: str) -> str:
    commands = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    assert len(commands) == 21, 'ordinary plus twenty fresh full modules required'
    formal = 'cd web/backend && $(BACKEND_PYTEST) tests/' + OBSERVER_FRESH_MODULE + ' -p no:logging -q'
    ignore = ' --ignore=tests/' + OBSERVER_FRESH_MODULE
    assert commands[-1] == formal and commands.count(formal) == 1
    assert commands[0].count(ignore) == 1 and commands[0].endswith(ignore + ' -q')
    prior = [commands[0].replace(ignore + ' -q', ' -q', 1), *commands[1:-1]]
    expanded = ''.join('\t' + c + '\n' for c in commands)
    assert makefile.count(expanded) == 1, 'observer process must extend the exact contiguous backend block'
    return makefile.replace(expanded, ''.join('\t' + c + '\n' for c in prior), 1)


def _original_makefile_before_b3_backend(makefile: str) -> str:
    makefile = _original_makefile_before_observer_backend(makefile)
    commands = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    assert len(commands) == 20, 'ordinary plus nineteen fresh full modules required'
    fresh = ['cd web/backend && $(BACKEND_PYTEST) tests/' + n + ' -p no:logging -q'
             for n in B3_FRESH_MAIN_MODULES]
    assert commands[-3:] == fresh
    extra = ''.join(' --ignore=tests/' + n for n in B3_FRESH_MAIN_MODULES)
    suffix = ' --ignore=tests/test_source_sec_access_lifecycle.py'
    assert commands[0].count(suffix + extra + ' -q') == 1
    assert all(commands[0].count(' --ignore=tests/' + n) == 1 for n in B3_FRESH_MAIN_MODULES)
    prior = [commands[0].replace(suffix + extra + ' -q', suffix + ' -q', 1), *commands[1:-3]]
    expanded = ''.join('\t' + c + '\n' for c in commands)
    assert makefile.count(expanded) == 1, 'B3 fresh processes must be one exact contiguous block'
    return makefile.replace(expanded, ''.join('\t' + c + '\n' for c in prior), 1)


def _original_makefile_before_gov_backend(makefile: str) -> str:
    """Reverse only the Gov lifecycle exclusion and full fresh process."""
    makefile = _original_makefile_before_b3_backend(makefile)
    prior_names = ('test_formal_main_admission.py', 'test_formal_main_source_supervisor.py',
                   'test_research_financial_import.py', 'test_formal_model_startup.py',
                   'acceptance/test_source_history_fixture_current15.py', 'test_research_financial_registries.py',
                   'test_research_source_origin_history.py', 'test_research_evidence_method_plan.py',
                   'test_research_evidence_method_native.py', 'test_plan_runtime_transport.py',
                   'test_research_native_browser_service.py', 'test_native_live_grant.py',
                   'test_formal_native_plan_supervisor.py', 'test_research_financial_execution_v2.py',
                   'test_research_financial_results_v2.py')
    names = prior_names + ('test_source_sec_access_lifecycle.py',)
    commands = ['cd web/backend && $(BACKEND_PYTEST)' + ''.join(' --ignore=tests/' + n for n in names) + ' -q']
    commands += ['cd web/backend && $(BACKEND_PYTEST) tests/' + n + ' -p no:logging -q' for n in names]
    expanded = ''.join('\t' + command + '\n' for command in commands)
    assert makefile.count(expanded) == 1, 'exact seventeen-process Gov Make block missing or duplicated'
    actual = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    assert actual == commands, 'Gov lifecycle must be the only new full Make backend consumer'
    prior = ['cd web/backend && $(BACKEND_PYTEST)' + ''.join(' --ignore=tests/' + n for n in prior_names) + ' -q']
    prior += ['cd web/backend && $(BACKEND_PYTEST) tests/' + n + ' -p no:logging -q' for n in prior_names]
    return makefile.replace(expanded, ''.join('\t' + command + '\n' for command in prior), 1)


def _original_makefile_before_native_financial_backend(makefile: str) -> str:
    """Reverse only the four exact native/financial whole-module consumers."""
    makefile = _original_makefile_before_gov_backend(makefile)
    prior_names=('test_formal_main_admission.py', 'test_formal_main_source_supervisor.py', 'test_research_financial_import.py', 'test_formal_model_startup.py', 'acceptance/test_source_history_fixture_current15.py', 'test_research_financial_registries.py', 'test_research_source_origin_history.py', 'test_research_evidence_method_plan.py', 'test_research_evidence_method_native.py', 'test_plan_runtime_transport.py', 'test_research_native_browser_service.py')
    names=prior_names+('test_native_live_grant.py', 'test_formal_native_plan_supervisor.py', 'test_research_financial_execution_v2.py', 'test_research_financial_results_v2.py')
    commands=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in names)+' -q']
    commands+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in names]
    expanded=''.join('\t'+command+'\n' for command in commands)
    assert makefile.count(expanded)==1, 'exact sixteen-process native financial Make block missing or duplicated'
    actual=[c for c in _make_recipe_commands(makefile,'verify-release') if c.startswith('cd web/backend ')]
    assert actual==commands, 'only exact native financial Make backend process split is allowed'
    prior=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in prior_names)+' -q']
    prior+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in prior_names]
    return makefile.replace(expanded,''.join('\t'+command+'\n' for command in prior),1)


def _original_makefile_before_evidence_backend(makefile: str) -> str:
    """Reverse only the five fixed Source/evidence/runtime Main consumers."""
    makefile = _original_makefile_before_native_financial_backend(makefile)
    prior_names=('test_formal_main_admission.py','test_formal_main_source_supervisor.py',
                 'test_research_financial_import.py','test_formal_model_startup.py',
                 'acceptance/test_source_history_fixture_current15.py','test_research_financial_registries.py')
    names=prior_names+('test_research_source_origin_history.py',
                       'test_research_evidence_method_plan.py','test_research_evidence_method_native.py',
                       'test_plan_runtime_transport.py','test_research_native_browser_service.py')
    commands=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in names)+' -q']
    commands+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in names]
    expanded=''.join('\t'+command+'\n' for command in commands)
    assert makefile.count(expanded)==1, 'exact twelve-process evidence Make backend block missing or duplicated'
    actual=[c for c in _make_recipe_commands(makefile,'verify-release') if c.startswith('cd web/backend ')]
    assert actual==commands, 'only the fixed evidence Make backend process split is allowed'
    prior=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in prior_names)+' -q']
    prior+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in prior_names]
    return makefile.replace(expanded,''.join('\t'+command+'\n' for command in prior),1)


def _original_makefile_before_fin2_backend(makefile: str) -> str:
    """Restore the reviewed 301 block only from the exact current15 extension."""
    makefile = _original_makefile_before_evidence_backend(makefile)
    original=('test_formal_main_admission.py','test_formal_main_source_supervisor.py',
              'test_research_financial_import.py','test_formal_model_startup.py')
    names=original+('acceptance/test_source_history_fixture_current15.py',
                    'test_research_financial_registries.py')
    commands=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in names)+' -q']
    commands+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in names]
    expanded=''.join('\t'+command+'\n' for command in commands)
    assert makefile.count(expanded)==1, 'exact seven-process FIN2 Make backend block missing or duplicated'
    actual=[c for c in _make_recipe_commands(makefile,'verify-release') if c.startswith('cd web/backend ')]
    assert actual==commands, 'only the fixed FIN2 Make backend process split is allowed'
    prior=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in original)+' -q']
    prior+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in original]
    return makefile.replace(expanded,''.join('\t'+command+'\n' for command in prior),1)


def _original_makefile_before_backend_isolation(makefile: str) -> str:
    makefile = _original_makefile_before_fin2_backend(makefile)
    names=('test_formal_main_admission.py','test_formal_main_source_supervisor.py',
           'test_research_financial_import.py','test_formal_model_startup.py')
    commands=['cd web/backend && $(BACKEND_PYTEST)'+''.join(' --ignore=tests/'+n for n in names)+' -q']
    commands+=['cd web/backend && $(BACKEND_PYTEST) tests/'+n+' -p no:logging -q' for n in names]
    expanded=''.join('\t'+command+'\n' for command in commands)
    assert makefile.count(expanded)==1, 'exact five-process Make backend block missing or duplicated'
    actual=[c for c in _make_recipe_commands(makefile,'verify-release') if c.startswith('cd web/backend ')]
    assert actual==commands, 'only the fixed Make backend process split is allowed'
    return makefile.replace(expanded,'\tcd web/backend && $(BACKEND_PYTEST) -q\n',1)


def _original_makefile_before_main_logging(makefile: str) -> str:
    makefile = _original_makefile_before_backend_isolation(makefile)
    makefile = _original_makefile_before_auth_bootstrap_browser(makefile)
    marker='-m "e2e and not requires_internet" -v'
    variable='BROWSER_CONTRACT_LIBRARY_AUTH_REPORTS_FAVORITES_TESTS'
    split=(f'\t$(PYTEST) tests/e2e/test_full_public_surface.py -p no:logging {marker}\n'
           f'\t$(PYTEST) $(filter-out tests/e2e/test_full_public_surface.py,$(filter tests/e2e/%,$({variable}))) {marker}\n')
    original=f'\t$(PYTEST) $(filter tests/e2e/%,$({variable})) {marker}\n'
    financial='test-financial-preview-browser-contract:\n\t$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n'
    assert makefile.count('-p no:logging')==2, 'only the two fixed Make processes may disable logging'
    assert makefile.count(split)==1 and makefile.count(financial)==1, 'exact Main Make split missing or duplicated'
    assert ('\t$(PYTEST) $(BROWSER_CONTRACT_DISCOVERY_CLASSES_PAPERS_TESTS) '+marker+'\n'+split) in makefile
    assert split+'\t$(PYTEST) $(filter web/tests/e2e/%,$('+variable+')) '+marker+'\n' in makefile
    assert financial+'test-retrieval-contract:' in makefile
    return makefile.replace(split,original,1).replace(financial,financial.replace(' -p no:logging',''),1)


def _original_makefile_before_evidence_method(makefile: str) -> str:
    additions = [
        "\tweb/frontend/tests/test_evidenceMethodPlan.js " + chr(92) + "\n",
        "EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS := " + chr(92) + "\n\tweb/tests/e2e/test_evidence_method_plan_browser.py\n\n",
        "test-evidence-method-browser-contract:\n\t$(BACKEND_PYTEST) $(EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n",
        '\t@echo "  test-evidence-method-browser-contract  Run all saved-evidence method browser cases"\n',
        "\t$(MAKE) test-evidence-method-browser-contract\n",
    ]
    assert additions[0] in makefile
    assert additions[1] + "PHASE_REAL_BROWSER_CONTRACT_TESTS :=" in makefile
    assert additions[2] + "test-retrieval-contract:" in makefile
    for addition in additions:
        assert makefile.count(addition) == 1, "evidence method Make consumer missing or duplicated"
        makefile = makefile.replace(addition, "", 1)
    phony = ".PHONY: test-evidence-method-browser-contract test-financial-preview-browser-contract "
    assert makefile.count(phony) == 1
    return makefile.replace(phony, ".PHONY: test-financial-preview-browser-contract ", 1)


def _original_makefile_before_header_scroll_node(makefile: str) -> str:
    """Validate the complete live Make contract, then reverse one exact entry."""
    _assert_make_release_closure(makefile)
    _assert_frontend_node_gate(_workflow_data(ROOT / '.github/workflows/ci.yml'), makefile)
    start_marker = 'FRONTEND_NODE_TESTS := ' + chr(92) + '\n'
    end_marker = '\nBROWSER_CONTRACT_SEARCH_ASK_ANALYZE_PHENOMENON_TESTS :='
    assert makefile.count(start_marker) == makefile.count(end_marker) == 1
    start = makefile.index(start_marker)
    end = makefile.index(end_marker, start)
    block = makefile[start:end]
    header = '\tweb/frontend/tests/test_headerScroll.js ' + chr(92) + '\n'
    exact = ('\tweb/frontend/tests/test_financialScenario.js ' + chr(92) + '\n'
             + header + '\tweb/frontend/tests/test_historyPrivacy.js ' + chr(92) + '\n')
    assert makefile.count('web/frontend/tests/test_headerScroll.js') == 1
    assert block.count(exact) == 1, 'header entry must occupy its one approved Make position'
    return makefile[:start] + block.replace(exact, exact.replace(header, '', 1), 1) + makefile[end:]


def _original_makefile_before_financial_scenario_browser(makefile: str) -> str:
    """Remove the exact FIN3 delta before applying the unchanged FIN2 chain."""
    makefile = _original_makefile_before_header_scroll_node(makefile)
    additions = [
        "\tweb/frontend/tests/test_financialScenario.js " + chr(92) + "\n",
        "FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS := " + chr(92) + "\n\tweb/tests/e2e/test_research_financial_scenario_browser.py\n\n",
        "test-financial-scenario-browser-contract:\n\t$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n",
        '\t@echo "  test-financial-scenario-browser-contract  Run all seven financial scenario actual Main browser cases"\n',
        "\t$(MAKE) test-financial-scenario-browser-contract\n",
    ]
    assert additions[1] + 'FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS :=' in makefile
    assert additions[2] + 'test-financial-registry-browser-contract:' in makefile
    for addition in additions:
        assert makefile.count(addition) == 1, 'financial scenario Make consumer missing or duplicated'
        makefile = makefile.replace(addition, '', 1)
    phony = '.PHONY: test-financial-scenario-browser-contract test-financial-registry-browser-contract '
    assert makefile.count(phony) == 1
    return makefile.replace(phony, '.PHONY: test-financial-registry-browser-contract ', 1)


def _original_makefile_before_financial_registry_browser(makefile: str) -> str:
    makefile = _original_makefile_before_financial_scenario_browser(makefile)
    additions = [
        "\tweb/frontend/tests/test_financialRegistry.js " + chr(92) + "\n",
        "FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS := " + chr(92) + "\n\tweb/tests/e2e/test_research_financial_registry_browser.py\n\n",
        "test-financial-registry-browser-contract:\n\t$(PYTEST) $(FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n",
        '\t@echo "  test-financial-registry-browser-contract  Run all financial registry save and account lifecycle browser cases"\n',
        "\t$(MAKE) test-financial-registry-browser-contract\n",
    ]
    assert additions[1] + 'EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS :=' in makefile
    assert additions[2] + 'test-evidence-method-browser-contract:' in makefile
    for addition in additions:
        assert makefile.count(addition) == 1, 'financial registry Make consumer missing or duplicated'
        makefile = makefile.replace(addition, '', 1)
    phony = '.PHONY: test-financial-registry-browser-contract test-evidence-method-browser-contract '
    assert makefile.count(phony) == 1
    return makefile.replace(phony, '.PHONY: test-evidence-method-browser-contract ', 1)


def _original_makefile_without_financial_preview(makefile: str) -> str:
    makefile = _original_makefile_before_financial_registry_browser(makefile)
    makefile = _original_makefile_before_evidence_method(makefile)
    makefile = _original_makefile_before_main_logging(makefile)
    # Only the exact approved new target/variable/help/phony token may differ.
    additions = [
        "FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS := " + chr(92) + "\n\tweb/tests/e2e/test_research_financial_preview_browser.py\n\n",
        "test-financial-preview-browser-contract:\n\t$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -v\n\n",
        '\t@echo "  test-financial-preview-browser-contract  Run all temporary financial CSV preview browser cases"\n',
    ]
    assert additions[0] + "PHASE_REAL_BROWSER_CONTRACT_TESTS :=" in makefile
    assert additions[1] + "test-retrieval-contract:" in makefile
    assert '\t@echo "  test-browser-contracts  Run the hard browser contract suite"\n' + additions[2] in makefile
    for addition in additions:
        assert makefile.count(addition) == 1, "financial Make addition missing or duplicated"
        makefile = makefile.replace(addition, "", 1)
    phony = ".PHONY: test-financial-preview-browser-contract test test-unit "
    assert makefile.count(phony) == 1 and "\n" + phony in makefile
    return makefile.replace(phony, ".PHONY: test test-unit ", 1)


def test_makefile_release_authority_is_independently_frozen() -> None:
    original = _original_makefile_without_financial_preview(_makefile_before_draft_contracts())
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b"
    )


def test_python_syntax_release_authority_is_independently_frozen() -> None:
    assert hashlib.sha256(
        (ROOT / "scripts/check_python_syntax.py").read_bytes()
    ).hexdigest() == (
        "904a8bf6ddbe9f614d67a3848da4330de5f612be643aeb5f92a4d4dc9444e2e7"
    )


def _original_dry_run_before_b3_backend(output: str) -> str:
    """Validate the three B3 consumers before removing only their full commands."""
    output = _original_dry_run_before_draft_collection(output)
    pythonpath = ":".join(str(ROOT / path) for path in (
        "web/backend", "packages/guarded-llm/src", "packages/cross-judge/src",
        "packages/reject-aware-critic/src", "packages/soc-pipeline/src",
    ))
    backend = "PYTHONPATH=" + pythonpath + " python -m pytest"
    prefix = "cd web/backend && " + backend
    observer_lines = output.splitlines(keepends=True)
    current_makefile = _makefile_before_draft_contracts()
    _original_makefile_before_b3_backend(current_makefile)
    expected = [command.replace("$(BACKEND_PYTEST)", backend, 1) + "\n"
                for command in _make_recipe_commands(current_makefile, "verify-release")
                if command.startswith("cd web/backend ")]
    actual = [line for line in observer_lines if line.startswith("cd web/backend ")]
    assert actual == expected, "actual dryrun must execute every exact backend command once"
    formal = prefix + " tests/" + OBSERVER_FRESH_MODULE + " -p no:logging -q\n"
    assert observer_lines.count(formal) == 1
    ignore = " --ignore=tests/" + OBSERVER_FRESH_MODULE
    assert expected[0].count(ignore) == 1 and expected[0].endswith(ignore + " -q\n")
    assert observer_lines.count(expected[0]) == 1
    observer_lines.remove(formal)
    output = "".join(observer_lines).replace(expected[0], expected[0].replace(ignore + " -q\n", " -q\n", 1), 1)
    lines = output.splitlines(keepends=True)
    ordinary = [line for line in lines if line.startswith(prefix + " --ignore=")]
    assert len(ordinary) == 1, "one exact ordinary backend command required"
    current_makefile = _makefile_before_draft_contracts()
    _original_makefile_before_b3_backend(current_makefile)
    makefile = _original_makefile_before_observer_backend(current_makefile)
    expected_ordinary = next(command for command in
        _make_recipe_commands(makefile, "verify-release")
        if command.startswith("cd web/backend && $(BACKEND_PYTEST) --ignore="))
    assert ordinary[0] == expected_ordinary.replace("$(BACKEND_PYTEST)", backend, 1) + "\n"
    ordinary_args = shlex.split(ordinary[0])
    for consumer in B3_FRESH_MAIN_MODULES:
        assert ordinary_args.count("--ignore=tests/" + consumer) == 1
        formal = prefix + " tests/" + consumer + " -p no:logging -q\n"
        assert lines.count(formal) == 1, "one complete B3 fresh command required"
        lines.remove(formal)
    return "".join(lines)


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
    output = _original_dry_run_before_b3_backend(completed.stdout)
    gov = next(line for line in output.splitlines() if "python -m pytest tests/test_source_sec_access_lifecycle.py" in line)
    assert output.splitlines().count(gov) == 1
    assert gov.endswith("python -m pytest tests/test_source_sec_access_lifecycle.py -p no:logging -q")
    assert gov.startswith("cd web/backend && PYTHONPATH=" + str(ROOT / "web/backend") + ":")
    assert output.count("--ignore=tests/test_source_sec_access_lifecycle.py") == 1
    assert "--ignore=tests/test_source_sec_access.py" not in output
    output = output.replace(gov + "\n", "", 1)
    scenario = next(line for line in output.splitlines() if "python -m pytest web/tests/e2e/test_research_financial_scenario_browser.py" in line)
    assert output.splitlines().count(scenario) == 1
    assert scenario.endswith("python -m pytest web/tests/e2e/test_research_financial_scenario_browser.py -p no:logging -v")
    assert scenario.startswith("PYTHONPATH=" + str(ROOT / "web/backend") + ":")
    output = output.replace(scenario + "\n", "", 1)
    assert output.count("python -m pytest") == 32
    assert output.count("python -m pytest web/tests/e2e/test_research_financial_registry_browser.py -p no:logging -v") == 1
    for consumer in (
        "test_native_live_grant.py", "test_formal_native_plan_supervisor.py",
        "test_research_financial_execution_v2.py", "test_research_financial_results_v2.py",
    ):
        assert output.count("python -m pytest tests/" + consumer + " -p no:logging -q") == 1
    assert "scripts/check_python_syntax.py" in output
    assert "scripts/openapi_artifact.py --check" in output
    assert "PY=python bash scripts/check_ts_types.sh" in output
    assert 'node "$test_file"' in output
    assert "pnpm lint && pnpm build" in output
    assert re.search(r"(?:^|\s)(?:true|false)(?:\s|$)", output) is None


@pytest.mark.parametrize("consumer", B3_FRESH_MAIN_MODULES)
def test_verify_release_actual_dry_run_rejects_b3_consumer_drift(consumer, monkeypatch):
    environment = os.environ.copy()
    for variable in ("MAKEFLAGS", "MAKEOVERRIDES", "PYTEST", "BACKEND_PYTEST", "OPENAPI_PY", "TYPES_PY"):
        environment.pop(variable, None)
    completed = subprocess.run(
        ["make", "-n", "--no-print-directory", "PY=python", "verify-release"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = completed.stdout
    formal = next(line + "\n" for line in output.splitlines()
                  if line.endswith("python -m pytest tests/" + consumer + " -p no:logging -q"))
    ignore = " --ignore=tests/" + consumer
    mutations = {
        "missing": output.replace(formal, "", 1),
        "duplicate": output.replace(formal, formal + formal, 1),
        "wrong_file": output.replace(formal, formal.replace(consumer, "test_source_document_raw.py"), 1),
        "selector": output.replace(formal, formal.rstrip("\n") + " -k smoke\n", 1),
        "logging": output.replace(formal, formal.replace(" -p no:logging", ""), 1),
        "missing_ignore": output.replace(ignore, "", 1),
        "duplicate_ignore": output.replace(ignore, ignore + ignore, 1),
        "ordinary_logging": output.replace("python -m pytest --ignore", "python -m pytest -p no:logging --ignore", 1),
        "pure_ignore": output.replace(ignore, ignore + " --ignore=tests/test_source_document_raw.py", 1),
        "extra": output.replace(formal, formal + formal.replace(consumer, "test_source_document_access.py"), 1),
    }
    for mutation, changed in mutations.items():
        assert changed != output, mutation
        result = subprocess.CompletedProcess(completed.args, 0, changed, "")
        with monkeypatch.context() as patch:
            patch.setattr(subprocess, "run", lambda *args, **kwargs: result)
            with pytest.raises(AssertionError):
                test_verify_release_dry_run_expands_real_test_and_build_commands()


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
    browser_tests.extend(_ci_matrix_paths(rows, "pytest_args_main", BROWSER_PATH_PATTERN))
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
    main_step = _named_ci_step(job, "Run actual Main public surface contract")
    node_step = _named_ci_step(job, "Run JavaScript trust contracts")
    conditional_steps = {
        step.get("name"): step["if"]
        for step in job["steps"]
        if isinstance(step, dict) and "if" in step
    }
    assert conditional_steps == {
        "Install complete backend runtime and verify imports": "matrix.shard == 'library-auth-reports-favorites'",
        "Run actual Main public surface contract": "matrix.pytest_args_main != ''",
        "Run isolated browser surface subgroup": "matrix.pytest_args_isolated != ''",
        "Run JavaScript trust contracts": "matrix.node_tests != ''",
    }
    install_tokens = _shell_tokens(install_step)
    assert install_tokens == [
        "python", "-m", "pip", "install",
        "pytest==9.0.3", "playwright==1.59.0", "pytest-playwright==0.7.2",
        "httpx==0.27.2",
        "fastapi==0.135.0", "pydantic==2.7.4", "starlette==1.3.1",
        "uvicorn[standard]==0.27.1", "PyJWT==2.15.1", "slowapi==0.1.9",
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
    assert main_step == {
        'name':'Run actual Main public surface contract',
        'if':"matrix.pytest_args_main != ''",
        'run':'pytest -p no:logging ${{ matrix.pytest_args_main }} -m "e2e and not requires_internet" -v',
    }
    assert job['steps'].index(main_step)==job['steps'].index(browser_step)+1==job['steps'].index(isolated_step)-1
    for row in rows:
        assert row['pytest_args_main']==('tests/e2e/test_full_public_surface.py web/tests/e2e/test_auth_login_bootstrap_privacy.py' if row['shard']=='library-auth-reports-favorites' else '')
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


def _frontend_node_ci_paths(value: dict) -> list[str]:
    """Count files only behind actual hard Node commands in the two CI jobs."""
    assert 'defaults' not in value, 'workflow defaults may not redirect Node execution'
    jobs = value['jobs']
    surface = jobs['browser-beta-surface-contract']
    identity = jobs['browser-identity-consent-contract']
    for name, job in (('browser-beta-surface-contract', surface),
                      ('browser-identity-consent-contract', identity)):
        _assert_hard_job_contract('.github/workflows/ci.yml', name, job)
        assert 'defaults' not in job, 'job defaults may not redirect Node execution'
    loop = _named_ci_step(surface, 'Run JavaScript trust contracts')
    assert set(loop) == {'name', 'if', 'shell', 'run'}
    assert loop['if'] == "matrix.node_tests != ''" and loop['shell'] == 'bash'
    assert _shell_tokens(loop) == [
        'set', '-euo', 'pipefail', 'for', 'test_file', 'in', '${{',
        'matrix.node_tests', '}};', 'do', 'node', '$test_file', 'done',
    ]
    paths = _ci_matrix_paths(_ci_matrix_rows(surface), 'node_tests', NODE_PATH_PATTERN)
    direct = _named_ci_step(identity, 'Verify header scroll JavaScript trust contract')
    assert set(direct) == {'name', 'run'}, 'direct Node consumer must execute at the repository root'
    tokens = _shell_tokens(direct)
    assert len(tokens) == 2 and tokens[0] == 'node', 'contract must run Node, not collect or echo paths'
    assert NODE_PATH_PATTERN.fullmatch(tokens[1])
    _assert_legal_repo_file(tokens[1])
    return paths + [tokens[1]]


def _assert_frontend_node_gate(value: dict, makefile: str) -> None:

    disk_tests = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "web/frontend/tests").glob("*.js")
    }
    make_tests = _make_path_list(makefile, "FRONTEND_NODE_TESTS")
    ci_tests = _frontend_node_ci_paths(value)

    assert len(make_tests) == len(set(make_tests)), "duplicate Make Node contract"
    assert len(ci_tests) == len(set(ci_tests)), "duplicate CI Node contract"
    assert set(make_tests) == disk_tests
    assert set(ci_tests) == disk_tests
    assert _make_recipe_commands(makefile, "test-frontend-node") == [
        '@set -eu; for test_file in $(FRONTEND_NODE_TESTS); do node "$$test_file"; done'
    ]


def test_frontend_node_gate_cannot_silently_skip_a_contract() -> None:
    _assert_frontend_node_gate(
        _workflow_data(ROOT / '.github/workflows/ci.yml'),
        _makefile_before_draft_contracts(),
    )


@pytest.mark.parametrize('mutation', [
    'missing_job', 'missing_step', 'echo', 'collect_only', 'shell_fallback',
    'soft_step', 'soft_job', 'conditional_job', 'step_cwd', 'job_cwd',
    'workflow_cwd', 'matrix_collect_only', 'matrix_cwd', 'duplicate_contract',
    'make_missing', 'make_duplicate', 'make_collect_only', 'make_soft', 'make_cwd', 'make_position',
])
def test_frontend_node_inventory_rejects_omitted_or_nonexecuting_consumers(mutation):
    value = _workflow_data(ROOT / '.github/workflows/ci.yml')
    jobs = value['jobs']; identity = jobs['browser-identity-consent-contract']
    direct = _named_ci_step(identity, 'Verify header scroll JavaScript trust contract')
    surface = jobs['browser-beta-surface-contract']
    loop = _named_ci_step(surface, 'Run JavaScript trust contracts')
    makefile = _makefile_before_draft_contracts()
    header = '\tweb/frontend/tests/test_headerScroll.js ' + chr(92) + '\n'
    if mutation == 'missing_job': jobs.pop('browser-identity-consent-contract')
    elif mutation == 'missing_step': identity['steps'].remove(direct)
    elif mutation == 'echo': direct['run'] = 'echo ' + direct['run']
    elif mutation == 'collect_only': direct['run'] = direct['run'].replace('node ', 'node --check ', 1)
    elif mutation == 'shell_fallback': direct['run'] += ' || true'
    elif mutation == 'soft_step': direct['continue-on-error'] = True
    elif mutation == 'soft_job': identity['continue-on-error'] = True
    elif mutation == 'conditional_job': identity['if'] = 'false'
    elif mutation == 'step_cwd': direct['working-directory'] = 'web/frontend'
    elif mutation == 'job_cwd': identity['defaults'] = {'run': {'working-directory': 'web/frontend'}}
    elif mutation == 'workflow_cwd': value['defaults'] = {'run': {'working-directory': 'web/frontend'}}
    elif mutation == 'matrix_collect_only': loop['run'] = loop['run'].replace('node ', 'node --check ', 1)
    elif mutation == 'matrix_cwd': loop['working-directory'] = 'web/frontend'
    elif mutation == 'duplicate_contract': _ci_matrix_rows(surface)[0]['node_tests'] += ' web/frontend/tests/test_headerScroll.js'
    elif mutation == 'make_missing': makefile = makefile.replace(header, '', 1)
    elif mutation == 'make_duplicate': makefile = makefile.replace(header, header + header, 1)
    elif mutation == 'make_collect_only': makefile = makefile.replace('do node "$$test_file"', 'do node --check "$$test_file"', 1)
    elif mutation == 'make_soft': makefile = makefile.replace('do node "$$test_file"; done', 'do node "$$test_file"; done || true', 1)
    elif mutation == 'make_cwd': makefile = makefile.replace('do node "$$test_file"', 'do cd web/frontend; node "$$test_file"', 1)
    else:
        makefile = makefile.replace(header, '', 1).replace(
            'FRONTEND_NODE_TESTS := ' + chr(92) + '\n',
            'FRONTEND_NODE_TESTS := ' + chr(92) + '\n' + header, 1)
    with pytest.raises((AssertionError, KeyError)):
        _assert_frontend_node_gate(value, makefile)
        original = _original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest() == 'd10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


def test_hard_browser_gate_has_one_make_and_ci_contract_list() -> None:
    makefile = _makefile_before_draft_contracts()
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
        ci_main = _ci_matrix_paths([row], "pytest_args_main", BROWSER_PATH_PATTERN)
        root_tests = [path for path in make_shard if path.startswith("tests/e2e/")]
        web_tests = [path for path in make_shard if path.startswith("web/tests/e2e/")]
        if root_tests and web_tests:
            assert ci_main == ['tests/e2e/test_full_public_surface.py', 'web/tests/e2e/test_auth_login_bootstrap_privacy.py']
            assert [p for p in ci_main if p.startswith('tests/e2e/')] + ci_primary == root_tests, f"mixed-root primary process: {shard}"
            assert ci_isolated == [p for p in web_tests if p not in ci_main], f"missing web isolation: {shard}"
        else:
            assert ci_primary == make_shard, f"unexpected primary split: {shard}"
            assert ci_main == [], f"unnecessary Main process: {shard}"
            assert ci_isolated == [], f"unnecessary isolated process: {shard}"
        ci_shard = ci_main + ci_primary + ci_isolated
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
        f"$(PYTEST) tests/e2e/test_full_public_surface.py web/tests/e2e/test_auth_login_bootstrap_privacy.py -p no:logging {marker}",
        "$(PYTEST) $(filter-out tests/e2e/test_full_public_surface.py,$(filter tests/e2e/%,$("
        f"{BROWSER_MAKE_SHARDS[2][1]}))) {marker}",
        "$(PYTEST) $(filter-out web/tests/e2e/test_auth_login_bootstrap_privacy.py,$(filter web/tests/e2e/%,$("
        f"{BROWSER_MAKE_SHARDS[2][1]}))) {marker}",
        f"$(PYTEST) $({BROWSER_MAKE_SHARDS[3][1]}) {marker}",
        "$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v",
    ]

    phase_tests = _make_path_list(makefile, "PHASE_REAL_BROWSER_CONTRACT_TESTS")
    assert phase_tests == [
        "web/tests/e2e/test_phase_auth_real.py",
        "web/tests/e2e/test_cookie_consent.py",
    ]
    phase_job = _ci_job("browser-identity-consent-contract")
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

    original = _original_makefile_before_evidence_method(
        _original_makefile_before_financial_registry_browser(makefile))
    assert _make_recipe_commands(_original_makefile_before_backend_isolation(original), "verify-release") == [
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
    assert '/auth/login?next=%2Fresearch' in chrome
    assert "登录以同步" in chrome
    assert "我的研究" in chrome
    assert "fetch('/api/auth/me'" in chrome
    assert "credential_conflict" in chrome and "确认账户" in chrome
    assert "site-header__account-cta" in chrome
    assert "site-menu-lang-toggle" in chrome
    assert "async def unified_auth_login" in backend


def test_primary_navigation_starts_at_the_real_workbench() -> None:
    chrome = (ROOT / "web/frontend/assets/js/site-chrome.js").read_text(encoding="utf-8")
    assert "{ href: '/research', key: 'nav.start_here', label: '开始研究' }" in chrome
    assert "{ href: '/research#my-research', key: 'nav.my_research'" in chrome
    assert "{ href: '/classes', key: 'nav.reference_clues'" in chrome
    assert "{ href: '/tools', key: 'nav.tools'" not in chrome
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
    index = (ROOT / "web/frontend/index.html").read_text(encoding="utf-8")
    assert "2–3 分钟" not in index
    assert 'id="start-research"' in index and 'href="/research"' in index
    assert 'method="post" action="/research"' in index
    assert 'data-legacy-ask-retired' in index
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


def _assert_nightly_has_only_reviewed_local_browser_admission(value):
    # JSON roundtrip makes YAML's legacy boolean `on` key deterministic.
    body = json.loads(json.dumps(value))
    job = body['jobs']['e2e-full']
    run = _named_ci_step(job, 'Run reviewed local browser contracts')
    assert set(run) == {'name', 'run'}
    assert _shell_tokens(run) == ['make', 'PY=python', 'test-browser-contracts']
    for key in ('OPENROUTER_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY', 'ANTHROPIC_API_KEY'):
        assert not _mapping_contains_key(body, key)
    job['steps'].remove(run)
    # The one approved execution step is removed; every other job, runtime,
    # trigger, dependency, deadline, load smoke and summary remains frozen.
    assert hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == 'ff7383650faf04a91c26ec48074d84841629b4e60b649b17232b949469882e59'


def test_nightly_removes_vendor_key_branch_in_favor_of_reviewed_local_contracts():
    _assert_nightly_has_only_reviewed_local_browser_admission(_workflow_data(ROOT / '.github/workflows/nightly.yml'))
    _assert_make_release_closure(_makefile_before_draft_contracts())


@pytest.mark.parametrize('mutation', ['vendor_step', 'vendor_job', 'has_key', 'scan_root',
    'scan_web', 'ignore_failure', 'skip_step', 'extra_paid_step', 'backend_changed', 'timeout'])
def test_nightly_rejects_reintroduced_paid_admission_or_removed_free_checks(mutation):
    value = _workflow_data(ROOT / '.github/workflows/nightly.yml')
    job = value['jobs']['e2e-full']
    step = _named_ci_step(job, 'Run reviewed local browser contracts')
    if mutation == 'vendor_step':step['env'] = {'OPENROUTER_API_KEY': '${{ secrets.OPENROUTER_API_KEY }}'}
    elif mutation == 'vendor_job':job['env'] = {'DEEPSEEK_API_KEY': '${{ secrets.DEEPSEEK_API_KEY }}'}
    elif mutation == 'has_key':step['run'] = 'if [ -n "$OPENROUTER_API_KEY" ]; then pytest tests/e2e; fi'
    elif mutation == 'scan_root':step['run'] = 'pytest tests/e2e -v -m "e2e and not requires_llm"'
    elif mutation == 'scan_web':step['run'] = 'pytest web/tests/e2e -v -m "not requires_llm"'
    elif mutation == 'ignore_failure':step['run'] += ' || true'
    elif mutation == 'skip_step':step['if'] = 'false'
    elif mutation == 'extra_paid_step':job['steps'].append({'name':'unregistered model path','run':'pytest web/tests/e2e/test_method_search.py'})
    elif mutation == 'backend_changed':value['jobs']['backend-full']['steps'][-1]['run'] = 'true'
    else:job['timeout-minutes'] = 60
    with pytest.raises(AssertionError):_assert_nightly_has_only_reviewed_local_browser_admission(value)


def test_nightly_make_command_resolves_only_existing_reviewed_browser_files():
    result = subprocess.run(
        ['make', '-n', 'PY=python', 'test-browser-contracts'], cwd=ROOT,
        env={'PATH': os.defpath}, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    commands = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(commands) == 7
    actual = BROWSER_PATH_PATTERN.findall(result.stdout)
    makefile = _makefile_before_draft_contracts()
    expected = [path for _, variable in BROWSER_MAKE_SHARDS for path in _make_path_list(makefile, variable)]
    expected += _make_path_list(makefile, 'PHASE_REAL_BROWSER_CONTRACT_TESTS')
    assert actual == expected and len(actual) == len(set(actual))
    assert all(Path(ROOT / path).is_file() for path in actual)
    assert all(token not in {'tests/e2e', 'web/tests/e2e'}
               for command in commands for token in shlex.split(command))



def test_financial_preview_browser_has_explicit_hard_make_admission() -> None:
    makefile = _makefile_before_draft_contracts()
    path = "web/tests/e2e/test_research_financial_preview_browser.py"
    assert _make_path_list(makefile, "FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS") == [path]
    assert _make_recipe_commands(makefile, "test-financial-preview-browser-contract") == [
        "$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v",
    ]
    job = _ci_job("browser-product-contract")
    steps = job["steps"]
    matches = [step for step in steps if step.get("name") == "Verify financial CSV readonly preview UI"]
    assert matches == [{"name": "Verify financial CSV readonly preview UI", "run": "make PY=python test-financial-preview-browser-contract"}]
    assert steps.index(matches[0]) == next(index for index, step in enumerate(steps)
        if step.get("name") == "Install complete backend runtime and verify imports") + 1
    assert _shell_tokens(matches[0]) == ["make", "PY=python", "test-financial-preview-browser-contract"]
    assert not (ROOT / "web/backend/tests/test_research_financial_preview_browser.py").exists()
    source = (ROOT / path).read_text(encoding="utf-8")
    assert "ROOT=Path(__file__).resolve().parents[3]" in source
    assert "from playwright.async_api import async_playwright,expect" in source
    assert "importorskip" not in source and "pytest.skip" not in source and "pytest.mark.skip" not in source
    assert len(_make_recipe_commands(makefile, "test-browser-contracts")) == 7


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "command", "old-command", "position"])
def test_financial_make_allowance_rejects_other_changes(mutation) -> None:
    makefile = _makefile_before_draft_contracts()
    if mutation == "missing": makefile = makefile.replace("test-financial-preview-browser-contract:\n", "", 1)
    elif mutation == "duplicate": makefile += "test-financial-preview-browser-contract:\n\t$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n"
    elif mutation == "command": makefile = makefile.replace("$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v", "true", 1)
    elif mutation == "position":
        target = "test-financial-preview-browser-contract:\n\t$(PYTEST) $(FINANCIAL_PREVIEW_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n"
        makefile = makefile.replace(target, "", 1) + target
    else: makefile = makefile.replace("$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v", "true", 1)
    with pytest.raises(AssertionError):
        original = _original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest() == "d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b"


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_position','other_target','old_selector','soft'])
def test_main_make_logging_allowance_reverses_only_fixed_processes(mutation) -> None:
    makefile=_makefile_before_draft_contracts()
    main='\t$(PYTEST) tests/e2e/test_full_public_surface.py web/tests/e2e/test_auth_login_bootstrap_privacy.py -p no:logging -m "e2e and not requires_internet" -v\n'
    if mutation=='missing':makefile=makefile.replace(main,main.replace(' -p no:logging',''),1)
    elif mutation=='duplicate':makefile=makefile.replace(main,main+main,1)
    elif mutation=='wrong_position':makefile=makefile.replace(main,'',1)+main
    elif mutation=='other_target':makefile=makefile.replace('$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v','$(PYTEST) $(PHASE_REAL_BROWSER_CONTRACT_TESTS) -p no:logging -v',1)
    elif mutation=='old_selector':makefile=makefile.replace('$(PYTEST) $(BROWSER_CONTRACT_SECONDARY_WHITESPACE_TESTS)','$(PYTEST) web/tests/e2e/test_whitespace.py',1)
    else:makefile=makefile.replace(main,'\t-'+main[1:],1)
    with pytest.raises(AssertionError):
        original=_original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest()=='d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


def test_auth_bootstrap_browser_is_one_complete_hard_Main_consumer():
    auth='web/tests/e2e/test_auth_login_bootstrap_privacy.py'
    rows=_ci_matrix_rows(_ci_job('browser-beta-surface-contract'))
    assert sum(_ci_matrix_paths([r],field,BROWSER_PATH_PATTERN).count(auth)
               for r in rows for field in ('pytest_args','pytest_args_main','pytest_args_isolated'))==1
    assert _ci_matrix_paths([rows[2]],'pytest_args_main',BROWSER_PATH_PATTERN)==['tests/e2e/test_full_public_surface.py',auth]
    source=(ROOT/auth).read_text();tree=ast.parse(source)
    assert {n.name for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}=={
        'test_unbound_login_is_inert_and_forced_native_POST_has_no_private_fields',
        'test_real_script_release_then_JSON_SMTP_verify_cookie_safe_return_and_single_click'}
    assert 'pytestmark = pytest.mark.e2e' in source
    assert all(token not in source for token in ('pytest.skip','pytest.xfail','pytest.importorskip','pytest.mark.skip','pytest.mark.xfail','requires_internet'))


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_process','marker'])
def test_auth_browser_Make_allowance_is_narrow(mutation):
    makefile=_makefile_before_draft_contracts();auth='web/tests/e2e/test_auth_login_bootstrap_privacy.py'
    if mutation=='missing':makefile=makefile.replace(' '+auth+' -p no:logging',' -p no:logging',1)
    elif mutation=='duplicate':makefile=makefile.replace(' '+auth+' -p no:logging',' '+auth+' '+auth+' -p no:logging',1)
    elif mutation=='wrong_process':makefile=makefile.replace(' '+auth+' -p no:logging',' -p no:logging',1).replace('$(PHASE_REAL_BROWSER_CONTRACT_TESTS) -v','$(PHASE_REAL_BROWSER_CONTRACT_TESTS) '+auth+' -v',1)
    else:makefile=makefile.replace(' '+auth+' -p no:logging',' '+auth+' -m smoke -p no:logging',1)
    with pytest.raises(AssertionError):
        original=_original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest()=='d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


@pytest.mark.parametrize('mutation',['missing','wrong_path','duplicate','ordinary_no_ignore','ordinary_no_logging','formal_logging','soft','position'])
def test_Make_backend_split_keeps_exact_full_files_and_hard_order(mutation):
    makefile=_makefile_before_draft_contracts()
    formal='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_source_supervisor.py -p no:logging -q\n'
    if mutation=='missing':makefile=makefile.replace(formal,'',1)
    elif mutation=='wrong_path':makefile=makefile.replace(formal,formal.replace('test_formal_main_source_supervisor.py','test_formal_search_profile.py'),1)
    elif mutation=='duplicate':makefile=makefile.replace(formal,formal+formal,1)
    elif mutation=='ordinary_no_ignore':makefile=makefile.replace(' --ignore=tests/test_formal_main_source_supervisor.py','',1)
    elif mutation=='ordinary_no_logging':makefile=makefile.replace('$(BACKEND_PYTEST) --ignore','$(BACKEND_PYTEST) -p no:logging --ignore',1)
    elif mutation=='formal_logging':makefile=makefile.replace(formal,formal.replace(' -p no:logging',''),1)
    elif mutation=='soft':makefile=makefile.replace(formal,'\t-'+formal[1:],1)
    else:makefile=makefile.replace(formal,'',1)+formal
    with pytest.raises(AssertionError):
        original=_original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest()=='d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


@pytest.mark.parametrize('consumer', ['acceptance/test_source_history_fixture_current15.py',
                                      'test_research_financial_registries.py'])
@pytest.mark.parametrize('mutation', ['missing', 'missing_ignore', 'logging', 'partial_file'])
def test_fin2_Make_backend_consumers_cannot_be_omitted_or_partially_run(consumer, mutation):
    makefile=_makefile_before_draft_contracts()
    formal='\tcd web/backend && $(BACKEND_PYTEST) tests/'+consumer+' -p no:logging -q\n'
    if mutation=='missing': makefile=makefile.replace(formal,'',1)
    elif mutation=='missing_ignore': makefile=makefile.replace(' --ignore=tests/'+consumer,'',1)
    elif mutation=='logging': makefile=makefile.replace(formal,formal.replace(' -p no:logging',''),1)
    else: makefile=makefile.replace(formal,formal.rstrip('\n')+' -k smoke\n',1)
    with pytest.raises(AssertionError):
        original=_original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest()=='d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


@pytest.mark.parametrize('consumer', ['test_research_source_origin_history.py',
                                      'test_research_evidence_method_plan.py',
                                      'test_research_evidence_method_native.py',
                                      'test_plan_runtime_transport.py',
                                      'test_research_native_browser_service.py',
                                      'test_native_live_grant.py',
                                      'test_formal_native_plan_supervisor.py',
                                      'test_research_financial_execution_v2.py',
                                      'test_research_financial_results_v2.py'])
@pytest.mark.parametrize('mutation', ['missing', 'missing_ignore', 'logging', 'partial_file'])
def test_evidence_Make_backend_consumers_cannot_be_omitted_or_partially_run(consumer, mutation):
    makefile=_makefile_before_draft_contracts()
    formal='\tcd web/backend && $(BACKEND_PYTEST) tests/'+consumer+' -p no:logging -q\n'
    if mutation=='missing': makefile=makefile.replace(formal,'',1)
    elif mutation=='missing_ignore': makefile=makefile.replace(' --ignore=tests/'+consumer,'',1)
    elif mutation=='logging': makefile=makefile.replace(formal,formal.replace(' -p no:logging',''),1)
    else: makefile=makefile.replace(formal,formal.rstrip('\n')+' -k smoke\n',1)
    with pytest.raises(AssertionError):
        original=_original_makefile_without_financial_preview(makefile)
        assert hashlib.sha256(original.encode()).hexdigest()=='d10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


def test_evidence_method_browser_is_one_complete_hard_consumer():
    makefile = _makefile_before_draft_contracts()
    node_path = 'web/frontend/tests/test_evidenceMethodPlan.js'
    browser_path = 'web/tests/e2e/test_evidence_method_plan_browser.py'
    assert _make_path_list(makefile, 'EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS') == [browser_path]
    assert _make_recipe_commands(makefile, 'test-evidence-method-browser-contract') == [
        '$(BACKEND_PYTEST) $(EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS) -p no:logging -v']
    assert _make_recipe_commands(makefile, 'verify-release').count('$(MAKE) test-evidence-method-browser-contract') == 1
    rows = _ci_matrix_rows(_ci_job('browser-beta-surface-contract'))
    assert _ci_matrix_paths(rows, 'node_tests', NODE_PATH_PATTERN).count(node_path) == 1
    job = _ci_job('browser-evidence-method-contract')
    assert set(job) == {'name', 'runs-on', 'timeout-minutes', 'steps'}
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 8
    product = _ci_job('browser-product-contract')
    assert job['steps'][:4] == product['steps'][:4]
    assert job['steps'][4:] == [{'name': 'Verify evidence method selection and saved results',
                               'run': 'make PY=python test-evidence-method-browser-contract'}]
    assert 'browser-evidence-method-contract' in _ci_job('release-gate-summary')['needs']
    assert node_path in _make_path_list(makefile, 'FRONTEND_NODE_TESTS')


@pytest.mark.parametrize('mutation', ['missing_target','duplicate_target','logging','soft','path','verify_release'])
def test_evidence_method_make_delta_rejects_weakened_or_missing_consumer(mutation):
    value = _makefile_before_draft_contracts()
    target = 'test-evidence-method-browser-contract:\n\t$(BACKEND_PYTEST) $(EVIDENCE_METHOD_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n'
    if mutation == 'missing_target': value = value.replace(target, '', 1)
    elif mutation == 'duplicate_target': value += target
    elif mutation == 'logging': value = value.replace(target, target.replace(' -p no:logging', ''), 1)
    elif mutation == 'soft': value = value.replace(target, target.replace('\t$(BACKEND_PYTEST)', '\t-$(BACKEND_PYTEST)'), 1)
    elif mutation == 'path': value = value.replace('web/tests/e2e/test_evidence_method_plan_browser.py', 'web/backend/tests/test_evidence_method_plan_browser.py', 1)
    else: value = value.replace('\t$(MAKE) test-evidence-method-browser-contract\n', '', 1)
    with pytest.raises(AssertionError): _original_makefile_without_financial_preview(value)


def test_financial_registry_browser_is_one_complete_hard_consumer():
    makefile = _makefile_before_draft_contracts()
    node_path = 'web/frontend/tests/test_financialRegistry.js'
    browser_path = 'web/tests/e2e/test_research_financial_registry_browser.py'
    assert _make_path_list(makefile, 'FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS') == [browser_path]
    assert _make_recipe_commands(makefile, 'test-financial-registry-browser-contract') == [
        '$(PYTEST) $(FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS) -p no:logging -v']
    assert _make_recipe_commands(makefile, 'verify-release').count('$(MAKE) test-financial-registry-browser-contract') == 1
    rows = _ci_matrix_rows(_ci_job('browser-beta-surface-contract'))
    assert _ci_matrix_paths(rows, 'node_tests', NODE_PATH_PATTERN).count(node_path) == 1
    job = _ci_job('browser-financial-registry-contract')
    assert set(job) == {'name', 'runs-on', 'timeout-minutes', 'steps'}
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 8
    product = _ci_job('browser-product-contract')
    assert job['steps'][:4] == product['steps'][:4]
    assert job['steps'][4:] == [{'name': 'Verify financial registry save selection and restored account lifecycle',
                               'run': 'make PY=python test-financial-registry-browser-contract'}]
    assert 'browser-financial-registry-contract' in _ci_job('release-gate-summary')['needs']
    assert node_path in _make_path_list(makefile, 'FRONTEND_NODE_TESTS')


@pytest.mark.parametrize('mutation', ['missing_target','duplicate_target','logging','soft','path','verify_release'])
def test_financial_registry_make_delta_rejects_weakened_or_missing_consumer(mutation):
    value = _makefile_before_draft_contracts()
    target = 'test-financial-registry-browser-contract:\n\t$(PYTEST) $(FINANCIAL_REGISTRY_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n'
    if mutation == 'missing_target': value = value.replace(target, '', 1)
    elif mutation == 'duplicate_target': value += target
    elif mutation == 'logging': value = value.replace(target, target.replace(' -p no:logging', ''), 1)
    elif mutation == 'soft': value = value.replace(target, target.replace('\t$(PYTEST)', '\t-$(PYTEST)'), 1)
    elif mutation == 'path': value = value.replace('web/tests/e2e/test_research_financial_registry_browser.py', 'web/backend/tests/test_research_financial_registry_browser.py', 1)
    else: value = value.replace('\t$(MAKE) test-financial-registry-browser-contract\n', '', 1)
    with pytest.raises(AssertionError): _original_makefile_without_financial_preview(value)


def test_financial_scenario_browser_is_one_complete_hard_consumer():
    makefile = _makefile_before_draft_contracts()
    node_path = 'web/frontend/tests/test_financialScenario.js'
    browser_path = 'web/tests/e2e/test_research_financial_scenario_browser.py'
    _assert_legal_repo_file(browser_path)
    _assert_legal_repo_file(node_path)
    assert _make_path_list(makefile, 'FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS') == [browser_path]
    assert _make_recipe_commands(makefile, 'test-financial-scenario-browser-contract') == [
        '$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS) -p no:logging -v']
    assert _make_recipe_commands(makefile, 'verify-release').count('$(MAKE) test-financial-scenario-browser-contract') == 1
    assert _make_path_list(makefile, 'FRONTEND_NODE_TESTS').count(node_path) == 1
    rows = _ci_matrix_rows(_ci_job('browser-beta-surface-contract'))
    assert _ci_matrix_paths(rows, 'node_tests', NODE_PATH_PATTERN).count(node_path) == 1
    assert next(row for row in rows if node_path in row['node_tests'].split())['shard'] == 'library-auth-reports-favorites'
    job = _ci_job('browser-financial-scenario-contract')
    assert set(job) == {'name', 'runs-on', 'timeout-minutes', 'steps'}
    assert job['runs-on'] == 'ubuntu-24.04' and job['timeout-minutes'] == 8
    assert job['steps'][:4] == _ci_job('browser-financial-registry-contract')['steps'][:4]
    assert job['steps'][4:] == [{'name': 'Verify all financial scenario actual Main browser cases',
                               'run': 'make PY=python test-financial-scenario-browser-contract'}]
    assert _ci_job('release-gate-summary')['needs'].count('browser-financial-scenario-contract') == 1
    module = ast.parse((ROOT / browser_path).read_text())
    cases = [node.name for node in module.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_')]
    assert len(cases) == 7 and all(name.startswith('test_fin3_actual_main_') for name in cases)


@pytest.mark.parametrize('mutation', [
    'missing_target', 'duplicate_target', 'logging', 'soft', 'partial_module',
    'shell', 'path', 'parent_namespace', 'verify_release', 'duplicate_release',
    'node_missing', 'node_duplicate', 'variable_duplicate', 'phony',
])
def test_financial_scenario_make_delta_rejects_weakened_or_missing_consumer(mutation):
    value = _makefile_before_draft_contracts()
    target = 'test-financial-scenario-browser-contract:\n\t$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS) -p no:logging -v\n\n'
    node = '\tweb/frontend/tests/test_financialScenario.js ' + chr(92) + '\n'
    release = '\t$(MAKE) test-financial-scenario-browser-contract\n'
    if mutation == 'missing_target': value = value.replace(target, '', 1)
    elif mutation == 'duplicate_target': value += target
    elif mutation == 'logging': value = value.replace(target, target.replace(' -p no:logging', ''), 1)
    elif mutation == 'soft': value = value.replace(target, target.replace('\t$(BACKEND_PYTEST)', '\t-$(BACKEND_PYTEST)'), 1)
    elif mutation == 'partial_module': value = value.replace(target, target.replace(' -v', ' -v -k smoke'), 1)
    elif mutation == 'shell': value = value.replace(target, target.replace(' -v', ' -v || true'), 1)
    elif mutation == 'path': value = value.replace('web/tests/e2e/test_research_financial_scenario_browser.py', 'web/backend/tests/test_research_financial_scenario_browser.py', 1)
    elif mutation == 'parent_namespace': value = value.replace(target, target.replace('$(BACKEND_PYTEST)', '$(PYTEST)'), 1)
    elif mutation == 'verify_release': value = value.replace(release, '', 1)
    elif mutation == 'duplicate_release': value = value.replace(release, release + release, 1)
    elif mutation == 'node_missing': value = value.replace(node, '', 1)
    elif mutation == 'node_duplicate': value = value.replace(node, node + node, 1)
    elif mutation == 'variable_duplicate': value += '\nFINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS += ignored.py\n'
    else: value = value.replace('.PHONY: test-financial-scenario-browser-contract ', '.PHONY: ', 1)
    with pytest.raises(AssertionError):
        original = _original_makefile_without_financial_preview(value)
        assert hashlib.sha256(original.encode()).hexdigest() == 'd10d21b2d90e07deb8f9219f663f511ea96d5532c7f97637213f67f51efb0b9b'


def test_gov_lifecycle_has_one_full_make_backend_process():
    makefile = _makefile_before_draft_contracts()
    legacy = _original_makefile_before_b3_backend(makefile)
    commands = [c for c in _make_recipe_commands(legacy, 'verify-release') if c.startswith('cd web/backend ')]
    assert len(commands) == 17
    assert commands[-1] == 'cd web/backend && $(BACKEND_PYTEST) tests/test_source_sec_access_lifecycle.py -p no:logging -q'
    assert commands[0].count(' --ignore=tests/test_source_sec_access_lifecycle.py') == 1
    assert ' -p no:logging' not in commands[0]
    assert 'test_source_sec_access.py' not in makefile
    prior = _original_makefile_before_gov_backend(makefile)
    assert len([c for c in _make_recipe_commands(prior, 'verify-release') if c.startswith('cd web/backend ')]) == 16
    assert 'test_source_sec_access_lifecycle.py' not in prior
    _assert_make_release_closure(makefile)


@pytest.mark.parametrize('mutation', [
    'missing', 'missing_ignore', 'duplicate', 'duplicate_ignore', 'partial_file',
    'formal_logging', 'ordinary_no_logging', 'order', 'soft', 'wrong_file',
    'pure_ignore', 'namespace',
])
def test_gov_lifecycle_make_delta_rejects_weakened_or_missing_consumer(mutation):
    value = _makefile_before_draft_contracts()
    formal = '\tcd web/backend && $(BACKEND_PYTEST) tests/test_source_sec_access_lifecycle.py -p no:logging -q\n'
    ignore = ' --ignore=tests/test_source_sec_access_lifecycle.py'
    if mutation == 'missing': value = value.replace(formal, '', 1)
    elif mutation == 'missing_ignore': value = value.replace(ignore, '', 1)
    elif mutation == 'duplicate': value = value.replace(formal, formal + formal, 1)
    elif mutation == 'duplicate_ignore': value = value.replace(ignore, ignore + ignore, 1)
    elif mutation == 'partial_file': value = value.replace(formal, formal.rstrip('\n') + ' -k smoke\n', 1)
    elif mutation == 'formal_logging': value = value.replace(formal, formal.replace(' -p no:logging', ''), 1)
    elif mutation == 'ordinary_no_logging': value = value.replace('$(BACKEND_PYTEST) --ignore', '$(BACKEND_PYTEST) -p no:logging --ignore', 1)
    elif mutation == 'order':
        previous = '\tcd web/backend && $(BACKEND_PYTEST) tests/test_research_financial_results_v2.py -p no:logging -q\n'
        assert previous + formal in value
        value = value.replace(previous + formal, formal + previous, 1)
    elif mutation == 'soft': value = value.replace(formal, formal.rstrip('\n') + ' || true\n', 1)
    elif mutation == 'wrong_file': value = value.replace(formal, formal.replace('test_source_sec_access_lifecycle.py', 'test_source_sec_access.py'), 1)
    elif mutation == 'pure_ignore': value = value.replace(ignore, ignore + ' --ignore=tests/test_source_sec_access.py', 1)
    else: value = value.replace(formal, formal.replace('$(BACKEND_PYTEST)', '$(PYTEST)'), 1)
    assert value != _makefile_before_draft_contracts()
    with pytest.raises(AssertionError): _original_makefile_before_gov_backend(value)


@pytest.mark.parametrize('consumer', B3_FRESH_MAIN_MODULES)
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'wrong_file', 'selector', 'logging', 'ignore_only', 'missing_ignore', 'duplicate_ignore', 'ordinary_logging', 'pure_ignore', 'extra'])
def test_b3_fresh_make_consumers_reject_drift(consumer, mutation):
    value = _makefile_before_draft_contracts()
    formal = '\tcd web/backend && $(BACKEND_PYTEST) tests/' + consumer + ' -p no:logging -q\n'
    ignore = ' --ignore=tests/' + consumer
    if mutation in ('missing', 'ignore_only'): value = value.replace(formal, '', 1)
    elif mutation == 'duplicate': value = value.replace(formal, formal + formal, 1)
    elif mutation == 'wrong_file': value = value.replace(formal, formal.replace(consumer, 'test_source_document_raw.py'), 1)
    elif mutation == 'selector': value = value.replace(formal, formal.rstrip('\n') + ' -k smoke\n', 1)
    elif mutation == 'logging': value = value.replace(formal, formal.replace(' -p no:logging', ''), 1)
    elif mutation == 'missing_ignore': value = value.replace(ignore, '', 1)
    elif mutation == 'duplicate_ignore': value = value.replace(ignore, ignore + ignore, 1)
    elif mutation == 'ordinary_logging': value = value.replace('$(BACKEND_PYTEST) --ignore', '$(BACKEND_PYTEST) -p no:logging --ignore', 1)
    elif mutation == 'pure_ignore': value = value.replace(ignore, ignore + ' --ignore=tests/test_source_document_raw.py', 1)
    else: value = value.replace(formal, formal + formal.replace(consumer, 'test_source_document_access.py'), 1)
    with pytest.raises(AssertionError): _original_makefile_without_financial_preview(value)


def test_b3_make_complete_module_inventory_stays_in_exactly_one_process():
    makefile = _makefile_before_draft_contracts()
    current_makefile = makefile
    makefile = _original_makefile_before_observer_backend(makefile)
    commands = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    assert len(commands) == 20
    fresh = [shlex.split(c)[4] for c in commands[1:]]
    assert len(fresh) == len(set(fresh)) == 19
    ignored = [t.removeprefix('--ignore=') for t in shlex.split(commands[0]) if t.startswith('--ignore=')]
    assert ignored == fresh
    inventory = {p.relative_to(ROOT / 'web/backend/tests').as_posix()
                 for p in (ROOT / 'web/backend/tests').rglob('test_*.py')}
    relative = [p.removeprefix('tests/') for p in fresh]
    assert set(relative) <= inventory
    ordinary = inventory - set(relative)
    assert all(int(name in ordinary) + relative.count(name) == 1 for name in inventory)
    for name in B3_FRESH_MAIN_MODULES:
        _assert_legal_repo_file('web/backend/tests/' + name)
    for name in ('test_source_document_raw.py', 'test_source_document_access.py',
                 'test_source_document_transport.py', 'test_financial_limit_observer.py'):
        assert 'tests/' + name not in ignored and 'tests/' + name not in fresh
        assert name in ordinary
    prior = _original_makefile_before_b3_backend(current_makefile)
    assert len([c for c in _make_recipe_commands(prior, 'verify-release') if c.startswith('cd web/backend ')]) == 17


def test_observer_whole_make_process_preserves_prior_nineteen_and_inventory():
    makefile = _makefile_before_draft_contracts()
    prior = _original_makefile_before_observer_backend(makefile)
    commands = [c for c in _make_recipe_commands(makefile, 'verify-release') if c.startswith('cd web/backend ')]
    old = [c for c in _make_recipe_commands(prior, 'verify-release') if c.startswith('cd web/backend ')]
    assert commands[1:-1] == old[1:] and len(old) == 20
    fresh = [shlex.split(c)[4].removeprefix('tests/') for c in commands[1:]]
    ignored = [t.removeprefix('--ignore=tests/') for t in shlex.split(commands[0]) if t.startswith('--ignore=')]
    assert fresh == ignored and len(set(fresh)) == 20
    inventory = {p.relative_to(ROOT / 'web/backend/tests').as_posix() for p in (ROOT / 'web/backend/tests').rglob('test_*.py')}
    assert set(fresh) <= inventory
    assert all(int(name not in fresh) + fresh.count(name) == 1 for name in inventory)
    _original_makefile_before_b3_backend(makefile)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'ignore_only', 'missing_ignore', 'duplicate_ignore', 'partial', 'logging'])
def test_observer_make_process_cannot_be_omitted_or_weakened(mutation):
    value = _makefile_before_draft_contracts()
    formal = '\tcd web/backend && $(BACKEND_PYTEST) tests/' + OBSERVER_FRESH_MODULE + ' -p no:logging -q\n'
    ignore = ' --ignore=tests/' + OBSERVER_FRESH_MODULE
    if mutation in ('missing', 'ignore_only'): value = value.replace(formal, '', 1)
    elif mutation == 'duplicate': value = value.replace(formal, formal + formal, 1)
    elif mutation == 'missing_ignore': value = value.replace(ignore, '', 1)
    elif mutation == 'duplicate_ignore': value = value.replace(ignore, ignore + ignore, 1)
    elif mutation == 'partial': value = value.replace(formal, formal.rstrip('\n') + ' -k smoke\n', 1)
    else: value = value.replace(formal, formal.replace(' -p no:logging', ''), 1)
    with pytest.raises(AssertionError): _original_makefile_before_observer_backend(value)


@pytest.mark.parametrize('mutation', ['echo_prefix', 'true_command', 'missing_ignore', 'missing', 'duplicate', 'partial', 'logging'])
def test_actual_observer_make_dryrun_inverse_rejects_nonexecution_and_drift(mutation):
    environment = os.environ.copy()
    for variable in ('MAKEFLAGS', 'MAKEOVERRIDES', 'PYTEST', 'BACKEND_PYTEST', 'OPENAPI_PY', 'TYPES_PY'):
        environment.pop(variable, None)
    completed = subprocess.run(['make', '-n', '--no-print-directory', 'PY=python', 'verify-release'],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=20, check=False)
    assert completed.returncode == 0
    output = completed.stdout
    formal = next(line for line in output.splitlines(keepends=True)
                  if ' tests/' + OBSERVER_FRESH_MODULE + ' -p no:logging -q\n' in line)
    if mutation == 'echo_prefix': changed = output.replace(formal, 'echo ' + formal, 1)
    elif mutation == 'true_command': changed = output.replace(formal, formal.replace('python -m pytest', 'true', 1), 1)
    elif mutation == 'missing_ignore': changed = output.replace(' --ignore=tests/' + OBSERVER_FRESH_MODULE, '', 1)
    elif mutation == 'missing': changed = output.replace(formal, '', 1)
    elif mutation == 'duplicate': changed = output.replace(formal, formal + formal, 1)
    elif mutation == 'partial': changed = output.replace(formal, formal.rstrip('\n') + ' -k smoke\n', 1)
    else: changed = output.replace(formal, formal.replace(' -p no:logging', '', 1), 1)
    assert changed != output
    with pytest.raises(AssertionError): _original_dry_run_before_b3_backend(changed)


def test_draft_history_make_outer_inverse_retains_every_prior_assertion_and_command():
    raw = _makefile_before_native_contracts()
    prior = _original_makefile_before_draft_collection(raw)
    assert len([c for c in _make_recipe_commands(raw, 'verify-release') if c.startswith('cd web/backend ')]) == 22
    assert len([c for c in _make_recipe_commands(prior, 'verify-release') if c.startswith('cd web/backend ')]) == 21
    _assert_make_release_closure(prior)
    _original_makefile_before_b3_backend(prior)


@pytest.mark.parametrize('mutation', ['missing','duplicate','ignore_only','missing_ignore','duplicate_ignore',
    'wrong_deselect','wrong_cwd_deselect','extra_deselect','parameter','partial_module','selector','logging','extra'])
def test_draft_history_make_collection_rejects_missing_or_weakened_work(mutation):
    raw = _makefile_before_native_contracts()
    path = 'tests/' + DRAFT_HISTORY_MODULE
    formal = '\tcd web/backend && $(BACKEND_PYTEST) ' + path + ' --deselect=web/backend/tests/' + DRAFT_HISTORY_MODULE + '::' + DRAFT_DEFERRED_FUNCTION + ' -p no:logging -q\n'
    ignore = ' --ignore=' + path
    if mutation in ('missing','ignore_only'): value = raw.replace(formal, '', 1)
    elif mutation == 'duplicate': value = raw.replace(formal, formal + formal, 1)
    elif mutation == 'missing_ignore': value = raw.replace(ignore, '', 1)
    elif mutation == 'duplicate_ignore': value = raw.replace(ignore, ignore + ignore, 1)
    elif mutation == 'wrong_deselect': value = raw.replace(formal, formal.replace(DRAFT_DEFERRED_FUNCTION, 'test_method_draft_public_models_exactly_match_runtime_contract'), 1)
    elif mutation == 'wrong_cwd_deselect': value = raw.replace(formal, formal.replace('--deselect=web/backend/tests/', '--deselect=tests/', 1), 1)
    elif mutation == 'extra_deselect': value = raw.replace(formal, formal.rstrip('\n') + ' --deselect=' + path + '::test_method_draft_public_models_exactly_match_runtime_contract\n', 1)
    elif mutation == 'parameter': value = raw.replace(formal, formal.replace(DRAFT_DEFERRED_FUNCTION, DRAFT_DEFERRED_FUNCTION + '[native]'), 1)
    elif mutation == 'partial_module': value = raw.replace(formal, formal.replace('$(BACKEND_PYTEST) ' + path + ' ', '$(BACKEND_PYTEST) ' + path + '::test_method_draft_public_models_exactly_match_runtime_contract ', 1), 1)
    elif mutation == 'selector': value = raw.replace(formal, formal.rstrip('\n') + ' -k smoke\n', 1)
    elif mutation == 'logging': value = raw.replace(formal, formal.replace(' -p no:logging', ''), 1)
    else: value = raw + '\n' + formal
    assert value != raw
    with pytest.raises(AssertionError): _original_makefile_before_draft_collection(value)


@pytest.mark.parametrize('mutation', ['echo_prefix','true_command','missing','duplicate','wrong_deselect','wrong_cwd_deselect','extra_deselect'])
def test_draft_history_actual_make_dryrun_rejects_nonexecution(mutation):
    environment = os.environ.copy()
    for variable in ('MAKEFLAGS','MAKEOVERRIDES','PYTEST','BACKEND_PYTEST','OPENAPI_PY','TYPES_PY'):
        environment.pop(variable, None)
    result = subprocess.run(['make','-n','--no-print-directory','PY=python','verify-release'],cwd=ROOT,env=environment,capture_output=True,text=True,timeout=20,check=False)
    assert result.returncode == 0
    output = result.stdout
    formal = next(line for line in output.splitlines(keepends=True) if '--deselect=web/backend/tests/' + DRAFT_HISTORY_MODULE in line)
    if mutation == 'echo_prefix': value = output.replace(formal, 'echo ' + formal, 1)
    elif mutation == 'true_command': value = output.replace(formal, formal.replace('python -m pytest','true',1),1)
    elif mutation == 'missing': value = output.replace(formal,'',1)
    elif mutation == 'duplicate': value = output.replace(formal,formal+formal,1)
    elif mutation == 'wrong_deselect': value = output.replace(formal,formal.replace(DRAFT_DEFERRED_FUNCTION,'test_method_draft_public_models_exactly_match_runtime_contract'),1)
    elif mutation == 'wrong_cwd_deselect': value = output.replace(formal,formal.replace('--deselect=web/backend/tests/','--deselect=tests/',1),1)
    else: value = output.replace(formal,formal.rstrip('\n')+' --deselect=tests/'+DRAFT_HISTORY_MODULE+'::test_method_draft_public_models_exactly_match_runtime_contract\n',1)
    assert value != output
    with pytest.raises(AssertionError): _original_dry_run_before_draft_collection(value)


def test_native_split_make_only_nineteen_ordinary_nodes_restore_53c_exactly():
    raw = _makefile_before_preowned_contracts()
    prior = _original_makefile_before_native_split(raw)
    assert len([c for c in _make_recipe_commands(raw,'verify-release') if c.startswith('cd web/backend ')]) == 22
    assert '--ignore=tests/test_research_native_plan.py' not in raw
    old = _original_makefile_before_draft_collection(prior)
    _assert_make_release_closure(old)


@pytest.mark.parametrize('mutation', ['missing','duplicate','wrong_relative','wrong_param','extra_pure','module_ignore','wrong_process','order','extra_deselect'])
def test_native_split_make_rejects_every_other_collection_change(mutation):
    raw = _makefile_before_preowned_contracts()
    token = ' --deselect="' + NATIVE_DEFERRED_NODES[0] + '"'
    if mutation == 'missing': value = raw.replace(token,'',1)
    elif mutation == 'duplicate': value = raw.replace(token,token+token,1)
    elif mutation == 'wrong_relative': value = raw.replace('--deselect="web/backend/tests/','--deselect="tests/',1)
    elif mutation == 'wrong_param': value = raw.replace('[ordinary]','[bogus]',1)
    elif mutation in ('extra_pure','extra_deselect'): value = raw.replace(_native_split_flags(),_native_split_flags()+' --deselect="'+NATIVE_PURE_NODES[0]+'"',1)
    elif mutation == 'module_ignore': value = raw.replace(_native_split_flags(),_native_split_flags()+' --ignore=tests/test_research_native_plan.py',1)
    elif mutation == 'wrong_process':
        value=raw.replace(token,'',1)
        formal='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q\n'
        value=value.replace(formal,formal.rstrip('\n')+token+'\n',1)
    else:
        second=' --deselect="'+NATIVE_DEFERRED_NODES[1]+'"'
        value=raw.replace(token,'',1).replace(second,second+token,1)
    assert value != raw
    with pytest.raises(AssertionError): _original_makefile_before_native_split(value)


@pytest.mark.parametrize('mutation', ['echo_prefix','missing','duplicate','wrong_relative','wrong_param','extra_pure'])
def test_native_split_actual_make_dryrun_rejects_nonexecution(mutation):
    environment = os.environ.copy()
    for variable in ('MAKEFLAGS','MAKEOVERRIDES','PYTEST','BACKEND_PYTEST','OPENAPI_PY','TYPES_PY'):environment.pop(variable,None)
    result=subprocess.run(['make','-n','--no-print-directory','PY=python','verify-release'],cwd=ROOT,env=environment,capture_output=True,text=True,timeout=20,check=False)
    assert result.returncode == 0
    output=result.stdout
    ordinary=next(line for line in output.splitlines(keepends=True) if ' --deselect="'+NATIVE_DEFERRED_NODES[0]+'"' in line)
    token=' --deselect="'+NATIVE_DEFERRED_NODES[0]+'"'
    if mutation == 'echo_prefix': value=output.replace(ordinary,'echo '+ordinary,1)
    elif mutation == 'missing':value=output.replace(token,'',1)
    elif mutation == 'duplicate':value=output.replace(token,token+token,1)
    elif mutation == 'wrong_relative':value=output.replace('--deselect="web/backend/tests/','--deselect="tests/',1)
    elif mutation == 'wrong_param':value=output.replace('[ordinary]','[bogus]',1)
    else:value=output.replace(token,token+' --deselect="'+NATIVE_PURE_NODES[0]+'"',1)
    assert value != output
    with pytest.raises(AssertionError):_original_dry_run_before_native_split(value)


def _changed_sanity_batch(value,mutation):
    value=copy.deepcopy(value);jobs=value['jobs'];a,b,fresh=(jobs[name] for name in SANITY_GROUP_IDS)
    sa,sb,sf=(_sanity_group_script(job) for job in (a,b,fresh))
    line=next(line for line in sa['run'].splitlines() if line.startswith('python -m pytest '))
    args=shlex.split(line);end=next(i for i in range(3,len(args)) if args[i].startswith('-'));paths=args[3:end]
    if mutation=='missing_file':sa['run']=sa['run'].replace(paths[0]+' ','',1)
    elif mutation=='duplicate_file':sa['run']=sa['run'].replace(paths[0],paths[0]+' '+paths[0],1)
    elif mutation=='boundary':
        first='tests/test_research_financial_admission_schemas.py';last='tests/test_research_deletion_schema_v8.py'
        sa['run']=sa['run'].replace(last,first,1);sb['run']=sb['run'].replace(first,last,1)
    elif mutation=='order':sa['run']=sa['run'].replace(paths[0]+' '+paths[1],paths[1]+' '+paths[0],1)
    elif mutation=='partial_module':sa['run']=sa['run'].replace(paths[0],paths[0]+'::test_partial',1)
    elif mutation=='fresh_in_ordinary':sa['run']=sa['run'].replace(paths[0],paths[0]+' tests/test_formal_main_admission.py',1)
    elif mutation=='merge_fresh':
        rows=[line for line in sf['run'].splitlines() if line.startswith('python -m pytest ')]
        sf['run']=sf['run'].replace(rows[0]+'\n'+rows[1],rows[0]+' '+rows[1],1)
    elif mutation=='logging':sf['run']=sf['run'].replace(' -p no:logging','',1)
    elif mutation=='wrong_cwd':sa['working-directory']='.'
    elif mutation=='wrong_defer':sa['run']=sa['run'].replace('--deselect="web/backend/tests/','--deselect="tests/',1)
    elif mutation=='extra_selector':sa['run']+=' -k smoke'
    elif mutation=='extra_ignore':sa['run']+=' --ignore=tests/test_research_native_plan.py'
    elif mutation=='setup':a['steps'].pop(0)
    elif mutation=='permission':a['permissions']={'contents':'write'}
    elif mutation=='timeout':a['timeout-minutes']=46
    elif mutation=='soft':a['continue-on-error']=True
    elif mutation=='missing_child':jobs.pop(SANITY_GROUP_IDS[0])
    elif mutation=='missing_needs':jobs['sanity-backend']['needs'].pop()
    elif mutation=='missing_always':jobs['sanity-backend'].pop('if')
    elif mutation=='required_name':jobs['sanity-backend']['name']='different-required-name'
    elif mutation=='aggregate_or':jobs['sanity-backend']['steps'][0]['run']='exit 0\n'
    else:jobs['sanity']['needs']=[SANITY_GROUP_IDS[0]]
    return value


def test_sanity_groups_fixed_inventory_setup_processes_and_required_gate():
    value=_sanity_source_before_preowned()
    restored=_workflow_before_sanity_groups(value)
    assert set(restored['jobs'])=={'sanity-backend','sanity'}
    assert restored['jobs']['sanity-backend']['name']=='sanity-backend'
    assert restored['jobs']['sanity']['needs']==['sanity-backend']


@pytest.mark.parametrize('mutation', ['missing_file','duplicate_file','boundary','order','partial_module','fresh_in_ordinary','merge_fresh','logging','wrong_cwd','wrong_defer','extra_selector','extra_ignore','setup','permission','timeout','soft','missing_child','missing_needs','missing_always','required_name','aggregate_or','sanity_bypass'])
def test_sanity_groups_reject_every_inventory_setup_or_strict_gate_drift(mutation):
    value=_sanity_source_before_preowned()
    changed=_changed_sanity_batch(value,mutation)
    assert changed!=value
    with pytest.raises(AssertionError):_workflow_before_sanity_groups(changed)


def test_preowned_six_make_whole_inverse_restores_current_all_prior_layers():
    value=_makefile_before_legacy_schema_contracts()
    prior=_original_makefile_before_preowned(value)
    prior=_original_makefile_before_native_split(prior)
    prior=_original_makefile_before_draft_collection(prior)
    _assert_make_release_closure(prior)


@pytest.mark.parametrize('mutation', ['missing','duplicate','wrong_relative','wrong_param','extra_pure','module_ignore','wrong_process','order'])
def test_preowned_six_make_rejects_wider_or_missing_deferral(mutation):
    value=_makefile_before_legacy_schema_contracts();token=' --deselect="'+PREOWNED_DEFERRED_NODES[0]+'"'
    if mutation=='missing':value=value.replace(token,'',1)
    elif mutation=='duplicate':value=value.replace(token,token+token,1)
    elif mutation=='wrong_relative':value=value.replace(' --deselect="web/backend/tests/test_research_native_preowned.py',' --deselect="tests/test_research_native_preowned.py',1)
    elif mutation=='wrong_param':value=value.replace(PREOWNED_DEFERRED_NODES[0],PREOWNED_DEFERRED_NODES[0]+'[unexpected]',1)
    elif mutation=='extra_pure':value=value.replace(_preowned_flags(),_preowned_flags()+' --deselect="'+NATIVE_PURE_NODES[0]+'"',1)
    elif mutation=='module_ignore':value=value.replace(_preowned_flags(),_preowned_flags()+' --ignore=tests/test_research_native_preowned.py',1)
    elif mutation=='wrong_process':
        value=value.replace(token,'',1)
        formal='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q\n'
        value=value.replace(formal,formal.rstrip('\n')+token+'\n',1)
    else:
        second=' --deselect="'+PREOWNED_DEFERRED_NODES[1]+'"'
        value=value.replace(token,'',1).replace(second,second+token,1)
    with pytest.raises(AssertionError):_original_makefile_before_preowned(value)


def test_legacy_schema_fourteen_unchanged_sources_and_exact_inventory():
    prefix='web/backend/tests/'
    native=ROOT/(prefix+'test_research_native_schema_v13.py')
    plan=ROOT/(prefix+'test_research_plan_schema_v12.py')
    assert hashlib.sha256(native.read_bytes()).hexdigest()==LEGACY_SCHEMA_ORIGINAL_SHA256
    assert hashlib.sha256(plan.read_bytes()).hexdigest()==LEGACY_SCHEMA_PLAN12_SHA256
    inventory=[]
    for path in (native,plan):
        for function in ast.parse(path.read_text()).body:
            if not isinstance(function,ast.FunctionDef) or not function.name.startswith('test_'):continue
            base=prefix+path.name+'::'+function.name
            if function.decorator_list:
                assert len(function.decorator_list)==1
                decorator=function.decorator_list[0]
                assert isinstance(decorator,ast.Call) and ast.unparse(decorator.func)=='pytest.mark.parametrize'
                assert ast.literal_eval(decorator.args[0])=='cut'
                cuts=ast.literal_eval(decorator.args[1])
                assert cuts==['journal','rebuild','resource','marker','before-commit','after-commit']
                inventory.extend(base+'['+cut+']' for cut in cuts)
            else:inventory.append(base)
    assert len(inventory)==15 and len(set(inventory))==15
    assert [node for node in inventory if node!=LEGACY_SCHEMA_REQUIRED_PRODUCER]==list(LEGACY_SCHEMA_DEFERRED_NODES)
    assert [node for node in inventory if node not in LEGACY_SCHEMA_DEFERRED_NODES]==[LEGACY_SCHEMA_REQUIRED_PRODUCER]

def test_legacy_schema_fourteen_make_inverse_retains_original_all_cases_and_golden():
    raw=(ROOT/'Makefile').read_text()
    restored=_original_makefile_before_legacy_schema(raw)
    assert restored==_makefile_before_legacy_schema_contracts()
    assert raw!=restored
    _assert_make_release_closure(_original_makefile_before_draft_collection(_original_makefile_before_native_split(_original_makefile_before_preowned(restored))))

@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_relative','wrong_cut','extra_producer','module_ignore','wrong_process','order'])
def test_legacy_schema_fourteen_make_rejects_wider_or_missing_defer(mutation):
    value=(ROOT/'Makefile').read_text();token=' --deselect="'+LEGACY_SCHEMA_DEFERRED_NODES[7]+'"'
    if mutation=='missing':value=value.replace(token,'',1)
    elif mutation=='duplicate':value=value.replace(token,token+token,1)
    elif mutation=='wrong_relative':value=value.replace(LEGACY_SCHEMA_DEFERRED_NODES[7],LEGACY_SCHEMA_DEFERRED_NODES[7].removeprefix('web/backend/'),1)
    elif mutation=='wrong_cut':value=value.replace(LEGACY_SCHEMA_DEFERRED_NODES[8],LEGACY_SCHEMA_DEFERRED_NODES[8]+'[unexpected]',1)
    elif mutation=='extra_producer':value=value.replace(_legacy_schema_flags(),_legacy_schema_flags()+' --deselect="'+LEGACY_SCHEMA_REQUIRED_PRODUCER+'"',1)
    elif mutation=='module_ignore':value=value.replace(_legacy_schema_flags(),_legacy_schema_flags()+' --ignore=tests/test_research_plan_schema_v12.py',1)
    elif mutation=='wrong_process':
        value=value.replace(token,'',1)
        line='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q\n'
        assert value.count(line)==1
        value=value.replace(line,line.rstrip('\n')+token+'\n',1)
    else:
        second=' --deselect="'+LEGACY_SCHEMA_DEFERRED_NODES[8]+'"'
        value=value.replace(token,'',1).replace(second,second+token,1)
    with pytest.raises(AssertionError):_original_makefile_before_legacy_schema(value)



def test_partial_runtime_original_source_and_five_parameters_retained():
    path=ROOT/'web/backend/tests/test_plan_runtime_transport.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==PARTIAL_RUNTIME_SOURCE_SHA256
    function=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name==PARTIAL_RUNTIME_BASE.split('::')[1])
    assert len(function.decorator_list)==1
    decorator=function.decorator_list[0]
    assert ast.unparse(decorator.func)=='pytest.mark.parametrize' and ast.literal_eval(decorator.args[0])=='fault'
    values=ast.literal_eval(decorator.args[1]);assert values==['want-read','want-write','failure','partial','pre-syscall']
    nodes=[PARTIAL_RUNTIME_BASE+'['+value+']' for value in values]
    assert [node for node in nodes if node!=PARTIAL_RUNTIME_NODE]==[PARTIAL_RUNTIME_BASE+'['+value+']' for value in ('want-read','want-write','failure','pre-syscall')]
    assert nodes.count(PARTIAL_RUNTIME_NODE)==1


@pytest.mark.parametrize('kind',['sanity','coverage'])
def test_partial_runtime_workflow_inverse_only_one_positive_parameter(kind):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text())
    restored=_workflow_before_partial_runtime(raw,kind+'.yml')
    assert restored!=raw
    assert hashlib.sha256(json.dumps(restored['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==PARTIAL_RUNTIME_PRIOR_JOBS_SHA256[kind+'.yml']
    assert _workflow_before_legacy_schema_fourteen(raw,kind+'.yml')==_workflow_source_before_legacy_schema(kind+'.yml')


@pytest.mark.parametrize('kind',['sanity','coverage'])
@pytest.mark.parametrize('mutation',['missing','duplicate','base','other_param','relative','extra_negative','module_ignore','wrong_process'])
def test_partial_runtime_workflow_rejects_wider_or_missing_parameter(kind,mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text())
    job=raw['jobs']['coverage' if kind=='coverage' else 'sanity-backend-fresh-1']
    title='Run coverage (split by suite, parallel files combined)' if kind=='coverage' else 'Leg 2 — web/backend pytest baseline'
    step=next(step for step in job['steps'] if step.get('name')==title);flag=_partial_runtime_flag()
    if mutation=='missing':step['run']=step['run'].replace(flag,'',1)
    elif mutation=='duplicate':step['run']=step['run'].replace(flag,flag+flag,1)
    elif mutation=='base':step['run']=step['run'].replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_BASE,1)
    elif mutation=='other_param':step['run']=step['run'].replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_BASE+'[want-read]',1)
    elif mutation=='relative':step['run']=step['run'].replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_NODE.removeprefix('web/backend/'),1)
    elif mutation=='extra_negative':step['run']=step['run'].replace(flag,flag+' --deselect="'+PARTIAL_RUNTIME_BASE+'[failure]"',1)
    elif mutation=='module_ignore':step['run']+=' --ignore=web/backend/tests/test_plan_runtime_transport.py'
    else:
        step['run']=step['run'].replace(flag,'',1)
        step['run']+='\npython -m pytest web/backend/tests/test_formal_main_admission.py'+flag+' -q\n'
    with pytest.raises(AssertionError):_workflow_before_partial_runtime(raw,kind+'.yml')



def test_partial_runtime_make_inverse_retains_original_all_other_cases():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_partial_runtime(raw)
    assert prior!=raw and hashlib.sha256(prior.encode()).hexdigest()==PARTIAL_RUNTIME_PRIOR_MAKE_SHA256
    restored=_original_makefile_before_legacy_schema(raw)
    restored=_original_makefile_before_preowned(restored)
    restored=_original_makefile_before_native_split(restored)
    restored=_original_makefile_before_draft_collection(restored)
    _assert_make_release_closure(restored)


@pytest.mark.parametrize('mutation',['missing','duplicate','base','other_param','relative','extra_negative','module_ignore','wrong_process'])
def test_partial_runtime_make_rejects_wider_or_missing_parameter(mutation):
    raw=(ROOT/'Makefile').read_text();flag=_partial_runtime_flag()
    if mutation=='missing':raw=raw.replace(flag,'',1)
    elif mutation=='duplicate':raw=raw.replace(flag,flag+flag,1)
    elif mutation=='base':raw=raw.replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_BASE,1)
    elif mutation=='other_param':raw=raw.replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_BASE+'[want-write]',1)
    elif mutation=='relative':raw=raw.replace(PARTIAL_RUNTIME_NODE,PARTIAL_RUNTIME_NODE.removeprefix('web/backend/'),1)
    elif mutation=='extra_negative':raw=raw.replace(flag,flag+' --deselect="'+PARTIAL_RUNTIME_BASE+'[failure]"',1)
    elif mutation=='module_ignore':raw=raw.replace(flag,flag+' --ignore=tests/test_plan_runtime_transport.py',1)
    else:
        raw=raw.replace(flag,'',1)
        wrong='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q\n'
        assert raw.count(wrong)==1;raw=raw.replace(wrong,wrong.rstrip('\n')+flag+'\n',1)
    with pytest.raises(AssertionError):_makefile_before_partial_runtime(raw)




def test_native_late_three_source_bodies_and_kept_cancel_remain_exact():
    inventory=[]
    names={'test_plan_runtime_transport.py':'test_actual_late_return_original_credential_books_fee_without_restoring_body',
           'test_research_evidence_method_native.py':'test_actual_http_stop_after_owned_return_keeps_original_fee_without_late_body'}
    for filename,name in names.items():
        path=ROOT/'web/backend/tests'/filename
        assert hashlib.sha256(path.read_bytes()).hexdigest()==NATIVE_LATE_SOURCE_SHA256[filename]
        function=next(node for node in ast.parse(path.read_text()).body if isinstance(node,ast.FunctionDef) and node.name==name)
        assert len(function.decorator_list)==1
        decorator=function.decorator_list[0]
        assert ast.unparse(decorator.func)=='pytest.mark.parametrize' and ast.literal_eval(decorator.args[0])=='action'
        assert ast.literal_eval(decorator.args[1])==['cancel','delete']
        inventory.extend('web/backend/tests/'+filename+'::'+name+'['+action+']' for action in ('cancel','delete'))
    assert len(inventory)==4 and len(set(inventory))==4
    assert [node for node in inventory if node in NATIVE_LATE_THREE_NODES]==list(NATIVE_LATE_THREE_NODES)
    assert [node for node in inventory if node not in NATIVE_LATE_THREE_NODES]==[NATIVE_LATE_THREE_NODES[2].replace('[delete]','[cancel]')]


@pytest.mark.parametrize('kind',['sanity','coverage'])
def test_native_late_three_workflow_inverse_returns_complete_prior_jobs(kind):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text())
    restored=_workflow_before_native_late_three(raw,kind+'.yml')
    assert restored!=raw
    assert hashlib.sha256(json.dumps(restored['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==NATIVE_LATE_PRIOR_JOBS_SHA256[kind+'.yml']
    # The previous strict bridge still validates the current complete chain.
    assert _workflow_before_partial_runtime(raw,kind+'.yml')!=restored


@pytest.mark.parametrize('kind',['sanity','coverage'])
@pytest.mark.parametrize('mutation',['missing','duplicate','function_base','kept_cancel','relative','module_ignore','wrong_process','order'])
def test_native_late_three_workflow_rejects_nonexact_collection(kind,mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text())
    job=raw['jobs']['coverage' if kind=='coverage' else 'sanity-backend-fresh-1']
    title='Run coverage (split by suite, parallel files combined)' if kind=='coverage' else 'Leg 2 — web/backend pytest baseline'
    step=next(step for step in job['steps'] if step.get('name')==title)
    node=NATIVE_LATE_THREE_NODES[2];token=' --deselect="'+node+'"'
    if mutation=='missing':step['run']=step['run'].replace(token,'',1)
    elif mutation=='duplicate':step['run']=step['run'].replace(token,token+token,1)
    elif mutation=='function_base':step['run']=step['run'].replace(node,node.removesuffix('[delete]'),1)
    elif mutation=='kept_cancel':step['run']=step['run'].replace(token,token+' --deselect="'+node.replace('[delete]','[cancel]')+'"',1)
    elif mutation=='relative':step['run']=step['run'].replace(node,node.removeprefix('web/backend/'),1)
    elif mutation=='module_ignore':step['run']+=' --ignore=web/backend/tests/test_research_evidence_method_native.py'
    elif mutation=='wrong_process':
        step['run']=step['run'].replace(token,'',1);step['run']+='\npython -m pytest web/backend/tests/test_formal_main_admission.py'+token+' -q\n'
    else:
        a=' --deselect="'+NATIVE_LATE_THREE_NODES[0]+'"';b=' --deselect="'+NATIVE_LATE_THREE_NODES[1]+'"'
        step['run']=step['run'].replace(a+b,b+a,1)
    with pytest.raises(AssertionError):_workflow_before_native_late_three(raw,kind+'.yml')



def test_native_late_three_make_inverse_keeps_exact_previous_full_recipe():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_native_late_three(raw)
    assert prior!=raw and hashlib.sha256(prior.encode()).hexdigest()==NATIVE_LATE_PRIOR_MAKE_SHA256
    _assert_make_release_closure(_original_makefile_before_draft_collection(_original_makefile_before_native_split(_original_makefile_before_preowned(_original_makefile_before_legacy_schema(raw)))))


@pytest.mark.parametrize('mutation',['missing','duplicate','function_base','kept_cancel','relative','module_ignore','wrong_process','order'])
def test_native_late_three_make_rejects_nonexact_collection(mutation):
    raw=(ROOT/'Makefile').read_text();node=NATIVE_LATE_THREE_NODES[2];token=' --deselect="'+node+'"'
    if mutation=='missing':raw=raw.replace(token,'',1)
    elif mutation=='duplicate':raw=raw.replace(token,token+token,1)
    elif mutation=='function_base':raw=raw.replace(node,node.removesuffix('[delete]'),1)
    elif mutation=='kept_cancel':raw=raw.replace(token,token+' --deselect="'+node.replace('[delete]','[cancel]')+'"',1)
    elif mutation=='relative':raw=raw.replace(node,node.removeprefix('web/backend/'),1)
    elif mutation=='module_ignore':raw=raw.replace(token,token+' --ignore=tests/test_research_evidence_method_native.py',1)
    elif mutation=='wrong_process':
        raw=raw.replace(token,'',1)
        wrong='\tcd web/backend && $(BACKEND_PYTEST) tests/test_formal_main_admission.py -p no:logging -q\n'
        assert raw.count(wrong)==1;raw=raw.replace(wrong,wrong.rstrip('\n')+token+'\n',1)
    else:
        a=' --deselect="'+NATIVE_LATE_THREE_NODES[0]+'"';b=' --deselect="'+NATIVE_LATE_THREE_NODES[1]+'"';raw=raw.replace(a+b,b+a,1)
    with pytest.raises(AssertionError):_makefile_before_native_late_three(raw)


def test_fin3_capacity_exact_one_preserves_original_source_and_six_current_cases():
    path=ROOT/FIN3_CAPACITY_NODE.split('::')[0]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==FIN3_CAPACITY_SOURCE_SHA256
    module=ast.parse(path.read_text())
    cases=[x.name for x in module.body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name.startswith('test_')]
    excluded=FIN3_CAPACITY_NODE.split('::')[1]
    assert len(cases)==7 and cases.count(excluded)==1
    assert tuple(name for name in cases if name!=excluded)==FIN3_CAPACITY_OTHER_CASES
    raw=(ROOT/'Makefile').read_text()
    prior=_makefile_before_fin3_capacity(raw)
    assert prior!=raw and hashlib.sha256(prior.encode()).hexdigest()==FIN3_CAPACITY_PRIOR_MAKE_SHA256
    # Feed original current raw through the complete old chain, never twice-normalized data.
    assert _makefile_before_draft_contracts()


@pytest.mark.parametrize('mutation',['missing','duplicate','whole_module','current_case','wrong_path','partial_filter','soft','other_recipe','release_missing'])
def test_fin3_capacity_make_rejects_any_nonexact_scope(mutation):
    raw=(ROOT/'Makefile').read_text();flag=_fin3_capacity_flag()
    if mutation=='missing':raw=raw.replace(flag,'',1)
    elif mutation=='duplicate':raw=raw.replace(flag,flag+flag,1)
    elif mutation=='whole_module':raw=raw.replace(flag,' --deselect="'+FIN3_CAPACITY_SELECTOR.split('::')[0]+'"',1)
    elif mutation=='current_case':raw=raw.replace(FIN3_CAPACITY_SELECTOR,FIN3_CAPACITY_SELECTOR.split('::')[0]+'::'+FIN3_CAPACITY_OTHER_CASES[0],1)
    elif mutation=='wrong_path':raw=raw.replace(FIN3_CAPACITY_SELECTOR,FIN3_CAPACITY_NODE,1)
    elif mutation=='partial_filter':raw=raw.replace(flag,flag+' -k smoke',1)
    elif mutation=='soft':raw=raw.replace('\t$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS)','\t-$(BACKEND_PYTEST) $(FINANCIAL_SCENARIO_BROWSER_CONTRACT_TESTS)',1)
    elif mutation=='other_recipe':raw=raw.replace('test-financial-registry-browser-contract:','test-financial-registry-browser-contractX:',1)
    else:raw=raw.replace('\t$(MAKE) test-financial-scenario-browser-contract\n','',1)
    with pytest.raises(AssertionError):_makefile_before_fin3_capacity(raw)


def test_authority_retry_exact_one_preserves_source_and_current_safety_cases():
    path=ROOT/AUTHORITY_RETRY_NODE.split('::')[0]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==AUTHORITY_RETRY_SOURCE_SHA256
    module=ast.parse(path.read_text());name=AUTHORITY_RETRY_NODE.split('::')[1]
    fn=next(x for x in module.body if isinstance(x,ast.FunctionDef) and x.name==name)
    assert not fn.decorator_list
    cases=[x.name for x in module.body if isinstance(x,ast.FunctionDef) and x.name.startswith('test_')]
    assert cases.count(name)==1 and 'test_static_pages_are_actual_repo_bytes_and_canonical_bridge_has_no_owner_cookie' in cases
    assert 'test_uncertain_failed_installation_keeps_references_and_private_root' in cases


@pytest.mark.parametrize('kind',['sanity','coverage'])
def test_authority_retry_workflow_exact_inverse_returns_previous_all_jobs(kind):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text());prior=_workflow_before_authority_retry(raw,kind+'.yml')
    assert prior!=raw
    assert hashlib.sha256(json.dumps(prior['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==AUTHORITY_RETRY_PRIOR_JOBS_SHA256[kind+'.yml']
    assert _workflow_before_native_late_three(raw,kind+'.yml')!=prior


@pytest.mark.parametrize('kind',['sanity','coverage'])
@pytest.mark.parametrize('mutation',['missing','duplicate','whole_module','wrong_path','current_case','partial','other_job'])
def test_authority_retry_workflow_rejects_any_wider_or_missing_scope(kind,mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows'/(kind+'.yml')).read_text());job=raw['jobs']['sanity-backend-fresh-1' if kind=='sanity' else 'coverage']
    title='Leg 2 — web/backend pytest baseline' if kind=='sanity' else 'Run coverage (split by suite, parallel files combined)'
    step=next(x for x in job['steps'] if x.get('name')==title);flag=_authority_retry_flag()
    if mutation=='missing':step['run']=step['run'].replace(flag,'',1)
    elif mutation=='duplicate':step['run']=step['run'].replace(flag,flag+flag,1)
    elif mutation=='whole_module':step['run']=step['run'].replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.split('::')[0],1)
    elif mutation=='wrong_path':step['run']=step['run'].replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.replace('web/backend/',''),1)
    elif mutation=='current_case':step['run']=step['run'].replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.split('::')[0]+'::test_static_pages_are_actual_repo_bytes_and_canonical_bridge_has_no_owner_cookie',1)
    elif mutation=='partial':step['run']=step['run'].replace(flag,flag+' -k smoke',1)
    else:next(iter(raw['jobs'].values()))['timeout-minutes']=999
    with pytest.raises(AssertionError):_workflow_before_authority_retry(raw,kind+'.yml')


def test_authority_retry_make_inverse_restores_full_prior_and_legacy_chain():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_authority_retry(raw)
    assert prior!=raw and hashlib.sha256(prior.encode()).hexdigest()==AUTHORITY_RETRY_PRIOR_MAKE_SHA256
    assert _makefile_before_draft_contracts()


@pytest.mark.parametrize('mutation',['missing','duplicate','whole_module','wrong_path','current_case','partial','other_recipe'])
def test_authority_retry_make_rejects_any_nonexact_collection(mutation):
    raw=(ROOT/'Makefile').read_text();flag=_authority_retry_flag()
    if mutation=='missing':raw=raw.replace(flag,'',1)
    elif mutation=='duplicate':raw=raw.replace(flag,flag+flag,1)
    elif mutation=='whole_module':raw=raw.replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.split('::')[0],1)
    elif mutation=='wrong_path':raw=raw.replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.replace('web/backend/',''),1)
    elif mutation=='current_case':raw=raw.replace(AUTHORITY_RETRY_NODE,AUTHORITY_RETRY_NODE.split('::')[0]+'::test_static_pages_are_actual_repo_bytes_and_canonical_bridge_has_no_owner_cookie',1)
    elif mutation=='partial':raw=raw.replace(flag,flag+' -k smoke',1)
    else:raw=raw.replace('test-financial-registry-browser-contract:','test-financial-registry-browser-contractX:',1)
    with pytest.raises(AssertionError):_makefile_before_authority_retry(raw)


def test_ordinary_b_parts_exact_inverse_keeps_original_all_jobs_and_group_order():
    raw=yaml.safe_load((ROOT/'.github/workflows/sanity.yml').read_text());prior=_workflow_before_ordinary_b_parts(raw,'sanity.yml')
    assert prior!=raw and hashlib.sha256(json.dumps(prior['jobs'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==ORDINARY_B_PART_PRIOR_JOBS_SHA256
    assert _workflow_before_authority_retry(raw,'sanity.yml')!=prior


@pytest.mark.parametrize('mutation',['missing_child','duplicate_module','missing_module','wrong_order','boundary','partial_filter','ignore','flags','cwd','runner','timeout','setup','permission','soft','missing_need','missing_always','aggregate_or','wrong_name','downstream_bypass'])
def test_ordinary_b_parts_reject_any_collection_setup_or_aggregate_drift(mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows/sanity.yml').read_text());jobs=raw['jobs'];first=jobs[ORDINARY_B_PART_IDS[0]];step=next(s for s in first['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline');path=ORDINARY_B_PART_MODULES[0][0]
    if mutation=='missing_child':jobs.pop(ORDINARY_B_PART_IDS[0])
    elif mutation=='duplicate_module':step['run']=step['run'].replace(path,path+' '+path,1)
    elif mutation=='missing_module':step['run']=step['run'].replace(path+' ','',1)
    elif mutation=='wrong_order':
        other=ORDINARY_B_PART_MODULES[0][1];step['run']=step['run'].replace(path+' '+other,other+' '+path,1)
    elif mutation=='boundary':
        x=ORDINARY_B_PART_MODULES[0][-1];y=ORDINARY_B_PART_MODULES[1][0];step['run']=step['run'].replace(x,y,1)
    elif mutation=='partial_filter':step['run']+=' -k smoke'
    elif mutation=='ignore':step['run']+=' --ignore='+path
    elif mutation=='flags':step['run']=step['run'].replace(' -x ',' ',1)
    elif mutation=='cwd':step['working-directory']='.'
    elif mutation=='runner':first['runs-on']='macos-latest'
    elif mutation=='timeout':first['timeout-minutes']=46
    elif mutation=='setup':first['steps'][1]['with']['python-version']='3.12'
    elif mutation=='permission':raw['permissions']={'contents':'write'}
    elif mutation=='soft':first['continue-on-error']=True
    elif mutation=='missing_need':jobs['sanity-backend-ordinary-b']['needs'].pop()
    elif mutation=='missing_always':jobs['sanity-backend-ordinary-b'].pop('if')
    elif mutation=='aggregate_or':jobs['sanity-backend-ordinary-b']['steps'][0]['run']+='true\n'
    elif mutation=='wrong_name':jobs['sanity-backend-ordinary-b']['name']='optional-b'
    else:jobs['sanity-backend']['needs']=['sanity-backend-ordinary-a','sanity-backend-fresh']
    with pytest.raises((AssertionError,KeyError)):_workflow_before_ordinary_b_parts(raw,'sanity.yml')


@pytest.mark.parametrize('child',[0,1,2])
@pytest.mark.parametrize('status',['failure','cancelled','skipped','',None,'unknown'])
def test_ordinary_b_parts_actual_strict_aggregate_rejects_each_non_success(tmp_path,child,status):
    values=['success']*3;values[child]=status;env={'PATH':os.environ.get('PATH','/usr/bin:/bin')}
    for name,value in zip(('BACKEND_B1_RESULT','BACKEND_B2_RESULT','BACKEND_B3_RESULT'),values):
        if value is not None:env[name]=value
    result=subprocess.run(['bash','-u','-e','-o','pipefail','-c',ORDINARY_B_PART_AGGREGATE['steps'][0]['run']],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10,check=False)
    assert result.returncode!=0


def test_ordinary_b_parts_actual_strict_aggregate_only_all_three_success(tmp_path):
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'BACKEND_B1_RESULT':'success','BACKEND_B2_RESULT':'success','BACKEND_B3_RESULT':'success'}
    result=subprocess.run(['bash','-u','-e','-o','pipefail','-c',ORDINARY_B_PART_AGGREGATE['steps'][0]['run']],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=10,check=False)
    assert result.returncode==0



def test_fresh_fixed_twenty_one_commands_restore_complete_prior_jobs():
    raw=yaml.safe_load((ROOT/'.github/workflows/sanity.yml').read_text())
    prior=_workflow_before_fresh_parts(raw,'sanity.yml')
    assert 'sanity-backend-fresh-1' not in prior['jobs'] and 'sanity-backend-fresh-2' not in prior['jobs']
    assert prior['jobs']['sanity-backend']['needs']==['sanity-backend-ordinary-a','sanity-backend-ordinary-b','sanity-backend-fresh']
    assert len(FRESH_PART_MODULES[0])==20 and FRESH_PART_MODULES[1]==('tests/test_research_method_drafts.py',)
    assert _workflow_before_ordinary_b_parts(raw,'sanity.yml')['jobs']['sanity-backend-fresh']==prior['jobs']['sanity-backend-fresh']


@pytest.mark.parametrize('mutation',['missing_worker','missing_command','duplicate_command','reverse_commands','flag','timeout','runner','environment','missing_need','missing_always','aggregate_soft','other_job'])
def test_fresh_fixed_segments_reject_any_missing_or_wider_boundary(mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows/sanity.yml').read_text());jobs=raw['jobs'];job=jobs[FRESH_PART_IDS[0]]
    step=next(s for s in job['steps'] if s.get('name')=='Leg 2 — web/backend pytest baseline')
    commands=[s for s in step['run'].splitlines(keepends=True) if s.startswith('python -m pytest ')]
    if mutation=='missing_worker':del jobs[FRESH_PART_IDS[1]]
    elif mutation=='missing_command':step['run']=step['run'].replace(commands[0],'',1)
    elif mutation=='duplicate_command':step['run']=step['run'].replace(commands[0],commands[0]+commands[0],1)
    elif mutation=='reverse_commands':step['run']=step['run'].replace(''.join(commands),''.join(reversed(commands)),1)
    elif mutation=='flag':step['run']=step['run'].replace(' -p no:logging','',1)
    elif mutation=='timeout':job['timeout-minutes']=90
    elif mutation=='runner':job['runs-on']='macos-latest'
    elif mutation=='environment':step['env']['PYTHONPATH']='foreign'
    elif mutation=='missing_need':jobs['sanity-backend-fresh']['needs'].pop()
    elif mutation=='missing_always':jobs['sanity-backend-fresh'].pop('if')
    elif mutation=='aggregate_soft':jobs['sanity-backend-fresh']['steps'][0]['run']+='true\n'
    else:jobs['sanity-backend-ordinary-a']['timeout-minutes']=99
    with pytest.raises((AssertionError,KeyError,ValueError)):_workflow_before_fresh_parts(raw,'sanity.yml')


@pytest.mark.parametrize('one,two',[('success','success'),('failure','success'),('cancelled','success'),('skipped','success'),('','success'),('unknown','success'),('success','failure'),('success','cancelled'),('success','skipped'),('success',''),('success','unknown')])
def test_fresh_aggregate_executes_strict_complete_success(one,two):
    run=FRESH_PART_AGGREGATE['steps'][0]['run']
    result=subprocess.run(['bash','-c',run],env={'BACKEND_FRESH1_RESULT':one,'BACKEND_FRESH2_RESULT':two},capture_output=True,text=True)
    assert (result.returncode==0)==(one==two=='success')


@pytest.mark.parametrize('system,version,target',[('ubuntu-latest','3.10',False),('ubuntu-latest','3.11',False),('ubuntu-latest','3.12',False),('macos-latest','3.11',False),('macos-latest','3.12',True)])
def test_backend_mac312_only_preparation_budget_preserves_five_matrix_cells(system,version,target):
    raw=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text());job=_workflow_before_cpu_torch_sources(raw,'ci.yml')['jobs']['backend'];prior=_workflow_before_backend_mac312_budget(raw,'ci.yml')['jobs']['backend']
    matrix=job['strategy']['matrix'];cells=[(s,p) for s in matrix['os'] for p in matrix['python-version'] if {'os':s,'python-version':p} not in matrix['exclude']]
    assert len(cells)==5 and (system,version) in cells and job['strategy']['fail-fast'] is False
    assert target==((system,version)==('macos-latest','3.12'))
    assert job['timeout-minutes']==BACKEND_MAC312_JOB_TIMEOUT and prior['timeout-minutes']==15
    assert job['steps'][:3]==prior['steps'][:3]
    if target:
        assert [job['steps'][i]['timeout-minutes'] for i in (5,8)]==[20,15]
        assert job['steps'][5]['run']==prior['steps'][3]['run']+prior['steps'][4]['run']
        assert job['steps'][8]['run'].splitlines()==[prior['steps'][5]['run'],prior['steps'][6]['run']]
        assert all(job['steps'][i]['if']==BACKEND_MAC312_TARGET_IF for i in (5,8))
    else:
        for actual,expected in zip(job['steps'][3:5]+job['steps'][6:8],prior['steps'][3:]):
            value=copy.deepcopy(actual);assert value.pop('if')==BACKEND_MAC312_OTHER_IF and value==expected


@pytest.mark.parametrize('mutation',['all_job_40','prep30','tests_each15','tests30','reverse_tests','missing_test','not_mutual','always','soften','drop_cell','cache','lfs','release_edge'])
def test_backend_mac312_budget_rejects_any_wider_or_weaker_scope(mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text());job=raw['jobs']['backend'];steps=job['steps']
    if mutation=='all_job_40':job['timeout-minutes']=40
    elif mutation=='prep30':steps[5]['timeout-minutes']=30
    elif mutation=='tests_each15':steps.insert(9,copy.deepcopy(steps[8]))
    elif mutation=='tests30':steps[8]['timeout-minutes']=30
    elif mutation=='reverse_tests':steps[8]['run']='\n'.join(reversed(steps[8]['run'].splitlines()))+'\n'
    elif mutation=='missing_test':steps[8]['run']=steps[8]['run'].splitlines()[0]+'\n'
    elif mutation=='not_mutual':steps[3]['if']=BACKEND_MAC312_TARGET_IF
    elif mutation=='always':steps[8]['if']='always()'
    elif mutation=='soften':steps[8]['continue-on-error']=True
    elif mutation=='drop_cell':job['strategy']['matrix']['python-version'].remove('3.11')
    elif mutation=='cache':steps[2]['with']['key']='new-cache'
    elif mutation=='lfs':steps[0]['with']['lfs']=False
    else:raw['jobs']['release-gate-summary']['needs'].remove('backend')
    with pytest.raises((AssertionError,KeyError)):_workflow_before_backend_mac312_budget(raw,'ci.yml')


@pytest.mark.parametrize('phase,fail_at,count',[('prepare',0,6),('prepare',1,1),('prepare',4,4),('tests',0,2),('tests',1,1),('tests',2,2)])
def test_backend_mac312_original_phase_shell_preserves_fail_fast(tmp_path,phase,fail_at,count):
    raw=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text());_workflow_before_backend_mac312_budget(raw,'ci.yml')
    step=raw['jobs']['backend']['steps'][5 if phase=='prepare' else 8]
    tools=tmp_path/'commands';tools.mkdir();trace=tmp_path/'trace';counter=tmp_path/'counter'
    stub='#!/bin/sh\nn=0; if [ -f "$COUNT_FILE" ]; then read -r n < "$COUNT_FILE"; fi\nn=$((n+1)); printf "%s\\n" "$n" > "$COUNT_FILE"; printf "%s\\n" "$n" >> "$TRACE_FILE"\nif [ "$n" -eq "$FAIL_AT" ]; then exit 17; fi\n'
    for name in ('python','pip','pytest'):
        p=tools/name;p.write_text(stub);p.chmod(0o700)
    result=subprocess.run(['/bin/bash','--noprofile','--norc','-e','-o','pipefail','-c',step['run']],env={'PATH':str(tools)+':/usr/bin:/bin','COUNT_FILE':str(counter),'TRACE_FILE':str(trace),'FAIL_AT':str(fail_at)},capture_output=True,text=True,timeout=5)
    assert trace.read_text().splitlines()==[str(n) for n in range(1,count+1)]
    assert result.returncode==(0 if fail_at==0 else 17)



def _cpu_torch_pin_verifier():
    source=CPU_TORCH_PRE.split("python - <<'CPU_TORCH_PIN'\n",1)[1].rsplit('\nCPU_TORCH_PIN',1)[0]
    tree=ast.parse(source);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_cpu_torch_pin')
    scope={'hashlib':hashlib,'re':re};exec(compile(ast.Module(body=[node],type_ignores=[]),'<fixed-cpu-pin-verifier>','exec'),scope)
    return scope['verify_cpu_torch_pin']


def test_cpu_torch_only_approved_consumers_and_original_dependency_resolution():
    assert CPU_TORCH_URL=='https://download-r2.pytorch.org/whl/cpu/torch-2.14.1%2Bcpu-cp311-cp311-manylinux_2_28_x86_64.whl'
    assert CPU_TORCH_SHA256=='5e38154c8896d426a5df58bf2276b603e82184dfae4f54d77dbb212f36e34f37'
    assert len(CPU_TORCH_ORIGINAL_RUNS)==10
    assert len({jid for name,jid,title in CPU_TORCH_ORIGINAL_RUNS if name=='sanity.yml'})==7
    verify=_cpu_torch_pin_verifier()
    verify((ROOT/'requirements/runtime-linux-cpu.lock').read_text(),(ROOT/'web/backend/requirements.txt').read_text(),('cpython','linux',(3,11),'x86_64'))
    for name in ('sanity.yml','ci.yml'):
        raw=yaml.safe_load((ROOT/'.github/workflows'/name).read_text());prior=_workflow_before_cpu_torch_sources(raw,name)
        for (workflow,jid,title),original in CPU_TORCH_ORIGINAL_RUNS.items():
            if workflow!=name:continue
            run=next(s['run'] for s in raw['jobs'][jid]['steps'] if s.get('name')==title)
            assert '--no-deps' not in run and '--upgrade' not in run.replace('python -m pip install --upgrade pip','')
            assert '--index-url' not in run and '--extra-index-url' not in run
            assert 'assert torch.version.cuda is None' in run
            assert next(s['run'] for s in prior['jobs'][jid]['steps'] if s.get('name')==title)==original
            if name=='sanity.yml' or title=='Install dependencies':
                commands=[shlex.split(line) for line in run.splitlines() if line.startswith(('pip install ','python -m pip install '))]
                assert sum(CPU_TORCH_REQUIREMENT in command for command in commands)==1
    ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    assert CPU_TORCH_CI_CONDITION=='if [ "${{ matrix.os }}" = "ubuntu-latest" ] && [ "${{ matrix.python-version }}" = "3.11" ]; then\n'
    # The already reviewed macOS preparation/test phases retain their exact bodies.
    original=_workflow_before_cpu_torch_sources(ci,'ci.yml')
    assert ci['jobs']['backend']['steps'][5]==original['jobs']['backend']['steps'][5]
    assert ci['jobs']['backend']['steps'][8]==original['jobs']['backend']['steps'][8]


@pytest.mark.parametrize('runtime',[('cpython','darwin',(3,11),'x86_64'),('cpython','linux',(3,12),'x86_64'),('cpython','linux',(3,11),'aarch64'),('pypy','linux',(3,11),'x86_64')])
def test_cpu_torch_pin_rejects_any_unapproved_runtime(runtime):
    with pytest.raises(AssertionError):_cpu_torch_pin_verifier()((ROOT/'requirements/runtime-linux-cpu.lock').read_text(),(ROOT/'web/backend/requirements.txt').read_text(),runtime)


@pytest.mark.parametrize('mutation',['lock_hash','wrong_public_version'])
def test_cpu_torch_pin_rejects_drift_before_installer(mutation):
    lock=(ROOT/'requirements/runtime-linux-cpu.lock').read_text();requirements=(ROOT/'web/backend/requirements.txt').read_text()
    if mutation=='lock_hash':lock=lock.replace(CPU_TORCH_SHA256,'0'*64,1)
    else:requirements=requirements.replace('torch==2.14.1','torch==2.15.0',1)
    with pytest.raises(AssertionError):_cpu_torch_pin_verifier()(lock,requirements,('cpython','linux',(3,11),'x86_64'))


@pytest.mark.parametrize('name,mutation',[('sanity.yml','missing'),('sanity.yml','hash'),('sanity.yml','source'),('sanity.yml','no_deps'),('sanity.yml','cuda_post'),('sanity.yml','other_job'),('ci.yml','missing'),('ci.yml','cpu_cell'),('ci.yml','other_python'),('ci.yml','local_post'),('ci.yml','mac_budget'),('ci.yml','matrix')])
def test_cpu_torch_workflow_rejects_any_wider_or_missing_selection(name,mutation):
    raw=yaml.safe_load((ROOT/'.github/workflows'/name).read_text())
    jid='sanity-backend-ordinary-b-3' if name=='sanity.yml' else 'backend'
    title='Install web/backend deps' if name=='sanity.yml' else 'Install dependencies'
    step=next(s for s in raw['jobs'][jid]['steps'] if s.get('name')==title)
    if mutation=='missing':step['run']=CPU_TORCH_ORIGINAL_RUNS[(name,jid,title)]
    elif mutation=='hash':step['run']=step['run'].replace(CPU_TORCH_SHA256,'0'*64)
    elif mutation=='source':step['run']=step['run'].replace('download-r2.pytorch.org','foreign.example')
    elif mutation=='no_deps':step['run']=step['run'].replace('pip install -r','pip install --no-deps -r',1)
    elif mutation=='cuda_post':step['run']=step['run'].replace('assert torch.version.cuda is None','pass')
    elif mutation=='other_job':raw['jobs']['sanity-backend']['steps'][0]['run']+='true\n'
    elif mutation=='cpu_cell':step['run']=step['run'].replace('"ubuntu-latest"','"macos-latest"',1)
    elif mutation=='other_python':step['run']=step['run'].replace('"3.11"','"3.12"',1)
    elif mutation=='local_post':next(s for s in raw['jobs']['backend']['steps'] if s.get('name')=='Install local packages (editable)')['run']=CPU_TORCH_ORIGINAL_RUNS[('ci.yml','backend','Install local packages (editable)')]
    elif mutation=='mac_budget':raw['jobs']['backend']['timeout-minutes']=40
    else:raw['jobs']['backend']['strategy']['matrix']['python-version'].remove('3.10')
    with pytest.raises((AssertionError,KeyError)):_workflow_before_cpu_torch_sources(raw,name)


@pytest.mark.parametrize('case',['complete','bad_hash','missing_dependency'])
def test_cpu_torch_stock_pip_dry_run_preserves_public_version_hash_and_dependencies(tmp_path,case):
    # Inert metadata wheels only: no package code, installation or external index.
    import zipfile
    wheels=tmp_path/'wheels';wheels.mkdir();home=tmp_path/'home';home.mkdir()
    def wheel(name,version,requires=()):
        normalized=name.replace('-','_');info=normalized+'-'+version+'.dist-info'
        target=wheels/(normalized+'-'+version+'-py3-none-any.whl')
        metadata='Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+'\n'+''.join('Requires-Dist: '+x+'\n' for x in requires)+'\n'
        with zipfile.ZipFile(target,'w') as archive:
            archive.writestr(info+'/METADATA',metadata)
            archive.writestr(info+'/WHEEL','Wheel-Version: 1.0\nGenerator: inert-ci-contract\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            archive.writestr(info+'/RECORD','')
        return target
    cpu=wheel('torch','2.14.1+cpu',('cpu-contract-dep==1.0',))
    if case!='missing_dependency':wheel('cpu-contract-dep','1.0')
    wheel('other-contract-dep','1.0')
    requirements=tmp_path/'requirements.txt';requirements.write_text('torch==2.14.1\nother-contract-dep==1.0\n')
    digest=hashlib.sha256(cpu.read_bytes()).hexdigest()
    if case=='bad_hash':digest='0'*64
    report=tmp_path/'report.json'
    command=[CPU_TORCH_PROOF_PYTHON,'-I','-B','-m','pip','--disable-pip-version-check','--cache-dir',str(tmp_path/'cache'),'install','--dry-run','--ignore-installed','--no-index','--only-binary=:all:','--find-links',str(wheels),'--report',str(report),'-r',str(requirements),'torch @ '+cpu.as_uri()+'#sha256='+digest]
    result=subprocess.run(command,env={'PATH':'/usr/bin:/bin','HOME':str(home),'TMPDIR':str(tmp_path),'PIP_CONFIG_FILE':os.devnull,'PIP_DISABLE_PIP_VERSION_CHECK':'1','PIP_NO_INPUT':'1','PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=15)
    assert result.returncode==0 if case=='complete' else result.returncode!=0
    if case=='complete':
        data=json.loads(report.read_text());planned={x['metadata']['name'].replace('_','-'):x['metadata']['version'] for x in data['install']}
        assert planned=={'torch':'2.14.1+cpu','cpu-contract-dep':'1.0','other-contract-dep':'1.0'}
        assert data['install'][0]['requested'] is True or any(x['requested'] for x in data['install'])
    else:assert not report.exists()



def test_root_current_main_pair_keeps_all_33_selected_in_one_fresh_process():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_root_current_main33(raw)
    assert len(ROOT_CURRENT_MAIN_NODES)==33
    assert all(node.startswith('tests/test_research_browser.py::') for node in ROOT_CURRENT_MAIN_NODES)
    assert not any('test_method_draft_refresh_preserves_newer_observation_state_unit' in node for node in ROOT_CURRENT_MAIN_NODES)
    assert 'tests/test_research_browser.py::test_new_research_without_task_selector_keeps_real_create_and_save' in ROOT_CURRENT_MAIN_NODES
    assert ROOT_CURRENT_MAIN_NODES[1]=='tests/test_research_browser.py::test_current_main_private_problem_xss_auth503_draft_and_real401_clear'
    assert ROOT_CURRENT_MAIN_PRIOR_RECIPE in prior


@pytest.mark.parametrize('mutation',['missing_pair','missing_filter','whole_module','wrong_path','wrong_parameter','duplicate_filter','fresh_missing','fresh_duplicate','fresh_order','marker','other_recipe'])
def test_root_current_main_pair_rejects_missing_duplicate_or_weaker_placement(mutation):
    raw=(ROOT/'Makefile').read_text();original,ordinary,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)');token=' --deselect="'+ROOT_CURRENT_MAIN_NODES[0]+'"'
    if mutation=='missing_pair':value=raw.replace(fresh,'',1)
    elif mutation=='missing_filter':value=raw.replace(token,'',1)
    elif mutation=='whole_module':value=raw.replace(token,' --deselect="tests/test_research_browser.py"',1)
    elif mutation=='wrong_path':value=raw.replace(token,token.replace('tests/','',1),1)
    elif mutation=='wrong_parameter':value=raw.replace(token,token[:-1]+'[foreign]"',1)
    elif mutation=='duplicate_filter':value=raw.replace(token,token+token,1)
    elif mutation=='fresh_missing':value=raw.replace(fresh,fresh.replace(shlex.quote(ROOT_CURRENT_MAIN_NODES[0])+' ','',1),1)
    elif mutation=='fresh_duplicate':value=raw.replace(fresh,fresh.replace(' -m ',' '+shlex.quote(ROOT_CURRENT_MAIN_NODES[0])+' -m ',1),1)
    elif mutation=='fresh_order':value=raw.replace(fresh,fresh.replace(shlex.join(ROOT_CURRENT_MAIN_NODES),shlex.join(reversed(ROOT_CURRENT_MAIN_NODES)),1),1)
    elif mutation=='marker':value=raw.replace(fresh,fresh.replace(' -m "not e2e and not slow and not requires_internet and not requires_llm"',''),1)
    else:value=raw.replace('$(PYTEST) -m "not e2e" -q','$(PYTEST) -q',1)
    with pytest.raises(AssertionError):_makefile_before_root_current_main33(value)


def test_root_current_main_pair_actual_make_dryrun_is_exact_and_reversible():
    result=subprocess.run(['make','-n','PY=python','test-release-contracts'],cwd=ROOT,env={'PATH':os.environ['PATH']},capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    restored=_dry_run_before_root_current_main33(result.stdout)
    assert restored.count(' tests --ignore=tests/e2e -m "not e2e and not slow and not requires_internet and not requires_llm" -q')==1
    assert not any(node in restored for node in ROOT_CURRENT_MAIN_NODES)



def test_root_retired_browser_exact121_preserves_current_and_client_safety():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_retired_browser121(raw)
    assert len(ROOT_RETIRED_BROWSER_NODES)==121 and len(ROOT_CURRENT_MAIN_NODES)==33
    assert all(node.startswith('tests/test_research_browser.py::') for node in ROOT_RETIRED_BROWSER_NODES)
    assert not set(ROOT_RETIRED_BROWSER_NODES)&set(ROOT_CURRENT_MAIN_NODES)
    assert not any(name in node for node in ROOT_RETIRED_BROWSER_NODES for name in ('test_entry_kb_input_generations_and_revocation_reject_late_results','test_task_selector_without_research_id_is_explicitly_invalid_and_cannot_create','test_method_draft_refresh_preserves_newer_observation_state_unit'))
    assert _root_retired_browser_flags() not in prior
    assert hashlib.sha256(prior.encode()).hexdigest()==ROOT_RETIRED_BROWSER_PRIOR_MAKE_SHA256


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_path','whole_module','function_prefix','foreign_parameter','fresh_defer','fresh_missing','marker','other_recipe'])
def test_root_retired_browser_rejects_missing_duplicate_or_wider_defer(mutation):
    raw=(ROOT/'Makefile').read_text();node=ROOT_RETIRED_BROWSER_NODES[0];token=' --deselect="'+node+'"'
    param=next(n for n in ROOT_RETIRED_BROWSER_NODES if '[' in n);param_token=' --deselect="'+param+'"'
    if mutation=='missing':value=raw.replace(token,'',1)
    elif mutation=='duplicate':value=raw.replace(token,token+token,1)
    elif mutation=='wrong_path':value=raw.replace(token,token.replace('tests/','',1),1)
    elif mutation=='whole_module':value=raw.replace(token,' --deselect="tests/test_research_browser.py"',1)
    elif mutation=='function_prefix':value=raw.replace(param_token,' --deselect="'+param.split('[')[0]+'"',1)
    elif mutation=='foreign_parameter':value=raw.replace(param_token,' --deselect="'+param.split('[')[0]+'[foreign]"',1)
    elif mutation=='fresh_defer':
        _,_,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)');value=raw.replace(fresh,fresh.replace(' -m ',token+' -m ',1),1)
    elif mutation=='fresh_missing':
        _,_,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)');value=raw.replace(fresh,'',1)
    elif mutation=='marker':value=raw.replace('not requires_llm" -q','not requires_llm and not current" -q',1)
    else:value=raw.replace('$(PYTEST) -m "not e2e" -q','$(PYTEST) -q',1)
    with pytest.raises(AssertionError):_makefile_before_retired_browser121(value)


def test_root_retired_browser_actual_make_dryrun_reverses_complete_chain():
    result=subprocess.run(['make','-n','PY=python','test-release-contracts'],cwd=ROOT,env={'PATH':os.environ['PATH']},capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    restored=_dry_run_before_root_current_main33(result.stdout)
    assert not any(node in restored for node in ROOT_CURRENT_MAIN_NODES+ROOT_RETIRED_BROWSER_NODES)
    assert restored.count(' tests --ignore=tests/e2e -m "not e2e and not slow and not requires_internet and not requires_llm" -q')==1



def test_root_current_main_stdout_only_disables_pytest_logging_for_fresh33():
    raw=(ROOT/'Makefile').read_text();prior=_makefile_before_current_main_stdout(raw)
    _,_,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)')
    assert fresh.replace(' -m ',' -p no:logging -m ',1) in raw and fresh in prior
    ordinary=[line for line in raw.splitlines() if line.startswith('\t$(BACKEND_PYTEST) tests --ignore=tests/e2e ')]
    assert len(ordinary)==1 and 'no:logging' not in ordinary[0]
    assert raw.count('-p no:logging')==prior.count('-p no:logging')+1


@pytest.mark.parametrize('mutation',['missing','duplicate','wrong_plugin','ordinary','different_selector','marker'])
def test_root_current_main_stdout_rejects_missing_duplicate_or_changed_scope(mutation):
    raw=(ROOT/'Makefile').read_text();_,_,fresh=_root_current_main_recipe_pair('\t$(BACKEND_PYTEST)');stdout=fresh.replace(' -m ',' -p no:logging -m ',1)
    if mutation=='missing':value=raw.replace(stdout,fresh,1)
    elif mutation=='duplicate':value=raw.replace(stdout,stdout.replace(' -p no:logging',' -p no:logging -p no:logging',1),1)
    elif mutation=='wrong_plugin':value=raw.replace(stdout,stdout.replace('no:logging','no:terminal',1),1)
    elif mutation=='ordinary':value=raw.replace('$(BACKEND_PYTEST) tests --ignore=tests/e2e','$(BACKEND_PYTEST) -p no:logging tests --ignore=tests/e2e',1)
    elif mutation=='different_selector':value=raw.replace(stdout,stdout.replace(ROOT_CURRENT_MAIN_NODES[0],ROOT_CURRENT_MAIN_NODES[0]+'[foreign]',1),1)
    else:value=raw.replace(stdout,stdout.replace('not requires_llm','not requires_llm and not current',1),1)
    with pytest.raises(AssertionError):_makefile_before_current_main_stdout(value)


def test_root_current_main_stdout_actual_make_dryrun_reverses_full_chain():
    result=subprocess.run(['make','-n','PY=python','test-release-contracts'],cwd=ROOT,env={'PATH':os.environ['PATH']},capture_output=True,text=True,timeout=10)
    assert result.returncode==0
    restored=_dry_run_before_root_current_main33(result.stdout)
    assert ' tests --ignore=tests/e2e -m "not e2e and not slow and not requires_internet and not requires_llm" -q' in restored
    assert not any(node in restored for node in ROOT_CURRENT_MAIN_NODES+ROOT_RETIRED_BROWSER_NODES)
