"""NOT_GATE workflow contracts; no collector/browser/trace is executed."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/beta-perf.yml"
REPO = "dada8899/structural-isomorphism"
HEAD_REF = "bootstrap/structure-ci-20261016"
DIAGNOSTIC = "NOT_GATE one marked Linux diagnostic pair"
UPLOAD = "Upload NOT_GATE Linux diagnostic evidence"
GRADE = "Audit beta surfaces against the existing product budget"
CLEANUP = "Stop local beta server"
ORIGINAL_UPLOAD = "Upload beta performance evidence"
ORIGINAL_GRADE_COMMAND = (
    "python scripts/beta_perf_audit.py --base http://127.0.0.1:4173 "
    "--runs 3 --budget perf-budget.json --out /tmp/beta-perf-audit.json"
)
# Original job plus the approved explicit PyYAML dependency (no gate change).
ORIGINAL_JOB_DIGEST = "1ff605671ee6159516eb8f0ca7b1860c415fd1b9dff887c935f832b491ba4348"
PREDICATES = [
    "always()", "!cancelled()", f"github.repository == '{REPO}'",
    "github.event_name == 'pull_request'", "github.event.action == 'synchronize'",
    "github.event.pull_request.number == 253",
    "github.event.pull_request.head.repo.full_name == github.repository",
    "github.event.pull_request.base.repo.full_name == github.repository",
    f"github.event.pull_request.head.ref == '{HEAD_REF}'", "github.run_attempt == '1'",
]
RAN = "(steps.beta_perf_diagnostic.outcome == 'success' || steps.beta_perf_diagnostic.outcome == 'failure')"


def load_workflow():
    return yaml.safe_load(WORKFLOW.read_text())


def expression(predicates):
    return "${{ " + " && ".join(predicates) + " }}"


def normalized(value):
    return " ".join(value.split())


def steps_by_name(value):
    return {step.get("name", "checkout"): step for step in value["jobs"]["beta-perf-audit"]["steps"]}


def assert_hook(value):
    assert list(value["jobs"]) == ["beta-perf-audit"], "no new diagnostic job"
    assert value["permissions"] == {"contents": "read"}
    job = value["jobs"]["beta-perf-audit"]
    assert "if" not in job and "continue-on-error" not in job
    steps = job["steps"]
    names = [step.get("name", "checkout") for step in steps]
    selected = steps_by_name(value)
    assert names.index(GRADE) < names.index(DIAGNOSTIC) < names.index(CLEANUP)
    assert names.index(CLEANUP) < names.index(ORIGINAL_UPLOAD) < names.index(UPLOAD)
    assert all("continue-on-error" not in step for step in steps)
    assert steps[0] == {"uses": "actions/checkout@v4", "with": {"fetch-depth": 2}}
    assert selected["Install locked browser runtime"]["run"] == (
        "python -m pip install pytest==9.0.3 playwright==1.59.0 pydantic==2.7.4 PyYAML==6.0.3\n"
        "python -m playwright install --with-deps chromium\n"
    )
    grade = selected[GRADE]
    assert grade == {"name": GRADE, "id": "beta_perf_gate", "run": ORIGINAL_GRADE_COMMAND}
    diagnostic = selected[DIAGNOSTIC]
    assert set(diagnostic) == {"name", "id", "if", "timeout-minutes", "env", "run"}
    assert diagnostic["id"] == "beta_perf_diagnostic"
    assert diagnostic["timeout-minutes"] == 5
    assert normalized(diagnostic["if"]) == normalized(expression(PREDICATES))
    assert diagnostic["env"] == {"ORIGINAL_GRADE_OUTCOME": "${{ steps.beta_perf_gate.outcome }}"}
    assert diagnostic["run"] == (
        "python scripts/beta_perf_diagnostics.py --grade-artifact /tmp/beta-perf-audit.json "
        '--grade-outcome "$ORIGINAL_GRADE_OUTCOME" --base http://127.0.0.1:4173/ '
        '--out "$RUNNER_TEMP/structure-perf-linux-r2-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"'
    )
    upload = selected[UPLOAD]
    assert set(upload) == {"name", "if", "uses", "with"}
    assert normalized(upload["if"]) == normalized(expression([*PREDICATES, RAN]))
    assert upload["uses"] == "actions/upload-artifact@v4"
    assert upload["with"] == {
        "name": "structure-perf-linux-r2-${{ github.run_id }}-${{ github.run_attempt }}",
        "path": "${{ runner.temp }}/structure-perf-linux-r2-${{ github.run_id }}-${{ github.run_attempt }}/",
        "if-no-files-found": "ignore",
    }
    assert "$RUNNER_TEMP" not in upload["with"]["path"]
    assert "always()" == selected[CLEANUP]["if"] == selected[ORIGINAL_UPLOAD]["if"]
    # Strip only the three approved additions to verify every original job
    # field/step/command (including upload layout and cleanup) is identical.
    original = copy.deepcopy(job)
    original["steps"] = [step for step in original["steps"] if step.get("name") not in {DIAGNOSTIC, UPLOAD}]
    del original["steps"][0]["with"]
    del next(step for step in original["steps"] if step.get("name") == GRADE)["id"]
    actual = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert actual == ORIGINAL_JOB_DIGEST, "original grade/work/cleanup/upload drift"


def evaluate(condition, github, steps, *, cancelled=False):
    """Small bounded condition evaluator, not GitHub's expression engine."""
    text = normalized(condition).removeprefix("${{").removesuffix("}}")
    text = re.sub(r"!(?!=)", "not ", text).replace("&&", " and ").replace("||", " or ").strip()

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return {"github": github, "steps": steps}[node.id]
        if isinstance(node, ast.Attribute):
            base = visit(node.value)
            return base.get(node.attr) if isinstance(base, dict) else None
        if isinstance(node, ast.BoolOp):
            return all(visit(item) for item in node.values) if isinstance(node.op, ast.And) else any(visit(item) for item in node.values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.Compare):
            assert len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)
            return visit(node.left) == visit(node.comparators[0])
        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name) and not node.args and not node.keywords
            assert node.func.id in {"always", "cancelled"}
            return True if node.func.id == "always" else cancelled
        raise AssertionError(f"unsupported condition node: {ast.dump(node)}")

    return visit(ast.parse(text, mode="eval"))


def approved_event():
    return {"repository": REPO, "event_name": "pull_request", "run_attempt": "1",
            "event": {"action": "synchronize", "pull_request": {
                "number": 253, "head": {"repo": {"full_name": REPO}, "ref": HEAD_REF},
                "base": {"repo": {"full_name": REPO}},
            }}}


def test_original_perf_gate_and_closed_diagnostic_hook_contract():
    assert_hook(load_workflow())


@pytest.mark.parametrize("mutation", [
    "push", "opened", "reopened", "attempt2", "other-pr", "other-repo", "fork-head", "fork-base", "other-ref", "cancelled",
])
def test_disallowed_events_cannot_collect_or_upload_even_with_forged_ran_outcome(mutation):
    event = approved_event()
    if mutation == "push":
        event["event_name"] = "push"
    elif mutation in {"opened", "reopened"}:
        event["event"]["action"] = mutation
    elif mutation == "attempt2":
        event["run_attempt"] = "2"
    elif mutation == "other-pr":
        event["event"]["pull_request"]["number"] = 254
    elif mutation == "other-repo":
        event["repository"] = "other/structural-isomorphism"
    elif mutation in {"fork-head", "fork-base"}:
        side = "head" if mutation == "fork-head" else "base"
        event["event"]["pull_request"][side]["repo"]["full_name"] = "fork/structural-isomorphism"
    elif mutation == "other-ref":
        event["event"]["pull_request"]["head"]["ref"] = "feature/other"
    selected = steps_by_name(load_workflow())
    state = {"beta_perf_gate": {"outcome": "failure"}, "beta_perf_diagnostic": {"outcome": "success"}}
    assert evaluate(selected[DIAGNOSTIC]["if"], event, state, cancelled=mutation == "cancelled") is False
    assert evaluate(selected[UPLOAD]["if"], event, state, cancelled=mutation == "cancelled") is False


@pytest.mark.parametrize("grade_outcome", ["success", "failure"])
def test_approved_event_collects_both_original_red_and_green(grade_outcome):
    selected = steps_by_name(load_workflow())
    state = {"beta_perf_gate": {"outcome": grade_outcome}, "beta_perf_diagnostic": {"outcome": "success"}}
    assert evaluate(selected[DIAGNOSTIC]["if"], approved_event(), state) is True
    assert evaluate(selected[UPLOAD]["if"], approved_event(), state) is True


@pytest.mark.parametrize("outcome,allowed", [("success", True), ("failure", True), ("skipped", False), ("cancelled", False), ("", False)])
def test_second_artifact_requires_a_completed_actual_diagnostic_step(outcome, allowed):
    condition = steps_by_name(load_workflow())[UPLOAD]["if"]
    assert evaluate(condition, approved_event(), {"beta_perf_diagnostic": {"outcome": outcome}}) is allowed


@pytest.mark.parametrize("step_name", [DIAGNOSTIC, UPLOAD])
@pytest.mark.parametrize("index", range(len(PREDICATES)))
@pytest.mark.parametrize("mutation", ["delete", "widen"])
def test_deleting_or_widening_any_admission_condition_is_rejected(step_name, index, mutation):
    value = load_workflow()
    predicates = list(PREDICATES)
    if mutation == "delete":
        predicates.pop(index)
    else:
        predicates[index] = "true"
    if step_name == UPLOAD:
        predicates.append(RAN)
    steps_by_name(value)[step_name]["if"] = expression(predicates)
    with pytest.raises(AssertionError):
        assert_hook(value)


@pytest.mark.parametrize("mutation", ["soft-grade", "grade-command", "timeout", "artifact-path", "missing-yaml", "no-cleanup"])
def test_grade_timeout_artifact_and_cleanup_cannot_be_softened(mutation):
    value = load_workflow()
    selected = steps_by_name(value)
    if mutation == "soft-grade":
        selected[GRADE]["continue-on-error"] = True
    elif mutation == "grade-command":
        selected[GRADE]["run"] += " || true"
    elif mutation == "timeout":
        selected[DIAGNOSTIC]["timeout-minutes"] = 10
    elif mutation == "artifact-path":
        selected[UPLOAD]["with"]["path"] = "$RUNNER_TEMP/structure-perf-linux-r2"
    elif mutation == "missing-yaml":
        selected["Install locked browser runtime"]["run"] = selected["Install locked browser runtime"]["run"].replace(" PyYAML==6.0.3", "")
    else:
        value["jobs"]["beta-perf-audit"]["steps"].remove(selected[CLEANUP])
    with pytest.raises((AssertionError, ValueError)):
        assert_hook(value)


def test_actual_grade_exit_is_not_swallowed_and_cli_receives_real_outcome_and_expanded_path(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python"
    fake_python.write_text(
        "#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.exit(int(os.environ['FAKE_EXIT']))\n"
    )
    fake_python.chmod(0o755)
    selected = steps_by_name(load_workflow())
    env = {"PATH": f"{fake_bin}:{Path(sys.executable).parent}:{os.defpath}",
           "RECORD": str(tmp_path / "grade-args.json"), "FAKE_EXIT": "7"}
    grade = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", selected[GRADE]["run"]],
                           env=env, capture_output=True, text=True, timeout=5)
    assert grade.returncode == 7
    assert json.loads(Path(env["RECORD"]).read_text()) == [
        "scripts/beta_perf_audit.py", "--base", "http://127.0.0.1:4173", "--runs", "3",
        "--budget", "perf-budget.json", "--out", "/tmp/beta-perf-audit.json",
    ]
    runner = tmp_path / "runner temp"
    env.update(RECORD=str(tmp_path / "diagnostic-args.json"), FAKE_EXIT="0", ORIGINAL_GRADE_OUTCOME="failure",
               RUNNER_TEMP=str(runner), GITHUB_RUN_ID="77", GITHUB_RUN_ATTEMPT="1")
    diagnostic = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", selected[DIAGNOSTIC]["run"]],
                                env=env, capture_output=True, text=True, timeout=5)
    assert diagnostic.returncode == 0 and grade.returncode == 7
    out = runner / "structure-perf-linux-r2-77-1"
    assert json.loads(Path(env["RECORD"]).read_text()) == [
        "scripts/beta_perf_diagnostics.py", "--grade-artifact", "/tmp/beta-perf-audit.json",
        "--grade-outcome", "failure", "--base", "http://127.0.0.1:4173/", "--out", str(out),
    ]
    rendered = selected[UPLOAD]["with"]["path"].replace("${{ runner.temp }}", str(runner)).replace(
        "${{ github.run_id }}", "77").replace("${{ github.run_attempt }}", "1")
    assert rendered == str(out) + "/"
    assert not out.exists(), "test doubles must not fabricate capture artifacts"


def test_shell_and_workflow_yaml_parse_without_executing_audit_or_trace():
    value = load_workflow()
    for step in value["jobs"]["beta-perf-audit"]["steps"]:
        if "run" in step:
            result = subprocess.run(["bash", "-n"], input=step["run"],
                                    capture_output=True, text=True, timeout=5)
            assert result.returncode == 0, result.stderr
