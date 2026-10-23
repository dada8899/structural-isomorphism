"""One fixed unprivileged companion; never calls a root/installer entry point.

The child receives the original seven-key stripped envelope, not event/run
authorization. The parent binds its own context to a strictly parsed result.
Every observation is new-run only; the consumed a11 effects stay UNKNOWN.
"""
from __future__ import annotations
import ast
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

SOURCE_HEAD='a11a354ec69bf65562a201cf58cf26ea45f795d3'
HELPER_SHA='332cae8e6ce61c8bdc9417b0cafd374fba96293b27f7f5769cf70d7efd07f316'
HELPER=Path(__file__).resolve().with_name('prepare_ci_chromium.py')
SELF=Path(__file__).resolve()
BRANCH='refs/heads/codex/structure-chromium-entry-diagnostic-20261023-attempt1'
SOURCE=Path('/etc/apt/sources.list.d/ubuntu.sources')
OLD_SOURCE_SHA='4508181e0dd5578c33d1247db48ab4847910b25da85e0789c8e7b3140d1fb289'
ENV_KEYS=('GITHUB_ACTIONS','RUNNER_ENVIRONMENT','RUNNER_OS','RUNNER_ARCH','RUNNER_TEMP','PATH','LANG')
CHECKS=('helper_code','env_scope','host_guard','sdk_profile','temporary_owner','request_shape','pwd_binding','source_metadata','source_input_profile','cleanup')
FIELDS=('Types','URIs','Suites','Components','Signed-By')
URI_CLASSES=('azure_http','azure_https','security_http','security_https','archive_http','archive_https','other')
FUNCTIONS={'require','sdk_profile','host_guard','mirror_source'}

class Closed(RuntimeError):pass

def need(value):
    if not value:raise Closed()

def strict_json(raw):
    def pairs(items):
        value={}
        for key,item in items:need(key not in value);value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=pairs)

def read_regular(path,cap):
    first=path.lstat();need(stat.S_ISREG(first.st_mode) and path==path.resolve() and first.st_nlink==1 and 0<=first.st_size<=cap)
    fd=os.open(path,os.O_RDONLY|os.O_NONBLOCK|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        need((os.fstat(fd).st_dev,os.fstat(fd).st_ino)==(first.st_dev,first.st_ino))
        parts=[];size=0;deadline=time.monotonic()+5
        while True:
            need(time.monotonic()<deadline);block=os.read(fd,min(65536,cap+1-size))
            if not block:break
            size+=len(block);need(size<=cap);parts.append(block)
        for current in (os.fstat(fd),path.lstat()):
            need((current.st_dev,current.st_ino,current.st_uid,current.st_gid,current.st_mode,current.st_nlink,current.st_size,current.st_mtime_ns,current.st_ctime_ns)
                 ==(first.st_dev,first.st_ino,first.st_uid,first.st_gid,first.st_mode,first.st_nlink,first.st_size,first.st_mtime_ns,first.st_ctime_ns))
        need(size==first.st_size);return b''.join(parts)
    finally:os.close(fd)

class Trace:
    def __init__(self):self.results=dict.fromkeys(CHECKS,'not_reached');self.active='helper_code';self.first=None;self.site=None
    def mark(self,name,okay):
        need(name in CHECKS);self.active=name;self.results[name]='pass' if okay else 'fail'
        if not okay and self.first is None:self.first=name
    def call(self,name,function):
        self.active=name
        try:value=function()
        except BaseException:
            if self.first is None:self.mark(self.active,False)
            raise Closed() from None
        self.mark(name,True);return value

def load_readonly(trace):
    raw=read_regular(HELPER,65536);need(hashlib.sha256(raw).hexdigest()==HELPER_SHA)
    tree=ast.parse(raw)
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS
           or isinstance(n,ast.ClassDef) and n.name=='Refused'
           or isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='KEYRING'
           or isinstance(n,ast.Import) and all(a.name in {'os','sys','importlib.metadata','json'} for a in n.names)
           or isinstance(n,ast.ImportFrom) and n.module=='pathlib' and [a.name for a in n.names]==['Path']]
    need({n.name for n in nodes if isinstance(n,ast.FunctionDef)}==FUNCTIONS)
    namespace={'__file__':str(HELPER)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(HELPER),'exec'),namespace)
    need(not any(name in namespace for name in ('prepare','root_worker','PinnedArchiveKeyring','SourceLease','subprocess','signal')))
    sites={}
    for node in nodes:
        if isinstance(node,ast.FunctionDef) and node.name!='require':
            calls=sorted([n for n in ast.walk(node) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require'],key=lambda n:n.lineno)
            for index,call in enumerate(calls,1):sites[(node.name,call.lineno)]={'function':node.name,'require_index':index}
    original_require=namespace['require'];original_sdk=namespace['sdk_profile']
    def traced_require(value):
        if not value:
            frame=inspect.currentframe().f_back
            try:trace.site=sites.get((frame.f_code.co_name,frame.f_lineno))
            finally:del frame
        return original_require(value)
    def sdk():
        trace.mark('host_guard',True)
        return trace.call('sdk_profile',original_sdk)
    namespace['require']=traced_require;namespace['sdk_profile']=sdk
    return namespace

def uri_class(values):
    if len(values)!=1:return 'other'
    for name,host in (('azure','azure.archive.ubuntu.com'),('security','security.ubuntu.com'),('archive','archive.ubuntu.com')):
        for scheme in ('http','https'):
            if values[0] in (scheme+'://'+host+'/ubuntu',scheme+'://'+host+'/ubuntu/'):
                return name+'_'+scheme
    return 'other'  # No unknown URL/host/userinfo is returned or hashed.

def source_summary(raw):
    try:text=raw.decode('utf-8');utf8=True
    except UnicodeError:text='';utf8=False
    rows=[];fields={};duplicates=set();unknown=0;continuation=False
    def finish():
        if not fields and not unknown and not continuation:return
        suites=fields.get('Suites',[])
        category='base_noble' if suites==['noble','noble-updates','noble-backports'] else 'security_noble' if suites==['noble-security'] else 'combined_noble' if suites==['noble','noble-updates','noble-backports','noble-security'] else 'other'
        rows.append({'uri_class':uri_class(fields.get('URIs',[])),'uri_single':len(fields.get('URIs',[]))==1,
            'field_present':[name in fields for name in FIELDS],'field_duplicate':[name in duplicates for name in FIELDS],
            'unknown_field_count':unknown,'continuation':continuation,'types_match':fields.get('Types')==['deb'],
            'components_match':len(fields.get('Components',[]))==4 and set(fields.get('Components',[]))=={'main','restricted','universe','multiverse'},
            'suites_class':category,'signed_by_match':fields.get('Signed-By')==['/usr/share/keyrings/ubuntu-archive-keyring.gpg']})
    for line in text.splitlines()+['']:
        if not line.strip():
            finish();fields={};duplicates=set();unknown=0;continuation=False;continue
        if line.startswith('#'):continue
        if line[0].isspace():continuation=True;continue
        if ':' not in line:unknown+=1;continue
        name,value=line.split(':',1)
        if name not in FIELDS:unknown+=1;continue
        if name in fields:duplicates.add(name)
        fields[name]=value.split()
    return {'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'matches_original_a11':len(raw)==2995 and hashlib.sha256(raw).hexdigest()==OLD_SOURCE_SHA,'utf8':utf8,
            'stanza_count':min(len(rows),3),'extra_stanzas':len(rows)>2,'stanzas':rows[:2]}

def child_observation():
    trace=Trace();temporary=None;source=None
    parent_fd=directory_fd=None;parent_birth=birth=None;base=None
    parent_open_attempted=creation_attempted=False
    def identity(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode)
    def parent_bound():
        need(parent_fd is not None and parent_birth is not None and base==base.resolve())
        need(identity(os.fstat(parent_fd))==parent_birth==identity(base.lstat()))
    def directory_bound():
        parent_bound()
        need(directory_fd is not None and birth is not None and temporary.parent==base)
        held=os.fstat(directory_fd);named=os.stat(temporary.name,dir_fd=parent_fd,follow_symlinks=False)
        need(identity(held)==birth==identity(named) and stat.S_ISDIR(held.st_mode)
             and held.st_uid==os.getuid() and stat.S_IMODE(held.st_mode)==0o700)
    try:
        frozen=trace.call('helper_code',lambda:load_readonly(trace))
        trace.call('env_scope',lambda:need(all(name not in os.environ for name in ('GITHUB_EVENT_NAME','GITHUB_REF','GITHUB_REPOSITORY','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_SHA','GITHUB_TOKEN','GITHUB_WORKSPACE','GITHUB_EVENT_PATH'))))
        trace.call('host_guard',frozen['host_guard'])
        def own_temp():
            nonlocal temporary,parent_fd,directory_fd,parent_birth,birth,base,parent_open_attempted,creation_attempted
            base=Path(os.environ['RUNNER_TEMP']);need(base.is_absolute() and base==base.resolve() and base.stat().st_uid==os.getuid())
            parent_open_attempted=True
            parent_fd=os.open(base,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            info=os.fstat(parent_fd);parent_birth=identity(info)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid());parent_bound()
            creation_attempted=True
            temporary=Path(tempfile.mkdtemp(prefix='structure-chromium-entry-child-',dir=base))
            need(temporary.parent==base)
            info=os.stat(temporary.name,dir_fd=parent_fd,follow_symlinks=False);birth=identity(info)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700)
            directory_fd=os.open(temporary.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd)
            directory_bound()
            return temporary
        temporary=trace.call('temporary_owner',own_temp)
        account=pwd.getpwuid(os.getuid())
        request={'uid':os.getuid(),'gid':os.getgid(),'python':sys.executable,'cache':str(Path(account.pw_dir)/'.cache/ms-playwright'),
                 'temporary':str(temporary),'deadline':time.monotonic()+100}
        trace.call('request_shape',lambda:need(json.loads(json.dumps(request))==request and type(request['uid']) is int and type(request['gid']) is int and type(request['deadline']) is float))
        trace.call('pwd_binding',lambda:need(account.pw_gid==os.getgid() and request['cache']==str(Path(account.pw_dir)/'.cache/ms-playwright')))
        raw=trace.call('source_metadata',lambda:read_regular(SOURCE,16384))
        source=source_summary(raw)
        trace.call('source_input_profile',lambda:frozen['mirror_source'](raw,effective=None))  # Discard rendered bytes.
    except BaseException:
        if trace.first is None:trace.mark(trace.active,False)
    finally:
        cleanup_ok=True
        try:
            need(not parent_open_attempted or parent_fd is not None)
            if creation_attempted:
                need(temporary is not None and birth is not None and directory_fd is not None)
                directory_bound()
                fd=os.open('entry-probe.json',os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory_fd)
                try:
                    first=os.fstat(fd);need(stat.S_ISREG(first.st_mode) and first.st_uid==os.getuid()
                        and first.st_nlink==1 and stat.S_IMODE(first.st_mode)==0o600)
                    raw=b'{"probe":"entry_only_not_authority"}';need(os.write(fd,raw)==len(raw));os.fsync(fd);need(os.pread(fd,len(raw)+1,0)==raw)
                    current=os.stat('entry-probe.json',dir_fd=directory_fd,follow_symlinks=False)
                    need((current.st_dev,current.st_ino)==(first.st_dev,first.st_ino) and current.st_nlink==1)
                    directory_bound();os.unlink('entry-probe.json',dir_fd=directory_fd)
                finally:os.close(fd)
                directory_bound();os.rmdir(temporary.name,dir_fd=parent_fd)
                # Retiring a same-named substitute cannot satisfy this held
                # birth descriptor proof. Never chase a renamed old path.
                need(os.fstat(directory_fd).st_nlink==0);parent_bound()
                try:os.stat(temporary.name,dir_fd=parent_fd,follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise Closed()
        except BaseException:cleanup_ok=False
        finally:
            for fd in (directory_fd,parent_fd):
                if fd is not None:
                    try:os.close(fd)
                    except BaseException:cleanup_ok=False
        trace.mark('cleanup',cleanup_ok)
    return {'schema':'helper-entry-child-v1','classification':'HELPER_ENTRY_READONLY_CHILD','source_head':SOURCE_HEAD,
            'status':'PASS' if trace.first is None else 'FAIL','first_failed_check_id':trace.first,'failed_site':trace.site,
            'checks':[{'check_id':name,'status':trace.results[name]} for name in CHECKS],'source':source,
            'sudo_invoked':False,'browser_installer_invoked':False,'setup_authorized':False}

def child_environment(env):
    result={name:env[name] for name in ENV_KEYS[:5]}
    result.update(PATH=str(Path(sys.executable).parent)+':/usr/local/bin:/usr/bin:/bin',LANG='C.UTF-8')
    return result

def companion(env):
    process=None;deadline=time.monotonic()+15
    result={'attempted':True,'actual_exit':None,'reaped':None,'group_absent':None,'deadline_exceeded':False}
    child=None
    try:
        process=subprocess.Popen([sys.executable,'-I','-B',str(SELF),'--child'],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=child_environment(env),start_new_session=True)
        raw,_=process.communicate(timeout=max(0,deadline-time.monotonic()-3))
        need(len(raw)<=8192)
        parsed=strict_json(raw)
        if valid_child(parsed):child=parsed
    except subprocess.TimeoutExpired:result['deadline_exceeded']=True
    except BaseException:pass  # Unknown construction/read never claims a clean non-start.
    finally:
        if process is not None:
            try:
                if process.poll() is None:os.killpg(process.pid,signal.SIGKILL)
                result['actual_exit']=process.wait(timeout=max(0,deadline-time.monotonic()));result['reaped']=True
                try:os.killpg(process.pid,0)
                except ProcessLookupError:result['group_absent']=True
                else:result['group_absent']=False
            except BaseException:pass
            finally:
                if process.stdout is not None:process.stdout.close()
        result['deadline_exceeded']=result['deadline_exceeded'] or time.monotonic()>=deadline
    return result,child

def parent_context(env):
    need(sys.platform=='linux' and os.uname().machine=='x86_64' and os.getuid()==os.geteuid()>0)
    need(env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted'
         and env.get('RUNNER_OS')=='Linux' and env.get('RUNNER_ARCH')=='X64')
    need(env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')==BRANCH
         and env.get('GITHUB_REPOSITORY')=='dada8899/structural-isomorphism' and env.get('GITHUB_RUN_ATTEMPT')=='1')
    run,sha=env.get('GITHUB_RUN_ID',''),env.get('GITHUB_SHA','')
    need(re.fullmatch('[1-9][0-9]{0,19}',run) is not None and re.fullmatch('[0-9a-f]{40}',sha) is not None)
    base=Path(env['RUNNER_TEMP']);need(base.is_absolute() and base==base.resolve() and base.stat().st_uid==os.getuid())
    root=base/('structure-chromium-entry-diagnostic-'+run+'-1');root.mkdir(mode=0o700)
    need(root.lstat().st_uid==os.getuid() and stat.S_IMODE(root.lstat().st_mode)==0o700)
    return root,run,sha

def parent_record(run,sha,process,child):
    failure=None
    if process['actual_exit'] not in (0,2) or process['reaped'] is not True or process['group_absent'] is not True or process['deadline_exceeded']:failure='child_process'
    elif child is None or (process['actual_exit'],child['status']) not in ((0,'PASS'),(2,'FAIL')):failure='child_record'
    elif child['status']=='FAIL':failure='child.'+child['first_failed_check_id']
    return {'schema':'helper-entry-diagnostic-v1','classification':'HELPER_ENTRY_DIAGNOSTIC_ONLY','source_head':SOURCE_HEAD,
            'event_sha':sha,'run_id':run,'same_stripped_envelope':True,'status':'PASS' if failure is None else 'FAIL',
            'first_failed_check_id':failure,'process':process,'child':child,'sudo_invoked':False,
            'browser_installer_invoked':False,'setup_authorized':False,'old_native_effects':'UNKNOWN'}

def number(value,low=0,high=2**64-1):return type(value) is int and low<=value<=high

def valid_source(value):
    if type(value) is not dict or set(value)!={'size','sha256','matches_original_a11','utf8','stanza_count','extra_stanzas','stanzas'}:return False
    if not number(value['size'],0,16384) or type(value['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value['sha256']) is None:return False
    if type(value['matches_original_a11']) is not bool or type(value['utf8']) is not bool or type(value['extra_stanzas']) is not bool:return False
    if value['matches_original_a11']!=(value['size']==2995 and value['sha256']==OLD_SOURCE_SHA):return False
    if not number(value['stanza_count'],0,3) or value['extra_stanzas']!=(value['stanza_count']==3):return False
    if type(value['stanzas']) is not list or len(value['stanzas'])!=min(value['stanza_count'],2):return False
    for row in value['stanzas']:
        if type(row) is not dict or set(row)!={'uri_class','uri_single','field_present','field_duplicate','unknown_field_count','continuation','types_match','components_match','suites_class','signed_by_match'}:return False
        if row['uri_class'] not in URI_CLASSES or row['suites_class'] not in ('base_noble','security_noble','combined_noble','other'):return False
        if any(type(row[k]) is not bool for k in ('uri_single','continuation','types_match','components_match','signed_by_match')):return False
        if not number(row['unknown_field_count'],0,16384):return False
        for key in ('field_present','field_duplicate'):
            if type(row[key]) is not list or len(row[key])!=5 or any(type(v) is not bool for v in row[key]):return False
    return True

def valid_child(value):
    keys={'schema','classification','source_head','status','first_failed_check_id','failed_site','checks','source','sudo_invoked','browser_installer_invoked','setup_authorized'}
    if type(value) is not dict or set(value)!=keys:return False
    if value['schema']!='helper-entry-child-v1' or value['classification']!='HELPER_ENTRY_READONLY_CHILD' or value['source_head']!=SOURCE_HEAD:return False
    if any(value[k] is not False for k in ('sudo_invoked','browser_installer_invoked','setup_authorized')):return False
    rows=value['checks']
    if type(rows) is not list or len(rows)!=len(CHECKS):return False
    for row,name in zip(rows,CHECKS):
        if type(row) is not dict or set(row)!={'check_id','status'} or row['check_id']!=name or row['status'] not in ('pass','fail','not_reached'):return False
    failed=[r['check_id'] for r in rows if r['status']=='fail']
    if value['first_failed_check_id']!=(failed[0] if failed else None) or value['status']!=('FAIL' if failed else 'PASS'):return False
    if not failed and any(r['status']!='pass' for r in rows):return False
    if failed:
        index=CHECKS.index(failed[0])
        if any(r['status']!='pass' for r in rows[:index]) or any(r['status']!='not_reached' for r in rows[index+1:-1]):return False
    site=value['failed_site']
    if site is not None:
        if type(site) is not dict or set(site)!={'function','require_index'} or site['function'] not in ('host_guard','sdk_profile','mirror_source') or not number(site['require_index'],1,32):return False
        expected={'host_guard':'host_guard','sdk_profile':'sdk_profile','mirror_source':'source_input_profile'}
        if value['first_failed_check_id']!=expected[site['function']]:return False
    if value['source'] is not None and not valid_source(value['source']):return False
    if rows[CHECKS.index('source_metadata')]['status']=='pass' and value['source'] is None:return False
    return True

def valid_parent(value):
    keys={'schema','classification','source_head','event_sha','run_id','same_stripped_envelope','status','first_failed_check_id','process','child','sudo_invoked','browser_installer_invoked','setup_authorized','old_native_effects'}
    if type(value) is not dict or set(value)!=keys:return False
    if value['schema']!='helper-entry-diagnostic-v1' or value['classification']!='HELPER_ENTRY_DIAGNOSTIC_ONLY' or value['source_head']!=SOURCE_HEAD:return False
    if type(value['run_id']) is not str or re.fullmatch('[1-9][0-9]{0,19}',value['run_id']) is None or type(value['event_sha']) is not str or re.fullmatch('[0-9a-f]{40}',value['event_sha']) is None:return False
    if value['same_stripped_envelope'] is not True or value['old_native_effects']!='UNKNOWN' or any(value[k] is not False for k in ('sudo_invoked','browser_installer_invoked','setup_authorized')):return False
    proc=value['process']
    if type(proc) is not dict or set(proc)!={'attempted','actual_exit','reaped','group_absent','deadline_exceeded'} or proc['attempted'] is not True or type(proc['deadline_exceeded']) is not bool:return False
    if proc['actual_exit'] is not None and not number(proc['actual_exit'],-255,255):return False
    if any(proc[k] is not None and type(proc[k]) is not bool for k in ('reaped','group_absent')):return False
    if proc['actual_exit'] is not None and proc['reaped'] is not True:return False
    if proc['group_absent'] is not None and proc['reaped'] is not True:return False
    if value['child'] is not None and not valid_child(value['child']):return False
    expected=parent_record(value['run_id'],value['event_sha'],proc,value['child'])
    return value==expected

def publish(root,value):
    need(valid_parent(value));raw=json.dumps(value,sort_keys=True,allow_nan=False).encode();need(len(raw)<=8192)
    path=root/'helper-entry-diagnostic.json';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    def identity(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink)
    try:
        first=os.fstat(fd);need(stat.S_ISREG(first.st_mode) and first.st_uid==os.getuid() and first.st_nlink==1 and stat.S_IMODE(first.st_mode)==0o600)
        need(os.write(fd,raw)==len(raw));os.fsync(fd)
        output=Path(os.environ['GITHUB_OUTPUT']);need(output==output.resolve() and output.is_absolute());before=output.lstat()
        out=os.open(output,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(out);need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and not info.st_mode&0o022)
            need(identity(info)==identity(before)==identity(output.lstat()) and info.st_size==before.st_size)
            need(identity(os.fstat(fd))==identity(first)==identity(path.lstat()) and os.fstat(fd).st_size==len(raw))
            checked=os.pread(fd,len(raw)+1,0);need(checked==raw and read_regular(path,8192)==raw and valid_parent(strict_json(checked)))
            flag=b'entry_diagnostic_safe=true\n';need(os.write(out,flag)==len(flag));os.fsync(out)
            final=os.fstat(out);need(identity(final)==identity(info)==identity(output.lstat()) and final.st_size==before.st_size+len(flag))
            return {'output_dev':info.st_dev,'output_ino':info.st_ino,'report_ino':first.st_ino,'fsynced':True}
        finally:os.close(out)
    finally:os.close(fd)

def main():
    try:
        if sys.argv[1:]==['--child']:
            value=child_observation();need(valid_child(value));raw=json.dumps(value,sort_keys=True,allow_nan=False);need(len(raw.encode())<=8192)
            print(raw);return 0 if value['status']=='PASS' else 2
        need(len(sys.argv)==1);root,run,sha=parent_context(os.environ)
        process,child=companion(os.environ);value=parent_record(run,sha,process,child);publish(root,value)
        return 0 if value['status']=='PASS' else 2
    except BaseException:return 2

if __name__=='__main__':raise SystemExit(main())
