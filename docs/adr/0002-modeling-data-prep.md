# ADR 0002 — Modeling Data Prep (Train/Test)

**Status:** Accepted  
**Date:** 2025-09-02

## Context
We are building a ΔFat Mass (ΔFM) model using daily nutrition, workouts, and body composition. We must be explicit about selection, imputation, and windowing so results are reproducible.

## Decision
Use a fixed train/test split, explicit imputations, and strict window eligibility rules.

### Data sources
- **intake_kcal** (MyFitnessPal → daily_facts / p0_staging)
- **workout_kcal** (TrainingPeaks → daily_facts / p0_staging)
- **fat_mass_kg** (Withings; interim from spreadsheet hack; Withings API later)

### Split
- **Train:** 2021-01-01 … 2024-12-31 (`p1_train_daily`)
- **Test:**  2025-01-01 … 2025-08-04 (`p1_test_daily`)

### Imputations
- **Intake:** If NULL, impute with **day-of-week mean** computed from observed days in the same split; mark `intake_imputed = true`.
- **Workout:** If NULL, treat as **0** (assume no recorded training = no training); mark `workout_imputed = true` ONLY if originally NULL.
- **Fat mass:** **No imputation** for model training. Windows requiring ΔFM must have both start and end FM observed.

### Windowing for ΔFM
- Window length: **7 days** (primary). We may test 14-day sensitivity later but report 7-day as canonical.
- A window is **eligible** if:
  - all 7 days have `intake_kcal` (observed or imputed) and `workout_kcal` (observed or 0),
  - the **first** and **last** day of the window have **observed** `fat_mass_kg` (no impute),
  - the window contains no flagged FM outliers (see below).
- ΔFM definition: `ΔFM_kg = fat_mass_kg(t_end) − fat_mass_kg(t_start)`.
- Net energy: `ΣNetKcal = Σ (intake_kcal − workout_kcal)` over the window.

### Outliers & QC
- **FM outlier rule:** exclude any day where `|fat_mass_kg − median_7d(fat_mass_kg)| > 2.5 × MAD_7d`. Mark excluded windows with `window_excluded_fm_outlier = true`.
- **Unit discipline:** all mass in **kg**, energy in **kcal**. 7,700 kcal/kg applies to **ΔFM only**.
- **Provenance flags:** carry `*_is_observed`/`*_imputed` booleans into window rows for audit.

### Maintenance (M) estimation
- Physics-anchored: slope fixed at 7,700 kcal/kg for ΔFM; solve closed-form M that minimizes squared error on eligible windows.
- Report: M (kcal/day), MAE/MAPE on **train**, and generalization error on **test**.

### Versioning
- Any change to split, imputation, or eligibility increments model prep version `prep_v = 1, 2, …` and is recorded here.

## Rationale
- Keeps modeling reproducible and debuggable.
- Prevents leakage across splits.
- Avoids hiding FM noise with imputation.

## Consequences
- Fewer but cleaner windows; better external validity.
- Simple to re-run when Withings API backfills FM.

## Open Questions
- Add seasonality covariate (month/DOY) now or later?
- Test 14-day windows only after 7-day baseline is stable.

## Links
- ADR 0001 — Apple Health Router for v0
- Health Auto Export docs (supported data; auto exports)
- Internal notes on daily_facts schema and flags
