# Historical Modeling Development Process

This document preserves the methodology used during initial model development (September 2025) for future reference and replication.

## Development Phases

### Phase 1: Data Preparation (P0)
- **Purpose**: Establish clean, consistent daily data from multiple sources
- **Artifacts**: `p0_staging`, `p0_imputed_intake`
- **Process**: 
  - Raw data ingestion from Withings, MyFitnessPal, TrainingPeaks
  - Daily aggregation and imputation
  - Data quality validation

### Phase 2: Model Development (P1)
- **Purpose**: Develop and validate model parameters
- **Artifacts**: `p1_train_daily`, `p1_test_daily`, `p1_*_windows_flex7`
- **Process**:
  - Train/test split (2021-2024 vs 2025+)
  - 7-day windowing for fat mass change analysis
  - Parameter fitting using TV-L1 denoising
  - Residual analysis and validation

## Key Learnings

### Data Quality Rules
- Fat mass range: 20-60kg (realistic for adult males)
- Intake calories: 500-6000 kcal/day
- Exercise calories: 0-8000 kcal/day
- 7-day windowing optimal for fat mass change analysis

### Starting Parameter Values (Initial Inputs)
- α_fm = 0.25 (fat mass EMA smoothing) - *fitted parameter*
- α_lbm = 0.10 (lean body mass EMA smoothing) - *fitted parameter*
- Energy density: 7,700 kcal/kg - *initial starting input (literature-based)*
- Compensation factor: c = 0.85 (exercise adjustment) - *initial starting input (literature-based)*

### Imputation Strategy
- Day-of-week medians for missing intake
- Zero for missing workouts
- No imputation for fat mass (exclude incomplete windows)

## Replication Instructions

### **Production Data Method (Recommended)**
To replicate using current production data pipeline:

1. **Create Production Splits**: Run `tools/create_production_splits.py`
   - Generates train/test views from `daily_facts` (2021-2024 vs 2025+)
   - Applies split-aware DoW imputation (prevents data leakage)
   - Uses raw fat_mass_kg values (not EMA-smoothed)

2. **Generate Windows**: Run `tools/create_production_windows.py`
   - Creates 7-day rolling windows with eligibility rules
   - Applies outlier filtering identical to P1 methodology
   - Outputs: `prod_train_windows`, `prod_test_windows`

3. **Fit Parameters**: Run `tools/fit_initial_params_production.py`
   - Fits α (energy density), c (compensation), BMR parameters
   - Uses identical methodology to P1 but on production data
   - Outputs: Initial parameter set for `model_params_timevarying`

4. **Validation**: Run `tools/eval_production_params.py`
   - Cross-validation on production test split
   - Compare parameter stability vs P1 results

### **Legacy P0/P1 Method (Historical Reference)**
*Available only if archived P0/P1 tables exist in database*

1. **Data Setup**: Query `p0_staging`, `p1_train_daily`, `p1_test_daily`
2. **Parameter Fitting**: Run `tools/p1_fit_params.py` (legacy)
3. **Validation**: Use `tools/p1_eval.py` (legacy)
4. **Window Analysis**: Query `p1_*_windows_flex7` views

## Migration to Production

The learnings from this development process were incorporated into:
- `model_params_timevarying` table for parameter versioning
- `daily_series_materialized` for computed daily series
- `weekly_coaching_snapshot` for weekly decision making
- Production workflows in `tools/` directory

## Files Preserved for Historical Reference
- `tools/p1_*` - All modeling tools
- `config/p1_params.yaml` - Final parameter values
- `data/p1_test_metrics.json` - Test results
- `docs/adr/0002-modeling-data-prep.md` - Detailed methodology
