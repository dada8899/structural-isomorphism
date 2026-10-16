# B1 实施记录：问题持久化与账户生命周期 A

日期：2026-10-17。当前任务：D1 来源发送者生命周期直接 P1 修复；固定基线 `9bb9bf40816e67124f9012f3ebbe2eb556413f61`，分支 codex/structure-d1-integration-20261017。本轮未提交／独审／接线。C0 页面两项已在 1a64f722 同 Astra 复核关闭；D1 正式接线仍暂停，不能把父监督／daemon 当作发送者在父 SIGKILL 后的约束。

**当前候选增加固定两步的本机离线任务、精确演练账本、取消／未知回执／重启处理。真实研究、公式检查、真实供应端费用与匿名研究认领仍未实现。** 新研究入口默认关闭，生产环境即使设置启用开关也始终拒绝。不能将本闭环解释为完整 B1、三项产品能力或可发布版本。

## 用户能完成的事情

在测试环境启用 `STRUCTURAL_RESEARCH_ENABLED=true` 后，使用现有账户的直接登录会话进入 `/research`，填写问题与目标并保存。保存成功后地址只包含 opaque 研究 ID，正文不会进入 URL。修改保存为新修订；历史问题保留，服务重启后仍从同一磁盘数据库读取。

页面使用“问题记录／尚未执行研究”说明当前状态，不展示虚构候选、证据或任务成功。失败保留输入；修订冲突要求重新读取；账户失效或跨账户拒绝后清空已经呈现的私有内容。页面提供私有链接重开，本次没有“我的研究”列表、匿名保存、分享、导出或完整工作台。

保存请求使用契约信封：`{schema_version, contract_revision, data}`。创建的 data 为 `{problem}`；修订的 data 为 `{expected_revision, problem}`。每个 POST 必须提供 `Idempotency-Key`。相同操作标识与相同正文返回原结果；标识相同但正文不同返回 409。结果不明时，页面保留操作标识和请求摘要；它不在浏览器存储研究正文。摘要前，页面按服务器相同字段执行 NFC 归一，但 original_input 始终保持原样；修订操作另保留原 expected_revision，避免重新读取后把同一请求变成另一次写入。

本次实现的正式导出为 `research.ResearchStore`、`research.ResearchService`，其他内部实现分别位于 authorization、schemas、projection、errors。Python 服务接口要求服务器创建的当前账户身份；HTTP 入口不接收客户端指定的 owner、epoch、grant、版本终态或账务事实。

## 数据与权限实现

| 部分 | 当前实现与边界 |
| --- | --- |
| 物理数据库 | 复用现有 AuthStore 初始化与 WAL；研究表就在 `AUTH_DATA_DIR/auth.sqlite3`。A 在 AuthStore 增加账户 lifecycle、持久 owner gate／配置指纹及删除 job |
| 迁移 | 同库 `BEGIN IMMEDIATE` 执行 research_schema v1→v2，保留修订与既有锁 inode，新增主体 gate_id；未来未知版本拒绝，不静默升级 |
| 原子保存 | 账户存在、session_generation、JWT jti 撤销／到期、主体状态／epoch、研究 owner／acl、grant 与写权限在实际事务内重核；修订采用 version／revision 条件更新 |
| 身份延续 | 主体绑定账户 incarnation，重新注册同名邮箱不继承旧研究；旧 cookie 被拒绝。只接直接账户会话，不把旧 SSO 身份猜成已支持的新研究身份 |
| 修订与幂等 | 数据库触发器拒绝更新旧修订；非空 scope_key 的唯一键消除 NULL 不互斥；同一事务保存修订、控制版本和幂等结果 |
| OS owner gate | 私有目录中按持久 opaque owner gate UUID 的稳定文件锁，校验目录／文件类型、属主、权限、链接数并拒绝 symlink；有界等待，不删换锁文件；进程退出由 OS 释放 |
| 隐私和请求边界 | 64 KiB 请求上限、严格对象／额外字段拒绝、重复 JSON key／非有限数／bool 冒充整数拒绝、文本和数组边界；错误不回显输入或 Pydantic input／ctx；读取和响应 no-store |
| 当前保护边界 | 账户删除与既有账户事务 wrapper 已共享 gate，deleting 资格不会被旧 registry 补偿恢复；匿名研究认领、runner、取消／预算仍未实现，A 仍待独立代码验收 |

OS gate 的当前证据仅覆盖已审代码的单机进程、保存／删除的两种排序与进程退出恢复，不证明多机、旧二进制混跑隔离或尚未实现的网络外发／认领排序。本轮没有读取、迁移或删除真实用户数据。

## 首闭环验证记录（截至 00a916b）

应用测试使用 CPython 3.11.15／macOS arm64，以及只读复用的 runtime 候选环境：FastAPI 0.135.0、Starlette 1.3.1、Pydantic 2.7.4、httpx 0.27.2。没有安装、修改或复制该 owner 的代码／依赖。本分支 requirements 仍是受审基线旧声明，不能称组合环境已经就绪。

| 检查组 | 结果 | 实际覆盖 |
| --- | --- | --- |
| 新持久化测试 | 34 项在下行完整回归中通过 | 真实 auth HTTP→研究 API→同库磁盘 SQLite；幂等、历史修订、重开、跨账户、logout、同邮箱新 incarnation、严格输入／版本／64 KiB／Origin、存储失败回滚；两个真实进程并发相同创建和竞争修订；OS gate 持锁进程退出后同 inode 恢复；新增六种凭据组合对照 |
| 新测试＋旧 auth、beta-primary-auth | 99 passed | 原 93 项保留并追加六种统一凭据检查；不等于新研究已支持所有旧身份入口 |
| 真实浏览器 | 5 passed | 保留原两项 375 px／XSS／重启／权限／同 key 证据；追加 NFC 丢回执并页面重开后确认、实际 commit 暂扣回执时控件冻结及失败恢复、无效 SSO 清空此前私有 DOM |
| main 安全头＋OpenAPI，使用 runtime 候选环境 | 25 passed／6 failed | 6 项 generator 检查明确拒绝实际新依赖版本与本分支旧 requirements 不匹配；没有改断言、跳过或放宽检查 |
| OpenAPI，使用现有匹配基线环境 | 11 passed／1 failed | 既有 FastAPI 0.115.14／Starlette 0.46.2／Pydantic 2.6.1 环境，无新安装；唯一失败为正式快照尚未同步新增 API |
| 其他 | 通过 | JS 语法、diff 空白检查；作者查看 375 px 长截图，表单及历史记录可顺序阅读，无横向溢出；不是独立体验或用户验收 |

浏览器由现有 pytest／Playwright 环境控制，HTTP 应用进程使用上述 runtime 候选 Python。仅关闭与本次无关的旧检索／模型 lifespan；账户、研究 API、SQLite、权限、投影与页面没有 mock。丢回执用浏览器网络故障注入：真实 API 已完成提交后再中断浏览器响应，不使用预置成功 JSON。没有调用外网模型、真实邮件或付费服务。

复现命令在仓库根执行。`RUNTIME_PYTHON` 指向上述只读候选 3.11 环境，`BROWSER_PYTHON` 指向现有包含 pytest／Playwright 的 3.11 环境；本记录不固化本机绝对路径：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_persistence.py -q
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_persistence.py web/backend/tests/test_auth.py web/backend/tests/test_beta_primary_auth.py -q
STRUCTURE_RESEARCH_TEST_PYTHON="$RUNTIME_PYTHON" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$BROWSER_PYTHON" -m pytest -p no:cacheprovider tests/test_research_browser.py -q
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_app_hardening_launch.py web/backend/tests/test_security_headers.py web/backend/tests/test_openapi_artifact.py -q
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$BROWSER_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_openapi_artifact.py -q
node --check web/frontend/assets/research.js
git diff --check
```

## 接口快照与下一检查点

只读运行正式 OpenAPI generator 比对基线：新增 `/api/research`、`/api/research/{research_id}`、`/api/research/{research_id}/revisions`，没有删除或改变既有路径，也没有新增 components schema。本次手动受控解析请求以拒绝重复 key 和回显，严格对象实际存在于 research.schemas；面向 SDK 的完整请求／响应 schema 文档化仍需后续冻结准备，不能把当前 generic OpenAPI 当全部契约已发布。

OpenAPI／TypeScript 快照由 PMO 在组合候选后交唯一生成 owner 处理；本次没有改产物、依赖、生成门禁或其他 owner 的测试。组合当前 SHA 的必要 CI、独立代码审和真实消费者仍待完成。

A 通过独审后再接匿名研究认领与迟到写入、持久 runner 的取消／恢复、精确共享预算与未知收据、有限公式与证据报告、旧收费 sink 的 Guard 或明确停用。现有三项真实产品能力、真实供应商上界、外部研究效果、Linux、完整模型启动、迁移恢复、VPS 发布、稳定观察与用户实际使用全部未验。

本次创建的 API 子进程、浏览器 context／browser、端口 socket、日志句柄和多进程测试均由创建者在 finally 关闭；专属截图／合成测试目录检查后收尾。没有留下服务、worker 或后台调度。源码候选保留供独立审阅，作者停写后由 PMO 接续。

## 首闭环独审与已复核返修

首闭环独立 Astra 完整审阅发现一项 P1、两项 P2，已在 00a916b 由同一 Astra 复核关闭。以下只追踪该历史范围，不抵消 A 的新审查。

| 独审问题 | 返修 | 原反例与合法对照 |
| --- | --- | --- |
| P1：direct cookie 绕过统一双凭据冲突检查 | research API 先调用统一账户解析，拒绝冲突或无效的另一凭据，再要求本轮支持的 direct cookie；没有借此启用单独 SSO | 下行列实际 API／浏览器对照 |
| 验证 P1 | 真实研究 GET、创建、修订、相同 key 回放与 /auth/me 成对调用 | A direct＋B 有效 SSO 均拒绝，研究返回 409；A direct＋无效 SSO 均 401，数据库行数不变且无正文；direct-only、同身份双有效合法；SSO-only 虽 /me 有效，新研究仍 401；无效 direct＋有效 SSO 也拒绝。浏览器原页面遇到无效 SSO 后清空私有表单与历史 |
| P2：pending 原始 JSON 摘要与服务器 NFC 结果不同，重读后无法确认原保存 | 发请求和算摘要前，仅按 ProblemInput 相同规则归一 objective、summary、constraints、unknowns、变量 label／observation；原始问题不归一 | 下行列实际 NFC／原始输入对照 |
| 验证 NFC | 真实修订提交后丢浏览器回执，reload 从 DB 读回 NFC，再以原 key／原 expected_revision 确认 | 摘要／目标／约束／未知含分解字符的第二修订成功确认，DB 仍两条修订；original_input 的分解字符逐字保留。原 ASCII／中文正常幂等对照继续通过 |
| P2：提交期间仍能编辑，迟到 render 静默覆盖新稿 | 提交至回执处理完成期间冻结全部 input／textarea／select／button；手动重新读取也使用同一 busy 边界；finally 恢复操作 | 下行列实际回执／失败对照 |
| 验证稿件保护 | 真实 API 已 commit 后暂扣浏览器响应，在释放前检查所有编辑控件并尝试键盘输入 | 原稿不变，放行真实回执后控件恢复，可编辑并保存新修订；另用真实 422 验证失败保留输入并恢复编辑，修正后可继续保存；UNKNOWN 回执对照同样恢复控件并保留原操作标识 |

该次三项返修仅覆盖 API admission、页面脚本、两份 owner 测试和实施记录，未改 auth 公共实现。A 的新增范围与当前验证以下节为准。依赖、CI、接口快照和生成门禁均未更改。

## 生命周期 A 基线（6baaf49）：删除开始后不恢复旧资格

本轮只接保存研究与现有账户删除，不建立通用 worker／计费／权限平台。HTTP 删除仍使用既有 `/api/me/delete`、统一凭据校验、同源检查和 `DELETE` 确认。账户保存、旧收藏／报告／SSO 写入口通过现有 account_owner_transaction 共同使用同一持久 OS gate；没有把“同邮箱共门”当作同一身份。

同一个 auth SQLite 内，AuthStore 增加账户 lifecycle、owner gate 绑定、HMAC 配置指纹和删除 job。owner key 使用既有隐私标识入口；数据库只存 HMAC 标识及随机门 ID。没有 auth_users 行的旧 API key 也能取得同一互斥门，之后账户注册仍建立全新的 principal／generation，旧 key 不能取得新研究资格。新连接及研究事务核对配置指纹；运行中换 key、另一进程使用不同 key 都拒绝，不默默分裂锁。

删除在取得 gate 并重新验证身份后，先用同库事务持久保存 auth deleting、principal epoch 递增、grant 撤销、研究 deleting 和 job，再清研究正文／幂等响应，最后执行旧 registry。旧 registry 的原始补偿保留，但它恢复旧收藏或 SSO binding 时，已提交的新资格屏障仍在；direct、SSO、旧 API key 的读写均不能回到 active。

| job 状态 | 已经发生的事实 | 允许的恢复 |
| --- | --- | --- |
| pending | 访问已停止；研究内容可能尚未清理，或旧 registry 清理未完成 | 仅本机继续同一已登记任务；保留处理所需的私有 email／generation 绑定，不能重新登录激活 |
| scrubbing | 新研究、旧 registry 和 auth 行已清理；job／principal 私有绑定已清空，旧 WAL 帧尚待确认截断 | 只对同一 auth DB 完成受控 checkpoint，不重放旧 registry；旧读者阻塞时返回未完成 |
| completed | WAL 清理已确认，只剩无正文的 opaque job、门、epoch 和计数收据 | 相同 job 幂等读回收据；新注册是新身份，旧研究和权限不复活 |

恢复入口仅为当前受控进程里的 `api.auth.pending_account_deletions()` 和 `resume_account_deletion(job_id)`，没有 HTTP／用户 CLI／新 admin 或凭据旁路。只接受一个已存在的规范 UUID，不接受邮箱、数据库路径、任意回调或动作；任务还绑定原数据库位置和固定旧存储／SSO 派生的摘要。错误存储配置或把 job 拷贝到另一 DB 都拒绝。处理方须核对当前批准版本、配置和同一数据根后逐任务恢复；本候选没有自动后台接续。

这里的清除证明包括新研究正文、幂等响应、auth DB／WAL 的合成 canary，以及 completed 收据不含原邮箱／generation；旧收藏和报告分别检查实际存储与访问拒绝。不是旧环境全面接管、备份／swap／文件系统取证清除或真实用户数据迁移证明。

### 用户看到的删除结果

后端在持久屏障之后失败，会返回 `cleanup_pending`、`access_ended=true` 和固定说明，不伪报 200。`my-reports.js` 仅修改原删除提交分支：确认清理未完成时隐藏旧资产、禁止重复删除／导出，并保留实际可用的退出；向用户说明“账户访问已停止，清理尚未完成。请联系维护方继续处理”，不展示 DB、job 或路径。

正常 200＋ok=true 才跳转删除完成页；未获准的请求说明本次未获准并要求核对状态。网络／不可信响应只说结果未确认，禁止盲目重复提交，不再声称“账户与数据仍保留”。现有账户页面在退出后仍采用普通匿名页面；这不表示重新登录可以恢复 deleting 资格，服务端验证会继续拒绝。未来生产运行的通知与持续恢复体验仍需整体验收。

### A 的实际验证与边界

应用仍是本机 CPython 3.11.15、macOS arm64 与前述 runtime 候选图；Linux 未验。所有账户／资金外部调用均为合成或未启用，没有收费、SSH 或真实账户删除。

| 检查 | 当前作者证据 |
| --- | --- |
| 完整受影响组 | 231 passed，0 skipped（22.11 秒）；包含原 225 项及新增 6 个锁冷创建／负例，旧两项并发收藏断言未修改 |
| A 定向与旧并发 | 20 passed：两个原并发收藏及 A 风险；真实两 API 进程保存→删除、删除→保存；两处真实进程退出后新进程恢复；旧库补偿仍禁读；原 key／同邮箱新身份不继承；v1→v2 保持原 inode；HMAC 进程不一致／运行变更拒绝、同 key 合法；错误恢复目标与 DB 副本拒绝 |
| WAL 长读者 | 真正持有旧 SQLite 读快照时删除返回 503／cleanup_pending，资格已停止且处于 scrubbing；释放读者后同 job 完成，旧 registry 不重放，原 auth DB／WAL canary 清除 |
| 新实际应用浏览器 | 9 passed，0 skipped（19.42 秒）；原 5 项加删除 4 种结果。暂扣／丢回执只注入真实服务网络边界，实际 auth／API／SQLite 没有 mock。pending 的退出已实际点击验证 cookie 清除 |
| 原页面和脚本 | 原报告／仪表板 4 passed，原 public_controls 所选 4 passed；10 个现有 Node 脚本全部 exit 0，包括 privateNavigation／historyPrivacy／reportTrust；不改旧断言凑绿 |

浏览器 launcher 在导入实际 main 前，把真实 ReportStore、收藏 legacy 源路径绑定到本任务合成目录；不访问默认旧历史文件。旧模型 lifespan 仍关闭，因此不据此称模型启动、检索或完整产品通过。磁盘故障／进程退出仅在实际执行点注入，不替换权限或持久化结果。

完整受影响组的复现命令：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_persistence.py web/backend/tests/test_auth.py web/backend/tests/test_beta_primary_auth.py web/backend/tests/test_account_data.py web/backend/tests/test_sso_report_claim.py web/backend/tests/test_favorites.py web/backend/tests/test_research_lifecycle.py -q --tb=short --show-capture=no
STRUCTURE_RESEARCH_TEST_PYTHON="$RUNTIME_PYTHON" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$BROWSER_PYTHON" -m pytest -p no:cacheprovider tests/test_research_browser.py -q --tb=short --show-capture=no
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$BROWSER_PYTHON" -m pytest -p no:cacheprovider web/tests/e2e/test_report_share.py -k 'my_reports or report_dashboard' -q
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$BROWSER_PYTHON" -m pytest -p no:cacheprovider tests/test_public_controls.py -k 'my_research_unifies_assets_and_account_rights or report_list_is_an_action_workbench or primary_navigation_starts_at_the_real_workbench or beta_auth_entry_is_user_visible_and_canonical' -q
```

Node 合同逐文件执行 `node web/frontend/tests/test_*.js` 中每个匹配文件并检查返回值，不能把 shell 一次展开当逐项测试；此次实际 10 文件均 exit 0。JS 语法、Python AST、diff 空白及旧文件函数改动范围另行核对。

### 失败记录与直接修正

旧测试中十项要求“删除失败后继续登录／写入／使用旧 SSO 码”，与已授权 fail-closed 决定冲突。先保留原断言取得失败证据，再经 PMO 精确交接，只更新 account_data 九函数及 sso_report_claim 一函数；原始补偿数据、错误状态、孤立账户、合法新 key／新身份／SSO 和并发对照均保留。三个线程测试增加 finally，早退也释放屏障并回收线程。

首次这些旧线程测试提前失败时，在新工作树遗留本任务纯合成 `web/backend/data/favorites.jsonl`，153 bytes，SHA-256 `188ffed57b98670fe9a5bfd4cb4dfba7ea01a04945523c818c95e4612f7080f1`。旧 legacy 自动迁移将它带入后续 fixture，造成首次创建 201 变 200。核对该精确摘要、未跟踪状态和唯一已知 fixture 内容后移除此任务生成文件；没有清理其他旧数据。新增多进程测试另固定仓库全限定模块名，避免旧测试前插 sys.path 时子进程错载其他 tests 包。这些失败没有当作产品成功。

随后完整组曾 225 passed，但另一次真实并发收藏出现 gate openat ENOENT，独立精确测试也复现，旧绿灯未覆盖该问题。作者无 API／SQLite 的 OS 冷创建探针 40 轮、8 线程、320 次操作取得 63 次 ENOENT；独立 Astra 100 轮取得 450 次。两边失败时目录 fd／路径 inode 稳定、目标实际存在，未发现 gate ID 分裂或 double-close。预创建与 exclusive-create／EEXIST 后无 O_CREAT 打开两个对照均无错；仅界定本机首次并发创建窗口，不宣称已知 OS 通病或 Linux 已复现。

最小修正为 O_CREAT＋O_EXCL 独占创建，仅 EEXIST 时以原 RDWR／NOFOLLOW／CLOEXEC 打开既有文件；其他错误拒绝。类型、属主、权限、nlink、稳定目录 fd、不删持久锁均保留，没有添加 ENOENT 重试或 DB 调度平台。新测试以真实 Gate 做 20 轮×8 线程冷创建与实际文件临界区计数／同 inode，并拒绝 symlink、hardlink、异常文件／目录权限及目录 symlink。原并发收藏、两进程、退出重开等仍须在该修正源码上通过。

A 结束前创建者关闭本任务 API、浏览器、socket、日志句柄及进程；小型 OS 诊断 TemporaryDirectory 已在 finally 清理。没有跨回合服务或自动任务。下一步是 PMO 精确提交和完整 A 当前 SHA 的独立 Astra 审查；本机定向诊断不是该审查通过，也不放行合入、共享冻结、真实付费、迁移或发布。


## A 完整独审两项返修（677081125 已接受）

独立 Astra 对 6baaf49 完整审阅回收两项阻断：最终 auth 清理失败后，旧 registry 虽不能恢复登录资格，却恢复了报告和分享凭据，公开读取／反馈仍能使用；另一个真实进程退出窗口使恢复时的零删除数量覆盖了原任务已完成的删除事实。该两项已由同一 Astra 在 677081125 复核 No findings；以下保留其范围与原反例。

### 资源所属状态与提交一致性

报告六个 HTTP 入口统一检查**服务器已存的资源 owner**：share、id、匿名列表、feedback、followup 写与读。公开分享不借用访问者 cookie 判断所属账户资格。SSO binding 可直接定位；direct 登录未建立 exchange binding 时，只在当前 AuthStore 登记身份中按固定 server subject 派生匹配。未读取 secret 文件或接受请求邮箱／owner；无法解析、非规范 owner 均 404，不借访问者的有效账户放行。

owned 资源取得同一持久 account gate 后重新读取资源与生命周期；公开匿名资源仍可合法使用。三个 Store 写方法 record_view／record_feedback／record_followup 接收 server-only expected_owner，在实际 history BEGIN IMMEDIATE 内比较所属关系后再写。未传的兼容 sentinel 与明确 None 分开，None 表示必须仍是匿名；身份变化抛固定异常，HTTP 返回统一 404。原 UPSERT、计数、回访转换与校验不变。

因此两种顺序均可验证：先完成匿名写入，再认领／删除，属于合法旧事实；读取后先发生真实认领／删除，再尝试写入，数据库拒绝旧预期，不追加正文。已 owned 的反馈与删除则按同一 owner gate 排序。匿名列表仅过滤生命周期不允许的资源并按可见项分页；**active 的 claimed 报告仍沿用已知旧匿名列表权限语义，PR #247 的独立隐私筛选尚待受控吸收，本次没有宣称修复它。** Store get_by_id／list_by_anon 源码未修改。

全仓非测试 Python 调用扫描只找到四处 record_* 调用，均在 api/report.py，现已传入服务器 owner；低层默认兼容不提供任意 Python／root 或其他未登记执行代码的隔离。本次未扩展 report 保存／认领实现、旧模型外发、后台 worker 或部署。

### 原任务收据与未知事实

旧存储副作用之前，auth DB 先持久记录 legacy_attempted；delete_all 成功返回后，立即持久保存原 legacy receipt，再进入 finish。已有原收据时恢复直接使用，不再次删除空存储，也不以重试零值覆盖原数量。原 exit74 窗口现能保留 1 条收藏、1 条报告、1 个账户和原研究数量；重复恢复不改变收据，也不删除新注册账户的资产。

新增更窄窗口：delete_all 已完成、原收据尚未保存便实际 exit75。此时无法证明原数量，恢复结果明确 count_status=unknown_after_interruption，仅把本次清理观察放在 recovery_observed，不能把其中 0 当原任务数量。旧 pending job 升级时也按可能已经尝试处理，不根据缺字段推断未执行。

定向测试还暴露一条关联写入：删除中重新申请登录链接可能在已清 auth 库增加 email-bearing token。add_token 现在用同库短事务检查 pending／lifecycle；request_link 返回与生产成功同形的通用确认，不保存 token 或发送无效邮件，不返回删除状态。已有 token 仍不能登录，清理完成后正常新注册对照继续通过。

### 当前验证

| 检查 | 作者结果与实际范围 |
| --- | --- |
| 完整受影响组 | **388 passed，0 skipped，36.19 秒**。包含原 A 全组及原 Store／SSO／report API／flywheel 回归，原并发收藏断言不改 |
| 资源与两种排序 | direct 无 SSO binding、SSO binding 两种正常 owner／pending／完成／同邮箱新身份对照；未知 owner 拒绝；匿名分享与反馈仍 200；实际两 API 进程反馈／删除双序；匿名读取后真实 claim／delete 与三种写入的双序；待删项超过一页仍不阻断合法匿名分页 |
| 收据与进程退出 | 真实 exit73／74／75、正常完成、重复恢复；74 保留原 1／1／1，75 原数量 unknown；删除中不新增登录 token，恢复后旧凭据不恢复 |
| 真实应用浏览器 | **10 passed，0 skipped，24.32 秒**。保留原 9 项，追加真实公开分享页：正常显示、最终清理故障与补偿后刷新显示失效、反馈 404 且数据库没有新 note。实际账户／API／数据库均未 mock |
| 前端合同 | 10 个既有 Node 脚本再次全部 exit 0，前端产品脚本未改动 |

唯一需要更新的原报告测试为 test_report_api 的 test_shared_historical_snapshots_recursively_drop_user_aggregates：原 fixture 将未定义 account-a 当真实 owner，新策略正确拒绝。经 PMO 交接，仅在该函数创建私有目录中的真实 active 合成账户，并使用 server subject；原 share 200 和所有递归聚合剥离断言完整保留。未放行未知 owner，也不访问默认源码 auth／SSO 数据。

新增浏览器对照最初使用旧格式测试报告，被既有页面完整性校验拒绝。改用仓库原有完整性校验通过的合成报告夹具后验证正常／待删除两态；没有修改或关闭页面校验，没有调用模型或把夹具当真实研究成果。

当前完整命令比 A 基线增加三个既有报告测试文件：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_persistence.py web/backend/tests/test_auth.py web/backend/tests/test_beta_primary_auth.py web/backend/tests/test_account_data.py web/backend/tests/test_sso_report_claim.py web/backend/tests/test_favorites.py web/backend/tests/test_research_lifecycle.py web/backend/tests/test_report_api.py web/backend/tests/test_report_store.py web/backend/tests/test_flywheel_feedback.py -q --tb=short --show-capture=no
STRUCTURE_RESEARCH_TEST_PYTHON="$RUNTIME_PYTHON" PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$BROWSER_PYTHON" -m pytest -p no:cacheprovider tests/test_research_browser.py -q --tb=short --show-capture=no
```

环境沿用前述 macOS arm64／CPython 3.11.15 和只读 runtime 候选图；Linux、真实用户数据、备份取证、旧二进制混跑、完整产品／冻结／发布均未验。中断且未取得回执的一次定向测试没有计为成功；当前数字来自后续完整新运行。全部本任务进程、浏览器、socket 和句柄已由 fixture finally 关闭，未留服务或后台接续；作者完成后停写交 PMO 精确提交与同 Astra 复审。


## C0 基线（fea54a486）：固定本机任务与持久演练账本

本轮仅为 canonical direct 账户增加一条 `discover_sources → compose_report` 固定计划。两个真实 HTTP consumer 访问本任务私有 loopback fixture，来源和整理输出都是有界 `offline_probe` 笔记。计划执行结束时 execution 可为 COMPLETED，但证据仍为 INSUFFICIENT、报告状态为 notes，页面明确“尚无真实研究结论”。没有加入商业领域 family、任意 DAG／插件／执行器或常驻调度服务，也未决定匿名认领是否退出首发。

新增生产文件为 research/budget.py、transport.py、runner.py、worker.py；测试 fixture／风险用例分别在 backend/tests/research_http_fixture.py、test_research_c0.py。共享修改仅研究 schemas／store／service／authorization／projection／导出、research API 与最小页。另经 PMO 精确交接，旧 test_research_lifecycle 的 v1 迁移检查仅版本预期 2→3，原 inode／内容／HTTP 修订断言保持。auth.py、AuthStore、ReportStore、既有收费路径、CI、依赖和需求／契约文档本轮不改。

### 账本和执行边界

| 部分 | 当前实现 |
| --- | --- |
| 同物理库 | research_schema v2→v3；任务／initial attempt1／两步／事件／笔记／permit，与 FundingAccount／snapshot／price／reservation／receipt 都在原 auth.sqlite3；不搬旧数据 |
| Money | 仅 fixture USD／scale6／63 位非负整数，拒 bool／float／混币种／混 scale；乘加与两种向上取整用后端整数，预留溢出在外发前拒绝 |
| 合成额度 | 私有控制入口准备 10,000 合成单位，R1=7,000、R2=5,000；正常 actual1=4,000、actual2=3,000，最终 settled=7,000、held=0。它不是实际余额、Credits 汇率或用户新预算上限 |
| 预留／收据 | 同 BEGIN IMMEDIATE 原子检查版本、snapshot／price TTL、cap／余额保守扣除和唯一键；消费前再核。final receipt 唯一引用／摘要＋状态仅结算一次，非 final／缺金额不按零；真实异常金额先记事实再 blocked，不截断 |
| 极值异常 | 总额不能表示为合法 Money 时保留单笔实际 receipt、冻结资金账户并保持未结预留；页面显示异常，不能继续消费，不宣称硬上界已证明 |
| 不可变与幂等 | price／snapshot／billing receipt 的更新由触发器拒绝；每 step 一个 reservation／permit／dispatch，未消费、已消费、已撤销明确区分。新 key 不能绕同输入仍未对账的调用 |
| 单机执行 | 每任务复用稳定 OS mutex，锁序 task→owner→短 DB；cancel／delete 仅 owner→DB，不等待 task 门。进程退出释放 task 门，持久状态仍决定是否可继续 |
| 发送起始 | owner gate 内提交 SENDING／SENT 并消费一次 permit，实际同步 HTTPConnection.request 发送本地字节后才离开 gate；不凭创建 async task 认定发送，不证明供应端接收或扣费 |
| 网络等待 | finish 在 gate／DB 事务之外；固定 127.0.0.1、私有 fixture port、无用户 URL、重定向、proxy、key 或 SDK 重试。响应 64 KiB 上限，另有累计 5 秒 socket deadline，慢字节流也会终止 |
| 取消／恢复 | stop／version／事件及未用票在同事务保存；只有确定未发的 HELD 释放。RECONCILING 可取消，UNKNOWN 持续 held；取消后迟到收据只结账、不续步骤或正文，未取消则按原 grant／预算恢复 |
| 身份／删除 | worker 精确核 persistent execute grant_id／epoch／generation，不把 browser logout 当后台授权取消；旧 cookie 读取仍拒绝。A 删除同事务停任务，清输出／旧鉴权与输入关联，保留最小费用关联以便迟到结算 |

只有预充值／价格／snapshot 的合成 fixture 条件在本轮成立。真实供应端余额、token／推理量上界、账户独占、查账费用、自动充值／后付费和旧全项目付费 sink 仍须独立验证；本轮没有加载 provider key、请求真实模型、调用供应商余额接口或把 Credits 当 USD。生产研究入口和 worker 即使设置 C0 开关仍拒绝运行。

### HTTP 与页面

增加 tasks／cancel／reconcile／resume／events，重用严格信封、同源和持久幂等；客户端不能提供 provider URL、余额、费率、费用事实、step 或终态。reconcile 只登记请求，实际 worker 只访问免费固定 fixture receipt 端点。没有新增资金管理 HTTP／admin API，也没有 retry、refund、live connector 或任意任务指令。

默认 view 只展示当前输入修订的任务；旧任务用 opaque task_id 显式读取并标历史。新增修订不冒用旧成功，也不隐式取消旧任务。最小页提供开始、停止、核对回执、已满足条件的继续及独立刷新状态；金额显示使用后端规范文本，不在 JS 浮点计算。只展示本 task 的已知／held／未知，不公开共享账户余额、binding 或端口。

任务响应／刷新只更新任务区，不覆盖未保存草稿；迟到的旧修订 start 回执也不能回绑较新的已存问题。历史任务只读问题表单。笔记只用 textContent 渲染，HTML 字符作为文本。队列必须由实际受控进程推进，页面不承诺回合外或无人值守运行。

### 实际验证（当前作者检查点）

| 检查 | 已取得的证据 |
| --- | --- |
| 完整后端 | 424 passed／0 skipped（69.99 秒），含原 388 项和 C0 36 项；原 cookie／Unicode／原文／receipt74–75／冷 gate 反例均保留 |
| 金额与共享并发 | 两真实 worker 同 task 供应端 POST 总数仅 2；两个真实 consumer 以 7,000／5,000 争同一 10,000 额度，一方拒绝发生在外发前；重启仍同账本、跨账户预算／事件不泄露 |
| 未知与重启 | 供应端已持久收费但掉回执，原库重启不重新 POST；真实 worker 在实际发送后 exit76，新进程先转对账；取消／未取消接受同迟到回执的对照分别不恢复／正常继续 |
| 取消与 I/O 排序 | 确定 barrier 验 prepared 先取消无 POST／HELD 释放；实际发送且响应仍被外部 fixture 暂扣时 cancel 已能提交，SENT 不释放，返回后仅结账不写笔记 |
| 失败与极值 | snapshot 与 price 分别过期、金额 bool／float／负／超范围、币种／scale 错误、无金额／非 final、actual>R、聚合溢出、已知费用但正文不可恢复、execute grant 撤销均验证，不静默重试 |
| 删除与隐私 | 实际 /me/delete 后迟到 receipt 仍结算，但新研究正文／笔记／鉴权／输入关联不复活，只有最小费用关联保留；不验证真实用户删除或旧备份取证 |
| 时间和资源 | 慢字节流在实际累计 deadline 内结束，仍 UNKNOWN／held；所有测试供应端、worker、API、socket、timer、浏览器由创建者关闭 |
| 页面 | 13 passed／0 skipped（40.45 秒），原 10 浏览器＋C0 正常／取消对账与迟到 start 回执对照。375 px 截图作者查看无横向溢出，不是独立体验或真人验收 |

基本 fixture 只替代外部 HTTP 服务，provider SQLite ledger 跨 worker 重启保留。鉴权、API、任务、预算、数据库、投影和页面都实际运行；I/O 故障／退出点／barrier 不返回伪造的应用成功。合成来源或收据附带的受控笔记不代表真实检索；仅费用收据而无可恢复 note 时明确 FAILED，不用账单编正文。

当前完整后端命令在 A 完整命令后增加 web/backend/tests/test_research_c0.py。浏览器仍用 tests/test_research_browser.py，应用子进程／worker 均使用只读 runtime 候选 Python，外层 Playwright 使用既有浏览器环境；旧模型 lifespan 关闭。CLI 仅 `python -m research.worker --once --task <opaque UUID>`，最多固定两步，不是后台服务。expiry 后只拒绝新增调用，本轮不提供 live 价格／余额自动刷新或复杂退款。

C0 候选仍须 PMO 精确提交及当前 SHA 独立 Astra 审查；全 B1 正式共享导出、组合 CI、PR #247 合成、Linux、真实供应商、外部研究与数学效果、稳定 VPS 服务和用户实际使用均未验。不把演练阶段笔记、自检总数或 A 的 No findings 当作这些结果。


### C0 收尾补充边界

- 准备后绑定新的更低余额 snapshot 时，实际发送事务再核保守可用额；不因为已经 HELD 就继续发送。余额不足／过期时不显示虚假的可继续按钮，取消仍可释放已证未发的预留。
- 费用提交后、笔记保存前真实 exit77 的窗口单独覆盖。重启时已知费用保持 4,000／held0，输出仍可显式核对；fixture 能返回同 dispatch 的已存结果时恢复笔记并继续剩余步骤，原调用不重发、费用不二次计入。若只有账务而没有可恢复 note，仍明确失败，不用收据编造研究正文。
- 一次 bounded worker 只选择实际可处理的排队／执行中任务，或明确请求的对账；不会把未请求核对的 UNKNOWN 当作新调用，也不会让它阻断后来排队项。不是后台自动唤醒或调度平台。
- 最后增加的页面反例使用实际 start HTTP 提交后暂扣回执，再保存修订 2；放回旧任务回执后当前问题、草稿和修订号不倒退，旧流程仅通过显式历史链接读取，历史问题表单只读。

上述结果仍只代表当前本机合成环境。尚未放行真实 DeepSeek／其他 provider，也未完成完整旧付费调用面的 Guard。C0 补的是未来真实研究所需的机制，不是任何现象解题、公式同构或真实深度研究已经交付。


C0 最后收尾检查点：当前代码完整后端 424 passed、真实浏览器 13 passed、10 个原 Node 脚本全部 exit0；Python AST／JS 语法／diff 空白检查通过。独立浏览器脚本保持原 10 项断言并新增 3 项，既有生命周期测试只有获准的版本预期单行变化。375 px 合成截图已查看，专属可视测试目录由创建者清理。作者已停止新增功能，保留源码候选供独审；未 commit／push／部署，没有遗留任务服务或跨回合调度承诺。


## C0 完整独审页面返修（1a64f722 已复核）

独立 Astra 回收两项页面阻断，其余账务／恢复审查与独立 424 后端、13 浏览器、删除与真实发送双序对照保持。当前返修只涉及 research.js、test_research_browser.py 与本文，没有改后端、HTML、其他测试、CI 或依赖。

| 问题 | 当前修法与真实对照 |
| --- | --- |
| 任务刷新把编辑／启动基准悄悄改成其他窗口的新修订 | editBase 固定记录实际载入的 revision、input digest、research version；只有完整且明确的问题载入或保存回执才能建立新基准。observed 只记录服务器最新状态，task refresh／action 不再改表单基准。检测外窗新修订时保留标签与草稿，明确提示载入最新会替换表单 |
| 旧 cancel 回执覆盖同输入修订的新任务 | 按已知 research_version 和 task_id 拒绝较早跨任务投影；非 start 操作还绑定原 targetTask。不能用 task1 的取消回执替换已由真实新 view 显示的 task2；同 task 的合法新 task_version 仍可更新，历史链接仍只读 |

新增三项真实浏览器用例，不删除或修改原 13 函数／fixture 断言：

1. 两个真实窗口载入修订 1，B 保存修订 2，A 保留未保存草稿并刷新任务。A 保存请求仍是 expected_revision=1，后端 409，数据库仍两修订且 B 正文保留；A 明确载入修订 2 后，以 expected_revision=2 正常保存修订 3。
2. 同样两窗冲突，A 的 Run 仍发送 input_revision=1／expected_research_version=1，后端 409，不生成 task；明确载入修订 2 后才正常启动 input_revision=2。没有禁任务刷新、客户端重写基准或绕 CAS。
3. task1 的实际取消已在后端提交但回执暂扣；另一合法 API 启动同 revision 的 task2，页面实际重读并确认 task2 queued 后才放回旧回执。页面仍显示 task2 queued、停止按钮可用，点击后真实取消对象是 task2。

第三项首次测试只等“queued”文字，无法区分仍是旧 task1 的画面；该次失败未计关闭。修正测试 barrier 为真实读取响应的 task_id 等于 task2，且页面读取完成后再放旧回执，保留原反例目标，不返回伪造应用数据。

当前作者验证：**16 passed／0 skipped 浏览器（48.38 秒）**，包括原 13 项与新增 3 项；10 个既有 Node 脚本全部 exit0，JS 语法与 diff 空白通过。原函数 AST 比对和精确三文件范围另核。后端源码保持 fea54a486，按本轮授权沿用其独立 424 项与账务证据，不机械重复后端组。

所有外部边界仍是固定本机 HTTP fixture，没有真实模型、费用、SMTP、SSH、网络目标、trace 或新 session。测试自建浏览器、context、API／worker 与 socket 由原 fixture finally 收尾；当前停写交 PMO 新 SHA 和同 Astra 受影响复核，未放行共享冻结、D1 接线或发布。


## D1 发送者生命周期 P1（当前未提交差异）

原实证是在完全本机固定夹具中，父持 owner gate 启动 source child，随后父被 SIGKILL；父 finally／12 秒监督失效，gate 提前释放，而无独立期限的孤儿 child 仍能在取消已提交后发送 GET。daemon 标记与记录 UNKNOWN 不能关闭这个边界。本次只修发送者生存／门／期限，没有推进 D1 网络接线、扩大源站或改变解析／许可／证据 repository。

当前协议是两阶段受控转交：

1. 已取得的 owner gate yield 公共 OwnerGateLease，旧 with 无 as 调用兼容。capability 只由 gate 创建，检查 active、creator PID 与原 fstat，不返回 raw FD，也禁止 pickle。
2. spawn child 不继承 lease。child 先设 SIGALRM=SIG_DFL、解除该信号继承屏蔽，再按同一 monotonic deadline 安装 ITIMER_REAL；只有安装后才返回 ARMED。默认内核终止动作不是可能被阻塞 C／DNS 推迟的 Python handler。
3. 父收到 ARMED 后再次核授权／期限，通过公开 send_handle 在 Unix socket 转交原 open-file-description 的 flock；child recv_handle 后校验 dev／inode／uid／mode／nlink 才调用真实发送 worker。没有预建 DupFd 或 resource_sharer 缓存锁副本。
4. 父在转交前死亡，child 没有发送 capability；父在转交后死亡，接收队列或 child 仍保同 flock，取消／删除不能假称提交。child 的独立内核期限退出后才释放门；只 close，绝不 LOCK_UN 提前解开共享锁。

PinnedPublicTransport.get 新增必需 owner_lease；CrossrefPlosChain 只转交 request_gate 实际 yield 的有效 lease。缺 lease、伪造／过期 lease、缺 POSIX 信号／FD 能力时 fail closed，没有 daemon／pid 轮询／全局 watchdog 降级。实际发送目标与原公网 DNS／pinning／TLS／重定向／读取上限策略不变；本次验证只有固定本机网络 fixture，没有实际公网请求。

### 实际检查点

- 原 source／evidence 入口 51 项及 43 subtests；原 77 个 unittest assert 调用 AST 保持，只有真实合成 OS gate 和新签名适配。
- 新 lifetime 7 项：parent SIGKILL 后的 ARM 前、ARMED 但转交前、真实 SCM_RIGHTS 已入队未 recv、已收到 lease 且卡发送前四切点；另加父屏蔽 SIGALRM 的继承对照、正常本机响应、无效 lease 拒绝。
- 发送者／队列持门时，真实同 flock 取消尝试返回 STORE_BUSY；独立 12 秒后门可取，超时后释放原发送 barrier 仍为零 GET。转交前取消可先提交，也不留下可晚发的 sender。每个独立 parent 的私有 resource_tracker 必须实际观察到一个，随后确认退出，不能用空列表算通过。
- 旧 gate／跨进程删除保存／进程退出恢复关键组 17 passed，旧无 as 使用与冷 gate／tamper 行为保持。

队列切点测试最初误以为 handoff 返回即是入队；Darwin send_handle 会等接收 ACK，因此 child 故意卡 recv 时该 marker 不到。测试改在公开 socket.sendmsg 实际成功（SCM_RIGHTS 已入内核队列）后取证，没有假设或伪造传递。曾把两个同名 tests 包混收集造成 ImportError，最终按各自原入口运行，未改依赖或收集规则放宽它。

复现分开执行：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider tests/test_research_sources.py tests/test_research_evidence.py -q --tb=short --show-capture=no
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_source_lifetime.py -q --tb=short --show-capture=no
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=web/backend "$RUNTIME_PYTHON" -m pytest -p no:cacheprovider web/backend/tests/test_research_lifecycle.py web/backend/tests/test_research_persistence.py -k 'gate or two_real_api_processes or real_process_crash' -q --tb=short --show-capture=no
```

所有 SIGKILL／signal／socket 都归属测试自己创建的独立本机 session/group；不终止共享 Python／用户程序。正常、异常、超时、授权晚回和原 source 对照保留。本次仅上述 source policy／adapter 转交、authorization capability、source 测试／新 lifetime 测试与实施记录；其他 D1 解析／许可／schema／repository、C0 DB／预算／runner／API／页、CI／依赖均未改变。Linux／VPS／真实公网、完整接线与共享冻结仍未验；作者结果不能代当前 SHA 独立复审。

## D1 固定来源子链接线（2026-10-17，待独审候选）

当前工作区为 B1 专用工作树，分支 `codex/structure-d1-integration-20261017`，基线 `210962009680e626f156ac85a5c52a4ca551d3a6`。本节是其未提交接线差异的实施记录，不能把前文生命周期修复的独审结论扩大为本轮接线已经独审通过。提交、合并及独审回收由 PMO 负责；本作者不 commit、push 或部署。

### 已接通的最小流程

1. 来源预览只读取当前账户、已保存问题和版本，返回查询计划 DTO，不创建 task、approval、evidence、额度或网络请求。
2. 用户明确确认查询后，同一 auth SQLite 持久保存批准，绑定账户 incarnation、epoch、问题修订与 digest、查询、计划摘要、策略、模式和四次上限。启动在同一事务中重新核对这些绑定，创建执行 grant、task、三个固定步骤、正式 AnalysisPlan，再消费批准并保存幂等结果。旧 key 返回原 task 当前投影，不重新启动。
3. worker 执行 discover → 至多三个已获许可的 PLOS 正文 → 本地整理 notes。每次请求都在实际 owner lease 内先用短事务消耗持久额度，再离开数据库事务调用原受审 PinnedPublicTransport。没有 C0 虚构资金账户、模型调用、行情序列或统计运算。
4. 原 EvidenceRepository 负责原文／提取摘要、来源许可、Unicode 字符偏移短摘录、假设级 claim 和 INSUFFICIENT report。中断后不重建 adapter 私有状态，不读取 repository 私有缓存接口，也不自动重取旧正文。
5. API 只开放 `sources / excerpts / claims / reports` 四种显式字段投影，每条仍经账户、研究、task、修订和许可检查。每页最多 20 条，序列化正文留在 512 KiB 之内；游标绑定账户、研究、输入、task、kind 及研究／task 版本。原文、完整 extracted、discovery 和内部 plan/execution 不走该公共接口。
6. 页面保留原 editBase 与 observed 高水位机制。来源预览、确认启动和刷新不会悄悄采用其他窗口的新问题。显示免费读取次数与模式，保留“未运行模型、行情或统计”的说明。启动回执丢失后，重载只重放原批准／启动体和原幂等 key，核对原流程。

### 中断闭合与额度

固定执行器在整个来源会话内持 task mutex；发送者沿用已受审的同 owner open-file-description lease 与独立内核期限。本轮没有改动 lease、source transport、解析器、许可规则或 evidence schema/repository。

恢复必须同时持有 task mutex，并重新取得同 inode 的独占 owner gate；持久记录的 dev、inode、uid、mode、nlink 必须与实际 capability 一致。这排除了旧父执行者和仍可能发送的子进程／SCM_RIGHTS 队列。随后退休旧 write_epoch 和步骤 CAS，保存版本化 closure proof/ref。旧请求仍为 UNKNOWN，原始 started/ended 时间不变；旧 task 结束为 FAILED 或保留 CANCELLED／ACCESS_REVOKED。单靠时间、PID 不存在或文字状态不能闭合执行。

新观察必须重新预览、明确批准并建立新 task、dispatch 和 acquiredAt；同一归一化操作链累计最多四次，UNKNOWN 不退款、不重置，新 dispatch 关联匹配的 prior_dispatch。这个规则只用于固定免费 GET，不放宽原 Money、paid UNKNOWN 或 receipt 机制。

### 数据迁移与清理

schema v4 只扩展 tasks 的策略／模式及 steps 的固定第三步，并新增来源批准、额度、run、request 与 evidence 表。专用连接在 BEGIN 前关闭并读回外键设置，在独立 BEGIN IMMEDIATE 内复制／替换受支持的旧表；拒绝未知表定义、附属索引或 trigger 漂移，提交前要求全库 foreign_key_check 为空。任一替换或 commit 故障整体回滚；finally 恢复并读回 FK ON 后关闭连接。应用常规事务始终 FK ON。

旧账务记录、ID、receipt、引用关系与锁 inode 保留。原 lifecycle 测试唯一获准变化是版本预期 `3 → 4`，其他正文和断言逐字保持。账户删除在清空 task 绑定前，以真实 pending deletion job、账户 generation／gate、数据库绑定、研究 owner 及 deleting 生命周期授权 repository.purge；随后清理批准、缓存正文和查询指纹，不删除费用凭据。

### 作者验证与边界

| 范围 | 实际结果 |
| --- | --- |
| 原完整后端 | 424 项通过；与当时新增 33 项合跑为 457 passed／0 skipped |
| 新 D1 集成组 | 最终 34 passed／0 skipped：真实 HTTP/auth/SQLite、一个与三个许可来源、预览零副作用、严格批准／幂等、不可见内部记录、未知许可／非法 metadata／超大正文、取消前零 GET、真实账户删除、同链累计四次与 prior_dispatch |
| 迁移 | 真实 v3 保存与已结算 C0 账务／receipt 数据；11 个替换与 commit 故障边界逐一回滚，恢复后原记录与锁 inode 一致 |
| SIGKILL | 实际独立父进程被杀后，孤儿 sender 仍持门，来源 GET 为零；独立内核期限后取得新的双门证明，旧 UNKNOWN 原时间保留，新显式批准才发出新请求 |
| 浏览器 | 18 passed／0 skipped，包含原 16 项、390 px 来源完整流程及已提交启动回执丢失后的重载核对；旧 13 个测试函数 AST 保持不变，参数化后为 16 项 |
| 页面与静态检查 | 现有 11 个 Node 脚本全部 exit0；JS 语法、Python AST、diff 空白与精确保护文件字节核对通过 |

新增丢回执浏览器用例初次使用表达式形式的等待，被实际 CSP 拒绝；改为原生 locator 文本断言后才计通过，没有放宽 CSP 或改写产品响应。最后补强删除 owner 检查后，仅补跑受影响的真实删除用例。

原 C0 budget.py、收费 transport.py、authorization.py，以及 D1 七个受审文件与基线逐字相同。新增路径严格限于 source_integration.py、source_workflow.py、test_research_d1_integration.py、source_http_fixture.py；没有改依赖、CI、D2、旧 AuthStore 或旧 report 实现。

以上均为本机合成来源，测试自建服务、浏览器、worker 和 SIGKILL 进程组均由各自 finally 收尾。未访问公网、SMTP、SSH、真实模型或付费接口，没有 trace、新 session 或后台运行承诺。本轮交付只解决固定方法来源的最小子链；完整 U1、跨域同构解题、公式发现、模型深研、Linux／VPS 与对外稳定服务仍须后续阶段验收。当前候选交 PMO/Astra 独审，不能据此放行发布。

## Source 超时分类直接修因（2026-10-17）

D1 接线由 PMO 固定为 `9b543d9a42984b7d8c481e9372a909adf3902da7` 后，同依赖组合验证暴露原 0.3 秒超时用例的间歇失败。作者保持原期限与全部原断言，诊断运行在第 19 次实际复现：slow_worker 的 IPC EOF 被父进程读到时，绝对 deadline 已过 1.953 毫秒，子进程 exitcode 为 `-14`（SIGALRM）；父进程却在 EOF 异常分支直接返回“source worker result unavailable”，跳过了正常收包后的期限检查。安全期限已实际生效，错误发生在父进程对结果的分类。

本次只改 `PinnedPublicTransport.get` 的两个失败出口：在 EOF／读取失败或已观察到子进程退出时，若已过原绝对 deadline，或已取得的退出状态为 SIGALRM，则准确返回 hard deadline；其余提前发生的 EOF、非零退出或 SIGTERM 保持原 unavailable／无结果错误。没有新增等待或调整重试，没有把全部 EOF 都归为超时。child 的内核期限、owner lease、ARM／FD 转交、DNS／TLS、许可与输入策略均未修改。

新增一个确定性监督分支测试，以 EOF 和无消息退出两种路径分别覆盖：已过 deadline 但 exitcode 尚未观察到、期限前已观察 SIGALRM、期限前普通失败、期限前状态未知、期限前 SIGTERM，共十个反例／对照。真实原 0.3 秒用例保留，并额外连续执行 25 次全部通过；该重复用于已复现竞态的返修核验，不替代确定性对照。

实际验证：原 source/evidence 组加新测试为 **52 passed、53 subtests passed**；原生命周期组 **7 passed**；D1 实际 HTTP/auth/SQLite/worker 组 **34 passed**。原 source 35 个方法的 AST 保持不变；source_policy 除 get 外全部函数／方法 AST 保持不变。D1-WIRE 的 DB、API、页面及其他文件按 PMO 冻结，无 commit／push／公网／模型／费用／SSH／trace／CI。作者停止写入，交 PMO 形成新 SHA 后统一独审；本节不是独立审查或发布放行。

## D1 独审五项返修（2026-10-17，基线 05a51d46）

完整独审在 `05a51d46a4d911d9e32f28cec145387bdcb87d49` 回收两项 P1 和三项 P2。原 458 后端、18 浏览器、52 source 与 7 lifetime 通过不能抵消这些真实反例。本轮仅修改 source_integration、source_workflow、research.js、对应 D1／浏览器测试与本文，未混入 Provider 或 D2。

| 独审问题 | 返修与直接证据 |
| --- | --- |
| 未闭合 SENDING 被遗漏 | start 与 request_gate 统一检查 SENDING／UNKNOWN 的 execution_closed。新增真实独立父进程 SIGKILL → sender 内核期限退出 → 正常账户 API cancel 对照；旧行仍 SENDING、closed=0、closure_ref=NULL 时，新批准启动返回 409 且零 GET。旧 task 经持 task mutex 和 fresh owner gate 受控闭合后，旧行变 UNKNOWN／closed=1，原时间不变，新显式批准才产生两个正常 GET |
| 未外发问题摘要改变可重置额度 | outbound fingerprint 只绑定归一化外发 query 和固定方法源操作族；完整 problem digest 仍绑定批准／task，不能拿旧批准执行新问题。额度／未闭合检查还按原批准 query 归组历史候选链，避免算法变更遗落旧链。实际完成四次 GET 后，仅修改本地 summary 再批准仍返回 429、GET 数保持四；两条旧 problem-fingerprint 链的历史持久形状也合计四次并拒绝重置 |
| 公共 DTO 混用内部 snapshot／execution 引用 | SourceRecord.id=source_id、revision=source_revision，按既有来源字段映射 content_digest、extracted_text_digest、accessed_at、许可说明与 execution_mode。Excerpt 使用 source_id/source_revision/text_digest；Report 使用可解析的 SourceVersion 与 claim_ids，不再公开 snapshot_id/snapshot_refs/execution_refs。SourceVersion 含内容 digest／access；报告创建时间取同一 compose 事务实际产生的 terminal 发布事件，不编造时间。真实 API 逐条核验来源版本、内容 digest 和 claim 引用，公共 JSON 不含内部 snapshot id |
| 新 task／input 留下旧来源卡 | 接受新研究／输入／task scope 时立即清空来源卡并退休旧读取 generation。全量问题重读也退休在途读取；每次收包、解析正文和渲染前核 scope，旧响应及旧错误不能清除／覆盖新 scope。浏览器验证同输入新 task 排队时旧四卡立即消失，空 records 保持空；另暂扣旧真实非空 records 响应，保存新修订后再放回，旧卡不会复活，表单保持新问题 |
| closed UNKNOWN 被投影成消失 | 受控 source_quota 同时提供 unknown_count／unknown_closed／unknown_unclosed；source_observations 给出原任务／修订、原 started/ended、闭合状态与 result_restored=false，不开放内部执行控制对象。新观测完成后，旧 UNKNOWN 摘要和原时间仍逐字相同。页面同时呈现“执行已闭合，原结果仍未知”和原观测时间，不声称恢复旧结果 |

作者实测：原完整后端 **424 passed**；D1 组从原 34 项增加五个反例／兼容对照，为 **39 passed**；真实浏览器原 18 项加三个反例，为 **21 passed**，最终脚本补强后重跑受影响五项均通过；11 个现有 Node 脚本全部 exit0。旧浏览器 15 个测试函数 AST 不变（参数化后原 18 项）；旧 D1 12 个函数 AST 仅有一处必要公共字段适配：报告 `len(snapshot_refs)==3` 改为 `len(source_revisions)==3`，保留同一三来源断言。没有删除、跳过或放宽其他旧断言。

source_policy、authorization／lease、budget、收费 transport、schema 迁移、旧 service/API、原 adapter、evidence schema/repository 均与 05a 基线字节相同；沿用该完整独审的 52 source／7 lifetime 证据，并由本轮真实 D1 正常链及两个 SIGKILL 情形复核接线。所有测试仅使用自建本机来源，资源由 finally 关闭；无公网、模型、费用、SMTP、SSH、trace、CI、新 session、commit 或 push。本轮候选停写后交 PMO 固定 SHA，再交原 Astra 复审；作者验证不替代独立放行。

## 37f4c062 复审剩余两项 P2（2026-10-17）

原审查者确认前轮两个 P1 反例已经关闭，但发现兼容旧链的关联和公共白名单仍有缺口。PMO 收到 Product 已关闭全部验收资源、源码零改的确认后，授权本轮单写返修。预算只读短卡通过消息回收，未混入 v5 schema、Provider、D2 或资金实现。

1. **原 dispatch 关联改用整个兼容链集合。** 额度和未闭合检查已经按原批准 query 归组，但 prior_dispatch 仍只查新 run 选中的一条链。本轮在同一受控事务中，用同一链集合、相同规范步骤／目标，选择已核闭合的 UNKNOWN；以 started_at、ordinal、dispatch_id 排序消除不确定选择。保留原 UNKNOWN、闭合证明及原时间，新观测仍是独立 dispatch／取得时间，不恢复旧请求结果。
2. **公共 sources 排除 provider_ref。** 虽然该值此前是公开 DOI，现行契约仍明确禁止公开这个字段；本轮删除它，页面链接文字和目标均使用已经获准的 canonical_url。新增严格字段集合相等测试，不能只靠“若干敏感字段没出现”漏过新增属性。

新增真实 HTTP/auth/SQLite 反例先产生一条成功 discovery 与另一条 closed UNKNOWN，恢复受支持的旧候选两链持久形状，刻意让成功链先排序、UNKNOWN 位于非选中链。额度尚余两次时，新 run 正常取得来源并结束，累计四次 GET；prior_dispatch 必须指向另一链的原 UNKNOWN，原行逐字段保持不变。另新增真实浏览器测试，核公共响应没有 provider_ref，链接仍用规范公开 URL 正常展示。原 D1／浏览器全部函数和断言 AST 保持，未删除或放宽旧测试。

作者验证：D1 完整组 **41 passed／0 skipped（49.19 秒）**；完整浏览器 **22 passed／0 skipped（72.44 秒）**；现有 **11 个 Node 脚本全部 exit0**。Python AST、JS 语法、精确保护文件字节及 diff 空白检查通过。实际业务源码仅 workflow 的 prior 查询、integration 的一项公共字段删除、JS 的一项链接文字修改；其余差异只是两项 D1 测试、一项浏览器测试和本文。未改费用、权限、迁移或安全发送机制；没有真实公网／模型／费用／SSH／trace／CI、提交或推送，资源按原 finally 收尾。本轮仍须 PMO 固定新 SHA 后交原 Astra 复审。
