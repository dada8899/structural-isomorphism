# W5-C PM Review — D1 Phase Detector + structural-isomorphism

> Reviewer: senior PM (B2B fintech data products, 10+ yrs — Bloomberg Terminal / Sentieo / FactSet background)
> Date: 2026-05-13
> Scope: `phase.bytedance.city` (D1 Phase Detector) + `beta.structural.bytedance.city` (main academic site)
> Method: code walkthrough (`phase/code/*.html`, `site/index.html`, `phase/data/*.jsonl`, `phase/samples/*.md`, `phase/content/*`), product surface inspection, competitive benchmark from memory.

---

## 1. TL;DR — 该不该做这个产品？

**Verdict: 现在不是一个 product，是一个非常聪明的 demo。一年内能不能从 demo 走到 product，取决于接下来 6 个月做什么。**

把它放到 VC pitch 里，我会回答：**这一轮不投，但保持 follow，6 个月后再看 retention 数字**。原因：

1. **Insight 是真的**。"用 dynamics 而不是 P/E 筛公司" 是一个有 narrative 杀伤力的 wedge——AlphaSense / Sentieo 这一代 SaaS 没人做这件事，Sornette 的 LPPLS 学术派也没做成 product。这是一个 defensible category-defining angle。
2. **Execution 还差三层皮**。当前 100 公司样本、LLM 自标签、零回测、零真实用户，是"博士生 weekend project ➜ 产品" 的中间态。所有声称的预测力都还在 LLM 信任前置阶段。
3. **作者 self-aware（about.html 第三节"已经验证过的事"列了 4 个 ✗ 失败项）**——这是好信号，但 VC 不会因为你诚实就投。

**作为 founder，next 6 个月只做三件事，其他全砍**：

1. **把样本从 100 ➜ 500 公司**（覆盖 S&P 500 + HSI Tech + 主要 ADR），让"用户搜的公司在不在 list" 概率从 < 20% 升到 > 75%。这是用户留存的命门。
2. **每周 1 份高质量 memo 推送到 waitlist 用户**，把 timeline + analogy 当成 newsletter 引擎做内容飞轮。零回测的情况下，**用内容 + 角度差异化建立信任**，而不是用 alpha 数据建立信任。
3. **找 5-10 个真实买方分析师做 design partner**，把 product roadmap 锚在他们的 weekly workflow 上——不是闭门造车再扩张。

**不该做的事**：扩 24 类 dynamics 到 50 类、做组合画像、做 PDF 导出、做 mobile app、做付费墙。这些是 "product complete" 后的事，现在做都是 distraction。

---

## 2. D1 Phase Detector 产品 review

### 2.1 Value proposition

**Tagline 评分**：
- 中文："别用市盈率筛股，用数学结构筛股" — **8/10**。punchy、对立鲜明、零行业黑话、能从 HN/Twitter 标题路过 5 秒抓住人。在中文 quant Twitter 圈这条 tagline 自带传播力。
- 英文："The first screener that filters companies by their mathematical dynamics, not financial ratios." — **6/10**。"the first" 是 red flag（不可证伪），"mathematical dynamics" 对英语圈普通投资者还是太学术。改成 "Screen stocks by their **lifecycle phase**, not their P/E" 更轻、更直觉。

**Target user 模糊**——产品当前 surfaces（screener + timeline + analogy + memo + redteam）跨度太大：
- Hedge fund quant 想要：批量信号 / 历史回测 / API 落库 — **现在都没有**
- VC analyst 想要：early-stage 公司分类 + 类比历史 — **现在 sample 全是上市公司，VC 用不上**
- Retail trader 想要：buy/sell signal — **明确拒绝（disclaimer 写了"不构成投资建议"）**
- Academic 物理学家：跨域类比可发表 — **主站才是他的目标**
- Tech curious：故事、视角、跟朋友显摆 — **目前 sample/memo 是最好的入口，但主页强调 screener 把这类人推走了**

**我的判断**：产品现在的真实 ICP 是 **"high-conviction long-term retail investor (5-10k USD ticket, Twitter active)" + "boutique 独立分析师 / 财经 KOL"**。这个人群对"角度"付费、对"alpha"不付费，他们的 pain 是"在 substack 上写出有差异化的公司分析"。Phase Detector 应该把自己定位成 **"独立分析师的研究副驾驶"**，而不是 "Bloomberg 替代品"。

把这个 ICP 想清楚之后，screener 的 UI 就要重新设计——见 § 2.2。

### 2.2 User journey — 大量 friction

**入口 friction**：
- 主页 hero 同时塞了 4 个 CTA（"打开结构筛选器" / "📜 相位演变" / "🕰️ 类比引擎" / 还有顶部 nav 6 个链接）。**对新用户认知负荷过高**。Bloomberg power user 习惯 deep nav，但他们花了 6 个月学。新用户应该被强制走 happy path。
- 推荐改造：hero 改成单 CTA "看 6 个正在结构相变的公司 →" 直接 jump 到一个 curated grid，绕开 screener UI，先让用户**消费内容 30 秒**而不是**操作界面**。Bloomberg 老 user 都知道，刚进 Terminal 5 秒看到 alerts 是最容易上瘾的路径。
- 现状的 "STRUCTURAL SIGNALS · 今日精选 · 6 家公司" section 已经在做这件事，但它在 fold 下方，应该 swap 到 fold 上方。

**Screener 体验问题（`phase/code/screener.html:300-400`）**：
- 4 个 dropdown filter（dynamics_family / phase / feedback_topology / boundary_behavior）全是科学术语。即使加了中文 label（"鞍结分岔" / "Hopf 分岔"），对非 quant 用户还是一道墙。
- **真正的 Bloomberg power user 习惯不是 dropdown，是 query syntax**：`phase=approaching_critical AND dynamics=Bistable_switch AND mcap>50B`。但当前用户是 retail，不需要 query syntax。
- 推荐：把 4 个 filter 折叠成 3 个 **直觉化 preset chip**——"📉 即将进入危机的公司" / "🚀 仍在加速的飞轮" / "🔄 双稳态翻转中"。preset 后面隐藏的实际是 dynamics_family + phase 的组合，但用户不知道也不需要知道。Notion / Linear 的 view preset 是同款思路。
- "Apply" button 还是 reactive filter？现在是 reactive（dropdown 一改 results 就重算），**对的**。Power user 会觉得反应灵敏。但 6+ filter 后 reactive 会因为数据 200 公司太少而 results 经常归零，应该加 "results: 0 公司 — 试试放宽 ___" 的空态引导。

**Company detail page 不 actionable**：
- 进 company.html 看到 dynamics_family / phase / feedback 这些字段，普通用户脑子里没有 mental model，看完不知道 **next action 是什么**。
- "深度分析" 是 LLM 在线生成（看 `company.html:300-340` 的 streaming progress bar），**等 30 秒以上是 dealbreaker**。Bloomberg 用户对 latency 容忍 < 200ms，retail 用户容忍 < 3s。把"深度分析" pre-bake 成静态 markdown，进页面直接显示，是必做。
- 缺 "compare with similar companies" CTA。一个 NFLX 看完用户最想做的事就是 "show me NVDA's dynamics next to NFLX 's"——这是 Bloomberg 的灵魂 feature `RV` (relative value)。

**关键 metric 漏点**——code 里我没看到 events tracking：
- 没有 `screener_filter_applied` event（用户用了哪个 filter combo？）
- 没有 `company_detail_view_time` event（用户在 NFLX page 停了多久？）
- 没有 `deep_analysis_completion_rate`（30s 等 LLM 多少人等到了？）
- 看到 `docs/analytics/` 目录在，但 W4-B Plausible 是 nginx log 级别，**缺业务事件 layer**。这是 product-led growth 必需层。

### 2.3 Trust & explainability

**Trust 问题最严重的产品块。** LLM 标签 + LLM 类比 + LLM 深度分析 + 零回测 = 用户每读一份报告心里都在打折。

具体痛点：
- `universality_class` / `dynamics_family` / `phase_state` 这些字段在 company.html 顶部突出展示，**普通用户看不懂**。需要 inline 教学 — hover 一个学术词，弹一个 100 字 tooltip。当前 about.html 第二节"核心原理（大白话）"质量很好，应该把那个段落片段化注入到每一个学术词的 first-touch。
- "Caveats" 章节在 about.html 第三节 "已经验证过的事"，**好东西但藏太深**。用户进公司详情页时，应该在头部就有一个 "⚠️ AI 生成 · 请独立验证" 的 ribbon，链到这个 caveats 段。Anthropic 自己产品都这么做。
- **Confidence bar 没看到校准说明**。从 `critical_signals.json` 字段 `c.confidence` 在 hero 区显示 "置信度 67%"，但用户问 "67% 是怎么算的"——是 LLM 自评？历史回测？模型集成投票？目前没回答。Bloomberg Terminal 上每一个估值数字都会标 source + methodology link，phase 这边缺这层。
- **TL;DR 写得够 layperson 吗**：sample `01-nflx.md` 第一段 "Netflix 不是成长股了，它是一家被市场误解为 SaaS 的老牌制片厂" 写得**极好**——这就是 publication-grade journalism quality。但 screener / company 主页面没有这种叙述性 TL;DR，全是结构化字段。应该把 sample md 里的核心观点抽出来做 `<div class="tldr-banner">` 顶部展示。

### 2.4 100 公司样本 — too small to be useful

**这是 product-killer #1。**

`phase/data/companies_struct.jsonl` + `companies_opus_N.jsonl` 当前覆盖 100-204 家（数字在多个 surface 不一致——hero 写 204、screener 默认 fetch /api/companies 数量未定、samples manifest 显示 10 份深度报告）。**先 fix 数字一致性**（QA blocker）。

**用户搜的公司很可能不在 list**：
- S&P 500 = 500 家
- HSI Tech = 30 家
- Nasdaq 100 = 100 家
- 主流 ADR = 50 家
- 用户 likely query universe ≈ 600-800 家
- 当前覆盖 = 200 家 → **hit rate ~25-33%**
- 用户连续 3 次搜的公司都找不到 = 永久流失

**ticker 优先级建议（30 天扩到 500 家）**：
1. **Tier 1 (必须有)**: S&P 100 Mega-cap + 中概股 ADR Top 20 + HSI Tech Top 20 → 140 家
2. **Tier 2 (差异化)**: 历史"曾经经历过相变"的 50 家（PTON / GME / BBBY / SVB / FRC / WeWork 这种），用 timeline 形态做内容差异化武器
3. **Tier 3 (覆盖)**: Russell 2000 中市值 100 家（避免只覆盖大盘）

LLM 标签成本：Claude Sonnet 4.5 ~$0.02/公司 × 500 ≈ $10。**这是 30 天可完成的成本最低 milestone**。

### 2.5 Pricing / monetization

**当前 monetization = waitlist 邮件收集，零 revenue stream。** about.html 第四节列了 6 个"未来可能场景"全是 feature，**没有一个标 price**。

我作为 PM 给的 pricing 三层（**这是 best-guess proposal，需要 5-10 个真实买方做 willingness-to-pay 访谈验证**）：

| Tier | 月费 | 内容 | 目标用户 |
|---|---|---|---|
| **Free** | $0 | 100 家公司 screener + 每月 2 份 sample memo + 类比引擎 query 5 次/天 | retail / curious tech |
| **Pro** | $29 / mo | 500+ 家全市场 + 每周 newsletter + analogy 无限 + 深度分析 PDF 导出 + 历史 timeline 全量 | 独立分析师 / 财经 KOL / high-net-worth retail |
| **Team** | $99 / mo / seat (≥3 seats) | Pro + 组合上传/分析 + 公司对比模式 + Excel 导出 + 邮件支持 | family office / boutique fund / 投研团队 |
| **B2B Index API** | $500-2000 / mo flat (custom) | 全市场 structural index + webhook on phase transition + 历史回填 | quant fund / fintech partner |

**ARR 预测 range（12 个月，conservative ➜ optimistic）**：
- Conservative：waitlist 1000 ➜ 2% paid conversion = 20 Pro × $29 × 12 = **$7K ARR**
- Base：waitlist 5000 ➜ 3% conversion = 150 Pro × $29 × 12 = **$52K ARR** + 1-2 B2B API = +$20K = **~$70K ARR**
- Optimistic：waitlist 20000 (HN 头条爆) ➜ 4% conversion = 800 Pro × $29 × 12 = **$278K** + 5 B2B API = **~$350K ARR**

**与 Sentieo / Koyfin 对比**：
- Sentieo Standard: $475 / mo / seat (个人) — 服务 hedge fund analyst，feature broader (transcripts / docs / quant)
- Koyfin Plus: $50 / mo — 服务 retail high-conviction investor，feature 更聚焦 charting + financial data + global coverage
- **Phase Detector $29/mo 是合理 anchor**——它定位在 Koyfin 之下，但提供一个 Koyfin **完全没有的 angle**。不是替代 Koyfin，是 complement。

**B2B API 是隐藏金矿**：如果"company X 进入 approaching_critical" 能 webhook 推送给 Sornette 学派的 hedge fund，他们愿意付 $2000/mo flat 来订阅 index。但这需要先证明 false-positive rate < 30%，**需要回测，需要扩样本**。

---

## 3. structural.bytedance.city 主站 review

### 3.1 Audience confusion

**主站最大问题：身份分裂。**

打开 site/index.html 看到的是一份学术研究的 Notion-like 文档库（v1 模型 / v2 知识库 / 思考链路 / 路线图…）。但顶部 nav `Live Beta` + Dataset DOI + GitHub 又像是开源数据集页。Phase Detector 又是商业子产品。**三个身份打架**：
1. 学术研究 lab（thinking-chain / v1-evaluation / paper drafts）
2. 数据集 + 模型发布站（HuggingFace + Zenodo DOI）
3. 商业产品入口（Phase Detector）

不同访客对应不同诉求，但主站没有 segmentation——所有访客看到同一个 sidebar 树。

**建议**：首页加一个 "Who are you?" segmentation gate，3 个卡片：
- 🔬 **I'm a researcher** → 学术 papers + dataset + methods 路径
- 📈 **I'm an investor** → 直接 jump Phase Detector
- 🤓 **I'm tech-curious** → 一个 5 分钟入门 essay + sample memo

Sornette's Financial Crisis Observatory 自己做过类似分流（researcher vs practitioner），效果很好。

### 3.2 Hero message

**当前 hero**: "13 verified universality systems across SOC / PA / Hysteresis / Scheffer + 1 unified preprint"

这是给学术圈写的。对外行：
- **SOC** = self-organized criticality？ 大多数人猜不出
- **PA** = phase-ahead？ partial alignment？ 不知道
- **Scheffer** = 名字？ 算法？ 是 ecologist Marten Scheffer 的方法吗？
- **unified preprint** = 论文还是产品文档？

**Bounce rate 估测**：non-academic 访客 5 秒内离开率 > 70%。

改造建议：
- Hero H1 改 layperson-friendly: "We discovered that **bank failures, neural avalanches, and earthquakes obey the same equation**. Here's the math—and a tool that finds these patterns in 200+ companies."
- 学术细节放 H2 subhead："Open dataset (Zenodo DOI), 13 verified universality classes, peer-review preprint."

### 3.3 Content strategy

20 篇 paper / thinking notes 现在全在 sidebar tree 平铺。**对没有 prior context 的读者，不知道从哪读起。**

缺失：
- **"Start here" 入门 essay**: 一篇 1500 字的 layperson explainer——"为什么我相信银行挤兑、地震、神经雪崩本质上是同一件事"
- **Learning path**: 三条 progression — Curious 30min / Practitioner 2hrs / Researcher full deep-dive
- **Story-first surfacing**: 当前所有内容都是 process-first（v1 training / v2 knowledge base），改成 outcome-first（"we found 13 systems that obey the same law"），更适合内容传播
- **Citation copy**: 每篇 paper 顶部加 "Cite this" 按钮，BibTeX + APA 一键复制（这是 academic 用户必需 feature）

---

## 4. 4 类 user persona 各自 journey

### Persona A: Hedge fund quant (35yo, $200M AUM mid-cap fund)

**进 phase. 干什么**: 看 "这个 alpha source 是不是真的，能不能 backtest"
- 第一停留点：sample reports（要看 methodology）
- 第二停留点：about.html — 看到 "PELT 不 work" + "没回测" + "0 用户" 立即关闭页面
- **Fail point**: about.html 的诚实自我披露，对 quant 是一个 "no investable yet" 的 signal
- **Fix**: 给 quant 用户单独一条 path — 标注 "B2B API · for institutional use only" 隐藏正面的 academic-honesty 自检，offer 直接的 backtest 数据 + sample CSV
- **Conversion likelihood**: 现状 < 1%。提供 backtest + API 后可到 10%。

### Persona B: VC analyst (28yo, early-stage SaaS focused)

**进 phase. 干什么**: 看新公司能不能套这个框架
- 第一停留点：screener — filter Tier-1 大公司，找不到自己关注的 Series B/C 公司
- 第二停留点：about.html — 看到 "204 家上市公司"，结论 "this is for public equities, not VC"
- **Fail point**: ICP mismatch，VC 不是当前 ICP
- **Fix**: 显式说明 "Currently public equities only. VC private-market expansion on roadmap." 不要假装服务 VC。
- **Conversion likelihood**: < 1%。这个 persona 应该 deprioritize。

### Persona C: Academic 物理学家 (45yo, complex systems researcher)

**进 structural. 看 paper**
- 第一停留点：site index → 思考链路 → v2 expanded screening — 看 dataset + 4 个 preprints
- 第二停留点：Zenodo DOI / GitHub — 验证 reproducibility
- **Friction**: dataset 是 LLM 生成的标签，不是 ground truth → reviewer 会质疑；缺 inter-rater reliability 统计
- **Citation Path**: "Cite this" 按钮缺失；CITATION.cff 已存在但 site UI 没暴露
- **Conversion likelihood**: 引用 → 写 1 篇基于这个 dataset 的 paper 概率 = 5-10% (decent for academic project)
- **Action**: 把 CITATION.cff 在主站每个 paper 页上方暴露 + 加 "Email me if you use this in your research" 邮件订阅。

### Persona D: Tech curious / writer (Hacker News 来的 sysadmin)

**进 phase. 5 分钟内能 walk away with story 吗？**
- 第一停留点：hero → "别用市盈率筛股，用数学结构筛股" → "📜 相位演变" CTA
- 第二停留点：timeline.html — 看 NFLX / NVDA 历史相位变化 → 这是好故事，会发 HN comment
- 第三停留点：about.html — 看到 "PELT 不 work / 0 用户" — **加分而不是减分**，HN crowd 喜欢 candor
- **Walk-away story**: "Some dude in China is classifying stocks by their phase transition. Trippy. Here's the link."
- **Conversion likelihood**: 看完即走 80%，加 waitlist 15%，付 $29 < 1%
- **关键**: 这个 persona 是 **traffic-driver**，不是 revenue-driver。优化 share-ability，不优化 conversion。

---

## 5. 与现有竞品对比

| 竞品 | 它做的好 | Phase Detector 做的差 / 好 |
|---|---|---|
| **Bloomberg Terminal** | 全资产 / 实时 / 投行 standard / 8M data fields | $25k/yr 不会被替代。Phase 是 complement angle，不是 replacement。 |
| **Sentieo / AlphaSense** | NLP 搜 transcript / filings, semantic indexing | Phase 完全不做 transcript。两者 0 overlap，但都讲 "data-driven analyst tool"。 |
| **Koyfin** | 现代 UI / global coverage / $50 个人 / 50 万 user | Phase **直接对标 Koyfin tier**。差距：coverage 1/30，feature 1/20。胜在 angle 独家。 |
| **FactSet** | 投行机构标配 / 数据深度 | 与 Phase 0 overlap |
| **Sornette FCO (Financial Crisis Observatory)** | 学术 reputation / LPPLS 模型 / 真实历史预测记录 | Sornette 是直接精神前辈。Sornette 没 product 化，Phase 有产品化空间。但 Phase **还没 Sornette 那种 backtest credibility**。 |
| **TradingView screeners** | 海量 user / 自定义 indicator marketplace | TradingView 是 chart-first，Phase 是 narrative-first。两者 user overlap 但不直接竞争。 |
| **Tegus / In Practise** | expert call transcripts / qualitative depth | qualitative analyst tool. Phase 是 quantitative-with-narrative wrapper。互补。 |

**Phase 的真正护城河（如果做对）**：
1. **跨学科类比**（Verhulst / SIR / Tilman / Schelling 直接套公司）是其他 fintech tool 全不做的
2. **Timeline of structural phases** 是新表达形式——Bloomberg / Sentieo 都是 cross-section 视角，没人做 longitudinal phase narrative
3. **Open-source dataset** 是学术-产品双轨的独家武器

**最不可被复制的优势**: 创始人本人对 "structural isomorphism" 这个 idea 的 10 年内化深度。这是 wedge——但 wedge 要变成 product 需要 execution。

---

## 6. Roadmap recommendation (12-month)

按 PM 优先级排序，每个标 effort (S=1wk / M=1mo / L=3mo) + impact (S/M/L)。

### P0 (Next 30 days)

| Item | Effort | Impact |
|---|---|---|
| 公司样本扩到 500 家（覆盖 S&P100+HSI Tech+中概+ADR） | M | L |
| Sample count consistency fix (100 vs 204 vs 83 三个数字打架) | S | M |
| Hero swap：把 "今日精选 6 公司" 顶到首屏 | S | M |
| Company detail "深度分析" 改 pre-baked static（去掉 30s LLM 等待） | S | L |
| Events tracking layer：screener_filter / company_view / waitlist_signup 写 Plausible custom events | S | M |
| "Start here" 入门 essay (1500 字 layperson) for 主站 | S | M |

### P1 (Day 31-90)

| Item | Effort | Impact |
|---|---|---|
| Filter UI 重构：4 个 dropdown ➜ 3 个 preset chip + advanced toggle | M | L |
| 每周 newsletter cadence + 3 篇内置 backlog memo（每周 1 篇 ship） | M | L |
| Company compare mode（2-3 家并排看 dynamics + analogy） | M | M |
| 找 5-10 个 design partner 做 weekly 用户访谈 | M | L |
| Confidence bar 校准 methodology page + UI tooltip | S | M |
| 主站 "Who are you?" segmentation gate + 3 条 learning path | M | M |

### P2 (Day 91-180)

| Item | Effort | Impact |
|---|---|---|
| Pricing 上线（Free + Pro $29 + Team $99） | M | L |
| Stripe 接入 + 付费墙（Free 限制 100 公司 / Pro 全量） | S | L |
| Portfolio upload (持仓粘贴 → structural 画像) | M | M |
| B2B API beta：phase_transition webhook + index export CSV | L | L (high revenue) |
| 历史回测一份：用 Phase 标签选股 vs S&P 500，至少 3 年 historical | L | L (trust unlock) |
| HN launch + Substack relaunch + Twitter thread campaign | S | L |

### P3 (Day 181-365)

| Item | Effort | Impact |
|---|---|---|
| 扩到 1000+ 公司 + 全球市场覆盖 | L | M |
| VC private market beta（覆盖 Series B+ unicorns） | L | M |
| Mobile app (read-only memo + alerts) | L | S |
| White-label B2B partnership（嵌入 wealth advisor tools） | L | L |

**不在 roadmap 内（明确砍）**：
- 24 类 dynamics 扩到 50 类（marginal value）
- PDF 导出（除非 Pro tier 需要）
- 多语言 i18n（除非英文版 traction 上来）
- VC private 数据集 before 12 个月（私募数据成本太高 + ICP 还没验证）
- Mobile native app（web responsive 优先）

---

## 7. Pricing model proposal

**Free tier (acquisition layer)**：
- 100 家公司 screener
- 类比引擎 5 query / 天
- 月度 1 篇 sample memo email
- About / methodology 全部
- 主站全部学术内容
- **目标**: 收 waitlist + 转 Pro 的 funnel top

**Pro $29 / month (engagement layer)**：
- 500+ 公司全量 screener
- 类比引擎 unlimited
- 每周 1-2 篇 deep memo（最新 + 历史档案）
- 历史 timeline 全量（50+ 公司 longitudinal）
- 深度分析 PDF 导出
- Email alert on phase transition (自选 watchlist)
- **目标 customer**: 独立分析师 / 财经 KOL / high-conviction retail
- **WTP 锚点**: Koyfin $50 / Sentieo $475，Phase $29 是合理 mid-anchor

**Team $99 / seat / month (≥3 seats)**：
- Pro everything +
- 组合上传分析 (portfolio dynamics distribution)
- 公司对比模式
- Excel + JSON 导出
- 邮件支持 < 24h
- **目标 customer**: family office / boutique fund / 投研团队

**B2B API $500-2000 / month flat (custom)**：
- 全市场 structural data dump (JSON / Parquet)
- Webhook on phase transition events
- 历史回填 5 年
- 自定义 ticker 优先级
- SLA: 99% uptime
- **目标 customer**: quant fund / fintech 数据 partner / academic group

**ARR 预测 (12 个月)**：

| Scenario | Waitlist | Conv rate | Pro paid | Team | API | ARR |
|---|---|---|---|---|---|---|
| Conservative | 1,000 | 2% | 20 | 0 | 0 | **$7K** |
| Base | 5,000 | 3% | 150 | 5 teams (~15 seats) | 1 | **~$80K** |
| Optimistic | 20,000 | 4% | 800 | 30 teams (~90 seats) | 5 | **~$370K** |

**关键 unlock**: HN front page + Substack 一次 viral 内容 = waitlist 从 1K ➜ 10K，这是 base→optimistic 的 swing factor。

---

## 8. Distribution / GTM

### HN launch readiness — **NO**

当前不 ready 上 HN：
- Sample count 数字不一致（HN crowd 30 秒就发现）
- "0 真实用户 / PELT 不 work" 等诚实自检会被 HN top comment 围攻
- 缺一个 "show, don't tell" 的 sticky example（Phase Detector 在 2024 SVB 危机前几周就标记到了 SVB approaching_critical?——这种 hindsight 故事是 HN 黄金）

**HN 上线前必做的 3 件事**：
1. 找出一个**真实历史 case**：Phase Detector 的 LLM 标签 + 真实历史时间能"预言"过某次崩塌？ PTON 2021 / SVB 2023 / WeWork 2019。哪怕只是 retrospective alignment，做成 case study。
2. 把 sample 数从 10 扩到 30 公司（HN reader 第一件事是 ctrl-F 找他们关心的 ticker）
3. Title 不要写 "I built X"，要写 "**Why bank failures and earthquakes obey the same equation (and what it means for stock screening)**" — story-first not tool-first

### Other channels

- **Reddit r/investing / r/SecurityAnalysis**: ICP 完美匹配。先发 substack memo 内容（不是产品），再 link to 产品
- **Reddit r/quant**: 不投。Quant crowd 会 demand backtest，没就嘲笑
- **Twitter (X) finfluencer**: 找 3-5 个 mid-tier finance influencer（5-50K followers, Phase Detector 类型 niche），送他们一份 free Pro + ghostwrite 一篇 thread for them. $0-500 cost.
- **学界 outreach**: arXiv 上 follow Sornette / Scheffer / Bak 引用图谱，给最近 6 个月 cite 这些 paper 的 corresponding author 发个性化 email。**dataset 是 academic outreach 的 anchor，不是产品**
- **Substack** + **小红书 + 雪球**: 已有内容（`phase/content/*`），cadence 拉到每周
- **YouTube**: 不在前 6 个月 priority。视频 production 成本太高

### Key KPI / North Star Metric

**Star metric**: **WAU (Weekly Active Users) who view ≥ 2 company pages**
- 这是 "看一篇是好奇，看两篇是真的在用" 的临界
- Phase 的 user value 在 "比较 / 类比"，单 page view 不构成 value 完成

**Supporting metrics**:
- Waitlist signup rate (HN/Reddit 流量 → email 转化)
- Sample memo email open rate (≥ 40% 是好 newsletter)
- Pro upgrade rate (waitlist → paid, target 2-4%)
- Pro 90-day retention (target ≥ 70%)
- B2B API contract count (lagging, target 3-5 by month 9)

---

## 9. Top 3 product 风险

### Risk 1: "Insight 看起来聪明，但 alpha 不存在"

**这是 founder-level existential risk。** 当前 0 回测、PELT 不 work、PE-based 筛选未被证伪。如果 6 个月内某个真实用户跑了 N=100 公司 backtest 发现 "用 Phase Detector 分类选股 vs 随机选股 alpha = 0"，**整个 narrative 崩塌**。

**Mitigation**:
- **不要 promise alpha**。约束 positioning 在 "analytical angle / story discovery" 而不是 "outperform market"
- 真正 differentiated 的 value 是**叙事生产力**，不是预测——独立分析师订 Pro 是因为他能用这个写出 sub-stack 文章，不是因为他靠这个赚钱
- 内部做一份非 promoted 回测，结果不公开但用来内部 sanity check。如果 alpha ≈ 0 + IR < 0.3，accept 这是 "narrative tool" 不是 "alpha tool"

### Risk 2: "LLM hallucination / 数据可信度" 的长期破窗效应

LLM 标签 + LLM 类比 + LLM 深度分析全栈使用。一旦用户发现一处事实硬伤（比如 "Tesla 像 1998 年的 Cisco"——但 Cisco 1998 年的市值/PE 数字写错），就会**普遍质疑所有内容**。Bloomberg 数据 PM 圈有句话叫 "trust is binary"。

**Mitigation**:
- 关键数字硬编码（来自 Yahoo Finance API / SEC EDGAR）+ 标 source
- LLM 只生成 narrative，不生成数字
- 每个深度分析 publish 前过一遍 fact-check pass（Sonnet 4.5 self-critic）
- 给每页加 "Report inaccuracy" 按钮，建立 user-as-QA 飞轮

### Risk 3: ICP 长期模糊 → 增长卡死

当前产品同时讨好 4 个 persona（quant / VC / academic / curious tech），**每个都不到位**。增长不来自"对每个用户都还行"，而来自"对一类用户极致 obsessed"。

**Mitigation**:
- **30 天内 lock ICP** = "high-conviction long-term retail investor + boutique 独立分析师"
- 把 quant API / VC private market / 学术 paper outreach 全部移到 P2+ roadmap
- 主站和 phase 子站做**显式 audience gating**，不要混屏

---

## 10. Top 5 Quick Wins (next 7 days actionable)

1. **修 sample count 不一致** (4 hours) — hero 写 204 / about 写 204 / screener load 83 / signal show 6——选一个 single source of truth 改 4 处。这是 polish 但 HN crowd 第一眼就抓
2. **Pre-bake "深度分析" 静态文件** (1 day) — 当前 30s LLM 等待是体验杀手。把 sample 10 公司的深度分析全 pre-render 成 markdown，company.html 直接显示
3. **Hero CTA 改单一 + 顶 6 公司 signal** (4 hours) — 把现有的 "STRUCTURAL SIGNALS 6 公司" 区块从 fold 下方调到 hero 直接下面。减 3 个次要 CTA
4. **加 events tracking** (1 day) — Plausible custom events: screener_filter_applied / company_view / deep_analysis_complete / waitlist_signup。没有这个，下一步任何 A/B 都不可做
5. **写一篇 "Start here" 入门 essay** (1-2 days) — 1500 字 layperson, 标题 "为什么银行挤兑、地震、神经雪崩本质上是同一件事". 放主站首屏 + Substack 同步 publish 一份。这是 HN-able 内容的 seed

---

## 11. Final Scores

| 维度 | 分数 | 评注 |
|---|---|---|
| Value prop clarity | 7/10 | 中文 tagline 强，英文偏学术 |
| UX (UI design) | 6.5/10 | 视觉精致克制，但 friction 多 |
| UX (information architecture) | 5/10 | 4 个学术 dropdown 是新用户杀手 |
| Trust (data credibility) | 4/10 | LLM 全栈无 backtest，confidence 校准缺 |
| Differentiation | 9/10 | 跨学科类比 + structural phase 是真护城河 |
| Monetization potential | 6/10 | $80K-300K ARR 范围可达，但 pricing UI 0 |
| Content quality (samples) | 8.5/10 | NFLX sample 是 publication-grade |
| Founder candor (about.html) | 9/10 | HN-friendly 自检诚实 |
| GTM readiness | 4/10 | HN/Reddit 任一渠道现在都不该 launch |
| **Overall product readiness** | **6.0/10** | 聪明 demo ➜ product 之间还差 90 天 PM-discipline 收敛 |

### Recommended next 30-day priority

**"Sample 扩 5x + 内容飞轮 + 单一 ICP" 三件套**：

1. 公司扩到 500 + sample 数字 consistency fix
2. 每周 newsletter 第一期上线（sample memo 改写为 broader appeal Substack 文章）
3. Lock ICP 在 "high-conviction retail + 独立分析师"，主站/phase audience gating

**不做**：付费墙 / API / 多语言 / mobile / 50 类 dynamics 扩展。

---

## 12. Closing PM thought

这个项目让我想起 2014 年的 Sentieo 早期阶段——一个聪明 founder + 一个非显然的 wedge + 真实的 data 资产，但还没找到 monetization 锁。Sentieo 走通靠两件事：（1）找到 mid-market hedge fund 的明确 pain（"transcript search"）；（2）建立了 inter-rater 可信度（不是 LLM-only，有 human review layer）。

Phase Detector 的 path-to-product 可能不是 Sentieo（机构 SaaS）那条，更像 **Substack-meets-Koyfin**——以独立分析师为 ICP，以"叙事生产力"为 value prop，以"角度独家性"为差异化。

如果 founder 在 next 6 个月**接受这是一个 narrative product 而不是 alpha product**，monetization 路径其实清晰：内容飞轮 → newsletter → Pro tier → 长尾 B2B。

如果坚持要做 alpha product，需要 quant 联合创始人 + $2-5M seed 钱 + 18 个月做出 statistically significant 回测。这是不同的 game。

**我的建议是前者**。后者烧钱概率太高，前者用现在的 founder skill set 是 perfect fit。

---

**End of review. — W5-C senior PM (B2B fintech data products), 2026-05-13**
