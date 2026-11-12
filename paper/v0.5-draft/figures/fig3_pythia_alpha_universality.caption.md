**Figure 3.  Pythia α cross-source universality.**

*Panel A.* Per-source mean α with error bars across 5 source recipes. Both
LAMBADA evaluators (v1 unconstrained, v2 L\_inf-constrained) deliver
TIGHT_UNIVERSALITY (CV < 0.15), while train-loss recipes (quality-filtered or
mixed) sit in BROAD_SPREAD even after dropping the broken 1.4b fit. *Panel B.*
Per-size α trajectories across the 8 Pythia checkpoints for three sources:
LAMBADA v1 and v2 trace nearly parallel curves inside the TIGHT band, train-loss
shows order-of-magnitude swings (pythia-1.4b α≈2.0 with R²<0 is the broken fit
diagnosing the BROAD_SPREAD outcome). *Panel C.* Spotlight on pythia-12b (the
largest Pythia checkpoint, only available in LAMBADA v1 and v2): σ across the
two LAMBADA recipes is 0.011 (CV = 0.063), the tightest cross-source agreement
in the panel. Cross-evaluator panel (WikiText / HellaSwag) omitted because the
upstream data is not yet committed. Source data:
`v4/validation/llm-scaling/cross_source_summary.json`, `results_lambada.json`,
`results_lambada_v2.json`.
