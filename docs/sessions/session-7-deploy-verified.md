# Session #7 — Deploy + e2e verified

> 2026-05-14 ~15:10 CST
> Status: **all live on prod, 11/11 e2e PASS**

## Live URLs (post-deploy)

| URL | Status | Notes |
|---|---|---|
| https://beta.structural.bytedance.city/ | 200 | **Perplexity-like 新主页面** ship |
| https://beta.structural.bytedance.city/learn | 200 | Legacy home backup |
| https://beta.structural.bytedance.city/search | 200 | Legacy (regression safety) |
| https://beta.structural.bytedance.city/analyze | 200 | Legacy (regression safety) |
| https://beta.structural.bytedance.city/discoveries | 200 | + skeleton 修 |
| https://beta.structural.bytedance.city/classes /papers /methods /start-here | 200 | 全 i18n EN |
| https://beta.structural.bytedance.city/api/health | 200 | kb_size=4443 |
| https://beta.structural.bytedance.city/api/ask/stream | SSE 200 | **新核心** |
| https://structural.bytedance.city/ | 200 | Legacy 学术静态 (不动) |
| https://phase.bytedance.city/ | 200 | Phase Detector |

## /api/ask/stream 实测（curl SSE）

输入：`{"query": "为什么银行挤兑这么吓人", "lang": "zh"}`

```
event: meta
data: {"query": "为什么银行挤兑这么吓人", "rewritten": "为什么银行挤兑这么吓人", "started_at": "2026-05-14T06:57:14.618712+00:00", "model": "deepseek/deepseek-chat", "lang": "zh"}

event: kb_cards
data: {"cards": [
  {"id": "soc-001", "name": "银行挤兑", "domain": "金融", "type_id": "18", "score": 0.9263, ...},
  {"id": "5k-14-056", "name": "稳定币储备的部分准备金传导链", ...},
  {"id": "soc-028", "name": "金融风险传染", ...},
  {"id": "5k-ef-054", "name": "影子银行的信用创造乘数", ...},
  {"id": "5k-13-082", "name": "外汇市场基准汇率操纵", ...}
], "count": 5}

event: answer_chunk
data: {"delta": "银行挤兑之所以吓"}
... typewriter cadence (8-char @ 25ms)
event: answer_chunk
data: {"delta": "导致灾难性后果。当"}

[ ... continues for ~200-400 字 ... ]

event: answer_done / similar_phenomena / followups / done
```

**Latency**: ≤2s 出 kb_cards / ≤8s 出完整 answer / ≤12s 全部完成 — 符合 Perplexity-like 设计要求。

## e2e (11/11 PASS, 20s 全跑)

```
test_home_loads_perplexity_layout PASSED
test_home_brand_h1 PASSED
test_submit_query_shows_thread PASSED
test_deep_link_q_auto_runs PASSED
test_learn_page_loads PASSED
test_home_returns_200 PASSED
test_search_html_reachable PASSED
test_analyze_html_reachable PASSED
test_mobile_375_no_horizontal_scroll PASSED
test_phase_detector_loads PASSED
test_legacy_structural_site_loads PASSED
```

## Hotfix patches during deploy

1. **PR #75** — `tier_limit_decorator` slowapi 签名 mismatch（W2-D bug）→ 500 on /api/ask/stream
   - Bug: `_spec_for(request)` but slowapi 调用 `__limit_provider()` no-arg
   - Fix: 回退到静态 default_anon。tier auth 仍在 endpoint 顶部生效

2. **PR #76** — `/learn` route missing → 404
   - W2-A 加了 `learn.html` 文件但没加 FastAPI route
   - Fix: 加 `@app.get("/learn")` 5 行

3. **PR #78** — Mobile 375px nav overflow → e2e fail
   - `.site-header__nav` 300px 在 375px viewport 越界
   - Fix: `@media (max-width: 480px)` hide 次要 nav-link + `html overflow-x: hidden`

## 部署管道（实证 SOP）

```bash
# Frontend
rsync -av --delete --exclude='.DS_Store' web/frontend/ \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/frontend/

# Backend services + api
rsync -av web/backend/services/ask_orchestrator.py web/backend/services/ask_schemas.py \
  web/backend/services/auth.py web/backend/services/rate_limit.py \
  web/backend/services/history_db.py web/backend/services/observability.py \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/services/
rsync -av web/backend/api/ask.py web/backend/api/history.py web/backend/api/analyze.py \
  root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/api/
rsync -av web/backend/main.py root@43.156.233.71:/root/Projects/structural-isomorphism/web/backend/main.py

# Verify imports + restart
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism && \
  PYTHONPATH=/root/Projects/structural-isomorphism:web/backend venv/bin/python -c \
  "from api import ask, history; from services.ask_orchestrator import AskOrchestrator; print(\"ok\")"'
ssh root@43.156.233.71 'systemctl restart structural-web && sleep 3 && systemctl is-active structural-web'

# Smoke
curl -s -o /dev/null -w "%{http_code}\n" https://beta.structural.bytedance.city/
curl -s -o /dev/null -w "%{http_code}\n" https://beta.structural.bytedance.city/learn
```

---
