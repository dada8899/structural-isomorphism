"""Actual Main HTTPS/owner/SQLite/Native ledger, no new-purpose transport."""
from contextlib import contextmanager
import json
import time
from uuid import uuid4

import pytest

from web.backend.tests.acceptance.formal_main_browser_service import _HttpsClient
from web.backend.tests.test_formal_main_admission import BETA, envelope, problem
from web.backend.tests.test_plan_runtime_transport import _ActualMainClient, provider, saved, stack
from web.backend.tests.test_research_native_plan import admitted
from api import auth
from research import ResearchRunner, plan_native
from research.authorization import AccountIdentity
from research.errors import ResearchError
from research.external_first_answer_contract import (
    CAP_UNITS, MIN_RISK_MARGIN_UNITS, PROJECT, PURPOSE, ContractError,
    ExplicitConfirmation, QuoteBinding, parse_unverified_candidate, recovery_hint,
)
from research.external_first_answer_seam import preview_saved_question, check_saved_confirmation
from research.service import ResearchService


@contextmanager
def approved_existing_fixture(store, actor, server):
    # The existing guarded Native writer creates the only economic account.
    # The test does not INSERT/UPDATE any funding or ledger row directly.
    authority = plan_native.create_controlled_runtime_fixture_authority(
        store, actor, server, approved_cap_units=CAP_UNITS, risk_margin_units=MIN_RISK_MARGIN_UNITS)
    provision = plan_native.issue_native_provision(store, authority)
    permit = plan_native.mint_runtime_permit(provision)
    resource = plan_native.open_plan_resource(permit)
    try:
        plan_native.install_native_funding(store, provision, resource)
        yield
    finally:
        plan_native.retire_installation(store)


def capture(store):
    with store.transaction() as conn:
        return {
            "ledger": [tuple(r) for r in conn.execute(
                'SELECT id, binding_id, funding_epoch, settled, held, upper_booked FROM research_funding_accounts ORDER BY id')],
            "runs": [tuple(r) for r in conn.execute(
                'SELECT id,account_id,state,cost_state,result_ref,upper FROM research_plan_native_runs ORDER BY id')],
            "counts": tuple(conn.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
                ('research_tasks', 'research_reservations', 'research_dispatch_permits', 'research_paid_approvals',
                 'research_plan_native_previews', 'research_plan_native_runs')),
        }


def offered_quote(store, now):
    existing=capture(store)["ledger"]
    assert len(existing)==1
    account_id,economic_binding,epoch,*_=existing[0]
    return QuoteBinding(purpose=PURPOSE,project_ref=PROJECT,provider="deepseek",model="deepseek-flash",
        account_id=account_id,economic_binding=economic_binding,funding_epoch=epoch,quote_id=str(uuid4()),
        price_basis_digest="a"*64,currency="CNY",scale=6,upper_units=5000,issued_at=now,valid_until=now+60)


def explicit(preview, **override):
    return ExplicitConfirmation(**({"purpose":PURPOSE,"preview_digest":preview.preview_digest,
        "request_digest":preview.request_digest,"upper_units":preview.upper_units,
        "confirm_exact_question":True,"confirm_maximum_cost":True,"declares_right_to_send":True}|override))


def second_owner(client):
    service=client.service
    other=_HttpsClient(service.port,service.certificate)
    assert other.request('POST','/api/auth/request-link',{'email':'other-external-fallback@example.invalid'})[0]==200
    token=service.take_latest_magic_token()
    try:assert other.request('POST','/api/auth/verify',{'token':token})[0]==200
    finally:token=None
    claims=auth._decode_jwt(next(c.value for c in other.cookies if c.name=='phase_session'))
    try:
        identity=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])
        assert other.request('POST','/api/research',envelope({'problem':problem()}),key='other-external-draft')[0]==200
        return identity
    finally:
        claims=None
        other.cookies.clear()


@pytest.mark.parametrize("unknown",[False,True],ids=["known-return","unknown-hold"])
def test_actual_owner_shared_ledger_and_existing_native_control_never_grant_new_purpose(stack,monkeypatch,unknown):
    client,_,old_rid,store=saved(stack,monkeypatch)
    actor=client.actor
    service=ResearchService(store)
    question="如果调节动作总是晚一轮生效，为什么反复超调？"
    original=problem()|{"original_input":question}
    saved_new=client.post('/api/research',json=envelope({'problem':original}),
        headers={'origin':BETA,'idempotency-key':'external-fallback-draft'})
    assert saved_new.status_code==200
    rid=saved_new.json()['data']['research']['id']
    foreign=second_owner(client)
    with provider(unknown_usage=unknown) as (server,calls,_),approved_existing_fixture(store,actor,server):
        assert plan_native.require_purpose(store,"phenomenon_plan_v1") is not None
        with pytest.raises(ResearchError,match="FUNDING_CLOSED"):
            plan_native.require_purpose(store,PURPOSE)
        now=int(time.time())
        quote=offered_quote(store,now)
        before=capture(store)
        prepared=preview_saved_question(service,actor,rid,1,1,quote,now=now)
        assert prepared.exact_question==question and prepared.may_send is False
        decision=explicit(prepared)
        with pytest.raises(ContractError,match="explicit_confirmation_required"):
            check_saved_confirmation(service,actor,rid,1,1,prepared,quote,
                explicit(prepared,confirm_exact_question=False),now=now)
        with pytest.raises(ResearchError,match="NOT_FOUND"):
            check_saved_confirmation(service,foreign,rid,1,1,prepared,quote,decision,now=now)
        first=check_saved_confirmation(service,actor,rid,1,1,prepared,quote,decision,now=now)
        assert first=={"state":"closed","reason":"external_purpose_not_admitted","may_reserve":False,"may_send":False,"result_ref":None}
        assert check_saved_confirmation(service,actor,rid,1,1,prepared,quote,decision,now=now)==first
        assert capture(store)==before and calls==[]

        # Positive control is the already authorized original purpose, on
        # this exact same account. Only its actual guarded runner can send.
        original_task=admitted(client,old_rid)
        result=ResearchRunner(store).run_once(original_task['task_id'])['data']
        assert [event[0] for event in calls]==['GET','POST']
        assert result['state']==('pending_reconciliation' if unknown else 'saved')
        assert result.get('real_model_executed',False) is False
        after=capture(store)
        assert len(after['ledger'])==len(after['runs'])==1
        assert after['ledger'][0][0]==quote.account_id==after['runs'][0][1]
        if unknown:
            assert after['ledger'][0][-2]>0 and after['runs'][0][2:4]==('unknown','unknown')
            hint=recovery_hint('unknown')
            assert hint['hold_possible_charge'] and not hint['may_send']
        else:
            opened=client.get('/api/research/'+old_rid+'/plan-results/'+original_task['result_ref'])
            assert opened.status_code==200 and opened.json()['data']['content']['execution_mode']=='controlled_fixture'
            assert client.get('/api/research/'+old_rid+'/plan-results/'+original_task['result_ref']).json()==opened.json()
            assert after['ledger'][0][-2]==0 and after['ledger'][0][-1]>0
        ResearchRunner(store).run_once(original_task['task_id'])
        latest=int(time.time())
        if latest>=quote.valid_until:pytest.fail("isolated fixture exceeded bounded quote lifetime")
        repeated=check_saved_confirmation(service,actor,rid,1,1,prepared,quote,decision,now=latest)
        assert repeated['reason']==('unknown_reconcile_only' if unknown else 'external_purpose_not_admitted')
        assert repeated['result_ref'] is None and not repeated['may_reserve'] and not repeated['may_send']
        parsed=parse_unverified_candidate(json.dumps({'status':'candidate',
            'explanation':'如果纠偏信息滞后，可能累积过度动作。',
            'assumptions':['系统确实会依据观测修正。'],'next_check':'固定输入，记录动作时延。',
            'evidence_status':'not_checked'},ensure_ascii=False).encode())
        assert parsed['review_required'] and parsed['state']=='closed'
        assert capture(store)==after and [event[0] for event in calls]==['GET','POST']
        changed=client.post('/api/research/'+rid+'/revisions',
            json=envelope({'expected_revision':1,'problem':original|{'original_input':question+' 对比外部周期。'}}),
            headers={'origin':BETA,'idempotency-key':'external-fallback-changed'})
        assert changed.status_code==200
        with pytest.raises(ResearchError,match="REVISION_CONFLICT"):
            check_saved_confirmation(service,actor,rid,1,1,prepared,quote,decision,now=latest)
        assert capture(store)==after and [event[0] for event in calls]==['GET','POST']
