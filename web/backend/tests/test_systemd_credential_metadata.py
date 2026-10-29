"""Pure finite ACL/proc/metadata controls; no credential or authority is born."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import stat
import struct
from types import SimpleNamespace

import pytest
import systemd_credential_metadata as metadata

ROOT = Path(__file__).resolve().parents[3]
UID, GID = 1234, 1235


def snapshot(role='file', shape='ROOT_ACL_RO'):
    directory = role == 'directory';permission = 5 if directory else 4
    root = shape == 'ROOT_ACL_RO'
    entries = ((1, metadata.UNDEFINED, permission), (2, UID, permission), (4, metadata.UNDEFINED, 0),
               (16, metadata.UNDEFINED, permission), (32, metadata.UNDEFINED, 0))
    return dict(dev=1, ino=2, uid=0 if root else UID, gid=0 if root else GID,
        mode=(stat.S_IFDIR if directory else stat.S_IFREG) | (0o550 if directory else 0o440) if root else
             (stat.S_IFDIR if directory else stat.S_IFREG) | (0o500 if directory else 0o400),
        nlink=2 if directory else 1, size=64, mtime=10, ctime=10,
        access=('PRESENT', entries, 5) if root else ('ABSENT', (), None),
        default=('ABSENT', (), None), readonly=True, mount_id=23, mount_matches=True)


def wire(entries, version=2):
    return struct.pack('<I', version) + b''.join(struct.pack('<HHI', tag, permission, qualifier) for tag, qualifier, permission in entries)


@pytest.mark.parametrize('role', ['file', 'directory'])
@pytest.mark.parametrize('shape', metadata.SHAPES)
def test_two_exact_data_only_shapes(role, shape):
    value = snapshot(role, shape)
    assert metadata.validate_snapshot(value, role, UID, GID) == shape
    if shape == 'ROOT_ACL_RO':assert metadata.decode_acl(wire(value['access'][1])) == value['access']
    else:
        permission = 5 if role == 'directory' else 4
        value['access'] = ('PRESENT', ((1, metadata.UNDEFINED, permission), (4, metadata.UNDEFINED, 0), (32, metadata.UNDEFINED, 0)), 3)
        assert metadata.validate_snapshot(value, role, UID, GID) == shape


@pytest.mark.parametrize('change', [
    {'uid': UID}, {'gid': GID}, {'uid': 42, 'gid': 42}, {'mode': stat.S_IFREG | 0o400},
    {'mode': stat.S_IFREG | 0o460}, {'mode': stat.S_IFLNK | 0o440}, {'mode': stat.S_IFIFO | 0o440},
    {'mode': stat.S_IFSOCK | 0o440}, {'nlink': 2}, {'readonly': False}, {'readonly': None},
    {'mount_id': None}, {'mount_matches': False}, {'access': ('ABSENT', (), None)},
    {'access': ('UNSUPPORTED', (), None)}, {'default': ('PRESENT', (), 0)}, {'default': ('IO', (), None)},
])
def test_counter_metadata_never_weakens_policy(change):
    value = snapshot();value.update(change)
    with pytest.raises(ValueError):metadata.validate_snapshot(value, 'file', UID, GID)


@pytest.mark.parametrize('row', [(2, UID + 1, 4), (2, UID + 1, 0), (8, GID, 0), (8, GID, 2), (2, UID, 6)])
def test_extra_acl_even_zero_or_mask_hidden_write_rejects(row):
    value = snapshot();entries = list(value['access'][1]);entries.append(row)
    value['access'] = metadata.decode_acl(wire(entries))
    with pytest.raises(ValueError):metadata.validate_snapshot(value, 'file', UID, GID)


@pytest.mark.parametrize('raw', [b'', b'\x02', b'\x02\0\0\0x', wire(((64, metadata.UNDEFINED, 4),)),
    wire(((1, 1, 4),)), wire(((2, metadata.UNDEFINED, 4),)), wire(((1, metadata.UNDEFINED, 8),)),
    wire(((1, metadata.UNDEFINED, 4),) * 2), wire((), version=3), b'\0' * 65536])
def test_acl_wire_truncated_unknown_duplicate_or_oversize(raw):
    assert metadata.decode_acl(raw)[0] in ('INVALID', 'TOO_MANY')


@pytest.mark.parametrize('state', ['IO', 'INVALID', 'TOO_MANY'])
def test_acl_unknown_state_fail_closed(state):
    value = snapshot('file', 'SERVICE_OWNER_RO');value['access'] = (state, (), None)
    with pytest.raises(ValueError):metadata.validate_snapshot(value, 'file', UID, GID)


def mountinfo(mount_id=23, mode='ro', point=metadata.DIRECTORY):
    return f'{mount_id} 1 0:1 / {point} {mode},nosuid - tmpfs none rw\n'.encode()


@pytest.mark.parametrize('raw', [mountinfo(mode='rw'), mountinfo(point='/other'), mountinfo(24), mountinfo()+mountinfo(), b'bad\n', mountinfo().rstrip()])
def test_consumer_mount_view_exact_and_ambiguous_rejections(raw):
    with pytest.raises(ValueError):metadata.mount_matches(raw, 23)


def test_mount_readonly_is_per_mount_and_not_superblock():
    assert metadata.mount_matches(mountinfo(), 23)
    assert metadata.parse_fdinfo(b'pos:\t0\nmnt_id:\t23\n') == 23
    for raw in (b'mnt_id: 1\nmnt_id: 2\n', b'mnt_id: unknown\n', b'x' * 4097):
        with pytest.raises(ValueError):metadata.parse_fdinfo(raw)


def process_inputs():
    status = (f'Uid:\t{UID}\t{UID}\t{UID}\t{UID}\nGid:\t{GID}\t{GID}\t{GID}\t{GID}\n'
              'CapEff:\t0000000000000000\nCapPrm:\t0000000000000000\nCapAmb:\t0000000000000000\nNoNewPrivs:\t1\n').encode()
    process_stat = b'123 (synthetic) S ' + b'0 ' * 18 + b'456\n'
    return [status, b'0 0 4294967295\n', b'0 0 4294967295\n', process_stat, 123, (1, 2), (1, 3)]


def test_consumer_real_effective_saved_fs_namespace_and_capability_rules():
    args = process_inputs();value = metadata.parse_consumer(*args)
    assert value['uid'] == UID and value['start'] == 456
    for index, raw in [(0, args[0].replace(b'NoNewPrivs:\t1', b'NoNewPrivs:\t0')),
        (0, args[0].replace(b'CapAmb:\t0000000000000000', b'CapAmb:\t0000000000000001')),
        (0, args[0].replace(str(UID).encode(), b'0', 1)), (1, b'0 1000 1\n'),
        (2, b'0 0 4294967295\n0 0 1\n'), (3, args[3].replace(b'123', b'124', 1)), (5, (1, 0))]:
        bad = list(args);bad[index] = raw
        with pytest.raises(ValueError):metadata.parse_consumer(*bad)
    for field in ('uid', 'gid', 'mode', 'access', 'mount_id', 'readonly'):
        before = snapshot();after = copy.deepcopy(before);after[field] = None
        assert not metadata.same_snapshot(before, after)


def test_actual_owned_fd_without_readonly_never_passes(tmp_path):
    path = tmp_path/'synthetic-local';path.write_bytes(b'owned-local-only');path.chmod(0o400)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        captured = metadata.capture_fd(fd, b'mnt_id: 23\n', mountinfo())
        assert captured['readonly'] is False
        with pytest.raises(ValueError, match='MOUNT_RO'):metadata.validate_snapshot(captured, 'file', os.geteuid(), os.getegid())
    finally:os.close(fd)


def test_helper_import_is_stdlib_data_only_and_formal_order_is_early():
    tree = ast.parse(Path(metadata.__file__).read_bytes())
    assert all(isinstance(n, (ast.Import, ast.Assign, ast.FunctionDef, ast.Expr)) for n in tree.body)
    assert not any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) for n in tree.body)
    assert {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names} == {'errno', 'os', 'stat', 'struct'}
    entry = ast.parse((ROOT/'scripts/run-formal-main.py').read_bytes())
    main = next(n for n in entry.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    calls = [(n.lineno, n.func.id) for n in ast.walk(main) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    positions = {name:min(line for line, label in calls if label == name) for name in ('_initial_environment', '_harden_current_process', '_code_paths', '_load_metadata_helper', '_credential_directory', '_read_group')}
    assert list(positions.values()) == sorted(positions.values())


def test_public_v3_metadata_closed_shape_unknown_null_and_sticky_first_snapshot():
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('metadata_probe_control', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    value = probe.empty_receipt('a'*40);record = probe.empty_metadata('stock_base');value['credential_metadata'].append(record)
    probe.validate_receipt(value)
    assert record['consumer']['instance_stable'] is None and record['formal_pre_read'] is None
    for modify in (lambda x:x.update(raw_mountinfo='forbidden'), lambda x:x['consumer'].update(uid=True),
                   lambda x:x.update(decision='allow'), lambda x:x['objects'].append({'slot':'arbitrary'})):
        bad = copy.deepcopy(value);modify(bad['credential_metadata'][0])
        with pytest.raises(probe.ProbeFailure):probe.validate_receipt(bad)
    bad = copy.deepcopy(value);bad['credential_metadata'] *= 5
    with pytest.raises(probe.ProbeFailure):probe.validate_receipt(bad)
    controller = probe.Controller({'head':'a'*40}, None, None);controller.result['credential_metadata'] = [copy.deepcopy(record)]
    controller._phase = 'stock_base';controller._mark('credential_metadata');controller._capture(probe.ProbeFailure('UNIT'))
    first = copy.deepcopy(controller.result)
    controller._phase = 'cleanup';controller._mark('unit_cleanup');controller._capture(OSError(5, 'omitted'))
    assert controller.result == first


def test_helper_source_and_module_attestation_detects_code_global_constant_changes(monkeypatch):
    import sys
    import types
    path = ROOT/'scripts/run-formal-main.py'
    spec = importlib.util.spec_from_file_location('metadata_source_rule_entry', path);entry = importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    source_path = ROOT/'web/backend/systemd_credential_metadata.py';raw = source_path.read_bytes()
    module = types.ModuleType('systemd_credential_metadata');module.__file__ = str(source_path)
    exec(compile(raw, str(source_path), 'exec', dont_inherit=True), vars(module))
    entry._METADATA_HELPER = module
    # Finite source-reader input only; root ownership is separately refused on
    # actual owned paths. This produces metadata functions, never authority.
    monkeypatch.setattr(entry, '_source_bytes', lambda path:raw)
    monkeypatch.setitem(sys.modules, 'systemd_credential_metadata', module)
    assert entry._require_metadata_helper() is module
    for name, replacement in [('TAGS', (1,)), ('DIRECTORY', '/unapproved'), ('capture_fd', lambda *a:None)]:
        original = getattr(module, name);setattr(module, name, replacement)
        with pytest.raises(entry.EntryFailure):entry._require_metadata_helper()
        setattr(module, name, original)
    original = module.same_snapshot
    module.same_snapshot = types.FunctionType(original.__code__, {'__name__':module.__name__})
    with pytest.raises(entry.EntryFailure):entry._require_metadata_helper()
    module.same_snapshot = original
    module.extra = True
    with pytest.raises(entry.EntryFailure):entry._require_metadata_helper()
    del module.extra
    monkeypatch.setattr(entry, '_source_bytes', lambda path:raw.replace(b"return type(a) is dict", b"return False and type(a) is dict"))
    with pytest.raises(entry.EntryFailure):entry._require_metadata_helper()


def test_acl_io_errno_does_not_become_acl_absence(monkeypatch):
    import errno
    for number, state in [(errno.ENODATA, 'ABSENT'), (errno.EOPNOTSUPP, 'UNSUPPORTED'),
                          (errno.EPERM, 'IO'), (errno.EACCES, 'IO'), (errno.EIO, 'IO')]:
        def failed(*args):raise OSError(number, 'redacted')
        monkeypatch.setattr(metadata.os, 'getxattr', failed, raising=False)
        assert metadata._xattr(123, 'system.posix_acl_access')[0] == state
        if state != 'ABSENT':
            value = snapshot();value['access'] = (state, (), None)
            with pytest.raises(ValueError):metadata.validate_snapshot(value, 'file', UID, GID)


def test_consumer_namespace_and_mount_changes_remain_distinct_instances():
    before = process_inputs();original = metadata.parse_consumer(*before)
    for index, value in [(5, (1, 99)), (6, (1, 98)), (3, before[3].replace(b'456', b'457'))]:
        changed = list(before);changed[index] = value
        assert metadata.parse_consumer(*changed) != original
    for key in ('uid', 'gid', 'access', 'readonly', 'mount_id', 'mount_matches', 'ctime'):
        a = snapshot();b = copy.deepcopy(a);b[key] = None
        assert not metadata.same_snapshot(a, b)


@pytest.mark.parametrize('fault', [None, 'readonly', 'acl', 'process_gone', 'close_after_reject'])
def test_controller_records_before_policy_and_keeps_failed_snapshot(monkeypatch, tmp_path, fault):
    """Collector-only synthetic IO; a pass here creates no service or witness."""
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('metadata_recording_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    controller = probe.Controller({'head':'a'*40}, None, None);controller.uid = UID;controller.gid = GID;controller._phase = 'stock_base'
    monkeypatch.setattr(probe, 'SECRETS', tmp_path)
    consumer = dict(pid=123, start=456, uid=UID, gid=GID, user_ns=(1, 2), mount_ns=(1, 3))
    def collect_consumer(*args):
        if fault == 'process_gone':raise FileNotFoundError()
        return dict(consumer)
    monkeypatch.setattr(controller, '_metadata_helper', lambda:metadata)
    monkeypatch.setattr(controller, '_metadata_read', lambda path,limit:mountinfo())
    monkeypatch.setattr(controller, '_consumer_metadata', collect_consumer)
    monkeypatch.setattr(controller, 'unit_info', lambda:{'MainPID':'123', 'InvocationID':'a'*32})
    table = {};closed = [];next_fd = 100
    def opened(name, *args, **kwargs):
        nonlocal next_fd
        next_fd += 1;fd = next_fd;label = Path(name).name
        if label == probe.UNIT:value = snapshot('directory')
        elif label in probe.IDS:
            value = snapshot();value['ino'] = 1000 + probe.IDS.index(label)
            if label == probe.IDS[0] and fault in ('readonly', 'close_after_reject'):value['readonly'] = False
            if label == probe.IDS[0] and fault == 'acl':value['access'] = ('ABSENT', (), None)
        else:
            value = snapshot('directory', 'SERVICE_OWNER_RO');value.update(uid=0, gid=0, mode=stat.S_IFDIR|0o755, readonly=False, mount_matches=False, ino={'root':10, 'run':11, 'credentials':12}[label])
        table[fd] = value;return fd
    def fstat(fd):
        value = table[fd]
        return SimpleNamespace(st_dev=value['dev'], st_ino=value['ino'], st_uid=value['uid'], st_gid=value['gid'],
            st_mode=value['mode'], st_nlink=value['nlink'], st_size=value['size'], st_mtime_ns=value['mtime'], st_ctime_ns=value['ctime'])
    def close(fd):
        closed.append(fd)
        if fault == 'close_after_reject' and fd == min(table):raise OSError('redacted')
    monkeypatch.setattr(controller, '_metadata_capture', lambda fd,*args:copy.deepcopy(table[fd]))
    with monkeypatch.context() as patch:
        patch.setattr(probe.os, 'open', opened);patch.setattr(probe.os, 'fstat', fstat);patch.setattr(probe.os, 'close', close)
        if fault is None:assert controller._credential_metadata(123, 'a'*32) == (1, 2)
        else:
            with pytest.raises(probe.ProbeFailure):controller._credential_metadata(123, 'a'*32)
    record = controller.result['credential_metadata'][0]
    assert set(closed) == set(table) and len(closed) == len(table)
    assert record['formal_pre_read'] is None and record['native_pre_read'] is None
    if fault is None:
        assert record['decision'] == 'ROOT_ACL_RO' and len(record['objects']) == 6
        assert all(item['legacy_owner_only'] is False for item in record['objects'])
    elif fault == 'process_gone':assert record['decision'] == 'UNKNOWN' and record['check'] == 'PROCESS_GONE'
    else:
        assert record['decision'] == 'REJECT' and record['objects'][-1]['uid'] == 0
        assert record['check'] == ('ACL_SHAPE' if fault == 'acl' else 'MOUNT_RO')
    probe.validate_receipt(controller.result)
    if fault == 'close_after_reject':
        assert controller.uncertain and controller._metadata_uncertain
        assert controller.result['first_failure']['operation'] == 'credential_metadata' and controller._first_reason == 'UNIT'


@pytest.mark.parametrize('index,permission', [(1, 6), (2, 2), (3, 6), (4, 4)])
def test_five_entry_mask_hidden_write_or_effective_other_read_never_allowed(index, permission):
    value = snapshot();entries = list(value['access'][1]);tag, qualifier, _ = entries[index];entries[index] = (tag, qualifier, permission)
    value['access'] = metadata.decode_acl(wire(entries))
    with pytest.raises(ValueError):metadata.validate_snapshot(value, 'file', UID, GID)


def test_owner_fallback_requires_ro_even_when_acl_not_supported():
    value = snapshot('directory', 'SERVICE_OWNER_RO');value['access'] = ('UNSUPPORTED', (), None);value['default'] = ('UNSUPPORTED', (), None)
    assert metadata.validate_snapshot(value, 'directory', UID, GID) == 'SERVICE_OWNER_RO'
    value['readonly'] = False
    with pytest.raises(ValueError, match='MOUNT_RO'):metadata.validate_snapshot(value, 'directory', UID, GID)


def test_v3_complete_pass_dto_and_missing_observation_rejections():
    """A finite serializer control, never an observed Linux/pass capability."""
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('metadata_pass_dto_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    value = probe.empty_receipt('a'*40);value.update(outcome='PASS', reason='OK')
    value['phases'] = {phase:True for phase in probe.PHASES}
    for key in ('initial_empty', 'normal_restart_unchanged', 'pre_get_closed_unreserved'):value['financial'][key] = True
    value['resources'].update(cgroup_empty=True, credential_mount_gone=True, unit_removed=True, directories_removed=True, user_removed=True, cleanup_uncertain=False)
    for key in ('source_closed', 'native_closed', 'proof_taken', 'component_woken', 'same_deadline_ref', 'within_main_deadline'):value['instrumented'][key] = True
    value['instrumented']['observer_failed'] = False
    for phase in probe.PHASES:
        record = probe.empty_metadata(phase);record['decision'] = 'ROOT_ACL_RO'
        record['consumer'] = dict(uid=UID, gid=GID, identity_matches=True, instance_stable=True, namespace_stable=True, initial_maps=True)
        for slot in probe.METADATA_SLOTS[:-1] if phase == 'stock_base' else probe.METADATA_SLOTS:
            role = 'directory' if slot == 'DIRECTORY' else 'file';data = snapshot(role);item = probe.empty_metadata_object(slot)
            item.update(kind='directory' if role=='directory' else 'regular', uid=0, gid=0, mode=stat.S_IMODE(data['mode']), nlink=data['nlink'], held_named_same=True, readonly=True, mount_matches=True, decision='ROOT_ACL_RO', legacy_owner_only=False)
            for key in ('access', 'default'):
                acl = data[key];item[key] = dict(state=acl[0], entries=[list(row) for row in acl[1]], count=acl[2])
            record['objects'].append(item)
        value['credential_metadata'].append(record)
    from .test_native_ready_diagnostics import complete_diagnostics
    complete_diagnostics(probe,value)
    raw = probe.validate_receipt(value);assert len(raw) <= 32768
    assert probe.validate_receipt(probe.strict_json(raw)) == raw
    for fault in ('unknown_consumer', 'missing_phase', 'missing_object', 'too_many_without_count'):
        bad = copy.deepcopy(value)
        if fault == 'unknown_consumer':bad['credential_metadata'][0]['consumer']['instance_stable'] = None
        elif fault == 'missing_phase':bad['credential_metadata'].pop()
        elif fault == 'missing_object':bad['credential_metadata'][0]['objects'].pop()
        else:bad['credential_metadata'][0]['objects'][0]['access'] = dict(state='TOO_MANY', entries=[], count=None)
        with pytest.raises(probe.ProbeFailure):probe.validate_receipt(bad)


@pytest.mark.parametrize('drift', [False, True])
def test_current_thread_collection_keeps_process_binding_without_persisting_tid(monkeypatch, drift):
    path = ROOT/'scripts/run-formal-main.py'
    spec = importlib.util.spec_from_file_location('thread_collector_entry', path);entry = importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    entry._METADATA_HELPER = metadata
    raw = Path(metadata.__file__).read_bytes();monkeypatch.setattr(entry, '_source_bytes', lambda path:raw)
    uid, gid, pid = os.geteuid(), os.getegid(), os.getpid()
    args = process_inputs();status = args[0].replace(str(UID).encode(), str(uid).encode()).replace(str(GID).encode(), str(gid).encode())
    values = {'/proc/thread-self/status':status, '/proc/thread-self/uid_map':args[1], '/proc/thread-self/gid_map':args[2], '/proc/self/stat':args[3].replace(b'123 (', str(pid).encode()+b' (', 1)}
    seen = [];count = 0;native_stat = os.stat
    def read(path, limit):seen.append(path);return values[path]
    def ns_stat(path, *a, **kw):
        nonlocal count
        if path not in ('/proc/thread-self/ns/user', '/proc/thread-self/ns/mnt'):return native_stat(path, *a, **kw)
        count += 1
        return SimpleNamespace(st_dev=1, st_ino=99 if drift and count==3 else 2 if str(path).endswith('user') else 3)
    monkeypatch.setattr(entry, '_read_proc', read)
    with monkeypatch.context() as patch:
        patch.setattr(entry.os, 'stat', ns_stat)
        patch.setattr(entry.os, 'getresuid', lambda:(uid,)*3, raising=False)
        patch.setattr(entry.os, 'getresgid', lambda:(gid,)*3, raising=False)
        if drift:
            with pytest.raises(entry.EntryFailure, match='BOUNDARY_CHANGED'):entry._capture_consumer()
        else:
            value = entry._capture_consumer();assert value['pid']==pid and set(value)==set(metadata.CONSUMER_FIELDS)
            assert 'tid' not in value and 'thread_id' not in value
    assert '/proc/thread-self/status' in seen and '/proc/self/stat' in seen


def _canonical_helper_input(monkeypatch, entry):
    import sys
    import types
    path = ROOT/'web/backend/systemd_credential_metadata.py';raw = path.read_bytes()
    module = types.ModuleType('systemd_credential_metadata');module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec', dont_inherit=True), vars(module))
    entry._METADATA_HELPER = module
    monkeypatch.setattr(entry, '_source_bytes', lambda path:raw)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module, raw


def _different_function_builtins(module, name):
    import builtins
    import types
    original = getattr(module, name);trusted = module.__builtins__
    altered = dict(vars(builtins));altered['bool'] = lambda value:True
    module.__builtins__ = altered
    replacement = types.FunctionType(original.__code__, vars(module), original.__name__, original.__defaults__)
    replacement.__kwdefaults__ = original.__kwdefaults__
    module.__builtins__ = trusted;setattr(module, name, replacement)
    assert replacement.__code__ == original.__code__ and replacement.__globals__ is original.__globals__
    assert replacement.__builtins__ is altered and module.__builtins__ is trusted
    return replacement


def test_repair_function_actual_builtins_refused_before_collector(monkeypatch):
    path = ROOT/'scripts/run-formal-main.py'
    spec = importlib.util.spec_from_file_location('repair_formal_builtins', path);entry = importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    module, _ = _canonical_helper_input(monkeypatch, entry)
    assert entry._require_metadata_helper() is module
    _different_function_builtins(module, 'capture_fd')
    with pytest.raises(entry.EntryFailure, match='CODE_IDENTITY_INVALID'):entry._require_metadata_helper()


def _ancestor_chain_input(monkeypatch, tmp_path):
    from services import native_live_credentials as native
    ancestor = tmp_path/'owned-ancestor';ancestor.mkdir();info = ancestor.stat()
    before = snapshot('directory');before.update(dev=info.st_dev, ino=info.st_ino, uid=0, gid=0,
        mode=stat.S_IFDIR|0o755, nlink=info.st_nlink, size=info.st_size, mtime=info.st_mtime_ns, ctime=info.st_ctime_ns,
        access=('ABSENT', (), None), readonly=False, mount_matches=False)
    states = [dict(before) for _ in range(3)] + [snapshot('directory')]
    entry = SimpleNamespace(_require_metadata_helper=lambda:metadata)
    entry._metadata_pair = lambda parent,name,fd,uid,role:(states[fd], metadata.validate_snapshot(states[fd], role, UID, GID))
    monkeypatch.setattr(native, '_formal_metadata_entry', lambda:entry)
    monkeypatch.setattr(native.os, 'get_inheritable', lambda fd:False)
    return native, ancestor, states


def test_repair_ancestor_unrelated_add_remove_preserves_credential_chain(tmp_path, monkeypatch):
    native, ancestor, states = _ancestor_chain_input(monkeypatch, tmp_path)
    original = native._directory_snapshots((0, 1, 2, 3), UID)
    for create in (True, False):
        if create:(ancestor/'unrelated.pid').write_bytes(b'owned synthetic data');(ancestor/'unrelated-child').mkdir()
        else:(ancestor/'unrelated.pid').unlink();(ancestor/'unrelated-child').rmdir()
        info = ancestor.stat();states[1] = dict(states[1], nlink=info.st_nlink, size=info.st_size, mtime=info.st_mtime_ns, ctime=info.st_ctime_ns)
        native._check_directories((0, 1, 2, 3), original, UID)


def _complete_policy_receipt(probe, shape='ROOT_ACL_RO'):
    value = probe.empty_receipt('a'*40);value.update(outcome='PASS', reason='OK')
    value['phases'] = {phase:True for phase in probe.PHASES}
    for key in ('initial_empty', 'normal_restart_unchanged', 'pre_get_closed_unreserved'):value['financial'][key] = True
    value['resources'].update(cgroup_empty=True, credential_mount_gone=True, unit_removed=True, directories_removed=True, user_removed=True, cleanup_uncertain=False)
    for key in ('source_closed', 'native_closed', 'proof_taken', 'component_woken', 'same_deadline_ref', 'within_main_deadline'):value['instrumented'][key] = True
    value['instrumented']['observer_failed'] = False
    for phase in probe.PHASES:
        record = probe.empty_metadata(phase);record['decision'] = shape
        record['consumer'] = dict(uid=UID, gid=GID, identity_matches=True, instance_stable=True, namespace_stable=True, initial_maps=True)
        for slot in probe.METADATA_SLOTS[:-1] if phase=='stock_base' else probe.METADATA_SLOTS:
            role = 'directory' if slot=='DIRECTORY' else 'file';data = snapshot(role, shape);item = probe.empty_metadata_object(slot)
            item.update(kind='directory' if role=='directory' else 'regular', uid=data['uid'], gid=data['gid'], mode=stat.S_IMODE(data['mode']), nlink=data['nlink'], held_named_same=True, readonly=True, mount_matches=True, decision=shape, legacy_owner_only=shape=='SERVICE_OWNER_RO')
            for key in ('access', 'default'):
                acl = data[key];item[key] = dict(state=acl[0], entries=[list(row) for row in acl[1]], count=acl[2])
            record['objects'].append(item)
        value['credential_metadata'].append(record)
    from .test_native_ready_diagnostics import complete_diagnostics
    complete_diagnostics(probe,value)
    return value


@pytest.mark.parametrize('fault', ['wrong_owner', 'writable_mode', 'no_acl', 'default_acl', 'wrong_acl_user'])
def test_repair_v3_contradictory_success_projection_rejected(fault):
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_projection_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    value = _complete_policy_receipt(probe);leaf = value['credential_metadata'][0]['objects'][1]
    if fault=='wrong_owner':leaf['uid'] = 9876
    elif fault=='writable_mode':leaf['mode'] = 0o666
    elif fault=='no_acl':leaf['access'] = dict(state='ABSENT', entries=[], count=None)
    elif fault=='default_acl':leaf['default'] = copy.deepcopy(leaf['access'])
    else:leaf['access']['entries'][1][1] = 9876
    with pytest.raises(probe.ProbeFailure):probe.validate_receipt(value)


def test_function_builtins_controller_seam_rejects_same_code_mapping(monkeypatch, tmp_path):
    import sys
    import types
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_controller_builtins', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    source = ROOT/'web/backend/systemd_credential_metadata.py';raw = source.read_bytes()
    monkeypatch.setattr(probe, 'DEPOT', tmp_path/'owned-source-input')
    frozen = probe.DEPOT/'web/backend/systemd_credential_metadata.py';frozen.parent.mkdir(parents=True);frozen.write_bytes(raw)
    module = types.ModuleType('systemd_credential_metadata');module.__file__ = str(frozen)
    exec(compile(raw, str(frozen), 'exec', dont_inherit=True), vars(module))
    controller = probe.Controller({'head':'a'*40}, None, None);controller._metadata_module = module
    monkeypatch.setitem(sys.modules, module.__name__, module)
    native_lstat = Path.lstat
    def source_info(path, *a, **kw):
        info = native_lstat(path, *a, **kw)
        if path != frozen:return info
        # Finite source-owner collector input; no root-owned FS is simulated as
        # evidence. This isolates the subsequent function identity predicate.
        return SimpleNamespace(st_uid=0, **{name:getattr(info, name) for name in ('st_dev','st_ino','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')})
    monkeypatch.setattr(Path, 'lstat', source_info)
    assert controller._metadata_helper() is module
    _different_function_builtins(module, 'capture_fd')
    with pytest.raises(probe.ProbeFailure):controller._metadata_helper()


def test_function_builtins_native_to_formal_seam_rejects_before_capture(monkeypatch):
    import builtins
    import sys
    import types
    from services import native_live_credentials as native
    path = ROOT/'scripts/run-formal-main.py';raw = path.read_bytes()
    entry = types.ModuleType('__main__');entry.__file__ = str(path)
    definitions = ast.parse(raw)
    assert isinstance(definitions.body[-1], ast.If) and ast.unparse(definitions.body[-1].test) == "__name__ == '__main__'"
    definitions.body.pop()  # Keep function code/lineno; never invoke Formal main.
    exec(compile(definitions, str(path), 'exec', dont_inherit=True), vars(entry))
    _canonical_helper_input(monkeypatch, entry)
    monkeypatch.setitem(sys.modules, '__main__', entry)
    # __main__ may expose the interpreter module rather than its same dict;
    # functions still must hold that interpreter's actual builtin dictionary.
    entry.__builtins__ = builtins
    assert native._formal_metadata_entry() is entry
    _different_function_builtins(entry, '_capture_metadata')
    with pytest.raises(Exception) as rejected:native._formal_metadata_entry()
    assert rejected.value.code == 'FUNDING_CLOSED'


def test_function_builtins_formal_to_native_seam_rejects_before_publish(monkeypatch):
    import sys
    import types
    from services import native_live_credentials as original
    path = ROOT/'scripts/run-formal-main.py'
    spec = importlib.util.spec_from_file_location('repair_formal_native_seam', path);entry = importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
    path = ROOT/'web/backend/services/native_live_credentials.py'
    module = types.ModuleType('services.native_live_credentials');module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec', dont_inherit=True), vars(module))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    entry._validate_entry_module(module, ROOT)
    _different_function_builtins(module, '_publish_entry_directory')
    with pytest.raises(entry.EntryFailure):entry._validate_entry_module(module, ROOT)
    assert not module._ENTRIES and not module._KEYS and not original._ENTRIES and not original._KEYS


@pytest.mark.parametrize('field', ['dev','ino','uid','gid','mode','access','default','readonly','mount_id','mount_matches'])
def test_ancestor_security_projection_drift_still_refused(tmp_path, monkeypatch, field):
    native, _, states = _ancestor_chain_input(monkeypatch, tmp_path)
    original = native._directory_snapshots((0,1,2,3), UID)
    changed = dict(states[1])
    if field == 'access':changed[field] = ('PRESENT', ((1, metadata.UNDEFINED, 7), (4, metadata.UNDEFINED, 5), (32, metadata.UNDEFINED, 5)), 3)
    elif field == 'default':changed[field] = ('UNSUPPORTED', (), None)
    elif field in ('readonly','mount_matches'):changed[field] = not changed[field]
    elif field == 'mode':changed[field] = stat.S_IFDIR|0o700
    else:changed[field] += 1
    states[1] = changed
    with pytest.raises(Exception):native._check_directories((0,1,2,3), original, UID)


@pytest.mark.parametrize('field', ['size','mtime','ctime','nlink'])
def test_final_credential_directory_stays_full_snapshot(tmp_path, monkeypatch, field):
    native, _, states = _ancestor_chain_input(monkeypatch, tmp_path)
    original = native._directory_snapshots((0,1,2,3), UID)
    states[3] = dict(states[3]);states[3][field] += 1
    with pytest.raises(Exception):native._check_directories((0,1,2,3), original, UID)


@pytest.mark.parametrize('shape', metadata.SHAPES)
def test_public_projection_and_complete_receipt_use_the_same_policy(shape):
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_shared_projection_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    value = _complete_policy_receipt(probe, shape);raw = probe.validate_receipt(value)
    assert probe.validate_receipt(probe.strict_json(raw)) == raw
    for role in ('directory','file'):
        current = snapshot(role, shape);projection = metadata.snapshot_projection(current)
        assert metadata.validate_projection(projection, role, UID, GID) == metadata.validate_snapshot(current, role, UID, GID) == shape
        assert set(projection) == set(metadata.PROJECTION_FIELDS)
        assert not {'dev','ino','size','mtime','ctime','mount_id'}.intersection(projection)


@pytest.mark.parametrize('field,value', [('gid',9876),('mode',0o500),('nlink',2),('readonly',False),('mount_matches',False),('held_named_same',False),('legacy_owner_only',False)])
def test_owner_fallback_receipt_requires_all_success_facts(field, value):
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_owner_projection_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    receipt = _complete_policy_receipt(probe, 'SERVICE_OWNER_RO');receipt['credential_metadata'][0]['objects'][1][field] = value
    with pytest.raises(probe.ProbeFailure):probe.validate_receipt(receipt)


def test_public_projection_fixed_source_ignores_preinjected_module(monkeypatch):
    import sys
    import types
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_projection_injection_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    fake = types.ModuleType('systemd_credential_metadata');fake.validate_projection = lambda *a:'ROOT_ACL_RO'
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    receipt = _complete_policy_receipt(probe);receipt['credential_metadata'][0]['objects'][1]['mode'] = 0o666
    with pytest.raises(probe.ProbeFailure):probe.validate_receipt(receipt)


def test_capture_atomicity_still_observes_full_stat_change(monkeypatch, tmp_path):
    path = tmp_path/'owned-metadata-only';path.write_bytes(b'owned synthetic bytes')
    fd = os.open(path, os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);original = os.fstat;calls = 0
    def changed(descriptor):
        nonlocal calls
        info = original(descriptor)
        if descriptor != fd:return info
        calls += 1
        data = {name:getattr(info,name) for name in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')}
        if calls == 2:data['st_mtime_ns'] += 1
        return SimpleNamespace(**data)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(metadata.os, 'fstat', changed)
            with pytest.raises(ValueError, match='IDENTITY'):metadata.capture_fd(fd,b'mnt_id: 23\n',mountinfo())
    finally:os.close(fd)


def test_public_projection_source_close_failure_cannot_serialize_pass(monkeypatch):
    path = ROOT/'scripts/probe-native-linux-lifecycle.py'
    spec = importlib.util.spec_from_file_location('repair_projection_close_probe', path);probe = importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    value = _complete_policy_receipt(probe);before = probe.canonical(value);closed = [];native_close = os.close
    def close_after(descriptor):
        native_close(descriptor);closed.append(descriptor);raise OSError('owned code-reader close uncertainty')
    with monkeypatch.context() as patch:
        patch.setattr(probe.os, 'close', close_after)
        with pytest.raises(probe.ProbeFailure):probe.validate_receipt(value)
    assert len(closed) == 1 and probe.canonical(value) == before
    with pytest.raises(OSError):os.fstat(closed[0])
