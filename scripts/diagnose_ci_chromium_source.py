"""Fixed public Ubuntu source preconditions; no installation or file mutations."""
import errno,fcntl,hashlib,json,os,stat,sys,types
from pathlib import Path
HELPER_SHA='245cbb8a4fdaeae5e5ac33f9d185f13fe73f0e125697681183f19593320f94b1'
SOURCE=Path('/etc/apt/sources.list.d/ubuntu.sources')
KEYRING=Path('/usr/share/keyrings/ubuntu-archive-keyring.gpg')
PARENTS=('/', '/etc','/etc/apt','/etc/apt/sources.list.d','/usr','/usr/share','/usr/share/keyrings','/tmp')
def metadata(s):
 return dict(dev=s.st_dev,ino=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=stat.S_IMODE(s.st_mode),nlink=s.st_nlink,size=s.st_size,regular=stat.S_ISREG(s.st_mode),directory=stat.S_ISDIR(s.st_mode),symlink=stat.S_ISLNK(s.st_mode))
def stable(s):return (s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
def shape(raw,helper):
 """Only bounded enums and counts leave this parser, never field/URI contents."""
 result={'bytes':len(raw),'fixed_profile_matches':len(raw)==helper.SOURCE_PROFILE_BYTES and hashlib.sha256(raw).hexdigest()==helper.SOURCE_PROFILE_SHA}
 def reject(code):return result|{'code':code,'mirror_source_passed':False}
 if not 0<len(raw)<=16384:return reject('SOURCE_SIZE')
 try:text=raw.decode('utf-8')
 except UnicodeError:return reject('SOURCE_UTF8')
 if '\r' in text or '\x00' in text:return reject('SOURCE_CONTROL')
 records=[];fields={};classes=[]
 for line in text.splitlines()+['']:
  if not line.strip():
   if fields:records.append(fields);fields={}
   continue
  if line.startswith('#'):continue
  if line[0].isspace() or ':' not in line:return reject('FIELD_LINE_SHAPE')
  name,value=line.split(':',1)
  if name not in ('Types','URIs','Suites','Components','Signed-By'):return reject('FIELD_NOT_ALLOWED')
  if name in fields:return reject('FIELD_DUPLICATE')
  if not value.startswith(' '):return reject('FIELD_VALUE_SEPARATOR')
  fields[name]=value.split()
  if name=='URIs':
   if len(fields[name])!=1:return reject('URI_COUNT')
   uri=fields[name][0];azure=uri in ('http://azure.archive.ubuntu.com/ubuntu','http://azure.archive.ubuntu.com/ubuntu/')
   classes.append('azure_http' if azure else 'fixed_archive_https' if uri in ('https://archive.ubuntu.com/ubuntu','https://archive.ubuntu.com/ubuntu/') else 'other_redacted')
   result['uri_classes']=classes.copy()
   if not (azure or result['fixed_profile_matches'] and len(uri)<=2048):return reject('URI_NOT_AZURE_OR_PINNED_PROFILE')
 result['record_count']=len(records)
 if len(records) not in (1,2):return reject('RECORD_COUNT')
 suites=[]
 for item in records:
  if set(item)!= {'Types','URIs','Suites','Components','Signed-By'}:return reject('EXACT_FIELDS')
  if item['Types']!=['deb']:return reject('TYPES')
  if item['Signed-By']!=[str(KEYRING)]:return reject('SIGNED_BY')
  if len(item['Components'])!=4 or set(item['Components'])!={'main','restricted','universe','multiverse'}:return reject('COMPONENTS')
  if item['Suites'] not in (['noble','noble-updates','noble-backports','noble-security'],['noble','noble-updates','noble-backports'],['noble-security']):return reject('SUITES')
  suites+=item['Suites']
 if len(suites)!=4 or set(suites)!={'noble','noble-updates','noble-backports','noble-security'}:return reject('SUITES_TOTAL')
 try:helper.mirror_source(raw)
 except Exception:return reject('ORIGINAL_MIRROR_VALIDATOR_REFUSED')
 return result|{'code':'ORIGINAL_MIRROR_VALIDATOR_PASSED','mirror_source_passed':True}

def inspect(path,helper):
 result={'path':str(path)};fd=None
 try:
  before=path.lstat();result['metadata']=metadata(before);result['physical']=path.resolve(strict=True)==path
  if not result['physical'] or not stat.S_ISREG(before.st_mode):return result|{'code':'PHYSICAL_REGULAR_REQUIRED'}
  fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC);s=os.fstat(fd)
  if stable(s)!=stable(before):return result|{'code':'OPEN_IDENTITY_CHANGED'}
  if path==SOURCE:
   result['original_metadata_guard_passed']=s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o644 and s.st_nlink==1
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);result['exclusive_lock_available']=True
   except OSError as e:
    result['exclusive_lock_available']=False;result['lock_errno']=e.errno
   result['mount_readonly']=bool(os.statvfs(path).f_flag & os.ST_RDONLY)
   raw=os.read(fd,16385);result['shape']=shape(raw,helper)
  else:
   raw=os.read(fd,helper.KEYRING_BYTES+1)
   result['original_keyring_guard_passed']=s.st_uid==0 and s.st_nlink==1 and s.st_size==helper.KEYRING_BYTES and len(raw)==helper.KEYRING_BYTES and hashlib.sha256(raw).hexdigest()==helper.KEYRING_SHA
  result['stable_read']=stable(s)==stable(os.fstat(fd))==stable(path.lstat())
  return result|{'code':'OBSERVED'}
 except OSError as e:return result|{'code':'FIXED_FILE_OS_ERROR','errno':e.errno}
 finally:
  if fd is not None:os.close(fd)

def run():
 if sys.platform!='linux' or os.getresuid()!=(0,0,0) or not sys.flags.isolated or not sys.flags.dont_write_bytecode:raise RuntimeError('FIXED_ROOT_LINUX_CONTEXT')
 helperpath=Path(__file__).resolve().with_name('prepare_ci_chromium.py');raw=helperpath.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=HELPER_SHA:raise RuntimeError('FIXED_D9_HELPER_PIN')
 helper=types.ModuleType('_pinned_pure_chromium_definitions');exec(compile(raw,str(helperpath),'exec'),helper.__dict__)
 parents=[]
 for name in PARENTS:
  p=Path(name)
  try:
   s=p.lstat();row={'path':name,'metadata':metadata(s),'physical':p.resolve(strict=True)==p}
   try:row['access_acl_present']=bool(os.getxattr(p,'system.posix_acl_access',follow_symlinks=False))
   except OSError as e:row['access_acl_present']=False if e.errno==errno.ENODATA else 'UNKNOWN';row['acl_errno']=e.errno
   parents.append(row)
  except OSError as e:parents.append({'path':name,'code':'PARENT_OS_ERROR','errno':e.errno})
 return {'protocol':'ci-chromium-fixed-source-readonly-diagnostic-v1','scope':'new_GitHub_image_observation_not_original_runner_causal_proof','helper_sha256':HELPER_SHA,'read_only':True,'no_install_no_apt_no_backup_write':True,'root_backup_creation_or_writability_not_tested':True,'original_effective_keyring_creation_not_replayed':True,'parents':parents,'source':inspect(SOURCE,helper),'keyring':inspect(KEYRING,helper),'private_values_exported':False}
if __name__=='__main__':
 try:print(json.dumps(run(),sort_keys=True,separators=(',',':')))
 except Exception:print('{"protocol":"ci-chromium-fixed-source-readonly-diagnostic-v1","status":"DIAGNOSTIC_REFUSED","private_values_exported":false}');raise SystemExit(2) from None
