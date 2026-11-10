"""Owner-only request coordination for the production external answer sender."""
from dataclasses import dataclass
import threading
import time
from uuid import uuid4

from . import external_live_production as production,external_live_sender as sender
if __package__=="web.backend.services":
    from ..research import external_first_answer_contract as contract
    from ..research.errors import ResearchError
    from ..research.external_first_answer_catalog import project_closed_preview,read_main_recovery
    from ..research.external_first_answer_seam import _authorized_saved_revision
    from ..research.external_first_answer_state import TABLE
    from ..research.paid_control import require_authenticated_action
    from ..research.plan_native_financial import unresolved
    from ..research.provider_schemas import canonical,digest
else:
    from research import external_first_answer_contract as contract
    from research.errors import ResearchError
    from research.external_first_answer_catalog import project_closed_preview,read_main_recovery
    from research.external_first_answer_seam import _authorized_saved_revision
    from research.external_first_answer_state import TABLE
    from research.paid_control import require_authenticated_action
    from research.plan_native_financial import unresolved
    from research.provider_schemas import canonical,digest

_CACHE={}
_LOCK=threading.RLock()


@dataclass(frozen=True,slots=True,repr=False)
class _Offered:
    handle:object
    scope:object
    quote:object
    prepared:object
    operation_key:str


def current(app,service,identity):
    handle=production._LIVE.get(id(app))
    if handle is None:
        return None
    try:
        policy,_=sender._require_live(handle,app)
        actual=handle._binding.service
        if (actual.store.path!=service.store.path or actual.store.storage_identity!=service.store.storage_identity
                or identity.generation!=handle._expected.owner_generation
                or actual._principal(identity)!=handle._expected.owner_principal):
            return None
        _,expiry,_=sender._trust(handle,policy,now=int(time.time()))
        return handle,actual,policy,expiry
    except (contract.ContractError,ResearchError,OSError,ValueError,PermissionError,TypeError,AttributeError):
        return None


def _source(proof,identity,action,rid,revision,key,data):
    return require_authenticated_action(proof,identity=identity,action=action,research_id=rid,
        task_id=str(revision),key=key,body_digest=digest(canonical(data.model_dump(mode="json"))))


def _prune(now):
    retired=[key for key,value in _CACHE.items() if value.quote.valid_until<=now or
             production._LIVE.get(id(value.handle._app)) is not value.handle]
    for key in retired:_CACHE.pop(key,None)


def _require_unused_revision(conn,rid,rev):
    if conn.execute("SELECT 1 FROM "+TABLE+" WHERE research_id=? AND input_revision=?",(rid,rev)).fetchone():
        raise ResearchError("OPERATION_ALREADY_USED",409,"此问题修订已使用外部分析；请用原操作键查看状态。")


def preview(selected,identity,rid,rev,request,source):
    _source(source,identity,"external-answer-preview",rid,rev,"",request)
    handle,service,policy,_=selected
    if type(handle) is not production._LiveHandle:
        raise contract.ContractError("real_external_live_handle_required")
    actual_policy,_=sender._require_live(handle,handle._app)
    if actual_policy is not policy or service is not handle._binding.service:
        raise contract.ContractError("external_owner_binding_changed")
    now=int(time.time())
    _,price_expiry,_=sender._trust(handle,policy,now=now)
    valid_until=min(now+45,price_expiry)
    if valid_until<=now:raise contract.ContractError("external_quote_expired")
    with _authorized_saved_revision(service,identity,rid,rev,request.research_version) as (conn,scope,raw):
        if scope.problem_digest!=request.problem_digest:
            raise contract.ContractError("revision_binding_changed")
        _require_unused_revision(conn,rid,rev)
        key=policy.canary_operation_key if policy.request_mode=="canary" else str(uuid4())
        if production.operation_already_spent(handle._app,handle,key):
            raise ResearchError("OPERATION_ALREADY_USED",409,"本次外部分析许可已使用；不会再次发送。")
        expected=handle._expected
        if (scope.principal_id,scope.auth_generation)!=(expected.owner_principal,expected.owner_generation):
            raise contract.ContractError("external_owner_binding_changed")
        account=conn.execute("""SELECT settled,held,upper_booked FROM research_funding_accounts
            WHERE id=? AND binding_id=? AND funding_epoch=? AND provider='deepseek' AND currency='CNY' AND scale=6""",
            (expected.account_id,expected.economic_binding,expected.funding_epoch)).fetchone()
        if account is None or unresolved(conn,expected.account_id):
            raise contract.ContractError("shared_ledger_unavailable")
        if sum(account)+policy.upper_units>contract.CAP_UNITS:
            raise contract.ContractError("shared_budget_exhausted")
        quote=contract.QuoteBinding(purpose=contract.PURPOSE,project_ref=contract.PROJECT,
            provider=contract.PROVIDER,model=contract.MODEL,account_id=expected.account_id,
            economic_binding=expected.economic_binding,funding_epoch=expected.funding_epoch,
            quote_id=str(uuid4()),price_basis_digest=policy.price_basis_sha256,currency="CNY",
            scale=6,upper_units=policy.upper_units,issued_at=now,valid_until=valid_until)
        prepared=contract.prepare_closed_preview(scope,raw,quote,now=now)
        if policy.request_mode=="canary" and prepared.request_digest!=policy.canary_request_sha256:
            raise contract.ContractError("external_canary_binding_changed")
        with _LOCK:
            _prune(now)
            if len(_CACHE)>=32:raise contract.ContractError("preview_capacity")
            _CACHE[prepared.preview_digest]=_Offered(handle,scope,quote,prepared,key)
        return project_closed_preview(scope,raw,quote,now=now)|{"may_send":True,"operation_key":key}


def confirm(selected,app,identity,rid,rev,key,decision,source):
    _source(source,identity,"external-answer-confirm",rid,rev,key,decision)
    handle,service,policy,_=selected
    actual_policy,_=sender._require_live(handle,app)
    if actual_policy is not policy or service is not handle._binding.service:
        raise contract.ContractError("external_owner_binding_changed")
    sender._request_binding(policy,key,decision.request_digest)
    try:original=read_main_recovery(service,identity,rid,rev,key)
    except ResearchError as error:
        if error.code!="NOT_FOUND":raise
        original=None
    if original is not None:
        with service.store.transaction() as conn:
            bound=conn.execute("SELECT preview_digest,request_digest,upper_units FROM "+TABLE+
                " WHERE id=? AND research_id=? AND input_revision=?",(key,rid,rev)).fetchone()
        if bound is None or tuple(bound)!=(decision.preview_digest,decision.request_digest,decision.upper_units):
            raise contract.ContractError("confirmation_binding_changed")
        return original
    with _LOCK:
        _prune(int(time.time()))
        offered=_CACHE.get(decision.preview_digest)
    if (offered is None or offered.handle is not handle or offered.scope.research_id!=rid
            or offered.scope.input_revision!=rev or offered.operation_key!=key):
        raise contract.ContractError("preview_unavailable")
    return sender.run_once(app,handle,service,identity,rid,rev,offered.scope.research_version,key,
                           offered.prepared,offered.quote,decision,source=source,quote_proof=offered)



def require_offered(proof,handle,service,identity,rid,revision,prepared,quote,decision,*,operation_key=None):
    """Only this process's owner-bound live preview can authorize a quote."""
    with _LOCK:
        _prune(int(time.time()))
        if (type(proof) is not _Offered or _CACHE.get(decision.preview_digest) is not proof
                or proof.handle is not handle or proof.operation_key!=operation_key or service is not handle._binding.service
                or (proof.scope.research_id,proof.scope.input_revision,proof.scope.auth_generation)!=(
                    rid,revision,identity.generation)
                or proof.prepared is not prepared or proof.quote is not quote):
            raise contract.ContractError("live_quote_proof_required")
