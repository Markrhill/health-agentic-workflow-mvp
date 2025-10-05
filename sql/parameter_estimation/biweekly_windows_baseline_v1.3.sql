-- Biweekly Windows - Baseline Volumes Only (v1.3)
-- Excludes HIGH volume periods to avoid muscle catabolism confounding
-- Estimates: BMR intercept, BMR per kg LBM, c_baseline

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
    wlbm.lbm_start_kg,
    wlbm.lbm_end_kg,
    wlbm.lbm_end_kg - wlbm.lbm_start_kg as delta_lbm_kg,
    (wfm.fm_start_kg - wfm.fm_end_kg) * 9675 as observed_deficit_kcal,
    wa.total_intake_kcal - wa.total_workout_kcal - (wfm.fm_end_kg - wfm.fm_start_kg) * 9675 as y_deficit,
    14 as days
  FROM window_aggregates wa
  JOIN window_fat_mass wfm ON wa.window_start = wfm.window_start
  JOIN window_lbm wlbm ON wa.window_start = wlbm.window_start
  WHERE wa.days_with_data >= 10
    AND wfm.fm_start_kg IS NOT NULL 
    AND wfm.fm_end_kg IS NOT NULL
    AND wa.avg_daily_workout_kcal < 600  -- BASELINE/MID VOLUMES (exclude high only)
    AND ABS(wlbm.lbm_end_kg - wlbm.lbm_start_kg) < 0.8  -- Relax LBM stability to 800g
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
  ROUND(lbm_start_kg::numeric, 2) as lbm_start_kg,
  ROUND(lbm_end_kg::numeric, 2) as lbm_end_kg,
  ROUND(delta_lbm_kg::numeric, 3) as delta_lbm_kg,
  ROUND(avg_daily_workout_kcal::numeric, 0) as avg_daily_workout_kcal,
  ROUND(y_deficit::numeric, 0) as y_deficit,
  days
FROM final_windows
ORDER BY window_start;

