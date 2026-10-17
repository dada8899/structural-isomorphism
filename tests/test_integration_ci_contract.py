"""Offline B0 gates: execute admission scripts, never dispatch or publish."""
from __future__ import annotations

import ast
import copy
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = "integration/structure-rebuild-v1"
BOOTSTRAP = "bootstrap/structure-ci-20261016"
PUSH_BRANCHES = ["main", INTEGRATION, BOOTSTRAP]
PR_BRANCHES = ["main", INTEGRATION]
CORE_WORKFLOWS = [
    "ci.yml", "sanity.yml", "types-sync.yml", "beta-perf.yml",
    "coverage.yml", "product-ci.yml",
]
PRODUCTION_WORKFLOWS = [
    "deploy-beta-backend.yml", "deploy-phase-detector.yml", "docs.yml",
    "release-packages.yml", "publish-pypi.yml",
]
# Semantic snapshots: be3a3c6 jobs, with only the two approved runtime-pin
# upgrades bridged from source 044e08c, plus the two approved sidebar test
# paths on a76d6b9 (see CI_BASELINE.md).
# Trigger expansion must not silently remove work from any existing hard job.
BASELINE_JOB_DIGESTS = {
    "retrieval-eval-contract": "314bae490885c88c9c6db354267821221f66bc51b1390e02f361c000016d15f8",
    "site-docs-contract": "0f57f4945237fd941c2e8d368de8c45ac77cebb7ef06263d1a8d66367c48a92c",
    "phase-python-contract": "31410b6d2c1aaf8d2d46261b6b9cfdefbcbe0ed0391d6afb119b636356c1dc32",
    "browser-product-contract": "ea661e1cc7eee8004be5a25e49b38fb1f4f9b27394648b6b64e2a428c55e39df",
    "browser-beta-surface-contract": "561bf72d78777f276b64e20f215a40efe67bb9d025c78ce4afc60744ef2ad004",
    "backend": "1880d457fc00c68ff81deb35c32c75e321c3dc5c6e0cdc793dfab4f030669b4c",
    "packages": "e4aa89e17ef04576287375e0d658dd3b2ee78569cfe6afb7d5d34b933d313fbe",
    "frontend": "bc2d19708c65b0594b78ca090ab06297a5106e1906fb826d4b5e01bce82fbe70",
    "release-gate-summary": "c1d17a4eae4364e1593eab37a4aed52eb03a48f8d40662fad0b981b68ffa165a",
}


def workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github/workflows" / name).read_text())


def triggers(value: dict) -> dict:
    return value.get("on", value.get(True))


def assert_existing_jobs_unchanged(value: dict) -> None:
    for name, expected in BASELINE_JOB_DIGESTS.items():
        body = value["jobs"][name]
        digest = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        assert digest == expected, f"existing hard job changed: {name}"


def assert_production_dependency_graph(value: dict) -> None:
    jobs = value["jobs"]
    assert "admit-production" in jobs

    def guarded(name: str, visiting: frozenset[str] = frozenset()) -> bool:
        assert name not in visiting, "cyclic job dependency"
        if name == "admit-production":
            return True
        job = jobs[name]
        assert "if" not in job, "job condition must not bypass failed admission"
        assert not job.get("continue-on-error", False)
        needs = job.get("needs", [])
        needs = [needs] if isinstance(needs, str) else needs
        return any(guarded(parent, visiting | {name}) for parent in needs)

    for name in jobs:
        assert guarded(name), f"production job bypasses admission: {name}"


def run_admission(name: str, event: str, ref: str, tmp_path: Path):
    step = workflow(name)["jobs"]["admit-production"]["steps"][0]
    # These are the actual checked-in shell bodies, not a duplicate decision.
    script = step["run"]
    assert "${{" not in script
    env = {"PATH": os.environ["PATH"], "EVENT_NAME": event, "SOURCE_REF": ref}
    return subprocess.run(
        ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c", script],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=5,
    )


@pytest.mark.parametrize("name", CORE_WORKFLOWS)
def test_required_checks_cover_exact_nonproduction_and_main_branches(name):
    events = triggers(workflow(name))
    assert events["push"] == {"branches": PUSH_BRANCHES}
    assert events["pull_request"] == {"branches": PR_BRANCHES}
    # No path filter can strand a required check on an unrelated-file PR.
    assert "workflow_dispatch" not in events or name == "sanity.yml"
    for branch in ["main", INTEGRATION, BOOTSTRAP, "feature/unrelated"]:
        assert (branch in events["push"]["branches"]) == (branch in PUSH_BRANCHES)


@pytest.mark.parametrize("name", ["ci-packages.yml", "runtime-smoke.yml"])
def test_optional_existing_checks_keep_scoped_paths_and_gain_branches(name):
    events = triggers(workflow(name))
    assert events["push"]["branches"] == PUSH_BRANCHES
    assert events["pull_request"]["branches"] == PR_BRANCHES
    assert events["push"]["paths"] == events["pull_request"]["paths"]
    assert f".github/workflows/{name}" in events["push"]["paths"]


def test_existing_hard_work_and_aggregator_are_preserved():
    value = workflow("ci.yml")
    assert_existing_jobs_unchanged(value)
    assert value["jobs"]["release-gate-summary"]["needs"] == list(BASELINE_JOB_DIGESTS)[:-1]


@pytest.mark.parametrize("mutation", ["remove-job", "empty-steps", "soften", "conditional"])
def test_hard_job_mutations_are_detected(mutation):
    value = copy.deepcopy(workflow("ci.yml"))
    job = value["jobs"]["backend"]
    if mutation == "remove-job":
        del value["jobs"]["backend"]
    elif mutation == "empty-steps":
        job["steps"] = []
    elif mutation == "soften":
        job["continue-on-error"] = True
    else:
        job["if"] = "false"
    with pytest.raises((AssertionError, KeyError)):
        assert_existing_jobs_unchanged(value)


def test_product_is_real_hard_check_and_declared_required():
    value = workflow("product-ci.yml")
    job = value["jobs"]["product"]
    assert job["name"] == "product"
    assert "if" not in job and "continue-on-error" not in job
    assert value["permissions"] == {"contents": "read"}
    steps = job["steps"]
    assert all("if" not in step and "continue-on-error" not in step for step in steps)
    commands = [step.get("run", "") for step in steps]
    assert "python -m pip install pytest==9.0.3 PyYAML==6.0.3" in commands
    assert "python -m pytest tests/test_integration_ci_contract.py -q" in commands
    identity = next(step for step in steps if "EVENT_SHA" in step.get("env", {}))
    assert identity["env"]["PR_HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"
    assert identity["env"]["PR_BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    assert identity["env"]["WORKFLOW_SHA"] == "${{ github.workflow_sha }}"
    assert identity["env"]["RUN_ID"] == "${{ github.run_id }}"
    assert identity["env"]["RUN_ATTEMPT"] == "${{ github.run_attempt }}"
    assert 'checkout != os.environ["EVENT_SHA"]' in identity["run"]
    manifest = json.loads((ROOT / ".github/release-gate-manifest.json").read_text())
    assert [entry["context"] for entry in manifest["branch_protection_required_checks"]] == [
        "release-gate", "sanity", "check", "beta-perf-audit", "product",
    ]


@pytest.mark.parametrize("matching", [True, False])
def test_product_identity_uses_actual_checkout_and_preserves_pr_identities(matching, tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([
        "git", "-c", "user.name=B0", "-c", "user.email=b0@example.invalid",
        "commit", "--allow-empty", "-qm", "merge-candidate",
    ], cwd=tmp_path, check=True)
    checkout = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    step = next(step for step in workflow("product-ci.yml")["jobs"]["product"]["steps"]
                if "EVENT_SHA" in step.get("env", {}))
    env = {"PATH": os.environ["PATH"], "EVENT_NAME": "pull_request",
           "WORKFLOW_REF": "repo/.github/workflows/product-ci.yml@refs/pull/250/merge",
           "WORKFLOW_SHA": "d" * 40, "RUN_ID": "250", "RUN_ATTEMPT": "2",
           "EVENT_SHA": checkout if matching else "0" * 40,
           "PR_HEAD_SHA": "a" * 40, "PR_BASE_SHA": "b" * 40}
    # PATH only supplies Python/git. No repository or environment credentials.
    script = step["run"].split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    result = subprocess.run([os.sys.executable, "-c", script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) is matching
    if matching:
        receipt = json.loads(result.stdout)
        assert receipt["checkout_sha"] == checkout == receipt["event_sha"]
        assert receipt["pr_head_sha"] != receipt["checkout_sha"]
        assert receipt["pr_base_sha"] != receipt["pr_head_sha"]
        assert receipt["workflow_sha"] == "d" * 40
        assert receipt["run_id"] == "250" and receipt["run_attempt"] == "2"


def live_condition_allows(expression: str, event: str, ref: str, base: str, labels: list[str]):
    """Evaluate this small boolean expression without eval or executing code."""
    text = expression.replace("&&", " and ").replace("||", " or ")
    text = text.replace("contains(github.event.pull_request.labels.*.name,", "has_label(")
    values = {"event": event, "ref": ref, "base": base}
    for source, target in [("github.event_name", "event"), ("github.ref", "ref"), ("github.base_ref", "base")]:
        text = text.replace(source, target)

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.BoolOp):
            items = [visit(item) for item in node.values]
            if isinstance(node.op, ast.And):
                return all(items)
            assert isinstance(node.op, ast.Or)
            return any(items)
        if isinstance(node, ast.Compare):
            assert len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
            return visit(node.left) == visit(node.comparators[0])
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name) and node.func.id == "has_label"
            assert len(node.args) == 1 and not node.keywords
            return visit(node.args[0]) in labels
        raise AssertionError(f"unsupported workflow condition: {ast.dump(node)}")

    return visit(ast.parse(text, mode="eval"))


@pytest.mark.parametrize("event,ref,base,labels,allowed", [
    ("push", "refs/heads/main", "", [], True),
    ("push", f"refs/heads/{INTEGRATION}", "", [], False),
    ("push", f"refs/heads/{BOOTSTRAP}", "", [], False),
    ("pull_request", "refs/pull/250/merge", INTEGRATION, ["run-e2e"], False),
    ("pull_request", "refs/pull/250/merge", "main", ["run-e2e"], True),
    ("pull_request", "refs/pull/250/merge", "main", [], False),
    ("workflow_dispatch", "refs/heads/main", "", [], False),
])
def test_optional_live_e2e_only_observes_production_events(event, ref, base, labels, allowed):
    expression = workflow("ci.yml")["jobs"]["e2e"]["if"]
    assert live_condition_allows(expression, event, ref, base, labels) is allowed


@pytest.mark.parametrize("name", PRODUCTION_WORKFLOWS)
def test_all_production_jobs_wait_for_pure_admission(name):
    value = workflow(name)
    assert_production_dependency_graph(value)
    guard = value["jobs"]["admit-production"]
    assert guard["permissions"] == {"contents": "read"}
    first = guard["steps"][0]
    assert "uses" not in first and "working-directory" not in first
    assert first["env"] == {"EVENT_NAME": "${{ github.event_name }}", "SOURCE_REF": "${{ github.ref }}"}
    assert "secrets." not in json.dumps(guard)
    assert "if" not in first and "continue-on-error" not in first
    # Production pushes remain unchanged; integration has no auto-release trigger.
    events = triggers(value)
    if "branches" in events["push"]:
        assert events["push"]["branches"] == ["main"]
    else:
        assert events["push"]["tags"]


@pytest.mark.parametrize("name", PRODUCTION_WORKFLOWS)
@pytest.mark.parametrize("ref", [f"refs/heads/{INTEGRATION}", f"refs/heads/{BOOTSTRAP}", "refs/heads/feature/main", "refs/tags/v0.1.0"])
def test_nonmain_dispatch_is_rejected_before_any_checkout_or_side_effect(name, ref, tmp_path):
    result = run_admission(name, "workflow_dispatch", ref, tmp_path)
    assert result.returncode != 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", PRODUCTION_WORKFLOWS)
def test_dispatch_input_cannot_execute_shell(name, tmp_path):
    marker = tmp_path / "injected"
    result = run_admission(name, "workflow_dispatch", f"refs/heads/$(touch {marker})", tmp_path)
    assert result.returncode != 0
    assert not marker.exists()


@pytest.mark.parametrize("name", PRODUCTION_WORKFLOWS)
def test_valid_main_dispatch_retains_admission(name, tmp_path):
    assert run_admission(name, "workflow_dispatch", "refs/heads/main", tmp_path).returncode == 0


@pytest.mark.parametrize("name", PRODUCTION_WORKFLOWS[:3])
def test_valid_main_push_retains_admission(name, tmp_path):
    assert run_admission(name, "push", "refs/heads/main", tmp_path).returncode == 0


@pytest.mark.parametrize("name,tag", [
    ("release-packages.yml", "guarded-llm-v0.1.0"),
    ("release-packages.yml", "soc-pipeline-v0.1.0"),
    ("release-packages.yml", "cross-judge-v0.1.0"),
    ("release-packages.yml", "reject-aware-critic-v0.1.0"),
    ("publish-pypi.yml", "v0.1.0"),
])
def test_existing_release_tag_formats_remain_admissible(name, tag, tmp_path):
    assert run_admission(name, "push", f"refs/tags/{tag}", tmp_path).returncode == 0
    assert any(fnmatch.fnmatchcase(tag, pattern) for pattern in triggers(workflow(name))["push"]["tags"])


@pytest.mark.parametrize("name", ["release-packages.yml", "publish-pypi.yml"])
def test_tag_lineage_rejects_unmerged_integration_commit(name, tmp_path):
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()
    git("init", "-q")
    git("-c", "user.name=B0", "-c", "user.email=b0@example.invalid", "commit", "--allow-empty", "-qm", "main")
    production = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", production)
    git("-c", "user.name=B0", "-c", "user.email=b0@example.invalid", "commit", "--allow-empty", "-qm", "integration")
    unmerged = git("rev-parse", "HEAD")
    guard = workflow(name)["jobs"]["admit-production"]
    assert guard["steps"][1]["with"] == {"fetch-depth": 0, "persist-credentials": False}
    script = guard["steps"][2]["run"]
    assert "${{" not in script
    for sha, allowed in [(production, True), (unmerged, False), ("not-a-sha", False)]:
        result = subprocess.run(["/bin/bash", "-c", script], cwd=tmp_path,
                                env={"PATH": os.environ["PATH"], "SOURCE_SHA": sha},
                                capture_output=True, text=True, timeout=5)
        assert (result.returncode == 0) is allowed


@pytest.mark.parametrize("mutation", ["remove-need", "always-bypass"])
def test_production_guard_bypass_mutations_are_detected(mutation):
    value = copy.deepcopy(workflow("deploy-phase-detector.yml"))
    if mutation == "remove-need":
        del value["jobs"]["deploy"]["needs"]
    else:
        value["jobs"]["deploy"]["if"] = "always()"
    with pytest.raises(AssertionError):
        assert_production_dependency_graph(value)


def test_changed_yaml_and_guard_shell_are_parseable():
    for name in set(CORE_WORKFLOWS + PRODUCTION_WORKFLOWS + ["ci-packages.yml", "runtime-smoke.yml"]):
        value = workflow(name)
        assert isinstance(triggers(value), dict) and value["jobs"]
        for job in value["jobs"].values():
            assert 1 <= job["timeout-minutes"] <= 90
        guard = value["jobs"].get("admit-production")
        if guard:
            for step in guard["steps"]:
                if "run" in step:
                    result = subprocess.run(["/bin/bash", "-n"], input=step["run"],
                                            capture_output=True, text=True, timeout=5)
                    assert result.returncode == 0, result.stderr


def runtime_steps(value=None):
    value = value or workflow("runtime-smoke.yml")
    return value["jobs"]["import-smoke"]["steps"]


def embedded_python(step):
    # Both executable heredocs are quoted; their Python source is not shell
    # interpolated. Tests run the actual checked-in verifier/import bodies.
    return step["run"].split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]


def assert_linux_runtime_smoke_contract(value):
    events = triggers(value)
    for event in ("push", "pull_request"):
        paths = events[event]["paths"]
        assert "requirements/runtime-*.in" in paths
        assert "requirements/runtime-*.lock" in paths
    assert "schedule" in events and "workflow_dispatch" in events
    job = value["jobs"]["import-smoke"]
    assert_job_env_contexts(value)
    assert job["runs-on"] == "ubuntu-latest"
    assert "if" not in job and "continue-on-error" not in job
    steps = runtime_steps(value)
    initializer = steps[0]
    assert initializer.get("name") == "Initialize isolated runtime paths"
    assert "env" not in job
    assert "if" not in initializer and "continue-on-error" not in initializer
    assert '"$RUNNER_TEMP" >> "$GITHUB_ENV"' in initializer["run"]
    names = [step.get("name", "") for step in steps]
    required_order = [
        "Install pinned uv tool",
        "Sync independent Python 3.11 Linux CPU runtime with hashes",
        "Write locked graph validator",
        "Verify locked graph before checkout imports",
        "Import structural_isomorphism from the exact checkout",
        "Verify locked graph after checkout import",
        "Import every heavy module that prod loads at startup",
        "Load SearchService and answer with a generic model and tiny KB",
        "Verify locked graph after SearchService smoke",
        "Remove this job's isolated runtime",
    ]
    indices = [names.index(name) for name in required_order]
    assert indices == sorted(indices)
    selected = {step.get("name"): step for step in steps}
    assert selected[required_order[0]]["run"] == "python -m pip install uv==0.11.8"
    sync = selected[required_order[1]]["run"]
    for fragment in (
        "uv venv --python", "--no-managed-python --no-python-downloads",
        'uv pip sync --python "$RUNTIME_PYTHON" --torch-backend cpu',
        "--require-hashes --strict", "requirements/runtime-linux-cpu.lock",
        'uv pip check --python "$RUNTIME_PYTHON"',
    ):
        assert fragment in sync
    assert "--no-deps" not in sync and "--no-verify-hashes" not in sync
    source = selected[required_order[4]]
    assert source["env"]["PYTHONPATH"] == "${{ github.workspace }}"
    assert source["env"]["EXPECTED_SOURCE_SHA"] == "${{ github.sha }}"
    assert "structural_isomorphism.__file__" in source["run"]
    assert "actual != os.environ" in source["run"]
    assert source["run"].index('find_spec("structural_isomorphism")') < source["run"].index("import structural_isomorphism\n")
    for name in required_order[:-1]:
        assert "if" not in selected[name] and "continue-on-error" not in selected[name]
    for name in [required_order[3], required_order[5], required_order[8]]:
        assert '"$RUNTIME_PYTHON" -I' in selected[name]["run"]
        assert 'uv pip check --python "$RUNTIME_PYTHON"' in selected[name]["run"]
    heavy = ast.parse(embedded_python(selected[required_order[6]]))
    modules = next(node for node in ast.walk(heavy)
                   if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "mods" for target in node.targets))
    assert ast.literal_eval(modules.value) == [
        "sentence_transformers", "transformers", "torch", "httpx", "fastapi",
        "uvicorn", "pydantic", "slowapi", "structlog", "dotenv", "starlette",
    ]
    tiny = selected[required_order[7]]["run"]
    assert 'model_path="shibing624/text2vec-base-chinese"' in tiny
    assert 'service.search("test phenomenon", top_k=2)' in tiny
    assert "service.kb_size != 2 or not hits" in tiny
    assert "TemporaryDirectory" in tiny
    assert selected[required_order[-1]]["if"] == "always()"


def test_linux_runtime_smoke_preserves_real_work_and_hash_graph_boundaries():
    assert_linux_runtime_smoke_contract(workflow("runtime-smoke.yml"))


@pytest.mark.parametrize("mutation", ["no-hashes", "wrong-backend", "missing-postcheck", "skipped-import"])
def test_linux_runtime_smoke_boundary_mutations_fail(mutation):
    value = copy.deepcopy(workflow("runtime-smoke.yml"))
    steps = runtime_steps(value)
    selected = {step.get("name"): step for step in steps}
    sync = selected["Sync independent Python 3.11 Linux CPU runtime with hashes"]
    if mutation == "no-hashes":
        sync["run"] = sync["run"].replace("--require-hashes", "")
    elif mutation == "wrong-backend":
        sync["run"] = sync["run"].replace("--torch-backend cpu", "--torch-backend auto")
    elif mutation == "missing-postcheck":
        steps.remove(selected["Verify locked graph after checkout import"])
    else:
        selected["Import structural_isomorphism from the exact checkout"]["if"] = "false"
    with pytest.raises((AssertionError, ValueError)):
        assert_linux_runtime_smoke_contract(value)


def runtime_verifier():
    step = next(step for step in runtime_steps() if step.get("name") == "Write locked graph validator")
    namespace = {"__name__": "runtime_lock_contract_fixture"}
    exec(compile(embedded_python(step), "<checked-in-runtime-verifier>", "exec"), namespace)
    return namespace


def synthetic_runtime_lock(pins):
    # Mock metadata tests verify rejection logic, not a Linux installation.
    return "".join(f"{name}=={version} \\\n    --hash=sha256:{'a' * 64}\n" for name, version in pins.items())


def synthetic_runtime_pins():
    pins = {"fastapi": "0.135.0", "pydantic": "2.7.4", "starlette": "1.3.1",
            "pyjwt": "2.15.1", "uvicorn": "0.27.1", "httpx": "0.27.2",
            "slowapi": "0.1.9", "structlog": "25.5.0", "torch": "2.14.1+cpu"}
    pins.update({f"fixture-{index}": "1.0" for index in range(64)})
    return pins


@pytest.mark.parametrize("mutation", [
    "valid", "wrong-version", "extra-package", "missing-package", "nvidia",
    "noncpu-torch", "cuda-build", "wrong-platform", "wrong-python", "missing-hash",
])
def test_actual_locked_graph_verifier_accepts_control_and_rejects_drift(mutation):
    pins = synthetic_runtime_pins()
    if mutation == "nvidia":
        pins["nvidia-cuda-runtime-cu12"] = pins.pop("fixture-0")
    installed = dict(pins)
    if mutation == "wrong-version":
        installed["fastapi"] = "0.115.14"
    elif mutation == "extra-package":
        installed["unapproved-package"] = "1.0"
    elif mutation == "missing-package":
        installed.pop("fixture-0")
    text = synthetic_runtime_lock(pins)
    if mutation == "missing-hash":
        text = text.replace("--hash=sha256:", "--hash=sha512:", 1)
    arguments = (text, installed, "2.14.1" if mutation == "noncpu-torch" else "2.14.1+cpu",
                 "12.8" if mutation == "cuda-build" else None,
                 "Darwin" if mutation == "wrong-platform" else "Linux", "x86_64",
                 (3, 12) if mutation == "wrong-python" else (3, 11))
    verify = runtime_verifier()["verify_runtime"]
    if mutation == "valid":
        assert verify(*arguments) == pins
    else:
        with pytest.raises(SystemExit):
            verify(*arguments)


@pytest.mark.parametrize("wrong_source,wrong_sha", [(False, False), (True, False), (False, True)])
def test_actual_checkout_binding_script_rejects_foreign_source_and_sha(tmp_path, wrong_source, wrong_sha):
    source = tmp_path / "source"
    foreign = tmp_path / "foreign"
    for root in (source, foreign):
        package = root / "structural_isomorphism"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("CHECKOUT_FIXTURE = True\n")
    marker = tmp_path / "foreign-imported"
    (foreign / "structural_isomorphism/__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    subprocess.run(["git", "init", "-q"], cwd=source, check=True)
    subprocess.run(["git", "add", "structural_isomorphism/__init__.py"], cwd=source, check=True)
    subprocess.run(["git", "-c", "user.name=B0", "-c", "user.email=b0@example.invalid",
                    "commit", "-qm", "source"], cwd=source, check=True)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    step = next(step for step in runtime_steps() if step.get("name") == "Import structural_isomorphism from the exact checkout")
    cwd = foreign if wrong_source else source
    result = subprocess.run([os.sys.executable, "-c", embedded_python(step)], cwd=cwd,
                            env={"PATH": os.environ["PATH"], "PYTHONPATH": str(cwd),
                                 "GITHUB_WORKSPACE": str(source),
                                 "EXPECTED_SOURCE_SHA": "0" * 40 if wrong_sha else sha},
                            capture_output=True, text=True, timeout=5)
    assert (result.returncode == 0) is (not wrong_source and not wrong_sha)
    assert not marker.exists(), "foreign package must be refused before its code executes"
    if wrong_source:
        assert "source resolves outside the checkout" in result.stderr
    elif wrong_sha:
        assert "checkout SHA mismatch" in result.stderr


def assert_job_env_contexts(value):
    # GitHub's Context availability table restricts jobs.<job_id>.env to
    # these roots; runner/env/job/steps are available at other keys only.
    # This is a narrow context check, not a full Actions expression parser.
    allowed = {"github", "needs", "strategy", "matrix", "vars", "secrets", "inputs"}
    functions = {"contains", "startswith", "endswith", "format", "join", "tojson", "fromjson"}
    for job in value["jobs"].values():
        for item in job.get("env", {}).values():
            if not isinstance(item, str):
                continue
            for expression in re.findall(r"\$\{\{(.*?)\}\}", item, re.S):
                # Quoted literals such as 'runner.temp' aren't context uses.
                expression = re.sub(r"'(?:[^']|'')*'", "''", expression)
                for token in re.finditer(r"(?<![.\w])([A-Za-z_][A-Za-z0-9_]*)(?:\s*\.\s*[A-Za-z_][A-Za-z0-9_-]*|\s*\[\s*\])*", expression):
                    name = token[1].lower()
                    if name in {"true", "false", "null"}:
                        continue
                    if expression[token.end():].lstrip().startswith("("):
                        assert name in functions, f"disallowed job-env function: {name}"
                    else:
                        assert name in allowed, f"disallowed job-env context: {name}"


@pytest.mark.parametrize("expression", [
    "${{ github.sha }}", "${{ needs.prepare.outputs.path }}", "${{ strategy.job-index }}",
    "${{ matrix.python }}", "${{ vars.RUNTIME_PATH }}", "${{ secrets.DEPLOY_KEY }}",
    "${{ inputs.path }}", "${{ format('runner.temp {0}', github.ref) }}",
])
def test_job_env_allowed_contexts_and_quoted_runner_literals(expression):
    assert_job_env_contexts({"jobs": {"probe": {"env": {"VALUE": expression}}}})


@pytest.mark.parametrize("expression", [
    "${{ runner.temp }}", "${{ runner['temp'] }}", "${{ toJSON(runner) }}",
    "${{ env.RUNTIME_ENV }}", "${{ job.status }}", "${{ steps.prepare.outputs.path }}",
    "${{ hashFiles('requirements/*.lock') }}",
])
def test_job_env_runner_and_other_unavailable_contexts_are_rejected(expression):
    with pytest.raises(AssertionError):
        assert_job_env_contexts({"jobs": {"probe": {"env": {"VALUE": expression}}}})


def test_original_job_env_runner_annotation_is_detected():
    value = copy.deepcopy(workflow("runtime-smoke.yml"))
    value["jobs"]["import-smoke"]["env"] = {
        "RUNTIME_ENV": "${{ runner.temp }}/structural-runtime-smoke",
        "RUNTIME_PYTHON": "${{ runner.temp }}/structural-runtime-smoke/bin/python",
    }
    with pytest.raises(AssertionError, match="disallowed job-env context: runner"):
        assert_job_env_contexts(value)


def test_runtime_path_step_exports_exact_paths_and_cleanup_is_scoped(tmp_path):
    runner_temp = tmp_path / "runner temp"
    runner_temp.mkdir()
    env_file = tmp_path / "github-env"
    steps = runtime_steps()
    initial = steps[0]["run"]
    env = {"PATH": os.environ["PATH"], "RUNNER_TEMP": str(runner_temp), "GITHUB_ENV": str(env_file)}
    result = subprocess.run(["/bin/bash", "-c", initial], env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    exported = dict(line.split("=", 1) for line in env_file.read_text().splitlines())
    runtime = runner_temp / "structural-runtime-smoke"
    assert exported == {"RUNTIME_ENV": str(runtime), "RUNTIME_PYTHON": str(runtime / "bin/python")}
    assert not runtime.exists(), "initialization must not install or start the runtime"
    cleanup = next(step["run"] for step in steps if step.get("name") == "Remove this job's isolated runtime")
    checker = runner_temp / "structural-runtime-lock-check.py"
    checker.write_text("owned fixture")
    unowned = tmp_path / "unowned"
    unowned.mkdir()
    marker = unowned / "keep"
    marker.write_text("must remain")
    refused = subprocess.run(["/bin/bash", "-c", cleanup],
                             env={**env, "RUNTIME_ENV": str(unowned)},
                             capture_output=True, text=True, timeout=5)
    assert refused.returncode != 0
    assert marker.is_file() and checker.is_file()
    runtime.mkdir()
    (runtime / "owned").write_text("fixture")
    removed = subprocess.run(["/bin/bash", "-c", cleanup], env={**env, **exported},
                             capture_output=True, text=True, timeout=5)
    assert removed.returncode == 0, removed.stderr
    assert not runtime.exists() and not checker.exists()
    assert marker.read_text() == "must remain"


RESEARCH_COVERAGE_COMMAND = [
    'python', '-m', 'coverage', 'run', '-p', '--rcfile=.coveragerc', '-m', 'pytest',
    'tests/test_research_evidence.py', 'tests/test_research_sources.py',
    'tests/test_research_formula.py', 'tests/test_research_provider_adapter.py',
    'tests/test_research_model_report.py', 'tests/test_research_financial.py',
    'tests/test_research_financial_result_adapter.py', 'tests/test_research_usage_upper.py',
    '$PYTEST_FLAGS',
]


def _assert_research_coverage_closure(value, rcfile):
    job = copy.deepcopy(value['jobs']['coverage'])
    step = next(s for s in job['steps'] if s.get('name') == 'Run coverage (split by suite, parallel files combined)')
    commands = [shlex.split(line, comments=True)
                for line in re.sub(r'\\\n\s*', ' ', step['run']).splitlines()
                if shlex.split(line, comments=True)]
    assert commands[-1] == ['python', '-m', 'coverage', 'combine', '--rcfile=.coveragerc']
    assert commands[-2] == RESEARCH_COVERAGE_COMMAND
    assert sum(command == RESEARCH_COVERAGE_COMMAND for command in commands) == 1
    step['run'] = commands[:-2] + commands[-1:]
    # Freeze the reviewed job, suites, limits and reports, apart from this one
    # added parallel measurement. Ignore comments/line wrapping in its script.
    assert hashlib.sha256(json.dumps(job, sort_keys=True, separators=(',', ':')).encode()).hexdigest() == '601c495e11c7d17017b64fc745760cbf9e80d369a8bdf35a2d217a4a39c574ee'
    assert hashlib.sha256(rcfile.encode()).hexdigest() == 'd99a2766d35215d1249c6f0388d8bb9effa7faec8ed715c040f897d6314847af'


def test_coverage_measures_root_research_before_combining_without_weakening_gates():
    _assert_research_coverage_closure(workflow('coverage.yml'), (ROOT / '.coveragerc').read_text())


@pytest.mark.parametrize('mutation', ['missing_file', 'missing_parallel', 'wrong_rcfile',
    'ignore_failure', 'after_combine', 'legacy_suite', 'timeout', 'global_threshold', 'omit',
    'missing_financial', 'missing_financial_adapter', 'missing_usage_upper'])
def test_research_coverage_closure_rejects_incomplete_or_relaxed_pipeline(mutation):
    value = workflow('coverage.yml')
    rcfile = (ROOT / '.coveragerc').read_text()
    step = next(s for s in value['jobs']['coverage']['steps'] if s.get('name') == 'Run coverage (split by suite, parallel files combined)')
    marker = '# Root research contracts'
    before, added = step['run'].split(marker, 1)
    if mutation == 'missing_file':added = added.replace('tests/test_research_model_report.py', '')
    elif mutation == 'missing_financial':added = added.replace('tests/test_research_financial.py', '')
    elif mutation == 'missing_financial_adapter':added = added.replace('tests/test_research_financial_result_adapter.py', '')
    elif mutation == 'missing_usage_upper':added = added.replace('tests/test_research_usage_upper.py', '')
    elif mutation == 'missing_parallel':added = added.replace('coverage run -p', 'coverage run')
    elif mutation == 'wrong_rcfile':added = added.replace('--rcfile=.coveragerc', '--rcfile=other.ini', 1)
    elif mutation == 'ignore_failure':added = added.replace('$PYTEST_FLAGS', '$PYTEST_FLAGS || true')
    elif mutation == 'after_combine':
        added = added.replace('python -m coverage combine --rcfile=.coveragerc\n', '')
        before += 'python -m coverage combine --rcfile=.coveragerc\n'
    elif mutation == 'legacy_suite':before = before.replace('packages/guarded-llm/tests/', 'packages/guarded-llm/missing/')
    elif mutation == 'timeout':value['jobs']['coverage']['timeout-minutes'] = 25
    elif mutation == 'global_threshold':rcfile = rcfile.replace('fail_under = 80', 'fail_under = 79')
    else:rcfile += '\n    web/backend/research/*\n'
    step['run'] = before + marker + added
    with pytest.raises(AssertionError):_assert_research_coverage_closure(value, rcfile)


# The backend baseline outgrew the original single-job wall budget. Both
# complete jobs remain hard requirements; only the existing sanity context
# is the branch-protection aggregate.
SANITY_SPLIT_DIGESTS = {
    "sanity-backend": "4135a5d81f35ed7c9155fa239f18644f51174d2bd8b9cacfd200cfef7a717798",
    "sanity": "c969dc72598a5d59f4eb6d3d220ea70b0a911590228d3793a4e89225c65664ca",
}


def _assert_sanity_backend_dependency(value):
    jobs = value["jobs"]
    assert set(jobs) == {"sanity-backend", "sanity"}
    backend, aggregate = jobs["sanity-backend"], jobs["sanity"]
    assert "if" not in backend and "needs" not in backend
    assert aggregate["needs"] == ["sanity-backend"]
    assert aggregate["if"] == "always()"
    assert aggregate["name"] == "sanity"
    assert backend["timeout-minutes"] == 45
    assert aggregate["timeout-minutes"] == 25
    for job in (backend, aggregate):
        assert "continue-on-error" not in job
    assert all("if" not in step and "continue-on-error" not in step
               for step in backend["steps"])
    gate = aggregate["steps"][0]
    assert gate["name"] == "Require complete backend baseline success"
    assert gate["env"] == {
        "SANITY_BACKEND_RESULT": "${{ needs['sanity-backend'].result }}",
    }
    assert "if" not in gate and "continue-on-error" not in gate
    for name, expected in SANITY_SPLIT_DIGESTS.items():
        actual = hashlib.sha256(json.dumps(
            jobs[name], sort_keys=True, separators=(",", ":"),
        ).encode()).hexdigest()
        assert actual == expected, f"complete sanity job changed: {name}"


def test_sanity_runs_complete_backend_and_gates_all_remaining_legs():
    _assert_sanity_backend_dependency(workflow("sanity.yml"))


@pytest.mark.parametrize("result", ["success", "failure", "cancelled", "skipped", "", "unknown", None])
def test_required_sanity_rejects_every_unsuccessful_backend_result(result):
    value = workflow("sanity.yml")
    _assert_sanity_backend_dependency(value)
    gate = value["jobs"]["sanity"]["steps"][0]
    env = {"PATH": "/usr/bin:/bin"}
    if result is not None:
        env["SANITY_BACKEND_RESULT"] = result
    actual = subprocess.run(
        ["/bin/bash", "-e", "-c", gate["run"]], env=env,
        capture_output=True, text=True, timeout=5,
    )
    assert (actual.returncode == 0) is (result == "success")


@pytest.mark.parametrize("mutation", [
    "missing_backend", "missing_dependency", "wrong_dependency", "missing_gate",
    "missing_result", "hardcoded_success", "gate_soft", "gate_if", "job_soft",
    "backend_soft", "backend_if", "backend_step_soft", "backend_timeout",
    "aggregate_timeout", "missing_backend_suite", "partial_backend_suite",
    "missing_backend_runtime", "changed_backend_runtime", "missing_lfs",
    "missing_root_contracts", "missing_types", "missing_package",
])
def test_sanity_split_rejects_incomplete_or_softened_dependencies(mutation):
    value = workflow("sanity.yml")
    jobs = value["jobs"]
    backend, aggregate = jobs["sanity-backend"], jobs["sanity"]
    gate = aggregate["steps"][0]
    if mutation == "missing_backend": del jobs["sanity-backend"]
    elif mutation == "missing_dependency": del aggregate["needs"]
    elif mutation == "wrong_dependency": aggregate["needs"] = []
    elif mutation == "missing_gate": aggregate["steps"].pop(0)
    elif mutation == "missing_result": gate["env"] = {}
    elif mutation == "hardcoded_success": gate["run"] = "exit 0"
    elif mutation == "gate_soft": gate["continue-on-error"] = True
    elif mutation == "gate_if": gate["if"] = "false"
    elif mutation == "job_soft": aggregate["continue-on-error"] = True
    elif mutation == "backend_soft": backend["continue-on-error"] = True
    elif mutation == "backend_if": backend["if"] = "false"
    elif mutation == "backend_step_soft": backend["steps"][-1]["continue-on-error"] = True
    elif mutation == "backend_timeout": backend["timeout-minutes"] = 26
    elif mutation == "aggregate_timeout": aggregate["timeout-minutes"] = 26
    elif mutation == "missing_lfs": backend["steps"][0]["with"]["lfs"] = False
    elif mutation in ("missing_backend_suite", "partial_backend_suite"):
        step = next(s for s in backend["steps"] if s.get("name") == "Leg 2 — web/backend pytest baseline")
        step["run"] = "true" if mutation == "missing_backend_suite" else "python -m pytest tests -k smoke"
    elif mutation in ("missing_backend_runtime", "changed_backend_runtime"):
        step = next(s for s in backend["steps"] if s.get("name") == "Install web/backend deps")
        step["run"] = "true" if mutation == "missing_backend_runtime" else "pip install fastapi"
    else:
        name = {"missing_root_contracts": "Leg 3 — offline root release contracts",
                "missing_types": "Leg 3 — reproducible API TypeScript artifact",
                "missing_package": "Leg 4 — packages/reject-aware-critic tests"}[mutation]
        next(s for s in aggregate["steps"] if s.get("name") == name)["run"] = "true"
    with pytest.raises((AssertionError, KeyError)):
        _assert_sanity_backend_dependency(value)
