"""Actual formal Auth -> Research account lifecycle; no caller-made authority."""
import sqlite3
import pytest
from api import auth
from research import ResearchStore
from research.authorization import AuthorizationGate
from research.formula_runtime import recover_formula_journal
from services.auth_store import AuthStore
from services.runtime_paths import RuntimePathError
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack,link,verify,BETA
from .test_research_formula_lifecycle import formula_problem
from .test_research_persistence import envelope


def configure(client,root,monkeypatch):
    from api import research,favorites,sso,report,report_account
    from errors import install_problem_handlers
    monkeypatch.setattr(research,'enabled',lambda:True)
    monkeypatch.setattr(sso,'_REPLAY_STORES',{})
    monkeypatch.setattr(report_account,'_store',None);monkeypatch.setattr(report,'_store',None)
    monkeypatch.setattr(favorites,'_legacy_data_file',lambda:root/'absent-legacy-favorites.jsonl')
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB',str(root/'history.db'))
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET','synthetic-share-secret')
    for router in (research.router,favorites.router,sso.router,report.router,report_account.router):client.app.include_router(router,prefix='/api')
    install_problem_handlers(client.app)




def test_formal_gate_rejects_safe_replacement_inode_even_before_any_research(stack):
    client,root,mail=stack
    assert verify(client,link(client,mail)).status_code==200
    store=auth._store();gate=store.owner_gate_id('fresh@example.invalid')
    lock=root/'research-locks'/(gate+'.lock');old=lock.with_suffix('.original')
    lock.rename(old);lock.write_bytes(b'');lock.chmod(0o600)
    assert lock.stat().st_ino!=old.stat().st_ino
    try:
        for target in (store,ResearchStore(store)):
            with pytest.raises((RuntimePathError,PermissionError)):
                with AuthorizationGate(target).owner_gate_id(gate):pytest.fail('replacement inode was admitted')
    finally:
        lock.unlink();old.rename(lock)
    with AuthorizationGate(store).owner_gate_id(gate) as lease:
        assert lease.identity[:2]==store.expected_owner_gate_identity(gate)


def test_offline_formula_port_accepts_exact_current_auth_metadata_without_mutation(roots):
    from services.auth_registration import bootstrap_private_runtime
    bootstrap_private_runtime();db=roots/'auth.sqlite3';before=db.stat()
    store=AuthStore(db)
    with store._connection() as conn:
        conn.execute('BEGIN')
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,15)]
        ResearchStore._check_v15(conn)
        schema_before=list(map(tuple,conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')))
    result=recover_formula_journal(db)
    assert result['schema_version']==15 and result['current_app_compatible'] is True
    assert (db.stat().st_dev,db.stat().st_ino)==(before.st_dev,before.st_ino)
    with AuthStore(db)._connection() as conn:
        conn.execute('BEGIN')
        assert AuthStore.check_offline_auth_metadata(conn)=='auth-provision-v1'
        assert list(map(tuple,conn.execute('SELECT * FROM research_schema')))==[(1,15)]
        ResearchStore._check_v15(conn)
        assert list(map(tuple,conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name')))==schema_before


def exchange_sso(client):
    import jwt
    from api import sso
    from .test_private_registration import SECRET
    started=client.get('/api/sso/start',follow_redirects=False)
    assert started.status_code==303,started.text
    state=jwt.decode(started.cookies.get(sso._STATE_COOKIE),SECRET,algorithms=['HS256'],audience='structural-beta-start',issuer=BETA)
    issued=client.post('/api/sso/issue',json={'audience':'structural-beta','state':state['state'],'nonce':state['nonce']},headers={'origin':BETA})
    assert issued.status_code==200,issued.text
    exchanged=client.post('/api/sso/exchange',json={'code':issued.json()['code'],'state':state['state']},headers={'origin':BETA})
    assert exchanged.status_code==200,exchanged.text
    assert not client.cookies.get('phase_session')
    return client.cookies.get(sso._BETA_SESSION_COOKIE)


def test_actual_sso_only_delete_revokes_old_sso_after_reregistration(stack,monkeypatch):
    client,root,mail=stack;configure(client,root,monkeypatch)
    assert verify(client,link(client,mail)).status_code==200
    generation=auth._store().user('fresh@example.invalid')['session_generation']
    cookie=exchange_sso(client)
    assert client.get('/api/auth/me').status_code==200
    deleted=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert deleted.status_code==200,deleted.text
    assert verify(client,link(client,mail)).status_code==200
    assert auth._store().user('fresh@example.invalid')['session_generation']!=generation
    from api import sso
    client.cookies.clear();client.cookies.set(sso._BETA_SESSION_COOKIE,cookie,domain='beta.structural.bytedance.city',path='/')
    assert client.get('/api/auth/me').status_code==401


@pytest.mark.parametrize('damage',['tampered','expired','issuer','audience','foreign','logout','revoked'])
def test_real_sso_delete_rejects_invalid_or_withdrawn_credentials_before_fence(stack,monkeypatch,damage):
    import jwt,time
    from api import sso
    from .test_private_registration import SECRET
    client,root,mail=stack;configure(client,root,monkeypatch)
    assert verify(client,link(client,mail)).status_code==200
    direct=client.cookies.get('phase_session');cookie=exchange_sso(client)
    claims=jwt.decode(cookie,SECRET,algorithms=['HS256'],audience='structural-beta-session',issuer=BETA)
    if damage=='foreign':
        assert verify(client,link(client,mail,email='foreign@example.invalid')).status_code==200
        cookie=exchange_sso(client)
    elif damage=='tampered':
        parts=cookie.split('.');parts[2]=('A' if parts[2][0]!='A' else 'B')+parts[2][1:];cookie='.'.join(parts)
    elif damage in ('expired','issuer','audience'):
        if damage=='expired':claims['exp']=int(time.time())-10
        elif damage=='issuer':claims['iss']='https://foreign.invalid'
        else:claims['aud']='foreign-audience'
        cookie=jwt.encode(claims,SECRET,algorithm='HS256')
    elif damage=='logout':assert client.post('/api/auth/logout',headers={'origin':BETA}).status_code==200
    else:sso.get_replay_store().revoke_subject(claims['sub'])
    client.cookies.clear();client.cookies.set(sso._BETA_SESSION_COOKIE,cookie,domain='beta.structural.bytedance.city',path='/')
    if damage=='foreign':client.cookies.set('phase_session',direct,domain='beta.structural.bytedance.city',path='/')
    denied=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert denied.status_code in (401,409),denied.text
    with auth._store()._connection() as conn:
        assert conn.execute("SELECT lifecycle FROM auth_users WHERE email='fresh@example.invalid'").fetchone()[0]=='active'
        assert conn.execute('SELECT count(*) FROM auth_deletion_jobs').fetchone()[0]==0






def test_ssosubject_revocation_during_real_capability_use_prevents_fence(stack,monkeypatch):
    from services import auth_registration as registration
    from research.paid_control import SsoAccountDeletionIdentity
    from api import sso
    client,root,mail=stack;configure(client,root,monkeypatch)
    assert verify(client,link(client,mail)).status_code==200
    exchange_sso(client);original=registration.mark_account_deleting;observed=[]
    def revoke(conn,**kwargs):
        source=kwargs['request_source']
        assert type(source.identity) is SsoAccountDeletionIdentity and not hasattr(source.identity,'jti')
        sso.get_replay_store().revoke_subject(source.identity.subject);observed.append(True)
        return original(conn,**kwargs)
    monkeypatch.setattr(registration,'mark_account_deleting',revoke)
    result=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert result.status_code!=200 and observed==[True]
    with auth._store()._connection() as conn:
        assert conn.execute("SELECT lifecycle FROM auth_users WHERE email='fresh@example.invalid'").fetchone()[0]=='active'
        assert conn.execute('SELECT count(*) FROM auth_deletion_jobs').fetchone()[0]==0


def test_real_signed_sso_cookie_in_fabricated_request_cannot_mint_delete_source(stack,monkeypatch):
    from starlette.requests import Request
    from research.paid_control import issue_authenticated_action,AuthenticatedActionSource,SsoAccountDeletionIdentity
    from api import sso
    client,root,mail=stack;configure(client,root,monkeypatch)
    assert verify(client,link(client,mail)).status_code==200
    cookie=exchange_sso(client)
    request=Request({'type':'http','method':'POST','scheme':'https','path':'/api/me/delete','query_string':b'',
        'server':('beta.structural.bytedance.city',443),'headers':[(b'origin',BETA.encode()),
        (b'cookie',(sso._BETA_SESSION_COOKIE+'='+cookie).encode())]})
    request._body=b'{"confirmation":"DELETE"}'
    with pytest.raises(PermissionError):issue_authenticated_action(request,action='account-delete')
    with pytest.raises(TypeError):AuthenticatedActionSource(identity=SsoAccountDeletionIdentity('fresh@example.invalid','g',2**40,'s',1))
    with auth._store()._connection() as conn:
        assert conn.execute('SELECT count(*) FROM auth_deletion_jobs').fetchone()[0]==0
