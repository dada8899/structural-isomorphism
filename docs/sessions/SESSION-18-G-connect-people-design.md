***REMOVED*** G — 按「问题结构」连接人 · 设计方案

> Session ***REMOVED***18 产出。**这是方案文档，不是本 session 的实现项。**
> G 是一次产品定位级的转向（工具 → 网络），需独立立项。本文写清
> 愿景、前置条件、架构方案、分阶段路径、风险，作为立项依据。

---

***REMOVED******REMOVED*** 1. 愿景

引擎现在已经在回答一个判断：**两个问题结构同不同构**。

如果 A 在研究「30 人公司的效率塌陷」，B 在研究「生态系统的灭绝债务」，
引擎知道它们共享同一个**延迟—债务结构**——那么 A 和 B 其实在解同一道
数学题，只是穿着不同领域的外衣。

把他们连起来，就得到一种**新的人际连接维度**：

| 连接维度 | 代表产品 | 连接依据 |
|---|---|---|
| 职位 / 履历 | LinkedIn | 你是谁 |
| 兴趣 / 话题 | Twitter / 即刻 | 你关注什么 |
| **问题结构** | **本方案** | **你正在解的结构性问题** |

前两种连人，跨领域的人永远不会相遇——做组织管理的不会刷到做生态学的。
但他们可能正卡在同一个结构难题上，彼此手里有对方缺的那一半解法。
G 让「结构同构」这件已经被引擎算出来的事，变成一条真实的人际连接。

---

***REMOVED******REMOVED*** 2. 前置条件清单（立项必须先解决）

G 不能在当前架构上直接长出来。以下每一条都是硬前置：

***REMOVED******REMOVED******REMOVED*** 2.1 用户身份体系 🔴 最大前置
- **现状**：只有匿名 `anonId`（设备级，存 cookie / localStorage）。换设备、清缓存即失联，无法联系，无法承载档案。
- **需要**：稳定账号（注册 / 登录）、email 验证、可联系渠道、个人档案。
- **迁移**：登录后把历史 `anonId` 的报告归并到 user（已有 `reports.creator_anon_id`，可做一次性 claim）。
- 这本身就是一个独立的中型工程，是 G 的 Phase 0。

***REMOVED******REMOVED******REMOVED*** 2.2 问题结构指纹（structural fingerprint）
- 把一个用户「在解的问题」归约成一个稳定、可比较的结构表示。
- **现成可用的料**：analyze 报告的 `shared_structure` 段、`b_id`、
  `_credibility.source_type_id`、KB 的 `type_id`、v4 的 26 个普适类。
- **需要新建**：一个 fingerprint 表示（建议 = `shared_structure` 文本的
  embedding + `type_id` + 普适类标签 三元组）+ 一个稳定的相似度度量。

***REMOVED******REMOVED******REMOVED*** 2.3 匹配引擎
- 给定一个用户的 fingerprint，找出**结构同构但领域不同**的其他用户。
- 领域相同的匹配没有跨域价值——必须显式拉开 domain distance。
- **冷启动**：用户基数小时无人可匹配（见 §5 缓解）。

***REMOVED******REMOVED******REMOVED*** 2.4 隐私与同意机制 🔴 产品成败所在
- 默认不暴露任何人的任何信息。连接必须**显式 opt-in**、**双向同意**。
- 已有 `/api/privacy/*`（导出 / 删除）需延伸到新数据。
- 一次隐私事故 = 信任崩，对一个「验证型」产品是致命的。

***REMOVED******REMOVED******REMOVED*** 2.5 社区 / 通知形态
- 连接建立后在哪交流？需要选定形态：站内信 / 引荐邮件 / 每周 digest。
- 需要 moderation（反 spam、反招聘推销滥用）。

---

***REMOVED******REMOVED*** 3. 架构方案

***REMOVED******REMOVED******REMOVED*** 3.1 数据模型（新增表）

```
users
  id, email, email_verified, display_name, created_at, status

user_profiles
  user_id (FK), bio, domains[], what_im_working_on,
  what_i_can_offer, default_visibility

structural_fingerprints           -- 一个用户可有多个（解多个问题）
  id, user_id (FK),
  source_report_id (FK reports.id),-- 指纹来自哪份 analyze 报告
  type_id, universality_class,     -- 结构标签
  embedding (BLOB),                -- shared_structure 文本向量
  problem_summary,                 -- 一句话问题摘要（用户可编辑）
  visibility_level,                -- L0 / L1 / L2，见 §3.3
  created_at, updated_at

structural_matches
  id, fingerprint_a, fingerprint_b,
  structural_similarity, domain_distance, combined_score,
  status,                          -- suggested / a_interested /
                                   -- b_interested / mutual / declined
  created_at, updated_at

introductions / messages           -- match 达成后的交流载体
  id, match_id, from_user, body, created_at
```

`anonId → user` 的升级：登录时若带历史 anonId，把该 anonId 名下的
reports 关联到 user，并允许用户把其中任意报告「升级成可连接的指纹」。

***REMOVED******REMOVED******REMOVED*** 3.2 匹配算法

```
fingerprint(report)
  = embedding(report.shared_structure 文本)
  ⊕ type_id
  ⊕ universality_class

candidates(fp) = 其他用户的 fingerprints 中满足：
  structural_similarity(fp, other) >= 阈值      -- 复用 search_service._cosine
  AND domain_distance(fp, other) >= 阈值        -- 领域必须不同
  AND other.visibility_level >= L1
  AND other.user_id != fp.user_id

rank = structural_similarity × domain_distance × 双方活跃度因子
```

复用现有资产：`search_service._cosine()`（已正确处理未归一化向量）、
普适类映射、KB 的 `type_id` 体系。匹配引擎是这些已有能力的组合，
**算法不是难点——身份体系和隐私才是**。

***REMOVED******REMOVED******REMOVED*** 3.3 隐私机制（核心设计）

三级可见性，默认最严：

| 级别 | 含义 | 别人能看到 |
|---|---|---|
| **L0** 私密（默认） | 指纹只用于自己 | 什么都看不到 |
| **L1** 结构可发现 | 参与匿名计数 | 「有 N 人在解结构相同的问题」——纯数字，**不暴露身份** |
| **L2** 可引荐 | 允许进入 match 流程 | 经双向同意后才交换身份 |

**双向同意的 match 流程**（类似交友 app 的 mutual match）：

```
系统建议 match
  → A 在匿名状态下表示「有兴趣」
  → B 收到「有人对你的这个问题结构感兴趣」（A 仍匿名）
  → B 也表示「有兴趣」
  → 双向 match 达成 → 此时才解锁双方档案 / 联系方式
```

任何时候可撤回 opt-in；fingerprint 可单独删除；纳入 `/api/privacy/*`
的导出与删除范围。

***REMOVED******REMOVED******REMOVED*** 3.4 交互形态

- **报告页**：底部一个克制的 opt-in 开关——「让在解结构相同问题的人能发现这个问题」。
- **`/connections` 页**：我的可连接问题 / 收到的 match 建议 / 已连接的人。
- **每周 digest 邮件**：「本周有 3 个结构邻居」——即使没达成 match，
  这个数字本身也提供「我不孤独，有人在解同一道题」的价值。

---

***REMOVED******REMOVED*** 4. 分阶段落地路径

每个阶段独立可上线、独立有价值，**不必一次做完**：

| 阶段 | 内容 | 价值 | 隐私风险 |
|---|---|---|---|
| **P0** | 账号体系（注册 / 登录 / 验证 / anonId 归并） | G 的地基；也惠及"我的报告"等现有功能 | 无 |
| **P1** | 结构指纹抽取与存储（被动，全 L0，不暴露） | 为后续铺数据 | 无 |
| **P2** | 匹配引擎 + L1 可发现（只展示「N 人结构相同」数字） | **用户少时也不尴尬**，已能提供"不孤独"价值 | 极低（纯计数） |
| **P3** | L2 + 双向同意 match + 引荐 | 真正的人际连接 | 高——需最严设计 |
| **P4** | 社区 / digest / moderation | 网络效应 | 中 |

建议立项时把 **P0+P1+P2 作为第一个里程碑**——它不触碰任何身份暴露，
风险可控，且 P2 的「N 人结构相同」是一个零隐私成本就能验证需求的切片。
P3 是真正的产品赌注，应在 P2 验证需求后再投入。

---

***REMOVED******REMOVED*** 5. 风险与开放问题

- **冷启动**：用户基数小时无人可匹配。缓解：P2 的「N 人结构相同」纯数字
  在小基数下也不尴尬；可先用历史报告（已脱敏）做"结构邻居"展示。
- **隐私是产品成败**：一次泄露即信任崩。L0 默认 + 双向同意 + 可撤回 + 可删除
  必须是地基，不能是后补。
- **滥用**：实名 + 结构门槛天然过滤掉一部分 spam；仍需 moderation 和举报。
- **产品定位转向**：G 把产品从「无状态工具」变成「有网络效应的平台」——
  商业模式、运营、社区治理都是全新命题，不是一次功能迭代。

---

***REMOVED******REMOVED*** 6. 为什么必须独立立项

账号体系、结构指纹、匹配引擎、隐私同意、社区形态——**每一块都是独立的
中大型模块**，合起来还把产品的形态从工具升级成网络。这是产品定位级的
决策，涉及商业模式与运营的重新设计，不应塞进一个实施 session。

**建议**：以本文为输入，单独走一遍 Phase 0（方向论证）→ Phase 1（PRD），
把 P0+P1+P2 作为首个里程碑独立立项。
