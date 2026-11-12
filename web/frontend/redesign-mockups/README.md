# 首页搜索框重做 — Perplexity-form 两种变体

对标 **Perplexity** 的搜索框气质，但严守白底（不引入 dark mode）。两种变体在 hero 背景 + tool 气质上拉开真实差异，让用户做一次清晰的取舍。

---

## 文件

```
redesign-mockups/
├── variant-a-perplexity-white.html   纯白卡 + 中性 hero 背景（#FAFAF9）
├── variant-b-perplexity-ink.html     纯白卡 + 暖墨 hero 背景（#F7F4ED）
├── screenshots/                       12 张（A/B × desktop/mobile × empty/focused/filled）
├── _screenshot.mjs                    Playwright 脚本（可复跑）
└── README.md                          本文件
```

跑截图（如需复现）：
```bash
cd web/frontend/redesign-mockups
node _screenshot.mjs
```

---

## 与 production（当前 `ask.css` line 68-204）对比

| 维度 | Production 现状 | Variant A（白卡） | Variant B（暖墨） |
|---|---|---|---|
| **max-width** | 660px | **768px** | **768px** |
| **padding** | 18/20/12 | **24/28/20** | **24/28/20** |
| **border-radius** | 16px | **20px** | **20px** |
| **font-size 输入** | 18px | **20px** | **20px** |
| **min-height** | 56px | **60px** | **60px** |
| **placeholder** | 长说明句（"描述一个你卡了很久的难题…"） | "你卡在哪个问题上？" | "问一个跨领域的问题..." |
| **快捷键提示** | focus 才显示（opacity 0→1） | **常驻显示** | **常驻显示** |
| **submit 尺寸** | 44×44 | **48×48** | **48×48** |
| **submit 状态** | 静态 accent-soft → hover 实色 | **填了文字直接变蓝实色**（Perplexity 风） | 同 A |
| **focus 反馈** | 边框深一档 + 中性阴影加深 | **同 + 卡片上浮 1px** | **同 + 卡片上浮 1px** |
| **hover 反馈** | scale(0.95) on active | **submit 上浮 1px + 阴影渲染**（200ms cubic-bezier(0.4,0,0.2,1)） | 同 A |
| **模式选择** | 无 | **深度分析 / 快速速览** 分段控件 | **DEEP / QUICK** monospace 工具感 |
| **hero 背景** | #F5F5F4 | #FAFAF9（中性偏冷） | **#F7F4ED 暖墨纸感 + 顶部柔光渐变** |
| **卡片对比** | 卡 = 纯白 on 浅灰，差异弱 | 卡 = 纯白 on 偏白，靠阴影 | **卡 = 纯白 on 暖墨，靠对比度浮起** |
| **示例 chips label** | "试试这些例子" | "试试这些例子"（无衬线小标题） | **"TRY THESE" monospace 工具气** |
| **letterpress 高光** | 无 | 无 | **`::before` inset 1px 白 50%**（顶边压印感） |

---

## Variant A — 白卡 + 中性 hero

**适合**：希望最贴近 Perplexity 原本视觉的方案，整页色温保持中性，强调"留白 + 字"。

**看点**：
- Hero 背景 `#FAFAF9` 比当前 production 的 `#F5F5F4` 略亮一点点 → 白卡靠双层中性阴影浮起
- 模式选择是分段控件（segmented control），Apple HIG 路数
- chips 区颜色全部中性，整体气质偏 **Apple / Notion**

**易踩坑**：白卡 on 偏白 hero，靠的是阴影的细腻度。如果某个屏幕 gamma 偏，可能阴影读起来过弱 → 用 box-shadow 双层 + transform translateY(-1px) 双重保险。

## Variant B — 白卡 + 暖墨 hero

**适合**：希望搜索框有"工具感"（Bear / Anthropic 那种），愿意整页色温向暖偏移的方案。

**看点**：
- Hero 是 `#F7F4ED → #F4F0E6` 纵向渐变 + 顶部 radial 柔光 → 纸质感但绝对不是米黄/beige
- 白卡 on 暖墨形成 **真实可见的对比度**（不靠阴影硬撑），第一眼就锁住视线
- 模式选择是 **monospace DEEP/QUICK + 圆点 + 细分隔线**，Bear/Notion 工具感
- 卡片 `::before` inset 1px 白 50% 高光 → 在好屏幕下有 letterpress 压印感
- chips 区 label 是 monospace 英文 "TRY THESE"，与卡片工具气一致

**易踩坑**：暖色 hero 是个判断题——如果整站其他页面都是 `#F5F5F4` 中性灰，单独一页换暖墨会有"飞地"感。要么整站跟进、要么放弃 Variant B。

---

## 推荐选择

**默认推荐 Variant B**，理由：

1. **真实差异更强**：白卡 on 暖墨 hero 的对比度，比白卡 on 偏白 hero 的阴影戏法更可靠。后者依赖屏幕、前者依赖物理对比度
2. **匹配品牌偏好**：用户喜好里 Bear / Notion / Manus 都是"暖中性纸"路数；Perplexity 自身近期也在朝暖灰走
3. **工具感而不是消费感**：Structural 是给 PM/分析师的认知工具，DEEP/QUICK monospace 比"深度分析/快速速览"分段控件更"工具"

**但如果**整站其他页面已经是 `#F5F5F4` 冷灰，且这次改动只覆盖首页 → **选 A**，避免视觉飞地。

---

## 主 session 集成步骤（仅供参考，本 session 不动）

两种变体改的都只是 `web/frontend/index.html` 顶部 hero + `web/frontend/assets/css/ask.css` 第 26-220 行。**`scripts/train_v2.py` / `v4/results/active_learning/simulation_report.md` / 任何其他文件都不动**（§2.6 boundary）。

1. 用户挑一个 variant
2. 把对应 HTML 文件里的 `<style>` 段对照 `ask.css` line 68-204 改造 → 写入 `ask.css`
   - `.ask-searchbox` → 768px / 20px radius / 24/28/20 padding
   - `.ask-searchbox__input` → 20px font / 60px min-height
   - `.ask-searchbox__submit` → 48×48 / 14px radius / hover translateY(-1px)
   - `.ask-searchbox__hint` → 去掉 opacity 0 默认值
3. 在 `index.html` line 154 把 placeholder 换成短句（"你卡在哪个问题上？" 或 "问一个跨领域的问题..."）
4. 新增 `.mode` 分段控件 HTML（footer 内 hint 之前）+ 对应 JS toggle
5. 仅 Variant B 需要：
   - `body` 背景改 hero gradient
   - `.ask-searchbox::before` 加 letterpress 高光
   - `.examples__label` 用 monospace
6. cache-bust：`ask.css?v=20260526a`
7. 测三层：单元（不需要）/ 集成（CSS 改动 → 视觉回归）/ 真实环境（Playwright 截 `localhost:8080/` 三态对比）
8. 主 session commit + push（按 §2.6 单文件 add）

---

## 关注点（设计 review 时请检查）

- [ ] 卡片在 1440 屏 + Retina 上有没有"飘"的感觉？阴影对不对
- [ ] focused 状态 transform translateY(-1px) 是否流畅，有没有跳一帧
- [ ] submit 从 disabled → enabled 过渡是否平滑（颜色 + 形状两个变化）
- [ ] 模式选择按钮 hover/pressed 三态切换是否清晰
- [ ] 移动端（390px）卡片是否撑满、内边距是否舒服、kbd 提示是否合理隐藏
- [ ] 暖色 hero（仅 B）在自己屏幕上是不是想要的"纸感"，而不是"米黄过头"

---

## 没做的事（避免越界）

- ❌ 没改 production 的 `ask.css` 或 `index.html`
- ❌ 没动 site-header / footer / 其他页面 CSS
- ❌ 没加 dark mode
- ❌ 没引入 chat-style continuation UI / agent-picker carousel
- ❌ 没碰 `scripts/train_v2.py` / `v4/results/` 等 §2.6 列出的禁区文件
