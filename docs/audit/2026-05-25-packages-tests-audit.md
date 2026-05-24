# Packages + Tests Audit — 2026-05-25

> Read-only audit. 不修改 packages/ 任何代码或配置, 不 commit/push/git add。
> 仅跑 `pytest` (在 `.venv`) + import smoke test + 本地 build wheel 到 `/tmp/`。
> 报告作者: audit agent (Opus 4.7 1M)

## TL;DR

- **pytest 总计**: 4 包 × 全绿 = **402 / 402 测试通过** (soc-pipeline 79, cross-judge 162, guarded-llm 111, reject-aware-critic 50)
- **import 4 包全部 OK** (public API 暴露符合各自 README 文档)
- **build 状态**: 老 3 包 `dist/` 已有 0.1.1 wheel + sdist 就绪 (本地 build); reject-aware-critic 本次 audit 临时 build 到 `/tmp/audit-build-rac/` 验证可 build, 但**包内还没有 `dist/` 产物**
- **PyPI 状态**: 老 3 包 0.1.0 已 live (PyPI 公网 200); 0.1.1 等 tag 触发上传。reject-aware-critic 在 PyPI 上 404, 未发布
- **跨包独立性 ✓**: 4 个 `src/` 没有任何 `from soc_pipeline / from cross_judge / from guarded_llm / from reject_aware_critic / from v4 / from structural_isomorphism` 跨引用; 完全 standalone
- **v4/critics 不存在** (`v4/` 目录里没有 `critics/` 子目录); 旧 ensemble 逻辑只剩 `v4/scripts/b3_ensemble.py` + `b4_ensemble.py` 两个 standalone urllib script, 不 import 任何 packages, **不存在 fork vs supersede 冲突**

### P0 / P1 总览

| 等级 | 项 | 位置 |
|---|---|---|
| P0 | release-packages.yml 不覆盖 reject-aware-critic, tag 触发会失败 | `.github/workflows/release-packages.yml` |
| P0 | ci-packages.yml matrix 不包含 reject-aware-critic, PR 不跑测试 | `.github/workflows/ci-packages.yml` |
| P0 | PYPI_API_TOKEN secret 状态未知; 老 3 包 0.1.1 等触发上传仍 pending user 确认 token 已配 | GitHub Settings → Secrets |
| P1 | reject-aware-critic 包内无 `dist/` 产物; CI 触发前需先 push tag `reject-aware-critic-v0.1.0` (但前提是 P0 修复) | `packages/reject-aware-critic/dist/` |
| P1 | `Verdict / VerdictLabel` 在 cross-judge 与 reject-aware-critic 之间字段重复 (KEEP/REJECT/SPLIT/MERGE/UNCLEAR/ERROR/PARSE_FAIL 完全相同) — 不是真冲突, 但应在 README 显式说明二者关系 | both READMEs |
| P1 | soc-pipeline pytest 有 ~246 万条 warnings (powerlaw deprecation), 不影响绿但应 filter | `packages/soc-pipeline/tests/` |

---

## 环境

- Mac mini, macOS Darwin 24.3.0
- 全局 `python3` = Python 3.14 (homebrew), 缺多数依赖
- 项目 venv: `/Users/dadamini/Projects/structural-isomorphism/.venv/bin/python` = **Python 3.14.3**
  - 已装: `httpx 2.13.4`, `tenacity`, `pydantic 2.4.2`, `numpy`, `scipy`, `pandas`, `jsonschema 4.26.0`, `requests 2.32.5`, `pytest 9.0.3`, `powerlaw`, `pyyaml`, `build 1.5.0`
  - **缺**: `pytest_mock`, `pytest_asyncio`, `respx`, `twine` (audit 不安装; 但 4 包当前 tests 不依赖这些 → 全绿)
- 所有 pytest 用 `PYTHONPATH=src python -m pytest tests -q --tb=short -p no:cacheprovider` 跑

---

## Per-package status

### 1. soc-pipeline (0.1.1, hatchling)

| 检查项 | 结果 |
|---|---|
| pyproject.toml | ✓ valid TOML, 所有字段 (name/version/description/readme/license/dependencies/urls/classifiers/build-system) 齐全 |
| src/tests/README/LICENSE/CHANGELOG | ✓ 全有 (LICENSE = MIT, README 252 行, CHANGELOG 存在) |
| version 字段 | `0.1.1` (与 dist/ 一致) |
| dependencies | `numpy>=1.24, scipy>=1.10, pandas>=2.0, powerlaw>=1.5` (4 条) |
| build-backend | `hatchling.build` |
| Import smoke | ✓ `from soc_pipeline import fit_clauset_powerlaw, vuong_lr_test, validate, Verdict, bootstrap_ci, synthetic_null, shape_normalized_collapse, fit_omori_p, fit_b_value, time_resolution_sweep, empirical_ccdf, verdict_from_alpha_band, SocAccessor` 全部 OK |
| `__version__` | `'0.1.1'` |
| **pytest** | **79 passed in 165.56s** (~2:45) |
| 关键文件 | 13 个测试文件 (`test_fit.py`, `test_bootstrap.py`, `test_lr_test.py`, `test_null_controls.py`, `test_omori.py`, `test_b_value.py`, `test_pandas_accessor.py`, `test_time_resolution.py`, `test_universal_collapse.py`, `test_utils.py`, `test_validate.py`, `test_validate_w11a_coverage.py`) |
| README 章节 | Why / Install / Quickstart (one-call validate) / Pre-registered band / Lower-level API / Public API table / Limitations / Earthquake quickstart / Pandas integration / Cross-domain validation suite / Tutorials / Citation / License / Status — 252 行 |
| dist/ | `soc_pipeline-0.1.1-py3-none-any.whl` + `.tar.gz` (本地 2026-05-25 00:04 建好) |
| PyPI live | **0.1.0 已 live** (`https://pypi.org/pypi/soc-pipeline/json` HTTP 200, releases=['0.1.0']); 0.1.1 等 tag 触发 |
| 警告 | pytest 出 ~246 万条 deprecation warnings 来自 powerlaw lib (`sigma` 属性, lognormal 拟合失败等)。**不影响绿**, 但建议在 pyproject `[tool.pytest.ini_options]` 加 `filterwarnings` 静音 |

### 2. cross-judge (0.1.1, setuptools)

| 检查项 | 结果 |
|---|---|
| pyproject.toml | ✓ valid TOML, 字段齐全 |
| src/tests/README/LICENSE/CHANGELOG/MANIFEST.in | ✓ 全有 |
| version | `0.1.1` |
| dependencies | `pydantic>=2, httpx>=0.27, pyyaml>=6` (3 条); optional [openai] / [dev] |
| build-backend | `setuptools.build_meta` |
| Import smoke | ✓ 主 API: `Critic, Ensemble, Verdict, VerdictKind, EnsembleVerdict, krippendorff_alpha`; ✓ 旧 API: `Reviewer, JudgePanel` |
| **pytest** | **162 passed in 0.42s** |
| 测试文件 | 9 个 (`test_aggregation`, `test_core_w11a_coverage`, `test_critic`, `test_ensemble`, `test_panel`, `test_prompts_reviewer_w11a_coverage`, `test_reviewer`, `test_vendors_w11a_coverage`, `test_voting`, `test_voting_w11a_coverage`) |
| README 章节 | 5-second pitch / Why / Install / Quickstart / Versioned prompts / VerdictKind vocabulary / Voting / Disagreement metrics / Reproducibility / Error handling / Legacy API / API stability / License / Citation — 281 行 |
| dist/ | `cross_judge-0.1.1-py3-none-any.whl` + `.tar.gz` (本地建好) |
| PyPI live | **0.1.0 已 live**; 0.1.1 等 tag |
| build/ | 有残留 build/ + src/cross_judge.egg-info/ (setuptools 副产品, 已在 .gitignore) |

### 3. guarded-llm (0.1.1, hatchling)

| 检查项 | 结果 |
|---|---|
| pyproject.toml | ✓ valid TOML, 字段齐全 (有最丰富的 keywords + classifiers) |
| src/tests/README/LICENSE/CHANGELOG/examples/docs | ✓ 全有 |
| version | `0.1.1` |
| dependencies | `pydantic>=2, httpx>=0.27, tenacity>=8, jsonschema>=3.2, requests>=2.28` (5 条); optional [anthropic/openai/deepseek/kimi/glm/all/dev] |
| build-backend | `hatchling.build` |
| Import smoke | ✓ `GuardedLLM, Budget, RetryPolicy, guardrailed_llm_call, LLMSchema` |
| **pytest** | **111 passed in 1.29s** |
| 测试文件 | 8 个 + `test_providers/` 子目录 (`test_budget`, `test_core_guarded_llm`, `test_guardrail`, `test_providers/`, `test_retry`, `test_schemas`, `test_validator`, `test_validator_w11a_coverage`) |
| README 章节 | Install / 5-line quickstart / Why / Quickstart per vendor (Anthropic/DeepSeek/Kimi/GLM) / Budget enforcement / Retry semantics / Multi-vendor failover / Extending — 255 行 |
| dist/ | `guarded_llm-0.1.1-py3-none-any.whl` + `.tar.gz` (本地建好) |
| PyPI live | **0.1.0 已 live**; 0.1.1 等 tag |

### 4. reject-aware-critic (0.1.0, setuptools) — **NEW, 未上 PyPI**

| 检查项 | 结果 |
|---|---|
| pyproject.toml | ✓ valid TOML, 所有字段齐全 (含 `Paper` URL 指向 `paper/c4-reject-aware-pipeline-2026-05-13.md`) |
| src/tests/README/LICENSE/CHANGELOG/examples | ✓ 全有 (LICENSE = MIT) |
| version | `0.1.0` |
| dependencies | `pydantic>=2.0, httpx>=0.25, tenacity>=8.0` (3 条); optional [dev]=pytest+pytest-asyncio |
| build-backend | `setuptools.build_meta` |
| Import smoke | ✓ `Critic, CriticEnsemble, CandidateClass, Verdict, EnsembleResult, CostBudgetError, DEFAULT_MODELS, TRAP_PATTERNS, candidate_signature_text, detect_traps` 全部 OK |
| Public 全表 | 30 个公开符号: `CandidateClass, CostBudgetError, Critic, CriticEnsemble, DEFAULT_MODELS, DEFAULT_SYSTEM_PROMPT, EnsembleResult, SYSTEM_PROMPTS, TRAP_PATTERNS, TrapFlag, VENDORS, VendorConfig, Verdict, VerdictLabel, build_user_prompt, candidate_signature_text, critic, detect_traps, detect_traps_strict, ensemble, filters, get_vendor, merge_trap_flags, prompts, register_mock_responder, schemas` |
| **pytest** | **50 passed in 0.08s** (符合 user 报告的 50/50) |
| 测试文件 | 4 个 (`test_critic`, `test_ensemble`, `test_filters`, `test_schemas`) |
| README 章节 | Install / 30-second demo (offline mock vendor) / Public API / 4 trap categories / When to use which ensemble / Cost guardrail / Structured logging / Related / License — 133 行 |
| dist/ | **没有 dist/ 目录** — 包内尚未 build artifact |
| 临时本地 build | ✓ `cd packages/reject-aware-critic && python -m build --outdir /tmp/audit-build-rac/ --wheel --sdist` 成功产出 `reject_aware_critic-0.1.0-py3-none-any.whl` (23.6KB) + `.tar.gz` (26.9KB) |
| PyPI live | **404** — `https://pypi.org/pypi/reject-aware-critic/json` returns 404, releases=[] |
| Standalone | ✓ `src/reject_aware_critic/` 没 import 任何外部 packages 或 `v4/` |
| README demo 可信度 | ✓ `register_mock_responder` 在 public API 里; README 30s demo 代码 syntactically 与 example `21_class_panel_demo.py` 一致 |

---

## Cross-package independence audit

跨包 import 扫描 (从每个包的 `src/` grep `^(from|import) (soc_pipeline|cross_judge|guarded_llm|reject_aware_critic|v4|structural_isomorphism)`):

```
soc-pipeline:          没有跨包 import
cross-judge:           没有跨包 import
guarded-llm:           没有跨包 import
reject-aware-critic:   没有跨包 import
```

**结论**: 4 包源码层面**完全独立 standalone**, 任何一个都可单独 `pip install`, 不依赖其他三包或本仓 `v4/` / `structural_isomorphism/`。

### cross-judge ↔ reject-aware-critic 关系

用户关心: "是不是同一个包写了两次?"

**不是。重叠是 label 词汇表, 不是 schema。**

| 对比维度 | cross-judge | reject-aware-critic |
|---|---|---|
| **定位** | 通用 multi-vendor LLM ensemble judge framework | universality-class 评审专用 critic ensemble |
| **输入 schema** | 自由 `query: str` + `context: dict` (str.format 模板) | `CandidateClass` Pydantic 强 schema (`class_id, shared_equations, members, domains, ...`) |
| **输出 schema** | `Verdict(kind, confidence, reasoning, critic_id, raw_response, error, elapsed_s)` | `Verdict(decision, confidence, rationale, trap_flags: list[TrapFlag], ...)` |
| **核心增量** | Krippendorff α + voting strategies (majority/unanimous/conservative) + 4 vendor adapter | 4 个 universality "trap" 类别检测 (`mechanism_vs_limit_theorem` / `mathematical_framework_masquerading` / `surface_similarity_from_heavy_tails` / `mechanism_dispersion_monolith`) + B3 (3 decodings) / B4 (cross-vendor) ensemble 预设 |
| **VerdictLabel literals** | `KEEP/REJECT/SPLIT/MERGE/UNCLEAR/ERROR/PARSE_FAIL` (一致) | `KEEP/REJECT/SPLIT/MERGE/UNCLEAR/ERROR/PARSE_FAIL` (一致) |
| **vendor 列表** | `deepseek / openai / openrouter` (3) | `deepseek / anthropic / kimi / glm / openrouter / mock` (含 anthropic + kimi + glm + 离线 mock) |
| **可独立用** | ✓ | ✓ |

**判断**: 是合理的 layered architecture, 不是重复。`cross-judge` 是通用层 (任何 KEEP/REJECT/SPLIT/MERGE 评审都可复用), `reject-aware-critic` 是 universality-class 业务层 (CandidateClass + trap_flags + B3/B4 预设)。

但**有重叠面**: 两包都定义了 `Verdict / VerdictLabel / Critic` 类名, 字段大半 (decision/kind, confidence, reasoning/rationale) 概念重合; 也都内置 `_extract_json` JSON-from-LLM 提取 (逻辑相似但代码独立)。

**潜在改进 (非本次 audit scope)**: 未来可让 reject-aware-critic 依赖 `cross-judge` 做底层 vendor 适配, 自己只保留 CandidateClass / trap_flags / B3/B4 这些 universality-specific 抽象。但当前 reject-aware-critic 选择 standalone 是有道理的 (减少依赖耦合, 不被 cross-judge 版本拖累)。

---

## v4/critics legacy

- `v4/critics/` 目录**不存在** (`ls v4/` 没有 `critics/` 子目录)
- 搜索 `class.*Critic / class.*Ensemble` 在 `v4/` 下: 命中只有 `v4/scripts/b3_ensemble.py / b4_ensemble.py / b4_deepseek_ensemble.py / run_preregistered_validation.py` 等 standalone shell-style scripts
- 这些 script 只用 `urllib.request` 直接打 HTTP, **不 import 任何 `cross_judge / reject_aware_critic / packages/*`**
- `v4/tests/sanity/test_b3_ensemble.py` 也是 `import b3_ensemble` (sibling 文件), 与 packages/ 解耦
- `v4/cli.py` 不 import critics 类
- `web/` 目录扫描: 没有 `from cross_judge / reject_aware_critic / v4.critics` 引用

**结论**: 不存在 "fork vs supersede" 关系。`v4/scripts/b?_ensemble.py` 是早期一次性 research script (硬编码 urllib), `packages/cross-judge` 与 `packages/reject-aware-critic` 是后来抽象出来的 reusable lib。两条线**互不依赖**, 不需要 deprecation 通知 — 但日后若 `v4/scripts/` 要复用 packages/, 需要单独重写, 不能直接迁移。

---

## Build / publish readiness

### dist/ 产物状态

| 包 | dist/ 存在 | wheel | sdist | 与 pyproject version 一致 |
|---|---|---|---|---|
| soc-pipeline | ✓ | `soc_pipeline-0.1.1-py3-none-any.whl` (32KB) | `soc_pipeline-0.1.1.tar.gz` (37KB) | ✓ 0.1.1 |
| cross-judge | ✓ | `cross_judge-0.1.1-py3-none-any.whl` (28KB) | `cross_judge-0.1.1.tar.gz` (40KB) | ✓ 0.1.1 |
| guarded-llm | ✓ | `guarded_llm-0.1.1-py3-none-any.whl` (33KB) | `guarded_llm-0.1.1.tar.gz` (40KB) | ✓ 0.1.1 |
| **reject-aware-critic** | **✗ (无 dist/)** | — | — | — (audit 在 `/tmp/audit-build-rac/` 临时 build 验证可建) |

`packages/cross-judge/build/` + `packages/cross-judge/src/cross_judge.egg-info/` + `packages/reject-aware-critic/build/` + `packages/reject-aware-critic/src/reject_aware_critic.egg-info/` 这些 setuptools 残留**在 `.gitignore` 内** (`*.egg-info/, dist/, build/`), 不会污染 commit。

### PyPI live status (`curl -s https://pypi.org/pypi/<name>/json`)

| 包 | HTTP | latest live | local pyproject |
|---|---|---|---|
| soc-pipeline | 200 | 0.1.0 | 0.1.1 (staged, 等 tag) |
| cross-judge | 200 | 0.1.0 | 0.1.1 (staged, 等 tag) |
| guarded-llm | 200 | 0.1.0 | 0.1.1 (staged, 等 tag) |
| reject-aware-critic | **404** | (none) | 0.1.0 (首次发布 pending) |

### `.github/workflows/release-packages.yml` 检查

- Tag pattern: `guarded-llm-v*` / `soc-pipeline-v*` / `cross-judge-v*` — **缺 `reject-aware-critic-v*`**
- `workflow_dispatch` inputs.package choices: 同上 3 个 — **缺 reject-aware-critic**
- 流程: tag 触发 → version 对账 (pyproject 与 tag 必须一致) → `python -m build` → `twine check --strict` → 有 `PYPI_API_TOKEN` 则 `twine upload`, 没则跳过并给 step summary 提示
- `id-token: write` permission 已加 (为未来 OIDC trusted publishing 留口)
- `environment: pypi` (GitHub Environment, 可用 protection rules)

**workflow 逻辑本身 OK**, 但**对 reject-aware-critic 不生效**: tag pattern + dispatch choices 都没列它。如果今天直接 `git tag reject-aware-critic-v0.1.0 && git push --tags`, workflow 不会 trigger (因为 push 的 tag pattern 不匹配 `on.push.tags`)。

### `.github/workflows/ci-packages.yml` matrix

```yaml
matrix:
  os: [ubuntu-latest, macos-latest]
  python-version: ["3.10", "3.11", "3.12", "3.13"]
  package:
    - guarded-llm
    - soc-pipeline
    - cross-judge
```

**缺 reject-aware-critic** — PR 触碰 `packages/reject-aware-critic/**` 不会跑测试 matrix。

### PYPI_API_TOKEN secret

- workflow 用 `secrets.PYPI_API_TOKEN`; 若未配置, 会跳过 upload 并在 Step Summary 给提示
- audit 无权检查 GitHub Settings → Secrets, 状态 **pending user 在 GitHub 控制台确认**
- 老 3 包 0.1.0 已 live 说明历史上某条路径 (本地 twine? 之前的 secret?) 完成过发布; 但 0.1.1 是否能通过 workflow 自动 publish, 依赖 secret 当前是否还在

---

## 验收结论

### 4 包当前 vs 用户期望

| 项 | 用户期望 (本任务说法) | audit 实测 | 一致? |
|---|---|---|---|
| reject-aware-critic pytest | 50/50 通过 | 50/50 通过 in 0.08s | ✓ |
| 4 包都能 install (PyPI) | 老 3 包 live, 新包未发 | 老 3 包 0.1.0 live, 0.1.1 dist 就绪等 tag; reject-aware-critic 404 待首发 | ✓ |
| 跨包 independence | reject-aware-critic 完全 standalone | ✓ src/ 无任何跨包 import | ✓ |
| v4/critics 关系 | "fork 还是 supersede" | v4/critics 不存在, v4/scripts/ 老 ensemble script 跟 packages/ 无依赖 → 不是 fork 也不是 supersede, 是并行两条独立线 | ✓ 澄清 |
| cross-judge vs reject-aware-critic overlap | "是不是同一个包写了两次?" | 不是。VerdictLabel 词汇表完全一样但 schema 不同; cross-judge 是通用 vendor judge framework, reject-aware-critic 是 universality-class 专用 trap-aware critic | ✓ 不重复 |

### 风险面

1. **CI/Release workflow 没把 reject-aware-critic 加进 matrix 与 tag pattern** (P0) — 任何 `reject-aware-critic-v0.1.0` push tag 不会 trigger release workflow。修复要点: `release-packages.yml` 的 `on.push.tags` 加 `"reject-aware-critic-v*"`, `workflow_dispatch.inputs.package.options` 加该包, tag 解析 case 加 `reject-aware-critic-v*) PKG=...`; `ci-packages.yml` matrix.package 加 `- reject-aware-critic`
2. **PYPI_API_TOKEN 状态需 user 确认** (P0) — 可在 GitHub Actions Settings → Secrets and variables → Actions 看 `PYPI_API_TOKEN` 是否存在; 也可看 `https://pypi.org/manage/account/token/` 是否有 active token
3. **reject-aware-critic 包内无 `dist/`** (P1) — 不阻塞 (workflow 内 build), 但若想 `twine upload` 直接发, 需 `cd packages/reject-aware-critic && python -m build` 先
4. **soc-pipeline pytest warning 数 246 万条** (P1) — 不影响绿但污染日志; 加 `filterwarnings = ["ignore::DeprecationWarning:powerlaw"]` 即可
5. **cross-judge / reject-aware-critic 两包都有 `Verdict / VerdictLabel / Critic` 同名 class** (P1 文档) — 两个 README 应互相 cross-reference, 说明 "想做 universality-class 评审用 reject-aware-critic; 想做通用 LLM judge ensemble 用 cross-judge"; 避免 user 装两个发现类名冲突
6. **build artifact 残留** (P2) — `packages/cross-judge/build/` + `packages/reject-aware-critic/build/` 这些目录虽 .gitignore 已盖, 但放在源码包根上视觉上挺乱; 可用 `python -m build --outdir /tmp/...` 替代

### 哪些可以立即发

- **soc-pipeline 0.1.1** — 79 test 全绿, dist 就绪, push tag `soc-pipeline-v0.1.1` 即可 (前提 PYPI_API_TOKEN OK)
- **cross-judge 0.1.1** — 162 test 全绿, dist 就绪, push tag `cross-judge-v0.1.1` 即可
- **guarded-llm 0.1.1** — 111 test 全绿, dist 就绪, push tag `guarded-llm-v0.1.1` 即可
- **reject-aware-critic 0.1.0** — 50 test 全绿, 包结构 OK, **但 release-packages.yml 没把它加进 tag pattern + ci-packages.yml 也没加进 matrix** → 必须先修 workflow, 再 tag

---

## 附录: 跑的命令

```bash
VENV=/Users/dadamini/Projects/structural-isomorphism/.venv/bin/python

# pytest (per package)
cd packages/soc-pipeline       && PYTHONPATH=src $VENV -m pytest tests -q --tb=short  # 79 passed in 165.56s
cd packages/cross-judge        && PYTHONPATH=src $VENV -m pytest tests -q --tb=short  # 162 passed in 0.42s
cd packages/guarded-llm        && PYTHONPATH=src $VENV -m pytest tests -q --tb=short  # 111 passed in 1.29s
cd packages/reject-aware-critic && PYTHONPATH=src $VENV -m pytest tests -q --tb=short  # 50 passed in 0.08s

# PyPI live check
for pkg in soc-pipeline cross-judge guarded-llm reject-aware-critic; do
  curl -s -o /tmp/pypi-$pkg.json -w "$pkg HTTP %{http_code}\n" "https://pypi.org/pypi/$pkg/json"
done
# Result: soc-pipeline/cross-judge/guarded-llm = 200 (latest 0.1.0); reject-aware-critic = 404

# Local build (reject-aware-critic, into /tmp to avoid polluting package dist/)
cd packages/reject-aware-critic && $VENV -m build --outdir /tmp/audit-build-rac/ --wheel --sdist
# → reject_aware_critic-0.1.0-py3-none-any.whl + .tar.gz built OK
```

报告完。
