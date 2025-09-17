# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2025-09-16
### Added
- Tables: performance_goals, model_params_timevarying, daily_series_materialized, weekly_coaching_snapshot, audit_hil
- View: facts_intake_dow_medians (day-of-week intake imputation support)
- Contract: imputation_flag_consistency (ensures method present when intake is imputed)
- Contract: weekly_snapshot_coverage (validates min 6 days present per week)

### Changed
- daily_facts semantic range: fat_mass_kg from 10-40kg to 20-60kg (more realistic for adult males)
- p0/p1 modeling artifacts: marked as one_time_analysis (excluded from daily workflows)
- Enhanced schema descriptions with clearer formulas and terminology

### Fixed
- YAML syntax issues with square brackets in descriptions
- Duplicate column definitions in daily_facts

### Notes
- Schema validation shows expected missing objects (not yet migrated to DB)
- Net kcal formula: `intake_kcal - (1-c)*workout_kcal - (bmr0 + k_lbm*lbm_ema)`
