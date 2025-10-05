-- Biweekly Training Windows for Parameter Estimation
-- Version: v1
-- Created: 2025-10-02
-- Purpose: Generate 14-day Monday-Sunday aligned windows for BMR and compensation parameter fitting
-- Dependencies: daily_facts, daily_facts_filtered (Kalman filtered fat mass)
-- Output: 121 training windows (2021-2024), 19 test windows (2025)
--
-- Methodology:
-- - 14-day windows starting each Monday (perfect DoW cancellation)
-- - Non-overlapping to ensure independence
-- - Requires ≥12 days of data per window
-- - LBM derived as: weight - fat_mass_filtered (includes gastric noise ~1.02 kg)
-- - Fat mass changes from Kalman filter (daily noise reduced 10× to 0.11 kg)
--
-- Regression model:
--   y = b₀×days + b₁×(days×LBM) + b₂×Exercise + ε
--   Where: y = Intake - Exercise + ΔFM×9675
--   Parameters: b₀ = BMR intercept, b₁ = kcal/kg/day, b₂ = -c

-- Generate 14-day Monday-Sunday aligned windows for parameter estimation
WITH 
-- Step 1: Combine daily facts with Kalman-filtered fat mass
daily_data AS (
  SELECT 
    df.fact_date,
    df.intake_kcal,
    df.workout_kcal,
    df.weight_kg,
    dff.fat_mass_kg_filtered,
    df.weight_kg - dff.fat_mass_kg_filtered as lbm_kg,
    EXTRACT(DOW FROM df.fact_date) as day_of_week
  FROM daily_facts df
  JOIN daily_facts_filtered dff ON df.fact_date = dff.fact_date
  WHERE df.fact_date >= '2021-01-01'
    AND df.fact_date <= '2025-09-29'
    AND df.weight_kg IS NOT NULL
    AND dff.fat_mass_kg_filtered IS NOT NULL
    AND df.intake_kcal IS NOT NULL
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

-- Step 5: Aggregate other metrics
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

-- Step 6: Combine and calculate derived metrics
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
    wa.total_intake_kcal - wa.total_workout_kcal + (wfm.fm_end_kg - wfm.fm_start_kg) * 9675 as y_deficit,
    14 as days,
    14 * wa.lbm_avg_kg as days_x_lbm
  FROM window_aggregates wa
  JOIN window_fat_mass wfm ON wa.window_start = wfm.window_start
  WHERE wa.days_with_data >= 12
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

