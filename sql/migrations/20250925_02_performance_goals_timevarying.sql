-- sql/migrations/20250925_02_performance_goals_timevarying.sql
-- Performance Goals Schema - Time-Varying Targets
-- Date: 2025-09-25
-- Description: Time-varying performance goals following model_params_timevarying pattern

CREATE TABLE performance_goals_timevarying (
    goal_version VARCHAR(20) PRIMARY KEY,
    effective_start_date DATE NOT NULL,
    effective_end_date DATE,
    
    -- Nutrition Targets (daily)
    protein_g_min NUMERIC(5,1),           -- Yellow threshold
    protein_g_target NUMERIC(5,1),        -- Green threshold
    fiber_g_min NUMERIC(5,1),            
    fiber_g_target NUMERIC(5,1),
    net_deficit_max INTEGER,              -- Maximum sustainable deficit
    net_deficit_target INTEGER,           -- Target deficit
    
    -- Training Volume Targets (weekly)
    z2_hours_min NUMERIC(3,1),           -- Attia's Zone 2 minimum
    z2_hours_target NUMERIC(3,1),        -- Optimal Zone 2
    z4_5_hours_min NUMERIC(3,1),         -- High intensity minimum  
    z4_5_hours_target NUMERIC(3,1),      -- Optimal high intensity
    strength_sessions_min INTEGER,        -- Minimum strength/week
    strength_sessions_target INTEGER,     -- Optimal strength/week
    
    -- Performance Metrics
    ftp_watts_target INTEGER,            -- FTP goal for period
    vo2max_target NUMERIC(4,1),          -- VO2max ml/kg/min
    
    -- Body Composition
    body_fat_pct_max NUMERIC(3,1),       -- Yellow threshold
    body_fat_pct_target NUMERIC(3,1),    -- Green target
    lean_mass_kg_min NUMERIC(4,1),       -- Minimum acceptable LBM
    
    -- Meta
    goal_source VARCHAR(50),             -- 'attia', 'custom', 'coach'
    priority VARCHAR(20),                -- 'performance', 'health', 'recomp'
    notes TEXT,
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    
    CHECK (effective_start_date <= COALESCE(effective_end_date, '9999-12-31')),
    CHECK (protein_g_min <= protein_g_target),
    CHECK (z2_hours_min <= z2_hours_target)
);

-- Create indexes for common queries
CREATE INDEX idx_performance_goals_effective_dates ON performance_goals_timevarying(effective_start_date, effective_end_date);
CREATE INDEX idx_performance_goals_source ON performance_goals_timevarying(goal_source);
CREATE INDEX idx_performance_goals_priority ON performance_goals_timevarying(priority);

-- Add comments
COMMENT ON TABLE performance_goals_timevarying IS 'Time-varying performance goals with effective dates';
COMMENT ON COLUMN performance_goals_timevarying.protein_g_min IS 'Minimum acceptable daily protein (yellow threshold)';
COMMENT ON COLUMN performance_goals_timevarying.protein_g_target IS 'Target daily protein (green threshold)';
COMMENT ON COLUMN performance_goals_timevarying.fiber_g_min IS 'Minimum acceptable daily fiber (yellow threshold)';
COMMENT ON COLUMN performance_goals_timevarying.fiber_g_target IS 'Target daily fiber (green threshold)';
COMMENT ON COLUMN performance_goals_timevarying.net_deficit_max IS 'Maximum sustainable daily calorie deficit';
COMMENT ON COLUMN performance_goals_timevarying.net_deficit_target IS 'Target daily calorie deficit';
COMMENT ON COLUMN performance_goals_timevarying.z2_hours_min IS 'Minimum weekly Zone 2 hours (Attia)';
COMMENT ON COLUMN performance_goals_timevarying.z2_hours_target IS 'Target weekly Zone 2 hours (Attia)';
COMMENT ON COLUMN performance_goals_timevarying.z4_5_hours_min IS 'Minimum weekly high intensity hours';
COMMENT ON COLUMN performance_goals_timevarying.z4_5_hours_target IS 'Target weekly high intensity hours';
COMMENT ON COLUMN performance_goals_timevarying.strength_sessions_min IS 'Minimum weekly strength sessions';
COMMENT ON COLUMN performance_goals_timevarying.strength_sessions_target IS 'Target weekly strength sessions';
COMMENT ON COLUMN performance_goals_timevarying.ftp_watts_target IS 'Target FTP in watts';
COMMENT ON COLUMN performance_goals_timevarying.vo2max_target IS 'Target VO2max in ml/kg/min';
COMMENT ON COLUMN performance_goals_timevarying.body_fat_pct_max IS 'Maximum acceptable body fat percentage';
COMMENT ON COLUMN performance_goals_timevarying.body_fat_pct_target IS 'Target body fat percentage';
COMMENT ON COLUMN performance_goals_timevarying.lean_mass_kg_min IS 'Minimum acceptable lean body mass in kg';
COMMENT ON COLUMN performance_goals_timevarying.goal_source IS 'Source of goal framework (attia, custom, coach)';
COMMENT ON COLUMN performance_goals_timevarying.priority IS 'Primary focus (performance, health, recomp)';

-- Initial goal set based on Attia discussion
INSERT INTO performance_goals_timevarying VALUES (
    'v2025_09_25',
    '2025-09-25',
    NULL,  -- Current/ongoing
    
    -- Nutrition (Attia-influenced)
    140.0,   -- protein_g_min (yellow)
    190.0,   -- protein_g_target (green)
    25.0,    -- fiber_g_min
    35.0,    -- fiber_g_target  
    750,     -- net_deficit_max (red threshold)
    400,     -- net_deficit_target
    
    -- Training Volume (weekly)
    3.0,     -- z2_hours_min
    5.0,     -- z2_hours_target (Attia's 4+ hrs)
    0.75,    -- z4_5_hours_min (45 min/week)
    1.5,     -- z4_5_hours_target
    2,       -- strength_sessions_min
    3,       -- strength_sessions_target
    
    -- Performance Metrics
    250,     -- ftp_watts_target (example)
    40.0,    -- vo2max_target (example)
    
    -- Body Composition
    20.0,    -- body_fat_pct_max
    17.0,    -- body_fat_pct_target
    73.0,    -- lean_mass_kg_min (current ~74kg)
    
    'attia', 
    'recomp',
    'Post-Attia discussion: Higher protein, more Z2, preserve LBM',
    'mark',
    NOW()
);

-- View to get current goals
CREATE VIEW current_performance_goals AS
SELECT * FROM performance_goals_timevarying
WHERE CURRENT_DATE BETWEEN effective_start_date 
    AND COALESCE(effective_end_date, '9999-12-31');

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
