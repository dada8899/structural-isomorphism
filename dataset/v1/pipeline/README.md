# Pipeline reproducibility README

This directory contains the frozen versions of the three core pipeline
scripts used to produce every headline α, τ, b-value, Omori-p, and
universality-class verdict in this bundle:

| Script             | LoC | Purpose |
|--------------------|-----|---------|
| `soc_pipeline.py`  | 339 | Clauset-Shalizi-Newman 2009 MLE power-law fit, bootstrap CI, LR tests vs. lognormal / exponential |
| `llm_guardrail.py` | 441 | Structured-output schema + abstention guardrails for the LLM curator and critic stages |
| `b3_ensemble.py`   | 584 | The 3-DeepSeek ensemble critic (deepseek-v4-pro@0.0, deepseek-v4-flash@0.0, deepseek-v4-pro@0.6 adversarial-dissenter) |

These files are *symlinks* into the parent repo's `v4/lib/` and
`v4/scripts/` directories. Editing them updates the upstream live versions
too. For a frozen-by-value copy, dereference at tarball time (`tar -czh`).

---

## 1. Setup

```bash
git clone https://github.com/dada8899/structural-isomorphism.git
cd structural-isomorphism

# Python 3.10+ recommended
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# (or `pip install numpy scipy powerlaw pandas pyyaml httpx tenacity` if
#  the repo doesn't ship a requirements.txt at the commit you've checked out)

# Only required for re-running the B3 ensemble critic (step 4 below):
export DEEPSEEK_API_KEY='sk-...'
```

The DeepSeek key is **not** included in this bundle (see § 8 of the parent
project's CLAUDE.md for the upstream key). If you don't need to re-run the
LLM ensemble critic, you can skip the `DEEPSEEK_API_KEY` step — the
verdicts are already in `dataset/v1/taxonomy/B3_*.jsonl`.

---

## 2. Reproduce a single system's headline result

### Example: earthquake Gutenberg-Richter b-value

```bash
cd structural-isomorphism
python3 dataset/v1/systems/01_earthquake/data/gutenberg_richter.py
# Expected output:
#   b = 1.084  (CI [1.073, 1.094])
#   n above Mc = 4.45: 37281
#   matches dataset/v1/systems/01_earthquake/paper.md within 0.001
```

### Example: stockmarket inverse-cubic α

```bash
python3 dataset/v1/systems/02_stockmarket/data/fetch_and_analyze.py
# Expected output:
#   α ≈ 3.0 (CI ~ [2.95, 3.05])
#   matches paper.md headline
```

### Example: all 16 systems

```bash
# Recipe pseudocode (see paper.md inside each slot for the exact runner)
for slot in dataset/v1/systems/*/; do
  if [ -f "$slot/data/analyze.py" ]; then
    python3 "$slot/data/analyze.py"
  fi
done
```

Total wall-clock: ~30 min on a laptop (slowest is universal_collapse
and 04_neural with their bin-factor sweeps).

---

## 3. Verify the 4 synthetic null controls (must be rejected)

```bash
python3 dataset/v1/null_controls/_generator.py
# Re-runs the 4 null generators with rng_seed=42, applies the same
# fitting pipeline, prints verdict.
#
# Expected: all 4 cases return pipeline_verdict = "rejected".
# All 4 also have vs_exponential_p ≪ 0.05 (the LR test correctly
# prefers exponential / folded-normal over power-law).
```

---

## 4. Re-run the B3 ensemble critic (LLM cost ~ $1)

```bash
export DEEPSEEK_API_KEY='sk-...'
cd structural-isomorphism
python3 dataset/v1/pipeline/b3_ensemble.py \
    --classes dataset/v1/taxonomy/classes/ \
    --output dataset/v1/taxonomy/B3_ensemble_review_rerun.jsonl
# Wall-clock: ~10 min (21 classes × 3 reviewers = 63 calls × ~10s each)
# Cost: ~$0.50-$1.00 depending on context length
#
# Then diff vs. the frozen verdicts:
diff <(jq -c '.consensus_verdict' dataset/v1/taxonomy/B3_taxonomy_v2.jsonl | sort) \
     <(jq -c '.consensus_verdict' dataset/v1/taxonomy/B3_ensemble_review_rerun.jsonl | sort)
# Should be identical or differ on at most 1-2 classes due to temperature=0.6
# adversarial dissenter being stochastic by design.
```

If you don't have a DeepSeek key, you can also point `b3_ensemble.py` at
any OpenAI-compatible endpoint (Together, Fireworks, OpenRouter for
non-CN IPs) — see the `DEEPSEEK_BASE` constant at the top of the script.

---

## 5. Run the 17-test sanity regression suite

```bash
cd structural-isomorphism
pytest dataset/v1/tests/sanity/ -v
# Expected: all 17 test files pass at git commit 607906c
#
# What the tests check:
# - Each system's headline α / τ / b-value lies within its frozen target band
# - Each system's CI is sane (lower < estimate < upper, σ > 0)
# - Null controls all produce pipeline_verdict = "rejected"
# - Universal-collapse panel residuals are within 2σ of zero
# - LLM guardrail rejects malformed structured outputs
# - B3 ensemble plurality voting agrees with cached verdicts
```

If a test fails after a fresh fetch, the most common cause is an
upstream provider rotating their API (USGS catalog refresh, etc.).
The bundle ships frozen jsonl/csv/parquet snapshots inside each
`data/` directory specifically to insulate from this.

---

## 6. Expected outputs vs. paper headlines

| System                  | Headline metric             | Expected value (CI)         | Source paper |
|-------------------------|------------------------------|------------------------------|--------------|
| 01 earthquake           | Gutenberg-Richter b          | 1.084 (1.073, 1.094)         | Phase 6      |
| 01 earthquake           | Energy α                     | 1.794 (σ=0.024)              | Phase 6      |
| 02 stockmarket          | Returns α                    | ≈ 3.0 (inverse cubic)        | Phase 7      |
| 03 defi (Aave)          | Liquidation α                | 1.57-1.68                    | Phase 9      |
| 04 neural (bf=4)        | τ (avalanche size)           | ~1.5                         | Phase 11     |
| 04 neural (bf=4)        | α (duration)                 | ~2.0                         | Phase 11     |
| 05 wildfire             | Burned-area α                | 1.66 (1.381, 1.808)          | Phase 10     |
| 06 solar                | Flare-fluence α              | 2.194 (2.159, 2.248)         | Phase 11     |
| 07 bank_failures        | Cluster-size α               | 1.899 (1.763, 2.047)         | Phase 8      |
| 08 github_stars         | Cumulative-stars α           | 2.867 (2.781, 3.000)         | Phase 6      |
| 11 hawkes_omori         | Omori p                      | ~1.0 (synthetic baseline)    | Phase 8      |
| universal_collapse      | 7-system row-centered fit    | residual ≤ 2σ                | Phase 12     |

A ≤ 5% deviation from these values is considered a successful reproduction.
Larger deviations usually mean (a) the upstream data provider has rotated
its catalog, or (b) numpy/scipy version drift in the bootstrap CI step.
Check the frozen `data/*.jsonl` snapshot inside the bundle for the canonical
input.

---

## 7. Troubleshooting

**`ImportError: powerlaw`** — the Clauset MLE uses the `powerlaw` package.
`pip install powerlaw` (it's not in scipy).

**`DEEPSEEK_API_KEY env var is not set`** — only required for §4. Skip
re-running the ensemble critic; the frozen verdicts are in `taxonomy/`.

**`Result differs from paper headline by > 5%`** — first check the
`data/*.jsonl` snapshot matches `provenance.json` / `fetch_log.json` SHA.
If yes, file an issue at the parent repo with the system slot + your numpy/
scipy versions.

**`OpenRouter Anthropic / Gemini returns 403`** — this is region-blocking
from CN IPs. Use DeepSeek directly (see `~/CLAUDE.md` reference memory
entry "OpenRouter Anthropic/Gemini在 CN被 region-block").

---

## 8. License

These pipeline scripts are MIT-licensed. See `dataset/v1/LICENSE`.
