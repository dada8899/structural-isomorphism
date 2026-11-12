# Linux 两页性能诊断采证

日期：2026-10-17。任务：STRUCTURE-PERF-LINUX-DIAG attempt2，Issue #255。代码起点为`847077a2706a748b37a21bfb1f613d8b86fa451a`，分支`ops/perf-diagnostics-20261016`。只新增本说明、诊断脚本及其单元测试；不改原测量、预算、fixture、业务、依赖或CI。B0 owner另行接线，经脚本/来源独审后由PMO发布唯一marker提交。

**诊断是NOT_GATE采证，不是性能门禁。** 已知PR run38924999925中analyze三轮230/220/233ms、papers222/213/246ms是真实新失败依据，另一次push绿色不抵消。旧Mac两次trace已用完并保持冻结；本任务只授权Linux固定两页各一次，不在本机试跑真实trace，也不因采证失败或结果红绿再采。

## 1 唯一绑定

入口只接受本repo PR253的`synchronize`，head/base repo均为`dada8899/structural-isomorphism`，`GITHUB_RUN_ATTEMPT=1`。push、opened、reopened、其他PR、fork、普通后续提交和重跑不能开始采证。

本次固定subject为`ci: capture structure-perf-linux-r2-20261016`。其中20261016是已批准nonce的一部分，不随本文日期变化。由PMO在来源与脚本独审后只发布一次，不强推、不重放或再发marker“采到绿”。执行时读取本地PR head commit对象的完整subject，不用PR标题/body或Shell插值推断授权。

现有checkout仅需由B0 owner将fetch-depth改为2，让PR merge checkout可读其head对象；脚本不执行fetch、不借新增token补对象。检查实际HEAD等于GITHUB_SHA，分别保留checkout与PR head身份。默认PR合并测试SHA不等于head是正常情况；两者的受审输入必须相同，不能伪造GITHUB_SHA或把head绿灯写成merge结果。

脚本固定54项SHA256，来自847中的两页HTML、其脚本、共通CSS/字体/i18n/目录数据、原两份审计/预算及后端报告fixture依赖。工作文件、PR head与checkout Git对象分别核对；诊断脚本本身也要与PR head/checkout字节一致。诊断/CI新增文件不放入847旧输入摘要，避免自身hash循环，但必须完成独立代码审阅。任一输入变化即拒绝，不提供CLI覆盖pin或本地强制采证开关。

实际run_id在运行时记录；不预猜未来ID、不使用repo变量平台或额外凭据。单次marker发布、事件限定和PMO回收负责跨run不重放；输出目录的attempt/per-page标记只提供同目录独占，不宣称是跨runner的分布式exactly-once锁。

## 2 原grade与启动前置

按当前job原8页×2viewport×3runs的完整artifact校验schema、engine、profile、窗口、页面路径、raw run数量及原六项source摘要，保留其原字节hash。原step outcome为success/failure都允许，与artifact的passed/failed必须一致；不得以“这轮仍失败”为采证条件，避免选择偏差。原step未运行、原结果不完整、源码不符时记录incomplete，不启动浏览器/trace。

安装前置为实际Linux、Python3.11、Playwright1.59.0、Pydantic2.7.4及已安装可执行Chromium；major147继续由原audit验证。没有pip/npm下载、浏览器自动安装或Mac override。依赖缺失是incomplete，不尝试安装后重采。

`--base`必须是原artifact中的`http://127.0.0.1:<port>/`，保留末尾斜线，不允许localhost替代、远端、认证信息、query或fragment。静态服务由原job提供，脚本只读借用：禁代理、拒重定向、各请求5秒且无重试，核两页HTML及所有受pin静态资源的HTTP实际字节与本地/批准hash相同。不调用任何真实API、模型、SMTP或SSH，也不停止该借用服务。

原artifact未携带run_id，所以脚本不能独立证明其来自当前step：B0接线必须使用该job原step新生成的固定文件，顺序在其结束后，不能下载/复用旧结果代替本轮。脚本校验step outcome及原文件hash，运行前后只读复核，不重写、修复或替换它；并发外部改写会使诊断incomplete，不把旧字节覆盖回去。

## 3 CLI及允许变量

唯一采证命令：

```sh
python scripts/beta_perf_diagnostics.py \
  --grade-artifact /tmp/beta-perf-audit.json \
  --grade-outcome success \
  --base http://127.0.0.1:4173/ \
  --out "$RUNNER_TEMP/structure-perf-linux-r2-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
```

grade-outcome由原step实际outcome提供，可为success/failure/skipped/cancelled；只有前两者能采，后两者仅得到incomplete。示例success不是强制改写结果，真实failure同样采。没有pages/runs/viewport/window/budget/limit/force-local可变参数；固定analyze/mobile、papers/mobile，各调用原audit_one一次。

脚本仅选择读取这些环境键：GITHUB_EVENT_NAME、GITHUB_EVENT_PATH、GITHUB_REPOSITORY、GITHUB_RUN_ID、GITHUB_RUN_ATTEMPT、GITHUB_SHA、RUNNER_OS、RUNNER_ARCH。不读或输出完整env、真实secret、账号配置或进程命令行；PR body只在事件JSON输入中被解析，不进入输出。RUNNER_TEMP仅由调用者展开为out参数。运行负载仅采OS/kernel/架构、CPU数/loadavg、有限cgroup数值，以及`comm`聚合的Chrome/Node数量，不能由matrix多job推断同机竞争。

stdout为闭合JSON：classification=NOT_GATE，status=not_scheduled/incomplete/complete。预检拒绝在stdout记录incomplete且不建capture资源；普通非目标事件/subject为not_scheduled，不伪造成功诊断。退出0表示采证完成或不属于本次调度，退出2表示incomplete，**都不是性能grade pass**。B0不得因此把原audit失败改成成功或忽略原退出码。

## 4 原测量和采证时序

原audit_one、PAGES、_analyze_fixture、page_setup_factory、page_validator、post_interaction_validator、ready与interaction selector、CPU4倍、慢4G、可信pointer/click及FCP→FCP+5000ms全部复用。fixture路由拒绝未登记API与外站，analyze是真实报告UI的确定响应，papers是真实20项目录及筛选交互；不是伪造HTML或空页面。两页顺序执行，鲜浏览器/context，不增加暖场、随机重复或并行采样。

page_setup在原fixture设置后加CDP Profiler及timeline；请求devtools.timeline、v8、user_timing、invalidationTracking及stack类别。运行时先查询所需invalidation类别，缺失则明确incomplete，不静默声称捕获。类别可用仍不保证每个Layout都有可归因栈，真正归因需Linux结果回收后判断。

原始指标已经计算后，run_evidence_sink的cleanup=pending回调才保存longTasks、LoAF、事件、资源/导航时序，停止CPU profile并结束Trace。Tracing.tracingComplete是异步事件：用`page.wait_for_timeout`泵原Playwright dispatcher等待，不用threading.Event.wait阻塞它；10秒deadline同时约束事件等待和IO流读取检查。CDP同步RPC若本身卡死不能靠轮询精确抢占，必须有外层5分钟step与信号清理，不能虚称任意故障都能10秒杀净。

pending与final双回调只捕一次；同回调重放同内容不再写/停/捕，不同内容重放标冲突。回调异常仍stop profiler/trace、关闭IO stream并detach；原audit关闭其browser，脚本对自己取得的尚连接browser提供finally兜底。全局driver/context由自己的with生命周期关闭，不碰原静态服务。SIGTERM/SIGINT转为清理中断，不继续第二页；SIGKILL不能保证finally，已有started标记和不完整证据不能被重放覆盖。

## 5 输出和容量

out必须是checkout外的绝对、非symlink规范目录，owner为当前执行用户、mode700。attempt.started.json独占创建，已有文件拒绝重入；每页started.json也独占。所有文件以O_EXCL/0600创建，不覆盖既有输出。

每页64MiB是**所有文件累计**，包括started、raw longtasks/资源、CPU profile、timeline、runner前后、pending/final audit及summary，不是仅timeline文件。bulk保留最多4KiB给短控制/失败摘要，总累计仍≤64MiB；到限保留自己的partial文件、标incomplete、不清掉痕迹或再采。全局少量身份/source摘要另存，不含原用户数据或凭据。

输出结构：attempt.started.json、diagnostic.json；analyze/与papers/各有started、audit.pending/audit.final、runner.before/runner.after、raw、cpu、timeline和summary。提前中断时部分文件允许缺失；diagnostic记录requested/started pages，不把缺失当空任务成功。complete仅表示原测量及传输/cleanup完成，不是源码根因已证明或性能达标。trace开销明确标记，不能拿其分数替代原无Profiler门禁。

## 6 B0唯一owner的最小接线参考

以下仅是需B0合成与审查的模板，不表示本任务已修改workflow。沿用原job、安装、静态服务、原8页3轮audit与artifact上传；为原audit加稳定step id、checkout depth2，并在原audit之后/原服务cleanup之前插入一步。不要新job、改原budget/测量、复制fixture或为采证放宽原检查。

```yaml
# 原checkout仅增加：with: {fetch-depth: 2}
# 原audit仅增加：id: beta_perf_gate，run命令不变
- name: NOT_GATE one marked Linux diagnostic pair
  if: >-
    ${{ always() && github.repository == 'dada8899/structural-isomorphism'
        && github.event_name == 'pull_request'
        && github.event.action == 'synchronize'
        && github.event.pull_request.number == 253
        && github.event.pull_request.head.repo.full_name == github.repository
        && github.run_attempt == '1' }}
  timeout-minutes: 5
  env:
    ORIGINAL_GRADE_OUTCOME: ${{ steps.beta_perf_gate.outcome }}
  run: >-
    python scripts/beta_perf_diagnostics.py
    --grade-artifact /tmp/beta-perf-audit.json
    --grade-outcome "$ORIGINAL_GRADE_OUTCOME"
    --base http://127.0.0.1:4173/
    --out "$RUNNER_TEMP/structure-perf-linux-r2-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
```

模板不在if中判断原grade红绿；subject/source由脚本在browser前拒绝。普通后续commit将not_scheduled；源/脚本独审完成后PMO单次marker才开启本次。原step失败继续失败；若诊断step失败，分列采证基础设施失败，不能修改原grade。新输出由B0加到既有always上传范围；借用服务仍由原always cleanup负责。未调度/预检失败可能没有输出目录，应保留stdout原因而不捏造artifact。

## 7 已验证和未验证

本机只运行单元/模拟反例及原审计回归，没有新Mac或Linux真实trace、外部API、模型或费用。模拟覆盖事件/nonce/source/浅克隆对象拒绝、红绿均采、原step未运行、原文件不被改写、双callback及重入、异步事件只有dispatcher泵后到达、10秒超时、累计容量、IO异常/partial setup、SIGINT式中断的owned资源关闭、缺invalidation类别和secret canary不进输出。

本机新增模拟与原有审计回归合跑104 passed（1条既有Pydantic namespace warning），无skip。本机单元环境为Python3.11.15、pytest9.1.1、Pydantic2.6.1；这不是live前置验证，真实采证仍严格检查2.7.4及Linux，不能据单元通过冒充同环境运行。

实际Linux类别支持、CI真实run绑定、负载、同步Layout和两页归因尚未验证。脚本及接线需独立审查，B0 owner合成并核当前SHA的必要CI后，PMO才单次发布marker。来源摘要和artifact本身不能证明workflow的外部命令参数未变；B0必须独立核原8页3runs及原预算命令未改。不能用上述模拟结果宣称Linux采证已执行、性能已修复、共享门禁已过或服务可发布。
