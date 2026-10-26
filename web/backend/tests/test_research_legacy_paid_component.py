"""Legacy-auth14 paid components; never formal Main or current15 authority.

The real source, funding, transport, receipt, cost and typed HTTP producers are
unchanged. Current15 private storage and Main admission are separate controls.
"""
import pytest
from fastapi.testclient import TestClient
from .test_research_persistence import stack,post,app
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api,preview_data,confirm_data,counts,PREVIEW_FIELDS,APPROVAL_FIELDS
from .test_research_lifecycle import lifecycle,delete
from research import ResearchStore
from research.authorization import AuthorizationGate


@pytest.fixture
def legacy_paid(paid_api,lifecycle):
    client,path,store,*_=paid_api
    assert lifecycle[1]==path
    assert lifecycle[0].cookies.get('phase_session')==client.cookies.get('phase_session')
    assert store._formal_mode() is False and store.auth_store._private_auth is False
    with store.transaction() as conn:
        assert store.auth_store.check_offline_auth_metadata(conn)=='legacy_auth'
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==14
        ResearchStore._check_v14(conn)
    return paid_api


@pytest.mark.parametrize('withdraw',['paid-grant','source','cancel'])
def test_legacy14_paid_result_rechecks_withdrawal_and_keeps_cost(legacy_paid,withdraw):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    client,_,store,rid,excerpt,_=legacy_paid
    with execution(legacy_paid) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        if withdraw=='cancel':
            cancelled=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':2},'formal-cancel')
            assert cancelled.status_code==200,cancelled.text
        else:
            with store.transaction(write=True) as conn:
                if withdraw=='paid-grant':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
                else:conn.execute("DELETE FROM research_evidence_objects WHERE kind='snapshots' AND research_id=?",(rid,))
        reconciled=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':3 if withdraw=='cancel' else 2},'formal-cost-after-withdrawal')
        assert reconciled.status_code==200 and reconciled.json()['data']['method_result'] is None,reconciled.text
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
        assert wire['requests']==1


def test_legacy14_typed_http_commit_and_read_keep_original_body(legacy_paid):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    client,_,store,rid,_,_=legacy_paid
    with execution(legacy_paid) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'formal-typed-commit')
        assert response.status_code==200,response.text
        report=response.json()['data']['method_result'];assert report['result_ref']==session.id and report['received_at']==receipt._time
        assert report['model_analysis_ran'] is False and report['evidence']=='INSUFFICIENT'
        reopened=client.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
        assert reopened.status_code==200 and reopened.json()['data']['method_result']==report,reopened.text
        assert wire['requests']==1


def test_legacy14_delete_before_late_return_keeps_body_closed(legacy_paid,lifecycle):
    from .test_research_paid_budget_loop import execution
    from research.paid_provider_session import persist_budget_return
    from research.paid_budget import observe_in
    client,_,store,rid,_,_=legacy_paid
    with execution(legacy_paid) as (session,result,wire,pid):
        receipt=session.receive()
        erased=delete(lifecycle[0]);assert erased.status_code==200,erased.text
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            observe_in(conn,store=store,lease=lease,return_ref=session.id)
            assert conn.execute('SELECT candidate_json,method_commit_json,body_origin_state FROM research_provider_sessions').fetchone()[:]==(None,None,'closed')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
        assert client.get(f'/api/research/{rid}').status_code==401
        assert wire['requests']==1


def test_legacy14_router_mount_public_projection_and_zero_send(legacy_paid):
    """The former raw-Main positive belongs to this explicit legacy router."""
    client,_,store,rid,excerpt,resolver=legacy_paid
    application=app()
    application.state.research_paid_resolver=resolver
    with TestClient(application) as mounted:
        mounted.cookies.update(client.cookies)
        response=post(mounted,'/api/research/'+rid+'/paid-previews',preview_data(client,rid,excerpt),'mounted')
        assert response.status_code==200,response.text
        draft=response.json()['data'];assert set(draft)==PREVIEW_FIELDS
        approved=post(mounted,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'mounted-confirm')
        assert approved.status_code==200,approved.text
        assert set(approved.json()['data'])==APPROVAL_FIELDS
        for forbidden in ('"funding"','"account_id"','"provider_binding_id"','"context"','"extracted_text"','"maximum_approved_upper"','"preview_view"'):
            assert forbidden not in response.text and forbidden not in approved.text
        assert all(counts(store)[name]==0 for name in ('research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions'))
        application.state.research_paid_resolver=None
        assert post(mounted,'/api/research/'+rid+'/paid-previews',preview_data(client,rid,excerpt),'normal-default').status_code==503
