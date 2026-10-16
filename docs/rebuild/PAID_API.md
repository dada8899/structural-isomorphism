# 离线付费预览／确认 API 检查点

2026-10-17，Core；基线 `bd027a00858996d22eee21207fea4e24b3642df2`。仅接已审§6.4.2两POST、严格请求与公开白名单，不接UI、runner、资金、CP3或live。

`POST /api/research/{id}/paid-previews` 的 Envelope.data 仅 input_revision、expected_research_version、1..20个不重复excerpt_ids、purpose=method_hypothesis。`POST .../paid-approvals` 仅 preview_ref、expected_preview_version、input_revision、expected_research_version、preview_digest和两个严格true确认字段。原64KiB JSON／重复key／extra拒绝继续，最终出站仍16KiB，不截断；两入口不接受query字段。

沿原canonical direct cookie/JWT、代际、共享凭据冲突、Same-Origin／CSRF及Idempotency-Key。Bearer-only和失效cookie不能救活；owner来自服务器当前身份，不来自请求。跨用户／路径不匹配对象404，格式422、超限413、版本／失效preview409、资金未核503、旧未知409，错误不反射正文或控制对象。

默认resolver=None或错误类型均真实BUDGET_UNVERIFIED 503，schema active行／普通env布尔不能启用。不创建draft/task/grant/reservation/permit/fee。唯一正例通过服务器app.state显式装配已审OfflineFundingResolver，绑定唯一允许actor，始终offline_probe；请求没有安装／选择resolver的入口。

preview响应只出§6.4.2 PaidPreviewView白名单，不序列化内部mode/excerpts别名、quote全配置、account/basis/authority。含完整已核署名与短引manifest、原quote摘要/UTC时效、CNY最大U、actual=null、model_analysis_ran=false和may_send=false。公开Envelope UTF-8≤512KiB，超限拒绝。

confirmation只消费preview并原子创建独立paid grant/queuedtask，既不预留也不派发；响应只PaidApprovalView，不含step/Context/费用控制。读回按原approval.task_id取当前ResearchView，旧cancelled不会拼新queued。无BackgroundTasks、自动worker或fixture runner代跑。

preview幂等在owner gate+同库事务内记录；原key只回未消费且未过期、原source/quote/输入/代码绑定仍有效的draft。confirmation请求摘要包含完整公开客户端data；同key同body在当前读取权限下回原批准/原任务当前状态，同key异body409，不重建。quote后来过期不使已提交key变新扣款申请；删除／撤权／源读取失效后不回私有素材。

测试走真实路由/auth/同DB及原main挂载（只不启动无关model/index lifespan）；服务器测试装配offline resolver，不mock auth/业务返回，不新增测试env后门。覆盖默认关闭／假资金字段、严格bool、CSRF/重复JSON/限额、跨号/同邮箱新代际/失效凭据、并发确认、实际提交后丢ack故障再回读、TTL、撤权删除、原任务重放与白名单。所有预留/permit/cost/session计数保持0；测试client/log handler/sys.path按finally收尾。

最终新API组40 passed／0 skipped（42.40秒）；此前38项API与旧权限／内部服务组合199 passed／0 skipped（103.09秒），后补“确认默认关闭／只读owner只能preview”两例已独立包含在最终40项。基线最小69项通过。当前300元Owner上限记录不是fresh balance/auth，仍无实际1P/资金/模型/厂商请求或收费。OpenAPI快照留后续集成Bootstrap统一生成，未在本卡越界更新。

## 0acf3e5 原审两项 P2

旧worker自动挑选仅限当下已启用且支持的c0-fixture／D1策略，所有选择条件均加策略范围；显式paid或未知策略在写入前明确FEATURE_UNAVAILABLE，不再误进旧fixture路径或堵Source，未增加paid worker。最终codec仅typed ProviderFailure('request_limit')在两个paid POST映射PAYLOAD_LIMIT/413，其余错误保持原语义，不把任意异常都称超限，不改16KiB。

新增原测试外的真实对照覆盖C0开／关先paid再Source、连续自动两次及显式Source实际两GET、显式paid拒且queued不变；1000 Unicode摘要配三条各1000字符合法原span返回413且业务计数不变，两条200对照；其他codec失败不映射413。原审两脚本原样实跑2 passed，新增5项独立通过；原API/c0/D1完整124 passed／0 skipped（137.02秒），旧API全部方法/断言AST保持。无DDL、阈值、F、成本来源、实际发送或资金放行，资源按原finally收尾，停写交原审查者。

## 严格公开响应接线

2026-10-17。两POST仅补requestBody／200／安全error的OpenAPI声明；仍用Request和原手动stream codec，保持enabled、cookie身份、CSRF、key、query及64KiB／duplicate／strict检查顺序。实际成功返回前调用受审validate_success_response，两paid操作的错误体调用validate_error_response；其余API沿原路径，快照由Bootstrap统一生成。

响应校验、错误体构造或序列化失败返回固定RESPONSE_UNAVAILABLE／503、retryable=false及原no-store／no-referrer，不反射输入或异常上下文；独立最小错误体不递归依赖坏validator。文案说明可能已保存并保留原操作标识核对；已提交确认不回滚，不换key重建或重发。真实业务sqlite／OSError仍为原STORE_UNAVAILABLE。真实auth／DB故障测试验证同key核回与取消状态、严格money／flags／extra及元数据；本增量不提供预留、供应商派发、实际费用或生产放行。

作者最终验证：新接线37项与原API／public DTO合组172 passed；原保存／生命周期／D1／C0另组149 passed，均0 skipped。原pure helper与全部旧测试逐字不变；原identity／manual parser／enabled及其他route定义AST不变。当前仅本地候选，待当前SHA独审，未生成OpenAPI快照或宣称生产可用。
