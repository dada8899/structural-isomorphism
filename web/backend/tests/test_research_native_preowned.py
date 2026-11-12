"""Actual owned socket cleanup before a balance/pending handoff; no live IO."""
from contextlib import contextmanager
import socket
import pytest
from research import ResearchRunner
from research import plan_native as native,plan_native_runtime as flow
from .test_research_native_plan import saved,provider,installed,admitted,post
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack


def test_preowned_real_get_socket_close_after_physical_close_is_not_clean(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    from research.errors import ResearchError
    checked=False
    try:
        with provider() as (server,calls),installed(data,server) as resource:
            original=socket.socket.close;fired=[];closed=[]
            def fail_after_close(conn):
                try:target=conn.getpeername()==('127.0.0.1',server.server_port)
                except OSError:target=False
                original(conn)
                if target and calls and calls[-1][0]=='GET' and not fired:
                    fired.append(True);closed.append(conn)
                    raise OSError('synthetic GET200 socket actually closed then close raised')
            monkeypatch.setattr(socket.socket,'close',fail_after_close)
            result=admitted(client,rid)
            with pytest.raises(OSError):ResearchRunner(store).run_once(result['task_id'])
            assert fired==[True] and closed[0].fileno()==-1 and [c[0] for c in calls]==['GET']
            with store.transaction() as conn:
                value=conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()
                assert value[:2]==('closed','unreserved')
                assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,0)
                assert value[2]=='uncertain'
                assert conn.execute('SELECT state FROM research_plan_native_funding').fetchone()[0]=='blocked'
            assert not native._PENDING and not native._RETURNS and not native._BALANCES and not flow._CAPS
            checked=True
    except ResearchError as cleanup:
        assert cleanup.code=='CLEANUP_UNCERTAIN'
    assert checked


def readmit(client,rid,key):
    version=client.get('/api/research/'+rid).json()['data']['research_version']
    response=post(client,rid,'plan-previews',dict(input_revision=1,expected_research_version=version,observation_source='own_observation',declaration_status='self_declared'),key+'-preview')
    assert response.status_code==200,response.json().get('error')
    preview=response.json()['data'];body={field:preview[field] for field in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};body['confirm_outbound']=True
    result=post(client,rid,'plan-approvals',body,key+'-confirm');assert result.status_code==200,result.json().get('error')
    return result.json()['data']


@contextmanager
def changing_balance_provider():
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from threading import Thread
    import json
    from .test_research_funded_plan import CANDIDATE
    calls=[];balances=iter(('1','59'))
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value):
            raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            calls.append('GET');self.reply({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':next(balances)}]})
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']));calls.append('POST')
            self.reply({'model':'deepseek-flash','usage':{'prompt_tokens':100,'completion_tokens':80,'total_tokens':180},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(CANDIDATE)}}]})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever);thread.start()
    try:yield server,calls
    finally:server.shutdown();server.server_close();thread.join(3);assert not thread.is_alive()


def test_clean_low_balance_keeps_same_resource_for_new_legal_attempt(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with changing_balance_provider() as (server,calls),installed(data,server) as resource:
        first=admitted(client,rid)
        with pytest.raises(ResearchError) as low:ResearchRunner(store).run_once(first['task_id'])
        assert low.value.code=='BUDGET_EXHAUSTED' and calls==['GET']
        resource.require();resource.permit.require();resource.retire_unhanded()
        assert not resource._io and not resource._cleanup_faults and not resource.flight.locked()
        with store.transaction() as conn:assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('closed','unreserved','clean')
        second=readmit(client,rid,'after-low')
        assert ResearchRunner(store).run_once(second['task_id'])['data']['state']=='saved'
        assert calls==['GET','GET','POST'] and not resource._io


def test_allocated_connection_failure_is_owned_and_clean_retry_uses_same_resource(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),installed(data,server) as resource:
        allocated=[];connect=socket.socket.connect_ex
        def fail(conn,address):
            if address==('127.0.0.1',server.server_port):
                assert conn in resource._io;allocated.append(conn);raise OSError('synthetic pre-send connect failure')
            return connect(conn,address)
        with monkeypatch.context() as fault:
            fault.setattr(socket.socket,'connect_ex',fail);first=admitted(client,rid)
            with pytest.raises(OSError,match='pre-send connect'):ResearchRunner(store).run_once(first['task_id'])
        assert allocated and all(conn.fileno()==-1 for conn in allocated) and calls==[]
        resource.require();resource.retire_unhanded();assert not resource._io
        second=readmit(client,rid,'after-connect')
        assert ResearchRunner(store).run_once(second['task_id'])['data']['state']=='saved' and [c[0] for c in calls]==['GET','POST']


def test_all_core_retirements_precede_hook_and_flight_release_after_close_fault(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data;events=[]
    for cls,label in ((flow.NativePlanSendLease,'send'),(native.ControlledNativePending,'pending'),(native.OwnedNativeReturn,'owned'),(native.OwnedBalanceReceipt,'balance'),(flow.NativeBalanceLease,'balance_cap')):
        original=cls.close
        def close(value,original=original,label=label):
            events.append(label);original(value)
            if label=='pending':raise OSError('synthetic pending close report after physical close')
        monkeypatch.setattr(cls,'close',close)
    hook=native.ControlledNativeResource.retire_unhanded;hook_locks=[]
    def observe(resource):
        events.append('hook');hook_locks.append(resource.flight.locked());return hook(resource)
    monkeypatch.setattr(native.ControlledNativeResource,'retire_unhanded',observe)
    with provider() as (server,calls),installed(data,server) as resource:
        result=admitted(client,rid)
        with pytest.raises(ResearchError) as uncertain:ResearchRunner(store).run_once(result['task_id'])
        assert uncertain.value.code=='CLEANUP_UNCERTAIN'
        assert events[:6]==['send','pending','owned','balance','balance_cap','hook'] and hook_locks[0] is True
        assert not resource.flight.locked() and not resource._io
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('returned','upper_booked','uncertain')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
        assert [c[0] for c in calls]==['GET','POST']
    # Installation close runs outside the worker flight; its hook is not a send.


def test_unreturned_allocated_socket_close_failure_keeps_original_error_and_uncertainty(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data;allocated=[];fired=[];checked=False
    try:
        with provider() as (server,calls),installed(data,server) as resource:
            connect=socket.socket.connect_ex;close=socket.socket.close
            def fail_connect(conn,address):
                if address==('127.0.0.1',server.server_port):
                    assert conn in resource._io;allocated.append(conn);raise OSError('original allocated connect failure')
                return connect(conn,address)
            def fail_close(conn):
                if conn in allocated and not fired:
                    fired.append(True);raise OSError('secondary close failure before physical close')
                return close(conn)
            monkeypatch.setattr(socket.socket,'connect_ex',fail_connect);monkeypatch.setattr(socket.socket,'close',fail_close)
            result=admitted(client,rid)
            with pytest.raises(OSError,match='original allocated connect failure'):ResearchRunner(store).run_once(result['task_id'])
            assert fired==[True] and all(conn.fileno()==-1 for conn in allocated) and calls==[]
            assert resource._cleanup_faults and resource._io and not resource.flight.locked()
            assert resource.permit.active and resource.permit.provision.active
            with store.transaction() as conn:
                assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('closed','unreserved','uncertain')
                assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,0)
            assert not native._PENDING and not native._RETURNS and not native._BALANCES and not flow._CAPS
            checked=True
    except ResearchError as cleanup:assert cleanup.code=='CLEANUP_UNCERTAIN'
    assert checked


def test_retire_hook_never_accepts_a_status_dto_as_clean(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    actual=native.ControlledNativeResource.retire_unhanded
    def wrong(resource):actual(resource);return {'state':'clean'}
    monkeypatch.setattr(native.ControlledNativeResource,'retire_unhanded',wrong)
    with provider() as (server,calls),installed(data,server) as resource:
        result=admitted(client,rid)
        with pytest.raises(ResearchError) as unsafe:ResearchRunner(store).run_once(result['task_id'])
        assert unsafe.value.code=='CLEANUP_UNCERTAIN'
        assert not resource._io and not resource.flight.locked()
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('returned','upper_booked','uncertain')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
        assert [c[0] for c in calls]==['GET','POST']
