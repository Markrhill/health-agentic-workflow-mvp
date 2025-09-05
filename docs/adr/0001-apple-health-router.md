# ADR 0001 — Apple Health as Router for v0

**Status:** Accepted  
**Date:** 2025-09-02

## Context
We need a reliable ingest path now. TrainingPeaks and Garmin APIs are gated and slow to approve. Apple Health + Health Auto Export already consolidates MFP, Withings, Garmin (via iOS Health), etc., and can produce export files we control.

## Decision
Use **Apple Health Auto Export** as the primary ETL router for v0. We will parse the export (zip/folder), normalize 3 data families, and load to Postgres staging → `daily_facts`:
- **Body composition**: weight_kg, fat_mass_kg, lean_mass_kg, hydration_kg, bone_mass_kg
- **Nutrition (daily totals)**: total_calories_kcal, protein_g, carbs_g, fat_g, is_user_entered
- **Workouts (daily)**: workout_kcal, optional tss/if when available

## Rationale
- Fastest path to usable data (hours, not weeks)
- Deterministic and inspectable files (fail gracefully, re-run easily)
- Clear provenance from each source app/device into the router

## Data Path (v0)
Apple Health Auto Export → `healthkit_*` staging tables → `sync_daily_facts_from_health()` → `daily_facts`

## Schema (canonical facts)
`daily_facts(fact_date, intake_kcal, protein_g, carbs_g, fat_g, workout_kcal, weight_kg, fat_mass_kg, lean_mass_kg, hydration_kg, bone_mass_kg, nutrition_is_observed, workout_is_observed, bodycomp_is_observed, source_hint)`

## Guardrails
- Flags (`*_is_observed`) must reflect direct observations vs imputations
- Fat-mass logic uses ΔFM only (7,700 kcal/kg applies to ΔFM, not total weight)
- Unit normalization is explicit; no hidden conversions

## Future
When API access is granted, we'll add direct connectors and adjust authority policy (e.g., Withings > Health for body comp).

## Sources (links you trust)
- HAE supported data page: https://www.healthyapps.dev/supported-data
- HAE Configure Automatic Apple Health Exports: https://www.healthyapps.dev/how-to-configure-automatic-apple-health-exports
- Internal notes on export file shapes & field mapping
