-- Train windows: START and END must have observed FM; END snapped to 7–9 days after START.
CREATE OR REPLACE VIEW p1_train_windows_flex7 AS
WITH d AS (
  SELECT fact_date, intake_kcal, workout_kcal, fat_mass_kg
  FROM p1_train_daily_i
),
fm AS (
  SELECT fact_date, fat_mass_kg
  FROM p1_train_daily
  WHERE fat_mass_kg IS NOT NULL
),
win AS (
  SELECT
    s.fact_date                             AS start_date,
    e.fact_date                             AS end_date,
    (e.fact_date - s.fact_date)             AS days,
    s.fat_mass_kg                           AS fm_start,
    e.fat_mass_kg                           AS fm_end
  FROM fm s
  JOIN fm e
    ON e.fact_date BETWEEN s.fact_date + INTERVAL '7 day'
                      AND s.fact_date + INTERVAL '9 day'
)
SELECT
  w.start_date,
  w.end_date,
  w.days,
  w.fm_start,
  w.fm_end,
  (w.fm_end - w.fm_start)                                  AS delta_fm_kg,
  SUM(d2.intake_kcal)                                      AS intake_kcal_sum,
  SUM(d2.workout_kcal)                                     AS workout_kcal_sum,
  SUM(d2.intake_kcal - d2.workout_kcal)                    AS net_kcal_sum,
  (w.days = 7)                                             AS is_7d,
  (w.days = 8)                                             AS is_8d,
  (w.days = 9)                                             AS is_9d
FROM win w
JOIN d d2
  ON d2.fact_date BETWEEN w.start_date AND w.end_date
-- Optional: exclude FM-outlier days if you have a flag/table; hook here.
GROUP BY 1,2,3,4,5
HAVING COUNT(*) = (w.days + 1);  -- ensure full coverage of all days
