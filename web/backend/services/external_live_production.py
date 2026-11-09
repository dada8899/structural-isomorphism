"""Source-pinned external issuer wiring; this source has no installed policy.

No environment, application config, caller callback, or synthetic handle can
activate it. A reviewed target-specific policy must be part of a new release.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib.util
import os
import re
from pathlib import Path
import stat
import sys
import time
import threading

from . import formal_admission
from .external_live_issuer import _attest_main,_LoadPermit,_FACTORY,_ENTRY,_CREDENTIAL_ID,_Sealed

if __package__=="web.backend.services":
    from ..research.external_first_answer_contract import ContractError
else:
    from research.external_first_answer_contract import ContractError


_APPROVAL=Path("/etc/structural/external-first-answer-startup.json")
_SOURCE_MANIFEST=Path("/etc/structural/external-first-answer-source.json")
_UNIT=Path("/etc/systemd/system/structural-web.service")
_RECEIPTS=Path("/var/lib/structural-isomorphism-deploy/external-first-answer-startups")
_RELEASES=Path("/srv/structural-isomorphism/releases")
_ENTRIES={}
_LIVE={}
_LIVE_LOCK=threading.RLock()
_FACTORY_LIVE=object()
_UNCERTAIN_FDS=[]


@dataclass(frozen=True,slots=True,repr=False)
class PinnedTargetPolicy:
    reviewer_public_key_hex:str
    runtime_closure_digest:str
    interpreter:str
    runtime_root:str
    dependency_files:tuple[tuple[str,str],...]


# Intentionally absent. No JSON file or ENV can install this code-owned pin.
_PINNED_POLICY=None


def _fixed_file(path,limit):
    if not path.is_absolute() or path.resolve(strict=True)!=path:
        raise ContractError("external_startup_material_path")
    for parent in path.parents:
        info=parent.stat(follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ContractError("external_startup_material_path")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_nlink!=1 or before.st_mode&0o022 or before.st_size>limit:
            raise ContractError("external_startup_material_file")
        with os.fdopen(fd,"rb",closefd=False) as stream:
            raw=stream.read(limit+1)
        actual=os.fstat(fd);named=path.stat(follow_symlinks=False)
        key=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if len(raw)!=before.st_size or key(before)!=key(actual) or key(before)!=key(named):
            raise ContractError("external_startup_material_changed")
        return raw
    finally:os.close(fd)


def _verify_runtime_files(policy,expected_digest):
    root=Path(policy.runtime_root)
    interpreter=Path(policy.interpreter)
    if (sys.platform!="linux" or Path(sys.executable).resolve(strict=True)!=interpreter
            or not root.is_absolute() or root.resolve(strict=True)!=root or not policy.dependency_files
            or len(policy.dependency_files)>4096):
        raise ContractError("external_runtime_closure_unbound")
    seen=set()
    checks=[]
    for name,sha in policy.dependency_files:
        path=Path(name)
        if name in seen or (path!=interpreter and not path.is_relative_to(root)):
            raise ContractError("external_runtime_closure_unbound")
        seen.add(name)
        if hashlib.sha256(_fixed_file(path,64*1024**2)).hexdigest()!=sha:
            raise ContractError("external_runtime_closure_changed")
        checks.append((name,sha))
    # Only import cryptography after checking its actual installed closure.
    if interpreter.as_posix() not in seen or any(k=="cryptography" or k.startswith("cryptography.") for k in sys.modules):
        raise ContractError("external_runtime_closure_unbound")
    for name in ("cryptography","cffi","_cffi_backend","pycparser"):
        spec=importlib.util.find_spec(name)
        if spec is None or spec.origin not in seen:
            raise ContractError("external_runtime_closure_unbound")
    import json
    raw=json.dumps(sorted(checks),separators=(",",":"),ensure_ascii=False).encode()
    if hashlib.sha256(raw).hexdigest()!=expected_digest:
        raise ContractError("external_runtime_closure_changed")


def publish_entry_for_serve(app,witness):
    """Borrow the existing hardened directory witness, not its old grant."""
    if _PINNED_POLICY is None:
        return
    from . import native_live_credentials
    native_live_credentials._entry_caller("_serve")
    if type(witness) is not native_live_credentials.EntryCredentialDirectoryWitness or id(app) in _ENTRIES:
        raise ContractError("external_entry_witness_required")
    witness.require_runtime()
    _ENTRIES[id(app)]=(app,witness)


def unpublish_entry_for_serve(app):
    if _PINNED_POLICY is None:return
    from . import native_live_credentials
    native_live_credentials._entry_caller("_serve")
    _ENTRIES.pop(id(app),None)


@contextmanager
def _receipt_directory(expected):
    if _RECEIPTS.resolve(strict=True)!=_RECEIPTS:
        raise ContractError("external_startup_receipt_unbound")
    for parent in _RECEIPTS.parents:
        s=parent.stat(follow_symlinks=False)
        if not stat.S_ISDIR(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022:
            raise ContractError("external_startup_receipt_unbound")
    parent=os.open(_RECEIPTS,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        s=os.fstat(parent)
        if ((s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode))!=
                (expected.receipts_dev,expected.receipts_ino,expected.runtime_uid,expected.runtime_gid,0o700)):
            raise ContractError("external_startup_receipt_unbound")
        yield parent
    finally:os.close(parent)


def _consume(expected,receipt):
    with _receipt_directory(expected) as parent:
        name="spent-"+receipt.startup_id+".json"
        try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        except FileExistsError:raise ContractError("startup_challenge_already_consumed") from None
        import json
        with os.fdopen(fd,"wb") as stream:
            stream.write(json.dumps({"startup_id":receipt.startup_id,"approval_digest":receipt.approval_digest,
                                     "source_commit":receipt.source_commit,"no_auto_retry":True},
                                    sort_keys=True,separators=(",",":")).encode())
            stream.flush();os.fsync(stream.fileno())
        os.fsync(parent)



_P1_SPENT="spent-p1-operation"


def _p1_spent_at(parent):
    try:os.stat(_P1_SPENT,dir_fd=parent,follow_symlinks=False)
    except FileNotFoundError:return False
    # Any existing object at this name is spent, including an incomplete
    # record after an uncertain fsync. Never repair or unlink to reopen.
    return True


def _claim_p1_at(parent,operation_key):
    if type(operation_key) is not str or not re.fullmatch(
            r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",operation_key):
        raise ContractError("external_canary_binding_changed")
    opaque=hashlib.sha256(b"structure-external-first-answer-p1-operation-v1\0"+operation_key.encode("ascii")).hexdigest()
    try:
        fd=os.open(_P1_SPENT,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
    except FileExistsError:
        raise ContractError("external_canary_already_spent") from None
    with os.fdopen(fd,"wb") as stream:
        stream.write((opaque+"\n").encode("ascii"))
        stream.flush();os.fsync(stream.fileno())
    os.fsync(parent)


def p1_already_spent(app,handle):
    if type(handle) is not _LiveHandle:
        raise ContractError("real_external_live_handle_required")
    handle.require_for_sender(app)
    try:
        with _receipt_directory(handle._expected) as parent:return _p1_spent_at(parent)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


def claim_p1_before_first_write(app,handle,operation_key):
    from .external_live_sender import _Ticket,_require_live
    frame=sys._getframe(1)
    try:
        if frame.f_code is not _Ticket.first_write.__code__ or type(handle) is not _LiveHandle:
            raise ContractError("external_consumption_ticket_required")
    finally:del frame
    policy,_=_require_live(handle,app)
    if policy.canary_operation_key!=operation_key:
        raise ContractError("external_canary_binding_changed")
    try:
        with _receipt_directory(handle._expected) as parent:_claim_p1_at(parent,operation_key)
    except OSError:raise ContractError("external_startup_receipt_unbound") from None


class _LiveCredential(_Sealed):
    __slots__=("_raw","_active")
    def __init__(self,raw,*,factory):
        if factory is not _FACTORY_LIVE or type(raw) is not bytearray:
            raise PermissionError("external credential factory required")
        object.__setattr__(self,"_raw",raw)
        object.__setattr__(self,"_active",True)
    def retire(self):
        for index in range(len(self._raw)):self._raw[index]=0
        self._raw.clear()
        object.__setattr__(self,"_active",False)


def _load_credential(permit,witness):
    from . import native_live_credentials as entry
    permit.claim(witness,entry=_ENTRY,credential_id=_CREDENTIAL_ID)
    witness.require_runtime()
    module=entry._formal_metadata_entry()
    helper=module._require_metadata_helper()
    directory=witness.fds[-1]
    root_snapshot=module._capture_metadata(directory)
    root_shape=helper.validate_snapshot(root_snapshot,"directory",witness.uid,os.getegid())
    fd=os.open(_CREDENTIAL_ID,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory)
    value=None
    try:
        before,shape=module._metadata_pair(directory,_CREDENTIAL_ID,fd,witness.uid,"file")
        if shape!=root_shape or before["mount_id"]!=root_snapshot["mount_id"] or not 1<=before["size"]<=4096:
            raise ContractError("external_credential_metadata_rejected")
        raw=os.read(fd,4097)
        os.lseek(fd,0,os.SEEK_SET)
        again=os.read(fd,4097)
        after,_=module._metadata_pair(directory,_CREDENTIAL_ID,fd,witness.uid,"file")
        witness.require_runtime()
        if not helper.same_snapshot(before,after) or len(raw)!=before["size"] or raw!=again:
            raise ContractError("external_credential_changed")
        entry.validate_provider_bytes(raw)
        value=_LiveCredential(bytearray(raw),factory=_FACTORY_LIVE)
    finally:
        try:os.close(fd)
        except OSError:
            if value is not None:value.retire()
            _UNCERTAIN_FDS.append(fd)
            raise RuntimeError("external credential retirement uncertain") from None
    return value


class _LiveHandle(_Sealed):
    __slots__=("_app","_binding","_expected","_resource","_entry")
    def __init__(self,app,binding,expected,resource,witness,*,factory):
        if factory is not _FACTORY_LIVE or type(resource) is not _LiveCredential:
            raise PermissionError("external live handle factory required")
        for name,value in (("_app",app),("_binding",binding),("_expected",expected),("_resource",resource),("_entry",witness)):
            object.__setattr__(self,name,value)
    def __repr__(self):return "<sealed external live credential handle>"
    def require_for_sender(self,app):
        if self._app is not app or _LIVE.get(id(app)) is not self or not self._resource._active or _attest_main(app,self._expected) is not self._binding:
            raise ContractError("external_live_handle_retired")
        self._entry.require_runtime()
        # No API exposes raw bytes. A later independently bound sender can
        # require this exact handle at reservation/consume.


def _prepare(app):
    if type(_PINNED_POLICY) is not PinnedTargetPolicy or id(app) in _LIVE:
        raise ContractError("external_production_policy_unbound")
    entry=_ENTRIES.get(id(app))
    if entry is None or entry[0] is not app:
        raise ContractError("external_entry_witness_required")
    witness=entry[1]
    witness.require_runtime()
    if (Path(__file__).resolve().parents[3].parent!=_RELEASES or sys.platform!="linux"
            or (os.geteuid(),os.getegid())!=(981,976)):
        raise ContractError("external_production_target_unbound")
    # Hash-check the code-owned target dependency closure before importing
    # cryptography. The signed Go is issued after the source is finalized;
    # its source SHA is not a self-referential constant in this file.
    _verify_runtime_files(_PINNED_POLICY,_PINNED_POLICY.runtime_closure_digest)
    from research.external_first_answer_issuer_contract import SignedApproval,_verify
    from research.provider_schemas import strict_json
    approved_bytes=_fixed_file(_APPROVAL,16384)
    expected=SignedApproval.model_validate(strict_json(approved_bytes,cap=16384)).approval.binding
    receipt=_verify(approved_bytes,expected,bytes.fromhex(_PINNED_POLICY.reviewer_public_key_hex),int(time.time()))
    root=Path(__file__).resolve().parents[3]
    if root.name!=expected.source_commit or expected.runtime_closure_digest!=_PINNED_POLICY.runtime_closure_digest:
        raise ContractError("external_source_changed")
    raw_source=_fixed_file(_SOURCE_MANIFEST,2*1024**2)
    if hashlib.sha256(raw_source).hexdigest()!=expected.source_manifest_digest:
        raise ContractError("external_source_changed")
    source=strict_json(raw_source,cap=2*1024**2)
    if source.get("schema")!="formal-main-source-payload-v1" or source.get("source_sha")!=expected.source_commit:
        raise ContractError("external_source_changed")
    paths={row["path"]:row["sha256"] for row in source["members"]}
    if len(paths)!=len(source["members"]):
        raise ContractError("external_source_changed")
    for name in ("scripts/run-formal-main.py","web/backend/main.py",
                 "web/backend/services/external_live_issuer.py","web/backend/services/external_live_production.py",
                 "web/backend/research/external_first_answer_issuer_contract.py"):
        if hashlib.sha256(_fixed_file(root/name,512*1024)).hexdigest()!=paths.get(name):
            raise ContractError("external_source_changed")
    dropins=("service.d","structural-.service.d","structural-web.service.d")
    unit_roots=(Path("/etc/systemd/system"),Path("/run/systemd/system"),
                Path("/usr/local/lib/systemd/system"),Path("/usr/lib/systemd/system"),Path("/lib/systemd/system"))
    if (hashlib.sha256(_fixed_file(_UNIT,16384)).hexdigest()!=expected.unit_digest
            or any(os.path.lexists(directory/name) for directory in unit_roots for name in dropins)
            or Path("/proc/self/cgroup").read_text().splitlines()!=["0::/system.slice/structural-web.service"]):
        raise ContractError("external_unit_changed")
    binding=_attest_main(app,expected)
    return binding,witness,expected,receipt


def activate(app):
    if _PINNED_POLICY is None:return None
    caller=sys._getframe(1)
    try:
        main=sys.modules.get("main")
        if main is None or caller.f_code is not main.lifespan.__wrapped__.__code__ or caller.f_locals.get("app") is not app:
            raise ContractError("external_main_startup_required")
    finally:del caller
    try:
        binding,witness,expected,receipt=_prepare(app)
        _consume(expected,receipt)
    except (ContractError,OSError,ValueError,TypeError,KeyError,RuntimeError,ImportError):
        # No loader has run. A possibly written challenge stays spent.
        return None
    permit=_LoadPermit(binding,_load_credential,witness,factory=_FACTORY)
    resource=None
    try:
        resource=_load_credential(permit,witness)
        if not permit._used or _attest_main(app,expected) is not binding:
            raise ContractError("external_main_attestation_rejected")
        handle=_LiveHandle(app,binding,expected,resource,witness,factory=_FACTORY_LIVE)
        with _LIVE_LOCK:_LIVE[id(app)]=handle
        return handle
    except (ContractError,OSError,ValueError,PermissionError):
        if resource is not None:resource.retire()
        return None
    except BaseException:
        if resource is not None:resource.retire()
        raise
    finally:object.__setattr__(permit,"_active",False)


@contextmanager
def wire_latch():
    """First write and resource retirement share one process-local lifetime latch."""
    with _LIVE_LOCK:yield


def retire(app,handle):
    with wire_latch():
        if handle is not None:
            if type(handle) is not _LiveHandle or _LIVE.get(id(app)) is not handle:
                raise ContractError("external_live_handle_retired")
            _LIVE.pop(id(app))
            handle._resource.retire()
