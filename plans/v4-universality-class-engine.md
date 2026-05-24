# V4：普适类发现引擎（Universality Class Discovery Engine）

> 创建日期：2026-04-15
> 状态：规划中，等待启动
> 前任 V4：`v4-solver-direction.md`（已废弃，retrieve+transform 方向被 04-14 可行性测试证伪，但其决策逻辑作为历史保留）
> 作者：达达 + CC 讨论整合

---

## 0. 一句话定义

**V4 不再做"给 B 问题找 A 解法"的 pair 级求解（老 V4 方向），而是把 V1/V2/V3 已经产出的 63 个 A 级候选升级为"普适类地图"——从 pair 级离散发现跃迁到等价类级统一抽象**。

---

## 1. 为什么这是正确的 V4（相对于老 V4）

老 V4 被 04-14 的可行性测试正确地否决：Direct Opus 在 10 个跨域求解问题上 9/10 胜过 retrieve+transform pipeline。结论是对的，但解读需要更深一层：

**老 V4 被打穿的真正原因**不是 retrieval 不值得做，而是"**它在错误的抽象层上和 Direct Opus 竞争**"——比谁更会在 pair 级做变量映射和变形预测。这一层 Opus 有模型规模优势，pipeline 加进去只会束缚它。

新 V4 从根本上换了个位置：

| 维度 | 老 V4 | 新 V4 |
|---|---|---|
| 抽象层 | pair 级（A ↔ B） | 等价类/普适类级（{A, B, C, D, ...}） |
| 产品形态 | 问题求解器 | 知识抽象引擎 |
| 和 Opus 关系 | 正面竞争 variable mapping | 把 Opus 当基元调用 |
| 输入 | 用户的 B 问题 | V1/V2/V3 已产出的 63 个候选 + KB |
| 输出 | top-3 B 解法 | 普适类目录 + 共享方程 + 可验证预测 |
| 论文类型 | 工程/方法论文 | 跨学科科学发现 |
| 成功判据 | beat GPT-5 求解 baseline | 至少 1 个普适类被实证验证 |
| 单人可行性 | 可行但周期长 | 可行且周期更短（直接用已有数据） |

**关键判断**：新 V4 不和任何 LLM 直接竞争，而是把 LLM 当成"普适类发现流水线上的一道工序"。这是"building on top of" 而不是 "competing against"，对个人/小团队项目尤其适合。

---

## 2. 核心概念

### 2.1 等价类（equivalence class）
项目在 V3 的 A 级结果里已经自然产生了等价类——**"清算级联的链上流动性危机"一个节点连接了至少 6 个其他现象**（闪崩、保证金螺旋、地震、银行挤兑、对手方风险、社会级联）。如果同构是合格的等价关系，这 6+1 个现象构成一个等价类。但项目目前没有把它当成等价类显式暴露，只展示成 6 条独立的 pair。

### 2.2 普适类（universality class）
等价类是数据观察，普适类是对这个等价类底层规律的数学刻画。物理学中已经建立的普适类（以本项目已暴露的 hub 为例）：

**候选普适类 #1：阈值级联 + 自组织临界性（SOC）**
- 已暴露成员：DeFi 清算 / 地震 / 闪崩 / 保证金螺旋 / 银行挤兑 / 社会级联
- 共享方程（V3 已写出）：`∑ⱼ K_ij · δⱼ > threshold_i → failure_i + stress transfer`
- 共享标度律：Gutenberg-Richter 幂律（规模分布 P(s) ∝ s^(-τ)，τ ≈ 1.5）+ Omori 律（时间衰减 n(t) ∝ 1/t^p）
- 共享临界性：平均场分支过程，ξ → 1
- 物理学名：Self-Organized Criticality (Bak-Tang-Wiesenfeld 1987) + branching process universality
- 物理学成熟度：40 年研究积累，数学完备，但"非物理系统属于这个类"的实证案例稀少

**这是一个活的案例，不是假设的。** V3 的数据已经把这个普适类的 6 个跨域实例摆在桌面上了。V4 的工作是把它从"6 条 pair 结果"升级为"1 个带完整数学结构 + 可验证预测的普适类"。

### 2.3 关键不变量（invariant）
V4 要从每个等价类里提取的核心对象。分类：

- **标度律（scaling law）**：幂律指数、分形维数、标度函数
- **对称性（symmetry）**：连续/离散对称群、破缺方式
- **守恒量（conserved quantity）**：对应 Noether 定理产生的守恒律
- **拓扑不变量（topological invariant）**：欧拉示性、绕数、亏格
- **临界指数（critical exponents）**：α, β, γ, δ, ν, η 等
- **变分原理（variational principle）**：最小作用、最大熵
- **阈值结构（threshold structure）**：分支过程临界、percolation 阈值

每个普适类由一组共享不变量定义。V4 的核心交付物是**不变量 → 普适类**的映射关系。

---

## 3. 评估产品上的影响（"V4 对用户到底带来什么"）

当前 discoveries 页面的用户体验：

> 用户看到 63 个离散的 "A ↔ B" 跨域发现，每条带评分和解释。感受：有意思但不系统。

V4 交付后的用户体验：

> 用户看到 M 个普适类卡片（预估 5-12 个），每个卡片展示：
> - 类名（如"阈值级联普适类"）
> - 核心成员（N 个跨领域现象）
> - 共享方程（LaTeX 渲染）
> - 共享不变量清单
> - 跨越的领域图谱
> - 已知的物理学原型（如 Bak-Tang-Wiesenfeld 模型）
> - 未验证的理论预测 + 可测数据集链接

这是一个**叙事完全不同**的产品：
- 老版本："我发现了 63 个跨域类比"（好玩但不学术）
- 新版本："我发现了 M 个跨学科普适类，每个都有数学结构和可验证预测"（Nature 级别叙事）

---

## 4. 架构（4 层 pipeline）

```
V1/V2/V3 A 级 + B+ 结果 (63 + ~34 候选)
    │
    ├── Layer 1: 等价类图构建
    │   - 节点 = 现象
    │   - 边 = 高分 pair (score ≥ 4.5)
    │   - 图清洗：同义节点合并（LLM judge）
    │   - 输出：candidate graph
    │
    ├── Layer 2: Hub 检测 + 社区发现
    │   - degree centrality
    │   - connected components
    │   - Louvain / 谱聚类
    │   - 过滤：≥3 成员、跨 ≥2 领域
    │   - 输出：M 个候选等价类
    │
    ├── Layer 3: 共享不变量提取（Opus 作工序）
    │   - 对每个候选类：
    │     (a) 收集成员 pair 的 shared_equation 集合
    │     (b) LLM 判断是否能抽象为统一方程（master equation）
    │     (c) 从物理学普适类库（人工维护的 taxonomy）里 match 候选
    │     (d) 提取共享不变量清单
    │     (e) 给出置信度 + 反例检测
    │   - 输出：M 个普适类 candidate with master equation + invariants
    │
    └── Layer 4: 可验证预测生成
        - 对高置信度普适类，枚举已知的物理学定律/标度律
        - 翻译为非物理领域的可测预测（如"DeFi 清算规模应服从 τ ≈ 1.5 幂律"）
        - 匹配现有数据集（DeFi: Dune/DeFiLlama; 社会: Twitter/GDELT; 生态: GBIF）
        - 输出：每个普适类 1-3 条具体预测 + 数据来源 + 验证 pipeline 设计
```

### Layer 1 细节：图构建
- 输入：`results/v2m-a-rated.jsonl` (19) + `v3/results/v3-a-rated.jsonl` (20) + V1 tier-1 (24) + B+ 扩展（34）
- 节点合并：同一现象在 V1/V2/V3 可能有不同表述，用 LLM judge pairwise 合并（如"DeFi 清算级联" ≡ "链上流动性危机"）
- 边权重：max(V1_score, V2_score, V3_score) 或加权平均
- 去重：同一 pair 在多管道都出现则合并为一条边
- 输出 schema：
```json
{
  "nodes": [
    {"id": "defi_liquidation_cascade", "canonical_name": "...", "domain": "..."}
  ],
  "edges": [
    {"src": "...", "dst": "...", "score": 4.8, "shared_equation": "...", "pipelines": ["V3"]}
  ]
}
```

### Layer 2 细节：Hub 检测
- 算法：NetworkX 的 degree centrality + connected components + Louvain
- 人工阈值（初版）：
  - hub 定义：degree ≥ 3
  - 普适类候选：connected subgraph with ≥ 3 nodes and ≥ 2 domains
- 质量排序信号：
  - 跨域数（越多越好）
  - 尺度跨度（量子/分子/细胞/生态/社会，覆盖越多越好）
  - 平均边 score（越高越好）
  - 成员数（越多越好）
- 输出：`v4/results/candidate_classes.jsonl`

### Layer 3 细节：不变量提取
这是 V4 最需要 LLM 工序精细设计的一步。参考 MiroThinker 的 Local/Global Verifier 模式做双层验证：

- **Step 1（generator，Opus）**：给定等价类所有成员 + 所有 shared_equation，生成候选 master equation
- **Step 2（critic，GPT-5 或 Gemini，独立模型）**：检查 master equation 能否真的从每个成员方程化约得出，标注不能化约的成员为"伪同构"
- **Step 3（物理学 taxonomy match，Opus）**：从维护好的 ~30 个已知普适类库里 match 最接近的一个，输出 top-3 候选 + 理由
- **Step 4（反例检测，Opus）**：主动构造"看起来像这个类但其实不是"的反例，检查 master equation 是否错误地包括了反例
- 输出：每个等价类 → 1 个 master equation + 不变量清单 + 已知普适类 match + 置信度

物理学 taxonomy 库（手动维护）：
- 阈值级联 / SOC
- 平衡态临界（Ising, XY, Heisenberg, percolation）
- 非平衡动力学（KPZ, directed percolation, reaction-diffusion）
- 标度不变流（分形生长 DLA, Kolmogorov 湍流）
- 相变通用性（Landau 理论, 对称破缺类型）
- 群体同步（Kuramoto, Winfree）
- 生物振荡（FitzHugh-Nagumo, Hodgkin-Huxley, Belousov-Zhabotinsky）
- 预测-修正反馈（Kalman filter, Bayesian updating）
- 多重均衡与自我实现预期（Diamond-Dybvig）
- 幂律优先连接（Barabási-Albert, preferential attachment）
- 最大熵 / 最大似然优化
- 变分原理（least action, entropy production）
- 随机过程共享类（random walk, Brownian motion, Lévy flight）
- 信道容量 / 信息不等式
- 神经振荡与同步（balanced E-I networks）
- 演化博弈 / 复制方程
- ...（约 30 类）

### Layer 4 细节：可验证预测
对每个高置信度普适类，跑一遍"标度律翻译"：

```
若 X 普适类在物理学中有定律 L(x₁, x₂, ..., xₙ)
且 X 普适类在非物理领域 D 中有成员 M
那么 M 应服从 L 的翻译版本 L'(y₁, y₂, ..., yₙ)
其中 yᵢ = map(xᵢ)（通过 variable_mapping 字段提供）
```

输出格式：
```json
{
  "universality_class": "SOC_threshold_cascade",
  "member": "DeFi 清算级联",
  "source_law": "Gutenberg-Richter: P(s) ∝ s^(-τ), τ ≈ 1.5",
  "translated_prediction": "DeFi 清算 USD 规模分布服从 τ = 1.5 ± 0.2 的幂律",
  "test_method": "极大似然拟合 vs KS 检验",
  "data_source": "DeFiLlama liquidations dataset (2020-2026)",
  "expected_sample_size": "N ≥ 10,000 清算事件",
  "null_hypothesis": "随机复合分布 / 指数分布",
  "alternative_hypothesis": "τ ∈ [1.3, 1.7] 幂律",
  "effort_estimate": "1-2 周",
  "paper_target": "Nature Physics / PRL"
}
```

### Layer 5 细节：实证验证与 Phase 命名

Layer 5 把 Layer 4 产出的可验证预测真正拿真实世界数据跑一遍。由于每次验证都锁定**一个具体的领域目标**（地震 / 股市 / DeFi / 神经雪崩 / ...），我们用"Phase N"给每一轮验证编号，每个 Phase 对应**一篇独立的 preprint + 一条 /classes 卡片上的 ✅ 已实证标签**。

命名规则：
- **Phase 编号 = 该领域在 Layer 5 序列里的完成顺序**（不是优先级，也不是难度）
- 每个 Phase 都遵循统一流程：数据抓取 → 同一 pipeline 跑拟合 → VERDICT 报告 → arXiv-style paper → /classes 卡片更新
- 工件统一放在 `v4/validation/<class-id>-<domain>/` 目录，如 `soc-earthquake/`、`soc-stockmarket/`、`soc-defi/`

已完成：
| Phase | 目标 | 数据 / 样本量 | 主要结果 | 状态 |
|---|---|---|---|---|
| **1** | USGS 全球地震（物理 ground truth） | 84,724 events 2020-2025 | b = 1.084, Omori p = 0.941, R² = 0.99 | ✅ paper 1 上线 |
| **2** | S&P 500 日收益（第一个非物理） | 9,060 交易日 1990-2025 | α = 2.998 (inverse cubic law), Omori p = 0.286 (daily) | ✅ paper 2 上线 |
| **3** | DeFi 清算（Aave V2 + Compound + Maker） | 43,065 events 2020-2024 | α ∈ [1.57, 1.68], Omori p ∈ [0.69, 0.76] (1-hour), 跨 3 协议收敛 | ✅ paper 3 v2 上线 |

Phase 4+ 候选目标（按可得性和工作量排序）：

| 备选 Phase | 目标 | 数据源 | 预估工时 | 预期结果 | 学术意义 |
|---|---|---|---|---|---|
| **A** | 神经雪崩 | Beggs-Plenz 2003 公开 + Allen Brain 电生理集 | 1-2 天 | α ≈ 1.5（文献值），验证可复现 | 中——已有文献对比，SOC 跨生物学扩展 |
| **B** | 森林火灾规模 | USGS / MODIS fire perimeter | 2-3 天 | α ≈ 1.3-1.5 | 中——经典 SOC 系统 |
| **C** | 电网级联故障 | NERC TADS 公开报告 | 3-5 天 | Motter-Lai 预期 τ ≈ 2.0 | 高——首次实证 Motter-Lai 亚类 |
| **D** | GitHub issue / commit 级联 | GHArchive.org | 2-3 天 | 可能幂律，但 SOC 是否成立未知 | 高——新领域，open question |
| **E** | Wikipedia 编辑级联 | Wikipedia API + Pushshift | 3-4 天 | 同上 | 中-高 |
| **F** | 巨灾保险理赔 | 国内银保监 / FEMA CED 公开数据 | 5-7 天 | 尾部幂律预期成立 | 中——已有 Cat bond 理论 |
| **G** | 社会抗议/示威级联 | GDELT / ACLED 事件库 | 2-3 天 | unknown | 高但 noise 大 |
| **H** | 跨链桥清算 / Curve pool depeg | Etherscan + Curve Subgraph | 3-4 天 | 预期与 Aave 类似但更稀疏 | 低——扩展而非新类 |

**推荐下一步**：Phase 4 优先选 **A 神经雪崩**——最快出结果、有文献基准、能把 SOC 簇从"物理+金融"扩展到"生物"，叙事完整度再升一档。

每个新 Phase 完成后应同步：
1. 在本表格"已完成"行追加一行
2. 在 `v4/validation/<类目录>/VERDICT-YYYY-MM-DD.md` 写 verdict
3. 在 `web/frontend/assets/data/papers/` 放 paper.md
4. 更新 `build_site_data.py` 里对应 predictions 条目的 status 为 "✅ 已验证"，`paper_url` 指向新 slug
5. 重跑 `build_site_data.py` → rsync → /classes 卡片自动亮绿色"✅ 已实证"

---

## 5. 成功判据

### 必须达到（MVP 通过线）
- [ ] Layer 1 产出一张清洗后的图，节点数 ≥ 50，边数 ≥ 60
- [ ] Layer 2 检出 ≥ 5 个等价类（≥3 成员、≥2 领域）
- [ ] Layer 3 为 ≥ 3 个等价类产出 master equation + 通过 critic 检验
- [ ] Layer 4 产出 ≥ 3 条具体可测预测（每条有数据源和检验方法）
- [ ] 至少 1 条预测进入实证验证阶段（有数据，有初步结果）
- [ ] discoveries 页面新增"普适类视图"，至少展示 5 个等价类卡片

### 卓越达到（值得写论文）
- [ ] 至少 1 个等价类被实证验证（如 DeFi 清算确实服从 τ ≈ 1.5 幂律 + Omori 1/t^p）
- [ ] 论文初稿投出（Nature Physics / PNAS / PRL 级别）
- [ ] 至少 1 个等价类是物理学 taxonomy 里**未被标注的跨域实例**（如"原来没人知道 X 也属于 SOC 类"）

### 明确的停止信号
- ⛔ Layer 1 之后没有任何 hub degree ≥ 3（说明 V1/V2/V3 的结果太分散，V4 前置不成立）
- ⛔ Layer 3 的 critic 否决率超过 80%（说明 master equation 抽象不起来，只是表面相似）
- ⛔ 选定的第一个实证预测在 2 周内无法获得合格数据（说明预测过于空泛）
- ⛔ 实证验证的预测失败，且失败理由是"普适类归类错误"（说明 pipeline 系统性问题）

**遇到任一停止信号，立即暂停 V4，回到 V3 数据上反思问题。**

---

## 6. 阶段与时间表

| Phase | 内容 | 工期 | 依赖 | 交付物 |
|---|---|---|---|---|
| P0 | 物理学 taxonomy 手工构建（~30 类） | 3-5 天 | 无 | `v4/taxonomy/universality_classes.yaml` |
| P1 | Layer 1 图构建 + 节点合并 + 去重 | 1 周 | V1/V2/V3 results | `v4/results/graph.json` |
| P2 | Layer 2 hub 检测 + 社区发现 | 3-5 天 | P1 | `v4/results/candidate_classes.jsonl` |
| P3 | Layer 3 不变量提取 pipeline（含 generator + critic + taxonomy match） | 2 周 | P2 + P0 | `v4/results/classes_with_invariants.jsonl` |
| P4 | Layer 4 预测生成 + 数据源 match | 1 周 | P3 | `v4/results/predictions.jsonl` |
| P5 | 产品层：discoveries 页面新增普适类视图 | 1 周 | P3 | `site/pages/universality-classes/*` |
| P6 | 实证验证第一个预测（SOC × DeFi 清算） | 2-4 周 | P4 | 数据分析 notebook + 中期结果 |
| P7 | 论文初稿 + 投稿 | 4-6 周 | P6 | arXiv preprint + 投稿 |

**总工期**：P0-P5 约 6-8 周（MVP），P6-P7 再 6-10 周（论文），全程 3-4 个月，单人可行。

**关键里程碑**：
- **Week 4**：第一张 hub 图 + 第一批等价类候选（能回答"V3 到底找到了哪些普适类"）
- **Week 8**：产品层上线，网站从"63 个 pair"升级为"M 个普适类"（用户叙事换血）
- **Week 16**：SOC × DeFi 实证验证有结论（成功则启动论文，失败则反思）

---

## 7. 和 V1/V2/V3 的关系

V4 **不替代** V1/V2/V3，而是**加在它们上面的一层抽象层**。

```
V4 (普适类层)                    ← 新增
  ↑
V3 (StructTuple + LLM rerank)   ← 已完成
V2 (embedding 精筛)              ← 已完成
V1 (embedding 广筛)              ← 已完成
  ↑
KB (4443 现象)                    ← 基础
```

- V1/V2/V3 生产"pair 级同构发现"
- V4 消费这些发现，生产"等价类/普适类"
- 未来 V5 可以在 V4 之上做"跨普适类的元理论"（如"这两个不同普适类都具有分形结构，背后是否有更深的统一"）

V4 的输入是已有数据，**不需要扩 KB、不需要改 pipeline、不需要重训 embedding**。这是它最大的执行优势——所有前置条件都已就绪。

---

## 8. 风险与缓解

### 风险 1：Hub 是检索假象
**问题**：V3 的 hub（清算级联连 6 个）可能只是因为"DeFi 相关现象在 KB 里被反复表述"导致的人为聚集，不是真正的结构 hub。

**缓解**：
- Layer 1 的节点合并必须严格，同义节点合并为一个
- Hub 的成员**必须跨 ≥2 个领域**才算合格
- 对每个 hub 做 ablation：去掉某个 V1/V2/V3 管道后 hub 是否还存在

### 风险 2：Master equation 是表面套壳
**问题**：LLM 很容易把"都是级联"这种表面描述写成一个伪方程。

**缓解**：
- Layer 3 必须有独立模型的 critic（GPT-5 或 Gemini）
- Critic 的任务是**证伪**而不是证成
- Master equation 必须能从每个成员方程通过具体变量替换化约得出
- 引入反例检测：主动构造"看起来像但不是"的反例

### 风险 3：实证验证失败
**问题**：P6 阶段可能发现 DeFi 清算其实不服从 τ = 1.5 幂律（因为数据量不够、市场结构特殊等）。

**缓解**：
- P4 阶段同时准备 3 条候选预测（不只押宝一条）
- 失败本身是可发表的（"我们证伪了 A 普适类适用于 X 领域"）
- 有备选普适类可切换（若 SOC 在 DeFi 上失败，可以试平衡态相变 + 银行挤兑）

### 风险 4：被 AI for Science 行业提前抢跑
**问题**：AI for Science 是热门领域，其他团队可能在做类似事情。

**缓解**：
- 项目的独特优势是"**已有 63 个 A 级候选作为冷启动**"，其他团队没有这个数据
- 优先产出 discoveries 页面的产品层（可见证据）
- 论文里显式引用本项目 V1/V2/V3 作为 discovery source，确立方法论时间戳

### 风险 5：单人带宽不够
**问题**：P0-P7 全流程约 3-4 个月，可能被其他项目打断。

**缓解**：
- P0-P2（前 2 周）产出就足以支撑一次 blog post + 网站升级，是第一个可分享的里程碑，即使后面停了也有价值
- P3-P4 可以每次只做一个等价类，不需要一次做完所有
- P6 实证验证可以外包给科研协作者（不一定自己做数据分析）

---

## 9. 和"10-discovery-after-isomorphism.md"的关系

项目现存文档 `site/docs/10-discovery-after-isomorphism.md` 明确说了发现同构后的四件事：
1. 搬解法 → V1 阶段重点
2. 做预测 → V2 阶段尝试
3. 找隐藏变量 → V3 阶段探索
4. **做统一 → V4 阶段触碰**

**新 V4 正是在做"第四件：统一"**。老 V4（solver direction）其实是在做"第一件：搬解法"的自动化，是错位的。新 V4 回到了项目原始设计文档里指定的 V4 任务。

这一层"和项目早期自洽性"的论证很重要——它说明新 V4 不是临时拍脑袋，而是**项目三个月前就规划好的方向**，只是老 V4 走偏了一步。

---

## 10. 即时行动清单（启动前两周）

**P0 + P1 并行启动**：

### 用户侧（达达）
- [ ] 审核本 plan，确认方向、边界、成功判据
- [ ] 决定是否立即启动（vs. 等别的项目告一段落）
- [ ] 提供物理学 taxonomy 种子：5-10 个你最熟的普适类 + 典型实例（冷启动 P0）
- [ ] 确认产品层（P5）是否要在 beta 站还是主站发布

### 执行侧
- [ ] 创建 `~/Projects/structural-isomorphism/v4/` 目录结构：
  - `v4/taxonomy/` — 物理学普适类库
  - `v4/results/` — pipeline 产出
  - `v4/scripts/` — pipeline 代码
  - `v4/validation/` — P6 实证验证工作目录
- [ ] P1 脚本骨架：`v4/scripts/build_graph.py`（读 V1/V2/V3 results → 产出 graph.json）
- [ ] P0 taxonomy schema 定稿（基于第 4 节 Layer 3 的 30 类清单）
- [ ] 先选 1 个已经看起来最成熟的 hub（SOC × DeFi 清算）做 end-to-end 贯通，验证 pipeline 每层都能跑出东西再扩展

### Day 1 的具体动作
```bash
cd ~/Projects/structural-isomorphism
mkdir -p v4/{taxonomy,results,scripts,validation}
cp plans/v4-universality-class-engine.md v4/README.md
# 然后写 v4/scripts/build_graph.py
```

---

## 11. 备忘：为什么这件事现在就应该做

1. **前置条件已满足**：V1/V2/V3 的 63 个 A 级候选就是 V4 的输入，不需要额外采数据
2. **已有明确 hub 证据**：V3 的清算级联一个节点连 6 个现象，不是假设性的
3. **物理学背书**：SOC 是成熟普适类，不用发明新数学
4. **叙事升级巨大**："发现 63 个 pair" → "发现 M 个普适类"，论文 tier 跨档
5. **单人可行**：所有工作在 LLM API + Python + 现有数据上完成，不需要训模型、不需要大算力
6. **可验证**：P6 阶段有明确的数据集和统计检验，不是空话
7. **停止条件清晰**：第 5 节的停止信号让它不会变成无底洞项目
8. **老 V4 让位**：老 V4 已被证伪，V4 这个 slot 是空的，不需要和别的规划抢资源

**项目从 V1 到 V3 走的是"把 pair 发现做得更准"的路线，V4 是第一次换方向——从 precision 追求转向 abstraction 追求**。这是项目的决定性跃迁，值得作为接下来 3-4 个月的主线。

---

## 附录 A：第一个端到端验证的 SOC × DeFi 案例

作为 P3-P7 的贯穿示例，预先写出完整执行路径作为 MVP 脚本的测试用例。

### A.1 等价类定义
```yaml
class_id: SOC_threshold_cascade
name: 阈值级联自组织临界类
members:
  - id: earthquake_coulomb_triggering
    domain: 地质学
  - id: defi_liquidation_cascade
    domain: 加密货币/DeFi
  - id: flash_crash_liquidity_spiral
    domain: 金融市场微观结构
  - id: margin_spiral_deleveraging
    domain: 金融市场微观结构
  - id: bank_run
    domain: 传统金融
  - id: social_cascade_failure
    domain: 计算社会科学
domains_covered: 5
scale_span_orders: 10  # 秒级清算 → 千年地震
```

### A.2 Master equation 候选
```
系统状态：N 个耦合元件，每个元件有状态 sᵢ 和阈值 θᵢ
动力学：dsᵢ/dt = f(sᵢ) + ∑ⱼ K_ij · g(sⱼ)
破裂规则：若 sᵢ > θᵢ → 触发 cascade，重置 sᵢ，把 Δsᵢ 按 K_ij 分配给邻居
临界条件：平均分支因子 ξ = <∑ⱼ K_ij> → 1
```

### A.3 不变量清单
- Gutenberg-Richter 幂律 P(s) ∝ s^(-τ)，τ = 1.5（平均场值）
- Omori 衰减律 n(t) ∝ 1/t^p，p ≈ 1（平均场值）
- 临界指数 β, ν, η 对应 mean-field directed percolation
- 分形维数 d_f = 4（平均场值）
- Waiting time 分布 Pareto 尾

### A.4 翻译到 DeFi 的可测预测
1. **清算规模分布**：单次清算级联的总 USD 规模服从 τ = 1.5 ± 0.2 幂律（拟合 MLE + KS 检验）
2. **级联间隔分布**：大清算后的次生清算频率衰减服从 Omori 1/t^p，p ≈ 1
3. **传染网络度分布**：清算触发图（A 清算 → B 被触发）的度分布服从幂律

### A.5 数据源
- **主源**：DeFiLlama liquidations API（2020-2026，所有主流协议）
- **补充**：Dune Analytics 自定义查询（逐块清算事件）
- **预期样本量**：≥ 50,000 清算事件
- **分析工具**：powerlaw Python package（Clauset 2009 方法）

### A.6 论文骨架
- **题目**：Earthquakes in Code: Self-Organized Criticality Governs DeFi Liquidation Cascades
- **摘要**：We show DeFi liquidation cascades exhibit the same Gutenberg-Richter scaling and Omori-law aftershock decay as seismic fault networks, providing the first high-frequency empirical test of branching-process SOC universality outside geophysics.
- **目标期刊**：Nature Physics / PRL / PNAS
- **预估工期**：数据准备 2 周 + 分析 2 周 + 写作 4 周 = 8 周
- **单人可行**：是

### A.7 成功/失败判据
- **成功**：τ ∈ [1.3, 1.7] 且 Omori p ∈ [0.8, 1.2]，两者同时满足
- **部分成功**：仅其中一个标度律成立（值得一篇方法论文而非物理论文）
- **失败**：两个都拒绝零假设 → SOC 不适用 DeFi，回到 taxonomy 重找
- **失败也有价值**：发一篇"为什么 DeFi 看起来像但不是 SOC"的 negative result，比沉默更好

---

**文档到此结束。这份 plan 是 V4 的规划锚点，启动后所有执行细节记录到 `v4/README.md` 和 `v4/progress.md`，本 plan 保持不动作为决策依据。**
