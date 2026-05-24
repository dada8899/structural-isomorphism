# SESSION-17 — 发布前可用性全站走查

**日期**: 2026-05-21
**审查对象**: https://beta.structural.bytedance.city/ (prod, semver 0.2.0, git 8f10d388c799)
**方法**: 生产站点实测 (curl/SSE 探测，含真实报告生成跑完一整条流程) + 前端代码静态走读
**审查范围**: 首页 / search / analyze / report / reports / classes / discoveries / papers / learn / methods / about / phenomenon / 404，全部 API 端点，share/feedback/收藏/历史/语言切换/移动端
**说明**: 本环境无 Playwright MCP，改用「生产 HTTP/SSE 实测 + 前端代码逐页走读」组合，每个页面、路由、交互都追到。报告生成实跑了一份完整 9 段报告（306KB，250s 跑完），并实测了 persist / share / feedback 全链路。

---

## 总评

**现在不能发布。** 产品骨架完整、设计语言统一、报告生成内核可用，但有 4 个 P0 级断裂会让「第一次来的用户」直接撞墙：

1. 用户生成的报告**找不回来**——「我的报告」页面永远是空的，主导航也没有入口。
2. 分享出去的报告链接打开后**排版严重降级**——显示的是原始英文字段名的键值树，不是给真人看的报告。
3. `/report/<id>` 路由整条死掉（API 404）。
4. 首页其实是「问答」UI，但全站文档/代码里的「搜索→结果→选现象」流程挂在一套**没有入口的旧首页**上——信息架构是分裂的。

这些不是打磨问题，是「核心承诺（存储/分享/回看报告）做不到」。修完 P0 + 关键 P1 后可以再评估。

**计数：P0 = 4 · P1 = 9 · P2 = 8**

---

## P0 — 阻断发布（必须修）

### P0-1 「我的报告」(/reports) 永远是空的，功能完全不可用
**复现**：
1. 生成任意一份报告（首页问答 → 运行深度分析 → 报告默认 persist=1）。
2. 访问 `/reports`。
3. 永远显示空状态「还没有保存的报告」。

**实测证据**：用 `X-Anon-Id: review-anon-3` 持久化了报告 `r_3d8655e19a61bbbb`（`persisted` 事件确认 `id` + `share_token` 都返回了），随后用**同一个 anon-id** 调 `GET /api/reports/mine` → `{"items":[],"has_more":false}`。换用 query 参数 `anon_id=` 持久化同样列不出来。

**根因**：报告 persist 时写入的 `creator_anon_id` 与 `ReportStore.list_by_anon()` 查询的 key 不匹配，或 persist 路径根本没把 anon-id 落库。`/reports` + `my-reports.js` + `/api/reports/mine` 三层代码都齐了，但端到端断链。

**影响**：用户生成报告后**没有任何办法回看自己的历史报告**。这是产品「可存储」承诺的核心，整条链路对用户不可见。

**建议**：修 persist→store 的 anon-id 落库路径。加一条集成测试：persist(anon=X) → `list_by_anon(X)` 必须返回该报告。这正是 CLAUDE.md「状态机不从下游反推 / SSE 协议改动必配集成测试」要求的场景。

---

### P0-2 已保存/已分享报告的查看页排版严重降级，显示原始英文字段名
**复现**：
1. 拿任意 share token 打开 `/report/share/<token>`。
2. 报告正文不是 analyze 页那种结构化排版，而是一棵原始 JSON 键值树。

**根因**：`report.js` 的 `renderReport()` 用通用 `renderValue()` 递归 dump payload，而不复用 `analyze.js` 里那 9 个专用 `renderers`。结果用户会看到 `if_time_short`、`this_week`、`next_week_followup`、`parameter_map`、`isomorphism_reason` 等**未翻译的英文字段名**直接当标题渲染（实测 payload 的 `action_plan` 子键就是 `intro / if_time_short / this_week / next_week_followup`）。analyze 页的「TL;DR 卡 / 行动清单 / 结构对照 / KaTeX 公式」等专属排版全部丢失。

**影响**：分享是产品的传播主路径。用户把链接发给同事，对方打开看到的是一坨技术 JSON——对「成熟产品」的观感是毁灭性的。

**建议**：`report.js` 直接 import / 复用 `analyze.js` 导出的 `SECTIONS` + `renderers`（analyze.js 已有 `window._suppressAnalyzeBoot` 机制，本就是为复用设计的，却没复用渲染器）。`renderValue` 只作为兜底。

---

### P0-3 `/api/report/{id}` 对真实存在的报告返回 404
**复现**：
1. 持久化报告，拿到 `id`（如 `r_3d8655e19a61bbbb`）。
2. `GET /api/report/r_3d8655e19a61bbbb`（带或不带 `X-Anon-Id`）→ HTTP 404 `{"detail":"not found"}`。

**根因**：`api/report.py:get_report_by_id` 做「软所有权检查」：`if owner and owner != x_anon_id: raise 404`。但实测带上持久化时用的同一 anon-id 仍然 404 → 说明要么 `creator_anon_id` 没落库（与 P0-1 同根），要么 `store.get_by_id()` 取不到行。

**影响**：`/report/<id>` 路由（`my-reports.js` 卡片 `href="/report/{id}"` + `report.js` 的 `idMatch` 分支）整条死掉。即使 P0-1 修好让「我的报告」列出卡片，点进去也是 404。

**建议**：与 P0-1 一起修。加集成测试覆盖「同 anon-id 读自己的报告」+「无 anon-id 读公开报告」两条路径。

---

### P0-4 信息架构分裂：部署的首页是「问答 UI」，但「搜索流」挂在一套无入口的旧首页
**复现 / 证据**：
- 生产 `index.html` 用的是 `#ask-form` / `.ask-searchbox__input`，加载 `ask.js`，提交到 `POST /api/ask/stream`（Perplexity 式问答）。
- 但 `home.js` 用的是 `#search-form` / `.searchbox__input`，跳转 `/search?q=`——这是另一套首页实现，**生产首页根本没加载它**。
- 全站只有 `history-sidebar.js` 和 `phenomenon.js` 链到 `/search`。一个第一次来的用户**没有任何自然路径**进入 `search.html` 的「候选列表→首推→选现象→/analyze」流程。
- `search.html`（含首推卡、补充视角、V2 跨域对、低适配度 gate）是套做得很完整的页面，却基本是孤儿页。

**影响**：项目文档（CLAUDE.md、各 SESSION handoff）描述的核心流程是「首页搜索框→搜索结果→选现象→生成报告」，但线上根本不是这个流程。两套首页 + 两条流程并存，没人知道哪条是正路。新用户走的是问答流（问答里有「运行深度分析」CTA 直接跳 `/analyze`，跳过了 search 选现象环节）。

**建议**：产品决策——**确定唯一首页流程**。要么（A）问答流是正路，那 `search.html` / `home.js` 要么删掉要么明确定位为「高级检索」并给入口；要么（B）搜索流是正路，那要换回 `home.js` 首页。当前「两套并存、一套没入口」必须收敛，否则文档、埋点、用户预期全是错位的。

---

## P1 — 应修（影响体验，不一定阻断）

### P1-1 主导航没有「我的报告」入口
`index.html` 主导航 9 项里没有 `/reports`。`reports.html` 自己导航里有，但用户到不了 `/reports` 就看不到这个导航。即使 P0-1 修好，用户也找不到入口。**建议**：主 header 加「我的报告」（放在「我的收藏」旁边）。

### P1-2 站内导航在不同页面严重不一致
实测每页 nav-link 数量：index 9 / classes 6 / discoveries 7 / papers 6 / learn 8 / methods 6 / about 7 / start-here 7 / reports 5 / search 7 / analyze 7。每个页面的 header 是各写各的，项目集合、顺序都不同（reports 页缺「从这里开始/方法/Phase Detector/收藏/了解」，classes 页又是另一组）。**影响**：用户在站内跳转时导航栏一直在变，缺乏「这是同一个产品」的稳定感。**建议**：抽一份共享 header 片段（report.html 已经用 JS 注入 header 了，可推广），所有页面统一。

### P1-3 report.html / reports.html 的 Plausible 指向错误域名
`report.html`、`reports.html` 加载 `https://plausible.io/js/script.js`（公网 Plausible 云），其余全站页面用 `https://plausible.bytedance.city/js/script.js`（自托管）。`index.html` 还专门 `preconnect` 了自托管域名。**影响**：这两页的埋点要么打到错误实例、要么被自托管假设下的 CSP/网络拦掉，分享页和报告列表页的数据会丢。**建议**：统一成自托管域名。

### P1-4 report.html 的 KaTeX 走 CDN，与全站自托管策略冲突
`report.html` 从 `cdn.jsdelivr.net` 加载 KaTeX，而 `index.html` 注释明确说字体/脚本要自托管避免外部依赖阻塞 LCP。**影响**：CDN 被墙/慢时分享报告页的公式渲染失败或卡顿，且引入了全站其它页面没有的第三方依赖。**建议**：KaTeX 自托管，与 analyze 页一致。

### P1-5 `/report/<id>` 模式下不渲染分享栏
`report.js`：`if (window._m14_renderShareBar && route.kind === 'share')` —— 只有 `share` 路由才渲染分享栏。用户从「我的报告」点进自己的报告（`/report/<id>` 路由），看不到「复制链接 / 分享」按钮，没法把自己的报告分享出去。**建议**：`/report/<id>` 也应能拿到 share_token 并渲染分享栏（detail 接口返回 share_token 即可）。

### P1-6 报告生成首字节延迟可达 30s+，加载文案承诺「30–60s」但实测整篇 >180s
实测一份完整报告生成耗时约 250s 才跑完 9 段；`meta` 事件本身在多次尝试里 30s 内都没到。但 `analyze.html` 加载态文案写「通常需 30–60s」。SESSION-16 handoff 第 162 行也明确写过「real-prod analyze stream measured > 180s，不要承诺 60–120s」。**影响**：用户被文案设了错误预期，等到 60s 还在转就会认为「卡死了」而离开。**建议**：把文案改成「通常需 2–4 分钟，会分段逐步出现」，并确保分段渲染（已实现）足够明显，让用户在等待中持续看到进度。

### P1-7 报告生成流偶发零字节返回（流可靠性）
实测同一个合法 `b_id=5k-25-001`：一次成功返回 306KB 完整 9 段，多次返回 0 字节、无任何 SSE 事件。HTTP 状态是 200 + `content-type: text/event-stream`，但 body 空。可能是长连接空闲被中间层（nginx/代理）掐断，或后端在首字节前就异常退出。**影响**：用户发起报告生成，有概率页面一直停在 loading 态、既不出内容也不报错（前端 `es.onerror` 在 `receivedKeys.size===0` 时才报错，但若连接是「正常关闭」可能连 onerror 都不触发）。**建议**：后端在流开始时立即 flush 一个 `meta` 或心跳事件占位；nginx 关闭该 location 的 proxy buffering 并加长 `proxy_read_timeout`；前端对「200 但流意外结束且零 section」也要落到错误态。

### P1-8 首页问答流里没有「查看/管理已存报告」的任何线索
部署的首页是 `ask.js`，整份代码 0 处提及 reports / 保存。问答流的 thread item 有「运行深度分析」CTA，但用户走完 analyze 生成并 persist 报告后，问答首页本身不提供任何回到报告的线索。配合 P0-1/P1-1，用户的报告处于「生成了但全站都看不到」的孤岛。**建议**：问答首页（及 analyze 页）显眼处放「我的报告」入口。

### P1-9 移动端缩放被锁：多页面缺 maximum-scale 但 index/learn/thank-you 设了 maximum-scale=5.0
不一致：`index.html` / `learn.html` / `thank-you.html` 设 `maximum-scale=5.0`，其余页面没设（默认允许缩放）。`maximum-scale` 限制了视障/老年用户放大页面的能力，是 WCAG 可达性问题，且全站不一致。**建议**：移除所有 `maximum-scale`，统一 `width=device-width, initial-scale=1`，允许用户自由缩放。

---

## P2 — 打磨

### P2-1 `/api/search` 仅支持 POST，GET 返回 405
`GET /api/search?q=x` → 405 Method Not Allowed。前端 `search.js` 走 POST 是对的，但任何人手动拼 GET URL（或爬虫/分享 search 链接被预取）会撞 405。错误页 `instance` 还指向 `structural.bytedance.city`（裸域）而非 `beta.` 子域。**建议**：要么 GET 也接受、要么 405 返回更友好的提示；统一错误页 instance 域名。

### P2-2 报告分享页 `report.html` 的英文/中文混用
`report.html` 的 `<meta description>` 是英文（"A persisted Structural cross-domain isomorphism report."），`report.js` 的 `renderValue` 兜底文案是英文（`(empty)`、`(empty list)`），`renderMeta` 里 `views` 是英文。而页面其余部分是中文。**建议**：统一中文。

### P2-3 report.html 错误文案用了英文标点
`report.html`：「这份报告可能已被删除,或链接已失效。」「分享前请确认.」——用了半角逗号/句号。中文排版应用全角「，」「。」。

### P2-4 `analyze.js` 在缺 `b_id` 时静默重定向回首页
`analyze.js` DOMContentLoaded：`if (!bId) { window.location.href = '/'; return; }`。用户若手贱改 URL 或拿到残缺链接，会被无提示弹回首页，困惑「我点的链接怎么没了」。**建议**：跳转前给一个 toast 或落到一个轻量错误态。

### P2-5 首页示例 chip 与「探索卡」文案里的数字可能与后端不同步
首页硬编码「23 个跨域等价类」「39 个精选发现」，但 `/api/discoveries` 实测返回 `count: 19`。数字是写死在 HTML 里的，后端数据增减后会对不上。**建议**：这些计数从 API 拉，或在数据变更流程里挂一个校验。

### P2-6 报告 `view_count` 对自己也计数
实测同一份报告我自己 curl 一次，`view_count` 从 0 → 1。作者自己打开自己的报告也算一次浏览，会让「👁 N 次浏览」虚高。**建议**：record_view 时排除 creator_anon_id 本人，或至少同一 anon-id 去重。

### P2-7 `report.js` 路由正则过严，trailing/大小写之外的合法变体会落空
`parseRoute()` 用 `^\/report\/share\/([a-f0-9]{32})$` 和 `^\/report\/(r_[a-f0-9]{16})$`。token/id 格式一旦后端调整（如加长、加连字符）前端会静默判定「无效 URL」。**建议**：放宽正则或由后端校验，前端只做基本提取。

### P2-8 `analyze.html` 默认 `persist=1` 但用户无知情、无开关
`analyze.js`：除非 URL 显式 `persist=0`，否则每份报告都默认持久化并生成公开可读的 share token。用户没有被告知「你生成的报告会被存下来、拿到链接的人都能看」。`reports.html` 副标题提了「soft-privacy」，但生成时刻没有任何提示。**建议**：生成页明确告知「报告会被保存，可分享」，或给一个「不保存」选项。属隐私合规打磨项。

---

## 走查覆盖清单（已实测/已走读）

| 页面/流程 | 状态 | 备注 |
|---|---|---|
| 首页 (index, ask UI) | ✅ 可用 | 问答流，example chips、字数计数、Cmd+Enter 都在 |
| 首页 search UI (home.js) | ⚠️ 孤儿 | 见 P0-4，生产未加载 |
| /search 结果页 | ⚠️ 无入口 | 页面本身完整（首推/补充视角/V2/低适配 gate） |
| /analyze 报告生成 | ✅ 内核可用 | 实测 306KB/9段跑通；偶发 0 字节 (P1-7)；文案误导 (P1-6) |
| /report/share/<token> | 🔴 排版降级 | P0-2 |
| /report/<id> | 🔴 API 404 | P0-3 |
| /reports 我的报告 | 🔴 永远空 | P0-1 + P1-1 |
| 分享链接 copy/open | ✅ | analyze 页分享栏逻辑正常 |
| 9 段 + 整体 👍/👎 反馈 | ✅ | `POST /api/report/{id}/feedback` 实测返回 `{ok:true,total_up:1}` |
| classes/discoveries/papers/learn/methods/about | ✅ 200 | 导航不一致 (P1-2) |
| phenomenon 详情页 | ✅ | 链到 /search、/analyze |
| 404 页 | ✅ | 干净 |
| 语言切换 i18n | ✅ | `lang-toggle` + analyze/search 都有 onChange 重渲染 |
| 收藏 | ✅ | localStorage，badge、首页 #home-favorites |
| 历史侧边栏 | ✅ | 链到 /search |
| 移动端 390 视口 | ⚠️ | 缩放锁不一致 (P1-9)；布局未能用 Playwright 实截，建议补真机走查 |
| 键盘可达性 | 🟡 部分 | textarea 有 aria-label/aria-describedby；缩放锁是减分项 |
| 空状态/加载态/错误态 | 🟡 部分 | search/analyze 错误态完整；analyze 缺 b_id 静默跳转 (P2-4)；流静默结束 (P1-7) |

---

## 修复优先级建议

1. **先修 P0-1 + P0-3**（同根：persist 的 anon-id 落库 + by-id 读取）——一次修复，「我的报告」和 `/report/<id>` 同时复活。配集成测试。
2. **P0-2**：`report.js` 复用 `analyze.js` 的 renderers——分享出去的报告才能见人。
3. **P0-4**：产品拍板首页唯一流程，收敛两套首页。
4. **P1-1/P1-8**：补「我的报告」入口（主 header + 问答页）。
5. **P1-3/P1-4**：report/reports 页的 Plausible 域名 + KaTeX 自托管对齐全站。
6. **P1-6/P1-7**：报告生成文案改为「2–4 分钟」+ 流可靠性加固（心跳事件 + nginx buffering + 前端兜底错误态）。
7. P1-2/P1-5/P1-9 与 P2 批量收尾。

修完 P0 全部 + P1-1/P1-6/P1-7 后，再做一轮（最好用真浏览器/Playwright）端到端验收，重点回归「生成→保存→在我的报告里看到→点开→分享→对方打开」整条链路。
