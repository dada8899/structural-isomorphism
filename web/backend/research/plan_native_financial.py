"""Financial9 native-plan domain. Legacy Financial8 declarations stay immutable."""
from functools import lru_cache
import json,os,sqlite3
from .errors import ResearchError

VERSION=9
RESEARCH_VERSION=13
_FACTORY=object()
_WRITES={}
MONEY='research_funding_accounts'
TABLES=(
"""CREATE TABLE research_plan_native_funding (
 id INTEGER PRIMARY KEY CHECK(id=1),mode TEXT NOT NULL CHECK(mode IN ('controlled_fixture','native_live')),
 state TEXT NOT NULL CHECK(state IN ('authorized','blocked','retired')),
 principal_id TEXT,generation TEXT,owner_gate_id TEXT NOT NULL,authority_ref TEXT NOT NULL,authority_digest TEXT NOT NULL CHECK(length(authority_digest)=64),
 account_id TEXT NOT NULL UNIQUE REFERENCES research_funding_accounts(id),economic_binding TEXT NOT NULL UNIQUE,
 credential_incarnation TEXT NOT NULL,grant_epoch INTEGER NOT NULL CHECK(typeof(grant_epoch)='integer' AND grant_epoch>0),
 approved_cap_units INTEGER NOT NULL CHECK(typeof(approved_cap_units)='integer' AND approved_cap_units>=0),
 risk_margin_units INTEGER NOT NULL CHECK(typeof(risk_margin_units)='integer' AND risk_margin_units>=0),
 runtime_digest TEXT NOT NULL CHECK(length(runtime_digest)=64),network_ref TEXT NOT NULL,
 balance_claim TEXT,balance_nonce TEXT,version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
 CHECK((state='retired' AND principal_id IS NULL AND generation IS NULL) OR (state!='retired' AND principal_id IS NOT NULL AND generation IS NOT NULL)))""",
"""CREATE TABLE research_plan_native_previews (
 id TEXT PRIMARY KEY,research_id TEXT REFERENCES research_controls(id),principal_id TEXT NOT NULL,
 input_revision INTEGER NOT NULL CHECK(typeof(input_revision)='integer' AND input_revision>0),
 research_version INTEGER NOT NULL CHECK(typeof(research_version)='integer' AND research_version>0),
 consent_json TEXT CHECK(consent_json IS NULL OR (json_valid(consent_json) AND length(CAST(consent_json AS BLOB))<=32768)),
 consent_digest TEXT NOT NULL CHECK(length(consent_digest)=64),request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
 quote_json TEXT NOT NULL CHECK(json_valid(quote_json) AND length(CAST(quote_json AS BLOB))<=16384),
 expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer'),state TEXT NOT NULL CHECK(state IN ('draft','confirmed','closed')),
 task_id TEXT UNIQUE,key_digest TEXT NOT NULL,operation_digest TEXT NOT NULL,UNIQUE(principal_id,research_id,key_digest))""",
"""CREATE TABLE research_plan_native_runs (
 id TEXT PRIMARY KEY,task_id TEXT NOT NULL UNIQUE REFERENCES research_tasks(id),result_ref TEXT NOT NULL UNIQUE,
 preview_id TEXT NOT NULL UNIQUE REFERENCES research_plan_native_previews(id),account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
 financial_version INTEGER NOT NULL CHECK(financial_version=9),consent_json TEXT,consent_digest TEXT NOT NULL CHECK(length(consent_digest)=64),
 admission_json TEXT CHECK(admission_json IS NULL OR (json_valid(admission_json) AND length(CAST(admission_json AS BLOB))<=65536)),admission_digest TEXT,
 upper INTEGER NOT NULL CHECK(typeof(upper)='integer' AND upper>=0),nonce TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL CHECK(state IN ('approved','reserved','consumed','unknown','returned','closed')),
 cost_state TEXT NOT NULL CHECK(cost_state IN ('unreserved','held','upper_booked','unknown')),
 cleanup_state TEXT NOT NULL CHECK(cleanup_state IN ('pending','clean','uncertain')),
 version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
 receipt_json TEXT,usage_json TEXT,result_json TEXT,commit_json TEXT,safe_code TEXT,
 CHECK(consent_json IS NULL OR (json_valid(consent_json) AND length(CAST(consent_json AS BLOB))<=32768)),
 CHECK(receipt_json IS NULL OR (json_valid(receipt_json) AND length(CAST(receipt_json AS BLOB))<=8192)),
 CHECK(usage_json IS NULL OR (json_valid(usage_json) AND length(CAST(usage_json AS BLOB))<=4096)),
 CHECK(result_json IS NULL OR (json_valid(result_json) AND length(CAST(result_json AS BLOB))<=32768)),
 CHECK(commit_json IS NULL OR (json_valid(commit_json) AND length(CAST(commit_json AS BLOB))<=8192)),
 CHECK(state NOT IN ('consumed','returned') OR (admission_json IS NOT NULL AND length(admission_digest)=64)),
 CHECK(state!='returned' OR (receipt_json IS NOT NULL AND usage_json IS NOT NULL AND commit_json IS NOT NULL)))""",
)
NAMES=tuple(s.split()[2] for s in TABLES)


def overlay(tables):
    result=dict(tables)
    result['research_tasks']=result['research_tasks'].replace("'funded-plan-v1'","'funded-plan-v1','native-plan-v1'").replace("'local_math'","'local_math','controlled_fixture','native_live'")
    return result


@lru_cache(maxsize=1)
def declarations():
    from .store import ResearchStore
    ddls=list(TABLES)
    for ddl in TABLES:
        table=ddl.split()[2];columns=[p[0] for p in ResearchStore._declared_columns(ddl)]
        def image(prefix):return "json_object('rowid',"+prefix+'.rowid,'+','.join("'"+k+"',"+prefix+'.'+k for k in columns)+')'
        for op in ('INSERT','UPDATE','DELETE'):
            before="'null'" if op=='INSERT' else image('OLD');after="'null'" if op=='DELETE' else image('NEW')
            ddls.append(f"CREATE TRIGGER {table}_f9_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT CASE WHEN research_plan_native_write_allowed('{table}','{op}',{before},{after})!=1 THEN RAISE(ABORT,'native Financial9 writer required') END; END")
        keys=['NEW.rowid IS OLD.rowid','NEW.id IS OLD.id']
        if table.endswith('previews'):keys+=['NEW.principal_id IS OLD.principal_id AND NEW.research_id IS OLD.research_id AND NEW.key_digest IS OLD.key_digest','NEW.task_id IS NOT NULL AND NEW.task_id IS OLD.task_id']
        if table.endswith('runs'):keys+=['NEW.task_id IS OLD.task_id','NEW.result_ref IS OLD.result_ref','NEW.preview_id IS OLD.preview_id','NEW.nonce IS OLD.nonce']
        ddls.append(f"CREATE TRIGGER {table}_f9_no_replace BEFORE INSERT ON {table} WHEN EXISTS(SELECT 1 FROM {table} OLD WHERE "+' OR '.join('('+k+')' for k in keys)+") BEGIN SELECT RAISE(ABORT,'Financial9 replacement forbidden'); END")
        ddls.append(f"CREATE TRIGGER {table}_f9_identity BEFORE UPDATE ON {table} WHEN NEW.rowid IS NOT OLD.rowid OR NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Financial9 identity immutable'); END")
    # Money stays in the shared economic account, never in a second wallet.
    ddls.extend((
      "CREATE TRIGGER research_native_money_control BEFORE UPDATE OF settled,held,upper_booked,funding_epoch,cap,status,binding_id ON research_funding_accounts WHEN EXISTS(SELECT 1 FROM research_plan_native_funding WHERE account_id=OLD.id) BEGIN SELECT CASE WHEN research_plan_native_money_allowed(OLD.id)!=1 THEN RAISE(ABORT,'native plan money authority required') END; END",
      "CREATE TRIGGER research_native_money_no_replace BEFORE INSERT ON research_funding_accounts WHEN EXISTS(SELECT 1 FROM research_funding_accounts a JOIN research_plan_native_funding f ON f.account_id=a.id WHERE NEW.rowid=a.rowid OR NEW.id=a.id OR NEW.binding_id=a.binding_id) BEGIN SELECT RAISE(ABORT,'native economic account retained'); END",
      "CREATE TRIGGER research_native_money_no_delete BEFORE DELETE ON research_funding_accounts WHEN EXISTS(SELECT 1 FROM research_plan_native_funding WHERE account_id=OLD.id) BEGIN SELECT RAISE(ABORT,'native economic account retained'); END",
      "CREATE TRIGGER research_native_funding_domain BEFORE UPDATE ON research_plan_native_funding WHEN NEW.mode IS NOT OLD.mode OR NEW.authority_ref IS NOT OLD.authority_ref OR NEW.authority_digest IS NOT OLD.authority_digest OR NEW.owner_gate_id IS NOT OLD.owner_gate_id OR NEW.account_id IS NOT OLD.account_id OR NEW.economic_binding IS NOT OLD.economic_binding OR NEW.approved_cap_units IS NOT OLD.approved_cap_units OR NEW.risk_margin_units IS NOT OLD.risk_margin_units OR NEW.runtime_digest IS NOT OLD.runtime_digest OR NEW.network_ref IS NOT OLD.network_ref OR NEW.credential_incarnation IS NOT OLD.credential_incarnation OR NEW.grant_epoch IS NOT OLD.grant_epoch OR NEW.version!=OLD.version+1 OR (NEW.principal_id IS NOT OLD.principal_id AND NOT (NEW.state='retired' AND NEW.principal_id IS NULL)) OR (NEW.generation IS NOT OLD.generation AND NOT (NEW.state='retired' AND NEW.generation IS NULL)) OR (OLD.state='retired' AND NEW.state!='retired') BEGIN SELECT RAISE(ABORT,'native funding cannot be rebound'); END",
      "CREATE TRIGGER research_native_preview_domain BEFORE UPDATE ON research_plan_native_previews WHEN NEW.principal_id IS NOT OLD.principal_id OR NEW.input_revision IS NOT OLD.input_revision OR NEW.research_version IS NOT OLD.research_version OR NEW.consent_digest IS NOT OLD.consent_digest OR NEW.request_digest IS NOT OLD.request_digest OR NEW.quote_json IS NOT OLD.quote_json OR NEW.expires_at IS NOT OLD.expires_at OR NEW.key_digest IS NOT OLD.key_digest OR NEW.operation_digest IS NOT OLD.operation_digest OR (NEW.consent_json IS NOT OLD.consent_json AND NOT (NEW.state='closed' AND NEW.consent_json IS NULL)) OR (OLD.task_id IS NOT NULL AND NEW.task_id IS NOT OLD.task_id) OR (NEW.research_id IS NOT OLD.research_id AND NEW.research_id IS NOT NULL) OR (OLD.state!='draft' AND NEW.state!='closed') BEGIN SELECT RAISE(ABORT,'native preview immutable'); END",
      "CREATE TRIGGER research_native_run_domain BEFORE UPDATE ON research_plan_native_runs WHEN NEW.task_id IS NOT OLD.task_id OR NEW.result_ref IS NOT OLD.result_ref OR NEW.preview_id IS NOT OLD.preview_id OR NEW.account_id IS NOT OLD.account_id OR NEW.financial_version IS NOT OLD.financial_version OR NEW.consent_digest IS NOT OLD.consent_digest OR NEW.upper IS NOT OLD.upper OR NEW.nonce IS NOT OLD.nonce OR NEW.version!=OLD.version+1 OR (NEW.consent_json IS NOT OLD.consent_json AND NOT (NEW.state='closed' AND NEW.consent_json IS NULL)) OR (OLD.admission_json IS NOT NULL AND NEW.admission_json IS NOT OLD.admission_json AND NOT (NEW.state='closed' AND NEW.admission_json IS NULL)) OR (OLD.admission_digest IS NOT NULL AND NEW.admission_digest IS NOT OLD.admission_digest) OR (OLD.state IN ('unknown','closed') AND NEW.state!='closed') OR (OLD.state='returned' AND NEW.state NOT IN ('returned','closed')) OR (OLD.state='consumed' AND NEW.state NOT IN ('unknown','returned','closed')) OR (OLD.state='approved' AND NEW.state NOT IN ('reserved','closed')) OR (OLD.state='reserved' AND NEW.state NOT IN ('consumed','closed')) BEGIN SELECT RAISE(ABORT,'native run cannot replay'); END",
    ))
    ddls.append("CREATE TRIGGER research_native_return_immutable BEFORE UPDATE ON research_plan_native_runs WHEN OLD.state='returned' AND NEW.state='returned' AND (NEW.receipt_json IS NOT OLD.receipt_json OR NEW.usage_json IS NOT OLD.usage_json OR NEW.result_json IS NOT OLD.result_json OR NEW.commit_json IS NOT OLD.commit_json OR NEW.cost_state IS NOT OLD.cost_state OR NEW.safe_code IS NOT OLD.safe_code) BEGIN SELECT RAISE(ABORT,'native return immutable'); END")
    return tuple(ddls)


def install_hook(conn):
    pid=os.getpid()
    def allowed(table,op,before,after):
        scope=_WRITES.get(id(conn))
        if not scope or scope['conn'] is not conn or pid!=os.getpid() or not conn.in_transaction or not scope['base'].active:return 0
        try:
            scope['lease'].identity;scope['verify']()
            return int(scope['table']==table and scope['op']==op and scope['before']==json.loads(before) and scope['after']==json.loads(after))
        except (ValueError,TypeError,PermissionError,ResearchError,OSError,sqlite3.Error):return 0
    def money(account):
        scope=_WRITES.get(id(conn))
        if not scope or scope['table']!=MONEY or scope['key']!=account or pid!=os.getpid() or not conn.in_transaction or not scope['base'].active:return 0
        try:scope['lease'].identity;scope['verify']();return 1
        except (ValueError,TypeError,PermissionError,ResearchError,OSError,sqlite3.Error):return 0
    conn.create_function('research_plan_native_write_allowed',4,allowed)
    conn.create_function('research_plan_native_money_allowed',1,money)
    conn.create_function('research_plan_native_guard_version',0,lambda:9 if pid==os.getpid() else 0)


def require_hook(conn):
    try:value=conn.execute("SELECT research_plan_native_guard_version(),research_plan_native_write_allowed('','INSERT','null','null'),research_plan_native_money_allowed('')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'原生计划连接守卫不可用。') from None
    if tuple(value)!=(9,0,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'原生计划连接守卫不匹配。')


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in NAMES:return True
    scope=_WRITES.get(id(conn));return bool(scope and scope['conn'] is conn and scope['base'].active and scope['pid']==os.getpid() and conn.in_transaction)


def _write(conn,lease,table,key,values,verify,*,_factory=None):
    from .paid_control import _current_scope
    if _factory is not _FACTORY or table not in (*NAMES,MONEY) or id(conn) in _WRITES:raise PermissionError('fixed native writer required')
    lease.identity;verify();base=_current_scope(conn)
    before=conn.execute('SELECT rowid AS rowid,* FROM '+table+' WHERE id=?',(key,)).fetchone();before=dict(before) if before else None
    after={**(before or {}),**values}
    if before:op='UPDATE'
    else:op='INSERT';after.update(id=key,rowid=conn.execute('SELECT coalesce(max(rowid),0)+1 FROM '+table).fetchone()[0])
    _WRITES[id(conn)]={'conn':conn,'lease':lease,'base':base,'verify':verify,'table':table,'key':key,'op':op,'before':before,'after':after,'pid':os.getpid()};base.refresh_authorizer()
    try:
        if before:
            keys=tuple(values);result=conn.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in keys)+' WHERE id=?',tuple(values[k] for k in keys)+(key,))
        else:
            keys=tuple(after);result=conn.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(after[k] for k in keys))
        if result.rowcount!=1:raise PermissionError('native write CAS failed')
        return result
    finally:_WRITES.pop(id(conn),None);base.refresh_authorizer()


def unresolved(conn,account,*,excluding=None):
    if conn.execute("SELECT 1 FROM research_plan_native_runs WHERE account_id=? AND id IS NOT ? AND (state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')) LIMIT 1",(account,excluding)).fetchone():return True
    if conn.execute("SELECT 1 FROM research_plan_dispatches WHERE account_id=? AND (state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')) LIMIT 1",(account,)).fetchone():return True
    return bool(conn.execute("SELECT 1 FROM research_reservations WHERE account_id=? AND status='UNKNOWN' LIMIT 1",(account,)).fetchone())


def provision_native_v13(path):
    from .formula_runtime import _offline_maintenance,_check_profile
    from .store import ResearchStore
    with _offline_maintenance(path,(12,13)) as (target,cap):
        conn=cap.conn;cap.require(target);conn.execute('PRAGMA foreign_keys=OFF')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=0:raise PermissionError('native FK toggle failed')
        try:
            conn.execute('BEGIN EXCLUSIVE');version=_check_profile(conn,target,(12,13))
            if version==12:
                overlays=overlay(ResearchStore._plan_tables());tables=tuple(overlays)
                extras=[r[0] for r in conn.execute("SELECT sql FROM sqlite_schema WHERE tbl_name IN ('research_tasks','research_steps') AND type IN ('index','trigger') AND sql IS NOT NULL")]
                for table,ddl in overlays.items():
                    columns=','.join(r[1] for r in conn.execute('PRAGMA table_info('+table+')'))
                    conn.execute(ddl.replace('CREATE TABLE IF NOT EXISTS ','CREATE TABLE ',1).replace('CREATE TABLE '+table,'CREATE TABLE '+table+'_native13',1))
                    conn.execute('INSERT INTO '+table+'_native13('+columns+') SELECT '+columns+' FROM '+table)
                for table in reversed(tables):conn.execute('DROP TABLE '+table)
                for table in tables:conn.execute('ALTER TABLE '+table+'_native13 RENAME TO '+table)
                for ddl in extras:conn.execute(ddl)
                for ddl in declarations():conn.execute(ddl)
                conn.execute('UPDATE research_schema SET version=13 WHERE id=1 AND version=12')
            ResearchStore._check_v13(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('native migration FK failure')
            cap.require(target);conn.commit()
        except BaseException:conn.rollback();raise
        finally:conn.execute('PRAGMA foreign_keys=ON')
        identity=cap.identity
    return {'schema_version':13,'financial_protocol':9,'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}
