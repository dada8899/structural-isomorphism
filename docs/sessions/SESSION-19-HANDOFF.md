# Session #19 Handoff

> 从 SESSION-18-OUTCOME.md 承接。本 session 完成了 B 飞轮深化 + UX 全面打磨 + 
> 开始部署，但部署时踩到 VPS Python 3.11 兼容性 bug，服务崩溃，网站目前 502。
> **起手第一件事：提交修复 + 重新部署。**

---

## 0. 当前状态（网站 502）

**根因**：`stress_test.py` 和 `diagnose.py` 含 `from __future__ import annotations`，
在 VPS Python 3.11 + Pydantic 2.6.1 下导致 `PydanticUndefinedAnnotation: name 'StressTestRequest' is not defined`，
服务崩溃重启循环 → nginx 502。

**修复已写好，在 working tree，未提交**：
- `web/backend/api/stress_test.py` — 删除了第 10 行 `from __future__ import annotations`
- `web/backend/api/diagnose.py` — 删除了第 13 行 `from __future__ import annotations`

**起手三步**：
```bash
cd ~/Projects/structural-isomorphism
git add web/backend/api/stress_test.py web/backend/api/diagnose.py
git commit -m "fix(backend): remove __future__ annotations from stress_test + diagnose (Python 3.11 Pydantic compat)"
git push origin main
gh workflow run "Deploy Beta Backend" --ref main
```

然后等 ~2 分钟，验证：
```bash
curl -s https://beta.structural.bytedance.city/api/version
curl -s https://beta.structural.bytedance.city/api/health
```

---

## 1. Session #19 完成的内容

### B 飞轮 — 人工验证闭环（已提交 d88597b）

- `report_store.py`: `count_human_verified(b_id)` — indexed JOIN 统计"used it, it worked"用户数
- `verified_isomorphisms.py`: `human_verified_for(store, b_id)` wrapper，降级返回 `{count: 0}`
- `analyze.py`: credibility 块新增 `human_verified_count` / `human_verified_recent` 字段
- `analyze.js`: `renderCredibilityBadge()` 在 count>0 时显示绿色"✓ N人验证这个跨域迁移真的有效"chip
- `analyze.css`: `.cred-badge__chip--human` success-green 样式
- `test_flywheel_feedback.py`: 10 个新测试

### UX 全面打磨（已提交 e629857）

9 个工具页面全部深化（discoveries / classes / insights / whitespace / lint + tools hub + apply / stress-test / diagnose 的 CSS 细节）：
- 信息层级更清晰，空状态更友好，mobile 适配更好
- e2e 修复：`sync_playwright` 在 asyncio loop 里 → 改用 conftest `page` fixture；
  `networkidle` → `domcontentloaded`（plausible analytics 脚本会阻塞 networkidle）；
  insights browser 测试 timeout 延长

### 测试覆盖

- 后端：713 passed（baseline 501 → +212）
- Education e2e：8/8 ✓
- Whitespace e2e：5/5 ✓
- Insights e2e：12/12 ✓（含 browser 测试）

---

## 2. 部署后待办

| 优先级 | 动作 | 说明 |
|---|---|---|
| 🔴 P0 | 修 502（见上） | 提交两行删除 + redeploy |
| 🔴 P0 | 轮换 OpenRouter API key | 旧 key 曾在 public repo 泄露（#17 起未办） |
| 🟡 | 部署后跑 whitespace LLM 预计算 | `OPENROUTER_API_KEY=... python scripts/build_whitespace_matrix.py --llm`，约 400+ LLM 调用，一次性 |
| 🟡 | 部署后跑 `@post_deploy` e2e | `STRUCTURAL_BASE=https://beta.structural.bytedance.city PHASE_BASE=https://beta.structural.bytedance.city .venv/bin/python -m pytest web/tests/e2e/ -k "post_deploy" -v` |
| 🟢 | G 方向：连接人 | 独立立项，设计文档在 `docs/sessions/SESSION-18-G-connect-people-design.md` |

---

## 3. Git 状态

```
本地 ahead/behind: 0 / 0（已全部 push）
最近 commit:
  e629857  feat(frontend): session #18 UX deepening — all 9 tool pages polished
  d88597b  feat(backend,frontend): session #18 B — flywheel feedback closes credibility loop
  3c3eeb1  docs(sessions): session #18 outcome — A-G shipped, deploy pending

working tree 剩余未提交:
  M scripts/train_v2.py       ← 不是本 session 的，留着不动
  M web/backend/api/stress_test.py   ← 本 session 的修复，下个 session 第一件事提交
  M web/backend/api/diagnose.py      ← 同上
```

---

## 4. 架构速查

| 层 | 位置 | 说明 |
|---|---|---|
| 后端 | `web/backend/main.py` | FastAPI + 14 个 router，port 5004（prod），8000（local） |
| KB 引擎 | `web/backend/services/search_service.py` | 4443 现象，BM25+embedding，通过 `app_state["search"]` 注入 |
| LLM 客户端 | `web/backend/services/llm_client.py` | OpenRouter，default deepseek/deepseek-chat:nitro |
| 数据飞轮 | `web/backend/services/report_store.py` + `verified_isomorphisms.py` | SQLite history.db，human_verified 统计 |
| 前端 | `web/frontend/` | 纯 HTML/JS/CSS，FastAPI FileResponse 托管 |
| MCP | `mcp/server.py` | 4 tools via FastMCP |
| 测试 | `web/backend/tests/`（713）+ `web/tests/e2e/` | pytest + Playwright |
| VPS | root@43.156.233.71 | structural-web.service，venv: Python 3.11 + Pydantic 2.6.1 |
| Git repo on VPS | `/root/Projects/structural-isomorphism-v4/` | deploy 从这里 rsync 到 `/root/Projects/structural-isomorphism/` |

---

## 5. 起手指令（下个 session）

```
读 SESSION-19-HANDOFF.md，立刻提交两文件修复 + push + 触发 Deploy Beta Backend。
等部署完成后跑 fingerprint check + post_deploy e2e。
然后可以继续深化或转向 G 方向。
```
