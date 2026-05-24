# Repo Structure & Health Audit — 2026-05-25

> Audit agent: read-only audit run on `main` HEAD `53b8fae` (post Wave 4 / C1 v0.4 commit), local working tree clean except别 session in-flight `scripts/train_v2.py`（不动）。
> Scope: 仓库结构健康度 + 部署 + repo 元信息。**不修改任何文件**，仅产出本报告。

---

## TL;DR

- **总分 6.5 / 10**。代码与数据层（v4/validation、data/、packages/、PyPI、站点、CI）大体健康；**文档元数据层（README、CITATION、CHANGELOG、HANDOFF.md、open issues、release/arxiv）相对实际进展全面滞后**。
- **P0 = 4**，**P1 = 7**，**P2 = 6**（共 17 条 finding）。
- **最关键 3 条 finding**：
  1. **README + README-zh 数字滞后到 v0.3**（27 SOC / 4888 KB / v0.3 unified preprint），实际已 v0.4（45+ SOC / 5388 KB / 18 class verdicts / `reject-aware-critic` 第 4 个包）。新读者会 underestimate 项目 1 个 wave。
  2. **CI 红：`sanity tests` + `types-sync` 持续 failure**。sanity 红是 `embedding_bridge` 测试拿 pickle .npy 但代码用 `np.load` 不带 `allow_pickle=True`；types-sync 红是 backend 加了 `model` / `deployed_at` / `query_cache` 字段但没重生 TS types。两者都是机械性 fix，但 main 现在 push 必红。
  3. **18 个 open GitHub issues 中至少 4 个实质已完成**（#155 README zh / #146 anderson YAML / #145 fBm YAML / #142+#144 cascade dataset），缺 close commit。社区第一印象差。

---

## Section A. README + metadata

### 检查结果

**A1. Badge / 引用路径**：
- DOI badge `10.5281/zenodo.19615170` → DataCite API 返 200，DOI 真实有效（"SIBD-63" 注册到 Wan, Qinghui，2026）。Zenodo 直接 GET 返 403 是反爬，不是 DOI 失效。**OK**。
- Preprint badge → `paper/v0-unified-pipeline-2026-05-13.md` 存在。**OK**。
- Methodology / a11y / perf / coverage badge 引用的 4 个路径全部存在。**OK**。
- Tests badge 写 "48 backend + 11 e2e" — **严重滞后**。SESSION-22 末已 817 backend passed；本地 `grep -rE "^def test_"` 在 `v4/tests/` + `tests/` 共 400+ 测试函数。
- Coverage badge "85.6%" → 引用 `.github/workflows/coverage.yml` 存在。数字未现场验证。

**A2. Live 站点 HTTP（curl -sI）**：
- `https://beta.structural.bytedance.city` → HTTP/2 200 nginx ✅
- `https://phase.bytedance.city` → HTTP/2 200 nginx ✅
- `https://structural.bytedance.city` → HTTP/2 200 nginx ✅
- 3 个站点全活。

**A3. README "Status as of 2026-05-25" 数字 vs 实际**：

| README 说 | 实际（v0.4 / SESSION-23） | 差异 |
|---|---|---|
| 27 SOC validation systems | **45+**（+18 Wave 2A/B/C） | 滞后 1 个 wave |
| 4888 KB entries | **5388**（+500: Wave 3B 200 + Wave 3C 300） | 滞后 |
| 3 PyPI packages | 3 live + 1 ready in packages/（`reject-aware-critic` v0.1.0 待上 PyPI） | 漏说 |
| C1 v0.3, 9/9 P0 closed | **C1 v0.4 + §3.5 18 class verdicts**（docs/sessions/C1-unified-preprint-draft-v0.4.md） | 滞后 |

Status 表底部："Universality taxonomy v0.3, B3 consensus complete, B4 ensemble run partial" + "Unified preprint (C1) v0.3.1 ready" — 与同 commit 已 ship 的 v0.4 paper draft + 18 class closure 直接矛盾。

**A4. README-zh.md** 同样滞后：Tests badge 仍 "48 backend + 11 e2e"，没有 Coverage / A11y / Performance 三个 badge（EN 版有，zh 版漏），Status 仍写 27 / 4888 / v0.3。

**A5. CITATION.cff** version 已 `0.4.0`，但 abstract 段仍写 "thirteen independent empirical systems" + "21-candidate universality-class taxonomy" + "213 tests"。GitHub `latestRelease` 是 `v0.5.0`（2026-05-19），与 CITATION 0.4.0 又对不上 — 三层版本号自相矛盾。

**A6. LICENSE / CONTRIBUTING / CODE_OF_CONDUCT / GOVERNANCE** 全部齐。**OK**。

**A7. CHANGELOG.md**：`[Unreleased]` 段仍列 "PyPI publish (3 packages, awaiting `PYPI_TOKEN`) / repo PUBLIC flip / Zenodo DOI mint / arXiv submission" — 这些**已在 SESSION-22 全部完成**（repo PUBLIC + 3 PyPI live + Zenodo DOI 已 mint）。CHANGELOG 顶端版本号停在 `[0.4.0] — 2026-05-15`，但 GitHub 已 tag `v0.5.0` (2026-05-19) + `v0.4.1` — **缺 0.5.0 + 0.4.1 章节**。

---

## Section B. Project structure

### 顶级目录清单（28 个目录）

`backtest/ config/ data/ dataset/ demo/ docs/ logs/ mcp/ models/ notebooks/ packages/ paper/ phase/ plans/ release/ results/ scripts/ site/ site_mkdocs/ structural_isomorphism/ tests/ tools/ tutorials/ v3/ v4-feasibility/ v4/ validation/ web/`

### README §Repository layout 提到 vs 实际

- **README 提到**：`v4/ web/ paper/ dataset/v1/ tutorials/ docs/` — 仅 6 个。
- **README 未提到**（22 个）：`backtest/ config/ data/ demo/ logs/ mcp/ models/ notebooks/ packages/ phase/ plans/ release/ results/ scripts/ site/ site_mkdocs/ structural_isomorphism/ tests/ tools/ v3/ v4-feasibility/ validation/`
- **关键漏说**：`packages/`（4 PyPI 包入口！）、`phase/`（Phase Detector 独立目录）、`backtest/`（README §3 卡片引用了 `/backtest`）、`release/`（Zenodo 包路径）

`validation/` 与 `v4/validation/` 同时存在（双 validation 目录），README 没说差别。

### release/ 同步度

- `release/zenodo/dataset-v1.tar.gz`（45 MB）+ `.zenodo.json` + manifest + README — 完整。**OK**。
- `release/arxiv/c1-unified-preprint-v0.3/` 含 `main.tex` / `references.bib` / `abstract.txt` / `cover-letter.txt` / `main.pdf.TODO`。
- **v0.4 paper 已写**（`docs/sessions/C1-unified-preprint-draft-v0.4.md`，77 KB，459 lines），**release/arxiv/ 没有对应 v0.4 目录**。这是 expected gap（v0.4 还在 paper draft 阶段、未到 arXiv 投递），但需要在 README/CHANGELOG 显式标"v0.3 = arxiv release，v0.4 = next draft"，否则容易当 bug。

---

## Section C. v4/validation 完整性

### 数字现状

- `v4/validation/` 子目录数：**57**（远多于 README 说的 27、SESSION-23 说的 45+）。原因：旧实验目录（如 `pre-reg-p1-bch` / `pre-reg-p2-reddit` / `gardner-collins-toggle` + `-v2`）+ taxonomy 派生类 + 老 SOC 类 + 新 Wave 2/3 全混在一起。
- 有 `verdict.md` 文件：23
- 有 `verdict.txt` 文件：3
- 有 `results.json` 文件：35
- 有 `run_validation.py`（或 `run_*.py`）：57（每个目录都有 runner，**OK**）

### Verdict 文件命名不统一

放宽到 `README.md` / `VERDICT-YYYY-MM-DD.md` / `summary.md` / `paper.md` 也算 verdict 后：

- **完全无 verdict-style 文件的 9 个目录**：
  - `beta-amyloid`（只有 results.json）
  - `city-zipf`
  - `pre-reg-p1-bch`
  - `pre-reg-p2-reddit`
  - `soc-github-resolution`（有 verdict.json 但无 .md）
  - `soc-solar-wind`
  - `twitter-cascades`
  - `youtube-views`
  - `zipf-language`

- **命名 drift**：`nyc-fdny-fires/README.md`、`hysteresis-traffic/VERDICT-2026-05-13.md`、`null-controls/VERDICT-2026-04-16.md`、`cve-vulnerabilities/README.md`、`llm-scaling/summary.md` — verdict 在但路径各异，自动化扫描会漏。

### Wave 2A/B/C 18 class（重点核对）

全部 18 个目录均含 `verdict.md`：adverse-selection-unraveling / anderson-localization / delay-differential-debt / fractional-brownian-crossings / gardner-collins-toggle(-v2) / hysteresis-first-order / leaky-integrate-fire / markov-memory-fidelity / percolation-connectivity / preisach-hysteresis-cascade / reflexive-fixed-point / scale-free-percolation / schelling-credible-commitment / second-order-damped-oscillator + extreme-value-tail + reaction-diffusion-steady-state + tail-copula-contagion + dp-contact-process / kpz-interface / manna-sandpile / oslo-rice / rfim-barkhausen / tracy-widom-gue。**Wave 2 ship 完整。**

---

## Section D. data/ 目录

### 主 KB

- `data/kb-5000-merged.jsonl` = **4888 lines**（与 README + SESSION-22 数字一致）
- `data/kb-5000-merged.jsonl.bak-session22` = 4475 lines（SESSION-22 起手 baseline）

### Wave 2 additions（2026-05-24，16 个文件，共 **481 条**）

```
beta-amyloid 10, city-zipf 10, climate-tipping 25, covid-omori 18,
dp 8, kpz 8, linguistics 150, llm-scaling 15, neuroscience 80,
oslo 8, rfim 8, tracy-widom 8, twitter-cascades 10, urban-social 105,
youtube-views 10, zipf-empirical 10
```

### Wave 3 additions

- **Wave 3A（2026-05-25 v0.4 class additions，20 个文件，共 147 条）**：每个 class 6-8 条 + `long-tail-batch.jsonl` 单独 300 条。
- **Wave 3B reproducible-data-layer**：`kb-reproducible-data-layer-2026-05-25.jsonl` = **200 lines**。
- 全部 additions 累计：`cat data/kb-additions-*.jsonl | wc -l` = **928 条**。

### 期望 merge 后主 KB ≈ 5388

`4888 + 500 (Wave 3B 200 + Wave 3C 300) = 5388`。Wave 2 (481) 应已在 4888 里。**当前主 KB 没有合并 Wave 3 — expected**，因为 SESSION-23 还在 v0.4 paper synthesize 阶段，未到合并发布。

**Merge 命令样例**（仅供下个 session 参考，不在本 audit 执行）：

```bash
cat data/kb-5000-merged.jsonl \
    data/kb-reproducible-data-layer-2026-05-25.jsonl \
    data/kb-additions-2026-05-25-long-tail-batch.jsonl \
  | python3 -c "
import sys, json
seen = set(); out = []
for line in sys.stdin:
    rec = json.loads(line)
    k = rec.get('id') or rec.get('text','')[:80]
    if k in seen: continue
    seen.add(k); out.append(line.rstrip())
print('\n'.join(out))
" > data/kb-5388-merged.jsonl
wc -l data/kb-5388-merged.jsonl   # 期望 ~5388
```

---

## Section E. packages/ 4 个包健康

### E1. soc-pipeline（v0.1.1）

- pyproject ✅ / src/soc_pipeline/ ✅ / 12 个 test 文件 ✅ / README 252 行 ✅ / LICENSE ✅ / CHANGELOG.md ✅
- PyPI 实际 published version = **0.1.0**，本地 pyproject = **0.1.1**。**版本号 drift**：bump 已做（commit `06e601b`）但没 publish。

### E2. cross-judge（v0.1.1）

- 同 soc-pipeline 结构，10 个测试，src 含 prompts/ + examples/。PyPI = 0.1.0。

### E3. guarded-llm（v0.1.1）

- 同上，10 个测试，src 含 providers/。PyPI = 0.1.0。

### E4. reject-aware-critic（v0.1.0，新增）

- pyproject + src/reject_aware_critic + 4 个测试 + README 133 行 + LICENSE ✅
- git log：`ac44831 feat(packages/reject-aware-critic): initial v0.1.0` — 确认 SESSION-23 新增。
- **PyPI 未上**（JSON 404）。需 publish 才能 install。

### E5. PyPI 一致性问题

| 包 | 本地 pyproject | PyPI 实际 | 缺 |
|---|---|---|---|
| soc-pipeline | 0.1.1 | 0.1.0 | 缺 0.1.1 publish |
| cross-judge | 0.1.1 | 0.1.0 | 缺 0.1.1 publish |
| guarded-llm | 0.1.1 | 0.1.0 | 缺 0.1.1 publish |
| reject-aware-critic | 0.1.0 | 不存在 | 缺首次 publish |

---

## Section F. PyPI status (curl)

| 包 | `pypi.org/project/X/` | `pypi.org/pypi/X/json` | latest version |
|---|---|---|---|
| soc-pipeline | 200 | 200 | 0.1.0 |
| cross-judge | 200 | 200 | 0.1.0 |
| guarded-llm | 200 | 200 | 0.1.0 |
| reject-aware-critic | 200* | **404** | (none) |

\* PyPI project page 对未注册包返软 200（重定向到 search-not-found）；JSON endpoint 才是真值。

---

## Section G. 站点健康

| URL | HTTP | server |
|---|---|---|
| https://beta.structural.bytedance.city | 200 | nginx |
| https://phase.bytedance.city | 200 | nginx |
| https://structural.bytedance.city | 200 | nginx |
| https://structural.bytedance.city/api/docs | 200 | nginx |

3 站全活，API host 的 Swagger UI 也通。

---

## Section H. GitHub repo

- visibility: **PUBLIC** ✅
- isArchived: false ✅
- description: "Beyond Semantic Similarity: Contrastive Learning..." — 此 description 是**老定位**（fine-tuned embedding + contrastive learning），与现在的 SOC universality validation 主线**严重不符**。
- diskUsage: 193 MB
- forkCount: 2，stargazerCount: 1
- pushedAt: 2026-05-24T20:32（最新 push 即本 commit）
- **latestRelease: v0.5.0** (2026-05-19)。CHANGELOG 顶端只到 0.4.0 — 缺 0.5.0 section。
- releases 历史：v0.5.0 / v0.4.1 / v0.4.0
- open issues: **18**，open PRs: 0
- **至少 4 个 open issue 实质已完成但没 close**：
  - #155 [i18n] Mandarin Chinese translation of the README → `README-zh.md` 已存在（11832 字节，对照 README EN 主体）
  - #146 [data] anderson_localization_transition universality class YAML → `v4/taxonomy/classes/anderson_localization.yaml` 已存在 + Wave 2 verdict PASS-CONFIRMED
  - #145 [data] fractional_brownian_crossings universality class YAML → 同上，Wave 2 verdict REJECT-CONFIRMED
  - #142 / #144 [data] Twitter cascade / GitHub resolution dataset → `v4/validation/twitter-cascades/` + `soc-github-resolution/` 已有 fetch + results

---

## Section I. CI / Actions

### Workflow 总览（18 个 workflow yaml）

`CI / Coverage / Deploy docs / perf budget / sanity tests / types-sync / ci-packages / coverage / deploy-beta-backend / deploy-phase-detector / docs / load-smoke / newsletter / nightly / perf / publish-pypi / release-packages / runtime-smoke / sanity / site-smoke / storybook / types-sync`

### 最近 conclusion

| Workflow | Latest |
|---|---|
| CI | running（已 4 分钟，本 commit 触发） |
| Coverage | running |
| Deploy docs | **success** |
| perf budget | running |
| **sanity tests** | **failure** |
| **types-sync** | **failure** |

### Sanity tests failure 根因

`v4/tests/sanity/test_embedding_bridge.py` 12 个测试 setup 全部 error：

```
v4/lib/embedding_bridge.py:162: in __init__
    self._emb: np.ndarray = np.load(self._npy_path)
E   ValueError: This file contains pickled (object) data.
    If you trust the file you can load it unsafely using the `allow_pickle=` keyword argument
```

→ CI 环境上 numpy 默认 `allow_pickle=False`，`.npy` cache 是 pickle 格式。要么把 `.npy` 重生为非 pickle（推荐），要么 `embedding_bridge.py` 显式 `np.load(path, allow_pickle=True)`。
另外 sanity 还有 50 passed + 33991 warnings（powerlaw lib `sigma` → `standard_err` deprecation 噪音）。

### types-sync failure 根因

Backend 加了 `query_cache` field（HistoryRow）+ `model` + `deployed_at` field（VersionResponse），但 `web/frontend/types/api.d.ts`（committed）没重生。diff 显示 5 行 ADD：

```
+  query_cache?: { [k: string]: number; } | null;
+  model: string;
+  deployed_at: string;
```

→ 跑 `pnpm types:gen` / `npm run types:gen`（或 workflow 指明的脚本）后 commit。

---

## Section J. Tech debt / outstanding

### J1. NEXT_SESSION.md 严重过时

文件首句 "User authorized everything in session #3 close-out" — 现在 session 22 / 23。指引"读 SESSION-4-STARTER.md" — 文件还在，但已是 9 个 session 前的状态。**应该 deprecate**（删除或改写为"看 docs/sessions/SESSION-23-HANDOFF.md"）。

### J2. docs/sessions/HANDOFF.md 同样过时

号称"永久 entry point"，但内容仍是 session #7 状态（git tag v0.4.0、500 ticker、Perplexity-like ship）。下个 session 起手按本文走会读到 9 个 session 前的快照。**应在每个 session 末更新或换成 SESSION-NN-HANDOFF 软链接**。

### J3. SESSION-22 → SESSION-23 衔接

SESSION-22-HANDOFF.md（17 KB，2026-05-23~25）+ SESSION-23-HANDOFF.md（14 KB，2026-05-25）头部都明确"承接前一个"，数字累计一致（27 → 45+ / 4888 → 5388 / 10 of 26 → 18 of 18 closure），**衔接 OK**。

### J4. .scrub-pre-backup/

`.scrub-pre-backup/repo-20260524-194839.bundle`（**108 MB**）— SESSION-22 history scrub 前的 bundle 备份。已 push origin/main + 有 `pre-scrub-backup-20260524-194839` git tag，本地 bundle 可以归档到 `~/Archive/` 或删除（节省 100 MB）。

`.scrub-dry-run.log`（400 字节）属一次性 dry-run 产物，可清理。

### J5. ARCHIVED / DEPRECATED

无 ARCHIVED / DEPRECATED 标记文件。**OK**。

### J6. CHANGELOG [Unreleased] 已完成项未迁移

- PyPI publish（3 包 0.1.0 已 live）
- Repo PUBLIC flip（已 PUBLIC）
- Zenodo DOI mint（已 mint 10.5281/zenodo.19615170）

这 3 条仍挂在 `[Unreleased]` 顶端 — 与现实直接矛盾。应迁到 0.5.0 section。

### J7. GitHub repo description 老定位

"Beyond Semantic Similarity: Contrastive Learning for Cross-Domain Structural Isomorphism Detection. First benchmark dataset (SIBD) + fine-tuned embedding model" — 仍是项目早期（fine-tune embedding 路线）的定位。现在主线已是 SOC universality validation + reject-aware critic + null-result publishing。新读者第一印象就错。

---

## P0 fixes（≤ 30 分钟）

1. **修 CI 红的 2 个 workflow**（机械性）：
   - `embedding_bridge.py` 加 `allow_pickle=True`，或重生 cache `.npy` 为非 pickle 数组（推荐后者，安全）。
   - 跑 types-sync 工具重生 `web/frontend/types/api.d.ts` + commit。
2. **关 4 个已完成的 open issue**：#155 / #146 / #145 / #142+#144（gh issue close NUM --comment "Implemented in commit X"）。
3. **README + README-zh "Status as of 2026-05-25" 数字更新**：27→45+，4888→5388，3 PyPI→3 live + 1 ready，v0.3→v0.4，9/9 P0→18/18 v0.4 closure。同步更新 `## Status` 表底 3 行。
4. **README tests badge** "48 backend + 11 e2e" → 至少 800+ backend（SESSION-22 末 817）。Coverage 数字若 CI 跑出可顺便更。

## P1 fixes（本 session 后期 / 下个 session 起手）

1. **CHANGELOG.md 补 0.4.1 + 0.5.0 section**，把 [Unreleased] 顶端 3 条已完成项（PyPI / PUBLIC / Zenodo）迁过去。
2. **CITATION.cff abstract 重写**：13→45+，21→27-28，213→817+ tests。version 同步到 0.5.0（与 GitHub release 对齐）。
3. **GitHub repo description 改写**：从 "Beyond Semantic Similarity / fine-tuned embedding" 改为 "Cross-domain self-organized criticality validation, frozen Clauset pipeline, 45+ systems, reject-aware critic ensemble, null-result transparency"。
4. **docs/sessions/HANDOFF.md 重写**：要么删掉作"永久 entry"角色（改成 "look at latest SESSION-NN-HANDOFF"），要么每个 session 末复制最新 SESSION-NN-HANDOFF 内容到这里。**单一权威源**：目前 HANDOFF.md + SESSION-NN-HANDOFF.md 双权威导致 HANDOFF 失效。
5. **NEXT_SESSION.md 删除或重写**。文件指向 9 个 session 前的状态，对新 session 是误导。
6. **README §Repository layout 补全**：至少加 `packages/`、`phase/`、`backtest/`、`release/`、`data/`、`scripts/`。
7. **publish soc-pipeline / cross-judge / guarded-llm v0.1.1 到 PyPI**（已 bump 但未发）；评估 reject-aware-critic 是否 ready 首发。

## P2 backlog（下个 session 起手）

1. **v4/validation/ 命名收敛**：9 个 verdict 文件命名 drift 统一到 `verdict.md`；`validation/` 与 `v4/validation/` 双目录消歧。
2. **release/arxiv/c1-unified-preprint-v0.4/ 准备**：把 v0.4 paper draft 转成 arxiv-ready latex（参考 v0.3 目录结构）。
3. **Wave 3 KB merge**：把 `kb-additions-2026-05-25-*.jsonl` + `kb-reproducible-data-layer-2026-05-25.jsonl` 合并到 `kb-5388-merged.jsonl`，更新 README 数字与 Zenodo bundle。
4. **`.scrub-pre-backup/repo-*.bundle` 归档**到 `~/Archive/`，省 100 MB。`.scrub-dry-run.log` 删。
5. **CHANGELOG [Unreleased]** 加 "Wave 2-4 / v0.4 paper / reject-aware-critic" 等本 batch 工作（待 0.5.x 或 0.6.0 release 时迁移）。
6. **powerlaw lib `sigma` deprecation 噪音**：sanity 跑出 33991 warnings；要么 pin 版本要么改源用 `standard_err`。

---

## 附录 A：核查命令快查

| 检查项 | 命令 |
|---|---|
| 站点健康 | `curl -sI -L https://beta.structural.bytedance.city/` |
| PyPI 版本 | `curl -s https://pypi.org/pypi/<pkg>/json \| jq .info.version` |
| DOI 真实性 | `curl -s https://api.datacite.org/dois/10.5281/zenodo.19615170` |
| CI 最近失败原因 | `gh run view <id> --log-failed` |
| open issue 实质完成识别 | `gh issue list --search "<keyword>"` + 对照 `v4/validation/` / `v4/taxonomy/classes/` |

## 附录 B：本 audit 未做但建议自动化

1. **每周 `gh issue list -s open` × `v4/validation/` × `v4/taxonomy/classes/` 三方对账**，自动关 implemented 的 issue。
2. **每次 release 自动核对**：CITATION.cff version == git latest tag == CHANGELOG 顶端 version == README status section。
3. **CI 跑前先 `pnpm types:gen` 检查 dirty** — 避免 types-sync 红堆积。
4. **`pip install -e packages/*` smoke test** 进 CI（当前 ci-packages.yml 可能漏）。

---

*Audit 完成时间：2026-05-25。Read-only，未修改任何其他文件，未 commit / push / git add。working tree 别 session in-flight `scripts/train_v2.py` 未触碰。*
