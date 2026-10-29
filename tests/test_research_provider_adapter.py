"""Offline probes with owned Auth backing: no public DNS, provider call or key."""
from contextlib import contextmanager
from copy import deepcopy
import gzip
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from web.backend.research.authorization import AuthorizationGate
from web.backend.research import provider_adapter as adapter
from web.backend.research import provider_schemas as s


def uid():
    return str(uuid4())


def packet():
    context = s.CallContext(principal_id=uid(), principal_epoch=1, grant_id=uid(), grant_epoch=1,
        owner_epoch=1, acl_epoch=1, research_id=uid(), input_revision=1, input_digest='a'*64,
        task_id=uid(), attempt=1, plan_id=uid())
    text = 'A short exact Unicode 摘录 for a bounded mechanism hypothesis.'
    handle = s.EvidenceHandle(handle='e1', source_id=uid(), source_revision=1, excerpt_id=uid(),
        title='Offline source', attribution='Offline author', extracted_digest=s.digest(text.encode()),
        extracted_text=text, start=0, end=len(text), quote=text,
        display_permission=True, may_send_to_provider=True)
    return s.EvidencePacket(context=context, handles=(handle,))


def quote(**updates):
    value = dict(revision=uid(), currency='USD', scale=6,
        peak_input_miss_units_per_million=300000, peak_input_hit_units_per_million=6000,
        peak_output_units_per_million=1200000, c_bound=1048576, o_bound=393216,
        output_basis='official_maximum', rounding_guard=10,
        price_document_digest='b'*64, model_document_digest='c'*64, bound_basis_digest='d'*64,
        valid_until=2000000000)
    value.update(updates)
    return s.PriceQuote(**value)


def basis(price, **updates):
    value = dict(id=uid(), account_id=uid(), provider_binding_id=uid(), funding_epoch=1, initial_prepaid=s.money('USD',10000000),
        other_use_margin=s.money('USD',1000000), cap=s.money('USD',9000000),
        settled_actual=s.money('USD',100000), upper_booked=s.money('USD',200000),
        held=s.money('USD',300000), available_after_observed_consumption=s.money('USD',8000000),
        price_revision=price.revision, valid_until=2000000000)
    value.update(updates)
    return s.BudgetBasisSnapshot(**value)


def candidate():
    return {'summary':'A candidate comparison, not an established mechanism.',
        'mechanisms':[{'label':'Feedback', 'mechanism':'Delayed feedback may explain oscillation.',
        'variable_map':[{'source':'delay','target':'decision delay','rationale':'A proposed correspondence.'}],
        'conditions':['Delay must be measured.'], 'nontransferable':['Physical units differ.'], 'evidence_handles':['e1']}],
        'competing_explanations':['A common shock could explain both.'],
        'validation_plan':{'measurement':'Measure delay and response.', 'outcome':'Compare to the baseline.',
        'falsification':'Reject equal baseline performance.', 'stop_rule':'Stop at the approved sample size.'},
        'gaps':['No mechanism review or empirical test.']}


def envelope(**updates):
    value = {'model':s.MODEL, 'object':'chat.completion', 'id':'offline-request-1', 'system_fingerprint':'offline',
        'choices':[{'index':0, 'finish_reason':'stop', 'message':{'role':'assistant', 'content':json.dumps(candidate())}}],
        'usage':{'prompt_tokens':100, 'completion_tokens':20, 'total_tokens':120,
                 'prompt_cache_hit_tokens':10, 'prompt_cache_miss_tokens':90,
                 'prompt_tokens_details':{'cached_tokens':10}, 'completion_tokens_details':{'reasoning_tokens':0}}}
    value.update(updates)
    return value


def permit(prepared, lease, price, budget, **updates):
    value = dict(id=uid(), account_id=budget.account_id, provider_binding_id=budget.provider_binding_id,
        funding_epoch=budget.funding_epoch, dispatch_id=uid(), reservation_id=uid(), context=prepared.packet.context,
        request_digest=prepared.request_digest, evidence_digest=prepared.evidence_digest,
        price_digest=s.digest(s.canonical(price.model_dump())), price_revision=price.revision,
        budget_basis_digest=s.digest(s.canonical(budget.model_dump())), gate_identity=lease.identity,
        expires_at=2000000000)
    value.update(updates)
    return s.CallPermit(**value)


@contextmanager
def local_server(body, *, encoding='identity', status=200, slow=None, truncated=False):
    listener = socket.socket()
    listener.bind(('127.0.0.1',0)); listener.listen(1); listener.settimeout(1)
    state = {'requests':0, 'request_body':None, 'stopped':False, 'address':listener.getsockname()}
    stop = threading.Event()
    def serve():
        conn = None
        try:
            conn, _ = listener.accept(); conn.settimeout(1)
            raw = b''
            while b'\r\n\r\n' not in raw:
                part = conn.recv(4096)
                if not part:raise ValueError('closed request')
                raw += part
                if len(raw)>20000:raise ValueError('request too large')
            header, incoming = raw.split(b'\r\n\r\n',1)
            size = int(next(x.split(b':',1)[1] for x in header.split(b'\r\n') if x.lower().startswith(b'content-length:')))
            while len(incoming)<size:
                part=conn.recv(size-len(incoming))
                if not part:raise ValueError('closed request')
                incoming+=part
            state['requests']+=1; state['request_body']=incoming
            response = (f'HTTP/1.1 {status} Probe\r\nContent-Type: application/json\r\nContent-Length: {len(body)+10 if truncated else len(body)}\r\nContent-Encoding: {encoding}\r\nConnection: close\r\n\r\n').encode()+body
            boundary = response.index(b'\r\n\r\n')+4
            if slow == 'headers':
                for byte in response:
                    if stop.wait(.015):break
                    conn.sendall(bytes([byte]))
            elif slow == 'body':
                conn.sendall(response[:boundary])
                for byte in body:
                    if stop.wait(.015):break
                    conn.sendall(bytes([byte]))
            else:
                conn.sendall(response)
        except (OSError,ValueError):
            pass
        finally:
            if conn is not None:conn.close()
            state['stopped']=True
    thread=threading.Thread(target=serve); thread.start()
    try:
        yield lambda deadline: socket.create_connection(listener.getsockname(),timeout=deadline.remaining()), state
    finally:
        stop.set(); listener.close(); thread.join(2)
        assert not thread.is_alive()


def callbacks(budget):
    state={'consumed':set(),'active':True}
    def admit(ticket, prepared, identity):
        if not state['active']:raise PermissionError('offline revoke')
        assert ticket.request_digest==prepared.request_digest and ticket.gate_identity==identity
        return s.DispatchApproval(permit=ticket,budget=budget)
    def consume(approval):
        if approval.permit.id in state['consumed']:raise ValueError('already consumed')
        state['consumed'].add(approval.permit.id)
        return s.ConsumeReceipt(permit=approval.permit, approval_digest=s.digest(s.canonical(approval.model_dump())))
    return admit,consume,state


@contextmanager
def gate(tmp_path):
    from web.backend.tests.test_research_source_spawn import development_auth
    with pytest.MonkeyPatch.context() as setup:
        backing = development_auth.__wrapped__(tmp_path, setup)
        with AuthorizationGate(backing).owner_gate_id(uid()) as lease:
            yield lease


def test_prepare_fixed_request_and_public_paid_closed(monkeypatch):
    evidence=packet(); prepared=adapter.prepare_request('Bounded offline question',evidence)
    value=json.loads(prepared.raw)
    assert len(prepared.raw)<=s.REQUEST_CAP and prepared.request_digest==s.digest(prepared.raw)
    assert value['model']==s.MODEL and value['stream'] is False and value['thinking']=={'type':'disabled'}
    assert value['max_tokens']==4096 and value['response_format']=={'type':'json_object'}
    assert 'tools' not in value and value['tool_choice']=='none'
    assert 'extracted_text' not in prepared.raw.decode() and evidence.context.grant_id not in prepared.raw.decode()
    monkeypatch.setattr(adapter,'_public_connection',lambda *_:pytest.fail('public network touched'))
    with pytest.raises(s.ProviderFailure,match='paid_disabled'):
        adapter.DeepSeekAdapter().preconnect(prepared)
    assert adapter.DeepSeekAdapter.reconcile_capability=='unsupported'


def test_whole_template_and_evidence_byte_limit():
    evidence=packet()
    handles=tuple(evidence.handles[0].model_copy(update={'handle':f'e{n}', 'title':'文'*300,'attribution':'文'*400}) for n in range(20))
    evidence=s.EvidencePacket(context=evidence.context,handles=handles)
    with pytest.raises(s.ProviderFailure,match='request_limit'):
        adapter.prepare_request('Bounded question',evidence)


@pytest.mark.parametrize('change', ['price_expired','basis_expired','currency','margin','cap','held','upper','available','overflow'])
def test_price_and_shared_budget_arithmetic_reject_bad_basis(change):
    price=quote(); budget=basis(price)
    if change=='price_expired':price=price.model_copy(update={'valid_until':1})
    elif change=='basis_expired':budget=budget.model_copy(update={'valid_until':1})
    elif change=='currency':budget=budget.model_copy(update={'held':s.money('CNY',1)})
    elif change=='margin':budget=budget.model_copy(update={'other_use_margin':s.money('USD',10000001)})
    elif change=='cap':budget=budget.model_copy(update={'cap':s.money('USD',9000001)})
    elif change=='held':budget=budget.model_copy(update={'held':s.money('USD',9000000)})
    elif change=='upper':budget=budget.model_copy(update={'upper_booked':s.money('USD',9000000)})
    elif change=='available':budget=budget.model_copy(update={'available_after_observed_consumption':s.money('USD',0)})
    else:price=price.model_copy(update={'peak_output_units_per_million':s.MAX_UNITS})
    with pytest.raises(s.ProviderFailure):budget.admit(price,100)


def test_upper_is_exact_and_native_currency_never_converted():
    price=quote(); budget=basis(price)
    assert budget.admit(price,100).amount_units==786442
    assert quote(o_bound=4096,output_basis='all_completion_request_cap_verified').upper().amount_units==319498
    for value in [True,1.2,-1]:
        with pytest.raises(ValueError):quote(rounding_guard=value)
    cny=quote(currency='CNY')
    with pytest.raises(s.ProviderFailure):budget.admit(cny,100)


@pytest.mark.parametrize('change',['missing','bool','negative','float','sum','cache','reasoning','overbound'])
def test_usage_must_be_complete_and_coherent(change):
    value=deepcopy(envelope()['usage'])
    if change=='missing':value.pop('prompt_tokens')
    elif change=='bool':value['completion_tokens']=True
    elif change=='negative':value['prompt_cache_hit_tokens']=-1
    elif change=='float':value['total_tokens']=120.0
    elif change=='sum':value['total_tokens']=121
    elif change=='cache':value['prompt_tokens_details']['cached_tokens']=9
    elif change=='reasoning':value['completion_tokens_details']['reasoning_tokens']=21
    else:value.update(prompt_tokens=2000000,prompt_cache_hit_tokens=0,prompt_cache_miss_tokens=2000000,total_tokens=2000020);value['prompt_tokens_details']['cached_tokens']=0
    with pytest.raises(s.ProviderFailure):s.parse_usage(value,quote())


def test_real_local_send_under_real_lease_and_accounting_intent(tmp_path):
    evidence=packet(); prepared=adapter.prepare_request('Bounded offline question',evidence)
    price=quote(); budget=basis(price); admit,consume,state=callbacks(budget)
    with local_server(s.canonical(envelope())) as (factory,server):
        client=adapter.DeepSeekAdapter.offline_probe(connection_factory=factory,credential_loader=lambda _binding:'offline-probe-not-a-key')
        connection=client.preconnect(prepared)
        with gate(tmp_path) as lease:
            ticket=permit(prepared,lease,price,budget)
            client.begin(connection,lease=lease,permit=ticket,price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
            assert connection.sent and ticket.id in state['consumed']
        result=client.finish(connection,current_authorizer=lambda *_:evidence)
        assert server['requests']==1 and server['request_body']==prepared.raw
        assert result.safe_code=='ok' and result.usage.total_tokens==120
        assert result.cost.kind=='estimated_upper' and result.cost.actual_charge is None
        assert result.cost.booked_upper==result.cost.reserved_upper==price.upper()
        assert result.execution_mode=='offline_probe' and result.candidate
        with pytest.raises(s.ProviderFailure):client.finish(connection,current_authorizer=lambda *_:evidence)
        assert not connection.deadline.timer.is_alive()


@pytest.mark.parametrize('mode',['fake_lease','expired','wrong_request','wrong_evidence','wrong_gate','wrong_account','wrong_epoch','wrong_price','revoked','bool_approval','bool_consume','consume_lost','duplicate'])
def test_admission_denial_never_sends_or_retries(tmp_path,mode):
    evidence=packet(); prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,state=callbacks(budget)
    class Sink:
        sends=0
        def settimeout(self,_):pass
        def sendall(self,_):self.sends+=1
        def shutdown(self,_):pass
        def close(self):pass
    sink=Sink();client=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda _:sink,credential_loader=lambda _binding:'offline-probe-not-a-key')
    connection=client.preconnect(prepared)
    with gate(tmp_path) as lease:
        ticket=permit(prepared,lease,price,budget)
        chosen=lease
        if mode=='fake_lease':chosen=SimpleNamespace(identity=lease.identity)
        elif mode=='expired':ticket=ticket.model_copy(update={'expires_at':1})
        elif mode=='wrong_request':ticket=ticket.model_copy(update={'request_digest':'0'*64})
        elif mode=='wrong_evidence':ticket=ticket.model_copy(update={'evidence_digest':'0'*64})
        elif mode=='wrong_gate':ticket=ticket.model_copy(update={'gate_identity':(0,0,0,0,0)})
        elif mode=='wrong_account':ticket=ticket.model_copy(update={'account_id':uid()})
        elif mode=='wrong_epoch':ticket=ticket.model_copy(update={'funding_epoch':2})
        elif mode=='wrong_price':ticket=ticket.model_copy(update={'price_digest':'0'*64})
        elif mode=='revoked':state['active']=False
        elif mode=='bool_approval':admit=lambda *_:True
        elif mode=='bool_consume':consume=lambda *_:True
        elif mode=='consume_lost':
            original_consume=consume
            def lost(approval):
                original_consume(approval)
                raise OSError('offline reply lost after committed CAS')
            consume=lost
        else:state['consumed'].add(ticket.id)
        with pytest.raises(s.ProviderFailure):client.begin(connection,lease=chosen,permit=ticket,price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
        with pytest.raises(s.ProviderFailure):client.begin(connection,lease=lease,permit=ticket,price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
    assert sink.sends==0 and not connection.deadline.timer.is_alive()
    if mode=='consume_lost':assert len(state['consumed'])==1


@pytest.mark.parametrize('mode',['bad_json','bad_candidate','length','tools','missing_usage','bad_usage','drift','cancelled','gzip','bomb','wire_limit','status','disconnect','fingerprint'])
def test_response_failures_do_not_forge_actual_or_release_upper(tmp_path,mode):
    evidence=packet(); prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,_=callbacks(budget)
    value=envelope();encoding='identity';status=200
    if mode=='bad_candidate':value['choices'][0]['message']['content']='{"level":"empirical_record"}'
    elif mode=='length':value['choices'][0]['finish_reason']='length'
    elif mode=='tools':value['choices'][0]['message']['tool_calls']=[{'id':'bad'}]
    elif mode=='missing_usage':value.pop('usage')
    elif mode=='bad_usage':value['usage']['total_tokens']=0
    elif mode=='drift':value['model']='deepseek-v4-pro'
    elif mode=='status':status=429
    elif mode=='fingerprint':price=price.model_copy(update={'expected_fingerprint_digest':'0'*64})
    raw=s.canonical(value)
    if mode=='bad_json':raw=b'{'
    elif mode=='wire_limit':raw=b'x'*(s.RESPONSE_CAP+1)
    elif mode=='bomb':raw=gzip.compress(b'x'*(s.RESPONSE_CAP+1));encoding='gzip'
    elif mode=='gzip':raw=gzip.compress(raw);encoding='gzip'
    with local_server(raw,encoding=encoding,status=status,truncated=mode=='disconnect') as (factory,server):
        client=adapter.DeepSeekAdapter.offline_probe(connection_factory=factory,credential_loader=lambda _binding:'offline-probe-not-a-key')
        connection=client.preconnect(prepared)
        with gate(tmp_path) as lease:
            client.begin(connection,lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
        result=client.finish(connection,current_authorizer=lambda *_:None if mode=='cancelled' else evidence)
        complete=mode in {'bad_candidate','length','tools','cancelled','gzip'}
        assert (result.cost.booked_upper is not None)==complete
        assert result.cost.kind==('estimated_upper' if complete else 'unknown')
        assert result.cost.actual_charge is None
        assert (result.candidate is not None)==(mode=='gzip')
        assert server['requests']==1 and not connection.deadline.timer.is_alive()


@pytest.mark.parametrize('slow',['headers','body'])
def test_absolute_deadline_stops_slow_bytes_and_closes_socket(tmp_path,slow):
    evidence=packet();prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,_=callbacks(budget)
    with local_server(s.canonical(envelope()),slow=slow) as (factory,server):
        client=adapter.DeepSeekAdapter.offline_probe(connection_factory=factory,credential_loader=lambda _binding:'offline-probe-not-a-key')
        start=time.monotonic();connection=client.preconnect(prepared,seconds=.15)
        with gate(tmp_path) as lease:
            client.begin(connection,lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
        result=client.finish(connection,current_authorizer=lambda *_:evidence)
        assert time.monotonic()-start<.7
        assert result.candidate is None and result.cost.kind=='unknown'
        assert connection.sock.fileno()==-1 and not connection.deadline.timer.is_alive()


def test_expired_real_lease_and_failed_send_are_closed(tmp_path):
    evidence=packet();prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,_=callbacks(budget)
    class Sink:
        def settimeout(self,_):pass
        def sendall(self,_):raise OSError('never expose raw error')
        def shutdown(self,_):pass
        def close(self):pass
    client=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda _:Sink(),credential_loader=lambda _binding:'offline-probe-not-a-key')
    with gate(tmp_path) as lease:ticket=permit(prepared,lease,price,budget)
    with pytest.raises(s.ProviderFailure,match='admission_rejected'):
        client.begin(client.preconnect(prepared),lease=lease,permit=ticket,price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
    with gate(tmp_path) as lease:
        with pytest.raises(s.ProviderFailure,match='send_unknown'):
            client.begin(client.preconnect(prepared),lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)


def test_fixed_public_transport_uses_original_tls_host_and_peer_only(monkeypatch):
    events=[]
    class Socket:
        def settimeout(self,value):assert 0<value<=60
        def connect(self,target):events.append(('connect',target))
        def getpeername(self):return ('8.8.8.8',443)
        def do_handshake(self):events.append(('handshake',))
        def shutdown(self,_):pass
        def close(self):events.append(('close',))
    sock=Socket()
    class TLS:
        check_hostname=True;verify_mode=adapter.ssl.CERT_REQUIRED
        def wrap_socket(self,raw,**kwargs):
            assert raw is sock
            assert kwargs=={'server_hostname':s.HOST,'do_handshake_on_connect':False}
            events.append(('tls',s.HOST));return sock
    monkeypatch.setattr(adapter,'_resolve_public',lambda _: '8.8.8.8')
    monkeypatch.setattr(adapter.socket,'socket',lambda *_:sock)
    monkeypatch.setattr(adapter.ssl,'create_default_context',lambda:TLS())
    deadline=adapter._Deadline()
    try:assert adapter._public_connection(deadline) is sock
    finally:deadline.close()
    assert events[:3]==[('connect',('8.8.8.8',443)),('tls',s.HOST),('handshake',)]


def test_default_dns_helper_is_bounded_and_contains_no_credentials(monkeypatch):
    called=[]
    def resolve(argv,**kwargs):
        called.append((argv,kwargs))
        assert kwargs['env']=={} and kwargs['timeout']<=60 and kwargs['close_fds']
        assert argv[1]=='-I' and 'signal.alarm(60)' in argv[-1] and s.HOST in argv[-1]
        return SimpleNamespace(stdout=b'["8.8.8.8"]')
    monkeypatch.setattr(adapter.subprocess,'run',resolve)
    deadline=adapter._Deadline()
    try:assert adapter._resolve_public(deadline)=='8.8.8.8'
    finally:deadline.close()
    assert len(called)==1


def test_cancel_during_bounded_credential_loading_is_rechecked_before_consume(tmp_path):
    evidence=packet();prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,state=callbacks(budget)
    class Sink:
        sends=0
        def settimeout(self,_):pass
        def sendall(self,_):self.sends+=1
        def shutdown(self,_):pass
        def close(self):pass
    sink=Sink()
    def loader(binding):
        assert binding==budget.provider_binding_id
        state['active']=False;return 'offline-probe-not-a-key'
    client=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda _:sink,credential_loader=loader)
    connection=client.preconnect(prepared)
    with gate(tmp_path) as lease:
        with pytest.raises(s.ProviderFailure,match='admission_rejected'):
            client.begin(connection,lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,current_authorizer=admit,consume_permit=consume,now=100)
    assert not state['consumed'] and sink.sends==0 and not connection.deadline.timer.is_alive()


@pytest.mark.parametrize('fault',['private_dns','wrong_peer','tls_unverified','resolver_timeout'])
def test_public_transport_faults_close_without_credentials_or_http(monkeypatch,fault):
    closed=[]
    class Sock:
        def settimeout(self,_):pass
        def connect(self,_):pass
        def getpeername(self):return ('1.1.1.1' if fault=='wrong_peer' else '8.8.8.8',443)
        def shutdown(self,_):pass
        def close(self):closed.append(True)
    sock=Sock()
    monkeypatch.setattr(adapter.socket,'socket',lambda *_:sock)
    def resolve(_):
        if fault=='resolver_timeout':raise adapter.subprocess.TimeoutExpired('offline resolver',.01)
        return '127.0.0.1' if fault=='private_dns' else '8.8.8.8'
    monkeypatch.setattr(adapter,'_resolve_public',resolve)
    monkeypatch.setattr(adapter.ssl,'create_default_context',lambda:SimpleNamespace(check_hostname=False,verify_mode=adapter.ssl.CERT_NONE))
    deadline=adapter._Deadline()
    try:
        with pytest.raises(s.ProviderFailure,match='connection_unavailable'):adapter._public_connection(deadline)
    finally:deadline.close()
    if fault in {'wrong_peer','tls_unverified'}:assert closed


def test_dns_timeout_is_safe_and_reaped_by_subprocess_run(monkeypatch):
    def timed(*args,**kwargs):
        assert kwargs['timeout']<=60 and kwargs['close_fds']
        raise adapter.subprocess.TimeoutExpired('offline resolver',.01,output=b'untrusted raw exception')
    monkeypatch.setattr(adapter.subprocess,'run',timed)
    deadline=adapter._Deadline()
    try:
        with pytest.raises(s.ProviderFailure,match='^connection_unavailable$'):adapter._resolve_public(deadline)
    finally:deadline.close()


def _process_before_send(address, lock_path, gate_id, ready):
    # This process is the actual sender, not a dispatch child of the adapter.
    evidence=packet();prepared=adapter.prepare_request('Offline process question',evidence)
    client=adapter.DeepSeekAdapter.offline_probe(
        connection_factory=lambda deadline:socket.create_connection(address,timeout=deadline.remaining()),
        credential_loader=lambda _binding:'offline-probe-not-a-key')
    connection=client.preconnect(prepared)
    try:
        from web.backend.tests.test_research_source_spawn import development_auth
        with pytest.MonkeyPatch.context() as setup:
            backing = development_auth.__wrapped__(Path(lock_path).parent, setup)
            assert backing.path == Path(lock_path)
            with AuthorizationGate(backing).owner_gate_id(gate_id):
                ready.send('preconnected-and-gate-held')
                ready.recv()  # parent terminates this sender before any begin/send
    finally:
        connection.close();ready.close()


def test_sender_death_before_begin_cannot_leave_orphan_http(tmp_path):
    import multiprocessing
    context=multiprocessing.get_context('spawn')
    receiver,sender=context.Pipe()
    from web.backend.tests.test_research_source_spawn import development_auth
    with pytest.MonkeyPatch.context() as setup:
        backing = development_auth.__wrapped__(tmp_path, setup)
        lock_path=backing.path;gate_id=uid()
        with local_server(b'{}') as (_factory,state):
            process=context.Process(target=_process_before_send,args=(state['address'],str(lock_path),gate_id,sender))
            process.start();sender.close()
            try:
                assert receiver.poll(5) and receiver.recv()=='preconnected-and-gate-held'
                process.terminate();process.join(3)
                assert not process.is_alive()
                with AuthorizationGate(backing).owner_gate_id(gate_id,timeout=.5):pass
            finally:
                if process.is_alive():process.kill();process.join(3)
                receiver.close()
            assert state['requests']==0


def test_real_bounded_dns_helper_timeout_kills_and_reaps_only_local_child(monkeypatch):
    native_run=adapter.subprocess.run; native_popen=adapter.subprocess.Popen
    children=[]
    def local_popen(*args,**kwargs):
        child=native_popen(*args,**kwargs);children.append(child);return child
    def local_run(argv,**kwargs):
        assert s.HOST in argv[-1]
        # Execute only a local sleeper; no DNS or network at all.
        return native_run([adapter.sys.executable,'-I','-c','import time;time.sleep(2)'],**kwargs)
    monkeypatch.setattr(adapter.subprocess,'Popen',local_popen)
    monkeypatch.setattr(adapter.subprocess,'run',local_run)
    deadline=adapter._Deadline(.08);start=time.monotonic()
    try:
        with pytest.raises(s.ProviderFailure):adapter._resolve_public(deadline)
    finally:deadline.close()
    assert time.monotonic()-start<.6 and len(children)==1 and children[0].poll() is not None


def test_absolute_tls_handshake_deadline_uses_parent_socket_shutdown(monkeypatch):
    stopped=threading.Event()
    class Sock:
        def settimeout(self,_):pass
        def connect(self,_):pass
        def getpeername(self):return ('8.8.8.8',443)
        def do_handshake(self):
            assert stopped.wait(.5)
            raise OSError('offline interrupted handshake')
        def shutdown(self,_):stopped.set()
        def close(self):stopped.set()
    sock=Sock()
    context=SimpleNamespace(check_hostname=True,verify_mode=adapter.ssl.CERT_REQUIRED,
        wrap_socket=lambda raw,**kwargs:raw)
    monkeypatch.setattr(adapter,'_resolve_public',lambda _: '8.8.8.8')
    monkeypatch.setattr(adapter.socket,'socket',lambda *_:sock)
    monkeypatch.setattr(adapter.ssl,'create_default_context',lambda:context)
    deadline=adapter._Deadline(.08);start=time.monotonic()
    try:
        with pytest.raises(s.ProviderFailure):adapter._public_connection(deadline)
    finally:deadline.close()
    assert stopped.is_set() and time.monotonic()-start<.5


@pytest.mark.parametrize('stage',['loader','consume'])
def test_expiry_during_server_capability_never_sends_after_expiration(tmp_path,monkeypatch,stage):
    evidence=packet();prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,state=callbacks(budget)
    wall=[100];monkeypatch.setattr(adapter.time,'time',lambda:wall[0])
    class Sink:
        sends=0
        def settimeout(self,_):pass
        def sendall(self,_):self.sends+=1
        def shutdown(self,_):pass
        def close(self):pass
    sink=Sink()
    def loader(_binding):
        if stage=='loader':wall[0]=2000000001
        return 'offline-probe-not-a-key'
    def consuming(approval):
        value=consume(approval)
        if stage=='consume':wall[0]=2000000001
        return value
    client=adapter.DeepSeekAdapter.offline_probe(connection_factory=lambda _:sink,credential_loader=loader)
    connection=client.preconnect(prepared)
    with gate(tmp_path) as lease:
        with pytest.raises(s.ProviderFailure,match='send_unknown' if stage=='consume' else 'admission_rejected'):
            client.begin(connection,lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,current_authorizer=admit,consume_permit=consuming)
    assert sink.sends==0 and not connection.deadline.timer.is_alive()
    assert bool(state['consumed'])==(stage=='consume')


@pytest.mark.parametrize('details', ['missing', {}, {'cached_tokens':10}])
def test_optional_prompt_details_keep_complete_top_level_usage(details):
    value=deepcopy(envelope()['usage'])
    if details=='missing':value.pop('prompt_tokens_details')
    else:value['prompt_tokens_details']=details
    result=s.parse_usage(value,quote())
    assert result.prompt_tokens==100 and result.completion_tokens==20 and result.total_tokens==120
    assert result.prompt_cache_hit_tokens==10 and result.prompt_cache_miss_tokens==90
    assert result.cached_tokens==(None if details=='missing' else details.get('cached_tokens'))


@pytest.mark.parametrize('details', [None, [], 'invalid', {'cached_tokens':None}, {'cached_tokens':9},
    {'cached_tokens':True}, {'cached_tokens':10.0}, {'cached_tokens':-1},
    {'cached_tokens':10,'extra':0}])
def test_present_prompt_details_require_exact_structure_and_consistent_integer(details):
    value=deepcopy(envelope()['usage']);value['prompt_tokens_details']=details
    with pytest.raises(s.ProviderFailure,match='usage_unknown'):s.parse_usage(value,quote())


def test_complete_usage_without_optional_details_retains_provider_candidate(tmp_path):
    evidence=packet();prepared=adapter.prepare_request('Question',evidence)
    price=quote();budget=basis(price);admit,consume,_=callbacks(budget)
    value=envelope();value['usage'].pop('prompt_tokens_details')
    with local_server(s.canonical(value)) as (factory,server):
        client=adapter.DeepSeekAdapter.offline_probe(connection_factory=factory,credential_loader=lambda _binding:'offline-probe-not-a-key')
        connection=client.preconnect(prepared)
        with gate(tmp_path) as lease:
            client.begin(connection,lease=lease,permit=permit(prepared,lease,price,budget),price=price,basis=budget,
                current_authorizer=admit,consume_permit=consume,now=100)
        result=client.finish(connection,current_authorizer=lambda *_:evidence)
        assert result.safe_code=='ok' and result.candidate==value['choices'][0]['message']['content']
        assert result.usage.cached_tokens is None and result.usage.prompt_cache_hit_tokens==10
        assert result.cost.kind=='estimated_upper' and result.cost.actual_charge is None
        assert result.cost.booked_upper==price.upper() and server['requests']==1
        assert not connection.deadline.timer.is_alive()
