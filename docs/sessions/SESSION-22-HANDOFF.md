***REMOVED*** Session ***REMOVED***22 Handoff

> 日期：2026-05-24
> 承接 SESSION-21-HANDOFF.md。
> 本 session 把 §8 的所有 🟢 + 📋 + W7-A/B/C/D 路线一次性闭环到 CC 极限，
> **所有必须用户操作的不可逆动作都已准备好材料、等你 GO**。
> 5 个 agent 并发执行，5 个 batch commit 推到 origin/main。

---

***REMOVED******REMOVED*** 0. 当前状态

- `beta.structural.bytedance.city` 健康（health 200）。
- 后端 **772 测试全过**（SESSION-21 是 756；+16 net 来自本 session 的
  waitlist 6 + billing 7 + privacy 2 + 测试发现 +1）。
- buildAnalyzeUrl node 单测 9/9 过。
- 本 session **5 个 commit** push 到 `origin/main`：

```
84b0c4f  feat(product): W7-D 6 mini-briefs landed
acb93d5  chore(release): Zenodo deposit + arXiv v0.3 submission bundles
4e70298  chore(security): git history scrub dry-run + script + audit
e942110  docs(paper): C1 v0.2 six-item pre-submission review closed
1076e67  fix: 4 green wrap-ups — fastapi 0.115 + buildAnalyzeUrl + e2e timeout + privacy export fingerprint
```

- 一个 annotated tag `soc-pipeline-v0.1.0` 创建在本地 4169928a，**未 push**
  （等用户授权 + 等 PyPI release）。
- working tree 仅剩 `scripts/train_v2.py`（别 session lineage，§2.6 不动）。

---

***REMOVED******REMOVED*** 1. 本 session 完成的工作

***REMOVED******REMOVED******REMOVED*** 1.1 SESSION-21 §8 的 4 个 🟢 收尾（全清）

**commit `1076e67`** — Agent A 落地：

| 项 | 改动 | 结果 |
|---|---|---|
| fastapi 升级 | requirements.txt 0.110.0 → 0.115.14 | 502 第二层防御；slowapi PEP 563 回归 4/4 还过 |
| buildAnalyzeUrl 抽共享 | 新建 `web/frontend/assets/js/utils/buildAnalyzeUrl.js` + 9 node 单测 + 改 4 入口 + bump cache-bust | /analyze 参数契约根治；单一权威 builder |
| struct-lint e2e 超时下调 | `web/tests/e2e/test_struct_lint.py` 210s → 10s SSE 首事件 + 180s 整体 | 流式化后超时与现实匹配 |
| privacy export 补 fingerprint | `/api/privacy/export` 含 `structural_fingerprints` 字段 + `ConnectionsStore.export_all_for_user` | DSAR 完整性；与 SESSION-21 §6 delete 对称 |

***REMOVED******REMOVED******REMOVED*** 1.2 C1 v0.2 6 项 Pre-submission Checklist 闭环

**commit `e942110`** — Agent B 落地。6 项现状：

| Item | 状态 | 说明 |
|---|---|---|
| 1. Zenodo DOI 核对 | ⚠️ 重大发现 | DOI `10.5281/zenodo.19547879` 解析到的是**项目 V1 contrastive-learning benchmark**，不是 Phase 1-5 SOC。新 deposit 必须做（commit `acb93d5` 已准备） |
| 2. Pipeline canonical tag | ✅ 完成 | annotated tag `soc-pipeline-v0.1.0` @ HEAD 4169928a 本地建好，未 push |
| 3. References [待核] | ✅ 完成 | refs 30-32 DeFi whitepaper 补 access date + URL；refs 41-45 用 `arXiv:2605.XXXXX` placeholder + reviewer-note |
| 4. Phase 2 lognormal 措辞 | ⚠️ 起草版本 | `docs/sessions/C1-v0.2-phase2-lognormal-revised-2026-05-24.md` 已 inline 进 v0.2 §3.2 §6.1，但**领域专家最终签字仍需真人** |
| 5. 同投 13-system 姊妹 | 📋 编辑决策 | `docs/sessions/C1-v0.2-sibling-submission-decision-2026-05-24.md`；CC 推荐：**post C1 first, hold sibling 6-8 weeks**（理由：epistemic dependency 反向、sibling 失败 mode 更多）；你拍 |
| 6. Domain-expert review | ⚠️ 内部 review | `docs/sessions/C1-v0.2-internal-review-2026-05-24.md`：3 hat（seismology / econophysics / neuroscience）合成 9 P0 + 9 P1 + 6 P2 issues。**5 of 9 P0 是纯编辑 CC 可在 v0.3 直接修；4 of 9 P0 需要重跑（≤2h/项）**。1 P0 framing 标给作者：Phase 4 §3.4 报 γ ≈ 1.10 没回应 branching-process γ=2 预测 |

**待用户决策**：5 个 author decision points（sibling co-submission / arxiv-02 correction note / Phase 1 declustering scope / Phase 4 multi-session expansion scope / 真领域专家 review 找谁）。

***REMOVED******REMOVED******REMOVED*** 1.3 git 历史 scrub dry-run（PUBLIC release P0）

**commit `4e70298`** — Agent C 落地：

- 扫描结果：**2 个真实 key 在历史 + 当前 HEAD**
  - OpenRouter `sk-or-v1-af9ae735…`（9 次，自 2026-04-16）
  - DeepSeek `sk-ad62cc6d…`（12 次，自 2026-05-13）
  - 21 raw 命中 × 17 distinct blobs
- 当前 HEAD 残留：`web/scripts/deploy.sh:39` + 3 个 docs 文件
- `scripts/scrub-history.sh` — 幂等、dry-run/execute/auto-patterns 三模式、内置 backup tag + bundle、**不执行 push**
- `scripts/scrub-patterns.txt` — 含 key 真值，`.gitignored`
- `docs/audit/git-history-scrub-2026-05-24.md` — 完整 runbook
- dry-run 验证：会改写 572 commit objects（261MB → 261MB，-3941 行），filtered export 0 key 残留

**待用户**：vendor 端轮换 key（你之前说先不管）→ 跑 scrub 脚本 → force-push（详见 §3）。

***REMOVED******REMOVED******REMOVED*** 1.4 Zenodo deposit + arXiv 投稿包

**commit `acb93d5`** — Agent D 落地：

```
release/zenodo/
├── .zenodo.json           ***REMOVED*** DataCite metadata，15 字段
├── dataset-v1.tar.gz       ***REMOVED*** 44MB LFS pointer，sha256: 8391a305...
├── README.md               ***REMOVED*** Zenodo description（13 系统 + 4 nulls + BibTeX）
└── manifest.txt            ***REMOVED*** 521 文件 per-file sha256 + size

release/arxiv/c1-unified-preprint-v0.3/
├── main.tex                ***REMOVED*** 1261 行，pandoc 转换 + 清理（去中文）
├── references.bib          ***REMOVED*** 35 BibTeX 条目，含 arXiv ID + Zenodo DOI placeholder
├── abstract.txt            ***REMOVED*** 249 词
├── cover-letter.txt        ***REMOVED*** categories + 6 suggested reviewers
└── main.pdf.TODO           ***REMOVED*** 本地无 LaTeX，建议走 arXiv server-side compile

docs/release/
├── zenodo-deposit-2026-05-24.md  ***REMOVED*** 上传 runbook + post-DOI substitution checklist
└── arxiv-submission-2026-05-24.md  ***REMOVED*** 上传 runbook + endorsement-check
```

**关键**：Zenodo DOI 必须先 mint（永久 + 一次性），arXiv 引用 DOI。

***REMOVED******REMOVED******REMOVED*** 1.5 W7-D 6 个 mini-brief 全落地

**commit `84b0c4f`** — Agent E 落地：

| Brief | 产物 | 状态 |
|---|---|---|
| 1. waitlist + Plausible | `api/waitlist.py` + 首页 section + 6 tests + Plausible 覆盖 26 页 | ✅ 全过 |
| 2. Stripe-mock Pro tier | `api/billing.py` + `pricing.html`（Free/Pro $19/Team $99）+ 7 tests | ✅ 全过；test mode + mock fallback |
| 3. weekly newsletter | `scripts/generate_weekly_signals.py` + `send_to_buttondown.py` + plist + 6 tests | ✅ 全过；plist 未装（步骤在 docs） |
| 4. backtest engine v0.1 | `scripts/backtest_walk_forward.py` + 2 tests | ⚠️ 跑通 pipeline 用 mock 数据（Sharpe lift -0.10），真实数据 v0.2 接入 |
| 5. UX consistency sprint | audit doc（18 finding）+ 12 CSS 落地修订 | ✅ 12/18 落地，6 deferred |
| 6. HN launch readiness | playbook + 10 Q&A FAQ | ⚠️ 标 NOT READY；blockers: demo GIF / load test / backtest v0.2 |

W7-B（guarded-llm）和 W7-C（soc-pipeline + cross-judge）三个 PyPI 包**起手已在 packages/ 完整存在**（dist/.whl + .tar.gz）；本 session 跑 `twine check` 6 个 dist 全 PASSED，等用户 PyPI token 后 `twine upload`。

---

***REMOVED******REMOVED*** 2. PUBLIC release decision-gates 全景

来自 `docs/PUBLIC_READINESS_CHECKLIST.md`，本 session 处理后状态：

| Decision gate | 状态 | 用户操作 |
|---|---|---|
| Rotate DeepSeek API key | ⏸️ 你说先不管 | 后续到 DeepSeek 控制台 |
| Rotate OpenRouter API key | ⏸️ 你说先不管 | 后续到 OpenRouter 控制台 |
| Force push scrubbed git history | ✅ Dry-run 就绪 | 见 §3.1 |
| Flip repo visibility to PUBLIC | ✅ 准备就绪 | 见 §3.2 |
| Submit C1 v0.3 to arXiv | ✅ 投稿包就绪 | 见 §3.3 |
| Mint Zenodo DOI | ✅ Deposit 就绪 | 见 §3.4 |
| Publish soc-pipeline 0.1.0 to PyPI | ✅ Wheel 就绪 + twine check PASSED | 见 §3.5 |
| Publish guarded-llm 0.1.0 to PyPI | ✅ 同上 | 见 §3.5 |

P1 项里 `Phase Detector browser-side runtime issue` + `universality-classes.json duplicate class_id` 在 SESSION-20 已闭环。

---

***REMOVED******REMOVED*** 3. 用户授权清单（每项 1 行命令 / 1 步操作）

按依赖顺序排，从上往下做：

***REMOVED******REMOVED******REMOVED*** 3.1 git history scrub（force push）

```bash
cd ~/Projects/structural-isomorphism

***REMOVED*** Step 1: 准备 patterns（自动从 gitleaks 扫，或手动填 scripts/scrub-patterns.txt）
bash scripts/scrub-history.sh --auto-patterns      ***REMOVED*** 或手动编辑 patterns 文件

***REMOVED*** Step 2: dry-run 再核对一次
bash scripts/scrub-history.sh --dry-run

***REMOVED*** Step 3: 真改写（自动建 backup tag + bundle）
bash scripts/scrub-history.sh --execute

***REMOVED*** Step 4: 验证 0 key 残留
git log --all -p | grep -E "sk-or-v1-af9|sk-ad62cc6d" && echo "STILL THERE" || echo "CLEAN"
gitleaks detect --no-banner --redact

***REMOVED*** Step 5: force-push（不可逆）
git push --force-with-lease --all origin
git push --force-with-lease --tags origin
```

详细回滚 + fork 协调见 `docs/audit/git-history-scrub-2026-05-24.md`。

***REMOVED******REMOVED******REMOVED*** 3.2 GitHub repo 翻 PUBLIC

1. GitHub → Settings → "Change repository visibility" → Make public → 输入 repo 名确认
2. 完了之后用 `gh repo view dada8899/structural-isomorphism --json visibility` 验证

***REMOVED******REMOVED******REMOVED*** 3.3 Zenodo DOI mint（**先于 arXiv**）

详细 runbook 在 `docs/release/zenodo-deposit-2026-05-24.md`，速查：

1. 登录 https://zenodo.org（用 ORCID）
2. 「New Upload」→ 拖 `release/zenodo/dataset-v1.tar.gz`
3. Metadata 从 `release/zenodo/.zenodo.json` 复制粘贴（手动填 ORCID）
4. Save Draft → preview → Publish（**永久，不可撤回**）
5. 拿到 DOI（形如 `10.5281/zenodo.XXXXXXX`）
6. 替换占位符（3 处）：
   - `release/zenodo/.zenodo.json` notes 字段
   - `release/arxiv/c1-unified-preprint-v0.3/references.bib` `si2026zenodo` 条目
   - `docs/sessions/C1-unified-preprint-draft-v0.2.md` §Appendix-A 和 ref 45

***REMOVED******REMOVED******REMOVED*** 3.4 arXiv v0.3 提交

详细 runbook 在 `docs/release/arxiv-submission-2026-05-24.md`，速查：

1. 登录 https://arxiv.org
2. 检查 `q-bio.NC` / `q-fin.ST` endorsement（如缺需找 endorser）
3. New Submission → upload `release/arxiv/c1-unified-preprint-v0.3/` 整目录（zip 起来）
4. Categories：primary `physics.soc-ph`，cross-list `q-fin.ST` + `q-bio.NC`
5. Abstract / cover letter 粘贴
6. Preview arXiv server-side compile 的 PDF
7. Submit（**不可撤回**，moderation 1-3 天）
8. 拿到 arXiv ID（形如 `2605.XXXXX`）后替换占位符（多处，见 doc）

***REMOVED******REMOVED******REMOVED*** 3.5 PyPI 发包（3 个）

```bash
***REMOVED*** 准备 PyPI token：https://pypi.org/manage/account/token/
export TWINE_USERNAME=__token__
export TWINE_PASSWORD='pypi-...'   ***REMOVED*** 你的 token

***REMOVED*** 发 guarded-llm 0.1.0
cd ~/Projects/structural-isomorphism/packages/guarded-llm
python -m twine upload dist/*

***REMOVED*** 发 soc-pipeline 0.1.0
cd ../soc-pipeline
python -m twine upload dist/*

***REMOVED*** 发 cross-judge 0.1.0
cd ../cross-judge
python -m twine upload dist/*

***REMOVED*** 验证（每个）
pip install guarded-llm soc-pipeline cross-judge
```

***REMOVED******REMOVED******REMOVED*** 3.6 push pipeline canonical tag

PyPI 发包成功后：

```bash
git push origin soc-pipeline-v0.1.0
```

***REMOVED******REMOVED******REMOVED*** 3.7 [可选] 装 weekly newsletter cron

```bash
cp scripts/launchd/com.structural.weekly-newsletter.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
launchctl list | grep structural   ***REMOVED*** 验证
```

---

***REMOVED******REMOVED*** 4. 仍需真人 / 仍未做的事

***REMOVED******REMOVED******REMOVED*** 4.1 真领域专家 review（Item 6 of C1 checklist）

CC 内部 review 在 `docs/sessions/C1-v0.2-internal-review-2026-05-24.md`。
真要稳，需要 3 个真人 reviewer：

- Phase 1（地震）：找一个 seismology / statistical seismology PhD
- Phase 2（S&P 500）：找一个 econophysics / quant finance research lead
- Phase 4（小鼠皮层）：找一个 neural avalanche / Beggs-Plenz traditional lab PhD

**建议**：发预印本到 arXiv 前先发邮件给 3-5 个 reviewer 候选，提供 v0.3 PDF + 1 周窗口要 1 小时反馈。

***REMOVED******REMOVED******REMOVED*** 4.2 Phase 4 framing P0（CC 可改但需作者拍）

C1 v0.2 §3.4 报 γ ≈ 1.10 没回应 branching-process γ=2 预测。真神经科学 reviewer 会卡在这里。建议在 v0.3 加一段：
> "Our γ ≈ 1.10 is consistent with subsampled estimates in the avalanche literature (refs to add) and deviates from the mean-field branching-process prediction γ=2; this likely reflects the single-session, single-region scope rather than a deep universality-class membership claim."

如果你 GO，CC 可以下个 session inline 改 v0.2。

***REMOVED******REMOVED******REMOVED*** 4.3 arxiv-02 correction note

C1 §3.2 标了 arxiv-02 原文 "power-law strongly dominates lognormal" 是 sign-interpretation error。**是否给 arxiv-02 发独立勘误**是你的决定。

***REMOVED******REMOVED******REMOVED*** 4.4 backtest v0.2 真实数据

W7-D §4 backtest 用 mock 跑通 pipeline，真实数据接入是 v0.2 工作（D1 Phase Detector 真实 100 公司 + yfinance）。**3 工程日**量，可以下个 session 开做。

***REMOVED******REMOVED******REMOVED*** 4.5 HN launch 准备

`docs/community/launch/hn-launch-readiness-2026-05-24.md` 标 NOT READY。剩下：演示 GIF / 负载测试 / backtest v0.2 / show HN 标题候选定稿。

---

***REMOVED******REMOVED*** 5. 下个 session 起手指令

```
读 SESSION-22-HANDOFF.md。站点健康，5 commit 推到 origin/main。

如果用户已经完成 §3 的某些动作：
  - 如果 git history 已 force-push：验证 gitleaks 0 命中 + 通知协作者 re-clone
  - 如果 Zenodo DOI 已 mint：跑 sed 替换 3 处占位符 + commit
  - 如果 arXiv ID 已下：跑 sed 替换多处占位符 + commit + 在 README 加 badge
  - 如果 PyPI 包已发：拉 pip install 在干净 venv 验证 + push soc-pipeline-v0.1.0 tag
  - 如果 repo 已 PUBLIC：扫 GitHub Issues + 答 first community questions

如果用户都没做：本 session 已闭环 CC 极限，等用户。

可以独立做的：
  (a) Phase 4 framing P0 在 v0.3 inline 修（§4.2，CC 可改但需作者拍）
  (b) backtest v0.2 真实数据接入（§4.4，3 工程日）
  (c) demo GIF / 演示视频（§4.5，HN launch 阻塞）
  (d) D1 Phase Detector auth + Stripe 接入真实付费（W7-B/W7-D 后续）
```

---

***REMOVED******REMOVED*** 6. 本 session 的执行模式（值得复盘）

- **5 个 agent 并发**，每个独立 scope，干完不 commit，主对话统一审 + 分批 commit
  → 避免 git index lock 冲突，commit message 干净
- **scripts/train_v2.py** 仍是别 session in-flight（自 SESSION-20 起），本 session
  按 §2.6 commit 边界铁律完全不动
- **5 commit 按产品边界**：fix（4 wrap-ups）/ docs(paper)（C1 review）/
  chore(security)（git scrub）/ chore(release)（Zenodo+arXiv）/ feat(product)（W7-D）
- **未做的并非"漏做"，是有意识停下**：所有不可逆动作（force push / PUBLIC flip /
  arXiv 投稿 / Zenodo mint / PyPI upload / key 轮换）按 CLAUDE.md
  「破坏性操作必先确认」铁律等用户 GO
- **诚实备注**：W7-D §4 backtest 用 mock 数据跑通 pipeline，Sharpe lift -0.10
  不代表真实 alpha。output markdown 里有 explicit MOCK banner，没掩盖
