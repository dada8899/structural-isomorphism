"""One-shot GitHub hosted guest. Require exact approved inputs; never SSH."""
import argparse, hashlib, json, os, pathlib, re, secrets, shutil, stat, subprocess, sys, tarfile, time
from formal_launcher_envelope import SOURCE,RUNTIME,ELF,ELF_SHA,ENTRY,RELEASE,FORMAL_ENTRY_SHA,FORMAL_UNIT_SHA,CREDENTIALS,UNIT
from render_github_guest import render
from verify_derived_pure_wheels import inventory

P=pathlib.Path
ARCHIVE="b702a19b26cbd007abf9ccbaa45dfdff99e9dbd646d89c9f3c9bb7b501aea44f"
LOCK="efd2731c4e9e212ab75e6bcb53880d88492e1a44272622f05b6c98e8a606b6f5"
STATE=P("/var/lib/structural-isomorphism")
CACHE=P("/var/cache/structural-isomorphism")
RUN=P("/run/structure-formal-launcher-vm-only")
UNIT_PATH=P("/run/systemd/system")/UNIT
BRANCH="refs/heads/codex/formal-launcher-guest-395de-r3-once"
SOURCE_MANIFEST_SHA="f380702b8cabad17b5de02aebbfaa1bdf7374dd7ca2ba3646cf520b03366649f"
UID,GID=981,976
ENV={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL":"C.UTF-8","TZ":"UTC"}
DEADLINE=0
PHASE="ENTRY"
FAILURE_PHASE=None
INVENTORY_REASON=None
INVENTORY_LOCATION=None
PHASES=frozenset(("ENTRY","ADMISSION","PUBLIC_INPUTS","CLAIM","ACCOUNT","PYTHON_ARCHIVE",
 "BUILD_A","BUILD_B","PURE_WHEEL_VERIFY","RUNTIME_INSTALL","RUNTIME_INVENTORY","SOURCE_COPY",
 "SYNTHETIC_CREDENTIALS","SYNTHETIC_DB","UNIT_WRITE","UNIT_START","HEALTH","RETIRE","RECEIPT"))


def phase(value):
    global PHASE
    if value not in PHASES:raise RuntimeError("PHASE_ENUM")
    PHASE=value
    print("GUEST_PHASE:"+value,flush=True)

SELF=P(__file__).resolve().parent

def need(ok):
    if not ok:raise RuntimeError("GUEST_PREREQUISITE_OR_PROOF_REJECTED")

def hash_file(path):
    need(path.is_file() and not path.is_symlink())
    with path.open("rb") as src:return hashlib.file_digest(src,"sha256").hexdigest()

def call(argv,*,data=None,env=None,maxsec=45):
    t=min(maxsec,DEADLINE-time.monotonic())
    need(t>0)
    r=subprocess.run(argv,input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                     env=ENV if env is None else env,timeout=t,check=True)
    need(len(r.stdout)<=262144)
    return r.stdout

def write(path,raw,mode=0o600):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    with os.fdopen(fd,"wb") as f:f.write(raw);f.flush();os.fsync(f.fileno())
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def read_blob(argv,size):
    need(type(size) is int and 0<=size<=3*1024*1024)
    limit=min(10,DEADLINE-time.monotonic())
    need(limit>0)
    result=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=ENV,
                          timeout=limit,check=True)
    need(len(result.stdout)==size)
    return result.stdout


def show():
    fields="LoadState,ActiveState,SubState,MainPID,ControlPID,InvocationID,ControlGroup,Result,ExecMainStatus"
    r=subprocess.run(["/usr/bin/systemctl","show",UNIT,"--property="+fields],capture_output=True,env=ENV,timeout=5)
    need(len(r.stdout)<4096)
    return dict(line.split("=",1) for line in r.stdout.decode().splitlines() if "=" in line)

def contained(argv,uid=UID,gid=GID):
    return ["/usr/bin/unshare","--net","--","/usr/bin/setpriv","--reuid",str(uid),"--regid",str(gid),
            "--clear-groups","--no-new-privs",*argv]

def ensure_account():
    import pwd,grp
    try:grp.getgrgid(GID);raise ValueError()
    except KeyError:pass
    try:pwd.getpwuid(UID);raise ValueError()
    except KeyError:pass
    call(["/usr/sbin/groupadd","--gid",str(GID),"structural"])
    call(["/usr/sbin/useradd","--uid",str(UID),"--gid",str(GID),"--no-create-home","--shell","/usr/sbin/nologin","structural"])

def secure_input(args,claim):
    need(hash_file(args.inputs/"cpython-20260414-stripped.tar.gz")==ARCHIVE)
    need(hash_file(SELF/"runtime-linux-cpu.lock")==LOCK)
    manifest_path=SELF/"PUBLIC-DISTRIBUTION-VERIFICATION.json"
    need(hash_file(manifest_path)==claim["distribution_manifest_sha256"])
    rows=json.loads(manifest_path.read_bytes())["rows"]
    need(len(rows)==73 and sum(x["kind"]=="wheel" for x in rows)==71)
    public=args.inputs/"verified-public-distributions"
    need(set(x.name for x in public.iterdir())=={r["filename"] for r in rows})
    lock=(SELF/"runtime-linux-cpu.lock").read_text()
    for row in rows:
        name=row["filename"];digest=row["sha256"]
        need(re.fullmatch(r"[A-Za-z0-9_.+-]+",name) and "--hash=sha256:"+digest in lock)
        need(hash_file(public/name)==digest and (public/name).stat().st_size==row["size"])
    need(call(["/usr/bin/git","-c","safe.directory="+str(args.checkout),"-C",str(args.checkout),"rev-parse","HEAD"]).decode().strip()==SOURCE)
    need(not call(["/usr/bin/git","-c","safe.directory="+str(args.checkout),"-C",str(args.checkout),"diff","--name-only","HEAD"]))
    need(hash_file(args.unit)==FORMAL_UNIT_SHA and hash_file(args.checkout/"scripts/run-formal-main.py")==FORMAL_ENTRY_SHA)
    return rows,public

def runtime_inventory(site,std,prefix,install,*,expected_uid=0):
    """No package import. Public fixed path classes only if a check fails."""
    global INVENTORY_REASON,INVENTORY_LOCATION
    def require_inventory(ok,code,family,kind,relative=""):
        global INVENTORY_REASON,INVENTORY_LOCATION
        if not ok:
            INVENTORY_REASON=code
            INVENTORY_LOCATION={"family":family,"path_class":kind,
                                "relative_name_sha256":hashlib.sha256(relative.encode()).hexdigest()}
            raise RuntimeError("RUNTIME_INVENTORY_REJECTED")
    def category(path):
        name=path.name.lower()
        return ("BYTECODE" if name.endswith((".pyc",".pyo")) else
                "PYTHON" if name.endswith(".py") else
                "NATIVE" if name.endswith((".so",".dylib",".pyd")) else
                "WHEEL" if name.endswith(".whl") else "PACKAGE_DATA")
    rows=[]
    for family,path in (("site",site),("stdlib",std)):
        require_inventory(path.is_dir(),"ROOT_MISSING",family,"DIRECTORY")
        for current,dirs,files in os.walk(path,followlinks=False):
            current=P(current)
            require_inventory(not current.is_symlink(),"DIRECTORY_LINK",family,"DIRECTORY",str(current.relative_to(path)))
            for name in dirs:
                require_inventory(not (current/name).is_symlink(),"CHILD_DIRECTORY_LINK",family,"DIRECTORY",str((current/name).relative_to(path)))
            for name in sorted(files):
                item=current/name
                info=item.stat(follow_symlinks=False)
                kind=category(item)
                require_inventory(stat.S_ISREG(info.st_mode),"NONREGULAR",family,kind,str(item.relative_to(path)))
                require_inventory(info.st_uid==expected_uid,"OWNER",family,kind,str(item.relative_to(path)))
                require_inventory(not info.st_mode&0o022,"WRITABLE",family,kind,str(item.relative_to(path)))
                rows.append((family,str(item.relative_to(path)),info.st_mode&0o777,hash_file(item)))
    require_inventory(bool(rows),"NO_FILES","combined","DIRECTORY")
    require_inventory((prefix/"pyvenv.cfg").is_file(),"PYVENV_MISSING","venv","CONFIG")
    observed_sha=hashlib.sha256(json.dumps(sorted(rows),separators=(",",":")).encode()).hexdigest()
    return observed_sha,hash_file(prefix/"pyvenv.cfg"),hash_file(install)


def setup_runtime(args,rows,public,scratch):
    phase("PYTHON_ARCHIVE")
    elf=P(ELF);runtime=P(RUNTIME)
    need(not elf.parent.parent.exists() and not runtime.parent.parent.exists())
    elf.parent.parent.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    with tarfile.open(args.inputs/"cpython-20260414-stripped.tar.gz") as tar:
        # Archive is exact public SHA; data filter also checks traversal and links.
        tar.extractall(elf.parent.parent.parent,filter="data")
    (elf.parent.parent.parent/"python").rename(elf.parent.parent)
    need(hash_file(elf)==ELF_SHA)
    runtime.parent.parent.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    call(contained([str(elf),"-I","-B","-c","import sys; assert sys.version_info[:3]==(3,11,15)"]))
    os.chmod(scratch,0o755)
    staged=scratch/"inputs";staged.mkdir(mode=0o755)
    for row in rows:
        target=staged/row["filename"]
        shutil.copyfile(public/row["filename"],target)
        need(hash_file(target)==row["sha256"])
        target.chmod(0o644)
    st=next(x for x in rows if x["filename"].startswith("setuptools-84.0.0-"))
    tools=scratch/"builder-tools.lock"
    write(tools,("setuptools==84.0.0 --hash=sha256:"+st["sha256"]+"\n").encode(),0o644)
    sdist=scratch/"two-source.lock"
    write(sdist,("".join((staged/r["filename"]).as_uri()+" --hash=sha256:"+r["sha256"]+"\n"
                  for r in rows if r["kind"]!="wheel")).encode(),0o644)
    outputs=[]
    for turn in ("build-a","build-b"):
        phase("BUILD_A" if turn=="build-a" else "BUILD_B")
        folder=scratch/turn;folder.mkdir(mode=0o700);os.chown(folder,UID,GID)
        outputs.append(folder/"out")
        py=folder/"builder/bin/python"
        e=ENV|{"HOME":str(folder),"PIP_CONFIG_FILE":"/dev/null","SOURCE_DATE_EPOCH":"1704067200","PYTHONHASHSEED":"0"}
        call(contained([str(elf),"-s","-B","-m","venv",str(folder/"builder")]),env=e,maxsec=70)
        call(contained([str(py),"-s","-B","-m","pip","--isolated","install","--no-index","--no-deps","--require-hashes",
                        "--find-links",str(staged),"-r",str(tools)]),env=e)
        call(contained([str(py),"-s","-B","-m","pip","--isolated","wheel","--no-index","--no-deps","--no-build-isolation",
                        "--use-pep517","--no-cache-dir","--require-hashes","--wheel-dir",str(outputs[-1]),"-r",str(sdist)]),env=e,maxsec=90)
    phase("PURE_WHEEL_VERIFY")
    derived=inventory(outputs[0])
    need(derived==inventory(outputs[1]))
    for row in derived:
        src=outputs[0]/row["filename"];dest=staged/row["filename"]
        shutil.copyfile(src,dest);need(hash_file(dest)==row["sha256"]);dest.chmod(0o644)
    # Populate runtime as the unprivileged identity, then remove its write access.
    phase("RUNTIME_INSTALL")
    prefix=runtime.parent.parent
    prefix.mkdir(mode=0o700);os.chown(prefix,UID,GID)
    install=scratch/"guest-install.lock"
    full=[x for x in rows if x["kind"]=="wheel"]+derived
    write(install,("".join((staged/x["filename"]).as_uri()+" --hash=sha256:"+x["sha256"]+"\n" for x in full)).encode(),0o644)
    buildhome=scratch/"runtime-install-home";buildhome.mkdir(mode=0o700);os.chown(buildhome,UID,GID)
    e=ENV|{"HOME":str(buildhome),"PIP_CONFIG_FILE":"/dev/null"}
    call(contained([str(elf),"-s","-B","-m","venv",str(prefix)]),env=e,maxsec=60)
    call(contained([str(runtime),"-s","-B","-m","pip","--isolated","install","--no-index","--no-deps","--require-hashes",
                    "-r",str(install)]),env=e,maxsec=150)
    call(contained([str(runtime),"-I","-B","-m","pip","--isolated","check"]),env=e)
    need(runtime.resolve(strict=True)==elf and hash_file(elf)==ELF_SHA)
    for current,dirs,files in os.walk(prefix,followlinks=False):
        for x in (P(current),*(P(current)/n for n in dirs+files)):
            os.chown(x,0,0,follow_symlinks=False)
            if not x.is_symlink():x.chmod(x.stat().st_mode&~0o022|0o044)
    prefix.chmod(0o755)
    phase("RUNTIME_INVENTORY")
    observed_sha,pyvenv_sha,install_sha=runtime_inventory(
        prefix/"lib/python3.11/site-packages",elf.parent.parent/"lib/python3.11",prefix,install)
    return derived,install_sha,observed_sha,pyvenv_sha


def synthetic_values():
    def token(markers):
        for _ in range(12):
            value=secrets.token_urlsafe(48).encode()
            if len(set(value))>=12 and not any(m in value.lower() for m in markers):
                return value
        raise RuntimeError("SYNTHETIC_CREDENTIAL_SHAPE")
    def hmac_key():
        for _ in range(12):
            value=secrets.token_hex(32).encode()
            if len(set(value))>=12:return value
        raise RuntimeError("SYNTHETIC_CREDENTIAL_SHAPE")
    return [token((b"replace",b"change-me",b"changeme",b"example",b"test-secret",b"dev-jwt")),
            token((b"replace",b"change-me",b"example",b"test-secret",b"dev-")),
            hmac_key(),secrets.token_urlsafe(48).encode(),secrets.token_urlsafe(32).encode()]


def seed(root,nonce,values):
    # Owned guest only: synthetic empty state, exact ordinary app bootstrap.
    for path in (STATE,CACHE):
        path.mkdir(mode=0o700)
        os.chown(path,UID,GID)
    base=ENV|{"STRUCTURAL_ENV":"prod","AUTH_ENABLED":"true","AUTH_SITE_ROLE":"beta","AUTH_DEV_MODE":"false",
              "AUTH_LINK_BASE_URL":"https://beta.structural.bytedance.city","AUTH_DATA_DIR":str(STATE),
              "STRUCTURAL_SSO_DATA_DIR":str(STATE),"AUTH_TRUSTED_PROXY_IPS":"127.0.0.1"}
    code=b"""import os,sys
from pathlib import Path
os.environ['STRUCTURAL_PRIVACY_HMAC_KEY']=sys.stdin.read()
sys.path.insert(0,sys.argv[1]+'/web/backend')
from services.auth_registration import bootstrap_private_runtime
from research.first_answer import provision_first_answers_v16
from research.external_first_answer_catalog import apply_closed_v17_maintenance
from research.formula_runtime import _offline_maintenance
assert bootstrap_private_runtime()['research_schema']==15
p=Path('/var/lib/structural-isomorphism/auth.sqlite3')
lock=p.parent/'research-first-answer-queue.lock'
fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600); os.close(fd)
assert provision_first_answers_v16(p)['schema_version']==16
with _offline_maintenance(p,(16,)) as (target,cap):
 assert apply_closed_v17_maintenance(target,cap)=={'schema':17,'external_first_answer':'status_only','may_send':False}
"""
    call(contained([RUNTIME,"-I","-B","-c",code.decode(),str(root)]),data=values[2],env=base,maxsec=45)

def health(pid):
    raw=call(["/usr/bin/nsenter","--target",pid,"--net","--","/usr/bin/python3","-I","-S","-B","-c",'''
import json,urllib.request,urllib.error
def get(path):
 try:
  with urllib.request.urlopen("http://127.0.0.1:5004"+path,timeout=2) as r:
   return r.status,json.loads(r.read(65536))
 except urllib.error.HTTPError as e:return e.code,{}
v,ver=get("/api/version");h,health=get("/api/health");a,_=get("/api/research?limit=1")
check=health.get("checks",{})
names=("base","search","first_answer","first_answer_local","external_first_answer","native_planner","source_execute")
print(json.dumps({"version":v,"source":ver.get("git_sha"),"health":h,"anonymous":a,
                  "checks":{k:check.get(k) for k in names}}))
'''],maxsec=8)
    result=json.loads(raw);c=result["checks"]
    need(result["version"]==result["health"]==200 and result["source"]==SOURCE and result["anonymous"]==401
         and c["base"]=="ready" and c["search"]=="ARTIFACTS_UNBOUND" and c["first_answer"]==c["first_answer_local"]=="QUEUE_UNAVAILABLE"
         and c["external_first_answer"]=="ISSUER_UNBOUND" and c["native_planner"]=="FUNDING_CLOSED"
         and c["source_execute"]=="unavailable")
    return result

def trigger_binding(env,approval):
    need(approval["workflow_sha"]==env.get("GITHUB_SHA")==env.get("PROBE_PUSH_AFTER")
         and re.fullmatch(r"[a-f0-9]{40}",approval["workflow_sha"])
         and approval["run_number"]==env.get("GITHUB_RUN_NUMBER")=="1"
         and env.get("RUNNER_ENVIRONMENT")=="github-hosted" and env.get("GITHUB_RUN_ATTEMPT")=="1"
         and env.get("GITHUB_REPOSITORY")=="dada8899/structural-isomorphism"
         and env.get("GITHUB_EVENT_NAME")=="push" and env.get("GITHUB_REF")==BRANCH
         and env.get("PROBE_PUSH_CREATED")=="true" and env.get("PROBE_PUSH_DELETED")=="false"
         and env.get("PROBE_PUSH_BEFORE")=="0"*40)
    need(approval["source_manifest_sha256"]==SOURCE_MANIFEST_SHA)


def main():
    global DEADLINE,FAILURE_PHASE
    DEADLINE=time.monotonic()+600
    a=argparse.ArgumentParser()
    for name in ("approval","inputs","checkout","unit","source-manifest"):a.add_argument("--"+name,type=P,required=True)
    a.add_argument("--approval-sha256",required=True)
    args=a.parse_args()
    phase("ADMISSION")
    need(sys.platform=="linux" and os.geteuid()==0 and os.uname().machine=="x86_64" and
         sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode and not sys.flags.optimize)
    allowed=set(ENV)|{"GITHUB_SHA","GITHUB_RUN_ID","GITHUB_RUN_NUMBER","GITHUB_RUN_ATTEMPT",
                      "GITHUB_REPOSITORY","GITHUB_EVENT_NAME","RUNNER_ENVIRONMENT","GITHUB_REF",
                      "PROBE_PUSH_CREATED","PROBE_PUSH_DELETED","PROBE_PUSH_BEFORE","PROBE_PUSH_AFTER"}
    need(set(os.environ)<=allowed and os.environ.get("GITHUB_RUN_ID","").isdigit())
    need(hash_file(args.approval)==args.approval_sha256)
    approval=json.loads(args.approval.read_bytes())
    required={"status","workflow_sha","run_number","nonce","distribution_manifest_sha256","controller_sha256","source_manifest_sha256"}
    need(set(approval)==required and approval["status"]=="APPROVED_DISPOSABLE_GITHUB_VM_ONLY"
         and approval["controller_sha256"]==hash_file(P(__file__)))
    trigger_binding(os.environ,approval)
    nonce=approval["nonce"]
    need(re.fullmatch(r"[a-f0-9]{16}",nonce) and P("/proc/1/comm").read_text().strip()=="systemd"
         and P("/proc/self/uid_map").read_text().split()==P("/proc/self/gid_map").read_text().split()==["0","0","4294967295"])
    need(show().get("LoadState")=="not-found" and not any(os.path.lexists(x) for x in
        (STATE,CACHE,UNIT_PATH,P("/run/credentials")/UNIT,P(RELEASE),RUN)))
    need(not call(["/usr/bin/ss","-H","-ltn","sport","=","5004"]))
    phase("PUBLIC_INPUTS")
    rows,public=secure_input(args,approval)
    # Guest public ancestors must be traversable by UID981. All private
    # directories and receipt/credential files still use explicit 0700/0600.
    os.umask(0o022)
    RUN.mkdir(mode=0o755);scratch=RUN/nonce;scratch.mkdir(mode=0o700)
    phase("CLAIM")
    write(scratch/"ATTEMPTED.json",b"{\"no_replay\":true}\n")
    phase("ACCOUNT")
    ensure_account()
    derived,install_sha,runtime_inventory_sha,pyvenv_sha=setup_runtime(args,rows,public,scratch)
    phase("SOURCE_COPY")
    root=P(RELEASE);root.mkdir(mode=0o755,parents=True)
    need(hash_file(args.source_manifest)==approval["source_manifest_sha256"])
    source_manifest=json.loads(args.source_manifest.read_bytes())
    need(source_manifest["source_sha"]==SOURCE)
    expected=[row for row in source_manifest["members"] if row["path"]=="scripts/run-formal-main.py"
              or row["path"].startswith(("web/backend/","web/frontend/"))]
    need(expected)
    seen=set()
    for row in expected:
        name=row["path"]
        pp=pathlib.PurePosixPath(name)
        need(name not in seen and not pp.is_absolute() and ".." not in pp.parts and
             row["git_mode"] in ("100644","100755") and re.fullmatch(r"[a-f0-9]{40}",row["git_blob"]))
        seen.add(name)
        # Read only exact approved Git blobs. Never create an archive that
        # serializes excluded .env.example or data/api_keys.jsonl.
        raw=read_blob(["/usr/bin/git","-c","safe.directory="+str(args.checkout),"-C",str(args.checkout),
                  "cat-file","blob",row["git_blob"]],row["bytes"])
        need(len(raw)==row["bytes"] and hashlib.sha256(raw).hexdigest()==row["sha256"])
        dest=root/name;dest.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
        write(dest,raw,0o755 if row["git_mode"]=="100755" else 0o644)
    need(hash_file(P(ENTRY))==FORMAL_ENTRY_SHA)
    phase("SYNTHETIC_CREDENTIALS")
    values=synthetic_values()
    encrypted=scratch/"encrypted";encrypted.mkdir(mode=0o700)
    for slot,value in zip(CREDENTIALS,values):
        cipher=encrypted/slot
        call(["/usr/bin/systemd-creds","encrypt","--with-key=host","--name="+slot,"-",str(cipher)],data=value)
        cipher.chmod(0o600)
        # Verify the synthetic same-guest host key and embedded slot label
        # before service launch. Output is held in memory, never logged.
        need(call(["/usr/bin/systemd-creds","decrypt","--name="+slot,str(cipher),"-"])==value)
    phase("SYNTHETIC_DB")
    seed(root,nonce,values);values.clear()
    write(scratch/"synthetic.env",b"SMTP_HOST=127.0.0.1\nSMTP_PORT=2465\nSMTP_USERNAME=synthetic\nSMTP_FROM_EMAIL=synthetic@example.invalid\nADMIN_NOTIFICATION_EMAIL=synthetic@example.invalid\nSMTP_STARTTLS=true\nSMTP_USE_SSL=false\nSMTP_TIMEOUT_SECONDS=2\n")
    write(scratch/"GUEST_ONLY",b"isolated synthetic GitHub guest only\n")
    profile,unit=render(args.unit.read_bytes(),P(ENTRY).read_bytes(),unit_sha=FORMAL_UNIT_SHA,entry_sha=FORMAL_ENTRY_SHA,nonce=nonce)
    need(DEADLINE-time.monotonic()>=120)
    phase("UNIT_WRITE")
    write(UNIT_PATH,unit,0o644)
    owned=False;observation=None;manager=None;retired=False
    try:
        call(["/usr/bin/systemctl","daemon-reload"])
        owned=True
        phase("UNIT_START")
        call(["/usr/bin/systemctl","start","--no-block",UNIT],maxsec=10)
        phase("HEALTH")
        startup_deadline=min(time.monotonic()+70,DEADLINE-35)
        bound=None
        while time.monotonic()<startup_deadline:
            manager=show()
            pid=manager.get("MainPID","0")
            if manager.get("ActiveState")=="failed":raise RuntimeError("GUEST_MAIN_FAILED")
            if manager.get("ActiveState")=="active" and pid.isdecimal() and int(pid)>0:
                proc=P("/proc")/pid
                try:
                    exe=(proc/"exe").resolve(strict=True)
                    argv=(proc/"cmdline").read_bytes().split(b"\0")
                except FileNotFoundError:
                    time.sleep(.5)
                    continue
                if exe!=P(ELF):
                    # Type=simple may report the pre-exec child briefly.
                    need(bound is None)
                    time.sleep(.5)
                    continue
                need(argv==[RUNTIME.encode(),b"-I",b"-B",ENTRY.encode(),b""]
                     and manager.get("ControlGroup")=="/system.slice/"+UNIT
                     and re.fullmatch(r"[a-f0-9]{32}",manager.get("InvocationID","")))
                observed=(pid,manager["InvocationID"])
                if bound is None:bound=observed
                need(bound==observed)
                need(os.stat(proc/"ns/net").st_ino!=os.stat("/proc/self/ns/net").st_ino and
                     os.stat(proc/"ns/mnt").st_ino!=os.stat("/proc/self/ns/mnt").st_ino)
                try:observation=health(pid);break
                except (subprocess.SubprocessError,RuntimeError):pass
            time.sleep(.5)
        need(observation is not None and show()["InvocationID"]==manager["InvocationID"]
             and re.fullmatch(r"[a-f0-9]{32}",manager["InvocationID"]))
        # Coarse mount metadata only; never open one of the five credential files.
        cred=proc/"root/run/credentials"/UNIT
        need(bool(os.statvfs(cred).f_flag&os.ST_RDONLY) and
             all((cred/slot).is_file() for slot in CREDENTIALS))
    except Exception:
        FAILURE_PHASE=PHASE
        raise
    finally:
        if owned:
            phase("RETIRE")
            # Do not try to restart; bounded retirement of the owned guest unit.
            subprocess.run(["/usr/bin/systemctl","stop",UNIT],env=ENV,stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=25,check=False)
            end=show()
            group=manager.get("ControlGroup") if manager else None
            cgroup=P("/sys/fs/cgroup")/group.lstrip("/") if group and group.startswith("/system.slice/") else None
            retired=end.get("MainPID")==end.get("ControlPID")=="0" and end.get("ActiveState")=="inactive" and end.get("Result")=="success" and end.get("ExecMainStatus")=="0" and (
                cgroup is not None and (not cgroup.exists() or "populated 0" in (cgroup/"cgroup.events").read_text()))
        if hash_file(UNIT_PATH)==profile["guest_unit_sha256"]:
            UNIT_PATH.unlink()
            subprocess.run(["/usr/bin/systemctl","daemon-reload"],env=ENV,timeout=10,check=False,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    need(retired and show().get("LoadState")=="not-found" and not (P("/run/credentials")/UNIT).exists())
    phase("RECEIPT")
    receipt={"status":"GITHUB_VM_SYNTHETIC_ACTUAL_LAUNCHER_PASS_NOT_GO","source":SOURCE,"elf_sha256":ELF_SHA,
             "guest_unit_sha256":profile["guest_unit_sha256"],"install_lock_sha256":install_sha,"derived_wheels":derived,
             "run_id":os.environ["GITHUB_RUN_ID"],"workflow_sha":approval["workflow_sha"],
             "systemd_version":call(["/usr/bin/systemctl","--version"],maxsec=3).decode().splitlines()[0],
             "boot_sha256":hashlib.sha256(P("/proc/sys/kernel/random/boot_id").read_bytes()).hexdigest(),
             "invocation_sha256":hashlib.sha256(manager["InvocationID"].encode()).hexdigest(),
             "runtime_inventory_sha256":runtime_inventory_sha,"pyvenv_sha256":pyvenv_sha,"readonly_credential_mount":True,
             "healthy":observation,"retired":True,"production_contacted":False,"target_os_equivalence":False,
             "runtime_current_target_closure":False}
    write(scratch/"PUBLIC-RECEIPT.json",(json.dumps(receipt,sort_keys=True)+"\n").encode())
    print(json.dumps(receipt,sort_keys=True))

if __name__=="__main__":
    try:main()
    except Exception as failure:
        kind=("child_nonzero" if isinstance(failure,subprocess.CalledProcessError) else
              "timeout" if isinstance(failure,subprocess.TimeoutExpired) else
              "os_error" if isinstance(failure,OSError) else "validation")
        print(json.dumps({"status":"HOLD_RECONCILE_NO_REPLAY","phase":FAILURE_PHASE or PHASE,"last_action":PHASE,"failure_kind":kind,
                          "inventory_reason":INVENTORY_REASON,"inventory_location":INVENTORY_LOCATION,
                          "child_returncode":failure.returncode if isinstance(failure,subprocess.CalledProcessError) else None}),file=sys.stderr)
        raise SystemExit(1) from None
