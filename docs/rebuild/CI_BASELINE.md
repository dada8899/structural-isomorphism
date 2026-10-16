# Structure 非生产集成线 CI Bootstrap

日期：2026-10-16。任务：STRUCTURE-CI-BOOTSTRAP，attempt 1，Issue #250，父任务 #248。初始源基线为 `be3a3c6b5de19f2508335519d01240077bb591ec`；提交目标为 `integration/structure-rebuild-v1`，不是 main。初次作者交付后，PMO 已提交并推送候选 `995e5c22d08279773b04b07b1dc437e09a753956`，形成草稿 PR #253。本次在该候选上返修真实 CI 失败，作者不自行提交或推送。

## 结果与范围

**非生产集成线接现有真实检查，生产入口先检查 ref 再进入有副作用的任务。** main 仍为生产代码权威；集成线是受控候选。共享契约尚未实现或冻结，B0 不能代表三项产品能力、真实计费、恢复或上线验收。

本轮修改 12 份既有 workflow，新增 `product-ci.yml`，扩展门禁 manifest，新增离线合同测试，并仅适配既有 `test_release_gate_manifest_binds_internal_and_external_checks` 函数。未改业务源码、依赖锁、部署脚本、服务器、DNS、账户数据、主分支保护或私有配置。

## 精确触发范围

| Workflow | push 分支 | PR base | 其他边界 |
| --- | --- | --- | --- |
| CI、sanity、types-sync、beta-perf、coverage、product-ci | main、integration/structure-rebuild-v1、bootstrap/structure-ci-20261016 | main、integration/structure-rebuild-v1 | 必要检查不加 path 过滤，避免无关文件 PR 缺检查；sanity 原有 dispatch 保留但不作为 PR 门禁替代 |
| ci-packages、runtime-smoke | 同上 | 同上 | 原有 path 过滤、schedule／dispatch 与执行内容保留；并非每次无关改动都运行其可选作业 |
| Beta、Phase、Docs 发布 | 仍仅 main，原 path 过滤不变 | 不新增 PR 发布事件 | 新增独立 admission job，main push／main dispatch 才允许后续 job |
| release-packages、publish-pypi | 原有 release tag 过滤不变 | 不新增 | main dispatch 或原允许 tag 事件通过 ref 检查，随后以只读 Git ancestry 核 release SHA 可从 origin/main 到达 |

没有采用全分支通配符，也没有扩大生产自动发布范围。CI 的可选 live e2e 改为 main push，或 base 为 main 且具有明确 `run-e2e` 标签的 PR；集成 base PR 即使被加同名标签也不能触发旧生产探测。原八个必要依赖没有因此减少，后续公网任务验收仍需独立执行。

## 真实门禁与提交身份

`release-gate` 原八个依赖及其 job 内容保持不变：retrieval-eval-contract、site-docs-contract、phase-python-contract、browser-product-contract、browser-beta-surface-contract、backend、packages、frontend。新合同以受审源的 job 语义摘要验证没有删除步骤、软化失败或加条件跳过。

manifest 保留 `release-gate`、`sanity`、`check`、`beta-perf-audit`，另加 `product`。原先的公开控制测试将 manifest 完整字典和 `branches: [main]` 精确固定；PMO 已批准只改这一函数，将预期扩为上述五项及精确分支列表，保留原八依赖、hard-job、聚合失败和逐项检查断言。其他函数及阈值、skip／xfail 未改，AST 对照已验证。

`product` 是硬作业：在 Python 3.11 上安装精确版本 pytest／PyYAML，执行新的 B0 风险合同，未使用空脚本、条件跳过或 continue-on-error。它当前只证明 CI 接线与生产拒绝机制；B1 必须在此基础上加入正式 API、持久化、状态投影、预算和撤权等消费者，不能把 B0 合同当作业务实现验收。

product 输出 event、workflow ref／SHA、run ID／attempt、event SHA、实际 checkout SHA、PR head／base SHA，并要求 checkout 与当前 event SHA 一致。PR 的 merge checkout 不冒充 head；本地临时 Git 仓库实测合法身份输出和错误 checkout 拒绝。真实 Actions 的 run／attempt 仍待 PMO 推送后核实。

## 生产拒绝与合法对照

各生产 workflow 的首个 admission step 只有固定 Bash case 与 GitHub event/ref 环境变量，不 checkout、不读 secrets、不运行源文件。Beta／Phase／Docs 拒绝任意非 main dispatch；所有后续 job 经 needs 链依赖成功 admission，没有 job 级 always 条件绕过。原 release-contracts、build 和发布步骤未删除。

包发布先检查 main dispatch 或允许 tag 格式，再以只读、完整 history checkout 执行 `git merge-base --is-ancestor SOURCE_SHA refs/remotes/origin/main`。tag 格式本身不证明源属于生产；临时 Git 仓库覆盖 main 历史提交合法对照、未合并集成提交和非法 SHA 拒绝。既有合法 tag 格式及后续发布步骤保留。

这些拒绝条件作用于本轮修订的 workflow 版本，不会追溯修改旧 refs 中的 workflow。分支保护、发布环境和批准执行者仍须按最终源核实；本轮没有发真实 dispatch／tag、触达生产或证明 GitHub 已替集成线强制执行五项检查。

## 本地验证

| 检查 | 结果与证据边界 |
| --- | --- |
| 新 B0 风险合同 | 71 passed；执行实际 admission shell 与 ancestry／身份脚本，含非 main dispatch、注入字符串、未合并 tag 源、生产依赖绕过及硬 job 缺失／软化反例 |
| 既有公开控制合同 | 103 passed；合法扩展必要检查与精确触发后，原 hard-job、聚合、输入和其他公开边界保持 |
| 上述两组同进程回归 | 174 passed；不是产品运行或研究效果证据 |
| 部署 workflow 相关回归 | 5 passed，129 deselected；只覆盖该选择范围，不冒充部署完整套件 |
| 静态核对 | 修改 YAML／JSON 可解析，两个测试文件可编译，所有改动 workflow 的 Bash run block 通过 `bash -n`，`git diff --check` 通过 |
| 修改范围核对 | 既有测试 AST 仅获准单函数变化；原八 CI 依赖及聚合 job 语义摘要未变 |

本机未运行 actionlint，也未执行 GitHub 的表达式引擎；可选 e2e 条件使用有限 AST 求值做离线真值表核对，真实事件行为仍待 Actions。未在此新树重跑全业务、完整浏览器矩阵或 CI 构建；未进行模型生成、收费 API、SSH、生产访问或数据迁移。

## 首次 Actions 失败与原候选返修

初始候选虽取得 Astra 精确差异 No findings，真实 `beta-perf-audit` run `38913144641` 的确定性测试步骤仍失败：`test_workflow_gates_all_primary_beta_surfaces_with_three_runs` 精确匹配旧 `branches: [main]` 字符串，未随已批准的分支扩展更新。作者在同一工作树、同一 task／attempt 的 `995e5c2` 上复现，不能以先前独审或新 B0 合同通过豁免。

依据各改动 workflow 的实际 run 命令，sanity 的 Leg 3 通过 `make test-release-contracts` 显式运行根测试。作者沿此入口进一步实测发现 `test_types_workflow_tracks_its_locked_generator_requirements` 同样硬断言旧 main-only 触发。初次定点复现结果为两项失败、77 项通过；这是 B0 触发合同漏适配，不是统计／科学阈值问题。

PMO 分别批准仅修改这两个函数的精确预期：PR base 为 main 与指定集成线，push 再包含指定 Bootstrap 分支。八个页面、三次测量、性能预算、依赖锁版本、always 收尾、无 path 过滤、类型生成器锁和 shell override／临时输出／cmp 等原断言全部保留。AST 对照确认每个文件只有获准函数改变，未增加 skip／xfail、软失败或修改阈值。

修复后性能两文件 42 passed；性能、类型、新 B0 与公开合同五文件组合 294 passed；部署 workflow 选择回归仍为 5 passed、129 deselected。测试使用本工作树的源码和包路径，并显式核对两个性能模块均从当前树导入，避免共享解释器误测其他 worktree。另按真实 sanity 入口，以现有解释器、本树 Makefile／ROOT／包路径和 300 秒进程组上限执行完整离线 `make test-release-contracts`：**1400 passed、158 skipped、1 deselected，5 warnings，217.37 秒，正常退出 0**。本次未改 skip／xfail／marker／科学阈值；跳过和未选择项不算通过证据。警告涉及既有 Pydantic 命名与 powerlaw 拟合边界，本轮未为消除警告修改实现。对实际调用测试的触发断言扫描未发现第三处旧 main-only 假设；生产入口只允许 main 的断言是预期安全边界，不应扩展。

`995e5c2` 的失败检查不能代表新返修候选，旧 No findings 也不覆盖这次改动。PMO 须提交新 SHA、回收 Astra 受影响复审并更新 PR #253，重新核必要检查。旧 run 只能标为失败或被新候选取代，取消不算通过。

## 浏览器保存完成条件返修

候选 `31f868020e5d226352b427394cfb5e7d01b84408` 的 push CI run `38914793667`、job `117019383698` 在 library/auth 隔离组出现一项失败、28 项通过：`test_owner_decision_brief_download_and_create_experiment` 收到 followup POST 200 后立即断言成功文案，实际 DOM 仍为“保存中…”。

直接原因是测试将网络响应事件当作 UI 完成。实际 `analyze.js` handler 先禁用按钮并写保存中，随后等待 fetch 返回、`res.json()` 和下一 Promise 回调，最后才写成功文案；按钮禁用也不是成功证据。本次不改生产 handler，不以无证据的 flaky 标签或重跑旧 SHA 处理。

经 PMO 批准，仅改该测试函数及参数化装饰器，保留下载、375px、指纹、焦点、截止日、真实 POST 200 和最终禁用断言，用 Playwright 的有界自动重试等待真实成功 DOM。正常与 delayed-json 两个 case 均访问原 API；延迟只在测试 browser context 内用手动释放的 JSON Promise 闩阻止 parsed body 交给 handler，未替换请求或返回体。闩未释放时明确断言“保存中…”且不含成功文字，证明旧即时成功断言会失败；释放后成功 DOM 出现，再通过原 GET 接口核对保存的假设、指标、截止日和停止条件。

本地使用现有 pytest／Playwright 1.59.0 和 Chromium：两参数用例 2 passed；完整目标文件 22 passed；所属 library/auth 根浏览器组 64 passed、3 deselected；隔离子组 30 passed；三个所属 JavaScript 信任合同文件全部通过。上述范围有重叠，不相加宣传为唯一测试数。依赖按既有 pnpm 锁离线复用缓存，未改锁、引入新测试框架、增 sleep、扩大超时、skip 或调整阈值。AST 对照确认测试文件仅获准函数和装饰器变化；生产脚本未改。

browser context、Chromium、临时 API／Next 服务均沿 fixture 的 finally 收尾；完成后未见与本工作树对应的遗留测试服务进程。未访问生产或发起付费调用。返修仍由 PMO 提交新 SHA、安排 Astra 受影响复审并核真实 Actions，不把旧 `31f8680` 的失败或旧独审结论冒充新候选结果。

## 回收与下一步

PMO 为本批唯一 Git 提交者。作者停写后，PMO 用精确路径清单提交，不包含未跟踪 AGENTS 或其他树内容；独立 Astra 审查当前差异，返修回本 owner。随后推送 Bootstrap 候选并创建到集成线的 PR，核真实 event／workflow／run／head／base／checkout 及所有必要结果；缺失、取消、未知或失败不放行。

集成线保护由有权限者按精确方案配置并回读，不能靠本 manifest 声称已强制执行。首次合入后再核集成 merge SHA 的检查，之后才接候选修复与 B1 共享实现；main 合并和发布仍各自受门禁。本轮没有执行上述 Git、保护变更、发布或共享冻结动作。
