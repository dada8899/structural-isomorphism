"""Candidate only: one fixed Analyze/mobile NOT_GATE capture; no grade/retry path."""
import argparse,hashlib,importlib,importlib.metadata,json,math,os,re,signal,stat,subprocess,sys,time
from pathlib import Path
from urllib.parse import urlsplit
SOURCE_SHA='88830a33000c3190901efd629081e9c41e259108'
BRANCH='refs/heads/codex/structure-analyze-mobile-diagnostic-88830-attempt1'
BASE='http://127.0.0.1:4173'
MAX_PROJECTED_BYTES=32*1024*1024
MAX_EVENTS=100000
STOP_SECONDS=10
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
 need(git(root,'rev-parse','HEAD')==SOURCE_SHA and not git(root,'status','--porcelain','--untracked-files=all'))
 for name,pin in PINS.items():need(sha(regular(root/name,4*1024*1024))==pin)
def number(v):need(type(v) in (int,float) and math.isfinite(v));return v
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
 def __init__(self,writer,beta,perf):
  self.writer,self.beta,self.perf=writer,beta,perf;self.page=self.cdp=None;self.tracing=False;self.stop_requested=False;self.stop_deadline=None;self.terminal_received=False;self.loss=None;self.projected=[];self.projected_bytes=0;self.source_events=0;self.overflow=False;self.ready=[];self.seen=set();self.final=None;self.captured=False;self.errors=[];self.browser=None
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
  phase=sample.get('cleanup_status');need(phase in ('pending','passed','failed'));key='pending' if phase=='pending' else 'final';need(key not in self.seen);self.seen.add(key);safe=self.beta._checkpoint_run_evidence(sample);self.writer.write_json('audit-'+key+'.json',{'classification':'NOT_GATE','sample':safe})
  if key=='final':self.final=safe;return
  try:
   need(not self.captured);self.captured=True;raw=snapshot_projection(self.page.evaluate(SNAPSHOT),self.ready);self.writer.write_json('browser-window.json',raw)
   fcp=raw['fcp'];parts=[]
   for task in raw['longTasks']:
    overlap=max(0,min(task['start']+task['duration'],fcp+5000)-max(task['start'],fcp));parts.append({'start':task['start'],'duration':task['duration'],'clipped_overlap':overlap,'blocking_ms':max(0,overlap-50)})
   tbt=self.perf.compute_tbt(raw['longTasks'],fcp,fcp+5000);self.writer.write_json('tbt-contributions.json',{'classification':'NOT_GATE','tasks':parts,'recomputed_tbt_ms':tbt,'original_single_sample_tbt_ms':safe.get('tbt_ms'),'matches_original_sample':safe.get('tbt_ms')==round(tbt,1),'historical888_grade_unchanged':'failed'})
   need(safe.get('tbt_ms')==round(tbt,1));self.end_trace()
  except BaseException:
   self.errors.append('capture_incomplete');raise
  finally:self.close_trace()
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
  self.stop_deadline=time.monotonic()+STOP_SECONDS;self.stop_requested=True;self.tracing=False;self.cdp.send('Tracing.end')
  while not self.terminal_received and time.monotonic()<self.stop_deadline:self.page.wait_for_timeout(20)
  if not self.terminal_received:self.error('trace_terminal_missing')
  if time.monotonic()>self.stop_deadline:self.error('trace_stop_deadline')
  if self.source_events==0 or not self.projected:self.error('trace_data_missing')
  trusted=self.terminal_received and self.loss is False and not self.overflow and not self.errors
  self.write_trace(trusted);need(trusted)
 def close_trace(self):
  if self.cdp is None:return
  try:
   if self.tracing and not self.stop_requested:
    self.stop_requested=True;self.tracing=False;self.cdp.send('Tracing.end')
   self.cdp.detach()
  except BaseException:self.error('trace_close_unknown')
  finally:self.cdp=None
 def close(self):
  self.close_trace()
  if self.browser is not None and self.browser.is_connected():
   try:self.browser.close()
   except BaseException:self.error('browser_close_unknown')
  return self.browser is not None and not self.browser.is_connected() and not self.errors

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

def run(root,out):
 validate_scope(root,out,os.environ);need(out.is_dir() and out.stat().st_uid==os.getuid() and stat.S_IMODE(out.stat().st_mode)==0o700 and not(out/'attempt.started.json').exists())
 sys.path.insert(0,str(root));beta=importlib.import_module('scripts.beta_perf_audit');perf=importlib.import_module('scripts.perf_audit');diag=importlib.import_module('scripts.beta_perf_diagnostics')
 for m in (beta,perf,diag):need(Path(m.__file__).resolve()==root/'scripts'/(m.__name__.split('.')[-1]+'.py'))
 need(importlib.metadata.version('playwright')=='1.59.0' and importlib.metadata.version('pydantic')=='2.7.4');writer=diag.ArtifactWriter(out,64*1024*1024);writer.write_json('attempt.started.json',{'classification':'NOT_GATE','source_sha':SOURCE_SHA,'collector_sha256':sha(regular(Path(__file__),262144)),'diagnostic_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'attempt':1,'trigger':'first_branch_push_created_true_deleted_strict_false','page':'analyze','viewport':'mobile','runs':1},control=True)
 started=time.monotonic();server=None;saved=None;capture=None;driver=None;result={'classification':'NOT_GATE','status':'UNKNOWN','historical888_grade_unchanged':'failed','retry':False,'server_closed':False,'browser_closed':False,'driver_closed':False,'work_removed':False,'error':None};cleaning=False
 def interrupt(signum,frame):
  if not cleaning:raise KeyboardInterrupt()
 prior={s:signal.signal(s,interrupt) for s in (signal.SIGTERM,signal.SIGINT,signal.SIGALRM)};signal.alarm(120)
 try:
  writer.write_json('runner-before.json',diag.runner_snapshot());server=subprocess.Popen([sys.executable,'-I','-B','-m','http.server','4173','--bind','127.0.0.1','--directory',str(root/'web/frontend')],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,env={'PATH':os.environ['PATH'],'LANG':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','HOME':os.environ['HOME'],'RUNNER_TRACKING_ID':os.environ.get('RUNNER_TRACKING_ID','')});saved=server_identity(server);writer.write_json('server-actor.json',{'pid':saved[0],'starttime':saved[1],'port':4173},control=True)
  deadline=time.monotonic()+10
  while not owned_listening(server):need(time.monotonic()<deadline);time.sleep(.05)
  from playwright.sync_api import sync_playwright
  driver=sync_playwright().start();binary=Path(driver.chromium.executable_path);need(binary.is_file());h=hashlib.sha256()
  with binary.open('rb') as f:
   while b:=f.read(1048576):h.update(b)
  writer.write_json('versions.json',{'python':sys.version.split()[0],'playwright':importlib.metadata.version('playwright'),'browser_binary_sha256':h.hexdigest()},control=True)
  request,stream=beta._analyze_fixture();case=beta.PAGES['analyze'];capture=Capture(writer,beta,perf);original=beta._page_setup_factory('analyze',case,('http','127.0.0.1',4173),request,stream);validator=beta._page_validator('analyze',case)
  def setup(page,viewport,index):
   need(viewport=='mobile' and index==0);state=original(page,viewport,index);capture.setup(page);writer.write_json('browser-version.json',{'version':page.context.browser.version},control=True);return state
  perf.audit_one(driver,BASE,case.path,'mobile',beta.VIEWPORTS['mobile'],case.interaction_selector,runs=1,page_setup=setup,ready_selector=case.ready_selector,page_validator=lambda page,state:capture.validated(page,state,validator),post_interaction_validator=beta._post_interaction_validator('analyze'),interaction_mode=case.interaction_mode,run_evidence_sink=capture.sink)
  need(capture.final and capture.final['audit_status']=='passed' and capture.final['cleanup_status']=='passed' and capture.seen=={'pending','final'} and capture.captured and not capture.errors)
  validate_scope(root,out,os.environ);result['status']='diagnostic_capture_complete_not_a_grade'
 except BaseException:result['error']='diagnostic_incomplete_no_retry'
 finally:
  cleaning=True;signal.alarm(0)
  if capture is not None:result['browser_closed']=capture.close()
  if driver is not None:
   try:driver.stop();result['driver_closed']=True
   except BaseException:result['error']='driver_close_unknown'
  try:result['server_closed']=stop_server(server,saved)
  except BaseException:result['error']='server_close_unknown'
  if all(result[x] for x in ('server_closed','browser_closed','driver_closed')):
   try:result['work_removed']=cleanup_work(out)
   except BaseException:result['error']='work_cleanup_unknown'
  if not all(result[x] for x in ('server_closed','browser_closed','driver_closed','work_removed')):result['status']='UNKNOWN'
  try:writer.write_json('runner-after.json',diag.runner_snapshot());result['elapsed_seconds']=round(time.monotonic()-started,3);writer.write_json('diagnostic.json',result,control=True)
  finally:
   for s,h in prior.items():signal.signal(s,h)
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();value=run(args.source_root,args.out);print(json.dumps({'classification':'NOT_GATE','status':value['status'],'retry':False}));raise SystemExit(0 if value['status']=='diagnostic_capture_complete_not_a_grade' else 2)
