# 付费账本 schema5 与控制端口

日期：2026-10-17。Core 为唯一迁移与控制源码 owner。实施基线 `742c0732627ab34f78139e82b17cb7b65b62a83b`，分支 `codex/structure-paid-schema-20261017`。版本与精确 DDL 以 `research/store.py` 的 `PAID_SCHEMA_VERSION / V5_SCHEMA / V5_AUX / V5_GUARDS / COST_SCHEMA` 为准；`paid_control.schema_requirements()` 只返回不可变需求与定义摘要，不建表、不分配版本。

**本轮只完成数据库安全前置和停止授权。** 没有 upper_budget、付费批准生产者、证据 may_send 读取来源、可信 provider 费用来源、资金 provision、loader、live 工厂、runner/API/页面接线。`CurrentPaidAuthority` 和 `TrustedCostAuthority` 都不能仅凭 DTO 被生产：缺来源明确拒绝。不能据此宣称全部共享端口就绪或资金可用。

## 原表的精确增量

| 表 | v5 增量／约束 |
| --- | --- |
| `research_grants` | `version` 默认1；状态、scopes、principal/acl epoch 变化由触发器递增，不能回退 |
| `research_tasks / research_steps` | policy 增固定 `deepseek-bounded-upper-v1`；步骤增 `model_report`，不扩大既有 position 范围 |
| `research_funding_accounts` | 原 `binding_id UNIQUE` 仍标识同一经济账户，唯一 cap 不另建；新增 provider、initial_prepaid_units、other_use_margin_units、upper_booked。fixture 原模式／10000 cap／USD6 不变；live 默认 unverified、cap/held/upper=0，没有预充值依据。已登记 B0/M/cap 不随 epoch、余额、别名重置；账号身份／币种不可改 |
| `research_balance_snapshots` | 新增 upper_booked_at_observation=0、funding_epoch=1、basis_evidence_digest；原行／ID／余额／有效期保留，禁止 UPDATE |
| `research_price_revisions` | 新增 policy_revision、quote_json、quote_digest；fixture 的 account/operation 唯一性改为 partial unique，原值不变。bounded 只用固定 model_report 和严格 PriceQuote；同账户币种／scale 必须相同，旧算术不能解释新价表 |
| `research_reservations` | 新增 UPPER_BOOKED 和 policy_revision、principal_id、auth_scope_digest、outbound_fingerprint；原 max_cost 即完整 U，UPPER_BOOKED 的 settled_cost 为 NULL。旧 policy 不能变更，旧 UNKNOWN/SETTLED 不追认为 UPPER_BOOKED |
| `research_dispatch_permits` | 增加 policy、request/evidence/price/budget_basis/context 摘要、basis/context/gate JSON、授权 task/step version。JSON 可在将来删除流程清空，必要财务摘要保留；现有删除流程不自动获得 paid 正文恢复权 |
| `research_cost_observations` | 唯一新增的 append-only 财务观测表；不是第二资金账户或 cap。字段为 id、account/reservation/dispatch、policy、kind、response_digest、usage_ref、私有 provider_response_ref、仅用量 usage_json、observation_digest、reserved_upper、booked_upper、actual_charge、usage_priced_estimate_units、price_revision、basis_digest、safe_code、observed_at。首轮 actual_charge 必须 NULL，禁止正文／任意用量键／字符串用量；不可 UPDATE/DELETE |

金额按同币 scale6 的63位非负存储整数约束，不能用浮点列或外汇推算。没有把 `S+UB+H<=cap` 做成全表 CHECK：真实异常事实即使超 cap 也须可保留并 blocked，准入和所有旧 writer 封边仍属于下一 Core 卡。此处字段／SQL约束通过，不代表已经存在这样的 writer。

关键唯一键：

- 旧 id、step、operation_key、dispatch、reservation 和 receipt 唯一性及 FK 保留。
- 未解收费操作：`UNIQUE(account_id, principal_id, outbound_fingerprint)`，仅 bounded 的 HELD/SENT/UNKNOWN 生效。principal_id 是不可变 incarnation 身份，索引没有可变 principal/grant/funding epoch，也没有 task/key/authscope，因此不能旋转它们绕 UNKNOWN；主体隔离也不被共享账户取消。
- 费用观测：`UNIQUE(dispatch_id, observation_digest)`；每 dispatch 最多一条 estimated_upper。冲突仍须后续受控 observe 留异常并阻断，不能把约束失败当未收费。
- idempotency 与此阻重键不同：沿用既有 principal 命名空间，未来消费方还必须绑定当前 authscope，先核授权再回读，不泄露其他主体结果。

## 事务与能力

只有 `ResearchStore.transaction(write=True)` 注册的当前同库事务可以 mint。控制能力绑定实际 conn、事务生命周期、PID、operation、真实活跃 OwnerGateLease.identity 及当前 DB 事实；commit/rollback/退出后退休，同一 conn 再 BEGIN 也不能复活。只读事务、跨 conn、旧 lease、普通 dict/bool/Pydantic DTO 均不授予权限。

当前真实生产者是 `mint_stop_authority(...)`：当前已验证账户的 owner/write、task/version、grant/version、owner/acl epoch 与输入；或同库真实 pending deletion job、账户 generation、gate、数据库 binding。`StopAuthority.require(conn,"cancel")` 每次重核，返回冻结 StopBinding（主体／task／task_version、scope摘要、可选删除job、门身份），不返回内部授权明细，也不给予 consume 权；未来 cancel 消费方须比对传入 task/version 与该绑定。`mint_current_paid_authority(...)` 先核 typed CallContext 与当前 task/step/grant/输入；付费批准和证据外发来源尚缺，始终 fail closed。`mint_trusted_cost_authority(...)` 不把正常 ProviderObservation 视为 transport provenance，也始终 fail closed。

事务 owner 是 Core：upper 函数将来只借用既有 conn，要求 active write transaction/FK ON/schema5，不能 connect/commit/rollback。consume 的 Core 回调必须结束短事务并确认 commit 后才返回给 transport；网络和 loader 不放在数据库事务中。结果不明先按当前授权只读回查原 permit/reservation/观测，不重新外发；实际恢复入口及来源是下一 writer 卡，不在本轮伪造。

未来 upper 模块只允许六入口：`schema_requirements()`；`reserve(conn, CurrentPaidAuthority, intent)`；`authorize(conn, CurrentPaidAuthority, permit, prepared, gate_identity)`；`consume(conn, CurrentPaidAuthority, DispatchApproval)`；`observe(conn, TrustedCostAuthority, ProviderObservation)`；`cancel(conn, StopAuthority, task_id, expected_task_version)`。当前后三类付费来源尚不具备合法 positive capability，Bootstrap 不得用 test-only mint 宣称授权正例或猜另一套表。

未来核账必须检查同 DB 总 held 包括本票；交 Provider 的冻结 basis.held 排除本票 U，让其 admit 只加一次 U。真实完整 usage 才可全 U 转 UPPER_BOOKED、actual=NULL；未知保留 held，不重发，不套免费 GET 闭合。实际扣费依据、退款、充值、FX 不新增通用入口；迟到账务与正文提交分离，不能复活被取消／删除任务。

## 迁移与验证边界

生产 fresh 依次旧3→4→5；真实 v1 修复后到5，未知版本拒绝。v5 专用连接在 BEGIN 前 FK OFF 并读回，BEGIN IMMEDIATE 内严格核旧表／附属结构，复制原列、替换、重建必要索引／触发器、全库 foreign_key_check、写版本并提交；finally FK ON 读回后关闭。任意故障整体回滚原 v4。没有生产降级或跳迁移开关。

必要兼容例外由 PMO 明确批准：六条旧生产 INSERT 和一条旧测试 INSERT 只补原列名，values/参数/金额/条件保持；旧 D1 v3→v4 测试专属 fixture 生成真实 v4，保留原故障切点／回滚／金融数据／inode 断言；旧 v1 用例先生成真实旧形状，再实际迁到5。不是把 v5 多余列留着只改版本号。

新增测试使用自建本机 auth/HTTP fixture 和合成整数金额，覆盖同一真实 v4 库中 HELD/SENT/UNKNOWN/SETTLED、receipt、原锁 inode；全部54个表替换、元数据填充、索引／触发器、版本／commit故障切点回滚；未知版本、63位／币种／cap不重置、原 policy 不洗白、append-only cost、原始正文拒绝、不可绕的 incarnation/outbound 索引；当前 owner 和真实删除任务的 StopAuthority 正例，以及普通 DTO、跨事务／连接、过期门、撤权和缺 paid/cost 来源负例。用量／SQL合成记录的约束对照不是实际资金或可信收费来源验证。

验证阶段：固定首轮定义后，原472项加当时新增72项合跑 **544 passed**、浏览器 **22 passed**。最后收紧 SQL 常量校验、统一 StopBinding，并将迁移故障覆盖扩大到全部54切点后，新增组 **90 passed（40.37秒）**；最终同一固定运行时代码的完整后端 **562 passed／0 skipped（190.31秒）**。中途曾边补强 DDL 边跑跨进程测试，出现两个子进程提前退出；当时父子可能载入不同代定义，但未从被抑制的 stderr 确认直接异常，该次失败不计通过。固定代码后，两项独立重跑、完整544项及最终562项均通过。没有放宽原信号／超时或旧断言。

当前不得宣称所有旧 writer 已计入 upper。它们的唯一行为变化只是显式旧列名；预算／runner／投影／删除 paid 适配仍须后续唯一 owner 卡。发布、真实付费、Linux/VPS 与产品验收均未在本轮放行。
