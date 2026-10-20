"""Same-auth-DB glue for a fixed, free source-only plan; no provider money."""
from __future__ import annotations

import base64
import json
import os
from uuid import uuid4

from .authorization import AuthorizationGate
from .budget import now
from .errors import ResearchError,not_found
from .evidence_repository import DDL,EvidenceContext,EvidenceRepository
from .evidence_schemas import AnalysisPlan,canonical,sha256
from .source_policy import discovery_target

POLICY="d1-source-only-v1"
PUBLIC_KINDS={"sources":"snapshots","excerpts":"excerpts","claims":"claims","reports":"reports"}


def normalized_query(query):
    return " ".join(query.lower().split())


def source_chains(conn,principal_id,research_id,query):
    # Also group pre-fix candidate chains by their actual approved outbound
    # query. A local problem edit or an old fingerprint must not reset quota.
    rows=conn.execute("""SELECT c.*,a.query FROM research_source_chains c
        LEFT JOIN research_source_runs r ON r.chain_id=c.id
        LEFT JOIN research_source_approvals a ON a.id=r.approval_id
        WHERE c.principal_id=? AND c.research_id=? ORDER BY c.id""",(principal_id,research_id)).fetchall()
    fingerprint=outbound_fingerprint(query)
    return list({row["id"]:row for row in rows if row["fingerprint"]==fingerprint or
        (row["query"] is not None and normalized_query(row["query"])==normalized_query(query))}.values())


def outbound_fingerprint(query):
    return sha256(canonical({"query":normalized_query(query),"operation_family":"crossref-plos-method-get"}).encode())


def unclosed_sources(conn,chains):
    return any(conn.execute("SELECT 1 FROM research_source_requests WHERE chain_id=? AND outcome IN ('SENDING','UNKNOWN') AND execution_closed=0",(chain["id"],)).fetchone() for chain in chains)


def project_task(conn,view,task):
    run=conn.execute("SELECT a.query FROM research_source_runs r JOIN research_source_approvals a ON a.id=r.approval_id WHERE r.task_id=?",(task["id"],)).fetchone()
    chains=source_chains(conn,task["principal_id"],task["research_id"],run["query"]) if run else []
    observations=[]
    for chain in chains:
        observations.extend(conn.execute("""SELECT r.id,r.task_id,t.input_revision,r.outcome,r.execution_closed,r.started_at,r.ended_at,p.id AS prior_ref
            FROM research_source_requests r JOIN research_tasks t ON t.id=r.task_id
            LEFT JOIN research_source_requests p ON p.dispatch_id=r.prior_dispatch_id
            WHERE r.chain_id=? AND r.outcome IN ('SENDING','UNKNOWN')""",(chain["id"],)).fetchall())
    pending=sum(not row["execution_closed"] for row in observations)
    closed=sum(bool(row["execution_closed"]) for row in observations)
    last=conn.execute("SELECT seq FROM research_task_events WHERE task_id=? ORDER BY seq DESC LIMIT 1",(task["id"],)).fetchone()
    execution=task["execution"]
    actions=["view","refresh"]
    if execution not in ("COMPLETED","FAILED","CANCELLED","ACCESS_REVOKED"):actions.append("cancel")
    view.update({"execution":execution,"evidence":task["evidence"],"execution_mode":task["execution_mode"],
        "status":{"QUEUED":"queued","RUNNING":"retrieving","WAITING_EXTERNAL":"retrieving","RECONCILING":"retrieving","COMPLETED":"insufficient","FAILED":"failed","CANCELLED":"cancelled","ACCESS_REVOKED":"cancelled"}[execution],
        "detail":"reconciliation_required" if pending else "unknown_outcome" if closed else "partial_results" if execution=="COMPLETED" else "normal",
        "report_status":"notes","model_analysis_ran":False,"statistics_ran":False,"price_series_available":False,
        "task":{"id":task["id"],"version":task["version"],"execution":execution,"phase":task["phase"],"attempt":1,
            "input_revision":task["input_revision"],"stop_requested":bool(task["stop_requested"]),"policy_revision":POLICY},
        "source_quota":{"used":sum(row["used"] for row in chains),"limit":4,"unknown_count":len(observations),"unknown_closed":closed,"unknown_unclosed":pending,"cost_mode":"free_get"},
        "source_observations":[{"observation_ref":r["id"],"task_id":r["task_id"],"input_revision":r["input_revision"],
            "state":"outcome_unknown" if r["outcome"]=="UNKNOWN" else "awaiting_result","execution_closed":bool(r["execution_closed"]),
            "started_at":r["started_at"],"ended_at":r["ended_at"],"prior_observation_ref":r["prior_ref"],"result_restored":False}
            for r in sorted(observations,key=lambda r:r["started_at"])[-20:]],
        "allowed_next_actions":actions,"task_event_cursor":last[0] if last else 0,
        "notes":["仅整理方法来源与短摘录；未运行模型分析、行情计算或统计检验。"]})


def public_record(record,kind,source,reported_at=None):
    item={"id":record.id,"kind":kind,"research_id":record.research_id,"task_id":record.task_id,"input_revision":record.input_revision}
    fields={"sources":("title","canonical_url","access"),
        "excerpts":("start","end","quote"),
        "claims":("text","excerpt_refs","limitations","level","assessment"),
        "reports":("outstanding_requirements","status","evidence","model_analysis_ran","statistics_ran")}[kind]
    item.update({name:getattr(record,name) for name in fields})
    if kind=="sources":
        item.update(id=record.source_id,revision=record.source_revision,research_id=record.research_id,kind="external_html",
            authors=[],published_at=None,accessed_at=record.acquired_at,
            retrieval_scope=f"{record.origin}: licensed method document only; cutoff {record.information_cutoff}",
            content_digest=record.raw_digest,extracted_text_digest=record.extracted_digest,extractor_version=record.parser_version,
            read_scope={"plos-html-text-v1":"legacy_page_unverified","plos-author-narrative-subset-v2":"author_narrative_subset"}[record.parser_version],
            license_note=record.licence.basis[:400],failure_code=None,execution_mode="live" if record.origin=="live" else "offline_probe")
    elif kind=="excerpts":
        snapshot=source(record.snapshot_id)
        item.update(source_id=snapshot.source_id,source_revision=snapshot.source_revision,text_digest=record.extracted_digest,
            page_number=None,extraction="plain",extraction_review="unreviewed")
    elif kind=="reports":
        if not reported_at:raise ValueError("report publication event unavailable")
        item["source_revisions"]=[{"source_id":snapshot.source_id,"revision":snapshot.source_revision,"content_digest":snapshot.raw_digest,"access":snapshot.access,
            "read_scope":{"plos-html-text-v1":"legacy_page_unverified","plos-author-narrative-subset-v2":"author_narrative_subset"}[snapshot.parser_version]} for snapshot in map(source,record.snapshot_refs)]
        item["claim_ids"]=record.claim_refs
        item.update(attempt=record.attempt,check_ids=[],limitations=record.outstanding_requirements,created_at=reported_at,
            execution_mode="live" if record.origin=="live" else "offline_probe")
        item["digest"]=sha256(canonical(item).encode())
    return item


def records(service,identity,rid,task_id,kind,cursor=None,*,request_app=None):
    require_enabled(request_app,capability="source_history",store=service.store);rid=service._id(rid);task_id=service._id(task_id);pid=service._principal(identity)
    if kind not in PUBLIC_KINDS:raise not_found()
    with service.store.transaction() as conn:
        control=service.authorization.check(conn,identity,pid,rid)
        task=conn.execute("SELECT * FROM research_tasks WHERE id=? AND research_id=? AND policy_revision=?",(task_id,rid,POLICY)).fetchone()
        if not task:raise not_found()
        binding={"actor":pid,"epoch":task["principal_epoch"],"generation":sha256(identity.generation.encode()),"research":rid,
            "input":task["input_revision"],"task":task_id,"kind":kind,"version":control["version"],"task_version":task["version"]}
        offset=0
        if cursor:
            try:
                if len(cursor)>2048:raise ValueError()
                decoded=json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
                if type(decoded) is not dict:raise ValueError()
                offset=decoded.pop("offset")
                if decoded!=binding or type(offset) is not int or not 0<=offset<=10000:raise ValueError()
            except (ValueError,TypeError,KeyError,UnicodeError):
                raise ResearchError("REVISION_CONFLICT",409,"记录游标已失效，请重新读取。") from None
        context=context_for(conn,task_id)
        repository=EvidenceRepository(conn,authorizer(service.store,identity=identity))
        rows=conn.execute("SELECT id FROM research_evidence_objects WHERE research_id=? AND input_revision=? AND task_id=? AND kind=? ORDER BY id LIMIT 21 OFFSET ?",(rid,task["input_revision"],task_id,PUBLIC_KINDS[kind],offset)).fetchall()
        items=[];size=0
        event=conn.execute("SELECT at FROM research_task_events WHERE task_id=? AND kind='terminal' AND safe_code IS NULL ORDER BY seq LIMIT 1",(task_id,)).fetchone() if kind=="reports" else None
        for row in rows[:20]:
            try:item=public_record(repository.get(context,PUBLIC_KINDS[kind],row[0]),kind,lambda ref:repository.get(context,"snapshots",ref),event[0] if event else None)
            except PermissionError:raise not_found() from None
            except (ValueError,LookupError):raise ResearchError("STORE_UNAVAILABLE",503,"证据记录当前无法核对。") from None
            size+=len(canonical(item).encode())
            if size>500000:break
            items.append(item)
        next_cursor=base64.urlsafe_b64encode(canonical({**binding,"offset":offset+len(items)}).encode()).decode() if len(rows)>len(items) else None
        return {"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"kind":kind,"items":items,"next_cursor":next_cursor,"research_version":control["version"],"task_version":task["version"]}}

SOURCE_DDL=(
    """CREATE TABLE research_source_approvals (
        id TEXT PRIMARY KEY,principal_id TEXT NOT NULL REFERENCES research_principals(id),principal_epoch INTEGER NOT NULL,
        auth_generation TEXT,research_id TEXT REFERENCES research_controls(id) ON DELETE CASCADE,
        input_revision INTEGER,problem_digest TEXT,query TEXT,plan_json TEXT,plan_digest TEXT,
        fingerprint TEXT,execution_mode TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL CHECK(status IN ('active','consumed','revoked')),consumed_task_id TEXT,created_at TEXT NOT NULL)""",
    """CREATE TABLE research_source_chains (
        id TEXT PRIMARY KEY,principal_id TEXT NOT NULL REFERENCES research_principals(id),
        research_id TEXT REFERENCES research_controls(id) ON DELETE SET NULL,fingerprint TEXT,
        used INTEGER NOT NULL DEFAULT 0 CHECK(used BETWEEN 0 AND 4),UNIQUE(principal_id,research_id,fingerprint))""",
    """CREATE TABLE research_source_runs (
        task_id TEXT PRIMARY KEY REFERENCES research_tasks(id),approval_id TEXT,
        chain_id TEXT NOT NULL REFERENCES research_source_chains(id),plan_id TEXT NOT NULL,
        fingerprint TEXT,origin TEXT NOT NULL CHECK(origin IN ('offline_probe','live')),
        started INTEGER NOT NULL DEFAULT 0,write_epoch INTEGER NOT NULL DEFAULT 1,task_gate_identity TEXT)""",
    """CREATE TABLE research_source_requests (
        id TEXT PRIMARY KEY,chain_id TEXT NOT NULL REFERENCES research_source_chains(id),
        task_id TEXT NOT NULL REFERENCES research_tasks(id),step_id TEXT NOT NULL REFERENCES research_steps(id),
        semantic TEXT NOT NULL,target_digest TEXT NOT NULL,dispatch_id TEXT NOT NULL UNIQUE,
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 4),write_epoch INTEGER NOT NULL,
        outcome TEXT NOT NULL CHECK(outcome IN ('SENDING','SUCCEEDED','FAILED','UNKNOWN')),
        execution_closed INTEGER NOT NULL DEFAULT 0 CHECK(execution_closed IN (0,1)),closure_ref TEXT,closure_proof TEXT,
        owner_gate_identity TEXT NOT NULL,task_gate_identity TEXT NOT NULL,
        started_at TEXT NOT NULL,ended_at TEXT,http_status INTEGER,safe_code TEXT NOT NULL DEFAULT 'none',
        prior_dispatch_id TEXT,UNIQUE(chain_id,ordinal),UNIQUE(task_id,semantic,target_digest))""",
)


def install_schema(conn,*,existing_required=False):
    source=SOURCE_DDL
    marker=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_schema'").fetchone()
    if marker and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
        from .source_guard import approval_table
        source=(approval_table(),*SOURCE_DDL[1:])
    statements=(*source,*DDL)
    existing=[]
    for statement in statements:
        # Exact existing objects are accepted for the legacy v1 gate-column
        # repair path. Partial or changed evidence schemas are never repaired
        # through destructive recreation.
        name=statement.split()[2]
        row=conn.execute("SELECT sql FROM sqlite_schema WHERE name=?",(name,)).fetchone()
        if row is not None and " ".join(row[0].split())!=" ".join(statement.split()):
            raise ResearchError("SCHEMA_UNSUPPORTED",503,"来源证据存储结构不匹配。")
        existing.append(row is not None)
    if any(existing) and not all(existing):
        raise ResearchError("SCHEMA_UNSUPPORTED",503,"来源证据存储结构不完整。")
    if existing_required and not all(existing):
        raise ResearchError("SCHEMA_UNSUPPORTED",503,"来源证据存储结构缺失。")
    if not any(existing):
        for statement in statements:conn.execute(statement)


def enabled():
    return (os.getenv("STRUCTURAL_ENV","dev").lower()!="prod"
            and os.getenv("STRUCTURAL_RESEARCH_ENABLED","").lower()=="true"
            and os.getenv("STRUCTURAL_D1_SOURCES_ENABLED","").lower()=="true")


def require_enabled(request_app=None,*,capability='source_execute',store=None):
    from .runtime_profile import formal_request_required,require_formal_application
    if formal_request_required(request_app) or (store is not None and store._formal_mode()):
        if request_app is None and capability=='source_execute' and store is not None:
            # Only the supervisor's current native thread/slot can enter here.
            # Never recurse through HTTP/Main capability admission from a worker.
            from .source_supervisor import _require_store_worker
            _require_store_worker(store,operation='send')
            return
        require_formal_application(request_app,capability)
        return
    if not enabled():raise ResearchError("FEATURE_UNAVAILABLE",503,"来源证据子链尚未开放。")


def origin():
    from .runtime_profile import formal_request_required
    if formal_request_required():return 'live'
    return "live" if os.getenv("STRUCTURAL_D1_PUBLIC_GET_ENABLED","").lower()=="true" else "offline_probe"


def draft(problem_digest,query):
    discovery_target(query)  # The already-reviewed fixed target grammar.
    fields={"query":query,"objective":"Collect licensed method evidence; no market or causal conclusion.",
            "competing_explanations":["Common external drivers","Measurement and sample-window effects"],
            "required_evidence":["Identified licensed originals","Exact short excerpts and unresolved limits"],
            "stop_rule":"At most four fixed GET requests; stop on unavailable permission or execution uncertainty.",
            "policy_revision":POLICY,"max_requests":4,"execution_mode":origin(),
            "samples":["NASDAQ:GFS","SSE:688981","HKEX:00981"],"exploration":"2024-01-01/2025-12-31",
            "validation":"2026-01-01/2026-09-30","price_series_available":False}
    plan_digest=sha256(canonical(fields).encode())
    # IDs, revision counters and policy *labels* cannot reset the same
    # normalized outbound operation. The semantic source family is fixed.
    fingerprint=outbound_fingerprint(query)
    input_digest=sha256(canonical({"problem_digest":problem_digest,"plan_digest":plan_digest}).encode())
    return fields,plan_digest,fingerprint,input_digest


def plan_for(task,approval,plan_id):
    fields=json.loads(approval["plan_json"])
    return AnalysisPlan(id=plan_id,research_id=task["research_id"],input_revision=task["input_revision"],
        task_id=task["id"],attempt=1,input_digest=task["input_digest"],query=fields["query"],external_query_approved=True,
        objective=fields["objective"],competing_explanations=tuple(fields["competing_explanations"]),
        required_evidence=tuple(fields["required_evidence"]),stop_rule=fields["stop_rule"],created_at=task["created_at"])


def context_for(conn,task_id,step_id=None):
    task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
    step=conn.execute("SELECT * FROM research_steps WHERE task_id=? "+("AND id=?" if step_id else "ORDER BY position LIMIT 1"),(task_id,step_id) if step_id else (task_id,)).fetchone()
    if not task or not step or not task["research_id"] or not task["input_digest"]:raise not_found()
    return EvidenceContext(research_id=task["research_id"],input_revision=task["input_revision"],task_id=task_id,attempt=1,
        input_digest=task["input_digest"],principal_id=task["principal_id"],principal_epoch=task["principal_epoch"],
        owner_epoch=task["owner_epoch"],acl_epoch=task["acl_epoch"],task_version=task["version"],
        step_id=step["id"],step_version=step["version"])


def authorizer(store,*,identity=None,delete_job=None):
    gate=AuthorizationGate(store)
    def authorize(conn,context,operation):
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(context.task_id,)).fetchone()
        step=conn.execute("SELECT * FROM research_steps WHERE id=? AND task_id=?",(context.step_id,context.task_id)).fetchone()
        if not task or not step or task["policy_revision"]!=POLICY:raise PermissionError("evidence task unavailable")
        if (task["research_id"]!=context.research_id or task["input_revision"]!=context.input_revision
                or task["input_digest"]!=context.input_digest or task["version"]!=context.task_version
                or step["version"]!=context.step_version or task["attempt"]!=context.attempt
                or task["principal_id"]!=context.principal_id or task["principal_epoch"]!=context.principal_epoch
                or task["owner_epoch"]!=context.owner_epoch or task["acl_epoch"]!=context.acl_epoch):
            raise PermissionError("stale evidence context")
        if operation=="delete":
            job=conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'",(delete_job,)).fetchone()
            principal=conn.execute("SELECT * FROM research_principals WHERE id=?",(task["principal_id"],)).fetchone()
            control=conn.execute("SELECT lifecycle,owner_id FROM research_controls WHERE id=?",(context.research_id,)).fetchone()
            if (not job or not principal or principal["status"]!="deleting" or principal["normalized_email"]!=job["owner_email"]
                    or principal["session_generation"]!=job["session_generation"] or principal["gate_id"]!=job["gate_id"]
                    or job["database_binding"]!=sha256(str(store.path).encode()) or not control or control[0]!="deleting" or control[1]!=task["principal_id"]):
                raise PermissionError("evidence deletion unavailable")
            return True
        if identity is not None:
            gate.check(conn,identity,context.principal_id,context.research_id)
        elif operation!="write":raise PermissionError("authenticated evidence read required")
        if operation=="write":
            gate.check_task(conn,task)
            if task["execution"] in ("FAILED","CANCELLED","COMPLETED","ACCESS_REVOKED") or step["state"] in ("UNKNOWN","DISCARDED","FAILED"):
                raise PermissionError("evidence write ended")
            check_approval(conn,task)
        return True
    return authorize


def purge_for_deletion(store,conn,task_id,job_id):
    task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
    if not task or task["policy_revision"]!=POLICY:return
    EvidenceRepository(conn,authorizer(store,delete_job=job_id)).purge(context_for(conn,task_id))
    conn.execute("UPDATE research_source_runs SET approval_id=NULL,fingerprint=NULL WHERE task_id=?",(task_id,))
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
        from .source_guard import erase_resource
        erase_resource(conn,task_id)
        conn.execute("UPDATE research_source_chains SET fingerprint=NULL,research_id=NULL WHERE id IN (SELECT chain_id FROM research_source_runs WHERE task_id=?)",(task_id,))
    else:
        conn.execute("UPDATE research_source_chains SET fingerprint=NULL WHERE id IN (SELECT chain_id FROM research_source_runs WHERE task_id=?)",(task_id,))


def check_approval(conn,task):
    run=conn.execute("SELECT * FROM research_source_runs WHERE task_id=?",(task["id"],)).fetchone()
    approval=conn.execute("SELECT * FROM research_source_approvals WHERE id=?",(run["approval_id"],)).fetchone() if run else None
    if (not approval or approval["version"]!=1 or approval["status"] not in ("active","consumed")
            or (approval["status"]=="consumed" and approval["consumed_task_id"]!=task["id"])
            or approval["principal_id"]!=task["principal_id"] or approval["principal_epoch"]!=task["principal_epoch"]
            or approval["auth_generation"]!=task["auth_generation"] or approval["research_id"]!=task["research_id"]
            or approval["input_revision"]!=task["input_revision"] or approval["execution_mode"]!=task["execution_mode"]):
        raise PermissionError("source approval unavailable")
    fields,pd,fp,inp=draft(approval["problem_digest"],approval["query"])
    legacy=sha256(canonical({"problem_digest":approval["problem_digest"],"query":normalized_query(approval["query"]),"operation_family":"crossref-plos-method-get"}).encode())
    if pd!=approval["plan_digest"] or canonical(fields)!=approval["plan_json"] or inp!=task["input_digest"] or run["fingerprint"] not in (fp,legacy) or run["fingerprint"]!=approval["fingerprint"]:
        raise PermissionError("source approval binding changed")
    revision=conn.execute("SELECT digest FROM research_revisions WHERE research_id=? AND revision=?",(task["research_id"],task["input_revision"])).fetchone()
    if not revision or revision[0]!=approval["problem_digest"]:raise PermissionError("source input unavailable")
    return run,approval


def preview(service,identity,rid,request,*,request_app=None):
    require_enabled(request_app,store=service.store);rid=service._id(rid);pid=service._principal(identity)
    with service.store.transaction() as conn:
        row=service.authorization.check(conn,identity,pid,rid)
        if row["current_revision"]!=request.input_revision or row["version"]!=request.expected_research_version:
            raise ResearchError("REVISION_CONFLICT",409,"预览基准已变化，请明确载入最新问题。")
        problem=conn.execute("SELECT digest FROM research_revisions WHERE research_id=? AND revision=?",(rid,request.input_revision)).fetchone()
        fields,pd,fp,inp=draft(problem[0],request.query)
        return {"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{
            "input_revision":request.input_revision,"research_version":row["version"],"query":request.query,
            "plan":fields,"preview_digest":sha256(canonical({"plan_digest":pd,"input_digest":inp}).encode()),
            "model_analysis_ran":False,"statistics_ran":False,"price_series_available":False}}


def _source_scope(conn,service,owner,identity,rid,request,key,source,*,admit=False):
    from contextlib import nullcontext
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] not in (11,12,13,14):return nullcontext()
    from .source_guard import approval_scope,admission_scope
    return (admission_scope if admit else approval_scope)(conn,service,owner,identity,rid,request,key,source)


def approve(service,identity,rid,request,key,*,request_source=None,request_app=None):
    require_enabled(request_app,store=service.store);rid=service._id(rid);pid=service._principal(identity)
    payload=request.model_dump(mode="json")
    from .service import digest
    with service.authorization.owner_gate(pid) as owner,service.store.transaction(write=True) as conn,_source_scope(conn,service,owner,identity,rid,request,key,request_source):
        row=service.authorization.check(conn,identity,pid,rid,scope="write")
        replay=service._replay(conn,pid,"source-approve","r:"+rid,key,digest(payload))
        if replay is not None:return replay
        if row["current_revision"]!=request.input_revision or row["version"]!=request.expected_research_version or not request.confirm_external:
            raise ResearchError("REVISION_CONFLICT",409,"批准基准已变化，请重新预览并明确确认。")
        revision=conn.execute("SELECT * FROM research_revisions WHERE research_id=? AND revision=?",(rid,request.input_revision)).fetchone()
        if not json.loads(revision["problem_json"])["confirmed"]:raise ResearchError("INPUT_INVALID",422,"请先确认并保存问题结构。")
        fields,pd,fp,inp=draft(revision["digest"],request.query)
        if request.preview_digest!=sha256(canonical({"plan_digest":pd,"input_digest":inp}).encode()):raise ResearchError("REVISION_CONFLICT",409,"预览摘要不一致。")
        aid=str(uuid4())
        values=(aid,pid,row["owner_epoch"],identity.generation,rid,request.input_revision,revision["digest"],request.query,canonical(fields),pd,fp,origin(),now())
        columns='id,principal_id,principal_epoch,auth_generation,research_id,input_revision,problem_digest,query,plan_json,plan_digest,fingerprint,execution_mode,status,created_at'
        placeholders="?,?,?,?,?,?,?,?,?,?,?,?,'active',?"
        if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
            from .source_guard import CONSENT_ORIGIN
            columns+=',consent_origin,consent_digest';placeholders+=',?,?'
            values+= (CONSENT_ORIGIN,request_source.body_digest)
        conn.execute('INSERT INTO research_source_approvals ('+columns+') VALUES('+placeholders+')',values)
        result={"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"approval_ref":aid,"input_revision":request.input_revision,"query":request.query,"plan_digest":pd,"execution_mode":origin()}}
        service._remember(conn,pid,"source-approve","r:"+rid,key,digest(payload),result)
        return result


def start_source(service,identity,rid,request,key,*,request_source=None,request_app=None):
    require_enabled(request_app,store=service.store);rid=service._id(rid);pid=service._principal(identity)
    from .service import digest
    from .projection import ResearchProjection
    from .runner import event_in
    payload=request.model_dump(mode="json")
    with service.authorization.owner_gate(pid) as owner,service.store.transaction(write=True) as conn,_source_scope(conn,service,owner,identity,rid,request,key,request_source,admit=True):
        row=service.authorization.check(conn,identity,pid,rid,scope="write")
        replay=service._replay(conn,pid,"source-start","r:"+rid,key,digest(payload))
        if replay is not None:
            tid=replay["data"]["task"]["id"]
            if not conn.execute("SELECT 1 FROM research_tasks WHERE id=? AND research_id=?",(tid,rid)).fetchone():raise not_found()
            return ResearchProjection.build(conn,row,task_id=tid)
        approval=conn.execute("SELECT * FROM research_source_approvals WHERE id=?",(request.approval_ref,)).fetchone()
        if (not approval or approval["version"]!=1 or approval["status"]!="active" or approval["principal_id"]!=pid
                or approval["principal_epoch"]!=row["owner_epoch"] or approval["auth_generation"]!=identity.generation
                or approval["research_id"]!=rid or approval["input_revision"]!=request.input_revision
                or approval["execution_mode"]!=origin() or row["current_revision"]!=request.input_revision
                or row["version"]!=request.expected_research_version):
            raise ResearchError("REVISION_CONFLICT",409,"批准不可用于当前问题与身份。")
        if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
            from .source_guard import CONSENT_ORIGIN
            if approval['consent_origin']!=CONSENT_ORIGIN or not approval['consent_digest']:
                raise ResearchError('SOURCE_PERMISSION_UNAVAILABLE',409,'旧来源批准仅保留历史，请重新预览并明确确认。')
        fields,pd,fp,inp=draft(approval["problem_digest"],approval["query"])
        revision=conn.execute("SELECT digest FROM research_revisions WHERE research_id=? AND revision=?",(rid,request.input_revision)).fetchone()
        if not revision or revision[0]!=approval["problem_digest"] or pd!=approval["plan_digest"] or canonical(fields)!=approval["plan_json"]:raise ResearchError("REVISION_CONFLICT",409,"批准内容已变化。")
        if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(rid,)).fetchone():raise ResearchError("VERSION_CONFLICT",409,"研究已有未结束流程。")
        chains=source_chains(conn,pid,rid,approval["query"])
        if chains:
            if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
                marks=','.join('?' for _ in chains)
                unproved=conn.execute('SELECT 1 FROM research_source_runs r LEFT JOIN research_source_resources s ON s.task_id=r.task_id WHERE r.chain_id IN ('+marks+') AND s.task_id IS NULL LIMIT 1',tuple(chain['id'] for chain in chains)).fetchone()
                if unproved:raise ResearchError('RECONCILIATION_REQUIRED',409,'旧来源链仅保留历史，尚无当前受保护执行准入。')
            if unclosed_sources(conn,chains):raise ResearchError("RECONCILIATION_REQUIRED",409,"相同来源读取仍未核实执行闭合。")
            if sum(chain["used"] for chain in chains)>=4:raise ResearchError("RESOURCE_LIMIT",429,"同一观测链已用完四次读取。")
            chain_id=chains[0]["id"]
        else:
            chain_id=str(uuid4());conn.execute("INSERT INTO research_source_chains(id,principal_id,research_id,fingerprint) VALUES(?,?,?,?)",(chain_id,pid,rid,fp))
        tid,gid,plan_id,timestamp=str(uuid4()),str(uuid4()),str(uuid4()),now()
        conn.execute("INSERT INTO research_grants (id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,?,'active',?)",(gid,pid,row["owner_epoch"],rid,row["acl_epoch"],'["execute"]',timestamp))
        conn.execute("""INSERT INTO research_tasks
            (id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED','queued',1,?,?,?,?)""",(tid,rid,pid,row["owner_epoch"],row["owner_epoch"],row["acl_epoch"],gid,identity.generation,request.input_revision,inp,row["version"]+1,POLICY,origin(),timestamp,timestamp))
        conn.execute("INSERT INTO research_attempts VALUES(?,1,'initial',?,?)",(tid,POLICY,inp))
        for position,kind in enumerate(("discover_sources","fetch_source","compose_report")):
            conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,?,?,'PENDING')",(str(uuid4()),tid,position,kind))
        conn.execute("INSERT INTO research_source_runs(task_id,approval_id,chain_id,plan_id,fingerprint,origin) VALUES(?,?,?,?,?,?)",(tid,approval["id"],chain_id,plan_id,approval["fingerprint"],origin()))
        if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14):
            from .source_guard import admit_resource
            admit_resource(conn,tid)
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(tid,)).fetchone()
        EvidenceRepository(conn,authorizer(service.store)).put(context_for(conn,tid),plan_for(task,approval,plan_id))
        conn.execute("UPDATE research_source_approvals SET status='consumed',consumed_task_id=? WHERE id=?",(tid,approval["id"]))
        event_in(conn,tid,"created")
        conn.execute("UPDATE research_controls SET version=version+1,updated_at=? WHERE id=?",(timestamp,rid))
        result=ResearchProjection.build(conn,service.authorization.check(conn,identity,pid,rid))
        service._remember(conn,pid,"source-start","r:"+rid,key,digest(payload),result)
        return result
