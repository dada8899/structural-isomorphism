# universality-classes.json: duplicate class_id resolution

**Date**: 2026-05-14
**Affected file**: `web/frontend/assets/data/universality-classes.json`
**Source of issue**: W6-E (session #3 wave 6, regression test) flagged 2 duplicate `class_id` values
**Fixed in commit**: `bfdf2b0` (`v4/fix (F1): P1 bugs — dedupe class_id + phase.bytedance.city React error`), session #3
**Verified in this maintenance pass (2026-05-14)**: all 23 entries have unique `class_id`

---

## What was duplicated

Two pairs of Louvain sub-communities had identical `class_id` because the curation script (manual layer + LLM layer) produced two independent records that resolved to the same physics prototype slug:

| Original `class_id` | Source | Sub-community | b3_consensus | size | n_domains |
|---|---|---|---|---|---|
| `motter_lai_network_cascade` | manual | "Motter-Lai 网络级联类" (hub = building progressive collapse) | SPLIT | 6 | 5 |
| `motter_lai_network_cascade` | llm | "Motter-Lai 负载重分配网络级联类" (hub = cascading failures in social networks) | SPLIT | 3 | 3 |
| `gardner_collins_toggle_switch` | manual | "双稳态 Toggle Switch 类" (hub = Th1/Th2 polarization) | MERGE | 5 | 4 |
| `gardner_collins_toggle_switch` | llm | "Hill 超敏正反馈双稳态开关类" (hub = caspase apoptotic switch) | MERGE | 3 | 3 |

Both pairs were **legitimately distinct Louvain sub-communities** (different members, different domains, different hub nodes) — not data-pipeline mistakes. They collided only on `class_id` because both sub-communities mapped to the same physics prototype name (Motter-Lai, Gardner-Collins).

---

## Resolution decision

**Policy chosen**: rename — keep both entries, suffix the lower-rank (LLM-curated, smaller `size`) entry with `_v2`. No information loss.

Rationale:

1. **Drop is wrong**: each sub-community contains real domain members that the cross-domain analysis depends on. Dropping the LLM-curated `_v2` entries would lose verified cross-domain edges.
2. **Merge is also wrong for SPLIT**: B3 consensus on the `motter_lai_*` pair was explicitly `SPLIT` — the human-in-the-loop critic panel said these should remain split despite sharing a physics prototype label.
3. **Rename preserves both with no data loss**: downstream consumers (`/classes` page, KB embedding pipeline, taxonomy-v2 cross-ref) treat them as distinct classes again. The `taxonomy_match` field on the `_v2` entries still points to the parent prototype slug, so the linkage is preserved for documentation purposes.

### Post-fix state (verified 2026-05-14)

```python
>>> import json
>>> data = json.load(open("web/frontend/assets/data/universality-classes.json"))
>>> ids = [c["class_id"] for c in data["classes"]]
>>> len(ids), len(set(ids))
(23, 23)
>>> # No duplicates.
```

All 23 `class_id` values are now unique:

| # | class_id | curation | b3_consensus |
|---|---|---|---|
| 4 | `motter_lai_network_cascade` | manual | SPLIT |
| 13 | `motter_lai_network_cascade_v2` | llm | SPLIT |
| 6 | `gardner_collins_toggle_switch` | manual | MERGE |
| 15 | `gardner_collins_toggle_switch_v2` | llm | MERGE |

The remaining `taxonomy_match` collisions (`soc_threshold_cascade`, `hysteresis_first_order_transition`, `multistable_self_fulfilling`, `preferential_attachment` — each appearing 2× across the 23 classes) are **not** bugs: they are the intended mapping from Louvain sub-communities to the upper-level 35-class taxonomy. Multiple sub-communities legitimately share a parent taxonomy node.

---

## Pending follow-up (out of scope of this fix)

The two `gardner_collins_toggle_switch*` entries both carry `b3_consensus: MERGE`, meaning the critic panel recommends *eventually* merging them after collecting more cross-domain evidence. This is research follow-up, not a data-integrity bug. Tracked in `docs/sessions/HANDOFF.md` § P2 backlog ("review B3 MERGE verdicts after Layer 5 Phase 4+ data lands").

---

## Provenance / how to reproduce the check

```bash
cd ~/Projects/structural-isomorphism
./.venv/bin/python -c "
import json
from collections import Counter
data = json.load(open('web/frontend/assets/data/universality-classes.json'))
classes = data['classes']
ids = [c['class_id'] for c in classes]
counter = Counter(ids)
dupes = {k:v for k,v in counter.items() if v>1}
assert not dupes, f'duplicate class_ids: {dupes}'
print(f'OK: {len(ids)} unique class_ids')
"
```

Suggested CI guard: add the above assertion to the `web/backend/tests/` suite so a regression is caught automatically.
