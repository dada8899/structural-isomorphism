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
