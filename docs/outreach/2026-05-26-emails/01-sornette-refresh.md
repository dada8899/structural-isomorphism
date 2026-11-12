**To:** [Prof. Didier Sornette — preferred personal email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** v0.5 update — Pythia LAMBADA cross-fit eval-specific finding + aggregation_kinetics PASS-STRONG (request for adversarial review)

Dear Prof. Sornette,

I wrote on 2026-05-25 asking for your adversarial read on the stock-market section of our cross-domain SOC validation preprint. The v0.4 arXiv submission is still pending (key rotation + LFS migration on our side); I write now because a v0.5 draft is on the repo at `paper/v0.5-draft/v05-draft-skeleton.md` (HEAD `14a73c4`) that I think changes the asks in a direction worth flagging before the v0.4 lands.

Three v0.5 increments that touch your territory:

(a) **Pythia LAMBADA scaling-law cross-fit (§4).** We applied the same Clauset-style fit family `L(C) = A·C^(−α) + L_inf` (Kaplan / Hoffmann form) across 8 Pythia sizes × 27 standard checkpoints, with v1 (L∞ unconstrained) and v2 (L∞ ∈ [1.0, 5.0] anchored to LAMBADA-OpenAI floor). Both fits deliver TIGHT_UNIVERSALITY (CV ≈ 0.12). Pooled across LAMBADA + train-loss sources, CV blows out to 0.58–1.49. We report this honestly as **eval-specific universality**, not a universality of the underlying scaling-law family. Would you be willing to skim §4.6 and tell us whether the "tight within-eval, broad across-eval" framing is overclaim-free?

(b) **`aggregation_kinetics` PASS-STRONG (§5).** Multilayer test pattern: per-aggregate Smoluchowski PL (Layer 1, three biological domains) + cross-population lognormal (Layer 2, Allen Brain TBI 4/5 series). Two of three Layer 1 anchors are pre-Clauset 2009 (log-log linear on CCDF — the Clauset 2009 §6 critique applies).

(c) **LPPL still not included.** Same v0.4 position. Your 2026-05-25 ask stands: is "no LPPL in a 2026 cross-domain study" the right call or the wrong one?

I would value any of the three reads. Repo public, ~30 min for §4.6 + §5 + §6 should suffice. The arXiv ID will land in the same thread when v0.4 is finally announced.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
