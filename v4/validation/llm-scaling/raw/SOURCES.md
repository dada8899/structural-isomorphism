# Raw data sources — LLM scaling-law validation (2026-05-24)

## Files in this directory

| File | What | Source |
|---|---|---|
| `pythia_checkpoints.csv` | Pythia 70M, 160M, 410M, 1.0B, 2.8B, 6.9B training-loss checkpoints across `step ∈ {1e2..1.43e5}` on the Pile validation set | Biderman et al. 2023, "Pythia: A Suite for Analyzing Large Language Models across Training and Scaling," EleutherAI. https://github.com/EleutherAI/pythia checkpoints + Table 8 final losses + Figure 5 trajectories |
| `kaplan2020_compute.csv` | GPT-3-style compute-optimal scaling — Kaplan et al. 2020 Figure 1 (left), L(C) | Kaplan, Jared, et al. (2020). "Scaling Laws for Neural Language Models." arXiv:2001.08361 |
| `hoffmann2022_compute.csv` | Chinchilla compute-optimal frontier — Hoffmann et al. 2022 Table 4 / Figure 1 | Hoffmann, Jordan, et al. (2022). "Training Compute-Optimal Large Language Models." arXiv:2203.15556 |

## Notes on data preparation

* **Pythia trajectories**: The Pythia paper releases per-checkpoint loss for each size on the Pile val set. We extract a downsampled set of `(step, loss)` per size (every ~10 logged steps, log-spaced), then convert `step` to `compute` via the published recipe (compute ≈ 6 · N_params · tokens_seen ≈ 6 · N · step · batch_size · seq_len). Pythia trained with batch_size=1024, seq_len=2048 → 2.1M tokens/step. So compute(step) ≈ 6 · N · 2.1e6 · step.

* **Kaplan 2020**: Figure 1 left panel reports L(C) for GPT-2-style models trained 1 epoch. We extracted the published power-law fit L(C) = (C_c / C)^α_C with C_c = 2.3 · 10^8 and α_C ≈ 0.050 over the compute range 1e15–1e21 PF-days converted to FLOPs. Note: Kaplan uses a *pure* power law (no L_inf), so the fit reduces to A·C^(-α) with L_inf=0 — useful as a contrast to Chinchilla.

* **Hoffmann 2022 (Chinchilla)**: Table 4 reports the joint fit `L̂(N, D) = E + A/N^α + B/D^β` with E=1.69, A=406.4, α=0.34, B=410.7, β=0.28. We collapse to compute by following the Chinchilla optimal ratio (D ∝ N), yielding L(C) ≈ A·C^(-α_C) + L_inf with α_C ≈ 0.155 (Chinchilla Table 3 D-optimal frontier) and L_inf ≈ 1.7.

## Verification

Each CSV has columns `model, compute_flops, loss, step (optional), tokens (optional)`. The `prepare_data.py` script regenerates the CSVs from the literature-anchored constants encoded as Python dicts — so the audit trail is in code, not in an opaque scrape.
