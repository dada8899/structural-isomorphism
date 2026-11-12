# Verdict — markov_chain_memory_fidelity_class

- **Date.** 2026-05-25
- **Class id.** `markov_chain_memory_fidelity_class`
- **B3 a-priori.** REJECT (statistical descriptor, not mechanism); rank=16 verified=false
- **Top verdict.** **REJECT-CONFIRMED**
- **Reason.** tau_mix spread 2.98 decades > 2.0: Markov framework absorbs any state series; tau_mix is set by each domain's native dynamics, not by any shared mechanism. B3 'statistical descriptor, not mechanism' confirmed.

## Per-domain results

| # | Domain | n_states | n_obs | time unit | |lam2| | tau_mix | H_norm |
|---|---|---|---|---|---|---|---|
| 1 | `D1_text_pride_prejudice_chars` | 27 | 692,490 | characters | 0.2916 | 0.81 characters | 0.862 |
| 2 | `D2_dna_human_mtdna_nucleotides` | 4 | 16,568 | base_pairs | 0.0731 | 0.38 base_pairs | 0.965 |
| 3 | `D3_fred_usrecd_daily_recession` | 2 | 62,629 | days | 0.9973 | 364.16 days | 0.849 |
| 4 | `D4_moodys_corp_rating_1y_transition` | 8 | lit | years | 0.9895 | 94.54 years | 0.905 |

## Cross-domain universality score

| Quantity | Value | Interpretation |
|---|---|---|
| n_domains with finite tau_mix | 4 | need >=3 to score |
| tau_mix log10 spread | **2.98 decades** | cluster if <0.5; REJECT-CONFIRMED if >2.0 |
| H_norm spread | 0.116 | cluster if <0.20 |
| descriptor_confirmed | True | True ⇒ B3 REJECT empirically confirmed |
| verdict_label | **REJECT-CONFIRMED-DESCRIPTOR** | — |

## Null controls

| Null | tau_mix | Expected | Pass? |
|---|---|---|---|
| `N1_iid_uniform_k5` | 0.21 | expected tau_mix ~ 1 (iid) | True |
| `N2_strict_period2` | inf | expected tau_mix inf (periodic) | True |
| `N3_lazy_ring_rw_k10` | 10.19 | expected tau_mix ~ 10-30 (ring RW k=10) | True |

## Paper positioning

This class is a **Layer-0 REJECT confirmation**: Markov chain is a
mathematical *framework*, not a universality mechanism. Every state-
space process in nature can be approximated by a Markov chain, but
the resulting tau_mix is set by the *domain's* native dynamics, not
by any shared mechanism. Concretely the four domains span
**2.98 decades** of mixing time:

- `D1_text_pride_prejudice_chars`: tau_mix ~ 0.81 characters
- `D2_dna_human_mtdna_nucleotides`: tau_mix ~ 0.38 base_pairs
- `D3_fred_usrecd_daily_recession`: tau_mix ~ 364.16 days
- `D4_moodys_corp_rating_1y_transition`: tau_mix ~ 94.54 years

The v0.4 paper should treat this class as an **expected-REJECT
cluster** anchor alongside `extreme_value_tail_class` and
`tail_copula_contagion_class`. Together they define the
**descriptor vs. mechanism boundary**: a real universality class
must cluster exponents across mechanisms (Manna, DP, Tracy-Widom,
etc.); a descriptor framework absorbs anything and produces
domain-specific numbers (EVT, copulas, Markov).

_elapsed: 0.9s_
