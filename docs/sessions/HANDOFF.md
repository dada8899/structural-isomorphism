***REMOVED*** structural-isomorphism · Next-session HANDOFF

> 永久 entry point。**下个 session 起手第一件事：读本文件**。
> Session-N 收尾后更新这个文件指向最新 sprint。历史 retro 在 `docs/sessions/structural-iso-session-N-end.md`。

---

***REMOVED******REMOVED*** 0. 起手 60 秒

```bash
cd ~/Projects/structural-isomorphism/
git pull origin main                        ***REMOVED*** 同步最新
git log --oneline -5                        ***REMOVED*** 确认 head = session 2 PR merge commit
source .venv/bin/activate                   ***REMOVED*** Python 3.14 + numpy/scipy/pandas/powerlaw/matplotlib/pytest
PYTHONPATH=v4/lib python -c "from soc_pipeline import fit_clauset_powerlaw; print('soc lib ok')"
PYTHONPATH=v4/lib python -c "from llm_guardrail import guardrailed_llm_call; print('guardrail ok')"
python v4/cli.py status                     ***REMOVED*** 应打印 13 phases + verdicts
.venv/bin/python -m pytest v4/tests/sanity -m sanity -q   ***REMOVED*** 38 passing in ~3.6s
```

读完这 5 个文件即可上手：
1. **本文件** (HANDOFF.md)
2. **`docs/sessions/SESSION-8-STARTER.md`** — 🔥 session ***REMOVED***8 直接执行清单（session ***REMOVED***7 收尾 + P0/P1/P2 队列）
3. `docs/sessions/SESSION-7-end.md` — session ***REMOVED***7 retrospective（5 directions + Perplexity-like ship）
4. `docs/sessions/session-7-deploy-verified.md` — 部署 SOP + 实证 SSE event log + 11/11 e2e pass
5. `paper/v0-unified-pipeline-2026-05-13.md` v0.3.1 — C1 unified preprint
6. `CLAUDE.md` (repo root) — 项目级 CC 指引

---

***REMOVED******REMOVED*** 1. 当前状态 (2026-05-14 session ***REMOVED***7 截止 + post-deploy scale)

- **Main HEAD**: `75c6908` (PR ***REMOVED***83 merged) — **20 PRs in session ***REMOVED***7** (***REMOVED***64-***REMOVED***83)
- **Git tag**: `v0.4.0`
- **Production live + 11/11 e2e PASS**:
  - https://beta.structural.bytedance.city/ — **Perplexity-like 真搜索引擎 (session ***REMOVED***7 北极星 ship)**: 输入复杂问题 → SSE 流式 answer + 5 KB cards + 3 similar phenomena + 3 followups + deep-analysis CTA
  - https://beta.structural.bytedance.city/learn — Legacy home backup（marketing + SEO 保留）
  - https://beta.structural.bytedance.city/search /analyze /discoveries /classes /papers /methods /start-here — 全部 200，i18n EN 100%
  - https://structural.bytedance.city/ — Legacy 学术静态（不动）
  - https://phase.bytedance.city/ — Phase Detector

***REMOVED******REMOVED******REMOVED*** Session ***REMOVED***7 主要交付 (5 directions + post-deploy scale)

| Direction | Status | Key artifact |
|---|---|---|
| *****REMOVED***6 Perplexity-like 真搜索引擎** | ✅ Live | POST /api/ask/stream SSE + new /index.html + ask.js (574 LOC) + ask.css (705 LOC) |
| *****REMOVED***1 Phase Detector** | ✅ Full | **500/500 ticker StructTuple full SP500** + backtest engine v0.1 + 9 pytest |
| *****REMOVED***2 UX 第三轮** | ✅ Live | mobile fix + Plausible 14 events + /discoveries skeleton + glossary v2 (5 新词) |
| *****REMOVED***3 科学纵深** | ✅ Full | 3 pre-reg yaml + **B4 full 21 classes (8 AGREE / 13 DIFFER = 62% disagree vs B3)** + **35/35 taxonomy yaml expanded** + **CVE FAIL** (α=2.668 outside band) + **NYC FDNY INCONCLUSIVE** (α=1.739 in band but lognormal/exp beat — finite cutoff hypothesis) + CVE paper draft v0.1 |
| *****REMOVED***4 工程平台** | ✅ Live | GitHub Actions CI + history SQLite + observability + auth tier middleware + i18n EN 100% (244/244) + 30 backend tests pass |

***REMOVED******REMOVED******REMOVED*** Session ***REMOVED***7 PR 表

| PR | Title | Commit |
|---|---|---|
| ***REMOVED***64 | SESSION-7-PLAN master plan | f3e9c92 |
| ***REMOVED***65 | POST /api/ask/stream SSE orchestrator (W1-A) | f29c85b |
| ***REMOVED***67 | CI workflows + history SQLite + observability (W1-D) | 0529b68 |
| ***REMOVED***68 | Phase Detector 100→500 + batch extract (W1-B) | db68684 |
| ***REMOVED***69 | Pre-registration + B4 ensemble + taxonomy expand infra (W1-C) | 34f2a81 |
| ***REMOVED***70 | Perplexity-like /index.html (W2-A) | 2566c39 |
| ***REMOVED***71 | Backtest engine v0.1 (W2-B) | 8b2fc68 |
| ***REMOVED***72 | API auth + history remote + i18n EN (W2-D) | 42888c0 |
| ***REMOVED***73 | B4 ensemble run + CVE preregister FAIL (W2-C) | 53b0f32 |
| ***REMOVED***74 | Playwright e2e + baseline screenshots (W3-A) | 9d2942f |
| ***REMOVED***75 | fix: tier_limit_decorator slowapi signature (hotfix) | e439aeb |
| ***REMOVED***76 | feat: /learn route (hotfix) | 7ce45dd |
| ***REMOVED***77 | UX 3rd round mobile + Plausible + glossary v2 (W3-B) | bcf10e4 |
| ***REMOVED***78 | fix: mobile ≤480px nav overflow (hotfix) | 70ce543 |
| ***REMOVED***79 | docs: deploy verified + screenshots | 98c8d5f |
- **UX 多维度打分**: 84.4% → 88-90% 预计 (+4-6 pts)
- **关键能力 shipped (session ***REMOVED***5)**: TL;DR 卡片 / synthesize SSE 流式 / shared brand tokens 中心化 / GlossaryTooltip / instant search cards / 4 处 layout-shift 兜底 / analyze loading 噪音降低

***REMOVED******REMOVED******REMOVED*** Session ***REMOVED***5 累计 PR 表

| PR | 主题 |
|---|---|
| ***REMOVED***54 | TL;DR card + /synthesize SSE + footer "HuggingFace 数据集" |
| ***REMOVED***55 | shared brand tokens (web/shared/tokens.css 5-var) + SSE markdown fence-strip |
| ***REMOVED***56 | StatsBar skeleton — kill "正在加载统计…" flash |
| ***REMOVED***57 | GlossaryTooltip — 7 jargon hover 解释 (auto-wrap) |
| ***REMOVED***58 | /search 立即出卡，不等 synth |
| ***REMOVED***59 | daily-grid skeleton + sector dropdown disabled-while-loading |
| ***REMOVED***60 | hero-evidence__desc line-clamp:3 + min-height |
| ***REMOVED***61 | /analyze 在 meta arrival 隐藏 loading block |
| ***REMOVED***62 | 修 PR-8 在 error/retry 路径的 regression |

***REMOVED******REMOVED******REMOVED*** 历史 — Session ***REMOVED***4 累计 PR 表

| PR | 主题 |
|---|---|
| ***REMOVED***46 | W6-D abstract + CITATION rebrand + README placeholder |
| ***REMOVED***47 | 全站 copy sweep — V1-V4 sprawl 全清 |
| ***REMOVED***48 | History sidebar — Structural |
| ***REMOVED***49 | Phase Detector SearchHero + parse-query NLU |
| ***REMOVED***50 | History sidebar — Phase Detector |
| ***REMOVED***51 | Cross-link symmetry polish |
| ***REMOVED***52 | 关键修复：Phase filter enum + /start-here 404 + 研究报告卡片删 + cross-link 域名 + analyze breadcrumb + 流式 typewriter |
| ***REMOVED***53 | docs(sessions): SESSION-5-STARTER + HANDOFF update |

---

***REMOVED******REMOVED*** 历史状态 (2026-05-13 session ***REMOVED***3 截止)

***REMOVED******REMOVED******REMOVED*** Session ***REMOVED***3 close 状态 (2026-05-14 close, post F1 P1 fixes)

**main HEAD**: `0380327` (F1 P1 fix merge) — 42 PRs merged 自 session ***REMOVED***2 base `332049b` 起。

**Session ***REMOVED***4 唯一第一件事：读 `docs/sessions/SESSION-4-STARTER.md` + 按 §2 顺序跑**。该文档涵盖：
- 凭证清单（PYPI_TOKEN / ZENODO_ACCESS_TOKEN / arXiv 账号 / gh CLI）
- Step 1-9 详细 runbook（每步 5-30 min，部分需 user 提供 token）
- 不可逆 step 的 rollback plan
- §5 验收标准（10 个 checkbox）

***REMOVED******REMOVED******REMOVED*** Session ***REMOVED***3 新增（基于 session ***REMOVED***2）

- **2 PyPI packages built (wheel ready, not yet published)**: `packages/soc-pipeline/` (1085 src + 37 tests + 5 notebooks) and `packages/guarded-llm/` (1624 src + 52 tests + 4 providers)
- **Zenodo dataset bundle ready**: `dataset/v1/` (244 files / 99 MB / 16 systems / 4 nulls / 35 yamls / MINT_DOI_RUNBOOK)
- **phase.bytedance.city LIVE** with HTTPS, 97 companies via /api/screener, 2 systemd units
- **Main site refreshed** with 5 new pages (papers / methods / taxonomy-v2 / start-here essay / featured preprint card)
- **C1 v0.3 preprint**: 16,109 words (v0.2 → v0.3 with Scheffer block-bootstrap actually run, §4.5 demoted, §7 FWER limitations, §8 adversarial pre-registration, §9 submission path)
- **6 paper drafts ready for arXiv** (C1 v0.3 + 4 solo + C4 red-team)
- **6-role review consolidated** (scholar / researcher / PM / student / UX / copywriter) → applied 5-agent fix wave
- **Tests expanded**: 98 → 213 (+117%), three-tier (unit + integration + e2e)
- **Scientific correction**: Scheffer A2 p-value revised from `< 10^-186` to `0.074` via block-bootstrap (Künsch 1989 method) — most important scientific honesty signal of session ***REMOVED***3

***REMOVED******REMOVED******REMOVED*** 当前 verdict summary (16 phases attempted in session ***REMOVED***3, 13 still canonical)

***REMOVED******REMOVED******REMOVED*** 已验证 universality systems：13 个（SOC × 9 + PA × 2 + Hysteresis × 1 + Scheffer × 1）

| Phase | 系统 | Class | α / 关键指标 | CI | n | paper | session |
|---|---|---|---|---|---|---|---|
| 1 | USGS earthquakes | SOC | b=1.084 | [1.073, 1.094] | 37k tail | ✓ | V4 L5 |
| 2 | S&P 500 returns | SOC | 2.998 | (n/a) | 9060 | ✓ | V4 L5 |
| 3 | DeFi Aave/Compound/Maker | SOC | 1.57-1.68 | (per-protocol) | 43k | ✓ | V4 L5 |
| 4 | Mouse cortex avalanches | SOC | 2.58 | [2.17, 3.00] | 1.39M spk | ✓ | V4 L5 |
| 5 | null validation (4/4 reject) | — | — | — | — | (footer) | V4 L5 |
| 6 | GitHub stars | PA | 2.867 | [2.781, 3.000] | 8398 | ✓ | ***REMOVED***1 |
| 8 | FDIC bank failures | SOC | 1.899 | [1.763, 2.047] | 3960 | ✓ | ***REMOVED***1 |
| 10 | NIFC wildfires | SOC | 1.660 | [1.381, 1.808] | 21k | ✓ | ***REMOVED***1 |
| 11 | GOES solar flares | SOC | 2.194 | [2.159, 2.248] | 29.9k | ✓ | ***REMOVED***1 |
| **7** | **Power grid cascades (MW)** | **Motter-Lai** | **2.018** | **[1.692, 2.307]** | **123 (40 tail)** | **✓** | *****REMOVED***2** |
| **12** | **Universal collapse (7 sys)** | **SOC meta** | shape-norm=1.11 | (excellent) | (composite) | **✓** | *****REMOVED***2** |
| **13** | **Wikipedia pageviews** | **PA** | **2.034** | **[1.854, 2.984]** | **7521 (2817 tail)** | **✓** | *****REMOVED***2** |
| **A2-1** | **NGSIM US-101 traffic** | **Hysteresis-Preisach** | ratio 0.926 + lit 1.375/1.385 | (composite) | 4538 cells | **✓** | *****REMOVED***2** |
| **A2-2** | **Fox River Green Bay DO** | **Scheffer fold** | AR(1) τ=+0.284 p=1e-186 | (rising) | 4732 obs | **✓** | *****REMOVED***2** |

**Session ***REMOVED***2 新增 5 个 verified phases + 1 universal-collapse polish。**

***REMOVED******REMOVED******REMOVED*** Taxonomy 状态 (B1 ⊗ B3 final)

- `v4/taxonomy/classes/*.yaml` — 24 类基础 schema (B4)
- `v4/results/layer3_critic.jsonl` — B1 critic (single Opus reviewer)
- `v4/results/B3_ensemble_review.jsonl` — B3 ensemble (3 × DeepSeek reviewers, 63 verdicts, 0 errors)
- `v4/results/B3_taxonomy_v2.jsonl` — B1 ⊗ B3 merged final taxonomy
- **B3 consensus**: KEEP=5 / REJECT=7 / SPLIT=5 / MERGE=4 (more conservative than B1 KEEP=11)
- Notable B3-driven demotions: `delay_differential_debt` / `hysteresis_preisach` / `scale_free_percolation` / `tail_copula_contagion` 都从 KEEP → REJECT（rigorous reviewer 抓 mechanism vs limit-theorem 混淆）

***REMOVED******REMOVED******REMOVED*** Git 状态

- main HEAD: session 2 PR merge commit (TBD pending merge — 11 commits on `v4/session2-mega-sprint`)
- 本 session 11 commits（C1 preprint / Phase 12 polish / E1 CLI / E3 tests / E4 guardrail / Phase 13 / Phase 7 / A2-Hysteresis / A2-Scheffer / D1 groundwork / B3 ensemble）
- 36525 lines net add，76 files changed

***REMOVED******REMOVED******REMOVED*** Site 状态

- `web/frontend/assets/data/universality-classes.json` 仍是 session ***REMOVED***1 的 8 verified predictions
- 5 个 session ***REMOVED***2 paper 还**未** copy 到 `web/frontend/assets/data/papers/`
- VPS 未同步（next session 处理）

***REMOVED******REMOVED******REMOVED*** Engineering 基础设施 (new in ***REMOVED***2)

- `v4/cli.py` — unified CLI（list/status/validate/collapse/calibrate/critic 6 subcommands）
- `v4/lib/llm_schemas.py + llm_guardrail.py` — 3-layer LLM JSON guardrail (E4)
- `v4/tests/sanity/*` — 38 deterministic regression tests (3.6s) covering 9 phases + soc_pipeline primitives + universal collapse + llm_guardrail
- `v4/product/d1_phase_detector/` — D1 MVP groundwork (schema + 100 companies + 5-sample DeepSeek run + cost projection $0.19 for full 100)

---

***REMOVED******REMOVED*** 2. 下个 sprint 优先级（session ***REMOVED***4，按 user authorization gate 排）

Session ***REMOVED***3 把几乎所有 engineering-side 工作做完。剩下都是需要 user 拍板的 irreversible/external actions。

***REMOVED******REMOVED******REMOVED*** P0 — Irreversible / external actions (waiting on user authorization)

1. **Rotate DeepSeek API key** — current key may be compromised in git history (W5-B P0). User runs rotation on console.deepseek.com.
2. **Scrub git history** — use BFG or git-filter-repo to remove old key references from past commits. Force push cleaned history. Coordinate before any clone-fork (no contributors yet so low blast radius).
3. **Flip repo to PUBLIC** — see `docs/PUBLIC_READINESS_CHECKLIST.md`. After P0 ***REMOVED***1 + ***REMOVED***2 done.
4. **Mint Zenodo DOI** for `dataset/v1/` bundle — bundle ready (244 files / 99 MB). Permanent DOI. Run `MINT_DOI_RUNBOOK.md`.
5. **arXiv submission** — submit C1 v0.3 unified pipeline preprint to `cond-mat.stat-mech` + `physics.data-an`. Coordinate with Zenodo DOI (paper references DOI).
6. **PyPI publish** — `soc-pipeline 0.1.0` + `guarded-llm 0.1.0`. Wheels built and tested.

***REMOVED******REMOVED******REMOVED*** P1 — Bug fixes (W6-E found)

7. ~~Fix `phase.bytedance.city` React error after networkidle~~ — **DONE in F1 (PR ***REMOVED***44, commit 0380327)**. Root causes: stale prod build (51 commits behind) + missing error boundaries + Next.js Server Action bot probe. Fix shipped: `app/error.tsx` + `app/global-error.tsx` + `lib/api.ts safeJson()` + VPS redeploy. E2E 9/10 pass + body asserted no "Application error".
8. ~~Fix `universality-classes.json` duplicate class_id~~ — **DONE in F1**. Preserved both valid Louvain sub-communities with `_v2` suffix on lower-rank dupes (no info loss). 23 entries all unique now.

***REMOVED******REMOVED******REMOVED*** P2 — Product growth (W7-D agenda)

9. **D1 expand 100 → 500 companies** — re-run extract_structtuple batch with new ticker list. Cost ~$1-2.
10. **Backtest engine v0.1** — historical StructTuple time series → "near_critical → 6mo return" backtest. Determines alpha-product vs narrative-product path.
11. **Weekly newsletter v1 send** — coordinate Buttondown account creation + first real send.

***REMOVED******REMOVED******REMOVED*** P3 — Continuing research (W7-A agenda)

12. **Adversarial pre-registration replication** — §8 of C1 v0.3 names 5 systems. Pre-register exponent bands BEFORE pulling data. Run 3 of 5.
13. **B4 cross-vendor ensemble** — replace 3-DeepSeek with Claude + GPT + DeepSeek + Kimi + GLM-5 heterogeneous critic. Rerun B3 verdicts.

***REMOVED******REMOVED******REMOVED*** Removed from list (done in session ***REMOVED***3)

- ~~D1 Phase Detector full ship~~ — DONE (Wave 3 + Wave 4 D)
- ~~Site refresh~~ — DONE (Wave 1 A + Wave 4 E)
- ~~Phase 14 Hawkes + A2 Copula + A2 SIR~~ — DONE (Wave 2)
- ~~C1 preprint v0.2 + v0.3~~ — DONE (Wave 1 B + Wave 6 C)
- ~~4 solo arXiv drafts~~ — DONE (Wave 3 E)
- ~~C4 red-team paper~~ — DONE (Wave 4 A)
- ~~Reproduction tutorial~~ — DONE (Wave 3 D)
- ~~B2 calibration / B4 yaml schema / F1 embedding / F2 active learning~~ — DONE (Wave 1-2 + Wave 4 C)

---

***REMOVED******REMOVED*** 3. 已知 blocker / 注意事项

***REMOVED******REMOVED******REMOVED*** 网络
- **OpenRouter Anthropic/Gemini CN region-block** — 已确认。所有 LLM 调用必须走 DeepSeek 直连（v4-pro + v4-flash, key in memory `reference_deepseek_direct_api_2026_05_06.md`）。session ***REMOVED***2 全程 OK，0 errors / 0 parse fails on 63 + 5 calls。
- **VPS SSH 22 transient** — 部署用重试或等 launchd 周期
- **DOE OE-417 portal TLS-handshake timeout** — Phase 7 用 literature meta + Wikipedia cross-val 替代；EIA API 也无 event-level disturbance endpoint
- **Reddit Pushshift 停服** — social cascade phase 替代源待研

***REMOVED******REMOVED******REMOVED*** Subagent
- **worktree isolation 限制**: 主 session CWD = `renai-cross`，操作 structural-isomorphism 时 subagent **不用 isolation**，给绝对路径，主 session harvest commit。
- **B3 长时 LLM 跑务必用 bash background**：直接 subagent 跑 63 个 LLM call 容易 "Monitor armed" 后未 wait 就退出。改用 `nohup python script &` 在主 session 起，poll JSONL 行数确认进度。

***REMOVED******REMOVED******REMOVED*** Commit
- main branch 直 push 被 sandbox 拒 — **必须走 PR**：feature branch + `gh pr create` + `gh pr merge --merge --delete-branch`. session ***REMOVED***1/***REMOVED***2 都按这条。
- session 内一次 commit 一个语义意图（一个 Wave deliverable），跨产品改动用 `renai` scope。

***REMOVED******REMOVED******REMOVED*** 数据
- `v4/validation/scheffer-lake/lake_do_timeseries.jsonl` 698KB，未 LFS（可接受）
- `v4/validation/hysteresis-traffic/us101_ngsim_agg_raw.csv` 较大，未 LFS
- session ***REMOVED***2 不引入新的 `.gitignore` 漏放（合理大小）

---

***REMOVED******REMOVED*** 4. Repo 结构速查（session ***REMOVED***2 之后）

```
~/Projects/structural-isomorphism/
├── .venv/
├── plans/
│   └── v4-next-roadmap-2026-05-13.md
├── paper/
│   └── v0-unified-pipeline-2026-05-13.md      ✨ session ***REMOVED***2 (C1)
├── v4/
│   ├── cli.py                                 ✨ session ***REMOVED***2 (E1)
│   ├── __init__.py                            ✨ session ***REMOVED***2
│   ├── lib/
│   │   ├── soc_pipeline.py
│   │   ├── llm_schemas.py                     ✨ session ***REMOVED***2 (E4)
│   │   └── llm_guardrail.py                   ✨ session ***REMOVED***2 (E4)
│   ├── validation/                            ***REMOVED*** 14 phase 目录
│   │   ├── soc-earthquake/ soc-stockmarket/ soc-defi/ soc-neural/
│   │   ├── soc-wildfire/ soc-solar/ soc-bank-failures/ soc-github-stars/
│   │   ├── null-controls/
│   │   ├── soc-universal-collapse/            ✨ session ***REMOVED***2 (Phase 12)
│   │   ├── soc-power-grid/                    ✨ session ***REMOVED***2 (Phase 7)
│   │   ├── soc-wikipedia-views/               ✨ session ***REMOVED***2 (Phase 13)
│   │   ├── hysteresis-traffic/                ✨ session ***REMOVED***2 (A2-Hysteresis)
│   │   └── scheffer-lake/                     ✨ session ***REMOVED***2 (A2-Scheffer)
│   ├── scripts/
│   │   ├── b3_ensemble.py                     ✨ session ***REMOVED***2 (B3)
│   │   └── (existing build_graph / calibrate / universal_collapse / hub_detect / update_classes_site_data)
│   ├── results/
│   │   ├── B3_ensemble_review.jsonl           ✨ session ***REMOVED***2 (B3, 63 verdicts)
│   │   ├── B3_ensemble_summary.md             ✨ session ***REMOVED***2 (B3)
│   │   ├── B3_taxonomy_v2.jsonl               ✨ session ***REMOVED***2 (B3, B1⊗B3 merged)
│   │   └── (existing A3_*, B2_*, layer3_*, layer4_*, candidate_classes ...)
│   ├── taxonomy/classes/*.yaml × 24
│   ├── tests/                                 ✨ session ***REMOVED***2 (E3 + E4 test)
│   │   ├── conftest.py
│   │   ├── sanity_helpers.py
│   │   └── sanity/test_*.py × 12
│   └── product/d1_phase_detector/             ✨ session ***REMOVED***2 (D1 groundwork)
│       ├── schema/structtuple_schema.json
│       ├── companies.jsonl (100)
│       ├── extract_structtuple.py
│       ├── sample_run.py + sample_structtuples.jsonl (5)
│       ├── cost_projection.md + README.md
├── web/frontend/                              ***REMOVED*** 站点（session ***REMOVED***2 未更新）
├── docs/sessions/
│   ├── HANDOFF.md (本文件)
│   ├── structural-iso-session-1-end.md
│   └── structural-iso-session-2-end.md        ✨ session ***REMOVED***2
├── pytest.ini                                 ✨ session ***REMOVED***2 (E3)
└── CLAUDE.md
```

---

***REMOVED******REMOVED*** 5. 常用命令速查（session ***REMOVED***2 起新增）

```bash
***REMOVED*** 起 session
cd ~/Projects/structural-isomorphism && git pull && source .venv/bin/activate

***REMOVED*** CLI（新）
python v4/cli.py status                     ***REMOVED*** 13 phases overview
python v4/cli.py validate <slug>            ***REMOVED*** single phase
python v4/cli.py list                       ***REMOVED*** all phases

***REMOVED*** Sanity tests（新）
.venv/bin/python -m pytest v4/tests/sanity -m sanity -q   ***REMOVED*** 38 in 3.6s

***REMOVED*** B3 ensemble re-run（如改 prompt 后重跑）
nohup .venv/bin/python v4/scripts/b3_ensemble.py > /tmp/b3.log 2>&1 &
tail -F /tmp/b3.log

***REMOVED*** D1 sample re-run
.venv/bin/python v4/product/d1_phase_detector/sample_run.py

***REMOVED*** D1 full 100 batch (next session)
.venv/bin/python v4/product/d1_phase_detector/extract_structtuple.py \
  v4/product/d1_phase_detector/companies.jsonl \
  v4/product/d1_phase_detector/structtuples_2026-05-XX.jsonl

***REMOVED*** PR flow
git checkout -b v4/session3-<topic>
***REMOVED*** ... 工作 ...
git push -u origin v4/session3-<topic>
gh pr create --base main --title "..." --body "..."
gh pr merge <num> --merge --delete-branch
git checkout main && git pull --ff-only
```

---

***REMOVED******REMOVED*** 6. 历史 sprint 索引

| Session | 日期 | 重点 | retro |
|---|---|---|---|
| (V1/V2) | 2026-04-11 | KB 5k + 3017 pair matches + 站点上线 | progress.md |
| (V3) | 2026-04-14 | V3 solver deprecated（Direct Opus 9/10 击穿） | progress.md |
| (V4 Layer 1-4) | 2026-04-15 | 23 candidate classes + 27 predictions | v4/results/FINDINGS-2026-04-15.md |
| (V4 L5 Phase 1-5) | 2026-04-15..16 | earthquake / S&P / DeFi / mouse / null | papers in v4/validation/*/paper.md |
| *****REMOVED***1** | **2026-05-13** | Phase 6/8/10/11 + B1/B2/B4 + A3 | docs/sessions/structural-iso-session-1-end.md |
| *****REMOVED***2** | **2026-05-13** | C1 preprint + Phase 7/12/13 + A2-Hyst + A2-Scheffer + B3 + D1 + E1/E3/E4 | docs/sessions/structural-iso-session-2-end.md |
| *****REMOVED***3** | **2026-05-13** | **41 PRs / 9 waves: site refresh + B/C/D 加固 + Phase 14 Hawkes / A2 Copula / A2 SIR + D1 ship LIVE + 6-role review + apply fixes + future planning + Zenodo + 2 PyPI + Scheffer p revised** | **docs/sessions/structural-iso-session-3-end.md** |
| ***REMOVED***4 | (next) | PUBLIC flip + arXiv submit + Zenodo mint + PyPI publish | (TBD) |

---

***REMOVED******REMOVED*** 7. 末尾 checklist (session N 结束时更新本文件)

下个 session 结束时更新本文件：
- [ ] §1 "已验证 systems" 加新行 (table)
- [ ] §2 "下个 sprint 优先级" 删已完成 + 排新
- [ ] §3 blocker 更新
- [ ] §4 repo 结构加新 ✨
- [ ] §5 命令速查加新
- [ ] §6 历史 sprint 索引加新行 + 写 `docs/sessions/structural-iso-session-N-end.md`
- [ ] commit 本文件 + push（走 PR）
