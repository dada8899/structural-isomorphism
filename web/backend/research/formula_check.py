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
    forms = {form.id: form for form in (request.left, request.right) if form}
    formula_refs = tuple({"id": form.id, "revision": form.revision, "formula_digest": digest(form.data()), "checked_representation": "validated_AST"} for form in forms.values())
    return FormulaCheckResult(request.input_digest, request.research_id, request.input_revision, request.task_id, request.attempt,
        request.comparison_scope, POLICY, formula_refs, tuple(outcomes), _sources(request),
        ("Mathematics under declared assumptions is not observed mechanism or successful transfer.",
         "Only the validated AST is checked; original display text is not parsed or proved.",
         "A tau-only solution does not verify any unprovided R*C or reciprocal-rate definition.",
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
                if recognize(request.left)[0] == "tau" and request.sample_points != ("0",):
                    raise PolicyIssue("unsupported", "timescale_numeric_is_one_fixed_parameter_case_not_a_time_grid")
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
        if operation not in {"calculate", "owned_calculate"}:
            send.send_bytes(b"failed")
            return
        decoded=json.loads(payload)
        owned=operation=='owned_calculate'
        if owned:
            if set(decoded)!={'request','claim_nonce','code_version'} or decoded['code_version']!=execution_code_version():
                send.send_bytes(b'failed');return
            request=FormulaCheckInput.parse(decoded['request'])
        else:request=FormulaCheckInput.parse(decoded)
        result = evaluate_fixed_templates(request)
        result = replace(result, resource_guard="linux_as_baseline_plus_128mib_cpu1s_wall2s")
        output=result.data()
        if owned:output={'result':output,'child_pid':os.getpid(),'claim_nonce':decoded['claim_nonce'],
            'input_digest':request.input_digest,'code_version':execution_code_version(),'policy_revision':POLICY,
            'resource_guard':result.resource_guard}
        encoded = canonical(output).encode()
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


def _launch(payload, still_authorized, operation="calculate", wall=WALL_SECONDS, *, _owned=None):
    ctx = multiprocessing.get_context("spawn")
    receive, send = ctx.Pipe(duplex=False)
    shared = ctx.RawArray("B", RESULT_CAP)
    process = ctx.Process(target=_worker, args=(send, shared, payload, operation), daemon=True)
    deadline = time.monotonic() + wall
    try:
        if still_authorized() is not True: return "revoked", None
        process.start()
        if _owned is not None:_owned.child_pid=process.pid
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
            if _owned is not None:
                _owned.reaped=not process.is_alive()
                _owned.exitcode=process.exitcode
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


# Owned-return capability is separate from mathematical content. The existing
# pure evaluator, public adapter, limits and tolerances are unchanged.
_OWNED_FACTORY=object()
_OWNED_RETURNS={}


class OwnedFormulaReturn:
    __slots__=('reference','creator','authority','child_pid','reaped','exitcode','state','payload','receipt','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _OWNED_FACTORY:raise TypeError('actual owned formula return required')
        for k,v in values.items():object.__setattr__(self,k,v)
    def __setattr__(self,*args):raise TypeError('owned formula return immutable')
    def __reduce__(self):raise TypeError('owned formula return cannot be serialized')
    def require(self,authority):
        if (not self.active or self.creator!=os.getpid() or self.authority is not authority
                or _OWNED_RETURNS.get(self.reference) is not self or not self.reaped):
            raise PermissionError('actual reaped formula return required')
        authority.require_identity()
        if digest(json.loads(self.payload))!=self.receipt['result_digest']:
            raise PermissionError('owned return bytes changed')
        return json.loads(self.payload),dict(self.receipt)
    def close(self):
        object.__setattr__(self,'active',False);_OWNED_RETURNS.pop(self.reference,None)


class _OwnedCapture:
    child_pid=None
    reaped=False
    exitcode=None


def owned_check(data,*,authority):
    from .formula_result import CurrentFormulaExecution
    if type(authority) is not CurrentFormulaExecution:raise PermissionError('actual formula claim required')
    authority.require_identity()
    request=FormulaCheckInput.parse(data)
    payload=canonical(request.data()).encode()
    if len(payload)>65536:raise FormulaLimit('request body limit')
    if request.input_digest!=authority.input_digest:raise PermissionError('claim input mismatch')
    capture=_OwnedCapture()
    owned_payload=canonical({'request':request.data(),'claim_nonce':authority.nonce,'code_version':authority.code_version}).encode()
    state,encoded=_launch(owned_payload,authority.current,operation='owned_calculate',_owned=capture)
    if capture.child_pid is None or not capture.reaped:raise PermissionError('worker was not owned and reaped')
    if state=='revoked':raise PermissionError('formula authorization ended before owned return')
    if state=='ok':
        envelope=json.loads(encoded)
        if (type(envelope) is not dict or set(envelope)!={'result','child_pid','claim_nonce','input_digest','code_version','policy_revision','resource_guard'}
                or envelope['child_pid']!=capture.child_pid or envelope['claim_nonce']!=authority.nonce
                or envelope['input_digest']!=request.input_digest or envelope['code_version']!=authority.code_version
                or envelope['policy_revision']!=POLICY or envelope['resource_guard']!='linux_as_baseline_plus_128mib_cpu1s_wall2s'):
            raise PermissionError('actual owned child return required')
        raw=envelope['result']
        if raw.get('input_digest')!=request.input_digest or raw.get('output_digest')!=digest({k:v for k,v in raw.items() if k!='output_digest'}):
            raise PermissionError('owned worker binding mismatch')
    else:
        status='unsupported' if state=='unsupported' else 'resource_limit' if state in {'limited','memory_limited'} else 'failed'
        reason='memory_guard_unavailable' if state=='unsupported' else 'access_ended' if state=='revoked' else 'worker_stopped_or_resource_limit'
        raw=_uniform(request,status,reason,'not_executed' if state=='unsupported' else 'isolated_execution_not_completed').data()
    from uuid import uuid4
    reference=str(uuid4())
    receipt={'reference':reference,'child_pid':capture.child_pid,'claim_nonce':authority.nonce,'input_digest':request.input_digest,
        'policy_revision':POLICY,'code_version':authority.code_version,
        'resource_guard':raw['resource_guard'],'return_state':state,'return_bytes_digest':__import__('hashlib').sha256(encoded or b'').hexdigest(),
        'return_bytes':len(encoded or b''),'result_digest':digest(raw),'reaped':capture.reaped,'exitcode':capture.exitcode}
    value=OwnedFormulaReturn(_factory=_OWNED_FACTORY,reference=reference,creator=os.getpid(),authority=authority,
        child_pid=capture.child_pid,reaped=capture.reaped,exitcode=capture.exitcode,state=state,payload=canonical(raw),receipt=receipt,active=True)
    _OWNED_RETURNS[reference]=value
    return value


def execution_code_version():
    import hashlib
    base=Path(__file__).parent
    value=hashlib.sha256()
    for name in ('formula_check.py','formula_policy.py','formula_schemas.py'):
        value.update(name.encode());value.update((base/name).read_bytes())
    return value.hexdigest()
