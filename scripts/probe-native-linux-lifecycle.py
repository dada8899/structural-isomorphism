#!/usr/bin/env python3
"""Fixed disposable GitHub VM controller. No target IO occurs on import.

Engineering alone never authorizes running this script. The reviewed final SHA
and one first-push attempt require the separate execution decision.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
BRANCH='refs/heads/codex/structure-native-linux-lifecycle-20261023'
REPOSITORY='dada8899/structural-isomorphism'
USER=GROUP='structural-native-probe'
UNIT='structural-web.service'
WORK=Path('/run/structural-native-probe')
SECRETS=Path('/run/structural-native-probe-secrets')
DEPOT=Path('/opt/structural-native-lifecycle')
STATE=Path('/var/lib/structural-isomorphism')
CACHE=Path('/var/cache/structural-isomorphism')
GRANT_DIR=Path('/etc/structural')
UNIT_FILE=Path('/etc/systemd/system')/UNIT
FIXTURE='web/backend/tests/acceptance/native_linux_lifecycle_fixture.py'
IDS=('structural-jwt-secret','structural-sso-secret','structural-privacy-hmac-key','structural-share-token-secret','structural-smtp-password')
PROVIDER_ID='structural-deepseek-api-key'
MARKER_NAME='native-lifecycle-clock.json'
RECEIPT_NAME='native-lifecycle-receipt.json'
REASONS=('OK','PRECHECK','CLOCK','SOURCE','UNIT','HTTP','OBSERVER','FACTS','CLEANUP','INTERNAL')
PHASES=('stock_base','stock_genesis','stock_restart','instrumented')
TOOLS=('/usr/bin/systemctl','/usr/bin/nsenter','/usr/bin/setpriv','/usr/bin/openssl','/usr/sbin/useradd','/usr/sbin/userdel','/usr/sbin/groupadd','/usr/sbin/groupdel')
SDKS={'pytest':'9.0.3','playwright':'1.59.0','pytest-playwright':'0.7.2','fastapi':'0.135.0','pydantic':'2.7.4','starlette':'1.3.1','uvicorn':'0.27.1','PyJWT':'2.15.1','slowapi':'0.1.9','structlog':'25.5.0'}
IMPORT_SDKS={'httpx':'0.27.2','numpy':'1.26.3'}
GIT=('git','-c','filter.lfs.process=','-c','filter.lfs.clean=cat','-c','filter.lfs.smudge=cat','-c','filter.lfs.required=false')


class ProbeFailure(RuntimeError):
    def __init__(self,reason):self.reason=reason if reason in REASONS else 'INTERNAL';super().__init__(self.reason)


def strict_json(raw,limit=32768):
    if type(raw) is not bytes or not 0<len(raw)<=limit:raise ProbeFailure('PRECHECK')
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ProbeFailure('PRECHECK')
            result[k]=v
        return result
    def invalid(_):raise ProbeFailure('PRECHECK')
    result=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)
    stack=[(result,0)];nodes=0
    while stack:
        item,depth=stack.pop();nodes+=1
        if nodes>4096 or depth>16:raise ProbeFailure('PRECHECK')
        if type(item) is float and not math.isfinite(item):raise ProbeFailure('PRECHECK')
        if type(item) is dict:stack.extend((v,depth+1) for v in item.values())
        elif type(item) is list:stack.extend((v,depth+1) for v in item)
    return result


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def hex40(value):return type(value) is str and re.fullmatch('[0-9a-f]{40}',value) is not None
def stat_key(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def mirror_selected(relative):
    if type(relative) is not str or Path(relative).is_absolute() or '..' in Path(relative).parts or any(part.startswith('.env') for part in Path(relative).parts):raise ProbeFailure('SOURCE')
    if relative in ('web/__init__.py','scripts/run-formal-main.py',FIXTURE,'web/frontend/auth-login.html','web/frontend/auth-verify.html','web/frontend/assets/data/papers-manifest.json'):return True
    if relative in ('structural_isomorphism/__init__.py','structural_isomorphism/search.py','structural_isomorphism/model.py','structural_isomorphism/data.py','structural_isomorphism/discovery_evidence.py'):return True
    if relative.startswith('web/frontend/assets/data/papers/') and Path(relative).suffix=='.md':return True
    return relative.startswith('web/backend/') and not relative.startswith('web/backend/tests/') and Path(relative).suffix=='.py'


def catalog_paths(raw):
    value=strict_json(raw,65536);paths=[]
    if type(value) is not dict or type(value.get('groups')) is not list:raise ProbeFailure('SOURCE')
    for group in value['groups']:
        if type(group) is not dict or type(group.get('papers')) is not list:raise ProbeFailure('SOURCE')
        for paper in group['papers']:
            slug=paper.get('slug') if type(paper) is dict else None
            if type(slug) is not str or not re.fullmatch(r'(?!.*\.\.)(?!.*\.$)[a-z0-9][a-z0-9._-]{1,119}',slug):raise ProbeFailure('SOURCE')
            paths.append('web/frontend/assets/data/papers/'+slug+'.md')
    if len(paths)!=20 or len(set(paths))!=20:raise ProbeFailure('SOURCE')
    return frozenset(paths)


def validate_metadata(meta):
    keys={'event','repository','ref','head','attempt','hosted','os','arch','run_id','created','deleted','before','after'}
    if type(meta) is not dict or set(meta)!=keys:raise ProbeFailure('PRECHECK')
    fixed={'event':'push','repository':REPOSITORY,'ref':BRANCH,'attempt':'1','hosted':'github-hosted','os':'Linux','arch':'X64','created':'true','deleted':'false','before':'0'*40}
    if any(type(meta[k]) is not str for k in keys) or any(meta[k]!=v for k,v in fixed.items()) or not hex40(meta['head']) or meta['head']!=meta['after'] or not re.fullmatch('[1-9][0-9]{0,19}',meta['run_id']):raise ProbeFailure('PRECHECK')


class Budget:
    def __init__(self,marker,meta,now):
        validate_metadata(meta)
        if type(marker) is not dict or set(marker)!= {'protocol','head','run_id','attempt','started','deadline'}:raise ProbeFailure('CLOCK')
        if marker['protocol']!='native-lifecycle-clock-v1' or any(marker[k]!=meta[k] for k in ('head','run_id','attempt')):raise ProbeFailure('CLOCK')
        start,end=marker['started'],marker['deadline']
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end,now)) or not 0<start<=now<end or end!=start+300:raise ProbeFailure('CLOCK')
        self.started=now;self.deadline=min(now+270,end)
        self.require(now,new=True)
    def require(self,now=None,*,new=False,ceiling=30):
        now=time.monotonic() if now is None else now
        if type(new) is not bool or any(type(v) not in (int,float) or not math.isfinite(v) for v in (now,ceiling)) or ceiling<=0:raise ProbeFailure('CLOCK')
        left=self.deadline-now-(30 if new else 0)
        if left<=0:raise ProbeFailure('CLOCK')
        return min(left,ceiling)


def empty_receipt(head):
    return {'protocol':'native-linux-lifecycle-probe-v1','head':head,'tree':None,'code_digest':None,'outcome':'FAIL','reason':'PRECHECK','elapsed_ms':0,
        'phases':{k:False for k in PHASES},'stock':{'typed_receipts':None,'creator_connections':None,'creator_fds':None,'clean_exit_inferred':False,'credential_invocation_changed':None},
        'instrumented':{'source_closed':None,'native_closed':None,'proof_taken':None,'component_woken':None,'component_ms':None,'same_deadline_ref':None,'within_main_deadline':None,'main_stop_to_closed_ms':None,'connections_born':None,'connections_creator_closed':None,'connections_property_closed':None,'fds_born':None,'fds_creator_closed':None,'fds_property_closed':None,'observer_failed':None},
        'financial':{'initial_empty':False,'normal_restart_unchanged':False,'pre_get_closed_unreserved':False,'held':None,'upper_booked':None,'settled':None,'native_unknown_held_verified':False},
        'resources':{'children_started':0,'children_reaped':0,'unit_invocations':0,'unit_exited':0,'cgroup_empty':False,'credential_mount_gone':False,'unit_removed':False,'directories_removed':False,'user_removed':False,'cleanup_uncertain':True,'forced':False},
        'scope':{'stock':'systemd-entry-finite-inference','instrumented':'original-entry-runpy-observation','counts':'instrumented-observed-subset-only','component':'active-slot-stopfd-select-only','provider':'not_run','public_source':'not_run'}}


def validate_receipt(value):
    template=empty_receipt('0'*40)
    if type(value) is not dict or set(value)!=set(template):raise ProbeFailure('PRECHECK')
    if not hex40(value['head']) or value['tree'] is not None and not hex40(value['tree']):raise ProbeFailure('PRECHECK')
    if value['code_digest'] is not None and (type(value['code_digest']) is not str or not re.fullmatch('[0-9a-f]{64}',value['code_digest'])):raise ProbeFailure('PRECHECK')
    if value['protocol']!=template['protocol'] or value['outcome'] not in ('PASS','FAIL') or value['reason'] not in REASONS:raise ProbeFailure('PRECHECK')
    if type(value['elapsed_ms']) is not int or not 0<=value['elapsed_ms']<=330000:raise ProbeFailure('PRECHECK')
    for key in ('phases','stock','instrumented','financial','resources','scope'):
        if type(value[key]) is not dict or set(value[key])!=set(template[key]):raise ProbeFailure('PRECHECK')
    if any(type(v) is not bool for v in value['phases'].values()):raise ProbeFailure('PRECHECK')
    if value['scope']!=template['scope'] or any(value['stock'][k] is not None for k in ('typed_receipts','creator_connections','creator_fds')) or type(value['stock']['clean_exit_inferred']) is not bool or value['stock']['credential_invocation_changed'] is not None and type(value['stock']['credential_invocation_changed']) is not bool:raise ProbeFailure('PRECHECK')
    bools={'source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline','observer_failed'}
    for key,item in value['instrumented'].items():
        if key in bools:
            if item is not None and type(item) is not bool:raise ProbeFailure('PRECHECK')
        elif item is not None and (type(item) is not int or not 0<=item<=1000000):raise ProbeFailure('PRECHECK')
    for prefix in ('connections','fds'):
        born,creator,closed=(value['instrumented'][prefix+suffix] for suffix in ('_born','_creator_closed','_property_closed'))
        if all(v is not None for v in (born,creator,closed)) and not 0<=creator<=closed<=born:raise ProbeFailure('PRECHECK')
    for key,item in value['financial'].items():
        if key in ('held','upper_booked','settled'):
            if item is not None and (type(item) is not int or not 0<=item<=300000000):raise ProbeFailure('PRECHECK')
        elif type(item) is not bool:raise ProbeFailure('PRECHECK')
    if value['financial']['native_unknown_held_verified'] is not False:raise ProbeFailure('PRECHECK')
    for key,item in value['resources'].items():
        if key in ('children_started','children_reaped','unit_invocations','unit_exited'):
            if type(item) is not int or not 0<=item<=1000:raise ProbeFailure('PRECHECK')
        elif type(item) is not bool:raise ProbeFailure('PRECHECK')
    if value['outcome']=='PASS':
        required=('cgroup_empty','credential_mount_gone','unit_removed','directories_removed','user_removed')
        if (not all(value['phases'].values()) or value['reason']!='OK' or value['resources']['cleanup_uncertain'] or value['resources']['forced']
                or not all(value['resources'][k] for k in required) or value['resources']['children_started']!=value['resources']['children_reaped']
                or not all(value['financial'][k] for k in ('initial_empty','normal_restart_unchanged','pre_get_closed_unreserved'))
                or not all(value['instrumented'][k] is True for k in ('source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline'))
                or value['instrumented']['observer_failed'] is not False):raise ProbeFailure('PRECHECK')
    raw=canonical(value)
    if len(raw)>32768:raise ProbeFailure('PRECHECK')
    return raw


class Controller:
    def __init__(self,meta,budget,python):
        self.meta,self.budget,self.python=meta,budget,python;self.result=empty_receipt(meta['head']);self.children=[];self.paths=[];self.user=False;self.group=False;self.unit_written=False;self.invocations=[];self.server=None;self.uid=self.gid=None;self.password=None;self.rpc_buffer=b'';self.uncertain=False;self.attempts={};self.group_attempted=False;self.user_attempted=False;self.group_record=None;self.user_record=None
    def _process_identity(self,process):
        # PID alone is not a birth witness. The start tick, proc inode, parent,
        # process group and session must still describe this owned child.
        pid=process.pid
        if type(pid) is not int or pid<=0:raise ProbeFailure('CLEANUP')
        root=Path('/proc')/str(pid)
        def snapshot():
            info=root.stat();raw=(root/'stat').read_text();end=raw.rfind(') ')
            fields=raw[end+2:].split()
            if end<0 or raw[:raw.find(' (')]!=str(pid) or len(fields)<20:raise ProbeFailure('CLEANUP')
            parent,group,session,tick=(int(fields[i]) for i in (1,2,3,19))
            if parent!=os.getpid() or group!=pid or session!=pid or tick<0:raise ProbeFailure('CLEANUP')
            return info.st_dev,info.st_ino,parent,group,session,tick
        before=snapshot()
        if snapshot()!=before:raise ProbeFailure('CLEANUP')
        return before
    def _spawn(self,argv,*,new=True,**kwargs):
        self.budget.require(new=new)
        kind=subprocess.Popen
        if not isinstance(kind,type):raise ProbeFailure('PRECHECK')
        process=kind.__new__(kind)
        # Retain the actual object before __init__: it may fork and then raise.
        self.children.append(process)
        record={'complete':False,'birth':'unborn','identity':None,'reaped':False}
        self.attempts[id(process)]=record
        try:
            # Allocation has no native resources. Once initialization is entered,
            # even _child_created=False cannot exclude an interrupted birth.
            record['birth']='unknown'
            kind.__init__(process,argv,**kwargs)
            record['complete']=True
            try:record['identity']=self._process_identity(process)
            except FileNotFoundError:
                if process.poll() is None:raise ProbeFailure('CLEANUP')
                record['reaped']=True
            record['birth']='born'
        except BaseException:
            # Retain every incomplete constructor; neither numeric PID fields
            # nor a default false _child_created establish physical retirement.
            self.uncertain=True
            raise
        return process
    def _signal(self,process,sig):
        record=self.attempts[id(process)]
        if not record['complete'] or record['identity'] is None or self._process_identity(process)!=record['identity']:raise ProbeFailure('CLEANUP')
        os.killpg(process.pid,sig)
    def command(self,argv,*,input=None,clean=False,limit=30,env=None):
        timeout=self.budget.require(new=not clean,ceiling=limit)
        process=self._spawn(argv,new=not clean,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=ROOT,env=env or {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'},start_new_session=True)
        try:out,_=process.communicate(input,timeout=timeout)
        except subprocess.TimeoutExpired:
            self.uncertain=True;self.result['resources']['forced']=True
            self._signal(process,signal.SIGKILL);process.wait(timeout=self.budget.require(ceiling=2));raise ProbeFailure('CLOCK')
        self.attempts[id(process)]['reaped']=process.returncode is not None
        if process.returncode or len(out)>1048576:raise ProbeFailure('PRECHECK')
        return out
    def _account_record(self,kind,expected_id=None):
        group=kind=='group';name=GROUP if group else USER
        rows=[tuple(line.split(':')) for line in Path('/etc/group' if group else '/etc/passwd').read_text().splitlines()]
        matches=[row for row in rows if row[0]==name]
        if len(matches)!=1:raise ProbeFailure('CLEANUP')
        row=matches[0]
        if len(row)!=(4 if group else 7) or not row[2].isdecimal() or not 0<int(row[2])<2147483648 or str(int(row[2]))!=row[2]:raise ProbeFailure('CLEANUP')
        number=int(row[2])
        if expected_id is not None and number!=expected_id:raise ProbeFailure('CLEANUP')
        if sum(len(other)>2 and other[2]==row[2] for other in rows)!=1:raise ProbeFailure('CLEANUP')
        if group:
            if row!=(GROUP,'x',str(number),''):raise ProbeFailure('CLEANUP')
        elif row!=(USER,'x',str(number),str(self.gid),'',str(STATE),'/usr/sbin/nologin'):raise ProbeFailure('CLEANUP')
        return row
    def _account_absent(self,kind,record):
        name=GROUP if kind=='group' else USER
        rows=[line.split(':') for line in Path('/etc/group' if kind=='group' else '/etc/passwd').read_text().splitlines()]
        return not any(row[0]==name or len(row)>2 and row[2]==record[2] for row in rows)
    def _require_account_births(self):
        # A failed command may have changed the account database. Neither the
        # attempt nor a matching name supplies deletion ownership.
        if self.user_attempted and self.user_record is None or self.group_attempted and self.group_record is None:raise ProbeFailure('CLEANUP')
        if self.group_record is not None and self._account_record('group',self.gid)!=self.group_record:raise ProbeFailure('CLEANUP')
        if self.user_record is not None and self._account_record('user',self.uid)!=self.user_record:raise ProbeFailure('CLEANUP')
    def _remove_accounts(self):
        self._require_account_births()
        if self.user_record is not None:
            # Recheck immediately before the name-taking system command.
            if self._account_record('user',self.uid)!=self.user_record:raise ProbeFailure('CLEANUP')
            self.command(['/usr/sbin/userdel',USER],clean=True,limit=3)
            if not self._account_absent('user',self.user_record):raise ProbeFailure('CLEANUP')
        if self.group_record is not None:
            # Ubuntu userdel may already remove the matching empty user group.
            # Confirm name AND original GID absent; never delete a replacement.
            if not self._account_absent('group',self.group_record):
                if self._account_record('group',self.gid)!=self.group_record:raise ProbeFailure('CLEANUP')
                self.command(['/usr/sbin/groupdel',GROUP],clean=True,limit=3)
                if not self._account_absent('group',self.group_record):raise ProbeFailure('CLEANUP')
    def absent(self,path):
        self.budget.require(new=True)
        if path.exists() or path.is_symlink():raise ProbeFailure('PRECHECK')
    def directory(self,path,uid=0,gid=0,mode=0o700):
        self.absent(path);path.mkdir(mode=mode);self.paths.append(path);os.chown(path,uid,gid);path.chmod(mode)
    def write(self,path,data,uid=0,gid=0,mode=0o600):
        self.budget.require(new=True);self.absent(path)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
        self.paths.append(path)
        try:
            os.fchown(fd,uid,gid);os.fchmod(fd,mode)
            if os.write(fd,data)!=len(data):raise ProbeFailure('PRECHECK')
            os.fsync(fd)
        finally:os.close(fd)
    def preflight(self):
        if sys.platform!='linux' or os.geteuid()!=0 or os.getuid()!=0 or sys.version_info[:2]!=(3,11) or sys.implementation.name!='cpython' or not sys.flags.isolated or not sys.flags.dont_write_bytecode:raise ProbeFailure('PRECHECK')
        if os.uname().machine!='x86_64' or Path('/proc/1/comm').read_text().strip()!='systemd':raise ProbeFailure('PRECHECK')
        os_release=Path('/etc/os-release').read_text()
        if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:raise ProbeFailure('PRECHECK')
        for tool in TOOLS:
            if not Path(tool).is_file():raise ProbeFailure('PRECHECK')
        from importlib.metadata import version
        if any(version(name)!=expected for name,expected in {**SDKS,**IMPORT_SDKS}.items()):raise ProbeFailure('PRECHECK')
        if not self.command(['/usr/bin/systemctl','--version']).startswith(b'systemd 255 '):raise ProbeFailure('PRECHECK')
        for path in (WORK,SECRETS,DEPOT,STATE,CACHE,GRANT_DIR,UNIT_FILE,Path('/run/systemd/system')/UNIT,Path('/run/credentials')/UNIT):self.absent(path)
        for path,name in ((Path('/etc/passwd'),USER),(Path('/etc/group'),GROUP)):
            if any(line.split(':',1)[0]==name for line in path.read_text().splitlines()):raise ProbeFailure('PRECHECK')
        if self.command([*GIT,'rev-parse','HEAD']).decode().strip()!=self.meta['head'] or self.command([*GIT,'status','--porcelain','--untracked-files=all']).strip():raise ProbeFailure('SOURCE')
        self.result['tree']=self.command([*GIT,'rev-parse','HEAD^{tree}']).decode().strip()
    def prepare(self):
        self.group_attempted=True;self.command(['/usr/sbin/groupadd','--system',GROUP])
        self.group_record=self._account_record('group');self.gid=int(self.group_record[2]);self.group=True
        self.user_attempted=True;self.command(['/usr/sbin/useradd','--system','--gid',GROUP,'--no-create-home','--no-log-init','-K','CREATE_MAIL_SPOOL=no','--home-dir',str(STATE),'--shell','/usr/sbin/nologin',USER])
        self.user_record=self._account_record('user');self.uid=int(self.user_record[2]);self.user=True
        if self._account_record('group',self.gid)!=self.group_record:raise ProbeFailure('CLEANUP')
        for path in (WORK,STATE,CACHE):self.directory(path,self.uid,self.gid)
        self.directory(STATE/'logs',self.uid,self.gid);self.directory(SECRETS);self.directory(DEPOT,mode=0o755)
        entries=self.command([*GIT,'ls-tree','-r','-z','HEAD']).decode().split('\0');total=0;expected_papers=None;copied_papers=set()
        for entry in entries:
            if not entry:continue
            metadata,relative=entry.split('\t');mode,kind,oid=metadata.split()
            if not mirror_selected(relative):continue
            if mode not in ('100644','100755') or kind!='blob':raise ProbeFailure('SOURCE')
            source=ROOT/relative
            if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent!=ROOT and ROOT in parent.parents):raise ProbeFailure('SOURCE')
            self.budget.require(new=True)
            descriptor=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                before=os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=1048576:raise ProbeFailure('SOURCE')
                raw=os.read(descriptor,1048577)
                if stat_key(os.fstat(descriptor))!=stat_key(before) or stat_key(source.lstat())!=stat_key(before):raise ProbeFailure('SOURCE')
            finally:os.close(descriptor)
            total+=len(raw)
            if len(raw)>1048576 or total>16777216 or raw.startswith(b'version https://git-lfs.github.com/spec/'):raise ProbeFailure('SOURCE')
            if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=oid:raise ProbeFailure('SOURCE')
            if relative=='web/frontend/assets/data/papers-manifest.json':expected_papers=catalog_paths(raw)
            if relative.startswith('web/frontend/assets/data/papers/') and relative.endswith('.md'):copied_papers.add(relative)
            target=DEPOT/relative
            for parent in reversed(target.parents):
                if parent==DEPOT or DEPOT not in parent.parents:continue
                if not parent.exists():self.directory(parent,mode=0o755)
            self.write(target,raw,mode=0o644)
        if expected_papers is None or copied_papers!=expected_papers:raise ProbeFailure('SOURCE')
        if not (DEPOT/'web/frontend/assets').exists():self.directory(DEPOT/'web/frontend/assets',mode=0o755)
        if not (DEPOT/FIXTURE).is_file():raise ProbeFailure('SOURCE')
        import secrets
        values=[secrets.token_urlsafe(48),secrets.token_urlsafe(48),secrets.token_hex(32),secrets.token_urlsafe(48),secrets.token_urlsafe(32)]
        self.password=values[-1]
        for name,value in zip(IDS,values):self.write(SECRETS/name,value.encode())
        self.write(SECRETS/PROVIDER_ID,('synthetic-no-provider-permission-'+uuid4().hex).encode())
        self.command(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=beta.structural.bytedance.city','-addext','subjectAltName=DNS:beta.structural.bytedance.city','-keyout',str(WORK/'local-key.pem'),'-out',str(WORK/'local-cert.pem')],limit=10)
        for path in (WORK/'local-key.pem',WORK/'local-cert.pem'):self.paths.append(path);os.chown(path,self.uid,self.gid);path.chmod(0o400)
        self.command(self.as_user([self.python,'-I','-B',str(DEPOT/FIXTURE),'bootstrap']),env=self.environment())
    def as_user(self,argv):return ['/usr/bin/setpriv','--reuid',str(self.uid),'--regid',str(self.gid),'--clear-groups',*argv]
    def environment(self):
        return {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(STATE),'STRUCTURAL_ENV':'prod','AUTH_ENABLED':'true','AUTH_DEV_MODE':'false','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':'https://beta.structural.bytedance.city','AUTH_DATA_DIR':str(STATE),'STRUCTURAL_SSO_DATA_DIR':str(STATE),'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','SMTP_HOST':'127.0.0.1','SMTP_PORT':'18025','SMTP_USERNAME':'native-probe','SMTP_FROM_EMAIL':'native-linux-sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'native-linux-admin@example.invalid','SMTP_STARTTLS':'false','SMTP_USE_SSL':'false','SMTP_TIMEOUT_SECONDS':'2'}
    def install_unit(self,provider=False,observed=False):
        self.budget.require(new=True)
        if self.unit_written:
            UNIT_FILE.unlink();self.paths.remove(UNIT_FILE);self.unit_written=False
        command=[self.python,'-I','-B',str(DEPOT/FIXTURE),'observe'] if observed else [self.python,'-I','-B',str(DEPOT/'scripts/run-formal-main.py')]
        if any(any(c in arg for c in ('\n','\r','%','"',' ')) for arg in command):raise ProbeFailure('SOURCE')
        lines=['[Unit]','Description=Owned disposable native lifecycle probe','[Service]','Type=simple','User='+USER,'Group='+GROUP,'UMask=0077','LimitCORE=0','NoNewPrivileges=yes','PrivateNetwork=yes','TimeoutStartSec=30','TimeoutStopSec=30','KillMode=control-group','Restart=no','WorkingDirectory='+str(DEPOT/'web/backend'),'ExecStart='+' '.join(command),'StandardOutput=null','StandardError=null']
        for key,value in self.environment().items():lines.append('Environment="'+key+'='+value+'"')
        for name in (*IDS,*((PROVIDER_ID,) if provider else ())):lines.append('LoadCredential='+name+':'+str(SECRETS/name))
        self.write(UNIT_FILE,('\n'.join(lines)+'\n').encode(),mode=0o644);self.unit_written=True
        self.command(['/usr/bin/systemctl','daemon-reload'])
    def unit_info(self,clean=False):
        raw=self.command(['/usr/bin/systemctl','show',UNIT,'--property=MainPID,ControlGroup,InvocationID,ActiveState,Result,ExecMainStatus'],clean=clean,limit=3).decode()
        rows=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        if set(rows)!= {'MainPID','ControlGroup','InvocationID','ActiveState','Result','ExecMainStatus'}:raise ProbeFailure('UNIT')
        return rows
    def start(self):
        self.command(['/usr/bin/systemctl','start',UNIT],limit=15)
        info=self.unit_info();pid=int(info['MainPID'])
        if pid<=1 or info['ControlGroup']!='/system.slice/'+UNIT or not re.fullmatch('[0-9a-f]{32}',info['InvocationID']):raise ProbeFailure('UNIT')
        if '0::/system.slice/'+UNIT not in Path('/proc/'+str(pid)+'/cgroup').read_text():raise ProbeFailure('UNIT')
        namespace=os.stat('/proc/'+str(pid)+'/ns/net');host=os.stat('/proc/self/ns/net')
        if (namespace.st_dev,namespace.st_ino)==(host.st_dev,host.st_ino):raise ProbeFailure('UNIT')
        self.invocations.append((pid,info['InvocationID']));self.result['resources']['unit_invocations']+=1
        # The fresh private netns must have no non-loopback IPv4/IPv6 route.
        routes=Path('/proc/'+str(pid)+'/net/route').read_text().splitlines()[1:]
        if any(line.split()[0]!='lo' for line in routes if line.strip()):raise ProbeFailure('UNIT')
        if any(line.split()[-1]!='lo' for line in Path('/proc/'+str(pid)+'/net/ipv6_route').read_text().splitlines()):raise ProbeFailure('UNIT')
        directory=Path('/proc/'+str(pid)+'/root/run/credentials')/UNIT
        if (directory.stat().st_uid,stat.S_IMODE(directory.stat().st_mode))!=(self.uid,0o500):raise ProbeFailure('UNIT')
        for name in (*IDS,*((PROVIDER_ID,) if (SECRETS/PROVIDER_ID).exists() and any('LoadCredential='+PROVIDER_ID+':' in line for line in UNIT_FILE.read_text().splitlines()) else ())):
            info=(directory/name).lstat()
            if not stat.S_ISREG(info.st_mode) or (info.st_uid,stat.S_IMODE(info.st_mode),info.st_nlink)!=(self.uid,0o400,1):raise ProbeFailure('UNIT')
        self.invocations[-1]=(*self.invocations[-1],(directory.stat().st_dev,directory.stat().st_ino))
        args=['/usr/bin/nsenter','--net=/proc/'+str(pid)+'/ns/net',*self.as_user([self.python,'-I','-B',str(DEPOT/FIXTURE),'serve'])]
        self.server=self._spawn(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(WORK)},start_new_session=True)
        self.server.stdin.write(canonical({'password':self.password,'deadline':self.budget.deadline-30})+b'\n');self.server.stdin.flush();self.rpc_buffer=b''
        if self.read_line()!=b'READY':raise ProbeFailure('HTTP')
    def read_line(self):
        while b'\n' not in self.rpc_buffer:
            timeout=self.budget.require(new=True,ceiling=10)
            if not select.select([self.server.stdout],[],[],timeout)[0]:raise ProbeFailure('HTTP')
            raw=os.read(self.server.stdout.fileno(),65536)
            if not raw or len(self.rpc_buffer)+len(raw)>65536:raise ProbeFailure('HTTP')
            self.rpc_buffer+=raw
        line,self.rpc_buffer=self.rpc_buffer.split(b'\n',1);return line
    def exercise(self,rid,approve=False):
        self.server.stdin.write(canonical({'rid':rid,'approve':approve})+b'\n');self.server.stdin.flush();value=strict_json(self.read_line(),65536)
        if type(value) is not dict or set(value)!= {'rid','identity_digest','native_ready'} or not re.fullmatch('[0-9a-f-]{36}',value['rid']) or not re.fullmatch('[0-9a-f]{64}',value['identity_digest']) or type(value['native_ready']) is not bool:raise ProbeFailure('HTTP')
        return value
    def stop(self):
        self.command(['/usr/bin/systemctl','stop',UNIT],clean=True,limit=30)
        info=self.unit_info(clean=True)
        if info['MainPID']!='0' or info['ActiveState']!='inactive' or info['Result']!='success' or info['ExecMainStatus']!='0':
            self.uncertain=True
            if info['Result']=='timeout':self.result['resources']['forced']=True
            raise ProbeFailure('UNIT')
        self.result['resources']['unit_exited']+=1
        group=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
        if group.exists() and group.read_text().strip():raise ProbeFailure('CLEANUP')
        self.result['resources']['cgroup_empty']=True
        if self.server is not None:
            self.server.stdin.close();self.server.wait(timeout=self.budget.require(ceiling=4))
            if self.server.returncode!=0:self.uncertain=True;raise ProbeFailure('CLEANUP')
            self.server=None
        if (Path('/run/credentials')/UNIT).exists():raise ProbeFailure('CLEANUP')
        self.result['resources']['credential_mount_gone']=True
    def facts(self):
        if self.unit_info(clean=True)['MainPID']!='0':raise ProbeFailure('FACTS')
        # A stopped, fully checkpointed specimen only. A root-owned reader must
        # not create root-owned WAL/SHM files or silently ignore a remaining WAL.
        database=STATE/'auth.sqlite3'
        if any(Path(str(database)+suffix).exists() for suffix in ('-wal','-shm','-journal')):raise ProbeFailure('FACTS')
        conn=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0)
        try:
            conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
            if conn.execute('SELECT version FROM research_schema').fetchone()[0]!=15:raise ProbeFailure('FACTS')
            principals=conn.execute("SELECT * FROM research_principals WHERE status='active'").fetchall()
            if len(principals)!=1:raise ProbeFailure('FACTS')
            p=dict(principals[0]);receipt=conn.execute("SELECT * FROM auth_registration_receipts WHERE gate_id=? AND kind='gate_resource'",(p['gate_id'],)).fetchone()
            if receipt is None:raise ProbeFailure('FACTS')
            tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'research_funding_%' OR name LIKE 'research_plan_native_%' OR name IN ('research_reservations','research_attempts','research_plan_dispatches')) ORDER BY name")]
            ledger={table:[dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in tables}
            if conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0]:raise ProbeFailure('FACTS')
            conn.rollback()
        finally:conn.close()
        db=(STATE/'auth.sqlite3').stat();gate=(STATE/'research-locks'/(p['gate_id']+'.lock')).stat()
        if (receipt['lock_dev'],receipt['lock_ino'])!=(gate.st_dev,gate.st_ino):raise ProbeFailure('FACTS')
        return p,ledger,[db.st_dev,db.st_ino],[gate.st_dev,gate.st_ino,gate.st_uid,stat.S_IMODE(gate.st_mode),gate.st_nlink]
    def grant(self,principal,db,gate):
        self.directory(GRANT_DIR,0,self.gid,0o750)
        flight=STATE/'native-plan-flight.lock';self.write(flight,b'',self.uid,self.gid);f=flight.stat()
        # Pure production exporters; no witness, session or authority is made.
        code="import sys,json;sys.path[:0]=["+repr(str(DEPOT/'web/backend'))+","+repr(str(DEPOT))+"];from research.native_live_grant import fixed_purpose_domains,approved_code_digest;print(json.dumps([fixed_purpose_domains(),approved_code_digest()]))"
        domains,code_digest=strict_json(self.command(self.as_user([self.python,'-I','-B','-c',code])),32768)
        self.result['code_digest']=code_digest
        grant={'protocol':'native-live-owner-grant-v1','project_ref':'structure-rebuild-v1','state':'active','grant_id':str(uuid4()),'grant_epoch':1,'principal_id':principal['id'],'auth_generation':principal['session_generation'],'principal_epoch':principal['epoch'],'owner_gate_id':principal['gate_id'],'database_identity':db,'owner_gate_identity':gate,'flight_identity':[f.st_dev,f.st_ino,f.st_uid,f.st_gid,stat.S_IMODE(f.st_mode),f.st_nlink],'account_id':str(uuid4()),'economic_binding':str(uuid4()),'credential_incarnation':'synthetic-'+uuid4().hex,'approved_cap_units':300000000,'risk_margin_units':2129920,'runtime_uid':self.uid,'runtime_gid':self.gid,'provider':'deepseek','model':'deepseek-flash','network_policy':'deepseek-fixed-https-v1','runtime_digest':hashlib.sha256((DEPOT/'web/backend/services/plan_runtime_transport.py').read_bytes()).hexdigest(),'approved_code_digest':code_digest,'purpose_domains':domains}
        self.write(GRANT_DIR/'native-live-grant.json',canonical(grant),0,self.gid,0o440)
    def events(self):
        p=WORK/'observed.jsonl'
        if not p.exists():return []
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:raise ProbeFailure('OBSERVER')
            raw=os.read(fd,32769)
        finally:os.close(fd)
        if len(raw)>32768:raise ProbeFailure('OBSERVER')
        # A concurrent append may be incomplete; parse only complete frames.
        values=[strict_json(line[:-1],2048) for line in raw.splitlines(keepends=True) if line.endswith(b'\n')]
        fields={'SLOT_BEFORE_GET':set(),'SLOT_WOKEN':{'elapsed_ms'},'PROOF_TAKEN':set(),'SOURCE_JOIN':{'closed'},'NATIVE_JOIN':{'closed'},'FINAL':set(self.result['instrumented']),'OBSERVER_FAILED':set(),'NETWORK_ENTRY':set()}
        for item in values:
            if type(item) is not dict or set(item)!= {'event','values'} or item['event'] not in fields or type(item['values']) is not dict or set(item['values'])!=fields[item['event']] or any(type(v) not in (int,bool,type(None)) for v in item['values'].values()):raise ProbeFailure('OBSERVER')
        if any(sum(v['event']==event for v in values)>1 for event in fields):raise ProbeFailure('OBSERVER')
        return values
    def run(self):
        self.preflight();self.prepare();self.install_unit();self.start();first=self.exercise(None)
        if first['native_ready']:raise ProbeFailure('FACTS')
        self.stop();principal,ledger,db,gate=self.facts()
        if any(ledger.values()):raise ProbeFailure('FACTS')
        self.result['financial']['initial_empty']=True;self.result['phases']['stock_base']=True
        self.grant(principal,db,gate);self.install_unit(provider=True);self.start();second=self.exercise(first['rid'])
        if not second['native_ready'] or first['identity_digest']!=second['identity_digest']:raise ProbeFailure('FACTS')
        self.stop();_,before,db2,gate2=self.facts()
        if db2!=db or gate2!=gate or len(before['research_plan_native_funding'])!=1 or len(before['research_funding_accounts'])!=1:raise ProbeFailure('FACTS')
        self.result['phases']['stock_genesis']=True
        self.start();third=self.exercise(first['rid'])
        if not third['native_ready'] or third['identity_digest']!=first['identity_digest']:raise ProbeFailure('FACTS')
        self.stop();_,after,db3,gate3=self.facts()
        if after!=before or db3!=db or gate3!=gate or after['research_plan_native_funding'][0]['state']!='authorized':raise ProbeFailure('FACTS')
        self.result['phases']['stock_restart']=True;self.result['stock']['clean_exit_inferred']=True;self.result['financial']['normal_restart_unchanged']=True
        self.result['stock']['credential_invocation_changed']=self.invocations[-1][2]!=self.invocations[-2][2]
        self.write(WORK/'observer.json',canonical({'head':self.meta['head'],'deadline':self.budget.deadline-30}),self.uid,self.gid,0o400)
        self.install_unit(provider=True,observed=True);self.start();observed=self.exercise(first['rid'],True)
        if observed['identity_digest']!=first['identity_digest'] or not observed['native_ready']:raise ProbeFailure('FACTS')
        while not any(v['event']=='SLOT_BEFORE_GET' for v in self.events()):self.budget.require(new=True);time.sleep(.02)
        self.stop();final=next((v['values'] for v in self.events() if v['event']=='FINAL'),None)
        if final is None or set(final)!=set(self.result['instrumented']):raise ProbeFailure('OBSERVER')
        self.result['instrumented']=final
        if not all(final[k] for k in ('source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline')) or final['observer_failed']:raise ProbeFailure('OBSERVER')
        _,last,_,_=self.facts();run=last['research_plan_native_runs'];account=last['research_funding_accounts'][0]
        if len(run)!=1 or (run[0]['state'],run[0]['cost_state'])!=('closed','unreserved') or last['research_plan_native_funding'][0]['balance_claim'] is not None or any(account[k] for k in ('held','upper_booked','settled')):raise ProbeFailure('FACTS')
        self.result['financial'].update(pre_get_closed_unreserved=True,held=account['held'],upper_booked=account['upper_booked'],settled=account['settled'])
        self.result['phases']['instrumented']=True
    def cleanup(self):
        failed=self.uncertain;actors_retired=True
        if not self.paths and not self.children and not self.group_attempted and not self.user_attempted:
            self.result['resources']['cleanup_uncertain']=False
            return
        if self.unit_written:
            try:
                self.command(['/usr/bin/systemctl','stop',UNIT],clean=True,limit=25)
                if self.unit_info(clean=True)['MainPID']!='0':raise ProbeFailure('CLEANUP')
                cg=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
                if cg.exists() and cg.read_text().strip():raise ProbeFailure('CLEANUP')
                self.result['resources']['cgroup_empty']=True
            except BaseException:
                failed=True;actors_retired=False;self.result['resources']['forced']=True
                try:
                    self.command(['/usr/bin/systemctl','kill','--kill-whom=all','--signal=KILL',UNIT],clean=True,limit=2)
                    cg=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
                    actors_retired=self.unit_info(clean=True)['MainPID']=='0' and (not cg.exists() or not cg.read_text().strip())
                except BaseException:pass
        for p in list(self.children):
            record=self.attempts.get(id(p))
            if record is None or not record['complete']:
                failed=True;actors_retired=False
                continue
            try:
                if p.poll() is None:
                    try:
                        if p is self.server and p.stdin:p.stdin.close()
                        else:self._signal(p,signal.SIGTERM)
                        p.wait(timeout=self.budget.require(ceiling=3))
                    except BaseException:
                        failed=True;self.result['resources']['forced']=True
                        self._signal(p,signal.SIGKILL);p.wait(timeout=self.budget.require(ceiling=2))
                record['reaped']=p.poll() is not None
                # This is an existence query only. If the leader has gone but
                # a group remains, do not signal a group with unproved identity.
                try:os.killpg(p.pid,0)
                except ProcessLookupError:pass
                else:failed=True;actors_retired=False
                if not record['reaped']:actors_retired=False
                for stream in (p.stdin,p.stdout,p.stderr):
                    if stream is not None and not stream.closed:stream.close()
            except BaseException:
                failed=True;actors_retired=False
        try:
            if not actors_retired:raise ProbeFailure('CLEANUP')
            self._require_account_births()
            if self.unit_written:
                UNIT_FILE.unlink();self.paths.remove(UNIT_FILE);self.command(['/usr/bin/systemctl','daemon-reload'],clean=True,limit=3);self.unit_written=False
            self.result['resources']['unit_removed']=not UNIT_FILE.exists()
            if (Path('/run/credentials')/UNIT).exists():raise ProbeFailure('CLEANUP')
            self.result['resources']['credential_mount_gone']=True
            for top in (DEPOT,WORK,SECRETS,STATE,CACHE,GRANT_DIR):
                if top in self.paths:shutil.rmtree(top)
            self.result['resources']['directories_removed']=all(not p.exists() for p in (DEPOT,WORK,SECRETS,STATE,CACHE,GRANT_DIR))
            if not self.result['resources']['directories_removed']:raise ProbeFailure('CLEANUP')
            self._remove_accounts()
            self.result['resources']['user_removed']=True
        except BaseException:failed=True
        self.result['resources'].update(children_started=len(self.children),children_reaped=sum(self.attempts[id(p)]['reaped'] for p in self.children if id(p) in self.attempts),cleanup_uncertain=failed)
        if failed:self.result['outcome']='FAIL';self.result['reason']='CLEANUP'


def metadata_from_environment():
    names={'event':'GITHUB_EVENT_NAME','repository':'GITHUB_REPOSITORY','ref':'GITHUB_REF','head':'GITHUB_SHA','attempt':'GITHUB_RUN_ATTEMPT','hosted':'RUNNER_ENVIRONMENT','os':'RUNNER_OS','arch':'RUNNER_ARCH','run_id':'GITHUB_RUN_ID','created':'PROBE_PUSH_CREATED','deleted':'PROBE_PUSH_DELETED','before':'PROBE_PUSH_BEFORE','after':'PROBE_PUSH_AFTER'}
    return {k:os.environ.get(v,'') for k,v in names.items()}


def read_marker(meta):
    temp=Path(os.environ.get('RUNNER_TEMP',''))
    if not temp.is_absolute() or temp!=temp.resolve() or '..' in temp.parts:raise ProbeFailure('CLOCK')
    path=temp/MARKER_NAME;fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_uid!=temp.stat().st_uid or not 0<info.st_size<=4096:raise ProbeFailure('CLOCK')
        raw=os.read(fd,4097)
        if stat_key(os.fstat(fd))!=stat_key(info) or stat_key(path.lstat())!=stat_key(info):raise ProbeFailure('CLOCK')
    finally:os.close(fd)
    return temp,Budget(strict_json(raw,4096),meta,time.monotonic())


def main():
    meta=metadata_from_environment();validate_metadata(meta);temp,budget=read_marker(meta)
    if sys.argv[1:]==['budget']:budget.require(new=True,ceiling=1);return 0
    if sys.argv[1:]!=['run']:raise ProbeFailure('PRECHECK')
    controller=Controller(meta,budget,str(Path(sys.executable).resolve()))
    if (temp/RECEIPT_NAME).exists() or (temp/RECEIPT_NAME).is_symlink():raise ProbeFailure('PRECHECK')
    cleaning=False
    def stop(signum,frame):
        if not cleaning:raise ProbeFailure('CLOCK')
    prior={sig:signal.signal(sig,stop) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:controller.run();controller.result['outcome']='PASS';controller.result['reason']='OK'
    except ProbeFailure as error:controller.result['reason']=error.reason
    except BaseException:controller.result['reason']='INTERNAL'
    finally:
        cleaning=True
        controller.cleanup();controller.result['elapsed_ms']=int((time.monotonic()-budget.started)*1000)
        raw=validate_receipt(controller.result)
        fd=os.open(temp/RECEIPT_NAME,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
        try:
            os.fchmod(fd,0o600)
            owner=temp.stat();os.fchown(fd,owner.st_uid,owner.st_gid)
            if os.write(fd,raw)!=len(raw):raise ProbeFailure('CLEANUP')
        finally:os.close(fd)
        for sig,handler in prior.items():signal.signal(sig,handler)
    return 0 if controller.result['outcome']=='PASS' else 1


if __name__=='__main__':
    try:exit_code=main()
    except BaseException:print('NATIVE_PROBE_REFUSED',file=sys.stderr);exit_code=78
    raise SystemExit(exit_code)
