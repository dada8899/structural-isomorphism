#!/usr/bin/env python3
"""One approved Linux diagnostic pair. Never grades or edits the perf gate."""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import signal
import stat
import subprocess
import sys
import time
from typing import Any
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "dada8899/structural-isomorphism"
PR_NUMBER = 253
MARKER_SUBJECT = "ci: capture structure-perf-linux-r2-20261016"
BASE_SHA = "847077a2706a748b37a21bfb1f613d8b86fa451a"
PAGES = ("analyze", "papers")
PAGE_PATHS = {"analyze": "analyze.html?id=target-two&a_id=source-one", "papers": "papers.html"}
MAX_PAGE_BYTES = 64 * 1024 * 1024
STOP_WAIT_SECONDS = 10
ENV_KEYS = (
    "GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH", "GITHUB_REPOSITORY", "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "RUNNER_OS", "RUNNER_ARCH",
)
GRADE_SOURCE_PATHS = (
    "web/frontend/analyze.html", "web/frontend/assets/js/analyze.js",
    "web/frontend/assets/css/analyze.css", "scripts/perf_audit.py",
    "scripts/beta_perf_audit.py", "perf-budget.json",
)
# SHA-256 of the approved 847 inputs; no diagnostic/workflow self-hash cycle.
SOURCE_PINS = {
    'perf-budget.json': 'fe2442643030ddf61fcda85053b4a3242abc68e88fc2f870e1e3874bfa319ad9',
    'scripts/beta_perf_audit.py': 'ad3f9e7f6b7151f55213254eba956dba9be1b27ba34168d3902339e35ff27402',
    'scripts/perf_audit.py': '5969635f8b8094f59b13ae9d15a89b6c376a82b304498ee5d1959aba58307d47',
    'structural_isomorphism/discovery_evidence.py': '6b2058340aa39fc24e3ed8d10b5cdb397da5278442e92ae3721d3cded60f4d82',
    'web/backend/requirements.txt': '9df6e33779d325a6e699d3af35684041dea3d2d256440a77cc643fcbc682af3f',
    'web/backend/services/candidate_origin.py': '68240508e51e8789bc0da0848f64ad00ff29f95aee7be152194c94630c4bfca6',
    'web/backend/services/deep_report.py': 'ce3ee02c3fdc9752d367857f4dec910f3cdaaff42904e16294b91841fb309da4',
    'web/backend/services/search_synthesis.py': 'f389b0a6cb3327734c376919d0acf5343fd9a805cd02e402e2adc9a7bcfaf99c',
    'web/backend/tests/deep_report_fixtures.py': 'a71cdc6db6e50e2fb93e33b840a3a3434bf6b1667c5edb2c07fd1c7785012626',
    'web/frontend/analyze.html': '3e903191903f48cf2ba360c871a06dec821e57e2f11d48ec3afe66da61ef36b1',
    'web/frontend/assets/css/analyze-actions.css': 'f93e7070f67146cc507291a3d7c160e2608e201cebc01a5011d5e4d9aa3c73e1',
    'web/frontend/assets/css/analyze.css': '86c7c9dbcd946ac6ae58dcedf8740bc430d7211f92c5df89809fb9dcf67bdf84',
    'web/frontend/assets/css/common.css': '8eae3e32b5a9cc8a5820d8aa98819b1bc2be5fb53a135ccaba53e4a9c38f682c',
    'web/frontend/assets/css/decision-brief.css': 'a8fc02f37a0cb5145d8803ca46c71fef89ce4ed2749b37f2444c33ed1f677e4a',
    'web/frontend/assets/css/design-system.css': '8c9c9271b80305f2514f39fc7c332304af4358dc066169794bf26b621081e187',
    'web/frontend/assets/css/evidence-envelope.css': '5910cccb833ae9a24710586d52c9a06973141c58e5743a16980162f0de01af5e',
    'web/frontend/assets/css/fonts-self-hosted.css': '6b9de622d7c90539d0bc2d54327d6ac5d695fd379f03bb42227cd361bfa61cfb',
    'web/frontend/assets/css/glossary.css': 'a2f90f00ae51b461dfde378249fcecd3425656aa9a849eb43f7e6ba1fcfed747',
    'web/frontend/assets/css/papers.css': 'd953ff2efa28079abae4e4221ff527d2050e5b510551853c36bea7c6caf4578d',
    'web/frontend/assets/css/reset.css': '95246049f624488169c78a0e143777fb73b49cd3c2db2c333ed066bb7306aa9a',
    'web/frontend/assets/css/responsive.css': 'd7b5402e9e7de598002ed678d5784e24284428fd72aa7b5963a2cba690c8527d',
    'web/frontend/assets/css/shared-tokens.css': '04484fab4c465f83ce7d37c440d1a13dabd8a6c24f61c51a5cfbf9ccc66cd210',
    'web/frontend/assets/data/i18n/content.json': '2d70555a42b9a652100c51374b0c3e9e7f2b52b4efca1fdf9474c0899a126889',
    'web/frontend/assets/data/i18n/ui.json': 'ab324b9e8a5b6131f93bb03e84609f319850431b30bf3f2c7f2dbca926f67f80',
    'web/frontend/assets/data/papers-manifest.json': 'f0b49f635e0ece7c1def745ee49dabcce8931f5836e795f5d154834a9e487803',
    'web/frontend/assets/fonts/crimson-pro-400-italic-latin.woff2': '1fac78d865686e4e1236e5e599f02c8afe05dd59d04344553cc45a160d53ac63',
    'web/frontend/assets/fonts/crimson-pro-400-latin.woff2': 'd2a3a146387d91b8d476d508849dd1d93a3cbde85d1e0d303e3d5c970726a703',
    'web/frontend/assets/fonts/crimson-pro-500-latin.woff2': '7d264f53a589d61475041f980a2f35a88cde1ec7012a8f661419e99769492684',
    'web/frontend/assets/fonts/crimson-pro-600-latin.woff2': '2d8f33b2352a04f3ed3af648df66d053c00d5c3ccbe793797273509824a5044a',
    'web/frontend/assets/fonts/inter-400-latin.woff2': '8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc',
    'web/frontend/assets/fonts/inter-500-latin.woff2': 'f3779f1efccc4bdcdf9c0a02ab95bf6bd092ed09c48c08cedc725889edd1d19f',
    'web/frontend/assets/fonts/inter-600-latin.woff2': 'f9a06e79cd3a2a20951c0f0e28f66dd0e6d3fda73911d640a2125c8fcb78f21a',
    'web/frontend/assets/fonts/inter-700-latin.woff2': '6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491',
    'web/frontend/assets/fonts/jetbrains-mono-400-latin.woff2': '14425ba9c695763c1547f48a206b7aa60350a33ae23de09f0407877f3fcd89eb',
    'web/frontend/assets/fonts/jetbrains-mono-500-latin.woff2': 'cb182feeed4d798ff6961d3c79f7026279448fca0676438aaecb21f3fc39553a',
    'web/frontend/assets/fonts/noto-serif-sc-400-latin.woff2': 'af0c95a3e897cfab6a319a789f203dc64b8f81574f8113c7d46240db68c8ff8f',
    'web/frontend/assets/fonts/noto-serif-sc-500-latin.woff2': 'f7116e1f4df8174acc2efe1d0878a2d1803e06829ba297df3cc53cfd4d9f3ec5',
    'web/frontend/assets/fonts/noto-serif-sc-600-latin.woff2': '3d7ce0ff551c2c3ab3a4647a4e69dd166b0bf251ce766b3cfcc6955c19c1ce18',
    'web/frontend/assets/fonts/noto-serif-sc-700-latin.woff2': '9a95913aa3f827281ad89ec6253bb71be94bb23dc3184ec3462a15acd7ff05e4',
    'web/frontend/assets/icons/favicon.svg': 'f7c982f28f2cc2156838435db8e4d7aa42e2ea3626c5361c0db0e5c01517fded',
    'web/frontend/assets/js/analytics-consent.js': '7accbe4d3b50eac3f94a75824e2048423de3c486b5eae67365e9be9948f91eec',
    'web/frontend/assets/js/analyze.js': 'c767858002433f325ddb8230a9347e443a5cfc3f318c0981243ce428830b5367',
    'web/frontend/assets/js/api.js': '85a3970f54312d04a1258383aabca515398d6ee6ff02ef10b75a9f4032877623',
    'web/frontend/assets/js/evidence-envelope.js': '5f357c9c3da4ec32b7b39a0fb853caa9d728eaa3556c1e06a8cf0b09c71c4817',
    'web/frontend/assets/js/glossary.js': '47fe46e9197d24f33e33189017f5de31acf83ada443d08f3a080fb0851b6944b',
    'web/frontend/assets/js/history-sidebar.js': '262c38698adeaeb2831a2ebf4bdefc0a5651bed7308889434869f42a1e0daa6f',
    'web/frontend/assets/js/i18n.js': '5c105839268bbb8014767bbacf91093681ec4d976229cf9968fe5a970ea98e61',
    'web/frontend/assets/js/papers-catalog.js': 'c81d8014f68dfb2f1f8f5e8e36edbef9551db95d0791d8b36200ac8b33ee4cd4',
    'web/frontend/assets/js/papers.js': '7643c5974aceee5d78d582fb3092b42818cf10b301d7fbe0699390f28cc24b9a',
    'web/frontend/assets/js/product-switcher.js': 'a4e37c9a42cb8ead1ea007e7734ccb23658e6730e74f21c3cba691426531ef26',
    'web/frontend/assets/js/site-chrome.js': 'b142f26f2eadb53d6b39039b556fac44e03966734aee932e4e8cc6b636ee28d7',
    'web/frontend/assets/js/utils.js': 'e8d167b628c8531c2ae938316f1f6240871458683091ad520034a7e10ebae7ab',
    'web/frontend/assets/js/utils/buildAnalyzeUrl.js': 'ae672524b16efadd7317a4dd7df5f434211fa622b56865042017b82b034b8a53',
    'web/frontend/papers.html': '0614345df1c41e1eb2ef1f79e01c386815016dc86e67a48ab3cf4ecece2d0e75',
}


class DiagnosticError(Exception):
    """Only closed error codes, never raw subprocess/provider messages."""


class NotScheduled(DiagnosticError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path: Path, limit: int) -> bytes:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise DiagnosticError("input_not_bounded_regular_file")
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise DiagnosticError("input_too_large")
    return data


def decode_json(data: bytes) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise DiagnosticError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise DiagnosticError("nonfinite_json")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)


def read_json(path: Path, limit: int = 16 * 1024 * 1024) -> Any:
    return decode_json(regular_bytes(path, limit))


@dataclass(frozen=True)
class Identity:
    checkout_sha: str
    head_sha: str
    run_id: str
    run_attempt: int = 1


def validate_event(env: dict[str, str], event: dict[str, Any]) -> Identity:
    if (not isinstance(event, dict) or env.get("GITHUB_REPOSITORY") != REPOSITORY
            or env.get("GITHUB_EVENT_NAME") != "pull_request"
            or env.get("GITHUB_RUN_ATTEMPT") != "1"
            or event.get("action") != "synchronize"):
        raise NotScheduled("event_not_approved")
    pr = event.get("pull_request", {})
    if (not isinstance(pr, dict) or type(pr.get("number")) is not int or pr["number"] != PR_NUMBER
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPOSITORY
            or pr.get("base", {}).get("repo", {}).get("full_name") != REPOSITORY):
        raise NotScheduled("pull_request_not_approved")
    checkout = env.get("GITHUB_SHA", "")
    head = pr.get("head", {}).get("sha", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    if (not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head)
            or not re.fullmatch(r"[0-9a-f]{40}", checkout)
            or not re.fullmatch(r"[1-9][0-9]{0,19}", run_id)):
        raise DiagnosticError("invalid_identity")
    return Identity(checkout, head, run_id)


def git_read(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=10)
    if result.returncode:
        raise DiagnosticError("required_git_object_unavailable")
    return result.stdout


def verify_binding(root: Path, identity: Identity, *, pins=None, read_git=git_read) -> dict[str, str]:
    pins = SOURCE_PINS if pins is None else pins
    if read_git(root, "rev-parse", "HEAD").decode().strip() != identity.checkout_sha:
        raise DiagnosticError("checkout_identity_mismatch")
    if read_git(root, "cat-file", "-t", identity.head_sha).decode().strip() != "commit":
        raise DiagnosticError("head_not_commit")
    subject = read_git(root, "show", "-s", "--format=%s", identity.head_sha).decode().rstrip("\n")
    if subject != MARKER_SUBJECT:
        raise NotScheduled("marker_not_approved")
    actual = {}
    for relative, expected in pins.items():
        local = digest(regular_bytes(root / relative, 4 * 1024 * 1024))
        head = digest(read_git(root, "show", f"{identity.head_sha}:{relative}"))
        checkout = digest(read_git(root, "show", f"{identity.checkout_sha}:{relative}"))
        if local != expected or head != expected or checkout != expected:
            raise DiagnosticError("source_digest_mismatch")
        actual[relative] = local
    relative = "scripts/beta_perf_diagnostics.py"
    if (digest(regular_bytes(root / relative, 1024 * 1024))
            != digest(read_git(root, "show", f"{identity.head_sha}:{relative}"))
            or read_git(root, "show", f"{identity.head_sha}:{relative}")
            != read_git(root, "show", f"{identity.checkout_sha}:{relative}")):
        raise DiagnosticError("diagnostic_script_mismatch")
    actual[relative] = digest(regular_bytes(root / relative, 1024 * 1024))
    return actual


def verify_grade(path: Path, pins=None) -> tuple[dict, str]:
    pins = SOURCE_PINS if pins is None else pins
    original = regular_bytes(path, 16 * 1024 * 1024)
    grade = decode_json(original)
    if (not isinstance(grade, dict) or grade.get("schema_version") != 2 or grade.get("engine") != "scripts/perf_audit.py:audit_one"
            or grade.get("runs_per_page") != 3 or grade.get("status") not in {"passed", "failed"}
            or grade.get("profiles", {}).get("mobile") != {"cpu_throttle": 4, "network": "slow-4g"}
            or grade.get("profiles", {}).get("tbt_window_ms") != 5000
            or grade.get("source_snapshot_sha256") != {p: pins[p] for p in GRADE_SOURCE_PATHS}):
        raise DiagnosticError("original_grade_identity_mismatch")
    expected_pages = {"home", "search", "analyze", "reports", "discoveries", "classes", "papers", "tools"}
    if set(grade.get("pages", {})) != expected_pages:
        raise DiagnosticError("original_audit_incomplete")
    for name, page in grade["pages"].items():
        if set(page.get("viewports", {})) != {"desktop", "mobile"}:
            raise DiagnosticError("original_audit_incomplete")
        for result in page["viewports"].values():
            runs = result.get("raw_runs", [])
            if (len(runs) != 3 or any(type(r.get("run_index")) is not int for r in runs)
                    or {r["run_index"] for r in runs} != {1, 2, 3}
                    or any(r.get("cleanup_status") not in {"passed", "failed"} for r in runs)):
                raise DiagnosticError("original_audit_incomplete")
        if name in PAGE_PATHS and page.get("path") != PAGE_PATHS[name]:
            raise DiagnosticError("original_case_changed")
    return grade, digest(original)


def require_linux() -> None:
    if sys.platform != "linux" or platform.system() != "Linux":
        raise DiagnosticError("linux_only_no_local_capture_override")


def verify_dependencies() -> dict[str, str]:
    if sys.version_info[:2] != (3, 11):
        raise DiagnosticError("python_311_required")
    versions = {p: importlib.metadata.version(p) for p in ("playwright", "pydantic")}
    if versions != {"playwright": "1.59.0", "pydantic": "2.7.4"}:
        raise DiagnosticError("pinned_dependencies_unavailable")
    return {"python": platform.python_version(), **versions}


def validate_base(base: str, original_base: str) -> tuple[str, str, int]:
    parsed = urlsplit(base)
    if (base != original_base or parsed.scheme != "http" or parsed.hostname != "127.0.0.1"
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != "/" or parsed.port is None):
        raise DiagnosticError("base_not_original_loopback_service")
    return parsed.scheme, parsed.hostname, parsed.port


def verify_service(base: str, root: Path, *, pins=None) -> None:
    pins = SOURCE_PINS if pins is None else pins
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            raise DiagnosticError("service_redirect_refused")

    opener = build_opener(ProxyHandler({}), NoRedirect())
    requests = {PAGE_PATHS[name]: f"web/frontend/{name}.html" for name in PAGES}
    requests.update({p.removeprefix("web/frontend/"): p for p in pins
                     if p.startswith("web/frontend/assets/")})
    for path, relative in requests.items():
        with opener.open(base + path, timeout=5) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            expected = regular_bytes(root / relative, 4 * 1024 * 1024)
            if response.status != 200 or body != expected or digest(body) != pins[relative]:
                raise DiagnosticError("static_service_not_ready")


class ArtifactWriter:
    """Exclusive files and a combined per-page byte cap, including control files."""

    def __init__(self, root: Path, limit: int = MAX_PAGE_BYTES):
        self.root, self.limit, self.used = root, limit, 0
        self.reserve = min(4096, limit // 4)

    def write_chunks(self, name: str, chunks, *, control=False) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_.-]*\.json", name):
            raise DiagnosticError("invalid_artifact_name")
        fd = os.open(self.root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as stream:
            for chunk in chunks:
                chunk = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                ceiling = self.limit if control else self.limit - self.reserve
                if self.used + len(chunk) > ceiling:
                    raise DiagnosticError("page_artifact_capacity_exceeded")
                stream.write(chunk)
                self.used += len(chunk)

    def write_json(self, name: str, value: Any, *, control=False) -> None:
        chunks = json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(value)
        self.write_chunks(name, chunks, control=control)


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise DiagnosticError("output_symlink_refused")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = path.stat()
    if not path.is_dir() or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) != 0o700:
        raise DiagnosticError("output_must_be_owned_private_directory")


def claim_attempt(out: Path, identity: Identity) -> None:
    if not out.is_absolute() or out.resolve() != out or out == ROOT or ROOT in out.parents:
        raise DiagnosticError("artifacts_must_be_outside_checkout")
    private_directory(out)
    ArtifactWriter(out).write_json("attempt.started.json", {
        "classification": "NOT_GATE", "marker": MARKER_SUBJECT,
        "run_id": identity.run_id, "run_attempt": identity.run_attempt,
        "checkout_sha": identity.checkout_sha, "head_sha": identity.head_sha,
    }, control=True)


RAW_SCRIPT = """() => ({timeOrigin:performance.timeOrigin,now:performance.now(),
 perf:window.__perf?{longTasks:window.__perf.longTasks,loaf:window.__perf.loaf,events:window.__perf.events}:null,
 resources:performance.getEntriesByType('resource').map(x=>({name:x.name,startTime:x.startTime,duration:x.duration,responseEnd:x.responseEnd,transferSize:x.transferSize,initiatorType:x.initiatorType})),
 navigation:performance.getEntriesByType('navigation').map(x=>x.toJSON())})"""
TRACE_CATEGORIES = ",".join((
    "devtools.timeline", "v8", "blink.user_timing", "disabled-by-default-devtools.timeline",
    "disabled-by-default-devtools.timeline.invalidationTracking", "disabled-by-default-devtools.timeline.stack",
))


class Capture:
    def __init__(self, writer: ArtifactWriter, *, clock=time.monotonic):
        self.writer, self.clock = writer, clock
        self.page = self.cdp = None
        self.profiling = self.tracing = self.captured = False
        self.stream_closed = False
        self.complete = {}
        self.seen = {}
        self.errors = []
        self.final_sample = None

    def setup(self, page):
        self.page = page
        self.cdp = page.context.new_cdp_session(page)
        self.cdp.on("Tracing.tracingComplete", lambda event: self.complete.update(event))
        available = self.cdp.send("Tracing.getCategories").get("categories", [])
        if "disabled-by-default-devtools.timeline.invalidationTracking" not in available:
            self.errors.append("invalidation_category_unavailable")
            raise DiagnosticError("invalidation_category_unavailable")
        self.cdp.send("Profiler.enable")
        self.cdp.send("Profiler.setSamplingInterval", {"interval": 1000})
        self.cdp.send("Profiler.start")
        self.profiling = True
        self.cdp.send("Tracing.start", {"categories": TRACE_CATEGORIES, "transferMode": "ReturnAsStream"})
        self.tracing = True

    def sink(self, sample):
        phase = sample.get("cleanup_status")
        if phase not in {"pending", "passed", "failed"}:
            self.errors.append("invalid_cleanup_checkpoint")
            return
        key = "pending" if phase == "pending" else "final"
        fingerprint = digest(json.dumps(sample, sort_keys=True, allow_nan=False).encode())
        if key in self.seen:
            if self.seen[key] != fingerprint:
                self.errors.append("checkpoint_replay_conflict")
            return
        self.seen[key] = fingerprint
        self.final_sample = sample
        try:
            self.writer.write_json(f"audit.{key}.json", sample)
            if key == "pending" and not self.captured:
                self.captured = True
                self.capture()
        except DiagnosticError as exc:
            self.errors.append(str(exc))
        except Exception:
            self.errors.append("capture_incomplete")
        finally:
            if key == "pending":
                self.stop_and_detach()

    def capture(self):
        if self.page is None or self.cdp is None or not self.profiling or not self.tracing:
            raise DiagnosticError("capture_setup_incomplete")
        self.writer.write_json("raw.json", self.page.evaluate(RAW_SCRIPT))
        profile = self.cdp.send("Profiler.stop")
        self.profiling = False
        self.writer.write_json("cpu.json", profile)
        deadline = self.clock() + STOP_WAIT_SECONDS
        self.cdp.send("Tracing.end")
        self.tracing = False
        while not self.complete:
            remaining = deadline - self.clock()
            if remaining <= 0:
                break
            self.page.wait_for_timeout(min(25, remaining * 1000))
        if not self.complete.get("stream"):
            raise DiagnosticError("trace_stop_timeout")
        handle = self.complete["stream"]

        def chunks():
            while True:
                if self.clock() >= deadline:
                    raise DiagnosticError("trace_stream_deadline")
                value = self.cdp.send("IO.read", {"handle": handle, "size": 1024 * 1024})
                data = value.get("data", "")
                yield base64.b64decode(data, validate=True) if value.get("base64Encoded") else data.encode("utf-8")
                if value.get("eof"):
                    break
        try:
            self.writer.write_chunks("timeline.json", chunks())
        finally:
            self.cdp.send("IO.close", {"handle": handle})
            self.stream_closed = True

    def stop_and_detach(self):
        if self.cdp is None:
            return
        for active, method in (("profiling", "Profiler.stop"), ("tracing", "Tracing.end")):
            if getattr(self, active):
                setattr(self, active, False)
                try:
                    self.cdp.send(method)
                except Exception:
                    self.errors.append("cdp_cleanup_failed")
        if self.complete.get("stream") and not self.stream_closed:
            try:
                self.cdp.send("IO.close", {"handle": self.complete["stream"]})
                self.stream_closed = True
            except Exception:
                self.errors.append("trace_stream_cleanup_failed")
        try:
            self.cdp.detach()
        except Exception:
            self.errors.append("cdp_detach_failed")
        self.cdp = None

    def close(self):
        self.stop_and_detach()
        if self.page is not None:
            try:
                browser = self.page.context.browser
                if browser is not None and browser.is_connected():
                    browser.close()
            except Exception:
                self.errors.append("owned_browser_cleanup_failed")


def runner_snapshot() -> dict:
    data = {"system": platform.system(), "machine": platform.machine(), "kernel": platform.release(),
            "logical_cpus": os.cpu_count(), "load_average": list(os.getloadavg())}
    for name in ("cpu.max", "cpu.stat", "cpu.pressure", "memory.current", "memory.max"):
        p = Path("/sys/fs/cgroup") / name
        try:
            value = regular_bytes(p, 2048).decode()
            if re.fullmatch(r"[a-zA-Z0-9_.= \n-]*", value):
                data[name] = value
        except (OSError, DiagnosticError):
            pass
    counts = {"chromium": 0, "node": 0}
    for p in Path("/proc").glob("[0-9]*/comm"):
        try:
            name = regular_bytes(p, 128).decode().strip().lower()
            if "chrome" in name or "chromium" in name:
                counts["chromium"] += 1
            elif name == "node":
                counts["node"] += 1
        except (OSError, DiagnosticError):
            pass
    data["process_counts_no_arguments"] = counts
    return data


def collect_pair(runtime, beta, perf, base: str, out: Path, *, unchanged=lambda: None,
                 metrics=runner_snapshot, capture_factory=Capture, results=None) -> list[dict]:
    case_request, case_stream = beta._analyze_fixture()
    origin_url = urlsplit(base)
    origin = (origin_url.scheme, origin_url.hostname, origin_url.port)
    results = [] if results is None else results
    for name in PAGES:
        unchanged()
        directory = out / name
        private_directory(directory)
        writer = ArtifactWriter(directory)
        writer.write_json("started.json", {"classification": "NOT_GATE", "page": name, "captures": 1}, control=True)
        capture = capture_factory(writer)
        case = beta.PAGES[name]
        original_setup = beta._page_setup_factory(name, case, origin, case_request, case_stream)

        def setup(page, viewport, run):
            fixture_state = original_setup(page, viewport, run)
            capture.setup(page)
            return fixture_state

        error = None
        try:
            writer.write_json("runner.before.json", metrics())
            perf.audit_one(runtime, base, case.path, "mobile", beta.VIEWPORTS["mobile"],
                case.interaction_selector, runs=1, page_setup=setup, ready_selector=case.ready_selector,
                page_validator=beta._page_validator(name, case),
                post_interaction_validator=beta._post_interaction_validator(name),
                interaction_mode=case.interaction_mode, run_evidence_sink=capture.sink)
        except Exception:
            error = "diagnostic_audit_incomplete"
        finally:
            capture.close()
        try:
            writer.write_json("runner.after.json", metrics())
        except Exception:
            capture.errors.append("runner_evidence_incomplete")
        sample = capture.final_sample or {}
        complete = (error is None and not capture.errors and capture.captured
                    and sample.get("audit_status") == "passed" and sample.get("cleanup_status") == "passed")
        summary = {"classification": "NOT_GATE", "page": name,
                   "status": "complete" if complete else "incomplete",
                   "reason": error, "capture_errors": capture.errors[:8], "bytes_before_summary": writer.used,
                   "invalidation_requested": True, "profiling_overhead": True}
        writer.write_json("summary.json", summary, control=True)
        results.append(summary)
        unchanged()
    return results


@contextmanager
def termination_cleanup():
    def interrupt(_number, _frame):
        raise KeyboardInterrupt()
    saved = {s: signal.signal(s, interrupt) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        yield
    finally:
        for signum, handler in saved.items():
            signal.signal(signum, handler)


def run(args) -> dict:
    require_linux()
    env = {key: os.environ.get(key, "") for key in ENV_KEYS}
    identity = validate_event(env, read_json(Path(env["GITHUB_EVENT_PATH"]), 1024 * 1024))
    sources = verify_binding(ROOT, identity)
    if args.grade_outcome not in {"success", "failure"}:
        raise DiagnosticError("original_step_not_finished")
    grade_path = Path(args.grade_artifact)
    grade, original_digest = verify_grade(grade_path)
    if args.grade_outcome not in {"success", "failure"} or grade["status"] != {
            "success": "passed", "failure": "failed"}[args.grade_outcome]:
        raise DiagnosticError("grade_outcome_artifact_mismatch")
    validate_base(args.base, grade.get("base_url", ""))
    versions = verify_dependencies()
    verify_service(args.base, ROOT)
    out = Path(args.out)
    claim_attempt(out, identity)
    header = {"classification": "NOT_GATE", "status": "incomplete", "base_source_sha": BASE_SHA,
              "checkout_sha": identity.checkout_sha, "pr_head_sha": identity.head_sha,
              "run_id": identity.run_id, "run_attempt": identity.run_attempt, "versions": versions,
              "original_step_outcome": args.grade_outcome,
              "original_grade_status": grade["status"], "original_grade_sha256": original_digest,
              "sources": sources, "requested_pages": list(PAGES), "pages": []}
    overall = ArtifactWriter(out)

    def unchanged():
        if digest(regular_bytes(grade_path, 16 * 1024 * 1024)) != original_digest:
            raise DiagnosticError("original_grade_changed")
        for relative, expected in sources.items():
            if digest(regular_bytes(ROOT / relative, 4 * 1024 * 1024)) != expected:
                raise DiagnosticError("sources_changed_during_diagnostics")

    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        beta = importlib.import_module("scripts.beta_perf_audit")
        perf = importlib.import_module("scripts.perf_audit")
        if any(Path(mod.__file__).resolve() != ROOT / "scripts" / (mod.__name__.split(".")[-1] + ".py")
               for mod in (beta, perf)):
            raise DiagnosticError("audit_module_origin_mismatch")
        from playwright.sync_api import sync_playwright
        with termination_cleanup(), sync_playwright() as runtime:
            binary = Path(runtime.chromium.executable_path)
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise DiagnosticError("installed_browser_missing")
            collect_pair(runtime, beta, perf, args.base, out, unchanged=unchanged,
                         metrics=runner_snapshot, results=header["pages"])
        unchanged()
        if all(p["status"] == "complete" for p in header["pages"]):
            header["status"] = "complete"
    except DiagnosticError as exc:
        header["reason"] = str(exc)
    except KeyboardInterrupt:
        header["reason"] = "diagnostic_interrupted_no_retry"
    except Exception:
        header["reason"] = "diagnostics_incomplete_no_retry"
    finally:
        header["started_pages"] = [p for p in PAGES if (out / p / "started.json").is_file()]
        overall.write_json("diagnostic.json", header, control=True)
    return header


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grade-artifact", required=True)
    parser.add_argument("--grade-outcome", choices=("success", "failure", "skipped", "cancelled"), required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except NotScheduled as exc:
        result = {"classification": "NOT_GATE", "status": "not_scheduled", "reason": str(exc)}
    except DiagnosticError as exc:
        result = {"classification": "NOT_GATE", "status": "incomplete", "reason": str(exc)}
    except Exception:
        result = {"classification": "NOT_GATE", "status": "incomplete", "reason": "preflight_rejected"}
    print(json.dumps({k: result[k] for k in ("classification", "status", "reason") if k in result}))
    return 0 if result["status"] in {"complete", "not_scheduled"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
