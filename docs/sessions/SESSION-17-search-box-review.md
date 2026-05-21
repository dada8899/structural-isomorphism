***REMOVED*** SESSION-17 · 首页搜索框 交互/视觉评审

> 2026-05-21 · 评审对象：https://beta.structural.bytedance.city/ 首页空状态搜索框（`.ask-searchbox`）
> 性质：纯评审，未改代码。结论给到具体色值/CSS 改动建议。

---

***REMOVED******REMOVED*** 0. 评审范围与现状采集

- 线上 `HTTP 200`，HTML 与本地 `web/frontend/index.html` 一致（同一份产物）。
- 本环境无 Playwright MCP，截图未取；评审基于源码逐属性还原（HTML + `ask.css` + `shared-tokens.css`），并按桌面 / 移动两套断点分别核对。

**相关源码：**
- 结构：`web/frontend/index.html` L83-120
- 样式：`web/frontend/assets/css/ask.css` L26-200（桌面）、L705-765（≤768）、L775-804（≤480）
- 色板：`web/frontend/assets/css/shared-tokens.css` L32-51

**当前搜索框的关键参数（桌面）：**

| 维度 | 当前值 |
|---|---|
| 容器背景 | `--brand-paper-card` = `***REMOVED***FFFFFF` |
| 页面背景 | `--brand-paper` = `***REMOVED***F5F5F4`（暖灰） |
| 边框 | `1.5px solid --brand-line ***REMOVED***E4E4E7` |
| 圆角 | `20px`（移动 480 → `14px`） |
| 内边距 | `18px 20px 12px` |
| 阴影 | `0 1px 2px rgba(24,24,27,.04), 0 8px 24px rgba(24,24,27,.08)` |
| 输入字号 | `18px` / 行高 1.55 / `min-height 56px` |
| placeholder 色 | `--brand-muted` = `***REMOVED***71717A` |
| placeholder 文案 | 「问点复杂的——它可能在另一个学科已经被解过」 |
| focus 态 | 边框变 `--brand-accent ***REMOVED***2563EB` + `0 0 0 4px rgba(37,99,235,.12)` 蓝光环 |
| 提交按钮 | 44×44 圆形，`--brand-accent ***REMOVED***2563EB` 实心蓝底白箭头；disabled 时灰底 |
| footer | 顶部 1px 分隔线，左侧 ⌘+Enter 提示（默认 opacity:0），右侧字数计数 + 提交按钮 |

---

***REMOVED******REMOVED*** 1. 诊断：「别扭」的具体原因（按可能性排序）

***REMOVED******REMOVED******REMOVED*** 主因 ① 提交按钮的「实心正蓝圆球」是最大违和源 —— 不是边框，是按钮

用户怀疑「蓝色」，方向对，但**罪魁不是 focus 边框，是右下角那个 44px 的实心蓝色圆形提交按钮**。

- 色值 `***REMOVED***2563EB`（Tailwind blue-600）：HSL ≈ `217°, 83%, 53%`。**饱和度 83% 在一个白底 + `***REMOVED***F5F5F4` 暖灰 + 衬线标题的克制版面里是异类**——整页其余颜色都是中性灰阶（`***REMOVED***18181B` / `***REMOVED***52525B` / `***REMOVED***71717A` / `***REMOVED***E4E4E7`），只有这一个高饱和正蓝。
- 它是**实心填充 + 纯圆形**：实心色块的视觉重量远大于线框/文字，圆形又比版面里其它元素（20px 圆角矩形、chips）形状异质。结果是一个本该「安静待命」的提交动作，变成了整个搜索框里最跳的视觉焦点。
- 对照基准：Notion / 飞书 / Bear 的输入框提交，要么是**灰色/中性按钮**，要么**根本没有常驻按钮**（靠回车提交），要么是**输入后才浮现的低调箭头**。iOS HIG 里搜索框是「安静的工具」，不带高饱和 CTA。当前设计把「搜索框」做成了「带强 CTA 的表单」，气质错位。
- 注意一个自相矛盾点：CSS 注释写「inert gray until there is input」——**设计意图本来就是想让它低调**，disabled 时确实是灰的。但只要用户开始输入（这恰恰是 90% 的真实场景），它立刻变成高饱和蓝。也就是说「别扭」在用户真正用它的那一刻才出现，所以「说不上来哪里别扭」——静态截图（空状态）看不出来。

***REMOVED******REMOVED******REMOVED*** 主因 ② 容器是「纯白卡片」浮在「暖灰背景」上，色温打架

- 页面背景 `***REMOVED***F5F5F4` 是**暖中性灰**（带一点点黄），搜索框背景 `***REMOVED***FFFFFF` 是**纯白**。两者并排，白卡片会显得「冷、生、像贴上去的」。
- 同时卡片用了 `1.5px` 实线边框 **+** 两层投影（`0 8px 24px` 的 8% 黑）。**描边和投影是两种相互替代的「抬升」手法，叠加使用会让卡片显得「过度封装」**——既圈了边又垫了影，边界感太硬，不够「融入页面」。Apple/Notion 的做法通常是二选一：要么极淡描边无影，要么无描边 + 极淡影。
- `1.5px` 这个边框宽度本身也偏重。Hairline 通常 `1px`，`1.5px` 在 Retina 上是肉眼可辨的「中等粗线」，和「克制」相悖。

***REMOVED******REMOVED******REMOVED*** 次因 ③ focus 态蓝光环 `4px` 偏厚 + 正蓝，二次强化违和

- focus 时 `0 0 0 4px rgba(37,99,235,.12)` —— 4px 光环偏厚（Apple 风格通常 3px 且更淡），且仍是 `***REMOVED***2563EB` 正蓝。这本身不算大问题（focus ring 用品牌色是合理的），但它和主因①的蓝按钮**同框出现**，把「整页唯一的高饱和蓝」从一个点变成一圈，违和被放大。
- 它只在 focus 时出现，所以也属于「静态看不出、一交互才别扭」。

***REMOVED******REMOVED******REMOVED*** 次因 ④ footer 分隔线把一个框「劈成两半」

- `.ask-searchbox__footer` 顶部有 `1px` 实线 `border-top`，把搜索框内部硬切成「输入区 / 工具区」两块。
- 空状态下 footer 里只有：左边一个 **默认 opacity:0 看不见** 的 ⌘+Enter 提示、中间一个 **默认 hidden** 的字数计数、右边一个 disabled 灰按钮。也就是说**这条分隔线下面，空状态时几乎是空的**——为了一个右对齐的按钮，硬加一条横线把框劈开，结构上不经济，视觉上多一条线。
- 衬线大标题 + 极简版面的气质下，「框里再画线」属于信息层级噪音。

***REMOVED******REMOVED******REMOVED*** 轻微 ⑤ placeholder 文案偏「文学」、不够「工具」

- 「问点复杂的——它可能在另一个学科已经被解过」——这句是**态度文案/slogan**，不是**操作引导**。它和上方 tagline（「跨学科搜索引擎 — 输入复杂问题，AI 从地震、神经、金融…」）语义重复，且用了中文破折号，偏散文。
- 搜索框 placeholder 的职责是「告诉用户该往里放什么 / 给个可模仿的输入样例」。这里更适合一句具体的示例式引导。属于轻微问题，但和「别扭」的整体气质有关。

***REMOVED******REMOVED******REMOVED*** 一句话总结
> 别扭 = 一个本该「安静」的搜索框，被「实心高饱和蓝圆按钮 + 纯白卡片浮在暖灰底 + 描边和投影双重封装 + 内部还劈一条线」做成了「用力的表单」。用户感觉到的「蓝色不对」是真的，但根源是**那抹蓝以「实心按钮」的形式出现**，而不是蓝色本身。

---

***REMOVED******REMOVED*** 2. Top 改进方案（具体色值 / CSS）

三个方案按「改动量」递增，推荐 **方案 B** 作为落地基线；方案 A 是最小改动止血；方案 C 是更彻底的重做。

***REMOVED******REMOVED******REMOVED*** 方案 A — 最小止血：只驯服那抹蓝（改 2 处）

不动结构，只把「实心高饱和蓝按钮」和「厚蓝光环」收敛，立刻去掉 80% 的违和。

```css
/* 1. 提交按钮：实心蓝 → 中性深墨，hover 才微微透出品牌色 */
.ask-searchbox__submit {
  /* was: background: var(--brand-accent);  ***REMOVED***2563EB */
  background: var(--brand-ink);     /* ***REMOVED***18181B 近黑，安静、与版面同族 */
  color: ***REMOVED***fff;
}
.ask-searchbox__submit:hover {
  background: ***REMOVED***000;                  /* 或保留 --brand-accent 作为 hover 微反馈 */
}

/* 2. focus 光环：4px → 3px，并降一档不透明度 */
.ask-searchbox:focus-within {
  border-color: var(--brand-ink-soft);            /* ***REMOVED***52525B 中性，不用正蓝 */
  box-shadow: 0 0 0 3px rgba(24,24,27,0.06),
              0 4px 18px rgba(0,0,0,0.05);
}
```

**为什么更好**：整页恢复「全中性灰阶」一致性，搜索框回到「安静工具」定位。深墨色按钮在白底上对比足够（用户看得见、点得到），但不再抢戏。这是 Notion 输入框、微信搜索的实际做法。

> 取舍：方案 A 等于「放弃品牌蓝在首页搜索框露出」。如果产品上希望保留一点品牌色，见方案 B。

***REMOVED******REMOVED******REMOVED*** 方案 B — 推荐基线：保留品牌蓝，但换「形态」+ 收口卡片（改 4 处）

核心思路：蓝色可以留，但**不要以「实心圆按钮」的形态出现**——改成「输入后才出现的低饱和箭头」或「描边/浅底按钮」。同时把卡片从「描边+投影双封装」收成「单一手法」。

```css
/* 1. 卡片：去掉硬描边，只留极淡描边 + 极淡单层投影；背景从纯白微微转暖 */
.ask-searchbox {
  background: ***REMOVED***FFFFFF;
  border: 1px solid var(--brand-line);            /* 1.5px → 1px hairline */
  border-radius: 16px;                             /* 20px → 16px，更内敛 */
  box-shadow: 0 1px 3px rgba(24,24,27,0.05);       /* 去掉 0 8px 24px 那层 */
}
.ask-searchbox:focus-within {
  border-color: var(--brand-line-strong);          /* ***REMOVED***D4D4D8，安静地变实 */
  box-shadow: 0 0 0 3px var(--brand-accent-ring),  /* 蓝光环留着，但 3px */
              0 2px 8px rgba(24,24,27,0.06);
}

/* 2. 提交按钮：实心圆 → 浅蓝底 + 蓝箭头（accent 退到「描边/浅底」层级） */
.ask-searchbox__submit {
  background: var(--brand-accent-soft);    /* rgba(37,99,235,.08) 浅蓝底 */
  color: var(--brand-accent);              /* 蓝箭头，不再是大色块 */
  border-radius: 12px;                     /* 圆形 → 圆角方形，与卡片同族 */
}
.ask-searchbox__submit:hover {
  background: var(--brand-accent);         /* hover 时才实心，作为交互奖励 */
  color: ***REMOVED***fff;
}

/* 3. 去掉 footer 那条把框劈开的横线 */
.ask-searchbox__footer {
  border-top: none;
  margin-top: 4px;
  padding-top: 4px;
}
```

```html
<!-- 4. placeholder 改成操作引导式（index.html L93） -->
placeholder="描述一个你卡住的复杂问题，比如「月活每月掉 7% 怎么干预」"
```

**为什么更好**：
- 蓝色保留了品牌识别，但从「实心色块（视觉重量最高）」降到「浅底+线性图标（视觉重量低）」——这正是「accent 该用在哪一层」的关键：**品牌蓝适合做边框/浅底/文字链接，不适合做首页唯一一个实心 CTA 圆球**。
- 圆形按钮 → 12px 圆角方形，与 16px 圆角的卡片形状同族，消除形状异质。
- 描边 1px + 单层淡影，去掉「双重封装」感，卡片「融入页面」而非「贴在页面上」。
- 删掉内部分隔线，搜索框回到「一个完整的框」。
- placeholder 给出可模仿的具体例子，降低「我该输入什么」的认知成本。

***REMOVED******REMOVED******REMOVED*** 方案 C — 彻底重做：无常驻按钮，回车提交（最克制）

如果愿意更激进地对标 Bear / 微信搜索的「极简」：**干脆去掉常驻提交按钮**，输入框聚焦后底部只显示一行极淡的 `↵ 提交 · ⌘↵ 换行` 提示，提交完全靠键盘。

- 优点：搜索框变成纯粹的「一个框 + 文字」，没有任何色块，最安静，最接近用户的设计偏好基准。
- 代价：移动端没有物理回车键的便利性，需要保留一个**输入后才淡入**的低调箭头（`opacity` 过渡，`--brand-ink-soft` 描边款），仅移动端显示。
- 适用：如果产品判断「首页搜索是核心动作、不需要 CTA 引导」，方案 C 最纯粹。否则方案 B 更稳。

---

***REMOVED******REMOVED*** 3. ASCII Mockup（方案 B 桌面态）

```
当前：                                方案 B：
┌──────────────────────────────┐     ┌──────────────────────────────┐
│  问点复杂的——它可能在...        │     │  描述一个你卡住的复杂问题，比如  │
│                              │     │  「月活每月掉 7% 怎么干预」      │
│ ───────────────────────────  │ ←劈  │                              │
│  ⌘+Enter        0/8000  ●蓝球 │ 线   │              0/8000   [↗浅蓝] │
└──────────────────────────────┘     └──────────────────────────────┘
   1.5px边框 + 双层投影                   1px描边 + 单层淡影，无内部线
   ●= ***REMOVED***2563EB 实心圆，整页最跳            [↗]= 浅蓝底蓝箭头，安静；hover才实心
```

---

***REMOVED******REMOVED*** 4. 落地建议

1. 先上 **方案 B**（4 处改动，集中在 `ask.css` L56-71 / L156-170 / L93-100 + `index.html` L93），改完用 Playwright 截桌面 1280 + 移动 390 两视口，人眼比对。
2. 同步检查 `.ask-followup-box`（L758-764）的提交按钮——它复用了 `ask-searchbox__counter` 但提交按钮样式可能也带同款实心蓝，应一并对齐，避免追问框和首页框气质不一致。
3. 移动端 480 断点的 `border-radius: 14px` 相应同比下调（如 12px），与桌面 16px 成比例。
4. 本评审不改代码，待用户确认方案后再实施。
