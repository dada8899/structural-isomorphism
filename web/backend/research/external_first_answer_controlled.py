"""Owned v17 Main rehearsal issuer and loopback consumer, never a live issuer."""
from contextlib import closing,contextmanager
from dataclasses import dataclass
from http.client import HTTPConnection,HTTPException
from http.server import ThreadingHTTPServer
import os
import sqlite3
import threading
import time
from uuid import uuid4

from .errors import ResearchError
from .external_first_answer_catalog import project_closed_preview,read_main_recovery
from .external_first_answer_contract import (
    CAP_UNITS,MAX_RESULT_BYTES,MIN_RISK_MARGIN_UNITS,PROJECT,PURPOSE,ContractError,QuoteBinding,prepare_closed_preview,
)
from .external_first_answer_file_writer import CandidateFileWriter,_TempLedgerProof,_TOKEN,_identity
from .external_first_answer_seam import _authorized_saved_revision
from .external_first_answer_state import TABLE

_ACTIVE={}
_LOCK=threading.RLock()


def _formal():
    if __package__=="web.backend.research":
        from ..services import formal_admission
    else:
        from services import formal_admission
    return formal_admission


@dataclass
class _Runtime:
    app: object
    binding: object
    proof: _TempLedgerProof
    server: ThreadingHTTPServer
    socket_identity: tuple
    balance: int
    previews: dict
    active: bool=True


def _socket_identity(server):
    entry=os.fstat(server.socket.fileno())
    if server.server_address[0]!="127.0.0.1" or server.socket.getsockname()!=server.server_address:
        raise ContractError("owned_loopback_required")
    return entry.st_dev,entry.st_ino


@contextmanager
def controlled_runtime(app,proof,server,*,balance):
    """Explicit scoped rehearsal enrollment: exact active Main and temp inode."""
    formal=_formal()
    formal.require(app,"research_basic")
    binding=formal._STATE[id(app)]
    if (binding.facts.profile.research_schema!=17 or type(proof) is not _TempLedgerProof or proof.token is not _TOKEN
            or proof.path!=binding.service.store.path or _identity(proof.path)!=proof.identity
            or type(server) is not ThreadingHTTPServer or type(balance) is not int or balance<0):
        raise ContractError("controlled_runtime_unavailable")
    runtime=_Runtime(app,binding,proof,server,_socket_identity(server),balance,{})
    with _LOCK:
        if id(app) in _ACTIVE:raise ContractError("controlled_runtime_conflict")
        _ACTIVE[id(app)]=runtime
    try:
        yield
    finally:
        with _LOCK:
            runtime.active=False
            _ACTIVE.pop(id(app),None)
            runtime.previews.clear()


def current(app,service):
    with _LOCK:
        runtime=_ACTIVE.get(id(app))
    if runtime is None or not runtime.active:
        return None
    formal=_formal()
    formal.require(app,"research_basic")
    if formal._STATE.get(id(app)) is not runtime.binding or service.store.path!=runtime.proof.path:
        return None
    return runtime


def _quote(conn,scope,now):
    row=conn.execute("""SELECT f.account_id,f.economic_binding,a.funding_epoch
      FROM research_plan_native_funding f JOIN research_funding_accounts a ON a.id=f.account_id
      WHERE f.id=1 AND f.state='authorized' AND f.principal_id=? AND f.generation=?
        AND f.approved_cap_units=? AND f.risk_margin_units=? AND a.binding_id=f.economic_binding
        AND a.currency='CNY' AND a.scale=6 AND a.provider='deepseek'""",
        (scope.principal_id,scope.auth_generation,CAP_UNITS,MIN_RISK_MARGIN_UNITS)).fetchone()
    if not row:raise ContractError("shared_funding_closed")
    return QuoteBinding(purpose=PURPOSE,project_ref=PROJECT,provider="deepseek",model="deepseek-flash",
       account_id=row[0],economic_binding=row[1],funding_epoch=row[2],quote_id=str(uuid4()),
       price_basis_digest="a"*64,currency="CNY",scale=6,upper_units=5000,issued_at=now,valid_until=now+45)


def preview(runtime,service,identity,rid,rev,expected):
    now=int(time.time())
    with _authorized_saved_revision(service,identity,rid,rev,expected.research_version) as (conn,scope,raw):
        if scope.problem_digest!=expected.problem_digest:
            raise ContractError("revision_binding_changed")
        quote=_quote(conn,scope,now)
        closed=prepare_closed_preview(scope,raw,quote,now=now)
        with _LOCK:
            if not runtime.active:raise ContractError("controlled_runtime_unavailable")
            runtime.previews={key:value for key,value in runtime.previews.items() if value[0].valid_until>now}
            if len(runtime.previews)>=32:raise ContractError("preview_capacity")
            runtime.previews[closed.preview_digest]=(quote,scope,closed)
        return project_closed_preview(scope,raw,quote,now=now)|{"may_send":True}


def _loopback(runtime,service,raw):
    try:
        if current(runtime.app,service) is not runtime or _socket_identity(runtime.server)!=runtime.socket_identity:
            return None
        with closing(HTTPConnection("127.0.0.1",runtime.server.server_port,timeout=3)) as conn:
            conn.request("POST","/fixture-external-first-answer",body=raw,headers={"Content-Type":"application/json"})
            with conn.getresponse() as response:
                body=response.read(MAX_RESULT_BYTES+1)
                return body if response.status==200 and 0<len(body)<=MAX_RESULT_BYTES else None
    except (OSError,HTTPException,ContractError,RuntimeError):
        return None


def confirm(runtime,service,identity,rid,rev,key,decision):
    try:
        # A repeated key never creates another operation, even when the
        # original response was lost or the quote is now expired.
        recovered=read_main_recovery(service,identity,rid,rev,key)
        if recovered is None:
            raise ContractError("controlled_runtime_unavailable")
        with service.store.transaction() as conn:
            original=conn.execute("SELECT preview_digest,request_digest,upper_units FROM "+TABLE+
                " WHERE id=? AND research_id=? AND input_revision=?",(key,rid,rev)).fetchone()
        if original is None or tuple(original)!=(decision.preview_digest,decision.request_digest,decision.upper_units):
            raise ContractError("confirmation_binding_changed")
        return recovered
    except ResearchError as error:
        if error.code!="NOT_FOUND":raise
    with _LOCK:
        selected=runtime.previews.get(decision.preview_digest)
    if selected is None:
        raise ContractError("preview_unavailable")
    quote,scope,closed=selected
    now=int(time.time())
    with closing(sqlite3.connect(runtime.proof.path.as_uri()+"?mode=rw",uri=True,isolation_level=None,timeout=2)) as conn:
        from .financial_guard import install_default_hook
        install_default_hook(conn)
        writer=CandidateFileWriter(conn,runtime.proof)
        with _authorized_saved_revision(service,identity,rid,rev,scope.research_version) as (_,actual,raw):
            if scope!=actual or not runtime.active:raise ContractError("revision_or_owner_changed")
            grant=writer.grant(scope,raw,closed,quote,decision,balance=runtime.balance,now=now,balance_until=now+30)
            writer.confirm(key,grant,scope)
            # An exception leaves the original durable stage. A write error
            # is not enough to assert not_sent; GET remains read-only.
            writer.reserve(key,grant,scope,now=now)
            outbound=writer.consume(key,grant,scope,now=now)
        returned=_loopback(runtime,service,outbound)
        if returned is None:
            writer.finish(key,grant,scope)
        else:
            try:
                with _authorized_saved_revision(service,identity,rid,rev,scope.research_version) as (_,actual,_):
                    if actual!=scope or not runtime.active:raise ContractError("revision_or_owner_changed")
                    writer.finish(key,grant,scope,candidate=returned)
            except (ContractError,ResearchError,sqlite3.Error):
                writer.finish(key,grant,scope)
    return read_main_recovery(service,identity,rid,rev,key)
