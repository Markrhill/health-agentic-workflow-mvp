-- Migration: Create facts_intake_dow_medians view
-- Date: 2025-09-16
-- Description: Support intake imputation by day of week

CREATE VIEW public.facts_intake_dow_medians AS
SELECT 
    EXTRACT(DOW FROM fact_date)::integer AS dow_index,
    CASE EXTRACT(DOW FROM fact_date)
        WHEN 1 THEN 'Monday'
        WHEN 2 THEN 'Tuesday'
        WHEN 3 THEN 'Wednesday'
        WHEN 4 THEN 'Thursday'
        WHEN 5 THEN 'Friday'
        WHEN 6 THEN 'Saturday'
        WHEN 0 THEN 'Sunday'
    END AS day_of_week,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY intake_kcal) AS intake_kcal_median
FROM public.daily_facts
WHERE intake_kcal IS NOT NULL
GROUP BY EXTRACT(DOW FROM fact_date)
ORDER BY dow_index;

-- Add comments
COMMENT ON VIEW public.facts_intake_dow_medians IS 'support intake imputation by day of week';
COMMENT ON COLUMN public.facts_intake_dow_medians.dow_index IS '1=Mon … 7=Sun for stable ordering';
COMMENT ON COLUMN public.facts_intake_dow_medians.day_of_week IS 'Monday..Sunday';
COMMENT ON COLUMN public.facts_intake_dow_medians.intake_kcal_median IS 'median intake_kcal for this day-of-week computed from daily_facts';
