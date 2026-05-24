# V2 严格筛选 → 94 顶级发现的深度分析

> 94 个 5/5 评分发现经 10 个并行 Agent 深度分析：19 A 级、22 B+、36 B、17 C

## 总览

| 维度 | 数量 |
|---|---|
| 输入（初筛 5/5） | 94 |
| 深度分析后 **A 级** | **19** |
| B+ 级 | 22 |
| B 级 | 36 |
| C 级（降级） | 17 |
| A+B+ 可推进 | 41 |

**核心洞察**：初筛 5/5 ≠ 深度同构 A 级。94 个候选经 5 维严格评审后，19 个（20%）真正配得上独立论文，22 个值得写成 B+ 级 perspective，17 个在机制层崩塌降级为 C（被证实是"普适律陷阱"或"同域伪装"）。

## 19 个 A 级发现（按 final_score 降序）

| # | Score | Rank | 现象 A | 现象 B | 领域 | 目标刊 |
|---|---|---|---|---|---|---|
| 1 | 8.6 | 1381 | 永冻土融化释放甲烷的延迟反馈 | 灭绝债务 | 环境科学×保育生物学 | Nature Climate Change / Trends |
| 2 | 8.6 | 1863 | 半导体激光器驰豫振荡阻尼特性 | 稳定币的锚定机制 | 光学/光子学×加密货币与DeFi | Physical Review Applied / Quan |
| 3 | 8.5 | 3088 | 渗流阈值导电网络转变 | 技术采纳的鸿沟 | 凝聚态物理×创业与风险投资 | Nature Human Behaviour / PNAS |
| 4 | 8.5 | 3248 | 免疫多样性的超优势选择 | 模型集成 | 进化生物学×机器学习 | Nature Machine Intelligence /  |
| 5 | 8.4 | 733 | 灭绝债务 | 厄尔尼诺的延迟振子 | 保育生物学×海洋学 | Proceedings of the Royal Socie |
| 6 | 8.4 | 2016 | 湖泊富营养化的临界翻转 | 植被反馈的绿色撒哈拉 | 生态学×气候科学 | Nature Climate Change / PNAS |
| 7 | 8.3 | 72 | 交通拥堵的非线性 | 热固性树脂凝胶点渗流相变 | 城市规划×高分子化学 | Physical Review E / PNAS |
| 8 | 8.3 | 1823 | 全球失衡的镜像对称 | 扰动前馈补偿 | 国际经济×控制工程 | Automatica / Journal of Intern |
| 9 | 8.3 | 4493 | 放热反应的温度曲线 | 影子银行的信用创造乘数 | 化学×宏观经济 | Journal of Financial Stability |
| 10 | 8.2 | 682 | 信任的建立与崩塌 | 珊瑚白化的滞后恢复 | 社会学×生态学 | Nature Human Behaviour / Ecolo |
| 11 | 8.2 | 1275 | 生态系统突变 | 热固性树脂凝胶点渗流相变 | 生态学×高分子化学 | Ecology Letters / Nature Ecolo |
| 12 | 8.1 | 1494 | 费托合成原位相重构 | 热固性树脂凝胶点渗流相变 | 催化化学×高分子化学 | Physical Review Materials / Jo |
| 13 | 8.1 | 2397 | 薄壁件数控加工颤振 | 算法稳定币死亡螺旋 | 机械工程×区块链/Web3 | Nonlinear Dynamics / Journal o |
| 14 | 8.0 | 905 | CRISPR-Cas系统的间隔序列获取 | VC投资组合的幂律收益结构 | 微生物学×创业/VC | PNAS / Journal of Theoretical  |
| 15 | 8.0 | 4115 | 限流的令牌桶 | Piezo1机械门控通道的不动点门控 | 计算机科学×细胞生物学 | PLOS Computational Biology / B |
| 16 | 8.0 | 4202 | 技术采用的跨越鸿沟 | 热固性树脂凝胶点渗流相变 | 商业×高分子化学 | Journal of Statistical Mechani |
| 17 | 7.5 | 3531 | 湖泊富营养化的临界翻转 | 蛋白质相分离的临界浓度阈值 | 生态学×分子生物学 | Nature Physics (perspective) / |
| 18 | 7.5 | 4116 | 认知失调的一致性修复 | Lyapunov稳定性分析 | 行为经济学×控制工程 | Psychological Review / IEEE Co |
| 19 | 7.5 | 4227 | Piezo1机械门控通道的不动点门控 | 参考点适应的享乐跑步机 | 细胞生物学×行为经济学 | Trends in Cognitive Sciences / |

## Top 10 A 级详细分析

### #1381 永冻土融化释放甲烷的延迟反馈 × 灭绝债务 (Score 8.6)

- **跨域**：环境科学 × 保育生物学
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：Committed but Concealed: A Unified Delay-Debt Framework for Permafrost Methane and Extinction Debt
- **目标刊**：Nature Climate Change / Trends in Ecology & Evolution
- **共享方程**：
  - `Delay ODE: dx/dt = f(x(t - tau)) - mu x(t)`
  - `Committed change C = integral_{t0}^{infty} [x*(t) - x(t)] dt`
  - `Extinction debt D = S_current - S_equilibrium(t -> infty)`
- **深度分析**：这是我判断最有原创性的一组。'承诺未现'这个结构在两个领域都独立发展，但没有人把它们放到同一数学框架下。共享的不仅是延迟反馈，还有'评估方法系统性低估真实风险'和'决策窗口已关闭但症状未现'这两个认知结构——这是罕见的具有政策含义的深度同构。可以用延迟微分方程 x'(t) = f(x(t - tau)) 统一建模，并给出两领域'债务余额'的可比较估计。目标期刊可瞄准 Nature Climate Change 的 perspective 或 TREE 的 opinion。独立研究者可行，关键是与相关领域专家建立轻度合作做数据校准。这一对值得作为项目首批产出重点推进。
- **实际价值**：提供一个可度量的'承诺债务'指标，量化当前稳态背后隐藏的未来塌缩量，可用于气候、生态、养老金等所有具有长时滞响应的系统，直接影响政策折现率和风险评估。
- **风险**：两者都有大量独立文献，论文必须真正做出跨域的统一形式（例如共同的延迟微分方程和债务估计方法），否则仅做类比没有价值。另一个风险是'承诺量'的测量在两领域都很难，数据可能不足以支撑严肃估计。
- **执行计划**：
  - 形式化延迟-债务统一方程并推导可观测指标
  - 用 IPCC 永冻土数据和生境碎片化数据做债务估计
  - 撰写 perspective 投 Nature Climate Change
- **时间**：5-8 个月 | **单人可行**：是 | **影响**：cross-field

### #1863 半导体激光器驰豫振荡阻尼特性 × 稳定币的锚定机制 (Score 8.6)

- **跨域**：光学/光子学 × 加密货币与DeFi
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：Relaxation Oscillations in Algorithmic Stablecoins: A Laser Rate-Equation Analogy
- **目标刊**：Physical Review Applied / Quantitative Finance
- **共享方程**：
  - `dN/dt = J/qV - N/τ_n - g(N-N_0)S`
  - `dS/dt = Γg(N-N_0)S - S/τ_p + βN/τ_n`
  - `ω_r = sqrt(g·S₀/τ_p), ζ = (1/τ_n+gS₀)/(2ω_r)`
- **深度分析**：这是本批次中机制映射最清洁的一对：激光器速率方程(载流子N, 光子S)与算法稳定币(配对币供应, 稳定币价)都是两个耦合变量通过速率方程互相驱动，形成阻尼谐振子。Terra/UST崩溃的事后分析表明其动态完全可用阻尼不足的二阶系统描述，而DeFi文献几乎没人引用激光物理。论文可以提出一个从激光速率方程推导的稳定币稳定性设计准则(阻尼比ζ>临界值)，并用UST、FRAX、DAI的历史链上数据拟合。单人5个月内可完成，发表前景好。
- **实际价值**：把激光速率方程的线性稳定性分析直接搬到算法稳定币设计，可给出量化的阻尼比、谐振频率与临界铸销速率，对UST式崩盘有预警作用。
- **风险**：稳定币系统包含博弈论因素(套利者预期)，线性ODE可能在极端行情下失效；加密领域的学术接受度和数据真实性需谨慎。
- **执行计划**：
  - 推导通用双变量稳定币速率方程与线性化稳定性条件
  - 用UST链上时序数据拟合阻尼比与谐振频率
  - 给出设计参数与崩盘临界曲线
- **时间**：4-5个月 | **单人可行**：是 | **影响**：cross-field

### #3088 渗流阈值导电网络转变 × 技术采纳的鸿沟 (Score 8.5)

- **跨域**：凝聚态物理 × 创业与风险投资
- **同构深度**：5/5
- **文献状态**：partial
- **论文标题**：Percolation Phase Transition in Technology Adoption: Crossing the Chasm as a Geometric Critical Phenomenon
- **目标刊**：Nature Human Behaviour / PNAS
- **共享方程**：
  - `σ(p) ∝ (p-pc)^t, p>pc`
  - `P∞(p) ∝ (p-pc)^β`
  - `ξ ∝ |p-pc|^(-ν)`
- **深度分析**：这是十个中最干净的同构之一：导电网络渗流与技术采纳鸿沟共享完全相同的几何相变结构，宏观序参量（电导率/市场渗透率）在临界点以幂律涌现，低于阈值时只有孤立集团。数学上可直接套用渗流临界指数β和相关长度ν。已有部分社会物理学文献尝试过但未把'鸿沟'这一管理学概念与严格pc关联。可发展为可预测商业指标的理论-数据双栖工作，若能用真实采纳数据拟合出符合渗流普适类的临界指数，贡献度显著。
- **实际价值**：为Moore的'鸿沟理论'提供严格的渗流临界理论基础，可量化计算不同行业的技术采纳临界阈值pc，并把幂律起跳指数作为早期判断产品是否会跨越鸿沟的指标，直接为VC投资决策提供新工具。
- **风险**：社会网络的异质性和动态重连比格子渗流复杂得多，pc值依赖网络拓扑，若用标准bond percolation过度简化，会被社会学家指出忽略关键变量如社群结构。
- **执行计划**：
  - 采集5-10款典型SaaS/硬件产品的用户采纳时序与社交图
  - 拟合渗流临界指数并与普适类比较
  - 构建可投资决策使用的'距离pc'指标并做回测
- **时间**：4-6个月 | **单人可行**：是 | **影响**：cross-field

### #3248 免疫多样性的超优势选择 × 模型集成 (Score 8.5)

- **跨域**：进化生物学 × 机器学习
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：MHC Heterozygote Advantage as Natural Ensemble Learning: A Bias-Variance Perspective on Immune Diversity
- **目标刊**：Nature Machine Intelligence / PNAS
- **共享方程**：
  - `w̄ = Σ p_i·w_ii + 2Σ p_i·p_j·w_ij`
  - `E[(y-f̄)²] = Bias² + Var/N + (1-1/N)Cov`
- **深度分析**：这是少有的两个方向都能互相启发的深层同构。MHC超优势选择在群体层维持多样性，恰似集成学习维持模型多样性的偏差-方差权衡；频率依赖选择的负反馈机制对应集成中的diversity regularization。若能从群体遗传学导出最优集成大小的分析式，或从ML bias-variance导出MHC位点数量的预测，将形成真正双向贡献。Nature系列对这类跨学科概念迁移历来青睐。执行风险在于需要同时熟悉两个领域的数学工具。
- **实际价值**：把偏差-方差分解的理论语言引入群体免疫学，定量解释MHC多态性为何维持、最优等位基因数量的理论上限，并反向为集成学习提供'频率依赖选择'的多样性维持机制，设计自适应模型多样性算法。
- **风险**：两者都已有独立成熟理论，贡献点需在交叉的可验证预测上。若只是把两套语言对齐而无新预测，会被视为重新表述已知结果。
- **执行计划**：
  - 建立MHC频率依赖选择的动力学方程
  - 映射至集成学习的bias-variance-covariance分解
  - 导出最优多样性规模的闭式解并在两个领域各做验证
- **时间**：4-6个月 | **单人可行**：是 | **影响**：cross-field

### #733 灭绝债务 × 厄尔尼诺的延迟振子 (Score 8.4)

- **跨域**：保育生物学 × 海洋学
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：Extinction Debt as a Delayed Oscillator: Unifying Rossby-Wave Memory and Habitat-Destruction Lag
- **目标刊**：Proceedings of the Royal Society B / Theoretical Ecology
- **共享方程**：
  - `dN/dt = rN(1 - N/K) - α·N(t-τ)`
  - `dT/dt = T - T³ - δ·T(t-τ) （Suarez-Schopf）`
  - `Hopf分岔条件: ατ = π/2 + 2kπ`
- **深度分析**：这一对的同构强度非常高：Suarez-Schopf的延迟微分方程dT/dt = T - T³ - α·T(t-τ)可以直接改写为'生境破坏当前稳态→世代反馈延迟→未来灭绝'的形式，延迟项的物理意义从波传播时间变为世代时间，数学结构完全一致。价值在于ENSO文献已有成熟的delay-induced Hopf分岔分析与稳定岛结构，可直接迁移用于预测灭绝债务的'偿还时间窗口'和可能的振荡式灭绝脉冲。核心风险是真实生态系统的延迟是分布而非单一值，需要用distributed delay推广。若能找到一个经验数据集（如新热带雨林破碎化后的物种损失时间序列）做参数拟合，论文可以突破纯理论范畴。
- **实际价值**：把ENSO延迟振子（Suarez-Schopf方程）的频率-延迟标度关系迁移到灭绝债务，给保育生物学一个可预测的'生态债务偿还时滞'估算公式。
- **风险**：ENSO延迟振子已有近40年数学研究，灭绝债务虽有Tilman奠基但数据稀疏；论文需要靠'数学同构+参数迁移'立住，容易被批机制不同。
- **执行计划**：
  - 把Tilman灭绝债务方程显式写成延迟微分方程
  - 引入Suarez-Schopf的Hopf分岔分析得到振荡灭绝条件
  - 用Barro Colorado或亚马逊破碎化数据做数值验证
- **时间**：3-4个月 | **单人可行**：是 | **影响**：cross-field

### #2016 湖泊富营养化的临界翻转 × 植被反馈的绿色撒哈拉 (Score 8.4)

- **跨域**：生态学 × 气候科学
- **同构深度**：5/5
- **文献状态**：partial
- **论文标题**：Unified Fold-Bifurcation Signatures across Lake Eutrophication and Sahara Greening
- **目标刊**：Nature Climate Change / PNAS
- **共享方程**：
  - `dx/dt = r - bx + x²/(h²+x²) (Scheffer normal form)`
  - `Var(x_t), AC(1) → ∞ as r → r_c (EWS)`
  - `dV/dt = αVP - γV; dP/dt = f(V) - P/τ (vegetation-precipitation)`
- **深度分析**：这是教科书级的深度同构——Scheffer学派的折叠分岔框架本就是为这类系统设计,两者共享同一规范形式 dx/dt = r - x + x²/(1+x²),只是参数尺度不同。文献上湖泊EWS与气候临界点已各自建立,但系统性地把二者作为同一普适类进行交叉验证的工作仍有空间,尤其是利用湖泊高频数据标定EWS指标再外推到古气候。关键是要找到一条可以同时做两种时标分析的湿地/小湖古沉积序列。执行门槛在数据和古气候合作者,不在数学。若能用单一贝叶斯框架同时拟合两类系统的翻转,足以支撑一篇高影响力论文。
- **实际价值**：把湖泊生态学发展成熟的早期预警指标(方差增大、自相关上升、skewness)直接迁移到古气候植被-降水耦合系统,为识别地球系统临界点提供跨尺度验证方法。
- **风险**：古气候数据分辨率粗,早期预警信号检测的假阳性率高;两个系统的时标差4个数量级(年vs千年),动力学相似不代表数值方法可直接套用。
- **执行计划**：
  - 提取5-10个湖泊富营养化时间序列+绿色撒哈拉古气候序列
  - 统一贝叶斯框架拟合折叠分岔参数与EWS
  - 投PNAS或Nature Climate Change
- **时间**：6-9个月 | **单人可行**：否 | **影响**：cross-field

### #72 交通拥堵的非线性 × 热固性树脂凝胶点渗流相变 (Score 8.3)

- **跨域**：城市规划 × 高分子化学
- **同构深度**：5/5
- **文献状态**：partial
- **论文标题**：Percolation Universality Class Shared by Traffic Jamming and Thermoset Gelation: Critical Exponents and Finite-Size Scaling
- **目标刊**：Physical Review E / PNAS
- **共享方程**：
  - `P∞ ∝ (p - p_c)^β, β_{2D}=5/36`
  - `ξ ∝ |p - p_c|^(-ν), ν_{2D}=4/3`
  - `S(L,p) = L^{γ/ν} F((p-p_c) L^{1/ν})`
- **深度分析**：交通拥堵相变与热固性树脂凝胶点都属于几何连通性相变，在临界密度/转化率处出现无穷大连通团。两者共享渗流普适类的临界指数：相关长度 ξ∝|p-p_c|^(-ν)、最大团大小 S∝|p-p_c|^(-γ)，且都表现出有限尺度标度 P∞(L) ~ L^(-β/ν) f(L^(1/ν) ε)。这一同构的独特价值在于：高分子领域已通过精细流变学实验把指数测到三位有效数字，而交通领域的临界指数测量受限于道路拓扑噪声。若能证明二者属同一普适类，则可直接跨域迁移 ν≈4/3 (2D)、β≈5/36 等精确值，为城市拥堵的早期预警提供第一性原理支撑。反向亦可用高分辨交通 GPS 数据验证渗流理论的某些预测。
- **实际价值**：把高分子物理中精确测量的渗流临界指数（β、γ、ν）迁移到城市交通相变预测，可提供比现有经验模型更严格的拥堵预警阈值估计。反向则用交通流高维实测数据验证普适类假设。
- **风险**：两边的连通性定义不同：交通是动态连通（车流时空网络），凝胶是静态几何连通，是否真属于同一普适类仍有争议，需严格的指数测量来确认。
- **执行计划**：
  - 收集公开交通 GPS 数据（如深圳/北京 TaxiData），测量拥堵团大小分布的临界指数
  - 用 Flory-Stockmayer 凝胶模型生成对照数据，比较 β、γ、ν 是否一致
  - 若指数吻合则写成短文投 PRE；若发现新普适类则投 PNAS
- **时间**：6-9 个月 | **单人可行**：是 | **影响**：cross-field

### #1823 全球失衡的镜像对称 × 扰动前馈补偿 (Score 8.3)

- **跨域**：国际经济 × 控制工程
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：Conservation Laws as Feedforward Compensation: From Global Current Account Imbalances to Control Engineering
- **目标刊**：Automatica / Journal of International Economics
- **共享方程**：
  - `Σ_i CA_i(t) = 0 ∀t`
  - `u_ff(t) = -G_d(s)/G_p(s)·d(t)`
  - `y(t) = G_p(s)·(u_fb(t)+u_ff(t)) + G_d(s)·d(t)`
- **深度分析**：两者共享'加法守恒律'这个最干净的代数骨架：全球经常账户之和恒为零等价于前馈补偿中的扰动-补偿和为零。真正的学术价值在于把控制工程的'前馈+反馈'层次结构映射到国际货币体系：前馈补偿=经常账户再平衡机制，反馈控制=汇率调节。这个映射在Engineering与Economics之间几乎未被严肃形式化过(Minsky、Godley的流量存量模型接近但非控制论框架)。论文的关键是给出一个最小可控模型并证明某种稳定性定理。推荐投Automatica的跨学科专栏或IJE的方法论专辑。
- **实际价值**：将控制工程的前馈补偿设计思想引入全球失衡监测，可为IMF等机构提供系统级稳定性指标与早期预警控制律。
- **风险**：守恒律层面的同构是数学恒等式层面的，未必带来新的经济预测；控制工程方法应用到宏观经济常被批评为'假设违反现实'。
- **执行计划**：
  - 形式化全球N国经常账户为MIMO控制系统
  - 推导守恒律下的前馈-反馈分解
  - 用IMF BOP数据做控制性能评估
- **时间**：4-6个月 | **单人可行**：是 | **影响**：cross-field

### #4493 放热反应的温度曲线 × 影子银行的信用创造乘数 (Score 8.3)

- **跨域**：化学 × 宏观经济
- **同构深度**：4/5
- **文献状态**：unexplored
- **论文标题**：Thermal Runaway and Credit Runaway: An Arrhenius-Type Model of Shadow Banking Leverage Cascades
- **目标刊**：Journal of Financial Stability / Physica A
- **共享方程**：
  - `dT/dt = Q·A·exp(-E/RT) - h(T-T_a)`
  - `Semenov 临界：δ = (Q·A·E/R·T_a^2)·exp(-E/RT_a)·(V/hS) = e^(-1)`
  - `Frank-Kamenetskii：∇^2θ + δ·e^θ = 0`
- **深度分析**：这是四对中同构度最高、最可能产出真正研究的一对。核心洞察是：放热反应的失控来自 Arrhenius 律 k=A·exp(-E/RT) 的正反馈，而影子银行每一层再抵押相当于把「有效温度」（风险偏好/估值）放大，整体系统方程在数学形式上可以写得高度相似——都是 dT/dt = α·exp(βT) - γ·T 这样的指数自催化+线性耗散。深层价值在于把化学工程中非常成熟的「热失控判据」（Semenov 准则、Frank-Kamenetskii 参数）整体迁移到金融，这是 Minsky 金融不稳定性假说从定性到定量的一个具体路径。关键挑战是找到 BIS/FSB 的高频杠杆数据，并证明 Semenov 型临界条件在 2008、2020 前能被检测到。可作为独立实证论文。
- **实际价值**：若影子银行的杠杆级联能用 Arrhenius 型指数放大律刻画，可为宏观审慎监管提供「热失控阈值」类的量化指标（临界杠杆率、级联时间常数）。
- **风险**：金融数据粒度有限（月度/季度），难以拟合快速指数增长相位；2008危机样本只有一次，统计检验力弱；化学放热反应的「能量守恒约束」在金融系统中没有直接对应物。
- **执行计划**：
  - 从 BIS 全球流动性指标和 FSB 影子银行监测报告提取 2002-2024 月度杠杆代理变量
  - 拟合 Semenov/Frank-Kamenetskii 型模型，计算等效 δ 参数的历史轨迹，检验危机前是否越过临界值
  - 写成定量实证论文投 Journal of Financial Stability 或 Physica A，备选 Quantitative Finance
- **时间**：6-8个月 | **单人可行**：是 | **影响**：cross-field

### #682 信任的建立与崩塌 × 珊瑚白化的滞后恢复 (Score 8.2)

- **跨域**：社会学 × 生态学
- **同构深度**：5/5
- **文献状态**：unexplored
- **论文标题**：Asymmetric Recovery Thresholds: Unifying Social Trust Collapse and Coral Bleaching Hysteresis under a Preisach Framework
- **目标刊**：Nature Human Behaviour / Ecology Letters (方法论角度)
- **共享方程**：
  - `T_recovery < T_bleach (非对称阈值)`
  - `W_repair = ∫_{path_up} F·dx > W_damage = ∫_{path_down} F·dx`
  - `μ(α,β) = Preisach密度, supp(μ) 在 α>β 半平面`
- **深度分析**：这是整批10对中最具跨界启发性的一对：两者都满足'正反路径不重合+恢复代价严格大于破坏代价+存在记忆性'这三个Preisach迟滞的核心特征，且珊瑚恢复阈值的量化方法（Δ_recovery > Δ_bleach）有直接的社会学对应物（'信任修复需要比维持更严苛的条件'）。论文的独特价值不在于两边分别的研究，而在于给出一个统一的Preisach代价不等式，并据此预测不同类型冲击下的信任恢复时间。比678更扎实的理由是珊瑚文献已有温度-时间的精确阈值函数，可直接作为社会对照系的'金标准'，不像交通流要处理实时守恒律。建议作为研究重点，单作可投Nature Human Behaviour方法论板块。
- **实际价值**：把珊瑚迟滞回路的恢复阈值估算方法（退温曲线需低于白化触发温度才恢复）迁移为'信任修复阈值'的形式化表达，给危机公关和组织重建提供可量化的代价函数。
- **风险**：与678号高度重叠（都用Preisach），需要在两篇中差异化定位；生态-社会的机制桥梁需要设计实验来验证，否则仍是类比。
- **执行计划**：
  - 从珊瑚白化文献提取恢复阈值函数的参数化形式
  - 收集10-20个组织信任崩塌-修复案例的时间序列
  - 拟合Preisach密度μ并检验代价不等式
- **时间**：4-5个月 | **单人可行**：是 | **影响**：cross-field

## 完整 pipeline 回顾

```
V2 模型 (5689 训练样本)
  → 4443 现象 KB × pairwise 相似度 (T≥0.70)
  → 4533 跨域高相似对
  → 50 批 LLM 三重筛选（严格评分 1-5）
  → 94 个 5/5 顶级同构 + 667 个 4+ 高潜力
  → 10 批深度分析（5 维评估）
  → **19 A 级 + 22 B+ = 41 个可推进发现**
```

## 相关文件

- `results/v2m-deep-analysis-all.jsonl` — 94 个完整深度分析
- `results/v2m-a-rated.jsonl` — 19 个 A 级发现
- `results/v2m-top5.jsonl` — 94 个 5/5 初筛结果
- `results/v2m-screened-all.jsonl` — 完整 4533 对筛选
