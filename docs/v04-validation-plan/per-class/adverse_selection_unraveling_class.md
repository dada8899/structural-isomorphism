# adverse_selection_unraveling_class

**Name (zh)**: 逆向选择与柠檬化退化类
**Name (en)**: Adverse Selection & Lemons Market Unraveling
**Pre-registered exponent band**: Diversity-decay half-life t_{1/2} ∈ [3, 14] days; Akerlof-equation parameter ratio α/β ∈ [1.15, 2.40] (> 1 ensures collapse). Rationale: Akerlof 1970 QJE 84:488, Noelle-Neumann 1974 spiral-of-silence, Bakshy–Messing–Adamic 2015 Science 348:1130 (Facebook filter bubble empirics).
**Verified status**: false (target: v0.4). B3 consensus = SPLIT — splits suggested between econ-side adverse selection and communication-side spiral-of-silence.

## Why this class needs an empirical anchor

SPLIT consensus says economic adverse selection (Akerlof lemons) and social-media spiral-of-silence may share an *equation* but not a *mechanism* — the unobservables are different (private quality info vs. private opinion). Empirical validation tests whether the *decay dynamics* match: if both produce the same Akerlof recursion with the same α/β ratio band, the cross-domain analogy is real and SPLIT can be downgraded.

KB linkage: 4 members — adverse selection (economics), spiral of silence (communications), filter bubbles (unlabelled), echo-chamber effect (unlabelled).

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Reddit Pushshift archive (political subreddits 2018–2023, post-API-shutdown snapshot) | https://academictorrents.com/details/9c263fc85366c1ef8f5bb9da0203f4c8c8db75f4 | Free, academic | ~3 TB total; ~50 GB political-subset | Direct measurement of diversity (Shannon entropy) decay in 50 political topics | Pushshift coverage gaps post-2023; Twitter Academic API now closed |
| 2 [fallback] | eBay auctions adverse-selection dataset (Lewis 2011 AER 101:1535, used-car listings replication data) | https://www.aeaweb.org/articles?id=10.1257/aer.101.4.1535 | CC-BY 4.0 | ~10⁵ listings 2002–2009 | Classic Akerlof empirics; cleaner identification of α/β | Older data; specific to eBay's then-policy |
| 3 [stretch] | Bluesky firehose archive (curated political feed subset, 2024–2025) | https://docs.bsky.app/docs/get-started + manual scraping | CC-BY 4.0 of public posts | ~50 GB | Modern replication on new platform | Short history; user base not yet representative |

## Validation procedure (concrete)

```bash
mkdir -p data/adverse_selection_unraveling_class

# 1. Reddit Pushshift political subset
# (use academictorrents bulk + filter)
python scripts/filter_pushshift_political.py \
  --in pushshift_full.zst \
  --subreddits politics,Conservative,Libertarian,ChapoTrapHouse,The_Donald \
  --out data/adverse_selection_unraveling_class/political_posts.parquet

# 2. Track Shannon entropy over time per topic
python -m v4.cli validate adverse_selection_unraveling_class \
  --data data/adverse_selection_unraveling_class/political_posts.parquet \
  --method entropy-decay --topic-detection bertopic \
  --alpha-band 1.15,2.40 --null-controls flat-entropy,growth-not-decay

# 3. Expected verdicts
#   PASS:  Shannon entropy decays as D(t+1) = D(t)(1-alpha) + beta*N(t) with alpha/beta in band,
#          half-life within [3, 14] days, and pattern replicates on eBay adverse-selection data
#   FAIL:  entropy stable or growing OR alpha/beta < 1 (no collapse)
#   INCONCLUSIVE: Reddit fits but eBay doesn't (or vice versa) → SPLIT confirmed
```

## Estimated workload

- Data acquisition: 6 h (Pushshift bulk is large; filtering is I/O-heavy)
- Pipeline run: 8 h (BERTopic on 10⁵ posts is the bottleneck)
- Verdict + writeup: 3 h
- **Total: ~17 h / 2 days**

## Risks specific to this class

1. **Pushshift quality**: Reddit changed API access in mid-2023, so the archive is incomplete for recent dates. Restrict primary analysis to 2018–2022.
2. **Topic-modelling noise**: BERTopic clusters drift across time, biasing entropy measurement. Use a fixed topic vocabulary inferred from a 2018 baseline.
3. **Cross-domain α/β comparison** requires both Reddit and eBay to be processed through the same Akerlof recursion specification. The communication-side N(t) (new participants) and economics-side N(t) (new listings) are not commensurable units — pre-register the dimensionless reformulation.

## Priority

⭐⭐⭐ (rationale: high paper interest but compute-heavy; SPLIT confirmation may already be the expected outcome)

## Dependencies

- `pyzstd`, `pyarrow`, `bertopic`, `sentence-transformers`, `scipy`
- No API key (Pushshift bulk via academictorrents)
- Storage: ~50 GB for political-subset Reddit; ~500 MB for eBay
- GPU recommended for BERTopic embedding step
