# 清算级联 × 网络清算机制：深度研究档案

日期：2026-07-12
Track：B
状态：Stage 0 文献与构念筛选完成；Stage 1 实证验证尚未开始

## 1. 执行结论

### 总判定

- **宽命题 NO-GO**：“金融清算、支付、CCP 和银行间网络共享同一种清算级联机制”不成立。它混合了至少四种不同的状态变量、约束、时间尺度和制度处置。
- **新颖性 NO-GO**：“首次把清算建模为网络固定点/级联”不成立。Eisenberg–Noe 早已定义有限责任、绝对优先和按比例偿付下的清算支付固定点；银行间传染、支付网络流动性、CCP 网络拓扑、违约瀑布和抛售反馈都有庞大理论与监管研究。
- **Stage 0 窄方向 GO**：构建“清算机制辨别器”，在统一冲击下区分：债务违约清算、RTGS 盘中流动性阻塞、CCP 保证金/违约管理、共同持仓抛售。价值不在发现它们都像级联，而在证明哪些观测能排除错误机制。
- **Stage 1 当前 NO-GO**：公开数据不足以重建银行—银行债权、逐笔支付、CCP 成员头寸与保证金调用的联合网络。没有受控监管数据合作或可信外部验证前，只能做合成机制基准和公开数据可行性研究，不能作真实金融系统因果结论。

### 最强可防守 claim

> 不同金融清算制度都可产生非线性放大，但其守恒量、结算规则、可逆性和可观测先后顺序不同。一个有用的结构迁移引擎应首先辨别机制，而不是仅检测“级联”。

这是一项方法/benchmark 候选，不是新的金融普适律、风险预测器或监管替代品。

## 2. 已有工作：哪些不能再声称是空白

### 2.1 债务网络清算固定点

Eisenberg–Noe 已把互联机构的偿付写成同时决定的 clearing payment vector，并证明存在性，在温和正则条件下证明唯一性，同时给出清算算法和比较静态。因此“网络中的违约需要联立清算”“局部冲击会通过义务网络降低系统价值”均是已有核心结论，而不是本项目的新发现。[Eisenberg and Noe, 2001](https://pubsonline.informs.org/doi/10.1287/mnsc.47.2.236.9835)

其经典结构可写为：

\[
p_i = \min\{\bar p_i,\; x_i + \sum_j \Pi_{ji}p_j\},
\]

其中 `p_i` 是实际偿付、`\bar p_i` 是名义义务、`x_i` 是外部资产、`\Pi` 是相对义务矩阵。有限责任、绝对优先、按比例偿付是制度假设，不是所有清算场景都自动满足的自然定律。

后续银行网络模型已经把流动性囤积、银行间联系、非流动资产和抛售外部性纳入，并研究资本/流动性监管的稳定—效率权衡。[BIS Working Paper 597](https://www.bis.org/publ/work597.htm)

### 2.2 支付与结算网络

支付系统不是债务到期后的静态破产清算。RTGS 的关键变量是盘中流动性、支付时间、排队、入账资金循环和央行信贷。ECB 的 TARGET2 研究显示参与者会用账户余额、收到的支付和盘中信贷为付款融资，网络规模影响流动性循环机会。[ECB, Liquidity usage in TARGET2](https://www.ecb.europa.eu/press/economic-bulletin/articles/2021/html/ecb.ebart202103_03~2e159cbd38.en.html)

ECB 对 TARGET2 的压力测试本身已把系统视为参与者网络并在收紧流动性条件下评估韧性。[ECB Occasional Paper 183](https://www.ecb.europa.eu/pub/pdf/scpops/ecbop183.en.pdf) CPMI 也早已记录支付与结算基础设施之间的相互依赖既降低成本/部分风险，又可能使扰动更快、更广传播。[CPMI, 2008](https://www.bis.org/cpmi/publ/d84.htm)

### 2.3 CCP、净额结算与违约瀑布

中央清算通过多边净额减少双边暴露，但将 CCP 变成与会员、流动性提供者、托管机构相连的关键节点。违约处置还包含对违约会员头寸的对冲和拍卖、初始保证金、违约基金、CCP 自有资本及追加资源；这些是规则驱动的有序处置，不等同于 Eisenberg–Noe 的按比例清算。[Bank of England CCP stress-testing framework](https://www.bankofengland.co.uk/paper/2021/supervisory-stress-testing-of-central-counterparties)

CCP 网络拓扑和净额/保证金需求也已有专门研究。Bank of England 的拓扑论文明确研究不同 clearing network topology 下的暴露和保证金；该文当时留下的是违约、损失分配和其他处置程序，而非“网络清算”概念本身。[Garratt and Zimmerman, 2013](https://www.bankofengland.co.uk/-/media/boe/files/working-paper/2013/central-counterparties-and-the-topology-of-clearing-networks.pdf)

违约拍卖设计也已有机制研究，并指出某些投标激励和损失分配会把外部性转移给存续会员。[Ferrara, Li and Marszalec, 2017](https://www.bankofengland.co.uk/working-paper/2017/central-counterparty-auction-design)

### 2.4 保证金、融资和抛售反馈

监管数据已显示 CCP 保证金需求与回购融资之间存在顺周期的 collateral cycle：会员通过 repo 获得现金满足保证金，波动上升时该过程加强并推高 repo rate；CCP 再通过逆回购等把现金返还市场。[Benos, Ferrara and Ranaldo, 2022/2024](https://www.bankofengland.co.uk/working-paper/2022/margin-procyclicality-and-the-collateral-cycle)

共同持仓抛售模型也表明，忽略银行与非银共同资产持有会低估损失；pro-rata 与 waterfall liquidation 对系统和被动机构的影响不同。[Caccioli, Ferrara and Ramadiah, 2020/2022](https://www.bankofengland.co.uk/working-paper/2020/modelling-fire-sale-contagion-across-banks-and-non-banks) 使用 ECB 细粒度但非公开数据的研究甚至发现，在特定 26 家银行样本与冲击下，直接银行间传染很小，抛售价格效应更重要。[Aldasoro, Hüser and Kok, 2020](https://www.bankofengland.co.uk/working-paper/2020/contagion-accounting)

因此，“价格下跌—被迫出售—价格再跌”与“债务违约—少收款—再违约”不能因为都呈现级联就合并。哪个通道占主导是实证问题。

## 3. 真正可能的空白

### 3.1 不是统一级联模型，而是统一的机制辨别协议

现有研究常在各自制度内建立模型。对结构同构引擎有价值、且尚可形成独立贡献的窄问题是：

> 给定相似的聚合损失曲线，能否用少量可观测的时序、网络和制度干预，可靠区分信用清算、支付流动性阻塞、CCP 资源瀑布与共同持仓抛售？

这个问题把“找相似”改成“反驳伪同构”。可能产出：

1. 一套跨制度但不抹平制度差异的 state/flow/constraint 表示；
2. 一组机制可识别条件和不可识别区域；
3. 一个 matched-output benchmark：不同机制被校准成相似尾部损失或级联大小，再要求模型辨别；
4. 对每个候选迁移给出最小可区分观测，而不是泛化风险分数。

### 3.2 潜在的政策设计空白

只有在获得可信数据后，下面的窄问题才值得 Stage 1：

- 同一压力下，增加盘中流动性、释放保证金缓冲、改变 CCP 拍卖/损失分配、限制抛售速度分别产生何种不同的先后顺序和分配效应？
- 哪些干预只是把损失从一个网络层转移到另一个层，而非降低全系统损失？
- 当会员同时参与多个 CCP、支付系统和融资市场时，资源瀑布的分段不连续是否能预测跨基础设施的流动性峰值？

这些都已有邻近工作，不能预设新颖。必须以系统综述、外部领域专家和精确的增量 claim 再做新颖性判定。

## 4. 结构映射与制度边界

| 抽象元素 | 债务网络 | RTGS/支付 | CCP | 抛售网络 |
|---|---|---|---|---|
| 节点 | 债务人/债权人机构 | 结算账户/参与者 | CCP、会员、客户、流动性提供者 | 持有资产的机构与资产 |
| 边 | 名义债权 `L_ij` | 带时间戳的支付指令/资金流 | 合约暴露、保证金、基金与服务依赖 | 共同持仓及价格冲击 |
| 状态 | 外部资产、应付、实际偿付 | 可用盘中流动性、队列、入账 | 头寸、保证金、违约资源、拍卖状态 | 杠杆、持仓、市场深度、价格 |
| 约束 | 有限责任、优先级、比例偿付 | 实时全额结算、排队规则、央行信贷 | rulebook、净额、保证金、瀑布、恢复工具 | 资本/流动性约束、清算策略、价格影响 |
| 主要反馈 | 少收款导致自身支付能力下降 | 延迟付款减少他人可循环流动性 | margin/default call 造成会员资金压力 | 卖出压价导致更多约束触发 |
| 可逆性 | 违约损失通常不可逆 | 盘中延迟可能随流动性到达解除 | 依规则阶段与拍卖结果而定 | 取决于市场深度和买方约束 |
| 守恒/结算 | 名义义务上限与资产约束 | 中央银行货币转移、日内时间关键 | 净额和资源优先序关键 | 价格变化会改变账面财富，不是简单守恒流 |

### 不允许的直接映射

- `银行违约 = 支付延迟`：延迟可恢复，违约包含资本损失和法律状态。
- `CCP = 网络中的普通节点`：CCP 有法定 rulebook、净额、保证金、拍卖、瀑布和恢复处置权。
- `保证金阈值 = 债务到期额`：保证金由风险模型动态更新，并可能顺周期变化。
- `资产价格 = 清算支付比例`：价格由市场吸收能力和战略出售内生决定。
- `连接更多必然更危险`：连接既能分散/净额，也能传播；效果通常非单调并依赖拓扑与制度。

## 5. 因果不可识别与数据陷阱

### 5.1 单看级联大小无法识别机制

相同的违约数、尾部损失、峰度或 cascade-size 分布，可以由直接债权、共同持仓、宏观共同冲击、保证金调用、支付延迟或行为性囤积产生。幂律/厚尾尤其不构成机制识别。

### 5.2 网络本身是内生的

银行选择交易对手、资产组合、CCP 和流动性缓冲；监管、信用质量和预期冲击同时影响拓扑与损失。观察到中心节点先出问题不能证明中心性导致传播。

### 5.3 冲击与反应同时发生

价格下跌触发出售，出售又压低价格；保证金调用同时响应波动并改变融资市场。没有外生时序或工具变量，反馈增益不可从相关性唯一恢复。

### 5.4 公开数据不等于联合网络数据

- BIS consolidated banking statistics 是国家级聚合，官方明确说明数据按 reporting country 汇总，而非单家银行双边网络。[BIS CBS overview](https://data.bis.org/topics/CBS)
- EBA transparency data 提供银行级资本、风险暴露、资产质量等，但不是完整银行—银行债权矩阵或逐笔 CCP/支付数据。[EBA Transparency Exercise](https://eba.europa.eu/risk-and-data-analysis/risk-analysis/eu-wide-transparency-exercise)
- FDIC Call Reports 和失败清单可公开下载，适合资产负债表/失败事件研究，但不能恢复真实双边义务和盘中支付路径。[FDIC downloads](https://www.fdic.gov/bank-data-guide/data-downloads) [FDIC failed-bank list](https://www.fdic.gov/resources/resolutions/bank-failures/failed-bank-list/)
- TARGET annual reports提供系统规模、账户和聚合业务事实，不提供公开的参与者级逐笔支付网络。[ECB TARGET Services Annual Report](https://www.ecb.europa.eu/press/targetservar/html/ecb.targetservar2025.en.html)
- 许多最相关结果依赖监管专有数据；例如 contagion accounting 使用三套细粒度 ECB 专有数据。这一事实必须成为 feasibility gate，而不能用估算网络替代后继续声称真实验证。

## 6. 可区分预测

下面预测必须在看数据前冻结；它们是机制辨别预测，不是交易预测。

### P1：债务网络清算主导

- 在外部资产冲击固定后，损失首先沿有向债权关系传播；`t` 期少收款应预测下一轮偿付缺口。
- 改变相对义务矩阵而保持共同持仓不变，应显著改变违约集合。
- 若经典 EN 假设近似成立，实际偿付对可用资产具有单调性；若出现由拍卖/价格冲击引发的多稳态或路径依赖，经典模型不足。

**反驳**：控制共同冲击和持仓后，债权邻接不预测增量损失；传播主要随共同资产暴露发生。

### P2：RTGS 流动性阻塞主导

- 延迟应在付款时序和循环流动性下降后快速出现，并可因流动性注入或收到付款而日内解除。
- 结算延迟/排队长度可大幅变化，而最终信用损失不必变化。
- 等额流动性在高循环机会的拓扑中应支持更多结算；网络位置影响的是 timing/liquidity recycling，而非必然的资不抵债。

**反驳**：即使提供充足盘中流动性，损失仍由资产不足和最终违约决定。

### P3：CCP 保证金/违约管理主导

- 波动上升之后应先出现保证金/流动性调用，再出现 repo 融资压力或资产出售；时序不能倒置后仍声称 margin causal channel。
- 风险应在 waterfall 层级耗尽点、拍卖失败或追加资源触发处出现制度性折点，而非平滑 EN 比例偿付。
- 改变拍卖与损失分配规则可改变存续会员损失，即使初始市场冲击不变。

**反驳**：保证金调用控制后没有融资/抛售增量，或观测变化完全由共同波动解释。

### P4：共同持仓抛售主导

- 传播应沿 institution–asset 二部图发生；价格冲击和市场深度先于非直接债权机构的损失。
- 固定债权网络、改变共同持仓或 liquidation strategy 应显著改变损失；pro-rata 与 waterfall selling 产生不同分配结果。
- 直接债权网络可稀疏/弱传染，同时系统仍因价格影响出现放大；监管研究已有这种可能结果，故不能把所有放大归因于互欠。

**反驳**：在可信价格影响估计下，共同持仓不能解释传播，而债权少收款能解释。

## 7. 负对照与伪同构

1. **同聚合尾部、不同机制**：校准四个机制，使最终损失分布相近；只允许使用时序/网络/干预响应辨别。
2. **共同宏观冲击、无网络传播**：节点相关受损但没有边上传播，检查模型是否把相关性误判为 contagion。
3. **随机重连债权网络**：保持度数/总暴露，破坏真实对手关系；若结论不变，说明并未使用结构。
4. **随机置换共同持仓**：保持机构规模和资产流动性，破坏 institution–asset 对应。
5. **无限市场深度**：关闭价格影响；抛售机制应消失而债务清算仍可存在。
6. **充足盘中流动性**：支付延迟应缓解，但资产不足导致的最终违约不应神奇消失。
7. **无 margin procyclicality**：固定保证金或预注册缓冲释放，对照动态保证金路径。
8. **无违约但运营中断**：支付/CCP 服务延迟可存在，不应被标成信用传染。
9. **合成非网络重尾过程**：产生重尾 cascade-like 输出但无边机制，检验厚尾捷径。

## 8. 数据策略

### 8.1 可公开且可立即审计

| 数据 | 能做什么 | 不能做什么 |
|---|---|---|
| FDIC Call Reports + failed-bank list | 银行资产负债表、失败时间、公开事件研究 | 双边义务、逐笔支付、CCP 头寸 |
| EBA bank-level transparency/Pillar 3 | 银行级资本、资产、国家/类别暴露压力 | 完整 interbank adjacency、盘中 margin/payment flow |
| BIS LBS/CBS bulk data | 国家/部门级跨境暴露与宏观压力 | 单家银行网络与级联路径 |
| TARGET annual/aggregate statistics | 系统规模、结算量、制度变化描述 | 参与者级排队、循环与因果传播 |
| 央行/监管 CCP stress reports | 场景、规则、聚合损失和韧性边界 | 会员级头寸、完整 waterfall 路径和反事实 |

BIS 提供 LBS/CBS CSV/SDMX 批量下载，适合可复现宏观描述，但不能被包装成微观网络验证。[BIS bulk downloads](https://data.bis.org/bulkdownload)

### 8.2 合成数据

合成数据应覆盖：

- EN 基础网络与带 bankruptcy cost 的扩展；
- 带时间戳支付、排队和流动性循环的 RTGS；
- CCP rulebook 状态机、margin call、auction、waterfall；
- institution–asset 二部图、不同 liquidation strategy 和非线性 price impact；
- 多层组合与已知机制权重。

生成参数、seed 和目标机制必须由独立 benchmark 负责人冻结。合成数据只能验证辨别器和假阳性率，不能证明现实系统机制或政策效果。

### 8.3 Stage 1 所需但当前缺失

至少一项独立的数据合作须提供去标识、可审计的：

- 双边义务/支付或 CCP member–CCP 暴露；
- 事件时间、margin/payment call、settlement/queue 状态；
- 共同持仓或足以估计 price impact 的交易/头寸；
- 制度规则与政策变更时间；
- 明确许可、数据字典、缺失机制和复核人。

只拿到其中一个网络层时，claim 必须限制在该层，禁止推断全系统级联。

## 9. 最小实验

### Experiment 0A：机制辨别合成基准

**目的**：检验结构引擎是否能区分机制，而非是否能拟合级联曲线。

1. 独立生成四类各 250 个 scenario，并做 matched-output 配对；
2. 训练/开发只见部分参数区间，测试保留新拓扑、新 shock size 和混合机制；
3. 基线：聚合统计分类器、普通时间序列模型、图模型、强通用 AI+结构化输入；
4. 完整引擎必须输出 mechanism、关键边/变量、可区分干预、REJECT；
5. 主要终点：最差机制 balanced accuracy；硬门禁包括无机制/共同冲击任务的 specificity；
6. 消融：去时序、去制度规则、去网络层、只留 cascade size、随机边；
7. 所有 generator family 做 leave-one-family-out。

**Stage 0 通过线**：预注册后完整引擎优于最强同预算基线，且只留聚合级联统计时性能显著下降；未知/混合机制能可靠 REJECT。具体最小效应和置信界限必须在 pilot 前冻结。

### Experiment 0B：公开数据可行性与不可识别证明

用 FDIC/EBA/BIS 公开字段建立 data dictionary，明确哪些机制变量可观测。对公开边际量构造多组相互矛盾但同样拟合的潜在网络，量化结果对 reconstruction assumptions 的敏感性。

预期高价值结果可能是负结论：公开聚合数据无法识别网络机制。该结果应阻止错误 Stage 1，而不是用最大熵网络生成一个漂亮答案。

### Experiment 1：受控数据的事件研究/干预研究

仅在数据合作通过后预注册。候选设计：

- margin rule/anti-procyclicality buffer 的外生变更；
- RTGS 流动性规则或运行中断下的高频 event study；
- CCP default drill/真实 default management 的封存场景；
- 明确监管差异下的 fire-sale identification。

需要事件前趋势、同期共同冲击、spillover interference、选择进入制度和多重检验处理。历史关联不能升级为机制因果确认。

## 10. 风险与停止条件

### 科学风险

- **标签同义反复**：用生成器类型当 ground truth，再让模型读取生成器特征。
- **重建网络伪精确**：用最大熵/比例分配补全双边网络后，把假设当观测。
- **制度漂移**：把不同年份、法域、产品和 CCP rulebook 合并。
- **同时性偏误**：把 margin、volatility、repo rate 的同步变化当单向因果。
- **幸存者偏差**：只观察存续会员/银行和成功结算。
- **政策危险**：把 stress model 当实时预警、交易或机构排名。

### 强制停止

发生任一条件即停止相应 claim：

1. 结构引擎在 matched-output benchmark 不优于只用聚合统计的强基线；
2. 去除网络/制度字段后性能不下降，说明模型使用表面捷径；
3. leave-one-generator/topology/domain 外推崩溃；
4. 公开数据下不同合理网络重建给出方向相反的政策结论；
5. 无法获得源许可、rulebook 版本或独立数据字典；
6. 数据只含聚合损失而无时序/网络/干预，因果机制不可识别；
7. 负对照假阳性超过预注册上限；
8. 结果依赖事后选择冲击、网络重建或阈值；
9. 外部支付/CCP/银行监管专家判定制度映射错误；
10. 任何输出被解释成单家机构违约概率、投资建议或监管合规结论。

失败后的合理降级：作为教学型机制模拟器、压力测试假设审计器或“需要什么数据才能区分机制”的 protocol 工具；不能称风险预测引擎。

## 11. Stage 0 / Stage 1 门禁

### Stage 0：条件 GO

必须交付：

- 四机制的正式 state/flow/constraint schema；
- 独立生成、matched-output 的合成基准；
- 基线、消融、负对照和 leave-one-family-out；
- 不可识别报告，展示仅凭聚合级联量无法恢复机制；
- 至少一名支付系统专家、一名 CCP/衍生品清算专家和一名银行网络研究者盲审映射。

允许 claim：`The benchmark tests whether a system can discriminate stylised clearing mechanisms under controlled synthetic conditions.`

禁止 claim：现实金融传染已验证、可预测机构风险、发现统一清算定律。

### Stage 1：当前 NO-GO，满足以下条件才可转 GO

1. 独立数据合作提供至少两个网络层或一个网络层加可信外生制度干预；
2. 许可允许复现审计，至少可发布去标识统计/代码/封存摘要；
3. 问题、主要终点、网络重建、缺失处理和停止规则预注册；
4. 对照至少包括领域标准 stress model 与同预算通用 AI/图模型；
5. 数据保管人与引擎开发者分离，结果在输出冻结后解封；
6. 外部专家完成制度正确性和政策误用审查。

Stage 1 即使通过，也只能声称在指定制度、时间和数据下有机制辨别增益；跨 CCP、跨法域、跨危机和政策反事实需要新的外部验证。

## 12. 产品与论文边界

### 可以做

- 展示机制候选、支持证据、反证和缺失变量；
- 比较“若是 A 机制/若是 B 机制”需要的下一项观测；
- 运行合成压力 scenario 并清楚标注 simulated；
- 记录 NULL/REJECT 和 reconstruction sensitivity；
- 帮研究者生成预注册的最小区分实验。

### 不可以做

- “已确认清算级联普适存在”；
- “由公开数据恢复真实银行网络”；
- “预测下一家违约机构/下一次市场崩盘”；
- “CCP 与 DeFi/银行挤兑是同一个机制”；
- “模型可替代监管压力测试”；
- 用内部结构匹配分作为违约概率、系统重要性或政策建议置信度。

## 13. 最终建议

Track B 不应继续写成“清算级联的跨行业发现”。已有文献覆盖太深，宽 claim 既不新也不准确。应把它重构为本项目最符合 reject-aware 理念的一项测试：

> 当四种制度都产生看似相同的级联时，结构同构引擎能否知道它们并不相同，并提出最便宜、最可证伪的区分观测？

如果这个问题在独立合成基准和之后的受控数据上成立，它证明的是“结构迁移可帮助科学机制辨别”，而不是金融世界存在一个统一方程。这一较窄结论反而更可能成为严谨、可复现且对监管研究有用的 AI for Science 案例。
