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
