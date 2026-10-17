# Structure B1 共享契约设计候选

版本：`b1-candidate-01`；日期：2026-10-16；关联 Issue #251、父任务 #248。基线：`be3a3c6b5de19f2508335519d01240077bb591ec`。依据：PRD 0.2、ARCHITECTURE 与规划独审 B1-01/02/03。

**本文规定正式对象、事务和消费者边界，不是实现或冻结收据。** 2026-10-16 设计基线保留；2026-10-17 在 `e1604b011551ceae5036edfe8888ccfd3a2a43ff` 上按 Mentor 正常委派补充 D1 接线规则，依据为已批准 PRD 0.3 和 Mentor 已采纳的免费只读 GET 恢复方向，不伪称用户逐条原话。此文档增量待独审，不自行变更已发布 schema revision、实施范围或冻结状态，不允许下游把未冻结字段直接当正式导出消费。隔离实现、合入、共享冻结及真实调用分别依项目当前授权、完整 SHA 独审、必要 CI 与真实消费者证据推进；本文不放行付费调用、生产数据迁移或部署。

2026-10-17 第二增量以已审免费 GET 文档 `47a585873465358ad84e9b96d4f0d2dbbcbac67f` 为基线：Mentor 在既有范围内准入最小 bounded-provider 保守预算与 typed 模型报告方向，新增§3.5、§6.4及对应探针，待独审和正式 owner 版本化接线。此方向不需要用户再次确认，不代表实际 provider 价格、grant、余额或付费验收已经核实；不改已审免费 GET 例外、旧 fixture 行为及原 final receipt 语义。

## 1 边界与默认选择

三条用户路径共享一个研究对象：现象解题、公式对应、外部研究。B1 先实现正式导出、真实事务存储、受控执行器、投影与离线消费者；供应商替身只验证机制，不能记成真实文献或计费验收。采用单机 SQLite 和既有 FastAPI/账户入口，不引入通用代理、任意脚本执行、动态工具安装或多机调度。

候选默认：**新研究控制与内容表、预算表和权威授权记录位于既有 `AUTH_DATA_DIR/auth.sqlite3` 同一物理数据库**，新增表统一 `research_` 前缀；已有报告、收藏等旧库不在 B1 搬迁。这样新研究提交能在一个 SQLite 事务中检查当前账户 incarnation/epoch 并写结果，不把跨库补偿称为原子事务。迁移版本与账户删除适配须独审。若正式实现选择不同物理库，必须先提出等价的事务/权限证明并重审本设计，不能以读取一次 auth 状态代替。

`account_owner_transaction` 在当前基线是进程内 `threading.Lock`；不能承担新 worker 的跨进程承诺。B1 须增加单主机、同持久根的跨进程 owner gate，覆盖外发起始、认领及删除/撤权线性化；SQLite 事务负责持久条件写入。所有相关写者，包括共享账户的 API 入口，必须接同一实现。未接入的旧 writer 不能与新功能同时放行。具体探针见 [CONSUMER_PROBES](CONSUMER_PROBES.md)。

## 2 基础类型和输入不变量

以下字段无特别说明均必填；`?` 表示可为 null，`[]` 必须显式传空数组。服务器生成字段不得由客户端或 LLM 覆盖。API 按对象版本严格拒绝额外字段、重复 JSON key、非有限数、隐式 bool→int 转换和重复集合 ID。

| 类型 | 精确定义 |
| --- | --- |
| `Id` | 服务端生成的规范小写 UUID v4，36 字符；不含自然语言、邮箱或供应商令牌 |
| `Revision` / `Epoch` | 严格整数 `1..2147483647`；只增不减，溢出停止写入，不能环绕 |
| `UtcTime` | 服务端 UTC 字符串 `YYYY-MM-DDTHH:MM:SS.ffffffZ`；业务顺序依 version/epoch，不依时钟先后 |
| `Digest` | 小写 64 位 SHA-256；结构内容按排序 key、UTF-8、无 NaN 的规范 JSON 计算；原始来源文件按原字节计算。两者另标 `digest_kind`，不混称 |
| `Text(n)` | NFC 归一、最多 n Unicode 字符，拒绝危险控制字符；描述可含 TAB/LF，标识符不可含。原始用户输入仍另存，归一不改写原文 |
| `ExactText(n)` | 取得内容的有界精确字符序列，不做NFC归一；提取文本仅统一LF并记录处理版本；拒绝孤立surrogate，摘录与位置按Unicode字符而非UTF-16单元核对 |
| `DecimalText` | 有限十进制字符串；最多 18 个有效数字，非零值归一科学记数的阶数在 `[-12,12]`（普通小数也按此检查）；规范化后不保留负零。进入计算后仍执行资源与结果范围检查 |
| `Money` | `{currency: USD\|CNY, scale:int, amount_units:int}`；scale为`0..12`，一单位=该币种`10^-scale`，amount_units为`0..2^63-1`。同FundingAccount固定scale，须精确表示其余额、费率与账单；不使用float、不混scale/币种、不自动汇兑 |
| `LegacyRef` | `{kind: kb\|legacy_report\|discovery\|paper, id: Text(120), artifact_id: Text(120)}`；适配现有 ID，不能强改旧 ID 成新 UUID |
| `Envelope` | `{schema_version: "structure-research-v1", contract_revision: "b1-candidate-01", data: T}`；实现冻结时由 owner 核准 revision；不接受未知版本猜测兼容 |

所有未另定范围的计数、游标、tokens与size均为严格非负整数，拒绝bool/float；引用数组无重复且仅指向当前授权范围。`CatalogRef={artifact_id:Text(120),record_id:Text(120),record_digest:Digest}`。Model/Formula/Method从知识目录导入后建立本研究的不可变快照，Source引用也映射到该研究；不直接跨用户复用私有来源。

`PrivateBindingRef={id:Id}`是服务器配置句柄，不是密钥、账号配置或可外发的凭据。

引用的辅助类型：`Family={queue_flow,first_order_storage,local_recovery}`；`TemplateId={little,mm1,passive_decay,linear_stable}`。`SourceVersion={source_id:Id,revision:Revision,content_digest:Digest?,access:SourceRecord.access,read_scope:legacy_page_unverified|author_narrative_subset}`。`Transform={kind:constant_fold|commute|associate|rename_bijection|substitute_constant|multiply_nonzero|divide_nonzero|positive_time_scale|state_normalize,input_digest:Digest,output_digest:Digest,precondition_ids:Text(64)[]}`。`NumericTolerance={absolute:DecimalText,relative:DecimalText,policy_revision:Text(64)}`，两容差非负。`Action={view,cancel,refresh,request_reconciliation,revise,export,record_followup,retry,start,resume,sign_in,return_to_library}`。`TaskBudgetView={known_cost:Money[],held_cost:Money[],unknown_count:int,status:unverified|available|exhausted|reconciling}`，每币种最多一项，只展示本任务，不展示共享账户余额或账号。

输入问题正文 `1..4000` 字符、摘要 `8..1000` 字符；变量/约束/未知各最多 12 项，每项 120 字符；候选最多 10，来源最多 20，单任务执行步骤最多 64。JSON 请求体上限 64 KiB（附件不在本候选允许范围）；公式另有限额。原问题、身份、正文和分享凭据不进入 URL、公开日志或 incident 文本。

## 3 最小正式对象

### 3.1 研究、修订与授权

| 对象 | 字段与类型 | 必须成立 |
| --- | --- | --- |
| `Research` | `id:Id, owner_id:Id, owner_epoch:Epoch, acl_epoch:Epoch, current_revision:Revision, current_task_id:Id?, version:Revision, visibility:"private", lifecycle:active\|deleting\|deleted, created_at:UtcTime, updated_at:UtcTime` | owner/epoch 服务器赋值；新研究默认私有；deleted 不允许 upsert 复活 |
| `ProblemRevision` | `research_id:Id, revision:Revision, entry:phenomenon\|formula\|research, original_input:Text(4000), objective:Text(1000), summary:Text(1000), variables:Variable[], constraints:Text(120)[], unknowns:Text(120)[], confirmed:bool, created_at:UtcTime, digest:Digest` | 不可变；变量最多12；修改创建新 revision；`expected_revision` 不等于当前值则409，不覆盖旧报告 |
| `Variable` | `id:Text(32), label:Text(120), role:state\|parameter\|input\|constraint\|output, unit_id:UnitId?, observation:Text(400)?, provenance:user_observed\|user_assumed\|system_proposed` | `id` ASCII `[a-z][a-z0-9_]{0,31}`，同 revision 唯一；提出变量不等于已观察 |
| `Principal` | `id:Id, kind:account\|anonymous, status:active\|revoked\|deleting\|deleted, epoch:Epoch, auth_generation:Text(64)?, auth_binding:{normalized_email:Text(200),session_generation:Text(64)}?, created_at:UtcTime` | account 绑定当前 `auth_users` 的存在及 `session_generation`；删除后 binding 清除，重注册生成新 principal，不能恢复旧身份 |
| `ResearchGrant` | `id:Id, principal_id:Id, principal_epoch:Epoch, research_id:Id, acl_epoch:Epoch, scopes:read\|write\|execute 的集合, status:active\|revoked, created_at:UtcTime` | 由已验证身份签发，客户端不能自造 owner/grant；单次浏览器登出撤销读会话，不自动冒充后台任务已取消；账户/研究 grant 撤销会停止后续执行 |
| `AuthorizationSnapshot` | `principal_id:Id, principal_epoch:Epoch, research_id:Id, owner_epoch:Epoch, acl_epoch:Epoch, grant_id:Id, auth_generation:Text(64)?` | task/attempt 创建时绑定，开始每步、消费外发票、提交及读取投影时重核当前owner_id和全部epoch；不得以旧 JWT/缓存替代当前状态 |

匿名主体来自服务器验证的浏览器 proof，不接受请求正文 `anon_id` 作为资格。认领须同时证明匿名 ownership 与新账户身份；旧匿名 grant 撤销、研究 owner/acl epoch 递增，旧在途 attempt 不获新账户写资格。可显式创建新 attempt 继续，先对账旧外发，不能自动重放。现有报告认领由旧接口适配，不在 B1 隐式转换全部历史数据。

### 3.2 模型、公式、方法与证据

| 对象 | 字段与类型 | 必须成立 |
| --- | --- | --- |
| `ModelRecord` | `id:Id, research_id:Id, revision:Revision, catalog_ref:CatalogRef?, family:Family, label:Text(120), scope:global_model\|local_model\|accounting_relation, assumptions:Assumption[], formula_ids:Id[], source_ids:Id[], provenance:curated\|candidate` | 支持 family 仅本节后续三类；“curated”表示记录整理，不等于现实机制已证实 |
| `Assumption` | `id:Text(64), statement:Text(400), status:declared\|supported\|contradicted\|unknown, evidence_ids:Id[]` | supported 要有证据引用；客户端选择已满足仍只能形成 declared，由相应检查记录升级 |
| `FormulaRecord` | `id:Id, research_id:Id, revision:Revision, catalog_ref:CatalogRef?, model_id:Id, template_id:TemplateId, original_display:Text(2048), expression:Ast, symbols:Symbol[], assumptions:Assumption[], initial_conditions:Condition[], boundary_conditions:Condition[], source_ids:Id[], digest:Digest` | display 只展示不执行；AST 必须匹配允许模板/变换；符号、单位、条件完整才检查相应等级 |
| `Symbol` / `Condition` | `Symbol={id:ASCII32, role:state\|time\|parameter\|output, unit_id:UnitId, value:DecimalText?}`；`Condition={id:ASCII64, kind:initial\|boundary\|domain, statement:Text(400), status:declared\|supported\|contradicted\|unknown}` | 名称只在本侧作用域，不能把热与电的物理量直接相等；缺条件保留 unknown |
| `MethodRecord` | `id:Id, research_id:Id, revision:Revision, catalog_ref:CatalogRef?, model_id:Id, label:Text(120), description:Text(1200), source_ids:Id[], applicability:Assumption[], limitations:Text(400)[], support:unreviewed\|source_linked\|reviewed` | 无可定位原文只能作为提议；不能仅凭内部 KB 把 support 设 reviewed |
| `TransferProposal` | `id:Id, research_id:Id, revision:Revision, source_model_id:Id, method_id:Id?, mapping:MappingItem[], prerequisites:Assumption[], nontransferable:Text(400)[], competing_explanations:Text(400)[], test:TestPlan, status:"hypothesis"` | mapping最多12、竞争解释1..5；与当前现象的有效性仍是假设；LLM 不能设为实证成功 |
| `MappingItem` / `TestPlan` | `MappingItem={source_symbol:ASCII32, target_variable:ASCII32, rationale:Text(400), evidence_ids:Id[], limitations:Text(400)[]}`；`TestPlan={id:Id,question:Text(400), measurement:Text(700), primary_outcome:Text(240), competitor:Text(400), falsification:Text(400), stop_rule:Text(400)}` | 双侧引用存在；判据与停止条件不同，不能不可证伪；未执行计划不记结果 |
| `SourceRecord` | `id:Id, research_id:Id, revision:Revision, kind:internal_kb\|external_metadata\|external_html\|external_pdf\|user_observation, title:Text(300), canonical_url:Text(2000)?, authors:Text(120)[], published_at:Text(40)?, accessed_at:UtcTime?, provider_ref:Text(200)?, retrieval_scope:Text(700), read_scope:legacy_page_unverified\|author_narrative_subset, access:discovered\|metadata_only\|body_retrieved\|failed\|restricted, content_digest:Digest?, extracted_text_digest:Digest?, extractor_version:Text(64)?, license_note:Text(400), failure_code:ErrorCode?` | discovered/metadata_only不能充当已读全文；read_scope由parser_version派生：v1=legacy_page_unverified、v2=author_narrative_subset（未显式标引他人内容的叙述子集，不是完整全文或语义归属审查），SourceVersion沿用同一映射，旧快照不改写；来源URL不含user/pass/令牌；外部抓取经受控适配器，不接受任意内网URL |
| `EvidenceExcerpt` | `id:Id, source_id:Id, source_revision:Revision, text_digest:Digest, start:int, end:int, quote:ExactText(1000), page_number:int?, extraction:plain\|pdf_text\|ocr, extraction_review:unreviewed\|checked` | LF归一的不可变提取文本按Unicode字符计，`[start,end)`必须精确匹配quote；PDF页为1起，另核页映射；OCR未经核对不能冒充准确引文 |
| `ClaimEvidenceLink` | `claim_id:Id, excerpt_id:Id, relation:supports\|contradicts\|context\|insufficient, assessment:llm_inference\|human_review\|deterministic_check, rationale:Text(700)` | 主张/摘录属于同研究授权范围；模型推断不升级为人工或确定验证；引用匹配检查不证明语义支持正确 |
| `Claim` | `id:Id, research_id:Id, revision:Revision, text:Text(1200), level:hypothesis\|literature_supported\|computed_under_assumptions\|empirical_record, evidence_links:ClaimEvidenceLink[], check_ids:Id[], limitations:Text(400)[]` | level只能由应用校验所需引用后设置；empirical_record须有独立记录的实际观测/实验，B1合成对照不得设置 |

本候选中的Model/Formula/Method/Transfer/Source/Excerpt/Claim/Check/Report的id标识不可变对象版本；更新生成新id并增加revision，不能同id改内容。Research、Task和控制账本是明确可变例外，使用version/CAS。引用只指向具体版本id，必要的SourceVersion中revision必须与该记录一致。

来源原文件、提取文本、摘录与主张分别版本化。旧快照不因网页更新而被悄悄替换。元数据日期可缺失，不编造；无法访问、来源冲突、所需正文不可读都是合法研究结果。私密用户材料的外发选择由独立用户动作及 grant 约束，不由 LLM 推断同意。

`SourceRecord`、`ReportSnapshot`另含服务端`execution_mode:offline_probe|live`。离线来源/供应商替身产生的记录必须为offline_probe，不能改变标志后作真实研究证据；真实数学执行器的离线确定检查可作为对应软件/数学机制证据，但不支持外部来源已检索或现实系统已验证。

### 3.3 执行、结果与投影

| 对象 | 字段与类型 | 必须成立 |
| --- | --- | --- |
| `ResearchTask` | `id:Id, research_id:Id, input_revision:Revision, auth:AuthorizationSnapshot, execution:ExecutionState, phase:queued\|retrieval\|analysis\|synthesis, evidence:EvidenceState, stop_requested:bool, active_attempt:Revision, version:Revision, created_at:UtcTime, updated_at:UtcTime` | version 用于 CAS；不是把同一字段同时当用户态、worker态和结论可信度 |
| `TaskAttempt` | `task_id:Id, attempt:Revision, parent_attempt:Revision?, reason:initial\|explicit_retry\|recovery_after_reconcile, policy_revision:Text(64), input_digest:Digest, started_at:UtcTime?, ended_at:UtcTime?` | attempt只增，输入变更创建新task；旧attempt不覆盖当前结果 |
| `Step` | `id:Id, task_id:Id, attempt:Revision, kind:discover_sources\|fetch_source\|check_formula\|assess_evidence\|compose_report, state:StepState, version:Revision, input_digest:Digest, auth:AuthorizationSnapshot, reservation_id:Id?, dispatch_id:Id?, output_ref:Id?, error_code:ErrorCode?, started_at:UtcTime?, ended_at:UtcTime?` | 固定kind，不允许自由工具名；一个step/attempt最多一次外发，重试新step尝试且另预留 |
| `TaskEvent` | `task_id:Id, seq:int, attempt:Revision, kind:created\|step_started\|step_finished\|waiting\|stop_requested\|authorization_changed\|reconciling\|terminal, at:UtcTime, state_version:Revision, safe_code:Text(64)?` | seq按task事务内递增；日志/事件不含正文、身份、供应商响应或秘密；事件只是可重放事实，DB当前态仍为权威 |
| `CheckResult` | `id:Id, research_id:Id, input_revision:Revision, formula_ids:Id[], policy_revision:Text(64), check_kind:template\|dimensions\|canonical_transform\|bounded_numeric, status:passed\|failed\|inconclusive\|unsupported\|resource_limit, relation:algebraic_identity\|conditional_model_equivalence\|local_approximation\|partial_structure\|not_equivalent\|undetermined, assumption_refs:Text(64)[], transform_trace:Transform[], input_digest:Digest, output_digest:Digest?, sample_points:DecimalText[], tolerance:NumericTolerance?, limitations:Text(400)[]` | unsupported/inconclusive不投影为不等价；数值passed不能设algebraic_identity；现实变量映射另验 |
| `ReportSnapshot` | `id:Id, research_id:Id, input_revision:Revision, task_id:Id, attempt:Revision, status:notes\|qualified_report\|complete_for_scope, claim_ids:Id[], source_revisions:SourceVersion[], check_ids:Id[], evidence:EvidenceState, limitations:Text(400)[], digest:Digest, created_at:UtcTime` | 服务端一次绑定不可变引用；complete_for_scope表示已完成所声明研究范围，不是世界机制已证明 |
| `FollowupRecord` | `id:Id,research_id:Id,input_revision:Revision,plan_ref:Id,action_observed:Text(700),observation:Text(1200),observed_at:UtcTime,outcome:supports\|contradicts\|inconclusive,evidence_ids:Id[],created_at:UtcTime` | 用户回访是观测记录，不由此自动确认机制；plan_ref必须对应当前用户可读的迁移验证计划 |
| `ResearchView` | `id:Id, revision:Revision, current_revision:Revision, task_id:Id?, is_historical:bool, product_state:ProductState, detail:ViewDetail, evidence:EvidenceState, report_status:notes\|qualified_report\|complete_for_scope\|none, allowed_actions:Action[], research_version:Revision, task_version:Revision?, task_event_cursor:int, budget:TaskBudgetView` | 由服务端唯一投影函数生成；每次读取重核授权；前端不可按本地猜测提升完成度 |

默认view只展示当前revision的task；若新修订尚无task，返回task_id=null、queued及可用的start/revise动作，不把旧任务成功当新问题完成。读取历史任务须显式提供opaque task_id并按其input_revision投影，revision为所展示修订，current_revision为研究当前修订，is_historical据两者计算。新修订不隐式重试或取消已运行旧task，但不能把其结果绑定到新修订；一研究仍只允许一活跃task。

`ResearchView`还包含`execution_mode:offline_probe|live`；实际页面必须呈现offline_probe标识。`ExecutionPolicy={id:Id,revision:Text(64),mode:offline_probe|live,allowed_steps:Step.kind[],formula_policy_revision:Text(64),provider_bindings:PrivateBindingRef[],max_steps:int,max_sources:int,step_wall_ms:int}`由服务器登记，不能来自客户端/LLM；上限分别为64、20、60000。任务attempt绑定该policy快照，生产配置拒绝offline_probe供应商绑定，不因测试fixture能运行就默认放行live。

来源适配的初始资源边界：每次响应≤4 MiB、提取文本≤200,000字符、重定向≤3跳、每跳与实际连接地址均拒绝私网/本机/云元数据，超时≤60秒；不得只验URL字符串而允许DNS重绑定。B1仅HTML文本与可安全提取的PDF文本，不执行网页脚本、不自动OCR或绕验证码。抓取的允许host/连接器、parser版本和精确资源策略随ExecutionPolicy登记；未登记拒绝，不能让搜索结果自行扩大网络权限。实际网络取证仍在后续已获准的live适配范围验收。

D1 固定公共只读来源的窄策略不扩大上述上限：Crossref/PLOS 仅登记的 GET 目标、最多 4 次累计请求、零重定向与零自动重试、原响应及解压后各≤2 MiB、提取文本≤200,000字符、独立 wall deadline≤12秒。每次 GET 持同一跨进程 owner gate 至有界请求收尾，但不持数据库事务；取消可能真实遇到 `STORE_BUSY`，页面说明繁忙并按原操作核对，不能承诺立即撤回已发字节。父进程死亡时子进程、接收端及写入资格的实际窗口仍待原安全审查者验证；本策略文字不证明父死即停写。

TaskEvent.state_version指该task的version；View分别返回research_version和task_version，不混用root/step版本。

`ExecutionState={QUEUED,RUNNING,WAITING_EXTERNAL,CANCEL_REQUESTED,RECONCILING,COMPLETED,FAILED,CANCELLED,ACCESS_REVOKED}`。`StepState={PENDING,PREPARED,SENDING,AWAITING_RECEIPT,SUCCEEDED,FAILED,DISCARDED,UNKNOWN}`。`EvidenceState={UNASSESSED,COLLECTING,SCOPE_COMPLETE,INSUFFICIENT,CONFLICTED}`。`ProductState={queued,retrieving,analysing,synthesising,completed,insufficient,failed,cancelled}`；中文按PRD映射。`ViewDetail={normal,waiting_external,cancel_pending,reconciliation_required,budget_unverified,budget_exhausted,conflicting_evidence,partial_results,access_ended}`。

### 3.4 持久键与 schema 边界

新表采用独立`research_schema_version=1`迁移记录，在短写事务初始化；遇未知/更高版本拒绝启动该功能，不自动删表或降级。旧auth表结构与旧报告库不因读取新记录而隐式重建。最小表组及约束如下；具体DDL由B1实现受审，但不能省略这些约束。

| 表组 | 主键/唯一性/关联 |
| --- | --- |
| principals、controls、grants | 各id主键；account incarnation绑定唯一；grant关联principal与research，研究owner/epoch/version明确；原始auth binding只在服务器私有库 |
| revisions、models、formulas、methods、transfers、test_plans | 研究修订`(research_id,revision)`唯一；其余对象id/revision绑定；test_plan id有可验证关联；同研究引用不得越owner |
| tasks、attempts、steps、events、idempotency | attempt按`(task_id,attempt)`唯一；step id唯一；事件`(task_id,seq)`唯一；幂等key按主体incarnation/operation/研究作用域唯一，并绑定请求摘要 |
| sources、excerpts、claims、claim_links、checks、reports、followups | 不可变版本和外键；摘录绑定source revision/text digest，报告绑定实际存在的修订/证据/检查；删除内容有明确级联或受控清除 |
| funding_accounts、balance_snapshots、price_revisions、reservations、billing_receipts | reservation幂等唯一；dispatch唯一且最多一次发送；每reservation最终结算通过CAS仅一次；可验证provider receipt在account内去重；金额/币种/非负整数有持久约束 |

上述名称均加`research_`前缀；引用方向和删除规则须在迁移测试验证。账单与安全tombstone不对正文做ON DELETE CASCADE丢失对账，但内容删除后task/step关联应置空或转必要opaque收据，不保留正文/邮箱。deleted控制记录若保留，仅含防复活必要ID/epoch/状态与明确留存责任，不是可恢复用户研究；未知ID的迟到提交只能拒绝，禁止upsert。

### 3.5 Bounded-provider 的 typed 模型报告增量

本节只规定新版本候选，不把模型 JSON 当既有报告直接入库。`ModelReportCandidate-v1` 仅允许：`summary:Text(1000)`；`mechanisms`最多3项，每项为`label:Text(120),mechanism:Text(1200),variable_map:{source:Text(120),target:Text(120),rationale:Text(400)}[]`（≤12项）、`conditions:Text(400)[]`（≤5）、`nontransferable:Text(400)[]`（≤5）、`evidence_handles:ASCII32[]`（≤20）；`competing_explanations:Text(400)[]`（≤5）；`validation_plan={measurement:Text(700),outcome:Text(240),falsification:Text(400),stop_rule:Text(400)}`；`gaps:Text(400)[]`（≤12）。数组显式提供；无机制必须有缺口，引用仅当前获准包内 handles；完整候选≤32 KiB。额外字段、重复 key、NaN、越界、空／截断或非 JSON 均拒绝。模型不能设置 id/revision、证据级别、checked、执行状态、账务、工具、任意 URL 或自造引用；公式显示只是数据，不执行模型生成代码。

服务器经当前授权、严格 schema 和引用校验后，生成不可变 `ModelReportRecord`，绑定研究／输入 revision+digest、task/attempt、实际 dispatch、模型声明版本、候选 schema、usage/cost observation refs、内容摘要和时间。逐项映射为服务器生成的 `Claim`，模型推断仅 `hypothesis`，证据关系标 `llm_inference`／未审；精确 hash、Unicode `[start,end)` 和短引匹配只证引用准确，不证语义支持。checked／假设下计算只能关联真实 D2 同研究同修订、明确 policy／公式版本的检查记录，数值 passed 不升级恒等或现实有效；不能由模型提供一个 check id 或布尔值自授资格。只继承该实际检查的状态、结果与范围，failed/inconclusive/unsupported 如实保留，不能用一项量纲 passed 标任意模型内容“已算”。

再映射到服务器 `ReportSnapshot` 的 claim/source/check 引用与当前证据状态。首个 U1 方法证据子链默认 `qualified_report + INSUFFICIENT`，不因一次模型返回就宣称完整机制、统计或 U2 曲线已满足。市场机制不硬塞三 Family 的 ModelRecord/TransferProposal；条件化迁移内容先作为受控假设保留。D1 `EvidenceReport` 的 notes/INSUFFICIENT/model_analysis_ran=false 类型保持不变，不重命名为模型报告；新记录的“模型已运行”仅由实际调用观测设置，也不是“机制已验证”。

公共 RecordKind 不扩。新版本可在现有 `reports` DTO 中增加明确 schema 标记的白名单假设 sections（机制、变量、条件、竞争解释、验证计划与 claim/citation refs），由正式 owner 审定投影；不直接序列化 ModelReportRecord、原模型响应或执行／计费控制对象。旧版本 fixture 与 notes DTO 保持旧解析语义，未完成版本迁移和消费者验收就不发布新格式。页面分别显示假设、来源支持范围、真实检查与缺口，不把引用存在当支持审查通过。

完整外发输入包必须由正式授权来源读取接口生成，绑定摘要／短摘录／必要署名、source/excerpt具体版本、hash/offset、当前 principal/grant/epoch、研究修订与批准 plan，以及最终 request digest。`may_send_to_provider` 与 cache/display/export 分别核，任何一项都不能推导另一项；首发只选同时获准外发与展示的短摘录，避免把仅外发许可当展示许可。每摘录仍≤20词／1000字符，首发完整模板、schema示例与包合计≤16 KiB。不得私读 `_get`、擅抓模型 URL、发全文或扩大私密输入；permit 同时绑定完整包、固定 provider/model、price revision、token 上界，send 前再核，迟到提交再核授权与 CAS。

## 4 生命周期、幂等与用户状态

### 4.1 操作和事务顺序

候选正式导出命名：`ResearchService.create/revise/start/cancel/retry/resume/request_reconciliation/view/events`；`ResearchStore.transaction`；`AuthorizationGate.check/claim/revoke/delete`；`BudgetLedger.reserve/mark_dispatch/settle/mark_unknown/reconcile`；`FormulaChecker.check`；`ResearchRunner.run_next/recover`；`ResearchProjection.build`。建议放在 `web/backend/research/`，旧路由只做适配；这些命名源于设计基线，实际存在、受审及冻结状态须按当前实现 SHA 与消费者证据核对，不由本文代签。

外部API候选：`POST /api/research`，`POST /api/research/{id}/revisions`，`POST /api/research/{id}/tasks`，`POST /api/research/{id}/formula-checks`，`POST /api/research/{id}/cancel`，`POST /api/research/{id}/retry`，`POST /api/research/{id}/resume`，`POST /api/research/{id}/reconcile`，`GET /api/research/{id}`，`GET /api/research/{id}/events?task_id=<Id>&after_seq=N`。只在已验证上下文解析owner，正文不能设置auth、epoch、费用实值或执行终态。查询参数仅事件游标等非敏感标量；B1不新增公开分享API。

同一正式服务另导出`list/export/record_followup`，对应`GET /api/research`（只按当前owner分页）、`POST /api/research/{id}/export`和`POST /api/research/{id}/followups`。resume仅恢复尚未结束、已对账且资格/预算有效的task，不复活取消或撤权任务；reconcile仅登记本地对账请求，不接受客户端账单/金额，也不自动外发收费查询。列表游标为服务器范围绑定的opaque cursor，事件每页最多200项并按seq续读；不得用邮箱或问题正文作为游标。

| 请求类型 | 客户端字段 | 约束 |
| --- | --- | --- |
| `ProblemInput` | `entry,original_input,objective,summary,variables,constraints,unknowns,confirmed` | 类型同ProblemRevision；不能传revision/digest/owner |
| `CreateResearchRequest` / `RevisionRequest` | `{problem:ProblemInput}` / `{expected_revision:Revision,problem:ProblemInput}` | 相同幂等key返回同结果；revision由服务器生成 |
| `StartTaskRequest` | `input_revision:Revision,expected_research_version:Revision,mode:phenomenon\|formula\|research,selected_candidate:LegacyRef?,approval_ref:Id?` | D1 live 免费 GET 必须引用下述持久批准；所选候选必须属于本研究可用集合；按服务端固定policy生成计划，不接受工具/供应商/费用覆盖；一研究仅一活跃task，冲突409；字段接线须正式 owner 审定 schema revision，本文不直接发布接口 |
| `FormulaInput` / `FormulaCheckRequest` | FormulaInput含`family,template_id,original_display,expression,symbols,assumptions,initial_conditions,boundary_conditions,source_ids`；请求为`{input_revision,left:FormulaInput,right:FormulaInput?,comparison_scope:expression\|equation_form\|initial_value_problem,requested_checks:CheckKind[],sample_points:DecimalText[]}` | check kind限template/dimensions/canonical_transform/bounded_numeric，不重复；有双侧才检查对应，单侧仅模板/量纲；source_ids须已获授权；同一方程形式不自动推出初值问题等价 |
| `TaskVersionRequest` / `RetryRequest` | `{task_id,expected_task_version}` / `{task_id,expected_task_version,failed_attempt}` | TaskVersionRequest用于cancel/resume/reconcile；task_id必须属于该研究；retry仅明确失败且对账闭合后允许，不能为UNKNOWN换key重发 |
| `FollowupRequest` | `input_revision,plan_ref,action_observed,observation,observed_at,outcome,evidence_ids` | 对应FollowupRecord；所有引用同研究/授权范围；回访不触发自动付费 |

FormulaInput中的assumptions只接受`AssumptionInput={id:Text(64),statement:Text(400),declared_satisfied:bool?,proposed_evidence_ids:Id[]}`，初/边界条件只接受`ConditionInput={id:Text(64),kind:initial|boundary|domain,statement:Text(400),declared_satisfied:bool?}`。服务器映射为declared或unknown，条件false不符合对应模板前提；客户端/LLM不能直接传supported/contradicted/reviewed。这些状态只能来自受控检查/评审记录，记录评估方法，不将声明或同域引用存在当科学事实。

**D1 preview 与批准／start 绑定。** Preview 仅为无 task 的本地 DTO，不创建执行记录、来源证据或外发资格，不消耗请求次数；显示的输入修订、关键词和计划摘要不自行成为批准。正式 start 须引用同 auth DB 中由受审显式确认入口形成的持久 `approval_ref`，其规范记录至少绑定主体 incarnation/epoch、研究、输入 revision+digest、plan digest、policy revision、固定 max_requests=4、获准外发关键词摘要及其 digest、批准版本与当前有效状态。批准须来自当前有权主体的明确确认，或已有授权内的后续计划明确决定并留记录，不能由 LLM、旧批准或“执行已闭合”自行推导。这是产品内对研究范围的确认，不新增宿主审批卡；确认入口或持久批准尚未实现时，明确拒绝 live start。

非幂等重放的 start 在一个事务内重核上述完整批准、当前身份与输入版本，服务端重建规范计划核摘要，再依次绑定 grant→task/attempt/steps→正式 plan 与批准消费记录→幂等结果，任一失败全部回滚，不留下半个正式计划或外发资格。请求仅引用批准，不接受旧 preview、客户端／LLM 覆盖的工具、provider、URL、价格或请求上限；每次 send 仍重核当前批准绑定、grant/epoch、task/step/version、stop 和累计 quota。原 key 的相同请求仅在当前授权允许后回读既有 task／结果引用与当前投影，不再次消费批准或请求次数；不同正文冲突，终结任务不因旧 key 或旧批准重启。

`Research`控制行的`version:Revision`在每次可见内容或current_revision/ownership/lifecycle改变时事务内递增；Task自身version另计，View分别返回research_version与task_version；StartTaskRequest的expected_research_version与其做CAS。读取/view/export在一致读事务中核授权与投影，避免“先验权限、后拿新owner内容”。列表与事件同样执行逐对象授权。

所有POST带 `Idempotency-Key`（服务端范围内 `1..128` ASCII安全字符），作用域为 `(principal incarnation, operation, research_id?)`；持久保存请求规范摘要与结果引用。相同key+相同请求返回原结果，不再次生成/预留；同key不同正文409。删除/撤权后旧key不返回私有结果，只允许返回泛化失效响应。网络返回未知时先查原key状态，不用新key重发。未结操作在当前主体 incarnation 与研究授权范围内，按规范外发输入 fingerprint、step 语义及规范 target 持久阻重，不能用新 task/attempt/key/approval 或 policy 标签绕过；输入修订与这些身份另作审计绑定，不以改编号抹去同一外发操作。收费／可能收费操作继续关联 reservation，只有原收费对账规则允许后才能新发；固定免费只读 GET 仅有下述新观测例外，不是重放原 dispatch。

1. 创建/修改：同DB事务验证当前身份、owner及expected_revision，写不可变修订、控制version和幂等结果。确认标志不替代观测证据。
2. 发起：同事务验证grant、已确认输入及policy，生成task/attempt和步骤计划；没有可靠余额只允许不收费步骤，不自动换供应商。收费步骤在外发前完成第6节预留。
3. 执行：worker以SQLite条件更新认领PENDING步骤；记录attempt/version后才读取必要正文；事务不跨完整网络等待。事务成功不表示已调用供应商。
4. 外发：取得跨进程owner gate，再在短事务重核auth/epoch、stop和预算，绑定dispatch_id并将step置SENDING；在同gate内消费一次性外发资格并启动受控transport。未经消费且撤权的票失效；已启动的请求属于在途，不能承诺撤回网络字节或远端收费。自动HTTP重试关闭。
5. 提交：结果先当不可信输入校验；同DB事务重新核owner/epoch、task active_attempt、step/version和stop，才保存证据/检查/报告并更新事件。条件不符则DISCARDED，不重新创建研究资产；必要计费收据走独立结算路径。
6. 恢复：PENDING/PREPARED且确证未进入SENDING可重获资格；SENDING/AWAITING_RECEIPT/UNKNOWN先RECONCILING，不能盲重放。已SUCCEEDED输出引用可重投影，不重新收费或改成新证据。

**固定免费只读 GET 的未知结果与新观测。** 分类由服务器受审 operation/固定 executor 策略决定，仅限已确认无收费、无认证计费副作用的公共只读 GET；客户端、LLM、缺少 key、HTTP 方法或自称免费均不能决定分类。任一收费／可能收费／分类不明调用不适用本例外，Money UNKNOWN 仍 held，既有对账、取消及禁重发规则不变；不制造零金额 fixture 账户替代控制。

原免费 dispatch 的 `outcome=UNKNOWN` 与执行闭合分开持久记录。仅当应用以受审固定 executor 的实际证据确认原执行组全部收尾、发送／接收通道和旧写入资格已关闭，且迟到正文提交被持久 gate/CAS 拒绝，才可写 `execution_closed` 及证据 ref、原 dispatch/fingerprint、executor/policy 版本与闭合时间。等待时长、单个 PID 不存在、lease 超时、取消／终结标记、新批准或人工改 true 都不构成闭合证明；父死遗留窗口未验或任何证据缺口时，继续拒绝该未结操作的新 GET。标记闭合后，原 dispatch 也不能以迟到正文变成功或恢复任务。

应用核实闭合后，原任务可按明确的失败／取消原因收束，原 step/outcome 仍 UNKNOWN，不伪造 FAILED/SUCCEEDED 的远端结果。当前有效的新显式批准及后续计划方可创建**关联原 dispatch 的新 observation、新 dispatch 和新 acquiredAt**，重新执行授权、计划、阻重及 quota 检查；已终结旧任务不复活。新观测保存原 dispatch/批准/来源版本关联，旧事实与旧时间不覆盖。请求计数在同一观测延续链累计，旧 UNKNOWN 已消耗次数不释放，新 task/attempt/key/approval 不重置 max4；累计已满则拒绝，不能因未取得正文推断旧请求未发生。此路径不是自动 retry、旧结果恢复或原请求成功的证据。

`ResearchService.cancel`在RECONCILING同样可用，不依赖余额已核、供应商可用或最终费用收据。它与外发票消费使用同一跨进程owner gate排序，在同一短DB事务中核授权/expected_task_version，原子保存`stop_requested=true`、取消状态、递增version/事件并撤销未消费的外发票。取消先提交则后续外发消费失败；外发已先启动则只属于在途，结果不能再写研究正文。应用后续执行被持久阻断后可转CANCELLED，无需等待账务已知；SENT/UNKNOWN的reservation仍保持UNKNOWN及held，仅按确证结算或未收费依据处理，不能因取消释放。迟到账务只更新必要收据/账本，核`stop_requested`和终态后不得恢复RUNNING、重派步骤或追加正文；未取消且明确对账完成的任务才可按原规则恢复。

同一研究按version做乐观并发，重复worker靠持久CAS拒绝；锁过期不证明远端没执行。旧attempt迟到只能补其计费收据，不能更新当前候选。DB锁忙返回明确可重试的存储错误，但不得把“重试事务”扩展成“重试外部调用”。

### 4.2 唯一投影及下一动作

投影优先级：先授权，再撤销/取消意图及费用未知，再执行终态，再阶段与证据。各阶段成功只推进步骤，不能前端自行标整体完成。

| 当前事实 | 用户产品态 / detail | 证据与报告 | 允许下一动作 |
| --- | --- | --- | --- |
| QUEUED | queued / normal | UNASSESSED；none | view、cancel |
| RUNNING，phase=retrieval/analysis/synthesis | retrieving/analysing/synthesising / normal | COLLECTING或已有部分；notes | view、cancel |
| WAITING_EXTERNAL | 保持当前phase / waiting_external | 已取得证据保持；notes | view、cancel、refresh；不提供retry |
| CANCEL_REQUESTED，有在途请求 | 保持当前phase / cancel_pending | 部分证据；notes | view、refresh；不派发新步、不提供retry |
| RECONCILING，未证明原动作未发生 | 保持当前phase / reconciliation_required | 已有证据保持；notes | view、cancel、refresh、request_reconciliation；不提供retry/resume外发 |
| COMPLETED + SCOPE_COMPLETE +已绑定完整报告、无未知费用/外发 | completed / normal | complete_for_scope | view、revise、export、record_followup |
| COMPLETED + CONFLICTED +条件化报告、无未知费用/外发 | completed / conflicting_evidence | qualified_report；冲突与未决必须可见 | view、revise、export、record_followup |
| COMPLETED + INSUFFICIENT、无未知费用/外发 | insufficient / partial_results | qualified_report或notes；保留检索范围 | view、revise；仅已对账且显式新计划才可start |
| FAILED，原步骤明确失败且全部费用已结清 | failed / partial_results | 已有证据；notes | view；`retry`须服务端重新验证资格/预算并新attempt |
| FAILED但任一费用/动作未知 | failed / reconciliation_required | 已有证据；notes | view、request_reconciliation；禁止无条件retry |
| CANCELLED且已阻断应用后续步骤，包括从RECONCILING取消 | cancelled；未知费用时detail=reconciliation_required | 部分结果仅仍有权限者可见 | view、refresh、request_reconciliation；未知费用只对账，不自动释放、重发或恢复执行 |
| 固定免费 GET 的原 outcome UNKNOWN，已凭证据 execution_closed，原 task 已 FAILED/CANCELLED | 保留失败／取消及“旧读取结果未知、执行已闭合”的说明，不冒费用已对账或原请求成功 | 原快照与 UNKNOWN 不改写，新观测有独立关联／时间 | 当前授权下 view、revise；仅满足新持久批准、累计 quota 等前置时 start 新计划，不对旧 task 提供 retry/resume；仍有收费未知时不得借此放行收费 |
| 余额未核/不足，未发收费步 | 保持phase / budget_unverified或budget_exhausted | 已有证据；notes | view、cancel；核实后服务端再判resume，不默认可重试 |
| ACCESS_REVOKED/主体删除/非owner | 私有视图不返回；已知当前用户失效可显示access_ended | 不返回标题/正文/来源/报告 | sign_in或返回我的研究；不能retry、export或恢复分享 |

`allowed_actions`由服务端输出，动作实际提交时再次检查，不能把按钮隐藏当权限控制。取消完成仅表示本应用不再产生研究写入与新步骤；在途收费仍可能待结算。重新开始与恢复是不同操作，未知旧动作对账后才能决定哪一种安全。

### 4.3 对外输出白名单

创建/修订/任务操作返回`{research_id:Id,task_id:Id?,view:ResearchView}`；公式检查返回`{check_id:Id,view:ResearchView}`。GET研究返回`{view:ResearchView,problem:ProblemRevision?,record_counts:RecordKind到非负整数的映射}`，不序列化Task.auth、Principal、Grant、ExecutionPolicy私有绑定、FundingAccount、BalanceSnapshot或原始供应商对象。

供实际页面读取的候选接口`GET /api/research/{id}/records?kind=<RecordKind>&cursor=<opaque>`只允许`RecordKind={models,formulas,methods,transfers,checks,sources,excerpts,claims,reports,followups}`，返回对应已声明对象的`{items:[],next_cursor:Text(512)?}`；source输出排除provider_ref和私有存储定位。每页最多20项、响应最多512 KiB，下一页由cursor显式续读，不静默截断正文或省略证据。kind按固定路由映射，不拼接任意SQL表名。cursor绑定主体incarnation、研究、kind与research_version，版本变化409后重新读取当前视图；每页仍重新核当前权限。

D1 内部 `snapshots` 映射为现有公共 records 的 `sources` DTO，不新增 `snapshots/plans/executions` 公共 RecordKind；内部 plan/execution 只供受控流程使用。映射使用 `SourceRecord.id=source_id,revision=source_revision`，保留标题、规范公开来源 URL、原字节 content_digest、真实访问范围／状态、许可说明及原取得时间；不序列化 snapshot 原始缓存、全文、提取全文、发现响应、批准／外发关键词、私有定位或执行控制对象。缓存、摘录展示和导出分别核对应许可与当前 owner；不能因缓存可读或短摘录就推定允许展示／导出。历史导入／缓存沿用原版本与原时间，在现有 scope/说明中明确本次未联网，不把 fixture 或旧观测改为本次 live；若已审 DTO 无法准确表达，返回明确失败／不足，不伪造映射。

需要缓存重放时只能经已审的授权读取接口，执行同样的 owner/incarnation、输入修订／版本及许可检查；不私调 repository `_get`、操纵 adapter 状态或重新标 live 绕过缺失挂点。最小阶段该接口或映射未实现即明确不足／不可用，不能以泄露全文、私读缓存或暗发新 GET 补齐页面。上述分页／响应 cap 与 cursor 版本绑定同样适用于 D1 来源。

### 4.4 允许转换与终态

| 状态维度 | 允许边与必要条件 |
| --- | --- |
| Task执行 | QUEUED→RUNNING/CANCELLED/ACCESS_REVOKED；RUNNING→WAITING_EXTERNAL/CANCEL_REQUESTED/RECONCILING/COMPLETED/FAILED/ACCESS_REVOKED；WAITING_EXTERNAL→RUNNING/CANCEL_REQUESTED/RECONCILING/FAILED/ACCESS_REVOKED；CANCEL_REQUESTED→CANCELLED/RECONCILING/ACCESS_REVOKED且stop_requested保持true；RECONCILING可不等待对账直接因cancel→CANCEL_REQUESTED，应用停止后→CANCELLED，或因撤权→ACCESS_REVOKED；stop_requested=false且明确对账后才可→RUNNING/FAILED；固定免费 GET 按§4.1执行闭合失败例外仅可→FAILED，不可据此→RUNNING；COMPLETED/CANCELLED/ACCESS_REVOKED为不可继续的终态，FAILED通常仅经显式retry创建新attempt，免费闭合未知的新观测必须另建合法任务而非复活原任务 |
| Step执行 | PENDING→PREPARED/FAILED/DISCARDED；PREPARED→SENDING/FAILED/DISCARDED；SENDING→AWAITING_RECEIPT/SUCCEEDED/FAILED/UNKNOWN/DISCARDED；AWAITING_RECEIPT→SUCCEEDED/FAILED/UNKNOWN/DISCARDED；UNKNOWN须对账后才→SUCCEEDED（确有可恢复输出且授权仍有效）/FAILED/DISCARDED；固定免费 GET 的 execution_closed 不改变原 UNKNOWN，只允许另经新批准产生关联的新观测；SENDING/AWAITING_RECEIPT只有明确结果及费用结论时才可直接FAILED，否则UNKNOWN；终态不再外发，迟到费用单独对账 |
| 证据完成度 | UNASSESSED→COLLECTING；COLLECTING可依据真实记录→SCOPE_COMPLETE/INSUFFICIENT/CONFLICTED；SCOPE_COMPLETE/INSUFFICIENT/CONFLICTED改变须新报告版本或明确新attempt，保留旧快照；禁止只因Step成功升级 |
| Reservation | HELD→SENT或RELEASED（确证未发送）；SENT→UNKNOWN或SETTLED；UNKNOWN→SETTLED或RELEASED（有确证未收费）；SETTLED/RELEASED不能重发或重复结算。SENT表示本地已进入可能外发区间，不证明远端接受，需收据确认 |

所有边均有当前version、attempt、auth与必要预算条件；未列边拒绝。Task完成还要求所有必需步骤合法终结、报告已绑定且不存在未知外发/待结算收费，证据不能为UNASSESSED/COLLECTING；无结果可COMPLETED+INSUFFICIENT，冲突可条件化完成。取消终态允许仅账务观察仍在途，不能再写研究正文。跨账户/删除失效优先级高于这些正常边，不能通过恢复重获旧授权。

固定免费 GET 已核 execution_closed 的旧任务仅可依明确闭合失败／取消原因收束，不据此记 COMPLETED/SCOPE_COMPLETE；原 UNKNOWN 保留为历史未知，新观测另绑定当前合法任务。此闭合例外不改变收费 reservation 状态，也不把仍未闭合的免费外发排除出阻重；未实现和未实测的闭合机制不能作为允许转换依据。

## 5 三模型家族的有限公式允许表

### 5.1 AST、单位和资源

允许节点仅：`const{value:DecimalText}`、`symbol{id:ASCII32}`、`neg{arg}`、二元`add/sub/mul/div{left,right}`、`pow_int{base,exponent:-2|-1|0|1|2}`、`exp{arg}`、`derivative{state_symbol,time_symbol,order:1}`、根节点`eq{left,right}`。JSON仅有这些key；不允许属性、下标、任意函数调用、积分、二阶导数、字符串代码、模块名、文件/网络操作和循环；exp只是允许模板内的内置节点。derivative只能作为允许模板中的形式节点，不能调用任意求导器。

AST合法还不够：必须匹配下一表的模板，经过允许变换后仍在相同模型域内。公式display/LaTeX只展示；自然语言/LLM提出的AST经过同一解析，不获额外权限。未知记号返回澄清或unsupported，不能用 `eval` 或动态生成程序兜底。

`UnitId`候选固定为 `one,count,s,workday,count_per_s,count_per_workday,inverse_s,inverse_workday,K,J_per_K,K_per_W,V,A,ohm,F`；单位表含固定量纲向量与time_basis。`workday`无默认秒数，只能在同一明确工作日边界内运算，不默认为8小时或日历日。热/电家族使用s；跨物理单位的状态映射先无量纲化，不声称K=V。未登记单位返回unsupported，不由LLM发明换算。

量纲顺序固定为`(质量M,长度L,时间T,电流I,温度Θ)`，每项整数指数；输入单位的精确表如下。count是无量纲计数标签，不另加一个物理维度，否则`1/(mu-lambda)`会被错误判为时间/计数；计数、比值、到达/服务率的语义仍按模板角色检查，不能把所有无量纲量任意互换。

| UnitId | 量纲向量 | 附加约束 |
| --- | --- | --- |
| one / count | `(0,0,0,0,0)` | 分别为纯比值/计数，按模板角色核标签 |
| s / workday | `(0,0,1,0,0)` | time_basis分别为s/workday；无显式换算不得混用 |
| count_per_s / inverse_s | `(0,0,-1,0,0)` | time_basis=s；前者为计数率，后者为恢复系数 |
| count_per_workday / inverse_workday | `(0,0,-1,0,0)` | time_basis=workday；角色约束同上 |
| K | `(0,0,0,0,1)` | 模板使用温差，不把摄氏绝对数直接代入 |
| J_per_K | `(1,2,-2,0,-1)` | 热容 |
| K_per_W | `(-1,-2,3,0,1)` | 热阻 |
| V | `(1,2,-3,-1,0)` | 电压 |
| A | `(0,0,0,1,0)` | 电流 |
| ohm | `(1,2,-3,-2,0)` | 电阻 |
| F | `(-1,-2,4,2,0)` | 电容 |

中间表达式按允许节点加减指数，指数绝对值不得超过8；加减/等式两侧量纲和time_basis须一致。归一化状态与归一时间的unit均为one。AST中的ASCII别名须经显式双射映射到各模板表列出的规范角色，不能通过增加未声明符号绕过模板。

候选资源策略 `formula-policy-v1`：每侧display≤2048字符，AST≤128节点、深度≤16、符号≤12、条件≤24；数值点≤256。十进制常数按基础类型限制；精确有理中间数≤256 bit，结果绝对值≤`10^12`；归一时间点在`[0,20]`，衰减exp参数在`[-100,0]`。单次检查CPU≤1秒、wall≤2秒、额外进程内存≤128 MiB；真正硬限制由受控计算worker实现与探针验证，文字值不是隔离保证。超界输出resource_limit，不以截断/溢出结果给结论。

只允许常数折叠、加乘交换/结合、变量双射改名、代入已知恒定参数、对已证非零项同除/同乘、声明的正时间尺度变换、有效状态尺度归一；每步记录输入/输出摘要与先决条件。禁止无条件约分可能为零的项、改变导数阶数、丢弃输入/边界或把经验相关变成因果。

### 5.2 模板与定义域

| Family / TemplateId | 允许公式与符号 | 定义域与允许检查 |
| --- | --- | --- |
| `queue_flow / little` | `l=lambda*w`；l:count，lambda:count_per_time，w:time，同一time_basis | l≥0、lambda≥0、w≥0；有限长期均值、有效到达与系统边界一致。检查量纲/指定数值关系；lambda=0时不能通过除法求w；不据关系断因果或优化方案 |
| `queue_flow / mm1` | `rho=lambda/mu`；`w=1/(mu-lambda)`；`wq=lambda/(mu*(mu-lambda))`；`l=lambda*w`；`lq=lambda*wq` | lambda≥0、mu>0且lambda<mu；声明单服务者、泊松到达、独立指数服务、FCFS、无限队列、稳定及无重入/批量。只按该假设模型演算；lambda≥mu拒绝稳态公式，不能返回负等待时间 |
| `first_order_storage / passive_decay` | `c*d(x)/dt=-x/r`，`tau=r*c`，`x=x0*exp(-t/tau)`；热侧x:K、c:J_per_K、r:K_per_W；电侧x:V、c:F、r:ohm | c>0、r>0、t≥0，x0允许0或负值；恒参数、无外部输入、线性耗散；热侧环境恒定和集总状态，电侧理想孤立RC。允许模板/量纲、正时间尺度与变量映射、限定解析/数值对照 |
| `local_recovery / linear_stable` | `d(delta)/dt=-k*delta`，`tau=1/k`，`delta=delta0*exp(-k*t)`；delta:one/K/V之一、k:inverse_s、t:s | k>0、t≥0，delta0允许0；稳定平衡附近的小扰动、局部近线性、采样/外驱动边界明确。只能输出局部模型的恢复时间与条件化对应，不能推出临界日期、普适阈值或投资预测 |

`time`在queue中仅为s或workday且双侧一致。参数均须有限，违反定义域返回`failed/precondition`或`inconclusive`（条件未知）；它不是宣称其他物理系统不存在。例如主动负阻或不稳定模型是本family不支持，不是一般数学错误。

`passive_decay`允许x0=0的未归一方程与恒零解；此时不得除以x0。仅x0≠0时允许u=x/x0、s=t/tau，得到`du/ds=-u,u(0)=1`。初值不同但都非零时，可比较各自归一响应；不能说原幅值/物理状态相等。`linear_stable`可映到同一标准式，但其有效范围仍为局部；不能丢掉范围后提升成全局模型同构。

本候选不计算任意队列网络、不求一般非线性方程、不拟合随机过程，也不将OU方差/相关性公式自动列入允许表；临界减速研究可以查文献并提出这些待检验关系，新增计算需单独变更policy和探针。给定模板的方程比对与来源方法/现实适配分开记录。

符号恒等检查采用有限变换及精确有理数；限定数值对照候选容差 `abs(a-b)≤1e-10+1e-8*max(abs(a),abs(b))`，记录具体方法和容差版本，只支持该样本域的数值结论。容差是技术比较策略，不是科学置信度，也不能靠调大容差让反例通过。

## 6 持久预算、未知结果与余额变化

### 6.1 计费对象

| 对象 | 必填字段 | 不变量 |
| --- | --- | --- |
| `FundingAccount` | `id:Id, provider:Text(64), mode:fixture\|live, private_account_ref:PrivateBindingRef, currency:USD\|CNY, scale:int, funding_epoch:Epoch, verified_cap:Money, settled:Money, held:Money, status:unverified\|active\|reconciling\|blocked, snapshot_id:Id?, version:Revision` | `verified_cap`来自已批准的现有预充值及可控计费边界，不是应用任意新增总预算；不自动把充值/余额增长当新增授权；offline_probe只可绑定fixture，live只可绑定经核live账户 |
| `BalanceSnapshot` | `id:Id, account_id:Id, observed_balance:Money, observed_at:UtcTime, local_settlement_cursor:int, pricing_revision:Text(64), hard_prepaid_verified:bool, auto_topup_off:bool, postpaid_off:bool, exclusive_allocation_verified:bool, receipt_digest:Digest` | 私有控制面；无凭据值和账单正文；公共ResearchView不暴露全账户余额/账号 |
| `PriceRevision` | `id:Text(64), account_id:Id, model_or_tool:Text(120), currency, scale:int, input_per_million_units:int, output_per_million_units:int, fixed_call_units:int, rounding:ceil_total\|ceil_components, max_input_tokens:int, max_billed_output_tokens:int, valid_until:UtcTime` | 费率非负整数；输出上限包含供应商可计费隐藏/推理量，不能只计可见文本；工具收费也需可上界 |
| `Reservation` | `id:Id, account_id:Id, task_id:Id?, step_id:Id?, funding_epoch:Epoch, price_revision:Text(64), idempotency_digest:Digest, max_cost:Money, settled_cost:Money?, status:HELD\|SENT\|UNKNOWN\|SETTLED\|RELEASED, dispatch_id:Id?, provider_request_ref:Text(200)?, version:Revision, created_at:UtcTime, updated_at:UtcTime` | money同币种/scale；只有确证未发送/未收费或完整结算差额才能释放；超时/取消/撤权不等于免费 |
| `BillingReceipt` | `id:Id, reservation_id:Id, provider_receipt_ref:Text(200)?, kind:charge\|refund, original_receipt_id:Id?, final:bool, observed_cost:Money?, input_tokens:int?, billed_output_tokens:int?, outcome:known\|unknown\|confirmed_not_sent\|confirmed_not_charged, received_at:UtcTime, digest:Digest` | 相同收据只处理一次；非final仅保存观测不释放预留；缺usage/费用不能推断0；删除研究后只留必要provider/account/reservation/金额与收据摘要，不留正文/邮箱/分享信息 |

所有账户/价格/余额/receipt使用相同固定scale。接入前依据批准供应商实际小数精度选scale；超出可精确表示范围时停止该适配器，不默默舍入余额或实际结算。异常返回的精度原值以受限十进制诊断收据保存并冻结账户，不能截断后宣称已精确结算；变更scale须新版本与迁移验收。离线探针固定scale=6，因此例中单位为微单位，不是所有live账户都固定六位。

统一以整数向上取整预留：`R = ceil((Imax*input_rate + Omax*output_rate)/1_000_000) + fixed_call`，若供应商分项取整则按其更保守规则计。无法上界的搜索、重试、隐藏tokens或收费工具不启用该适配器。B1离线费率为明确测试替身，不写成真实供应商价格。

### 6.2 原子预留与结算

中间乘加采用有界精确整数，最终amount_units必须可存入63位非负范围；溢出拒绝外发，不截断。

同一FundingAccount跨进程共用SQLite记录。`BEGIN IMMEDIATE`内核account active、funding_epoch/price版本、snapshot新鲜度，再检验`settled+held+R≤verified_cap`并插入唯一reservation、增加held，成功后才允许mark_dispatch。幂等重入返回同reservation，不再增加held。超额拒绝时不调用供应商。

初始snapshot候选TTL为60秒，实际供应商接入前由owner按余额与账户隔离能力核准。后续snapshot下降或发现外部消费/价格漂移时转reconciling/blocked，停止新增收费外发；不能通过调高本地cap掩盖。已发送费用按事实记账。若共享账户存在不受控外部消费，必须有经验证的供应商硬预付费/独立额度边界；仅定时查余额不足以保证并发硬上限，不能放行真实适配器。

新预留还受最新供应商可用余额的保守约束：从snapshot余额扣除当前未结预留与snapshot后已知本地结算再比较R，允许保守重复扣除，不允许高估可用额。若账单入账时点不可区分，先停新预留进行对账。首笔已验证额度、此后实际支出与已识别退款有明确funding_epoch及收据，不将新充值或促销额度自动加入本次上限。

结算同事务按唯一final receipt记录实际cost、从held减去原R、将cost计入settled，差额才释放。每reservation最多一个有效最终charge结算；refund只通过对账路径关联原charge处理，通过status/version CAS防止不同进程重复settle；供应商收据ref（有则用）在account内唯一并核dispatch绑定，无ref时按reservation+final内容摘要去重，不能把无来源自报金额作为可信结算。**实际cost>R或出现异常负/未知费用时先保存异常事实并冻结账户，不丢弃真实支出或静默截断到R。** 大于cap是适配器或上界失效，不能仍宣称硬预算已验。

SENT超时→UNKNOWN：R继续占用，任务不能无条件重试。只有供应商明确收据/查账或可证明本地从未发送才能reconcile；“时间久了”“网页已取消”“没有看到结果”都不是释放依据。用户账户/研究删除只切断内容访问，结算使用独立reservation引用，不复活研究记录。已知refund作为独立正金额反向收据记录（kind=refund、original_receipt_id必填），累计退款不得超过已核原收费，按原收据关联幂等反冲，不自动超出原授权funding边界。

### 6.3 全项目收费边界与旧接口桥接

Mentor已决定Phase本轮保留静态研究与冻结结果，未修复动态不启用，也不作为三核心能力的必要链路；主认证、私有旧记录和SSO兼容仍须保护。不能把整段`/phase`粗暴禁掉而破坏共享账户，也不能因旧页面仍可打开就返回HTTP 200伪动态交互。

本轮在固定基线只读定位的实际调用面如下。它是待闭合manifest输入，不是已完成技术隔离或全仓所有外部副作用的证明。

| 入口/消费者 | 实际到达的收费路径 | 本版设计处置 |
| --- | --- | --- |
| 主Ask与Analyze流 | `services/ask_orchestrator.py`的`_call_llm_once/_call_llm_stream`；`LLMService.stream_deep_analysis`；原始请求级`cost_ledger.charge`各只计一次 | 接统一BudgetGuard；每次实际调用及重试分别预留，原日计数只能保留为附加限流 |
| Search评估/重写、Mapping及Synthesize | `LLMService.assess_and_rewrite/generate_mapping/stream_mapping/synthesize_answer/stream_synthesize_answer`，经`api/search.py`、`mapping.py`、`synthesize.py` | 仅已批准的POST桥接到Guard；未接完的能力显式不可用，不由None/fallback伪装已执行 |
| 查询扩展、英译中 | `query_expansion.py`、`retrieval_pipeline.py`调用`llm_client.complete_json`；一次请求可能扩成多调用 | 每个分支属于同一上层执行/资金账户，各有call/reservation，输入与输出上限固定；缓存miss不绕预算 |
| KB英文展示 | `translation.py::_llm_translate_batch`直接HTTP；`api/phenomenon.py`的GET及Search可经translate_kb_item(s)隐式触发 | GET不再隐式产生收费；可读已审公开翻译缓存或原文并明确未翻译，生成另走批准POST；不复活已退役GET接口 |
| Method search/apply、stress、lint、diagnose | 四个service使用`llm_client.complete_json`多轮评估/生成；底层`complete_json/complete_text/stream_text`均直接HTTP | 有需求且已桥接的操作走Guard，其他明确停用；轮次、模型和重试不由旧默认值自动扩大 |
| Phase七个动态LLM路由 | `main.py`的POST `/phase/api/redteam`、`deep-report`、`analogy`、`analogy-detail`、`analogy-detail/stream`、`analogy/stream`、`memo/stream`；前四经`_phase_urlopen_json`，后三新建httpx client | 全部显式停用，在读取动态缓存/构建stream前拒绝；不靠缺key，不自动回退模型；静态冻结结果经单独读取路径呈现来源与日期 |
| MCP、旧CLI/包及生成脚本 | `mcp/server.py`转调主API；独立研究脚本/包可能自己调provider | MCP继承同一API admission，不凭调用来自MCP放行。未纳入Guard的脚本/包不进入服务运行/自动任务制品，不注入本项目live计费绑定；需要运行时另登记受控入口 |

在网页后端中，LLMService六个、llm_client三个、Ask两个和translation一个直接HTTP调用位置，加上main的一个urllib sink与三个stream sink，构成本轮定位的16个底层位置；同一sink可能服务多个路由/重试，不能按16作为唯一收费次数。HTML/SDK调用、别名和异步嵌套须由实现owner继续逐项核入口与实际sink。Phase waitlist的Buttondown转发、邮件、Stripe和其他网络操作另有副作用/权限分类，不误称LLM，也不因未计入本表就默认可执行。

共享正式导出增补`BudgetGuard.admit/prepare_call/dispatch/reconcile`、`LegacyBillingBridge.resolve`、`GuardedProviderTransport.send/stream`。`OperationRegistryEntry={id:Text(120),revision:Text(64),mode:disabled|read_only|guarded_paid,allowed_http_methods:GET|POST集合,price_binding:PrivateBindingRef?,max_calls:int,max_retries:int,cache_policy:disabled|public_artifact|private_scoped,output_policy:validated_result_only}`由服务端登记，默认disabled；mode、资金、模型/供应商/工具、次数上限不能由客户端或LLM改变。旧服务默认模型及fallback列表不是本轮已批准模型，不自动沿用。

每次调用需要私有`CallPermit={id:Id,dispatch_id:Id,operation_id:Text(120),operation_revision:Text(64),authorization:CallAuthorization,reservation_id:Id,provider_binding:PrivateBindingRef,price_revision:Text(64),input_digest:Digest,max_input_tokens:int,max_billed_output_tokens:int,expires_at:UtcTime,state:prepared|consumed|revoked}`。它由Guard事务创建、仅受控transport一次消费，并在消费时重新核身份、operation与reservation；普通Id或用户header不是permit。有效key但无permit、过期/重复permit、参数/模型/输入变化、非批准operation，一律在外发前拒绝。read_only操作不能取得收费permit。

`CallAuthorization`为已定义Research授权快照，或最小`LegacyAuthorizationSnapshot={principal_id:Id,principal_epoch:Epoch,auth_generation:Text(64)?,grant_id:Id,operation_id:Text(120),operation_revision:Text(64),request_digest:Digest}`。旧接口先由正式身份适配签发仅该操作的持久grant，仍使用相同Principal与跨进程gate；正文anon_id、API key tier或任意请求ID不能直接变成授权。旧调用无需为了账务自动保存用户问题正文或伪造Research记录，只留最小控制/摘要与收据。涉及旧私有资产的写入/分享若尚未接当前ownership和删除边界，则停用该写功能，不能把无research_id当绕过撤权的理由。

该grant的精确类型为`LegacyOperationGrant={id:Id,principal_id:Id,principal_epoch:Epoch,auth_generation:Text(64)?,operation_id:Text(120),operation_revision:Text(64),request_digest:Digest,status:active|revoked,expires_at:UtcTime}`，持久化于同一控制库，不能伪装成缺research_id的ResearchGrant。guarded_paid只允许POST；max_calls在1..16、max_retries在0..2，实际总调用不超过max_calls，重试上限不加在总数之外。permit候选有效期最长60秒，过期且确证未消费时先原子撤销票，再释放未发预留，不能仅凭时间到期释放可能已发送的费用。

幂等唯一键不使用nullable research_id直接做SQL UNIQUE：先形成非空`scope_key`，研究为`r:<research_id>`，研究创建为`new`，旧操作为`l:<operation_id>`，再以`(principal incarnation,operation,scope_key,key_digest)`建唯一约束。原请求摘要仍参与同key冲突检查；消除SQLite的NULL不互斥漏洞。

Bridge先核operation与当前身份，再查缓存；private缓存按principal incarnation、授权范围、输入修订/摘要、物料及policy版本隔离，不能跨账户或认领后继续用匿名旧缓存。public_artifact缓存仅限经审公开、与用户输入无关的版本化内容。合法缓存hit不新增收费，必须标明历史/缓存及原执行版本，不能改成刚运行的研究。cache miss只有批准POST才可生成；停用的动态路由即使有旧cache仍拒绝交互，静态历史读取另有明确入口。

Bridge/Guard拒绝不得被旧`except Exception`吞成None、success fallback、固定报告或自动换模型；流式请求在SSE响应头发出前完成admission。已开始的请求失败后仅发送受控失败/对账状态，不追加done成功；旧stream客户端断开不等于供应商未计费。供应商、HTTP库、SDK、模型修复和上层重试均禁止隐藏自动重发，每次额外外发须新permit及预留，旧结果未知时先对账。

不能只在路由加一层检查：`LLMService`、`llm_client`、Ask低层方法、translation及任何获准SDK入口都必须强制接受并验证Guard上下文，`_get_http_client`不能继续向业务提供可直连计费端点的裸client。运行制品的收费sink只允许在受控transport内；静态调用图/导入扫描与动态探针共同拒绝新增直接HTTP/SDK sink。扫描不是OS隔离，也不能单靠删除环境key证明边界。

本设计保证范围是**已审运行制品的正式应用路径**，不声称在任意Python/root代码执行或凭据泄漏后仍能阻止任意HTTP计费。如果无法闭合某路径、可加载扩展或外部自动任务的调用图，必须显式停用/排除，或先建立并独立验证凭据与出站隔离；不能文字登记成已受控。真实发布前所有可达收费callsite只有“已Guard覆盖并验收”或“实际拒绝/不在运行制品”两种放行状态。

### 6.4 Bounded-provider 保守占用增量

版本范围：本节以下原有全 U 占用规则为 `bounded_full_u_v1`；§6.4.1另定义 Mentor 已确认方向的 `bounded_usage_upper_v2`。策略在发送前由受审服务端选择并随 dispatch 不可变绑定；旧 fixture/final-receipt、v1及历史金额不自动迁入v2。文档增量不是实现或实费验收收据。

本节为新 accounting policy／schema 分支，不能静默套入旧 C0 fixture 或旧 `BillingReceipt.final` 解析器。首发仅固定官方 `https://api.deepseek.com/chat/completions` 的单次受控 POST，沿 Bootstrap 卡候选 `deepseek-flash`／文档声明 `DeepSeek-V4.1-Flash`，接线前核官方当前映射；model 与文档声明版本绑定，不沿用旧别名或自动 fallback；stream=false、thinking disabled、请求 max_tokens=4096、无工具、零自动重试。受控响应原字节及解压后各≤128 KiB、总 wall deadline≤60秒，超限／截断按真实 usage 可得性分别处理，不默默当完成。Bootstrap 的 2026-10-17 官方只读卡是设计输入，不是本轮价格／账户实测；模型别名不保证锁定不可变权重，必须记录声明版本与实际响应模型／可得指纹，漂移则关 paid。正式调用仍须 Mentor/DevOps 核真实 grant、原预充值、无自动充值／后付费、同币余额与他用边界。沿现有 Guard 的发送线性化：预连不得发送敏感输入；同 owner gate 内重核完整输入包、当前授权、permit 与预算，在受控短发送期限内实际启动 POST 字节，响应等待在 gate 外，任何网络等待不持 DB 事务。固定免费 GET 持 gate 至收尾的窄策略不借此改写。

| 对象／增量 | 最小字段与不变量 |
| --- | --- |
| `BudgetBasisSnapshot` | funding_epoch、已验证初始纯预付可用额 B0、可核他用风险余量 M（0≤M≤B0）、cap=B0−M、currency/scale、价格与模型文档 digest／适用范围／valid_until、C_bound/O_bound及依据、本地 rounding_guard；均为私有控制面，客户端／LLM不可设置 |
| `UsageObservation` | dispatch/input/model/price 绑定、响应摘要、可得 provider 响应 ref、完整最终 usage及验证结果；用量是观测，不是单笔财务 receipt，不保存用户正文或凭据 |
| `CostObservation` | reservation/dispatch/usage ref、kind=actual/estimated_upper/unknown、actual_charge:Money?、reserved_upper:Money、booked_upper:Money?、可选 usage_priced_estimate、basis/policy/version/digest；实际金额无可信财务依据时为 null，不能写0 |
| 新状态 `UPPER_BOOKED` | 仅发送时已绑定该新 policy 且足额预留 U 的同币 dispatch 允许；增加 upper_booked 汇总，旧版本默认0。不是 SETTLED、不是 actual；旧 fixture/final-policy UNKNOWN 不追认迁入，只按其原对账规则处理 |

每 call 的保守预留 `U=ceil_native((C_bound*最高适用峰值cache-miss输入价 + O_bound*最高适用峰值输出价)/1_000_000)+rounding_guard`，中间精确整数／Decimal、金额同币同scale且不溢出。C_bound 取不小于官方最大 context 的登记保守界；若“1M”口径未精确，记录采用的保守解释与来源，不能拿字符/4或本轮未测 tokenizer 冒硬界。O_bound 只有在官方参数覆盖全部可计费 completion 上界已核时才取请求4096，否则首笔按官方最大输出的更保守界预留；隐藏／reasoning 不重复加计，也不能漏计。完整输入模板／证据包有固定字节上限，但不是实际 token 数证明。价格、模型／币种、context/output依据不明或过期则拒绝新 paid。

ceil 和 rounding_guard 是公开标注的本地保守策略，不伪称官方舍入／最小扣费单位已知。在已核硬预付费与风险余量、上界依据和 policy 的范围内，首个小额有界验证不因官方未提供 rounding 或逐笔 receipt 端点而无限等待；这也不是实际扣款绝对上界的已实测证明。资金真实币种、余额精度及价格必须一致；USD 价格不能推算 CNY，CNY 须可信同币价及 schema／账本迁移另验。无法精确保存的实际余额／扣费仍按原规则停止，不靠向上取整估算篡改 actual。

同 auth DB 短事务与跨进程 CAS 必须维护 `settled_actual + upper_booked + held + U <= cap` 的新预留条件；settled_actual 对应原 settled 的真实已结算语义。共享该资金账户的所有预留 writer 都须计入 upper_booked，否则相应 paid 入口禁用；旧 fixture 的 upper_booked=0，因此保留原消费者算术结果。新 snapshot、价表、充值、促销、模型别名或较高余额不能自动抬 cap，也不能退旧 upper_booked；最新余额另作保守可用约束。外部消费、价格漂移或余量失效停止新 paid。异常真实费用若超过预留／cap，保留事实并冻结，不截断回 U，也不继续宣称预算边界已证。

可信最终响应的 usage 必须来自受控 provider envelope：同 dispatch/模型、非负严格整数非bool、prompt=hit+miss、total=prompt+completion、缓存明细一致、reasoning若有不大于且不重复计入completion。完整本地持久观测可在不重发的前提下恢复；请求 ID 只作关联，不能当费用 receipt。满足新 policy 时，`SENT→UPPER_BOOKED`；原 UNKNOWN 只有恢复到同 dispatch 的完整可信持久响应／usage 后才可转，不凭余额变化、客户端上报或缺失字段补0。事务一次性把 held U 减 U、upper_booked 加 U，重复观测不再占用；保守占用保持完整 U，不因较小 usage estimate 释放差额。相同响应 ref／摘要冲突或 usage 越上界，保存安全异常并阻断，不覆盖旧记录。

usage 完整但模型内容坏 JSON、空／截断、非法 schema／引用时，费用仍独立 UPPER_BOOKED，报告失败；内容失败不等于免费。缺失／矛盾 usage、丢响应或发送结果不明仍 `UNKNOWN + held U`，不释放、不换 key/task/model 重发；逐请求补查未有官方能力就明确 unsupported，只可读已有可信本地凭证，不造 receipt 查询路径或用账户余额差猜单笔。任何收费 UNKNOWN 都不能套用§4.1固定免费 GET 的 execution_closed 例外。确证未发送／未收费的释放及可信 final actual 的原规则继续成立。

后来若有可信财务依据，才可按受审流程将 upper_booked U 替换为 settled_actual A，并仅释放已证差额；不得同时扣 U 与 A，或将模型 JSON/估算／usage/余额差伪造成 final actual BillingReceipt。退款仍须关联可信原 charge；无法确认时保守占用不退。真实记录溢出／超预留／精度异常仍保留并冻结，不舍弃已发生费用。

新版本任务预算白名单投影增加 `upper_booked:Money[]` 与受限的当前任务 cost observations：区分 actual、estimated_upper、unknown，显示 actual=null 的“实际扣费未核”，原 known_cost 只放 actual。UNKNOWN/held 与 UPPER_BOOKED 分开；仅可信完整最终响应／usage且已足额保守占用的后者，不计入新版本 UNKNOWN 外发计数；但实际扣费未核必须独立呈现，也不能显示成实际0元／已财务结算。这是§4.2／4.4费用完成前置在新 policy 下的明确限定：它可以在其余执行与证据门禁满足时结束声明范围内的有条件报告，不永久等不存在的逐笔接口；缺 usage 的 UNKNOWN 仍保持原门禁，旧版本 fixture／final-receipt policy 不适用此完成例外。公开投影不含共享账户余额／账号、私有绑定、原响应或完整账单。取消／删除后仅费用控制记录可幂等转移／收实际依据，正文、分享和任务不得复活。

正式 owner 须对同物理 auth DB 做版本化迁移（旧 upper_booked=0、旧状态与 final 语义不变），同步派发／幂等／恢复／删除与新版本投影消费者，再启用新分支。该增量不另造计费平台、逐笔查询服务或新的资金账户体系；旧 fixture 正常结算、未知 held 与退款消费者继续原样验收。

#### 6.4.1 CNY usage-upper v2：可信用量后的保守重记账

2026-10-17，按 Mentor 已确认的保守用量上界方向，在 `bdd9cfc6d1f6c08a9e6f1ccc7a1ad3529de05547` 上新增此显式分支，不代表新的真实调用／凭据授权或 v5 已实现。v2 首发限同币 CNY 的已验证预充值、可信峰价、余额／他用边界与既有 cap；其他币种、旧策略须另按其受审规则处理，不猜汇率，也不因可用余额上升自动放宽。

定义同一个不可变费用函数 `F(i,o)=ceil_native((i*P_peak_miss_CNY + o*P_peak_output_CNY)/1_000_000)+local_guard`。rate、currency/scale、ceil方式、local_guard及price revision在 dispatch 时冻结，均非负且精确可表示。发送前仍 `U=F(contextBound,4096)` 足额预留；contextBound 仍按已核官方 context 的保守界，不用字符数推实际 token。与 v1不同，v2不采用未知的大输出fallback：必须已有官方参数语义依据与最终请求代码证明，保证全部可计费 completion 受4096上限约束；否则不启用v2，不能仅靠模板／配置声称已限。

最终序列化请求须固定 `max_tokens=4096`、thinking disabled、无 tools、非流式、零自动重试。受控 prepare 在所有模板／参数合并之后严格核完整最终 bytes（重复 key／额外覆盖拒绝），把该摘要、model/version、contextBound、输出界、F及 policy revision绑定permit；实际 send 再核发送bytes完全相同。调用者kwargs、后层SDK／middleware不得改max_tokens、开thinking或插工具；代码独审和本机发送边界反例须证明改动在任何敏感字节发出前被拒。此要求不能拿4096可见文本上限替代全部可计费completion界。

只在同 dispatch 的完整可信最终 usage 已持久化、模型／请求摘要／原price和新policy绑定一致后，沿原整数、缓存合计、total、reasoning规则核验：`0<=prompt_tokens<=contextBound`、`0<=completion_tokens<=4096`，reasoning若有属于completion而不重复加。必需字段缺失、非final、bool／负数／矛盾、绑定不符或越界均不能补0。按全部 prompt 一律峰值 cache-miss、全部 completion 峰值输出，使用原来的同一个 F 得 `Uobs=F(prompt_tokens,completion_tokens)`；不赌cache-hit或非峰折扣，不换新价表／scale，不省local_guard。先严格核 `0<=Uobs<=U`；若不成立，保留原全 held U 并置UNKNOWN／阻断新paid，绝不 `min(Uobs,U)` 裁切过关。

同 auth DB 的一个幂等CAS事务绑定该持久usage／cost观测后，完成 `held-=U; upper_booked+=Uobs`、置UPPER_BOOKED，并记录 `reserved_upper=U,booked_upper=Uobs,released_reserve_difference=U-Uobs,actual_charge=null` 及原F／policy／dispatch关联。仅原来发送时已绑定v2且状态／版本／预留匹配的 SENT，或有同dispatch完整可信持久观测恢复的UNKNOWN允许此转移；重复或并发处理同观测不再退／扣差额。事务崩溃回滚保持全held，已提交则恢复同一Uobs，不能“先释放、后补记”或重复释放。差额只是保守预留重估，不是provider退款或单笔actual已知；新预留仍核 `settled_actual+upper_booked+held+newU<=cap` 及最新保守可用余额约束。

内容坏JSON、schema／引用失败但上述usage有效时，仍按v2独立记Uobs，报告失败；取消／撤权／删除后仅最小费用记录可迁移，正文／分享／任务不得复活。丢usage／响应、超界或异常usage继续UNKNOWN并全held U、不重试，不套免费GET execution_closed。旧fixture/final policy/v1或未绑定v2的既有SENT／UNKNOWN／UPPER_BOOKED均不追溯释放差额；历史全U金额、退款／actual记录不因新算法回放减记。

投影仍区分 actual、estimated_upper、unknown：v2显示已核用量对应的保守Uobs、原U与一次释放的预留差额，同时明确actual=null，不写SETTLED／伪final receipt／实际0元。报告完成按原有条件化规则，不把计费上界当证据级别。后来可信账单A若大于Uobs（即使仍小于原U），须记录上界失效并阻断新paid，不丢弃／裁切真实费用；不得仍宣称旧上界有效。若A不超Uobs，按受审财务依据只以当前Uobs替换actual A，差额只算Uobs−A，不能再释放已处理的U−Uobs；余额差不是该单笔依据。

本分支最小消费者判据如下，均待正式owner实现与独审实际运行；当前不修改旧消费者探针的fixture/v1对照。

| 场景 | 必须成立 |
| --- | --- |
| 最终请求覆盖／cap证明 | 改max_tokens、thinking、tools、序列化重复key或发送bytes，在真实发送边界前拒且计数0；合法最终固定包为对照，不能只测prepare模板 |
| 低量／满量与ceil | 低量按原F算Uobs，差额释放一次；prompt=contextBound、completion=4096时Uobs=U；cache hit全额仍按miss计，local_guard不丢；不是actual账单 |
| 并发／重复／崩溃 | 两进程处理同dispatch观测只一次held U→upper Uobs；事务各故障点原子回滚或读回已提交值，不二次退差，其他writer的新预留仍受同cap |
| 内容坏而usage完整 | 报告失败，保守费用Uobs仍持久；不发JSON修复／重试，不恢复被撤权正文 |
| 缺／伪／超界usage | UNKNOWN保全held，不补0／不min裁切／不重发；响应ref或绑定冲突阻断；后续账单A>Uobs如实保存并关paid |
| 旧策略／币种／历史与重启 | fixture/final/v1及既有金额原样不减；未绑定v2、错币或过期依据不新发；重启保原policy/F/usage与一次差额记录，余额／充值／别名变化不追认或放宽 |

#### 6.4.2 付费研究预览与确认的外部契约

本节仅冻结两个 POST 的外部 DTO 与同意／控制边界，由 Core 后续适配内部服务；不实现路由、资金、真实模型或 CP3。当前执行模式只用已冻结 `offline_probe`，`model_analysis_ran=false`；真实 paid mode／结果 producer 须另一个受审增量，不能给旧离线 DTO 改标 live，也不能因 quote／F 通过宣称模型跑过。外部资金／凭据／实际付费放行仍按§6.4独立核验。

两入口沿既有 Envelope、cookie-only 研究身份入口、CSRF、`Idempotency-Key`、`Cache-Control:no-store` 与 `Referrer-Policy:no-referrer`。Bearer-only 为401，失效 cookie 不被 Bearer 救活，两 cookie／共享凭据冲突保持原语义；不新增 JWT/Bearer 身份选择。原始请求体含 Envelope 合计≤64 KiB，严格 JSON／额外字段／重复 key／类型拒绝规则继续有效。两响应含 Envelope 的 UTF-8 总字节沿§4投影上限≤512 KiB，超限拒绝；实际最终外发包另限16 KiB，不能用公开投影限额扩大外发。

| 入口／DTO | 精确客户端 data 与结果 |
| --- | --- |
| `POST /api/research/{research_id}/paid-previews` | `{input_revision:Revision,expected_research_version:Revision,excerpt_ids:Id[],purpose:"method_hypothesis"}`；excerpt_ids为1..20项、不重复；路径 ID 不能从正文覆盖。返回 `PaidPreviewView` |
| `POST /api/research/{research_id}/paid-approvals` | `{preview_ref:Id,expected_preview_version:Revision,input_revision:Revision,expected_research_version:Revision,preview_digest:Digest,confirm_external_input:true,confirm_maximum_reserve:true}`；两确认必须是显式严格布尔 true，拒绝缺省／false／1／字符串。返回 `PaidApprovalView` |

请求不能指定或覆盖 provider/model、summary、price/quote、funding、cap/余额、policy、调用次数／重试、可信 usage/cost、owner/grant、最终 packet、许可或 may_send。用户只能选当前已保存摘录；服务端从当前研究修订读取摘要，选择已核 quote／资金／policy，不能从客户请求中挑一份“可用价表”或依布尔自授资格。purpose固定方法假设，不借此启用任意金融预测／交易或旧动态工具。

| 响应／子对象 | 精确白名单字段与含义 |
| --- | --- |
| `PaidPreviewBinding` | `{research_id:Id,input_revision:Revision,input_digest:Digest,research_version:Revision}`；绑定当前研究及问题，不含完整 CallContext／主体／grant／资金 binding |
| `PaidPreviewQuote` | `{revision:Id,digest:Digest,valid_until:UtcTime}`；来自服务端当前受审 UsageUpperQuote，原 policy／币种／价格／context/output依据、代码摘要与时效全部在服务端核并绑定；不是客户端报送的 quote |
| `PaidPreviewSource` | `{source_id:Id,source_revision:Revision,excerpt_id:Id,title:ExactText(300),canonical_url:Text(2000),attribution:ExactText(400),raw_digest:Digest,extracted_digest:Digest,discovery_digest:Digest,permission_basis_digest:Digest,start:int,end:int,quote:ExactText(1000),read_scope:"author_narrative_subset",acquired_at:UtcTime,information_cutoff:YYYY-MM-DD,may_send_to_provider:false}`；仍由现有 source/excerpt资格读取生成，0≤start<end，Unicode区间／原取得时间／署名／许可逐项核，短引≤20词 |
| `PaidOutboundHandle` | `{handle:ASCII32,source_id:Id,source_revision:Revision,excerpt_id:Id,title:ExactText(300),attribution:ExactText(400),extracted_digest:Digest,start:int,end:int,quote:ExactText(1000)}`；精确复用现有 EvidenceHandle.outbound 白名单，handle在包内唯一；不含完整 extracted_text、display_permission或发送权限布尔 |
| `PaidPreviewManifest` | `{problem_summary:Text(1000),sources:PaidPreviewSource[],handles:PaidOutboundHandle[]}`；两数组1..20且逐项同 source/excerpt具体版本／hash/offset／短引／署名，一一对应；sources是核查与显示依据，真正用户输入出站仅 problem_summary+handles |
| `PaidPreviewView` | `{preview_ref:Id,preview_version:Revision,status:"draft",expires_at:UtcTime,bindings:PaidPreviewBinding,purpose:"method_hypothesis",provider:"deepseek",model:"deepseek-flash",declared_model_version:"DeepSeek-V4.1-Flash",execution_mode:"offline_probe",policy_revision:"bounded_usage_upper_v2",quote:PaidPreviewQuote,maximum_reserve:Money,actual:null,cost_label:"maximum_reserve_not_actual",max_calls:1,manifest:PaidPreviewManifest,manifest_digest:Digest,outbound_request_digest:Digest,preview_digest:Digest,may_send_to_provider:false,model_analysis_ran:false}`；maximum_reserve严格CNY／scale6，来自原F完整U；只是保守预留上界，不是实际收费、概率费用估计、余额或官方最终账单 |
| `PaidApprovalView` | `{approval_ref:Id,preview_ref:Id,preview_version:Revision,preview_digest:Digest,research_version:Revision,task_id:Id,task_version:Revision,execution:ExecutionState,status:ProductState,execution_mode:"offline_probe",model_analysis_ran:false}`；preview_version指所确认的原预览内容版本，不是消费后的内部CAS版本；首次固定QUEUED／queued；重放返回实际当前状态，只说明原批准与任务，不因确认显示已外发／已生成／U1或U2已完成 |

预览必须展示实际将外发的摘要、短引、署名和上述费用提示，不能只列来源标题或只给预估金额；页面按固定policy明确说明单次、无工具、非流式、零自动重试及输出界4096，不能由请求改写。缺信息／许可／完整署名或资金／quote未核则明确拒绝，不构造假成功 preview。完整问题原文、全文提取文本、原始文件句柄、provider key、共享账号／余额／私有资金／authority对象不进入响应、URL或公开日志。公开字段不是控制对象的直接序列化；无关当前范围的资料不得夹带出站。

`manifest_digest=SHA256(canonical(PaidPreviewManifest))`；`outbound_request_digest`只绑定真实最终 provider 请求 bytes，包括固定 system模板／schema示例／model／参数与 problem_summary+handles，完整包≤16 KiB且无截断。`preview_digest=SHA256(canonical(PaidPreviewView去掉preview_digest字段))`，因此展示范围、原quote摘要／有效期、U、模式／policy／目标和版本均被绑定。hash对象域和规范算法必须明示；研究input_digest、manifest_digest、outbound_request_digest和同意请求摘要不互作替身。

Preview manifest是不携带发送能力的独立显示结构；资格两层 may_send 均 false，不能为了调用 prepare 临时翻 true，也不提前生成假的 task/attempt/plan 或已批准 EvidenceHandle。Core须用无能力的固定序列化预览构建／校验出站 bytes，不调用发送、消费或签票入口。确认后才分配正式 task/attempt/plan，将新的 CallContext 与同一获准内容建立实际 EvidencePacket；其 binding_digest另含这些新控制ID，必须独立计算并绑定，不强求它等于preview manifest摘要。实际外发 bytes摘要必须仍等于获准 outbound_request_digest，不能借控制ID变化改变用户获准内容。

#### 预览、确认与实际派发的事务边界

Preview仅产生无权力 draft（可保存其私有控制行及幂等引用），不新建／消费 paid grant、task、reservation、permit或费用，不改变 research version。先核当前 cookie身份／研究read权限／input revision+digest／expected_research_version及摘录资格、显示范围，再由受控 quote／资金入口取得当前报价条件；固定 v2quote与U由唯一受审算术产生，不在API复制另一套F。expires_at不得晚于服务端本地preview TTL或原quote.valid_until，时效规则明确为本地策略；缺 quote不以旧价／前端价格兜底。

首次 confirmation 在既有 owner gate／同 auth DB 的短事务中重核当前主体 incarnation/epochs、研究owner/acl/grant、write及独立付费执行资格、研究修订／版本、所选全部源许可／完整署名及读显范围、原preview版本／摘要／draft未消费／未过期、原quote和资金basis当前性，并核实际出站内容及 max_calls=1。两个 true只表达用户对具体资料外发与最大预留U的同意，不能替Owner资金权限或将免费GET批准变成付费批准。

事务原子消费该preview，保存独立 paid批准及其私有授权／quote／manifest／最终bytes／资金epoch绑定，创建正式 plan/task/attempt与queued步骤、幂等结果，递增 research version；preview内部消费CAS版本另增，公开 approval回指原内容版本。全部失败回滚、无半计划。确认不建 reservation／permit／派发或费用；同研究已有活task拒绝，不用新preview/key绕开当前未知外发／资金对账。D1免费GET的批准／quota／未结控制仍独立，不互相继承或清零。

reservation只在后续 prepare／authorize前的既有受审预算事务中足额预留U，再按原guard流程生成并一次消费permit。真正send之前仍重核当前批准、原quoteTTL、资金及 source/current auth、完整最终固定bytes和预算；queued或确认成功不是外发成功。价格／模型／模板／输入／来源许可或原绑定变化、到期时失效未消费的发送资格，重新显式preview／confirm；不自动换价、换模型或把旧同意迁到新包。原调用若已发／未知，先按原规则对账，不用新确认重发；生产资金、CP3真实producer及live版本尚未独审放行时仍拒绝实际paid。

幂等按现有主体incarnation／operation／research非空scope及key摘要唯一，正文摘要覆盖全部对应客户端data。相同key同正文重放先核当前身份、研究与资料读取权限，再回原preview或approval/task引用及当前安全状态，不新建／消费／派发；未消费draft的原key重放若已过期或当前输入／绑定变化，返回409要求重新预览，不盲回仍有效draft；已提交同意的原key回读不能因原quote已过期变成新的扣费申请。同key异正文409，换key也不能重复消费同preview或绕过未结fingerprint；并发只一个有效确认。replay不能返回盲存的旧QUEUED状态冒当前执行进度，PaidApprovalView的execution/status首次为QUEUED/queued，重放从既有ResearchView读取当前二状态并保留原approval/task refs，具体已确认版本不变。

删除、研究撤权、账户incarnation更换、失效会话或许可撤销后，旧preview／确认／key／缓存不恢复私有正文或资格；跨账户及不匹配的对象引用404。已启动不可取消的provider调用不能承诺撤销费用，迟到只按现有费用控制规则处理，不恢复报告、分享或任务；缺usage的UNKNOWN保持held，不套免费GET闭合例外。付费入口不接收客户端usage、receipt或余额差作为可信费用；坏内容与可信usage的费用分别按§6.4.1记账，actual仍未知时为null。

| 拒绝／结果 | HTTP与动作 |
| --- | --- |
| 格式、版本类型／确认值、额外字段／重复key；rawbody／最终外发／响应超限 | 422；体积超限413，执行／派发0，不截断 |
| 研究／preview版本、摘要／包变化、preview或原quote过期、已消费、已有活task | 409，读当前状态或重新preview；不自动换价重发 |
| 来源／许可／完整署名不支持；预览创建时funding／可用新quote未核；预算不足 | SOURCE_PERMISSION_UNAVAILABLE 409；BUDGET_UNVERIFIED 503；BUDGET_EXHAUSTED 429；不返回source私有细节或资金控制对象 |
| 在途／未知、身份失效、对象越权 | OUTCOME_UNKNOWN／RECONCILIATION_REQUIRED 409并request_reconciliation；身份401／原冲突语义；对象404，均无新外发 |

#### 最小消费者反例（待实现后独立执行）

| 场景 | 必须成立 |
| --- | --- |
| preview→确认→prepare/send | preview真实task/reservation/permit/发送计数0且may_send=false；显示摘要／短引与最终获准bytes一致。确认只一批准/queued task、无费用；受审后续预算及真实producer缺一仍不可send，离线不标live |
| 客户端伪造与边界 | 自报价表／资金／可信usage／may_send、数字1代true、bool/float/string代Revision、重复／跨研究excerpt、额外字段／JSON重复key、超64KiB输入或16KiB最终包，在创建/发送前拒；合法cookie+严格整数/true为对照，Bearer-only及失效cookie+Bearer不救活 |
| TTL、许可与摘要域 | quote/preview到期、改题／读显许可／署名／模型／模板／bytes漂移拒；manifest与含新task IDs的packet摘要分域，正式packet重建仍吻合原bytes，不先翻发送许可布尔 |
| CAS、重放与未知 | 两进程确认仅一原子批准/计划；丢ack用原key读回，无二次消费/预留/发送，异正文409；新key/preview/task不绕UNKNOWN、同研究活task或原funding cap |
| 撤权／删号与费用 | 跨号、两cookie冲突、同邮箱新incarnation、CSRF及删除/确认/迟到竞争均保原边界；不回放私有幂等正文；内容坏而usage可信仍记保守费用，unknown全held、不重发、不用余额差造actual |

### 6.5 本地财务情景结果：保存与读取增量

依据已批准 PRD 0.3／U2，复用 `7e0780ba30d163180efc5584e65ef138b1571f27` 的五文件有限执行器。本节仅冻结候选接口，独审后由 PMO 分检查点派实现；不表示 API／存储已实现或 U2 已验收。操作固定为 `local_financial_result_v1`：本机纯计算并保存私有结果，无网络、模型、资金、reservation、dispatch 或外发批准；不借用 D1／model task，不更改它们的完成状态、来源标志或费用，不改§6.4、schema6及价格函数。表迁移版本由 Core 唯一 owner 后续核定。

#### 对象与受控来源

| 对象 | 最小字段与边界 |
| --- | --- |
| `FinancialRegistryRef` | `{id:Id,revision:Revision,digest:Digest}`；指服务端在本研究授权范围保存的不可变 `SourceRegistry`，digest 按执行器的规范 JSON 算法绑定完整 registry；请求仅引用，不接受来源事实表或自报许可 |
| `FinancialSourceBinding` | `{financial_snapshot_id:Id,registry_ref:FinancialRegistryRef,snapshot_digest:Digest,source_record_ref:{id:Id,revision:Revision}?}`；financial_snapshot_id 精确对应 registry.sources 中的 SourceSnapshot.id，观测／FX 的 source_refs 只能指该 registry 内的快照；绑定由受控 importer 保存，不能靠 UUID 存在认定同研究／可读 |
| `FinancialResultBinding` | `{research_id:Id,input_revision:Revision,input_digest:Digest,request_digest:Digest,registry_ref:FinancialRegistryRef,policy_revision:Text(64),producer_commit:Text(40)}`；producer 固定上述受审执行器，policy=`financial-scenario-v1-candidate`。另私存当前主体 incarnation／principal epoch、auth_generation、owner/acl epoch、grant，不能由请求或模型赋值或在公开投影泄露 |
| `FinancialResult` | `{id:Id,type:"financial_scenario_v1",binding:FinancialResultBinding,snapshot_digest:Digest,canonical_snapshot:ExactText(131072),calculation_status:"calculated_under_assumptions",u2_goal_status:not_assessed\|not_met,model_analysis_ran:false,created_at:UtcTime,research_version_at_commit:Revision}`；服务端生成、不可变；字节上限另验，缺必要基线／成本／构成时必须 not_met，纯计算不得自行签发 U2 通过 |
| `FinancialResultReceipt` | `{result_id:Id,input_revision:Revision,snapshot_digest:Digest,research_version_at_commit:Revision}`；仅回受权结果引用，不返回原始 registry／凭据／正文；同 key 恢复仍须当前授权 |

财务 SourceSnapshot 的 `kind/read_scope/source_chain` 保留执行器原类型；不扩写或借用现有 SourceRecord／SourceVersion 的两种 parser read_scope。`curated_record` 必须绑定整理表摘要、固定 commit、entry 定位和实际人工读取范围，raw_response_digest／extracted_text_digest／retained_original_ref 均 null；87e564 历史表不冒原文、live 或独立交叉确认。`historical_original/live_original` 必须由受控导入／取证路径保存真实原文、提取摘要及受权 opaque 引用，另建快照而不回填 curated。source_record_ref 仅在该实际记录的范围、版本、摘要和读取语义均能正确表达时绑定，否则为 null，保留独立财务来源记录；不得强行套 PLOS parser 标志。

importer 单独核来源真实性／层级、同源转载关系与本研究读取／显示权限，生成 registry 和上述映射；执行器类型验证不承担这些证明。本节不新增任意 URL 抓取、原文导入接口或自动来源升级。后续取得的来源、新事实／会计口径／参数均形成新 registry 或新结果，旧内容不原位覆盖；公共来源可按许可重新导入，跨账户私有 registry 不得复用。投影不给原文私有路径、保留文件句柄或未经许可的原文。

财务数值沿受审模块的独立 `FinancialDecimalText` 范围：有限十进制字符串≤64字符、≤24有效位、指数及非零数量级±18、绝对值≤1e18，拒绝 bool／float／表达式；不是§2 的 DecimalText 或计费 Money。原币 CNY/USD、期间／单位／会计口径／证据级别与未舍入原值保留，历史 FX 与未来假设分开；净利／EBITDA 不替营业利润，CAPEX 不直计营业费用，共用成本／折旧／SBC 不重复。2026E 中期加剩余期间假设桥接、2027–2031 五完整年、最多3情景及21单参数敏感点沿原 policy；业务互斥、未分配及缺失／冲突保留，null 不补0、全未分配不算构成完成。未来参数始终标条件假设，范围不是已校准概率；没有可信绝对基线／成本桥接时不以指数图或机械演示宣称题目满足，不在本契约设新参数数值。

#### POST、提交与重开

| 消费者 | 正式请求／响应边界 |
| --- | --- |
| `POST /research/{research_id}/financial-results` | 请求为 `{input_revision:Revision,expected_research_version:Revision,registry_ref:FinancialRegistryRef,request:FinancialRequest}`，沿现有 Envelope／身份／CSRF／Idempotency-Key 与严格额外字段、重复 key 拒绝规则；FinancialRequest 精确复用上述执行器的字段、显式假设和上限，客户端不能传 registry 内容、快照、digest 结果、trusted 标志、owner、模型或价格。成功返回 FinancialResultReceipt |
| `GET /research/{research_id}/financial-results/{result_id}?view=summary\|table\|chart` | 默认 summary，未知 view 拒绝；在一致读事务逐对象验当前授权，跨账户／不属于该研究／失效引用统一404。响应为 Envelope，data 固定含 `{result_id,type,input_revision,input_digest,request_digest,registry_digest,policy_revision,snapshot_digest,created_at,is_historical,calculation_status,u2_goal_status,model_analysis_ran:false,view,payload}`；payload 按下述三种白名单投影，不能任意字段／函数调用 |
| summary／table／chart payload | summary 只列情景／指标可用性、信息截止、来源 kind/read_scope、显式缺口与假设索引；table 为同一保存快照的 table() 视图并带历史背景、来源／观测／参数依据；chart 为同一快照 chart_spec() 及对应依据索引。源、原值和理由按当前显示权限过滤，不能用删除缺口或换一份 registry 维持图形。研究 view 仅增受权 result refs／capability，旧 notes／D1／model report 类型保持 |

内部正式边界为 `resolve_financial_registry(conn,identity,binding,ref)->AuthorizedFinancialRegistry`、`evaluate_financial_candidate(request,authorized_registry,binding)->ServerFinancialCandidate`、`commit_financial_result_locked(conn,identity,expected_research_version,candidate,key)->FinancialResultReceipt`、`read_financial_result(conn,identity,research_id,result_id,view)->Envelope[FinancialResultView]`。前两种内部类型只由受控调用链产生，携带完整 registry／输入绑定和私有授权快照；类型或摘要本身不授予信任，commit／read 仍按下述门禁重核；FinancialResultView 即上表 GET 白名单。adapter 不接受任意对象注入这些内部类型。

服务端先在短一致读事务核当前有效身份 incarnation、principal/owner/acl epoch、read+write grant、研究 active、已确认且当前的 input_revision+digest、expected_research_version 和 registry 绑定／来源权限，再取得不可变输入包；事务外执行有限纯计算，不持 DB／owner gate 等待完整计算。请求体沿64 KiB上限，request+受控registry≤128 KiB，所有原对象数量、Decimal50／5000步骤／合作式2秒上限继续有效；合作式限制不声称 OS 隔离。资源超限整次拒绝，不降精度或删来源过关。

`evaluate_financial` 产物只是服务端内部 candidate；`FinancialSnapshot(str)` 仅验大小，不能用它校验不可信快照。保存入口不接受客户端／LLM 自报 candidate、canonical bytes 或摘要；从该次受控 request+registry+producer 调用取得结果，严格核结构、输入／registry／policy 摘要、完整 export 上限和表图一致后，才能交 commit。摘要不是授权凭证；不从裸 JSON 还原一个对象就追认来源或计算已验证。

commit 在既有跨进程 owner gate 内、同一 auth DB 的短事务中重新核上述全部授权／grant／来源显示范围及版本，CAS 当前 research version 与 input revision+digest；来源撤权／改版、问题变更、账户删除或研究撤权先提交时，候选不得保存或恢复资产。成功原子写不可变结果、source 映射引用及幂等引用，并递增 research version，current_task_id／任务状态不变；任何失败全部回滚、不留半结果，未知 ID 禁止 upsert。Core 是 DDL／连接／事务／删除与 API 接线唯一 owner；独立 adapter 不自行 connect/commit、建库、分配 schema 版本或迁移当前 paid producer 表。

幂等唯一作用域为 `(principal incarnation,local_financial_result_v1,r:<research_id>,key_digest)`，规范请求摘要含全部客户端请求字段；同 key 异正文409，同 key 同正文并发只存一个结果。重放先核当前身份、研究及 registry 读取权限，再返回原结果引用；已改题仍可作为有标历史读取，不重算或覆盖旧结果。响应丢失／进程崩溃先按原 key 查提交事实；仅确证未提交且当前版本／权限仍有效时可重做本地纯计算，不新增外部请求或伪造 UNKNOWN 费用。已撤权／删除不回放私有幂等正文，最小防复活记录不能重建内容。

每次 GET／重开重新核当前研究及来源读取／显示资格，校验保存 canonical 摘要、受控 producer／policy／严格快照结构和 binding，拒绝损坏／未知版本，不能从客户端缓存补写；历史结果按 input_revision 与当前 revision 比较设置 is_historical，原输入与来源／参数摘要、原 created_at 保持。table 和 chart 仅从这一份不可变快照投影，均带相同 snapshot_digest；缺点不连线、不再计算、拟合或自动换汇。table() 的 same_as 展开及外层 Envelope 也受限：持久完整结果、每种最终 UTF-8 view 响应分别≤128 KiB，超限明确拒绝、不截断；不要重复拼装 table+export+chart 绕过上限。对无效／超限 candidate 不产生结果；已有完整结果的某 view 超限只拒该 view，不伪造成计算成功的新结果。

账户／研究删除与撤权复用同库控制门禁及§7，先禁读／增 epoch，再清 FinancialResult、私有 registry／来源映射、幂等正文和保存的参数快照；共享公开源只清本研究授权关联，不误删其他仍获授权研究的来源。迟到计算及旧 cookie／同邮箱新 incarnation／旧 key 均不得复活结果、研究或分享。本节不开放新的匿名读取、分享、模型调用或预算入口；“本地无外发”不是 provider actual=0 账单，model_analysis_ran=false 也不代表 U2 价值已验收。

#### 最小消费者反例（待实现后独立执行）

| 消费者场景 | 必须成立 |
| --- | --- |
| POST→保存→重开→表／图 | 实际私有 API 调纯执行器，重启后同 result/input/registry/snapshot 摘要与原时间，table/chart 同源；同请求单元格与纯模块 golden 一致，模型／网络／资金调用0 |
| 伪事实／摘要／来源 | 客户端 registry／快照／trusted 或伪造来源引用在执行前拒绝；只改 digest、将87e curated 冒 live／原文、同源转载冒独立、跨 owner registry 不能入库；未知 policy／损坏保存字节不得读取 |
| 竞争／丢回执／版本 | 同 key 并发只一结果，异正文409；提交前后崩溃按原 key 读回或确证未提交再算。计算中改题／来源授权变化先提交则结果提交拒绝，已存旧修订只能有标历史展示，不改当前问题或任务 |
| 隐私／删除与迟到 | 跨账户／同邮箱新 incarnation／失效会话不得读，撤权或删除与 commit 竞争只允许合法先后；删除后迟到 candidate、旧 key／缓存／重启不能恢复正文或分享，原文句柄不出投影／日志 |
| 数值／资源／不足 | 半年不直年化、OP不以净利代、成本不重计；缺 FX／成本／分部保留 null／缺口与not_met，不假U2通过；same_as 展开／Envelope 超128 KiB拒该view，任一输入／计算上限整次失败，不删来源或补0，范围不标概率 |

## 7 撤权、删除、认领与迟到提交

同DB维护principal/acl epoch、task授权快照与新研究数据。正常结果提交使用条件写入，要求principal active、auth用户仍存在且generation相同、grant active、research active、各epoch一致、task attempt/version当前、未stop。任一条件不满足即拒绝持久正文，不依靠先读后写的时间窗。

跨进程owner gate是单机实际原语，候选为受控私有目录内按opaque principal_id固定的OS文件锁；不能放邮件或用户输入到锁路径，不在有等待者时删换锁文件。认领同时取旧匿名/新账户gate时按ID排序，避免死锁。进程内锁只是优化。不可跨主机共享此保证；第二台worker不得接入本设计。

外发方在gate中重核资格并启动一次transport，撤权/认领方在同gate中提交epoch变化，形成明确先后。已启动的旧请求可以继续返回，但结果提交必须重核并丢弃；不能保证远端停止或取消收费。还未启动的票在epoch变化后失效。SQLite写事务只用于短状态变更，不覆盖完整网络等待；transport启动卡住有固定超时并进入UNKNOWN，不持锁无限等待。

账户删除先在gate+同DB事务将principal置deleting、epoch递增、撤销grant、标task stop并禁读/分享，再清除新研究内容及既有registry资产。旧库补偿失败时保持deleting与访问封禁，记录恢复任务；不得自动把epoch改回旧值恢复旧写资格。最终删除auth行、清binding，必要的未知费用只留最小独立收据。现有多库删除须通过适配接该前置门禁，未接前不能启用新后台研究。

撤销研究访问权增加acl_epoch并撤销grant；认领转移owner及epoch并撤销匿名grant，旧任务不继承新身份。新grant需当前身份操作，恢复任务新attempt且先对账旧步骤。重新注册、重新登录或生成新分享链接不能重新激活旧epoch。API返回未知/跨owner对象统一404；已知本人的授权失效可以给泛化access_ended，不附原研究信息。

## 8 统一错误和公开信息

错误包为`{error:{code, message, retryable, allowed_next_actions, incident_id}}`；message是受控用户文案，无供应商原始异常/URL、私有路径、正文和身份。`incident_id`为随机Id。默认retryable=false；retryable只授权重试该API的纯操作，不代表可重发在途收费。

| ErrorCode | HTTP/结果 | 行为 |
| --- | --- | --- |
| INPUT_INVALID / SCHEMA_UNSUPPORTED | 422 | 修输入或升级明确版本，不执行 |
| PAYLOAD_LIMIT | 413 | 缩小输入，不截断后执行 |
| REVISION_CONFLICT / IDEMPOTENCY_CONFLICT | 409 | 读当前版本/原key结果，不覆盖 |
| AUTH_REQUIRED / NOT_FOUND | 401 / 404 | 重新登录或返回；不泄露对象存在 |
| ACCESS_TERMINATED / AUTHORIZATION_STALE | 对外403泛化或404；内部明确码 | 无retry/内容读取；旧回执只结算 |
| BUDGET_UNVERIFIED / BUDGET_EXHAUSTED | 503 / 429 | 暂停对应收费步骤，保留已有结果 |
| OUTCOME_UNKNOWN / RECONCILIATION_REQUIRED | 409 | request_reconciliation，不能无条件retry |
| UPSTREAM_UNAVAILABLE / UPSTREAM_TIMEOUT | 502 / 504 | 若可能已发送同时置UNKNOWN，不按HTTP错误推断未计费 |
| STORE_BUSY / VERSION_CONFLICT | 503 / 409 | 仅重试未完成的本地事务，按幂等key确认 |
| FORMULA_UNSUPPORTED / PRECONDITION_UNKNOWN / RESOURCE_LIMIT | 合法请求返回CheckResult相应status | 说明范围/条件/资源，不伪造不等价或成功 |
| SOURCE_RESTRICTED / SOURCE_FETCH_FAILED | 步骤/来源结果 | 留读取范围和缺口；不绕访问门禁 |
| FEATURE_UNAVAILABLE / BILLING_CONTEXT_REQUIRED / OUTBOUND_NOT_REGISTERED / PERMIT_INVALID | 503 / 403 / 403 / 403 | 明确不可用或拒绝；无fallback/自动重试/其他模型外发；GET请求收费生成另返回405与Allow:POST，不重启已退役GET |

## 9 冻结前必须解决的少量选择与未验

本候选选用同一auth SQLite与单机owner gate，以减少不可证明的跨库竞态；实施owner需审其迁移/锁顺序、Phase共享入口和异常补偿，再通过多进程探针。公式资源值与snapshot TTL是可逆技术初值，必须在实现中验证拒绝路径，不能只存在文档。供应商可计费上界、硬预付费隔离及实际余额均未实测，不阻断离线B1，也不放行真实调用。

所有导出、路由、表和schema均为候选建议；本规格工作树没有新增源码、数据迁移、产品运行或冻结证据。返修复核后，可由唯一共享owner在指定固定受审base隔离实现B1，不把B0等待扩大为阻断无依赖实现；合入和冻结仍需B0、科学、runtime组合当前SHA的独审、必要CI与真实消费者证据全部闭合。PRD、源码现有字段和旧报告语义不因本文自动改变。

## 10 CP3 内部 OwnedSession／Return 消费增量

2026-10-17，追加于受审离线预览／确认候选之后。本节只冻结内部来源与消费边界，不新增公共 API、表、资金账户或通用执行平台，不实现六个预算 writer、资金 loader、secret 或 live 工厂。§6.4.1 的唯一 F、§6.4.2 的确认与最终字节守卫、§7 的撤权／删除继续独立适用。

### 10.1 类型、模式与不可变关联

最小新增类型为 Core 拥有的 `OwnedProviderSession`、`OwnedReturnReceipt` 与冻结的 `FinancialReturnBinding`。它们由受审服务端调用链构造并绑定实际资源；普通 `ProviderObservation`、客户端 JSON、`trusted=true`、URI／UUID存在或摘要一致都不能生产可信收包能力。Python 私有构造、禁止 pickle 和类型检查仅是正式应用路径的约束，不构成对任意 Python／root 代码的进程安全隔离。

阶段一仅 `offline_probe`：服务器测试装配的独立连接与合成控制源可验证机制，但不登记为真实供应商收费，不显示 `model_analysis_ran=true`。默认公开 adapter 的 `paid_disabled` 与既有 probe 入口语义保持，不私改 probe 标志或给旧 DTO／v1 记录换 live 标签。真实结果、资金、凭据与出站模式必须在后续 additive 版本中另经 producer／制品／授权独审，不能借本节放行。

`FinancialReturnBinding` 至少冻结：session／paid approval／dispatch／reservation／permit 引用及消费版本；task／step／attempt与发送时授权版本；实际最终请求 bytes、evidence 与授权上下文摘要；account及稳定经济 binding、原 funding_epoch；accounting policy／model声明版本／实际响应模型及可得指纹；原合法准入的 quote revision／digest、basis digest、F界限与 server admitted_at。模式与 producer 版本同样绑定。关联均由当前同库受控来源生成，不接受客户补字段、换 quote 或回填准入时间。

### 10.2 唯一受控收包与持久来源

1. Core 在发送前登记 session，独占实际 adapter 实例、connection、creator PID、固定绝对期限及原完整请求。核已批准单次计划、当前 source／paid grant／资金用途和实际 HELD、prepared permit／版本；普通 DTO 或 `state='received'` 不能注册一个可消费 session。
2. 同 owner lease 内，Core 通过唯一预算消费入口在短同库事务中 CAS 一次 permit／reservation、approval／session、task／step及事件；确认 commit 后，受控 transport 才能启动敏感 POST 字节。任何网络、loader 或响应等待不放在数据库事务中。消费提交／回执不明先重读原状态，不能换 key／task／session重新发送。
3. `OwnedProviderSession.receive()` 自己调用该 session 已登记 adapter 的 `finish`，从该实际收包路径生成 `OwnedReturnReceipt`。禁止 `mint(observation)`／任意布尔或调用者 callback 把普通响应 DTO 盖章为可信来源；类型校验、合法 usage 和 hash 只能作为必要条件，不能代替此次受控调用出处。
4. `persist_owned_return(conn, receipt)` 由 Core 唯一拥有连接／事务，核实际 session／消费票及全部 binding，首次 CAS 保存同 auth DB 的 `financial_return_json / return_digest / received_at`。财务部分只保严格 usage、受控 safe_code、模型／响应摘要及必要私有请求关联；不含 credential、用户摘要、摘录、完整 prompt或原始响应正文。重复相同凭证只回原记录；不同内容冲突保留安全异常并阻断，不能 UPDATE／REPLACE 首个事实。
5. `candidate_json` 是独立可擦槽。候选结构／引用失败，或已取消／撤权时保持 NULL／清除；财务 usage 完整与否分别处理，不把坏正文当免费，也不为了账务恢复而复原候选。候选不成为费用可信来源。
6. `mint_cost_from_return(conn, return_ref)` 仅消费上述真实受控持久来源，并重新核原 binding／mode／producer／记录完整性。现有 `mint_trusted_cost_authority(observation=普通DTO)` 拒绝语义继续保留；新入口不给正文提交或新发送权限。

这些内部签名是实现消费者的最小约定，不代表当前源码已经提供。复用现有唯一 DB、session／approval／permit／reservation／cost 表；如字段不足，Core 须先冻结最小版本化差异，不能由模块另建账本或自行分配 schema 版本。

恢复时可信出处依赖受审 server 写入边界、其消费／收包因果关联以及持久元数据完整性；数据库位置／UUID／hash／状态本身不是外部返回证明。只有这些来源证据都可验证，才可恢复原 receipt。若进程死亡前没有保存完整可信 usage，或恢复时出处缺失／冲突／损坏，则保留 UNKNOWN／held并明确不可恢复；不从普通缓存重造可信 stamp，不新发 HTTP、不伪造逐笔查询或用余额差猜费用。该保证不覆盖已被任意 root/SQL 写入破坏的信任边界。

### 10.3 账务消费与正文提交分离

合法 v2 receipt 沿原合法准入 quote／policy 调唯一受审 `observed_bound`，不因事后 TTL 到期换价。Core 在一个幂等 CAS 事务内核同 dispatch／reservation／版本及原 U，完成 `held-=U; upper_booked+=Uobs`、写原 U／Uobs／一次差额和观测引用，`actual_charge=null`。数学 DTO 不是 release／receipt／资金权限，Core 不复制另一套 F；重复处理、并发及重启回读不得二次扣／退。坏内容而 usage完整仍独立记录 Uobs；usage缺失、矛盾、越界、绑定不明则 UNKNOWN并保全 held U，不裁切、不补0、不重发。旧 fixture／final-policy／v1 历史金额不回放减记，后续可信账单超过 Uobs仍按§6.4.1留事实并阻断。

取消／撤权／删除后，迟到费用可核原已消费的最小财务 binding，不要求旧主体重新获得正文写权；只补必要 opaque账务事实，不改变任务为 RUNNING、不新派发、不恢复正文／报告／分享。删除先按§7封禁，再清批准私密 payload、候选和可擦上下文，必要财务摘要／原时间保留。不得为“重建来源”恢复已清用户材料。

正文提交是另一条当前身份／owner／source许可／epochs／input／task-step版本／stop门禁，只接受同一受控返回的合法候选并再核权限。成本能力不能授予内容能力；内容丢弃不推导费用为0。离线记录的这一分离只证明代码机制，不构成真实费用或真实模型执行证明。

### 10.4 分卡与最小反例

实施顺序为：先本内部契约独审；再最小 owned session／receive／持久来源生产者与故障探针；其后 Core 唯一封边并接六个预算 writer（Bootstrap唯一纯 F仍不拥有事务）；最后组合原 App／API／取消删除／重开验收。公共结果／模式增量、实际资金／loader／secret／live及真实一笔费用仍需独立正式授权，不在本节自动接续。

| 反例／对照 | 必须成立 |
| --- | --- |
| 普通 DTO／伪 receipt／错 conn或PID／任一 binding改变 | 实际 trusted-cost mint拒；同一受控 session真实本机收包为正对照，不拿合成行当真实资金证据 |
| 消费 commit丢ack／父死／收包未持久 | 按原票对账，UNKNOWN保全held且外发至多一次，不换session重发，不用elapsed/PID消失推断未收费 |
| 重复／两进程／金融事务各故障切点 | 同receipt只一次原 U→Uobs；全回滚或读回既有提交，不丢首个观测／不重复退差 |
| 坏正文但usage完整；缺／矛盾／超界usage | 前者正文拒而费用独立记Uobs；后者UNKNOWN全held，不补0／裁切；不是actual结算 |
| 取消／删除在收包前后两序与重开 | 仅保原quote／policy／时间／最小财务凭证，正文新增0、任务不复活；破损或伪持久元数据fail closed |
| 旧v1／offline换标签／未核funding | 旧金额和模式不改，离线model flag仍false，默认paid_disabled及真实运行NO GO保持 |

## 11 无 KB 线索时的现象起步计划增量

本节兑现既有现象解题目标的起步缺口：用户只有自己的现象描述、没有合适 KB 命中，也不预先知道英文方法名时，可以先取得未核提名和可编辑查询计划。它不是已找到成熟解法、已完成研究或新增自主 Agent/search 平台。仅冻结内容与控制契约；不创建 API 路由、表、实现、预算账户、资金 grant、loader或live资格，既有正文与受审边界保持。

### 11.1 显式分支与自有观察输入

新分支固定 `purpose="phenomenon_plan_v1"`、`input_template="SelfObservationPlanInput-v1"`、`candidate_schema="PhenomenonPlanCandidate-v1"`。新的候选 Envelope 使用 `schema_version="structure-research-v1",contract_revision="phenomenon-plan-candidate-01"`，与原 `b1-candidate-01`／`method_hypothesis` 显式区分；这里的v1是新内容分支首版，不是旧报告或旧会计策略v1。当前接口在新版本独审接线前继续拒绝不支持的purpose／版本，不由本节自动接受。

原 `method_hypothesis` 的1..20条合法摘录、完整署名、许可／当前读显／外发权限及 EvidencePacket 约束不变。不能用空 handles、将用户摘要伪装成已读摘录／SourceRecord、填 PLOS read_scope或给旧 DTO 改标签来走新分支。账务仍沿原 `bounded_usage_upper_v2`；输入、返回、receipt及实际模式的additive消费者须后续分别实现和独审，旧 `offline_probe/model_analysis_ran=false` 不改真。

| 输入／关联 | 最小字段与不变量 |
| --- | --- |
| `PhenomenonPlanPreviewRequest-v1` | `{input_revision:Revision,expected_research_version:Revision,purpose:"phenomenon_plan_v1",observation_source:"own_observation"}`；从当前已确认研究修订读取自有观察摘要，不接受正文／URL／附件／source/excerpt IDs／模板／模型／资金／价格覆盖 |
| `SelfObservationPlanInput-v1` | 服务端固定 `{input_kind:"user_observation_summary",summary:Text(1000)}`，summary必须为已保存当前 ProblemRevision.summary 的完整8..1000字符；原文原样保留私有，不截断、拼接或暗取 original_input／附件补进模型包。超限先要求用户修改保存的摘要 |
| 所有权声明 | observation_source只是用户声明，不是服务端版权认证；确认另要求严格 `confirm_own_observation:true`，同用户／当前修订／摘要摘要／时间存为 self_declared，不可生成“版权已核”或第三方文献许可 |
| `PhenomenonPlanBinding-v1` | 服务端绑定主体incarnation／grant／epochs、research/input revision+digest、summary_digest、声明版本、purpose/input_template/candidate_schema、模板与最终bytes摘要、原quote/policy与有效期；问题摘要、输入manifest、最终请求、财务usage各域分别核验 |

服务端核当前owner、读取／写入／付费执行资格、已保存修订／版本、明确输入来源及必要敏感信息选择。用户输入者身份不证明文字自有；路径／字段和已知资料来源可检查，不能靠用户勾选或文本相似度证明版权。已知为第三方长文、附件、已读资料或其绕行粘贴的内容，不可改标own_observation悄作usertext；应让用户改写自己的观察或进入原受许可资料流程。未知归属须如实说明，不能宣称server verified；明确资料疑点未处理不外发。输入不当不扣费，不自动截摘要或付费改写以绕许可。

接§10时，purpose/input_template必须作显式输入分支判别：本分支核input_manifest_digest／summary_digest，原方法分支仍核真实evidence／packet摘要；两者不互赋相等、不填空迁入旧receipt或空摘录分支。金融用量凭证仍只能由受控OwnedSession实际消费／收包生成，提名JSON、用户声明和内容摘要不能mint可信receipt；该additive接缝另随producer版本独审。

预览沿原无能力draft控制，展示完整将外发的自有摘要、self_declared来源含义、新purpose／模板、单次目标、费用保守U与本地TTL。`input_manifest`只描述这一份自有摘要及其绑定，不能充当第三方evidence manifest。新固定模板／代码须由服务端登记、当前quote依据明确覆盖该分支；不能只因模型或价相同就沿用绑定旧method模板的quote／批准。最终 system模板、示例和输入合计≤16 KiB；不把字符数当token硬界，不静默删字段凑包。

### 11.2 有界提名与查询建议

模型只返回下表候选数据，完整候选JSON≤16 KiB；原受控响应原字节／解压上限、4096可计费completion界、零自动重试、无工具、非流式保持。数量与UTF-8字节上限同时成立，超限整次拒绝，不裁剪后称成功。

| 模型候选字段 | 严格schema边界 |
| --- | --- |
| `summary` | Text(700)，只归纳起步思路，不输出结论完成度、已核证据或保证 |
| `candidates` | 0..3项，每项精确 `{label:Text(120),mechanism_hypothesis:Text(700),why_considered:Text(400),method_leads:Text(160)[],key_unknowns:Text(240)[]}`；method_leads为0..2个待核方法名，key_unknowns为1..5项；无模型生成id、来源引用、checked或成熟度等级 |
| `query_suggestions` | 0..5项，每项精确 `{candidate_index:int?,query:EnglishQuery,intent:Text(240)}`；非null index是非bool整数且指当前candidates数组，直接围绕观察的查询可为null；query按当前Source预览既有ASCII字母／空格／连字符、3..160字符规则，去重，intent解释供用户理解和选择，不扩大Source允许范围 |
| `gaps`／`clarification_questions` | 分别Text(400)的1..8项、Text(240)的0..3项；候选和查询都空时至少有一个澄清问题。无法提名是合法不足结果，不伪造方法或固定答案补齐 |

类型、数组／引用／文本和允许范围由代码先验，不靠system prompt或模型自述守界。所有文字沿公开候选主张检查，拒绝无依据成熟／已验证／保证或概率断言、伪引文及来源标识；无URL、工具、command、代码、自动检索或执行字段。显式URI／代码围栏／命令结构整次拒绝，自由文本只作转义显示，不作为任意URL、shell、SQL、模型参数或工具调用解释。数学名词／公式显示不生成 CheckResult、不执行生成代码，不因换符号即标同构。

服务器生成不可变 `PhenomenonPlanResult-v1`，绑定上述输入／purpose／实际返回摘要及原取得时间，保存候选和可编辑计划的初始版本。展示状态固定为“未核机制／方法提名”，文献未检索、数学未检查、机制未验证，研究证据仍不足；这些状态由应用赋值，不接受模型覆盖。可以复用既有reports的独立schema标记白名单section，但不得作为旧ModelReportRecord或已审Source/Method/Claim证据直接入库，不新增公共RecordKind。阶段完成只表示起步草案产出，不能将原研究或完整解题目标标为已满足。

`QueryPlanRevision-v1` 仅是同研究／输入修订下的可编辑建议，最小保存proposal_ref、服务端revision、上述query列表、编辑者来源与digest；修改生成新版本并递增research version，不改原模型提名／原时间，不需要新模型。用户新写的查询可把candidate_index置null并标用户编辑，不能反向声称模型或来源支持。修改问题本身则沿原ProblemRevision创建新修订，旧提名／计划清楚显示历史，旧同意不自动迁移。

### 11.3 人工确认顺序与共享费用控制

1. 用户保存并确认自己的现象摘要；KB无合适线索时可以进入新起步分支，不能因KB分数低就拿旧Ask生成兜底、硬配一个KB候选或要求用户先知道英文方法名。
2. 服务端生成无外发／无任务／无预留的起步预览，显示全部摘要和原quote/最大U/版本；用户核对并严格确认自有观察、具体摘要外发及最大预留，不能从一次来源GET批准或旧研究同意推导。
3. 新确认数据复用原preview_ref／expected_preview_version／input_revision／expected_research_version／preview_digest及两个严格true外发/费用确认字段，再加本分支的confirm_own_observation；只在当前owner／epochs／版本／来源声明／quote与资金权限满足时原子保存独立批准和单次queued计划。不同合同版本明确解析，不能向旧confirmation追加字段冒兼容。
4. 后续唯一受控派发仍须完整当前权限、同经济binding／同ledger／当前币种与预充值、原F的足额U和一次permit；max_calls=1、零自动重试／修复／fallback。现有新鲜资金、CP3实际producer、loader及live放行未齐时仍关实际调用；本节不授予它们。
5. 收到提名后只展示、保存并允许本地编辑查询；服务端不选择一条自动检索，不循环尝试建议，不付费翻译／重提名。没有可用建议时显示缺口，用户可补充自己的摘要后走新预览，未知费用仍先按原规则对账。
6. 用户明确选择或编辑某条查询，再进入现有Source预览、逐次批准／start，绑定当前研究修订、选定plan revision与查询摘要的审计关联；审计关联由服务端当前已保存选择生成，不能向旧Source DTO夹带plan_ref、候选ID或许可字段；Source请求字段、许可、请求quota与实际目标仍按原合同，不直接执行模型URL或新增主机。编辑计划／起步批准都不是Source批准。
7. 取得合法、当前获准的短摘录后，才进入原 `method_hypothesis` 的预览／独立批准／受控执行；其证据／署名／许可门槛一项不减，起步提名不能当检索所得证据。完整现象解题仍须方法证据、条件化迁移与适当数学/实测验证另验，不以此草案替代。

全部派发、幂等、取消／撤权／删除和迟到提交沿§6.4／§7／§10；新purpose/plan/ref/key不重置资金cap或绕未结fingerprint。用量完整但候选坏／越界仍独立按原quote/F记Uobs且actual=null；缺失／矛盾usage仍UNKNOWN+全heldU、无自动重发。删除后只可核最小迟到费用，不恢复自有摘要、候选、查询或分享；当前授权过期不能用同意声明重新取得资格。这里只复用唯一账本，不新增额度、资金账户、余额证明或真实调用授权。

### 11.4 最小用户任务与反例验收

| 场景 | 必须成立 |
| --- | --- |
| KB空／用户无英文方法知识 | 用至少两个未作开发固定答案、无预置KB命中的新现象实际走起步预览与明确确认，得到有理由／缺口、可理解且能进入现Source预览的建议；人工词表／固定三家族／固定真实题答案不算泛化通过 |
| 未同意与阶段隔离 | 确认前模型／费用／Source请求计数0；一次提名后未选择和批准查询时Source仍0。用户编辑及重开不触发模型或搜索；原method purpose空摘录仍拒，不能翻旧may_send或给旧probe改live |
| 输入来源／版本 | 自有摘要8/1000边界与原文完整保存通过；超限不截断，第三方长文／附件／资料绕行或已知来源冲突不外发，勾选不变版权已核；改题／换主体／旧版本批准在实际派发前拒绝 |
| 坏提名与资源 | URL／命令／代码／伪来源／verified标志、无效index、重复／不合法查询、超过数量/16KiB候选或最终包拒；解释和方法名只作未核文本，无数学或成熟解法标签，不执行也不自动补发 |
| 不足、保存与后续 | 无lead有真实缺口／澄清；正常提名与用户编辑各版本可重开、历史标记和摘要一致；合法资料链后才进入原方法报告，不把用户同意、候选名或付费成功当证据 |
| 费用／撤权竞争 | 同key并发至多一次派发，丢ack/UNKNOWN不换purpose重发；新鲜quote/资金缺口仍关，stop/删号/来源疑点处理遵守原门禁，迟到可核费用但正文／计划不复活，正文失败不释放已发生费用 |

以上是待实现的消费与价值判据，不是本轮已经调用模型、检索原文、完成数学验证或兑现最终服务。先独审本增量，再派最小纯类型／固定codec与安全反例卡；Core唯一接授权／事务／保存，实际模式、制品、正常CI及真实用户任务另行验收，不新增搜索／Agent平台。

## 12 Phase B 项目统一预算与最小金融准入

2026-10-17。仅冻结后续离线消费接线的契约，不实现、迁移或开放资金。§10的A阶段真实收包来源不等于预算消费；其合成consumed前置、旧producer或普通SQL记录均不能升级为本节费用能力。§11新purpose的实施独立准入，本节仅支持原method_hypothesis；旧v1会计含义、v5/v6定义及所有历史金额不变。

### 12.1 两道上限与唯一项目绑定

项目授权上限记为P，供应商资金约束记为C及当前保守可用余额B。P表示Owner允许本项目占用多少，不是供应商余额、预充值或付款证明；现funding_account.cap=initial_prepaid−other_use_margin继续表示原资金约束，不能改成P或反向把P算成现金。新增预留须同时满足账务总占用+U≤P、≤C及B足够；所有金额为同币CNY、scale=6的非bool有界整数，不隐式换汇。

选定最小V7增量：沿唯一auth DB复用funding_account.settled／upper_booked／held计数，新增下列两表，不再建第二套计数账本。一个项目固定关联一个稳定经济binding及一个资金账户，不能按用户、key、purpose、phase、重试或epoch新领一份P。

| 新表 | 最小字段与技术约束 |
| --- | --- |
| research_project_budgets | id为PRIMARY KEY且CHECK(id=1)，project_key唯一且CHECK为structure；funding_account_id为NOT NULL唯一FK、economic_binding唯一且非空、currency=CNY、scale=6、authorized_cap=P、authorization_ref／digest、database_binding、mode=offline_probe、status=closed/active/blocked、version。授权ref为服务器登记的opaque依据，非请求字段。 |
| research_financial_admissions | id:Id；project_budget_id FK；reservation_id／permit_id／session_id分别唯一FK，dispatch_id唯一；record_version=financial-admission-v1、producer_version=owned-budget-offline-v1、policy=bounded_usage_upper_v2、mode=offline_probe；snapshot_json为≤16KiB严格金融对象、snapshot_digest、原created_at。此v1是新记录首版，不是旧会计v1。 |

项目行的身份、P、经济binding、账户关联、币种／scale／mode、授权依据及DB绑定登记后不可原位改写、删除或REPLACE；版本单调CAS，status只按受控暂停／恢复转移。资金账户的binding与项目字段须一致，FK／唯一键／固定project_key及跨表guard拒绝别名绕行；创建新账户不能转移该单例或重置历史。需要改授权或换账户另审保留累计占用的迁移，不在本节提供增额／充值接口。

P的登记是独立服务器控制动作，迁移不登记额度、不凭登录激活；缺项目行、无明确Owner授权、错误actor或来源未核都关闭。原资金账户已有同币settled、upper和held全部计入项目，旧v1占用不漏算、不重估；已有占用超过P则关闭新增预留，不删除事实或清零以通过。外部应用共用供应商账户的支出不由本DB互斥控制，仍须新鲜原生余额、other-use margin及有效期这道外部floor；认证成功、旧余额或余额差都不是单笔actual。

### 12.2 原子准入的严格纯金融快照

snapshot_json仅允许下表字段；解析采用严格、extra-forbid、有界JSON模型。不得保存email、浏览器凭据／session generation、用户摘要、摘录、候选、查询、完整请求bytes、原始响应或secret；opaque关联和必要摘要不在公共响应、普通日志展示。

| 金融域 | 必须保存并核对的原事实 |
| --- | --- |
| 项目与主体授权 | project预算ref／原version／P／authorization_digest；同auth DB绑定；account／稳定economic binding／原funding_epoch／币种scale；principal opaque ref及原epoch、grant opaque ref及原version、paid approval ref／原digest、funding permission ref／digest与scope_digest。无grant或research的删除级联FK，不保留身份正文。 |
| 单次消费关联 | task／step／attempt、发送授权版本及实际消费前后版本；reservation／session refs及实际版本、permit ref及prepared→consumed状态CAS、唯一dispatch。现permit没有独立version，不伪造一个版本；保存实际request_digest、evidence_digest、context_digest、outbound_fingerprint、已批准purpose及固定codec代码digest，不接受客户端覆盖。 |
| 原数学与资金依据 | 完整严格UsageUpperQuote、原ReservedUpperMath(U)、原BudgetBasisSnapshot、各canonical摘要、价格ref、F/policy/纯数学实现版本及代码digest；与现不可变price.quote_json、项目／资金行、原确认中已核准U逐项一致，不能从票据抄值再自比。 |
| 原时间与来源 | reserve核价的服务器时间、最终admitted_at、同消费事务recorded_at；满足实际确认≤准入≤服务器当时钟且在原quote/basis有效期内，消费时quote剩余窗口≤60秒。recorded_at不是预填的commit回执；快照存在须来自真正提交的受控消费事务。 |

原basis必须在仍有权限时从已核原批准／资金源取得，不能在删除后根据一个digest、最新余额或猜测字段重建。原quote／F／basis／消费版本及快照正文的摘要互相绑定；原始准入合法性由消费链证明，数学DTO、时间合法或哈希匹配仅是必要条件。

### 12.3 最小迁移与写入防线

V7只追加两表、相应唯一索引及guard，提升schema marker；现v5/v6表定义、旧策略与数据逐字保留，不以重建或回放重写历史。迁移先核旧结构及未知附属对象；不支持、旧结构漂移或半途失败则全回滚，既有正确库保持，B入口关闭。不得把无新版admission的旧A／v2／v1行补标为新来源。

新admission仅在consume事务INSERT一次，禁止UPDATE／DELETE／REPLACE及所有唯一键冲突替换。跨表guard核项目账户、币种、policy、dispatch、session／permit／reservation关联、受控消费状态／版本及严格金融快照；financial_return与新admission互绑，其首次JSON／digest／原时间沿现不可变guard保留。

仅凭表结构、UUID或普通conn.execute不构成来源。冻结连接内受控写许可：Core在实际canonical conn／当前事务／PID／owner lease内核真实Authority后，才临时打开绑定operation及目标行版本的私有write scope；SQLite guard调用该conn的Core校验函数，缺hook或未持有效许可一律拒绝。默认函数拒绝；普通SQL不能设置许可，不能把一个数据库布尔列当钥匙。项目账务列、新admission及有admission的B financial_return均受此防线；candidate擦除独立，不取得账务权。

旧AuthStore／ResearchStore连接工厂须装默认拒绝hook，schema_requirements核完整V7定义与guard指纹；代码／schema／hook任一缺口都不支持B。源安全依赖受审服务器写入与配置边界，不声称抵抗任意root、任意Python或有权重注册SQLite函数／改schema者；同内容复制到未登记DB也不能恢复本项目能力。

### 12.4 六入口及一次性账务转移

所有入口由Core统一拥有conn，不自行connect、commit或建旁账；使用同auth DB的BEGIN IMMEDIATE、实际scope与lease、版本CAS及精确rowcount。发生COMMIT／ROLLBACK或隐式回滚后旧能力失效，换conn／PID／操作、过期lease或旧版本不能复活。网络与响应等待不进入DB事务。

| 入口 | 唯一职责 |
| --- | --- |
| schema_requirements | 只返回受审V7结构和guard要求，不给额度、资金或发送能力。 |
| reserve | CurrentPaidAuthority核当前明确paid grant／actor／原批准和当前source／quote；唯一reserve_bound得U，核项目P、原资金C、保守B及并发占用，CAS一次HELD、held+=U和prepared票／step，不复制F；重复仅核回原记录。 |
| authorize | 同conn／lease重核当前身份、grant/epochs、task-step版本、原项目账户／epoch／U／quote TTL、合法来源和最终固定bytes，不增加额度或再预留。 |
| consume | 一事务CAS permit、reservation、approval、session、task/step及event，并INSERT完整FinancialAdmission；版本定义明确对应消费前后，不能拿prepare旧版本盖当前发送。只有实际commit已确认后才在仍有效lease内由受控transport发送敏感bytes一次。 |
| observe | mint_cost_from_return只消费受保护的新版admission+实际自身finish首次持久return，核producer/mode、原关联及完整性后发仅财务TrustedCostAuthority；旧mint(observation=DTO)继续拒绝。缺任一因果来源不消费。 |
| cancel | 仅实际StopAuthority或经核的删除控制链：HELD且prepared才能一次撤票、held−=U；已consumed／SENT／UNKNOWN不退，转UNKNOWN保全held。暂停或停止不授权换key重发或增加额度。 |

账务写须同时CAS项目／账户当前版本及原票版本，重复消费拒绝；observe使用当前账务版本，不要求它仍等于过去准入版本。项目后续暂停、actor撤权或删除不取消已发生费用的财务核对资格，但不能因此获得新发送或正文权限。无论调用者来自service、runner、取消、删除恢复或后台控制，都不可旁路新入口；旧C0 release／settle等不得操作v2票，未识别策略fail closed，不误当fixture。

合法同dispatch完整usage沿原已登记F实现调用observed_bound；只读原quote和ReservedUpperMath，不伪造now重新reserve，不换新价或丢local_guard。一个幂等事务完成held−=U、upper_booked+=Uobs、reservation→UPPER_BOOKED，append原U/Uobs／一次差额／usage／return_ref，actual_charge=null。总占用不增加；旧v1／fixture金额不迁减。坏正文而usage完整仍独立记Uobs；账务不写SETTLED或“实际零元”。

缺／坏／矛盾／越界／非最终usage、Uobs>U、快照或实现版本无法核对时，保全原held U、置UNKNOWN／必要时阻断新paid；不补0、不裁切、不按余额差算actual。consume回执丢失、父进程死亡或发送结果不明先读原事务结果；“已consumed”也不证明未发，可疑状态不能重建socket、换session／purpose／key发送。

### 12.5 删除、撤权与重启后的仅财务恢复

删除仍先封禁／增epoch，再擦approval私密payload、summary、candidate、授权上下文、原有可擦permit JSON、原始请求正文／私有来源映射及其余§7资料。本节不修改旧擦除语义，而是仅保留新表中受控消费产生的严格最小金融快照和必要不含正文的既有账务记录；未消费的草稿不借“金融”长期保留用户材料。

现有budget_basis_json删除后为空、仅有basis_digest的A记录不具备本节恢复资格；不保留旧完整approvalpayload补洞。新admission在删除前已完整且来源可核时，恢复只读取允许保留的admission／原price／session return／permit-reservation与账户记录，重验严格schema、canonical摘要、producer版本、原消费版本及真实写入因果；不能凭state=received或可重算hash自证。

仅财务恢复可使用保留的opaque principal／gate关联取得真实lease，不要求旧cookie、已删grant或主体重新活跃；能力只能observe原调用，不能新reserve/send、重建正文/报告/分享、恢复RUNNING或给新同邮箱主体额度。源码／schema／最小快照缺失、损坏或冲突则UNKNOWN全held；无完整可信return绝不再HTTP。候选首次保存与幂等重放均独立核当前内容资格，已擦不回填。

### 12.6 分卡与必须实跑的反例

B0只文档独审；B1须完整真实reserve→authorize→consume及快照同落→本机自身finish→持久return→observer闭环，不以合成SQL consumed票作正例；B2再封齐全部调用者、取消／删除与重开。正例仅在隔离的同auth测试DB使用服务器指定actor的OfflineFundingResolver和本机响应，模拟账务不得复制到正式账本冒真实资金或费用。任一卡未闭合全部生产门禁仍prodclosed，mode及model_analysis_ran=false不改真。供应商authenticated observation不等于fresh资金授权，真实loader／credential／live／新purpose另审。

| 反例／对照 | 验收 |
| --- | --- |
| 项目与双上限 | 两用户／任务／进程并发只占同P及同C/B；换key、epoch、purpose、account alias／新建另一account／重启均不重置；P<C及C<P都取更紧值，未授权actor／只有登录／只有认证成功都不获资金。 |
| 写入与来源 | 普通SQL伪造admission/received、DTO／trusted=true、错误DB/conn/PID/事务/lease、替换账户/basis/quote/U/时间/版本、旧A/v1冒新producer均拒；实际受控全生命周期为正例，原单独F绿测不是它。 |
| 原子与幂等 | 各SQL切点故障全回滚，consume丢ack先核回而不重发；双进程同return仅一次U→Uobs，取消与observe竞争不双退，其他writer同时reserve仍受共享上限。 |
| 用量与旧值 | 低量、满量、cache-hit按峰miss、ceil/local_guard通过；正文坏但usage完整保财务；usage缺／矛盾／超界UNKNOWN全held，v1全U、历史actual和已有占用不重放减记。 |
| 晚费与删除重开 | cancel/revoke/delete在接收、持久与observe前后分别竞争，清空进程缓存后仅凭允许金融域核原F并至多一次记账；坏/缺依据不补正文、不发HTTP、不复活任务/分享，同邮箱新主体不继承。 |

新schema／代码、正常CI、原独审、实际funding与真实费用事件是分开的门槛；本节及离线闭环不证明真实预充值、实际模型或对外服务已完成。

## 13 Phase B method_hypothesis 的受保护可擦正文与 typed 存读

本节只冻结当前 `method_hypothesis`／B 的内容来源边界，不实现类型／codec、SQL／迁移、权限／producer、worker或API，不扩大产品方向。§12金融准入与晚费能力不含正文权；§10的进程OwnedReceipt、`response_digest`整包摘要、普通candidate JSON均不能单独证明一份重启后正文的来源。起步计划、公式或其他purpose须后续显式additive输入／结果版本，不能借本节绕旧资料门槛。

### 13.1 资源引用、版本和整体字节边界

最小正文槽候选仍为现有 `research_provider_sessions.candidate_json`，可先用版本envelope承载；这不是“无需DDL／guard”的结论。`result_ref`复用实际既有session UUID，始终是资源引用而非权限，不用digest造server id，不从客户端创建一个session来补洞。

| 对象／字段 | 固定内容与边界 |
| --- | --- |
| `OwnedMethodBody-v1` | 精确 `{header:MethodBodyBinding-v1,candidate:ModelReportCandidate-v1,candidate_digest:Digest,envelope_digest:Digest}`；candidate是受审parser所得合法候选对象，不是完整provider响应或未核原字符串 |
| `MethodBodyBinding-v1`：对象／输入 | `result_ref:Id,research_id:Id,task_id:Id,step_id:Id,input_revision:Revision,input_digest:Digest,approval_ref:Id,dispatch_id:Id,permit_id:Id`；全部来自真实已消费的当前B链，引用关系由Core逐项核，不能只验UUID格式 |
| `MethodBodyBinding-v1`：消费版本 | `approval_consumed_version:Revision,dispatch_consumed_version:Revision,permit_consumed_version:Revision,authorized_task_version:Revision,authorized_step_version:Revision`；指实际准入／消费记录中的精确版本。dispatch无独立可变控制行，dispatch_consumed_version精确引用该dispatch唯一permit的一次性消费版本并等于permit_consumed_version，不虚构新计数器／可写dispatch对象 |
| `MethodBodyBinding-v1`：内容／出处 | `request_digest:Digest,evidence_digest:Digest,financial_return_ref:Id,financial_return_digest:Digest,candidate_schema:"ModelReportCandidate-v1",body_schema:"OwnedMethodBody-v1",producer_revision:Text(64),execution_mode:"offline_probe",received_at:UtcTime`；跨域摘要不互作替身，时间为该次真实收包原时间，producer须受审Core登记 |
| 摘要算法 | candidate_digest为规范candidate对象的UTF-8 SHA-256；envelope_digest为规范envelope去掉自身字段后的SHA-256。金融return及response摘要只做实际因果交叉关联，不能替candidate摘要／内容出处；摘要相同不是授权或科学证明 |

整个envelope含header、candidate及摘要合计UTF-8≤32 KiB，仍在现槽范围内；SQL现有字符数CHECK不替代字节校验。旧候选独立上限不被偷偷放宽，若header开销使合法候选装不下，新正文保存明确失败、费用独立处理，不截断、不删引用凑包、不另存无保护旁文件。未来模式若另版本支持offline/live，字段只描述数据，实际来源与模型调用事实仍须受控receipt；传live或纯codec通过不能把旧probe／model_analysis_ran=false改真。

`ExpectedMethodBodyBinding`、期待摘要和纯codec输出仅是数据。Core必须从实际owned／准入／受保护持久来源取得期待值；不得从同份客户端／普通槽JSON取字段、重算hash就自称独立证明，不以`trusted=true`、finance-only authority或恢复后的`_OWNED`模拟来源。后续纯模块只能校结构／canonical／摘要，不生产CurrentBodySource、grant或OwnedReturnReceipt。

### 13.2 首次实际收包、重放和不可回填

1. 只有该实际session持有的 `OwnedReturnReceipt` 首次处理路径，经过原B消费admission／permit／request／evidence和producer核验，并核当下正文资格，才可构造上述正文envelope；普通ProviderObservation／candidate DTO／传入callback不能替代它。
2. 同一canonical auth DB的受控短事务，以session及实际消费版本做CAS，在financial_return首次NULL→持久事实的同一次写入中，正文合法且当前可提交时写envelope，否则candidate_json仍NULL。金融usage／费用处理不以正文有效为前置，也不因正文缺失推断免费。
3. 首次处理后，只允许在当前仍可读且正文仍存在／完好的情况下幂等回读同一result_ref；不重发HTTP、不重建模型响应、不重复生成新的结果或改原时间。金融重复凭证不自动取得正文重放权。
4. 首次坏正文／权限已终止而为NULL，或后续被擦为NULL，都必须持久防止再次写非NULL。即使后来出现普通候选缓存、源材料重新可读、同邮箱账号或新grant，也不得给该旧收包补签／回填；financial事实不可变与内容关闭条件须被实际guard一起核。
5. 合法erase使用独立、真实当前删除／撤权控制链，清正文及其中的摘要／私有引用，不要求取得财务写能力。擦除与首次保存／重放竞争按同库版本与owner gate线性化；已擦结果不能因崩溃恢复、普通UPDATE或旧receipt复活。
6. 旧A/v1的会话裸candidate或其他无本节proof的会话行，只关闭本节BodySource恢复／提交资格并保原政策必要费用；不取代合法旧报告按既有已审门禁独立读取，不连带删除材料。不得批量封装、回算header或升级producer追认为新来源，旧源码／行存在不是迁移授权。

### 13.3 当前资格、历史边界与 typed 结果

内容来源证明只证明受控收包及保护写入的因果关联，不证明机制／数学正确、文献支持或当前Source权限。每次首次typed提交、幂等重放和read都须Core重新核当前cookie身份／account incarnation、owner／grant／principal及acl epochs、研究状态、task/step/input具体绑定、stop／终态边界、所有source/excerpt版本／hash／Unicode引用及当前读显ACL；finance-only恢复可在删号后继续，而本段读取／提交不得借其绕开正文资格。

发送／消费冻结版本与内容提交／读取版本分域。原admission精确核authorized/consumed版本；后续合法状态转移和内容commit以独立当前预期版本CAS并保存其结果关联，不要求伪装旧SENDING，也不能用`current_version>=old_version`泛放。旧input只遵已采纳的明确历史读取边界，满足当前对象／资料授权才可有标回看；保存本身不新增历史读取特权，不继承新问题的同意，不能当当前修订结果、重新执行或跨人认领。

Core在已核同库读事务中从受保护、未擦、未损坏的新正文来源建立仅当前消费的内部BodySource；不是反序列化普通JSON成OwnedReceipt，也不是用户自报header。重启清空进程registry后仍须验证准入→实际收包→受保护首次持久的来源／版本完整性；缺hook／旧producer／未知版本／绑定或摘要不符均拒，不能降级到raw candidate或金融return补正文。

typed提交复用既有ModelReportCandidate的严格结构／公开主张和引用校验；生成的机制／变量／条件／竞争解释／验证计划仍是 `hypothesis/llm_inference/unreviewed`、`qualified_report+INSUFFICIENT`。不接受模型check id／checked，不由本节关联假数学检查，也不把schema／精确短引通过当科学支持。原ModelReportRecord接受普通observation的纯构造不是本节受权提交入口；需要additive消费BodySource并保持原离线含义。

最小公开 `MethodHypothesisResultView-v1` 只给result_ref、原input_revision／input_digest、candidate/body schema、producer版本、received_at、is_historical、实际模式、固定离线model_analysis_ran=false、报告/evidence状态与已核候选sections、具体source版本／引用和limitations。不能dump私有header、完整CallContext、permit／admission、财务凭据／账号、full extracted或原响应；各类型／引用／整体响应沿现白名单及512 KiB边界。重开保持同一result_ref／内容摘要／原时间，不能每次读重造server id，digest不作为对象id。

v2 typed commit/readback以其真实完整usage／UPPER_BOOKED与当前内容资格门禁为前置，按§6.4.1和§12保actual=null；不得调用旧FixtureRunner.commit_result的SETTLED专用路径、将账务假改SETTLED或伪actual让旧流程通过。不能把ModelReportRecord JSON塞notes让前端自行解析；结果存读与当前ResearchView的明确关联须Core唯一冻结，不称现有D1 reports即为本节通用结果库。若不能复用既有受保护slot／typed报告协议，先报最小版本化接缝，不另造通用结果平台。

### 13.4 尚未闭合的技术前置与分工

**当前candidate可擦槽允许任意UPDATE，故现状不具备本节正文来源保证。** Core必须先冻结版本化的默认拒绝nonNULL普通SQL／缺hook／错scope、仅实际首次来源可写、合法erase独立能力及无refill保护，并核canonical连接、实际事务、PID／lease与目标行／版本。仅在Python函数前加检查或envelope多一个hash不够；具体最小SQL guard、既有state可否复用、迁移版本／结构指纹及故障回滚由Core审定，本文不宣称无需DDL或已能保存。

该前置须由Core与实际request proof、真实deletion job／lease及既有恢复门禁统一冻结，不给并行模块抢写这些接缝。金融guard与内容guard分别授职，财务观察／admission只金融；erase不变新财务mint，body来源也不授权预留／发送。已删主体迟到完整usage仍可按原最小金融域至多一次记账，候选、报告、task、分享和旧权限不复活。

实施顺序：本契约独审→另GO至多两纯type/codec模块及其tests（只校本envelope／期待数据／32KiB／安全错误／白名单）→Core唯一保护写/擦/重启reader→当前v2 typed commit/readback／Notebook实际闭环。Core拥有paid_provider_session.py、必要store/financial_guard差异及model_report/service/projection/runner接线；实际allowed_paths由停写检查点给定，不由本文授予全部文件写权。纯模块不得mint来源／授权、写SQL、创建worker、接API或真实资金；plan/公式另purpose后审，不泛造平台。

### 13.5 必须独立实跑的消费者反例

| 场景 | 必须成立 |
| --- | --- |
| 实际收包与重启typed读 | 原真实受控B离线链首次持久body+金融事实，清空_OWNED后仍可在当前权限下读同result_ref／摘要／时间；纯codec/data fixture不替这个来源正例 |
| 伪body／写入防线 | 普通SQL/UPDATE/REPLACE、缺hook、仅finance authority、旧DTO、重算candidate/envelope hash、错producer／绑定／quote／schema不能造正文；实际首次receipt+当前资格为对照 |
| 首次NULL／擦除与竞争 | 坏正文或失权首次NULL不可补写；保存、erase、重放并发及各事务故障切点不留半来源，擦后重启／同邮箱新incarnation／旧key／候选缓存均不refill |
| 当前与历史边界 | 来源许可／epoch／输入／task-step版本变化逐项拒越权；合法历史只能按原规则有标回看，不靠>=version或新问题同意放旧正文，不伪造当前状态 |
| 账务独立与旧记录 | 坏/擦正文不妨碍可信usage按原F记Uobs／actualnull，缺usage仍UNKNOWN全held；latefee不恢复body，旧无proof历史只closed，不改SETTLED／notes借道 |
| 字节、白名单与科学边界 | envelope含header真实UTF8超32KiB整次拒，未知／嵌套字段／坏Unicode／重复key／非finite及安全异常不泄原文；public typed内容仍未科学／许可验证，不因模式字段、数学词或费用成功升级 |

本节没有真实外网、模型、资金、保存或产品验收收据；只明确B2-B前的最小共享条件。新实际模式、资金／loader、完整正常CI和最终真实用户任务依然分别验收，不能以协议或纯模块通过代替。
