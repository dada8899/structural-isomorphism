"""Stdlib-only approved material comparison. Never observes-to-approve or loads keys."""
import hashlib,json,os,re,sqlite3,stat
from pathlib import Path
from uuid import uuid4
MANIFEST=Path('/etc/structural/external-first-answer-deployment.json')
MANIFEST_SHA=Path('/etc/structural/external-first-answer-deployment.sha256')
APPROVAL=Path('/etc/structural/external-first-answer-startup.json')
PRICE=Path('/etc/structural/external-first-answer-price-basis.json')
DB=Path('/var/lib/structural-isomorphism/auth.sqlite3')
SIGNER_UNIT='structural-external-startup-material.service'
SIGNER_ID='structural-external-first-answer-startup-signing-key'
SIGNER_DIRECTORY=Path('/run/credentials')/SIGNER_UNIT
H=re.compile('[a-f0-9]{64}')
class MaterialError(ValueError):pass
def need(v,code):
 if not v:raise MaterialError(code)
def canonical(d):return (json.dumps(d,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def parse(raw):
 def unique(pairs):
  d={}
  for k,v in pairs:need(k not in d,'duplicate_material_key');d[k]=v
  return d
 return json.loads(raw,object_pairs_hook=unique)
def fixed_file(path,limit,*,mode=None):
 need(path.is_absolute() and path.resolve(strict=True)==path,'material_path')
 for parent in path.parents:
  s=parent.stat(follow_symlinks=False);need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o022,'material_parent')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
 with os.fdopen(fd,'rb') as f:
  a=os.fstat(f.fileno());need(stat.S_ISREG(a.st_mode) and a.st_uid==0 and a.st_nlink==1 and not a.st_mode&0o022
   and 0<a.st_size<=limit and (mode is None or stat.S_IMODE(a.st_mode)==mode),'material_metadata')
  raw=f.read(limit+1);b=os.fstat(f.fileno());c=path.stat(follow_symlinks=False);key=lambda z:(z.st_dev,z.st_ino,z.st_size,z.st_mode,z.st_uid,z.st_mtime_ns,z.st_ctime_ns)
  need(len(raw)==a.st_size and key(a)==key(b)==key(c),'material_changed');return raw

def approved_manifest(raw,pin):
 need(type(raw) is bytes and len(raw)<=8*1024**2 and type(pin) is str and H.fullmatch(pin) and sha(raw)==pin,'deployment_pair_mismatch')
 d=parse(raw)
 need(type(d) is dict and set(d)=={'schema','reviewer_public_key_hex','approval_template','files','purpose_snapshot','price_ceiling_sha256','runtime_root','interpreter','signature_origins'}
  and d['schema']=='external-live-approved-deployment-v1' and H.fullmatch(d['reviewer_public_key_hex'])
  and H.fullmatch(d['price_ceiling_sha256']),'deployment_shape')
 t=d['approval_template'];need(type(t) is dict and type(t.get('binding')) is dict and t['binding'].get('schema_version')==18,'deployment_binding')
 need(not {'approval_id','issued_at','expires_at'}&set(t) and 'startup_id' not in t['binding'],'deployment_contains_dynamic_startup')
 source=t['binding'].get('source_commit');need(type(source) is str and re.fullmatch('[a-f0-9]{40}',source),'deployment_source')
 need(type(d['files']) is dict and 0<len(d['files'])<=40000 and type(d['signature_origins']) is dict
  and set(d['signature_origins'])=={'cryptography','cffi','_cffi_backend','pycparser'},'deployment_files')
 need(type(d['runtime_root']) is str and d['runtime_root'].startswith('/srv/structural-isomorphism/runtimes/')
  and d['runtime_root'] not in ('/srv/structural-isomorphism/runtimes/','/'),'deployment_runtime_root')
 need(all(path in d['files'] and Path(path).is_relative_to(Path(d['runtime_root'])) for path in d['signature_origins'].values()) and d['interpreter'] in d['files'],'deployment_signature_closure')
 for name,row in d['files'].items():
  path=Path(name)
  allowed=(path.is_relative_to(Path('/srv/structural-isomorphism/releases')/source)
   or path.is_relative_to(Path(d['runtime_root'])) or path==Path(d['interpreter'])
   or name in ('/etc/systemd/system/structural-web.service','/etc/ssl/certs/ca-certificates.crt',
     '/etc/structural/external-first-answer-source.json','/etc/structural/external-first-answer-economic-binding.json'))
  need(path.is_absolute() and '..' not in path.parts and allowed and not any(x.startswith('.env') or x in ('credentials','credstore.encrypted','api_keys.jsonl') for x in path.parts)
   and not '/web/backend/data/' in name,'deployment_file_scope')
  need(type(row) is dict and set(row)=={'sha256','bytes','mode','uid','gid'} and H.fullmatch(row['sha256'])
   and type(row['bytes']) is int and 0<row['bytes']<=512*1024**2 and row['uid']==0
   and type(row['mode']) is int and not row['mode']&0o7022,'deployment_file_spec')
 required=('/etc/systemd/system/structural-web.service','/etc/ssl/certs/ca-certificates.crt',
  '/etc/structural/external-first-answer-source.json','/etc/structural/external-first-answer-economic-binding.json')
 need(all(n in d['files'] for n in required),'deployment_fixed_materials_missing')
 need(d['files'][required[0]]['sha256']==t['binding'].get('unit_digest')
  and d['files'][required[2]]['sha256']==t['binding'].get('source_manifest_digest'),'deployment_binding_material_mismatch')
 runtime_checks=sorted((name,row['sha256']) for name,row in d['files'].items()
  if Path(name).is_relative_to(Path(d['runtime_root'])) or name==d['interpreter'])
 need(sha(json.dumps(runtime_checks,separators=(',',':'),ensure_ascii=False).encode())==t['binding'].get('runtime_closure_digest'),'deployment_runtime_material_mismatch')
 return d

def verify_expected_files(d,reader=fixed_file):
 for name,row in d['files'].items():
  # Expected hashes are approved input, not values learned from this read.
  raw=reader(Path(name),row['bytes'],mode=row['mode'])
  need(len(raw)==row['bytes'] and sha(raw)==row['sha256'],'approved_deployment_changed')
  meta=Path(name).stat(follow_symlinks=False)
  need(meta.st_uid==row['uid'] and meta.st_gid==row['gid'],'approved_deployment_owner_changed')
 source_path=Path('/etc/structural/external-first-answer-source.json')
 source=parse(reader(source_path,d['files'][str(source_path)]['bytes'],mode=d['files'][str(source_path)]['mode']))
 binding=d['approval_template']['binding']
 need(source.get('schema')=='formal-main-source-payload-v1' and source.get('source_sha')==binding['source_commit'],'approved_source_manifest_identity')
 seen=set();base=Path('/srv/structural-isomorphism/releases')/binding['source_commit']
 for row in source.get('members',[]):
  name=row['path'];rel=Path(name)
  need(not rel.is_absolute() and '..' not in rel.parts and name not in seen,'approved_source_member');seen.add(name)
  expected=d['files'].get(str(base/rel))
  need(expected is not None and expected['sha256']==row['sha256'] and expected['bytes']==row['bytes'],'approved_source_member_not_closed')
 need(bool(seen),'approved_source_members_missing')
 return d

def verify_purpose(d,conn):
 need(conn.in_transaction,'purpose_snapshot_transaction')
 need(conn.execute('SELECT id,version FROM main.research_schema').fetchall()==[(1,18)],'purpose_schema')
 wanted=d['purpose_snapshot'];need(type(wanted) is dict and wanted.get('status')=='active','purpose_expected_active')
 columns=('id','purpose','account_id','local_binding_ref','owner_principal','owner_generation','owner_gate_id','credential_source',
  'credential_incarnation','authorization_event_ref','payer_identity_status','payer_id','project_cap','single_upper','funding_epoch','status','version')
 row=conn.execute('SELECT '+','.join(columns)+' FROM main.research_external_owner_funding WHERE id=1').fetchone()
 need(row is not None and dict(zip(columns,row))==wanted,'purpose_binding_changed')
 binding=d['approval_template']['binding']
 compare={'account_id':'account_id','local_binding_ref':'economic_binding','owner_principal':'owner_principal',
  'owner_generation':'owner_generation','owner_gate_id':'owner_gate_id','credential_source':'credential_source',
  'credential_incarnation':'credential_incarnation','authorization_event_ref':'authorization_event_ref',
  'payer_identity_status':'payer_identity_status','payer_id':'payer_id','funding_epoch':'funding_epoch'}
 need(all(wanted.get(a)==binding.get(b) for a,b in compare.items()),'approved_purpose_binding_mismatch')
 account=conn.execute('''SELECT a.id,a.binding_id,a.funding_epoch,a.mode,a.provider,a.currency,a.scale,a.status,a.cap,
 p.epoch,p.status,p.session_generation,p.gate_id,u.lifecycle,u.session_generation
 FROM main.research_funding_accounts a JOIN main.research_external_owner_funding f ON f.account_id=a.id
 JOIN main.research_principals p ON p.id=f.owner_principal JOIN main.auth_users u ON u.email=p.normalized_email WHERE f.id=1''').fetchone()
 expected=(binding['account_id'],binding['economic_binding'],binding['funding_epoch'],'live','deepseek','CNY',6,'unverified',0,
  binding['owner_epoch'],'active',binding['owner_generation'],binding['owner_gate_id'],'active',binding['owner_generation'])
 need(account is not None and tuple(account)==expected,'purpose_owner_or_account_changed')
 need(tuple(conn.execute('PRAGMA database_list')) and any(row[1]=='main' for row in conn.execute('PRAGMA database_list')),'purpose_database')

def fresh_payload(d,*,now,startup_id=None,approval_id=None):
 need(type(now) is int and now>0,'startup_time')
 t=json.loads(json.dumps(d['approval_template']))
 t['binding']['startup_id']=startup_id or str(uuid4());t.update(approval_id=approval_id or str(uuid4()),issued_at=now,expires_at=now+120)
 return t

def load_approved_pair():
 raw=fixed_file(MANIFEST,8*1024**2,mode=0o600);pin=fixed_file(MANIFEST_SHA,65,mode=0o600).decode('ascii').strip()
 return approved_manifest(raw,pin)

def replace_root_material(path,raw):
 """Atomic single-file generation, owner/mode before rename, fsync parent."""
 need(path in (APPROVAL,PRICE) and len(raw)<=65536,'material_output_scope')
 parent=path.parent;need(parent.resolve(strict=True)==parent,'material_output_parent')
 for p in (parent,*parent.parents):
  s=p.stat(follow_symlinks=False);need(s.st_uid==0 and stat.S_ISDIR(s.st_mode) and not s.st_mode&0o022,'material_output_owner')
 tmp=parent/('.'+path.name+'.'+str(uuid4()))
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
 try:
  with os.fdopen(fd,'wb') as f:
   os.fchown(f.fileno(),0,976);os.fchmod(f.fileno(),0o640)
   f.write(raw);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)
  directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:
  if tmp.exists():tmp.unlink()
