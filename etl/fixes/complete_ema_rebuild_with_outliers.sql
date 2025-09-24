-- etl/fixes/complete_ema_rebuild_with_outliers.sql
-- Purpose: Complete rebuild of EMAs from 2021-2025 with outlier detection
-- Handles data entry errors and scale malfunctions by excluding extreme values

-- Step 1: Backup current data
CREATE TABLE IF NOT EXISTS daily_series_backup_with_outliers AS
SELECT * FROM daily_series_materialized;

-- Step 2: Identify and log outliers
CREATE TEMP TABLE identified_outliers AS
SELECT 
    fact_date,
    fat_mass_kg,
    CASE 
        -- Flag values outside physiological range or with impossible jumps
        WHEN fat_mass_kg > 30 THEN TRUE  -- Above 30kg is impossible for your profile
        WHEN fat_mass_kg < 15 THEN TRUE  -- Below 15kg is impossible
        WHEN ABS(fat_mass_kg - LAG(fat_mass_kg) OVER (ORDER BY fact_date)) > 5 THEN TRUE  -- >5kg daily change
        WHEN ABS(fat_mass_kg - LEAD(fat_mass_kg) OVER (ORDER BY fact_date)) > 5 THEN TRUE
        ELSE FALSE
    END as is_outlier
FROM daily_facts
WHERE fat_mass_kg IS NOT NULL;

-- Log outliers found
INSERT INTO etl_run_log (run_id, process_name, started_at, status, error_message)
SELECT 
    'outliers_' || TO_CHAR(NOW(), 'YYYYMMDD_HH24MISS'),
    'outlier_detection',
    NOW(),
    'INFO',
    'Found ' || COUNT(*) || ' outliers: ' || STRING_AGG(fact_date::text || '=' || fat_mass_kg::text, ', ')
FROM identified_outliers
WHERE is_outlier;

-- Step 3: Complete rebuild excluding outliers
UPDATE daily_series_materialized dsm
SET 
    fat_mass_ema_kg = subq.correct_fat_ema,
    lbm_ema_kg_for_bmr = subq.correct_lbm_ema,
    bmr_kcal = ROUND(subq.bmr0 + subq.k_lbm * subq.correct_lbm_ema),
    adj_exercise_kcal = ROUND((1 - subq.c_comp) * subq.workout),
    net_kcal = subq.intake - ROUND((1 - subq.c_comp) * subq.workout) - ROUND(subq.bmr0 + subq.k_lbm * subq.correct_lbm_ema),
    computed_at = NOW(),
    compute_run_id = 'rebuild_no_outliers_' || TO_CHAR(NOW(), 'YYYYMMDD_HH24MISS')
FROM (
    WITH RECURSIVE ema_fix AS (
        -- Day 1: Initialize with actual measurements
        SELECT 
            '2021-01-01'::date as fact_date,
            20.956::numeric as correct_fat_ema,
            73.437::numeric as correct_lbm_ema,
            COALESCE(df.intake_kcal, 0)::numeric as intake,
            COALESCE(df.workout_kcal, 0)::numeric as workout,
            p.bmr0_kcal::numeric as bmr0,
            p.k_lbm_kcal_per_kg::numeric as k_lbm,
            p.c_exercise_comp::numeric as c_comp
        FROM daily_facts df
        LEFT JOIN model_params_timevarying p 
            ON '2021-01-01' >= p.effective_start_date 
            AND '2021-01-01' <= COALESCE(p.effective_end_date, '9999-12-31')
        WHERE df.fact_date = '2021-01-01'
        
        UNION ALL
        
        -- Subsequent days with outlier handling
        SELECT 
            dates.fact_date,
            ROUND(
                prev.correct_fat_ema * (1 - p.alpha_fm) + 
                COALESCE(
                    -- Exclude outliers by treating them as NULL
                    CASE 
                        WHEN io.is_outlier THEN NULL 
                        ELSE df.fat_mass_kg 
                    END,
                    -- Forward-fill from last valid non-outlier value
                    (SELECT fat_mass_kg 
                     FROM daily_facts df2
                     LEFT JOIN identified_outliers io2 ON df2.fact_date = io2.fact_date
                     WHERE df2.fat_mass_kg IS NOT NULL 
                       AND df2.fact_date < dates.fact_date
                       AND (io2.is_outlier IS NULL OR io2.is_outlier = FALSE)
                     ORDER BY df2.fact_date DESC 
                     LIMIT 1),
                    prev.correct_fat_ema
                ) * p.alpha_fm,
                3
            )::numeric as correct_fat_ema,
            ROUND(
                prev.correct_lbm_ema * (1 - p.alpha_lbm) + 
                COALESCE(
                    df.fat_free_mass_kg,
                    (SELECT fat_free_mass_kg FROM daily_facts 
                     WHERE fat_free_mass_kg IS NOT NULL AND fact_date < dates.fact_date 
                     ORDER BY fact_date DESC LIMIT 1),
                    prev.correct_lbm_ema
                ) * p.alpha_lbm,
                3
            )::numeric as correct_lbm_ema,
            COALESCE(df.intake_kcal, 0)::numeric as intake,
            COALESCE(df.workout_kcal, 0)::numeric as workout,
            p.bmr0_kcal::numeric as bmr0,
            p.k_lbm_kcal_per_kg::numeric as k_lbm,
            p.c_exercise_comp::numeric as c_comp
        FROM (
            SELECT generate_series('2021-01-02'::date, CURRENT_DATE, '1 day'::interval)::date as fact_date
        ) dates
        INNER JOIN ema_fix prev ON dates.fact_date = (prev.fact_date + INTERVAL '1 day')::date
        LEFT JOIN daily_facts df ON dates.fact_date = df.fact_date
        LEFT JOIN identified_outliers io ON dates.fact_date = io.fact_date
        LEFT JOIN model_params_timevarying p 
            ON dates.fact_date >= p.effective_start_date 
            AND dates.fact_date <= COALESCE(p.effective_end_date, '9999-12-31')
    )
    SELECT * FROM ema_fix
) subq
WHERE dsm.fact_date = subq.fact_date;

-- Step 4: Verification report
SELECT 
    'REBUILD COMPLETE' as status,
    COUNT(*) as rows_updated,
    MIN(fat_mass_ema_kg) as min_ema,
    MAX(fat_mass_ema_kg) as max_ema,
    ROUND(AVG(fat_mass_ema_kg), 2) as avg_ema,
    ROUND(STDDEV(fat_mass_ema_kg), 2) as stddev_ema
FROM daily_series_materialized;

-- Step 5: Show excluded outliers
SELECT 
    'OUTLIERS EXCLUDED' as report,
    fact_date,
    fat_mass_kg as outlier_value
FROM identified_outliers
WHERE is_outlier
ORDER BY fact_date;

-- Step 6: Verify no large jumps remain
SELECT 
    'LARGEST REMAINING JUMPS' as report,
    fact_date,
    fat_mass_ema_kg,
    ROUND(fat_mass_ema_kg - LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date), 2) as daily_change
FROM daily_series_materialized
WHERE ABS(fat_mass_ema_kg - LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date)) > 0.5
ORDER BY ABS(fat_mass_ema_kg - LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date)) DESC
LIMIT 5;
