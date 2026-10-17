"""Real private replay storage and actual consumer wiring; no app release."""
from pathlib import Path
import os,sqlite3,time,json,asyncio,importlib
import pytest
from services import runtime_paths as paths,sqlite_utils,sso_store
from services.sso_store import SsoReplayStore
from api import sso,auth,report,report_account

SECRET='A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3'


@pytest.fixture
def private(tmp_path,monkeypatch):
    state,cache,logs=tmp_path.resolve()/'state',tmp_path.resolve()/'cache',tmp_path.resolve()/'state/logs'
    for directory in (state,cache,logs):directory.mkdir(mode=0o700)
    for name,value in (('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',logs)):monkeypatch.setattr(paths,name,value)
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('AUTH_DATA_DIR',str(state))
    monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',str(state));monkeypatch.setenv('STRUCTURAL_SSO_SECRET',SECRET)
    monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY','0123456789abcdef'*4)
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET','synthetic-share-secret')
    db=state/'sso_replay.sqlite3';SsoReplayStore(db);db.chmod(0o600)
    monkeypatch.setattr(sso,'_REPLAY_STORES',{});monkeypatch.setenv('STRUCTURAL_ENV','prod')
    return db


@pytest.fixture
def native(monkeypatch):
    real=sqlite3.connect
    class Native(list):pass
    seen=Native();seen.calls=[]
    def observed(*args,**kwargs):
        conn=real(*args,**kwargs);seen.append(conn);seen.calls.append((args,kwargs));return conn
    monkeypatch.setattr(sqlite3,'connect',observed)
    yield seen
    for conn in seen:
        with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')


def raw(db):return sqlite3.connect(db.as_uri()+'?mode=rw',uri=True,factory=sqlite_utils.ClosingConnection)


def shared_assets(db,monkeypatch):
    from services.auth_store import AuthStore
    from research.store import ResearchStore
    from services.history_db import HistoryDB
    from services.report_store import ReportStore
    from services.connections_store import ConnectionsStore
    from services.connections_p3_store import ConnectionsP3Store
    with monkeypatch.context() as setup:
        setup.setenv('STRUCTURAL_ENV','dev')
        account=AuthStore(db.parent/'auth.sqlite3');ResearchStore(account)
        account.ensure_user_and_notification('fixture@example.invalid','free','synthetic')
        for factory in (HistoryDB,ReportStore,ConnectionsStore,ConnectionsP3Store):factory(db.parent/'history.db')
    for name in ('auth.sqlite3','history.db'):db.with_name(name).chmod(0o600)
    monkeypatch.setattr(auth,'_AUTH_STORES',{})
    monkeypatch.setattr(report,'_store',None);monkeypatch.setattr(report_account,'_store',None)
    return account


def test_formal_ctor_ro_schema_and_tuple_runtime_without_hooks(private,native):
    before=private.read_bytes();store=SsoReplayStore(private)
    assert private.read_bytes()==before
    assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_ in native.calls)
    with store._connect() as conn:
        assert conn.row_factory is None and conn.isolation_level is None and not conn.in_transaction
        assert type(conn.execute('SELECT 1').fetchone()) is tuple
        assert conn.execute('PRAGMA busy_timeout').fetchone()[0]==10000
        with pytest.raises(sqlite3.OperationalError):conn.execute('SELECT research_method_guard_version()')
    assert sso.get_replay_store() is sso.get_replay_store()


@pytest.mark.parametrize('config',[None,'',' ','relative','file:/bad','/bad'])
def test_formal_config_is_explicit_and_no_fallback(private,native,monkeypatch,config):
    if config is None:monkeypatch.delenv('STRUCTURAL_SSO_DATA_DIR')
    else:monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',config)
    with pytest.raises(paths.RuntimePathError):sso.get_replay_store()
    assert native==[] and sso._REPLAY_STORES=={}


@pytest.mark.parametrize('fault',['missing','parent-mode','file-mode','symlink','hardlink','sidecar'])
def test_unsafe_ledger_rejected_before_native_or_create(private,native,fault):
    if fault=='missing':private.unlink()
    elif fault=='parent-mode':private.parent.chmod(0o755)
    elif fault=='file-mode':private.chmod(0o644)
    elif fault=='symlink':private.rename(private.with_name('real.db'));private.symlink_to(private.with_name('real.db'))
    elif fault=='hardlink':os.link(private,private.with_name('alias.db'))
    else:
        side=private.with_name(private.name+'-wal');side.write_bytes(b'x');side.chmod(0o644)
    with pytest.raises((paths.RuntimePathError,OSError)):sso.get_replay_store()
    assert native==[]
    if fault=='missing':assert not private.exists()


@pytest.mark.parametrize('fault',['missing-table','missing-column','unknown-aux','wrong-index','corrupt','empty'])
def test_unsupported_schema_is_readonly_rejected_no_repair(private,native,fault):
    if fault in ('corrupt','empty'):private.write_bytes(b'invalid' if fault=='corrupt' else b'')
    else:
        with raw(private) as conn:
            if fault=='missing-table':conn.execute('DROP TABLE consumed_sso_codes')
            elif fault=='missing-column':conn.execute('ALTER TABLE issued_sso_codes DROP COLUMN email')
            elif fault=='unknown-aux':conn.execute('CREATE TABLE unknown_sso_aux(x TEXT)')
            else:conn.execute('CREATE INDEX unknown_sso_idx ON revoked_sso_subjects(revoked_at)')
    before=private.read_bytes();start=len(native)
    with pytest.raises(Exception):sso.get_replay_store()
    assert private.read_bytes()==before and not sso._REPLAY_STORES
    assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_ in native.calls[start:])


@pytest.mark.parametrize('missing',[('email',),('issued_ns',),('email','issued_ns')])
def test_actual_completed_legal_alter_forms(private,native,missing):
    with raw(private) as conn:
        conn.execute('DROP TABLE issued_sso_codes')
        ddl=sso_store._SSO_TABLE_DDL[1]
        if 'email' in missing:ddl=ddl.replace(', email TEXT','')
        if 'issued_ns' in missing:ddl=ddl.replace(', issued_ns INTEGER','')
        conn.execute(ddl)
        for name,sql in zip(('email','issued_ns'),sso_store._SSO_ALTER_DDL):
            if name in missing:conn.execute(sql)
    assert SsoReplayStore(private).storage_identity is not None


def test_real_replay_issue_consume_revoke_and_conditional_restore(private,native):
    store=sso.get_replay_store();subject=sso._subject_id('fixture@example.invalid')
    store.issue('synthetic-code',subject,'free',int(time.time())+300,email='fixture@example.invalid')
    assert store.email_for_subject(subject)=='fixture@example.invalid'
    snap=store.export_issued_for_subject(subject)
    assert store.consume_issued('synthetic-code')['subject_id']==subject
    assert store.consume_issued('synthetic-code') is None
    assert store.consume_once('generic-code',int(time.time())+100) is True
    assert store.consume_once('generic-code',int(time.time())+100) is False
    assert store.revoke_subject(subject,10)==10
    assert store.revoke_subject(subject,20)==20
    store.revoke_subject(subject,30);store.restore_subject_revocation(subject,10,20)
    assert store.subject_revoked_at(subject)==30
    store.delete_issued_for_subject(subject);store.restore_issued(snap)
    assert store.lookup_issued('synthetic-code')['subject_id']==subject


def test_cache_rechecks_missing_schema_identity_and_profile(private,native,monkeypatch):
    old=sso.get_replay_store();image=private.read_bytes()
    private.rename(private.with_name('old.db'));private.write_bytes(image);private.chmod(0o600)
    with pytest.raises(paths.RuntimePathError):
        with old._connect():pass
    new=sso.get_replay_store();assert new is not old
    monkeypatch.setenv('STRUCTURAL_ENV','dev')
    with new._connect() as conn:assert isinstance(conn,sqlite_utils.PrivateSsoConnection)
    monkeypatch.setenv('STRUCTURAL_ENV','prod');private.unlink();start=len(native)
    with pytest.raises(paths.RuntimePathError):sso.get_replay_store()
    assert len(native)==start and not private.exists()


def test_all_namespace_factories_same_canonical_file_mutex(private,native,monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    runtime=importlib.import_module('web.backend.services.runtime_paths')
    for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(runtime,name,getattr(paths,name))
    api=importlib.import_module('web.backend.api.sso');monkeypatch.setattr(api,'_REPLAY_STORES',{})
    assert api._REPLAY_LOCK is sso._REPLAY_LOCK
    assert api.get_replay_store().path==sso.get_replay_store().path==private
    assert api.get_replay_store().storage_identity==sso.get_replay_store().storage_identity


def test_bad_ledger_blocks_report_fallback_auth_scan(private,native,monkeypatch):
    shared_assets(private,monkeypatch);owner=sso._subject_id('fixture@example.invalid')
    private.unlink();start=len(native)
    with pytest.raises(paths.RuntimePathError):report._resource_owner_email({'owner_user_id':owner})
    assert len(native)==start  # No Auth preflight or auth_users scan fallback.


def test_valid_ledger_without_binding_keeps_real_auth_fallback(private,native,monkeypatch):
    shared_assets(private,monkeypatch);owner=sso._subject_id('fixture@example.invalid')
    assert report._resource_owner_email({'owner_user_id':owner})=='fixture@example.invalid'


def test_bad_ledger_blocks_history_restore_and_subject_revocation(private,native,monkeypatch):
    shared_assets(private,monkeypatch)
    store=report_account._get_store();owner=sso._subject_id('fixture@example.invalid')
    row=store.create(query='synthetic',b_id='fixture',lang='en',payload={},model='fixture',creator_anon_id='device')
    store.claim_by_anon('device',owner);snapshot=store.export_by_owner(owner);store.delete_by_owner(owner)
    private.unlink();start=len(native)
    with pytest.raises(paths.RuntimePathError):report_account.restore_account_reports('fixture@example.invalid',snapshot,{'beta_sessions_revoked_at':10})
    assert len(native)==start
    assert store.get_by_id(row['id']) is None


@pytest.mark.parametrize('target,table',[('history.db','reports'),('sso_replay.sqlite3','sso_subject_email_bindings'),('sso_replay.sqlite3','issued_sso_codes')])
def test_snapshot_failure_precedes_any_subject_revoke(private,native,monkeypatch,target,table):
    shared_assets(private,monkeypatch);owner=sso._subject_id('fixture@example.invalid')
    ledger=sso.get_replay_store();ledger.revoke_subject(owner,10)
    real=sqlite3.connect;blocked=[]
    def denied(*args,**kwargs):
        conn=real(*args,**kwargs)
        if args[0].endswith(target+'?mode=rw'):
            def authorizer(action,name,*_):
                if action==sqlite3.SQLITE_READ and name==table:blocked.append(True);return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            conn.set_authorizer(authorizer)
        return conn
    monkeypatch.setattr(sqlite3,'connect',denied)
    with pytest.raises(sqlite3.DatabaseError):report_account.delete_account_reports('fixture@example.invalid')
    assert blocked and ledger.subject_revoked_at(owner)==10


def test_real_report_delete_restore_uses_same_ledger_and_newer_revoke_survives(private,native,monkeypatch):
    shared_assets(private,monkeypatch);owner=sso._subject_id('fixture@example.invalid');store=report_account._get_store()
    row=store.create(query='synthetic',b_id='fixture',lang='en',payload={},model='fixture',creator_anon_id='device');store.claim_by_anon('device',owner)
    ledger=sso.get_replay_store();ledger.issue('code',owner,'free',int(time.time())+300,email='fixture@example.invalid')
    snapshot=report_account.snapshot_account_reports('fixture@example.invalid')
    removed=report_account.delete_account_reports('fixture@example.invalid')
    assert store.get_by_id(row['id']) is None
    later=removed['beta_sessions_revoked_at']+1;ledger.revoke_subject(owner,later)
    report_account.restore_account_reports('fixture@example.invalid',snapshot,removed)
    assert store.get_by_id(row['id'])['owner_user_id']==owner
    assert ledger.subject_revoked_at(owner)==later


def test_real_bad_ledger_logout_never_revokes_auth_jti(private,native,monkeypatch):
    from starlette.requests import Request
    shared_assets(private,monkeypatch)
    settings={'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':'https://beta.structural.bytedance.city',
        'JWT_SECRET':SECRET,'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid',
        'ADMIN_NOTIFICATION_EMAIL':'owner@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1'}
    for name,value in settings.items():monkeypatch.setenv(name,value)
    token,jti=auth._issue_jwt('fixture@example.invalid','free')
    private.unlink()
    request=Request({'type':'http','method':'POST','path':'/api/auth/logout','scheme':'https',
        'server':('beta.structural.bytedance.city',443),
        'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',b'https://beta.structural.bytedance.city'),
                   (b'cookie',('phase_session='+token).encode())]})
    with pytest.raises(paths.RuntimePathError):asyncio.run(auth.logout(request))
    assert auth._store().is_revoked(jti) is False and not private.exists()


def test_ro_preflight_reads_only_metadata_no_row_hook_or_ddl(private,native,monkeypatch):
    actual=sqlite3.connect;reads=[];forbidden=[]
    def guarded(*args,**kwargs):
        conn=actual(*args,**kwargs)
        if args[0]==private.as_uri()+'?mode=ro':
            def authorizer(action,table,*_):
                if action==sqlite3.SQLITE_READ:
                    reads.append(table)
                    if table not in ('sqlite_master','sqlite_schema'):forbidden.append(table);return sqlite3.SQLITE_DENY
                elif action not in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION):
                    forbidden.append(action);return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            conn.set_authorizer(authorizer)
        return conn
    monkeypatch.setattr(sqlite3,'connect',guarded)
    SsoReplayStore(private)
    assert reads and not forbidden


def test_real_runtime_pragma_failure_closes_native_connection(private,native,monkeypatch):
    store=SsoReplayStore(private);actual=sqlite3.connect
    def fault(*args,**kwargs):
        conn=actual(*args,**kwargs)
        if args[0].endswith('?mode=rw'):
            conn.set_authorizer(lambda action,name,*_:sqlite3.SQLITE_DENY
                                if action==sqlite3.SQLITE_PRAGMA and name=='busy_timeout' else sqlite3.SQLITE_OK)
        return conn
    monkeypatch.setattr(sqlite3,'connect',fault)
    with pytest.raises(sqlite3.DatabaseError):store._connect()


def test_failed_formal_factory_publication_is_not_cached(private,native,monkeypatch):
    actual=sqlite3.connect;changed=[]
    def changed_config(*args,**kwargs):
        conn=actual(*args,**kwargs)
        if args[0].endswith('?mode=ro') and not changed:
            monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR','/unapproved');changed.append(True)
        return conn
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',changed_config)
        with pytest.raises(paths.RuntimePathError):sso.get_replay_store()
    assert not sso._REPLAY_STORES
    monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',str(private.parent))
    assert sso.get_replay_store().path==private


_SSO_CHILD=r'''
import sys,os,json,time,sqlite3,socket
from pathlib import Path
owned=Path(os.environ['TMPDIR']).resolve()
def audit(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','sentence_transformers','huggingface_hub'):raise AssertionError('model forbidden')
 if event=='sqlite3.connect':
  from urllib.parse import unquote,urlsplit
  value=str(args[0]);p=Path(unquote(urlsplit(value).path)) if value.startswith('file:') else Path(value)
  assert value==':memory:' or p.is_relative_to(owned)
sys.addaudithook(audit);sys.path[:0]=sys.argv[1:3]
from services import runtime_paths as r
from services.sso_store import SsoReplayStore
root=Path(sys.argv[3]);r.STATE_ROOT=root;r.CACHE_ROOT=root.parent/'cache';r.LOG_ROOT=root/'logs'
os.environ.update(STRUCTURAL_ENV='prod',STRUCTURAL_SSO_DATA_DIR=str(root))
if sys.argv[4]=='missing':
 from services.runtime_paths import RuntimePathError
 from api.sso import get_replay_store
 attempted=[]
 def forbidden(*a,**k):attempted.append(True);raise AssertionError('missing SSO opened native connection')
 sqlite3.connect=forbidden
 for operation in (lambda:SsoReplayStore(root/'sso_replay.sqlite3'),get_replay_store):
  try:operation()
  except RuntimePathError:pass
  else:raise AssertionError('missing replay ledger accepted')
 assert not attempted and not (root/'sso_replay.sqlite3').exists()
 print('SSO_RESULT:'+json.dumps({'missing_rejected':True}));sys.exit(0)
store=SsoReplayStore(root/'sso_replay.sqlite3')
if sys.argv[4]=='consume':
 result=store.consume_once('same-process-race-code',int(time.time())+300)
 print('SSO_RESULT:'+json.dumps({'consumed':result}));sys.exit(0)
if sys.argv[4]=='write':store.consume_once('child-write',int(time.time())+300)
with store._connect() as conn:rows=sorted(row[0] for row in conn.execute('SELECT jti FROM consumed_sso_codes'))
print('SSO_RESULT:'+json.dumps({'rows':rows}))
'''


def peer_command(private,operation):
    import sys
    root=Path(__file__).resolve().parents[3]
    return [sys.executable,'-B','-c',_SSO_CHILD,str(root/'web/backend'),str(root),str(private.parent),operation]


def peer_env(private):
    owned = str(private.parent.parent.resolve())
    return {'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':owned,
        'TMPDIR':owned,'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}


def peer(private,operation):
    import subprocess
    result=subprocess.run(peer_command(private,operation),env=peer_env(private),text=True,capture_output=True,timeout=10)
    assert result.returncode==0,result.stderr
    return json.loads(next(line.split(':',1)[1] for line in result.stdout.splitlines() if line.startswith('SSO_RESULT:')))


def test_real_two_processes_consume_same_code_exactly_once(private):
    import subprocess
    children=[];outcomes=[]
    try:
        for _ in range(2):children.append(subprocess.Popen(peer_command(private,'consume'),env=peer_env(private),text=True,
                                                           stdout=subprocess.PIPE,stderr=subprocess.PIPE))
        for child in children:
            stdout,stderr=child.communicate(timeout=10)
            assert child.returncode==0,stderr
            outcomes.append(json.loads(next(line.split(':',1)[1] for line in stdout.splitlines() if line.startswith('SSO_RESULT:')))['consumed'])
    finally:
        for child in children:
            if child.poll() is None:child.terminate();child.wait(timeout=5)
    assert sorted(outcomes)==[False,True]


def test_live_wal_reader_and_ordinary_peer_close_preserve_both_commits(private,native):
    first=sqlite_utils.connect_private_sso(private)
    try:
        first.execute('BEGIN');first.execute('SELECT count(*) FROM consumed_sso_codes').fetchall()
        second=sqlite_utils.connect_private_sso(private)
        second.execute('SELECT count(*) FROM consumed_sso_codes').fetchall();second.close()
        assert peer(private,'read')['rows']==[]
        assert all(private.with_name(private.name+s).exists() for s in ('-wal','-shm'))
        first.rollback()
        first.execute('INSERT INTO consumed_sso_codes VALUES(?,?,?)',('parent-write',int(time.time()),int(time.time())+300));first.commit()
        assert peer(private,'read')['rows']==['parent-write']
        assert peer(private,'write')['rows']==['child-write','parent-write']
    finally:first.close()
    assert peer(private,'read')['rows']==['child-write','parent-write']


def test_development_schema_creation_and_legacy_directory_fallback(tmp_path,monkeypatch):
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.delenv('STRUCTURAL_SSO_DATA_DIR',raising=False)
    monkeypatch.setenv('AUTH_DATA_DIR',str(tmp_path));monkeypatch.setattr(sso,'_REPLAY_STORES',{})
    store=sso.get_replay_store()
    assert store.path==tmp_path/'sso_replay.sqlite3'
    with store._connect() as conn:assert conn.row_factory is None and conn.isolation_level is None


def test_new_process_missing_ledger_cannot_become_empty_revocation_state(private):
    private.unlink()
    assert peer(private,'missing')=={'missing_rejected':True}
    assert not private.exists()


def test_bad_formal_ledger_start_never_issues_state_cookie_or_redirect(private,monkeypatch):
    from starlette.requests import Request
    private.unlink();issued=[]
    def no_nonce(*args):issued.append(True);raise AssertionError('state capability generated')
    monkeypatch.setattr(sso.secrets,'token_urlsafe',no_nonce)
    request=Request({'type':'http','method':'GET','path':'/api/sso/start','scheme':'https',
        'server':('beta.structural.bytedance.city',443),'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',b'https://beta.structural.bytedance.city')]})
    with pytest.raises(paths.RuntimePathError):asyncio.run(sso.start_exchange(request))
    assert issued==[] and not private.exists()


def test_bad_ledger_issue_never_creates_owner_gate_or_persists_exchange(private,native,monkeypatch):
    from starlette.requests import Request
    shared_assets(private,monkeypatch)
    monkeypatch.setenv('AUTH_ENABLED','true');monkeypatch.setenv('JWT_SECRET',SECRET)
    monkeypatch.setenv('AUTH_LINK_BASE_URL','https://phase.bytedance.city')
    token,_=auth._issue_jwt('fixture@example.invalid','free')
    with auth._store()._connection() as conn:before=conn.execute('SELECT count(*) FROM auth_owner_gates').fetchone()[0]
    private.unlink()
    request=Request({'type':'http','method':'POST','path':'/api/sso/issue','scheme':'https',
        'server':('phase.bytedance.city',443),'headers':[(b'host',b'phase.bytedance.city'),
            (b'origin',b'https://phase.bytedance.city'),(b'cookie',('phase_session='+token).encode())]})
    body=sso.IssueBody(audience='structural-beta',state='s'*40,nonce='n'*40)
    with pytest.raises(paths.RuntimePathError):asyncio.run(sso.issue_exchange_code(body,request))
    with auth._store()._connection() as conn:assert conn.execute('SELECT count(*) FROM auth_owner_gates').fetchone()[0]==before
    assert not private.exists()


def _parent_cleanup_binding(email):
    """The pre-SSO-change digest, including its absolute ledger pathname."""
    import hashlib
    from api import favorites
    binding = {
        "auth": str(auth._store().path.resolve()),
        "favorites": str(favorites._data_file().resolve()),
        "favorites_legacy": str(favorites._legacy_data_file().resolve()),
        "reports": str(report_account._get_store().db_path.resolve()),
        "sso": str((sso._data_dir() / "sso_replay.sqlite3").resolve()),
        "subject": sso._subject_id(email),
        "registry": auth._account_registry().manifest(),
    }
    return hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _development_binding_assets(db, monkeypatch, configuration):
    from api import favorites
    shared_assets(db, monkeypatch)
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    from services.report_store import ReportStore
    monkeypatch.setattr(report_account, '_store', ReportStore(db.parent / 'history.db'))
    monkeypatch.chdir(db.parent.parent)
    if configuration.startswith('explicit'):
        monkeypatch.setenv('STRUCTURAL_SSO_DATA_DIR',
            'state' if configuration.endswith('relative') else str(db.parent))
    else:
        monkeypatch.delenv('STRUCTURAL_SSO_DATA_DIR', raising=False)
        monkeypatch.setenv('AUTH_DATA_DIR',
            'state' if configuration.endswith('relative') else str(db.parent))
    monkeypatch.setenv('STRUCTURAL_FAVORITES_PATH', str(db.parent / 'favorites.jsonl'))
    monkeypatch.setattr(favorites, '_legacy_data_file', lambda: db.parent / 'unused-legacy.jsonl')
    (db.parent / 'favorites.jsonl').write_text(json.dumps({
        'email': 'fixture@example.invalid', 'tickers': ['AAPL'], 'bookmarks': [],
    }) + '\n', encoding='utf-8')
    return favorites


@pytest.mark.parametrize('configuration', [
    'explicit-relative', 'explicit-absolute', 'fallback-relative', 'fallback-absolute',
])
def test_existing_cleanup_binding_preserves_parent_digest(private, native, monkeypatch, configuration):
    _development_binding_assets(private, monkeypatch, configuration)
    old = _parent_cleanup_binding('fixture@example.invalid')
    new = auth._account_cleanup_binding('fixture@example.invalid')
    assert sso.get_replay_store().path.resolve() == private
    assert old == new


@pytest.mark.parametrize('configuration', [
    'explicit-relative', 'explicit-absolute', 'fallback-relative', 'fallback-absolute',
])
def test_parent_pending_deletion_resumes_without_binding_migration(private, native, monkeypatch, configuration):
    favorites = _development_binding_assets(private, monkeypatch, configuration)
    email = 'fixture@example.invalid'
    subject = sso._subject_id(email)
    reports = report_account._get_store()
    item = reports.create(query='synthetic pending job', b_id='fixture', lang='en',
        payload={}, model='fixture', creator_anon_id='pending-device')
    reports.claim_by_anon('pending-device', subject)
    sso.get_replay_store().issue('pending-code', subject, 'free', int(time.time()) + 300, email=email)
    old_binding = _parent_cleanup_binding(email)
    service = auth._account_deletion_service()
    with auth.account_owner_transaction(email) as lease:
        job_id = service.begin_account_deletion_locked(email,
            auth._store().user(email)['session_generation'], auth._store().owner_gate_id(email),
            old_binding, owner_lease=lease)
    before = service.deletion_job(job_id)
    assert before['state'] == 'pending' and before['cleanup_binding'] == old_binding
    assert auth._store().user(email)['lifecycle'] == 'deleting'
    assert auth.pending_account_deletions() == [job_id]
    result = auth.resume_account_deletion(job_id)
    assert result['removed']['favorites']['records'] == 1
    assert result['removed']['claimed_reports']['reports'] == 1
    assert result['removed']['authentication']['account'] == 1
    assert auth._store().user(email) is None
    assert reports.get_by_id(item['id']) is None
    assert favorites.export_account_favorites(email)['exists'] is False
    assert sso.get_replay_store().export_issued_for_subject(subject) == []
    assert auth.pending_account_deletions() == []
    after = service.deletion_job(job_id)
    assert after['state'] == 'completed' and after['cleanup_binding'] == old_binding
    assert auth.resume_account_deletion(job_id) == result
