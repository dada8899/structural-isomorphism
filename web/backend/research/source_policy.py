"""Fixed-host D1 GET transport; no keys, redirects, automatic retries or JS.

All DNS, connect, TLS, headers, wire/decompressed reads happen in an owned
spawned process. The parent enforces an independent wall deadline and reaps it.
The canonical Source session supplies the external-send boundary. DOC additionally
requires its actual governor flight and a first protected SENDING witness.
"""
from dataclasses import dataclass
import http.client
import io
import ipaddress
import multiprocessing
from multiprocessing.reduction import recv_handle
import os
import signal
import stat
import socket
import ssl
import time
import zlib
import inspect
import threading
from urllib.parse import urlencode

from .authorization import OwnerGateLease


RAW_CAP = 2 * 1024 * 1024
TEXT_CAP = 200000
HEADER_CAP = 16384
WALL_SECONDS = 12.0


class SourceFailure(ValueError):
    def __init__(self, message, *, http_status=None):
        super().__init__(message)
        if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
            raise ValueError("invalid HTTP observation")
        self.http_status = http_status


@dataclass(frozen=True)
class RequestTarget:
    host: str
    path: str

    def __post_init__(self):
        # Targets can only be constructed by the two fixed request factories.
        from urllib.parse import parse_qs, urlsplit
        import re
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc or parsed.fragment:
            raise SourceFailure("invalid target")
        query = parse_qs(parsed.query, strict_parsing=True)
        if self.host == "api.crossref.org" and parsed.path == "/works":
            if (set(query) != {"query", "filter", "rows", "select"} or query["filter"] != ["prefix:10.1371"]
                    or query["rows"] != ["3"] or query["select"] != ["DOI,title,license"]):
                raise SourceFailure("invalid discovery target")
            if len(query["query"]) != 1 or re.fullmatch(r"[A-Za-z][A-Za-z -]{2,159}", query["query"][0]) is None:
                raise SourceFailure("invalid academic query")
        elif self.host == "journals.plos.org" and parsed.path == "/plosone/article":
            if set(query) != {"id"} or len(query["id"]) != 1 or re.fullmatch(r"10\.1371/journal\.pone\.[0-9]{7}", query["id"][0]) is None:
                raise SourceFailure("invalid article target")
        else:
            raise SourceFailure("unregistered source target")
        if len(self.path) > 512 or any(ord(c) < 33 or ord(c) > 126 for c in self.path):
            raise SourceFailure("invalid request path")


def discovery_target(query):
    # Do not request abstracts: metadata openness does not license every abstract.
    return RequestTarget("api.crossref.org", "/works?" + urlencode({"query": query, "filter": "prefix:10.1371", "rows": "3", "select": "DOI,title,license"}))


def article_target(doi):
    return RequestTarget("journals.plos.org", "/plosone/article?" + urlencode({"id": doi}))


def public_addresses(host, resolver=socket.getaddrinfo):
    results = resolver(host, 443, type=socket.SOCK_STREAM)
    addresses = []
    for family, socktype, protocol, _, sockaddr in results:
        if family not in (socket.AF_INET, socket.AF_INET6) or socktype != socket.SOCK_STREAM:
            raise SourceFailure("invalid DNS address family")
        address = ipaddress.ip_address(sockaddr[0])
        if (not address.is_global or address.is_multicast or address.is_unspecified or address.is_reserved
                or getattr(address, "ipv4_mapped", None) is not None or "%" in sockaddr[0]):
            raise SourceFailure("nonpublic source address")
        if str(address) not in addresses:
            addresses.append(str(address))
    if not addresses:
        raise SourceFailure("no public source address")
    return addresses


def decompress(data, encoding):
    if len(data) > RAW_CAP:
        raise SourceFailure("raw body limit")
    if encoding in ("", "identity"):
        return data
    if encoding != "gzip":
        raise SourceFailure("unsupported content encoding")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        output = decoder.decompress(data, RAW_CAP + 1)
    except zlib.error:
        raise SourceFailure("invalid compressed source") from None
    if len(output) > RAW_CAP or decoder.unconsumed_tail:
        raise SourceFailure("decompressed body limit")
    if not decoder.eof or decoder.unused_data:
        raise SourceFailure("incomplete or concatenated gzip source")
    return output


class _Reader(io.RawIOBase):
    def __init__(self, sock, prefix):
        self.sock, self.prefix, self.received = sock, bytearray(prefix), 0
        # Passive bounded evidence only. Legacy paper parsing is unchanged;
        # DOC rejects interim responses before HTTPResponse.begin can skip one.
        self.header_prefix=bytes(prefix[:HEADER_CAP+1])

    def readable(self):
        return True

    def readinto(self, buffer):
        # Includes chunk framing; a bounded framing allowance is separate from
        # the compressed-body cap enforced by the HTTPResponse consumer.
        remaining = RAW_CAP + HEADER_CAP + 65536 - self.received
        if remaining <= 0:
            raise SourceFailure("wire response limit")
        count = min(len(buffer), remaining)
        if self.prefix:
            data = self.prefix[:count]
            del self.prefix[:count]
        else:
            data = self.sock.recv(count)
        buffer[:len(data)] = data
        self.received += len(data)
        return len(data)


class _ResponseSocket:
    def __init__(self, sock, header):
        self.sock, self.header = sock, header

    def makefile(self, mode):
        return io.BufferedReader(_Reader(self.sock, self.header), buffer_size=8192)


_DOC_CHILD=None
_DOC_FACTORY=object()
_DOC_OUTCOMES={}
_DOC_RETIREMENTS={}


def _doc_now():
    from datetime import datetime,timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')


def _doc_header(prefix):
    """One complete final DOC header, bounded before the HTTP parser runs."""
    end=prefix.find(b'\r\n\r\n')
    if end<0 or end+4>HEADER_CAP:raise SourceFailure('DOC response header limit')
    status_line=bytes(prefix[:end]).split(b'\r\n',1)[0].split(None,2)
    if (len(status_line)<2 or status_line[0] not in (b'HTTP/1.0',b'HTTP/1.1')
            or len(status_line[1])!=3 or not status_line[1].isdigit()):raise SourceFailure('DOC response status unavailable')
    status=int(status_line[1])
    if not 200<=status<=599:
        raise SourceFailure('DOC final response required',http_status=status if 100<=status<=599 else None)
    return status


def _require_doc_child(wire):
    from .source_document_raw import DocWireTarget,decode_doc_wire
    from .source_document_access import (APPROVED_DIGEST,APPROVED_FROM,APPROVED_UNTIL,approved_references,
        material_bytes,material_data,_stamp)
    from .evidence_schemas import sha256
    from dataclasses import asdict
    context=_DOC_CHILD
    if (type(wire) is not DocWireTarget or context is None or context[0]!=os.getpid() or context[1] is not wire
            or inspect.currentframe().f_back.f_code is not _network_get.__code__
            or os.geteuid()!=981 or os.getegid()!=976 or wire.send_not_after>context[4]
            or (wire.valid_from,wire.expires_at)!=(APPROVED_FROM,APPROVED_UNTIL)
            or time.monotonic()>=min(context[4],wire.send_not_after)
            or not _stamp(wire.valid_from).timestamp()<=time.time()<_stamp(wire.expires_at).timestamp()):
        raise PermissionError('actual bounded DOC child required')
    decode_doc_wire(asdict(wire))
    ref,rights=approved_references()
    if wire.access_profile_ref!=ref or wire.rights_digest!=rights or sha256(material_bytes(material_data(APPROVED_FROM,wire.user_agent)))!=APPROVED_DIGEST:
        raise PermissionError('DOC private material differs')
    info=os.fstat(context[2])
    if (info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)!=context[3]:
        raise PermissionError('DOC transferred lease differs')


def _doc_response(wire,response,sent_at):
    """Observe one response. Rejected/partial bodies never leave this child."""
    from .source_document_raw import DocObservation
    from .evidence_schemas import sha256
    status=response.status
    if type(response) is http.client.HTTPResponse:
        reader=getattr(response.fp,'raw',None)
        if type(reader) is _Reader:_doc_header(reader.header_prefix)
    def bounded_header(name,limit):
        value=response.getheader(name)
        if value is not None and (not value or len(value)>limit or any(ord(c)<32 or ord(c)>126 for c in value)):
            raise SourceFailure('DOC response header invalid',http_status=status)
        return value
    content_type=bounded_header('Content-Type',300)
    content_encoding=bounded_header('Content-Encoding',64)
    transfer=bounded_header('Transfer-Encoding',64)
    location=bounded_header('Location',512)
    length_text=bounded_header('Content-Length',24)
    if length_text is not None and (not length_text.isdecimal() or int(length_text)>9223372036854775807):
        raise SourceFailure('DOC response length invalid',http_status=status)
    length=int(length_text) if length_text is not None else None
    media=content_type.split(';',1)[0].strip().lower() if content_type else None
    data=dict(requested_target=wire.target,observed_final_target=wire.target,http_status=status,
        content_type_header=content_type,media_type=media,content_encoding_header=content_encoding,
        effective_content_encoding=None,content_length=length,transfer_encoding_header=transfer,
        location_header=location,attempted_at=wire.attempted_at,request_sent_at=sent_at,received_at=None,
        observed_failure_at=None,safe_code='invalid_source',body_complete=False,raw_length=None,
        raw_sha256=None,observed_lower_bound=None,job_digest=wire.job_digest)
    raw=b''
    if type(status) is not int or not 100<=status<=599:raise SourceFailure('DOC response status invalid')
    if status!=200:
        data['safe_code']='access_denied' if status in (401,403,429) else 'unavailable'
    elif (transfer not in (None,'chunked') or (transfer is not None and length is not None)
            or (content_encoding is not None and content_encoding.strip().lower()!='identity')):
        pass
    elif length is not None and length>RAW_CAP:
        data['safe_code']='limit'
    else:
        try:raw=response.read(RAW_CAP+1)
        except (OSError,http.client.IncompleteRead) as error:
            raise SourceFailure('DOC response outcome unknown',http_status=status) from error
        if len(raw)>RAW_CAP:
            raw=b'';data.update(safe_code='limit',observed_lower_bound=RAW_CAP+1)
        elif length is not None and len(raw)!=length:
            raise SourceFailure('DOC incomplete response body',http_status=status)
        elif not raw:
            raw=b''
        else:
            # This is a quarantine classifier, never document identity/parser
            # verification. Preserve full 200 bytes for independent inspection.
            soft=any(marker in raw[:65536].lower() for marker in
                (b'access denied',b'captcha',b'undeclared automated tool',b'request rate threshold',b'your request originates'))
            data.update(effective_content_encoding='identity',body_complete=True,raw_length=len(raw),raw_sha256=sha256(raw),
                received_at=_doc_now(),safe_code='access_denied' if soft else 'none' if media=='text/html' else 'invalid_source')
    if not data['body_complete']:data['observed_failure_at']=_doc_now()
    return DocObservation(**data),raw


class ActualDocOutcome:
    __slots__=('flight','observation','raw','retirement','pid','thread','_factory')
    def __init__(self,flight,observation,raw,*,_factory=None):
        if _factory is not _DOC_FACTORY or inspect.currentframe().f_back.f_code is not PinnedPublicTransport.get.__code__:
            raise PermissionError('actual DOC transport outcome required')
        self.flight,self.observation,self.raw,self.retirement=flight,observation,raw,None
        self.pid,self.thread,self._factory=os.getpid(),threading.current_thread(),_factory
        _DOC_OUTCOMES[id(self)]=(self,flight,observation,raw,self.pid,self.thread)
    def __repr__(self):return '<native DOC outcome>'
    def __reduce__(self):raise TypeError('DOC outcome cannot be serialized')


class ActualTransportRetirement:
    __slots__=('flight','process','popen','connections','monotonic_at','audit','pid','thread','_factory')
    def __init__(self,flight,process,popen,connections,*,_factory=None):
        if _factory is not _DOC_FACTORY or inspect.currentframe().f_back.f_code is not PinnedPublicTransport.get.__code__:
            raise PermissionError('original DOC retirement required')
        # The real Process.close has retired its private Popen and tracker.
        if (process is not flight.process or popen is not flight.popen or not process._closed
                or (popen is not None and (popen.sender is not None and popen.sender.poll() is None
                    or popen._owned_fds or popen.tracker is not None and
                    (popen.tracker._owned_fds or popen.tracker.process is not None)))
                or any(not connection.closed for connection in connections)):
            raise PermissionError('DOC actual resources remain')
        from .source_document_raw import TransportRetirementAudit
        self.flight,self.process,self.popen,self.connections=flight,process,popen,connections
        self.monotonic_at,self.pid,self.thread,self._factory=time.monotonic(),os.getpid(),threading.current_thread(),_factory
        self.audit=TransportRetirementAudit(protocol='doc-transport-retirement-audit-v1',request_id=flight.witness.row['id'],
            dispatch_id=flight.witness.row['dispatch_id'],job_digest=flight.wire.job_digest,retired_at=_doc_now(),
            sender_reaped=True,tracker_reaped=True,ipc_closed=True,pipe_fds_closed=True,buffer_released=True)
        _DOC_RETIREMENTS[id(self)]=(self,flight,process,popen,connections,self.monotonic_at,self.audit,self.pid,self.thread)
    def __repr__(self):return '<native DOC transport retirement>'
    def __reduce__(self):raise TypeError('DOC retirement cannot be serialized')


def require_doc_retirement(value,flight):
    flight.identity()
    if (type(value) is not ActualTransportRetirement or _DOC_RETIREMENTS.get(id(value))!=(value,flight,value.process,value.popen,value.connections,value.monotonic_at,value.audit,value.pid,value.thread)
            or value._factory is not _DOC_FACTORY or value.flight is not flight or value.pid!=os.getpid()
            or value.thread is not threading.current_thread() or value.process is not flight.process
            or value.popen is not flight.popen):raise PermissionError('actual DOC retirement required')
    return value


def require_doc_outcome(value,session):
    if (type(value) is not ActualDocOutcome or _DOC_OUTCOMES.get(id(value))!=(value,value.flight,value.observation,value.raw,value.pid,value.thread)
            or value._factory is not _DOC_FACTORY or value.pid!=os.getpid() or value.thread is not threading.current_thread()
            or value.flight.session is not session or value.flight.outcome is not value
            or value.flight.state!='RETIRED' or value.retirement is not value.flight.retirement):
        raise PermissionError('actual DOC outcome required')
    require_doc_retirement(value.retirement,value.flight)
    return value


def _network_get(target):
    # Revalidate in child. Resolve once and connect the numeric address only;
    # do not re-resolve the hostname during connection or follow Location.
    from .source_document_raw import DocWireTarget
    doc = type(target) is DocWireTarget
    if doc:
        _require_doc_child(target)
    else:
        target = RequestTarget(target.host, target.path)
    ip = public_addresses(target.host)[0]
    context = ssl.create_default_context()
    raw = socket.create_connection((ip, 443), timeout=5)
    try:
        if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(ip):
            raise SourceFailure("source peer mismatch")
        with context.wrap_socket(raw, server_hostname=target.host) as tls:
            tls.settimeout(5)
            if doc:
                _require_doc_child(target)
                sent_at=_doc_now()
                agent,encoding=target.user_agent,'identity'
            else:agent,encoding='StructureMethodEvidence/1','gzip'
            tls.sendall((f"GET {target.path} HTTP/1.1\r\nHost: {target.host}\r\n"
                         f"User-Agent: {agent}\r\nAccept-Encoding: {encoding}\r\nConnection: close\r\n\r\n").encode("ascii"))
            header = bytearray()
            while b"\r\n\r\n" not in header:
                chunk = tls.recv(1024)
                if not chunk:
                    raise SourceFailure("incomplete response headers")
                header.extend(chunk)
                if b"\r\n\r\n" not in header and len(header) > HEADER_CAP:
                    raise SourceFailure("response header limit")
            if header.index(b"\r\n\r\n") + 4 > HEADER_CAP:
                raise SourceFailure("response header limit")
            if doc:_doc_header(header)
            response = http.client.HTTPResponse(_ResponseSocket(tls, header))
            try:
                response.begin()
                if doc:return _doc_response(target,response,sent_at)
                if response.status != 200:
                    # Redirect/403 bodies are not read and cannot become source.
                    raise SourceFailure("source HTTP status " + str(response.status), http_status=response.status)
                if response.getheader("Transfer-Encoding") not in (None, "chunked"):
                    raise SourceFailure("unsupported transfer encoding")
                if response.getheader("Transfer-Encoding") and response.getheader("Content-Length"):
                    raise SourceFailure("ambiguous HTTP framing")
                length = response.getheader("Content-Length")
                if length is not None and (not length.isdecimal() or int(length) > RAW_CAP):
                    raise SourceFailure("raw body limit")
                body = response.read(RAW_CAP + 1)
                if length is not None and len(body) != int(length):
                    raise SourceFailure("incomplete response body")
                decoded = decompress(body, response.getheader("Content-Encoding", "identity").lower())
                return (response.status, response.getheader("Content-Type", ""), body, decoded)
            finally:
                response.close()
    finally:
        raw.close()


def _child(send, target, worker, shared, deadline, identity):
    lease_fd=None
    try:
        # Default OS disposition, not a Python handler: blocking DNS/TLS or
        # native code cannot defer this process-local absolute expiry.
        signal.signal(signal.SIGALRM,signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK,{signal.SIGALRM})
        remaining=deadline-time.monotonic()
        if remaining<=0:
            return
        signal.setitimer(signal.ITIMER_REAL,remaining)
        if time.monotonic()>=deadline:
            return
        send.send_bytes(b'["armed"]')
        lease_fd=recv_handle(send)
        os.set_inheritable(lease_fd,False)
        info=os.fstat(lease_fd)
        actual=(info.st_dev,info.st_ino,info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)
        if (actual!=identity or not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
                or info.st_mode & 0o077 or info.st_nlink!=1 or time.monotonic()>=deadline):
            raise PermissionError("invalid source owner lease")
        from .source_document_raw import DocWireTarget,doc_ipc
        doc=type(target) is DocWireTarget
        if doc:
            global _DOC_CHILD
            from .source_spawn import SourceSpawnProcess
            current=multiprocessing.current_process()
            if (type(current) is not SourceSpawnProcess or current._target is not _child
                    or current._args[1] is not target or worker is not _network_get):
                raise PermissionError('native DOC child required')
            _DOC_CHILD=(os.getpid(),target,lease_fd,identity,deadline)
        value = worker(target)
        if doc:
            observation,raw=value
            if type(raw) is not bytes or len(raw)>RAW_CAP:raise SourceFailure('DOC body limit')
            if observation.body_complete:
                from .evidence_schemas import sha256
                if len(raw)!=observation.raw_length or sha256(raw)!=observation.raw_sha256:raise SourceFailure('DOC observed body differs')
            elif raw:raise SourceFailure('DOC rejected body retained')
            view=memoryview(shared).cast('B')
            try:view[:len(raw)]=raw
            finally:view.release()
            send.send_bytes(doc_ipc(observation))
            return
        # Only bounded, typed results can cross the process boundary.
        status, content_type, raw, decoded = value
        if (type(status) is not int or status != 200 or type(content_type) is not str or len(content_type) > 300
                or type(raw) is not bytes or len(raw) > RAW_CAP or type(decoded) is not bytes or len(decoded) > RAW_CAP):
            raise SourceFailure("invalid transport response")
        import json
        view = memoryview(shared).cast("B")
        view[:len(raw)] = raw
        view[RAW_CAP:RAW_CAP + len(decoded)] = decoded
        # One small atomic pipe message avoids an unbounded parent recv of a
        # partially sent multi-megabyte pickle after poll reports readability.
        send.send_bytes(json.dumps([True, status, content_type, len(raw), len(decoded)]).encode())
    except Exception as exc:
        # No provider body, socket exception text, URL or query in error output.
        try:
            import json
            status = exc.http_status if isinstance(exc, SourceFailure) else None
            send.send_bytes(json.dumps([False, status]).encode())
        except (OSError, EOFError):
            pass  # parent cancelled/timed out and has already closed its end
    finally:
        _DOC_CHILD=None
        if lease_fd is not None:os.close(lease_fd)
        send.close()


class PinnedPublicTransport:
    def __init__(self, *, wall_seconds=WALL_SECONDS, _worker=_network_get):
        if type(wall_seconds) not in (int, float) or not 0 < wall_seconds <= WALL_SECONDS:
            raise ValueError("bounded deadline required")
        self.wall_seconds, self._worker = wall_seconds, _worker
        self.execution_mode = "live" if _worker is _network_get else "offline_probe"

    def get(self, target, *, still_authorized, owner_lease):
        from .source_document_raw import DocTarget,decode_doc_ipc
        doc=type(target) is DocTarget
        flight=outcome=retirement=popen=None
        if doc:
            import types
            from .source_workflow import SourceSession
            from .source_document_access import session_supervisor
            from .source_sec_access import begin_request
            if (type(still_authorized) is not types.MethodType or still_authorized.__func__ is not SourceSession.still_authorized
                    or self._worker is not _network_get):raise SourceFailure('canonical DOC authority required')
            session=still_authorized.__self__;supervisor=session_supervisor(session)
            if session._doc_request is None or session._doc_request.owner is not owner_lease:raise PermissionError('DOC Owner differs')
            doc_deadline=float(time.monotonic()+self.wall_seconds)
            flight=begin_request(supervisor._sec_access,session,target)
            target=flight.wire
        else:target = RequestTarget(target.host, target.path)
        if self.execution_mode!=("live" if self._worker is _network_get else "offline_probe"):
            raise SourceFailure("source transport provenance mismatch")
        if (os.name!="posix" or not all(hasattr(signal,key) for key in ("SIGALRM","ITIMER_REAL","setitimer","pthread_sigmask"))
                or type(owner_lease) is not OwnerGateLease):
            raise SourceFailure("source lifetime boundary unavailable")
        identity=owner_lease.identity
        if not callable(still_authorized) or still_authorized() is not True:
            raise PermissionError("source dispatch denied")
        from .source_spawn import source_process,require_supported
        require_supported()
        ctx = multiprocessing.get_context("spawn")
        receive, send = ctx.Pipe(duplex=True)
        deadline = doc_deadline if doc else time.monotonic() + self.wall_seconds
        process = None
        shared = view = None
        handed_off=False
        def unavailable(message):
            # Kernel expiry can close IPC before the parent's next deadline
            # check. Classify the observed termination without waiting longer
            # or treating an unrelated early EOF/exit as a timeout.
            if time.monotonic()>=deadline or process.exitcode==-signal.SIGALRM:
                return SourceFailure("source hard deadline")
            return SourceFailure(message)
        try:
            shared = ctx.RawArray("B", RAW_CAP * 2)
            process = source_process((send, target, self._worker, shared,deadline,identity))
            process.start()
            popen=process._popen
            send.close()
            while True:
                if still_authorized() is not True:
                    raise PermissionError("source access ended")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SourceFailure("source hard deadline")
                if receive.poll(min(0.025, remaining)):
                    import json
                    try:
                        packet=receive.recv_bytes(4096 if doc else 1024)
                        message = json.loads(packet)
                    except (EOFError, OSError, ValueError):
                        raise unavailable("source worker result unavailable") from None
                    if time.monotonic() >= deadline:
                        raise SourceFailure("source hard deadline")
                    if still_authorized() is not True:
                        raise PermissionError("late source discarded")
                    if not handed_off:
                        if message!=["armed"]:
                            raise SourceFailure("source worker lifetime unavailable")
                        if time.monotonic()>=deadline or still_authorized() is not True:
                            raise PermissionError("source handoff denied")
                        from .source_supervisor import send_handoff_scope
                        with send_handoff_scope(still_authorized,deadline_monotonic=deadline):
                            owner_lease.handoff(receive,process.pid,deadline)
                            handed_off=True
                            if doc:flight.handed_off=True;flight.state='SENT'
                        continue
                    if doc:
                        if type(message) is list:
                            if len(message)==2 and message[0] is False:raise SourceFailure('DOC outcome unknown',http_status=message[1])
                            raise SourceFailure('DOC outcome unknown')
                        observation=decode_doc_ipc(packet,target)
                        view=memoryview(shared).cast('B')
                        raw=bytes(view[:observation.raw_length]) if observation.body_complete else b''
                        from .evidence_schemas import sha256
                        if observation.body_complete and (len(raw)!=observation.raw_length or sha256(raw)!=observation.raw_sha256):
                            raise SourceFailure('DOC original body differs')
                        outcome=ActualDocOutcome(flight,observation,raw,_factory=_DOC_FACTORY)
                        flight.outcome=outcome
                        return outcome
                    if type(message) is list and len(message) == 2 and message[0] is False:
                        raise SourceFailure("source_unavailable", http_status=message[1])
                    if (type(message) is not list or len(message) != 5 or message[0] is not True
                            or message[1] != 200 or type(message[2]) is not str
                            or any(type(n) is not int or not 0 <= n <= RAW_CAP for n in message[3:])):
                        raise SourceFailure("invalid worker result")
                    view = memoryview(shared).cast("B")
                    return (message[1], message[2], bytes(view[:message[3]]), bytes(view[RAW_CAP:RAW_CAP + message[4]]))
                if not process.is_alive():
                    raise unavailable("source worker exited without result")
        finally:
            import sys
            primary=sys.exc_info()[1]
            errors=[]
            for connection in (send,receive):
                try:connection.close()
                except BaseException as error:errors.append(error)
            try:
                if process is not None:process.close()
            except BaseException as error:errors.append(error)
            if not errors:
                try:
                    if view is not None:view.release()
                except BaseException as error:errors.append(error)
            if not errors:
                # Child/tracker and IPC retirement succeeded. Drop only this
                # call's buffer exports, never the allocator's shared arenas.
                # The propagated exception keeps its original traceback; this
                # local alias must not make that traceback retain itself.
                if doc and process is not None and process._closed:
                    # BaseProcess.start deletes these after successful spawn;
                    # a failed start can still retain this call's RawArray.
                    for name in ('_target','_args','_kwargs'):
                        if name in vars(process):delattr(process,name)
                view = shared = primary = None
            if errors:
                from .source_spawn import SourceCleanupUncertain,_cleanup_note
                if doc:flight.unknown(errors[0])
                if primary is not None:
                    _cleanup_note(primary,'Source transport retirement uncertain')
                    raise primary
                raise SourceCleanupUncertain('Source transport retirement uncertain') from errors[0]
            if doc:
                try:
                    # If construction/start failed, the flight still retains
                    # any partial Popen registered before its first resource.
                    popen=flight.popen
                    if process is None:raise PermissionError('DOC sender construction incomplete')
                    retirement=ActualTransportRetirement(flight,process,popen,(send,receive),_factory=_DOC_FACTORY)
                    from .source_sec_access import finish_request
                    finish_request(flight,retirement)
                    if outcome is not None:outcome.retirement=retirement
                except BaseException as error:
                    flight.unknown(error)
                    from .source_spawn import SourceCleanupUncertain
                    debt=SourceCleanupUncertain('DOC transport retirement uncertain');debt._doc_flight=flight
                    raise debt from error
