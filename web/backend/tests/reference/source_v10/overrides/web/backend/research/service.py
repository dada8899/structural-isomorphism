"""Transactional create/revise/read with incarnation-scoped idempotency."""
from __future__ import annotations

import hashlib
import json
import base64
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .authorization import AuthorizationGate
from .errors import ResearchError, not_found
from .projection import ResearchProjection,require_revision_budget,projection_bytes,RESEARCH_RESPONSE_LIMIT


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ResearchService:
    def __init__(self, store):
        self.store = store
        self.authorization = AuthorizationGate(store)

    def _principal(self, identity, *, create=False):
        if create and self.store._formal_mode():
            # Existing owner mapping and actual preprovisioned lock come before
            # the first principal write. This lease ends before create's later
            # independent owner transaction; it is never nested or transferred.
            with self.store.transaction() as conn:
                self.authorization.check_account(conn,identity)
                gate_id=self.store.auth_store.owner_gate_in(conn,identity.email)
            with self.authorization.owner_gate_id(gate_id) as lease,self.store.transaction(write=True) as conn:
                self.authorization.check_account(conn,identity)
                if self.store.auth_store.owner_gate_in(conn,identity.email)!=gate_id:
                    raise ResearchError('AUTHORIZATION_STALE',409,'账户锁绑定已变化，请重新读取。')
                lease.identity
                row=conn.execute('SELECT * FROM research_principals WHERE normalized_email=? AND session_generation=?',
                    (identity.email,identity.generation)).fetchone()
                if row is not None:
                    if row['status']!='active' or row['gate_id']!=gate_id:raise not_found()
                    return row['id']
                pid=str(uuid4())
                conn.execute('INSERT INTO research_principals VALUES(?,?,?,?,?,?,?,?)',
                    (pid,'account',identity.email,identity.generation,1,'active',now(),gate_id))
                return pid
        with self.store.transaction(write=create) as conn:
            self.authorization.check_account(conn, identity)
            row = conn.execute("SELECT * FROM research_principals WHERE normalized_email=? AND session_generation=?",
                               (identity.email, identity.generation)).fetchone()
            if row is None and create:
                pid = str(uuid4())
                gate_id = self.store.auth_store.owner_gate_in(conn, identity.email, pid)
                conn.execute("INSERT INTO research_principals VALUES(?,?,?,?,?,?,?,?)",
                             (pid, "account", identity.email, identity.generation, 1, "active", now(), gate_id))
                return pid
            if row is None or row["status"] != "active":
                raise not_found()
            return row["id"]

    @staticmethod
    def _id(value):
        try:
            parsed = UUID(value)
            if parsed.version != 4 or str(parsed) != value:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise not_found() from None
        return value

    @staticmethod
    def _replay(conn, principal, operation, scope, key, request_digest):
        row = conn.execute("""SELECT * FROM research_idempotency
            WHERE principal_id=? AND operation=? AND scope_key=? AND key_digest=?""",
            (principal, operation, scope, hashlib.sha256(key.encode()).hexdigest())).fetchone()
        if row is None:
            return None
        if row["request_digest"] != request_digest:
            raise ResearchError("IDEMPOTENCY_CONFLICT", 409, "同一操作标识对应了不同内容，请核对已保存结果。")
        result=json.loads(row['result_json'])
        # Older full response snapshots never confer current method-body access.
        if type(result) is dict and type(result.get('data')) is dict:
            data=result['data']
            if 'method_result' in data:
                data.pop('method_result')
                if data.get('report_status')=='qualified_report':data['report_status']='none'
        return result

    @staticmethod
    def _remember(conn, principal, operation, scope, key, request_digest, result):
        if type(result) is dict and type(result.get('data')) is dict and result['data'].get('method_result') is not None:
            raise PermissionError('method content cannot be copied into response cache')
        conn.execute("INSERT INTO research_idempotency VALUES(?,?,?,?,?,?)",
                     (principal, operation, scope, hashlib.sha256(key.encode()).hexdigest(), request_digest, canonical(result)))

    def create(self, identity, request, key):
        principal = self._principal(identity, create=True)
        payload = request.model_dump(mode="json")
        if payload["problem"].get("formula_draft") is None:payload["problem"].pop("formula_draft",None)
        request_digest = digest(payload)
        with self.authorization.owner_gate(principal) as lease, self.store.transaction(write=True) as conn:
            owner = self.authorization.check(conn, identity, principal)
            replay = self._replay(conn, principal, "create", "new", key, request_digest)
            if replay is not None:
                # A replay must not return stale private data after revocation.
                self.authorization.check(conn, identity, principal, replay["data"]["research"]["id"])
                return replay
            rid, timestamp = str(uuid4()), now()
            problem={k:v for k,v in payload['problem'].items() if k!='formula_draft'}
            require_revision_budget([{'research_id':rid,'revision':1,**problem,'digest':digest(problem),'created_at':timestamp}])
            conn.execute("INSERT INTO research_controls VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (rid, principal, owner["epoch"], 1, 1, 1, "private", "active", timestamp, timestamp))
            conn.execute("INSERT INTO research_grants (id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                         (str(uuid4()), principal, owner["epoch"], rid, 1, '["read","write"]', "active", timestamp))
            conn.execute("INSERT INTO research_revisions VALUES(?,?,?,?,?)", (rid, 1, canonical(problem), digest(problem), timestamp))
            from .formula_result import save_snapshot
            save_snapshot(conn,store=self.store,lease=lease,identity=identity,principal=principal,rid=rid,revision=1,draft=request.problem.formula_draft)
            row = self.authorization.check(conn, identity, principal, rid, scope="write")
            result = ResearchProjection.build(conn, row)
            if projection_bytes(result)>RESEARCH_RESPONSE_LIMIT:raise ResearchError('PAYLOAD_LIMIT',413,'完整研究视图超过保存范围；旧记录未更改。')
            self._remember(conn, principal, "create", "new", key, request_digest, result)
            return result

    def revise(self, identity, research_id, request, key):
        rid = self._id(research_id)
        principal = self._principal(identity)
        payload = request.model_dump(mode="json")
        if payload["problem"].get("formula_draft") is None:payload["problem"].pop("formula_draft",None)
        request_digest = digest(payload)
        with self.authorization.owner_gate(principal) as lease, self.store.transaction(write=True) as conn:
            row = self.authorization.check(conn, identity, principal, rid, scope="write")
            replay = self._replay(conn, principal, "revise", "r:" + rid, key, request_digest)
            if replay is not None:
                return replay
            revision = row["current_revision"]
            if revision != payload["expected_revision"]:
                raise ResearchError("REVISION_CONFLICT", 409, "研究已有新修订，请先重新读取，当前输入仍保留在页面。")
            if revision == 2147483647 or row["version"] == 2147483647:
                raise ResearchError("VERSION_CONFLICT", 409, "研究版本已达上限，当前操作无法保存。")
            timestamp, problem = now(), {k:v for k,v in payload["problem"].items() if k!="formula_draft"}
            require_revision_budget([*ResearchProjection.revision_records(conn,rid),
                {'research_id':rid,'revision':revision+1,**problem,'digest':digest(problem),'created_at':timestamp}])
            conn.execute("INSERT INTO research_revisions VALUES(?,?,?,?,?)",
                         (rid, revision + 1, canonical(problem), digest(problem), timestamp))
            changed = conn.execute("""UPDATE research_controls SET current_revision=?,version=version+1,updated_at=?
                WHERE id=? AND version=? AND current_revision=? AND lifecycle='active'""",
                (revision + 1, timestamp, rid, row["version"], revision)).rowcount
            if changed != 1:
                raise ResearchError("REVISION_CONFLICT", 409, "研究已有新修订，请重新读取。")
            from .formula_result import save_snapshot
            save_snapshot(conn,store=self.store,lease=lease,identity=identity,principal=principal,rid=rid,revision=revision+1,draft=request.problem.formula_draft)
            result = ResearchProjection.build(conn, self.authorization.check(conn, identity, principal, rid))
            if projection_bytes(result)>RESEARCH_RESPONSE_LIMIT:raise ResearchError('PAYLOAD_LIMIT',413,'完整研究视图超过保存范围；旧记录未更改。')
            self._remember(conn, principal, "revise", "r:" + rid, key, request_digest, result)
            return result

    def view(self, identity, research_id, task_id=None,*,request_source=None):
        rid, principal = self._id(research_id), self._principal(identity)
        with self.authorization.owner_gate(principal) as lease,self.store.transaction() as conn:
            row = self.authorization.check(conn, identity, principal, rid)
            return self._method_projection(conn,row,identity,lease,request_source,task_id)

    def _method_projection(self,conn,row,identity,lease,request_source,task_id):
        result=None;authorized=False;state=None;history=None;next_task_id=None
        if request_source is not None and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (9,10):
            from .paid_control import require_authenticated_action
            require_authenticated_action(request_source,identity=identity,action=request_source.action,research_id=row['id'],task_id=task_id)
            task=conn.execute('SELECT * FROM research_tasks WHERE research_id=? '+('AND id=?' if task_id else 'AND input_revision=? ORDER BY start_version DESC,id DESC LIMIT 1'),
                (row['id'],task_id if task_id else row['current_revision'])).fetchone()
            if task_id and not task:raise not_found()
            if request_source.action=='method-read':history,next_task_id=self._task_history(conn,row,task if task_id else None)
            if task and task['policy_revision']=='bounded_usage_upper_v2':
                from .method_result import result_view
                authorized=True
                saved=conn.execute('SELECT s.body_origin_state,s.method_commit_json IS NOT NULL FROM research_provider_sessions s JOIN research_paid_approvals a ON a.id=s.approval_id WHERE a.task_id=? AND a.research_id=? ORDER BY s.rowid DESC LIMIT 1',(task['id'],row['id'])).fetchone()
                state='unavailable' if saved and (saved[0]=='closed' or saved[1]) else 'none'
                if not task['stop_requested'] and task['execution'] not in ('FAILED','CANCELLED','ACCESS_REVOKED'):
                    try:
                        result=result_view(conn,store=self.store,lease=lease,identity=identity,rid=row['id'],task_id=task['id'],request_source=request_source)
                        if result is not None:state='available'
                    except ResearchError as exc:
                        if exc.code!='NOT_FOUND':raise
                        state='unavailable'
                    except (PermissionError,ValueError,TypeError,KeyError):state='unavailable'
        view=ResearchProjection.build(conn,row,task_id=task_id,method_result=result,method_authorized=authorized,
            method_state=state,task_history=history,next_task_id=next_task_id)
        if projection_bytes(view)>RESEARCH_RESPONSE_LIMIT:raise ResearchError('PAYLOAD_LIMIT',413,'研究结果超过响应范围；旧记录未更改。')
        return view

    @staticmethod
    def _task_history(conn,control,anchor):
        current=conn.execute('SELECT id FROM research_tasks WHERE research_id=? AND input_revision=? ORDER BY start_version DESC,id DESC LIMIT 1',
            (control['id'],control['current_revision'])).fetchone()
        sql='SELECT * FROM research_tasks WHERE research_id=?';args=[control['id']]
        if anchor:
            sql+=' AND (start_version<? OR (start_version=? AND id<=?))'
            args.extend((anchor['start_version'],anchor['start_version'],anchor['id']))
        rows=conn.execute(sql+' ORDER BY start_version DESC,id DESC LIMIT 21',args).fetchall();items=[]
        for task in rows[:20]:
            stored=conn.execute('SELECT s.body_origin_state,s.received_at,s.method_commit_json IS NOT NULL FROM research_provider_sessions s JOIN research_paid_approvals a ON a.id=s.approval_id WHERE a.task_id=? AND a.research_id=? ORDER BY s.rowid DESC LIMIT 1',(task['id'],control['id'])).fetchone()
            status='stored' if stored and stored[0]=='present' and stored[2] else 'unavailable' if stored and stored[0]=='closed' else 'none'
            items.append(dict(task_id=task['id'],input_revision=task['input_revision'],input_digest=task['input_digest'],start_version=task['start_version'],
                execution=task['execution'],is_historical=bool(task['input_revision']!=control['current_revision'] or not current or current[0]!=task['id']),
                received_at=stored[1] if stored else None,result_status=status))
        return items,rows[20]['id'] if len(rows)>20 else None

    def paid_preview(self,identity,research_id,request,key,*,funding_resolver=None):
        from .paid_approval import PaidApprovalService,OfflineFundingResolver
        from .schemas import PaidPreviewRequest
        rid=self._id(research_id);pid=self._principal(identity)
        with self.store.transaction() as conn:self.authorization.check(conn,identity,pid,rid)
        if type(request) is not PaidPreviewRequest:raise ResearchError('INPUT_INVALID',422,'预览请求无效。')
        if type(funding_resolver) is not OfflineFundingResolver:raise ResearchError('BUDGET_UNVERIFIED',503,'当前资金来源未核。')
        result=PaidApprovalService(self.store,funding_resolver=funding_resolver).preview(identity,rid,request.input_revision,
            request.expected_research_version,tuple(request.excerpt_ids),key=key,client_request_digest=digest(request.model_dump(mode='json')))
        return self._paid_envelope(result['preview_view'])

    def paid_confirm(self,identity,research_id,request,key,*,funding_resolver=None):
        from .paid_approval import PaidApprovalService,OfflineFundingResolver
        from .schemas import PaidConfirmationRequest
        rid=self._id(research_id);pid=self._principal(identity)
        with self.store.transaction() as conn:self.authorization.check(conn,identity,pid,rid,scope='write')
        if type(request) is not PaidConfirmationRequest:raise ResearchError('INPUT_INVALID',422,'确认请求无效。')
        if request.confirm_external_input is not True or request.confirm_maximum_reserve is not True:raise ResearchError('INPUT_INVALID',422,'请明确核对本次范围。')
        with self.store.transaction() as conn:
            preview=conn.execute('SELECT principal_id,research_id FROM research_paid_approvals WHERE id=?',(request.preview_ref,)).fetchone()
            if not preview or preview['principal_id']!=pid or preview['research_id']!=rid:raise not_found()
        if type(funding_resolver) is not OfflineFundingResolver:raise ResearchError('BUDGET_UNVERIFIED',503,'当前资金来源未核。')
        result=PaidApprovalService(self.store,funding_resolver=funding_resolver).confirm(identity,request.preview_ref,request.preview_digest,key,
            expected_preview_version=request.expected_preview_version,research_id=rid,input_revision=request.input_revision,
            expected_research_version=request.expected_research_version,client_request_digest=digest(request.model_dump(mode='json')))
        fields=('approval_ref','preview_version','research_version','task_id','task_version','execution','status')
        return self._paid_envelope({**{name:result[name] for name in fields},'preview_ref':request.preview_ref,'preview_digest':request.preview_digest,
            'execution_mode':'offline_probe','model_analysis_ran':False})

    @staticmethod
    def _paid_envelope(data):
        from .schemas import SCHEMA_VERSION,CONTRACT_REVISION
        result={'schema_version':SCHEMA_VERSION,'contract_revision':CONTRACT_REVISION,'data':data}
        if len(canonical(result).encode())>524288:raise ResearchError('PAYLOAD_LIMIT',413,'响应超过范围上限。')
        return result

    def index(self, identity, query):
        """Keyset page of currently readable research, never a saved-view cache."""
        from .schemas import ResearchIndexQuery,SCHEMA_VERSION,CONTRACT_REVISION
        if type(query) is not ResearchIndexQuery:raise ResearchError("INPUT_INVALID",422,"列表分页参数无效。")
        query=ResearchIndexQuery.model_validate(query.model_dump())
        boundary=None
        namespace="research-owner-index-v1"
        if query.cursor is not None:
            try:
                raw=base64.b64decode(query.cursor+"="*((-len(query.cursor))%4),altchars=b"-_",validate=True)
                if base64.urlsafe_b64encode(raw).decode().rstrip("=")!=query.cursor:raise ValueError()
                def unique(pairs):
                    data={}
                    for key,value in pairs:
                        if key in data:raise ValueError()
                        data[key]=value
                    return data
                boundary=json.loads(raw.decode("utf-8"),object_pairs_hook=unique)
                if type(boundary) is not dict or set(boundary)!={"operation","scope","updated_at","research_id"}:raise ValueError()
                if boundary["operation"]!=namespace or not all(type(v) is str for v in boundary.values()):raise ValueError()
                for name in ("research_id",):
                    parsed=UUID(boundary[name])
                    if parsed.version!=4 or str(parsed)!=boundary[name]:raise ValueError()
                if re.fullmatch(r"[0-9a-f]{64}",boundary["scope"]) is None:raise ValueError()
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z",boundary["updated_at"],re.ASCII) is None:raise ValueError()
                datetime.strptime(boundary["updated_at"],"%Y-%m-%dT%H:%M:%S.%fZ")
            except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):
                raise ResearchError("INPUT_INVALID",422,"列表分页游标无效。") from None
        with self.store.transaction() as conn:
            self.authorization.check_account(conn,identity)
            principal=conn.execute("SELECT * FROM research_principals WHERE normalized_email=? AND session_generation=?",(identity.email,identity.generation)).fetchone()
            empty={"schema_version":SCHEMA_VERSION,"contract_revision":CONTRACT_REVISION,"data":{"items":[],"next_cursor":None}}
            if principal is None:
                if boundary is not None:raise ResearchError("INPUT_INVALID",422,"列表分页游标无效。")
                return empty
            pid=principal["id"]
            self.authorization.check(conn,identity,pid)
            scope=digest({"operation":namespace,"principal":pid,"generation":identity.generation})
            if boundary is not None and boundary["scope"]!=scope:
                raise ResearchError("INPUT_INVALID",422,"列表分页游标无效。")
            if boundary:
                try:anchor=self.authorization.check(conn,identity,pid,boundary["research_id"])
                except ResearchError:raise ResearchError("REVISION_CONFLICT",409,"列表游标已失效，请重新读取。") from None
                if anchor["updated_at"]!=boundary["updated_at"]:
                    raise ResearchError("REVISION_CONFLICT",409,"列表游标已失效，请重新读取。")
            cursor_sql=" AND (c.updated_at<? OR (c.updated_at=? AND c.id<?))" if boundary else ""
            params=[pid,principal["epoch"],pid,principal["epoch"]]
            if boundary:params.extend((boundary["updated_at"],boundary["updated_at"],boundary["research_id"]))
            params.append(query.limit+1)
            rows=conn.execute("""SELECT c.*,r.problem_json FROM research_controls c
                JOIN research_revisions r ON r.research_id=c.id AND r.revision=c.current_revision
                WHERE c.owner_id=? AND c.owner_epoch=? AND c.lifecycle='active'
                AND EXISTS(SELECT 1 FROM research_grants g WHERE g.principal_id=? AND g.principal_epoch=?
                    AND g.research_id=c.id AND g.acl_epoch=c.acl_epoch AND g.status='active'
                    AND EXISTS(SELECT 1 FROM json_each(g.scopes) WHERE value='read'))"""+cursor_sql+
                " ORDER BY c.updated_at DESC,c.id DESC LIMIT ?",params).fetchall()
            items=[]
            for row in rows[:query.limit]:
                self.authorization.check(conn,identity,pid,row["id"])
                task=conn.execute("SELECT execution,evidence FROM research_tasks WHERE research_id=? AND input_revision=? ORDER BY start_version DESC,id DESC LIMIT 1",(row["id"],row["current_revision"])).fetchone()
                try:title=json.loads(row["problem_json"])["summary"]
                except (ValueError,KeyError,TypeError):raise ResearchError("STORE_UNAVAILABLE",503,"研究记录当前无法核对。") from None
                if type(title) is not str:raise ResearchError("STORE_UNAVAILABLE",503,"研究记录当前无法核对。")
                items.append({"research_id":row["id"],"title":title[:160],"current_input_revision":row["current_revision"],"updated_at":row["updated_at"],
                    "current_task":{"execution":task["execution"],"evidence":task["evidence"]} if task else None})
            next_cursor=None
            if len(rows)>query.limit:
                last=rows[query.limit-1]
                next_cursor=base64.urlsafe_b64encode(canonical({"operation":namespace,"scope":scope,"updated_at":last["updated_at"],"research_id":last["id"]}).encode()).decode().rstrip("=")
            return {"schema_version":SCHEMA_VERSION,"contract_revision":CONTRACT_REVISION,"data":{"items":items,"next_cursor":next_cursor}}

    def start(self,identity,research_id,request,key):
        from .budget import require_enabled, POLICY
        from .runner import event_in
        require_enabled()
        rid,principal=self._id(research_id),self._principal(identity)
        payload=request.model_dump(mode="json")
        with self.authorization.owner_gate(principal),self.store.transaction(write=True) as conn:
            row=self.authorization.check(conn,identity,principal,rid,scope="write")
            replay=self._replay(conn,principal,"start","r:"+rid,key,digest(payload))
            if replay is not None:return replay
            if row["version"]!=payload["expected_research_version"] or row["current_revision"]!=payload["input_revision"]:
                raise ResearchError("REVISION_CONFLICT",409,"问题已有新版本，请先刷新。")
            if row["version"]==2147483647:raise ResearchError("VERSION_CONFLICT",409,"研究版本已达上限。")
            revision=conn.execute("SELECT * FROM research_revisions WHERE research_id=? AND revision=?",(rid,row["current_revision"])).fetchone()
            if not json.loads(revision["problem_json"])["confirmed"]:
                raise ResearchError("INPUT_INVALID",422,"请先确认并保存问题结构。")
            if conn.execute("SELECT 1 FROM research_tasks WHERE research_id=? AND execution IN ('QUEUED','RUNNING','WAITING_EXTERNAL','RECONCILING')",(rid,)).fetchone():
                raise ResearchError("VERSION_CONFLICT",409,"该研究已有尚未结束的流程。")
            if conn.execute("""SELECT 1 FROM research_reservations r JOIN research_tasks t ON t.id=r.task_id
                WHERE t.research_id=? AND t.input_revision=? AND r.status IN ('SENT','UNKNOWN')""",(rid,row["current_revision"])).fetchone():
                raise ResearchError("RECONCILIATION_REQUIRED",409,"同一问题仍有未确认调用，请先对账。")
            task,grant,timestamp=str(uuid4()),str(uuid4()),now()
            owner=conn.execute("SELECT * FROM research_principals WHERE id=?",(principal,)).fetchone()
            conn.execute("INSERT INTO research_grants (id,principal_id,principal_epoch,research_id,acl_epoch,scopes,status,created_at) VALUES(?,?,?,?,?,?,'active',?)",(grant,principal,owner["epoch"],rid,row["acl_epoch"],'["execute"]',timestamp))
            conn.execute("""INSERT INTO research_tasks
                (id,research_id,principal_id,principal_epoch,owner_epoch,acl_epoch,grant_id,auth_generation,input_revision,input_digest,start_version,
                 execution,phase,version,policy_revision,execution_mode,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'QUEUED','queued',1,?,'offline_probe',?,?)""",
                (task,rid,principal,owner["epoch"],row["owner_epoch"],row["acl_epoch"],grant,identity.generation,row["current_revision"],revision["digest"],row["version"]+1,POLICY,timestamp,timestamp))
            conn.execute("INSERT INTO research_attempts VALUES(?,1,'initial',?,?)",(task,POLICY,revision["digest"]))
            for position,kind in enumerate(("discover_sources","compose_report")):
                conn.execute("INSERT INTO research_steps(id,task_id,position,kind,state) VALUES(?,?,?,?,'PENDING')",(str(uuid4()),task,position,kind))
            event_in(conn,task,"created")
            conn.execute("UPDATE research_controls SET version=version+1,updated_at=? WHERE id=?",(timestamp,rid))
            result=ResearchProjection.build(conn,self.authorization.check(conn,identity,principal,rid))
            self._remember(conn,principal,"start","r:"+rid,key,digest(payload),result)
            return result

    def task_action(self,identity,research_id,request,key,operation,*,request_source=None):
        from .budget import BudgetLedger, require_enabled
        from .runner import state_in
        rid,principal=self._id(research_id),self._principal(identity)
        payload=request.model_dump(mode="json")
        if operation=='reconcile':
            with self.store.transaction() as conn:
                self.authorization.check(conn,identity,principal,rid,scope='write')
                candidate=conn.execute('SELECT policy_revision FROM research_tasks WHERE id=? AND research_id=?',(request.task_id,rid)).fetchone()
                method=bool(candidate and candidate[0]=='bounded_usage_upper_v2' and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (9,10))
            if method:return self._reconcile_method(identity,rid,principal,request,key,request_source)
        with self.authorization.owner_gate(principal) as lease,self.store.transaction(write=True) as conn:
            row=self.authorization.check(conn,identity,principal,rid,scope="write")
            task=conn.execute("SELECT * FROM research_tasks WHERE id=? AND research_id=?",(request.task_id,rid)).fetchone()
            if not task:raise not_found()
            is_paid=task['policy_revision']=='bounded_usage_upper_v2'
            method_request=is_paid and operation=='reconcile' and request_source is not None and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (9,10)
            if method_request:
                from .paid_control import require_authenticated_action
                require_authenticated_action(request_source,identity=identity,action='method-reconcile',research_id=rid,task_id=task['id'],key=key,body_digest=digest(payload))
            if not is_paid and operation!='cancel':require_enabled()
            if is_paid and operation=='resume':raise ResearchError('FEATURE_UNAVAILABLE',503,'此任务不能自动继续或重新外发。')
            if (is_paid or task['policy_revision']=='local-formula-v1') and operation=='cancel':
                from .paid_control import require_authenticated_action
                require_authenticated_action(request_source,identity=identity,action='cancel',research_id=rid,task_id=task['id'],key=key,body_digest=digest(payload))
            if task['policy_revision']=='local-formula-v1' and operation!='cancel':
                raise ResearchError('FEATURE_UNAVAILABLE',503,'公式检查不能自动恢复或重复计算；请核对原结果标识。')
            if task["policy_revision"]=="d1-source-only-v1" and operation!="cancel":
                raise ResearchError("RECONCILIATION_REQUIRED",409,"来源读取只能闭合旧执行后重新预览并明确批准，不能继续旧调用。")
            replay=self._replay(conn,principal,operation,"r:"+rid,key,digest(payload))
            if replay is not None:
                if method_request:return self._method_projection(conn,row,identity,lease,request_source,task['id'])
                if is_paid and operation=='reconcile' and conn.execute('SELECT version FROM research_schema').fetchone()[0] in (9,10):
                    return ResearchProjection.build(conn,row,task_id=task['id'])
                return replay
            if task["version"]!=request.expected_task_version:
                raise ResearchError("VERSION_CONFLICT",409,"任务状态已变化，请先刷新。")
            unresolved=conn.execute("SELECT count(*) FROM research_reservations WHERE task_id=? AND status IN ('SENT','UNKNOWN')",(task["id"],)).fetchone()[0]
            if operation=="cancel":
                if task["execution"] not in ("COMPLETED","FAILED","ACCESS_REVOKED"):
                    if is_paid:
                        from .paid_control import mint_stop_authority
                        from .paid_budget import stop_financial_in
                        authority=mint_stop_authority(conn,store=self.store,lease=lease,principal_id=principal,task_id=task['id'],
                            expected_task_version=task['version'],identity=identity,request_source=request_source,key=key,body_digest=digest(payload))
                        stop_financial_in(conn,store=self.store,lease=lease,authority=authority)
                    elif task['policy_revision']=='local-formula-v1':
                        from .formula_result import cancel_in
                        cancel_in(conn,store=self.store,lease=lease,identity=identity,principal=principal,rid=rid,task_id=task['id'])
                    else:BudgetLedger.release_prepared_in(conn,task["id"])
                    conn.execute("UPDATE research_tasks SET stop_requested=1 WHERE id=?",(task["id"],))
                    conn.execute("UPDATE research_steps SET state='DISCARDED',version=version+1 WHERE task_id=? AND state IN ('PENDING','PREPARED')",(task["id"],))
                    if not is_paid or task['execution']!='CANCELLED':state_in(conn,task["id"],"CANCELLED",kind="stop_requested")
            elif operation=="reconcile":
                if is_paid:
                    from .paid_budget import reconcile_task_in
                    reconcile_task_in(conn,store=self.store,lease=lease,task_id=task['id'])
                    conn.execute('UPDATE research_tasks SET reconcile_requested=0 WHERE id=?',(task['id'],))
                    if method_request and not task['stop_requested'] and task['execution'] not in ('FAILED','CANCELLED','ACCESS_REVOKED'):
                        from .method_result import commit_result
                        try:commit_result(conn,store=self.store,lease=lease,identity=identity,rid=rid,task_id=task['id'],request_source=request_source)
                        except (PermissionError,ValueError,TypeError,KeyError):raise not_found() from None
                elif unresolved or task["execution"]=="RECONCILING":
                    conn.execute("UPDATE research_tasks SET reconcile_requested=1 WHERE id=?",(task["id"],))
                    state_in(conn,task["id"],task["execution"],kind="reconciling")
            elif operation=="resume":
                if task["stop_requested"] or task["execution"]!="WAITING_EXTERNAL" or unresolved:
                    raise ResearchError("RECONCILIATION_REQUIRED",409,"当前状态不能继续，请先核对调用。")
                self.authorization.check_task(conn,task)
                if not BudgetLedger.ready_in(conn,task["id"]):
                    raise ResearchError("BUDGET_UNVERIFIED",503,"当前演练额度或费率尚不允许继续。")
                state_in(conn,task["id"],"QUEUED",kind="waiting")
            else:raise ValueError("unregistered task action")
            row=self.authorization.check(conn,identity,principal,rid,scope='write')
            result=self._method_projection(conn,row,identity,lease,request_source if method_request else None,task['id'])
            cached={'_method_result_replay':1,'task_id':task['id']} if method_request else result
            self._remember(conn,principal,operation,"r:"+rid,key,digest(payload),cached)
            return result

    def _reconcile_method(self,identity,rid,principal,request,key,request_source):
        """Commit trusted financial outcome before optional body publication.

        A later unavailable body or response-size error cannot undo valid fees.
        No network or new execution is started by either phase.
        """
        payload=request.model_dump(mode='json')
        with self.authorization.owner_gate(principal) as lease,self.store.transaction(write=True) as conn:
            self.authorization.check(conn,identity,principal,rid,scope='write')
            task=conn.execute('SELECT * FROM research_tasks WHERE id=? AND research_id=?',(request.task_id,rid)).fetchone()
            if not task or task['policy_revision']!='bounded_usage_upper_v2':raise not_found()
            if request_source is not None:
                from .paid_control import require_authenticated_action
                require_authenticated_action(request_source,identity=identity,action='method-reconcile',research_id=rid,task_id=task['id'],key=key,body_digest=digest(payload))
            replay=self._replay(conn,principal,'reconcile','r:'+rid,key,digest(payload))
            if replay is None:
                if task['version']!=request.expected_task_version:raise ResearchError('VERSION_CONFLICT',409,'任务状态已变化，请先刷新。')
                from .paid_budget import reconcile_task_in
                reconcile_task_in(conn,store=self.store,lease=lease,task_id=task['id'])
                conn.execute('UPDATE research_tasks SET reconcile_requested=0 WHERE id=?',(task['id'],))
                if request_source is not None and not task['stop_requested'] and task['execution'] not in ('FAILED','CANCELLED','ACCESS_REVOKED'):
                    from .method_result import commit_result
                    commit_result(conn,store=self.store,lease=lease,identity=identity,rid=rid,task_id=task['id'],request_source=request_source)
                self._remember(conn,principal,'reconcile','r:'+rid,key,digest(payload),{'_method_result_replay':1,'task_id':task['id']})
        # Deliberately outside the mutation transaction, including replay.
        return self.view(identity,rid,task_id=request.task_id,request_source=request_source)

    def events(self,identity,research_id,task_id,after_seq):
        rid,principal=self._id(research_id),self._principal(identity)
        self._id(task_id)
        if type(after_seq) is not int or after_seq<0:raise ResearchError("INPUT_INVALID",422,"事件游标无效。")
        with self.store.transaction() as conn:
            self.authorization.check(conn,identity,principal,rid)
            if not conn.execute("SELECT 1 FROM research_tasks WHERE id=? AND research_id=?",(task_id,rid)).fetchone():raise not_found()
            rows=[dict(r) for r in conn.execute("SELECT seq,state_version,kind,safe_code,at FROM research_task_events WHERE task_id=? AND seq>? ORDER BY seq LIMIT 200",(task_id,after_seq))]
            return {"schema_version":"structure-research-v1","contract_revision":"b1-candidate-01","data":{"items":rows,"after_seq":rows[-1]["seq"] if rows else after_seq}}

    def begin_account_deletion_locked(self, email, generation, gate_id, cleanup_binding,*,owner_lease=None,request_source=None):
        """Internal only: caller holds this owner's OS gate and revalidated auth.

        The committed fence is intentionally outside the legacy multi-store
        compensation. No legacy restore can turn this epoch active again.
        """
        with self.store.transaction(write=True) as conn:
            user = conn.execute("SELECT session_generation,lifecycle FROM auth_users WHERE email=?", (email,)).fetchone()
            if not user or user["session_generation"] != generation or user["lifecycle"] != "active":
                raise ResearchError("AUTH_REQUIRED", 401, "账户当前无法执行删除。")
            if self.store.auth_store.owner_gate_in(conn, email) != gate_id:
                raise ResearchError("AUTHORIZATION_STALE", 409, "账户状态已变化。")
            principal = conn.execute("SELECT * FROM research_principals WHERE normalized_email=? AND session_generation=?", (email,generation)).fetchone()
            if principal is None:
                principal_id = str(uuid4())
                conn.execute("INSERT INTO research_principals VALUES(?,?,?,?,?,?,?,?)",
                             (principal_id,"account",email,generation,1,"active",now(),gate_id))
            else:
                principal_id = principal["id"]
            has_paid=conn.execute("SELECT 1 FROM research_tasks WHERE principal_id=? AND policy_revision IN ('bounded_usage_upper_v2','local-formula-v1') LIMIT 1",(principal_id,)).fetchone()
            if conn.execute('SELECT version FROM research_schema').fetchone()[0]==10:
                has_paid=has_paid or conn.execute('SELECT 1 FROM research_formula_revisions f JOIN research_controls c ON c.id=f.research_id WHERE c.owner_id=? LIMIT 1',(principal_id,)).fetchone()
            from .paid_control import require_authenticated_action,create_authenticated_deletion_job
            formal=self.store._formal_mode()
            protected=formal or bool(has_paid)
            if request_source is not None:
                require_authenticated_action(request_source,identity=request_source.identity,action='account-delete')
                if request_source.identity.email!=email or request_source.identity.generation!=generation:
                    raise PermissionError('deletion request incarnation mismatch')
            elif protected:raise ResearchError('AUTHORIZATION_STALE',403,'此删除需要实际认证操作来源。')
            job_id, timestamp = str(uuid4()), now()
            if formal:
                if __package__=='web.backend.research':from ..services.auth_registration import mark_account_deleting
                else:from services.auth_registration import mark_account_deleting
                mark_account_deleting(conn,store=self.store,lease=owner_lease,request_source=request_source,email=email,generation=generation)
            else:
                conn.execute("UPDATE auth_users SET lifecycle='deleting' WHERE email=? AND session_generation=?", (email,generation))
            conn.execute("UPDATE research_principals SET status='deleting',epoch=epoch+1 WHERE id=? AND status!='deleted'", (principal_id,))
            conn.execute("UPDATE research_grants SET status='revoked' WHERE principal_id=?", (principal_id,))
            conn.execute("UPDATE research_controls SET lifecycle='deleting' WHERE owner_id=?", (principal_id,))
            values=dict(id=job_id,owner_key=self.store.auth_store.owner_key(email),gate_id=gate_id,cleanup_binding=cleanup_binding,
                database_binding=hashlib.sha256(str(self.store.path).encode()).hexdigest(),owner_email=email,session_generation=generation,state='pending',created_at=timestamp)
            if request_source is not None and protected:
                create_authenticated_deletion_job(conn,store=self.store,lease=owner_lease,source=request_source,values=values)
            else:
                conn.execute('INSERT INTO auth_deletion_jobs('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
            from .budget import BudgetLedger
            from .runner import state_in
            for task in conn.execute("SELECT * FROM research_tasks WHERE principal_id=?",(principal_id,)).fetchall():
                if task['policy_revision']=='bounded_usage_upper_v2':
                    from .paid_control import mint_stop_authority
                    from .paid_budget import stop_financial_in
                    authority=mint_stop_authority(conn,store=self.store,lease=owner_lease,principal_id=principal_id,
                        task_id=task['id'],expected_task_version=task['version'],deletion_job_id=job_id)
                    stop_financial_in(conn,store=self.store,lease=owner_lease,authority=authority)
                else:BudgetLedger.release_prepared_in(conn,task["id"])
                conn.execute("UPDATE research_tasks SET stop_requested=1,reconcile_requested=1 WHERE id=?",(task["id"],))
                state_in(conn,task["id"],"ACCESS_REVOKED",kind="authorization_changed")
            return job_id

    def deletion_job(self, job_id):
        self._id(job_id)
        with self.store.transaction() as conn:
            row = conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise not_found()
            if row["database_binding"] != hashlib.sha256(str(self.store.path).encode()).hexdigest():
                raise ResearchError("AUTHORIZATION_STALE",409,"删除任务数据库绑定不一致。")
            return dict(row)

    def erase_research_locked(self, job_id,*,owner_lease=None):
        with self.store.transaction(write=True) as conn:
            job = conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state='pending'", (job_id,)).fetchone()
            if not job or not job["owner_email"] or not job["session_generation"]:
                raise ResearchError("AUTHORIZATION_STALE", 409, "删除任务状态已变化。")
            from .paid_control import verify_deletion_origin,deletion_job_write
            verify_deletion_origin(conn,store=self.store,lease=owner_lease,job_id=job_id)
            email, generation = job["owner_email"], job["session_generation"]
            if self.store.auth_store.owner_key(email) != job["owner_key"] or self.store.auth_store.owner_gate_in(conn,email) != job["gate_id"]:
                raise ResearchError("AUTHORIZATION_STALE", 409, "删除任务绑定不一致。")
            user = conn.execute("SELECT lifecycle,session_generation FROM auth_users WHERE email=?", (email,)).fetchone()
            if user and (user["lifecycle"] != "deleting" or user["session_generation"] != generation):
                raise ResearchError("AUTHORIZATION_STALE", 409, "删除任务不能影响其他账户。")
            if job["research_erased"]:
                return json.loads(job["research_counts_json"])
            principal = conn.execute("SELECT id,status FROM research_principals WHERE normalized_email=? AND session_generation=?", (email,generation)).fetchone()
            if not principal or principal["status"] != "deleting":
                raise ResearchError("AUTHORIZATION_STALE", 409, "删除任务主体状态不一致。")
            pid = principal["id"]
            if self.store._formal_mode():
                if __package__=='web.backend.research':from ..services.auth_registration import erase_registration_for_job
                else:from services.auth_registration import erase_registration_for_job
                erase_registration_for_job(conn,store=self.store,lease=owner_lease,job_id=job_id)
            from .paid_approval import erase_paid_private_inputs
            erase_paid_private_inputs(self.store,conn,pid,job_id,owner_lease=owner_lease)
            count = lambda table, clause, params: conn.execute(f"SELECT count(*) FROM {table} WHERE {clause}",params).fetchone()[0]
            counts = {
                "researches": count("research_controls","owner_id=?",(pid,)),
                "revisions": count("research_revisions","research_id IN (SELECT id FROM research_controls WHERE owner_id=?)",(pid,)),
                "idempotency_results": count("research_idempotency","principal_id=?",(pid,)),
                "grants": count("research_grants","principal_id=?",(pid,)),
            }
            tasks=[t["id"] for t in conn.execute("SELECT id FROM research_tasks WHERE principal_id=?",(pid,))]
            for task_id in tasks:
                from .source_integration import purge_for_deletion
                purge_for_deletion(self.store,conn,task_id,job_id)
                conn.execute("DELETE FROM research_step_outputs WHERE task_id=?",(task_id,))
                conn.execute("DELETE FROM research_task_events WHERE task_id=?",(task_id,))
                conn.execute("UPDATE research_attempts SET input_digest=NULL WHERE task_id=?",(task_id,))
                conn.execute("UPDATE research_dispatch_permits SET input_digest=NULL WHERE step_id IN (SELECT id FROM research_steps WHERE task_id=?)",(task_id,))
                conn.execute("UPDATE research_tasks SET grant_id=NULL,auth_generation=NULL,input_revision=NULL,input_digest=NULL,research_id=NULL WHERE id=?",(task_id,))
            conn.execute("DELETE FROM research_idempotency WHERE principal_id=?",(pid,))
            conn.execute("DELETE FROM research_revisions WHERE research_id IN (SELECT id FROM research_controls WHERE owner_id=?)",(pid,))
            conn.execute("DELETE FROM research_grants WHERE principal_id=?",(pid,))
            conn.execute("DELETE FROM research_controls WHERE owner_id=?",(pid,))
            deletion_job_write(conn,store=self.store,lease=owner_lease,job_id=job_id,
                sql="UPDATE auth_deletion_jobs SET research_erased=1,research_counts_json=? WHERE id=?",args=(canonical(counts),job_id))
            return counts

    def finish_account_deletion_locked(self, job_id, removed,*,owner_lease=None):
        # First clear private bindings durably. A crash/busy checkpoint then
        # needs only the opaque job/gate and same DB, never restored identity.
        with self.store.transaction(write=True) as conn:
            job = conn.execute("SELECT * FROM auth_deletion_jobs WHERE id=? AND state!='completed'",(job_id,)).fetchone()
            if not job or not job["research_erased"]:
                raise ResearchError("AUTHORIZATION_STALE",409,"删除任务尚未完成。")
            from .paid_control import verify_deletion_origin,deletion_job_write
            verify_deletion_origin(conn,store=self.store,lease=owner_lease,job_id=job_id)
            if job["state"] == "pending":
                if removed is None or conn.execute("SELECT 1 FROM auth_users WHERE email=?",(job["owner_email"],)).fetchone():
                    raise ResearchError("AUTHORIZATION_STALE",409,"账户清理尚未完成。")
                result = {"deleted_at":now(),"removed":{**removed,"research":json.loads(job["research_counts_json"])}}
                conn.execute("UPDATE research_principals SET status='deleted',normalized_email=NULL,session_generation=NULL WHERE normalized_email=? AND session_generation=? AND status='deleting'",(job["owner_email"],job["session_generation"]))
                deletion_job_write(conn,store=self.store,lease=owner_lease,job_id=job_id,
                    sql="UPDATE auth_deletion_jobs SET state='scrubbing',owner_email=NULL,session_generation=NULL,result_json=? WHERE id=?",args=(canonical(result),job_id))
            else:
                result = json.loads(job["result_json"])
        # Explicitly truncate old frames, even if another connection keeps WAL
        # alive. A busy historical reader leaves scrubbing and access closed.
        self.store.checkpoint_erasure()
        with self.store.transaction(write=True) as conn:
            deletion_job_write(conn,store=self.store,lease=owner_lease,job_id=job_id,
                sql="UPDATE auth_deletion_jobs SET state='completed',completed_at=? WHERE id=? AND state='scrubbing'",args=(now(),job_id))
            return result

    def prepare_legacy_deletion_locked(self, job_id,*,owner_lease=None):
        """Persist attempted before side effects; never infer a lost receipt."""
        with self.store.transaction(write=True) as conn:
            from .paid_control import verify_deletion_origin,deletion_job_write
            verify_deletion_origin(conn,store=self.store,lease=owner_lease,job_id=job_id)
            job=conn.execute("SELECT legacy_attempted,legacy_receipt_json FROM auth_deletion_jobs WHERE id=? AND state='pending'",(job_id,)).fetchone()
            if not job:
                raise ResearchError("AUTHORIZATION_STALE",409,"删除任务状态已变化。")
            if job["legacy_receipt_json"] is not None:
                return False,json.loads(job["legacy_receipt_json"])
            first=not bool(job["legacy_attempted"])
            deletion_job_write(conn,store=self.store,lease=owner_lease,job_id=job_id,
                sql="UPDATE auth_deletion_jobs SET legacy_attempted=1 WHERE id=?",args=(job_id,))
            return first,None

    def record_legacy_deletion_locked(self, job_id, removed, *, first,owner_lease=None):
        receipt={"count_status":"known" if first else "unknown_after_interruption","observed":removed}
        with self.store.transaction(write=True) as conn:
            from .paid_control import deletion_job_write
            changed=deletion_job_write(conn,store=self.store,lease=owner_lease,job_id=job_id,
                sql="UPDATE auth_deletion_jobs SET legacy_receipt_json=? WHERE id=? AND state='pending' AND legacy_attempted=1 AND legacy_receipt_json IS NULL",args=(canonical(receipt),job_id)).rowcount
            if changed != 1:
                raise ResearchError("AUTHORIZATION_STALE",409,"删除收据状态已变化。")
        return receipt

    @staticmethod
    def legacy_deletion_result(receipt):
        if receipt["count_status"] == "known":
            return receipt["observed"]
        # These values describe only the successful recovery pass, not the
        # original job's possibly committed deletes. A retry's zero is not a
        # zero original deletion count.
        return {name:{"count_status":"unknown_after_interruption","recovery_observed":observed}
                for name,observed in receipt["observed"].items()}
