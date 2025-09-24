const { getPool } = require('./connection');

// Get current parameters
const getCurrentParameters = async () => {
  const pool = getPool();
  const query = `
    SELECT 
      params_version,
      effective_start_date,
      alpha_fm,
      alpha_lbm,
      c_exercise_comp,
      bmr0_kcal,
      k_lbm_kcal_per_kg,
      kcal_per_kg_fat
    FROM model_params_timevarying 
    WHERE effective_start_date <= CURRENT_DATE
    ORDER BY effective_start_date DESC 
    LIMIT 1
  `;
  const result = await pool.query(query);
  return result.rows[0];
};

// Get weekly data for UI
const getWeeklyData = async (limit = 10) => {
  const pool = getPool();
  const query = `
    SELECT 
      -- Instead of returning raw date fields, return formatted strings
      TO_CHAR(dsm.fact_date - EXTRACT(DOW FROM dsm.fact_date - 1)::int, 'YYYY-MM-DD') as week_start_monday,
      COUNT(*) as days_in_week,
      AVG(dsm.fat_mass_ema_kg) as avg_fat_mass_ema,
      AVG(dsm.fat_mass_ema_kg) as avg_fat_mass_raw,  -- Using same value since no raw data available
      AVG(dsm.net_kcal) as avg_net_kcal,
      0 as total_intake,  -- Placeholder since intake data not available
      SUM(dsm.adj_exercise_kcal) as total_adj_exercise,
      0 as imputed_days,  -- Placeholder
      MIN(dsm.params_version_used) as params_version,
      MIN(dsm.computed_at) as computed_at
    FROM daily_series_materialized dsm
    WHERE dsm.fact_date >= '2025-01-01'
    GROUP BY dsm.fact_date - EXTRACT(DOW FROM dsm.fact_date - 1)::int
    ORDER BY week_start_monday DESC
    LIMIT $1
  `;
  const result = await pool.query(query, [limit]);
  return result.rows;
};

// Get daily data for specific week
const getDailyDataForWeek = async (startDate, endDate) => {
  const pool = getPool();
  const query = `
    -- Factory Rule: Daily data with parameter table as single source of truth
    WITH current_params AS (
        SELECT alpha_fm, c_exercise_comp as c, kcal_per_kg_fat, bmr0_kcal, k_lbm_kcal_per_kg
        FROM model_params_timevarying 
        WHERE effective_start_date <= $2::date
        ORDER BY effective_start_date DESC 
        LIMIT 1
    )
    -- Includes fiber_g for nutrition tracking
    SELECT 
        df.fact_date,
        EXTRACT(DOW FROM df.fact_date) as day_of_week,
        TO_CHAR(df.fact_date, 'Day') as day_name,
        dsm.fat_mass_ema_kg * 2.20462 as fat_mass_ema_lbs,
        dsm.net_kcal,
        df.intake_kcal,
        df.workout_kcal as raw_exercise_kcal,
        dsm.adj_exercise_kcal as compensated_exercise_kcal,
        df.intake_is_imputed,
        df.imputation_method,
        dsm.params_version_used,
        0 as fat_mass_uncertainty_lbs,  -- Placeholder
        df.fat_mass_kg * 2.20462 as raw_fat_mass_lbs,
        dsm.bmr_kcal,
        cp.alpha_fm,
        cp.c as compensation_factor,
        cp.kcal_per_kg_fat,
        df.protein_g,
        df.fiber_g
    FROM daily_facts df
    LEFT JOIN daily_series_materialized dsm ON df.fact_date = dsm.fact_date
    CROSS JOIN current_params cp
    WHERE df.fact_date >= $1::date
      AND df.fact_date <= $2::date
    ORDER BY df.fact_date;
  `;
  
  const result = await pool.query(query, [startDate, endDate]);
  
  // Debug: Log the actual fact_date values being returned
  console.log('Daily data query parameters:', { startDate, endDate });
  console.log('Daily data fact_date values:', result.rows.map(d => d.fact_date));
  console.log('Number of days returned:', result.rows.length);
  
  return result.rows;
};

// Get health metrics summary
const getHealthMetricsSummary = async () => {
  const pool = getPool();
  const query = `
    SELECT 
      COUNT(*) as total_days,
      MIN(fact_date) as earliest_date,
      MAX(fact_date) as latest_date,
      AVG(fat_mass_ema_kg) as avg_fat_mass_kg,
      AVG(net_kcal) as avg_net_kcal,
      0 as imputed_days_count  -- Placeholder since intake data not available
    FROM daily_series_materialized dsm
    WHERE dsm.fact_date >= CURRENT_DATE - INTERVAL '30 days'
  `;
  const result = await pool.query(query);
  return result.rows[0];
};

module.exports = {
  getCurrentParameters,
  getWeeklyData,
  getDailyDataForWeek,
  getHealthMetricsSummary
};
