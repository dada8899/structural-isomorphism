# Outreach — 2026-05-25 batch (6 senior reviewers)

Cold-outreach emails requesting cross-validation / adversarial review of:

- **C1 unified preprint** (`paper/v0-unified-pipeline-2026-05-13.md`, v0.3.1, ~10,400 words)
- **C4 reject-aware methodology preprint** (`paper/c4-reject-aware-pipeline-2026-05-13.md`, v0.2)
- **27-system SOC validation pipeline** (`v4/validation/<system>/`, frozen at commit `7ee228c`)
- **4,888-entry cross-domain KB** + **21-candidate universality-class taxonomy** with B1/B3 critic verdicts
- **Honest negative results**: W7-D backtest Sharpe lift **−0.23** (alpha not confirmed), A2-Scheffer block-bootstrap p = 0.074 (inconclusive), B3 reject rate **14% → 33%** (mostly demoting B1-KEEPs)

The asks are deliberately framed as **hard adversarial review**, not endorsement.

---

## Routing table

| # | File | Recipient | Angle | Length |
|---|------|-----------|-------|--------|
| 1 | `01-sornette.md` | Didier Sornette (ETH Zürich, retired) | LPPL + dragon-kings + stock-market inverse-cubic § sanity check | ~290 w |
| 2 | `02-stumpf.md` | Michael Stumpf (Melbourne / former Imperial) | Adversarial test of his 2012 *Critical Truths* taxonomy on our 27-system Clauset pipeline | ~310 w |
| 3 | `03-porter.md` | Mason A. Porter (UCLA) | Motter-Lai network cascade + scale-free percolation REJECT verdict | ~290 w |
| 4 | `04-clauset.md` | Aaron Clauset (CU Boulder) | Notification + misapplication audit of his 2009 SIAM Review pipeline | ~280 w |
| 5 | `05-sethna.md` | James P. Sethna (Cornell) | RFIM Barkhausen + Preisach hysteresis validation review | ~290 w |
| 6 | `06-bouchaud.md` | Jean-Philippe Bouchaud (CFM / X) | Financial-markets cross-domain mapping + honest backtest null result | ~310 w |

Plus:
- `99-template.md` — reusable shell for future extensions (Newman, Barabási, Mantegna, Stanley, Sornette's PhD cohort, etc.).

---

## Recommended send order + cadence

**Tier 1 (send first — methodology core, lowest "weirdness" risk):**

1. **Clauset (#4)** — Day 0. Our entire pipeline directly extends his 2009 SIAM Review code; a courtesy notification + misapplication-audit request is the most legitimate cold ask of the six. His response (or non-response) becomes a calibration anchor for the rest.
2. **Stumpf (#2)** — Day 0 + 4 h (decoupled from #4; different time zone, different specialty).

**Tier 2 (send Day +2, after #1/#2 have had 48 h to land):**

3. **Sethna (#5)** — narrow, specific, two textbook classes (RFIM + Preisach); naturally interesting to him.
4. **Porter (#3)** — networks angle, including a REJECT verdict he is well-placed to argue about.

**Tier 3 (send Day +4, after Tier 2 ack/non-ack):**

5. **Sornette (#1)** — semi-retired but active on arXiv; stock-market chapter section is the natural hook. Send after #4 (Clauset) has acked, so we can cite "we have notified Clauset" as a soft trust signal.
6. **Bouchaud (#6)** — econophysics, honest negative result (−0.23 Sharpe) is the lure. CFM is industry — likely the slowest to reply but the most useful adversarial check.

Total elapsed time to last send: **~4 days**. This staggers responses across two weeks and prevents bulk-reply fatigue if multiple senior researchers reply on the same day.

---

## Follow-up policy

| Trigger | Action |
|---------|--------|
| No reply at **T+10 days** | Single follow-up: 3 sentences, no new attachments, subject line `Re: [original]`. One ping only — never two. |
| No reply at **T+30 days** | Mark `no-response` in `docs/outreach/2026-05-25-emails/_status.csv` (to be created). Do not re-ping. Treat as silent decline. |
| Polite decline / "no time" | Thank, ask if they can suggest a postdoc or recent PhD with relevant overlap. Stop. |
| Substantive critique | Acknowledge within 24 h. Do **not** defend in the first reply — restate their point in our own words, ask one clarifying question, give a concrete commitment date for response (≥ 7 days; resist same-day fixes that look defensive). |
| Endorsement-style reply ("looks great!") | Politely ask for one specific thing they would change. Endorsement without specifics is not actionable; ask for actionable. |

---

## Incorporation rules

When a reviewer reply contains substantive critique:

1. **Log** the email + response under `docs/outreach/2026-05-25-emails/responses/<NN>-<lastname>-<YYYY-MM-DD>.md` (verbatim, redact nothing except personal contact info).
2. **Open an issue** on the GitHub repo per substantive point, labelled `external-review`, `tier:<reviewer-name>`.
3. **Triage within 7 days** into: (a) revise paper, (b) revise pipeline code, (c) add caveat/limitation, (d) acknowledge + defer to future work with explicit justification.
4. **Cite the reviewer** in the next paper revision's acknowledgements **only with explicit consent** — never assume.
5. **No silent retraction** of reviewer points. If we disagree, document the disagreement in `docs/reviews/external/` and respond to the reviewer in writing.

---

## Hard rules (no exceptions)

- **No mass-bcc, no mail-merge.** Each email is hand-sent from a real address; the recipient should see only their own name in `To:`.
- **No "would you co-author?" — ever.** This batch is review-solicitation, not collaboration-solicitation. Do not blur the line.
- **No follow-ups beyond one.** Senior researchers are time-poor. A second ping converts a 50/50 reply into a near-certain non-reply.
- **No deadline pressure.** The arXiv submission date stays on our internal calendar; never communicate it as a clock the reviewer must beat.
- **All `[PENDING_*]` placeholders must be resolved at T-1 day** by `docs/outreach/2026-05-25-emails/_release_check.sh` (to be written): arXiv ID, Zenodo DOI version, date stamps.

---

## Placeholders used across files

| Placeholder | Resolved by | Source of truth |
|-------------|-------------|-----------------|
| `[PENDING_ARXIV_ID]` | arXiv announcement email | `release/arxiv-submission-receipt.txt` |
| `[PENDING_ARXIV_DATE]` | Same | Same |
| `[PENDING_ZENODO_DOI]` | Zenodo deposit confirmation | `release/zenodo-deposit.json` |
| `[PENDING_REPO_RELEASE_TAG]` | GitHub release | `gh release view --json tagName` |
| `[PENDING_SEND_DATE]` | Day-of sending | manual |

---

## Word counts

| File | Words | Notes |
|------|-------|-------|
| `01-sornette.md` | ~290 | LPPL specific, dragon-king honest qualifier |
| `02-stumpf.md` | ~310 | 4 traps from his 2012 Science paper directly addressed |
| `03-porter.md` | ~290 | Motter-Lai + REJECT verdict highlighted as ask, not hidden |
| `04-clauset.md` | ~280 | Shortest; pure methodology notification |
| `05-sethna.md` | ~290 | Two textbook classes; honest Preisach demotion ask |
| `06-bouchaud.md` | ~310 | Honest −0.23 Sharpe foregrounded |
| `99-template.md` | — | Reusable shell |

All within the 200–350 word target; each fits under one screen at default reading size.
