"""Research tables in the canonical auth SQLite; no alternate content DB."""
from __future__ import annotations

import sqlite3
import re
from contextlib import contextmanager
from pathlib import Path
from functools import lru_cache

from .errors import ResearchError
from .financial_guard import FINANCIAL_SCHEMA_VERSION,V7_TABLES,V7_GUARDS,install_default_hook,require_hook
from .financial_guard import DELETION_SCHEMA_VERSION,JOB_ORIGIN_COLUMNS,V8_JOB_GUARDS
from .financial_guard import METHOD_SCHEMA_VERSION,METHOD_COLUMNS,METHOD_GUARDS
CURRENT_RESEARCH_SCHEMA_VERSION=10

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS research_schema (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)",
    """CREATE TABLE IF NOT EXISTS research_principals (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind='account'),
        normalized_email TEXT, session_generation TEXT,
        epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 2147483647),
        status TEXT NOT NULL CHECK(status IN ('active','revoked','deleting','deleted')),
        created_at TEXT NOT NULL, gate_id TEXT,
        UNIQUE(normalized_email, session_generation))""",
    """CREATE TABLE IF NOT EXISTS research_controls (
        id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES research_principals(id),
        owner_epoch INTEGER NOT NULL CHECK(owner_epoch BETWEEN 1 AND 2147483647),
        acl_epoch INTEGER NOT NULL CHECK(acl_epoch BETWEEN 1 AND 2147483647),
        current_revision INTEGER NOT NULL CHECK(current_revision BETWEEN 1 AND 2147483647),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 2147483647),
        visibility TEXT NOT NULL CHECK(visibility='private'),
        lifecycle TEXT NOT NULL CHECK(lifecycle IN ('active','deleting','deleted')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_grants (
        id TEXT PRIMARY KEY, principal_id TEXT NOT NULL REFERENCES research_principals(id),
        principal_epoch INTEGER NOT NULL CHECK(principal_epoch BETWEEN 1 AND 2147483647),
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        acl_epoch INTEGER NOT NULL CHECK(acl_epoch BETWEEN 1 AND 2147483647),
        scopes TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','revoked')),
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_revisions (
        research_id TEXT NOT NULL REFERENCES research_controls(id),
        revision INTEGER NOT NULL CHECK(revision BETWEEN 1 AND 2147483647),
        problem_json TEXT NOT NULL CHECK(json_valid(problem_json)),
        digest TEXT NOT NULL CHECK(length(digest)=64), created_at TEXT NOT NULL,
        PRIMARY KEY(research_id, revision))""",
    """CREATE TRIGGER IF NOT EXISTS research_revision_no_update
        BEFORE UPDATE ON research_revisions BEGIN SELECT RAISE(ABORT, 'immutable revision'); END""",
    """CREATE TABLE IF NOT EXISTS research_idempotency (
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        operation TEXT NOT NULL, scope_key TEXT NOT NULL, key_digest TEXT NOT NULL,
        request_digest TEXT NOT NULL, result_json TEXT NOT NULL CHECK(json_valid(result_json)),
        PRIMARY KEY(principal_id, operation, scope_key, key_digest))""",
    "CREATE INDEX IF NOT EXISTS research_owner_idx ON research_controls(owner_id, lifecycle)",
)

C0_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS research_tasks (
        id TEXT PRIMARY KEY, research_id TEXT REFERENCES research_controls(id) ON DELETE SET NULL,
        principal_id TEXT NOT NULL REFERENCES research_principals(id),
        principal_epoch INTEGER, owner_epoch INTEGER, acl_epoch INTEGER,
        grant_id TEXT REFERENCES research_grants(id) ON DELETE SET NULL,
        auth_generation TEXT, input_revision INTEGER, input_digest TEXT, start_version INTEGER NOT NULL,
        execution TEXT NOT NULL CHECK(execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING','COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED')),
        phase TEXT NOT NULL, evidence TEXT NOT NULL DEFAULT 'UNASSESSED',
        stop_requested INTEGER NOT NULL DEFAULT 0 CHECK(stop_requested IN (0,1)),
        version INTEGER NOT NULL CHECK(version BETWEEN 1 AND 2147483647),
        attempt INTEGER NOT NULL DEFAULT 1 CHECK(attempt=1),
        policy_revision TEXT NOT NULL CHECK(policy_revision IN ('c0-fixture-v1','d1-source-only-v1')),
        execution_mode TEXT NOT NULL CHECK(execution_mode IN ('offline_probe','live')),
        reconcile_requested INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS research_one_active_task ON research_tasks(research_id)
        WHERE research_id IS NOT NULL AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')""",
    """CREATE TABLE IF NOT EXISTS research_attempts (
        task_id TEXT PRIMARY KEY REFERENCES research_tasks(id), attempt INTEGER NOT NULL CHECK(attempt=1),
        reason TEXT NOT NULL CHECK(reason='initial'), policy_revision TEXT NOT NULL, input_digest TEXT)""",
    """CREATE TABLE IF NOT EXISTS research_steps (
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES research_tasks(id),
        position INTEGER NOT NULL CHECK(position IN (0,1,2)),
        kind TEXT NOT NULL CHECK(kind IN ('discover_sources','fetch_source','compose_report')),
        state TEXT NOT NULL CHECK(state IN ('PENDING','PREPARED','SENDING','AWAITING_RECEIPT','SUCCEEDED','UNKNOWN','DISCARDED','FAILED')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(version BETWEEN 1 AND 2147483647),
        reservation_id TEXT, UNIQUE(task_id,position))""",
    """CREATE TABLE IF NOT EXISTS research_task_events (
        task_id TEXT NOT NULL REFERENCES research_tasks(id), seq INTEGER NOT NULL,
        state_version INTEGER NOT NULL, kind TEXT NOT NULL, safe_code TEXT,
        at TEXT NOT NULL, PRIMARY KEY(task_id,seq))""",
    """CREATE TABLE IF NOT EXISTS research_step_outputs (
        step_id TEXT PRIMARY KEY REFERENCES research_steps(id), task_id TEXT NOT NULL REFERENCES research_tasks(id),
        note TEXT NOT NULL, execution_mode TEXT NOT NULL CHECK(execution_mode='offline_probe'), created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_funding_accounts (
        id TEXT PRIMARY KEY, binding_id TEXT NOT NULL UNIQUE,
        fixture_port INTEGER NOT NULL CHECK(fixture_port BETWEEN 1 AND 65535),
        mode TEXT NOT NULL CHECK(mode='fixture'), currency TEXT NOT NULL CHECK(currency='USD'),
        scale INTEGER NOT NULL CHECK(scale=6), funding_epoch INTEGER NOT NULL CHECK(funding_epoch>0),
        cap INTEGER NOT NULL CHECK(cap=10000), settled INTEGER NOT NULL DEFAULT 0 CHECK(settled>=0),
        held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0),
        status TEXT NOT NULL CHECK(status IN ('active','unverified','reconciling','blocked')),
        snapshot_id TEXT, version INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS research_balance_snapshots (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        balance INTEGER NOT NULL CHECK(balance BETWEEN 0 AND 9223372036854775807),
        settled_at_observation INTEGER NOT NULL CHECK(settled_at_observation>=0),
        local_settlement_cursor INTEGER NOT NULL CHECK(local_settlement_cursor>=0), observed_at TEXT NOT NULL,
        expires_at TEXT NOT NULL, hard_prepaid INTEGER NOT NULL CHECK(hard_prepaid=1),
        auto_topup_off INTEGER NOT NULL CHECK(auto_topup_off=1), postpaid_off INTEGER NOT NULL CHECK(postpaid_off=1))""",
    """CREATE TABLE IF NOT EXISTS research_price_revisions (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        operation TEXT NOT NULL CHECK(operation IN ('discover_sources','compose_report')),
        currency TEXT NOT NULL CHECK(currency='USD'), scale INTEGER NOT NULL CHECK(scale=6),
        input_rate INTEGER NOT NULL CHECK(input_rate>=0), output_rate INTEGER NOT NULL CHECK(output_rate>=0),
        max_input INTEGER NOT NULL CHECK(max_input>=0), max_output INTEGER NOT NULL CHECK(max_output>=0),
        fixed_units INTEGER NOT NULL CHECK(fixed_units>=0),
        rounding TEXT NOT NULL CHECK(rounding IN ('ceil_total','ceil_components')),
        expires_at TEXT NOT NULL, UNIQUE(account_id,operation))""",
    """CREATE TABLE IF NOT EXISTS research_reservations (
        id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        task_id TEXT NOT NULL REFERENCES research_tasks(id), step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        operation_key TEXT NOT NULL UNIQUE, price_revision TEXT NOT NULL REFERENCES research_price_revisions(id),
        funding_epoch INTEGER NOT NULL, max_cost INTEGER NOT NULL CHECK(max_cost BETWEEN 0 AND 9223372036854775807),
        settled_cost INTEGER CHECK(settled_cost BETWEEN 0 AND 9223372036854775807),
        status TEXT NOT NULL CHECK(status IN ('HELD','SENT','UNKNOWN','SETTLED','RELEASED')),
        version INTEGER NOT NULL DEFAULT 1)""",
    """CREATE TABLE IF NOT EXISTS research_dispatch_permits (
        id TEXT PRIMARY KEY, step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        reservation_id TEXT NOT NULL UNIQUE REFERENCES research_reservations(id),
        dispatch_id TEXT NOT NULL UNIQUE, input_digest TEXT,
        state TEXT NOT NULL CHECK(state IN ('prepared','consumed','revoked')),
        expires_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS research_billing_receipts (
        id TEXT PRIMARY KEY, reservation_id TEXT NOT NULL REFERENCES research_reservations(id),
        account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        provider_ref TEXT NOT NULL, digest TEXT NOT NULL, cost INTEGER,
        status TEXT NOT NULL CHECK(status IN ('known','nonfinal','anomaly')),
        at TEXT NOT NULL, UNIQUE(account_id,provider_ref))""",
)

# Historical C0_SCHEMA remains the literal v3/v4 installation baseline.
# Only this owner defines the v5 replacement; consumers never install DDL.
PAID_SCHEMA_VERSION = 5
_MAX = "9223372036854775807"
_POLICY = "deepseek-bounded-upper-v1"


def _integer(name, *, default=None, nullable=False):
    required="" if nullable else " NOT NULL"
    initial="" if default is None else f" DEFAULT {default}"
    return f"{name} INTEGER{required}{initial} CHECK({name} IS NULL OR (typeof({name})='integer' AND {name} BETWEEN 0 AND {_MAX}))"


V5_SCHEMA = {
    "research_grants": SCHEMA[3].replace("created_at TEXT NOT NULL)","created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647))"),
    "research_tasks": C0_SCHEMA[0].replace("'c0-fixture-v1','d1-source-only-v1'",f"'c0-fixture-v1','d1-source-only-v1','{_POLICY}'"),
    "research_steps": next(s for s in C0_SCHEMA if s.startswith("CREATE TABLE IF NOT EXISTS research_steps (")).replace("'fetch_source','compose_report'","'fetch_source','compose_report','model_report'"),
    "research_funding_accounts": f"""CREATE TABLE research_funding_accounts (
        id TEXT PRIMARY KEY,binding_id TEXT NOT NULL UNIQUE,
        fixture_port INTEGER,mode TEXT NOT NULL DEFAULT 'live' CHECK(mode IN ('fixture','live')),
        currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency IN ('USD','CNY')),
        scale INTEGER NOT NULL DEFAULT 6 CHECK(typeof(scale)='integer' AND scale=6),
        funding_epoch INTEGER NOT NULL DEFAULT 1 CHECK(typeof(funding_epoch)='integer' AND funding_epoch BETWEEN 1 AND 2147483647),
        {_integer('cap',default=0)},{_integer('settled',default=0)},{_integer('held',default=0)},
        status TEXT NOT NULL DEFAULT 'unverified' CHECK(status IN ('active','unverified','reconciling','blocked')),
        snapshot_id TEXT,version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        provider TEXT NOT NULL DEFAULT 'fixture' CHECK(provider IN ('fixture','deepseek')),
        {_integer('initial_prepaid_units',nullable=True)},{_integer('other_use_margin_units',nullable=True)},
        {_integer('upper_booked',default=0)},
        CHECK((mode='fixture' AND provider='fixture' AND typeof(fixture_port)='integer' AND fixture_port BETWEEN 1 AND 65535 AND currency='USD' AND cap=10000)
            OR (mode='live' AND provider='deepseek' AND fixture_port IS NULL)),
        CHECK(mode='fixture' OR (status='unverified' AND cap=0 AND initial_prepaid_units IS NULL AND other_use_margin_units IS NULL)
            OR (initial_prepaid_units IS NOT NULL AND other_use_margin_units IS NOT NULL AND other_use_margin_units<=initial_prepaid_units AND cap=initial_prepaid_units-other_use_margin_units)))""",
    "research_balance_snapshots": f"""CREATE TABLE research_balance_snapshots (
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        {_integer('balance')},{_integer('settled_at_observation')},{_integer('local_settlement_cursor')},
        observed_at TEXT NOT NULL,expires_at TEXT NOT NULL,
        hard_prepaid INTEGER NOT NULL CHECK(hard_prepaid=1),auto_topup_off INTEGER NOT NULL CHECK(auto_topup_off=1),postpaid_off INTEGER NOT NULL CHECK(postpaid_off=1),
        {_integer('upper_booked_at_observation',default=0)},funding_epoch INTEGER NOT NULL DEFAULT 1 CHECK(typeof(funding_epoch)='integer' AND funding_epoch BETWEEN 1 AND 2147483647),
        basis_evidence_digest TEXT CHECK(basis_evidence_digest IS NULL OR length(basis_evidence_digest)=64))""",
    "research_price_revisions": f"""CREATE TABLE research_price_revisions (
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        operation TEXT NOT NULL CHECK(operation IN ('discover_sources','compose_report','model_report')),
        currency TEXT NOT NULL CHECK(currency IN ('USD','CNY')),scale INTEGER NOT NULL CHECK(typeof(scale)='integer' AND scale=6),
        {_integer('input_rate',default=0)},{_integer('output_rate',default=0)},{_integer('max_input',default=0)},{_integer('max_output',default=0)},{_integer('fixed_units',default=0)},
        rounding TEXT NOT NULL DEFAULT 'ceil_total' CHECK(rounding IN ('ceil_total','ceil_components')),expires_at TEXT NOT NULL,
        policy_revision TEXT NOT NULL DEFAULT 'c0-fixture-v1' CHECK(policy_revision IN ('c0-fixture-v1','{_POLICY}')),
        quote_json TEXT,quote_digest TEXT,
        CHECK((policy_revision='c0-fixture-v1' AND operation IN ('discover_sources','compose_report') AND currency='USD' AND quote_json IS NULL AND quote_digest IS NULL)
            OR (policy_revision='{_POLICY}' AND operation='model_report' AND quote_json IS NOT NULL AND quote_digest IS NOT NULL AND json_valid(quote_json) AND json_type(quote_json)='object' AND length(quote_json)<=8192 AND length(quote_digest)=64)))""",
    "research_reservations": f"""CREATE TABLE research_reservations (
        id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        task_id TEXT NOT NULL REFERENCES research_tasks(id),step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        operation_key TEXT NOT NULL UNIQUE,price_revision TEXT NOT NULL REFERENCES research_price_revisions(id),
        funding_epoch INTEGER NOT NULL CHECK(typeof(funding_epoch)='integer' AND funding_epoch BETWEEN 1 AND 2147483647),
        {_integer('max_cost')},{_integer('settled_cost',nullable=True)},
        status TEXT NOT NULL CHECK(status IN ('HELD','SENT','UNKNOWN','SETTLED','RELEASED','UPPER_BOOKED')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        policy_revision TEXT NOT NULL DEFAULT 'c0-fixture-v1' CHECK(policy_revision IN ('c0-fixture-v1','{_POLICY}')),
        principal_id TEXT REFERENCES research_principals(id),auth_scope_digest TEXT,outbound_fingerprint TEXT,
        CHECK((policy_revision='c0-fixture-v1' AND status!='UPPER_BOOKED') OR
            (policy_revision='{_POLICY}' AND principal_id IS NOT NULL AND auth_scope_digest IS NOT NULL AND outbound_fingerprint IS NOT NULL AND length(auth_scope_digest)=64 AND length(outbound_fingerprint)=64 AND
            (status!='UPPER_BOOKED' OR settled_cost IS NULL))))""",
    "research_dispatch_permits": f"""CREATE TABLE research_dispatch_permits (
        id TEXT PRIMARY KEY,step_id TEXT NOT NULL UNIQUE REFERENCES research_steps(id),
        reservation_id TEXT NOT NULL UNIQUE REFERENCES research_reservations(id),dispatch_id TEXT NOT NULL UNIQUE,input_digest TEXT,
        state TEXT NOT NULL CHECK(state IN ('prepared','consumed','revoked')),expires_at TEXT NOT NULL,
        policy_revision TEXT NOT NULL DEFAULT 'c0-fixture-v1' CHECK(policy_revision IN ('c0-fixture-v1','{_POLICY}')),
        request_digest TEXT,evidence_digest TEXT,price_digest TEXT,budget_basis_digest TEXT,budget_basis_json TEXT,
        authorization_context_digest TEXT,authorization_context_json TEXT,gate_identity_json TEXT,
        authorized_task_version INTEGER,authorized_step_version INTEGER,
        CHECK(policy_revision='c0-fixture-v1' OR (request_digest IS NOT NULL AND evidence_digest IS NOT NULL AND price_digest IS NOT NULL
            AND budget_basis_digest IS NOT NULL AND authorization_context_digest IS NOT NULL AND length(request_digest)=64 AND length(evidence_digest)=64 AND length(price_digest)=64
            AND length(budget_basis_digest)=64 AND length(authorization_context_digest)=64
            AND (budget_basis_json IS NULL OR (json_valid(budget_basis_json) AND length(budget_basis_json)<=8192))
            AND (authorization_context_json IS NULL OR (json_valid(authorization_context_json) AND length(authorization_context_json)<=8192))
            AND (gate_identity_json IS NULL OR (json_valid(gate_identity_json) AND length(gate_identity_json)<=256))
            AND typeof(authorized_task_version)='integer' AND authorized_task_version BETWEEN 1 AND 2147483647
            AND typeof(authorized_step_version)='integer' AND authorized_step_version BETWEEN 1 AND 2147483647)))""",
}

COST_SCHEMA = f"""CREATE TABLE research_cost_observations (
    id TEXT PRIMARY KEY,account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
    reservation_id TEXT NOT NULL REFERENCES research_reservations(id),dispatch_id TEXT NOT NULL,
    policy_revision TEXT NOT NULL CHECK(policy_revision='{_POLICY}'),
    kind TEXT NOT NULL CHECK(kind IN ('estimated_upper','unknown','anomaly')),
    response_digest TEXT CHECK(response_digest IS NULL OR length(response_digest)=64),usage_ref TEXT CHECK(usage_ref IS NULL OR length(usage_ref)=64),
    provider_response_ref TEXT CHECK(provider_response_ref IS NULL OR (length(provider_response_ref) BETWEEN 1 AND 120 AND provider_response_ref NOT GLOB '*[^a-zA-Z0-9._:-]*')),
    usage_json TEXT CHECK(usage_json IS NULL OR (json_valid(usage_json) AND json_type(usage_json)='object' AND length(usage_json)<=4096)),
    observation_digest TEXT NOT NULL CHECK(length(observation_digest)=64),
    {_integer('reserved_upper')},{_integer('booked_upper',nullable=True)},actual_charge INTEGER CHECK(actual_charge IS NULL),
    {_integer('usage_priced_estimate_units',nullable=True)},price_revision TEXT NOT NULL REFERENCES research_price_revisions(id),
    basis_digest TEXT NOT NULL CHECK(length(basis_digest)=64),
    safe_code TEXT NOT NULL CHECK(safe_code IN ('ok','body_invalid','access_ended','response_unknown','usage_unknown','usage_over_bound','model_drift','deadline','response_limit','send_unknown','conflict')),
    observed_at TEXT NOT NULL,UNIQUE(dispatch_id,observation_digest),
    CHECK((kind='estimated_upper' AND booked_upper=reserved_upper AND booked_upper IS NOT NULL AND usage_json IS NOT NULL AND usage_ref IS NOT NULL AND response_digest IS NOT NULL)
        OR (kind IN ('unknown','anomaly') AND booked_upper IS NULL)))"""

V5_AUX = (
    "CREATE UNIQUE INDEX research_fixture_price_operation ON research_price_revisions(account_id,operation) WHERE policy_revision='c0-fixture-v1'",
    """CREATE UNIQUE INDEX research_bounded_open_operation ON research_reservations(account_id,principal_id,outbound_fingerprint)
        WHERE policy_revision='deepseek-bounded-upper-v1' AND status IN ('HELD','SENT','UNKNOWN')""",
    "CREATE UNIQUE INDEX research_one_upper_observation ON research_cost_observations(dispatch_id) WHERE kind='estimated_upper'",
    """CREATE TRIGGER research_reservation_policy_immutable BEFORE UPDATE OF policy_revision ON research_reservations
        WHEN NEW.policy_revision!=OLD.policy_revision BEGIN SELECT RAISE(ABORT,'reservation policy immutable'); END""",
    """CREATE TRIGGER research_grant_version AFTER UPDATE OF status,scopes,principal_epoch,acl_epoch ON research_grants
        WHEN NEW.version=OLD.version AND (NEW.status!=OLD.status OR NEW.scopes!=OLD.scopes OR NEW.principal_epoch!=OLD.principal_epoch OR NEW.acl_epoch!=OLD.acl_epoch)
        BEGIN UPDATE research_grants SET version=version+1 WHERE id=NEW.id; END""",
    """CREATE TRIGGER research_grant_version_monotonic BEFORE UPDATE OF version ON research_grants
        WHEN NEW.version<=OLD.version BEGIN SELECT RAISE(ABORT,'grant version monotonic'); END""",
    """CREATE TRIGGER research_cost_usage_keys BEFORE INSERT ON research_cost_observations WHEN NEW.usage_json IS NOT NULL
        BEGIN SELECT CASE WHEN EXISTS(SELECT 1 FROM json_each(NEW.usage_json) WHERE key NOT IN
            ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','cached_tokens','reasoning_tokens')
            OR (type!='integer' AND NOT (type='null' AND key IN ('cached_tokens','reasoning_tokens'))) OR (type='integer' AND (value<0 OR value>9223372036854775807)))
            THEN RAISE(ABORT,'financial usage fields only') END; END""",
    """CREATE TRIGGER research_funding_identity_immutable BEFORE UPDATE OF binding_id,mode,provider,currency,scale ON research_funding_accounts
        WHEN NEW.binding_id!=OLD.binding_id OR NEW.mode!=OLD.mode OR NEW.provider!=OLD.provider OR NEW.currency!=OLD.currency OR NEW.scale!=OLD.scale
        BEGIN SELECT RAISE(ABORT,'funding identity immutable'); END""",
    """CREATE TRIGGER research_funding_cap_immutable BEFORE UPDATE OF cap,initial_prepaid_units,other_use_margin_units ON research_funding_accounts
        WHEN OLD.initial_prepaid_units IS NOT NULL AND (NEW.cap!=OLD.cap OR NEW.initial_prepaid_units IS NOT OLD.initial_prepaid_units OR NEW.other_use_margin_units IS NOT OLD.other_use_margin_units)
        BEGIN SELECT RAISE(ABORT,'funding cap immutable'); END""",
    """CREATE TRIGGER research_funding_epoch_monotonic BEFORE UPDATE OF funding_epoch ON research_funding_accounts
        WHEN NEW.funding_epoch<=OLD.funding_epoch BEGIN SELECT RAISE(ABORT,'funding epoch monotonic'); END""",
    """CREATE TRIGGER research_cost_binding BEFORE INSERT ON research_cost_observations
        BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM research_reservations r JOIN research_dispatch_permits p ON p.reservation_id=r.id
            JOIN research_price_revisions q ON q.id=r.price_revision JOIN research_funding_accounts a ON a.id=r.account_id
            WHERE r.id=NEW.reservation_id AND r.account_id=NEW.account_id AND r.price_revision=NEW.price_revision
            AND r.max_cost=NEW.reserved_upper AND r.policy_revision='deepseek-bounded-upper-v1'
            AND q.policy_revision=r.policy_revision AND q.currency=a.currency AND q.scale=a.scale
            AND p.policy_revision=r.policy_revision AND p.dispatch_id=NEW.dispatch_id AND p.state='consumed' AND p.budget_basis_digest=NEW.basis_digest
            AND r.status IN ('SENT','UNKNOWN','UPPER_BOOKED'))
            THEN RAISE(ABORT,'cost observation binding') END; END""",
    """CREATE TRIGGER research_price_account_binding BEFORE INSERT ON research_price_revisions
        BEGIN SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM research_funding_accounts a WHERE a.id=NEW.account_id
            AND a.currency=NEW.currency AND a.scale=NEW.scale AND ((a.mode='fixture' AND NEW.policy_revision='c0-fixture-v1')
            OR (a.mode='live' AND NEW.policy_revision='deepseek-bounded-upper-v1')))
            THEN RAISE(ABORT,'price account currency binding') END; END""",
    """CREATE TRIGGER research_cost_usage_complete BEFORE INSERT ON research_cost_observations WHEN NEW.kind='estimated_upper'
        BEGIN SELECT CASE WHEN NOT (
            json_type(NEW.usage_json,'$.prompt_tokens') IS 'integer' AND json_type(NEW.usage_json,'$.completion_tokens') IS 'integer'
            AND json_type(NEW.usage_json,'$.total_tokens') IS 'integer' AND json_type(NEW.usage_json,'$.prompt_cache_hit_tokens') IS 'integer'
            AND json_type(NEW.usage_json,'$.prompt_cache_miss_tokens') IS 'integer'
            AND json_extract(NEW.usage_json,'$.prompt_tokens')=json_extract(NEW.usage_json,'$.prompt_cache_hit_tokens')+json_extract(NEW.usage_json,'$.prompt_cache_miss_tokens')
            AND json_extract(NEW.usage_json,'$.total_tokens')=json_extract(NEW.usage_json,'$.prompt_tokens')+json_extract(NEW.usage_json,'$.completion_tokens')
            AND (json_type(NEW.usage_json,'$.cached_tokens') IS NULL OR json_type(NEW.usage_json,'$.cached_tokens') IS 'null' OR json_extract(NEW.usage_json,'$.cached_tokens')=json_extract(NEW.usage_json,'$.prompt_cache_hit_tokens'))
            AND (json_type(NEW.usage_json,'$.reasoning_tokens') IS NULL OR json_type(NEW.usage_json,'$.reasoning_tokens') IS 'null' OR json_extract(NEW.usage_json,'$.reasoning_tokens')<=json_extract(NEW.usage_json,'$.completion_tokens')))
            THEN RAISE(ABORT,'complete financial usage required') END; END""",
    """CREATE TRIGGER research_funding_no_replace BEFORE INSERT ON research_funding_accounts
        WHEN EXISTS(SELECT 1 FROM research_funding_accounts WHERE id=NEW.id OR binding_id=NEW.binding_id)
        BEGIN SELECT RAISE(ABORT,'funding replacement forbidden'); END""",
    """CREATE TRIGGER research_cost_no_replace BEFORE INSERT ON research_cost_observations
        WHEN EXISTS(SELECT 1 FROM research_cost_observations WHERE id=NEW.id
            OR (dispatch_id=NEW.dispatch_id AND observation_digest=NEW.observation_digest)
            OR (dispatch_id=NEW.dispatch_id AND kind='estimated_upper' AND NEW.kind='estimated_upper'))
        BEGIN SELECT RAISE(ABORT,'cost replacement forbidden'); END""",
    """CREATE TRIGGER research_snapshot_no_replace BEFORE INSERT ON research_balance_snapshots
        WHEN EXISTS(SELECT 1 FROM research_balance_snapshots WHERE id=NEW.id)
        BEGIN SELECT RAISE(ABORT,'snapshot replacement forbidden'); END""",
    """CREATE TRIGGER research_price_no_replace BEFORE INSERT ON research_price_revisions
        WHEN EXISTS(SELECT 1 FROM research_price_revisions WHERE id=NEW.id OR
            (account_id=NEW.account_id AND operation=NEW.operation AND policy_revision='c0-fixture-v1' AND NEW.policy_revision='c0-fixture-v1'))
        BEGIN SELECT RAISE(ABORT,'price replacement forbidden'); END""",
    """CREATE TRIGGER research_receipt_no_replace BEFORE INSERT ON research_billing_receipts
        WHEN EXISTS(SELECT 1 FROM research_billing_receipts WHERE id=NEW.id OR (account_id=NEW.account_id AND provider_ref=NEW.provider_ref))
        BEGIN SELECT RAISE(ABORT,'receipt replacement forbidden'); END""",
)

V5_GUARDS=tuple(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable accounting record'); END"
    for table in ("research_price_revisions","research_balance_snapshots","research_cost_observations"))+("CREATE TRIGGER research_cost_no_delete BEFORE DELETE ON research_cost_observations BEGIN SELECT RAISE(ABORT,'append only cost observation'); END",
    "CREATE TRIGGER research_funding_no_delete BEFORE DELETE ON research_funding_accounts BEGIN SELECT RAISE(ABORT,'funding identity retained'); END")

# Producer v6 is additive/versioned; the reviewed v5 definitions remain intact.
PRODUCER_SCHEMA_VERSION=6
USAGE_POLICY="bounded_usage_upper_v2"
V6_SCHEMA={name:ddl.replace("'deepseek-bounded-upper-v1'", "'deepseek-bounded-upper-v1','bounded_usage_upper_v2'",1)
    for name,ddl in V5_SCHEMA.items() if name in ("research_tasks","research_price_revisions","research_reservations","research_dispatch_permits")}
V6_SCHEMA["research_grants"]=V5_SCHEMA["research_grants"][:-1]+",funding_account_id TEXT REFERENCES research_funding_accounts(id),funding_permission_ref TEXT)"
V6_SCHEMA["research_price_revisions"]=V6_SCHEMA["research_price_revisions"].replace("policy_revision='deepseek-bounded-upper-v1'","policy_revision IN ('deepseek-bounded-upper-v1','bounded_usage_upper_v2')")
V6_SCHEMA["research_reservations"]=V6_SCHEMA["research_reservations"].replace("policy_revision='deepseek-bounded-upper-v1'","policy_revision IN ('deepseek-bounded-upper-v1','bounded_usage_upper_v2')")
V6_SCHEMA["research_dispatch_permits"]=V6_SCHEMA["research_dispatch_permits"].replace("CHECK(policy_revision='c0-fixture-v1' OR", "paid_approval_ref TEXT REFERENCES research_paid_approvals(id),admitted_at INTEGER,CHECK(policy_revision='c0-fixture-v1' OR")
V6_SCHEMA["research_cost_observations"]=COST_SCHEMA.replace("policy_revision='deepseek-bounded-upper-v1'","policy_revision IN ('deepseek-bounded-upper-v1','bounded_usage_upper_v2')").replace("booked_upper=reserved_upper", "((policy_revision='deepseek-bounded-upper-v1' AND booked_upper=reserved_upper) OR (policy_revision='bounded_usage_upper_v2' AND booked_upper<=reserved_upper))").replace("observed_at TEXT NOT NULL,UNIQUE", "observed_at TEXT NOT NULL,released_reserve_difference INTEGER NOT NULL DEFAULT 0 CHECK(typeof(released_reserve_difference)='integer' AND released_reserve_difference BETWEEN 0 AND 9223372036854775807),trusted_return_ref TEXT REFERENCES research_provider_sessions(id),UNIQUE").replace("CHECK((kind='estimated_upper'", "CHECK(kind!='estimated_upper' OR (policy_revision='deepseek-bounded-upper-v1' AND released_reserve_difference=0) OR (policy_revision='bounded_usage_upper_v2' AND released_reserve_difference=reserved_upper-booked_upper)),CHECK((kind='estimated_upper'")

PRODUCER_DDL=(
    """CREATE TABLE research_paid_approvals (
        id TEXT PRIMARY KEY,principal_id TEXT NOT NULL REFERENCES research_principals(id),
        research_id TEXT REFERENCES research_controls(id) ON DELETE SET NULL,
        payload_json TEXT CHECK(payload_json IS NULL OR (json_valid(payload_json) AND length(payload_json)<=65536)),
        payload_digest TEXT NOT NULL CHECK(length(payload_digest)=64),
        state TEXT NOT NULL CHECK(state IN ('draft','confirmed','consumed','revoked')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        mode TEXT NOT NULL CHECK(mode='offline_probe'),policy_revision TEXT NOT NULL CHECK(policy_revision='bounded_usage_upper_v2'),
        funding_source_ref TEXT NOT NULL,account_id TEXT NOT NULL REFERENCES research_funding_accounts(id),
        task_id TEXT UNIQUE,grant_id TEXT UNIQUE,dispatch_id TEXT UNIQUE,
        confirmed_at INTEGER,expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>0),
        created_at TEXT NOT NULL,max_calls INTEGER NOT NULL DEFAULT 1 CHECK(max_calls=1))""",
    """CREATE TABLE research_provider_sessions (
        id TEXT PRIMARY KEY,approval_id TEXT NOT NULL REFERENCES research_paid_approvals(id),
        dispatch_id TEXT NOT NULL UNIQUE,permit_id TEXT NOT NULL UNIQUE REFERENCES research_dispatch_permits(id),
        mode TEXT NOT NULL CHECK(mode='offline_probe'),binding_digest TEXT NOT NULL CHECK(length(binding_digest)=64),
        state TEXT NOT NULL CHECK(state IN ('created','consumed','sent','received','unknown','closed')),
        version INTEGER NOT NULL DEFAULT 1 CHECK(typeof(version)='integer' AND version BETWEEN 1 AND 2147483647),
        financial_return_json TEXT CHECK(financial_return_json IS NULL OR (json_valid(financial_return_json) AND length(financial_return_json)<=16384)),
        return_digest TEXT,received_at TEXT,candidate_json TEXT CHECK(candidate_json IS NULL OR length(candidate_json)<=32768))""",
)

V6_AUX=tuple(ddl.replace("policy_revision='deepseek-bounded-upper-v1'","policy_revision IN ('deepseek-bounded-upper-v1','bounded_usage_upper_v2')")
    .replace("WHERE r.id=NEW.reservation_id", "WHERE NEW.policy_revision=r.policy_revision AND NEW.policy_revision=p.policy_revision AND NEW.policy_revision=q.policy_revision AND r.id=NEW.reservation_id")
    for ddl in V5_AUX)+(
    """CREATE TRIGGER research_paid_approval_identity BEFORE UPDATE OF principal_id,research_id,mode,policy_revision,funding_source_ref,account_id,max_calls,expires_at,created_at ON research_paid_approvals
        WHEN NEW.principal_id!=OLD.principal_id OR NEW.mode!=OLD.mode OR NEW.policy_revision!=OLD.policy_revision
            OR NEW.funding_source_ref!=OLD.funding_source_ref OR NEW.account_id!=OLD.account_id OR NEW.max_calls!=OLD.max_calls
            OR NEW.expires_at!=OLD.expires_at OR NEW.created_at!=OLD.created_at OR (NEW.research_id IS NOT OLD.research_id
                AND NOT (NEW.research_id IS NULL AND NEW.state='revoked' AND EXISTS(SELECT 1 FROM research_principals WHERE id=OLD.principal_id AND status='deleting')))
        BEGIN SELECT RAISE(ABORT,'paid approval binding immutable'); END""",
    """CREATE TRIGGER research_paid_approval_state BEFORE UPDATE OF state ON research_paid_approvals
        WHEN NEW.state!=OLD.state AND NOT ((OLD.state='draft' AND NEW.state IN ('confirmed','revoked'))
            OR (OLD.state='confirmed' AND NEW.state IN ('consumed','revoked')) OR (OLD.state='consumed' AND NEW.state='revoked'))
        BEGIN SELECT RAISE(ABORT,'paid approval transition forbidden'); END""",
    """CREATE TRIGGER research_paid_approval_no_replace BEFORE INSERT ON research_paid_approvals
        WHEN EXISTS(SELECT 1 FROM research_paid_approvals WHERE id=NEW.id OR task_id=NEW.task_id OR grant_id=NEW.grant_id OR dispatch_id=NEW.dispatch_id)
        BEGIN SELECT RAISE(ABORT,'paid approval replacement forbidden'); END""",
    """CREATE TRIGGER research_paid_approval_payload_guard BEFORE UPDATE OF payload_json,payload_digest ON research_paid_approvals
        WHEN OLD.state!='draft' AND (NEW.payload_json IS NOT OLD.payload_json OR NEW.payload_digest!=OLD.payload_digest)
        AND NOT (NEW.payload_json IS NULL AND NEW.payload_digest=OLD.payload_digest AND NEW.state='revoked'
            AND EXISTS(SELECT 1 FROM research_principals WHERE id=OLD.principal_id AND status='deleting'))
        BEGIN SELECT RAISE(ABORT,'confirmed paid input immutable'); END""",
    """CREATE TRIGGER research_provider_session_no_replace BEFORE INSERT ON research_provider_sessions
        WHEN EXISTS(SELECT 1 FROM research_provider_sessions WHERE id=NEW.id OR dispatch_id=NEW.dispatch_id OR permit_id=NEW.permit_id)
        BEGIN SELECT RAISE(ABORT,'provider session replacement forbidden'); END""",
    """CREATE TRIGGER research_provider_return_immutable BEFORE UPDATE OF financial_return_json,return_digest,received_at ON research_provider_sessions
        WHEN OLD.financial_return_json IS NOT NULL AND (NEW.financial_return_json IS NOT OLD.financial_return_json OR NEW.return_digest IS NOT OLD.return_digest OR NEW.received_at IS NOT OLD.received_at)
        BEGIN SELECT RAISE(ABORT,'provider financial return immutable'); END""",
)


class ResearchStore:
    def __init__(self, auth_store):
        self.auth_store = auth_store
        if __package__=='web.backend.research':from ..services.auth_store import _formal_auth_mode,AuthStore
        else:from services.auth_store import _formal_auth_mode,AuthStore
        current=_formal_auth_mode()
        captured=getattr(auth_store,'_private_auth',False)
        if current and not captured:raise RuntimeError('development Auth cannot become private Research')
        self._private_auth=bool(current or captured)
        self.path=Path(auth_store.path) if self._private_auth else Path(auth_store.path).resolve()
        self._private_path=self.path if self._private_auth else None
        self._storage_identity=auth_store.storage_identity if self._private_auth else None
        if self._private_auth:
            self._formal_mode()
            if AuthStore.preflight_private(self.path)!=self._storage_identity:
                raise RuntimeError('private Research and Auth identities differ')
            with self.transaction():pass
            return
        # A completed v6 source must be verified before any legacy IF NOT
        # EXISTS installation could hide missing inherited objects.
        completed_v6=False
        completed_v7=False
        completed_v8=False
        with self.transaction() as conn:
            present=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema' AND type='table'").fetchone()
            if present:
                try:current=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()
                except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究版本标记结构不匹配。') from None
                if current and current[0]==10:
                    self._check_v10(conn);return
                if current and current[0]==METHOD_SCHEMA_VERSION:
                    self._check_structure_version(conn,9);self._check_v9(conn);return
                if current and current[0]==DELETION_SCHEMA_VERSION:
                    self._check_v8(conn);self._check_v7_attachments(conn);completed_v8=True
                if current and current[0]==FINANCIAL_SCHEMA_VERSION:
                    self._check_v7(conn);self._check_v7_attachments(conn)
                    completed_v7=True
                if current and current[0]==PRODUCER_SCHEMA_VERSION:
                    self._check_v6_inherited(conn)
                    self._check_v7_attachments(conn)
                    if conn.execute('PRAGMA foreign_key_check').fetchall():
                        raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究旧库关联不匹配。')
                    completed_v6=True
        if completed_v6:
            self._migrate_v7()
            self._migrate_v8_if_ready()
            self._migrate_v9_if_ready()
            return
        if completed_v7:
            self._migrate_v8()
            self._migrate_v9_if_ready()
            return
        if completed_v8:
            self._migrate_v9()
            return
        # AuthStore already initializes auth tables and WAL with its own lock.
        with self.transaction(write=True) as conn:
            existing=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema' AND type='table'").fetchone()
            financial_names=tuple(ddl.split()[2] for ddl in (*V7_TABLES,*V7_GUARDS))
            financial_exists=conn.execute('SELECT 1 FROM sqlite_schema WHERE name IN ('+','.join('?' for _ in financial_names)+') LIMIT 1',financial_names).fetchone()
            if not existing and conn.execute("SELECT 1 FROM sqlite_schema WHERE name GLOB 'research_*' LIMIT 1").fetchone():
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究结构缺少版本标记。')
            if not existing and self._initialize_current(conn):return
            if existing:
                try:current=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()
                except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究版本标记结构不匹配。') from None
                # A peer may finish initialization after our first read. The
                # write snapshot, not that stale read, decides whether legacy
                # installation is allowed. Never repair a completed graph.
                if current and current[0]==10:
                    self._check_v10(conn)
                    return
                if current and current[0]==METHOD_SCHEMA_VERSION:
                    self._check_structure_version(conn,9);self._check_v9(conn)
                    return
                if current and current[0]==DELETION_SCHEMA_VERSION:
                    self._check_completed_migration_peer(conn,current[0])
                    completed_v8=True
                elif current and current[0]==FINANCIAL_SCHEMA_VERSION:
                    self._check_v7(conn);self._check_v7_attachments(conn)
                    completed_v7=True
                elif current and current[0]==PRODUCER_SCHEMA_VERSION:
                    self._check_v6_inherited(conn);self._check_v7_attachments(conn)
                    if conn.execute('PRAGMA foreign_key_check').fetchall():
                        raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究旧库关联不匹配。')
                    completed_v6=True
                elif current is None or financial_exists:
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融结构与版本标记不匹配。')
            if not (completed_v6 or completed_v7 or completed_v8):
                conn.execute(SCHEMA[0])
                row = conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()
                if row is not None and row["version"] not in (1, 2, 3, 4, 5, 6):
                    raise ResearchError("SCHEMA_UNSUPPORTED", 503, "研究数据版本暂不支持。")
                for statement in SCHEMA[1:]:
                    conn.execute(statement)
                columns = {item["name"] for item in conn.execute("PRAGMA table_info(research_principals)")}
                if "gate_id" not in columns:
                    conn.execute("ALTER TABLE research_principals ADD COLUMN gate_id TEXT")
                for principal in conn.execute("SELECT id,normalized_email FROM research_principals WHERE gate_id IS NULL").fetchall():
                    if not principal["normalized_email"]:
                        raise ResearchError("SCHEMA_UNSUPPORTED", 503, "研究主体迁移缺少必要绑定。")
                    gate_id = self.auth_store.owner_gate_in(conn, principal["normalized_email"], principal["id"])
                    conn.execute("UPDATE research_principals SET gate_id=? WHERE id=?", (gate_id, principal["id"]))
                conn.execute("""CREATE TRIGGER IF NOT EXISTS research_principal_gate_required
                    BEFORE INSERT ON research_principals WHEN NEW.gate_id IS NULL
                    BEGIN SELECT RAISE(ABORT, 'principal gate required'); END""")
                for statement in C0_SCHEMA:
                    conn.execute(statement)
                for table in ("research_price_revisions","research_balance_snapshots","research_billing_receipts"):
                    conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_immutable
                        BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable accounting record'); END""")
                conn.execute("INSERT INTO research_schema VALUES(1,3) ON CONFLICT(id) DO NOTHING")
        # Resume only after releasing the initialization write transaction;
        # each original migration obtains and validates its own transaction.
        if completed_v6:
            self._migrate_v7()
            self._migrate_v8_if_ready()
            self._migrate_v9_if_ready()
            return
        if completed_v7:
            self._migrate_v8()
            self._migrate_v9_if_ready()
            return
        if completed_v8:
            self._migrate_v9()
            return
        self._migrate_v4()
        self._migrate_v5()
        self._migrate_v6()
        # Only a completed producer schema is eligible for the additive v7
        # migration. An explicitly isolated earlier migration profile keeps
        # its original capabilities; it never becomes a v7 financial source.
        with self.transaction() as conn:
            producer_version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
        if producer_version==PRODUCER_SCHEMA_VERSION:self._migrate_v7()
        self._migrate_v8_if_ready()
        self._migrate_v9_if_ready()

    def _initialize_current(self,conn):
        """Only the exact, empty Research profile is eligible for cold install."""
        if conn.execute("SELECT 1 FROM sqlite_schema WHERE name GLOB 'research_*' LIMIT 1").fetchone():
            raise ResearchError('SCHEMA_UNSUPPORTED',503,'冷启动发现未识别研究结构。')
        self._check_auth_job_schema(conn,expanded=False)
        for name,ddl in JOB_ORIGIN_COLUMNS:conn.execute('ALTER TABLE auth_deletion_jobs ADD COLUMN '+name+' '+ddl)
        objects=self._current_structure_declarations(version=10)
        for kind,target,forms in objects.values():
            if kind=='table' and target!='auth_deletion_jobs':conn.execute(forms[0])
        for kind,target,forms in objects.values():
            if kind!='table' and target!='auth_deletion_jobs':conn.execute(forms[0])
        for ddl in V8_JOB_GUARDS:conn.execute(ddl)
        conn.execute('INSERT INTO research_schema VALUES(1,10)')
        self._check_v10(conn)
        return True

    @property
    def storage_identity(self):
        return self._storage_identity

    def _formal_mode(self):
        if __package__=='web.backend.research':
            from ..services.auth_store import _formal_auth_mode,AuthStore
            from ..services.runtime_paths import private_auth_path,RuntimePathError
        else:
            from services.auth_store import _formal_auth_mode,AuthStore
            from services.runtime_paths import private_auth_path,RuntimePathError
        current=_formal_auth_mode();captured=getattr(self,'_private_auth',False)
        if (current or getattr(getattr(self,'auth_store',None),'_private_auth',False)) and not captured:
            raise RuntimePathError('development Research cannot become private')
        if not captured:return False
        import sys
        auth_types=(AuthStore,)+tuple(candidate for name in
            ('services.auth_store','web.backend.services.auth_store')
            if (module:=sys.modules.get(name)) is not None
            and isinstance(candidate:=getattr(module,'AuthStore',None),type) and candidate is not AuthStore)
        if type(self.auth_store) not in auth_types:
            raise RuntimePathError('private Research requires the actual Auth store')
        if (self.path!=self._private_path or self.path!=private_auth_path() or self.auth_store.path!=self.path
                or not getattr(self.auth_store,'_private_auth',False)
                or self.auth_store.storage_identity!=self._storage_identity or self._storage_identity is None):
            raise RuntimePathError('private Research Auth binding changed')
        return True

    def _connect(self,*,readonly=False):
        if self._formal_mode():
            if __package__=='web.backend.research':from ..services.sqlite_utils import connect_private_auth
            else:from services.sqlite_utils import connect_private_auth
            return connect_private_auth(self.path,readonly=readonly,timeout=5,expected_identity=self._storage_identity)
        return sqlite3.connect(self.path,timeout=5,isolation_level=None)

    def _require_development_migration(self):
        if self._formal_mode():raise RuntimeError('private Research migration requires separate provisioning')

    @classmethod
    def _check_completed_migration_peer(cls,conn,version):
        """An exact completed peer is an idempotent migration, never authority."""
        if version==10:
            cls._check_v10(conn);return True
        if version not in (DELETION_SCHEMA_VERSION,METHOD_SCHEMA_VERSION):return False
        if version==METHOD_SCHEMA_VERSION:
            cls._check_structure_version(conn,9);cls._check_v9(conn)
        else:
            # V8 has the same declared graph except the V9 method overlay.
            # Check every managed object before the original full V8 domain
            # checks; unknown auxiliaries cannot hide behind a newer marker.
            objects=cls._current_structure_declarations(version=9)
            for ddl in METHOD_GUARDS:del objects[ddl.split()[2]]
            session=next(ddl for ddl in PRODUCER_DDL if ddl.startswith('CREATE TABLE research_provider_sessions'))
            objects['research_provider_sessions']=('table','research_provider_sessions',(session,))
            tables={name for name,(kind,_,_) in objects.items() if kind=='table'}
            catalog={}
            for value in conn.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema'):
                row=tuple(value);kind,name,target,sql=row
                if name not in objects and not name.startswith('research_') and target not in tables:continue
                catalog[name]=row
                automatic=(kind=='index' and sql is None and target in tables
                    and re.fullmatch(r'sqlite_autoindex_'+re.escape(target)+r'_[0-9]+',name) is not None)
                if name not in objects and not automatic:
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究迁移发现未知对象。')
            cls._check_declared_structure(conn,objects,catalog=catalog)
            marker=[tuple(row) for row in conn.execute('SELECT id,version FROM main.research_schema')]
            if marker!=[(1,DELETION_SCHEMA_VERSION)] or any(type(value) is not int for value in marker[0]):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究迁移版本标记不匹配。')
            cls._check_v8(conn);cls._check_v7_attachments(conn)
        return True

    def _migrate_v4(self):
        """Controlled SQLite table replacement, never an application session.

        FK enforcement is suspended only on this migration connection, before
        BEGIN. No network/records API uses it. Validate the full graph before
        commit; every failure rolls back the original tables and schema value.
        """
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=OFF")
            if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 0:
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移连接配置失败。")
            conn.execute("BEGIN IMMEDIATE")
            self.auth_store.check_gate_policy(conn)
            version=conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0]
            if self._check_completed_migration_peer(conn,version):conn.commit();return
            if version==FINANCIAL_SCHEMA_VERSION:
                self._check_v7(conn);self._check_v7_attachments(conn);conn.commit();return
            if version in (4,5,6):
                from .source_integration import install_schema
                install_schema(conn,existing_required=True)
                conn.commit();return
            if version not in (1,2,3):raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移版本不支持。")
            for name in ("research_tasks","research_steps"):
                ddl=next(sql for sql in C0_SCHEMA if sql.startswith("CREATE TABLE IF NOT EXISTS "+name+" ("))
                previous=conn.execute("SELECT sql FROM sqlite_schema WHERE name=? AND type='table'",(name,)).fetchone()
                old=ddl.replace("IN ('c0-fixture-v1','d1-source-only-v1')","='c0-fixture-v1'").replace("IN ('offline_probe','live')","='offline_probe'")
                old=old.replace("IN (0,1,2)","IN (0,1)").replace("'discover_sources','fetch_source','compose_report'","'discover_sources','compose_report'")
                normalize=lambda sql:"".join(sql.replace("IF NOT EXISTS","").replace('"', '').split()).lower()
                if not previous or normalize(previous[0]) not in {normalize(ddl),normalize(old)}:
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究旧表结构与迁移基准不一致。")
                for extra in conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(name,)):
                    expected=next((sql for sql in C0_SCHEMA if sql.startswith("CREATE UNIQUE INDEX IF NOT EXISTS "+extra["name"]+" ")),None)
                    if extra["type"]!="index" or expected is None or normalize(extra["sql"])!=normalize(expected):
                        raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究旧表附属结构与迁移基准不一致。")
                conn.execute(ddl.replace("CREATE TABLE IF NOT EXISTS "+name,"CREATE TABLE "+name+"_v4",1))
                conn.execute(f"INSERT INTO {name}_v4 SELECT * FROM {name}")
            conn.execute("DROP TABLE research_steps")
            conn.execute("DROP TABLE research_tasks")
            conn.execute("ALTER TABLE research_tasks_v4 RENAME TO research_tasks")
            conn.execute("ALTER TABLE research_steps_v4 RENAME TO research_steps")
            for sql in C0_SCHEMA:
                if sql.startswith("CREATE UNIQUE INDEX"):conn.execute(sql)
            from .source_integration import install_schema
            install_schema(conn)
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移关联校验失败。")
            conn.execute("UPDATE research_schema SET version=4 WHERE id=1")
            conn.commit()
        except Exception:
            conn.rollback();raise
        finally:
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"研究迁移连接恢复失败。")
            finally:
                conn.close()

    @staticmethod
    @lru_cache(maxsize=1024)
    def _normalize_sql(sql):
        # Compare tokens, never flattened SQL text. Only SQLite's automatic
        # quoting of simple managed research_* names is normalized away.
        # Quoted identifiers with spaces/keywords keep their exact boundary.
        tokens=[]
        pattern=r"\s+|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|`(?:``|[^`])*`|\[[^\]]*\]|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|."
        for match in re.finditer(pattern,sql,re.S):
            value=match.group()
            if value.isspace():continue
            if value.startswith("'"):token=("literal",value)
            elif value[0] in ('"','`','['):
                unquoted=value[1:-1].replace(value[0]*2,value[0]) if value[0]!='[' else value[1:-1]
                token=("word",unquoted.lower()) if re.fullmatch(r"research_[A-Za-z_0-9]+",unquoted,re.I) else ("quoted_identifier",unquoted)
            elif re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*",value):token=("word",value.lower())
            elif value.isdigit():token=("number",value)
            else:token=("punctuation",value)
            tokens.append(token)
        optional=[("word","if"),("word","not"),("word","exists")]
        return tuple(token for i,token in enumerate(tokens) if not any(tokens[j:j+3]==optional and j<=i<j+3 for j in range(max(0,i-2),i+1)))

    def _migrate_v5(self):
        """Single-owner graph replacement; no application/upper-budget writes."""
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute("PRAGMA foreign_keys=OFF")
            if conn.execute("PRAGMA foreign_keys").fetchone()[0]!=0:
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本迁移连接配置失败。")
            conn.execute("BEGIN IMMEDIATE")
            self.auth_store.check_gate_policy(conn)
            version=conn.execute("SELECT version FROM research_schema WHERE id=1").fetchone()[0]
            if self._check_completed_migration_peer(conn,version):conn.commit();return
            if version==FINANCIAL_SCHEMA_VERSION:
                self._check_v7(conn);self._check_v7_attachments(conn);conn.commit();return
            if version==6:
                conn.commit();return
            if version==5:
                self._check_v5(conn)
                conn.commit();return
            if version!=4:raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本迁移版本不支持。")
            if conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_cost_observations'").fetchone():
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本迁移结构不一致。")
            legacy={s.split()[5]:s for s in (*SCHEMA,*C0_SCHEMA) if s.startswith("CREATE TABLE IF NOT EXISTS ")}
            for name,ddl in V5_SCHEMA.items():
                original=conn.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",(name,)).fetchone()
                if not original or self._normalize_sql(original[0])!=self._normalize_sql(legacy[name]):
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本旧表与迁移基准不一致。")
                for item in conn.execute("SELECT type,name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(name,)):
                    expected=next((s for s in C0_SCHEMA if s.startswith("CREATE UNIQUE INDEX IF NOT EXISTS "+item["name"]+" ")),None)
                    immutable=item["name"]==name+"_immutable" and name in ("research_price_revisions","research_balance_snapshots") and item["type"]=="trigger"
                    if immutable:
                        expected=f"CREATE TRIGGER {name}_immutable BEFORE UPDATE ON {name} BEGIN SELECT RAISE(ABORT,'immutable accounting record'); END"
                    if expected is None or self._normalize_sql(expected)!=self._normalize_sql(item["sql"]):
                        raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本旧表附属结构不一致。")
                clean=ddl.replace("CREATE TABLE IF NOT EXISTS ","CREATE TABLE ",1)
                conn.execute(clean.replace("CREATE TABLE "+name,"CREATE TABLE "+name+"_v5",1))
                columns=",".join('"'+row["name"]+'"' for row in conn.execute(f"PRAGMA table_info({name})"))
                conn.execute(f"INSERT INTO {name}_v5 ({columns}) SELECT {columns} FROM {name}")
            conn.execute("UPDATE research_funding_accounts_v5 SET initial_prepaid_units=cap,other_use_margin_units=0 WHERE mode='fixture'")
            for name in reversed(tuple(V5_SCHEMA)):
                conn.execute(f"DROP TABLE {name}")
            for name in V5_SCHEMA:
                conn.execute(f"ALTER TABLE {name}_v5 RENAME TO {name}")
            conn.execute(COST_SCHEMA)
            for ddl in V5_AUX:conn.execute(ddl)
            for ddl in C0_SCHEMA:
                if ddl.startswith("CREATE UNIQUE INDEX"):conn.execute(ddl)
            for ddl in V5_GUARDS:conn.execute(ddl)
            if conn.execute("PRAGMA foreign_key_check").fetchall():
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本迁移关联校验失败。")
            conn.execute("UPDATE research_schema SET version=5 WHERE id=1")
            self._check_v5(conn)
            conn.commit()
        except Exception:
            conn.rollback();raise
        finally:
            try:
                conn.execute("PRAGMA foreign_keys=ON")
                if conn.execute("PRAGMA foreign_keys").fetchone()[0]!=1:
                    raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本迁移连接恢复失败。")
            finally:conn.close()

    @classmethod
    def _check_v5(cls,conn):
        for name,ddl in (*V5_SCHEMA.items(),("research_cost_observations",COST_SCHEMA)):
            row=conn.execute("SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",(name,)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本结构不匹配。")
        for ddl in (*V5_AUX,*V5_GUARDS):
            name=ddl.split()[3] if ddl.startswith("CREATE UNIQUE INDEX") else ddl.split()[2]
            row=conn.execute("SELECT sql FROM sqlite_schema WHERE name=?",(name,)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):
                raise ResearchError("SCHEMA_UNSUPPORTED",503,"账本控制结构不匹配。")

    def _migrate_v6(self):
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute("PRAGMA foreign_keys=OFF")
            if conn.execute("PRAGMA foreign_keys").fetchone()[0]!=0:raise ResearchError("SCHEMA_UNSUPPORTED",503,"生产者迁移连接配置失败。")
            conn.execute("BEGIN IMMEDIATE");self.auth_store.check_gate_policy(conn)
            version=conn.execute("SELECT version FROM research_schema").fetchone()[0]
            if self._check_completed_migration_peer(conn,version):conn.commit();return
            if version==FINANCIAL_SCHEMA_VERSION:
                self._check_v7(conn);self._check_v7_attachments(conn);conn.commit();return
            if version==6:
                self._check_v6(conn);conn.commit();return
            if version!=5:raise ResearchError("SCHEMA_UNSUPPORTED",503,"生产者迁移版本不支持。")
            self._check_v5(conn)
            allowed={}
            for ddl in (*V5_AUX,*V5_GUARDS,*[s for s in C0_SCHEMA if s.startswith('CREATE UNIQUE INDEX')]):
                tokens=ddl.split();name=tokens[3] if ddl.startswith('CREATE UNIQUE INDEX') else tokens[2]
                if name=='IF':name=tokens[6]
                allowed[name]=ddl
            for table in V6_SCHEMA:
                for item in conn.execute("SELECT name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(table,)):
                    if item['name'] not in allowed or self._normalize_sql(item['sql'])!=self._normalize_sql(allowed[item['name']]):
                        raise ResearchError('SCHEMA_UNSUPPORTED',503,'生产者旧表附属结构不一致。')
            for name in ('research_paid_approvals','research_provider_sessions'):
                if conn.execute("SELECT 1 FROM sqlite_schema WHERE name=?",(name,)).fetchone():raise ResearchError("SCHEMA_UNSUPPORTED",503,"生产者结构不一致。")
            for name,ddl in V6_SCHEMA.items():
                clean=ddl.replace("CREATE TABLE IF NOT EXISTS ","CREATE TABLE ",1)
                conn.execute(clean.replace("CREATE TABLE "+name,"CREATE TABLE "+name+"_v6",1))
                columns=",".join('"'+r['name']+'"' for r in conn.execute(f"PRAGMA table_info({name})"))
                conn.execute(f"INSERT INTO {name}_v6 ({columns}) SELECT {columns} FROM {name}")
            for name in reversed(tuple(V6_SCHEMA)):conn.execute(f"DROP TABLE {name}")
            for name in V6_SCHEMA:conn.execute(f"ALTER TABLE {name}_v6 RENAME TO {name}")
            for ddl in PRODUCER_DDL:conn.execute(ddl)
            # Replace policy predicates by explicit v6 definitions; never
            # reinterpret an old row's immutable policy or historical amount.
            for ddl in (*V5_AUX,*V5_GUARDS):
                name=ddl.split()[3] if ddl.startswith('CREATE UNIQUE INDEX') else ddl.split()[2]
                conn.execute('DROP '+('INDEX' if ddl.startswith('CREATE UNIQUE INDEX') else 'TRIGGER')+' IF EXISTS '+name)
            for ddl in (*V6_AUX,*V5_GUARDS):conn.execute(ddl)
            for ddl in C0_SCHEMA:
                if ddl.startswith('CREATE UNIQUE INDEX'):conn.execute(ddl)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise ResearchError('SCHEMA_UNSUPPORTED',503,'生产者迁移关联校验失败。')
            conn.execute('UPDATE research_schema SET version=6 WHERE id=1');self._check_v6(conn);conn.commit()
        except Exception:conn.rollback();raise
        finally:
            try:
                conn.execute('PRAGMA foreign_keys=ON')
                if conn.execute('PRAGMA foreign_keys').fetchone()[0]!=1:raise ResearchError('SCHEMA_UNSUPPORTED',503,'生产者连接恢复失败。')
            finally:conn.close()

    @classmethod
    def _check_v6(cls,conn,*,method=False,formula=False):
        tables={**V5_SCHEMA,**V6_SCHEMA}
        tables.update({ddl.split()[2]:ddl for ddl in PRODUCER_DDL})
        if method:tables['research_provider_sessions']=cls._method_session_sql()
        if formula:tables.update(cls._formula_tables())
        for name,ddl in tables.items():
            row=conn.execute('SELECT sql FROM sqlite_schema WHERE name=? AND type=\'table\'',(name,)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):raise ResearchError('SCHEMA_UNSUPPORTED',503,'生产者结构不匹配。')
        for ddl in (*V6_AUX,*V5_GUARDS):
            name=ddl.split()[3] if ddl.startswith('CREATE UNIQUE INDEX') else ddl.split()[2]
            row=conn.execute('SELECT sql FROM sqlite_schema WHERE name=?',(name,)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):raise ResearchError('SCHEMA_UNSUPPORTED',503,'生产者控制结构不匹配。')

    @classmethod
    def _v7_required_legacy_objects(cls,*,method=False,formula=False):
        """Complete inherited baseline, with the reviewed version overlays."""
        required={}
        for ddl in (*SCHEMA,*C0_SCHEMA):
            tokens=ddl.split();offset=3 if tokens[1]=='UNIQUE' else 2
            if tokens[offset]=='IF':offset+=3
            required[tokens[offset]]=ddl
        required.update(V5_SCHEMA);required.update(V6_SCHEMA)
        for ddl in (*PRODUCER_DDL,*V6_AUX,*V5_GUARDS):
            tokens=ddl.split();offset=3 if tokens[1]=='UNIQUE' else 2
            required[tokens[offset]]=ddl
        required['research_principal_gate_required']="CREATE TRIGGER research_principal_gate_required BEFORE INSERT ON research_principals WHEN NEW.gate_id IS NULL BEGIN SELECT RAISE(ABORT, 'principal gate required'); END"
        required['research_billing_receipts_immutable']="CREATE TRIGGER research_billing_receipts_immutable BEFORE UPDATE ON research_billing_receipts BEGIN SELECT RAISE(ABORT,'immutable accounting record'); END"
        if method:required['research_provider_sessions']=cls._method_session_sql()
        if formula:required.update(cls._formula_tables())
        return required

    @classmethod
    def _check_v6_inherited(cls,conn,*,method=False,formula=False):
        for name,ddl in cls._v7_required_legacy_objects(method=method,formula=formula).items():
            row=conn.execute('SELECT type,sql FROM sqlite_schema WHERE name=?',(name,)).fetchone()
            expected_type='table' if ddl.startswith('CREATE TABLE') else 'trigger' if ddl.startswith('CREATE TRIGGER') else 'index'
            if not row or row['type']!=expected_type or cls._normalize_sql(row['sql'])!=cls._normalize_sql(ddl):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究必需基础结构不匹配。')
        cls._check_v6(conn,method=method,formula=formula)
        from .source_integration import install_schema
        install_schema(conn,existing_required=True)

    @classmethod
    def _check_v7(cls,conn,*,method=False,formula=False):
        cls._check_v6_inherited(conn,method=method,formula=formula)
        require_hook(conn)
        for ddl in (*V7_TABLES,*V7_GUARDS):
            name=ddl.split()[2]
            row=conn.execute('SELECT sql FROM sqlite_schema WHERE name=?',(name,)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融基础结构不匹配。')
        expected={ddl.split()[2]:ddl for ddl in V7_GUARDS}
        for ddl in V7_TABLES:
            for row in conn.execute("SELECT name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(ddl.split()[2],)):
                if row['name'] not in expected or cls._normalize_sql(row['sql'])!=cls._normalize_sql(expected[row['name']]):
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融附属结构不匹配。')
        if conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融存储关联不匹配。')
        from .financial_admission_schemas import ProjectBudget
        row=conn.execute('SELECT * FROM research_project_budgets WHERE id=1').fetchone()
        if row:
            try:project=ProjectBudget.model_validate(dict(row))
            except ValueError:raise ResearchError('SCHEMA_UNSUPPORTED',503,'项目预算结构不匹配。') from None
            from .provider_schemas import digest
            database=next((r[2] for r in conn.execute('PRAGMA database_list') if r[1]=='main'),None)
            if not database or project.database_binding!=digest(str(Path(database).resolve()).encode()):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'项目预算数据库绑定不匹配。')

    @classmethod
    def _check_v7_attachments(cls,conn,*,method=False):
        allowed={}
        for ddl in (*cls._v7_required_legacy_objects().values(),*V7_GUARDS):
            if not ddl.startswith(('CREATE INDEX','CREATE UNIQUE INDEX','CREATE TRIGGER')):continue
            tokens=ddl.split();offset=3 if tokens[1]=='UNIQUE' else 2
            if tokens[offset]=='IF':offset+=3
            allowed[tokens[offset]]=ddl
        if method:allowed.update({ddl.split()[2]:ddl for ddl in METHOD_GUARDS})
        # Preserve the existing extra-attachment policy; required inherited
        # objects are independently validated above and never recreated.
        for table in (*V5_SCHEMA,'research_cost_observations','research_paid_approvals','research_provider_sessions'):
            for row in conn.execute("SELECT name,sql FROM sqlite_schema WHERE tbl_name=? AND type IN ('index','trigger') AND sql IS NOT NULL",(table,)):
                if row['name'] not in allowed or cls._normalize_sql(row['sql'])!=cls._normalize_sql(allowed[row['name']]):
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融迁移发现未知附属结构。')

    def _migrate_v7(self):
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN IMMEDIATE')
            self.auth_store.check_gate_policy(conn)
            version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
            if self._check_completed_migration_peer(conn,version):conn.commit();return
            if version==FINANCIAL_SCHEMA_VERSION:
                self._check_v7(conn);self._check_v7_attachments(conn);conn.commit();return
            if version!=PRODUCER_SCHEMA_VERSION:raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融迁移版本不支持。')
            self._check_v6_inherited(conn);self._check_v7_attachments(conn)
            for ddl in (*V7_TABLES,*V7_GUARDS):
                if conn.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(ddl.split()[2],)).fetchone():
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融迁移发现部分新结构。')
            for ddl in (*V7_TABLES,*V7_GUARDS):conn.execute(ddl)
            conn.execute('UPDATE research_schema SET version=7 WHERE id=1')
            self._check_v7(conn)
            if conn.execute('PRAGMA foreign_key_check').fetchall():raise ResearchError('SCHEMA_UNSUPPORTED',503,'金融迁移关联校验失败。')
            conn.commit()
        except Exception:
            conn.rollback();raise
        finally:conn.close()

    @staticmethod
    def _auth_job_baseline_forms():
        if __package__=='web.backend.research':from ..services.auth_store import _BASE_SCHEMA_STATEMENTS
        else:from services.auth_store import _BASE_SCHEMA_STATEMENTS
        full=next(sql for sql in _BASE_SCHEMA_STATEMENTS if sql.startswith('CREATE TABLE IF NOT EXISTS auth_deletion_jobs'))
        legacy=full.replace("        legacy_attempted INTEGER NOT NULL DEFAULT 0 CHECK(legacy_attempted IN (0,1)),\n",'').replace(
            "        legacy_receipt_json TEXT CHECK(legacy_receipt_json IS NULL OR json_valid(legacy_receipt_json)),\n",'')
        legacy=legacy.rstrip()[:-1]+', legacy_attempted INTEGER NOT NULL DEFAULT 0 CHECK(legacy_attempted IN (0,1)), legacy_receipt_json TEXT CHECK(legacy_receipt_json IS NULL OR json_valid(legacy_receipt_json)))'
        return full,legacy

    @classmethod
    def _check_auth_job_schema(cls,conn,*,expanded):
        forms=cls._auth_job_baseline_forms()
        if expanded:forms=tuple(sql.rstrip()[:-1]+', '+', '.join(name+' '+ddl for name,ddl in JOB_ORIGIN_COLUMNS)+')' for sql in forms)
        row=conn.execute("SELECT type,sql FROM sqlite_schema WHERE name='auth_deletion_jobs'").fetchone()
        if not row or row['type']!='table' or cls._normalize_sql(row['sql']) not in {cls._normalize_sql(sql) for sql in forms}:
            raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除任务结构不匹配。')
        expected="CREATE UNIQUE INDEX auth_one_pending_deletion ON auth_deletion_jobs(owner_key) WHERE state!='completed'"
        index=conn.execute("SELECT sql FROM sqlite_schema WHERE name='auth_one_pending_deletion'").fetchone()
        if not index or cls._normalize_sql(index[0])!=cls._normalize_sql(expected):raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除任务索引不匹配。')
        allowed={'auth_one_pending_deletion':expected}
        if expanded:allowed.update({ddl.split()[2]:ddl for ddl in V8_JOB_GUARDS})
        for extra in conn.execute("SELECT name,sql FROM sqlite_schema WHERE tbl_name='auth_deletion_jobs' AND sql IS NOT NULL AND type IN ('index','trigger')"):
            if extra['name'] not in allowed or cls._normalize_sql(extra['sql'])!=cls._normalize_sql(allowed[extra['name']]):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除任务存在未知附属结构。')

    @classmethod
    def _check_v8(cls,conn,*,method=False,formula=False):
        cls._check_v7(conn,method=method,formula=formula);cls._check_auth_job_schema(conn,expanded=True)
        for ddl in V8_JOB_GUARDS:
            row=conn.execute('SELECT sql FROM sqlite_schema WHERE name=?',(ddl.split()[2],)).fetchone()
            if not row or cls._normalize_sql(row[0])!=cls._normalize_sql(ddl):raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除来源守卫不匹配。')

    def _migrate_v8_if_ready(self):
        self._require_development_migration()
        with self.transaction() as conn:
            version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
            if version==10:self._check_v10(conn)
        if version==FINANCIAL_SCHEMA_VERSION:self._migrate_v8()

    @staticmethod
    def _method_session_sql():
        old=next(ddl for ddl in PRODUCER_DDL if ddl.startswith('CREATE TABLE research_provider_sessions'))
        return old.rstrip()[:-1]+', '+', '.join(name+' '+ddl for name,ddl in METHOD_COLUMNS)+')'

    @classmethod
    def _structure_declarations(cls,statements):
        objects={}
        for sql in statements:
            tokens=cls._normalize_sql(sql)
            offset=2 if tokens[1]==('word','unique') else 1
            kind=tokens[offset][1];name=tokens[offset+1][1]
            target=name if kind=='table' else tokens[tokens.index(('word','on'))+1][1]
            objects[name]=(kind,target,(sql,))
        return objects

    @classmethod
    def _current_structure_declarations(cls,*,version=10):
        # Code-owned declarations only. No application objects or constructors.
        from .source_integration import SOURCE_DDL
        from .evidence_repository import DDL as evidence_ddl
        statements=(*cls._v7_required_legacy_objects(method=True).values(),*SOURCE_DDL,*evidence_ddl,
            *V7_TABLES,*V7_GUARDS,*V8_JOB_GUARDS,*METHOD_GUARDS)
        objects=cls._structure_declarations(statements)
        if version==10:
            from .formula_runtime import FORMULA_DDL
            objects.update(cls._structure_declarations((*cls._formula_tables().values(),*FORMULA_DDL)))
        elif version!=9:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究版本不支持。')
        forms=tuple(sql.rstrip()[:-1]+', '+', '.join(name+' '+ddl for name,ddl in JOB_ORIGIN_COLUMNS)+')'
            for sql in cls._auth_job_baseline_forms())
        objects['auth_deletion_jobs']=('table','auth_deletion_jobs',forms)
        objects.update(cls._structure_declarations(("CREATE UNIQUE INDEX auth_one_pending_deletion ON auth_deletion_jobs(owner_key) WHERE state!='completed'",)))
        return objects

    @classmethod
    def _check_declared_structure(cls,conn,objects,*,catalog=None):
        if catalog is None:
            catalog={row[1]:tuple(row) for row in conn.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema')}
        for name,(kind,target,forms) in objects.items():
            row=catalog.get(name)
            if (not row or row[0]!=kind or row[2]!=target or row[3] is None
                    or cls._normalize_sql(row[3]) not in {cls._normalize_sql(sql) for sql in forms}):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'当前研究存储结构不匹配。')
        return catalog

    @classmethod
    def _declared_columns(cls,sql):
        tokens=cls._normalize_sql(sql);depth=0;segments=[];current=[]
        for token in tokens[tokens.index(('punctuation','('))+1:]:
            if token==('punctuation',')') and depth==0:
                segments.append(current);break
            if token==('punctuation',',') and depth==0:
                segments.append(current);current=[];continue
            current.append(token)
            if token==('punctuation','('):depth+=1
            elif token==('punctuation',')'):depth-=1
        constraints={'check','primary','foreign','unique','constraint'}
        return tuple((part[0][1],part[1][1]) for part in segments
            if part and part[0][1] not in constraints)

    @classmethod
    def check_current_structure(cls,conn):
        return cls._check_structure_version(conn,10)

    @classmethod
    def _check_structure_version(cls,conn,version):
        """Current Research metadata only, in the caller's existing snapshot.

        This does not certify Auth base rows/policy, FK data, budget bindings,
        connection hooks, native read-only access, or application readiness.
        No connection, transaction, hook, migration, or business-row operation.
        """
        if not isinstance(conn,sqlite3.Connection) or not conn.in_transaction:
            raise ResearchError('SCHEMA_UNSUPPORTED',503,'结构检查需要调用方的事务快照。')
        objects=cls._current_structure_declarations(version=version)
        tables={name for name,(kind,_,_) in objects.items() if kind=='table'}
        catalog={}
        # Reject unknown/view/vtab objects before any object-specific PRAGMA.
        for value in conn.execute('SELECT type,name,tbl_name,sql FROM main.sqlite_schema'):
            row=tuple(value);kind,name,target,sql=row
            if name not in objects and not name.startswith('research_') and target not in tables:continue
            if name in catalog:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究结构存在名称冲突。')
            catalog[name]=row
            if name in objects:continue
            automatic=(kind=='index' and sql is None and target in tables
                and re.fullmatch(r'sqlite_autoindex_'+re.escape(target)+r'_[0-9]+',name) is not None)
            if not automatic:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究结构存在未知对象。')
        cls._check_declared_structure(conn,objects,catalog=catalog)
        marker=[tuple(row) for row in conn.execute('SELECT id,version FROM main.research_schema')]
        if marker!=[(1,version)] or any(type(value) is not int for value in marker[0]):
            raise ResearchError('SCHEMA_UNSUPPORTED',503,'当前研究版本标记不匹配。')
        columns={}
        for name in tables:
            # Both accepted Auth-job layouts retain their actual column order.
            sql=next(form for form in objects[name][2] if cls._normalize_sql(form)==cls._normalize_sql(catalog[name][3]))
            expected=cls._declared_columns(sql)
            actual=[tuple(row) for row in conn.execute("PRAGMA main.table_xinfo('"+name+"')")]
            if tuple((row[1],row[2].lower()) for row in actual)!=expected or any(row[0]!=i or row[6]!=0 for i,row in enumerate(actual)):
                raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究列结构不匹配。')
            columns[name]={column for column,_ in expected}
        for name in tables:
            for fk in conn.execute("PRAGMA main.foreign_key_list('"+name+"')"):
                if fk[2] not in columns or fk[3] not in columns[name] or (fk[4] is not None and fk[4] not in columns[fk[2]]):
                    raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究外键声明不匹配。')
            indexes=[tuple(row) for row in conn.execute("PRAGMA main.index_list('"+name+"')")]
            known={key for key,value in catalog.items() if value[0]=='index' and value[2]==name}
            if {row[1] for row in indexes}!=known:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究索引集合不匹配。')
            for index in indexes:
                row=catalog[index[1]];sql=row[3]
                if sql is None:
                    if index[2]!=1 or index[3] not in ('pk','u') or index[4]!=0:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究自动索引不匹配。')
                else:
                    tokens=cls._normalize_sql(sql)
                    if index[2]!=int(tokens[1]==('word','unique')) or index[3]!='c' or index[4]!=int(('word','where') in tokens):
                        raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究索引声明不匹配。')
                for part in conn.execute("PRAGMA main.index_xinfo('"+index[1]+"')"):
                    if part[5] and (part[1]<0 or part[2] not in columns[name]):raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究索引列不匹配。')

    @classmethod
    def _check_v9(cls,conn):
        cls._check_v8(conn,method=True);cls._check_v7_attachments(conn,method=True)
        cls._check_declared_structure(conn,cls._structure_declarations(METHOD_GUARDS))
        cls._check_method_hook(conn)

    @staticmethod
    def _check_method_hook(conn):
        try:version=conn.execute('SELECT research_method_guard_version(),research_method_write_allowed(?,?,?)',('probe','','{}')).fetchone()
        except sqlite3.Error:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究正文连接守卫不可用。') from None
        if tuple(version)!=(9,0):raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究正文连接守卫不匹配。')

    def _migrate_v9_if_ready(self):
        self._require_development_migration()
        with self.transaction() as conn:
            version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
            if version==10:self._check_v10(conn)
        if version==DELETION_SCHEMA_VERSION:self._migrate_v9()

    def _migrate_v9(self):
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN IMMEDIATE');self.auth_store.check_gate_policy(conn)
            version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
            if version==10:self._check_v10(conn);conn.commit();return
            if version==METHOD_SCHEMA_VERSION:self._check_structure_version(conn,9);self._check_v9(conn);conn.commit();return
            if version!=DELETION_SCHEMA_VERSION:raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究正文迁移版本不支持。')
            self._check_v8(conn);self._check_v7_attachments(conn)
            for ddl in METHOD_GUARDS:
                if conn.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(ddl.split()[2],)).fetchone():raise ResearchError('SCHEMA_UNSUPPORTED',503,'研究正文存在部分守卫。')
            for name,ddl in METHOD_COLUMNS:conn.execute('ALTER TABLE research_provider_sessions ADD COLUMN '+name+' '+ddl)
            for ddl in METHOD_GUARDS:conn.execute(ddl)
            conn.execute('UPDATE research_schema SET version=9 WHERE id=1');self._check_v9(conn);conn.commit()
        except Exception:conn.rollback();raise
        finally:conn.close()

    def _migrate_v8(self):
        self._require_development_migration()
        conn=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        try:
            conn.row_factory=sqlite3.Row
            install_default_hook(conn)
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN IMMEDIATE');self.auth_store.check_gate_policy(conn)
            version=conn.execute('SELECT version FROM research_schema WHERE id=1').fetchone()[0]
            if self._check_completed_migration_peer(conn,version):conn.commit();return
            if version!=FINANCIAL_SCHEMA_VERSION:raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除来源迁移版本不支持。')
            self._check_v7(conn);self._check_v7_attachments(conn);self._check_auth_job_schema(conn,expanded=False)
            for ddl in V8_JOB_GUARDS:
                if conn.execute('SELECT 1 FROM sqlite_schema WHERE name=?',(ddl.split()[2],)).fetchone():raise ResearchError('SCHEMA_UNSUPPORTED',503,'删除来源存在部分守卫。')
            for name,ddl in JOB_ORIGIN_COLUMNS:conn.execute('ALTER TABLE auth_deletion_jobs ADD COLUMN '+name+' '+ddl)
            for ddl in V8_JOB_GUARDS:conn.execute(ddl)
            conn.execute('UPDATE research_schema SET version=8 WHERE id=1');self._check_v8(conn)
            conn.commit()
        except Exception:conn.rollback();raise
        finally:conn.close()

    @classmethod
    def _formula_tables(cls):
        from .formula_runtime import formula_table_overlay
        return formula_table_overlay(V6_SCHEMA['research_tasks'],V5_SCHEMA['research_steps'])

    @classmethod
    def _check_v10(cls,conn):
        if __package__=='web.backend.research':from ..services.auth_store import AuthStore
        else:from services.auth_store import AuthStore
        AuthStore.check_gate_policy(conn)
        cls.check_current_structure(conn)
        cls._check_v8(conn,method=True,formula=True)
        cls._check_v7_attachments(conn,method=True)
        cls._check_declared_structure(conn,cls._structure_declarations(METHOD_GUARDS))
        cls._check_method_hook(conn)
        from .formula_runtime import require_hook
        require_hook(conn)

    def migrate_formula_v10(self,*,maintenance):
        """Explicit offline provisioning only; never called by constructor/helper."""
        from .formula_runtime import migrate_v10
        return migrate_v10(self,maintenance=maintenance)

    @contextmanager
    def transaction(self, *, write=False):
        formal=self._formal_mode()
        conn=self._connect(readonly=not write)
        try:
            conn.row_factory = sqlite3.Row
            install_default_hook(conn)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA secure_delete=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            self.auth_store.check_gate_policy(conn)
            if formal:
                self._check_v10(conn)
            from .paid_control import _transaction_scope
            with _transaction_scope(conn,write=write):
                yield conn
                conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            if getattr(exc, "sqlite_errorcode", 0) & 255 in (5, 6):
                raise ResearchError("STORE_BUSY", 503, "保存暂时繁忙，请用原操作重试。", retryable=True) from None
            raise ResearchError("STORE_UNAVAILABLE", 503, "研究存储暂时不可用。") from None
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def checkpoint_erasure(self):
        """Do not report erasure while old WAL frames are held by a reader."""
        formal=self._formal_mode()
        conn=self._connect()
        try:
            conn.row_factory = sqlite3.Row
            if formal:
                install_default_hook(conn)
                conn.execute('PRAGMA foreign_keys=ON');conn.execute('BEGIN')
                self._check_v10(conn)
            self.auth_store.check_gate_policy(conn)
            if formal:conn.commit()
            conn.execute("PRAGMA busy_timeout=5000")
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result[0] != 0:
                raise ResearchError("STORE_BUSY", 503, "删除等待存储清理完成。", retryable=True)
        finally:
            conn.close()
