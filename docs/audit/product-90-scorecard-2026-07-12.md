# Structural Isomorphism 产品 90 分审计

> 日期：2026-07-12  
> 范围：beta Structural Workbench + Phase Detector  
> 角色：资深产品总监 / UX 负责人  
> 状态：只读审计快照；认证入口正在由另一线程修复，本文不修改其文件

## 1. 结论

当前综合分 **74.0 / 100**，属于“可信、功能较完整的研究预览”，还不是可证明留存价值的 90 分产品。

| 维度 | 得分 | 90 分门槛的主要差距 |
|---|---:|---|
| 功能完整性 | 84 | beta 账户无真实产品内状态；英文检索未过上线门禁；报告分组浏览器测试尚未进入 CI |
| 使用体验 | 76 | 指纹仍由用户从空白表单开始；候选证据密度高；报告首值慢；跨产品入口割裂 |
| 用户价值 | 68 | 尚无 15–20 个真实 ICP 任务与 outcome；候选证据仍是检索级；Phase 本身只有方法展示价值 |
| 端到端动线 | 68 | 注册跨域不统一；实验只在重开报告后明显；没有真实 3/7/14 天触达；复访依赖本机匿名标识 |
| **等权综合** | **74.0** | **先关闭 P0，再完成真实用户验证，才可能超过 90** |

首发 ICP 应保持为：**研究密集型产品经理 / 增长负责人**。核心 JTBD 是：

> 我被一个复杂业务问题卡住时，帮我找到一个非显然但可检验的跨领域方法，并在 7 天内决定继续、调整或停止。

建议北极星：**Weekly Verified Transfer Outcomes**，即每周由报告 owner 完成实验并记录 result + learning 的独立迁移数。

## 2. 评分与扣分规则

所有维度从 100 分起扣。相同根因只在最相关维度扣一次，避免重复惩罚。

### 2.1 功能完整性：84 / 100

| 扣分 | 证据 | 规则 |
|---:|---|---|
| -6 | beta 导航出现 `/auth/login`，但当前产品没有 beta 账户页与账户态报告归并；Phase 使用 host-only `phase_session` | 公开主 CTA 404 或登录后不能兑现产品内状态：每条 -5 至 -10 |
| -4 | MiniLM 只在旧固定池有正信号；expanded human judgments、holdout、中文回归未完成 | 核心语言对目标用户不可可靠使用：-4 至 -10 |
| -3 | 报告 Today/Week/Waiting/Completed 已有 E2E，但 CI browser job 的 `-k` 只运行 workbench 候选旅程 | 关键新功能有测试但不在 fail-closed CI：-3 |
| -3 | Phase 静态 gate 不能覆盖约 378 处 JSX 控件；生产 live E2E 仍是 soft-fail | “全站可用”没有与声明等价的行为证据：-3 至 -8 |

已得分项：KB/embedding/model manifest fail closed；OOS 拒绝；候选显式选择；报告持久化 opt-in；结构化实验/outcome；真实邮箱 magic link；Phase SSR、性能与生产 smoke。

### 2.2 使用体验：76 / 100

| 扣分 | 证据 | 规则 |
|---:|---|---|
| -6 | `openFingerprintReview()` 仅把原问题复制到 summary，变量/约束/未知默认全空 | 核心步骤把模型工作转嫁给不懂术语的用户：-5 至 -8 |
| -4 | 候选卡在 220px 横向卡片内展示四层证据，信息完整但移动端扫描成本高 | 首次决策卡在 375px 需要高密度阅读：-2 至 -5 |
| -5 | 深报告明确需约 2–3 分钟；首选候选后仍需等待完整报告才获得定制映射 | 首个可行动价值超过 10 秒：-5 至 -10 |
| -4 | beta、Phase、docs 三套产品面；身份、导航、视觉与数据状态不同 | 同一任务跨站后 mental model 重置：-3 至 -6 |
| -3 | radio 组仍缺方向键/roving tabindex 的完整 WAI-ARIA 行为；全站 axe/375/390 矩阵不完整 | 核心键盘/移动门禁缺失：-3 |
| -2 | `/analyze` 是主导航项，但无上下文时只显示返回首页的空态 | 核心导航目的与页面能力不完全匹配：-2 |

### 2.3 用户价值：68 / 100

| 扣分 | 证据 | 规则 |
|---:|---|---|
| -14 | 尚无 15–20 位 ICP 的真实任务漏斗、D7 复用或 outcome cohort | 没有真实需求与留存证据：-10 至 -20 |
| -7 | 候选的 match basis 来自检索分与来源摘要，明确不是变量/因果验证 | 核心“validated transfer”仍只有候选级线索：-5 至 -8 |
| -5 | 594 expanded candidates 尚无三位真实标注者与仲裁 | 英文质量不能支撑国际用户价值：-4 至 -8 |
| -4 | Phase 的公开 walk-forward 回测为 NULL；合理价值是透明研究 demo，不是决策优势 | 子产品没有证明预测或工作流价值：-4 |
| -2 | 结果回写模型存在，但没有足够真实 verified/no-effect 案例形成可复用库 | moat 尚是数据模型，不是结果资产：-2 至 -5 |

### 2.4 端到端动线：68 / 100

| 扣分 | 证据 | 规则 |
|---:|---|---|
| -8 | Phase 与 beta 位于不同 cookie 父域；当前不能共享 session；beta 报告仍按 anonId | 注册完成却不能形成全产品身份连续性：-6 至 -10 |
| -5 | Phase AuthNav 首次 loading 态曾只显示“…”；用户实测看不到入口；主线程正在修 | 首访关键 CTA 不可发现：-5 |
| -6 | 实验面板主要在持久报告页出现，生成完成后没有强制的一页决策 brief → 创建实验路径 | 价值到行动之间需要用户自己找下一步：-4 至 -8 |
| -5 | “3/7/14 天回访”没有真实调度；当前 nudge 只在用户主动重开报告时显示 | 留存机制被动而非可触达：-4 至 -7 |
| -4 | 保存报告为显式 opt-in是正确隐私设计，但未保存则无法进入列表/实验复访；二者关系需更清楚 | 隐私选择与闭环收益解释不足：-2 至 -4 |
| -4 | 账户登录与 beta anon 报告没有 merge/claim 流程 | 注册后历史不连续：-4 |

## 3. 核心旅程逐步审计

| 步骤 | 当前行为 | 主 CTA | 状态 | 90 分要求 |
|---|---|---|---|---|
| 首访 | beta 一句话价值主张、示例、单输入框 | 输入问题 | 良好 | 只保留一个主任务；Phase 降为研究案例 |
| 提问 | 长度/键盘提交/OOS 有 guard | 生成研究报告 | 良好 | 提交前说明处理、保存和预计首值 |
| 指纹 | summary=原问题；变量、约束、未知由用户填写 | 确认结构 | 待提升 | 系统先给草案，标注推断/确认/未知 |
| 检索 | 先返回候选；不默认 Top 1 | 选择候选 | 良好 | p75 <10 秒并记录失败原因 |
| 候选 | 显示检索依据、来源、反证缺口、边界 | 查看来源 / 选择 | 边界诚实 | 用真实用户验证是否足够理解与决策 |
| 报告 | 9 节流式报告，2–3 分钟，保存显式 opt-in | 保存并生成分享链接 | 可用偏慢 | 默认一页 brief；全文作为研究附录 |
| 实验 | hypothesis/owner/deadline/baseline/metric/threshold/stop | 保存实验 | 功能完整 | 生成完成页直接创建，不要求先重开报告 |
| 回写 | result/failure_reason/learning/next_decision，owner-only | 保存结果 | 强 | 为 deadline 建真实提醒与 overdue 状态 |
| 复访 | 报告按 Today/Week/Waiting/Completed 分组 | 继续报告 | 新功能良好 | E2E 纳入 CI；支持账户 claim/跨设备 |
| 注册 | Phase magic link真实可用；beta 尚非统一账户 | 注册 / 登录 | P0 | 明确 Phase 账户，或实现真正跨域 SSO |

## 4. beta 逐页与核心 CTA

| 页面 | 主要用途 / CTA | 判定 |
|---|---|---|
| `/` | 提问 → 指纹 → 候选 → 报告 | 核心主入口；价值最清楚 |
| `/analyze` | 有上下文时生成报告；无上下文返回首页 | 可用；不宜作为独立主导航“分析” |
| `/reports` | Today/Week/Waiting/Completed 行动队列 | 高价值新功能；需进 CI |
| `/report/<id>` | owner 查看、实验、结果回写 | 核心闭环页 |
| `/report/share/<token>` | 分享只读报告 | 必须持续禁止非 owner 写 follow-up |
| `/search` | 高级候选检索 | 功能完整但与 Ask 主流重叠；放工具层 |
| `/phenomenon/<id>` | 来源案例详情 → 分析 | 是候选证据页，保留 |
| `/start-here` | 教育与启动 | 可用；CTA 应回核心输入 |
| `/learn` | 历史解释型首页 | 与 `/` 重复；降为教程，不再承诺主入口 |
| `/tools` | 9 个工具汇总 | 仅高级用户；不要抢首屏 |
| `/apply` | 方法迁移 | 保留为工具 |
| `/diagnose` | 结构诊断 | 保留为工具 |
| `/stress-test` | 压力测试/反证 | 与 validated 定位一致，保留 |
| `/lint` | 结构表达检查 | 保留为工具 |
| `/whitespace` | 研究空白 | 研究用户工具，不是 ICP 主路径 |
| `/insights` | 聚合使用/结果洞察 | 只有 owner 证据可计入；内部/研究面 |
| `/discoveries` | 精选发现 | 内容探索，不是主任务 |
| `/classes` | taxonomy 浏览 | 证据库 |
| `/taxonomy-v2` | AI review 过程 | 研究透明度页 |
| `/methods` | 方法说明 | 证据库 |
| `/papers`、`/paper/<slug>` | 论文资产 | 研究读者路径 |
| `/about` | 项目边界 | 必须保留 |
| `/privacy` | 保存、分享、邮箱与删除边界 | 必须与提交时短提示一致 |
| `/thank-you` | waitlist 成功 | 应加载统一 chrome；当前历史上曾缺 |
| `/pricing` | 已退休表面 | 应保持无公开入口/404 或明确研究状态 |
| `/connections` | 已退休社交产品 | 不得重回公开导航 |
| `/404` | 恢复导航 | 可用 |

## 5. Phase 逐页与核心 CTA

| 页面 | 主要用途 / CTA | 判定 |
|---|---|---|
| `/`、`/zh` | 597 frozen demo、NULL backtest、浏览公司 | 定位已诚实；账户入口可发现性是当前 P0 |
| `/companies` | 筛选、搜索、加载更多 | 核心 demo；0 结果应建议放宽具体条件 |
| `/company/<ticker>` | 标签、证据、原始数据、对比 | 可用；必须持续标 demo provenance |
| `/compare` | 最多 5 个 ticker 对比 | 可用；空态回 `/companies`，不是 `/` |
| `/universality`、`/<class>` | 类别与公司映射 | 研究解释页，不作为预测 |
| `/methodology` | pipeline、来源、限制 | 核心信任页 |
| `/backtest` | NULL 结果 | Phase 最有价值的可信资产 |
| `/search` | Cmd+K 搜索落地 | 可用 |
| `/onboarding` | 教学 tour | 文案必须保持 frozen demo，不承诺周更 |
| `/newsletter`、`/001` | 研究更新档案 | 不得伪造“本周新翻转” |
| `/thank-you` | 更新名单成功 | 不承诺固定下次发刊时间 |
| `/pricing` | 无可购买 offer 的状态页 | 可直达但不进主导航 |
| `/checkout/mock` | legacy 308 | 必须保持 redirect |
| `/auth/login` | magic link 注册/登录 | Phase 账户唯一真实入口 |
| `/auth/verify` | token 兑换 | token 先从 URL 清除；重放拒绝 |
| `/me` | 邮箱、tier、退出 | 可用；登出失败不能假成功 |
| `/me/favorites` | 当前仍以本地收藏为主 | 不承诺登录后自动云同步 |
| `/privacy` | 账户/token/SMTP/cookie | 已补披露 |
| `/about` | demo 与域名关系 | 可用 |
| `/offline` | PWA 离线恢复 | 重试按钮可用 |
| 404/global error | 返回/重试 | 已有恢复入口 |

## 6. P0 / P1 / P2

### P0：达到“可公开可信使用”

| 工作 | 自动实现 | 需外部输入 |
|---|---|---|
| 修复 beta `/auth/login` 404；明确“Phase 账户”而非假统一账号 | 是 | 否 |
| Phase 首帧、桌面、移动、footer 都有可见账户入口 | 是 | 否 |
| auth enabled/disabled 与 beta 跨站入口进入 fail-closed browser CI | 是 | 否 |
| 报告分组 E2E 纳入 browser-product-contract，而非只存在测试文件 | 是 | 否 |
| 保护 owner-only follow-up 与默认不保存隐私边界 | 已实现，持续门禁 | 否 |
| 英文 expanded judgments / holdout | 工具已实现 | **需要三位真实标注者** |

### P1：达到“可验证 PMF”

| 工作 | 自动实现 | 需外部输入 |
|---|---|---|
| 系统生成指纹草案，逐项标推断/用户确认/未知 | 是 | 5 个可用性测试校正文案 |
| 报告完成页直接创建 7 天实验；一页 decision brief 默认展开 | 是 | 真实任务验证字段是否够用 |
| deadline/overdue、本地提醒和工作台计数 | 是 | 邮件提醒需用户选择与送达策略 |
| radio 方向键、axe、375/390、焦点返回矩阵 | 是 | 真机抽查有帮助 |
| 首值 p75 <10 秒与失败原因 dashboard | 大部分可自动 | 真实流量分布 |
| 15–20 个 PM 真实任务 cohort | 否 | **必须真实用户** |

### P2：达到“可规模留存”

- 跨域 SSO code exchange，或把产品迁到共同父域；不能依赖 Domain cookie。
- 登录后 claim/merge beta anon reports，不丢历史。
- Today/Waiting/Completed 工作台支持 Linear/Notion/飞书导出。
- verified/no-effect 案例在用户明确授权匿名化后形成可检索资产。
- 仅在 5 个团队连续 4 周、50+ outcomes、D7 达标后恢复付费与团队路线。

## 7. 90 分验收线

### 产品指标

- 指纹确认后候选首值 p75 < 10 秒。
- 候选人工接受率 ≥ 60%。
- 深报告启动率 ≥ 45%，完整率 ≥ 95%。
- 实验创建率 ≥ 35%，7 日启动率 ≥ 20%。
- 14 日结果回写率 ≥ 15%，D7 复用率 ≥ 25%。
- 敏感信息意外分享为 0。

### 质量门禁

- 所有公开 CTA 真实点击 E2E，无本域 404、假成功或无效按钮。
- 核心旅程 fail closed：首访 → 提问 → 指纹 → 候选 → 报告 → 实验 → 回写 → 复访。
- 注册旅程 fail closed：入口 → 邮件 → verify → me → logout/replay；enabled/disabled 都测。
- 每个“verified”均绑定 owner、证据版本、反证、实验与 outcome。
- 英文模型只有在 expanded human holdout 提升且中文/OOS/延迟不退化后上线。

达到以上指标后，功能预计 93、体验 91、价值 90、动线 92，综合约 **91.5**。在真实用户数据产生前，任何“产品已经 90 分”的说法都不诚实。
