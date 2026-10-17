# 离线受控生产者：CP1

2026-10-17，Core；基线 `3c8966213d9698330140d4e33bd34ae245394f4e`，分支 `codex/structure-paid-producers-20261017`。本检查点只交授权来源候选读取和最终字节守卫，供原审查者先冻结；没有 schema6、独立付费批准、实际 CurrentPaidAuthority／TrustedCostAuthority 生产者、upper、资金、loader或live接线。

## 受控来源候选

正式 Core 包装为 `read_provider_eligibility(store, identity, research_id, input_revision, research_version, excerpt_ids)`；固定当前同库身份、owner／grant／epoch与当前问题修订，不接受调用者自带 authorizer、owner或许可布尔。仅1..20个独立有效UUID摘录，候选合计≤16KiB，超限拒绝不静默删引用。

包装调用 `EvidenceRepository.provider_eligibility(context, excerpt_id)` 公共读端口。端口内部核不可变记录、缓存／原始／发现／提取摘要、当前显示权、原source/excerpt绑定和Unicode精确短引；不把原文或完整 extracted 暴露给外层。外层不私读 repository `_get` 或操纵 adapter 状态。

仅已审 `plos-author-narrative-subset-v2` 可进入候选。实际从已有存档的 bounded Crossref响应重核该DOI/title的CC BY4元数据，并用原始 HTML 独立重核当前文章版权／署名条件、身份及作者叙述subset；identity/gzip均用既有有界解码，不访问源站、不自动重抓。重提取结果必须与原 immutable text digest及quote偏移相符。旧v1、历史导入、权限未知、缓存损坏或scope漂移拒绝。

返回仅含来源具体版本、摘录ID、scope、原取得时间／cutoff、原始／提取／发现摘要、短引和来源署名候选等冻结数据。两层 `may_send_to_provider` 均固定 false，构造为true会失败；eligibility不是发送能力、资金权限或用户同意。署名候选保留标题／规范URL／许可名，不编造作者；CP2正式外发仍须核齐实际需要的署名／许可要素与当前用户确认，不得把此caption当完整外发批准。

## 最终字节守卫

`provider_adapter.final_request_bytes(prepared)` 重建完整固定请求并严格核最终 UTF-8 JSON：固定model、max_tokens严格整数4096、thinking disabled、无tools、tool_choice none、非流式、固定response_format；重复key、额外字段及完整包/摘要变化都拒绝。模板、schema示例和实际输入合计仍≤16KiB，不接受额外覆盖kwargs。

preconnect前先核；begin在全部授权／loader／consume回调之后、发送敏感字节之前再次核，绑定permit的request/context/evidence摘要。实际send使用该次返回的本地不可变bytes和对应Content-Length，不能借后层引用变更换包。消费后检测失败沿原send_unknown规则，不自称免费或重发；本卡不实现收费处置。代码固定4096不是实际厂商计费completion上界已验，官方语义／资金与v2算术仍由后续卡闭合。

默认 `DeepSeekAdapter().preconnect` 的 paid_disabled不变；未修改probe flag、已有v1费用规则、F或Uobs。普通DTO只用于编解码／边界测试，不是可信来源或支付授权。

## 本机验证与下一步

组合baseline197 passed。原provider/source/evidence组合137 passed、64 subtests；CP1初18项与原D1/v5/owner-index组合215 passed；最后补坏metadata拒绝后新组19 passed。均无skip，无外网／模型／费用／1P／密钥读取；来源验证只用原App/auth/同DB与自建本机HTTP夹具，最终发送守卫只用内存sink，不产生厂商请求。原repository全部方法AST保持，Source parser/schema/公共port、v5、CONTRACT_SPEC、API/UI、现有测试字节不改。

此处不称三producer已全部完成。CP1固定SHA独审后，才进入CP2必要schema6／独立paid批准与当前资金授权来源；CP3再接真实拥有的adapter/session/持久收包来源。Bootstrap拥有后续唯一v2预算helper，Core不得复制另一套F。外部资金／凭据／真实模型／外网仍NO GO。

## CP2 前置：additive v2 报价类型

基线58b196，按 PMO 精确例外仅在 provider_schemas.py 增 `UsageUpperQuote`。字段固定v2 policy、Flash声明版本、CNY/scale6、revision、正native peak miss/output rates、严格 context_bound≥1048576且≤2147483647、output_bound=4096、int63 local_guard、price/model/completioncap/finalcode证据摘要及valid_until。旧PriceQuote／CostObservation／cost_intent与全部旧节点AST不变。

新类型没有F、upper、预留、释放、receipt或可信资金权限。它只约束数据，单字段在int63内不证明乘积可表示；唯一算术与溢出检查由Bootstrap后续usage_upper.py实现。Core正式resolver、真实quote证据、准入时admitted_at与原quote摘要仍待CP2闭合，不能凭DTO或合成行自封trusted quote。

本小检查点新40项边界测试及原provider77项通过；新值全为纯合成native整数，不查真实价格／资金／key。schema6、API、外发packet、CurrentPaidAuthority与成本生产者尚未实施。本文件与quote/test停写交原审冻结后，再按正式范围继续。

## CP2：内部离线确认与当前能力

基线 f19f1056。无公开API：其方法／DTO／错误仍由Architecture合同先行，内部 `PaidApprovalService.preview/confirm` 不自行成为公开路由。默认无resolver直接拒绝，即使数据库合成active行也不能启用；唯一正例依赖显式服务器装配的 OfflineFundingResolver，始终标offline_probe，没有真实资金、凭据或live工厂。

schema6只新增 `research_paid_approvals / research_provider_sessions` 两个producer控制表，并给原grant增资金用途绑定、permit增approval/admitted_at、显式v2 policy与cost差额数据约束。原V5定义／旧行不变，不回放减记。sessions只建表，未实现收包／TrustedCost来源；cost新约束不是F或账务writer。

preview读取当前真实身份／问题和CP1来源候选，核离线配置与当前同币account/quote/basis记录，仅写无能力draft，不建task/grant/reservation/permit/fee。confirm在同owner lease+短同库事务核preview版本／摘要、原问题与当前权限、TTL、受控用途配置；独立创建execute_paid grant和queued单步任务，max_calls=1。Cookie身份、用户确认、许可和资金用途彼此不能替代。

确认后才允许新 `read_confirmed_provider_packet`／repository端口；它只接受同conn/txn/lease实际DB生产的 PaidPacketAuthority，不接受bool/dict或Eligibility。当前许可、具体scope/hash/offset、原版本与manifest重核，creator/year署名必须来自该文章实际articleinfo citation，缺失或长度/结构不明拒绝，不能拿用户同意补版权。full extracted只在内部repr=False字段核验，outbound仍仅短引／必要署名；原CP1候选false和guard AST不变。

完整请求由原固定prepare/guard重建；实际codec制品摘要同时绑定quote与preview，模板/代码变动不能暗换包。确认后request digest只含最终bytes，EvidencePacket.binding_digest另绑定实际分配task/attempt/grant。确认幂等按当前owner核验、原key回原任务，不再次创建。

CurrentPaidAuthority每次require都重核确认行、当前paid grant/epochs/revision/stop/task/step/CAS、注册offline来源、同币quote/basis/完整包摘要；只能产生offline权限。authorize/consume还要求真实同policy HELD全额本票和当前prepared permit/approval绑定/admitted_at，核DB总held含本票；没有“金额差”猜费或旧UNKNOWN转v2。Scope仍按原conn/真实事务/lease机制退休。

Offline resolver的approved_upper为显式服务器模拟授权数据，不是已验真实资金或F计算结果；未来账本reserve必须用Bootstrap独占F重算并核匹配，Core未复制F/Uobs或实现reserve/consume/费用写入。真实来源默认不可用；注册模拟来源退休或服务重启无法重建可信源时，只能拒绝而不能从控制行自证资金。

删除先凭实际pending job清确认payload/permit私密JSON与候选槽、撤销状态，再由原流程去研究/身份绑定；必要opaque摘要不复活正文。迟到成本来源与收费对账仍待CP3，不能把本卡成本行0新增当迟到实费已经闭合。

旧v3/v4/v5迁移探针仅测试fixture隔离v6，原故障／金额／receipt／inode断言保留；旧unknown6改7、当前requirements5改6、PK冲突value5不动。新v5→6逐写入故障回滚测试与内部真实auth/DB确认、单次并发／故障重试、缺署名／改题／撤权／旧UNKNOWN／删除对照独立验证。受影响组合336 passed；最终确认组16 passed（16.38秒），含实际版本/本票/permit变更、旧task幂等准确状态与隐私删除；扩至全部80个迁移写入／移除guard／commit切点后，迁移组81 passed（53.85秒），旧v5非空事实与锁inode保留。CP1原方法AST和guard/quote字节保持。未作生产／真实余额／厂商模型验收，CP3未启动。

§6.4.2后补冻结合同已只读核对，公开适配仍有两个明确缺口：当前内部preview是无能力候选caption，完整creator credit在确认packet口才核；实际bytes digest也在确认分配Context后算。正式API必须再增加无能力的preview序列化端口／模板复用，预览即核齐署名并绑定bytes；不能临时翻may_send或用假task/quote充全文。本卡不改冻结adapter、不开路由、不把当前内部返回对象当外部DTO。确认重放已按原approval.task_id取得当前ResearchView二状态，保留旧ref，不能默认指向新current_task。

## 4347ed6 原审三项最小返修

2026-10-17。v6 cost binding 现在在插入时明确要求 observation／reservation／price／permit 四者的 policy 相同，不能给旧v1票贴v2标签释放差额。旧v1合法全U与新CNY/v2同策略差额分别为正对照，旧金额／V5定义不改。

authorize／consume 除核调用者当前expected版本，还核持久permit上的authorized_task_version／authorized_step_version与实际task／step一致。四种票版本改99的组合均拒，已有cap的require也失效；合法同版本票仍可作为离线权限正例，不代表已实现金融consume。

附属结构检查此前误置于_v5提交前，本轮已移到真正_v6首次复制／建表之前；直接已存在v5库也必须核待替换表的全部显式index／trigger。未知附属结构拒绝并回滚，不再随DROP TABLE静默消失。真实额外trigger/index反例均保留原v5全snapshot及inode，原v5方法不再夹带此v6检查。

作者验证：原审5个票版本／策略拒绝断言实跑5 passed（原extra-trigger脚本要求保留升级，本实现选择更保守拒绝，另以2个真实新反例核exact原库）；原v5安全组+approval+迁移最终220 passed／0 skipped（124.46秒），其中v1不可折减与v2部分／全额三个对照独立3 passed。首轮组合因新fixture未显式导入source_stack出现1个setup error，没有计绿；补齐测试依赖后完整220项通过。原fault81、旧隐式事务退休／REPLACE／CP1 guard等保留，未改原审证据、旧测试或其他源码。API/preview-codec/CP3/F/资金/live仍未进入本轮。

## 无能力 preview codec／完整署名检查点

基线37e4；协调停写后仅合受审preview_bound，续接HEAD188f237。唯一模板从adapter抽到纯preview_codec.request_bytes，确认后的prepare亦调用它；final_request_bytes与begin/finish/preconnect权限守卫AST保持。PreviewOutboundHandle没有Context、fulltext、may_send或资金字段，PreviewRequest不能交adapter发送，不造task/plan/dispatch；固定4096/thinking off/no tools/nonstream和原16KiB整包拒溢出保留。

新独立preview署名口在真实当前owner/revision下重核CP1资格和完整creator/year，返回sources全false及精确outbound handles；旧eligibility/confirmed读口AST保持。缺署名现在preview即拒、draft/task/grant/fee不增。manifest摘要与无能力bytes摘要在确认前保存，确认分配真实Context后重建同codec bytes须逐字相同；EvidencePacket.binding_digest另域，不拿控制ID替身。公开preview_view采用§6.4.2白名单和SHA256(canonical(view去preview_digest))，内部旧别名不准直接成为API响应。

U仅调用受审usage_upper.preview_bound，用真实服务器clock核≤60秒TTL和quote revision/digest；返回值不是reserve/observed凭证，Core不复制F。原合成fixture仅把2033长期quote改当前clock+60，过期／长TTL负例拒绝，不假now/dispatch；真实资金默认None/live closed。原provider/model115项、预览/确认/CP1受影响48项通过。未改DDL、API/UI、runner或CP3；客户/源HTTP/本机sink/timer按finally关闭，公开网络/资金/key/真实模型为0。独审冻结前停写，仍不声称公共API或真实费用链已交付。

## CP3 A：离线实际收包来源

2026-10-17。OwnedProviderSession独占真实loopback socket，登记前和敏感POST前依据原确认approval／funding核实际账户、经济binding／epoch、basis、批准U及合法admitted时窗，不从票据抄值自证；自身finish生成receipt，同auth DB首次CAS保存binding及usage。candidate另槽可擦，首次保存及幂等重放均核当前内容资格：取消／撤权后擦候选，财务首事实不变，已擦不回填。普通DTO、重复注册、损坏binding、退休来源均拒；无完整收包即UNKNOWN并关闭socket／timer。Python私有类型不是任意root代码隔离；合法时窗也不是实际金融消费证明，本阶段待原独审复验。
旧finish只委托共用收包校验并调用原v1 cost_intent；原begin／最终字节守卫／probe标志和旧schema定义不变。测试装配的已消费票及余额均为合成前置，不能证明预算consume；生产注册／send、TrustedCostAuthority及held→upper消费继续关闭，未新增DDL／API／F／资金／凭据或真实模型调用。

## Phase B0：金融准入契约候选

2026-10-17。CONTRACT_SPEC §12选定待审V7最小增量：单例项目预算表将Owner上限P独立绑定唯一经济账户，沿用原账户计数；不可变金融准入表与真实consume同事务保存原quote/F/basis及授权/消费关联。两个上限分别核，删除不改旧擦除规则，仅保新版严格纯金融域，缺失依据UNKNOWN全held，旧A合成票不升级为费用来源。本轮仅文档，未实现表／guard／六writer、迁移或真实资金；B1完整生命周期与observer、B2全部调用者及删号恢复均须后续最小范围GO与独审。

## V7 基础候选：空表、关闭登记与默认拒绝

2026-10-17。追加V7两表／guard、严格纯金融数据模型与连接默认拒绝hook，保留原SCHEMA/C0/v5/v6定义及producer版本6；仅完成6后迁7，已有7先完整校验，部分结构／未知附件不补建。两新表默认空，服务器受控offline配置也只能登记closed单例，项目授权P独立于原资金cap，账户计数不变；普通SQL／DTO、缺hook、旧A合成consumed记录不能取得金融写权。没有Money六writer、资金loader、真实provider或active登记入口，纯快照通过仅表示类型关联正确。

迁移与守卫测试使用临时auth DB及合成数据，覆盖每个DDL／marker／commit故障、进程死亡重开、旧金融值／policy／锁inode保留、真实closed INSERT失败回滚和许可收尾、过期／错conn/PID/lease及复制DB拒。旧隔离v5→v6探针仍真断6；通用当前版本期待才指向7，隐式rollback／cached BEGIN／REPLACE／unknownAux保护保留。API／Source旧路径未实现新收费，Notebook实际组合体验与统一typed读口不由本基础候选预签。

作者最终两组实跑：新基础75＋旧schema／迁移200合组275 passed，原paid／auth／持久化／生命周期／C0／D1及Source期限收尾391 passed，均0 skipped；旧DDL整块逐字不变，两个current-target期待与历史profile隔离的最小测试接缝保留。当前SHA待原独审，实际业务库未迁移，真实资金／模型／生产发送未放行。

## V7 原审 P2：必需基础对象完整性

原审指出V7早返仅核金融结构，漏掉原幂等表及修订不可变guard。本轮将SCHEMA／C0及版本overlay的全部必需table／index／trigger、初始化附加guard和Source既有结构一并校验，缺失／漂移即SCHEMA_UNSUPPORTED；研究／V7对象已存在但marker丢表／丢行／列漂移也在初始化前拒绝，不自动补建。原金融未知附件规则、旧DDL、历史profile和原断言保留；只追加损坏／漂移／实际登记与API早拒反例，没有新资金writer或生产放行。

原strict-reopen两反例已先复现后通过；新增21项基础缺失／漂移及早拒用例。最终新旧金融组296 passed、应用／Source期限组391 passed，均0 skipped；正常v1迁移与旧真实存储故障回滚对照保留通过。这里只修完整性检查，旧证据不改，候选仍交原独审复验。

## v6 启动预检：先验证继承对象，再迁移

原审指出：marker6缺幂等表或修订guard时，直接迁移拒绝，但普通构造先执行SCHEMA/C0补建后成功升7。本轮抽取已审完整legacy对象校验供v6/v7共用；构造识别完整marker6后先只读核基础类型／DDL、Source及附件／FK，再单独进入原V7迁移，不走旧初始化补建。直接V7迁移也先核该继承基底，损坏库SCHEMA_UNSUPPORTED且schema／rows不变；完整6正例、V1–V4获准历史路径及旧profile规则不改。仅基础预检，没有B1六口、资金或发送代码；实际业务DB未迁移，候选待原独审。

作者先复现原2拒绝断言失败，再原脚本／完整6／真实v1迁移4 passed；新增10缺失对象零安装语句、4漂移／未知附件／FK及完整6一次升级正控，扩展前置86 passed。最终旧新金融311 passed，原API／公开校验／持久化／生命周期／C0／D1／Source期限429 passed，均0 skipped；旧DDL区块与所有原测试前缀逐字保持，独立基础候选交原审复核。

## B1：受控离线预算与实际收包纵向候选

唯一paid_budget写者接实际reserve／authorize／consume／cancel／observe；先真实API预览确认、受控offline项目试验启用、足额held，再外部preconnect、同库消费与immutable admission同落。消费commit成功后由独立连接回读可见事实，B专属session才一次begin／自身finish／sealed receipt；首次persist核实际所属资源与receipt，重启observe只读受保护admission／金融return，不要求进程内OWNED，不重造收包凭证。旧A合成consumed／DTO仍不授B能力，F／adapter及旧A实现不改。

写许可绑定实际conn／txn／PID／lease／operation／目标row与version；现有authorizer组合保护活动预算的票／返回／观测写入，私有scope进出刷新同一authorizer以拒缓存SQL越权，原trace／rollback退休保持。P、原C与fresh保守B分别核，项目／账户／票CAS共享；完整可信usage按原F仅一次U→Uobs、actual=null，坏正文不免记用量。缺首次持久return、丢ack或死亡不再begin／重发，UNKNOWN全held；删除后只用允许金融域核对，正文／任务不复活。

新B1专属31项与原金融组组合327 passed，原消费者／auth／保存／生命周期／C0／D1／Source期限391 passed，均0 skipped。覆盖两进程不同任务争P、两新进程同return一次记账、实际SQL各故障点／真实commit丢ack、consume后begin前及完整receive后未持久死亡、P较大而C/B更紧、真实删号／撤权／取消后的财务处理。只使用隔离auth测试DB、合成资金及本机TCP；B2全部真实caller与HELD取消／删号lease封边未签，公开worker仍拒paid，真实Owner/funding/loader/live/新purpose未放行，当前候选待原审。
