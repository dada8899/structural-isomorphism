# 本人研究列表端口

2026-10-17，Core；基线 `b2fc48cfccaa7978784d8202020869f994762b2d`。本卡只补保存后找回研究的列表，不改前端、Source、schema、资金或发布配置。

`GET /api/research?limit=1..20&cursor=<opaque>` 沿用当前研究功能开关、统一凭据冲突检查及有效 direct cookie/JWT 代际；响应仍为既有 schema/contract envelope，`data={items,next_cursor}`。

每项仅含 `research_id,title,current_input_revision,updated_at,current_task`。title 来自当前输入摘要，最多160 Unicode码点；无原始正文、owner/principal、task ID、epoch、grant、资金绑定、全局数量或余额。`current_task` 仅当前输入修订的最新任务，形状为 `{execution,evidence}` 或 null；两维直接来自持久状态，COMPLETED 不推导证据充分，历史成功不冒新修订结果。详情继续用既有 GET id。

列表在同库读事务核当前账户/incarnation、owner epoch、研究 active 与 read grant；SQL先过滤并逐项重新核权限，不信客户端owner或缓存DTO。无研究主体时返回空列表，不创建 principal、研究、grant、任务或费用。

分页为 updated_at DESC、research_id DESC 的稳定 keyset，每页硬上限20。游标仅有本操作namespace、不可逆scope摘要和最后一项边界；scope绑定当前principal incarnation与auth generation，不返回它们明文。编码不是授权或新签名服务，任何边界都必须再次通过当前owner/ACL检查，不能放宽SQL过滤。

未知／重复query key、非法limit、空／超长／非规范编码、额外或重复JSON字段、错误namespace/scope/date均拒绝。跨用户／新代际游标不承接旧记录；边界研究更新、撤权或不存在时409重新从首页读。对未变化列表跨页无重漏；不引入全局计数、缓存快照或目录索引。

接口全程 `Cache-Control:no-store / Referrer-Policy:no-referrer`，错误不回显游标或标题。XSS样式标题只是 application/json 文本；后续页面消费者仍须按纯文本展示。

真实原路由/auth/SQLite测试覆盖21条同时间跨页与重开、最新修订/最新任务、原App挂载、空列表零业务写、Unicode/XSS、跨账户/同邮箱新代际、有效凭据冲突/过期/注销/单SSO、撤权与删除、恶意和重复游标、边界失效。原App测试只关闭无关模型/index lifespan，未替代认证或业务响应；测试的client/log handler均自行关闭，sys.path与日志级别还原。最终新增组40 passed；此前38项与必要旧权限回归组合203 passed，均无skip。旧service方法／请求schema AST及全部旧测试字节保持。不代表前端已接入、OpenAPI快照已更新或已发布。
