# gardner_collins_toggle_switch

**Name (zh)**: 双稳态 Toggle Switch 类
**Name (en)**: Gardner-Collins Bistable Toggle
**Pre-registered exponent band**: Hill coefficient n ∈ [2.0, 4.5]; bimodality dip ratio (min/peak density) < 0.25; polarised-state dwell time exponential cutoff τ ∈ [5, 40] days. Rationale: Gardner–Cantor–Collins 2000 Nature 403:339 (synthetic toggle, n ≈ 2.5–3.5); Mariani et al. 2010 (Th1/Th2 polarization in mice, n ≈ 2.8).
**Verified status**: false (target: v0.4). B3 consensus = MERGE (with `gardner_collins_toggle_switch_v2` — see that file). Verification is the natural prerequisite to deciding the merge.

## Why this class needs an empirical anchor

The toggle switch is one of the most cited motifs in synthetic biology and immunology and is *not* a mere descriptor — mutual repression with Hill kinetics is a clear mechanism. The B3 MERGE flag indicates overlap with v2 (the Hill-ultrasensitive variant); validation will surface whether v1 and v2 are empirically distinguishable (different n bands? different dwell-time distributions?) or whether the merge is justified.

KB linkage: 5 members — X-inactivation locking, synthetic genetic toggles, Th1/Th2 polarization, Rb G1/S switch, insulin developmental timing.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Gardner–Cantor–Collins 2000 Nature 403:339 supplementary (synthetic genetic toggle in E. coli, IPTG/aTc induction) | doi:10.1038/35002131 | Free supplementary | ~24 induction profiles | Canonical anchor — the paper that defines the class; n, threshold directly fittable | Small N; old data quality |
| 2 [fallback] | Tabula Muris Senis CD4 T-cell scRNA-seq atlas (Th1/Th2 polarization markers Tbx21/Gata3) | https://tabula-muris-senis.ds.czbiohub.org/ | CC-BY 4.0 | ~110k T cells across tissues | Tests Th1/Th2 bimodality at single-cell resolution | T-cell heterogeneity confounds bimodality; gating subjective |
| 3 [stretch] | ImmPort SDY1412 / SDY1419 single-cell datasets (allergic rhinitis + TB CD4 panels) | https://immport.org/shared/study/SDY1412 | Free, registration | ~45 patients × 5–15k cells | Original pre-registered target; clinical relevance | Registration friction; cross-batch normalisation |

## Validation procedure (concrete)

```bash
mkdir -p data/gardner_collins_toggle_switch

# 1. Download Gardner 2000 supplementary
curl -L "https://www.nature.com/articles/35002131" -o data/gardner_collins_toggle_switch/gardner2000.html
# (extract Fig 5 + supplementary tables manually or via OCR)

# 2. Tabula Muris Senis CD4 subset
python -c "
import scanpy as sc
adata = sc.read_h5ad('TabulaMurisSenis_FACS_CD4.h5ad')
adata.obs['tbx21'] = adata[:,'Tbx21'].X.toarray().ravel()
adata.obs['gata3'] = adata[:,'Gata3'].X.toarray().ravel()
adata.obs[['tbx21','gata3']].to_csv('data/gardner_collins_toggle_switch/cd4_tbx_gata.csv')
"

# 3. Validate
python -m v4.cli validate gardner_collins_toggle_switch \
  --data data/gardner_collins_toggle_switch/cd4_tbx_gata.csv \
  --method bimodal-fit --hill-fit \
  --alpha-band 2.0,4.5 --null-controls unimodal-gaussian,lognormal

# 4. Expected verdicts
#   PASS:  bimodal Gaussian-mixture preferred over unimodal by BIC, dip ratio < 0.25,
#          Hill n ∈ [2.0, 4.5] from steady-state I/O curve fit
#   FAIL:  unimodal preferred OR Hill n outside band
```

## Estimated workload

- Data acquisition: 3 h (Tabula Muris is straightforward; ImmPort needs registration)
- Pipeline run: 4 h (scRNA-seq normalisation + GMM fit + Hill fit + bootstrap)
- Verdict + writeup: 2 h
- **Total: ~9 h / 1–1.5 days**

## Risks specific to this class

1. **scRNA-seq dropout** inflates apparent bimodality; must correct via MAGIC / scVI imputation or use protein-level CITE-seq subset.
2. **Cell-cycle confound**: Tbx21/Gata3 expression varies with cycle; restrict to G0/G1.
3. v1 vs v2 cannot be distinguished from a single dataset — need to validate both with the *same* pipeline to compare residuals; coordinate with `gardner_collins_toggle_switch_v2.md`.

## Priority

⭐⭐⭐⭐⭐ (rationale: textbook mechanism, free data, MERGE decision pending — high paper-section yield)

## Dependencies

- `scanpy`, `anndata`, `sklearn.mixture` (GMM), `scipy.optimize` (Hill fit)
- ImmPort registration optional for fallback only
- Storage: ~5 GB for Tabula Muris CD4 subset
