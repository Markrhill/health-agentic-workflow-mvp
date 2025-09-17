-- Migration: Create model_params_timevarying table
-- Date: 2025-09-16
-- Description: Versioned model parameters effective dated

CREATE TABLE public.model_params_timevarying (
    params_version text PRIMARY KEY,
    effective_start_date date NOT NULL,
    effective_end_date date,
    c_exercise_comp numeric NOT NULL CHECK (c_exercise_comp >= 0 AND c_exercise_comp <= 1),
    alpha_fm numeric NOT NULL CHECK (alpha_fm > 0 AND alpha_fm <= 1),
    alpha_lbm numeric NOT NULL CHECK (alpha_lbm > 0 AND alpha_lbm <= 1),
    bmr0_kcal numeric NOT NULL CHECK (bmr0_kcal > 0),
    k_lbm_kcal_per_kg numeric NOT NULL CHECK (k_lbm_kcal_per_kg > 0),
    kcal_per_kg_fat numeric NOT NULL CHECK (kcal_per_kg_fat > 0),
    method_notes text,
    approved_by text,
    approved_at timestamp with time zone
);

-- Add indexes for common queries
CREATE INDEX idx_model_params_effective_dates ON public.model_params_timevarying(effective_start_date, effective_end_date);
CREATE INDEX idx_model_params_approved_at ON public.model_params_timevarying(approved_at);

-- Add comments
COMMENT ON TABLE public.model_params_timevarying IS 'versioned model parameters effective dated';
COMMENT ON COLUMN public.model_params_timevarying.c_exercise_comp IS 'exercise compensation factor c in [0,1]';
COMMENT ON COLUMN public.model_params_timevarying.alpha_fm IS 'EMA alpha for fat mass (kg)';
COMMENT ON COLUMN public.model_params_timevarying.alpha_lbm IS 'EMA alpha for LBM used for BMR stability';
COMMENT ON COLUMN public.model_params_timevarying.bmr0_kcal IS 'BMR intercept (kcal/day)';
COMMENT ON COLUMN public.model_params_timevarying.k_lbm_kcal_per_kg IS 'BMR slope per kg of LBM';
COMMENT ON COLUMN public.model_params_timevarying.kcal_per_kg_fat IS 'kcal-to-kg mapping for fat mass (e.g., 7700)';
