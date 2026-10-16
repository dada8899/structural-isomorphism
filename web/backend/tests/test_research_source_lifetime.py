"""Owned local processes/sockets only; no public DNS, credentials or HTTP."""
from __future__ import annotations

import functools
import http.client
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from types import SimpleNamespace
from uuid import uuid4

import pytest

from web.backend.research.authorization import AuthorizationGate,OwnerGateLease
from web.backend.research.errors import ResearchError
from web.backend.research import source_policy

ROOT=Path(__file__).resolve().parents[3]
TARGET=source_policy.article_target("10.1371/journal.pone.0015032")


def _write(path,value):
    temporary=Path(str(path)+".new")
    temporary.write_text(json.dumps(value));temporary.replace(path)


def _await_file(path,seconds=10):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if Path(path).exists():return json.loads(Path(path).read_text())
        time.sleep(.01)
    raise AssertionError("owned test barrier did not arrive")


def _local_worker(config,target):
    _write(config["ready"],{"pid":os.getpid(),"stage":"sender"})
    while not Path(config["go"]).exists():time.sleep(.01)
    connection=http.client.HTTPConnection("127.0.0.1",config["port"],timeout=1)
    try:
        connection.request("GET","/owned-source")
        response=connection.getresponse();raw=response.read(100)
        return response.status,"text/plain",raw,raw
    finally:connection.close()


def _setup_child(config,*args):
    if config["stage"]=="before-arm":
        _write(config["ready"],{"pid":os.getpid(),"stage":"before-arm"})
        while not Path(config["setup_go"]).exists():time.sleep(.01)
    if config["stage"]=="queued-handle":
        original=source_policy.recv_handle
        def delayed_receive(channel):
            _write(config["receiver"],{"pid":os.getpid(),"stage":"armed-before-receive"})
            while not Path(config["setup_go"]).exists():time.sleep(.01)
            return original(channel)
        source_policy.recv_handle=delayed_receive
    source_policy._child(*args)


def parent_main(config_path):
    config=json.loads(Path(config_path).read_text())
    if config["stage"]=="blocked-alarm":signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGALRM})
    if config["stage"] in {"before-arm","queued-handle"}:
        source_policy._child=functools.partial(_setup_child,config)
    original=OwnerGateLease.handoff
    if config["stage"]=="queued-handle":
        original_sendmsg=socket.socket.sendmsg
        def queued_sendmsg(self,buffers,ancdata=(),*args,**kwargs):
            value=original_sendmsg(self,buffers,ancdata,*args,**kwargs)
            if any(level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS for level,kind,_ in ancdata):
                # Observe the actual kernel enqueue, before Darwin's optional
                # receive acknowledgement; do not invent a transferred FD.
                _write(config["ready"],{"pid":_await_file(config["receiver"],1)["pid"],"stage":"handle-queued"})
                while not Path(config["parent_go"]).exists():time.sleep(.01)
            return value
        socket.socket.sendmsg=queued_sendmsg
    def observed_handoff(self,connection,child_pid,deadline):
        if config["stage"]=="before-handoff":
            _write(config["ready"],{"pid":child_pid,"stage":"armed-before-handoff"})
            while not Path(config["parent_go"]).exists():time.sleep(.01)
        original(self,connection,child_pid,deadline)
    OwnerGateLease.handoff=observed_handoff
    gate=AuthorizationGate(SimpleNamespace(path=Path(config["root"])/"unused.sqlite3"))
    with gate.owner_gate_id(config["gate_id"]) as lease:
        _write(config["started"],{"at":time.monotonic(),"parent":os.getpid(),"identity":lease.identity})
        value=source_policy.PinnedPublicTransport(wall_seconds=config["wall"],_worker=functools.partial(_local_worker,config)).get(
            TARGET,still_authorized=lambda:True,owner_lease=lease)
        _write(config["result"],{"status":value[0],"body":value[2].decode()})


def _running(pid):
    result=subprocess.run(["ps","-p",str(pid),"-o","stat="],capture_output=True,text=True)
    state=result.stdout.strip()
    return bool(state and not state.startswith("Z"))


def _private_trackers(parent):
    output=subprocess.run(["ps","-axo","pid,ppid,command"],capture_output=True,text=True,check=True).stdout
    return [int(parts[0]) for row in output.splitlines()[1:]
            if len(parts:=row.strip().split(None,2))==3 and parts[1]==str(parent) and "multiprocessing.resource_tracker" in parts[2]]


@pytest.fixture
def local_source(tmp_path):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            calls.append({"at":time.monotonic(),"cancel_committed":(tmp_path/"committed").exists()})
            self.send_response(200);self.send_header("Content-Length","5");self.end_headers();self.wfile.write(b"local")
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:yield server.server_address[1],calls
    finally:server.shutdown();server.server_close();thread.join(5)


def _start(tmp_path,port,stage,wall):
    config={"root":str(tmp_path),"gate_id":str(uuid4()),"port":port,"stage":stage,"wall":wall}
    for name in ("ready","receiver","go","setup_go","parent_go","started","result"):
        config[name]=str(tmp_path/name)
    path=tmp_path/"config.json";path.write_text(json.dumps(config))
    env={**os.environ,"PYTHONPATH":str(ROOT)+os.pathsep+str(ROOT/"web/backend"),"PYTHONDONTWRITEBYTECODE":"1"}
    log=(tmp_path/"parent.log").open("wb")
    process=subprocess.Popen([sys.executable,"-c","from web.backend.tests.test_research_source_lifetime import parent_main; import sys; parent_main(sys.argv[1])",str(path)],cwd=ROOT,env=env,start_new_session=True,stdout=log,stderr=log)
    return process,config,log


def _cleanup_group(process,log):
    if process.poll() is None:process.terminate()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    # This session/group was created by _start; it contains only this test's
    # request parent, sender and private resource_tracker, never shared workers.
    for sig in (signal.SIGTERM,signal.SIGKILL):
        try:os.killpg(process.pid,sig)
        except ProcessLookupError:break
        time.sleep(.05)
    log.close()


@pytest.mark.parametrize("stage",["before-arm","before-handoff","queued-handle","sender","blocked-alarm"])
def test_sigkill_parent_cannot_leave_unleased_late_sender(tmp_path,local_source,stage):
    port,calls=local_source
    wall=12 if stage in {"queued-handle","sender"} else 2
    parent,config,log=_start(tmp_path,port,stage,wall)
    trackers=[]
    try:
        started=_await_file(config["started"])
        ready=_await_file(config["ready"])
        if stage=="queued-handle":_await_file(config["receiver"])
        trackers=_private_trackers(parent.pid)
        assert len(trackers)==1,"expected this independent parent's private resource_tracker"
        os.kill(parent.pid,signal.SIGKILL);parent.wait(timeout=3)
        gate=AuthorizationGate(SimpleNamespace(path=tmp_path/"unused.sqlite3"))
        leased=stage in {"queued-handle","sender","blocked-alarm"}
        if leased:
            with pytest.raises(ResearchError) as error:
                with gate.owner_gate_id(config["gate_id"],timeout=.1):
                    pytest.fail("cancel committed while sender/queued capability still owns gate")
            assert error.value.code=="STORE_BUSY"
        else:
            with gate.owner_gate_id(config["gate_id"],timeout=1):
                (tmp_path/"committed").write_text("cancel committed before any handoff")
        end=started["at"]+wall+.4
        while time.monotonic()<end:time.sleep(min(.03,end-time.monotonic()))
        # Replay the original late-release shape beyond 12 seconds. The
        # kernel timer, not the dead parent/finally/daemon, owns the limit.
        if stage=="before-arm":Path(config["setup_go"]).write_text("release unarmed startup")
        Path(config["go"]).write_text("late send release")
        Path(config["setup_go"]).write_text("late receive release")
        if leased:
            with gate.owner_gate_id(config["gate_id"],timeout=1):
                (tmp_path/"committed").write_text("cancel committed only after sender expiry")
        deadline=time.monotonic()+3
        while _running(ready["pid"]) and time.monotonic()<deadline:time.sleep(.02)
        assert not _running(ready["pid"]),"owned sender still running"
        assert calls==[] and (tmp_path/"committed").exists()
        deadline=time.monotonic()+3
        while any(_running(pid) for pid in trackers) and time.monotonic()<deadline:time.sleep(.02)
        assert not any(_running(pid) for pid in trackers),"private resource_tracker did not close"
        assert not Path(config["result"]).exists()
    finally:_cleanup_group(parent,log)


def test_normal_local_response_and_lease_context_recovery(tmp_path,local_source):
    port,calls=local_source
    parent,config,log=_start(tmp_path,port,"sender",3)
    try:
        ready=_await_file(config["ready"])
        Path(config["go"]).write_text("normal send")
        parent.wait(timeout=5)
        assert parent.returncode==0,(tmp_path/"parent.log").read_text()
        assert json.loads(Path(config["result"]).read_text())=={"status":200,"body":"local"}
        assert len(calls)==1 and calls[0]["cancel_committed"] is False
        gate=AuthorizationGate(SimpleNamespace(path=tmp_path/"unused.sqlite3"))
        with gate.owner_gate_id(config["gate_id"],timeout=1):pass
        assert not _running(ready["pid"])
    finally:_cleanup_group(parent,log)


def test_missing_inactive_or_forged_lease_fails_before_spawn(tmp_path):
    with pytest.raises(TypeError):OwnerGateLease(0)
    gate=AuthorizationGate(SimpleNamespace(path=tmp_path/"unused.sqlite3"))
    with gate.owner_gate_id(str(uuid4())) as lease:
        identity=lease.identity
        assert len(identity)==5
        with pytest.raises(TypeError):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True)
        with pytest.raises(source_policy.SourceFailure):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True,owner_lease=True)
    with pytest.raises(PermissionError):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True,owner_lease=lease)
