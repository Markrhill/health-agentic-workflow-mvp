-- Create nutrition_daily view to aggregate nutrition data
-- This view aggregates data from hae_metrics_parsed for nutrition tracking

CREATE OR REPLACE VIEW nutrition_daily AS
SELECT 
    date as day_date,
    ROUND(MAX(CASE WHEN metric_name = 'dietary_energy' THEN value END)) as total_calories_kcal,
    ROUND(MAX(CASE WHEN metric_name = 'total_fat' THEN value END), 1) as total_fat_g,
    ROUND(MAX(CASE WHEN metric_name = 'total_fat' THEN value END), 1) as total_saturated_fat_g,  -- Placeholder
    0 as total_polyunsaturated_fat_g,  -- Placeholder
    0 as total_monounsaturated_fat_g,  -- Placeholder
    0 as total_trans_fat_g,  -- Placeholder
    0 as total_cholesterol_mg,  -- Placeholder
    0 as total_sodium_mg,  -- Placeholder
    0 as total_potassium_mg,  -- Placeholder
    ROUND(MAX(CASE WHEN metric_name = 'carbohydrates' THEN value END), 1) as total_carbohydrates_g,
    ROUND(MAX(CASE WHEN metric_name = 'fiber' THEN value END), 1) as total_fiber_g,
    0 as total_sugar_g,  -- Placeholder
    ROUND(MAX(CASE WHEN metric_name = 'protein' THEN value END), 1) as total_protein_g,
    0 as total_vitamin_a_iu,  -- Placeholder
    0 as total_vitamin_c_mg,  -- Placeholder
    0 as total_calcium_mg,  -- Placeholder
    0 as total_iron_mg  -- Placeholder
FROM hae_metrics_parsed
WHERE metric_name IN ('dietary_energy', 'total_fat', 'carbohydrates', 'fiber', 'protein')
GROUP BY date
ORDER BY date;

-- Add comment
COMMENT ON VIEW nutrition_daily IS 'Daily nutrition aggregates from HAE import data';
