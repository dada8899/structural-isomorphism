"""Fixed external-purpose registration and project-wide v18 money backstop.

No credential, payer identity, balance observation, sender or startup issuer is
created here. Registration consumes the existing canonical offline capability.
V17 declarations and all original Native triggers remain unchanged.
"""
from dataclasses import dataclass
import json,os,sqlite3,sys,threading
from uuid import UUID

from .external_first_answer_contract import CAP_UNITS,ContractError
from .external_first_answer_file_writer import MONEY_GUARD,_ACCOUNT_COLUMNS
from .provider_schemas import canonical

TABLE='research_external_owner_funding'
REGISTER_GUARD='research_external_v18_registration_allowed'
RETIRE_GUARD='research_external_v18_retirement_allowed'
SINGLE_UPPER=2_129_920
_REG={}
_RETIRE={}
_BINDING_COLUMNS=('id','purpose','account_id','local_binding_ref','owner_principal','owner_generation','owner_gate_id','credential_source','credential_incarnation','authorization_event_ref','payer_identity_status','payer_id','project_cap','single_upper','funding_epoch','status','version')
_UNKNOWN={
 'research_external_first_answer_runs':"state IN ('consumed','unknown')",
 'research_plan_native_runs':"state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')",
 'research_plan_dispatches':"state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')",
 'research_reservations':"status IN ('SENT','UNKNOWN')",
}

def _unknown_sql(excluding=None):
 parts=[]
 for table,predicate in _UNKNOWN.items():
  exclude=' AND id IS NOT '+excluding[1] if excluding is not None and excluding[0]==table else ''
  parts.append('EXISTS(SELECT 1 FROM main.'+table+' WHERE ('+predicate+')'+exclude+')')
 return '('+' OR '.join(parts)+')'

def _image(side):return 'json_array('+','.join(side+'.'+n for n in _ACCOUNT_COLUMNS)+')'
def _bounded(side):
 return '('+' AND '.join("typeof("+side+'.'+k+")='integer' AND "+side+'.'+k+' BETWEEN 0 AND 300000000' for k in ('settled','held','upper_booked'))+')'
_BAD_AMOUNT="EXISTS(SELECT 1 FROM main.research_funding_accounts a WHERE NOT "+_bounded('a')+")"
_USAGE='(SELECT coalesce(sum(CASE WHEN '+_bounded('a')+' THEN a.settled+a.held+a.upper_booked ELSE 300000001 END),0) FROM main.research_funding_accounts a)'
_BAD_UNITS="EXISTS(SELECT 1 FROM main.research_funding_accounts WHERE (currency!='CNY' OR scale!=6) AND (settled>0 OR held>0 OR upper_booked>0))"
_OLD_TOTAL='(OLD.settled+OLD.held+OLD.upper_booked)'
_NEW_TOTAL='(NEW.settled+NEW.held+NEW.upper_booked)'
_ROW_EXACT='('+_bounded('OLD')+' AND '+_bounded('NEW')+')'
_NET_INCREASE='(CASE WHEN '+_ROW_EXACT+' THEN '+_NEW_TOTAL+'>'+_OLD_TOTAL+' ELSE 0 END)'
_NONINCREASING='(NEW.settled<=OLD.settled AND NEW.held<=OLD.held AND NEW.upper_booked<=OLD.upper_booked)'
def _binding_image(side):return 'json_array('+','.join(side+'.'+n for n in _BINDING_COLUMNS)+')'

def declarations():
 ddl=["""CREATE TABLE research_external_owner_funding (
 id INTEGER PRIMARY KEY CHECK(id=1),purpose TEXT NOT NULL CHECK(purpose='external-first-answer-question-v1'),
 account_id TEXT NOT NULL UNIQUE REFERENCES research_funding_accounts(id),local_binding_ref TEXT NOT NULL UNIQUE,
 owner_principal TEXT REFERENCES research_principals(id),owner_generation TEXT CHECK(length(owner_generation)=32),
 owner_gate_id TEXT,credential_source TEXT NOT NULL CHECK(credential_source='owner_supplied'),
 credential_incarnation TEXT NOT NULL UNIQUE,authorization_event_ref TEXT NOT NULL UNIQUE,
 payer_identity_status TEXT NOT NULL CHECK(payer_identity_status='unknown'),payer_id TEXT CHECK(payer_id IS NULL),
 project_cap INTEGER NOT NULL CHECK(project_cap=300000000),single_upper INTEGER NOT NULL CHECK(single_upper=2129920),
 funding_epoch INTEGER NOT NULL CHECK(funding_epoch=1),
 status TEXT NOT NULL CHECK(status IN ('active','retired')),version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version>0),
 CHECK((status='active' AND owner_principal IS NOT NULL AND owner_generation IS NOT NULL AND owner_gate_id IS NOT NULL)
 OR (status='retired' AND owner_principal IS NULL AND owner_generation IS NULL AND owner_gate_id IS NULL)))""",
  "CREATE TRIGGER research_external_v18_binding_insert BEFORE INSERT ON "+TABLE+" BEGIN SELECT CASE WHEN "+REGISTER_GUARD+"('binding',NEW.account_id)!=1 THEN RAISE(ABORT,'external v18 registration required') END; END",
  "CREATE TRIGGER research_external_v18_binding_no_replace BEFORE INSERT ON "+TABLE+" WHEN EXISTS(SELECT 1 FROM "+TABLE+") BEGIN SELECT RAISE(ABORT,'external purpose already registered'); END",
  "CREATE TRIGGER research_external_v18_binding_no_update BEFORE UPDATE ON "+TABLE+" BEGIN SELECT CASE WHEN coalesce("+RETIRE_GUARD+"("+_binding_image('OLD')+","+_binding_image('NEW')+"),0)!=1 THEN RAISE(ABORT,'external purpose binding immutable') END; END",
  "CREATE TRIGGER research_external_v18_binding_no_delete BEFORE DELETE ON "+TABLE+" BEGIN SELECT RAISE(ABORT,'external purpose binding retained'); END",
  "CREATE TRIGGER research_external_v18_account_insert BEFORE INSERT ON research_funding_accounts BEGIN SELECT CASE WHEN "+REGISTER_GUARD+"('account',NEW.id)!=1 OR NEW.settled!=0 OR NEW.held!=0 OR NEW.upper_booked!=0 THEN RAISE(ABORT,'external zero account registration required') END; END",
  "CREATE TRIGGER research_external_v18_money BEFORE UPDATE ON research_funding_accounts WHEN EXISTS(SELECT 1 FROM "+TABLE+" WHERE account_id=OLD.id) BEGIN SELECT CASE WHEN coalesce("+MONEY_GUARD+"("+_image('OLD')+","+_image('NEW')+"),0)!=1 THEN RAISE(ABORT,'external owned money writer required') END; END",
  "CREATE TRIGGER research_external_v18_project_cap BEFORE UPDATE OF settled,held,upper_booked ON research_funding_accounts BEGIN "
  "SELECT CASE WHEN NOT "+_ROW_EXACT+" AND NOT "+_NONINCREASING+" THEN RAISE(ABORT,'unverified legacy money delta') END; "
  "SELECT CASE WHEN "+_NET_INCREASE+" THEN CASE WHEN "+_BAD_UNITS+" OR "+_BAD_AMOUNT+" OR "+_USAGE+"-"+_OLD_TOTAL+"+"+_NEW_TOTAL+">300000000 THEN RAISE(ABORT,'shared project cap exhausted') END END; "
  "SELECT CASE WHEN "+_NET_INCREASE+" AND "+_unknown_sql()+" THEN RAISE(ABORT,'shared project unknown reconcile only') END; END",

 ]
 for table in _UNKNOWN:
  if table=='research_reservations':condition="NEW.status='SENT' AND OLD.status!='SENT'"
  else:condition="NEW.state IN ('reserved','consumed') AND NEW.state IS NOT OLD.state"
  ddl.append("CREATE TRIGGER "+table+"_v18_project_unknown BEFORE UPDATE ON "+table+" WHEN "+condition+
    " BEGIN SELECT CASE WHEN "+_BAD_UNITS+" OR "+_BAD_AMOUNT+" OR "+_USAGE+">300000000 THEN RAISE(ABORT,'shared project cap exhausted') END; SELECT CASE WHEN "+_unknown_sql((table,'NEW.id'))+" THEN RAISE(ABORT,'shared project unknown reconcile only') END; END")
  insert_condition="NEW.status='SENT'" if table=='research_reservations' else "NEW.state IN ('reserved','consumed')"
  ddl.append("CREATE TRIGGER "+table+"_v18_project_unknown_insert BEFORE INSERT ON "+table+" WHEN "+insert_condition+
    " BEGIN SELECT CASE WHEN "+_BAD_UNITS+" OR "+_BAD_AMOUNT+" OR "+_USAGE+">300000000 THEN RAISE(ABORT,'shared project cap exhausted') END; SELECT CASE WHEN "+_unknown_sql((table,'NEW.id'))+" THEN RAISE(ABORT,'shared project unknown reconcile only') END; END")
 return tuple(ddl)
DDL=declarations()

def project_usage(conn):
 if conn.execute('SELECT 1 FROM main.research_funding_accounts WHERE (currency!=\'CNY\' OR scale!=6) AND (settled>0 OR held>0 OR upper_booked>0) LIMIT 1').fetchone():
  raise ContractError('project_currency_unverified')
 value=0
 for row in conn.execute('SELECT settled,held,upper_booked FROM main.research_funding_accounts'):
  if any(type(v) is not int or v<0 for v in row):raise ContractError('project_usage_unverified')
  value+=sum(row)  # Python exact integers, never SQLite REAL promotion.

 return value

def project_unresolved(conn,*,excluding=None):
 if excluding is not None and (type(excluding) is not tuple or len(excluding)!=2 or excluding[0] not in _UNKNOWN or type(excluding[1]) is not str):
  raise ContractError('project_unknown_exclusion_invalid')
 for table,predicate in _UNKNOWN.items():
  params=();tail=''
  if excluding is not None and excluding[0]==table:tail=' AND id IS NOT ?';params=(excluding[1],)
  if conn.execute('SELECT 1 FROM main.'+table+' WHERE ('+predicate+')'+tail+' LIMIT 1',params).fetchone():return True
 return False

def require_room(conn,upper,*,excluding=None,consuming=False):
 """Reserve adds upper once; consume/first-write rechecks usage without adding it."""
 if not conn.in_transaction or type(upper) is not int or not 1<=upper<=SINGLE_UPPER:
  raise ContractError('project_reservation_bound')
 if project_unresolved(conn,excluding=excluding):raise ContractError('project_unknown_reconcile_only')
 used=project_usage(conn)
 if used+(0 if consuming else upper)>CAP_UNITS:raise ContractError('shared_project_budget_exhausted')
 return used

def read_binding(conn):
    """Exact fixed local purpose facts, not a payer identity or live grant."""
    from .store import ResearchStore
    ResearchStore._check_v18(conn)
    row=conn.execute('SELECT * FROM main.'+TABLE+' WHERE id=1').fetchone()
    if row is None:return None
    names=_BINDING_COLUMNS
    return dict(zip(names,row))


def _registration_frame(conn,state):
 frame=sys._getframe(1)
 try:
  while frame:
   if (frame.f_code is _register.__code__ and frame.f_globals is globals()
       and frame.f_locals.get('conn') is conn and frame.f_locals.get('cap') is state['cap']
       and frame.f_locals.get('target') is state['target']):return True
   frame=frame.f_back
 finally:del frame
 return False


def install_hook(conn):
 pid=os.getpid()
 def allowed(kind,account):
  state=_REG.get(id(conn))
  if not state or state['conn'] is not conn or pid!=os.getpid() or not conn.in_transaction:return 0
  try:_require_cap(state['target'],state['cap'],conn)
  except (ContractError,TypeError):return 0
  if state.get('thread')!=threading.get_ident() or not _registration_frame(conn,state):return 0
  try:state['cap'].require(state['target'])
  except (PermissionError,OSError,sqlite3.Error):return 0
  return int(kind in ('binding','account') and account==state['account'])
 conn.create_function(REGISTER_GUARD,2,allowed)
 conn.create_function(RETIRE_GUARD,2,lambda before,after:allowed_retirement(conn,before,after))
 conn.create_function('research_external_v18_guard_version',0,lambda:18 if pid==os.getpid() else 0)

def require_hook(conn):
 if tuple(conn.execute('SELECT research_external_v18_guard_version(),'+REGISTER_GUARD+"('account','')").fetchone())!=(18,0):
  raise ContractError('external_v18_closed_hook_required')

def statement_allowed(conn,action,table,column):
 if table!=TABLE or action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE):return True
 state=_REG.get(id(conn))
 if action==sqlite3.SQLITE_UPDATE:return id(conn) in _RETIRE and _retirement_context(conn,_RETIRE[id(conn)])
 if not (state and state['conn'] is conn and conn.in_transaction and state['pid']==os.getpid() and state.get('thread')==threading.get_ident() and action==sqlite3.SQLITE_INSERT):return False
 try:_require_cap(state['target'],state['cap'],conn);return _registration_frame(conn,state)
 except (ContractError,PermissionError,OSError,sqlite3.Error):return False

@dataclass(frozen=True,slots=True)
class OwnerKeyRegistration:
 account_id:str
 local_binding_ref:str
 owner_principal:str
 owner_generation:str
 owner_gate_id:str
 credential_incarnation:str
 authorization_event_ref:str
 def validate(self):
  for value in (self.account_id,self.local_binding_ref,self.owner_principal,self.owner_gate_id,self.credential_incarnation,self.authorization_event_ref):
   if type(value) is not str or str(UUID(value,version=4))!=value:raise ContractError('external_registration_identity')
  if type(self.owner_generation) is not str or len(self.owner_generation)!=32 or any(c not in '0123456789abcdef' for c in self.owner_generation):
   raise ContractError('external_registration_generation')

def _require_cap(target,cap,conn):
 from .formula_runtime import FormulaMaintenance,_OfflineFormulaTarget
 if type(target) is not _OfflineFormulaTarget or type(cap) is not FormulaMaintenance or cap.conn is not conn or cap.store is not target or cap.pid!=os.getpid():
  raise ContractError('external_registration_real_maintenance_required')
 cap.require(target)

def _register(target,cap,record):
 frame=sys._getframe(1)
 try:
  if frame.f_code is not apply_owner_key_v18.__code__ or frame.f_globals is not globals():raise ContractError('external_registration_fixed_entry_required')
 finally:del frame
 _require_cap(target,cap,cap.conn)
 if type(record) is not OwnerKeyRegistration:raise ContractError('external_registration_record_required')
 record.validate();conn=cap.conn
 actual=conn.execute('''SELECT p.id,p.session_generation,p.gate_id FROM main.research_principals p
  JOIN main.auth_users u ON u.email=p.normalized_email WHERE p.id=? AND p.status='active' AND u.lifecycle='active'
  AND u.session_generation=p.session_generation''',(record.owner_principal,)).fetchone()
 if actual is None or tuple(actual)!=(record.owner_principal,record.owner_generation,record.owner_gate_id):
  raise ContractError('external_registration_owner_changed')
 values=(1,'external-first-answer-question-v1',record.account_id,record.local_binding_ref,record.owner_principal,
  record.owner_generation,record.owner_gate_id,'owner_supplied',record.credential_incarnation,record.authorization_event_ref,
  'unknown',None,CAP_UNITS,SINGLE_UPPER,1,'active',1)
 existing=conn.execute('SELECT * FROM main.'+TABLE+' WHERE id=1').fetchone()
 if existing:
  if tuple(existing)!=values:raise ContractError('external_purpose_cannot_rebind')
  return
 _REG[id(conn)]={'conn':conn,'target':target,'cap':cap,'account':record.account_id,'pid':os.getpid(),'thread':threading.get_ident()}
 try:
  conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,scale,status,cap) VALUES(?,?,'live','deepseek','CNY',6,'unverified',0)",(record.account_id,record.local_binding_ref))
  conn.execute('INSERT INTO '+TABLE+' VALUES('+','.join('?' for _ in values)+')',values)
 finally:_REG.pop(id(conn),None)

def apply_owner_key_v18(target,cap,record):
 """Explicit canonical offline17->18 + first registration, atomically, no loader."""
 from .formula_runtime import FormulaMaintenance,_OfflineFormulaTarget,_check_profile
 from .store import ResearchStore
 if type(target) is not _OfflineFormulaTarget or type(cap) is not FormulaMaintenance or type(record) is not OwnerKeyRegistration:
  raise ContractError('external_v18_offline_capability_required')
 cap.require(target);conn=cap.conn;conn.execute('BEGIN EXCLUSIVE')
 try:
  version=_check_profile(conn,target,(17,18))
  if version==17:
   for statement in DDL:conn.execute(statement)
   if conn.execute('UPDATE main.research_schema SET version=18 WHERE id=1 AND version=17').rowcount!=1:raise ContractError('external_v18_schema_CAS')
  _register(target,cap,record);ResearchStore._check_v18(conn);cap.require(target);conn.commit()
 except BaseException:conn.rollback();raise
 return {'schema':18,'credential_source':'owner_supplied','payer_identity':'unknown','new_account':record.account_id,'may_send':False}

def _retirement_context(conn,state):
 from .authorization import OwnerGateLease
 from .external_first_answer_erasure import require_deletion_frame
 if (not state or state['conn'] is not conn or state['pid']!=os.getpid() or state['thread']!=threading.get_ident()
     or not conn.in_transaction or type(state['lease']) is not OwnerGateLease):return False
 try:
  require_deletion_frame(conn);state['lease'].identity
  job=conn.execute('SELECT owner_email,session_generation,gate_id,state FROM main.auth_deletion_jobs WHERE id=?',(state['job_id'],)).fetchone()
  principal=conn.execute('SELECT normalized_email,session_generation,gate_id,status FROM main.research_principals WHERE id=?',(state['principal'],)).fetchone()
  return bool(job and principal and tuple(principal)==(job[0],job[1],job[2],'deleting') and job[3]=='pending')
 except (PermissionError,OSError,sqlite3.Error):return False

def allowed_retirement(conn,before,after):
 state=_RETIRE.get(id(conn))
 if not _retirement_context(conn,state):return 0
 try:
  old,new=json.loads(before),json.loads(after)
  return int(len(old)==len(new)==len(_BINDING_COLUMNS) and canonical(old)==state['before'] and canonical(new)==state['after'])
 except (ValueError,TypeError):return 0

def retire_for_deletion(conn,store,owner_lease,principal_id,job_id):
 """Only existing verified account deletion; preserves account, cap and spent."""
 from .external_first_answer_erasure import require_deletion_frame,require_no_pending
 from .paid_control import verify_deletion_origin
 require_deletion_frame(conn)
 job=verify_deletion_origin(conn,store=store,lease=owner_lease,job_id=job_id)
 row=conn.execute('SELECT * FROM main.'+TABLE+' WHERE id=1').fetchone()
 if row is None or row['status']=='retired' or row['owner_principal']!=principal_id:return 0
 if (row['owner_generation'],row['owner_gate_id'])!=(job['session_generation'],job['gate_id']):
  raise PermissionError('external retirement owner mismatch')
 require_no_pending(conn,principal_id)
 for table,predicate in _UNKNOWN.items():
  if conn.execute('SELECT 1 FROM main.'+table+' WHERE account_id=? AND ('+predicate+') LIMIT 1',(row['account_id'],)).fetchone():
   from .errors import ResearchError
   raise ResearchError('RECONCILIATION_REQUIRED',503,'仍有未核对的费用，未清除绑定或释放占额。')
 old=list(row);new=list(old)
 for key in ('owner_principal','owner_generation','owner_gate_id'):new[_BINDING_COLUMNS.index(key)]=None
 new[_BINDING_COLUMNS.index('status')]='retired';new[_BINDING_COLUMNS.index('version')]+=1
 if id(conn) in _RETIRE:raise PermissionError('nested external retirement')
 _RETIRE[id(conn)]={'conn':conn,'pid':os.getpid(),'thread':threading.get_ident(),'lease':owner_lease,
  'job_id':job_id,'principal':principal_id,'before':canonical(old),'after':canonical(new)}
 try:
  if not _retirement_context(conn,_RETIRE[id(conn)]):raise PermissionError('external retirement origin changed')
  changed=conn.execute('UPDATE main.'+TABLE+" SET owner_principal=NULL,owner_generation=NULL,owner_gate_id=NULL,status='retired',version=version+1 WHERE id=1 AND status='active' AND version=? AND owner_principal=?",(row['version'],principal_id)).rowcount
  if changed!=1:raise PermissionError('external retirement CAS failed')
 finally:_RETIRE.pop(id(conn),None)
 return 1
