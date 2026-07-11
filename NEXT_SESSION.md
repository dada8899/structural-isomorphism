# Structural Isomorphism — 下一会话交接

> 日期：2026-07-11
> 状态：已由用户明确恢复；本地审计完成，生产修复尚未执行
> 当前唯一入口：本文件
> 历史封存快照：`FROZEN.md`（仅作历史依据，不再作为当前入口）

## 0. 下一会话先做什么

```bash
cd /Users/dadamini/Projects/structural-isomorphism
pwd
git rev-parse --show-toplevel
git status --short
head -5 README.md
sed -n '1,320p' NEXT_SESSION.md
```

先向用户确认一句：

> 已进入 Structural Isomorphism，本地工作树保留了 4 个未提交修复；是否授权我执行两个线上 P0 恢复（beta 数据恢复、phase API 依赖修复）？密钥轮换仍需你在服务商控制台完成。

不要先 `git pull`、不要覆盖 4 个未提交文件、不要直接部署、不要展示任何密钥值。

## 1. 项目与运行拓扑

| 层 | 当前事实 |
|---|---|
| 本地权威代码 | `/Users/dadamini/Projects/structural-isomorphism`，Git `main` |
| GitHub | `dada8899/structural-isomorphism`，公开仓库 |
| VPS 旧同步目录 | `/root/Projects/structural-isomorphism`，没有 `.git`，不能当代码权威源 |
| VPS Phase 目录 | `/root/Projects/structural-isomorphism-v4`，独立 Git 工作树 |
| 项目介绍站 | `https://structural.bytedance.city/` |
| beta 产品 | `https://beta.structural.bytedance.city/` |
| Phase Detector | `https://phase.structural.bytedance.city/` 与 `https://phase.bytedance.city/` 的配置需部署前再次核对 |
| beta 后端 | systemd `structural-web`，本机端口 `5004` |
| Phase API / Web | systemd `phase-detector-api`（`8200`）与 `phase-detector-web`（`3210`） |

本轮已更新 Codex 状态：

- `~/.codex/state/current_project` = `structural-isomorphism`
- `~/.codex/state/next_cwd` = `/Users/dadamini/Projects/structural-isomorphism`
- `~/.codex/project_registry.md` 已将项目标记为 `active`

## 2. 本轮结论

项目不缺功能，当前真正缺的是可靠的核心闭环。

推荐把产品从“跨领域搜索工具集合”收敛为 **Validated Transfer Workbench（经验证的跨领域迁移工作台）**：用户提交问题，系统生成结构指纹，给出候选同构、PASS/FAIL 证据、可迁移解法、最小实验和结果回写。核心资产不是页面数量或原始语料，而是可验证的同构对、拒绝理由和迁移结果。

产品研究方向成立，但目前不能继续扩页面、付费入口或泛化到投资预测。应先恢复线上核心能力、统一数据和模型版本、建立真实任务评测集，再验证一个明确人群的使用闭环。

## 3. 线上 P0：尚未修复

### P0-A：beta 搜索静默失效

现象：

- `GET /api/health?deep=1` 返回 `ok`，但 `kb_size = 0`
- 真实搜索请求返回 HTTP 200、`count = 0`，约 10 秒
- 页面和进程存活，因此现有监控误判为健康

四层根因：

1. 表面：搜索没有结果。
2. 直接原因：VPS 的 `data/kb-expanded.jsonl` 只有约 132 字节，是 Git LFS pointer，不是真实 JSONL。
3. 系统根因：部署流程没有验证 LFS 物料、行数、checksum、KB 与 embeddings 维度；健康检查只验证服务对象存在。
4. 全局影响：所有依赖 KB 的搜索、分析与报告可能静默产出空结果；成功的 HTTP 状态掩盖了产品不可用。

恢复前必须核对：

- 本地真实 `data/kb-expanded.jsonl`：4,443 条
- 与它严格匹配的 v2 embeddings 是 `web/data/kb_v2_embeddings.npy.bak-session22`：`4443 x 768`
- VPS 当前配置指向的 `web/data/kb_v2_embeddings.npy` 在本地是 `4856 x 768`，不能与 4,443 条 KB 混用

修复验收：

- 生产 KB 不是 LFS pointer，条数与 manifest 一致
- embeddings 第一维与 KB 条数一致
- deep health 在 `kb_size == 0` 或维度不匹配时返回失败
- 至少 5 个固定查询有非空结果，并检查跨域质量，不只检查 HTTP 200

### P0-B：Phase API 持续崩溃

现象：

- `phase-detector-web` 在线
- `phase-detector-api` 在 systemd crash loop，累计重启约 43 万次
- nginx `/api/` 请求返回 502
- GitHub EWS nightly 每天在最终 API smoke 失败

四层根因：

1. 表面：Phase API 502。
2. 直接原因：`api/universality.py` 导入 `yaml`，运行环境没有 PyYAML。
3. 系统根因：依赖声明、生产 venv 和部署流程不一致；工作流先重建前端，直到最后才检查 API。
4. 全局影响：前端看似可用，但 universality/EWS API 不可用；持续重启浪费资源并污染日志。

修复验收：

- 在受控 requirements/lock 中加入并锁定 PyYAML，不只手工 `pip install`
- 重建或同步 API venv，重启服务
- `/api/health` 与 `/api/ews/meta` 返回 200 且 schema 正确
- EWS nightly 全链路通过
- systemd restart counter 不再增长

### P0-C：公开仓库历史密钥风险

- GitHub Issue `#228` 仍开放，标题指出 MiniMax API 密钥曾进入仓库。
- 历史封存文档还记录过 OpenRouter / DeepSeek 泄漏风险。
- 本轮只做了脱敏扫描，没有读取或输出密钥值。

必须由用户在对应服务商控制台撤销并轮换所有疑似暴露的 key，再更新 GitHub/VPS secret。只清 Git 历史不能使已暴露 key 失效。

## 4. 数据、模型与版本漂移

当前没有单一数据 manifest，不同文件和文档同时出现 4,443、4,856、4,888、5,341、5,689 等口径：

| 文件 | 本轮实测 |
|---|---:|
| `data/kb-expanded.jsonl` | 4,443 unique ids |
| `data/kb-5000-merged.jsonl` | 5,341 unique ids |
| `data/clean-expanded.jsonl` | 5,689 行，训练格式，不含统一 `id` |
| `web/data/kb_embeddings.npy` | `4888 x 768` |
| `web/data/kb_v2_embeddings.npy` | `4856 x 768` |
| `web/data/kb_v2_embeddings.npy.bak-session22` | `4443 x 768` |

其他风险：

- `models/structural-v2` 在本地存在，但被忽略且不在 Git/LFS；公开 Hugging Face 地址当前不能作为可靠恢复源。
- beta 生产后端版本为旧 SHA，VPS 旧同步目录没有 Git 元数据。
- README、model card、dataset card、部署文档的模型名和数量互相漂移。

下一步应新增一个权威 manifest，至少记录：artifact name、schema version、row count、embedding shape、model id、checksum、生成命令、生成日期。部署必须按 manifest fail closed。

## 5. 本地环境与测试基线

本地仓库已可继续开发，依赖和真实模型/数据已完成冒烟验证。

已通过：

| 范围 | 结果 |
|---|---:|
| 根目录 `make test-fast` | 299 passed，27 deselected |
| `web/backend` | 830 passed，1 skipped |
| `packages/guarded-llm` | 111 passed |
| `packages/cross-judge` | 162 passed |
| `packages/reject-aware-critic` | 50 passed |
| `packages/soc-pipeline` | 79 passed |
| Phase Detector production build | 成功，29 routes |

说明：以上总数存在不同 test root 的统计口径，不要把简单求和宣传成“唯一测试数”。当前 `make test-fast` 不包含 web backend 和各 package，绿色基线仍是碎片化的。

本地后端实测：

- 使用 4,443 条 KB、`structural-v2` 和匹配的 `4443 x 768` embeddings 成功启动
- deep health 返回 `kb_size = 4443`
- 与线上同一查询在本地约 0.47 秒返回 3 条结果
- 临时服务已正常关闭，没有残留监听

环境债务：

- 当前 `.venv` 是 Python 3.14.5，而项目声明和生产更接近 3.11；本机已有 Python 3.12
- `pip check` 有 `jsonschema` / `cffconvert` 与 `starlette` / `sse-starlette` 冲突
- `soc-pipeline` 单包测试产生约 246 万条 warning，耗时约 158 秒
- Phase build 依赖 Google Fonts 网络请求；离线/代理失效时会失败
- 本机旧代理 `127.0.0.1:7890` 会干扰 Git 和字体下载；需要显式清理代理环境后重试

## 6. 当前未提交修改：必须保留

工作树有 4 个本轮修复，尚未 commit / push：

1. `v4/tests/integration/test_pipeline_e2e.py`
   - 去掉把 `v4/lib` 插到 `sys.path` 首位的旧做法
   - 改为包路径导入，修复全量测试中的 `soc_pipeline` 自导入/循环导入污染
2. `structural_isomorphism/model.py`
   - 默认模型路径从不存在的 `structural-v1` 改为本地实际存在的 `structural-v2`
3. `web/scripts/precompute_embeddings.py`
   - 默认预计算模型同步改为 `structural-v2`
4. `web/backend/.env.example`
   - 去掉个人硬编码路径，示例改为通用路径和 `structural-v2`

这些修改已经过目标测试和全量相关测试验证，但下一会话仍应先看 diff，再决定是否组成一个本地修复 commit：

```bash
git diff --check
git diff -- structural_isomorphism/model.py \
  v4/tests/integration/test_pipeline_e2e.py \
  web/backend/.env.example \
  web/scripts/precompute_embeddings.py
```

根目录 `.env` 权限已从 `644` 收紧到 `600`，不要输出其内容。

## 7. 产品体验与功能问题

本轮无法使用内置交互浏览器进行点击和截图验收；以下结论来自线上 HTTP/API、代码、构建、文档和本地真实查询，应在下一轮生产恢复后补一轮浏览器端验收。

核心体验问题：

- 首页承诺与线上核心能力不一致：产品可以加载，但搜索为零结果。
- 检索质量不稳定：明确结构事件有时表现好，普通业务问题会出现弱相关或同领域结果，削弱“跨领域迁移”的价值。
- OOS guard 不完整，例如简单算术形式可能没有被拒绝。
- 英文查询质量明显弱于中文。
- 数据集中的同领域 exact match 容易压过真正有价值的跨领域候选。
- 页面、工具、API 和实验入口过多，主任务不突出；billing/checkout 等仍有 mock 成分。
- 缺少“采用了哪个迁移建议、做了什么实验、结果如何”的结果回流，所以无法形成可学习的产品数据。

已实现但需要恢复后验证的能力：置信度分层、OOS/forecast guard、reports 入口、2–3 分钟预期、verified pairs 和人工验证提示。旧审计中部分问题已经被代码修复，不要照搬旧结论。

## 8. 研究状态

研究资产的强项：固定 Clauset MLE 流程、预注册、null controls、PASS/FAIL/REJECT 诚实报告，以及地震、股票、DeFi、神经等实证数据。

当前不宜直接投稿或继续扩大 universality claim：

- v0.5 草稿约 25,085 字，但文件自身仍标记为 reviewer-readable draft / do not submit
- v0.4 的 18 类中有较多 synthetic anchors
- 部分判定来自单次 session，跨领域预测尚未形成独立外部验证
- 引用、arXiv placeholder、DOI 和宽置信区间仍需整理
- Phase Detector 的市场 backtest 是负结果，不应包装成投资预测产品；可以作为透明可信的研究资产

建议拆成 1–2 个可防守的问题，先找统计/复杂系统与各领域外部专家 review，再决定论文边界，不启动泛化更大的 v0.6。

## 9. 推荐推进顺序

### 0–72 小时：恢复可信运行

1. 用户撤销并轮换所有疑似泄漏 key。
2. 经用户授权后，恢复 beta 的真实 KB 与匹配 embeddings。
3. 修 deep health、部署前 artifact 校验和语义 smoke tests。
4. 经用户授权后，把 PyYAML 写入 Phase 受控依赖并恢复 API。
5. 为两个线上系统保存部署前备份、回滚命令和验证证据。

### 第 1–2 周：建立单一绿色基线

1. 建 canonical data/model manifest。
2. 用 Python 3.12 重建干净本地 venv，解决依赖冲突。
3. 建一个真正覆盖 root、backend、packages、Phase build 的统一 CI 入口。
4. 建 warning budget，先处理 246 万 warning 与 Clauset 性能债。
5. 评估外部 PR `#229`（continuous Clauset fitting 加速），不要在未审 diff/测试前合并。
6. 建 100 条真实任务的中英双语评测集，覆盖空值、特殊字符、OOS、同领域压制和跨领域质量。

### 第 3–6 周：产品收敛

只服务一个首发 ICP，建议先在 PM / 增长 / 内容创作者中选一个，而不是三者同时做。主流程固定为：

`问题 → 结构指纹 → 候选同构 → 证据/反证 → 迁移计划 → 最小实验 → 结果回写`

成功指标至少包括：有效候选率、跨域率、人工接受率、实验启动率、报告完成率、7/30 日复用率，而不是只看查询量。

### 第 7–12 周：决定产品与论文是否继续扩张

- 产品：只有核心评测和用户结果闭环达标后，才开放 API/MCP、团队协作和付费。
- 研究：完成外部 review、可复现包与引用清理后，再决定投稿和 claim 边界。
- Phase：定位为研究验证/透明负结果资产，不与“投资 alpha”绑定。

## 10. 明确不要做

- 不在 P0 未恢复时继续增加页面、工具、支付功能或新领域。
- 不把 HTTP 200、进程 active、前端可打开当作产品健康。
- 不把 KB 和 embeddings 通过文件名猜配。
- 不从 VPS 无 Git 的旧目录反向覆盖本地。
- 不用 rsync 覆盖 `.git`、`.env`、venv、lock 或模型缓存。
- 不在轮换前把历史清理误当作密钥修复。
- 不把 Phase 的负 backtest 宣传成可交易能力。

## 11. 下一会话完成标准

如果用户授权线上修复，下一会话至少应交付：

- 密钥轮换状态由用户确认；对话与日志中无 secret 值
- beta deep health 对零 KB fail closed
- beta 固定查询返回非空且人工检查质量
- KB / embeddings / model checksum 被记录到唯一 manifest
- Phase API 两个真实 endpoint 通过，restart counter 稳定
- EWS workflow 通过或剩余失败有完整四层根因
- 4 个本地修改完成 diff review、测试、单一 commit；用户未授权则不 push
- 更新本文件与 `~/progress.md`，写清部署、验证和回滚

---

本轮未执行任何生产写入、服务重启、Git commit、push、PR 合并或密钥轮换。线上只做了只读检查；本地只做了上述 4 个小修复、测试、状态文件更新和本交接文档。

## 12. 2026-07-11 官网 P0 恢复记录

- 根因：`site/index.html` 导航引用了大量 `/docs/*.md`，但本地与 VPS 都只剩 6 份文档；历史提交 `55cc420` 删除了 34 份站点文档，后续未完整恢复。
- 生产备份：`/root/Backups/structural-site-20260711-171500`。
- 现场回滚目录：`/root/Projects/structural-isomorphism/site.predeploy-20260711-171500`。
- 恢复 34 份历史 Markdown，修正脱敏脚本误伤的 `#`，与现有 6 份合计 40 份。
- 移除 3 个从未存在内容源的导航项：`v1-vs-v2-comparison`、`v2-expanded-final-ranking`、`v2-expanded-screening`。
- 新增 `scripts/check_site_docs.py`，部署前 fail closed 检查缺失文档、孤立文档、重复 slug、首页快捷入口和残留脱敏标记。
- `.gitignore` 已放行 `site/index.html` 和 `site/docs/*.md`，避免重新 clone 后再次丢失内容。
- 本地 HTTP 验收：40/40 文档返回非空 200，不存在文档返回 404，5 个首页快捷入口通过。
- 生产验收：文件 checksum 通过，nginx `-t` 通过，经真实 nginx/TLS 路由验证 40/40 文档为非空 200，缺失文档为 404。
- 浏览器自动化当时无可用实例，未产生点击截图；服务器端全量内容验收已完成。

## 13. 2026-07-11 beta / Phase 生产 P0 恢复

### beta Structural Search

- 新增权威 artifact manifest：`artifacts/production-v2-4443.json`，artifact id 为 `structural-v2-kb4443-20260711`。
- 生产 artifact 版本目录：`/root/structural-artifacts/releases/structural-v2-kb4443-20260711`；`current` 为原子 symlink。
- 恢复 4,443 条真实 KB、`4443 x 768 float32` embeddings 和 checksum 匹配的 `structural-v2`。
- 启动前强制检查 LFS pointer、row/unique id、embedding shape/dtype、KB/embedding/model checksum 和 manifest 路径边界。
- deep health 在空 KB 或未验证 artifact 时返回 503；生产实测为 `status=ok`、`kb_size=4443`、`embedding_shape=[4443,768]`。
- 部署 readiness 改为最长 120 秒轮询，失败自动恢复 previous SHA 和 `.env.runtime`。
- 5 条固定中文查询均返回非空结果且有跨域候选；其中“月活流失”的 Top 3 相关性仍偏弱，属于后续产品质量 P1，不是可用性 P0。
- 生产备份：`/root/Backups/structural-beta-p0-20260711-190000`。

### Phase Detector API

- 新增独立精确锁定依赖，包含 `PyYAML==6.0.3`、`python-multipart==0.0.20` 和 Postgres driver。
- VPS forced-command 入口已改为委托仓库内 `scripts/deploy-phase-detector-vps.sh`，每次安装 API 依赖、import smoke、build、重启 API/Web 并验证真实 endpoint。
- beta / Phase 共享 VPS Git 工作树的竞争已用 `/var/lock/structural-isomorphism-deploy.lock` 串行化。
- nginx 修复 `/api/` 前缀被 trailing-slash `proxy_pass` 剥离的问题；权威配置为 `web/phase-detector/phase.bytedance.city.nginx.conf`。
- 生产 `/api/health` 和 `/api/ews/meta` 均返回 200；EWS meta 为 597 tickers，`price_provenance=demo`。
- GitHub Deploy Phase Detector 最终 workflow 全绿，types-sync 亦已恢复。
- 生产备份：`/root/Backups/phase-api-p0-20260711-190000`。

### 提交

- `8d95595` `fix(beta): validate production artifacts fail closed`
- `502f5a5` `fix(phase): deploy API with locked dependencies`
- `104642b` `fix(deploy): serialize shared VPS worktree`
- `2d6fd55` `fix(ci): deploy tracked Phase script changes`
- `8162798` `fix(phase): preserve API prefixes in nginx`

上述 commit 已 push `origin/main`。原先 4 个本地修复仍保持未提交，没有混入这批 P0 commit。密钥撤销/轮换仍需在对应服务商控制台完成。

## 14. 2026-07-11 P1 自动驾驶交接（最新状态）

> 本节是当前最新状态，优先级高于前文“P0 尚未执行”等历史措辞。
> 本轮因 context 临近上限主动停止，**未 commit、未 push、未部署**。

### 已完成

1. 建立检索评测资产：
   - `evaluation/retrieval-v1.jsonl`：100 条、50 组中英配对；80 条 in-scope、20 条 OOS。
   - `evaluation/qrels-v1.jsonl`：DeepSeek Reasoner 官方 API 判定的 400 条候选级 graded qrels，相关度 0–3，严格 query/doc allow-list。
   - `scripts/build_retrieval_eval.py`：确定性生成器。
   - `scripts/evaluate_retrieval_v1.py`：本地/线上评测，含 OOS、Hit/MRR、双语 Jaccard、graded nDCG。
   - `scripts/judge_retrieval_qrels.py`：provider 可配置、3 次重试、输入 fingerprint、resume 校验、原子写入。
   - `evaluation/results/retrieval-v1-graded-baseline.json`：冻结基线报告。
2. 当前 production-v2-4443 基线：
   - graded `nDCG@5 = 0.5786`
   - graded `Success@5 = 0.6125`
   - 中文 type Hit@5 `0.575`
   - 英文 type Hit@5 `0.025`
   - 中英 Top-5 type Jaccard `0.0351`
   - OOS precision / recall / reason accuracy / strict refusal 均为 `1.0`
   - 结论：OOS 已可靠；英文检索是当前最大产品缺口；type_id 与根目录 `taxonomy-v1.md` 存在历史污染，不能拿 type 指标冒充真实相关性。
3. 共享 scope guard 已新增算术、闲聊、事实查询、预测、空白/纯符号拒绝，并补真实结构问题负例；修复了 search/ask/analyze 范围策略分裂的一部分。
4. CI：
   - `make test-retrieval-contract`
   - `.github/workflows/ci.yml` 新增离线 retrieval contract job
   - 移除 backend integration 的 `|| true` 假绿
5. 页面 P0 诚信修复：
   - Phase 覆盖统一为“597 个 ticker 的 demo 研究快照”，不再宣称每日 1000+ / 实时市场数据。
   - `/checkout/mock` 改为研究预览登记；beta 与 Phase 定价页不再模拟购买成功。
   - billing 默认 fail closed，新增 `BILLING_ENABLED`；events endpoint 加 admin token。
   - 深路由语言切换不再生成不存在的 `/zh/*` 404。
   - 两站隐私联系人统一为角色邮箱，移除 mock checkout 无限期保留等陈旧声明。
   - Phase pricing、FAQ、RSS、PWA、about、methodology、company 等页面同步修正。
6. API/模型盘点：
   - VPS Structural `.env` 中 OpenRouter 主/备 key 均能列出 345 模型；真实调用 Claude Opus 4.8 和 Sonnet 5 返回 200。`/root/.bashrc` 另有一枚陈旧 OpenRouter key，真实调用 401，不能混用。
   - EasyRouter 配置在本机 `~/Vault/重要信息/easyrouter.md`，但 `api.easyrouter.io` 在本机与 VPS 均无法解析，当前不可用。
   - BAI 未在本机/VPS常规 secrets、Vault、shell、systemd、项目配置中定位到。
   - DeepSeek 官方 key 已恢复充值，Reasoner 真实调用 200，并用于 qrels。
   - 火山 ARK key 可列 126 模型，但账户 overdue，Seed 2.0 Pro 推理返回 403；未用于最终判定。

### 已验证

- `make test-fast`：299 passed，27 deselected（仍有 128,533 warnings）。
- `web/backend` 全量：847 passed，1 skipped，4,018 warnings。
- Phase production build：29/29 routes 成功，已修 compare hook warning 后应再跑一次最终 build。
- retrieval contract：5 passed；相关目标回归 67 passed。
- `git diff --check`：通过（最后几处修改后需再跑一次）。
- 内置浏览器 runtime 无可用 browser（`agent.browsers.list() == []`），因此尚未完成真实点击/截图；不能把 build 当成浏览器验收。

### 第二轮独立 Validator 剩余 blocker（提交前必须修）

1. `scripts/evaluate_retrieval_v1.py` 尚未消费并验证 qrels 中的 dataset/KB fingerprint；同 ID 内容变化时可能静默复用旧 qrels。必须 fail closed。
2. `web/backend/api/billing.py::_verify_signature` 不是完整 Stripe 算法：真实 Stripe v1 应验证 `timestamp + '.' + raw_payload` 并检查时间容差，或直接使用 `stripe.Webhook.construct_event`。当前 `BILLING_ENABLED=true` 时真实 webhook 会失败。
3. `scope_guard.py` 食谱 regex 仍可能误伤“菜鸟团队遇到增长瓶颈应该怎么做”；移除单字“菜/饭/面/蛋”等宽匹配，补该负例；同时补“茅台涨到多少”预测拒绝。

### 工作树与提交边界

当前约 42 个已修改文件 + 新增 `evaluation/`、3 个评测脚本和 contract test。不要一次混成一个 commit，建议：

1. `fix(core): align model defaults and scope guard`
2. `feat(eval): add bilingual retrieval benchmark and graded qrels`
3. `fix(billing): fail closed until paid entitlements launch`
4. `fix(phase): align public claims with demo provenance`
5. `ci: gate retrieval contracts and integration failures`
6. `docs: refresh the single session handoff`

提交前先看：

```bash
cd /Users/dadamini/Projects/structural-isomorphism
git status --short
git diff --check
git diff --stat
```

### 下一会话严格顺序

1. 修完上面 3 个 Validator blocker并补测试。
2. 重跑 retrieval contract、backend 目标测试、backend 全量、`make test-fast`、Phase `pnpm build`。
3. 做 route-matrix HTTP 验收；如浏览器恢复，再做关键路由点击与截图。
4. 按上述 6 个边界提交；确认 staged files 后 push `origin/main`。
5. Phase 页面变更会触发 deploy workflow；billing/scope/backend 变更会触发 beta deploy。监控两个 workflow 到全绿。
6. 线上复核 beta deep health、20 条 OOS、5 条中文 + 5 条英文检索、Phase 关键路由和 provenance 文案。
7. 最后再追加本文件与 `~/progress.md`，记录 commit、workflow、生产验收和回滚。

## 15. 2026-07-11 P1 完成交付：双语评测、模型接入、生产收口

### 最终状态

- 本节取代第 14 节的“未提交、未部署”状态；第 14 节保留为过程记录。
- 100 条中英双语检索评测集、400 条 graded qrels、评测器、冻结基线与 CI contract 已提交并推送。
- beta 后端与 Phase 站已部署；生产 beta 使用 `openai/gpt-5.6-luna-pro`，配置与仓库默认一致。
- 工作树干净；代码与本交接文档均已提交并推送。

### Validator blocker 收口

1. qrels consumer 已强校验 schema、judge model、dataset/KB/results SHA-256、query/doc 完整覆盖；输入漂移时 fail closed。
2. Stripe webhook 已按 `timestamp.raw_payload` 验证、多 `v1` 支持并执行 300 秒容差；billing 默认 fail closed。
3. scope guard 已修复食谱、股价预测与结构分析误拒绝，并防止 `predict/guaranteed` 借“机制分析”绕过。
4. 第三轮独立 Validator 对前两项确认通过；最后一项经两轮对抗用例修复并在线复验。

### 最终本地验证

- `make test-fast`：299 passed，27 deselected。
- `web/backend` 全量：857 passed，1 skipped，4,021 warnings。
- billing/scope/qrels 目标集：105 passed；最终模型配置目标集：30 passed。
- retrieval contract：6 passed。
- Phase `pnpm build`：29/29 routes。
- graded direct eval：100/100 query、400 judgments、0 request error；`nDCG@5=0.5786`、`Success@5=0.6125`。
- `git diff --check` 与两条 workflow YAML 解析通过。

### API 与模型最终决策

- OpenRouter：VPS 项目主/备 key 可用；模型目录 345 个。Claude Opus 4.8、Sonnet 5 与 GPT-5.6 Luna Pro 均真实调用 200。
- 最终按质量优先选择 `openai/gpt-5.6-luna-pro`；OpenRouter 返回的实际版本为 `openai/gpt-5.6-luna-pro-20260709`。
- Luna Pro 生产 Ask 实测 HTTP 200、约 11.3 秒完成；同题 Opus 4.8 对照约 14.3 秒。
- EasyRouter：`api.easyrouter.io` 在本机与 VPS 均 DNS 失败，不接入。
- BAI：未在本机/VPS 的常规私有配置位置定位到，不虚构接入。
- DeepSeek 官方：Reasoner 真实调用 200，已用于生成 400 条 qrels；保留为评测/国内模型能力，不替代当前生产主模型。
- ARK：能列模型但账户 403 overdue，未接入。
- VPS 模型配置回滚：`web/backend/.env.pre-luna-pro-20260711-2110`；更早 Opus 前备份为 `.env.pre-opus-20260711-2058`。两者权限 600，文档未记录任何密钥值。

### 提交

- `1789782` — retrieval defaults 与 scope guard
- `85cfe09` — 双语 graded retrieval evaluation
- `f9ceb57` — billing fail closed 与 Stripe webhook
- `e342bbb` — 公网页面生产事实对齐
- `edbdf7b` — retrieval contract CI
- `5d12e2f` — legacy checkout 标准 HTTP redirect
- `15def22` — GPT-5.6 Luna Pro 权威默认与测试隔离
- `d184fd3` — deploy fingerprint 从单一权威配置读取

### 部署与线上验收

- Beta workflow `29153946442`：success；deploy、deep health、artifact、5 条语义 smoke、commit/model fingerprint 全部通过。
- Phase workflow `29153475201`：success；构建、SSH deploy、API smoke 通过。
- CI `29153475194`、sanity `29153475198`、Coverage `29153475222`、types-sync `29153475249`：success（对应页面重定向提交）。
- beta `/api/version`：`git_sha=d184fd303e6b`、`model=openai/gpt-5.6-luna-pro`。
- beta deep health：4443 KB、`[4443,768]`、artifact `structural-v2-kb4443-20260711`，所有 checks 为 ok。
- beta billing checkout：503 `billing_not_available`，不存在假支付成功。
- beta scope 在线正负例：明确预测/保证上涨均拒绝；“比特币与银行挤兑的结构类比”等核心分析请求正常返回 12 条候选。
- Phase 权威域名为 `https://phase.bytedance.city`；主页、zh、companies、pricing、privacy、about、methodology、newsletter、compare、health、EWS meta 均 200。
- Phase 展示 `597`、`demo snapshot`、`research preview/Planned`；EWS meta 为 597 tickers、`price_provenance=demo`。
- `/checkout/mock` 现为 HTTP 308，`Location: /newsletter?source=legacy-checkout`。

### 唯一已知非本目标红灯

- `perf budget` workflow `29153475238` 失败：移动端 3 个 LCP（2692/3020/2800ms）与 5 个 `INP*` 超预算。
- 该红灯在本轮前的 `8162798` 也已存在，不是双语评测、billing、scope 或模型切换引入；当前 audit 仅单次运行，且 `INP*` 把加载期 worst LoAF 当成交互延迟，口径存在系统性偏差。
- 不应放宽预算或添加豁免来假绿。下一阶段应先修 audit 为交互窗口测量并使用多次中位数，再针对 companies/company/compare 的真实移动 LCP 优化。

### 下一阶段优先级

1. P1 检索质量：优先解决英文检索（英文 type Hit@5 仅 0.025），禁止只调 taxonomy 指标冒充真实相关性提升。
2. 用冻结 qrels 做 rerank/多语 embedding 实验，以 nDCG@5、Success@5 和 bilingual consistency 为准。
3. 修复 perf audit 测量口径后，再做真实移动端性能优化。
4. 浏览器 runtime 本轮仍无可用实例；页面已做 source/build/HTTP route matrix 验收，但没有截图式视觉验收。
