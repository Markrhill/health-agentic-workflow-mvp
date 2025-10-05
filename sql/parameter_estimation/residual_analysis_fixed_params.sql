-- Residual Analysis with Fixed Parameters
-- Tests: α=9,675, BMR from Katch-McArdle (370 + 21.6×LBM), c=0.20 (baseline)
-- Goal: Identify where and why predictions fail

WITH 
daily_data AS (
  SELECT 
    dff.fact_date,
    COALESCE(df.intake_kcal, 0) as intake_kcal,
    COALESCE(df.workout_kcal, 0) as workout_kcal,
    df.weight_kg,
    dff.fat_mass_kg_filtered,
    df.weight_kg - dff.fat_mass_kg_filtered as lbm_kg,
    EXTRACT(DOW FROM dff.fact_date) as day_of_week
  FROM daily_facts_filtered dff
  LEFT JOIN daily_facts df ON dff.fact_date = df.fact_date
  WHERE dff.fact_date >= '2021-01-01'
    AND dff.fact_date <= '2025-09-29'
    AND df.intake_kcal IS NOT NULL
    AND df.weight_kg IS NOT NULL
),

mondays AS (
  SELECT DISTINCT fact_date as monday_date
  FROM daily_data
  WHERE day_of_week = 1
  ORDER BY fact_date
),

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

window_lbm AS (
  SELECT 
    w.window_start,
    MIN(CASE WHEN d.fact_date = w.window_start THEN d.lbm_kg END) as lbm_start_kg,
    MAX(CASE WHEN d.fact_date = w.window_end THEN d.lbm_kg END) as lbm_end_kg
  FROM windows w
  JOIN daily_data d 
    ON d.fact_date >= w.window_start 
    AND d.fact_date <= w.window_end
  GROUP BY w.window_start
),

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

baseline_windows AS (
  SELECT 
    wa.window_start,
    wa.window_end,
    wa.dataset_split,
    wa.total_intake_kcal,
    wa.total_workout_kcal,
    wfm.fm_end_kg - wfm.fm_start_kg as delta_fm_kg,
    wlbm.lbm_end_kg - wlbm.lbm_start_kg as delta_lbm_kg,
    wa.lbm_avg_kg,
    wa.avg_daily_workout_kcal,
    EXTRACT(YEAR FROM wa.window_start) as year
  FROM window_aggregates wa
  JOIN window_fat_mass wfm ON wa.window_start = wfm.window_start
  JOIN window_lbm wlbm ON wa.window_start = wlbm.window_start
  WHERE wa.days_with_data >= 10
    AND wfm.fm_start_kg IS NOT NULL 
    AND wfm.fm_end_kg IS NOT NULL
    AND wa.avg_daily_workout_kcal < 600  -- BASELINE/MID VOLUMES
    AND ABS(wlbm.lbm_end_kg - wlbm.lbm_start_kg) < 0.8  -- LBM stability
),

predictions AS (
  SELECT 
    window_start,
    window_end,
    dataset_split,
    year,
    total_intake_kcal,
    total_workout_kcal,
    delta_fm_kg,
    delta_lbm_kg,
    lbm_avg_kg,
    avg_daily_workout_kcal,
    
    -- Fixed parameters
    370 + 21.6 * lbm_avg_kg as bmr_daily,
    (370 + 21.6 * lbm_avg_kg) * 14 as bmr_14days,
    0.20 as c_baseline,
    9675 as alpha,
    
    -- Predicted deficit: BMR×14 + c×Exercise (compensation adds to expenditure)
    (370 + 21.6 * lbm_avg_kg) * 14 + 0.20 * total_workout_kcal as predicted_expenditure,
    
    -- Observed deficit: Intake - ΔFM×α
    total_intake_kcal - delta_fm_kg * 9675 as observed_expenditure,
    
    -- Predicted fat mass change: (Intake - BMR×14 - (1-c)×Exercise) / α
    (total_intake_kcal - (370 + 21.6 * lbm_avg_kg) * 14 - 0.80 * total_workout_kcal) / 9675 as predicted_delta_fm,
    
    -- Residual (positive = under-predicted expenditure = over-predicted fat gain)
    (total_intake_kcal - delta_fm_kg * 9675) - ((370 + 21.6 * lbm_avg_kg) * 14 + 0.20 * total_workout_kcal) as residual_kcal
  FROM baseline_windows
)

-- Window-by-window details
SELECT 
  window_start,
  dataset_split,
  year,
  ROUND(lbm_avg_kg::numeric, 1) as lbm_kg,
  ROUND(bmr_daily::numeric, 0) as bmr_daily,
  ROUND(bmr_14days::numeric, 0) as bmr_14d,
  total_workout_kcal as exercise,
  ROUND(avg_daily_workout_kcal::numeric, 0) as exercise_daily,
  ROUND(delta_fm_kg::numeric, 3) as actual_delta_fm,
  ROUND(delta_lbm_kg::numeric, 3) as actual_delta_lbm,
  ROUND(predicted_delta_fm::numeric, 3) as pred_delta_fm,
  ROUND((delta_fm_kg - predicted_delta_fm)::numeric, 3) as fm_error_kg,
  ROUND(residual_kcal::numeric, 0) as residual_kcal,
  ROUND((residual_kcal / 14)::numeric, 0) as residual_kcal_per_day
FROM predictions
ORDER BY window_start;

-- Summary by year
SELECT 
  year,
  dataset_split,
  COUNT(*) as n_windows,
  ROUND(AVG(lbm_avg_kg)::numeric, 1) as mean_lbm,
  ROUND(AVG(avg_daily_workout_kcal)::numeric, 0) as mean_exercise_daily,
  ROUND(AVG(delta_fm_kg)::numeric, 3) as mean_actual_delta_fm,
  ROUND(AVG(predicted_delta_fm)::numeric, 3) as mean_pred_delta_fm,
  ROUND(AVG(delta_fm_kg - predicted_delta_fm)::numeric, 3) as mean_fm_error_kg,
  ROUND(AVG(residual_kcal)::numeric, 0) as mean_residual_kcal,
  ROUND(STDDEV(residual_kcal)::numeric, 0) as stddev_residual_kcal,
  ROUND((AVG(residual_kcal) / 14)::numeric, 0) as mean_residual_per_day
FROM predictions
GROUP BY year, dataset_split
ORDER BY year, dataset_split;

-- Overall summary
SELECT 
  dataset_split,
  COUNT(*) as n_windows,
  ROUND(AVG(delta_fm_kg)::numeric, 3) as mean_actual_delta_fm,
  ROUND(AVG(predicted_delta_fm)::numeric, 3) as mean_pred_delta_fm,
  ROUND(AVG(delta_fm_kg - predicted_delta_fm)::numeric, 3) as mean_fm_error_kg,
  ROUND(STDDEV(delta_fm_kg - predicted_delta_fm)::numeric, 3) as stddev_fm_error_kg,
  ROUND(AVG(residual_kcal)::numeric, 0) as mean_residual_kcal,
  ROUND(STDDEV(residual_kcal)::numeric, 0) as stddev_residual_kcal,
  -- Pseudo R² based on variance explained
  ROUND((1 - VARIANCE(delta_fm_kg - predicted_delta_fm) / VARIANCE(delta_fm_kg))::numeric, 3) as pseudo_r2
FROM predictions
GROUP BY dataset_split
ORDER BY dataset_split;

