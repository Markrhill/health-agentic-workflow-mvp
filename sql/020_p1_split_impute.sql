-- Split views
CREATE OR REPLACE VIEW p1_train_daily AS
SELECT * FROM p0_staging
WHERE fact_date BETWEEN DATE '2021-01-01' AND DATE '2024-12-31';

CREATE OR REPLACE VIEW p1_test_daily AS
SELECT * FROM p0_staging
WHERE fact_date BETWEEN DATE '2025-01-01' AND DATE '2025-08-04';

-- Intake DoW means (train)
WITH train_dow AS (
  SELECT EXTRACT(DOW FROM fact_date)::int AS dow, AVG(intake_kcal)::float AS mean_kcal
  FROM p1_train_daily
  WHERE intake_kcal IS NOT NULL
  GROUP BY 1
)
CREATE OR REPLACE VIEW p1_train_daily_i AS
SELECT
  d.fact_date,
  COALESCE(d.intake_kcal, ROUND(td.mean_kcal)::int) AS intake_kcal,
  COALESCE(d.workout_kcal, 0)                       AS workout_kcal,
  d.weight_kg,
  d.fat_mass_kg,
  d.lean_mass_kg,
  (d.intake_kcal IS NULL)                            AS intake_imputed,
  (d.workout_kcal IS NULL)                           AS workout_imputed
FROM p1_train_daily d
LEFT JOIN train_dow td
  ON EXTRACT(DOW FROM d.fact_date)::int = td.dow;

-- Intake DoW means (test)
WITH test_dow AS (
  SELECT EXTRACT(DOW FROM fact_date)::int AS dow, AVG(intake_kcal)::float AS mean_kcal
  FROM p1_test_daily
  WHERE intake_kcal IS NOT NULL
  GROUP BY 1
)
CREATE OR REPLACE VIEW p1_test_daily_i AS
SELECT
  d.fact_date,
  COALESCE(d.intake_kcal, ROUND(td.mean_kcal)::int) AS intake_kcal,
  COALESCE(d.workout_kcal, 0)                       AS workout_kcal,
  d.weight_kg,
  d.fat_mass_kg,
  d.lean_mass_kg,
  (d.intake_kcal IS NULL)                            AS intake_imputed,
  (d.workout_kcal IS NULL)                           AS workout_imputed
FROM p1_test_daily d
LEFT JOIN test_dow td
  ON EXTRACT(DOW FROM d.fact_date)::int = td.dow;
