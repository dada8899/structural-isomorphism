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
from web.backend.tests.test_research_source_spawn import development_auth

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
    with pytest.MonkeyPatch.context() as backing_setup:
        backing=development_auth.__wrapped__(Path(config["root"]),backing_setup)
        gate=AuthorizationGate(backing)
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
    output=subprocess.run(["ps","-ww","-axo","pid,ppid,command"],capture_output=True,text=True,check=True).stdout
    return [int(parts[0]) for row in output.splitlines()[1:]
            if len(parts:=row.strip().split(None,2))==3 and parts[1]==str(parent) and "multiprocessing.resource_tracker" in parts[2]]


def _owned_tracker_diagnostic(parent_pid,ready,started,stage,tracker_count,*,proc_root=Path("/proc")):
    """Failure-only safe snapshot. Never return command lines or global ps rows."""
    def ps(arguments):
        try:
            result=subprocess.run(["ps",*arguments],capture_output=True,text=True,timeout=2)
            return result.stdout if result.returncode==0 else ""
        except (OSError,subprocess.SubprocessError):
            return ""
    # Discover ownership using numeric topology only, before reading commands.
    topology={}
    for line in ps(["-axo","pid=,ppid=,pgid="]).splitlines():
        values=line.split()
        if len(values)==3 and all(value.isdecimal() for value in values):
            pid,ppid,pgid=map(int,values);topology[pid]=(ppid,pgid)
    known={parent_pid,ready["pid"]}
    owned=set(known)
    for _ in range(32):
        additions={pid for pid,(ppid,pgid) in topology.items() if pgid==parent_pid or ppid in owned}
        if additions<=owned:break
        owned.update(additions)
    owned=set(sorted(owned)[:32])|known
    selection=",".join(str(pid) for pid in sorted(owned))
    def snapshot(wide):
        args=(["-ww"] if wide else [])+["-p",selection,"-o","pid=,ppid=,pgid=,stat=,command="]
        rows={}
        for line in ps(args).splitlines():
            values=line.strip().split(None,4)
            if len(values)<4 or not all(value.isdecimal() for value in values[:3]):continue
            pid,ppid,pgid=map(int,values[:3])
            if pid not in owned:continue
            command=values[4] if len(values)==5 else ""
            rows[pid]={"present":True,"ppid":ppid if ppid in owned or ppid==os.getpid() else None,
                "in_owned_group":pgid==parent_pid,"zombie":values[3].startswith("Z"),
                "tracker_marker":"multiprocessing.resource_tracker" in command,
                "spawn_marker":"multiprocessing.spawn" in command}
        return rows
    normal,wide=snapshot(False),snapshot(True)
    rows=[]
    for pid in sorted(owned):
        proc=proc_root/str(pid)
        detail={"supported":proc_root.is_dir(),"exists":proc.is_dir()}
        if proc.is_dir():
            try:
                status=proc.joinpath("status").read_text()
                parent_line=next((line.split(":",1)[1].strip() for line in status.splitlines() if line.startswith("PPid:")),"")
                ppid=int(parent_line) if parent_line.isdecimal() else None
                comm=proc.joinpath("comm").read_text().strip()
                command=proc.joinpath("cmdline").read_bytes()
                detail.update(ppid=ppid if ppid in owned or ppid==os.getpid() else None,
                    comm_python=comm.startswith("python"),
                    tracker_marker=b"multiprocessing.resource_tracker" in command)
            except (OSError,UnicodeError,ValueError):detail["read_unavailable"]=True
        rows.append({"pid":pid,"role":"parent" if pid==parent_pid else "sender" if pid==ready["pid"] else "owned_descendant",
            "normal_ps":normal.get(pid,{"present":False}),"wide_ps":wide.get(pid,{"present":False}),"proc":detail})
    allowed={"before-arm","before-handoff","queued-handle","sender","blocked-alarm"}
    ready_stages={"before-arm","armed-before-handoff","handle-queued","sender","armed-before-receive"}
    return {"kind":"owned_tracker_diagnostic_v1","stage":stage if stage in allowed else "unknown",
        "ready_stage":ready.get("stage") if ready.get("stage") in ready_stages else "unknown",
        "started_parent_matches":started.get("parent")==parent_pid,"tracker_count":tracker_count,
        "parent_pid":parent_pid,"sender_pid":ready["pid"],"owned":rows}


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
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:env['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+env['PYTHONPATH']
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
def test_sigkill_parent_cannot_leave_unleased_late_sender(tmp_path,local_source,stage,development_auth):
    port,calls=local_source
    wall=12 if stage in {"queued-handle","sender"} else 2
    parent,config,log=_start(tmp_path,port,stage,wall)
    trackers=[]
    try:
        started=_await_file(config["started"])
        ready=_await_file(config["ready"])
        if stage=="queued-handle":_await_file(config["receiver"])
        trackers=_private_trackers(parent.pid)
        if len(trackers)!=1:
            print(json.dumps(_owned_tracker_diagnostic(parent.pid,ready,started,stage,len(trackers)),sort_keys=True))
        assert len(trackers)==1,"expected this independent parent's private resource_tracker"
        os.kill(parent.pid,signal.SIGKILL);parent.wait(timeout=3)
        gate=AuthorizationGate(development_auth)
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


def test_normal_local_response_and_lease_context_recovery(tmp_path,local_source,development_auth):
    port,calls=local_source
    parent,config,log=_start(tmp_path,port,"sender",3)
    try:
        ready=_await_file(config["ready"])
        Path(config["go"]).write_text("normal send")
        parent.wait(timeout=5)
        assert parent.returncode==0,(tmp_path/"parent.log").read_text()
        assert json.loads(Path(config["result"]).read_text())=={"status":200,"body":"local"}
        assert len(calls)==1 and calls[0]["cancel_committed"] is False
        gate=AuthorizationGate(development_auth)
        with gate.owner_gate_id(config["gate_id"],timeout=1):pass
        assert not _running(ready["pid"])
    finally:_cleanup_group(parent,log)


def test_missing_inactive_or_forged_lease_fails_before_spawn(tmp_path,development_auth):
    with pytest.raises(TypeError):OwnerGateLease(0)
    gate=AuthorizationGate(development_auth)
    with gate.owner_gate_id(str(uuid4())) as lease:
        identity=lease.identity
        assert len(identity)==5
        with pytest.raises(TypeError):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True)
        with pytest.raises(source_policy.SourceFailure):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True,owner_lease=True)
    with pytest.raises(PermissionError):source_policy.PinnedPublicTransport().get(TARGET,still_authorized=lambda:True,owner_lease=lease)


def test_tracker_failure_diagnostic_filters_ownership_before_emitting_commands(tmp_path,monkeypatch):
    canary="DO_NOT_LOG_PRIVATE_COMMAND_OR_PATH"
    commands=[]
    def fake_ps(argv,**kwargs):
        commands.append(argv)
        if "-axo" in argv:
            assert argv[-1]=="pid=,ppid=,pgid="
            return SimpleNamespace(returncode=0,stdout="101 1 101\n102 101 101\n103 101 101\n999 1 999\n")
        assert argv[argv.index("-p")+1]=="101,102,103"
        marker=" multiprocessing.resource_tracker" if "-ww" in argv else " truncated"
        return SimpleNamespace(returncode=0,stdout=f"101 1 101 S {canary}\n102 101 101 S multiprocessing.spawn {canary}\n103 101 101 S{marker} {canary}\n999 1 999 S {canary}\n")
    monkeypatch.setattr(subprocess,"run",fake_ps)
    proc=tmp_path/"proc"/"103";proc.mkdir(parents=True)
    (proc/"status").write_text("PPid:\t101\n")
    (proc/"comm").write_text("python3.11\n")
    (proc/"cmdline").write_bytes(b"python\0multiprocessing.resource_tracker\0"+canary.encode())
    value=_owned_tracker_diagnostic(101,{"pid":102,"stage":"sender"},{"parent":101},"sender",0,proc_root=tmp_path/"proc")
    encoded=json.dumps(value)
    assert canary not in encoded and "999" not in encoded and str(tmp_path) not in encoded
    assert [row["pid"] for row in value["owned"]]==[101,102,103]
    tracker=value["owned"][-1]
    assert tracker["normal_ps"]["tracker_marker"] is False and tracker["wide_ps"]["tracker_marker"] is True
    assert tracker["proc"]["tracker_marker"] is True and tracker["proc"]["ppid"]==101
    assert len(commands)==3


def test_tracker_failure_diagnostic_never_echoes_ps_errors(tmp_path,monkeypatch):
    def unavailable(*args,**kwargs):
        raise subprocess.TimeoutExpired("PRIVATE_COMMAND_CANARY",2,output="PRIVATE_OUTPUT_CANARY")
    monkeypatch.setattr(subprocess,"run",unavailable)
    value=_owned_tracker_diagnostic(101,{"pid":102,"stage":"sender"},{"parent":101},"sender",0,proc_root=tmp_path/"missing")
    assert "PRIVATE" not in json.dumps(value)
    assert all(not row["normal_ps"]["present"] and not row["wide_ps"]["present"] for row in value["owned"])


def test_private_tracker_reader_requests_full_width_for_real_owned_process(tmp_path,monkeypatch):
    manifest=tmp_path/"owned-reader.json"
    program=(
        "import json,os,pathlib,subprocess,sys,time; "
        "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)',"
        "'padding-'*100,'multiprocessing.resource_tracker']); "
        f"pathlib.Path({str(manifest)!r}).write_text(json.dumps({{'parent':os.getpid(),'child':child.pid}})); "
        "time.sleep(30)"
    )
    native_run=subprocess.run
    calls=[]
    with subprocess.Popen([sys.executable,"-c",program],start_new_session=True,
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as parent:
        try:
            owned=_await_file(manifest,seconds=5)
            assert owned["parent"]==parent.pid and os.getpgid(owned["child"])==parent.pid
            def observed_ps(argv,**kwargs):
                calls.append(argv)
                result=native_run(argv,**kwargs)
                if "-ww" not in argv:
                    return subprocess.CompletedProcess(argv,result.returncode,
                        "\n".join(row[:80] for row in result.stdout.splitlines()),result.stderr)
                rows=[line.strip().split(None,2) for line in result.stdout.splitlines()[1:]]
                assert any(len(row)==3 and row[0]==str(owned["child"]) and
                    row[1]==str(parent.pid) and "multiprocessing.resource_tracker" in row[2] for row in rows)
                return result
            monkeypatch.setattr(subprocess,"run",observed_ps)
            assert _private_trackers(parent.pid)==[owned["child"]]
            assert calls==[["ps","-ww","-axo","pid,ppid,command"]]
            # Reproduce a narrow display deterministically. Wide above was a
            # real OS read, not a second mocked copy of a diagnostic result.
            narrow=observed_ps(["ps","-axo","pid,ppid,command"],capture_output=True,text=True,check=True)
            monkeypatch.setattr(subprocess,"run",lambda *args,**kwargs:narrow)
            assert _private_trackers(parent.pid)==[]
        finally:
            try:os.killpg(parent.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            parent.wait(timeout=5)


@pytest.mark.parametrize("case",["foreign","wrong-marker","empty","error"])
def test_private_tracker_wide_reader_preserves_rejection_rules(monkeypatch,case):
    def output(argv,**kwargs):
        assert argv==["ps","-ww","-axo","pid,ppid,command"]
        assert kwargs=={"capture_output":True,"text":True,"check":True}
        if case=="error":raise subprocess.CalledProcessError(1,argv)
        rows={"foreign":" PID PPID COMMAND\n202 999 multiprocessing.resource_tracker\n",
              "wrong-marker":" PID PPID COMMAND\n202 101 multiprocessing.spawn\n",
              "empty":""}
        return SimpleNamespace(stdout=rows[case])
    monkeypatch.setattr(subprocess,"run",output)
    if case=="error":
        with pytest.raises(subprocess.CalledProcessError):_private_trackers(101)
    else:
        assert _private_trackers(101)==[]  # original lifecycle still requires exactly one
