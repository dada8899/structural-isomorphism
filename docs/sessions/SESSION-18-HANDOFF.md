***REMOVED*** Session ***REMOVED***18 交接 — 价值挖掘 A–G

> 上一 session：***REMOVED***17。本文是给下一个 CC session 的技术交接。
> 项目：`~/Projects/structural-isomorphism/`（repo `dada8899/structural-isomorphism`，**PUBLIC**）
> A–G 的来源思考见 `docs/sessions/SESSION-17-untapped-value.md`（**先读它**）。

---

***REMOVED******REMOVED*** 0. 当前 prod 状态（verified 2026-05-22）

- 站点：`https://beta.structural.bytedance.city`
- prod git_sha：`3abaa78`（session ***REMOVED***17 全部成果已上线）
- 模型：`deepseek/deepseek-chat:nitro`，env=prod
- 测试基线：**后端 501 + e2e 15 全绿**

**起手第一件事 —— fingerprint check：**
```bash
python3 ~/Projects/structural-isomorphism/scripts/dogfood_fingerprint.py
```
看到 ✅ 才往下走。看不到立刻怀疑 deploy 没真上线（session ***REMOVED***15 血泪）。
注意：`_local_git_sha` 已修成「取最近非 docs commit」，docs-only 提交不会误报 mismatch。

**session ***REMOVED***17 已完成（别重做）**：M1.4 e2e、My Reports 页、发布前 5 路审查 + P0/P1/P2 全修、价值优化 V1–V6、nginx SSE 修复、搜索框去蓝光环。详见 `progress.md` 和 `SESSION-17-*.md` 系列。

---

***REMOVED******REMOVED*** 1. 本 session 任务：价值挖掘 A–G

A–G 是 7 个**产品方向**（不是 7 个小功能）。一个 session 做不完全部 —— **按下方「执行排序」做**，便宜高杠杆的先做扎实，长线的给起步切片。不要每个都做一半。

***REMOVED******REMOVED******REMOVED*** 资产清单（A–G 都建立在这些之上，先摸清）
- KB：`data/kb-expanded.jsonl`（4443 条现象，字段 `id/name/domain/type_id/description`）
- 23 个普适类：`web/frontend/assets/data/universality-classes.json`
- 39 个精选发现：`web/data/a_discoveries_merged.json`
- v2 跨域对索引：`services/v2_pairs.py` + `web/data/v2_pairs_index.json`（LLM 评分的「验证过」同构对）
- SIBD-63 数据集：`dataset/v1/structural-isomorphism-v1.0-benchmark/`（**已发布冻结，勿改其内部结构**）
- 报告引擎：`web/backend/api/analyze.py` + `services/`；前端 `web/frontend/assets/js/analyze.js`
- 回访数据：`report_followup` 表（session ***REMOVED***17 V6 新建）+ `report_feedback` 表
- Phase Detector：`/phase/*` 路由 + `v4/product/d1_phase_detector/`

---

***REMOVED******REMOVED*** A. 反向引擎 —— 从「解题」到「发现题」

引擎现在只跑正向（问题→找同构）。两个反向用法：

***REMOVED******REMOVED******REMOVED*** A1 方法 → 还能用在哪
用户输入一个方法/算法/模型 → 引擎在 KB 里找「结构上能套用此方法」的其他领域现象。
- 本质是把现有 search/analyze 的检索方向调过来：用「方法的结构描述」做 query，匹配 KB 现象。
- 复用 `services/search_service.py` 的检索；analyze 的报告模板需要一个新 mode（现有 query mode / pair mode 之外的 "method mode"）。
- 估：1 个 session 可出可用版本。

***REMOVED******REMOVED******REMOVED*** A2 普适类 → 研究空白地图 ★最便宜高杠杆，建议第一个做
23 个普适类 × 领域 = 矩阵。已映射的是少数格子，**空格子 = 研究选题**。
- 实现：对每个 (普适类, 领域) 组合，用 embedding 判断「该领域有没有现象属于这个类」。空缺且「理论上应该有」的 = research-lead。
- 产物：一个新页面，按普适类列出「这些领域大概率成立但还没人验证」，每条可一键生成验证方案（复用 analyze）。
- 几乎零新基础设施，数据（普适类 + KB domain）都现成。**一个周末能出原型。**
- 估：1 个 session 可做扎实。

---

***REMOVED******REMOVED*** B. 数据飞轮 —— 把「收集真实结果」变成核心设计 ★最重要、最该认真对待

V6 已建 `report_followup` 表（action_status + outcome + note）。本 session 要把它从「一个小功能」升级成产品主线：

1. **提高回访采集率**：报告生成 N 天后，用户回来时主动提示「上次那份报告你试了吗」；My Reports 列表上标未回访的报告。
2. **「已验证同构库」**：把 `report_followup` 里 outcome=worked 的报告，其 (问题结构 → source 现象) 对，沉淀成一个**结果验证过的同构数据集**——和 LLM 评分的 v2_pairs 分开存、分开标。V4 徽章未来可以升级成「这个映射有 N 人真的用成功过」。
3. **聚合洞察面板**：一个内部/对外的 dashboard，展示「用户最常卡住的问题结构 Top N」——本身可发表/可对外。
- 估：B 较大。本 session 至少做完 1+2 的 schema 与采集闭环；3 作为切片起步。
- 注意：`report_followup` schema 见 `services/report_store.py`，加字段走已有的 ALTER TABLE 自愈机制。

---

***REMOVED******REMOVED*** C. 从「报告」到「能力」—— 嵌入决策现场

***REMOVED******REMOVED******REMOVED*** C1 MCP server ★本 session 可做扎实
把 `search` / `analyze` / `find-isomorphism` 封装成 MCP server，让 Claude / agent 生态能调用「找结构同构」。
- 逻辑全现成（复用现有 API），主要是包一层 MCP 协议。
- 参考 Claude Agent SDK / MCP 规范。估：1 个 session 一部分时间。

***REMOVED******REMOVED******REMOVED*** C2 结构 lint（喂一份策略文档 → 标出结构性风险）
- 输入一段长文档，抽取其中的「假设/类比/判断」，逐条找结构同构 + 失效模式。
- 复用 analyze 的 risks_and_limits 能力，但输入是文档不是单个问题。
- 估：本 session 出 MVP（命令行或一个简单页面），打磨留后续。

***REMOVED******REMOVED******REMOVED*** C3 浏览器插件 / Notion·飞书 集成 —— 长线，本 session 不做，仅在文档里留方案。

---

***REMOVED******REMOVED*** D. 教育 / 科普资产 —— 沉睡的增长入口 ★本 session 可做

- `/discoveries` `/classes` 现在是「资料陈列」，改造成「增长引擎」：每条发现/普适类做成**可单独分享**的卡片（带 OG 图、短链），文案改成「地震和银行挤兑是同一个方程」这种钩子式。
- 每个普适类页加「用它分析你自己的问题」入口（导流到 analyze）。
- 可选：把 23 个普适类做成一个轻量「跨域思维」学习路径页。
- 纯前端 + 内容工作，估 1 个 session 一部分。
- 注意：session ***REMOVED***17 已把这些页从主导航移除（只留核心 4 页）；做 D 时要决定是否重新给它们导航入口。

---

***REMOVED******REMOVED*** E. verification-as-a-service —— 把「证伪能力」单独做成产品

- 现有的迁移风险段 / Rank-0 自检 / PASS-FAIL 管线，是产品最难被 ChatGPT 复制的部分。
- 本 session：做一个独立入口/流程「结构压力测试」——用户输入一个商业类比 / 战略判断（「我们是中国版的 X」），产品只做证伪：这个类比结构上成不成立、最可能从哪一环崩。
- 复用 analyze 引擎，但输出聚焦 risks + 一个明确的 PASS/FAIL/CONDITIONAL 结论。
- 估：本 session 出 MVP。

---

***REMOVED******REMOVED*** F. Phase Detector 转型为「结构诊断」

- 现有 `/phase/*` 是把结构引擎套到公司上，回测 null（诚实）。
- 本 session：**重新定位**——不预测股价，做「结构诊断报告」：告诉一家公司「你处于 滞回陷阱 / 级联脆弱 / SOC 临界 哪种结构状态」。
- 主要是文案 + 输出形态重构，引擎复用。session ***REMOVED***17 实测的「30 人公司效率塌陷」报告已证明这条能打动人。
- 估：本 session 可做重定位 + 输出改造的一部分；完整 B2B 化是后续。

---

***REMOVED******REMOVED*** G. 按「问题结构」连接人 —— 长线，本 session 只出方案

- 两个不同领域、结构同构的问题 = 在解同一道数学题的人，把他们连起来。
- 前置：用户账号体系（现在只有匿名 anonId）、问题结构的相似度匹配、隐私/同意机制、某种社区或通知形态。
- **本 session 不实现**，只在文档里写清架构方案和前置条件清单，作为独立立项。

---

***REMOVED******REMOVED*** 2. 建议执行排序（重要）

按「能在一个 session 做扎实 × 杠杆」排：

1. **A2 研究空白地图** —— 最便宜，资产现成，先做、先出原型验证需求
2. **B 数据飞轮 1+2** —— 最重要、会复利，schema + 采集闭环本 session 必须落地
3. **D 科普资产改造** —— 纯前端，增长入口
4. **C1 MCP server** —— 逻辑现成，战略卡位
5. **A1 / E / C2** —— 各出 MVP
6. **F Phase Detector 重定位** —— 文案/输出重构
7. **G** —— 只出方案文档

做完 1–4 就是非常扎实的一个 session。5–7 看时间，做不完顺延 ***REMOVED***19。**宁可 1–4 做透，不要 1–7 都做一半。**

---

***REMOVED******REMOVED*** 3. 工程纪律（session ***REMOVED***17 验证有效，照做）

- **多 agent 按目录边界并行**：后端 agent 只动 `web/backend/`，前端 agent 只动 `web/frontend/`，互不冲突。跨前后端的功能：先派后端定契约，再派前端对接。
- **不碰 `scripts/train_v2.py`** —— 别 session 的 in-flight 工作，working tree 里一直显示 modified，跳过它。
- **commit 边界**：显式 `git add <具体路径>`，禁 `git add -A` / `commit -a`。按目录/主题分 commit。
- **测试**：后端 `PYTHONPATH=web/backend .venv/bin/python -m pytest web/backend/tests/ -q`（基线 501）；e2e `PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_report_share.py -q`（基线 15）。每个功能配测试，三层验收（单元/集成/真浏览器 Playwright）。
- **真实环境验证**：涉及报告生成的，实跑一份完整报告（现在能跑完，~216s）。涉及钱（LLM 调用）的至少跑 1 次完整路径。
- **部署**：`gh workflow run "Deploy Beta Backend" --ref main` —— 这是高危生产部署，**需用户显式授权**，不要自己触发。部署后用 fingerprint 复验。

---

***REMOVED******REMOVED*** 4. 关键 gotcha

- **nginx SSE 已修**（session ***REMOVED***17）：`/api/(analyze|ask)/stream` 已有专门 location（buffering off + 600s timeout），报告能跑完。VPS 配置备份在 `/etc/nginx/conf.d/beta-structural.conf.bak-s17`。若再动 nginx 必须 `nginx -t` 通过才 reload。
- **`kb_v2_embeddings.npy` 未 L2 归一化**（norm 14–22）：读取侧 `SearchService._cosine()` 已防御，运行时正确。但若 B/A 要重算相似度，注意用 `_cosine`/`relevance_score`，别裸 `np.dot`。彻底修要重新导出归一化的 npy（属 `scripts/`）。
- **scope floor**：`ANALYZE_SCOPE_MIN_SIMILARITY` 默认 0.50（[0,1] 口径下的正交线）。别调到高于 search 展示的 relevance，否则 search/analyze 自相矛盾复发。
- **V4 徽章数据**：KB 里没有 SIBD-63/普适类/评审分元数据，徽章只能用 `meta.credibility` 的真实字段（similarity + v2 验证对数）。**禁止造假徽章**。A2/B 若要更强的「验证」标签，得先把验证数据真正接进 KB。
- **报告生成慢**：完整 9 段约 3–4 分钟。任何涉及实跑报告的测试给足 timeout（≥300s）。

---

***REMOVED******REMOVED*** 5. 用户授权阻塞（CC 推不动）

| 优先级 | 动作 | 说明 |
|---|---|---|
| 🔴 P0 | 轮换 OpenRouter API key | `web/backend/.env.bak-v1` 的 key 曾在 PUBLIC 仓库泄露（session ***REMOVED***17 已 untrack 但 key 已暴露）。去 OpenRouter 控制台轮换 |
| 🟡 | 触发部署 | `gh workflow run "Deploy Beta Backend"` 是高危操作，每次需用户授权 |
| 🟡 | 改 VPS nginx（若需要） | 共享多站主机，需用户显式授权 |

---

***REMOVED******REMOVED*** 6. 关键文件 / 文档

- `docs/sessions/SESSION-17-untapped-value.md` — A–G 的完整思考来源（**必读**）
- `docs/sessions/SESSION-17-value-optimization.md` — V1–V6（已完成）的背景
- `docs/sessions/SESSION-17-extension-directions.md` — 更早的路线盘点
- `docs/sessions/SESSION-17-prelaunch-checklist.md` + `SESSION-17-review-*.md` — 发布前 5 路审查
- `progress.md` — 全量进展时间线
- `scripts/dogfood_fingerprint.py` — 起手 fingerprint check
- 后端：`web/backend/api/{analyze,search,report}.py`、`web/backend/services/{search_service,report_store,scope_guard,v2_pairs}.py`
- 前端：`web/frontend/assets/js/{analyze,search,report,my-reports}.js`

---

***REMOVED******REMOVED*** 7. 起手指令（下个 session 直接说这句）

> 读 `docs/sessions/SESSION-18-HANDOFF.md`，跑 fingerprint check，然后按「执行排序」从 A2 开始做价值挖掘 A–G。
