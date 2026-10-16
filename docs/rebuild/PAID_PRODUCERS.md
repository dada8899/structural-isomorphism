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
