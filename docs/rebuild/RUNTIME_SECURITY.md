# Structure 运行依赖安全候选

日期：2026-10-16。任务：STRUCTURE-RUNTIME-SECURITY，attempt 1，Issue #254。基线 `be3a3c6b5de19f2508335519d01240077bb591ec`，独立分支 `fix/runtime-security-20261016`。本轮仅形成受支持依赖、平台锁候选、回归与生成物；未改 CI、监测脚本、业务处理、服务器或用户数据，未提交或推送。

**兼容组合已在 macOS 原生环境实际安装并通过本轮回归，Linux CPU 图只完成交叉解析，尚未冻结为可部署运行时。** main 仍为生产权威；本候选还须与 CI／监测桥接、独立安全代码审、Linux 实装及当前 SHA 必要检查闭合。

## 兼容选择与漏洞可达性

FastAPI 0.115.14 的官方元数据要求 Starlette 小于 0.47，不能通过强装单个 Starlette 来修复文件与表单路径。候选使用 FastAPI 0.135.0、Starlette 1.3.1、Pydantic 2.7.4；官方元数据允许此组合，实际解析未使用 `--no-deps`。不选引入更多基线变化的最新主框架，也不机械升级 Phase Next major。

| 包 | 原声明 | 候选 | 依据与边界 |
| --- | --- | --- | --- |
| FastAPI | 0.115.14 | 0.135.0 | 原 Starlette 上界冲突；候选要求 Starlette >=0.46、Pydantic >=2.7，实际兼容回归通过 |
| Starlette | 0.46.2 | 1.3.1 | 包含 FileResponse Range 合并修复及 urlencoded 表单解析限额修复；主站确有文件路由，Phase 确有 Form 路径 |
| Pydantic | 2.6.1 | 2.7.4 | 最小兼容的已测试补丁版本；已纳入实际解析图复扫和 API／账户回归，不以元数据解析代替行为验证 |
| python-multipart | Phase 0.0.20；主站范围 | 0.0.32 | 包含 part header、分号解析及负 Content-Length 修复；后者仅直接 `parse_form()` 受影响，Starlette 驱动 parser 不走该路径，不能虚报为本应用远程漏洞 |
| PyJWT | 2.12.1 | 2.15.1 | 治理已知条件公告。当前固定 HS256、无 JWKS／混合算法前提，不支持“旧账户可伪造”的判断；新增 payload／OKP 公告同样按实际前提区分 |
| python-dotenv | 1.0.1 | 1.2.2 | 图复扫发现 set_key／unset_key 的本地 symlink 重写公告；未见应用调用这两个写函数，不称当前远程可利用；最小升级并回归现有加载行为 |

模型库家族采用原已观察环境中的 SentenceTransformer 5.7.0、Torch 2.14.1、transformers 5.19.0、safetensors 0.8.0，未为本任务更换模型或训练。其余直接依赖按当前候选精确声明，完整目标约束与分发摘要由平台锁补齐。

Phase 的静态研究内容和冻结结果保留，未经修复及验证的动态服务本轮不启用。该产品决定不等于 Next 告警已修复；本轮没有修改 Next package/lock、导航或旧数据。主产品是 FastAPI 和静态前端，不能把 Phase 的构建链公告直接计为主站可利用 RCE。

## 平台图、分发摘要与恢复边界

| 目标 | 本轮取得的证据 | 尚不能宣称什么 |
| --- | --- | --- |
| CPython 3.11／x86_64 GNU Linux／CPU | `runtime-linux-cpu.in/.lock` 交叉解析 73 包，Torch `2.14.1+cpu`，无 NVIDIA 包，1,478 个分发 SHA256 | 没有 Linux 安装、native wheel 导入、实际选轮清单、载模或运行时证明 |
| CPython 3.11.15／macOS 15.3.1／arm64 | 原生解析 73 包，Torch 2.14.1，1,469 个分发 SHA256；隔离 venv 以 `--require-hashes` 实装，包兼容检查通过 | 不是 Linux 图，也不是未来服务的冻结或恢复验收 |
| Python 3.10／Linux 兼容矩阵 | 主服务 requirements 交叉解析成功；Torch `2.14.1+cpu`、SciPy 1.15.3、scikit-learn 1.7.2 | 仅解析，不是实装／测试；不能误用 3.11 的锁去宣称 3.10 目标 graph |

工具为 uv 0.11.8。通用 Darwin 交叉目标默认的 macOS 13 不接受 Torch 的 macOS 14 wheel，本轮先得到明确解析失败，再按实际 macOS 15.3.1 原生解析；没有为消除失败而静默换旧 Torch。解释器 SOABI 为 `cpython-311-darwin`，其构建平台标签与当前宿主版本分别记录。

平台锁含包版本与可接受分发的完整摘要，可能含 wheel 和源分发，不是“本次最终选中 wheel 已逐个归档”的收据。部署前仍须在对应 Linux／ABI 实装，留实际分发来源、选轮摘要、已安装 graph 和恢复包。两个服务保留独立运行环境；共享的完整约束不要求 Phase 安装主产品全部模型库。

可复现命令均在仓库根运行，只作用于新建的目标 venv：

```bash
uv pip compile --python-version 3.11 --python-platform x86_64-unknown-linux-gnu \
  --torch-backend cpu --generate-hashes requirements/runtime-linux-cpu.in \
  -o requirements/runtime-linux-cpu.lock
uv pip compile --python .venv/bin/python --generate-hashes \
  requirements/runtime-macos-arm64.in -o requirements/runtime-macos-arm64.lock
uv pip sync --python <linux-candidate-venv>/bin/python --torch-backend cpu \
  --require-hashes requirements/runtime-linux-cpu.lock
uv pip check --python <linux-candidate-venv>/bin/python
```

73 包候选经 OSV querybatch 复扫后零匹配；这只是查询时点的包公告匹配结果，不覆盖 native 库、系统包、CDN、Next 或未知漏洞。不能据此批准上线。

## Schema 与生成器一致性

`scripts/requirements-types.txt` 的 Pydantic 精确 pin 同步为 2.7.4，pydantic-to-typescript 2.0.0 不变。OpenAPI 和 TypeScript 均由原有受控生成器生成、再检查；没有环境绕过。API 仍为 105 paths、136 schemas，TypeScript 的 74 个声明逐字未变，但这些数量不能单独证明兼容。

OpenAPI 有 188 个结构差异，按行为分为三类：

| 变化 | 具体含义 | 验证与限制 |
| --- | --- | --- |
| 非 null 单值 Literal 新增 enum／type，含 anyOf 内分支 | 由既有 const 可推出，重复表达原约束 | 剔除这些可证明冗余的注解后继续比较，未以“全是格式变化”掩盖其余差异 |
| 19 个既有 Literal[None] 字段明确 enum[null]／type:null | 旧文档仅剩 title，源模型本来就只接受 None；涉及候选 score、source／ledger 空证据字段等 | 新运行时 None 正例和非 null 反例通过；这是文档约束变明确，不增加已验证证据，也不允许填入数值分数 |
| 默认 ValidationError 增加可选 input／ctx | FastAPI 默认错误模型文档变化 | 实际主服务 RFC7807 handler 仍只投影 loc/msg/type；含私密 canary 的无效输入不回显，未修改错误处理源码 |

没有发现路径、操作、默认值、业务字段可空性或验证阈值的其他变化；独立审查仍须核对完整生成物差异，而不只复用本表。现有错误模型与自定义 RFC7807 的文档覆盖差异不在本次偷偷重设计。

## 已执行检查

| 范围 | 实际结果与环境边界 |
| --- | --- |
| 完整 backend | macOS 候选实际图：1,908 passed、1 skipped；未把 skip 计为运行通过 |
| 账户／SSO／删除／限流与新增文件路径／校验隐私 | 181 passed，已包含在 backend 总范围；不另相加宣传唯一测试数 |
| 完整 Phase API | 53 passed；其中26项为正常／超量Form、multipart header、分号与隐私子集，不相加；实际Phase app和临时SQLite，无真实发信 |
| 原 OpenAPI artifact 检查 | 12 passed；wrong999 拒绝和必须精确 pin 保留；其中 browser CI 的旧字面 pin 待协调桥接，不能当新目标 CI 已一致 |
| Phase SSO import 合同 | 6 passed；只更新获准的依赖精确值，其他门禁未改 |
| 正式生成器 | OpenAPI `--write` 后 `--check` 成功；TS 临时输出与 tracked 文件 cmp 相同，临时文件已删除 |
| 实际本地模型 | 四个 manifest required file 摘要匹配后，离线／local-only／trust_remote_code=false／CPU 载入既有 structural-v2，encode `[1,768]` 且全有限 |

模型测试不下载模型、不调用收费 API，不代表检索质量或 Linux 载模。首次最小环境的完整 app lifespan 曾因缺 jieba 被现有 fail-fast 拒绝；补齐 graph 后完成上述组件／模型验证，但没有把它改写成完整生产启动成功。首次模型探针的旧 namespace 预置检查也曾拒绝，静态核实两个已校验配置中的官方模块 namespace 后才执行载入，没有放宽为任意模块。

## CI 与监测桥接交接

以下文件不由 runtime owner 写；不能删除旧精确检查或以其未同步为由豁免失败。B0／监测 owner 应在分别提交、审阅后的非生产组合分支适配：

| 文件与位置 | 最小变更与应保留的门禁 |
| --- | --- |
| `ci.yml` 的 browser-product-contract／browser-beta-surface-contract 安装步骤 | FastAPI 0.135.0、Pydantic 2.7.4、Starlette 1.3.1、PyJWT 2.15.1；其余 pytest／浏览器／slowapi 等锁和所有作业依赖保留 |
| `beta-perf.yml` 安装步骤 | Pydantic 2.7.4；八页面、三次运行、预算和收尾不变 |
| `nightly.yml` 重建浏览器运行时步骤 | 同一受审核心版本表，不让夜间继续测旧框架 |
| `deploy-beta-backend.yml` 的 immutable runtime attestation 版本表 | 更新前三核心版本，uvicorn 0.27.1 不变；requirements／installed graph／源码 SHA 验证不能删 |
| `production_smoke.py` 的 EXPECTED_RUNTIME_VERSIONS | 与受审目标一致；相应成功 payload／非法版本反例一起适配，不能放宽为任意版本 |
| `runtime-smoke.yml` 的 canonical Linux py3.11 | 在独立候选 venv 以 CPU 锁 require-hashes 实装，导入二进制与重型模块，留 graph／ABI／锁摘要；不得用 PyPI 泛 CUDA 图代替。其他 Python／macOS 矩阵保留各自兼容性检查，不能谎称它们装了 Linux 3.11 图 |

既有 runtime smoke 的两行临时 KB／默认模型回退是通用类库加载探针，不证明相同生产物料或新产品任务通过。桥接须保留其合法功能验证及失败拒绝，同时单列实际生产 bundle 的 Linux 验收；不能把模型不可得静默 skip 成通过。

最小 canonical Linux 图流程可在外层 CI 工具解释器安装固定 uv，在另一个 Python 3.11 候选 venv 用 CPU 锁 `--require-hashes` 同步并 `uv pip check`，先记录仅生产73包的 graph／ABI／锁摘要，再在另外受约束的测试环境加工具。项目源码可从当前 checkout 的显式导出路径导入；不能用 `pip install -e .` 二次解析修改过的候选图后仍声称是同一73包。若必须安装项目包，先使用标准构建准备并比较安装前后所有已锁包与摘要，不使用 `--no-deps` 硬装来隐藏冲突。模型和实际分发恢复证据继续单列。

CI 依赖版本变更会有意改变 B0 的对应 job 语义摘要，需精确更新该已审基线而非删除八个硬作业保护。关联旧字面断言分别位于 public_controls 的三个浏览器安装函数、beta_perf 的 workflow 函数、openapi_artifact 的 browser pin 函数，以及部署／production_smoke／heredoc 的当前版本 fixture。模拟历史构建的自洽旧版本 fixture 不应机械替换，只有绑定当前 release 的预期需要适配。当前仅获准的三个测试函数由本 owner 改，其余待协调者明确 owner。

## 收尾与剩余门禁

任务 venv 和锁定 Node 类型生成器保留供独审，未启动 HTTP 进程、浏览器、监听或持久连接。没有下载模型、读取用户业务行、发送真实邮件、调用收费模型、SSH 或改变服务器。仍需：当前差异独立安全代码审、组合 CI／监测桥接、Linux CPU 实装与二进制/选轮/实际 bundle 验收、生产恢复和实际路径风险闭合。私有凭据、账号、余额与目标连接不在本报告或锁文件中。

## 一手来源

- [FastAPI 0.115.14 元数据](https://pypi.org/pypi/fastapi/0.115.14/json)、[FastAPI 0.135.0 元数据](https://pypi.org/pypi/fastapi/0.135.0/json)、[Starlette 1.3.1 元数据](https://pypi.org/pypi/starlette/1.3.1/json)。
- [Starlette Range 修复](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8)、[urlencoded 限额](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq)。
- [multipart 分号解析](https://github.com/Kludex/python-multipart/security/advisories/GHSA-5rvq-cxj2-64vf)、[负 Content-Length 条件](https://github.com/Kludex/python-multipart/security/advisories/GHSA-v9pg-7xvm-68hf)。
- [PyJWT pre-verification payload](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)、[OKP key 条件](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-x33g-cr3x-6449)。
- [dotenv 本地写入 symlink 条件](https://github.com/theskumar/python-dotenv/security/advisories/GHSA-mf9w-mj56-hr94)。
