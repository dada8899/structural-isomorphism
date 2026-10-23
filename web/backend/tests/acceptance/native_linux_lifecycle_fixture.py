"""Explicit disposable-VM fixture. Import performs no system or app operation.

Stock entry is separate. The observer executes the unchanged physical entry
through stdlib runpy; it observes fixed source frames, never installs authority.
"""
import base64
import hashlib
import http.client
import http.cookiejar
import http.server
import json
import math
import os
from pathlib import Path
import re
import runpy
import select
import socket
import socketserver
import sqlite3
import ssl
import sys
import threading
import time
import types
import urllib.request
from urllib.parse import parse_qs, urlsplit
import weakref

ORIGIN='https://beta.structural.bytedance.city'
HOST='beta.structural.bytedance.city'
SMTP_PORT=18025
HTTPS_PORT=18443
WORK=Path('/run/structural-native-probe')
STATE=Path('/var/lib/structural-isomorphism')
ROOT=Path(__file__).resolve().parents[4]
EVENTS=('SLOT_BEFORE_GET','SLOT_WOKEN','PROOF_TAKEN','SOURCE_JOIN','NATIVE_JOIN','FINAL','OBSERVER_FAILED','NETWORK_ENTRY')
SUMMARY_KEYS=('source_closed','native_closed','proof_taken','component_woken','component_ms','same_deadline_ref','within_main_deadline','main_stop_to_closed_ms','connections_born','connections_creator_closed','connections_property_closed','fds_born','fds_creator_closed','fds_property_closed','observer_failed')


class FixtureFailure(RuntimeError):pass


def strict_json(raw,limit=65536):
    if type(raw) is not bytes or not 0<len(raw)<=limit:raise FixtureFailure('WIRE')
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise FixtureFailure('DUPLICATE')
            out[k]=v
        return out
    def invalid(_):raise FixtureFailure('NUMBER')
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)
    stack=[(value,0)];nodes=0
    while stack:
        item,depth=stack.pop();nodes+=1
        if depth>16 or nodes>4096:raise FixtureFailure('DEPTH')
        if type(item) is float and not math.isfinite(item):raise FixtureFailure('NUMBER')
        if type(item) is dict:stack.extend((v,depth+1) for v in item.values())
        elif type(item) is list:stack.extend((v,depth+1) for v in item)
    return value


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def remaining(deadline,ceiling=5):
    if type(deadline) not in (int,float) or not math.isfinite(deadline):raise FixtureFailure('CLOCK')
    value=min(ceiling,deadline-time.monotonic())
    if value<=0:raise FixtureFailure('CLOCK')
    return value


def validate_summary(value):
    if type(value) is not dict or set(value)!=set(SUMMARY_KEYS):raise FixtureFailure('SHAPE')
    for k,v in value.items():
        if k in ('source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline','observer_failed'):
            if v is not None and type(v) is not bool:raise FixtureFailure('SHAPE')
        elif v is not None and (type(v) is not int or not 0<=v<=1000000):raise FixtureFailure('SHAPE')
    for prefix in ('connections','fds'):
        born,creator,closed=(value[prefix+suffix] for suffix in ('_born','_creator_closed','_property_closed'))
        if all(v is not None for v in (born,creator,closed)) and not 0<=creator<=closed<=born:raise FixtureFailure('SHAPE')
    return value


def validate_event(event,values):
    if event not in EVENTS or type(values) is not dict:raise FixtureFailure('EVENT')
    fields={'SLOT_BEFORE_GET':set(),'SLOT_WOKEN':{'elapsed_ms'},'PROOF_TAKEN':set(),'SOURCE_JOIN':{'closed'},'NATIVE_JOIN':{'closed'},'FINAL':set(SUMMARY_KEYS),'OBSERVER_FAILED':set(),'NETWORK_ENTRY':set()}
    if set(values)!=fields[event]:raise FixtureFailure('EVENT')
    if any(type(v) not in (bool,int,type(None)) for v in values.values()):raise FixtureFailure('EVENT')
    if event=='FINAL':validate_summary(values)
    if event in ('SOURCE_JOIN','NATIVE_JOIN') and type(values['closed']) is not bool:raise FixtureFailure('EVENT')
    if event=='SLOT_WOKEN' and (type(values['elapsed_ms']) is not int or not 0<=values['elapsed_ms']<=300000):raise FixtureFailure('EVENT')


def emit_event(event,values):
    validate_event(event,values)
    raw=canonical({'event':event,'values':values})+b'\n'
    if len(raw)>2048:raise FixtureFailure('EVENT')
    fd=os.open(WORK/'observed.jsonl',os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    try:
        info=os.fstat(fd)
        if info.st_uid!=os.geteuid() or info.st_mode&0o777!=0o600 or info.st_nlink!=1 or info.st_size>16384:raise FixtureFailure('EVENT')
        if os.write(fd,raw)!=len(raw):raise FixtureFailure('EVENT')
    finally:os.close(fd)


def absolute_remaining(deadline,ceiling=5):
    if type(deadline) not in (int,float) or not math.isfinite(deadline):raise FixtureFailure('CLOCK')
    left=min(ceiling,deadline-time.monotonic())
    if left<=0:raise FixtureFailure('CLOCK')
    return left


class _DeadlineFile:
    def __init__(self,connection):self.connection=connection;self.closed=False;self.native_file=connection.raw.makefile('rb',buffering=0)
    def read(self,size=-1):
        if self.closed:raise OSError('closed response reader')
        if type(size) is not int or size<0 or size>524289:raise FixtureFailure('HTTP')
        out=bytearray()
        while len(out)<size:
            raw=self.connection.recv(min(4096,size-len(out)))
            if not raw:break
            out.extend(raw)
        return bytes(out)
    def readline(self,size=-1):
        if self.closed:raise OSError('closed header reader')
        limit=65537 if size<0 else min(size,65537);out=bytearray()
        while len(out)<limit:
            raw=self.connection.recv(1)
            if not raw:break
            out.extend(raw)
            if raw==b'\n':break
        return bytes(out)
    def close(self):
        if not self.closed:
            self.native_file.close();self.closed=True


class _DeadlineSocket:
    """Each actual IO operation is clipped to one unchanged absolute end."""
    def __init__(self,raw,deadline,ceiling):self.raw,self.deadline,self.ceiling=raw,deadline,ceiling
    def recv(self,size):
        self.raw.settimeout(absolute_remaining(self.deadline,self.ceiling));result=self.raw.recv(size);absolute_remaining(self.deadline,self.ceiling);return result
    def sendall(self,raw):
        self.raw.settimeout(absolute_remaining(self.deadline,self.ceiling));result=self.raw.sendall(raw);absolute_remaining(self.deadline,self.ceiling);return result
    def settimeout(self,value):self.ceiling=min(self.ceiling,value);self.raw.settimeout(absolute_remaining(self.deadline,self.ceiling))
    def setsockopt(self,*args):return self.raw.setsockopt(*args)
    def makefile(self,*args,**kwargs):return _DeadlineFile(self)
    def close(self):return self.raw.close()
    def fileno(self):return self.raw.fileno()


def write_startup_bytes(raw,deadline):
    if type(raw) is not bytes or not 0<len(raw)<=1024:raise FixtureFailure('FRAME')
    fd=sys.stdout.fileno();os.set_blocking(fd,False);offset=0
    while offset<len(raw):
        if not select.select([],[fd],[],absolute_remaining(deadline))[1]:raise FixtureFailure('CLOCK')
        try:sent=os.write(fd,raw[offset:])
        except BlockingIOError:continue
        if sent<=0:raise FixtureFailure('FRAME')
        offset+=sent


class StartupWriter:
    def __init__(self,deadline):self.deadline=deadline;self.state=StartupFrames()
    def emit(self,stage,health=None,error=None):
        failed_at=exception=number=None
        if stage=='FAILED':
            failed_at=self.state.last
            exception='TLS_ERROR' if isinstance(error,ssl.SSLError) else 'DEADLINE' if isinstance(error,FixtureFailure) and error.args==('CLOCK',) else 'OS_ERROR' if isinstance(error,OSError) else 'VALUE_ERROR' if isinstance(error,ValueError) else 'OTHER'
            if isinstance(error,OSError) and type(error.errno) is int and 0<=error.errno<=4095:number=error.errno
        value={'protocol':'native-helper-startup-v1','seq':self.state.count,'stage':stage,'failed_at':failed_at,'exception':exception,'errno':number,'health':empty_health() if health is None else health}
        self.state.accept(value);raw=canonical(value)+b'\n'
        if len(raw)>1024 or self.state.total+len(raw)>8192:raise FixtureFailure('FRAME')
        self.state.total+=len(raw);write_startup_bytes(raw,self.deadline)



class _SMTP(socketserver.StreamRequestHandler):
    def setup(self):
        self.request=_DeadlineSocket(self.request,self.server.io_deadline,2)
        super().setup()
    def handle(self):
        self.request.settimeout(2);authenticated=False;recipients=[];pending=None
        def send(raw):self.wfile.write(raw);self.wfile.flush()
        def line():
            raw=self.rfile.readline(8193)
            if len(raw)>8192:raise FixtureFailure('SMTP')
            return raw
        send(b'220 owned.invalid SMTP\r\n')
        while True:
            raw=line()
            if not raw:return
            if pending=='plain':payload=raw.strip();pending=None;verb=b'AUTH-PAYLOAD'
            else:
                verb=raw.split(None,1)[0].upper();payload=None
            if verb in (b'EHLO',b'HELO'):send(b'250-owned.invalid\r\n250-AUTH PLAIN\r\n250 SIZE 65536\r\n')
            elif verb==b'AUTH':
                parts=raw.split()
                if len(parts)<2 or parts[1].upper()!=b'PLAIN':send(b'504 unsupported\r\n');continue
                if len(parts)==2:pending='plain';send(b'334 \r\n');continue
                payload=parts[2];verb=b'AUTH-PAYLOAD'
            if verb==b'AUTH-PAYLOAD':
                decoded=base64.b64decode(payload,validate=True).split(b'\0')
                authenticated=(len(decoded)==3 and decoded[1]==b'native-probe' and decoded[2]==self.server.password)
                send(b'235 authenticated\r\n' if authenticated else b'535 denied\r\n')
            elif verb==b'MAIL':send(b'250 ok\r\n' if authenticated else b'530 authentication required\r\n')
            elif verb==b'RCPT':
                address=raw.partition(b':')[2].strip().strip(b'<>')
                if authenticated and re.fullmatch(rb'[a-z0-9._+-]+@example\.invalid',address):recipients.append(address);send(b'250 ok\r\n')
                else:send(b'553 synthetic recipients only\r\n')
            elif verb==b'DATA' and authenticated and recipients:
                send(b'354 data\r\n');body=bytearray()
                while True:
                    part=line()
                    if part==b'.\r\n':break
                    if not part or len(body)+len(part)>65536:raise FixtureFailure('SMTP')
                    body.extend(part[1:] if part.startswith(b'..') else part)
                # Retain only bounded synthetic verification tokens in memory.
                from email import policy
                from email.parser import BytesParser
                message=BytesParser(policy=policy.default).parsebytes(bytes(body))
                plain=message.get_body(preferencelist=('plain',))
                if plain is not None:
                    for found in re.findall(r'https://[^\s<>]+',plain.get_content()):
                        target=urlsplit(found);token=parse_qs(target.query).get('token',[])
                        if target.hostname==HOST and target.path=='/auth/verify' and len(token)==1:
                            with self.server.lock:self.server.tokens.append(token[0])
                recipients.clear();send(b'250 stored\r\n')
            elif verb==b'QUIT':send(b'221 bye\r\n');return
            elif verb in (b'RSET',b'NOOP'):recipients.clear();send(b'250 ok\r\n')


class _NumericHTTP(http.client.HTTPConnection):
    def connect(self):
        raw=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            raw.settimeout(absolute_remaining(self.absolute_deadline,self.timeout));raw.connect(('127.0.0.1',5004))
            self.sock=_DeadlineSocket(raw,self.absolute_deadline,self.timeout)
        except BaseException:raw.close();raise


class _Workers:
    def process_request(self,request,address):
        thread=threading.Thread(target=self.process_request_thread,args=(request,address),daemon=self.daemon_threads)
        with self.worker_lock:
            if len(self.workers)>=512:raise FixtureFailure('CLEANUP')
            self.workers.add(thread)
        try:thread.start()
        except BaseException:
            self.worker_uncertain=True
            try:self.shutdown_request(request)
            except BaseException:pass
            raise
    def process_request_thread(self,request,address):
        return super().process_request_thread(request,address)


class _OwnedTCP(_Workers,socketserver.ThreadingTCPServer):pass


class _OwnedHTTP(_Workers,http.server.ThreadingHTTPServer):
    def get_request(self):
        if getattr(self,'worker_uncertain',False):raise FixtureFailure('CLEANUP')
        sock,address=self.socket.accept()
        try:
            sock.settimeout(absolute_remaining(self.io_deadline,2))
            return self.tls.wrap_socket(sock,server_side=True),address
        except BaseException:
            try:sock.close()
            except BaseException:
                # One retained object: uncertainty stops this accept loop and
                # remains sticky even if physical retirement happened first.
                self.worker_uncertain=True;self._unretired_accepted=sock
                self._BaseServer__shutdown_request=True
            raise


class _Bridge(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def setup(self):
        self.request=_DeadlineSocket(self.request,self.server.io_deadline,2)
        super().setup()
    def log_message(self,*args):pass
    def do_GET(self):self._forward()
    def do_POST(self):self._forward()
    def _forward(self):
        if not self.path.startswith(('/api/auth/','/api/research','/api/health')) or '?' in self.path:raise FixtureFailure('PATH')
        length=int(self.headers.get('Content-Length','0'))
        if not 0<=length<=65536:raise FixtureFailure('HTTP')
        body=self.rfile.read(length)
        conn=_NumericHTTP('127.0.0.1',5004,timeout=2);conn.absolute_deadline=self.server.io_deadline;response=None
        try:
            headers={k:self.headers[k] for k in ('Content-Type','Cookie','Origin','Idempotency-Key') if k in self.headers}
            headers.update(Host=HOST,Connection='close',**{'X-Forwarded-Proto':'https','X-Forwarded-For':'127.0.0.1'})
            conn.request(self.command,self.path,body if length else None,headers)
            response=conn.getresponse();raw=response.read(524289)
            if len(raw)>524288:raise FixtureFailure('HTTP')
            self.send_response(response.status)
            for key,value in response.getheaders():
                if key.lower() in ('content-type','set-cookie','cache-control'):self.send_header(key,value)
            self.send_header('Content-Length',str(len(raw)));self.send_header('Connection','close');self.end_headers();self.wfile.write(raw)
        finally:
            try:
                if response is not None:response.close()
            finally:conn.close()


class _HTTPS(http.client.HTTPSConnection):
    def __init__(self,*args,absolute_deadline,**kwargs):
        self.absolute_deadline=absolute_deadline;super().__init__(*args,**kwargs)
    def connect(self):
        raw=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:
            raw.settimeout(absolute_remaining(self.absolute_deadline,self.timeout));raw.connect(('127.0.0.1',HTTPS_PORT))
            raw.settimeout(absolute_remaining(self.absolute_deadline,self.timeout));wrapped=self._context.wrap_socket(raw,server_hostname=HOST)
            self.sock=_DeadlineSocket(wrapped,self.absolute_deadline,self.timeout)
        except BaseException:raw.close();raise


class _Handler(urllib.request.HTTPSHandler):
    def __init__(self,*,context,deadline):super().__init__(context=context);self.deadline=deadline
    def https_open(self,request):
        if urlsplit(request.full_url).netloc!=HOST:raise FixtureFailure('HOST')
        return self.do_open(_HTTPS,request,context=self._context,check_hostname=True,absolute_deadline=self.deadline)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise FixtureFailure('HOST')


STARTUP_STAGES=('CONFIG','SMTP_BIND','TLS_BIND','TLS_CERT','SERVERS_START','HEALTH_WAIT','READY','FAILED')
HEALTH_VALUES=('READY','UNAVAILABLE','ABSENT','OTHER')
HEALTH_TRANSPORTS=('OK','CONNECT','TLS','TIMEOUT','HTTP_ERROR','JSON','SHAPE','OTHER')
STARTUP_EXCEPTIONS=('OS_ERROR','TLS_ERROR','DEADLINE','VALUE_ERROR','OTHER')


def empty_health():return {'http_status':None,'base':None,'source_execute':None,'transport':None}


def validate_health(value):
    if type(value) is not dict or set(value)!=set(empty_health()):raise ValueError('FRAME_INVALID')
    status=value['http_status']
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('FRAME_INVALID')
    for key in ('base','source_execute'):
        if value[key] is not None and (type(value[key]) is not str or value[key] not in HEALTH_VALUES):raise ValueError('FRAME_INVALID')
    if value['transport'] is not None and (type(value['transport']) is not str or value['transport'] not in HEALTH_TRANSPORTS):raise ValueError('FRAME_INVALID')
    return value


def health_projection(status,body,transport):
    value=empty_health()
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('FRAME_INVALID')
    if transport not in HEALTH_TRANSPORTS:raise ValueError('FRAME_INVALID')
    value.update(http_status=status,transport=transport)
    if body is None:return value
    if type(body) is not dict:return dict(value,transport='SHAPE')
    checks=body.get('checks',{})
    if type(checks) is not dict:return dict(value,transport='SHAPE')
    for key in ('base','source_execute'):
        observed=checks.get(key)
        value[key]='ABSENT' if key not in checks else 'READY' if observed=='ready' else 'UNAVAILABLE' if observed=='unavailable' else 'OTHER'
    return value


def health_ready(value):
    validate_health(value)
    return value['http_status']==200 and value['base']=='READY' and value['source_execute']=='READY' and value['transport']=='OK'


def ready_budget(now,controller_deadline):
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (now,controller_deadline)):raise ValueError('DEADLINE')
    end=min(now+10,controller_deadline-30)
    if end<=now:raise ValueError('DEADLINE')
    return end,end-3


def validate_startup_frame(value):
    fields={'protocol','seq','stage','failed_at','exception','errno','health'}
    if type(value) is not dict or set(value)!=fields or value['protocol']!='native-helper-startup-v1':raise ValueError('FRAME_INVALID')
    if type(value['seq']) is not int or not 0<=value['seq']<8 or value['stage'] not in STARTUP_STAGES:raise ValueError('FRAME_INVALID')
    validate_health(value['health'])
    if value['stage']=='FAILED':
        if value['failed_at'] not in STARTUP_STAGES[:-2] or value['exception'] not in STARTUP_EXCEPTIONS:raise ValueError('FRAME_INVALID')
        if value['errno'] is not None and (type(value['errno']) is not int or not 0<=value['errno']<=4095):raise ValueError('FRAME_INVALID')
    elif any(value[k] is not None for k in ('failed_at','exception','errno')):raise ValueError('FRAME_INVALID')
    if value['stage']=='READY' and not health_ready(value['health']):raise ValueError('FRAME_INVALID')
    if value['stage'] not in ('READY','FAILED','HEALTH_WAIT') and value['health']!=empty_health():raise ValueError('FRAME_INVALID')
    return value


class StartupFrames:
    """Finite data-only protocol state, never a service or capability."""
    def __init__(self):self.count=0;self.total=0;self.pending=bytearray();self.last=None;self.terminal=None;self.health=empty_health();self.failed_at=None;self.exception=None;self.errno=None
    def accept(self,value):
        validate_startup_frame(value)
        if self.terminal is not None or value['seq']!=self.count:raise ValueError('FRAME_INVALID')
        stage=value['stage']
        if stage=='FAILED':
            if self.last is None or value['failed_at']!=self.last:raise ValueError('FRAME_INVALID')
        elif stage=='READY':
            if self.last!='HEALTH_WAIT':raise ValueError('FRAME_INVALID')
        elif stage!=STARTUP_STAGES[self.count]:raise ValueError('FRAME_INVALID')
        self.count+=1
        if self.count>8:raise ValueError('FRAME_LIMIT')
        self.last=stage;self.health=dict(value['health']);self.failed_at=value['failed_at'];self.exception=value['exception'];self.errno=value['errno']
        if stage in ('READY','FAILED'):self.terminal=stage
    def feed(self,raw):
        if type(raw) is not bytes or not raw:raise ValueError('FRAME_INVALID')
        self.total+=len(raw)
        if self.total>8192:raise ValueError('FRAME_LIMIT')
        for byte in raw:
            if self.terminal is not None:raise ValueError('FRAME_INVALID')
            self.pending.append(byte)
            if len(self.pending)>1024 or len(self.pending)==1024 and byte!=10:
                self.pending.clear();raise ValueError('FRAME_LIMIT')
            if byte==10:
                line=bytes(self.pending[:-1]);self.pending.clear()
                self.accept(strict_json(line,1023))
    def finish(self):
        if self.pending or self.terminal is None:raise ValueError('EOF')



class LocalService:
    def __init__(self,password,deadline,ready_deadline):
        self.password,self.deadline,self.ready_deadline=password,deadline,ready_deadline;self.work_deadline=ready_deadline-3
        self.servers=[];self.threads=[];self.startup=StartupWriter(ready_deadline);self.health=empty_health();self.ready=False
    def start(self):
        self.startup.emit('CONFIG');absolute_remaining(self.work_deadline)
        self.startup.emit('SMTP_BIND')
        smtp=_OwnedTCP(('127.0.0.1',SMTP_PORT),_SMTP);self.servers.append(smtp);smtp.daemon_threads=True;smtp.block_on_close=False;smtp.io_deadline=self.work_deadline
        smtp.worker_lock=threading.Lock();smtp.workers=set();smtp.worker_uncertain=False
        smtp.password=self.password.encode();smtp.tokens=[];smtp.lock=threading.Lock();self.smtp=smtp
        absolute_remaining(self.work_deadline);self.startup.emit('TLS_BIND')
        web=_OwnedHTTP(('127.0.0.1',HTTPS_PORT),_Bridge);self.servers.append(web);web.daemon_threads=True;web.block_on_close=False;web.io_deadline=self.work_deadline
        web.worker_lock=threading.Lock();web.workers=set();web.worker_uncertain=False
        absolute_remaining(self.work_deadline);self.startup.emit('TLS_CERT')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(WORK/'local-cert.pem',WORK/'local-key.pem')
        absolute_remaining(self.work_deadline);web.tls=context
        verify=ssl.create_default_context(cafile=str(WORK/'local-cert.pem'));absolute_remaining(self.work_deadline)
        self.handler=_Handler(context=verify,deadline=self.work_deadline)
        self.client=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect(),self.handler,urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.startup.emit('SERVERS_START')
        for server in self.servers:
            absolute_remaining(self.work_deadline)
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=False);self.threads.append(thread);thread.start()
        self.startup.emit('HEALTH_WAIT')
        while True:
            absolute_remaining(self.work_deadline)
            self.health=self._health_request(self.work_deadline)
            absolute_remaining(self.work_deadline)
            if health_ready(self.health):break
            time.sleep(min(.05,absolute_remaining(self.work_deadline,.05)))
        for server in self.servers:server.io_deadline=self.deadline
        self.handler.deadline=self.deadline;self.startup.emit('READY',self.health);self.ready=True
    def _health_request(self,deadline):
        response=None;status=None
        try:
            request=urllib.request.Request(ORIGIN+'/api/health',headers={'Origin':ORIGIN},method='GET')
            try:response=self.client.open(request,timeout=absolute_remaining(deadline))
            except urllib.error.HTTPError as error:response=error
            status=response.status
            transport='OK' if status==200 else 'HTTP_ERROR'
            chunks=bytearray()
            while True:
                absolute_remaining(deadline)
                raw=response.read(min(4096,524289-len(chunks)))
                absolute_remaining(deadline)
                if not raw:break
                chunks.extend(raw)
                if len(chunks)>524288:return health_projection(status,None,'JSON')
            try:body=strict_json(bytes(chunks),524288)
            except (ValueError,FixtureFailure):return health_projection(status,None,'JSON')
            return health_projection(status,body,transport)
        except ssl.SSLError:return health_projection(status,None,'TLS')
        except (TimeoutError,socket.timeout):return health_projection(status,None,'TIMEOUT')
        except OSError as error:
            reason=getattr(error,'reason',None)
            return health_projection(status,None,'TLS' if isinstance(reason,ssl.SSLError) else 'TIMEOUT' if isinstance(reason,(TimeoutError,socket.timeout)) else 'CONNECT')
        except FixtureFailure:raise
        except Exception:return health_projection(status,None,'OTHER')
        finally:
            if response is not None:response.close()
    def request(self,method,path,body=None,key=None):
        headers={'Origin':ORIGIN}
        if body is not None:headers['Content-Type']='application/json'
        if key:headers['Idempotency-Key']=key
        request=urllib.request.Request(ORIGIN+path,None if body is None else canonical(body),headers,method=method)
        with self.client.open(request,timeout=remaining(self.deadline)) as response:
            if response.status!=200:raise FixtureFailure('HTTP')
            raw=response.read(524289)
        return strict_json(raw,524288)
    def exercise(self,rid,approve):
        with self.smtp.lock:self.smtp.tokens.clear()
        self.request('POST','/api/auth/request-link',{'email':'native-linux-probe@example.invalid'})
        end=min(self.deadline,time.monotonic()+3)
        while True:
            with self.smtp.lock:token=self.smtp.tokens[-1] if self.smtp.tokens else None
            if token:break
            remaining(end);time.sleep(.02)
        result=self.request('POST','/api/auth/verify',{'token':token})
        if result.get('ok') is not True:raise FixtureFailure('AUTH')
        if rid is None:
            problem={'entry':'phenomenon','original_input':'合成观察：集中到达的任务出现更长等待。','objective':'减少等待','summary':'仅用于隔离生命周期探针','variables':[],'constraints':[],'unknowns':[],'confirmed':True}
            root=self.request('POST','/api/research',{'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'problem':problem}},'native-linux-create')
            rid=root['data']['research']['id']
        root=self.request('GET','/api/research/'+rid);view=root['data'];p=view['current_problem']
        identity=[rid,view['research']['created_at'],p['revision'],p['digest'],p['created_at']]
        health=self.request('GET','/api/health')
        if health['checks']['base']!='ready' or health['checks']['source_execute']!='ready':raise FixtureFailure('HEALTH')
        if approve:
            preview=self.request('POST','/api/research/'+rid+'/plan-previews',{'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':{'input_revision':1,'expected_research_version':view['research_version'],'observation_source':'own_observation','declaration_status':'self_declared'}},'native-linux-preview')['data']
            if preview['can_confirm'] is not True:raise FixtureFailure('FUNDING')
            body={k:preview[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};body['confirm_outbound']=True
            self.request('POST','/api/research/'+rid+'/plan-approvals',{'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':body},'native-linux-confirm')
        return {'rid':rid,'identity_digest':hashlib.sha256(canonical(identity)).hexdigest(),'native_ready':health['checks']['native_planner']=='NATIVE_OWNER_READY_SLOT_REQUIRED'}
    def close(self):
        end=self.deadline if self.ready else self.ready_deadline
        errors=[];workers=[]
        for server in self.servers:server._BaseServer__shutdown_request=True
        for thread in self.threads:
            try:thread.join(absolute_remaining(end,2))
            except BaseException as error:errors.append(type(error))
        # Registration precedes Thread.start, and no server loop can create a
        # later worker after its join. Tombstones are kept until this boundary.
        for server in self.servers:
            lock=getattr(server,'worker_lock',None)
            if lock is not None:
                with lock:workers.extend(server.workers)
            if getattr(server,'worker_uncertain',False):errors.append(RuntimeError)
        for thread in workers:
            try:thread.join(absolute_remaining(end,2))
            except BaseException as error:errors.append(type(error))
        for server in reversed(self.servers):
            try:server.server_close()
            except BaseException as error:errors.append(type(error))
        if time.monotonic()>end:errors.append(TimeoutError)
        if errors or any(t.is_alive() for t in (*self.threads,*workers)):raise FixtureFailure('CLEANUP')


def _code(raw,path,names):
    current=compile(raw,str(path),'exec',dont_inherit=True)
    for name in names:current=next(v for v in current.co_consts if type(v) is types.CodeType and v.co_name==name)
    return current


class Observer:
    """Read-only fixed-code trace/profile; never serializes frame locals."""
    def __init__(self,deadline):
        self.deadline=deadline;self.codes={};self.connections={};self.connection_current={};self.fds={};self.fd_current={};self.closes={};self.barrier=False
        self.budget_id=None;self.budget_source=False;self.budget_native=False;self.stop_time=self.stop_deadline=None
        self.summary={k:None for k in SUMMARY_KEYS};self.summary.update(source_closed=False,native_closed=False,proof_taken=False,component_woken=False,observer_failed=False)
        sources={'sqlite':('web/backend/services/sqlite_utils.py',(('connect_private_auth',),('connect_private_history',),('connect_private_sso',))),
                 'source_join':('web/backend/research/source_supervisor.py',(('join',),)),
                 'native_join':('web/backend/research/native_plan_supervisor.py',(('join',),)),
                 'slot':('web/backend/research/native_plan_supervisor.py',(('NativePlanSlotLease','__init__'),)),
                 'budget':('web/backend/research/native_plan_supervisor.py',(('_ThreadBudget','__enter__'),)),
                 'stop_clock':('web/backend/research/native_plan_supervisor.py',(('shrink_main_deadline',),)),
                 'proof':('web/backend/research/plan_native_runtime.py',(('take_native_attempt_cleanup',),)),
                 'balance':('web/backend/services/plan_runtime_transport.py',(('NativePlanResource','balance'),)),
                 'credential_fd':('web/backend/services/native_live_credentials.py',(('_CredentialFDHandle','record'),)),
                 'control_fd':('web/backend/research/native_live_grant.py',(('_ControlReadHandle','open'),)),
                 'network':('web/backend/services/plan_runtime_transport.py',( ('NativePlanResource','_connect_live'),)),
                 'dns':('web/backend/services/native_dns_process.py',(('resolve_native_host',),))}
        for label,(relative,names) in sources.items():
            path=ROOT/relative
            if path.is_symlink():raise FixtureFailure('SOURCE')
            raw=path.read_bytes()
            if len(raw)>262144:raise FixtureFailure('SOURCE')
            for name in names:self.codes[_code(raw,path,name)]=(label,path)
        self.fd_closers=set()
        for relative,names in (('web/backend/research/native_plan_supervisor.py',('_worker_main',)),('web/backend/research/native_live_grant.py',('_close_fd',)),('web/backend/services/native_live_credentials.py',('_CredentialFDHandle','close'))):
            path=ROOT/relative;self.fd_closers.add(_code(path.read_bytes(),path,names))
        path=ROOT/'web/backend/services/sqlite_utils.py';self.connection_closer=_code(path.read_bytes(),path,('PrivateHistoryConnection','close'))
    def fd_birth(self,fd):
        info=os.fstat(fd);identity=(fd,info.st_dev,info.st_ino);prior=self.fd_current.get(identity)
        if prior is not None and not self.fds[prior][1]:return
        key=(*identity,len(self.fds));self.fd_current[identity]=key;self.fds[key]=[threading.get_ident(),False]
    def trace(self,frame,event,arg):
        entry=self.codes.get(frame.f_code)
        if entry is None:return None
        frame.f_trace_lines=False
        try:
            label,path=entry
            module=sys.modules.get(frame.f_globals.get('__name__'))
            if frame.f_code.co_filename!=str(path) or module is None or vars(module) is not frame.f_globals or Path(module.__file__)!=path:raise FixtureFailure('SOURCE')
            if event=='call' and label in ('network','dns'):
                self.summary['observer_failed']=True;emit_event('NETWORK_ENTRY',{});raise FixtureFailure('NETWORK')
            if event=='call' and label=='balance':self.wait_slot(frame)
            if event=='return':
                if label=='sqlite' and isinstance(arg,sqlite3.Connection):
                    expected=sys.modules.get('services.sqlite_utils')
                    if expected is None or type(arg) not in (expected.PrivateAuthConnection,expected.PrivateHistoryConnection,expected.PrivateSsoConnection):raise FixtureFailure('SOURCE')
                    prior=self.connection_current.get(id(arg))
                    if prior is not None and self.connections[prior][0]() is arg:return self.trace
                    try:ref=weakref.ref(arg)
                    except TypeError:ref=lambda:None
                    key=(id(arg),len(self.connections));self.connection_current[id(arg)]=key
                    self.connections[key]=[ref,threading.get_ident(),False,False]
                elif label=='slot':
                    slot=frame.f_locals['self'];self.fd_birth(slot.stop_fd);self.fd_birth(slot._write_fd)
                elif label=='credential_fd':self.fd_birth(frame.f_locals['fd'])
                elif label=='control_fd' and type(arg) is tuple and len(arg)==2:self.fd_birth(arg[0])
                elif label=='proof' and arg is not None:
                    module=sys.modules.get('research.plan_native_runtime')
                    if module is None or type(arg) is not module.NativeAttemptCleanupProof:raise FixtureFailure('PROOF')
                    self.summary['proof_taken']=True;emit_event('PROOF_TAKEN',{})
                elif label=='budget' and arg is not None:
                    budget=frame.f_locals['self'];module=sys.modules.get('research.native_plan_supervisor')
                    if type(budget) is not module._ThreadBudget or not budget.active or module._CONTEXTS.get(id(budget.scope.binding.app)) is not budget.scope:raise FixtureFailure('CLOCK')
                    identity=id(budget.scope.budget)
                    if self.budget_id is not None and self.budget_id!=identity:raise FixtureFailure('CLOCK')
                    self.budget_id=identity
                    if budget.source is not None and budget.source._thread is threading.current_thread():self.budget_source=True
                    if budget.supervisor is not None and budget.supervisor._thread is threading.current_thread():self.budget_native=True
                    if self.budget_source and self.budget_native:self.summary['same_deadline_ref']=True
                elif label=='stop_clock' and arg is not None:
                    if type(arg) not in (int,float) or not math.isfinite(arg):raise FixtureFailure('CLOCK')
                    scope=frame.f_locals['scope']
                    if id(scope.budget)!=self.budget_id:raise FixtureFailure('CLOCK')
                    self.stop_time,self.stop_deadline=time.monotonic(),arg
                elif label in ('source_join','native_join') and arg is not None:
                    module=sys.modules.get('research.source_supervisor' if label=='source_join' else 'research.native_plan_supervisor')
                    expected=getattr(module,'SourceCleanupReceipt' if label=='source_join' else 'NativePlanCleanupReceipt',None)
                    if type(arg) is not expected:raise FixtureFailure('RECEIPT')
                    closed=arg.state=='CLOSED' and arg.reason=='CLOSED' and arg.pending_task_id is None
                    self.summary['source_closed' if label=='source_join' else 'native_closed']=closed
                    if self.summary['source_closed'] and self.summary['native_closed'] and self.stop_deadline is not None:
                        self.summary['within_main_deadline']=time.monotonic()<=self.stop_deadline
                        self.summary['main_stop_to_closed_ms']=int((time.monotonic()-self.stop_time)*1000)
                    emit_event('SOURCE_JOIN' if label=='source_join' else 'NATIVE_JOIN',{'closed':closed})
        except BaseException:
            self.summary['observer_failed']=True;emit_event('OBSERVER_FAILED',{});raise
        return self.trace
    def profile(self,frame,event,arg):
        # Observe original native closes; do not replace os/sqlite functions.
        if event not in ('c_call','c_return','c_exception'):return
        if arg is os.close and frame.f_code in self.fd_closers:
            fd=frame.f_locals.get('fd')
            if type(fd) is not int:return
            if event=='c_call':
                try:
                    info=os.fstat(fd);key=self.fd_current.get((fd,info.st_dev,info.st_ino))
                    if key is not None:self.closes[(threading.get_ident(),id(frame))]=key
                except OSError:pass
            else:
                key=self.closes.pop((threading.get_ident(),id(frame)),None)
                if key is not None and event=='c_return' and self.fds[key][0]==threading.get_ident():self.fds[key][1]=True
        elif frame.f_code is self.connection_closer and type(arg) is types.BuiltinMethodType and arg.__name__=='close':
            connection=getattr(arg,'__self__',None);key=self.connection_current.get(id(connection));record=self.connections.get(key)
            if record is not None and event=='c_return':
                try:connection.in_transaction
                except sqlite3.ProgrammingError:
                    record[2]=True;record[3]=record[1]==threading.get_ident()
    def wait_slot(self,frame):
        if self.barrier:raise FixtureFailure('REPEAT')
        module=sys.modules.get('research.native_plan_supervisor');resource=frame.f_locals.get('self');cap=frame.f_locals.get('capability')
        slot=getattr(cap,'slot_scope',None);session=getattr(resource,'_live_session',None)
        if module is None or type(slot) is not module.NativePlanSlotLease or getattr(cap,'resource',None) is not resource or slot.dispatch!=cap.claim[0]:raise FixtureFailure('SLOT')
        module.require_slot(slot,cap.store,session,task_id=slot.task_id,purpose=slot.purpose,mode='cleanup')
        self.barrier=True;fd=slot.stop_fd;identity=slot.stop_fd_identity
        emit_event('SLOT_BEFORE_GET',{})
        left,right=socket.socketpair();left.setblocking(False);right.setblocking(False)
        began=time.monotonic();component_deadline=began+180
        try:
            ready,_,_=select.select([left,fd],[],[],remaining(min(component_deadline,self.deadline),180))
            info=os.fstat(fd)
            if fd not in ready or (info.st_dev,info.st_ino)!=identity:raise FixtureFailure('STOP')
            self.summary['component_woken']=True;self.summary['component_ms']=int((time.monotonic()-began)*1000)
            emit_event('SLOT_WOKEN',{'elapsed_ms':self.summary['component_ms']})
        finally:left.close();right.close()
        # Return to the original B function. It creates the real stop primary.
    def finish(self):
        self.summary.update(connections_born=len(self.connections),connections_creator_closed=sum(v[3] for v in self.connections.values()),connections_property_closed=sum(v[2] for v in self.connections.values()),fds_born=len(self.fds),fds_creator_closed=sum(v[1] for v in self.fds.values()))
        closed=0
        for key,record in self.fds.items():
            fd,dev,ino,_=key
            if record[1]:closed+=1;continue
            try:info=os.fstat(fd);closed+=int((info.st_dev,info.st_ino)!=(dev,ino))
            except OSError:closed+=1
        self.summary['fds_property_closed']=closed
        emit_event('FINAL',validate_summary(self.summary))


def _observe():
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:raise FixtureFailure('FLAGS')
    config=strict_json((WORK/'observer.json').read_bytes())
    if set(config)!= {'deadline','head'} or not re.fullmatch('[0-9a-f]{40}',config['head']):raise FixtureFailure('CONFIG')
    remaining(config['deadline']);observer=Observer(config['deadline'])
    if any(name=='main' or name.startswith(('api.','services.','research.','web.backend')) for name in sys.modules):raise FixtureFailure('PREIMPORT')
    entry=ROOT/'scripts/run-formal-main.py';sys.argv=[str(entry)]
    sys.settrace(observer.trace);threading.settrace(observer.trace);sys.setprofile(observer.profile);threading.setprofile(observer.profile)
    try:runpy.run_path(str(entry),run_name='__main__')
    finally:
        sys.settrace(None);threading.settrace(None);sys.setprofile(None);threading.setprofile(None);observer.finish()


def _bootstrap():
    sys.path[:0]=[str(ROOT/'web/backend'),str(ROOT)]
    from services.auth_registration import bootstrap_private_runtime
    result=bootstrap_private_runtime()
    if result['research_schema']!=15:raise FixtureFailure('SCHEMA')
    print('BOOTSTRAP_OK',flush=True)


def _serve():
    config=strict_json(sys.stdin.buffer.readline(65537))
    if set(config)!= {'password','deadline','ready_deadline'} or type(config['password']) is not str:raise FixtureFailure('CONFIG')
    now=time.monotonic();remaining(config['deadline']);absolute_remaining(config['ready_deadline'])
    if config['ready_deadline']>config['deadline'] or config['ready_deadline']>now+10:raise FixtureFailure('CONFIG')
    service=LocalService(config['password'],config['deadline'],config['ready_deadline'])
    try:
        try:service.start()
        except BaseException as error:
            if service.startup.state.terminal is None and service.startup.state.last is not None:
                try:service.startup.emit('FAILED',service.health,error)
                except BaseException:pass
            raise FixtureFailure('STARTUP') from None
        while True:
            raw=sys.stdin.buffer.readline(65537)
            if not raw:return
            request=strict_json(raw)
            if type(request) is not dict or set(request)!= {'rid','approve'} or type(request['approve']) is not bool:raise FixtureFailure('COMMAND')
            if request['rid'] is not None and not re.fullmatch('[0-9a-f-]{36}',request['rid']):raise FixtureFailure('REF')
            response=canonical(service.exercise(request['rid'],request['approve']))+b'\n'
            if len(response)>65536:raise FixtureFailure('HTTP')
            fd=sys.stdout.fileno();offset=0
            while offset<len(response):
                if not select.select([],[fd],[],absolute_remaining(service.deadline))[1]:raise FixtureFailure('CLOCK')
                try:sent=os.write(fd,response[offset:])
                except BlockingIOError:continue
                if sent<=0:raise FixtureFailure('HTTP')
                offset+=sent
    finally:service.close()


if __name__=='__main__':
    try:
        if sys.argv[1:]==['bootstrap']:_bootstrap()
        elif sys.argv[1:]==['serve']:_serve()
        elif sys.argv[1:]==['observe']:_observe()
        else:raise FixtureFailure('ARGUMENT')
    except FixtureFailure:
        print('FIXTURE_FAILED',file=sys.stderr);raise SystemExit(78)
