# beta.structural.bytedance.city 前端修复报告

日期: 2026-04-13
目标: 修复 P0/P1 级 review 发现
部署路径: `/root/Projects/structural-isomorphism/web/frontend/`（Nginx 静态，无需重启）

## 已修复

### P0
1. **4475 → 4,443**（index.html:54,121；about.html:68,72）
2. **19 → 39 个 A 级发现**（index.html:223；discoveries.html:8 meta + 56 hero）
3. **Demo query 清理**：index.html:177 `团队规模变大后效率反而下降` → `为什么市场会崩盘`；同步更新 assets/js/home.js:82 PLACEHOLDER_TEXTS
4. **/phenomenon 无 id**：phenomenon.js:771 在 `else` 分支调用 `window.location.replace('/')`
5. **/phenomenon/{fake-id} 404**：phenomenon.js:744 catch 块检测 `API 404` 错误消息，渲染与 /404.html 一致的空状态（大号 "404" + "这个现象还没有被收录" + 返回首页 CTA）

### P1
6. **favicon.svg**: 新建 `assets/icons/favicon.svg`（S 字母圆圈 logo），7 个 HTML 文件全部加 `<link rel="icon" type="image/svg+xml">`
7. **og-image**: 新建 `assets/og-image.svg`，用 VPS 上 `rsvg-convert -w 1200 -h 630` 生成 `og-image.png`（36 KB）。analyze.html 已有引用，其他 6 个 HTML 同步补 OG tags
8. **统一 footer**: 6 个页面 + analyze.html（原本无 footer）+ 404.html 现在共享同一 footer：主站 / 关于 / 论文 / GitHub (dada8899/structural-isomorphism) / HuggingFace (qinghuiwan/structural-isomorphism-v3-structtuple) / Zenodo (10.5281/zenodo.19557847)
9. **meta description + OG**: search/phenomenon/about/404 四页全部补齐 description + og:title/description/image + twitter card
10. **beta 徽章**: common.css 新增 `.beta-badge` class（小号、弱色、圆角、border），7 个 HTML 文件 logo 旁加 `<span class="beta-badge">beta</span>`
11. **dead CSS 清理**: search.css 删除 21 行 `.search-bar` 相关规则（评审说 ~80 行，实际只有 21 行；从未被 HTML 使用）

## 跳过

无。所有 11 项均已完成。

## 线上验证

`curl` 抓取线上页面确认以下均已生效：
- index.html: 4,443 / 39 个 / beta-badge / favicon 全部存在
- about.html: 4,443 两处全部生效
- discoveries.html: 39 条 / 39 个
- phenomenon.js: `window.location.replace('/')` + `isNotFound` 分支 + "这个现象还没有被收录" 全部线上可见
- /assets/icons/favicon.svg → HTTP 200
- /assets/og-image.png → HTTP 200
- search.html footer 含 Zenodo、HuggingFace、structural-isomorphism 链接

## 说明

- 无需重启服务（Nginx 直接服务静态文件）
- 所有编辑在本地 /tmp/si-frontend 完成，通过 rsync 一次性同步到 VPS
- shared/ 目录为空，未找到其他 placeholder 文案需要修复
- 4475 动态化（通过 `/api/health`）未实施；直接硬编码为 4,443（与 review 提示一致），未来若再变再迁移
