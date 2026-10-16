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

## Runtime 版本桥接候选

源基线 `044e08c612dc69aa7d3b78887d4a303446be4cef`。runtime owner 的独立候选正在安全审阅，本树没有复制其 WIP、backend requirements、OpenAPI／TypeScript 生成物或业务源码；本节只形成待组合的 CI 版本桥接，不提交、不推送或合并。

| 项目 | 目标版本 | 本次桥接位置 |
| --- | --- | --- |
| FastAPI | 0.135.0 | CI 两个 browser 安装步骤、nightly browser 安装、Beta workflow 的 expected_versions |
| Pydantic | 2.7.4 | 上述位置及 beta-perf 安装 |
| Starlette | 1.3.1 | CI／nightly browser 安装、Beta workflow 的 expected_versions |
| PyJWT | 2.15.1 | CI／nightly browser 安装 |

uvicorn 0.27.1、httpx 0.27.2、slowapi 0.1.9、structlog 25.5.0 及原测试／浏览器锁保持。初始桥接只适配 PMO 指定的三个 public-controls 函数、一个 beta-perf 函数、一个 deploy-runtime 函数及一个 heredoc 函数中的精确版本字面；随后追加的监测常量权限与范围见下文。其他函数不动，未削减八个硬 job、矩阵、步骤、依赖和失败条件。

语义摘要仅更新两个有版本变化的 job：browser-product-contract 为 `5a7c0ecd56d6300bcf3a3418bdb7ee0f41f2064fb7efa527295d7956b257a205`，browser-beta-surface-contract 为 `26f0c96a942aa86f5027e4d9048c375200260e343278877992070b0bdeaa5479`。更新前已逐 job 验证差异等于四项获准版本替换，其余六个硬 job 和 release-gate-summary 语义未变；摘要仍受 B0 合同检查，不以重算掩盖删检查。

为避免使用旧依赖树假称升级通过，本轮新建独立 Python 3.11.15 环境，按 CI／nightly browser 声明的完整包集合安装，包括 pytest 9.0.3、Playwright 1.59.0、pytest-playwright 0.7.2、Pillow 12.3.0 及合同测试所需 PyYAML 6.0.3。实际解析并安装 45 包，`uv pip check` 确认兼容；逐项读取目标版本，与四个升级版本及保持版本一致。基础 FastAPI／TestClient GET 冒烟通过，未导入产品或 runtime WIP。Starlette 提示当前 httpx TestClient 适配弃用；保留警告，未擅自安装替代包或改变 httpx 锁。

在这个新环境，以本树源码运行 B0、完整 public-controls、获准 beta-perf／deploy-runtime／heredoc 目标合同，**177 passed**。这是桥接字面、CI 安全边界及基础依赖机制证据，不是完整 backend 安装或 runtime／OpenAPI／产品组合验收；不采用旧环境的绿灯代替。

PMO 后续精确追加监测权限：仅将 `scripts/production_smoke.py` 的 EXPECTED_RUNTIME_VERSIONS 内 FastAPI／Pydantic／Starlette 改为目标三版本，uvicorn 不动；`tests/test_production_smoke.py` 只更新当前 release 的两份成功 payload 版本与 bad-version 参数的三个预期错误字符串，原坏版本、无覆盖／身份拒绝、历史模拟及其他逻辑均保留。追加后在同一新环境重跑监测文件和上述精确合同组，**208 passed**，未向公网发送监测请求。

跨 owner 依赖已只读确认并报告：`web/backend/tests/test_openapi_artifact.py::test_browser_contract_jobs_use_the_release_target_runtime_pins` 的 required 元组在本树仍为旧三版本，组合时需 runtime owner／PMO 接续。未跨树改该文件，也未复制尚在独审的 runtime WIP。本树 backend requirements、OpenAPI 和 TypeScript 生成物仍是原基线，各 browser workflow 的真实 Actions、安全复核和完整组合仍待验，不能用本次静态／离线精确合同结果解除这些门禁。

隔离环境仅作为本桥接复核资源保留，owner 为 Bootstrap；没有运行中的浏览器、服务或连接，后续组合验证完成后由 owner 清理。本次未触服务器、生产、收费模型、私有配置或其他树。

## Linux CPU 锁真实安装入口桥接

PMO 追加 `runtime-smoke.yml` 的 Linux 安装桥接，并允许在 B0 合同文件补模板和负例。锁数据只读自已受审提交 `594566481313cf2ac931875e34c7f95d61e997b1`，未复制 runtime 工作树 WIP；Linux 输入摘要为 `4ae9d5046cd002d46712c17d13c28d9be88996c279ca5dc7346199c60aa7e708`，锁摘要为 `efd2731c4e9e212ab75e6bcb53880d88492e1a44272622f05b6c98e8a606b6f5`。本地实际解析该受审锁，确认 73 个带哈希精确版本，Torch 为 `2.14.1+cpu`。

本机固定 uv 0.11.8 的实际 help 已确认支持以下命令。Linux workflow 安装同版工具，用 setup-python 的 Python 3.11 建独立、不 seed pip 的环境，禁止自动切换／下载解释器，再执行：

```sh
uv venv --python "$(python -c 'import sys; print(sys.executable)')" \
  --no-managed-python --no-python-downloads "$RUNTIME_ENV"
uv pip sync --python "$RUNTIME_PYTHON" --torch-backend cpu \
  --require-hashes --strict --no-python-downloads requirements/runtime-linux-cpu.lock
uv pip check --python "$RUNTIME_PYTHON"
```

不使用 `--no-deps` 或跳过哈希。根包正常 editable 安装会额外拉入不属于这份生产锁的 pandas／powerlaw／matplotlib 等研究依赖，所以采用 PMO 明确允许的当前 checkout 源码导入方案：核实际完整 SHA 与导入模块 `__file__` 的归属，使用独立 runtime 的解释器和明确 checkout 导出路径，保留全部重模块 import。源码导入前、导入后、真实 SearchService 冒烟后，均检查依赖兼容、73 包完整版本图、核心桥接版本、实际 Torch CPU 后缀／CUDA 元数据和无 NVIDIA 包。

tiny-KB 步骤仍真实加载模型、编码和查询，明确选择通用 `shibing624/text2vec-base-chinese`，要求真实 KB 大小为二且查询非空。它不证明生产 structural-v2 bundle 完整或查询质量。临时 KB 用 TemporaryDirectory 收尾，workflow 的 always 清理仅删除本 job 固定的独立环境与校验脚本；不触源树或其他运行时。

main／集成／Bootstrap 的原精确触发、schedule 和 dispatch 均保留，push／PR 的 paths 增加 `requirements/runtime-*.in` 与 `requirements/runtime-*.lock`。固定锁尚未进入本 Bootstrap 源，真实安装会保持 fail closed，必须先由 PMO 组合受审 runtime 提交，不能跳过缺锁或提前声称成功。

新增离线合同直接执行 workflow 中的锁图校验器及 source-binding 脚本，以模拟 metadata 和临时 Git 源提供合法对照，并覆盖版本漂移、缺包／额外包、NVIDIA、非 CPU Torch、CUDA、错误平台／Python、缺 hash、错 SHA／跨 checkout 导入、移除哈希／后置核验和跳过 source import 等反例。原八个硬 job 与生产拒绝合同仍保留。扩展后 B0 合同 **89 passed**；新目标版本隔离环境中的完整本次精确合同组 **226 passed**；runtime-smoke 所有 shell 和嵌入 Python 语法通过。

本机是 Mac，没有执行 Linux 73 包安装、CPU Torch import、通用模型下载或真实 SearchService 查询。本地 fixture 只证明校验逻辑及源码绑定机制；Linux 完整安装、包图与模型实际加载／回答必须在组合后 Actions 的当前 SHA 验证。既有 analyze/mobile 性能门槛的失败由相应业务 owner 调查，本轮未改预算、测量、业务代码或对旧 run 盲重试。

## 组合后部署 helper 默认版本返修

组合基线为 `3f00d596c3b76f874c72c3517f7aeeeaa227cc6a`。组合独审发现 P1：`deploy-versioned-runtime.sh` 的默认 FastAPI／Pydantic／Starlette 仍为旧版本，实际部署调用链没有 expected override，导致 `source` 后直接调用 `runtime_validate_direct_pins` 对当前 backend requirements 返回 1。作者以清除 expected-version 环境覆盖的真实 helper 直调用复现，错误为要求旧 FastAPI 精确 pin。

只将 helper 三个默认值改为 0.135.0／2.7.4／1.3.1，uvicorn 0.27.1、override 机制、精确次数检查和全部其他脚本内容不变。逐字归一对照确认整个 helper 等于组合源上的这三项替换。修复后同一无 override 直调用返回 0，实际输出三项新默认与原 uvicorn。

当前 release 的虚拟 runtime 模板同步目标版本；两个故意模拟旧版的失败／恢复场景保留旧 requirements，并显式指定旧 expected。构建失败 fixture 补齐原 helper 已使用的 `-I` 调用形态，并用文件标记证明到达 resolver venv 故障；活动中的不完整 release fixture 明确检查其错误原因，证明没有在默认版本检查处提前退出。原 current／代码／不完整物料保留断言均保持，未把历史输入机械替换为新版本。

新增真实 helper 合同覆盖当前真实 requirements 成功、历史 pin、四项单独漂移、重复／缺失 pin 拒绝，以及历史显式 override 合法且不改变默认。11 项定点合同通过；完整 `test_deploy_versioned_runtime.py` **143 passed，66.82 秒，退出 0**，未跳过或调整阈值。执行器设置 300 秒进程组上限，未触发超时；测试创建的 runtime 模板在结束后清理。`bash -n`、差异空白检查通过；AST 对照确认已有测试体仅两项历史场景作显式路径验证调整，其余原测试体不变。未触任何真实部署、服务、迁移、生产数据或外部付费调用；本轮返修不提交或推送，需新 SHA 的受影响 Astra 复审和必要 CI。

## GitHub job-env context 解析阶段返修

候选 `a98fee6a3aa4ad0811de9113b01a79e32274f81f` 的 [runtime-smoke run 38921464534](https://github.com/dada8899/structural-isomorphism/actions/runs/38921464534) 在 workflow 解析阶段失败，**0 jobs**；它没有执行 Linux 安装。第 53／54 行在 job-level env 使用 `runner.temp`，而 [GitHub context availability](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability) 规定该位置仅允许 github、needs、strategy、matrix、vars、secrets、inputs，runner 要到 step 等允许的位置使用。

本次只移除这两个 job-level 表达式，增加首个路径初始化 step，以已存在的 `RUNNER_TEMP` 写入 `GITHUB_ENV`，后续步骤继续使用原 RUNTIME_ENV／RUNTIME_PYTHON。逐字对照证明 workflow 其余部分完全相同：独立环境、CPU／哈希同步、73 包校验、导入／模型实际检查及原 always 清理均保持，不改锁、测量、其他 CI 或安装策略。

PyYAML 与 Bash 语法不能判断 GitHub context 可用位置，因此新增可移植的窄 job-env context 合同：允许表及带引号文字的合法对照，runner 点／括号／裸对象与其他不可用 contexts／函数的拒绝，原失败配置的回放。测试还实际执行路径初始化和清理：包含空格的 runner 临时目录能导出精确路径，初始化不安装或启动 runtime；非法清理目标被拒绝且未删除，合法目标只清理本 job 资源。

另使用任务私有的 actionlint v1.7.12，`-shellcheck= -pyflakes=` 检查该单一 workflow：对原 a98 源实际复现两个 context 错误并退出 1，对修复后文件退出 0。没有新增 CI job 或工具依赖，也没有以本地窄正则冒充完整 Actions 语义验证。新 B0 合同 **106 passed**；与原 public-controls 同进程回归 **209 passed**。原 shell／嵌入 Python 及源绑定／锁图／清理反例保留。

此结果修复的是解析前置，不是 Linux 安装通过。作者未 dispatch、push、重跑旧 run、调用生产或付费服务；PMO 需提交新 SHA、回收受影响 Astra 复审，再由新的真实 Actions 验证有 job 执行及其实际 Linux 结果。

## Sidebar 回归合同漏接线

基线 `a76d6b97d68cf323211cb0ee3ee052c58c97ab9e` 已包含 sidebar 性能修复及新 Node 合同，但 Make 与 CI 列表漏掉该文件。作者实际复现 `test_frontend_node_gate_cannot_silently_skip_a_contract` 失败：磁盘上的 `web/frontend/tests/test_historySidebarPerformance.js` 不在 Make／CI 的全集中，不能靠减少全集断言或删除测试取得绿灯。

仅在 FRONTEND_NODE_TESTS 增加该 Node，library/auth 的 Make 浏览器列表与 CI 同 shard 的 pytest_args 增加规范路径 `tests/e2e/test_history_sidebar.py`，同 shard node_tests 增加新 Node。原列表、isolated 子组、e2e 条件、工作量及 parser 均保持。逐结构对比证明 CI job 唯一变化是这两条测试路径；browser-beta-surface-contract 的新摘要为 `cc468c8be6afbfe28539a507697c95b4f37e7e5611f8499b7f0445803ab44d18`，其余硬 job 和聚合不动。

Node 合同实际通过，完整 `make test-frontend-node` 通过；B0 硬 job 合同与原漏接线反例组合 107 passed，CI 文件通过 actionlint。规范迁移来自 perf owner 的固定提交 `cd78029c80f53698127c3c2a2cadfc621a318739`；本轮只读该提交确认 ROOT 使用 parents[2]，三项浏览器 case 保持 e2e 标记，Node case 由单独 Node 门禁覆盖，未复制其 WIP 或修改性能实现、测量及预算。

首次接线时该规范文件尚未进入本树，只有旧根路径；缺失路径不是通过证据。PMO 随后合入受审迁移，组合源变为 `91dfd355b6281b4ac1c60a1ed7cfbd2a839dbe14`，四个 CI 接线未提交改动保留，规范文件实际存在。完整 Node 门禁与规范文件四用例通过，CI 文件 actionlint 通过；继续验证发现以下两项确定阻塞，当前不放行：

- 完整 public-controls 与 B0 硬 job 组合为 **208 passed、1 failed**。失败是 `test_makefile_release_authority_is_independently_frozen` 将整个 Makefile 固定为旧摘要 `4b4dfb0608153681fd409d28c3bfd1fea5fecc93aefc550dc6585266d1ffac95`；本次两项合法新增后的摘要为 `9dc5644b315a28704b6041e14d4d30c0d437649daeeda1ef671728f7895733f0`。逐字还原确认只有两条测试路径新增，执行器、recipe 和原列表均未变。未自行改独立冻结断言，已交 PMO／Astra 核准。
- library/auth 主浏览器组合为 **64 passed、4 deselected、3 setup errors**，隔离 web 子组仍 **30 passed**。sidebar 单文件正常，但 unified-library 使用 pytest-playwright 0.7.2 的 session 级 manager，sidebar fixture 又独立启动 Sync manager，在活动 asyncio loop 中失败；已读取实际插件 fixture 源确认，非产品断言失败或无证 flaky。该 fixture 属 perf 测试 owner，已返其最小复用 manager 处理，CI owner 未抢写、未改 parser 或新建 job 隐藏冲突。

Make 摘要变更随后经 Astra 独立前置核验 No findings，确认只新增两条已受审测试路径，原 recipes／executors／顺序保持。PMO 精确授权只更新 `test_makefile_release_authority_is_independently_frozen` 中的摘要为上述新值，仍做完全相等断言，其他函数不改；完整 public-controls 与硬 job 合同重新运行 **209 passed**。该授权不放行 fixture 混组问题，也不替代整批接线的最终独审。

这些用例在目标版本／Playwright 1.59.0 环境中实际运行，未因缺依赖跳过。仍待原 perf 测试 owner 的 fixture 修复受审合入，再验证真实混组；规范主分组不转为 isolated 逃避，旧 a76 的 Node 覆盖失败与本次新发现均保留。本次接线不提交或推送，不通过删测试、弱化冻结／覆盖断言、改预算或盲重跑取得绿灯。

## Daily 卡片加载态就绪条件返修

源基线 `847077a2706a748b37a21bfb1f613d8b86fa451a`。真实 push CI run `38924986095` 的 discovery/classes/papers shard 为 27 passed、1 failed：320 宽度的 daily 用例在 href 断言失败。只读诊断确认 `home.js` 先以三个无 href 的 busy ARTICLE 渲染骨架，与真实结果共用 `.disc-card`；原测试的第一张 `.disc-card` 可见并不代表候选数据已渲染。daily 返回有效 200 后，`loadHomeData` 仍等待 suggest 的 Promise.allSettled 屏障，能够放大该窗口。

有效原测试只自然运行一次且通过，DOM 轨迹仍记录骨架到真实 anchor 的转换；首次错误参数 nodeid 没有执行测试，记录保留，没有反复采到绿。只读受控 320／390 各一次均证明旧等待提前满足而 href 条件为 false；释放 suggest 后三条真实深链、aria、键盘、边界文案与语言切换通过，无 pageerror，console 仅夹具刻意返回的匿名 auth 401。CI 原次没有逐卡 DOM artifact，不能宣称掌握那一次全部 DOM，也不能用本地通过抵消真实失败。

经 PMO 精确授权，只改原 daily 测试函数及参数化：保留正常 320／390，新增各自 suggest-held 对照。受控分支只暂停网络 fixture 的 suggest 完成，daily 原 fixture 返回体不改；确认 daily body 完成且有三条数据后，先证明原 broad 选择器已有三个 busy 骨架、真实 anchors 为零、href 均为空，随后释放建议接口。就绪等待仅从 `.disc-card` 改为 `a.disc-card`，不预筛选正确 href；原 broad 卡片数量、无分数、每条深链／aria、文案、溢出、焦点、44px 和 i18n 断言逐条保留。未增 sleep、延长原等待、skip、修改生产／DOM renderer、导航、预算或其他测试。

Playwright 1.59.0 目标版本环境中，四个正常／受控参数用例 **4 passed**；完整目标文件 **15 passed**；对应 discovery/classes/papers shard **30 passed**；public-controls 与 B0 硬 job 合同 **209 passed**。这些范围重叠，不相加宣传唯一测试数。AST 核实项目内仅获准函数／装饰器变化，原宽度列表和全部原顶层断言保持。测试 context／browser 和静态服务沿 fixture teardown 收尾，未访问生产、收费模型或重跑旧 run。

本轮不把本地证据当新 SHA 的 CI；作者停写后由 PMO 提交、Astra 受影响复核及新 Actions 确认。双接口渲染屏障如需产品层独立加载优化另立明确范围，本次不修改业务来掩盖测试的加载态误判。

## Linux NOT_GATE 两页诊断接线候选

日期：2026-10-17。hook 源基线 `462f301ad66447071a7f5b19a60bc8413d8449b3`。固定 collector 输入为 `4194a4678a2c0e47ffb1bcb09d321fa1ceaccc2e`，其 `PERF_DIAGNOSTICS.md` 第 6 节与 CLI 只读核对；PMO 已回收该工具 Astra No findings 及 104 项独立模拟／原审计回归。本树尚未合入 collector，本轮只准备 hook，不提交、推送、dispatch、发布 marker 或采任何 Mac／Linux trace。

checkout 仅增加 fetch-depth 2，原性能 audit 仅增加 `beta_perf_gate` id，八页、两 viewport、三轮、预算文件及原 run 命令字节保持。原 grade 结束后、借用静态服务关闭前，新增五分钟的 NOT_GATE step：同 repo 的 PR253 synchronize、同 head／base repo、固定 Bootstrap head ref、run_attempt 1 且未取消才调用；红／绿均允许，实际 `steps.beta_perf_gate.outcome` 原样经环境和引用参数传入，不以 grade 红绿决定是否采证。完整 subject `ci: capture structure-perf-linux-r2-20261016` 与 54 项 source、head／checkout 等前置仍由固定 collector 自行严格校验，日期不改 nonce，不增加 force／page／runs／budget 覆盖或令牌／repo 变量平台。

原 always 服务清理和原 artifact 的名字、路径、布局完全不变。新增第二个专属 artifact，在原上传之后，以相同事件边界和 diagnostic step 实际 success／failure outcome 才上传；路径使用合法的 step-with `runner.temp` context，不把 Shell `$RUNNER_TEMP` 写入不会展开的 with.path。未调度／前置拒绝没有文件时用 if-no-files-found ignore，不造空报告。collector incomplete 的非零退出仍分列基础设施失败；没有 continue-on-error 或改写原 grade 的退出／结果，NOT_GATE 不是性能达标证明。

完整 hook 合同恢复后的原 job 语义摘要为 `9859b40bfa87aa0b9c08cb730e4364ee3c2f9a967faa62bdea06cb218dcff714`：只移除新增两步、checkout depth 与原 audit id 后，原安装、确定性单测、服务、审计、清理和上传与原版本完全一致。新测试覆盖 push、opened、reopened、attempt2、错 repo／PR／head／base／ref 和取消拒绝，红绿都允许、删／宽化任一条件被合同拒绝、五分钟及 artifact／清理边界，以及真实 Shell 下原 grade 非零退出不被后续成功吞掉、实际 outcome 和含空格 runner 路径正确传参。该 Shell 检查用明确测试替身，不运行实际 audit 或 collector，也不伪造 capture artifact。

原 public-controls 同时存在全局 HARD_STEP_CONDITIONS 与 release-gate 函数尾部的重复二项条件表。第一次组合回归为 315 passed／1 failed，发现后由 PMO 精确授权两处仅增加同两个固定名称／完整条件字符串；原 Stop／Upload always、manifest 五检查／八依赖／分支／退出断言及 `_assert_hard_job_contract` 均未改。不是放宽到任意 always 或跳过硬检查。

目标版本 Python 3.11／Pydantic 2.7.4 环境下，新 hook 合同 **65 passed**；新合同、原两份 audit、public-controls 与 B0 合同同进程 **316 passed**，一条既有 Pydantic namespace warning，无 skip。任务私有 actionlint v1.7.12 实际检查该 workflow 通过；Shell／Python／差异核对通过。原 workflow 函数的全部原断言保留，public-controls 仅获准全局 beta 条目和该函数尾部精确表变化。

这不是 collector＋hook 当前组合或真实 Linux 采证验收。PMO 须先合受审 collector、提交当前 hook 并回收来源／接线独审，再单次发布唯一 marker；不能先改变 54 项输入、合入 B1／PR247 或重发 marker“采到绿”。旧真实性能失败继续保留，诊断分数、成功退出或 artifact 不能替代原无 Profiler gate。

## Marker 发布前的干净依赖环境返修

日期：2026-10-17。源基线 `41ea13d57b585e9a4b1fdaeaddba939229dae9e3`。当前局部 marker 尚未推送，远端发布仍由 PMO 控制。独审发现 P1：原 workflow 函数新增 `import yaml`，而 beta-perf job 仅直接安装 pytest／Playwright／Pydantic，依赖旧复核环境中预先存在的 PyYAML 才显得通过；干净 job 会在原评分前失败。

本次仅在该安装命令明确增加 `PyYAML==6.0.3`，原 grade／collector／测量／预算／诊断限额与调度条件均不动。精确依赖合同冻结四个直接包及浏览器安装命令，增加删除 PyYAML 的拒绝反例；复原后的 job 摘要只随这项安装依赖修正为 `1ff605671ee6159516eb8f0ca7b1860c415fd1b9dff887c935f832b491ba4348`，原 gate 命令仍逐字相同。collector 的 54 项 source pin 实际全部匹配。

验证从同一受支持 CPython 基解释器创建全新 venv，未继承此前45包环境的 site-packages。初始 pytest／playwright／pydantic／yaml 均不存在，`import yaml` 退出1；之后从实际 workflow 提取 pip 命令，在该新环境正常解析安装全部四项 Python 直接依赖，无额外测试包补丁。实际 Python 为3.11.15，macOS 15.3.1 arm64；yaml6.0.3从该新prefix导入，`pip check` 为No broken requirements found。完整已安装清单如下，含venv自带pip/setuptools：

```text
annotated-types==0.8.0
greenlet==3.5.6
iniconfig==2.3.1
packaging==26.3
pip==24.0
playwright==1.59.0
pluggy==1.7.0
pydantic==2.7.4
pydantic_core==2.18.4
pyee==13.0.1
Pygments==2.21.0
pytest==9.0.3
PyYAML==6.0.3
setuptools==79.0.1
typing_extensions==4.16.0
```

包清单以本轮私有 `verified.json` 原始 metadata 为准；同时保存initial、pip安装日志和两组测试日志，权限600。原 deterministic unit contracts 的实际 argv 在新环境 **42 passed**；新增接线合同 **66 passed**，无skip，一条既有Pydantic namespace warning。actionlint v1.7.12、Shell／Python／差异检查通过。未执行Chromium安装、真实浏览器、HTTP研究、collector或trace；Python依赖闭合不代表Linux浏览器/采证已验收。

本轮不创建其他会话，不提交、推送、amend／rebase／force或触发CI。旧局部空marker保留历史，PMO须先提交本修复并回收当前SHA独审，再以最终marker作首次唯一远端发布；不能用旧45包环境或局部空marker放行真实采证。新临时venv由Bootstrap保留供本修复复核，结束后负责清理；没有运行中的服务或采证资源。

## Cookie／tour 真实弹层操作顺序返修

日期：2026-10-17。源基线 `6224e13eea1c079ee83d5c631e073b482eafbd83`。真实 push CI run `38936481598`、job `117093165122` 的账户手机可访问性用例在430×932被 welcome tour 的全屏 backdrop 拦截 cookie-only click，原文件为12 passed／1 failed。未读取或转发包含夹具一次性链接的原始日志。只读代码证据显示 tour modal 位于z9999、cookie在z200；旧 helper 固定先cookie再skip，无法在click被遮挡时走到skip，并非加等待可解决。PR247精确差异不含这两个组件或该helper，既有单tour owner修复不涉及此操作顺序。

按PMO选择只修测试操作，不改变产品的cookie优先决策或层级。helper在cookie正常click期间临时注册可见tour-skip的locator handler，正常点击Skip并等真实tour隐藏；finally移除handler。随后保留独立延迟tour的正常关闭核查，移除后才手动点残留Skip，避免点击自身再次触发handler。cookie仍实际选择仅必要；click失败不吞掉，未force、写storage、禁tour、加sleep、延超时或自造无界重试。

同文件新增真实Next三种确定对照：tour先显示、cookie先显示后在正常click检查边界推进原1500ms计时器、以及通过真实Skip建立的无tour状态。只用测试时钟控制既有生产timer，没有mock DOM或组件；确认真实consent仅必要。helper返回后通过导航正常重开tour，并用auto-waiting可见断言证明handler没有残留，再正常关闭。原375／390／430账户设置、44px、焦点和axe等全部原测试／fixture的AST保持，只有helper改变及新增对照函数。

Playwright1.59.0／目标runtime45包环境下，三种对照与原430×932定点用例四项均通过。首次私有日志包装器在pytest四项及teardown通过后遇到关闭句柄flush错误（进程120、pytest0）；仅修正包装器关闭顺序，没有以此重跑定点采绿。随后执行原CI文件选择`pytest web/tests/e2e/test_phase_auth_real.py -v`，仅增加隐私capture与显式关闭trace/video/screenshot选项，**16 passed、退出0**（原13项＋新增3项），无skip。原Next/API子进程stdout/stderr在写日志前丢弃；测试结果仅存600权限的脱敏日志和不含链接／凭据的结构化回执，未读取原token日志。

测试context、browser、Next/API服务沿fixture finally收尾，新测试自身finally另移除边界handler并关闭context。原54source、评分、collector和marker均未修改，未trace、Profiler、HTTP研究、SSH、模型或提交／推送。此卡完成后helper源码停写，后续Papers卡按独立范围顺序接续，最终两卡由PMO按当前完整SHA独审。

## Papers 重复语言通知的目录去重

日期：2026-10-17。接续同一源基线 `6224e13eea1c079ee83d5c631e073b482eafbd83`，弹层helper保持停写。PMO回收的既有Linux离线诊断将Papers重复整目录替换定位到多次i18n通知；本卡只修改Papers本地renderer、原两Papers测试文件和本记录，不更改全局i18n、utils、评分、预算、CI、Make、collector或原54输入摘要。既有采证已完成，Papers源码变化后历史固定摘要自然不再代表当前源码，不能重写历史摘要或重采来覆盖。

renderer以已成功完成的validated对象身份和实际语言作为去重条件；重复通知仍同步静态ARIA标签，保留现有目录节点、展开状态、筛选和焦点。实际语言变化、新validated对象继续完整渲染全部20项，沿原逻辑恢复展开slug与筛选。替换前清除成功记录，只有目录、筛选及aria-busy全部完成才记录成功；根缺失及错误显示均清除成功记录，失败后同对象同语言仍可重试。未减少正文、材料数量、安全边界或延后内容渲染，没有添加产品调试接口。

原Node合同文件新增真实renderer闭包的受控生命周期检查：manifest前／后的i18n通知、连续同tuple通知、新validated对象、zh→en→zh、初次根缺失、最终完成步骤抛错及已渲染后根缺失恢复。真实Chromium新增公共i18n.render广播检查，连续三次广播保持全部节点身份、真实summary焦点、展开和筛选；换语言检查标题、材料状态、边界、20项链接及可见1项计数，并运行原axe规则。原两个文件全部既有函数、fixture与类AST逐项核对原样，既有断言未删改。

目标runtime45包环境，最终命令 `python -m pytest tests/test_papers_public_contract.py tests/e2e/test_papers_public_runtime.py -q --tracing=off --video=off --screenshot=off -p no:cacheprovider` 配合当前树PYTHONPATH，**25 passed，退出0**。首次新增浏览器断言误把首条historical-draft写成historical-record，24 passed／1 failed；仅更正该新增预期后25 passed，再补根缺失恢复的源码及反例，最终当前版本25 passed。包含原375／390／430矩阵、20条详情路由、安全Markdown与axe；本机浏览器结果不替代Linux性能或发布验收。Node语法、差异检查通过。所有测试context和服务沿原fixture finally收尾，未创建trace、Profiler、新marker、SSH、外部模型或提交／推送。

两卡至此作者停写，PMO回收精确五文件差异并按当前SHA独审。helper的16项已完成结果保留，未无故重跑；Papers最终25项通过不撤销既有Linux性能失败，也不代表已部署。

## 历史采证清单与后续产品源码的组合合同返修

日期：2026-10-17。PMO已将前述两卡精确提交为 `bd5d681f638c68825b14ac1f146e0eab48a9c51e`，独立审查的25项Papers、16项Next及275项静态检查通过，但另发现发布组合P1：`test_pins_cover_both_pages_shared_assets_fixture_and_original_audit` 永久将当前工作树逐文件与历史54pin比较，使合法Papers修复必然被历史快照拦住。真实collector普通subject已返回not_scheduled；带原marker的新源码仍会拒绝，不应通过重写历史摘要或放宽真实来源校验来处理。

本卡仅改该历史合同函数、新增两个参数化反例函数与本记录。以UTF-8、sort_keys和紧凑分隔的canonical JSON固定原base_sha和全部source_pins的联合SHA-256 `3d885f0afbc667763e3258f9537a9016b238d195630fa98ffa2fe03a4c391cea`，保留原路径覆盖并要求54项，冻结的是原采证清单身份；正常后续产品工作树不再永久等于旧内容。新增base／摘要／路径／缺项四类清单变造拒绝；隔离目录复制当前源码后模拟后续Papers修订，执行真实main→run→verify_binding，仅注入浅Git读取与Linux平台前提：普通subject退出0、not_scheduled且只读取三项Git身份；marker退出2、source_digest_mismatch。两者均在grade、依赖、动态导入、service、claim及capture前停止，无采证目录，也不读取原847历史对象或fetch。原其他函数AST全部保持。

目标Python3.11环境，诊断文件 **68 passed**；perf_audit、beta_perf_audit、beta_perf_diagnostics及Papers静态组合 **125 passed**，一条原Pydantic namespace warning。没有新生产改动，沿已完成25项Papers及16项Next独立结果，不重跑浏览器。首次原make test-release-contracts使用45包环境因缺NumPy在收集阶段16 errors、退出2；未修改安装或联网，改用本机既有Python3.14.7／NumPy2.4.4环境执行同一原make目标，完整结果为 **1608 passed、160 skipped、1 deselected、1 failed**，80条既有warning、218.50秒，make退出2（内部目标Error 1）。唯一失败是既有 `test_runtime_proofs_ignore_cwd_and_pythonpath_distribution_injection` 的ABI断言：expected cpython-311、actual cpython-314；未更改测试或部署脚本。在现有目标Python3.11.15环境单独复核此原用例 **1 passed、退出0**。因此记录完整本机make执行及版本边界，不宣称目标3.11全量发布合同全部通过；本卡相关125项和该ABI用例在3.11分别通过。

collector、原54pin、生产Papers、helper、Make、CI、原grade和预算未改，无浏览器、trace、Profiler、新marker、网络、SSH、费用或提交／推送。此卡交PMO回收当前差异及新SHA独审，不以历史快照身份合同替代真实受准marker的强制来源校验。

## 回收与下一步

PMO 为本批唯一 Git 提交者。作者停写后，PMO 用精确路径清单提交，不包含未跟踪 AGENTS 或其他树内容；独立 Astra 审查当前差异，返修回本 owner。随后推送 Bootstrap 候选并创建到集成线的 PR，核真实 event／workflow／run／head／base／checkout 及所有必要结果；缺失、取消、未知或失败不放行。

集成线保护由有权限者按精确方案配置并回读，不能靠本 manifest 声称已强制执行。首次合入后再核集成 merge SHA 的检查，之后才接候选修复与 B1 共享实现；main 合并和发布仍各自受门禁。本轮没有执行上述 Git、保护变更、发布或共享冻结动作。
