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
import socket
import struct
import stat
import subprocess
import sys
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
BRANCH='refs/heads/codex/structure-native-linux-lifecycle-attempt8-20261025'
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
FAILURE_PHASES=('preflight','prepare',*PHASES,'cleanup','unknown')
FAILURE_OPERATIONS=('unknown','platform','sdk','target_absence','account_absence','checkout','command_start','command_wait','command_result','command_output','process_birth','process_identity','process_cleanup','process_group','group_create','user_create','group_record','user_record','account_record','account_cleanup','directory_create','directory_owner','directory_mode','file_open','file_write','file_close','mirror_entry','mirror_mode','mirror_link','mirror_open','mirror_metadata','mirror_read','mirror_identity','mirror_size','mirror_hash','mirror_catalog','mirror_close','secret_prepare','certificate_metadata','bootstrap','unit_install','unit_start','unit_info','unit_isolation','credential_metadata','helper_start','helper_ready','exercise','stop','facts','facts_close','grant','events','unit_cleanup','directory_cleanup','cleanup_summary','ready_diagnostics')
FAILURE_COMMANDS=('unknown','systemd_version','git_head','git_status','git_tree','git_listing','group_add','user_add','certificate','bootstrap','code_export','unit_reload','unit_show','unit_start','unit_stop','unit_kill','user_delete','group_delete','helper')
FAILURE_EXCEPTIONS=('PROBE_FAILURE','OS_ERROR','TIMEOUT','VALUE_ERROR','TYPE_ERROR','KEY_ERROR','ASSERTION_ERROR','OTHER')
ACCOUNT_CHECKS=('read','record_count','shape','id_format','id_match','id_unique','fields','birth','absence','record_changed')
TOOLS=('/usr/bin/systemctl','/usr/bin/nsenter','/usr/bin/setpriv','/usr/bin/openssl','/usr/sbin/useradd','/usr/sbin/userdel','/usr/sbin/groupadd','/usr/sbin/groupdel')
SDKS={'pytest':'9.0.3','playwright':'1.59.0','pytest-playwright':'0.7.2','fastapi':'0.135.0','pydantic':'2.7.4','starlette':'1.3.1','uvicorn':'0.27.1','PyJWT':'2.15.1','slowapi':'0.1.9','structlog':'25.5.0'}
IMPORT_SDKS={'httpx':'0.27.2','numpy':'1.26.3'}
GIT=('git','-c','safe.directory='+str(ROOT),'-c','filter.lfs.process=','-c','filter.lfs.clean=cat','-c','filter.lfs.smudge=cat','-c','filter.lfs.required=false')


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
    if type(relative) is not str or Path(relative).is_absolute() or '..' in Path(relative).parts:raise ProbeFailure('SOURCE')
    # Environment paths are excluded from the mirror before any content IO.
    if any(part.startswith('.env') for part in Path(relative).parts):return False
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
    return {'protocol':'native-linux-lifecycle-probe-v5','first_failure':None,'credential_metadata':[],'startup_diagnostics':{phase:None for phase in PHASES},'diagnostic_resources':empty_diagnostic_resources(),'head':head,'tree':None,'code_digest':None,'outcome':'FAIL','reason':'PRECHECK','elapsed_ms':0,
        'phases':{k:False for k in PHASES},'stock':{'typed_receipts':None,'creator_connections':None,'creator_fds':None,'clean_exit_inferred':False,'credential_invocation_changed':None},
        'instrumented':{'source_closed':None,'native_closed':None,'proof_taken':None,'component_woken':None,'component_ms':None,'same_deadline_ref':None,'within_main_deadline':None,'main_stop_to_closed_ms':None,'connections_born':None,'connections_creator_closed':None,'connections_property_closed':None,'fds_born':None,'fds_creator_closed':None,'fds_property_closed':None,'observer_failed':None},
        'financial':{'initial_empty':False,'normal_restart_unchanged':False,'pre_get_closed_unreserved':False,'held':None,'upper_booked':None,'settled':None,'native_unknown_held_verified':False},
        'resources':{'children_started':0,'children_reaped':0,'unit_invocations':0,'unit_exited':0,'cgroup_empty':False,'credential_mount_gone':False,'unit_removed':False,'directories_removed':False,'user_removed':False,'cleanup_uncertain':True,'forced':False},
        'scope':{'stock':'systemd-entry-finite-inference','instrumented':'original-entry-runpy-observation','counts':'instrumented-observed-subset-only','component':'active-slot-stopfd-select-only','provider':'not_run','public_source':'not_run'}}


METADATA_SLOTS=('DIRECTORY',*IDS,PROVIDER_ID)
METADATA_CHECKS=('DIR_OWNER','FILE_OWNER','MODE','ACL_SHAPE','ACL_MASK','DEFAULT_ACL','LINK','MOUNT_RO','MOUNT_ID','IDENTITY','CONSUMER','NAMESPACE','IO','PROCESS_GONE')
METADATA_DECISIONS=('ROOT_ACL_RO','SERVICE_OWNER_RO','REJECT','UNKNOWN')


def empty_metadata(phase):
    return {'phase':phase,'location':'controller_pre_main_check','formal_pre_read':None,'native_pre_read':None,
        'consumer':{'uid':None,'gid':None,'identity_matches':None,'instance_stable':None,'namespace_stable':None,'initial_maps':None},
        'objects':[],'decision':'UNKNOWN','check':None}


def empty_metadata_object(slot):
    return {'slot':slot,'kind':None,'uid':None,'gid':None,'mode':None,'nlink':None,'held_named_same':None,
        'access':None,'default':None,'readonly':None,'mount_matches':None,'decision':'UNKNOWN','check':None,'legacy_owner_only':None}


def _receipt_metadata_policy():
    # Decoder-side source is the fixed checkout, not a credential path or a
    # pre-injected module. Fresh functions use the interpreter's builtin dict.
    import builtins,types
    path=ROOT/'web/backend/systemd_credential_metadata.py'
    try:
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            before=os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1 or not 0<before.st_size<=65536:raise ProbeFailure('PRECHECK')
            raw=os.read(fd,65537)
            if len(raw)!=before.st_size or stat_key(os.fstat(fd))!=stat_key(before) or stat_key(path.lstat())!=stat_key(before):raise ProbeFailure('PRECHECK')
        finally:os.close(fd)
        trusted_builtins=vars(builtins)
        namespace={'__name__':'systemd_credential_metadata','__file__':str(path),'__builtins__':trusted_builtins}
        exec(compile(raw,str(path),'exec',dont_inherit=True),namespace)
        predicate=namespace.get('validate_projection')
        if type(predicate) is not types.FunctionType or predicate.__globals__ is not namespace or predicate.__builtins__ is not trusted_builtins or predicate.__closure__ is not None:raise ProbeFailure('PRECHECK')
        return predicate
    except Exception:raise ProbeFailure('PRECHECK') from None


def _public_projection(item):
    projection={key:item[key] for key in ('kind','uid','gid','mode','nlink','readonly','mount_matches')}
    for key in ('access','default'):
        value=item[key]
        if value is None:raise ProbeFailure('PRECHECK')
        projection[key]=(value['state'],tuple(tuple(row) for row in value['entries']),value['count'])
    return projection


def validate_credential_metadata(values):
    if type(values) is not list or len(values)>4:raise ProbeFailure('PRECHECK')
    phases=[];policy=None
    for record in values:
        if type(record) is not dict or set(record)!=set(empty_metadata('stock_base')):raise ProbeFailure('PRECHECK')
        if record['phase'] not in PHASES or record['phase'] in phases or record['location']!='controller_pre_main_check' or record['formal_pre_read'] is not None or record['native_pre_read'] is not None:raise ProbeFailure('PRECHECK')
        phases.append(record['phase'])
        if record['decision'] not in METADATA_DECISIONS or record['check'] is not None and record['check'] not in METADATA_CHECKS:raise ProbeFailure('PRECHECK')
        consumer=record['consumer']
        if type(consumer) is not dict or set(consumer)!=set(empty_metadata('stock_base')['consumer']):raise ProbeFailure('PRECHECK')
        for key,item in consumer.items():
            if key in ('uid','gid'):
                if item is not None and (type(item) is not int or not 0<=item<4294967295):raise ProbeFailure('PRECHECK')
            elif item is not None and type(item) is not bool:raise ProbeFailure('PRECHECK')
        objects=record['objects'];slots=[]
        if type(objects) is not list or len(objects)>7:raise ProbeFailure('PRECHECK')
        for item in objects:
            if type(item) is not dict or set(item)!=set(empty_metadata_object('DIRECTORY')):raise ProbeFailure('PRECHECK')
            if item['slot'] not in METADATA_SLOTS or item['slot'] in slots:raise ProbeFailure('PRECHECK')
            slots.append(item['slot'])
            if item['kind'] is not None and item['kind'] not in ('directory','regular','other'):raise ProbeFailure('PRECHECK')
            for key,maximum in (('uid',4294967294),('gid',4294967294),('mode',4095),('nlink',4294967295)):
                if item[key] is not None and (type(item[key]) is not int or not 0<=item[key]<=maximum):raise ProbeFailure('PRECHECK')
            for key in ('held_named_same','readonly','mount_matches','legacy_owner_only'):
                if item[key] is not None and type(item[key]) is not bool:raise ProbeFailure('PRECHECK')
            if item['decision'] not in METADATA_DECISIONS or item['check'] is not None and item['check'] not in METADATA_CHECKS:raise ProbeFailure('PRECHECK')
            for key in ('access','default'):
                acl=item[key]
                if acl is None:continue
                if type(acl) is not dict or set(acl)!= {'state','entries','count'} or acl['state'] not in ('ABSENT','PRESENT','UNSUPPORTED','IO','INVALID','TOO_MANY') or type(acl['entries']) is not list or len(acl['entries'])>5:raise ProbeFailure('PRECHECK')
                if acl['count'] is not None and (type(acl['count']) is not int or not 0<=acl['count']<=65535):raise ProbeFailure('PRECHECK')
                for row in acl['entries']:
                    if type(row) is not list or len(row)!=3 or any(type(v) is not int for v in row) or row[0] not in (1,2,4,8,16,32) or not 0<=row[1]<=4294967295 or not 0<=row[2]<=7:raise ProbeFailure('PRECHECK')
                if acl['state']=='PRESENT':
                    if acl['count']!=len(acl['entries']) or len({(r[0],r[1]) for r in acl['entries']})!=len(acl['entries']):raise ProbeFailure('PRECHECK')
                elif acl['entries']:raise ProbeFailure('PRECHECK')
                if acl['state']=='PRESENT' and (acl['count'] not in (3,5) or acl['entries']!=sorted(acl['entries'])):raise ProbeFailure('PRECHECK')
                if acl['state']=='TOO_MANY' and (type(acl['count']) is not int or not 5<acl['count']<=65535):raise ProbeFailure('PRECHECK')
                if acl['state'] in ('ABSENT','UNSUPPORTED','IO') and acl['count'] is not None:raise ProbeFailure('PRECHECK')
                if any((row[0] in (1,4,16,32) and row[1]!=4294967295) or (row[0] in (2,8) and row[1]==4294967295) for row in acl['entries']):raise ProbeFailure('PRECHECK')
        for item in objects:
            if item['decision'] not in ('ROOT_ACL_RO','SERVICE_OWNER_RO'):continue
            if item['check'] is not None or item['held_named_same'] is not True:raise ProbeFailure('PRECHECK')
            if policy is None:policy=_receipt_metadata_policy()
            role='directory' if item['slot']=='DIRECTORY' else 'file'
            try:selected=policy(_public_projection(item),role,consumer['uid'],consumer['gid'])
            except (ValueError,TypeError,KeyError):raise ProbeFailure('PRECHECK') from None
            legacy=(item['uid']==consumer['uid'] and item['mode']==(0o500 if role=='directory' else 0o400) and (role=='directory' or item['kind']=='regular' and item['nlink']==1))
            if selected!=item['decision'] or item['legacy_owner_only'] is not legacy:raise ProbeFailure('PRECHECK')
        if record['decision'] in ('ROOT_ACL_RO','SERVICE_OWNER_RO'):
            if slots!=list(METADATA_SLOTS[:-1] if record['phase']=='stock_base' else METADATA_SLOTS):raise ProbeFailure('PRECHECK')
            if consumer['uid'] is None or consumer['uid']==0 or consumer['gid'] is None or record['check'] is not None or not objects or slots[0]!='DIRECTORY' or any(v['decision']!=record['decision'] or v['check'] is not None for v in objects) or not all(v is True for k,v in consumer.items() if k not in ('uid','gid')) or any(v['readonly'] is not True or v['held_named_same'] is not True or v['mount_matches'] is not True or v['access'] is None or v['default'] is None or v['kind']!=('directory' if v['slot']=='DIRECTORY' else 'regular') for v in objects):raise ProbeFailure('PRECHECK')


def validate_unit_diagnostic(value):
    keys={'active','result','exit_kind','exit_status','invocation_matches','pid_matches','start_matches','start_elapsed_ms','exit_elapsed_ms'}
    if type(value) is not dict or set(value)!=keys:raise ProbeFailure('PRECHECK')
    for key,allowed in (('active',UNIT_ACTIVE),('result',UNIT_RESULTS),('exit_kind',('EXITED','SIGNALED','DUMPED','OTHER'))):
        if value[key] is not None and (type(value[key]) is not str or value[key] not in allowed):raise ProbeFailure('PRECHECK')
    for key,maximum in (('exit_status',255),('start_elapsed_ms',300000),('exit_elapsed_ms',300000)):
        if value[key] is not None and (type(value[key]) is not int or not 0<=value[key]<=maximum):raise ProbeFailure('PRECHECK')
    for key in ('invocation_matches','pid_matches','start_matches'):
        if value[key] is not None and type(value[key]) is not bool:raise ProbeFailure('PRECHECK')
    if value['exit_kind'] is None and value['exit_status'] is not None:raise ProbeFailure('PRECHECK')


def validate_ready_diagnostics(receipt):
    rows=receipt['startup_diagnostics'];resource=receipt['diagnostic_resources']
    if type(rows) is not dict or set(rows)!=set(PHASES) or type(resource) is not dict or set(resource)!=set(empty_diagnostic_resources()):raise ProbeFailure('PRECHECK')
    numeric=('listener_births','listener_closed','listener_unproved','accepted_births','accepted_closed','accepted_unproved','paths_born','paths_removed','paths_unproved')
    for key,item in resource.items():
        if key in numeric:
            if type(item) is not int or not 0<=item<=4:raise ProbeFailure('PRECHECK')
        elif type(item) is not bool:raise ProbeFailure('PRECHECK')
    if resource['listener_closed']>resource['listener_births'] or resource['accepted_closed']>resource['accepted_births'] or resource['paths_removed']>resource['paths_born']:raise ProbeFailure('PRECHECK')
    if (resource['directory_closed'] or resource['directory_removed'] or any(resource[k] for k in numeric)) and not resource['directory_born']:raise ProbeFailure('PRECHECK')
    if (resource['listener_unproved'] or resource['accepted_unproved'] or resource['paths_unproved']) and not resource['uncertain']:raise ProbeFailure('PRECHECK')
    if resource['uncertain'] and not receipt['resources']['cleanup_uncertain']:raise ProbeFailure('PRECHECK')
    for phase,row in rows.items():
        if row is None:
            if receipt['phases'][phase]:raise ProbeFailure('PRECHECK')
            continue
        if type(row) is not dict or set(row)!=set(empty_startup_diagnostic()) or len(canonical(row))>2048:raise ProbeFailure('PRECHECK')
        for key in ('last_stage','failed_at'):
            allowed=STARTUP_STAGES if key=='last_stage' else STARTUP_STAGES[:-2]
            if row[key] is not None and (type(row[key]) is not str or row[key] not in allowed):raise ProbeFailure('PRECHECK')
        for key,allowed in (('exception',STARTUP_EXCEPTIONS),('parent_failure',PARENT_FAILURES)):
            if row[key] is not None and (type(row[key]) is not str or row[key] not in allowed):raise ProbeFailure('PRECHECK')
        for key,low,high in (('errno',0,4095),('helper_returncode',-255,255),('frames',0,8),('startup_bytes',0,8192)):
            if row[key] is not None and (type(row[key]) is not int or not low<=row[key]<=high):raise ProbeFailure('PRECHECK')
        for key in ('deadline_reached','ready_observed'):
            if row[key] is not None and type(row[key]) is not bool:raise ProbeFailure('PRECHECK')
        try:validate_health(row['health'])
        except ValueError:raise ProbeFailure('PRECHECK') from None
        if row['last_stage']=='FAILED':
            if row['failed_at'] is None or row['exception'] is None or row['ready_observed'] is True:raise ProbeFailure('PRECHECK')
        elif any(row[key] is not None for key in ('failed_at','exception','errno')):raise ProbeFailure('PRECHECK')
        if row['ready_observed'] is True and (row['last_stage']!='READY' or not health_ready(row['health']) or row['frames']!=7 or row['startup_bytes'] is None or row['startup_bytes']==0 or row['deadline_reached'] is not False):raise ProbeFailure('PRECHECK')
        formal=row['formal']
        if type(formal) is not dict or set(formal)!=set(empty_startup_diagnostic()['formal']):raise ProbeFailure('PRECHECK')
        if formal['binding'] not in ('BOUND','UNPROVED') or formal['stream'] not in STREAM_STATES:raise ProbeFailure('PRECHECK')
        if formal['code'] is not None and formal['code'] not in FORMAL_CODES or formal['close_code'] not in (None,'FD_CLOSE_FAILED'):raise ProbeFailure('PRECHECK')
        if formal['binding']=='UNPROVED' and (formal['code'] is not None or formal['close_code'] is not None):raise ProbeFailure('PRECHECK')
        if formal['close_code'] is not None and formal['code'] is None:raise ProbeFailure('PRECHECK')
        try:validate_identity(formal['identity'])
        except ValueError:raise ProbeFailure('PRECHECK') from None
        if formal['identity'] is not None and (formal['binding']!='BOUND' or formal['code']!='CODE_IDENTITY_INVALID' or formal['stream'] not in ('OPEN','UNKNOWN_LINES','EOF')):raise ProbeFailure('PRECHECK')
        if receipt['phases'][phase] and formal['identity'] is not None:raise ProbeFailure('PRECHECK')
        for key,maximum in (('read_bytes',16384),('unknown_lines',16384),('receive_buffer',32768)):
            if formal[key] is not None and (type(formal[key]) is not int or not 0<=formal[key]<=maximum):raise ProbeFailure('PRECHECK')
        if formal['peer_root'] is not None and type(formal['peer_root']) is not bool:raise ProbeFailure('PRECHECK')
        if formal['binding']=='BOUND' and (formal['peer_root'] is not True or formal['receive_buffer'] is None or formal['receive_buffer']==0):raise ProbeFailure('PRECHECK')
        for key in ('unit_before','unit_after'):
            if row[key] is not None:validate_unit_diagnostic(row[key])
        if receipt['phases'][phase] and row['ready_observed'] is not True:raise ProbeFailure('PRECHECK')
    if receipt['outcome']=='PASS':
        if resource!=dict(empty_diagnostic_resources(),listener_births=4,listener_closed=4,accepted_births=4,accepted_closed=4,paths_born=4,paths_removed=4,directory_born=True,directory_closed=True,directory_removed=True):raise ProbeFailure('PRECHECK')
        if receipt['resources']['unit_invocations']!=4 or receipt['resources']['unit_exited']!=4:raise ProbeFailure('PRECHECK')
        for row in rows.values():
            if row is None or row['ready_observed'] is not True or row['parent_failure'] is not None or row['helper_returncode']!=0:raise ProbeFailure('PRECHECK')
            if row['formal']['binding']!='BOUND' or row['formal']['stream']!='EOF' or row['formal']['code'] is not None or row['formal']['close_code'] is not None:raise ProbeFailure('PRECHECK')
            final=row['unit_after']
            if final is None or final['active']!='inactive' or final['result']!='success' or final['exit_kind']!='EXITED' or final['exit_status']!=0 or not all(final[key] is True for key in ('invocation_matches','pid_matches','start_matches')):raise ProbeFailure('PRECHECK')


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
    failure=value['first_failure']
    if failure is not None:
        fields={'phase','operation','command','command_exit','exception','errno','account_check','account_mismatch_mask'}
        if type(failure) is not dict or set(failure)!=fields:raise ProbeFailure('PRECHECK')
        for key,allowed,nullable in (('phase',FAILURE_PHASES,False),('operation',FAILURE_OPERATIONS,False),('command',FAILURE_COMMANDS,True),('exception',FAILURE_EXCEPTIONS,True),('account_check',ACCOUNT_CHECKS,True)):
            item=failure[key]
            if not (nullable and item is None) and (type(item) is not str or item not in allowed):raise ProbeFailure('PRECHECK')
        for key,low,high in (('command_exit',-255,255),('errno',0,4095),('account_mismatch_mask',0,127)):
            item=failure[key]
            if item is not None and (type(item) is not int or not low<=item<=high):raise ProbeFailure('PRECHECK')
        if failure['command'] is None and failure['command_exit'] is not None or failure['exception'] is None and failure['errno'] is not None or failure['account_check'] is None and failure['account_mismatch_mask'] is not None:raise ProbeFailure('PRECHECK')
        if value['outcome']=='PASS':raise ProbeFailure('PRECHECK')
    validate_credential_metadata(value['credential_metadata'])
    validate_ready_diagnostics(value)
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
        if {record['phase'] for record in value['credential_metadata']}!=set(PHASES) or any(record['decision'] not in ('ROOT_ACL_RO','SERVICE_OWNER_RO') for record in value['credential_metadata']):raise ProbeFailure('PRECHECK')
        required=('cgroup_empty','credential_mount_gone','unit_removed','directories_removed','user_removed')
        if (not all(value['phases'].values()) or value['reason']!='OK' or value['resources']['cleanup_uncertain'] or value['resources']['forced']
                or not all(value['resources'][k] for k in required) or value['resources']['children_started']!=value['resources']['children_reaped']
                or not all(value['financial'][k] for k in ('initial_empty','normal_restart_unchanged','pre_get_closed_unreserved'))
                or not all(value['instrumented'][k] is True for k in ('source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline'))
                or value['instrumented']['observer_failed'] is not False):raise ProbeFailure('PRECHECK')
    raw=canonical(value)
    if len(raw)>32768:raise ProbeFailure('PRECHECK')
    return raw


STARTUP_STAGES=('CONFIG','SMTP_BIND','TLS_BIND','TLS_CERT','SERVERS_START','HEALTH_WAIT','READY','FAILED')
HEALTH_VALUES=('READY','UNAVAILABLE','ABSENT','OTHER')
HEALTH_TRANSPORTS=('OK','CONNECT','TLS','TIMEOUT','HTTP_ERROR','JSON','SHAPE','OTHER')
STARTUP_EXCEPTIONS=('OS_ERROR','TLS_ERROR','DEADLINE','VALUE_ERROR','OTHER')


def empty_health():return {'http_status':None,'base':None,'source_execute':None,'transport':None}


def validate_health(value):
    if type(value) is not dict or set(value)!=set(empty_health()):raise ValueError('FRAME_INVALID')
    status=value['http_status']
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('FRAME_INVALID')
    for key in ('base','source_execute'):
        if value[key] is not None and (type(value[key]) is not str or value[key] not in HEALTH_VALUES):raise ValueError('FRAME_INVALID')
    if value['transport'] is not None and (type(value['transport']) is not str or value['transport'] not in HEALTH_TRANSPORTS):raise ValueError('FRAME_INVALID')
    return value


def health_projection(status,body,transport):
    value=empty_health()
    if status is not None and (type(status) is not int or not 100<=status<=599):raise ValueError('FRAME_INVALID')
    if transport not in HEALTH_TRANSPORTS:raise ValueError('FRAME_INVALID')
    value.update(http_status=status,transport=transport)
    if body is None:return value
    if type(body) is not dict:return dict(value,transport='SHAPE')
    checks=body.get('checks',{})
    if type(checks) is not dict:return dict(value,transport='SHAPE')
    for key in ('base','source_execute'):
        observed=checks.get(key)
        value[key]='ABSENT' if key not in checks else 'READY' if observed=='ready' else 'UNAVAILABLE' if observed=='unavailable' else 'OTHER'
    return value


def health_ready(value):
    validate_health(value)
    return value['http_status']==200 and value['base']=='READY' and value['source_execute']=='READY' and value['transport']=='OK'


def ready_budget(now,controller_deadline):
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in (now,controller_deadline)):raise ValueError('DEADLINE')
    end=min(now+10,controller_deadline-30)
    if end<=now:raise ValueError('DEADLINE')
    return end,end-3


def validate_startup_frame(value):
    fields={'protocol','seq','stage','failed_at','exception','errno','health'}
    if type(value) is not dict or set(value)!=fields or value['protocol']!='native-helper-startup-v1':raise ValueError('FRAME_INVALID')
    if type(value['seq']) is not int or not 0<=value['seq']<8 or value['stage'] not in STARTUP_STAGES:raise ValueError('FRAME_INVALID')
    validate_health(value['health'])
    if value['stage']=='FAILED':
        if value['failed_at'] not in STARTUP_STAGES[:-2] or value['exception'] not in STARTUP_EXCEPTIONS:raise ValueError('FRAME_INVALID')
        if value['errno'] is not None and (type(value['errno']) is not int or not 0<=value['errno']<=4095):raise ValueError('FRAME_INVALID')
    elif any(value[k] is not None for k in ('failed_at','exception','errno')):raise ValueError('FRAME_INVALID')
    if value['stage']=='READY' and not health_ready(value['health']):raise ValueError('FRAME_INVALID')
    if value['stage'] not in ('READY','FAILED','HEALTH_WAIT') and value['health']!=empty_health():raise ValueError('FRAME_INVALID')
    return value


class StartupFrames:
    """Finite data-only protocol state, never a service or capability."""
    def __init__(self):self.count=0;self.total=0;self.pending=bytearray();self.last=None;self.terminal=None;self.health=empty_health();self.failed_at=None;self.exception=None;self.errno=None
    def accept(self,value):
        validate_startup_frame(value)
        if self.terminal is not None or value['seq']!=self.count:raise ValueError('FRAME_INVALID')
        stage=value['stage']
        if stage=='FAILED':
            if self.last is None or value['failed_at']!=self.last:raise ValueError('FRAME_INVALID')
        elif stage=='READY':
            if self.last!='HEALTH_WAIT':raise ValueError('FRAME_INVALID')
        elif stage!=STARTUP_STAGES[self.count]:raise ValueError('FRAME_INVALID')
        self.count+=1
        if self.count>8:raise ValueError('FRAME_LIMIT')
        self.last=stage;self.health=dict(value['health']);self.failed_at=value['failed_at'];self.exception=value['exception'];self.errno=value['errno']
        if stage in ('READY','FAILED'):self.terminal=stage
    def feed(self,raw):
        if type(raw) is not bytes or not raw:raise ValueError('FRAME_INVALID')
        self.total+=len(raw)
        if self.total>8192:raise ValueError('FRAME_LIMIT')
        for byte in raw:
            if self.terminal is not None:raise ValueError('FRAME_INVALID')
            self.pending.append(byte)
            if len(self.pending)>1024 or len(self.pending)==1024 and byte!=10:
                self.pending.clear();raise ValueError('FRAME_LIMIT')
            if byte==10:
                line=bytes(self.pending[:-1]);self.pending.clear()
                self.accept(strict_json(line,1023))
    def finish(self):
        if self.pending or self.terminal is None:raise ValueError('EOF')



OBSERVATION=Path('/run/structural-native-probe-observation')
FORMAL_CODES=('ENTRY_ARGUMENTS', 'INTERPRETER_FLAGS', 'INHERITED_SECRET', 'CODE_OVERRIDE', 'PROFILE_INVALID', 'SMTP_AUTH_REQUIRED', 'CREDENTIAL_DIRECTORY_INVALID', 'UNSUPPORTED_PLATFORM', 'SERVICE_IDENTITY_INVALID', 'CORE_HARDENING_FAILED', 'DUMP_HARDENING_FAILED', 'BOUNDARY_CHANGED', 'CREDENTIAL_METADATA_INVALID', 'CREDENTIAL_CHANGED', 'CREDENTIAL_SIZE_INVALID', 'CREDENTIAL_ENCODING_INVALID', 'CREDENTIAL_FORMAT_INVALID', 'CREDENTIAL_IO_FAILED', 'FD_CLOSE_FAILED', 'ENV_INSTALL_FAILED', 'CODE_IDENTITY_INVALID', 'APP_IMPORT_FAILED', 'SERVER_FAILED')
IDENTITY_SITES = ('SRC_ROOT', 'SRC_COMPONENT', 'SRC_LEAF_BOUNDS', 'SRC_READBACK', 'HELPER_MODULE', 'HELPER_BUILTINS', 'HELPER_MEMBERS', 'HELPER_FUNCTION', 'HELPER_CONSTANT', 'HELPER_SOURCE_REREAD', 'LOAD_PREINJECT', 'LOAD_SOURCE_CHANGED', 'ENTRY_PATH', 'ENTRY_WITNESS_PAIR', 'APP_PREIMPORT', 'ENTRY_MODULE', 'ENTRY_BUILTINS', 'ENTRY_FUNCTION', 'MAIN_IDENTITY')
IDENTITY_MASKS = {'SRC_ROOT': 3, 'SRC_COMPONENT': 15, 'SRC_LEAF_BOUNDS': 48, 'SRC_READBACK': 192}
STREAM_STATES=('IDENTITY_INVALID','LISTENING','OPEN','EOF','UNKNOWN_LINES','READ_LIMIT','LINE_TOO_LONG','TRUNCATED','EXTRA_CODE','PEER_INVALID','DUPLICATE_PEER','BINDING_UNPROVED','IO','CLOSE_UNKNOWN')
PARENT_FAILURES=('TIMEOUT','EOF','FRAME_INVALID','FRAME_LIMIT','HELPER_EXIT','HELPER_FAILED','STDERR_INVALID','BINDING_UNPROVED','IO')
UNIT_ACTIVE=('active','activating','deactivating','inactive','failed','reloading','OTHER')
UNIT_RESULTS=('success','exit-code','signal','core-dump','timeout','watchdog','oom-kill','start-limit-hit','resources','protocol','OTHER')


def empty_startup_diagnostic():
    return {'last_stage':None,'failed_at':None,'exception':None,'errno':None,'health':empty_health(),
        'parent_failure':None,'helper_returncode':None,'deadline_reached':None,'ready_observed':None,'frames':None,'startup_bytes':None,
        'formal':{'binding':'UNPROVED','code':None,'close_code':None,'identity':None,'stream':'LISTENING','read_bytes':0,'unknown_lines':0,'receive_buffer':None,'peer_root':None},
        'unit_before':None,'unit_after':None}


def empty_diagnostic_resources():
    return {'listener_births':0,'listener_closed':0,'listener_unproved':0,'accepted_births':0,'accepted_closed':0,'accepted_unproved':0,'paths_born':0,'paths_removed':0,'paths_unproved':0,
        'directory_born':False,'directory_closed':False,'directory_removed':False,'uncertain':False}


def validate_identity(value):
    if value is None:return None
    if type(value) is not dict or set(value)!={'site','component_index','predicate_mask'}:raise ValueError('IDENTITY_INVALID')
    site,component,mask=value['site'],value['component_index'],value['predicate_mask']
    if type(site) is not str or site not in IDENTITY_SITES:raise ValueError('IDENTITY_INVALID')
    if site in IDENTITY_MASKS:
        if component is not None and (type(component) is not int or (component!=0 if site=='SRC_ROOT' else not 1<=component<=31)):raise ValueError('IDENTITY_INVALID')
        if mask is not None and (type(mask) is not int or mask<=0 or mask & ~IDENTITY_MASKS[site]):raise ValueError('IDENTITY_INVALID')
    elif component is not None or mask is not None:raise ValueError('IDENTITY_INVALID')
    return value


def parse_identity_line(line):
    parts=line[:-1].split(b':')
    if len(parts)!=4 or parts[0]!=b'FORMAL_IDENTITY_V1' or not line.endswith(b'\n'):raise ValueError('IDENTITY_INVALID')
    def number(raw):
        if raw==b'-':return None
        if not 0<len(raw)<=3 or not raw.isdigit() or str(int(raw)).encode('ascii')!=raw:raise ValueError('IDENTITY_INVALID')
        return int(raw)
    try:site=parts[1].decode('ascii')
    except UnicodeDecodeError:raise ValueError('IDENTITY_INVALID') from None
    return validate_identity({'site':site,'component_index':number(parts[2]),'predicate_mask':number(parts[3])})


class FormalCodeBytes:
    def __init__(self):self.total=0;self.pending=bytearray();self.codes=[];self.identity=None;self.identity_adjacent=False;self.unknown=0;self.state='OPEN'
    def _fail(self,state):
        self.identity=None;self.identity_adjacent=False;self.state=state;raise ValueError(state)
    def feed(self,raw):
        if type(raw) is not bytes or not 0<len(raw)<=1024:self._fail('IO')
        if self.state not in ('OPEN','UNKNOWN_LINES'):self._fail(self.state)
        if self.total+len(raw)>16384:self._fail('READ_LIMIT')
        self.total+=len(raw)
        for byte in raw:
            self.pending.append(byte)
            if len(self.pending)>128:self.pending.clear();self._fail('LINE_TOO_LONG')
            if byte==10:
                line=bytes(self.pending);self.pending.clear()
                if line.startswith(b'FORMAL_IDENTITY'):
                    if not self.identity_adjacent or self.identity is not None or self.codes!=['CODE_IDENTITY_INVALID']:self._fail('IDENTITY_INVALID')
                    try:self.identity=parse_identity_line(line)
                    except ValueError:self._fail('IDENTITY_INVALID')
                    self.identity_adjacent=False
                else:
                    matched=next((code for code in FORMAL_CODES if line==b'FORMAL_ENTRY:'+code.encode('ascii')+b'\n'),None)
                    self.identity_adjacent=False
                    if matched is None:self.unknown+=1;self.state='UNKNOWN_LINES'
                    else:
                        if len(self.codes)>=2 or self.codes and matched!='FD_CLOSE_FAILED':self._fail('EXTRA_CODE')
                        self.codes.append(matched)
                        self.identity_adjacent=self.codes==['CODE_IDENTITY_INVALID']
        if self.total==16384:self._fail('READ_LIMIT')
    def finish(self):
        if self.pending:self.pending.clear();self._fail('TRUNCATED')
        if self.state in ('OPEN','UNKNOWN_LINES'):self.state='EOF'



def unit_diagnostic(raw,expected,now):
    value={'active':None,'result':None,'exit_kind':None,'exit_status':None,'invocation_matches':None,'pid_matches':None,'start_matches':None,'start_elapsed_ms':None,'exit_elapsed_ms':None}
    if type(raw) is not dict:return value
    value['active']=raw.get('ActiveState') if raw.get('ActiveState') in UNIT_ACTIVE else 'OTHER'
    value['result']=raw.get('Result') if raw.get('Result') in UNIT_RESULTS else 'OTHER'
    def number(key,maximum=2**63-1):
        item=raw.get(key)
        return int(item) if type(item) is str and item.isascii() and 0<len(item)<=20 and item.isdecimal() and 0<=int(item)<=maximum else None
    code=number('ExecMainCode',255);status=number('ExecMainStatus',255)
    if code is not None:value['exit_kind']={0:None,1:'EXITED',2:'SIGNALED',3:'DUMPED'}.get(code,'OTHER')
    if code in (1,2,3):value['exit_status']=status
    if type(expected) is dict:
        value['invocation_matches']=raw.get('InvocationID')==expected.get('InvocationID')
        pid=number('ExecMainPID',2**31-1)
        value['pid_matches']=pid is not None and pid==expected.get('pid') and raw.get('MainPID') in ('0',str(pid))
        start=number('ExecMainStartTimestampMonotonic')
        value['start_matches']=start is not None and start>0 and start==expected.get('start')
    for key,field in (('ExecMainStartTimestampMonotonic','start_elapsed_ms'),('ExecMainExitTimestampMonotonic','exit_elapsed_ms')):
        point=number(key)
        if point is not None and point>0 and type(now) in (int,float) and math.isfinite(now):
            elapsed=int(now*1000)-point//1000
            if 0<=elapsed<=300000:value[field]=elapsed
    return value


def peer_unit_binding(peer,before,after,window):
    if type(peer) is not tuple or len(peer)!=3 or any(type(v) is not int for v in peer) or peer[0]<=1 or peer[1]!=0 or not 0<=peer[2]<2**32:return False
    if type(before) is not dict or type(after) is not dict or type(window) is not tuple or len(window)!=2:return False
    if any(type(v) not in (int,float) or not math.isfinite(v) for v in window) or window[0]>window[1]:return False
    invocation=before.get('InvocationID')
    if type(invocation) is not str or invocation!=after.get('InvocationID') or not re.fullmatch('[0-9a-f]{32}',invocation):return False
    points=[]
    for row in (before,after):
        if row.get('ExecMainPID')!=str(peer[0]) or row.get('MainPID') not in ('0',str(peer[0])):return False
        raw=row.get('ExecMainStartTimestampMonotonic')
        if type(raw) is not str or not raw.isascii() or not 0<len(raw)<=20 or not raw.isdecimal():return False
        point=int(raw)
        if not 0<point<2**63 or not int(window[0]*1000000)<=point<=int(window[1]*1000000):return False
        points.append(point)
    return points[0]==points[1]


class DiagnosticHandle:
    """Owned object retained before initialization; unknown is never retired."""
    def __init__(self,kind):self.kind=kind;self.obj=None;self.fd=None;self.identity=None;self.born=False;self.closed=False;self.uncertain=False
    def remember(self,obj):
        self.obj=obj;self.fd=obj.fileno()
        if type(self.fd) is not int or self.fd<0:raise OSError('diagnostic descriptor birth unproved')
        self.born=True
        info=os.fstat(self.fd);self.identity=(info.st_dev,info.st_ino)
        if not stat.S_ISSOCK(info.st_mode):raise OSError('diagnostic descriptor kind invalid')
    def require(self):
        if self.obj is None or self.fd is None or self.identity is None or self.closed:raise OSError('diagnostic ownership unknown')
        info=os.fstat(self.fd)
        if self.obj.fileno()!=self.fd or (info.st_dev,info.st_ino)!=self.identity:raise OSError('diagnostic descriptor changed')
    def close(self):
        if self.closed:
            if self.uncertain:raise OSError('diagnostic retirement uncertain')
            return
        try:
            self.require();self.obj.close()
            if self.obj.fileno()!=-1:raise OSError('diagnostic descriptor still attached')
            try:info=os.fstat(self.fd)
            except OSError as error:
                if error.errno!=9:raise
            else:
                if (info.st_dev,info.st_ino)==self.identity:raise OSError('diagnostic descriptor still present')
            if self.uncertain:raise OSError('prior diagnostic birth or retirement uncertainty')
            self.closed=True
        except BaseException:self.uncertain=True;raise



class Controller:
    def __init__(self,meta,budget,python):
        self.meta,self.budget,self.python=meta,budget,python;self.result=empty_receipt(meta['head']);self.children=[];self.paths=[];self.user=False;self.group=False;self.unit_written=False;self.invocations=[];self.server=None;self.uid=self.gid=None;self.password=None;self.rpc_buffer=b'';self.uncertain=False;self.attempts={};self.group_attempted=False;self.user_attempted=False;self.group_record=None;self.user_record=None;self._first_reason=None;self._phase='preflight';self._metadata_module=None;self._metadata_uncertain=[];self._diag=None;self._diag_handles=[];self._diag_directory_fd=None;self._diag_directory_identity=None;self._diag_unit_bytes=None;self._diag_unit_identity=None;self._where={'operation':'unknown','command':None,'command_exit':None,'account_check':None,'account_mismatch_mask':None}
    def _wait_process(self,process,timeout,clean=False):
        end=time.monotonic()+timeout
        while True:
            self._diag_pump(clean=clean)
            if process.poll() is not None:return process.returncode
            left=end-time.monotonic()
            if left<=0:raise subprocess.TimeoutExpired('owned-process',timeout)
            self._wait_io([],[],min(end,time.monotonic()+.05),clean=clean)
    def _diag_uncertain(self):
        self.uncertain=True;self.result['diagnostic_resources']['uncertain']=True
    def _diag_fault(self,state,clean=False):
        if self._diag is not None:
            self._diag['record']['formal']['identity']=None;self._diag['stream'].identity=None
        if self._diag is not None and self._diag['record']['formal']['stream'] in ('LISTENING','OPEN','EOF','UNKNOWN_LINES'):self._diag['record']['formal']['stream']=state
        self._diag_uncertain()
        if not clean:
            if self._diag is not None:self._diag['record']['parent_failure']=self._diag['record']['parent_failure'] or 'STDERR_INVALID'
            self._mark('ready_diagnostics');self._reject('HTTP')
    def _diag_new_socket(self):
        handle=DiagnosticHandle('listener');self._diag_handles.append(handle)
        self._diag['listener']=handle
        try:
            kind=socket.socket
            if not isinstance(kind,type):raise OSError('diagnostic socket type changed')
            obj=kind.__new__(kind);handle.obj=obj
            kind.__init__(obj,socket.AF_UNIX,socket.SOCK_STREAM|socket.SOCK_CLOEXEC)
            handle.remember(obj)
            obj.setblocking(False);os.set_inheritable(handle.fd,False)
            return handle
        except BaseException:
            handle.uncertain=True;self._diag_uncertain()
            if handle.obj is not None and not handle.born:
                try:handle.remember(handle.obj)
                except BaseException:pass
            raise
        finally:
            if handle.born:self.result['diagnostic_resources']['listener_births']+=1
    def _diag_open(self):
        if self._diag is not None or self._phase not in PHASES or self.result['startup_diagnostics'][self._phase] is not None:self._reject('PRECHECK')
        resource=self.result['diagnostic_resources']
        if sum(handle.kind=='listener' for handle in self._diag_handles)>=4:self._reject('PRECHECK')
        record=empty_startup_diagnostic();self.result['startup_diagnostics'][self._phase]=record
        path=OBSERVATION/(self._phase+'.sock')
        self._diag={'phase':self._phase,'record':record,'path':path,'path_identity':None,'bind_attempted':False,'bound':False,'listener':None,'peer':None,'credentials':None,'first_unit':None,'last_unit':None,'window_start':None,'window_end':None,'unit_count':0,'accepted_at_count':None,'sampled':False,'stream':FormalCodeBytes()}
        try:
            self._diag_directory_check();self.absent(path)
            listener=self._diag_new_socket();self._diag['listener']=listener
            self._diag['bind_attempted']=True;listener.obj.bind(str(path));self._diag['bound']=True;resource['paths_born']+=1
            initial=path.lstat()
            if not stat.S_ISSOCK(initial.st_mode) or (initial.st_uid,initial.st_nlink)!=(0,1):raise OSError('socket path birth invalid')
            self._diag['path_identity']=stat_key(initial)
            os.chown(path,0,0);path.chmod(0o600);info=path.lstat()
            if (info.st_dev,info.st_ino)!=(initial.st_dev,initial.st_ino):raise OSError('socket path replaced')
            if not stat.S_ISSOCK(info.st_mode) or (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)!=(0,0,0o600,1):raise OSError('diagnostic socket path invalid')
            self._diag['path_identity']=stat_key(info)
            listener.obj.listen(1)
            self._diag_directory_check()
        except BaseException:self._diag_uncertain();raise
    def _diag_create_directory(self):
        self._mark('directory_create');self.absent(OBSERVATION)
        OBSERVATION.mkdir(mode=0o700);self.paths.append(OBSERVATION)
        self.result['diagnostic_resources']['directory_born']=True
        try:
            self._mark('directory_owner');os.chown(OBSERVATION,0,0);OBSERVATION.chmod(0o700)
            self._diag_directory_fd=os.open(OBSERVATION,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
            info=os.fstat(self._diag_directory_fd)
            self._diag_directory_identity=(info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))
            self._diag_directory_check()
        except BaseException:self._diag_uncertain();raise
    def _diag_directory_check(self):
        if self._diag_directory_fd is None or self._diag_directory_identity is None:raise OSError('observation directory unproved')
        info=os.fstat(self._diag_directory_fd);named=OBSERVATION.lstat()
        identity=lambda value:(value.st_dev,value.st_ino,value.st_uid,value.st_gid,stat.S_IMODE(value.st_mode))
        if identity(info)!=self._diag_directory_identity or identity(named)!=identity(info) or not stat.S_ISDIR(info.st_mode) or identity(info)[2:]!=(0,0,0o700):raise OSError('observation directory changed')
    def _diag_unit_rotate(self):
        if not self.unit_written or self._diag_unit_bytes is None or self._diag_unit_identity is None:self._reject('UNIT')
        before=UNIT_FILE.lstat()
        if stat_key(before)!=self._diag_unit_identity or not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or UNIT_FILE.read_bytes()!=self._diag_unit_bytes:self._reject('UNIT')
        lines=self._diag_unit_bytes.decode().splitlines()
        if sum(line.startswith('StandardError=') for line in lines)!=1:self._reject('UNIT')
        lines=['StandardError=file:'+str(self._diag['path']) if line.startswith('StandardError=') else line for line in lines]
        UNIT_FILE.unlink();self.paths.remove(UNIT_FILE);self.unit_written=False
        self.write(UNIT_FILE,('\n'.join(lines)+'\n').encode(),mode=0o644);self.unit_written=True
        self._diag_unit_bytes=UNIT_FILE.read_bytes();self._diag_unit_identity=stat_key(UNIT_FILE.lstat())
        self.command(['/usr/bin/systemctl','daemon-reload'])
    def _diag_note_unit(self,rows,clean=False):
        if self._diag is None:return
        item=self._diag;was_bound=item['record']['formal']['binding']=='BOUND'
        if item['first_unit'] is None:item['first_unit']=dict(rows)
        item['last_unit']=dict(rows);item['window_end']=time.monotonic();item['unit_count']=item.get('unit_count',0)+1
        self._diag_refresh_binding()
        if was_bound and item['record']['formal']['binding']!='BOUND':
            item['record']['parent_failure']=item['record']['parent_failure'] or 'BINDING_UNPROVED'
            self._diag_fault('BINDING_UNPROVED',clean=clean)
    def _diag_refresh_binding(self):
        if self._diag is None:return
        item=self._diag;formal=item['record']['formal'];before=item['first_unit'];after=item['last_unit']
        bound=(item.get('unit_count',0)>=2 and type(item.get('accepted_at_count')) is int and item['unit_count']>item['accepted_at_count'] and item['window_start'] is not None and item['window_end'] is not None and peer_unit_binding(item['credentials'],before,after,(item['window_start'],item['window_end'])))
        formal['binding']='BOUND' if bound else 'UNPROVED'
        formal['code']=item['stream'].codes[0] if bound and item['stream'].codes else None
        formal['close_code']=item['stream'].codes[1] if bound and len(item['stream'].codes)>1 else None
        formal['identity']=item['stream'].identity if bound and formal['code']=='CODE_IDENTITY_INVALID' and item['stream'].state in ('OPEN','UNKNOWN_LINES','EOF') else None
    def _diag_sources(self):
        if self._diag is None:return []
        out=[];item=self._diag
        for key in ('listener','peer'):
            handle=item[key]
            if handle is not None and not handle.closed:
                if key=='peer' and item['stream'].state not in ('OPEN','UNKNOWN_LINES'):continue
                try:handle.require()
                except BaseException:handle.uncertain=True;self._diag_uncertain();raise
                out.append(handle.obj)
        return out
    def _diag_pump(self,ready=None,clean=False):
        if self._diag is None:return
        item=self._diag
        try:
            self._diag_directory_check()
            if item['path_identity'] is None or stat_key(item['path'].lstat())!=item['path_identity']:raise OSError('diagnostic path changed')
            sources=self._diag_sources()
            available=select.select(sources,[],[],0)[0] if ready is None else ready
            listener=item['listener']
            if listener is not None and listener.obj in available:
                if item['peer'] is not None:self._diag_fault('DUPLICATE_PEER',clean);return
                handle=DiagnosticHandle('accepted');self._diag_handles.append(handle);item['peer']=handle
                try:
                    obj,_=listener.obj.accept();handle.obj=obj
                    handle.remember(obj)
                    item['peer']=handle;obj.setblocking(False);os.set_inheritable(handle.fd,False)
                    obj.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8192)
                    amount=obj.getsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF)
                    if type(amount) is not int or not 0<amount<=32768:raise OSError('diagnostic receive buffer unproved')
                    item['record']['formal']['receive_buffer']=amount
                    credentials=struct.unpack('3i',obj.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    item['credentials']=credentials;item['accepted_at_count']=item.get('unit_count',0);item['record']['formal']['peer_root']=credentials[1]==0
                    if credentials[0]<=1 or credentials[1]!=0 or credentials[2]<0:self._diag_fault('PEER_INVALID',clean);return
                    item['record']['formal']['stream']='OPEN';self._diag_refresh_binding()
                except BlockingIOError:
                    if handle.obj is not None or handle.born:
                        handle.uncertain=True;self._diag_uncertain();self._diag_fault('IO',clean)
                    else:self._diag_handles.remove(handle);item['peer']=None
                except BaseException:
                    handle.uncertain=True;self._diag_uncertain()
                    if handle.obj is not None and not handle.born:
                        try:handle.remember(handle.obj)
                        except BaseException:pass
                    raise
                finally:
                    if handle.born:self.result['diagnostic_resources']['accepted_births']+=1
            peer=item['peer']
            if peer is not None and (peer.obj in available or ready is None) and item['stream'].state in ('OPEN','UNKNOWN_LINES'):
                peer.require()
                try:raw=peer.obj.recv(min(1024,16384-item['stream'].total))
                except BlockingIOError:return
                try:
                    if raw:item['stream'].feed(raw)
                    else:item['stream'].finish()
                except ValueError as error:
                    self._diag_refresh_binding()  # Keep an observed primary even if its annotation is invalid.
                    self._diag_fault(error.args[0] if error.args and error.args[0] in STREAM_STATES else 'IO',clean)
                finally:
                    formal=item['record']['formal'];formal.update(read_bytes=item['stream'].total,unknown_lines=item['stream'].unknown,stream=item['stream'].state)
                self._diag_refresh_binding()
        except ProbeFailure:raise
        except BaseException:self._diag_fault('IO',clean)
    def _wait_io(self,readers,writers,end,clean=False):
        while True:
            left=end-time.monotonic()
            if left<=0:return [],[]
            streams=self._diag_sources()
            readable,writable,_=select.select([*readers,*streams],writers,[],min(left,.05))
            self._diag_pump(readable,clean)
            chosen=[fd for fd in readable if fd in readers]
            if time.monotonic()>=end:return [],[]
            if chosen or writable:return chosen,writable
    def _write_helper(self,raw,end):
        fd=self.server.stdin.fileno();os.set_blocking(fd,False);offset=0
        while offset<len(raw):
            if not self._wait_io([],[fd],end)[1]:raise ValueError('TIMEOUT')
            try:sent=os.write(fd,raw[offset:])
            except BlockingIOError:continue
            if sent<=0:raise ValueError('IO')
            offset+=sent
            if time.monotonic()>=end:raise ValueError('TIMEOUT')
    def _startup_wait(self,end):
        decoder=StartupFrames();record=self._diag['record'];record.update(frames=0,startup_bytes=0,ready_observed=False,deadline_reached=False)
        fd=self.server.stdout.fileno();os.set_blocking(fd,False)
        try:
            while decoder.terminal is None:
                if not self._wait_io([fd],[],end)[0]:raise ValueError('TIMEOUT')
                if decoder.total>=8192:raise ValueError('FRAME_LIMIT')
                raw=os.read(fd,min(1024,8192-decoder.total))
                if not raw:
                    record['helper_returncode']=self.server.poll()
                    raise ValueError('HELPER_EXIT' if record['helper_returncode'] is not None else 'EOF')
                decoder.feed(raw)
                record.update(last_stage=decoder.last,failed_at=decoder.failed_at,exception=decoder.exception,errno=decoder.errno,health=dict(decoder.health),frames=decoder.count,startup_bytes=decoder.total)
            if decoder.terminal!='READY':raise ValueError('HELPER_FAILED')
            decoder.finish();self._diag_pump();self._diag_refresh_binding()
            if self._diag['record']['formal']['binding']!='BOUND':raise ValueError('BINDING_UNPROVED')
            if time.monotonic()>=end:raise ValueError('TIMEOUT')
            record['ready_observed']=True
        except BaseException as error:
            record.update(last_stage=decoder.last,failed_at=decoder.failed_at,exception=decoder.exception,errno=decoder.errno,health=dict(decoder.health),frames=decoder.count,startup_bytes=decoder.total)
            label=error.args[0] if type(error) is ValueError and error.args and error.args[0] in PARENT_FAILURES else 'FRAME_INVALID'
            record['parent_failure']=record['parent_failure'] or label;record['deadline_reached']=time.monotonic()>=end
            self._mark('helper_ready',command='helper');self._reject('HTTP')
    def _diag_unit_expected(self):
        if self._diag is None or self._diag['credentials'] is None or self._diag['first_unit'] is None:return None
        raw=self._diag['first_unit'];point=raw.get('ExecMainStartTimestampMonotonic','')
        if type(point) is not str or not point.isascii() or not 0<len(point)<=20 or not point.isdecimal():return None
        return {'InvocationID':raw.get('InvocationID'),'pid':self._diag['credentials'][0],'start':int(point)}
    def _diag_failure_snapshot(self):
        if self._diag is None or self._diag['sampled']:return
        self._diag['sampled']=True;prior=self._where
        try:
            available=self.budget.require(new=True,ceiling=1)
            rows=self.unit_info(clean=True,limit=available)
            self._diag['record']['unit_before']=unit_diagnostic(rows,self._diag_unit_expected(),time.monotonic())
        except BaseException:pass
        finally:self._where=prior
    def _diag_retire(self,unit_gone):
        if self._diag is None:return
        item=self._diag;failed=False
        try:
            for _ in range(17):
                sources=self._diag_sources()
                if not select.select(sources,[],[],0)[0]:break
                self._diag_pump(clean=True)
        except BaseException:failed=True
        if not unit_gone:self._diag_uncertain();return
        for key in ('peer','listener'):
            handle=item[key]
            if handle is None:continue
            try:handle.close();self.result['diagnostic_resources']['accepted_closed' if key=='peer' else 'listener_closed']+=1
            except BaseException:
                failed=True
                if item['record']['formal']['stream'] in ('LISTENING','OPEN','EOF','UNKNOWN_LINES'):item['record']['formal']['stream']='CLOSE_UNKNOWN'
        try:
            if item['path_identity'] is None:
                if item['bind_attempted']:
                    raise OSError('socket path birth unknown')
            else:
                self._diag_directory_check()
                if stat_key(item['path'].lstat())!=item['path_identity']:raise OSError('socket path replaced')
                item['path'].unlink();self.result['diagnostic_resources']['paths_removed']+=1
        except BaseException:
            self.result['diagnostic_resources']['paths_unproved']+=1;failed=True
        resource=self.result['diagnostic_resources']
        resource['listener_unproved']=sum(h.kind=='listener' and (h.uncertain or h.identity is None) for h in self._diag_handles)
        resource['accepted_unproved']=sum(h.kind=='accepted' and (h.uncertain or h.identity is None) for h in self._diag_handles)
        if failed:self._diag_uncertain()
        self._diag=None
    def _diag_close_directory(self):
        resource=self.result['diagnostic_resources']
        if not resource['directory_born']:return
        try:
            self._diag_directory_check()
            fd=self._diag_directory_fd;os.close(fd)
            try:remaining=os.fstat(fd)
            except OSError as error:
                if error.errno!=9:raise
            else:
                if (remaining.st_dev,remaining.st_ino)==self._diag_directory_identity[:2]:raise OSError('directory descriptor remains')
            resource['directory_closed']=True;self._diag_directory_fd=None
            if (OBSERVATION.lstat().st_dev,OBSERVATION.lstat().st_ino)!=self._diag_directory_identity[:2]:raise OSError('observation directory replaced')
            OBSERVATION.rmdir();resource['directory_removed']=True
        except BaseException:self._diag_uncertain()
    def _mark(self,operation,*,command=None,command_exit=None,account_check=None,account_mismatch_mask=None):
        self._where=dict(operation=operation,command=command,command_exit=command_exit,account_check=account_check,account_mismatch_mask=account_mismatch_mask)
    def _capture(self,error=None):
        if self.result['first_failure'] is not None:return
        # Never format an exception, argv, account field, path or traceback.
        category=None;number=None
        if error is not None:
            category=('TIMEOUT' if isinstance(error,subprocess.TimeoutExpired) else 'PROBE_FAILURE' if isinstance(error,ProbeFailure) else 'OS_ERROR' if isinstance(error,OSError) else 'VALUE_ERROR' if isinstance(error,ValueError) else 'TYPE_ERROR' if isinstance(error,TypeError) else 'KEY_ERROR' if isinstance(error,KeyError) else 'ASSERTION_ERROR' if isinstance(error,AssertionError) else 'OTHER')
            if isinstance(error,OSError):
                try:number=error.errno
                except BaseException:number=None
                if type(number) is not int or not 0<=number<=4095:number=None
        where=self._where
        # A corrupt diagnostic marker cannot inject private text into artifact.
        failure={'phase':self._phase if type(self._phase) is str and self._phase in FAILURE_PHASES else 'unknown','operation':where['operation'] if type(where['operation']) is str and where['operation'] in FAILURE_OPERATIONS else 'unknown','command':where['command'] if type(where['command']) is str and where['command'] in FAILURE_COMMANDS else None,'command_exit':where['command_exit'] if type(where['command_exit']) is int and -255<=where['command_exit']<=255 else None,'exception':category,'errno':number,'account_check':where['account_check'] if type(where['account_check']) is str and where['account_check'] in ACCOUNT_CHECKS else None,'account_mismatch_mask':where['account_mismatch_mask'] if type(where['account_mismatch_mask']) is int and 0<=where['account_mismatch_mask']<=127 else None}
        if failure['command'] is None:failure['command_exit']=None
        if failure['account_check'] is None:failure['account_mismatch_mask']=None
        self.result['first_failure']=failure
        self._first_reason=('CLEANUP' if failure['phase']=='cleanup' else error.reason if isinstance(error,ProbeFailure) else 'CLOCK' if isinstance(error,subprocess.TimeoutExpired) else 'INTERNAL')
    def _reject(self,reason):
        error=ProbeFailure(reason);self._capture(error);raise error
    def _account_reject(self,check,mask=None):
        operation=self._where['operation']
        self._mark(operation if operation in ('group_record','user_record') else 'account_record',account_check=check,account_mismatch_mask=mask)
        self._reject('CLEANUP')
    def _command_name(self,argv):
        # Only fixed labels leave this private controller, never argument text.
        if argv[:len(GIT)]==list(GIT):
            return {('rev-parse','HEAD'):'git_head',('status','--porcelain','--untracked-files=all'):'git_status',('rev-parse','HEAD^{tree}'):'git_tree',('ls-tree','-r','-z','HEAD'):'git_listing'}.get(tuple(argv[len(GIT):]),'unknown')
        if argv and argv[0]=='/usr/bin/systemctl':
            return {'--version':'systemd_version','daemon-reload':'unit_reload','show':'unit_show','start':'unit_start','stop':'unit_stop','kill':'unit_kill'}.get(argv[1] if len(argv)>1 else None,'unknown')
        if argv and argv[0]=='/usr/bin/setpriv':return 'bootstrap' if argv[-1]=='bootstrap' else 'code_export'
        return {'/usr/sbin/groupadd':'group_add','/usr/sbin/useradd':'user_add','/usr/sbin/userdel':'user_delete','/usr/sbin/groupdel':'group_delete','/usr/bin/openssl':'certificate'}.get(argv[0] if argv else None,'unknown')
    def _process_identity(self,process):
        # PID alone is not a birth witness. The start tick, proc inode, parent,
        # process group and session must still describe this owned child.
        pid=process.pid
        if type(pid) is not int or pid<=0:self._reject('CLEANUP')
        root=Path('/proc')/str(pid)
        def snapshot():
            info=root.stat();raw=(root/'stat').read_text();end=raw.rfind(') ')
            fields=raw[end+2:].split()
            if end<0 or raw[:raw.find(' (')]!=str(pid) or len(fields)<20:self._reject('CLEANUP')
            parent,group,session,tick=(int(fields[i]) for i in (1,2,3,19))
            if parent!=os.getpid() or group!=pid or session!=pid or tick<0:self._reject('CLEANUP')
            return info.st_dev,info.st_ino,parent,group,session,tick
        before=snapshot()
        if snapshot()!=before:self._reject('CLEANUP')
        return before
    def _spawn(self,argv,*,new=True,**kwargs):
        self.budget.require(new=new)
        kind=subprocess.Popen
        if not isinstance(kind,type):self._reject('PRECHECK')
        process=kind.__new__(kind)
        # Retain the actual object before __init__: it may fork and then raise.
        self.children.append(process)
        record={'complete':False,'birth':'unborn','identity':None,'reaped':False}
        self.attempts[id(process)]=record
        try:
            # Allocation has no native resources. Once initialization is entered,
            # even _child_created=False cannot exclude an interrupted birth.
            record['birth']='unknown'
            self._mark('process_birth',command=self._where['command'])
            kind.__init__(process,argv,**kwargs)
            record['complete']=True
            self._mark('process_identity',command=self._where['command'])
            try:record['identity']=self._process_identity(process)
            except FileNotFoundError:
                if process.poll() is None:self._reject('CLEANUP')
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
        if not record['complete'] or record['identity'] is None or self._process_identity(process)!=record['identity']:self._reject('CLEANUP')
        os.killpg(process.pid,sig)
    def command(self,argv,*,input=None,clean=False,limit=30,env=None):
        prior=self._where;name=self._command_name(argv)
        self._mark('command_start',command=name)
        try:
            timeout=self.budget.require(new=not clean,ceiling=limit);end=time.monotonic()+timeout
            process=self._spawn(argv,new=not clean,stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,cwd=ROOT,env=env or {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'},start_new_session=True)
            self._mark('command_wait',command=name)
            payload=input
            try:
                while True:
                    self._diag_pump(clean=clean)
                    left=end-time.monotonic()
                    if left<=0:raise subprocess.TimeoutExpired(argv,timeout)
                    try:out,_=process.communicate(payload,timeout=min(.05,left));break
                    except subprocess.TimeoutExpired:payload=None
                self._diag_pump(clean=clean)
            except subprocess.TimeoutExpired as error:
                self._capture(error);self.uncertain=True;self.result['resources']['forced']=True
                self._signal(process,signal.SIGKILL);process.wait(timeout=self.budget.require(ceiling=2));self._reject('CLOCK')
            self.attempts[id(process)]['reaped']=process.returncode is not None
            self._mark('command_result',command=name,command_exit=process.returncode)
            if process.returncode or len(out)>1048576:self._reject('PRECHECK')
            return out
        except BaseException as error:self._capture(error);raise
        finally:self._where=prior
    def _account_record(self,kind,expected_id=None):
        group=kind=='group';name=GROUP if group else USER
        operation='group_record' if group else 'user_record'
        self._mark(operation,account_check='read')
        rows=[tuple(line.split(':')) for line in Path('/etc/group' if group else '/etc/passwd').read_text().splitlines()]
        matches=[row for row in rows if row[0]==name]
        if len(matches)!=1:self._account_reject('record_count')
        row=matches[0]
        if len(row)!=(4 if group else 7):self._account_reject('shape')
        self._mark(operation,account_check='id_format',account_mismatch_mask=4)
        if not row[2].isdecimal() or not 0<int(row[2])<2147483648 or str(int(row[2]))!=row[2]:self._account_reject('id_format',4)
        number=int(row[2])
        if expected_id is not None and number!=expected_id:self._account_reject('id_match',4)
        if sum(len(other)>2 and other[2]==row[2] for other in rows)!=1:self._account_reject('id_unique',4)
        if group:
            if row!=(GROUP,'x',str(number),''):self._account_reject('fields',sum(1<<i for i,(actual,expected) in enumerate(zip(row,(GROUP,'x',str(number),''))) if actual!=expected))
        elif row!=(USER,'x',str(number),str(self.gid),'',str(STATE),'/usr/sbin/nologin'):self._account_reject('fields',sum(1<<i for i,(actual,expected) in enumerate(zip(row,(USER,'x',str(number),str(self.gid),'',str(STATE),'/usr/sbin/nologin'))) if actual!=expected))
        return row
    def _account_absent(self,kind,record):
        self._mark('group_record' if kind=='group' else 'user_record',account_check='absence')
        name=GROUP if kind=='group' else USER
        rows=[line.split(':') for line in Path('/etc/group' if kind=='group' else '/etc/passwd').read_text().splitlines()]
        return not any(row[0]==name or len(row)>2 and row[2]==record[2] for row in rows)
    def _require_account_births(self):
        self._mark('account_cleanup',account_check='birth')
        # A failed command may have changed the account database. Neither the
        # attempt nor a matching name supplies deletion ownership.
        if self.user_attempted and self.user_record is None or self.group_attempted and self.group_record is None:self._reject('CLEANUP')
        if self.group_record is not None and self._account_record('group',self.gid)!=self.group_record:self._reject('CLEANUP')
        if self.user_record is not None and self._account_record('user',self.uid)!=self.user_record:self._reject('CLEANUP')
    def _remove_accounts(self):
        self._require_account_births()
        if self.user_record is not None:
            # Recheck immediately before the name-taking system command.
            if self._account_record('user',self.uid)!=self.user_record:self._reject('CLEANUP')
            self.command(['/usr/sbin/userdel',USER],clean=True,limit=3)
            if not self._account_absent('user',self.user_record):self._reject('CLEANUP')
        if self.group_record is not None:
            # Ubuntu userdel may already remove the matching empty user group.
            # Confirm name AND original GID absent; never delete a replacement.
            if not self._account_absent('group',self.group_record):
                if self._account_record('group',self.gid)!=self.group_record:self._reject('CLEANUP')
                self.command(['/usr/sbin/groupdel',GROUP],clean=True,limit=3)
                if not self._account_absent('group',self.group_record):self._reject('CLEANUP')
    def absent(self,path):
        self._mark('target_absence')
        self.budget.require(new=True)
        if path.exists() or path.is_symlink():self._reject('PRECHECK')
    def directory(self,path,uid=0,gid=0,mode=0o700):
        self._mark('directory_create')
        self.absent(path);self._mark('directory_create');path.mkdir(mode=mode);self.paths.append(path);self._mark('directory_owner');os.chown(path,uid,gid);self._mark('directory_mode');path.chmod(mode)
    def write(self,path,data,uid=0,gid=0,mode=0o600):
        self._mark('file_open')
        self.budget.require(new=True);self.absent(path)
        self._mark('file_open')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
        self.paths.append(path)
        try:
            self._mark('file_write')
            os.fchown(fd,uid,gid);os.fchmod(fd,mode)
            if os.write(fd,data)!=len(data):self._reject('PRECHECK')
            os.fsync(fd)
        except BaseException as error:self._capture(error);raise
        finally:
            self._mark('file_close')
            try:os.close(fd)
            except BaseException as error:self._capture(error);raise
    def preflight(self):
        self._mark('platform')
        if sys.platform!='linux' or os.geteuid()!=0 or os.getuid()!=0 or sys.version_info[:2]!=(3,11) or sys.implementation.name!='cpython' or not sys.flags.isolated or not sys.flags.dont_write_bytecode:self._reject('PRECHECK')
        if os.uname().machine!='x86_64' or Path('/proc/1/comm').read_text().strip()!='systemd':self._reject('PRECHECK')
        os_release=Path('/etc/os-release').read_text()
        if 'ID=ubuntu\n' not in os_release or 'VERSION_ID="24.04"' not in os_release:self._reject('PRECHECK')
        for tool in TOOLS:
            if not Path(tool).is_file():self._reject('PRECHECK')
        self._mark('sdk')
        from importlib.metadata import version
        if any(version(name)!=expected for name,expected in {**SDKS,**IMPORT_SDKS}.items()):self._reject('PRECHECK')
        self._mark('platform')
        if not self.command(['/usr/bin/systemctl','--version']).startswith(b'systemd 255 '):self._reject('PRECHECK')
        for path in (OBSERVATION,WORK,SECRETS,DEPOT,STATE,CACHE,GRANT_DIR,UNIT_FILE,Path('/run/systemd/system')/UNIT,Path('/run/credentials')/UNIT):self.absent(path)
        self._mark('account_absence')
        for path,name in ((Path('/etc/passwd'),USER),(Path('/etc/group'),GROUP)):
            if any(line.split(':',1)[0]==name for line in path.read_text().splitlines()):self._reject('PRECHECK')
        self._mark('checkout')
        if self.command([*GIT,'rev-parse','HEAD']).decode().strip()!=self.meta['head'] or self.command([*GIT,'status','--porcelain','--untracked-files=all']).strip():self._reject('SOURCE')
        self.result['tree']=self.command([*GIT,'rev-parse','HEAD^{tree}']).decode().strip()
    def prepare(self):
        self._phase='prepare';self._mark('group_create')
        self.group_attempted=True;self.command(['/usr/sbin/groupadd','--system',GROUP])
        self.group_record=self._account_record('group');self.gid=int(self.group_record[2]);self.group=True
        self._mark('user_create')
        self.user_attempted=True;self.command(['/usr/sbin/useradd','--system','--gid',GROUP,'--no-create-home','--no-log-init','--home-dir',str(STATE),'--shell','/usr/sbin/nologin',USER])
        self.user_record=self._account_record('user');self.uid=int(self.user_record[2]);self.user=True
        if self._account_record('group',self.gid)!=self.group_record:self._reject('CLEANUP')
        for path in (WORK,STATE,CACHE):self.directory(path,self.uid,self.gid)
        self._diag_create_directory()
        self.directory(STATE/'logs',self.uid,self.gid);self.directory(SECRETS);self.directory(DEPOT,mode=0o755)
        entries=self.command([*GIT,'ls-tree','-r','-z','HEAD']).decode().split('\0');total=0;expected_papers=None;copied_papers=set()
        for entry in entries:
            if not entry:continue
            self._mark('mirror_entry')
            metadata,relative=entry.split('\t');mode,kind,oid=metadata.split()
            if not mirror_selected(relative):continue
            self._mark('mirror_mode')
            if mode not in ('100644','100755') or kind!='blob':self._reject('SOURCE')
            source=ROOT/relative
            self._mark('mirror_link')
            if source.is_symlink() or any(parent.is_symlink() for parent in source.parents if parent!=ROOT and ROOT in parent.parents):self._reject('SOURCE')
            self.budget.require(new=True)
            self._mark('mirror_open')
            descriptor=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
            try:
                self._mark('mirror_metadata')
                before=os.fstat(descriptor)
                if not stat.S_ISREG(before.st_mode) or not 0<=before.st_size<=1048576:self._reject('SOURCE')
                self._mark('mirror_read')
                raw=os.read(descriptor,1048577)
                self._mark('mirror_identity')
                if stat_key(os.fstat(descriptor))!=stat_key(before) or stat_key(source.lstat())!=stat_key(before):self._reject('SOURCE')
            except BaseException as error:self._capture(error);raise
            finally:
                self._mark('mirror_close')
                try:os.close(descriptor)
                except BaseException as error:self._capture(error);raise
            self._mark('mirror_size')
            total+=len(raw)
            if len(raw)>1048576 or total>16777216 or raw.startswith(b'version https://git-lfs.github.com/spec/'):self._reject('SOURCE')
            self._mark('mirror_hash')
            if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=oid:self._reject('SOURCE')
            self._mark('mirror_catalog')
            if relative=='web/frontend/assets/data/papers-manifest.json':expected_papers=catalog_paths(raw)
            if relative.startswith('web/frontend/assets/data/papers/') and relative.endswith('.md'):copied_papers.add(relative)
            target=DEPOT/relative
            for parent in reversed(target.parents):
                if parent==DEPOT or DEPOT not in parent.parents:continue
                if not parent.exists():self.directory(parent,mode=0o755)
            self.write(target,raw,mode=0o644)
        self._mark('mirror_catalog')
        if expected_papers is None or copied_papers!=expected_papers:self._reject('SOURCE')
        if not (DEPOT/'web/frontend/assets').exists():self.directory(DEPOT/'web/frontend/assets',mode=0o755)
        if not (DEPOT/FIXTURE).is_file():self._reject('SOURCE')
        self._mark('secret_prepare')
        import secrets
        values=[secrets.token_urlsafe(48),secrets.token_urlsafe(48),secrets.token_hex(32),secrets.token_urlsafe(48),secrets.token_urlsafe(32)]
        self.password=values[-1]
        for name,value in zip(IDS,values):self.write(SECRETS/name,value.encode())
        self.write(SECRETS/PROVIDER_ID,('synthetic-no-provider-permission-'+uuid4().hex).encode())
        self.command(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=beta.structural.bytedance.city','-addext','subjectAltName=DNS:beta.structural.bytedance.city','-keyout',str(WORK/'local-key.pem'),'-out',str(WORK/'local-cert.pem')],limit=10)
        self._mark('certificate_metadata')
        for path in (WORK/'local-key.pem',WORK/'local-cert.pem'):self.paths.append(path);os.chown(path,self.uid,self.gid);path.chmod(0o400)
        self.command(self.as_user([self.python,'-I','-B',str(DEPOT/FIXTURE),'bootstrap']),env={**self.environment(),'STRUCTURAL_PRIVACY_HMAC_KEY':values[2]})
    def as_user(self,argv):return ['/usr/bin/setpriv','--reuid',str(self.uid),'--regid',str(self.gid),'--clear-groups',*argv]
    def environment(self):
        return {'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(STATE),'STRUCTURAL_ENV':'prod','AUTH_ENABLED':'true','AUTH_DEV_MODE':'false','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':'https://beta.structural.bytedance.city','AUTH_DATA_DIR':str(STATE),'STRUCTURAL_SSO_DATA_DIR':str(STATE),'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','SMTP_HOST':'127.0.0.1','SMTP_PORT':'18025','SMTP_USERNAME':'native-probe','SMTP_FROM_EMAIL':'native-linux-sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'native-linux-admin@example.invalid','SMTP_STARTTLS':'false','SMTP_USE_SSL':'false','SMTP_TIMEOUT_SECONDS':'2'}
    def install_unit(self,provider=False,observed=False):
        self._mark('unit_install')
        self.budget.require(new=True)
        self._diag_open()
        if self.unit_written:
            UNIT_FILE.unlink();self.paths.remove(UNIT_FILE);self.unit_written=False
        command=[self.python,'-I','-B',str(DEPOT/FIXTURE),'observe'] if observed else [self.python,'-I','-B',str(DEPOT/'scripts/run-formal-main.py')]
        if any(any(c in arg for c in ('\n','\r','%','"',' ')) for arg in command):self._reject('SOURCE')
        lines=['[Unit]','Description=Owned disposable native lifecycle probe','[Service]','Type=simple','User='+USER,'Group='+GROUP,'UMask=0077','LimitCORE=0','NoNewPrivileges=yes','PrivateNetwork=yes','TimeoutStartSec=30','TimeoutStopSec=30','KillMode=control-group','Restart=no','WorkingDirectory='+str(DEPOT/'web/backend'),'ExecStart='+' '.join(command),'StandardOutput=null','StandardError=file:'+str(self._diag['path'])]
        for key,value in self.environment().items():lines.append('Environment="'+key+'='+value+'"')
        for name in (*IDS,*((PROVIDER_ID,) if provider else ())):lines.append('LoadCredential='+name+':'+str(SECRETS/name))
        self.write(UNIT_FILE,('\n'.join(lines)+'\n').encode(),mode=0o644);self.unit_written=True
        self._diag_unit_bytes=UNIT_FILE.read_bytes();self._diag_unit_identity=stat_key(UNIT_FILE.lstat())
        self.command(['/usr/bin/systemctl','daemon-reload'])
    def unit_info(self,clean=False,limit=3):
        self._mark('unit_info')
        raw=self.command(['/usr/bin/systemctl','show',UNIT,'--property=MainPID,ControlGroup,InvocationID,ActiveState,Result,ExecMainPID,ExecMainCode,ExecMainStatus,ExecMainStartTimestampMonotonic,ExecMainExitTimestampMonotonic'],clean=clean,limit=limit).decode()
        rows=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
        if set(rows)!= {'MainPID','ControlGroup','InvocationID','ActiveState','Result','ExecMainPID','ExecMainCode','ExecMainStatus','ExecMainStartTimestampMonotonic','ExecMainExitTimestampMonotonic'}:self._reject('UNIT')
        self._diag_note_unit(rows,clean=clean)
        return rows
    def start(self):
        if self._diag is None:
            self._diag_open();self._diag_unit_rotate()
        self._diag['window_start']=time.monotonic()
        self._mark('unit_start')
        self.command(['/usr/bin/systemctl','start',UNIT],limit=15)
        info=self.unit_info();self._mark('unit_isolation');pid=int(info['MainPID'])
        if pid<=1 or info['ControlGroup']!='/system.slice/'+UNIT or not re.fullmatch('[0-9a-f]{32}',info['InvocationID']):self._reject('UNIT')
        if '0::/system.slice/'+UNIT not in Path('/proc/'+str(pid)+'/cgroup').read_text():self._reject('UNIT')
        namespace=os.stat('/proc/'+str(pid)+'/ns/net');host=os.stat('/proc/self/ns/net')
        if (namespace.st_dev,namespace.st_ino)==(host.st_dev,host.st_ino):self._reject('UNIT')
        self.invocations.append((pid,info['InvocationID']));self.result['resources']['unit_invocations']+=1
        # The fresh private netns must have no non-loopback IPv4/IPv6 route.
        routes=Path('/proc/'+str(pid)+'/net/route').read_text().splitlines()[1:]
        if any(line.split()[0]!='lo' for line in routes if line.strip()):self._reject('UNIT')
        if any(line.split()[-1]!='lo' for line in Path('/proc/'+str(pid)+'/net/ipv6_route').read_text().splitlines()):self._reject('UNIT')
        self._mark('credential_metadata')
        directory_identity=self._credential_metadata(pid,info['InvocationID'])
        self.invocations[-1]=(*self.invocations[-1],directory_identity)
        args=['/usr/bin/nsenter','--net=/proc/'+str(pid)+'/ns/net',*self.as_user([self.python,'-I','-B',str(DEPOT/FIXTURE),'serve'])]
        ready_end,work_end=ready_budget(time.monotonic(),self.budget.deadline)
        if work_end<=time.monotonic():
            self._diag['record']['parent_failure']='TIMEOUT';self._diag['record']['deadline_reached']=time.monotonic()>=ready_end
            self._mark('helper_ready',command='helper');self._reject('CLOCK')
        self._mark('helper_start',command='helper')
        self.server=self._spawn(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':str(WORK)},start_new_session=True)
        self._mark('helper_ready',command='helper')
        self.rpc_buffer=b''
        try:self._write_helper(canonical({'password':self.password,'deadline':self.budget.deadline-30,'ready_deadline':ready_end})+b'\n',ready_end)
        except BaseException as error:
            row=self._diag['record']
            if row['parent_failure'] is None:
                row['parent_failure']='TIMEOUT' if type(error) is ValueError and error.args==('TIMEOUT',) else 'IO'
                row['deadline_reached']=time.monotonic()>=ready_end
            self._reject('HTTP')
        self._startup_wait(ready_end)
    def _metadata_close(self,descriptors):
        failed=[]
        for fd in reversed(descriptors):
            try:os.close(fd)
            except BaseException:failed.append(fd)
        if failed:
            self._metadata_uncertain.append(tuple(failed));self.uncertain=True;self._reject('CLEANUP')
    def _metadata_read(self,path,limit):
        descriptors=[]
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);descriptors.append(fd)
            value=os.read(fd,limit+1)
            if not 0<len(value)<=limit:self._reject('UNIT')
            return value
        finally:self._metadata_close(descriptors)
    def _metadata_helper(self):
        import builtins,importlib.util,types
        path=DEPOT/'web/backend/systemd_credential_metadata.py'
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_mode&0o022 or before.st_nlink!=1 or not 0<before.st_size<=65536:self._reject('SOURCE')
        raw=self._metadata_read(path,65536)
        if stat_key(path.lstat())!=stat_key(before):self._reject('SOURCE')
        if hashlib.sha256(raw).digest()!=hashlib.sha256((ROOT/'web/backend/systemd_credential_metadata.py').read_bytes()).digest():self._reject('SOURCE')
        if self._metadata_module is None:
            if 'systemd_credential_metadata' in sys.modules:self._reject('SOURCE')
            spec=importlib.util.spec_from_file_location('systemd_credential_metadata',path)
            module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
            exec(compile(raw,str(path),'exec',dont_inherit=True),vars(module));self._metadata_module=module
        module=self._metadata_module
        if sys.modules.get('systemd_credential_metadata') is not module or module.__file__!=str(path):self._reject('SOURCE')
        trusted_builtins=vars(builtins)
        if vars(module).get('__builtins__') is not trusted_builtins:self._reject('SOURCE')
        expected={'__name__':module.__name__,'__file__':str(path),'__builtins__':trusted_builtins};exec(compile(raw,str(path),'exec',dont_inherit=True),expected)
        names={name for name in expected if not name.startswith('__')}
        if {name for name in vars(module) if not name.startswith('__')}!=names:self._reject('SOURCE')
        for name in names:
            actual,original=vars(module)[name],expected[name]
            if type(original) is types.FunctionType:
                if type(actual) is not types.FunctionType or actual.__globals__ is not vars(module) or actual.__module__!=module.__name__ or actual.__code__!=original.__code__ or actual.__defaults__!=original.__defaults__ or actual.__kwdefaults__!=original.__kwdefaults__ or actual.__builtins__ is not trusted_builtins or actual.__closure__ is not None:self._reject('SOURCE')
            elif type(actual) is not type(original) or (actual is not original if isinstance(original,types.ModuleType) else actual!=original):self._reject('SOURCE')
        return module
    def _consumer_metadata(self,pid,module):
        proc=Path('/proc')/str(pid)
        user=(proc/'ns/user').stat();mount=(proc/'ns/mnt').stat()
        namespaces=(user.st_dev,user.st_ino),(mount.st_dev,mount.st_ino)
        value=module.parse_consumer(self._metadata_read(proc/'status',65536),self._metadata_read(proc/'uid_map',65536),self._metadata_read(proc/'gid_map',65536),self._metadata_read(proc/'stat',65536),pid,*namespaces)
        user=(proc/'ns/user').stat();mount=(proc/'ns/mnt').stat()
        if namespaces!=((user.st_dev,user.st_ino),(mount.st_dev,mount.st_ino)) or value['uid']!=self.uid or value['gid']!=self.gid:raise ValueError('CONSUMER')
        return value
    def _metadata_capture(self,fd,pid,module,consumer):
        if self._consumer_metadata(pid,module)!=consumer:raise ValueError('CONSUMER')
        before=stat_key(os.fstat(fd))
        snapshot=module.capture_fd(fd,self._metadata_read('/proc/self/fdinfo/'+str(fd),4096),self._metadata_read(Path('/proc')/str(pid)/'mountinfo',262144))
        if stat_key(os.fstat(fd))!=before:raise ValueError('IDENTITY')
        if self._consumer_metadata(pid,module)!=consumer:raise ValueError('CONSUMER')
        return snapshot
    def _credential_metadata(self,pid,invocation):
        # Controller observes after unit start; Formal independently gates reads.
        if any(v['phase']==self._phase for v in self.result['credential_metadata']):self._reject('UNIT')
        record=empty_metadata(self._phase);self.result['credential_metadata'].append(record)
        descriptors=[];module=None;directory_snapshot=None;shape=None;fingerprints=[];item=None
        try:
            module=self._metadata_helper();before=self._consumer_metadata(pid,module)
            record['consumer'].update(uid=before['uid'],gid=before['gid'],identity_matches=True,initial_maps=True)
            directory=Path('/proc')/str(pid)/'root/run/credentials'/UNIT
            # The target root magic-link is the already-bound unit namespace;
            # each actual credential component below it is opened nofollow.
            flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC
            parent=os.open(Path('/proc')/str(pid)/'root',os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC);descriptors.append(parent)
            module.validate_snapshot(self._metadata_capture(parent,pid,module,before),'ancestor',self.uid,self.gid)
            for component in ('run','credentials',UNIT):
                child=os.open(component,flags,dir_fd=parent);descriptors.append(child);parent=child
                if component!=UNIT:
                    snapshot=self._metadata_capture(child,pid,module,before)
                    module.validate_snapshot(snapshot,'ancestor',self.uid,self.gid)
            directory_fd=parent
            for index,component in enumerate(('run','credentials',UNIT),1):
                named=os.open(component,flags,dir_fd=descriptors[index-1]);descriptors.append(named)
                if not module.same_snapshot(self._metadata_capture(descriptors[index],pid,module,before),self._metadata_capture(named,pid,module,before)):raise ValueError('IDENTITY')
            ids=(*IDS,*((PROVIDER_ID,) if (SECRETS/PROVIDER_ID).exists() and any('LoadCredential='+PROVIDER_ID+':' in line for line in UNIT_FILE.read_text().splitlines()) else ()))
            for slot in ('DIRECTORY',*ids):
                item=empty_metadata_object(slot);record['objects'].append(item)
                role='directory' if slot=='DIRECTORY' else 'file'
                fd=directory_fd if slot=='DIRECTORY' else os.open(slot,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=directory_fd)
                if slot!='DIRECTORY':descriptors.append(fd)
                info=os.fstat(fd)
                item.update(kind='directory' if stat.S_ISDIR(info.st_mode) else 'regular' if stat.S_ISREG(info.st_mode) else 'other',uid=info.st_uid,gid=info.st_gid,mode=stat.S_IMODE(info.st_mode),nlink=info.st_nlink,legacy_owner_only=(info.st_uid==self.uid and stat.S_IMODE(info.st_mode)==(0o500 if role=='directory' else 0o400) and (role=='directory' or stat.S_ISREG(info.st_mode) and info.st_nlink==1)))
                snapshot=self._metadata_capture(fd,pid,module,before)
                for key in ('access','default'):
                    value=snapshot[key];item[key]={'state':value[0],'entries':[list(row) for row in value[1]],'count':value[2]}
                item['readonly']=snapshot['readonly']
                named=os.open(UNIT if role=='directory' else slot,flags if role=='directory' else os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=descriptors[2] if role=='directory' else directory_fd);descriptors.append(named)
                named_snapshot=self._metadata_capture(named,pid,module,before)
                item['held_named_same']=module.same_snapshot(snapshot,named_snapshot)
                if not item['held_named_same']:raise ValueError('IDENTITY')
                # Use the unit consumer's view, never host/self mountinfo.
                module.mount_matches(self._metadata_read(Path('/proc')/str(pid)/'mountinfo',262144),snapshot['mount_id']);item['mount_matches']=True
                selected=module.validate_snapshot(snapshot,role,self.uid,self.gid)
                if shape is None:shape=selected;directory_snapshot=snapshot
                if selected!=shape or snapshot['mount_id']!=directory_snapshot['mount_id']:raise ValueError('MOUNT_ID')
                item['decision']=selected;fingerprints.append((fd,UNIT if role=='directory' else slot,descriptors[2] if role=='directory' else directory_fd,snapshot,item,role))
            for fd,name,parent,expected,item,role in fingerprints:
                current=self._metadata_capture(fd,pid,module,before)
                named=os.open(name,flags if role=='directory' else os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=parent);descriptors.append(named)
                named_snapshot=self._metadata_capture(named,pid,module,before)
                if not module.same_snapshot(expected,current) or not module.same_snapshot(current,named_snapshot):raise ValueError('IDENTITY')
                module.mount_matches(self._metadata_read(Path('/proc')/str(pid)/'mountinfo',262144),current['mount_id'])
            for index,component in enumerate(('run','credentials',UNIT),1):
                named=os.open(component,flags,dir_fd=descriptors[index-1]);descriptors.append(named)
                if not module.same_snapshot(self._metadata_capture(descriptors[index],pid,module,before),self._metadata_capture(named,pid,module,before)):raise ValueError('IDENTITY')
            after=self._consumer_metadata(pid,module)
            record['consumer']['namespace_stable']=before['user_ns']==after['user_ns'] and before['mount_ns']==after['mount_ns']
            current=self.unit_info();self._mark('credential_metadata')
            record['consumer']['instance_stable']=before==after and current['MainPID']==str(pid) and current['InvocationID']==invocation
            if not all(v is True for k,v in record['consumer'].items() if k not in ('uid','gid')):raise ValueError('CONSUMER')
            record['decision']=shape
            return directory_snapshot['dev'],directory_snapshot['ino']
        except BaseException as error:
            check='PROCESS_GONE' if isinstance(error,FileNotFoundError) else error.args[0] if type(error) is ValueError and len(error.args)==1 and error.args[0] in METADATA_CHECKS else 'IO'
            record['check']=check;record['decision']='UNKNOWN' if check in ('PROCESS_GONE','IO') else 'REJECT'
            if item is not None:item.update(check=check,decision=record['decision'])
            self._mark('credential_metadata');self._reject('UNIT')
        finally:self._metadata_close(descriptors)
    def read_line(self):
        end=time.monotonic()+self.budget.require(new=True,ceiling=10)
        while b'\n' not in self.rpc_buffer:
            if not self._wait_io([self.server.stdout],[],end)[0]:self._reject('HTTP')
            raw=os.read(self.server.stdout.fileno(),65536)
            if not raw or len(self.rpc_buffer)+len(raw)>65536:self._reject('HTTP')
            self.rpc_buffer+=raw
        line,self.rpc_buffer=self.rpc_buffer.split(b'\n',1);return line
    def exercise(self,rid,approve=False):
        self._mark('exercise')
        self._write_helper(canonical({'rid':rid,'approve':approve})+b'\n',self.budget.deadline-30);value=strict_json(self.read_line(),65536)
        if type(value) is not dict or set(value)!= {'rid','identity_digest','native_ready'} or not re.fullmatch('[0-9a-f-]{36}',value['rid']) or not re.fullmatch('[0-9a-f]{64}',value['identity_digest']) or type(value['native_ready']) is not bool:self._reject('HTTP')
        return value
    def stop(self):
        self._mark('stop')
        self.command(['/usr/bin/systemctl','stop',UNIT],clean=True,limit=30)
        info=self.unit_info(clean=True)
        if self._diag is not None:self._diag['record']['unit_after']=unit_diagnostic(info,self._diag_unit_expected(),time.monotonic())
        if info['MainPID']!='0' or info['ActiveState']!='inactive' or info['Result']!='success' or info['ExecMainStatus']!='0':
            self.uncertain=True
            if info['Result']=='timeout':self.result['resources']['forced']=True
            self._reject('UNIT')
        if self._diag is not None and self._diag['record']['parent_failure']=='BINDING_UNPROVED':self._mark('ready_diagnostics');self._reject('UNIT')
        self.result['resources']['unit_exited']+=1
        group=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
        if group.exists() and group.read_text().strip():self._reject('CLEANUP')
        self.result['resources']['cgroup_empty']=True
        self._diag_retire(True)
        if self.server is not None:
            self.server.stdin.close();self._wait_process(self.server,self.budget.require(ceiling=4),clean=True)
            row=self.result['startup_diagnostics'].get(self._phase)
            if row is not None:row['helper_returncode']=self.server.returncode
            if self.server.returncode!=0:self.uncertain=True;self._reject('CLEANUP')
            self.server=None
        if (Path('/run/credentials')/UNIT).exists():self._reject('CLEANUP')
        self.result['resources']['credential_mount_gone']=True
    def facts(self):
        self._mark('facts')
        if self.unit_info(clean=True)['MainPID']!='0':self._reject('FACTS')
        self._mark('facts')
        # A stopped, fully checkpointed specimen only. A root-owned reader must
        # not create root-owned WAL/SHM files or silently ignore a remaining WAL.
        database=STATE/'auth.sqlite3'
        if any(Path(str(database)+suffix).exists() for suffix in ('-wal','-shm','-journal')):self._reject('FACTS')
        conn=sqlite3.connect(database.as_uri()+'?mode=ro&immutable=1',uri=True,timeout=0)
        try:
            conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON');conn.execute('BEGIN')
            if conn.execute('SELECT version FROM research_schema').fetchone()[0]!=15:self._reject('FACTS')
            principals=conn.execute("SELECT * FROM research_principals WHERE status='active'").fetchall()
            if len(principals)!=1:self._reject('FACTS')
            p=dict(principals[0]);receipt=conn.execute("SELECT * FROM auth_registration_receipts WHERE gate_id=? AND kind='gate_resource'",(p['gate_id'],)).fetchone()
            if receipt is None:self._reject('FACTS')
            tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE 'research_funding_%' OR name LIKE 'research_plan_native_%' OR name IN ('research_reservations','research_attempts','research_plan_dispatches')) ORDER BY name")]
            ledger={table:[dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY rowid')] for table in tables}
            if conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0]:self._reject('FACTS')
            conn.rollback()
        except BaseException as error:self._capture(error);raise
        finally:
            self._mark('facts_close')
            try:conn.close()
            except BaseException as error:self._capture(error);raise
        self._mark('facts')
        db=(STATE/'auth.sqlite3').stat();gate=(STATE/'research-locks'/(p['gate_id']+'.lock')).stat()
        if (receipt['lock_dev'],receipt['lock_ino'])!=(gate.st_dev,gate.st_ino):self._reject('FACTS')
        return p,ledger,[db.st_dev,db.st_ino],[gate.st_dev,gate.st_ino,gate.st_uid,stat.S_IMODE(gate.st_mode),gate.st_nlink]
    def grant(self,principal,db,gate):
        self._mark('grant')
        self.directory(GRANT_DIR,0,self.gid,0o750)
        flight=STATE/'native-plan-flight.lock';self.write(flight,b'',self.uid,self.gid);f=flight.stat()
        self._mark('grant')
        # Pure production exporters; no witness, session or authority is made.
        code="import sys,json;sys.path[:0]=["+repr(str(DEPOT/'web/backend'))+","+repr(str(DEPOT))+"];from research.native_live_grant import fixed_purpose_domains,approved_code_digest;print(json.dumps([fixed_purpose_domains(),approved_code_digest()]))"
        domains,code_digest=strict_json(self.command(self.as_user([self.python,'-I','-B','-c',code])),32768)
        self.result['code_digest']=code_digest
        grant={'protocol':'native-live-owner-grant-v1','project_ref':'structure-rebuild-v1','state':'active','grant_id':str(uuid4()),'grant_epoch':1,'principal_id':principal['id'],'auth_generation':principal['session_generation'],'principal_epoch':principal['epoch'],'owner_gate_id':principal['gate_id'],'database_identity':db,'owner_gate_identity':gate,'flight_identity':[f.st_dev,f.st_ino,f.st_uid,f.st_gid,stat.S_IMODE(f.st_mode),f.st_nlink],'account_id':str(uuid4()),'economic_binding':str(uuid4()),'credential_incarnation':'synthetic-'+uuid4().hex,'approved_cap_units':300000000,'risk_margin_units':2129920,'runtime_uid':self.uid,'runtime_gid':self.gid,'provider':'deepseek','model':'deepseek-flash','network_policy':'deepseek-fixed-https-v1','runtime_digest':hashlib.sha256((DEPOT/'web/backend/services/plan_runtime_transport.py').read_bytes()).hexdigest(),'approved_code_digest':code_digest,'purpose_domains':domains}
        self.write(GRANT_DIR/'native-live-grant.json',canonical(grant),0,self.gid,0o440)
    def events(self):
        self._mark('events')
        p=WORK/'observed.jsonl'
        if not p.exists():return []
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=self.uid or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:self._reject('OBSERVER')
            raw=os.read(fd,32769)
        except BaseException as error:self._capture(error);raise
        finally:
            try:os.close(fd)
            except BaseException as error:self._capture(error);raise
        if len(raw)>32768:self._reject('OBSERVER')
        # A concurrent append may be incomplete; parse only complete frames.
        values=[strict_json(line[:-1],2048) for line in raw.splitlines(keepends=True) if line.endswith(b'\n')]
        fields={'SLOT_BEFORE_GET':set(),'SLOT_WOKEN':{'elapsed_ms'},'PROOF_TAKEN':set(),'SOURCE_JOIN':{'closed'},'NATIVE_JOIN':{'closed'},'FINAL':set(self.result['instrumented']),'OBSERVER_FAILED':set(),'NETWORK_ENTRY':set()}
        for item in values:
            if type(item) is not dict or set(item)!= {'event','values'} or item['event'] not in fields or type(item['values']) is not dict or set(item['values'])!=fields[item['event']] or any(type(v) not in (int,bool,type(None)) for v in item['values'].values()):self._reject('OBSERVER')
        if any(sum(v['event']==event for v in values)>1 for event in fields):self._reject('OBSERVER')
        return values
    def run(self):
        self.preflight();self.prepare();self._phase='stock_base';self.install_unit();self.start();first=self.exercise(None)
        if first['native_ready']:self._reject('FACTS')
        self.stop();principal,ledger,db,gate=self.facts()
        if any(ledger.values()):self._reject('FACTS')
        self.result['financial']['initial_empty']=True;self.result['phases']['stock_base']=True
        self._phase='stock_genesis'
        self.grant(principal,db,gate);self.install_unit(provider=True);self.start();second=self.exercise(first['rid'])
        if not second['native_ready'] or first['identity_digest']!=second['identity_digest']:self._reject('FACTS')
        self.stop();_,before,db2,gate2=self.facts()
        if db2!=db or gate2!=gate or len(before['research_plan_native_funding'])!=1 or len(before['research_funding_accounts'])!=1:self._reject('FACTS')
        self.result['phases']['stock_genesis']=True
        self._phase='stock_restart'
        self.start();third=self.exercise(first['rid'])
        if not third['native_ready'] or third['identity_digest']!=first['identity_digest']:self._reject('FACTS')
        self.stop();_,after,db3,gate3=self.facts()
        if after!=before or db3!=db or gate3!=gate or after['research_plan_native_funding'][0]['state']!='authorized':self._reject('FACTS')
        self.result['phases']['stock_restart']=True;self.result['stock']['clean_exit_inferred']=True;self.result['financial']['normal_restart_unchanged']=True
        self.result['stock']['credential_invocation_changed']=self.invocations[-1][2]!=self.invocations[-2][2]
        self._phase='instrumented'
        self.write(WORK/'observer.json',canonical({'head':self.meta['head'],'deadline':self.budget.deadline-30}),self.uid,self.gid,0o400)
        self.install_unit(provider=True,observed=True);self.start();observed=self.exercise(first['rid'],True)
        if observed['identity_digest']!=first['identity_digest'] or not observed['native_ready']:self._reject('FACTS')
        while not any(v['event']=='SLOT_BEFORE_GET' for v in self.events()):self.budget.require(new=True);time.sleep(.02)
        self.stop();final=next((v['values'] for v in self.events() if v['event']=='FINAL'),None)
        if final is None or set(final)!=set(self.result['instrumented']):self._reject('OBSERVER')
        self.result['instrumented']=final
        if not all(final[k] for k in ('source_closed','native_closed','proof_taken','component_woken','same_deadline_ref','within_main_deadline')) or final['observer_failed']:self._reject('OBSERVER')
        _,last,_,_=self.facts();run=last['research_plan_native_runs'];account=last['research_funding_accounts'][0]
        if len(run)!=1 or (run[0]['state'],run[0]['cost_state'])!=('closed','unreserved') or last['research_plan_native_funding'][0]['balance_claim'] is not None or any(account[k] for k in ('held','upper_booked','settled')):self._reject('FACTS')
        self.result['financial'].update(pre_get_closed_unreserved=True,held=account['held'],upper_booked=account['upper_booked'],settled=account['settled'])
        self.result['phases']['instrumented']=True
    def cleanup(self):
        self._phase='cleanup';self._mark('cleanup_summary')
        failed=self.uncertain;actors_retired=True
        if not self.paths and not self.children and not self.group_attempted and not self.user_attempted:
            self.result['resources']['cleanup_uncertain']=False
            return
        if self.unit_written:
            self._mark('unit_cleanup')
            try:
                self.command(['/usr/bin/systemctl','stop',UNIT],clean=True,limit=25)
                final_info=self.unit_info(clean=True)
                if self._diag is not None:self._diag['record']['unit_after']=unit_diagnostic(final_info,self._diag_unit_expected(),time.monotonic())
                if final_info['MainPID']!='0':self._reject('CLEANUP')
                cg=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
                if cg.exists() and cg.read_text().strip():self._reject('CLEANUP')
                self.result['resources']['cgroup_empty']=True
            except BaseException as error:
                self._capture(error);failed=True;actors_retired=False;self.result['resources']['forced']=True
                try:
                    self.command(['/usr/bin/systemctl','kill','--kill-whom=all','--signal=KILL',UNIT],clean=True,limit=2)
                    cg=Path('/sys/fs/cgroup/system.slice')/UNIT/'cgroup.procs'
                    actors_retired=self.unit_info(clean=True)['MainPID']=='0' and (not cg.exists() or not cg.read_text().strip())
                except BaseException as error:self._capture(error)
        for p in list(self.children):
            self._mark('process_cleanup')
            record=self.attempts.get(id(p))
            if record is None or not record['complete']:
                self._capture();failed=True;actors_retired=False
                continue
            try:
                if p.poll() is None:
                    try:
                        if p is self.server and p.stdin:p.stdin.close()
                        else:self._signal(p,signal.SIGTERM)
                        self._wait_process(p,self.budget.require(ceiling=3),clean=True)
                    except BaseException as error:
                        self._capture(error);failed=True;self.result['resources']['forced']=True
                        self._signal(p,signal.SIGKILL);p.wait(timeout=self.budget.require(ceiling=2))
                record['reaped']=p.poll() is not None
                if p is self.server:
                    for row in self.result['startup_diagnostics'].values():
                        if row is not None and row['helper_returncode'] is None:row['helper_returncode']=p.returncode
                    if p.returncode!=0:self._diag_uncertain();failed=True
                # This is an existence query only. If the leader has gone but
                # a group remains, do not signal a group with unproved identity.
                self._mark('process_group')
                try:os.killpg(p.pid,0)
                except ProcessLookupError:pass
                else:self._capture();failed=True;actors_retired=False
                if not record['reaped']:self._capture();actors_retired=False
                self._mark('process_cleanup')
                for stream in (p.stdin,p.stdout,p.stderr):
                    if stream is not None and not stream.closed:stream.close()
            except BaseException as error:
                self._capture(error);failed=True;actors_retired=False
        try:
            if not actors_retired:
                self._diag_uncertain();self._reject('CLEANUP')
            self._diag_retire(actors_retired);self._diag_close_directory()
            if self.result['diagnostic_resources']['uncertain']:failed=True
            self._require_account_births()
            self._mark('unit_cleanup')
            if self.unit_written:
                UNIT_FILE.unlink();self.paths.remove(UNIT_FILE);self.command(['/usr/bin/systemctl','daemon-reload'],clean=True,limit=3);self.unit_written=False
            self.result['resources']['unit_removed']=not UNIT_FILE.exists()
            if (Path('/run/credentials')/UNIT).exists():self._reject('CLEANUP')
            self.result['resources']['credential_mount_gone']=True
            self._mark('directory_cleanup')
            for top in (DEPOT,WORK,SECRETS,STATE,CACHE,GRANT_DIR):
                if top in self.paths:shutil.rmtree(top)
            self.result['resources']['directories_removed']=all(not p.exists() for p in (OBSERVATION,DEPOT,WORK,SECRETS,STATE,CACHE,GRANT_DIR))
            if not self.result['resources']['directories_removed']:self._reject('CLEANUP')
            self._remove_accounts()
            self.result['resources']['user_removed']=True
        except BaseException as error:self._capture(error);failed=True
        failed=failed or self.uncertain
        self.result['resources'].update(children_started=len(self.children),children_reaped=sum(self.attempts[id(p)]['reaped'] for p in self.children if id(p) in self.attempts),cleanup_uncertain=failed)
        if failed:
            self.result['outcome']='FAIL'
            failure=self.result['first_failure']
            if failure is None or failure['phase']=='cleanup':self.result['reason']='CLEANUP'


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
    except ProbeFailure as error:controller._capture(error);controller.result['reason']=controller._first_reason or error.reason;controller._diag_failure_snapshot()
    except BaseException as error:controller._capture(error);controller.result['reason']=controller._first_reason or 'INTERNAL';controller._diag_failure_snapshot()
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
