# StructTuple 抽取 Prompt v2 — 严格分类指引

这份 prompt 是给 Opus agent 用的。目标是**强制它做精细分类**，而不是把所有公司都扔到 `ODE1_saturating` 兜底。

## 核心原则

1. **拒绝兜底**：`ODE1_saturating` 只能用于**真正处于 logistic 饱和后段、增长主要来自 ARPU 而非新增**的公司。如果公司还在 30%+ 增长，不能用 ODE1_saturating。
2. **优先更具体的分类**：27 个分类按"具体性"排序，越往后越具体。先看最具体的能不能套，不能再退。
3. **每份输出必须有 `why_this_family`**：一句话写清为什么选这个家族，而不是其他。

## 27 个 dynamics_family 分类指南 + 标志性公司

### 相变 / 临界现象类（最具体，优先匹配）

**`Phase_transition_1st`** — 一阶相变：某个参数越过临界值的瞬间，系统从一个稳态跳到另一个。商业上对应**监管悬崖、政治/法律断裂、技术代际切换**。
- ✅ 例子：Uber 中国（2016 网约车新规，几天内模式崩塌）、P2P 网贷（2018 监管）、字节跳动印度版 TikTok（一纸令下归零）
- ❌ 不是：缓慢下跌、营收转向这类渐变

**`Bistable_switch`** — 双稳态：系统有两个稳定平衡点，在临界参数附近切换。商业上对应**网络效应主导 vs 不主导**、**技术采纳 vs 被替代**。
- ✅ 例子：Tesla（EV 主流 vs niche 的双稳态，当前越过了 cusp）、BlackBerry（企业市场 vs 淘汰）、信用卡网络起步时
- ❌ 不是：单调增长或下滑

**`Fold_bifurcation`** — 鞍结分岔：参数改变让一个稳态消失，系统被迫跳到另一个。**一旦跳不能回来**。
- ✅ 例子：Peloton（疫情红利期→后疫情的鞍结，不可回归）、WeWork（估值期→破产）
- ❌ 不是：有弹性的波动

**`Hopf_bifurcation`** — Hopf 分岔：稳态失稳后变成**周期性振荡**。
- ✅ 例子：美团 vs 抖音本地生活（三体博弈 + 周期性补贴战）、DRAM 半导体周期
- ❌ 不是：单次跳变

**`Hysteresis_loop`** — 滞回环：系统有记忆，正向和反向走的是不同路径。
- ✅ 例子：房价（涨停板 vs 跌停板不对称）、品牌信任（崩塌快、重建慢）
- ❌ 不是：对称的上下浮动

**`Percolation_threshold` / `Percolation_network`** — 渗流阈值：网络节点达到临界密度时整个网络突然连通（或断裂）。
- ✅ 例子：早期 Facebook（大学间连通）、信用网络、电动车充电桩部署
- ❌ 不是：个体节点表现不相关的业务

**`Phase_transition_2nd`** — 二阶相变：连续但非解析变化，常伴随**临界放缓 + susceptibility 发散**。对应**对外部冲击反应幅度持续放大**的公司。
- ✅ 例子：Snowflake（网络效应 vs 商品化对撞）、Cisco 2000 年、BlackBerry 2010-11
- ❌ 不是：单一趋势主导的

### 网络传播类

**`Network_cascade`** — 级联传播：一个节点变化触发邻居变化，如病毒传播、银行挤兑、破产链条。
- ✅ 例子：Temu/拼多多海外（老带新爆发）、Clubhouse 2021、SVB 挤兑、LTCM 1998
- ❌ 不是：独立增长的（即便增长速度高）

**`Self_fulfilling_prophecy`** — 自我实现：预期本身驱动结果，典型如**资产泡沫、银行挤兑、汇率崩盘**。
- ✅ 例子：MicroStrategy（BTC 预期 → 加仓 → 推高 BTC → 预期更强）、2000 年互联网泡沫
- ❌ 不是：基于 fundamentals 的增长

### 延迟 / 反馈类

**`DDE_delayed_feedback`** — 延迟反馈（延迟微分方程）：作用和结果之间有时间滞后，导致振荡或延迟爆发。
- ✅ 例子：Peloton（灭绝债务，已经注定但延迟显现）、供应链牛鞭效应、养老金缺口
- ❌ 不是：即时反馈的

### 生态 / 博弈类

**`Game_theoretic_equilibrium`** — 博弈均衡：多方策略决定的稳态，任何一方改变策略都会打破。
- ✅ 例子：美团（商家/骑手/用户三体）、双边 marketplace、加密货币中的套利
- ❌ 不是：单边决策的

### 统计分布类

**`Power_law_distribution`** — 幂律分布：结果的大小呈幂律，少数极端值主导。
- ✅ 例子：VC 投资组合（少数独角兽贡献全部回报）、Twitter 内容传播、城市人口
- ❌ 不是：Gaussian 分布的

**`Heavy_tail_extremal`** — 重尾极值：正态假设失效，黑天鹅事件主导风险。
- ✅ 例子：保险尾部风险、对冲基金爆仓、加密交易所（FTX）
- ❌ 不是：稳定分布的

### 增长类（默认倾向，谨慎使用）

**`ODE1_exponential_growth`** — 纯指数增长：在刚刚突破临界点、还远离饱和的早期。**只用于真正爆发期**。
- ✅ 例子：NVIDIA 2023-2025 数据中心（runaway positive feedback 接近临界）、OpenAI 2023 用户增长早期
- ❌ 不是：已减速的成长股

**`ODE1_exponential_decay`** — 纯指数衰减：收入/用户基数本身持续萎缩。
- ✅ 例子：Intel 传统 PC 业务、Kodak 2005-2012、有线电视订户
- ❌ 不是：增速放缓但绝对值还在涨的

**`ODE1_logistic` / `ODE1_saturating`** — 逻辑斯蒂饱和：S 曲线后段，承载量约束明显。**只用于确实到了 60%+ 渗透率、增长主要靠 ARPU 的公司**。
- ✅ 例子：Netflix（K_eff 约 3.48 亿，当前 2.65 亿 = 76%）、McDonald's、可口可乐
- ❌ 不是：仍在 20%+ 年增长的公司

**`ODE1_linear`** — 线性增长：成熟稳定生意，增长线性跟随市场。
- ✅ 例子：Coca-Cola、Walmart、Costco（会员 ARPU 递增型）
- ❌ 不是：有明显拐点的公司

### 振荡类

**`ODE2_damped_oscillation`** — 阻尼振荡：周期性波动但振幅逐渐减小。
- ✅ 例子：成熟周期股（能源、材料）在需求波动下的价格表现

**`ODE2_undamped_oscillation`** — 无阻尼振荡：持续的周期性波动，无衰减。
- ✅ 例子：期货市场、汇率短周期、某些商品价格

### 扩散类

**`PDE_reaction_diffusion` / `PDE_diffusion` / `PDE_wave`** — 偏微分方程扩散：空间扩散结构主导。
- ✅ 例子：BYD 海外扩张（Fisher-KPP 行波）、疫情时空蔓延、文化扩散
- ❌ 不是：单点增长的

### 不确定 / 其他

**`Markov_chain`** — 马尔可夫链：离散状态转移。
- ✅ 例子：信用评级迁移、用户流失漏斗、客户生命周期

**`Stochastic_process`** — 一般随机过程：没有明显动力学主导，噪声驱动。
- ✅ 例子：高频交易环境、事件驱动型对冲基金业务

**`Random_walk`** — 随机游走：无漂移的累积随机过程。

**`Unknown`** — **只有在真的无法分类时才用**。每个公司都有某个主导动力学，不要偷懒用 Unknown。

## 输出要求

```json
{
  "ticker": "NVDA",
  "name": "NVIDIA",
  "exchange": "NASDAQ",
  "country": "US",
  "industry": "Semiconductors / AI",
  "market_cap_usd": 3500000000000,
  "dynamics_family": "ODE1_exponential_growth",
  "why_this_family": "仍在 100%+ YoY 数据中心增长，客户 capex 飞轮仍在加速，未见减速信号。选 exp_growth 而不是 saturating，因为 saturating 需要明确的 K 约束证据，NVDA 目前还看不到。",
  "feedback_topology": "positive_loop",
  "boundary_behavior": "runaway",
  "timescale_log10_s": 7,
  "phase_state": "approaching_critical",
  "canonical_equation": "dI/dt = alpha*I*(P - Q) (Semenov thermal explosion)",
  "critical_points": ["四大 hyperscaler 任一减单 25%+", "成本 / 价格弹性穿过 k=1"],
  "confidence": 0.85,
  "note": "runaway positive feedback 接近临界，任何关键客户减单都会引发级联收缩"
}
```

## 硬规则（违反即改）

1. **不要给所有公司都打 ODE1_saturating**。先问"它真的在饱和后段了吗？"再做决定。
2. **每个 company 都必须有 `why_this_family`**。一句话说清楚为什么不选其他类别。
3. `phase_state` 必须和 `dynamics_family` 一致——比如 `ODE1_exponential_growth` 不能搭 `saturated`。
4. `critical_points` 必须是**具体可观测**的（"营收 YoY 跌破 20%"），不是模糊的（"市场情绪变化"）。
