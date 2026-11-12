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

## 8. 注册用户能力与研究资产完整性审计

### 8.1 结论

当前邮箱注册、magic link 验证、session、`/me` 与退出均为真实能力，新增用户通知也已接入；但账户目前仍是一个**身份外壳**，尚未成为用户资产的所有权主体。收藏仍以浏览器 localStorage 或旧 `X-API-Key` 身份运行，beta 报告及 follow-up 仍绑定 `X-Anon-Id`。用户注册后换设备，不会自动看到原收藏或报告。

因此，产品可以诚实地说“可用邮箱登录 Phase”，不能说“登录后收藏与报告跨设备同步”。在账户所有权、隐私导出/删除完成前，不应把注册作为 beta 主旅程的强制步骤。

### 8.2 功能 inventory

| 能力 | 当前实现 | 是否真正绑定邮箱账户 | 判定 |
|---|---|---:|---|
| 邮箱注册/登录 | Phase magic link；同一入口兼容新老用户 | 是 | 可用 |
| 登录持久化 | HttpOnly `phase_session`；`/api/auth/me` 校验 | 是 | 可用 |
| 退出 | 服务端注销，失败时 UI 不假成功 | 是 | 可用 |
| 新用户通知管理员 | 注册成功后进入通知发送链 | 是 | 可用，持续监控失败队列 |
| 账户资料 | `/me` 展示 email、tier、创建时间 | 是 | 信息价值有限 |
| Phase 收藏 | localStorage；旧服务端路径以 `X-API-Key.owner_email` 标识 | **否** | magic-link 用户无法获得云同步 |
| 收藏跨设备 | 页面明确提示仅本设备 | 否 | 诚实但未形成账户价值 |
| beta 报告 | `creator_anon_id` / `X-Anon-Id` | 否 | 清缓存或换设备即失联 |
| 报告 follow-up | owner-only，但 owner 是 anon id | 否 | 安全边界已有，账户归属缺失 |
| 报告分享 | share link | 不适用 | 可用；分享 token 不得用于 claim 所有权 |
| 报告简报 | 分析页“复制为简报”生成 Markdown | 否 | 有即时价值，但不是持久研究资产 |
| 用户数据导出 | legacy email + mock code DSAR | 部分 | 不含 auth、token/session、收藏、报告、通知记录 |
| 用户数据删除 | legacy email + mock code，邮件确认仍为 log | 部分 | 不等于删除账户；同样漏删新账户资产 |
| 账户自助删除 | `/me` 无入口 | 否 | P0 合规/信任缺口 |
| 报告转研究草稿/论文 | 无 | 否 | 需先建立证据安全的 research-note 层 |

### 8.3 四条端到端旅程

#### A. 匿名收藏 → 注册 → 换设备

当前：本地收藏 → 登录 Phase → 收藏仍在原浏览器 → 新设备为空。

目标：登录后明确询问或自动合并本地收藏 → 服务端以 `user_id` 持久化 → 新设备恢复；合并应按稳定对象 ID 去重，并保留本地回滚副本直到服务端确认成功。

#### B. 匿名报告 → 注册 → 换设备

当前：beta 使用 anon id 创建报告 → Phase 登录不改变报告归属 → 新设备无法进入“我的报告”。

目标：通过一次性跨域 SSO code exchange 在 beta 建立短期账户 session；用户在持有原 anon cookie/localStorage 的浏览器内主动 claim。服务端事务性写入 `owner_user_id`，保留 `creator_anon_id` 仅作迁移审计。公开 share token 绝不能作为所有权证明。

#### C. 导出数据 / 删除账户

当前 DSAR 实现仍按“没有账户”的旧假设工作，验证方式为部署配置的 mock code，删除确认邮件也仍是日志。导出/删除集合覆盖 newsletter、mock checkout、error log、fingerprints 与 connections P3，但没有覆盖 auth 用户、magic token/session、收藏、报告/follow-up 和注册通知状态。

目标：`/me` 提供“导出我的数据”和“删除账户”；登录 session + 邮箱二次确认完成高风险验证。导出清单与删除清单由同一个数据资产 registry 生成，CI 强制二者对称。删除须撤销全部 session/token，并明确保留最小合规 tombstone 的字段和期限。

#### D. 报告 → 决策简报 → 研究草稿/论文

首要用户是研究密集型 PM/growth，立即需要的是可带进团队评审的 decision brief，而不是看似学术但证据不足的“自动论文”。现有“复制为简报”是正确起点，但缺少下载、版本、来源与复现信息。

建议两级输出：

1. P1 `Decision Brief (.md)`：问题、结构指纹、候选类比、共享机制、边界/反证、7 天实验、结果、来源链接、artifact/model/prompt 版本。
2. P2 `Research Note`：在 brief 上增加 claim-evidence 表、方法、假设、负结果、局限与可复现清单；只有 outcome 已验证且引用完整时才允许生成 paper outline。检索分数或 LLM 判断不得被包装为论文结论。

### 8.4 推荐数据模型与接口边界

- 所有账户资产统一使用不可变 `user_id`；规范化 email 只用于登录和通知，不作为跨表主键。
- favorites 迁入与 auth 同一事务数据库，或至少由统一 repository 管理；magic-link session 必须成为唯一用户鉴权入口，逐步废弃浏览器可写的 `phase_api_key` 身份。
- reports 增加 nullable `owner_user_id`、`claimed_at`、`claim_source_anon_id`；旧报告继续可读，登录后仅合并当前浏览器能证明拥有的 anon 报告。
- beta 与 Phase 位于不同 host，不能假设现有 cookie 自动共享；采用短时、单次、绑定 audience/state/nonce 的 code exchange，避免把长 session 放进 URL。
- `/api/me/favorites`、`/api/me/reports`、`/api/me/export`、`/api/me/delete` 均从同一 session dependency 取得 `user_id`，不要由客户端提交 email 决定所有权。
- 建立数据资产 registry：每新增一类用户数据，必须同时声明 owner key、导出器、删除器、保留期限和审计策略；测试校验 export/delete 对称。

### 8.5 优先级与自动驾驶边界

#### P0：公开推广注册前完成

- 保持所有页面对同步能力的诚实披露，不出现“登录即可跨设备同步”的暗示。
- 修复 DSAR 旧假设：至少锁定未接真实验证码的公开入口，并将当前账户资产缺口列入上线门禁。
- 为账户、收藏、报告、notification、token/session 建立统一数据资产清单与 export/delete 对称测试。
- `/me` 明示当前账户实际保存什么、不保存什么，并提供隐私请求入口。

#### P1：让注册产生核心产品价值

- magic-link session 接管收藏服务端鉴权；完成 local → cloud 的幂等 merge。
- 完成 beta/Phase 一次性 SSO exchange、anon report claim、跨设备“我的报告”。
- 提供登录态数据导出与账户删除；删除后验证 session 失效、资产不可恢复访问。
- 保存报告页提供 `.md` decision brief 下载，携带来源、版本、边界与实验结果。
- 关键 E2E：匿名产出资产 → 注册 → merge/claim → 新设备登录 → 资产可见 → 导出 → 删除 → 重放 session 失败。

#### P2：研究资产与团队协作

- Research Note、BibTeX/引用清单、evidence manifest、复现包。
- 在证据与 outcome 门禁通过后生成 paper outline；不得默认生成“可发表论文”。
- 版本 diff、团队权限、Notion/飞书/Linear 导出与审阅工作流。

### 8.6 需要真实用户而非代码替代的问题

- 先访谈/观察 5–8 位研究密集型 PM：跨设备收藏、跨设备报告、decision brief 三者的真实优先级。
- 另访谈 5 位学术研究者：他们需要的是灵感检索、research note、literature map，还是论文草稿；不要用 PM 的需求替代学术需求。
- 对两个 ICP 分开评估留存：PM 看实验启动与结果回写，研究者看证据保存、引用复用与研究问题演化。
- 付费前必须确认用户愿意为“可复用、可追溯的研究资产”付费，而不是只为一次类比的新奇感付费。

这一账户闭环完成后，注册才从运营指标变成真实产品能力；否则新增注册通知只说明有人进入过入口，不能证明用户获得了持续价值。

## 9. 产品功能 × 数据 / 实验 / 模型证据矩阵

### 9.1 证据等级

- **E0 — 仅实现**：按钮或接口存在，没有可重复的质量证据。
- **E1 — 合成验证**：单元、契约、边界或合成 fixture 通过。
- **E2 — 冻结离线评测**：数据、模型、代码与指标可追溯，但可能复用旧池或存在分布偏差。
- **E3 — 独立人工 / holdout**：盲审、多标注者一致性、未参与调参的 holdout 及回归门禁通过。
- **E4 — 真实使用结果**：目标 ICP 在真实任务中重复使用，行为与 outcome 指标达到预注册门槛。

公开用户承诺必须服从最低证据等级：E1 只能承诺“功能可运行”，E2 可承诺“在冻结样本上的表现”，E3 才能承诺“离线质量改善”，E4 才能承诺“帮助用户取得结果”。

### 9.2 逐功能完备性

| 功能 | 依赖的数据 / 实验 / 模型 | 当前证据 | 当前可承诺 | 失效时用户体验 | 要补的数据与重跑门禁 | 优先级 | 对 90 分预计提升 |
|---|---|---|---|---|---|---:|---:|
| 中英文结构搜索 | 4,443 KB、embedding、query rewrite/rerank、OOS 与 graded judgments | 中文/整体 **E2**：100 query、400 judgments，nDCG@5 0.5786；英文仅旧池 **E2-**，扩展池 **E0** | 中文/整体可称“冻结评测可用”；英文只能披露实验中 | 英文输入返回表面相似或错机制候选，用户在首步失去信任 | 594 expanded candidates × 3 独立盲审；仲裁清零、QWK≥0.67；独立 holdout；中文/OOS/延迟不退化；真实 endpoint 并发通过才切流 | P0 | +3.0 |
| 候选匹配证据 | KB source、共享机制、变量映射、反证、适用边界、来源 provenance | 检索排序 **E2**；逐候选“为何匹配”主要为 LLM/KB 生成，整体约 **E1** | 可称“候选与解释”，不能称“已证实同构” | 分数看似精确但用户无法判断是机制一致还是关键词相似；误迁移风险高 | 候选卡固定展示 source、mechanism、mapping、counterevidence、boundary；抽取 100 对专家盲审；calibration/ECE、严重误配率、引用可达率设 fail-closed 门禁 | P0 | +2.5 |
| 深度报告 | 检索候选、LLM、report schema、引用、artifact/model/prompt 版本 | schema/stream/failure tests 约 **E1**；无独立内容质量 holdout | 可称“结构化分析草稿”，不可称“可靠决策结论” | 等待后得到空泛内容、来源断裂或把检索分数当因果证据 | 50 个冻结任务 × PM/领域专家 rubric；事实/引用/边界完整率；无来源 claim 比例；p75 首值<10s、完成率≥95%；模型升级全量回归 | P0/P1 | +2.0 |
| 实验计划 | 报告建议、hypothesis、metric、baseline、threshold、owner、deadline、stop condition | 字段与 guardrail **E1**，真实可执行性 **E0** | 可称“生成/记录最小实验计划” | 计划听起来专业但不可执行、指标不可测、没有停止条件 | 30 个真实 PM 任务；独立评审可执行率≥80%、指标可测率≥90%；用户编辑率与 7 日启动率；缺 hypothesis/metric/threshold 时禁止标 ready | P1 | +1.5 |
| 结果回写与“已验证” | owner-only follow-up、experiment/outcome schema、真实 outcome、反事实与时间窗 | 权限/字段 **E1**；真实结果 **E0/E1** | 只能称“用户自报结果”；不能直接称科学验证 | 自报 worked 被全站包装为“已验证”，制造虚假社会证明 | 将 `user_reported`、`replicated`、`independently_verified` 分级；记录样本、指标、时间窗、actual、失败原因；至少 50 outcomes 后校准；公开案例需授权和复核 | P0 | +1.5 |
| 收藏与账户 | magic-link auth、user_id、favorite/report ownership、merge/claim、跨域 SSO | auth **E2/E3**（真实邮件验收）；资产同步 **E0** | 只承诺 Phase 邮箱登录与本地收藏 | 用户注册后换设备仍为空，感觉注册无意义 | local→cloud 幂等合并；anon report claim；双设备 E2E；冲突、重复、断网、重放、删除门禁；真实用户恢复成功率≥99% | P1 | +1.5 |
| Phase Detector | frozen 597 ticker snapshot、EWS pipeline、500 ticker × 5 年 walk-forward、provenance、NULL result | **E2/E3-**：冻结数据、公开 NULL backtest p=0.681、来源标记；非实时、非预测产品 | 可承诺“研究 demo 快照与透明 NULL 结果” | 用户把 demo price/signal 当实时交易建议；或因 NULL 结果误以为产品无价值 | 每 release 校验 snapshot hash、ticker count、price provenance、NULL 数值与页面一致；禁用 prediction/weekly/live 文案；若转实时需独立 prospective preregistration | P0 持续 | +0.8 |
| Decision Brief 导出 | 报告、来源、实验/outcome、版本 manifest | 复制 Markdown **E1**；持久下载/复现 **E0** | 可称“复制简报草稿” | 复制后丢来源、版本和边界，团队无法审阅或复现 | golden-file/schema 测试；所有 claim 有 source 或明确 `unsupported`；下载 `.md` 与页面一致；版本 hash 可回溯 | P1 | +1.0 |
| Research Note / 研究草稿 | evidence manifest、claim-evidence table、citation metadata、负结果、方法与局限 | **E0** | 暂无承诺 | 生成“像论文”的文本却没有证据与引用，伤害学术可信度 | 先建 Research Note；20 个研究任务由 2 位领域研究者评审；引用精确率/可达率、claim coverage、复现清单；outcome 未验证时禁止 paper-ready 标记 | P2 | +1.0 |
| 隐私导出 / 删除 | 数据资产 registry、auth/session、favorites、reports、notifications、retention | legacy 范围 **E1**；当前账户完整性 **E0** | 只能承诺现有列明数据的有限处理，不能称“全部账户数据” | 用户删除后仍有 token、报告或收藏；严重信任与合规故障 | export/delete 从同一 registry 生成；全资产 seed 后导出完整、删除归零、session 重放失败；保留 tombstone 字段/期限固定并测试 | P0 | +1.2 |

以上增益是对当前约 74 分基线的**上限估计**，合计约 +16 分；它们存在相关性，不能简单用完成按钮数相加。P0 证据诚信与 P1 账户/实验闭环全部通过后，才有资格接近 90；P2 研究草稿不是达到 90 的前置条件。

### 9.3 推荐的 release gate 顺序

1. **数据完整性 gate**：KB/snapshot/report schema hash、行数、唯一键、source 可达性、provenance 无漂移。
2. **离线质量 gate**：中文、英文、OOS 分开报告；英文 594 三人盲审完成前候选模型不得上线。
3. **内容安全 gate**：候选和报告逐 claim 检查来源、边界、反证；unsupported 内容不得显示为 verified。
4. **性能与失败 gate**：首值、完整耗时、并发、超时、降级、重试；失败必须显示可恢复状态，不能空白或假成功。
5. **闭环 gate**：报告 → 实验 → outcome → 工作台 → 导出在 owner 权限下全链路通过。
6. **账户资产 gate**：匿名 → 注册 → merge/claim → 新设备 → 导出 → 删除 → session 重放失败。
7. **真实价值 gate**：15–20 个 PM 真实任务、至少 50 个 outcome；达到预注册启动率、回写率、D7 复用率后再提升价值承诺。

### 9.4 模型或数据更新的 fail-closed 规则

- 任一 KB、embedding、reranker、prompt 或 report schema 更新，必须产生新 artifact id，并重跑它影响的完整门禁，不得沿用旧绿灯。
- 总平均提升不能掩盖英文、中文、OOS 或长尾领域退化；任一关键 slice 超过预设回归容忍即拒绝发布。
- 离线指标提升但真实 endpoint p75/p95、错误率或成本越界时拒绝发布。
- 人类标签不得由待评模型生成或补齐；reviewer 身份、任务版本、仲裁与一致性均应可审计。
- Phase 的 NULL 结果是产品可信资产，不应因营销需要隐藏；任何新预测主张必须走新的 prospective preregistration，而不是重解释旧 backtest。
- “已验证”是证据状态，不是 UI 徽章：只有满足对应等级的数据记录才能升级，降级与撤回同样要可追溯。
