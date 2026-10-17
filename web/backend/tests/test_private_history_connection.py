"""Four real SQLite stores on synthetic private roots; no API admission bypass."""
from pathlib import Path
import errno
import os
import sqlite3
import pytest
from services import runtime_paths as paths, sqlite_utils
from services.history_db import HistoryDB
from services.report_store import ReportStore
from services.connections_store import ConnectionsStore
from services.connections_p3_store import ConnectionsP3Store

STORES = (HistoryDB, ReportStore, ConnectionsStore, ConnectionsP3Store)


@pytest.fixture
def private(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    state, cache, logs = root / 'state', root / 'cache', root / 'state/logs'
    for directory in (state, cache, logs):directory.mkdir(mode=0o700)
    monkeypatch.setattr(paths, 'STATE_ROOT', state)
    monkeypatch.setattr(paths, 'CACHE_ROOT', cache)
    monkeypatch.setattr(paths, 'LOG_ROOT', logs)
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    return state / 'history.db'


@pytest.fixture
def native(monkeypatch):
    original = sqlite3.connect
    observed = []
    def connected(*args, **kwargs):
        conn = original(*args, **kwargs)
        observed.append((args, kwargs, conn))
        return conn
    monkeypatch.setattr(sqlite3, 'connect', connected)
    yield observed
    for _args, _kwargs, conn in observed:
        with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')


def assert_closed(connection, witness):
    with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
    assert witness.file_identity is None and witness.parent_fd is None


@pytest.mark.parametrize('store_class', STORES)
def test_real_store_formal_open_is_canonical_rw_and_private(private, native, store_class):
    store = store_class(private)
    assert private.stat().st_mode & 0o777 == 0o600
    with store._connect() as conn:
        witness = conn._history_file
        assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == private
        assert conn.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        for suffix in ('-wal', '-shm', '-journal'):
            side = private.with_name(private.name + suffix)
            if side.exists():assert side.stat().st_mode & 0o777 == 0o600
    assert_closed(conn, witness)
    for args, kwargs, _conn in native:
        assert args == (private.as_uri() + '?mode=rw',)
        assert kwargs['uri'] is True
        assert kwargs['factory'] is sqlite_utils.PrivateHistoryConnection


def test_four_real_stores_share_one_database_and_preserve_sql_schema(private, native):
    stores = [constructor(private) for constructor in STORES]
    with stores[0]._connect() as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'history', 'reports', 'structural_fingerprints', 'match_requests',
            'referrals', 'connections_messages', 'connections_prefs'} <= tables
    row_id = stores[0].record('synthetic-device', 'synthetic query', 'search', None)
    assert stores[0].list_recent('synthetic-device', limit=10)[0]['id'] == row_id
    assert stores[2].export_all_for_user('fixture@example.invalid') == []
    assert all(not rows for rows in stores[3].export_all_for_user('fixture@example.invalid').values())


@pytest.mark.parametrize('store_class', STORES)
@pytest.mark.parametrize('bad', ['repo', 'relative', 'uri', 'different-name'])
def test_wrong_formal_target_rejected_before_mkdir_or_sql(private, native, monkeypatch, store_class, bad):
    target = {'repo': Path(__file__).resolve().parents[1] / 'data/history.db',
              'relative': Path('history.db'), 'uri': 'file:' + str(private),
              'different-name': private.with_name('shadow.db')}[bad]
    attempted = []
    def mkdir(*_a, **_k):attempted.append('mkdir');raise AssertionError('formal constructor mkdir')
    monkeypatch.setattr(Path, 'mkdir', mkdir)
    with pytest.raises(paths.RuntimePathError):store_class(target)
    assert attempted == [] and native == [] and not private.exists()


@pytest.mark.parametrize('fault', ['missing-parent', 'parent-mode', 'symlink-parent', 'file-mode',
                                  'file-symlink', 'file-hardlink', 'file-fifo'])
def test_unsafe_formal_state_never_opens_sqlite(private, native, fault):
    if fault == 'missing-parent':
        private.parent.joinpath('logs').rmdir();private.parent.rmdir()
    elif fault == 'parent-mode':private.parent.chmod(0o755)
    elif fault == 'symlink-parent':
        moved = private.parent.with_name('real-state');private.parent.rename(moved)
        private.parent.symlink_to(moved, target_is_directory=True)
    elif fault == 'file-symlink':private.symlink_to(private.with_name('outside'))
    elif fault == 'file-fifo':os.mkfifo(private, 0o600)
    else:
        private.write_bytes(b'');private.chmod(0o644 if fault == 'file-mode' else 0o600)
        if fault == 'file-hardlink':os.link(private, private.with_name('alias'))
    with pytest.raises((paths.RuntimePathError, OSError)):HistoryDB(private)
    assert native == []


@pytest.mark.parametrize('suffix', ['-wal', '-shm', '-journal'])
def test_orphan_sidecars_are_rejected_not_absorbed(private, native, suffix):
    side = private.with_name(private.name + suffix)
    side.write_bytes(b'synthetic orphan');side.chmod(0o600)
    with pytest.raises(paths.RuntimePathError):HistoryDB(private)
    assert not private.exists() and native == []


@pytest.mark.parametrize('winner', ['private', 'unsafe', 'disappeared'])
def test_exclusive_creation_eexist_only_revalidates_actual_winner(private, native, monkeypatch, winner):
    original = os.open
    injected = []
    def racing(path, flags, *args, **kwargs):
        if path == 'history.db' and flags & os.O_EXCL:
            assert not injected
            injected.append(True)
            if winner != 'disappeared':
                fd = original(path, flags, *args, **kwargs);os.close(fd)
                if winner == 'unsafe':private.chmod(0o644)
            raise FileExistsError(errno.EEXIST, 'synthetic competing creator')
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(os, 'open', racing)
    if winner == 'private':HistoryDB(private);assert native
    else:
        with pytest.raises(paths.RuntimePathError):HistoryDB(private)
        assert native == []
    assert injected == [True]


def test_sidecar_arriving_during_fresh_creation_is_rejected(private, native, monkeypatch):
    original = os.open
    injected = []
    def racing(path, flags, *args, **kwargs):
        fd = original(path, flags, *args, **kwargs)
        if path == 'history.db' and flags & os.O_EXCL:
            side = private.with_name(private.name + '-wal')
            side.write_bytes(b'synthetic orphan');side.chmod(0o600);injected.append(True)
        return fd
    monkeypatch.setattr(os, 'open', racing)
    with pytest.raises(paths.RuntimePathError):HistoryDB(private)
    assert injected == [True] and native == []
    # A failed precreation is not an excuse to absorb the orphan on retry.
    with pytest.raises(paths.RuntimePathError):HistoryDB(private)
    assert native == []


def test_missing_database_after_initialization_is_not_recreated(private, native):
    store = HistoryDB(private);before = len(native);private.unlink()
    with pytest.raises(paths.RuntimePathError):store._connect()
    assert len(native) == before and not private.exists()


def test_native_mode_rw_will_not_recreate_file_lost_at_connect(private, native, monkeypatch):
    store = HistoryDB(private);original = sqlite3.connect;changed = []
    def removed(*args, **kwargs):
        private.unlink();changed.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(sqlite3, 'connect', removed)
    with pytest.raises(sqlite3.OperationalError):store._connect()
    assert changed == [True] and not private.exists()


@pytest.mark.parametrize('change', ['parent-mode', 'parent-identity', 'file-identity', 'sidecar-mode'])
def test_native_open_then_path_change_closes_real_connection(private, native, monkeypatch, change):
    store = HistoryDB(private);original = sqlite3.connect;changed = []
    def after_open(*args, **kwargs):
        conn = original(*args, **kwargs)
        if change == 'parent-mode':private.parent.chmod(0o755)
        elif change == 'parent-identity':
            private.parent.rename(private.parent.with_name('held-state'))
            private.parent.mkdir(mode=0o700)
        elif change == 'file-identity':
            private.rename(private.with_name('held.db'));private.write_bytes(b'');private.chmod(0o600)
        else:
            side = private.with_name(private.name + '-wal');side.write_bytes(b'bad sidecar');side.chmod(0o644)
        changed.append(True)
        return conn
    monkeypatch.setattr(sqlite3, 'connect', after_open)
    with pytest.raises(paths.RuntimePathError):store._connect()
    assert changed == [True]


def test_real_pragma_authorizer_denial_closes_connection(private, native, monkeypatch):
    store = HistoryDB(private);original = sqlite3.connect
    def denied(*args, **kwargs):
        conn = original(*args, **kwargs)
        conn.set_authorizer(lambda action, name, *_args: sqlite3.SQLITE_DENY
                            if action == sqlite3.SQLITE_PRAGMA and name == 'journal_mode'
                            else sqlite3.SQLITE_OK)
        return conn
    monkeypatch.setattr(sqlite3, 'connect', denied)
    with pytest.raises(sqlite3.DatabaseError):store._connect()


def test_real_pragma_permission_change_is_rechecked(private, native, monkeypatch):
    store = HistoryDB(private);original = sqlite3.connect;changed = []
    def mutate(*args, **kwargs):
        conn = original(*args, **kwargs)
        def authorizer(action, name, *_args):
            if action == sqlite3.SQLITE_PRAGMA and name == 'journal_mode' and not changed:
                private.parent.chmod(0o755);changed.append(True)
            return sqlite3.SQLITE_OK
        conn.set_authorizer(authorizer)
        return conn
    monkeypatch.setattr(sqlite3, 'connect', mutate)
    with pytest.raises(paths.RuntimePathError):store._connect()
    assert changed == [True]


def test_real_transaction_commit_and_error_rollback_close_all_witnesses(private, native):
    store = HistoryDB(private)
    with store._connect() as conn:
        committed = conn._history_file
        conn.execute("INSERT INTO history(device_id,query,kind) VALUES('d','kept','search')")
    assert_closed(conn, committed)
    with pytest.raises(ValueError):
        with store._connect() as conn:
            rolled_back = conn._history_file
            conn.execute("INSERT INTO history(device_id,query,kind) VALUES('d','rolled-back','search')")
            raise ValueError('synthetic task failure')
    assert_closed(conn, rolled_back)
    assert [r['query'] for r in store.list_recent('d', limit=10)] == ['kept']


def test_parent_change_at_transaction_end_rolls_back_and_closes(private, native):
    store = HistoryDB(private)
    with pytest.raises(paths.RuntimePathError):
        with store._connect() as conn:
            witness = conn._history_file
            conn.execute("INSERT INTO history(device_id,query,kind) VALUES('d','rolled-back','search')")
            private.parent.chmod(0o755)
    assert_closed(conn, witness)
    private.parent.chmod(0o700)
    assert store.list_recent('d', limit=10) == []


@pytest.mark.parametrize('store_class', STORES)
def test_formal_store_does_not_downgrade_when_environment_changes(private, native, monkeypatch, store_class):
    store = store_class(private);monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    with store._connect() as conn:assert isinstance(conn, sqlite_utils.PrivateHistoryConnection)


@pytest.mark.parametrize('store_class', STORES)
def test_development_defaults_and_legacy_connection_semantics_remain(tmp_path, monkeypatch, store_class):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev');db = tmp_path / 'legacy-nested/history.db'
    store = store_class(db)
    with store._connect() as conn:
        assert type(conn) is sqlite_utils.ClosingConnection
        assert Path(conn.execute('PRAGMA database_list').fetchone()[2]) == db


def test_real_four_store_records_exports_deletes_and_report_restore(private, native, monkeypatch):
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET', 'synthetic-unit-share-secret-never-live')
    history, reports, fingerprints, messages = [constructor(private) for constructor in STORES]
    created = reports.create(query='synthetic report', b_id='fixture', lang='en',
                             payload={'synthetic': True}, model='fixture', creator_anon_id='device')
    reports.claim_by_anon('device', 'synthetic-subject')
    snapshot = reports.export_by_owner('synthetic-subject')
    assert snapshot['reports'][0]['id'] == created['id']
    reports.delete_by_owner('synthetic-subject')
    assert reports.export_by_owner('synthetic-subject')['reports'] == []
    reports.restore_owner_snapshot(snapshot)
    assert reports.get_by_id(created['id'])['owner_user_id'] == 'synthetic-subject'
    fid = fingerprints.create_fingerprint(user_email='fixture@example.invalid', problem_summary='synthetic')
    assert fingerprints.export_all_for_user('fixture@example.invalid')[0]['id'] == fid
    mid = messages.create_message(from_email='fixture@example.invalid', to_email='peer@example.invalid', body='synthetic')
    assert messages.export_all_for_user('fixture@example.invalid')['connections_messages'][0]['id'] == mid
    assert fingerprints.delete_all_for_user('fixture@example.invalid') == 1
    assert messages.delete_all_for_user('fixture@example.invalid')['connections_messages'] == 1


@pytest.mark.parametrize('fault', ['orphan', 'connect-change', 'pragma-denial', 'success', 'rollback'])
def test_all_witness_fds_close_on_real_success_and_failures(private, native, monkeypatch, fault):
    original_close = paths.PrivateHistoryFile.close
    closed = []
    def checked_close(witness):
        held = [witness.parent_fd] if witness.parent_fd is not None else []
        try:
            return original_close(witness)
        finally:
            for fd in held:
                with pytest.raises(OSError):os.fstat(fd)
                closed.append(fd)
    monkeypatch.setattr(paths.PrivateHistoryFile, 'close', checked_close)
    if fault == 'orphan':
        side = private.with_name(private.name + '-wal');side.write_bytes(b'orphan');side.chmod(0o600)
        with pytest.raises(paths.RuntimePathError):HistoryDB(private)
    else:
        store = HistoryDB(private)
        if fault in ('connect-change', 'pragma-denial'):
            original_connect = sqlite3.connect
            def faulty(*args, **kwargs):
                conn = original_connect(*args, **kwargs)
                if fault == 'connect-change':private.parent.chmod(0o755)
                else:conn.set_authorizer(lambda action, name, *_: sqlite3.SQLITE_DENY
                                        if action == sqlite3.SQLITE_PRAGMA and name == 'journal_mode'
                                        else sqlite3.SQLITE_OK)
                return conn
            monkeypatch.setattr(sqlite3, 'connect', faulty)
            with pytest.raises((paths.RuntimePathError, sqlite3.DatabaseError)):store._connect()
        elif fault == 'rollback':
            with pytest.raises(ValueError):
                with store._connect():raise ValueError('synthetic')
        else:
            with store._connect() as conn:assert conn.execute('SELECT 1').fetchone()[0] == 1
    assert closed


def test_explicit_commit_rechecks_before_data_is_committed(private, native):
    store = HistoryDB(private)
    with pytest.raises(paths.RuntimePathError):
        with store._connect() as conn:
            conn.execute("INSERT INTO history(device_id,query,kind) VALUES('d','not-committed','search')")
            private.parent.chmod(0o755)
            conn.commit()
    private.parent.chmod(0o700)
    assert store.list_recent('d', limit=10) == []


def test_context_entry_failure_and_direct_double_close_release_witnesses(private, native):
    store = HistoryDB(private)
    conn = store._connect();witness = conn._history_file
    private.parent.chmod(0o755)
    with pytest.raises(paths.RuntimePathError):
        with conn:raise AssertionError('unsafe context entered')
    assert_closed(conn, witness)
    private.parent.chmod(0o700)
    conn = store._connect();witness = conn._history_file
    conn.close();conn.close()
    assert_closed(conn, witness)


@pytest.mark.parametrize('store_class', STORES)
def test_old_development_store_cannot_bypass_later_formal_policy(private, native, monkeypatch, store_class):
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    store = store_class(private.parent.parent / 'legacy/history.db')
    before = len(native)
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    with pytest.raises(paths.RuntimePathError):store._connect()
    assert len(native) == before


_WAL_CHILD = r'''
import os,sys,json,sqlite3,socket
from pathlib import Path
from urllib.parse import unquote,urlsplit
owned=Path(os.environ['TMPDIR']).resolve();fdpaths={};pending=[None]
raw_open,raw_close=os.open,os.close

def absolute(path,dir_fd=None):
 p=Path(os.fsdecode(path))
 if not p.is_absolute():p=(fdpaths[dir_fd] if dir_fd is not None else Path.cwd())/p
 return p

def opened(path,flags,*a,**k):
 full=absolute(path,k.get('dir_fd'));previous=pending[0];pending[0]=full
 try:fd=raw_open(path,flags,*a,**k)
 finally:pending[0]=previous
 fdpaths[fd]=full
 return fd

def closed(fd):
 try:return raw_close(fd)
 finally:fdpaths.pop(fd,None)
os.open,os.close=opened,closed

def guarded(event,args):
 if event=='open':
  name,mode,flags=args
  full=pending[0] or (absolute(name) if isinstance(name,(str,bytes)) else None)
  text=str(full).lower()
  assert '/models/' not in text and '/huggingface/' not in text
  assert not text.endswith(('.safetensors','.bin','.pt','.env','.env.runtime'))
  writes=(isinstance(mode,str) and any(c in mode for c in 'wax+')) or (isinstance(flags,int) and flags&(os.O_CREAT|os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_TRUNC))
  if writes:assert full is not None and full.is_relative_to(owned)
 elif event=='sqlite3.connect':
  value=str(args[0]);p=Path(unquote(urlsplit(value).path)) if value.startswith('file:') else Path(value)
  assert p.is_relative_to(owned)
 elif event=='socket.__new__':assert args[1] not in (socket.AF_INET,socket.AF_INET6)
 elif event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('child network prohibited')
 elif event=='import':assert args[0].split('.')[0] not in ('torch','transformers','huggingface_hub','sentence_transformers','safetensors')
sys.addaudithook(guarded)
sys.path.insert(0,sys.argv[1]);from services import runtime_paths as runtime
from services.history_db import HistoryDB
db=Path(sys.argv[2]);runtime.STATE_ROOT=db.parent
runtime.CACHE_ROOT=db.parent.parent/'cache';runtime.LOG_ROOT=db.parent/'logs'
os.environ['STRUCTURAL_ENV']='prod'
if sys.argv[3]=='create-race':
 import time
 from services.sqlite_utils import prepare_private_history
 parent_open=os.open;attempted=[];lost=[]
 def raced(path,flags,*args,**kwargs):
  if path=='history.db' and flags & os.O_EXCL:
   attempted.append(True)
   (db.parent.parent/(sys.argv[4]+'.ready')).write_text('ready')
   deadline=time.monotonic()+5
   while not all((db.parent.parent/(name+'.ready')).exists() for name in ('one','two')):
    assert time.monotonic()<deadline,'creator peer never became ready'
    time.sleep(.005)
   try:return parent_open(path,flags,*args,**kwargs)
   except FileExistsError:lost.append(True);raise
  return parent_open(path,flags,*args,**kwargs)
 os.open=raced
 prepare_private_history(db)
 assert attempted==[True] and not fdpaths
 print('CREATE_RACE:'+json.dumps({'attempted':True,'eexist':bool(lost)}))
 sys.exit(0)
store=HistoryDB(db)
if sys.argv[3]=='write':store.record('d','child-write','search',None)
rows=sorted(row['query'] for row in store.list_recent('d',limit=10))
assert not fdpaths
print('WAL_ROWS:'+json.dumps(rows))
'''


def _wal_peer(private, operation):
    import json
    import subprocess
    import sys
    backend = str(Path(__file__).resolve().parents[1])
    owned = str(private.parent.parent.resolve())
    environment = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'HOME': owned,
                   'TMPDIR': owned, 'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'AUTH_ENABLED': 'false'}
    result = subprocess.run([sys.executable, '-B', '-c', _WAL_CHILD, backend, str(private), operation],
                            env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.startswith('WAL_ROWS:')]
    assert len(lines) == 1
    return json.loads(lines[0].split(':', 1)[1])


@pytest.mark.parametrize('mode', ['raw', 'formal'])
def test_legal_wal_peer_close_preserves_both_committed_rows(private, native, mode):
    store = HistoryDB(private)
    def connect():
        if mode == 'formal':return store._connect()
        conn = sqlite3.connect(private.as_uri() + '?mode=rw', uri=True, factory=sqlite_utils.ClosingConnection)
        conn.execute('PRAGMA journal_mode=WAL')
        return conn
    reader = connect()
    try:
        reader.execute('BEGIN');reader.execute('SELECT count(*) FROM history').fetchall()
        other = connect()
        try:other.execute('SELECT count(*) FROM history').fetchall()
        finally:other.close()
        assert _wal_peer(private, 'read') == []
        # An ordinary reader must not remove files still used by this reader.
        assert all(private.with_name(private.name + suffix).exists() for suffix in ('-wal', '-shm'))
        reader.rollback()
        reader.execute("INSERT INTO history(device_id,query,kind) VALUES('d','concurrent','search')")
        reader.commit()
        assert _wal_peer(private, 'read') == ['concurrent']
        assert _wal_peer(private, 'write') == ['child-write', 'concurrent']
    finally:
        reader.close()
    assert _wal_peer(private, 'read') == ['child-write', 'concurrent']


def test_existing_database_never_opens_or_duplicates_ordinary_database_fd(private, native, monkeypatch):
    HistoryDB(private)
    original_open = os.open
    attempted = []
    def no_database_open(path, *args, **kwargs):
        if os.fsdecode(path) == 'history.db' or Path(path) == private:
            attempted.append('open')
            raise AssertionError('existing SQLite file must not have an application FD')
        return original_open(path, *args, **kwargs)
    def no_dup(*args, **kwargs):
        attempted.append('dup')
        raise AssertionError('database descriptors must remain SQLite-owned')
    monkeypatch.setattr(os, 'open', no_database_open)
    monkeypatch.setattr(os, 'dup', no_dup)
    for constructor in STORES:
        store = constructor(private)
        with store._connect() as conn:
            assert conn.execute('SELECT 1').fetchone()[0] == 1
    assert attempted == []


@pytest.mark.parametrize('namespace', ['services', 'web.backend.services'])
def test_new_inode_creation_fd_is_closed_before_competing_native_open(private, monkeypatch, namespace):
    import importlib
    import threading
    from concurrent.futures import ThreadPoolExecutor
    native_opened, creation_paused, release_creation, lock_attempted = [threading.Event() for _ in range(4)]
    original_open, original_close, original_connect = os.open, os.close, sqlite3.connect
    actual_lock = paths.HISTORY_OPEN_LOCK
    other_paths = importlib.import_module(namespace + '.runtime_paths')
    other_utils = importlib.import_module(namespace + '.sqlite_utils')
    assert other_paths.HISTORY_OPEN_LOCK is actual_lock
    for attr in ('STATE_ROOT', 'CACHE_ROOT', 'LOG_ROOT'):
        monkeypatch.setattr(other_paths, attr, getattr(paths, attr))
    creation_fd, opener_thread, order = [], [], []

    class ObservedLock:
        def __enter__(self):
            if opener_thread and threading.get_ident() == opener_thread[0]:lock_attempted.set()
            actual_lock.acquire()
            return self
        def __exit__(self, *args):actual_lock.release()

    def opened(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if path == 'history.db' and flags & os.O_EXCL:creation_fd.append(fd)
        return fd
    def closed(fd):
        if creation_fd and fd == creation_fd[0] and not creation_paused.is_set():
            creation_paused.set()
            released = release_creation.wait(5)
            order.append('creation-fd-close')
            result = original_close(fd)
            assert released, 'test creator was never released'
            return result
        return original_close(fd)
    def native_open(*args, **kwargs):
        assert actual_lock._is_owned()  # Actual native call remains inside the same RLock.
        native_opened.set();order.append('native-open')
        return original_connect(*args, **kwargs)
    def consume():
        opener_thread.append(threading.get_ident())
        with other_utils.connect_private_history(private) as conn:
            witness = conn._history_file
            assert conn.execute('SELECT 1').fetchone()[0] == 1
        # Check closure in the creating thread, not a check_same_thread error.
        assert_closed(conn, witness)

    observer = ObservedLock()
    monkeypatch.setattr(paths, 'HISTORY_OPEN_LOCK', observer)
    monkeypatch.setattr(other_paths, 'HISTORY_OPEN_LOCK', observer)
    monkeypatch.setattr(os, 'open', opened)
    monkeypatch.setattr(os, 'close', closed)
    monkeypatch.setattr(sqlite3, 'connect', native_open)
    with ThreadPoolExecutor(max_workers=2) as executor:
        creator = executor.submit(sqlite_utils.prepare_private_history, private)
        consumer = None
        try:
            assert creation_paused.wait(5)
            consumer = executor.submit(consume)
            assert lock_attempted.wait(5)
            assert not native_opened.wait(0.1)
        finally:
            release_creation.set()
        creator.result(timeout=5)
        if consumer is not None:consumer.result(timeout=5)
    assert creation_fd and order == ['creation-fd-close', 'native-open']


def test_failed_new_inode_validation_closes_creation_fd_before_unlock(private, monkeypatch):
    original = os.open
    created = []
    def unsafe_new_file(path, flags, *args, **kwargs):
        fd = original(path, flags, *args, **kwargs)
        if path == 'history.db' and flags & os.O_EXCL:
            created.append(fd);private.chmod(0o644)
        return fd
    monkeypatch.setattr(os, 'open', unsafe_new_file)
    with pytest.raises(paths.RuntimePathError):sqlite_utils.prepare_private_history(private)
    assert len(created) == 1
    with pytest.raises(OSError):os.fstat(created[0])
    # A second thread must be able to acquire the lock after the failure.
    import threading
    acquired = []
    def checked():
        with paths.HISTORY_OPEN_LOCK:acquired.append(True)
    thread = threading.Thread(target=checked)
    thread.start();thread.join(timeout=5)
    assert not thread.is_alive() and acquired == [True]


def test_two_real_processes_exclusive_create_one_winner_no_existing_file_open(private, native):
    import json
    import subprocess
    import sys
    backend = str(Path(__file__).resolve().parents[1])
    owned = str(private.parent.parent.resolve())
    env = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'HOME': owned,
           'TMPDIR': owned, 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'AUTH_ENABLED': 'false'}
    children = []
    outcomes = []
    try:
        for name in ('one', 'two'):
            children.append(subprocess.Popen([sys.executable, '-B', '-c', _WAL_CHILD,
                backend, str(private), 'create-race', name], env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        for child in children:
            out, err = child.communicate(timeout=10)
            assert child.returncode == 0, err
            rows = [line for line in out.splitlines() if line.startswith('CREATE_RACE:')]
            assert len(rows) == 1
            outcomes.append(json.loads(rows[0].split(':', 1)[1]))
    finally:
        for child in children:
            if child.poll() is None:child.terminate();child.wait(timeout=5)
    assert all(row['attempted'] for row in outcomes)
    assert sum(row['eexist'] for row in outcomes) == 1
    assert private.stat().st_mode & 0o777 == 0o600
    store = HistoryDB(private)
    store.record('d', 'after-real-creation-race', 'search', None)
    assert store.list_recent('d', limit=10)[0]['query'] == 'after-real-creation-race'
