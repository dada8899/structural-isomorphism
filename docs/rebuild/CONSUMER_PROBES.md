# Structure B1 真实消费者冻结探针候选

版本：`b1-candidate-01`；日期：2026-10-16；Issue #251、父 #248。设计基线 `be3a3c6b5de19f2508335519d01240077bb591ec`。依赖同版 [CONTRACT_SPEC](CONTRACT_SPEC.md)。**本文件规定运行与判定计划，不是当前实现的验收收据；已有实际验证以对应 SHA 与项目检查点为准，本轮 D1 增量探针尚未运行。不解除 B0、当前 SHA CI、独审或共享冻结门禁。**

2026-10-17 增量：在 `e1604b011551ceae5036edfe8888ccfd3a2a43ff` 基础上，按 Mentor 正常委派补充 D1 免费 GET、持久批准与来源 DTO 接线探针。方向已在既有委派内采纳，不是要求用户再次处理宿主审批，也不伪称其逐条原话；以下新增项仍是待执行判据，不继承其他隔离测试为本产品链通过。

同日第二增量在已审 `47a585873465358ad84e9b96d4f0d2dbbcbac67f` 上，按已认可的 bounded-provider／typed 报告方向补充 P03-BP/P04-BP。旧免费 GET 与旧 fixture/final receipt 判据保持；新增项未运行，不代表实际价格、grant、余额、模型或付费验收完成。

## 1 要证明什么

B1必须证明真实应用消费者能够使用正式导出完成“输入/事件→合法状态→真实持久化→实际页面投影→重开/恢复→结束”，并能拒绝反例。只验证Pydantic形状、手拼响应快照、静态页面fixture、作者截图或调用测试替身的次数不足以冻结。

离线供应商/来源替身只替代边界外服务。API、账户校验、公式执行、runner、SQLite事务、预算和投影不得被mock；由测试驱动真实应用。与待验契约无关的旧搜索模型启动依赖若需明确替身，报告其具体范围，不能据此宣称真实检索质量通过。不得访问旧生产、真实用户数据、收费API或真实邮件。

## 2 正式导出与消费者入口

下列路径和名称均为候选，正式B1实现后核实际存在和导入；不能把此表称作已导出的接口。

| 消费者 | 候选正式导出/实际入口 | 必须真实接通的部分 |
| --- | --- | --- |
| C1 Research API | `research.ResearchService`、`research.ResearchStore`；实际应用挂载`api.research`的创建、修订、任务、读取接口 | 从HTTP身份解析、请求校验到同一磁盘SQLite，再由真实GET读回；不是直接往表塞预期响应 |
| C2 Formula consumer | `research.FormulaChecker.check`，由`POST /api/research/{id}/formula-checks`调用 | 真实解析/允许表/确定检查，保存CheckResult，GET视图及页面展示相同ID、范围和结果 |
| C3 Research runner | `research.ResearchRunner.run_next/recover`、正式Step/Evidence/Report导出；候选单步入口`python -m research.worker --once` | 用实际task计划和控制适配器执行、持久检查点、恢复、绑定报告；不直接把数据库置COMPLETED |
| C4 两种收费消费者 | 来源发现适配器与报告综合适配器分别经过`research.BudgetLedger`和相同FundingAccount | 两个真实服务调用路径并发预留/结算、真实HTTP测试供应商计数；不是仅测Budget类算术 |
| C5 页面消费者 | 正式`research.ResearchProjection.build`，浏览器端`researchClient`，实际`/research/{id}`只读最小页面及已有账户入口 | 页面实际调用HTTP API；显示状态、证据、动作和offline_probe标识；刷新/重新打开读DB，不从测试脚本注入结果 |
| C6 Account lifecycle | 既有auth账户删除/撤权/认领入口，经新增`research.AuthorizationGate`与同DB条件写入 | 当前登录/anonymous proof、持久epoch、跨进程gate、迟到提交和预算收据；不是只调用私有清理函数 |

B1最小页面只承担真实状态/证据/动作的消费与恢复验证，不提前实现完整D4工作台、导航或商业化。目录与文件由共享owner统一确定；改路径后更新同版契约与此表，不让消费者各自复制类型。

## 3 运行环境和证据包

每次运行使用本任务专属临时数据根和真正磁盘SQLite，启用外键及生产一致的事务模式；合成账户、研究和测试资金全部由正式API/受控身份适配创建。进程重启后重新打开同一路径，禁止换成空DB冒充恢复。测试结束关闭自己启动的API、worker、HTTP供应商与浏览器并清理临时资源；失败时只保留经脱敏的必要证据和明确回收责任。

测试供应商是本机专属HTTP服务，按请求ID记录“已接收/已收费/响应或故障”，可控制延迟、响应丢失和查账结果。它不能接触真实密钥；offline_probe模式与生产live配置分开，生产拒绝fixture绑定。来源替身使用有明确标记的测试正文/摘要，含冲突与不支持段落；真实外部访问另在D3/QA验收。

证据包至少记录：task/attempt、base与候选完整SHA、contract/policy revision、测试代码及应用入口、实际checkout与环境版本、运行ID、临时资源归属、输入摘要/合成标识、请求/事件/收据的opaque关联、真实DB路径与迁移版本、前后状态、页面观察、通过/失败及未验。公开证据不含账户配置、余额、真人身份、正文或秘密；精确私有路径只留项目批准的本地证据。

按Mentor决定，当前B0未闭合时可在指定固定受审base隔离实现B1及其探针；不能把本计划写成已执行，也不允许下游提前消费未冻结接口。合入和共享冻结仍等待B0、科学、runtime组合当前完整SHA的独审、必要CI与真实消费者证据闭合。未来CI记录run_id/attempt/event/checkout SHA与每项实际结论；成功绑定当前候选，不继承旧SHA绿灯。独立审阅者加入未用于实现固定答案的合法变体和失败假设。

## 4 P01 研究与修订的真实生命周期

前置：合成活跃账户A、匿名主体N、另一账户B；私有测试DB；真实API和最小页面已挂载。

1. A通过API创建排队现象与目标，读取研究ID、revision1、version及私有投影；浏览器打开该ID。
2. 确认结构，通过正式task入口运行不收费本地步骤；得到候选/检查/阶段笔记并保存。
3. 修改lambda或未知条件创建revision2；重新读取revision1绑定的旧快照，必须显示历史输入，不被覆盖。
4. 关闭并重启应用/浏览器，重新登录A打开同ID；DB内容、revision、事件游标和报告绑定一致。
5. 显式结束/取消任务，再次操作旧按钮，服务端核当前version，不能重新派发旧步骤。

合法对照：同幂等key、完全相同请求只产生一条研究/修订/预留；B自己的独立研究正常可读写。反例：同key不同body409；旧expected_revision409；B读取A与任意不存在ID均404且不返回A标题；正文伪造owner/epoch/终态422；未确认输入不能进入要求确认的外发步骤。

通过证据：正式API请求、唯一DB行/事件序列、旧新快照绑定、实际页面重开结果和无跨账户数据。只验证返回JSON不算通过。

## 5 P02 三家族公式与数学边界

每条均由公式API→正式FormulaChecker→真实DB→GET投影→浏览器→保存重开执行；另从Python消费者直接调用同一正式导出，结果语义和版本一致，不能各写一套求解。下表是预期判据，不是已运行结果。

| 家族与正常输入 | 应有结果 | 反例和合法变体 |
| --- | --- | --- |
| queue_flow/mm1：lambda=36、mu=40，均为count_per_workday，声明M/M/1条件 | rho=0.9；W=0.25 workday、Wq=0.225 workday、L=9；明确是假设演算 | 未预置lambda/mu变体得到对应新值；lambda=42,mu=40拒绝稳态式；只给均值/批量到达不得把M/M/1条件当已观察 |
| queue_flow/little：L=9、lambda=36、W=0.25，同系统边界 | 量纲及关系检查通过，不据此证明原因或最优方法 | lambda=0、L=0为合法边界，但不能用L/lambda计算W；队内人数与全程时间混用或workday/calendar day混用拒绝该计算 |
| first_order_storage：声明理想热/RC，自由衰减，两侧R,C正、非零x0，各自按tau和x0归一 | 标准式和所声明初值下可对应；s=0,1,2响应约1、0.3678794412、0.1353352832 | 更换合法R/C/x0仍能规范化；x0=0使用未归一方程与恒零解，不除以0；一侧零另一侧非零不能无视初值宣称同一初值问题 |
| local_recovery：delta'=−k delta，k>0，声明局部线性与范围 | 时间尺度1/k及有限轨迹；条件化局部对应，不宣布真实系统已临界 | k≤0是本稳定家族不支持/前提不符，不宣称方程全球无效；外驱动/非线性/无局部范围时降级；不输出通用阈值或崩溃日期 |

补充恶意/资源反例：未知AST key、属性/下标、任意函数/模块、二阶导数、非法unit、非有限数、bool冒充数字、除零、未经证明非零的约分、129节点、深度17、257数值点、超出十进制阶数及计算结果范围、运行时间/内存超限。验证实际拒绝发生在执行前或受控worker边界，不能仅测试错误文案。

方程形式一致、初值问题等价、局部近似、数值一致分开断言。检查数值容差按policy记录，不允许增大容差让反例通过；unsupported/resource_limit不显示“不等价已证实”。实际页面能展开原式、单位、条件、变换与check记录；重开不丢版本。

## 6 P03 来源、证据与受控报告

通过真实研究任务产生discover→fetch→assess→compose步骤。测试来源S1正文明确支持一条范围受限主张，S2正文描述不同条件或反对证据；S3只有元数据，S4访问受限，S5网络故障。取得的原字节、LF提取文本、offset和quote通过正式Evidence对象保存。

正常路径要求页面能打开本研究的实际摘录位置与读取范围，ClaimEvidenceLink可追溯；成功综合的是带offline_probe标识的机制演示报告，不得标成真实外部深研成果。冲突路径用CONFLICTED+qualified_report，陈述条件与未决，不由多数票抹平。无结果/正文不可读以INSUFFICIENT或阶段笔记结束，不返回固定同题“研究完成”报告。

反例：伪造source_id、跨研究引用、offset不匹配、quote不在已取回文本、Unicode组合字符/非BMP字符因NFC或UTF-16索引错误而错引、只在题名出现的论断、以metadata_only冒充全文、OCR未核当精确引文、外部文献注入系统指令/任意工具、模型返回额外权限字段。后者必须不改变允许步骤/网络/预算，已发生的模型费用仍结算，不能因内容被拒绝假装调用免费。

网络边界探针使用受控resolver/transport，验证HTTPS目标、每跳重定向、实际连接地址、字节/类型/时间上限。私网、loopback、云元数据、DNS重绑定和第四次重定向必须在禁止连接前拒绝；fixture transport仅用于offline_probe环境，不能写进生产allowlist。验证拒绝时调用计数为零，合法来源为正常对照。

### P03-D1 最小批准、来源 DTO 与缓存消费

使用正式 API→同 auth DB→runner→records→实际页面；外部固定 GET 可用明确 offline_probe 的本地来源替身，本探针不因此宣称真实公网取证。D1 窄策略仍为 max4、12秒、零重定向／重试和原响应／解压各2 MiB，不能继承通用策略更大的上限。

| 场景 | 必须核对的事实与合法对照 |
| --- | --- |
| preview 后尚未确认／start | 只有无 task 的本地 DTO；DB 无新 task/step/执行证据，外发计数与 quota 不变；旧 preview 不能直接成为批准 |
| 合法持久批准→start | 正式确认入口形成规范批准；start 同事务核主体 incarnation/epoch、研究、input revision+digest、plan/policy、max4、外发关键词摘要，再绑定 grant/task/steps/正式 plan/批准消费/幂等结果；实际 send 重核相同绑定 |
| 批准后修改输入／关键词／plan／policy，或换账户、撤权 | 旧 approval_ref 拒绝，无半创建对象／新外发；客户端／LLM 覆盖 provider、URL、价格或 quota 同样拒绝。新合法批准为对照，不能靠一律禁止 start 掩盖 |
| start 创建中途故障／重复 key | 全部事务回滚，不遗留 grant/task/plan 半绑定或消耗；同 key 同请求授权回读既有结果、不重复批准与 quota，不同正文409；旧终结 task 不复活 |
| 内部 snapshots 的来源投影 | 仅经 records kind=sources 返回已审 SourceRecord DTO，ID/revision/hash/原取得时间和访问范围一致；plans/executions/snapshots 非公共 kind，原缓存、全文、提取全文、发现响应、批准与私有定位不泄露 |
| 来源分页与改版 | 每页≤20、响应≤512 KiB，cursor 绑定 owner/incarnation/研究/kind/research_version；跨 owner 或版本改变拒绝，不能沿旧 cursor 拼出已撤权内容 |
| 读取／导出缓存 | 正常只走已审授权接口，分别核 cache/展示/导出许可与当前权限；合法历史读取保留原时间／版本并说明本次未联网，不新增 live 取证事实。接口缺失／许可未知明确失败或不足，不私调 _get、操纵 adapter、装 live 或暗发新 GET；合法缓存读不增加外发计数 |
| GET 持 gate 与取消竞争 | 实际跨进程 gate 覆盖有界请求、无跨网络等待 DB 事务；取消遇 busy 时 API/页面如实说明并核原操作，不能假取消成功。父死时实际子执行组／接收／写入窗口由原安全审查者另做故障实验，未验不称已保证 |

### P03-BP 受控模型候选到实际报告

先用明确 offline_probe 的受控 provider 响应验证机制，再在 Mentor/DevOps 完成真实 gate 后只做一个有界真实任务；两类证据不得混用。正常路径为实际 API 保存问题／批准证据包→一次固定模型 dispatch→最终 usage／费用分类→严格候选→同 DB ModelReportRecord/Claim/ReportSnapshot→records reports 与真实页面→关闭重开后相同版本／摘要／引用／费用分类。不会因源码、schema 或 usage 存在就宣布 U1/U2 价值、实际扣费或 VPS 发布通过。

| 场景 | 必须成立 |
| --- | --- |
| 正常模型候选 | 按固定 schema/上限生成服务器 ID 与假设 Claim；首个方法子链为 qualified_report/INSUFFICIENT；D1 notes 硬 false 类型不改名，内部模型记录不直泄为公共 kind |
| 重复 key、NaN、额外 level/checked/id/工具 URL、超长、空／截断或非 JSON | 候选拒绝，不执行模型建议的工具／代码；可信最终 usage 的费用仍独立保守占用，不因内容失败变免费或自动补发 |
| 伪引用／错版本、hash/offset或引用只在标题 | 不伪造来源支持；准确摘录仅证明定位正确，LLM 推断仍 hypothesis/unreviewed；checked 仅关联真实同研究同修订 D2 的实际范围与状态，不用量纲 passed 宣称任意内容已算 |
| 展示许可有而外发许可无，或反向 | 两项分别拒绝相应动作；首发证据输入须同时许可外发与展示。外发完整包／source revision／授权或模型价格绑定改变，send前拒绝，无新调用 |
| 取消／账户删除／撤权／来源许可变化发生在发送前后 | 发前重核并拒绝；已发仅保留必要费用处理，迟到报告正文／分享不复活，不以删除归零费用 |
| 新旧报告消费者 | 新格式经新 revision 白名单投影，不序列化 provider 原响应、批准、私有绑定或全文；旧 fixture/notes 消费者仍原样工作，不将未知新格式吞成旧 note |

## 7 P04 预算由两个真实调用消费者共同使用

创建fixture FundingAccount，币种USD、scale=6、verified_cap=10,000微单位，真实持久账本；两个独立应用进程分别执行来源发现和报告综合的正式调用路径。供应商fixture只记录经过允许外发的请求与已收费收据。

| 操作/故障 | 必须成立 |
| --- | --- |
| 两进程同时预留7,000与5,000 | 只能一个成功；不能假定谁先赢；DB held≤10,000，供应商只收到获预留的一次请求；另一个预算拒绝发生在外发前 |
| 同key并发再次reserve | 返回同reservation，不重复增加held或外发；不同body同key409 |
| 获准调用最终actual=4,000 | 一次结算后settled=4,000、held=0；差额释放，重复final receipt不改变金额 |
| 仅非final usage或返回缺金额/usage | 不按0结算，不释放R；保留观测并置UNKNOWN/RECONCILING |
| 收到最终actual>R | 保存真实支出并冻结新调用，不截断、不丢弃费用；此用例证明发现越界，不证明供应商硬上限成立 |
| 币种/scale/price revision错误、无法精确表示的账单、float金额、负费率、过期snapshot | 拒绝新增收费外发；不能混币种算同一余额 |
| 最小分数费用 | 按price的ceil_total/ceil_components向上取整；中间乘加不溢出，不产生float误差 |
| provider余额下降或外部消耗 | 停新预留进入对账，旧已发送费用照实记录；不自动调高cap或换服务 |
| 余额增加、退款、自动充值状态变化 | 不把新资金当本次授权；退款必须匹配原收据幂等处理；自动充值/后付费边界不满足即不启用live |

重启后读取同DB，预留、settled、unknown与唯一键均保持；另开同服务进程必须看见相同可用额。不能仅在单进程里顺序调用两次Budget对象就登记跨进程通过。

### P04-BP 保守占用与真实费用分列

此处新 policy 的探针不改上一表 final receipt fixture 对照。通过正式 budget/permit/transport 同物理 auth DB 执行，不直接填表制造成功；金额、FundingAccount、模型／价格与观测版本均可按安全 opaque 引用回读，不在公开证据放真实余额、账号、凭据或完整账单。

| 场景 | 必须成立 |
| --- | --- |
| B0−他用余量与全 token 上界预留 | 同币初始纯预付与最高适用价、context/output保守界、rounding guard及有效期可核；不是实际 token 数／官方舍入声明。未知币种、过期依据、无可靠同币价、溢出／精度不符均发前拒绝；不猜 CNY/USD 汇率 |
| 并发新 reserve，一方已 upper_booked | 所有同账户 writer 均算 actual+upper_booked+held，新金额超cap前拒，不能只算旧 settled+held；合法未超预算为对照。旧fixture upper=0行为不变 |
| 可信完整最终 usage，但无逐笔财务金额／查询接口 | held U→upper_booked U一次幂等转移，actual=null；页面显示estimated_upper/实际未核，known_cost不添伪actual。声明范围的有条件报告可按新policy完成，不永久等不存在的逐笔接口 |
| prompt/cache/completion总数、bool／负值、模型／price绑定错，或 usage 越界 | 不伪造0，不按较小估算退差额，记录安全异常并冻结或保留UNKNOWN/held；模型正文中嵌usage/amount不能作为provider envelope观测 |
| 内容坏 JSON 但可信 usage 完整 | 报告失败，费用仍 UPPER_BOOKED；不得用内容拒绝、重试按钮或取消释放 U |
| 断网／丢响应／缺usage后重启、换key/task/model | UNKNOWN/held持久保持且不二发；无逐笔查账能力明确unsupported，只可读可信本地持久观测，余额差不猜单笔。免费GET execution_closed不能解锁收费 |
| 重复观测／相同响应ref冲突／恢复持久完整观测 | 正常重放只一次转移U，不重复扣；冲突拒绝并阻断。原UNKNOWN仅有同dispatch完整可信持久证据才转UPPER_BOOKED，无新网络补查或自填金额 |
| 新价表、模型别名、充值、促销、余额上涨／他用下降 | 不自动加cap或退旧保守占用；模型／价格漂移、他用余量失效停paid，余额仅账户级快照 |
| 后续确有可信actual／退款或实际超U | 原upper与actual不可双扣，差额只按可信依据释放，退款关联原charge；超U/溢出／精度异常保存事实并阻断，不截断actual。普通usage/余额不是final receipt |
| 版本迁移、撤权／删除与未知遗留 | 同auth DB版本化，旧upper=0、旧状态／final语义保持；新状态/观测唯一键及并发CAS、旧UNKNOWN/held保留且不得追认新policy转UPPER_BOOKED。删除仅保留最小费用控制／摘要，不留研究正文、邮箱／分享；迟到费用不恢复报告或任务 |

真实小额验收必须由现有 grant/余额／无自动充值后付费／他用边界 gate 通过后单独登记：固定模型与包、实际一次 dispatch、实际 usage、保守占用及 actual 未核状态、typed 报告与页面重开。离线结果不能代签；此轮文档没有执行任何调用或新增探针。

## 8 P05 在途账户删除、撤权与认领

使用真实账户/anonymous proof和正式生命周期入口，新旧writer都经相同跨进程owner gate与SQLite条件提交。fixture transport提供“取得gate前、消费票前、已启动请求、返回后提交前”四个可控停顿点，不能用sleep时间先后来代替确定屏障。

| 排序场景 | 预期与合法对照 |
| --- | --- |
| 删除/撤权先提交，worker后请求外发资格 | 无供应商请求，无新正文/报告/分享；旧snapshot资格失效。活跃A同输入正常完成作对照 |
| worker已启动请求，随后账户删除，再返回 | 旧请求允许被记为在途且可能收费；结果提交DISCARDED，新研究内容不复活；最小billing receipt仍结算/对账，不保留或重建已删正文 |
| 返回已到、尚未提交时撤研究grant或acl epoch | 条件提交失败；不能通过先读active、后写结果的竞态窗口；跨进程与同进程都覆盖 |
| N匿名记录被A认领，N旧worker迟到 | N不能再列表/读取/写入，迟到结果不按A身份保存；A合法读已有被认领资产。继续研究需新grant/attempt并先对账旧外发 |
| 账户删除后重新注册同邮箱 | 新principal/incarnation；旧JWT、grant、幂等key、检查点与回执不能恢复旧内容/分享 |
| 旧多库registry清理失败 | research gate保持deleting及禁读/禁发，不能补偿回旧epoch放行；恢复任务有明确状态，不将失败宣称删除成功 |
| 旧客户端缓存/事件连接/分享状态 | 每次API/事件读取重核；撤权后不再返回标题、摘录、原问题或报告，不仅隐藏按钮 |

探针必须启动至少两个真实进程，读取实际epoch与事件顺序，分别验证两个线性化顺序。OS锁持有者退出后由操作系统释放，旧票仍靠DBepoch/version拒绝；不得删换锁文件让旧等待者与新锁分裂。构造不经过新gate的旧writer应被配置/迁移门禁拒绝启用，不以口头“以后都遵守”放行。

数据检查同时扫描本任务DB和日志：删除后正文canary、合成邮箱、分享凭据不得出现在新结果、日志或计费收据。保留的reservation只含必要供应商账户/请求关联与金额；未知费用不因删除释放。这里是合成数据的安全机制证据，不是实际用户删除已执行。

## 9 P06 中断、取消与未知回执

只终止本探针自己创建并已核身份的worker/API进程，按失效点逐项运行；不要杀共享服务。进程重启用原DB、相同task/key与新worker身份。

| 中断点 | 恢复判据 |
| --- | --- |
| PREPARED，已预留但确证未进入SENDING | 可以复用原reservation与幂等记录继续，或释放已证未发的预留；不能同时释放又用旧票发送 |
| SENDING后、本地未保存provider结果 | 进入RECONCILING，页面无无条件retry；供应商计数可能0或1，不能凭无本地结果猜测 |
| provider已收费，响应丢失 | 查账确认同一request/reservation，收费只计一次；查账本身的fixture免费不证明live查账免费；live收费对账也需独立上界与预留 |
| 结果已保存，响应未到浏览器 | 同key返回已保存结果，不重新调用；页面刷新恢复相同版本 |
| 费用已核但研究结果无法恢复 | 允许以明确失败结束；后续显式新attempt才可新预留/调用，不能用账单收据伪造研究正文 |
| 用户取消、供应商不可取消 | 立即阻断后续步骤和研究提交；界面cancel_pending/费用待对账与实际状态一致，不承诺已撤销远端收费 |
| RECONCILING中调用真实cancel API，并与外发gate竞争 | 两个真实进程用确定屏障排列：取消先提交则票消费拒绝、无新外发；请求已启动则记录在途。事务原子持久stop_requested及取消状态/版本，应用停止后CANCELLED；reservation仍UNKNOWN/held，不等收据、不因取消释放 |
| RECONCILING取消后API/worker重启，迟到费用收据到达 | 重开原DB与实际页面仍是cancelled并显示待对账；收据仅结算/保留未知，不恢复RUNNING、不重派、不追加正文。重复cancel/重复收据幂等，陈旧version明确冲突后读回，不重发收费 |
| 老attempt在新attempt创建后返回 | 不能覆盖新结果；仅按老reservation补结算，事件/数据不串线 |

至少覆盖PENDING→PREPARED→SENDING→SUCCEEDED的正常完成与PENDING→取消的明确无外发结束，作为失败注入的合法对照；另保留未取消对照：RECONCILING且stop_requested=false，经真实对账确认和当前授权重核后可按规则恢复RUNNING。该对照与“已取消、同样收据到达但保持CANCELLED”的两进程/重启反例成对执行，不能通过一律禁止恢复掩盖错误。对账未证明旧动作未发生时，不允许测试通过直接把UNKNOWN改为FAILED来解锁retry。

### P06-D1 固定免费读取闭合后的新观测

下表不适用于任何收费／可能收费 dispatch。测试驱动受审固定 executor 与正式服务完成闭合，不直接改 SQL 的 UNKNOWN/closed 标志；真实 DB、GET／页面、请求计数、旧／新 dispatch 与 observation 关联同时回读。

| 场景 | 必须成立 |
| --- | --- |
| 原免费 GET 结果未知、执行组尚未核闭合 | 重启／取消／终结／新 task、attempt、key、approval 或 policy 标签均不能绕同规范输入 fingerprint+step/target 再发；计数不增加，无迟到正文被采纳 |
| 仅等待超时／单 PID 消失，子执行或结果接收仍可能存在 | 不得写可信 execution_closed 或放行新 GET；原安全审查者实测父死窗口。合法完整收尾的固定 executor 为对照，不把探针变成通用监护平台 |
| 实际执行组、接收通道与旧写入资格均已关闭 | 正式服务保存 execution_closed、固定 executor/policy 与证据 ref；原 outcome 仍 UNKNOWN，迟到原正文提交拒绝，旧 task 不恢复 RUNNING，直接调用旧 retry/resume 也拒绝，不伪记原成功 |
| 免费已闭合未知＋新持久显式批准 | 新合法任务产生关联原 dispatch 的新 observation/dispatch/acquiredAt，实际新 GET 只一次；原 UNKNOWN／原时间不改。批准缺失、陈旧、跨 owner 或闭合证据缺失均拒绝 |
| 原计数已消耗，新计划再取证 | 同观测延续链累计计数；新 task/attempt/key/approval 不清零旧 quota，未知请求不退次数；累计 max4 后新批准也不能产生第五次。合法未满额度的新观测为对照 |
| 同样的未知／取消／闭合场景换成收费或可能收费调用 | 服务器代码分类拒绝免费例外；客户端／LLM free 标志、GET 方法、无 key 均无效。原 Money UNKNOWN/held 与收据保持，不释放、不换 key／task 重发收费 |

收费恢复原 P06 对照继续全量保留；免费 execution_closed 只关闭原执行与写入能力，不对账远端成功，不提供旧正文、许可或预算已结算证明。新观测成功也不把旧 UNKNOWN 补成成功；两者分别显示，避免用“重试成功”掩盖未知历史。

## 10 P07 产品态、执行态与证据完成度投影

通过真实API/runner事件构造状态，不直改JSON；每项同时核DB、GET和实际页面，刷新与重启后再次核对。

- 一个来源读取成功时仍是retrieving/COLLECTING；不是completed。
- WAITING_EXTERNAL、CANCEL_REQUESTED、RECONCILING分别显示当前阶段与等待/取消/对账说明，下一动作不得有无条件retry；RECONCILING必须可cancel，不能把“费用待对账”变成无法停止应用研究的理由。
- COMPLETED+SCOPE_COMPLETE+绑定报告且无未知费用/外发才显示completed/normal；offline_probe标识始终保留。
- COMPLETED+CONFLICTED显示条件化完成及冲突；COMPLETED+INSUFFICIENT显示证据不足及补证方向。
- FAILED但费用未知仍显示reconciliation_required，FAILED且已对账也需服务端重新验资格后才可retry。
- CANCELLED只承诺应用后续动作停止；未知收费继续显式显示，不能预算归零。
- 固定免费 GET 已实际 execution_closed 的原未知读取，继续显示 UNKNOWN 与闭合／失败或取消；经新批准产生的新观测有新关联及时间，不把它显示为旧任务恢复成功，也不把免费请求次数混成 Money 对账余额。
- 权限失效先于所有投影：返回泛化失效/404，无原内容、export或retry。前端缓存的旧allowed_actions不能绕过服务端检查。
- 事件after_seq断线续读按持久seq恢复，不重复推动实际步骤；若游标过期或状态版本跳变，重新读取授权后的当前快照，不拼接成伪完整结果。

对非法组合如COMPLETED+UNASSESSED、缺完整报告却声称complete_for_scope，正式导出必须拒绝或进入受控不变量错误，不能由前端“最好猜测”兜底。软件状态通过不代表来源语义、公式现实适用或用户价值通过。

## 11 P08 旧调用面、Phase静态边界与旁路

测试以实际运行路由表和源码callsite manifest为输入，不只挑新Runner。fixture环境配置一个**真实可用的合成供应商凭据**，这样拒绝证据不能归因于“没有key”。保护主auth、私有旧报告及SSO，Phase动态停用不影响这些正常消费者。

| 消费者/反例 | 必须观察到的结果 |
| --- | --- |
| 经批准POST的旧Ask/Analyze或工具桥接 | LegacyBillingBridge或Research上下文签发合法grant；每次底层调用经过Guard/permit/同一账本，返回有效结果，供应商计数与reservation一一对应 |
| Phase七个动态路由，含普通与stream形式 | 即使key配置、输入合法、有旧cache也在动态执行与SSE头之前返回明确503不可用；计费计数0，没有成功done或固定“生成结果” |
| Phase冻结结果/历史页面、主auth、SSO及私有旧记录 | 静态结果有版本/日期与冻结标识；正常身份仍可按权限读取；缺实际数据则明确不可用，不HTTP200假交互；不因整体禁`/phase`误伤账户 |
| GET phenomenon的翻译cache miss、任何旧GET生成变体 | 不隐式调用收费翻译/重写；有审定公开翻译cache可只读命中并标版本，缺失显示未翻译原文或明确不可用；已退役GET保持拒绝，不能靠GET绕POST guard |
| POST工具未在OperationRegistry登记、disabled或read_only请求收费 | 执行前返回FEATURE_UNAVAILABLE/OUTBOUND_NOT_REGISTERED，不吞成None、空报告、fallback成功或换模型 |
| 直接调用LLMService、llm_client三入口、Ask低层方法、translation helper | 在有合成key但无合法上下文/permit时，正式客户端入口外发前拒绝，计费计数0；有合法permit为正对照 |
| 过期/重复/伪造permit，改模型、输入、价格、operation或principal | transport消费拒绝；同一个permit最多一笔实际外发，不凭来自服务内部就放行 |
| 查询扩展/英译中/工具评审/JSON修复重试 | 每次额外外发有独立permit/R，同资金账户总数受限；旧结果未知保留额度且不进入新尝试；不能只在请求入口计一次数 |
| 流断开、超时、429/5xx、响应无usage或非法JSON | 已发送可能费用UNKNOWN继续占用或按真实收据结算；取消/校验失败不免费；不盲重试、不追加done成功 |
| 私有cache跨账户、认领/撤权后旧匿名cache、同key不同body | 先验当前授权再读cache；越权拒绝不返回标题/正文；冲突409；合法cache hit不新增收费，也不改成“刚执行” |
| MCP调用旧API/工具、未登记后台脚本入口 | 经过同一admission或明确不可用；不因MCP/CLI来源自动取得预算资格；未Guard脚本不进入运行/自动任务制品 |

实施owner还须提供收费sink的实际运行制品闭合证据：代码/导入扫描能发现直接构造provider HTTP/SDK、urllib旁路、隐藏重试与遗漏route，独立审阅用临时反例验证扫描确实失败。所有项目正式provider client运行时也执行permit验证。静态扫描不是OS网络隔离；如果存在可运行任意扩展/代码或不能闭合的入口，必须停用/排除，或先验证真实凭据/出站隔离，不能通过改manifest把反例豁免。

本探针不声称对拿到root或泄漏凭据后的任意HTTP有防护。发布前callsite登记逐项只有“Guard实际通过”或“实际拒绝/未纳入运行制品”；单纯没有API key、没有导航链接、配置注释或未点击页面均不能作为停用证明。主认证/私有旧数据兼容与旧调用收费边界是两个独立验收维度。

## 12 冻结收据与后续边界

独立执行者回收每类消费者的导入、实际入口、DB/事件/页面证据、正常/失败/结束、原反例与合法对照。允许固定受审base上的隔离B1实现；合入和共享冻结前，B0、科学、runtime组合候选当前完整SHA的必要CI、独审与真实消费者证据须全部闭合。共享owner记录contract revision、实现与测试路径、资源策略、迁移版本、作者及独审结论；任何未运行项保留未验，不能靠总测试数抵消。

达到这些条件后才向PMO提出共享冻结；冻结由协调者核对完整SHA/revision和真实消费者证据，不由本文自封。后续模块从该受审同SHA消费正式导出，不能复制本文件未冻结类型。真实供应商余额/计费、真实外部检索原文、目标现象数学/经验有效性、整体产品与VPS用户任务分别继续验收，不从B1离线机制结果推导。

当前两份文档未改源码/CI/依赖/数据库，没有实际运行探针、调用付费服务、SSH或提交。可审阅后返修；在正式实现前，单物理DB和跨进程gate的迁移/部署约束、受控parser与资源初值、live计费边界仍须由相应owner核实。
