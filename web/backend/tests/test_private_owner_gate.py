"""Native preprovisioned account mapping and stable owner-lock consumers."""
import os
import sqlite3
import fcntl
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from .test_research_private_storage import prepared,private,native,raw
from research.authorization import AuthorizationGate
from services import runtime_paths as paths
from .test_private_registration import register_private_user,corrupt_auth_fixture,FIXTURE_SECRET


def test_formal_mapping_and_lock_reuse_existing_identity_without_writes(prepared,native):
    obj=prepared['auth'];lock=prepared['lock'];before=(lock.stat().st_dev,lock.stat().st_ino)
    assert obj.owner_gate_id('  '+prepared['actor'].email.upper()+'  ')==prepared['gate']
    assert all(args[0].endswith('?mode=ro') for args,_kw,_conn in native)
    with AuthorizationGate(prepared['store']).owner_gate_id(prepared['gate']) as lease:
        assert lease.identity[:2]==before
    with pytest.raises(PermissionError):lease.identity
    assert (lock.stat().st_dev,lock.stat().st_ino)==before


@pytest.mark.parametrize('fault',['missing','uuid','type','policy','identity','path','profile'])
def test_auth_direct_owner_mapping_fails_closed_without_insert(prepared,native,monkeypatch,fault):
    obj=prepared['auth'];path=prepared['path'];email=prepared['actor'].email
    if fault in ('missing','uuid','type','policy'):
        with raw(path) as conn,corrupt_auth_fixture(conn,'auth_owner_gates'):
            if fault=='missing':conn.execute('DELETE FROM auth_owner_gates')
            elif fault=='policy':conn.execute("UPDATE auth_owner_gate_policy SET fingerprint='wrong'")
            else:conn.execute('UPDATE auth_owner_gates SET gate_id=?',('wrong' if fault=='uuid' else b'not-text',))
    elif fault=='identity':obj._storage_identity=(0,0)
    elif fault=='path':obj.path=path.with_name('other.sqlite3')
    else:
        obj._private_auth=False
    before=path.read_bytes();start=len(native)
    with pytest.raises((RuntimeError,OSError,sqlite3.Error)):obj.owner_gate_id(email)
    assert path.read_bytes()==before
    assert all(args[0].endswith('?mode=ro') for args,_kw,_conn in native[start:])
    assert not path.with_name('other.sqlite3').exists()


@pytest.mark.parametrize('fault',['directory','file','directory-mode','file-mode','symlink','hardlink'])
def test_account_owner_transaction_missing_or_unsafe_lock_never_creates_or_writes(prepared,monkeypatch,fault):
    from api import auth
    lock=prepared['lock'];root=lock.parent
    if fault=='directory':lock.unlink();root.rmdir()
    elif fault=='file':lock.unlink()
    elif fault=='directory-mode':root.chmod(0o755)
    elif fault=='file-mode':lock.chmod(0o644)
    elif fault=='symlink':lock.rename(lock.with_name('saved'));lock.symlink_to(lock.with_name('saved'))
    else:os.link(lock,lock.with_name('alias'))
    before=prepared['path'].read_bytes();names=sorted(p.name for p in root.iterdir()) if root.exists() else None
    monkeypatch.setattr(auth,'_store',lambda:prepared['auth'])
    with pytest.raises((RuntimeError,OSError)):
        with auth.account_owner_transaction(prepared['actor'].email):pytest.fail('unsafe lock yielded a lease')
    assert prepared['path'].read_bytes()==before
    assert (sorted(p.name for p in root.iterdir()) if root.exists() else None)==names


@pytest.mark.parametrize('target',['directory','file'])
def test_replacement_while_acquiring_flock_rejects_and_closes_all_fds(prepared,monkeypatch,target):
    original=fcntl.flock;opened=[];real_open=os.open;changed=[]
    def observed(*args,**kwargs):
        fd=real_open(*args,**kwargs);opened.append(fd);return fd
    def replace(fd,operation):
        original(fd,operation)
        if not changed:
            changed.append(True);lock=prepared['lock']
            if target=='directory':
                lock.parent.rename(lock.parent.with_name('old-locks'));lock.parent.mkdir(mode=0o700)
            else:lock.rename(lock.with_name('old-lock'))
            lock.write_bytes(b'');lock.chmod(0o600)
    monkeypatch.setattr(os,'open',observed);monkeypatch.setattr(fcntl,'flock',replace)
    with pytest.raises(paths.RuntimePathError):
        with AuthorizationGate(prepared['store']).owner_gate_id(prepared['gate']):pytest.fail('replaced lock yielded')
    for fd in opened:
        with pytest.raises(OSError):os.fstat(fd)


def test_lock_replacement_during_lease_retires_it_and_pid_cannot_reuse(prepared):
    with pytest.raises(paths.RuntimePathError):
        with AuthorizationGate(prepared['store']).owner_gate_id(prepared['gate']) as lease:
            child=os.fork()
            if child==0:
                try:lease.identity
                except PermissionError:os._exit(0)
                os._exit(2)
            _,status=os.waitpid(child,0);assert os.waitstatus_to_exitcode(status)==0
            lock=prepared['lock'];lock.rename(lock.with_name('old-lock'));lock.write_bytes(b'');lock.chmod(0o600)
    with pytest.raises(PermissionError):lease.identity


def test_formal_owner_mapping_remains_readonly_after_environment_downgrade(prepared,native,monkeypatch):
    monkeypatch.setenv('STRUCTURAL_ENV','dev')
    assert prepared['auth'].owner_gate_id(prepared['actor'].email)==prepared['gate']
    with AuthorizationGate(prepared['store']).owner_gate_id(prepared['gate']):pass
    assert all(args[0].endswith('?mode=ro') for args,_kw,_conn in native)


@pytest.mark.parametrize('fault',['missing','uuid','type','policy'])
@pytest.mark.parametrize('downgrade',[False,True])
def test_direct_owner_gate_in_cannot_bypass_preprovisioned_mapping(prepared,monkeypatch,fault,downgrade):
    from services.sqlite_utils import connect_private_auth
    with raw(prepared['path']) as conn,corrupt_auth_fixture(conn,'auth_owner_gates'):
        if fault=='missing':conn.execute('DELETE FROM auth_owner_gates')
        elif fault=='policy':conn.execute("UPDATE auth_owner_gate_policy SET fingerprint='wrong'")
        else:conn.execute('UPDATE auth_owner_gates SET gate_id=?',('bad' if fault=='uuid' else b'bad',))
    before=prepared['path'].read_bytes()
    if downgrade:monkeypatch.setenv('STRUCTURAL_ENV','dev')
    conn=connect_private_auth(prepared['path'],readonly=True,expected_identity=prepared['auth'].storage_identity)
    try:
        conn.execute('BEGIN')
        with pytest.raises(RuntimeError):prepared['auth'].owner_gate_in(conn,prepared['actor'].email,preferred=str(uuid4()))
    finally:conn.close()
    assert prepared['path'].read_bytes()==before


def test_plain_connection_marker_cannot_become_a_private_mapping_consumer(prepared):
    from types import SimpleNamespace
    from services.sqlite_utils import ClosingConnection
    fake=SimpleNamespace(private_storage_identity=prepared['auth'].storage_identity,in_transaction=True,
        execute=lambda *_:pytest.fail('plain connection DTO reached SQL'))
    with pytest.raises(paths.RuntimePathError):prepared['auth'].owner_gate_in(fake,prepared['actor'].email)
    with sqlite3.connect(':memory:',factory=ClosingConnection) as ordinary:
        ordinary.execute('BEGIN')
        with pytest.raises(paths.RuntimePathError):prepared['auth'].owner_gate_in(ordinary,prepared['actor'].email)


def test_direct_mapping_recognizes_actual_private_native_connection_in_both_namespaces(prepared,monkeypatch):
    from services.sqlite_utils import connect_private_auth
    from web.backend.services import runtime_paths as other_paths
    from web.backend.services.auth_store import AuthStore as OtherAuth
    for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other_paths,name,getattr(paths,name))
    conn=connect_private_auth(prepared['path'],readonly=True,expected_identity=prepared['auth'].storage_identity)
    try:
        conn.execute('BEGIN')
        assert OtherAuth.owner_gate_in(conn,prepared['actor'].email)==prepared['gate']
    finally:conn.close()


@pytest.mark.parametrize('mapped',[False,True])
def test_formal_first_principal_missing_map_or_lock_does_not_commit_any_research_rows(private,monkeypatch,mapped):
    from services.auth_store import AuthStore
    from research import ResearchStore,ResearchService
    from research.authorization import AccountIdentity
    from research.schemas import CreateResearchRequest
    from .test_research_persistence import problem
    email='a2-unprovisioned@example.invalid';user,token=register_private_user(monkeypatch,email)
    obj=AuthStore(private);gate=obj.owner_gate_id(email)
    (private.parent/'research-locks'/(gate+'.lock')).unlink();(private.parent/'research-locks').rmdir()
    if not mapped:
        with raw(private) as conn,corrupt_auth_fixture(conn,'auth_owner_gates'):conn.execute('DELETE FROM auth_owner_gates')
    store=ResearchStore(obj)
    import jwt
    claims=jwt.decode(token,os.getenv('JWT_SECRET') or FIXTURE_SECRET,algorithms=['HS256'])
    actor=AccountIdentity(email,user['session_generation'],claims['jti'],claims['exp'])
    with pytest.raises((RuntimeError,OSError)):
        ResearchService(store).create(actor,CreateResearchRequest(problem=problem()),'unprovisioned-create')
    with store.transaction() as conn:
        principals=conn.execute('SELECT count(*) FROM research_principals').fetchone()[0]
        mappings=conn.execute('SELECT count(*) FROM auth_owner_gates').fetchone()[0]
        assert conn.execute('SELECT count(*) FROM research_controls').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_grants').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_idempotency').fetchone()[0]==0
    assert principals==0 and mappings==int(mapped) and not (private.parent/'research-locks').exists()


@pytest.fixture
def first_owner(private,monkeypatch):
    from services.auth_store import AuthStore
    from research import ResearchStore
    from research.authorization import AccountIdentity
    email='a2-first-owner@example.invalid';user,token=register_private_user(monkeypatch,email)
    auth=AuthStore(private);gate=auth.owner_gate_id(email);folder=private.parent/'research-locks';lock=folder/(gate+'.lock')
    store=ResearchStore(auth)
    import jwt
    claims=jwt.decode(token,os.getenv('JWT_SECRET') or FIXTURE_SECRET,algorithms=['HS256'])
    return dict(path=private,auth=auth,store=store,gate=gate,lock=lock,actor=AccountIdentity(email,user['session_generation'],claims['jti'],claims['exp']))


@pytest.mark.parametrize('change',['revoke','generation','lifecycle','mapping'])
def test_first_principal_rechecks_account_and_mapping_after_waiting_for_actual_lock(first_owner,monkeypatch,change):
    from research import ResearchService
    from research.errors import ResearchError
    from research.schemas import CreateResearchRequest
    from .test_research_persistence import problem
    data=first_owner;reached=threading.Event();flock=fcntl.flock
    pool=ThreadPoolExecutor(max_workers=1)
    try:
        with AuthorizationGate(data['store']).owner_gate_id(data['gate']):
            def observed(fd,operation):
                try:return flock(fd,operation)
                except BlockingIOError:reached.set();raise
            monkeypatch.setattr(fcntl,'flock',observed)
            future=pool.submit(ResearchService(data['store']).create,data['actor'],CreateResearchRequest(problem=problem()),'first-wait')
            assert reached.wait(5)
            with data['auth']._connection() as conn:
                if change=='revoke':conn.execute('INSERT INTO revoked_sessions(jti,revoked_at,email) VALUES(?,?,?)',(data['actor'].jti,'synthetic',data['actor'].email))
                elif change in ('generation','lifecycle'):
                    with corrupt_auth_fixture(conn,'auth_users'):
                        if change=='generation':conn.execute("UPDATE auth_users SET session_generation='changed'")
                        else:conn.execute("UPDATE auth_users SET lifecycle='deleting'")
                else:
                    with corrupt_auth_fixture(conn,'auth_owner_gates'):conn.execute('UPDATE auth_owner_gates SET gate_id=?',(str(uuid4()),))
        with pytest.raises(ResearchError) as rejected:future.result(timeout=10)
        assert rejected.value.code==('AUTHORIZATION_STALE' if change=='mapping' else 'AUTH_REQUIRED')
    finally:pool.shutdown(wait=True)
    with data['store'].transaction() as conn:
        for table in ('research_principals','research_controls','research_grants','research_idempotency'):
            assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==0


def test_two_actual_concurrent_first_creates_share_one_principal_and_idempotent_research(first_owner):
    from research import ResearchService
    from research.schemas import CreateResearchRequest
    from .test_research_persistence import problem
    data=first_owner;request=CreateResearchRequest(problem=problem());service=ResearchService(data['store'])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:service.create(data['actor'],request,'concurrent-first'),range(2)))
    assert results[0]==results[1]
    with data['store'].transaction() as conn:
        for table in ('research_principals','research_controls','research_idempotency'):
            assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==1


def test_existing_principal_cannot_be_returned_under_a_different_preprovisioned_gate(prepared):
    from research import ResearchService
    from research.errors import ResearchError
    from research.schemas import CreateResearchRequest
    from .test_research_persistence import problem
    with prepared['store'].transaction(write=True) as conn:conn.execute('UPDATE research_principals SET gate_id=?',(str(uuid4()),))
    with pytest.raises(ResearchError):ResearchService(prepared['store']).create(prepared['actor'],CreateResearchRequest(problem=problem()),'wrong-principal-gate')
    with prepared['store'].transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_controls').fetchone()[0]==1
