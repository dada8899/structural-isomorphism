"""Fixed production startup-approval contract; no live issuer or credential I/O.

Signed DTOs are not runtime authority. A separate marked-temp rehearsal can
prove cryptographic binding and durable one-shot consumption without loading a
provider key, opening a socket or publishing a Main capability.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile
from typing import Annotated, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, StrictInt, StringConstraints, ValidationError

from .external_first_answer_contract import (
    CAP_UNITS, INPUT_SCHEMA, MODEL, OUTPUT_SCHEMA, PROJECT, PROVIDER, PURPOSE, TARGET,
    ContractError, template_digest,
)
from .provider_schemas import DTO, Digest, Id, Natural, Positive, ProviderFailure, canonical, digest, strict_json

PROTOCOL="external-first-answer-startup-approval-v1"
BALANCE_TARGET="https://api.deepseek.com/user/balance"
CREDENTIAL_ENTRY="run-formal-main-external-first-answer-v1"
CREDENTIAL_ID="structural-external-first-answer-deepseek-key"
KEY_NAME="external-first-answer-startup-review-v1"
MAX_APPROVAL_AGE=120
_SIGNATURE=Annotated[str,StringConstraints(pattern=r"^[a-f0-9]{128}$")]
_GENERATION=Annotated[str,StringConstraints(pattern=r"^[a-f0-9]{32}$")]
_SOURCE=Annotated[str,StringConstraints(pattern=r"^[a-f0-9]{40}$")]
_BINDING=Annotated[str,StringConstraints(pattern=r"^[A-Za-z0-9._:-]{1,100}$")]
_TIME=Annotated[StrictInt,Field(ge=1,le=(1<<63)-1)]


class StartupBinding(DTO):
    """Snapshot of future code-owned startup facts, not a caller grant."""

    startup_id:Id
    source_commit:_SOURCE
    source_manifest_digest:Digest
    runtime_closure_digest:Digest
    unit_digest:Digest
    database_dev:Natural
    database_ino:Annotated[StrictInt,Field(ge=1)]
    receipts_dev:Natural
    receipts_ino:Annotated[StrictInt,Field(ge=1)]
    schema_version:Literal[17]
    runtime_uid:Annotated[StrictInt,Field(ge=981,le=981)]
    runtime_gid:Annotated[StrictInt,Field(ge=976,le=976)]
    owner_principal:Id=Field(repr=False)
    owner_generation:_GENERATION=Field(repr=False)
    owner_epoch:Positive
    owner_gate_id:Id=Field(repr=False)
    account_id:Id=Field(repr=False)
    economic_binding:_BINDING=Field(repr=False)
    funding_epoch:Positive
    credential_incarnation:_BINDING=Field(repr=False)
    ledger_policy_digest:Digest
    endpoint_policy_digest:Digest


class OwnerKeyStartupBinding(StartupBinding):
    """Independent owner-supplied credential; no provider payer claim."""

    schema_version:Literal[18]
    credential_source:Literal['owner_supplied']
    authorization_event_ref:Id
    payer_identity_status:Literal['unknown']
    payer_id:None


class Approval(DTO):
    protocol:Literal["external-first-answer-startup-approval-v1"]
    reviewer_key_id:Literal["external-first-answer-startup-review-v1"]
    purpose:Literal["external-first-answer-question-v1"]
    project:Literal["structure-rebuild-v1"]
    provider:Literal["deepseek"]
    model:Literal["deepseek-flash"]
    completion_target:Literal["https://api.deepseek.com/chat/completions"]
    balance_target:Literal["https://api.deepseek.com/user/balance"]
    input_schema:Literal["external-first-answer-question-only-v1"]
    output_schema:Literal["external-first-answer-unverified-candidate-v1"]
    template_digest:Digest
    credential_entry:Literal["run-formal-main-external-first-answer-v1"]
    credential_id:Literal["structural-external-first-answer-deepseek-key"]
    cap_units:Annotated[StrictInt,Field(ge=CAP_UNITS,le=CAP_UNITS)]
    currency:Literal["CNY"]
    scale:Annotated[StrictInt,Field(ge=6,le=6)]
    approval_id:Id
    issued_at:_TIME
    expires_at:_TIME
    binding:StartupBinding|OwnerKeyStartupBinding=Field(repr=False)


class SignedApproval(DTO):
    approval:Approval=Field(repr=False)
    signature:_SIGNATURE=Field(repr=False)


@dataclass(frozen=True,slots=True)
class ClosedStartupReceipt:
    startup_id:str
    approval_id:str
    approval_digest:str
    source_commit:str
    state:Literal["closed"]="closed"
    live_authority:Literal[False]=False
    credential_loaded:Literal[False]=False
    may_reserve:Literal[False]=False
    may_send:Literal[False]=False


def _verify(raw,expected,reviewer_public_key,now):
    try:
        if type(expected) not in (StartupBinding,OwnerKeyStartupBinding) or type(reviewer_public_key) is not bytes or len(reviewer_public_key)!=32:
            raise ValueError()
        expected=type(expected).model_validate(expected)
        parsed=strict_json(raw,cap=16384)
        envelope=SignedApproval.model_validate(parsed)
        if canonical(envelope.model_dump(mode="json"))!=raw:
            raise ValueError()
        signed=canonical(envelope.approval.model_dump(mode="json"))
        Ed25519PublicKey.from_public_bytes(reviewer_public_key).verify(bytes.fromhex(envelope.signature),signed)
        approval=envelope.approval
        if (type(now) is not int or not 0<approval.expires_at-approval.issued_at<=MAX_APPROVAL_AGE
                or not approval.issued_at<=now<approval.expires_at or approval.binding!=expected
                or approval.template_digest!=template_digest()
                or (approval.purpose,approval.project,approval.provider,approval.model,approval.completion_target,
                    approval.input_schema,approval.output_schema)!=(PURPOSE,PROJECT,PROVIDER,MODEL,TARGET,INPUT_SCHEMA,OUTPUT_SCHEMA)):
            raise ValueError()
        return ClosedStartupReceipt(expected.startup_id,approval.approval_id,digest(signed),expected.source_commit)
    except (InvalidSignature,ProviderFailure,ValidationError,ValueError,TypeError,UnicodeError):
        raise ContractError("startup_approval_rejected") from None


def _scratch(path,expected):
    if type(path) is not type(Path()) or path.resolve(strict=True)!=path:
        raise ContractError("issuer_fixture_required")
    root=Path(tempfile.gettempdir()).resolve(strict=True)
    if not path.is_relative_to(root) or path==root or any(path.is_relative_to(Path(p)) for p in (
            "/var/lib/structural-isomorphism","/var/cache/structural-isomorphism","/srv/structural-isomorphism")):
        raise ContractError("issuer_fixture_required")
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if (info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700
                or (info.st_dev,info.st_ino)!=(expected.receipts_dev,expected.receipts_ino)):
            raise ContractError("issuer_fixture_required")
        marker=os.open("STRUCTURE-EXTERNAL-ISSUER-FIXTURE",os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fd)
        try:
            s=os.fstat(marker)
            if (not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600
                    or s.st_nlink!=1 or os.read(marker,64)!=b"isolated external issuer rehearsal\n"):
                raise ContractError("issuer_fixture_required")
        finally:os.close(marker)
        return fd
    except BaseException:
        os.close(fd)
        raise


def consume_isolated_startup_once(path,raw,expected,reviewer_public_key,*,now):
    """Spend one exact synthetic startup challenge, never open a live lane."""
    receipt=_verify(raw,expected,reviewer_public_key,now)
    try:parent=_scratch(path,expected)
    except OSError:raise ContractError("issuer_fixture_required") from None
    try:
        name="spent-"+receipt.startup_id+".json"
        try:
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=parent)
        except FileExistsError:
            raise ContractError("startup_challenge_already_consumed") from None
        record=canonical({"startup_id":receipt.startup_id,"approval_id":receipt.approval_id,
             "approval_digest":receipt.approval_digest,"source_commit":receipt.source_commit,
             "state":"closed","no_auto_retry":True})
        with os.fdopen(fd,"wb") as sink:
            sink.write(record);sink.flush();os.fsync(sink.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    return receipt


def require_live_startup_issuer():
    # Do not accept a DTO, arbitrary callback, config flag or the controlled
    # runtime's loopback authority. No production verifier/entry witness is
    # installed in this release.
    raise ContractError("live_external_issuer_unbound")
