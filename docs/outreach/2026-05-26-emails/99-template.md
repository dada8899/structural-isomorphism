# Reusable outreach template

For future cold-outreach to senior researchers (Newman, Barabási, Mantegna, Stanley, Sornette's PhD cohort, etc.). Copy this file, rename `NN-<lastname>.md`, and fill the five `<...>` blocks. Keep the email under one screen (200–350 words).

---

**To:** [<Title> <Full Name> — preferred email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** <specific-claim-the-recipient-can-evaluate> + <honest-qualifier> — request for adversarial review

Dear Prof. <Last Name>,

I am writing because <specific section / specific claim> of our cross-domain validation pipeline rests directly on <cite 1–2 specific papers by recipient, with year, not full oeuvre>, and I would value your specifically adversarial reading of that section before we submit.

The project applies one frozen Clauset-Shalizi-Newman pipeline (`v4/lib/soc_pipeline.py`, 339 lines, commit `7ee228c`) unchanged across **27 independent systems** spanning <domains>. <One sentence elevator pitch tying the recipient's specialty to a specific section of the preprint.> Two findings I want to flag honestly rather than bury:

- <Honest negative or inconclusive result #1 relevant to recipient's specialty — e.g. "Vuong inconclusive on 3/9 systems on raw tails"; "W7-D backtest Sharpe lift −0.23"; "A2-Scheffer block-bootstrap $p_{\text{AR1}}=0.074$"; "Phase 7 verification independence flagged LOW">.
- <Honest negative or inconclusive result #2 — e.g. B3 critic ensemble REJECT verdict of 7/21 classes (33%), reduced from B1 single-critic 14%, mostly demoting "mathematical frameworks masquerading as universality classes">.

Three asks, any subset of which would be valuable:

(a) Would you be willing to skim arXiv:[PENDING_ARXIV_ID] §<X> and flag any claim you find misleading or overstated?

(b) <One specialty-specific methodology question — phrased so a "yes / no / it depends on Y" answer is possible in under 5 minutes. Concrete reference to a published method, dataset, or test the recipient is known for.>

(c) Anything we should have <tested / cited / cross-checked> and did not.

We are not seeking endorsement, co-authorship, or signature. The repo is public, code is reproducible end-to-end (Zenodo DOI [PENDING_ZENODO_DOI], three PyPI packages: `structural-isomorphism-core`, `-validation`, `-critic`), and we expect hard review.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
Site: https://structural.bytedance.city
arXiv: [PENDING_ARXIV_ID]
Zenodo: [PENDING_ZENODO_DOI]

---

## Authoring checklist (must be ticked before send)

- [ ] Recipient's email confirmed against their current institutional page (not a 5-year-old PDF footer).
- [ ] Both cited recipient papers actually exist, year is correct, claim is correct. **One wrong citation kills the email.**
- [ ] Specialty-specific question (b) is *answerable* — not "what do you think of our work" but a binary or ternary question with a known answer space.
- [ ] At least one honest negative or inconclusive finding is foregrounded in the body. Senior reviewers reach for emails that don't oversell.
- [ ] No deadline pressure language. No "we plan to submit on <date>". No "by next week".
- [ ] No "would you be a co-author / endorser / signatory" language. **Never.**
- [ ] Body fits under one screen at default reading size (~350 words max, ~250 words preferred).
- [ ] All `[PENDING_*]` placeholders resolved (arXiv ID, Zenodo DOI, send date).
- [ ] Subject line names a *specific claim* the recipient can evaluate, not a generic "feedback request".
- [ ] Routing-table entry added to `00-INDEX.md` and recommended send-order tier assigned.
- [ ] A follow-up policy decision is logged: send once at T+10 if no reply, never again.

## Anti-patterns (do not do)

- ❌ Full-oeuvre flattery ("your seminal work on X has shaped the field..."). Senior researchers smell it instantly. Cite 1–2 specific papers.
- ❌ "We have $N$ exciting results to share!" — show, don't tell, and pick the negative one as the headline.
- ❌ Asking for "general thoughts" or "any feedback". Senior researchers cannot prioritise diffuse asks. Make every ask answerable in under 10 minutes.
- ❌ Cc'ing other recipients. Each email is private; the recipient should see only their name in `To:`.
- ❌ Multiple follow-ups. One ping at T+10 is the limit.
- ❌ Defending in the first reply to substantive critique. Restate, ask one clarifying question, give a real response date.
