"""Fixed native live control input. Parsed JSON/metadata are never authority.

No import performs IO. The real reader is unreachable before the canonical C
startup scope is validated. Synthetic helpers only validate pure rules and do
not mint witnesses, sessions, credentials, permits, or a network capability.
"""
from dataclasses import dataclass,field
import fcntl
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys
import threading
import types
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .store import ResearchStore
from .errors import ResearchError
from .provider_schemas import canonical,digest

GRANT_PATH=Path('/etc/structural/native-live-grant.json')
FLIGHT_NAME='native-plan-flight.lock'
GRANT_CAP=16384
MAX_INT=9223372036854775807
_FACTORY=object()
_GRANTS={};_FLIGHTS={};_SESSIONS={}
_BOOTSTRAPS={}
SELF='phenomenon_plan_v1'
EVIDENCE='evidence_method_plan_v1'
PURPOSES=(SELF,EVIDENCE)
APPROVED_PATHS=(
 'web/backend/research/plan_native.py','web/backend/research/plan_native_runtime.py',
 'web/backend/research/plan_native_schemas.py','web/backend/research/plan_native_financial.py',
 'web/backend/research/evidence_method_plan.py','web/backend/research/evidence_method_plan_schemas.py',
 'web/backend/research/evidence_method_plan_codec.py','web/backend/services/plan_runtime_transport.py',
 'web/backend/research/native_live_grant.py','web/backend/services/native_live_credentials.py',
 'web/backend/services/native_dns_process.py','web/backend/research/native_plan_supervisor.py',
 'web/backend/main.py','web/backend/services/formal_admission.py','web/backend/research/runtime_profile.py',
 'scripts/run-formal-main.py','web/backend/research/plan_preview_codec.py',
 'web/backend/research/phenomenon_plan.py','web/backend/research/plan_runtime.py',
 'web/backend/research/store.py','web/backend/research/authorization.py','web/backend/services/auth_store.py',
 'web/backend/services/auth_registration.py','web/backend/services/sqlite_utils.py','web/backend/research/source_supervisor.py',
)
FIELDS=frozenset(('protocol','project_ref','state','grant_id','grant_epoch','principal_id',
 'auth_generation','principal_epoch','owner_gate_id','database_identity','owner_gate_identity',
 'flight_identity','account_id','economic_binding','credential_incarnation','approved_cap_units',
 'risk_margin_units','runtime_uid','runtime_gid','provider','model','network_policy','runtime_digest',
 'approved_code_digest','purpose_domains'))


def _closed():return ResearchError('FUNDING_CLOSED',503,'原生资金资源尚未完成受信绑定；账户、资料和合法历史仍可使用。')
def _integer(value,minimum=0,maximum=MAX_INT):
    if type(value) is not int or not minimum<=value<=maximum:raise ValueError('bounded exact integer required')
    return value

def _uuid(value):
    if type(value) is not str or re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',value) is None:raise ValueError('canonical UUID4 required')
    return value

def _ref(value):
    if type(value) is not str or re.fullmatch(r'[A-Za-z0-9._:-]{1,100}',value) is None:raise ValueError('bounded reference required')
    return value

def _hash(value,length=64):
    if type(value) is not str or re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is None:raise ValueError('exact digest/generation required')
    return value


def fixed_purpose_domains():
    from . import plan_preview_codec as codec,phenomenon_plan as parser
    from .plan_native import _evidence_purpose_domain
    first=dict(purpose=SELF,input_template=parser.INPUT_TEMPLATE,candidate_schema=parser.CANDIDATE_SCHEMA,
        result_schema='owned-native-plan-result-v2',codec_revision=codec.CODEC_REVISION,
        template_digest=codec.template_digest(),provider='deepseek',model='deepseek-flash',method='POST',
        target='https://api.deepseek.com/chat/completions')
    return [first,_evidence_purpose_domain()]


@dataclass(frozen=True,slots=True)
class NativeLiveGrantData:
    """Pure validated content, never accepted in place of a witness."""
    encoded:bytes=field(repr=False)
    def data(self):return json.loads(self.encoded)


def decode_grant(raw):
    if type(raw) is not bytes or not 0<len(raw)<=GRANT_CAP:raise ValueError('bounded grant input required')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate grant field')
            result[key]=value
        return result
    def number(text):
        if len(text)>19:raise ValueError('bounded grant integer required')
        return _integer(int(text))
    def invalid(_):raise ValueError('integer-only grant data required')
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_int=number,parse_float=invalid,parse_constant=invalid)
    except (UnicodeError,RecursionError):raise ValueError('strict grant JSON required') from None
    stack=[(value,0)];nodes=0
    while stack:
        item,depth=stack.pop();nodes+=1
        if depth>12 or nodes>512:raise ValueError('bounded grant structure required')
        if type(item) is dict:stack.extend((x,depth+1) for x in item.values())
        elif type(item) is list:stack.extend((x,depth+1) for x in item)
    if type(value) is not dict or set(value)!=FIELDS:raise ValueError('exact grant fields required')
    fixed={'protocol':'native-live-owner-grant-v1','project_ref':'structure-rebuild-v1',
        'approved_cap_units':300000000,'risk_margin_units':2129920,'provider':'deepseek',
        'model':'deepseek-flash','network_policy':'deepseek-fixed-https-v1'}
    for key,expected in fixed.items():
        if type(value[key]) is not type(expected) or value[key]!=expected:raise ValueError('fixed grant policy differs')
    if value['state'] not in ('active','revoke_requested') or type(value['state']) is not str:raise ValueError('fixed grant state required')
    for key in ('grant_id','principal_id','owner_gate_id','account_id'):_uuid(value[key])
    for key in ('economic_binding','credential_incarnation'):_ref(value[key])
    for key in ('grant_epoch','principal_epoch'):_integer(value[key],1,2147483647)
    for key in ('runtime_uid','runtime_gid'):_integer(value[key],0,2147483647)
    _hash(value['auth_generation'],32)
    for key in ('runtime_digest','approved_code_digest'):_hash(value[key])
    for key,length in (('database_identity',2),('owner_gate_identity',5),('flight_identity',6)):
        identity=value[key]
        if type(identity) is not list or len(identity)!=length:raise ValueError('exact native identity required')
        for item in identity:_integer(item)
        if identity[1]<1:raise ValueError('actual native inode required')
    if value['owner_gate_identity'][2:]!=[value['runtime_uid'],0o600,1] or value['flight_identity'][2:]!=[value['runtime_uid'],value['runtime_gid'],0o600,1]:raise ValueError('native gate/flight metadata differs')
    if type(value['purpose_domains']) is not list or value['purpose_domains']!=fixed_purpose_domains():raise ValueError('exact ordered two-purpose domains required')
    return NativeLiveGrantData(canonical(value))


@dataclass(frozen=True,slots=True)
class FileMetadata:
    dev:int;ino:int;uid:int;gid:int;mode:int;nlink:int;kind:int;size:int;mtime_ns:int;ctime_ns:int
    @classmethod
    def from_stat(cls,info):
        return cls(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),
            info.st_nlink,stat.S_IFMT(info.st_mode),info.st_size,info.st_mtime_ns,info.st_ctime_ns)
    @property
    def identity(self):return (self.dev,self.ino,self.uid,self.gid,self.mode,self.nlink)


def validate_control_metadata(chain,leaf,*,runtime_uid,runtime_gid):
    """Pure metadata predicate; no FD/context/witness is accepted or returned."""
    _integer(runtime_uid,1,2147483647);_integer(runtime_gid,0,2147483647)
    if type(chain) is not tuple or len(chain)!=3 or any(type(x) is not FileMetadata for x in (*chain,leaf)):raise ValueError('fixed control walk metadata required')
    for info in (*chain,leaf):
        for value in (info.dev,info.ino,info.uid,info.gid,info.mode,info.nlink,info.kind,info.size,info.mtime_ns,info.ctime_ns):_integer(value)
        if not info.ino or not info.nlink:raise ValueError('actual control resource required')
    for info in chain:
        if info.kind!=stat.S_IFDIR or info.uid!=0 or info.mode&0o022 or info.uid==runtime_uid and info.mode&0o200:raise ValueError('root-owned non-service-writable parent required')
    if (chain[-1].gid,chain[-1].mode)!=(runtime_gid,0o750):raise ValueError('fixed grant directory mode/group required')
    if (leaf.kind,leaf.uid,leaf.gid,leaf.mode,leaf.nlink)!=(stat.S_IFREG,0,runtime_gid,0o440,1) or not 0<leaf.size<=GRANT_CAP:raise ValueError('fixed grant file metadata required')


def _research_family():
    if __package__ not in ('research','web.backend.research'):raise _closed()
    return __package__


def _canonical_module(name,relative,functions,classes):
    try:module=importlib.import_module(name)
    except (ImportError,ModuleNotFoundError):raise _closed() from None
    expected=Path(__file__).resolve().parents[1]/relative
    if Path(module.__file__).resolve()!=expected or Path(module.__file__).is_symlink():raise _closed()
    raw=expected.read_bytes();compiled=compile(raw,str(expected),'exec')
    codes={v.co_name:v for v in compiled.co_consts if type(v) is types.CodeType}
    for key in functions:
        function=getattr(module,key,None)
        if type(function) is not types.FunctionType or function.__globals__ is not vars(module) or function.__code__!=codes.get(key):raise _closed()
    for key in classes:
        kind=getattr(module,key,None);source=codes.get(key)
        if type(kind) is not type or kind.__module__!=name or kind.__name__!=key or source is None:raise _closed()
        for code in (item for item in source.co_consts if type(item) is types.CodeType and not item.co_name.startswith('<')):
            method=vars(kind).get(code.co_name)
            if type(method) in (staticmethod,classmethod):method=method.__func__
            if type(method) is property:method=method.fget
            if type(method) is not types.FunctionType or method.__globals__ is not vars(module) or method.__code__!=code:raise _closed()
    return module


def _c_module():
    return _canonical_module(_research_family()+'.native_plan_supervisor',Path('research/native_plan_supervisor.py'),
        ('require_startup_scope','require_lifecycle_scope','require_slot','require_worker','require_worker_retired','bounded_revoke_transaction','request_session_stop'),
        ('MainStartupScope','NativeLifecycleScope','NativePlanSlotLease','NativePlanWorkerLease','BoundedRevokeTransaction'))


def _b_module():
    family='web.backend.services' if _research_family()=='web.backend.research' else 'services'
    return _canonical_module(family+'.native_live_credentials',Path('services/native_live_credentials.py'),
        ('load_native_live_credential',),('NativeLiveCredential',))


def _startup(scope,store,session=None):
    from .store import ResearchStore
    module=_c_module()
    if type(store) is not ResearchStore or store.storage_identity is None or type(scope) is not module.MainStartupScope:raise _closed()
    if module.require_startup_scope(scope,store,session=session) is not None:raise _closed()
    return module


def _lifecycle(scope,store,session,action):
    module=_c_module()
    if action not in ('revoke','retire','recover') or type(scope) is not module.NativeLifecycleScope:raise _closed()
    if module.require_lifecycle_scope(scope,store,session,action=action) is not None:raise _closed()
    return module


def require_slot(scope,store,session,*,task_id,purpose,mode):
    module=_c_module()
    if purpose not in PURPOSES or mode not in ('execute','cleanup') or type(scope) is not module.NativePlanSlotLease:raise _closed()
    if module.require_slot(scope,store,session,task_id=task_id,purpose=purpose,mode=mode) is not None:raise _closed()


def approved_code_digest():
    """Fixed bounded 25-file closure; no caller paths or directory traversal."""
    root=Path(__file__).resolve().parents[3];files={};total=0
    try:
        for relative in APPROVED_PATHS:
            path=root/relative
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent!=root and root in parent.parents):raise _closed()
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
            try:
                before=FileMetadata.from_stat(os.fstat(fd))
                if before.kind!=stat.S_IFREG or not 0<before.size<=262144:raise _closed()
                with os.fdopen(os.dup(fd),'rb') as stream:raw=stream.read(262145)
                if len(raw)!=before.size or FileMetadata.from_stat(os.fstat(fd))!=before or FileMetadata.from_stat(path.lstat())!=before:raise _closed()
            finally:os.close(fd)
            total+=len(raw)
            if total>2097152:raise _closed()
            files[relative]=digest(raw)
    except OSError:raise _closed() from None
    return digest(canonical(files))


def _require_auth(store,value):
    from .store import ResearchStore
    if type(store) is not ResearchStore or store.storage_identity is None or tuple(store.storage_identity)!=tuple(value['database_identity']):raise _closed()
    if (os.geteuid(),os.getegid())!=(value['runtime_uid'],value['runtime_gid']):raise _closed()
    with store.transaction() as conn:
        if getattr(conn,'private_storage_identity',None)!=store.storage_identity or conn.execute('SELECT version FROM research_schema').fetchone()[0]!=15:raise _closed()
        principal=conn.execute('SELECT * FROM research_principals WHERE id=?',(value['principal_id'],)).fetchone()
        if not principal or (principal['status'],principal['session_generation'],principal['epoch'],principal['gate_id'])!=('active',value['auth_generation'],value['principal_epoch'],value['owner_gate_id']):raise _closed()
        user=conn.execute('SELECT session_generation,lifecycle FROM auth_users WHERE email=?',(principal['normalized_email'],)).fetchone()
        if not user or tuple(user)!= (value['auth_generation'],'active'):raise _closed()
        receipt=conn.execute("SELECT lock_dev,lock_ino,database_binding FROM auth_registration_receipts WHERE gate_id=? AND kind='gate_resource'",(value['owner_gate_id'],)).fetchone()
        if not receipt or (receipt['lock_dev'],receipt['lock_ino'])!=tuple(value['owner_gate_identity'][:2]) or receipt['database_binding']!=digest(canonical(list(store.storage_identity))):raise _closed()
        if store.auth_store.expected_owner_gate_identity(value['owner_gate_id'])!=tuple(value['owner_gate_identity'][:2]):raise _closed()
    path=store.path.parent/'research-locks'/(value['owner_gate_id']+'.lock')
    info=path.lstat()
    actual=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)
    if not stat.S_ISREG(info.st_mode) or actual!=tuple(value['owner_gate_identity']):raise _closed()


def _birth(factory,function):
    frame=inspect.currentframe().f_back.f_back
    try:
        names=function if type(function) is tuple else (function,)
        if factory is not _FACTORY or frame.f_globals is not globals() or frame.f_code not in tuple(_BIRTH_CODES[name] for name in names):raise TypeError('fixed native resource birth required')
    finally:del frame


def _close_all(resources):
    """Attempt every owned resource. Return errors, never invent a close proof."""
    errors=[]
    for resource in resources:
        if resource is None:continue
        try:resource.close()
        except BaseException as error:errors.append(type(error).__name__)
    return tuple(errors)


def _close_fd(fd,identity):
    if fd is None:return
    info=os.fstat(fd)
    if (info.st_dev,info.st_ino)!=identity:raise RuntimeError('owned native descriptor identity changed')
    os.close(fd)


class _Sealed:
    __slots__=()
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('native live resource immutable')
        object.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native live resource is not serializable')


class NativeLiveStartFailure(RuntimeError):
    """Actual partial resources stay owned; the caller must retain this handle."""
    def __init__(self,handle,resources,*,uncertain):
        super().__init__('native live start incomplete')
        self.handle,self.resources,self.uncertain=handle,tuple(resources),bool(uncertain)
    def __setattr__(self,name,value):_Sealed.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native partial start is not serializable')


class NativeLiveGrantWitness(_Sealed):
    __slots__=('store','_data','_fd','_directories','_metadata','_raw_digest','pid','uid','reference','closed','uncertain')
    def __init__(self,store,data,fd,directories,metadata,raw_digest,*,_factory=None):
        _birth(_factory,'read_native_live_grant')
        self.store,self._data,self._fd,self._directories,self._metadata=store,data,fd,tuple(directories),metadata
        self._raw_digest=raw_digest
        self.pid,self.uid,self.reference,self.closed,self.uncertain=os.getpid(),os.geteuid(),object(),False,False
        _GRANTS[self.reference]=self
    def __repr__(self):return '<NativeLiveGrantWitness redacted>'
    def __reduce__(self):raise TypeError('native grant witness is not serializable')
    def _identity(self):
        if self.pid!=os.getpid() or self.uid!=os.geteuid() or _GRANTS.get(self.reference) is not self:raise _closed()
    def _current(self):
        self._identity()
        if self.closed or self.uncertain or self._fd is None:raise _closed()
        value=self._data.data()
        if value['state']!='active':raise _closed()
        actual=tuple(FileMetadata.from_stat(os.fstat(fd)) for fd,_ in self._directories)
        if actual!=tuple(meta for _,meta in self._directories):raise _closed()
        for (parent,_),(child,meta),name in zip(self._directories,self._directories[1:],('etc','structural')):
            if FileMetadata.from_stat(os.stat(name,dir_fd=parent,follow_symlinks=False))!=meta:raise _closed()
        before=FileMetadata.from_stat(os.fstat(self._fd));named=FileMetadata.from_stat(os.stat('native-live-grant.json',dir_fd=self._directories[-1][0],follow_symlinks=False))
        validate_control_metadata(actual,before,runtime_uid=value['runtime_uid'],runtime_gid=value['runtime_gid'])
        if before!=self._metadata or named!=before:raise _closed()
        os.lseek(self._fd,0,os.SEEK_SET);raw=os.read(self._fd,GRANT_CAP+1)
        if len(raw)!=before.size or FileMetadata.from_stat(os.fstat(self._fd))!=before or digest(raw)!=self._raw_digest or decode_grant(raw).encoded!=self._data.encoded:raise _closed()
        _require_auth(self.store,value)
        if approved_code_digest()!=value['approved_code_digest']:raise _closed()
    def require_bootstrap(self,startup_scope):
        _startup(startup_scope,self.store);self._current()
    def data_bootstrap(self,startup_scope):
        self.require_bootstrap(startup_scope);return self._data.data()
    def require_past(self):
        # Called only after a session has validated the actual original C scope.
        self._identity()
        if self._fd is not None:
            info=os.fstat(self._fd)
            if (info.st_dev,info.st_ino)!=(self._metadata.dev,self._metadata.ino):raise _closed()
        if self.uncertain:raise _closed()
    def close(self):
        self._identity();errors=[]
        if self._fd is not None:
            try:_close_fd(self._fd,(self._metadata.dev,self._metadata.ino));object.__setattr__(self,'_fd',None)
            except BaseException as error:errors.append(type(error).__name__)
        remaining=[]
        for fd,meta in reversed(self._directories):
            try:_close_fd(fd,(meta.dev,meta.ino))
            except BaseException as error:errors.append(type(error).__name__);remaining.append((fd,meta))
        object.__setattr__(self,'_directories',tuple(reversed(remaining)));object.__setattr__(self,'closed',not errors)
        if errors:object.__setattr__(self,'uncertain',True);raise ResearchError('CLEANUP_UNCERTAIN',503,'原生控制文件资源关闭尚待核对。')


class _ControlReadHandle(_Sealed):
    """Only the fixed grant/flight readers' unpublished descriptors, no authority."""
    __slots__=('pid','fds','errors','closed')
    def __init__(self,*,_factory=None):
        _birth(_factory,('read_native_live_grant','claim_live_flight'))
        self.pid,self.fds,self.errors,self.closed=os.getpid(),(),(),False
    def _caller(self):
        frame=inspect.currentframe().f_back.f_back
        try:
            if self.pid!=os.getpid() or frame.f_globals is not globals() or frame.f_code not in (_BIRTH_CODES['read_native_live_grant'],_BIRTH_CODES['claim_live_flight']):raise _closed()
        finally:del frame
    def open(self,path,flags,*,dir_fd=None):
        self._caller()
        fd=os.open(path,flags,dir_fd=dir_fd)
        # Record allocation before fstat itself can fail.
        object.__setattr__(self,'fds',self.fds+((fd,None),))
        metadata=FileMetadata.from_stat(os.fstat(fd))
        object.__setattr__(self,'fds',self.fds[:-1]+((fd,metadata),))
        return fd,metadata
    def close_parent(self,fd):
        self._caller()
        pair=next((pair for pair in self.fds if pair[0]==fd),None)
        if pair is None or pair[1] is None:raise _closed()
        try:_close_fd(fd,(pair[1].dev,pair[1].ino))
        except BaseException as error:
            object.__setattr__(self,'errors',self.errors+(type(error).__name__,));raise
        object.__setattr__(self,'fds',tuple(pair for pair in self.fds if pair[0]!=fd))
    def transfer_flight(self,lease):
        self._caller()
        if type(lease) is not NativeLiveFlightLease or _FLIGHTS.get(lease.reference) is not lease or self.fds!=((lease.fd,lease.metadata),):raise _closed()
        object.__setattr__(self,'fds',());object.__setattr__(self,'closed',True)
    def transfer(self,witness):
        self._caller()
        if type(witness) is not NativeLiveGrantWitness or _GRANTS.get(witness.reference) is not witness or tuple((fd,meta) for fd,meta in self.fds)!=(*witness._directories,(witness._fd,witness._metadata)):raise _closed()
        object.__setattr__(self,'fds',());object.__setattr__(self,'closed',True)
    def close(self):
        if self.pid!=os.getpid():raise _closed()
        remaining=[];errors=[]
        for fd,meta in reversed(self.fds):
            try:
                if meta is None:os.close(fd)
                else:_close_fd(fd,(meta.dev,meta.ino))
            except BaseException as error:remaining.append((fd,meta));errors.append(type(error).__name__)
        object.__setattr__(self,'fds',tuple(reversed(remaining)));object.__setattr__(self,'errors',self.errors+tuple(errors))
        if self.errors:raise ResearchError('CLEANUP_UNCERTAIN',503,'原生控制读取的部分资源尚待核对。')
        object.__setattr__(self,'closed',True)


def read_native_live_grant(store,*,main_context):
    _startup(main_context,store)  # Must happen before any control-file access.
    _b_module()  # Module presence is not key access or a credential.
    if sys.platform!='linux' or not hasattr(os,'O_NOFOLLOW'):raise _closed()
    if str(store.path) in _BOOTSTRAPS or any(value.store.path==store.path and not value.closed for value in _GRANTS.values()):raise _closed()
    io=_ControlReadHandle(_factory=_FACTORY);directories=[];result=None
    try:
        current,metadata=io.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        directories.append((current,metadata))
        for part in ('etc','structural'):
            child,metadata=io.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=current)
            directories.append((child,metadata))
            if FileMetadata.from_stat(os.stat(part,dir_fd=current,follow_symlinks=False))!=metadata:raise _closed()
            current=child
        fd,before=io.open('native-live-grant.json',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=current)
        if before.kind!=stat.S_IFREG or not 0<before.size<=GRANT_CAP:raise _closed()
        raw=os.read(fd,GRANT_CAP+1);after=FileMetadata.from_stat(os.fstat(fd))
        if len(raw)!=before.size or after!=before or FileMetadata.from_stat(os.stat('native-live-grant.json',dir_fd=current,follow_symlinks=False))!=before:raise _closed()
        data=decode_grant(raw);value=data.data()
        validate_control_metadata(tuple(meta for _,meta in directories),before,runtime_uid=value['runtime_uid'],runtime_gid=value['runtime_gid'])
        _require_auth(store,value)
        if approved_code_digest()!=value['approved_code_digest']:raise _closed()
        result=NativeLiveGrantWitness(store,data,fd,directories,before,digest(raw),_factory=_FACTORY)
        io.transfer(result)
        result.require_bootstrap(main_context);return result
    except BaseException as primary:
        if result is not None:
            owned={fd for fd,_ in (*result._directories,(result._fd,result._metadata))}
            object.__setattr__(io,'fds',tuple(pair for pair in io.fds if pair[0] not in owned))
            errors=_close_all((result,io))
            raise NativeLiveStartFailure(result,(result,io),uncertain=bool(errors)) from primary
        errors=_close_all((io,))
        if errors:raise NativeLiveStartFailure(io,(io,),uncertain=True) from primary
        raise


class NativeLiveFlightLease(_Sealed):
    __slots__=('store','grant','fd','metadata','pid','uid','reference','active','uncertain','session')
    def __init__(self,store,grant,fd,metadata,*,_factory=None):
        _birth(_factory,'claim_live_flight')
        self.store,self.grant,self.fd,self.metadata=store,grant,fd,metadata
        self.pid,self.uid,self.reference,self.active,self.uncertain,self.session=os.getpid(),os.geteuid(),object(),True,False,None
        _FLIGHTS[self.reference]=self
    def __repr__(self):return '<NativeLiveFlightLease redacted>'
    def __reduce__(self):raise TypeError('native flight lease is not serializable')
    def require_bootstrap(self,startup_scope):
        _startup(startup_scope,self.store,session=self.session);self.grant.require_bootstrap(startup_scope);self._held()
    def _held(self):
        if not self.active or self.uncertain or self.pid!=os.getpid() or self.uid!=os.geteuid() or _FLIGHTS.get(self.reference) is not self:raise _closed()
        held=FileMetadata.from_stat(os.fstat(self.fd));named=FileMetadata.from_stat((self.store.path.parent/FLIGHT_NAME).lstat())
        if held.identity!=self.metadata.identity or named.identity!=held.identity or held.kind!=stat.S_IFREG:raise _closed()
    def close(self):
        if not self.active:return
        if self.pid!=os.getpid() or _FLIGHTS.get(self.reference) is not self:raise _closed()
        if self.session is not None:self.session._require_flight_retirement()
        try:_close_fd(self.fd,(self.metadata.dev,self.metadata.ino))
        except BaseException:object.__setattr__(self,'uncertain',True);raise
        object.__setattr__(self,'active',False);object.__setattr__(self,'fd',None);_FLIGHTS.pop(self.reference,None)


def claim_live_flight(store,grant,*,main_context):
    _startup(main_context,store)
    if type(grant) is not NativeLiveGrantWitness or grant.store is not store:raise _closed()
    grant.require_bootstrap(main_context);value=grant.data_bootstrap(main_context)
    io=_ControlReadHandle(_factory=_FACTORY);lease=None
    try:
        parent,_=io.open(store.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        fd,before=io.open(FLIGHT_NAME,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
        named=FileMetadata.from_stat(os.stat(FLIGHT_NAME,dir_fd=parent,follow_symlinks=False))
        if before.kind!=stat.S_IFREG or before.identity!=tuple(value['flight_identity']) or named.identity!=before.identity:raise _closed()
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise _closed() from None
        after=FileMetadata.from_stat(os.fstat(fd));named=FileMetadata.from_stat(os.stat(FLIGHT_NAME,dir_fd=parent,follow_symlinks=False))
        if after.identity!=before.identity or named.identity!=after.identity:raise _closed()
        io.close_parent(parent)
        lease=NativeLiveFlightLease(store,grant,fd,after,_factory=_FACTORY)
        io.transfer_flight(lease)
        return lease
    except BaseException as primary:
        if lease is not None:
            object.__setattr__(io,'fds',tuple(pair for pair in io.fds if pair[0]!=lease.fd))
            errors=_close_all((lease,io))
            raise NativeLiveStartFailure(lease,(lease,io),uncertain=bool(errors)) from primary
        errors=_close_all((io,))
        if errors:raise NativeLiveStartFailure(io,(io,),uncertain=True) from primary
        raise


def _c_caller(module):
    """A scope and an actual frame of the installed canonical C are required."""
    frame=inspect.currentframe().f_back
    compiled=compile(Path(module.__file__).read_bytes(),str(Path(module.__file__).resolve()),'exec')
    codes={value for value in compiled.co_consts if type(value) is types.CodeType}
    functions=tuple(value for value in vars(module).values() if type(value) is types.FunctionType and value.__globals__ is vars(module) and value.__code__ in codes)
    try:
        while frame is not None:
            if frame.f_globals is vars(module) and any(frame.f_code is value.__code__ for value in functions):return
            frame=frame.f_back
        raise _closed()
    finally:del frame


def stable_facts(data,continuity):
    """Pure deterministic mapping. Its bytes are not a funding authority."""
    if type(data) is not NativeLiveGrantData:raise ValueError('validated grant content required')
    data=decode_grant(data.encoded);value=data.data();_hash(continuity)
    if value['state']!='active':raise ValueError('active birth grant required')
    facts=dict(version='native-owner-provision-v1',mode='native_live',principal_id=value['principal_id'],
        generation=value['auth_generation'],owner_gate_id=value['owner_gate_id'],authority_ref=value['grant_id'],
        account_id=value['account_id'],economic_binding=value['economic_binding'],credential_incarnation=value['credential_incarnation'],
        grant_epoch=value['grant_epoch'],approved_cap_units=value['approved_cap_units'],risk_margin_units=value['risk_margin_units'],
        runtime_digest=value['runtime_digest'],network_ref=value['network_policy'],grant=value,credential_continuity=continuity)
    raw=canonical(facts)
    if len(raw)>16384:raise ValueError('common stable facts exceed bound')
    return raw


_FUNDING_FIELDS=('mode','principal_id','generation','owner_gate_id','authority_ref','account_id','economic_binding',
    'credential_incarnation','grant_epoch','approved_cap_units','risk_margin_units','runtime_digest','network_ref')


def require_funding_snapshot(conn,facts_bytes,*,allow_blocked=False):
    """Read-only exact resume check. No account adoption or financial writes."""
    facts=json.loads(facts_bytes)
    try:
        checked=decode_grant(canonical(facts['grant']))
        if stable_facts(checked,facts['credential_continuity'])!=facts_bytes:raise _closed()
    except (KeyError,ValueError,TypeError):raise _closed() from None
    funding=conn.execute('SELECT * FROM research_plan_native_funding WHERE id=1').fetchone()
    if not funding:raise _closed()
    retired=allow_blocked and funding['state']=='retired' and funding['principal_id'] is None and funding['generation'] is None
    fields=tuple(key for key in _FUNDING_FIELDS if not retired or key not in ('principal_id','generation'))
    if any(funding[key]!=facts[key] for key in fields) or funding['authority_digest']!=digest(facts_bytes):raise _closed()
    if funding['state'] not in (('authorized','blocked','retired') if allow_blocked else ('authorized',)):raise _closed()
    account=conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(facts['account_id'],)).fetchone()
    if not account or (account['binding_id'],account['mode'],account['provider'],account['currency'],account['status'],account['cap'])!=(facts['economic_binding'],'live','deepseek','CNY','unverified',0):raise _closed()
    return funding,account


class NativeLiveSession(_Sealed):
    __slots__=('store','grant','flight','credential','startup_scope','facts','pid','uid','reference','state','thread_flight',
        'authority','provision','resources','permits','worker','recovery_complete','lifecycle_scope','uncertainty','birth_resources','_c','_stop_hint','_stop_code')
    def __init__(self,store,grant,flight,credential,startup_scope,facts,c_module,*,_factory=None):
        _birth(_factory,'bind_live_authority')
        self.store,self.grant,self.flight,self.credential,self.startup_scope,self.facts=store,grant,flight,credential,startup_scope,facts
        self.pid,self.uid,self.reference,self.state=os.getpid(),os.geteuid(),object(),'starting'
        self.thread_flight=threading.Lock();self.authority=self.provision=self.worker=self.lifecycle_scope=None
        self.resources=();self.permits=();self.birth_resources=(grant,flight,credential)
        self.recovery_complete=False;self.uncertainty=()
        self._c,self._stop_hint,self._stop_code=c_module,c_module.request_session_stop,c_module.request_session_stop.__code__
        _SESSIONS[self.reference]=self
    def __repr__(self):return '<NativeLiveSession redacted>'
    def _identity(self):
        if self.pid!=os.getpid() or self.uid!=os.geteuid() or _SESSIONS.get(self.reference) is not self:raise _closed()
    def _request_stop(self):
        # Native function/source identity was proven at birth. This hint path
        # performs memory checks only; subsequent scope checks remain full.
        self._identity()
        try:
            if self._stop_hint is not self._c.request_session_stop or self._stop_hint.__code__ is not self._stop_code or self._stop_hint.__globals__ is not vars(self._c):raise _closed()
            if self._stop_hint(self) is not None:raise _closed()
        except BaseException as error:
            object.__setattr__(self,'uncertainty',self.uncertainty+('stop_hint_'+type(error).__name__,))
            raise ResearchError('CLEANUP_UNCERTAIN',503,'原生停止提示未被受信监督器确认；保留原句柄和债务。') from None
    def require_bootstrap(self,startup_scope):
        self._identity();_startup(startup_scope,self.store,self)
        if startup_scope is not self.startup_scope or self.state!='starting' or self.uncertainty:raise _closed()
        self.grant.require_bootstrap(startup_scope);self.flight._held()
        self.credential.require_bootstrap(self.grant,self.flight,main_context=startup_scope)
    def data_bootstrap(self,startup_scope):
        self.require_bootstrap(startup_scope);return json.loads(self.facts)
    def require(self):
        self._identity()
        if self.state!='executable' or self.uncertainty:raise _closed()
        try:
            self.grant._current();self.flight._held();self.credential.require_current(self)
            with self.store.transaction() as conn:require_funding_snapshot(conn,self.facts)
        except BaseException:
            object.__setattr__(self,'state','cleanup_only')
            try:self._request_stop()
            except BaseException:pass  # Keep the intrinsic failure and sticky physical uncertainty.
            raise
        if self.state!='executable':raise _closed()
    def require_past(self,scope):
        self._identity();module=_c_module()
        if self.state not in ('starting','executable','cleanup_only','uncertain'):raise _closed()
        if type(scope) is module.NativePlanSlotLease:
            require_slot(scope,self.store,self,task_id=scope.task_id,purpose=scope.purpose,mode='cleanup')
        elif type(scope) is module.NativeLifecycleScope:
            if scope.action not in ('retire','recover','revoke'):raise _closed()
            _lifecycle(scope,self.store,self,scope.action)
        else:raise _closed()
        self.grant.require_past();self.flight._held();self.credential.require_past(self,scope)
    def retire(self,*,lifecycle_scope):
        self._identity();_lifecycle(lifecycle_scope,self.store,self,'retire')
        object.__setattr__(self,'state','cleanup_only');object.__setattr__(self,'lifecycle_scope',lifecycle_scope)
        self._request_stop()
    def _require_flight_retirement(self):
        self._identity();module=_lifecycle(self.lifecycle_scope,self.store,self,'retire')
        if module.require_worker_retired(self.worker,self.store,self,lifecycle_scope=self.lifecycle_scope) is not None:raise _closed()
        if self.uncertainty:raise _closed()
    def close(self):
        self._identity()
        if self.state=='closed':return
        object.__setattr__(self,'state','cleanup_only')
        # Resource/key retirement is attempted even if stop/retirement fails.
        errors=()
        try:self._request_stop()
        except BaseException as error:errors+=(type(error).__name__,)
        errors+=_close_all((*reversed(self.resources),self.credential))
        retired=False
        try:self._require_flight_retirement();retired=True
        except BaseException as error:errors+=('worker_retirement_'+type(error).__name__,)
        # Keep the A past chain alive while a real worker might still book its
        # original OwnedReturn. cleanup_only already denies all new sends.
        if retired:errors+=_close_all((*reversed(self.permits),self.provision,self.authority))
        if errors:
            object.__setattr__(self,'uncertainty',self.uncertainty+errors);object.__setattr__(self,'state','uncertain')
            raise ResearchError('CLEANUP_UNCERTAIN',503,'原生资源关闭尚未证明；保留原句柄、资金锁和债务。')
        errors=_close_all((self.flight,self.grant))
        if errors:
            object.__setattr__(self,'uncertainty',self.uncertainty+errors);object.__setattr__(self,'state','uncertain')
            raise ResearchError('CLEANUP_UNCERTAIN',503,'原生资源关闭尚未证明；保留原句柄和债务。')
        object.__setattr__(self,'state','closed');_BOOTSTRAPS.pop(str(self.store.path),None)


def bind_live_authority(store,grant,flight,credential,*,main_context):
    module=_startup(main_context,store);_c_caller(module)
    if type(grant) is not NativeLiveGrantWitness or type(flight) is not NativeLiveFlightLease or grant.store is not store or flight.store is not store or flight.grant is not grant:raise _closed()
    if str(store.path) in _BOOTSTRAPS or flight.session is not None:raise _closed()
    grant.require_bootstrap(main_context);flight.require_bootstrap(main_context)
    b=_b_module()
    if type(credential) is not b.NativeLiveCredential:raise _closed()
    credential.require_bootstrap(grant,flight,main_context=main_context)
    continuity=credential.continuity_for_grant(grant,flight,main_context=main_context);_hash(continuity)
    facts=stable_facts(grant._data,continuity)
    session=NativeLiveSession(store,grant,flight,credential,main_context,facts,module,_factory=_FACTORY)
    _BOOTSTRAPS[str(store.path)]=session;object.__setattr__(flight,'session',session)
    try:
        from . import plan_native as ports
        authority=ports._live_authority(session,main_context)
        object.__setattr__(session,'authority',authority)
        provision=ports.issue_native_provision(store,authority,startup_scope=main_context)
        object.__setattr__(session,'provision',provision)
        for purpose in PURPOSES:
            permit=ports.mint_runtime_permit(provision,purpose=purpose,startup_scope=main_context)
            object.__setattr__(session,'permits',(*session.permits,permit))
            resource=ports.open_plan_resource(permit,startup_scope=main_context)
            object.__setattr__(session,'resources',(*session.resources,resource))
        return session
    except BaseException as primary:
        object.__setattr__(session,'state','cleanup_only')
        if type(primary) is NativeLiveStartFailure:
            object.__setattr__(session,'birth_resources',session.birth_resources+primary.resources)
        errors=_close_all((*reversed(session.resources),*reversed(session.permits),session.provision,session.authority,credential,*(primary.resources if type(primary) is NativeLiveStartFailure else ())))
        # C must supply a sealed partial-start retirement proof before release.
        if errors:object.__setattr__(session,'uncertainty',errors);object.__setattr__(session,'state','uncertain')
        raise NativeLiveStartFailure(session,session.birth_resources+session.permits+session.resources,uncertain=True) from primary


def install_live_session(store,session,*,main_context):
    module=_startup(main_context,store,session);_c_caller(module)
    if type(session) is not NativeLiveSession or session.store is not store or len(session.resources)!=2:raise _closed()
    session.require_bootstrap(main_context)
    from . import plan_native as ports
    ports.install_native_funding(store,session.provision,session.resources[0],startup_scope=main_context)
    return session


def recover_live_session(session,*,lifecycle_scope):
    """No rerun: classify all bound rows, including terminal/deleted debt."""
    if type(session) is not NativeLiveSession:raise _closed()
    module=_lifecycle(lifecycle_scope,session.store,session,'recover');_c_caller(module)
    session.require_past(lifecycle_scope)
    from . import plan_native_runtime as runtime,plan_native_financial as finance
    store=session.store;facts=json.loads(session.facts);unresolved=False
    with store.transaction() as conn:
        require_funding_snapshot(conn,session.facts)
        rows=[dict(value) for value in conn.execute('SELECT * FROM research_plan_native_runs WHERE account_id=? ORDER BY id',(facts['account_id'],))]
    for value in rows:
        session.require_past(lifecycle_scope)
        if value['state'] in ('approved','reserved','consumed'):
            try:
                with store.transaction() as conn:
                    current=runtime.row(conn,runtime.RUNS,value['id'])
                    consent,task,_,_=runtime._current(conn,store,current)
                    expected={key:facts[key] for key in ('principal_id','generation','account_id','economic_binding','credential_incarnation','grant_epoch')}
                    expected.update(authority_digest=digest(session.facts),mode='native_live',producer='owned-native-plan-runtime-v1',producer_digest=runtime.code_digest())
                    if any(consent.get(key)!=value for key,value in expected.items()):raise _closed()
                runtime._fail(store,facts['principal_id'],value['id'])
            except BaseException:unresolved=True
        elif value['state']=='unknown' or value['cost_state']=='unknown' or (value['state']=='closed' and value['cost_state']=='held'):unresolved=True
    with store.transaction() as conn:
        funding,_=require_funding_snapshot(conn,session.facts)
        if funding['balance_claim'] is not None or finance.unresolved(conn,facts['account_id']):unresolved=True
    object.__setattr__(session,'recovery_complete',not unresolved)
    if unresolved:raise ResearchError('RECONCILIATION_REQUIRED',409,'原账本仍有未决记录；保留债务且不会重发。')


def activate_live_session(session,*,startup_scope,worker):
    if type(session) is not NativeLiveSession:raise _closed()
    module=_startup(startup_scope,session.store,session);_c_caller(module)
    session.require_bootstrap(startup_scope)
    if not session.recovery_complete or type(worker) is not module.NativePlanWorkerLease:raise _closed()
    object.__setattr__(session,'worker',worker)  # Retain the actual birth handle on activation failure.
    if module.require_worker(worker,session.store,session,startup_scope=startup_scope) is not None:raise _closed()
    from .plan_native_financial import unresolved
    with session.store.transaction() as conn:
        funding,_=require_funding_snapshot(conn,session.facts)
        if funding['balance_claim'] is not None or unresolved(conn,json.loads(session.facts)['account_id']):raise _closed()
    object.__setattr__(session,'state','executable')
    return session


# Original native code identities survive read-only observation wrappers.
_BIRTH_CODES={name:globals()[name].__code__ for name in
    ('read_native_live_grant','claim_live_flight','bind_live_authority')}


def _credential_message(data):
    """Pure HMAC input encoding; not a key, witness or send authority."""
    if type(data) is not NativeLiveGrantData:raise ValueError('validated grant content required')
    value=decode_grant(data.encoded).data()
    if value['state']!='active':raise ValueError('active credential birth grant required')
    return canonical(['native-live-credential-v1',value])


def credential_bootstrap_binding(grant,flight,*,main_context)->tuple['ResearchStore',bytes]:
    """B receives the captured store and exact message only after actual C."""
    if (type(grant) is not NativeLiveGrantWitness or type(flight) is not NativeLiveFlightLease
            or _GRANTS.get(getattr(grant,'reference',None)) is not grant
            or _FLIGHTS.get(getattr(flight,'reference',None)) is not flight):raise _closed()
    store=grant.store;_startup(main_context,store)
    if flight.store is not store or flight.grant is not grant:raise _closed()
    grant.require_bootstrap(main_context);flight.require_bootstrap(main_context)
    return store,_credential_message(grant._data)


def credential_session_binding(session,credential)->bool:
    """Memory-only birth pairing. True grants no current or network rights."""
    if type(session) is not NativeLiveSession or _SESSIONS.get(getattr(session,'reference',None)) is not session:return False
    if session.pid!=os.getpid() or session.uid!=os.geteuid():return False
    return (session.credential is credential and type(session.grant) is NativeLiveGrantWitness
        and type(session.flight) is NativeLiveFlightLease and session.grant.store is session.store
        and session.flight.store is session.store and session.flight.grant is session.grant
        and session.flight.session is session)
