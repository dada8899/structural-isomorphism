**To:** [Prof. Michael P. H. Stumpf — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** "Critical Truths" (2012) as a falsification target for a 27-system Clauset pipeline — adversarial review request

Dear Prof. Stumpf,

I am writing to ask whether you would be willing to read a cross-domain validation pipeline I have built explicitly with your 2012 *Science* paper "Critical Truths About Power Laws" (with Mason Porter) as the adversarial standard. The point of the request is not that I think we passed your test; the point is that I would like you to tell me where we did not.

The pipeline applies one frozen Python module (`v4/lib/soc_pipeline.py`, 339 lines, commit `7ee228c`) — Clauset-Shalizi-Newman MLE with KS-driven $x_{\min}$, bootstrap CIs, Vuong likelihood ratios against lognormal and exponential, matched-$n$ synthetic null controls, log-binned density estimation, BIC model comparison — unchanged across **27 independent systems** (geology, equity finance, DeFi, neuroscience, plasma astrophysics, ecology, banking history, software communities, power grids, highway traffic, lake biogeochemistry). Three of the qualifications I read as central to your 2012 argument we address directly and report honestly:

- **Raw-tail Vuong vs lognormal is inconclusive or favours lognormal in 3/9 systems** (S&P 500, NIFC wildfires, Wikipedia pageviews). We do not paper over this; §6.2 of the preprint discusses the BIC-vs-Vuong tension at length.
- **Phase 7 power-grid catalog ($n=123$) is literature-anchored, not OE-417 direct.** We flag verification independence as LOW and the verdict as "consistent with anchors, not independent".
- **Phase 13 Wikipedia pageviews** survives Clauset-pipeline tail-fit but is cross-sectional, not the $\propto k$ longitudinal attachment-kernel test.

Three asks, any of which would be valuable:

(a) Would you be willing to spend 30 minutes skimming arXiv:[PENDING_ARXIV_ID] §3 and Table 1, and flagging any of the nine systems where you would now, in 2026, say the test does not meet your 2012 bar?

(b) The companion methodology preprint (arXiv:[PENDING_ARXIV_ID]-c4) reports a separate finding: a within-vendor multi-decoding LLM-critic ensemble flagged 7/21 candidate universality classes as REJECT (33%), versus 3/21 (14%) for a single critic — mostly demoting *mathematical frameworks masquerading as universality classes*. I would value your read on whether that framing maps onto the trap your 2012 paper named.

(c) Anything obvious we did not test.

We are not seeking endorsement. Repo is public, code is reproducible, Zenodo DOI [PENDING_ZENODO_DOI].

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]
