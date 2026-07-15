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

## 16. 2026-07-11 全项目审计与 P2 自动驾驶（进行中）

> 本节是当前最新运行状态，优先级高于前文。
> 用户已明确授权本项目持续自动驾驶；上下文接近 90% 时必须先追加本文件，compact/新 Session 后第一步完整重读本文件。

### 已完成审计

- 产品、学术、工程三路独立审查完成，汇总文档：`docs/audit/project-audit-2026-07-11.md`。
- 主产品路线收敛为 Validated Transfer Workbench；Phase Detector 保持 597 ticker demo/null-result 研究预览定位。
- 学术路线收窄为 reject-aware 方法论与 3–4 个真实系统的 scaling concordance；不再把 synthetic anchors 包装成普适机制确认。
- README 中英文、model card、dataset card 已对齐 4,443 KB、597 demo、英文质量缺口、历史 embedding 评测泄漏与 reviewer-readable/do-not-submit 边界。

### 已完成实现与提交

- `e72529b` `fix(perf): measure trusted interactions fail closed`
  - 性能 audit 改为真实 Playwright click、Event Timing interactionId、交互窗口 LoAF、页面稳定 selector、部分轮失败 fail closed、CI 3 次中位数。
  - 本地 CI 同构 `/company/AAPL` 移动 3 次中位：LCP 2464ms、INP proxy 40ms；旧脚本同场景错报 0ms。
- `1d36007` `ci: make release gates fail closed`
  - cross-judge/frontend/coverage/E2E 移除假绿 `|| true`；reject-aware-critic 纳入 CI；外网 E2E 用 job-level non-blocking 显示真实失败；新增 `make verify-release`。
- `64ce1f7` `fix(prod): retire unfinished account and legacy phase surfaces`
  - 生产缺失/弱 JWT secret 硬失败；Auth/Connections/云 Favorites 默认 503；beta legacy `/phase/api/*` 410，旧 Phase 页面 308 到权威域；Phase 前端隐藏未开放登录。
  - backend 全量：859 passed，1 skipped；Phase lint/build 29/29 routes。
- `065f96d` `eval: measure English translation rerank signal`
  - 固定旧 judged Top-5 池：英文 nDCG@5 0.3029，paired Chinese reference proxy 0.4041，RRF 0.3846。
  - paired delta 均值 0.1012，bootstrap 95% CI [0.0313, 0.1738]；15 正/22 零/3 负；只有 27.5% 旧池含 relevance>=2，因此不宣称端到端 recall 提升。
- `b080df8` `ci: monitor production business invariants`
  - 新增三站 fail-closed 合成监控：docs、version/deep health/artifact、5 中+5 英、20 OOS、billing/auth 503、Phase health/meta/provenance、route matrix。
- `ff9af1e` `docs: align product and research claims with evidence`
  - 新增全项目审计与 P0/P1/P2 验收路线。
- `51eec84` `ci: install canonical backend coverage dependencies`
  - 首次 fail-closed coverage 暴露缺 sentence-transformers/jieba/rank-bm25/multipart 和 LFS；已改为权威 backend requirements + LFS checkout。新 workflow `29155228893` 已 success。
- `6839d7e` / `cf64648` / `453e53b`
  - 生产 smoke 低于 30/min 限流节流，增加阶段进度，并区分公开 route 与退役 beta pricing route。
- `030d376` / `78da9d5`
  - 英文 Top10 + paired Chinese reference Top10 扩展候选池：40 queries、794 query-doc，复用旧判定 200，需新判 594；全部绑定 dataset/KB/model/embedding/code/git/artifact 指纹。
  - 判定器支持 strict allow-list/schema/resume/原子写，但真实 DeepSeek 调用被运行环境以“向外部第三方导出大量 query/document”为由硬拒绝，不得绕过。

### 当前外部状态

- push 到 `origin/main` 的最新 SHA：`78da9d5`（后续本地还有新 commit，见 `git log`）。
- `78da9d5` CI `29155228888`、Coverage `29155228893`、sanity `29155228897`、types-sync `29155228892`、beta deploy `29155228918` 已 success。
- perf `29155228884` 仍在运行 10 pages × 2 viewports × 3 runs；必须监控到结束，不放宽预算。
- 完整生产 smoke 已通过 docs、deep health、中英检索、20 OOS、Auth/Billing、Phase provenance；在 beta `/pricing.html` 发现 404。核对后确认该文件是未公开/退役付费表面，监控已改为检查 `/start-here` 并显式要求 `/pricing.html` 保持 404。

### 当前工作树与进行中实验

- 本地已新增未提交 `scripts/experiment_multilingual_embedding.py` 与测试，默认纯离线，只有显式 `--allow-model-download` 才下载公开模型；查询/KB 始终本地编码。
- 正在下载并实验 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（471MB）；模型官方 card 声称支持 50 种语言。完成后必须记录 cache tree hash、fixed-pool nDCG/MRR/Top1、全 50 对中英 Top5 doc Jaccard 和不可比边界。
- 生产 smoke route 修正与多语实验完成后，需分 commit、push，再手动触发 `site-smoke.yml`。

### 严格下一步

1. 等待本地 MiniLM 下载/编码完成，独立复算结果；若无明确增益，不改生产检索。
2. 监控 perf `29155228884` 到结束；如失败，下载 audit artifact，分离测量错误与真实 LCP 红灯。
3. 提交/push 当前 smoke route 修正和多语实验，监控新 CI/coverage/perf。
4. 手动触发 site smoke，必须 51 个请求全通过。
5. 线上复核 `/api/version`、deep health、Auth 503、legacy Phase 410/308、Phase 597/demo 与关键路由。
6. 不在没有 expanded judgments/人类复核的情况下上线 translate-before-retrieve 或宣称英文 recall 提升。
7. 最后追加本节与 `~/progress.md`，记录最终 commit、workflow、生产 smoke、回滚与剩余 P1/P2。

## 17. 2026-07-11 P2 自动驾驶续航：英文实验与真实性能门禁

> 本节是当前最新权威状态，优先级高于第 16 节。上下文接近 90% 时已按用户要求主动交接；compact 后必须先完整重读本文件再继续。

### 已完成

- `453e53b` 修正生产 smoke 的公开/退役 beta route；手动 `site smoke` workflow `29155810650` 已 success，51 个生产请求全通过。
- 线上复核：beta `78da9d5`、4443 KB、`[4443,768]`、Auth 503、legacy Phase API 410、legacy Phase 页面 308；Phase 为 597 ticker、`price_provenance=demo`。
- `a4f09b4` / `446282a` 新增本地多语 MiniLM 实验、结果、测试与完整复现 provenance：
  - 模型：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`，本地缓存内容寻址；查询/KB 未外发。
  - 旧英文固定 Top5 判定池：nDCG@5 `0.302861 -> 0.397643`，MRR `0.129583 -> 0.18`，Top1 `0.05 -> 0.125`。
  - 50 对中英 Top5 mean Jaccard `0.342381`；Top50 union 平均 71.2 个未判定文档。
  - 两次离线结果逐字节一致；独立 Validator 对实验与 provenance PASS，但对上线 NO-GO：无 expanded human/heterogeneous judgments、holdout、中文 nDCG 回归、真实 endpoint/OOS/延迟并发门禁。
- 性能脚本补丁已真正落盘并多轮校正：
  - `2ee7bbd` 响应式可见导航交互，去掉永不满足的 Next.js `networkidle`；单页双视口从约 39 秒降到约 8 秒。
  - `2acc791` 隔离已有独立交互测试的 onboarding/cookie 首访覆盖层，并记录 LCP 文本节点。
  - `24f0bf9` 移除 LCP 前的程序化滚动；移动图例/说明去重、TLDR 响应式收敛、companies 初步拆包。
  - `a479518` companies 下折叠视口懒加载，移动 chart/compare 重复长文隐藏；Phase lint 与 29/29 build 通过。
- 所有上述 commit 已 push `origin/main`。本地关键页多次中位复测通过预算，但 GitHub runner 暴露出更慢的真实边界，未放宽预算。

### 当前唯一红灯与证据

- 最新权威 perf workflow：`29157003952`，20/20 页面/视口均成功测量，失败仅剩：
  - companies mobile LCP `2608 > 2600ms`，TBT `277 > 200ms`；
  - company/AAPL mobile LCP `2784 > 2600ms`，LCP 节点为 actionable 说明；
  - compare mobile LCP `2640 > 2600ms`，LCP 节点为页面 intro；
  - 其余页面、CLS、INP 均通过。不要改预算或排除这些业务内容。
- 最新 SHA `a479518` 的 CI/Coverage/sanity/types-sync/Phase deploy/docs deploy 在本节写入时仍运行或排队；必须监控到终态。
- 本地仅 `NEXT_SESSION.md` 有未提交交接修改；本地 Phase 测试 server 可能仍在 3017（session 13124），结束前关闭。

### 严格下一步

1. 完整重读本文件并检查 `git status/log`、最新 workflows。
2. 对 companies TBT 做组件级 profiler/长任务定位；当前 IntersectionObserver 仍使首屏 leaderboard 立即加载，不能靠固定延迟逃避 TBT。
3. 把 company/compare 首屏关键数据改为服务端可渲染或内联到初始 payload，消除 hydration 后晚到文本；不要继续用 CSS 隐藏核心内容。
4. 每次修改先本地关键页 3-run，再跑最终 GitHub perf；预算保持原值。
5. 最新 Phase deploy 成功后重新触发 `site-smoke.yml` 并做关键路由 HTTP/视觉验收。
6. perf 全绿且 CI/部署/smoke 全绿后，追加本节最终状态与 `~/progress.md`，提交交接文档并 push。
7. 英文检索下一步只做本地 expanded candidate judgments / human review 设计；不得向第三方批量导出 594 个 query-doc，也不得据当前 fixed-pool 信号上线模型。

## 18. 2026-07-11 最新生产与门禁终态

> 本节补充第 17 节写入后的终态；第 17 节仍是完整技术交接。

- 最新代码 SHA：`a479518`；CI `29157003924`、Coverage `29157004004`、types-sync `29157003992`、Phase deploy `29157003931`、docs deploy `29157003980` 均 success。
- 部署后生产业务 smoke `29157197712` success，51 个请求全通过。
- sanity `29157003962` 仍在运行；perf `29157003952` 为唯一失败，20/20 测量完整，精确剩余：companies mobile LCP `2608 > 2600`、TBT `277 > 200`；company/AAPL mobile LCP `2784 > 2600`；compare mobile LCP `2640 > 2600`。
- 不得放宽预算。下一轮从 server-rendered/initial payload 与首屏组件 profiler 入手；当前 CSS 隐藏和 IntersectionObserver 优化已经消除重复说明，但不能替代首屏数据架构修复。
- 本地交接文档待提交；本地测试 server session `13124` 应关闭。

## 19. 2026-07-12 P0/P1/P2 产品闭环与邮箱认证交付

> 本节是当前最新权威状态。代码与生产部署已完成；最终长时 CI/性能门禁仍在运行，下一节应记录终态。

### 已实现并推送

- `2ee2f56`：工作台改为“用户确认结构指纹 → 显式选择候选 → 证据/反证 → 结构化最小实验 → 结果回写”；禁止默认选择 Top 1。
- `a967889`：新增 594 条 expanded candidate 的本地盲审工具、断点续标、严格导入/导出、三标注者一致性与仲裁队列；未伪造人工标签。
- `d555378`：新增 claim-evidence ledger 和 fail-closed 研究门禁；修正 WTO 数值置信区间为显著负向但符号反转的诚实结论。
- `ee0cfd4`：修复公开页面死入口、Phase Explore 链接、onboarding 服务端请求、收藏文案与远程 Google Fonts 构建依赖。
- `6eb6f77`：实现邮箱 magic-link 注册/登录、HttpOnly session、token 单次事务消费、持久化用户与 durable 管理员通知 outbox、限流、撤销、SMTP 后台重试和生产 fail-closed。
- `332c266`：新增全站路由矩阵、工作台真实浏览器核心旅程和产品/研究契约；本地核心旅程在 CI 中 fail-closed。
- `285be50`：CI 产品门禁 checkout 权威 Git LFS KB，修复干净 runner 只拿到 pointer 的问题。

### 验证与部署

- 本地 backend：`890 passed, 1 skipped`。
- 本地根测试：`299 passed, 31 deselected`；产品/研究契约 `17 passed`；Phase lint 和 29/29 production build 通过。
- GitHub fail-closed browser product contract 已通过；LFS 修复后的 retrieval/product/research contract 已通过。
- Beta deploy `29162301984` success；线上 SHA `332c266`，4443 KB、`[4443,768]`、Luna Pro、artifact checks 全部正常。
- Phase deploy `29162301553` success；线上 health 200、EWS 597 ticker、`price_provenance=demo`。
- 生产认证保持 `NEXT_PUBLIC_AUTH_ENABLED=false`；`/api/auth/me` 返回 503 `auth unavailable`，避免没有发信能力时暴露半成品入口。

### 唯一外部上线 blocker

- 当前本机、VPS 与腾讯 SES 均没有可用已验证发信身份/SMTP 配置；腾讯 SES 创建身份受到账号侧 domain limit 拒绝。
- 因此注册登录代码可部署但不能安全启用。启用前需要真实私有 `JWT_SECRET`、SMTP 配置和 `ADMIN_NOTIFICATION_EMAIL`；部署会拒绝公开占位/低熵 JWT、非 600 env、仓库内数据目录或不匹配的 systemd EnvironmentFile。
- 启用后必须完成真实邮箱收信、管理员通知、token 重放拒绝、服务重启持久化和 SMTP 失败重试五项生产验收。

### 仍在运行

- 当前最新 SHA `285be50`：CI `29162357905`、Coverage `29162357901`、sanity `29162357956`、perf `29162357899` 仍在运行；types-sync `29162357906` 已 success。
- 全部终态后触发 `site-smoke.yml`，复核全站路由并追加下一节；不得把运行中写成已通过。

## 20. 2026-07-12 性能与生产最终收口

> 本节取代第 19 节“长时门禁仍运行”的过程状态。

- `1d60c56` 修复 Phase 移动端稳定 CLS：自托管字体从 `display: swap` 改为 `optional`，保留快缓存品牌字体并避免慢首访后换字重排。
- 首轮失败证据为 backtest mobile CLS 三次均 `0.1141`、about mobile 三次均 `0.2393`；不是随机噪声。修复后 perf workflow `29162628931` 对 10 页 × 2 视口 × 3 runs 全部通过，预算未放宽、内容未隐藏。
- Phase deploy `29162628915`、types-sync `29162628927`、docs deploy `29162628892`、Coverage `29162628887` 均 success。
- 部署后生产 smoke `29162780942` success；beta/Phase 深度健康、搜索/OOS、597 demo provenance、认证关闭态与全部业务不变量通过。
- CI 的 live soft-fail E2E 曾在 Phase 部署切换窗口捕获 `/company/AAPL` 单次 502；同 job 其余 28 项通过，部署后 smoke 未复现。route matrix 已增加最多 3 次有限 5xx 重试（1s/2s），持续失败仍 fail closed。
- 本轮交付的代码级 P0/P1/P2 已完成；不可自动完成的剩余项只有真实人工标注/外部学术 review，以及账号侧可用 SMTP/已验证发信身份。注册登录必须继续关闭，直到具备真实私有配置并完成五项生产验收。

## 21. 2026-07-12 多专家复审、证据安全与生产邮箱认证

> 本节是当前最新权威状态，取代第 20 节“认证仍关闭”的状态。用户再次确认：context 接近 90% 前主动追加本文件；compact 后第一步完整重读。

### 多角色复审结论

- 资深 PM/UX：首发 ICP 收敛为研究密集型 PM/增长负责人；北极星建议 Weekly Verified Transfer Outcomes。发现 Phase 冻结 demo/NULL 回测与 alpha/本周信号冲突、beta 597/耗时/机制文案漂移、报告默认持久化隐私风险。
- 资深 QA/安全：复现公共报告读者可伪造 `worked` followup 并污染 verified evidence；发现 Phase 隐私披露落后于邮箱账户、登出与收藏批量删除假成功、生产监控未覆盖认证开启态。
- 资深研究员/复杂系统科学家：当前投稿 NO-GO；高价值路线应收缩为 reject-aware、可追溯的跨域 scaling 协议与负结果。发现 manuscript 强 claim 可绕过 ledger，以及 Schelling taxonomy REJECT 与稿件 PASS 冲突。

### 已修复并推送

- `6ae5042`：manuscript Abstract/Contributions 强 claim 与 ledger 双向 inventory/hash 门禁；新增 Schelling taxonomy/WTO submission-blocking conflict，强制排除 universality PASS 计数。
- `c15cf2b`：有 owner 的报告只允许 owner followup；所有 verified/count/stuck/insights 证据聚合只接受 creator 自己的结果，DB 绕过攻击也不计入。
- `0f90b57`：Phase 统一为 597 frozen demo + published NULL + 无预测能力；删除 alpha/本周翻转/可购买 Offer，Pricing 改未开放状态；beta 统一 597、2–3 分钟和机制仍需验证。
- `2e2a657`：Phase 隐私页披露邮箱账户、token hash、SMTP、HttpOnly session；登出失败保留会话并提示；收藏部分删除不再假成功；生产认证开关启用。
- `46494e9`：报告 persistence/share capability 默认关闭，用户生成前必须显式勾选保存与持链可读链接。
- `16fb749`：生产 smoke 新增 Phase auth enabled/no-session 401 门禁；总请求数 52。

### 本地验证

- backend：`892 passed, 1 skipped`；owner/evidence/report/auth 目标集与对抗测试通过。
- root：`299 passed, 31 deselected`。
- 产品/研究契约：`24 passed`；production smoke unit：`13 passed`。
- Phase lint 与 production build：29/29 routes。
- `git diff --check`、Node syntax、Ruff、TypeScript 均通过。

### Resend、DNS 与生产认证终态

- Resend 域名 `auth.bytedance.city`：DKIM、SPF MX、SPF TXT 均 verified；区域 `ap-northeast-1`。
- DNSPod 记录已创建：`resend._domainkey.auth` TXT、`send.auth` MX/TXT。
- VPS 私有配置：`/root/.config/structural-isomorphism/phase-auth.env` mode 600；systemd EnvironmentFile 已加载；用户/会话数据在 `/var/lib/structural-isomorphism/auth`，位于 Git 外。
- 生产仅保留 send-only Resend Key；两枚临时 Full Access Key 已通过 API 撤销，本机临时管理 secret 与验收文件已删除。
- 真实验收：SMTP 测试邮件 delivered；Magic Link delivered；首次兑换 200；`/me` 200；token 重放 400；API 重启后会话仍 200；新增用户管理员通知 delivered。
- SMTP 临时失败/outbox retry 由并发/失败单测覆盖，未故意破坏生产网络演示。

### 部署与剩余运行项

- beta deploy `29163928489` success；Phase deploy `29163928490` success；对应 CI、perf、types、docs 已 success，Coverage/sanity 长任务仍需看最新提交终态。
- 最新 SHA `16fb749` 的 CI `29164150070`、Coverage `29164150101`、sanity `29164150068`、perf `29164150087` 正在运行；types `29164150086` success。
- 最终 production smoke `29164170117` 已触发，必须等到 success；不得把运行中写成完成。

### 后续仍需推进

- 产品：候选选择前补结构匹配证据/反证/适用边界；报告列表升级为 Today/This week/Waiting/Completed；首值 p75<10s；真实 ICP 15–20 个任务。
- 研究：594 expanded candidates 需真实多标注者；WTO cluster bootstrap/LOO/Firth或Bayesian sensitivity与独立双人编码；外部复杂系统统计 reviewer。
- QA：真实 Next + API 的 auth/favorites 浏览器链路、375/390 移动键盘/axe 矩阵、Phase 全控件行为 inventory；静态 154 controls 不得宣称等价于每个按钮行为已验证。

## 22. 2026-07-12 产品决策闭环、真实浏览器门禁与研究 P1 终态

> 本节是当前最新权威状态。可自动完成的工程、产品体验、安全、性能、部署和生产验证已经收口；后续工作进入真实用户研究与独立人工评审阶段。

### 产品与体验

- `8702521`：报告列表升级为“今天 / 本周 / 等待推进 / 已完成”行动队列。
- 候选选择前展示结构匹配线索、来源摘要、反证/缺失证据和适用边界。
- “相似度百分比”改为不暗示成功概率的“检索分”；所有候选明确为检索线索，不是因果或迁移验证。
- 不新增 LLM 调用，不增加模型首值延迟。

### 认证、全控件与无障碍

- `f556266`：真实 Next + FastAPI + Playwright 门禁发现并修复两个 P0：
  1. Next App Router 拦截 `replaceState`，导致 token 参数消失并取消兑换；
  2. React StrictMode 重跑 effect，导致一次性 token 被并发 POST 两次。
- 修复为原生 History URL 清理与按 token 复用同一兑换 Promise。
- 真实门禁覆盖 Magic Link 单次兑换、HttpOnly Cookie、刷新后 `/me`、登出 503 保持会话、收藏部分失败、375px 键盘/axe，以及 23 个公开路由 × 375/390 的可见控件名称与键盘可达性。
- clean runner 先后暴露 axe 本机隐藏缓存和通用 `role=alert` 二义性；远端 `a4201b1` / `a4706e2` 已修复为已安装 axe-core 与精确业务提示定位。

### 研究 P1

- `324c914`：594 条英文盲审增加投稿级门禁：至少 3 名 reviewer、每任务至少 3 份评价、仲裁清零、平均 quadratic-weighted kappa ≥ 0.67；当前无人类标签，因此不会误报 publication-ready。
- WTO 23 行按政策事件合并为 17 clusters，执行 2,000 次确定性 cluster bootstrap 和 17 次 leave-one-cluster-out。
- 结果只支持“负斜率符号在聚类与 LOO 敏感性中仍存在”：bootstrap `k` 95% CI `[-94.23, -0.107]`，97.88% 有效样本为负，17/17 LOO 为负；4.28% 出现 `|k| > 20` separation 极端尾部，因此禁止精确效应量和因果表述。
- 已生成 23 项独立双人编码包，不泄露现有 stage/score/outcome，不自动裁决分歧。

### 最终验证

- 本地 backend：`894 passed, 1 skipped`；root：`299 passed, 32 deselected`。
- 研究目标集：`21 passed`，claim gate PASS；产品/相关目标集通过。
- 真实浏览器：auth/mobile/axe/control `7 passed`；公开页面/工作台 `5 passed`。
- Phase lint、TypeScript 和 29/29 production build 通过。
- GitHub SHA `a4706e2`：CI `29167564785`、sanity `29167564782`、Coverage `29167564756`、types `29167564752`、perf `29167564751` 全部 success。
- 最终 production smoke `29168304570` success，52 项 fail-closed 请求全部通过。
- beta 生产保持 4,443 KB、`[4443,768]`、权威 artifact 与 Luna Pro；Phase 保持 597 frozen demo、published NULL、认证开启且未登录 `/api/auth/me = 401`。

### 只剩真人/外部工作

1. 594 expanded candidates 的 3 人独立盲审、仲裁和 holdout 评测。
2. 15–20 个真实研究密集型 PM/增长任务，验证候选接受率、术语理解与 Weekly Verified Transfer Outcomes。
3. WTO 两名贸易法领域独立 coder、第三名仲裁者、政策 cluster 定义复核，并用最终仲裁数据重跑。
4. 外部复杂系统/统计 reviewer；在完成前论文继续保持 submission NO-GO。

### 接力注意

- GitHub HTTPS/CLI 曾被失效代理 `127.0.0.1:7890` 间歇阻断；两次小修复通过 GitHub Connector 写入远端，因此本地等价提交 SHA 与远端 `a4201b1` / `a4706e2` 不同。
- 下一会话先 fetch 并按内容安全对齐本地与 `origin/main`，不得 destructive reset，也不要重复应用相同补丁。

## 23. 2026-07-12 成熟产品与 AI for Science 引擎新阶段

> 本节是当前最新权威状态。用户要求持续自动驾驶，且特别强调跨 Session 记忆不可靠；后续必须执行本节的可恢复性协议。

### 新的最高目标

- 项目不再只以“同构检索产品”完成度为终点，而要成为可证伪、可复现、能主动寻找反证并通过前瞻实验验证的 AI for Science 引擎。
- 总需求与完成合同：`docs/product/master-requirements-2026-07-12.md`。
- 引擎闭环：科学问题 → 结构表示 → 跨域机制检索 → 可证伪假设 → 反例/边界 → 可区分实验 → 前瞻预测 → 结果回写 → 可信度更新。
- 至少一个核心发现通过预注册前瞻验证或独立复现前，不得宣称“新范式已被证明”。

### 当前本地版本

- 本地已提交：`65cb825` 注册/登录入口、`2f8845d` 产品价值评分、`2e65dd5` 移动端 100 分门禁；本地与远端存在等价补丁但 SHA 不同，禁止 destructive reset。
- GitHub 远端账户入口 PR `#230` 基于远端主线创建，写入本节时仍需检查全部 checks 后方可合并。
- 移动端公开页面 375/390/430 审计：路由、溢出、控件名称、键盘、触控目标和 axe serious 均为 0 缺陷；新增 clean-runner workflow，尚需远端独立运行。
- 收藏 Builder 已完成 session 权威、匿名合并、登出清理、stale-session 安全回落、Git 外持久化和一次性迁移；主 Agent 尚需独立复核后提交。
- 公开文案 Builder 已完成旧口径、伪实时、伪置信度、直接写论文和内部代号清理；静态 claim contract 与 3 个测试通过，尚需独立复核后提交。
- 模拟用户评测框架已实现 8 角色、五阶段门禁、异构模型要求和故意失败 fixture；12 个 public-copy/journey 测试通过。真实异构模型运行尚未完成。

### 新增研究与产品资产

- `docs/audit/product-90-scorecard-2026-07-12.md`
- `docs/audit/value-evidence-framework-2026-07-12.md`
- `docs/audit/evidence-bound-paper-drafting-2026-07-12.md`
- `docs/audit/experiment-data-revalidation-matrix-2026-07-12.md`
- `docs/audit/high-value-isomorphism-research-priorities-2026-07-12.md`
- `docs/testing/simulated-user-evaluation-v1-2026-07-12.md`
- 首轮高价值排序最高为路口溢流锁死↔电网级联 85；当前没有候选达到 90，禁止把共享方程当作机制证明。
- AI for Science 范式定义与独立统计红队协议正在由两个独立 Agent 编写，完成后必须由主 Agent 交叉核验。

### 当前未提交范围

- 收藏/auth/deploy 相关修改。
- 公开文案、claim inventory/checker/tests。
- 模拟用户评测配置、fixture、runner/tests/docs。
- 产品、实验、论文草拟、高价值研究和总需求审计文档。
- 不得一次混为一个 commit；按 favorites、copy claims、journey evaluation、research/product docs 分批 Builder→Validator→目标/全量测试。

### 跨 Session 强制协议

1. 80% context 开始整理，最迟 90% 前追加本文件；每个部署版本后立即追加。
2. compact/新 Session 第一动作必须完整读取本文件 1–末行，不只读最新节；然后检查 pwd、repo、README、git status/log、Agent、CI、部署和生产状态。
3. 交接必须含 SHA/分支、未提交文件归属、测试命令/结果、workflow/run、生产证据、数据/模型指纹、回滚和严格下一步。
4. 聊天记忆、摘要和 Agent 自报均不是最终证据；主 Agent 必须现场验证。
5. 不在本文件或日志中记录任何 secret 值。
6. 自动驾驶必须主动向用户同步阶段进展，至少覆盖 Validator、P0/P1、目标/全量测试、CI、部署、生产 smoke 和研究 go/no-go 节点；不等待用户询问。
7. 进展汇报必须明确分开已验证、运行中、问题、风险边界与下一步，不能把局部绿色表述为项目完成。

### 严格下一步

1. 独立复核并测试 favorites/auth/deploy，按独立版本提交。
2. 独立复核 public copy 与 claim gate，提交并跑完整相关门禁。
3. 为 simulated journey runner 指派非 Builder Validator，再进行至少两个异构模型家族的真实公共数据评分。
4. 回收 AI for Science 范式与统计红队文档，收敛最强 claim、benchmark、消融、负对照和前瞻验证计划。
5. 按高价值优先级选择 2–3 个 dossier 深挖；先验证文献新颖性和可区分实验，不按吸引力直接开发。
6. 检查 PR `#230` 及所有 CI；全绿后合并、部署并运行更新后的生产 smoke。

### 项目完成后的待研究事项

- 用户确认：本项目达到严格完成定义后，再独立研究如何实现真正的 24 小时无人值守自动驾驶。
- 当前会话自动驾驶不等于常驻 daemon；无新执行回合时，已启动的 Agent/CI/长进程可完成，但主 Agent 不会自然获得无限续回合。
- 后续专题范围：常驻 orchestrator、持久任务队列、自动续回合、阶段状态机、权限/预算、安全、失败隔离、Builder-Validator、CI/部署、生产监控、交接恢复与人工升级。
- 在 Structural Isomorphism 完成前，不让该基础设施专题分散当前产品与研究主线。

## 24. 2026-07-12 产品 90 分第二阶段：版本化与发布门禁

> 本节是当前最新权威状态。阶段进展需主动同步；用户要求当前持续执行期间约每 10 分钟汇报一次。聊天系统无执行回合时无法按墙钟主动发消息，此限制不得隐瞒。

### 已独立验证并提交到本地主线

- `7cdec1d`：账户 session 权威收藏、匿名合并、跨设备恢复、登出/陈旧 session、安全迁移与 Git 外持久化。Validator 发现并修复生产 `/api/api/favorites` 双前缀；后端 61、真实 Next/FastAPI/Chromium 9 全通过。
- `7601a7d`：公开文案与 claim inventory 门禁，移除旧 verified 数、伪实时、伪置信度、直接写论文和内部代号；contract PASS、3 tests。
- `f61d3d7`：账户数据 registry、登录态导出/删除、session generation、deletion epoch、旧 SQLite 迁移、安全擦除和补偿回滚；独立 Validator 后账户目标 73、backend 全量 915 passed/1 skipped。
- `757e874`：工作台系统先生成确定性指纹草案，标明用户原文/待确认/未知，缓存污染防护、移动/键盘/读屏；Validator 真实 Chromium 3、静态契约 1、public controls 11 通过。
- `ea54579`：Stage 1 benchmark harness，含强基线、8 消融、负对照、预算、VFU、时间切分、污染与 immutable seal；红队修复 formal/symlink/TOCTOU/遗漏/重复绕过，23 tests。仅实现级 PASS，正式科学证据 NO-GO。
- `59e3e09`：8角色×2任务模拟用户评测门禁，严格异构 panel、locator、digest、JSON、abstain和指纹；18 tests。真实异构运行仍 NO-GO，待模型 registry、不可变 evidence bundle 与 adapter。
- `5b0738d`：总需求、90 分评分、AI for Science 范式、独立验证协议、论文证据安全、数据/实验复核和高价值研究优先级。

### 发布 PR 与线上为什么暂未变化

- 生产 beta 现场仍为 `324c914`；因此用户目前看不到本批变化。
- 本地与远端因 GitHub Connector 等价补丁产生分叉；未 force push。基于 `origin/main=28078db` 无损重建发布分支 `release/product-90-20260712`，PR `#231`。
- PR #231 首轮：backend矩阵、build、coverage、frontend、packages、sanity通过；4个红灯已完成四层根因：
  1. browser：CI只装精简依赖，favorites经errors导入缺`slowapi`；
  2. product contract：仍断言旧“收藏不与邮箱同步”文案；
  3. mobile：PR门禁错误审计未部署生产站，形成部署前循环；
  4. perf：真实 bundle/perf全PASS，仅PR评论权限403导致job失败。
- 修复提交 `fc7400a` 已推送 PR #231：补slowapi、更新产品契约、mobile改为本地Beta+Phase构建审计、perf声明最小评论权限。本地产品契约26/26，workflow YAML与diff check通过；需等待第二轮CI终态。
- 账户入口另有 PR `#230`；不得在 checks 未全绿时合并。PR #231未包含本地`65cb825`账户入口，以避免和远端逐文件Connector分支冲突。

### 当前进行中三条 Builder

1. `/me` 用户可见导出/删除 UI 与真实 Next/API E2E。
2. Decision Brief 下载与报告完成后直接创建 7 天实验。
3. 真实异构旅程评分前的模型 registry、不可变 evidence bundle 与安全 adapter；不调用外部模型、不伪造评分。

### 严格下一步

1. 监控 PR #231 第二轮 checks；逐项绿后才合并、部署、运行生产 smoke，并复核线上 SHA 与用户可见变化。
2. 检查 PR #230 checks与冲突；若账户入口未进入#231，安全合并或在最新main重建最小补丁。
3. 回收三条 Builder，分别指派独立 Validator；目标/全量测试后独立提交。
4. 把本节 `NEXT_SESSION.md` 在对应发布终态后再次追加，不用本节“运行中”代替最终证据。

## 25. 2026-07-12 第二阶段冻结发布与配额接力

> 本节是当前最新权威状态。第二阶段代码已在隔离发布分支冻结并完成本地 Builder-Validator；GitHub push 因 Codex 外部执行用量上限被平台拒绝，尚未创建 PR、运行远端 CI 或部署。

### 冻结分支与提交

- worktree：`/tmp/si-product-release2`
- branch：`release/product-90-stage2-20260712`
- frozen HEAD：`c31f352`（`fix(release): close SSO and evidence gate bypasses`）
- 基线：生产主线 squash `15d8a70`，其上无损 cherry-pick 16 个已验证本地版本，再追加 `c31f352`。
- push 首次因沙箱 DNS 失败；按规则申请外部执行后，被 Codex usage limit 拒绝。不得绕过；额度恢复后直接重试并核对远端 ref。

### 本批主要能力

- 账户数据导出、永久删除、旧 session 永久失效与跨产品删除对称。
- beta/Phase 跨域 SSO、匿名报告按当前浏览器 proof 认领、一次性 code 与跨域报告归属。
- Decision Brief 下载、证据边界、7 日实验、截止日与本地提醒。
- 确定性结构指纹草案、模拟用户评测、Stage 1 benchmark 与 pilot sourcing。
- KB 来源双审队列、Evidence Ladder、公开 claim/data provenance 收口。
- Phase 44px 交互目标、移动端/键盘/axe 与 universality 候选/非机制证明文案。
- 两条高价值 dossier 已收窄：交通锁死×电网级联仅 Stage 0 conditional GO；清算机制辨别仅受控 Stage 0 GO，现实 Stage 1 NO-GO。

### 独立 Validator 与本地门禁

- 产品/UX：GO；Decision Brief 19、公开控件/文案 14、账户/报告/SSO 163、真实浏览器 5；375/390/430 与 15 次 axe 检查无 critical/serious，P0=0、P1=0。
- 安全：GO for PR/CI；账户/SSO 20。修复公开/私有 env 重复 key、弱 secret、非 canonical origin、非 600 env、非 prod、共享目录 symlink/realpath 绕过；生产仍必须真实配置与跨域 smoke。
- 科学：本轮工程门禁 GO；93 个联合测试及 evidence/public/research validators PASS。修复 evidence level 伪升级、False/空集合/类型/hash/verdict/独立性/日期/URL 凭据与 fragment 绕过，合法 replicated 正路径可达。
- 后端全量：`926 passed, 1 skipped`（隔离 worktree 需 `PYTHONPATH` 和 Git 外本地模型挂载；首次环境失败不属于代码回归）。
- Phase：TypeScript 与生产 build 通过，30/30 routes。
- 新增/目标 root 门禁：126 passed；最终研究联合门禁 93 passed；`git diff --check`、两个 deploy shell `bash -n` 通过。

### 科学与价值边界

- 当前来源覆盖仍为零；KB 不得从 candidate 自动升级。
- formal Stage 1 与 pilot dispatch 仍 NO-GO；合成 harness 明确 `scientific_evidence=false`。
- 在核心发现完成预注册前瞻验证或独立复现前，不得宣称 AI for Science 新范式已被证明。
- 真实用户价值仍需 15–20 个研究密集型任务或等价的前瞻证据；当前工程/UX 绿色不能替代真实价值证明。

### 额度恢复后的严格下一步

1. 完整重读本文件，检查 `/tmp/si-product-release2` HEAD 必须为 `c31f352` 且工作树干净。
2. 推送 `release/product-90-stage2-20260712`；必须用远端 ref/PR head 核对，不能相信空 push 输出。
3. 创建 PR，等待 CI、backend matrix、packages、frontend、browser、mobile clean runner、perf、coverage、sanity、types 全部终态。
4. 红灯先四层根因分析再修；冻结 SHA 后重新跑移动/浏览器门禁。
5. PR 全绿才合并；随后在 VPS 私有配置中安装相同高熵 `STRUCTURAL_SSO_SECRET`、相同 Git 外 `STRUCTURAL_SSO_DATA_DIR` 与 canonical origins，绝不记录 secret 值。
6. 依次部署 beta、Phase、docs；核对 `/api/version` SHA、deep health、4443 KB、597 frozen demo、账户入口、真实跨域 SSO、匿名报告 claim、账户删除撤销、全部 production smoke。
7. 部署终态立即追加第 26 节和 `~/progress.md`，记录 workflow、生产证据与回滚。

## 26. 2026-07-12 第二阶段生产发布、跨域 SSO 与账户删除 P0

> 本节是当前最新权威状态。第二阶段主版本已发布；跨域 SSO 真实 smoke 已通过至报告认领，但暴露 Phase 账户永久删除的共享 import topology P0。修复 PR #236 正在运行全量 CI，尚未合并、部署或完成最终 production smoke。

### 已合并与已部署

- PR `#232` 全部门禁通过后 squash 合并，远端 main 为 `758a92f`；第二阶段产品、账户、报告、证据、研究门禁和移动体验进入生产主线。
- beta deploy `29195010569` 在安装私有 SSO 配置后重跑 success；deep health、4,443 KB、artifact、语义搜索和部署 SHA 指纹通过。
- docs deploy `29195010578`、perf `29195010574`、主线 CI/Coverage/sanity/types 全部 success。
- PR `#234` 修复 Phase 共享 SSO router 在 beta 顶层 import 与 Phase package import 两种 topology；合并 main `c8f2b29`。
- PR `#235` 修复 Phase 自动部署未监听共享 auth/SSO 依赖，以及 beta 私有 env symlink 目标权限应使用 `stat -L` 校验；合并 main `13cccac`。
- Phase deploy `29196248941` success：dependency contract、SSH deploy、API smoke 全绿。

### 生产私有配置

- Phase 与 beta 使用相同高熵 `STRUCTURAL_SSO_SECRET`，仅存 VPS mode 600 私有 env，未进入仓库、文档、日志或对话。
- canonical origins：`https://phase.bytedance.city` 与 `https://beta.structural.bytedance.city`。
- 共享 Git 外数据目录：`/var/lib/structural-isomorphism/sso`，mode 700。
- Phase auth env 与 beta env 已在修改前备份，时间戳 `20260712T134739Z`。
- Phase Git 工作树通过 ignored private symlink 指向唯一 beta env，避免两份 secret 配置漂移。

### 真实生产 smoke 已验证

- beta `/api/sso/start`：303 到 canonical Phase connect，state/nonce binding 正常。
- Phase `/api/sso/issue`：合成有效 Phase session 返回 200。
- beta `/api/sso/exchange`：200，建立 beta-only HttpOnly session；重复 exchange 被拒绝。
- 创建合成匿名报告后，`/api/reports/anon-proof` 200、`/api/me/reports/claim` 200、账户报告列表包含被认领报告。
- 每轮合成账户和报告均由 finally/registry 清理，不触碰真实用户。

### 当前真实 P0 与四层根因

- 表面：Phase `POST /api/me/delete` 返回 500。
- 直接原因：`auth._account_registry()` 在 Phase package topology 中加载 favorites/report assets；favorites 和 auth package re-export 仍包含 beta-only 顶层 imports，日志为 `ModuleNotFoundError: auth`。
- 系统根因：共享账户删除依赖图只验证 beta 运行方式，之前只对 SSO 第一层做双 topology contract，没有实例化完整 deletion registry。
- 全局影响：注册、登录、SSO、匿名报告认领正常，但 Phase 用户当前无法永久删除账户；这是隐私 P0，最终生产收口 NO-GO。

### 当前修复 PR #236

- branch：`fix/phase-account-delete-imports-20260712`
- commit：`dd6dec5`。
- 修复 favorites 的 api-key/auth/errors package-relative imports、report_account 的 SSO/store imports、auth package 的相对 re-export。
- 新回归实际从 `web.backend.api.auth` 构建完整账户删除 registry，不只做静态字符串检查。
- 本地：Phase import/deletion registry contract `4 passed`；beta account/favorites/SSO `51 passed`；diff check PASS。
- 远端当前：types、retrieval contract 已 pass；backend 六矩阵、browser、frontend、packages、coverage、sanity 正在运行，无失败项。

### 严格下一步

1. 等 PR #236 全部门禁终态；有红灯先四层根因分析，不跳过。
2. 全绿后 squash 合并；新 main 应自动触发 beta 与 Phase deploy，因为 #235 已补完整共享依赖路径。
3. 监控两端 deploy 到 success，核对最终 main SHA 与线上版本。
4. 重跑可清理生产 smoke：start 303、issue 200、exchange 200、重放拒绝、anon proof 200、claim 200、delete 200、旧 beta session 401。
5. 触发最终 `site-smoke.yml`，验证 docs/beta/Phase 全部业务不变量。
6. 终态立即追加第 27 节和 `~/progress.md`；不得再等待用户提醒才写交接。

## 27. 2026-07-12 PR #236 发布后生产删除 P0 仍未关闭

> 本节是当前最新权威状态。PR #236 已全绿合并并部署到 beta/Phase，但真实生产 smoke 暴露 Phase 锁定运行环境缺少完整账户删除依赖；最终生产结论仍为 NO-GO。

### 已完成

- PR `#236` 全部门禁 success 后 squash 合并，远端 main：`efed48bb0f5408171420f01621199be11a72a2c9`。
- beta deploy `29197973546` success：健康、4,443 KB、artifact identity、语义搜索和部署指纹通过。
- Phase 因 workflow paths 未覆盖 `favorites.py`、`report_account.py`、`auth/__init__.py` 未自动触发；手动 dispatch `29197993059` success，依赖 contract、SSH deploy、API smoke 通过。
- 真实生产 smoke 再次验证 start/issue/exchange、防重放、匿名报告 proof、claim 与列表成功；合成数据由 finally 清理。

### 新的四层根因

1. 表面：Phase `POST /api/me/delete` 仍返回 500。
2. 直接原因：完整账户 registry 导入 `web.backend.errors`，Phase 锁定 venv 缺少 `slowapi`，日志为 `ModuleNotFoundError: slowapi`。
3. 系统根因：Phase deploy contract 只导入主 app，没有在 Phase 锁定依赖环境实例化共享完整账户删除 registry；自动部署 paths 也未覆盖这组共享依赖文件。
4. 全局影响：Phase 常规 API、SSO 和报告认领正常，但永久删除不可用；隐私 P0 与最终 production GO 仍被阻断。

### 严格下一步

1. 在 Phase 锁定 requirements 增加精确版本 `slowapi`，不得临时污染生产 venv。
2. 部署 contract 在同一 venv 实际构建 `web.backend.api.auth._account_registry()`。
3. Phase workflow paths 覆盖完整共享账户依赖文件，并增加静态回归契约。
4. Builder 后由独立 Validator 审查，跑 Phase dependency contract、账户目标测试、Phase build 和 diff check。
5. PR 全绿后合并、自动部署 Phase；重跑完整生产 smoke，必须得到 delete 200、旧 beta session 401。
6. 终态继续追加第 28 节与 `~/progress.md`。

## 28. 2026-07-13 Phase 永久删除生产 P0 关闭

> 本节是当前最新权威状态。Phase 账户永久删除、跨域 SSO、匿名报告认领和跨产品会话撤销已通过真实生产 smoke；核心隐私 P0 已关闭。最终全站 site smoke `29199428277` 已触发，写入本节时需等待终态。

### 修复与发布

- PR `#237`：`fix(phase): validate account deletion runtime dependencies`。
- 独立 Validator 首轮发现 workflow 错写不存在的 `account_data.py` 且漏掉真实 `account_data_registry.py` / `auth_store.py`，判定 NO-GO；修正后第二轮最终 GO。
- Phase requirements 精确锁定 `slowapi==0.1.9`；clean Python 3.12 venv 实际导入 Phase app 并构建完整三资产 account registry。
- Phase workflow paths 覆盖 auth、SSO、favorites、report account、auth package、errors、account registry、auth/report/SSO stores。
- 本地：clean Python 3.12 registry contract PASS；Phase contract `6 passed`；账户/收藏/报告 `51 passed`；YAML 与 diff check PASS。
- PR #237 全量 CI success 后 squash 合并，远端 main：`d9f795918180149d3fd558dd413cdbaafbcd43aa`。
- Phase deploy `29199350344` success：clean dependency contract、SSH deploy、公开 smoke 全部通过。

### 真实生产证据

- 可清理合成账户链路：`start=303`、`issue=200`、`exchange=200`、code replay 拒绝、匿名报告 proof/claim/list 成功、`delete=200`、旧 beta session `401`。
- 脚本输出：`production_sso_smoke=PASS start=303 issue=200 exchange=200 claim=200 delete=200 revoked=401`。
- 合成账户与报告由 finally/registry 清理；一次性脚本已从 VPS 删除；无 secret 值进入输出。
- 当前结论：跨域账户删除隐私 P0 已关闭。

### 接力下一步

1. 等待 site smoke `29199428277` 终态；若成功，将本节中的运行中状态追加为最终 success，不改写历史。
2. 核对 main `d9f7959` 的 CI、coverage、sanity、types、perf 全部终态；红灯按四层根因处理。
3. 修复 GitHub Actions Node 20 deprecation warning 是 P2 基础设施债，不阻断当前 P0。
4. 回到成熟产品与 AI for Science 主线：真实异构 journey scoring、Stage 1/pilot 外部证据、英文检索质量和全站用户可见体验验收；工程绿色不能冒充真实用户/科学价值已证实。

### 2026-07-13 终态追加

- site smoke `29199428277` success，耗时 2m24s；fail-closed production synthetic monitor 全部通过。
- 同一 main SHA 的 Phase deploy、types、perf 已 success；CI、coverage、sanity 在本追加时仍正常运行且无已知红灯，需等待终态。
- GitHub Actions 提示 Node 20 action 被强制运行在 Node 24；记录为 P2 维护债，不影响本次 P0/生产验收结论。

### 2026-07-13 主线门禁最终追加

- main `d9f7959` 的 CI `29199350354`、coverage `29199350355`、sanity `29199350394`、types `29199350343`、perf `29199350372`、Phase deploy `29199350344` 与 site smoke `29199428277` 全部 success。
- 下一阶段已在隔离 worktree `/tmp/si-english-retrieval`、分支 `feat/english-retrieval-safe-experiment-20260713` 启动；仅做安全双路检索实验和无泄漏证据轨，feature flag 默认关闭，尚未提交、PR、部署。

## 29. 2026-07-13 英文检索安全实验与不可伪造评测协议

> 本节是当前最新权威状态。英文检索被确认存在严重召回塌缩；安全实验入口与评测基础设施已完成多轮独立审查并进入 PR #238，但生产功能保持默认关闭，尚无九系统 runs、评审标签、评分或上线授权。

### 现状诊断

- 旧 40 条 English DEV：nDCG@5 `0.3029`、Success@5 `0.275`、Top1 relevant `0.05`；29/40 的 Top-5 没有 relevance>=2。
- 对应中文：nDCG@5 `0.8543`、Success@5 `0.95`、Top1 `0.75`；英文是候选召回塌缩和跨语 hubness，不是轻微排序问题。
- 人工中文对应句和 multilingual MiniLM 只证明旧 judged pool 内存在约 30% rerank 信号；新候选未判，不能证明端到端 recall 或真实翻译收益。

### 工程轨

- commit `007d259`：默认关闭的 `retrieve_safe_english` 实验入口。
- NFKC/control/zero-width/空白/长度规范化；Bearer/JWT/AWS/access token 等敏感信息只走本地原文。
- 明确英文最多一次翻译；exact schema、中文占比、URL/HTML/行动指令/长度 guard；必须注入可信本地 semantic guard，否则 fail closed 回原文。
- 原文 lane 先启动、模型/guard/翻译搜索异常硬回退；确定性 RRF；不返回 candidate query 明文。
- 新旧目标测试 `34 passed`；独立安全 Validator 限定 GO。
- 未接真实 `/ask`、未开启 flag、未部署；真实接入和 UI/E2E 必须另行 Builder-Validator。

### 证据轨

- commit `0ccb6b6`：200 条 label-sealed deterministic simulated holdout（100 in-scope、100 OOS、40 dangerous，全部唯一）；旧 40 永久标为 DEV_ONLY。
- 九系统×200×Top50 内容寻址共同池；每系统 output、code、model、KB、run 和 common union 均现场重算指纹。
- raw `(query,doc,reviewer,score,scope)` 评审；每候选至少 3 reviewer；in-scope relevance QWK 与 OOS scope agreement 分离；逐争议独立仲裁。
- 唯一 confirmatory primary、cluster bootstrap 10k、paired permutation；英文/中文/OOS/dangerous/延迟/成功率门禁。
- 中文非劣从权威 qrels 与内容寻址 runs 现场重算；ranking 严格等于冻结 output 前缀、Top5 唯一非空、nDCG 必须 finite 且 `[0,1]`。
- 四轮独立产品/证据 Validator 曾先后拦截重复 OOS、伪共同池、伪 QWK、cluster 混杂、排名换序、中文手填分、重复高相关 doc 等绕过；最终评测基础设施 GO，P0=0、阻断 P1=0。
- 主线程相关测试 `26 passed`，py_compile/diff check PASS。

### GitHub 与严格下一步

- worktree：`/tmp/si-english-retrieval`；branch：`feat/english-retrieval-safe-experiment-20260713`；HEAD `0ccb6b6`。
- PR `#238` 已创建，需等待全部 CI/coverage/sanity/types/perf 终态；当前不得合并前跳过红灯。
- candidate manifest 仍 `NOT_BUILT`；没有九系统 runs、raw reviews、adjudications、中文 controls 或评分，因此英文上线与价值结论仍 NO-GO。
- PR 全绿后可合并基础设施，但仍不部署/开启英文功能；下一步是生成九系统候选 runs、异构模型模拟盲评（明确不冒充真人）、仲裁与离线评分，再决定是否进入真实 endpoint shadow/canary。
- 真实用户价值和投稿级证据仍需独立真人/外部评审；内部模拟不能替代。

## 30. 2026-07-13 产品能力 90 分冲刺与 Stage 3 并行状态

> 本节是当前最新权威状态。用户明确要求产品能力核心维度达到严格 90 分以上才结束；不能用高分可靠性平均掉英文、证据与发现等低分项，也不能用内部模拟冒充真实用户或科学证明。

### 已合并基线

- PR `#238` 全量 CI success 后合并，远端 main：`924e8771c394e5057df6143e13b1ce60f4392549`。
- 合并内容：默认关闭的安全英文双路实验入口、200 条 label-sealed simulated holdout、不可伪造九系统候选/评审/统计协议。
- 生产英文能力未开启，candidate manifest 仍 `NOT_BUILT`。

### 最新现场产品评分

- 运行可靠性 94；移动布局/控件 92；账户 92；用户资产 88；Decision Brief/实验闭环 86；中文主旅程 82。
- 文案/信任 70；实证验证体验 62；精选发现 58；KB 证据可信度 52；英文搜索 25；严格综合约 73。
- 生产移动 46 intentional routes × 375/390/430 的 route/overflow/named/keyboard/touch PASS；本轮 axe 因隔离 worktree缺依赖未执行，不能写成现场全绿。

### 新发现并行状态

- 基础设施 commit `6ed3860` 已本地提交：精确修复 powerlaw 2.0 `sigma` warning storm，PR 快测 72 pass/10 slow deselected/21 real warnings/约15秒；nightly不再吞backend/E2E/k6失败；Actions升级Node24版本。独立Validator GO，尚未push/PR。
- 九系统 freezer Builder完成但独立Validator NO-GO：四本地adapter未统一锁定production manifest、BM25 capability与真实依赖不一致、候选ID未校验KB；另有symlink逃逸、authority不可独立复核等P1。正在返工，未提交。
- 本地多语 guard Builder首版独立Validator NO-GO：MiniLM会把`positive feedback`↔`负反馈`判为高相似，只能验证topic不能验证方向忠实。正在增加否定/方向/数字/实体保真与并发边界，未提交。
- 产品现场P0：英文生产静默返回明显错误候选且无Beta边界；About/Tools等仍把39候选写成已验证，与Evidence Ladder冲突。claim修复正在Builder，英文正式候选继续保持NO-GO。

### 严格下一步

1. 三路Builder分别由非Builder独立Validator复核；按infra、freezer、guard、claim分开commit。
2. 先push基础设施版本并跑CI，验证packages/sanity真实耗时与warning数量改善。
3. freezer GO后在具备真实4443 KB/model/embeddings的权威工作树运行四本地系统；五个缺模型/API系统不可伪造或降级。
4. 英文候选/异构模拟评审达预注册门槛前，不接生产；先修生产英文静默误导和claim诚信P0。
5. P0关闭后并行推进KB/Discovery provenance、Empirical Result Card、账户/Library、Decision状态机、全控件行为矩阵与axe clean runner；每个维度独立复评，低于90继续返工。

## 31. 2026-07-13 夜间 90 分冲刺：Validator 反例与 PR #239

> 本节是当前最新权威状态。三条产品/英文基础轨均在独立 Validator 反例后返工；只有 CI 性能版本已独立 GO 并进入 PR。不得把 Builder 自测或局部通过计入产品 90 分。

### PR #239：CI 性能与 nightly 可靠性

- commit `6ed3860`；PR `#239`。
- powerlaw `sigma` warning storm 在精确第三方调用边界处理，保留真实数值告警；PR快测72 pass/10 slow deselected/21 warnings/约15秒。
- GitHub真实结果：主 packages 由约9分钟降至1m39s，sanity由约10分钟降至3m42s；SOC多Python/OS矩阵多数1–2分钟success。
- nightly不再吞backend/E2E/k6失败；Actions升级Node24官方major。
- 写入时41 checks success、1 skipped；仅两个Ubuntu py3.11 package jobs因GitHub runner卡在`setup-python@v6`而pending，非测试步骤失败；workflow有20分钟timeout。未全绿前不合并。

### Freezer 最新 NO-GO 与返工

- 首轮P0（production corpus、BM25 capability、KB ID allowlist）和symlink/authority/partial问题已修。
- 后续Validator发现`production_endpoint` construction provenance仍可用自洽JSON伪造：没有raw HTTP request/response bytes与真实version capture；external model同理缺raw provider证据与cost ledger。
- 当前返工要求：内容寻址raw artifacts，parser只从raw response抽Top50；canonical final URL/status/timestamp/version payload；external request ID、raw response、逐请求token/cost与总预算；无raw/篡改raw/row mismatch fail closed。
- 未最终GO、未提交、未运行收费模型。

### Crosslingual guard 最新 NO-GO 与返工

- 首版MiniLM只能判topic，`positive feedback`↔`负反馈`错误放行；第二版又被Validator用普通实体因果反转、数字角色交换与可变cache污染击穿。
- 当前返工覆盖：普通anchor与因果顺序、A/B、数字+canonical unit+role/range、否定缩写、中英单位映射、immutable cache、canonical JSON key、Future sameflight异常共享、14条DEV校准fixture与Wilson报告。
- Builder最新offline MiniLM 42 tests自测通过，仍需同一独立Validator终审；未接pipeline/API/生产。

### Public claim 最新 NO-GO 与返工

- Builder已清理About/Tools/Insights主要“39已验证/A级”等文案，但独立Science Validator发现i18n切换仍恢复强claim：同一方程/跨协议普适/独立涌现/empirically validated/five arXiv/从不修改不调参等。
- 系统根因：contract依赖少量exact phrase，变体可绕过。当前返工需同步全部中英key、Tools数字就近ledger/date、regex/variant checker和中英渲染级测试。
- 未独立GO、未提交、未部署。

### 严格下一步

1. PR #239最后两job终态；全绿才合并并核对main新SHA。
2. freezer/guard/claim分别完成同一Validator复审；按三个独立commit/PR，不混合。
3. claim P0优先部署并生产复验；英文production仍关闭。
4. freezer正式GO后才生成四本地真实runs；五外部/缺模型系统严格fail closed或补真实raw capture，不以伪fixture完成。
5. 继续按约10分钟或阶段节点主动汇报；compact后完整重读本文件。

## 32. 2026-07-13 CI 性能合并、续费重启恢复与 Stage 3 第三轮审查

> 本节是当前最新权威状态。PR #239 已合并且新 main 全绿；腾讯云续费恢复触发的整机重启曾造成 beta 短暂 502，当前生产已恢复并通过完整 smoke。Claim 与 cross-lingual guard 仍在第三轮 Builder-Validator，未发布。

### 已合并与生产终态

- PR `#239` 全部门禁通过后 squash 合并，远端 main：`e73dc624832b2c080ee2d69150c44031cc6baed7`。
- 合并后 CI `29226118723`、Coverage `29226118733`、perf `29226118752`、sanity `29226118727`、packages `29226118739`、types `29226118768` 全部 success。
- packages 实际由约 9 分钟降至约 1–2 分钟，sanity 约 4 分钟；nightly backend/E2E/k6 不再吞失败，SOC warning storm 被精确压到真实告警。
- 腾讯云到期续费恢复后 VPS 于 `2026-07-13 13:24:05 +08:00` 整机重启；`structural-web` 在模型与 4,443 KB 尚未 ready 时已被 systemd 标记 active，nginx 短暂返回 502。
- 当前 beta deep health 200：4,443 KB、`[4443,768]`、canonical artifact、Luna Pro 全部正常；docs 与 Phase 200。
- 重启后完整 production smoke `29226266134` success，54 项业务不变量通过；当前生产 GO。
- 独立 reliability 补丁正在 Validator：systemd `ExecStartPost` 等待 deep readiness；production smoke 仅对 GET 的 network/502/503/504 做两次有限退避，POST 不重试、持续错误仍 fail closed。本地主线程 `17 passed`、diff check PASS，未提交/未部署。

### Freezer 第三轮最终 GO

- 独立 Product QA 重放伪 production、fake provider、NaN/零预算、中断恢复、响应超限及 CLI/别名绕过后最终 GO；专项 `19 passed`。
- 因仓库没有独立 runner 公钥/签名 verifier 或 provider-native receipt verifier，production endpoint 与三个 external construction 明确 fail-closed unavailable；任何本地自洽 JSON/SHA 均不能冻结。
- 本地 HTTP capture 仅标记为 `UNTRUSTED_LOCAL_FORENSIC_CAPTURE`，支持逐 query 原子 checkpoint/resume 与 8 MiB 响应上限；usage/budget 拒绝 bool、NaN/Inf、负数及非整数 token。
- 独立 commit：`0a26c23` `eval: freeze English candidate runs fail closed`；尚未 push/PR，未接生产。

### Claim 与 guard 当前 NO-GO/返工

- Claim 第二轮虽 checker PASS，但 Science Validator 在运行时 i18n 发现 `same law governs`、`都是它`、`validated on`、`可相互迁移`、合成对照排除偏差等强断言，判定 NO-GO。
- Claim 第三轮 Builder 已降级所有点名文案，checker 增加 HTML/JSON 渲染扫描、220 字符邻接 caveat 与中英文变体攻击；目标测试 `18 passed`，正在同一 Science Validator 终审，未提交/部署。
- Cross-lingual guard 第二轮 `42 passed` 仍被 Product QA 用否定作用域转移、实体 increase/decrease 交换、同单位数字槽位交换、Alice/Bob 因果反转、`unlikely` 漏判及 `not only/without delay` 误拒击穿，判定 NO-GO。
- Guard 第三轮 Builder 正在改为 clause/role ledger：predicate(subject, polarity, object)、signed change→entity、number→entity/metric/unit/role；无法可靠解析的方向性输入 fail closed。未提交/接 API/生产。

### 严格下一步

1. reliability、claim、guard 分别完成独立 Validator；只有 GO 才分 scope 提交。
2. 基于最新 main 建干净发布分支，逐个 cherry-pick 独立 commit；不得把 stage3 工作树未提交 scope 混在一起。
3. reliability 与 claim 先 PR/CI/部署/production smoke；freezer 与 guard 仅默认关闭基础设施，继续不启用英文生产链路。
4. Freezer 在真实 4,443 artifact 环境只运行可证明的四个本地系统；其余五个保持 unavailable，直到具备真实 provider-native capture 与独立 attestation。
5. 继续推进 KB/Discovery provenance、Empirical Result Card、账户 Library、Decision 状态机与 axe clean runner；每个低于 90 的维度独立返工，不能用平均分掩盖。

## 33. 2026-07-13 beta 主产品架构纠偏与第六轮安全/Claim 门禁

> 本节是当前最新权威状态。用户再次明确：`https://beta.structural.bytedance.city/` 是整个产品的唯一入口，Phase 只是 Structural Labs 下的子产品。当前生产仍是旧的反向账户架构；新实现尚未提交、PR、部署，独立 Validator 已判定两条关键 scope NO-GO，禁止提前上线。

### 当前权威架构

- beta Structural：主产品、研究工作台、统一账户中心与用户资产入口。
- Phase：`Structural Labs · Phase` 子产品，保持 597 ticker frozen demo、published NULL 与无预测能力边界。
- 目标主旅程：`提出问题 → 选择候选 → 研究草案 → 保存到我的研究 → 设计实验 → 记录结果`。
- 账户 Library 最终应统一报告、收藏、实验与结果；不能继续把 localStorage 收藏、账户报告和 Phase 会话视为三套产品。

### 当前现场状态

- 活跃隔离工作树：`/tmp/si-english-stage3`；branch `feat/english-retrieval-stage3-20260713`。
- 已独立提交但未发布：`a1ea4de` 重启 readiness；`0a26c23` 英文候选 freezer fail-closed。
- 当前生产 beta `/api/version` 仍为 `924e8771c394`，deep health 200、4,443 KB、`[4443,768]`；`/auth/login` 仍 308 到 Phase。Phase/docs 当前 200。
- PR #239 合并 main `e73dc624832b2c080ee2d69150c44031cc6baed7` 的全部 CI/coverage/perf/sanity/packages/types 已 success；本地旧主工作树尚未 fetch 对齐，发布必须从最新远端 main 建干净分支，不能 destructive reset。

### beta 原生账户 Builder 与独立 NO-GO

- Builder 已实现 beta-native `/auth/login`、`/auth/verify`、同源 magic link、direct session 到旧 SSO subject 的基础映射、独立 mode-600 `beta-auth.env` 部署契约。
- Builder/主线程目标验证：账户与资产相关 209 passed；生产冒烟/静态契约 30 passed；真实 Chromium 动态账户入口和移动焦点 2 passed；JS/Shell/Python syntax 与 diff check PASS。
- 独立安全 Validator 判定 3 个 P0：验证页首批静态资源可能通过 Referer 泄漏 token；旧坏 `structural_beta_session` 会压住成功的新 direct login；旧 Phase SSO 只有 subject，收藏/导出/删除和同邮箱资产没有统一。
- P1：轮换邮箱可绕过单邮箱邮件限流；应用运行时缺少与部署脚本等价的 role/data-dir fail-closed；登录后动态入口与账户管理 UI 尚未完整闭环。
- Security Builder 正在第六轮返工；完成后必须由同一独立 Validator 重放攻击路径，未 GO 不得提交。
- `scripts/production_smoke.py` 已改为不发送真实邮件的 beta `/api/auth/me = 401` 门禁；routine smoke 禁止创建账户、发邮件或触发管理员通知。

### Public Claim 第五轮独立 NO-GO

- Claim Builder 第五轮已做 Unicode/default-ignorable、隐藏 caveat 与多处强断言降级，自测 claim/research 22 passed；独立 Validator 现场只收集到 claim 13 passed，checker 虽 PASS 但仍可绕过。
- 两个 P0：`classes.html` 无 JS fallback 仍有“全部正确拒绝幂律/优秀 collapse”等强结论；`content.json` 运行时又升级为“已匹配物理普适类/翻译已知物理定律”，与 internal candidate taxonomy ledger 冲突。
- Gate 还需覆盖 `transform:scale(0)`、offscreen absolute、语义错绑 caveat、ARIA/title-only claim，以及拆成多个 JSON value 的强断言。
- 原 Claim Builder 正在第六轮返工，之后仍由 Science 独立复审。

### 产品体验已修与待修

- beta 全站账户 CTA 已收敛为单一入口：匿名“登录以同步”，登录后“我的研究”；移动抽屉已补焦点圈、Escape 关闭和焦点恢复；i18n toggle 双绑定已收敛为单一 wire 标记。
- 机械 cache-bust 曾截断 `404.html`，仅发生在隔离工作树且未部署；已用原页面恢复，并新增全 HTML 最小体积与 `</html>` 完整性检查。根因是批量改写缺少逐文件完整性门禁。
- 产品审查剩余 P0：导航“分析”仍指向依赖参数的结果页；报告所有权文案冲突；收藏未并入 Library；Phase 仍需子产品品牌/返回母产品路径；首页 Classes/Discoveries 第一触点 claim 仍需最终复核。

### 严格下一步

1. 完成 Auth 第六轮 Builder，独立 Validator 重放 token Referer、坏 cookie 恢复、同邮箱双路径资产/删除、IP/全局限流与 runtime 配置攻击。
2. 完成 Claim 第六轮 Builder，Science 重放 static/i18n/ARIA/hidden/JSON split 攻击；必须独立 GO。
3. 恢复 Phase 子产品 Builder；另由非 Builder 验证桌面/375/390、键盘、返回主产品和 frozen-demo claim。
4. 将 beta-native auth、账户 discoverability、claim、reliability 分 scope commit；从最新 `origin/main` 建干净发布分支 cherry-pick，PR 全门禁 success 后才合并。
5. 生产创建独立 `beta-auth.env`（只引用私有变量名，不记录值），部署 beta/docs/Phase；真实验证 magic email、重放拒绝、HTTPS cookie、重启持久化、同邮箱资产、导出/删除和旧会话撤销。
6. 发布后继续 Library/Decision 状态机、全控件行为矩阵、KB/Discovery provenance、英文四本地系统真实 runs 与 guard；外部五系统无原生证明保持 unavailable。
7. 每个部署节点继续追加本文件和 `~/progress.md`；context compact 后完整重读 1–末行。

## 34. 2026-07-13 beta 账户第七轮 GO 与 Claim 第七轮返工

> 本节是当前最新权威状态。beta 原生账户迁移已通过第七轮独立安全终审并形成隔离 commit；尚未 PR/CI/部署。Public Claim 第六轮仍被独立 Validator 判 NO-GO，正在第七轮返工。

### Auth 独立 GO

- commit：`6880818` `feat(auth): make beta the canonical account center`，位于 `/tmp/si-english-stage3` 分支 `feat/english-retrieval-stage3-20260713`。
- beta 原生 `/auth/login`、`/auth/verify`、same-origin magic link、token URL 清理、Referrer-Policy/no-store、direct/Phase SSO canonical identity、账户收藏/报告/导出/删除已进入同一身份状态机。
- 跨账号双凭证不再按优先级任选：direct Alice + SSO Bob 时 auth/me、favorites、reports list/claim、export、delete 六端点全部 `409 error=credential_conflict`，响应不泄露邮箱，双方资产和 revoke epoch 零变化。
- 同账号 direct+SSO 可正常合并；删除后两类旧 session 均 401。任一 invalid/revoked/unlinked credential 均 fail closed，不降级到另一枚凭证。
- SSO exchange 成功后主动清 direct cookie；direct verify/logout/delete 清旧 SSO cookie。
- 邮件限流为 SQLite 原子 per-email + trusted-proxy client-IP + global circuit breaker；应用运行时与 deploy script 均强制 beta role、canonical HTTPS、Git 外绝对数据目录和可信代理配置。
- 独立 Validator 目标集 75 passed；主线程更大账户/资产组合 221 passed；root public-controls/production-smoke 32 passed；JS/Shell/py_compile/diff check PASS。
- 生产私有 `beta-auth.env` 尚未创建；需要新增 `AUTH_TRUSTED_PROXY_IPS` 并按真实 nginx/uvicorn loopback 拓扑设定。未配置前部署会 fail closed。

### Claim 第六轮仍 NO-GO

- static/runtime Classes/Methods 已统一降级，现有 checker PASS；但独立 Validator 实际只收集 15 个 claim tests，并非 Builder 汇报的 24 个完整门禁。
- hidden caveat 仍可被 `scaleX(0)`、`.0`、fixed/offscreen、clip、1px overflow、translate 等 CSS 变体绕过。
- inventory 没有覆盖 public runtime dependency closure；Search/Analyze 仍存在“成熟解法”“真的有效”“经 AI 评审验证”等升级文案，checker 仍可绿色。
- 第七轮必须改为同一 text node/极小标记 allowlist，任何 style/class/hidden/aria-hidden caveat fail closed；从 public HTML 自动收集本地 script/data 依赖闭包并真实运行新增攻击测试。未 GO 不提交。

### 产品主线当前进展

- 顶部冷启动入口已从无参数 `/analyze` 改为“开始研究”回到首页工作台；单一账户 CTA 匿名“登录以同步”、登录“我的研究”、双凭证冲突“确认账户”。
- `/reports` 正在升级为“我的研究”：报告/实验、账户收藏与本机收藏、账户/数据权利同页；390px Chromium 覆盖导出入口、logout/delete失败零假成功、DELETE确认和 credential conflict 资产锁定。
- 本模块仍等待独立 Product QA，未提交。
- Evidence Envelope Builder 正在并行贯通 Search/Analyze/Ask/Discoveries/Insights 的 candidate/source/result/independence/counterexamples/ledger 六字段；未完成/未验证。

### 严格下一步

1. Claim 第七轮 Builder→同一 Science Validator，独立 GO 后再提交。
2. Product QA 完成“我的研究/导航/移动/失败恢复”独立验证；修完 P0/P1 后单独提交。
3. Evidence Envelope Builder 完成后由非 Builder 对 schema、六类页面、来源与 ledger 降级做对抗验证。
4. 从 `origin/main=e73dc624832b2c080ee2d69150c44031cc6baed7` 建干净发布分支，按 `a1ea4de` reliability → `6880818` auth → account UX → claim 顺序 cherry-pick；freezer `0a26c23` 默认关闭另发。
5. PR 全绿前先在 VPS 创建 mode-600 beta auth 私有配置并做只读校验；合并部署后完成真实邮件、token重放、HTTPS cookie、重启持久化、旧/新身份迁移、导出/删除和 production smoke。

## 35. 2026-07-13 beta 发布 PR、证据门禁与子产品复验

> 本节是当前最新权威状态，取代第 34 节中的旧 commit/配置措辞。生产仍为旧版 beta 登录架构；以下新能力尚未合并或部署，不得宣称线上已可见。

### beta canonical auth 发布轨

- Stage 3 中 auth commit 已因补生成 SQLite ignore 修订为 `1843883`；部署时保护可变 runtime data 的 commit 为 `accec6c`。
- 干净发布 worktree：`/tmp/si-beta-auth-release`；分支 `release/beta-primary-auth-20260713`；PR `#241`。
- 发布分支当前提交：`fa7b9d0` readiness、`de19a63` canonical auth、`72095f2` runtime data exclude、`7552cea` beta native auth route contract。
- PR 首轮 retrieval contract 唯一失败为 `check_public_controls.py` 未登记 `/auth/login`、`/auth/verify`；四层根因是新页面与路由 allow-list 分属不同 scope，干净 PR 揭示依赖缺口。最小修复 `7552cea` 已推送，本地相关 28 passed、public control contract 155 controls、diff check PASS；等待新一轮 CI 终态。
- VPS 已存在 mode-600 私有 `beta-auth.env`，canonical beta URL、beta role、loopback trusted proxies 与 Git 外数据目录已按生产拓扑配置；值未进入仓库/文档/日志。真实服务尚未重启。
- 部署 dry-run 已确认排除整个 `web/backend/data/`，不会用源工作树覆盖生产 `history.db`、auth rate-limit、outbox 或用户数据。

### 当前独立门禁

- Auth：第七轮独立安全 GO；75 个攻击目标、221 个账户/资产组合通过。
- Claim：第七轮 Science 复验仍发现 linked CSS `content`、inline script、字符串拼接和 template interpolation 五类绕过；新 Builder 已扩展 CSS/JS/inline runtime closure，Claim+Research 35 passed、两道 gate PASS，等待独立复验，未提交。
- Evidence Envelope：首轮独立 NO-GO，原因是浏览器与后端对未知 verdict、日期、independence、counterexample 和 score 的升级判定不一致，且 verdict 不可见、Search 有未来 nested-anchor 风险、语言切换不重渲染。主线程已统一 allow-list/日期/账本/反证规则，增加 verdict、等级本地化、ledger URL、`suppressActions` 与 i18n refresh；专项 22、相关后端 80 passed，等待同一 Product QA 对抗复验，未提交。
- My Research：独立复验 NO-GO；真实 409 credential conflict 未全资产锁定，可能回退显示本机收藏；mobile drawer Shift+Tab 逃逸且无移动语言入口。Builder 正在修复并增加真实 409/焦点/语言 E2E，未提交。
- Phase：Builder build 30/30、静态 6、浏览器 1 通过，但独立 Validator 判 NO-GO。P0 是权威 backtest `p=0.5690715676` 与首页/companies/FAQ 的 `p=0.681` 冲突；P1 包括移动边界条过高、640px 导航溢出、drawer 无完整 focus trap、旧品牌残留、44px 漏项与 320px privacy overflow。原 Builder 正在从单一结果源修复并补 320/640/品牌/高度/焦点门禁。

### 时间与严格下一步

- 当前估计：3–5 小时首批用户可见发布；10–16 个有效工程小时完成账户、证据、文案、移动与全链路生产收口；英文正式门禁和研究证据另需 1–3 天，不能以内部工程绿色替代科学证明。
- Claim、Evidence、My Research、Phase 必须各由非 Builder 独立 GO；任何 NO-GO 由原 Builder 返工。
- 各 scope GO 后分开 commit，按依赖 cherry-pick 到 PR #241 或后续最小 PR；全 CI 终态绿色才合并。
- 合并后先部署 beta，验证原生 login/verify、真实邮件、重放拒绝、同身份/冲突身份、收藏/报告/导出/删除、重启持久化与 4,443 KB；再部署 Phase 并核对 597 frozen demo、NULL、唯一 p 值和全路由主产品返回。
- 发布终态继续追加第 36 节与 `~/progress.md`，不改写本节历史；compact 后从本文件第 1 行完整重读到末行。

### 2026-07-13 CI 与 Evidence 追加

- PR #241 第二轮 route contract 已转绿，但旧架构测试仍断言 beta `/auth/login` 308 跳 Phase；coverage/sanity 因此各 1 fail。browser fixture 又将多条 `Set-Cookie` 折叠为一条，丢失 direct session，造成 6 个 Phase Next 账户旅程失败。
- 修复 commit `b3e239c`：测试改断言 beta 原生 200 登录页；真实 Next/FastAPI 测试代理逐条应用多 cookie，不修改生产认证语义。本地真实 Chromium 13 passed，目标后端 1、public controls 12、syntax/diff PASS；已推送，第三轮 CI 全部重新 pending。
- Evidence Envelope 经 Product QA 第二轮仅剩 Insights 未接 i18n；补 `i18n.js < evidence-envelope.js < insights.js` 与六 surface 顺序契约后，独立真实 Chromium 390px 中英初始化/双向切换、verdict/ledger、无溢出全部通过，最终 GO。专项 22、相关后端 80 passed；尚未提交，需等待重叠 Claim/My Research 文件均 GO 后再按 patch 边界冻结。
- PR #241 第三轮已全部终态绿色：backend 5 个 OS/Python 组合、model-load、browser、coverage、frontend、mobile、packages、retrieval、sanity 与 check 均 pass，live soft-fail job 按设计 skipped。暂不合并，先把账户入口/My Research 独立 GO 版本纳入，避免发布“原生路由存在但导航仍指向旧 Phase”的半成品。

## 36. 2026-07-13 产品诚信版本冻结并进入最终 CI

> 本节是当前最新权威状态。新产品版本已推送 PR #241，但尚未合并、部署；生产 beta 仍是旧账户入口。不得在 CI 全绿和生产 smoke 前宣称用户已可见。

### 独立 GO 与冻结提交

- Phase 最终 GO：static 9、lint、build 30/30、真实 Chromium 覆盖 320/375/390/640/1024/1279，boundary+header=122px、全部 drawer focusable>=44px、无 overflow、focus trap/inert/Escape、privacy wrap；1280 正确切桌面。公开 NULL p 值单源 `0.5690715676`，旧品牌清零。Stage commit `ba6a166`，发布 cherry-pick `434ce09`。
- Evidence Envelope 最终 GO：未知 verdict、非法/未来日期、independence、counterexample、score 与 ledger 前后端 parity；verdict/ledger 可见、等级本地化、Search 无 nested anchor、Ask/Insights 中英切换与 390px 通过。产品冻结内含。
- Claim Gate 最终 GO：34 Claim + 9 research = 43 passed，两 gate PASS；DOM receiver provenance 与真实 load context 消除 `error.title`、`logger.append`、asset fixture 三类误报，同时保留 linked CSS/DOM/JS 渲染检测。产品冻结内含。
- My Research 最终 GO：14 static、12 Chromium；身份与 reports/favorites 使用原子 staging，两种延迟 409 下 MutationObserver `seen_secret=false` 且本机读取为 0；普通 401、局部 503、移动 i18n/focus/44px 均通过。Stage 产品 commit `cb3e4ef`，发布 cherry-pick `1cef340`。
- Cross-lingual guard 仍为 NO-GO/默认未接入；两个未跟踪文件仅留在 Stage 3 worktree，没有进入任何发布 commit。

### PR #241 当前发布头

- release branch：`release/beta-primary-auth-20260713`；当前 head `2b21479`。
- 新增发布 commits：`434ce09` Phase、`1cef340` product trust、`2b21479` 内部 KB provenance E2E 断言；此前 auth/reliability/data protection/CI fixes 均保留。
- cherry-pick 唯一冲突为 public route allow-list 的格式级同内容冲突，按两边并集解决；public controls 15 passed、159 controls。
- 干净发布本地：产品门禁 98 passed；相关后端 92 passed/1 deselected；Claim/Research 两 gate PASS；Phase lint/build 30/30；Phase clean browser 1 passed。
- Beta 全浏览器组合首次 21 项中 20 passed；唯一失败仍寻找旧“查看候选来源”文案。产品已正确改为“查看内部 KB 记录”，测试同步后目标旅程 1 passed；此修复为 `2b21479`。
- 当前最新 push 已触发新一轮全 CI，尚待终态；上一轮 auth-only head 曾全绿，不能替代当前 head 的门禁。

### 严格下一步

1. 等 PR #241 当前 head 全部 CI/coverage/browser/mobile/packages/retrieval/sanity 终态；任何红灯先四层根因。
2. 全绿后合并，核对新 main SHA；监控 beta 与 Phase 自动部署。若 paths 未触发对应部署则手动 dispatch，不能只看 main merge。
3. beta 生产验证：首页账户 CTA、`/auth/login` 200、真实受控 Magic Link、token重放拒绝、cookie安全、重启持久化、同/异身份、报告/收藏/导出/删除、4,443 KB、runtime data 未覆盖。
4. Phase 生产验证：597 frozen demo、NULL、唯一 p 值、全路由主产品返回、320/390/1024 与键盘；再触发 site smoke。
5. 生产终态追加第 37 节与 `~/progress.md`。随后继续英文四本地系统真实 runs、guard 返工、发现/KB provenance 与研究证据，不以本轮发布冒充全项目科学证明完成。

## 37. 2026-07-13 beta 主账户生产发布与部署契约收口

> 本节是当前最新权威状态。beta 主产品账户、我的研究、Evidence Envelope、公开 Claim 门禁与 Phase 子产品版本均已上线并通过生产验收。英文 cross-lingual guard 仍为 NO-GO/未发布；科学证明与英文正式门禁不能用本节的工程绿色替代。

### 发布版本

- PR `#241` 全部门禁 success 后 squash 合并，main `95a142a1829a6e09af1c5d8f97f5da78868e6276`。
- beta deploy `29230970677` success；docs deploy `29230970794` success。生产 beta `/api/version` 已返回 `95a142a1829a`，4,443 KB、`[4443,768]`、Luna Pro 与 canonical artifact 均正常。
- Phase 首次 deploy `29230970701` 失败：新 auth runtime 要求 trusted proxy/beta role，而 Phase 私有 env 和旧部署契约仍按旧 origin；服务保持运行，beta 不受影响。
- 系统性修复 PR `#242` 经独立 Security Validator 三轮（两次 NO-GO、最终 GO）后 squash 合并，main `04c95c842605289a45c0b5b6fcab8f3eacc86fd7`。
- 修复后 beta deploy `29232268832` success；Phase deploy `29232268824` success；site smoke `29232398181` success。

### 两次生产 P0 与系统性修复

1. beta 登录页已上线但 `/api/auth/me` 仍 503。
   - 直接原因：VPS 实际 systemd unit 没有加载已经准备好的 mode-600 `beta-auth.env`。
   - 系统根因：tracked unit 虽正确，但 `deploy-vps.sh` 从未安装它；部署只验健康/数据/版本，不验账户业务不变量。
   - 修复：unit 只从 Git SOURCE 安装，旧 unit 事务备份；install/daemon-reload/restart/健康/auth curl/JSON 任一失败均回滚；workflow 监听 unit 文件并硬校验公网匿名 401。
2. Phase 新 auth 配置与共享模块角色冲突。
   - 修复：Beta/Phase 必须显式声明各自 `AUTH_SITE_ROLE`，并分别绑定唯一 canonical HTTPS origin；Phase 要求 trusted proxy，并在 lifespan 启动时 fail-stop 验证，不再只靠逐请求 503。
- 本地生成的 `web/backend/data/auth.sqlite3*` 已加入 ignore，避免测试运行时账户状态误提交。
- VPS 现场备份：`phase-auth.env.pre-beta-canonical-20260713T071018Z` 与 `phase-auth.env.pre-role-phase-20260713T073013Z`；systemd 旧 unit 在部署事务内自动备份/恢复，不记录任何 secret。

### 验证证据

- 本地相关账户/报告/收藏/SSO/Phase：`266 passed`；Shell syntax、两个 workflow YAML、`git diff --check` PASS。
- 独立 Security Validator 第三轮最终 GO：SOURCE 权威 unit、已有/无旧 unit 回滚、root fail-fast、restart/curl 逃逸、role-origin、proxy、SQLite ignore 全部关闭。
- 公网：beta `/auth/login=200`；beta 与 Phase 匿名 `/api/auth/me=401 error=no session`；Phase EWS `597`、`price_provenance=demo`。
- VPS：`structural-web` 实际 unit 已含 private beta auth EnvironmentFile 与 deep-readiness `ExecStartPost`；三个服务均 active。
- 可清理生产账户链路：verify `200`、token replay `400`、Secure/HttpOnly/SameSite cookie、服务重启后 `/me=200`、export `200`、delete `200`、旧 cookie `401`；合成账户已删除。
- Resend 官方 `delivered@resend.dev` 测试 sink：beta request-link `200`，说明真实 SMTP 同步接受；测试 token 与 rate-limit 行已清理。此前第 21 节真实邮箱 delivered/管理员通知验收仍有效。

### 当前工作树与严格下一步

- 临时发布 worktree `/tmp/si-beta-auth-release` 已基于最新 main；本地 docs 分支仅用于准备交接，不得覆盖 `/Users/dadamini/Projects/structural-isomorphism` 中本文件的完整追加历史。
- Stage 3 `/tmp/si-english-stage3` 仍只保留两个未跟踪 cross-lingual guard 文件；它们没有进入 PR #241/#242，生产英文链路继续关闭。
- 先核对 main `04c95c8` 的 CI/coverage/sanity/types/perf 全部终态；若红灯按四层根因处理。
- 下一产品/研究主线：四个可证明本地系统的真实英文 candidate runs；guard 第四轮对抗返工；KB/Discovery provenance 与 Empirical Result Card；英文 expanded judgments 和人类/异构独立评审。
- 仍禁止把 internal candidate、模拟 reviewer 或 fixed-pool 提升写成英文 recall、机制迁移或 AI for Science 范式已被证明。
- 每个新发布节点继续追加第 38 节与 `~/progress.md`；compact 后从本文件第 1 行完整重读到末行。

### 主线终态追加

- main `04c95c8` 的 CI `29232268801`、Coverage `29232268861`、sanity `29232268798`、types `29232268844`、perf `29232268831`、beta deploy `29232268832`、Phase deploy `29232268824` 与 site smoke `29232398181` 已全部终态 success。
- 第 37 节工程与生产结论正式 GO；下一步直接进入英文候选真实 runs、guard 与 provenance/科学证据轨，不重复本轮账户发布工作。

## 38. 2026-07-13 英文真实候选 runs 与生产产品只读复验

> 本节是当前最新权威状态。三个可证明本地英文候选系统已完成真实 run；生产 HTTP/HTML/部署一致性 GO且未发现 P0/P1。这不构成英文质量结论，也不得将未完成的生产浏览器交互冒充为已验收。

### 英文候选真实 run

- 权威输入现场核验：KB `299a0fd6...ab99`，4,443 rows/unique IDs；embeddings `dafec148...4f27`，`[4443,768]` float32；structural-v2 四个 required file SHA 均与 manifest 一致；holdout `2df0c126...2b6b`，200 条 label-sealed；多语 MiniLM 唯一 pinned snapshot 存在。
- Stage 3 因 KB 是 LFS pointer 且缺 model，因此在隔离执行根 `/tmp/si-freezer-exec-20260713` 安装已验物料；输出为 `/tmp/si-english-formal-runs-20260713`，未污染项目工作树。
- 正式本地 run 完成三项：BM25 `2.69s` / SHA `693eab44...09bb`；current Chinese dense `16.67s` / SHA `acfe246e...9d89`；multilingual dense `25.94s` / SHA `55f76765...177d`。
- 三项均为 200 queries x Top-50，每条候选唯一且全部属于 4,443 KB allowlist；每 query 三系统 union min 144 / max 150 / mean 148.29；`--resume` 复验前后 SHA 完全不变。
- 第四项 `production_endpoint` 不是本地 adapter；无独立 runner attestation 时必须 fail closed，本地 capture 不 eligible。九系统 freeze 因缺此项及其他五个外部/缺模型系统未生成 `FROZEN_COMPLETE`；`external_paid_calls_executed=false`。
- 当前只能声称“三个真实本地候选 run 完成”。尚无 labels/qrels/metrics，不得声称英文 recall、机制迁移或完整 candidate pool 已证明。

### 生产产品只读 QA

- beta `/`、`/auth/login?next=%2Freports`、`/reports`与 Phase 八个核心路由全部 200；匿名 beta `/api/auth/me=401 no session`、`/api/me/reports=401 valid beta session required`。
- beta 主要页面与 auth/my-reports/site-chrome/i18n/common/responsive 资产 SHA-256 和当前本地验收字节完全一致；Phase HTML 含桌面/移动返回主产品链接、`xl` breakpoint、`min-h-11`、NULL 与唯一 `p=0.5690715676`。
- production smoke `22/22`、production-smoke tests `18/18`、public-controls `14/14`、159 个静态控件契约 PASS；deep health 仍为 KB 4,443 / embeddings `[4443,768]`，Phase demo 597。未发现已确认 P0/P1。
- 生产交互仅 `CONDITIONAL GO`：当前 Browser runtime 无可用实例，按规范未改用 standalone Playwright。待补 320/375/390/1024 实际布局、Tab/Escape、动态 CTA、console/network 与真实点击后才可转完全 GO。本地同字节版本的既有浏览器 GO 不冒充生产现场结论。

### 当前严格下一步

1. 独立对抗审查未接入的 cross-lingual guard，覆盖否定、实体、数字/单位、因果方向、范围、条件与混合语言；非 GO 不接入。
2. 定稿 qrels/judgments 的盲评、异构模型+人类校准、指标/置信区间与发布门禁；指标完成前不做质量结论。
3. 独立复审 KB/Discovery provenance、Evidence Envelope 与 Empirical Result Card，修复任何 P0/P1 后才进入新发布。
4. 任一 Browser runtime 可用时补约 5 分钟生产交互验收；不因该外部执行位暂缺而停止其他主线。
5. 继续保留 Stage 3 两个 guard 文件为未跟踪/未发布；下一发布节点追加第 39 节和 `~/progress.md`。

### 2026-07-13 用户优先级调整

- 用户明确要求：英文能力后置，先把其他每个环节全部做完。该优先级取代本节上方“立即推进英文 guard/qrels”的时序，但不改变其 NO-GO/不得过度声称的事实边界。
- 已中止英文 guard 与英文评测两条 Agent 当前工作；三个真实本地 runs 作为已冻结证据保留，不继续扩展。
- 当前主线改为：先修复公开 Insights 数据边界、动态强断言与 claim gate；再完善 KB/Discovery provenance、Evidence Envelope、Empirical Result Card；同时继续全页面/全控件/移动/文案/失败恢复验收。
- 英文轨只在上述非英文 P0/P1 全部关闭并发布后恢复。

### 2026-07-13 主动进度同步纪律

- 在正在运行的长执行回合中，每约 10 分钟主动汇报一次已验证进度；P0、门禁结果、部署或真实阻塞立即汇报。
- 不得将“聊天会话未运行时无法自行唤醒”冒充为实时后台自动驾驶；持久无人值守汇报属于 Structural 完成后的独立控制平面项目。

## 39. 2026-07-14 非英文产品硬化、隐私传输与可复现发布（进行中）

> 本节是当前最新权威状态。用户再次确认英文能力后置；先关闭其他产品、隐私、可信输出、运行时和全链路体验 P0/P1。当前改动仍在隔离工作树，尚未 commit、push、PR、部署；生产继续是稳定旧版，不得把本节的本地进展写成线上已可见。

### 当前代码与生产

- 活跃工作树：`/private/tmp/si-nonenglish-hardening`；分支 `feat/nonenglish-product-hardening-20260713`；基线/HEAD/origin main 均为 `04c95c842605289a45c0b5b6fcab8f3eacc86fd7`。
- 工作树约 198 个 modified/untracked 文件、约 26,720 行新增；包含此前已经 Builder-Validator 的研究来源、账户资产、公开文案、移动体验、证据契约，以及本轮仍在移动的隐私/Search/runtime。禁止 `git add -A`、禁止 destructive reset、禁止从 VPS 反向覆盖。
- 已为 P0 日志热修预建干净工作树 `/private/tmp/si-nginx-privacy-hotfix`，分支 `fix/privacy-path-only-logging-20260714`，基于 `origin/main=04c95c8`；尚未复制补丁或提交。
- 2026-07-14 现场复验生产：beta `/api/version=04c95c842605`；deep health 为 4,443 KB、`[4443,768]`、canonical artifact、Luna Pro，全部 checks `ok`；Phase 为 597 ticker frozen demo。生产稳定但没有本轮用户可见改动。

### 已完成并正在收口的三条 Builder

1. 隐私传输与账户收藏：
   - Analyze、Struct Lint 已改为严格 POST JSON + fetch ReadableStream；旧 GET 410；NFKC/control/长度门禁、abort/retry 已实现。
   - 收藏 `bookmark-v2` 使用 typed query/fingerprint/candidate origin，公开 href 只含安全路径/公开 ID；旧 raw href 迁移后清理；跨设备点击通过一次性本地 handoff 恢复。
   - Analyze/账户/收藏目标 129 passed；Node handoff 16 passed；Mapping POST 专项 46/46 passed。
   - `privateNavigation.js` 已实现随机 key、一次消费、typed `history.state`、reload/back/tab 隔离；Search consumer 正在接入，Phenomenon/所有入口、Nginx、Uvicorn、Sentry 和 query-derived logs 尚未最终冻结。
2. 自然语言 Search 可信度：
   - 新增严格 typed candidate synthesis；模型只能引用服务端重跑 Top-5 后从 KB 回源的真实 ID；blocking/stream 均在完整 JSON、Pydantic 与语义门禁通过后才发布，进度事件不含 raw model text。
   - UI 不再把 fused score 显示成百分比/强中弱/置信度，改为本次查询序位并声明不可跨查询比较、不是概率或证据等级；失败提供显式降级与重试。
   - Synthesize request 已 strict/extra-forbid、NFKC、1..8000、rewrite<=800、Top-5 唯一 ID、lang enum；模型输出新增 Unicode/bidi/default-ignorable、跨字段、双重否定、URL/Markdown 绕过门禁。专项 55 passed；此前 Search 相关集 106 passed。
   - 真实 Chromium 的 3 项 reload/edit/back/force/replay/expiry/storage/two-tab/mobile 测试已写，但本机 Chromium 因 Mach/bootstrap 权限无法启动；沙箱外申请又被平台 usage limit 拒绝，未绕过。最终必须由正常 GitHub browser CI 执行。
3. 可复现 Python runtime 与事务部署：
   - runtime identity 为 CPython ABI + 完整 requirements SHA + canonical resolved graph SHA；构建后执行 pip check、sys.prefix/interpreter/pip shebang、精确依赖版本、import 和全树只读验证。
   - 已实现 deploy journal、4 GiB 磁盘门禁、orphan recovery、bounded GC、current/previous/N 保护、effective systemd unit/drop-in/ExecStart 检查、首次 enable、deep-ready rollback 和公开 runtime attestation。
   - SOURCE 必须 clean Git 且 HEAD==DEPLOY_COMMIT；部署改从 commit Git archive 逐 blob/mode 手工安全解包，拒绝 hardlink/特殊路径/越界 symlink，LFS 物料继续只走外部 artifact manifest；TARGET tracked bytes 最终逐项证明等于 commit。
   - deployment/smoke 最近 63 passed，version/auth 32 passed，signal fault injection 已覆盖 TERM/HUP/INT；最后一个只读 TOCTOU fixture 正在收口，之后交回原独立 Runtime Validator。

### 新确认的隐私 P0 与四层根因

- 表面：前端准备移除 `/search?q=`、`from_query`、Analyze/Lint/Mapping GET，Magic Link 页面也会清理 token URL。
- 直接原因：生产 Nginx 仍使用 global `log_format main` 的 `$request`，beta/Phase 无私有格式；两个 Uvicorn ExecStart 也未关闭默认 access log。浏览器清理发生在首个请求之后，因此 query、token、SSO code 仍可能进入 access log 或 systemd log。
- 系统根因：此前隐私边界只覆盖页面和 API body，没有覆盖反向代理、应用服务器、可选 Sentry、模型校验错误和 query-derived telemetry；把无盐截断 SHA 当作“privacy-preserving”也是同类错误。
- 全局影响：研究问题可被日志关联/小词典反查，一次性认证凭证可能在有效期内落盘；这阻断生产发布。
- 生产只读事实：`/var/log/nginx/access.log` mode 640，当前约 129 KB，daily rotate 10；未读取内容、未删除历史。Sentry 当前私有配置未启用。
- Builder 已落 path-only canonical beta/Phase TLS vhost、事务安装/回滚脚本和 static contract；正在补双 Uvicorn `--no-access-log`、Nginx fault injection、Referrer-Policy、Sentry scrub、无盐 query/email/IP identifier 清理。热修完成后必须独立安全复审并优先最小发布；旧日志不擅自删除，按轮转自然到期。

### 当前门禁证据与已知移动失败

- 当前 moving tree `git diff --check` PASS；public claim checker、research claim gate、159 static public controls PASS。
- `make test-release-contracts` 最近一次完整快照：932 passed、157 skipped、1 deselected；之后 public API 仍在变化，不能当最终结果。
- 公开控件/文案组合当前 90 passed、4 failed：两项旧测试仍绑定旧 handoff 函数字面量；一项新资产出现 `20260714p1/p2` cache key 分裂；一项 About i18n 测试仍绑定旧措辞。根因是共享前端契约和 release cache 版本尚未冻结，不是删除测试即可解决。
- 修复要求：旧测试改为 typed/one-time/no-raw-URL 行为不变量；所有本批变更资产在最终冻结点统一一个 release cache key；中英文 claim 测试继续验证“未校准排序不是证据、模型意见不是独立评审、必须展示证据缺口与下一步核查”。
- OpenAPI/TypeScript 目前因 API 仍移动而预期 drift；不得中途反复生成。最终 API freeze 后使用现有 pinned venv 一次生成并由原 OpenAPI Validator 独立复验。

### 尚未开始或尚未关闭

1. Ask：确认后的结构指纹目前只显示在 UI，没有进入 request/retrieval；raw LLM answer delta 在整包校验前已进入 DOM；abort/retry 会留下悬空状态。需一个独立 Builder 统一 request schema、原 query OOS guard、fingerprint retrieval、typed answer/source binding、validation-before-display 和并发状态机。
2. Analyze：deep prompt 仍预设 SOURCE 有成熟答案、结构相同、要求具体阈值/本周动作/历史引用；输出缺少投稿级 typed evidence guard。需改成候选映射、竞争解释、证据缺口、失败条件和可区分实验。
3. Stress/Diagnose/Apply/Lint：仍有 PASS/FAIL、LLM confidence%、“结构同构真实先例”、score百分比、“可套用”等过度确定表达，需统一 candidate/evidence envelope 与失败恢复。
4. 最终全页面真实浏览器、320/375/390/1024、键盘、动态账户/收藏/报告/导出/删除、所有按钮、console/network 仍需正常 CI/生产执行位补全；static controls 不等价于行为验收。

### 严格下一步

1. 完成隐私 Nginx/Uvicorn/Sentry/query-log 热修；由非 Builder Security Validator 做 fake-bin rollback、effective config、POST/410、URL/history/referrer/log 对抗审查；GO 后复制到干净 hotfix 分支，目标测试、PR、CI、事务部署和生产 path-only 复验。
2. Runtime Builder 完成最后 fixture 后恢复原 Runtime Validator；必须给出最终 GO 才进入发布分支。
3. Search 与 Private Navigation 冻结后由独立 Validator 重放 malformed model、unknown ID、Unicode/Markdown/score、storage/reload/tab 与不泄漏路径；真实浏览器留给正常 CI，不伪称本机已跑。
4. 依次启动 Ask/Fingerprint、Analyze Deep Report、secondary tools 三个 Builder；每个超过 100 行均 Builder→独立 Validator，OpenAPI 最后一次生成。
5. 冻结单一 cache key，跑 backend/root/packages/Phase/build/browser/mobile/perf/claims/controls/`make verify-release`；按研究来源、账户隐私、产品 UX、核心可信输出、runtime 五个逻辑边界提交，禁止 `git add -A`。
6. PR 全绿才部署 beta/Phase/docs；生产核对 runtime attestation、4,443 artifact、POST/410、账户全链路、所有主要旅程与移动端。严格复评分项均>=90 后才恢复英文轨；最终追加第 40 节和 `~/progress.md`。

## 40. 2026-07-14 独立红队、额度恢复与三轨返工（进行中）

> 本节是当前最新权威状态。Codex usage limit 曾阻断所有文件写入；用户已明确额度恢复，主线程已用 `apply_patch` 实测写入成功并继续自动驾驶。当前仍未 commit、push、PR 或部署；生产继续运行 `04c95c8` 稳定旧版。

### 当前代码、生产与纪律

- 活跃工作树仍为 `/private/tmp/si-nonenglish-hardening`，分支 `feat/nonenglish-product-hardening-20260713`，HEAD/origin main 均为 `04c95c842605289a45c0b5b6fcab8f3eacc86fd7`。
- moving tree 约 200 个 modified/untracked 文件；包含多个已验证与未冻结 scope。继续禁止 `git add -A`、destructive reset、从 VPS 反向覆盖和整体直接部署。
- 生产只读基线未变：beta 4,443 KB、`[4443,768]`、canonical artifact、Luna Pro；Phase 597 frozen demo。额度封锁期间没有生产写入。
- 平台封锁前后所有 Builder/Validator 均明确记录了零部署边界；本节只恢复本地落盘与测试，不代表发布 GO。

### Runtime 独立审查与已落盘返工

- 已完成 protected/excluded 根与父链 symlink containment、恢复写入前二次验证；生产移除未消费且依赖外网的 legacy `TARGET/models` 恢复，模型唯一来源为已验证 `ARTIFACT_ROOT/structural-v2`。
- rollback/current runtime 改为用目标解释器现场核验 `sys.prefix`、ABI、pip shebang、`pip check`、完整 installed graph、关键包 metadata/import/version 与 release 路径；伪 shell、binary tamper、metadata tamper 已有对抗 fixture。
- Full SHA 主链、systemd 状态、known auth drop-in、Nginx/unit/fingerprint/service journal 与 rollback 语义已部分落盘，但远端 forced dispatcher、SIGKILL 幂等恢复和二次 rollback fault coverage 尚未完成。
- 最近证据：发布/生产相关 `79 passed`；backend version/security `19 passed`；28 个 shell Python heredoc 全部编译；bash/YAML/diff check PASS。
- 独立 Validator 曾判定 NO-GO：rollback 失败清证据、SIGKILL 无恢复、protected symlink 越界、伪 runtime、systemd disabled/error、Nginx 不在外层事务、短 SHA/push race、错误 smoke 基线等必须逐项以 fault tests 关闭。
- usage limit 前最后留下两个明确 P0：public attestation heredoc 缺 `import re`；schema2 journal 不兼容可能存在的 legacy terminal schema1。额度恢复后主线程第一项已补 `import re`，必须增加 exact block 执行测试；schema1 仍待受控兼容/迁移。
- Candidate continuity 有一个旧断言：实际 rollback 已从 `|| true` 加强为 `|| failed=1`，测试仍要求旧文本；应改为验证 fail-closed 语义。

### Privacy 独立 Security Validator：P0 NO-GO

- `$uri` 不是隐私安全：`/api/report/share/{token}` 与 `/report/share/{token}` 的 path segment 本身是 bearer capability；应用 Correlation ContextVar 又把 raw path 注入每条日志，404 也可记录任意敏感路径。
- 对抗异常 `ValueError` 已实证 secret 原样进入日志，500 丢失 `X-Request-ID`；response 日志在 context reset 后失去关联信息。
- Sentry 对抗事件中 breadcrumbs、extra、exception value/frame vars、transaction 仍可携带秘密；当前 scrubber 是 false-green。
- Nginx installer 可被 `../`、symlink parent/source、FIFO/特殊文件、domain/format/变量注入绕过；全局 header 计数使 beta+Phase 双 vhost 无法共存；rollback/signal/KILL 失败会删唯一 backup。
- 生产现有 `structural-web` auth drop-in 与新部署“DropInPaths 必须空”冲突；未事务迁移前首发必失败。
- query hash、email/IP/owner hash、waitlist/newsletter 网络元数据和 raw LLM/Pydantic/exception 日志仍需清理。业务必需 raw email 存储可保留，但 operational telemetry 不得可反查；不擅自删除历史数据。
- 必须改为 Nginx 极小字段 allowlist、可信 route template、Sentry allowlist rebuild、统一 request ID、外层可恢复事务和全链路 secret canary；原 Security Validator 复验 GO 前不得复制 hotfix 或部署。

### Search / Private Navigation 独立 Validator：NO-GO

- `privateNavigation.js` 在 Web Crypto 缺失时仍回退 `Date.now()+Math.random()`；必须 crypto-only fail closed。
- helper 仅 Search 页面加载；Learn、Classes、History、Phenomenon 入口会失效/丢上下文；Phenomenon 仍构造/读取 `/search?q=` 与 `from_query`。
- one-time key 消费失败会回退当前 `history.state`，同 key 可重放；有 key 但消费失败必须拒绝，只有无 key reload/back 可恢复 typed state。
- 后端重算 Top-5 后重新编号，前端只按 `result_index` 绑定旧数组；可把 `kb-2` 解释显示到 `kb-1`。必须按 canonical `source_kb_id` 绑定。
- private nav 接受 8,000 字符而 Search API 只接受 500；需端到端统一限制。
- Unicode combining mark、Markdown、中文文字数字、迁移保证和双重否定可绕过 claim guard；synthesis 旧请求回调缺 generation 校验，可覆盖新结果；Phenomenon 仍显示检索百分比。
- 现有 113 pytest、8 Node private-nav 和 rendering tests 通过，但对抗复现仍失败；这些绿测不能替代真实入口/竞态/绑定验证。

### 严格下一步

1. 三轨并行且文件互斥：Runtime 完成两个 P0、journal/fault/full-SHA/dispatcher；Privacy 完成代理到观测/持久化/导航全链路；Search 完成 crypto/replay/入口/source binding/claim/generation。
2. 每条 Builder 冻结后由不同 Validator 复验；同一人不得自审。浏览器本机受 Mach 限制的项目留给正常 GitHub browser CI，不伪称通过。
3. 三条 GO 后再启动 Ask/Fingerprint、Analyze Deep Report、secondary tools Builder；随后冻结单一 cache key 和 OpenAPI。
4. 完整门禁、分 scope commit、干净发布分支、PR/CI 全绿后才事务部署；生产 secret canary、账户、主要用户旅程、移动/键盘/console/network 全验收后复评分。
5. 下次 context 接近 90% 前只追加第 41 节；不要改写本节历史。

## 41. 2026-07-15 恢复工作树、全量冻结门禁与发布前置（本地 GO）

> 本节取代第 40 节的“本地返工中”状态，但不改写历史。代码、隐私、分析、覆盖率与可复现产物已在恢复工作树完成并通过独立 Validator；远端 PR、合并、事务部署与生产验收仍必须按本节顺序执行，不能把本地 GO 当作线上完成。

### 当前权威与安全边界

- 恢复候选位于 `/private/tmp/si-recovered-20260715`，分支 `feat/nonenglish-product-hardening-20260713`；旧损坏工作树 `/private/tmp/si-nonenglish-hardening` 未再修改。
- GitHub remote 只能显式使用 `github=https://github.com/dada8899/structural-isomorphism.git`；本地 `origin` 指向旧临时工作树，禁止普通 `git push`。
- 本机绝对路径 `models` 软链已移除，不能进入提交。`v4/validation/llm-scaling/requirements-generator.txt` 是正式 13 包锁文件，必须进入提交。
- 项目注册表已在 2026-07-15 校正：VPS Git 源为 `/root/Projects/structural-isomorphism-v4/`，Beta 版本化目标为 `/root/Projects/structural-isomorphism/`，Plausible 目标为 `/root/plausible-ce/`。
- 科学结论保持保守：LLM scaling 仍为 `INSUFFICIENT_REAL_WIDE_SERIES_FOR_UNIVERSALITY_INFERENCE`；本轮只提高产物可复现性与拒绝能力，不升级研究主张。

### 已关闭的系统性问题

- Runtime/部署：所有发布 Python 证明路径使用隔离解释器；full SHA、runtime attestation、事务 journal、回滚、systemd/Nginx/隐私边界均进入 fail-closed 合同。
- 隐私/分析：Beta 与 Phase 只在明确同意后发送 allowlist 事件；capability、私有研究、异常路径、DNT、撤回与旧 tracker 全部默认拒绝。Plausible runbook 以应用先发布、DNS 最后为唯一顺序。
- Coverage/CI：`reject-aware-critic` 纳入 coverage source、sanity 与发布矩阵；生产包要求非零采集，关键模块阈值与全局 80% 门禁均有效。
- Parquet/Python：backtest 通过 `pyarrow==24.0.0` 单一 extra；项目元数据改为 Python `>=3.10`，与依赖真实边界一致。
- 科学产物：Python 3.11 与 13 个完整传递依赖精确锁定；JSON 禁止 `NaN`；primary、cross-source、12B 与 PNG 绑定同一摘要。PNG 比较使用 metadata、尺寸和解码 RGBA，既拒绝像素篡改，也不因等价压缩编码假红。

### 最终本地证据

- `make verify-release` 在非沙箱 Python 3.11 环境完整通过：syntax 755；fast 306；backend 1902/1 skip；packages 111 + 162 + 50 + 72（另 10 deselected）；retrieval 6；root release contracts 1320/157 skip/1 deselected。
- 浏览器合同分进程全部通过：11 + 28 + 64（另 3 deselected）+ 28 + 13 + 20；Phase `pnpm lint` 与 30-route production build 通过。
- LLM/Parquet 独立 Validator：Parquet 14/14；locked LLM 31/31；ordinary 30/1 expected skip；public controls 103/103；两份 fresh env 五项产物逐字节稳定，JSON 与保留正确 metadata 的 PNG 像素篡改均被拒绝。
- Coverage 独立 Validator：6 suite 合计 2485 passed/1 skipped；global 84.3%；Cross 97.7%、Guarded 89.5%、Reject-aware 85.0%、SOC 71.9%；关键模块均超过各自门槛。
- Dispatcher bootstrap 独立 Validator：runtime/deploy 129/129，dispatcher/installer 聚焦 32/32，Nginx+Phase privacy 86/86，相关 shell syntax 与 diff-check 通过。

### 发布前 P0 与严格执行顺序

1. 从 GitHub PR head 建立新干净 release worktree，把当前最终内容按 runtime/privacy、产品 analytics、CI/reproducibility、docs/handoff 四个边界显式提交；禁止 `git add -A` 和改写旧损坏工作树。
2. 显式 push 到 `github` 的 `feat/nonenglish-product-hardening-20260713`，确认 PR #243 head 等于冻结 SHA；所有 required/optional checks 必须 success，不接受 failure、cancelled 或 pending。
3. 合并前建立短时 deploy freeze。从该已绿 PR SHA 经 `git archive` 提取 installer 与五个入口，做 root-only 外部备份、逐文件 hash/mode/owner 校验、installer `--check` 与非法命令负测。VPS 当前旧 wildcard dispatcher 不兼容 exact-SHA workflow，未完成此 bootstrap 禁止 merge。
4. 合并并记录 main merge SHA；Beta/Phase workflow 只能发送 `beta-backend <40-sha>` 与 `phase-deploy <40-sha>`，共用部署锁串行完成。必须核对 workflow SHA、VPS SHA、journal、runtime attestation、immutable interpreter、4,443 KB、597 demo、认证 401、隐私 drop-in 与真实公网路线。
5. Beta/Phase/Docs/site smoke 全绿后，才执行 `docs/analytics/plausible-deployment.md`：loopback CE、关闭注册、HTTP ACME staging、DNS/证书、TLS proxy、Beta+Phase 真实浏览器入库、ClickHouse/Dashboard、备份恢复演练。`202` 或 service active 不能单独算验收。
6. 生产验收后只追加新回执，不回写本节；同步 `~/progress.md`，再做最终全项目评分。英文能力轨仍按用户先前优先级延后，不能伪称已完成外部科学或人工英文评审。
