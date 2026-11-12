# Structural Phase 1 MVP — 三次对话实施计划

> 产品：beta.structural.bytedance.city
> 知识库：4475 条现象（kb-5000-merged.jsonl）
> 视觉风格：Linear / Perplexity / Anthropic
> 技术栈：FastAPI + 纯 HTML/CSS/JS + OpenRouter LLM
> 部署：VPS + systemd + Nginx

---

## 总体策略

每次对话结束时，用户能看到**可运行的东西**（即使不完整），而不是一堆半成品代码。

| 次数 | 交付形态 | 用户能做什么 |
|------|---------|------------|
| 第 1 次 | 本地 localhost 跑起来 | 打开首页，完成引导，搜索，看到结果卡片列表 |
| 第 2 次 | 本地 localhost 完整版 | 结果页+详情页+所有辅助页面全部跑通 |
| 第 3 次 | beta.structural.bytedance.city 上线 | 手机打开就能用，体验全部打磨完成 |

---

## 视觉基准

### 参考产品
- **Linear** (linear.app)：极简、精准、动效精致
- **Perplexity** (perplexity.ai)：搜索中心化、信息密度、分层清晰
- **Anthropic** (anthropic.com)：衬线字体、大留白、学术感

### 设计系统

**色彩（固定值，全局使用）**
```css
--bg-primary: #FAFAF9;      /* 主背景，极淡米色 */
--bg-secondary: #F4F4F5;    /* 次背景，灰白 */
--bg-tertiary: #FFFFFF;     /* 卡片背景 */
--border-subtle: #E4E4E7;   /* 默认边框 */
--border-strong: #D4D4D8;   /* 强调边框 */
--text-primary: #18181B;    /* 主文字，非纯黑 */
--text-secondary: #52525B;  /* 次要文字 */
--text-tertiary: #A1A1AA;   /* 三级文字/占位符 */
--accent: #2563EB;          /* 唯一强调色，克制使用 */
--accent-hover: #1D4ED8;
--success: #059669;         /* 仅用于相似度高的数字 */
```

**字体**
```css
--font-serif: 'Noto Serif SC', 'Times New Roman', serif;  /* 主标题 */
--font-sans: 'Inter', 'PingFang SC', -apple-system, sans-serif;  /* 正文 */
--font-mono: 'JetBrains Mono', 'SF Mono', monospace;  /* 数字/代码 */
```

**字号阶梯**（严格遵守）
```
72px / 48px / 32px / 24px / 20px / 16px / 14px / 12px
```

**间距系统**（8px 基准）
```
4px / 8px / 12px / 16px / 24px / 32px / 48px / 64px / 96px / 128px
```

**圆角**
```
4px (输入框/按钮) / 8px (卡片) / 12px (大卡片) / 16px (对话框)
```

**动效缓动**
```css
--ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);  /* 主要缓动 */
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
--duration-fast: 150ms;
--duration-normal: 240ms;
--duration-slow: 400ms;
```

---

## 第 1 次对话：地基 + 首页

**目标**：跑起来一个能搜索的基础版本。结束时用户能本地打开首页，完成引导，搜索，看到结果卡片（但结果页还是基础版）。

### 交付清单

#### 1.1 项目初始化（15 分钟）

```
~/Projects/structural-isomorphism/web/
├── PLAN.md                    # 本文档
├── backend/
│   ├── main.py                # FastAPI 入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── search.py          # 搜索端点
│   │   ├── phenomenon.py      # 现象详情端点
│   │   ├── mapping.py         # LLM 映射生成端点
│   │   └── daily.py           # 每日发现端点
│   ├── services/
│   │   ├── __init__.py
│   │   ├── search_service.py  # 封装 StructuralSearch
│   │   ├── llm_service.py     # OpenRouter 调用
│   │   └── cache.py           # 映射缓存
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html             # 首页
│   ├── search.html            # 结果页（第 2 次对话完善）
│   ├── phenomenon.html        # 详情页（第 2 次对话完善）
│   ├── about.html             # 关于页（第 2 次对话）
│   ├── 404.html               # 404 页（第 2 次对话）
│   ├── assets/
│   │   ├── css/
│   │   │   ├── reset.css
│   │   │   ├── design-system.css    # 设计变量
│   │   │   ├── common.css           # 通用组件
│   │   │   ├── home.css             # 首页样式
│   │   │   └── onboarding.css       # 引导流程样式
│   │   ├── js/
│   │   │   ├── api.js               # API 封装
│   │   │   ├── onboarding.js        # 引导流程逻辑
│   │   │   ├── home.js              # 首页交互
│   │   │   └── utils.js
│   │   ├── fonts/                   # Inter + Noto Serif SC 子集
│   │   └── icons/                   # SVG 图标
│   └── shared/
│       ├── header.html              # 共享头部
│       └── footer.html              # 共享底部
├── data/                             # 运行时数据（缓存等）
│   └── mapping_cache.jsonl
└── scripts/
    ├── dev.sh                        # 本地开发启动
    └── precompute_daily.py           # 预计算每日发现
```

#### 1.2 FastAPI 后端骨架（30 分钟）

- 初始化 FastAPI 应用
- CORS 配置
- 静态文件服务（frontend/ 目录）
- 日志配置
- 环境变量加载（OPENROUTER_API_KEY）
- 启动时加载 StructuralSearch（预加载 4475 条知识库和模型）
- 健康检查端点 `/api/health`

#### 1.3 核心 API 端点（60 分钟）

**POST /api/search**
- 输入：`{"query": "字符串", "top_k": 12}`
- 输出：`{"results": [{"id", "name", "domain", "type_id", "description", "score"}]}`
- 逻辑：调用 StructuralSearch.query()
- 过滤：相似度 < 0.5 的不返回

**GET /api/phenomenon/{id}**
- 返回单个现象的完整信息
- 包含：name, domain, type_id, description, 该结构类型的其他现象

**GET /api/daily**
- 返回今日的 3 组跨领域发现
- 数据源：预计算的 results/v2-discoveries.jsonl 的前 3 对
- 按日期轮换（用日期作为 seed）

**GET /api/suggest**
- 返回 5 条预设的搜索建议（用于空状态引导）
- 静态配置，不需要数据库

**GET /api/examples**
- 返回首页的 3 个示例发现
- 从 v2-discoveries.jsonl 挑选最惊艳的 3 个

#### 1.4 LLM 集成（30 分钟）

**POST /api/mapping**
- 输入：`{"phenomenon_a_id": "...", "phenomenon_b_id": "..."}`
- 输出：`{"structure_name", "formula", "parameter_mapping", "action_suggestions", "why_important"}`
- 先查缓存（data/mapping_cache.jsonl）
- 未命中则调用 OpenRouter（用 Claude Sonnet 或 GPT-4）
- 生成后写入缓存

Prompt 模板：
```
你是一个跨领域结构分析专家。给定两个现象：

现象 A：{name_a}（领域：{domain_a}）
描述：{desc_a}

现象 B：{name_b}（领域：{domain_b}）
描述：{desc_b}

相似度：{score}

请输出 JSON：
1. structure_name：共享的数学结构名称（中文）
2. formula：数学公式（LaTeX）
3. parameter_mapping：3-5 对参数对应关系，每对 {a_term, b_term, a_symbol, b_symbol}
4. action_suggestions：3 条"从 A 领域借用到 B 领域的行动建议"
5. why_important：一句话说明为什么这个映射重要

要求：
- 语言精确、不说废话
- 参数对应关系必须在数学上成立
- 行动建议必须具体可执行
```

#### 1.5 首页引导流程（90 分钟）

**Step 1：欢迎动画（2 秒）**

全屏黑色渐变背景，中央文字序列：
1. 0-500ms：`万物的形状都在重复` 淡入
2. 500-1500ms：屏幕两侧浮现两个现象卡片（"放射性衰变" 和 "社交媒体热度消退"）
3. 1500-2500ms：中间用 SVG 路径画出连接线，画完后亮起
4. 2500ms：`一个跨领域思维引擎` 淡入
5. 页面自动进入 Step 2 或用户点击"跳过"

**Step 2：具体例子（10-15 秒）**

展示一个真实的结构映射作为教学：
- 左右两张卡片：放射性衰变 / 药物浓度下降
- 中间展示参数对照表（3 行：原子核数量↔药物浓度 等）
- 底部一句话："它们共享同一个数学骨架：指数衰减"
- 底部按钮：`我也想找一个试试 →`
- 右上角"跳过"链接

**Step 3：引导首次搜索**

- 跳转到首页
- 搜索框有呼吸动效（box-shadow 脉冲）
- 搜索框上方浮动一个 tooltip：`描述一个你好奇的现象，比如"交通越治越堵"`
- 用户开始输入（focus + 按键）后 tooltip 淡出
- localStorage 标记 `onboarding_complete=true`，之后不再显示

**技术实现**：
- 单个 HTML 页面（index.html）用状态切换显示不同 step
- 用 CSS transform + opacity 做切换
- 整个引导用 `<dialog>` 或全屏 fixed overlay
- 跳过按钮绑定 ESC 键和点击事件

#### 1.6 首页主体（90 分钟）

**布局**（基于 Linear/Perplexity 风格）

```
┌──────────────────────────────────────────────┐
│  [logo]                       [关于] [GitHub] │  ← 极简顶栏 56px
├──────────────────────────────────────────────┤
│                                               │
│                                               │
│           (垂直居中到视口的 40% 处)             │
│                                               │
│             Structural                        │  ← Noto Serif SC 48px
│                                               │
│        万物的形状都在重复。找到它。             │  ← 次标题 20px
│                                               │
│  ┌─────────────────────────────────────┐      │
│  │ 描述一个你观察到的现象...          🔍 │      │  ← 搜索框 720px
│  └─────────────────────────────────────┘      │
│                                               │
│  或试试这些：                                  │
│  [为什么所有排行榜都头部通吃] [堵车如波浪...] │  ← 建议 chips
│  [药越吃越没效果] [团队大了效率下降]         │
│                                               │
│  ─────────────────────────────────────        │
│                                               │
│  今日发现                                      │
│                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐      │  ← 3 个示例卡片
│  │ 放射性衰变│ │ 排队买奶茶│ │ 雪崩      │      │
│  │    ↕     │ │    ↕     │ │    ↕     │      │
│  │ 遗忘曲线  │ │ 打印机队列│ │ 股市崩盘 │      │
│  │ 0.94     │ │ 0.92     │ │ 0.89     │      │
│  └──────────┘ └──────────┘ └──────────┘      │
│                                               │
│                                               │
│  500+ 现象  ·  87 个领域  ·  84 种数学结构     │  ← 底部统计
│                                               │
└──────────────────────────────────────────────┘
```

**交互细节**：

- 搜索框聚焦时：边框从 --border-subtle 变 --accent，有 4px 半透明焦点环
- placeholder 动画：每 4 秒轮换文案（CSS 或 JS 实现）
- 建议 chips hover：背景 fade in，边框颜色加深
- 示例卡片 hover：整个卡片微微上浮（translateY -2px），阴影加深
- 回车键触发搜索，跳转到 /search?q=xxx

**动画进入序列**（页面首次加载，onboarding 结束后）：
1. 0ms：Logo 淡入
2. 100ms：主标题从下浮入
3. 200ms：副标题淡入
4. 300ms：搜索框从 scale 0.98 → 1.0 + 淡入
5. 400ms：建议 chips 依次淡入（每个延迟 50ms）
6. 600ms：今日发现区域滑入
7. 800ms：底部统计淡入

#### 1.7 搜索提交到基础结果页（30 分钟）

第 1 次对话不做完整结果页，但要能跳转到一个**临时的基础结果页**：

- URL：`/search?q=xxx`
- 显示搜索词
- 调用 API
- 展示结果为简单卡片列表（不做精致设计，第 2 次对话再做）
- 每张卡片可点击跳转到详情页（404，第 2 次再做）

目的：让第 1 次对话结束时有完整的 "搜索体验闭环"——能搜索，能看到结果。

### 第 1 次对话交付物

- ✅ 项目结构完整
- ✅ FastAPI 后端运行在 localhost:8000
- ✅ 所有核心 API 端点可调用
- ✅ LLM 映射生成可用（带缓存）
- ✅ 首页完整，带引导流程
- ✅ 可以搜索并看到基础结果列表
- ❌ 结果页视觉未打磨
- ❌ 详情页不存在
- ❌ 关于页、404 页不存在
- ❌ 未部署

---

## 第 2 次对话：结果页 + 详情页 + 辅助页面

**目标**：所有页面完整，本地跑通完整流程。

### 2.1 搜索结果页（120 分钟）

**顶部结构揭示区**（高度 280px）
- 左侧：用户的查询 + 识别到的数学结构名称 + 公式 + 一句话解释
- 右侧：匹配结果摘要（前 3 个）
- 中间：动态连接线动画（SVG）

**中部结果列表**（主内容区）
- 卡片列表，每张卡片 16px 内边距
- 包含：现象名、领域、描述、相似度、结构类型
- **核心差异化**：每张卡片下方有"参数对照表"
- 点击整张卡片进入详情页

**右侧筛选/排序**（sidebar）
- 按相似度排序 / 按领域筛选
- 展示结果分布统计

**空状态**
- 无结果：展示"没找到"插图 + 建议

### 2.2 现象详情页（150 分钟）

按照 PM2 的完整设计实现：

1. **Hero 模块**：双现象头部 + 相似度 + 结构名
2. **结构映射可视化**：左右对照表 + SVG 连线 + hover 交互
3. **数学结构卡片**：折叠式，含人话、可视化、公式三层
4. **行动建议（借用答案）**：源领域解法 → 翻译后建议
5. **相关现象**：同结构的其他现象卡片

LLM 实时生成内容（带 loading 骨架屏）：
- 首次访问：显示骨架屏 → LLM 生成 → 写入缓存 → 展示
- 再次访问：直接从缓存读取，秒开

### 2.3 辅助页面（60 分钟）

**关于页**（/about）
- 产品介绍（1 段话）
- 团队信息
- 论文链接
- GitHub 链接
- 联系方式

**404 页**
- 精致的 404 插图（用 SVG）
- 幽默但不过火的文案："这个现象还没有被收录。"
- 返回首页按钮

**加载状态**
- 全局骨架屏组件
- 结果页骨架、详情页骨架、卡片骨架

**错误状态**
- API 失败：温和的重试提示
- 网络错误：顶部滑出灰色 toast

### 2.4 全局导航（30 分钟）

- 极简顶栏：Logo + 搜索入口 + 关于 + GitHub
- 详情页增加面包屑：首页 / 搜索: xxx / 现象名

### 第 2 次对话交付物

- ✅ 所有页面功能完整
- ✅ 所有错误状态处理
- ✅ 本地 E2E 流程跑通
- ❌ 视觉细节未完全打磨（动效、微交互）
- ❌ 响应式适配未完全
- ❌ 未部署

---

## 第 3 次对话：打磨 + 部署

**目标**：上线 beta.structural.bytedance.city，所有细节到位。

### 3.1 视觉细节打磨（120 分钟）

- 所有动效的缓动曲线精调
- 页面进入动画的 stagger 时序
- Hover 状态的微交互
- 字体加载优化（font-display: swap + 预加载）
- 图标系统统一（所有 SVG 线宽 1.5px，尺寸 20px）
- 暗色模式（可选，如果时间允许）

### 3.2 响应式适配（90 分钟）

- 桌面 (>1024px)：完整体验
- 平板 (768-1024px)：布局调整，详情页从左右变上下
- 手机 (<768px)：
  - 搜索框全宽
  - 示例 chips 变纵向
  - 详情页的结构映射从左右并排变上下堆叠
  - 顶栏简化

### 3.3 性能优化（30 分钟）

- 首屏 CSS inline
- 非关键 JS 延迟加载
- API 响应 gzip
- 图标用 inline SVG 而非图片
- LLM 映射的预计算（上线前预生成 top 30 对）

### 3.4 SEO 和 meta（30 分钟）

- 每个页面的 title 和 description
- OG meta tags（分享卡片）
- robots.txt
- sitemap.xml

### 3.5 部署到 VPS（60 分钟）

- 推送代码到 VPS `/root/Projects/structural-isomorphism/web/`
- 安装 Python 依赖
- 创建 systemd 服务：`structural-web.service`
  - ExecStart: uvicorn backend.main:app --host 127.0.0.1 --port 5004
  - Restart=always
- 配置 Nginx：
  - `beta.structural.bytedance.city` → proxy_pass 127.0.0.1:5004
  - SSL: `certbot --nginx -d beta.structural.bytedance.city`
- DNSPod 添加 A 记录：beta.structural → VPS IP
- 注册到 VPS 项目注册表（CLAUDE.md）

### 3.6 上线前检查清单（30 分钟）

- [ ] 所有页面在 Chrome/Safari/Firefox 打开正常
- [ ] 手机浏览器打开正常
- [ ] 搜索、详情、引导全流程可用
- [ ] 错误状态全覆盖
- [ ] 键盘导航可用
- [ ] 404 页面正常
- [ ] SSL 证书有效
- [ ] 首屏加载 < 2 秒
- [ ] 写入 AI Monitor 项目卡片
- [ ] 更新 ~/progress.md

### 第 3 次对话交付物

- ✅ beta.structural.bytedance.city 上线
- ✅ 手机/电脑都能流畅使用
- ✅ 所有细节打磨完成
- ✅ 写入项目注册表
- ✅ 可以直接演示给梁文锋

---

## 关键决策锁定

| 项 | 决策 |
|---|------|
| 域名 | beta.structural.bytedance.city |
| 知识库 | 4475 条 (kb-5000-merged.jsonl) |
| 视觉参考 | Linear + Perplexity |
| 字体 | Inter + Noto Serif SC + JetBrains Mono |
| 主色 | #FAFAF9 背景 / #18181B 文字 / #2563EB 强调 |
| 引导 | 3 步（跳过保底） |
| LLM | OpenRouter + Claude Sonnet / GPT-4 |
| 缓存 | JSONL 文件缓存 mapping |
| 部署 | FastAPI + systemd + Nginx |
| 完成标志 | 手机打开流畅，可演示 |

---

## 风险和缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| LLM 生成质量差 | 中 | 调 Prompt + 固定用 Claude Opus 4.6 |
| 模型加载慢 (4475 条 encoding) | 高 | 启动时预加载，首次启动等待 30s |
| Nginx 配置错 | 中 | 参考 ai-monitor 现有配置 |
| 前端视觉不够"高级" | 中 | 严格对标 Linear 官网，逐像素对齐 |
| 移动端适配问题 | 中 | 第 3 次对话专门做，不要中间做 |

---

> 下一步：用户确认此 plan → 进入第 1 次对话开工
