"""Closed production port and native loopback fixture HTTP resources.

No callback, real credential loader, external endpoint or environment unlock.
A future live installer must be a separately reviewed fixed server module.
"""
from http.server import ThreadingHTTPServer,HTTPServer
import os
import re
import select
import socket
import threading
import time
from uuid import uuid4
from .errors import ResearchError
from .provider_schemas import strict_json,digest

CREDENTIAL_REFERENCE='structural-deepseek-api-key'
_FACTORY=object()
_RESOURCES={}
_RETURNS={}
_PENDING={}


def _ready(conn,deadline,*,read=False):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('fixture HTTP wall limit')
    readable,writable,failed=select.select([conn] if read else [],[] if read else [conn],[conn],remaining)
    if failed or not (readable if read else writable):raise TimeoutError('fixture HTTP wall limit')


def _connect(port):
    deadline=time.monotonic()+2
    conn=socket.socket(socket.AF_INET,socket.SOCK_STREAM);conn.setblocking(False)
    try:
        conn.connect_ex(('127.0.0.1',port));_ready(conn,deadline)
        if conn.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR):raise OSError('fixture connection unavailable')
        return conn,deadline
    except BaseException:conn.close();raise


def _request(resource,method,path,raw):
    return (method+' '+path+' HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\nContent-Type: application/json\r\nX-Fixture-Incarnation: '+resource.credential_incarnation+'\r\nContent-Length: '+str(len(raw))+'\r\n\r\n').encode('ascii')+raw


def _send_remaining(conn,deadline,pending):
    while pending:
        _ready(conn,deadline);sent=conn.send(pending)
        if not sent:raise OSError('fixture send interrupted')
        pending=pending[sent:]


def _receive(conn,deadline):
    buffer=bytearray()
    while True:
        _ready(conn,deadline,read=True);chunk=conn.recv(16384)
        if not chunk:break
        buffer.extend(chunk)
        if len(buffer)>81920:raise ValueError('provider response limit')
    head,separator,body=bytes(buffer).partition(b'\r\n\r\n')
    if not separator or len(head)>16384 or len(body)>65536:raise ValueError('bounded HTTP response required')
    lines=head.split(b'\r\n');status=re.fullmatch(rb'HTTP/1\.[01] ([0-9]{3}) [^\r\n]*',lines[0])
    if not status:raise ValueError('fixed HTTP response required')
    headers={}
    for line in lines[1:]:
        key,colon,value=line.partition(b':');key=key.lower()
        if not colon or key in headers:raise ValueError('ambiguous response headers')
        headers[key]=value.strip()
    if b'transfer-encoding' in headers:raise ValueError('fixture chunked encoding unavailable')
    length=headers.get(b'content-length')
    if length is not None and (not length.isdigit() or int(length)!=len(body)):raise ValueError('incomplete response')
    return int(status[1]),body


class FixturePlanResource:
    __slots__=('server','port','pid','nonce','credential_incarnation','economic_binding','active','flight','_socket_identity')
    def __init__(self,server,*,economic_binding,credential_incarnation,_factory=None):
        if _factory is not _FACTORY or type(server) not in (ThreadingHTTPServer,HTTPServer):raise TypeError('actual fixture server required')
        if server.server_address[0]!='127.0.0.1' or not isinstance(server.socket,socket.socket):raise PermissionError('loopback fixture only')
        self.server,self.port,self.pid=server,server.server_address[1],os.getpid()
        self.nonce,self.credential_incarnation,self.economic_binding=str(uuid4()),credential_incarnation,economic_binding
        self.active,self.flight=True,threading.Lock()
        self._socket_identity=os.fstat(server.socket.fileno())[:2]
        _RESOURCES[self.nonce]=self
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('credential resource immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('credential resource cannot be serialized')
    def require(self):
        if (not self.active or self.pid!=os.getpid() or _RESOURCES.get(self.nonce) is not self
                or os.fstat(self.server.socket.fileno())[:2]!=self._socket_identity):raise PermissionError('actual fixture resource ended')
    def balance(self):
        self.require();conn,deadline=_connect(self.port)
        try:
            _send_remaining(conn,deadline,memoryview(_request(self,'GET','/user/balance',b'')))
            status,raw=_receive(conn,deadline)
        finally:conn.close()
        data=strict_json(raw,65536)
        if status!=200 or type(data) is not dict or data.get('is_available') is not True:raise ResearchError('BUDGET_UNVERIFIED',503,'资金余额不可用，请重新预览。')
        balances=data.get('balance_infos')
        if type(balances) is not list or len(balances)!=1 or type(balances[0]) is not dict or balances[0].get('currency')!='CNY':raise ResearchError('BUDGET_UNVERIFIED',503,'需要当前官方原币余额。')
        from decimal import Decimal
        text=balances[0].get('total_balance')
        if type(text) is not str or len(text)>32:raise ValueError('native CNY balance required')
        amount=Decimal(text)*1_000_000
        if not amount.is_finite() or amount<0 or amount!=amount.to_integral_value():raise ValueError('native CNY balance required')
        return int(amount),digest(raw)
    def prepare_post(self):
        self.require();conn,deadline=_connect(self.port)
        try:return PendingPlanHTTP(self,conn,deadline,_factory=_FACTORY)
        except BaseException:conn.close();raise
    def post(self,_):raise PermissionError('native prepared first-write capability required')
    def close(self):object.__setattr__(self,'active',False);_RESOURCES.pop(self.nonce,None)


class PendingPlanHTTP:
    """Actual connected FD, one first-write grant, bounded receive after unlock."""
    __slots__=('resource','conn','deadline','pid','identity','reference','active','grant','remaining')
    def __init__(self,resource,conn,deadline,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual fixed connection required')
        self.resource,self.conn,self.deadline,self.pid=resource,conn,deadline,os.getpid()
        info=os.fstat(conn.fileno());self.identity=(info.st_dev,info.st_ino)
        self.reference,self.active,self.grant,self.remaining=str(uuid4()),True,None,None
        _PENDING[self.reference]=self
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('native pending resource immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native pending resource cannot be serialized')
    def require(self):
        self.resource.require();info=os.fstat(self.conn.fileno())
        if not self.active or self.pid!=os.getpid() or _PENDING.get(self.reference) is not self or (info.st_dev,info.st_ino)!=self.identity:raise PermissionError('actual pending socket lifetime required')
    def write_first(self,capability):
        from .plan_runtime import _PlanSendLease
        self.require()
        if self.grant is not None or type(capability) is not _PlanSendLease:raise PermissionError('single native first-write capability required')
        raw,dispatch,nonce,admission_digest=capability.consume(self.resource)
        request=_request(self.resource,'POST','/chat/completions',raw)
        if time.monotonic()>=self.deadline:raise TimeoutError('fixture HTTP wall limit')
        # This nonblocking syscall never waits for a response while holding Owner.
        sent=self.conn.send(request)
        if not sent:raise OSError('fixture first write interrupted')
        object.__setattr__(self,'remaining',request[sent:])
        object.__setattr__(self,'grant',(dispatch,nonce,admission_digest))
    def receive(self):
        self.require()
        if self.grant is None:raise PermissionError('actual first write required')
        try:
            _send_remaining(self.conn,self.deadline,memoryview(self.remaining))
            status,body=_receive(self.conn,self.deadline)
            dispatch,nonce,admission_digest=self.grant
            result=OwnedPlanReturn(_factory=_FACTORY,resource=self.resource,dispatch=dispatch,claim_nonce=nonce,admission_digest=admission_digest,status=status,body=body)
            _RETURNS[result.reference]=result
            return result
        finally:self.close()
    def close(self):
        if self.active:
            object.__setattr__(self,'active',False);_PENDING.pop(self.reference,None);self.conn.close()


class OwnedPlanReturn:
    __slots__=('resource','dispatch','claim_nonce','admission_digest','status','body','reference','pid','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('actual owned HTTP return required')
        for k,v in values.items():object.__setattr__(self,k,v)
        object.__setattr__(self,'reference',str(uuid4()));object.__setattr__(self,'pid',os.getpid());object.__setattr__(self,'active',True)
    def __setattr__(self,*args):raise TypeError('owned return immutable')
    def __reduce__(self):raise TypeError('owned return cannot be serialized')
    def require(self,resource,dispatch,nonce,admission_digest):
        self.resource.require()
        if not self.active or self.pid!=os.getpid() or _RETURNS.get(self.reference) is not self or self.resource is not resource or (self.dispatch,self.claim_nonce,self.admission_digest)!=(dispatch,nonce,admission_digest):raise PermissionError('actual owned return mismatch')
    def close(self):object.__setattr__(self,'active',False);_RETURNS.pop(self.reference,None)


def fixture_resource(server,*,economic_binding,credential_incarnation):
    """Explicit synthetic server resource, never proof of real funded service."""
    if type(credential_incarnation) is not str or not 1<=len(credential_incarnation)<=100 or re.fullmatch(r'fixture-[a-zA-Z0-9._:-]+',credential_incarnation) is None:raise ValueError('explicit fixture identity required')
    return FixturePlanResource(server,economic_binding=economic_binding,credential_incarnation=credential_incarnation,_factory=_FACTORY)


def sending(dispatch):
    for pending in tuple(_PENDING.values()):
        if pending.grant is not None and pending.grant[0]==dispatch:
            try:
                pending.require()
                if time.monotonic()<pending.deadline:return True
            except (OSError,PermissionError):pass
    return False
