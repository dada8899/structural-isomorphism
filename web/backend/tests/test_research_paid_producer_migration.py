"""Real nonempty v5->v6, preserving old financial facts on every fault."""
import sqlite3
from uuid import uuid4

import pytest

from .test_research_paid_schema import legacy,snapshot,rows
from .test_research_persistence import stack
from api import auth
from research import ResearchStore
from research.store import V6_SCHEMA,V6_AUX,V5_AUX,V5_GUARDS,PRODUCER_DDL
from .test_research_paid_schema import current,bounded_rows,insert_cost,_USAGE
from research.errors import ResearchError
from .test_research_paid_approval import approved_inputs,preview,identity
from .test_research_d1_integration import source_stack


@pytest.fixture
def v5(legacy,monkeypatch):
    client,path,old,provider,ids=legacy
    with monkeypatch.context() as boundary:
        boundary.setattr(ResearchStore,'_migrate_v6',lambda self:None)
        store=ResearchStore(auth._store())
    with store.transaction() as conn:assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==5
    return client,path,store,provider,ids


def test_nonempty_v5_upgrade_preserves_old_policies_money_receipts_and_inodes(v5):
    _,path,_,_,_=v5;before=rows(path)
    locks={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    store=ResearchStore(auth._store())
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==6
        for table,(columns,values) in before.items():
            if table=='research_schema':continue
            selected=','.join('"'+name+'"' for name in columns)
            assert [tuple(r) for r in conn.execute('SELECT '+selected+' FROM '+table+' ORDER BY rowid')]==values
        assert set(r[0] for r in conn.execute('SELECT status FROM research_reservations'))=={'HELD','SENT','UNKNOWN','SETTLED'}
        assert conn.execute('SELECT count(*) FROM research_paid_approvals').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert {p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}==locks
    ResearchStore(auth._store())


FAULTS=[(phase,name) for phase in ('CREATE TABLE','INSERT INTO','DROP TABLE','ALTER TABLE') for name in V6_SCHEMA]
FAULTS += [('SQL',sql) for sql in (*PRODUCER_DDL,*V6_AUX,*V5_GUARDS)]
FAULTS += [('SQL','DROP '+('INDEX' if ddl.startswith('CREATE UNIQUE INDEX') else 'TRIGGER')+' IF EXISTS '+(ddl.split()[3] if ddl.startswith('CREATE UNIQUE INDEX') else ddl.split()[2])) for ddl in (*V5_AUX,*V5_GUARDS)]
FAULTS += [('SQL','UPDATE research_schema SET version=6'),('COMMIT',None)]


@pytest.mark.parametrize('phase,target',FAULTS)
def test_v6_every_write_boundary_rollback_is_exact_v5(v5,monkeypatch,phase,target):
    _,path,store,_,_=v5;before=snapshot(path);original=sqlite3.connect;raised=[];restored=[]
    marker=target if phase=='SQL' else phase+' '+target+('_v6' if phase in ('CREATE TABLE','INSERT INTO','ALTER TABLE') else '') if target else None
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if marker and sql.startswith(marker) and not raised:
                raised.append(True);raise sqlite3.OperationalError('owned producer migration fault')
            return super().execute(sql,*args,**kwargs)
        def commit(self):
            if phase=='COMMIT' and self.in_transaction and not raised:
                raised.append(True);raise sqlite3.OperationalError('owned producer migration fault')
            return super().commit()
        def close(self):
            restored.append(self.execute('PRAGMA foreign_keys').fetchone()[0]);super().close()
    monkeypatch.setattr(sqlite3,'connect',lambda *a,**k:original(*a,**k,factory=Fault))
    with pytest.raises(sqlite3.OperationalError,match='owned producer migration fault'):store._migrate_v6()
    monkeypatch.setattr(sqlite3,'connect',original)
    assert raised and restored==[1] and snapshot(path)==before
    ResearchStore(auth._store())


@pytest.mark.parametrize('kind',['trigger','index'])
def test_existing_v5_unknown_attachment_rejects_upgrade_without_losing_it(v5,kind):
    _,path,store,_,_=v5
    with store.transaction(write=True) as conn:
        if kind=='trigger':conn.execute("CREATE TRIGGER extra_v5_guard BEFORE UPDATE ON research_dispatch_permits BEGIN SELECT RAISE(ABORT,'owned guard'); END")
        else:conn.execute('CREATE INDEX extra_v5_index ON research_dispatch_permits(expires_at)')
    before=snapshot(path);locks={p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}
    with pytest.raises(ResearchError) as failure:ResearchStore(auth._store())
    assert failure.value.code=='SCHEMA_UNSUPPORTED' and snapshot(path)==before
    assert {p.name:p.stat().st_ino for p in (path.parent/'research-locks').glob('*.lock')}==locks
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==5
        assert conn.execute("SELECT count(*) FROM sqlite_schema WHERE name LIKE 'extra_v5_%'").fetchone()[0]==1


def test_old_v1_send_cannot_acquire_v2_discounted_observation(current):
    store=current[2]
    with store.transaction(write=True) as conn:
        ids=bounded_rows(conn,current)
        with pytest.raises(sqlite3.IntegrityError):
            insert_cost(conn,ids,_USAGE,policy_revision='bounded_usage_upper_v2',booked_upper=1,released_reserve_difference=1)
        with pytest.raises(sqlite3.IntegrityError):
            insert_cost(conn,ids,_USAGE,booked_upper=1,released_reserve_difference=1)
        with pytest.raises(sqlite3.IntegrityError):
            insert_cost(conn,ids,_USAGE,booked_upper=2,released_reserve_difference=1)
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        insert_cost(conn,ids,_USAGE)
        assert tuple(conn.execute('SELECT policy_revision,reserved_upper,booked_upper,released_reserve_difference FROM research_cost_observations').fetchone())==('deepseek-bounded-upper-v1',2,2,0)


@pytest.mark.parametrize('booked',[1,2])
def test_same_v2_policy_can_record_its_bound_difference(approved_inputs,booked):
    client,_,store,_,pid,_,_=approved_inputs;service,draft=preview(approved_inputs)
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'cost-shape-only')
    with store.transaction(write=True) as conn:
        # Legal CNY/v2 schema preconditions only, not an F/CAS implementation.
        quote=conn.execute("SELECT id,account_id,quote_digest FROM research_price_revisions WHERE policy_revision='bounded_usage_upper_v2'").fetchone()
        reservation,permit,dispatch=str(uuid4()),str(uuid4()),str(uuid4())
        conn.execute("INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint) VALUES(?,?,?,?,?,?,1,2,'SENT','bounded_usage_upper_v2',?,?,?)",(reservation,quote['account_id'],result['task_id'],result['step_id'],str(uuid4()),quote['id'],pid,'a'*64,'b'*64))
        conn.execute("INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,authorization_context_digest,authorized_task_version,authorized_step_version) VALUES(?,?,?,?,'consumed','2033','bounded_usage_upper_v2',?,?,?,?,?,1,1)",(permit,result['step_id'],reservation,dispatch,'a'*64,'b'*64,quote['quote_digest'],'c'*64,'d'*64))
        insert_cost(conn,(quote['account_id'],quote['id'],reservation,dispatch),_USAGE,policy_revision='bounded_usage_upper_v2',booked_upper=booked,released_reserve_difference=2-booked)
        assert tuple(conn.execute('SELECT reserved_upper,booked_upper,released_reserve_difference,actual_charge FROM research_cost_observations').fetchone())==(2,booked,2-booked,None)
