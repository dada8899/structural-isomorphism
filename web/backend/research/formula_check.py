"""Fixed-template math core and fail-closed isolated entrypoint; no DB or LLM.

`FormulaChecker.check` is the candidate execution boundary, not a frozen API.
The pure core is testable separately but is NOT a sandbox or product runner.
Linux guards use an absolute RLIMIT_AS = measured child VMS + 128 MiB, not a
claim that process creation itself limits memory. Unsupported hosts fail closed.
"""
from __future__ import annotations

from dataclasses import replace
import json
import math
import multiprocessing
import os
from pathlib import Path
try:
    import resource
except ImportError:  # unsupported platforms do not silently run unguarded
    resource = None
import sys
import time

from .formula_schemas import (
    CheckOutcome, FormulaCheckInput, FormulaCheckResult, FormulaInputError, FormulaLimit, canonical, digest,
)
from .formula_policy import (
    POLICY, ABS_TOL, REL_TOL, CORPUS_DIGEST, CORPUS_LOCATORS, PolicyIssue, comparison, dimensions, numeric_result, recognize,
)

RESULT_CAP = 512 * 1024
EXTRA_MEMORY = 128 * 1024 * 1024
WALL_SECONDS = 2.0
CPU_SECONDS = 1
CORE_GUARD = "pure_core_not_a_sandbox"


def _sources(request):
    return tuple({ref.id: ref for form in (request.left, request.right) if form for ref in form.source_refs}.values())


def _result(request, outcomes, guard=CORE_GUARD):
    formula_refs = tuple({"id": form.id, "revision": form.revision, "formula_digest": digest(form.data()), "checked_representation": "validated_AST"} for form in (request.left, request.right) if form)
    return FormulaCheckResult(request.input_digest, request.research_id, request.input_revision, request.task_id, request.attempt,
        request.comparison_scope, POLICY, formula_refs, tuple(outcomes), _sources(request),
        ("Mathematics under declared assumptions is not observed mechanism or successful transfer.",
         "Only the validated AST is checked; original display text is not parsed or proved.",
         "Curated SOURCE_CORPUS references are historical editorial references, not product-retrieved excerpts.",
         "Numeric agreement is limited to recorded points; it cannot prove an identity or predict a collapse date."), guard)


def _uniform(request, status, reason, guard):
    return _result(request, [CheckOutcome(kind, status, "undetermined", reason) for kind in request.requested_checks], guard)


def evaluate_fixed_templates(request):
    """Pure deterministic math consumer. Only the guarded worker is executable
    from a future product API. Direct calls in tests do not prove isolation.
    """
    request = FormulaCheckInput.parse(request.data())
    for form in (request.left, request.right):
        if form:
            for source in form.source_refs:
                if source.provenance == "curated_reference" and (source.content_digest != CORPUS_DIGEST or source.locator not in CORPUS_LOCATORS.get(form.template_id, ())):
                    return _uniform(request, "unsupported", "curated_reference_version_or_locator", CORE_GUARD)
    outcomes = []
    forms = (request.left,) if request.right is None else (request.left, request.right)
    for kind in request.requested_checks:
        try:
            if kind == "template":
                for form in forms: recognize(form)
                outcome = CheckOutcome(kind, "passed", "undetermined", "finite_template_shape_only")
            elif kind == "dimensions":
                for form in forms: dimensions(form)
                outcome = CheckOutcome(kind, "passed", "undetermined", "each_side_dimensions_and_semantic_roles_only")
            elif kind == "canonical_transform":
                relation, trace = comparison(request.left, request.right, request.comparison_scope)
                outcome = CheckOutcome(kind, "passed", relation, "within_declared_scope", trace)
            else:
                if not request.sample_points:
                    raise PolicyIssue("inconclusive", "explicit_sample_points_missing")
                if request.left.template_id in {"little", "mm1"} and request.sample_points != ("0",):
                    raise PolicyIssue("unsupported", "queue_numeric_is_one_fixed_parameter_case_not_a_time_grid")
                comparison(request.left, request.right, request.comparison_scope)
                samples, equal = [], True
                for point in request.sample_points:
                    left = numeric_result(request.left, point, request.comparison_scope)
                    right = numeric_result(request.right, point, request.comparison_scope)
                    exact = left["arithmetic"] == right["arithmetic"] == "exact_rational"
                    if exact:
                        # Output is a bounded Fraction representation, not a
                        # reparse of arbitrary strings supplied by a client.
                        from fractions import Fraction
                        passed = Fraction(left["value"]) == Fraction(right["value"])
                    else:
                        a, b = float(left["value"]), float(right["value"])
                        passed = math.isfinite(a) and math.isfinite(b) and abs(a-b) <= ABS_TOL + REL_TOL * max(abs(a), abs(b))
                    equal &= passed
                    samples.append({"point": point, "left": left, "right": right, "passed": passed,
                                    "comparison": "exact" if exact else "abs1e-10_rel1e-8_normalized_only"})
                tolerance = None if all(v["comparison"] == "exact" for v in samples) else {"absolute": "1e-10", "relative": "1e-8", "policy_revision": POLICY, "scope": "normalized_same_scale_samples_only"}
                outcome = CheckOutcome(kind, "passed" if equal else "failed", "undetermined", "recorded_samples_only", samples=tuple(samples), tolerance=tolerance)
            outcomes.append(outcome)
        except FormulaLimit:
            outcomes.append(CheckOutcome(kind, "resource_limit", "undetermined", "policy_resource_bound"))
        except PolicyIssue as issue:
            relation = "not_equivalent" if issue.reason == "zero_nonzero_initial_problems_not_equivalent" else "undetermined"
            outcomes.append(CheckOutcome(kind, issue.status, relation, issue.reason))
    return _result(request, outcomes)


def _linux_limits():
    if sys.platform != "linux" or not hasattr(resource, "RLIMIT_AS"):
        return False
    try:
        # VMS pages, not RSS/high-water memory. Measure after fixed imports and
        # before decoding/computing untrusted input. Bound added address space.
        pages = Path("/proc/self/statm").read_text().split()[0]
        if not pages.isdecimal() or len(pages) > 20: return False
        baseline = int(pages) * os.sysconf("SC_PAGE_SIZE")
        cap = baseline + EXTRA_MEMORY
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
        return resource.getrlimit(resource.RLIMIT_AS) == (cap, cap) and resource.getrlimit(resource.RLIMIT_CPU) == (CPU_SECONDS, CPU_SECONDS)
    except (OSError, ValueError, OverflowError):
        return False


def _worker(send, shared, payload, operation):
    try:
        # Fixed, private diagnostic code paths: no user-callable functions or
        # code strings. CPU/wall probes never evaluate a formula without AS.
        if operation == "probe_cpu":
            if resource is None:
                send.send_bytes(b"unsupported")
                return
            resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
            while True: pass
        if operation == "probe_wall":
            time.sleep(10)
            return
        if not _linux_limits():
            send.send_bytes(b"unsupported")
            return
        if operation == "probe_memory":
            try:
                block = bytearray(EXTRA_MEMORY * 2)
                del block
                send.send_bytes(b"guard_failed")
            except MemoryError:
                send.send_bytes(b"memory_limited")
            return
        if operation != "calculate":
            send.send_bytes(b"failed")
            return
        request = FormulaCheckInput.parse(json.loads(payload))
        result = evaluate_fixed_templates(request)
        result = replace(result, resource_guard="linux_as_baseline_plus_128mib_cpu1s_wall2s")
        encoded = canonical(result.data()).encode()
        if len(encoded) > RESULT_CAP:
            send.send_bytes(b"limited")
            return
        memoryview(shared).cast("B")[:len(encoded)] = encoded
        send.send_bytes(str(len(encoded)).encode())
    except (MemoryError, FormulaLimit):
        send.send_bytes(b"limited")
    except Exception:
        try: send.send_bytes(b"failed")
        except (OSError, EOFError): pass
    finally:
        send.close()


def _launch(payload, still_authorized, operation="calculate", wall=WALL_SECONDS):
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    shared = ctx.RawArray("B", RESULT_CAP)
    process = ctx.Process(target=_worker, args=(send, shared, payload, operation), daemon=True)
    deadline = time.monotonic() + wall
    try:
        if still_authorized() is not True: return "revoked", None
        process.start()
        send.close()
        while True:
            if still_authorized() is not True: return "revoked", None
            remaining = deadline - time.monotonic()
            if remaining <= 0: return "limited", None
            if receive.poll(min(0.01, remaining)):
                try: message = receive.recv_bytes(64)
                except (EOFError, OSError):
                    process.join(timeout=0.05)
                    return ("cpu_limited" if operation == "probe_cpu" and process.exitcode is not None and process.exitcode < 0 else "limited"), None
                if time.monotonic() >= deadline: return "limited", None
                if still_authorized() is not True: return "revoked", None
                if not message.isdigit(): return message.decode("ascii"), None
                length = int(message)
                if not 0 < length <= RESULT_CAP: return "failed", None
                return "ok", bytes(memoryview(shared).cast("B")[:length])
            if not process.is_alive(): return "limited", None
    finally:
        receive.close(); send.close()
        if process.pid is not None:
            if process.is_alive(): process.terminate()
            process.join(timeout=0.25)
            if process.is_alive():
                process.kill(); process.join(timeout=0.25)
            process.close()


class FormulaChecker:
    @staticmethod
    def check(data, *, still_authorized):
        """Candidate bounded entry. C0 must authorize source refs and commit
        under its task/epoch/stop CAS; this class creates no storage or runner.
        Unsupported memory guards never fall back to this process's math core.
        """
        if not callable(still_authorized): raise FormulaInputError("current authorization callback required")
        request = FormulaCheckInput.parse(data)
        payload = canonical(request.data()).encode()
        if len(payload) > 65536: raise FormulaLimit("request body limit")
        state, encoded = _launch(payload, still_authorized)
        if state != "ok":
            status = "unsupported" if state == "unsupported" else "resource_limit" if state in {"limited", "memory_limited"} else "failed"
            reason = "memory_guard_unavailable" if state == "unsupported" else "access_ended" if state == "revoked" else "worker_stopped_or_resource_limit"
            return _uniform(request, status, reason, "not_executed" if state == "unsupported" else "isolated_execution_not_completed")
        raw = json.loads(encoded)
        if raw.get("input_digest") != request.input_digest or raw.get("comparison_scope") != request.comparison_scope:
            return _uniform(request, "failed", "worker_binding_mismatch", "isolated_execution_not_completed")
        if raw.get("output_digest") != digest({key: value for key, value in raw.items() if key != "output_digest"}):
            return _uniform(request, "failed", "worker_result_digest_mismatch", "isolated_execution_not_completed")
        outcomes = tuple(CheckOutcome(v["check_kind"], v["status"], v["relation"], v["reason"], tuple(v["trace"]), tuple(v["samples"]), v["tolerance"]) for v in raw["outcomes"])
        return _result(request, outcomes, raw["resource_guard"])


def _guard_probe(operation, *, wall=WALL_SECONDS):
    """Private fixed fault probes only; not accepted in FormulaCheckInput."""
    if operation not in {"probe_cpu", "probe_wall", "probe_memory"}:
        raise FormulaInputError("unknown fixed probe")
    return _launch(b"", lambda: True, operation, wall)[0]
