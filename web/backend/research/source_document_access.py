"""B1 authenticated read boundary; all DOC native execution remains closed.

There is no approved access profile material in this version. In particular
this module never opens a profile path or turns a JSON digest into a permit.
"""
from contextlib import contextmanager
import inspect
import os
import threading

from .errors import ResearchError
from .evidence_schemas import identifier

_READ_FACTORY = object()
_READS = {}


def unavailable():
    return ResearchError('SOURCE_PERMISSION_UNAVAILABLE',503,'官方原始材料准备尚不可用：访问身份与原生获取链尚未接齐。')


def require_execution(*args, **kwargs):
    raise unavailable()


def require_private_cache(*args, **kwargs):
    raise PermissionError('DOC private cache approval unavailable')


class ActualAccessProfile:
    def __new__(cls, *args, **kwargs):
        raise PermissionError('B1 has no actual DOC access profile factory')


class DocCompletion:
    def __new__(cls, *args, **kwargs):
        raise PermissionError('B1 has no actual DOC completion factory')


def attach_access(*args, **kwargs):
    raise PermissionError('B1 DOC native attachment is closed')


def freeze_doc_completion(*args, **kwargs):
    raise PermissionError('B1 DOC native completion is closed')


def finalize_doc_request(*args, **kwargs):
    raise PermissionError('B1 DOC protected finalization is closed')


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
