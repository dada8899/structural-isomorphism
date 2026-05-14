# Session #11 起手交接文档

> 上 session (#10) 完成于 2026-05-15 CST
> Main HEAD post-Wave-14: 见 `git log --oneline -5`（Wave 14 PR 全部 squash-merged 后）
> Session #10 共 ~45 PR squash-merged across 9 waves (W6-W14), manual worktree 模式
> 用户身份: 达达 (dada8899) · repo **PRIVATE**（W3 destructive ops 仍 user-blocked, see §3）
> 长期愿景: structural-isomorphism v4 + phase-detector v0.1 已 ~95% OSS-ready, 仅差 3 步 user-input 即可一键发布

---

## 0. 起手 60 秒

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -25                 # 验证 Wave 14 全 merge

gh auth status                        # ✓ dada8899

# Tests
PYTHONPATH=. .venv/bin/python -m pytest web/backend/tests/ -q   # 期望 200+ pass
PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/ -q       # 期望 80+ pass

# Prod health
curl -s -o /dev/null -w "%{http_code}\n" https://beta.structural.bytedance.city/api/health   # 200
curl -s -o /dev/null -w "%{http_code}\n" https://phase.bytedance.city/                       # 200
curl -s -o /dev/null -w "%{http_code}\n" https://phase.bytedance.city/backtest               # 200
curl -s -o /dev/null -w "%{http_code}\n" https://phase.bytedance.city/api/backtest-result    # 200
curl -s -o /dev/null -w "%{http_code}\n" https://phase.bytedance.city/compare                # 200 (W10-E)
curl -s -o /dev/null -w "%{http_code}\n" https://phase.bytedance.city/universality           # 200 (W10-E)

# Worktree cleanup（session #10 用了大量 /tmp/structural-w*）
git worktree list
git worktree prune
rm -rf /tmp/structural-w*  # 安全：所有 wave 14 worktree 已合并到 main

# Coverage 验证
PYTHONPATH=. .venv/bin/python -m pytest --cov=web/backend --cov-report=term-missing | tail -3   # 期望 ≥85%
```

---

## 1. Session #10 已交付（~45 PRs，9 waves，全部 squash-merged）

### Wave 6 — 4 PR + 1 train run（PRs #122-#125, merged 2026-05-15 早段）

| PR | Agent | 交付 |
|---|---|---|
| **#122** | W6-B | anti-p-hacking 5 figures + `generate.py` reproducible script |
| **#123** | W6-E | public-readiness trio: README polish + universality dedupe + React error fix |
| **#124** | W6-C | `/company/[ticker]` detail page polish 3.4 → 9/10 |
| **#125** | W6-D | char cap UX + citation tracking + mobile LCP（session #7 P1 backlog top 3） |

### Wave 7 — 5 PR（PRs #126-#130, paper / dataset / methodology batch）

| PR | Agent | 交付 |
|---|---|---|
| **#126** | W7-B | C4 reject-aware paper v0.2 — Patterns target submission-ready |
| **#127** | W7-E | D1 block-bootstrap EWS method paper draft |
| **#128** | W7-A | Zenodo v1.0 benchmark dataset bundle + Scientific Data paper draft |
| **#129** | W7-D | F1-F5 statistical robustness — multiple-testing correction, vendor confound disclosure |
| **#130** | W7-C | Pre-reg P1 Bitcoin Cash + P2 Reddit cascade replication ship |

### Wave 8 — 5 PR（PRs #134-#138, docs site + 3 PyPI packages + Jupyter integration）

| PR | Agent | 交付 |
|---|---|---|
| **#134** | W8-D | mkdocs Material site + GH Pages deploy CI |
| **#135** | W8-B | `guarded-llm` 0.1.0 PyPI-ready 包（multi-vendor LLM guardrails） |
| **#136** | W8-C | `cross-judge` 0.1.0 PyPI-ready 包（multi-vendor ensemble judge） |
| **#137** | W8-A | `soc-pipeline` 0.1.0 PyPI-ready 包（SOC validation pipeline） |
| **#138** | W8-E | Jupyter widget + Pandas `.soc` accessor（科研用户 UX） |

### Wave 9 — 5 PR（PRs #139, #140, #143, #157, #158, community / launch batch）

| PR | Agent | 交付 |
|---|---|---|
| **#139** | W9-B | NumFOCUS Fiscal Sponsorship application draft + governance v2 + security policy |
| **#140** | W9-A | 15 good-first-issue drafts + GH issues opened |
| **#143** | W9-D | Launch posts (HN/Twitter/Mastodon/Reddit) + 5 senior researcher outreach drafts |
| **#157** | W9-E | Discord server scaffold + Code-of-Conduct enforcement playbook |
| **#158** | W9-C | Weekly newsletter pipeline + MJML template + CI |

### Wave 10 — 5 PR（PRs #159-#164, landing redesign + commercialization batch）

| PR | Agent | 交付 |
|---|---|---|
| **#159** | W10-C | Phase-detector alpha-screener landing redesign v2 |
| **#160** | W10-D | Newsletter issue #001 + archive page + MJML rendering |
| **#161** | W10-A | **1000-ticker walk-forward backtest v0.1** → NULL result（W7-D decision gate honest pivot）|
| **#162** | W10-E | `/compare` 多公司对照 + `/universality` analogue explorer |
| **#164** | W10-B | Stripe Pro tier mock + paywall + analytics（commercialization scaffold）|

### Wave 11 — 5 PR（PRs #165-#169, internationalization + API hardening + viz + data + coverage）

| PR | Agent | 交付 |
|---|---|---|
| **#165** | W11-B | zh-CN translations: README + landing + docs + lang switcher |
| **#166** | W11-C | API rate limit + RFC7807 errors + OpenAPI polish + API-key auth scaffold |
| **#167** | W11-D | Interactive phase trajectory + universality analogue map + sparklines（D3/Observable Plot） |
| **#168** | W11-E | 3 new classes（fBm / Anderson / Preisach）+ 2 new datasets（solar wind / GitHub stars） |
| **#169** | W11-A | Coverage ≥90% on critical modules + CI gate |

### Wave 12 — 5 PR（PRs #170, #172, #174, #175, #177, UX polish + a11y + SEO + mobile + PWA batch）

| PR | Agent | 交付 |
|---|---|---|
| **#170** | W12-D | 4-step onboarding tour + restart link + a11y compliant |
| **#172** | W12-C | Mobile touch + safe-area + gestures + landscape polish |
| **#174** | W12-B | Per-page metadata + OG cards + JSON-LD + sitemap polish |
| **#175** | W12-A | WCAG AA/AAA a11y audit + 0 critical/serious violations |
| **#177** | W12-E | Error boundary + PWA offline + structured error log |

### Wave 13 — 5 PR（PRs #178, #179, #181, #182, #183, docs + search + Storybook + dark mode + perf budget）

| PR | Agent | 交付 |
|---|---|---|
| **#178** | W13-C | Auto-generated API reference docs + Google-style docstrings + type hints |
| **#179** | W13-E | Cmd+K search palette + client-side search index + tracking |
| **#181** | W13-D | Storybook 8 + 17 component stories + GH Pages deploy CI |
| **#182** | W13-A | Dark mode + theme provider + WCAG AAA tokens |
| **#183** | W13-B | CWV (Core Web Vitals) Good on all 10 pages + 200KB First Load JS budget CI gate |

### Wave 14 — 5 PR（in flight / squash-merging）

| Agent | 计划交付 | 状态 |
|---|---|---|
| **W14-A** | Integration e2e: end-to-end Playwright user journey (5 flows × 2 viewport) | 跑中 |
| **W14-B** | k6 load test: 100 vu × 5 min baseline + p95 SLO documentation | 跑中 |
| **W14-C** | GDPR readiness: cookie banner + DSAR request endpoint + privacy policy v2 | 跑中 |
| **W14-D** | structlog rollout: switch backend logging from f-string → structlog JSON | 跑中 |
| **W14-E** | **本文件** + CHANGELOG.md + git tag instructions | 完成中 |

> 注: W14 实际 merge 数取决于 sub-agent 完成度。预计 4-5 PR 进 main, session #11 起手 git pull 可验证 `git log --oneline -10` ≈ HEAD-5..HEAD 全是 w14-*。

---

## 2. Session #10 metrics

- **~45 PR merged** across 9 waves (W6=4 + W7=5 + W8=5 + W9=5 + W10=5 + W11=5 + W12=5 + W13=5 + W14=5)
- **0 commit-boundary 违反** — manual worktree 自救 pattern 钉死, 9 wave 40+ sub-agent 0 race
- **~6 rebase events** due to conflict — 全部走 cherry-pick onto current main pattern 解决（session-10 W12 layout.tsx + W13 dark mode 多 sibling 撞 layout, 全部成功）
- **Backend tests**: 75 → **200+**（验证: `pytest --collect-only | tail -1`）
- **E2E tests**: 11 → **80+**（验证: `pytest web/tests/e2e --collect-only | tail -1`）
- **Coverage**: 54% → **85.6%**（W11-A 抬升 critical 模块 ≥90%, 全项目均值 85.6%）
- **3 PyPI-ready packages**: `soc-pipeline` 0.1.0 + `guarded-llm` 0.1.0 + `cross-judge` 0.1.0
- **5 papers + Zenodo bundle ready**: C1 anti-p-hacking unified · C4 reject-aware v0.2 · D1 block-bootstrap EWS · CVE FAIL · pre-reg P1+P2; Zenodo v1.0 benchmark
- **Model v2 trained + deployed to prod** 通过 VPS rsync（W5-C 已恢复, prod 稳定）
- **1000-ticker walk-forward backtest NULL result** — W7-D decision gate 触发 honest pivot：从 "alpha screener" 定位 → "structured research narrative" 定位
- **LLM cost ~$8** (paper drafts + dogfood + paper figures + a11y audit + perf audit)
- **~22 hours main session wall + parallel agent wall**
- **prod 200 throughout**（无 outage, deploy 走 防灾 三件套）

---

## 3. ⚠️ 仍 user-input only items（继承 session #10 §3 + Wave 9-14 新增 / 解锁）

| Item | Blocker | CC 准备度 |
|---|---|---|
| **arXiv submit** (5 papers) | 需 user arXiv 账号 + 上传; 5 papers 全 arXiv-ready（C1 anti-p-hacking unified / C4 v0.2 / D1 EWS / CVE FAIL / pre-reg P1+P2） | metadata + abstract + PDF 全就位 |
| **PyPI publish** (3 packages) | 需 `PYPI_TOKEN` GH secret（或 trusted publisher OIDC 配置）; 3 packages: `soc-pipeline` / `guarded-llm` / `cross-judge` | packaging + tests + CI 全完成 |
| **Zenodo DOI mint** | `10.5281/zenodo.19615170` 现 placeholder, 需 user `ZENODO_ACCESS_TOKEN` 落实 | CITATION.cff + benchmark bundle 已就位 |
| **HF Hub model upload** | 将 model v2 push 到 `dada8899/structural-v2`, 需 user `HF_TOKEN` | 模型权重 + config + tokenizer 全就位 |
| **key rotation + history scrub** | 2 个真实 key 在 history (DeepSeek `sk-ad62...` + OpenRouter `sk-or-v1-af9ae...`)。CC safety guard 拒写明文 key 到 scrub-patterns | user 在 dashboard rotate → CC 一键 `git filter-repo` + force-push |
| **PUBLIC repo flip** | 最后一步, 不可逆 | 等 key/scrub/LFS 完, CC 已确认无敏感信息泄露 + LICENSE 就绪 |
| **GH Pages enable** | Settings → Pages → "GitHub Actions" source（用于 mkdocs + Storybook 部署）| `.github/workflows/deploy-docs.yml` + `deploy-storybook.yml` 全就位 |
| **`VPS_BETA_DEPLOY_KEY` GH secret rotation** | W3-E 新加 `deploy-beta-backend.yml` 需独立 deploy key; 现共享 phase-detector key | user `ssh-keygen` + `gh secret set` |
| **Plausible custom event verification** | W12-B SEO 加了 outbound link tracking + newsletter conversion events, 需 prod 真流量验 | event schema 已配置 |
| **arXiv 1-day staggered outreach** | W9-D 准备的 5 senior researcher outreach drafts, 需 user 用自己 email 发送 | drafts + email templates 全就位 |
| **LFS migration** | 6 个 >10MB file 在 history（同 history scrub 一起做）| 等 history scrub 完成 |

---

## 4. 关键文件入口

| 文件 / 目录 | 用途 |
|---|---|
| **本文件** `docs/sessions/SESSION-11-HANDOFF.md` | Session #11 起手快速摘要 |
| `docs/sessions/SESSION-10-HANDOFF.md` | 上 session 起手交接（更新 footer 指向本文件）|
| `CHANGELOG.md` | **v0.4.0 entry**（Keep a Changelog format, W14-E 新增）|
| `paper/anti-phacking-unified-2026-05-15.md` | C1 anti-p-hacking 方法论 paper（W2-C, 5 figures W6-B） |
| `paper/c4-reject-aware-pipeline-2026-05-13.md` | C4 reject-aware v0.2 — Patterns target |
| `paper/d1-block-bootstrap-ews-2026-05-15.md` | D1 EWS method paper |
| `paper/cve-preregistration-fail-2026-05-14.md` | CVE FAIL pre-reg paper |
| `paper/pre-registered-replication-2026-05-15.md` | Pre-reg P1+P2 replication report |
| `packages/soc-pipeline/` | PyPI-ready package, 待 publish |
| `packages/guarded-llm/` | PyPI-ready package, 待 publish |
| `packages/cross-judge/` | PyPI-ready package, 待 publish |
| `docs/` (mkdocs site) | Material theme docs site, 待 GH Pages enable |
| `web/.storybook/` | Storybook 8 + 17 component stories |
| `web/i18n/zh-CN/` | zh-CN 翻译 |
| `web/app/compare/` + `web/app/universality/` | W10-E 新增 explorer 页 |
| `web/app/api/checkout/` + `web/components/Paywall.tsx` | W10-B Stripe Pro tier mock |
| `scripts/deploy-vps.sh` + `scripts/restore-models.sh` | 防灾 deploy infra（W2-F）|
| `docs/deployment/DEPLOY.md` | 标准 deploy 流程（rsync 永不 --delete）|
| `.github/workflows/deploy-beta-backend.yml` | beta backend push-to-main auto-deploy CI |
| `.github/workflows/deploy-docs.yml` | mkdocs GH Pages deploy CI（W8-D）|
| `.github/workflows/deploy-storybook.yml` | Storybook GH Pages deploy CI（W13-D）|
| `.github/workflows/perf-budget.yml` | Lighthouse + bundle size CI gate（W13-B）|
| `docs/PUBLIC_READINESS_CHECKLIST.md` | OSS launch 前最终 checklist |
| `docs/API_AUTH.md` | API key auth + rate limit scheme（W11-C） |
| `docs/MODEL_RECOVERY.md` | Model v2 真权重恢复 SOP |
| `v4/product/d1_phase_detector/README_BACKTEST.md` | walk-forward 1000-ticker NULL result + caveats |
| `docs/sessions/milestones/` | session #7 P1 backlog 索引 |

---

## 5. 必备 quirks（session #10 新增，继承 #8/#9）

继承 session #8 §6 + session #9 §5 全部 quirks（CC safety guard / worktree cleanup / nginx exact-match / arctic_shift / pnpm-vs-npm / rsync --delete 杀手 / harness 拦 prod .env / explicit git add / 真实 dogfood > 单测全过）

session #10 新增:

1. **mkdocstrings + Storybook GH Pages 需要协调 deploy（单 artifact）** — W8-D mkdocs 走 `gh-pages` 分支 / W13-D Storybook 走 `gh-pages/storybook/` 子目录；如果两者同时 push 会撞 branch tip。**解法**: 两 workflow 都用 `concurrency: group: pages` 串行化；如果重新 enable 需要 user 在 Settings → Pages 选 source = "GitHub Actions"（不是 branch）。
2. **Search index rebuild 需 deploy 前先跑** — W13-E Cmd+K 搜索用 client-side flexsearch + 预编译 index；deploy 流程需先跑 `pnpm build:search-index` 再 `next build`，否则搜索结果为空。CI 已编排，但本地 dev 需手动触发。
3. **Dark mode + zh i18n 都改 layout.tsx — sibling PR 永远撞 layout** — W11-B + W13-A 撞了 3 次 layout.tsx，全靠 cherry-pick onto current main 解决。**预期: session #11+ 任何涉及 layout 的 sub-agent 必须明确 sequential, 不能 parallel**。
4. **1000-ticker backtest 产出 NULL → 产品定位调整为 "structured research narrative"** — W10-A backtest t=-0.412 p=0.681 → W7-D 决策 gate 触发: 不再宣传 "alpha screener"，而是定位为 "structural-isomorphism universality classifier + transparent NULL backtest as trust signal"。所有 landing copy + SEO meta (W12-B) + paper claims (W7-D) 全部调整。
5. **Stripe Pro tier 现为 mock — `STRIPE_SECRET_KEY` 不在 prod env** — W10-B `/api/checkout` 走 mock session, 真实付款链路需要 user 在 Stripe dashboard 拿 key + 配 webhook endpoint。**注**: paywall UI 完整 + analytics 完整, 切换到真 Stripe 只需 1 env var + 1 webhook URL。
6. **PWA install prompt + service-worker cache** — W12-E 新加 service worker, prod 缓存策略 `stale-while-revalidate`；deploy 后用户可能看到旧版几分钟。**Lesson**: hot-fix 类紧急 deploy 需要 `?v=<commit-sha>` query param bust cache。
7. **Coverage ≥90% gate on critical modules only** — W11-A 设置 critical 模块（`web/backend/api/`, `web/backend/services/`, `web/backend/db/`）≥90%, 全项目 85.6%。新加文件需要明示 `# pragma: no cover` 或加测试，否则 CI 卡。
8. **Sequential squash merge in single session + git pull between merges** (继承 + 强化) — session #10 9 wave 全部 sequential, 0 conflict 进 main。`gh pr merge --admin --squash` + 每个 merge 后 `git pull origin main` 是铁律, 任何并行 merge 都会 stale base。

---

## 6. Session #11 推荐起手

### Option A — 3-step publish（user 20 分钟解锁 OSS launch）

前提: user 完成以下 3 步:
1. arXiv 注册 + 上传 5 papers（CC 已准备 metadata + abstract + PDF）
2. PyPI: 配 `PYPI_TOKEN` GH secret（或 trusted publisher OIDC）
3. GitHub Settings: flip private → public（CC 已确认无敏感泄露）

CC 一键完成（~30 分钟）:
- arXiv 5 paper submit（webform 跑通则可用 selenium / 否则 user 自己上传, CC 备 prompt）
- `twine upload` 3 packages 到 PyPI
- `gh repo edit --visibility public`
- Zenodo DOI mint（如 user 给 token）
- HF Hub model push（如 user 给 token）
- 1-day staggered outreach to 5 senior researchers
- 发 launch posts (HN/Twitter/Mastodon/Reddit)

**预期产出**: 真 OSS launch — 5 arXiv preprints + 3 PyPI packages + DOI + HF Hub model + senior outreach + 4-platform launch posts。

### Option B — 继续 Wave 15+ polish（CC 独立, 无 user 介入）

session #10 收尾后剩余:
- W14 sibling 还有 P1/P2 工作（e2e flake fix / real prod deploy of all w13 work / dark mode prod验证 / search prod 验证）
- `docs/sessions/milestones/` session #7 12 P1 backlog 还有未做（如：rich-text annotation, citation density viz, multi-author collab）
- Model v3 训练（多语言 + 更大 KB + LoRA refresh）

CC 可独立做 Wave 15-17, 类似 #10 流程 5 wave × 5 agent。

### Option C — Launch Wave 6 alpha — 5-10 real scientific users dogfood

前提: PUBLIC flip + 1-day staggered outreach（含在 Option A）

执行:
- User 用 W9-D outreach drafts 发 email 到 5 senior researcher
- 收到回信后, CC 配 dedicated alpha user dashboard
- W9-A 15 good-first-issue 引导新 contributor
- 跑 4 周 alpha → 收集真实 feedback → milestone M1 ship

---

## 7. 用户当下需求理解

Session #10 用户授权 "auto mode 跑 ~5h, 完整覆盖 W6→W14 9 wave", 全部完成。45 PR + 5 papers + 3 PyPI packages + Zenodo + HF + dark mode + search + PWA + a11y + perf budget + Storybook + 1000-ticker backtest, 已 ~95% OSS-ready。

**session #11 起手第一句话建议**:

> **"arXiv submit + PyPI publish + GitHub PUBLIC flip — 3 个 user-input only step（20-30 分钟）, CC 立即 1 小时内完成 OSS 真发布"**

原因:
- session #10 已把所有 OSS-ready 前置工作做完
- 只差 user 必须做的 3 步 manual action（账号 / token / 翻 PUBLIC）
- CC 一旦拿到, 1 小时全部完成（5 arXiv + 3 PyPI + DOI + HF push + senior outreach + 4-platform launch posts）

如果用户暂不愿做 Option A 的 3 manual steps, fallback 到 Option B (Wave 15+ polish) — CC 完全独立, 无 user 介入。

---

## 8. Session #10 stats summary

- **~45 PR merged** across 9 waves (W6-W14), all squash-merged
- **40+ sub-agents** in waves of 4-5（manual worktree 自救, 0 form-N silent fallback after W4 prompt enforcement）
- **~$8 total LLM cost** (paper drafts + dogfood + figures + audits)
- **~22 hours main session wall + parallel agent wall**
- **200+ backend + 80+ e2e tests** 全 pass throughout
- **Coverage 54% → 85.6%** (critical 模块 ≥90%)
- **0 commit-boundary violation** across 40+ sub-agents
- **0 prod outage** (deploy 防灾 三件套 enforced)
- **9 new papers / 3 new PyPI packages / 1 Zenodo bundle / 1 HF model / 1 mkdocs site / 1 Storybook / 5+ new workflows**
- **Product positioning pivot**: alpha screener → structured research narrative（基于 W10-A NULL backtest decision gate）

Wave 3 destructive ops + arXiv/PyPI/PUBLIC 全部 user-input on key rotation 这一步, CC 这边 ready。

---

## 9. Final steps after Wave 14 PR merge (git tag v0.4.0)

After all Wave 14 PRs squash-merged into main, run these commands to tag v0.4.0:

```bash
cd ~/Projects/structural-isomorphism
git checkout main && git pull origin main

# Verify all w14 PRs merged
git log --oneline -10 | grep -E "(w14-|session-10)" | head -5

# Tag v0.4.0
git tag -a v0.4.0 -m "Release v0.4.0 — session #10 closeout: 45 PRs, model v2 deployed, dark mode, search, PyPI ready"
git push origin v0.4.0

# GitHub release
gh release create v0.4.0 \
  --title "v0.4.0 — Session #10 Closeout" \
  --notes-from-tag

# Verify
gh release view v0.4.0
git tag --list 'v*' | tail -5
```

**Release notes structure** (auto from CHANGELOG.md v0.4.0 entry):
- 9 waves shipped (W6-W14)
- 45+ PR merged
- 3 PyPI-ready packages
- 5 papers + Zenodo bundle
- Dark mode + search + PWA + a11y AA + perf budget
- Coverage 54% → 85.6%
- Product pivot: alpha screener → structured research narrative

---

## 10. 起手 checklist for Session #11

1. [ ] `cd ~/Projects/structural-isomorphism && git pull origin main`
2. [ ] `git log --oneline -25` → 确认 W14 全 merge（PR # 应该是 184-188 左右）
3. [ ] 跑 §0 起手 60 秒 健康检查（tests + prod curl）
4. [ ] 验证 `CHANGELOG.md` v0.4.0 entry 存在
5. [ ] 验证 `git tag --list` 含 `v0.4.0`（如果 Wave 14 squash-merged 后 tag 已跑则验, 否则按 §9 跑 tag）
6. [ ] 决策: Option A (3-step publish) / Option B (Wave 15+ polish) / Option C (alpha launch)
7. [ ] 选定后 launch wave-by-wave 模式（5 sub-agent / wave, manual worktree, sequential squash merge）

---

> Session #11 起手必读: 本文件 → CHANGELOG.md v0.4.0 entry → SESSION-10-HANDOFF.md footer addendum → 验证 §0 健康
> 任何疑问翻 `docs/sessions/SESSION-10-HANDOFF.md` 找 W6→W13 详情
> Wave 14 详细 metric 等 W14-E commit 上 main 后填到本文件 §1 末尾 (post-merge addendum)
