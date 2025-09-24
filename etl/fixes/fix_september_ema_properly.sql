-- etl/fixes/fix_september_ema_properly.sql
-- Purpose: Correctly fix the broken EMA calculations for September 2025
-- Problem: EMA is jumping to forward-filled values instead of smoothing toward them
-- Solution: Recalculate EMAs with proper formula: prev * 0.75 + current * 0.25

-- Step 1: Backup current data before fix
CREATE TABLE IF NOT EXISTS daily_series_backup_sep_fix AS
SELECT * FROM daily_series_materialized 
WHERE fact_date BETWEEN '2025-09-01' AND '2025-09-22';

-- Step 2: Fix September EMAs with proper calculation
UPDATE daily_series_materialized dsm
SET 
    fat_mass_ema_kg = subq.correct_fat_ema,
    lbm_ema_kg_for_bmr = subq.correct_lbm_ema,
    bmr_kcal = ROUND(subq.bmr0 + subq.k_lbm * subq.correct_lbm_ema),
    net_kcal = subq.intake - ROUND((1 - subq.c_comp) * subq.workout) - ROUND(subq.bmr0 + subq.k_lbm * subq.correct_lbm_ema),
    computed_at = NOW(),
    compute_run_id = 'fix_sep_ema_' || TO_CHAR(NOW(), 'YYYYMMDD_HH24MISS')
FROM (
    WITH RECURSIVE ema_fix AS (
        -- Base case: Start from last known good value (Sep 10)
        SELECT 
            dsm.fact_date,
            dsm.fat_mass_ema_kg::numeric as correct_fat_ema,
            dsm.lbm_ema_kg_for_bmr::numeric as correct_lbm_ema,
            0::numeric as intake,
            0::numeric as workout,
            0::numeric as bmr0,
            0::numeric as k_lbm,
            0::numeric as c_comp
        FROM daily_series_materialized dsm
        WHERE fact_date = '2025-09-10'
        
        UNION ALL
        
        -- Recursive case: Calculate each subsequent day properly
        SELECT 
            dates.fact_date,
            -- Fat mass EMA: prev * (1-alpha_fm) + current * alpha_fm
            ROUND(
                prev.correct_fat_ema * 0.75 + 
                COALESCE(
                    df.fat_mass_kg,
                    (SELECT fat_mass_kg FROM daily_facts 
                     WHERE fat_mass_kg IS NOT NULL AND fact_date < dates.fact_date 
                     ORDER BY fact_date DESC LIMIT 1)
                ) * 0.25,
                3
            ) as correct_fat_ema,
            -- LBM EMA: prev * (1-alpha_lbm) + current * alpha_lbm  
            ROUND(
                prev.correct_lbm_ema * 0.90 + 
                COALESCE(
                    df.fat_free_mass_kg,
                    (SELECT fat_free_mass_kg FROM daily_facts 
                     WHERE fat_free_mass_kg IS NOT NULL AND fact_date < dates.fact_date 
                     ORDER BY fact_date DESC LIMIT 1)
                ) * 0.10,
                3
            ) as correct_lbm_ema,
            COALESCE(df.intake_kcal, 0) as intake,
            COALESCE(df.workout_kcal, 0) as workout,
            p.bmr0_kcal as bmr0,
            p.k_lbm_kcal_per_kg as k_lbm,
            p.c_exercise_comp as c_comp
        FROM (
            SELECT generate_series('2025-09-11'::date, '2025-09-22'::date, '1 day'::interval)::date as fact_date
        ) dates
        INNER JOIN ema_fix prev ON dates.fact_date = prev.fact_date + INTERVAL '1 day'
        LEFT JOIN daily_facts df ON dates.fact_date = df.fact_date
        LEFT JOIN model_params_timevarying p 
            ON dates.fact_date >= p.effective_start_date 
            AND dates.fact_date <= COALESCE(p.effective_end_date, '9999-12-31')
    )
    SELECT * FROM ema_fix WHERE fact_date > '2025-09-10'
) subq
WHERE dsm.fact_date = subq.fact_date
  AND dsm.fact_date BETWEEN '2025-09-11' AND '2025-09-22';

-- Step 3: Verify the fix worked
SELECT 
    dsm.fact_date,
    df.fat_mass_kg as actual,
    dsm.fat_mass_ema_kg as fixed_ema,
    LAG(dsm.fat_mass_ema_kg) OVER (ORDER BY dsm.fact_date) as prev_ema,
    ROUND(dsm.fat_mass_ema_kg - LAG(dsm.fat_mass_ema_kg) OVER (ORDER BY dsm.fact_date), 3) as daily_change
FROM daily_series_materialized dsm
LEFT JOIN daily_facts df ON dsm.fact_date = df.fact_date
WHERE dsm.fact_date BETWEEN '2025-09-10' AND '2025-09-22'
ORDER BY dsm.fact_date;
