# 8 Transformation Primitives (V4 schema)

When taking a solved problem from domain A and applying it to domain B, the "transformation" can be decomposed into combinations of these 8 primitive operations:

| ID | Name | Description | Example |
|---|---|---|---|
| `variable_rename` | Variable rename | Same math, change symbol/unit | Thermodynamic entropy → Shannon entropy (only the unit changes) |
| `concept_transfer` | Concept transfer | Replace one physical quantity with a structurally analogous one | F=ma's mass → LC oscillator's inductance (mass → inductance) |
| `causal_inversion` | Causal inversion | Swap cause and effect direction | Supply-demand determines price → price determines supply-demand |
| `continuity_toggle` | Continuous ↔ discrete | Switch between continuous and discrete formulations | Differential equation → difference equation / cellular automaton |
| `boundary_rewrite` | Boundary condition rewrite | Change boundary conditions, topology, or domain | Open system → closed system; infinite line → ring |
| `dim_shift` | Dimension shift | Change the effective dimensionality (up or down) | 2D Ising → 3D Ising; Kaluza-Klein extra dim |
| `stochastic_toggle` | Stochasticity toggle | Add or remove random noise | Deterministic Lotka-Volterra ODE → Gillespie stochastic simulation |
| `time_scaling` | Time scaling / regime shift | Change the time scale or temporal regime | Thermodynamic equilibrium → non-equilibrium dynamics |

## Labeling rules

- Each historical case is labeled with a **set** of applied primitives (can be 0-N).
- If no transformation is needed (pure isomorphism with same variables), label with empty set.
- If a custom transformation doesn't fit any primitive, note `other` + description.
- `variable_rename` should ONLY apply when the change is literally just naming/units; if a deeper reinterpretation happens, prefer `concept_transfer`.
