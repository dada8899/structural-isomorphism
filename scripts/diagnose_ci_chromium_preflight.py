"""Bounded readonly observations, never an installer or an old-run diagnosis.

Only checksum-verified readonly AST definitions from21d are loaded. No frozen
context, setup CLI, subprocess import, claim or installation function is loaded.
The only writes are this run's private probe/report and the fixed safe output.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from types import SimpleNamespace

SOURCE_HEAD = '21dbe13dcf6aa835d549b83b994fbcf04acbed47'
SOURCE_SHA = 'ab98c861e0681e1549c3d47fe559c93a7d68461900d19bf4e57480d6cb577445'
SOURCE_FILE = Path(__file__).resolve().with_name('verify_ci_chromium_setup.py')
BRANCH = 'refs/heads/codex/structure-chromium-preflight-diagnostic-20261023-attempt2'
SCHEMA = 'setup-preflight-diagnostic-v1'
CHECKS = ('context_complete','source_code','helper_metadata','source_metadata','keyring_metadata',
          'snapshot_modes','sdk_python','sdk_lookup','sdk_pins','sdk_registry','write_probe','public_persist')
FUNCTIONS = {'need','strict_json','metadata','snapshot','helper_metadata','sdk'}
CONSTANTS = {'HELPER_SHA','HELPER','SYSTEM_FILES','VERSION','PINS'}
IMPORTS = {'hashlib','importlib.metadata','json','os','stat','sys','time'}
PACKAGES = ('pytest','playwright','pytest-playwright','fastapi','pydantic','starlette',
            'uvicorn','PyJWT','slowapi','structlog')
BROWSERS = ('chromium','chromium-headless-shell')
META_KEYS = {'kind','dev','ino','uid','gid','mode','nlink','size','sha256','within_cap','stable','expected_sha_match'}


class Closed(RuntimeError):
    pass


def need(value):
    if not value:
        raise Closed()


def integers(info):
    return {'dev':info.st_dev,'ino':info.st_ino,'uid':info.st_uid,'gid':info.st_gid,
            'mode':stat.S_IMODE(info.st_mode),'nlink':info.st_nlink,'size':info.st_size}


def node(path, cap):
    value = dict.fromkeys(META_KEYS)
    try:
        info = path.lstat()
    except FileNotFoundError:
        value['kind'] = 'missing'
        return value
    except OSError:
        value['kind'] = 'unavailable'
        return value
    value.update(integers(info), within_cap=0 <= info.st_size <= cap)
    value['kind'] = 'regular' if stat.S_ISREG(info.st_mode) else 'symlink' if stat.S_ISLNK(info.st_mode) else 'directory' if stat.S_ISDIR(info.st_mode) else 'other'
    return value


def read_regular(path, cap):
    """No body/target read for a symlink or nonregular input; no raw export."""
    first = path.lstat()
    need(stat.S_ISREG(first.st_mode) and path.is_absolute() and path == path.resolve() and 0 <= first.st_size <= cap)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        need(integers(info) == integers(first))
        parts, size, deadline = [], 0, time.monotonic()+5
        while True:
            need(time.monotonic() < deadline)
            raw = os.read(fd, min(65536, cap+1-size))
            if not raw:
                break
            size += len(raw);need(size <= cap);parts.append(raw)
        final = os.fstat(fd);last = path.lstat()
        for current in (final,last):
            need(integers(current) == integers(first) and
                 (current.st_mtime_ns,current.st_ctime_ns) == (first.st_mtime_ns,first.st_ctime_ns))
        need(size == first.st_size)
        return b''.join(parts)
    finally:
        os.close(fd)


def observe(path, cap, expected=None):
    result = node(path,cap)
    if result['kind'] == 'regular' and result['within_cap']:
        try:
            raw = read_regular(path,cap)
            result.update(sha256=hashlib.sha256(raw).hexdigest(),stable=True)
            if expected is not None:
                result['expected_sha_match'] = result['sha256'] == expected
        except BaseException:
            result['stable'] = False
    return result


class Trace:
    def __init__(self):
        self.results = dict.fromkeys(CHECKS,'not_reached')
        self.active, self.first = 'context_complete', None
        self.packages = {name:{'package_id':name,'status':'not_reached','pin_match':None} for name in PACKAGES}
        self.failed_input = self.registry = None
        self.registry_raw = None
        self.sdk_need_lines = {}

    def mark(self, name, okay):
        need(name in CHECKS)
        self.active = name
        self.results[name] = 'pass' if okay else 'fail'
        if not okay and self.first is None:
            self.first = name

    def call(self, name, function):
        self.active = name
        try:
            result = function()
        except BaseException:
            self.mark(self.active,False)
            raise Closed() from None
        self.mark(name,True)
        return result


def load_readonly(trace):
    raw = read_regular(SOURCE_FILE,65536)
    need(hashlib.sha256(raw).hexdigest() == SOURCE_SHA)
    tree = ast.parse(raw)
    nodes = [n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1
             and isinstance(n.targets[0],ast.Name) and n.targets[0].id in CONSTANTS
             or isinstance(n,ast.ClassDef) and n.name=='Unavailable'
             or isinstance(n,ast.FunctionDef) and n.name in FUNCTIONS
             or isinstance(n,ast.Import) and all(alias.name in IMPORTS for alias in n.names)
             or isinstance(n,ast.ImportFrom) and n.module=='pathlib' and [a.name for a in n.names]==['Path']]
    need({n.name for n in nodes if isinstance(n,ast.FunctionDef)} == FUNCTIONS)
    namespace = {'__file__':str(SOURCE_FILE),'os':os,'stat':stat,'time':time,'hashlib':hashlib,
                 'Path':Path,'sys':sys,'json':json,'importlib':SimpleNamespace(metadata=importlib.metadata)}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE_FILE),'exec'),namespace)
    need(not any(name in namespace for name in ('subprocess','context','before','install','after','prepare','root_worker')))
    sdk_ast = next(n for n in nodes if isinstance(n,ast.FunctionDef) and n.name=='sdk')
    calls = sorted([n for n in ast.walk(sdk_ast) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='need'],key=lambda n:n.lineno)
    need(len(calls) == 5)
    trace.sdk_need_lines = dict(zip([n.lineno for n in calls],('sdk_python','sdk_pins','sdk_registry','sdk_registry','sdk_registry')))
    original_need = namespace['need']
    def traced_need(value):
        frame = inspect.currentframe().f_back
        try:
            check = trace.sdk_need_lines.get(frame.f_lineno,trace.active) if frame.f_code.co_name=='sdk' else trace.active
        finally:
            del frame
        trace.mark(check,bool(value))
        return original_need(value)
    namespace['need'] = traced_need
    return namespace


def trace_sdk(frozen, trace):
    original_version, original_distribution = importlib.metadata.version, importlib.metadata.distribution
    order = []
    def version(name):
        need(name in PACKAGES and name not in order)
        trace.active = 'sdk_lookup';row = trace.packages[name]
        try:
            result = original_version(name)
        except BaseException:
            row['status']='fail';trace.mark('sdk_lookup',False)
            raise Closed() from None
        row.update(status='pass',pin_match=result == frozen['PINS'][name]);order.append(name)
        if len(order)==len(PACKAGES):trace.mark('sdk_lookup',True)
        return result
    def distribution(name):
        need(name=='playwright');trace.active='sdk_registry'
        return original_distribution(name)
    class Registry:
        def __init__(self,path):
            self.path=Path(path)
            need(self.path.parts[-4:]==('playwright','driver','package','browsers.json'))
        def stat(self):
            trace.registry={'size':None,'sha256':None,
                            'browsers':[{'browser_id':name,'revision':None,'version':None,'override_present':None} for name in BROWSERS]}
            info=self.path.lstat()
            trace.registry['size']=info.st_size
            need(stat.S_ISREG(info.st_mode) and self.path==self.path.resolve())
            return info
        def read_bytes(self):
            raw=read_regular(self.path,16384);trace.registry_raw=raw
            return raw
    frozen['importlib'] = SimpleNamespace(metadata=SimpleNamespace(version=version,distribution=distribution))
    frozen['Path'] = Registry
    trace.active='sdk_python'
    try:
        frozen['sdk']()
    except BaseException:
        trace.mark(trace.active,False)
        raise Closed() from None
    finally:
        if trace.registry_raw is not None:
            trace.registry={'size':len(trace.registry_raw),'sha256':hashlib.sha256(trace.registry_raw).hexdigest(),
                            'browsers':[{'browser_id':name,'revision':None,'version':None,'override_present':None} for name in BROWSERS]}
            try:
                data=json.loads(trace.registry_raw)
                for row in trace.registry['browsers']:
                    candidates=[v for v in data['browsers'] if type(v) is dict and v.get('name')==row['browser_id']]
                    if len(candidates)!=1:continue
                    candidate=candidates[0];revision=candidate.get('revision');version_value=candidate.get('browserVersion')
                    if type(revision) is str and re.fullmatch('[0-9]{1,6}',revision):row['revision']=revision
                    if type(version_value) is str and re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){3}',version_value):row['version']=version_value
                    row['override_present']=bool(candidate.get('revisionOverrides'))
            except BaseException:
                pass


def write_probe(root):
    path=root/'write-probe.json';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    okay=False
    try:
        first=os.fstat(fd);need(stat.S_ISREG(first.st_mode) and first.st_uid==os.getuid() and first.st_nlink==1 and stat.S_IMODE(first.st_mode)==0o600)
        raw=b'{"probe":"diagnostic_only"}'
        need(os.write(fd,raw)==len(raw));os.fsync(fd)
        need(os.pread(fd,len(raw)+1,0)==raw)
        current=path.lstat();need((current.st_dev,current.st_ino)==(first.st_dev,first.st_ino))
        okay=True
    finally:
        os.close(fd)
        if okay:path.unlink()


def run_checks(frozen, trace, root):
    targets=(('helper_metadata','helper',frozen['HELPER'],128*1024,lambda:frozen['helper_metadata']()),
             ('source_metadata','source',frozen['SYSTEM_FILES']['source'][0],16384,
              lambda:frozen['metadata'](*frozen['SYSTEM_FILES']['source'],0)),
             ('keyring_metadata','keyring',frozen['SYSTEM_FILES']['keyring'][0],1024*1024,
              lambda:frozen['metadata'](*frozen['SYSTEM_FILES']['keyring'],0)))
    result={}
    for check,path_id,path,cap,function in targets:
        try:
            # Refuse unsafe inputs before any original function can read a body.
            trace.active=check;info=path.lstat();need(stat.S_ISREG(info.st_mode) and path==path.resolve())
            result[path_id]=trace.call(check,function)
        except BaseException:
            trace.mark(check,False)
            trace.failed_input={'path_id':path_id,'metadata':observe(path,cap,frozen['HELPER_SHA'] if path_id=='helper' else None)}
            return
    try:
        trace.call('snapshot_modes',lambda:frozen['need'](all(result[k]['mode']==0o644 for k in ('source','keyring'))))
        trace_sdk(frozen,trace)
        trace.call('write_probe',lambda:write_probe(root))
    except BaseException:
        if trace.active == 'snapshot_modes':
            role=next(k for k in ('source','keyring') if result[k]['mode']!=0o644)
            trace.failed_input={'path_id':role,'metadata':observe(frozen['SYSTEM_FILES'][role][0],frozen['SYSTEM_FILES'][role][1])}
        return


def context(env):
    predicates={'native_host':sys.platform=='linux' and os.uname().machine=='x86_64' and os.getuid()==os.geteuid()>0,
                'github_hosted':env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted',
                'platform_vars':env.get('RUNNER_OS')=='Linux' and env.get('RUNNER_ARCH')=='X64',
                'event':env.get('GITHUB_EVENT_NAME')=='push','ref':env.get('GITHUB_REF')==BRANCH,
                'repository':env.get('GITHUB_REPOSITORY')=='dada8899/structural-isomorphism','attempt':env.get('GITHUB_RUN_ATTEMPT')=='1'}
    need(predicates['native_host'] and predicates['github_hosted'])
    run=env.get('GITHUB_RUN_ID','');sha=env.get('GITHUB_SHA','')
    need(re.fullmatch('[1-9][0-9]{0,19}',run) is not None and re.fullmatch('[0-9a-f]{40}',sha) is not None)
    base=Path(env['RUNNER_TEMP']);need(base.is_absolute() and base==base.resolve() and base.stat().st_uid==os.getuid())
    root=base/('structure-chromium-preflight-diagnostic-'+run+'-1');root.mkdir(mode=0o700)
    info=root.lstat();need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700)
    return root,run,sha,predicates,integers(info)


def record(trace,run,sha,predicates,root_stat):
    return {'schema':SCHEMA,'classification':'PREFLIGHT_DIAGNOSTIC_ONLY','source_head':SOURCE_HEAD,
            'event_sha':sha,'run_id':run,'helper_invoked':False,'setup_authorized':False,
            'new_runner_observation_only':True,'status':'DIAGNOSTIC_FAIL' if trace.first else 'DIAGNOSTIC_PASS',
            'first_failed_check_id':trace.first,'checks':[{'check_id':name,'status':trace.results[name]} for name in CHECKS],
            'context':{'predicates':predicates,'uid':os.getuid(),'root_stat':root_stat},
            'packages':list(trace.packages.values()),'failed_input':trace.failed_input,'registry':trace.registry}


def natural(value, cap=2**64-1):
    return type(value) is int and 0 <= value <= cap


def valid_record(value):
    keys={'schema','classification','source_head','event_sha','run_id','helper_invoked','setup_authorized',
          'new_runner_observation_only','status','first_failed_check_id','checks','context','packages','failed_input','registry'}
    if type(value) is not dict or set(value)!=keys:return False
    if value['schema']!=SCHEMA or value['classification']!='PREFLIGHT_DIAGNOSTIC_ONLY' or value['source_head']!=SOURCE_HEAD:return False
    if value['helper_invoked'] is not False or value['setup_authorized'] is not False or value['new_runner_observation_only'] is not True:return False
    if type(value['event_sha']) is not str or re.fullmatch('[0-9a-f]{40}',value['event_sha']) is None:return False
    if type(value['run_id']) is not str or re.fullmatch('[1-9][0-9]{0,19}',value['run_id']) is None:return False
    checks=value['checks']
    if type(checks) is not list or len(checks)!=len(CHECKS):return False
    for row,name in zip(checks,CHECKS):
        if type(row) is not dict or set(row)!={'check_id','status'} or row['check_id']!=name or row['status'] not in ('pass','fail','not_reached'):return False
    failed=[row['check_id'] for row in checks if row['status']=='fail']
    if value['first_failed_check_id']!=(failed[0] if failed else None):return False
    if value['status']!=('DIAGNOSTIC_FAIL' if failed else 'DIAGNOSTIC_PASS'):return False
    if not failed and any(row['status']!='pass' for row in checks):return False
    if failed:
        first=CHECKS.index(failed[0])
        if any(row['status']!='pass' for row in checks[:first]):return False
        if any(row['status']!='not_reached' for row in checks[first+1:-1]):return False
    ctx=value['context'];predicate_keys={'native_host','github_hosted','platform_vars','event','ref','repository','attempt'}
    if type(ctx) is not dict or set(ctx)!={'predicates','uid','root_stat'} or not natural(ctx['uid']):return False
    if type(ctx['predicates']) is not dict or set(ctx['predicates'])!=predicate_keys or any(type(v) is not bool for v in ctx['predicates'].values()):return False
    if (checks[0]['status']=='pass') != all(ctx['predicates'].values()):return False
    info=ctx['root_stat']
    if type(info) is not dict or set(info)!={'dev','ino','uid','gid','mode','nlink','size'} or any(not natural(v) for v in info.values()):return False
    if info['uid']!=ctx['uid'] or info['mode']!=0o700:return False
    rows=value['packages']
    if type(rows) is not list or len(rows)!=len(PACKAGES):return False
    for row,name in zip(rows,PACKAGES):
        if type(row) is not dict or set(row)!={'package_id','status','pin_match'} or row['package_id']!=name or row['status'] not in ('pass','fail','not_reached'):return False
        if row['pin_match'] is not None and type(row['pin_match']) is not bool:return False
        if row['status']!='pass' and row['pin_match'] is not None:return False
        if row['status']=='pass' and type(row['pin_match']) is not bool:return False
    lookup=checks[CHECKS.index('sdk_lookup')]['status']
    if lookup=='not_reached' and any(row['status']!='not_reached' for row in rows):return False
    if lookup=='pass' and any(row['status']!='pass' for row in rows):return False
    if checks[CHECKS.index('sdk_pins')]['status']=='pass' and any(row['pin_match'] is not True for row in rows):return False
    item=value['failed_input']
    if item is not None:
        if type(item) is not dict or set(item)!={'path_id','metadata'} or item['path_id'] not in ('helper','source','keyring'):return False
        if value['first_failed_check_id'] not in ('helper_metadata','source_metadata','keyring_metadata','snapshot_modes'):return False
        expected={'helper_metadata':('helper',),'source_metadata':('source',),'keyring_metadata':('keyring',),'snapshot_modes':('source','keyring')}
        if item['path_id'] not in expected[value['first_failed_check_id']]:return False
        role=item['path_id']
        item=item['metadata']
        if type(item) is not dict or set(item)!=META_KEYS or item['kind'] not in ('regular','symlink','directory','other','missing','unavailable'):return False
        for key in ('dev','ino','uid','gid','mode','nlink','size'):
            if item[key] is not None and not natural(item[key]):return False
        for key in ('within_cap','stable','expected_sha_match'):
            if item[key] is not None and type(item[key]) is not bool:return False
        if item['sha256'] is not None and (type(item['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',item['sha256']) is None):return False
        if item['kind']!='regular' and any(item[k] is not None for k in ('sha256','stable','expected_sha_match')):return False
        if (item['sha256'] is not None) != (item['stable'] is True):return False
        if role!='helper' and item['expected_sha_match'] is not None:return False
    registry=value['registry']
    if registry is not None:
        if type(registry) is not dict or set(registry)!={'size','sha256','browsers'}:return False
        if registry['size'] is not None and not natural(registry['size']):return False
        if registry['sha256'] is not None and (type(registry['sha256']) is not str or re.fullmatch('[0-9a-f]{64}',registry['sha256']) is None or not natural(registry['size'],16384)):return False
        if type(registry['browsers']) is not list or len(registry['browsers'])!=2:return False
        for row,name in zip(registry['browsers'],BROWSERS):
            if type(row) is not dict or set(row)!={'browser_id','revision','version','override_present'} or row['browser_id']!=name:return False
            if row['revision'] is not None and (type(row['revision']) is not str or re.fullmatch('[0-9]{1,6}',row['revision']) is None):return False
            if row['version'] is not None and (type(row['version']) is not str or re.fullmatch(r'[0-9]{1,4}(?:\.[0-9]{1,4}){3}',row['version']) is None):return False
            if row['override_present'] is not None and type(row['override_present']) is not bool:return False
    if checks[CHECKS.index('sdk_registry')]['status']=='pass':
        if registry is None or registry['sha256'] is None:return False
        if any(row['revision']!='1217' or row['version']!='147.0.7727.15' or row['override_present'] is not False for row in registry['browsers']):return False
    return True


def publish(root, value):
    need(valid_record(value))
    raw=json.dumps(value,sort_keys=True,allow_nan=False).encode();need(len(raw)<=8192)
    path=root/'preflight-diagnostic.json';fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    def identity(info):
        return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink)
    try:
        info=os.fstat(fd);need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600)
        need(os.write(fd,raw)==len(raw));os.fsync(fd);need(os.pread(fd,len(raw)+1,0)==raw)
        current=path.lstat();need((current.st_dev,current.st_ino)==(info.st_dev,info.st_ino) and os.fstat(fd).st_nlink==1)
        need(read_regular(path,8192)==raw)
        output=Path(os.environ['GITHUB_OUTPUT']);need(output.is_absolute() and output==output.resolve())
        output_before=output.lstat()
        out_fd=os.open(output,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            out_info=os.fstat(out_fd)
            need(stat.S_ISREG(out_info.st_mode) and out_info.st_uid==os.getuid() and out_info.st_nlink==1 and not out_info.st_mode&0o022)
            need(identity(out_info)==identity(output_before)==identity(output.lstat()) and out_info.st_size==output_before.st_size)
            # Bind the held report and its name *after* the real output open.
            # This is an adjacent single-writer check, not isolation from an
            # adversary changing every anchor under the same UID afterwards.
            held=os.fstat(fd);named=path.lstat()
            need(identity(held)==identity(info)==identity(named) and held.st_size==named.st_size==len(raw))
            checked=os.pread(fd,len(raw)+1,0)
            need(checked==raw and read_regular(path,8192)==checked and valid_record(json.loads(checked)))
            need(identity(os.fstat(fd))==identity(info)==identity(path.lstat()))
            flag=b'diagnostic_safe=true\n';need(os.write(out_fd,flag)==len(flag));os.fsync(out_fd)
            output_after=os.fstat(out_fd)
            need(identity(output_after)==identity(out_info)==identity(output.lstat()) and output_after.st_size==out_info.st_size+len(flag))
            return {'report_dev':info.st_dev,'report_ino':info.st_ino,'report_sha256':hashlib.sha256(checked).hexdigest(),
                    'output_dev':out_info.st_dev,'output_ino':out_info.st_ino,'output_uid':out_info.st_uid,
                    'output_mode':stat.S_IMODE(out_info.st_mode),'offset':out_info.st_size,'bytes':len(flag),'fsynced':True}
        finally:os.close(out_fd)
    finally:os.close(fd)


def main():
    trace=Trace()
    try:
        need(len(sys.argv)==1)
        root,run,sha,predicates,root_stat=context(os.environ)
        trace.mark('context_complete',all(predicates.values()))
        if trace.first is None:
            frozen=trace.call('source_code',lambda:load_readonly(trace))
            run_checks(frozen,trace,root)
    except BaseException:
        trace.mark(trace.active,False)
        if 'root' not in locals():return 2
    trace.mark('public_persist',True)  # Safe output is signed only after actual fsync/readback.
    try:publish(root,record(trace,run,sha,predicates,root_stat))
    except BaseException:return 2
    return 0 if trace.first is None else 2


if __name__=='__main__':
    raise SystemExit(main())
