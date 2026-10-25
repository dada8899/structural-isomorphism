"""Native DOC material capture and authenticated read lifetimes.

Approved data alone never creates a Source request or a completion capability.
"""
from contextlib import contextmanager
import inspect
import os
import threading
import datetime
import hashlib
import json
import re
import stat
import time
from dataclasses import asdict

from .errors import ResearchError
from .evidence_schemas import identifier

_READ_FACTORY = object()
_READS = {}


def unavailable():
    return ResearchError('SOURCE_PERMISSION_UNAVAILABLE',503,'官方原始材料准备尚不可用：访问身份与原生获取链尚未接齐。')


APPROVED_ID = 'structure-sec-gfs-rawprep-v1'
APPROVED_DIGEST = '5316357e05d7f4fb7ebaade54a12c52c2beacee9d76c1b10c96530c6b3f34ca0'
POLICY_SHA = 'ea65b7d5385685497fd7bab03ca54715d78937696bcce00975a8b8d44661d4c8'
PROFILE_NAME = 'source-sec-access-profile.json'
EXPECTED_ROOT = '/var/lib/structural-isomorphism'
EXPECTED_UID, EXPECTED_GID = 981, 976
APPROVED_FROM = '2026-10-23T22:24:04Z'
APPROVED_UNTIL = '2026-11-22T22:24:04Z'
MATERIAL_CAP = 32768
_PROFILE_FACTORY = object()
_PROFILES = {}


class MaterialRefused(ValueError):
    pass


def _stamp(value):
    if type(value) is not str or re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z',value) is None:
        raise MaterialRefused('TIMESTAMP_INVALID')
    try:return datetime.datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
    except ValueError:raise MaterialRefused('TIMESTAMP_INVALID') from None


def _user_agent(value):
    pattern = r"StructureResearch/1 [A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?"
    if (type(value) is not str or not 1<=len(value)<=256 or any(not 32<=ord(c)<=126 for c in value)
            or re.fullmatch(pattern,value) is None):raise MaterialRefused('USER_AGENT_INVALID')
    return value


def _rights(expires):
    copy_url='https://www.sec.gov/about/privacy-information#website-dissemination'
    return {'network_get':{'allowed':True,'expires_at':expires,'basis_refs':[
        'https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data',
        'https://www.sec.gov/about/developer-resources',copy_url],'requires_separate_actual_get_go':True},
        'private_cache':{'allowed':True,'expires_at':None,'scope':'complete-http200-private-identity-parser-soft-error-quarantine',
            'basis_refs':[copy_url,'https://www.sec.gov/about/webmaster-frequently-asked-questions'],
            'required_current_checks':['current_acl','protected_anchor','current_purpose'],'non200_body':'never_store','attribution':'recommended'},
        'display_excerpt':{'allowed':False},'provider_input':{'allowed':False},'export':{'allowed':False}}


def material_data(created_at,ua):
    """Codec data only; not a native profile factory or approved test material."""
    from .source_document_raw import catalog,PROFILE_ID
    created=_stamp(created_at);expires=(created+datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'schema':'structure-sec-access-profile-material-v1','classification':'material-only-not-runtime-authority',
        'profile_id':APPROVED_ID,'revision':1,'plan_profile_id':PROFILE_ID,'policy_decision_sha256':POLICY_SHA,
        'created_at':created_at,'operator':{'private_identity_ref':'owner-admin-input-20261020','user_agent':_user_agent(ua)},
        'sender':{'sender_ref':'structure-production-vps-v1','service':'structural-web.service','expected_uid':EXPECTED_UID,
            'expected_gid':EXPECTED_GID,'state_root':EXPECTED_ROOT},
        'network_identity':{'valid_from':created_at,'expires_at':expires},
        'targets':[{'doc_id':t.doc_ref.doc_id,'doc_version':t.doc_ref.doc_version,'semantic_object_id':t.semantic_object_id,
            'role':t.document_role,'host':t.host,'path':t.path} for t in catalog()],'rights':_rights(expires)}


def material_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')


def _strict_equal(left,right):
    if type(left) is not type(right):return False
    if type(left) is dict:return left.keys()==right.keys() and all(_strict_equal(left[k],right[k]) for k in left)
    if type(left) is list:return len(left)==len(right) and all(_strict_equal(a,b) for a,b in zip(left,right))
    return left==right


def validate_material(raw):
    if type(raw) is not bytes or not 1<=len(raw)<=MATERIAL_CAP:raise MaterialRefused('BYTE_LIMIT_OR_TYPE')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise MaterialRefused('DUPLICATE_KEY')
            result[key]=value
        return result
    def number(_):raise MaterialRefused('NONINTEGER_NUMBER')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=number,parse_float=number)
        if type(value) is not dict or type(value.get('operator')) is not dict:raise MaterialRefused('SCHEMA_INVALID')
        expected=material_data(value.get('created_at'),value['operator'].get('user_agent'))
        if not _strict_equal(value,expected):raise MaterialRefused('SCHEMA_OR_FIXED_SCOPE_INVALID')
        if material_bytes(value)!=raw:raise MaterialRefused('NONCANONICAL_ENCODING')
        return value
    except MaterialRefused:raise
    except (UnicodeError,ValueError,TypeError,OverflowError,RecursionError):raise MaterialRefused('JSON_INVALID') from None


def approved_references():
    from .source_document_raw import ProfileRef
    return ProfileRef(id=APPROVED_ID,revision=1,digest=APPROVED_DIGEST),hashlib.sha256(material_bytes(_rights(APPROVED_UNTIL))).hexdigest()


def _profile_metadata(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
        raise MaterialRefused('PROFILE_METADATA_INVALID')
    return info.st_dev,info.st_ino


def _target_matches(binding):
    return (str(binding.roots[0])==EXPECTED_ROOT and os.geteuid()==EXPECTED_UID and os.getegid()==EXPECTED_GID)


class ActualAccessProfile:
    __slots__=('governor','binding','pid','fd','identity','state','errors','_data','_factory','_digest')
    def __new__(cls,*args,**kwargs):
        if cls is not ActualAccessProfile or kwargs.get('_factory') is not _PROFILE_FACTORY:raise PermissionError('native DOC profile factory required')
        return object.__new__(cls)
    def __init__(self,governor,*,_factory=None):
        if inspect.currentframe().f_back.f_code is not attach_access.__code__:raise PermissionError('native DOC profile attachment required')
        self.governor,self.binding,self.pid=governor,governor.binding,os.getpid()
        self.fd=self.identity=self._data=self._digest=None;self.state='OPENING';self.errors=[];self._factory=_factory
        _PROFILES[id(self)]=self
    def __repr__(self):return '<native private DOC access profile>'
    def __reduce__(self):raise TypeError('private DOC profile cannot be serialized')
    def _native(self):
        from . import source_sec_access as sec
        if (type(self) is not ActualAccessProfile or self._factory is not _PROFILE_FACTORY or _PROFILES.get(id(self)) is not self
                or self.pid!=os.getpid() or self.governor.profile is not self or self.binding is not self.governor.binding):
            raise PermissionError('actual DOC profile required')
        sec._identity(self.governor)
        if not _target_matches(self.binding):raise PermissionError('DOC sender target differs')
        return sec._parent(self.governor)
    def check(self,*,network):
        parent=self._native()
        if self.state!='BOUND' or self.fd is None:raise unavailable()
        try:
            if (_profile_metadata(os.fstat(self.fd))!=self.identity
                    or _profile_metadata(os.stat(PROFILE_NAME,dir_fd=parent,follow_symlinks=False))!=self.identity):
                raise PermissionError('DOC profile pathname changed')
            raw=os.pread(self.fd,MATERIAL_CAP+1,0)
            if hashlib.sha256(raw).hexdigest()!=self._digest or self._digest!=APPROVED_DIGEST:
                raise PermissionError('DOC profile bytes changed')
        except BaseException as error:
            self.uncertain(error);raise
        if self.governor.retired and network:raise unavailable()
        if network and not _stamp(self._data['network_identity']['valid_from']).timestamp()<=time.time()<_stamp(self._data['network_identity']['expires_at']).timestamp():raise unavailable()
        return self
    def uncertain(self,error):
        from . import source_sec_access as sec
        self.errors.append(error);self.state='CLEANUP_UNCERTAIN';sec._uncertain(self.governor,error)
    def close(self):
        if self.state=='CLEANUP_UNCERTAIN':return False
        if self.fd is not None:
            try:os.close(self.fd)
            except BaseException as error:self.uncertain(error);return False
            self.fd=None
        self._data=None;self.state='CLOSED';_PROFILES.pop(id(self),None)
        return True


def attach_access(governor=None,*args,**kwargs):
    if args or kwargs:raise PermissionError('canonical governor attachment required')
    from . import source_sec_access as sec
    caller=inspect.currentframe().f_back
    if caller.f_code is not sec.attach.__code__ or caller.f_globals is not vars(sec):raise PermissionError('canonical governor attachment required')
    sec._identity(governor)
    if not _target_matches(governor.binding):return None
    profile=ActualAccessProfile(governor,_factory=_PROFILE_FACTORY);governor.profile=profile
    try:
        parent=sec._parent(governor)
        profile.fd=os.open(PROFILE_NAME,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent)
        profile.identity=_profile_metadata(os.fstat(profile.fd))
        if _profile_metadata(os.stat(PROFILE_NAME,dir_fd=parent,follow_symlinks=False))!=profile.identity:
            profile.uncertain(RuntimeError('DOC profile replaced during capture'));return profile
        raw=os.pread(profile.fd,MATERIAL_CAP+1,0);data=validate_material(raw)
        if hashlib.sha256(raw).hexdigest()!=APPROVED_DIGEST:raise MaterialRefused('UNAPPROVED_MATERIAL')
        profile._data,profile._digest=data,APPROVED_DIGEST;profile.state='BOUND';profile.check(network=False)
    except OSError as error:
        if profile.fd is not None:
            profile.uncertain(error);return profile
        if not profile.close():return profile
        governor.profile=None
        return None
    except MaterialRefused as error:
        if not profile.close():return profile
        governor.profile=None
        return None
    except BaseException as error:profile.uncertain(error)
    return profile


def require_execution(*args,store=None,request_app=None,**kwargs):
    if args or kwargs:raise unavailable()
    from . import source_supervisor as source
    from .runtime_profile import require_formal_application
    if store is None or not store._formal_mode():raise unavailable()
    if request_app is not None:require_formal_application(request_app,'source_execute')
    candidates=[s for s in source._REGISTRY.values() if s._pid==os.getpid() and (request_app is None or s._binding.app is request_app)
        and s._path==store.path and s._identity==store.storage_identity]
    if len(candidates)!=1:raise unavailable()
    supervisor=candidates[0];source._check(supervisor,published=True);source._same_store(supervisor,store)
    governor=supervisor._sec_access
    if (governor is None or governor.profile is None or governor.retired
            or governor.errors or governor.state=='CLEANUP_UNCERTAIN'):raise unavailable()
    from . import source_sec_access as sec
    sec._held(governor)
    return governor.profile.check(network=True)


def profile_for_connection(conn,*,network):
    """Same real private Auth connection and canonical registered Main only."""
    from . import source_supervisor as source
    if __package__=='web.backend.research':from ..services.sqlite_utils import PrivateAuthConnection
    else:from services.sqlite_utils import PrivateAuthConnection
    if type(conn) is not PrivateAuthConnection or not conn.in_transaction:raise unavailable()
    witness=conn._history_file
    if witness is None:raise unavailable()
    candidates=[s for s in source._REGISTRY.values() if s._pid==os.getpid()
        and s._path==witness.path and s._identity==witness.file_identity]
    if len(candidates)!=1:raise unavailable()
    supervisor=candidates[0];source._check(supervisor,published=True)
    governor=supervisor._sec_access
    if governor is None or governor.profile is None or governor.errors or governor.retired:raise unavailable()
    return governor.profile.check(network=network)


def require_private_cache(*args,**kwargs):
    # Implemented with the actual read scope below, independently of live send.
    if len(args)!=2 or set(kwargs)!={'purpose'}:raise PermissionError('actual DOC cache read lifetime required')
    return _cache_read(*args,**kwargs)


_COMPLETION_FACTORY = object()
_COMPLETIONS = {}
_COMPLETION_DOMAINS = {}


class DocCompletion:
    __slots__=('session','outcome','flight','witness','pid','thread','epoch','artifact_ref','receipt_ref','state',
        'conn','before','records','cas_checked','_factory')
    def __new__(cls,*args,**kwargs):
        if cls is not DocCompletion or kwargs.get('_factory') is not _COMPLETION_FACTORY:raise PermissionError('native DOC completion factory required')
        return object.__new__(cls)
    def __init__(self,session,outcome,*,_factory=None):
        from uuid import uuid4
        if inspect.currentframe().f_back.f_code is not freeze_doc_completion.__code__:raise PermissionError('canonical DOC completion issuer required')
        supervisor=session_supervisor(session)
        self.session,self.outcome,self.flight,self.witness=session,outcome,outcome.flight,session._doc_request
        self.pid,self.thread,self.epoch=os.getpid(),threading.current_thread(),supervisor._slot_epoch
        self.artifact_ref=str(uuid4()) if outcome.observation.body_complete else None;self.receipt_ref=str(uuid4())
        self.conn=self.before=self.records=None;self.state='PREPARED';self.cas_checked=False;self._factory=_factory
        _COMPLETIONS[id(self)]=self
        _COMPLETION_DOMAINS[id(self)]=(self,session,outcome,self.flight,self.witness,self.pid,self.thread,self.epoch,self.artifact_ref,self.receipt_ref,_factory)
    def __repr__(self):return '<native DOC completion>'
    def __reduce__(self):raise TypeError('DOC completion cannot be serialized')
    def check(self,conn=None):
        from .source_policy import require_doc_outcome
        original=_COMPLETION_DOMAINS.get(id(self))
        current=(self,self.session,self.outcome,self.flight,self.witness,self.pid,self.thread,self.epoch,self.artifact_ref,self.receipt_ref,self._factory)
        # No caller-provided completion digest or observation can substitute.
        if (type(self) is not DocCompletion or _COMPLETIONS.get(id(self)) is not self or self._factory is not _COMPLETION_FACTORY
                or original is None or not all(before is after for before,after in zip(original,current))
                or self.pid!=os.getpid() or self.thread is not threading.current_thread()
                or self.state not in ('PREPARED','WRITING') or session_supervisor(self.session)._slot_epoch!=self.epoch
                or self.session._doc_request is not self.witness):raise PermissionError('actual current DOC completion required')
        require_doc_outcome(self.outcome,self.session)
        self.witness.profile.check(network=False);self.witness.owner.identity
        if conn is not None:
            self.session.checked(conn);self.session.task_lease.require(self.session.store,conn)
            if self.conn is not None and self.conn is not conn:raise PermissionError('DOC completion connection differs')
        return self
    def enter(self,conn):
        self.check(conn)
        if self.state!='PREPARED' or self.conn is not None:raise PermissionError('DOC completion cannot enter twice')
        self.witness.check(conn,network=False)
        for ref in (self.artifact_ref,self.receipt_ref):
            if ref is not None and conn.execute('SELECT 1 FROM research_evidence_objects WHERE id=?',(ref,)).fetchone():raise PermissionError('DOC output existed before transaction')
        self.before=dict(conn.execute('SELECT rowid,* FROM research_source_requests WHERE id=?',(self.witness.row['id'],)).fetchone())
        self.conn=conn;self.state='WRITING'
        self.records=self.derive(conn)
    def derive(self,conn):
        from .source_document_raw import request_output_data,canonical,sha256
        from .source_guard import resource
        from . import source_supervisor as source
        from pathlib import Path
        self.check(conn)
        root=Path(source.__file__).resolve().parent.parent
        images={str(path.relative_to(root)):value.hex() for path,value in self.flight.governor.supervisor._images.items()}
        admission=resource(conn,self.session.task_id)
        return request_output_data(self.session.plan,self.before,self.outcome.observation,self.outcome.retirement.audit,
            artifact_ref=self.artifact_ref,receipt_ref=self.receipt_ref,admission_digest=admission['admission_digest'],
            producer_code_digest=sha256(canonical(images).encode()))
    def verify_rows(self,conn):
        from .evidence_schemas import encode,sha256
        self.check(conn)
        artifact,receipt,c=self.derive(conn)
        for record,kind,raw in ((artifact,'snapshots',self.outcome.raw),(receipt,'executions',None)):
            if record is None:continue
            row=conn.execute('SELECT * FROM research_evidence_objects WHERE id=? AND kind=?',(record.id,kind)).fetchone()
            expected=encode(record)
            if (row is None or row['payload']!=expected or row['payload_digest']!=sha256(expected.encode())
                    or row['research_id']!=record.research_id or row['input_revision']!=record.input_revision
                    or row['task_id']!=record.task_id or row['attempt']!=record.attempt
                    or row['raw']!=raw or row['extracted'] is not None or row['discovery'] is not None):raise PermissionError('DOC same-transaction output differs')
        return c
    def allow_update(self,conn,before,after):
        from .evidence_schemas import canonical
        self.check(conn)
        if self.state!='WRITING' or self.cas_checked or before!=self.before:raise PermissionError('DOC first beforeimage differs')
        c=self.verify_rows(conn)
        expected=dict(before,outcome=c['result']['request_outcome'],execution_closed=1,closure_ref=self.receipt_ref,
            closure_proof=canonical(c),ended_at=c['result']['completion_observed_at'],http_status=c['result']['actual_http_status'],safe_code=c['result']['safe_code'])
        if expected!=after:raise PermissionError('DOC protected afterimage differs')
        self.cas_checked=True
        return True
    def acknowledge(self):
        if not self.cas_checked:raise PermissionError('DOC request CAS absent')
        self.state='COMMITTED';_COMPLETIONS.pop(id(self),None)
        _COMPLETION_DOMAINS.pop(id(self),None)
    def reconcile_ack(self):
        from .evidence_schemas import canonical,encode,sha256
        # No write, new IDs, retry GET, or adoption after an acknowledgement
        # error. A close error has already become sticky Source debt upstream.
        if not self.cas_checked or self.records is None:return False
        artifact,receipt,c=self.records
        with self.session._transaction() as conn:
            row=conn.execute('SELECT * FROM research_source_requests WHERE id=?',(self.witness.row['id'],)).fetchone()
            if (row is None or row['dispatch_id']!=self.witness.row['dispatch_id'] or row['outcome']!=c['result']['request_outcome']
                    or row['execution_closed']!=1 or row['closure_ref']!=self.receipt_ref or row['closure_proof']!=canonical(c)):return False
            for record,kind,raw in ((artifact,'snapshots',self.outcome.raw),(receipt,'executions',None)):
                if record is None:continue
                actual=conn.execute('SELECT * FROM research_evidence_objects WHERE id=? AND kind=?',(record.id,kind)).fetchone();payload=encode(record)
                if actual is None or actual['payload']!=payload or actual['payload_digest']!=sha256(payload.encode()) or actual['raw']!=raw or actual['extracted'] is not None or actual['discovery'] is not None:return False
        self.acknowledge();return True


def freeze_doc_completion(*args,**kwargs):
    from .source_workflow import SourceSession
    from .source_policy import require_doc_outcome
    if len(args)!=2 or kwargs:raise PermissionError('actual native DOC outcome and retirement required')
    session,outcome=args
    if inspect.currentframe().f_back.f_code is not SourceSession._raw_request_gate.__wrapped__.__code__:raise PermissionError('canonical DOC request completion required')
    session_supervisor(session);require_doc_outcome(outcome,session)
    if outcome.observation.http_status is None:raise PermissionError('unknown DOC outcome cannot finalize')
    with session._transaction() as conn:session._doc_request.check(conn,network=False)
    return DocCompletion(session,outcome,_factory=_COMPLETION_FACTORY)


def finalize_doc_request(*args,**kwargs):
    from .source_workflow import SourceSession
    from .source_guard import _WRITES
    from .evidence_schemas import canonical
    if len(args)!=2 or kwargs:raise PermissionError('native DOC completion transaction required')
    conn,completion=args
    if inspect.currentframe().f_back.f_code is not SourceSession._raw_request_gate.__wrapped__.__code__:raise PermissionError('canonical DOC finalization required')
    if type(completion) is not DocCompletion:raise PermissionError('native DOC completion required')
    scope=_WRITES.get(id(conn))
    if scope is None or scope.doc_completion is not completion or not scope.active:raise PermissionError('DOC source write scope absent')
    completion.check(conn);c=completion.verify_rows(conn)
    result=c['result']
    count=conn.execute("""UPDATE research_source_requests SET outcome=?,execution_closed=1,closure_ref=?,closure_proof=?,
        ended_at=?,http_status=?,safe_code=? WHERE id=? AND dispatch_id=? AND outcome='SENDING' AND execution_closed=0
        AND closure_ref IS NULL AND closure_proof IS NULL""",(result['request_outcome'],completion.receipt_ref,canonical(c),
            result['completion_observed_at'],result['actual_http_status'],result['safe_code'],completion.witness.row['id'],completion.witness.row['dispatch_id'])).rowcount
    if count!=1 or not completion.cas_checked:raise PermissionError('DOC first finalization CAS failed')
    return c


class RawReadScope:
    """An actual authenticated read lifetime, never cache/send authority."""
    __slots__ = ('conn','service','identity','source','research_id','task_id','pid','thread','active')

    def __init__(self, conn, service, identity, source, research_id, task_id, *, _factory=None):
        frame=inspect.currentframe().f_back
        if _factory is not _READ_FACTORY or frame.f_code is not rawprep_read_scope.__wrapped__.__code__:
            raise PermissionError('canonical raw read lifetime required')
        for key,value in {'conn':conn,'service':service,'identity':identity,'source':source,'research_id':research_id,
                'task_id':task_id,'pid':os.getpid(),'thread':threading.current_thread(),'active':True}.items():
            object.__setattr__(self,key,value)
        _READS[id(self)]=self

    def __setattr__(self,*args): raise TypeError('DOC read scope is immutable')
    def __reduce__(self): raise TypeError('DOC read scope cannot be serialized')

    def check(self, conn, context):
        from .paid_control import require_authenticated_action
        from .service import ResearchService
        from .source_document_raw import read_query_digest
        if (type(self) is not RawReadScope or _READS.get(id(self)) is not self or not self.active
                or self.pid!=os.getpid() or self.thread is not threading.current_thread()
                or self.conn is not conn or not conn.in_transaction or type(self.service) is not ResearchService
                or self.research_id!=context.research_id or self.task_id!=context.task_id):
            raise PermissionError('actual current DOC read scope required')
        require_authenticated_action(self.source,identity=self.identity,action='source-raw-read',research_id=self.research_id,
            task_id=self.task_id,key='',body_digest=read_query_digest(self.task_id))
        pid=self.service._principal(self.identity)
        self.service.authorization.check(conn,self.identity,pid,self.research_id)


@contextmanager
def rawprep_read_scope(conn, service, identity, source, research_id, task_id):
    from . import source_integration
    from .paid_control import require_authenticated_action
    from .source_document_raw import read_query_digest
    caller=inspect.currentframe().f_back
    # contextmanager resumes through contextlib; inspect the caller of __enter__.
    caller=caller.f_back if caller is not None else None
    if caller is None or caller.f_code is not source_integration.raw_preparations.__code__:
        raise PermissionError('canonical actual raw read action required')
    identifier(research_id);identifier(task_id)
    require_authenticated_action(source,identity=identity,action='source-raw-read',research_id=research_id,
        task_id=task_id,key='',body_digest=read_query_digest(task_id))
    scope=RawReadScope(conn,service,identity,source,research_id,task_id,_factory=_READ_FACTORY)
    try: yield scope
    finally:
        object.__setattr__(scope,'active',False);_READS.pop(id(scope),None)



def _cache_read(*args,**kwargs):
    # Root is freezing the current, revocable code-mapped cache policy. Never
    # open a new UA/profile FD after Source has already closed.
    raise PermissionError('current DOC cache policy binding pending')


_REQUEST_FACTORY = object()
_DOC_REQUESTS = {}


def session_supervisor(session):
    from .source_workflow import SourceSession
    from . import source_supervisor as source
    if type(session) is not SourceSession or not session.store._formal_mode():raise unavailable()
    supervisor=source._require_store_worker(session.store,operation='send')
    if (supervisor._session is not session or supervisor._lease is not session.task_lease
            or supervisor._slot!=session.task_id or threading.current_thread() is not supervisor._thread):raise unavailable()
    return supervisor


class DocRequestWitness:
    __slots__=('session','supervisor','conn','owner','row','profile','pid','thread','epoch','issued','active','_factory')
    def __new__(cls,*args,**kwargs):
        if cls is not DocRequestWitness or kwargs.get('_factory') is not _REQUEST_FACTORY:raise PermissionError('native DOC request required')
        return object.__new__(cls)
    def __init__(self,session,conn,owner,row,profile,*,_factory=None):
        if inspect.currentframe().f_back.f_code is not request_witness.__code__:raise PermissionError('native DOC request issuer required')
        self.session,self.supervisor,self.conn,self.owner,self.row,self.profile=session,session_supervisor(session),conn,owner,dict(row),profile
        self.pid,self.thread,self.epoch=os.getpid(),threading.current_thread(),self.supervisor._slot_epoch
        self.issued,self.active,self._factory=False,True,_factory;_DOC_REQUESTS[id(self)]=self
    def __repr__(self):return '<native DOC request witness>'
    def __reduce__(self):raise TypeError('DOC request cannot be serialized')
    def check(self,conn=None,*,network=False):
        from .authorization import OwnerGateLease
        supervisor=session_supervisor(self.session)
        if (type(self) is not DocRequestWitness or _DOC_REQUESTS.get(id(self)) is not self or not self.active
                or self._factory is not _REQUEST_FACTORY or self.pid!=os.getpid() or self.thread is not threading.current_thread()
                or self.epoch!=supervisor._slot_epoch or self.session._doc_request is not self
                or type(self.owner) is not OwnerGateLease or self.profile is not supervisor._sec_access.profile):raise unavailable()
        self.owner.identity;self.profile.check(network=network)
        if conn is not None:
            self.session.task_lease.require(self.session.store,conn)
            task=self.session.checked(conn)
            if task['id']!=self.row['task_id']:raise PermissionError('DOC current task differs')
            actual=conn.execute('SELECT * FROM research_source_requests WHERE id=?',(self.row['id'],)).fetchone()
            if actual is None or any(actual[k]!=v for k,v in self.row.items()):raise PermissionError('DOC original SENDING differs')
        return self
    def retire(self):
        self.active=False;_DOC_REQUESTS.pop(id(self),None)


def request_witness(session,conn,owner,row):
    from .source_workflow import SourceSession
    caller=inspect.currentframe().f_back
    if caller.f_code is not SourceSession._raw_request_gate.__wrapped__.__code__:raise PermissionError('canonical DOC request gate required')
    supervisor=session_supervisor(session)
    profile=supervisor._sec_access.profile
    if profile is None:raise unavailable()
    profile.check(network=True);owner.identity;session.task_lease.require(session.store,conn)
    return DocRequestWitness(session,conn,owner,row,profile,_factory=_REQUEST_FACTORY)


def guard_doc_request(witness,conn,row):
    from .source_document_raw import canonical
    if type(witness) is not DocRequestWitness or witness.conn is not conn:raise PermissionError('actual DOC request transaction required')
    witness.check(network=True)
    if any(row.get(key)!=value for key,value in witness.row.items()):raise PermissionError('DOC first request differs')
    if (row['outcome']!='SENDING' or row['execution_closed']!=0 or row['closure_ref'] is not None or row['closure_proof'] is not None
            or row['ended_at'] is not None or row['http_status'] is not None or row['safe_code']!='none'
            or row['owner_gate_identity']!=canonical(witness.owner.identity)
            or row['task_gate_identity']!=canonical(witness.session.task_lease.identity)):raise PermissionError('DOC initial SENDING domain differs')
    witness.issued=True
    return True


class DocTransaction:
    """A producer-owned Store transaction; close errors are sticky Source debt.

    This is only for the still-live native Source worker, never historical read
    borrowing or a CLOSED Source receipt. The canonical Store owns SQL/budgets.
    """
    def __init__(self,session,*,write=True):
        from .source_workflow import SourceSession
        frame=inspect.currentframe().f_back
        if frame.f_code not in (SourceSession._raw_request_gate.__wrapped__.__code__,SourceSession._run_raw.__code__,SourceSession._transaction.__code__):
            raise PermissionError('canonical DOC producer transaction required')
        self.session=session;self.supervisor=session_supervisor(session)
        self.context=session.store.transaction(write=write);self.conn=None;self.witness=None;self.close_codes=set();self.uncertain_fds=[]
    def _remember(self):
        if self.conn is not None:
            self.witness=getattr(self.conn,'_history_file',None)
            for obj in (self.conn,self.witness):
                method=getattr(obj,'close',None)
                code=getattr(method,'__code__',None)
                if code is not None:self.close_codes.add(code)
        if __package__=='web.backend.research':from ..services import sqlite_utils,runtime_paths
        else:from services import sqlite_utils,runtime_paths
        self.close_codes.update((sqlite_utils.PrivateHistoryConnection.close.__code__,runtime_paths.PrivateHistoryFile.close.__code__))
    def _close_failure(self,error):
        if __package__=='web.backend.research':from ..services import sqlite_utils
        else:from services import sqlite_utils
        # Store classification preserves the native exception as __context__.
        # Inspect only exact known native frames; never format or publish locals.
        pending=[error];seen=set();found=False
        while pending:
            current=pending.pop()
            if id(current) in seen:continue
            seen.add(id(current));tb=current.__traceback__
            for linked in (current.__cause__,current.__context__):
                if linked is not None:pending.append(linked)
            while tb is not None:
                frame=tb.tb_frame
                if frame.f_code in self.close_codes:
                    found=True
                    fd=frame.f_locals.get('fd')
                    if type(fd) is int and fd not in self.uncertain_fds:self.uncertain_fds.append(fd)
                    actual=frame.f_locals.get('self')
                    if self.witness is None and actual is not self.conn:self.witness=actual
                if frame.f_code is sqlite_utils.connect_private_auth.__code__:
                    if self.conn is None:self.conn=frame.f_locals.get('connection')
                    if self.witness is None:self.witness=frame.f_locals.get('witness')
                tb=tb.tb_next
        if found or getattr(error,'_source_cleanup_uncertainty',None):
            from .source_spawn import SourceCleanupUncertain
            debt=SourceCleanupUncertain('DOC producer transaction retirement uncertain')
            debt._doc_transaction=self
            raise debt from error
    def __enter__(self):
        self._remember()
        try:self.conn=self.context.__enter__()
        except BaseException as error:self._close_failure(error);raise
        self._remember();return self.conn
    def __exit__(self,kind,error,tb):
        try:return self.context.__exit__(kind,error,tb)
        except BaseException as cleanup:self._close_failure(cleanup);raise
