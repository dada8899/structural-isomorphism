# Outreach — 2026-05-26 batch (6 senior refresh + 2 new methodology specialists)

Companion to: `paper/v0.5-draft/v05-draft-skeleton.md` (v0.5 SKELETON DRAFT, ~10k words, HEAD `14a73c4`).

This batch refreshes the 2026-05-25 senior outreach (six recipients) for v0.5 increments and adds two new methodology specialists targeted at v0.5's two scientific methodology contributions (§3.6.5 (s\*, k) threshold-tobit reparametrisation; §3.6.6 multilayer test pattern).

**Status declared honestly in every email.** The v0.4 preprint arXiv ID is still **pending** at time of drafting; each email states "preprint forthcoming" where appropriate rather than claiming an arXiv URL we do not yet have.

---

## Routing table

| # | File | Recipient | Angle | Length |
|---|------|-----------|-------|--------|
| 1 | `01-sornette-refresh.md` | Didier Sornette (ETH Zürich, retired) | v0.5 refresh — Pythia LAMBADA cross-fit eval-specific finding + aggregation_kinetics PASS-STRONG; LPPL ask reduced to a confirmation/decline | ~290 w |
| 2 | `02-stumpf-refresh.md` | Michael Stumpf (Melbourne / former Imperial) | v0.5 refresh — multilayer test pattern (§3.6.6) explicitly addresses one of his 2012 traps; aggregation_kinetics treated as test case | ~310 w |
| 3 | `03-porter-refresh.md` | Mason A. Porter (UCLA) | v0.5 refresh — multilayer pattern's network-growth candidate row + Motter-Lai Phase 7 LOW-independence verdict unchanged | ~290 w |
| 4 | `04-clauset-refresh.md` | Aaron Clauset (CU Boulder) | v0.5 refresh — same Clauset 2009 pipeline applied to 8 Pythia × 27 checkpoints (LAMBADA cross-fit); honest negative on v2 R² | ~280 w |
| 5 | `05-sethna-refresh.md` | James P. Sethna (Cornell) | v0.5 refresh — aggregation_kinetics class (Smoluchowski + multiplicative-stochastic Layer 2) is a multilayer cousin to crackling-noise; would value the read | ~300 w |
| 6 | `06-bouchaud-refresh.md` | Jean-Philippe Bouchaud (CFM / X) | v0.5 refresh — Pythia LAMBADA cross-eval BROAD_SPREAD pooled result; "tight within-eval, broad across-eval" framing | ~310 w |
| 7 | `07-econometrics-tobit.md` | NEW: senior econometrics / psychometrics methodologist (probit / threshold-tobit reparametrisation) — `[NAME / AFFILIATION pending]` | §3.6.5 (s\*, k) reparametrisation review ask | ~270 w |
| 8 | `08-multilayer-scaling.md` | NEW: senior physicist on allometric / multi-scale critical phenomena — `[NAME / AFFILIATION pending]` | §3.6.6 multilayer test pattern review ask | ~280 w |

Plus:
- `99-template.md` — reusable shell for future extensions (carried over from 2026-05-25 batch, unchanged).

---

## Recommended send order + cadence

The 2026-05-25 batch staggered across ~4 days. The 2026-05-26 batch follows the same logic with a small twist: the two new specialists are sent in Tier 0 (Day 0), *before* the six v0.5 refreshes, because they have no prior thread and are independent cold asks.

**Tier 0 (Day 0, sent first):**

- `07-econometrics-tobit.md` — cold ask, narrow methodology scope. Independent of all prior threads.
- `08-multilayer-scaling.md` — cold ask, narrow methodology scope. Independent.

**Tier 1 (Day 0 + 24 h):**

- `04-clauset-refresh.md` — same pipeline angle as 2026-05-25; the v0.5 update is a clean continuation, lowest friction follow-up.
- `02-stumpf-refresh.md` — v0.5 directly addresses §3.6.6 multilayer pattern, which maps onto his 2012 "Critical Truths" framing.

**Tier 2 (Day +2):**

- `05-sethna-refresh.md` — aggregation_kinetics is a multilayer cousin to crackling-noise; natural hook.
- `03-porter-refresh.md` — Motter-Lai Phase 7 unchanged + multilayer-pattern network-growth candidate row added.

**Tier 3 (Day +4):**

- `01-sornette-refresh.md` — LPPL ask demoted to confirm/decline since v0.5 still does not include an LPPL fit; Pythia and aggregation_kinetics are the new hooks.
- `06-bouchaud-refresh.md` — Pythia LAMBADA cross-eval BROAD_SPREAD pooled result + W7-D backtest null carried over; most useful adversarial check.

Total elapsed time to last send: **~4 days**, as before.

---

## Follow-up + incorporation rules

**Unchanged from 2026-05-25 batch** — see `docs/outreach/2026-05-25-emails/00-INDEX.md` §§ "Follow-up policy" and "Incorporation rules" for the verbatim policy (T+10 single follow-up, no second ping, decline-handling, substantive-critique 24h ack + ≥ 7-day response window, GitHub `external-review` issue per substantive point).

---

## Hard rules (no exceptions)

Same as 2026-05-25:

- **No mass-bcc, no mail-merge.** Each email is hand-sent from a real address; the recipient should see only their own name in `To:`.
- **No "would you co-author?" — ever.** This batch is review-solicitation, not collaboration-solicitation.
- **No follow-ups beyond one.**
- **No deadline pressure.**
- **All `[PENDING_*]` placeholders must be resolved at T-1 day** by `docs/outreach/2026-05-26-emails/_release_check.sh` (to be written; can be copied verbatim from the 2026-05-25 batch).
- **For the two new specialists**: the `[NAME]` / `[AFFILIATION]` / `[EMAIL]` fields must be filled by the user before send. These are real specialists the user identifies; the drafts deliberately leave them blank to avoid presuming names.

---

## Placeholders used across files

| Placeholder | Resolved by | Source of truth |
|-------------|-------------|-----------------|
| `[PENDING_ARXIV_ID]` | arXiv announcement email | `release/arxiv-submission-receipt.txt` (still pending at draft time) |
| `[PENDING_ARXIV_DATE]` | Same | Same |
| `[PENDING_ZENODO_DOI]` | Zenodo deposit confirmation | `release/zenodo-deposit.json` |
| `[PENDING_REPO_RELEASE_TAG]` | GitHub release | `gh release view --json tagName` |
| `[PENDING_SEND_DATE]` | Day-of sending | manual |
| `[NAME]` / `[AFFILIATION]` / `[EMAIL]` (07 + 08 only) | User identifies the two specialists before send | manual |

---

## Word counts

| File | Words (target ~250–310) |
|------|------|
| `01-sornette-refresh.md` | ~290 |
| `02-stumpf-refresh.md` | ~310 |
| `03-porter-refresh.md` | ~290 |
| `04-clauset-refresh.md` | ~280 |
| `05-sethna-refresh.md` | ~300 |
| `06-bouchaud-refresh.md` | ~310 |
| `07-econometrics-tobit.md` | ~270 |
| `08-multilayer-scaling.md` | ~280 |

All within the 250–310 word target.
