import ast
import hashlib
import json
import os
import re
import shlex
import subprocess
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
        if "if" in step:
            name = step.get("name")
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
        "test-release-contracts", "test-frontend-node", "test-browser-contracts",
        "openapi-check", "types-check", "verify-release",
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
        "openapi-check": [
            "PYTHONPATH=$(ROOT)/web/backend:$(PACKAGE_PYTHONPATH) $(OPENAPI_PY) "
            "$(ROOT)/scripts/openapi_artifact.py --check"
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
        "pytest==9.0.3", "playwright==1.59.0", "fastapi==0.115.14",
        "pydantic==2.6.1", "starlette==0.46.2",
        "uvicorn[standard]==0.27.1", "PyJWT==2.12.1", "slowapi==0.1.9",
        "structlog==25.5.0", "python", "-m", "playwright", "install",
        "--with-deps", "chromium",
    ]
    requirements = (
        ROOT / "web/backend/requirements.txt"
    ).read_text(encoding="utf-8").splitlines()
    assert "structlog==25.5.0" in requirements


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


def test_release_gate_manifest_binds_internal_and_external_checks() -> None:
    manifest_path = ROOT / ".github/release-gate-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_needs = [
        "retrieval-eval-contract",
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


def test_makefile_release_authority_is_independently_frozen() -> None:
    assert hashlib.sha256((ROOT / "Makefile").read_bytes()).hexdigest() == (
        "5230385937dd093bd362dd459f55ef4716baa8ba2b8b8f76283b44ab5c604b0c"
    )


def test_verify_release_dry_run_expands_real_test_and_build_commands() -> None:
    environment = os.environ.copy()
    for variable in ("MAKEFLAGS", "MAKEOVERRIDES", "PYTEST", "BACKEND_PYTEST"):
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
    assert install_tokens[:4] == ["python", "-m", "pip", "install"]
    assert "pytest-playwright==0.7.2" in install_tokens
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
    assert phase_tests == ["web/tests/e2e/test_phase_auth_real.py"]
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
    assert _shell_tokens(phase_step) == ["pytest", *phase_tests, "-v"]

    assert _make_recipe_commands(makefile, "verify-release") == [
        "$(MAKE) openapi-check",
        "$(MAKE) types-check",
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


def test_optional_analytics_never_blocks_dom_content_loaded() -> None:
    """Third-party telemetry must not delay the product's readiness event."""
    failures: list[str] = []
    pattern = re.compile(
        r"<script\b(?P<attrs>[^>]*)\bsrc=[\"']"
        r"https://plausible\.bytedance\.city/js/script\.js[\"'][^>]*>",
        re.I,
    )
    for page in sorted((ROOT / "web/frontend").glob("*.html")):
        for match in pattern.finditer(page.read_text(encoding="utf-8")):
            attrs = match.group("attrs")
            if not re.search(r"(?:^|\s)async(?:\s|$)", attrs, re.I):
                failures.append(f"{page.name}: Plausible script is not async")
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
