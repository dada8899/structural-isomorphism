"""Pure live boundary/framing controls, never a synthetic live activation.

These tests never publish an entry witness, grant, session or C slot and never
resolve DNS. Owned synthetic files/socketpairs exercise only local helpers.
"""
import ast
import errno
import json
import os
from pathlib import Path
import pickle
import socket
import stat
import time
from types import SimpleNamespace

import pytest
from research.errors import ResearchError
from services import native_live_credentials as credentials
from services import native_dns_process as dns
from services import plan_runtime_transport as transport


def parse(wire, limit=65536, split=7):
    parser=transport._LiveHTTPParser(limit)
    for start in range(0,len(wire),split):parser.feed(wire[start:start+split])
    return parser.finish()


@pytest.mark.parametrize('split',[1,2,7,16384])
@pytest.mark.parametrize('wire',[
    b'HTTP/1.1 200 OK\r\nContent-Length: 4\r\n\r\n{}\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\n{\r\n1\r\n}\r\n0\r\n\r\n',
    b'HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n{}',
])
def test_live_framing_split_reads_are_data_only(wire,split):
    status,body=parse(wire,split=split)
    assert status==200 and body.strip()==b'{}'


@pytest.mark.parametrize('wire',[
    b'HTTP/1.1 302 Redirect\r\nContent-Length: 0\r\n\r\n',
    b'HTTP/1.1 100 Continue\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Length: 0\r\n\r\n0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nContent-Encoding: gzip\r\n\r\nx',
    b'HTTP/1.1 200 OK\r\nContent-Length: +1\r\n\r\nx',
    b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nx',
    b'HTTP/1.1 200 OK\r\nContent-Length: 1\r\n\r\nxx',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: identity\r\n\r\nx',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1;x=y\r\nx\r\n0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx!\r\n0\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\nX-Trailer: refused\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n1\r\nx\r\n',
    b'HTTP/1.1 200 OK\r\nBad Header: x\r\n\r\n',
    b'HTTP/1.1 200 OK\r\nX: a\x00b\r\n\r\n',
])
def test_live_framing_rejects_ambiguity_redirect_or_incomplete(wire):
    with pytest.raises(ValueError):parse(wire,split=3)


@pytest.mark.parametrize('limit',[65536,393216])
def test_live_body_limits_and_declared_oversize_reject_before_body(limit):
    head=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(limit).encode()+b'\r\n\r\n'
    assert parse(head+b'x'*limit,limit=limit,split=16384)==(200,b'x'*limit)
    with pytest.raises(ValueError):parse(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(limit+1).encode()+b'\r\n\r\n',limit=limit)
    with pytest.raises(ValueError):parse(b'HTTP/1.0 200 OK\r\n\r\n'+b'x'*(limit+1),limit=limit,split=16384)


def test_live_header_chunk_count_line_and_wire_bounds():
    with pytest.raises(ValueError):parse(b'HTTP/1.1 200 OK\r\nX: '+b'x'*16384)
    head=b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
    assert len(parse(head+b'1\r\nx\r\n'*1023+b'0\r\n\r\n',split=17)[1])==1023
    with pytest.raises(ValueError):parse(head+b'1\r\nx\r\n'*1024+b'0\r\n\r\n',split=17)
    with pytest.raises(ValueError):parse(head+b'0'*129,split=17)
    with pytest.raises(ValueError):transport._LiveHTTPParser(65536).feed(b'x'*(16384+393216+65536+1))
    with pytest.raises(ValueError):transport._LiveHTTPParser(True)
    # The original controlled parser still refuses transfer encoding.
    with pytest.raises(ValueError):transport._parse_response(head+b'0\r\n\r\n')
    assert transport._WALL==8.0


@pytest.mark.parametrize('value',[[],['127.0.0.1'],['10.0.0.1'],['169.254.1.1'],['::1'],['::ffff:8.8.8.8'],
    ['224.0.0.1'],['1.1.1.1','1.1.1.1'],['1.1.1.1','127.0.0.1'],['fe80::1%lo0'],['8.8.8.8']*17,[True]])
def test_dns_shape_refuses_private_mixed_duplicate_or_unbounded(value):
    with pytest.raises(ValueError):dns.validate_addresses(value)


def test_dns_canonical_frame_identity_and_public_shape_only():
    answers=['1.1.1.1','2606:4700:4700::1111'];raw=json.dumps(['native-dns-result-v1',123,'n',answers],separators=(',',':')).encode()
    assert dns.decode_result(raw,123,'n')==tuple(answers)
    for body,pid,nonce in ((raw+b' ',123,'n'),(raw,124,'n'),(raw,123,'other'),(b'[]',123,'n')):
        with pytest.raises(ValueError):dns.decode_result(body,pid,nonce)


def test_missing_native_ports_and_forged_scopes_fail_before_key_dns_or_process(monkeypatch):
    reads=[]
    def forbidden(*args,**kwargs):reads.append(True);raise AssertionError('no key or DNS resource may be born')
    monkeypatch.setattr(credentials,'_read_provider',forbidden)
    monkeypatch.setattr(socket,'socketpair',forbidden)
    monkeypatch.setattr(dns.subprocess,'Popen',forbidden)
    for action in (lambda:credentials.load_native_live_credential(None,None,None,main_context=object()),
                   lambda:credentials.entry_directory_witness(object()),
                   lambda:dns.resolve_native_host(object(),object(),deadline=time.monotonic()+1),
                   lambda:credentials._publish_entry_directory([])):
        with pytest.raises((PermissionError,RuntimeError,ValueError,TypeError,ResearchError)) as denied:action()
    assert reads==[] and not credentials._ENTRIES and not credentials._KEYS


def test_actual_resource_constructors_reject_caller_factory_without_registering():
    keys=tuple(credentials._KEYS);entries=tuple(credentials._ENTRIES)
    with pytest.raises(Exception):credentials.EntryCredentialDirectoryWitness([],[],os.geteuid(),None,_factory=credentials._FACTORY)
    with pytest.raises(Exception):credentials.NativeLiveCredential(None,None,None,None,b'',bytearray(),-1,(),None,_factory=credentials._FACTORY)
    assert tuple(credentials._KEYS)==keys and tuple(credentials._ENTRIES)==entries


@pytest.mark.parametrize('raw',[b'',b' a',b'a ',b'a\r\nb',b'a\0b',b'\xff',b'a:b',b'a=b=c',b'x'*4097])
def test_provider_token_data_grammar_never_trims_or_accepts_injection(raw):
    with pytest.raises(ValueError):credentials.validate_provider_bytes(raw)


def test_synthetic_fd_reader_is_not_a_live_credential(tmp_path):
    path=tmp_path/'structural-deepseek-api-key';path.write_bytes(b'synthetic-local-token_01');path.chmod(0o400)
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);fd=None
    try:
        key,fd,metadata,io=credentials._read_provider(directory,os.geteuid())
        assert key==bytearray(b'synthetic-local-token_01') and metadata[4:7]==(0o400,1,len(key))
        assert not credentials._KEYS and not credentials._ENTRIES
        key[:]=b'\0'*len(key);key.clear()
        io.close();fd=None
    finally:
        if fd is not None:os.close(fd)
        os.close(directory)


@pytest.mark.parametrize('fault',['symlink','hardlink','fifo','mode','empty','oversize'])
def test_synthetic_provider_metadata_faults_reject_and_retire(tmp_path,fault):
    path=tmp_path/'structural-deepseek-api-key';path.write_bytes(b'synthetic-token');path.chmod(0o400)
    if fault=='symlink':path.unlink();path.symlink_to(tmp_path/'absent')
    elif fault=='hardlink':os.link(path,tmp_path/'other')
    elif fault=='fifo':path.unlink();os.mkfifo(path,0o400)
    elif fault=='mode':path.chmod(0o600)
    else:path.chmod(0o600);path.write_bytes(b'' if fault=='empty' else b'x'*4097);path.chmod(0o400)
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        with pytest.raises((ValueError,OSError)):credentials._read_provider(directory,os.geteuid())
    finally:os.close(directory)
    assert not credentials._KEYS and not credentials._ENTRIES


def test_synthetic_same_size_change_during_read_is_rejected(tmp_path,monkeypatch):
    path=tmp_path/'structural-deepseek-api-key';path.write_bytes(b'synthetic-token');path.chmod(0o400)
    read=os.read;calls=[]
    def changed(fd,size):
        raw=read(fd,size);calls.append(fd)
        if len(calls)==1:path.chmod(0o600);path.write_bytes(b'different-token');path.chmod(0o400)
        return raw
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(os,'read',changed)
            with pytest.raises(ValueError):credentials._read_provider(directory,os.geteuid())
        assert len(set(calls))==1
        with pytest.raises(OSError):os.fstat(calls[0])
    finally:os.close(directory)


def test_dns_socketpair_close_is_physical_and_detach_is_sticky_unknown():
    class Owner:
        def __init__(self):self._dns_processes={};self.uncertain=False
        def _mark_cleanup_uncertain(self):self.uncertain=True
    for detached in (False,True):
        owner=Owner();owned=dns._OwnedDNS(owner,None,time.monotonic()+1)
        owned.parent,owned.child=socket.socketpair();owned.remember_socket(owned.parent);owned.remember_socket(owned.child)
        fds=[owned.parent.fileno(),owned.child.fileno()]
        try:
            if detached:
                leaked=owned.parent.detach()
                with pytest.raises(OSError):owned.close()
                assert owner.uncertain and owned.uncertain and owner._dns_processes
                os.close(leaked)
                with pytest.raises(OSError):owned.close()
            else:
                owned.close();assert owned.closed and not owner._dns_processes and not owner.uncertain
            for fd in fds:
                with pytest.raises(OSError):os.fstat(fd)
        finally:
            for sock in (owned.parent,owned.child):sock.close()


def test_new_boundary_module_top_imports_are_stdlib_and_no_dynamic_bootstrap_calls():
    import sys
    for module in (credentials,dns):
        tree=ast.parse(Path(module.__file__).read_bytes())
        imports={a.name.split('.')[0] for n in tree.body if isinstance(n,ast.Import) for a in n.names}
        assert imports<=sys.stdlib_module_names
        assert not any(isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) for n in tree.body)


def test_partial_credential_birth_reports_real_readonly_handle_on_close_uncertainty(tmp_path,monkeypatch):
    path=tmp_path/'structural-deepseek-api-key';path.write_bytes(b'synthetic-token');path.chmod(0o600)
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);failed=[]
    close=os.close
    def unavailable(fd):
        if fd!=directory:failed.append(fd);raise OSError('synthetic provider FD retirement uncertainty')
        return close(fd)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(os,'close',unavailable)
            with pytest.raises(credentials.NativeCredentialStartFailure) as caught:
                credentials._read_provider(directory,os.geteuid())
            failure=caught.value
        assert failure.uncertain is True and failure.resources==(failure.handle,)
        assert len(failed)==1 and os.fstat(failed[0]).st_ino==path.stat().st_ino
        assert 'synthetic-token' not in repr(failure) and 'synthetic-token' not in repr(failure.handle)
        with pytest.raises(TypeError):failure.handle=None
        with pytest.raises(TypeError):pickle.dumps(failure)
        # Real later close succeeds physically; prior uncertainty remains.
        with pytest.raises(ResearchError):failure.handle.close()
        with pytest.raises(OSError):os.fstat(failed[0])
        assert failure.uncertain and not credentials._KEYS and not credentials._ENTRIES
    finally:
        if failed:
            try:os.fstat(failed[0])
            except OSError:pass
            else:close(failed[0])
        close(directory)


def test_synthetic_directory_helper_cannot_read_systemd_shaped_directory(tmp_path,monkeypatch):
    path=tmp_path/'structural-deepseek-api-key';path.write_bytes(b'synthetic-token');path.chmod(0o400)
    directory=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);opened=[];real_open=os.open
    def seen(name,*args,**kwargs):
        if name=='structural-deepseek-api-key':opened.append(True)
        return real_open(name,*args,**kwargs)
    try:
        tmp_path.chmod(0o500)
        with monkeypatch.context() as patch:
            patch.setattr(os,'open',seen)
            with pytest.raises(ValueError):credentials._read_provider(directory,os.geteuid())
        assert opened==[] and not credentials._KEYS and not credentials._ENTRIES
    finally:tmp_path.chmod(0o700);os.close(directory)
