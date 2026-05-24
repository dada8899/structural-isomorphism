**To:** [Prof. Aaron Clauset — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** A pipeline that uses your 2009 SIAM Review code on 27 systems — courtesy notification + misapplication audit

Dear Prof. Clauset,

I am writing as a courtesy: a cross-domain validation preprint we are about to put on arXiv is built directly on the Clauset-Shalizi-Newman 2009 *SIAM Review* pipeline (MLE + KS-based $x_{\min}$ + bootstrap CIs + Vuong likelihood ratios). I want you to know it is happening, and I would value any flag you have time to throw on places where we have misapplied the method.

The pipeline is one frozen Python module (`v4/lib/soc_pipeline.py`, 339 lines, commit `7ee228c`) applied unchanged across **27 independent systems** (geology, equity finance, DeFi, neural avalanches, plasma astrophysics, ecology, banking history, software communities, power grids, highway traffic, lake biogeochemistry). We explicitly run the parts of your 2009 framework I read as the load-bearing parts: MLE fit, KS-based $x_{\min}$, parametric bootstrap goodness-of-fit, Vuong likelihood ratios against lognormal and exponential, plus log-binned density + BIC as a secondary check. Where Vuong is inconclusive (3 of 9 systems on raw tails), we say so, and on log-binned BIC the comparison flips and lognormal wins 0/7; the procedural tension is discussed honestly in §6.2.

Three asks, any of which would be valuable:

(a) Would you be willing to skim arXiv:[PENDING_ARXIV_ID] Table 1 and §3 and flag any system where you would say the Clauset 2009 framework was applied outside the regime your paper considered reliable (small $n$, heavy censoring, narrow dynamic range)?

(b) On `powerlaw` package vs your reference R / MATLAB implementation: we use Alstott et al. We did not independently re-implement. Is that a documented gap in current practice we should close before submission, or is `powerlaw` now accepted as a faithful port?

(c) Anything in the 2009 paper that the community now systematically gets wrong and we have probably also gotten wrong without noticing?

Code is reproducible end-to-end, three PyPI packages (`structural-isomorphism-core`, `-validation`, `-critic`), Zenodo DOI [PENDING_ZENODO_DOI]. No endorsement requested — only flags.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]
