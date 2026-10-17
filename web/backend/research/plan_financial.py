"""Financial8 starting-plan protocol; Financial7 history remains exact.

Only native, current transaction writers act here. Stored DTOs are audit data.
No production credential loader or public activation endpoint is installed.
"""
from contextlib import contextmanager
from functools import lru_cache
import json
import os
import sqlite3
from .provider_schemas import canonical,digest
from .errors import ResearchError

VERSION=8
RESEARCH_VERSION=12
PURPOSE='phenomenon_plan_v1'
ADMISSION='financial-admission-v2'
PRODUCER='owned-plan-fixture-v1'
_FACTORY=object()
_WRITES={}
TABLES=(
"""CREATE TABLE research_plan_funding (
 id INTEGER PRIMARY KEY CHECK(id=1),status TEXT NOT NULL CHECK(status IN ('closed','fixture','blocked','retired')),
 principal_id TEXT, generation TEXT, account_id TEXT REFERENCES research_funding_accounts(id),
 economic_binding TEXT, credential_incarnation TEXT, funding_epoch INTEGER, balance_claim TEXT, balance_nonce TEXT, version INTEGER NOT NULL CHECK(version>0),
 CHECK((status='closed' AND principal_id IS NULL AND generation IS NULL AND account_id IS NULL AND economic_binding IS NULL AND credential_incarnation IS NULL AND funding_epoch IS NULL)
 OR (status='retired' AND principal_id IS NULL AND generation IS NULL AND account_id IS NOT NULL AND economic_binding IS NOT NULL AND credential_incarnation IS NOT NULL AND funding_epoch>0)
 OR (status IN ('fixture','blocked') AND principal_id IS NOT NULL AND generation IS NOT NULL AND account_id IS NOT NULL AND economic_binding IS NOT NULL AND credential_incarnation IS NOT NULL AND funding_epoch>0)))""",
"""CREATE TABLE research_plan_previews (
 id TEXT PRIMARY KEY,research_id TEXT REFERENCES research_controls(id),principal_id TEXT NOT NULL,
 input_revision INTEGER NOT NULL,research_version INTEGER NOT NULL,payload_json TEXT CHECK(payload_json IS NULL OR (json_valid(payload_json) AND length(CAST(payload_json AS BLOB))<=32768)),
 preview_digest TEXT NOT NULL CHECK(length(preview_digest)=64),request_digest TEXT NOT NULL CHECK(length(request_digest)=64),
 quote_json TEXT NOT NULL CHECK(json_valid(quote_json) AND length(CAST(quote_json AS BLOB))<=16384),expires_at INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('draft','confirmed','closed')),task_id TEXT UNIQUE,
 key_digest TEXT NOT NULL,operation_digest TEXT NOT NULL,UNIQUE(principal_id,research_id,key_digest))""",
"""CREATE TABLE research_plan_dispatches (
 id TEXT PRIMARY KEY,task_id TEXT NOT NULL UNIQUE REFERENCES research_tasks(id),result_ref TEXT NOT NULL UNIQUE,
 preview_id TEXT NOT NULL UNIQUE REFERENCES research_plan_previews(id),account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
 admission_version TEXT NOT NULL CHECK(admission_version='financial-admission-v2'),financial_version INTEGER NOT NULL CHECK(financial_version=8),
 admission_json TEXT CHECK(admission_json IS NULL OR (json_valid(admission_json) AND length(CAST(admission_json AS BLOB))<=65536)),admission_digest TEXT NOT NULL CHECK(length(admission_digest)=64),
 upper INTEGER NOT NULL CHECK(typeof(upper)='integer' AND upper>=0),
 state TEXT NOT NULL CHECK(state IN ('approved','reserved','consumed','unknown','returned','closed')),
 cost_state TEXT NOT NULL CHECK(cost_state IN ('unreserved','held','upper_booked','unknown')),
 safe_code TEXT CHECK(safe_code IS NULL OR safe_code IN ('saved','body_invalid','send_unknown','not_sent','cancelled','access_ended')),
 nonce TEXT NOT NULL UNIQUE,version INTEGER NOT NULL CHECK(version>0),
 receipt_json TEXT CHECK(receipt_json IS NULL OR (json_valid(receipt_json) AND length(CAST(receipt_json AS BLOB))<=8192)),
 usage_json TEXT CHECK(usage_json IS NULL OR (json_valid(usage_json) AND length(CAST(usage_json AS BLOB))<=2048)),
 result_json TEXT CHECK(result_json IS NULL OR (json_valid(result_json) AND length(CAST(result_json AS BLOB))<=32768)),
 commit_json TEXT CHECK(commit_json IS NULL OR (json_valid(commit_json) AND length(CAST(commit_json AS BLOB))<=4096)),
 CHECK(state!='returned' OR (receipt_json IS NOT NULL AND usage_json IS NOT NULL AND commit_json IS NOT NULL)),
 CHECK(state NOT IN ('approved','reserved','consumed') OR admission_json IS NOT NULL))""",
)
NAMES=tuple(x.split()[2] for x in TABLES)


def overlay(tables):
    result=dict(tables)
    result['research_tasks']=result['research_tasks'].replace("'local-formula-v1'","'local-formula-v1','funded-plan-v1'")
    result['research_steps']=result['research_steps'].replace("'formula_check'","'formula_check','phenomenon_plan'")
    return result


@lru_cache(maxsize=1)
def declarations():
    from .store import ResearchStore
    ddls=list(TABLES)
    for ddl in TABLES:
        name=ddl.split()[2];columns=[x[0] for x in ResearchStore._declared_columns(ddl)]
        def image(prefix):return "json_object('rowid',"+prefix+'.rowid,'+','.join("'"+k+"',"+prefix+'.'+k for k in columns)+')'
        for op in ('INSERT','UPDATE','DELETE'):
            before="'null'" if op=='INSERT' else image('OLD');after="'null'" if op=='DELETE' else image('NEW')
            ddls.append(f"CREATE TRIGGER {name}_f8_{op.lower()} BEFORE {op} ON {name} BEGIN SELECT CASE WHEN research_plan_write_allowed('{name}','{op}',{before},{after})!=1 THEN RAISE(ABORT,'native Financial8 writer required') END; END")
        keys=['NEW.rowid IS OLD.rowid','NEW.id IS OLD.id']
        if name.endswith('previews'):keys+=['NEW.principal_id IS OLD.principal_id AND NEW.research_id IS OLD.research_id AND NEW.key_digest IS OLD.key_digest','NEW.task_id IS NOT NULL AND NEW.task_id IS OLD.task_id']
        if name.endswith('dispatches'):keys+=['NEW.task_id IS OLD.task_id','NEW.result_ref IS OLD.result_ref','NEW.preview_id IS OLD.preview_id','NEW.nonce IS OLD.nonce']
        ddls.append(f"CREATE TRIGGER {name}_f8_no_replace BEFORE INSERT ON {name} WHEN EXISTS(SELECT 1 FROM {name} OLD WHERE "+' OR '.join('('+k+')' for k in keys)+") BEGIN SELECT RAISE(ABORT,'Financial8 replacement forbidden'); END")
        ddls.append(f"CREATE TRIGGER {name}_f8_identity BEFORE UPDATE ON {name} WHEN NEW.rowid IS NOT OLD.rowid OR NEW.id IS NOT OLD.id BEGIN SELECT RAISE(ABORT,'Financial8 identity immutable'); END")
    ddls.extend((
      "CREATE TRIGGER research_plan_preview_domain BEFORE UPDATE ON research_plan_previews WHEN NEW.principal_id IS NOT OLD.principal_id OR NEW.preview_digest IS NOT OLD.preview_digest OR NEW.request_digest IS NOT OLD.request_digest OR NEW.quote_json IS NOT OLD.quote_json OR NEW.expires_at IS NOT OLD.expires_at OR NEW.input_revision IS NOT OLD.input_revision OR NEW.research_version IS NOT OLD.research_version OR NEW.key_digest IS NOT OLD.key_digest OR NEW.operation_digest IS NOT OLD.operation_digest OR (NEW.payload_json IS NOT OLD.payload_json AND NOT (NEW.state='closed' AND NEW.payload_json IS NULL)) OR (OLD.state!='draft' AND NEW.state!='closed') OR (NEW.research_id IS NOT OLD.research_id AND NEW.research_id IS NOT NULL) OR (OLD.task_id IS NOT NULL AND NEW.task_id IS NOT OLD.task_id) BEGIN SELECT RAISE(ABORT,'immutable plan confirmation'); END",
      "CREATE TRIGGER research_plan_dispatch_domain BEFORE UPDATE ON research_plan_dispatches WHEN NEW.task_id IS NOT OLD.task_id OR NEW.result_ref IS NOT OLD.result_ref OR NEW.preview_id IS NOT OLD.preview_id OR NEW.account_id IS NOT OLD.account_id OR NEW.admission_version IS NOT OLD.admission_version OR NEW.financial_version IS NOT OLD.financial_version OR NEW.admission_digest IS NOT OLD.admission_digest OR NEW.upper IS NOT OLD.upper OR NEW.nonce IS NOT OLD.nonce OR NEW.version!=OLD.version+1 OR (NEW.admission_json IS NOT OLD.admission_json AND NOT (NEW.state='closed' AND NEW.admission_json IS NULL)) OR (OLD.state IN ('unknown','closed') AND NEW.state!='closed') OR (OLD.state='returned' AND NEW.state!='closed') OR (OLD.state='consumed' AND NEW.state NOT IN ('unknown','returned','closed')) OR (OLD.state='approved' AND NEW.state NOT IN ('reserved','closed')) OR (OLD.state='reserved' AND NEW.state NOT IN ('consumed','closed')) BEGIN SELECT RAISE(ABORT,'irreversible plan dispatch'); END",
      "CREATE TRIGGER research_plan_funding_version BEFORE UPDATE ON research_plan_funding WHEN NEW.version!=OLD.version+1 OR (OLD.account_id IS NOT NULL AND (NEW.account_id IS NOT OLD.account_id OR NEW.economic_binding IS NOT OLD.economic_binding OR (NEW.principal_id IS NOT OLD.principal_id AND NOT (NEW.status='retired' AND NEW.principal_id IS NULL)) OR (NEW.generation IS NOT OLD.generation AND NOT (NEW.status='retired' AND NEW.generation IS NULL)))) BEGIN SELECT RAISE(ABORT,'funding binding cannot reset'); END",
    ))
    return tuple(ddls)


def install_hook(conn):
    pid=os.getpid()
    def allowed(table,op,before,after):
        current=_WRITES.get(id(conn))
        if not current or current['conn'] is not conn or pid!=os.getpid() or not conn.in_transaction:return 0
        try:
            if not current['base'].active or current['base'].pid!=pid or current['pid']!=pid:return 0
            current['lease'].identity
            current['verify']()
            return int(table==current['table'] and op==current['operation'] and json.loads(before)==current['before'] and json.loads(after)==current['after'])
        except (ValueError,TypeError,PermissionError,ResearchError,OSError,sqlite3.Error):return 0
    conn.create_function('research_plan_write_allowed',4,allowed)
    conn.create_function('research_plan_guard_version',0,lambda:8 if os.getpid()==pid else 0)


def require_hook(conn):
    try:row=conn.execute("SELECT research_plan_guard_version(),research_plan_write_allowed('','INSERT','null','null')").fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'计划资金连接守卫不可用。') from None
    if tuple(row)!=(8,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'计划资金连接守卫不匹配。')


def statement_allowed(conn,action,table,column):
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in NAMES:return True
    current=_WRITES.get(id(conn))
    return bool(current and current['conn'] is conn and current['base'].active and current['pid']==os.getpid() and conn.in_transaction)


def _write(conn,lease,table,key,values,*,verify,_factory=None):
    """Exactly one native before/after image, never a caller-owned scope."""
    from .paid_control import _current_scope
    if _factory is not _FACTORY or table not in NAMES or id(conn) in _WRITES:raise PermissionError('fixed plan table required')
    lease.identity;base=_current_scope(conn);verify()
    row=conn.execute('SELECT rowid AS rowid,* FROM '+table+' WHERE id=?',(key,)).fetchone()
    before=dict(row) if row else None
    after={**(before or {}),**values}
    if row:op='UPDATE'
    else:
        op='INSERT';after['id']=key
        # Explicit native rowid prevents an unbound replacement target.
        after['rowid']=conn.execute('SELECT coalesce(max(rowid),0)+1 FROM '+table).fetchone()[0]
    current=dict(conn=conn,base=base,lease=lease,verify=verify,before=before,after=after,table=table,operation=op,pid=os.getpid())
    _WRITES[id(conn)]=current;base.refresh_authorizer()
    try:
        if row:
            keys=tuple(values);changed=conn.execute('UPDATE '+table+' SET '+','.join(k+'=?' for k in keys)+' WHERE id=?',tuple(values[k] for k in keys)+(key,)).rowcount
        else:
            keys=tuple(after);changed=conn.execute('INSERT INTO '+table+'('+','.join(keys)+') VALUES('+','.join('?' for _ in keys)+')',tuple(after[k] for k in keys)).rowcount
        if changed!=1:raise PermissionError('plan native CAS failed')
    finally:_WRITES.pop(id(conn),None);base.refresh_authorizer()


def check_unknown(conn,account_id):
    if conn.execute("SELECT 1 FROM research_plan_dispatches WHERE account_id=? AND (state IN ('consumed','unknown') OR cost_state='unknown' OR (state='closed' AND cost_state='held')) LIMIT 1",(account_id,)).fetchone() or conn.execute("SELECT 1 FROM research_reservations WHERE account_id=? AND status='UNKNOWN' LIMIT 1",(account_id,)).fetchone():
        raise ResearchError('RECONCILIATION_REQUIRED',409,'资金账户存在未核对发送，暂停新执行。')


def provision_plan_v12(path):
    """Explicit offline11 ->12, same-inode exclusive atomic migration."""
    from .formula_runtime import _offline_maintenance,_check_profile
    from .store import ResearchStore
    with _offline_maintenance(path,(11,12)) as (target,cap):
        conn=cap.conn;cap.require(target);conn.execute('PRAGMA foreign_keys=OFF')
        if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=0:raise PermissionError('offline FK toggle failed')
        try:
            conn.execute('BEGIN EXCLUSIVE')
            version=_check_profile(conn,target,(11,12))
            if version==11:
                objects=ResearchStore._current_structure_declarations(version=12)
                rebuild=('research_tasks','research_steps')
                attachments=[row[0] for row in conn.execute("SELECT sql FROM sqlite_schema WHERE tbl_name IN ('research_tasks','research_steps') AND type IN ('index','trigger') AND sql IS NOT NULL")]
                for table in rebuild:
                    columns=','.join(row[1] for row in conn.execute('PRAGMA table_info('+table+')'))
                    ddl=objects[table][2][0]
                    conn.execute(ddl.replace('CREATE TABLE IF NOT EXISTS ','CREATE TABLE ',1).replace('CREATE TABLE '+table,'CREATE TABLE '+table+'_plan12',1))
                    conn.execute('INSERT INTO '+table+'_plan12('+columns+') SELECT '+columns+' FROM '+table)
                for table in reversed(rebuild):conn.execute('DROP TABLE '+table)
                for table in rebuild:conn.execute('ALTER TABLE '+table+'_plan12 RENAME TO '+table)
                for ddl in attachments:conn.execute(ddl)
                for ddl in declarations():conn.execute(ddl)
                conn.execute('UPDATE research_schema SET version=12 WHERE id=1 AND version=11')
            ResearchStore._check_v12(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise PermissionError('plan migration FK failure')
            cap.require(target);conn.commit()
        except BaseException:conn.rollback();raise
        finally:conn.execute('PRAGMA foreign_keys=ON')
        identity=cap.identity
    return {'schema_version':12,'financial_protocol':8,'journal_mode':'wal','database_identity':list(identity),'backup_scope':'in_memory_algorithm_recovery_only'}
