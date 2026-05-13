# structural-isomorphism · Next-session HANDOFF

> 永久 entry point。**下个 session 起手第一件事：读本文件**。
> Session-N 收尾后更新这个文件指向最新 sprint。历史 retro 在 `docs/sessions/structural-iso-session-N-end.md`。

---

## 0. 起手 60 秒

```bash
cd ~/Projects/structural-isomorphism/
git pull origin main                        # 同步最新
git log --oneline -5                        # 确认 head = d222aa1 或之后
source .venv/bin/activate                   # 激活 venv（Python 3.14 + numpy/scipy/pandas/powerlaw/...）
python -c "from soc_pipeline import fit_clauset_powerlaw; print('lib ok')" \
  || (cd v4/lib && PYTHONPATH=. python -c "from soc_pipeline import fit_clauset_powerlaw; print('lib ok')")
ls v4/validation/                           # 9 个 phase 目录 (含 wildfire/solar/github-stars/bank-failures)
ls v4/taxonomy/classes/ | wc -l             # 应该是 24 yaml
```

读完这 4 个文件即可上手：
1. **本文件** (HANDOFF.md)
2. `plans/v4-next-roadmap-2026-05-13.md` — 7 维度全景路线图
3. `docs/sessions/structural-iso-session-1-end.md` — 上 session retro 详情
4. `CLAUDE.md` (repo 根) — 如果还没有/不熟，需要先读 `~/CLAUDE.md` 全局规范

---

## 1. 当前状态 (2026-05-13 截止)

### 已验证 SOC 系统：9 个

| Phase | 系统 | α | CI | n | paper |
|---|---|---|---|---|---|
| 1 | USGS earthquakes | b=1.084 | [1.073, 1.094] | 37k tail | ✓ |
| 2 | S&P 500 returns | 2.998 | (n/a) | 9060 | ✓ |
| 3 | DeFi Aave/Compound/Maker | 1.57-1.68 | (per-protocol) | 43k | ✓ |
| 4 | Mouse cortex avalanches | 2.58 | [2.17, 3.00] | 1.39M spk | ✓ |
| 5 | null validation (4/4 reject) | — | — | — | (footer) |
| **6** | **GitHub stars (PA class)** | **2.867** | **[2.781, 3.000]** | **8398** | ✓ |
| **8** | **FDIC bank failures** | **1.899** | **[1.763, 2.047]** | **3960** | ✓ |
| **10** | **NIFC wildfires** | **1.660** | **[1.381, 1.808]** | **21k** | ✓ |
| **11** | **GOES solar flares** | **2.194** | **[2.159, 2.248]** | **29.9k** | ✓ |

### Taxonomy 状态

- `v4/taxonomy/classes/*.yaml` — 24 类，per-class positive/negative/edge_cases
- `v4/results/layer3_critic.jsonl` — B1 critic 推荐 21 → 15 active classes
- `v4/results/A3_universal_collapse_plot.png` — 7 系统 master curve

### Git 状态

- main HEAD: `d222aa1` (PR #1 merged 2026-05-13)
- 4 commits 来自 session 1: `d03a841 / 3e57acb / 490afba / 2767738`
- 本地 = origin/main，clean

### Site 状态

- `web/frontend/assets/data/universality-classes.json` 已更新（8 verified predictions）
- 4 papers copied to `web/frontend/assets/data/papers/`
- **VPS 未同步**（SSH 22 不通时段，下次 launchd 周期或手动 pull 后生效）

---

## 2. 下个 sprint 优先级（按 leverage 排）

### Sprint A — 直接产出 (8-10h)

1. **C1 unified preprint v0.1** — 把 Phase 1+2+3+4+5+6+8+10+11 合成一篇 arXiv 草稿
   - 标题候选：*"A pipeline for cross-domain validation of self-organized criticality and preferential attachment: 9 systems, one method"*
   - 模板：派 Opus subagent 用各 phase paper.md + A3 universal collapse 结果合成 5000-7000 word 主稿
   - 写到 `paper/v0-unified-pipeline-2026-05-XX.md`
   - 预期：1-2 个 subagent dispatch，2-3h 完成 v0.1
   - 卖点：单一管道 0 调参跨 9 个真实系统 + null validation + B1 critic + universal collapse
   - **强 leverage** — 把 4 周工作变成可投 arXiv 的成品

2. **B3 multi-model ensemble** — DeepSeek 直连 + Kimi 直连绕开 OpenRouter CN 区域 block
   - DeepSeek 直连 key 在 memory: `reference_deepseek_direct_api_2026_05_06.md`
   - 3 模型对 23 类投票 → 写 `v4/results/B3_ensemble_review.jsonl`
   - 配合 B1 critic 一起进 taxonomy v2 输出

3. **Phase 12 — universal-collapse polish + 新增 c-extension** — A3 现在是基础版，可加：
   - finite-size scaling 完整推导（不仅 99th-pctl rescale）
   - log-bin density estimation
   - 写成单独 paper.md 而不是只 summary.md
   - 1-2h 工作

### Sprint B — 新数据 (6-10h)

4. **Phase 7 NERC TADS 电网级联**（Motter-Lai 亚类 explicit）
   - 数据：NERC TADS 报告（PDF 或 Excel）。Excel 友好。
   - URL: https://www.nerc.com/pa/RAPA/tads/ (找 Excel 附件)
   - 替代：US EIA OE-417 electricity disturbance reports (~5k events)
   - 预测：α 1.4-1.9 (Motter-Lai)，event size = MW affected / customer hours
   - 估时 3-4d

5. **Phase 13 Wikipedia views**（再 verify preferential_attachment）
   - 数据：Wikimedia REST API pageviews
   - 已知 α ≈ 2.0 (Newman 2005)
   - 估时 2d

6. **A2-Hysteresis 交通拥堵**（首次非 SOC 类实证）
   - 数据：PeMS California highway 5-min loop detector data
   - 验证：q_c1 / q_c2 ratio in [1.25, 1.55]
   - 估时 3d

7. **A2-Scheffer 湖泊富营养化**
   - 数据：USGS National Water Information System
   - 验证：bistable regime shift + early warning indicators
   - 估时 3d

### Sprint C — 工程加固 (2-3h)

8. **E1 unified CLI** — 把 v4/validation/*/analyze.py 抽成 `v4 validate <slug>` 子命令
9. **E2 DVC / git-lfs** — 给 catalog.parquet / aave_v2_liquidations.jsonl 等大 jsonl 加 versioning
10. **E3 CI sanity tests** — 每 phase 一个 10s synthetic regression test

---

## 3. 已知 blocker / 注意事项

### 网络
- **VPS SSH 22 不通时段** — 本地→43.156.233.71:22 路由经常 transient 抖动；可用 `ssh -o ConnectTimeout=30` 重试或等 launchd 周期
- **OpenRouter Anthropic/Gemini CN region-block** — 用 DeepSeek 直连 / Kimi 直连绕开（key 在 memory）
- **Reddit Pushshift API 停服** — Phase 9 social cascade 数据需要换源（Hacker News Algolia API 是替代）

### 子 agent
- **worktree isolation 限制**: structural-isomorphism 仓在 `/Users/dadamini/Projects/structural-isomorphism`，主 session CWD 是 `/Users/dadamini/Projects/renai-cross`。subagent `isolation: "worktree"` 会基于主 session CWD，导致 worktree 在 renai-cross 内，无法操作 structural-isomorphism。
  - **解决**：subagent **不用 isolation**，直接给绝对路径，让它在主仓写文件，主 session 后续 commit。memory 有相关 feedback (`feedback_subagent_worktree_*.md`)。
  - **代价**：多 subagent 并行写不同目录可以，但 git commit 必须主 session 来做（避免 race）。

### Commit
- main branch 直接 push 被 sandbox 拒 — **必须走 PR**：起 feature branch + `gh pr create` + `gh pr merge --merge --delete-branch`。session 1 走通这条路（PR #1）。

### 数据
- `v4/validation/soc-wildfire/raw_nifc.csv` 17MB — `.gitignore` 已加；如果 re-fetch 需要 17M 不进 git
- `models/` (782MB V1/V2) — 已 `.gitignore`，V4 不依赖

---

## 4. Repo 结构速查

```
~/Projects/structural-isomorphism/
├── .venv/                          # Python 3.14 venv (numpy/scipy/pandas/powerlaw/...)
├── plans/                          # 路线图 + 老 V3 plans
│   └── v4-next-roadmap-2026-05-13.md   ⭐ 7 维度全景路线
├── v4/
│   ├── lib/soc_pipeline.py             ⭐ 共享 SOC primitives
│   ├── validation/                     # 9 个 phase 目录
│   │   ├── soc-earthquake/
│   │   ├── soc-stockmarket/
│   │   ├── soc-defi/
│   │   ├── soc-neural/
│   │   ├── soc-wildfire/               # session 1 new
│   │   ├── soc-solar/                  # session 1 new
│   │   ├── soc-bank-failures/          # session 1 new
│   │   ├── soc-github-stars/           # session 1 new
│   │   └── null-controls/
│   ├── scripts/                        # 全局 utilities
│   │   ├── build_graph.py / build_site_data.py / hub_detect.py
│   │   ├── calibrate_predictions_ci.py    # B2
│   │   ├── universal_collapse.py          # A3
│   │   └── update_classes_site_data.py    # site updater
│   ├── results/                        # cross-phase 结果
│   │   ├── candidate_classes.jsonl     # Layer 2
│   │   ├── layer3_auto_curated.jsonl   # Layer 3
│   │   ├── layer4_predictions.jsonl    # Layer 4
│   │   ├── layer3_critic.jsonl + summary.md     # B1 ✨
│   │   ├── layer4_predictions_calibrated.jsonl # B2 ✨
│   │   ├── verified_observations.json           # B2 ✨
│   │   ├── A3_universal_collapse.{json,plot.png,summary.md}  # A3 ✨
│   │   └── B2_calibration_summary.md            # B2 ✨
│   └── taxonomy/
│       ├── universality_classes.yaml   # 老 seed (don't overwrite)
│       ├── SCHEMA.md                    # B4 ✨
│       └── classes/<class_id>.yaml × 24  # B4 ✨
├── web/frontend/
│   ├── classes.html / assets/js/classes.js  # /classes 页面
│   └── assets/data/
│       ├── universality-classes.json   # ✨ 8 verified predictions
│       └── papers/<slug>.md            # 4 new papers ✨
├── paper/                              # 老 V1/V2 paper drafts
├── docs/sessions/
│   ├── HANDOFF.md (本文件)
│   └── structural-iso-session-1-end.md
└── CLAUDE.md                           # 项目级 CC 指引（项目根，重要）
```

---

## 5. 常用命令速查

```bash
# 跑某个 phase analyze (例: wildfire)
cd ~/Projects/structural-isomorphism && source .venv/bin/activate
python v4/validation/soc-wildfire/analyze.py

# 重新跑 B2 calibration（添加新 verified 后）
python v4/scripts/calibrate_predictions_ci.py

# A3 universal collapse 重新合成
python v4/scripts/universal_collapse.py

# 更新 /classes 站点数据
python v4/scripts/update_classes_site_data.py

# 起 feature branch + commit + PR + merge（替代 direct push to main）
git checkout -b v4/next-phase-XX
# ... 工作 ...
git add <specific files>
git commit -m "..."
git push -u origin v4/next-phase-XX
gh pr create --base main --title "..." --body "..."
gh pr merge <num> --merge --delete-branch
git checkout main && git pull --ff-only

# VPS git pull (SSH 通的时候)
ssh vps "cd /root/Projects/structural-isomorphism && git pull origin main && systemctl restart nginx"
# 注意：VPS 目录原本是 rsync 快照非 git，第一次需要 git init + remote add + fetch + reset
```

---

## 6. 历史 sprint 索引

| Session | 日期 | 重点 | retro |
|---|---|---|---|
| (V1/V2) | 2026-04-11 | KB 5k + 3017 pair matches + 站点上线 | progress.md |
| (V3) | 2026-04-14 | V3 solver deprecated（被 Direct Opus 9/10 击穿） | progress.md |
| (V4 Layer 1-4) | 2026-04-15 | 23 candidate classes 浮现 + 27 predictions | v4/results/FINDINGS-2026-04-15.md |
| (V4 Layer 5 Phase 1-5) | 2026-04-15..16 | earthquake / S&P / DeFi / mouse / null validation | papers in v4/validation/*/paper.md |
| **Session 1** | **2026-05-13** | **Phase 6/8/10/11 + B1/B2/B4 + A3** | **docs/sessions/structural-iso-session-1-end.md** |
| Session 2 | (next) | C1 unified preprint / B3 ensemble / Phase 7+ | (TBD) |

---

## 7. 末尾 checklist (session N 结束时更新本文件)

下个 session 结束时，把这个 HANDOFF.md 更新：
- [ ] §1 "已验证 SOC 系统" 加一行
- [ ] §2 "下个 sprint 优先级" 把已完成的删去 + 排新优先级
- [ ] §3 "已知 blocker" 更新（解决的删，新增的加）
- [ ] §6 "历史 sprint 索引" 加一行 + 写 `docs/sessions/structural-iso-session-N-end.md`
- [ ] commit 本文件 + push（走 PR）
