# 财务结果纯适配器检查点

日期：2026-10-17。基线：`b68e18b96bbe4c5225e7f03fcbb01abc157d75fd`。本检查点仅新增纯适配器、合成测试和本说明，原五文件执行器及 CONTRACT_SPEC 不改。

适配器完成受控 registry 的结构绑定、真实有限计算、保存内容序列化与重开白名单投影；**没有数据库、账户授权、API、CSRF、CAS、迁移、页面、模型、网络或计费实现**。所有金额和来源对象来自既有 synthetic fixture，不是字节数据或预测。

## 给 Core 的内部接口

| 接口 | 输入与输出 |
| --- | --- |
| `resolve_financial_registry(binding, ref, server_record)` | 只接受服务端提供的 typed ServerFinancialRegistryRecord；核研究、ref/revision/digest及每个 SourceSnapshot 的完整映射，冻结为 ResolvedFinancialRegistry |
| `evaluate_financial_candidate(operation, resolved_registry, binding)` | operation 为完整四字段 POST 正文；核64 KiB、输入修订／请求摘要，调用原 evaluate_financial，输出只由计算路径创建的 ServerFinancialCandidate |
| `prepare_financial_record(candidate, resolved_registry, *, result_id, created_at, research_version_at_commit)` | 只接受计算出的 candidate，加入 Core 生成的元数据并核完整保存记录≤128 KiB；不接受 JSON 盖章，不产生签名／trusted 标志，也不提交数据库 |
| `project_financial_result(record, resolved_registry, expected, *, current_input_revision, view)` | expected 必须是 Core 从受权不可变元数据另取的 FinancialResultExpectation；核完整记录、canonical bytes／摘要及输出结构，再投影 summary/table/chart；不重算财务 |

这些是纯模块接口，不冒充§6.5带 conn／identity 的正式服务包装。Core 后续唯一实现当前身份／grant／来源读显授权、同库 owner gate／事务／CAS、幂等、删除及真实 API；不得把 HTTP 正文反序列化为 server_record、expected 或内部 candidate。typed 对象、digest和候选均不是权限或来源真实性证明。

Core 必须真正核 source_record_ref 对应记录、版本、摘要、读取范围及本研究授权；本模块只核引用结构和财务快照摘要，不访问实际 SourceRecord。registry 映射须作为该不可变 ref 的服务端关联保存，不能在重开时任意换链接。读取／提交都需重新核权限，不能拿本模块成功替代 ACL 或跨账户验收。

## 摘要与保存边界

- `binding.input_digest` 是外层研究问题修订摘要；`binding.request_digest` 是包含 expected_research_version 的完整 POST 规范摘要；`canonical_snapshot.input_digest` 仅核原执行器的 FinancialRequest+registry 摘要。三者分别校验，不按同名相互比较。
- snapshot_digest 是原 canonical snapshot 的 UTF-8 SHA-256；registry digest 精确绑定原 registry，来源映射另核每个 source snapshot。原币、期间、原值、口径、curated 来源层级与原文来源区分均保留。
- Core 的本地提交须将 research version 精确加1；保存的 research_version_at_commit−1用于重开复原原 POST 的 expected_research_version，再核 request_digest。若后续改变该提交规则，先协调接口，不能猜版本或绕开摘要。
- Core 应在实际写事务内保存由此序列化且未经后改的完整记录，以及独立不可变元数据／摘要；read 的 expectation 不得从不可信 snapshot／浏览器或其自报 digest 推导。模块不承诺恶意 Python／数据库管理员篡改全部可信元数据后的权限或真实性保证。
- 重开逐项核固定 producer/policy、原 request/registry、年度／币种、字段白名单、原始金额与6位 HALF_EVEN 展示、成本及业务结构、引用／敏感性绑定、缺口和资格状态。只读同一份快照投影，既不重跑 evaluate，也不自动修复坏数据。
- table/chart 只返回明确白名单；不暴露 retained_original_ref 私有原文句柄。来源是否可显示仍由 Core 在投影前核定。每次返回独立 JSON 视图，调用者改返回值不能改候选或后续读取。

## 资源与用户含义

原计算的 Decimal50、5000步骤及合作式2秒规则保持；适配器另按每次调用合作式2秒、JSON深度32／20000节点预检，拒绝非 JSON 数值、重复 key、孤立 surrogate 和过大字符串。输入操作≤64 KiB；request+registry、完整保存记录及最终含 Envelope 的各视图分别≤128 KiB。不是 OS 抢占隔离，也不保证数量上限全部满载仍可装下。

same_as 展开后的 table 若超限，只拒该视图；已保存记录、summary/chart保留，不截断来源或降精度。原缺值／冲突仍 null，不连缺失点；营业利润不由净利／EBITDA替代，业务未分配不强配。摘要含具体缺口代码和假设索引。

计算状态固定 calculated_under_assumptions，model_analysis_ran=false。必要数值／构成不足或机械假设示范为 not_met；其余只到 not_assessed，不能由纯适配器判定 U2 通过。可选净利缺失保留，不因此伪造净利，也不阻断有显式成本的条件营业利润计算。

## 本轮证据与未验范围

固定既有 Python 3.11 环境运行原34项和新增31项 unittest，共65项通过。覆盖独立金额 golden、摘要分域、来源类型／映射、篡改与伪 trusted 输入、重开不重算、历史输入标记、表图同摘要、缺 FX／净利、敏感性、输入／步骤／deadline与实际 same_as 展开超限。静态依赖检查及真实执行中的网络／SQLite禁止对照均通过。

实际容量反例使用两情景五分类：完整记录可保存，table 展开超过128 KiB而拒绝，summary/chart仍可读。所有测试均为 pure synthetic；未执行真实保存、重启服务、撤权删除竞争、跨账号 HTTP 或真实 U2 取证／验收，独立代码审查另行回收。

原独审 P2 返修：完整 POST 摘要匹配也须先将 registry_ref 按严格字段、UUID、整数版本和摘要实例化，再比服务端引用，避免 Python 的 true==1。新增反例在原代码复现一次真实纯执行器调用；返修后 bool／float／字符串版本与坏字段在计算前拒绝，合法整数版本仍仅计算一次并可重开三视图。
