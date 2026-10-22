"""V7 structures and CLOSED offline registry only. No money writer capability."""
import json
import os
import sqlite3
from contextlib import contextmanager
from uuid import uuid4

from .financial_admission_schemas import ProjectBudget
from .provider_schemas import Money,canonical,digest
from .errors import ResearchError

FINANCIAL_SCHEMA_VERSION=7
_SOURCES={}
_WRITES={}
_LEDGER_ROWS={'research_reservations','research_dispatch_permits','research_provider_sessions','research_cost_observations'}
_ERASABLE={'research_dispatch_permits':{'input_digest','authorization_context_json','budget_basis_json','gate_identity_json'},
    'research_provider_sessions':{'candidate_json'}}


def _statement_allowed(conn,action,table,column):
    from .method_draft import statement_allowed as draft_statement_allowed
    if not draft_statement_allowed(conn,action,table,column):return False
    from .plan_native_financial import statement_allowed as native_statement_allowed
    if not native_statement_allowed(conn,action,table,column):return False
    from .plan_financial import statement_allowed as plan_statement_allowed
    if not plan_statement_allowed(conn,action,table,column):return False
    from .formula_runtime import statement_allowed
    if not statement_allowed(conn,action,table,column):return False
    if action not in (sqlite3.SQLITE_INSERT,sqlite3.SQLITE_UPDATE,sqlite3.SQLITE_DELETE) or table not in _LEDGER_ROWS:return True
    if action==sqlite3.SQLITE_UPDATE and column in _ERASABLE.get(table,set()):return True
    if action==sqlite3.SQLITE_UPDATE and table=='research_provider_sessions' and column in dict(METHOD_COLUMNS):
        from .method_result import statement_allowed
        return statement_allowed(conn)
    permit=_WRITES.get(id(conn))
    if not permit or 'authority' not in permit:return False
    try:
        facts=permit['authority'].require(conn,permit['operation'])
        return facts.table==table and permit['scope'].active
    except (PermissionError,ResearchError,sqlite3.Error):return False

V7_TABLES=(
    """CREATE TABLE research_project_budgets (
        id INTEGER PRIMARY KEY CHECK(id=1),project_key TEXT NOT NULL UNIQUE CHECK(project_key='structure'),
        funding_account_id TEXT NOT NULL UNIQUE REFERENCES research_funding_accounts(id),
        economic_binding TEXT NOT NULL UNIQUE,currency TEXT NOT NULL CHECK(currency='CNY'),
        scale INTEGER NOT NULL CHECK(typeof(scale)='integer' AND scale=6),
        authorized_cap INTEGER NOT NULL CHECK(typeof(authorized_cap)='integer' AND authorized_cap BETWEEN 0 AND 9223372036854775807),
        authorization_ref TEXT NOT NULL,authorization_digest TEXT NOT NULL CHECK(length(authorization_digest)=64),
        database_binding TEXT NOT NULL CHECK(length(database_binding)=64),mode TEXT NOT NULL CHECK(mode='offline_probe'),
        status TEXT NOT NULL CHECK(status IN ('closed','active','blocked')),
        version INTEGER NOT NULL CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647))""",
    """CREATE TABLE research_financial_admissions (
        id TEXT NOT NULL PRIMARY KEY,project_budget_id INTEGER NOT NULL REFERENCES research_project_budgets(id) CHECK(project_budget_id=1),
        reservation_id TEXT NOT NULL UNIQUE REFERENCES research_reservations(id),
        permit_id TEXT NOT NULL UNIQUE REFERENCES research_dispatch_permits(id),
        session_id TEXT NOT NULL UNIQUE REFERENCES research_provider_sessions(id),dispatch_id TEXT NOT NULL UNIQUE,
        record_version TEXT NOT NULL CHECK(record_version='financial-admission-v1'),
        producer_version TEXT NOT NULL CHECK(producer_version='owned-budget-offline-v1'),
        policy TEXT NOT NULL CHECK(policy='bounded_usage_upper_v2'),mode TEXT NOT NULL CHECK(mode='offline_probe'),
        snapshot_json TEXT NOT NULL CHECK(json_valid(snapshot_json) AND json_type(snapshot_json)='object' AND length(CAST(snapshot_json AS BLOB))<=16384),
        snapshot_digest TEXT NOT NULL CHECK(length(snapshot_digest)=64),created_at TEXT NOT NULL)""",
)

_PROJECT_COLUMNS=tuple(ProjectBudget.model_fields)
_NEW_PROJECT_JSON='json_object('+','.join("'"+name+"',NEW."+name for name in _PROJECT_COLUMNS)+')'
V7_GUARDS=(
    "CREATE TRIGGER research_project_insert_control BEFORE INSERT ON research_project_budgets BEGIN SELECT CASE WHEN research_financial_write_allowed('register-project',"+_NEW_PROJECT_JSON+")!=1 THEN RAISE(ABORT,'controlled closed registration required') END; SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM research_funding_accounts a WHERE a.id=NEW.funding_account_id AND a.binding_id=NEW.economic_binding AND a.currency=NEW.currency AND a.scale=NEW.scale AND a.provider='deepseek') THEN RAISE(ABORT,'project economic binding mismatch') END; END",
    """CREATE TRIGGER research_project_no_replace BEFORE INSERT ON research_project_budgets
        WHEN EXISTS(SELECT 1 FROM research_project_budgets)
        BEGIN SELECT RAISE(ABORT,'project registration immutable'); END""",
    """CREATE TRIGGER research_project_update_control BEFORE UPDATE ON research_project_budgets
        BEGIN SELECT CASE WHEN research_financial_write_allowed('project-update','')!=1 THEN RAISE(ABORT,'project update unavailable') END; END""",
    """CREATE TRIGGER research_project_identity BEFORE UPDATE ON research_project_budgets
        WHEN NEW.id!=OLD.id OR NEW.project_key!=OLD.project_key OR NEW.funding_account_id!=OLD.funding_account_id
            OR NEW.economic_binding!=OLD.economic_binding OR NEW.currency!=OLD.currency OR NEW.scale!=OLD.scale
            OR NEW.authorized_cap!=OLD.authorized_cap OR NEW.authorization_ref!=OLD.authorization_ref
            OR NEW.authorization_digest!=OLD.authorization_digest OR NEW.database_binding!=OLD.database_binding
            OR NEW.mode!=OLD.mode OR NEW.version!=OLD.version+1
        BEGIN SELECT RAISE(ABORT,'immutable project authorization'); END""",
    "CREATE TRIGGER research_project_no_delete BEFORE DELETE ON research_project_budgets BEGIN SELECT RAISE(ABORT,'project budget retained'); END",
    """CREATE TRIGGER research_admission_insert_control BEFORE INSERT ON research_financial_admissions
        BEGIN SELECT CASE WHEN research_financial_write_allowed('admit',NEW.dispatch_id)!=1 THEN RAISE(ABORT,'financial admission unavailable') END;
        SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM research_project_budgets b JOIN research_reservations r ON r.account_id=b.funding_account_id
            JOIN research_dispatch_permits p ON p.reservation_id=r.id JOIN research_provider_sessions s ON s.permit_id=p.id
            WHERE b.id=NEW.project_budget_id AND b.status='active' AND r.id=NEW.reservation_id AND p.id=NEW.permit_id
            AND s.id=NEW.session_id AND p.dispatch_id=NEW.dispatch_id AND s.dispatch_id=p.dispatch_id
            AND r.status='SENT' AND p.state='consumed' AND s.state='consumed'
            AND r.policy_revision=NEW.policy AND p.policy_revision=NEW.policy AND s.mode=NEW.mode)
        THEN RAISE(ABORT,'financial admission binding mismatch') END; END""",
    """CREATE TRIGGER research_admission_no_replace BEFORE INSERT ON research_financial_admissions
        WHEN EXISTS(SELECT 1 FROM research_financial_admissions WHERE id=NEW.id OR reservation_id=NEW.reservation_id
            OR permit_id=NEW.permit_id OR session_id=NEW.session_id OR dispatch_id=NEW.dispatch_id)
        BEGIN SELECT RAISE(ABORT,'admission replacement forbidden'); END""",
    "CREATE TRIGGER research_admission_no_update BEFORE UPDATE ON research_financial_admissions BEGIN SELECT RAISE(ABORT,'immutable financial admission'); END",
    "CREATE TRIGGER research_admission_no_delete BEFORE DELETE ON research_financial_admissions BEGIN SELECT RAISE(ABORT,'financial admission retained'); END",
    """CREATE TRIGGER research_project_money_control BEFORE UPDATE OF settled,upper_booked,held ON research_funding_accounts
        WHEN EXISTS(SELECT 1 FROM research_project_budgets WHERE funding_account_id=OLD.id)
        BEGIN SELECT CASE WHEN research_financial_write_allowed('money',OLD.id)!=1 THEN RAISE(ABORT,'project money writer unavailable') END; END""",
    """CREATE TRIGGER research_financial_return_control BEFORE UPDATE OF financial_return_json,return_digest,received_at ON research_provider_sessions
        WHEN EXISTS(SELECT 1 FROM research_financial_admissions WHERE session_id=OLD.id)
        BEGIN SELECT CASE WHEN research_financial_write_allowed('return',OLD.id)!=1 THEN RAISE(ABORT,'owned financial return unavailable') END; END""",
)

DELETION_SCHEMA_VERSION=8
JOB_ORIGIN_VERSION='authenticated-delete-v1'
JOB_ORIGIN_COLUMNS=(
    ('origin_version',"TEXT CHECK(origin_version IS NULL OR origin_version='authenticated-delete-v1')"),
    ('origin_digest',"TEXT CHECK((origin_version IS NULL AND origin_digest IS NULL) OR (origin_version IS NOT NULL AND origin_version='authenticated-delete-v1' AND typeof(origin_digest)='text' AND length(origin_digest)=64 AND origin_digest NOT GLOB '*[^a-f0-9]*'))"),
)
V8_JOB_GUARDS=(
    """CREATE TRIGGER auth_deletion_origin_create BEFORE INSERT ON auth_deletion_jobs WHEN NEW.origin_version IS NOT NULL
        BEGIN SELECT CASE WHEN research_financial_write_allowed('delete-create',NEW.id)!=1
            OR NEW.state!='pending' OR NEW.owner_email IS NULL OR NEW.session_generation IS NULL
            OR NEW.research_erased!=0 OR NEW.legacy_attempted!=0 OR NEW.legacy_receipt_json IS NOT NULL
            OR NEW.result_json IS NOT NULL OR NEW.completed_at IS NOT NULL
            THEN RAISE(ABORT,'authenticated deletion creation required') END; END""",
    """CREATE TRIGGER auth_deletion_origin_no_retro BEFORE UPDATE OF origin_version,origin_digest ON auth_deletion_jobs
        WHEN OLD.origin_version IS NULL AND (NEW.origin_version IS NOT NULL OR NEW.origin_digest IS NOT NULL)
        BEGIN SELECT RAISE(ABORT,'legacy deletion origin cannot be signed'); END""",
    """CREATE TRIGGER auth_deletion_origin_identity BEFORE UPDATE ON auth_deletion_jobs WHEN OLD.origin_version IS NOT NULL
        AND (NEW.rowid IS NOT OLD.rowid OR NEW.id IS NOT OLD.id OR NEW.owner_key IS NOT OLD.owner_key OR NEW.gate_id IS NOT OLD.gate_id
            OR NEW.cleanup_binding IS NOT OLD.cleanup_binding OR NEW.database_binding IS NOT OLD.database_binding
            OR NEW.created_at IS NOT OLD.created_at OR NEW.origin_version IS NOT OLD.origin_version OR NEW.origin_digest IS NOT OLD.origin_digest)
        BEGIN SELECT RAISE(ABORT,'immutable deletion origin binding'); END""",
    """CREATE TRIGGER auth_deletion_origin_stage BEFORE UPDATE ON auth_deletion_jobs WHEN OLD.origin_version IS NOT NULL
        BEGIN SELECT CASE WHEN research_financial_write_allowed('delete-stage',OLD.id)!=1 OR OLD.state='completed'
            OR NOT ((OLD.state='pending' AND NEW.state IN ('pending','scrubbing')) OR (OLD.state='scrubbing' AND NEW.state='completed'))
            OR NEW.research_erased<OLD.research_erased OR NEW.legacy_attempted<OLD.legacy_attempted
            OR (OLD.legacy_receipt_json IS NOT NULL AND NEW.legacy_receipt_json IS NOT OLD.legacy_receipt_json)
            OR (OLD.result_json IS NOT NULL AND NEW.result_json IS NOT OLD.result_json)
            OR (NEW.state='pending' AND (NEW.owner_email IS NOT OLD.owner_email OR NEW.session_generation IS NOT OLD.session_generation))
            OR (NEW.state IN ('scrubbing','completed') AND (NEW.owner_email IS NOT NULL OR NEW.session_generation IS NOT NULL
                OR NEW.research_erased!=1 OR NEW.result_json IS NULL OR NOT json_valid(NEW.result_json)))
            OR (NEW.state!='completed' AND NEW.completed_at IS NOT OLD.completed_at)
            OR (NEW.state='completed' AND NEW.completed_at IS NULL)
            THEN RAISE(ABORT,'invalid deletion stage transition') END; END""",
    """CREATE TRIGGER auth_deletion_origin_no_replace BEFORE INSERT ON auth_deletion_jobs
        WHEN EXISTS(SELECT 1 FROM auth_deletion_jobs j WHERE j.origin_version IS NOT NULL AND
            (j.rowid=NEW.rowid OR j.id=NEW.id OR (j.owner_key=NEW.owner_key AND j.state!='completed' AND NEW.state!='completed')))
        BEGIN SELECT RAISE(ABORT,'protected deletion replacement forbidden'); END""",
    """CREATE TRIGGER auth_deletion_origin_no_update_replace BEFORE UPDATE ON auth_deletion_jobs
        WHEN EXISTS(SELECT 1 FROM auth_deletion_jobs j WHERE j.origin_version IS NOT NULL AND j.rowid IS NOT OLD.rowid AND
            (j.rowid=NEW.rowid OR j.id=NEW.id OR (j.owner_key=NEW.owner_key AND j.state!='completed' AND NEW.state!='completed')))
        BEGIN SELECT RAISE(ABORT,'protected deletion update replacement forbidden'); END""",
    """CREATE TRIGGER auth_deletion_origin_no_delete BEFORE DELETE ON auth_deletion_jobs WHEN OLD.origin_version IS NOT NULL
        BEGIN SELECT RAISE(ABORT,'deletion provenance retained'); END""",
)

METHOD_SCHEMA_VERSION=9
METHOD_COLUMNS=(
    ('body_origin_state',"TEXT NOT NULL DEFAULT 'legacy_unproved' CHECK(body_origin_state IN ('legacy_unproved','fresh','present','closed'))"),
    ('body_candidate_digest',"TEXT CHECK(body_candidate_digest IS NULL OR (length(body_candidate_digest)=64 AND body_candidate_digest NOT GLOB '*[^a-f0-9]*'))"),
    ('body_envelope_digest',"TEXT CHECK(body_envelope_digest IS NULL OR (length(body_envelope_digest)=64 AND body_envelope_digest NOT GLOB '*[^a-f0-9]*'))"),
    ('method_commit_json',"TEXT CHECK(method_commit_json IS NULL OR (json_valid(method_commit_json) AND length(CAST(method_commit_json AS BLOB))<=4096)) CHECK((body_origin_state='legacy_unproved' AND body_candidate_digest IS NULL AND body_envelope_digest IS NULL AND method_commit_json IS NULL) OR (body_origin_state='fresh' AND candidate_json IS NULL AND body_candidate_digest IS NULL AND body_envelope_digest IS NULL AND method_commit_json IS NULL AND financial_return_json IS NULL) OR (body_origin_state='closed' AND candidate_json IS NULL AND body_candidate_digest IS NULL AND body_envelope_digest IS NULL AND method_commit_json IS NULL) OR (body_origin_state='present' AND candidate_json IS NOT NULL AND body_candidate_digest IS NOT NULL AND body_envelope_digest IS NOT NULL AND financial_return_json IS NOT NULL AND received_at IS NOT NULL AND length(CAST(candidate_json AS BLOB))<=32768))"),
)
_METHOD_NEW="json_object("+','.join("'"+name+"',NEW."+name for name in ('id','approval_id','dispatch_id','permit_id','mode','binding_digest','candidate_json',*(name for name,_ in METHOD_COLUMNS)))+")"
METHOD_GUARDS=(
    """CREATE TRIGGER research_method_birth BEFORE INSERT ON research_provider_sessions
        WHEN NEW.body_origin_state!='legacy_unproved' OR NEW.candidate_json IS NOT NULL
            OR NEW.body_candidate_digest IS NOT NULL OR NEW.body_envelope_digest IS NOT NULL OR NEW.method_commit_json IS NOT NULL
        BEGIN SELECT CASE WHEN NEW.body_origin_state!='fresh' OR NEW.candidate_json IS NOT NULL
            OR NEW.body_candidate_digest IS NOT NULL OR NEW.body_envelope_digest IS NOT NULL OR NEW.method_commit_json IS NOT NULL
            OR research_method_write_allowed('birth',NEW.id,"""+_METHOD_NEW+""")!=1 THEN RAISE(ABORT,'controlled method birth required') END; END""",
    """CREATE TRIGGER research_method_write BEFORE UPDATE OF candidate_json,body_origin_state,body_candidate_digest,body_envelope_digest,method_commit_json ON research_provider_sessions
        WHEN OLD.body_origin_state!='legacy_unproved' OR NEW.body_origin_state!='legacy_unproved'
            OR NEW.body_candidate_digest IS NOT NULL OR NEW.body_envelope_digest IS NOT NULL OR NEW.method_commit_json IS NOT NULL
        BEGIN SELECT CASE WHEN OLD.body_origin_state='legacy_unproved'
            OR NOT ((OLD.body_origin_state='fresh' AND NEW.body_origin_state IN ('present','closed'))
                OR (OLD.body_origin_state='present' AND NEW.body_origin_state IN ('present','closed'))
                OR (OLD.body_origin_state='closed' AND NEW.body_origin_state='closed'))
            OR (OLD.body_origin_state='present' AND NEW.body_origin_state='present' AND
                (NEW.candidate_json IS NOT OLD.candidate_json OR NEW.body_candidate_digest IS NOT OLD.body_candidate_digest
                    OR NEW.body_envelope_digest IS NOT OLD.body_envelope_digest OR OLD.method_commit_json IS NOT NULL))
            OR research_method_write_allowed('write',OLD.id,"""+_METHOD_NEW+""")!=1 THEN RAISE(ABORT,'controlled method write required') END; END""",
    """CREATE TRIGGER research_method_identity BEFORE UPDATE ON research_provider_sessions WHEN OLD.body_origin_state!='legacy_unproved'
        AND (NEW.rowid IS NOT OLD.rowid OR NEW.id IS NOT OLD.id OR NEW.approval_id IS NOT OLD.approval_id OR NEW.dispatch_id IS NOT OLD.dispatch_id
            OR NEW.permit_id IS NOT OLD.permit_id OR NEW.mode IS NOT OLD.mode OR NEW.binding_digest IS NOT OLD.binding_digest)
        BEGIN SELECT RAISE(ABORT,'immutable method source binding'); END""",
    """CREATE TRIGGER research_method_no_replace BEFORE INSERT ON research_provider_sessions
        WHEN EXISTS(SELECT 1 FROM research_provider_sessions s WHERE s.body_origin_state!='legacy_unproved'
            AND (s.rowid=NEW.rowid OR s.id=NEW.id OR s.dispatch_id=NEW.dispatch_id OR s.permit_id=NEW.permit_id))
        BEGIN SELECT RAISE(ABORT,'method source replacement forbidden'); END""",
    """CREATE TRIGGER research_method_no_update_replace BEFORE UPDATE ON research_provider_sessions
        WHEN EXISTS(SELECT 1 FROM research_provider_sessions s WHERE s.body_origin_state!='legacy_unproved' AND s.rowid IS NOT OLD.rowid
            AND (s.rowid=NEW.rowid OR s.id=NEW.id OR s.dispatch_id=NEW.dispatch_id OR s.permit_id=NEW.permit_id))
        BEGIN SELECT RAISE(ABORT,'method source update replacement forbidden'); END""",
    """CREATE TRIGGER research_method_no_delete BEFORE DELETE ON research_provider_sessions WHEN OLD.body_origin_state!='legacy_unproved'
        BEGIN SELECT RAISE(ABORT,'method source tombstone retained'); END""",
)


def install_default_hook(conn):
    """No authorizer/trace replacement; private registration is the sole permit."""
    from .source_guard import install_hook as install_source_hook
    install_source_hook(conn)
    from .plan_financial import install_hook as install_plan_hook
    install_plan_hook(conn)
    from .plan_native_financial import install_hook as native_hook
    native_hook(conn)
    from .method_draft import install_hook as draft_hook
    draft_hook(conn)
    pid=os.getpid()
    def allowed(operation,raw):
        permit=_WRITES.get(id(conn))
        if (pid!=os.getpid() or permit is None or permit['conn'] is not conn or not conn.in_transaction
                or not permit['scope'].active or permit['scope'].pid!=pid):
            return 0
        try:
            permit['lease'].identity
            if 'authority' in permit:
                if operation!=permit['operation'] or raw!=permit['target']:return 0
                facts=permit['authority'].require(conn,operation)
                return int(facts.operation==operation and facts.target==raw)
            return int(operation=='register-project' and json.loads(raw)==permit['values'])
        except (ValueError,TypeError,PermissionError,OSError):return 0
    conn.create_function('research_financial_write_allowed',2,allowed)
    conn.create_function('research_financial_guard_version',0,lambda:7 if os.getpid()==pid else 0)
    from .method_result import install_hook
    install_hook(conn)
    from .formula_runtime import install_hook as formula_hook
    formula_hook(conn)
    from .paid_control import _SCOPES
    if id(conn) not in _SCOPES:
        # Fresh factory connections have no transaction observer to replace.
        schema=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema' AND type='table'").fetchone()
        try:version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone() if schema else None
        except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究版本标记结构不匹配。') from None
        if version and version[0] in (7,8,9,10,11,12,13,14):
            conn.set_authorizer(lambda action,table,column,db,trigger:
                sqlite3.SQLITE_OK if _statement_allowed(conn,action,table,column) else sqlite3.SQLITE_DENY)


def require_hook(conn):
    try:valid=conn.execute('SELECT research_financial_guard_version(),research_financial_write_allowed(?,?)',('probe','')).fetchone()
    except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融连接守卫不可用。') from None
    if tuple(valid)!=(7,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融连接守卫不匹配。')


@contextmanager
def _financial_write_scope(conn,lease,authority):
    from .paid_control import FinancialWriteAuthority,_current_scope
    if type(authority) is not FinancialWriteAuthority:raise PermissionError('real financial write authority required')
    operation=authority._operation;facts=authority.require(conn,operation);scope=_current_scope(conn)
    if authority._lease is not lease or id(conn) in _WRITES:raise PermissionError('financial write scope mismatch')
    _WRITES[id(conn)]={'conn':conn,'scope':scope,'lease':lease,'authority':authority,'operation':operation,'target':facts.target}
    scope.refresh_authorizer()
    try:yield
    finally:
        _WRITES.pop(id(conn),None)
        scope.refresh_authorizer()


class OfflineProjectRegistration:
    """Explicit server-only simulation configuration; cannot activate a budget."""
    __slots__=('_store','_identity','_principal','_funding','_cap','_reference','_pid','_active','_facts','_ref')
    def __setattr__(self,name,value):
        if hasattr(self,name):raise TypeError('offline registration configuration immutable')
        object.__setattr__(self,name,value)
    def __init__(self,*,store,identity,principal_id,funding_resolver,authorized_cap,authorization_ref):
        from .store import ResearchStore
        from .authorization import AccountIdentity,AuthorizationGate
        from .paid_approval import OfflineFundingResolver
        if (type(store) is not ResearchStore or type(identity) is not AccountIdentity or type(funding_resolver) is not OfflineFundingResolver
                or type(authorized_cap) is not Money):raise TypeError('controlled offline registration dependencies required')
        from .provider_schemas import Id
        from pydantic import TypeAdapter
        TypeAdapter(Id).validate_python(authorization_ref,strict=True)
        if type(authorized_cap.scale) is not int:raise ValueError('native project scale required')
        cap=Money.model_validate(authorized_cap)
        if cap.currency!='CNY' or type(cap.scale) is not int or cap.scale!=6:raise ValueError('native project permission required')
        with store.transaction() as conn:
            AuthorizationGate(store).check(conn,identity,principal_id)
            facts=funding_resolver.current(conn,principal_id)
        self._store,self._identity,self._principal,self._funding=store,identity,principal_id,funding_resolver
        self._cap,self._reference,self._pid,self._active=cap,authorization_ref,os.getpid(),True
        self._facts,self._ref=canonical(facts),str(uuid4());_SOURCES[self._ref]=self
    def __reduce__(self):raise TypeError('offline registration cannot be serialized')
    def close(self):object.__setattr__(self,'_active',False);_SOURCES.pop(self._ref,None)


def register_closed_project(conn,*,store,identity,lease,source=None):
    from .store import ResearchStore
    from .paid_control import _current_scope,_owner_binding
    from .authorization import AuthorizationGate,AccountIdentity,OwnerGateLease
    scope=_current_scope(conn)
    if type(store) is not ResearchStore or type(identity) is not AccountIdentity or type(lease) is not OwnerGateLease:
        raise PermissionError('canonical registration store identity and lease required')
    if (type(source) is not OfflineProjectRegistration or not source._active or source._pid!=os.getpid()
            or _SOURCES.get(source._ref) is not source or source._store is not store or source._identity!=identity):
        raise PermissionError('explicit offline project registration source required')
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (10,11,12,13,14):ResearchStore.check_runtime_version(conn)
    elif conn.execute('SELECT version FROM research_schema').fetchone()[0]==9:ResearchStore._check_v9(conn)
    else:ResearchStore._check_v7(conn);ResearchStore._check_v7_attachments(conn)
    _owner_binding(conn,store,source._principal,lease)
    AuthorizationGate(store).check(conn,identity,source._principal)
    facts=source._funding.current(conn,source._principal)
    if canonical(facts)!=source._facts:raise PermissionError('offline project funding binding changed')
    values=ProjectBudget(id=1,project_key='structure',funding_account_id=facts['account_id'],economic_binding=facts['binding_id'],
        currency='CNY',scale=6,authorized_cap=source._cap.amount_units,authorization_ref=source._reference,
        authorization_digest=digest(canonical({'ref':source._reference,'principal':source._principal,'funding_source':facts['source_ref'],
            'cap':source._cap.model_dump(),'account':facts['account_id'],'binding':facts['binding_id']})),
        database_binding=digest(str(store.path).encode()),mode='offline_probe',status='closed',version=1).model_dump()
    old=conn.execute('SELECT * FROM research_project_budgets WHERE id=1').fetchone()
    if old:
        if dict(old)!=values:raise PermissionError('project authorization already registered')
        scope.financial_active=True;scope.refresh_authorizer()
        return ProjectBudget.model_validate(dict(old))
    if id(conn) in _WRITES:raise PermissionError('registration scope already active')
    _WRITES[id(conn)]={'conn':conn,'scope':scope,'lease':lease,'values':values}
    try:
        columns=','.join(values)
        conn.execute('INSERT INTO research_project_budgets('+columns+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
    finally:_WRITES.pop(id(conn),None)
    scope.financial_active=True;scope.refresh_authorizer()
    return ProjectBudget.model_validate(values)
