"""One saved-problem view; no invented execution or evidence status."""
import json

from .schemas import CONTRACT_REVISION, SCHEMA_VERSION
from .schemas import MAX_MONEY
from .budget import BudgetLedger, enabled, money, money_text
from .errors import not_found


class ResearchProjection:
    @staticmethod
    def build(conn, row, task_id=None,*,method_result=None,method_authorized=False):
        revisions = []
        for item in conn.execute("SELECT * FROM research_revisions WHERE research_id=? ORDER BY revision", (row["id"],)):
            revisions.append({"research_id": row["id"], "revision": item["revision"],
                              **json.loads(item["problem_json"]), "digest": item["digest"],
                              "created_at": item["created_at"]})
        if task_id is None:
            task=conn.execute("SELECT * FROM research_tasks WHERE research_id=? AND input_revision=? ORDER BY start_version DESC LIMIT 1",(row["id"],row["current_revision"])).fetchone()
        else:
            task=conn.execute("SELECT * FROM research_tasks WHERE id=? AND research_id=?",(task_id,row["id"])).fetchone()
            if not task:raise not_found()
        view={
            "research": {**dict(row), "current_task_id":task["id"] if task else None},
            "research_version": row["version"], "task_version":task["version"] if task else None,
            "revisions": revisions, "current_problem": next((r for r in revisions if task and r["revision"]==task["input_revision"]),revisions[-1]),
            "execution": None, "evidence": "UNASSESSED", "status": "saved",
            "task":None,"is_historical":bool(task and task["input_revision"]!=row["current_revision"]),
            "execution_mode":"offline_probe", "report_status":"none", "detail":"normal",
            "allowed_next_actions": ["view", "revise"],
            "capabilities": {"execution":enabled(),"anonymous_claim":False,"account_erasure_integration":True},
        }
        active=conn.execute("SELECT id FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING') ORDER BY start_version DESC LIMIT 1",(row["id"],)).fetchone()
        from .source_integration import enabled as source_enabled
        view["capabilities"]["source_evidence"]=source_enabled()
        view["other_active_task_id"]=active["id"] if active and (not task or active["id"]!=task["id"]) else None
        unresolved_current=conn.execute("SELECT 1 FROM research_reservations r JOIN research_tasks t ON t.id=r.task_id WHERE t.research_id=? AND t.input_revision=? AND r.status IN ('SENT','UNKNOWN')",(row["id"],row["current_revision"])).fetchone()
        if enabled() and view["current_problem"]["confirmed"] and not active and not unresolved_current:
            view["allowed_next_actions"].append("start")
        if task:
            if task['policy_revision']=='bounded_usage_upper_v2':
                event=conn.execute('SELECT seq FROM research_task_events WHERE task_id=? ORDER BY seq DESC LIMIT 1',(task['id'],)).fetchone()
                execution=task['execution'];terminal=execution in ('COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED')
                view.update(execution=execution,evidence=task['evidence'],status={'COMPLETED':'insufficient','FAILED':'failed','CANCELLED':'cancelled','ACCESS_REVOKED':'cancelled','QUEUED':'queued'}.get(execution,'synthesising'),
                    report_status='qualified_report' if method_result else 'none',task=dict(id=task['id'],version=task['version'],execution=execution,
                        phase=task['phase'],attempt=1,input_revision=task['input_revision'],stop_requested=bool(task['stop_requested']),policy_revision=task['policy_revision']),
                    task_event_cursor=event[0] if event else 0,allowed_next_actions=['view','refresh']+([] if terminal else ['cancel','request_reconciliation']))
                if method_authorized:view['method_result']=method_result
                return {'schema_version':SCHEMA_VERSION,'contract_revision':CONTRACT_REVISION,'data':view}
            if task["policy_revision"]=="d1-source-only-v1":
                from .source_integration import project_task
                project_task(conn,view,task)
                return {"schema_version":SCHEMA_VERSION,"contract_revision":CONTRACT_REVISION,"data":view}
            rows=conn.execute("SELECT r.*,a.status AS account_status FROM research_reservations r JOIN research_funding_accounts a ON a.id=r.account_id WHERE r.task_id=?",(task["id"],)).fetchall()
            known=sum(r["settled_cost"] or 0 for r in rows if r["status"]=="SETTLED")
            held=sum(r["max_cost"] for r in rows if r["status"] in ("HELD","SENT","UNKNOWN"))
            unresolved=sum(1 for r in rows if r["status"] in ("SENT","UNKNOWN"))
            anomaly=any(r["account_status"]=="blocked" for r in rows) or max(known,held)>MAX_MONEY
            budget={"known_cost":[money(known)] if known<=MAX_MONEY else [],"held_cost":[money(held)] if held<=MAX_MONEY else [],
                    "unknown_count":unresolved,"status":"reconciling" if unresolved or anomaly else "available",
                    "known_text":money_text(known),"held_text":money_text(held),"anomaly":anomaly}
            execution=task["execution"]
            status={"QUEUED":"queued","RUNNING":"retrieving" if task["phase"]=="retrieval" else "synthesising",
                    "WAITING_EXTERNAL":"retrieving" if task["phase"]=="retrieval" else "synthesising",
                    "RECONCILING":"retrieving" if task["phase"]=="retrieval" else "synthesising",
                    "COMPLETED":"insufficient","FAILED":"failed","CANCELLED":"cancelled","ACCESS_REVOKED":"cancelled"}[execution]
            last=conn.execute("SELECT safe_code,seq FROM research_task_events WHERE task_id=? ORDER BY seq DESC LIMIT 1",(task["id"],)).fetchone()
            detail="reconciliation_required" if execution=="RECONCILING" or (execution in ("FAILED","CANCELLED") and unresolved) else "waiting_external" if execution=="WAITING_EXTERNAL" else "partial_results" if execution=="COMPLETED" else "normal"
            if last and last["safe_code"] in ("BUDGET_EXHAUSTED","BUDGET_UNVERIFIED"):
                detail=last["safe_code"].lower()
                budget["status"]="exhausted" if detail=="budget_exhausted" else "unverified"
            actions=["view","refresh"]
            if execution not in ("COMPLETED","FAILED","CANCELLED","ACCESS_REVOKED"):actions.append("cancel")
            if unresolved or execution=="RECONCILING":actions.append("request_reconciliation")
            if execution=="WAITING_EXTERNAL" and not unresolved and not task["stop_requested"] and enabled() and BudgetLedger.ready_in(conn,task["id"]):actions.append("resume")
            view.update({"execution":execution,"status":status,"detail":detail,"evidence":task["evidence"],"report_status":"notes",
                         "task":{"id":task["id"],"version":task["version"],"execution":execution,"phase":task["phase"],"attempt":1,
                                 "input_revision":task["input_revision"],"stop_requested":bool(task["stop_requested"]),"policy_revision":task["policy_revision"]},
                         "budget":budget,"task_event_cursor":last["seq"] if last else 0,"allowed_next_actions":actions,
                         "notes":[r["note"] for r in conn.execute("SELECT note FROM research_step_outputs WHERE task_id=? ORDER BY created_at,step_id",(task["id"],))]})
        return {"schema_version":SCHEMA_VERSION,"contract_revision":CONTRACT_REVISION,"data":view}
