"""Separate external-purpose startup attestation and loader capability.

There is no installed production policy in this build. The only executable
enrollment is a marked-temporary rehearsal; its handles can never enter a
live sender. This module imports neither a provider adapter nor cryptography
on the default-closed production path.
"""
from contextlib import contextmanager
import os
import sqlite3
import sys
import threading
import types

from . import formal_admission

if __package__ == "web.backend.services":
    from ..research.errors import ResearchError
    from ..research.external_first_answer_contract import CAP_UNITS, ContractError
else:
    from research.errors import ResearchError
    from research.external_first_answer_contract import CAP_UNITS, ContractError

_CREDENTIAL_ID="structural-external-first-answer-deepseek-key"
_ENTRY="run-formal-main-external-first-answer-v1"
_FACTORY=object()
_ACTIVE={}
_LOCK=threading.RLock()


def _attest_main(app,expected):
    """Read actual admitted v17 Main and the existing, not newly minted ledger."""
    from importlib import import_module
    family="web.backend.research" if __package__=="web.backend.services" else "research"
    schema=import_module(family+".external_first_answer_issuer_contract")
    if type(expected) is not schema.StartupBinding:
        raise ContractError("external_startup_binding_required")
    try:
        formal_admission.require(app,"research_basic")
        binding=formal_admission._STATE.get(id(app))
        if (type(binding) is not formal_admission._Binding or binding.app is not app or binding.pid!=os.getpid()
                or binding.facts.profile.research_schema!=17 or not binding.service.store._formal_mode()):
            raise ValueError()
        store=binding.service.store
        if store.storage_identity!=(expected.database_dev,expected.database_ino):
            raise ValueError()
        with store.transaction() as conn:
            row=conn.execute("""SELECT f.account_id,f.economic_binding,f.credential_incarnation,f.principal_id,
               f.generation,f.owner_gate_id,f.approved_cap_units,f.risk_margin_units,
               a.funding_epoch,p.epoch,p.gate_id
               FROM research_plan_native_funding f JOIN research_funding_accounts a ON a.id=f.account_id
               JOIN research_principals p ON p.id=f.principal_id
               JOIN auth_users u ON u.email=p.normalized_email
               WHERE f.id=1 AND f.state='authorized' AND a.binding_id=f.economic_binding
                 AND a.mode='live' AND a.status='unverified' AND a.cap=0
                 AND a.currency='CNY' AND a.scale=6 AND a.provider='deepseek'
                 AND p.status='active' AND u.lifecycle='active'
                 AND p.session_generation=f.generation AND u.session_generation=f.generation""").fetchone()
            from_module=import_module(family+".external_first_answer_contract")
            if row is None or tuple(row)!=(
                    expected.account_id,expected.economic_binding,expected.credential_incarnation,expected.owner_principal,
                    expected.owner_generation,expected.owner_gate_id,CAP_UNITS,from_module.MIN_RISK_MARGIN_UNITS,
                    expected.funding_epoch,expected.owner_epoch,expected.owner_gate_id):
                raise ValueError()
        if formal_admission._STATE.get(id(app)) is not binding:
            raise ValueError()
        return binding
    except (ValueError,RuntimeError,PermissionError,OSError,AttributeError,ResearchError,sqlite3.Error):
        raise ContractError("external_main_attestation_rejected") from None


class _Sealed:
    __slots__=()

    def __setattr__(self,name,value):
        raise TypeError("external startup handle immutable")

    def __reduce__(self):
        raise TypeError("external startup handle cannot be serialized")


class _LoadPermit(_Sealed):
    __slots__=("_binding","_loader","_entry_witness","_owner_thread","_pid","_active","_used")

    def __init__(self,binding,loader,entry_witness,*,factory):
        if factory is not _FACTORY:
            raise PermissionError("external loader factory required")
        for name,value in (("_binding",binding),("_loader",loader),("_entry_witness",entry_witness),
                ("_owner_thread",threading.get_ident()),("_pid",os.getpid()),("_active",True),("_used",False)):
            object.__setattr__(self,name,value)

    def claim(self,entry_witness,*,entry,credential_id):
        caller=sys._getframe(1)
        try:
            if (not self._active or self._used or self._pid!=os.getpid() or self._owner_thread!=threading.get_ident()
                    or caller.f_code is not self._loader.__code__ or caller.f_globals is not self._loader.__globals__
                    or entry_witness is not self._entry_witness or (entry,credential_id)!=(_ENTRY,_CREDENTIAL_ID)
                    or formal_admission._STATE.get(id(self._binding.app)) is not self._binding):
                raise ContractError("external_loader_claim_rejected")
            formal_admission.require(self._binding.app,"research_basic")
            object.__setattr__(self,"_used",True)
        finally:del caller


class RehearsalCredential(_Sealed):
    """An inert loader result. Accepts no key or payload."""
    __slots__=("_active",)

    def __init__(self):
        object.__setattr__(self,"_active",True)

    def retire(self):
        object.__setattr__(self,"_active",False)


class ExternalSenderHandle(_Sealed):
    """Lifetime interface for a sender; this build can issue only fixtures."""
    __slots__=("_binding","_resource","_expected","_pid","_token","_mode")

    def __init__(self,binding,resource,expected,*,factory):
        if factory is not _FACTORY or type(resource) is not RehearsalCredential:
            raise PermissionError("external sender handle factory required")
        for name,value in (("_binding",binding),("_resource",resource),("_expected",expected),("_pid",os.getpid()),
                           ("_token",object()),("_mode","fixture")):
            object.__setattr__(self,name,value)

    def __repr__(self):
        return "<sealed external sender handle>"

    def require(self,app,*,live=True):
        with _LOCK:
            if (_ACTIVE.get(self._token) is not self or self._pid!=os.getpid() or self._binding.app is not app
                    or formal_admission._STATE.get(id(app)) is not self._binding or not self._resource._active):
                raise ContractError("external_sender_handle_retired")
        formal_admission.require(app,"research_basic")
        if live is not False or self._mode!="fixture":
            raise ContractError("live_external_issuer_unbound")
        if _attest_main(app,self._expected) is not self._binding:
            raise ContractError("external_main_attestation_rejected")
        return None


@contextmanager
def rehearse_external_loader(app,receipt_directory,raw,expected,public_key,loader,*,now):
    """Synthetic callback, attested temp launch, never registered for Main."""
    if type(loader) is not types.FunctionType:
        raise ContractError("fixture_loader_required")
    from importlib import import_module
    family="web.backend.research" if __package__=="web.backend.services" else "research"
    schema=import_module(family+".external_first_answer_issuer_contract")
    binding=_attest_main(app,expected)
    # The same temp-only, exact signed, durable challenge is consumed before
    # giving even the rehearsal loader an opportunity to claim.
    schema.consume_isolated_startup_once(receipt_directory,raw,expected,public_key,now=now)
    witness=object()
    permit=_LoadPermit(binding,loader,witness,factory=_FACTORY)
    resource=handle=None
    try:
        resource=loader(permit,witness)
        if not permit._used or type(resource) is not RehearsalCredential or not resource._active:
            raise ContractError("external_loader_receipt_rejected")
        _attest_main(app,expected)
        handle=ExternalSenderHandle(binding,resource,expected,factory=_FACTORY)
        with _LOCK:
            _ACTIVE[handle._token]=handle
        yield handle
    finally:
        object.__setattr__(permit,"_active",False)
        if handle is not None:
            with _LOCK:_ACTIVE.pop(handle._token,None)
        if type(resource) is RehearsalCredential:
            resource.retire()


def activate_live_external_issuer(app):
    """Reserved Main entry. No key, receipt-path or callback input accepted."""
    formal_admission.require(app,"research_basic")
    # No target-attested pinned reviewer key, protected receipt sink or
    # dedicated encrypted credential entry has been installed.
    raise ContractError("live_external_issuer_unbound")
