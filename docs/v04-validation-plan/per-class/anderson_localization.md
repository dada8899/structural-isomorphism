# anderson_localization

**Name (zh)**: Anderson 局域化 (金属-绝缘体相变)
**Name (en)**: Anderson localization (metal-insulator transition)
**Pre-registered exponent band**: Correlation-length exponent ν ≈ 1.57 ± 0.06 in 3D orthogonal class (Slevin–Ohtsuki 2014 New J Phys 16:015012 high-precision numerics); critical disorder W_c / hopping t ≈ 16.5 ± 0.5 for box-distribution disorder. Universal critical conductance distribution P(g) reproducible.
**Verified status**: unverified (no `verified` field — confidence "well-established"). No KB predictions yet — taxonomy-completion entry.

## Why this class needs an empirical anchor

Anderson localization is one of the most rigorously established universality classes in condensed-matter physics (Nobel Prize 1977). Numerics already give ν to 4 significant figures. The empirical anchor here is **not** to discover ν but to demonstrate that the *cross-system* universality — cold atoms / photonics / random networks all in the same orthogonal class — survives in real data. This is a textbook-completeness validation rather than a discovery.

KB linkage: 5 members listed across Condensed matter / Photonics / Cold-atom / Random network theory. Specific members not enumerated in JSON; grep KB JSONL.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Aspect group cold-atom Anderson localization data — Billy et al. 2008 Nature 453:891 + Jendrzejewski et al. 2012 Nat Phys 8:398 supplementary | DOI:10.1038/nature07000 | Free supplementary | ~50 experimental conditions | Cleanest cross-domain anchor; ν estimable from finite-size scaling of localisation length | Supplementary data often only as figure PDFs — needs digitisation |
| 2 [fallback] | Synthetic Anderson tight-binding numerics with box-distribution disorder on 3D cubic lattice (own simulation, GPU) | own code | — | up to L=128 (10⁶ sites) | Re-derives ν as numerical sanity check; full control of disorder distribution | Not "empirical" — synthetic only; defensible because Anderson class is already textbook-established |
| 3 [stretch] | Photonic localization data — Schwartz et al. 2007 Nature 446:52 (disordered photonic lattice) supplementary | DOI:10.1038/nature05623 | Free supplementary | ~30 lattice configurations | Tests cross-domain (cold atom + photonic) universality of ν | Smaller statistics; photonic class may be unitary not orthogonal |

## Validation procedure (concrete)

```bash
mkdir -p data/anderson_localization

# 1a. Digitise Billy 2008 figures (supplementary) — manual or WebPlotDigitizer
# Outputs: localisation length xi vs disorder strength W

# 1b. OR run own tight-binding finite-size scaling
python scripts/anderson_tightbinding_fss.py \
  --lattice 3d-cubic --sizes 16,24,32,48,64 \
  --disorder 12,14,16,16.5,17,18,20 \
  --out data/anderson_localization/fss_results.npz

# 2. Fit ν from finite-size scaling collapse
python -m v4.cli validate anderson_localization \
  --data data/anderson_localization/fss_results.npz \
  --method finite-size-scaling --order-param xi/L \
  --nu-band 1.51,1.63 --wc-band 16.0,17.0 \
  --null-controls power-law-no-transition,first-order

# 3. Expected verdicts
#   PASS:  ν ∈ [1.51, 1.63], W_c ∈ [16.0, 17.0] for orthogonal 3D class,
#          scaling collapse R² > 0.95
#   FAIL:  exponents outside narrow band (would contradict 50 y of literature → suspect data/code bug)
#   INCONCLUSIVE: finite-size effects dominate; need larger L
```

## Estimated workload

- Data acquisition: 4 h (digitisation OR setting up tight-binding simulation)
- Pipeline run: 8 h (FSS over 7 disorder × 5 sizes, each L=64 takes ~hour single-thread, ~10 min GPU)
- Verdict + writeup: 3 h
- **Total: ~15 h / 2 days** (extendable with larger L for tighter ν)

## Risks specific to this class

1. **Synthetic-not-empirical**: primary fallback is own tight-binding simulation. Defensible because the universality class is *already* textbook; the v0.4 paper section is "we recover the known value as a sanity check," not "we discover ν."
2. **Symmetry class**: 3D orthogonal ν ≈ 1.57, unitary ≈ 1.43, symplectic ≈ 1.38. Pre-register which class each empirical source belongs to.
3. **Photonic vs cold-atom universality differences**: photonic experiments may break time-reversal symmetry → unitary class. Cross-domain comparison must respect symmetry-class boundaries.

## Priority

⭐⭐ (rationale: canonical textbook physics; result is essentially predetermined; mainly useful for taxonomy completeness and as cross-check on the validation pipeline)

## Dependencies

- `numpy`, `scipy.sparse.linalg` (large sparse eigenproblem)
- Optional: `cupy` or `torch` for GPU acceleration
- WebPlotDigitizer for figure digitisation
- Storage: < 5 GB
