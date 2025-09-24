-- Create daily_facts table according to schema.manifest.yaml
-- Migration: 20250923_create_daily_facts_with_fiber.sql

-- Create daily_facts table as the canonical daily facts surface
CREATE TABLE IF NOT EXISTS daily_facts (
    fact_date DATE NOT NULL PRIMARY KEY,
    intake_kcal INTEGER,
    protein_g NUMERIC,
    carbs_g NUMERIC,
    fat_g NUMERIC,
    fiber_g NUMERIC(10,2),  -- Add fiber_g column
    intake_is_imputed BOOLEAN,
    imputation_method TEXT,
    nutrition_is_observed BOOLEAN,
    workout_kcal INTEGER,
    weight_kg NUMERIC(10,3),
    fat_mass_kg NUMERIC(10,3),
    fat_free_mass_kg NUMERIC(10,3),
    muscle_mass_kg NUMERIC(10,3),
    hydration_kg NUMERIC(10,3),
    bone_mass_kg NUMERIC(10,3),
    season TEXT,
    is_holiday BOOLEAN,
    travel_status TEXT
);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_daily_facts_fact_date ON daily_facts(fact_date);
CREATE INDEX IF NOT EXISTS idx_daily_facts_fiber_g ON daily_facts(fiber_g);
CREATE INDEX IF NOT EXISTS idx_daily_facts_intake_kcal ON daily_facts(intake_kcal);
CREATE INDEX IF NOT EXISTS idx_daily_facts_workout_kcal ON daily_facts(workout_kcal);

-- Add comments for documentation
COMMENT ON TABLE daily_facts IS 'Canonical daily facts surface - source of truth for daily metrics';
COMMENT ON COLUMN daily_facts.fiber_g IS 'Daily fiber intake in grams from nutrition tracking';
COMMENT ON COLUMN daily_facts.intake_kcal IS 'Daily intake kcal (from nutrition_daily)';
COMMENT ON COLUMN daily_facts.workout_kcal IS 'Exercise kcal (sum of trainingpeaks_enriched)';
COMMENT ON COLUMN daily_facts.fat_mass_kg IS 'Withings fat mass (kg), earliest-of-day';
