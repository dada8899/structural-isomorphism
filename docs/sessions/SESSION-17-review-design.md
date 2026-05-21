***REMOVED*** SESSION-17 发布前视觉设计审查

> 审查日期：2026-05-21
> 审查范围：web/frontend/ 全站 11 页 × 桌面 1280 / 移动 390 两视口
> 审查方式：Playwright + Chromium 截图（本地 http.server 渲染；线上 beta 仅部署了 home/analyze/report）
> 审查人：资深视觉设计师（只审不改）
> 设计基准：Apple / 微信 / Bear / 飞书 / Notion / 小红书 —— 克制、留白、字体精致、信息层级清晰、白底为主、对标 iOS HIG

---

***REMOVED******REMOVED*** 总评

**视觉设计基础是扎实的**：design-system.css / shared-tokens.css 有单一权威 token 源、8px 网格、三档 hero 字号 clamp、衬线+无衬线混排有设计主张（不是 AI 通用感）。首页、about、learn 的排版克制、留白舒服，达到了对标产品的水准。

**但当前状态「不够格直接对外发布」**，卡点不在「美不美」，而在**一致性与完成度**：

1. 全站导航在不同页面长得不一样（reports 页少 4 个链接、report 页换成另一种 nav）。
2. **移动端 ≤480px 完全没有站点导航**——所有 nav link 被 `display:none`，又没有汉堡菜单兜底，手机用户只能看 logo + EN，去不了任何其他页。
3. 多个页面在「无数据 / 接口失败」时把原始报错暴露给用户（discoveries 直接显示 `Unexpected token '<'`），或残留无意义控件（reports 空状态还显示「加载更多」按钮）。
4. report 错误页没有页头页脚，是个「半截页面」。

这些是「成熟产品 vs 半成品」的分界线问题，不是 polish。**修完 P0 + P1 即可发布**，P2 可发布后迭代。

**计数：P0 = 5 ｜ P1 = 9 ｜ P2 = 8**

---

***REMOVED******REMOVED*** P0 — 阻断发布，必须修

***REMOVED******REMOVED******REMOVED*** P0-1 移动端无站点导航（全站，≤480px）
- **位置**：所有页面，视口 ≤480px。
- **现象**：`assets/css/responsive.css:405` 把 `.site-header__nav .site-header__nav-link { display:none }`，移动端整条导航消失，且没有汉堡菜单替代。手机上唯一的浮动 `☰` 按钮（`history-sidebar__trigger`）打开的是「最近查询」侧栏，不是站点导航。
- **影响**：手机用户进入任意页后无法跳到 共享模式 / 精选发现 / 论文 / 方法 / 关于 等任何页，移动端等于「单页死路」。这是 iOS HIG 明确反对的——核心导航必须始终可达。
- **改法**：加一个标准移动汉堡菜单。`.site-header` 右侧放 44×44px 的菜单按钮（iOS 最小可点区域），点击展开全屏或抽屉式 nav，复用桌面那 8 个链接。抽屉背景 `--brand-paper-card ***REMOVED***FFF`，链接 `font-size:18px`、行高 56px、`--brand-line` 分隔线。不要保留「nav 直接消失」这个方案。

***REMOVED******REMOVED******REMOVED*** P0-2 导航条跨页不一致
- **位置**：站点页头 `.site-header__nav`。
- **现象**：
  - `index.html` / `about.html`：8 个链接（从这里开始 / 共享模式 / 精选发现 / 论文 / 方法 / Phase Detector / 我的收藏 / 关于）+ EN。
  - `reports.html`：只有 5 个（共享模式 / 精选发现 / 论文 / 我的报告 / 关于）——少了「从这里开始 / 方法 / Phase Detector / 我的收藏」，还多了「我的报告」。
  - `report.html`：完全换成 `analyze-crumb` 面包屑导航，不是 `site-header__nav`。
- **影响**：同一产品不同页导航不同，用户每跳一页都要重新建立空间感，廉价、不专业。
- **改法**：抽一份**唯一权威的 header 片段**（含完整 8 链接 + 当前页高亮 `aria-current="page"`），所有页面统一引用。「我的报告」「我的收藏」二选一术语统一（见 P1-9）。report.html 也用标准 header，面包屑可作为 header 下方的二级导航，而不是替换 header。

***REMOVED******REMOVED******REMOVED*** P0-3 report 错误页缺页头页脚
- **位置**：`report.html` 错误态。
- **现象**：`report.html` 只有 1 处 footer 标记（其他页 8~16 处），错误态截图里整页只有一个面包屑 + 一张报错卡片，无标准 `site-header`、无 `site-footer`，上下大片空白。
- **影响**：看起来像「崩了的页面」而不是「产品的一个状态」，直接劝退。
- **改法**：report.html 套用标准 `site-header` + `site-footer`。错误卡片收进正常内容区，宽度对齐其他页的内容容器（max-width ~720–960px、居中）。

***REMOVED******REMOVED******REMOVED*** P0-4 接口失败把原始报错暴露给用户
- **位置**：`discoveries.html`（桌面+移动均复现）。
- **现象**：页面底部红字 `加载失败：Unexpected token '<', "<!DOCTYPE "... is not valid JSON`——这是 fetch 拿到 HTML 当 JSON 解析的原始 JS 异常，直接显示给终端用户。
- **影响**：暴露技术栈细节，极不专业，用户完全看不懂。
- **改法**：所有数据加载失败统一走「友好空状态」组件：一句人话（如「内容暂时加载不出来，请稍后重试」）+ 一个「重试」按钮，文字色 `--text-secondary`，不要红色原始 error。原始 error 只进 console。同类排查 learn.html 的空白卡片（见 P1-1）。

***REMOVED******REMOVED******REMOVED*** P0-5 reports 空状态残留「加载更多」按钮
- **位置**：`reports.html`，空状态。
- **现象**：「还没有保存的报告」空状态下，下方仍渲染了一个「加载更多」按钮——没有任何内容可加载。
- **影响**：明显的逻辑/视觉 bug，点了什么也不会发生，破坏「成熟产品」的信任感。
- **改法**：空状态时隐藏「加载更多」。该按钮只在「已有报告且还有下一页」时出现。

---

***REMOVED******REMOVED*** P1 — 影响精致度与一致性，发布前应修

***REMOVED******REMOVED******REMOVED*** P1-1 learn 页多处空白卡片
- **位置**：`learn.html`「你输入一个问题之后会发生什么」「每天从知识库揭示 3 组跨领域同构」两个区块。
- **现象**：卡片骨架渲染出来了，但卡片内容是空白（疑似异步内容未填充或 skeleton 卡死）。
- **改法**：排查内容渲染逻辑；若依赖接口，给静态兜底文案或正确的空状态，不要把空骨架留在页面上。

***REMOVED******REMOVED******REMOVED*** P1-2 「我的收藏」徽标在导航里裸露「0」
- **位置**：全站 header，`site-header__fav-badge`。
- **现象**：about.html nav 文本抓取出现孤立的「0」。收藏数为 0 时徽标应 `hidden`（HTML 里有 `hidden` 属性，但渲染出来仍可见）。
- **改法**：确认数量为 0 时徽标真正不显示；非 0 时再出现。

***REMOVED******REMOVED******REMOVED*** P1-3 报错卡片用蓝色聚焦边框
- **位置**：`report.html` 错误卡片。
- **现象**：「报告不可用」卡片用了亮蓝色 (`--brand-accent ***REMOVED***2563EB`) 的粗边框 + 蓝色外发光，视觉上像「被选中的输入框」，与「错误」语义冲突。
- **改法**：错误卡片用中性边框 `--brand-line ***REMOVED***E4E4E7` 1px，无外发光；或用 `--danger-border ***REMOVED***FECACA` + `--danger-surface ***REMOVED***FEF2F2` 的克制错误样式。不要用 accent 蓝。

***REMOVED******REMOVED******REMOVED*** P1-4 classes 页信息密度过高、缺留白节奏
- **位置**：`classes.html` 卡片网格。
- **现象**：23 张等价类卡片密排，卡片内字号多档跳动（标题/英文副标/标签/数值/链接挤在一张小卡里），整页像数据表而非产品页。移动端尤其拥挤。
- **改法**：卡片间距 `gap` 提到 `--space-5`（20–24px）；卡片内最多 3 档字号（标题 15–16px / 正文 13–14px / 标签 11–12px）；英文副标题统一降到 `--text-tertiary` 12px；卡片 padding 至少 16–20px。考虑首屏只显示 8–12 张 + 「展开全部」。

***REMOVED******REMOVED******REMOVED*** P1-5 移动端页脚链接换行错乱
- **位置**：home / 多页 footer，移动 390。
- **现象**：footer 链接（关于 / 从这里开始 / 论文 / GitHub / HuggingFace…）在窄屏挤成多行且每个词被拆字换行（「从/这/里/开/始」竖排）。
- **改法**：移动端 footer 链接改为纵向堆叠列表（每行一个，行高 40–44px），或 `flex-wrap` + 给每个链接 `white-space:nowrap`。

***REMOVED******REMOVED******REMOVED*** P1-6 home/learn 页脚同款不一致
- **位置**：footer。
- **现象**：home footer 有 6 个外链（关于/从这里开始/论文/GitHub/HuggingFace/Zenodo），reports footer 只有 3 个（关于/论文/GitHub）。
- **改法**：与 P0-2 一起，抽唯一权威 footer 片段，全站统一。

***REMOVED******REMOVED******REMOVED*** P1-7 discoveries hero 与上方订阅卡片层级倒挂
- **位置**：`discoveries.html` 顶部。
- **现象**：页面最顶是「想第一时间看到新发现？」邮件订阅卡片，其下才是真正的 hero 大标题「那些隐藏的联系」。次要的 newsletter CTA 抢在主标题之前，信息层级倒置。
- **改法**：hero 标题区放最上面，newsletter 订阅卡片移到页尾或内容中段。

***REMOVED******REMOVED******REMOVED*** P1-8 hero 标题中英文混排基线/字重不齐
- **位置**：discoveries「那些隐藏的联系」、learn 标题等。
- **现象**：衬线大标题里中文与英文/数字基线略有错位，部分标题斜体（Crimson Pro italic）与正排中文混用，重心不稳。
- **改法**：hero 中文统一 Noto Serif SC，英文/数字若同字号需 `vertical-align` 微调；斜体仅用于真正需要强调的英文术语，不要整句中英混斜。

***REMOVED******REMOVED******REMOVED*** P1-9 术语不统一：「我的收藏」vs「我的报告」vs「已保存的报告」
- **位置**：导航、reports 页、report 面包屑。
- **现象**：index nav 写「我的收藏」，reports nav 写「我的报告」，report 面包屑写「已保存的报告」，reports 页正文标题「我的报告」。同一个东西三个名字。
- **改法**：统一一个词（建议「我的报告」），全站 nav / 面包屑 / 标题 / 空状态一致。

---

***REMOVED******REMOVED*** P2 — 可发布后迭代

- **P2-1** home 三张入口卡片（23 个跨领域等价类 / 39 个精选发现 / Phase Detector）图标风格不统一：前两个是 emoji（🔗✨），第三个是彩色柱状图标——emoji 在不同 OS 渲染不一致，显廉价。建议统一为单色线性 SVG 图标（与 logo 同 stroke-width 1.5）。
- **P2-2** home 搜索框下方「⌘ + Enter 提交」提示，`⌘` 符号在非 Mac 设备上语义不明确。建议根据平台显示，或改为「Ctrl/⌘ + Enter」。
- **P2-3** classes / papers 页大量彩色标签（绿/橙/蓝 avg 评分徽标）色彩偏多，削弱「克制」基调。建议评分统一用单色 + 数值，仅高分用一种强调色。
- **P2-4** papers / methods 两页是几乎相同的模板（同一条 pipeline、13 个验证系统），内容高度重叠，用户会困惑两个入口是不是重复。建议合并，或明确区分定位。
- **P2-5** 404 页左侧「最近的查询」侧栏在 404 场景下意义不大，且让 404 页与其他纯内容页结构不一致。建议 404 用居中纯页式布局。
- **P2-6** about 页统计数字（4,445 / 63 / 23 / 5）四个数据块之间分隔较弱，建议加细分隔线或加大间距，强化「数据看板」感。
- **P2-7** 全站未见深色模式实现。当前白底为主符合用户偏好，可不做；若后续做，token 已是 CSS 变量结构，扩展成本低——建议留作 roadmap，不阻断发布。
- **P2-8** beta 徽标（`beta-badge`）在 logo 后，灰底小胶囊样式 OK，但桌面/移动大小一致性可再校准，确保不挤压 logo 文字基线。

---

***REMOVED******REMOVED*** 部署侧附带发现（非视觉，但影响发布判断）

- 线上 beta `https://beta.structural.bytedance.city/` **只部署了 home / analyze / report 三个页面**，其余 7 个页面（reports / classes / discoveries / papers / learn / methods / about）线上全部 404。本报告的页面审查基于本地 `web/frontend/` 渲染。**发布前必须确认这 7 个页面是否要上线**——若要，需补部署；若不要，需从导航里移除对应链接（否则用户点了就 404，等于 P0）。

---

***REMOVED******REMOVED*** 修复优先级建议

1. **先修 P0-1 / P0-2 / P0-4 / P0-5**（导航可达性 + 接口失败兜底 + 空状态 bug）——这几条直接决定「能不能给人用」。
2. **再修 P0-3 + P1 全部**——一致性与精致度，决定「像不像成熟产品」。
3. **确认部署侧 7 页 404 问题**——决定导航里的链接是真还是假。
4. P2 列入发布后迭代清单。

修完 P0 + P1，本站视觉上「够格对外发布」。当前状态：**未够格，差一轮收尾**。
