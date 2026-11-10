"""Synthetic files/processes only: never sudo, APT, network or a browser."""
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import time
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_chromium_candidate', ROOT/'scripts/prepare_ci_chromium.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
SOURCE = (b'# original comment\nTypes: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\n'
          b'Suites: noble noble-updates noble-backports noble-security\n'
          b'Components: main restricted universe multiverse\n'
          b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')


def synthetic_source_pin(monkeypatch, raw):
    # Explicit synthetic complete-input pin; never a claimed native 2995B sample.
    monkeypatch.setattr(setup,'SOURCE_PROFILE_BYTES',len(raw),raising=False)
    monkeypatch.setattr(setup,'SOURCE_PROFILE_SHA',hashlib.sha256(raw).hexdigest(),raising=False)


def test_exact_synthetic_source_pin_maps_opaque_tokens_only_to_independent_fixed_target(monkeypatch):
    first=SOURCE.replace(b'http://azure.archive.ubuntu.com/ubuntu/',b'UNTRUSTED_SECRET_TOKEN_A').replace(
        b'noble noble-updates noble-backports noble-security',b'noble noble-updates noble-backports')
    second=SOURCE.replace(b'http://azure.archive.ubuntu.com/ubuntu/',b'UNTRUSTED_SECRET_TOKEN_B/').replace(
        b'noble noble-updates noble-backports noble-security',b'noble-security')
    raw=first+b'\n'+second;synthetic_source_pin(monkeypatch,raw)
    rendered=setup.mirror_source(raw)
    assert rendered == raw.replace(b'UNTRUSTED_SECRET_TOKEN_A',b'https://archive.ubuntu.com/ubuntu').replace(
        b'UNTRUSTED_SECRET_TOKEN_B/',b'https://archive.ubuntu.com/ubuntu')
    assert b'UNTRUSTED_SECRET' not in rendered
    with pytest.raises(setup.Refused):setup.mirror_source(raw+b'# unpinned\n')


@pytest.mark.parametrize('change',[
    (b'Types: deb',b'Types: deb-src'),(b'Suites: noble ',b'Suites: unknown '),
    (b'Components: main ',b'Components: unknown '),
    (b'Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg',b'Signed-By: unknown'),
    (b'Types: deb',b'Types: deb\nTypes: deb'),(b'Types: deb',b'Unknown: yes\nTypes: deb'),
    (b'Types: deb',b' Types: deb'),(b'OPAQUE_SECRET',b'OPAQUE_SECRET SECOND'),
    (b'# original comment',b'# original\rcomment'),(b'# original comment',b'# original\x00comment'),
])
def test_pinned_source_still_runs_every_strict_field_predicate_without_leaking(monkeypatch,change):
    raw=SOURCE.replace(b'http://azure.archive.ubuntu.com/ubuntu/',b'OPAQUE_SECRET').replace(*change)
    synthetic_source_pin(monkeypatch,raw)
    with pytest.raises(setup.Refused) as error:setup.mirror_source(raw)
    assert 'OPAQUE_SECRET' not in str(error.value)


@pytest.mark.parametrize('mutation',['none','extra','phase','stage','status','duplicate','code','bool_code'])
def test_parent_projects_only_closed_failure_from_returned_fake_child(tmp_path,monkeypatch,mutation):
    reply={'protocol':'ci-chromium-failure-v1','status':'UNKNOWN','failure_phase':'root-worker','failure_stage':'source'}
    code=2
    if mutation=='extra':reply['raw']='CANARY_SECRET'
    elif mutation in ('phase','stage','status'):reply['failure_'+mutation if mutation!='status' else 'status']='CANARY_SECRET'
    elif mutation=='code':code=1
    elif mutation=='bool_code':code=True
    raw=json.dumps(reply).encode()
    if mutation=='duplicate':raw=raw[:-1]+b',"failure_stage":"source"}'
    class Process:
        stdin=io.BytesIO();stdout=io.BytesIO(raw)
        def wait(self,timeout):return code
    monkeypatch.setattr(setup,'host_guard',lambda:None);monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    def launch(*_args, **kwargs):
        assert kwargs['stderr'] is setup.subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(setup.subprocess,'Popen',launch)
    with pytest.raises(setup.Refused) as error:setup.prepare()
    if mutation=='none':assert type(error.value) is setup.StagedFailure and error.value.value==reply
    else:assert type(error.value) is not setup.StagedFailure
    assert 'CANARY_SECRET' not in str(error.value) and len(list(tmp_path.iterdir()))==1


def test_main_keeps_success_exact_four_keys_and_failure_only_fixed_stages(monkeypatch,capsys):
    success={'status':'ready','children_closed':True,'source_restored':True,'keyring':fake_keyring_receipt()}
    monkeypatch.setattr(setup.sys,'argv',['fixed-helper']);monkeypatch.setattr(setup,'prepare',lambda:success)
    assert setup.main()==0 and json.loads(capsys.readouterr().out)==success
    def fail():
        setup.entering('parent','host');raise RuntimeError('CANARY_SECRET_PATH_URI')
    monkeypatch.setattr(setup,'prepare',fail)
    assert setup.main()==2
    value=json.loads(capsys.readouterr().out)
    assert setup.failure_valid(value,2) and value['failure_stage']=='host' and 'CANARY' not in json.dumps(value)


@pytest.mark.parametrize('invalid', [False, True])
def test_parent_reads_known_failed_diagnostic_only_through_bounded_json(tmp_path, monkeypatch, invalid):
    result = {'status':'failed','children_closed':True,'source_restored':True,'keyring':fake_keyring_receipt(),
              'installer':{'protocol':'ci-chromium-installer-v1','outcome':'deadline','observed_exit_code':None}}
    if invalid: result['installer']['raw'] = 'CANARY_SDK_STDERR'
    class Process:
        stdin=io.BytesIO();stdout=io.BytesIO(json.dumps(result).encode())
        def wait(self, timeout): return 1
    def launch(*_args, **kwargs):
        assert kwargs['stderr'] is setup.subprocess.DEVNULL
        return Process()
    monkeypatch.setattr(setup,'host_guard',lambda:None)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    monkeypatch.setattr(setup.subprocess,'Popen',launch)
    if invalid:
        with pytest.raises(setup.Refused) as error: setup.prepare()
        assert 'CANARY' not in str(error.value) and len(list(tmp_path.iterdir())) == 1
    else:
        assert setup.prepare() == result and list(tmp_path.iterdir()) == []


def fake_keyring_receipt():
    original={'dev':1,'ino':11,'uid':0,'gid':0,'mode':0o777,'nlink':1,'size':setup.KEYRING_BYTES,'sha256':setup.KEYRING_SHA}
    return {'profile':setup.KEYRING_PROFILE,'reference':'1'*32,'input_trust':'untrusted','original':original,
            'effective':{**original,'ino':12,'mode':0o644},'directory':{'dev':1,'ino':13,'uid':0,'gid':0,'mode':0o755,'nlink':2},
            'original_unchanged':True,'signed_by_bound':True,'retired':True}


@pytest.mark.parametrize('worker', [False, True])
@pytest.mark.parametrize('with_diagnostic', [False, True])
def test_main_preserves_known_install_failure_after_verified_retirement(monkeypatch, capsys, worker, with_diagnostic):
    result = {'status':'failed', 'children_closed':True, 'source_restored':True,
              'keyring':fake_keyring_receipt()}
    if with_diagnostic:
        result['installer'] = setup.installer_diagnostic('deadline', None)
    assert setup.keyring_receipt_ok(result['keyring'], bound=False)
    phase = 'root-worker' if worker else 'parent'

    def completed(*_args):
        setup.entering(phase, 'retirement')
        return result

    monkeypatch.setattr(setup.sys, 'argv', ['fixed-helper'] + (['--root-worker'] if worker else []))
    monkeypatch.setattr(setup, 'root_worker' if worker else 'prepare', completed)
    if worker:
        monkeypatch.setattr(setup.sys, 'stdin', io.TextIOWrapper(io.BytesIO(b'{}\n')))
    assert setup.main() == 1
    assert json.loads(capsys.readouterr().out) == result


@pytest.mark.parametrize('fault', ['children', 'source', 'keyring', 'extra', 'status',
    'installer-secret', 'installer-extra', 'installer-code', 'ready-extra'])
def test_main_does_not_project_unverified_failure_as_known_retired(monkeypatch, capsys, fault):
    result = {'status':'failed', 'children_closed':True, 'source_restored':True,
              'keyring':fake_keyring_receipt()}
    if fault == 'children': result['children_closed'] = False
    elif fault == 'source': result['source_restored'] = False
    elif fault == 'keyring': result['keyring']['retired'] = False
    elif fault == 'extra': result['raw'] = 'CANARY_SECRET_SDK_OUTPUT'
    elif fault == 'status': result['status'] = 'CANARY_SECRET_STATUS'
    else:
        result['installer'] = {'protocol':'ci-chromium-installer-v1','outcome':'deadline','observed_exit_code':None}
        if fault == 'installer-secret': result['installer']['outcome'] = 'CANARY_SECRET_SDK_OUTPUT'
        elif fault == 'installer-extra': result['installer']['raw'] = 'CANARY_SECRET_SDK_OUTPUT'
        elif fault == 'installer-code': result['installer']['observed_exit_code'] = False
        else: result['status'] = 'ready'
    monkeypatch.setattr(setup.sys, 'argv', ['fixed-helper'])
    monkeypatch.setattr(setup, 'prepare', lambda: result)
    assert setup.main() == 2
    value = json.loads(capsys.readouterr().out)
    assert setup.failure_valid(value, 2) and 'CANARY' not in json.dumps(value)


@pytest.mark.parametrize('outcome,code', [('completed',0), ('deadline',None), ('deadline',0),
    ('control-stop',None), ('control-stop',-9), ('nonzero-exit',1), ('nonzero-exit',255),
    ('launch-exception',None), ('loop-exception',None)])
def test_installer_diagnostic_has_only_finite_controller_data(outcome, code):
    assert setup.installer_diagnostic(outcome, code) == {
        'protocol':'ci-chromium-installer-v1', 'outcome':outcome, 'observed_exit_code':code}


@pytest.mark.parametrize('outcome,code', [('CANARY_SDK_OUTPUT',None), ('completed',None),
    ('completed',1), ('nonzero-exit',0), ('nonzero-exit',None), ('deadline',False),
    ('deadline',256), ('deadline',-256), ('deadline','CANARY_PATH'), ('loop-exception',1)])
def test_installer_diagnostic_rejects_untrusted_or_inconsistent_data(outcome, code):
    with pytest.raises(setup.Refused) as error:
        setup.installer_diagnostic(outcome, code)
    assert 'CANARY' not in str(error.value)


@pytest.fixture
def pinned_factory(tmp_path,monkeypatch):
    original=tmp_path/'original.gpg';raw=b'SYNTHETIC_APPROVED_PUBLIC_BYTES'.ljust(3607,b'x')
    original.write_bytes(raw);original.chmod(0o777)
    copies=tmp_path/'copies';copies.mkdir(mode=0o700)
    monkeypatch.setattr(setup,'KEYRING_SHA',__import__('hashlib').sha256(raw).hexdigest())
    monkeypatch.setattr(setup.os,'geteuid',lambda:0)
    monkeypatch.setattr(setup.PinnedArchiveKeyring,'_input_path',staticmethod(lambda:original))
    monkeypatch.setattr(setup.PinnedArchiveKeyring,'_parent_path',staticmethod(lambda:copies))
    native=setup.PinnedArchiveKeyring._info
    def root_info(path=None,fd=None):
        info=native(path=path,fd=fd)
        # Fake root ownership only; actual ordinary test files/FDs stay user-owned.
        return SimpleNamespace(**{name:getattr(info,name) for name in ('st_dev','st_ino','st_mode','st_nlink','st_size')},st_uid=0,st_gid=0)
    monkeypatch.setattr(setup.PinnedArchiveKeyring,'_info',staticmethod(root_info))
    resources=[]
    def create():
        item=setup.PinnedArchiveKeyring(time.monotonic()+100);resources.append(item);return item
    yield SimpleNamespace(original=original,raw=raw,copies=copies,create=create)
    for item in resources:
        try:
            if item.active:item.retire(True,True,False)
        except setup.Refused:pass
        finally:item.close_handles()


def test_777_input_is_only_data_and_root_copy_is_separately_pinned_and_retired(pinned_factory):
    f=pinned_factory;before=f.original.stat();item=f.create()
    assert item.path.read_bytes()==f.raw and item.path.stat().st_mode&0o777==0o644
    assert item.directory.stat().st_mode&0o777==0o755
    assert f.original.read_bytes()==f.raw and f.original.stat().st_mode&0o777==0o777
    assert (f.original.stat().st_ino,f.original.stat().st_mtime_ns,f.original.stat().st_ctime_ns)==(before.st_ino,before.st_mtime_ns,before.st_ctime_ns)
    receipt=item.retire(True,True,True)
    assert setup.keyring_receipt_ok(receipt) and receipt['original']['mode']==0o777
    assert not item.path.exists() and not item.directory.exists()


def test_same_777_mode_with_wrong_content_pin_is_never_materialized(pinned_factory):
    f=pinned_factory;f.original.write_bytes(b'wrong'.ljust(3607,b'x'))
    with pytest.raises(setup.Refused):f.create()
    assert not list(f.copies.iterdir()) and f.original.stat().st_mode&0o777==0o777


@pytest.mark.parametrize('fault',['bytes','inode','mode','directory'])
def test_private_copy_late_mutation_or_permissions_never_remain_authority(pinned_factory,fault):
    item=pinned_factory.create()
    if fault=='bytes':item.path.write_bytes(b'changed'.ljust(3607,b'x'))
    elif fault=='mode':item.path.chmod(0o666)
    elif fault=='directory':item.directory.chmod(0o777)
    else:
        item.path.rename(item.directory/'old-key');item.path.write_bytes(pinned_factory.raw);item.path.chmod(0o644)
    with pytest.raises(setup.Refused):item.require()
    with pytest.raises(setup.Refused):item.retire(True,True,True)
    assert item.directory.exists()


def test_signed_by_uses_only_factory_copy_and_source_restores_before_key_retirement(pinned_factory,tmp_path):
    item=pinned_factory.create();source=tmp_path/'ubuntu.sources';source.write_bytes(SOURCE);source.chmod(0o644)
    lease=setup.SourceLease(source,tmp_path/'backup',expected_uid=os.getuid(),effective=item)
    try:
        lease.apply()
        assert ('Signed-By: '+str(item.path)).encode() in source.read_bytes() and lease.signed_by_bound
        with pytest.raises(setup.Refused):item.retire(False,True,True)
        with pytest.raises(setup.Refused):item.retire(True,False,True)
        lease.restore();assert source.read_bytes()==SOURCE
        receipt=item.retire(True,True,lease.signed_by_bound)
        assert setup.keyring_receipt_ok(receipt)
    finally:lease.close()


def test_corrupted_copy_does_not_block_restoring_known_source_but_retains_uncertainty(pinned_factory,tmp_path):
    item=pinned_factory.create();source=tmp_path/'ubuntu.sources';source.write_bytes(SOURCE);source.chmod(0o644)
    lease=setup.SourceLease(source,tmp_path/'backup',expected_uid=os.getuid(),effective=item)
    try:
        lease.apply();item.path.write_bytes(b'changed'.ljust(3607,b'x'))
        lease.restore();assert source.read_bytes()==SOURCE
        with pytest.raises(setup.Refused):item.retire(True,True,True)
        assert item.path.exists() and (tmp_path/'backup').read_bytes()==SOURCE
    finally:lease.close()


def test_external_input_change_is_not_repaired_or_retrusted(pinned_factory):
    f=pinned_factory;item=f.create();f.original.write_bytes(b'external change'.ljust(3607,b'x'))
    with pytest.raises(setup.Refused):item.require()
    with pytest.raises(setup.Refused):item.retire(True,True,True)
    assert f.original.read_bytes().startswith(b'external change') and f.original.stat().st_mode&0o777==0o777
    assert item.path.exists()


def test_partial_destination_copy_failure_does_not_touch_original_or_leave_an_authority(pinned_factory,monkeypatch):
    f=pinned_factory
    def fail(fd,data):
        os.pwrite(fd,data[:17],0)
        raise OSError('synthetic partial copy')
    monkeypatch.setattr(setup.SourceLease,'_write',staticmethod(fail))
    with pytest.raises(OSError):f.create()
    assert f.original.read_bytes()==f.raw and f.original.stat().st_mode&0o777==0o777
    assert not list(f.copies.iterdir())


@pytest.mark.parametrize('valid_receipt',[True,False])
def test_recovery_cleanup_requires_effective_retirement_and_strict_receipt(tmp_path,monkeypatch,valid_receipt):
    uid,gid=os.getuid(),os.getgid();source=tmp_path/'source';source.write_bytes(SOURCE);source.chmod(0o644)
    temporary=tmp_path/'user';temporary.mkdir(mode=0o700);copydir=tmp_path/'copy';created=[];recoveries=[]
    class Trust:
        def __init__(self,deadline):
            self.directory=copydir;copydir.mkdir();self.path=copydir/'key';self.path.write_bytes(b'synthetic-public-key')
            self.closed=False;created.append(self)
        def require(self):pass
        def retire(self,*args):
            assert source.read_bytes()==SOURCE
            value=fake_keyring_receipt()
            if valid_receipt:self.path.unlink();self.directory.rmdir()
            else:value['retired']=False
            return value
        def close_handles(self):self.closed=True
    monkeypatch.setattr(setup.os,'geteuid',lambda:0)
    monkeypatch.setattr(setup.os,'environ',{'SUDO_UID':str(uid),'SUDO_GID':str(gid)})
    monkeypatch.setattr(setup.pwd,'getpwuid',lambda _:SimpleNamespace(pw_gid=gid,pw_name='synthetic',pw_dir=str(tmp_path)))
    monkeypatch.setattr(setup,'sdk_profile',lambda:None)
    monkeypatch.setattr(setup.ctypes,'CDLL',lambda *a,**k:SimpleNamespace(prctl=lambda *a:0))
    probe=tmp_path/'pidfd';probe.write_bytes(b'')
    monkeypatch.setattr(setup.os,'pidfd_open',lambda *_:os.open(probe,os.O_RDONLY),raising=False)
    monkeypatch.setattr(setup.signal,'pidfd_send_signal',lambda *a:None,raising=False)
    monkeypatch.setattr(setup.signal,'signal',lambda *a:None)
    monkeypatch.setattr(setup,'PinnedArchiveKeyring',Trust);monkeypatch.setattr(setup,'SOURCE',source)
    original_lease=setup.SourceLease
    monkeypatch.setattr(setup,'SourceLease',lambda path,backup,**kw:original_lease(path,backup,expected_uid=uid,**kw))
    native=setup.tempfile.mkdtemp
    def recovery(**kw):
        value=native(prefix=kw['prefix'],dir=tmp_path);recoveries.append(Path(value));return value
    monkeypatch.setattr(setup.tempfile,'mkdtemp',recovery)
    def completed(lease,*args):
        lease.apply();lease.restore()
        return {'status':'ready','children_closed':True,'source_restored':True}
    monkeypatch.setattr(setup,'install_with_lease',completed)
    request={'uid':uid,'gid':gid,'python':setup.sys.executable,'cache':str(tmp_path/'.cache/ms-playwright'),
             'temporary':str(temporary),'deadline':time.monotonic()+100}
    if valid_receipt:
        result=setup.root_worker(request)
        assert result['status']=='ready' and not recoveries[0].exists() and not copydir.exists()
    else:
        with pytest.raises(setup.CleanupUnknown) as error:setup.root_worker(request)
        assert error.value.recovery==recoveries[0].name and recoveries[0].is_dir()
        assert (recoveries[0]/'ubuntu.sources.backup').read_bytes()==SOURCE and copydir.exists()
    assert source.read_bytes()==SOURCE and created[0].closed


def test_arbitrary_signed_by_reference_cannot_replace_root_factory_resource():
    with pytest.raises(setup.Refused):setup.mirror_source(SOURCE,effective=Path('/unapproved/key.gpg'))


def test_only_mirror_uri_changes_and_all_four_suites_fonts_profile_are_retained():
    assert setup.mirror_source(SOURCE) == SOURCE.replace(b'http://azure.archive.ubuntu.com', b'https://archive.ubuntu.com')
    split = SOURCE.replace(b'noble noble-updates noble-backports noble-security', b'noble noble-updates noble-backports')
    split += b'\n' + SOURCE.replace(b'noble noble-updates noble-backports noble-security', b'noble-security')
    assert setup.mirror_source(split) == split.replace(b'http://azure.archive.ubuntu.com', b'https://archive.ubuntu.com')
    comment = b'# URIs: http://azure.archive.ubuntu.com/ubuntu/\n'
    assert setup.mirror_source(comment+SOURCE) == comment+setup.mirror_source(SOURCE)


@pytest.mark.parametrize('change', [
    (b'Types: deb', b'Types: deb deb-src'),
    (b'noble-security', b'other-security'),
    (b'/usr/share/keyrings/ubuntu-archive-keyring.gpg', b'/tmp/other-key'),
    (b'http://azure.archive.ubuntu.com/ubuntu/', b'https://user:private@example.invalid/'),
    (b'Components: main restricted universe multiverse', b'Components: main'),
    (b'URIs: ', b' URIs: '),
    (b'Types: deb', b'Types: deb\nTrusted: yes'),
    (b'Types: deb', b'Types: deb\nTypes: deb'),
    (b'\n', b'\r\n'),
])
def test_unknown_layout_or_trust_expansion_refuses_without_printing_source(change):
    with pytest.raises(setup.Refused) as error:
        setup.mirror_source(SOURCE.replace(*change))
    assert str(error.value) == 'ci_chromium_setup_refused'


def source_lease(tmp_path):
    path = tmp_path/'ubuntu.sources'
    path.write_bytes(SOURCE)
    path.chmod(0o644)
    lease = setup.SourceLease(path, tmp_path/'backup', expected_uid=os.getuid())
    return path, lease


def test_native_source_inode_bytes_mode_owner_and_backup_survive_restore(tmp_path):
    path, lease = source_lease(tmp_path)
    before = setup.identity(path.stat())
    try:
        lease.apply()
        assert path.read_bytes() == setup.mirror_source(SOURCE)
        assert (tmp_path/'backup').read_bytes() == SOURCE
        assert (tmp_path/'backup').stat().st_mode & 0o777 == 0o600
        lease.restore()
        assert path.read_bytes() == SOURCE and setup.identity(path.stat()) == before
        assert not lease.changed
    finally:
        lease.close()


@pytest.mark.parametrize('fault', ['replaced_inode', 'foreign_bytes', 'symlink'])
def test_restore_never_overwrites_replaced_or_concurrently_changed_source(tmp_path, fault):
    path, lease = source_lease(tmp_path)
    try:
        lease.apply()
        if fault == 'foreign_bytes':
            path.write_bytes(b'concurrent writer')
        else:
            path.rename(tmp_path/'original-inode')
            if fault == 'symlink': path.symlink_to(tmp_path/'original-inode')
            else: path.write_bytes(b'new inode')
        snapshot = path.read_bytes()
        with pytest.raises(setup.CleanupUnknown): lease.restore()
        assert path.read_bytes() == snapshot and (tmp_path/'backup').read_bytes() == SOURCE
    finally:
        lease.close()


def test_partial_native_write_is_unknown_instead_of_a_false_restore(tmp_path, monkeypatch):
    path, lease = source_lease(tmp_path)
    def partial(fd, data):
        os.pwrite(fd, b'partial', 0)
        raise OSError('synthetic interrupted write')
    monkeypatch.setattr(lease, '_write', partial)
    try:
        with pytest.raises(OSError): lease.apply()
        with pytest.raises(setup.CleanupUnknown): lease.restore()
        assert lease.changed and (tmp_path/'backup').read_bytes() == SOURCE
    finally:
        lease.close()


def test_descendant_walk_tracks_sudo_children_outside_the_launcher_group():
    # Rows contain only native parent and start time, not an assumed PGID.
    assert setup.descendants({10:(1,1), 11:(10,2), 12:(11,3), 19:(1,4)}, 10) == {11:(10,2),12:(11,3)}


@pytest.mark.parametrize('reused', [False, True])
def test_root_signals_pidfd_only_after_rechecking_pid_identity(monkeypatch, reused):
    own = os.getpid()
    tables = iter([{44:(own,77)}, {44:(own,78 if reused else 77)}])
    calls = []
    monkeypatch.setattr(setup.os, 'geteuid', lambda:0)
    monkeypatch.setattr(setup, 'proc_rows', lambda:next(tables))
    monkeypatch.setattr(setup.os, 'pidfd_open', lambda pid: calls.append(('open',pid)) or 101, raising=False)
    monkeypatch.setattr(setup.signal, 'pidfd_send_signal', lambda fd,sig:calls.append(('signal',fd,sig)), raising=False)
    monkeypatch.setattr(setup.os, 'close', lambda fd:calls.append(('close',fd)))
    setup.signal_children(signal.SIGKILL)
    assert calls[0] == ('open',44) and calls[-1] == ('close',101)
    assert (('signal',101,signal.SIGKILL) in calls) is not reused


@pytest.mark.parametrize('stubborn', [False, True])
def test_cleanup_uses_the_shared_deadline_and_never_claims_stubborn_root_children_closed(monkeypatch, stubborn):
    now, sent = [86.0], []
    monkeypatch.setattr(setup.time, 'monotonic', lambda:now[0])
    monkeypatch.setattr(setup.time, 'sleep', lambda n:now.__setitem__(0,now[0]+max(n,0.02)))
    monkeypatch.setattr(setup, 'signal_children', lambda sig:sent.append(sig))
    monkeypatch.setattr(setup, 'proc_rows', lambda:{})
    monkeypatch.setattr(setup, 'descendants', lambda *_: {42:(1,7)} if stubborn or signal.SIGKILL not in sent else {})
    monkeypatch.setattr(setup.os, 'waitpid', lambda *_: (_ for _ in ()).throw(ChildProcessError()))
    process = SimpleNamespace(poll=lambda:0)
    if stubborn:
        with pytest.raises(setup.CleanupUnknown): setup.finish_children(process,100.0)
    else:
        setup.finish_children(process,100.0)
    assert signal.SIGTERM in sent and signal.SIGKILL in sent and now[0] <= 95.03


def test_empty_proc_snapshot_is_not_retirement_when_kernel_still_has_a_child(monkeypatch):
    now=[86.0]
    monkeypatch.setattr(setup.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(setup.time,'sleep',lambda n:now.__setitem__(0,now[0]+max(n,0.02)))
    monkeypatch.setattr(setup,'signal_children',lambda *_:None)
    monkeypatch.setattr(setup,'proc_rows',lambda:{})
    monkeypatch.setattr(setup.os,'waitpid',lambda *_:(0,0))
    with pytest.raises(setup.CleanupUnknown):
        setup.finish_children(SimpleNamespace(poll=lambda:0),100.0)


def test_nonroot_worker_refuses_before_reading_or_mutating_system_files(monkeypatch):
    monkeypatch.setattr(setup.os,'geteuid',lambda:501)
    with pytest.raises(setup.Refused): setup.root_worker({})


def test_installer_environment_preserves_sdk_and_user_cache_without_home_or_secrets():
    env = setup.child_environment('/approved/python3.11','/original/user/.cache/ms-playwright','/owned/tmp')
    assert set(env) == {'PATH','LANG','LC_ALL','CI','PLAYWRIGHT_BROWSERS_PATH','TMPDIR'}
    assert env['PATH'].startswith('/approved:') and env['PLAYWRIGHT_BROWSERS_PATH']=='/original/user/.cache/ms-playwright'
    assert setup.COMMAND == ('-m','playwright','install','--with-deps','chromium')


@pytest.mark.parametrize('fault', ['none','exit','launch','cleanup','cancel','loop'])
def test_fake_install_failure_and_root_cleanup_are_ordered_before_native_restore(tmp_path, monkeypatch, capsys, fault):
    path, lease = source_lease(tmp_path)
    events=[]
    def poll():
        if fault=='loop': raise OSError('CANARY_SDK_ERROR')
        return 1 if fault=='exit' else 0
    process=SimpleNamespace(poll=poll)
    def launch(argv, **kw):
        events.append(('launch',argv,kw))
        if fault=='launch': raise OSError('synthetic child launch failure')
        return process
    def finish(p, deadline):
        assert p is (None if fault=='launch' else process)
        events.append(('retire',))
        if fault=='cleanup': raise setup.CleanupUnknown('synthetic cleanup uncertainty')
    original=lease.restore
    def restore():
        events.append(('restore',))
        original()
    monkeypatch.setattr(setup.subprocess,'Popen',launch)
    monkeypatch.setattr(setup,'finish_children',finish)
    monkeypatch.setattr(setup.os,'getgrouplist',lambda *_:[os.getgid()])
    monkeypatch.setattr(lease,'restore',restore)
    request={'cache':'/original/user/.cache/ms-playwright','temporary':str(tmp_path),
             'uid':os.getuid(),'gid':os.getgid()}
    try:
        if fault=='cleanup':
            with pytest.raises(setup.CleanupUnknown):
                setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[False])
            assert events[-1]==('retire',) and path.read_bytes()==setup.mirror_source(SOURCE)
            assert capsys.readouterr().err == ''
        else:
            result=setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[fault=='cancel'])
            assert result['status']==('ready' if fault=='none' else 'failed')
            assert result['source_restored'] and path.read_bytes()==SOURCE
            assert events[-1]==('restore',)
            if fault=='cancel': assert events==[('restore',)]
            output=capsys.readouterr()
            expected={'none':'completed','exit':'nonzero-exit','launch':'launch-exception',
                      'cancel':'control-stop','loop':'loop-exception'}[fault]
            assert output.out == output.err == ''
            if fault=='none': assert 'installer' not in result
            else: assert result['installer']['outcome'] == expected
        if fault!='cancel':
            assert events[0][1][-5:]==list(setup.COMMAND)
            assert events[0][2]['user']==os.getuid() and events[0][2]['group']==os.getgid()
            assert events[0][2]['stdout'] is setup.subprocess.DEVNULL and events[0][2]['stderr'] is setup.subprocess.DEVNULL
    finally:
        lease.close()


def test_sdk_deadline_still_fails_after_known_cleanup_and_reports_no_sdk_text(tmp_path, monkeypatch, capsys):
    path,lease=source_lease(tmp_path)
    now=[0.0];events=[]
    def poll():
        now[0]=88.0
        return None
    process=SimpleNamespace(poll=poll)
    monkeypatch.setattr(setup.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(setup.subprocess,'Popen',lambda *a,**kw:process)
    monkeypatch.setattr(setup,'finish_children',lambda p,d:events.append(('retired',p is process,d)))
    monkeypatch.setattr(setup.os,'getgrouplist',lambda *_:[os.getgid()])
    request={'cache':'/public/cache','temporary':str(tmp_path),'uid':os.getuid(),'gid':os.getgid()}
    try:
        result=setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),100.0,[False])
        assert setup.sdk_snapshot_valid(result['installer'].pop('sdk_processes'))
        assert result=={'status':'failed','children_closed':True,'source_restored':True,
                       'installer':{'protocol':'ci-chromium-installer-v1','outcome':'deadline','observed_exit_code':None}}
        assert path.read_bytes()==SOURCE and events==[('retired',True,100.0)]
        output=capsys.readouterr()
        assert output.out==output.err==''
        assert setup.TOTAL_SECONDS==180
    finally:
        lease.close()


@pytest.mark.parametrize('retirement_known', [True, False])
def test_postfork_constructor_failure_must_retire_without_a_popen_object(tmp_path, monkeypatch, retirement_known):
    path,lease=source_lease(tmp_path)
    events=[]
    alive=[False]
    def postfork(*args,**kwargs):
        alive[0]=True
        raise MemoryError('synthetic failure after child creation')
    def retire(process,deadline):
        assert process is None
        events.append('native_retirement_proof')
        if not retirement_known: raise setup.CleanupUnknown()
        alive[0]=False
    original=lease.restore
    def restore():
        assert not alive[0], 'restore ran before native child retirement'
        events.append('restore')
        original()
    monkeypatch.setattr(setup.subprocess,'Popen',postfork)
    monkeypatch.setattr(setup,'finish_children',retire)
    monkeypatch.setattr(setup.os,'getgrouplist',lambda *_:[os.getgid()])
    monkeypatch.setattr(lease,'restore',restore)
    request={'uid':os.getuid(),'gid':os.getgid(),'cache':'/original/user/.cache/ms-playwright','temporary':str(tmp_path)}
    try:
        if retirement_known:
            result=setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[False])
            assert setup.sdk_snapshot_valid(result['installer'].pop('sdk_processes'))
            assert result=={'status':'failed','children_closed':True,'source_restored':True,
                           'installer':{'protocol':'ci-chromium-installer-v1','outcome':'launch-exception','observed_exit_code':None}}
            assert events==['native_retirement_proof','restore'] and path.read_bytes()==SOURCE
        else:
            with pytest.raises(setup.CleanupUnknown):
                setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[False])
            assert events==['native_retirement_proof'] and path.read_bytes()==setup.mirror_source(SOURCE)
            assert (tmp_path/'backup').read_bytes()==SOURCE
    finally:
        lease.close()


@pytest.mark.parametrize('kernel_empty', [True, False])
def test_none_launch_result_still_requires_kernel_and_descendant_retirement(monkeypatch, kernel_empty):
    now=[86.0]
    monkeypatch.setattr(setup.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(setup.time,'sleep',lambda n:now.__setitem__(0,now[0]+max(n,0.02)))
    monkeypatch.setattr(setup,'signal_children',lambda *_:None)
    monkeypatch.setattr(setup,'proc_rows',lambda:{})
    def wait(*_):
        if kernel_empty: raise ChildProcessError()
        return (0,0)
    monkeypatch.setattr(setup.os,'waitpid',wait)
    if kernel_empty: setup.finish_children(None,100.0)
    else:
        with pytest.raises(setup.CleanupUnknown): setup.finish_children(None,100.0)
    assert now[0]<=95.03


@pytest.mark.parametrize('retirement_known', [True, False])
def test_failure_after_popen_return_also_retires_before_source_restore(tmp_path, monkeypatch, retirement_known):
    path,lease=source_lease(tmp_path)
    process=SimpleNamespace(poll=lambda: (_ for _ in ()).throw(MemoryError('synthetic late poll failure')))
    events=[]
    monkeypatch.setattr(setup.subprocess,'Popen',lambda *a,**kw:process)
    monkeypatch.setattr(setup.os,'getgrouplist',lambda *_:[os.getgid()])
    def retire(value,deadline):
        assert value is process
        events.append('retired')
        if not retirement_known: raise setup.CleanupUnknown()
    monkeypatch.setattr(setup,'finish_children',retire)
    original=lease.restore
    def restore():
        events.append('restore')
        original()
    monkeypatch.setattr(lease,'restore',restore)
    request={'uid':os.getuid(),'gid':os.getgid(),'cache':'/original/user/.cache/ms-playwright','temporary':str(tmp_path)}
    try:
        if retirement_known:
            result=setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[False])
            assert setup.sdk_snapshot_valid(result['installer'].pop('sdk_processes'))
            assert result=={'status':'failed','children_closed':True,'source_restored':True,
                           'installer':{'protocol':'ci-chromium-installer-v1','outcome':'loop-exception','observed_exit_code':None}}
            assert events==['retired','restore'] and path.read_bytes()==SOURCE
        else:
            with pytest.raises(setup.CleanupUnknown):
                setup.install_with_lease(lease,request,SimpleNamespace(pw_name='synthetic'),time.monotonic()+100,[False])
            assert events==['retired'] and path.read_bytes()==setup.mirror_source(SOURCE)
    finally:
        lease.close()


@pytest.mark.parametrize('error', [OSError, MemoryError])
def test_outer_sudo_constructor_failure_is_unknown_and_retains_task_directory(tmp_path, monkeypatch, error):
    monkeypatch.setattr(setup,'host_guard',lambda:None)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    monkeypatch.setattr(setup.subprocess,'Popen',lambda *a,**kw: (_ for _ in ()).throw(error('synthetic unobservable launch')))
    with pytest.raises(setup.CleanupUnknown): setup.prepare()
    assert len(list(tmp_path.iterdir()))==1


@pytest.mark.parametrize('result', [
    {'status':'ready','children_closed':True,'source_restored':True},
    {'status':'ready','children_closed':False,'source_restored':True},
    {'status':'ready','children_closed':True,'source_restored':False},
    {'status':'ready','children_closed':1,'source_restored':True},
    {'status':'failed','children_closed':True,'source_restored':True},
])
def test_only_both_retirement_and_restoration_admit_the_next_step(tmp_path, monkeypatch, result):
    calls=[]
    reply={**result,'keyring':fake_keyring_receipt()}
    class Process:
        stdin=io.BytesIO()
        stdout=io.BytesIO(json.dumps(reply).encode())
        def wait(self,timeout):
            calls.append(('wait',timeout))
            return 1 if result['status']=='failed' else 0
    monkeypatch.setattr(setup, 'host_guard', lambda:None)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    monkeypatch.setenv('PRIVATE_TEST_CREDENTIAL','must-not-forward')
    monkeypatch.setattr(setup.subprocess,'Popen',lambda argv,**kw:calls.append((argv,kw)) or Process())
    if result['children_closed'] is True and result['source_restored'] is True:
        assert setup.prepare()==reply
        assert not list(tmp_path.iterdir())
    else:
        with pytest.raises(setup.Refused): setup.prepare()
        assert len(list(tmp_path.iterdir()))==1  # Retain uncertainty, never fake cleanup.
    argv,kw=calls[0]
    assert argv[:3]==['/usr/bin/sudo','-n','--'] and argv[-1]=='--root-worker'
    assert set(kw['env'])=={'PATH','LANG'} and 0<calls[1][1]<=180


# Failure-only SDK metadata controls in the existing module.
def _sdk_snapshot_fixtures(monkeypatch,after=None,meta=None):
 before={100:(1,10),101:(100,11),102:(101,12)}
 calls=[before,after or before,after or before]
 monkeypatch.setattr(setup.os,'getpid',lambda:100);monkeypatch.setattr(setup,'proc_rows',lambda:calls.pop(0) if calls else (after or before))
 monkeypatch.setattr(setup,'sdk_process_metadata',lambda pid:(before[pid], 'apt_get' if pid==101 else 'apt_https','S') if meta is None else meta(pid))
 monkeypatch.setattr(setup.time,'monotonic',lambda:0.)
def test_owned_sdk_counts_only(monkeypatch):
 _sdk_snapshot_fixtures(monkeypatch);result=setup.sdk_tree_snapshot(100)
 assert result=={'status':'observed','observed':2,'skipped':0,'counts':[{'exe_class':'apt_get','state':'S','count':1},{'exe_class':'apt_https','state':'S','count':1}]}
def test_pid_reuse_or_parent_drift_skips(monkeypatch):
 _sdk_snapshot_fixtures(monkeypatch,after={100:(1,10),101:(100,99),102:(101,12)});value=setup.sdk_tree_snapshot(100);assert value['skipped']>=1
def test_owner_identity_drift_skips_all(monkeypatch):
 _sdk_snapshot_fixtures(monkeypatch,after={100:(1,99),101:(100,11),102:(101,12)});value=setup.sdk_tree_snapshot(100);assert value['observed']==0 and value['skipped']==2
def test_left_owned_tree_skipped(monkeypatch):
 _sdk_snapshot_fixtures(monkeypatch,after={100:(1,10),101:(200,11),102:(101,12)});value=setup.sdk_tree_snapshot(100);assert value['observed']==0
def test_disappearance_is_skipped_no_exception(monkeypatch):
 _sdk_snapshot_fixtures(monkeypatch)
 monkeypatch.setattr(setup,'sdk_process_metadata',lambda pid:(_ for _ in ()).throw(FileNotFoundError()))
 assert setup.sdk_tree_snapshot(100)['skipped']==2
def test_budget_exhausted_best_effort_unavailable(monkeypatch):
 monkeypatch.setattr(setup.time,'monotonic',lambda:100.);assert setup.sdk_tree_snapshot(100)['status']=='snapshot_unavailable'
def test_snapshot_exception_does_not_mask_original(monkeypatch):
 monkeypatch.setattr(setup.time,'monotonic',lambda:0.);monkeypatch.setattr(setup,'proc_rows',lambda:(_ for _ in ()).throw(RuntimeError('internal_fixture')))
 assert setup.sdk_tree_snapshot(100)=={'status':'snapshot_unavailable','observed':0,'skipped':0,'counts':[]}
def test_validator_rejects_free_data(monkeypatch):
 good={'status':'observed','observed':1,'skipped':0,'counts':[{'exe_class':'other','state':'other','count':1}]};assert setup.sdk_snapshot_valid(good)
 for wrong in (good|{'pid':42},good|{'observed':True},good|{'counts':[{'exe_class':'PRIVATE_PATH','state':'S','count':1}]},good|{'counts':[{'exe_class':[],'state':'S','count':1}]}):assert not setup.sdk_snapshot_valid(wrong)
def test_ready_schema_and_stdout_unchanged():
 source=(ROOT/'scripts/prepare_ci_chromium.py').read_text();assert 'stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL' in source
 assert setup.TOTAL_SECONDS==180
 # No sampling loop/everseen or extension of installer command/environment.
 assert 'sdk_tree_snapshot(deadline)' in source and 'sdk_processes=sdk_tree_snapshot(deadline)' in source
 assert set(setup.installer_diagnostic('deadline',None))=={'protocol','outcome','observed_exit_code'}

def test_actual_synthetic_stat_exe_white_other_only(tmp_path,monkeypatch):
    root=tmp_path/'101';root.mkdir()
    fields=['?','100']+['0']*17+['11']
    (root/'stat').write_text('101 (opaque synthetic comm) '+' '.join(fields))
    real_path=Path
    monkeypatch.setattr(setup,'Path',lambda value:tmp_path if str(value)=='/proc' else real_path(value))
    monkeypatch.setattr(setup.os,'readlink',lambda *_:'/private/DO_NOT_EXPORT/unknown_program')
    proof,exe,state=setup.sdk_process_metadata(101)
    assert (proof,exe,state)==((100,11),'other','other')
    (root/'stat').write_text('101 (opaque) '+' '.join(['S','100']+['0']*17+['11']))
    monkeypatch.setattr(setup.os,'readlink',lambda *_:'/usr/bin/apt-get')
    assert setup.sdk_process_metadata(101)==((100,11),'apt_get','S')

def test_failure_only_schema_rejects_invalid_extra_snapshot():
    # Actual keyring receipt authority is covered by the original 110 controls;
    # this exercises strict installer projection without claiming ready.
    value={'status':'observed','observed':1,'skipped':0,'counts':[{'exe_class':'node','state':'S','count':1}]}
    result=setup.installer_diagnostic('deadline',None,value)
    assert set(result)=={'protocol','outcome','observed_exit_code','sdk_processes'}
    with pytest.raises(setup.Refused):setup.installer_diagnostic('deadline',None,value|{'path':'private'})


@pytest.mark.parametrize('status', ['ready', 'failed'])
def test_parent_cleanup_accepts_owned_child_directory_after_known_root_return(tmp_path, monkeypatch, status):
    reply = {'status': status, 'children_closed': True, 'source_restored': True,
             'keyring': fake_keyring_receipt()}
    if status == 'failed':
        reply['installer'] = setup.installer_diagnostic('deadline', None, {
            'status': 'observed', 'observed': 1, 'skipped': 0,
            'counts': [{'exe_class': 'node', 'state': 'S', 'count': 1}],
        })
    observed = {}
    class Process:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(json.dumps(reply).encode())
        def wait(self, timeout):
            request = json.loads(self.stdin.getvalue())
            directory = Path(request['temporary'])
            before = directory.lstat()
            child = directory / 'owned-download-child'
            child.mkdir()
            (child / 'synthetic-data').write_bytes(b'public synthetic content')
            after = directory.lstat()
            observed['same_inode'] = (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
            observed['nlink_changed'] = before.st_nlink != after.st_nlink
            return 0 if status == 'ready' else 1
    monkeypatch.setattr(setup, 'host_guard', lambda: None)
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path))
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda *a, **k: Process())
    assert setup.prepare() == reply
    assert observed == {'same_inode': True, 'nlink_changed': True}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('difference', ['inode', 'mode', 'symlink'])
def test_parent_directory_guard_keeps_wrong_identity_and_outside_files(tmp_path, monkeypatch, difference):
    outside = tmp_path / 'outside'
    outside.mkdir()
    sentinel = outside / 'public-sentinel'
    sentinel.write_bytes(b'untouched synthetic data')
    reply = {'status': 'ready', 'children_closed': True, 'source_restored': True,
             'keyring': fake_keyring_receipt()}
    class Process:
        def __init__(self):
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(json.dumps(reply).encode())
        def wait(self, timeout):
            directory = Path(json.loads(self.stdin.getvalue())['temporary'])
            if difference == 'mode':
                directory.chmod(0o755)
            elif difference == 'inode':
                directory.rename(tmp_path / 'retained-original')
                directory.mkdir(mode=0o700)
            else:
                directory.rmdir()
                directory.symlink_to(outside, target_is_directory=True)
            return 0
    monkeypatch.setattr(setup, 'host_guard', lambda: None)
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path))
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda *a, **k: Process())
    with pytest.raises(setup.Refused): setup.prepare()
    assert sentinel.read_bytes() == b'untouched synthetic data'
    assert list(tmp_path.glob('structure-ci-chromium-user-*'))


@pytest.mark.parametrize('field', ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode'])
def test_temporary_directory_identity_preserves_all_immutable_fields(tmp_path, field):
    info = tmp_path.stat()
    values = {name: getattr(info, name) for name in
              ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink')}
    changed = values | {field: values[field] + 1}
    assert setup.temporary_directory_identity(SimpleNamespace(**changed)) != setup.temporary_directory_identity(info)
    links = values | {'st_nlink': values['st_nlink'] + 1}
    assert setup.temporary_directory_identity(SimpleNamespace(**links)) == setup.temporary_directory_identity(info)
    # General file identity must still include nlink for the existing source,
    # keyring and recovery checks; this is not a global weakening.
    assert setup.identity(SimpleNamespace(**links)) != setup.identity(info)


def test_temporary_directory_identity_refuses_regular_file(tmp_path):
    path = tmp_path / 'public-data'
    path.write_bytes(b'synthetic')
    with pytest.raises(setup.Refused): setup.temporary_directory_identity(path.lstat())


def test_parent_real_remove_failure_stays_unknown_without_exposing_exception(tmp_path, monkeypatch, capsys):
    reply = {'status': 'ready', 'children_closed': True, 'source_restored': True,
             'keyring': fake_keyring_receipt()}
    class Process:
        stdin = io.BytesIO()
        stdout = io.BytesIO(json.dumps(reply).encode())
        def wait(self, timeout): return 0
    original = setup.shutil.rmtree
    def denied(*args, **kwargs): raise PermissionError('SYNTHETIC_INTERNAL_PATH_DO_NOT_PROJECT')
    denied.avoids_symlink_attacks = original.avoids_symlink_attacks
    monkeypatch.setattr(setup, 'host_guard', lambda: None)
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path))
    monkeypatch.setattr(setup.subprocess, 'Popen', lambda *a, **k: Process())
    monkeypatch.setattr(setup.shutil, 'rmtree', denied)
    monkeypatch.setattr(setup.sys, 'argv', ['fixed-helper'])
    assert setup.main() == 2
    output = capsys.readouterr().out
    assert json.loads(output) == setup.failure_record('parent', 'retirement')
    assert 'SYNTHETIC_INTERNAL_PATH' not in output and list(tmp_path.iterdir())
