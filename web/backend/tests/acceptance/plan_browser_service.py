#!/usr/bin/env python3
"""Actual Main HTTPS with controlled model resources, never live activation.

Run with the release Python and --self-test or --serve. All app/provider sockets
bind loopback port zero. The app retains its canonical production Auth origin;
a browser driver must route that origin to the printed owned TLS port inside
its isolated browser context. No DNS, hosts file or production setting changes.
The Python controller and mail sink are in-process only, never HTTP endpoints.
"""
from __future__ import annotations
import argparse
import asyncio
from contextlib import AbstractContextManager,asynccontextmanager
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
import mimetypes
import os
import re
import stat
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
from typing import Literal

ROOT=Path(__file__).resolve().parents[4]
for source in (ROOT,ROOT/'web/backend'):
    if str(source) not in sys.path:sys.path.insert(0,str(source))
ORIGIN='https://beta.structural.bytedance.city'
HOST='beta.structural.bytedance.city'
BRIDGE_LIMIT=524288
BRIDGE_WALL=5.0
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
    def connection_type(self):
        port=self.port;context=self.context
        class Connection(http.client.HTTPSConnection):
            def connect(self):
                raw=socket.create_connection(('127.0.0.1',port),self.timeout)
                try:self.sock=context.wrap_socket(raw,server_hostname=HOST)
                except BaseException:raw.close();raise
        return Connection
    def connection(self,timeout):
        return self.connection_type()(HOST,timeout=timeout,context=self.context)
    def https_open(self,request):
        parsed=urlsplit(request.full_url)
        if parsed.scheme!='https' or parsed.netloc!=HOST:raise PermissionError('fixture canonical origin only')
        return self.do_open(self.connection_type(),request,context=self.context)


def _read_public_file(relative):
    """Read only the fixed repo frontend, with no symlink traversal or listing."""
    parts=relative.split('/')
    if not parts or any(not part or part in ('.','..') or part.startswith('.') or '\\' in part or '\x00' in part for part in parts):raise FileNotFoundError('unknown public file')
    descriptors=[]
    try:
        parent=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);descriptors.append(parent)
        for part in ('web','frontend',*parts[:-1]):
            parent=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent);descriptors.append(parent)
        fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent);descriptors.append(fd)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>BRIDGE_LIMIT:raise FileNotFoundError('unavailable public file')
        chunks=[];size=0
        while chunk:=os.read(fd,min(65536,BRIDGE_LIMIT+1-size)):
            chunks.append(chunk);size+=len(chunk)
            if size>BRIDGE_LIMIT:raise FileNotFoundError('public file exceeded bound')
        return b''.join(chunks)
    finally:
        for fd in reversed(descriptors):os.close(fd)


def _mount_public_pages(app):
    from fastapi import Request
    from fastapi.responses import Response
    async def public(request:Request):
        path=request.url.path
        fixed={'/research':'research.html','/auth/login':'auth-login.html','/auth/verify':'auth-verify.html'}
        relative=fixed.get(path)
        if re.fullmatch(r'/research/[a-zA-Z0-9_-]{1,100}',path):relative='research.html'
        if path.startswith('/assets/'):relative=path[1:]
        if relative is None:return Response(status_code=404)
        try:body=_read_public_file(relative)
        except (OSError,ValueError):return Response(status_code=404)
        kind=mimetypes.guess_type(relative)[0] or 'application/octet-stream'
        return Response(body if request.method!='HEAD' else b'',media_type=kind,headers={'Content-Length':str(len(body)),'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'})
    for path in ('/research','/research/{rid}','/auth/login','/auth/verify','/assets/{asset_path:path}'):
        app.add_route(path,public,methods=['GET','HEAD'])


class BridgeResponse:
    __slots__=('status','headers','body')
    def __init__(self,status,headers,body):self.status,self.headers,self.body=status,tuple(headers),body
    def __repr__(self):return '<BridgeResponse status='+str(self.status)+' body_bytes='+str(len(self.body))+'>'


class _BrowserResponseCapture:
    """Ephemeral evidence for one actual browser request and forwarded response."""
    def __init__(self,page,method,url,timeout):
        self.page,self.method,self.url,self.timeout=page,method,url,timeout
        self.request=self.request_body=self.request_headers=self.actual=None
        loop=asyncio.get_running_loop()
        self.future=loop.create_future()
        self.deadline=loop.time()+timeout
        self.ambiguous=self.expired=False
        self.timer=loop.call_later(timeout,self._expire)

    def __repr__(self):return '<owned browser response capture>'

    def bind(self,request,headers,body):
        if self.expired:return False
        if request.method!=self.method or request.url!=self.url or request.frame.page is not self.page:return False
        if self.request is not None:
            self.ambiguous=True
            return False
        self.request,self.request_headers,self.request_body=request,dict(headers),body
        return True

    async def json(self,response):
        if self.expired:raise TimeoutError('original browser response capture expired')
        await asyncio.wait_for(asyncio.shield(self.future),max(0,self.deadline-asyncio.get_running_loop().time()))
        if self.expired:raise TimeoutError('original browser response capture expired')
        if (self.ambiguous or self.actual is None or response.request is not self.request
                or response.request.method!=self.method or response.url!=self.url
                or response.request.post_data_buffer!=self.request_body
                or await response.request.all_headers()!=self.request_headers
                or response.status!=self.actual.status):
            raise AssertionError('original forwarded browser response identity differs')
        return json.loads(self.actual.body)

    def _expire(self):
        self.expired=True
        self.page=self.request=self.request_body=self.request_headers=self.actual=None
        if not self.future.done():self.future.set_result(None)

    def clear(self):
        self.timer.cancel()
        self.future.cancel()
        self.page=self.request=self.request_body=self.request_headers=self.actual=None


class CanonicalBrowserBridge(AbstractContextManager):
    """Trusted harness transport only; no CookieJar and no installed identity.

    forward preserves status/raw body/header pairs and never follows redirects.
    async with bridge.routed(context) owns temporary Playwright interception;
    the harness owns and closes its dedicated browser context (left offline on
    route exit). Secure-cookie behavior in
    that browser is separate evidence from this verified upstream TLS hop.
    """
    def __init__(self,service):
        self.service=service;self.handler=_OwnedHTTPSHandler(service.port,service.certificate)
        self.active=True;self.pending={};self.condition=threading.Condition()
        self._captures=[];self._routed_context=None
        info=os.fstat(service.app_socket.fileno());self.socket_identity=(info.st_dev,info.st_ino)

    @asynccontextmanager
    async def capture_response(self,page,method,url,*,timeout=10):
        """Retain only the original forwarded bytes, never repeat an HTTP call."""
        parsed=urlsplit(url)
        if (not self.active or page.context is not self._routed_context or method not in ('GET','HEAD','POST')
                or parsed.scheme!='https' or parsed.netloc!=HOST or parsed.fragment
                or not parsed.path.startswith('/') or len(url)>8192
                or type(timeout) not in (int,float) or not 0<timeout<=30):
            raise ValueError('active bounded canonical response capture required')
        if self._captures:
            raise RuntimeError('one response capture per bridge required')
        capture=_BrowserResponseCapture(page,method,url,timeout)
        self._captures.append(capture)
        try:yield capture
        finally:
            self._captures.remove(capture)
            capture.clear()
    def _shutdown(self,connection):
        sock=connection.sock
        if sock is not None:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
    def forward(self,method,url,headers,body=None):
        if type(url) is not str or len(url)>8192:raise ValueError('bounded canonical URL required')
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!=HOST or parsed.fragment or not parsed.path.startswith('/'):raise PermissionError('canonical fixture origin required')
        if method not in ('GET','HEAD','POST') or body is not None and type(body) is not bytes:raise ValueError('bounded browser method/body required')
        if body is not None and len(body)>BRIDGE_LIMIT:raise ValueError('browser request exceeds bound')
        pairs=list(headers.items()) if isinstance(headers,dict) else list(headers)
        if len(pairs)>64:raise ValueError('browser headers exceed bound')
        length=0;names=[]
        for name,value in pairs:
            if type(name) is not str or type(value) is not str or len(name)>128 or len(value)>8192 or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name) or '\r' in value or '\n' in value:raise ValueError('invalid browser header')
            length+=len(name)+len(value);names.append(name.lower())
            if name.lower()=='host' and value!=HOST:raise PermissionError('canonical Host required')
            if name.lower() in ('transfer-encoding','upgrade'):raise ValueError('browser tunneling unsupported')
            if name.lower()=='content-length' and value!=str(len(body or b'')):raise ValueError('browser Content-Length differs')
        if length>65536 or names.count('host')>1 or names.count('cookie')>1 or names.count('content-length')>1:raise ValueError('browser headers exceed bound')
        deadline=time.monotonic()+BRIDGE_WALL;connection=self.handler.connection(BRIDGE_WALL);response=None
        timer=threading.Timer(BRIDGE_WALL,self._shutdown,args=(connection,));timer.name='controlled-plan-bridge-deadline';timer.daemon=True
        with self.condition:
            if not self.active or self.service.stop.is_set() or not self.service.server_thread.is_alive():raise PermissionError('fixture bridge retired')
            info=os.fstat(self.service.app_socket.fileno())
            if (info.st_dev,info.st_ino)!=self.socket_identity or self.service.app_socket.getsockname()!=('127.0.0.1',self.handler.port):raise PermissionError('owned fixture TLS socket differs')
            self.pending[connection]=timer
        def remaining():
            value=deadline-time.monotonic()
            if value<=0:raise TimeoutError('browser fixture wall deadline')
            return value
        try:
            timer.start();connection.connect();connection.sock.settimeout(remaining())
            target=parsed.path+('?' +parsed.query if parsed.query else '')
            connection.putrequest(method,target,skip_host=True,skip_accept_encoding=True)
            for name,value in pairs:connection.putheader(name,value)
            if 'host' not in names:connection.putheader('Host',HOST)
            if body is not None and 'content-length' not in names:connection.putheader('Content-Length',str(len(body)))
            connection.endheaders(body);sock=connection.sock;sock.settimeout(remaining())
            response=connection.getresponse();result_headers=response.getheaders()
            if len(result_headers)>64 or sum(len(k)+len(v) for k,v in result_headers)>65536:raise ValueError('upstream headers exceed bound')
            chunks=[];size=0
            while True:
                sock.settimeout(remaining());chunk=response.read1(min(65536,BRIDGE_LIMIT+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
                if size>BRIDGE_LIMIT:raise ValueError('upstream body exceeds bound')
            return BridgeResponse(response.status,result_headers,b''.join(chunks))
        finally:
            primary=sys.exc_info()[1];errors=[]
            actions=[timer.cancel]
            if response is not None:actions.append(response.close)
            actions.append(connection.close)
            if timer.ident is not None:actions.append(lambda:timer.join(.5))
            for action in actions:
                try:action()
                except BaseException as error:errors.append(type(error).__name__)
            if timer.is_alive():errors.append('deadline_thread_alive')
            with self.condition:
                if not errors:self.pending.pop(connection,None)
                self.condition.notify_all()
            if errors:
                if primary is not None:primary.add_note('browser bridge cleanup uncertain: '+','.join(errors))
                else:raise RuntimeError('browser bridge cleanup uncertain: '+','.join(errors))
    @asynccontextmanager
    async def routed(self,context):
        if self._routed_context is not None:raise RuntimeError('one routed context per bridge required')
        async def handle(route,request):
            if not self.active:
                await route.abort('blockedbyclient');return
            try:
                request_headers=await request.all_headers();request_body=request.post_data_buffer
                captures=[item for item in self._captures if item.bind(request,request_headers,request_body)]
                result=await asyncio.to_thread(self.forward,request.method,request.url,request_headers,request_body)
                grouped={}
                for name,value in result.headers:grouped.setdefault(name.lower(),[]).append(value)
                headers={name:('\n' if name=='set-cookie' else ', ').join(values) for name,values in grouped.items()}
                await route.fulfill(status=result.status,body=result.body,headers=headers)
                for capture in captures:
                    if not capture.future.done():
                        capture.actual=result
                        capture.future.set_result(None)
            except (PermissionError,ValueError,OSError,TimeoutError):await route.abort('blockedbyclient')
        await context.route('**/*',handle)
        self._routed_context=context
        try:yield self
        finally:
            # A dedicated harness context is left offline before removing the
            # interception, so late page polls cannot escape to public DNS.
            # Its creator must still close that browser context in finally.
            primary=sys.exc_info()[1];errors=[];offline=False
            self._routed_context=None
            with self.condition:self.active=False
            try:
                await context.set_offline(True);offline=True
            except BaseException as error:errors.append(error)
            try:self.close()
            except BaseException as error:errors.append(error)
            # On an offline failure the retired handler remains installed and
            # aborts late requests until its creator closes the context.
            if offline:
                try:await context.unroute('**/*',handle)
                except BaseException as error:errors.append(error)
            if errors:
                first=primary if primary is not None else errors[0]
                for error in errors:
                    if error is not first:first.add_note('browser context cleanup failed: '+type(error).__name__)
                if primary is None:raise first
    def close(self):
        with self.condition:self.active=False;pending=list(self.pending)
        for connection in pending:self._shutdown(connection)
        deadline=time.monotonic()+BRIDGE_WALL
        with self.condition:
            while self.pending:
                left=deadline-time.monotonic()
                if left<=0:raise RuntimeError('browser bridge cleanup uncertain')
                self.condition.wait(left)
    def __exit__(self,*args):self.close()


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
    def __init__(self,*,approved_cap_units=41_000_000,risk_margin_units=1_000_000,transport:Literal['core','runtime']='core'):
        if type(transport) is not str or transport not in ('core','runtime'):raise ValueError('fixed controlled transport required')
        self.transport=transport
        self.approved_cap_units=approved_cap_units;self.risk_margin_units=risk_margin_units
        self.temp=None;self.root=None;self.provider=None;self.provider_thread=None;self.server=None;self.server_thread=None;self.app_socket=None
        self.worker=None;self.stop=threading.Event();self.mail=[];self.mail_lock=threading.Lock();self.calls=[];self.worker_failures=[]
        self.store=None;self.resource=None;self.identity=None;self.principal=None;self.client=None;self.installed=False;self.environment={};self.saved_globals=None
        self.cleanup_errors=();self._install_cleanup_errors=();self._failed_native=();self._browser_bridges=[];self._main_service=None
    def __enter__(self):
        try:self._start();return self
        except BaseException as primary:
            try:self.close()
            except BaseException as cleanup:primary.add_note('controlled fixture cleanup also failed: '+type(cleanup).__name__)
            raise
    def _start(self):
        # Keep the outer controller root until every owned resource is closed.
        # Dynamic import avoids the shared Main helper's fixed bridge imports.
        self.temp=Path(tempfile.mkdtemp(prefix='controlled-plan-browser-')).resolve();self.root=self.temp;self.root.chmod(0o700)
        if self.root.is_relative_to(ROOT):raise PermissionError('fixture private root must be outside the repository')
        from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService
        self._main_service=FormalMainBrowserService(self.root/'actual-main')
        self._main_service.__enter__()
        service=self._main_service
        self.app,self.server,self.server_thread=service.app,service.server,service.server_thread
        self.app_socket,self.port,self.certificate=service.app_socket,service.port,service.certificate
        # Independent real cookie jar: the historical Source owner is never
        # used as this controller's observation/funding identity.
        if service.seed.email==OWNER:raise PermissionError('independent controlled owner required')
        self.client=FixtureClient(self.port,self.certificate)
        self._register()
    def browser_bridge(self):
        bridge=CanonicalBrowserBridge(self);self._browser_bridges.append(bridge);return bridge
    def _mail(self,_to,_subject,text):
        with self.mail_lock:self.mail.append(text)
    def take_latest_magic_token(self):
        """Privileged in-process browser harness only; never logs/HTTP output."""
        if self._main_service is None:raise RuntimeError('actual Main mail sink unavailable')
        return self._main_service.take_latest_magic_token()
    def _register(self):
        status,_=self.client.request('POST','/api/auth/request-link',{'email':OWNER})
        if status!=200:raise RuntimeError('actual fixture request-link failed')
        token=self.take_latest_magic_token()
        try:status,_=self.client.request('POST','/api/auth/verify',{'token':token})
        finally:token=None
        if status!=200:raise RuntimeError('actual fixture registration/verify failed')
        from api import auth
        from research import ResearchStore,ResearchService
        from research.authorization import AccountIdentity
        claims=auth._decode_jwt(self.client.session())
        if not claims or claims.get('sub')!=OWNER:raise PermissionError('actual registered fixture session required')
        self.identity=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])
        self.store=ResearchStore(auth._store())
        with self.store.transaction() as conn:ResearchStore._check_v15(conn)
        self.principal=ResearchService(self.store)._principal(self.identity,create=True)
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
            # A fixed trusted-controller choice only. Both implementations
            # remain controlled_fixture; absent/mismatched Runtime never falls
            # back to Core or changes native_live/funding authority.
            issuer=native.create_controlled_runtime_fixture_authority if self.transport=='runtime' else native.create_controlled_fixture_authority
            opener=native.open_plan_resource if self.transport=='runtime' else native.open_controlled_fixture_resource
            authority=issuer(self.store,self.identity,self.provider,approved_cap_units=self.approved_cap_units,risk_margin_units=self.risk_margin_units)
            provision=native.issue_native_provision(self.store,authority);permit=native.mint_runtime_permit(provision);resource=opener(permit)
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
            # Consumed is conservatively pending_reconciliation while the
            # same worker still owns its response; poll only this original ref
            # until its cleanup audit is committed. Never rerun the worker.
            if body['data']['state'] not in ('queued','generating') and body['data']['cleanup_state']!='pending':return body
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
        for bridge in self._browser_bridges:attempt(bridge.close)
        attempt(lambda:join(self.worker,8))
        if self.installed:
            from research import plan_native
            attempt(lambda:plan_native.retire_installation(self.store))
            self.installed=False
        if self.worker is not None and self.worker.is_alive():attempt(lambda:join(self.worker,3))
        if self.worker is not None and self.worker.is_alive():
            errors.append(self.worker.name)
        if self._failed_native:
            from research import plan_native
            errors.extend(plan_native.retire_attempts(*self._failed_native))
        errors.extend(self._close_provider())
        # Shared Main owns its TLS/SMTP/Source lifespan and original deadline.
        # Preserve its private root when controller cleanup was uncertain.
        if self._main_service is not None:
            primary=RuntimeError('controlled fixture cleanup uncertain') if errors else None
            attempt(lambda:self._main_service._close(primary))
        active=[t.name for t in (self.worker,self.server_thread,self.provider_thread) if t is not None and t.is_alive()]
        errors.extend(active)
        if not active:
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
        root=fixture.root;report={'scope':'controlled_fixture_only','schema':15,'financial':9,'actual_https':True,'canonical_origin_preserved':True,'same_process_worker':True,'provider_calls':fixture.calls.copy(),'saved_same_ref_time':True,'real_model_executed':False,'automatically_created_sources':0}
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
