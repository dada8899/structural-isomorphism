"""Real consumer getters and real native SQLite; the public app stays closed."""
from pathlib import Path
import asyncio
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
import importlib

import pytest
from api import history, report, report_account, connections
from api.privacy import export as privacy_export, delete as privacy_delete
from services import runtime_paths as runtime
from services.history_db import HistoryDB
from services.report_store import ReportStore
from services.connections_store import ConnectionsStore
from services.connections_p3_store import ConnectionsP3Store


def bootstrap(db):
    # Controlled pre-request preparation through the real B1 constructors.
    # This never injects an API singleton or substitutes a Store implementation.
    for factory in (HistoryDB, ReportStore, ConnectionsStore, ConnectionsP3Store):factory(db)

GETTERS = [history.get_db, report._get_store, report_account._get_store,
           connections._get_store, connections._get_p3_store]
SELECTORS = [privacy_export._history_db, privacy_delete._history_db]


def roots(monkeypatch, root):
    state, cache, logs = root / 'state', root / 'cache', root / 'state/logs'
    for path in (state, cache, logs):path.mkdir(mode=0o700, parents=True, exist_ok=True);path.chmod(0o700)
    monkeypatch.setattr(runtime, 'STATE_ROOT', state)
    monkeypatch.setattr(runtime, 'CACHE_ROOT', cache)
    monkeypatch.setattr(runtime, 'LOG_ROOT', logs)
    return state / 'history.db'


@pytest.fixture
def private(tmp_path, monkeypatch):
    db = roots(monkeypatch, tmp_path.resolve())
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    monkeypatch.delenv('STRUCTURAL_HISTORY_DB', raising=False)
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET', 'synthetic-share-key-never-live')
    monkeypatch.setenv('STRUCTURAL_SSO_SECRET', 'A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3')
    monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR', str(db.parent))
    bootstrap(db)
    # Clear lifecycle state only. Never preseed Store objects or mock IO.
    for module, slot in ((history,'_db'),(report,'_store'),(report_account,'_store'),
                         (connections,'_store'),(connections,'_p3_store')):
        monkeypatch.setattr(module, slot, None)
    return db


@pytest.fixture
def native(monkeypatch):
    actual = sqlite3.connect
    class NativeCalls(list):
        pass
    seen = NativeCalls()
    seen.calls = []
    def observed(*args, **kwargs):
        connection = actual(*args, **kwargs)
        seen.calls.append((args, kwargs))
        seen.append(connection)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', observed)
    yield seen
    for connection in seen:
        with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')


def test_all_actual_getters_share_approved_inode_and_read_write(private, native):
    stores = [getter() for getter in GETTERS]
    identity = (private.stat().st_dev, private.stat().st_ino)
    assert all(store.db_path == private for store in stores)
    assert all((path().stat().st_dev, path().stat().st_ino) == identity for path in SELECTORS)
    hid = stores[0].record('device', 'synthetic history', 'search', None)
    assert stores[0].list_recent('device', limit=10)[0]['id'] == hid
    row = stores[1].create(query='synthetic report', b_id='fixture', lang='en',
                           payload={'synthetic':True}, model='fixture', creator_anon_id='device')
    assert stores[2].get_by_id(row['id'])['query'] == 'synthetic report'
    fid = stores[3].create_fingerprint(user_email='fixture@example.invalid', problem_summary='synthetic')
    assert privacy_export._export_fingerprints('fixture@example.invalid')[0]['id'] == fid
    mid = stores[4].create_message(from_email='fixture@example.invalid', to_email='peer@example.invalid', body='synthetic')
    assert privacy_export._export_p3('fixture@example.invalid')['connections_messages'][0]['id'] == mid
    assert privacy_delete._delete_fingerprints('fixture@example.invalid') == 1
    assert privacy_delete._delete_p3('fixture@example.invalid')['connections_messages'] == 1
    assert privacy_export._export_fingerprints('fixture@example.invalid') == []
    assert all(not rows for rows in privacy_export._export_p3('fixture@example.invalid').values())


@pytest.mark.parametrize('getter', GETTERS)
def test_cache_returns_complete_singleton_and_concurrent_init(private, native, getter):
    # Thread-created handles are closed and verified in their own thread.
    first = getter()
    assert getter() is first
    assert first._history_consumer_binding == (True, str(private))
    # No Store is injected into the cache. A separate target tests cold init.


@pytest.mark.parametrize('which', range(len(GETTERS)))
def test_cold_concurrent_actual_getter_initializes_one_store(private, monkeypatch, which):
    import threading
    getter = GETTERS[which]
    actual = sqlite3.connect
    opened = {}
    def connected(*args, **kwargs):
        connection = actual(*args, **kwargs)
        opened.setdefault(threading.get_ident(), []).append(connection)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', connected)
    def worker(_):
        value = getter()
        # Verify closure in the creator thread; cross-thread ProgrammingError
        # alone would not prove the native connection was closed.
        for connection in opened.get(threading.get_ident(), []):
            with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
        return value
    with ThreadPoolExecutor(max_workers=4) as executor:
        values = list(executor.map(worker, range(4)))
    assert len({id(value) for value in values}) == 1
    with values[0]._connect() as conn:assert conn.execute('SELECT 1').fetchone()[0] == 1


@pytest.mark.parametrize('getter', GETTERS)
def test_cache_is_rebound_to_new_approved_path_without_moving_old_data(private, native, monkeypatch, getter):
    first = getter()
    old_identity = (private.stat().st_dev, private.stat().st_ino)
    second_path = roots(monkeypatch, private.parent.parent / 'other-approved')
    bootstrap(second_path)
    second = getter()
    assert second is not first and second.db_path == second_path
    assert (private.stat().st_dev,private.stat().st_ino) == old_identity
    assert getter() is second


@pytest.mark.parametrize('override', ['', ' ', 'history.db', 'file:/unapproved/history.db', '/unapproved/history.db'])
@pytest.mark.parametrize('entry', GETTERS + SELECTORS)
def test_formal_bad_override_rejects_even_with_live_cache(private, native, monkeypatch, override, entry):
    history.get_db()
    if entry in GETTERS:entry()
    before = len(native)
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB', override)
    with pytest.raises(runtime.RuntimePathError):entry()
    assert len(native) == before


@pytest.mark.parametrize('entry', GETTERS + SELECTORS)
def test_explicit_approved_override_stays_on_same_file(private, native, monkeypatch, entry):
    history.get_db()
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB', str(private))
    value = entry()
    assert (value.db_path if hasattr(value,'db_path') else value) == private


@pytest.mark.parametrize('getter', GETTERS)
@pytest.mark.parametrize('fault', ['missing-db','file-mode','wal-mode','parent-mode'])
def test_cache_hit_rechecks_actual_file_and_never_recreates_lost_database(private, native, getter, fault):
    getter()
    if fault == 'missing-db':private.unlink()
    elif fault == 'file-mode':private.chmod(0o644)
    elif fault == 'parent-mode':private.parent.chmod(0o755)
    else:
        side = private.with_name(private.name+'-wal');side.write_bytes(b'synthetic');side.chmod(0o644)
    before = len(native)
    with pytest.raises(runtime.RuntimePathError):getter()
    assert len(native) == before
    if fault == 'missing-db':assert not private.exists()


@pytest.mark.parametrize('operation', [privacy_export._export_fingerprints, privacy_export._export_p3,
                                       privacy_delete._delete_fingerprints, privacy_delete._delete_p3])
def test_privacy_missing_or_orphan_database_is_error_never_empty_success(private, native, operation):
    private.unlink()
    with pytest.raises(runtime.RuntimePathError):operation('fixture@example.invalid')
    assert not private.exists() and native == []
    side=private.with_name(private.name+'-wal');side.write_bytes(b'orphan');side.chmod(0o600)
    with pytest.raises(runtime.RuntimePathError):operation('fixture@example.invalid')
    assert not private.exists() and native == []


@pytest.mark.parametrize('which', range(len(GETTERS)))
def test_real_failed_sqlite_schema_init_never_publishes_store_and_can_retry(private, native, monkeypatch, which):
    real = sqlite3.connect
    denied = []
    def reject_create(*args, **kwargs):
        connection = real(*args, **kwargs)
        def authorizer(action, name, *_):
            if action == sqlite3.SQLITE_CREATE_TABLE:
                denied.append(name);return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        if args[0] == private.as_uri() + '?mode=rw':
            connection.set_authorizer(authorizer)
        return connection
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',reject_create)
        with pytest.raises(sqlite3.DatabaseError):GETTERS[which]()
    assert denied
    slots=[(history,'_db'),(report,'_store'),(report_account,'_store'),(connections,'_store'),(connections,'_p3_store')]
    assert getattr(*slots[which]) is None
    actual = GETTERS[which]()
    assert actual is GETTERS[which]() and actual.db_path == private


def test_history_profile_and_dev_override_switches_do_not_reuse_wrong_store(private, native, monkeypatch):
    formal = history.get_db()
    dev_path=private.parent.parent/'legacy/history.db'
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('STRUCTURAL_HISTORY_DB',str(dev_path))
    legacy = history.get_db()
    assert legacy is not formal and legacy.db_path == dev_path and not legacy._formal_history
    monkeypatch.setenv('STRUCTURAL_ENV','prod');monkeypatch.delenv('STRUCTURAL_HISTORY_DB')
    again = history.get_db()
    assert again is not legacy and again.db_path == private and again._formal_history


def test_report_account_existing_snapshot_delete_restore_use_same_real_history(private, native):
    email='fixture@example.invalid';owner=report_account._subject_id(email)
    store=report._get_store()
    row=store.create(query='synthetic',b_id='fixture',lang='en',payload={},model='fixture',creator_anon_id='device')
    store.claim_by_anon('device',owner)
    snapshot=report_account.snapshot_account_reports(email)
    assert snapshot['reports'][0]['id']==row['id']
    assert report_account.export_account_reports(email)['reports'][0]['id']==row['id']
    removed=report_account.delete_account_reports(email)
    assert report_account._get_store().export_by_owner(owner)['reports']==[]
    report_account.restore_account_reports(email,snapshot,removed)
    assert report._get_store().get_by_id(row['id'])['owner_user_id']==owner
    assert report_account._get_store().db_path==store.db_path==private


@pytest.mark.parametrize('operation', [report_account.export_account_reports,report_account.snapshot_account_reports,
                                      report_account.delete_account_reports])
def test_bad_history_path_rejects_before_real_sso_ledger_creation(private, native, monkeypatch, operation):
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB','/unapproved/history.db')
    with pytest.raises(runtime.RuntimePathError):operation('fixture@example.invalid')
    assert not (private.parent/'sso_replay.sqlite3').exists()
    assert native == []


def test_bad_history_path_never_revokes_preexisting_sso_subject(private, native, monkeypatch):
    from services.sso_store import SsoReplayStore
    email='fixture@example.invalid';owner=report_account._subject_id(email)
    ledger=SsoReplayStore(private.parent/'sso_replay.sqlite3')
    ledger.issue('synthetic-issued-code',owner,'free',int(time.time())+300,email=email)
    before=ledger.export_issued_for_subject(owner)
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB','/unapproved/history.db')
    with pytest.raises(runtime.RuntimePathError):report_account.delete_account_reports(email)
    assert ledger.subject_revoked_at(owner) is None
    assert ledger.export_issued_for_subject(owner)==before


def test_real_report_delete_failure_rolls_back_and_compensates_existing_snapshot(private, native, monkeypatch):
    email='fixture@example.invalid';owner=report_account._subject_id(email)
    store=report_account._get_store()
    row=store.create(query='synthetic',b_id='fixture',lang='en',payload={},model='fixture',creator_anon_id='device')
    store.claim_by_anon('device',owner)
    actual=sqlite3.connect;blocked=[]
    def first_delete_failure(*args,**kwargs):
        connection=actual(*args,**kwargs)
        if args[0] == private.as_uri()+'?mode=rw':
            def authorizer(action,name,*_):
                if action==sqlite3.SQLITE_DELETE and name=='reports' and not blocked:
                    blocked.append(True);return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            connection.set_authorizer(authorizer)
        return connection
    monkeypatch.setattr(sqlite3,'connect',first_delete_failure)
    with pytest.raises(sqlite3.DatabaseError):report_account.delete_account_reports(email)
    assert blocked==[True]
    assert store.get_by_id(row['id'])['owner_user_id']==owner


def test_dev_empty_privacy_semantics_and_other_asset_directories_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv('STRUCTURAL_ENV','dev')
    for module in (privacy_export,privacy_delete):monkeypatch.setattr(module,'_data_dir',lambda:tmp_path)
    assert privacy_export._export_fingerprints('fixture@example.invalid')==[]
    assert privacy_delete._delete_fingerprints('fixture@example.invalid')==0
    assert privacy_export._newsletter_file()==tmp_path/'newsletter-subscribers.jsonl'
    assert privacy_delete._checkouts_file()==tmp_path/'mock_checkouts.jsonl'


def test_both_real_api_namespaces_use_same_approved_database_and_init_lock(private, native, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    package_runtime=importlib.import_module('web.backend.services.runtime_paths')
    for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):
        monkeypatch.setattr(package_runtime,name,getattr(runtime,name))
    other_history=importlib.import_module('web.backend.api.history')
    other_report=importlib.import_module('web.backend.api.report')
    other_account=importlib.import_module('web.backend.api.report_account')
    other_connections=importlib.import_module('web.backend.api.connections')
    other_export=importlib.import_module('web.backend.api.privacy.export')
    other_delete=importlib.import_module('web.backend.api.privacy.delete')
    for module,slot in ((other_history,'_db'),(other_report,'_store'),(other_account,'_store'),
                        (other_connections,'_store'),(other_connections,'_p3_store')):
        monkeypatch.setattr(module,slot,None)
    assert history._HISTORY_STORE_LOCK is other_history._HISTORY_STORE_LOCK
    stores=[getter() for getter in GETTERS]
    other=[other_history.get_db(),other_report._get_store(),other_account._get_store(),
           other_connections._get_store(),other_connections._get_p3_store()]
    assert all(store.db_path==private for store in stores+other)
    assert other_export._history_db()==other_delete._history_db()==private
    stores[0].record('namespace-device','synthetic namespace row','search',None)
    assert other[0].list_recent('namespace-device',limit=10)[0]['query']=='synthetic namespace row'


@pytest.mark.parametrize('getter', GETTERS)
def test_formal_unmarked_cache_not_trusted_and_corrupt_binding_rejected(private, native, getter):
    first=getter()
    del first._history_consumer_binding
    rebuilt=getter()
    assert rebuilt is not first and rebuilt._formal_history
    rebuilt.db_path=private.with_name('shadow.db')
    before=len(native)
    with pytest.raises(runtime.RuntimePathError):getter()
    assert len(native)==before and not private.with_name('shadow.db').exists()


@pytest.mark.parametrize('entry', GETTERS+SELECTORS)
def test_malformed_formal_profile_does_not_fall_into_development(private, native, monkeypatch, entry):
    history.get_db();before=len(native)
    monkeypatch.setenv('STRUCTURAL_ENV','prod ')
    with pytest.raises(runtime.RuntimePathError):entry()
    assert len(native)==before


@pytest.mark.parametrize('which',range(len(GETTERS)))
def test_configuration_changed_during_actual_initialization_is_not_cached(private, native, monkeypatch, which):
    actual=sqlite3.connect;changed=[]
    def mutate(*args,**kwargs):
        connection=actual(*args,**kwargs)
        def authorizer(action,name,*_):
            if action==sqlite3.SQLITE_PRAGMA and name=='journal_mode' and args[0]==private.as_uri()+'?mode=rw' and not changed:
                monkeypatch.setenv('STRUCTURAL_HISTORY_DB','/unapproved/changed.db');changed.append(True)
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorizer)
        return connection
    with monkeypatch.context() as scoped:
        scoped.setattr(sqlite3,'connect',mutate)
        with pytest.raises(runtime.RuntimePathError):GETTERS[which]()
    slots=[(history,'_db'),(report,'_store'),(report_account,'_store'),(connections,'_store'),(connections,'_p3_store')]
    assert changed==[True] and getattr(*slots[which]) is None
    monkeypatch.delenv('STRUCTURAL_HISTORY_DB')
    assert GETTERS[which]().db_path==private


@pytest.mark.parametrize('entry',GETTERS[1:]+SELECTORS)
@pytest.mark.parametrize('loss',['missing','truncation'])
def test_cold_consumer_cannot_rebuild_or_accept_database_lost_after_other_consumer(private,native,entry,loss):
    store=history.get_db()
    store.record('device','must-not-vanish','search',None)
    if loss=='missing':private.unlink()
    else:private.write_bytes(b'')
    before=len(native)
    with pytest.raises(runtime.RuntimePathError):entry()
    if loss=='missing':
        assert len(native)==before and not private.exists()
    else:
        assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_kwargs in native.calls[before:])


@pytest.mark.parametrize('entry',GETTERS+SELECTORS)
def test_cold_formal_missing_database_refused_before_any_native_connection(private,native,entry):
    private.unlink()
    before=len(native)
    with pytest.raises(runtime.RuntimePathError):entry()
    assert not private.exists() and len(native)==before


@pytest.mark.parametrize('fault',['empty','missing-table','missing-column','wrong-index','unknown-aux','corrupt'])
@pytest.mark.parametrize('entry',[history.get_db,report._get_store,privacy_export._history_db,privacy_delete._history_db])
def test_readonly_schema_gate_rejects_drift_without_constructor_or_byte_changes(private,native,fault,entry):
    from services.sqlite_utils import ClosingConnection
    if fault=='empty':private.write_bytes(b'')
    elif fault=='corrupt':private.write_bytes(b'synthetic not a sqlite database')
    else:
        with sqlite3.connect(private.as_uri()+'?mode=rw',uri=True,factory=ClosingConnection) as conn:
            if fault=='missing-table':conn.execute('DROP TABLE match_requests')
            elif fault=='missing-column':conn.execute('ALTER TABLE reports DROP COLUMN model')
            elif fault=='unknown-aux':conn.execute('CREATE TABLE unexpected_aux(value TEXT)')
            else:
                name=conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name LIMIT 1").fetchone()[0]
                quoted='"'+name.replace('"','""')+'"'
                conn.execute('DROP INDEX '+quoted)
                conn.execute('CREATE INDEX '+quoted+' ON history(kind)')
    # All connections used to prepare the synthetic fault are closed before
    # ordinary byte inspection, so hashing cannot disturb POSIX SQLite locks.
    before=private.read_bytes();start=len(native)
    with pytest.raises(runtime.RuntimePathError):entry()
    assert private.read_bytes()==before
    calls=native.calls[start:]
    assert all(args[0]==':memory:' or args[0]==private.as_uri()+'?mode=ro' for args,_ in calls)
    assert history._db is None and report._store is None


def test_fixed_contract_covers_nine_final_store_tables_columns_and_indexes(private,native):
    from services import report_store,connections_store,connections_p3_store
    expected=history._history_schema_contract()
    names=set(expected[1])
    assert names-{'sqlite_sequence'}=={'history','reports','report_feedback','report_followup',
        'structural_fingerprints','match_requests','referrals','connections_messages','connections_prefs'}
    columns={name:{row[1] for row in data[0]} for name,data in expected[1].items()}
    assert set(name for name,_ in report_store.ReportStore._REPORTS_COLUMNS)<=columns['reports']
    assert set(name for name,_ in connections_store._FP_COLUMNS)<=columns['structural_fingerprints']
    for name,source in [('match_requests',connections_p3_store._MR_COLUMNS),('referrals',connections_p3_store._RF_COLUMNS),
                        ('connections_messages',connections_p3_store._CM_COLUMNS),('connections_prefs',connections_p3_store._CP_COLUMNS)]:
        assert set(column for column,_ in source)<=columns[name]
    assert {'experiment_json','outcome_detail_json','publish_to_insights','consent_version',
            'consented_at','withdrawn_at'}<=columns['report_followup']
    from services.sqlite_utils import ClosingConnection
    with sqlite3.connect(private.as_uri()+'?mode=ro',uri=True,factory=ClosingConnection) as conn:
        assert history._schema_metadata(conn)==expected
    assert expected[2]  # Includes explicit and constraint-generated indexes.


def test_new_process_cold_missing_consumers_do_not_create_database(private):
    import subprocess,sys
    private.unlink()
    script=r'''
import os,sys,sqlite3,socket
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
def guarded(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','huggingface_hub','sentence_transformers','safetensors'):raise AssertionError('real model import forbidden')
sys.addaudithook(guarded)
from services import runtime_paths as runtime
from api import history,report,report_account,connections
from api.privacy import export,delete
root=Path(sys.argv[3]);runtime.STATE_ROOT=root;runtime.CACHE_ROOT=root.parent/'cache';runtime.LOG_ROOT=root/'logs'
os.environ['STRUCTURAL_ENV']='prod';os.environ.pop('STRUCTURAL_HISTORY_DB',None)
attempted=[]
def no_sqlite(*a,**k):attempted.append(True);raise AssertionError('missing consumer touched SQLite')
sqlite3.connect=no_sqlite
for entry in (history.get_db,report._get_store,report_account._get_store,connections._get_store,connections._get_p3_store,export._history_db,delete._history_db):
 try:entry()
 except runtime.RuntimePathError:pass
 else:raise AssertionError('missing database accepted')
assert not attempted and not (root/'history.db').exists()
print('COLD_MISSING_OK')
'''
    root=Path(__file__).resolve().parents[3]
    env={'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':os.environ.get('TMPDIR','/private/tmp'),
         'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
    result=subprocess.run([sys.executable,'-B','-c',script,str(root/'web/backend'),str(root),str(private.parent)],
                          env=env,text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'COLD_MISSING_OK' in result.stdout and not private.exists()


@pytest.mark.parametrize('point',['after-open','during-metadata'])
def test_readonly_schema_connection_identity_permissions_and_finally_close_are_real(private,native,monkeypatch,point):
    real=sqlite3.connect;changed=[]
    def altered(*args,**kwargs):
        conn=real(*args,**kwargs)
        if args[0]==private.as_uri()+'?mode=ro':
            assert kwargs['uri'] is True
            if point=='after-open':
                private.parent.chmod(0o755);changed.append(True)
            else:
                def authorizer(action,name,*_):
                    if action==sqlite3.SQLITE_PRAGMA and name=='table_xinfo' and not changed:
                        private.chmod(0o644);changed.append(True)
                    return sqlite3.SQLITE_OK
                conn.set_authorizer(authorizer)
        return conn
    monkeypatch.setattr(sqlite3,'connect',altered)
    with pytest.raises(runtime.RuntimePathError):report._get_store()
    assert changed==[True] and report._store is None
    assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_ in native.calls)


@pytest.mark.parametrize('getter',GETTERS)
def test_cached_schema_drift_is_not_repaired_or_hidden(private,native,getter):
    from services.sqlite_utils import ClosingConnection
    getter()
    with sqlite3.connect(private.as_uri()+'?mode=rw',uri=True,factory=ClosingConnection) as conn:
        conn.execute('DROP TABLE match_requests')
    before=private.read_bytes();start=len(native)
    with pytest.raises(runtime.RuntimePathError):getter()
    assert private.read_bytes()==before
    assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_ in native.calls[start:])


@pytest.mark.parametrize('damage',['missing-table','missing-column','wrong-index','unknown-aux'])
def test_new_process_halfstate_consumers_use_readonly_gate_not_store_self_repair(private,damage):
    import subprocess,sys
    from services.sqlite_utils import ClosingConnection
    with sqlite3.connect(private.as_uri()+'?mode=rw',uri=True,factory=ClosingConnection) as conn:
        if damage=='missing-table':conn.execute('DROP TABLE connections_messages')
        elif damage=='missing-column':conn.execute('ALTER TABLE reports DROP COLUMN model')
        elif damage=='unknown-aux':conn.execute('CREATE TABLE unexpected_aux(value TEXT)')
        else:
            name=conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name LIMIT 1").fetchone()[0]
            quoted='"'+name.replace('"','""')+'"'
            conn.execute('DROP INDEX '+quoted);conn.execute('CREATE INDEX '+quoted+' ON history(kind)')
    before=private.read_bytes()
    script=r'''
import os,sys,sqlite3,socket
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
def guarded(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','huggingface_hub','sentence_transformers','safetensors'):raise AssertionError('model forbidden')
sys.addaudithook(guarded)
from services import runtime_paths as runtime
from api import history,report,report_account,connections
from api.privacy import export,delete
root=Path(sys.argv[3]);db=root/'history.db'
runtime.STATE_ROOT=root;runtime.CACHE_ROOT=root.parent/'cache';runtime.LOG_ROOT=root/'logs'
os.environ['STRUCTURAL_ENV']='prod';os.environ.pop('STRUCTURAL_HISTORY_DB',None)
actual=sqlite3.connect;opened=[]
def readonly_only(path,*args,**kwargs):
 assert path==':memory:' or path==db.as_uri()+'?mode=ro','consumer attempted mutable native open'
 conn=actual(path,*args,**kwargs);opened.append(conn);return conn
sqlite3.connect=readonly_only
for entry in (history.get_db,report._get_store,report_account._get_store,connections._get_store,connections._get_p3_store,export._history_db,delete._history_db):
 try:entry()
 except runtime.RuntimePathError:pass
 else:raise AssertionError('incomplete schema accepted')
for conn in opened:
 try:conn.execute('SELECT 1')
 except sqlite3.ProgrammingError:pass
 else:raise AssertionError('native connection leaked')
print('COLD_SCHEMA_REJECT_OK')
'''
    root=Path(__file__).resolve().parents[3]
    env={'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':os.environ.get('TMPDIR','/private/tmp'),
         'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}
    result=subprocess.run([sys.executable,'-B','-c',script,str(root/'web/backend'),str(root),str(private.parent)],
                          env=env,text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'COLD_SCHEMA_REJECT_OK' in result.stdout and private.read_bytes()==before
