***REMOVED*** Session ***REMOVED***12 起手交接文档

> Session ***REMOVED***11 完结于 2026-05-20，本文档供下个 session（本人换设备或新 CC session）起手用。
> 上 session 末态：main HEAD 离 `1d9ce82` 21 PR 后 + v0.5.0 tag + repo PUBLIC
> 重要：本节有 **🔴 紧急 user 动作**，先看 §3

---

***REMOVED******REMOVED*** 1. 当前 state 快照

| Item | Value |
|---|---|
| repo | `dada8899/structural-isomorphism` — **PUBLIC** ✅ |
| main HEAD | `9febcc9` (Wave 4 addendum doc 提交后) |
| Latest tag | `v0.5.0` (GH release published) |
| GH Pages | enabled ✅, `https://dada8899.github.io/structural-isomorphism/` |
| Prod | phase.bytedance.city / beta.structural.bytedance.city / bytedance.city / cc / monitor — 全 200 ✅ |
| Prod cert | 3 cert force-renewed 2026-05-15，timer enabled (next auto-renew ≤ 60 天) |

***REMOVED******REMOVED******REMOVED*** CI workflow 状态（最新 push 后）

| Workflow | Status | 备注 |
|---|---|---|
| types-sync | ✅ | F11 ***REMOVED***207 持续绿 |
| sanity | ✅ | F15+F17 PYTHONPATH+sklearn 修 |
| docs | ✅ | F14 strict 修 + GH Pages enable |
| deploy-phase-detector | ✅ | F12 + VPS-side patch |
| coverage | **部分修** | TOTAL 84.5% ✅ ／ ask.py per-file 90% gate 因 CI vs local env mismatch 仍卡 |
| ci (matrix) | ⏳ ubuntu/macOS 应绿 | windows-latest 已 exclude (PR ***REMOVED***217); 其他 RUNNING 待验 |
| perf | ⏳ post C13 应绿 | RUNNING |
| deploy-beta-backend | stale 04:01 fail | F12 fix in repo 已 merge，paths trigger 没自动 re-fire；需 user 手动 trigger 一次或 push 一个 `scripts/deploy-vps.sh` change |
| storybook | NONE | 没自动跑（W13-D workflow？看 yml 是否 trigger） |

---

***REMOVED******REMOVED*** 2. Session ***REMOVED***11 交付物（21 PR + 多项 infra）

***REMOVED******REMOVED******REMOVED*** Wave 1（audit findings 修）— PR ***REMOVED***199-***REMOVED***204
- *****REMOVED***199** ci 装 editable packages/* + pyyaml + mkdocstrings
- *****REMOVED***200** FastAPI on_event → lifespan
- *****REMOVED***201** Next.js 14.2.15 → 14.2.35 (CVE-2024-56332 + cache poisoning + mw bypass)
- *****REMOVED***202** tier-aware rate limit ContextVar + 7 LLM-expensive endpoints
- *****REMOVED***203** polish: CITATION 0.4.0 + /me redirect + 404 zh + ESLint config + 加载更多
- *****REMOVED***204** OpenAPI schema sync + 9 response_model

***REMOVED******REMOVED******REMOVED*** Wave 2（CI deepening）— PR ***REMOVED***205-***REMOVED***211
- *****REMOVED***205** storybook fixtures schema align (UniversalityEvidenceSystem)
- *****REMOVED***206** perf regex v1（leading char + bare /）
- *****REMOVED***207** TS types regen 跟 ***REMOVED***204 同步
- *****REMOVED***208** deploy-vps.sh `export CI=true`（pnpm TTY bypass）
- *****REMOVED***209** pnpm-lock.yaml refresh after ***REMOVED***203 eslint
- *****REMOVED***210** coverage 装 pyjwt+structlog+openai+sklearn + continue-on-collection-errors
- *****REMOVED***211** mkdocs pin <1.0 + drop --strict（临时）

***REMOVED******REMOVED******REMOVED*** Wave 3（真根因迭代）— PR ***REMOVED***212-***REMOVED***214
- *****REMOVED***212** perf 真根因 = lint blocks build + pipefail + actionable error dump
- *****REMOVED***213** sanity PYTHONPATH/conftest（v4/lib append + dotted path shim imports）
- *****REMOVED***214** sanity 缺 sklearn 装

***REMOVED******REMOVED******REMOVED*** Wave 4（公开 + 清尾）— PR ***REMOVED***217-***REMOVED***221
- *****REMOVED***217** ci matrix exclude windows-latest（3 platform issues: cp1252 编码 + subprocess paths）
- *****REMOVED***218** PyPI publish workflow + `docs/deployment/PYPI_PUBLISH.md`（tag-trigger + token/OIDC dual-auth）
- *****REMOVED***219** mkdocs --strict 重启 + 4 cp + 7 broken links 修
- *****REMOVED***220** ESLint `react/no-unescaped-entities` 重启 + 22 CJK 引号修
- *****REMOVED***221** coverage workflow `-p` flag（5 处）— combine bug 真根因

***REMOVED******REMOVED******REMOVED*** 其他基础设施
- **v0.5.0** git tag + GH release (110 commits since v0.4.1)
- **PUBLIC repo flip**（user 做的，session 5 天间隙）
- **GH Pages enable** via `gh api ... -X POST -f build_type=workflow`
- **PyPI 3 package 名占座**（user 配的；但 0 release published）
- **3 prod cert force-renewed** (bytedance.city / cc / monitor)
- **certbot.timer enabled** 永久（OpenCloudOS preset=disabled 根因）
- **VPS-side `/root/scripts/deploy-phase-detector.sh`** patched (加 `export CI=true`)

---

***REMOVED******REMOVED*** 3. 🔴 紧急 user 动作（先做）

***REMOVED******REMOVED******REMOVED*** B7 历史 LLM key 暴露 — repo 已 PUBLIC 5+ 天

详见 audit doc：`audit/p0-history-key-scrub-1779210404` branch（**未 merge**，仍在 origin；含完整 plaintext key — 也是泄露载体）

**2 个 active key 仍在 main HEAD plaintext**：

| Key | 首暴露 commit | 时长 | 文件位置 (HEAD 仍在) |
|---|---|---|---|
| OpenRouter `sk-or-v1-af9ae...` | 2026-04-16 (commit `aa044dd`) | 34 天 | `web/backend/.env.bak-v1`, `web/scripts/deploy.sh:39`, `docs/sessions/SESSION-9-HANDOFF.md:84` |
| DeepSeek `sk-ad62cc6d...` | 2026-05-13 (commit `a88dbef`) | 7 天 | `W5-B-researcher-review-...md:111`, `docs/sessions/SESSION-9-HANDOFF.md:83` |

**外加**：fork `Eudes-Crabe/structural-isomorphism` 已镜像（force-push 无法清理 fork）

**user 立即做的 4 步**：

```bash
***REMOVED*** 1. Vendor dashboard 立即 rotate
***REMOVED*** OpenRouter: https://openrouter.ai/settings/keys → revoke + create new
***REMOVED*** DeepSeek: https://platform.deepseek.com/api_keys → revoke + create new

***REMOVED*** 2. 验证旧 key 已 dead (curl 应得 401)
curl -X POST https://openrouter.ai/api/v1/chat/completions \
  -H "Authorization: Bearer sk-or-v1-af9ae735..." \
  -d '{"model":"openai/gpt-4o-mini","messages":[{"role":"user","content":"test"}]}' 
***REMOVED*** 期望 401

***REMOVED*** 3. 更新 VPS systemd env / .env 文件，重启服务
ssh vps "systemctl restart beta-structural-backend phase-detector-web"

***REMOVED*** 4. 删除 audit branch（含 plaintext key 的额外暴露载体）
git push origin --delete audit/p0-history-key-scrub-1779210404
```

**之后可选**（route A vs B）:
- **Route A (rotate-only)**：到此为止。旧 key 已 dead，历史上的明文 key 无危害但永远在 git log 里。fork 也无所谓。
- **Route B (filter-repo + force-push)**：彻底删历史。会 break ***REMOVED***215/***REMOVED***216 等 open PR，fork 残留无法清。耗时 30 分钟。命令在 `docs/security/2026-05-20-history-key-audit.md`（audit branch 那 252 行）。

CC 推荐 Route A — 既然 key rotate 了，明文历史 risk = 0，不值得 force-push 的成本。

---

***REMOVED******REMOVED*** 4. 仍 user-input only blocker（非紧急）

| Item | 需要 |
|---|---|
| PyPI 实际 publish | `PYPI_API_TOKEN` GH secret + git tag 触发自动（workflow ***REMOVED***218 已建） |
| arXiv 5 paper 上传 | arXiv 账号 + manual upload (paper/ 下 5 文件 ready) |
| HF Hub model push | `HF_TOKEN` GH secret + 跑 `huggingface-cli` |
| Zenodo DOI mint | `ZENODO_ACCESS_TOKEN` + DOI claim |
| 5 senior outreach | user 用自己 email 按 `docs/community/launch/senior-outreach-2026-05-15.md` 1-day staggered 发 |

---

***REMOVED******REMOVED*** 5. 下个 session 推荐起手

***REMOVED******REMOVED******REMOVED*** Option A — 1 小时 OSS launch（最高 ROI）

前提：user 完成 §3 紧急动作 + 配 4 个 token（PYPI / HF / ZENODO / arXiv 账号）

CC 一键完成（30-60 min）：
1. `git tag -a v0.5.1` → publish-pypi.yml 自动 publish 3 包到 PyPI
2. arXiv selenium 上传 5 paper（或 user 自己 webform）
3. `huggingface-cli` push v2 model 到 `dada8899/structural-v2`
4. Zenodo DOI mint + CITATION.cff 更新
5. 5 senior researcher 1-day staggered outreach 发送
6. HN / Twitter / Mastodon / Reddit launch posts post（drafts 全在 `docs/community/launch/`）

***REMOVED******REMOVED******REMOVED*** Option B — code 端清尾（CC 独立）

剩下小 P1（每个 < 30 min）：
- **ask.py CI vs local env mismatch**：local 100% / CI 54.3%。看 `web/backend/tests/test_ask_endpoint.py` 的 streaming mock 是否在 CI 走 missing dep 分支。可能要装 sse-starlette 或类似
- **deploy-beta-backend** 手动 trigger 验证 F12 真起作用
- **packages (py3.11) `Verdict.alpha_ci_lo` API drift** — 改 test 或 src 让 attr 一致
- **frontend (node 20) LFS pointer cache key** — pnpm-lock.yaml 漂或 LFS 配置
- **storybook CI** 没自动跑 — 看 trigger paths
- **mkdocstrings 1.x 真升级**（现 pin <1.0 是 ***REMOVED***211 临时方案）

***REMOVED******REMOVED******REMOVED*** Option C — Wave 16+ feature

- Model v3 训练（多语言 + 大 KB + LoRA refresh）— 需 GPU
- session ***REMOVED***7 P1 backlog 残（rich-text annotation / citation density viz / multi-author collab）
- 真实 Stripe 接入（user 配 dashboard + webhook）

---

***REMOVED******REMOVED*** 6. 关键文件入口（起手必读）

| File | 用途 |
|---|---|
| **本文件** | session ***REMOVED***12 起手快速摘要 |
| `docs/sessions/session-11-close-out.md` | session ***REMOVED***11 详细总结（21 PR breakdown） |
| `docs/sessions/SESSION-11-HANDOFF.md` | session ***REMOVED***11 起手时的交接（session ***REMOVED***10 末态） |
| `docs/security/2026-05-20-history-key-audit.md` | B7 audit doc（在 `audit/p0-history-key-scrub-1779210404` 未 merge branch，**含 plaintext key**） |
| `docs/deployment/PYPI_PUBLISH.md` | PyPI publish setup 指引（user 配 token 步骤） |
| `CHANGELOG.md` | v0.4.0 / v0.4.1 / v0.5.0 entry |
| `paper/` | 5 papers arXiv-ready (anti-phacking-unified / c4-reject-aware-v0.2 / d1-block-bootstrap-ews / cve-preregistration-fail / pre-registered-replication) |
| `packages/{soc-pipeline,guarded-llm,cross-judge}/` | 3 PyPI-ready packages（待 publish） |

---

***REMOVED******REMOVED*** 7. 起手 5 步（session ***REMOVED***12）

```bash
cd ~/Projects/structural-isomorphism
git pull origin main                                          ***REMOVED*** HEAD 应 = 9febcc9
git log --oneline -10                                         ***REMOVED*** 看 wave 4 PR
cat docs/sessions/SESSION-12-HANDOFF.md                       ***REMOVED*** 本文件
gh run list --branch main --limit 12                          ***REMOVED*** 看 CI 状态
```

如果 user 已经 rotate key + 删 audit branch：起手第一句

> "B7 key 已 rotate + audit branch 已删，CC 帮我 §5 Option A（1 小时 OSS launch）"

否则：

> "先处理 §3 B7 紧急，然后 §5 选哪个"

---

> Session ***REMOVED***11 落幕。21 PR + 1 release + 全程 prod 4 域名 200 + 0 commit-boundary 违反 + 0 outage。
> Co-author: Claude Opus 4.7 (1M context). 2026-05-20 by 达达 (dada8899).
