# Launch materials — INDEX

**Date**: 2026-05-24 (drafted; not yet sent).
**Companion**: `docs/community/launch/INDEX.md` — the pre-arXiv community draft set (2026-05-15).
**Status**: ALL drafts. Nothing has been launched. Pre-launch gate is in
`docs/community/launch/hn-launch-readiness-2026-05-24.md` § 5.

---

## File map

### Task 1 — HN blocker unlocks

| File | Purpose |
|---|---|
| [`demo-gif-script-2026-05-24.md`](demo-gif-script-2026-05-24.md) | Storyboard + Playwright/QuickTime recording script + ffmpeg post-processing pipeline for the 15s `site/demo.gif` |
| [`load-test-plan-2026-05-24.md`](load-test-plan-2026-05-24.md) | 4-stage load test procedure with SLOs, scaling triggers, and capacity headroom analysis |
| [`hn-title-candidates-2026-05-24.md`](hn-title-candidates-2026-05-24.md) | 5 title candidates with backtest-conditional decision matrix |
| [`hn-faq-expanded-2026-05-24.md`](hn-faq-expanded-2026-05-24.md) | Q1–Q20 prepared answers + tone guard-rails + keyword index |
| `../../tools/load-test/locustfile.py` | Locust script — 50/100/200 RPS test users (AnonymousVisitor + CuriousReader + PhaseDetectorUser) |
| `../../tools/load-test/k6-spike.js` | k6 script — same SLOs, better for burst testing |

### Task 2 — arXiv launch posts

| File | Purpose |
|---|---|
| [`blog-post-arxiv-2026-05-24.md`](blog-post-arxiv-2026-05-24.md) | English long-form blog post (~1050 words). 5-phase narrative, reproduction snippet, links. |
| [`blog-post-arxiv-2026-05-24-zh.md`](blog-post-arxiv-2026-05-24-zh.md) | Chinese 公众号 version (~1300 字), 公众号-editor-ready. |
| [`twitter-thread-arxiv-2026-05-24.md`](twitter-thread-arxiv-2026-05-24.md) | 10-tweet thread (+ 2 bonus tweets), media asset specs, engagement strategy |
| [`linkedin-post-arxiv-2026-05-24.md`](linkedin-post-arxiv-2026-05-24.md) | Long-form LinkedIn post (~500 words), B2B / recruiter voice, image-attachment strategy |
| [`reddit-arxiv-2026-05-24.md`](reddit-arxiv-2026-05-24.md) | 3 subreddit posts (r/Physics, r/MachineLearning, r/datascience) with cadence + engagement strategy |

### Task 3 — PyPI launch

| File | Purpose |
|---|---|
| [`pypi-launch-post-2026-05-24.md`](pypi-launch-post-2026-05-24.md) | Long-form package launch post: one-liner install + 30-sec demo + 3-package overview + reproduction recipe |
| [`pypi-twitter-thread-2026-05-24.md`](pypi-twitter-thread-2026-05-24.md) | Short (5-tweet) Twitter thread paired with the long-form. Code-screencast asset spec. |

### Task 4 — Launch day playbook

| File | Purpose |
|---|---|
| [`launch-day-playbook-2026-05-24.md`](launch-day-playbook-2026-05-24.md) | T-1d / T-1h / T+0 / T+24h / T+48h playbook + contingencies + recommended launch dates |

---

## How the launches sequence (canonical order)

1. **PyPI**: already live 2026-05-24. Post (Task 3) is the "we now have packages, here's how to install" announcement. Low stakes, used as warmup.
2. **arXiv**: requires the preprint to land + a real arXiv ID. Trigger all Task 2 posts within 25 minutes of confirming the ID.
3. **HN**: 10 min after the Twitter arXiv thread. The HN post is the high-stakes drop — uses the existing `hn-launch-2026-05-15.md` body with title chosen from `hn-title-candidates-2026-05-24.md`.
4. **LinkedIn + WeChat**: 15 min + 20 min after HN.
5. **Reddit**: T+1 day after HN (Wednesday + Thursday US mornings).
6. **Senior outreach**: T+3 to T+14 (already drafted in `docs/community/launch/senior-outreach-2026-05-15.md`).

Full minute-by-minute sequence in `launch-day-playbook-2026-05-24.md` § T+0.

---

## Pre-send placeholders to replace

Every doc in this directory contains literal `ARXIV_ID_PENDING` placeholders.
The T-1d step in the playbook is:

```bash
cd ~/Projects/structural-isomorphism
grep -rln 'ARXIV_ID_PENDING' docs/launch/ README.md README-zh.md
# Replace each occurrence with the real arXiv ID (e.g. 2605.12345)
```

Other placeholders:

- `pending — link will be added here on launch day` (HN thread link in blog post + LinkedIn): replace with actual HN URL once submitted.
- `dada8899` (account/repo handle): already correct; do not re-replace.
- Date strings `YYYY-MM-DD` in the retro template + the post-launch checklist: fill in actual date.

---

## Recommended launch date

**Primary**: Tuesday **2026-06-02**, 09:00 ET — see playbook § "Recommended launch dates" for full rationale.

**Backup**: Wednesday 2026-06-03 (Tue weather/health-blocked) or Tuesday 2026-06-23 (if backtest v0.2 isn't ready by 2026-05-31).

---

## Pre-launch checklist (consolidated)

Before any send, confirm:

- [ ] arXiv submission has landed; replace every `ARXIV_ID_PENDING` placeholder
- [ ] Zenodo DOI link is live (https://doi.org/10.5281/zenodo.19615170) — verified from non-author IP
- [ ] beta.structural.bytedance.city + phase.bytedance.city — 200 OK
- [ ] PyPI packages installable from clean venv (3 packages)
- [ ] CITATION.cff renders correctly via GitHub's "Cite this repository" button
- [ ] Repo README badges all load (not 404)
- [ ] Demo GIF (`site/demo.gif`) embedded above the fold in README
- [ ] Load test Stage 1 + 2 passed within last 24h
- [ ] HN account has sufficient karma
- [ ] Twitter / Mastodon accounts are warmed up (≥ 50 followers, ≥ 30-day age)
- [ ] HN title decision made
- [ ] FAQ doc open in browser tab
- [ ] Trusted observer scheduled for T+0 to T+6h
