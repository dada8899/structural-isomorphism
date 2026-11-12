**To:** [Prof. Mason A. Porter — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** Motter-Lai cascade verdict + scale-free percolation REJECT verdict — request for adversarial review

Dear Prof. Porter,

I am writing because two specific verdicts in our cross-domain validation pipeline rest on territory you have shaped — network-cascade dynamics on the Motter-Lai axis, and the broader caution about treating "scale-free" as a single universality class. I would value your specifically adversarial read on whether we got either of them right.

The project (one frozen Clauset-Shalizi-Newman pipeline applied unchanged across **27 systems**, frozen at commit `7ee228c`, code reproducible end-to-end) reports two network-relevant findings I want to flag honestly:

- **Phase 7 (North American power-grid cascades, Motter-Lai class).** Literature-meta catalog of $n=123$ events with $\alpha_{\text{MW}}=2.02 \pm 0.16$, inside the predicted $[1.3, 2.0]$ band at the upper edge. We have flagged verification independence as **LOW** (the catalog was assembled from the same anchors it is compared against); a FOIA-acquired raw OE-417 catalog or non-overlapping ENTSO-E disturbance roster is on the to-do list. I am uncomfortable with the current status and would value your read on whether the "consistent-with-literature-anchors" framing is fair or oversells.

- **`scale_free_percolation_class` REJECT verdict.** Our B3 within-vendor multi-decoding critic ensemble (three DeepSeek decodings, T=0/0/0.6) demoted this class on the grounds that "scale-free percolation as a single universality class" conflates distinct generative mechanisms (continuum percolation, configuration-model percolation, geometric inhomogeneous random graphs) under a shared tail signature — a textbook *mechanism-vs-limit-theorem confusion*. This is the kind of call where I would most value being told we were wrong, in a direction we can defend.

Three asks, any subset of which would be valuable:

(a) Would you skim arXiv:[PENDING_ARXIV_ID] §3.10 (Motter-Lai) and §5 (B3 verdicts) and flag whichever call you find weakest?

(b) Is the n=123 literature-meta catalog enough to make any Motter-Lai claim at all, or should we strip the section back to "literature consistency check, not validation"?

(c) Any cascade dataset or network you wish we had used and we did not (especially anything with cleaner provenance than OE-417)?

We are not seeking endorsement. Repo public, Zenodo DOI [PENDING_ZENODO_DOI], three PyPI packages.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]
