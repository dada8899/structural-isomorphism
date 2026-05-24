# Session #7 e2e Baseline — Wave 3 W3-A

**Date**: 2026-05-14
**Agent**: Wave 3 Agent A (e2e + screenshots)
**Branch**: `session7/e2e-playwright`
**Phase**: Pre-deploy baseline (W3-C 部署新 /index.html 之前)

## 目标

1. 写完整 Playwright e2e 测试代码覆盖 Perplexity-like 搜索引擎流程
2. 跑一次 baseline 截图作为 PRE-DEPLOY 控制组
3. 等 W3-C 部署后 W3-B / 主 session 跑 post-deploy 对比

## 部署阶段说明

| 阶段 | 时间 | prod 状态 |
|------|------|----------|
| **Baseline (本次)** | 2026-05-14 | session #5 末状态。新 `/index.html` / `ask.css` / `ask.js` 未部署 |
| **Post-deploy** | W3-C 完成后 | 新 Perplexity-like home + `/learn` legacy backup |

## 测试套件

### 文件清单

| 文件 | 用途 |
|------|------|
| `web/tests/e2e/conftest.py` | Playwright fixtures (session-scoped instance, per-test page) |
| `web/tests/e2e/test_perplexity_search.py` | 11 个测试 (5 post_deploy + 6 regression-safety) |
| `web/tests/e2e/screenshot_baseline.py` | 8 个 viewport 全页截图脚本 |
| `web/tests/e2e/smoke_curl.py` | Playwright 不可用时的降级方案 (urllib-only) |
| `web/tests/e2e/pytest.ini` | 注册 `post_deploy` mark |

### 测试分类

**Regression-safety (6 个，baseline 必须 PASS)**：
- `test_home_returns_200` — / 返回 200
- `test_search_html_reachable` — /search.html 服务器可达 (200/3xx/404 都可接受)
- `test_analyze_html_reachable` — /analyze.html 同上
- `test_mobile_375_no_horizontal_scroll` — 375px 视口横向滚动 ≤ +80px (baseline 阈值)
- `test_phase_detector_loads` — phase.bytedance.city 返回 200
- `test_legacy_structural_site_loads` — structural.bytedance.city 返回 200

**Post-deploy (5 个，等 W3-C 后跑)**：
- `test_home_loads_perplexity_layout` — `.ask-searchbox` + `.ask-empty__examples-chips` + 3+ chips
- `test_home_brand_h1` — `.ask-empty__brand` 文本 = "Structural"
- `test_submit_query_shows_thread` — 提交后切换到 `.ask-thread`
- `test_deep_link_q_auto_runs` — `?q=...` 自动运行
- `test_learn_page_loads` — `/learn` 是 legacy backup，含 `[href="/"]` 链接

## Baseline 测试结果

```
6 passed, 5 deselected (post_deploy) in 11.90s
```

全部 regression-safety 测试通过.

### 真实发现（Baseline informational）

1. **`/learn` 404**：session #5 末状态 prod 上 `/learn` 不存在。W3-C 部署新 `/index.html` 时必须同时建 `/learn` 作为 legacy backup（指引文档已要求）
2. **`/search.html` 404**：旧 search 入口已被早期清理。新 Perplexity-like home 替换它
3. **`/analyze.html` 404**：同上
4. **Mobile 375px 横向溢出 ≈ 448px**：当前 prod home (session #5 layout) 在 mobile viewport 下 scrollWidth=448 > clientWidth=375. Baseline 阈值放宽到 +80px (PASS)，post-deploy 必须收紧到 +5px

## Baseline 截图

`docs/screenshots/session-7/baseline/` — 8/8 截图成功:

| 文件 | 描述 | 大小 |
|------|------|------|
| `home-desktop.png` | beta home 1280x800 | 542 KB |
| `home-mobile.png` | beta home 375x812 | 457 KB |
| `search-desktop.png` | /search.html (404 page) | 58 KB |
| `analyze-desktop.png` | /analyze.html (404 page) | 58 KB |
| `discoveries-desktop.png` | /discoveries (live) | 798 KB |
| `learn-desktop.png` | /learn (404 page) | 58 KB |
| `phase-desktop.png` | phase.bytedance.city home | 366 KB |
| `legacy-structural-desktop.png` | structural.bytedance.city home | 151 KB |

3 个 58KB 文件 = 404 页面（相同 nginx default），符合预期.

## 复跑指令

### 安装环境（本地）

```bash
cd /Users/dadamini/Projects/structural-isomorphism
python3 -m venv .venv-e2e
source .venv-e2e/bin/activate
pip install playwright pytest pytest-playwright
playwright install chromium
```

### 跑 baseline 测试

```bash
source .venv-e2e/bin/activate
python3 -m pytest web/tests/e2e/test_perplexity_search.py -v -k "not post_deploy" -c web/tests/e2e/pytest.ini
```

### 跑 post-deploy 测试（W3-C 部署后）

```bash
source .venv-e2e/bin/activate
python3 -m pytest web/tests/e2e/test_perplexity_search.py -v -c web/tests/e2e/pytest.ini  # 跑全部，包括 post_deploy
```

### 抓 post-deploy 截图

```bash
# 修改 screenshot_baseline.py 中 OUTPUT 为 docs/screenshots/session-7/post-deploy/
# 或者新建 screenshot_postdeploy.py 复用同样的 PAGES 列表
source .venv-e2e/bin/activate
python3 web/tests/e2e/screenshot_baseline.py
```

### Curl-only 降级

```bash
python3 web/tests/e2e/smoke_curl.py  # 无依赖，CI 兜底
```

## Post-deploy 收紧 TODO（W3-B 或主 session）

1. `test_mobile_375_no_horizontal_scroll` 阈值 80 → 5
2. `test_search_html_reachable` / `test_analyze_html_reachable` 改成期望 200 (如 W3-C 保留这些 path 作 backward compat) 或维持现状 (如显式废弃)
3. 跑全部 11 个测试，包括 5 个 `post_deploy` 标记的
4. 抓 post-deploy 截图存到 `docs/screenshots/session-7/post-deploy/`，与 baseline 并排比对

## 约束遵守

- prod 站点 read-only — 仅 GET 测试，不写
- worktree 隔离：`/tmp/si-e2e` 独立分支 `session7/e2e-playwright`
- commit boundary：仅 commit 本任务直接产生文件（`web/tests/e2e/` + `docs/screenshots/session-7/baseline/` + 本报告）
