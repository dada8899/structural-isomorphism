import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import playwright.sync_api as playwright_sync

from scripts.beta_perf_audit import (
    AuditFailure,
    EVIDENCE_SOURCES,
    PAGES,
    VIEWPORTS,
    _analyze_fixture,
    _budget_failures,
    _checkpoint_run_evidence,
    _source_snapshot,
    _validate_audit_result,
    _validate_local_base,
    _write_report,
    _page_validator,
    _destination_validator,
    _post_interaction_validator,
    run,
)
from scripts.perf_audit import (
    ARM_TRUSTED_INTERACTION_SCRIPT,
    FLUSH_EVENT_TIMING_SCRIPT,
    READ_TRUSTED_INTERACTION_SCRIPT,
    RunFinalizationError,
    audit_one,
)


ROOT = Path(__file__).resolve().parents[1]


def test_local_base_is_fail_closed() -> None:
    assert _validate_local_base("http://127.0.0.1:4173") == "http://127.0.0.1:4173/"
    for value in (
        "https://127.0.0.1:4173",
        "http://example.com",
        "http://user:pass@localhost:4173",
    ):
        with pytest.raises(AuditFailure):
            _validate_local_base(value)


class _EntryElement:
    def __init__(self, *, count=1, visible=True, enabled=True, href=None):
        self.size=count;self.visible=visible;self.enabled=enabled;self.href=href
    def count(self):return self.size
    def is_visible(self):return self.visible
    def is_enabled(self):return self.enabled
    def is_disabled(self):return not self.enabled
    def get_attribute(self,key):return self.href if key=='href' else None
    def wait_for(self,**_kwargs):
        if not self.size or not self.visible:raise TimeoutError('destination DOM missing')


class _EntryDOM:
    url='http://127.0.0.1:4173/research'
    def __init__(self):
        self.elements={
            '#start-research':_EntryElement(href='/research'),
            '#analytics-consent':_EntryElement(count=0,visible=False),
            '#legacy-ask-entry':_EntryElement(visible=False),
            '#ask-input':_EntryElement(enabled=False),
            '.ask-chip':_EntryElement(count=4,visible=False,enabled=False),
            '#access a':_EntryElement(href='/auth/login?next=%2Fresearch'),
            '#problem-form':_EntryElement(visible=False),
        }
    def locator(self,selector):return self.elements.get(selector,_EntryElement(count=0,visible=False))
    def evaluate(self,_script):return {'viewport':390,'scroll':390}


def _entry_state():
    return {'invalid_api':[],'unknown_requests':[],'page_errors':[],'bad_static_responses':[],
            'api_counts':{('GET','/api/auth/me'):2},'home_origin':('http','127.0.0.1',4173),
            'home_navigation_count':1,'home_destination_validated':False}


@pytest.mark.parametrize('failure',['missing_entry','hidden_entry','disabled_entry','wrong_href','legacy_visible','old_input_enabled'])
def test_retired_chips_cannot_satisfy_current_home_readiness(failure):
    page=_EntryDOM()
    if failure=='missing_entry':page.elements['#start-research'].size=0
    elif failure=='hidden_entry':page.elements['#start-research'].visible=False
    elif failure=='disabled_entry':page.elements['#start-research'].enabled=False
    elif failure=='wrong_href':page.elements['#start-research'].href='/analyze'
    elif failure=='legacy_visible':page.elements['#legacy-ask-entry'].visible=True
    else:page.elements['#ask-input'].enabled=True
    with pytest.raises(AuditFailure):_page_validator('home',PAGES['home'])(page,_entry_state())


@pytest.mark.parametrize('failure',['wrong_target','query','fragment','foreign','empty_dom','hidden_dom','wrong_login_next','form_visible','missing_navigation','missing_auth','private_read'])
def test_research_destination_rejects_unproven_or_wrong_states(failure):
    popup=_EntryDOM();state=_entry_state()
    if failure=='wrong_target':popup.url='http://127.0.0.1:4173/not-research'
    elif failure=='query':popup.url+='?q=private'
    elif failure=='fragment':popup.url+='#private'
    elif failure=='foreign':popup.url='https://example.invalid/research'
    elif failure=='empty_dom':popup.elements={}
    elif failure=='hidden_dom':popup.elements['#access a'].visible=False
    elif failure=='wrong_login_next':popup.elements['#access a'].href='/auth/login?next=%2Freports'
    elif failure=='form_visible':popup.elements['#problem-form'].visible=True
    elif failure=='missing_navigation':state['home_navigation_count']=0
    elif failure=='missing_auth':state['api_counts']={('GET','/api/auth/me'):1}
    else:state['api_counts'][('GET','/api/research')]=1
    with pytest.raises((AuditFailure,TimeoutError)):_destination_validator('home')(popup,state,{})
    assert not state['home_destination_validated']


def test_current_home_and_destination_have_explicit_separate_proofs():
    assert PAGES['home'].ready_selector==PAGES['home'].interaction_selector=='#start-research'
    assert PAGES['home'].interaction_mode=='new_tab'
    page=_EntryDOM();state=_entry_state();details={'mode':'new_tab','popup_created':True,'destination_url':page.url}
    _page_validator('home',PAGES['home'])(page,state)
    with pytest.raises(AuditFailure):_post_interaction_validator('home')(page,state,details)
    _destination_validator('home')(page,state,details)
    _post_interaction_validator('home')(page,state,details)
    assert details['destination_state']=='research_sign_in_required'
    assert all(_destination_validator(name) is None for name in PAGES if name!='home')


def test_home_never_ignores_a_failed_destination_response():
    state=_entry_state();state['bad_static_responses']=['404 /research']
    with pytest.raises(AuditFailure,match='bad_static_responses'):
        _page_validator('home',PAGES['home'])(_EntryDOM(),state)


def test_home_destination_fixture_serves_actual_checkout_document_and_closed_auth():
    from types import SimpleNamespace
    from scripts.beta_perf_audit import _page_setup_factory
    class Context:
        def on(self,*_args):pass
        def route(self,pattern,handler):self.handler=handler
    class Page:
        context=Context()
        def on(self,*_args):pass
    page=Page();state=_page_setup_factory('home',PAGES['home'],('http','127.0.0.1',4173),{},'')(page,'desktop',1)
    class Route:
        def __init__(self,url):self.request=SimpleNamespace(url=url,method='GET');self.reply=None;self.aborted=False
        def fulfill(self,**kwargs):self.reply=kwargs
        def abort(self):self.aborted=True
    document=Route('http://127.0.0.1:4173/research');page.context.handler(document)
    assert document.reply['status']==200
    assert document.reply['body']==(ROOT/'web/frontend/research.html').read_text()
    auth=Route('http://127.0.0.1:4173/api/auth/me');page.context.handler(auth)
    assert auth.reply['status']==401 and json.loads(auth.reply['body'])=={'ok':False,'error':'no session'}
    foreign=Route('https://example.invalid/research');page.context.handler(foreign)
    assert foreign.aborted and state['unknown_requests']


def _valid_sample() -> dict:
    return {
        "audit_status": "passed",
        "primary_audit_status": "passed",
        "stage": "complete",
        "cleanup_status": "passed",
        "cleanup_attempted": True,
        "evidence_revision": 2,
        "status": 200,
        "lcp_ms": 100.0,
        "cls": 0.01,
        "fcp_ms": 50.0,
        "tbt_ms": 10.0,
        "inp_proxy_ms": 16.0,
        "long_task_total_ms": 0.0,
        "dom_loaded_ms": 40.0,
        "load_event_ms": 45.0,
        "interaction_event_count": 1,
        "event_timing_flushed_count": 0,
        "loaf_flushed_count": 0,
        "observer_animation_frame_flush_count": 2,
        "trusted_interaction_count": 1,
        "trusted_interaction_window_verified": True,
        "trusted_pointer_sequence_verified": True,
        "event_timing_supported": True,
        "event_timing_threshold_ms": 16,
        "event_timing_calibration": "chromium_147_threshold_16",
        "inp_observation_mode": "event_timing_observed",
        "transfer_kb": {
            "js_kb": 10.0,
            "css_kb": 2.0,
            "img_kb": 1.0,
            "other_kb": 3.0,
            "total_kb": 16.0,
        },
    }


def test_authoritative_result_requires_three_finite_trusted_runs() -> None:
    sample = _valid_sample()
    result = {**sample, "runs": 3, "raw_runs": [dict(sample) for _ in range(3)]}
    _validate_audit_result(result, 3)
    for mutation in (
        lambda value: value.update({"lcp_ms": float("nan")}),
        lambda value: value.update({"inp_proxy_ms": float("inf")}),
        lambda value: value.update({"interaction_event_count": 0}),
        lambda value: value["transfer_kb"].update({"js_kb": float("nan")}),
    ):
        broken = {
            **result,
            "raw_runs": [
                {**row, "transfer_kb": dict(row["transfer_kb"])}
                for row in result["raw_runs"]
            ],
        }
        mutation(broken["raw_runs"][1])
        with pytest.raises(AuditFailure):
            _validate_audit_result(broken, 3)
    with pytest.raises(AuditFailure):
        _validate_audit_result({**result, "raw_runs": result["raw_runs"][:2]}, 3)
    for key, bad_value in (
        ("audit_status", "failed"),
        ("primary_audit_status", "failed"),
        ("cleanup_status", "pending"),
        ("cleanup_attempted", False),
        ("evidence_revision", 1),
    ):
        forged = {**result, "raw_runs": [dict(row) for row in result["raw_runs"]]}
        forged["raw_runs"][1][key] = bad_value
        with pytest.raises(AuditFailure, match="incomplete"):
            _validate_audit_result(forged, 3)
    fallback = {
        **sample,
        "interaction_event_count": 0,
        "inp_proxy_ms": 16.0,
        "inp_observation_mode": "trusted_click_threshold_bound",
    }
    _validate_audit_result({
        **fallback, "runs": 3, "raw_runs": [dict(fallback) for _ in range(3)],
    }, 3)
    mixed_rows = [dict(sample), dict(fallback), dict(sample)]
    _validate_audit_result({
        **sample,
        "runs": 3,
        "raw_runs": mixed_rows,
        "inp_observation_mode": "mixed_trusted_modes",
        "interaction_event_count": 0,
    }, 3)
    for key, bad_value in (
        ("trusted_interaction_count", 0),
        ("trusted_interaction_window_verified", False),
        ("trusted_pointer_sequence_verified", False),
        ("event_timing_supported", False),
        ("event_timing_threshold_ms", 8),
        ("event_timing_calibration", "unknown_event_timing_calibration"),
        ("observer_animation_frame_flush_count", 1),
        ("inp_observation_mode", "unknown_inp_mode"),
    ):
        invalid = {**result, "raw_runs": [dict(row) for row in result["raw_runs"]]}
        invalid["raw_runs"][0][key] = bad_value
        with pytest.raises(AuditFailure, match="trusted successful interaction"):
            _validate_audit_result(invalid, 3)
    for key, forged_value in (
        ("inp_observation_mode", "mixed_trusted_modes"),
        ("trusted_interaction_count", 2),
        ("interaction_event_count", 0),
        ("event_timing_flushed_count", 1),
        ("loaf_flushed_count", 1),
    ):
        forged_aggregate = {**result, key: forged_value}
        with pytest.raises(AuditFailure, match="aggregate trusted interaction"):
            _validate_audit_result(forged_aggregate, 3)


def test_budget_is_viewport_specific_and_strict() -> None:
    thresholds = {
        "lcp_mobile_ms": 2600,
        "lcp_desktop_ms": 2000,
        "cls": 0.1,
        "tbt_ms": 200,
        "inp_proxy_ms": 2200,
    }
    good = {
        "lcp_ms": 1900.0,
        "cls": 0.05,
        "tbt_ms": 100.0,
        "inp_proxy_ms": 100.0,
    }
    assert _budget_failures("home", "desktop", good, thresholds) == []
    bad = {
        "lcp_ms": 2700.0,
        "cls": 0.11,
        "tbt_ms": 201.0,
        "inp_proxy_ms": 2201.0,
    }
    assert len(_budget_failures("home", "mobile", bad, thresholds)) == 4
    with pytest.raises(AuditFailure):
        _budget_failures("home", "desktop", good, {**thresholds, "cls": 0})
    with pytest.raises(AuditFailure):
        _budget_failures(
            "home", "desktop", good, {**thresholds, "tbt_ms": float("nan")}
        )
    with pytest.raises(AuditFailure):
        _budget_failures(
            "home", "desktop", {**good, "cls": float("nan")}, thresholds
        )


def test_analyze_fixture_is_backend_validated_and_complete() -> None:
    request, stream = _analyze_fixture()
    assert request == {
        "b_id": "target-two",
        "a_id": "source-one",
        "lang": "zh",
        "persist": 0,
    }
    assert stream.count("event: section\n") == 9
    assert stream.count("event: report_validated\n") == 1
    assert stream.count("event: done\n") == 1


def test_early_failure_still_writes_machine_readable_evidence(tmp_path: Path) -> None:
    out = tmp_path / "failure.json"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/beta_perf_audit.py",
            "--runs",
            "2",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "error"
    assert payload["failures"]


def test_checkpoint_replace_is_atomic_and_failure_preserves_old_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "checkpoint.json"
    old = {"status": "running", "completed_runs": 1}
    out.write_text(json.dumps(old), encoding="utf-8")
    replacement = {"status": "running", "completed_runs": 2}
    real_replace = os.replace
    inspected = []

    def inspect_then_replace(source, destination):
        assert json.loads(Path(source).read_text(encoding="utf-8")) == replacement
        assert json.loads(Path(destination).read_text(encoding="utf-8")) == old
        inspected.append(True)
        real_replace(source, destination)

    monkeypatch.setattr("scripts.beta_perf_audit.os.replace", inspect_then_replace)
    _write_report(out, replacement)
    assert inspected
    assert json.loads(out.read_text(encoding="utf-8")) == replacement

    def reject_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("scripts.beta_perf_audit.os.replace", reject_replace)
    with pytest.raises(OSError, match="replace failure"):
        _write_report(out, {"status": "failed", "completed_runs": 3})
    assert json.loads(out.read_text(encoding="utf-8")) == replacement
    assert list(tmp_path.glob(".checkpoint.json.*.tmp")) == []


def test_authoritative_run_failure_emits_structured_safe_evidence() -> None:
    class Page:
        def add_init_script(self, _script):
            return None

    class Context:
        def new_page(self):
            return Page()

    class Browser:
        version = "147.0.7727.15"

        def new_context(self, **_kwargs):
            return Context()

        def close(self):
            return None

    class Chromium:
        def launch(self, **_kwargs):
            return Browser()

    class Runtime:
        chromium = Chromium()

    captured = []

    def fail_setup(*_args):
        raise RuntimeError("PRIVATE-QUESTION-MUST-NOT-PERSIST")

    result = audit_one(
        Runtime(), "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        runs=1, page_setup=fail_setup, run_evidence_sink=captured.append,
    )
    assert result["error"] == "1 of 1 runs failed"
    assert [sample["evidence_revision"] for sample in captured] == [1, 2]
    assert result["raw_runs"] == [captured[-1]]
    assert captured[-1]["run_index"] == 1
    assert captured[-1]["stage"] == "page_setup"
    assert captured[-1]["cleanup_status"] == "passed"
    assert captured[-1]["error_detail"] == {
        "code": "page_setup_failed", "type": "RuntimeError",
    }
    assert "elapsed" in captured[-1]["timings_ms"]
    assert "PRIVATE-QUESTION" not in json.dumps(result)


class _AuditLocator:
    def __init__(self, page: "_AuditPage"):
        self.page = page
        self.fail_stage = page.fail_stage

    @property
    def first(self):
        return self

    def wait_for(self, **_kwargs):
        return None

    def evaluate(self, script: str):
        self.page.locator_evaluate_scripts.append(script)
        if script == READ_TRUSTED_INTERACTION_SCRIPT:
            raise AssertionError("trusted handshake must be read from the page")
        if self.page.interaction_element_detached:
            raise RuntimeError("interaction element is no longer attached")
        if "tagName" in script:
            return "BUTTON"
        if script == ARM_TRUSTED_INTERACTION_SCRIPT:
            return {"armed": True}
        return None

    def click(self, **_kwargs):
        if self.fail_stage == "interaction":
            raise RuntimeError("PRIVATE-CLICK-MUST-NOT-PERSIST")
        if self.fail_stage == "detached_after_click":
            self.page.interaction_element_detached = True


class _AuditPage:
    def __init__(self, fail_stage: str | None):
        self.fail_stage = fail_stage
        self._clock = iter((1000.0, 1100.0, 6000.0))
        self.interaction_element_detached = False
        self.locator_evaluate_scripts: list[str] = []

    def add_init_script(self, _script):
        return None

    def goto(self, *_args, **_kwargs):
        if self.fail_stage == "navigation":
            raise RuntimeError("PRIVATE-NAV-MUST-NOT-PERSIST")
        return type("Response", (), {"status": 200})()

    def wait_for_load_state(self, *_args, **_kwargs):
        return None

    def wait_for_timeout(self, _duration):
        return None

    def locator(self, _selector):
        return _AuditLocator(self)

    def evaluate(self, script: str):
        if script == "performance.now()":
            return next(self._clock)
        if script == READ_TRUSTED_INTERACTION_SCRIPT:
            if self.fail_stage == "multiple_clicks":
                return {
                    "count": 2,
                    "pointerDownTimestamp": 1020.0,
                    "pointerUpTimestamp": 1040.0,
                    "timestamp": 1050.0,
                    "armed": False,
                }
            if self.fail_stage == "timestamp_outside_window":
                return {
                    "count": 1,
                    "pointerDownTimestamp": 1200.0,
                    "pointerUpTimestamp": 1220.0,
                    "timestamp": 1240.0,
                    "armed": False,
                }
            return {
                "count": 1,
                "pointerDownTimestamp": 1020.0,
                "pointerUpTimestamp": 1040.0,
                "timestamp": 1050.0,
                "armed": False,
            }
        if script == FLUSH_EVENT_TIMING_SCRIPT:
            return {
                "eventTimingSupported": self.fail_stage != "event_unsupported",
                "eventTimingThresholdMs": 16,
                "trustedInteractionCount": 1,
                "flushedEventCount": 0,
                "flushedLoafCount": 0,
                "animationFrameFlushCount": 2,
                "chromiumMajor": (
                    146 if self.fail_stage == "ua_mismatch" else 147
                ),
            }
        if "getEntriesByType('paint')" in script:
            return 100.0
        if "JSON.parse(JSON.stringify(window.__perf))" in script:
            if self.fail_stage == "metric":
                raise RuntimeError("PRIVATE-METRIC-MUST-NOT-PERSIST")
            return {
                "lcp": 120.0,
                "lcpElement": "MAIN",
                "lcpElementText": "PRIVATE-PAGE-CONTENT",
                "cls": 0.0,
                "longTasks": [],
                "loaf": [],
                "events": (
                    [] if self.fail_stage == "fast_event"
                    else [{
                        "name": "click",
                        "startTime": 1050.0,
                        "duration": 800.0 if self.fail_stage == "id0_long" else 16.0,
                        "interactionId": 0 if self.fail_stage == "id0_long" else 1,
                    }]
                ),
            }
        if "getEntriesByType('resource')" in script:
            return []
        if "getEntriesByType('navigation')" in script:
            return {
                "domContentLoadedEventEnd": 40.0,
                "loadEventEnd": 45.0,
                "responseEnd": 30.0,
                "transferSize": 0,
            }
        return None


class _AuditContext:
    def __init__(self, page: _AuditPage):
        self.page = page

    def new_page(self):
        return self.page


class _AuditBrowser:
    def __init__(
        self, page: _AuditPage, close_error: BaseException | None = None,
        before_close=None, fail_context: bool = False,
        browser_version: str = "147.0.7727.15",
    ):
        self.page = page
        self.close_error = close_error
        self.before_close = before_close
        self.fail_context = fail_context
        self.version = browser_version
        self.close_calls = 0

    def new_context(self, **_kwargs):
        if self.fail_context:
            raise RuntimeError("PRIVATE-CONTEXT-MUST-NOT-PERSIST")
        return _AuditContext(self.page)

    def close(self):
        self.close_calls += 1
        if self.before_close is not None:
            self.before_close()
        if self.close_error is not None:
            raise self.close_error


class _AuditRuntime:
    def __init__(self, browser: _AuditBrowser):
        self.chromium = type(
            "Chromium", (), {"launch": lambda _self, **_kwargs: browser}
        )()


@pytest.mark.parametrize(
    ("fail_stage", "expected_stage", "expected_code"),
    (
        ("page_setup", "page_setup", "page_setup_failed"),
        ("navigation", "navigation", "navigation_failed"),
        ("validator", "pre_measure_validation", "page_validation_failed"),
        ("interaction", "interaction", "interaction_failed"),
        ("metric", "metric_collection", "metric_collection_failed"),
        (None, "complete", None),
    ),
)
def test_cleanup_failure_replay_upsert_preserves_each_primary_outcome(
    fail_stage: str | None, expected_stage: str, expected_code: str | None,
) -> None:
    updates = []
    durable = {}

    def sink(sample):
        updates.append(sample)
        durable[sample["run_index"]] = sample

    def before_close():
        assert durable[1]["cleanup_status"] == "pending"
        assert durable[1]["evidence_revision"] == 1

    page = _AuditPage(fail_stage)
    browser = _AuditBrowser(
        page, RuntimeError("PRIVATE-CLOSE-MUST-NOT-PERSIST"), before_close,
    )

    def page_setup(*_args):
        if fail_stage == "page_setup":
            raise RuntimeError("PRIVATE-SETUP-MUST-NOT-PERSIST")
        return {}

    def validator(*_args):
        if fail_stage == "validator":
            raise RuntimeError("PRIVATE-VALIDATOR-MUST-NOT-PERSIST")

    result = audit_one(
        _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        runs=1, page_setup=page_setup, page_validator=validator,
        run_evidence_sink=sink,
    )
    final = result["raw_runs"][0]
    assert len(result["raw_runs"]) == len(durable) == 1
    assert [row["evidence_revision"] for row in updates] == [1, 2]
    assert final == durable[1]
    assert final["audit_status"] == "failed"
    assert final["primary_audit_status"] == (
        "passed" if fail_stage is None else "failed"
    )
    assert final["stage"] == expected_stage
    assert final["cleanup_status"] == "failed"
    assert final["cleanup_error"] == {
        "code": "browser_close_failed", "type": "RuntimeError",
    }
    if expected_code is None:
        assert "error" not in final
    else:
        assert final["error"] == expected_code
        assert final["error_detail"]["code"] == expected_code
    assert browser.close_calls == 1
    assert "PRIVATE-" not in json.dumps(result)


def test_fast_trusted_click_without_event_entry_uses_threshold_bound() -> None:
    durable = {}
    result = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage("fast_event"))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
        run_evidence_sink=lambda sample: durable.update(
            {sample["run_index"]: sample}
        ),
    )
    assert "error" not in result
    final = durable[1]
    assert final["trusted_interaction_count"] == 1
    assert final["trusted_interaction_window_verified"] is True
    assert final["event_timing_supported"] is True
    assert final["interaction_event_count"] == 0
    assert final["inp_proxy_ms"] == 16.0
    assert final["inp_observation_mode"] == "trusted_click_threshold_bound"
    assert "timestamp" not in json.dumps(final).lower()


def test_trusted_handshake_survives_interaction_element_removal() -> None:
    page = _AuditPage("detached_after_click")
    durable = {}
    result = audit_one(
        _AuditRuntime(_AuditBrowser(page)),
        "http://127.0.0.1/", "search.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "#search-edit-btn",
        page_setup=lambda *_args: {},
        run_evidence_sink=lambda sample: durable.update(
            {sample["run_index"]: sample}
        ),
    )

    assert "error" not in result
    assert page.interaction_element_detached is True
    assert READ_TRUSTED_INTERACTION_SCRIPT not in page.locator_evaluate_scripts
    assert ARM_TRUSTED_INTERACTION_SCRIPT in page.locator_evaluate_scripts
    final = durable[1]
    assert final["trusted_interaction_count"] == 1
    assert final["trusted_interaction_window_verified"] is True
    assert final["trusted_pointer_sequence_verified"] is True


def test_long_zero_interaction_id_event_cannot_be_downgraded_to_threshold() -> None:
    durable = {}
    result = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage("id0_long"))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
        run_evidence_sink=lambda sample: durable.update(
            {sample["run_index"]: sample}
        ),
    )
    assert "error" not in result
    final = durable[1]
    assert final["interaction_event_count"] == 1
    assert final["inp_proxy_ms"] == 800.0
    assert final["inp_observation_mode"] == "event_timing_observed"


def test_unsupported_event_timing_api_fails_closed() -> None:
    result = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage("event_unsupported"))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
    )
    final = result["raw_runs"][0]
    assert final["stage"] == "event_timing"
    assert final["error"] == "event_timing_unsupported"
    assert final["audit_status"] == "failed"


@pytest.mark.parametrize("attack", ("multiple_clicks", "timestamp_outside_window"))
def test_trusted_click_handshake_rejects_count_and_window_attacks(
    attack: str,
) -> None:
    result = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage(attack))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
    )
    final = result["raw_runs"][0]
    assert final["stage"] == "interaction"
    assert final["error"] == "interaction_failed"


def test_ua_claim_cannot_bypass_python_runtime_calibration() -> None:
    wrong_browser = audit_one(
        _AuditRuntime(_AuditBrowser(
            _AuditPage(None), browser_version="146.0.0.0"
        )),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
    )
    assert wrong_browser["raw_runs"][0]["stage"] == "browser_setup"
    assert wrong_browser["raw_runs"][0]["error"] == (
        "event_timing_calibration_failed"
    )

    wrong_ua = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage("ua_mismatch"))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
    )
    assert wrong_ua["raw_runs"][0]["stage"] == "event_timing"
    assert wrong_ua["raw_runs"][0]["error"] == "event_timing_calibration_failed"


def test_unpinned_playwright_runtime_fails_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.perf_audit.importlib.metadata.version", lambda _name: "1.58.0"
    )
    result = audit_one(
        _AuditRuntime(_AuditBrowser(_AuditPage(None))),
        "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {},
    )
    assert result["raw_runs"][0]["stage"] == "browser_setup"
    assert result["raw_runs"][0]["error"] == "event_timing_calibration_failed"


def test_partial_browser_setup_is_checkpointed_before_failed_cleanup() -> None:
    durable = {}
    page = _AuditPage(None)

    def assert_pending():
        assert durable[1]["cleanup_status"] == "pending"

    browser = _AuditBrowser(
        page, RuntimeError("PRIVATE-CLOSE"), assert_pending, fail_context=True,
    )

    def sink(sample):
        durable[sample["run_index"]] = sample

    result = audit_one(
        _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        run_evidence_sink=sink,
    )
    final = result["raw_runs"][0]
    assert final["stage"] == "browser_setup"
    assert final["error"] == "browser_setup_failed"
    assert final["cleanup_status"] == "failed"
    assert browser.close_calls == 1


def test_publish_failure_attempts_cleanup_without_fabricating_final_evidence() -> None:
    page = _AuditPage("page_setup")
    browser = _AuditBrowser(page)

    def reject_publish(_sample):
        raise RuntimeError("PRIVATE-PUBLISH-MUST-NOT-PERSIST")

    with pytest.raises(RuntimeError, match="PUBLISH"):
        audit_one(
            _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html",
            "desktop", {"width": 1280, "height": 800, "isMobile": False},
            "button", page_setup=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("PRIVATE-PRIMARY")
            ), run_evidence_sink=reject_publish,
        )
    assert browser.close_calls == 1


def test_final_publish_failure_leaves_replayable_pending_checkpoint() -> None:
    durable = {}
    browser = _AuditBrowser(_AuditPage("page_setup"))

    def sink(sample):
        if sample["evidence_revision"] == 2:
            raise OSError("PRIVATE-FINAL-PUBLISH")
        durable[sample["run_index"]] = sample

    with pytest.raises(OSError, match="FINAL-PUBLISH"):
        audit_one(
            _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html",
            "desktop", {"width": 1280, "height": 800, "isMobile": False},
            "button", page_setup=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("PRIVATE-PRIMARY")
            ), run_evidence_sink=sink,
        )
    assert durable[1]["cleanup_status"] == "pending"
    assert durable[1]["evidence_revision"] == 1
    assert browser.close_calls == 1


def test_publish_and_cleanup_dual_failure_is_structured_and_raised() -> None:
    browser = _AuditBrowser(
        _AuditPage("page_setup"), RuntimeError("PRIVATE-CLOSE")
    )
    with pytest.raises(RunFinalizationError) as caught:
        audit_one(
            _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html",
            "desktop", {"width": 1280, "height": 800, "isMobile": False},
            "button", page_setup=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("PRIVATE-PRIMARY")
            ), run_evidence_sink=lambda _sample: (_ for _ in ()).throw(
                OSError("PRIVATE-PUBLISH")
            ),
        )
    assert caught.value.publish_error_type == "OSError"
    assert caught.value.cleanup_error_type == "RuntimeError"
    assert browser.close_calls == 1


def test_cleanup_cancellation_is_checkpointed_then_propagated() -> None:
    durable = {}
    browser = _AuditBrowser(_AuditPage("page_setup"), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        audit_one(
            _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html",
            "desktop", {"width": 1280, "height": 800, "isMobile": False},
            "button", page_setup=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("PRIVATE-PRIMARY")
            ), run_evidence_sink=lambda sample: durable.update(
                {sample["run_index"]: sample}
            ),
        )
    assert durable[1]["cleanup_status"] == "failed"
    assert durable[1]["evidence_revision"] == 2
    assert durable[1]["stage"] == "page_setup"


def test_checkpoint_sanitizer_uses_closed_diagnostic_vocabularies() -> None:
    secret = "TOKEN-super-secret-value"
    evidence = _checkpoint_run_evidence({
        "run_index": 1,
        "audit_status": secret,
        "primary_audit_status": secret,
        "stage": secret,
        "error": secret,
        "error_detail": {"code": secret, "type": secret},
        "cleanup_status": secret,
        "cleanup_error": {"code": secret, "type": secret},
        "inp_observation_mode": secret,
        "event_timing_threshold_ms": 8,
        "event_timing_supported": True,
        "event_timing_calibration": secret,
        "trusted_interaction_window_verified": True,
        "trusted_pointer_sequence_verified": True,
        "timings_ms": {secret: 1.0, "elapsed": 2.0},
        "request_summary": {
            "api_counts": [{
                "method": secret, "path": f"/api/auth/{secret}", "count": 1,
            }],
        },
    })
    serialized = json.dumps(evidence)
    assert secret not in serialized
    assert evidence["audit_status"] == "unknown_audit_status"
    assert evidence["primary_audit_status"] == "unknown_audit_status"
    assert evidence["stage"] == "unknown_stage"
    assert evidence["error"] == "unknown_run_error"
    assert evidence["error_detail"] == {
        "code": "unknown_run_error", "type": "unknown_error_type",
    }
    assert evidence["cleanup_status"] == "unknown_cleanup_status"
    assert evidence["cleanup_error"] == {
        "code": "unknown_cleanup_error", "type": "unknown_error_type",
    }
    assert evidence["inp_observation_mode"] == "unknown_inp_mode"
    assert evidence["event_timing_threshold_ms"] == 0
    assert evidence["event_timing_supported"] is True
    assert evidence["event_timing_calibration"] == (
        "unknown_event_timing_calibration"
    )
    assert evidence["trusted_interaction_window_verified"] is True
    assert evidence["trusted_pointer_sequence_verified"] is True
    assert evidence["timings_ms"] == {"elapsed": 2.0}
    assert evidence["request_summary"]["api_counts"] == [{
        "method": "UNKNOWN", "path": "/:unknown_api", "count": 1,
    }]


def test_authoritative_raw_evidence_closes_exception_and_request_labels() -> None:
    secret = "TOKEN_super_secret_value"
    secret_error = type(secret, (RuntimeError,), {})
    browser = _AuditBrowser(_AuditPage("validator"))
    result = audit_one(
        _AuditRuntime(browser), "http://127.0.0.1/", "analyze.html", "desktop",
        {"width": 1280, "height": 800, "isMobile": False}, "button",
        page_setup=lambda *_args: {
            "api_counts": {(secret, f"/api/auth/{secret}"): 1},
        },
        page_validator=lambda *_args: (_ for _ in ()).throw(secret_error()),
    )
    final = result["raw_runs"][0]
    assert secret not in json.dumps(result)
    assert final["error_detail"]["type"] == "unknown_error_type"
    assert final["request_summary"]["api_counts"] == [{
        "method": "UNKNOWN", "path": "/:unknown_api", "count": 1,
    }]


def test_run_checkpoint_precedes_later_exception_and_preserves_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "checkpoint.json"
    observed_before_raise = []

    class RuntimeManager:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    def audit_then_abort(*_args, **kwargs):
        kwargs["run_evidence_sink"]({
            "run_index": 1,
            "audit_status": "failed",
            "stage": "interaction",
            "error": "trusted_event_missing",
            "error_detail": {"code": "trusted_event_missing", "type": None},
            "timings_ms": {"browser_setup": 2.0, "elapsed": 9.0},
            "request_summary": {
                "api_counts": [{
                    "method": "POST", "path": "/api/analyze/stream", "count": 1,
                }],
                "invalid_api_count": 0,
                "unknown_request_count": 0,
                "page_error_count": 0,
                "bad_static_response_count": 0,
            },
            "lcp_element_text": "PRIVATE-QUESTION-MUST-NOT-PERSIST",
        })
        checkpoint = json.loads(out.read_text(encoding="utf-8"))
        run = checkpoint["pages"]["analyze"]["viewports"]["mobile"]["raw_runs"][0]
        observed_before_raise.append(run)
        assert run["stage"] == "interaction"
        assert "PRIVATE-QUESTION" not in out.read_text(encoding="utf-8")
        raise RuntimeError("PRIVATE-QUESTION-MUST-NOT-PERSIST")

    monkeypatch.setattr(
        "scripts.beta_perf_audit.PAGES", {"analyze": PAGES["analyze"]}
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit.VIEWPORTS", {"mobile": VIEWPORTS["mobile"]}
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit._analyze_fixture", lambda: ({}, "")
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit._load_authoritative_audit", lambda: audit_then_abort
    )
    monkeypatch.setattr(playwright_sync, "sync_playwright", RuntimeManager)

    report, failures = run(
        "http://127.0.0.1:4173", 3, ROOT / "perf-budget.json",
        evidence_path=out,
    )
    assert observed_before_raise
    assert failures
    durable = report["pages"]["analyze"]["viewports"]["mobile"]
    assert durable["raw_runs"][0]["stage"] == "interaction"
    assert durable["run_errors"][0]["error"] == "trusted_event_missing"
    assert durable["gate_error"]["code"] == "audit_execution_failed"
    assert "PRIVATE-QUESTION" not in out.read_text(encoding="utf-8")


def test_beta_checkpoint_upserts_pending_and_final_by_run_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "checkpoint.json"
    observed = []

    class RuntimeManager:
        def __enter__(self):
            return object()

        def __exit__(self, *_args):
            return False

    def audit_then_abort(*_args, **kwargs):
        base = {
            "run_index": 1,
            "audit_status": "passed",
            "primary_audit_status": "passed",
            "stage": "complete",
            "cleanup_attempted": True,
            "request_summary": {"api_counts": []},
        }
        kwargs["run_evidence_sink"]({
            **base, "cleanup_status": "pending", "evidence_revision": 1,
        })
        pending = json.loads(out.read_text(encoding="utf-8"))["pages"][
            "analyze"
        ]["viewports"]["mobile"]
        observed.append(pending)
        assert len(pending["raw_runs"]) == 1
        assert pending["completed_runs"] == 0
        assert pending["status"] == "incomplete"
        kwargs["run_evidence_sink"]({
            **base,
            "audit_status": "failed",
            "cleanup_status": "failed",
            "cleanup_error": {
                "code": "browser_close_failed", "type": "RuntimeError",
            },
            "evidence_revision": 2,
        })
        final = json.loads(out.read_text(encoding="utf-8"))["pages"][
            "analyze"
        ]["viewports"]["mobile"]
        observed.append(final)
        assert len(final["raw_runs"]) == 1
        assert final["completed_runs"] == 1
        assert final["successful_runs"] == 0
        assert final["status"] == "failed"
        assert len(final["run_errors"]) == 1
        raise RuntimeError("PRIVATE-AFTER-FINAL")

    monkeypatch.setattr(
        "scripts.beta_perf_audit.PAGES", {"analyze": PAGES["analyze"]}
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit.VIEWPORTS", {"mobile": VIEWPORTS["mobile"]}
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit._analyze_fixture", lambda: ({}, "")
    )
    monkeypatch.setattr(
        "scripts.beta_perf_audit._load_authoritative_audit", lambda: audit_then_abort
    )
    monkeypatch.setattr(playwright_sync, "sync_playwright", RuntimeManager)

    report, failures = run(
        "http://127.0.0.1:4173", 3, ROOT / "perf-budget.json",
        evidence_path=out,
    )
    assert len(observed) == 2
    assert failures
    durable = report["pages"]["analyze"]["viewports"]["mobile"]
    assert len(durable["raw_runs"]) == len(durable["run_errors"]) == 1
    assert durable["raw_runs"][0]["cleanup_status"] == "failed"
    assert durable["raw_runs"][0]["evidence_revision"] == 2
    assert "PRIVATE-" not in out.read_text(encoding="utf-8")


def test_release_gate_rejects_non_median_run_count_before_browser_start() -> None:
    with pytest.raises(AuditFailure, match="exactly three"):
        run("http://127.0.0.1:4173", 2, ROOT / "perf-budget.json")


def test_workflow_gates_all_primary_beta_surfaces_with_three_runs() -> None:
    assert set(PAGES) == {
        "home", "search", "analyze", "reports",
        "discoveries", "classes", "papers", "tools",
    }
    workflow = (ROOT / ".github/workflows/beta-perf.yml").read_text(encoding="utf-8")
    authoritative = (ROOT / "scripts/perf_audit.py").read_text(encoding="utf-8")
    beta = (ROOT / "scripts/beta_perf_audit.py").read_text(encoding="utf-8")
    assert "playwright==1.59.0" in workflow
    assert "pydantic==2.7.4" in workflow
    assert "PyYAML==6.0.3" in workflow
    assert "--runs 3" in workflow
    assert "--budget perf-budget.json" in workflow
    assert "if: always()" in workflow
    assert "/tmp/beta-perf-audit.json" in workflow
    assert "\n    paths:" not in workflow
    assert "pull_request:\n    branches: [main, integration/structure-rebuild-v1]" in workflow
    assert "push:\n    branches: [main, integration/structure-rebuild-v1, bootstrap/structure-ci-20261016]" in workflow
    assert "scripts/perf_audit.py" in EVIDENCE_SOURCES
    assert set(_source_snapshot()) == set(EVIDENCE_SOURCES)
    assert VIEWPORTS["mobile"]["isMobile"] is True
    assert PAGES["reports"].interaction_selector == "#myr-export"
    assert PAGES["tools"].interaction_mode == "new_tab"
    assert '"rate": 4' in authoritative
    assert "Network.emulateNetworkConditions" in authoritative
    assert "fcp_ms + 5000" in authoritative
    assert "interactionId" in authoritative and "long-animation-frame" in authoritative
    assert "post_measure_validation_failed" in authoritative
    assert "post_interaction_validator" in authoritative
    assert "audit_one(" in beta and "unknown API" in beta
    assert 'page.locator("#analytics-consent").count() != 0' in beta
    assert "research-library export action did not complete" in beta
    assert "tool-card navigation did not load its real target" in beta

    import yaml
    data = yaml.safe_load(workflow)
    job = data["jobs"]["beta-perf-audit"]
    gate = next(step for step in job["steps"] if step.get("id") == "beta_perf_gate")
    assert "if" not in gate and "continue-on-error" not in gate
    assert gate["run"] == (
        "python scripts/beta_perf_audit.py --base http://127.0.0.1:4173 "
        "--runs 3 --budget perf-budget.json --out /tmp/beta-perf-audit.json"
    )


class _NavigationPopup(_EntryDOM):
    def __init__(self, fail=False):super().__init__();self.closed=False;self.fail=fail
    def wait_for_load_state(self,*_args,**_kwargs):
        if self.fail:raise RuntimeError('navigation failed')
    def evaluate(self,_script):raise AssertionError('destination metrics must never be collected as home')
    def close(self):self.closed=True


class _NavigationLocator(_AuditLocator):
    def evaluate(self,script):
        if 'tagName' in script:return 'A'
        return super().evaluate(script)


class _NavigationPage(_AuditPage):
    def locator(self,_selector):return _NavigationLocator(self)


class _NavigationContext(_AuditContext):
    def __init__(self,page,popup):super().__init__(page);self.popup=popup
    def expect_page(self,**_kwargs):
        popup=self.popup
        class Expected:
            value=popup
            def __enter__(self):return self
            def __exit__(self,*_args):return False
        return Expected()


class _NavigationBrowser(_AuditBrowser):
    def __init__(self,page,popup):super().__init__(page);self.popup=popup
    def new_context(self,**_kwargs):return _NavigationContext(self.page,self.popup)


@pytest.mark.parametrize('failure',[None,'navigation','empty_dom','missing_callback'])
def test_destination_validation_precedes_close_and_retains_origin_metrics(failure):
    popup=_NavigationPopup(failure=='navigation')
    if failure=='empty_dom':popup.elements={}
    page=_NavigationPage(None);browser=_NavigationBrowser(page,popup);state=_entry_state();calls=[];evidence=[]
    def destination(live,scope,details):
        assert live is popup and not live.closed
        calls.append('destination')
        _destination_validator('home')(live,scope,details)
    result=audit_one(_AuditRuntime(browser),'http://127.0.0.1:4173/','index.html','desktop',
        {'width':1280,'height':800,'isMobile':False},'#start-research',
        page_setup=lambda *_args:state,interaction_mode='new_tab',
        destination_validator=None if failure=='missing_callback' else destination,
        post_interaction_validator=_post_interaction_validator('home'),run_evidence_sink=evidence.append)
    assert popup.closed and browser.close_calls==1
    sample=evidence[-1]
    if failure is None:
        assert calls==['destination'] and sample['audit_status']=='passed'
        assert sample['lcp_ms']==120 and sample['fcp_ms']==100
        assert sample['interaction_details']['destination_state']=='research_sign_in_required'
    elif failure=='missing_callback':
        assert calls==[] and sample['stage']=='interaction_validation'
        assert sample['error']=='interaction_validation_failed'
    else:
        assert sample['stage']=='interaction' and sample['error']=='interaction_failed'


def test_destination_callback_default_does_not_change_in_page_consumers():
    def forbidden(*_args):raise AssertionError('in-page consumer invoked destination validation')
    result=audit_one(_AuditRuntime(_AuditBrowser(_AuditPage(None))),
        'http://127.0.0.1/','analyze.html','desktop',
        {'width':1280,'height':800,'isMobile':False},'button',destination_validator=forbidden)
    assert 'error' not in result and result['status']==200
