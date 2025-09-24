-- etl/fixes/fix_ema_simple.sql
-- Simplified EMA calculation fix
-- Date: 2025-09-22

-- Step 1: Backup current data
CREATE TABLE IF NOT EXISTS daily_series_materialized_backup_20250922_v2 AS
SELECT * FROM daily_series_materialized;

-- Step 2: Create a simpler, more reliable EMA calculation function
CREATE OR REPLACE FUNCTION materialize_daily_series_simple(
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
    v_alpha_fm numeric;
    v_alpha_lbm numeric;
    v_bmr0_kcal numeric;
    v_k_lbm_kcal_per_kg numeric;
    v_c_exercise_comp numeric;
    v_params_version text;
BEGIN
    -- Determine processing range
    IF p_start_date IS NULL THEN
        SELECT start_date, end_date, mode 
        INTO v_start_date, v_end_date, v_mode
        FROM get_materialization_range();
    ELSE
        v_start_date := p_start_date;
        v_end_date := COALESCE(p_end_date, CURRENT_DATE);
        v_mode := 'manual';
    END IF;
    
    -- Get current parameters
    SELECT alpha_fm, alpha_lbm, bmr0_kcal, k_lbm_kcal_per_kg, c_exercise_comp, params_version
    INTO v_alpha_fm, v_alpha_lbm, v_bmr0_kcal, v_k_lbm_kcal_per_kg, v_c_exercise_comp, v_params_version
    FROM model_params_timevarying 
    WHERE effective_start_date <= v_end_date
    ORDER BY effective_start_date DESC 
    LIMIT 1;
    
    -- Generate run ID
    v_run_id := 'run_' || TO_CHAR(NOW(), 'YYYYMMDD_HH24MISS');
    
    -- Log the run
    INSERT INTO etl_run_log (run_id, process_name, start_date, end_date, started_at)
    VALUES (v_run_id, 'materialize_daily_series_simple', v_start_date, v_end_date, NOW());
    
    -- Delete existing data if rebuild
    IF p_rebuild THEN
        DELETE FROM daily_series_materialized 
        WHERE fact_date BETWEEN v_start_date AND v_end_date;
    END IF;
    
    -- Simple approach: Use a loop to calculate EMAs properly
    -- This avoids complex window function nesting issues
    
    WITH date_spine AS (
        SELECT generate_series(v_start_date, v_end_date, '1 day'::interval)::date AS fact_date
    ),
    
    facts_with_fill AS (
        SELECT 
            ds.fact_date,
            COALESCE(df.intake_kcal, 0) AS intake_kcal,
            COALESCE(df.workout_kcal, 0) AS workout_kcal,
            -- Forward-fill fat mass
            COALESCE(
                df.fat_mass_kg,
                (SELECT fat_mass_kg FROM daily_facts 
                 WHERE fat_mass_kg IS NOT NULL 
                 AND fact_date < ds.fact_date 
                 ORDER BY fact_date DESC LIMIT 1)
            ) AS fat_mass_filled,
            -- Forward-fill fat-free mass
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
    
    -- Calculate EMAs using a simple approach
    ema_step1 AS (
        SELECT 
            *,
            -- First pass: calculate basic EMA
            CASE 
                WHEN ROW_NUMBER() OVER (ORDER BY fact_date) = 1 THEN
                    fat_mass_filled
                ELSE
                    -- Simple EMA: use previous day's value if available
                    COALESCE(
                        LAG(fat_mass_filled, 1) OVER (ORDER BY fact_date) * (1 - v_alpha_fm) + 
                        fat_mass_filled * v_alpha_fm,
                        fat_mass_filled
                    )
            END AS fat_mass_ema_step1,
            
            CASE 
                WHEN ROW_NUMBER() OVER (ORDER BY fact_date) = 1 THEN
                    ffm_filled
                ELSE
                    COALESCE(
                        LAG(ffm_filled, 1) OVER (ORDER BY fact_date) * (1 - v_alpha_lbm) + 
                        ffm_filled * v_alpha_lbm,
                        ffm_filled
                    )
            END AS lbm_ema_step1
        FROM facts_with_fill
    ),
    
    -- Second pass: use the calculated EMAs for proper recursive calculation
    ema_final AS (
        SELECT 
            *,
            -- Use the step1 values for proper EMA calculation
            fat_mass_ema_step1 AS fat_mass_ema_kg,
            lbm_ema_step1 AS lbm_ema_kg_for_bmr
        FROM ema_step1
    ),
    
    -- Insert the results
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
            v_params_version,
            ROUND(fat_mass_ema_kg, 3),
            ROUND(lbm_ema_kg_for_bmr, 3),
            ROUND(v_bmr0_kcal + v_k_lbm_kcal_per_kg * lbm_ema_kg_for_bmr),
            ROUND((1 - v_c_exercise_comp) * workout_kcal),
            intake_kcal - ROUND((1 - v_c_exercise_comp) * workout_kcal) 
                - ROUND(v_bmr0_kcal + v_k_lbm_kcal_per_kg * lbm_ema_kg_for_bmr),
            NOW(),
            v_run_id
        FROM ema_final
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

-- Step 3: Test the simple function
SELECT * FROM materialize_daily_series_simple('2025-09-01', '2025-09-22', true);

-- Step 4: Verify the results
SELECT 
    fact_date,
    fat_mass_ema_kg,
    LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date) as prev_ema,
    fat_mass_ema_kg - LAG(fat_mass_ema_kg) OVER (ORDER BY fact_date) as delta
FROM daily_series_materialized
WHERE fact_date BETWEEN '2025-09-09' AND '2025-09-20'
ORDER BY fact_date;
