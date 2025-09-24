-- etl/functions/update_daily_series_factory.sql
-- Reusable factory for maintaining daily_series_materialized
-- Handles both backfill and incremental updates

-- Function 1: Find gaps and determine processing range
CREATE OR REPLACE FUNCTION get_materialization_range()
RETURNS TABLE(start_date date, end_date date, mode text) AS $$
BEGIN
    RETURN QUERY
    WITH current_state AS (
        SELECT 
            COALESCE(MAX(fact_date), '2020-12-31'::date) AS last_materialized,
            COALESCE(MAX(fact_date), CURRENT_DATE) AS last_facts
        FROM daily_series_materialized
    ),
    facts_range AS (
        SELECT 
            MIN(fact_date) AS first_fact,
            MAX(fact_date) AS last_fact
        FROM daily_facts
        WHERE fact_date > (SELECT last_materialized FROM current_state)
    )
    SELECT 
        COALESCE(f.first_fact, CURRENT_DATE) AS start_date,
        GREATEST(COALESCE(f.last_fact, CURRENT_DATE), CURRENT_DATE) AS end_date,
        CASE 
            WHEN f.first_fact IS NULL THEN 'extend_to_current'
            ELSE 'new_facts_available'
        END AS mode
    FROM facts_range f;
END;
$$ LANGUAGE plpgsql;

-- Function 2: Main materialization engine
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
    v_outliers_found int := 0;
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

    -- Create temp table with outlier detection and cleaning
    CREATE TEMP TABLE temp_facts_cleaned AS
    SELECT 
        ds.fact_date,
        COALESCE(df.intake_kcal, 0) AS intake_kcal,
        COALESCE(df.workout_kcal, 0) AS workout_kcal,
        -- Mark outliers and use NULL instead
        CASE 
            WHEN is_measurement_outlier(df.fat_mass_kg, ds.fact_date) THEN NULL
            ELSE df.fat_mass_kg
        END AS fat_mass_kg_clean,
        df.fat_free_mass_kg AS ffm_clean,
        is_measurement_outlier(df.fat_mass_kg, ds.fact_date) AS was_outlier
    FROM (
        SELECT generate_series(v_start_date, v_end_date, '1 day'::interval)::date AS fact_date
    ) ds
    LEFT JOIN daily_facts df ON ds.fact_date = df.fact_date;

    -- Count outliers for logging
    SELECT COUNT(*) INTO v_outliers_found 
    FROM temp_facts_cleaned 
    WHERE was_outlier;

    IF v_outliers_found > 0 THEN
        RAISE NOTICE 'Found and excluded % outliers in date range', v_outliers_found;
        
        -- Log outliers to audit table
        INSERT INTO outlier_audit (fact_date, original_value, detection_reason, run_id)
        SELECT 
            fact_date, 
            (SELECT fat_mass_kg FROM daily_facts WHERE fact_date = tf.fact_date),
            'Auto-detected outlier',
            v_run_id
        FROM temp_facts_cleaned tf
        WHERE was_outlier;
        
        -- Log outliers to ETL log
        INSERT INTO etl_run_log (run_id, process_name, started_at, status, error_message)
        VALUES (
            v_run_id, 
            'outlier_exclusion', 
            NOW(), 
            'WARNING',
            'Excluded ' || v_outliers_found || ' outliers from EMA calculation'
        );
    END IF;
    
    -- Main materialization logic with cleaned data
    WITH date_spine AS (
        SELECT generate_series(
            v_start_date,
            v_end_date,
            '1 day'::interval
        )::date AS fact_date
    ),
    
    -- Get all historical data for forward-fill context (including cleaned data)
    all_facts AS (
        SELECT 
            fact_date,
            intake_kcal,
            workout_kcal,
            fat_mass_kg,
            fat_free_mass_kg
        FROM daily_facts
        WHERE fact_date <= v_end_date
    ),
    
    -- Forward-fill body composition using cleaned data
    facts_filled AS (
        SELECT 
            ds.fact_date,
            COALESCE(tf.intake_kcal, 0) AS intake_kcal,
            COALESCE(tf.workout_kcal, 0) AS workout_kcal,
            -- Use cleaned data with forward-fill from non-outlier values
            COALESCE(
                tf.fat_mass_kg_clean,
                (SELECT fat_mass_kg FROM daily_facts 
                 WHERE fat_mass_kg IS NOT NULL 
                   AND fact_date < ds.fact_date
                   AND NOT is_measurement_outlier(fat_mass_kg, fact_date)
                 ORDER BY fact_date DESC LIMIT 1)
            ) AS fat_mass_filled,
            COALESCE(
                tf.ffm_clean,
                (SELECT fat_free_mass_kg FROM daily_facts 
                 WHERE fat_free_mass_kg IS NOT NULL 
                 AND fact_date < ds.fact_date 
                 ORDER BY fact_date DESC LIMIT 1)
            ) AS ffm_filled
        FROM date_spine ds
        LEFT JOIN temp_facts_cleaned tf ON ds.fact_date = tf.fact_date
    ),
    
    -- Get seed EMAs from previous data
    seed_emas AS (
        SELECT 
            fat_mass_ema_kg AS seed_fat_ema,
            lbm_ema_kg_for_bmr AS seed_lbm_ema
        FROM daily_series_materialized
        WHERE fact_date = (v_start_date - INTERVAL '1 day')
    ),
    
    -- Calculate EMAs using window functions
    ema_calculated AS (
        SELECT 
            f.fact_date,
            f.intake_kcal,
            f.workout_kcal,
            f.fat_mass_filled,
            f.ffm_filled,
            p.params_version,
            p.alpha_fm,
            p.alpha_lbm,
            p.bmr0_kcal,
            p.k_lbm_kcal_per_kg,
            p.c_exercise_comp,
            
            -- Calculate EMA using window functions
            CASE 
                WHEN f.fact_date = v_start_date AND EXISTS (SELECT 1 FROM seed_emas)
                THEN (SELECT seed_fat_ema FROM seed_emas) * (1 - p.alpha_fm) + f.fat_mass_filled * p.alpha_fm
                WHEN f.fact_date = v_start_date
                THEN f.fat_mass_filled  -- First day ever: use raw value
                ELSE 
                    -- Use previous day's EMA if available, otherwise use current value
                    COALESCE(
                        LAG(f.fat_mass_filled, 1) OVER (ORDER BY f.fact_date) * (1 - p.alpha_fm) + f.fat_mass_filled * p.alpha_fm,
                        f.fat_mass_filled
                    )
            END AS fat_mass_ema_kg,
            
            CASE 
                WHEN f.fact_date = v_start_date AND EXISTS (SELECT 1 FROM seed_emas)
                THEN (SELECT seed_lbm_ema FROM seed_emas) * (1 - p.alpha_lbm) + f.ffm_filled * p.alpha_lbm
                WHEN f.fact_date = v_start_date
                THEN f.ffm_filled
                ELSE 
                    -- Use previous day's EMA if available, otherwise use current value
                    COALESCE(
                        LAG(f.ffm_filled, 1) OVER (ORDER BY f.fact_date) * (1 - p.alpha_lbm) + f.ffm_filled * p.alpha_lbm,
                        f.ffm_filled
                    )
            END AS lbm_ema_kg_for_bmr
            
        FROM facts_filled f
        LEFT JOIN model_params_timevarying p 
            ON f.fact_date >= p.effective_start_date 
            AND f.fact_date <= COALESCE(p.effective_end_date, '9999-12-31')
        WHERE f.fact_date BETWEEN v_start_date AND v_end_date
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

    -- Clean up temp table
    DROP TABLE temp_facts_cleaned;
    
    -- Update log
    UPDATE etl_run_log 
    SET 
        completed_at = NOW(),
        rows_processed = v_rows,
        status = 'SUCCESS'
    WHERE run_id = v_run_id;
    
    RETURN QUERY SELECT v_rows, 'SUCCESS: ' || v_mode || ' - ' || v_outliers_found || ' outliers excluded';
    
EXCEPTION WHEN OTHERS THEN
    -- Clean up temp table on error
    DROP TABLE IF EXISTS temp_facts_cleaned;
    
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

-- Function 3: Quick daily update wrapper
CREATE OR REPLACE FUNCTION daily_update()
RETURNS void AS $$
BEGIN
    -- Check if new data exists
    IF EXISTS (
        SELECT 1 FROM daily_facts 
        WHERE fact_date > (SELECT MAX(fact_date) FROM daily_series_materialized)
    ) THEN
        PERFORM materialize_daily_series();
        RAISE NOTICE 'Daily series updated successfully';
    ELSE
        RAISE NOTICE 'No new data to process';
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create ETL log table if not exists
CREATE TABLE IF NOT EXISTS etl_run_log (
    run_id text PRIMARY KEY,
    process_name text,
    start_date date,
    end_date date,
    started_at timestamp,
    completed_at timestamp,
    rows_processed int,
    status text,
    error_message text
);

-- Create index for performance
CREATE INDEX IF NOT EXISTS idx_etl_run_log_process ON etl_run_log(process_name, started_at DESC);

-- Function to check if a measurement is an outlier
CREATE OR REPLACE FUNCTION is_measurement_outlier(
    p_fat_mass numeric,
    p_fact_date date
) RETURNS boolean AS $$
DECLARE
    v_prev_value numeric;
    v_next_value numeric;
    v_median numeric;
    v_stddev numeric;
    v_q1 numeric;
    v_q3 numeric;
    v_iqr_fence numeric;
BEGIN
    -- Get statistical thresholds from recent history (last 90 days)
    SELECT 
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fat_mass_kg),
        STDDEV(fat_mass_kg),
        PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY fat_mass_kg),
        PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY fat_mass_kg)
    INTO v_median, v_stddev, v_q1, v_q3
    FROM daily_facts
    WHERE fat_mass_kg IS NOT NULL
      AND fact_date >= p_fact_date - INTERVAL '90 days'
      AND fact_date < p_fact_date;
    
    v_iqr_fence := (v_q3 - v_q1) * 1.5;
    
    -- Get adjacent values
    SELECT fat_mass_kg INTO v_prev_value
    FROM daily_facts
    WHERE fat_mass_kg IS NOT NULL
      AND fact_date < p_fact_date
    ORDER BY fact_date DESC
    LIMIT 1;
    
    SELECT fat_mass_kg INTO v_next_value
    FROM daily_facts
    WHERE fat_mass_kg IS NOT NULL
      AND fact_date > p_fact_date
    ORDER BY fact_date
    LIMIT 1;
    
    -- Check multiple outlier conditions
    IF p_fat_mass IS NULL THEN
        RETURN FALSE;  -- NULL is not an outlier, just missing data
    ELSIF p_fat_mass > 30 THEN
        RAISE NOTICE 'Outlier detected %: % kg exceeds 30kg limit', p_fact_date, p_fat_mass;
        RETURN TRUE;
    ELSIF v_prev_value IS NOT NULL AND ABS(p_fat_mass - v_prev_value) > 3 THEN
        RAISE NOTICE 'Outlier detected %: % kg jumps % kg from previous', p_fact_date, p_fat_mass, ABS(p_fat_mass - v_prev_value);
        RETURN TRUE;
    ELSIF v_median IS NOT NULL AND v_stddev > 0 AND ABS(p_fat_mass - v_median) / v_stddev > 3.5 THEN
        RAISE NOTICE 'Outlier detected %: % kg has z-score %', p_fact_date, p_fat_mass, ABS(p_fat_mass - v_median) / v_stddev;
        RETURN TRUE;
    ELSIF v_q1 IS NOT NULL AND (p_fat_mass < v_q1 - v_iqr_fence OR p_fat_mass > v_q3 + v_iqr_fence) THEN
        RAISE NOTICE 'Outlier detected %: % kg outside IQR fence [%, %]', p_fact_date, p_fat_mass, v_q1 - v_iqr_fence, v_q3 + v_iqr_fence;
        RETURN TRUE;
    END IF;
    
    RETURN FALSE;
END;
$$ LANGUAGE plpgsql;

-- Add outlier audit table for tracking
CREATE TABLE IF NOT EXISTS outlier_audit (
    fact_date date PRIMARY KEY,
    original_value numeric,
    detection_reason text,
    detected_at timestamp DEFAULT NOW(),
    run_id text
);

-- Function to manually review and approve outliers
CREATE OR REPLACE FUNCTION review_outlier(
    p_fact_date date,
    p_approve boolean
) RETURNS void AS $$
BEGIN
    IF p_approve THEN
        -- Remove from outlier audit (will be included in next run)
        DELETE FROM outlier_audit WHERE fact_date = p_fact_date;
        RAISE NOTICE 'Outlier for % approved and will be included in next update', p_fact_date;
    ELSE
        -- Keep in audit table (continues to be excluded)
        UPDATE outlier_audit 
        SET detection_reason = detection_reason || ' - CONFIRMED OUTLIER'
        WHERE fact_date = p_fact_date;
        RAISE NOTICE 'Outlier for % confirmed and will remain excluded', p_fact_date;
    END IF;
END;
$$ LANGUAGE plpgsql;
