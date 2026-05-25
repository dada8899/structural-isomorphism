**To:** [Prof. Aaron Clauset — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** v0.5 update — same 2009 SIAM Review pipeline applied to 8 Pythia × 27 LAMBADA checkpoints + honest negative

Dear Prof. Clauset,

Quick v0.5 follow-up to my 2026-05-25 courtesy notification. v0.4 arXiv submission is still pending; the v0.5 draft (`paper/v0.5-draft/v05-draft-skeleton.md`, HEAD `14a73c4`) extends the pipeline in two directions worth flagging because they are the kind of place I would most expect to misapply your 2009 framework.

(a) **Pythia LAMBADA scaling-law cross-fit (§4).** We apply the Clauset-style fit family `L(C) = A·C^(−α) + L_inf` to 8 Pythia sizes × 27 standard EleutherAI checkpoints (216 (size, checkpoint) pairs). v1 (L∞ unconstrained) gives mean α = 0.144, CV = 0.118 across sizes — TIGHT_UNIVERSALITY by our pre-registered convention (CV < 0.20). v2 (L∞ ∈ [1.0, 5.0] anchored to the LAMBADA-OpenAI literature floor) gives mean α = 0.159, CV = 0.116. **Mean R² *decreased* by 0.018 in v2** — all 8 sizes hit the lower bound. We report this as an honest negative finding: within Pythia training-compute range, LAMBADA log-perplexity is still in the power-law-decay regime, not the floor-bounded regime. The headline contribution is the *cross-fit robustness* of α, not an R² improvement.

(b) **`aggregation_kinetics` PASS-STRONG (§5)** — two of three Layer 1 anchors (Cruz 1997, Brú 2003) use pre-Clauset log-log linear fitting on the CCDF (the methodology your 2009 §6 specifically criticised). In-band result robust to method choice; SEs not directly comparable to the Hartig 2018 Clauset-MLE SE. Honest path forward: contemporary Clauset MLE re-fit on Cruz 1997 + Brú 2003 raw data, if recoverable.

Three asks:

(a) Is the §4 v1 vs v2 cross-fit framing — "TIGHT verdict is robust to L∞ specification" — a defensible application of your 2009 framework, or do we need to fit a single global L∞ across all 8 sizes (Hoffmann 2022 style) before claiming the universality at all?

(b) Anything in §4 we have plausibly applied outside the regime your 2009 paper considered reliable?

(c) Same question as 2026-05-25 on `powerlaw` vs your reference R/MATLAB implementation.

Repo public, ~20 min on §4 + §5 Caveat B should suffice. No endorsement requested.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
