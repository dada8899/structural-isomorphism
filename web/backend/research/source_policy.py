"""Fixed-host D1 GET transport; no keys, redirects, automatic retries or JS.

All DNS, connect, TLS, headers, wire/decompressed reads happen in an owned
spawned process. The parent enforces an independent wall deadline and reaps it.
This transport is unwired: the caller must hold/consume C0's external-send
permit at the start boundary and persist request quota/unknown state there.
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


def _network_get(target):
    # Revalidate in child. Resolve once and connect the numeric address only;
    # do not re-resolve the hostname during connection or follow Location.
    target = RequestTarget(target.host, target.path)
    ip = public_addresses(target.host)[0]
    context = ssl.create_default_context()
    raw = socket.create_connection((ip, 443), timeout=5)
    try:
        if ipaddress.ip_address(raw.getpeername()[0]) != ipaddress.ip_address(ip):
            raise SourceFailure("source peer mismatch")
        with context.wrap_socket(raw, server_hostname=target.host) as tls:
            tls.settimeout(5)
            tls.sendall((f"GET {target.path} HTTP/1.1\r\nHost: {target.host}\r\n"
                         "User-Agent: StructureMethodEvidence/1\r\nAccept-Encoding: gzip\r\nConnection: close\r\n\r\n").encode("ascii"))
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
            response = http.client.HTTPResponse(_ResponseSocket(tls, header))
            try:
                response.begin()
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
        value = worker(target)
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
        if lease_fd is not None:os.close(lease_fd)
        send.close()


class PinnedPublicTransport:
    def __init__(self, *, wall_seconds=WALL_SECONDS, _worker=_network_get):
        if type(wall_seconds) not in (int, float) or not 0 < wall_seconds <= WALL_SECONDS:
            raise ValueError("bounded deadline required")
        self.wall_seconds, self._worker = wall_seconds, _worker
        self.execution_mode = "live" if _worker is _network_get else "offline_probe"

    def get(self, target, *, still_authorized, owner_lease):
        target = RequestTarget(target.host, target.path)
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
        deadline = time.monotonic() + self.wall_seconds
        process = None
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
                        message = json.loads(receive.recv_bytes(1024))
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
                        owner_lease.handoff(receive,process.pid,deadline)
                        handed_off=True
                        continue
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
            if errors:
                from .source_spawn import SourceCleanupUncertain,_cleanup_note
                if primary is not None:
                    _cleanup_note(primary,'Source transport retirement uncertain')
                    raise primary
                raise SourceCleanupUncertain('Source transport retirement uncertain') from errors[0]
