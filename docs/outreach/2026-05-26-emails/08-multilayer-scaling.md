**To:** [NAME — senior physicist, allometric / multi-scale critical phenomena, EMAIL]
**Affiliation:** [AFFILIATION — physics / quantitative biology / complex systems]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** Adversarial review request — multilayer test pattern for cross-domain universality classes (§3.6.6)

Dear Prof. [NAME],

I am writing because a recent methodology increment in a cross-domain SOC validation project we are about to put on arXiv proposes a *multilayer test pattern* for candidate universality classes whose underlying theory predicts different scaling forms at different scales — and I would value your specifically adversarial read because the territory (multi-scale critical phenomena; allometric scaling; per-element vs ensemble distributions) is one you have thought about longer than most.

The setting (`paper/v0.5-draft/v05-draft-skeleton.md` §3.6.6, HEAD `14a73c4`): in v0.4 we ran a single-layer cross-section test on β-amyloid aggregation and got 4/5 lognormal-preferred vs. power-law (INCONCLUSIVE). But Hyman 2008 *predicts* cross-section lognormal as the signature of multiplicative-stochastic patient-level progression; the predicted power-law is at the *per-plaque* scale, where Smoluchowski coagulation theory gives α ∈ [1.7, 3.5]. We rebuilt the pre-registration as two independent layers:

- **Layer 1 (per-aggregate)** Clauset MLE power-law, α ∈ [1.7, 3.5]. Anchored across 3 distinct biological domains: Cruz 1997 / Hartig 2018 / Iwata 2000 + Brú 2003.
- **Layer 2 (cross-population)** Vuong R < 0 vs power-law at p < 0.05. Verified at 4/5 Allen Brain TBI Aβ series.

The class becomes PASS-STRONG-MULTILAYER. The combined verdict ladder is `PASS-CONFIRMED-MULTILAYER` / `SPLIT` / `REJECT-MULTILAYER`.

We list four further candidate classes for which this pattern might apply: allometric Kleiber scaling (Layer 1 intra-species, Layer 2 cross-species); preferential-attachment (Layer 1 per-node degree, Layer 2 ensemble size); SOC (Layer 1 per-event size, Layer 2 cross-event Hawkes waiting-time); earthquake productivity (Felzer-Brodsky 2006; Helmstetter 2003).

Three asks, any of which would be valuable (~30 min, §3.6.6 + §5 + candidate table):

(a) Is the Layer 1 / Layer 2 decomposition well-posed for the four candidate classes listed, or are some of them really *one* scaling regime that looks bi-modal under poor binning?

(b) Are there cross-domain anchors (allometric / multi-scale critical) where the pattern would falsify cleanly and we should run next, before claiming generalisability?

(c) The §3.6.6 framing positions the multilayer test as complementary to the descriptor-vs-mechanism cross-domain scatter threshold (§3.5.3 in v0.4). Is that complementarity honest or are we double-counting?

This is review-solicitation, not endorsement or collaboration. Repo public, code reproducible. No follow-up beyond one ping at T+10 days.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
