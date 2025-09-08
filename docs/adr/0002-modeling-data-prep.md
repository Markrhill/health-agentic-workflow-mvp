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

## Addendum — Data QA Outcomes (2025-09-04)

- Training rows: 1,461  
- Intake NULLs: 8 (0.5%), imputed with DoW means  
- Workout NULLs: 0 (treated as 0 kcal by rule)  
- Fat mass: no imputation; 319 missing days simply excluded  
- Unresolved gaps: 0  
- Conclusion: negligible risk of material error from imputations.

## Addendum — Flex Window Results (2025-09-04)

**Goal.** Maximize usable ΔFM windows while keeping a weekly cadence. We allow the **END** to “snap” to the next observed FM day within 7–9 days of the **START** (START and END must both have observed `fat_mass_kg`). Intake gaps are imputed by DoW rule; missing workouts count as 0.

**Artifacts**
- View: `p1_train_windows_flex7`
- Columns: `start_date, end_date, days, fm_start, fm_end, delta_fm_kg, intake_kcal_sum, workout_kcal_sum, net_kcal_sum, is_7d, is_8d, is_9d`

**Train-set coverage (2021‑01‑01 … 2024‑12‑31)**
- Total eligible windows: **969**
  - Exact 7‑day: **866**
  - 8‑day (snapped): **60**
  - 9‑day (snapped): **43**

**Decision**
- Use **flex 7–9 day** windows for modeling, labeled by `is_7d/8d/9d`.
- Report primary results on **7‑day** subset; use 8/9‑day for robustness only.
- Exclude any window that contains an FM outlier day per the ADR rule (MAD‑based) or lacks observed FM at START/END.

**Why**
- Lifts usable windows vs strict 7‑day without smearing FM with interpolation.
- Preserves interpretability of “about a week” while handling 1–2‑day FM gaps.

**Pre‑model checklist**
- `SELECT COUNT(*) FROM p1_train_windows_flex7;` → **969**
- `SELECT MIN(days), MAX(days) FROM p1_train_windows_flex7;` → **7, 9**
- Confirm no test‑period dates appear in the train view.
- Quick sanity: `SELECT percentile_disc(ARRAY[0.1,0.5,0.9]) WITHIN GROUP (ORDER BY net_kcal_sum) FROM p1_train_windows_flex7 WHERE is_7d;` to ensure plausible energy ranges.

## Appendix — SQL Artifacts & Provenance (p0→p1)

**Source table**
- `p0_staging(fact_date, intake_kcal, workout_kcal, weight_kg, fat_mass_kg, lean_mass_kg)`
  - Units: kcal for energy; kg for mass. One row per calendar day.
  - Provenance: 2021–2025 spreadsheet export (“p0_staging.csv”) after cleaning thousand-separators.

**Train/Test split views**
- `p1_train_daily`: 2021-01-01 … 2024-12-31
- `p1_test_daily`:  2025-01-01 … 2025-08-04

**Imputation rule (applied per split)**
- Intake: if NULL ⇒ DoW mean (from observed days of the same split).
- Workout: if NULL ⇒ 0.
- Fat mass: **never imputed** for modeling windows.

**Window view (train)**
- `p1_train_windows_flex7` (columns: start_date, end_date, days, fm_start, fm_end, delta_fm_kg, intake_kcal_sum, workout_kcal_sum, net_kcal_sum, is_7d, is_8d, is_9d)
- Eligibility: START/END must have observed `fat_mass_kg`; window length 7–9 days; intake/workout present (intake may be imputed, workout may be 0); FM outliers excluded per ADR-0002.

**Counts (as executed)**
- Train rows: 1,461; Intake NULLs imputed: 8; Workout NULLs: 0; FM missing days: 319.
- Flex windows (train): total 969 (7-day: 866; 8-day: 60; 9-day: 43).

> Re-run procedure: `psql -f sql/020_p1_split_impute.sql && psql -f sql/030_p1_windows_flex7.sql`

