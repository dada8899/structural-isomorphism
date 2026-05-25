**To:** [Prof. Jean-Philippe Bouchaud — preferred CFM / Polytechnique email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** v0.5 update — eval-specific scaling-law universality (Pythia LAMBADA) + Schelling WTO real-data sign-reversal (honest broker request)

Dear Prof. Bouchaud,

Quick v0.5 follow-up to my 2026-05-25 note. The v0.4 arXiv submission is still pending; the v0.5 draft (`paper/v0.5-draft/v05-draft-skeleton.md`, HEAD `14a73c4`) adds two findings that I think you would specifically appreciate having a hard adversarial read on, because both are framed as honest negative-or-restricted results and both touch quantitative-economics methodology.

(a) **Pythia LAMBADA scaling-law cross-fit — TIGHT_UNIVERSALITY is eval-specific (§4).** Same Clauset-style fit family `L(C) = A·C^(−α) + L_inf` across 8 Pythia sizes × 27 LAMBADA-OpenAI checkpoints, with v1 (L∞ unconstrained) and v2 (L∞ ∈ [1.0, 5.0]). Both deliver CV ≈ 0.12 across sizes (TIGHT_UNIVERSALITY by our pre-reg convention). **Pooled across LAMBADA + train-loss sources, CV blows out to 0.58–1.49.** We report this honestly as eval-specific universality, not a universality of the underlying scaling-law family. The v0.4 BROAD_SPREAD verdict was an artefact of mixed 3-real + 3-synthetic provenance.

(b) **Schelling credible-commitment v0.5 — Horn-Mavroidis WTO real-data sanity check returns sign-reversed slope (§6 + `paper/v0.5-draft/sec-6-real-data-update.md`).** Probit fit on n = 23 WTO disputes reaching Article 22.6 retaliation-request stage returns `k = −2.92`, 95 % CI `[−7.92, −0.67]` — *opposite direction* of the Schelling pre-registration. Per-anchor projection: 0/4 within ±0.20 on any anchor. Most parsimonious explanation: observational selection on defendant intransigence (cases that travel all the way to applied retaliation are precisely those where the defendant was least willing to comply). We do not interpret this as refuting Schelling's exogenous-`s` theory, only the *observational identification* from Horn-Mavroidis alone.

(c) **W7-D backtest Sharpe lift = −0.23** still the headline financial result. Same ask as 2026-05-25: is the negative-result framing honest or still oversold?

Three asks (any subset):

(a) §4.6 — does "tight within-eval, broad across-eval" land honestly as a restriction of the universality claim?

(b) `sec-6-real-data-update.md` — is the observational-identification framing the right read of the Horn-Mavroidis sign-reversal, or are we letting Schelling off too easily?

(c) Anything in v0.5's econometrics (probit / threshold-tobit reparametrisation) that you would flag as misapplied?

Repo public, ~30 min on §4.6 + sec-6-real-data-update + W7-D should suffice. No endorsement sought.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
