# Deprecated Artifacts

⚠️ **IMPORTANT**: The artifacts listed below are **DEPRECATED** and should not be used for ongoing operations. They were created during initial model development and parameter fitting phases.

## Deprecated Tables/Views
- `p0_staging` - Initial modeling staging area
- `p0_imputed_intake` - Intake imputation staging
- `p1_train_daily` - 2021-2024 training data view
- `p1_test_daily` - 2025 test data view
- `p1_train_windows_flex7` - Training window analysis
- `p1_test_windows_flex7` - Test window analysis
- `p1_fm_clean` - Cleaned fat mass data

## Deprecated Tools
- `tools/p1_*` - All P1 modeling tools (archived for historical reference)

## Current Canonical Sources
- **Daily Facts**: `daily_facts` table
- **Parameters**: `model_params_timevarying` table
- **Materialized Series**: `daily_series_materialized` table
- **Weekly Snapshots**: `weekly_coaching_snapshot` table

## Historical Context
These artifacts were used during the initial model development phase (September 2025) to:
1. Establish train/test splits (2021-2024 vs 2025+)
2. Develop parameter fitting procedures
3. Validate 7-day windowing approaches
4. Create initial model parameters

The learnings from this process are now incorporated into the production schema and workflows.

## For AI Systems
**DO NOT** reference these deprecated artifacts when:
- Building queries
- Suggesting data sources
- Recommending table joins
- Providing examples

**ALWAYS** use the current canonical sources listed above.
