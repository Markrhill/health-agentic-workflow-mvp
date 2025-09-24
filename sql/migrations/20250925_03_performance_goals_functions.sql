-- sql/migrations/20250925_03_performance_goals_functions.sql
-- Performance Goals Functions - Corrected
-- Date: 2025-09-25

-- Function to evaluate daily performance
CREATE OR REPLACE FUNCTION evaluate_daily_goals(p_date DATE)
RETURNS TABLE (
    metric VARCHAR,
    actual NUMERIC,
    target NUMERIC,
    min_acceptable NUMERIC,
    status VARCHAR  -- 'green', 'yellow', 'red'
) AS $$
BEGIN
    RETURN QUERY
    WITH goals AS (
        SELECT * FROM performance_goals_timevarying
        WHERE p_date BETWEEN effective_start_date 
            AND COALESCE(effective_end_date, '9999-12-31')
    ),
    actuals AS (
        SELECT 
            df.protein_g,
            df.fiber_g,
            dsm.net_kcal
        FROM daily_facts df
        LEFT JOIN daily_series_materialized dsm ON df.fact_date = dsm.fact_date
        WHERE df.fact_date = p_date
    )
    SELECT 
        'protein_g'::VARCHAR as metric,
        a.protein_g as actual,
        g.protein_g_target as target,
        g.protein_g_min as min_acceptable,
        CASE 
            WHEN a.protein_g >= g.protein_g_target THEN 'green'::VARCHAR
            WHEN a.protein_g >= g.protein_g_min THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM actuals a, goals g
    UNION ALL
    SELECT 
        'fiber_g'::VARCHAR as metric,
        a.fiber_g as actual,
        g.fiber_g_target as target,
        g.fiber_g_min as min_acceptable,
        CASE 
            WHEN a.fiber_g >= g.fiber_g_target THEN 'green'::VARCHAR
            WHEN a.fiber_g >= g.fiber_g_min THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM actuals a, goals g
    UNION ALL
    SELECT 
        'net_deficit'::VARCHAR as metric,
        -a.net_kcal as actual,  -- Convert net_kcal to deficit (positive = deficit)
        g.net_deficit_target as target,
        g.net_deficit_max as min_acceptable,
        CASE 
            WHEN -a.net_kcal <= g.net_deficit_target THEN 'green'::VARCHAR
            WHEN -a.net_kcal <= g.net_deficit_max THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM actuals a, goals g;
END;
$$ LANGUAGE plpgsql;

-- Function to evaluate weekly performance
CREATE OR REPLACE FUNCTION evaluate_weekly_goals(p_start_date DATE, p_end_date DATE)
RETURNS TABLE (
    metric VARCHAR,
    actual NUMERIC,
    target NUMERIC,
    min_acceptable NUMERIC,
    status VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    WITH goals AS (
        SELECT * FROM performance_goals_timevarying
        WHERE p_start_date BETWEEN effective_start_date 
            AND COALESCE(effective_end_date, '9999-12-31')
    ),
    weekly_actuals AS (
        SELECT 
            AVG(df.protein_g) as avg_protein_g,
            AVG(df.fiber_g) as avg_fiber_g,
            AVG(-dsm.net_kcal) as avg_deficit,  -- Convert to deficit
            -- Add weekly training metrics when available
            0 as z2_hours,  -- Placeholder - would need training data
            0 as z4_5_hours,  -- Placeholder
            0 as strength_sessions  -- Placeholder
        FROM daily_facts df
        LEFT JOIN daily_series_materialized dsm ON df.fact_date = dsm.fact_date
        WHERE df.fact_date BETWEEN p_start_date AND p_end_date
    )
    SELECT 
        'avg_protein_g'::VARCHAR as metric,
        wa.avg_protein_g as actual,
        g.protein_g_target as target,
        g.protein_g_min as min_acceptable,
        CASE 
            WHEN wa.avg_protein_g >= g.protein_g_target THEN 'green'::VARCHAR
            WHEN wa.avg_protein_g >= g.protein_g_min THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM weekly_actuals wa, goals g
    UNION ALL
    SELECT 
        'avg_fiber_g'::VARCHAR as metric,
        wa.avg_fiber_g as actual,
        g.fiber_g_target as target,
        g.fiber_g_min as min_acceptable,
        CASE 
            WHEN wa.avg_fiber_g >= g.fiber_g_target THEN 'green'::VARCHAR
            WHEN wa.avg_fiber_g >= g.fiber_g_min THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM weekly_actuals wa, goals g
    UNION ALL
    SELECT 
        'avg_deficit'::VARCHAR as metric,
        wa.avg_deficit as actual,
        g.net_deficit_target as target,
        g.net_deficit_max as min_acceptable,
        CASE 
            WHEN wa.avg_deficit <= g.net_deficit_target THEN 'green'::VARCHAR
            WHEN wa.avg_deficit <= g.net_deficit_max THEN 'yellow'::VARCHAR
            ELSE 'red'::VARCHAR
        END as status
    FROM weekly_actuals wa, goals g;
END;
$$ LANGUAGE plpgsql;

-- Dashboard view for goal performance
CREATE VIEW goal_performance_dashboard AS
SELECT 
    p_date,
    COUNT(*) as total_metrics,
    COUNT(CASE WHEN status = 'green' THEN 1 END) as green_count,
    COUNT(CASE WHEN status = 'yellow' THEN 1 END) as yellow_count,
    COUNT(CASE WHEN status = 'red' THEN 1 END) as red_count,
    ROUND(COUNT(CASE WHEN status = 'green' THEN 1 END)::NUMERIC / COUNT(*) * 100, 1) as green_percentage
FROM (
    SELECT 
        generate_series(CURRENT_DATE - INTERVAL '7 days', CURRENT_DATE, '1 day'::interval)::date as p_date
) dates
CROSS JOIN LATERAL (
    SELECT * FROM evaluate_daily_goals(dates.p_date)
) goals
GROUP BY p_date
ORDER BY p_date DESC;
