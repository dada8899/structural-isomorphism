# KB 覆盖度量化审计 — 2026-05-24

> 用户反馈"经常找近似现象却找不到对应"。本审计专攻**内容缺口**侧，定量回答：KB 里到底缺什么、缺多严重、补哪 3 块 ROI 最高。匹配算法问题另议。

---

## 0. 数据基线

| 文件 | 条数 | 字段 | 说明 |
|---|---|---|---|
| `data/clean-expanded.jsonl` | 5689 | `type_id`, `description` | 描述最全，缺 domain/name |
| `data/kb-5000-merged.jsonl` | **4475** | `id`, `name`, `domain`, `type_id`, `description` | 主分析对象（最接近文档说的 4443） |
| `data/clean.jsonl` | 1214 | + `type_name` | type_id → 中文名词典源 |

- `type_id`：1–84 的结构分类（线性比例 / 幂律 / 临界阈值 …），完整 84 类
- `domain`：自由文本，kb-5000-merged 里出现 **183 个** unique domain（含别名）

---

## 1. 当前覆盖统计

### 1.1 学科大类分布（基于 kb-5000-merged 4475 条，22 学科聚合）

```
economics      ████████████ 703  (15.7%)
engineering    █████████    495  (11.1%)
earth          ███████      385  ( 8.6%)
CS             ██████       345  ( 7.7%)
physics        █████        313  ( 7.0%)
biology        █████        299  ( 6.7%)
chemistry      ███          206  ( 4.6%)
medicine       ██           123  ( 2.7%)
psychology     ██           116  ( 2.6%)
linguistics    ██           112  ( 2.5%)
sociology      ██           103  ( 2.3%)
political      ██           102  ( 2.3%)
ecology        █             83  ( 1.9%)
culture_arts   █             81  ( 1.8%)
law/military   █             65  ( 1.5%)
education      █             55  ( 1.2%)
neuroscience   █             53  ( 1.2%)
agriculture    ▏             46  ( 1.0%)
urban          ▏             37  ( 0.8%)
anthropology   ▏             35  ( 0.8%)
history        ▏             30  ( 0.7%)
math_stats     ▏             18  ( 0.4%)
(unmapped)     ███          670  (15.0%)  ← domain 命名未归一
```

**结论**：经济 / 工程 / 地球 / CS / 物理 / 生物 6 大类占 56%；社会科学 + 人文一共 ~12%；neuroscience / urban / ecology 都 < 2%。

### 1.2 现象类型（type_id 1–84）分布

- 头部 5 名（占 14.8%）：`03 对数关系 174`、`08 幂律增长/衰减 150`、`18 正反馈 144`、`06 指数衰减 124`、`25 一阶相变 123`
- 尾部 10 名（每个 < 15 条）：`77 长程相关/1f 噪声 8`、`80 小波变换 8`、`81 对偶性 8`、`79 傅里叶变换 9`、`84 维度灾难 9`、`65 形式语言与语法 11`、`74 元胞自动机 11`、`68 自组织临界性 12`、`60 群/对称 12`、`39 变分原理 12`
- type_id × discipline 交叉表共 **84 × 21 = 1764** 个 cell，其中 **1023 个 = 0**（58% 空白）

### 1.3 时间 / 空间尺度（用关键词正则归类）

| 时间尺度 | 数量 | 空间尺度 | 数量 |
|---|---|---|---|
| **unspecified** | **3693** | **unspecified** | **3192** |
| week-month | 290 | molecular | 418 |
| year | 205 | tissue/organism | 210 |
| hour-day | 151 | cellular | 195 |
| second-minute | 76 | national | 148 |
| μs–ms | 26 | population | 120 |
| ≤1ns | 18 | global | 104 |
| geological | 9 | urban | 42 |
| century | 7 | cosmic | 26 |

→ KB 描述里**绝大多数没有显式时间/空间尺度标签**（>70%），导致"跨尺度同构搜索"无 metadata 可用。这是 schema 缺陷，不是内容缺陷，但直接影响"近似但找不到"。

### 1.4 数据成熟度

显式标注实证 / 理论 / 案例的 < 135 条（3%）。绝大多数 description 是案例叙述体，**无 confidence flag**。

---

## 2. 稀疏 / 缺失领域 Top 20

按"该 cell 是经典理论应有 × KB 实际 = 0 或 < 3"判定。

| # | 领域 / 现象 | KB 命中 | 经典出处 |
|---|---|---|---|
| 1 | **linguistics × 大多数 type_id**（22/84 = 0；正反馈/指数增长/扩散方程/相变/级联在语言学里全空） | 多数为 0 | Newman / Croft 语言变化 |
| 2 | **neuroscience × 多 type_id**（指数增长/衰减、扩散、网络级联、混沌、时滞反馈全 0） | 多数为 0 | Beggs–Plenz neural avalanche |
| 3 | **urban × 大多数 type_id**（标度律、扩散、级联、相变在城市学里几乎缺） | 多数为 0 | Bettencourt urban scaling |
| 4 | **psychology × 临界 / 指数 / 时滞 / 混沌**（社会比较、情绪传染缺机制层标签） | 多数为 0 | Centola social contagion |
| 5 | **ecology × 临界 / 级联 / 反馈**（保育生物学只 35 条） | 稀疏 | Scheffer tipping points |
| 6 | **city scaling law / Kleiber**（异速生长） | type_id 69 仅 13 条 | West/Brown/Enquist |
| 7 | **Zipf law / Heaps law（专有名词）** | 0 / 0 命中（口语化版本 6 命中） | Zipf 1949 |
| 8 | **萤火虫同步 / Kuramoto** | 0 / 1 命中 | Strogatz Sync |
| 9 | **Zachary karate / preferential attachment（专名）** | 0 / 2 | Newman Networks |
| 10 | **气候 tipping point 专名** | 0（口语化 11 命中） | Lenton/Rockström |
| 11 | **Turing pattern 专名** | 0（"斑图" 8 命中） | Turing 1952 |
| 12 | **细胞自动机 / 生命游戏** | 2 命中 | Wolfram NKS |
| 13 | **opinion polarization 在 sociology** | 一边 0 | Macy/Centola |
| 14 | **meme drift / 文化漂变** | 0 | Cavalli-Sforza |
| 15 | **AMOC / 大西洋环流崩溃** | 8 命中但 type_id 23 × earth 仅 20 | IPCC AR6 |
| 16 | **LLM 涌现 scaling law**（type_id 72 涌现 仅 55，AI 占比 < 5） | 1 命中 | Kaplan / Wei et al. |
| 17 | **forest fire SOC（精确版）** | 1 命中 | Drossel-Schwabl |
| 18 | **`type_id` 77/79/80/81/83/84**（1/f 噪声、傅里叶、小波、对偶、NP、维度灾难）全 < 15 条 | — | 算法/分析工具型机制空白 |
| 19 | **anthropology / history / law / math_stats** 整体覆盖 < 1% | 35/30/65/18 | 长期被遗忘的学科条 |
| 20 | **`unmapped 670`**：crypto/DeFi、量子计算、AI/DL、太空技术、基因编辑等热门新领域因 domain 命名分裂没归到主学科，搜不到时容易显得"缺" | — | schema/命名问题 |

---

## 3. 跨域同构对子覆盖测试

10 对用户最可能搜的"近似现象"，验 KB 两侧是否都有：

| Pair | 左侧 | 右侧 | 状态 |
|---|---|---|---|
| 1 | flash crash 闪崩（7） | 地震余震（10） | ✅ 两侧都有 |
| 2 | opinion cascade 观点级联（**0**） | forest fire 森林火灾（8） | ⚠️ **一边缺** |
| 3 | neural avalanche 神经雪崩（9） | market liquidity shock（18） | ✅ |
| 4 | bank run 银行挤兑（6） | epidemic outbreak（4） | ✅ |
| 5 | Zipf 词频幂律（4） | 城市规模幂律（7） | ✅ |
| 6 | flocking 鸟群（3） | crowd 人群（9） | ✅ |
| 7 | synaptic plasticity（5） | social tie 强度（4） | ✅ |
| 8 | protein folding（36） | cooling crystallization（25） | ✅ |
| 9 | genetic drift 遗传漂变（11） | meme/文化漂变（**0**） | ⚠️ **一边缺** |
| 10 | phase transition 水相变（30） | social revolution 社会突变（**0**） | ⚠️ **一边缺** |

**3/10 对子有一边缺**，且缺的全部集中在 **sociology / linguistics / culture** 侧——印证 §2 的稀疏判断。

---

## 4. 扩展优先级建议

按 **「用户最可能搜 × 当前最稀疏 × 数据获取性」** 三维打分。

### Top 1 ★★★ — Linguistics 全谱补足（+150 条）
- **理由**：22/84 个 type_id 在 linguistics 完全 0；Zipf / Heaps / 语言变化 S-curve / 词汇衰减 / 句法演化都是经典案例，且用户对子测试有 3 个缺口落在 culture/language 侧。
- **数据可获取性**：高。WALS、PHOIBLE、Google Ngrams、Zipf 词频数据都是公开 dataset。
- **关键现象 candidates**：词频 Zipf 律、词汇半衰期、语言扩散波（wave model）、grammatical change S-curve、phonological merger、句法 island constraint、code-switching cascade、loanword diffusion、语言死亡阈值。

### Top 2 ★★★ — Neuroscience × 跨 type_id 补足（+80 条）
- **理由**：neuroscience 只有 53 条，且基本只覆盖 type_id 23/42，**指数衰减 / 扩散方程 / 时滞反馈 / 混沌 / 一阶相变 / 网络级联**全 = 0；但用户做"市场 ↔ 大脑"同构搜索是高频需求（neural avalanche ↔ liquidity shock 已是经典对）。
- **数据可获取性**：高。OpenNeuro、Allen Brain Atlas、SfN 教材现象级清单。
- **关键现象**：synaptic depression（指数衰减）、calcium wave（扩散）、heart rate variability 1/f 噪声、epileptic seizure（一阶相变）、EEG gamma synchrony、cortical traveling wave、dopamine RPE 时滞反馈、连接组小世界。

### Top 3 ★★ — Urban / Computational Social Science（+100 条）
- **理由**：urban 仅 37 条，社会学 103 条但 type_id × discipline 大量空白；用户 §3 的对子 2/9/10 全在这个方向缺口；同时是 Bettencourt / Barabási / Watts 等经典著作的核心案例库。
- **数据可获取性**：中-高。CitySDK、SafeGraph、Twitter/Weibo 公开数据集、政府开放数据。
- **关键现象**：城市标度律（GDP/人口/犯罪/专利的超线性）、交通拥堵相变、电网级联停电、suburb sprawl 扩散、housing bubble 一阶相变、opinion polarization 临界、virality cascade、urban heat island 反馈。

---

## 5. 横向 schema 建议（非内容缺口，但放大"找不到"）

1. **加 `discipline` 字段**：当前 183 个 domain 自由文本里有 `加密货币与DeFi` / `加密货币/DeFi` / `crypto` 等 5 种写法 → 归一后 670 条 unmapped 可挂回主学科。
2. **加 `time_scale` / `space_scale` 字段**：现在 70%+ 描述里时间/空间尺度只能靠正则推断，加显式标签后跨尺度搜索可行。
3. **加 `confidence_tier` 字段**：empirical / theoretical / anecdotal 三档，匹配返回时可降权 anecdotal。
4. **专有名词 alias 表**：Zipf / Kuramoto / Turing / Bettencourt / Kleiber 等 30+ 经典命名应在 KB 外维护一个 alias 索引（即使中文描述里没写，也能命中）。

---

## 6. 关键结论（一句话版）

> 当前 4475 条 KB 主要覆盖了**经济/工程/物理/生物**的中频现象；**linguistics / neuroscience / urban / sociology** 在中高频 type_id 上**结构性空白**（type_id × discipline 矩阵 58% cell = 0）。用户感受到的"找不到对应"主要来自这三块缺口 + 70% 描述无 time/space scale 元数据 + 专有名词缺 alias。补全 Top 3 优先级（+330 条）可覆盖最常见的跨域搜索路径。

— end —
