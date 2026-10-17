"""Actual v7 migrations/closed registration; synthetic money, no network."""
from datetime import datetime,timezone
import multiprocessing
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

import pytest

from .test_research_persistence import stack,create
from web.backend.tests.research_process_fixture import _crash_v7
from .test_research_paid_schema import snapshot,rows,bounded_rows,insert_cost,_USAGE
from .test_research_paid_producers import identity
from .test_research_financial_admission_schemas import financial_sample
from api import auth
from research import ResearchStore
from research.authorization import AuthorizationGate
from research.errors import ResearchError
from research.financial_guard import (V7_TABLES,V7_GUARDS,OfflineProjectRegistration,register_closed_project,
    install_default_hook,require_hook,FINANCIAL_SCHEMA_VERSION)
from research.paid_approval import OfflineFundingResolver,request_codec_digest
from research.paid_control import mint_trusted_cost_authority
from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money,canonical,digest


@pytest.fixture
def v6_data(stack,monkeypatch):
    client,path=stack
    with monkeypatch.context() as boundary:
        boundary.setattr(ResearchStore,'_migrate_v7',lambda self:None)
        rid=create(client);store=ResearchStore(auth._store())
    with store.transaction(write=True) as conn:
        pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
        ids=bounded_rows(conn,(client,path,store,rid,pid))
        insert_cost(conn,ids,_USAGE)
        conn.execute("UPDATE research_reservations SET status='UPPER_BOOKED',version=2 WHERE id=?",(ids[2],))
        conn.execute('UPDATE research_funding_accounts SET settled=7,upper_booked=2 WHERE id=?',(ids[0],))
    return client,path,store,rid,pid


@pytest.fixture
def registry_inputs(stack):
    client,path=stack;rid=create(client);store=ResearchStore(auth._store());actor=identity(client)
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    money=lambda n:Money(currency='CNY',scale=6,amount_units=n)
    fid,binding,sid=(str(uuid4()) for _ in range(3));now=int(time.time())
    quote=UsageUpperQuote(revision=str(uuid4()),context_bound=1048576,peak_input_miss_units_per_million=1,
        peak_output_units_per_million=2,local_guard=1,price_document_digest='a'*64,model_document_digest='b'*64,
        completion_bound_basis_digest='c'*64,final_request_code_digest=request_codec_digest(),valid_until=now+60)
    basis=BudgetBasisSnapshot(id=sid,account_id=fid,provider_binding_id=binding,funding_epoch=1,initial_prepaid=money(1000),
        other_use_margin=money(0),cap=money(1000),settled_actual=money(0),upper_booked=money(0),held=money(0),
        available_after_observed_consumption=money(1000),price_revision=quote.revision,valid_until=now+3600)
    stamp=lambda value:datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,cap,initial_prepaid_units,other_use_margin_units,status,snapshot_id) VALUES(?,?,'live','deepseek','CNY',1000,1000,0,'active',?)",(fid,binding,sid))
        conn.execute("INSERT INTO research_balance_snapshots(id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off,basis_evidence_digest) VALUES(?,?,1000,0,0,?,?,1,1,1,?)",(sid,fid,stamp(now),stamp(now+3600),digest(canonical(basis.model_dump()))))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,?,'bounded_usage_upper_v2',?,?)",(quote.revision,fid,stamp(now+60),canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    resolver=OfflineFundingResolver(principal_id=pid,quote=quote,basis=basis,approved_upper=money(3))
    try:yield client,path,store,pid,actor,resolver
    finally:resolver.close()


def source(data,cap=10):
    _,_,store,pid,actor,resolver=data
    return OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=cap),authorization_ref=str(uuid4()))


def test_empty_default_and_nonempty_upgrade_keep_all_old_financial_facts(v6_data):
    _,path,_,_,_=v6_data;before=rows(path)
    locks={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==7
        for name,(columns,values) in before.items():
            if name=='research_schema':continue
            assert [tuple(row) for row in conn.execute('SELECT '+','.join('"'+c+'"' for c in columns)+' FROM '+name+' ORDER BY rowid')]==values
        for name in ('research_project_budgets','research_financial_admissions'):assert conn.execute('SELECT count(*) FROM '+name).fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert locks=={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    ResearchStore(auth._store())


FAULT_SQL=(*V7_TABLES,*V7_GUARDS,'UPDATE research_schema SET version=7 WHERE id=1')
@pytest.mark.parametrize('position',range(len(FAULT_SQL)+1))
def test_every_v7_dml_or_commit_failure_rolls_back_exact_v6(v6_data,monkeypatch,position):
    _,path,store,_,_=v6_data;before=snapshot(path);connect=sqlite3.connect;hit=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if position<len(FAULT_SQL) and sql==FAULT_SQL[position]:hit.append(True);raise sqlite3.OperationalError('owned v7 migration fault')
            return super().execute(sql,*args,**kwargs)
        def commit(self):
            if position==len(FAULT_SQL):hit.append(True);raise sqlite3.OperationalError('owned v7 commit fault')
            return super().commit()
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,factory=Fault,**k))
        with pytest.raises(sqlite3.OperationalError):store._migrate_v7()
    assert hit and snapshot(path)==before
    ResearchStore(auth._store())




@pytest.mark.parametrize('cut',['table','guard','marker','before_commit','after_commit'])
def test_process_death_reopens_complete_v6_or_v7_without_money_or_lock_drift(v6_data,cut):
    _,path,_,_,_=v6_data;before=snapshot(path)
    inodes={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    process=multiprocessing.get_context('spawn').Process(target=_crash_v7,args=(str(path),cut))
    process.start()
    try:process.join(15);assert not process.is_alive() and process.exitcode==(62 if cut=='after_commit' else 61)
    finally:
        if process.is_alive():process.terminate();process.join(3)
        process.close()
    if cut!='after_commit':assert snapshot(path)==before
    ResearchStore(auth._store())
    assert inodes=={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    after=rows(path)
    for name,values in before[1].items():
        if name!='research_schema':assert after[name]==values


@pytest.mark.parametrize('change',['partial-table','partial-guard','unknown-old-aux'])
def test_v6_partial_or_unknown_objects_are_never_silently_repaired(v6_data,change):
    _,path,store,_,_=v6_data
    with store.transaction(write=True) as conn:
        if change=='partial-table':conn.execute(V7_TABLES[0])
        elif change=='partial-guard':conn.execute("CREATE TRIGGER research_project_money_control BEFORE UPDATE ON research_funding_accounts BEGIN SELECT 1; END")
        else:conn.execute('CREATE INDEX unexpected_v6_financial_idx ON research_dispatch_permits(dispatch_id)')
    before=snapshot(path)
    with pytest.raises(ResearchError):ResearchStore(auth._store())
    assert snapshot(path)==before


@pytest.mark.parametrize('change',['missing-table','missing-guard','changed-guard','unknown-new-aux','unknown-old-aux','unknown-version'])
def test_v7_reopen_rejects_damage_without_rebuilding_it(registry_inputs,change):
    _,path,store,_,_,_=registry_inputs
    with store.transaction(write=True) as conn:
        if change=='missing-table':conn.execute('DROP TABLE research_financial_admissions')
        elif change=='unknown-new-aux':conn.execute('CREATE INDEX unexpected_financial_idx ON research_financial_admissions(dispatch_id)')
        elif change=='unknown-old-aux':conn.execute('CREATE INDEX unexpected_current_idx ON research_dispatch_permits(dispatch_id)')
        elif change=='unknown-version':conn.execute('UPDATE research_schema SET version=8')
        else:
            conn.execute('DROP TRIGGER research_admission_insert_control')
            if change=='changed-guard':conn.execute('CREATE TRIGGER research_admission_insert_control BEFORE INSERT ON research_financial_admissions BEGIN SELECT 1; END')
    before=snapshot(path)
    with pytest.raises(ResearchError):ResearchStore(auth._store())
    assert snapshot(path)==before


@pytest.mark.parametrize('cap',[5,2000])
def test_real_offline_source_can_only_register_closed_separate_project_cap(registry_inputs,cap):
    _,_,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs,cap)
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            initial=tuple(conn.execute('SELECT cap,initial_prepaid_units,settled,held,upper_booked FROM research_funding_accounts').fetchone())
            result=register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
            assert result.status=='closed' and result.authorized_cap==cap
            assert register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)==result
            assert tuple(conn.execute('SELECT cap,initial_prepaid_units,settled,held,upper_booked FROM research_funding_accounts').fetchone())==initial
            assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==0
            for obj in (True,{},result):
                with pytest.raises(PermissionError):mint_trusted_cost_authority(conn,observation=obj)
            assert conn.execute("SELECT research_financial_write_allowed('money','')").fetchone()[0]==0
    finally:dependency.close()


@pytest.mark.parametrize('kind',['dto','no-source','wrong-lease','closed-source','wrong-pid'])
def test_registration_requires_canonical_live_scope_and_lease(registry_inputs,kind):
    _,_,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            selected=dependency
            if kind=='dto':selected={}
            elif kind=='no-source':selected=None
            elif kind=='closed-source':dependency.close()
            elif kind=='wrong-pid':object.__setattr__(dependency,'_pid',-1)
            with pytest.raises(PermissionError):register_closed_project(conn,store=store,identity=actor,lease=True if kind=='wrong-lease' else lease,source=selected)
            assert conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==0
    finally:dependency.close()


def test_ordinary_sql_missing_hook_and_existing_closed_row_never_grant_financial_writes(registry_inputs):
    _,path,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            row=register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
        values=row.model_dump();columns=','.join(values)
        with store.transaction(write=True) as conn:
            for sql in ["UPDATE research_project_budgets SET status='active',version=2",'DELETE FROM research_project_budgets',
                    "UPDATE research_funding_accounts SET held=held+1",'INSERT OR REPLACE INTO research_project_budgets('+columns+') VALUES('+','.join('?' for _ in values)+')']:
                with pytest.raises(sqlite3.IntegrityError):conn.execute(sql,tuple(values.values()) if sql.startswith('INSERT') else ())
            assert conn.execute("SELECT research_financial_write_allowed('admit','')").fetchone()[0]==0
        with sqlite3.connect(path) as raw:
            with pytest.raises(sqlite3.OperationalError):raw.execute("UPDATE research_project_budgets SET status='active',version=2")
            with pytest.raises(ResearchError):require_hook(raw)
        with store.auth_store._connection() as conn:require_hook(conn)
    finally:dependency.close()


@pytest.mark.parametrize('ending',['commit','rollback','implicit'])
def test_ended_scope_never_revives_registration_permission(registry_inputs,ending):
    _,_,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            conn.execute('CREATE TEMP TABLE owned_scope_probe(id INTEGER PRIMARY KEY)')
            conn.execute('INSERT INTO owned_scope_probe VALUES(1)')
            if ending=='implicit':
                with pytest.raises(sqlite3.IntegrityError):conn.execute('INSERT OR ROLLBACK INTO owned_scope_probe VALUES(1)')
            else:getattr(conn,ending)()
            conn.execute('BEGIN IMMEDIATE')
            with pytest.raises(PermissionError):register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
            assert conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==0
    finally:dependency.close()


def test_data_shape_and_raw_sql_cannot_insert_an_admission(registry_inputs,financial_sample):
    _,path,store,_,_,_=registry_inputs
    from research.financial_admission_schemas import validate_snapshot_json
    raw=canonical(financial_sample);assert validate_snapshot_json(raw)
    values=(str(uuid4()),1,str(uuid4()),str(uuid4()),str(uuid4()),str(uuid4()),
        'financial-admission-v1','owned-budget-offline-v1','bounded_usage_upper_v2','offline_probe',raw.decode(),digest(raw),'2026-10-17T00:00:00.000000Z')
    sql='INSERT INTO research_financial_admissions VALUES('+','.join('?' for _ in values)+')'
    with store.transaction(write=True) as conn:
        with pytest.raises(sqlite3.IntegrityError,match='financial admission unavailable'):conn.execute(sql,values)
        assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==0
        with pytest.raises(PermissionError):mint_trusted_cost_authority(conn,observation=validate_snapshot_json(raw))
    with sqlite3.connect(path) as conn:
        with pytest.raises(sqlite3.OperationalError):conn.execute(sql,values)


def test_expired_lease_readonly_connection_and_other_db_cannot_register(registry_inputs,tmp_path):
    _,path,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with AuthorizationGate(store).owner_gate(pid) as expired:pass
        with store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):register_closed_project(conn,store=store,identity=actor,lease=expired,source=dependency)
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction() as conn:
            with pytest.raises(PermissionError):register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
        target=tmp_path/'alternate'/'auth.sqlite3';target.parent.mkdir()
        with sqlite3.connect(path) as original,sqlite3.connect(target) as other:original.backup(other)
        other_store=ResearchStore(type(store.auth_store)(target))
        with other_store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):register_closed_project(conn,store=other_store,identity=actor,lease=True,source=dependency)
    finally:dependency.close()


def test_closed_registry_copy_cannot_be_rebound_to_another_database(registry_inputs,tmp_path):
    _,path,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
        target=tmp_path/'copy'/'auth.sqlite3';target.parent.mkdir()
        with sqlite3.connect(path) as original,sqlite3.connect(target) as other:original.backup(other)
        with pytest.raises(ResearchError,match='SCHEMA_UNSUPPORTED'):ResearchStore(type(store.auth_store)(target))
    finally:dependency.close()


def test_actual_insert_failure_rolls_back_and_does_not_leave_a_write_permit(registry_inputs,monkeypatch):
    _,_,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs);connect=sqlite3.connect;hits=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if sql.startswith('INSERT INTO research_project_budgets('):hits.append(True);raise sqlite3.OperationalError('owned closed registration fault')
            return result
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease:
            with monkeypatch.context() as patch:
                patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,factory=Fault,**k))
                with pytest.raises(ResearchError):
                    with store.transaction(write=True) as conn:register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
            with store.transaction(write=True) as conn:
                assert hits and conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==0
                assert conn.execute("SELECT research_financial_write_allowed('register-project','{}')").fetchone()[0]==0
                assert register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency).status=='closed'
    finally:dependency.close()


def test_identity_shaped_object_and_mutable_configuration_cannot_register(registry_inputs):
    _,_,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    class PretendIdentity:
        def __eq__(self,other):return True
        def __getattr__(self,name):return getattr(actor,name)
    try:
        with pytest.raises(TypeError):dependency._cap=Money(currency='CNY',scale=6,amount_units=1)
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):register_closed_project(conn,store=store,identity=PretendIdentity(),lease=lease,source=dependency)
            assert conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==0
    finally:dependency.close()


def test_isolated_earlier_profile_keeps_its_schema_but_never_gets_v7_capability(stack,monkeypatch):
    client,_=stack
    with monkeypatch.context() as profile:
        profile.setattr(ResearchStore,'_migrate_v5',lambda self:None)
        profile.setattr(ResearchStore,'_migrate_v6',lambda self:None)
        create(client);store=ResearchStore(auth._store())
    with store.transaction(write=True) as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==4
        with pytest.raises(PermissionError):mint_trusted_cost_authority(conn,observation={})
    with pytest.raises(ResearchError):store._migrate_v7()


@pytest.mark.parametrize('kind,name',[
    ('table','research_idempotency'),('table','research_revisions'),('table','research_controls'),
    ('table','research_principals'),('table','research_attempts'),('table','research_task_events'),
    ('table','research_step_outputs'),('table','research_billing_receipts'),
    ('trigger','research_revision_no_update'),('trigger','research_principal_gate_required'),
    ('trigger','research_billing_receipts_immutable'),('index','research_owner_idx'),
    ('index','research_one_active_task'),('table','research_source_approvals'),('table','research_evidence_objects')])
def test_missing_required_base_object_rejects_reopen_and_closed_registry_without_repair(registry_inputs,kind,name):
    _,path,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        # Hold the real lease before damaging even its principal lookup table.
        with AuthorizationGate(store).owner_gate(pid) as lease:
            with sqlite3.connect(path) as raw:raw.execute('DROP '+kind.upper()+' '+name)
            before=snapshot(path)
            with pytest.raises(ResearchError) as caught:ResearchStore(auth._store())
            assert caught.value.code=='SCHEMA_UNSUPPORTED' and snapshot(path)==before
            with store.transaction(write=True) as conn:
                with pytest.raises(ResearchError) as caught:register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
                assert caught.value.code=='SCHEMA_UNSUPPORTED'
            assert snapshot(path)==before
    finally:dependency.close()


@pytest.mark.parametrize('change',['idempotency-ddl','revision-guard-ddl','marker-table','marker-row','marker-column'])
def test_required_base_drift_and_lost_marker_fail_closed_without_any_rebuild(registry_inputs,change):
    from research.store import SCHEMA
    _,path,_,_,_,_=registry_inputs
    with sqlite3.connect(path) as conn:
        if change=='idempotency-ddl':
            conn.execute('DROP TABLE research_idempotency')
            ddl=next(sql for sql in SCHEMA if sql.startswith('CREATE TABLE IF NOT EXISTS research_idempotency'))
            conn.execute(ddl.replace('PRIMARY KEY(principal_id, operation, scope_key, key_digest)','PRIMARY KEY(principal_id, operation, key_digest)'))
        elif change=='revision-guard-ddl':
            conn.execute('DROP TRIGGER research_revision_no_update')
            conn.execute('CREATE TRIGGER research_revision_no_update BEFORE UPDATE ON research_revisions BEGIN SELECT 1; END')
        elif change=='marker-table':conn.execute('DROP TABLE research_schema')
        elif change=='marker-row':conn.execute('DELETE FROM research_schema')
        else:conn.execute('ALTER TABLE research_schema RENAME COLUMN version TO revision')
    before=snapshot(path)
    with pytest.raises(ResearchError) as caught:ResearchStore(auth._store())
    assert caught.value.code=='SCHEMA_UNSUPPORTED' and snapshot(path)==before


def test_missing_revision_guard_is_not_accepted_for_registration_or_late_store_failure(registry_inputs):
    from .test_research_persistence import post,problem
    client,path,store,pid,actor,_=registry_inputs;dependency=source(registry_inputs)
    try:
        with store.transaction(write=True) as conn:
            with pytest.raises(sqlite3.IntegrityError):conn.execute("UPDATE research_revisions SET digest=?",('f'*64,))
            conn.execute('DROP TRIGGER research_revision_no_update')
        before=snapshot(path)
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            with pytest.raises(ResearchError):register_closed_project(conn,store=store,identity=actor,lease=lease,source=dependency)
        response=post(client,'/api/research',{'problem':problem()},'reject-damaged-guard')
        assert response.status_code==503 and response.json()['error']['code']=='SCHEMA_UNSUPPORTED'
        assert snapshot(path)==before
    finally:dependency.close()


@pytest.mark.parametrize('kind,name',[
    ('table','research_idempotency'),('table','research_revisions'),('table','research_controls'),
    ('table','research_attempts'),('table','research_step_outputs'),
    ('trigger','research_revision_no_update'),('trigger','research_principal_gate_required'),
    ('trigger','research_billing_receipts_immutable'),('index','research_owner_idx'),
    ('table','research_source_approvals')])
def test_v6_constructor_preflight_rejects_missing_objects_without_executing_installation(v6_data,monkeypatch,kind,name):
    _,path,store,_,_=v6_data
    with sqlite3.connect(path) as raw:raw.execute('DROP '+kind.upper()+' '+name)
    before=snapshot(path);connect=sqlite3.connect;writes=[]
    class Observe(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql.lstrip().upper().startswith(('CREATE ','ALTER ','DROP ','INSERT ','UPDATE ','DELETE ')):writes.append(sql)
            return super().execute(sql,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Observe,**k))
        with pytest.raises(ResearchError) as caught:ResearchStore(store.auth_store)
        assert caught.value.code=='SCHEMA_UNSUPPORTED'
    assert writes==[] and snapshot(path)==before
    with pytest.raises(ResearchError) as caught:store._migrate_v7()
    assert caught.value.code=='SCHEMA_UNSUPPORTED' and snapshot(path)==before


@pytest.mark.parametrize('change',['base-ddl','base-guard','unknown-aux','foreign-key'])
def test_v6_constructor_rejects_drift_before_repair_or_data_change(v6_data,change):
    from research.store import SCHEMA
    _,path,store,_,_=v6_data
    with sqlite3.connect(path) as conn:
        if change=='base-ddl':
            conn.execute('DROP TABLE research_idempotency')
            ddl=next(sql for sql in SCHEMA if sql.startswith('CREATE TABLE IF NOT EXISTS research_idempotency'))
            conn.execute(ddl.replace('PRIMARY KEY(principal_id, operation, scope_key, key_digest)','PRIMARY KEY(principal_id, operation, key_digest)'))
        elif change=='base-guard':
            conn.execute('DROP TRIGGER research_revision_no_update')
            conn.execute('CREATE TRIGGER research_revision_no_update BEFORE UPDATE ON research_revisions BEGIN SELECT 1; END')
        elif change=='unknown-aux':conn.execute('CREATE INDEX extra_v6_preflight_idx ON research_dispatch_permits(dispatch_id)')
        else:conn.execute('UPDATE research_controls SET owner_id=?',(str(uuid4()),))
    before=snapshot(path)
    with pytest.raises(ResearchError) as caught:ResearchStore(store.auth_store)
    assert caught.value.code=='SCHEMA_UNSUPPORTED' and snapshot(path)==before


def test_valid_v6_constructor_checks_source_before_any_create_then_upgrades_once(v6_data,monkeypatch):
    _,path,store,_,_=v6_data;before=rows(path);connect=sqlite3.connect;events=[]
    class Observe(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            events.append(sql)
            return super().execute(sql,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Observe,**k))
        upgraded=ResearchStore(store.auth_store)
    first_create=next(i for i,sql in enumerate(events) if sql.startswith('CREATE '))
    assert events[first_create]==V7_TABLES[0]
    assert not any('CREATE TABLE IF NOT EXISTS' in sql for sql in events)
    with upgraded.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==7
        assert conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==0
    after=rows(path)
    assert all(after[name]==data for name,data in before.items() if name!='research_schema')
    ResearchStore(store.auth_store)
