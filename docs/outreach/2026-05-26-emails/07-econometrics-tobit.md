**To:** [NAME — senior methodologist, probit / threshold-tobit reparametrisation, EMAIL]
**Affiliation:** [AFFILIATION — econometrics or psychometrics]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** Adversarial review request — (s\*, k) threshold-tobit reparametrisation applied to a Schelling credible-commitment validation

Dear Prof. [NAME],

I am writing because a recent methodology increment in a cross-domain validation project we are about to put on arXiv applies a probit / threshold-tobit reparametrisation in a setting that I think benefits from your specifically adversarial read — a setting outside the canonical microeconometric application but structurally close enough that misapplications would matter.

The setting (`paper/v0.5-draft/v05-draft-skeleton.md` §3.6.5, HEAD `14a73c4`): a Schelling credible-commitment universality-class validation (§6) used a v0.4 pre-registration that pinned (i) a logit slope band `b ∈ [1.2, 2.6]` AND (ii) two point follow-through rates `p(s > 0.4) > 0.75` and `p(s < 0.2) < 0.35` — but the slope implied algebraically by (ii)+(iii) is `b > 8.59`, outside the pre-registered slope band. The v0.4 INCONCLUSIVE verdict was forced by *mutual inconsistency of the pre-registration*, not by an empirical mechanism failure.

The v0.5 fix replaces the logit with a probit `p(s) = Φ((β s − τ)/σ)` and reparametrises to:

- `s* = −τ/β + μ` — midpoint of the dose-response curve (s-value at which p = 0.5)
- `k = β/σ` — standardised probit slope

The point-rate constraints become *derived diagnostics* of the fitted (s\*, k) box, not independent pre-registered targets. We pre-registered independent bounds (`s* ∈ [0.20, 0.35]`, `k ∈ [4, 12]`) anchored to Bown 2009 + Horn-Mavroidis WTO retaliation data. A cross-class applicability audit returned **N/A for three other candidate binary-outcome classes**.

Three asks, any of which would be valuable (~30 min, §3.6.5 + the cross-class retrospective at `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`):

(a) Is the (s\*, k) reparametrisation the right tool here, or are we re-inventing something that the threshold-tobit / probit literature handles more cleanly (e.g., Greene / Wooldridge / Cameron-Trivedi treatments)?

(b) The Horn-Mavroidis WTO real-data sanity check (n = 23, `sec-6-real-data-update.md`) returns a sign-reversed probit slope. We attribute this to observational selection on defendant intransigence rather than to a refutation of Schelling's exogenous-`s` theory. Is the identification framing right?

(c) Anything we are about to misapply this pattern to in v0.6 batches.

This is review-solicitation, not endorsement or collaboration. Repo public, code reproducible. No follow-up beyond one ping at T+10 days.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
