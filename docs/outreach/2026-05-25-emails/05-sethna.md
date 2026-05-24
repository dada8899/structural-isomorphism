**To:** [Prof. James P. Sethna — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** RFIM Barkhausen + Preisach hysteresis validation in a 27-system cross-domain pipeline — adversarial review request

Dear Prof. Sethna,

I am writing because two of the universality classes our cross-domain validation pipeline tests are squarely in your territory — RFIM Barkhausen / crackling-noise avalanches and Preisach hysteresis — and I would value an adversarial read from someone who has thought longer than anyone about whether these classes mean what their tail exponents suggest.

The project (one frozen Clauset-Shalizi-Newman pipeline applied unchanged across **27 systems**, commit `7ee228c`, full code on GitHub) has two findings relevant to your work I want to flag honestly, neither of which I am fully comfortable with:

- **RFIM / crackling-noise class** is on our taxonomy as KEEP, with tail exponents in the predicted band on the synthetic-control benchmarks. We have *not* yet exercised it on a real-data Barkhausen avalanche catalog of the calibre of the Faulkner-Maaß-Sethna runs. This is on the to-do list and we say so, but I want to ask: is a paper that puts RFIM on a taxonomy without a fresh real-data Barkhausen test premature?

- **Preisach hysteresis** had its monolithic single-class formulation **demoted** by our B3 critic ensemble (7/21 REJECT, 33%) on the grounds that "Preisach hysteresis as one universality class" conflates distinct mechanisms (single-domain vs collective-pinning regimes, geometric vs dynamic disorder, rate-independent vs viscous limits). The A2-Hysteresis empirical test on NGSIM US-101 highway traffic does confirm a first-order Preisach loop-width ratio of $1.38 \in [1.25, 1.55]$ from literature anchors — but the taxonomy entry above the empirical test was split, not kept. I would value your read on whether that split is right and where the natural sub-class boundaries actually lie.

Three asks, any subset of which would help:

(a) Would you skim arXiv:[PENDING_ARXIV_ID] §3.12 (A2-Hysteresis NGSIM) and §5 (B3 verdicts on Preisach) and flag the weakest claim?

(b) Are there RFIM Barkhausen catalogs we could run the pipeline on tomorrow that would be the natural validation set (FeCoB / Ni81Fe19 ribbon / your group's archival data)?

(c) Anything the field now treats as RFIM that is not RFIM, that we should worry about double-counting?

Code reproducible end-to-end, three PyPI packages, Zenodo DOI [PENDING_ZENODO_DOI]. No endorsement requested.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]
