"""Private runtime paths and the deliberately closed R2-A admission gate.

No filesystem objects are created or migrated here. R2-B/R3 consumers have not
been connected yet; only a later reviewed source change may admit production.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import threading
import sqlite3


class FormalAdmissionError(RuntimeError):
    """Formal persistence consumers are not integrated in this candidate."""


def require_formal_admission():
    # No environment/state/registry switch can attest to completed migration.
    raise FormalAdmissionError("formal persistence consumers are not integrated")


class FormalAdmissionMiddleware:
    """Outermost user ASGI boundary, including when lifespan is disabled."""

    def __init__(self, app, *, formal: bool):
        self.app = app
        # Capture the effective import-time profile. Later environment changes
        # and fabricated app.state readiness cannot turn off this boundary.
        if type(formal) is not bool:
            raise TypeError("formal must be a boolean")
        self.formal = formal

    async def __call__(self, scope, receive, send):
        if self.formal and scope["type"] in ("http", "websocket"):
            try:
                require_formal_admission()
            except FormalAdmissionError:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1013})
                else:
                    body = (b'{"type":"about:blank","title":"Service unavailable",'
                            b'"status":503,"detail":"Formal runtime storage is not admitted."}')
                    await send({"type": "http.response.start", "status": 503,
                                "headers": [(b"content-type", b"application/problem+json"),
                                            (b"cache-control", b"no-store"),
                                            (b"content-length", str(len(body)).encode())]})
                    await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


# Approved a2 roots only. Environment flags do not override these locations.
STATE_ROOT = Path("/var/lib/structural-isomorphism")
CACHE_ROOT = Path("/var/cache/structural-isomorphism")
LOG_ROOT = STATE_ROOT / "logs"

# File names retain their current owners' meanings. This is path resolution,
# not a consumer migration registry and never grants formal admission. Other
# asset paths remain unresolved until their owners connect B/R3 consumers.
_FILES = {
    "auth": ("state", "auth.sqlite3"),
    "history": ("state", "history.db"),
    "sso": ("state", "sso_replay.sqlite3"),
    "mapping_cache": ("cache", "mapping_cache.jsonl"),
    "analysis_cache": ("cache", "analysis_cache.jsonl"),
    "server_log": ("logs", "server.jsonl"),
    "retrieval_log": ("logs", "retrieval.jsonl"),
}


class RuntimePathError(RuntimeError):
    """A proposed private path is outside the approved storage boundary."""


def _directory_fd(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimePathError("private runtime paths must be absolute and canonical")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _repository_roots(repository):
    """Read only Git worktree location metadata, never config or credentials."""
    repository = Path(repository).resolve()
    roots = {repository}
    git = repository / ".git"
    if git.is_file():
        text = git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            raise RuntimePathError("invalid repository location metadata")
        directory = Path(text[len("gitdir: "):])
        git = (repository / directory).resolve()
    if git.is_dir():
        common_file = git / "commondir"
        common = (git / common_file.read_text().strip()).resolve() if common_file.is_file() else git
        roots.add(common.parent)
        registrations = common / "worktrees"
        if registrations.is_dir():
            for entry in registrations.iterdir():
                location = entry / "gitdir"
                if location.is_file():
                    value = Path(location.read_text().strip())
                    if not value.is_absolute():
                        raise RuntimePathError("invalid registered worktree location")
                    roots.add(value.parent.resolve())
    return roots


def _validated_directory_fd(path, *, forbidden):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimePathError("private runtime paths must be absolute and canonical")
    # The subsequent no-follow walk rejects aliases in the candidate itself;
    # resolving public roots also rejects paths behind a public symlink mount.
    if any(path == root or path.is_relative_to(root) for root in forbidden):
        raise RuntimePathError("private runtime path overlaps a repository or public tree")
    fd = _directory_fd(path)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimePathError("private runtime directory owner or permissions are invalid")
    except BaseException:
        os.close(fd)
        raise
    return fd


def _validate_directory(path, *, forbidden):
    fd = _validated_directory_fd(path, forbidden=forbidden)
    os.close(fd)
    return Path(path)


def _check_current_parent(path, fd, *, forbidden):
    # Reopen only to compare the current pathname to the held, validated FD;
    # file/sidecar inspection itself never switches to this second directory.
    current_fd = _validated_directory_fd(path, forbidden=forbidden)
    try:
        held, current = os.fstat(fd), os.fstat(current_fd)
        if (held.st_uid != os.geteuid() or stat.S_IMODE(held.st_mode) != 0o700
                or current.st_uid != os.geteuid() or stat.S_IMODE(current.st_mode) != 0o700
                or (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)):
            raise RuntimePathError("private runtime directory changed during inspection")
    finally:
        os.close(current_fd)


@dataclass(frozen=True)
class RuntimePaths:
    state: Path
    cache: Path
    logs: Path
    forbidden: frozenset[Path]

    @classmethod
    def inspect_formal(cls, *, repository, public_roots):
        """Inspect existing a2 directories without creating them or admitting IO.

        public_roots must come from the application's actual mounted directories;
        knowing these paths is not evidence that any consumer has migrated.
        """
        forbidden = _repository_roots(repository)
        forbidden.update(Path(p).resolve() for p in public_roots)
        # Always exclude the repository frontend, even before static mounts are
        # instantiated. Explicit external mounted roots are required separately.
        forbidden.add((Path(repository) / "web/frontend").resolve())
        forbidden = frozenset(forbidden)
        if LOG_ROOT != STATE_ROOT / "logs":
            raise RuntimePathError("formal log root must be inside the approved state root")
        try:
            state, cache, logs = (
                _validate_directory(p, forbidden=forbidden) for p in (STATE_ROOT, CACHE_ROOT, LOG_ROOT)
            )
        except OSError:
            raise RuntimePathError("private runtime directory is missing or unsafe") from None
        return cls(state, cache, logs, forbidden)

    def file(self, kind):
        """Inspect a known target now; never create it or grant write access.

        File/sidecar checks use one validated directory FD. The pathname must
        still match it at the final check, but the returned Path is inspection
        only: B/R3 consumers still need their own atomic open/FD validation.
        No guarantee extends to replacements after this function returns.
        """
        if kind not in _FILES:
            raise RuntimePathError("unknown private runtime file")
        group, name = _FILES[kind]
        parent = getattr(self, group)
        try:
            fd = _validated_directory_fd(parent, forbidden=self.forbidden)
            try:
                try:
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    info = None
                if info is not None and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
                    raise RuntimePathError("private runtime file owner, links or permissions are invalid")
                # SQLite journal sidecars must obey the same private boundary.
                if name.endswith((".db", ".sqlite3")):
                    for suffix in ("-wal", "-shm", "-journal"):
                        try:
                            side = os.stat(name + suffix, dir_fd=fd, follow_symlinks=False)
                        except FileNotFoundError:
                            continue
                        if (not stat.S_ISREG(side.st_mode) or side.st_nlink != 1
                                or side.st_uid != os.geteuid() or stat.S_IMODE(side.st_mode) != 0o600):
                            raise RuntimePathError("private SQLite sidecar is unsafe")
                _check_current_parent(parent, fd, forbidden=self.forbidden)
            finally:
                os.close(fd)
        except OSError:
            raise RuntimePathError("private runtime file is unsafe") from None
        return parent / name


def resolve_runtime_file(kind, *, formal, development_path, repository, public_roots):
    """Future consumer hook; development retains its caller-owned old default."""
    if type(formal) is not bool:
        raise TypeError("formal must be a boolean")
    if not formal:
        return Path(development_path)
    return RuntimePaths.inspect_formal(repository=repository, public_roots=public_roots).file(kind)


def formal_history_runtime():
    return os.getenv('STRUCTURAL_ENV', 'dev').lower() == 'prod'


# Process-local only: closing even an unrelated ordinary database FD releases
# this process's POSIX locks on that inode. Protect a *new* inode's short
# precreation FD until close, against every native open through this helper.
# This mutex does not serialize SQL transactions or replace SQLite's locks.
# Both supported module names (services.* / web.backend.services.*) must use
# the same mutex in one interpreter. sqlite3 is the canonical shared module;
# setdefault installs exactly one object, not a migration/admission flag.
HISTORY_OPEN_LOCK = vars(sqlite3).setdefault('_structural_history_open_lock_v1', threading.RLock())


class PrivateHistoryFile:
    """A parent-directory FD and non-locking file-identity snapshot.

    Never open/dup/close an ordinary FD for an existing SQLite database:
    closing it can release another live connection's process-level locks.
    Native sqlite3 opens a pathname, not an application-owned database FD.
    This boundary assumes the dedicated service UID, trusted parents and no uncontrolled same-UID path
    replacement. Maintenance must stop consumers. It is not a hostile-root
    proof, custom VFS, or permission to admit the unfinished formal app.
    """

    def __init__(self):
        self.parent_fd = None
        self.file_identity = None

    @classmethod
    def acquire(cls, path, *, create=False):
        with HISTORY_OPEN_LOCK:
            return cls._acquire_locked(path, create=create)

    @classmethod
    def _acquire_locked(cls, path, *, create):
        witness = cls()
        try:
            supplied = os.fspath(path)
            expected = STATE_ROOT / 'history.db'
            if (not isinstance(supplied, str) or supplied.startswith('file:')
                    or Path(supplied) != expected or '..' in Path(supplied).parts
                    or not Path(supplied).is_absolute()):
                raise RuntimePathError('formal history requires the approved canonical file')
            root = Path(__file__).resolve().parents[3]
            frontend = root / 'web/frontend'
            paths = RuntimePaths.inspect_formal(repository=root, public_roots=[
                frontend, frontend / 'assets', frontend / 'phase/samples', frontend / 'phase/data',
            ])
            witness.path = expected
            witness.forbidden = paths.forbidden
            witness.parent_fd = _validated_directory_fd(paths.state, forbidden=paths.forbidden)
            base = witness._entry('history.db')
            sides = witness._sidecars()
            if sides and (base is None or base.st_size == 0):
                raise RuntimePathError('orphan SQLite sidecars cannot initialize a history database')
            created = False
            if base is None:
                if not create:
                    raise RuntimePathError('formal history database is missing')
                try:
                    fd = os.open('history.db', os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
                                 | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=witness.parent_fd)
                except FileExistsError:
                    # Validate the winner by no-follow stat only. Opening and
                    # closing it would invalidate other native SQLite locks.
                    base = witness._entry('history.db')
                    if base is None:
                        raise RuntimePathError('history creation race has no validated winner')
                else:
                    try:
                        base = os.fstat(fd)
                        witness._require_private_file(base)
                    finally:
                        # Still under HISTORY_OPEN_LOCK: no helper native open
                        # may have acquired a lock on this new inode yet.
                        os.close(fd)
                    created = True
            witness.file_identity = (base.st_dev, base.st_ino)
            if created and witness._sidecars():
                raise RuntimePathError('sidecars appeared during fresh history creation')
            witness.check()
            return witness
        except BaseException:
            witness.close()
            raise

    @staticmethod
    def _require_private_file(info):
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
            raise RuntimePathError('private history file owner, permissions or links are unsafe')

    def _entry(self, name):
        try:
            info = os.stat(name, dir_fd=self.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        self._require_private_file(info)
        return info

    def _sidecars(self):
        return [info for suffix in ('-wal', '-shm', '-journal')
                if (info := self._entry('history.db' + suffix)) is not None]

    def check(self):
        _check_current_parent(self.path.parent, self.parent_fd, forbidden=self.forbidden)
        current = self._entry('history.db')
        if current is None or self.file_identity != (current.st_dev, current.st_ino):
            raise RuntimePathError('formal history pathname no longer matches its identity snapshot')
        if self._sidecars() and current.st_size == 0:
            raise RuntimePathError('empty history database has orphan sidecars')

    @property
    def uri(self):
        return self.path.as_uri() + '?mode=rw'

    def close(self):
        self.file_identity = None
        fd = self.parent_fd
        self.parent_fd = None
        if fd is not None:
            os.close(fd)


def private_auth_path(configured_dir=None):
    """Static Auth role only; None/unset uses approved state, empty is invalid."""
    profile=os.getenv('STRUCTURAL_ENV','dev')
    if profile.strip().lower()=='prod' and profile.lower()!='prod':
        raise RuntimePathError('private Auth profile contains invalid whitespace')
    configured = os.environ.get('AUTH_DATA_DIR') if configured_dir is None else os.fspath(configured_dir)
    if configured is not None and (not configured or configured.startswith('file:')
            or not Path(configured).is_absolute() or '..' in Path(configured).parts
            or Path(configured) != STATE_ROOT):
        raise RuntimePathError('private auth directory does not match its approved root')
    return STATE_ROOT / 'auth.sqlite3'


def _auth_forbidden_roots():
    repository = Path(__file__).resolve().parents[3]
    frontend = repository / 'web/frontend'
    inspected = RuntimePaths.inspect_formal(repository=repository, public_roots=[
        frontend, frontend/'assets', frontend/'phase/samples', frontend/'phase/data',
    ])
    return inspected.forbidden


class PrivateAuthFile(PrivateHistoryFile):
    """Existing Auth file metadata and parent FD; no ordinary database FD."""
    @classmethod
    def acquire(cls, path):
        witness = cls()
        try:
            if not isinstance(path, (str, Path)) or Path(path) != private_auth_path():
                raise RuntimePathError('private auth requires its canonical existing file')
            witness.path = private_auth_path()
            witness.forbidden = _auth_forbidden_roots()
            witness.parent_fd = _validated_directory_fd(witness.path.parent, forbidden=witness.forbidden)
            info = witness._entry('auth.sqlite3')
            if info is None:
                raise RuntimePathError('private auth database is missing')
            witness.file_identity = (info.st_dev, info.st_ino)
            witness.check()
            return witness
        except BaseException:
            witness.close()
            raise

    def _sidecars(self):
        return [info for suffix in ('-wal','-shm','-journal')
                if (info := self._entry('auth.sqlite3'+suffix)) is not None]

    def check(self):
        _check_current_parent(self.path.parent, self.parent_fd, forbidden=self.forbidden)
        current = self._entry('auth.sqlite3')
        if current is None or self.file_identity != (current.st_dev,current.st_ino):
            raise RuntimePathError('private auth database identity changed')
        if self._sidecars() and current.st_size == 0:
            raise RuntimePathError('private auth database has orphan sidecars')


def require_private_auth_lock_dir(auth_path):
    if Path(auth_path) != private_auth_path():
        raise RuntimePathError('private auth lock root has an invalid database binding')
    root = Path(auth_path).parent/'research-locks'
    fd = _validated_directory_fd(root, forbidden=_auth_forbidden_roots())
    os.close(fd)
    return root


def append_private_auth_audit(record):
    """Specific existing tombstone journal; no create or partial-record repair."""
    import fcntl
    import json
    payload = (json.dumps(record, ensure_ascii=False, allow_nan=False)+'\n').encode('utf-8')
    if len(payload)>1024*1024:
        raise RuntimePathError('private auth audit record is too large')
    parent = private_auth_path().parent
    forbidden = _auth_forbidden_roots()
    directory = _validated_directory_fd(parent, forbidden=forbidden)
    fd = None
    name = 'account_deletion_audit.jsonl'
    try:
        initial=os.stat(name,dir_fd=directory,follow_symlinks=False)
        PrivateAuthFile._require_private_file(initial)
        fd = os.open(name, os.O_RDWR|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(fd)
        PrivateAuthFile._require_private_file(info)
        if (initial.st_dev,initial.st_ino)!=(info.st_dev,info.st_ino):
            raise RuntimePathError('private auth audit changed while opening')
        fcntl.flock(fd,fcntl.LOCK_EX)
        info=os.fstat(fd);PrivateAuthFile._require_private_file(info)
        _check_current_parent(parent,directory,forbidden=forbidden)
        bound = os.stat(name,dir_fd=directory,follow_symlinks=False)
        if (info.st_dev,info.st_ino)!=(bound.st_dev,bound.st_ino):
            raise RuntimePathError('private auth audit identity changed')
        if info.st_size and os.pread(fd,1,info.st_size-1)!=b'\n':
            raise RuntimePathError('private auth audit has an unfinished record; operator reconciliation required')
        offset=0
        while offset<len(payload):
            written=os.write(fd,payload[offset:])
            if written<=0:raise RuntimePathError('private auth audit append was incomplete')
            offset+=written
        os.fsync(fd)
        after=os.fstat(fd);PrivateAuthFile._require_private_file(after)
        _check_current_parent(parent,directory,forbidden=forbidden)
        bound=os.stat(name,dir_fd=directory,follow_symlinks=False)
        if (after.st_dev,after.st_ino)!=(bound.st_dev,bound.st_ino):
            raise RuntimePathError('private auth audit pathname changed during append')
    finally:
        if fd is not None:os.close(fd)  # Releases this non-DB journal's flock.
        os.close(directory)
