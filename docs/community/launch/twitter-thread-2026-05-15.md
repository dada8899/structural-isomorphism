# Twitter / X launch thread — 2026-05-15

Posted: 2026-05-15 morning PT (09:00 PT optimal window)
Account: @dada8899 (or project handle)
Format: 7-tweet thread. Each tweet ≤ 270 chars to leave room for trailing media.

Below: each tweet content is on the line immediately after its number, single-line, no internal newlines.

---

1. Do systems from radically different scientific domains share the same mathematical structure? We tried to answer it honestly: same Clauset MLE pipeline, no per-domain tuning, pre-registered exponent bands, 13 empirical systems. Repo + dataset below. A thread.

2. Universality classes are a 50-year-old stat-mech idea: a small set of equations describe phase transitions in materials, fluids, magnets that look nothing alike. The question: does the same extend, untuned, to neural avalanches, DeFi liquidations, wildfires, citation cascades?

3. The pipeline is one frozen module: v4/lib/soc_pipeline.py, 339 LOC, commit 7ee228c. Discrete Clauset MLE, KS-optimal xmin, Hill-form alpha, block-bootstrap CIs, Vuong tests vs lognormal + exponential. Same function, every system. No per-domain knobs downstream.

4. Reject-aware methodology: 21 LLM-curated candidate classes -> 18 B1 survivors -> 14 B3 survivors -> 17 pre-registered tests -> 13 passing. 4 prototype demotions on record. The funnel is the point: a pipeline that never rejects is not measuring anything.

5. Honest limits: B3 ensemble is within-vendor multi-decoding, not cross-architecture (B4 blocked by region routing). One v0.3 collapse stat (r_shape) was a combinatorial artifact, fixed in v0.4. Several alpha estimates sit near inverse-cubic boundary. All in the paper.

6. Open dataset: SIBD-63 on Zenodo (10.5281/zenodo.19615170). 63 A-level cross-domain pairs with shared equations, variable mappings, multi-vendor critic verdicts (Claude / DeepSeek / Kimi / GLM-5). CC-BY-4.0. Ready for replication, critique, fork.

7. Code MIT, data CC-BY. Looking for reviewers who will try to break the methodology. arXiv preprint pending. Repo: github.com/dada8899/structural-isomorphism — Live demos: beta.structural.bytedance.city + phase.bytedance.city
