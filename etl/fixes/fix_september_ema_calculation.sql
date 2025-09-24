-- etl/fixes/fix_september_ema_calculation.sql
-- Purpose: Correct the broken EMA calculations in daily_series_materialized
-- Issue: EMA calculations are using wrong alpha values or wrong forward-fill logic
-- Date: 2025-09-22

-- Step 1: Backup current data
CREATE TABLE IF NOT EXISTS daily_series_materialized_backup_20250922 AS
SELECT * FROM daily_series_materialized;

-- Step 2: Fix the materialize_daily_series function
-- The recursive CTE approach is causing issues with EMA calculation
-- Replace with window function approach for reliable forward-fill and EMA

CREATE OR REPLACE FUNCTION materialize_daily_series(
    p_start_date date DEFAULT NULL,
    p_end_date date DEFAULT NULL,
    p_rebuild boolean DEFAULT FALSE
) 
RETURNS TABLE(rows_processed int, status text) AS $$
DECLARE
    v_start_date date;
    v_end_date date;
    v_mode text;
    v_rows int;
    v_run_id text;
BEGIN
    -- Determine processing range if not provided
    IF p_start_date IS NULL THEN
        SELECT start_date, end_date, mode 
        INTO v_start_date, v_end_date, v_mode
        FROM get_materialization_range();
    ELSE
        v_start_date := p_start_date;
        v_end_date := COALESCE(p_end_date, CURRENT_DATE);
        v_mode := 'manual';
    END IF;
    
    -- Generate run ID
    v_run_id := 'run_' || TO_CHAR(NOW(), 'YYYYMMDD_HH24MISS');
    
    -- Log the run
    INSERT INTO etl_run_log (run_id, process_name, start_date, end_date, started_at)
    VALUES (v_run_id, 'materialize_daily_series', v_start_date, v_end_date, NOW());
    
    -- Delete existing data if rebuild or if updating existing dates
    IF p_rebuild OR EXISTS (
        SELECT 1 FROM daily_series_materialized 
        WHERE fact_date BETWEEN v_start_date AND v_end_date
    ) THEN
        DELETE FROM daily_series_materialized 
        WHERE fact_date BETWEEN v_start_date AND v_end_date;
    END IF;
    
    -- Main fix: Replace recursive CTE with proper window functions
    -- Use FIRST_VALUE for forward-fill
    -- Apply EMA formula correctly: prev_ema * (1-α) + value * α
    
    WITH date_spine AS (
        -- Generate all dates in range
        SELECT generate_series(v_start_date, v_end_date, '1 day'::interval)::date AS fact_date
    ),
    
    facts_with_fill AS (
        SELECT 
            ds.fact_date,
            COALESCE(df.intake_kcal, 0) AS intake_kcal,
            COALESCE(df.workout_kcal, 0) AS workout_kcal,
            -- Forward-fill: Use most recent non-null value
            COALESCE(
                df.fat_mass_kg,
                (SELECT fat_mass_kg FROM daily_facts 
                 WHERE fat_mass_kg IS NOT NULL 
                 AND fact_date < ds.fact_date 
                 ORDER BY fact_date DESC LIMIT 1)
            ) AS fat_mass_filled,
            COALESCE(
                df.fat_free_mass_kg,
                (SELECT fat_free_mass_kg FROM daily_facts 
                 WHERE fat_free_mass_kg IS NOT NULL 
                 AND fact_date < ds.fact_date 
                 ORDER BY fact_date DESC LIMIT 1)
            ) AS ffm_filled
        FROM date_spine ds
        LEFT JOIN daily_facts df ON ds.fact_date = df.fact_date
    ),
    
    -- Get parameters for each date
    facts_with_params AS (
        SELECT 
            f.*,
            p.params_version,
            p.alpha_fm,
            p.alpha_lbm,
            p.bmr0_kcal,
            p.k_lbm_kcal_per_kg,
            p.c_exercise_comp
        FROM facts_with_fill f
        LEFT JOIN model_params_timevarying p 
            ON f.fact_date >= p.effective_start_date 
            AND f.fact_date <= COALESCE(p.effective_end_date, '9999-12-31')
    ),
    
    -- Calculate EMAs using proper window functions
    ema_calculated AS (
        SELECT 
            *,
            -- Fat mass EMA: prev_ema * (1-α) + current_value * α
            CASE 
                WHEN ROW_NUMBER() OVER (ORDER BY fact_date) = 1 THEN
                    fat_mass_filled  -- First day: use raw value
                ELSE
                    -- EMA calculation: previous EMA * (1-α) + current * α
                    LAG(
                        fat_mass_filled * alpha_fm + 
                        COALESCE(
                            LAG(fat_mass_filled, 1) OVER (ORDER BY fact_date) * (1 - alpha_fm),
                            0
                        ), 1
                    ) OVER (ORDER BY fact_date) * (1 - alpha_fm) + 
                    fat_mass_filled * alpha_fm
            END AS fat_mass_ema_kg,
            
            -- LBM EMA: same logic
            CASE 
                WHEN ROW_NUMBER() OVER (ORDER BY fact_date) = 1 THEN
                    ffm_filled  -- First day: use raw value
                ELSE
                    LAG(
                        ffm_filled * alpha_lbm + 
                        COALESCE(
                            LAG(ffm_filled, 1) OVER (ORDER BY fact_date) * (1 - alpha_lbm),
                            0
                        ), 1
                    ) OVER (ORDER BY fact_date) * (1 - alpha_lbm) + 
                    ffm_filled * alpha_lbm
            END AS lbm_ema_kg_for_bmr
            
        FROM facts_with_params
    ),
    
    -- Calculate final metrics and insert
    final_insert AS (
        INSERT INTO daily_series_materialized (
            fact_date,
            params_version_used,
            fat_mass_ema_kg,
            lbm_ema_kg_for_bmr,
            bmr_kcal,
            adj_exercise_kcal,
            net_kcal,
            computed_at,
            compute_run_id
        )
        SELECT 
            fact_date,
            params_version,
            ROUND(fat_mass_ema_kg, 3),
            ROUND(lbm_ema_kg_for_bmr, 3),
            ROUND(bmr0_kcal + k_lbm_kcal_per_kg * lbm_ema_kg_for_bmr),
            ROUND((1 - c_exercise_comp) * workout_kcal),
            intake_kcal - ROUND((1 - c_exercise_comp) * workout_kcal) 
                - ROUND(bmr0_kcal + k_lbm_kcal_per_kg * lbm_ema_kg_for_bmr),
            NOW(),
            v_run_id
        FROM ema_calculated
        ORDER BY fact_date
        RETURNING 1
    )
    SELECT COUNT(*) INTO v_rows FROM final_insert;
    
    -- Update log
    UPDATE etl_run_log 
    SET 
        completed_at = NOW(),
        rows_processed = v_rows,
        status = 'SUCCESS'
    WHERE run_id = v_run_id;
    
    RETURN QUERY SELECT v_rows, 'SUCCESS: ' || v_mode;
    
EXCEPTION WHEN OTHERS THEN
    -- Log failure
    UPDATE etl_run_log 
    SET 
        completed_at = NOW(),
        status = 'FAILED',
        error_message = SQLERRM
    WHERE run_id = v_run_id;
    
    RETURN QUERY SELECT 0, 'FAILED: ' || SQLERRM;
END;
$$ LANGUAGE plpgsql;

-- Step 3: Recalculate September data
SELECT * FROM materialize_daily_series('2025-09-01', '2025-09-22', true);

-- Step 4: Verify the fix
SELECT 
    fact_date,
    fat_mass_ema_kg,
    LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date) as prev_ema,
    fat_mass_ema_kg - LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date) as delta
FROM daily_series_materialized
WHERE fact_date BETWEEN '2025-09-09' AND '2025-09-20'
ORDER BY fact_date;
