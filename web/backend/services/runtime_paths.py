"""Private runtime paths and the deliberately closed R2-A admission gate.

No filesystem objects are created or migrated here. R2-B/R3 consumers have not
been connected yet; only a later reviewed source change may admit production.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat


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


def _validate_directory(path, *, forbidden):
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
    finally:
        os.close(fd)
    return path


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
        """Inspect a known target; a missing file is returned, never created."""
        if kind not in _FILES:
            raise RuntimePathError("unknown private runtime file")
        group, name = _FILES[kind]
        parent = getattr(self, group)
        try:
            _validate_directory(parent, forbidden=self.forbidden)
            fd = _directory_fd(parent)
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
