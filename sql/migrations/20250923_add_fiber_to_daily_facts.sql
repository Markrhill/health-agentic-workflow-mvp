-- Add missing fiber_g column to daily_series_materialized
-- Migration: 20250923_add_fiber_to_daily_facts.sql

-- Add fiber_g column to daily_series_materialized table
ALTER TABLE daily_series_materialized 
ADD COLUMN fiber_g NUMERIC(10,2);

-- Backfill from hae_metrics_parsed if it exists
-- Note: This assumes hae_metrics_parsed table has fiber data
-- If the table structure is different, adjust accordingly
UPDATE daily_series_materialized dsm
SET fiber_g = hmp.value
FROM hae_metrics_parsed hmp
WHERE dsm.fact_date = hmp.date
AND hmp.metric_name = 'fiber_g'
AND hmp.value IS NOT NULL;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_daily_series_fiber_g ON daily_series_materialized(fiber_g);

-- Add comment for documentation
COMMENT ON COLUMN daily_series_materialized.fiber_g IS 'Daily fiber intake in grams from nutrition tracking';
