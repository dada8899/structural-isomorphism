# Taxonomy — bundle-level README

This directory bundles the **B1 ⊗ B3 universality-class verdict matrix**
produced by the V4 universality-class engine (Layer 3 curator → Layer 3.5
B1 single-Opus critic → Layer 3.6 B3 three-DeepSeek ensemble critic) of
the structural-isomorphism project, evaluated at git commit `607906c`.

## Files

| File                          | Lines | Description |
|-------------------------------|-------|-------------|
| `B3_taxonomy_v2.jsonl`        | 21    | Final per-class plurality verdict (one row per class, includes B1 verdict, B3 consensus, avg_confidence, reviewer rationales) |
| `B3_ensemble_review.jsonl`    | 63    | Per-reviewer rationale (21 classes × 3 reviewers); preserves the raw critic outputs for traceability |
| `B3_ensemble_summary.md`      | 65    | Human-readable summary table + methodology notes (symlinked from `v4/results/`) |
| `classes/` (35 YAML files)    | —     | Layer 3 curator output — display name + shared normal-form equation + invariants + positive/negative examples per class. 35 files because some classes have sub-variants (e.g., `adverse_selection_unraveling_class.yaml` + 3 variant files for Akerlof lemons, echo chamber, spiral of silence) |
| `universality_classes.yaml`   | —     | Top-level class index |
| `SCHEMA.md`                   | —     | YAML schema specification for the class files |

## Headline counts

| Metric                              | Count |
|-------------------------------------|-------|
| Classes critiqued                   | 21    |
| Reviewer verdicts cast              | 63    |
| Final KEEP (with B1+B3 consensus)   | 5     |
| Final REJECT                        | 7     |
| Final SPLIT                         | 5     |
| Final MERGE                         | 4     |
| Final UNCLEAR                       | 0     |

(See `B3_ensemble_summary.md` for the per-class breakdown.)

## Methodology in two sentences

The B3 ensemble is a *three-reviewer plurality vote* across
`deepseek-v4-pro@temp=0.0` (rigorous main reviewer),
`deepseek-v4-flash@temp=0.0` (rigorous lightweight reviewer), and
`deepseek-v4-pro@temp=0.6` with an adversarial-dissenter system prompt
(creative reviewer). Consensus rule: if ≥ 2/3 reviewers agree on a category
(KEEP/REJECT/SPLIT/MERGE/UNCLEAR), that category is the B3 consensus;
otherwise UNCLEAR (no class hit UNCLEAR in this run).

## Known limitations

1. **Same-family**: all 3 reviewers are DeepSeek v4 family. OpenRouter
   access to Anthropic Claude and Google Gemini was region-blocked from CN
   IPs at evaluation time. A future v1.1 should add an Anthropic + Gemini
   reviewer for true vendor diversity.
2. **B1 vs. B3 disagreement on 9/21 classes**: this is informative —
   single Opus tends to KEEP classes that the DeepSeek ensemble rejects
   (e.g., `scale_free_percolation_class`, `hysteresis_preisach`,
   `delay_differential_debt`). The ensemble's higher rejection rate is
   the methodological value-add.
3. **Class YAML count = 35 vs. classes critiqued = 21**: 14 of the 35
   YAML files are sub-variants (e.g., `motter_lai_network_cascade.yaml`
   plus `motter_lai_network_cascade__conserved_load.yaml` plus
   `motter_lai_network_cascade__threshold_contagion.yaml`). The B3
   ensemble critiques the 21 top-level classes; the 14 sub-variants
   document the within-class diversity.

## Reproduce

```bash
export DEEPSEEK_API_KEY='sk-...'
python3 dataset/v1/pipeline/b3_ensemble.py \
    --classes dataset/v1/taxonomy/classes/ \
    --output  dataset/v1/taxonomy/B3_ensemble_review_rerun.jsonl
# ~10 min wall-clock, ~$1 LLM cost
diff <(jq -c '.consensus_verdict' dataset/v1/taxonomy/B3_taxonomy_v2.jsonl | sort) \
     <(jq -c '.consensus_verdict' dataset/v1/taxonomy/B3_ensemble_review_rerun.jsonl | sort)
# At most 1-2 classes may differ due to creative-reviewer stochasticity.
```

See `pipeline/README.md` for full reproducibility instructions.
