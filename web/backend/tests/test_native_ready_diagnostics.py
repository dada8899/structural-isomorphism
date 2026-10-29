"""Pure Native7 protocol/deadline/ownership controls; never start services."""
import ast
import copy
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import threading
from types import SimpleNamespace
import urllib.error

import pytest

ROOT=Path(__file__).resolve().parents[3]


def load(relative,name):
    path=ROOT/relative;spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


P=load('scripts/probe-native-linux-lifecycle.py','ready_protocol_controller')
F=load('web/backend/tests/acceptance/native_linux_lifecycle_fixture.py','ready_protocol_fixture')


def frame(seq,stage,health=None,failed_at=None,exception=None,number=None):
    return {'protocol':'native-helper-startup-v1','seq':seq,'stage':stage,'failed_at':failed_at,'exception':exception,'errno':number,'health':P.empty_health() if health is None else health}


def ready_health():return {'http_status':200,'base':'READY','source_execute':'READY','transport':'OK'}


def complete_diagnostics(probe,value):
    """Legal DTO data, no socket, unit, Main, witness or execution observed."""
    for phase in probe.PHASES:
        row=probe.empty_startup_diagnostic();row.update(last_stage='READY',health=ready_health(),helper_returncode=0,deadline_reached=False,ready_observed=True,frames=7,startup_bytes=2048)
        row['formal'].update(binding='BOUND',stream='EOF',peer_root=True,receive_buffer=16384)
        row['unit_after']={'active':'inactive','result':'success','exit_kind':'EXITED','exit_status':0,'invocation_matches':True,'pid_matches':True,'start_matches':True,'start_elapsed_ms':100,'exit_elapsed_ms':0}
        value['startup_diagnostics'][phase]=row
    value['diagnostic_resources']=dict(probe.empty_diagnostic_resources(),listener_births=4,listener_closed=4,accepted_births=4,accepted_closed=4,paths_born=4,paths_removed=4,directory_born=True,directory_closed=True,directory_removed=True)
    value['resources'].update(unit_invocations=4,unit_exited=4)
    return value


def startup_wire(module=P):
    return b''.join(module.canonical(frame(i,stage,ready_health() if stage=='READY' else None))+b'\n' for i,stage in enumerate(P.STARTUP_STAGES[:-1]))


@pytest.mark.parametrize('split',[1,7,63,1024])
def test_fixed_frames_survive_arbitrary_fragmentation_without_service(split):
    decoder=P.StartupFrames();wire=startup_wire()
    for offset in range(0,len(wire),split):decoder.feed(wire[offset:offset+split])
    decoder.finish();assert decoder.terminal=='READY' and decoder.count==7 and decoder.total==len(wire)
    assert P.health_ready(decoder.health)


@pytest.mark.parametrize('fault',['duplicate','order','truncated','extra','unknown','duplicate_key','oversize','terminal_again'])
def test_startup_hostile_byte_streams_fail_closed(fault):
    decoder=P.StartupFrames();first=P.canonical(frame(0,'CONFIG'))+b'\n'
    if fault=='duplicate':wire=first+P.canonical(frame(1,'CONFIG'))+b'\n'
    elif fault=='order':wire=P.canonical(frame(0,'SMTP_BIND'))+b'\n'
    elif fault=='truncated':wire=first[:-1]
    elif fault=='extra':bad=frame(0,'CONFIG');bad['raw']='forbidden';wire=P.canonical(bad)+b'\n'
    elif fault=='unknown':wire=P.canonical(frame(0,'UNREVIEWED'))+b'\n'
    elif fault=='duplicate_key':wire=b'{"protocol":"native-helper-startup-v1","protocol":"x"}\n'
    elif fault=='oversize':wire=b'x'*1024
    else:wire=startup_wire()+P.canonical(frame(7,'FAILED',failed_at='HEALTH_WAIT',exception='OTHER'))+b'\n'
    with pytest.raises(Exception):decoder.feed(wire);decoder.finish()


@pytest.mark.parametrize('status,base,source,transport,accepted',[(200,'ready','ready','OK',True),(503,'ready','ready','HTTP_ERROR',False),(200,'ready','unavailable','OK',False),(200,'unavailable','ready','OK',False),(200,'ready','ready','TLS',False)])
def test_ready_requires_http200_and_both_real_check_values(status,base,source,transport,accepted):
    value=P.health_projection(status,{'checks':{'base':base,'source_execute':source}},transport)
    assert P.health_ready(value) is accepted
    if not accepted:
        with pytest.raises(ValueError):P.validate_startup_frame(frame(6,'READY',value))


def test_health_absent_other_and_unobserved_have_different_meanings():
    assert P.empty_health()['base'] is None
    assert P.health_projection(200,{},'OK')['base']=='ABSENT'
    assert P.health_projection(200,{'checks':{'base':None}},'OK')['base']=='OTHER'
    assert P.health_projection(200,[],'OK')['transport']=='SHAPE'


def test_codecs_are_exact_same_ast_and_formal_whitelist_is_original():
    functions=('empty_health','validate_health','health_projection','health_ready','ready_budget','validate_startup_frame','StartupFrames')
    trees=[ast.parse(Path(m.__file__).read_bytes()) for m in (P,F)]
    for name in functions:
        nodes=[next(n for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name) for t in trees]
        assert ast.dump(nodes[0],include_attributes=False)==ast.dump(nodes[1],include_attributes=False)
    formal=ast.parse((ROOT/'scripts/run-formal-main.py').read_bytes())
    codes=ast.literal_eval(next(n.value.args[0] for n in formal.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='_CODES' for t in n.targets)))
    assert set(codes)==set(P.FORMAL_CODES)
    assert 'StandardError=file:' in Path(P.__file__).read_text() and 'StandardError=null' not in Path(P.__file__).read_text()


@pytest.mark.parametrize('chunks',[[b'FORMAL_ENTRY:APP_',b'IMPORT_FAILED\n'],[b'noise\nFORMAL_ENTRY:APP_IMPORT_FAILED\nFORMAL_ENTRY:FD_CLOSE_FAILED\n']])
def test_code_stream_only_keeps_exact_fixed_lines(chunks):
    stream=P.FormalCodeBytes()
    for chunk in chunks:stream.feed(chunk)
    stream.finish();assert stream.codes[0]=='APP_IMPORT_FAILED' and stream.state=='EOF'
    assert 'noise' not in repr(stream.codes)


@pytest.mark.parametrize('raw',[b' FORMAL_ENTRY:APP_IMPORT_FAILED\n',b'FORMAL_ENTRY:APP_IMPORT_FAILED\r\n',b'prefixFORMAL_ENTRY:APP_IMPORT_FAILED\n',b'FORMAL_ENTRY:not-reviewed\n',b'\xff\n'])
def test_unknown_lines_are_counted_without_raw_retention(raw):
    stream=P.FormalCodeBytes();stream.feed(raw);stream.finish()
    assert stream.codes==[] and stream.unknown==1 and stream.pending==bytearray()


@pytest.mark.parametrize('fault',['long','truncated','third','wrong_second','limit'])
def test_code_stream_limits_are_not_expanded_to_find_a_marker(fault):
    stream=P.FormalCodeBytes()
    with pytest.raises(ValueError):
        if fault=='long':stream.feed(b'x'*129)
        elif fault=='truncated':stream.feed(b'partial');stream.finish()
        elif fault=='third':stream.feed(b'FORMAL_ENTRY:APP_IMPORT_FAILED\nFORMAL_ENTRY:FD_CLOSE_FAILED\nFORMAL_ENTRY:FD_CLOSE_FAILED\n')
        elif fault=='wrong_second':stream.feed(b'FORMAL_ENTRY:APP_IMPORT_FAILED\nFORMAL_ENTRY:SERVER_FAILED\n')
        else:
            for _ in range(16):stream.feed(b'\n'*1024)
    assert stream.total<=16384 and len(stream.pending)<=128 and len(stream.codes)<=2


def unit(pid='123',main='123',invocation='a'*32,start='1000000'):
    return {'MainPID':main,'ExecMainPID':pid,'InvocationID':invocation,'ExecMainStartTimestampMonotonic':start,'ExecMainExitTimestampMonotonic':'0','ExecMainCode':'0','ExecMainStatus':'0','ActiveState':'active','Result':'success'}


def test_root_connect_is_not_confused_with_runtime_service_uid_or_exited_main():
    before=unit();after=unit(main='0')
    assert P.peer_unit_binding((123,0,0),before,after,(.5,2))
    assert not P.peer_unit_binding((123,999,987),before,after,(.5,2))
    assert not P.peer_unit_binding((124,0,0),before,after,(.5,2))


@pytest.mark.parametrize('change',[{'InvocationID':'b'*32},{'ExecMainPID':'124'},{'ExecMainStartTimestampMonotonic':'0'},{'ExecMainStartTimestampMonotonic':'1500000'},{'MainPID':'999'},{'InvocationID':None}])
def test_same_pid_different_invocation_or_missing_start_never_binds(change):
    before=unit();after=dict(before,**change)
    assert not P.peer_unit_binding((123,0,0),before,after,(.5,2))


def test_running_default_zero_is_not_an_observed_normal_exit():
    snapshot=P.unit_diagnostic(unit(),{'pid':123,'start':1000000,'InvocationID':'a'*32},2)
    assert snapshot['exit_kind'] is None and snapshot['exit_status'] is None
    unknown=P.unit_diagnostic({},None,2);assert unknown['start_matches'] is None


def test_one_absolute_deadline_and_three_seconds_are_inside_ten():
    end,work=P.ready_budget(100,500);assert (end,work)==(110,107)
    assert P.ready_budget(100,135)==(105,102)
    decoder=P.StartupFrames()
    for i,stage in enumerate(P.STARTUP_STAGES[:6]):decoder.feed(P.canonical(frame(i,stage))+b'\n')
    assert (end,work)==(110,107)  # Progress cannot mutate either deadline.


class ClockRaw:
    def __init__(self,clock,step,raw=b'x'):self.clock=clock;self.step=step;self.data=raw;self.timeouts=[];self.closed=False
    def settimeout(self,value):self.timeouts.append(value)
    def recv(self,size):self.clock[0]+=self.step;return self.data[:size]
    def sendall(self,raw):self.clock[0]+=self.step
    def makefile(self,*a,**k):return SimpleNamespace(close=lambda:setattr(self,'closed',True))
    def close(self):self.closed=True


@pytest.mark.parametrize('operation',['readline','read','send'])
def test_slow_chunks_or_flush_do_not_renew_absolute_time(monkeypatch,operation):
    clock=[0.0];raw=ClockRaw(clock,.4);connection=F._DeadlineSocket(raw,1.0,5)
    monkeypatch.setattr(F.time,'monotonic',lambda:clock[0])
    reader=connection.makefile('rb')
    try:
        with pytest.raises(F.FixtureFailure):
            if operation=='readline':reader.readline(10)
            elif operation=='read':reader.read(10)
            else:
                for _ in range(4):connection.sendall(b'x')
        assert max(raw.timeouts)<=1 and raw.timeouts[-1]<raw.timeouts[0]
    finally:reader.close()


class Response:
    def __init__(self,raw,status=200,clock=None,step=0):self.raw=raw;self.status=status;self.clock=clock;self.step=step;self.owner=threading.get_ident();self.closed=False
    def read(self,size):
        if self.clock is not None:self.clock[0]+=self.step
        result=self.raw[:size];self.raw=self.raw[size:];return result
    def close(self):assert threading.get_ident()==self.owner;self.closed=True
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


def test_http_error_body_is_bounded_projected_and_closed_by_creator():
    body=io.BytesIO(F.canonical({'checks':{'base':'ready','source_execute':'ready'},'irrelevant':'never published'}))
    error=urllib.error.HTTPError(F.ORIGIN+'/api/health',503,'not published',None,body)
    class Client:
        def open(self,*a,**k):raise error
    service=object.__new__(F.LocalService);service.client=Client()
    result=service._health_request(F.time.monotonic()+1)
    assert result=={'http_status':503,'base':'READY','source_execute':'READY','transport':'HTTP_ERROR'}
    assert body.closed and not F.health_ready(result)


def test_slow_health_closes_response_and_cannot_report_ready(monkeypatch):
    clock=[0.0];response=Response(b'x'*8192,clock=clock,step=.6)
    service=object.__new__(F.LocalService);service.client=SimpleNamespace(open=lambda *a,**k:response)
    monkeypatch.setattr(F.time,'monotonic',lambda:clock[0])
    with pytest.raises(F.FixtureFailure):service._health_request(1)
    assert response.closed


def test_runtime_request_uses_original_runtime_not_expired_work_window(monkeypatch):
    clock=[5.0];response=Response(b'{}');seen=[]
    service=object.__new__(F.LocalService);service.deadline=20;service.work_deadline=2
    def opened(*args,**kwargs):seen.append(kwargs['timeout']);return response
    service.client=SimpleNamespace(open=opened);monkeypatch.setattr(F.time,'monotonic',lambda:clock[0])
    assert service.request('GET','/api/health')=={} and seen==[5] and response.closed


def test_owned_socketpair_file_reference_survives_connection_close():
    left,right=socket.socketpair();old=left.fileno();reader=None
    try:
        connection=F._DeadlineSocket(left,F.time.monotonic()+1,1);reader=connection.makefile('rb')
        right.sendall(b'line\n');connection.close()
        assert reader.readline(16)==b'line\n'
        reader.close();reader=None
        with pytest.raises(OSError):os.fstat(old)
    finally:
        if reader is not None:reader.close()
        left.close();right.close()


@pytest.mark.parametrize('fault',['remember','reused','no_close','close_after'])
def test_actual_owned_pair_partial_close_and_fd_reuse_remain_unknown(monkeypatch,fault):
    left,right=socket.socketpair();handle=P.DiagnosticHandle('accepted')
    try:
        if fault=='remember':
            original=os.fstat
            def denied(fd):
                if fd==left.fileno():raise OSError(errno.EIO,'owned birth metadata failure')
                return original(fd)
            with monkeypatch.context() as patch:
                patch.setattr(P.os,'fstat',denied)
                with pytest.raises(OSError):handle.remember(left)
            with pytest.raises(OSError):handle.close()
            assert not handle.closed and left.fileno()>=0
        elif fault=='reused':
            handle.remember(left);old=left.detach();os.close(old);r,w=os.pipe()
            try:
                with pytest.raises(OSError):handle.close()
                assert os.fstat(r) and os.fstat(w) and not handle.closed
            finally:os.close(r);os.close(w)
        else:
            def bad_close():
                if fault=='close_after':left.close();raise OSError('owned close receipt failure')
            wrapper=SimpleNamespace(fileno=left.fileno,close=bad_close);handle.remember(wrapper)
            with pytest.raises(OSError):handle.close()
            assert handle.uncertain and not handle.closed
    finally:left.close();right.close()


def test_sticky_first_failure_and_unknown_resources_survive_later_gone():
    controller=P.Controller({'head':'a'*40},None,None);controller._phase='stock_base';controller._mark('helper_ready',command='helper');controller._capture(P.ProbeFailure('HTTP'))
    first=copy.deepcopy(controller.result['first_failure']);controller._diag_uncertain();controller.result['resources']['forced']=True
    controller._phase='cleanup';controller._capture(OSError(errno.EIO,'redacted'))
    assert controller.result['first_failure']==first and controller._first_reason=='HTTP'
    assert controller.result['diagnostic_resources']['uncertain'] and controller.result['resources']['forced']


def test_v4_positive_and_contradictions_stay_closed_and_bounded():
    from .test_systemd_credential_metadata import _complete_policy_receipt
    value=_complete_policy_receipt(P);raw=P.validate_receipt(value);assert len(raw)<=32768
    assert P.validate_receipt(P.strict_json(raw))==raw
    for key,bad in [('ready_observed',False),('health',P.empty_health()),('helper_returncode',78),('frames',8),('deadline_reached',True)]:
        broken=copy.deepcopy(value);broken['startup_diagnostics']['stock_base'][key]=bad
        with pytest.raises(P.ProbeFailure):P.validate_receipt(broken)
    for bad in ({'raw_stderr':'forbidden'},{'binding':'UNPROVED','code':'APP_IMPORT_FAILED'},{'receive_buffer':32769}):
        broken=copy.deepcopy(value);broken['startup_diagnostics']['stock_base']['formal'].update(bad)
        with pytest.raises(P.ProbeFailure):P.validate_receipt(broken)
    old=copy.deepcopy(P.empty_receipt('a'*40));old.pop('startup_diagnostics');old.pop('diagnostic_resources');old['protocol']='native-linux-lifecycle-probe-v3'
    with pytest.raises(P.ProbeFailure):P.validate_receipt(old)


def test_startup_writer_emits_only_bounded_protocol_on_owned_pipe(monkeypatch):
    readfd,writefd=os.pipe();clock=F.time.monotonic()+2
    try:
        with monkeypatch.context() as patch:
            patch.setattr(F.sys,'stdout',SimpleNamespace(fileno=lambda:writefd))
            writer=F.StartupWriter(clock)
            for stage in F.STARTUP_STAGES[:-1]:writer.emit(stage,ready_health() if stage=='READY' else None)
        os.close(writefd);writefd=None
        raw=os.read(readfd,8193);decoder=P.StartupFrames();decoder.feed(raw);decoder.finish()
        assert len(raw)<=8192 and decoder.terminal=='READY' and decoder.count==7
    finally:
        os.close(readfd)
        if writefd is not None:os.close(writefd)


def test_partial_socket_constructor_is_retained_and_cannot_become_closed(monkeypatch):
    controller=P.Controller({'head':'a'*40},None,None);controller._diag={'listener':None}
    class Partial:
        def __init__(self,*args):self.fd=500;raise OSError(errno.EIO,'owned partial constructor')
        def fileno(self):return self.fd
        def close(self):self.fd=-1
    def information(fd):
        if fd!=500:raise OSError(errno.EBADF,'gone')
        if controller._diag_handles[0].obj.fileno()==-1:raise OSError(errno.EBADF,'gone')
        return SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFSOCK)
    with monkeypatch.context() as patch:
        patch.setattr(P.socket,'socket',Partial);patch.setattr(P.socket,'SOCK_CLOEXEC',0x80000,raising=False);patch.setattr(P.os,'fstat',information)
        with pytest.raises(OSError):controller._diag_new_socket()
        handle=controller._diag_handles[0]
        assert handle is controller._diag['listener'] and handle.born and handle.obj is not None
        with pytest.raises(OSError):handle.close()
    assert controller.result['diagnostic_resources']['listener_births']==1 and controller.result['diagnostic_resources']['uncertain']
    assert handle.uncertain and not handle.closed


def test_partial_bind_path_is_not_adopted_or_deleted(monkeypatch,tmp_path):
    left,right=socket.socketpair();controller=P.Controller({'head':'a'*40},SimpleNamespace(require=lambda **kw:1),None);controller._phase='stock_base'
    class BoundThenFailed:
        def __init__(self,*args):pass
        def fileno(self):return left.fileno()
        def setblocking(self,value):left.setblocking(value)
        def bind(self,path):Path(path).write_bytes(b'owned counter only');raise OSError(errno.EIO,'partial bind')
        def close(self):left.close()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(P,'OBSERVATION',tmp_path);patch.setattr(P.socket,'socket',BoundThenFailed);patch.setattr(P.socket,'SOCK_CLOEXEC',0x80000,raising=False)
            patch.setattr(controller,'_diag_directory_check',lambda:None)
            with pytest.raises(OSError):controller._diag_open()
            path=tmp_path/'stock_base.sock';assert path.exists()
            controller._diag_retire(True)
            assert path.exists() and controller.result['diagnostic_resources']['paths_removed']==0
            assert controller.result['diagnostic_resources']['uncertain']
    finally:left.close();right.close()


def test_accept_metadata_failure_keeps_the_actual_object_and_unknown(monkeypatch,tmp_path):
    left,right=socket.socketpair();accepted,other=socket.socketpair();controller=P.Controller({'head':'a'*40},None,None);controller._phase='stock_base'
    wrapper=SimpleNamespace(fileno=left.fileno,accept=lambda:(accepted,None),close=left.close)
    listener=P.DiagnosticHandle('listener');listener.remember(wrapper)
    path=tmp_path/'owned-path';path.write_bytes(b'finite path input')
    record=P.empty_startup_diagnostic()
    controller._diag={'phase':'stock_base','record':record,'path':path,'path_identity':P.stat_key(path.lstat()),'bind_attempted':True,'bound':True,'listener':listener,'peer':None,'credentials':None,'first_unit':None,'last_unit':None,'window_start':0,'window_end':1,'sampled':False,'stream':P.FormalCodeBytes()}
    controller._diag_handles=[listener];native=os.fstat
    def unavailable(fd):
        if fd==accepted.fileno():raise OSError(errno.EIO,'owned accepted identity failure')
        return native(fd)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(controller,'_diag_directory_check',lambda:None);patch.setattr(P.os,'fstat',unavailable)
            with pytest.raises(P.ProbeFailure):controller._diag_pump([wrapper])
        handle=controller._diag['peer']
        assert handle.obj is accepted and handle.born and handle.identity is None and handle.uncertain
        assert controller.result['diagnostic_resources']['accepted_births']==1 and not handle.closed
    finally:left.close();right.close();accepted.close();other.close()


def test_no_raw_or_unbounded_wait_is_added_to_existing_boundary():
    tree=ast.parse(Path(P.__file__).read_bytes());fixture=ast.parse(Path(F.__file__).read_bytes())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
    pump=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_diag_pump')
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('send','sendall') for n in ast.walk(pump))
    close=next(n for n in ast.walk(fixture) if isinstance(n,ast.FunctionDef) and n.name=='close' and any(isinstance(v,ast.Attribute) and v.attr=='servers' for v in ast.walk(n)))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='shutdown' for n in ast.walk(close))
    command=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='command')
    assert '.05' in ast.unparse(command) or '0.05' in ast.unparse(command)
    assert 'StandardOutput=null' in Path(P.__file__).read_text()


def test_four_maximum_diagnostics_and_full_acl_records_still_fit_original_32k():
    from .test_systemd_credential_metadata import _complete_policy_receipt
    value=_complete_policy_receipt(P);value.update(outcome='FAIL',reason='HTTP');value['phases']={phase:False for phase in P.PHASES}
    value['resources'].update(forced=True,cleanup_uncertain=True)
    for row in value['startup_diagnostics'].values():
        row.update(last_stage='FAILED',failed_at='HEALTH_WAIT',exception='OS_ERROR',errno=4095,parent_failure='HELPER_FAILED',helper_returncode=255,deadline_reached=True,ready_observed=False,frames=7,startup_bytes=8192)
        row['health']={'http_status':599,'base':'UNAVAILABLE','source_execute':'UNAVAILABLE','transport':'HTTP_ERROR'}
        row['formal'].update(code=max(P.FORMAL_CODES,key=len),close_code='FD_CLOSE_FAILED',stream='UNKNOWN_LINES',read_bytes=16383,unknown_lines=16000,receive_buffer=32768)
        unitrow={'active':'deactivating','result':'start-limit-hit','exit_kind':'OTHER','exit_status':255,'invocation_matches':True,'pid_matches':True,'start_matches':True,'start_elapsed_ms':300000,'exit_elapsed_ms':300000}
        row['unit_before']=dict(unitrow);row['unit_after']=dict(unitrow)
        assert len(P.canonical(row))<=2048
    # Add the seventh allowed fixed slot to base as a failed observation, so
    # every phase carries seven full ACL-shaped facts without claiming PASS.
    base=value['credential_metadata'][0];base['decision']='REJECT';base['check']='IO'
    extra=copy.deepcopy(base['objects'][-1]);extra['slot']=P.PROVIDER_ID;base['objects'].append(extra)
    raw=P.validate_receipt(value);assert len(raw)<=32768 and len(P.strict_json(raw)['startup_diagnostics'])==4


def test_single_unit_row_does_not_bind_and_later_epoch_change_revokes_code():
    controller=P.Controller({'head':'a'*40},None,None);stream=P.FormalCodeBytes();stream.feed(b'FORMAL_ENTRY:APP_IMPORT_FAILED\n')
    row=P.empty_startup_diagnostic();row['formal'].update(peer_root=True,receive_buffer=16384)
    controller._diag={'record':row,'credentials':(123,0,0),'first_unit':None,'last_unit':None,'window_start':.5,'window_end':None,'unit_count':0,'accepted_at_count':0,'stream':stream}
    controller._diag_note_unit(unit());assert row['formal']['binding']=='UNPROVED' and row['formal']['code'] is None
    controller._diag_note_unit(unit());assert row['formal']['binding']=='BOUND' and row['formal']['code']=='APP_IMPORT_FAILED'
    with pytest.raises(P.ProbeFailure):controller._diag_note_unit(unit(invocation='b'*32))
    assert row['formal']['binding']=='UNPROVED' and row['formal']['code'] is None and controller.result['diagnostic_resources']['uncertain']


def test_failure_snapshot_has_at_most_one_extra_show_and_preserves_primary():
    controller=P.Controller({'head':'a'*40},SimpleNamespace(require=lambda **kw:.5),None)
    row=P.empty_startup_diagnostic();controller._diag={'sampled':False,'record':row}
    calls=[];controller.unit_info=lambda **kw:calls.append(kw) or unit();controller._diag_unit_expected=lambda:None
    controller._phase='stock_base';controller._mark('helper_ready',command='helper');controller._capture(P.ProbeFailure('HTTP'))
    first=copy.deepcopy(controller.result['first_failure'])
    controller._diag_failure_snapshot();controller._diag_failure_snapshot()
    assert calls==[{'clean':True,'limit':.5}] and controller.result['first_failure']==first and controller._first_reason=='HTTP'


@pytest.mark.parametrize('fault',['deadline_after_accept','settimeout_failure','tls_wrap_failure'])
def test_accepted_http_socket_is_closed_before_initialization_error_escapes(monkeypatch,fault):
    left,right=socket.socketpair();fd=left.fileno();closed=[];calls=[]
    failure=OSError(errno.EIO,'finite owned initialization failure')
    class Accepted:
        def settimeout(self,value):
            calls.append('settimeout')
            if fault=='settimeout_failure':raise failure
            left.settimeout(value)
        def close(self):closed.append(True);left.close()
    def take():calls.append('accept');return Accepted(),None
    def wrap(*args,**kwargs):
        calls.append('wrap')
        if fault!='tls_wrap_failure':pytest.fail('initialization must fail before TLS')
        raise failure
    owner=SimpleNamespace(socket=SimpleNamespace(accept=take),io_deadline=1.0,tls=SimpleNamespace(wrap_socket=wrap))
    monkeypatch.setattr(F.time,'monotonic',lambda:2.0 if fault=='deadline_after_accept' else 0.0)
    try:
        with pytest.raises(F.FixtureFailure if fault=='deadline_after_accept' else OSError) as caught:
            F._OwnedHTTP.get_request(owner)
        if fault!='deadline_after_accept':assert caught.value is failure
        assert calls==({'deadline_after_accept':['accept'],'settimeout_failure':['accept','settimeout'],'tls_wrap_failure':['accept','settimeout','wrap']}[fault])
        # Observe candidate closure before the test's own finally retires pairs.
        assert closed==[True] and left.fileno()==-1
        with pytest.raises(OSError) as retired:os.fstat(fd)
        assert retired.value.errno==errno.EBADF
    finally:left.close();right.close()


@pytest.mark.parametrize('retire_first',[False,True])
def test_accepted_close_error_keeps_original_failure_and_sticky_owned_uncertainty(monkeypatch,retire_first):
    left,right=socket.socketpair();fd=left.fileno();calls=[];closed=[];server_closed=[]
    primary=F.FixtureFailure('CLOCK');secondary=OSError(errno.EIO,'finite owned close receipt failure')
    class Accepted:
        def settimeout(self,value):pytest.fail('deadline must fail before timeout setter')
        def close(self):
            closed.append(True)
            if retire_first:left.close()
            raise secondary
    accepted=Accepted()
    def take():calls.append(True);return accepted,None
    def expired(*args):raise primary
    owner=SimpleNamespace(socket=SimpleNamespace(accept=take),io_deadline=1.0,worker_uncertain=False,
                          server_close=lambda:server_closed.append(True))
    monkeypatch.setattr(F,'absolute_remaining',expired)
    try:
        with pytest.raises(F.FixtureFailure) as caught:F._OwnedHTTP.get_request(owner)
        assert caught.value is primary and caught.value.args==('CLOCK',)
        assert owner.worker_uncertain and owner._unretired_accepted is accepted
        assert owner._BaseServer__shutdown_request is True and closed==[True]
        if retire_first:
            assert left.fileno()==-1
            with pytest.raises(OSError) as gone:os.fstat(fd)
            assert gone.value.errno==errno.EBADF
        else:assert left.fileno()==fd and os.fstat(fd)
        # No fresh accept or close retry, even after the test physically retires
        # a socket whose candidate close failed. Late retirement cannot prove it.
        for late_retirement in (False,True):
            if late_retirement:left.close()
            with pytest.raises(F.FixtureFailure,match='CLEANUP'):F._OwnedHTTP.get_request(owner)
            assert calls==[True] and closed==[True]
            assert owner.worker_uncertain and owner._unretired_accepted is accepted
        service=object.__new__(F.LocalService)
        service.ready=False;service.ready_deadline=3;service.servers=[owner];service.threads=[]
        monkeypatch.setattr(F.time,'monotonic',lambda:2.0)
        with pytest.raises(F.FixtureFailure,match='CLEANUP'):service.close()
        assert server_closed==[True] and closed==[True]
        assert owner.worker_uncertain and owner._unretired_accepted is accepted
    finally:left.close();right.close()


def test_identity_v5_default_is_unknown_and_primary_annotation_is_separate():
    assert P.empty_receipt('a'*40)['protocol']=='native-linux-lifecycle-probe-v5'
    assert P.empty_startup_diagnostic()['formal']['identity'] is None
    stream=P.FormalCodeBytes()
    stream.feed(b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\nFORMAL_IDENTITY_V1:SRC_ROOT:0:2\nFORMAL_ENTRY:FD_CLOSE_FAILED\n')
    stream.finish()
    assert stream.codes==['CODE_IDENTITY_INVALID','FD_CLOSE_FAILED']
    assert stream.identity=={'site':'SRC_ROOT','component_index':0,'predicate_mask':2}


def identity_wire(site='SRC_COMPONENT',component='1',mask='2'):
    return ('FORMAL_IDENTITY_V1:'+site+':'+component+':'+mask+'\n').encode('ascii')


@pytest.mark.parametrize('split',[1,2,17,128,1024])
def test_identity_stream_fragmentation_keeps_two_codes_and_separate_identity(split):
    wire=b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n'+identity_wire()+b'FORMAL_ENTRY:FD_CLOSE_FAILED\n'
    stream=P.FormalCodeBytes()
    for offset in range(0,len(wire),split):stream.feed(wire[offset:offset+split])
    stream.finish()
    assert stream.state=='EOF' and stream.codes==['CODE_IDENTITY_INVALID','FD_CLOSE_FAILED']
    assert stream.identity=={'site':'SRC_COMPONENT','component_index':1,'predicate_mask':2}


@pytest.mark.parametrize('fault',['before','other_primary','duplicate','after_close','noise_between','unknown_site','bad_version','extra_field','zero_mask','wrong_bit','bool_mask','negative','plus','leading_zero','root_index','component_zero','component32','non_src_index','non_src_mask','truncated','line_limit','read_limit'])
def test_identity_invalid_stream_never_projects_a_site_or_replaces_primary(fault):
    primary=b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n';annotation=identity_wire()
    wire=primary+annotation
    if fault=='before':wire=annotation+primary
    elif fault=='other_primary':wire=b'FORMAL_ENTRY:APP_IMPORT_FAILED\n'+annotation
    elif fault=='duplicate':wire+=annotation
    elif fault=='after_close':wire=primary+b'FORMAL_ENTRY:FD_CLOSE_FAILED\n'+annotation
    elif fault=='noise_between':wire=primary+b'noise\n'+annotation
    elif fault=='unknown_site':wire=primary+identity_wire('OTHER')
    elif fault=='bad_version':wire=primary+annotation.replace(b'_V1:',b'_V2:')
    elif fault=='extra_field':wire=primary+annotation[:-1]+b':extra\n'
    elif fault=='zero_mask':wire=primary+identity_wire(mask='0')
    elif fault=='wrong_bit':wire=primary+identity_wire(mask='16')
    elif fault=='bool_mask':wire=primary+identity_wire(mask='True')
    elif fault=='negative':wire=primary+identity_wire(component='-1')
    elif fault=='plus':wire=primary+identity_wire(component='+1')
    elif fault=='leading_zero':wire=primary+identity_wire(component='01')
    elif fault=='root_index':wire=primary+identity_wire('SRC_ROOT','1','2')
    elif fault=='component_zero':wire=primary+identity_wire(component='0')
    elif fault=='component32':wire=primary+identity_wire(component='32')
    elif fault=='non_src_index':wire=primary+identity_wire('HELPER_MODULE','1','-')
    elif fault=='non_src_mask':wire=primary+identity_wire('HELPER_MODULE','-','2')
    elif fault=='truncated':wire=wire[:-1]
    elif fault=='line_limit':wire+=b'x'*129
    stream=P.FormalCodeBytes()
    with pytest.raises(ValueError):
        if fault=='read_limit':
            stream.feed(wire)
            for _ in range(256):stream.feed(b'x\n'*32)
        else:
            for offset in range(0,len(wire),37):stream.feed(wire[offset:offset+37])
            stream.finish()
    assert stream.identity is None
    if fault not in ('before',):assert stream.codes[0]==('APP_IMPORT_FAILED' if fault=='other_primary' else 'CODE_IDENTITY_INVALID')
    assert len(stream.codes)<=2


@pytest.mark.parametrize('site',P.IDENTITY_SITES)
def test_identity_null_source_inputs_remain_unknown_and_sites_are_closed(site):
    item={'site':site,'component_index':None,'predicate_mask':None}
    assert P.validate_identity(item)==item
    assert P.parse_identity_line(identity_wire(site,'-','-'))==item
    assert len(identity_wire(site,'-','-'))<=128


def test_identity_schema_bound_primary_phase_and_exact_keys():
    from .test_systemd_credential_metadata import _complete_policy_receipt
    value=_complete_policy_receipt(P);value.update(outcome='FAIL',reason='HTTP');value['phases']={phase:False for phase in P.PHASES}
    formal=value['startup_diagnostics']['stock_base']['formal']
    formal.update(code='CODE_IDENTITY_INVALID',identity={'site':'SRC_COMPONENT','component_index':1,'predicate_mask':2})
    P.validate_receipt(value)
    for change in ({'binding':'UNPROVED'},{'code':'APP_IMPORT_FAILED'},{'stream':'IDENTITY_INVALID'},
                   {'identity':{'site':'SRC_ROOT','component_index':True,'predicate_mask':2}},
                   {'identity':{'site':'SRC_COMPONENT','component_index':1,'predicate_mask':False}},
                   {'identity':{'site':'HELPER_MODULE','component_index':None,'predicate_mask':1}},
                   {'identity':{'site':'SRC_ROOT','component_index':0,'predicate_mask':2,'raw':'forbidden'}}):
        bad=copy.deepcopy(value);bad['startup_diagnostics']['stock_base']['formal'].update(change)
        with pytest.raises(P.ProbeFailure):P.validate_receipt(bad)
    bad=copy.deepcopy(value);bad['phases']['stock_base']=True
    with pytest.raises(P.ProbeFailure):P.validate_receipt(bad)
    bad=copy.deepcopy(value);bad['protocol']='native-linux-lifecycle-probe-v4'
    with pytest.raises(P.ProbeFailure):P.validate_receipt(bad)
    bad=copy.deepcopy(value);bad['startup_diagnostics']['stock_base']['formal'].pop('identity')
    with pytest.raises(P.ProbeFailure):P.validate_receipt(bad)


def test_identity_binding_requires_both_samples_and_epoch_loss_clears_every_code():
    controller=P.Controller({'head':'a'*40},None,None);stream=P.FormalCodeBytes()
    stream.feed(b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n'+identity_wire()+b'FORMAL_ENTRY:FD_CLOSE_FAILED\n');stream.finish()
    row=P.empty_startup_diagnostic();row['formal'].update(peer_root=True,receive_buffer=16384)
    controller._diag={'record':row,'credentials':(123,0,0),'first_unit':None,'last_unit':None,'window_start':.5,'window_end':None,'unit_count':0,'accepted_at_count':0,'stream':stream}
    controller._diag_note_unit(unit());assert row['formal']['identity'] is None and row['formal']['code'] is None
    controller._diag_note_unit(unit());assert row['formal']['identity']==stream.identity
    first=copy.deepcopy(controller.result['first_failure'])
    with pytest.raises(P.ProbeFailure):controller._diag_note_unit(unit(invocation='b'*32))
    assert row['formal']['identity'] is None and row['formal']['code'] is None and row['formal']['close_code'] is None
    assert stream.identity is None and controller.result['diagnostic_resources']['uncertain']
    assert controller.result['first_failure'] is not None or first is not None


def test_four_identity_diagnostics_fit_original_caps_without_success_claim():
    from .test_systemd_credential_metadata import _complete_policy_receipt
    value=_complete_policy_receipt(P);value.update(outcome='FAIL',reason='HTTP');value['phases']={phase:False for phase in P.PHASES}
    value['resources'].update(forced=True,cleanup_uncertain=True);value['diagnostic_resources']['uncertain']=True
    for row in value['startup_diagnostics'].values():
        row.update(last_stage='FAILED',failed_at='HEALTH_WAIT',exception='OS_ERROR',errno=4095,parent_failure='HELPER_FAILED',helper_returncode=255,deadline_reached=True,ready_observed=False,frames=7,startup_bytes=8192)
        row['health']={'http_status':599,'base':'UNAVAILABLE','source_execute':'UNAVAILABLE','transport':'HTTP_ERROR'}
        row['formal'].update(code='CODE_IDENTITY_INVALID',close_code='FD_CLOSE_FAILED',stream='UNKNOWN_LINES',read_bytes=16383,unknown_lines=16000,receive_buffer=32768,identity={'site':'SRC_READBACK','component_index':31,'predicate_mask':192})
        unitrow={'active':'deactivating','result':'start-limit-hit','exit_kind':'OTHER','exit_status':255,'invocation_matches':True,'pid_matches':True,'start_matches':True,'start_elapsed_ms':300000,'exit_elapsed_ms':300000}
        row['unit_before']=dict(unitrow);row['unit_after']=dict(unitrow)
        assert len(P.canonical(row))<=2048
    base=value['credential_metadata'][0];base['decision']='REJECT';base['check']='IO'
    extra=copy.deepcopy(base['objects'][-1]);extra['slot']=P.PROVIDER_ID;base['objects'].append(extra)
    raw=P.validate_receipt(value);assert len(raw)<=32768
    assert P.strict_json(raw)['resources']['forced'] and P.strict_json(raw)['resources']['cleanup_uncertain']


def test_identity_format_fault_clears_public_slot_and_preserves_first_failure():
    controller=P.Controller({'head':'a'*40},None,None);stream=P.FormalCodeBytes()
    stream.feed(b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n'+identity_wire())
    row=P.empty_startup_diagnostic();row['formal'].update(binding='BOUND',code='CODE_IDENTITY_INVALID',identity=stream.identity,stream='OPEN')
    controller._diag={'record':row,'stream':stream};controller._phase='stock_base'
    controller._mark('helper_ready',command='helper');controller._capture(P.ProbeFailure('HTTP'))
    first=copy.deepcopy(controller.result['first_failure'])
    with pytest.raises(ValueError):stream.feed(identity_wire())
    with pytest.raises(P.ProbeFailure):controller._diag_fault('IDENTITY_INVALID')
    assert row['formal']['identity'] is None and row['formal']['code']=='CODE_IDENTITY_INVALID'
    assert stream.identity is None and row['formal']['stream']=='IDENTITY_INVALID'
    assert controller.result['first_failure']==first and controller.result['diagnostic_resources']['uncertain']


@pytest.mark.parametrize('noise',[b'',b'finite-noise\n'])
@pytest.mark.parametrize('clean',[False,True])
@pytest.mark.parametrize('fragmented',[False,True])
def test_invalid_identity_in_same_read_preserves_bound_primary(monkeypatch,tmp_path,noise,clean,fragmented):
    left,right=socket.socketpair();controller=P.Controller({'head':'a'*40},None,None)
    path=tmp_path/'owned-stream-path';path.write_bytes(b'finite owned input')
    stream=P.FormalCodeBytes();row=P.empty_startup_diagnostic();row['formal'].update(peer_root=True,receive_buffer=16384,stream='OPEN')
    controller.result['startup_diagnostics']['stock_base']=row
    peer=P.DiagnosticHandle('accepted');peer.remember(left)
    controller._diag={'record':row,'path':path,'path_identity':P.stat_key(path.lstat()),'listener':None,'peer':peer,
                      'credentials':(123,0,0),'first_unit':unit(),'last_unit':unit(),'window_start':.5,'window_end':2,
                      'unit_count':2,'accepted_at_count':0,'stream':stream}
    monkeypatch.setattr(controller,'_diag_directory_check',lambda:None)
    controller._phase='stock_base';controller._mark('helper_ready',command='helper');controller._capture(P.ProbeFailure('HTTP'))
    first=copy.deepcopy(controller.result['first_failure'])
    try:
        primary=noise+b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n';annotation=identity_wire('UNKNOWN');wire=primary+annotation
        if fragmented:
            right.sendall(primary);controller._diag_pump([left],clean=clean)
            assert row['formal']['read_bytes']==len(primary) and row['formal']['unknown_lines']==int(bool(noise))
            right.sendall(annotation)
        else:right.sendall(wire)
        if clean:controller._diag_pump([left],clean=True)
        else:
            with pytest.raises(P.ProbeFailure):controller._diag_pump([left])
        assert row['formal']['code']=='CODE_IDENTITY_INVALID' and row['formal']['identity'] is None
        assert row['formal']['stream']=='IDENTITY_INVALID' and controller.result['first_failure']==first
        assert stream.total==len(wire) and stream.unknown==int(bool(noise))
        assert row['formal']['read_bytes']==stream.total and row['formal']['unknown_lines']==stream.unknown
        assert controller.result['diagnostic_resources']['uncertain']
        assert P.validate_receipt(controller.result)
    finally:left.close();right.close()


def test_identity_closed_bitsets_and_integer_types_exhaust_original_byte_range():
    for site,allowed in P.IDENTITY_MASKS.items():
        for mask in range(256):
            value={'site':site,'component_index':0 if site=='SRC_ROOT' else 1,'predicate_mask':mask}
            if mask and not mask & ~allowed:assert P.validate_identity(value)==value
            else:
                with pytest.raises(ValueError):P.validate_identity(value)
        for component in (False,True,-1,32,1.0,'1'):
            value={'site':site,'component_index':component,'predicate_mask':None}
            with pytest.raises(ValueError):P.validate_identity(value)
    for value in (False,True,[],{}, {'site':'SRC_ROOT','component_index':0,'predicate_mask':True}):
        with pytest.raises(ValueError):P.validate_identity(value)
