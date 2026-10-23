"""One bounded source session; interrupted sessions never reconstruct adapters."""
from contextlib import contextmanager
import re
from uuid import uuid4

from .authorization import AuthorizationGate
from .budget import now
from .errors import ResearchError
from .evidence_repository import EvidenceRepository
from .evidence_schemas import Binding,EvidenceExcerpt,EvidenceClaim,EvidenceReport,ExecutionRecord,POLICY as EXECUTOR,canonical,sha256
from .runner import TERMINAL,state_in
from .source_adapters.crossref_plos import CrossrefPlosChain
from .source_policy import PinnedPublicTransport,SourceFailure
from .source_integration import POLICY,authorizer,check_approval,context_for,plan_for,require_enabled,origin,source_chains,unclosed_sources


def _worker_scope(conn,store,task_lease,*,owner_lease=None,close=False):
    from contextlib import nullcontext
    if conn.execute('SELECT version FROM research_schema').fetchone()[0] not in (11,12,13,14,15):return nullcontext()
    from .source_guard import worker_scope
    return worker_scope(conn,store,task_lease,owner_lease=owner_lease,close=close)


class SourceSession:
    def __init__(self,store,task_id,task_lease,transport):
        self.store,self.task_id,self.task_lease,self.transport=store,task_id,task_lease,transport
        self.gate=AuthorizationGate(store)
        self.step_id=None
        self.last_request=None
        with store.transaction() as conn:
            task=self.checked(conn)
            run,approval=check_approval(conn,task)
            self.plan=plan_for(task,approval,run["plan_id"])
            self.mode=run["origin"]
        self.binding={name:getattr(self.plan,name) for name in Binding.__dataclass_fields__}
        if store._formal_mode():
            from .source_supervisor import _bind_session
            _bind_session(self)

    def checked(self,conn):
        if self.store._formal_mode():
            from .source_supervisor import _require_store_worker
            _require_store_worker(self.store,operation='send')
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(self.task_id,)).fetchone()
        self.gate.check_task(conn,task)
        if conn.execute('SELECT version FROM research_schema').fetchone()[0] in (11,12,13,14,15):
            from .source_guard import check_active
            self.task_lease.require(self.store,conn);check_active(self.store,conn,self.task_id)
        if task["execution"] in TERMINAL:raise PermissionError("source session ended")
        check_approval(conn,task)
        return task

    def still_authorized(self):
        try:
            with self.store.transaction() as conn:self.checked(conn)
            return True
        except (ResearchError,PermissionError):return False

    def begin(self,position):
        with self.store.transaction(write=True) as conn:
            self.checked(conn)
            step=conn.execute("SELECT * FROM research_steps WHERE task_id=? AND position=?",(self.task_id,position)).fetchone()
            if not step or step["state"]!="PENDING":raise PermissionError("source step cannot replay")
            conn.execute("UPDATE research_steps SET state='PREPARED',version=version+1 WHERE id=?",(step["id"],))
            state_in(conn,self.task_id,"RUNNING",phase="synthesis" if position==2 else "retrieval",kind="step_started")
            self.step_id=step["id"]

    def finish_step(self):
        with self.store.transaction(write=True) as conn:
            self.checked(conn)
            conn.execute("UPDATE research_steps SET state='SUCCEEDED',version=version+1 WHERE id=? AND state='PREPARED'",(self.step_id,))
            state_in(conn,self.task_id,"RUNNING",kind="step_finished")

    @contextmanager
    def request_gate(self,plan,local_ordinal,target):
        if plan!=self.plan:raise PermissionError("source plan changed")
        with self.store.transaction() as conn:principal=self.checked(conn)["principal_id"]
        with self.gate.owner_gate(principal) as lease:
            with self.store.transaction(write=True) as conn,_worker_scope(conn,self.store,self.task_lease,owner_lease=lease):
                task=self.checked(conn);run,_=check_approval(conn,task)
                step=conn.execute("SELECT * FROM research_steps WHERE id=? AND task_id=?",(self.step_id,self.task_id)).fetchone()
                if not step or step["state"]!="PREPARED":raise PermissionError("source step changed")
                semantic=step["kind"]
                target_digest=sha256(canonical({"host":target.host,"path":target.path}).encode())
                chains=source_chains(conn,task["principal_id"],task["research_id"],plan.query)
                if unclosed_sources(conn,chains):
                    raise PermissionError("source execution closure required")
                used=conn.execute("SELECT used FROM research_source_chains WHERE id=?",(run["chain_id"],)).fetchone()[0]
                if sum(chain["used"] for chain in chains)>=4:raise SourceFailure("source chain quota exhausted")
                chain_ids=tuple(chain["id"] for chain in chains)
                marks=",".join("?" for _ in chain_ids)
                prior=conn.execute(f"""SELECT dispatch_id FROM research_source_requests
                    WHERE chain_id IN ({marks}) AND semantic=? AND target_digest=?
                    AND outcome='UNKNOWN' AND execution_closed=1
                    ORDER BY started_at DESC,ordinal DESC,dispatch_id DESC LIMIT 1""",(*chain_ids,semantic,target_digest)).fetchone()
                request_id,dispatch=str(uuid4()),str(uuid4())
                conn.execute("UPDATE research_source_chains SET used=used+1 WHERE id=? AND used=?",(run["chain_id"],used))
                conn.execute("""INSERT INTO research_source_requests
                    (id,chain_id,task_id,step_id,semantic,target_digest,dispatch_id,ordinal,write_epoch,outcome,owner_gate_identity,task_gate_identity,started_at,prior_dispatch_id)
                    VALUES(?,?,?,?,?,?,?,?,?,'SENDING',?,?,?,?)""",(request_id,run["chain_id"],self.task_id,self.step_id,semantic,target_digest,dispatch,used+1,run["write_epoch"],canonical(lease.identity),canonical(self.task_lease.identity),now(),prior[0] if prior else None))
                self.last_request=request_id
            try:
                yield lease
            except BaseException as exc:
                with self.store.transaction(write=True) as conn,_worker_scope(conn,self.store,self.task_lease,owner_lease=lease):
                    status=exc.http_status if isinstance(exc,SourceFailure) else None
                    conn.execute("UPDATE research_source_requests SET outcome='UNKNOWN',safe_code='outcome_unknown',http_status=?,ended_at=? WHERE id=? AND outcome='SENDING'",(status,now() if status is not None else None,request_id))
                raise
            else:
                with self.store.transaction(write=True) as conn,_worker_scope(conn,self.store,self.task_lease,owner_lease=lease):
                    self.checked(conn)
                    conn.execute("UPDATE research_source_requests SET outcome='SUCCEEDED',ended_at=?,http_status=200 WHERE id=? AND outcome='SENDING'",(now(),request_id))

    def save_snapshot(self,snapshot,raw,extracted,discovery):
        # Exact, short text is taken from this in-memory response only. A
        # restarted process does not open the private cache or re-fetch it.
        match=re.match(r"(?:\S+\s*){1,20}",extracted)
        quote=(match.group(0) if match else extracted[:1]).rstrip()[:1000]
        excerpt=EvidenceExcerpt(**self.binding,id=str(uuid4()),snapshot_id=snapshot.id,extracted_digest=snapshot.extracted_digest,start=0,end=len(quote),quote=quote)
        claim=EvidenceClaim(**self.binding,id=str(uuid4()),text="该来源可供后续方法研究核对，尚未确认支持当前现象的解释。",excerpt_refs=(excerpt.id,),limitations=("未做语义审查或因果验证。","未取得行情序列或进行统计检验。"))
        with self.store.transaction(write=True) as conn:
            self.checked(conn)
            context=context_for(conn,self.task_id,self.step_id)
            repository=EvidenceRepository(conn,authorizer(self.store))
            repository.put(context,snapshot,raw=raw,extracted=extracted,discovery=discovery)
            repository.put(context,excerpt)
            repository.put(context,claim)
            request=conn.execute("SELECT * FROM research_source_requests WHERE id=? AND outcome='SUCCEEDED'",(self.last_request,)).fetchone()
            if not request:raise PermissionError("source observation missing")
            execution=ExecutionRecord(**self.binding,id=str(uuid4()),plan_id=self.plan.id,step_id=self.step_id,step_version=context.step_version,
                dispatch_id=request["dispatch_id"],executor_version=EXECUTOR,started_at=request["started_at"],ended_at=request["ended_at"],
                status="succeeded",origin=self.mode,request_count=1,http_status=request["http_status"],snapshot_refs=(snapshot.id,))
            repository.put(context,execution)
        return snapshot.id,claim.id,execution.id

    def save_observation(self,*,failed=False):
        if not self.last_request or not self.step_id:return
        with self.store.transaction(write=True) as conn:
            self.checked(conn)
            context=context_for(conn,self.task_id,self.step_id)
            request=conn.execute("SELECT * FROM research_source_requests WHERE id=? AND step_id=?",(self.last_request,self.step_id)).fetchone()
            if not request:return
            if conn.execute("SELECT 1 FROM research_evidence_objects WHERE task_id=? AND kind='executions' AND json_extract(payload,'$.dispatch_id')=?",(self.task_id,request["dispatch_id"])).fetchone():return
            unknown=request["outcome"]=="UNKNOWN"
            record=ExecutionRecord(**self.binding,id=str(uuid4()),plan_id=self.plan.id,step_id=self.step_id,step_version=context.step_version,
                dispatch_id=request["dispatch_id"],executor_version=EXECUTOR,started_at=request["started_at"],ended_at=request["ended_at"] or now(),
                status="outcome_unknown" if unknown else "failed" if failed else "succeeded",origin=self.mode,request_count=1,http_status=request["http_status"],
                safe_code="outcome_unknown" if unknown else "invalid_source" if failed else "none")
            EvidenceRepository(conn,authorizer(self.store)).put(context,record)

    def run(self):
        chain=CrossrefPlosChain(self.plan,self.transport,request_gate=self.request_gate,still_authorized=self.still_authorized,origin=self.mode)
        self.begin(0);hits=chain.discover();self.save_observation();self.finish_step()
        self.begin(1)
        snapshots=[];claims=[];executions=[]
        for hit in hits:
            if not hit.cc_by_4:continue
            snapshot,raw,extracted=chain.fetch(hit.doi)
            source,claim,execution=self.save_snapshot(snapshot,raw,extracted,chain.discovery_body)
            snapshots.append(source);claims.append(claim);executions.append(execution)
        self.finish_step()
        self.begin(2)
        with self.store.transaction(write=True) as conn:
            task=self.checked(conn)
            if snapshots:
                report=EvidenceReport(**self.binding,id=str(uuid4()),plan_id=self.plan.id,snapshot_refs=tuple(snapshots),claim_refs=tuple(claims),execution_refs=tuple(executions),
                    outstanding_requirements=("现象与方法的同构关系尚未验证。","没有行情、统计检验或模型分析。","短摘录仅为定位材料，不构成支持结论。"),origin=self.mode)
                EvidenceRepository(conn,authorizer(self.store)).put(context_for(conn,self.task_id,self.step_id),report)
            conn.execute("UPDATE research_steps SET state='SUCCEEDED',version=version+1 WHERE id=?",(self.step_id,))
            state_in(conn,self.task_id,"COMPLETED",evidence="INSUFFICIENT",kind="terminal")
            conn.execute("UPDATE research_controls SET version=version+1,updated_at=? WHERE id=?",(now(),task["research_id"]))
        return "COMPLETED"


def close_interrupted(store,task_id,task_lease):
    """Fresh exclusive same-inode owner lock plus held task lock is proof.

    The reviewed sender shares the owner's open-file-description lock until
    kernel deadline exit. Therefore this acquisition excludes sender/queued
    SCM_RIGHTS capabilities; the task mutex excludes the previous parent.
    No elapsed-time or PID observation grants closure.
    """
    gate=AuthorizationGate(store)
    with store.transaction() as conn:
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
        principal=task["principal_id"]
        version=conn.execute('SELECT version FROM research_schema').fetchone()[0]
        if version in (11,12,13,14,15):
            from .source_guard import resource
            owner_gate=resource(conn,task_id)['owner_gate_id']
    owner=gate.owner_gate_id(owner_gate) if version in (11,12,13,14,15) else gate.owner_gate(principal)
    with owner as fresh_owner:
        with store.transaction(write=True) as conn,_worker_scope(conn,store,task_lease,owner_lease=fresh_owner,close=True):
            if store._formal_mode():
                from .source_supervisor import _require_store_worker
                _require_store_worker(store,operation='cleanup')
            task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
            run=conn.execute("SELECT * FROM research_source_runs WHERE task_id=?",(task_id,)).fetchone()
            if not run:return
            if run["task_gate_identity"]!=canonical(task_lease.identity):raise PermissionError("task gate identity changed")
            requests=conn.execute("SELECT * FROM research_source_requests WHERE task_id=? AND outcome IN ('SENDING','UNKNOWN') AND execution_closed=0",(task_id,)).fetchall()
            if task["execution"] in TERMINAL and not requests:return
            for request in requests:
                if request["owner_gate_identity"]!=canonical(fresh_owner.identity) or request["task_gate_identity"]!=canonical(task_lease.identity):
                    raise PermissionError("source gate identity changed")
            retired=run["write_epoch"]
            conn.execute("UPDATE research_source_runs SET write_epoch=write_epoch+1 WHERE task_id=? AND write_epoch=?",(task_id,retired))
            if version in (11,12,13,14,15):
                conn.execute("UPDATE research_source_resources SET state='closed',write_epoch=write_epoch+1 WHERE task_id=?",(task_id,))
            conn.execute("UPDATE research_steps SET state='DISCARDED',version=version+1 WHERE task_id=? AND state!='SUCCEEDED'",(task_id,))
            for request in requests:
                proof=canonical({"policy":POLICY,"executor":EXECUTOR,"task_gate":task_lease.identity,"owner_gate":fresh_owner.identity,"retired_write_epoch":request["write_epoch"],"proof_version":1})
                conn.execute("UPDATE research_source_requests SET outcome='UNKNOWN',safe_code='outcome_unknown',execution_closed=1,closure_ref=?,closure_proof=? WHERE id=? AND execution_closed=0",(str(uuid4()),proof,request["id"]))
            conn.execute("UPDATE research_tasks SET stop_requested=1,reconcile_requested=0 WHERE id=?",(task_id,))
            if task["execution"] not in TERMINAL:state_in(conn,task_id,"FAILED",evidence="INSUFFICIENT",kind="terminal",safe_code="source_incomplete")


def run_source_once(store,task_id,task_lease,transport=None):
    require_enabled(store=store)
    with store.transaction(write=True) as conn:
        run=conn.execute("SELECT * FROM research_source_runs WHERE task_id=?",(task_id,)).fetchone()
        task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
        if not run:raise PermissionError("source run missing")
        interrupted=bool(run["started"])
        if not interrupted:
            if task["execution"] in TERMINAL:return task["execution"]
            version=conn.execute('SELECT version FROM research_schema').fetchone()[0]
            if version in (11,12,13,14,15):
                with _worker_scope(conn,store,task_lease):
                    if run['task_gate_identity']!=canonical(task_lease.identity):raise PermissionError('Source native task binding changed')
                    if conn.execute('UPDATE research_source_runs SET started=1 WHERE task_id=? AND started=0',(task_id,)).rowcount!=1:raise PermissionError('Source claim CAS failed')
                    conn.execute("UPDATE research_source_resources SET state='running' WHERE task_id=? AND state='admitted'",(task_id,))
            else:
                conn.execute("UPDATE research_source_runs SET started=1,task_gate_identity=? WHERE task_id=? AND started=0",(canonical(task_lease.identity),task_id))
    if interrupted:
        close_interrupted(store,task_id,task_lease)
        with store.transaction() as conn:return conn.execute("SELECT execution FROM research_tasks WHERE id=?",(task_id,)).fetchone()[0]
    session=None
    try:
        if transport is None:
            if origin()!="live":raise SourceFailure("explicit local fixture required")
            transport=PinnedPublicTransport()
        if store._formal_mode():
            from .source_supervisor import _require_store_worker
            _require_store_worker(store,operation='send')
            if (type(transport) is not PinnedPublicTransport or transport._worker is not PinnedPublicTransport()._worker
                    or run['origin']!='live'):
                raise SourceFailure('formal Source requires the fixed live transport')
        if type(transport) is not PinnedPublicTransport or transport.execution_mode!=run["origin"]:
            raise SourceFailure("source transport provenance mismatch")
        session=SourceSession(store,task_id,task_lease,transport)
        return session.run()
    except (ValueError,ResearchError,PermissionError,OSError) as error:
        from .source_spawn import SourceCleanupUncertain
        if isinstance(error,SourceCleanupUncertain) or getattr(error,'_source_cleanup_uncertainty',None):raise
        if session is not None:
            try:session.save_observation(failed=True)
            except (ValueError,ResearchError,PermissionError):pass
        close_interrupted(store,task_id,task_lease)
        with store.transaction() as conn:return conn.execute("SELECT execution FROM research_tasks WHERE id=?",(task_id,)).fetchone()[0]
