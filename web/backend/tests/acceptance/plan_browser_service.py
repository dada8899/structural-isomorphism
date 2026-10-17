#!/usr/bin/env python3
"""Explicit controlled-fixture HTTPS service, not Main or live activation.

Run with the release Python and --self-test or --serve. All app/provider sockets
bind loopback port zero. The app retains its canonical production Auth origin;
a browser driver must route that origin to the printed owned TLS port inside
its isolated browser context. No DNS, hosts file or production setting changes.
The Python controller and mail sink are in-process only, never HTTP endpoints.
"""
from __future__ import annotations
import argparse
from contextlib import AbstractContextManager
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
import os
from pathlib import Path
import secrets
import signal
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs,urlsplit

ROOT=Path(__file__).resolve().parents[4]
for source in (ROOT,ROOT/'web/backend'):
    if str(source) not in sys.path:sys.path.insert(0,str(source))
ORIGIN='https://beta.structural.bytedance.city'
OWNER='registered@example.invalid'
OBSERVATION='我发现团队的到达任务变得集中时，等待时间明显增加。'
CANDIDATE={'summary':'A controlled fixture plan from a self observation.','candidates':[{'label':'Queue variability','mechanism_hypothesis':'Variable arrivals may accumulate work.','why_considered':'The observation concerns waiting.','method_leads':['queueing model'],'key_unknowns':['Arrival variation is unknown.']}],'query_suggestions':[{'candidate_index':0,'query':'queue variability waiting','intent':'Choose a possible comparison later.'}],'gaps':['No literature or mathematics has been checked.'],'clarification_questions':[]}


def envelope(data,contract='b1-candidate-01'):
    return {'schema_version':'structure-research-v1','contract_revision':contract,'data':data}


def _certificates(root):
    """Ephemeral self-signed test identity; no real cert/credential is read."""
    tls=root/'tls';tls.mkdir(mode=0o700)
    key=tls/'private.key';certificate=tls/'certificate.pem';config=tls/'request.cnf'
    config.write_text('[req]\ndistinguished_name=subject\nx509_extensions=extensions\nprompt=no\n[subject]\nCN=beta.structural.bytedance.city\n[extensions]\nsubjectAltName=DNS:beta.structural.bytedance.city\nbasicConstraints=critical,CA:TRUE\n')
    config.chmod(0o600)
    subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(certificate),'-days','1','-config',str(config)],input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=8)
    key.chmod(0o600);certificate.chmod(0o600)
    return key,certificate


class _OwnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self,port,certificate):
        self.port=port
        self.context=ssl.create_default_context(cafile=str(certificate))
        super().__init__(context=self.context)
    def https_open(self,request):
        if urlsplit(request.full_url).netloc!='beta.structural.bytedance.city':raise PermissionError('fixture canonical origin only')
        port=self.port;context=self.context
        class Connection(http.client.HTTPSConnection):
            def connect(self):
                raw=socket.create_connection(('127.0.0.1',port),self.timeout)
                try:self.sock=context.wrap_socket(raw,server_hostname='beta.structural.bytedance.city')
                except BaseException:raw.close();raise
        return self.do_open(Connection,request,context=self.context)


class FixtureClient:
    """Real HTTPS and CookieJar, with a canonical URL and an owned TCP route."""
    def __init__(self,port,certificate):
        self.cookies=CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_OwnedHTTPSHandler(port,certificate),urllib.request.HTTPCookieProcessor(self.cookies))
    def request(self,method,path,data=None,*,key=None,origin=ORIGIN):
        if not path.startswith('/api/') or path.startswith('//'):raise ValueError('fixed app API only')
        headers={}
        if origin is not None:headers['Origin']=origin
        if key is not None:headers['Idempotency-Key']=key
        raw=None if data is None else json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
        if raw is not None:headers['Content-Type']='application/json'
        request=urllib.request.Request(ORIGIN+path,data=raw,method=method,headers=headers)
        try:response=self.opener.open(request,timeout=8)
        except urllib.error.HTTPError as error:response=error
        with response:
            body=response.read(524289)
            if len(body)>524288:raise ValueError('fixture app response exceeded public bound')
            return response.status,json.loads(body) if body else None
    def session(self):
        values=[item.value for item in self.cookies if item.name=='phase_session']
        if len(values)!=1:raise PermissionError('one actual registered session required')
        return values[0]


class PlanBrowserFixture(AbstractContextManager):
    """Same-process real registered controller, sealed resources and worker."""
    def __init__(self,*,approved_cap_units=41_000_000,risk_margin_units=1_000_000):
        self.approved_cap_units=approved_cap_units;self.risk_margin_units=risk_margin_units
        self.temp=None;self.root=None;self.provider=None;self.provider_thread=None;self.server=None;self.server_thread=None;self.app_socket=None
        self.worker=None;self.stop=threading.Event();self.mail=[];self.mail_lock=threading.Lock();self.calls=[];self.worker_failures=[]
        self.store=None;self.resource=None;self.identity=None;self.principal=None;self.client=None;self.installed=False;self.environment={};self.saved_globals=None
        self.cleanup_errors=();self._install_cleanup_errors=();self._failed_native=()
    def __enter__(self):
        try:self._start();return self
        except BaseException as primary:
            try:self.close()
            except BaseException as cleanup:primary.add_note('controlled fixture cleanup also failed: '+type(cleanup).__name__)
            raise
    def _start(self):
        # Explicit ownership: uncertain cleanup must not be silently erased by
        # TemporaryDirectory garbage collection. Only close removes this root.
        self.temp=Path(tempfile.mkdtemp(prefix='controlled-plan-browser-')).resolve();self.root=self.temp;self.root.chmod(0o700)
        if self.root.is_relative_to(ROOT):raise PermissionError('fixture private root must be outside the repository')
        from services import runtime_paths as paths
        from api import auth,research
        self.saved_globals=(paths.STATE_ROOT,paths.CACHE_ROOT,paths.LOG_ROOT,auth._send_email,auth._AUTH_STORES,research.enabled)
        paths.STATE_ROOT=self.root/'state';paths.CACHE_ROOT=self.root/'cache';paths.LOG_ROOT=paths.STATE_ROOT/'logs'
        secret=secrets.token_urlsafe(48)
        settings={'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(paths.STATE_ROOT),'STRUCTURAL_SSO_DATA_DIR':str(paths.STATE_ROOT),'STRUCTURAL_PRIVACY_HMAC_KEY':secrets.token_hex(32),
            'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':ORIGIN,'JWT_SECRET':secret,'STRUCTURAL_SSO_SECRET':secret,
            'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}
        self.environment={key:os.environ.get(key) for key in settings};os.environ.update(settings)
        from services.auth_registration import bootstrap_private_runtime
        if bootstrap_private_runtime()['research_schema']!=13:raise PermissionError('current reviewed Research13 required')
        auth._AUTH_STORES={};auth._send_email=self._mail;research.enabled=lambda:True
        from fastapi import FastAPI
        import uvicorn
        self.app=FastAPI(title='Controlled fixture only — no real model or funds')
        self.app.include_router(auth.router,prefix='/api');self.app.include_router(research.router,prefix='/api')
        key,certificate=_certificates(self.root);self.certificate=certificate
        self.app_socket=socket.socket(socket.AF_INET,socket.SOCK_STREAM);self.app_socket.bind(('127.0.0.1',0));self.app_socket.listen(64)
        self.port=self.app_socket.getsockname()[1]
        config=uvicorn.Config(self.app,host='127.0.0.1',port=self.port,ssl_keyfile=str(key),ssl_certfile=str(certificate),loop='asyncio',ws='none',log_config=None,log_level='critical',access_log=False,timeout_graceful_shutdown=3)
        self.server=uvicorn.Server(config)
        self.server_thread=threading.Thread(target=self.server.run,kwargs={'sockets':[self.app_socket]},name='controlled-plan-app')
        self.server_thread.start();deadline=time.monotonic()+5
        while not self.server.started:
            if not self.server_thread.is_alive() or time.monotonic()>=deadline:raise RuntimeError('fixture HTTPS app did not start')
            time.sleep(.02)
        self.client=FixtureClient(self.port,certificate)
        self._register()
    def _mail(self,_to,_subject,text):
        with self.mail_lock:self.mail.append(text)
    def take_latest_magic_token(self):
        """Privileged in-process browser harness only; never logs/HTTP output."""
        with self.mail_lock:
            if not self.mail:raise RuntimeError('fixture outbox is empty')
            text=self.mail.pop()
        return parse_qs(urlsplit(text.strip().split()[-1]).query)['token'][0]
    def _register(self):
        status,_=self.client.request('POST','/api/auth/request-link',{'email':OWNER})
        if status!=200:raise RuntimeError('actual fixture request-link failed')
        token=self.take_latest_magic_token()
        status,_=self.client.request('POST','/api/auth/verify',{'token':token})
        if status!=200:raise RuntimeError('actual fixture registration/verify failed')
        from api import auth
        from research import ResearchStore,ResearchService
        from research.authorization import AccountIdentity
        claims=auth._decode_jwt(self.client.session())
        if not claims or claims.get('sub')!=OWNER:raise PermissionError('actual registered fixture session required')
        self.identity=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])
        self.store=ResearchStore(auth._store());self.principal=ResearchService(self.store)._principal(self.identity,create=True)
    def install_controlled_funding(self):
        """Trusted controller method, deliberately not exposed through HTTP."""
        if self.stop.is_set():raise RuntimeError('fixture controller is closing')
        if self.installed:raise RuntimeError('fixture funding is already installed')
        if self._install_cleanup_errors:raise RuntimeError('prior installation cleanup uncertain; reentry rejected')
        if self.provider is not None and (self.provider.socket.fileno()!=-1 or self.provider_thread is not None and self.provider_thread.is_alive()):raise RuntimeError('prior provider is not retired')
        calls=self.calls
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,body):
                raw=json.dumps(body).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            def do_GET(self):
                if self.path!='/user/balance':self.send_error(404);return
                calls.append('GET');self.reply({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'59'}]})
            def do_POST(self):
                if self.path!='/chat/completions':self.send_error(404);return
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:self.send_error(413);return
                body=json.loads(self.rfile.read(length))
                if body.get('model')!='deepseek-flash' or body.get('max_tokens')!=4096 or 'tools' in body:self.send_error(422);return
                calls.append('POST');self.reply({'model':'deepseek-flash','usage':{'prompt_tokens':100,'completion_tokens':80,'total_tokens':180},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(CANDIDATE)}}]})
        from research import plan_native as native
        authority=provision=permit=resource=None
        try:
            # Retain each born object before the next operation can fail.
            self.provider=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.provider_thread=None
            self.provider_thread=threading.Thread(target=self.provider.serve_forever,name='controlled-plan-provider');self.provider_thread.start()
            authority=native.create_controlled_fixture_authority(self.store,self.identity,self.provider,approved_cap_units=self.approved_cap_units,risk_margin_units=self.risk_margin_units)
            provision=native.issue_native_provision(self.store,authority);permit=native.mint_runtime_permit(provision);resource=native.open_controlled_fixture_resource(permit)
            native.install_native_funding(self.store,provision,resource);self.resource=resource;self.installed=True
            self.worker=threading.Thread(target=self._work,name='controlled-plan-worker');self.worker.start()
        except BaseException as primary:
            errors=native.retire_attempts(resource,permit,provision,authority)
            errors+=self._close_provider()
            if errors:
                self._failed_native=tuple(value for value in (resource,permit,provision,authority) if value is not None)
                self._install_cleanup_errors=errors;self.cleanup_errors=errors
                primary.add_note('controlled installation cleanup uncertain: '+','.join(errors))
            raise
    def _close_provider(self):
        errors=[]
        def attempt(action):
            try:action()
            except BaseException as error:errors.append(type(error).__name__)
        if self.provider is not None:
            if self.provider_thread is not None and self.provider_thread.is_alive():attempt(self.provider.shutdown)
            attempt(self.provider.server_close)
            if self.provider_thread is not None and self.provider_thread.ident is not None:attempt(lambda:self.provider_thread.join(3))
            if self.provider.socket.fileno()!=-1:errors.append('provider_socket_open')
            if self.provider_thread is not None and self.provider_thread.is_alive():errors.append('provider_thread_alive')
        # Closed references remain inspectable; only a proven clean attempt
        # permits replacement. Uncertain resources are never overwritten.
        return tuple(errors)
    def _work(self):
        from research import ResearchRunner
        while not self.stop.wait(.05):
            try:
                # Only this registered fixture owner's native tasks; never C0,
                # Source, another principal, or arbitrary existing work.
                with self.store.transaction() as conn:
                    task=conn.execute("SELECT r.task_id FROM research_plan_native_runs r JOIN research_tasks t ON t.id=r.task_id WHERE r.state='approved' AND t.execution='QUEUED' AND t.policy_revision='native-plan-v1' AND t.principal_id=? ORDER BY t.created_at,t.id LIMIT 1",(self.principal,)).fetchone()
                if task and not self.stop.is_set():ResearchRunner(self.store).run_once(task[0])
            except BaseException as error:
                self.worker_failures.append(type(error).__name__);self.stop.set()
    def wait_result(self,rid,ref):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            status,body=self.client.request('GET','/api/research/'+rid+'/plan-results/'+ref)
            if status!=200:raise RuntimeError('actual fixture result read failed')
            if body['data']['state'] not in ('queued','generating'):return body
            if self.worker_failures:raise RuntimeError('fixture worker failed: '+','.join(self.worker_failures))
            time.sleep(.03)
        raise TimeoutError('bounded fixture worker result deadline')
    def close(self):
        errors=list(self._install_cleanup_errors);self.stop.set()
        def attempt(action):
            try:action()
            except BaseException as error:errors.append(type(error).__name__)
        def join(thread,seconds):
            if thread is not None and thread.ident is not None:thread.join(seconds)
        # Stop admission to the controller worker, preserve an already owned
        # response through its financial commit, then retire transport rights.
        attempt(lambda:join(self.worker,8))
        if self.installed:
            from research import plan_native
            attempt(lambda:plan_native.retire_installation(self.store))
            self.installed=False
        if self.worker is not None and self.worker.is_alive():attempt(lambda:join(self.worker,3))
        if self.server is not None:self.server.should_exit=True
        attempt(lambda:join(self.server_thread,5))
        if self.server_thread is not None and self.server_thread.is_alive():
            self.server.force_exit=True;attempt(lambda:join(self.server_thread,1))
        if self._failed_native:
            from research import plan_native
            errors.extend(plan_native.retire_attempts(*self._failed_native))
        errors.extend(self._close_provider())
        if self.app_socket is not None:attempt(self.app_socket.close)
        active=[t.name for t in (self.worker,self.server_thread,self.provider_thread) if t is not None and t.is_alive()]
        errors.extend(active)
        if not active:
            if self.saved_globals is not None:
                from services import runtime_paths as paths
                from api import auth,research
                paths.STATE_ROOT,paths.CACHE_ROOT,paths.LOG_ROOT,auth._send_email,auth._AUTH_STORES,research.enabled=self.saved_globals
                self.saved_globals=None
            for key,value in self.environment.items():
                if value is None:os.environ.pop(key,None)
                else:os.environ[key]=value
            self.environment={}
            with self.mail_lock:self.mail.clear()
            if self.temp is not None and not errors:
                try:shutil.rmtree(self.temp)
                except BaseException as error:errors.append(type(error).__name__)
                else:self.temp=None
        self.cleanup_errors=tuple(errors)
        if errors:raise RuntimeError('fixture cleanup uncertain: '+','.join(errors))
    def __exit__(self,exc_type,exc,tb):
        try:self.close()
        except BaseException as cleanup:
            if exc is None:raise
            exc.add_note('controlled fixture cleanup also failed: '+type(cleanup).__name__)
        return False


def self_test():
    with PlanBrowserFixture() as fixture:
        client=fixture.client
        problem={'entry':'phenomenon','original_input':OBSERVATION,'objective':'缩短合成等待时间','summary':'合成排队现象与等待时间的结构描述','variables':[],'constraints':['仅为受控演练'],'unknowns':['到达规律尚未确认'],'confirmed':True}
        status,saved=client.request('POST','/api/research',envelope({'problem':problem}),key='browser-create')
        assert status==200,(status,saved.get('error'));rid=saved['data']['research']['id']
        data={'input_revision':1,'expected_research_version':1,'observation_source':'own_observation','declaration_status':'self_declared'}
        status,closed=client.request('POST','/api/research/'+rid+'/plan-previews',envelope(data,'funded-plan-v2'),key='browser-closed')
        assert status==200 and closed['data']['can_confirm'] is False
        assert closed['data']['cash_evidence']=='not_observed' and fixture.calls==[]
        denied={k:closed['data'][k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};denied['confirm_outbound']=True
        status,rejected=client.request('POST','/api/research/'+rid+'/plan-approvals',envelope(denied,'funded-plan-v2'),key='browser-closed-confirm')
        assert status==503 and rejected['error']['code']=='FUNDING_CLOSED' and fixture.calls==[]
        assert client.request('POST','/api/research/'+rid+'/plan-previews',envelope(data,'funded-plan-v2'),key='foreign-origin',origin='https://foreign.example.invalid')[0]==403
        assert client.request('POST','/api/research/'+rid+'/funding-install',{})[0]==404
        fixture.install_controlled_funding()
        status,preview=client.request('POST','/api/research/'+rid+'/plan-previews',envelope(data,'funded-plan-v2'),key='browser-preview')
        assert status==200 and preview['data']['can_confirm'] is True
        preview=preview['data'];confirmation={k:preview[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};confirmation['confirm_outbound']=True
        status,confirmed=client.request('POST','/api/research/'+rid+'/plan-approvals',envelope(confirmation,'funded-plan-v2'),key='browser-confirm')
        assert status==200;ref=confirmed['data']['result_ref'];result=fixture.wait_result(rid,ref)
        assert result['data']['state']=='saved' and result['data']['content']['proposal']==CANDIDATE
        assert result['data']['content']['real_model_executed'] is False and result['data']['content']['automatically_created_sources']==0
        assert fixture.calls==['GET','POST']
        assert client.request('GET','/api/research/'+rid+'/plan-results/'+ref)[1]==result
        assert client.request('GET','/api/research/'+rid)[0]==200
        assert not fixture.worker_failures
        root=fixture.root;report={'scope':'controlled_fixture_only','schema':13,'financial':9,'actual_https':True,'canonical_origin_preserved':True,'same_process_worker':True,'provider_calls':fixture.calls.copy(),'saved_same_ref_time':True,'real_model_executed':False,'automatically_created_sources':0}
    assert not root.exists();report['cleanup']='closed'
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--self-test',action='store_true');mode.add_argument('--serve',action='store_true');args=parser.parse_args()
    if args.self_test:print(json.dumps(self_test(),sort_keys=True));return
    with PlanBrowserFixture() as fixture:
        fixture.install_controlled_funding()
        print(json.dumps({'scope':'controlled_fixture_only','canonical_origin':ORIGIN,'owned_tls_connect_host':'127.0.0.1','owned_tls_connect_port':fixture.port,'fixture_mail':'in_process_controller_only','real_model_executed':False}),flush=True)
        previous=signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGTERM,lambda *_:fixture.stop.set())
        try:
            try:
                while not fixture.stop.wait(.5):pass
            except KeyboardInterrupt:pass
            if fixture.worker_failures:raise RuntimeError('controlled fixture worker failed: '+','.join(fixture.worker_failures))
        finally:signal.signal(signal.SIGTERM,previous)

if __name__=='__main__':main()
