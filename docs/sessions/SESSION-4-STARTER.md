# Session #4 Starter — 全权授权执行清单

> Session #3 已完成所有 engineering / paper / product / community / future-planning 工作（41 PRs + F1 P1 fix = 42 PRs merged）。Session #4 = **执行不可逆 / 对外发布 / 需 token 的 last-mile actions**。
>
> 用户已说"全部授权"，session #4 起手即可按本文档顺序执行，无需再问。
>
> **起手第一件事**：读本文件 + `HANDOFF.md`，然后按 §0 跑环境检查。

---

## §0 起手 60 秒 — 环境 + 凭证扫描

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -5         # head 应该是 session #3 W9 finalize merge (commit 6f9efe6 或之后含 F1 P1 fix 的 0380327)

# 凭证扫描
gh auth status                                          # 必须 ✓ logged in dada8899 with repo scope
env | grep -iE "deepseek|pypi|zenodo" | sed 's/=.*/=<SET>/'  # 看 token 是否在 env
ls ~/.pypirc 2>&1                                        # 看 pypi config
which git-filter-repo twine pandoc 2>&1                  # 看工具是否装好
```

### 必须的凭证清单（按需准备）

| Action | 凭证 | 获取方式 |
|--------|------|----------|
| Git history scrub + force push | gh CLI auth + `repo` scope | 已就绪 (gh auth status) |
| Repo PUBLIC flip | gh CLI auth + admin perm | 已就绪 |
| PyPI publish | `PYPI_TOKEN` | https://pypi.org/manage/account/token/ → "Add API token", scope = "entire account" first publish |
| Zenodo mint DOI | `ZENODO_ACCESS_TOKEN` | https://zenodo.org/account/settings/applications/tokens/new/ → scope: deposit:write + deposit:actions |
| arXiv submission | arxiv.org 账号 + 物理类 endorsement | https://arxiv.org/user/register (新账号需 endorsement，老账号直接可投) |
| DeepSeek key rotation | 登录 platform.deepseek.com | 用户 web 操作 |

---

## §1 当前 main 状态（session #3 + F1 P1 fix 后）

- **main HEAD**: `0380327` (F1 P1 fix merge) — 42 PRs since session #2 base `332049b`
- **production live**:
  - https://phase.bytedance.city/ (HTTPS, 97 companies, **W6-D narrative + F1 React error fix applied + redeployed**)
  - https://beta.structural.bytedance.city/ (5 new pages: papers/methods/taxonomy-v2/start-here/about)
- **packages built (wheel ready, NOT yet on PyPI)**:
  - `packages/soc-pipeline/` (1085 src LOC + 37 tests + 5 notebooks)
  - `packages/guarded-llm/` (1624 src LOC + 52 tests + 4 providers)
- **dataset ready (NOT yet on Zenodo)**:
  - `dataset/v1/` (244 files / 99 MB / 16 systems / 4 nulls / 35 yamls + MINT_DOI_RUNBOOK.md)
- **paper drafts ready (NOT yet on arXiv)**:
  - `paper/v0-unified-pipeline-2026-05-13.md` v0.3 — 16,109 words (C1 unified, Scheffer p revised)
  - `paper/arxiv-drafts/2026-05-13/01-04*.md` — 4 solo papers (Phase 1/2/3/4)
  - `paper/c4-reject-aware-pipeline-2026-05-13.md` — C4 methodology, 8,164 words
- **OSS scaffolding done**:
  - LICENSE / CONTRIBUTING / CODE_OF_CONDUCT / GOVERNANCE / .github/ISSUE_TEMPLATE + workflow / PUBLIC_READINESS_CHECKLIST

---

## §2 Session #4 执行顺序（按依赖排，每步独立可暂停）

### Step 1: Rotate DeepSeek API key （≤ 5 min, **用户 web action**）

**Why first**: 老 key 可能 leak 在 git history（W5-B 反馈）。先 rotate，老 key 立即失效，再 scrub 历史就没风险。

**Steps**:
1. 登录 https://platform.deepseek.com → Account → API Keys
2. Revoke 老 key (前缀 `sk-ad62...`)
3. Create new key, copy
4. 更新本地 + VPS env：
   ```bash
   # Local: 加到 ~/.zshrc 或 .env
   export DEEPSEEK_API_KEY="sk-NEW..."

   # VPS:
   ssh root@43.156.233.71 'cat >> /etc/environment <<EOF
   DEEPSEEK_API_KEY=sk-NEW...
   EOF
   systemctl daemon-reload
   systemctl restart phase-detector-api'
   ```

**Verify**: 跑一个 LLM call confirm new key works
```bash
DEEPSEEK_API_KEY="sk-NEW..." python -c "
import os, requests
r = requests.post('https://api.deepseek.com/chat/completions',
  headers={'Authorization': f'Bearer {os.getenv(\"DEEPSEEK_API_KEY\")}'},
  json={'model':'deepseek-chat','messages':[{'role':'user','content':'ping'}]})
print(r.status_code, r.json().get('choices',[{}])[0].get('message',{}).get('content','no resp'))
"
```

### Step 2: Scrub git history （15-20 min, irreversible, **all auto**）

**Why**: 历史 commits 仍包含老 key 引用（即使已 rotate，从 OSS 卫生角度该清除）。

**Steps**:
```bash
# Install
pip install git-filter-repo

# Backup repo first (safety)
cd ~/Projects/
cp -r structural-isomorphism structural-isomorphism-backup-pre-scrub-2026-05-14

# Identify all secret patterns to scrub
cd ~/Projects/structural-isomorphism
git log --all --full-history --source -p | grep -oE "sk-[a-zA-Z0-9_-]{20,}" | sort -u > /tmp/keys-found.txt
cat /tmp/keys-found.txt  # 应列出 1-N 个 key fragment

# Create replacement file
cat > /tmp/secret-replacements.txt <<EOF
sk-ad62***==>***REDACTED***
EOF
# Add each unique key to /tmp/secret-replacements.txt as `<key>==>***REDACTED***`

# Run scrub
git filter-repo --replace-text /tmp/secret-replacements.txt --force

# Verify scrub clean
git log --all -p | grep -E "sk-[a-zA-Z0-9_-]{20,}" | head -5
# Should be empty
```

**Force push cleaned history**:
```bash
# Re-add origin (filter-repo removes it for safety)
git remote add origin https://github.com/dada8899/structural-isomorphism.git

# Force push (irreversible)
git push --force-with-lease --all origin
git push --force-with-lease --tags origin
```

**Rollback (if scrub goes wrong)**:
```bash
cd ~/Projects/
rm -rf structural-isomorphism
mv structural-isomorphism-backup-pre-scrub-2026-05-14 structural-isomorphism
cd structural-isomorphism
git push --force origin main  # restore origin to pre-scrub state
```

### Step 3: Verify history clean + cleanup local clones （5 min）

```bash
# Verify GitHub remote also clean
gh api repos/dada8899/structural-isomorphism/commits | jq -r '.[].sha' | head -5
# spot-check a recent commit:
gh api repos/dada8899/structural-isomorphism/git/blobs/$(gh api repos/dada8899/structural-isomorphism/contents/v4/scripts/b3_ensemble.py | jq -r .sha) | jq -r .content | base64 -d | grep -c "sk-ad62"
# should output 0

# Clean VPS clone too
ssh root@43.156.233.71 'cd /root/Projects/structural-isomorphism-v4 && git fetch && git reset --hard origin/main'
```

### Step 4: Flip repo PUBLIC （1 min, **auto via gh**）

```bash
# Before:
gh repo view dada8899/structural-isomorphism --json visibility -q .visibility   # "PRIVATE"

# Flip
gh repo edit dada8899/structural-isomorphism --visibility public --accept-visibility-change-consequences

# After:
gh repo view dada8899/structural-isomorphism --json visibility -q .visibility   # "PUBLIC"

# Verify externally accessible
curl -sI https://github.com/dada8899/structural-isomorphism | head -3
```

### Step 5: PyPI publish — soc-pipeline + guarded-llm （10 min, **需 PYPI_TOKEN**）

```bash
pip install build twine

# Rebuild wheels fresh (safer than stale)
cd packages/soc-pipeline
rm -rf dist/ build/
python -m build
twine check dist/*   # 必须 PASSED
cd ../..

cd packages/guarded-llm
rm -rf dist/ build/
python -m build
twine check dist/*
cd ../..

# Publish (use TestPyPI first if cautious)
export TWINE_USERNAME="__token__"
export TWINE_PASSWORD="pypi-..."  # 你的 PYPI_TOKEN

# soc-pipeline
twine upload packages/soc-pipeline/dist/*

# guarded-llm
twine upload packages/guarded-llm/dist/*

# Verify
pip install soc-pipeline==0.1.0
python -c "from soc_pipeline import fit_clauset_powerlaw; print('ok')"
pip install guarded-llm==0.1.0
python -c "from guarded_llm import guardrailed_llm_call; print('ok')"
```

**Browse pages**:
- https://pypi.org/project/soc-pipeline/
- https://pypi.org/project/guarded-llm/

### Step 6: Zenodo mint DOI for dataset/v1 （15 min, **需 ZENODO_ACCESS_TOKEN**）

```bash
# Tarball the bundle
cd dataset/v1/
tar czf /tmp/structural-isomorphism-dataset-v1.tar.gz --dereference --exclude='.DS_Store' .
ls -lh /tmp/structural-isomorphism-dataset-v1.tar.gz   # ~100 MB
cd ../..

# Create deposition
ZENODO_TOKEN="..."   # 你的 token
RESP=$(curl -s -X POST "https://zenodo.org/api/deposit/depositions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  -d '{}')
DEP_ID=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['id'])")
BUCKET=$(echo $RESP | python -c "import sys,json; print(json.load(sys.stdin)['links']['bucket'])")
echo "Deposition: $DEP_ID  Bucket: $BUCKET"

# Upload
curl --progress-bar -X PUT "$BUCKET/structural-isomorphism-dataset-v1.tar.gz" \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  --data-binary @/tmp/structural-isomorphism-dataset-v1.tar.gz

# Add metadata
cat > /tmp/zenodo-metadata.json <<'JSON'
{"metadata":{
  "title":"Cross-domain SOC validation dataset (v1, 2026-05-13)",
  "upload_type":"dataset",
  "description":"13 verified universality systems + 4 null controls + B1xB3 taxonomy verdicts (21 classes) + frozen pipeline. Cross-domain validation of self-organized criticality. Companion to arXiv preprint (placeholder).",
  "creators":[{"name":"dada8899","affiliation":"Independent Research"}],
  "access_right":"open",
  "license":"CC-BY-4.0",
  "keywords":["self-organized criticality","universality","power-law","cross-domain validation","LLM ensemble"]
}}
JSON

curl -s -X PUT "https://zenodo.org/api/deposit/depositions/$DEP_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZENODO_TOKEN" \
  -d @/tmp/zenodo-metadata.json

# Visit zenodo.org to review + click PUBLISH
echo "Review at: https://zenodo.org/deposit/$DEP_ID"
echo "After publish, DOI will be: https://doi.org/10.5281/zenodo.<ID>"
```

**Then update repo refs**:
- `dataset/v1/CITATION.cff` doi field
- `dataset/v1/manifest.json` doi field
- `README.md` add DOI badge
- 4 paper drafts add `[Zenodo dataset: 10.5281/zenodo.<ID>]` in Data Availability section

Commit + push 这些更新。

### Step 7: arXiv submission — C1 v0.3 first （30 min web form, **需 arxiv.org 账号**）

**arXiv 没有 submission API**，必须 web form。

1. 装 pandoc (`brew install pandoc` 或 `apt install pandoc`)
2. Build PDF：
   ```bash
   pandoc paper/v0-unified-pipeline-2026-05-13.md \
     -o /tmp/c1-unified-v0.3.pdf \
     --pdf-engine=xelatex \
     --variable=geometry:margin=1in \
     --variable=mainfont="Times New Roman" \
     --toc
   ```
3. 登录 https://arxiv.org/user → New submission
4. Metadata (从 paper 顶部 copy)：
   - Title: A pipeline for cross-domain validation of self-organized criticality: thirteen systems, one method
   - Authors: <your name> (Independent Research)
   - Abstract: <250 字 from paper §abstract>
   - Primary: `cond-mat.stat-mech`
   - Cross-list: `physics.data-an`
   - Comments: "16 pages, 12 figures, 60 references; dataset Zenodo DOI:10.5281/zenodo.<ID from step 6>; code github.com/dada8899/structural-isomorphism"
   - License: CC BY 4.0
5. Upload `/tmp/c1-unified-v0.3.pdf`
6. Preview → Submit
7. 等 arXiv mod review（1-3 working day）

**Then repeat for C2 4 solo + C4 red-team**（推荐 stagger 2-3 days 间投，避免一次性 spam）。

C4 投 `stat.ML` primary + `cs.LG` cross-list（LLM ensemble methodology）。

### Step 8: 更新 cross-refs (10 min)

得到 arXiv IDs (e.g. `2605.XXXXX`) 后更新：
- `README.md`: arXiv badge
- `dataset/v1/CITATION.cff`: arXiv identifier
- `dataset/v1/manifest.json`: paper reference
- `web/frontend/index.html`: cite arXiv link
- GitHub release notes
- Zenodo deposition (related_identifiers: isSupplementTo arXiv:<ID>)

### Step 9: GitHub release v0.3.0 (5 min)

```bash
gh release create v0.3.0 \
  --title "structural-isomorphism v0.3 — session #3 mega-sprint" \
  --notes "$(cat <<'EOF'
## Session #3 deliverables (2026-05-13)

41 PRs merged across 9 waves. Key items:

- **phase.bytedance.city LIVE** — Phase Detector with 97 companies, HTTPS, full Next.js + FastAPI stack
- **2 PyPI packages**: \`soc-pipeline\` 0.1.0 + \`guarded-llm\` 0.1.0
- **Dataset DOI**: 10.5281/zenodo.<ID>
- **arXiv preprints**: 2605.XXXXX (C1 unified), 2605.YYYYY (C4 red-team), + 4 solo Phase papers
- **Scientific correction**: Scheffer A2 p-value revised from <1e-186 to 0.074 via block-bootstrap (verdict INCONCLUSIVE)
- **6-role peer review**: scholar / researcher / PM / student / UX / copywriter — all P0 items applied
- **213 tests across 3 tiers**: unit + integration + e2e

See docs/sessions/structural-iso-session-3-end.md for full retro.
EOF
)"
```

### Step 10: HN / Reddit / Twitter launch announcements (optional, **scheduled**)

不在 session #4 强制范围。投 arXiv 后 1-2 周再做（让 paper 先有 reading time）。

Outreach drafts 应该提前写好 — 见下方 §4 ready-made templates section（待 session #5 完成）。

---

## §3 Risk gates / rollback

| Action | Reversible? | Rollback |
|--------|------------|----------|
| Step 1 (rotate key) | Yes — generate another new key | — |
| Step 2 (history scrub) | **NO** — irreversible if force-pushed. Mitigation: backup repo first |
| Step 3 (verify) | n/a | — |
| Step 4 (PUBLIC flip) | Yes — `gh repo edit --visibility private` | — |
| Step 5 (PyPI) | **NO** — can yank version but never republish same version# | mitigation: TestPyPI first |
| Step 6 (Zenodo) | **NO** — DOI permanent once published. Can release new version v1.1 | mitigation: review before clicking Publish |
| Step 7 (arXiv) | **Withdraw** option exists but discouraged | mitigation: preview carefully |
| Step 8-9 | Yes | — |

---

## §4 已知次要事项（不阻塞 session #4 但 nice-to-do）

1. **agent-soc-solar worktree leftover** (`.claude/worktrees/agent-soc-solar`): from earlier session, can `git worktree remove --force` cleanup
2. **`b.ai` / `easyrouter.io` backup LLM keys** (memory `reference_backup_llm_keys_2026_05_03.md`): 可能也需要 rotate (low priority)
3. **bot probing /waitlist POST endpoints**: F1 加了 error boundary 抵御，但可以加 rate limiting middleware in next session
4. **Newsletter Buttondown account**: W8-D scaffolding 已 ready, 待 user 注册 buttondown.email 并配置 DNS CNAME
5. **D1 100 → 500 companies expansion**: W7-D 排在 P2，需新一轮 LLM batch 跑（cost ~$1-2）
6. **Backtest engine v0.1**: W7-D 关键决策点（alpha-product vs narrative-product），需要 historical StructTuple time series
7. **C3 Taxonomy v2 paper**: 需 senior physicist co-author（W7-A 建议先发 C1 等 reviewer 反馈再追）
8. **Mac launchd / monitor 集成**: phase.bytedance.city 加进 ai-monitor.py Projects 卡片区 + DNS health check

---

## §5 Session #4 验收标准

session #4 完成 = 以下 all true：

- [ ] DeepSeek key 已 rotate
- [ ] Git history 无 plaintext API key (`git log --all -p | grep -E 'sk-[a-zA-Z0-9_-]{20,}'` empty)
- [ ] Repo PUBLIC (`gh repo view --json visibility -q .visibility` = "PUBLIC")
- [ ] `pip install soc-pipeline==0.1.0` works
- [ ] `pip install guarded-llm==0.1.0` works
- [ ] Zenodo DOI minted + reflected in CITATION.cff + manifest.json
- [ ] C1 v0.3 投 arXiv → 拿到 ID
- [ ] (optional) C2 4 solo + C4 也投 arXiv
- [ ] GitHub release v0.3.0 created
- [ ] HANDOFF.md 更新到 session #4 close 状态

预估 wall time：**2-3 小时**（如果所有 token 都准备好且无 web step 卡住）。

---

## §6 Session #4 起手第一段 prompt 模板

如果 user 想换 prompt 直接告诉 next-session Claude：

```
读 docs/sessions/SESSION-4-STARTER.md。按 §2 顺序执行 Step 1-9。
凭证已就绪：
- PYPI_TOKEN = <在 .env 或 env var>
- ZENODO_ACCESS_TOKEN = <...>
- arXiv 账号准备好了

全权 auto mode，不可逆 step 前给我个一句话 confirm 即可继续。
不可逆 step 撞到任何 unexpected 状态，立即停下报告。
```

---

## 附录：本 SESSION-4-STARTER.md 维护规则

- Step 7-9 完成后，把对应行从 §5 验收标准 check 掉
- 任何 step 失败导致 partial 状态，在 §3 加一条 incident note
- 如果 session #4 衍生新 sprint，append 到 §4 "已知次要事项"
- arXiv ID / Zenodo DOI / PyPI URLs 拿到后即时回填到本文 + HANDOFF.md
