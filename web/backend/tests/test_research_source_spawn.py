"""Source exec boundaries; synthetic environment and owned local resources only."""
import json
import os
import functools
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest

from web.backend.research.authorization import AuthorizationGate
from web.backend.research import source_policy,source_spawn

SENSITIVE_NAMES=('JWT_SECRET','STRUCTURAL_SSO_SECRET','STRUCTURAL_PRIVACY_HMAC_KEY','SMTP_PASSWORD')


def _observe_worker(target, forbidden_identity=None):
    # Return names and file kinds only, never environment values or file bytes.
    import stat
    observed={'inherited_sensitive_names':[name for name in SENSITIVE_NAMES if name in os.environ],
        'environment_names':sorted(os.environ),
        'stdio_character_devices':[stat.S_ISCHR(os.fstat(fd).st_mode) for fd in (0,1,2)],
        'inherited_business_fds':[]}
    for fd in range(3,256):
        try:info=os.fstat(fd)
        except OSError:continue
        if (info.st_dev,info.st_ino)==forbidden_identity:observed['inherited_business_fds'].append(fd)
    raw=json.dumps(observed).encode()
    return 200,'application/json',raw,raw


def _blocked_worker(target):
    time.sleep(10)
    return 200,'text/plain',b'late',b'late'


def _failing_worker(target):
    raise OSError('synthetic Source body failure')


def _parent_liveness_worker(target):
    import multiprocessing
    parent=multiprocessing.parent_process()
    raw=json.dumps({'alive':parent.is_alive(),'parent_pid':parent.pid,'actual_parent_pid':os.getppid()}).encode()
    return 200,'application/json',raw,raw


def _ignore_term_worker(ready,target):
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    Path(ready).write_text('sender armed')
    time.sleep(10)
    return 200,'text/plain',b'late',b'late'


def _observe_exec(monkeypatch):
    original=source_spawn.subprocess.Popen;records=[]
    def execute(command,**kwargs):
        process=original(command,**kwargs)
        records.append((process,command,kwargs))
        return process
    monkeypatch.setattr(source_spawn.subprocess,'Popen',execute)
    return records


def _get(tmp_path,worker=_observe_worker,*,wall=12,authorized=lambda:True):
    gate=AuthorizationGate(SimpleNamespace(path=tmp_path/'unused.sqlite3'))
    with gate.owner_gate_id(str(uuid4())) as owner:
        return source_policy.PinnedPublicTransport(wall_seconds=wall,_worker=worker).get(
            source_policy.article_target('10.1371/journal.pone.0015032'),still_authorized=authorized,owner_lease=owner)


def _assert_retired(records):
    assert len(records)==2
    assert all(process.poll() is not None for process,_,_ in records)
    assert all(kwargs['env']=={'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1'} for _,_,kwargs in records)
    assert all(kwargs['close_fds'] is True and kwargs['stdin']==kwargs['stdout']==kwargs['stderr']==subprocess.DEVNULL for _,_,kwargs in records)
    assert not source_spawn._UNCERTAIN


def test_sender_exec_starts_without_sensitive_environment(tmp_path,monkeypatch):
    from multiprocessing import resource_tracker
    original_tracker=(resource_tracker._resource_tracker._pid,resource_tracker._resource_tracker._fd)
    monkeypatch.setenv('STRUCTURAL_ENV','test')
    for name in SENSITIVE_NAMES:monkeypatch.setenv(name,'synthetic-spawn-sentinel')
    records=_observe_exec(monkeypatch)
    witness=tmp_path/'business-file';witness.write_bytes(b'synthetic')
    fd=os.open(witness,os.O_RDONLY);os.set_inheritable(fd,True)
    try:
        info=os.fstat(fd)
        response=_get(tmp_path,functools.partial(_observe_worker,forbidden_identity=(info.st_dev,info.st_ino)))
    finally:os.close(fd)
    observed=json.loads(response[2])
    assert observed['inherited_sensitive_names']==[]
    platform_names={'__CF_USER_TEXT_ENCODING'} if sys.platform=='darwin' else set()
    assert set(observed['environment_names'])<={'PYTHONDONTWRITEBYTECODE','PYTHONUTF8','LC_CTYPE'}|platform_names
    assert observed['stdio_character_devices']==[True,True,True]
    assert observed['inherited_business_fds']==[]
    assert all(os.environ[name]=='synthetic-spawn-sentinel' for name in SENSITIVE_NAMES)
    _assert_retired(records)
    assert 'multiprocessing.resource_tracker' in records[0][1][-1]
    assert len(records[0][2]['pass_fds'])==1
    assert len(records[1][2]['pass_fds'])==5  # tracker, RawArray, duplex channel, payload, sentinel
    assert (resource_tracker._resource_tracker._pid,resource_tracker._resource_tracker._fd)==original_tracker


def test_owned_loopback_response_crosses_standard_rawarray_and_retires_each_tracker(tmp_path,monkeypatch):
    from web.backend.tests.source_http_fixture import source_server,get_local,METADATA,ARTICLE
    records=_observe_exec(monkeypatch)
    gate=AuthorizationGate(SimpleNamespace(path=tmp_path/'unused.sqlite3'))
    with source_server() as (port,calls),gate.owner_gate_id(str(uuid4())) as owner:
        transport=source_policy.PinnedPublicTransport(_worker=functools.partial(get_local,port))
        for target,expected in ((source_policy.discovery_target('queue theory'),METADATA),
                (source_policy.article_target('10.1371/journal.pone.0015032'),ARTICLE)):
            result=transport.get(target,still_authorized=lambda:True,owner_lease=owner)
            assert result[0]==200 and result[2]==result[3]==expected
        assert calls==['/discovery','/article']
        assert transport.execution_mode=='offline_probe'
    _assert_retired(records[:2]);_assert_retired(records[2:])
    assert records[0][0].pid!=records[2][0].pid


def test_sender_exec_failure_retires_already_born_tracker(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);original=source_spawn._exec
    def execute(command,descriptors):
        if len(records)==1:raise OSError('synthetic sender exec failure')
        return original(command,descriptors)
    monkeypatch.setattr(source_spawn,'_exec',execute)
    with pytest.raises(OSError,match='synthetic sender exec failure'):_get(tmp_path)
    assert len(records)==1 and records[0][0].poll() is not None
    assert not source_spawn._UNCERTAIN


@pytest.mark.parametrize('end',['stop','deadline'])
def test_sender_stop_or_deadline_reaps_both_processes(tmp_path,monkeypatch,end):
    records=_observe_exec(monkeypatch);started=time.monotonic()
    def authorized():return end!='stop' or time.monotonic()-started<.25
    with pytest.raises((PermissionError,source_policy.SourceFailure)):
        _get(tmp_path,_blocked_worker,wall=.45,authorized=authorized)
    _assert_retired(records)


def test_tracker_close_after_real_close_is_uncertain_and_sender_still_reaped(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);original=source_spawn._Tracker._close_fd;fault=[]
    def close(self,fd):
        is_writer=fd==self.fd
        original(self,fd)
        if is_writer and not fault:
            fault.append(fd);raise OSError('synthetic post-close observation failure')
    monkeypatch.setattr(source_spawn._Tracker,'_close_fd',close)
    try:
        with pytest.raises(source_spawn.SourceCleanupUncertain):_get(tmp_path)
        assert len(records)==2 and all(process.poll() is not None for process,_,_ in records)
        assert fault and source_spawn._UNCERTAIN
        with pytest.raises(OSError):os.fstat(fault[0])
    finally:
        # All physical resources above are confirmed retired; keep no false
        # operational authority from this test's intentionally uncertain record.
        source_spawn._UNCERTAIN.clear()


def test_sender_fd_close_failure_still_attempts_tracker_and_other_fds(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);original=source_spawn._SourcePopen._close_fd;fault=[]
    def close(self,fd):
        is_sentinel=fd==self.sentinel
        original(self,fd)
        if is_sentinel and not fault:
            fault.append(fd);raise OSError('synthetic sender post-close failure')
    monkeypatch.setattr(source_spawn._SourcePopen,'_close_fd',close)
    try:
        with pytest.raises(source_spawn.SourceCleanupUncertain):_get(tmp_path)
        assert len(records)==2 and all(process.poll() is not None for process,_,_ in records)
        assert fault and source_spawn._UNCERTAIN
        with pytest.raises(OSError):os.fstat(fault[0])
    finally:source_spawn._UNCERTAIN.clear()


def test_primary_error_keeps_cleanup_uncertainty_metadata(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);original=source_spawn._Tracker._close_fd;fault=[]
    def close(self,fd):
        writer=fd==self.fd
        original(self,fd)
        if writer and not fault:
            fault.append(fd);raise OSError('synthetic post-close failure')
    monkeypatch.setattr(source_spawn._Tracker,'_close_fd',close)
    try:
        with pytest.raises(source_policy.SourceFailure) as failure:_get(tmp_path,_failing_worker)
        assert failure.value._source_cleanup_uncertainty==('Source transport retirement uncertain',)
        assert fault and source_spawn._UNCERTAIN
        assert len(records)==2 and all(process.poll() is not None for process,_,_ in records)
        with pytest.raises(OSError):os.fstat(fault[0])
    finally:source_spawn._UNCERTAIN.clear()


def test_stop_kills_sender_ignoring_term_then_retires_tracker(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);ready=tmp_path/'ready'
    with pytest.raises(PermissionError):
        _get(tmp_path,functools.partial(_ignore_term_worker,str(ready)),wall=2,authorized=lambda:not ready.exists())
    _assert_retired(records)
    assert records[1][0].returncode==-signal.SIGKILL


def test_live_factory_requires_fixed_source_target_without_network():
    process=source_spawn.source_process((None,None,source_policy._network_get,None,0,None))
    try:assert process._target is source_policy._child
    finally:process.close()


def test_missing_spawn_mechanism_closes_before_exec(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch)
    monkeypatch.setattr(source_spawn.reduction,'HAVE_SEND_HANDLE',False)
    with pytest.raises(RuntimeError,match='unavailable'):_get(tmp_path)
    assert records==[]


def test_real_parent_liveness_and_parent_pipe_retirement(tmp_path,monkeypatch):
    records=_observe_exec(monkeypatch);original=source_spawn._SourcePopen.retire;descriptors=[]
    def retire(self):
        if not descriptors:
            assert len(self._owned_fds)==2
            descriptors.extend(self._owned_fds)
            for fd in descriptors:os.fstat(fd)
        return original(self)
    monkeypatch.setattr(source_spawn._SourcePopen,'retire',retire)
    value=json.loads(_get(tmp_path,_parent_liveness_worker)[2])
    assert value=={'alive':True,'parent_pid':os.getpid(),'actual_parent_pid':os.getpid()}
    _assert_retired(records)
    for fd in descriptors:
        with pytest.raises(OSError):os.fstat(fd)


def test_fixture_cannot_be_relabelled_live(tmp_path):
    transport=source_policy.PinnedPublicTransport(_worker=_observe_worker);transport.execution_mode='live'
    gate=AuthorizationGate(SimpleNamespace(path=tmp_path/'unused.sqlite3'))
    with gate.owner_gate_id(str(uuid4())) as owner:
        with pytest.raises(source_policy.SourceFailure,match='provenance'):
            transport.get(source_policy.article_target('10.1371/journal.pone.0015032'),still_authorized=lambda:True,owner_lease=owner)


def test_original13_source_policy_is_reconstructed_exactly():
    import hashlib
    from web.backend.tests.method_v13_reference import historical_bytes
    root=Path(__file__).resolve().parents[3]
    manifest=json.loads((root/'web/backend/tests/reference/method_v13/manifest.json').read_text())
    relative='web/backend/research/source_policy.py'
    expected=manifest['cases']['native']['files'][relative]['sha256']
    assert hashlib.sha256(historical_bytes(root,relative,expected)).hexdigest()==expected
