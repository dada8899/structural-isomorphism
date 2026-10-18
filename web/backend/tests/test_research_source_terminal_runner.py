"""Actual cancelled Source runs; terminal observation is never sending proof."""
from contextlib import closing,contextmanager
from functools import partial
import sqlite3

from .test_research_d1_integration import source_stack,stack,start,post,source_server,get_local
from research import ResearchStore,ResearchRunner,source_workflow
from research.authorization import AuthorizationGate,OwnerGateLease
from research.source_policy import PinnedPublicTransport
from api import auth


def _cancel(client,rid,tid):
    current=client.get(f'/api/research/{rid}').json()['data']
    response=post(client,f'/api/research/{rid}/cancel',{'task_id':tid,'expected_task_version':current['task_version']})
    assert response.status_code==200 and response.json()['data']['execution']=='CANCELLED'


def _image(path):
    with closing(sqlite3.connect(path)) as conn:
        return tuple(conn.iterdump())


def test_cancelled_never_born_source_is_read_only_observation(source_stack,monkeypatch):
    client,path,rid=source_stack;tid=start(client,rid);_cancel(client,rid,tid)
    store=ResearchStore(auth._store());runner=ResearchRunner(store);before=_image(path)
    original=store.transaction
    @contextmanager
    def read_only(*args,**kwargs):
        assert not kwargs.get('write',False)
        with original(*args,**kwargs) as conn:yield conn
    def no_gate(*args,**kwargs):raise AssertionError('terminal observation must not birth a sender')
    monkeypatch.setattr(store,'transaction',read_only);monkeypatch.setattr(runner.gate,'source_task_gate',no_gate)
    assert runner.run_once(tid)=='CANCELLED'
    assert _image(path)==before
    assert not (path.parent/'research-locks'/('source-'+tid+'.lock')).exists()


def test_cancelled_started_source_still_requires_actual_task_and_fresh_owner(source_stack,monkeypatch):
    client,path,rid=source_stack;tid=start(client,rid);store=ResearchStore(auth._store());gate=AuthorizationGate(store)
    with gate.source_task_gate(tid) as task_lease,store.transaction(write=True) as conn,source_workflow._worker_scope(conn,store,task_lease):
        identity=task_lease.identity
        conn.execute('UPDATE research_source_runs SET started=1 WHERE task_id=?',(tid,))
        conn.execute("UPDATE research_source_resources SET state='running' WHERE task_id=?",(tid,))
    _cancel(client,rid,tid)
    closed=[];owners=[];original_close=source_workflow.close_interrupted;original_owner=AuthorizationGate.owner_gate_id
    def close(store,task,lease):
        assert lease.identity==identity and lease.cleanup is True
        original_close(store,task,lease);closed.append(task)
    @contextmanager
    def owner(self,owner_id,**kwargs):
        with original_owner(self,owner_id,**kwargs) as lease:
            assert type(lease) is OwnerGateLease
            owners.append(lease.identity);yield lease
    monkeypatch.setattr(source_workflow,'close_interrupted',close)
    monkeypatch.setattr(AuthorizationGate,'owner_gate_id',owner)
    with source_server() as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=='CANCELLED'
        assert calls==[]
    assert closed==[tid] and len(owners)==1
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?',(tid,)).fetchone()[0]==1
        assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0]==0
