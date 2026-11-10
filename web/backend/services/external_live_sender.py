"""Source-pinned production transport and shared ledger, closed by default.

Canary mode pins one request/key. Saved-question mode binds each saved revision
and explicit confirmation to its server-offered key. Neither mode installs pins.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import time

from . import external_live_production as production
if __package__=="web.backend.services":
    from ..research import external_first_answer_contract as contract
    from ..research import external_first_answer_file_writer as file_writer
    from ..research.external_first_answer_catalog import read_main_recovery
    from ..research.external_first_answer_seam import _authorized_saved_revision
    from ..research.external_first_answer_state import TABLE,GUARD
    from ..research.paid_control import require_authenticated_action
    from ..research.provider_schemas import canonical,digest,strict_json
else:
    from research import external_first_answer_contract as contract
    from research import external_first_answer_file_writer as file_writer
    from research.external_first_answer_catalog import read_main_recovery
    from research.external_first_answer_seam import _authorized_saved_revision
    from research.external_first_answer_state import TABLE,GUARD
    from research.paid_control import require_authenticated_action
    from research.provider_schemas import canonical,digest,strict_json

_HOST="api.deepseek.com"
_BALANCE="/user/balance"
_COMPLETION="/chat/completions"
_CA=Path("/etc/ssl/certs/ca-certificates.crt")
_ACCOUNT_PROOF=Path("/etc/structural/external-first-answer-economic-binding.json")
_PRICE_PROOF=Path("/etc/structural/external-first-answer-price-basis.json")
_MAX_RESPONSE=128*1024
_CANARY_MAX_UPPER=2_129_920
_WHOLE_CONTEXT_TOKENS=1_000_000
_TOKEN=object()


@dataclass(frozen=True,slots=True)
class EndpointPolicy:
    public_ip:str
    ca_sha256:str
    economic_proof_sha256:str
    price_basis_sha256:str
    upper_units:int
    canary_operation_key:str|None=None
    canary_request_sha256:str|None=None
    request_mode:str="canary"

    def wire_digest(self):
        _request_mode(self)
        return digest(canonical({"host":_HOST,"public_ip":self.public_ip,"balance":_BALANCE,
                                 "completion":_COMPLETION,"ca_sha256":self.ca_sha256,
                                 "economic_proof_sha256":self.economic_proof_sha256,
                                 "price_basis_sha256":self.price_basis_sha256,"upper_units":self.upper_units,
                                 "canary_operation_key":self.canary_operation_key,"canary_request_sha256":self.canary_request_sha256,
                                 "request_mode":self.request_mode}))


_PINNED_ENDPOINT=EndpointPolicy(
    public_ip='3.173.21.63',
    ca_sha256='ecd9dc38bc3efb7dbd6431f57e29d2f8d6a0f0d211e1464b3fef2cbfe266fcd2',
    economic_proof_sha256='fd4041488720a5603d980656d4acf4c8c95c22cbc2142586d5c786c253aea50c',
    price_basis_sha256='e31d0ba23f7635e3b751ae401e23517640b45931fb816d03095a9618d6ebe51d',
    upper_units=2_129_920,
    request_mode="saved-question",
)


def _within_canary_upper(value):
    return type(value) is int and 1<=value<=_CANARY_MAX_UPPER


def _valid_operation_key(key):
    return type(key) is str and re.fullmatch(r"[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}",key) is not None


def _request_mode(policy):
    if type(policy.request_mode) is not str:
        raise contract.ContractError("external_request_mode_unbound")
    if policy.request_mode=="canary":
        if (not _valid_operation_key(policy.canary_operation_key) or type(policy.canary_request_sha256) is not str
                or re.fullmatch(r"[a-f0-9]{64}",policy.canary_request_sha256) is None):
            raise contract.ContractError("external_canary_unbound")
    elif policy.request_mode=="saved-question":
        if policy.canary_operation_key is not None or policy.canary_request_sha256 is not None:
            raise contract.ContractError("external_saved_question_policy_invalid")
    else:
        raise contract.ContractError("external_request_mode_unbound")
    return policy.request_mode


def _request_binding(policy,key,request_digest):
    mode=_request_mode(policy)
    if mode=="canary" and (key,request_digest)!=(policy.canary_operation_key,policy.canary_request_sha256):
        raise contract.ContractError("external_canary_binding_changed")
    if not _valid_operation_key(key) or type(request_digest) is not str or re.fullmatch(r"[a-f0-9]{64}",request_digest) is None:
        raise contract.ContractError("external_operation_binding_changed")


def _require_live(handle,app):
    if type(handle) is not production._LiveHandle or production._LIVE.get(id(app)) is not handle:
        raise contract.ContractError("real_external_live_handle_required")
    handle.require_for_sender(app)
    policy=_PINNED_ENDPOINT
    if (type(policy) is not EndpointPolicy or policy.wire_digest()!=handle._expected.endpoint_policy_digest
            or not _within_canary_upper(policy.upper_units)):
        raise contract.ContractError("external_endpoint_policy_unbound")
    _request_mode(policy)
    address=ipaddress.ip_address(policy.public_ip)
    if not address.is_global or address.is_multicast or address.is_unspecified or getattr(address,"ipv4_mapped",None):
        raise contract.ContractError("external_endpoint_policy_unbound")
    return policy,address


def _parse_price_basis(price,policy,*,now):
    basis=strict_json(price,cap=16384)
    if (type(basis) is not dict or set(basis)!={"model","currency","scale","max_prompt_tokens","max_output_tokens",
              "peak_input_miss_units_per_million","peak_output_units_per_million",
              "source_url","official_document_sha256","issued_at","valid_until"}
            or (basis["model"],basis["currency"],basis["scale"],basis["max_output_tokens"])!=(
                contract.MODEL,"CNY",6,contract.MAX_OUTPUT_TOKENS)
            or type(basis["max_prompt_tokens"]) is not int or basis["max_prompt_tokens"]!=_WHOLE_CONTEXT_TOKENS
            or basis["source_url"]!="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
            or type(basis["official_document_sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}",basis["official_document_sha256"])
            or type(basis["issued_at"]) is not int or type(basis["valid_until"]) is not int
            or not basis["issued_at"]<=now<basis["valid_until"]<=basis["issued_at"]+86400
            or any(type(basis[name]) is not int or basis[name]<=0 for name in (
                "peak_input_miss_units_per_million","peak_output_units_per_million"))):
        raise contract.ContractError("external_price_basis_unbound")
    numerator=basis["max_prompt_tokens"]*basis["peak_input_miss_units_per_million"]+basis["max_output_tokens"]*basis["peak_output_units_per_million"]
    if not _within_canary_upper(policy.upper_units):
        raise contract.ContractError("external_canary_upper_exceeded")
    if (numerator+999999)//1_000_000>policy.upper_units:
        raise contract.ContractError("external_price_upper_insufficient")
    return basis


def _trust(handle,policy,*,now):
    proof=production._fixed_file(_ACCOUNT_PROOF,16384)
    if digest(proof)!=policy.economic_proof_sha256:
        raise contract.ContractError("external_economic_proof_unbound")
    row=strict_json(proof,cap=16384)
    expected=handle._expected
    if row!={"provider":"deepseek","project":contract.PROJECT,"account_id":expected.account_id,
             "economic_binding":expected.economic_binding,"credential_incarnation":expected.credential_incarnation,
             "funding_epoch":expected.funding_epoch,"ledger_policy_digest":expected.ledger_policy_digest}:
        raise contract.ContractError("external_economic_proof_unbound")
    basis=_price_window(expected,policy,now=now)
    ca=production._fixed_file(_CA,2*1024**2)
    if digest(ca)!=policy.ca_sha256:
        raise contract.ContractError("external_CA_unbound")
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_2
    ctx.load_verify_locations(cadata=ca.decode("ascii"))
    return ctx,basis["valid_until"],basis["max_prompt_tokens"]


def _price_window(expected,policy,*,now):
    if expected.schema_version==18:
        from .external_price_materials import validate_observation,MaterialError
        try:
            return validate_observation(production._fixed_file(_PRICE_PROOF,65536),policy.price_basis_sha256,
                now=now,upper_units=policy.upper_units)
        except (MaterialError,ValueError,TypeError,KeyError,UnicodeError):
            raise contract.ContractError("external_price_basis_unbound") from None
    price=production._fixed_file(_PRICE_PROOF,16384)
    if digest(price)!=policy.price_basis_sha256:
        raise contract.ContractError("external_price_basis_unbound")
    return _parse_price_basis(price,policy,now=now)


def _strict_reply(raw):
    """Consume exactly one 200 response with unambiguous complete framing."""
    if type(raw) is not bytes or len(raw)>_MAX_RESPONSE:
        raise contract.ContractError("external_response_bound")
    header,separator,body=raw.partition(b"\r\n\r\n")
    if not separator or len(header)>16384:
        raise contract.ContractError("external_receipt_framing")
    lines=header.split(b"\r\n")
    if not lines or not re.fullmatch(rb"HTTP/1\.[01] 200(?: [ -~]*)?",lines[0]):
        raise contract.ContractError("external_receipt_unverified")
    framing={}
    for line in lines[1:]:
        name,sep,value=line.partition(b":")
        if (not sep or not re.fullmatch(rb"[A-Za-z0-9!#$%&'*+.^_`|~-]+",name)
                or not re.fullmatch(rb"[\t -~]*",value)):
            raise contract.ContractError("external_receipt_framing")
        name=name.lower()
        if name in (b"content-length",b"transfer-encoding",b"content-encoding"):
            if name in framing:
                raise contract.ContractError("external_receipt_framing")
            framing[name]=value.strip(b" \t")
    if framing.get(b"content-encoding",b"identity").lower()!=b"identity":
        raise contract.ContractError("external_receipt_framing")
    length=framing.get(b"content-length")
    transfer=framing.get(b"transfer-encoding")
    if (length is None)==(transfer is None):
        raise contract.ContractError("external_receipt_framing")
    if length is not None:
        if not re.fullmatch(rb"0|[1-9][0-9]{0,6}",length) or int(length)!=len(body):
            raise contract.ContractError("external_receipt_framing")
        return body
    if transfer.lower()!=b"chunked":
        raise contract.ContractError("external_receipt_framing")
    out=bytearray()
    offset=0
    while offset<len(body):
        end=body.find(b"\r\n",offset)
        if end<0 or not re.fullmatch(rb"[a-fA-F0-9]{1,6}",body[offset:end]):
            raise contract.ContractError("external_receipt_framing")
        count=int(body[offset:end],16);offset=end+2
        if count==0:
            if body[offset:]!=b"\r\n":raise contract.ContractError("external_receipt_framing")
            return bytes(out)
        end=offset+count
        if end+2>len(body) or body[end:end+2]!=b"\r\n" or len(out)+count>_MAX_RESPONSE:
            raise contract.ContractError("external_receipt_framing")
        out.extend(body[offset:end]);offset=end+2
    raise contract.ContractError("external_receipt_framing")


def _exchange(handle,policy,address,context,method,path,payload,first_send):
    if (sys._getframe(1).f_code is not run_once.__code__ or (method,path) not in (("GET",_BALANCE),("POST",_COMPLETION))
            or (method=="GET" and payload)
            or (method=="POST" and (type(getattr(first_send,"__self__",None)) is not _Ticket or first_send.__self__.raw!=payload))):
        raise contract.ContractError("external_target_rejected")
    end=time.monotonic()+10.0
    def left():
        remain=end-time.monotonic()
        if remain<=0:raise TimeoutError("external response deadline")
        return remain
    family=socket.AF_INET6 if address.version==6 else socket.AF_INET
    sock=socket.socket(family,socket.SOCK_STREAM)
    tls=None
    try:
        sock.settimeout(left())
        sock.connect((str(address),443,0,0) if address.version==6 else (str(address),443))
        sock.settimeout(left())
        tls=context.wrap_socket(sock,server_hostname=_HOST)
        # This is the sole credential use; no environment, DNS, proxy,
        # redirect or arbitrary method/host enters the request.
        header=(f"{method} {path} HTTP/1.1\r\nHost: {_HOST}\r\nConnection: close\r\n"
                "Content-Type: application/json\r\nAccept-Encoding: identity\r\nAuthorization: Bearer ").encode()
        wire=header+bytes(handle._resource._raw)+f"\r\nContent-Length: {len(payload)}\r\n\r\n".encode()+payload
        tls.settimeout(left())
        first_send(tls,wire,end)
        raw=bytearray()
        while len(raw)<=_MAX_RESPONSE:
            tls.settimeout(left())
            chunk=tls.recv(min(4096,_MAX_RESPONSE+1-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        if len(raw)>_MAX_RESPONSE:
            raise contract.ContractError("external_response_bound")
        return _strict_reply(bytes(raw))
    finally:
        (tls if tls is not None else sock).close()


def _balance_units(raw):
    response=strict_json(raw,cap=_MAX_RESPONSE)
    if type(response) is not dict or response.get("is_available") is not True or type(response.get("balance_infos")) is not list:
        raise contract.ContractError("official_balance_unverified")
    rows=[row for row in response["balance_infos"] if type(row) is dict and row.get("currency")=="CNY"]
    if len(rows)!=1:
        raise contract.ContractError("official_balance_unverified")
    number=rows[0].get("total_balance")
    if type(number) is not str or not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,6})?",number):
        raise contract.ContractError("official_balance_unverified")
    major,_,minor=number.partition(".")
    units=int(major)*1_000_000+int(minor.ljust(6,"0"))
    if units>(1<<63)-1:raise contract.ContractError("official_balance_unverified")
    return units


@dataclass(frozen=True,slots=True,repr=False)
class _Grant:
    scope:object
    quote:object
    preview:object
    account_id:str
    binding:str
    epoch:int
    balance:int
    valid_until:int
    token:object


class _Writer(file_writer.CandidateFileWriter):
    def __init__(self,app,handle,service,identity,grant,source,decision_digest,key):
        if sys._getframe(1).f_code is not run_once.__code__ or type(grant) is not _Grant or grant.token is not _TOKEN:
            raise contract.ContractError("external_balance_grant_required")
        self.app,self.handle,self.service,self.identity,self.grant=app,handle,service,identity,grant
        self.source,self.decision_digest,self.key=source,decision_digest,key
        self.conn=None
        self._expect=self._money=None

    @contextmanager
    def _transaction(self):
        _require_live(self.handle,self.app)
        with self.service.authorization.owner_gate(self.grant.scope.principal_id),self.service.store.transaction(write=True) as conn:
            if getattr(conn,"private_storage_identity",None)!=self.service.store.storage_identity or self.service.store is not self.handle._binding.service.store:
                raise contract.ContractError("external_ledger_identity_changed")
            self.conn=conn
            conn.create_function(GUARD,3,self._allow_run)
            conn.create_function(file_writer.MONEY_GUARD,2,self._allow_external_money)
            try:
                if self.handle._expected.schema_version==18 and hasattr(self,'_room_consuming'):
                    from importlib import import_module
                    family='web.backend.research' if __package__=='web.backend.services' else 'research'
                    import_module(family+'.external_funding_v18').require_room(conn,self.grant.quote.upper_units,
                        excluding=(TABLE,self.key),consuming=self._room_consuming)
                yield
            finally:
                file_writer.install_closed_hooks(conn)
                self.conn=None

    def _fence(self,grant,scope):
        if grant is not self.grant or grant.scope!=scope:
            raise contract.ContractError("revision_or_owner_changed")
        current=self.service.authorization.check(self.conn,self.identity,scope.principal_id,scope.research_id,scope="write")
        owner=self.service.authorization.check(self.conn,self.identity,scope.principal_id)
        row=self.conn.execute("SELECT digest FROM research_revisions WHERE research_id=? AND revision=?",
                              (scope.research_id,scope.input_revision)).fetchone()
        if (row is None or (current["current_revision"],current["version"],current["owner_epoch"],current["acl_epoch"],
                           owner["epoch"],self.identity.generation,row[0])!=(scope.input_revision,scope.research_version,
                           scope.owner_epoch,scope.acl_epoch,scope.principal_epoch,scope.auth_generation,scope.problem_digest)):
            raise contract.ContractError("revision_or_owner_changed")
        if self.handle._expected.schema_version!=18 and getattr(self,"_check_legacy_unknown",False) and file_writer.unresolved(self.conn,grant.account_id):
            raise contract.ContractError("legacy_unknown_reconcile_only")

    def _account(self,grant):
        if self.handle._expected.schema_version==18:
            from importlib import import_module
            family='web.backend.research' if __package__=='web.backend.services' else 'research'
            funding=import_module(family+'.external_funding_v18').read_binding(self.conn)
            expected=self.handle._expected
            if funding is None or funding['status']!='active' or (funding['account_id'],funding['local_binding_ref'],funding['owner_principal'],
                    funding['owner_generation'],funding['credential_incarnation'],funding['authorization_event_ref'],
                    funding['funding_epoch'])!=(grant.account_id,grant.binding,grant.scope.principal_id,
                    grant.scope.auth_generation,expected.credential_incarnation,expected.authorization_event_ref,grant.epoch):
                raise contract.ContractError('external_owner_funding_changed')
            account=file_writer.FixtureWriter._account(self,grant)
        else:
            account=super()._account(grant)
        self.current_account=account
        return account

    def reserve(self,run_id,grant,scope,*,now):
        self._room_consuming=False
        try:return super().reserve(run_id,grant,scope,now=now)
        finally:del self._room_consuming

    def consume(self,run_id,grant,scope,*,now):
        self._room_consuming=True
        try:return super().consume(run_id,grant,scope,now=now)
        finally:del self._room_consuming

    def finish_live(self,run_id,receipt,body):
        if sys._getframe(1).f_code is not run_once.__code__:
            raise contract.ContractError("external_owned_return_required")
        with self._transaction():
            run=self._row(run_id,self.grant)
            if run["state"]!="consumed":raise contract.ContractError("reconcile_original_only")
            self._fence(self.grant,self.grant.scope)
            account=self._account(self.grant)
            self._update_money(account,held=account[4]-run["upper_units"],booked=account[5]+run["upper_units"])
            self._change(run,state="returned",receipt_digest=receipt,candidate_digest=digest(body),candidate_json=body.decode())


class _Ticket:
    __slots__=("writer","run","raw","pid","used","account")
    def __init__(self,writer,run,raw):
        if sys._getframe(1).f_code is not run_once.__code__:
            raise contract.ContractError("external_consumption_ticket_required")
        self.writer,self.run,self.raw,self.pid,self.used=writer,run,raw,os.getpid(),False
        self.account=writer.current_account

    def first_write(self,sock,wire,deadline):
        if (sys._getframe(1).f_code is not _exchange.__code__ or self.used or self.pid!=os.getpid() or self.run!=self.writer.key
                or not wire.startswith(b"POST /chat/completions HTTP/1.1\r\n") or not wire.endswith(self.raw)):
            raise contract.ContractError("reconcile_original_only")
        # Burn the ephemeral permission before any potentially ambiguous send.
        self.used=True
        w=self.writer;scope=w.grant.scope
        with w.service.authorization.owner_gate(scope.principal_id),production.wire_latch():
            # Recheck after the possibly blocking Owner lease. Retirement
            # cannot zero the live resource until this bounded first write ends.
            _require_live(w.handle,w.app)
            require_authenticated_action(w.source,identity=w.identity,action="external-answer-confirm",
                research_id=scope.research_id,task_id=str(scope.input_revision),key=w.key,body_digest=w.decision_digest)
            with w.service.store.transaction() as conn:
                if w.handle._expected.schema_version==18:
                    from importlib import import_module
                    family='web.backend.research' if __package__=='web.backend.services' else 'research'
                    import_module(family+'.external_funding_v18').require_room(conn,w.grant.quote.upper_units,
                        excluding=(TABLE,self.run),consuming=True)
                control=w.service.authorization.check(conn,w.identity,scope.principal_id,scope.research_id,scope="write")
                row=conn.execute("SELECT state,request_digest,account_id FROM "+TABLE+" WHERE id=?",(self.run,)).fetchone()
                money=conn.execute("""SELECT id,binding_id,funding_epoch,settled,held,upper_booked,version
                    FROM research_funding_accounts WHERE id=? AND status='unverified' AND provider='deepseek'
                    AND currency='CNY' AND scale=6 AND cap=0""",(w.grant.account_id,)).fetchone()
                if (row is None or tuple(row)!=("consumed",digest(self.raw),w.grant.account_id)
                        or money is None or tuple(money)!=self.account or money[4]<w.grant.quote.upper_units
                        or file_writer.unresolved(conn,w.grant.account_id,excluding_external=self.run)
                        or (control["current_revision"],control["version"],control["owner_epoch"],control["acl_epoch"])!=(
                           scope.input_revision,scope.research_version,scope.owner_epoch,scope.acl_epoch)):
                    raise contract.ContractError("external_consumption_fence_changed")
            remaining=deadline-time.monotonic()
            if remaining<=0 or int(time.time())>=min(w.grant.valid_until,w.grant.quote.valid_until):
                raise TimeoutError("external first-write deadline")
            if _require_live(w.handle,w.app)[0].request_mode=="canary":
                production.claim_p1_before_first_write(w.app,w.handle,w.key)
            else:
                production.claim_saved_question_before_first_write(w.app,w.handle,w.key)
            remaining=deadline-time.monotonic()
            if remaining<=0 or int(time.time())>=min(w.grant.valid_until,w.grant.quote.valid_until):
                raise TimeoutError("external first-write deadline")
            if w.handle._expected.schema_version==18:
                _price_window(w.handle._expected,_require_live(w.handle,w.app)[0],now=int(time.time()))
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError("external first-write deadline")
            sock.settimeout(remaining)
            sock.sendall(wire)


def _candidate(raw,*,max_prompt_tokens=_WHOLE_CONTEXT_TOKENS):
    reply=strict_json(raw,cap=_MAX_RESPONSE)
    if type(reply) is not dict or reply.get("model")!=contract.MODEL or not isinstance(reply.get("id"),str):
        raise contract.ContractError("external_receipt_unverified")
    usage=reply.get("usage")
    if (type(usage) is not dict or any(type(usage.get(k)) is not int or usage[k]<0 for k in (
            "prompt_tokens","completion_tokens","total_tokens"))
            or usage["prompt_tokens"]>max_prompt_tokens or usage["completion_tokens"]>contract.MAX_OUTPUT_TOKENS
            or usage["total_tokens"]!=usage["prompt_tokens"]+usage["completion_tokens"]):
        raise contract.ContractError("external_usage_unknown")
    choices=reply.get("choices")
    if type(choices) is not list or len(choices)!=1 or choices[0].get("finish_reason")!="stop":
        raise contract.ContractError("external_receipt_unverified")
    candidate=choices[0]["message"]["content"]
    return canonical(contract.parse_unverified_candidate(candidate.encode()))


def run_once(app,handle,service,identity,rid,revision,research_version,key,preview,quote,confirmation,*,source=None,quote_proof=None):
    """Candidate sender port. No caller-provided transport or balance."""
    policy,address=_require_live(handle,app)
    if service.store is not handle._binding.service.store:
        raise contract.ContractError("external_ledger_identity_changed")
    key=service._id(key)
    _request_binding(policy,key,confirmation.request_digest)
    decision_digest=digest(canonical(confirmation.model_dump(mode="json")))
    require_authenticated_action(source,identity=identity,action="external-answer-confirm",
        research_id=rid,task_id=str(revision),key=key,body_digest=decision_digest)
    from .external_live_operations import require_offered
    require_offered(quote_proof,handle,service,identity,rid,revision,preview,quote,confirmation,operation_key=key)
    now=int(time.time())
    original=None
    with _authorized_saved_revision(service,identity,rid,revision,research_version) as (conn,scope,raw):
        approved=contract.compare_confirmation(preview,scope,raw,quote,confirmation,now=now)
        binding=handle._expected
        if ((scope.principal_id,scope.auth_generation,quote.account_id,quote.economic_binding,quote.funding_epoch)
                !=(binding.owner_principal,binding.owner_generation,binding.account_id,binding.economic_binding,binding.funding_epoch)
                or (quote.price_basis_digest,quote.upper_units)!=(policy.price_basis_sha256,policy.upper_units)):
            raise contract.ContractError("external_quote_or_funding_changed")
        original=conn.execute("SELECT preview_digest,request_digest,upper_units FROM "+TABLE+
            " WHERE id=? AND research_id=? AND principal_id=? AND input_revision=?",
            (key,rid,scope.principal_id,revision)).fetchone()
        if original is not None:
            if tuple(original)!=(confirmation.preview_digest,confirmation.request_digest,confirmation.upper_units):
                raise contract.ContractError("confirmation_binding_changed")
        elif conn.execute("SELECT 1 FROM "+TABLE+" WHERE research_id=? AND input_revision=?",
                          (rid,revision)).fetchone() or file_writer.unresolved(conn,quote.account_id):
            raise contract.ContractError("reconcile_original_only")
    if original is not None:
        return read_main_recovery(service,identity,rid,revision,key)
    if production.operation_already_spent(app,handle,key):
        raise contract.ContractError("external_canary_already_spent" if policy.request_mode=="canary" else "external_operation_already_spent")
    context,price_valid_until,prompt_bound=_trust(handle,policy,now=now)
    if quote.valid_until>price_valid_until:raise contract.ContractError("external_quote_expired")
    def balance_first(sock,wire,deadline):
        with service.authorization.owner_gate(scope.principal_id),production.wire_latch():
            _require_live(handle,app)
            require_authenticated_action(source,identity=identity,action="external-answer-confirm",
                research_id=rid,task_id=str(revision),key=key,body_digest=decision_digest)
            with service.store.transaction() as conn:
                control=service.authorization.check(conn,identity,scope.principal_id,rid,scope="write")
                if (control["current_revision"],control["version"],control["owner_epoch"],control["acl_epoch"])!=(
                        scope.input_revision,scope.research_version,scope.owner_epoch,scope.acl_epoch):
                    raise contract.ContractError("revision_or_owner_changed")
                if (conn.execute("SELECT 1 FROM "+TABLE+" WHERE research_id=? AND input_revision=?",
                                 (rid,revision)).fetchone() or file_writer.unresolved(conn,quote.account_id)):
                    raise contract.ContractError("reconcile_original_only")
            remaining=deadline-time.monotonic()
            if production.operation_already_spent(app,handle,key):
                raise contract.ContractError("external_canary_already_spent" if policy.request_mode=="canary" else "external_operation_already_spent")
            if remaining<=0:raise TimeoutError("external balance deadline")
            if handle._expected.schema_version==18:
                _price_window(handle._expected,policy,now=int(time.time()))
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError("external balance deadline")
            sock.settimeout(remaining)
            sock.sendall(wire)
    balance=_balance_units(_exchange(handle,policy,address,context,"GET",_BALANCE,b"",balance_first))
    now=int(time.time())
    grant=_Grant(scope,quote,approved,quote.account_id,quote.economic_binding,quote.funding_epoch,balance,now+30,_TOKEN)
    writer=_Writer(app,handle,service,identity,grant,source,decision_digest,key)
    writer.confirm(key,grant,scope)
    writer.reserve(key,grant,scope,now=now)
    outbound=writer.consume(key,grant,scope,now=now)
    ticket=_Ticket(writer,key,outbound)
    try:
        returned=_exchange(handle,policy,address,context,"POST",_COMPLETION,outbound,ticket.first_write)
        writer.finish_live(key,digest(returned),_candidate(returned,max_prompt_tokens=prompt_bound))
    except Exception:
        # If even marking UNKNOWN fails, consumed still projects as unknown,
        # and the original held upper remains. Never re-run the POST.
        try:writer.finish(key,grant,scope)
        except Exception:pass
    return read_main_recovery(service,identity,rid,revision,key)
