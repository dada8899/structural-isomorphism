"""New current14 sessions use actual protected birth; no historical re-signing."""
from .test_research_private_storage import formal_paid
from .test_research_method_result import stack,source_stack,approved_inputs,paid_api,lifecycle
from .test_research_paid_budget_loop import execution
from research.authorization import AuthorizationGate
from research.paid_provider_session import persist_budget_return
from research.paid_budget import observe_in


def test_actual_current14_reserve_mints_fresh_origin_before_trusted_return(formal_paid):
    _,_,store,_,_,_=formal_paid
    with execution(formal_paid) as (session,_,wire,pid):
        with store.transaction() as conn:
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==14
            row=conn.execute('SELECT body_origin_state,candidate_json,body_candidate_digest,body_envelope_digest,method_commit_json FROM research_provider_sessions WHERE id=?',(session.id,)).fetchone()
            assert tuple(row)==('fresh',None,None,None,None)
            assert conn.execute('SELECT research_method_guard_version()').fetchone()[0]==9
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            observe_in(conn,store=store,lease=lease,return_ref=session.id)
            row=conn.execute('SELECT body_origin_state,candidate_json,body_candidate_digest,body_envelope_digest,method_commit_json FROM research_provider_sessions WHERE id=?',(session.id,)).fetchone()
            assert row[0]=='present' and all(row[index] is not None for index in (1,2,3)) and row[4] is None
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,2,0)
        assert wire['requests']==1
