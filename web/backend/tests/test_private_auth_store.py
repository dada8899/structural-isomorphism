"""Real preprovisioned Auth+Research metadata and native IO; no A2/app release."""
from pathlib import Path
import os,json,sqlite3,importlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from services import runtime_paths as paths,sqlite_utils
from services.auth_store import AuthStore
from research.store import ResearchStore
from api import auth

KEY='0123456789abcdef'*4


@pytest.fixture
def private(tmp_path,monkeypatch):
    state,cache,logs=tmp_path.resolve()/'state',tmp_path.resolve()/'cache',tmp_path.resolve()/'state/logs'
    for folder in (state,cache,logs):folder.mkdir(mode=0o700)
    for name,value in [('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',logs)]:monkeypatch.setattr(paths,name,value)
    monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY',KEY)
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('AUTH_DATA_DIR',str(state))
    db=state/'auth.sqlite3';source=AuthStore(db);ResearchStore(source);db.chmod(0o600)
    audit=state/'account_deletion_audit.jsonl';audit.write_bytes(b'');audit.chmod(0o600)
    monkeypatch.setenv('STRUCTURAL_ENV','prod')
    monkeypatch.setattr(auth,'_AUTH_STORES',{})
    return db


@pytest.fixture
def native(monkeypatch):
    actual=sqlite3.connect;seen=[]
    def recorded(*args,**kwargs):
        conn=actual(*args,**kwargs);seen.append((args,kwargs,conn));return conn
    monkeypatch.setattr(sqlite3,'connect',recorded)
    yield seen
    for _a,_k,conn in seen:
        with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')


def raw(db):return sqlite3.connect(db.as_uri()+'?mode=rw',uri=True,factory=sqlite_utils.ClosingConnection)


def test_real_constructor_preflight_is_ro_no_repairs_and_policy_exact(private,native):
    before=private.read_bytes()
    obj=AuthStore(private)
    assert obj.storage_identity==(private.stat().st_dev,private.stat().st_ino)
    assert private.read_bytes()==before
    assert all(args[0]==':memory:' or args[0]==private.as_uri()+'?mode=ro' for args,_kw,_c in native)
    assert auth._store() is auth._store()


@pytest.mark.parametrize('config',['',' ','relative','file:/bad','/bad'])
def test_formal_bad_config_never_opens_or_creates(private,native,monkeypatch,config):
    monkeypatch.setenv('AUTH_DATA_DIR',config)
    with pytest.raises(paths.RuntimePathError):auth._store()
    assert native==[] and auth._AUTH_STORES=={}


def test_none_unset_defaults_to_approved_root_but_empty_does_not(private,monkeypatch):
    monkeypatch.delenv('AUTH_DATA_DIR')
    assert paths.private_auth_path(None)==private
    with pytest.raises(paths.RuntimePathError):paths.private_auth_path('')


@pytest.mark.parametrize('fault',['missing','parent-mode','file-mode','symlink','hardlink','sidecar'])
def test_existing_formal_storage_checks_before_any_native(private,native,fault):
    if fault=='missing':private.unlink()
    elif fault=='parent-mode':private.parent.chmod(0o755)
    elif fault=='file-mode':private.chmod(0o644)
    elif fault=='symlink':private.rename(private.with_name('real.db'));private.symlink_to(private.with_name('real.db'))
    elif fault=='hardlink':os.link(private,private.with_name('alias.db'))
    else:
        side=private.with_name('auth.sqlite3-wal');side.write_bytes(b'x');side.chmod(0o644)
    with pytest.raises((paths.RuntimePathError,OSError)):AuthStore(private)
    assert native==[]
    if fault=='missing':assert not private.exists()


@pytest.mark.parametrize('change',['missing-policy','extra-policy','wrong-policy','old-research','missing-auth-table','auth-column','aux'])
def test_invalid_structure_or_control_row_rejects_readonly_bytes_unchanged(private,native,change):
    with raw(private) as conn:
        if change=='missing-policy':conn.execute('DELETE FROM auth_owner_gate_policy')
        elif change=='extra-policy':
            conn.execute('PRAGMA ignore_check_constraints=ON');conn.execute("INSERT INTO auth_owner_gate_policy VALUES(2,'extra')")
        elif change=='wrong-policy':conn.execute("UPDATE auth_owner_gate_policy SET fingerprint='wrong'")
        elif change=='old-research':conn.execute('UPDATE research_schema SET version=8')
        elif change=='missing-auth-table':conn.execute('DROP TABLE magic_tokens')
        elif change=='auth-column':conn.execute('ALTER TABLE auth_users ADD COLUMN unexpected TEXT')
        else:conn.execute('CREATE TABLE unexplained_auth_aux(value TEXT)')
    before=private.read_bytes();start=len(native)
    with pytest.raises(Exception):AuthStore(private)
    assert private.read_bytes()==before
    assert all(args[0]==':memory:' or args[0].endswith('?mode=ro') for args,_kw,_conn in native[start:])


def test_preflight_reads_only_schema_version_and_control_policy_no_hooks(private,native,monkeypatch):
    actual=sqlite3.connect;reads=[];sql=[];forbidden=[]
    def guarded(*args,**kwargs):
        conn=actual(*args,**kwargs)
        if args[0]==private.as_uri()+'?mode=ro':
            def authorize(action,table,column,*_):
                if action==sqlite3.SQLITE_READ:
                    reads.append(table)
                    if table not in ('sqlite_master','sqlite_schema','research_schema','auth_owner_gate_policy'):
                        forbidden.append(table);return sqlite3.SQLITE_DENY
                elif action not in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_PRAGMA,sqlite3.SQLITE_TRANSACTION):
                    forbidden.append(action);return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            conn.set_authorizer(authorize);conn.set_trace_callback(sql.append)
        return conn
    monkeypatch.setattr(sqlite3,'connect',guarded)
    AuthStore.preflight_private(private)
    assert not forbidden and reads
    assert not any(q.upper().startswith(('INSERT','UPDATE','DELETE','CREATE','ALTER')) for q in sql)
    assert not any('guard_version(' in q or 'write_allowed(' in q for q in sql)


def test_runtime_connection_preserves_autocommit_hook_policy_and_secure_delete(private,native):
    obj=AuthStore(private)
    with obj._connection() as conn:
        assert conn.isolation_level is None and conn.row_factory is sqlite3.Row and not conn.in_transaction
        assert conn.execute('PRAGMA busy_timeout').fetchone()[0]==10000
        assert conn.execute('PRAGMA secure_delete').fetchone()[0]==1
        assert conn.execute('SELECT research_method_guard_version()').fetchone()[0]==9
        conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('fixture@example.invalid','free','synthetic','generation')")
    with obj._connection() as conn:
        assert conn.execute("SELECT email FROM auth_users WHERE email='fixture@example.invalid'").fetchone()[0]=='fixture@example.invalid'
    with pytest.raises(RuntimeError):
        with obj._connection(bootstrap=True):pass


@pytest.mark.parametrize('point',['hook','pragma','policy'])
def test_configuration_errors_also_close_actual_native(private,native,monkeypatch,point):
    obj=AuthStore(private)
    if point=='hook':
        from research import financial_guard
        monkeypatch.setattr(financial_guard,'install_default_hook',lambda _conn:(_ for _ in ()).throw(RuntimeError('owned hook fault')))
    elif point=='policy':monkeypatch.setattr(obj,'check_gate_policy',lambda _conn:(_ for _ in ()).throw(RuntimeError('owned policy fault')))
    else:
        actual=sqlite3.connect
        def bad(*a,**k):
            conn=actual(*a,**k)
            if a[0].endswith('?mode=rw'):conn.set_authorizer(lambda action,name,*_:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_PRAGMA and name=='secure_delete' else sqlite3.SQLITE_OK)
            return conn
        monkeypatch.setattr(sqlite3,'connect',bad)
    with pytest.raises(Exception):
        with obj._connection():raise AssertionError('bad configuration yielded')


def test_captured_profile_and_cache_preflight_cannot_downgrade(private,native,monkeypatch):
    obj=auth._store();monkeypatch.setenv('STRUCTURAL_ENV','dev')
    with obj._connection() as conn:assert isinstance(conn,sqlite_utils.PrivateAuthConnection)
    monkeypatch.setenv('STRUCTURAL_ENV','prod');private.chmod(0o644)
    with pytest.raises(paths.RuntimePathError):auth._store()


def test_missing_database_never_recreated_by_hot_or_cold_factory(private,native):
    obj=auth._store();private.unlink();before=len(native)
    with pytest.raises(paths.RuntimePathError):auth._store()
    with pytest.raises(paths.RuntimePathError):AuthStore(private)
    with pytest.raises(paths.RuntimePathError):
        with obj._connection():pass
    assert len(native)==before and not private.exists()


def test_lock_dir_port_is_existing_only_for_later_core_a2(private):
    with pytest.raises((OSError,paths.RuntimePathError)):paths.require_private_auth_lock_dir(private)
    folder=private.parent/'research-locks';folder.mkdir(mode=0o700)
    assert paths.require_private_auth_lock_dir(private)==folder
    folder.chmod(0o755)
    with pytest.raises(paths.RuntimePathError):paths.require_private_auth_lock_dir(private)


def test_audit_real_concurrent_complete_records_and_missing_refusal(private):
    file=private.parent/'account_deletion_audit.jsonl'
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda n:auth._append_deletion_audit({'synthetic':n}),range(32)))
    rows=[json.loads(line) for line in file.read_text().splitlines()]
    assert sorted(row['synthetic'] for row in rows)==list(range(32))
    file.unlink()
    with pytest.raises(OSError):auth._append_deletion_audit({'synthetic':99})
    assert not file.exists()


@pytest.mark.parametrize('fault',['mode','symlink','hardlink','unfinished'])
def test_audit_refuses_unsafe_existing_file_without_repair(private,fault):
    file=private.parent/'account_deletion_audit.jsonl'
    if fault=='mode':file.chmod(0o644)
    elif fault=='symlink':file.rename(file.with_suffix('.real'));file.symlink_to(file.with_suffix('.real'))
    elif fault=='hardlink':os.link(file,file.with_suffix('.alias'))
    else:file.write_bytes(b'{"unfinished":')
    before=file.read_bytes()
    with pytest.raises(Exception):auth._append_deletion_audit({'synthetic':1})
    assert file.read_bytes()==before


def test_audit_short_write_and_partial_failure_are_not_faked_success(private,monkeypatch):
    file=private.parent/'account_deletion_audit.jsonl';actual=os.write
    with monkeypatch.context() as patch:
        patch.setattr(os,'write',lambda fd,data:actual(fd,data[:2]))
        auth._append_deletion_audit({'synthetic':'short-writes'})
    assert json.loads(file.read_text())=={'synthetic':'short-writes'}
    count=[]
    def failed(fd,data):
        if not count:count.append(True);return actual(fd,data[:2])
        raise OSError('owned append fault')
    with monkeypatch.context() as patch:
        patch.setattr(os,'write',failed)
        with pytest.raises(OSError):auth._append_deletion_audit({'synthetic':'incomplete'})
    before=file.read_bytes()
    with pytest.raises(paths.RuntimePathError):auth._append_deletion_audit({'synthetic':'next'})
    assert file.read_bytes()==before  # No truncation, retry-delete, or automatic recovery.


@pytest.mark.parametrize('devmode',['true','false'])
def test_production_email_never_uses_mock_outbox(private,monkeypatch,devmode):
    monkeypatch.setenv('AUTH_DEV_MODE',devmode)
    monkeypatch.delenv('SMTP_HOST',raising=False);monkeypatch.delenv('SMTP_FROM_EMAIL',raising=False)
    with pytest.raises(RuntimeError):auth._send_email('fixture@example.invalid','synthetic','never-write-token')
    assert not (private.parent/'mock_email_outbox.jsonl').exists()


def test_production_smtp_failure_never_falls_back_to_file(private,monkeypatch):
    monkeypatch.setenv('AUTH_DEV_MODE','true');monkeypatch.setenv('SMTP_HOST','fixture.invalid')
    monkeypatch.setenv('SMTP_FROM_EMAIL','sender@example.invalid')
    monkeypatch.setattr(auth.smtplib,'SMTP',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('synthetic no-network SMTP fault')))
    with pytest.raises(RuntimeError):auth._send_email('fixture@example.invalid','synthetic','never-write-token')
    assert not (private.parent/'mock_email_outbox.jsonl').exists()


def test_development_initialization_and_mock_delivery_preserved(tmp_path,monkeypatch):
    monkeypatch.setenv('STRUCTURAL_ENV','dev');monkeypatch.setenv('STRUCTURAL_PRIVACY_HMAC_KEY',KEY)
    monkeypatch.setenv('AUTH_DATA_DIR',str(tmp_path));monkeypatch.setenv('AUTH_DEV_MODE','true')
    obj=AuthStore(tmp_path/'auth.sqlite3')
    assert obj.storage_identity is None
    auth._send_email('fixture@example.invalid','synthetic','synthetic body')
    assert json.loads((tmp_path/'mock_email_outbox.jsonl').read_text())['text']=='synthetic body'


def test_legal_alter_nullable_generation_form_is_accepted(private,native):
    with raw(private) as conn:
        conn.execute('ALTER TABLE auth_users RENAME TO old_auth_users')
        conn.execute("CREATE TABLE auth_users(email TEXT PRIMARY KEY,tier TEXT NOT NULL,created_at TEXT NOT NULL,session_generation TEXT)")
        conn.execute("ALTER TABLE auth_users ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','deleting'))")
        conn.execute('DROP TABLE old_auth_users')
    assert AuthStore(private).storage_identity is not None


def test_both_supported_namespaces_same_path_policy_and_native_mutex(private,native,monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    other=importlib.import_module('web.backend.services.runtime_paths')
    for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other,name,getattr(paths,name))
    cls=importlib.import_module('web.backend.services.auth_store').AuthStore
    other_api=importlib.import_module('web.backend.api.auth')
    monkeypatch.setattr(other_api,'_AUTH_STORES',{})
    assert other.HISTORY_OPEN_LOCK is paths.HISTORY_OPEN_LOCK
    assert other_api._data_dir()==auth._data_dir()==private.parent
    assert cls(private).storage_identity==AuthStore(private).storage_identity
    assert other_api._store().storage_identity==auth._store().storage_identity


def test_lowlevel_port_never_starts_tx_hook_or_implicit_create(private,native):
    for readonly in (True,False):
        connection=sqlite_utils.connect_private_auth(private,readonly=readonly)
        try:
            assert not connection.in_transaction and connection.isolation_level is None
            with pytest.raises(sqlite3.OperationalError):connection.execute('SELECT research_method_guard_version()')
        finally:connection.close()
    private.unlink();before=len(native)
    with pytest.raises(paths.RuntimePathError):sqlite_utils.connect_private_auth(private)
    assert len(native)==before and not private.exists()


def test_captured_identity_refuses_replacement_and_cache_does_not_reuse_old_object(private,native):
    old=auth._store()
    # No active native connection while copying the synthetic test image.
    payload=private.read_bytes();private.rename(private.with_name('old.sqlite3'))
    private.write_bytes(payload);private.chmod(0o600)
    with pytest.raises(paths.RuntimePathError):
        with old._connection():pass
    new=auth._store()
    assert new is not old and new.storage_identity!=old.storage_identity


def test_newprocess_missing_auth_store_never_opens_sqlite_or_creates(private):
    import sys,subprocess
    private.unlink()
    script=r'''
import sys,os,sqlite3,socket
from pathlib import Path
sys.path[:0]=sys.argv[1:3]
def audit(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','sentence_transformers','huggingface_hub'):raise AssertionError('model forbidden')
sys.addaudithook(audit)
from services import runtime_paths as r
from services.auth_store import AuthStore
from api import auth
root=Path(sys.argv[3]);r.STATE_ROOT=root;r.CACHE_ROOT=root.parent/'cache';r.LOG_ROOT=root/'logs'
os.environ.update(STRUCTURAL_ENV='prod',AUTH_DATA_DIR=str(root),STRUCTURAL_PRIVACY_HMAC_KEY='0123456789abcdef'*4)
seen=[]
def no_connection(*a,**k):seen.append(True);raise AssertionError('missing auth opened database')
sqlite3.connect=no_connection
for operation in (lambda:AuthStore(root/'auth.sqlite3'),auth._store):
 try:operation()
 except r.RuntimePathError:pass
 else:raise AssertionError('missing auth accepted')
assert not seen and not (root/'auth.sqlite3').exists()
'''
    root=Path(__file__).resolve().parents[3]
    r=subprocess.run([sys.executable,'-B','-c',script,str(root/'web/backend'),str(root),str(private.parent)],
        env={'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':os.environ.get('TMPDIR','/private/tmp'),'PYTHONDONTWRITEBYTECODE':'1'},text=True,capture_output=True,timeout=15)
    assert r.returncode==0,r.stderr


@pytest.fixture
def handler_audit_owner(private,monkeypatch,record_property):
    """Preprovision only the synthetic owner used by the stubbed handler case."""
    import stat
    from uuid import UUID
    with monkeypatch.context() as setup:
        setup.setenv('STRUCTURAL_ENV','dev')
        gate=AuthStore(private).owner_gate_id('fixture@example.invalid')
        folder=private.parent/'research-locks';folder.mkdir(mode=0o700)
        lock=folder/(gate+'.lock');lock.write_bytes(b'');lock.chmod(0o600)
    assert type(gate) is str and str(UUID(gate,version=4))==gate
    for label,path,directory,mode in (
        ('state_root',private.parent,True,0o700),('database',private,False,0o600),
        ('lock_root',folder,True,0o700),('owner_lock',lock,False,0o600),
        ('audit',private.parent/'account_deletion_audit.jsonl',False,0o600),
    ):
        info=path.lstat()
        assert info.st_uid==os.geteuid() and stat.S_IMODE(info.st_mode)==mode
        assert stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        assert info.st_nlink>=1 if directory else info.st_nlink==1
        record_property('handler_audit_fixture.'+label,json.dumps(dict(uid=info.st_uid,
            mode=format(stat.S_IMODE(info.st_mode),'04o'),nlink=info.st_nlink,
            type='directory' if directory else 'regular'),sort_keys=True))
    assert AuthStore(private).owner_gate_id('fixture@example.invalid')==gate


@pytest.mark.usefixtures('handler_audit_owner')
def test_formal_audit_completed_delete_response_boundary_never_retries_core(private,monkeypatch):
    """Handler-only boundary: Core completion/session is explicitly stubbed.

    This is not proof of actual account erasure or a durable Core receipt.
    The journal append and its missing-file error remain real filesystem IO.
    """
    import asyncio
    from starlette.requests import Request
    from contextlib import contextmanager
    store=auth._store()
    user,_=store.ensure_user_and_notification('fixture@example.invalid','free','synthetic')
    calls=[]
    @contextmanager
    def assumed_lease(_):yield object()
    class AssumedCompletedCore:
        def begin_account_deletion_locked(self,*a,**k):return 'assumed-completed-job'
    monkeypatch.setattr(auth,'_auth_unavailable',lambda:None)
    monkeypatch.setattr(auth,'_require_same_origin',lambda _:None)
    monkeypatch.setattr(auth,'resolve_account_user',lambda _:(user,'valid'))
    monkeypatch.setattr(auth,'account_owner_transaction',assumed_lease)
    monkeypatch.setattr(auth,'_account_deletion_service',lambda:AssumedCompletedCore())
    monkeypatch.setattr(auth,'_account_cleanup_binding',lambda _:'synthetic-binding')
    def completed(*a,**k):calls.append(True);return {'removed':{'authentication':1}}
    monkeypatch.setattr(auth,'_run_account_deletion_locked',completed)
    monkeypatch.setenv('JWT_SECRET','A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3')
    (private.parent/'account_deletion_audit.jsonl').unlink()
    request=Request({'type':'http','method':'POST','path':'/api/me/delete','headers':[], 'scheme':'https','server':('fixture.invalid',443)})
    response=asyncio.run(auth.delete_my_account(auth.DeleteAccountBody(confirmation='DELETE'),request))
    assert response.status_code==200 and json.loads(response.body)['ok'] is True
    assert calls==[True] and not (private.parent/'account_deletion_audit.jsonl').exists()


_AUTH_CHILD=r'''
import os,sys,json,sqlite3,socket
from pathlib import Path
root=Path(sys.argv[3]);owned=Path(os.environ['TMPDIR']).resolve()
def audit(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','huggingface_hub','sentence_transformers','safetensors'):raise AssertionError('model forbidden')
 if event=='sqlite3.connect':
  from urllib.parse import unquote,urlsplit
  value=str(args[0]);path=Path(unquote(urlsplit(value).path)) if value.startswith('file:') else Path(value)
  assert value==':memory:' or path.is_relative_to(owned)
sys.addaudithook(audit);sys.path[:0]=sys.argv[1:3]
from services import runtime_paths as r
r.STATE_ROOT=root;r.CACHE_ROOT=root.parent/'cache';r.LOG_ROOT=root/'logs'
os.environ.update(STRUCTURAL_ENV='prod',AUTH_DATA_DIR=str(root),STRUCTURAL_PRIVACY_HMAC_KEY='0123456789abcdef'*4)
if sys.argv[4]=='audit':
 for n in range(16):r.append_private_auth_audit({'worker':sys.argv[5],'n':n})
 print('AUTH_RESULT:'+json.dumps({'audit':16}));sys.exit(0)
from services.auth_store import AuthStore
obj=AuthStore(root/'auth.sqlite3')
with obj._connection() as conn:
 if sys.argv[4]=='write':conn.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('child@example.invalid','free','synthetic','generation')")
 rows=sorted(row[0] for row in conn.execute('SELECT email FROM auth_users'))
print('AUTH_RESULT:'+json.dumps({'users':rows}))
'''


def child_command(private,operation,worker=''):
    import sys
    root=Path(__file__).resolve().parents[3]
    return [sys.executable,'-B','-c',_AUTH_CHILD,str(root/'web/backend'),str(root),str(private.parent),operation,worker]


def child_env(private):
    owned=str(private.parent.resolve())
    return {'PATH':'/usr/bin:/bin:/opt/homebrew/bin','HOME':owned,
            'TMPDIR':owned,'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}


def auth_peer(private,operation):
    import subprocess
    result=subprocess.run(child_command(private,operation),env=child_env(private),capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    return json.loads(next(line.split(':',1)[1] for line in result.stdout.splitlines() if line.startswith('AUTH_RESULT:')))


def test_native_auth_wal_ordinary_peer_close_preserves_two_process_commits(private,native):
    AuthStore(private)
    parent=sqlite_utils.connect_private_auth(private)
    try:
        parent.execute('BEGIN');parent.execute('SELECT count(*) FROM auth_users').fetchall()
        peer=sqlite_utils.connect_private_auth(private)
        peer.execute('SELECT count(*) FROM auth_users').fetchall();peer.close()
        assert auth_peer(private,'read')['users']==[]
        assert all(private.with_name(private.name+s).exists() for s in ('-wal','-shm'))
        parent.rollback()
        parent.execute("INSERT INTO auth_users(email,tier,created_at,session_generation) VALUES('parent@example.invalid','free','synthetic','generation')")
        parent.commit()
        assert auth_peer(private,'read')['users']==['parent@example.invalid']
        assert auth_peer(private,'write')['users']==['child@example.invalid','parent@example.invalid']
    finally:parent.close()
    assert auth_peer(private,'read')['users']==['child@example.invalid','parent@example.invalid']


@pytest.mark.parametrize('inherited_tmpdir',[None,'unrelated'])
def test_child_environment_uses_fixture_root_without_inherited_tmpdir(private,tmp_path,monkeypatch,inherited_tmpdir):
    if inherited_tmpdir is None:monkeypatch.delenv('TMPDIR',raising=False)
    else:
        other=tmp_path/'unrelated-temp';other.mkdir(mode=0o700)
        monkeypatch.setenv('TMPDIR',str(other))
    env=child_env(private)
    assert env['TMPDIR']==env['HOME']==str(private.parent.resolve())
    assert auth_peer(private,'read')['users']==[]


def test_existing_audit_real_multi_process_complete_records(private):
    import subprocess
    children=[]
    try:
        for name in ('one','two','three'):
            children.append(subprocess.Popen(child_command(private,'audit',name),env=child_env(private),
                                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
        for child in children:
            stdout,stderr=child.communicate(timeout=10)
            assert child.returncode==0,stderr
            assert 'AUTH_RESULT:' in stdout
    finally:
        for child in children:
            if child.poll() is None:child.terminate();child.wait(timeout=5)
    rows=[json.loads(line) for line in (private.parent/'account_deletion_audit.jsonl').read_text().splitlines()]
    assert len(rows)==48 and {(r['worker'],r['n']) for r in rows}=={(name,n) for name in ('one','two','three') for n in range(16)}


def test_audit_hardlink_is_rejected_before_opening_a_database_alias(private,monkeypatch):
    parent=sqlite_utils.connect_private_auth(private)
    file=private.parent/'account_deletion_audit.jsonl';original=os.open;attempted=[]
    try:
        parent.execute('BEGIN');parent.execute('SELECT count(*) FROM auth_users').fetchall()
        file.unlink();os.link(private,file)
        def no_audit_open(path,*args,**kwargs):
            if path=='account_deletion_audit.jsonl':attempted.append(True);raise AssertionError('database alias opened')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(os,'open',no_audit_open)
        with pytest.raises(paths.RuntimePathError):auth._append_deletion_audit({'synthetic':1})
        file.unlink()  # Test-owned fault removed while the native reader stays live.
        assert not attempted and auth_peer(private,'read')['users']==[]
        assert all(private.with_name(private.name+suffix).exists() for suffix in ('-wal','-shm'))
    finally:parent.close()


def test_failed_audit_fsync_closes_real_descriptors_without_repair(private,monkeypatch):
    original_open=os.open;opened=[]
    def observed(path,*args,**kwargs):
        fd=original_open(path,*args,**kwargs)
        if path=='account_deletion_audit.jsonl':opened.append(fd)
        return fd
    monkeypatch.setattr(os,'open',observed)
    monkeypatch.setattr(os,'fsync',lambda _fd:(_ for _ in ()).throw(OSError('synthetic fsync fault')))
    with pytest.raises(OSError):auth._append_deletion_audit({'synthetic':'durability-unknown'})
    assert len(opened)==1
    with pytest.raises(OSError):os.fstat(opened[0])
    # The row was written, but the function did not return a durability success.
    assert json.loads((private.parent/'account_deletion_audit.jsonl').read_text())=={'synthetic':'durability-unknown'}


def test_live_object_connection_also_refuses_extra_policy_control_row(private,native):
    obj=AuthStore(private)
    with raw(private) as conn:
        conn.execute('PRAGMA ignore_check_constraints=ON')
        conn.execute("INSERT INTO auth_owner_gate_policy VALUES(2,'ambiguous')")
    with pytest.raises(RuntimeError):
        with obj._connection():raise AssertionError('ambiguous policy yielded authority')
