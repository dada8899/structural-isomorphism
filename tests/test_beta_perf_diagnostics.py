"""No browser, profiler, network, or capture is started by these tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
import json
import os
import stat
import sys

import pytest

from scripts import beta_perf_diagnostics as diag


def event_identity():
    env = {"GITHUB_REPOSITORY": diag.REPOSITORY, "GITHUB_EVENT_NAME": "pull_request",
           "GITHUB_RUN_ATTEMPT": "1", "GITHUB_RUN_ID": "123456", "GITHUB_SHA": "a" * 40}
    event = {"action": "synchronize", "pull_request": {"number": 253,
        "head": {"sha": "b" * 40, "repo": {"full_name": diag.REPOSITORY}},
        "base": {"repo": {"full_name": diag.REPOSITORY}}}}
    return env, event


@pytest.mark.parametrize("field,value", [
    ("GITHUB_EVENT_NAME", "push"), ("GITHUB_EVENT_NAME", "workflow_dispatch"),
    ("GITHUB_REPOSITORY", "other/repo"), ("GITHUB_RUN_ATTEMPT", "2"),
    ("GITHUB_RUN_ATTEMPT", "01"),
])
def test_unapproved_events_do_not_admit(field, value):
    env, event = event_identity()
    env[field] = value
    with pytest.raises(diag.NotScheduled):
        diag.validate_event(env, event)


@pytest.mark.parametrize("action", ["opened", "reopened", "closed", "edited"])
def test_only_synchronize(action):
    env, event = event_identity()
    event["action"] = action
    with pytest.raises(diag.NotScheduled):
        diag.validate_event(env, event)


@pytest.mark.parametrize("mutation", ["fork", "wrong_pr", "string_pr", "base_repo"])
def test_pr_identity_is_exact(mutation):
    env, event = event_identity()
    pr = event["pull_request"]
    if mutation == "fork": pr["head"]["repo"]["full_name"] = "fork/repo"
    elif mutation == "wrong_pr": pr["number"] = 254
    elif mutation == "string_pr": pr["number"] = "253"
    else: pr["base"]["repo"]["full_name"] = "other/repo"
    with pytest.raises(diag.NotScheduled):
        diag.validate_event(env, event)


def test_merge_checkout_and_pr_head_are_separate_identities():
    env, event = event_identity()
    identity = diag.validate_event(env, event)
    assert identity.checkout_sha == "a" * 40
    assert identity.head_sha == "b" * 40
    assert identity.run_id == "123456"


def binding_fixture(tmp_path, subject=diag.MARKER_SUBJECT):
    relative = "input.txt"
    (tmp_path / relative).write_bytes(b"approved")
    script = tmp_path / "scripts/beta_perf_diagnostics.py"
    script.parent.mkdir()
    script.write_bytes(b"reviewed diagnostic")
    identity = diag.Identity("a" * 40, "b" * 40, "123456")
    calls = []

    def read_git(root, *args):
        calls.append(args)
        assert root == tmp_path
        if args == ("rev-parse", "HEAD"): return b"a" * 40 + b"\n"
        if args == ("cat-file", "-t", "b" * 40): return b"commit\n"
        if args == ("show", "-s", "--format=%s", "b" * 40): return subject.encode() + b"\n"
        if args[0] == "show":
            return b"reviewed diagnostic" if args[1].endswith("scripts/beta_perf_diagnostics.py") else b"approved"
        raise AssertionError(args)
    return identity, {relative: diag.digest(b"approved")}, read_git, calls


def test_subject_is_exact_and_read_from_head_object(tmp_path):
    identity, pins, reader, calls = binding_fixture(tmp_path)
    result = diag.verify_binding(tmp_path, identity, pins=pins, read_git=reader)
    assert all(result[k] == v for k,v in pins.items())
    assert result["scripts/beta_perf_diagnostics.py"] == diag.digest(b"reviewed diagnostic")
    assert ("show", "-s", "--format=%s", identity.head_sha) in calls
    assert all("fetch" not in c for c in calls)


@pytest.mark.parametrize("suffix", [" changed", " ", "\nsecond subject"])
def test_wrong_nonce_or_subject_rejected(tmp_path, suffix):
    identity, pins, reader, _ = binding_fixture(tmp_path, diag.MARKER_SUBJECT + suffix)
    with pytest.raises(diag.NotScheduled):
        diag.verify_binding(tmp_path, identity, pins=pins, read_git=reader)


def test_source_or_script_drift_rejected_before_capture(tmp_path):
    identity, pins, reader, _ = binding_fixture(tmp_path)
    (tmp_path / "input.txt").write_bytes(b"unreviewed")
    with pytest.raises(diag.DiagnosticError, match="source_digest"):
        diag.verify_binding(tmp_path, identity, pins=pins, read_git=reader)
    (tmp_path / "input.txt").write_bytes(b"approved")
    (tmp_path / "scripts/beta_perf_diagnostics.py").write_bytes(b"unreviewed")
    with pytest.raises(diag.DiagnosticError, match="script_mismatch"):
        diag.verify_binding(tmp_path, identity, pins=pins, read_git=reader)


def test_missing_shallow_head_is_rejected_without_fetch(tmp_path):
    identity, pins, reader, _ = binding_fixture(tmp_path)
    def missing(root, *args):
        if args[0] == "cat-file": raise diag.DiagnosticError("required_git_object_unavailable")
        return reader(root, *args)
    with pytest.raises(diag.DiagnosticError, match="unavailable"):
        diag.verify_binding(tmp_path, identity, pins=pins, read_git=missing)


@pytest.mark.parametrize("ref", ["a" * 40, "b" * 40])
def test_each_git_source_identity_is_checked_not_only_worktree(tmp_path, ref):
    identity, pins, reader, _ = binding_fixture(tmp_path)
    def changed(root, *args):
        if args == ("show", f"{ref}:input.txt"): return b"different git object"
        return reader(root, *args)
    with pytest.raises(diag.DiagnosticError, match="source_digest"):
        diag.verify_binding(tmp_path, identity, pins=pins, read_git=changed)


def grade_value(status):
    sample = [{"run_index": n, "cleanup_status": "passed"} for n in (1, 2, 3)]
    return {"schema_version": 2, "engine": "scripts/perf_audit.py:audit_one", "runs_per_page": 3,
        "status": status, "base_url": "http://127.0.0.1:4173/",
        "profiles": {"mobile": {"cpu_throttle": 4, "network": "slow-4g"}, "tbt_window_ms": 5000},
        "source_snapshot_sha256": {p: diag.SOURCE_PINS[p] for p in diag.GRADE_SOURCE_PATHS},
        "pages": {name: {"path": diag.PAGE_PATHS.get(name, name + ".html"),
            "viewports": {vp: {"raw_runs": deepcopy(sample)} for vp in ("desktop", "mobile")}}
            for name in ("home", "search", "analyze", "reports", "discoveries", "classes", "papers", "tools")}}


@pytest.mark.parametrize("status", ["passed", "failed"])
def test_grade_red_or_green_both_eligible_and_never_rewritten(tmp_path, status):
    path = tmp_path / "grade.json"
    path.write_text(json.dumps(grade_value(status)))
    original = path.read_bytes()
    value, sha = diag.verify_grade(path)
    assert value["status"] == status
    assert sha == diag.digest(original)
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", ["source", "window", "profile", "raw_count", "case", "incomplete"])
def test_changed_or_unfinished_grade_rejected(tmp_path, change):
    value = grade_value("failed")
    if change == "source": value["source_snapshot_sha256"]["perf-budget.json"] = "0" * 64
    elif change == "window": value["profiles"]["tbt_window_ms"] = 1000
    elif change == "profile": value["profiles"]["mobile"]["cpu_throttle"] = 1
    elif change == "raw_count": value["pages"]["papers"]["viewports"]["mobile"]["raw_runs"].pop()
    elif change == "case": value["pages"]["analyze"]["path"] = "index.html"
    else: value["status"] = "running"
    path = tmp_path / "grade.json"
    path.write_text(json.dumps(value))
    with pytest.raises(diag.DiagnosticError): diag.verify_grade(path)


@pytest.mark.parametrize("base", ["http://localhost:4173/", "https://example.com/", "http://127.0.0.1:4173/?x=1"])
def test_no_arbitrary_service_or_redirect_target(base):
    with pytest.raises(diag.DiagnosticError): diag.validate_base(base, "http://127.0.0.1:4173/")


def test_actual_nonlinux_has_no_capture_override(monkeypatch):
    monkeypatch.setattr(diag.sys, "platform", "darwin")
    with pytest.raises(diag.DiagnosticError, match="linux_only"): diag.require_linux()


def test_attempt_reentry_and_existing_outputs_are_not_overwritten(tmp_path):
    out = tmp_path / "private"
    identity = diag.Identity("a" * 40, "b" * 40, "123456")
    diag.claim_attempt(out, identity)
    initial = (out / "attempt.started.json").read_bytes()
    with pytest.raises(FileExistsError): diag.claim_attempt(out, identity)
    assert (out / "attempt.started.json").read_bytes() == initial
    assert stat.S_IMODE(out.stat().st_mode) == 0o700
    assert stat.S_IMODE((out / "attempt.started.json").stat().st_mode) == 0o600


def test_capacity_and_artifact_paths_fail_closed(tmp_path):
    writer = diag.ArtifactWriter(tmp_path, limit=100)
    with pytest.raises(diag.DiagnosticError, match="capacity"):
        writer.write_chunks("timeline.json", [b"x" * 80])
    assert writer.used <= 100
    with pytest.raises(FileExistsError): writer.write_chunks("timeline.json", [b"x"])
    with pytest.raises(diag.DiagnosticError, match="name"):
        writer.write_json("../escape.json", {})


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now


class Browser:
    def __init__(self): self.connected = True; self.closes = 0
    def is_connected(self): return self.connected
    def close(self): self.connected = False; self.closes += 1


class Session:
    def __init__(self, complete=True, payload=None, fail_start=False):
        self.complete = complete; self.payload = payload or '{"traceEvents":[]}'
        self.fail_start = fail_start; self.calls = []; self.handler = None; self.detaches = 0
    def on(self, _name, handler): self.handler = handler
    def send(self, name, params=None):
        self.calls.append((name, params))
        if name == "Tracing.getCategories": return {"categories": diag.TRACE_CATEGORIES.split(",")}
        if name == "Tracing.start" and self.fail_start: raise RuntimeError("synthetic setup failure")
        if name == "Profiler.stop": return {"profile": {"nodes": [], "samples": [], "timeDeltas": []}}
        if name == "Tracing.end" and self.complete: self.handler({"stream": "fixture"})
        if name == "IO.read": return {"data": self.payload, "eof": True}
        return {}
    def detach(self): self.detaches += 1


class Page:
    def __init__(self, session=None, clock=None):
        self.session = session or Session(); self.clock = clock or Clock()
        self.context = SimpleNamespace(browser=Browser(), new_cdp_session=lambda _page: self.session)
    def evaluate(self, _script): return {"perf": {"longTasks": []}, "resources": []}
    def wait_for_timeout(self, ms): self.clock.now += ms / 1000


def sample(cleanup="pending"):
    return {"run_index": 1, "audit_status": "passed", "cleanup_status": cleanup,
            "stage": "complete", "tbt_ms": 250}


def test_duplicate_checkpoint_captures_once_and_cleanup_is_owned(tmp_path):
    page = Page(); capture = diag.Capture(diag.ArtifactWriter(tmp_path)); capture.setup(page)
    capture.sink(sample()); capture.sink(sample()); page.context.browser.close(); capture.sink(sample("passed")); capture.close()
    assert capture.errors == []
    assert sum(x[0] == "Tracing.start" for x in page.session.calls) == 1
    assert sum(x[0] == "Tracing.end" for x in page.session.calls) == 1
    assert sum(x[0] == "Profiler.stop" for x in page.session.calls) == 1
    assert page.session.detaches == 1
    assert page.context.browser.closes == 1
    assert (tmp_path / "timeline.json").is_file()


def test_conflicting_checkpoint_is_not_silently_accepted(tmp_path):
    page = Page(); capture = diag.Capture(diag.ArtifactWriter(tmp_path)); capture.setup(page)
    capture.sink(sample()); changed = sample(); changed["tbt_ms"] = 1; capture.sink(changed); capture.close()
    assert "checkpoint_replay_conflict" in capture.errors


def test_trace_timeout_is_bounded_and_closes_browser(tmp_path):
    clock = Clock(); page = Page(Session(complete=False), clock)
    capture = diag.Capture(diag.ArtifactWriter(tmp_path), clock=clock); capture.setup(page); capture.sink(sample()); capture.close()
    assert "trace_stop_timeout" in capture.errors
    assert 10 <= clock.now < 10.1
    assert page.session.detaches == 1
    assert not page.context.browser.connected
    assert sum(x[0] == "Tracing.end" for x in page.session.calls) == 1


def test_async_completion_arrives_only_while_playwright_dispatcher_is_pumped(tmp_path):
    clock = Clock(); page = Page(Session(complete=False), clock)
    pump_calls = []
    def pump(ms):
        pump_calls.append(ms)
        clock.now += ms / 1000
        if clock.now >= 0.05:
            page.session.handler({"stream": "fixture"})
    page.wait_for_timeout = pump
    capture = diag.Capture(diag.ArtifactWriter(tmp_path), clock=clock)
    capture.setup(page); capture.sink(sample()); capture.close()
    assert pump_calls and capture.errors == []
    assert clock.now == 0.05 and page.session.detaches == 1
    assert (tmp_path / "timeline.json").read_text() == '{"traceEvents":[]}'


def test_stream_exception_still_closes_io_session_and_owned_browser(tmp_path):
    page = Page(); original = page.session.send
    def broken(name, params=None):
        if name == "IO.read": raise RuntimeError("synthetic IO interruption")
        return original(name, params)
    page.session.send = broken
    capture = diag.Capture(diag.ArtifactWriter(tmp_path))
    capture.setup(page); capture.sink(sample()); capture.close()
    assert capture.errors == ["capture_incomplete"]
    assert any(x[0] == "IO.close" for x in page.session.calls)
    assert page.session.detaches == 1 and page.context.browser.closes == 1


def test_failure_before_trace_read_closes_available_stream_during_cleanup(tmp_path):
    page = Page(); writer = diag.ArtifactWriter(tmp_path); original = writer.write_json
    def failed_cpu(name, value, **kwargs):
        if name == "cpu.json": raise OSError("synthetic disk failure")
        return original(name, value, **kwargs)
    writer.write_json = failed_cpu
    capture = diag.Capture(writer)
    capture.setup(page); capture.sink(sample()); capture.close()
    assert capture.errors == ["capture_incomplete"]
    names = [x[0] for x in page.session.calls]
    assert names.count("Tracing.end") == names.count("IO.close") == 1
    assert capture.stream_closed and page.session.detaches == 1


def test_oversized_trace_closes_stream_and_detaches(tmp_path):
    page = Page(Session(payload="x" * 10000)); capture = diag.Capture(diag.ArtifactWriter(tmp_path, limit=4096))
    capture.setup(page); capture.sink(sample()); capture.close()
    assert "page_artifact_capacity_exceeded" in capture.errors
    assert any(x[0] == "IO.close" for x in page.session.calls)
    assert page.session.detaches == 1
    assert capture.writer.used <= 4096


def test_partial_profiler_setup_still_stops_it(tmp_path):
    page = Page(Session(fail_start=True)); capture = diag.Capture(diag.ArtifactWriter(tmp_path))
    with pytest.raises(RuntimeError): capture.setup(page)
    capture.close()
    assert any(x[0] == "Profiler.stop" for x in page.session.calls)
    assert not page.context.browser.connected


def test_missing_required_invalidation_category_does_not_silently_claim_capture(tmp_path):
    page = Page(); original = page.session.send
    def unsupported(name, params=None):
        if name == "Tracing.getCategories": return {"categories": []}
        return original(name, params)
    page.session.send = unsupported
    capture = diag.Capture(diag.ArtifactWriter(tmp_path))
    with pytest.raises(diag.DiagnosticError, match="category_unavailable"):
        capture.setup(page)
    capture.close()
    assert not any(x[0] in {"Profiler.start", "Tracing.start"} for x in page.session.calls)
    assert page.session.detaches == 1 and page.context.browser.closes == 1


def fake_modules(pages):
    calls = []
    cases = {name: SimpleNamespace(path=diag.PAGE_PATHS[name], interaction_selector="original-selector-" + name,
        ready_selector="original-ready-" + name, interaction_mode="in_page") for name in diag.PAGES}
    validators = {name: object() for name in diag.PAGES}
    post = {name: object() for name in diag.PAGES}
    beta = SimpleNamespace(PAGES=cases, VIEWPORTS={"mobile": {"width": 390, "height": 844, "isMobile": True}},
        _analyze_fixture=lambda: ({"fixture": "unchanged"}, "original-sse"),
        _page_setup_factory=lambda name, case, origin, request, stream: (lambda *_args: {"fixture": name}),
        _page_validator=lambda name, case: validators[name], _post_interaction_validator=lambda name: post[name])

    def audit(runtime, base, path, viewport_name, viewport, selector, **kwargs):
        page = Page(); pages.append(page); name = next(k for k,v in cases.items() if v.path == path)
        calls.append((name, kwargs))
        assert viewport_name == "mobile" and viewport == beta.VIEWPORTS["mobile"]
        assert selector == cases[name].interaction_selector and kwargs["runs"] == 1
        assert kwargs["page_validator"] is validators[name] and kwargs["post_interaction_validator"] is post[name]
        assert kwargs["ready_selector"] == cases[name].ready_selector
        try:
            assert kwargs["page_setup"](page, "mobile", 0) == {"fixture": name}
            kwargs["run_evidence_sink"](sample()); kwargs["run_evidence_sink"](sample())
        finally: page.context.browser.close()
        kwargs["run_evidence_sink"](sample("passed"))
        return {"status": 200, "tbt_ms": 250}
    return beta, SimpleNamespace(audit_one=audit), calls


def test_exact_pair_original_parameters_no_regrade_and_no_retry(tmp_path):
    pages = []; beta, perf, calls = fake_modules(pages)
    grade = tmp_path / "grade.json"; grade.write_bytes(b'original-grade-result')
    def unchanged(): assert grade.read_bytes() == b'original-grade-result'
    results = diag.collect_pair(object(), beta, perf, "http://127.0.0.1:4173/", tmp_path,
        unchanged=unchanged, metrics=lambda: {"synthetic": True})
    assert [x[0] for x in calls] == ["analyze", "papers"]
    assert all(x["classification"] == "NOT_GATE" and x["status"] == "complete" for x in results)
    assert all(p.context.browser.closes == 1 for p in pages)
    with pytest.raises(FileExistsError):
        diag.collect_pair(object(), beta, perf, "http://127.0.0.1:4173/", tmp_path, metrics=lambda: {})
    assert len(calls) == 2


def test_exception_outside_auditor_finalizer_falls_back_to_owned_close(tmp_path):
    pages = []; beta, perf, _ = fake_modules(pages)
    def crash(runtime, base, path, vp, viewport, selector, **kwargs):
        page = Page(); pages.append(page); kwargs["page_setup"](page, vp, 0)
        raise RuntimeError("synthetic unexpected interruption")
    perf.audit_one = crash
    result = diag.collect_pair(object(), beta, perf, "http://127.0.0.1:4173/", tmp_path, metrics=lambda: {})
    assert all(x["status"] == "incomplete" for x in result)
    assert all(p.session.detaches == 1 and p.context.browser.closes == 1 for p in pages)


def test_cli_denial_never_calls_capture(monkeypatch, capsys):
    def denied(): raise diag.DiagnosticError("linux_only_no_local_capture_override")
    monkeypatch.setattr(diag, "require_linux", denied)
    monkeypatch.setattr(diag, "collect_pair", lambda *_a, **_k: pytest.fail("capture started"))
    assert diag.main(["--grade-artifact", "unused.json", "--grade-outcome", "failure", "--base", "http://127.0.0.1:4173/", "--out", "/unused"]) == 2
    assert json.loads(capsys.readouterr().out)["classification"] == "NOT_GATE"


def test_pins_cover_both_pages_shared_assets_fixture_and_original_audit():
    required = {"web/frontend/papers.html", "web/frontend/assets/js/papers.js",
        "web/frontend/assets/js/history-sidebar.js", "web/frontend/assets/js/site-chrome.js",
        "web/frontend/assets/js/i18n.js", "web/frontend/assets/js/utils.js",
        "web/backend/tests/deep_report_fixtures.py", *diag.GRADE_SOURCE_PATHS}
    assert required <= diag.SOURCE_PINS.keys()
    for relative, expected in diag.SOURCE_PINS.items():
        assert diag.digest((diag.ROOT / relative).read_bytes()) == expected


def test_service_must_serve_exact_static_files_without_network(tmp_path, monkeypatch):
    front = tmp_path / "web/frontend"; front.mkdir(parents=True)
    for name in diag.PAGES: (front / f"{name}.html").write_bytes(name.encode())
    pins = {f"web/frontend/{n}.html": diag.digest(n.encode()) for n in diag.PAGES}
    asset = front / "assets/js/shared.js"; asset.parent.mkdir(parents=True); asset.write_bytes(b"shared asset")
    pins["web/frontend/assets/js/shared.js"] = diag.digest(asset.read_bytes())
    urls = []
    class Response:
        status = 200
        def __init__(self, data): self.data = data
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def read(self, _limit): return self.data
    def opened(url, timeout):
        urls.append(url)
        assert timeout == 5
        relative = diag.urlsplit(url).path.lstrip("/")
        return Response((front / relative).read_bytes())
    monkeypatch.setattr(diag, "build_opener", lambda *_args: SimpleNamespace(open=opened))
    diag.verify_service("http://127.0.0.1:4173/", tmp_path, pins=pins)
    assert len(urls) == 3 and urls[-1].endswith("assets/js/shared.js")
    monkeypatch.setattr(diag, "build_opener", lambda *_args: SimpleNamespace(open=lambda *_a, **_k: Response(b"wrong source")))
    with pytest.raises(diag.DiagnosticError, match="not_ready"):
        diag.verify_service("http://127.0.0.1:4173/", tmp_path, pins=pins)


def controller_fixture(tmp_path, monkeypatch, grade_status):
    root = tmp_path / "source"; (root / "scripts").mkdir(parents=True)
    (root / "input.txt").write_bytes(b"approved")
    grade_path = tmp_path / "grade.json"; grade_path.write_text(json.dumps(grade_value(grade_status)))
    env, event = event_identity(); event_path = tmp_path / "event.json"; event_path.write_text(json.dumps(event))
    for k,v in env.items(): monkeypatch.setenv(k,v)
    monkeypatch.setenv("GITHUB_EVENT_PATH",str(event_path))
    monkeypatch.setattr(diag,"ROOT",root)
    monkeypatch.setattr(diag,"require_linux",lambda: None)
    monkeypatch.setattr(diag,"verify_binding",lambda *_args: {"input.txt":diag.digest(b"approved")})
    monkeypatch.setattr(diag,"verify_dependencies",lambda: {"python":"3.11.15","playwright":"1.59.0","pydantic":"2.7.4"})
    monkeypatch.setattr(diag,"verify_service",lambda *_args: None)
    monkeypatch.setattr(diag,"runner_snapshot",lambda: {})
    pages=[]; beta,perf,calls=fake_modules(pages)
    beta.__name__="scripts.beta_perf_audit"; beta.__file__=str(root/"scripts/beta_perf_audit.py")
    perf.__name__="scripts.perf_audit"; perf.__file__=str(root/"scripts/perf_audit.py")
    original_import=diag.importlib.import_module
    def imported(name,*args,**kwargs):
        if name==beta.__name__:return beta
        if name==perf.__name__:return perf
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(diag.importlib,"import_module",imported)
    binary=tmp_path/"synthetic-browser-file";binary.write_bytes(b"not executable and never launched")
    binary.chmod(0o700)
    manager=SimpleNamespace(enters=0,exits=0)
    class Manager:
        def __enter__(self):
            manager.enters+=1
            return SimpleNamespace(chromium=SimpleNamespace(executable_path=str(binary)))
        def __exit__(self,*_args):manager.exits+=1
    pkg=ModuleType("playwright");pkg.__path__=[]
    api=ModuleType("playwright.sync_api");api.sync_playwright=Manager
    monkeypatch.setitem(sys.modules,"playwright",pkg)
    monkeypatch.setitem(sys.modules,"playwright.sync_api",api)
    args=SimpleNamespace(grade_artifact=str(grade_path),grade_outcome="success" if grade_status=="passed" else "failure",base="http://127.0.0.1:4173/",out=str(tmp_path/"outputs"))
    return args,grade_path,manager,pages,calls


@pytest.mark.parametrize("status",["passed","failed"])
def test_controller_collects_both_once_after_either_grade_without_editing_it(tmp_path,monkeypatch,status):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,status)
    original=path.read_bytes()
    result=diag.run(args)
    assert result["classification"]=="NOT_GATE" and result["status"]=="complete"
    assert result["original_grade_status"]==status and path.read_bytes()==original
    assert [x[0] for x in calls]==["analyze","papers"]
    assert manager.enters==manager.exits==1
    assert all(p.context.browser.closes==1 for p in pages)
    with pytest.raises(FileExistsError):diag.run(args)
    assert len(calls)==2 and manager.enters==1


def test_service_failure_is_before_manager_or_started_markers(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    def missing(*_args):raise diag.DiagnosticError("static_service_not_ready")
    monkeypatch.setattr(diag,"verify_service",missing)
    with pytest.raises(diag.DiagnosticError,match="not_ready"):diag.run(args)
    assert manager.enters==0 and pages==[] and calls==[]
    assert not Path(args.out).exists()


def test_original_grade_changed_by_other_writer_is_not_restored_or_regraded(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    def external_change(*_args,**_kwargs):
        path.write_bytes(b"concurrent external write")
        return []
    monkeypatch.setattr(diag,"collect_pair",external_change)
    result=diag.run(args)
    assert result["status"]=="incomplete" and result["classification"]=="NOT_GATE"
    assert path.read_bytes()==b"concurrent external write"
    assert manager.enters==manager.exits==1


def test_original_step_outcome_must_match_without_conditioning_on_red(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"passed")
    args.grade_outcome="failure"
    with pytest.raises(diag.DiagnosticError,match="grade_outcome"):
        diag.run(args)
    assert manager.enters==0 and pages==[] and calls==[]


def test_unrelated_environment_and_event_body_never_enter_artifacts(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    canary="DO_NOT_CAPTURE_ACCOUNT_SECRET"
    monkeypatch.setenv("OPENROUTER_API_KEY",canary)
    event_path=Path(os.environ["GITHUB_EVENT_PATH"])
    event=json.loads(event_path.read_text());event["pull_request"]["body"]=canary
    event_path.write_text(json.dumps(event))
    result=diag.run(args)
    assert result["status"]=="complete"
    for p in Path(args.out).rglob("*.json"):
        assert canary not in p.read_text()


def test_interruption_closes_owned_resources_and_does_not_try_second_page(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    original_import=diag.importlib.import_module
    perf=original_import("scripts.perf_audit")
    def interrupted(runtime,base,path,vp,viewport,selector,**kwargs):
        page=Page();pages.append(page);kwargs["page_setup"](page,vp,0)
        raise KeyboardInterrupt()
    perf.audit_one=interrupted
    result=diag.run(args)
    assert result["status"]=="incomplete" and result["reason"]=="diagnostic_interrupted_no_retry"
    assert result["started_pages"]==["analyze"]
    assert manager.enters==manager.exits==1 and len(pages)==1
    assert pages[0].session.detaches==1 and pages[0].context.browser.closes==1


def test_source_rejection_before_any_manager_or_markers(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    def mismatch(*_args):raise diag.DiagnosticError("source_digest_mismatch")
    monkeypatch.setattr(diag,"verify_binding",mismatch)
    with pytest.raises(diag.DiagnosticError,match="source_digest"):
        diag.run(args)
    assert manager.enters==0 and pages==[] and not Path(args.out).exists()


def test_wrong_dependency_prevents_start(monkeypatch):
    monkeypatch.setattr(diag.sys,"version_info",(3,11,0))
    monkeypatch.setattr(diag.importlib.metadata,"version",lambda _p:"wrong-version")
    with pytest.raises(diag.DiagnosticError,match="dependencies"):
        diag.verify_dependencies()


def test_original_audit_not_run_is_incomplete_without_browser(tmp_path,monkeypatch):
    args,path,manager,pages,calls=controller_fixture(tmp_path,monkeypatch,"failed")
    args.grade_outcome="skipped"
    with pytest.raises(diag.DiagnosticError,match="not_finished"):
        diag.run(args)
    assert manager.enters==0 and pages==[] and not Path(args.out).exists()


@pytest.mark.parametrize("data",[b'{"x":1,"x":2}',b'{"x":NaN}'])
def test_json_does_not_hide_duplicates_or_nonfinite_values(data):
    with pytest.raises(diag.DiagnosticError):diag.decode_json(data)
