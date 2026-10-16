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

## 回收与下一步

PMO 为本批唯一 Git 提交者。作者停写后，PMO 用精确路径清单提交，不包含未跟踪 AGENTS 或其他树内容；独立 Astra 审查当前差异，返修回本 owner。随后推送 Bootstrap 候选并创建到集成线的 PR，核真实 event／workflow／run／head／base／checkout 及所有必要结果；缺失、取消、未知或失败不放行。

集成线保护由有权限者按精确方案配置并回读，不能靠本 manifest 声称已强制执行。首次合入后再核集成 merge SHA 的检查，之后才接候选修复与 B1 共享实现；main 合并和发布仍各自受门禁。本轮没有执行上述 Git、保护变更、发布或共享冻结动作。
