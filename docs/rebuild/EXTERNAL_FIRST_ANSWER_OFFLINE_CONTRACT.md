# 明确确认的外部后备分析：离线合同

本地问题入口和分析流程保持原样。如果本地没有合适结果，可考虑一个单独的“用 DeepSeek 补充分析”动作。现有项目 CNY300 累计上限可以继续用于同经济账户的 Structure DeepSeek 工作，但旧资金运行许可和外发确认只覆盖原有目的。新目的没有现成的在线准入；本合同所有返回都关闭，也不接入 Main。

| 可复用 | 新用途必须单独核实 |
| --- | --- |
| 现有的登录、所有者权限、修订/代际、短时报价、精确预览、一次性确认和对账机制 | 新 purpose（external-first-answer-question-v1）、固定问题模板、结果形状、资金 grant 和 source/runtime 绑定；旧的现象规划和证据规划都不能替代 |
| 同一个 Structure 项目账本和同经济账户的余额读数、实际/上界/未决占用和风险余量 | 新用途现行官方报价及可信 token 上限、原账本版本和官方新鲜余额；不能另立预算、重置未知占用、换 key 或切付费提供方 |
| 已有 JSON/纯文本校验、结果与修订绑定、撤权与历史隔离 | 此后备不发送知识库、附件或来源。结果只是未核候选；后续须单独审查支持度、是否回答问题和条件边界，未经核对不进入用户结果 |

外发只包含保存修订中的原始问题与固定模板。原话限 8–1000 字，不截断、不改 Unicode 或空格；拒绝明显链接、联系方式、凭据和代码结构。规则只能降低误发送风险，不证明内容可公开。用户确认准确原话、接收方、金额上限及外发资格；现有作者标记或用户主动登录不等于同意。单独的金额说明不能覆盖外发，反之也不行。任何用户授权代际、问题修订、权限 epoch、模板、价格或字节变化使预览失效。

同目的、账号、经济绑定和账本 epoch 下同时检查两条边界：CNY300 减实际、上界和 held 后的项目余量；官方当前余额减风险余量、held 和上界后的余额边界。离线检查只回答输入数字是否一致和足够，不申请资金或认定这些数字来自实际官方账户。发生可能已发送的 consumed/UNKNOWN 时，保留原操作与可能费用，只对账，不能凭换请求、换会话、换 key、恢复服务或用户重按而重发。

调用关系：prepare_closed_preview → compare_confirmation → inspect_shared_capacity 仅校验数据；recovery_hint 提示原操作处理；parse_unverified_candidate 只解析响应语法，标为必须审查。函数不读密钥、不创建任务或账本、不进行任何网络或写入。后续实现须将已验证的授权、同账本原子预留、发送前再核、单次 transport 和回执对账接在另一个受审的运行层。还应单独保存后备结果引用，不覆盖已存本地答案或重启原本地终态队列。

相关现行实现：native_live_grant.py 的双目的绑定、plan_native_runtime.py 的审批/额度/一次性消费、paid_approval.py 和 model_report.py 的离线用途。这里仅保留其有用约束，没有把旧接口提升为通用在线发送。

## 实际隔离集成边界

external_first_answer_seam.py 通过既有 ResearchService 所有者锁、同一事务内的读写资格和当前 revision 读取问题，复核精确预览，再只读绑定既有 Native 资金账户与其未决状态。它没有登记 HTTP 路由，也不创建审批、任务、占用或结果。即使同一 revision 的原话及费用都明确确认、同经济账户存在，独立新用途也返回 external_purpose_not_admitted；原账本有未决发送则返回 unknown_reconcile_only。

两个隔离场景使用真实 Main HTTPS、合成登录和 SQLite，借既有 Native 授权工厂登记唯一 CNY300 账本。作为对照，旧现象规划能在该账本下进行一次合成余额 GET 与一次合成 POST：正常回执能从原记录重复读回；缺用量回执时真实账本保持原 held，重进执行器不发送第二次。新用途在相同条件下零请求、零新账、零占用和零结果。未确认、换账户及修订改变均被原鉴权或合同拒绝；本地合成输出只通过待审候选解析，不冒充新用途的在线回读。

剩余缺口是新用途的真实 Native 执行授权、同账本的原子资金写入与消费、可核对回执、独立审查和结果记录。一条模拟成功或一份数据模型不能替代这些条件。没有读取真实密钥、访问外部提供方、消费费用或改生产。

## 独立持久状态候选

external_first_answer_state.py 定义待审 SQLite 表与闭合消费边界。每个研究修订最多一个后备操作，绑定原 scope、预览、外发字节、报价、既有资金账户和资金代次。它只引用原账本和预留行，不持有独立金额余额。版本与核心绑定不可变，未确认发送无法回到可发送状态或被替换、删除；已知回执必须先有 consumed，候选摘要不能被后来修改。表默认没有注册 writer hook，原生 SQL 拒绝新增或修改；消费入口不会收任意 callback、布尔值或 DTO 来开放发送。

不能直接接旧资金 writer：plan_native_financial._producer 只允许既有 native/runtime 活动调用栈，同账本资金变化还必须与旧 dispatch 行、真实余额和固定 reserve/return/release 函数一致。把后备用途塞进旧计划、开放原 writer hook 或新建第二个钱包都会破坏边界。后续接入需明确：新 purpose 的受信 issuer 和固定 transport，真实 Owner/revision/ACL/CAS，预留与状态写入同一 SQLite 事务，发送前再次核绑定及 durable consumption，原 held 的回执/晚到/UNKNOWN 对账，候选独立审核及所有者读回。未知费用的合法账号删除需先按现有财务留存规则设计独立清理通路，不能删除未决资金行。

新增 9 项隔离状态检查。测试数据库只建身份外键占位，不建余额或账本；测试 hook 只用于证实 SQL 的状态形状与不可逆约束，不是资金证明。现有真实 Native 集成对照仍是上一节的两项负控。新表未加到任何迁移或 Main，未签新目的消费、保存或回读闭环。

## 受控原子写入演练

external_first_answer_fixture_writer.py 只允许 SQLite 内存库，不接受磁盘库或已挂接库。它复用既有资金账户表的真实声明，测试只建立一个 CNY 账户。独立后备 grant 复核精确预览、确认、已存修订/权限和账户绑定。预留与状态同事务写入，消费提交后只交出一次请求字节；测试随后仅向本机回环地址发送这一次。正常合成回执在原账户上把 held 转入保守上界，并保存可重复回读的未核候选；没有回执时原 held 保留且拒绝后续预留、消费或重发。没有第二份额度。

另有两连接并发竞抢、已有占用扣减和注入状态写入失败的回滚检查。演练使用内存专用 guard、合成余额和合成回执，不冒用旧用途授权、不改动旧 Financial9 代码，不是可接生产的 writer。生产仍需受审的独立用途 issuer、真实同物理库授权、官方余额与预留身份，及跨旧/新目的的未决占用一致性验证。新的 run 行用自己的 ID 标记已占用；不造一条旧 research_reservations/task 行借用身份。

## 同物理文件账本候选

external_first_answer_file_writer.py 将预留、消费、保守记账和候选读回放进同一个有真实文件 inode 的隔离 SQLite 库。复用既有 CNY 资金账户表和 Native 资金登记形状。独立后备绑定必须与原登记的账号、经济绑定、Owner/代际、CNY300 及风险余量一致。新 run 与共享账户同时更新，文件、账户、已保存 revision 和 SQL catalog 任一变化即拒。测试证明先预留后关闭连接、重开完成一次记账并原样回读；UNKNOWN 保留原 held，拒补发或覆写；注入运行状态写失败时金额也一起回滚。

候选资金触发器只接受精确旧 SQL 作为迁移前提，保留原 Financial9 判定，再添加独立 OLD/NEW 行验证分支。新分支只可改 held、upper_booked 和加一版本；旧禁止替换/删除仍原样。未有新 proof 时，新 hook 默认返回 0。旧账本的未决状态在新预留、消费的同一写事务中查询；反方向提供 unresolved_external，但尚未接入旧流程。因此不能将这个候选当成可上线的跨用途互斥。

这会改变精确 schema catalog：新增 run 表/触发器，并替换 Native money trigger 的声明。当前 v16 及其回退桥不能读取或运行该 catalog；若推进，须独立版本迁移、同 catalog 的无发送回退桥，以及备份恢复演练。不能原地向现役 v16 塞表或覆写触发器。

执行点尚未进入 Main。正式路径需在固定的 ResearchStore 连接初始化中装闭合 hook，并由经审 issuer 同 Owner lease、真实账号/余额 witness、当前修订和写事务发出单次 proof；把新目的的行许可纳入 SQL authorizer，且在旧目的余额/预留/consume 入口都检查新 UNKNOWN。在既有 Financial8 项目 money guard 同时适用时，它仍独立拒绝新分支；不能通过这次候选短接。临时文件 proof 仅为隔离实验，禁止生产路径，不是实时资金授权。没有访问提供方、读取密钥或进行实际费用。

## v17 候选与只读恢复

provision_isolated_v17 只接受有明确标记的临时私有 Auth 文件，复用原有离线互斥、数据库独占、完整 v16 预检和 WAL 恢复。候选精确替换 Native 资金触发器的旧版声明，保留原判定并加默认拒绝的新分支，新增后备 run 表。两个 schema 校验层都逐项验证 v17 声明。没有改变 Main 的 15/16 运行准入，没有可操作的生产 CLI。真实隔离库已验证同 inode v16→17、重复核对、注入验证失败后原子回到原 v16，以及旧校验器拒绝新结构。

桥接适配器单独打开已绑定 inode 的只读连接，沿用真实账户和 Owner 权限检查。原 UUID 操作键、原修订、摘要和身份共同定位状态；confirmed→pending，reserved→accepted，consumed/unknown→unknown，returned→completed，只有明确的 closed_unsent 才能报告 not_sent。找不到或权限变化拒绝，绝不据此推断没发送。result 为独立读回，要求 completed 且保存摘要、规范字节与未核候选形状一致，返回 review_required=true。preview 公共投影不包含外发字节、原账本或内部身份；默认 may_send=false。没有注册 HTTP 路由，正式发送入口固定关闭。

接入实际 v17 服务前，还需完整的同结构回退 Main（账户/历史等原有运行路径仍以现行 v16 为准）、隔离演练、后备用途受信 issuer、同账本的双向 UNKNOWN 约束及结果内容独立审核。这里的 status-only 适配器已在真实临时库验证可鉴权并拒绝不存在的 key，不能代替完整回退服务或在线执行。

## v17 回退 Main（隔离验证）

v17 的规范数据库结构可由已标记的临时私有 Auth 库使用 `--offline-migrate-external-fallback` 离线迁移，仍要求前置 v16 和真实维护互斥。该入口不适用于生产。v17 Main 可验证账户、保留已有会话和历史、保存普通问题修订；Native 付费、Source 外发和本地首答队列消费者不启动，历史首答仍可读。账户删除在新用途未决费用与擦除规则实现前，明确返回 503 并保留账户和数据。现行 15/16 主流程沿原有分支。

隔离实际 Main 核对：同 inode CLI 迁移、v17 两次启动和退役、历史首答及财务结果等值读回、旧账户重新登录、普通问题新增/修订/重开、匿名拒绝与另一账户拒绝、删除拒绝后账户仍可读取。没有真实提供方、密钥、费用或生产操作。未把该证据扩展到完整来源/高级工具或 v17 真发送。

## v17 Main 受控回环闭环

外部三类读写请求可在标记的临时 Auth 库上独立验收。controlled_runtime 显式绑定实际已运行 v17 Main、同一物理库和自有 127.0.0.1 回环服务；无此合成授权时 preview/confirm 仍 503，生产启动没有安装入口。合成 issuer 引用现有登记的同一 CNY300 账户；没有借用旧用途发送许可，也不创建第二账户。

真实 Main 先读取已保存修订并形成精确预览。三个确认字段和绑定一致后，在 Owner fence 下持久化并使用同账本原子预留；消费提交后只对精确回环服务发送一次原问题。正常返回记录未核候选、原键状态和结果，重复读回不发送；回执缺失保留原 held、状态为 unknown，不冒充 not_sent。已登记账户、已保存修订、权限代际、原 key 和确认内容仍须保持一致；同 key 不同金额拒绝。退出合成授权或重启 Main 只保留状态和结果读取。老 Native 与早期预算检查也识别同账户新 UNKNOWN；新路径沿用旧 UNKNOWN 检查。未伪造旧 task/run。

验证覆盖正式 Main 隔离身份、同 inode v16→v17、无授权/未确认拒绝、两种回执、严格原 key 和其他账户、一次回环及重启。仅本机合成，普通页面能力仍为 status_only；未安装真实 issuer、真实余额/密钥或外部 transport。上线还需受审实时授予与官方报价/余额、故障/晚回执、独立结果核验和实际回退。

## 外部用途正式启动授权候选

external_first_answer_issuer_contract.py 独立于 controlled_runtime。它定义新用途的短期签名批准：固定 DeepSeek 模型、GET 官方余额与 POST chat completion 两个 HTTPS 目标、question-only 输入及未核输出、模板摘要；同一 Structure CNY300 上限。批准绑定确切 source commit/manifest、运行代码闭包、unit、Auth 数据库及独立收据目录 inode、v17、服务 UID/GID、当前 Owner/代际/gate、同一个真实经济账户及资金/凭据代次。旧用途、旧凭据入口、另一模型或端点、另一个账本或代码版本、过期批准均拒绝。

正式凭据入口提案是 run-formal-main-external-first-answer-v1 与 purpose 专用 systemd 加密项 structural-external-first-answer-deepseek-key。这只是合同，未注册、未读取。实际接入必须在已审 Main 启动见证及进程硬化完成后，核 root 管理的固定公钥和实际物理绑定，先在受保护的启动记录中单次消费、再由专用受审 loader 取得凭据；不能用任意传入公钥/DTO、配置开关、控制台余额截图或旧许可替代。新凭据名不是新经济账户；必须单独证明它的官方余额与现有项目账本属于同一经济账户。发送仍另需用户逐次确认和原子资金许可。

合成演练使用临时签名公钥，只接受标记的私有临时目录；签名通过后用 O_EXCL 在已绑定 inode 上持久写启动挑战的消费记录。相同挑战即使换签名批准 ID 也不能重用，并发只有一方成功。记录不含问题、账户或密钥。消费返回明确 closed，无 live authority、无凭据、无资金或发送权限；真实 issuer 入口固定拒绝。24 项离线正反例验证了精确绑定、篡改/过期拒绝、物理路径变化和持久互斥。未改变 Main、旧 grant 或生产。

## v17 账户擦除

已核对回执且没有外部未决预留时，v17 沿原有认证删除、Owner 锁和持久擦除阶段。外部候选记录与本地队列/首答一同擦除，原保守记账不重置，其他账户不受影响。reserved、consumed 和 unknown 在写入账户删除 fence 之前阻断；没有生成删除任务、释放 held 或重发。新 SQL 权限仅允许真实受保护删除任务在对应 Owner 锁/同事务中删除绑定的那一行；通用 v17 付费 scope 和直接删除仍拒绝。

真实隔离 Main 两种回执测试核对了已完成清理和 UNKNOWN 原账保留、跨账户及本地队列。没有接触生产或真实费用。此前“v17 回退账户删除总是 503”的历史说明由本节的细分规则替代。

正式签名 issuer 仍关闭：当前生产 a3 的 requirements/CPU lock 没有声明 cryptography，不能根据开发机测试推断可用。若采用 Ed25519 模块，应固定目标 Linux 完整依赖与制品摘要，在与正式 UID/runtime 一致的无网络隔离环境验证签名和拒绝路径；或复用已单独获准的签名验证入口并做相同绑定验证。未验证前不加载生产 issuer，也不临时安装依赖或使用未审替代。

## 启动见证与专用 loader 接口

services/external_live_issuer.py 把签名批准和实际 Main 绑到一起：核当前已准入的 v17 Main、进程与私有 Auth inode，从真实 SQLite 查现有资金账户、经济身份、额度、风险余量、Owner/gate 与代次。签名核对并持久消耗原启动挑战之后，才向专用 loader 交一次性 claim；只有绑定的执行函数、同线程、同一入口见证和新 credential ID 可以 claim 一次。未 claim、入口不符或加载失败都不会恢复原启动挑战。发给 sender 的不可序列化 handle 绑定实际 Main/进程与资源生命周期；仅合成 handle 可由测试访问，任何 live 检查均拒绝。退出会收回 handle。

实际隔离 Main 测试使用合成账户登记、真实 Auth 文件、同账本、合成签名与 inert loader，不读取密钥、不发供应端请求。旧 credential ID、不同数据库 inode、重复 claim、未 claim 返回、重复启动、退休后及合成 handle 冒充 live 均被拒绝。保持旧用途 loader、grant 和资金代码不动。这个模块没有配置开关，也没有安装生产 verifier/loader；activate_live_external_issuer 仍关闭。

要开启生产，还缺可具体核对的材料：

- 独立审查者批准的正式 Ed25519 公钥指纹、root 管理的唯一 pin 和真实签名启动批准；批准绑定最终受保护 main 源、制品、实际 unit、代码闭包、进程 UID/GID 和持久收据位置。不能把测试公钥或任意参数当根信任。
- 正式目标 Linux 运行制品的可信依赖闭包：当前 a3 没有声明 cryptography，必须固定并隔离证明目标 ABI 与签名路径，或指定独立已批准的验证入口。
- 专用加密凭据项、物理目录/FD 见证与已审 run-formal-main 入口实现。须在硬化及单次启动许可后加载，只能证明同一供应端经济账户与原账本，不能以 key 名或 key 摘要当经济身份；加载或清理未知不得重播启动。
- 真 sender 的不可替代 handle、官方新鲜余额和价格来源、实际同账本原子预留/消费以及已占用和 UNKNOWN 的恢复。启动授权只控制 loader，不能替代每次用户确认、当前 Owner/revision/ACL、同账本额度及 UNKNOWN 阻断，也不批准任何真实执行。

## 正式启动接线候选（默认关闭）

run-formal-main 的实际 _serve 可将已硬化的 systemd 凭据目录见证借给新用途，但不共享旧 grant。v17 Main 在真实准入后才尝试外部 issuer，结束时撤回 handle 和擦除受控缓冲。external_live_production.py 的代码固定政策目前为空；未提供真实入口见证，或实际源码/Unit/账本/签名/依赖核对任一缺失，外部用途保持关闭。配置、合成公钥、测试 loader 和原凭据名都不能开启这条路径。未启用请求级 sender。

若后续准备实际授权，先冻结独立审查公钥与目标解释器/依赖文件清单。启动器在导入 cryptography 前检查实际目标 Linux 解释器、完整已审文件摘要和 cryptography/cffi/_cffi_backend/pycparser 的实际导入入口，拒绝当前未证的 a3 或已从其他来源导入的 verifier；本轮没有安装或证明目标依赖。随后用固定根管理路径的签名 Go 核实实际发布目录、源码 manifest 和关键文件、正式 Unit 摘要、无已知 drop-in 与实际 cgroup、数据库及同一经济账户。部署前还应独立核实际加载 Unit 的 FragmentPath/DropInPaths 及执行制品；磁盘摘要不替代正式部署现场证据。

只有确认全部绑定并在独立受保护目录持久消费启动挑战后，专用 loader 才能通过原目录见证读新 credential ID。它复查 ACL、只读挂载及文件身份/重复读，且不输出或写入 ENV。旧用途 loader 和 grant 不扩展。已有状态仍需新 sender、官方新鲜余额、受审按次授权和 UNKNOWN 对账；启动 handle 不授预留或发送。未加载真实钥、未发供应端请求、未操作生产。

已验证实际隔离 Main 的两种负例：无源固定 pin、只有合成 pin 但没有真实入口见证；两者都不访问批准文件、依赖或凭据，账户及普通保存照常，预览 503。合成 issuer 仍不能产生 live handle。旧正式入口与系统凭据元数据回归继续保持。
