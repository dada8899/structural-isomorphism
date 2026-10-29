# DeepSeek 有界 producer：独立模块候选

日期：2026-10-17。负责人：Bootstrap；Git 提交与接线负责人：PMO／Core。基线 `210962009680e626f156ac85a5c52a4ca551d3a6`，分支 `codex/structure-provider-adapter-20261017`。本卡仅新建三个 producer 文件、两个测试文件及本文，不修改 C0、D1、D2、数据库、API、页面、旧收费入口、契约、依赖或 CI。

## 当前可以证明什么

公开 `DeepSeekAdapter().preconnect` 固定拒绝 `paid_disabled`，不解析 DNS 或读取凭据。唯一可运行入口明确叫 `offline_probe`，使用调用者提供的本机连接与假凭据能力；所有观测、报告均标 `offline_probe`，`model_analysis_ran=false`。这不是已经接通真实模型或允许上线。Core 后续必须明确批准 live 工厂／模式及真实受控 loader 的接线，不能私改 probe 标志或拿离线观测冒真实记录。

`provider_schemas.py` 提供冻结、严格、禁止额外字段且可重验的 DTO，以及同币整数算术。`provider_adapter.py` 仅生成固定请求、受控发送和观测；`model_report.py` 将合法候选映射为服务器生成 ID 的假设记录。模块不创建或打开数据库，不预留资金、不结算、不推进任务，也不修改原 D1 notes 类型。

## 接口与发送边界

`prepare_request(summary, EvidencePacket)` 产生规范 UTF-8 请求字节、request digest 和 evidence digest。请求只允许固定 `deepseek-flash`／声明版本 `DeepSeek-V4.1-Flash`、`POST https://api.deepseek.com/chat/completions`、非流式、JSON object、thinking disabled、max_tokens=4096、无工具、零重试。完整模板／示例／问题摘要／短摘录包≤16 KiB；不发送提取全文、principal／grant 控制对象或私有计费绑定。

`preconnect` 建立独占连接及最多60秒绝对网络窗口，不发送 HTTP、凭据或问题。固定公共传输实现仅选择一个已核公网地址，直连443，核真实 peer 与所选地址一致；TLS 使用系统验证和原始固定 SNI，禁止代理、重定向、换模型或换地址重试。DNS 单独由只含固定主机名的解释器子进程解析，不携带凭据、输入或环境；父方 timeout 杀死并回收，子方另有 kernel alarm。子进程绝不发送 HTTP；实际 POST 只由持 gate 的调用者 PID 发送，父死后没有可继续发 POST 的派发子进程。公共入口仍关闭，公共传输检查全部使用拦截，未运行公网 DNS/TLS。

`begin(connection, lease, permit, price, basis, current_authorizer, consume_permit)` 只接受真实活跃 `OwnerGateLease`，仅调用其公开 `identity`，不读 FD 或私有方法。验证账号／binding／funding epoch、研究及 grant 上下文、完整请求／证据／价表／预算摘要、价表 token caps 与有效期；受控回调必须返回精确 `DispatchApproval`，不能返回客户端布尔。loader 按 permit 的 opaque binding 取用假凭据；之后再次准入，再调用受控原子 CAS 消费回调并核 `ConsumeReceipt`。当前授权、持久唯一 dispatch／permit 及预算的真伪仍由未来正式服务器能力负责，DTO 本身不是授权。

消费完成后在同一 lease 范围内实际 `sendall`，短发送 timeout≤2秒，先标可能发送再调用网络；失败统一给安全错误，可能消费／发送时留待调用者记 UNKNOWN，不伪称未收费。实例内另防重入与 dispatch 重放；此集合不是跨 worker 的持久幂等。原子消费回调必须结束短 DB 事务才返回，模块不会在网络等待中保留 DB 事务。

`finish` 在 gate 外读响应。绝对计时器关闭当前 socket，使慢 TLS、慢响应头和慢字节流不能按每次 read 重置等待；HTTP 头和原 body 累计≤128 KiB，gzip 解压后另≤128 KiB。拒绝重复／歧义长度和编码头、非 JSON MIME、异常状态、截断及超限。模型名／已登记 fingerprint 不符保守拒绝；不回传原响应或原异常。结果候选仍须当前 evidence authorizer 核对；撤权／取消后只有费用观测可保留，正文丢弃。`reconcile_capability=unsupported`，没有 fixture receipt URL、余额查询、余额差猜费或自动补发。

**窗口边界**：60秒覆盖本模块 DNS／connect／TLS／HTTP 等待和禁止过期发送，不是对任意 Python 注入回调的强制终止保证。测试 seam 与未来 current_authorizer／consume／loader 必须是受控、同步、有界能力；SQLite 回调须复用正式短事务与忙期限，loader 宜在网络窗口前准备为有界内存能力。恶意或无限阻塞的回调不是本模块可安全杀死的网络子进程；Core 接线需实测其期限，未验证不开放 live。没有为此增加通用 watchdog／调度平台。

## 费用与报告

`BudgetBasisSnapshot` 冻结初始纯预付、风险余量、cap、币种、funding epoch、实际／upper／held 与价格版本；要求 `cap=B0−M`，`actual+upper+held+U≤cap`，并核保守可用余额。此处 `held` 是新 reservation 之前的其他占用；Core 在发送前回调必须以真实同库状态重核本 dispatch 的已预留 U，不能再次预留或把旧快照当当前余额。本模块只验不可变控制输入，不保证并发 writer 已接线。

`U=ceil((C_bound×峰值cache-miss输入价+O_bound×峰值输出价)/1M)+local_guard`，采用63位非负同币整数、溢出拒绝；USD/CNY不换算。C_bound≥1,048,576是对文档“1M”的登记保守解释，不是本轮 tokenizer 实测；O_bound 默认393,216，只有已登记全部 completion 参数上界依据才允许4096。价格／模型／上界来源摘要及有效期由正式 owner 核，不把 DTO 构造成功当官方当前费率已核。ceil／guard是本地保守政策，不称官方舍入。

usage 必须严格整数非 bool、prompt=hit+miss、total=prompt+completion、缓存明细一致、reasoning≤completion且不重复计价，超上界阻断。完整可信 usage 只产生 `estimated_upper`／UPPER_BOOKED **意图**：保留完整 U，actual=null；usage priced estimate 不释放差额。usage ref 绑定 dispatch、完整请求／证据、模型、价表及响应摘要，不能跨请求挪用。缺 usage、冲突、丢响应或来源不确定则 `unknown`／held；不能写零或伪造 final actual。真实异常扣费、财务依据、UNKNOWN→UPPER_BOOKED 恢复、跨 worker CAS 与后续实际结算均留 Core 同库集成，不在本模块假做。

`ModelReportCandidate-v1` 严格 JSON≤32 KiB，拒额外字段、重复 key、NaN、空／截断、数量／长度越界、工具／URL／自造 ID、level 或 checked。引用只能匹配当前受控包 handles；包独立检查 display 和 may_send、具体 source revision／excerpt ID、提取文本 hash 与 Unicode `[start,end)` 精确短引，仍≤20词／1000字符。当前提交再次经 authorizer；这只证明引用准确，不证明语义支持。

服务器生成不可变 `ModelReportRecord` 和 `HypothesisClaim`，保存摘要及版本化短引引用，永远 `hypothesis/llm_inference/unreviewed`，首发 `qualified_report+INSUFFICIENT`；不会把市场模型硬塞三 Family。`check_refs=()`：本独立模块不接 D2，不接收模型 check id，更不自行写 checked／computed。后续只有正式 owner 关联真实同研究同修订、相符 policy／公式版本的 CheckResult，才可表达其实际范围；当前无“已算”结果。records DTO 白名单、ReportSnapshot 持久映射、迁移和页面显示均未实施。

## 本轮验证与交回

所有测试使用 Python3.11.15／现有依赖、纯 DTO 或本地 TCP。已测固定请求包／字节上限、币种／价表／cap／upper占用、usage合计与超界、真实 lease／过期／错误绑定／布尔伪准入／重复消费、loader期间撤权、发送异常、坏 JSON／伪引用／level／checked／工具、取消后只费用观测、gzip及超限、截断、慢 headers／body、TLS／DNS期限和资源回收。发送者在 preconnect 后持锁被终止的真实子进程对照：服务端收到0个HTTP请求，锁可重新取得；DNS期限对照仅运行本机 sleeper，不解析任何域名。TLS／peer检查是拦截模拟，不是实际公网验证。

首轮新测试44 passed／2 failed暴露响应资源包装缺 `flush` 导致异常收尾中断，补齐并保证 finally 总能关 socket／timer；之后逐项扩展回归。首次将 root 与 backend 的同名 tests package 混收集产生2个 import errors，保持原文件，改为独立进程按原路径执行。在loader及消费期间过期的补强后，新101项加原source 30项曾组合 **131 passed、29 subtests passed、退出0（1.93秒）**。随后追加“消费已CAS提交但丢回执”的确定反例，最终新两文件 **102项全部通过**；完整同一组合的最新结果为 **131 passed、1 failed、29 subtests passed、退出1（2.06秒）**。唯一失败是原 `SourceTests.test_owned_process_success_failure_and_hard_timeout_are_reaped`：0.3秒slow_worker应报“source hard deadline”，实际报“source worker result unavailable”，不能将前轮绿色覆盖这项当前红灯。原source源码／测试／阈值未改；父期限与子自身expiry的错误分类竞态只是只读推断，交PMO／原owner定位，不为采绿重复运行或扩大本卡范围。原C0与source_lifetime独立进程 **43 passed、退出0（62.10秒）**，三条既有依赖warning。五个Python文件AST通过；精确文件清单与原tracked源码零差异核对通过。最终源码摘要由停写回执交PMO；不把单元seam当真实授权、已财务占用或端到端产品验收。

没有真实 key／ENV／1Password／私有 env 读取，没有公网 HTTP/DNS、余额、模型、费用、SSH、SMTP、trace、CI、提交或推送。所有本机 socket／timer／server／测试子进程由 finally 关闭／join，原 actor 的文件不动。需 PMO 精确六路径提交与当前 SHA 独立 Astra 审查，之后才由 Core 唯一 owner 接线；API→真实 provider→同库账本→typed记录→页面重开的实际任务仍未验收。

## 100d 独审 P2：可选缓存明细

日期：2026-10-17。针对受审 `100d82ec4ef992f56c0d9bce140554d5a6d45869` 的唯一 P2，仅修改 `provider_schemas.py`、追加 provider 测试和本记录。顶层 prompt／completion／total／cache-hit／cache-miss 完整一致时，缺 `prompt_tokens_details` 不再误判 UNKNOWN；对象内可选 cached_tokens 未提供时保留 None，不补零、不改顶层 hit。对象出现必须为 dict 且无未知字段；cached_tokens 若出现必须严格整数非bool、非负并等于顶层 hit，显式 null／float／冲突仍拒绝。全部原合计、token上界、reasoning和费用规则保持。

新增对象缺失、空可选对象、正常值及九种冲突／非法结构对照；另用真实本地TCP证明省略对象后候选仍为ok、usage完整，费用仍是完整U的estimated_upper意图、actual=null。原全部测试／fixture函数AST保持。最终新模块两个完整测试文件 **115 passed、退出0（0.83秒）**，无skip；没有重跑或修改原来源超时分类问题。公开paid仍固定关闭，没有实际provider、凭据读取、网络研究、数据库接线、提交或推送；资源沿原finally正常关闭。作者停写交PMO新SHA及同Astra复核。
