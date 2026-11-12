"""Current account checks and stable single-host owner gates."""
from __future__ import annotations

import fcntl
import json
import math
import os
import stat
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID

from .errors import ResearchError, not_found


_LEASE_FACTORY = object()


class OwnerGateLease:
    """Active capability for an already-held gate; never exposes its raw FD.

    Transfer only after the receiver has armed its independent kernel expiry.
    Closing copies never explicitly unlocks the shared open-file description.
    """
    __slots__ = ("__fd", "__creator", "__identity", "__active")

    def __init__(self, fd, *, _factory=None):
        if _factory is not _LEASE_FACTORY:
            raise TypeError("owner gate context must create the lease")
        self.__fd, self.__creator, self.__active = fd, os.getpid(), True
        info=os.fstat(fd)
        self.__identity=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)

    def __reduce__(self):
        raise TypeError("owner gate leases cannot be pickled")

    def _check(self):
        if not self.__active or self.__creator!=os.getpid():
            raise PermissionError("owner gate lease is not active here")
        info=os.fstat(self.__fd)
        identity=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)
        if (identity!=self.__identity or not stat.S_ISREG(info.st_mode)
                or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode & 0o077):
            raise PermissionError("owner gate lease changed")

    @property
    def identity(self):
        self._check()
        return self.__identity

    def handoff(self, connection, child_pid, deadline):
        self._check()
        if (os.name!="posix" or type(child_pid) is not int or child_pid<=0
                or type(deadline) not in (int,float) or not math.isfinite(deadline)
                or not 0<deadline-time.monotonic()<=12):
            raise PermissionError("invalid owner gate handoff")
        from multiprocessing.reduction import send_handle
        # SCM_RIGHTS is sent only now, never cached in a resource_sharer or
        # inherited before the child has installed its hard expiry.
        send_handle(connection,self.__fd,child_pid)

    def _deactivate(self):
        self.__active=False


@dataclass(frozen=True)
class AccountIdentity:
    email: str
    generation: str
    jti: str
    expires_at: int


class AuthorizationGate:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def check_account(conn, identity):
        row = conn.execute("SELECT session_generation,lifecycle FROM auth_users WHERE email=?", (identity.email,)).fetchone()
        revoked = conn.execute("SELECT 1 FROM revoked_sessions WHERE jti=?", (identity.jti,)).fetchone()
        if (row is None or row["lifecycle"] != "active" or row["session_generation"] != identity.generation
                or revoked is not None or identity.expires_at <= time.time()):
            raise ResearchError("AUTH_REQUIRED", 401, "登录已失效，请重新登录。")

    def check(self, conn, identity, principal_id, research_id=None, *, scope="read"):
        self.check_account(conn, identity)
        principal = conn.execute("SELECT * FROM research_principals WHERE id=?", (principal_id,)).fetchone()
        if (not principal or principal["status"] != "active"
                or principal["normalized_email"] != identity.email
                or principal["session_generation"] != identity.generation):
            raise not_found()
        if research_id is None:
            return principal
        research = conn.execute("SELECT * FROM research_controls WHERE id=?", (research_id,)).fetchone()
        if (not research or research["owner_id"] != principal_id or research["lifecycle"] != "active"
                or research["owner_epoch"] != principal["epoch"]):
            raise not_found()
        grant = conn.execute("""SELECT scopes FROM research_grants WHERE principal_id=?
            AND principal_epoch=? AND research_id=? AND acl_epoch=? AND status='active'
            AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value=?)""",
            (principal_id, principal["epoch"], research_id, research["acl_epoch"],scope)).fetchone()
        if not grant or scope not in json.loads(grant["scopes"]):
            raise not_found()
        return research

    def check_task(self,conn,task):
        """Persistent execution grant, not the original browser cookie/JTI."""
        if task["stop_requested"] or not task["research_id"] or not task["grant_id"]:
            raise not_found()
        principal=conn.execute("SELECT * FROM research_principals WHERE id=?",(task["principal_id"],)).fetchone()
        if not principal or principal["status"]!="active" or principal["epoch"]!=task["principal_epoch"]:
            raise not_found()
        user=conn.execute("SELECT lifecycle,session_generation FROM auth_users WHERE email=?",(principal["normalized_email"],)).fetchone()
        research=conn.execute("SELECT * FROM research_controls WHERE id=?",(task["research_id"],)).fetchone()
        grant=conn.execute("SELECT * FROM research_grants WHERE id=?",(task["grant_id"],)).fetchone()
        if (not user or user["lifecycle"]!="active" or user["session_generation"]!=task["auth_generation"]
                or principal["session_generation"]!=task["auth_generation"] or not research or research["lifecycle"]!="active"
                or research["owner_id"]!=principal["id"] or research["owner_epoch"]!=task["owner_epoch"]
                or research["acl_epoch"]!=task["acl_epoch"] or not grant or grant["status"]!="active"
                or grant["principal_id"]!=principal["id"] or grant["principal_epoch"]!=principal["epoch"]
                or grant["research_id"]!=research["id"] or grant["acl_epoch"]!=research["acl_epoch"]
                or "execute" not in json.loads(grant["scopes"])):
            raise not_found()
        return research

    @contextmanager
    def owner_gate(self, principal_id, *, timeout=5):
        with self.store.transaction() as conn:
            row = conn.execute("SELECT gate_id FROM research_principals WHERE id=?", (principal_id,)).fetchone()
            if not row or not row["gate_id"]:
                raise not_found()
            gate_id = row["gate_id"]
        with self.owner_gate_id(gate_id, timeout=timeout) as lease:
            yield lease

    def source_task_gate(self,task_id,*,timeout=5):
        return _source_task_gate(self,task_id,timeout=timeout)

    @contextmanager
    def owner_gate_id(self, gate_id, *, timeout=5):
        if type(gate_id) is not str or str(UUID(gate_id, version=4)) != gate_id:
            raise ValueError("canonical gate id required")
        if __package__=='web.backend.research':
            from ..services.auth_store import _formal_auth_mode
            from ..services.runtime_paths import (PrivateAuthFile,private_auth_path,require_private_auth_lock_dir,
                _check_current_parent,_auth_forbidden_roots,RuntimePathError)
        else:
            from services.auth_store import _formal_auth_mode
            from services.runtime_paths import (PrivateAuthFile,private_auth_path,require_private_auth_lock_dir,
                _check_current_parent,_auth_forbidden_roots,RuntimePathError)
        if __package__=='web.backend.research':from ..services.sqlite_utils import native_thread_budget
        else:from services.sqlite_utils import native_thread_budget
        budget=native_thread_budget(self.store.path,self.store.storage_identity)
        if budget is not None:budget.check()
        current=_formal_auth_mode();formal=getattr(self.store,'_private_auth',False)
        if hasattr(self.store,'_formal_mode'):formal=self.store._formal_mode()
        if current and not formal:raise RuntimePathError('development owner gate cannot become private')
        witness=None;directory=None;fd=None;lease=None
        root=self.store.path.parent/'research-locks';name=gate_id+'.lock'
        def check_formal_lock():
            if budget is not None:budget.check()
            witness.check()
            if witness.file_identity!=self.store.storage_identity:
                raise RuntimePathError('private owner gate Auth identity changed')
            _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
            held=os.fstat(fd);entry=os.stat(name,dir_fd=directory,follow_symlinks=False)
            for info in (held,entry):
                if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid()
                        or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
                    raise RuntimePathError('private owner gate file is unsafe')
            if (held.st_dev,held.st_ino)!=(entry.st_dev,entry.st_ino):
                raise RuntimePathError('private owner gate inode changed')
            auth=getattr(self.store,'auth_store',self.store)
            if (held.st_dev,held.st_ino)!=auth.expected_owner_gate_identity(gate_id):
                raise RuntimePathError('private owner gate differs from admitted resource')
        try:
            if formal:
                if (self.store.path!=private_auth_path() or self.store.storage_identity is None):
                    raise RuntimePathError('private owner gate Auth binding changed')
                # Research also pins its Auth object/profile, not just a path.
                if hasattr(self.store,'_formal_mode'):self.store._formal_mode()
                witness=PrivateAuthFile.acquire(self.store.path)
                if witness.file_identity!=self.store.storage_identity:
                    raise RuntimePathError('private owner gate Auth identity changed')
                root=require_private_auth_lock_dir(self.store.path)
                directory=os.open('research-locks',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=witness.parent_fd)
                _check_current_parent(root,directory,forbidden=_auth_forbidden_roots())
                fd=os.open(name,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=directory)
                check_formal_lock()
            else:
                root.mkdir(mode=0o700,exist_ok=True)
                info=root.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                    raise ResearchError('STORE_UNAVAILABLE',503,'研究锁目录不可用。')
                directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                flags=os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC
                try:fd=os.open(name,flags|os.O_CREAT|os.O_EXCL,0o600,dir_fd=directory)
                except FileExistsError:fd=os.open(name,flags,dir_fd=directory)
                info=os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or info.st_mode&0o077:
                    raise ResearchError('STORE_UNAVAILABLE',503,'研究锁不可用。')
            deadline=time.monotonic()+timeout
            if budget is not None:
                budget.check();limit=budget.limit()
                if limit is not None:deadline=min(deadline,limit)
            while True:
                try:
                    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if budget is not None:budget.check()
                    if time.monotonic()>=deadline:
                        raise ResearchError('STORE_BUSY',503,'保存暂时繁忙，请用原操作重试。',retryable=True) from None
                    time.sleep(min(0.01,max(0.,deadline-time.monotonic())))
            if formal:check_formal_lock()
            lease=OwnerGateLease(fd,_factory=_LEASE_FACTORY)
            try:yield lease
            finally:
                if formal:check_formal_lock()
        finally:
            if lease is not None:lease._deactivate()
            try:
                if fd is not None:os.close(fd)
            finally:
                try:
                    if directory is not None:os.close(directory)
                finally:
                    if witness is not None:witness.close()
        # Stable lock inodes are never unlinked, including on failures.


_TASK_FACTORY=object()


class _TaskBirth:
    __slots__=('store','task_id','fd','parentfd','name','pid','active','_identity')
    def __init__(self,store,task_id,fd,parentfd,name,*,_factory=None):
        if _factory is not _TASK_FACTORY:raise TypeError('actual Source task resource required')
        info=os.fstat(fd)
        values=dict(store=store,task_id=task_id,fd=fd,parentfd=parentfd,name=name,pid=os.getpid(),active=True,
            _identity=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink))
        for key,value in values.items():object.__setattr__(self,key,value)
    def __setattr__(self,*args):raise TypeError('Source task birth is immutable')
    def __reduce__(self):raise TypeError('Source task birth cannot be serialized')
    @property
    def identity(self):
        self.require(self.store,self.task_id);return self._identity
    def require(self,store,task_id):
        if not self.active or self.pid!=os.getpid() or store is not self.store or task_id!=self.task_id:raise PermissionError('Source birth retired')
        parent=os.fstat(self.parentfd);named=(store.path.parent/'research-locks').lstat()
        if (parent.st_dev,parent.st_ino)!=(named.st_dev,named.st_ino) or stat.S_IMODE(named.st_mode)!=0o700:raise PermissionError('Source task parent changed')
        held=os.fstat(self.fd);entry=os.stat(self.name,dir_fd=self.parentfd,follow_symlinks=False)
        for info in (held,entry):
            if (not stat.S_ISREG(info.st_mode) or (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)!=self._identity
                    or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):raise PermissionError('Source task resource changed')


class TaskGateLease:
    """Independent task mutex: never an Auth owner lease or send capability."""
    __slots__=('_birth','task_id','owner_gate_id','admission_digest','epoch','cleanup','active','pid')
    def __init__(self,birth,row,cleanup,*,_factory=None):
        if _factory is not _TASK_FACTORY:raise TypeError('actual held Source task mutex required')
        values=dict(_birth=birth,task_id=row['task_id'],owner_gate_id=row['owner_gate_id'],admission_digest=row['admission_digest'],
            epoch=row['write_epoch'],cleanup=cleanup,active=True,pid=os.getpid())
        for key,value in values.items():object.__setattr__(self,key,value)
    def __setattr__(self,*args):raise TypeError('Source task lease is immutable')
    def __reduce__(self):raise TypeError('Source task lease cannot be serialized')
    @property
    def identity(self):
        if not self.active or self.pid!=os.getpid():raise PermissionError('Source task lease retired')
        return self._birth.identity
    def require(self,store,conn,*,cleanup=False):
        from .source_guard import resource
        from .evidence_schemas import canonical
        self.identity;self._birth.require(store,self.task_id)
        row=resource(conn,self.task_id)
        if row['owner_gate_id']!=self.owner_gate_id or row['admission_digest']!=self.admission_digest or row['task_gate_identity']!=canonical(self.identity):raise PermissionError('Source task binding changed')
        if store._formal_mode():
            owner=(store.path.parent/'research-locks'/(self.owner_gate_id+'.lock')).lstat()
            if (owner.st_dev,owner.st_ino)!=store.auth_store.expected_owner_gate_identity(self.owner_gate_id):raise PermissionError('Source owner resource replaced')
        if not cleanup and (self.cleanup or row['write_epoch']!=self.epoch or row['state']=='closed'):raise PermissionError('Source task execution authority retired')
        if cleanup and row['write_epoch']<self.epoch:raise PermissionError('Source task epoch regressed')
        return row


@contextmanager
def _source_task_gate(gate,task_id,*,timeout=5):
    """Birth only from protected admission; unknown files are never adopted."""
    from .source_guard import resource,check_active,birth_scope
    from .evidence_schemas import canonical
    if type(task_id) is not str or str(UUID(task_id,version=4))!=task_id:raise ValueError('canonical Source task required')
    store=gate.store;fd=directory=None;witness=birth=lease=None
    if __package__=='web.backend.research':from ..services.sqlite_utils import native_thread_budget
    else:from services.sqlite_utils import native_thread_budget
    budget=native_thread_budget(store.path,store.storage_identity)
    if budget is not None:budget.check()
    try:
        with store.transaction() as conn:row=dict(resource(conn,task_id))
        formal=store._formal_mode()
        root=store.path.parent/'research-locks';name='source-'+task_id+'.lock'
        if formal:
            if __package__=='web.backend.research':from ..services.runtime_paths import PrivateAuthFile,require_private_auth_lock_dir
            else:from services.runtime_paths import PrivateAuthFile,require_private_auth_lock_dir
            witness=PrivateAuthFile.acquire(store.path);root=require_private_auth_lock_dir(store.path)
            if witness.file_identity!=store.storage_identity:raise PermissionError('Source Auth inode changed')
            directory=os.open('research-locks',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=witness.parent_fd)
        else:directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        parent=os.fstat(directory);named=root.lstat()
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.geteuid() or stat.S_IMODE(parent.st_mode)!=0o700 or (parent.st_dev,parent.st_ino)!=(named.st_dev,named.st_ino)):
            raise PermissionError('Source lock parent changed')
        if row['task_gate_identity'] is None:
            with gate.owner_gate_id(row['owner_gate_id']) as owner:
                try:
                    with store.transaction(write=True) as conn:
                        current=check_active(store,conn,task_id)
                        run=conn.execute('SELECT started FROM research_source_runs WHERE task_id=?',(task_id,)).fetchone()
                        if not run or run[0]!=0 or current['state']!='admitted' or current['task_gate_identity'] is not None:raise PermissionError('Source birth is no longer available')
                        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
                        birth=_TaskBirth(store,task_id,fd,directory,name,_factory=_TASK_FACTORY)
                        birth.identity;os.fsync(fd);os.fsync(directory)
                        with birth_scope(conn,store,task_id,birth,owner):
                            encoded=canonical(birth.identity)
                            if conn.execute('UPDATE research_source_resources SET task_gate_identity=? WHERE task_id=? AND task_gate_identity IS NULL',(encoded,task_id)).rowcount!=1:raise PermissionError('Source birth CAS failed')
                            conn.execute('UPDATE research_source_runs SET task_gate_identity=? WHERE task_id=? AND task_gate_identity IS NULL',(encoded,task_id))
                except BaseException:
                    # A lost commit ACK is reconciled from this protected row,
                    # never from the existence/name/content of a filesystem file.
                    if birth is None:raise
                    with store.transaction() as conn:committed=resource(conn,task_id)
                    if committed['task_gate_identity']!=canonical(birth.identity) or committed['admission_digest']!=row['admission_digest']:raise
        else:
            fd=os.open(name,os.O_RDWR|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=directory)
            birth=_TaskBirth(store,task_id,fd,directory,name,_factory=_TASK_FACTORY)
            if canonical(birth.identity)!=row['task_gate_identity']:raise PermissionError('Source task inode differs from protected binding')
        # No owner lock while waiting on the independent task mutex.
        deadline=time.monotonic()+timeout
        if budget is not None:
            budget.check();limit=budget.limit()
            if limit is not None:deadline=min(deadline,limit)
        while True:
            if budget is not None:budget.check()
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise ResearchError('STORE_BUSY',503,'来源任务仍在执行。',retryable=True)
                time.sleep(min(.01,max(0.,deadline-time.monotonic())))
        with store.transaction() as conn:
            row=resource(conn,task_id);task=conn.execute('SELECT execution,stop_requested FROM research_tasks WHERE id=?',(task_id,)).fetchone()
            cleanup=row['state']=='closed' or not task or bool(task['stop_requested']) or task['execution'] in ('COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED')
            if not cleanup:check_active(store,conn,task_id)
            lease=TaskGateLease(birth,row,cleanup,_factory=_TASK_FACTORY);lease.require(store,conn,cleanup=cleanup)
        try:yield lease
        finally:lease.identity
    finally:
        if lease is not None:object.__setattr__(lease,'active',False)
        if birth is not None:object.__setattr__(birth,'active',False)
        try:
            if fd is not None:os.close(fd)
        finally:
            try:
                if directory is not None:os.close(directory)
            finally:
                if witness is not None:witness.close()
