# 公司分析产品 · 完整 Plan

**文档状态**：v0.1 草案
**日期**：2026-04-15
**作者**：达达 + Claude
**父项目**：structural-isomorphism（V1+V2+V3 pipeline 已就绪）

---

## 零. TL;DR

一个**面向商业分析师的结构化跨域 insight 生成工具**。

给定一家公司（ticker 或描述），系统自动提取其"结构签名"，并从物理学/生物学/生态学/复杂系统等**非商业领域**检索 3-5 个数学上同构的框架，生成一份带方程映射、历史先例、红队反驳、可观测指标的分析报告。

**不是**：Bloomberg 替代品、AI 量化交易系统、自动化研报生成器、Chatbot。
**是**：一个"把你没想到的角度摆到你面前"的**差异化 thesis 生成器**，让分析师 30 分钟获得 3 个 non-obvious 视角。

---

## 一. 定位

### 1.1 一句话定位

> **"用物理学、生物学、生态学的视角看你的目标公司——看见其他分析师看不见的结构动力学。"**

### 1.2 产品名候选

- `Structural Intel` — 品牌中性
- `Isomorph` — 学术感
- `跨域研究` — 中文朴素
- `Beyond Analog` — 英文有力度
- `Second Brain for Analysts` — 营销向

**暂定**：`Structural Intel`，英文 StructInt，中文"结构情报"。

### 1.3 为什么是这个定位

三个选择的拒绝理由：

| 拒绝的定位 | 拒绝原因 |
|---|---|
| "AI 研究助手" | 已被 Perplexity / Tegus / AlphaSense 占据，同质化，无 moat |
| "量化信号工具" | 需要回测数据 + 历史验证 + 合规风险 |
| "全自动 DCF 生成器" | 建模部分是 commodity，大厂会很快 copy |
| "公司画像平台" | 沦为数据 terminal，打不过 Bloomberg |

三个选择的接受理由：

| 接受的定位 | 接受原因 |
|---|---|
| "结构化跨域 insight 工具" | 没人做；技术基础已在 V2/V3 里；niche 但真实 |
| "每天给你 1-3 个差异化角度" | 内容驱动，不依赖数据竞争 |
| "thesis red-team 工具" | 避免 confirmation bias 是普遍痛点，没人专门解决 |

### 1.4 最重要的 anti-positioning

**不要做的 5 件事**：
1. 不做"数据"——让 Bloomberg / FactSet 做
2. 不做"预测数字"——让 Consensus / VisibleAlpha 做
3. 不做"screening 筛股"——让 Koyfin / Simply Wall St 做
4. 不做"问答 chatbot"——让 Perplexity / Claude 做
5. 不做"自动化报告生成"——让 AlphaSense / Tegus 做

**只做一件事**：给定一家公司，返回 **3-5 个来自非商业领域的数学框架**，每个框架包含：
- 方程 + 变量到这家公司具体指标的映射
- 该框架预测的 **3 个情境**（base / bull / bear）
- **2-3 个历史先例**（商业界曾经被此框架正确解释的真实公司）
- **具体可观测的预警信号**（分析师应该监控财报哪一行）
- **框架失效的 3 种场景**（避免 cargo culting）

---

## 二. 用户画像（3 个 Persona）

### Persona 1：Alice · 独立 Substack 分析师

- 35 岁，原买方分析师，自己开 Substack 一年
- 订阅 1,200 人，付费 85 人（$10/月）
- 每周写 1-2 篇公司深度分析
- 核心痛点：**每周都要找新的差异化角度**，但自己的知识库有上限
- 愿付：**$149/月** 换 1 篇/周的结构化 insight
- 使用场景：周三晚上写本周分析前，用工具生成 3 个角度，挑 1 个深耕

### Persona 2：Ben · 小型对冲基金分析师

- 28 岁，$80M AUM long/short fund 的初级分析师
- 覆盖 ~20 只股票，每月写 3-5 篇更新
- PM 希望他"说点别人没说过的"
- 核心痛点：**共识信息太多，non-consensus insight 稀缺**
- 愿付：**$299/月 个人订阅** 或 **$1,500/月 团队 5 人**
- 使用场景：季报前生成结构化红队报告，季报后生成"结构变化"分析

### Persona 3：Carol · VC 投资分析师

- 30 岁，早期 VC fund 初级合伙人
- 每月看 30-50 家公司，出 5-10 份 memo
- 核心痛点：**预测创业公司的长期结构**（很难用历史 comp 推演）
- 愿付：**$199/月** 或 **$99/月 轻量版**
- 使用场景：看项目时快速匹配结构孪生，识别这家公司"像生态系统里哪种物种"

### 共性需求

- 都写**长文本分析**（非 dashboard 型用户）
- 都有**内容产出压力**（需要差异化 insight）
- 都是**个人采购**决策（$100-500/月可以 self-serve）
- 都是**文字型思考者**（理解框架，不只是 dashboard）

**目标全球 TAM**：
- 独立分析师/Substack 财经作者：~5k 人
- 小型 buy-side 分析师：~20k 人
- VC/PE 分析师：~15k 人
- 公司战略研究员：~50k 人
- 认真的零售分析师：~100k 人

**合计可触达 TAM**：~190k 潜在用户

假设 5% 转化率、平均 $150/月 ARPU → TAM = $17M ARR 上限

**现实目标**（3 年内）：**捕获 1% = $170k ARR**（约 900 付费用户）

---

## 三. 核心产品功能

MVP 里只做 3 个功能，不多不少。

### 功能 1：结构化公司分析报告（核心）

**输入**：
- 公司 ticker（如 `NFLX`、`PDD`、`700.HK`）
- 或公司描述（自然语言 200-2000 字）
- 可选：用户当前的 memo 草稿

**处理**：
1. 抓取公司 5 年财务数据（revenue, margin, growth rate, cash, debt 等）
2. 抓取最近 90 天新闻/filings 摘要
3. LLM 提取公司的 **StructTuple**（state_vars, dynamics_family, feedback_topology, boundary_behavior, timescale, critical_points）
4. 在 KB 中匹配 top 20 结构孪生
5. LLM rerank 到 top 5（排除同领域）
6. 生成带方程、映射、历史案例、预警信号的完整报告

**输出**：2-3 页结构化 Markdown/PDF 报告
- Section 1: 这家公司的结构签名（可视化 StructTuple）
- Section 2-4: 3 个跨域框架 × 各 400 字
- Section 5: 红队 vulnerabilities（3 个）
- Section 6: 可观测预警信号（5-8 个具体指标）
- Section 7: 历史结构孪生（3 个成功 + 2 个失败案例）

**技术链路**：复用 V3 StructTuple 抽取 + V3 matcher + LLM rerank

**预期耗时**：生成一份报告 60-120 秒

---

### 功能 2：Thesis Red Team（防御性）

**输入**：用户上传自己的 bull/bear 研报（PDF / Markdown / 粘贴文本）

**处理**：
1. LLM 提取 thesis 的核心假设（通常 5-15 个）
2. 对每个假设抽取其结构（"持续增长"、"网络效应护城河"、"管理层能力"等）
3. 在 KB 中找**结构相同但失败的案例**
4. 生成红队分析：哪 3 个假设最脆弱

**输出**：
- 每个脆弱假设对应 1-2 个历史失败结构孪生
- 每个假设的 bear scenario 量化估计
- "如果要你 short 这家公司，你会 short 哪个假设"

**技术链路**：LLM-based 假设抽取 + 反向结构检索（专找失败案例）

**独立价值**：即使不用功能 1，这个功能本身是独立卖点。

---

### 功能 3：结构变化追踪（留存）

**输入**：用户订阅一个公司 watchlist（设定 10-30 只）

**处理**：
1. 每周自动重新抓数据
2. 比较 StructTuple 的关键字段变化（dynamics_family shift / feedback strength change / boundary approach）
3. 检测 "critical slowing down" 信号（方差扩大、自相关上升）
4. 触发告警时生成短报告：**这家公司的结构发生了什么变化**

**输出**：
- 每周邮件 digest：watchlist 里哪 2-3 家公司结构发生显著变化
- 每家公司附 30 秒 TL;DR + 链接到完整分析

**独立价值**：**这是 recurring value**。功能 1、2 是 one-shot 交易，功能 3 创造订阅留存的理由。

---

### 不做的功能（明确拒绝）

- ❌ 股价预测（合规风险 + 准确度问题）
- ❌ 估值模型（DCF / Multiples）（commodity）
- ❌ 同行比较表（大家都有）
- ❌ 管理层评分（主观 + 被起诉风险）
- ❌ 自动买卖信号（合规 + 品牌污染）
- ❌ Chatbot 对话（失焦）
- ❌ 多语言支持（MVP 只做中英文）

---

## 四. 实现架构

### 4.1 系统架构图

```
┌──────────────────────────────────────────────────────────┐
│                   User Interface (Web)                    │
│   - Landing page + 3 core flows                           │
│   - Report viewer (Markdown + KaTeX)                      │
│   - Watchlist management                                  │
│   - Auth (Google OAuth / Magic Link)                      │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend                          │
│   /api/report      → Generate full report                 │
│   /api/redteam     → Analyze a thesis                     │
│   /api/watchlist   → CRUD + weekly digest trigger         │
│   /api/auth        → OAuth callbacks                      │
└──────┬───────────┬───────────┬───────────┬───────────────┘
       │           │           │           │
       ▼           ▼           ▼           ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ Company  │ │Structural│ │   KB     │ │  LLM     │
│   Data   │ │Extractor │ │Retriever │ │Generator │
│  Layer   │ │  (LLM)   │ │          │ │  (LLM)   │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
      │            │            │            │
      ▼            ▼            ▼            ▼
┌───────────────────────────────────────────────┐
│              PostgreSQL + Redis                │
│  - users, watchlists, reports, cache          │
│  - Phenomena KB (4443 + 500 finance curated)  │
│  - Business case library (300 tagged cases)   │
│  - Pre-computed StructTuples for top 500 cos  │
└───────────────────────────────────────────────┘
```

### 4.2 核心管线（Company → Report）

```
Input: ticker="NFLX"
   │
   ├─► [1] Fetch financials (SEC EDGAR / FMP API)
   │       → 5y revenue, margin, growth, cash, debt, headcount
   │
   ├─► [2] Fetch recent news (NewsAPI / RSS)
   │       → 最近 90 天 top 20 news headlines + summaries
   │
   ├─► [3] LLM extract company StructTuple
   │       prompt: "Given this company's financials and context,
   │                extract its structural signature using schema X"
   │       → state_vars=[subs, ARPU, content_lib, churn]
   │         dynamics_family="logistic_saturation + network_cascade"
   │         feedback_topology="positive (content→subs→rev→content)"
   │         critical_points=[international saturation at ~750M]
   │
   ├─► [4] KB retrieval (V3 matcher, same dynamics_family)
   │       → top 20 phenomena sharing structural signature
   │       → filter out business-domain matches (we want cross-domain)
   │       → keep top 10 from physics/bio/ecology/network
   │
   ├─► [5] LLM pairwise rerank
   │       → for each of 10, produce shared_equation + variable_mapping
   │       → keep top 5 with highest specificity scores
   │
   ├─► [6] Historical twin search
   │       For each of top 5 structures, find 2-3 historical companies
   │       that were explained by this structure (Blockbuster / Nokia / ...)
   │       Source: curated business case library
   │
   ├─► [7] Red team generation
   │       For each structure, generate "how this framework could
   │       mislead" + 3 failure modes
   │
   └─► [8] LLM final report synthesis
           Combine all above into 2-3 page structured Markdown
           with specific numbers, equations, cited cases
           
Output: Report object (Markdown + PDF) → served to user
```

### 4.3 技术栈（最小复杂度）

| 层 | 选型 | 理由 |
|---|---|---|
| **Frontend** | Next.js + Tailwind | 快，SEO 友好 |
| **Backend** | FastAPI（Python，复用 V3）| 技术连续性 |
| **DB** | Supabase（Postgres + Auth + Storage）| 一站式，省运维 |
| **Cache** | Redis（upstash）| 服务器less |
| **LLM** | OpenRouter 路由（主用 Claude Sonnet 4.6 + Haiku 4.5）| 成本控制 |
| **Data APIs** | SEC EDGAR（免费）+ FMP（$15/月）+ NewsAPI（$99/月）| 起步够用 |
| **Hosting** | Vercel（前端）+ Railway/Render（后端）| 个人可负担 |
| **Analytics** | PostHog（免费版）| 用户行为追踪 |
| **Email** | Resend（免费额度）| 周度 digest |

**总运行成本**（100 个付费用户规模）：
- Hosting: $50/月
- DB: $25/月
- Data APIs: $150/月
- LLM: ~$300/月（平均 3 份报告/用户/月，每份 ~$0.10-0.30）
- Email: $0（免费额度内）
- **合计**: ~$525/月

100 用户 × $149 = $14,900 MRR → 毛利率 ~96%

### 4.4 复用现有 V3 的部分

| V3 资产 | 复用方式 | 修改需求 |
|---|---|---|
| `kb-expanded-struct.jsonl`（4443 条）| 作为底层 KB | 过滤出 physics/bio/ecology/network 子集（~2500 条）|
| `extract_structtuple.py` | 扩展为公司结构抽取 | 加 finance 字段：asset_class, business_model, moat_type |
| `matcher.py` | 复用 dynamics_family 硬匹配 + MMR | 加 cross-domain bonus |
| `kb-expanded-struct.jsonl` 的 StructTuple schema | 直接使用 | 无 |
| V3 A-rated 的 20 个 discoveries | 作为 "best of" 展示素材 | 无 |

**不复用的部分**：
- V1 embedding（太弱）
- V2 embedding（需要 retrain 或换掉）
- 现有 beta 站 UI（重新设计，更 content-first）

---

## 五. 数据规划

### 5.1 需要的数据清单

| 数据类型 | 用途 | 规模 | 来源 |
|---|---|---|---|
| **跨域现象 KB** | 检索池 | ~3,000 条 | 现有 V3 KB + 扩展 |
| **商业案例库** | 历史结构孪生 | ~300 条 | 手动 curate（MVP）|
| **公司财务数据** | StructTuple 抽取 | 按需拉取 | SEC EDGAR + FMP |
| **公司新闻** | Context 补充 | 按需拉取 | NewsAPI |
| **行业动力学模板** | 垂直场景预设 | 10-15 个 | 手动 curate |
| **经典金融经济框架** | 基线对照 | ~50 个 | 教科书提取 |

### 5.2 数据源详细规划

#### 5.2.1 跨域现象 KB（4443 → 3000 精选）

**起点**：现有 `v3/results/kb-expanded-struct.jsonl` 的 4443 条

**筛选策略**：
- 保留 dynamics_family 非 Unknown 的 2625 条（59%）
- 剔除明显和公司分析无关的（粒子物理、天体物理、纯数学）
- 补充 300-500 条 finance-relevant 空白：
  - 经济学经典：Minsky、Fisher、Kondratieff 周期
  - 博弈论：Nash、Schelling segregation、Polya urn
  - 网络科学：preferential attachment、small-world
  - 行为金融：prospect theory、herding、anchoring
  - 生态学：Allee effect、invasive species、trophic cascade
  - 流行病：SIR、SEIR、superspreaders
  - 物理：SOC、fold bifurcation、critical slowing down
  - 信息论：channel capacity、redundancy、coding limits

**最终目标**：~3,000 条高质量现象，每条带完整 StructTuple

**成本**：~$20 LLM 费用（用 Kimi 批量抽取新增 500 条）

#### 5.2.2 商业案例库（300 条手动 curate）

这是 **MVP 最重要的数据资产**。没有这个，系统只能给抽象框架，不能给"这家公司曾经也这样"。

**来源**：
1. **经典商业失败案例**（100 条）：Blockbuster、Kodak、Nokia、Sears、Borders、Polaroid、Radio Shack、Toys R Us、Blackberry...
2. **经典商业成功转型**（50 条）：Netflix DVD → 流媒体、IBM 大机 → 服务、Microsoft Cloud 转型、Apple iPod → iPhone
3. **近期显著案例**（50 条）：Peloton 泡沫、Zoom 2020-2023、Beyond Meat、WeWork、Robinhood、Snowflake、SoFi、Bird
4. **中国独特案例**（50 条）：拼多多增长、美团骑手网络、滴滴监管、教培行业、房地产链条、新茶饮周期
5. **金融危机样例**（50 条）：LTCM、雷曼、Silicon Valley Bank、Terra/Luna、三箭资本

**每条数据结构**：
```json
{
  "case_id": "BLOCKBUSTER-2010",
  "company": "Blockbuster",
  "period": "2000-2010",
  "outcome": "failure",
  "narrative": "从 9000 店鼎盛期到 2010 破产",
  "structural_signature": {
    "dynamics_family": "Network_cascade",
    "feedback_topology": "delayed_negative",
    "critical_points": ["Netflix 2007 launches streaming", "fold bifurcation in DVD demand"],
  },
  "key_mechanism": "固定资产重 + 订阅模式慢 + 被轻资产对手反向利用",
  "predicted_by_frameworks": [
    "technology S-curve",
    "critical slowing down in declining market",
    "fold bifurcation with no recovery path"
  ],
  "lessons": "资产重 + 正反馈衰退结构 = 一旦进入衰退不可逆",
  "sources": ["HBS Case 812-116", "WSJ 2010 coverage"]
}
```

**成本**：手动 curate 300 条 × 30 min = 150 小时。**MVP 阶段先做 50 条**，上线后边运营边扩。

**可外包**：找 MBA 学生每条 $5-10 curate。成本 $1,500-3,000。

#### 5.2.3 公司财务数据

**免费数据源优先级**：
1. **SEC EDGAR**（美股，免费）- filings + financial statements
2. **AKShare**（A 股 + 港股，免费 Python 库）
3. **Yahoo Finance**（免费，非官方 API）
4. **StockAnalysis.com**（免费网页抓取）
5. **Wikipedia infobox**（公司基础信息）

**付费数据源（上规模后）**：
1. **Financial Modeling Prep**（$15/月起）- API 友好
2. **Alpha Vantage**（$50/月起）- 多市场
3. **Polygon.io**（$29/月起）- 美股为主

**抓取范围**：
- 5 年季度财务（revenue, COGS, OpEx, EBIT, FCF, debt, cash）
- 近 3 年 KPI（subscribers、users、ARPU、CAC、churn，如披露）
- 最近年报 + 季报的 MD&A 文本
- 最近 90 天新闻 headline + 摘要

#### 5.2.4 新闻 / 定性数据

**MVP 方案**：
- **NewsAPI**（$99/月）：主流英文媒体聚合
- **Feedly API**（$99/月）：RSS 聚合
- **Google News RSS**（免费）：针对 ticker 的新闻流

**中国公司**：
- **东方财富网**（免费网页抓取）
- **雪球用户讨论**（免费 API，非官方）
- **Wind**（付费，太贵先不用）

#### 5.2.5 行业动力学模板

针对主要垂直（SaaS、DTC、Marketplace、Fintech、半导体、新能源、生物医药、游戏、教育、媒体），每个垂直预设：
- 典型 state_vars 列表
- 典型 dynamics_family
- 该垂直常见的 critical_points
- 该垂直的 3-5 个经典失败案例

**成本**：每个垂直 2-4 小时 curate × 15 垂直 = 30-60 小时。

**可外包**：专门请一位懂行业的 MBA 一周完成。成本 $1,500-3,000。

### 5.3 数据更新策略

| 数据类型 | 更新频率 | 触发方式 |
|---|---|---|
| 跨域现象 KB | 每月追加 10-20 条 | 用户反馈驱动 |
| 商业案例库 | 每周追加 5-10 条 | 用户 request / 新闻热点 |
| 公司财务数据 | 每季度全量刷新 | 财报公布后 T+3 |
| 公司新闻 | 每天增量 | 定时任务 |
| 行业模板 | 每季度 review | 手动 |

---

## 六. 能实现到的效果

### 6.1 用户能感知到的 5 个核心 Moment

1. **初次输入 ticker → 30 秒后看到报告**
   - 读到一个"从没想过"的跨领域框架
   - 感受："哇，这个视角真的是我之前没想到的"

2. **读到 shared_equation 和 variable_mapping**
   - 发现框架有具体方程而不是廉价类比
   - 感受："这不是文科类比，是数学"

3. **读到历史结构孪生案例**
   - 看到"Blockbuster 2010 也是这个结构"
   - 感受："原来失败是可以预测的"

4. **读到红队部分**
   - 自己的 bull thesis 的弱点被明确指出
   - 感受："还好没早点买"或"这就是我之前忽略的"

5. **周度 digest 邮件触发**
   - 某只 watchlist 公司的结构发生变化
   - 感受："工具帮我盯着了"

### 6.2 量化目标（12 个月）

| 指标 | 3 个月 | 6 个月 | 12 个月 |
|---|---|---|---|
| Waitlist | 300 | 1,500 | 5,000 |
| 免费试用用户 | 100 | 500 | 2,000 |
| 付费用户 | 10 | 50 | 200 |
| MRR | $1.5k | $7.5k | $30k |
| 流失率 | — | 15%/月 | 8%/月 |
| NPS | 30 | 45 | 50 |
| 每周活跃 | 30% | 45% | 55% |

**Kill criteria**：
- 3 个月 waitlist < 100 → 市场 cold，停
- 6 个月付费 < 20 → 转化失败，停
- 12 个月 MRR < $10k → 规模不够，转为 side project

### 6.3 技术指标目标

| 指标 | MVP | Stable |
|---|---|---|
| 报告生成时间 | < 120s | < 60s |
| 报告质量 (1-5) | 3.5 | 4.2 |
| 用户"有 insight"反馈率 | 50% | 75% |
| 非共识角度比例（vs 一致预期）| 40% | 60% |
| 红队有效指出风险比例 | 40% | 65% |

---

## 七. 分阶段路线图

### Phase 0：验证（Week 1-2，零成本）

**目标**：用 0 代码证明市场真实性

**任务**：
1. 用现有 V3 + 手动 prompting 为 10 家知名公司生成 structural analysis（NFLX, NVDA, PDD, BYD, Tesla, 美团, 理想, 京东, Snowflake, Shopify）
2. 每份 1,500-2,500 字
3. 发到：
   - Substack（个人 newsletter）
   - X/Twitter（pinned thread）
   - 雪球（长文区）
   - 小红书（笔记形式）
   - Hacker News（英文版）
   - 少数高质量 Reddit（r/SecurityAnalysis, r/ValueInvesting, r/investing）

**衡量**：
- 转发、评论数
- "这是什么工具"的询问数
- 主动订阅邮件的数量

**投入**：~20 小时（生成 + 发布）

**Go / No-Go**：
- ≥ 200 人主动询问 → 继续 Phase 1
- 50-200 → 再发 10 篇确认
- < 50 → 回到论文路径

### Phase 1：MVP（Week 3-6）

**前提**：Phase 0 通过

**任务**：
1. 搭建简化版网站（Next.js landing + auth + 单个 report 功能）
2. 实现 "输入 ticker → 生成报告" 的主流程
3. 接入免费数据源（SEC EDGAR + Yahoo Finance + NewsAPI 免费版）
4. 手动 curate 50 条商业案例
5. Pricing: freemium（3 份报告免费，$29/报告 或 $99/月 unlimited）
6. 支付：Stripe / Lemon Squeezy
7. 反馈收集：每份报告底部 1-5 星评分 + 1 行文字反馈

**投入**：
- 时间：150-200 小时（1-1.5 个月全职或 3 个月业余）
- 现金：$500-1,000（domain + hosting + API）

**Go / No-Go**：
- MVP 上线后 4 周内付费 ≥ 10 → 继续 Phase 2
- < 10 → 诊断：是产品问题还是分销问题？
  - 产品问题 → 迭代报告质量
  - 分销问题 → 回到内容 marketing

### Phase 2：功能补完（Week 7-14）

**目标**：留存与重复购买

**任务**：
1. 上线功能 2（Thesis Red Team）
2. 上线功能 3（Watchlist + 周度 digest 邮件）
3. 增加 150 条商业案例（扩到 200 条）
4. 增加 10 个行业模板
5. 切换到付费 API（FMP + NewsAPI pro）
6. 引入用户反馈循环：用户标记报告"有用 / 无用"，改进 rerank 权重
7. 建立"**案例画廊**"页面：公开展示 20 个最有代表性的结构化分析

**Pricing 调整**：
- Individual: $99/月 unlimited（10 份/月封顶）
- Pro: $199/月 unlimited + Red Team + Watchlist
- Team: $499/月 5 seats

**投入**：
- 时间：300-400 小时
- 现金：$2,000-5,000（API 升级 + 外包 MBA curate 案例）

**衡量**：
- MRR 达到 $5k
- 流失率 < 15%/月
- 30% 用户使用 watchlist 功能

### Phase 3：增长（Week 15-28）

**目标**：找到可规模化的获客渠道

**3 个同时进行的实验**：

**实验 A：Content Marketing**
- 每周 1 篇深度公司分析发 Substack
- 每篇结尾带 CTA："用工具生成你自己公司的版本"
- 目标：每月 +200 waitlist

**实验 B：KOL 合作**
- 找 10 个 finance Twitter 影响者，免费送 1 年使用权换推荐
- 目标：2-3 个 KOL 带来 50+ 付费用户

**实验 C：垂直社区渗透**
- Reddit r/SecurityAnalysis、ValueInvesting 的 AMA
- 雪球、ETF 之家、集思录的长文
- 目标：每月 30+ 付费用户

**Phase 3 末期目标**：
- MRR $15-20k
- 400-600 付费用户
- 确定 1 个 scale 得动的渠道

### Phase 4：规模化决策（Month 7-12）

**分叉点**：根据 Phase 3 结果决定

**路径 A：SaaS 持续做大**（如果 MRR 达到 $20k+）
- 招 1 位兼职全栈 + 1 位 content creator
- 投入 SEO / paid ads
- 12 个月目标 $100k MRR

**路径 B：Lifestyle Business**（如果 MRR $5-15k）
- 不招人，自己维持
- 稳定 300-500 付费用户 = 可持续 side income
- 每月投入 10 小时维护 + 10 小时 content

**路径 C：Product Pivot**（如果 MRR < $5k）
- 产品做对了但分销没通 → 做 licensing 给某个现有 platform
- 或者把 KB 和 structural analysis 卖给 2-3 家对冲基金做 custom

**路径 D：Kill**（如果 Phase 3 都无起色）
- 把工具作为 open source demo
- 回到论文 / 学术路径

---

## 八. 资源估算

### 8.1 时间投入

| Phase | 持续时间 | 每周投入 | 总工时 |
|---|---|---|---|
| Phase 0 验证 | 2 周 | 20h | 40h |
| Phase 1 MVP | 4 周 | 40h | 160h |
| Phase 2 功能补完 | 8 周 | 30h | 240h |
| Phase 3 增长 | 14 周 | 20h | 280h |
| **合计（前 28 周）** | ~7 个月 | — | **~720h** |

**换算**：相当于 **4-5 个月全职** 或 **10 个月每周 2-3 天**。

### 8.2 现金投入

| 项目 | Phase 0-1 | Phase 2 | Phase 3 | 合计 |
|---|---|---|---|---|
| Domain | $20 | 0 | 0 | $20 |
| Hosting | $100 | $200 | $400 | $700 |
| DB / Redis | 0 | $50 | $150 | $200 |
| Data APIs | $0 | $300 | $600 | $900 |
| LLM | $100 | $500 | $1,500 | $2,100 |
| 案例 curate（外包） | 0 | $2,000 | $1,000 | $3,000 |
| Email / analytics | 0 | $100 | $200 | $300 |
| 设计（一次性 logo + brand） | $200 | 0 | 0 | $200 |
| 法务（terms + privacy） | 0 | $500 | 0 | $500 |
| Reserve（15% buffer） | $60 | $600 | $600 | $1,260 |
| **合计** | **$480** | **$4,250** | **$4,450** | **$9,180** |

**总现金投入**：**~$9,200** 在 28 周内（主要是 Phase 2/3 的案例 curate 外包 + API 费用）

**预期回报**：
- 6 个月 MRR $7.5k × 12 = $90k ARR
- 12 个月 MRR $30k × 12 = $360k ARR（如果 Phase 3 顺利）

**投资回报**：~10× - 40×（如果成功）；**0×**（如果失败）

### 8.3 人力 gap

你自己可以做：
- ✅ 产品设计
- ✅ 后端（复用 V3）
- ✅ 前端（如果时间够）
- ✅ Content marketing（如果有写作能力）

需要外包或补足：
- ⚠️ **Logo / Brand design**（$200 on Fiverr）
- ⚠️ **案例 curate**（MBA 学生 $5-10/条）
- ⚠️ **精品前端 UI**（如果觉得自己设计不好看，$500-2000 请 freelance）
- ⚠️ **法务文件**（$200-500 模板 + 律师 review）

---

## 九. 风险清单

### 9.1 严重风险（P0）

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| **无分销渠道，Phase 0 静音** | 高 (60%) | 致命 | 先做内容 3 个月建观众再上产品 |
| **报告质量不够"有 insight"** | 中 (40%) | 严重 | Phase 0 手动生成的 10 份必须过稿率 > 80% 才进 Phase 1 |
| **LLM 成本失控** | 中 (30%) | 严重 | 引入 Kimi/Haiku fallback，report 缓存复用，设月度 budget 自动断闸 |
| **用户找不到"实用 ROI"** | 中 (40%) | 严重 | 每份报告附具体可操作建议，避免纯哲学类比 |

### 9.2 中度风险（P1）

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 数据源 API 涨价或停服 | 中 | 中 | 多源备份（SEC + Yahoo + FMP） |
| 竞品快速跟进 | 低 (20%) | 中 | 案例库是 moat，技术易复制但内容难 |
| 合规问题（被当做投顾） | 低 (15%) | 严重 | 明确 disclaimer: "not investment advice" |
| 个人 burnout | 中 (40%) | 严重 | 严格每周上限 30h，不加班 |
| 中美两市场分裂 | 中 | 小 | MVP 只做美股 + A 股头部，暂时不做港股/欧股 |

### 9.3 尾部风险（P2）

- LLM 输出偏见导致的社会舆论（解决：每份报告人工抽查前 100 份）
- 用户恶意使用（pump and dump）（解决：watermark + 法律 disclaimer）
- Domain 被抢注（解决：Phase 0 结束前立刻买下）

---

## 十. 最关键的 5 个决策点

这 5 个决策每个都可能决定成败。

### 决策 1：Phase 0 要不要先做？

**选项 A**：跳过 Phase 0，直接 Phase 1 MVP
- 优点：快
- 缺点：没有市场验证就投入 150 小时，风险高

**选项 B**：严格 Phase 0 2 周
- 优点：低成本验证
- 缺点：慢 2 周

**推荐**：**B**。这 2 周的成本极低，但如果 Phase 0 失败，省下 150 小时 + $5k。

### 决策 2：用 ticker 还是公司描述作为主输入？

**选项 A**：只支持 ticker
- 优点：结构化，数据好拉
- 缺点：排除私有公司、新兴项目

**选项 B**：两种都支持
- 优点：覆盖更广
- 缺点：自然语言输入的抽取更难

**推荐**：**Phase 1 只支持 ticker**，Phase 2 加自然语言。

### 决策 3：是否做自动化报告生成？

**选项 A**：全自动化（快，但质量可能差）
**选项 B**：AI 生成 + 人工 review（慢，但质量保）

**推荐**：**Phase 1 前 100 份用 B**，手动 review 每份报告。Phase 2 后逐步 A。

### 决策 4：定价锚点

**选项 A**：$19/月（retail 价格）
- 优点：低摩擦
- 缺点：ARPU 低，100 用户只有 $1.9k MRR

**选项 B**：$99/月（professional 价格）
- 优点：ARPU 高
- 缺点：转化门槛高

**选项 C**：$29/份（pay-per-report）
- 优点：更低心理门槛
- 缺点：无 recurring

**推荐**：**freemium + $99/月** 主打专业用户，同时保留 $29/份的 single report 入口捕获犹豫用户。

### 决策 5：是否学术论文化？

**选项 A**：纯商业产品，不发论文
**选项 B**：同时发 1 篇 position paper（比如 arXiv）作为信任背书

**推荐**：**B**。一篇 arXiv 论文能在冷启动时作为 credibility 素材——对专业买方用户特别有效。论文内容可以从现有 V3 工作直接改写。

---

## 十一. 从今天开始的第一步

### 今天

1. Review 这份 plan，决定 Go / No-Go
2. 如果 Go：买下 domain（`structuralintel.io` / `structint.com` / `isomorph.finance`）
3. 开一个 notion page 记录 Phase 0 进度

### 本周

1. 选 3 家公司（NFLX / NVDA / PDD）生成第一批测试报告
2. 发到 Substack 建立基础 newsletter
3. 同一内容翻译到雪球 / 小红书 / Twitter

### 本月

1. 完成 10 份公司报告
2. 观察 3 周的 waitlist 增长
3. 根据数据决定进入 Phase 1 还是调整策略

---

## 附录 A：相关链接

- 现有项目：`~/Projects/structural-isomorphism/`
- V3 核心代码：`v3/matcher.py` + `v3/extract_structtuple.py`
- V3 数据：`v3/results/kb-expanded-struct.jsonl`（4443 现象）
- Beta 站：`beta.structural.bytedance.city`（参考 UI）
- GitHub：`github.com/dada8899/structural-isomorphism`

## 附录 B：版本历史

- v0.1 (2026-04-15)：初版草案
