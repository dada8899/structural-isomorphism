# Retrieval Evaluation v1

`retrieval-v1.jsonl` is the canonical product-quality benchmark for Structural
Search. It contains 50 paired intents in Chinese and English: 40 in-scope
structural-transfer questions and 10 out-of-scope refusal cases, for 100 rows.

The source of truth for case wording and labels is
`scripts/build_retrieval_eval.py`. Regenerate and validate with:

```bash
python3 scripts/build_retrieval_eval.py
python3 scripts/evaluate_retrieval_v1.py --validate-only
```

Run a live baseline without sending credentials:

```bash
python3 scripts/evaluate_retrieval_v1.py \
  --base-url https://beta.structural.bytedance.city \
  --output evaluation/results/retrieval-v1-production.json
```

Primary metrics are Hit@5 and MRR@5 against accepted structural type IDs,
cross-domain success, OOS precision/recall, bilingual Top-5 type Jaccard, and
latency p50/p95. The benchmark is versioned; label changes require an explicit
version bump and review rather than overwriting historical results.
