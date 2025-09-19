# Health Agentic Workflow MVP - Project Context

## Factory Rules (Always Apply)
- All table changes must validate against schema.manifest.yaml first
- Test computations on single week before batch operations  
- Parameter changes require versioning and full recomputation
- Schema evolution requires ADR documentation

## Architecture Overview
- **Versioned Parameters**: All model parameters (α_fm, α_lbm, c, BMR) stored in `model_params_timevarying` with effective dates for reproducible calculations
- **Materialized Daily Series**: Pre-computed daily series (`daily_series_materialized`) for fast UI queries and immutable weekly snapshots
- **Human-in-the-Loop**: Weekly coaching decisions stored in immutable `weekly_coaching_snapshot` with full audit trail in `audit_hil`
- **Multi-source Integration**: Withings (body composition), MyFitnessPal (nutrition), TrainingPeaks (exercise) data unified in `daily_facts`

## Database Schema
- **Core Surface**: `daily_facts` as authoritative daily health metrics with imputation tracking (`intake_is_imputed`, `imputation_method`)
- **Parameter Versioning**: `model_params_timevarying` with effective-dated parameters and foreign key relationships
- **Weekly Snapshots**: `weekly_coaching_snapshot` with analytics fields (prediction accuracy, goal progress, data quality scores)
- **Goal Management**: `performance_goals` with W/kg calculations and TSS ramp plans
- **Data Quality**: Contracts enforce imputation consistency and goal progress validation

## Data Processing Pipeline
- **Fixed Train/Test Split**: 2021-2024 training, 2025+ testing with explicit imputation rules
- **7-Day Windowing**: Primary window length for ΔFM calculations with strict eligibility rules (observed start/end FM)
- **Imputation Strategy**: Day-of-week medians for intake, zero for missing workouts, no imputation for fat mass
- **Outlier Detection**: 2.5×MAD rule for fat mass outliers with window exclusion flags
- **Net Energy Formula**: `net_kcal = intake_kcal - (1-c)*workout_kcal - (bmr0 + k_lbm*lbm_ema)`

## Critical Business Logic
- **BIA Measurement Handling**: Withings scale data requires first-of-day selection and validation before use in modeling
- **Exponential Smoothing**: Fat mass and lean body mass coefficients (stored in model_params_timevarying.alpha_fm and model_params_timevarying.alpha_lbm)
- **Energy Density**: kcal/kg conversion factor for fat mass changes only (stored in model_params_timevarying.kcal_per_kg_fat)
- **Compensation Factor**: Exercise calories adjusted by (1-c) where c is the compensation factor [0,1] (stored in model_params_timevarying.c)
- **Unit Discipline**: All mass in kg, energy in kcal, strict conversion rules

## Known Issues & Constraints
- **Schema Validation**: Some objects missing from database (expected until migrations run)
- **Data Quality**: Fat mass range 20-60kg enforced, intake 500-6000 kcal/day validation
- **Imputation Transparency**: UI must show asterisk (*) when intake was imputed with tooltip showing DoW median source
- **Parameter Changes**: Require new version and full recomputation to maintain historical consistency
- **Window Eligibility**: Strict rules prevent modeling on incomplete or outlier-contaminated data

## AI System Guidance
**CRITICAL**: Do not reference deprecated P0/P1 artifacts (p0_staging, p1_train_daily, etc.). 
These were one-time development artifacts. Always use current canonical sources:
- `daily_facts` for daily health metrics
- `model_params_timevarying` for parameters
- `daily_series_materialized` for computed series
- `weekly_coaching_snapshot` for weekly decisions

See `docs/DEPRECATED.md` for complete list of deprecated artifacts.
