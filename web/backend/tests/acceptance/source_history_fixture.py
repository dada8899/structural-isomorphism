"""Synthetic historical Source preparation, never a Main/Source enablement port.

Enter before configuring signing secrets or starting Main. Start/stop the real
Main *inside* this context. On any body/cleanup failure retain the owned root;
never retry an unknown preparation or erase an uncertain save. Only the old13
controlled component has fixture feature overrides and an in-memory mail sink.
Current production flags, routes, permission checks and Main binding stay intact.
"""
from contextlib import contextmanager,closing
from dataclasses import dataclass
from functools import partial
import hashlib,importlib,json,os,secrets,shutil,signal,sqlite3,subprocess,sys
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

ORIGIN='https://beta.structural.bytedance.city'
_KEY_NAMES=('JWT_SECRET','STRUCTURAL_SSO_SECRET','STRUCTURAL_PRIVACY_HMAC_KEY')
_FRAME='SOURCE_HISTORY_PRIVATE_FRAME:'


@dataclass(frozen=True,slots=True)
class PreparedSourceHistory:
    owned_root: Path
    state_root: Path
    cache_root: Path
    log_root: Path
    research_id: str
    source_task_id: str
    email: str
    origin: str
    source_input_revision: int
    current_input_revision: int
    research_version: int
    excerpt_refs: tuple[dict,...]
    acquired_at: str
    mode: str
    schema_version: int
    original_source_code_manifest_sha256: str
    original_loaded_modules_sha256: str
    original_source_rows_digest: str


def _rows_digest(conn):
    tables=('research_principals','research_controls','research_revisions','research_grants','research_tasks',
        'research_source_resources','research_source_runs','research_source_approvals','research_source_chains',
        'research_source_requests','research_evidence_objects','auth_users','auth_owner_gates','auth_owner_gate_policy')
    def value(item):return {'bytes_sha256':hashlib.sha256(item).hexdigest()} if type(item) is bytes else item
    rows={name:[[value(item) for item in row] for row in conn.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in tables}
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def _loaded_old(package,manifest):
    expected=json.loads(manifest.read_text())['cases']['native']['files'];actual={}
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0] not in ('api','services','research') and not name.startswith('web.backend'):continue
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve()
        if not path.is_relative_to(package) or path.suffix!='.py':raise RuntimeError('mixed historical source')
        relative=path.relative_to(package).as_posix();sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if relative not in expected or expected[relative]['sha256']!=sha:raise RuntimeError('historical source digest mismatch')
        actual[name]={'path':relative,'sha256':sha}
    return actual


def _child(package,manifest,state,origin,email,target_revision):
    package=Path(package).resolve();manifest=Path(manifest);state=Path(state)
    _loaded_old(package,manifest)
    from services import runtime_paths as paths
    paths.STATE_ROOT=state;paths.CACHE_ROOT=state.parent/'cache';paths.LOG_ROOT=state/'logs'
    from services.auth_registration import bootstrap_private_runtime
    if bootstrap_private_runtime()['research_schema']!=13:raise RuntimeError('complete old13 required')
    from api import auth,research
    from research import ResearchStore,ResearchRunner,source_integration
    from research.source_policy import PinnedPublicTransport
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web.backend.tests.source_http_fixture import source_server,get_local
    # Historical synthetic component only. This is neither formal13 Main nor
    # any current14 Source execution/admission. No model or funding producer.
    mail=[];auth._send_email=lambda _to,_subject,text:mail.append(text)
    research.enabled=lambda:True;source_integration.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    def post(client,path,data,key):
        response=client.post(path,json={'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':data},headers={'origin':origin,'idempotency-key':key})
        if response.status_code!=200:raise RuntimeError('historical HTTP preparation rejected')
        return response.json()['data']
    _loaded_old(package,manifest)
    with TestClient(app,base_url=origin) as client:
        if client.post('/api/auth/request-link',json={'email':email},headers={'origin':origin}).status_code!=200:raise RuntimeError('synthetic registration rejected')
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        if client.post('/api/auth/verify',json={'token':token},headers={'origin':origin}).status_code!=200:raise RuntimeError('synthetic verification rejected')
        problem={'entry':'phenomenon','original_input':'我观察到合成队列在任务集中到达时等待变长。','objective':'记录等待','summary':'仅供受控历史来源准备的合成问题。','variables':[],'constraints':['Synthetic historical fixture only'],'unknowns':['Arrival process unknown'],'confirmed':True}
        rid=post(client,'/api/research',{'problem':problem},'source-history-create')['research']['id'];base='/api/research/'+rid
        query={'input_revision':1,'expected_research_version':1,'query':'queue theory'}
        preview=post(client,base+'/source-preview',query,'source-history-preview')
        approved=post(client,base+'/source-approvals',{**query,'confirm_external':True,'preview_digest':preview['preview_digest']},'source-history-approve')
        task=post(client,base+'/source-tasks',{'input_revision':1,'expected_research_version':1,'approval_ref':approved['approval_ref']},'source-history-start')['task']['id']
        store=ResearchStore(auth._store())
        with source_server() as (port,calls):
            if ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(task)!='COMPLETED' or calls!=['/discovery','/article']:
                raise RuntimeError('owned Source worker did not complete')
        if target_revision:
            problem={**problem,'original_input':'合成队列的新观察：服务时间变化也可能影响等待。'}
            post(client,base+'/revisions',{'expected_revision':1,'problem':problem},'source-history-target')
        with store.transaction() as conn:
            snapshot=json.loads(conn.execute("SELECT payload FROM research_evidence_objects WHERE task_id=? AND kind='snapshots'",(task,)).fetchone()[0])
            refs=[]
            for row in conn.execute("SELECT payload FROM research_evidence_objects WHERE task_id=? AND kind='excerpts' ORDER BY id",(task,)):
                excerpt=json.loads(row[0]);refs.append({'excerpt_id':excerpt['id'],'source_revision':snapshot['source_revision'],
                    'content_digest':snapshot['extracted_digest'],'start':excerpt['start'],'end':excerpt['end']})
            control=conn.execute('SELECT current_revision,version FROM research_controls WHERE id=?',(rid,)).fetchone()
            digest=_rows_digest(conn)
            if not refs or snapshot['origin']!='offline_probe' or conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]!=0:raise RuntimeError('pure historical fixture required')
        result={'research_id':rid,'source_task_id':task,'current_input_revision':control[0],'research_version':control[1],
            'excerpt_refs':refs,'acquired_at':snapshot['acquired_at'],'rows_digest':digest,
            'loaded_old_modules':_loaded_old(package,manifest),'cookie':client.cookies.get('phase_session')}
    # Private anonymous stdout pipe only; parent never logs/saves this frame.
    sys.stdout.write(_FRAME+json.dumps(result,separators=(',',':'))+'\n');sys.stdout.flush()


def _read_current(state,result,cookie):
    from api import auth
    from services.auth_store import AuthStore
    from research import ResearchStore
    from research.authorization import AccountIdentity
    from research.source_integration import context_for,authorizer
    from research.evidence_repository import EvidenceRepository
    claims=auth._decode_jwt(cookie)
    if not claims:raise RuntimeError('actual signed historical session required')
    actor=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp']);store=ResearchStore(AuthStore(state/'auth.sqlite3'))
    with store.transaction() as conn:
        schema=conn.execute('SELECT version FROM research_schema').fetchone()[0]
        if schema!=15 or _rows_digest(conn)!=result['rows_digest']:raise RuntimeError('historical bindings changed')
        repository=EvidenceRepository(conn,authorizer(store,identity=actor));context=context_for(conn,result['source_task_id'])
        for ref in result['excerpt_refs']:
            details=repository.excerpt_details(context,ref['excerpt_id'])
            if any(details[key]!=ref[key] for key in ('source_revision','content_digest','start','end')) or details['input_revision']!=1:raise RuntimeError('historical excerpt changed')
            excerpt=repository.get(context,'excerpts',ref['excerpt_id']);snapshot=repository.get(context,'snapshots',excerpt.snapshot_id)
            if snapshot.acquired_at!=result['acquired_at'] or not snapshot.licence.display_excerpt or snapshot.origin!='offline_probe':raise RuntimeError('original time or permission changed')
    return schema


@contextmanager
def prepared_source_history(source_root,owned_root,*,origin=ORIGIN,email='source-history@example.invalid',target_revision=False):
    """Yield safe refs after controlled13 -> reviewed offline14/15 -> real reader.

    Must precede parent signing configuration/Main startup. Synthetic keys stay
    only in parent/child memory and environment for this context; no caller keys
    are read/adopted. Configure any real-Main test SMTP sink separately inside.
    The default leaves revision1; the actual Main/UI creates revision2 later.
    Main must shut down before this context exits. Exceptions retain owned data.
    """
    source_root=Path(source_root).resolve();owned_root=Path(owned_root).resolve()
    if origin!=ORIGIN or type(email) is not str or not email.endswith('@example.invalid') or type(target_revision) is not bool:
        raise ValueError('canonical synthetic history fixture only')
    if owned_root.exists() or any(name in os.environ for name in _KEY_NAMES):raise RuntimeError('use fresh owned root before signing configuration')
    owned_root.mkdir(mode=0o700);state=owned_root/'state';cache=owned_root/'cache';logs=state/'logs'
    generated={name:secrets.token_urlsafe(48) for name in _KEY_NAMES}
    privacy=secrets.token_hex(32)
    while len(set(privacy))<12:privacy=secrets.token_hex(32)
    generated['STRUCTURAL_PRIVACY_HMAC_KEY']=privacy
    settings={**generated,'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':origin,'AUTH_DEV_MODE':'false','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1'}
    prior={name:os.environ.get(name) for name in settings if name not in _KEY_NAMES};bindings=[];completed=False
    try:
        os.environ.update(settings)
        for name in ('services.runtime_paths','web.backend.services.runtime_paths'):
            module=importlib.import_module(name)
            for key,value in (('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',logs)):
                bindings.append((module,key,getattr(module,key)));setattr(module,key,value)
        from web.backend.tests.method_v13_reference import reconstruct
        package,manifest=reconstruct(source_root,owned_root/'old13','native')
        env={key:os.environ[key] for key in ('PATH','PYTHONDONTWRITEBYTECODE') if key in os.environ}
        env.update(settings);env.update({'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(owned_root),
            'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
            'STRUCTURAL_D1_PUBLIC_GET_ENABLED':'false','STRUCTURAL_LOG_FILE':str(owned_root/'child-events.log'),
            'REVIEW_SOURCE_ROOT':str(package),'A006_AUDIT_ROOT':os.environ.get('A006_AUDIT_ROOT',str(owned_root)),
            'PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package)})
        guard=sys.modules.get('audit_bootstrap')
        if guard:env['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+env['PYTHONPATH']
        command=[sys.executable,str(Path(__file__).resolve()),'--seed-child',str(package),str(manifest),str(state),origin,email,'1' if target_revision else '0']
        child=subprocess.Popen(command,cwd=package,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            try:stdout,_stderr=child.communicate(timeout=35)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.communicate(timeout=2)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.communicate(timeout=2)
                raise RuntimeError('historical preparation outcome unknown; owned root retained') from None
            if child.returncode!=0:
                safe=[line for line in _stderr.decode(errors='replace').splitlines() if line.startswith('HISTORY_PREP_SAFE_ERROR:')]
                raise RuntimeError('historical preparation failed; owned root retained; '+(safe[-1] if safe else 'no safe child diagnostic'))
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
            for stream in (child.stdout,child.stderr):
                if stream is not None:stream.close()
        frames=[line[len(_FRAME):] for line in stdout.decode().splitlines() if line.startswith(_FRAME)]
        if len(frames)!=1:raise RuntimeError('historical preparation acknowledgement unknown; owned root retained')
        result=json.loads(frames[0]);cookie=result.pop('cookie');del frames,stdout,_stderr
        from research.method_draft import provision_method_drafts_v14
        inode=(state/'auth.sqlite3').stat();identity=(inode.st_dev,inode.st_ino)
        if provision_method_drafts_v14(state/'auth.sqlite3')['schema_version']!=14:raise RuntimeError('complete14 migration required')
        after=(state/'auth.sqlite3').stat()
        if (after.st_dev,after.st_ino)!=identity:raise RuntimeError('historical DB inode changed')
        from research.financial_input import provision_financial_inputs_v15
        expected={'schema_version':15,'financial_protocol':9,'financial_input_protocol':2,
            'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}
        receipt=provision_financial_inputs_v15(state/'auth.sqlite3')
        if receipt!=expected or provision_financial_inputs_v15(state/'auth.sqlite3')!=receipt:raise RuntimeError('complete15 migration and noop required')
        after=(state/'auth.sqlite3').stat()
        if (after.st_dev,after.st_ino)!=identity:raise RuntimeError('historical DB inode changed')
        schema=_read_current(state,result,cookie);cookie=None
        seed=PreparedSourceHistory(owned_root,state,cache,logs,result['research_id'],result['source_task_id'],email,origin,1,
            result['current_input_revision'],result['research_version'],tuple(result['excerpt_refs']),result['acquired_at'],'offline_probe',schema,
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            hashlib.sha256(json.dumps(result['loaded_old_modules'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),result['rows_digest'])
        # No raw source, cookie, signing key or financial record is yielded.
        yield seed;completed=True
    finally:
        for module,key,value in reversed(bindings):setattr(module,key,value)
        for name in settings:
            if name in _KEY_NAMES:os.environ.pop(name,None)
            elif prior[name] is None:os.environ.pop(name,None)
            else:os.environ[name]=prior[name]
        if completed:shutil.rmtree(owned_root)
        # Unknown preparation/body/shutdown outcomes deliberately retain root.


@dataclass(frozen=True,slots=True)
class PreparedSourceHistoryEight(PreparedSourceHistory):
    materials: tuple[dict,...]
    loopback_requests: int


def _eight_child(package,manifest,state,origin,email,target_revision):
    """Eight distinct actual old13 tasks in one Root; never public networking.

    Original _child/default AST and ARTICLE are unchanged. Only this fixed mode
    supplies complete synthetic credit and adds seven genuine HTTP approvals.
    Each task consumes its own original two-GET chain; total loopback GETs=16.
    """
    if target_revision:raise ValueError('fixed current revision1 required')
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch
    from web.backend.tests import source_http_fixture as fixture
    original=fixture.source_server
    credit=fixture.ARTICLE.replace(('Citation: '+fixture.TITLE).encode(),('Citation: Example A, Example B (2026) '+fixture.TITLE).encode())
    captured=io.StringIO()
    with patch.object(fixture,'source_server',partial(original,article=credit)),redirect_stdout(captured):
        _child(package,manifest,state,origin,email,False)
    frames=[line[len(_FRAME):] for line in captured.getvalue().splitlines() if line.startswith(_FRAME)]
    if len(frames)!=1:raise RuntimeError('fixed first source acknowledgement required')
    result=json.loads(frames[0]);captured.close();del frames
    from api import auth,research
    from research import ResearchStore,ResearchRunner
    from research.source_policy import PinnedPublicTransport
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    store=ResearchStore(auth._store());app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    rid=result['research_id'];base='/api/research/'+rid;materials=[];total=2
    def facts(tid):
        with store.transaction() as conn:
            payloads=[json.loads(row[0]) for row in conn.execute("SELECT payload FROM research_evidence_objects WHERE task_id=? AND kind='excerpts' ORDER BY id",(tid,))]
            snapshot=json.loads(conn.execute("SELECT payload FROM research_evidence_objects WHERE task_id=? AND kind='snapshots'",(tid,)).fetchone()[0])
            refs=[dict(excerpt_id=x['id'],source_revision=snapshot['source_revision'],content_digest=snapshot['extracted_digest'],start=x['start'],end=x['end']) for x in payloads]
            if len(refs)!=1 or conn.execute('SELECT used FROM research_source_chains WHERE id=(SELECT chain_id FROM research_source_runs WHERE task_id=?)',(tid,)).fetchone()[0]!=2:raise RuntimeError('actual two-GET task required')
            return dict(task_id=tid,acquired_at=snapshot['acquired_at'],excerpt_refs=refs,loopback_gets=2)
    materials.append(facts(result['source_task_id']))
    with TestClient(app,base_url=origin) as client:
        client.cookies.set('phase_session',result['cookie'])
        def post(path,data,key):
            response=client.post(path,json={'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':data},headers={'origin':origin,'idempotency-key':key})
            if response.status_code!=200:raise RuntimeError('fixed eight source HTTP refused')
            return response.json()['data']
        for number,word in enumerate(('alpha','beta','gamma','delta','epsilon','zeta','eta'),2):
            root=client.get(base)
            if root.status_code!=200:raise RuntimeError('same Root must remain readable')
            version=root.json()['data']['research_version'];query=dict(input_revision=1,expected_research_version=version,query='queue '+word)
            preview=post(base+'/source-preview',query,'eight-preview-'+word)
            approved=post(base+'/source-approvals',{**query,'confirm_external':True,'preview_digest':preview['preview_digest']},'eight-approve-'+word)
            tid=post(base+'/source-tasks',dict(input_revision=1,expected_research_version=version,approval_ref=approved['approval_ref']),'eight-start-'+word)['task']['id']
            with original(article=credit) as (port,calls):
                if ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(fixture.get_local,port))).run_once(tid)!='COMPLETED' or calls!=['/discovery','/article']:raise RuntimeError('fixed eight source task did not complete')
            total+=len(calls);materials.append(facts(tid))
    refs=[ref for material in materials for ref in material['excerpt_refs']]
    if len(refs)!=8 or len({ref['excerpt_id'] for ref in refs})!=8 or total!=16:raise RuntimeError('eight distinct real excerpts required')
    with store.transaction() as conn:
        control=conn.execute('SELECT current_revision,version FROM research_controls WHERE id=?',(rid,)).fetchone()
        if control[0]!=1 or conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]!=0:raise RuntimeError('no revision or funding mutation allowed')
        result.update(research_version=control[1],excerpt_refs=refs,materials=materials,loopback_requests=total,rows_digest=_rows_digest(conn))
    sys.stdout.write(_FRAME+json.dumps(result,separators=(',',':'))+'\n');sys.stdout.flush()


def _read_current_eight(state,result,cookie):
    first=result['materials'][0]
    schema=_read_current(state,{**result,'excerpt_refs':first['excerpt_refs'],'acquired_at':first['acquired_at']},cookie)
    from api import auth
    from services.auth_store import AuthStore
    from research import ResearchStore
    from research.authorization import AccountIdentity
    from research.source_integration import context_for,authorizer
    from research.evidence_repository import EvidenceRepository
    claims=auth._decode_jwt(cookie)
    if not claims:raise RuntimeError('actual synthetic session required')
    actor=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp']);store=ResearchStore(AuthStore(state/'auth.sqlite3'))
    refs=[]
    with store.transaction() as conn:
        repository=EvidenceRepository(conn,authorizer(store,identity=actor))
        for material in result['materials']:
            context=context_for(conn,material['task_id'])
            for ref in material['excerpt_refs']:
                details=repository.excerpt_details(context,ref['excerpt_id'])
                if details['input_revision']!=1 or any(details[key]!=ref[key] for key in ('source_revision','content_digest','start','end')):raise RuntimeError('actual eight historical ref changed')
                eligible,handle=repository.preview_provider_handle(context,ref['excerpt_id'],'e'+str(len(refs)+1))
                if eligible.acquired_at!=material['acquired_at'] or eligible.origin!='offline_probe' or not handle.attribution.startswith('Example A, Example B (2026) — '):raise RuntimeError('actual complete credit/time required')
                refs.append(ref['excerpt_id'])
        if len(refs)!=8 or len(set(refs))!=8 or result['loopback_requests']!=16:raise RuntimeError('fixed eight historical reader required')
    return schema

@contextmanager
def prepared_source_history_eight(source_root,owned_root,*,origin=ORIGIN,email='source-history@example.invalid',target_revision=False):
    """Yield safe refs after controlled13 -> reviewed offline14/15 -> real reader.

    Must precede parent signing configuration/Main startup. Synthetic keys stay
    only in parent/child memory and environment for this context; no caller keys
    are read/adopted. Configure any real-Main test SMTP sink separately inside.
    The default leaves revision1; the actual Main/UI creates revision2 later.
    Main must shut down before this context exits. Exceptions retain owned data.
    """
    source_root=Path(source_root).resolve();owned_root=Path(owned_root).resolve()
    if origin!=ORIGIN or type(email) is not str or not email.endswith('@example.invalid') or target_revision is not False:
        raise ValueError('canonical synthetic history fixture only')
    if owned_root.exists() or any(name in os.environ for name in _KEY_NAMES):raise RuntimeError('use fresh owned root before signing configuration')
    owned_root.mkdir(mode=0o700);state=owned_root/'state';cache=owned_root/'cache';logs=state/'logs'
    generated={name:secrets.token_urlsafe(48) for name in _KEY_NAMES}
    privacy=secrets.token_hex(32)
    while len(set(privacy))<12:privacy=secrets.token_hex(32)
    generated['STRUCTURAL_PRIVACY_HMAC_KEY']=privacy
    settings={**generated,'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':origin,'AUTH_DEV_MODE':'false','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1'}
    prior={name:os.environ.get(name) for name in settings if name not in _KEY_NAMES};bindings=[];completed=False
    try:
        os.environ.update(settings)
        for name in ('services.runtime_paths','web.backend.services.runtime_paths'):
            module=importlib.import_module(name)
            for key,value in (('STATE_ROOT',state),('CACHE_ROOT',cache),('LOG_ROOT',logs)):
                bindings.append((module,key,getattr(module,key)));setattr(module,key,value)
        from web.backend.tests.method_v13_reference import reconstruct
        package,manifest=reconstruct(source_root,owned_root/'old13','native')
        env={key:os.environ[key] for key in ('PATH','PYTHONDONTWRITEBYTECODE') if key in os.environ}
        env.update(settings);env.update({'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(owned_root),
            'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
            'STRUCTURAL_D1_PUBLIC_GET_ENABLED':'false','STRUCTURAL_LOG_FILE':str(owned_root/'child-events.log'),
            'REVIEW_SOURCE_ROOT':str(package),'A006_AUDIT_ROOT':os.environ.get('A006_AUDIT_ROOT',str(owned_root)),
            'PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package)})
        guard=sys.modules.get('audit_bootstrap')
        if guard:env['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+env['PYTHONPATH']
        command=[sys.executable,str(Path(__file__).resolve()),'--seed-eight-child',str(package),str(manifest),str(state),origin,email,'1' if target_revision else '0']
        child=subprocess.Popen(command,cwd=package,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        try:
            try:stdout,_stderr=child.communicate(timeout=240)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.communicate(timeout=2)
                except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.communicate(timeout=2)
                raise RuntimeError('historical preparation outcome unknown; owned root retained') from None
            if child.returncode!=0:
                safe=[line for line in _stderr.decode(errors='replace').splitlines() if line.startswith('HISTORY_PREP_SAFE_ERROR:')]
                raise RuntimeError('historical preparation failed; owned root retained; '+(safe[-1] if safe else 'no safe child diagnostic'))
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=2)
            for stream in (child.stdout,child.stderr):
                if stream is not None:stream.close()
        frames=[line[len(_FRAME):] for line in stdout.decode().splitlines() if line.startswith(_FRAME)]
        if len(frames)!=1:raise RuntimeError('historical preparation acknowledgement unknown; owned root retained')
        result=json.loads(frames[0]);cookie=result.pop('cookie');del frames,stdout,_stderr
        from research.method_draft import provision_method_drafts_v14
        inode=(state/'auth.sqlite3').stat();identity=(inode.st_dev,inode.st_ino)
        if provision_method_drafts_v14(state/'auth.sqlite3')['schema_version']!=14:raise RuntimeError('complete14 migration required')
        after=(state/'auth.sqlite3').stat()
        if (after.st_dev,after.st_ino)!=identity:raise RuntimeError('historical DB inode changed')
        from research.financial_input import provision_financial_inputs_v15
        expected={'schema_version':15,'financial_protocol':9,'financial_input_protocol':2,
            'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}
        receipt=provision_financial_inputs_v15(state/'auth.sqlite3')
        if receipt!=expected or provision_financial_inputs_v15(state/'auth.sqlite3')!=receipt:raise RuntimeError('complete15 migration and noop required')
        after=(state/'auth.sqlite3').stat()
        if (after.st_dev,after.st_ino)!=identity:raise RuntimeError('historical DB inode changed')
        schema=_read_current_eight(state,result,cookie);cookie=None
        seed=PreparedSourceHistory(owned_root,state,cache,logs,result['research_id'],result['source_task_id'],email,origin,1,
            result['current_input_revision'],result['research_version'],tuple(result['excerpt_refs']),result['acquired_at'],'offline_probe',schema,
            hashlib.sha256(manifest.read_bytes()).hexdigest(),
            hashlib.sha256(json.dumps(result['loaded_old_modules'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),result['rows_digest'])
        seed=PreparedSourceHistoryEight(**{field.name:getattr(seed,field.name) for field in __import__('dataclasses').fields(PreparedSourceHistory)},materials=tuple(result['materials']),loopback_requests=result['loopback_requests'])
        # No raw source, cookie, signing key or financial record is yielded.
        yield seed;completed=True
    finally:
        for module,key,value in reversed(bindings):setattr(module,key,value)
        for name in settings:
            if name in _KEY_NAMES:os.environ.pop(name,None)
            elif prior[name] is None:os.environ.pop(name,None)
            else:os.environ[name]=prior[name]
        if completed:shutil.rmtree(owned_root)



if __name__=='__main__' and len(sys.argv)>1 and sys.argv[1]=='--seed-eight-child':
    try:_eight_child(*sys.argv[2:7],sys.argv[7]=='1')
    except Exception as error:
        import traceback
        frames=[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)[-8:]]
        sys.stderr.write('HISTORY_PREP_SAFE_ERROR:'+json.dumps({'type':type(error).__name__,'frames':frames})+'\n');raise SystemExit(1)
    raise SystemExit(0)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--seed-child':
        try:_child(*sys.argv[2:7],sys.argv[7]=='1')
        except Exception as error:
            import traceback
            frames=[{'file':Path(frame.filename).name,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)[-8:]]
            sys.stderr.write('HISTORY_PREP_SAFE_ERROR:'+json.dumps({'type':type(error).__name__,'frames':frames})+'\n');raise SystemExit(1)
    elif len(sys.argv)==3 and sys.argv[1]=='--self-test':
        root=Path(__file__).resolve().parents[4];owned=Path(sys.argv[2])
        with prepared_source_history(root,owned) as seed:
            if seed.schema_version!=15 or seed.current_input_revision!=1 or not seed.excerpt_refs:raise RuntimeError('history preparation assertion failed')
            print(json.dumps({'schema_version':seed.schema_version,'source_input_revision':1,'current_input_revision':1,'mode':seed.mode,
                'excerpt_count':len(seed.excerpt_refs),'same_ref_time_permission':True,'no_financial_producer':True}))
        if owned.exists():raise RuntimeError('owned history root cleanup incomplete')
    else:raise SystemExit('test-only source history preparation helper')
