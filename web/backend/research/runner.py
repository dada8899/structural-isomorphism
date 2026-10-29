"""One fixed, bounded offline plan. No plugin or general scheduler."""
from __future__ import annotations

import json
import http.client
from uuid import uuid4

from .authorization import AuthorizationGate
from .budget import BudgetLedger, POLICY, now, require_enabled
from .errors import ResearchError, not_found
from .transport import FixtureTransport


TERMINAL={"COMPLETED","FAILED","CANCELLED","ACCESS_REVOKED"}


def event_in(conn,task_id,kind,safe_code=None):
    task=conn.execute("SELECT version FROM research_tasks WHERE id=?",(task_id,)).fetchone()
    seq=conn.execute("SELECT COALESCE(MAX(seq),0)+1 FROM research_task_events WHERE task_id=?",(task_id,)).fetchone()[0]
    conn.execute("INSERT INTO research_task_events VALUES(?,?,?,?,?,?)",(task_id,seq,task["version"],kind,safe_code,now()))


def state_in(conn,task_id,execution,*,phase=None,evidence=None,kind="waiting",safe_code=None):
    changed=conn.execute("""UPDATE research_tasks SET execution=?,phase=COALESCE(?,phase),
        evidence=COALESCE(?,evidence),version=version+1,updated_at=? WHERE id=? AND version<2147483647""",
        (execution,phase,evidence,now(),task_id)).rowcount
    if changed!=1:raise ResearchError("VERSION_CONFLICT",409,"任务版本已达上限。")
    event_in(conn,task_id,kind,safe_code)


def access_ended_in(conn,task):
    if task['policy_revision']=='bounded_usage_upper_v2':raise ResearchError('FEATURE_UNAVAILABLE',503,'自动撤权停止尚无受控来源。')
    if not task["stop_requested"] and task["execution"] not in TERMINAL:
        conn.execute("UPDATE research_tasks SET stop_requested=1 WHERE id=?",(task["id"],))
        BudgetLedger.release_prepared_in(conn,task["id"])
        state_in(conn,task["id"],"ACCESS_REVOKED",kind="authorization_changed")


class ResearchRunner:
    def __init__(self,store,*,source_transport=None):
        self.store=store
        self.gate=AuthorizationGate(store)
        self.ledger=BudgetLedger(store)
        self.source_transport=source_transport

    def task(self,task_id):
        with self.store.transaction() as conn:
            row=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
            if not row:raise not_found()
            return dict(row)

    def prepare(self,task_id):
        task=self.task(task_id)
        with self.gate.owner_gate(task["principal_id"]),self.store.transaction(write=True) as conn:
            task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
            self.gate.check_task(conn,task)
            if task["execution"] in TERMINAL:return None
            step=conn.execute("SELECT * FROM research_steps WHERE task_id=? AND state!='SUCCEEDED' ORDER BY position LIMIT 1",(task_id,)).fetchone()
            if not step:return None
            if step["state"] not in ("PENDING","PREPARED"):return dict(step)
            BudgetLedger.reserve_in(conn,task,step)
            state_in(conn,task_id,"RUNNING",phase="retrieval" if step["position"]==0 else "synthesis",kind="step_started")
            return dict(conn.execute("SELECT * FROM research_steps WHERE id=?",(step["id"],)).fetchone())

    def send(self,task_id,step_id):
        task=self.task(task_id)
        with self.gate.owner_gate(task["principal_id"]):
            with self.store.transaction(write=True) as conn:
                task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
                self.gate.check_task(conn,task)
                step=conn.execute("SELECT * FROM research_steps WHERE id=? AND task_id=?",(step_id,task_id)).fetchone()
                if not step or step["state"]!="PREPARED":raise ResearchError("PERMIT_INVALID",409,"步骤当前不能外发。")
                permit,account=BudgetLedger.dispatch_in(conn,step)
                if permit["input_digest"]!=task["input_digest"]:
                    raise ResearchError("PERMIT_INVALID",409,"调用输入已变化。")
                event_in(conn,task_id,"step_started","local_send_prepared")
            # Real request bytes start here, after commit and before gate exit.
            connection=FixtureTransport(account["fixture_port"]).begin(step["kind"],permit["dispatch_id"],permit["input_digest"])
            try:
                with self.store.transaction(write=True) as conn:
                    conn.execute("UPDATE research_steps SET state='AWAITING_RECEIPT',version=version+1 WHERE id=? AND state='SENDING'",(step_id,))
                    state_in(conn,task_id,"WAITING_EXTERNAL",kind="waiting")
            except Exception:
                connection.close()
                raise
            return connection

    def unknown(self,task_id,step_id):
        with self.store.transaction(write=True) as conn:
            BudgetLedger.unknown_in(conn,step_id)
            task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
            if task and not task["stop_requested"] and task["execution"] not in TERMINAL:
                state_in(conn,task_id,"RECONCILING",kind="reconciling",safe_code="outcome_unknown")

    def commit_result(self,task_id,step_id,result):
        with self.store.transaction(write=True) as conn:
            task=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
            step=conn.execute("SELECT * FROM research_steps WHERE id=? AND task_id=?",(step_id,task_id)).fetchone()
            if not task or not step:return False
            try:self.gate.check_task(conn,task)
            except ResearchError:
                access_ended_in(conn,task)
                conn.execute("UPDATE research_steps SET state='DISCARDED',version=version+1 WHERE id=?",(step_id,))
                return False
            if task["execution"] in TERMINAL or step["state"]=="SUCCEEDED":return False
            reservation=conn.execute("SELECT status FROM research_reservations WHERE step_id=?",(step_id,)).fetchone()
            permit=conn.execute("SELECT dispatch_id FROM research_dispatch_permits WHERE step_id=?",(step_id,)).fetchone()
            if not reservation or reservation["status"]!="SETTLED" or not permit or permit["dispatch_id"]!=result.dispatch_id:
                raise ResearchError("PERMIT_INVALID",409,"步骤结果尚未核实费用。")
            if result.note is None:
                conn.execute("UPDATE research_steps SET state='FAILED',version=version+1 WHERE id=?",(step_id,))
                state_in(conn,task_id,"FAILED",kind="terminal",safe_code="body_unavailable")
                return False
            conn.execute("INSERT OR IGNORE INTO research_step_outputs VALUES(?,?,?,'offline_probe',?)",(step_id,task_id,result.note,now()))
            conn.execute("UPDATE research_steps SET state='SUCCEEDED',version=version+1 WHERE id=?",(step_id,))
            remaining=conn.execute("SELECT count(*) FROM research_steps WHERE task_id=? AND state!='SUCCEEDED'",(task_id,)).fetchone()[0]
            state_in(conn,task_id,"COMPLETED" if remaining==0 else "RUNNING",evidence="INSUFFICIENT" if remaining==0 else "COLLECTING",kind="terminal" if remaining==0 else "step_finished")
            conn.execute("UPDATE research_controls SET version=version+1,updated_at=? WHERE id=? AND version<2147483647",(now(),task["research_id"]))
            return True

    def reconcile(self,task_id):
        # Fee receipts may be processed after cancellation/deletion. They never
        # grant permission to recreate research contents.
        task=self.task(task_id)
        if task['policy_revision']=='bounded_usage_upper_v2':
            from .paid_budget import reconcile_task_in
            with self.gate.owner_gate(task['principal_id']) as lease,self.store.transaction(write=True) as conn:
                reconcile_task_in(conn,store=self.store,lease=lease,task_id=task_id)
                conn.execute('UPDATE research_tasks SET reconcile_requested=0 WHERE id=?',(task_id,))
            return
        with self.store.transaction() as conn:
            rows=conn.execute("""SELECT s.id,p.dispatch_id,a.fixture_port FROM research_steps s
                JOIN research_reservations r ON r.step_id=s.id JOIN research_dispatch_permits p ON p.step_id=s.id
                JOIN research_funding_accounts a ON a.id=r.account_id
                WHERE s.task_id=? AND r.status IN ('SENT','UNKNOWN','SETTLED')
                AND s.state IN ('SENDING','AWAITING_RECEIPT','UNKNOWN')""",(task_id,)).fetchall()
        for row in rows:
            try:result=FixtureTransport(row["fixture_port"]).receipt(row["dispatch_id"])
            except Exception:continue
            if result is not None and self.ledger.settle(row["id"],result.model_dump(mode="json")):
                self.commit_result(task_id,row["id"],result)
        with self.store.transaction(write=True) as conn:
            conn.execute("UPDATE research_tasks SET reconcile_requested=0 WHERE id=?",(task_id,))

    def run_next(self,task_id):
        return self.run_once(task_id,max_steps=1)

    def run_once(self,task_id=None,*,max_steps=2):
        if task_id is None:
            from .plan_runtime import next_plan_task
            task_id=next_plan_task(self.store)
            if task_id is None:
                with self.store.transaction() as conn:
                    native=conn.execute("SELECT r.task_id FROM research_plan_native_runs r JOIN research_tasks t ON t.id=r.task_id WHERE r.state='approved' AND t.execution='QUEUED' ORDER BY t.created_at,t.id LIMIT 1").fetchone() if conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_plan_native_runs'").fetchone() else None
                    task_id=native[0] if native else None
        if task_id is not None and self.task(task_id)['policy_revision']=='native-plan-v1':
            from .plan_native_runtime import run_once
            return run_once(self.store,task_id)
        if task_id is not None and self.task(task_id)['policy_revision']=='funded-plan-v1':
            from .plan_runtime import run_once
            return run_once(self.store,task_id)

        from .source_integration import enabled as sources_enabled
        from .budget import enabled as c0_enabled
        source_available=sources_enabled()
        if not source_available:require_enabled()
        supported=([POLICY] if c0_enabled() else [])+(['d1-source-only-v1'] if source_available else [])
        if type(max_steps) is not int or max_steps not in (1,2):raise ValueError("fixed plan only")
        if task_id is None:
            with self.store.transaction() as conn:
                marks=','.join('?' for _ in supported)
                row=conn.execute("""SELECT t.id FROM research_tasks t WHERE t.policy_revision IN ("""+marks+""") AND (t.execution IN ('QUEUED','RUNNING')
                    OR t.reconcile_requested=1 OR (t.execution='WAITING_EXTERNAL' AND EXISTS(
                    SELECT 1 FROM research_steps s WHERE s.task_id=t.id AND s.state IN ('SENDING','AWAITING_RECEIPT'))))
                    ORDER BY t.created_at,t.id LIMIT 1""",supported).fetchone()
                if not row:return "idle"
                task_id=row["id"]
        from uuid import UUID
        if str(UUID(task_id,version=4))!=task_id:raise not_found()
        if self.task(task_id)['policy_revision'] not in supported:
            raise ResearchError('FEATURE_UNAVAILABLE',503,'此worker尚不支持该任务策略。')
        # Task lock may span response wait. Cancellation/deletion only take
        # owner lock, so they never wait for this task lock or network finish.
        with self.store.transaction() as conn:
            version=conn.execute('SELECT version FROM research_schema').fetchone()[0]
            if version in (11,12,13,14,15):
                # A cancelled, never-born sender needs no new sending lease.
                # Existing gates/started runs/any request still take the real
                # task+owner closure path below, including terminal tasks.
                terminal=conn.execute("""SELECT t.execution FROM research_tasks t
                    JOIN research_source_runs r ON r.task_id=t.id
                    JOIN research_source_resources s ON s.task_id=t.id
                    WHERE t.id=? AND t.policy_revision='d1-source-only-v1'
                    AND t.execution IN ('COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED')
                    AND r.started=0 AND r.task_gate_identity IS NULL
                    AND s.state='closed' AND s.task_gate_identity IS NULL
                    AND NOT EXISTS(SELECT 1 FROM research_source_requests q WHERE q.task_id=t.id)""",(task_id,)).fetchone()
                if terminal:return terminal['execution']
        lock=self.gate.source_task_gate(task_id) if version in (11,12,13,14,15) and self.task(task_id)['policy_revision']=='d1-source-only-v1' else self.gate.owner_gate_id(task_id)
        with lock as task_lease:
            task=self.task(task_id)
            if task['policy_revision'] not in supported:
                raise ResearchError('FEATURE_UNAVAILABLE',503,'此worker尚不支持该任务策略。')
            if task["policy_revision"]=="d1-source-only-v1":
                from .source_workflow import run_source_once
                return run_source_once(self.store,task_id,task_lease,self.source_transport)
            require_enabled()
            with self.store.transaction(write=True) as conn:
                rows=conn.execute("SELECT id FROM research_steps WHERE task_id=? AND state IN ('SENDING','AWAITING_RECEIPT')",(task_id,)).fetchall()
                for row in rows:BudgetLedger.unknown_in(conn,row["id"])
                if rows and not task["stop_requested"] and task["execution"] not in TERMINAL:
                    state_in(conn,task_id,"RECONCILING",kind="reconciling",safe_code="restart_unknown")
            if task["reconcile_requested"]:self.reconcile(task_id)
            for _ in range(max_steps):
                task=self.task(task_id)
                if task["stop_requested"] or task["execution"] in TERMINAL:return task["execution"]
                if task["execution"]=="RECONCILING":return "RECONCILING"
                try:step=self.prepare(task_id)
                except ResearchError as exc:
                    with self.store.transaction(write=True) as conn:
                        current=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
                        if current and not current["stop_requested"]:
                            if exc.code=="NOT_FOUND":access_ended_in(conn,current)
                            else:state_in(conn,task_id,"WAITING_EXTERNAL",kind="waiting",safe_code=exc.code)
                    return self.task(task_id)["execution"]
                if not step:return self.task(task_id)["execution"]
                if step["state"] not in ("PENDING","PREPARED"):
                    self.unknown(task_id,step["id"])
                    return self.task(task_id)["execution"]
                try:
                    connection=self.send(task_id,step["id"])
                    result=FixtureTransport.finish(connection)
                    known=self.ledger.settle(step["id"],result.model_dump(mode="json"))
                    if not known:
                        self.unknown(task_id,step["id"])
                        return self.task(task_id)["execution"]
                    self.commit_result(task_id,step["id"],result)
                except ResearchError as exc:
                    with self.store.transaction(write=True) as conn:
                        current=conn.execute("SELECT * FROM research_tasks WHERE id=?",(task_id,)).fetchone()
                        local=conn.execute("SELECT state FROM research_steps WHERE id=?",(step["id"],)).fetchone()
                        if current and exc.code=="NOT_FOUND":
                            access_ended_in(conn,current)
                            return "ACCESS_REVOKED" if not current["stop_requested"] else current["execution"]
                        if current and not current["stop_requested"] and local["state"]=="PREPARED":
                            state_in(conn,task_id,"WAITING_EXTERNAL",kind="waiting",safe_code=exc.code)
                            return "WAITING_EXTERNAL"
                    self.unknown(task_id,step["id"])
                    return self.task(task_id)["execution"]
                except (OSError,ValueError,http.client.HTTPException):
                    self.unknown(task_id,step["id"])
                    return self.task(task_id)["execution"]
            return self.task(task_id)["execution"]
