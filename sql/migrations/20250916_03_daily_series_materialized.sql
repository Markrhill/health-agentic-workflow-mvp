-- Migration: Create daily_series_materialized table
-- Date: 2025-09-16
-- Description: Derived daily series for UI and snapshots

CREATE TABLE public.daily_series_materialized (
    fact_date date NOT NULL,
    params_version_used text NOT NULL,
    fat_mass_ema_kg numeric(10,3) NOT NULL,
    lbm_ema_kg_for_bmr numeric(10,3) NOT NULL,
    bmr_kcal integer NOT NULL,
    adj_exercise_kcal integer NOT NULL,
    net_kcal integer NOT NULL,
    computed_at timestamp with time zone NOT NULL DEFAULT now(),
    compute_run_id text,
    PRIMARY KEY (fact_date),
    FOREIGN KEY (params_version_used) REFERENCES public.model_params_timevarying(params_version)
);

-- Add indexes for common queries
CREATE INDEX idx_daily_series_params_version ON public.daily_series_materialized(params_version_used);
CREATE INDEX idx_daily_series_computed_at ON public.daily_series_materialized(computed_at);
CREATE INDEX idx_daily_series_net_kcal ON public.daily_series_materialized(net_kcal);

-- Add comments
COMMENT ON TABLE public.daily_series_materialized IS 'derived daily series for UI and snapshots';
COMMENT ON COLUMN public.daily_series_materialized.fat_mass_ema_kg IS 'EMA-smoothed fat mass (kg)';
COMMENT ON COLUMN public.daily_series_materialized.lbm_ema_kg_for_bmr IS 'LBM used for BMR calc after light EMA';
COMMENT ON COLUMN public.daily_series_materialized.bmr_kcal IS 'basal metabolic rate (kcal/day), computed as bmr0_kcal + k_lbm_kcal_per_kg * lbm_ema_kg_for_bmr for params_version_used';
COMMENT ON COLUMN public.daily_series_materialized.adj_exercise_kcal IS '(1 - c) * workout_kcal using params_version_used';
COMMENT ON COLUMN public.daily_series_materialized.net_kcal IS 'intake_kcal - adj_exercise_kcal - bmr_kcal';
COMMENT ON COLUMN public.daily_series_materialized.compute_run_id IS 'batch/run id for reproducibility';
