# structural-isomorphism V4 后续深入路线图

**文档状态**：v0.1 规划稿（2026-05-13 起草，B 机 dadamini）
**前置状态**：V4 Layer 5 Phase 1-5 全部完成（2026-04-16 19:15 截止）
**最后 commit**：`f610dbb` Layer 5 Phase 5 null validation；之后做了 i18n round 1/2/3（`e41b02b` 最新）
**距离上次实质推进**：~4 周（4-17 → 5-13），期间重心在 renai-cross / ipos / openclaw

---

## 一. 当前家底（盘点）

### 1.1 方法论层（已就绪）

V4 完整管道 5 层：
| Layer | 内容 | 状态 |
|---|---|---|
| L1 节点抽取 | 180 现象节点（V1 KB 5000 条 + V2 3017 跨域对 + V3 191 deep analysis） | ✅ |
| L2 等价类发现 | 143 条边 → 23 个候选等价类（连通分量 + Louvain 亚社区） | ✅ |
| L3 LLM 不变量提取 | 8 个 manually curated + 15 个 LLM auto-curated（含置信度 badge） | ✅ |
| L4 跨域预测生成 | 27 条可验证预测（数值 band + 真实数据源 + 期刊目标） | ✅ |
| L5 实证验证 | 5 phases 全过（4 真实数据 + 1 null control） | ✅ |

### 1.2 实证结果（Layer 5 Phase 1-5）

| Phase | 系统 | 关键指标 | 结论 |
|---|---|---|---|
| 1 | USGS 全球地震 84k events | b=1.08±0.005 / Omori p=0.94±0.017 / R²=0.99 | ✅ canonical |
| 2 | S&P 500 1990-2025 9060d | α=3.00 (inverse cubic) / Omori p=0.29 (daily band) | ✅ 首次非物理 |
| 3v2 | DeFi Aave+Compound+Maker 43k | α∈[1.57,1.68] / p∈[0.69,0.76] | ✅ 跨协议 |
| 4 | mouse cortex DANDI 1.39M spikes | τ∈[2.17,3.00] / α∈[2.49,2.94] / γ=1.10±0.02 | ⚠️ 子临界 task-state |
| 5 | null validation（高斯/指数/Poisson × 3 + Poisson→Omori） | 4/4 全部正确拒绝 | ✅ 排除方法偏见 |

**已发表 paper（站内）**：4 篇（earthquake / stockmarket / defi / neural）+ null 写到方法论 footer。

### 1.3 产品层（已上线）

- **structural.bytedance.city**（V1+V2 主站，30 篇文档）
- **beta.structural.bytedance.city/classes**（V4 普适类页，23 类全渲染）
- **/paper/{slug}**（4 篇论文页面 + KaTeX 排版）
- i18n round 3 已全站中英切换

### 1.4 资产边界（B 机本地状态）

- ✅ GitHub clone 完整（74 commits / 252M）
- ✅ 关键数据全在：`data/` `v4/validation/` `v4/results/` `paper/` `plans/`
- ❌ `models/structural-v1/v2/`（782M，`.gitignore` 排除）— V1/V2 embedding 模型，V4 不依赖，VPS 已部署
- 站点 prod 在 VPS（`/root/Projects/structural-isomorphism/`）

---

## 二. 后续深入方向（按维度展开）

### 维度 A：科学层 — Layer 5 实证扩展（高密度产出）

**核心模式**：每个普适类做一个跨域实证 → 产出 1 篇 arXiv 子论文 + /classes 卡片 +1 个绿色 verified badge。

**A1. SOC 巨簇剩余跨域**（已有 4 个，目标 8-10 个）

| 候选 | 数据源 | 预测指标 | 估算单系统耗时 |
|---|---|---|---|
| **Phase 6 — GitHub 事件级联** | GH Archive bigquery（star / fork / commit 突发） | preferential attachment α / Omori-like 余震衰减 | 2-3d |
| **Phase 7 — 电网级联** | NERC TADS（北美电网中断公开数据集） | Motter-Lai 亚类专属验证；预期 α 范围 [1.4, 1.9] | 2d |
| **Phase 8 — 银行挤兑** | FRED bank failure dataset + FDIC + ECB stress test | Diamond-Dybvig 亚类；预期 α 离散事件层 [1.2, 1.6] | 3-4d |
| **Phase 9 — 社交传染** | Reddit Pushshift cascade / Twitter virality | Hawkes process Omori p / branching ratio | 2-3d |
| **Phase 10 — 山火** | CalFire / Copernicus EMS | 经典 SOC 系统，应严格匹配 BTW 沙堆模型 | 1-2d |
| **Phase 11 — 太阳耀斑** | GOES X-ray flux historical | Lu-Hamilton 1991 经典结果，pipeline 复现 | 1d |
| **Phase 12 — 流量拥堵** | PeMS / OpenStreetMap routing | 交通相变（与 #2 Hysteresis 一起） | 3d |

**A2. 其他普适类的首次实证**（每类至少 1 个）

| 普适类 | 优先候选系统 | 难度 |
|---|---|---|
| #2 Hysteresis (Preisach) | 交通拥堵 hysteresis loop（PeMS speed-density） | 中 |
| #3 Scheffer / Fold | 湖泊富营养化（USGS lake DO 公开数据） | 中 |
| #6 Copula tail dependence | 巨灾 + 股市同向尾部（FRED + NOAA） | 中高 |
| #7 Toggle switch | 合成生物学公开 dataset（Gardner 2000 重做） | 高（生物学专业） |
| LLM-提议的 5 类（extreme value / leaky IF / Akerlof / Markov fidelity / SIR contagion） | SIR 走 COVID openly published / Akerlof 走 used car market | 中 |

**A3. 方法论扩展**

- **Phase 13 — 时间分辨率扫描**：同一系统跑多个 bin factor（已在 mouse 上做），系统化推广，发现 scaling exponent 的尺度依赖 → 论文卖点
- **Phase 14 — 跨系统 universal collapse**：把 4 个已验证系统的 P(s) 曲线 rescale 到同一 master curve（finite-size scaling）→ 首次证明"普适类" 而非"4 个独立 power law"
- **Phase 15 — 反例库**：每次 null validation 失败的案例记录到 `v4/validation/null-controls/registry.jsonl`，下次新系统先比对

**预估**：A1 + A2 + A3 → ~25 个新实证 sprint，按 2-3d 一个，单干约 2-3 个月可吃完一半（约 12-15 个）。

---

### 维度 B：方法论加固 — 现有 23 个候选类的纵深

**B1. Layer 3 critic pass**（debug 模式）

现在 8 manual + 15 LLM curated 共 23 类，没有"反向 critic"。需要：

- 每类生成 3-5 个"看起来像但实际不是"的反例
- 跑 Opus critic agent 判定：是否真正同构 vs 表面相似（surface analogy）
- 输出 `layer3_critic_rejections.jsonl`，把误归类的成员剔除
- 预期：23 类中 15-18 类站得住，5-8 类需要拆分或丢弃

**B2. Layer 4 预测数值 band calibration**

现在 27 条预测都有"数值区间"但区间宽窄不统一。需要：

- 对每个数值预测：用 bootstrap / Monte Carlo / Bayesian credible interval 给出 95% CI
- 计算 "落在预测区间内 / 区间外 / 完全失配" 三态记分
- 已验证的 4 phase 反向回填评分

**B3. Multi-model ensemble**

V4 现在 Layer 3 完全靠 Opus。引入异构模型：

- DeepSeek R1 做 critic / reject pass（推理强项）
- Kimi K2.5 做 second curator pass（差异视角）
- 三模型投票通过的等价类标"high consensus"，单模型独有的标"speculative"
- 沿用 `~/CLAUDE.md` 推荐的 OpenRouter 路由

**B4. 反例正例显式声明**

每个等价类 yaml 文件加：
```yaml
positive_examples:  # 已验证属于此类
  - {phenomenon: ..., evidence_url: ...}
negative_examples:  # 看起来像但不是
  - {phenomenon: ..., reason: surface_analogy_only}
edge_cases:        # 临界，有争议
  - {phenomenon: ..., debate: ...}
```

这是 V3 时代缺的，做完后等价类描述质量大幅提升。

---

### 维度 C：学术发表 — 从站内 paper 升级到正式 arXiv

**C1. 合成 unified preprint**

把 Phase 1-5 合成一篇 arXiv：

- 标题候选："A pipeline for cross-domain validation of self-organized criticality: 5 systems, one method"
- 结构：Introduction → Pipeline → 4 case studies → null validation → Discussion → ~6000 字
- 估算耗时：1-2 天 LLM 生成稿件 + 5-7 天人审校改 + 投 arXiv 1 天
- 强卖点：**单一管道零调参跨 4 个真实系统 + 通过 null control**
- 期刊目标：arXiv preprint → 投 PRE / Nature Physics correspondence / Chaos

**C2. Solo papers 子序列**

每个 verified 系统单独发 arXiv：
- earthquake（已有站内稿，重写为 arXiv 格式）
- S&P 500（已有，arXiv 化）
- DeFi 跨协议（已有 v2，arXiv 化，3613 words 略短，扩到 4500）
- mouse neural（partial，需补充更多 session 验证再投）

每篇 1-2 周 turnaround，共 4 篇可在 Q3 内完成。

**C3. Taxonomy v2 论文**

23 个候选普适类 → 整理成正式 cross-domain taxonomy paper：

- 标题："A computational taxonomy of cross-domain universality classes from 3017 phenomenon pairs"
- 方法层：详细描述 V1-V4 pipeline
- 结果层：列出 8 个 well-established + 15 个 LLM-proposed + 5 个新候选
- 影响力目标：Nature Communications / Science Advances 候选
- 难度：高（需要 senior 物理学合作者背书，发表周期 6-12 月）

**C4. 红队 / Critic 论文**

把维度 B 的反例库和 critic 流程单独写成方法论 paper：
- "A reject-aware pipeline for cross-domain universality discovery"
- 卖点：不只发现，还系统化剔除 false positives

---

### 维度 D：产品层 — Phase Detector 落地

`plans/company-analysis-product.md` v0.2 已设计完整（5 功能 Screener / Report / Projections / Chat / Index API），但**未开工**。这是把科学成果商业化的接口。

**D1. MVP 阶段（4-6 周）**

- 选 100 家公司预计算 StructTuple（成本 ~$30-50 LLM）
- Postgres 索引 dynamics_family + critical_point_state
- 简单 filter UI + 30 秒 TL;DR
- 部署到 phase.bytedance.city（独立子域）

**D2. 拓展阶段（2-3 月）**

- 扩到 Top 500 全市场（A 股 + 美股 + 港股）
- Report 详情页（drill-down）
- 每周 RSS / 邮件订阅
- Free tier + paid tier（$15-49/月起）

**D3. B2B Index API**

- Structural Index™ 公开数据集（每月 snapshot）
- API 按 query / 按月订阅
- 目标客户：小型 hedge fund / VC / research seat

**判断**：D1 比 D2/D3 重要，D1 上线后看真实需求再决定是否做 D2。

---

### 维度 E：基础设施 / 工程化

**E1. Pipeline reproducibility**

- 现在 v4/ 下脚本散落，多个 phase 各自一套 `run.py`
- 需要：统一 `cli.py`，子命令 `validate <system>` `null-check <system>` `report <slug>`
- 单条命令重跑 phase X，给定 seed 完全可复现

**E2. Data versioning**

- 引入 DVC 或 git-lfs（针对 catalog.parquet / aave_v2_liquidations.jsonl 这种 >5MB 数据）
- 防止 git-filter-repo 那种事故（2026-04-16 commit b135717 教训）

**E3. CI / 回归测试**

- 每个 phase 一个 deterministic synthetic sanity test（10s 跑完）
- pytest -m sanity 全过才允许 push 到 v4/
- 对应 site smoke test 已存在（`db8ddd5`），扩展到 v4 计算管道

**E4. LLM 输出 guardrail**

- 现在 Layer 3 LLM JSON 偶尔漂移（unescaped quote bug 修过一次）
- 引入 Pydantic schema 校验 + jsonschema 在 critic 层做白名单
- 失败自动 retry + fallback to deterministic state machine fixer

---

### 维度 F：数据资产复活 — V1+V2+V3 → V4 的桥接

V1 模型（Silhouette 0.85, R@5 100%）+ V2 3017 跨域匹配 现在 V4 没充分用。

**F1. Embedding-driven candidate expansion**

- 用 V1/V2 模型为新进现象自动建议 nearest neighbors（不只 LLM）
- 同时 keep LLM curator pass
- 双源 candidate → 更高 recall

**F2. Active learning loop**

- V4 Layer 3 critic 拒绝的样本回流到 V1/V2 training set
- 重新 fine-tune embedding → R@5 可能突破 100%（更精细 ranking）
- 形成正反馈循环

---

### 维度 G：生态 / 影响力

**G1. 社区曝光**

- arXiv preprint 发后同步：Hacker News / Reddit r/science r/dataisbeautiful / Twitter
- 选 2-3 个最强卖点做 thread（"我用一个管道 0 调参跨 4 个系统验证了 SOC"）
- 给 SOC / criticality 学界（Plenz / Priesemann / Newman / Sornette）发 email + preprint

**G2. 开源**

- repo 已 PRIVATE — 考虑 v4/ 子目录开 PUBLIC subtree（结果数据 + pipeline 代码）
- LICENSE 已 MIT
- 写 reproduction tutorial（README + notebook）：30min 让别人复现 SOC × earthquake

**G3. 用户访问数据**

- structural.bytedance.city / beta. 接入 Plausible / 简单 access log
- 看哪些 paper 页 / 普适类 卡片最被点
- 反向指导 D1 产品（Phase Detector）做哪些功能

---

## 三. 优先级建议（基于"差异化 × 成本 × 转化"）

### 立刻能做（1-2 周，单 session 可吃下）

1. **Phase 6 GitHub 事件级联** — 数据公开易拉，1 篇站内 paper +1 个 verified badge（A1）
2. **B2 数值 band calibration** — 不需要新数据，把已有 27 条预测重写为 95% CI（B2）
3. **C1 unified preprint v0.1 草稿** — Opus subagent 一晚上写完，人审校 1 周（C1）

### 中期（1-2 月）

4. **Phase 7-9** — 电网 / 银行 / 社交（A1，每个 2-4d）
5. **D1 Phase Detector MVP** — 100 公司 StructTuple + Screener（D1）
6. **B1 Layer 3 critic pass** — 23 类 reject pass，定型 v2 taxonomy（B1）
7. **C2 4 篇 solo paper arXiv 化** — 已有站内稿改格式即可（C2）

### 长期（3-6 月）

8. **C3 Taxonomy v2 论文**（高难度高回报）
9. **D2 / D3 产品扩展 + B2B Index API**（D2 D3）
10. **F1 / F2 数据资产复活**（F1 F2）
11. **G1 学界 outreach**（G1）

---

## 四. 不建议做 / 慎做

- **V3 老 solver 方向**（已正式 deprecated，2026-04-14 被 Direct Opus 9/10 打穿）
- **Random new 普适类发明** — 没有真实数据支撑的新类一律不写入 taxonomy
- **D2/D3 大规模产品先行**（在 D1 MVP 没验证需求前不要扩）
- **公开 GitHub repo 全量**（v4/ 子树可，但 V1/V2 模型不公开，避免被滥用）

---

## 五. 第一个 sprint 建议

**B 机 session #N+1（约 8-10h）**：

1. 起手：`git pull` + 读本 roadmap + 看 progress.md（30min）
2. **Sprint A — Phase 6 GitHub 事件级联**（5h）
   - 拉 GH Archive bigquery（star / fork events，2020-2025 顶级 repo） 
   - 跑同一 pipeline：Clauset α / Omori p / synthetic null
   - 写 paper 5 站内
   - /classes SOC 卡片加第 5 条预测
3. **Sprint B — B2 数值 band calibration**（2h）
   - 把 layer4_predictions.jsonl 的 27 条预测加 95% CI
   - 已验证 4 phase 回填评分（in-band / out-band）
4. **Sprint C — C1 unified preprint v0.1**（2h）
   - Opus subagent 草稿（5000-6000 words）
   - 写到 `paper/v0-unified-soc-pipeline-2026-05-13.md`
5. **结尾**：commit + push + 写 `docs/sessions/structural-iso-session-N+1-end.md`

**预期产出**：1 个新 verified 系统 + 27 条预测带 CI + 1 篇 unified preprint v0.1 + 站内更新。

---

## 六. 待定决策点（需用户拍板再开工）

| ID | 议题 | 默认选项 |
|---|---|---|
| **D-struct-1** | unified preprint 投哪：arXiv only / arXiv + PRE / arXiv + Nature Phys correspondence | arXiv 先 + 看反响再投期刊 |
| **D-struct-2** | Phase Detector 产品先做 MVP 还是先把科学层吃透 | 科学层先吃半年（A1+B 维度），产品 MVP 排 Q4 |
| **D-struct-3** | v4/ 子树是否开 PUBLIC GitHub | 等 unified preprint 投后开 |
| **D-struct-4** | 学界 outreach 时机 | unified preprint v0.1 内审完成后 |
| **D-struct-5** | Phase 6 数据源（GH Archive 走 bigquery 还是 free monthly dump） | bigquery 快 + 已配额，~$10 内可控 |

---

**结尾**：这个项目的 moat 在科学层（Layer 5 cross-domain validation pipeline），产品层是 nice-to-have。建议未来 3 个月聚焦维度 A + B + C，把 SOC 巨簇吃透到 8-10 systems 验证 + unified preprint + taxonomy v2 → 此时项目的学术影响力和产品转化基础都到位。
