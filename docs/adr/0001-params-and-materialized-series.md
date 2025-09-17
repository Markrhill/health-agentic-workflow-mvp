# ADR 0001: Versioned params + materialized daily series
Date: 2025-09-16
Status: Accepted

## Context
We need reproducible weekly coaching snapshots and UI speed. EMA smoothing params (α_fm, α_lbm), compensation c, and BMR params must be versioned and applied consistently.

## Decision
- Store effective-dated params in `model_params_timevarying`.
- Compute `daily_series_materialized` daily with:
  - `fat_mass_ema_kg` (α_fm)
  - `lbm_ema_kg_for_bmr` (α_lbm)
  - `bmr_kcal = bmr0 + k_lbm * lbm_ema_kg_for_bmr`
  - `adj_exercise_kcal = (1 - c) * workout_kcal`
  - `net_kcal = intake - adj_exercise_kcal - bmr_kcal`
- Weekly snapshots read only from materialized daily series.

## Consequences
- Fast UI reads and immutable weekly snapshots.
- Parameter changes require new `params_version` and recomputation to compare eras.
