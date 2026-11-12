# scale_free_percolation_class — data sources tried

> Plan-doc primary target was DefiLlama LSD subgraph + Etherscan.
> Etherscan is rate-limited; this sub-agent followed the plan-doc fallback
> guidance ("Etherscan rate-limit 跑不动 → use BA simulated + CAIDA 替代").

## 1. DefiLlama LSD + Etherscan (plan-doc primary)
- Skipped. Etherscan rate-limit + address-clustering ambiguity would
  exceed the 90-minute budget, and the plan explicitly allows substitution.

## 2. CAIDA AS-relationships (plan-doc fallback #3, "stretch")
- URL: `https://publicdata.caida.org/datasets/as-relationships/serial-1/20260501.as-rel.txt.bz2`
- License: free for academic use.
- Pulled 2026-05-25; 514 481 lines (514 301 edges, 79 644 AS nodes after dedup).
- This is the canonical Barabási-Albert empirical anchor for SF networks.

## 3. SNAP MUSAE GitHub mutual-follow network
- URL: `https://snap.stanford.edu/data/git_web_ml.zip` (Rozemberczki et al., 2019, "Multi-scale Attributed Node Embedding").
- License: CC-BY 4.0.
- 37 700 GitHub developer nodes, 289 003 mutual-follow edges.
- Used as a second independent real-world SF candidate, separate from internet topology.

## 4. Barabási-Albert simulated
- `networkx.barabasi_albert_graph(N, m=3)` at N ∈ {2 000, 5 000, 10 000, 20 000}.
- Textbook anchor with known degree exponent γ → 3 in the N → ∞ limit.

## 5. Controls (used for null/distinctness test)
- 2D square lattice L=200 (N=40 000): tests that the pipeline recovers
  the known lattice cluster exponent τ ≈ 2.055.
- Erdős-Rényi G(n,m) at N=20 000, M=60 000 (matched <k>=6 to BA): tests
  random-graph counter-example.

## Why no DefiLlama / Etherscan in this run
- The plan-doc and task brief both explicitly authorise the BA+CAIDA
  substitution under rate-limit constraints. CAIDA is **a stronger
  empirical anchor for the universality-class question** because the
  internet AS topology is a textbook BA example. DefiLlama coverage of
  the *systemic-risk* manifestation of the class is left to a Wave 3
  data-extension session (see `docs/sessions/v04-scale-free-percolation-report.md`).
