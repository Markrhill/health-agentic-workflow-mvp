-- Migration: Create performance_goals table
-- Date: 2025-09-16
-- Description: Forward-looking goals for coaching (targets for date, W/kg, deficit, optional TSS plan)

CREATE TABLE public.performance_goals (
    goal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_name text NOT NULL,
    target_date date NOT NULL,
    target_fat_mass_lb numeric,
    target_weight_kg numeric,
    target_ftp_w integer,
    target_ave_watts integer,
    bike_weight_kg numeric,
    target_w_per_kg numeric GENERATED ALWAYS AS (
        CASE 
            WHEN target_ave_watts IS NOT NULL AND target_weight_kg IS NOT NULL AND bike_weight_kg IS NOT NULL
            THEN target_ave_watts / (target_weight_kg + bike_weight_kg)
            ELSE NULL
        END
    ) STORED,
    target_daily_deficit integer NOT NULL DEFAULT 500,
    tss_ramp_plan jsonb,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now()
);

-- Add indexes for common queries
CREATE INDEX idx_performance_goals_target_date ON public.performance_goals(target_date);
CREATE INDEX idx_performance_goals_created_at ON public.performance_goals(created_at);

-- Add comments
COMMENT ON TABLE public.performance_goals IS 'Forward-looking goals for coaching (targets for date, W/kg, deficit, optional TSS plan)';
COMMENT ON COLUMN public.performance_goals.target_w_per_kg IS 'W/kg computed as target_ave_watts ÷ (target_weight_kg + bike_weight_kg)';
COMMENT ON COLUMN public.performance_goals.target_daily_deficit IS 'prescribed kcal/day deficit (default 500)';
COMMENT ON COLUMN public.performance_goals.tss_ramp_plan IS 'plan for weekly TSS progression';
