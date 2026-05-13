# F1 — V1/V2 Embedding Bridge

**Status**: shipped (session #3, W2-E) — interface + TF-IDF fallback. Real-model wiring deferred to F1.1 (VPS deployment).
**Owner**: W2-E subagent
**Related**: `v4/lib/embedding_bridge.py`, `v4/tests/sanity/test_embedding_bridge.py`

## 1. Goal

Reuse the V1/V2 trained sentence-transformer embeddings as a **second signal source** for V4 Layer 3 (candidate-class expansion / membership refinement). Today, Layer 3 generates all candidate phenomena via the LLM. F1 adds: *for each `KEEP` class, surface nearest neighbours from the 4475-item KB cache so the LLM critic (or a human) can decide whether they belong.*

This is a **recall booster**, not a replacement for the LLM. The LLM is still the arbiter of class membership; F1 just feeds the LLM better candidates.

## 2. What we're reusing

| Asset | Path | Size | What it is |
|---|---|---|---|
| KB jsonl | `data/kb-5000-merged.jsonl` | 1.7 MB | 4475 cross-domain phenomena (id, name, domain, description, type_id) |
| V1 cached embeddings | `web/data/kb_embeddings.npy` | 13.7 MB | (4475, 768) float32, L2-normalised |
| V1 id index | `web/data/kb_embeddings_ids.json` | 58 KB | parallel id array |
| V2 cached embeddings | `web/data/kb_v2_embeddings.npy` | 13.6 MB | (4443, 768) float32, raw (we normalise on load) |
| V2 id index | `web/data/kb_v2_embeddings_ids.json` | 58 KB | parallel id array |
| V2 pairs catalog | `web/data/v2_pairs_index.json` | 710 KB | curated cross-domain pair annotations (3017 pairs) |
| V1 model | `models/structural-v1/` | 782 MB | sentence-transformer; gitignored, **VPS-only** |

**Key insight**: even without the 782 MB model on disk, the `.npy` caches alone let us do nearest-neighbour queries — *provided we can encode the query text*. That's the bridge's whole point: split "encode the query" from "compare to cached neighbours" so we can swap encoders.

## 3. Architecture

```
                        ┌────────────────────┐
   query text  ───────► │  encode strategy   │ ───► query_vec (768d)
                        └────────────────────┘
                                                          │
                                                          ▼
                        ┌────────────────────┐    cosine sim
   .npy + ids cache ──► │   neighbour search │ ◄──────────┘
                        └────────────────────┘
                                                          │
                                                          ▼
                                                   top-k Neighbor[]
```

Encoder strategies in priority order:

1. **`real_model`** (preferred): load `models/structural-v1/` via `SentenceTransformer.encode()`. Query lands in *the same* V1/V2 latent space as the cache → cosine sim is meaningful. Used on VPS / wherever the 782 MB model is provisioned.
2. **`tfidf`** (fallback): when the model file is absent (laptops, CI), fit `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,3))` over the KB descriptions. Query → TF-IDF vector → top-20 TF-IDF neighbours → take their V1/V2 centroid as a *pseudo-query* in V-space → re-rank the full KB by cosine to that pseudo-query. This is a 2-hop approximation; it inherits TF-IDF's char-overlap weakness but keeps the rest of the pipeline in V-space.

## 4. API

```python
bridge = EmbeddingBridge(
    version="v2",                 # "v1" or "v2"
    fallback_mode="tfidf",        # used when model_path is missing
    model_path=None,              # auto-detects models/structural-v1
)

# Suggest neighbours for a single phenomenon (dict or str)
bridge.suggest_neighbors(
    phenomenon,                   # dict with "description" / "name" / "id", or str
    k=5,
    exclude_ids=None,             # iterable[str], usually self id + known positives
) -> list[Neighbor]

# Expand a candidate class: centroid of positive_examples, top-k from KB
bridge.expand_candidate_class(
    class_yaml,                   # parsed v4/taxonomy/classes/*.yaml
    k=10,
) -> list[Neighbor]

# Inspection
bridge.mode            # "real_model" | "tfidf"
bridge.num_phenomena   # 4475 (v1) or 4443 (v2)
```

`Neighbor` is a dataclass with `id`, `name`, `domain`, `description`, `similarity`, and `to_dict()`.

## 5. Where this plugs into V4 Layer 3

Today (commit 7dce90e):

```
Layer 3 candidate generation
  └─ LLM proposes phenomena for each candidate class
     └─ critic LLM verifies / rejects
```

After F1:

```
Layer 3 candidate generation
  ├─ LLM proposes phenomena for each candidate class           (primary)
  └─ EmbeddingBridge.expand_candidate_class(class_yaml, k=10)  (recall booster)
     │   ↑ centroid of positive_examples in V1/V2 space
     └─ merge candidates → critic LLM verifies / rejects       (LLM still arbiter)
```

The critic remains the source of truth; F1 just widens the funnel.

## 6. Limitations of the TF-IDF fallback

Smoke test on `percolation_connectivity` (5 positive examples) returned operating-system / immunology phenomena ranking near the top — these are *not* structurally percolation-like; they share Chinese character n-grams (e.g. 系统, 临界, 阈值). This confirms the design: **TF-IDF is a development/CI placeholder, not a production signal**. Real V1/V2 model on VPS gives Silhouette 0.85 / R@5 100% on holdout — that's the quality F1 unlocks once the bridge is wired through to a model-bearing host.

## 7. F1.1 — VPS deployment (next step, not in this PR)

- Stand up a thin HTTP endpoint on VPS that wraps `EmbeddingBridge(version='v2', model_path=…)` (model already provisioned).
- Add a `RemoteEmbeddingBridge` class that POSTs query texts to the endpoint and pulls back cosine scores — same `Neighbor` interface, so Layer 3 callers don't change.
- Auth via existing VPS Bearer token (same one used by cc-daemon).

## 8. F2 — Active-learning loop (deferred)

When V4 critic rejects an F1 suggestion, log `(class_id, suggested_id, "rejected_by_critic")` to a feedback file. Periodically (monthly or after N rejections), use these as new hard-negatives to re-fine-tune V1/V2 → V3. **Out of scope for F1.**

## 9. Tests

`v4/tests/sanity/test_embedding_bridge.py` covers (13 cases, 2.78s):

- Construction loads V1 (4475) and V2 (4443) caches; rejects unknown versions.
- `suggest_neighbors`: dict input, str input, empty input, ranking is descending, similarity ∈ [-1, 1], `exclude_ids` honoured, self-id auto-excluded.
- `expand_candidate_class`: works on real `percolation_connectivity.yaml` and `hysteresis_first_order_transition.yaml`, handles missing/empty `positive_examples` gracefully.
- `Neighbor.to_dict()` serialisation.

All run under the `sanity` marker; no LLM calls, no network. CI-safe.

## 10. Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-05-13 | Use V2 as default | More pairs (3017 vs V1), richer training signal |
| 2026-05-13 | Char-bigram TF-IDF fallback (not word) | Chinese text — no Chinese tokenizer dep needed |
| 2026-05-13 | Tfidf path goes 2-hop via V1/V2 centroid (not pure TF-IDF) | Keeps the result re-ranking inside the trained latent geometry — at least the *output order* respects V-space, even if the pseudo-query is rough |
| 2026-05-13 | `expand_candidate_class` uses centroid of positives (not per-seed) | Single centroid biases toward the class's "centre of mass"; per-seed adds noise + dup risk. Per-seed kept as a future diagnostic. |
| 2026-05-13 | Defer F1.1 (VPS endpoint) to its own PR | F1 alone is meaningful (interface + fallback + tests); VPS HTTP boundary is a separate concern |
