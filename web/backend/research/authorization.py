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

    @contextmanager
    def owner_gate_id(self, gate_id, *, timeout=5):
        # IDs are internal UUIDs; no raw identity enters paths.
        if str(UUID(gate_id, version=4)) != gate_id:
            raise ValueError("canonical gate id required")
        root = self.store.path.parent / "research-locks"
        root.mkdir(mode=0o700, exist_ok=True)
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ResearchError("STORE_UNAVAILABLE", 503, "研究锁目录不可用。")
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fd = None
        lease = None
        try:
            flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
            try:
                fd = os.open(gate_id + ".lock", flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
            except FileExistsError:
                # Open an existing inode without O_CREAT. On this macOS target,
                # concurrent non-exclusive cold create/openat produced ENOENT
                # even with a stable live directory. Do not retry other errors.
                fd = os.open(gate_id + ".lock", flags, dir_fd=directory)
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o077):
                raise ResearchError("STORE_UNAVAILABLE", 503, "研究锁不可用。")
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ResearchError("STORE_BUSY", 503, "保存暂时繁忙，请用原操作重试。", retryable=True) from None
                    time.sleep(0.01)
            lease=OwnerGateLease(fd,_factory=_LEASE_FACTORY)
            yield lease
        finally:
            if lease is not None:lease._deactivate()
            if fd is not None:
                os.close(fd)  # Closing releases flock, including exception paths.
            os.close(directory)
        # Never unlink lock files: waiters must keep the same inode.
