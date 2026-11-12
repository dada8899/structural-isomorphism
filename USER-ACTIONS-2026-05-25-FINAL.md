# 🎯 USER ACTIONS — 2026-05-25 SESSION-23 收尾

> 本 session（SESSION-23）CC 已把所有能做的工作完成 + push（**33 commits**，HEAD on `origin/main`）。
> 下面列出**只有你能做**的 7 项操作。每项独立，按时间紧急度排，每项都附 5 分钟内可 copy-paste 的指令。

---

## ✅ CC 已完成（无需你操作，已经在 `origin/main`）

- 18 个 universality class 全验证（10 PASS / 6 REJECT / 2 INCONCLUSIVE / 5 SPLIT / 1 MERGE）
- KB master 已 promote 到 **5333 entries**（旧 4888 archive 在 `data/kb-5000-merged.jsonl.archive-pre-v0.4-merge`，已 gitignore）
- 40 个 unmapped type_id 已 remap 到现有 84 个数字 ID（option (a)）
- C1 v0.4 paper draft 完成（459 lines markdown + 2536 lines tex）
- arXiv v0.4 submission bundle 完整（`release/arxiv/c1-unified-preprint-v0.4/` 7 个文件）
- 4 PyPI packages：3 live + `reject-aware-critic` v0.1.0 ready（**tag 已本地创建**，未 push）
- 4 read-only audits + 4 P0 fixes 全 commit
- README + README-zh + CITATION + CHANGELOG sync 到 v0.4
- CI 两个红的 workflow 修了（`embedding_bridge` allow_pickle + `api-types.ts` 3 字段）
- 5 stale GitHub issues 关闭（带 evidence）
- 6 senior outreach 邮件草稿（`docs/outreach/2026-05-25-emails/`）
- 负面结果 launch 材料（博客 + LinkedIn + HN title #6 候选）

---

## 🔴 你的 7 项操作（按时间紧急度排）

### 1. 设 GitHub Secret `PYPI_API_TOKEN`（2 分钟，阻塞 #2）

CC 没有 GitHub Settings 写权限。

**步骤**：
1. 登录 https://github.com/dada8899/structural-isomorphism/settings/secrets/actions
2. 点 "New repository secret"
3. Name: `PYPI_API_TOKEN`
4. Value: 你从 https://pypi.org/manage/account/token/ 拿到的 token（必须是 "Entire account" 或包含 `reject-aware-critic` project 范围的 token）
5. Save

---

### 2. Push `reject-aware-critic-v0.1.0` tag（1 分钟，触发首次 PyPI 发布）

**必须在 #1 完成后**——不然 workflow 会跑但发布失败。

```bash
cd /Users/dadamini/Projects/structural-isomorphism
git push origin reject-aware-critic-v0.1.0
```

跑完后看 https://github.com/dada8899/structural-isomorphism/actions 应该看到 `release-packages.yml` workflow 自动启动 → 5-10 分钟后 https://pypi.org/project/reject-aware-critic/ 会有 0.1.0 出现。

---

### 3. API key 轮换（5 分钟，安全卫生）

CC 做不了，外部 console 操作。

**DeepSeek**：
1. 登录 https://platform.deepseek.com/api_keys
2. 新建 key
3. SSH 到 VPS 改 prod .env：
   ```bash
   ssh vps
   cd /root/Projects/structural-isomorphism
   sed -i 's|DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=<new-key>|' .env
   systemctl restart structural-web
   ```
4. 旧 key 在 DeepSeek console 删除

**OpenRouter**：同上，console 在 https://openrouter.ai/keys

---

### 4. Zenodo upload + mint DOI（10 分钟，arXiv submit 前置）

CC 做不了，需要登录 + 拖文件。

**步骤**：
1. 登录 https://zenodo.org
2. New Upload
3. 拖入 `release/zenodo/dataset-v1.tar.gz`（44 MB LFS — 之前 SESSION-22 已准备好）
4. 从 `release/zenodo/.zenodo.json` 复制 metadata 到表单（title / authors / description / keywords / license CC-BY-4.0）
5. **重要**：在 description 中标 "Companion to arXiv:[PENDING_ARXIV_ID]"——arxiv 出来后再回填
6. Publish → 拿到 DOI（格式 `10.5281/zenodo.<NNN>`）
7. 回到本地跑：
   ```bash
   cd /Users/dadamini/Projects/structural-isomorphism
   # 替换占位符
   grep -rln "PENDING_ZENODO_DOI" release/arxiv/c1-unified-preprint-v0.4/ docs/launch/ docs/outreach/ README.md README-zh.md | \
     xargs sed -i '' 's|PENDING_ZENODO_DOI|10.5281/zenodo.<新DOI>|g'
   git add -A
   git commit -m "chore: backfill Zenodo DOI 10.5281/zenodo.<NNN>"
   git push
   ```

---

### 5. arXiv v0.4 submit（15 分钟，#4 完成后）

CC 做不了，需要登录 arxiv.org。

**完整 step-by-step 在**：`release/arxiv/c1-unified-preprint-v0.4/README.md`

简版：
1. https://arxiv.org/submit → New Submission → TeX/LaTeX
2. Upload `release/arxiv/c1-unified-preprint-v0.4/` 下的 `main.tex` + `references.bib`（用 zip）
3. Primary archive: `physics.soc-ph`
4. Cross-list: `q-fin.ST`, `q-bio.NC`, `cond-mat.stat-mech`
5. 粘贴 `abstract.txt` 内容
6. Title: "Structural Isomorphism: Cross-Domain Universality Validation Pipeline (v0.4 — Taxonomy Closure)"
7. Authors: 万庆徽 (Wan Qinghui)
8. Comments: "v0.4 supersedes v0.3 with full 18-class taxonomy closure; companion: github.com/dada8899/structural-isomorphism"
9. Submit → 等 24-48h 拿 arXiv ID（格式 `2605.NNNNN`）
10. 拿到 ID 后回到本地：
    ```bash
    cd /Users/dadamini/Projects/structural-isomorphism
    grep -rln "PENDING_ARXIV_ID" docs/launch/ docs/outreach/ release/arxiv/c1-unified-preprint-v0.4/README.md | \
      xargs sed -i '' 's|PENDING_ARXIV_ID|<新ID>|g'
    git add -A && git commit -m "chore: backfill arXiv ID <新ID>" && git push
    ```

---

### 6. 发 6 封 senior outreach 邮件（30 分钟，#5 拿到 arXiv ID 后）

CC 做不了，需要你的邮箱。

6 封邮件在 `docs/outreach/2026-05-25-emails/`：
- `01-sornette.md` → didier.sornette@ethz.ch
- `02-stumpf.md` → mstumpf@unimelb.edu.au
- `03-porter.md` → mason@math.ucla.edu
- `04-clauset.md` → aaron.clauset@colorado.edu
- `05-sethna.md` → sethna@cornell.edu
- `06-bouchaud.md` → jean-philippe.bouchaud@cfm.com

发送顺序 + 节奏在 `docs/outreach/2026-05-25-emails/00-INDEX.md`（3-tier，每封间隔 1-2 天）。

**发送前**：每封邮件中 `[PENDING_ARXIV_ID]` / `[PENDING_ZENODO_DOI]` 都要替换（#4 #5 完成后会自动 sed 替换上）。

---

### 7. HN launch + Stripe live mode 决策（你拍板）

非紧急，但前置 #1-#6 都完成后做。

**HN launch**：推荐 2026-06-02 09:00 ET。前置：
- arXiv ID 拿到 + Zenodo DOI 上 + 3 个 senior 收到回信（至少 1 个有 substantive 反馈）

**HN 标题**：默认走 `docs/launch/hn-title-candidates-2026-05-24.md` 的 **#6b "Honesty funnel"**——基于 backtest 失败 + 33% reject rate 的 narrative，是 unforgeable signal。

**Stripe live mode**：取决于你看 W7-D pivot 后是否真要做 B2B SaaS。LinkedIn `docs/launch/linkedin-b2b-pilot-probe-2026-05-25.md` 是试水文案——发了之后看 1-2 个 pilot 客户回复，再决定是否走 Stripe。

---

## 📁 关键文件速查

| 任务 | 文件 |
|---|---|
| arXiv 提交 | `release/arxiv/c1-unified-preprint-v0.4/main.tex` + `README.md` |
| Zenodo 上传 | `release/zenodo/dataset-v1.tar.gz` + `.zenodo.json` |
| 6 outreach 邮件 | `docs/outreach/2026-05-25-emails/01..06-*.md` |
| HN 标题 | `docs/launch/hn-title-candidates-2026-05-24.md` #6 |
| LinkedIn probe | `docs/launch/linkedin-b2b-pilot-probe-2026-05-25.md` |
| 负面结果博客 | `docs/launch/blog-post-negative-results-2026-05-25.md` |
| SESSION-23 接力 | `docs/sessions/SESSION-23-HANDOFF.md` |
| 类型 ID remap 决策 | `docs/fixes/2026-05-25-type-id-remap-final.md` |

---

## 📊 SESSION-23 数字总览

| 维度 | SESSION-22 末 | SESSION-23 末 | Δ |
|---|---|---|---|
| Commits pushed | 26 | **33** | +33 |
| SOC validation systems | 27 | **45+** | +18 |
| Universality classes verified | 10/26 | **18/18 v0.4 closed** | +8 PASS + 6 REJECT + 2 INCONCLUSIVE |
| MERGE/SPLIT decisions | 0 | **5 SPLIT + 1 MERGE** | new |
| KB entries (master) | 4888 | **5333** | +445 真实净增 |
| PyPI packages | 3 live | 3 live + **1 ready** | +1 (待 push tag) |
| C1 paper | v0.3 | **v0.4 draft + tex** | new |
| Open GitHub issues | 18 | **13** | -5 closed |
| CI workflows red | 2 | **0** | fixed |
| Audit reports | 0 | **4** | new |
| Fix reports | 0 | **4** | new |
| Senior outreach emails | 0 | **6 drafts** | new |
| Launch materials | 13 (v0.3) | **+3 new** (negative-results blog + LinkedIn probe + HN #6) | |

**3 个 P0 audit findings 全部 fixed**，无 outstanding。

---

## 🎬 下次 session 起手指令

```
读 docs/sessions/SESSION-23-HANDOFF.md + USER-ACTIONS-2026-05-25-FINAL.md
当前 main HEAD: <main 对话会告诉>
所有 wave + audit + fixes 已完成。
检查用户清单 7 项完成度，按下一项启动。
```

---

**End of USER ACTIONS doc.**
