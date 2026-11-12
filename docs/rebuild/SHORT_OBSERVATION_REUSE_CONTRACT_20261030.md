# 单问题短自述：现有调用合同

2026-10-30；Core。原02／Mentor裁定、原Astra限定接受；仅用于真实适用的8–1000字本人现象自述。未证明任意问题、U2、4000字研究规划或真实模型可用。本稿与独立短自述测试不改 Native approved-code paths；首个有用组合无需选择先前 b2a/e65/d3 中的闭合草案API或未接线codec。它们的WIP历史继续保留。

**用户输入一次，先看完整原话卡，明确采用本人原话，再核外发范围与费用。** 原话卡写明“本人原话，尚未进行系统分析，未知项未填写”。采用按钮为“采用这段原话作为本人现象自述”，另有真实本人权属声明；默认不勾确认。采用与外发是两个可见动作。

| 阶段 | 精确接口和内容 |
| --- | --- |
| 保存采用 | `POST /api/research`，schema_version=`structure-research-v1`，contract_revision=`b1-candidate-01`；data.problem=`{entry:"phenomenon",original_input:raw,objective:"",summary:raw,variables:[],constraints:[],unknowns:[],confirmed:true}`。只有明确采用动作后发送。summary标为本人原话，不称模型整理；该字段按既有规则可能NFC规范化，逐字原话始终是original_input。 |
| 追加修订 | `POST /api/research/{id}/revisions`，同b1合同，data=`{expected_revision,problem}`；使用实际版本，不另造研究或覆盖旧修订。 |
| 外发／费用预览 | `POST /api/research/{id}/plan-previews`，contract_revision=`funded-plan-v2`；data=`{input_revision,expected_research_version,observation_source:"own_observation",declaration_status:"self_declared"}`。id／修订／版本取保存回执。展示exact_input、purpose、目的地、报价上界、can_confirm与funding_reason。外发字节来自original_input，不拿NFC后的summary替换。 |
| 明确外发 | `POST /api/research/{id}/plan-approvals`，同funded-plan-v2；原样回传preview_ref、preview_digest、request_digest、expected_research_version、approved_upper_units，加confirm_outbound=true。用户看过范围与费用再确认，不自动审批或抬上界。 |
| 结果／重开 | `GET /api/research/{id}/plan-results/{result_ref}`与既有研究视图／历史；只读原task/ref，不重发。区分queued、generating、saved、failed_insufficient、pending_reconciliation。候选／0–3关键追问／查询建议为线索，文献、数学和机制仍未验证。 |

1–7／1001–4000字与其他用途在页面精确保稿并说明现范围缺口，不切片、补字、假摘要或要求重写来过门。第三方资料、URL/code不能伪报own_observation；同修订已有Source流程的限制继续生效，资料综合走原evidence目的。后续Source仍要真实许可和Ref，不能拿候选当研究成果。

## Native真实准入：复用已实现生命周期

Main `main.py:215–235`已有prepare_main_context→native.start；`native_plan_supervisor.py:505–527`已有entry witness→grant→flight→credential→bind/install session；`:529–538`先恢复旧active/held/UNKNOWN，未解决就不激活，`:540–546`才出生worker并进入READY。Core当前没有证据要求新生命周期框架。

04需要闭合的是最终组合SourceSHA／approved code identity对应的真实安装与资源事实：systemd provider entry（不展示值）、当前Main scope的grant/flight、Owner与代际、共享economic account／持久CNY300、旧账本恢复。现有static回执与旧CODE_IDENTITY_INVALID不代实际安装；FUNDING_CLOSED单一健康事实不能区分失败子阶段。fresh balance只在原获准run_once/slot内获取和核账，外部数值或静态报价不能替代。既有两次queuedACK后pending仍UNKNOWN，同前提真实发送继续HOLD，不用新label或loopback grant重置失败。

## 本地验证范围

独立文件 `web/backend/tests/test_research_short_observation_entry.py`只测ASGI/Auth保存重开、未确认拒绝、明确采用修订、空objective/集合、原文出站纯字节、NFC区别、CAS冲突、账户隔离、未适用长度及URL/code拒绝。零worker birth、零资金安装、零provider/Source实发，不是Main15或线上执行验收。部署与Owner使用另收事实。
