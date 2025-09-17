-- Migration: Create facts_intake_dow_medians view
-- Date: 2025-09-16
-- Description: Support intake imputation by day of week

CREATE OR REPLACE VIEW public.facts_intake_dow_medians AS
WITH base AS (
  SELECT
    to_char(fact_date, 'Day')::text AS day_of_week,
    intake_kcal
  FROM public.daily_facts
  WHERE intake_kcal IS NOT NULL
)
SELECT
  trim(day_of_week) AS day_of_week,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY intake_kcal)::numeric AS intake_kcal_median
FROM base
GROUP BY 1;

-- Add comments
COMMENT ON VIEW public.facts_intake_dow_medians IS 'support intake imputation by day of week';
COMMENT ON COLUMN public.facts_intake_dow_medians.day_of_week IS 'Monday..Sunday';
COMMENT ON COLUMN public.facts_intake_dow_medians.intake_kcal_median IS 'median intake_kcal for this day-of-week computed from daily_facts';
