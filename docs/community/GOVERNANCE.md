# Governance

> **Version**: v2 (2026-05-15) — supersedes v1 (BDFL-only, 2026-Q1)
> **Scope**: project decision-making, leadership, conflict resolution, succession, license + trademark policy
> **Author of record**: @dada8899 (BDFL); changes require process described in § Amendments

This document is normative. Where it conflicts with informal practice, this document wins.

## 1. Current state

structural-isomorphism is currently led by a single **Benevolent Dictator For Life** (BDFL): @dada8899. The BDFL has 100% commit authority and final say on all decisions. This is appropriate for a sub-50-contributor, pre-v1.0 project; it is **not** intended to be the long-term governance model.

This file documents both how we are governed today **and** the explicit, time-bound path to a 3-member Maintainer Council.

## 2. Decision-making (today, under BDFL)

| Category | Procedure | Quorum |
|---|---|---|
| Code changes (bug fix, feature, docs) | PR + 1 maintainer review | 1 reviewer (BDFL or delegate) |
| Architecture changes | ADR in `docs/adrs/` + PR review | BDFL ratification |
| Release (`packages/*`) | SemVer; PR to `release/*` branch | BDFL sign-off |
| Dataset additions (`data/`, `v4/validation/`) | PR + content-addressed manifest update | BDFL sign-off |
| Research disputes | Issue with `research` label; literature-cited discussion | BDFL resolution after public discussion ≥ 7 days |
| License changes | Forbidden unilaterally (see § 9) | N/A under BDFL alone |
| CoC enforcement | Per CODE_OF_CONDUCT.md ladder | BDFL (with documented rationale) |

## 3. Transition trigger — when BDFL → Council

Council formation is triggered by **whichever of these comes first**:

1. **External contribution threshold**: externally-merged contributions (from authors not employed by or coordinating with @dada8899) reach **≥ 5 PRs in any single quarter**.
2. **Scientific landmark**: first **arXiv preprint acceptance** of a structural-isomorphism-attributed paper lands publicly.
3. **Calendar hard stop**: **2027-01-01**, regardless of the above.

The first of these to fire opens a 90-day council-formation window per § 5.

## 4. Council composition & authority

Once triggered, the project is governed by a **3-member Maintainer Council**:

- **1 seat**: BDFL (perpetual until self-stepdown; see § 7)
- **2 seats**: external maintainers selected via the process in § 5

Council holds collective authority over:

- Merges to `main` (any council member can merge after PR review by another council member)
- Releases and version-tag policy
- Dataset acceptance + retraction
- Roadmap ratification
- Budget allocation (post-NumFOCUS or other fiscal sponsor)
- CoC enforcement (per § 8)
- Council expansion or contraction (subject to § 11 amendment vote)

The BDFL retains:

- A single vote in council decisions (no veto, except per § 5.4 conflict-of-interest)
- Ownership of the project name (which is **not trademarked**; see § 10)
- Tie-breaker authority on a 2-2 split if council expands to 4 (rare; rebalance via § 11)

## 5. First-council nomination process

When the trigger in § 3 fires, the BDFL announces the council-formation window publicly within 14 days. The 90-day window proceeds as:

### 5.1 Open call for nominations (days 0 - 30)

- Public announcement in: GitHub Discussions, Discord, monthly newsletter, the repo README.
- Anyone may **self-nominate or nominate another person**. Nomination form: brief (≤ 500 words) describing technical or scientific contributions to structural-isomorphism + commitment to a 12-month term.
- All nominations published in `docs/community/council-2027/nominations/`.

### 5.2 Public comment period (days 30 - 44)

- 14-day comment period. Anyone may comment publicly on any nomination via GitHub issues with `council-nomination` label.
- BDFL responds to every nomination within the comment window (acknowledge + ask clarifying questions if needed).
- Bad-faith comments (per CoC) removed; commenter warned per CoC ladder.

### 5.3 BDFL ratification (days 44 - 60)

- BDFL selects 2 council members from nominees.
- Selection criteria (published in advance):
  1. Demonstrable technical or scientific contribution (≥ 3 merged PRs OR documented dataset contribution OR co-authored paper using the pipeline)
  2. Diversity of geography, institution, and seniority (no two council members from the same lab/employer)
  3. Stated commitment to a 12-month term + ~ 4 hours/week of project work
- BDFL publishes the selection rationale in `docs/community/council-2027/selection-rationale.md`.

### 5.4 BDFL veto (limited)

The BDFL may **only** veto a nominee under documented conflict-of-interest (e.g. nominee's employer holds adversarial IP claims against the project, or nominee is currently subject to an unresolved CoC complaint). All other "preferences" must be exercised through ratification choice, not veto.

### 5.5 Public acceptance & oath (days 60 - 90)

- Selected council members publicly accept via PR adding themselves to `MAINTAINERS.md`.
- Brief written statement of commitment included in the PR.
- Council is officially seated on the merge date.

### 5.6 Subsequent rotations

After the first council is seated, **the council itself** (not the BDFL alone) runs nomination + ratification for replacement seats. The BDFL retains a single vote and the same veto power (conflict-of-interest only). The process otherwise mirrors § 5.1 - 5.5.

## 6. Council voting

| Decision class | Threshold | Notes |
|---|---|---|
| Technical (merges, releases, ADRs, dataset acceptance) | Simple majority (2 of 3) | Default. Most decisions live here. |
| Governance changes (this document) | 2/3 supermajority (2 of 3) | Plus 30-day public comment window |
| License changes (MIT / CC-BY-4.0) | 2/3 supermajority + 60-day public comment + BDFL co-sign | License changes are deliberately the hardest |
| CoC enforcement against non-council member | Simple majority | Per CODE_OF_CONDUCT.md ladder |
| CoC enforcement against **fellow council member** | **100% consensus** (unanimous) | Excludes the accused from the vote; remaining members must agree unanimously |
| Council seat replacement (mid-term) | 2/3 supermajority | Per § 5.6 |
| Expansion of council size (> 3 seats) | 2/3 + amendment process per § 11 | |
| Emergency action (security, legal) | Any single council member can act unilaterally if all others are unreachable for > 48 hours; must report within 7 days | See § 8.2 |

Abstentions count as "no" for supermajority thresholds.

## 7. Term length & rotation

- **External council seats**: 12 months, renewable indefinitely with re-nomination. Renewal is via § 5 process — no automatic re-up.
- **BDFL seat**: perpetual until **voluntary stepdown** (see below) or **incapacity** (see § 8.3).
- **Staggered terms**: of the two external seats, one is initially seated to a 12-month term and the other to an 18-month term. This prevents simultaneous turnover and preserves institutional memory.
- **Voluntary BDFL stepdown**: BDFL announces ≥ 60 days in advance; council elects new BDFL via 2/3 vote among themselves + 1 nominee from open call. New BDFL inherits the BDFL seat but **not** automatic perpetual tenure (a stepped-down founder is rare; the next BDFL's term is initially 24 months, renewable by council 2/3 vote).

## 8. Emergency procedures

### 8.1 Security vulnerabilities

Reported per `.github/SECURITY.md`. Triage SLA: 14 days for acknowledgement; 90 days for fix (or coordinated disclosure if longer needed). Any council member can issue an emergency patch release without full quorum if at least one other council member is reachable for sign-off. The remaining member is informed within 24 hours.

### 8.2 Legal / DMCA / takedown notices

Council member receiving the notice forwards to all council members + BDFL within 24 hours. Council deliberates within 7 days. If urgent action required (court order, etc.), § 6 emergency-action clause applies.

### 8.3 Abrupt BDFL absence

- **≥ 30 days no response** (email, GitHub, Discord all unreachable):
  - Remaining council can **co-opt a third member** for quorum purposes from the most recent nomination list, or from a fast-track nomination (7-day window if no existing nominations).
  - Co-opted member serves until BDFL returns or until § 8.3 (≥ 90 days) triggers.
- **≥ 90 days no response**:
  - Council can elect an **interim BDFL** via 2/3 vote.
  - Interim BDFL's term is 12 months, renewable once by council, after which standard § 5 procedure applies.
  - Original BDFL retains rights to the GitHub org if/when they return; but interim BDFL handles day-to-day decisions.
- **Confirmed permanent absence** (death, incapacity, formal stepdown):
  - Council elects permanent BDFL per the procedure above.
  - GitHub org ownership and any secrets (per `docs/SECRETS_BREAK_GLASS.md`) transfer per documented escrow.

### 8.4 Council disbandment / quorum loss

If 2 of 3 council seats simultaneously vacate (resignation, removal, or incapacity), the remaining member + BDFL (if separate) can:

1. Run an emergency § 5 process with a compressed timeline (45 days instead of 90).
2. Request NumFOCUS (or fiscal sponsor) mediation to ensure continuity.
3. As a last resort, **escrow the project** to NumFOCUS or to a successor open-source community (e.g. astropy, scikit-learn) per § 12 handoff procedure.

## 9. License & trademark policy

### 9.1 License lock

- Source code: **MIT License**, locked.
- Datasets: **CC-BY-4.0**, locked.
- Documentation: **CC-BY-4.0**, locked.

Changing any of these requires the full § 6 license-change procedure: 2/3 council supermajority + 60-day public comment + BDFL co-sign. We are deliberately making this the hardest decision in the project; "going closed-source" is essentially infeasible by design.

### 9.2 Trademark

The project does **not** hold and does **not** intend to seek a trademark on the name "structural-isomorphism". The name and logos (when designed) are CC-BY-4.0. Anyone may fork and use the name, **subject to one rule**: forks must not misrepresent NumFOCUS sponsorship status, fiscal sponsorship, or council endorsement.

### 9.3 Contributor sign-off

We use the [Developer Certificate of Origin](https://developercertificate.org/) (DCO) via signed Git commits. We do **not** require a CLA. Contributors retain copyright on their contributions and grant the project a perpetual MIT/CC-BY-4.0 license via the DCO.

## 10. Conflict of interest

Council members must disclose to the rest of the council:

- Paid employment at any organization that consumes, funds, or competes with structural-isomorphism
- Grant funding (named PI or co-PI) that touches the project's research scope
- Equity in any organization that consumes or competes with the project
- Personal relationships (family, romantic) with other council members or PR authors whose work they review

Disclosures live in `docs/community/coi/<member>.md`. Updates required within 30 days of any material change. A council member with a COI on a specific decision **recuses** from that decision; the recusal is logged.

## 11. Amendments

This GOVERNANCE.md can be amended via:

1. PR proposing the change (any project member can open)
2. 30-day public-comment period
3. 2/3 council supermajority vote
4. BDFL co-sign

License-related amendments additionally require the § 9 60-day comment window.

Amendments take effect on merge. Each amendment includes a `## Changelog` entry (added at bottom of this file) summarizing what changed and why.

## 12. Project handoff / dissolution

If the council dissolves, the project merges with another OSS project (e.g. NumFOCUS adopts us into a larger umbrella), or all council members and the BDFL collectively decide to wind down, the following handoff requirements apply:

- **Data handoff**: All datasets are mirrored to:
  - Zenodo (DOIs already minted; permanent)
  - At least one additional academic data host (Harvard Dataverse, Figshare, or institutional repository)
  - The full provenance manifest is published with each mirror.
- **Code handoff**: The repository is mirrored to:
  - Software Heritage (passive archival; usually already automatic)
  - GitLab as a backup mirror
  - If specific organizational successor is chosen, the GitHub org transfers ownership cleanly with all history intact.
- **Secrets handoff**: per `docs/SECRETS_BREAK_GLASS.md`, age-encrypted and held by ≥ 2 council members. On dissolution, secrets are either rotated and re-escrowed with successor, or destroyed.
- **Announcement**: A public dissolution notice in the repo README, the docs site, and the newsletter, with at least 90 days' notice to dependent users.
- **Final tag**: A `final-` prefixed git tag marking the last commit under current governance.

No member of the council or BDFL has the right to take the project private, sell the trademark (we have none), or close-source the codebase on dissolution. The project either continues under new governance or archives publicly.

## 13. Current maintainers

- @dada8899 (founder, BDFL) — sole maintainer as of 2026-05-15

## 14. Contact

For governance questions: GitHub Discussions "Meta" category, or email the BDFL.
For CoC reports: per `CODE_OF_CONDUCT.md`.
For security: per `.github/SECURITY.md`.

---

## Changelog

### v2 (2026-05-15) — this version
- Added explicit transition trigger (whichever-comes-first: 5 PRs/quarter, first arXiv acceptance, or 2027-01-01)
- Added 3-member council composition (BDFL + 2 external)
- Added detailed first-council nomination process (90-day window, 5 sub-phases)
- Added voting thresholds (simple majority / 2/3 / 100% consensus for in-council CoC)
- Added 12-month term length, staggered, renewable
- Added emergency procedures (≥30-day absence, ≥90-day absence, quorum loss)
- Added trademark policy (none; freely usable)
- Added project handoff requirements (Zenodo mirror, Software Heritage, secrets escrow)
- Added formal amendment process
- Added COI disclosure framework

### v1 (2026-Q1) — superseded
- BDFL-only governance with future-council placeholder
- Vague trigger ("≥10 external contributors + ≥12 months project age")
- No detailed transition procedure
- No emergency procedures
- No trademark policy
- No handoff requirements
