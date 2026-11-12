"""Synthetic metadata tests, actual Mac refusal, and a Linux-only boundary probe.

No real /run/credentials data, systemd, 1Password, mail, models or Main readiness.
The Linux probe must run in its own approved -I -B nonroot process: hard CORE=0
cannot be restored. It certifies only that process boundary, not a service.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / 'scripts/run-formal-main.py'


def load_entry():
    spec = importlib.util.spec_from_file_location('formal_secret_entry_under_test', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def entry():
    return load_entry()


def synthetic_values(entry):
    return {target: (secrets.token_hex(32) if target == 'STRUCTURAL_PRIVACY_HMAC_KEY'
                     else '短' if target == 'STRUCTURAL_SHARE_TOKEN_SECRET'
                     else secrets.token_urlsafe(48)) for _, target in entry.CREDENTIAL_IDS}


@pytest.fixture
def credentials(tmp_path, entry, monkeypatch):
    import systemd_credential_metadata as metadata
    entry._METADATA_HELPER = metadata
    def collect_owned(descriptor):
        info = os.fstat(descriptor)
        return dict(zip(metadata.SNAPSHOT_FIELDS, (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns, ('ABSENT', (), None), ('ABSENT', (), None), True, 23, True)))
    # Only the new collector is synthetic; every strict predicate and original
    # byte/mutation/close rule still executes on these actual owned files.
    monkeypatch.setattr(entry, '_capture_metadata', collect_owned)
    root = tmp_path / 'synthetic-credentials'
    root.mkdir(mode=0o700)
    values = synthetic_values(entry)
    for name, target in entry.CREDENTIAL_IDS:
        path = root / name
        path.write_bytes(values[target].encode())
        path.chmod(0o400)
    root.chmod(0o500)
    yield root, values
    root.chmod(0o700)


def read_owned(entry, root):
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        return entry._read_group(directory, os.geteuid())
    finally:
        os.close(directory)


def test_complete_synthetic_group_matches_actual_consumer_rules(entry, credentials, monkeypatch):
    root, expected = credentials
    assert read_owned(entry, root) == expected
    for name, value in expected.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    from api.auth import _jwt_secret
    from api.sso import _secret
    from services.privacy_identifiers import validate_privacy_hmac_config
    from services.report_store import _share_secret
    assert _jwt_secret() == expected['JWT_SECRET'] and _secret() == expected['STRUCTURAL_SSO_SECRET']
    validate_privacy_hmac_config()
    assert _share_secret() == expected['STRUCTURAL_SHARE_TOKEN_SECRET'].encode()
    assert entry._validate_value('STRUCTURAL_SHARE_TOKEN_SECRET', b'x') == 'x'
    # Whitespace is neither silently removed nor a new length restriction.
    raw = (' ' + expected['JWT_SECRET'] + ' ').encode()
    assert entry._validate_value('JWT_SECRET', raw).encode() == raw


@pytest.mark.parametrize('fault', ['missing', 'symlink', 'hardlink', 'fifo', 'mode', 'empty', 'oversize', 'utf8', 'newline'])
def test_bad_or_partial_group_never_publishes_and_closes_fds(entry, credentials, monkeypatch, fault):
    root, _ = credentials
    root.chmod(0o700)
    target = root / 'structural-smtp-password'
    if fault == 'missing': target.unlink()
    elif fault == 'symlink':
        target.unlink(); target.symlink_to(root / 'structural-jwt-secret')
    elif fault == 'hardlink': os.link(target, root / 'not-a-credential')
    elif fault == 'fifo': target.unlink(); os.mkfifo(target, 0o400)
    elif fault == 'mode': target.chmod(0o600)
    else:
        target.chmod(0o600)
        target.write_bytes(b'' if fault == 'empty' else b'x' * 4097 if fault == 'oversize' else b'\xff' if fault == 'utf8' else b'synthetic\n')
        target.chmod(0o400)
    root.chmod(0o500)
    opened = []; original = os.open
    def observe(*args, **kwargs):
        descriptor = original(*args, **kwargs); opened.append(descriptor); return descriptor
    monkeypatch.setattr(os, 'open', observe)
    before = {name: name in os.environ for _, name in entry.CREDENTIAL_IDS}
    with pytest.raises(entry.EntryFailure) as error:
        read_owned(entry, root)
    assert error.value.code.startswith('CREDENTIAL_')
    assert before == {name: name in os.environ for _, name in entry.CREDENTIAL_IDS}
    for descriptor in opened:
        with pytest.raises(OSError): os.fstat(descriptor)


def test_same_size_mutation_is_rejected_and_close_failure_attempts_remaining_fds(entry, credentials, monkeypatch):
    root, _ = credentials
    read = os.read
    def mutate(descriptor, size):
        raw = read(descriptor, size)
        path = root / 'structural-jwt-secret'
        path.chmod(0o600); path.write_bytes(b'Z' * len(raw)); path.chmod(0o400)
        return raw
    with monkeypatch.context() as patch:
        patch.setattr(os, 'read', mutate)
        with pytest.raises(entry.EntryFailure, match='CREDENTIAL_CHANGED'):
            read_owned(entry, root)
    left, right = os.pipe(); native_close = os.close; calls = []
    def close_after(descriptor):
        native_close(descriptor); calls.append(descriptor); raise OSError('owned close receipt fault')
    monkeypatch.setattr(os, 'close', close_after)
    with pytest.raises(entry.EntryFailure, match='FD_CLOSE_FAILED'):
        entry._close_all([left, right])
    assert set(calls) == {left, right}
    for descriptor in (left, right):
        with pytest.raises(OSError): os.fstat(descriptor)


@pytest.mark.parametrize('name', ['JWT_SECRET', 'DEEPSEEK_API_KEY', 'OPENAI_API_KEY', 'OP_SERVICE_ACCOUNT_TOKEN'])
def test_inherited_sensitive_name_refused_without_reading_value(entry, monkeypatch, name):
    class NamesOnly(dict):
        def __getitem__(self, key): raise AssertionError('must not read inherited values')
        def get(self, *args): raise AssertionError('must not read inherited values')
    monkeypatch.setattr(os, 'environ', NamesOnly({name: object()}))
    with pytest.raises(entry.EntryFailure, match='INHERITED_SECRET'):
        entry._initial_environment()


def test_metadata_and_readback_predicates_are_fail_closed(entry):
    from types import SimpleNamespace
    import stat
    for info in (SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_uid=12),
                 SimpleNamespace(st_mode=stat.S_IFDIR | 0o500, st_uid=0)):
        with pytest.raises(entry.EntryFailure): entry._directory_metadata(info, 12, final=True)
    for value in ((0, 1), (1, 0), (1, 1), (False, False)):
        with pytest.raises(entry.EntryFailure): entry._core_state(value)
    for value in (1, 2, -1, None):
        with pytest.raises(entry.EntryFailure): entry._dump_state(value)
    for target, raw in (('SMTP_PASSWORD', b'has\0nul'), ('SMTP_PASSWORD', b'has\rreturn'),
                        ('JWT_SECRET', b'weak'), ('STRUCTURAL_SSO_SECRET', b'dev-' + b'0123456789abcdef' * 3),
                        ('STRUCTURAL_PRIVACY_HMAC_KEY', b'ABCDEF0123456789' * 4)):
        with pytest.raises(entry.EntryFailure): entry._validate_value(target, raw)


def test_logical_environment_batch_rolls_back_its_partial_install(entry, monkeypatch):
    values = synthetic_values(entry)
    class Partial(dict):
        def update(self, values):
            super().__setitem__('JWT_SECRET', values['JWT_SECRET'])
            raise OSError('owned partial environment update')
    environment = Partial()
    monkeypatch.setattr(os, 'environ', environment)
    with pytest.raises(entry.EntryFailure, match='ENV_INSTALL_FAILED'):
        entry._publish_environment(values)
    assert all(name not in environment for _, name in entry.CREDENTIAL_IDS)
    assert not any(value in str(entry.EntryFailure('ENV_INSTALL_FAILED')) for value in values.values())


def test_nonsecret_precheck_rejects_wrong_directory_code_override_profile_and_empty_username(entry, monkeypatch):
    initial = {'CREDENTIALS_DIRECTORY': entry.CREDENTIAL_DIRECTORY, 'SMTP_USERNAME': 'synthetic-user'}
    for patch, code in (({'CREDENTIALS_DIRECTORY': entry.CREDENTIAL_DIRECTORY + '/'}, 'CREDENTIAL_DIRECTORY_INVALID'),
                        ({'STRUCTURAL_PROJECT_ROOT': '/unapproved-code'}, 'CODE_OVERRIDE'),
                        ({'AUTH_SITE_ROLE': 'phase'}, 'PROFILE_INVALID'),
                        ({'SMTP_USERNAME': ' '}, 'SMTP_AUTH_REQUIRED')):
        with monkeypatch.context() as scope:
            scope.setattr(os, 'environ', {**initial, **patch})
            with pytest.raises(entry.EntryFailure, match=code): entry._initial_environment()


def test_earlier_file_changed_during_later_read_rejects_whole_group(entry, credentials, monkeypatch):
    root, _ = credentials
    original = os.read; count = 0
    def late_mutation(descriptor, size):
        nonlocal count
        count += 1; raw = original(descriptor, size)
        if count == 5:
            first = root / 'structural-jwt-secret'
            first.chmod(0o600); first.write_bytes(b'X' * first.stat().st_size); first.chmod(0o400)
        return raw
    monkeypatch.setattr(os, 'read', late_mutation)
    with pytest.raises(entry.EntryFailure, match='CREDENTIAL_CHANGED'):
        read_owned(entry, root)


def test_fixed_ids_no_exec_no_uid_change_and_no_application_import_at_module_load():
    tree = ast.parse(SCRIPT.read_bytes())
    top_imports = {alias.name for item in tree.body if isinstance(item, ast.Import) for alias in item.names}
    assert top_imports == {'os', 'stat', 'sys'}
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert not any(isinstance(node.func, ast.Attribute) and (
        node.func.attr.startswith('exec') or node.func.attr in ('setuid', 'seteuid', 'setresuid', 'setgid', 'Popen')) for node in calls)
    entry = load_entry()
    assert len(entry.CREDENTIAL_IDS) == 5
    assert entry.CREDENTIAL_DIRECTORY == '/run/credentials/structural-web.service'


@pytest.mark.skipif(sys.platform != 'darwin', reason='actual Mac unsupported boundary only')
def test_actual_mac_boundary_refuses_with_zero_credential_opens(entry, monkeypatch):
    opened = []
    def refuse(*args, **kwargs):
        opened.append(True); raise AssertionError('credential open forbidden')
    monkeypatch.setattr(os, 'open', refuse)
    with pytest.raises(entry.EntryFailure, match='UNSUPPORTED_PLATFORM'):
        entry._harden_current_process()
    assert not opened


def test_isolated_entry_missing_or_inherited_boundary_has_safe_output(tmp_path):
    environment = {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'JWT_SECRET': 'synthetic-private-marker'}
    result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], env=environment,
                            capture_output=True, timeout=10)
    assert result.returncode == 78 and result.stderr == b'FORMAL_ENTRY:INHERITED_SECRET\n'
    assert not result.stdout and b'synthetic-private-marker' not in result.stderr
    environment.pop('JWT_SECRET')
    result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], env=environment,
                            capture_output=True, timeout=10)
    assert result.returncode == 78 and result.stderr == b'FORMAL_ENTRY:CREDENTIAL_DIRECTORY_INVALID\n'
    if sys.platform == 'darwin':
        environment.update(CREDENTIALS_DIRECTORY='/run/credentials/structural-web.service', SMTP_USERNAME='synthetic-user')
        result = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT)], env=environment,
                                capture_output=True, timeout=10)
        assert result.returncode == 78 and result.stderr == b'FORMAL_ENTRY:UNSUPPORTED_PLATFORM\n'


@pytest.mark.skipif(sys.platform != 'linux', reason='requires actual Linux; never simulated as evidence')
def test_real_linux_boundary_in_own_final_interpreter(tmp_path):
    if os.geteuid() == 0:
        pytest.skip('requires actual approved nonroot identity')
    result = subprocess.run([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--linux-boundary-probe'],
        env={'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path)}, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    facts = json.loads(result.stdout)
    assert facts['scope'] == 'linux_boundary_only' and facts['pid_unchanged']
    assert facts['core'] == [0, 0] and facts['dumpable'] == 0 and facts['credential_reads'] == 0


if __name__ == '__main__':
    if sys.argv[1:] != ['--linux-boundary-probe'] or not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise SystemExit(78)
    credential_reads = []
    def audit(event, args):
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            if os.fsdecode(args[0]).startswith('/run/credentials/'):
                credential_reads.append(True)
                raise AssertionError('boundary probe must never read credentials')
    sys.addaudithook(audit)
    module = load_entry()
    before = os.getpid()
    pid, uid = module._harden_current_process()
    module._check_boundary(pid, uid)
    import resource
    print(json.dumps({'scope': 'linux_boundary_only', 'pid_unchanged': before == os.getpid() == pid,
        'core': resource.getrlimit(resource.RLIMIT_CORE), 'dumpable': module._prctl()(3, 0, 0, 0, 0),
        'credential_reads': len(credential_reads), 'formal_main_or_systemd_verified': False}))


def test_provider_is_not_added_to_existing_environment_group(entry):
    assert len(entry.CREDENTIAL_IDS)==5
    assert not any('deepseek' in name.lower() or 'API_KEY' in target for name,target in entry.CREDENTIAL_IDS)
    code=ast.parse(SCRIPT.read_bytes())
    publish=next(n for n in code.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='_publish_entry_directory' for n in ast.walk(publish))


def test_same_named_preimport_module_cannot_get_entry_source_exception(entry):
    from types import SimpleNamespace
    with pytest.raises(entry.EntryFailure):entry._code_paths(entry_module=SimpleNamespace(),entry_witness=object())


def test_entry_failure_retains_failed_descriptor_and_attempts_remaining(entry,monkeypatch):
    descriptors=[101,102,103];closed=[]
    def close(fd):
        closed.append(fd)
        if fd==102:raise OSError('synthetic close uncertainty')
    monkeypatch.setattr(entry.os,'close',close)
    with pytest.raises(entry.EntryFailure,match='FD_CLOSE_FAILED'):entry._close_all(descriptors)
    assert closed==[103,102,101] and descriptors==[102] and entry._UNCERTAIN_FDS[-1]==(102,)


def test_preinjected_metadata_helper_and_untrusted_source_refused(entry, monkeypatch, tmp_path):
    from types import ModuleType
    fake = ModuleType('systemd_credential_metadata')
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'modules', {name:value for name,value in sys.modules.items() if not name.startswith(('services', 'api', 'research', 'web.backend'))})
        patch.setitem(sys.modules, 'systemd_credential_metadata', fake)
        with pytest.raises(entry.EntryFailure, match='CODE_IDENTITY_INVALID'):entry._code_paths()
    owned = tmp_path/'helper.py';owned.write_bytes(b'# owned synthetic source\n')
    with pytest.raises((entry.EntryFailure, OSError)):entry._source_bytes(owned)


def test_metadata_snapshot_mutation_and_group_pre_publish_recheck(entry, credentials, monkeypatch):
    root, _ = credentials
    read_owned(entry, root)
    native = entry._capture_metadata;calls = []
    def changed(descriptor):
        value = native(descriptor);calls.append(descriptor)
        if len(calls) == 2:value['mount_id'] += 1
        return value
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(entry, '_capture_metadata', changed)
            with pytest.raises(entry.EntryFailure, match='CREDENTIAL_CHANGED'):entry._check_group(directory, os.geteuid())
        root.chmod(0o700)
        target = root/'structural-jwt-secret';target.chmod(0o600);target.write_bytes(b'changed synthetic bytes');target.chmod(0o400);root.chmod(0o500)
        with pytest.raises(entry.EntryFailure):entry._check_group(directory, os.geteuid())
    finally:os.close(directory)


def test_identity_annotation_is_per_exception_and_keeps_original_code(entry):
    original=entry.EntryFailure('CODE_IDENTITY_INVALID',('SRC_ROOT',0,2))
    assert original.identity_site==('SRC_ROOT',0,2)
    assert str(original)=='CODE_IDENTITY_INVALID'
    assert entry._identity_annotation(original)==b'FORMAL_IDENTITY_V1:SRC_ROOT:0:2\n'
    assert entry._identity_annotation(entry.EntryFailure('CODE_IDENTITY_INVALID'))==b''
    second=entry.EntryFailure('CODE_IDENTITY_INVALID',('HELPER_FUNCTION',None,None))
    assert entry._identity_annotation(second)==b'FORMAL_IDENTITY_V1:HELPER_FUNCTION:-:-\n'
    assert original.identity_site==('SRC_ROOT',0,2)
    assert entry._identity_annotation(entry.EntryFailure('CREDENTIAL_IO_FAILED',original.identity_site))==b''
    with pytest.raises(AttributeError):original.identity_site=('HELPER_FUNCTION',None,None)


def _source_identity_inputs(entry,monkeypatch,fault='none',depth=5):
    import stat
    from types import SimpleNamespace
    parts=('/',*[('node'+str(i)) for i in range(1,depth)],'helper.py')
    path=Path(*parts);raw=b'# finite source\n';fds={};events=[];read_done=False
    def info(index):
        leaf=index==depth;mode=(stat.S_IFREG|0o644) if leaf else (stat.S_IFDIR|0o755)
        uid=0;nlink=1 if leaf else 2;size=len(raw) if leaf else 4096
        if (fault in ('root_owner','root_owner_and_write') and index==0) or (fault in ('component_owner','component_owner_and_write') and index==depth):uid=1
        if (fault in ('root_write','root_owner_and_write') and index==0) or (fault in ('component_write','component_owner_and_write') and index==depth):mode|=0o022
        if fault=='component_type' and leaf:mode=stat.S_IFDIR|0o755
        if fault=='leaf_link' and leaf:nlink=2
        if fault=='leaf_size' and leaf:size=65537
        return SimpleNamespace(st_dev=1,st_ino=index+1,st_uid=uid,st_gid=0,st_mode=mode,st_nlink=nlink,st_size=size,
                               st_mtime_ns=2 if fault=='read_identity' and leaf and read_done else 1,st_ctime_ns=1)
    def opened(name,flags,dir_fd=None):
        index=0 if dir_fd is None else fds[dir_fd]+1;assert name==parts[index]
        descriptor=100+index;fds[descriptor]=index;events.append(('open',index));return descriptor
    def held(descriptor):events.append(('fstat',fds[descriptor]));return info(fds[descriptor])
    def named(name,dir_fd,follow_symlinks):
        index=fds[dir_fd]+1;assert name==parts[index] and follow_symlinks is False
        events.append(('stat',index));value=info(index)
        if fault=='component_identity' and index==depth:value.st_ino+=1
        return value
    def read(descriptor,limit):
        nonlocal read_done
        assert fds[descriptor]==depth and limit==65537;events.append(('read',depth));read_done=True
        return raw[:-1] if fault=='short_read' else raw
    def close(descriptor):
        events.append(('close',fds[descriptor]))
        if fault=='close_overrides' and fds[descriptor]==depth:raise OSError('finite close failure')
    fake=SimpleNamespace(**{name:getattr(os,name) for name in ('O_RDONLY','O_DIRECTORY','O_NOFOLLOW','O_CLOEXEC','O_NONBLOCK')},
                         open=opened,fstat=held,stat=named,read=read,close=close)
    if fault=='close_overrides':
        native_read=read
        def short(descriptor,limit):native_read(descriptor,limit);return b''
        fake.read=short
    monkeypatch.setattr(entry,'os',fake)
    return path,raw,events


@pytest.mark.parametrize('fault,site,mask',[('root_owner','SRC_ROOT',1),('root_write','SRC_ROOT',2),('root_owner_and_write','SRC_ROOT',1),('component_owner_and_write','SRC_COMPONENT',1),
    ('component_owner','SRC_COMPONENT',1),('component_write','SRC_COMPONENT',2),('component_identity','SRC_COMPONENT',4),
    ('component_type','SRC_COMPONENT',8),('leaf_link','SRC_LEAF_BOUNDS',16),('leaf_size','SRC_LEAF_BOUNDS',32),
    ('short_read','SRC_READBACK',64),('read_identity','SRC_READBACK',128)])
def test_source_identity_rejections_preserve_short_circuit_inputs(entry,monkeypatch,fault,site,mask):
    path,raw,events=_source_identity_inputs(entry,monkeypatch,fault)
    with pytest.raises(entry.EntryFailure) as caught:entry._source_bytes(path)
    assert caught.value.code=='CODE_IDENTITY_INVALID'
    assert caught.value.identity_site==(site,0 if site=='SRC_ROOT' else 5,mask)
    assert sum(e[0]=='open' for e in events)==sum(e[0]=='close' for e in events)
    if fault=='short_read':
        read_index=events.index(('read',5))
        assert all(e[0]=='close' for e in events[read_index+1:])
        assert sum(e[0]=='fstat' for e in events)==7


def test_source_identity_good_input_and_deep_component_unknown(entry,monkeypatch):
    with monkeypatch.context() as patch:
        path,raw,events=_source_identity_inputs(entry,patch)
        assert entry._source_bytes(path)==raw
        assert sum(e[0]=='fstat' for e in events)==8
    with monkeypatch.context() as patch:
        path,raw,events=_source_identity_inputs(entry,patch,'component_owner',depth=32)
        with pytest.raises(entry.EntryFailure) as caught:entry._source_bytes(path)
        assert caught.value.identity_site==('SRC_COMPONENT',None,1)
        assert entry._identity_annotation(caught.value)==b'FORMAL_IDENTITY_V1:SRC_COMPONENT:-:1\n'


def _finite_identity_helper(entry,monkeypatch):
    import builtins
    from types import ModuleType,SimpleNamespace
    path=ROOT/'web/backend/systemd_credential_metadata.py';raw=path.read_bytes()
    module=ModuleType('systemd_credential_metadata');module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True),vars(module))
    monkeypatch.setattr(entry,'_METADATA_HELPER',module)
    monkeypatch.setattr(entry,'sys',SimpleNamespace(modules={module.__name__:module}))
    monkeypatch.setattr(entry,'_source_bytes',lambda path:raw)
    assert module.__builtins__ is vars(builtins)
    return module,raw


@pytest.mark.parametrize('site',['HELPER_MODULE','HELPER_BUILTINS','HELPER_MEMBERS','HELPER_FUNCTION','HELPER_CONSTANT','HELPER_SOURCE_REREAD'])
def test_helper_identity_sites_reject_actual_instance_without_authority(entry,monkeypatch,site):
    module,raw=_finite_identity_helper(entry,monkeypatch)
    if site=='HELPER_MODULE':entry._METADATA_HELPER=None
    elif site=='HELPER_BUILTINS':module.__builtins__=dict(module.__builtins__)
    elif site=='HELPER_MEMBERS':module.extra=True
    elif site=='HELPER_FUNCTION':module.capture_fd=lambda:None
    elif site=='HELPER_CONSTANT':module.TAGS=(1,)
    else:
        reads=iter((raw,raw+b'\n'));monkeypatch.setattr(entry,'_source_bytes',lambda path:next(reads))
    with pytest.raises(entry.EntryFailure) as caught:entry._require_metadata_helper()
    assert caught.value.code=='CODE_IDENTITY_INVALID' and caught.value.identity_site==(site,None,None)


@pytest.mark.parametrize('site',['LOAD_PREINJECT','LOAD_SOURCE_CHANGED'])
def test_helper_loader_identity_sites_preserve_rejection(entry,monkeypatch,site):
    import importlib
    from types import SimpleNamespace
    backend=ROOT/'web/backend';module=object()
    monkeypatch.setattr(entry,'sys',SimpleNamespace(modules={},path=[]))
    if site=='LOAD_PREINJECT':monkeypatch.setattr(entry,'_METADATA_HELPER',module)
    else:
        reads=iter((b'before',b'after'));monkeypatch.setattr(entry,'_source_bytes',lambda path:next(reads))
        monkeypatch.setattr(importlib,'import_module',lambda name:module)
        monkeypatch.setattr(entry,'_require_metadata_helper',lambda:module)
    with pytest.raises(entry.EntryFailure) as caught:entry._load_metadata_helper(backend)
    assert caught.value.code=='CODE_IDENTITY_INVALID' and caught.value.identity_site==(site,None,None)


@pytest.mark.parametrize('site',['ENTRY_PATH','ENTRY_WITNESS_PAIR','APP_PREIMPORT'])
def test_code_path_identity_sites_remain_closed(entry,monkeypatch,tmp_path,site):
    from types import SimpleNamespace
    monkeypatch.setattr(entry,'sys',SimpleNamespace(modules={}))
    kwargs={}
    if site=='ENTRY_PATH':
        path=tmp_path/'different-name.py';path.write_bytes(b'# owned code\n');monkeypatch.setattr(entry,'__file__',str(path))
    elif site=='ENTRY_WITNESS_PAIR':kwargs['entry_witness']=object()
    else:entry.sys.modules['main']=object()
    with pytest.raises(entry.EntryFailure) as caught:entry._code_paths(**kwargs)
    assert caught.value.code=='CODE_IDENTITY_INVALID' and caught.value.identity_site==(site,None,None)


@pytest.mark.parametrize('site',['ENTRY_MODULE','ENTRY_BUILTINS','ENTRY_FUNCTION'])
def test_formal_native_module_identity_sites_never_publish(entry,monkeypatch,site):
    import builtins
    import types
    from types import SimpleNamespace
    path=ROOT/'web/backend/services/native_live_credentials.py';module=types.ModuleType('services.native_live_credentials');module.__file__=str(path)
    package=types.ModuleType('services');package.__file__=str(path.parent/'__init__.py')
    codes={c.co_name:c for c in compile(path.read_bytes(),str(path),'exec',dont_inherit=True).co_consts if isinstance(c,types.CodeType)}
    module.__builtins__=vars(builtins)
    for name in ('_publish_entry_directory','_require_entry_preimport','_require_entry_for_serve'):
        setattr(module,name,types.FunctionType(codes[name],vars(module)))
    monkeypatch.setattr(entry,'sys',SimpleNamespace(modules={'services':package,'services.native_live_credentials':module}))
    if site=='ENTRY_MODULE':module.__file__+='-wrong'
    elif site=='ENTRY_BUILTINS':module.__builtins__=dict(vars(builtins))
    else:module._publish_entry_directory=lambda:None
    with pytest.raises(entry.EntryFailure) as caught:entry._validate_entry_module(module,ROOT)
    assert caught.value.code=='CODE_IDENTITY_INVALID' and caught.value.identity_site==(site,None,None)


def test_main_identity_site_uses_only_finite_import_result(entry,monkeypatch):
    import importlib
    from types import SimpleNamespace
    calls=[];source=ROOT/'web/backend/main.py'
    monkeypatch.setattr(entry,'_code_paths',lambda **kwargs:(ROOT,source.parent,source))
    monkeypatch.setattr(entry,'sys',SimpleNamespace(path=[]))
    def imported(name):
        calls.append(name);assert name=='main'
        return SimpleNamespace(__file__=str(source),_IS_PROD=False,_LAUNCH_FORMAL=True)
    monkeypatch.setattr(importlib,'import_module',imported)
    with pytest.raises(entry.EntryFailure) as caught:entry._serve(123,999)
    assert caught.value.code=='CODE_IDENTITY_INVALID' and caught.value.identity_site==('MAIN_IDENTITY',None,None)
    assert calls==['main']  # No actual Main import or uvicorn/server call.


def _main_failure_output(entry,monkeypatch,error,annotation=None):
    from types import SimpleNamespace
    writes=[]
    monkeypatch.setattr(entry,'sys',SimpleNamespace(argv=['formal'],flags=SimpleNamespace(isolated=True,dont_write_bytecode=True)))
    monkeypatch.setattr(entry,'os',SimpleNamespace(environ={},write=lambda fd,raw:writes.append((fd,raw))))
    def failed():raise error
    monkeypatch.setattr(entry,'_initial_environment',failed)
    if annotation is not None:monkeypatch.setattr(entry,'_identity_annotation',annotation)
    assert entry.main()==78
    assert len(writes)==1 and writes[0][0]==2
    return writes[0][1]


def test_primary_single_write_and_format_failure_fallback(entry,monkeypatch):
    failure=entry.EntryFailure('CODE_IDENTITY_INVALID',('HELPER_MODULE',None,None))
    assert _main_failure_output(entry,monkeypatch,failure)==b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\nFORMAL_IDENTITY_V1:HELPER_MODULE:-:-\n'
    with monkeypatch.context() as patch:
        def bad_format(error):raise ValueError('finite formatting failure')
        assert _main_failure_output(entry,patch,failure,bad_format)==b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n'
    unrelated=entry.EntryFailure('CREDENTIAL_IO_FAILED');unrelated.__context__=failure
    assert _main_failure_output(entry,monkeypatch,unrelated)==b'FORMAL_ENTRY:CREDENTIAL_IO_FAILED\n'
    assert _main_failure_output(entry,monkeypatch,entry.EntryFailure('CODE_IDENTITY_INVALID'))==b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\n'


def test_close_failure_becomes_actual_primary_without_stale_identity(entry,monkeypatch):
    with monkeypatch.context() as patch:
        path,raw,events=_source_identity_inputs(entry,patch,'close_overrides')
        with pytest.raises(entry.EntryFailure) as caught:entry._source_bytes(path)
        assert caught.value.code=='FD_CLOSE_FAILED' and caught.value.identity_site is None
        assert caught.value.__context__.identity_site==('SRC_READBACK',5,64)
        assert entry._UNCERTAIN_FDS[-1]==(105,)
    assert _main_failure_output(entry,monkeypatch,caught.value)==b'FORMAL_ENTRY:FD_CLOSE_FAILED\n'


@pytest.mark.parametrize('value',[
    ('UNKNOWN',None,None),('HELPER_MODULE',1,None),('HELPER_MODULE',None,1),
    ('SRC_ROOT',True,2),('SRC_ROOT',1,2),('SRC_COMPONENT',0,1),('SRC_COMPONENT',32,1),
    ('SRC_ROOT',0,0),('SRC_COMPONENT',1,16),('SRC_READBACK',1,False),
    ('SRC_LEAF_BOUNDS',1,64),('SRC_ROOT',0,-1),['SRC_ROOT',0,2]])
def test_invalid_identity_metadata_is_omitted_without_new_failure(entry,value):
    error=entry.EntryFailure('CODE_IDENTITY_INVALID',value)
    assert entry._identity_annotation(error)==b'' and str(error)=='CODE_IDENTITY_INVALID'


def test_helper_wrapper_does_not_recover_discarded_context_identity(entry,monkeypatch):
    import importlib
    from types import SimpleNamespace
    source=ROOT/'web/backend/main.py';old=entry.EntryFailure('CODE_IDENTITY_INVALID',('MAIN_IDENTITY',None,None))
    monkeypatch.setattr(entry,'_code_paths',lambda **kwargs:(ROOT,source.parent,source))
    monkeypatch.setattr(entry,'sys',SimpleNamespace(path=[]))
    def imported(name):
        assert name=='main'
        try:raise old
        except entry.EntryFailure:raise ValueError('finite wrapper failure')
    monkeypatch.setattr(importlib,'import_module',imported)
    with pytest.raises(entry.EntryFailure) as caught:entry._serve(123,999)
    assert caught.value.code=='APP_IMPORT_FAILED' and caught.value.identity_site is None
    assert _main_failure_output(entry,monkeypatch,caught.value)==b'FORMAL_ENTRY:APP_IMPORT_FAILED\n'


def test_final_close_marker_keeps_original_separate_write_and_primary(entry,monkeypatch):
    from types import SimpleNamespace
    writes=[];closed=[]
    witness=SimpleNamespace()
    def close():closed.append(True);raise OSError('finite owned cleanup failure')
    witness.close=close
    monkeypatch.setattr(entry,'sys',SimpleNamespace(argv=['formal'],flags=SimpleNamespace(isolated=True,dont_write_bytecode=True),path=[]))
    monkeypatch.setattr(entry,'os',SimpleNamespace(environ={},write=lambda fd,raw:writes.append((fd,raw))))
    monkeypatch.setattr(entry,'_initial_environment',lambda:None)
    monkeypatch.setattr(entry,'_harden_current_process',lambda:(123,999))
    monkeypatch.setattr(entry,'_code_paths',lambda:(ROOT,ROOT/'web/backend',ROOT/'web/backend/main.py'))
    monkeypatch.setattr(entry,'_load_metadata_helper',lambda backend:None)
    monkeypatch.setattr(entry,'_check_boundary',lambda pid,uid:None)
    monkeypatch.setattr(entry,'_capture_consumer',lambda:('finite-consumer',))
    monkeypatch.setattr(entry,'_credential_directory',lambda uid:[100])
    monkeypatch.setattr(entry,'_read_group',lambda fd,uid:{})
    monkeypatch.setattr(entry,'_check_directories',lambda fds,uid:None)
    monkeypatch.setattr(entry,'_check_group',lambda fd,uid:None)
    monkeypatch.setattr(entry,'_validate_entry_module',lambda module,root:None)
    monkeypatch.setattr(entry,'_close_all',lambda fds:None)
    module=SimpleNamespace(_publish_entry_directory=lambda fds:witness,NativeCredentialStartFailure=type('FiniteStartFailure',(Exception,),{}))
    import importlib
    monkeypatch.setattr(importlib,'import_module',lambda name:module)
    def refuse():raise entry.EntryFailure('CODE_IDENTITY_INVALID',('HELPER_MODULE',None,None))
    witness.require_runtime=refuse
    assert entry.main()==78 and closed==[True]
    assert writes==[(2,b'FORMAL_ENTRY:CODE_IDENTITY_INVALID\nFORMAL_IDENTITY_V1:HELPER_MODULE:-:-\n'),(2,b'FORMAL_ENTRY:FD_CLOSE_FAILED\n')]


def test_read_proc_short_chunks_require_eof_on_same_fd(entry,monkeypatch):
    opened=[];reads=[];closed=[];chunks=iter([b'a',b'bc',b''])
    def open_proc(path,flags):
        assert path=='/proc/self/status'  # No credential/source FD is opened.
        opened.append((path,flags));return 321
    def read_proc(fd,count):
        assert fd==321;reads.append(count);return next(chunks)
    monkeypatch.setattr(entry.os,'open',open_proc);monkeypatch.setattr(entry.os,'read',read_proc);monkeypatch.setattr(entry.os,'close',closed.append)
    assert entry._read_proc('/proc/self/status',4)==b'abc'
    assert opened==[('/proc/self/status',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)]
    assert reads==[5,4,2] and closed==[321]


@pytest.mark.parametrize('chunks,limit,expected,requests',[
    ([b'abcd',b''],4,b'abcd',[5,1]),
    ([b'a',b'b',b'c',b'd',b''],4,b'abcd',[5,4,3,2,1]),
    ([b'',],4,None,[5]),
    ([b'abcde'],4,None,[5]),
    ([b'ab',b'cde'],4,None,[5,3]),
])
def test_read_proc_exact_cap_overflow_and_empty_boundaries(entry,monkeypatch,chunks,limit,expected,requests):
    supplied=iter(chunks);reads=[];closed=[];opened=[]
    def open_proc(path,flags):assert path=='/proc/self/status';opened.append(path);return 322
    def read_proc(fd,count):
        assert fd==322 and count>0;reads.append(count);chunk=next(supplied);assert len(chunk)<=count;return chunk
    monkeypatch.setattr(entry.os,'open',open_proc);monkeypatch.setattr(entry.os,'read',read_proc);monkeypatch.setattr(entry.os,'close',closed.append)
    if expected is None:
        with pytest.raises(entry.EntryFailure,match='CREDENTIAL_METADATA_INVALID'):entry._read_proc('/proc/self/status',limit)
    else:assert entry._read_proc('/proc/self/status',limit)==expected
    assert reads==requests and opened==['/proc/self/status'] and closed==[322]


@pytest.mark.parametrize('after_cap,close_fails',[(False,False),(True,False),(False,True),(True,True)])
def test_read_proc_io_or_eof_error_is_not_success_and_finally_closes(entry,monkeypatch,after_cap,close_fails):
    calls=[];closed=[]
    def open_proc(path,flags):assert path=='/proc/self/status';return 323
    def read_proc(fd,count):
        assert fd==323;calls.append(count)
        if after_cap and len(calls)==1:return b'abcd'
        raise OSError('synthetic proc IO failure')
    def close_proc(fd):
        closed.append(fd)
        if close_fails:raise OSError('synthetic close uncertainty')
    monkeypatch.setattr(entry.os,'open',open_proc);monkeypatch.setattr(entry.os,'read',read_proc);monkeypatch.setattr(entry.os,'close',close_proc)
    if close_fails:
        with pytest.raises(entry.EntryFailure,match='FD_CLOSE_FAILED'):entry._read_proc('/proc/self/status',4)
        assert entry._UNCERTAIN_FDS[-1]==(323,)
    else:
        with pytest.raises(OSError,match='synthetic proc IO failure'):entry._read_proc('/proc/self/status',4)
    assert closed==[323] and calls==([5,1] if after_cap else [5])


def _server_diagnostic_probe(entry,monkeypatch,*,outcome='returned',started=False,flags=(False,False,False),capture_fails=False):
    """Only fake Config/Server methods; never import Main or run an app."""
    from types import SimpleNamespace
    import importlib
    import uvicorn
    source=ROOT/'web/backend/main.py';calls=[]
    server=SimpleNamespace(started=started)
    if flags is not None:server.lifespan=SimpleNamespace(error_occured=flags[0],startup_failed=flags[1],shutdown_failed=flags[2])
    def run():
        calls.append('run')
        if outcome=='raised':raise RuntimeError('SECRET_SENTINEL_NEVER_LOG')
    server.run=run
    monkeypatch.setattr(entry,'_code_paths',lambda **kwargs:(ROOT,source.parent,source))
    monkeypatch.setattr(entry,'_check_boundary',lambda pid,uid:calls.append('boundary'))
    monkeypatch.setattr(entry,'sys',SimpleNamespace(path=[]))
    def imported(name):
        assert name=='main';calls.append('main')
        return SimpleNamespace(__file__=str(source),_IS_PROD=True,_LAUNCH_FORMAL=True,app=object())
    monkeypatch.setattr(importlib,'import_module',imported)
    monkeypatch.setattr(uvicorn,'Config',lambda *a,**k:object())
    monkeypatch.setattr(uvicorn,'Server',lambda config:server)
    if capture_fails:
        def fail(*a):raise ValueError('SECRET_SENTINEL_NEVER_LOG')
        monkeypatch.setattr(entry,'_server_failure_snapshot',fail)
    with pytest.raises(entry.EntryFailure) as caught:entry._serve(123,999)
    assert calls==['main','boundary','run'] and caught.value.code=='SERVER_FAILED'
    return caught.value


@pytest.mark.parametrize('outcome,started,flags,record',[
    ('raised',False,(False,False,False),('raised',False,False,False,False)),
    ('returned',False,(False,False,False),('returned',False,False,False,False)),
    ('returned',True,(True,False,False),('returned',True,True,False,False)),
    ('returned',True,(False,True,False),('returned',True,False,True,False)),
    ('returned',True,(False,False,True),('returned',True,False,False,True)),
    ('returned',False,None,('returned',False,None,None,None)),
    ('returned',0,('SECRET_SENTINEL_NEVER_LOG',1,False),('returned',None,None,None,False)),
])
def test_server_diagnostic_actual_failure_branch_and_four_strict_flags(entry,monkeypatch,outcome,started,flags,record):
    failure=_server_diagnostic_probe(entry,monkeypatch,outcome=outcome,started=started,flags=flags)
    assert failure.server_failure==record
    output=_main_failure_output(entry,monkeypatch,failure)
    expected=('FORMAL_SERVER_V1:'+record[0]+':'+':'.join('-' if x is None else '1' if x else '0' for x in record[1:])+'\n').encode()
    assert output==b'FORMAL_ENTRY:SERVER_FAILED\n'+expected and b'SECRET_SENTINEL' not in output


def test_server_diagnostic_capture_formatter_and_output_failure_keep_primary(entry,monkeypatch):
    with monkeypatch.context() as patch:
        failure=_server_diagnostic_probe(entry,patch,capture_fails=True)
        assert failure.server_failure is None
    assert _main_failure_output(entry,monkeypatch,failure)==b'FORMAL_ENTRY:SERVER_FAILED\n'
    with monkeypatch.context() as patch:
        def fail(error):raise ValueError('SECRET_SENTINEL_NEVER_LOG')
        patch.setattr(entry,'_server_annotation',fail)
        assert _main_failure_output(entry,patch,failure)==b'FORMAL_ENTRY:SERVER_FAILED\n'
    from types import SimpleNamespace
    writes=[]
    def unavailable(fd,raw):writes.append((fd,raw));raise OSError('SECRET_SENTINEL_NEVER_LOG')
    monkeypatch.setattr(entry,'os',SimpleNamespace(environ={},write=unavailable))
    assert entry.main()==78 and len(writes)==1


@pytest.mark.parametrize('record',[
    ('unknown',False,False,False,False),('raised',1,False,False,False),
    ('returned',False,'secret',False,False),('returned',False,False,False),
    ['raised',False,False,False,False],None,
])
def test_server_diagnostic_invalid_or_unrelated_primary_is_omitted(entry,monkeypatch,record):
    failure=_server_diagnostic_probe(entry,monkeypatch)
    failure._server_failure=record
    assert entry._server_annotation(failure)==b''
    unrelated=entry.EntryFailure('CREDENTIAL_IO_FAILED');unrelated.__context__=failure
    assert entry._server_annotation(unrelated)==b''
    unbound=entry.EntryFailure('SERVER_FAILED');unbound._server_failure=('raised',False,False,False,False)
    assert entry._server_annotation(unbound)==b''


def _load_lifespan_diagnostic_only():
    """Compile only selected stdlib diagnostic AST, never execute Main imports."""
    import copy
    source=ROOT/'web/backend/main.py';tree=ast.parse(source.read_bytes())
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='_lifespan_primary_annotation'
              or isinstance(node,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='_LIFESPAN_FRAME_SPECS' for x in node.targets)]
    namespace={'__file__':str(source),'Path':Path}
    exec(compile(ast.Module(body=copy.deepcopy(selected),type_ignores=[]),str(source),'exec'),namespace)
    lifespan=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='lifespan')
    production=next(n for n in lifespan.body if isinstance(n,ast.If) and isinstance(n.test,ast.Name) and n.test.id=='_IS_PROD')
    protected=next(n for n in production.body if isinstance(n,ast.Try))
    handler=copy.deepcopy(protected.handlers[0])
    assert isinstance(handler.type,ast.Name) and handler.type.id=='BaseException'
    body=ast.Try(body=[ast.Raise(exc=ast.Name(id='sentinel',ctx=ast.Load()),cause=None)],handlers=[handler],orelse=[],
        finalbody=[ast.Expr(value=ast.Call(func=ast.Name(id='cleanup',ctx=ast.Load()),args=[ast.Name(id='primary',ctx=ast.Load())],keywords=[]))])
    function=ast.FunctionDef(name='lifespan',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),
        body=[ast.Assign(targets=[ast.Name(id='primary',ctx=ast.Store())],value=ast.Constant(value=None)),body],decorator_list=[])
    module=ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[]));exec(compile(module,str(source),'exec'),namespace)
    return namespace


@pytest.mark.parametrize('fault',['none','format','output'])
def test_lifespan_diagnostic_same_primary_raise_cleanup_and_failure_isolation(fault):
    from types import SimpleNamespace
    namespace=_load_lifespan_diagnostic_only();writes=[];closed=[];primary=RuntimeError('SECRET_SENTINEL_NEVER_LOG')
    namespace['sentinel']=primary;namespace['cleanup']=closed.append
    def write(fd,raw):
        writes.append((fd,raw))
        if fault=='output':raise OSError('SECRET_SENTINEL_NEVER_LOG')
    namespace['os']=SimpleNamespace(write=write)
    if fault=='format':
        def fail(error):raise ValueError('SECRET_SENTINEL_NEVER_LOG')
        namespace['_lifespan_primary_annotation']=fail
    try:namespace['lifespan']()
    except BaseException as caught:assert caught is primary
    else:raise AssertionError('original primary was swallowed')
    assert closed==[primary]
    if fault=='format':assert writes==[]
    else:
        assert len(writes)==1 and writes[0][0]==2
        assert writes[0][1].startswith(b'FORMAL_LIFESPAN_V1:RuntimeError:') and b'SECRET_SENTINEL' not in writes[0][1]


def test_lifespan_diagnostic_hostile_exception_attributes_and_external_frames_do_not_leak():
    namespace=_load_lifespan_diagnostic_only();touched=[]
    class HostileError(RuntimeError):
        def __str__(self):touched.append('str');raise AssertionError('forbidden')
        def __repr__(self):touched.append('repr');raise AssertionError('forbidden')
        def __getattribute__(self,name):
            if name in ('args','__traceback__','__context__','__cause__','__dict__'):
                touched.append(name);raise AssertionError('forbidden')
            return BaseException.__getattribute__(self,name)
    primary=HostileError('SECRET_SENTINEL_NEVER_LOG')
    try:raise primary
    except BaseException:pass
    output=namespace['_lifespan_primary_annotation'](primary)
    assert output==b'FORMAL_LIFESPAN_V1:OTHER:-\n' and touched==[]
    assert b'test_formal_secret_entry' not in output and b'SECRET_SENTINEL' not in output


def test_lifespan_diagnostic_fixed_release_coords_limited_to_eight():
    namespace=_load_lifespan_diagnostic_only();source=ROOT/'web/backend/main.py'
    exec(compile('def lifespan(n):\n if n: return lifespan(n-1)\n raise ValueError("SECRET_SENTINEL_NEVER_LOG")\n',str(source),'exec'),namespace)
    try:namespace['lifespan'](20)
    except BaseException as primary:output=namespace['_lifespan_primary_annotation'](primary)
    coords=output.split(b':',2)[2].strip().split(b';')
    assert len(coords)==8 and all(item.startswith(b'web/backend/main.py|lifespan|') for item in coords)
    assert len(output)<=2048 and b'SECRET_SENTINEL' not in output
