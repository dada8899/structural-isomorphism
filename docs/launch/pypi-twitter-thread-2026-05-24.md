# Twitter / X thread — PyPI launch (short version) — 2026-05-24

**Posted**: PyPI day, ~14:00 PT (afternoon slot — different from morning arXiv slot).
**Format**: 5-tweet thread. Brief vs the 10-tweet arXiv thread.
**Account**: same as arXiv thread.
**Companion**: `pypi-launch-post-2026-05-24.md` linked from tweet 1.

> Difference vs `twitter-thread-arxiv-2026-05-24.md`:
> - PyPI thread is shorter (5 vs 10 tweets)
> - lead with `pip install` one-liner, not with arXiv ID
> - tweet 1 has a 30-sec code-screencast attached (different from arXiv demo.mp4)
> - skips the limitations/honest-limits section (covered in long-form post)

---

## Tweet 1 (with code-screencast.mp4 attached, ~30s)

`pip install structural-soc-pipeline`. Frozen 339-line Clauset MLE pipeline now on PyPI. Same function for every cross-domain system in our paper — neural avalanches, bank runs, wildfires, GitHub stars. KS-optimal xmin, Hill alpha, block-bootstrap CIs, Vuong tests. Thread ↓

## Tweet 2

Three packages released today: `structural-soc-pipeline` (the frozen 339-LOC fit module), `structural-critics` (multi-vendor LLM critic ensemble used in SIBD-63 curation), `structural-taxonomy` (pre-registered exponent bands + cross-domain variable mappings). All on PyPI.

## Tweet 3

```python
from structural_soc.pipeline import fit_powerlaw

result = fit_powerlaw(my_sizes, xmin_method="ks", bootstrap_reps=1000)
print(result.alpha, result.alpha_ci, result.vuong_lognormal)
```

Try your heavy-tailed dataset. The package returns the verdict regardless of what you wanted to find. That's the point.

## Tweet 4

To reproduce one of the paper's 17 pre-registered verdicts on your machine: `git clone github.com/dada8899/structural-isomorphism && python v4/validate.py neural-avalanches`. Returns PASS / FAIL / PARTIAL / NULL / INCONCLUSIVE + full diagnostic table. If your run mismatches our published table — P0 issue.

## Tweet 5

Code MIT. Dataset CC-BY-4.0 on Zenodo (doi.org/10.5281/zenodo.19615170). arXiv preprint: ARXIV_ID_PENDING. Long-form launch post: github.com/dada8899/structural-isomorphism/blob/main/docs/launch/pypi-launch-post-2026-05-24.md. Looking for reviewers who will try to break the methodology.

---

## Visual asset spec — code-screencast.mp4

Should NOT be the same as the arXiv demo.mp4. This one is a terminal recording.

```bash
# 30 sec asciinema cast
asciinema rec --idle-time-limit 1 --rows 28 --cols 100 tools/code-screencast.cast
# Script:
#   1. pip install structural-soc-pipeline   (3s)
#   2. python (1s)
#   3. >>> from structural_soc.pipeline import fit_powerlaw  (2s)
#   4. >>> result = fit_powerlaw([3,1,2,7,...], xmin_method="ks", bootstrap_reps=200)  (8s while it runs)
#   5. >>> print(result.alpha)  (1s) → 1.523
#   6. >>> print(result.alpha_ci)  (1s) → (1.48, 1.58)
#   7. >>> print(result.vuong_lognormal)  (1s) → R=2.1, p=0.018
#   8. >>> result.verdict  (1s) → 'PASS (band: (1.4, 1.7))'

# Convert to video
agg tools/code-screencast.cast tools/code-screencast.gif --rows 28 --cols 100 --speed 1.0
# Then GIF -> MP4 for Twitter
ffmpeg -i tools/code-screencast.gif -movflags +faststart \
  -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" \
  site/code-screencast.mp4
```

Target file size: ≤ 1 MB.

## Engagement strategy

- Reply to ANY question with a copy-paste code snippet. The PyPI audience is technical and wants to run it.
- Pin tweet 1; quote-retweet from co-author / trusted reviewer for amplification.
- If a quote-reply asks "does it work for [X data]" → respond with the snippet to try, NOT with a vague "yes".
- After 24h: if the thread cleared 100 likes on tweet 1, the launch is healthy. < 30 → diagnose (likely the demo.mp4 didn't render in mobile feed).
