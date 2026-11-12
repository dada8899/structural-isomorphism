# Structural Isomorphism 全项目审计与下一阶段路线

> 日期：2026-07-11
>
> 范围：产品、用户体验、研究、数据/模型、工程、测试、部署与运营
> 运行状态权威入口：`NEXT_SESSION.md`

## 1. 执行摘要

项目的研究与工程资产很厚，但当前不是“缺更多功能”，而是缺一个可量化、可反馈、可证伪的主任务。多入口、多工具、多叙事同时争夺用户注意力，还把产品候选、LLM 判定、经验证据和科学结论混在一起。

下一阶段的唯一主产品应收敛为 **Validated Transfer Workbench（经验证的跨领域迁移工作台）**：

` 真实问题 → 适用性拒绝 → 结构指纹 → 跨域候选 → 证据/反证 → 最小实验 → 结果回写 `

Phase Detector 保持独立，定位为透明的研究预览与负结果案例，不与投资 alpha 绑定。论文不再扩大 universality claim，先发表“可拒绝、可复现的跨领域 scaling 验证协议”与负结果。

## 2. 当前功能地图

### 2.1 Structural Search / Workbench

- 自然语言问题、OOS guard、语义/BM25 混合检索。
- SSE 流式 Ask，9 节深度迁移报告。
- 结构映射、方法迁移、诊断、压力测试、struct lint、研究空白、insights/discoveries。
- 报告持久化、分享、反馈与 follow-up outcome 数据模型。
- 匿名历史/收藏；Auth、云收藏、Connections 为未完成 scaffold。
- 100 条中英配对评测、400 条 LLM graded qrels、冻结 baseline 与 CI contract。

### 2.2 Phase Detector

- 597 ticker demo snapshot，公司筛选、详情、对比、universality explorer。
- EWS meta/leaderboard、methodology、backtest、about/newsletter/onboarding。
- v0.2 负回测；当前是描述性研究快照，不是实时数据或投资信号。

### 2.3 研究与开发者资产

- Clauset MLE、alternative distributions、bootstrap、null controls、PASS/FAIL/INCONCLUSIVE ledger。
- SIBD-63、SOC 验证系统、universality taxonomy、pre-registrations。
- `soc-pipeline`、`guarded-llm`、`cross-judge`、`reject-aware-critic` 四个包。
- notebooks、tutorials、MCP、v4 研究管线、paper/release 资产。

## 3. 核心问题

### 3.1 产品与体验

1. 英文检索是实质性缺陷，不是轻微差距：冻结 baseline 的英文 type Hit@5 为 0.025，中英 Top-5 type Jaccard 为 0.0351。
2. 当前评测重 retrieval，却没有验证“建议是否可执行、实验是否启动、结果是否回写”。
3. 报告过长、首个价值出现过慢。应先在 10 秒内给 3 个候选摘要，用户选择后再生成深度报告。
4. Connections 是另一个社交产品，与核心 PMF 没有已证明的因果关系。
5. 纯 HTML beta 与 Next.js Phase 的导航、身份、视觉和数据状态容易持续漂移。

### 3.2 工程与可靠性

1. 原 CI/coverage/E2E 多处 `|| true`，“绿灯”不能证明安装、测试或构建成功。
2. 监控原先主要检查首页 HTTP 200，无法发现 KB 为空、英文退化、Phase API 失效或 mock 功能暴露。
3. 生产 Auth 实际只写 mock outbox，且曾允许固定 JWT fallback；必须在真实邮件交付前 fail closed。
4. beta 曾同时挂载一套 legacy Phase API，与独立 Phase 服务双轨，且存在旧模型硬编码与成本/输出门禁不一致。
5. 测试入口碎片化，root、backend、packages、retrieval、Phase 之间没有唯一 release gate。

### 3.3 学术与证据

1. “指数/分布相似”不等于“生成机制相同”；`UNIVERSAL-ACROSS-MATTER` 过强。
2. v0.5 的多个类依赖 synthetic/literature-calibrated anchors，且存在 single-session verdict。
3. 18 类、多参数、SPLIT/MERGE 与 post-hoc reparametrisation 带来多重比较和研究者自由度。
4. 只有少量明确时间锁定的 prereg，不能把全部 sweep 统称严格外部预注册。
5. 历史 embedding 评测按 pair 随机切分，同一 description 可跨 train/eval；100% Retrieval@5/10 不是泛化证据。
6. 400 条 qrels 来自单一 LLM judge，只能作开发集，不能作投稿金标准。
7. Phase v0.2 负回测不支持预测产品；其价值是透明 null result 和方法自我拒绝。

## 4. 产品策略

### 4.1 首发 ICP

首发只选“研究密集型产品经理/增长负责人”。他们有真实复杂问题，也能在 1–2 周内执行最小实验。不同时服务 PM、内容创作者、科研人员和投资者。

### 4.2 主体验

1. 首页只保留一个主 CTA：“描述一个卡住的问题”。
2. 先返回 3 个跨域候选、一句价值解释、证据/反证和置信等级。
3. 用户选择后才启动深度报告，默认先显示 one-page decision brief。
4. 报告必须产出一个 7 天内可执行的最小实验：owner、deadline、baseline、metric、stop condition。
5. 第 3/7/14 天回访，记录 `worked/partial/no_effect/too_early`。

### 4.3 企业路线（只在主闭环达标后）

- workspace/项目/成员/权限，团队问题库与决策日志。
- 每份报告写入数据、模型、prompt、代码和 artifact 版本。
- 先做飞书/Notion/Linear 导出，不先做完整内建项目管理。
- Connections 若重启，先做“组织内谁处理过同构问题”，不做陌生人社交。

## 5. 学术路线

### 5.1 首选方法论文

`A preregistered reject-aware pipeline for cross-domain scaling claims`

只聚焦冻结协议、全量 ledger、真实 SOC core、matched null 与真正 timestamped prereg negatives。贡献是让 LLM-in-the-loop science 能够拒绝错误假说，而不是宣称已发现大规模普适性。

### 5.2 次选实证论文

`Cross-domain scaling concordance under a fixed pipeline`

最多保留 3–4 个高质量真实系统，称 `concordant scaling signatures`，不称 universality。使用层级 meta-analysis、heterogeneity、leave-one-system-out 和 matched non-class controls。

### 5.3 学术硬门禁

- claim-evidence ledger 中每条 headline claim 必须连到 raw data、checksum、script、result、figure/table、commit/tag、seed 和 provenance。
- 幂律分析补齐 bootstrap GOF、tail n/xmin stability、alternative likelihood ratio 和依赖数据的 block bootstrap。
- 训练/评测按 type/domain/source group split，增加 leave-one-domain-out、leave-one-type-out 和 hard negatives。
- 产品 qrels 另增 3 位双盲人类标注者，Krippendorff alpha 目标 ≥0.67，专家裁决分歧。
- 至少 1 名复杂系统统计学家、每应用域 1 名专家、1 名计算复现 reviewer。

## 6. 分阶段路线与验收

### P0：可信核心（1–2 周）

- 英文 retrieval：query translation、multilingual embedding、hybrid retrieval、rerank 做冻结 A/B。
- 检索门禁不使用污染 type metric 冒充真实相关性。
- 修正 perf audit 口径，3 次中位数，再优化 companies/company/compare 移动 LCP。
- 生产 Auth/Connections/legacy Phase 未完成表面 fail closed。
- CI、coverage、E2E 和生产合成监控不得假绿。
- README/model/dataset/paper card 与 canonical manifest 一致。

验收：nDCG@5 绝对提升 ≥0.05 且 paired bootstrap CI 下界 >0；Success@5 提升 ≥0.08；英文-中文差距减半；OOS precision/recall ≥0.98；retrieval p95 ≤1.5s；移动 LCP ≤2.5s；真实 INP 代理 ≤200ms。

### P1：使用闭环（2–6 周）

- 首页与导航收敛为单一主任务。
- 先候选后报告；hypothesis/evidence/counter-evidence/confidence cards。
- 行动计划转为可跟踪实验，自动回访 outcome。
- 15–20 名首发 ICP 完成真实任务试用。

验收：有效候选人工接受率 ≥60%；深度报告启动率 ≥45%；完整生成率 ≥95%；行动项创建率 ≥35%；7 天实验启动率 ≥20%；14 天结果回写率 ≥15%；7 日复用率 ≥25%。

### P2：团队与研究网络（6–12 周，P1 达标后才启动）

- workspace、共享报告、组织内历史迁移检索。
- 飞书/Notion/Linear 导出、API/MCP、claim ledger 和外部审查。
- 根据 5 个团队连续 4 周使用、50+ outcome 案例和外部专家复核决定付费与 Connections 是否成立。

## 7. 明确暂停

- 新页面、新工具、陌生人 Connections、支付扩张。
- 实时投资、alpha、预测能力叙事。
- 在外部 review、可复现包和 claim ledger 完成前投递 v0.5 或扩大 v0.6。
- 在真实使用闭环达标前扩展 API/团队协作/付费。

## 8. 完成定义

“整体没有问题”不等于没有 backlog，而是：所有公开功能都是真实可用或明确标记为 unavailable/experimental；所有核心闭环有业务级合成监控；任何绿色门禁都确实覆盖它所声称覆盖的范围；产品 claim 不超过生产数据，学术 claim 不超过独立证据。
