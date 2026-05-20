***REMOVED*** Session ***REMOVED***16 — Handoff

**Started**: 2026-05-20 evening
**Ended**: 2026-05-21 (UTC morning)
**Mode**: Full auto-drive (user said "把整个项目能往下做的全部做完" 两次)
**Outcome**: 16 commits to main, 88/88 M1.4 test green (374/374 full suite),
**M1.4 全 5 PR shippable** (backend + frontend + viewer page), Validator P0/P1/P2 全清,
6/36 已合并 stale branch 删除。

---

***REMOVED******REMOVED*** 0. TL;DR for the next session

**Prod fingerprint check is now ONE COMMAND**:
```bash
python3 ~/Projects/structural-isomorphism/scripts/dogfood_fingerprint.py
```
If this exits non-zero, prod is on the wrong code — don't trust any dogfood numbers until it's green.

**M1.4 backend is done + Validator-reviewed**. Only frontend PR ***REMOVED***5 remains. See `M1.4-frontend-integration-guide.md` for the next session.

**1 unresolved P0** (needs user action, not CC):
- Set `STRUCTURAL_SHARE_TOKEN_SECRET` in VPS `/root/Projects/structural-isomorphism/web/backend/.env` (generate with `python -c "import secrets; print(secrets.token_hex(32))"`). Without this, `/api/analyze/stream?persist=1` will RAISE in prod (intentional fail-fast). Set it once — rotating breaks every existing share URL.

---

***REMOVED******REMOVED*** 1. What landed (12 commits, main)

| ***REMOVED*** | Commit | Description |
|---|---|---|
| 1 | `90c0b14` | `/api/version` returns model + deployed_at; deploy-vps.sh writes .env.runtime; dogfood_fingerprint.py |
| 2 | `8644ee4` | M1.4 PRD v0.1 (`docs/sessions/M1.4-report-generator-prd.md`) |
| 3 | `f2ce48f` | Forecasting-intent keyword gate (ask) + PRD update with real prod data |
| 4 | `44e557d` | M1.4 PR ***REMOVED***1 — ReportStore + share token signing |
| 5 | `05a879f` | M1.4 PR ***REMOVED***2+***REMOVED***3+***REMOVED***4 — /api/report endpoints + persist=1 in /api/analyze/stream |
| 6 | `7a4a8b1` | M1.4 e2e tests (SSE → persist → share read round-trip) |
| 7 | `50729f0` | analyze-stream API spec + cross-judge v1.0 stability table |
| 8 | `e241ec3` | runtime-smoke CI workflow (closes session-15 incident ***REMOVED***2) |
| 9 | `bd013c6` | env override policy doc + deploy fingerprint verify gate |
| 10 | `316651c` | cleanup-stale-branches.sh (36 merged branches eligible) |
| 11 | `4e7493e` | Validator review fixes: P0 share-secret + 3 P1 (NULL upsert / is_partial / model drift) |
| 12 | `4bb6e6d` | Frontend integration guide for PR ***REMOVED***5 |
| 13 | `8543bc1` | Test isolation fix (verify_api_token cross-pollination) |
| 14 | `7c028c1` | SESSION-16 handoff + SESSION-17 start prompt |
| 15 | `addbb08` | **M1.4 PR ***REMOVED***5** — frontend share + feedback + persisted-report viewer (685 LOC) |
| 16 | `6f5b9c8` | Validator P2 batch — 6 nice-to-fix items (text_a cap / async subprocess / payload cap / etc.) |

**Stale branch cleanup**: 6 of 36 merged branches deleted manually
(session7/ask-ui, session7/backtest, v4/session3-w1e/w2a/w2b/w2c).
Auto-mode classifier stopped further bulk deletes. Use
`./scripts/cleanup-stale-branches.sh` for the rest.

---

***REMOVED******REMOVED*** 2. What's still pending

***REMOVED******REMOVED******REMOVED*** 2.1 User action required (CC can't do)

| ***REMOVED*** | Action | Why blocked |
|---|---|---|
| **P0** | Set `STRUCTURAL_SHARE_TOKEN_SECRET` in VPS `.env` | SSH credentials + secret generation are user's call |
| P1 | Configure `PYPI_TOKEN` GitHub secret | Token issue |
| P1 | Upload 5 papers to arXiv | Account |
| P1 | DeepSeek API key rotate + delete audit branch | Account |
| P2 | `ZENODO_ACCESS_TOKEN` for DOI mint | Account |
| P2 | `HF_TOKEN` for model push | Account |

***REMOVED******REMOVED******REMOVED*** 2.2 PR ***REMOVED***5 (DONE in this session)

✅ Frontend integration landed in commit `addbb08`:
- analyze.js: persist=1 by default + anon_id query param + persisted SSE handler
- New report.html + report.js (/report/share/{token} + /report/{id} routes)
- Share bar (URL + copy/open buttons) + per-section + overall 👍/👎 feedback
- 5 Plausible events wired (Persisted / Share Clicked / Share Page Viewed / Feedback / future List Viewed)
- XSS defence via escapeHtml in report.js

**Still TODO (next session, not ship-blocking)**:
- Playwright e2e (5 scenarios per integration guide §5)
- "My Reports" list page (the `/api/reports/mine` endpoint is ready)
- PDF / Markdown export (Pro layer)
- Free-text feedback comment box (v1.1)

***REMOVED******REMOVED******REMOVED*** 2.3 Validator P2 items — 6/8 DONE in this session (commit `6f5b9c8`)

✅ text_a Query max_length=2000 cap
✅ /api/version subprocess via asyncio.to_thread
✅ cache-hit branch re-computes is_partial from EXPECTED_SECTIONS
✅ ReportStore.create raises on payload > 256 KB (+ 1 new regression test)
✅ dogfood_fingerprint.py stderr warn when both --expect-sha and git rev-parse empty
✅ deploy-vps.sh warns when SOURCE has no .git

Deferred (not material):
- ***REMOVED***6 anonymous-id ACL hardening (designed v1 trade-off)
- ***REMOVED***10 frontend XSS sanitize (done in report.js escapeHtml)

***REMOVED******REMOVED******REMOVED*** 2.4 M2 backlog (touched but unfinished)

- ⏸ Stale remote branches: 36 merged ones can be one-clicked deleted with `./scripts/cleanup-stale-branches.sh`. The 124 unmerged need per-branch judgment.
- ⏸ V4 universality class extensions (Layer 5 Phase 6-15) — long-term roadmap, no urgency.
- ⏸ Cross-judge v1.1 async critique pass — wait for ≥ 100 reports / week first.

---

***REMOVED******REMOVED*** 3. How to verify session-***REMOVED***16 actually deployed

After the next push to main triggers `deploy-beta-backend.yml`:

```bash
***REMOVED*** 1. Fingerprint check (gives full status in one line)
python3 ~/Projects/structural-isomorphism/scripts/dogfood_fingerprint.py

***REMOVED*** Expected output:
***REMOVED***   semver:       0.2.0
***REMOVED***   git_sha:      <commit on main>
***REMOVED***   model:        deepseek/deepseek-chat:nitro
***REMOVED***   env:          prod
***REMOVED***   deployed_at:  <recent UTC timestamp>
***REMOVED***   ✅ fingerprint OK

***REMOVED*** 2. Verify /api/version has the new fields
curl -s https://beta.structural.bytedance.city/api/version | python3 -m json.tool
***REMOVED*** Expected fields: semver, git_sha, model, deployed_at, build_date, env, python_version

***REMOVED*** 3. Try a forecasting-intent query — should refuse locally fast (~1-3s)
curl -sN -X POST -H "Content-Type: application/json" \
  -d '{"query":"AI 能不能预测股票","lang":"zh"}' \
  https://beta.structural.bytedance.city/api/ask/stream | head -c 800
***REMOVED*** Expected: refused=true with forecasting-specific text ("不预测资产价格")

***REMOVED*** 4. Once STRUCTURAL_SHARE_TOKEN_SECRET is set, try persist
curl -sN \
  "https://beta.structural.bytedance.city/api/analyze/stream?b_id=soc-160&text_a=test&persist=1" \
  -H "X-Anon-Id: test-anon" | grep -E "^event: persisted"
***REMOVED*** Expected: one `event: persisted` line with share_url
```

---

***REMOVED******REMOVED*** 4. Files / paths the next session needs

| Path | Why |
|---|---|
| `docs/sessions/M1.4-report-generator-prd.md` | full M1.4 design + open questions |
| `docs/sessions/M1.4-frontend-integration-guide.md` | what PR ***REMOVED***5 builds |
| `docs/api/analyze-stream-spec.md` | the wire format |
| `docs/deployment/env-override-policy.md` | prod env audit rules |
| `scripts/dogfood_fingerprint.py` | first thing to run |
| `scripts/cleanup-stale-branches.sh` | branch hygiene when ready |
| `web/backend/services/report_store.py` | ReportStore + share token |
| `web/backend/api/report.py` | the 4 new endpoints |
| `web/backend/tests/test_*` (5 files) | all green; do not break |

---

***REMOVED******REMOVED*** 5. Discipline notes (carried forward)

- **`scripts/train_v2.py` is STILL another session's in-flight** — `git status` shows it modified; do NOT add it to any commit. Same for `.claude/worktrees/agent-a3e2f585dec5d670b/`.
- Every commit in this session used explicit `git add <files>` — no `-A` / no `commit -a`. Continue.
- The auto-mode classifier (correctly) blocked one bulk `git push --delete` operation; that's the right boundary. Use the cleanup script when you decide to act.
- After M1.4 PR ***REMOVED***5 lands, drive 4 reviewers (marketing / UX / security / i18n) over the full flow per project nature.
- Real-prod analyze stream measured > 180s for 6/9 sections — PRD §5.1 has the math; do NOT promise users "completes in 60-120s".

---

***REMOVED******REMOVED*** 6. Counts

- **19 task-list items**: 18 completed + 1 user-action-blocked (P0 prod secret)
- **16 commits** to main (M1.4 PRs ***REMOVED***1-5 all landed + Validator fixes + ops docs)
- **88/88 M1.4 tests pass** (374/374 full backend suite when last measured)
- **~62 new tests added** (5 version + 12 forecasting + 27 report_store + 16 report_api + 4 analyze_persist)
- **~3,900 LOC net additions** across backend + frontend + tests + docs
- 0 commits to `scripts/train_v2.py` (correctly left alone)
- Validator: 1 P0 + 3 P1 fixed + **6/8 P2 fixed** (2 P2 designed-as-is)
- 6/36 merged stale branches deleted; 30 left to `cleanup-stale-branches.sh`
