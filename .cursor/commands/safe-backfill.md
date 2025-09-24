# Safe Data Pipeline Operations

## Pre-Processing Checklist

Before any batch data processing operations:

### 1. Test on Single Week First
Always validate computations on a single week before running batch operations.

```sql
-- Test EMA calculation for one week only
SELECT fact_date, fat_mass_kg, 
       AVG(fat_mass_kg) OVER (ORDER BY fact_date ROWS BETWEEN 3 PRECEDING AND CURRENT ROW) as test_ema
FROM daily_facts 
WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
ORDER BY fact_date;
```

### 2. Validate Intermediate Results
- Compare against known values from previous runs
- Verify parameter calculations match expected formulas
- Check data quality constraints are met

### 3. Use Transactions for Rollback Capability
```sql
BEGIN;

-- Your batch operation here
UPDATE daily_facts 
SET fat_mass_ema = calculated_value
WHERE fact_date BETWEEN '2025-01-01' AND '2025-12-31';

-- Verify results before committing
SELECT COUNT(*) as updated_rows FROM daily_facts WHERE fat_mass_ema IS NOT NULL;

-- If results look good:
COMMIT;
-- If issues found:
-- ROLLBACK;
```

### 4. Log First 5 Records for Manual Verification
```sql
-- Always log sample results for verification
SELECT fact_date, fat_mass_kg, fat_mass_ema, 
       ROUND(fat_mass_ema, 3) as ema_rounded
FROM daily_facts 
WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
ORDER BY fact_date
LIMIT 5;
```

## Project-Specific Parameters

Reference: @CONTEXT.md for critical parameters:
- **αFM = 0.25** (fat mass exponential smoothing)
- **αLBM = 0.10** (lean body mass exponential smoothing)
- **Energy Density**: 7,700 kcal/kg conversion factor
- **Compensation Factor**: (1-c) for exercise calories

## Data Quality Validation

### Fat Mass Constraints
```sql
-- Validate fat mass range (20-60kg)
SELECT COUNT(*) as invalid_fm_count
FROM daily_facts 
WHERE fat_mass_kg < 20 OR fat_mass_kg > 60;
```

### Intake Validation
```sql
-- Validate intake range (500-6000 kcal/day)
SELECT COUNT(*) as invalid_intake_count
FROM daily_facts 
WHERE intake_kcal < 500 OR intake_kcal > 6000;
```

### Imputation Consistency
```sql
-- Check imputation flags are consistent
SELECT 
    imputation_method,
    COUNT(*) as count,
    COUNT(CASE WHEN intake_is_imputed = true THEN 1 END) as imputed_count
FROM daily_facts 
GROUP BY imputation_method;
```

## Common Backfill Patterns

### EMA Calculation
```sql
-- Fat Mass EMA (α=0.25)
WITH ema_calc AS (
    SELECT 
        fact_date,
        fat_mass_kg,
        LAG(fat_mass_ema, 1) OVER (ORDER BY fact_date) as prev_ema,
        CASE 
            WHEN LAG(fat_mass_ema, 1) OVER (ORDER BY fact_date) IS NULL 
            THEN fat_mass_kg
            ELSE 0.25 * fat_mass_kg + 0.75 * LAG(fat_mass_ema, 1) OVER (ORDER BY fact_date)
        END as new_ema
    FROM daily_facts
    WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
)
SELECT * FROM ema_calc ORDER BY fact_date;
```

### Net Energy Calculation
```sql
-- Net kcal = intake_kcal - (1-c)*workout_kcal - (bmr0 + k_lbm*lbm_ema)
SELECT 
    fact_date,
    intake_kcal,
    workout_kcal,
    bmr0,
    k_lbm,
    lbm_ema,
    c as compensation_factor,
    intake_kcal - (1-c)*workout_kcal - (bmr0 + k_lbm*lbm_ema) as net_kcal
FROM daily_facts 
WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
ORDER BY fact_date;
```

### 7-Day Window Validation
```sql
-- Check 7-day window eligibility
SELECT 
    fact_date,
    fat_mass_kg,
    LAG(fat_mass_kg, 7) OVER (ORDER BY fact_date) as fm_7d_ago,
    CASE 
        WHEN LAG(fat_mass_kg, 7) OVER (ORDER BY fact_date) IS NOT NULL 
        THEN 'eligible'
        ELSE 'ineligible'
    END as window_status
FROM daily_facts 
WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
ORDER BY fact_date;
```

## Safety Protocols

### Before Batch Operations
1. ✅ Test on single week (2025-01-06 to 2025-01-12)
2. ✅ Validate parameters against CONTEXT.md
3. ✅ Check data quality constraints
4. ✅ Use transaction wrapper
5. ✅ Log sample results for verification

### During Batch Operations
- Monitor row counts and processing time
- Check for constraint violations
- Verify calculation accuracy on sample data
- Log progress for long-running operations

### After Batch Operations
- Validate final row counts match expectations
- Check for data quality issues
- Verify parameter consistency
- Document any issues or adjustments made

## Emergency Procedures

If backfill operations fail:
1. **STOP** - Don't run additional operations
2. Check transaction status
3. Review error logs
4. Consider rolling back if necessary
5. Document the failure and resolution

## Health-Specific Data Pipeline Operations

### Parameter Version Validation
Always query current parameters from model_params_timevarying:
```sql
-- Get current parameters before any calculation
SELECT effective_date, c, alpha_fm, alpha_lbm, kcal_per_kg_fat
FROM model_params_timevarying 
WHERE effective_date <= CURRENT_DATE
ORDER BY effective_date DESC 
LIMIT 1;
```

Never hardcode parameter values in calculations. Always JOIN with model_params_timevarying table.

This approach:
- **Removes temptation** to use hardcoded values
- **Forces** the AI to query the parameter table
- **Eliminates confusion** about which values to use
- **Enforces** the versioned parameter architecture

The factory pattern should make correct behavior easier than incorrect behavior. Listing specific values (even with warnings) creates cognitive load and potential for copy-paste errors.

### EMA Calculation Protocol
Before any exponential moving average computation:
```sql
-- Test EMA on single week first (fact_date 2025-01-06 to 2025-01-12)
WITH current_params AS (
    SELECT c, alpha_fm, alpha_lbm, kcal_per_kg_fat
    FROM model_params_timevarying 
    WHERE effective_date <= CURRENT_DATE
    ORDER BY effective_date DESC 
    LIMIT 1
),
test_week AS (
    SELECT fact_date, fat_mass_kg, lbm_kg
    FROM daily_facts 
    WHERE fact_date BETWEEN '2025-01-06' AND '2025-01-12'
    ORDER BY fact_date
),
ema_test AS (
    SELECT fact_date,
           fat_mass_kg,
           p.alpha_fm * fat_mass_kg + (1 - p.alpha_fm) * LAG(fat_mass_kg, 1, fat_mass_kg) OVER (ORDER BY fact_date) as fat_mass_ema_test
    FROM test_week
    CROSS JOIN current_params p
)
SELECT * FROM ema_test;
```
Verify first 3 records manually before proceeding to full dataset.

### Batch Processing Safety
Process in monthly chunks, never full YTD at once:
```sql
-- Process January only first
INSERT INTO daily_series_materialized (
    fact_date, fat_mass_ema_kg, lbm_ema_kg_for_bmr, 
    bmr_kcal, adj_exercise_kcal, net_kcal,
    params_version_used, computed_at
)
SELECT 
    df.fact_date,
    -- EMA calculations using JOIN to parameter table
    -- Net energy: intake_kcal - (1-mp.c)*workout_kcal - bmr_kcal
    df.intake_kcal - (1 - mp.c) * df.workout_kcal - (mp.bmr0_kcal + mp.k_lbm_kcal_per_kg * df.lbm_ema_kg) as net_kcal,
    mp.version_id,
    NOW()
FROM daily_facts df
JOIN model_params_timevarying mp ON mp.effective_date <= df.fact_date
WHERE df.fact_date BETWEEN '2025-01-01' AND '2025-01-31'
ORDER BY df.fact_date;
```
Test January before processing February.

### Emergency Rollback
```sql
-- If computation fails, clean up partial results
DELETE FROM daily_series_materialized 
WHERE computed_at >= '[start_timestamp]'
AND params_version_used = '[current_version]';
```
Always wrap batch operations in transactions with rollback capability.

## References

- **Project Context**: @CONTEXT.md
- **Failure Patterns**: @.cursor/failure-patterns.md
- **Schema Validation**: `schema.manifest.yaml`
- **Migration Files**: `sql/migrations/`
