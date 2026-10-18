"""Read-only Core facts and the fixed Main admission seam; facts grant nothing."""
from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sqlite3
import sys
import types
from typing import Literal

from .errors import ResearchError


@dataclass(frozen=True,slots=True)
class FormalResearchProfileFacts:
    contract: Literal['core-formal-profile-v1']
    auth_profile: Literal['auth-provision-v1']
    research_schema: Literal[14]
    financial_protocols: tuple[int,...]
    method_protocol: Literal[9]
    database_identity_verified: Literal[True]
    foreign_keys_verified: Literal[True]
    hooks_verified: Literal[True]
    checked_pid: int


@dataclass(frozen=True,slots=True)
class CapabilityFact:
    state: Literal['profile_verified','closed','unsupported','per_run_guard_required','controlled_fixture']
    reason: str


@dataclass(frozen=True,slots=True)
class ResearchRuntimeCapabilityFacts:
    contract: Literal['core-runtime-capabilities-v1']
    profile: FormalResearchProfileFacts
    basic_read_write: CapabilityFact
    source_history: CapabilityFact
    source_execute: CapabilityFact
    local_math: CapabilityFact
    native_planner: CapabilityFact


def _closed_profile():
    return ResearchError('SCHEMA_UNSUPPORTED',503,'正式研究存储当前无法完整核对；不会创建或迁移数据。')


def inspect_formal_profile(conn):
    """Caller owns the active native snapshot, hook installation and close.

    Full checks are initialization facts, never an HTTP/Main/funding lease.
    No ordinary database FD is opened, and no hook or transaction is replaced.
    """
    from .store import ResearchStore
    try:
        namespace=type(conn).__module__
        if namespace not in ('services.sqlite_utils','web.backend.services.sqlite_utils'):raise PermissionError()
        native=importlib.import_module(namespace)
        expected=Path(__file__).resolve().parents[1]/'services'/'sqlite_utils.py'
        if Path(native.__file__).resolve()!=expected or not Path(native.__file__).is_file() or Path(native.__file__).is_symlink() or type(conn) is not native.PrivateAuthConnection:raise PermissionError()
        if (not conn.in_transaction or conn.row_factory is not sqlite3.Row or conn.text_factory is not str
                or conn.isolation_level is not None or type(conn.execute) is not types.BuiltinMethodType
                or conn.execute.__self__ is not conn or getattr(type(conn),'execute') is not sqlite3.Connection.execute):raise PermissionError()
        # These hooks capture the installing PID; inherited connections fail
        # before metadata/domain scans and cannot certify a child lifespan.
        from .financial_guard import require_hook as require_financial_hook
        require_financial_hook(conn)
        family=namespace.rsplit('.',1)[0]
        paths=importlib.import_module(family+'.runtime_paths')
        auth=importlib.import_module(family+'.auth_store').AuthStore
        witness=conn._history_file
        if type(witness) is not paths.PrivateAuthFile or witness.path!=paths.private_auth_path():raise PermissionError()
        witness.check()
        identity=conn.private_storage_identity
        main=[row[2] for row in conn.execute('PRAGMA database_list') if row[1]=='main']
        if identity is None or main!=[str(witness.path)] or identity!=witness.file_identity:raise PermissionError()
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:raise PermissionError()
        if auth.check_offline_auth_metadata(conn)!='auth-provision-v1':raise PermissionError()
        auth.check_gate_policy(conn,initialize=False)
        if conn.execute("SELECT auth_registration_write_allowed('__profile_probe__','')").fetchone()[0]!=0:raise PermissionError()
        ResearchStore._check_v14(conn)
        if conn.execute('PRAGMA foreign_key_check').fetchone() is not None:raise PermissionError()
        witness.check()
        return FormalResearchProfileFacts('core-formal-profile-v1','auth-provision-v1',14,(7,8,9),9,True,True,True,os.getpid())
    except (ResearchError,PermissionError,ValueError,TypeError,AttributeError,RuntimeError,OSError,sqlite3.Error):
        raise _closed_profile() from None


def runtime_capability_facts(service):
    from .store import ResearchStore
    from .service import ResearchService
    try:
        if type(service) is not ResearchService or type(service.store) is not ResearchStore or not service.store._formal_mode():raise PermissionError()
    except (PermissionError,ResearchError,ValueError,TypeError,AttributeError,RuntimeError,OSError):
        raise _closed_profile() from None
    store=service.store
    if __package__=='web.backend.research':
        from ..services.sqlite_utils import connect_private_auth
        from ..services.auth_registration import install_hook as auth_hook
    else:
        from services.sqlite_utils import connect_private_auth
        from services.auth_registration import install_hook as auth_hook
    from .financial_guard import install_default_hook
    try:
        conn=connect_private_auth(store.path,readonly=True,expected_identity=store.storage_identity)
        try:
            install_default_hook(conn);auth_hook(conn)
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
            profile=inspect_formal_profile(conn)
        finally:conn.close()
    except (ResearchError,PermissionError,ValueError,TypeError,AttributeError,RuntimeError,OSError,sqlite3.Error):
        raise _closed_profile() from None
    planner=CapabilityFact('closed','FUNDING_CLOSED')
    from . import plan_native
    pair=plan_native.installation(store)
    if pair is not None:
        try:
            provision,resource=pair
            if type(provision) is not plan_native.NativePlanProvision or provision.authority.store is not store:raise PermissionError()
            provision.require();facts=provision.data()
            from .provider_schemas import digest
            if type(resource) is plan_native.ControlledNativeResource:
                expected_producer='core-controlled-native-v1';code_digest=plan_native._module_digest()
            else:
                module=plan_native._runtime_module()
                if type(resource) is not module.NativePlanResource:raise PermissionError()
                expected_producer='owned-native-plan-runtime-v1';code_digest=digest(Path(module.__file__).read_bytes())
            resource.require()
            if (resource.permit.provision is not provision or facts['mode']!='controlled_fixture'
                    or (resource.mode,resource.producer,resource.economic_binding,resource.credential_incarnation)
                    !=(facts['mode'],expected_producer,facts['economic_binding'],facts['credential_incarnation'])
                    or facts['runtime_digest']!=code_digest):raise PermissionError()
            with store.transaction() as conn:
                funding=conn.execute('SELECT * FROM research_plan_native_funding WHERE id=1').fetchone()
                if (not funding or funding['state']!='authorized' or funding['authority_digest']!=digest(provision.facts)
                        or any(funding[name]!=facts[name] for name in ('principal_id','generation','owner_gate_id','account_id','economic_binding','credential_incarnation','grant_epoch','runtime_digest'))):raise PermissionError()
                project=conn.execute('SELECT status FROM research_project_budgets WHERE funding_account_id=?',(funding['account_id'],)).fetchone()
                if (project is not None and project[0]!='active') or plan_native.financial.unresolved(conn,funding['account_id']):raise PermissionError()
            planner=CapabilityFact('controlled_fixture','CONTROLLED_RESOURCE_ONLY')
        except (ResearchError,PermissionError,ValueError,TypeError,AttributeError,KeyError,RuntimeError,OSError,sqlite3.Error):pass
    math=(CapabilityFact('per_run_guard_required','NOT_ATTESTED_UNTIL_OWNED_RUN') if sys.platform=='linux'
        else CapabilityFact('unsupported','PLATFORM_GUARD_UNAVAILABLE'))
    return ResearchRuntimeCapabilityFacts('core-runtime-capabilities-v1',profile,
        CapabilityFact('profile_verified','ACTOR_ACL_REQUIRED'),
        CapabilityFact('profile_verified','CURRENT_ACL_AND_STORED_SOURCE_REQUIRED'),
        CapabilityFact('closed','SUPERVISED_SOURCE_WORKER_UNBOUND'),math,planner)


def formal_request_required(app=None):
    """An actual canonical Main never falls back after environment downgrade."""
    expected=Path(__file__).resolve().parents[1]/'main.py'
    for name in ('main','web.backend.main'):
        module=sys.modules.get(name)
        if module is not None and getattr(module,'app',None) is app:
            file=getattr(module,'__file__',None)
            if file is not None and Path(file).resolve()==expected:return True
    return os.getenv('STRUCTURAL_ENV','dev').strip().lower()=='prod'


def require_formal_application(app,capability):
    """Only the fixed service owns Main bindings. No callback or facts input."""
    from fastapi import FastAPI
    if type(app) is not FastAPI or capability not in ('research_basic','source_history','source_execute'):
        raise ResearchError('FEATURE_UNAVAILABLE',503,'正式研究能力尚未就绪。')
    name=('web.backend.services' if __package__=='web.backend.research' else 'services')+'.formal_admission'
    try:
        module=importlib.import_module(name)
        path=Path(__file__).resolve().parents[1]/'services'/'formal_admission.py'
        function=module.require
        if (type(module) is not types.ModuleType or Path(module.__file__).resolve()!=path or not path.is_file() or Path(module.__file__).is_symlink()
                or type(function) is not types.FunctionType or function.__globals__ is not vars(module)
                or function.__module__!=name or Path(function.__code__.co_filename).resolve()!=path):raise PermissionError()
        # A filename or module DTO alone cannot turn an arbitrary callback into
        # the fixed implementation. Compile trusted source without executing it.
        source=path.read_bytes()
        if len(source)>65536:raise PermissionError()
        codes=[value for value in compile(source,function.__code__.co_filename,'exec',dont_inherit=True).co_consts
            if isinstance(value,types.CodeType) and value.co_name=='require']
        if len(codes)!=1 or codes[0]!=function.__code__:raise PermissionError()
        if function(app,capability) is not None:raise PermissionError()
    except Exception:
        raise ResearchError('FEATURE_UNAVAILABLE',503,'正式研究能力尚未就绪。') from None
