# ADR 0001 — Apple Health as Router for v0

**Status:** Superseded  
**Date:** 2025-09-02  
**Superseded:** 2025-09-24 (Implementation completed)

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

## Data Path (v0) - IMPLEMENTED
Apple Health Auto Export → `hae_raw` → `hae_metrics_parsed` → `daily_facts`

**Implementation Details:**
- **Script**: `etl/hae_import.py`
- **Raw Storage**: `hae_raw` table stores complete JSON exports
- **Parsed Data**: `hae_metrics_parsed` table stores normalized metrics by date
- **Sync Process**: Direct INSERT/UPDATE to `daily_facts` (lines 196-217 in hae_import.py)

## Schema (canonical facts) - IMPLEMENTED
`daily_facts(fact_date, intake_kcal, protein_g, carbs_g, fat_g, fiber_g, workout_kcal, weight_kg, fat_mass_kg, fat_free_mass_kg, muscle_mass_kg, hydration_kg, bone_mass_kg, intake_is_imputed, imputation_method, nutrition_is_observed)`

**Key Changes from Original:**
- ✅ Added `fiber_g` for nutrition tracking
- ✅ Added `fat_free_mass_kg` and `muscle_mass_kg` for body composition
- ✅ Added `intake_is_imputed` and `imputation_method` for data quality tracking
- ✅ Simplified schema (removed unused fields like `source_hint`)

## Guardrails
- Flags (`*_is_observed`) must reflect direct observations vs imputations
- Fat-mass logic uses ΔFM only (7,700 kcal/kg applies to ΔFM, not total weight)
- Unit normalization is explicit; no hidden conversions

## Implementation Status
✅ **COMPLETED** - HAE integration fully implemented and operational

**Production Usage:**
```bash
python etl/hae_import.py /path/to/HealthAutoExport-YYYY-MM-DD.json
```

**Data Quality:**
- ✅ Handles missing fiber data gracefully (HAE limitation)
- ✅ Validates critical fields during import
- ✅ Supports multiple overwrite modes (update_nulls, overwrite, skip_existing)
- ✅ Complete audit trail via `hae_raw` and `hae_metrics_parsed` tables

## Future
When API access is granted, we'll add direct connectors and adjust authority policy (e.g., Withings > Health for body comp).

## Sources (links you trust)
- HAE supported data page: https://www.healthyapps.dev/supported-data
- HAE Configure Automatic Apple Health Exports: https://www.healthyapps.dev/how-to-configure-automatic-apple-health-exports
- Internal notes on export file shapes & field mapping
