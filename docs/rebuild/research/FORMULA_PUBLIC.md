# 有限公式的纯公开内容适配

日期：2026-10-17；基线：`6387213e9d6785ebe3ece75bc94221391d141d0a`。本轮仅输入草案、结果内容校验和展示，不增加家族、科学算法、API、任务、来源事实、数据库或执行权限。

`formula_public.parse_formula_draft` 接受三家族四模板内的结构化草案。复用原 Node／Symbol／Condition／InitialValue 解析及数值限制，保原 display 文本；草案拒绝 server id、research/task/attempt、source_refs、callback及 checked/授权字段。符号名是局部数学标识，不是服务器记录ID。模板与单位只是已登记范围检查，不证明量纲、假设或现实对应已成立。

`parse_comparison_draft` 保留原三比较域、四check kind、单侧限制及256点上限。输入不足不生成任务；未登记家族／模板／单位明确拒绝，条件声明保留true/false/null，true不升级为观测证据。公开草案视图固定未核授权、执行、来源与display，摘要只是内容绑定。

草案content_digest、完整FormulaCheckInput.input_digest和外层ProblemRevision摘要是不同内容域；不能直接互比，也不能当服务器对象id。完整结果output_digest只校验内容，仍须Core另取当前受权不可变元数据和真正执行来源。

`formula_result_adapter.project_formula_result` 只接受已有结果内容及调用者另取的原 FormulaCheckInput 和独立 output_digest；重新用原解析器核输入，严格核完整结果字段、研究/修订/task/attempt内容绑定、policy、scope、formula/source具体版本、摘要、check集合、trace链和样本／容差范围。它不调用 FormulaChecker、纯数学核或权限callback，不生成id／task或执行记录。

原 passed/failed/inconclusive/unsupported/resource_limit 与六种relation、trace／samples／limitations均按原结构保留，不把数字一致变成恒等，不把方程同形变成初值问题等价。结构、摘要或trace一致也不证明结果确由受控worker产生；独立元数据不能由浏览器从同份结果自报。

投影固定 authorization_verified/execution_attested/source_facts_verified/display_checked=false。provided_formula_refs保提供的版本引用，不是本模块签发的服务器id。原resource_guard只标reported，不从字符串宣称已隔离。原式与受检AST并列显示，display不解析／执行；条件为用户声明。curated_reference与product_excerpt原类别保留为declared_provenance，均要求Core另核来源授权；本纯视图不暴露locator／私有路径、不虚构原文读取。

输入含64 KiB边界、结果与最终视图512 KiB；JSON先限深24／节点20000，拒未知／嵌套字段、重复key、非有限／float和坏Unicode。AST只调用原有16深／128节点解析器，没有新的无限递归解析或字符串求值。数值结果只校验有限文本形状，不重算科学结果。失败抛固定安全异常，实际context/cause槽清空，不回原Pydantic材料／调用者敏感异常。

真实执行与保存仍待Core冻结当前任务／来源reader、stop/epoch/CAS及check/result保存读取；然后使用原Linux隔离checker。纯类型、内容摘要、用户declared或lambda不能授予调用资格。资源guard不支持时仍应按原checker拒绝，不能改走纯核冒充产品执行。

新测试复用既有有限fixture和纯数学核的真实结果作为数据，绝不运行FormulaChecker／worker；这些合成task UUID只是测试内容，不对应创建的任务。测试保四主要关系、三scope、失败／不足／不支持／资源分类、反例及私密异常不泄露，不是实际页面、Linux隔离或现实机制验收。

原审两项内容一致性返修：结果来源按原每侧≤20条合并去重，合法并集最多40条，具体版本和输入64 KiB／结果512 KiB保持；不截断并集。样本仅左右arithmetic都为exact_rational才允许comparison=exact且无容差，其他组合必须沿原固定容差。此处只核类型与标签一致，不重新比较数值或增加科学模板；混合类型反例也不代表新模板配对已获支持。
