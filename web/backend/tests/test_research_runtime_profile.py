"""Actual native15 profile facts and closed fixed-Main seams, no execution."""
from contextlib import contextmanager,closing
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import ModuleType,SimpleNamespace
import json,os,sqlite3,sys
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services.auth_registration import bootstrap_private_runtime,install_hook as auth_hook
from services.auth_store import AuthStore
from services.sqlite_utils import connect_private_auth,PrivateAuthConnection
from research import ResearchStore,ResearchService
from research.financial_guard import install_default_hook
from research.errors import ResearchError
from research.runtime_profile import require_formal_application,formal_request_required
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack


@pytest.fixture
def current(roots):
    assert bootstrap_private_runtime()['research_schema']==15
    auth=AuthStore(roots/'auth.sqlite3')
    return ResearchStore(auth)


@contextmanager
def native_snapshot(store,*,hooks=True):
    conn=connect_private_auth(store.path,readonly=True,expected_identity=store.storage_identity)
    try:
        if hooks:install_default_hook(conn);auth_hook(conn)
        conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
        yield conn
    finally:conn.close()


def test_actual_native15_profile_facts_are_readonly_frozen_and_not_funding(current):
    with native_snapshot(current) as conn:
        image=conn.serialize();before=conn.total_changes
        facts=ResearchStore.inspect_formal_profile(conn)
        assert facts.auth_profile=='auth-provision-v1' and facts.research_schema==15
        assert facts.financial_protocols==(7,8,9) and facts.method_protocol==9 and facts.checked_pid==os.getpid()
        assert facts.database_identity_verified and facts.hooks_verified and facts.foreign_keys_verified
        with pytest.raises(FrozenInstanceError):facts.research_schema=13
        assert conn.total_changes==before==0 and conn.serialize()==image and conn.in_transaction
        assert not conn.execute('SELECT 1 FROM research_funding_accounts').fetchone()
    capabilities=ResearchService(current).runtime_capability_facts()
    assert capabilities.basic_read_write.state==capabilities.source_history.state=='profile_verified'
    assert capabilities.source_execute.state==capabilities.native_planner.state=='closed'
    assert capabilities.local_math.state==('per_run_guard_required' if sys.platform=='linux' else 'unsupported')


@pytest.mark.parametrize('kind',['dto','plain_sqlite','memory_native','no_txn','ended_txn','closed','missing_hooks','wrong_marker','row_callback','execute_callback','foreign_keys_off','foreign_key_violation'])
def test_profile_rejects_non_native_expired_or_incomplete_context(current,kind):
    conn=None
    try:
        if kind=='dto':conn=SimpleNamespace(in_transaction=True,private_storage_identity=current.storage_identity)
        elif kind=='plain_sqlite':conn=sqlite3.connect(current.path,isolation_level=None);conn.execute('BEGIN')
        elif kind=='memory_native':conn=sqlite3.connect(':memory:',isolation_level=None,factory=PrivateAuthConnection);conn.execute('BEGIN')
        else:
            conn=connect_private_auth(current.path,readonly=True,expected_identity=current.storage_identity)
            if kind!='missing_hooks':install_default_hook(conn);auth_hook(conn)
            conn.execute('PRAGMA foreign_keys=ON')
            if kind=='foreign_keys_off':conn.execute('PRAGMA foreign_keys=OFF')
            if kind=='foreign_key_violation':
                with closing(sqlite3.connect(current.path,isolation_level=None)) as corrupt:
                    corrupt.execute("INSERT INTO research_controls VALUES('00000000-0000-4000-8000-000000000001','missing-owner',1,1,1,1,'private','active','2026-10-18T00:00:00.000000Z','2026-10-18T00:00:00.000000Z')")
            if kind!='no_txn':conn.execute('BEGIN')
            if kind=='ended_txn':conn.rollback()
            elif kind=='closed':conn.close()
            elif kind=='wrong_marker':
                conn.close();conn=None
                with closing(sqlite3.connect(current.path,isolation_level=None)) as other:other.execute('UPDATE research_schema SET version=13')
                conn=connect_private_auth(current.path,readonly=True,expected_identity=current.storage_identity);install_default_hook(conn);auth_hook(conn)
                conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
            elif kind=='row_callback':conn.row_factory=lambda *_:None
            elif kind=='execute_callback':conn.execute=lambda *_:None
        with pytest.raises(ResearchError) as failed:ResearchStore.inspect_formal_profile(conn)
        assert failed.value.code=='SCHEMA_UNSUPPORTED' and failed.value.status==503
    finally:
        if isinstance(conn,sqlite3.Connection):
            if kind=='execute_callback' and 'execute' in conn.__dict__:del conn.execute
            conn.close()
            with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')


def test_profile_rejects_hooks_inherited_by_a_different_pid(current,monkeypatch):
    with native_snapshot(current) as conn:
        actual=os.getpid()
        monkeypatch.setattr(os,'getpid',lambda:actual+1)
        with pytest.raises(ResearchError):ResearchStore.inspect_formal_profile(conn)


def test_fixed_main_missing_and_unknown_app_reject_state_flags_and_callback_module(monkeypatch):
    from api import research
    app=FastAPI();app.include_router(research.router,prefix='/api')
    app.state.ready=True;app.state.formal_admission={'ready':True,'pid':os.getpid()}
    monkeypatch.setenv('STRUCTURAL_ENV','prod');monkeypatch.setenv('STRUCTURAL_RESEARCH_ENABLED','true')
    monkeypatch.setattr(research,'enabled',lambda:True)
    with TestClient(app) as client:
        result=client.get('/api/research')
        assert result.status_code==503 and result.json()['error']['code']=='FEATURE_UNAVAILABLE'
    with pytest.raises(ResearchError):require_formal_application(SimpleNamespace(state={'ready':True}),'research_basic')
    module=ModuleType('services.formal_admission')
    filename=str(Path(research.__file__).resolve().parents[1]/'services'/'formal_admission.py')
    module.__file__=filename
    exec(compile('def require(app,capability):\n    return None\n',filename,'exec'),module.__dict__)
    monkeypatch.setitem(sys.modules,'services.formal_admission',module)
    with pytest.raises(ResearchError):require_formal_application(app,'research_basic')


def test_canonical_main_request_stays_formal_after_environment_downgrade(monkeypatch):
    from api import research
    app=FastAPI();module=ModuleType('main');module.app=app;module.__file__=str(Path(research.__file__).resolve().parents[1]/'main.py')
    monkeypatch.setitem(sys.modules,'main',module);monkeypatch.setenv('STRUCTURAL_ENV','dev')
    assert formal_request_required(app) is True
    with pytest.raises(ResearchError):require_formal_application(app,'research_basic')


def test_formal_source_history_and_execution_do_not_accept_flag_or_store_only(current,monkeypatch):
    from research import source_integration
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('STRUCTURAL_RESEARCH_ENABLED','true');monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','true')
    monkeypatch.setattr(source_integration,'enabled',lambda:True)
    for capability in ('source_history','source_execute'):
        with pytest.raises(ResearchError):source_integration.require_enabled(store=current,capability=capability)


def test_capability_facts_require_actual_controlled_resource_and_notice_retirement(stack):
    from api import auth
    from .test_private_registration import link,verify
    from .test_research_paid_producers import identity
    from .test_research_funded_plan import provider
    from research import plan_native
    client,root,mail=stack
    assert verify(client,link(client,mail)).status_code==200
    store=ResearchStore(auth._store());service=ResearchService(store)
    with provider() as (server,calls):
        authority=provision=permit=resource=None
        try:
            authority=plan_native.create_controlled_fixture_authority(store,identity(client),server,approved_cap_units=41_000_000)
            provision=plan_native.issue_native_provision(store,authority);permit=plan_native.mint_runtime_permit(provision)
            resource=plan_native.open_controlled_fixture_resource(permit);plan_native.install_native_funding(store,provision,resource)
            facts=service.runtime_capability_facts()
            assert facts.native_planner.state=='controlled_fixture' and facts.native_planner.reason=='CONTROLLED_RESOURCE_ONLY'
            assert facts.basic_read_write.state=='profile_verified' and calls==[]
            permit.close()
            assert service.runtime_capability_facts().native_planner.state=='closed' and calls==[]
        finally:
            plan_native.retire_installation(store)
            for owned in (resource,permit,provision,authority):
                if owned is not None:owned.close()


def test_captured_private_api_never_uses_dev_enabled_override(stack,monkeypatch):
    from api import auth,research
    from .test_private_registration import link,verify
    client,root,mail=stack
    assert verify(client,link(client,mail)).status_code==200
    captured=auth._store();client.app.include_router(research.router,prefix='/api')
    monkeypatch.setattr(auth,'_store',lambda:captured)
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('STRUCTURAL_RESEARCH_ENABLED','true')
    monkeypatch.setattr(research,'enabled',lambda:True)
    response=client.get('/api/research')
    assert response.status_code==503 and response.json()['error']['code']=='FEATURE_UNAVAILABLE'
