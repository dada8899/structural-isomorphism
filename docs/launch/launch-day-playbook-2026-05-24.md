# Launch day playbook — 2026-05-24

**Purpose**: single source of truth for what happens on launch day, in what
order, by whom, with what fallback. Supersedes the embedded day-of section in
`docs/community/launch/hn-launch-readiness-2026-05-24.md` § 4 (which still
holds for HN-specific items).

**Scope**: PyPI launch + arXiv launch + HN launch + Reddit + LinkedIn + 公众号 (WeChat).
**Audience**: founder + 1 trusted observer (the "second pair of eyes" — answers
fly-by questions in #ops while founder focuses on HN comments).

**Constraint**: do not launch on US public holidays, Chinese national holidays,
NeurIPS / ICLR submission deadline weeks, or major macroeconomic event days.
See § 10 for the launch-window calendar.

---

## T -1 day (Monday)

### Morning (PT 09:00–12:00)

- [ ] **Run full load-test sequence** (see `load-test-plan-2026-05-24.md` § Test sequence)
  - Stage 1: 50 RPS × 10 min — MUST pass
  - Stage 2: 100 RPS × 5 min — MUST pass
  - Stage 3: 200 RPS × 60 s spike — informational
  - Stage 4: phase detector cross-product — informational
- [ ] **Drop verdict line into HN readiness doc** if Stage 1 + 2 pass.
- [ ] **arXiv submission status**: confirm preprint has appeared and arXiv ID is final
  - If still in moderation queue → **DELAY LAUNCH BY 24 H**. No real arXiv ID = no launch.
- [ ] **Replace `ARXIV_ID_PENDING` everywhere**:
  ```bash
  cd ~/Projects/structural-isomorphism
  grep -rln 'ARXIV_ID_PENDING' docs/launch/ README.md README-zh.md
  # Manually replace each occurrence with the real arXiv ID (e.g. 2605.12345)
  ```
- [ ] **Verify PyPI install from clean venv**:
  ```bash
  python3 -m venv /tmp/pypi-launch-test
  source /tmp/pypi-launch-test/bin/activate
  pip install structural-soc-pipeline structural-critics structural-taxonomy
  python -c "from structural_soc.pipeline import fit_powerlaw; print(fit_powerlaw.__doc__[:200])"
  deactivate
  rm -rf /tmp/pypi-launch-test
  ```
- [ ] **Demo GIF generated and embedded** (see `demo-gif-script-2026-05-24.md`)
  - `site/demo.gif` ≤ 5 MB ✓
  - `site/demo.mp4` ≤ 2 MB ✓
  - README.md hero image ✓
  - 6 burned-in captions readable ✓
- [ ] **Friend-test the HN title** (see `hn-title-candidates-2026-05-24.md`)
  - Share 5 candidates with 3-5 trusted reviewers
  - Decide title based on backtest outcome + friend votes
  - Default to Candidate 4 ("17 / 13 / 4") if no Strong backtest

### Afternoon (PT 13:00–17:00)

- [ ] **Final dogfood pass** on prod
  ```bash
  bash scripts/smoke_test_urls.sh
  python scripts/dogfood_fingerprint.py --host beta.structural.bytedance.city
  python scripts/dogfood-ask-prod.py
  ```
- [ ] **Drain non-essential cron** on VPS
  ```bash
  ssh vps "sudo systemctl stop com.wanqh.sync-claude-vps.service \
           weekly-newsletter.timer plausible-rollup.timer"
  ssh vps "atq | grep -v at"   # confirm queue empty
  ```
- [ ] **Pre-cache HN headline image / OG card**
  ```bash
  curl -s https://beta.structural.bytedance.city/og.png > /dev/null
  curl -s https://github.com/dada8899/structural-isomorphism > /dev/null
  ```
- [ ] **Open all draft posts in tabs** + pin a sticky note with launch order
  ```
  Tab 1: PyPI Twitter thread (pypi-twitter-thread-2026-05-24.md)
  Tab 2: arXiv Twitter thread (twitter-thread-arxiv-2026-05-24.md)
  Tab 3: HN submit page
  Tab 4: HN body comment (hn-launch-2026-05-15.md)
  Tab 5: Reddit /r/Physics post (reddit-arxiv-2026-05-24.md)
  Tab 6: Reddit /r/MachineLearning post
  Tab 7: LinkedIn post (linkedin-post-arxiv-2026-05-24.md)
  Tab 8: WeChat editor (blog-post-arxiv-2026-05-24-zh.md)
  Tab 9: FAQ doc (hn-faq-expanded-2026-05-24.md)
  Tab 10: Monitor dashboard (monitor.bytedance.city)
  Tab 11: Plausible (plausible.io/beta.structural.bytedance.city)
  ```
- [ ] **Notify hoster of expected spike** — Tencent Cloud Singapore: email or ticket logged.
- [ ] **Notify trusted observer** — schedule them for T+0 to T+6h availability.
- [ ] **Set Slack + iPhone push alerts** for monitor.bytedance.city 5xx + p95.

### Evening (PT 18:00–22:00)

- [ ] **Personal logistics**: 8 hours sleep, alarms set, ssh-agent loaded, coffee.
- [ ] **No code changes after 18:00 PT**. Freeze. Any "let me quickly fix X" = delay.

---

## T -1h (Tuesday morning, 07:00 PT)

```bash
# Health checks
curl -I https://beta.structural.bytedance.city                                  # 200 expected
curl -I https://phase.bytedance.city                                            # 200 expected
curl -I https://github.com/dada8899/structural-isomorphism                      # 200 expected
curl -I https://pypi.org/project/structural-soc-pipeline/                       # 200 expected
curl -I https://doi.org/10.5281/zenodo.19615170                                 # 302 → Zenodo URL
curl -I https://arxiv.org/abs/$ARXIV_ID                                         # 200 expected

# Plausible event firing test (visit the site, see Plausible light up)
open https://beta.structural.bytedance.city/?utm_source=preflight
# Wait 30s, refresh https://plausible.io/beta.structural.bytedance.city
# Verify 1 page-view registered with utm_source=preflight

# Backend tail (4th terminal pane)
ssh vps "journalctl -u structural-backend -f -o cat"

# Latency baseline (5th pane)
ssh vps "watch -n 5 'curl -w \"ttfb=%{time_starttransfer}s status=%{http_code}\\n\" \
  -s -o /dev/null https://beta.structural.bytedance.city/'"

# Verify deploy is current commit
ssh vps "cd /root/Projects/structural-isomorphism && git rev-parse HEAD"
# Compare to local: git rev-parse origin/main

# Verify /api/waitlist write path (the only mutating endpoint readers will hit)
curl -X POST https://beta.structural.bytedance.city/api/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email":"preflight-'"$(date +%s)"'@test.invalid","src":"preflight"}' \
  -i
# Expect 200; then verify row in DB

# Final OG card check (different browser, different IP)
# Use a tool like opengraph.xyz or socialsharepreview.com — paste both URLs
# Visual sanity: title + description + image render correctly
```

If ANY of the above fails → **abort T+0 launch**, fix, re-attempt T-1h
checks one hour later. Do not soldier through.

---

## T +0 — launch triggers, in strict order

**Time budget**: ~20 minutes total. Pre-time stagger built in.

### T +0:00 — PyPI launch post (low-stakes warmup)

- [ ] **Twitter PyPI thread** (5 tweets, see `pypi-twitter-thread-2026-05-24.md`)
  - Post all 5 tweets back-to-back, no time gap
  - Pin tweet 1
- [ ] **Blog post on personal site** (link the PyPI long-form: `pypi-launch-post-2026-05-24.md`)
- [ ] **Wait 5 minutes** — observe initial engagement; debug feed-render issues here, not on the higher-stakes drops.

### T +0:05 — arXiv launch post

- [ ] **Twitter arXiv thread** (10 tweets, see `twitter-thread-arxiv-2026-05-24.md`)
  - Attach `site/demo.mp4` to tweet 1
  - Attach band-overlap plot to tweet 4
  - Pin the new thread (replacing the PyPI one)
- [ ] **Cross-link**: quote-tweet the PyPI thread from the arXiv thread tweet 5 ("companion thread for `pip install` users").

### T +0:10 — HN submit (THE high-stakes drop)

- [ ] Go to https://news.ycombinator.com/submit
- [ ] **Title**: paste from `hn-title-candidates-2026-05-24.md` (decision matrix)
- [ ] **URL**: https://github.com/dada8899/structural-isomorphism
- [ ] **Submit**
- [ ] **Within 60s**: post the body as the first comment on your own post.
  Body text from `hn-launch-2026-05-15.md`.
- [ ] **Watch first 5 minutes**: is it climbing?
  - Rank 1–10 within 10 min → strong start
  - Rank 11–25 within 10 min → typical; let it ride
  - Rank > 25 by 30 min → stalled; let it ride, do NOT delete + repost same-day

### T +0:15 — LinkedIn post

- [ ] Paste body from `linkedin-post-arxiv-2026-05-24.md`
- [ ] Attach contact-sheet image (`site/demo-contact-sheet.png`)
- [ ] Post (not as company page — as founder personal)

### T +0:20 — 公众号 (WeChat) post

- [ ] Open 公众号 editor; paste body from `blog-post-arxiv-2026-05-24-zh.md`
- [ ] Cover image: 4th frame of demo GIF
- [ ] Schedule for 19:00 CST (China evening commute) — NOT immediate, to align with CN audience window
- [ ] **NOT immediate** because the HN/Twitter drops in the morning of US Tuesday are
  evening of Tuesday CST, but CN engagement peaks at 19:00–22:00 CST.

### T +0:25 — Mastodon

- [ ] Post `mastodon-2026-05-15.md` to fediscience.org
- [ ] Update arXiv ID inline

### T +1 day — Reddit drops (Wednesday)

(Reddit waits 1 day per existing `INDEX.md` schedule — let HN settle first.)

- [ ] /r/Physics — Wed 10:00 ET
- [ ] /r/MachineLearning — Wed 13:00 ET (3-hour stagger)
- [ ] /r/datascience — Thu 10:00 ET

---

## T +1h .. T +6h — peak window

### Founder priorities (in order)

1. **Respond to every top-level HN comment within 15 minutes.**
2. **Watch monitor dashboard**: latency p95, error rate, RPS.
3. **Pin best questions**: at 1h and 3h marks, pin a top-level comment summarizing top questions + answers (helps late readers).
4. **Twitter quote-reply**: respond to substantive quote-tweets within 30 minutes.
5. **DO NOT delete or edit comments**. HN flags edits visibly.

### Trusted observer priorities

- Watch #ops Slack for VPS alerts
- Watch Plausible real-time tab — flag if RPS > 50 sustained or 5xx > 1%
- Drop "you should respond to this one" pings via DM (don't read HN comments to founder — let founder triage)

### Real-time scaling triggers

| Symptom | Action |
|---|---|
| RPS > 100 sustained for 5 min | Run `ssh vps "systemctl reload structural-backend"` after bumping `WEB_CONCURRENCY=12` |
| RPS > 200 sustained | Provision temp VPS upgrade via tccli (16 → 32 cores) |
| Postgres pool exhausted | `pg_stat_activity` check; bump pool_size to 40 |
| p95 > 3 s for 60 s | Throttle non-essential routes (`/api/discoveries` heavier) — turn on rate limit middleware |
| 5xx > 1% sustained | Stop everything; investigate; may rollback to last known-good commit |

---

## T +6h .. T +24h — sustained

- [ ] Continue answering HN comments (slower cadence OK after 6h)
- [ ] At T +12h: post a comment under your own HN post summarizing top 3 questions + answers
- [ ] At T +18h: check Plausible weekly stats projection
- [ ] Sleep at T +12h to T +18h (founder)

---

## T +24h .. T +48h — monitoring window

### Metrics to pull at T +24h

| Channel | Metric | Healthy range | Concerning |
|---|---|---|---|
| HN | Final rank + score | rank 1–5 sustained, score 200+ | rank 25+ within 6h |
| HN | Comment count | 50+ substantive | < 20 substantive |
| GitHub | Stars added | 100+ | < 30 |
| PyPI | Daily downloads (per package) | 200+ for soc-pipeline | < 50 |
| Twitter | Tweet 1 impressions | 25k+ | < 5k |
| Twitter | New followers | 50+ | < 10 |
| LinkedIn | Impressions | 5k+ | < 1k |
| Reddit | /r/Physics upvote ratio | > 0.85 | < 0.70 |
| Site | Unique visitors (Plausible) | 5k+ | < 1k |
| Site | Waitlist signups | 200+ | < 50 |
| arXiv | Abstract views (24h) | 500+ | < 100 |

### Decision rules

- Waitlist > 500 → launch was a hit; trigger follow-up newsletter immediately.
- Waitlist 200–500 → healthy; standard follow-up cadence.
- Waitlist < 200 → diagnose: was it title, was it timing, was it content?
- HN < 25 upvotes → write retro with hypothesis on why; do NOT re-submit same content.

### Follow-up actions

- [ ] Send W7-D weekly-signals newsletter with "from HN" subject tag (the
      pipeline is in `scripts/generate-newsletter.py`)
- [ ] Schedule the "Thank you HN, top concerns surfaced" follow-up post for
      T +48h (NOT a "Show HN" — a regular post on personal blog or
      /r/algotrading)
- [ ] Write retrospective: `docs/community/launch/hn-launch-retro-YYYY-MM-DD.md`
  - Traffic curve (Plausible export)
  - Top 10 objections actually surfaced (not the ones we prepared for)
  - Waitlist conversion rate
  - Lessons learned for next launch

---

## Contingencies

### Service down

| Severity | Symptom | Action |
|---|---|---|
| P0 | Both sites 5xx | (a) Acknowledge in HN top comment within 5 min: "site under load, working on it"; (b) restart backend; (c) if not back in 10 min, rollback to last known-good deploy; (d) if not back in 20 min, hard-delete HN post + post retraction |
| P1 | One site 5xx | Restart that backend; do not touch HN messaging unless it persists > 10 min |
| P2 | One endpoint 5xx (e.g. /api/search slow) | Throttle that endpoint; turn on 429 with friendly message; mention in next-comment if asked |
| P3 | CDN flake | Cycle CDN; usually < 5 min self-recovery |

### HN explosion (rank 1, sustained traffic > 200 RPS)

- [ ] Engage trusted observer to triage comments — founder cannot keep up alone
- [ ] Pre-warmed `tccli` script ready to upgrade VPS specs in-place (have it open in a tab)
- [ ] Post a sticky comment: "hey HN folks — we are at front page top 5 (thank you!) — please give the site 3–5 seconds on load, it's getting a workout"
  - This kind of meta-acknowledgment actually helps; HN audience is forgiving when you are honest about it.

### Hostile / factually-wrong top comment

- [ ] **First**: read the comment three times. Many "wrong" comments are actually a misunderstanding that's our fault for not having explained clearly.
- [ ] **If factually wrong but in good faith**: reply within 15 min with a polite correction + the specific paper / file / line number. Do not engage emotionally.
- [ ] **If factually wrong AND inflammatory**: reply once, substantively, then disengage. HN audience usually downvotes inflammatory commenters; let the community handle it.
- [ ] **If the comment exposes a real factual error we cannot refute**: thank them, acknowledge the error, file an issue against the repo, link the issue from the reply. This is a worse comment than a wrong one, but the response is also clearer.

### Rollback conditions

If any of the following → take down the HN linkpost via `delete` (allowed within first 2h):

- Critical bug found that misrepresents methodology
- VPS goes down for > 5 min and we cannot restore
- A top comment exposes a factual error we cannot refute and cannot quickly fix

Soft rollback (don't delete, but stop driving traffic): if NPS-equivalent
feedback in the comments turns hostile in the first 3 hours, stop tweeting
/ re-posting, let it slide off front page naturally.

---

## Recommended launch dates (2026)

**Avoid**:

- US federal holidays: Memorial Day Mon **2026-05-25**, Independence Day Sat **2026-07-04** (4-day weekend), Labor Day Mon **2026-09-07**, Thanksgiving Thu **2026-11-26** (4-day weekend), Christmas/New Year period **2026-12-21 to 2027-01-04**
- Chinese national holidays: Labor Day window **2026-05-01 to 2026-05-05**, National Day **2026-10-01 to 2026-10-07**, Spring Festival **2026-02-16 to 2026-02-24** (already past)
- NeurIPS 2026 submission window: late May 2026 (avoid the week before deadline)
- Major macro: FOMC announcement days (next: 2026-06-17, 2026-07-29, 2026-09-16) — financial-adjacent audiences distracted

**Recommended primary launch windows** (Tue/Wed mornings, 9 AM ET):

| Date | Tue/Wed? | Notes |
|---|---|---|
| **2026-06-02** Tue | Tue ✓ | First post-Memorial-Day Tuesday; cleanest window |
| **2026-06-03** Wed | Wed ✓ | Backup if 06-02 weather/health issue |
| **2026-06-09** Tue | Tue ✓ | Strong second-week window |
| **2026-06-10** Wed | Wed ✓ | |
| **2026-06-16** Tue | Tue (avoid) | FOMC day next day — split attention |
| **2026-06-23** Tue | Tue ✓ | Solid window, post-FOMC |
| **2026-06-24** Wed | Wed ✓ | |

**Strong recommendation**: **Tuesday 2026-06-02, 09:00 ET launch**.
Rationale:
- First post-holiday Tuesday → clean attention
- Late enough to land all T-1 day load-tests + arXiv submission (~1 week buffer)
- Early enough to avoid FOMC week chatter
- Tuesday morning ET = HN historical peak engagement window
- 8 days from today (2026-05-25) — enough room for the blockers but not so far away the momentum dissipates

**Backup primary**: 2026-06-03 Wed if Tue is health/weather-blocked.

**Secondary window**: 2026-06-23 Tue if backtest v0.2 results aren't ready by 2026-05-31.

---

## Post-launch retro template

To be filled at T +7 days:

```
# HN launch retro — YYYY-MM-DD

## Numbers
- HN: rank ___ / score ___ / comments ___
- GitHub: +___ stars / +___ forks / +___ issues
- PyPI: ___ daily downloads (peak), ___ unique IPs
- Twitter: ___ impressions on tweet 1, ___ new followers
- LinkedIn: ___ impressions, ___ reactions
- Reddit r/Physics: ___ upvotes, ___ comments
- arXiv: ___ abstract views in 24h
- Site: ___ unique visitors in 24h, ___ in 7 days
- Waitlist: +___ signups
- Plausible bounce rate: ___%

## What worked
- (3–5 specific things, with evidence)

## What didn't work
- (3–5 specific things, with evidence)

## Top objections actually surfaced
- (sorted by frequency; flag which were in pre-prepared FAQ)

## Lessons for next launch
- (3–5 specific items, with action owners)
```
