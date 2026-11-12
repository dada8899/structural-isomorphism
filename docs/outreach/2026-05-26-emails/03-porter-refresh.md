**To:** [Prof. Mason A. Porter — preferred institutional email, to be confirmed]
**Cc:** —
**Send date:** [PENDING_SEND_DATE]

---

**Subject:** v0.5 update — multilayer test pattern adds a network-growth candidate row + Phase 7 unchanged

Dear Prof. Porter,

Following my 2026-05-25 note: the v0.4 arXiv submission is still pending, and the v0.5 draft (`paper/v0.5-draft/v05-draft-skeleton.md`, HEAD `14a73c4`) now adds a methodology increment that I think benefits from your read because one of its cross-class candidate rows lives squarely on the preferential-attachment / scale-free-networks territory you have shaped.

§3.6.6 (multilayer test pattern) lists four candidate classes whose underlying theory predicts *different* scaling forms at *different* scales. One of them is the network-growth row:

> Per-node degree power-law (preferential attachment) × Cross-network: giant-component / Barabási–Albert ensemble statistics × anchors: Barabási-Albert 1999; Newman 2003; Faloutsos 1999 (CAIDA AS graph).

The pattern says: test these *separately*, with each layer's verdict computed against its own functional form. v0.5 does not actually run this test on a network-growth dataset; it lists the candidate as a future-work row. Two asks:

(a) Is the Layer 1 / Layer 2 decomposition for preferential-attachment well-posed at all? I worry that the per-node degree distribution and the ensemble size distribution are not as cleanly separable as the Aβ aggregation case where Smoluchowski (Layer 1) and lognormal multiplicative-growth (Layer 2) are different physics. Would you push back on the pattern as applied to network-growth?

(b) The v0.4 Phase 7 Motter-Lai cascade verdict (LOW independence, $n=123$ literature-meta catalog) is unchanged in v0.5. Your 2026-05-25 ask stands: is the "consistent-with-anchors, not independent" framing fair? FOIA-acquired OE-417 raw catalog or ENTSO-E roster remain on the to-do list.

(c) `scale_free_percolation_class` REJECT verdict unchanged. Same ask as before — is the call defensible?

Repo public, ~30 min on §3.6.6 + Phase 7 + §5 (`scale_free_percolation_class` row) would be plenty. No endorsement requested.

Best regards,

Wan Qinghui (万庆徽)
Independent researcher
Repo: https://github.com/dada8899/structural-isomorphism
v0.5 draft: paper/v0.5-draft/v05-draft-skeleton.md
arXiv: [PENDING_ARXIV_ID — preprint forthcoming]
Zenodo: [PENDING_ZENODO_DOI]
