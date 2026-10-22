"""Sealed native-plan ports and controlled native fixture resources.

Human authorization documents are never parsed here. The real private provision
bootstrap is unbound and closed. Only the explicitly named controlled fixture
issuer can currently create an authority, with a real registered current owner.
"""
from dataclasses import dataclass
from http.server import HTTPServer,ThreadingHTTPServer
import hashlib,importlib,os,socket,stat,time
from pathlib import Path
from uuid import uuid4
from .authorization import AuthorizationGate,AccountIdentity
from .errors import ResearchError
from .provider_schemas import canonical,digest,strict_json
from . import plan_native_financial as financial
from .plan_transport import _ready,_send_remaining,_receive

CREDENTIAL_REF='structural-deepseek-api-key'
_FACTORY=object()
_AUTHORITIES={};_PROVISIONS={};_PERMITS={};_RESOURCES={};_BALANCES={};_RETURNS={};_PENDING={};_INSTALLATIONS={}
FUNDING_TABLE=financial.NAMES[0]


def _module_digest():return digest(Path(__file__).read_bytes())
def _uid():return str(uuid4())
def _family():return 'web.backend.services' if __package__=='web.backend.research' else 'services'

def _runtime_module():
    name=_family()+'.plan_runtime_transport'
    try:module=importlib.import_module(name)
    except ModuleNotFoundError as error:
        if error.name!=name:raise
        raise ResearchError('FUNDING_CLOSED',503,'固定原生传输模块尚未安装。') from None
    expected=Path(__file__).resolve().parents[1]/'services'/'plan_runtime_transport.py'
    if Path(module.__file__).resolve()!=expected or Path(module.__file__).is_symlink():raise PermissionError('canonical native Runtime namespace/source required')
    return module

def _gate_identity(path):
    value=path.stat();return value.st_dev,value.st_ino

def _fd_identity(fd):
    info=os.fstat(fd)
    return (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)


class _Sealed:
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('native capability immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native capability cannot be serialized')


class OwnerFundingAuthorityLease(_Sealed):
    __slots__=('store','identity','principal','owner_gate_id','fd','path','native_identity','pid','reference','facts','server','server_identity','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('fixed native bootstrap required')
        for name,value in values.items():setattr(self,name,value)
    def require(self,*,current=True):
        if not self.active or self.pid!=os.getpid() or _AUTHORITIES.get(self.reference) is not self or _fd_identity(self.fd)!=self.native_identity:raise PermissionError('native authority lifetime ended')
        named=self.path.lstat()
        if (named.st_dev,named.st_ino)!=(self.native_identity[0],self.native_identity[1]) or not stat.S_ISREG(named.st_mode) or named.st_uid!=os.getuid() or named.st_nlink!=1 or stat.S_IMODE(named.st_mode)!=0o600:raise PermissionError('native authority resource replaced')
        if _fd_identity(self.server.socket.fileno())[:2]!=self.server_identity:raise PermissionError('controlled issuer server ended')
        if current:
            with self.store.transaction() as conn:
                principal=AuthorizationGate(self.store).check(conn,self.identity,self.principal)
                if principal['gate_id']!=self.owner_gate_id or self.store.auth_store.owner_gate_in(conn,self.identity.email)!=self.owner_gate_id:raise PermissionError('native authority current incarnation differs')
    def close(self):
        if self.active:
            object.__setattr__(self,'active',False);_AUTHORITIES.pop(self.reference,None)
            os.close(self.fd)


def bootstrap_native_owner_authority(store):
    """No approved native provision resource is bound in this release.

    In particular, a Markdown/JSON statement, its hash, an email, a caller FD,
    environment flag, or provider balance cannot create this authority.
    """
    raise ResearchError('FUNDING_CLOSED',503,'受信原生资金资源尚未绑定；账户和已存研究仍可使用。')


def create_controlled_fixture_authority(store,identity,server,*,approved_cap_units,risk_margin_units=0):
    return _fixture_authority(store,identity,server,approved_cap_units,risk_margin_units,_module_digest())


def create_controlled_runtime_fixture_authority(store,identity,server,*,approved_cap_units,risk_margin_units=0):
    """Fixed canonical Runtime fixture issuer; never native/live authority."""
    module=_runtime_module()
    return _fixture_authority(store,identity,server,approved_cap_units,risk_margin_units,digest(Path(module.__file__).read_bytes()))


def _evidence_purpose_domain():
    from . import evidence_method_plan_schemas as types,evidence_method_plan_codec as codec
    return dict(purpose=types.PURPOSE,input_template=types.INPUT_TEMPLATE,candidate_schema=types.CANDIDATE_SCHEMA,
        result_schema=types.RESULT_SCHEMA,codec_revision=types.CODEC_REVISION,template_digest=codec.template_digest(),
        provider='deepseek',model='deepseek-flash',method='POST',target='https://api.deepseek.com/chat/completions')


def create_controlled_evidence_method_fixture_authority(store,identity,server,*,approved_cap_units,risk_margin_units=0):
    """Only the fixed evidence purpose; never the self-declaration factory."""
    return _fixture_authority(store,identity,server,approved_cap_units,risk_margin_units,_module_digest(),_evidence=True)


def create_controlled_runtime_evidence_method_fixture_authority(store,identity,server,*,approved_cap_units,risk_margin_units=0):
    module=_runtime_module()
    return _fixture_authority(store,identity,server,approved_cap_units,risk_margin_units,digest(Path(module.__file__).read_bytes()),_evidence=True)


def purpose_scope(resource):
    facts=strict_json(resource.permit.facts,16384)
    domain=facts.get('purpose_domain')
    if domain is None:return 'phenomenon_plan_v1'
    if domain!=_evidence_purpose_domain():raise PermissionError('sealed evidence purpose domain differs')
    return 'evidence_method_plan_v1'


def require_purpose(store,purpose,*,current=True):
    pair=installation(store)
    if pair is None:raise ResearchError('FUNDING_CLOSED',503,'该目的的原生资源当前关闭。')
    provision,resource=pair
    if type(provision) is not NativePlanProvision:raise PermissionError('actual purpose provision required')
    if type(resource) is not ControlledNativeResource:
        module=_runtime_module()
        if type(resource) is not module.NativePlanResource:raise PermissionError('actual purpose resource required')
    provision.require(current=current);resource.require(current=current)
    if resource.permit.provision is not provision or purpose_scope(resource)!=purpose:raise ResearchError('FUNDING_CLOSED',503,'原资源未授权此目的，请使用独立授权。')
    return resource


def _fixture_authority(store,identity,server,approved_cap_units,risk_margin_units,runtime_digest,*,_evidence=False):
    """Explicit server fixture bootstrap, never a real/live funding issuer."""
    if _evidence:
        frame=__import__('sys')._getframe(1)
        try:
            if _evidence is not True or frame.f_globals is not globals() or frame.f_code not in _EVIDENCE_FACTORY_CODES:raise PermissionError('fixed evidence fixture issuer required')
        finally:del frame
    from .service import ResearchService
    if type(identity) is not AccountIdentity or type(server) not in (HTTPServer,ThreadingHTTPServer) or server.server_address[0]!='127.0.0.1':raise PermissionError('actual registered owner and loopback fixture required')
    if any(type(v) is not int or not 0<=v<=9223372036854775807 for v in (approved_cap_units,risk_margin_units)):raise ValueError('native fixed-unit declaration required')
    principal=ResearchService(store)._principal(identity,create=True)
    with AuthorizationGate(store).owner_gate(principal),store.transaction() as conn:
        owner=AuthorizationGate(store).check(conn,identity,principal)
        gate=owner['gate_id'];expected=store.auth_store.expected_owner_gate_identity(gate)
        if expected!=_gate_identity(store.path.parent/'research-locks'/(gate+'.lock')):raise PermissionError('actual owner gate receipt differs')
        old=conn.execute('SELECT * FROM '+FUNDING_TABLE+' WHERE id=1').fetchone()
        if old:raise ResearchError('RECONCILIATION_REQUIRED',409,'已有原生资金绑定，不能另建账户或重置账本。')
        for table in ('research_funding_accounts','research_project_budgets','research_reservations','research_plan_dispatches'):
            if conn.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchone():raise ResearchError('LEDGER_BINDING_REQUIRED',409,'非空历史资金账本不能被自动收养为原生资金。')
    reference=_uid();path=store.path.parent/('native-plan-authority-'+reference+'.lock')
    parent=os.open(store.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);fd=None
    try:
        fd=os.open(path.name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        os.write(fd,os.urandom(32));os.fsync(fd);os.fsync(parent);native=_fd_identity(fd)
        if native[2:]!=(os.getuid(),0o600,1):raise PermissionError('native fixture authority is unsafe')
        facts=dict(version='controlled-owner-provision-v1',mode='controlled_fixture',principal_id=principal,generation=identity.generation,
            owner_gate_id=gate,authority_ref=reference,account_id=_uid(),economic_binding=_uid(),credential_incarnation='controlled-'+_uid(),grant_epoch=1,
            approved_cap_units=approved_cap_units,risk_margin_units=risk_margin_units,runtime_digest=runtime_digest,network_ref='owned-loopback-'+reference)
        if _evidence:
            facts['purpose_domain']=_evidence_purpose_domain()
        value=OwnerFundingAuthorityLease(_factory=_FACTORY,store=store,identity=identity,principal=principal,owner_gate_id=gate,fd=fd,path=path,native_identity=native,pid=os.getpid(),reference=reference,
            facts=canonical(facts),server=server,server_identity=_fd_identity(server.socket.fileno())[:2],active=True)
        _AUTHORITIES[reference]=value;return value
    except BaseException:
        if fd is not None:os.close(fd)
        raise
    finally:os.close(parent)


class NativePlanProvision(_Sealed):
    __slots__=('authority','facts','reference','pid','active')
    def __init__(self,authority,*,_factory=None):
        if _factory is not _FACTORY or type(authority) is not OwnerFundingAuthorityLease:raise TypeError('native owner authority required')
        authority.require();self.authority,self.facts,self.reference,self.pid,self.active=authority,authority.facts,_uid(),os.getpid(),True;_PROVISIONS[self.reference]=self
    def require(self,*,current=True):
        if not self.active or self.pid!=os.getpid() or _PROVISIONS.get(self.reference) is not self:raise PermissionError('actual native provision required')
        self.authority.require(current=current)
    def data(self):self.require();return strict_json(self.facts,16384)
    def close(self):object.__setattr__(self,'active',False);_PROVISIONS.pop(self.reference,None)


def issue_native_provision(store,authority_lease):
    if type(authority_lease) is not OwnerFundingAuthorityLease or authority_lease.store is not store:raise PermissionError('actual fixed owner authority required')
    return NativePlanProvision(authority_lease,_factory=_FACTORY)


class NativeRuntimePermit(_Sealed):
    __slots__=('provision','facts','reference','pid','active')
    def __init__(self,provision,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('fixed Core permit producer required')
        provision.require();self.provision,self.facts,self.reference,self.pid,self.active=provision,provision.facts,_uid(),os.getpid(),True;_PERMITS[self.reference]=self
    def require(self,*,current=True):
        if not self.active or self.pid!=os.getpid() or _PERMITS.get(self.reference) is not self:raise PermissionError('native runtime permit retired')
        self.provision.require(current=current)
    def data(self,*,current=True):self.require(current=current);return strict_json(self.facts,16384)
    def controlled_endpoint(self):
        self.require()
        if strict_json(self.facts,16384)['mode']!='controlled_fixture':raise PermissionError('controlled endpoint only')
        return ('127.0.0.1',self.provision.authority.server.socket.getsockname()[1])
    def close(self):object.__setattr__(self,'active',False);_PERMITS.pop(self.reference,None)


def mint_runtime_permit(provision):
    if type(provision) is not NativePlanProvision:raise PermissionError('fixed native provision required')
    return NativeRuntimePermit(provision,_factory=_FACTORY)


class OwnedBalanceReceipt(_Sealed):
    __slots__=('resource','claim','balance_units','response_digest','observed_at','credential_incarnation','reference','pid','active')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('actual controlled balance required')
        for name,value in values.items():setattr(self,name,value)
        self.reference,self.pid,self.active=_uid(),os.getpid(),True;_BALANCES[self.reference]=self
    def require(self,resource,claim):
        if not self.active or self.pid!=os.getpid() or _BALANCES.get(self.reference) is not self or self.resource is not resource or self.claim!=claim:raise PermissionError('actual owned balance receipt required')
        resource.require()
    def audit(self):return dict(protocol='owned-balance-v1',mode='controlled_fixture',balance_units=self.balance_units,currency='CNY',observed_at=self.observed_at,response_digest=self.response_digest,credential_incarnation=self.credential_incarnation)
    def close(self):object.__setattr__(self,'active',False);_BALANCES.pop(self.reference,None)


class OwnedNativeReturn(_Sealed):
    __slots__=('resource','dispatch','nonce','admission_digest','status','body','reference','pid','active','producer_digest','mode')
    def __init__(self,*,_factory=None,**values):
        if _factory is not _FACTORY:raise TypeError('actual native return factory required')
        for name,value in values.items():setattr(self,name,value)
        self.reference,self.pid,self.active=_uid(),os.getpid(),True;_RETURNS[self.reference]=self
    def require(self,resource,dispatch,nonce,admission_digest,producer_digest):
        if not self.active or self.pid!=os.getpid() or _RETURNS.get(self.reference) is not self or self.resource is not resource or (self.dispatch,self.nonce,self.admission_digest,self.producer_digest)!=(dispatch,nonce,admission_digest,producer_digest):raise PermissionError('actual native owned return required')
        resource.require(current=False)
    def close(self):object.__setattr__(self,'active',False);_RETURNS.pop(self.reference,None)


class ControlledNativeResource(_Sealed):
    __slots__=('permit','mode','producer','economic_binding','credential_incarnation','flight','pid','reference','active','port','credential_instance','_io','_cleanup_faults')
    def __init__(self,permit,*,_factory=None):
        import threading
        if _factory is not _FACTORY:raise TypeError('fixed controlled resource factory required')
        data=permit.data()
        if data['mode']!='controlled_fixture' or data['runtime_digest']!=_module_digest():raise PermissionError('controlled resource scope differs')
        self.permit,self.mode,self.producer=permit,'controlled_fixture','core-controlled-native-v1'
        self.economic_binding,self.credential_incarnation=data['economic_binding'],data['credential_incarnation']
        self.flight,self.pid,self.reference,self.active=threading.Lock(),os.getpid(),_uid(),True
        self.port=permit.provision.authority.server.socket.getsockname()[1];self.credential_instance=None;self._io={};self._cleanup_faults=[];_RESOURCES[self.reference]=self
    def require(self,*,current=True):
        if not self.active or self.pid!=os.getpid() or _RESOURCES.get(self.reference) is not self:raise PermissionError('controlled native resource retired')
        self.permit.require(current=current)
    def _open(self):
        # Track the actual socket immediately after allocation, before fstat,
        # nonblocking configuration or connect can raise without a handoff.
        self.require();deadline=time.monotonic()+2
        conn=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        record={'pid':os.getpid(),'identity':None,'holder':None,'fault':False}
        self._io[conn]=record
        try:
            record['identity']=_fd_identity(conn.fileno())[:2]
            conn.setblocking(False);conn.connect_ex(('127.0.0.1',self.port));_ready(conn,deadline)
            if conn.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR):raise OSError('controlled fixture connection unavailable')
            return conn,deadline
        except BaseException as primary:
            try:self._close_io(conn)
            except BaseException as cleanup:primary.add_note('owned connection cleanup uncertain: '+type(cleanup).__name__)
            raise
    def _close_io(self,conn):
        record=self._io.get(conn)
        if self.pid!=os.getpid() or record is None or record['pid']!=os.getpid():raise PermissionError('actual owned socket required')
        try:
            if conn.fileno()!=-1 and record['identity'] is not None and _fd_identity(conn.fileno())[:2]!=record['identity']:raise PermissionError('owned socket identity differs')
            conn.close()
            if conn.fileno()!=-1:raise OSError('owned socket not closed')
        except BaseException as error:
            record['fault']=True;self._cleanup_faults.append(type(error).__name__)
            raise
        else:
            # Even a physically closed FD cannot erase an observed close
            # exception. Keep that actual object for uncertainty reconciliation.
            if not record['fault']:self._io.pop(conn,None)
    def retire_unhanded(self):
        """Retire only this resource's residual IO, never funding or flight."""
        if self.pid!=os.getpid():raise PermissionError('owned IO belongs to another process')
        errors=[]
        for conn,record in list(self._io.items()):
            holder=record['holder']
            if holder is not None:
                if type(holder) is not ControlledNativePending or holder.resource is not self:
                    errors.append('foreign_holder');continue
                object.__setattr__(holder,'active',False);_PENDING.pop(holder.reference,None)
            try:self._close_io(conn)
            except BaseException as error:errors.append(type(error).__name__)
        if errors or self._cleanup_faults or self._io:
            raise ResearchError('CLEANUP_UNCERTAIN',503,'原生执行资源清场仍待核对；保留原记录，不会重发。')
    def _bytes(self,method,path,raw):
        return (method+' '+path+' HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\nContent-Type: application/json\r\nX-Fixture-Incarnation: '+self.credential_incarnation+'\r\nContent-Length: '+str(len(raw))+'\r\n\r\n').encode()+raw
    def balance(self,capability):
        from .plan_native_runtime import NativeBalanceLease
        if type(capability) is not NativeBalanceLease:raise PermissionError('actual pre-GET claim required')
        claim=capability.consume(self);self.require()
        # The fixture has no real key; an opaque instance identifies the same
        # controlled credential resource for both actual requests.
        if self.credential_instance is None:object.__setattr__(self,'credential_instance',_uid())
        conn,deadline=self._open()
        primary=None
        try:
            _send_remaining(conn,deadline,memoryview(self._bytes('GET','/user/balance',b'')));status,raw=_receive(conn,deadline)
        except BaseException as error:primary=error;raise
        finally:
            try:self._close_io(conn)
            except BaseException as cleanup:
                if primary is None:raise
                primary.add_note('owned balance cleanup uncertain: '+type(cleanup).__name__)
        data=strict_json(raw,65536)
        if status!=200 or type(data) is not dict or data.get('is_available') is not True:raise ResearchError('BUDGET_UNVERIFIED',503,'当前余额不可核对。')
        infos=data.get('balance_infos')
        if type(infos) is not list or len(infos)!=1 or type(infos[0]) is not dict or infos[0].get('currency')!='CNY':raise ValueError('one exact CNY balance required')
        from decimal import Decimal
        text=infos[0].get('total_balance')
        if type(text) is not str or len(text)>32:raise ValueError('bounded native cash required')
        units=Decimal(text)*1000000
        if not units.is_finite() or units<0 or units!=units.to_integral_value():raise ValueError('native CNY units required')
        return OwnedBalanceReceipt(_factory=_FACTORY,resource=self,claim=claim,balance_units=int(units),response_digest=digest(raw),observed_at=int(time.time()),credential_incarnation=self.credential_incarnation)
    def prepare_post(self):
        self.require()
        if self.credential_instance is None:raise PermissionError('same controlled credential must observe balance first')
        conn,deadline=self._open()
        pending=ControlledNativePending(self,conn,deadline,_factory=_FACTORY)
        self._io[conn]['holder']=pending
        return pending
    def close(self):
        object.__setattr__(self,'active',False);_RESOURCES.pop(self.reference,None)
        self.retire_unhanded()


class ControlledNativePending(_Sealed):
    __slots__=('resource','conn','deadline','identity','pid','reference','active','grant','remaining')
    def __init__(self,resource,conn,deadline,*,_factory=None):
        if _factory is not _FACTORY:raise TypeError('actual controlled pending required')
        self.resource,self.conn,self.deadline,self.identity=resource,conn,deadline,_fd_identity(conn.fileno())[:2]
        self.pid,self.reference,self.active,self.grant,self.remaining=os.getpid(),_uid(),True,None,None;_PENDING[self.reference]=self
    def require(self):
        if not self.active or self.pid!=os.getpid() or _PENDING.get(self.reference) is not self or _fd_identity(self.conn.fileno())[:2]!=self.identity:raise PermissionError('actual controlled pending socket required')
    def write_first(self,capability):
        from .plan_native_runtime import NativePlanSendLease
        self.require()
        if type(capability) is not NativePlanSendLease or self.grant is not None:raise PermissionError('actual native first-write lease required')
        if purpose_scope(self.resource)=='evidence_method_plan_v1':
            from .evidence_method_plan_codec import decode_request
            descriptor=capability.inspect_payload(self.resource)
            decode_request(descriptor.raw,descriptor.domain,descriptor.exact_input,descriptor.selection_manifest)
            consumed=capability.consume(self.resource)
            if consumed!=descriptor:raise PermissionError('inspected evidence payload changed before consume')
            raw,dispatch,nonce,admission_digest,producer_digest=consumed.raw,consumed.dispatch_id,consumed.nonce,consumed.admission_digest,consumed.producer_digest
        else:raw,dispatch,nonce,admission_digest,producer_digest=capability.consume(self.resource)
        data=self.resource._bytes('POST','/chat/completions',raw)
        if time.monotonic()>=self.deadline:raise TimeoutError('controlled native wall limit')
        count=self.conn.send(data)
        if count<=0:raise OSError('controlled native first-write failed')
        object.__setattr__(self,'grant',(dispatch,nonce,admission_digest,producer_digest));object.__setattr__(self,'remaining',data[count:])
    def receive(self):
        self.require()
        if self.grant is None:raise PermissionError('actual first write required')
        # Core owns independent pending.close in its finally, after accepting
        # and committing this owned return. A socket-close error must not
        # replace the handoff or orphan a registered receipt.
        _send_remaining(self.conn,self.deadline,memoryview(self.remaining));status,body=_receive(self.conn,self.deadline)
        dispatch,nonce,admission_digest,producer_digest=self.grant
        return OwnedNativeReturn(_factory=_FACTORY,resource=self.resource,dispatch=dispatch,nonce=nonce,admission_digest=admission_digest,producer_digest=producer_digest,status=status,body=body,mode='controlled_fixture')
    def close(self):
        if self.active:
            object.__setattr__(self,'active',False);_PENDING.pop(self.reference,None)
            self.resource._close_io(self.conn)


def open_controlled_fixture_resource(permit):
    if type(permit) is not NativeRuntimePermit:raise PermissionError('fixed Core runtime permit required')
    return ControlledNativeResource(permit,_factory=_FACTORY)


def open_plan_resource(permit):
    """Fixed Runtime installation seam; no ducktype or mutable registry escape."""
    if type(permit) is not NativeRuntimePermit:raise PermissionError('fixed Core runtime permit required')
    data=permit.data();module=_runtime_module()
    actual=digest(Path(module.__file__).read_bytes())
    if actual!=data['runtime_digest']:raise PermissionError('approved native Runtime code digest differs')
    resource=module.open_plan_resource(permit)
    if type(resource) is not module.NativePlanResource:raise PermissionError('exact canonical Runtime resource required')
    resource.require();return resource


def install_native_funding(store,provision,resource):
    from .paid_control import _owner_binding
    if type(provision) is not NativePlanProvision:raise PermissionError('actual native provision required')
    provision.require();facts=provision.data()
    if type(resource) is ControlledNativeResource:resource.require()
    else:
        module=_runtime_module()
        if type(resource) is not module.NativePlanResource or digest(Path(module.__file__).read_bytes())!=facts['runtime_digest']:raise PermissionError('fixed accepted Runtime module required')
        resource.require()
    expected_producer='core-controlled-native-v1' if type(resource) is ControlledNativeResource else 'owned-native-plan-runtime-v1'
    if resource.permit.provision is not provision or (resource.mode,resource.producer,resource.economic_binding,resource.credential_incarnation)!=(facts['mode'],expected_producer,facts['economic_binding'],facts['credential_incarnation']):raise PermissionError('resource/provision mode/origin pairing differs')
    pid=facts['principal_id']
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        def verify():provision.require();_owner_binding(conn,store,pid,lease)
        verify()
        if conn.execute('SELECT 1 FROM '+FUNDING_TABLE+' LIMIT 1').fetchone():raise ResearchError('LEDGER_BINDING_REQUIRED',409,'原生资金已绑定；不能另建或清零。')
        if conn.execute('SELECT 1 FROM research_funding_accounts LIMIT 1').fetchone():raise ResearchError('LEDGER_BINDING_REQUIRED',409,'现有账本必须由受信原生资源显式接续。')
        # Genesis is explicit native authority and empty finance only. The
        # declaration cap is not a deposit or a cash-balance observation.
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,status,cap) VALUES(?,?,'live','deepseek','CNY','unverified',0)",(facts['account_id'],facts['economic_binding']))
        values={k:facts[k] for k in ('mode','principal_id','generation','owner_gate_id','authority_ref','account_id','economic_binding','credential_incarnation','grant_epoch','approved_cap_units','risk_margin_units','runtime_digest','network_ref')}
        values.update(state='authorized',authority_digest=digest(provision.facts),balance_claim=None,balance_nonce=None,version=1)
        financial._write(conn,lease,FUNDING_TABLE,1,values,verify,_factory=financial._FACTORY)
    _INSTALLATIONS[str(store.path)]=(provision,resource)
    return resource


def installation(store):return _INSTALLATIONS.get(str(store.path))


def retire_installation(store):
    pair=_INSTALLATIONS.pop(str(store.path),None)
    if pair:
        errors=[]
        for item in (pair[1],pair[1].permit,pair[0],pair[0].authority):
            try:item.close()
            except BaseException as error:errors.append(type(error).__name__)
        if errors:raise ResearchError('CLEANUP_UNCERTAIN',503,'原生资源权限已退休，资源关闭仍待核对。')


def retire_attempts(*resources,flight=None):
    """Attempt every retirement; a close failure never skips the next action."""
    errors=[]
    for value in resources:
        if value is None:continue
        try:value.close()
        except BaseException as error:errors.append(type(error).__name__)
    if flight is not None:
        try:flight.release()
        except BaseException as error:errors.append(type(error).__name__)
    return tuple(errors)


# Fixed code origins, captured before test wrappers or caller attribute aliases.
_WRITE_PRODUCERS=(install_native_funding,)
_EVIDENCE_FACTORY_CODES=(create_controlled_evidence_method_fixture_authority.__code__,create_controlled_runtime_evidence_method_fixture_authority.__code__)
