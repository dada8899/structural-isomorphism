**To:** [Prof. James P. Sethna — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** v0.5 update — `aggregation_kinetics` is a multilayer cousin to crackling-noise; would value your read

Dear Prof. Sethna,

Quick v0.5 follow-up to my 2026-05-25 note. v0.4 arXiv submission is still pending. The v0.5 draft (`paper/v0.5-draft/v05-draft-skeleton.md`, HEAD `14a73c4`) introduces a new universality class — `aggregation_kinetics`, PASS-STRONG — that I think is structurally a multilayer cousin to the RFIM Barkhausen / crackling-noise class your work helped articulate, and would benefit from your read for that reason.

The construction (§5 + §3.6.6 methodology):

- **Layer 1 (per-aggregate)**: Clauset MLE power-law with predicted α ∈ [1.7, 3.5] from Smoluchowski coagulation theory. Anchored across **3 distinct biological domains**: Cruz 1997 (human cortical plaques, α = 1.70, ~6,500 plaques); Hartig 2018 (5xFAD mouse cortex, α = 2.10, ~12,400 plaques, contemporary Clauset MLE); Iwata 2000 (theory) + Brú 2003 (empirical, ~1,500 tumor colonies across 7 cancer types, α ≈ 2.05).
- **Layer 2 (cross-population)**: Vuong R < 0 vs power-law at p < 0.05, anchored on Hyman 2008 (multiplicative-stochastic patient-level Aβ progression). Verified at 4/5 Allen Brain TBI Aβ series.

Two of three Layer 1 anchors are pre-Clauset (log-log linear on CCDF), which is a real methodology concern flagged honestly in §5 Caveat B. The MERGE recommendation from v0.4 (`preisach_hysteresis_cascade` + `rfim_barkhausen` → `crackling_noise_universality`) is unchanged in v0.5.

Three asks, any subset of which would help:

(a) Is the multilayer test pattern (§3.6.6) the right framing for crackling-noise-style classes more broadly? RFIM avalanches have a natural per-event Layer 1 (size distribution) and a cross-event Layer 2 (waiting-time distribution); we have not yet run that decomposition.

(b) Real-data RFIM Barkhausen catalog ask from 2026-05-25 still stands — your group's archival data or FeCoB / Ni81Fe19 ribbon datasets would be the natural validation set for the pattern.

(c) Anything obvious we have misclassified by treating `aggregation_kinetics` as a separate class from the crackling-noise family.

Repo public, ~30 min on §3.6.6 + §5 should suffice. No endorsement requested.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
