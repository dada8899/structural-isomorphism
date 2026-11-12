#!/usr/bin/env python3
"""Fixed Root material maintenance only. No provider completion/balance requests.

Missing approved input is a durable CLOSED preparation result, not a swallowed
failure. Failure to invalidate/publish is nonzero. No arbitrary paths/approve.
"""
import importlib.util,json,os,re,sqlite3,ssl,stat,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 path=ROOT/'web/backend/services'/name
 spec=importlib.util.spec_from_file_location('_root_'+name.replace('.','_'),path)
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
materials=load('external_startup_materials.py')
prices=load('external_price_materials.py')

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise materials.MaterialError('official_price_redirect')
def fetch_official(d):
 path='/etc/ssl/certs/ca-certificates.crt';row=d['files'].get(path)
 materials.need(row is not None,'approved_CA_missing')
 ca=materials.fixed_file(Path(path),row['bytes'],mode=row['mode'])
 materials.need(materials.sha(ca)==row['sha256'],'approved_CA_changed')
 context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);context.minimum_version=ssl.TLSVersion.TLSv1_2
 context.load_verify_locations(cadata=ca.decode('ascii'))
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context),NoRedirect())
 request=urllib.request.Request(prices.URL,headers={'Accept':'text/html','Accept-Encoding':'identity'})
 with opener.open(request,timeout=10) as response:
  materials.need(response.status==200 and response.url==prices.URL,'official_price_response')
  raw=response.read(prices.MAX_DOCUMENT+1)
 materials.need(len(raw)<=prices.MAX_DOCUMENT,'official_price_bound');return raw

def refresh_price():
 # A new unsupported/over-ceiling observation must never leave old validity.
 try:
  d=materials.load_approved_pair();materials.need(d['price_ceiling_sha256']==prices.ceiling_digest(),'approved_price_ceiling')
  raw=fetch_official(d);observed=prices.observe_document(raw,now=int(time.time()))
  materials.replace_root_material(materials.PRICE,prices.canonical(observed))
  return {'status':'PRICE_VALID' if observed['status']=='valid' else 'EXTERNAL_CLOSED_PRICE_OVER_CEILING'}
 except (FileNotFoundError,materials.MaterialError,prices.MaterialError,UnicodeError,ValueError):
  materials.replace_root_material(materials.PRICE,prices.canonical(prices.closed_material('observation_failed',now=int(time.time()))))
  return {'status':'EXTERNAL_CLOSED_PRICE_MATERIAL'}
 # Transport/OS failures are real failed jobs. The caller does not mask them;
 # old proof can live only until its original <=24h expiry, never extended.

def read_signer_seed():
 materials.need(os.environ.get('CREDENTIALS_DIRECTORY')==str(materials.SIGNER_DIRECTORY),'root_signer_credential_directory')
 directory=materials.SIGNER_DIRECTORY
 for path in (directory,*directory.parents):
  info=path.stat(follow_symlinks=False)
  materials.need(path.resolve(strict=True)==path and stat.S_ISDIR(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,'root_signer_parent')
 materials.need(stat.S_IMODE(directory.stat().st_mode)==0o700 and os.statvfs(directory).f_flag&os.ST_RDONLY,'root_signer_private_readonly')
 path=directory/materials.SIGNER_ID
 raw=materials.fixed_file(path,32,mode=0o400);materials.need(len(raw)==32,'root_signer_seed_format')
 return bytearray(raw)

def compare_current_purpose(d):
 # Metadata only, on the canonical DB. Never SELECT questions, candidates,
 # private records, key material or arbitrary tables.
 path=materials.DB
 info=path.stat(follow_symlinks=False);binding=d['approval_template']['binding']
 materials.need(path.resolve(strict=True)==path and stat.S_ISREG(info.st_mode) and info.st_uid==981 and info.st_nlink==1
  and [info.st_dev,info.st_ino]==[binding['database_dev'],binding['database_ino']],'approved_database_identity_changed')
 conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None,timeout=.5)
 try:conn.execute('BEGIN');materials.verify_purpose(d,conn);conn.rollback()
 finally:conn.close()

def verify_signing_source_root(d):
 source=d['approval_template']['binding']['source_commit']
 approved=Path('/srv/structural-isomorphism/releases')/source
 materials.need(ROOT==approved and ROOT.resolve(strict=True)==approved,'signer_current_release_mismatch')
 materials.need(Path(__file__).resolve(strict=True)==approved/'scripts/maintain-external-live-materials.py'
  and Path(materials.__file__).resolve(strict=True)==approved/'web/backend/services/external_startup_materials.py'
  and Path(prices.__file__).resolve(strict=True)==approved/'web/backend/services/external_price_materials.py','signer_actual_source_origin')
 required=('scripts/maintain-external-live-materials.py','web/backend/services/external_startup_materials.py',
  'web/backend/services/external_price_materials.py')
 manifest_path=Path('/etc/structural/external-first-answer-source.json')
 row=d['files'].get(str(manifest_path));materials.need(row is not None,'signer_source_manifest_missing')
 raw=materials.fixed_file(manifest_path,row['bytes'],mode=row['mode'])
 materials.need(materials.sha(raw)==d['approval_template']['binding']['source_manifest_digest'],'signer_source_manifest_hash')
 doc=materials.parse(raw);materials.need(doc.get('source_sha')==source,'signer_source_manifest_identity')
 members={r['path']:r for r in doc.get('members',[])}
 materials.need(len(members)==len(doc.get('members',[])),'signer_source_duplicate')
 for name in required:
  path=approved/name;expected=d['files'].get(str(path));member=members.get(name)
  materials.need(expected is not None and member is not None and expected['sha256']==member['sha256']
   and expected['bytes']==member['bytes'] and expected['bytes']>0,'signer_own_source_not_approved')
  current=materials.fixed_file(path,expected['bytes'],mode=expected['mode'])
  materials.need(materials.sha(current)==member['sha256'],'signer_own_source_changed')


def sign_fresh_approved_startup():
 # No caller-selected deployment or payload enters the secret-bearing helper.
 d=materials.load_approved_pair();verify_signing_source_root(d);materials.verify_expected_files(d);compare_current_purpose(d)
 prices.validate_observation(materials.fixed_file(materials.PRICE,65536),d['price_ceiling_sha256'],now=int(time.time()),upper_units=2129920)
 payload=materials.fresh_payload(d,now=int(time.time()))
 # Verify actual interpreter and approved signature module origins before any
 # Crypto import or secret read. The generic web startup guard is untouched.
 materials.need(str(Path(sys.executable).resolve(strict=True))==d['interpreter'],'approved_signing_interpreter')
 materials.need(not any(n=='cryptography' or n.startswith('cryptography.') for n in sys.modules),'crypto_loaded_before_closure')
 site=Path(d['runtime_root'])/'lib/python3.11/site-packages'
 materials.need(site.resolve(strict=True)==site and str(site) not in sys.path,'approved_signing_site')
 sys.path.append(str(site))
 for name,expected in d['signature_origins'].items():
  spec=importlib.util.find_spec(name);materials.need(spec is not None and spec.origin==expected,'approved_signature_origin')
 # Local imports only now, after compare. Issuer contract also imports Crypto.
 from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
 from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
 sys.path.insert(0,str(ROOT/'web/backend'))
 from research.external_first_answer_issuer_contract import Approval,OwnerKeyStartupBinding,_verify
 from research.provider_schemas import canonical
 parsed=Approval.model_validate(payload);expected=OwnerKeyStartupBinding.model_validate(parsed.binding)
 seed=read_signer_seed()
 try:
  key=Ed25519PrivateKey.from_private_bytes(bytes(seed))
  public=key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
  materials.need(public.hex()==d['reviewer_public_key_hex'],'approved_signer_public_key')
  approval=parsed.model_dump(mode='json');raw=canonical({'approval':approval,'signature':key.sign(canonical(approval)).hex()})
  _verify(raw,expected,public,int(time.time()))
  for name,module in tuple(sys.modules.items()):
   if name=='cryptography' or name.startswith(('cryptography.','cffi.','pycparser.')) or name in ('cffi','pycparser','_cffi_backend'):
    origin=getattr(getattr(module,'__spec__',None),'origin',None)
    if origin not in ('built-in','frozen',None):materials.need(origin in d['files'],'unapproved_signature_import')
  return raw
 finally:
  for i in range(len(seed)):seed[i]=0

def fresh_startup():
 # Invalidate first, before any check/import/key. No old startup approval can
 # survive a missing material. Never remove any startup/operation spent record.
 materials.replace_root_material(materials.APPROVAL,materials.canonical({'status':'external_closed','reason':'fresh_startup_pending'}))
 try:
  raw=sign_fresh_approved_startup()
  materials.replace_root_material(materials.APPROVAL,raw)
  return {'status':'FRESH_STARTUP_MATERIAL_WRITTEN','expires_in_seconds':120}
 except (FileNotFoundError,materials.MaterialError,prices.MaterialError,ValueError,TypeError,KeyError,ImportError):
  # Tombstone already durable. Safe CLOSED is an explicit completed outcome,
  # not ||true or claiming the external feature started successfully.
  return {'status':'EXTERNAL_CLOSED_STARTUP_MATERIAL'}

def main():
 if not(sys.platform=='linux' and os.geteuid()==0 and sys.flags.isolated and sys.flags.no_site
  and sys.flags.dont_write_bytecode and not sys.flags.optimize and len(sys.argv)==2 and sys.argv[1] in ('--price','--startup')):
  raise SystemExit('ROOT_FIXED_MATERIAL_ENTRY_REQUIRED')
 result=refresh_price() if sys.argv[1]=='--price' else fresh_startup()
 print(json.dumps(result,sort_keys=True))
if __name__=='__main__':
 try:main()
 except Exception:
  print('{"status":"ROOT_MATERIAL_JOB_FAILED","external_authority_created":false}')
  raise SystemExit(1) from None
