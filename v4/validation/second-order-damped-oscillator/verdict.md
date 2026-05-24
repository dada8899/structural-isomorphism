# Verdict — Second-Order Damped Oscillator (Cross-Domain Universality)

> **Date.** 2026-05-25
> **System.** 5-domain cross-class test of m·ẍ + c·ẋ + k·x = F(t).
> **Class.** `second_order_damped_oscillator` (B3 rank=8, verified=false).
> **Verdict.** **REJECT**
> **Reason.** ζ spread 2395.4x >= 10.0; regimes split across {'overdamped', 'near_critical', 'underdamped'}

## Pre-registered PASS gate

- Per-domain N ≥ 20
- Cross-domain ζ-median spread < 10x
- All domain dominant regimes equal (one of underdamped / near_critical / overdamped)

## Per-domain summary

| Domain | N | ζ min | ζ median | ζ max | ζ geomean | ω₀ median (Hz) | Regime |
|---|---:|---:|---:|---:|---:|---:|---|
| economic_macro | 23 | 0.5241 | 0.7953 | 0.9862 | 0.7616 | 0.2536 | near_critical |
| mechanical_building | 20 | 0.007 | 0.012 | 0.016 | 0.01153 | 0.1675 | underdamped |
| pendulum | 24 | 5.198e-07 | 0.0005583 | 0.2142 | 0.0004353 | 0.4139 | underdamped |
| power_grid_swing | 24 | 0.02246 | 1.337 | 12.24 | 0.869 | 1.325 | overdamped |
| rlc_circuit | 24 | 5e-05 | 0.07646 | 33.23 | 0.06647 | 1592 | underdamped |

## Cross-domain ζ spread

- max(median ζ) / min(median ζ) = **2395.41x**
- Domain regimes: {'economic_macro': 'near_critical', 'mechanical_building': 'underdamped', 'pendulum': 'underdamped', 'power_grid_swing': 'overdamped', 'rlc_circuit': 'underdamped'}
- Insufficient-N domains: none

## Interpretation

Cross-domain ζ scatters across regimes — mechanical buildings sit in a very narrow ultra-underdamped band (ζ ~ 0.01), while RLC, economic, and power-grid distributions span 2-3 decades of ζ and cross from underdamped to overdamped. **The second-order ODE is a *mathematical framework* not a universality class**: it parameterises any linear stable 2-pole system but does not predict cluster behaviour.

## Paper positioning recommendation

- **Demote** `second_order_damped_oscillator` from a universality class to a   *Layer-0 mathematical descriptor* in the v0.4 taxonomy (similar to   `markov_chain_memory_fidelity`, `tail_copula_contagion`,   `extreme_value_tail_class`: descriptor families, not mechanism classes).
- The (ω₀, ζ) joint distribution is still useful as a *common parameterisation*   across linear stable systems but it does not impose a cross-domain   scaling-law constraint that mechanism-class members must obey.
- The KB members (power-system small-signal, transient stability, high-rise   wind vibration) should remain linked by the shared *engineering practice*   of expressing modal dynamics in (ω₀, ζ) form, but flagged as a   representation choice not a universality claim.

## Reproduction

```bash
cd ~/Projects/structural-isomorphism
.venv/bin/python v4/validation/second-order-damped-oscillator/run_validation.py
```

Wall-clock ~30 s after FRED CSV cache hit (< 2 min cold).

End of verdict card.
