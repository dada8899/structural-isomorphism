"""Candidate only: one fixed Analyze/mobile NOT_GATE capture; no grade/retry path."""
import argparse,hashlib,select,importlib,importlib.metadata,json,math,os,re,signal,stat,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlsplit,urljoin
SOURCE_SHA='88830a33000c3190901efd629081e9c41e259108'
BRANCH='refs/heads/codex/structure-analyze-mobile-origin-fix-88830-attempt5' # proposal only; no trigger GO
BASE='http://127.0.0.1:4173'
MAX_PROJECTED_BYTES=32*1024*1024
MAX_EVENTS=100000
STOP_SECONDS=10
NAVIGATION_NET_ERRORS=('ERR_ABORTED','ERR_CONNECTION_REFUSED','ERR_CONNECTION_CLOSED','ERR_CONNECTION_RESET','ERR_NAME_NOT_RESOLVED','ERR_FAILED','ERR_BLOCKED_BY_CLIENT','ERR_TIMED_OUT','ERR_SSL_PROTOCOL_ERROR','ERR_EMPTY_RESPONSE')
PINS={'scripts/perf_audit.py': '6bca7e272d7c534b64fcd62cb6898154cd829047054caa04202eb7f7858b1433', 'scripts/beta_perf_audit.py': 'e3360ea983d06d88908afa95cff43e714ea0d969f2a7da1dfca2d31b0d6655a4', 'scripts/beta_perf_diagnostics.py': '2669423ae7f9e03f208bd58c01b41ed77feb087a7a0198f666eadcb4605cdab4', 'perf-budget.json': 'fe2442643030ddf61fcda85053b4a3242abc68e88fc2f870e1e3874bfa319ad9', 'web/frontend/analyze.html': '3e903191903f48cf2ba360c871a06dec821e57e2f11d48ec3afe66da61ef36b1', 'web/frontend/assets/js/analyze.js': 'c767858002433f325ddb8230a9347e443a5cfc3f318c0981243ce428830b5367', 'web/frontend/assets/css/analyze.css': '86c7c9dbcd946ac6ae58dcedf8740bc430d7211f92c5df89809fb9dcf67bdf84'}
ALLOWED_ENV=frozenset(('PATH','HOME','TMPDIR','LANG','LC_ALL','LC_CTYPE','LD_LIBRARY_PATH','PYTHONDONTWRITEBYTECODE','PLAYWRIGHT_BROWSERS_PATH','RUNNER_TEMP','RUNNER_OS','RUNNER_ARCH','RUNNER_TRACKING_ID','GITHUB_WORKSPACE','GITHUB_REPOSITORY','GITHUB_EVENT_NAME','GITHUB_EVENT_PATH','GITHUB_REF','GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
TRACE_NAMES=frozenset(('RunTask','ThreadControllerImpl::RunTask','FunctionCall','EvaluateScript','Layout','UpdateLayoutTree','RecalculateStyles','ParseHTML','ParseAuthorStyleSheet','Paint','CompositeLayers','EventDispatch','FireAnimationFrame','TimerFire','RunMicrotasks','RequestAnimationFrame','ScheduleStyleRecalculation','ResourceFinish','ResourceSendRequest','CommitLoad','navigationStart','firstContentfulPaint','MarkDOMContent','MarkLoad','TracingStartedInBrowser','thread_name','process_name'))
TRACE_CATEGORIES='devtools.timeline,v8,blink.user_timing,disabled-by-default-devtools.timeline,disabled-by-default-devtools.timeline.stack'
SNAPSHOT='''() => { const p=window.__perf||{}; const n=performance.getEntriesByType('navigation')[0]; const f=performance.getEntriesByType('paint').find(e=>e.name==='first-contentful-paint'); return {timeOrigin:performance.timeOrigin,now:performance.now(),fcp:f?f.startTime:0,longTasks:(p.longTasks||[]).map(t=>({start:t.start,duration:t.duration})),click:{count:p.trustedInteractionCount||0,pointerDown:p.trustedPointerDownTimestamp||0,pointerUp:p.trustedPointerUpTimestamp||0,at:p.trustedInteractionTimestamp||0},navigation:n?{startTime:n.startTime,responseEnd:n.responseEnd,domContentLoadedEventEnd:n.domContentLoadedEventEnd,loadEventEnd:n.loadEventEnd}:null,resources:performance.getEntriesByType('resource').map(x=>({url:x.name,start:x.startTime,duration:x.duration,responseEnd:x.responseEnd,bytes:x.transferSize}))}; }'''
class Refused(RuntimeError):pass
def need(v):
 if not v:raise Refused('scope_or_evidence_refused')
def sha(b):return hashlib.sha256(b).hexdigest()
def regular(path,limit):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd);need(stat.S_ISREG(a.st_mode) and a.st_size<=limit);raw=b''
  while b:=os.read(fd,min(65536,limit-len(raw)+1)):raw+=b;need(len(raw)<=limit)
  z=os.fstat(fd);need((a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(z.st_dev,z.st_ino,z.st_size,z.st_mtime_ns,z.st_ctime_ns));return raw
 finally:os.close(fd)
def git(root,*args):
 r=subprocess.run(['git','-C',str(root),*args],stdin=subprocess.DEVNULL,capture_output=True,timeout=5);need(r.returncode==0 and len(r.stdout)<=262144);return r.stdout.decode().strip()
def validate_push(meta,env):
 need(env.get('GITHUB_REPOSITORY')=='dada8899/structural-isomorphism' and env.get('GITHUB_EVENT_NAME')=='push' and env.get('GITHUB_REF')==BRANCH and env.get('GITHUB_RUN_ATTEMPT')=='1')
 need(type(meta) is dict and meta.get('created') is True and meta.get('deleted') is False)
 need(meta.get('ref')==BRANCH and meta.get('after')==env.get('GITHUB_SHA') and type(meta.get('repository')) is dict and meta['repository'].get('full_name')=='dada8899/structural-isomorphism')
def validate_scope(root,out,env):
 need(sys.platform=='linux' and sys.flags.isolated and sys.flags.dont_write_bytecode)
 need(not(set(env)-ALLOWED_ENV));need(env.get('RUNNER_OS')=='Linux' and env.get('RUNNER_ARCH')=='X64')
 event_path=Path(env.get('GITHUB_EVENT_PATH',''));need(event_path.is_absolute() and event_path==event_path.resolve() and Path(env['RUNNER_TEMP']).resolve() in event_path.parents)
 validate_push(json.loads(regular(event_path,2*1024*1024)),env)
 need(re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')) is not None and re.fullmatch('[0-9a-f]{40}',env.get('GITHUB_SHA','')) is not None)
 need(root.is_absolute() and root==root.resolve() and root==Path(env['GITHUB_WORKSPACE']).resolve()/'source')
 need(out.is_absolute() and out==out.resolve() and out==Path(env['RUNNER_TEMP']).resolve()/('structure-beta-perf-once-'+env['GITHUB_RUN_ID']+'-1')/'artifacts' and root not in out.parents)
 need(Path(env['HOME'])==out.parent/'work/home' and Path(env['TMPDIR'])==out.parent/'work/tmp')
SOURCE_ALLOW18={'results/v2-discoveries-v2model.jsonl': {'oid': 'bda38dbd67bd26f1f9803e0deaab1fe9ae9d1d16', 'bytes': 3757626}, 'results/v2-discoveries.jsonl': {'oid': '26f2d0a541e494415fdbb723a7736547fc32a1bc', 'bytes': 2328222}, 'results/v2m-screened-all.jsonl': {'oid': 'afb122260c3e97aa2c9eedae9a090b9c844b5c95', 'bytes': 1182215}, 'v3/results/kb-expanded-struct.jsonl': {'oid': '416417c843919ff6c0bbdde1e8998512ee754007', 'bytes': 2789655}, 'v4/validation/hysteresis-traffic/us101_ngsim_agg_raw.csv': {'oid': 'd1fc3a07e605b1e662fa1749d154f651d5dcb920', 'bytes': 236284}, 'v4/validation/scheffer-lake/lake_do_timeseries.jsonl': {'oid': 'ce6bfa283bcc642c61655557b3087a63147c7dcb', 'bytes': 698206}, 'v4/validation/soc-bank-failures/raw_fdic.json': {'oid': '0b3abc6cbb322810945c1f41f8479052cfe2a980', 'bytes': 2408576}, 'v4/validation/soc-defi/aave_v2_liquidations.jsonl': {'oid': 'e753b82fe26d4f2cbea4dfc6323be3f841400909', 'bytes': 12889578}, 'v4/validation/soc-defi/compound_v2_liquidations.jsonl': {'oid': '70267f27d85a83884b550a5d1c83987c6b5e1ac4', 'bytes': 6612343}, 'v4/validation/soc-defi/maker_dog_liquidations.jsonl': {'oid': 'c06232b5434c6d48d04e94cd95d5a9b8f88cad41', 'bytes': 1348041}, 'v4/validation/soc-earthquake/catalog.jsonl': {'oid': '3175911bedb53084e990a5b90cb4c1d64b2b4d99', 'bytes': 22087130}, 'v4/validation/soc-earthquake/catalog.parquet': {'oid': '7ff6556b89ce94d2d7078c9c5455cbf4092bce3a', 'bytes': 5139487}, 'v4/validation/soc-neural/bf_1.jsonl': {'oid': '4316d85b4135d68caa7cf01f908c8b4ad3cf781a', 'bytes': 8170109}, 'v4/validation/soc-neural/bf_2.jsonl': {'oid': '549866c4330000462af7e3cebf1dd09c9bb9cee3', 'bytes': 2165216}, 'v4/validation/soc-neural/data/sample.nwb': {'oid': '43be7ac0b64af3dd607f5e7b3326707b258bcb5b', 'bytes': 11476076}, 'v4/validation/soc-neural/neural_avalanches.jsonl': {'oid': '4316d85b4135d68caa7cf01f908c8b4ad3cf781a', 'bytes': 8170109}, 'v4/validation/soc-neural/synthetic_avalanches.jsonl': {'oid': '37a185357961b5b9c73dd2ca124bc0c9797da4fc', 'bytes': 5512674}, 'v4/validation/soc-solar/flares.jsonl': {'oid': '3dd1de0d66c9c191d7896001bfd84f51efb7bff7', 'bytes': 5695346}}
SOURCE_FILE_CAP=32*1024*1024
SOURCE_TOTAL_CAP=128*1024*1024
SOURCE_WALL_SECONDS=20
class SourceRefused(RuntimeError):pass
def source_need(value,reason):
 if not value:raise SourceRefused(reason)
def source_meta(root,args,deadline,accepted=(0,)):
 timeout=min(5,deadline-time.monotonic());source_need(timeout>0,'source_deadline');env=dict(os.environ);env['GIT_OPTIONAL_LOCKS']='0'
 r=subprocess.run(['git','-C',str(root),*args],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,timeout=timeout)
 source_need(r.returncode in accepted and len(r.stdout)<=262144,'git_metadata_unavailable');return r.returncode,r.stdout
def source_decision(head,index_clean,status):
 source_need(head==SOURCE_SHA,'head_mismatch');source_need(index_clean is True,'index_or_staged_change')
 if status==b'':return 'normal_clean',[]
 rows=status.split(b'\0');source_need(rows[-1]==b'' and 1<len(rows)<=257,'status_protocol_invalid');dirty=[]
 for row in rows[:-1]:
  source_need(len(row)>=4 and row[2:3]==b' ','status_protocol_invalid');xy=row[:2];path=row[3:]
  source_need(xy!=b'??','untracked_present');source_need(xy==b' M','nonexception_worktree_status')
  matches=[name for name in SOURCE_ALLOW18 if name.encode()==path];source_need(len(matches)==1,'dirty_outside_allowlist');dirty.append(matches[0])
 source_need(len(dirty)==len(set(dirty)),'duplicate_dirty_path');return 'allow18_byte_check_required',dirty
def source_identity(m):return(m.st_dev,m.st_ino,m.st_uid,m.st_mode,m.st_nlink,m.st_size,m.st_mtime_ns,m.st_ctime_ns)
def scoped_data_open(root,name,size):
 source_need(name in SOURCE_ALLOW18,'path_outside_allowlist');parts=Path(name).parts;source_need(not Path(name).is_absolute() and '..' not in parts,'invalid_relative_path');fds=[];dirs=[]
 try:
  before=root.lstat();source_need(stat.S_ISDIR(before.st_mode),'root_link_or_type');fds.append(os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC));source_need(source_identity(before)==source_identity(os.fstat(fds[0])),'root_changed');dirs.append(before)
  for part in parts[:-1]:
   before=os.stat(part,dir_fd=fds[-1],follow_symlinks=False);source_need(stat.S_ISDIR(before.st_mode),'parent_link_or_type');child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fds[-1]);fds.append(child);source_need(source_identity(before)==source_identity(os.fstat(child)),'parent_changed');dirs.append(before)
  fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,dir_fd=fds[-1]);fds.append(fd);m=os.fstat(fd)
  source_need(stat.S_ISREG(m.st_mode) and m.st_nlink==1 and m.st_size==size and not m.st_mode&0o111,'input_metadata_changed');return fds,m,dirs
 except BaseException:
  for fd in reversed(fds):os.close(fd)
  raise
def compare_chunks(chunks,read,size,deadline):
 count=0
 for expected in chunks:
  source_need(time.monotonic()<deadline,'byte_comparison_deadline');count+=len(expected);source_need(count<=size,'blob_size_changed');actual=b''
  while len(actual)<len(expected):
   data=read(len(expected)-len(actual));source_need(bool(data),'worktree_short');actual+=data
  source_need(actual==expected,'raw_byte_mismatch')
 source_need(count==size and read(1)==b'','raw_size_mismatch');source_need(time.monotonic()<deadline,'byte_comparison_deadline');return count
def compare_source_blob(root,name,pin,overall_deadline):
 size=pin['bytes'];source_need(0<size<=SOURCE_FILE_CAP,'file_byte_cap');deadline=min(overall_deadline,time.monotonic()+5);fds,first,dirs=scoped_data_open(root,name,size);process=None
 try:
  env=dict(os.environ);env['GIT_OPTIONAL_LOCKS']='0';process=subprocess.Popen(['git','-C',str(root),'cat-file','blob',pin['oid']],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env);os.set_blocking(process.stdout.fileno(),False)
  def chunks():
   while True:
    remaining=deadline-time.monotonic();source_need(remaining>0,'blob_stream_deadline');ready,_,_=select.select([process.stdout],[],[],min(.1,remaining))
    if not ready:continue
    b=os.read(process.stdout.fileno(),65536)
    if not b:break
    yield b
  count=compare_chunks(chunks(),lambda n:os.read(fds[-1],n),size,deadline);source_need(time.monotonic()<deadline,'blob_stream_deadline');source_need(process.wait(timeout=max(.01,deadline-time.monotonic()))==0,'blob_reader_failed');source_need(time.monotonic()<deadline,'blob_wait_deadline');source_need(source_identity(first)==source_identity(os.fstat(fds[-1]))==source_identity(os.stat(Path(name).name,dir_fd=fds[-2],follow_symlinks=False)),'input_changed_during_read')
  source_need(source_identity(dirs[0])==source_identity(root.lstat())==source_identity(os.fstat(fds[0])),'root_changed_during_read')
  for i,part in enumerate(Path(name).parts[:-1],1):source_need(source_identity(dirs[i])==source_identity(os.fstat(fds[i]))==source_identity(os.stat(part,dir_fd=fds[i-1],follow_symlinks=False)),'parent_changed_during_read')
  source_need(time.monotonic()<deadline,'blob_metadata_deadline');return count,source_identity(first),[source_identity(x) for x in dirs]
 finally:
  if process is not None:
   if process.poll() is None:
    process.terminate()
    try:process.wait(timeout=1)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)
   if process.stdout:process.stdout.close()
  for fd in reversed(fds):os.close(fd)
def preflight_json(out,name,value):
 raw=json.dumps(value,sort_keys=True,allow_nan=False).encode();source_need(len(raw)<=16384,'preflight_json_cap');fd=os.open(out/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  at=0
  while at<len(raw):n=os.write(fd,raw[at:]);source_need(n>0,'preflight_receipt_write');at+=n
  os.fsync(fd)
 finally:os.close(fd)
def checked_preflight_output(out,env):
 source_need(out.is_absolute() and out==out.resolve(),'output_path_invalid');source_need(re.fullmatch('[1-9][0-9]{0,19}',env.get('GITHUB_RUN_ID','')) is not None,'run_id_invalid');source_need(out==Path(env['RUNNER_TEMP']).resolve()/('structure-beta-perf-once-'+env['GITHUB_RUN_ID']+'-1')/'artifacts','output_scope_invalid');m=out.lstat();source_need(stat.S_ISDIR(m.st_mode) and m.st_uid==os.getuid() and stat.S_IMODE(m.st_mode)==0o700,'output_permissions_invalid')
def source_result(classification):
 return {'classification':classification,'status':'UNKNOWN','capture_complete':False,'head':None,'head_matches':None,'head_after':None,'index_sha256_before':None,'index_sha256_after':None,'index_matches':None,'native_clean':None,'status_sha256':None,'dirty_path_count':None,'allowed_dirty_paths':[],'comparison':[],'post_worktree_status_same':None,'pins_verified':False,'pin_metadata_sha256':None,'allow_metadata_sha256':None,'reason':None}
def source_error(result,error):
 result['status']='refused';result['reason']=str(error) if type(error) is SourceRefused else 'scope_or_evidence_error';result['error_type']=type(error).__name__ if type(error).__name__ in ('SourceRefused','Refused','OSError','PermissionError','FileNotFoundError','TimeoutExpired','TimeoutError','UnicodeDecodeError') else 'Other'
def source_coordinates(result):
 source_need(result['status']=='source_verified','unverified_source_coordinates')
 # Immutable local tuple derived from native facts before Source imports, not caller ENV/app-state.
 return tuple(result[key] for key in ('head','index_sha256_after','status_sha256','pin_metadata_sha256','allow_metadata_sha256'))
def verify_source_readonly(root,deadline,result):
 source_need(time.monotonic()<deadline,'source_deadline')
 _,head=source_meta(root,['rev-parse','HEAD'],deadline);head=head.decode().strip();source_need(re.fullmatch('[0-9a-f]{40}',head) is not None,'head_protocol_invalid');result['head']=head;result['head_matches']=head==SOURCE_SHA;source_need(result['head_matches'],'head_mismatch')
 _,idx=source_meta(root,['rev-parse','--git-path','index'],deadline);idxpath=Path(idx.decode().strip());idxpath=idxpath if idxpath.is_absolute() else root/idxpath;source_need(idxpath.is_absolute() and idxpath==idxpath.resolve() and root in idxpath.parents,'index_path_invalid');result['index_sha256_before']=sha(regular(idxpath,4*1024*1024))
 rc,_=source_meta(root,['diff-index','--cached','--quiet','--no-ext-diff',SOURCE_SHA,'--'],deadline,(0,1));result['index_matches']=rc==0;source_need(result['index_matches'],'index_or_staged_change')
 _,status=source_meta(root,['status','--porcelain=v1','-z','--untracked-files=all'],deadline);result['native_clean']=status==b'';result['status_sha256']=sha(status);result['dirty_path_count']=0 if not status else max(0,len(status.split(b'\0'))-1)
 # Never echo unrecognized untracked/dirty names, query text, or command stderr.
 mode,dirty=source_decision(head,result['index_matches'],status);result['allowed_dirty_paths']=dirty;result['channel']=mode;snapshots={}
 if dirty:
  _,objects=source_meta(root,['ls-tree','-r','-z',SOURCE_SHA,'--',*SOURCE_ALLOW18],deadline);expected_objects={('100644 blob '+pin['oid']+'\t'+name).encode() for name,pin in SOURCE_ALLOW18.items()};source_need(set(objects.split(b'\0')[:-1])==expected_objects and objects.endswith(b'\0'),'allowlist_object_mismatch')
  _,attrs=source_meta(root,['check-attr','-z','filter','--',*SOURCE_ALLOW18],deadline);expected=b''.join(name.encode()+b'\0filter\0lfs\0' for name in SOURCE_ALLOW18);source_need(attrs==expected,'allowlist_attributes_differ');source_need(sum(x['bytes'] for x in SOURCE_ALLOW18.values())<=SOURCE_TOTAL_CAP,'total_byte_cap');total=0
  for name,pin in SOURCE_ALLOW18.items():
   count,file_identity,parents=compare_source_blob(root,name,pin,deadline);snapshots[name]=(file_identity,parents);total+=count;source_need(total<=SOURCE_TOTAL_CAP,'total_byte_cap');result['comparison'].append({'path':name,'oid':pin['oid'],'bytes':count,'raw_blob_identical':True})
 pin_meta=[]
 for name,pin in PINS.items():
  before=(root/name).lstat();actual=sha(regular(root/name,4*1024*1024));after=(root/name).lstat();source_need(source_identity(before)==source_identity(after),'pin_changed_during_read');source_need(actual==pin,'source_pin_mismatch');pin_meta.append((name,source_identity(after)))
 result['pin_metadata_sha256']=sha(json.dumps(pin_meta,sort_keys=True).encode())
 for name,(file_identity,parents) in snapshots.items():
  fds,last,dirs=scoped_data_open(root,name,SOURCE_ALLOW18[name]['bytes'])
  try:source_need(source_identity(last)==file_identity and [source_identity(x) for x in dirs]==parents,'input_changed_after_read')
  finally:
   for fd in reversed(fds):os.close(fd)
 _,post_status=source_meta(root,['status','--porcelain=v1','-z','--untracked-files=all'],deadline);result['post_worktree_status_same']=post_status==status;source_need(result['post_worktree_status_same'],'worktree_status_changed_during_preflight')
 result['allow_metadata_sha256']=sha(json.dumps(sorted(snapshots.items()),sort_keys=True).encode())
 result['pins_verified']=True;_,after=source_meta(root,['rev-parse','HEAD'],deadline);after=after.decode().strip();source_need(re.fullmatch('[0-9a-f]{40}',after) is not None,'head_protocol_invalid');result['head_after']=after;result['index_sha256_after']=sha(regular(idxpath,4*1024*1024));source_need(after==head and result['index_sha256_after']==result['index_sha256_before'],'head_or_index_changed_during_preflight');source_need(time.monotonic()<deadline,'source_deadline');result['status']='source_verified'
 return source_coordinates(result)
def source_preflight(root,out):
 checked_preflight_output(out,os.environ);preflight_json(out,'source-preflight-reserved.json',{'classification':'SOURCE_PREFLIGHT_ONLY','status':'pending','capture_started':False});result=source_result('SOURCE_PREFLIGHT_ONLY');result['capture_started']=False;deadline=time.monotonic()+SOURCE_WALL_SECONDS;prior={}
 def stop(signum,frame):raise SourceRefused('preflight_interrupted_or_deadline')
 try:
  for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM):prior[sig]=signal.signal(sig,stop)
  signal.alarm(SOURCE_WALL_SECONDS);validate_scope(root,out,os.environ);coordinates=verify_source_readonly(root,deadline,result)
 except BaseException as error:source_error(result,error)
 finally:
  signal.alarm(0)
  for sig,handler in prior.items():signal.signal(sig,handler)
  preflight_json(out,'source-preflight.json',result)
 source_need(result['status']=='source_verified' and time.monotonic()<deadline,'source_preflight_refused');return coordinates
def source_postflight(root,out,initial_coordinates,capture_deadline):
 # No signal/alarm changes here: use the stricter of20s and the original remaining120s budget.
 deadline=min(capture_deadline,time.monotonic()+SOURCE_WALL_SECONDS);checked_preflight_output(out,os.environ);result=source_result('SOURCE_POSTFLIGHT_ONLY');result['bound_to_initial']=False
 try:
  validate_scope(root,out,os.environ);coordinates=verify_source_readonly(root,deadline,result);result['bound_to_initial']=coordinates==initial_coordinates;source_need(result['bound_to_initial'],'source_changed_since_start');source_need(time.monotonic()<deadline,'source_postflight_deadline')
 except BaseException as error:source_error(result,error)
 finally:preflight_json(out,'source-postflight.json',result)
 source_need(result['status']=='source_verified' and result['bound_to_initial'] and time.monotonic()<deadline,'source_postflight_refused');return coordinates

def number(v):need(type(v) in (int,float) and math.isfinite(v));return v
def fixture_audit_base(base,relative_path):
 # Source audit_one concatenates base+path. Match the official normalizedbase
 # contract, and independently prove its target equals the standard URLjoin.
 need(type(base) is str and 0<len(base)<=256 and type(relative_path) is str and 0<len(relative_path)<=1024)
 need(base.isascii() and relative_path.isascii() and not any(ord(c)<33 or ord(c)==127 or c=='\\' for c in base+relative_path))
 try:
  origin=urlsplit(base);relative=urlsplit(relative_path);port=origin.port
 except ValueError:raise Refused('fixture_navigation_refused') from None
 need((origin.scheme,origin.hostname,port)==('http','127.0.0.1',4173) and origin.username is None and origin.password is None)
 need(origin.path in ('','/') and not origin.query and not origin.fragment)
 need(base=='http://127.0.0.1:4173'+origin.path)
 need(not relative.scheme and not relative.netloc and relative.path=='analyze.html' and not relative.fragment)
 need(relative_path==relative.path+('?' + relative.query if relative.query else ''))
 normalized=base.rstrip('/')+'/';target=urljoin(normalized,relative_path);parsed=urlsplit(target)
 need((parsed.scheme,parsed.hostname,parsed.port,parsed.path)==('http','127.0.0.1',4173,'/analyze.html'))
 need(parsed.query==relative.query and not parsed.fragment and target==normalized+relative_path)
 return normalized
def bounded_action(deadline,action):
 # A nested phase may shorten, never renew, the existing absolute alarm.
 now=time.monotonic();need(now<deadline);old_delay,interval=signal.getitimer(signal.ITIMER_REAL);need(interval==0)
 old_deadline=now+old_delay if old_delay>0 else None
 effective=min(deadline,old_deadline) if old_deadline is not None else deadline
 def expired(signum,frame):raise Refused('diagnostic_phase_deadline')
 old_handler=signal.signal(signal.SIGALRM,expired)
 try:
  signal.setitimer(signal.ITIMER_REAL,max(.000001,effective-time.monotonic()))
  value=action();need(time.monotonic()<effective);return value
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old_handler)
  remaining=max(0,old_deadline-time.monotonic()) if old_deadline is not None else 0
  if remaining>0:signal.setitimer(signal.ITIMER_REAL,remaining)
def navigation_failure_category(error,error_type,timeout_type):
 # Inspect only the two actual SDK exception classes. Never export the text,
 # arbitrary class names, URLs, tracebacks, headers or any page/account data.
 label='Error' if type(error) is error_type else 'TimeoutError' if type(error) is timeout_type else 'other'
 if isinstance(error,(KeyboardInterrupt,SystemExit)):return label,'navigation_interrupted'
 if label=='TimeoutError':return label,'timeout'
 if label!='Error':return label,'other'
 try:text=str(error)
 except (KeyboardInterrupt,SystemExit):raise
 except BaseException:return label,'other'
 if len(text)>8192:return label,'other'
 for code in NAVIGATION_NET_ERRORS:
  if re.search(r'(?<![A-Z0-9_])net::'+code+r'(?![A-Z0-9_])',text):return label,'net::'+code
 if 'Target page, context or browser has been closed' in text or 'Target closed' in text:return label,'target_closed'
 if 'interrupted by another navigation' in text or 'Navigation interrupted' in text:return label,'navigation_interrupted'
 return label,'other'
def bind_navigation_observer(page,writer,capture,capture_deadline,error_type,timeout_type):
 original=page.goto;calls=0
 def publish(outcome,error=None):
  try:
   need(calls==1)
   label,category=navigation_failure_category(error,error_type,timeout_type) if error is not None else (None,None)
   record={'classification':'NOT_GATE','kind':'navigation_observer_v1','outcome':outcome,'calls_observed':calls,'exception_type':label,'failure_category':category}
   need(len(json.dumps(record,allow_nan=False).encode())<=512)
   bounded_action(capture_deadline,lambda:writer.write_json('navigation-outcome.json',record,control=True))
  except BaseException as observation_error:
   capture.error('navigation_observer_receipt_unknown')
   if isinstance(observation_error,(KeyboardInterrupt,SystemExit)):
    if error is not None and capture.primary_failure is None:
     label='Error' if type(error) is error_type else 'TimeoutError' if type(error) is timeout_type else 'other'
     capture.primary_failure={'stage':'navigation','error':'navigation_failed','error_detail':{'code':'navigation_failed','type':label}}
    raise  # New cancellation wins; the original goto error stays in context.
 def observed(*args,**kwargs):
  nonlocal calls
  calls+=1
  try:value=original(*args,**kwargs)
  except BaseException as error:
   publish('raised',error)
   raise  # Preserve the exact original exception object and cancellation.
  publish('returned')
  return value
 page.goto=observed
def safe_path(value):
 need(type(value) is str and len(value)<=4096);u=urlsplit(value)
 if (u.scheme,u.hostname,u.port)==('http','127.0.0.1',4173) and (u.path=='/analyze.html' or re.fullmatch(r'/assets/[A-Za-z0-9_./-]{1,220}',u.path) and '..' not in u.path.split('/')):return u.path
 return '<nonlocal-or-evaluation>'
def safe_frame(d):
 need(type(d) is dict);out={}
 for k in ('lineNumber','columnNumber'):
  if type(d.get(k)) is int and 0<=d[k]<=10000000:out[k]=d[k]
 if type(d.get('scriptId')) is str and re.fullmatch('[0-9]{1,12}',d['scriptId']):out['scriptId']=d['scriptId']
 if type(d.get('url')) is str:out['path']=safe_path(d['url'])
 name=d.get('functionName')
 if type(name) is str and re.fullmatch(r'[A-Za-z0-9_.$<>: -]{0,120}',name):out['function']=name
 return out
def project_trace_event(e):
 need(type(e) is dict)
 if e.get('name') not in TRACE_NAMES:return None
 row={'name':e['name']}
 if e.get('ph') in ('B','E','X','I','i','R','M','C'):row['ph']=e['ph']
 for k in ('pid','tid','ts','dur'):
  if type(e.get(k)) in (int,float):row[k]=number(e[k])
 args=e.get('args',{});d=args.get('data',{}) if type(args) is dict else {};d=d if type(d) is dict else {};f=safe_frame(d)
 if f:row['code']=f
 stack=d.get('stackTrace')
 if type(stack) is list:
  need(len(stack)<=128);row['stack']=[safe_frame(x) for x in stack]
 if e['name'] in ('thread_name','process_name'):
  name=args.get('name')
  if name in ('CrRendererMain','CrBrowserMain','Renderer','Browser','Compositor','Chrome_ChildIOThread'):row['thread_or_process']=name
 return row
def snapshot_projection(raw,ready):
 need(type(raw) is dict and len(raw['longTasks'])<=4096 and len(raw['resources'])<=1024)
 return {'classification':'NOT_GATE','timeOrigin':number(raw['timeOrigin']),'now':number(raw['now']),'fcp':number(raw['fcp']),'window_end':number(raw['fcp'])+5000,'longTasks':[{'start':number(x['start']),'duration':number(x['duration'])} for x in raw['longTasks']],'click':{k:number(raw['click'][k]) for k in ('count','pointerDown','pointerUp','at')},'validated_ready_browser_ms':ready,'navigation':None if raw['navigation'] is None else {k:number(raw['navigation'][k]) for k in ('startTime','responseEnd','domContentLoadedEventEnd','loadEventEnd')},'resources':[{'path':safe_path(x['url']),**{k:number(x[k]) for k in ('start','duration','responseEnd','bytes')}} for x in raw['resources']]}
class Capture:
 def __init__(self,writer,beta,perf,capture_deadline=None):
  self.writer,self.beta,self.perf=writer,beta,perf;self.page=self.cdp=None;self.tracing=False;self.stop_requested=False;self.stop_deadline=None;self.terminal_received=False;self.loss=None;self.projected=[];self.projected_bytes=0;self.source_events=0;self.overflow=False;self.ready=[];self.seen=set();self.final=None;self.captured=False;self.errors=[];self.browser=None
  self.capture_deadline=capture_deadline;self.trace_finished=False;self.metric_verified=False;self.primary_failure=None
 def error(self,code):
  if code not in self.errors:self.errors.append(code)
 def on_data(self,message):
  if self.terminal_received:self.error('trace_data_after_terminal');return
  try:
   need(type(message) is dict and type(message.get('value')) is list);events=message['value'];self.source_events+=len(events)
   if self.source_events>MAX_EVENTS:self.overflow=True;self.error('trace_event_limit');return
   if self.errors:return
   for event in events:
    if self.stop_deadline is not None and time.monotonic()>self.stop_deadline:self.error('trace_processing_deadline');return
    row=project_trace_event(event)
    if row is None:continue
    encoded=json.dumps(row,separators=(',',':'),allow_nan=False).encode();extra=len(encoded)+(1 if self.projected else 0)
    if self.projected_bytes+extra>MAX_PROJECTED_BYTES-4096:self.overflow=True;self.error('trace_projection_byte_limit');return
    # Only already-filtered encoded rows are retained; never retain raw event/args objects.
    self.projected.append(encoded);self.projected_bytes+=extra
  except Exception:self.error('trace_projection_invalid')
 def on_complete(self,message):
  if self.terminal_received:self.error('trace_duplicate_terminal');return
  self.terminal_received=True
  if not self.stop_requested:self.error('trace_premature_terminal')
  if type(message) is not dict:self.error('trace_terminal_invalid');return
  self.loss=message.get('dataLossOccurred') if type(message.get('dataLossOccurred')) is bool else None
  if self.loss is not False:self.error('trace_data_lost' if self.loss is True else 'trace_loss_flag_unknown')
  if 'stream' in message:self.error('unexpected_stream_transport')
 def setup(self,page):
  need(self.page is None);self.page=page;self.browser=page.context.browser;self.cdp=page.context.new_cdp_session(page);self.cdp.on('Tracing.dataCollected',self.on_data);self.cdp.on('Tracing.tracingComplete',self.on_complete);self.cdp.send('Tracing.start',{'categories':TRACE_CATEGORIES,'transferMode':'ReportEvents'});self.tracing=True
 def validated(self,page,state,original):
  original(page,state);need(len(self.ready)<2);self.ready.append({'phase':'before_click' if not self.ready else 'after_window','ms':number(page.evaluate('performance.now()'))})
 def sink(self,sample):
  phase=sample.get('cleanup_status');need(phase in ('pending','passed','failed'));key='pending' if phase=='pending' else 'final';need(key not in self.seen);self.seen.add(key);safe=self.beta._checkpoint_run_evidence(sample)
  if key=='pending' and safe.get('audit_status')!='passed':self.primary_failure={k:safe[k] for k in ('stage','error','error_detail') if k in safe}
  self.writer.write_json('audit-'+key+'.json',{'classification':'NOT_GATE','sample':safe})
  if key=='final':self.final=safe;return
  try:
   # Failed primary evidence has no valid metric. Preserve it and let the
   # original audit publish its real browser-close result before returning.
   if safe.get('audit_status')!='passed':return
   need(not self.captured);self.captured=True;raw=snapshot_projection(self.page.evaluate(SNAPSHOT),self.ready);self.writer.write_json('browser-window.json',raw)
   fcp=raw['fcp'];parts=[]
   for task in raw['longTasks']:
    overlap=max(0,min(task['start']+task['duration'],fcp+5000)-max(task['start'],fcp));parts.append({'start':task['start'],'duration':task['duration'],'clipped_overlap':overlap,'blocking_ms':max(0,overlap-50)})
   tbt=self.perf.compute_tbt(raw['longTasks'],fcp,fcp+5000);self.writer.write_json('tbt-contributions.json',{'classification':'NOT_GATE','tasks':parts,'recomputed_tbt_ms':tbt,'original_single_sample_tbt_ms':safe.get('tbt_ms'),'matches_original_sample':safe.get('tbt_ms')==round(tbt,1),'historical888_grade_unchanged':'failed'})
   need(safe.get('tbt_ms')==round(tbt,1));self.metric_verified=True
  except BaseException:
   self.error('capture_incomplete')
  finally:self.finish_trace()
 def finish_trace(self):
  if self.trace_finished:return
  self.trace_finished=True
  deadline=min(self.capture_deadline,time.monotonic()+STOP_SECONDS) if self.capture_deadline is not None else time.monotonic()+STOP_SECONDS
  def finish():
   try:
    if self.cdp is not None and not self.stop_requested:self.end_trace()
    elif self.cdp is not None and not self.terminal_received:self.error('trace_terminal_missing')
   finally:self.close_trace(deadline)
  try:bounded_action(deadline,finish)
  except BaseException:self.error('trace_finalize_unknown')
 def write_trace(self,trusted):
  terminal={'classification':'NOT_GATE','transport':'ReportEvents','trace_complete':trusted,'terminal_received':self.terminal_received,'dataLossOccurred':self.loss,'overflow':self.overflow,'source_events_observed':self.source_events,'retained_projected_events':len(self.projected),'retained_encoded_bytes_with_separators':self.projected_bytes,'application_projection_byte_limit':MAX_PROJECTED_BYTES,'raw_trace_artifact_written_by_collector':False,'native_browser_driver_memory_or_storage_hardcap_proven':False,'unknown_reasons':list(self.errors)}
  self.writer.write_json('trace-terminal.json',terminal,control=True)
  def chunks():
   yield b'{"classification":"NOT_GATE","trace_complete":'+(b'true' if trusted else b'false')+b',"events":['
   for i,row in enumerate(self.projected):
    if i:yield b','
    yield row
   yield b']}'
  self.writer.write_chunks('timeline.json',chunks())
 def end_trace(self):
  self.stop_deadline=time.monotonic()+STOP_SECONDS
  if self.capture_deadline is not None:self.stop_deadline=min(self.stop_deadline,self.capture_deadline)
  self.stop_requested=True;self.tracing=False;self.cdp.send('Tracing.end')
  while not self.terminal_received and time.monotonic()<self.stop_deadline:self.page.wait_for_timeout(20)
  if not self.terminal_received:self.error('trace_terminal_missing')
  if time.monotonic()>self.stop_deadline:self.error('trace_stop_deadline')
  if self.source_events==0 or not self.projected:self.error('trace_data_missing')
  trusted=self.terminal_received and self.loss is False and not self.overflow and not self.errors
  self.write_trace(trusted);need(trusted)
 def close_trace(self,deadline=None):
  if self.cdp is None:return
  try:
   if deadline is not None:need(time.monotonic()<deadline)
   if self.tracing and not self.stop_requested:
    self.stop_requested=True;self.tracing=False;self.cdp.send('Tracing.end')
   if deadline is not None:need(time.monotonic()<deadline)
   self.cdp.detach()
  except BaseException:self.error('trace_close_unknown')
  finally:self.cdp=None
 def close(self):
  # Closure is a native-state observation, separate from diagnostic validity.
  try:
   if self.browser is not None and self.browser.is_connected():self.browser.close()
   return self.browser is not None and not self.browser.is_connected()
  except BaseException:self.error('browser_close_unknown');return False

def server_identity(p):
 text=regular(Path('/proc')/str(p.pid)/'stat',8192).decode();v=text[text.rfind(')')+2:].split();return (p.pid,int(v[19]))
def owned_listening(p):
 need(p.poll() is None);table=regular(Path('/proc/net/tcp'),262144).decode().splitlines();inodes={line.split()[9] for line in table[1:] if len(line.split())>9 and line.split()[1]=='0100007F:104D' and line.split()[3]=='0A'}
 if not inodes:return False
 for f in (Path('/proc')/str(p.pid)/'fd').iterdir():
  try:link=os.readlink(f)
  except FileNotFoundError:continue
  if link.startswith('socket:[') and link[8:-1] in inodes:return True
 return False
def stop_server(p,saved):
 if p is None:return True
 if p.poll() is not None:return True
 need(server_identity(p)==saved);p.terminate()
 try:p.wait(timeout=5)
 except subprocess.TimeoutExpired:
  need(server_identity(p)==saved);p.kill();p.wait(timeout=2)
 return p.returncode is not None

def cleanup_work(out):
 work=out.parent/'work';need(work==work.resolve() and work.stat().st_uid==os.getuid() and stat.S_IMODE(work.stat().st_mode)==0o700);dirs=[];files=[];count=0
 for parent,children,names in os.walk(work,followlinks=False):
  dirs.append(Path(parent))
  for name in [*children,*names]:
   path=Path(parent)/name;m=path.lstat();need(m.st_uid==os.getuid() and (stat.S_ISDIR(m.st_mode) or stat.S_ISREG(m.st_mode) and m.st_nlink==1));count+=1;need(count<=8192)
   if stat.S_ISREG(m.st_mode):files.append(path)
 for path in files:path.unlink()
 for path in reversed(dirs):path.rmdir()
 return not work.exists()

def finalize_diagnostic(result,capture,driver,server,saved,root,out,initial_coordinates,capture_deadline):
 def failed(code):
  if code not in result['secondary_errors']:result['secondary_errors'].append(code)
  if result['error'] is None:result['error']=code
 if capture is not None:
  if result['primary_failure'] is None:result['primary_failure']=capture.primary_failure
  capture.finish_trace()
 # A failed navigation must not suppress the independent end-of-source check.
 try:
  bounded_action(min(capture_deadline,time.monotonic()+SOURCE_WALL_SECONDS),lambda:source_postflight(root,out,initial_coordinates,capture_deadline));result['source_postflight_verified']=True
 except BaseException:failed('source_postflight_unknown')
 # Capture work keeps its original absolute120s budget. Only resource
 # retirement uses up to the existing10s outer reserve, never a new capture.
 signal.alarm(0);cleanup_deadline=min(capture_deadline+STOP_SECONDS,time.monotonic()+STOP_SECONDS)
 operations=[('browser_closed',lambda:capture.close() if capture is not None else False),('driver_closed',lambda:(driver.stop() is None) if driver is not None else False),('server_closed',lambda:stop_server(server,saved))]
 for name,action in operations:
  try:result[name]=bounded_action(cleanup_deadline,action) is True
  except BaseException:result[name]=False
  if not result[name]:failed(name+'_unknown')
 if all(result[x] for x in ('server_closed','browser_closed','driver_closed')):
  try:result['work_removed']=bounded_action(cleanup_deadline,lambda:cleanup_work(out)) is True
  except BaseException:result['work_removed']=False
  if not result['work_removed']:failed('work_cleanup_unknown')
 valid=(result['error'] is None and result['primary_failure'] is None and result['capture_evidence_verified'] and result['source_postflight_verified'] and not result['secondary_errors'] and capture is not None and not capture.errors and all(result[x] for x in ('server_closed','browser_closed','driver_closed','work_removed')))
 result['status']='diagnostic_capture_complete_not_a_grade' if valid else 'UNKNOWN'
 if capture is not None:result['capture_errors']=list(capture.errors)

def run(root,out):
 initial_source_coordinates=source_preflight(root,out);need(not(out/'attempt.started.json').exists())
 sys.path.insert(0,str(root));beta=importlib.import_module('scripts.beta_perf_audit');perf=importlib.import_module('scripts.perf_audit');diag=importlib.import_module('scripts.beta_perf_diagnostics')
 for m in (beta,perf,diag):need(Path(m.__file__).resolve()==root/'scripts'/(m.__name__.split('.')[-1]+'.py'))
 need(importlib.metadata.version('playwright')=='1.59.0' and importlib.metadata.version('pydantic')=='2.7.4');writer=diag.ArtifactWriter(out,64*1024*1024);writer.write_json('attempt.started.json',{'classification':'NOT_GATE','source_sha':SOURCE_SHA,'collector_sha256':sha(regular(Path(__file__),262144)),'diagnostic_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':1,'trigger':'first_branch_push_created_true_deleted_strict_false','page':'analyze','viewport':'mobile','runs':1},control=True)
 started=time.monotonic();server=None;saved=None;capture=None;driver=None;result={'classification':'NOT_GATE','status':'UNKNOWN','historical888_grade_unchanged':'failed','retry':False,'server_closed':False,'browser_closed':False,'driver_closed':False,'work_removed':False,'error':None,'primary_failure':None,'secondary_errors':[],'capture_evidence_verified':False,'source_postflight_verified':False}
 def interrupt(signum,frame):
  raise KeyboardInterrupt()
 prior={s:signal.signal(s,interrupt) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)};capture_deadline=time.monotonic()+120;signal.alarm(120)
 try:
  writer.write_json('runner-before.json',diag.runner_snapshot());server=subprocess.Popen([sys.executable,'-I','-B','-m','http.server','4173','--bind','127.0.0.1','--directory',str(root/'web/frontend')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ['HOME'],'RUNNER_TRACKING_ID':os.environ.get('RUNNER_TRACKING_ID','')});saved=server_identity(server);writer.write_json('server-actor.json',{'pid':saved[0],'starttime':saved[1],'port':4173},control=True)
  deadline=time.monotonic()+10
  while not owned_listening(server):need(time.monotonic()<deadline);time.sleep(.05)
  from playwright.sync_api import sync_playwright,Error as NavigationError,TimeoutError as NavigationTimeout
  driver=sync_playwright().start();binary=Path(driver.chromium.executable_path);need(binary.is_file());h=hashlib.sha256()
  with binary.open('rb') as f:
   while b:=f.read(1048576):h.update(b)
  writer.write_json('versions.json',{'python':sys.version.split()[0],'playwright':importlib.metadata.version('playwright'),'browser_binary_sha256':h.hexdigest()},control=True)
  request,stream=beta._analyze_fixture();case=beta.PAGES['analyze'];normalized_base=fixture_audit_base(BASE,case.path);capture=Capture(writer,beta,perf,capture_deadline);original=beta._page_setup_factory('analyze',case,('http','127.0.0.1',4173),request,stream);validator=beta._page_validator('analyze',case)
  def setup(page,viewport,index):
   need(viewport=='mobile' and index==0);state=original(page,viewport,index);capture.setup(page);bind_navigation_observer(page,writer,capture,capture_deadline,NavigationError,NavigationTimeout);writer.write_json('browser-version.json',{'version':page.context.browser.version},control=True);return state
  perf.audit_one(driver,normalized_base,case.path,'mobile',beta.VIEWPORTS['mobile'],case.interaction_selector,runs=1,page_setup=setup,ready_selector=case.ready_selector,page_validator=lambda page,state:capture.validated(page,state,validator),post_interaction_validator=beta._post_interaction_validator('analyze'),interaction_mode=case.interaction_mode,run_evidence_sink=capture.sink)
  need(capture.final and capture.final['audit_status']=='passed' and capture.final['cleanup_status']=='passed' and capture.seen=={'pending','final'} and capture.captured and capture.metric_verified and not capture.errors)
  source_need(time.monotonic()<capture_deadline,'capture_deadline');result['capture_evidence_verified']=True
 except BaseException:result['error']='diagnostic_incomplete_no_retry'
 finally:
  try:
   finalize_diagnostic(result,capture,driver,server,saved,root,out,initial_source_coordinates,capture_deadline)
   writer.write_json('runner-after.json',diag.runner_snapshot());result['elapsed_seconds']=round(time.monotonic()-started,3);writer.write_json('diagnostic.json',result,control=True)
  finally:
   signal.alarm(0)
   for s,h in prior.items():signal.signal(s,h)
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();value=run(args.source_root,args.out);print(json.dumps({'classification':'NOT_GATE','status':value['status'],'retry':False}));raise SystemExit(0 if value['status']=='diagnostic_capture_complete_not_a_grade' else 2)
