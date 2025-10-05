-- Biweekly Training Windows for Parameter Estimation
-- Version: v1.1 (relaxed filters for better coverage)
-- Created: 2025-10-02
-- Purpose: Generate 14-day Monday-Sunday aligned windows for BMR and compensation parameter fitting
--
-- Changes from v1.0:
-- - Use daily_facts_filtered as authoritative source (includes Kalman forward-propagated days)
-- - Include imputed intake (DoW median backfill is statistically valid)
-- - Only exclude days where intake is truly NULL
-- - Derive LBM from weight - fat_mass_filtered on each day

WITH 
-- Step 1: Get all days with Kalman-filtered fat mass
daily_data AS (
  SELECT 
    dff.fact_date,
    df.intake_kcal,
    COALESCE(df.workout_kcal, 0) as workout_kcal,
    df.weight_kg,
    dff.fat_mass_kg_filtered,
    df.weight_kg - dff.fat_mass_kg_filtered as lbm_kg,
    EXTRACT(DOW FROM dff.fact_date) as day_of_week
  FROM daily_facts_filtered dff
  JOIN daily_facts df ON dff.fact_date = df.fact_date
  WHERE dff.fact_date >= '2021-01-01'
    AND dff.fact_date <= '2025-09-29'
    AND df.intake_kcal IS NOT NULL  -- Only exclude if truly missing
    AND df.weight_kg IS NOT NULL    -- Need weight to calculate LBM
),

-- Step 2: Find all Mondays
mondays AS (
  SELECT DISTINCT fact_date as monday_date
  FROM daily_data
  WHERE day_of_week = 1
  ORDER BY fact_date
),

-- Step 3: Create 14-day windows
windows AS (
  SELECT 
    m.monday_date as window_start,
    m.monday_date + INTERVAL '13 days' as window_end,
    CASE 
      WHEN m.monday_date < '2025-01-01' THEN 'TRAIN'
      ELSE 'TEST'
    END as dataset_split
  FROM mondays m
  WHERE m.monday_date + INTERVAL '13 days' <= (SELECT MAX(fact_date) FROM daily_data)
),

-- Step 4: Get first/last fat mass for each window
window_fat_mass AS (
  SELECT 
    w.window_start,
    MIN(CASE WHEN d.fact_date = w.window_start THEN d.fat_mass_kg_filtered END) as fm_start_kg,
    MAX(CASE WHEN d.fact_date = w.window_end THEN d.fat_mass_kg_filtered END) as fm_end_kg
  FROM windows w
  JOIN daily_data d 
    ON d.fact_date >= w.window_start 
    AND d.fact_date <= w.window_end
  GROUP BY w.window_start
),

-- Step 5: Aggregate metrics
window_aggregates AS (
  SELECT 
    w.window_start,
    w.window_end,
    w.dataset_split,
    COUNT(d.fact_date) as days_with_data,
    SUM(d.intake_kcal) as total_intake_kcal,
    SUM(d.workout_kcal) as total_workout_kcal,
    AVG(d.workout_kcal) as avg_daily_workout_kcal,
    AVG(d.lbm_kg) as lbm_avg_kg
  FROM windows w
  JOIN daily_data d 
    ON d.fact_date >= w.window_start 
    AND d.fact_date <= w.window_end
  GROUP BY w.window_start, w.window_end, w.dataset_split
),

-- Step 6: Combine and calculate
final_windows AS (
  SELECT 
    wa.window_start,
    wa.window_end,
    wa.dataset_split,
    wa.days_with_data,
    wa.total_intake_kcal,
    wa.total_workout_kcal,
    wa.avg_daily_workout_kcal,
    wa.lbm_avg_kg,
    wfm.fm_start_kg,
    wfm.fm_end_kg,
    wfm.fm_end_kg - wfm.fm_start_kg as delta_fm_kg,
    (wfm.fm_start_kg - wfm.fm_end_kg) * 9675 as observed_deficit_kcal,
    CASE 
      WHEN wa.avg_daily_workout_kcal < 300 THEN 'LOW'
      WHEN wa.avg_daily_workout_kcal < 500 THEN 'MID'
      ELSE 'HIGH'
    END as volume_regime,
    wa.total_intake_kcal - wa.total_workout_kcal - (wfm.fm_end_kg - wfm.fm_start_kg) * 9675 as y_deficit,
    14 as days,
    14 * wa.lbm_avg_kg as days_x_lbm
  FROM window_aggregates wa
  JOIN window_fat_mass wfm ON wa.window_start = wfm.window_start
  WHERE wa.days_with_data >= 10  -- Relaxed from 12 to 10
    AND wfm.fm_start_kg IS NOT NULL 
    AND wfm.fm_end_kg IS NOT NULL
)

SELECT 
  window_start,
  window_end,
  dataset_split,
  days_with_data,
  total_intake_kcal,
  total_workout_kcal,
  observed_deficit_kcal,
  ROUND(lbm_avg_kg::numeric, 2) as lbm_avg_kg,
  ROUND(fm_start_kg::numeric, 3) as fm_start_kg,
  ROUND(fm_end_kg::numeric, 3) as fm_end_kg,
  ROUND(delta_fm_kg::numeric, 3) as delta_fm_kg,
  ROUND(avg_daily_workout_kcal::numeric, 0) as avg_daily_workout_kcal,
  volume_regime,
  ROUND(y_deficit::numeric, 0) as y_deficit,
  days,
  ROUND(days_x_lbm::numeric, 1) as days_x_lbm
FROM final_windows
ORDER BY window_start;

