-- Migration: Create weekly_coaching_snapshot table
-- Date: 2025-09-16
-- Description: Immutable weekly review snapshot Mon to Sun

CREATE TABLE public.weekly_coaching_snapshot (
    week_start date NOT NULL,
    week_end date NOT NULL,
    params_version_used text NOT NULL,
    avg_intake_kcal integer NOT NULL,
    avg_adj_exercise_kcal integer NOT NULL,
    avg_bmr_kcal integer NOT NULL,
    avg_net_kcal integer NOT NULL,
    days_on_target integer NOT NULL,
    predicted_delta_fm_kg numeric(10,3) NOT NULL,
    uncertainty_kg numeric(10,3) NOT NULL,
    observed_delta_fm_kg numeric(10,3) NOT NULL,
    within_expected_range boolean NOT NULL,
    decision text NOT NULL CHECK (decision IN ('Approve', 'Within Noise', 'Investigate')),
    completeness_pct numeric(5,2) NOT NULL,
    data_freeze_ts timestamp with time zone NOT NULL,
    reviewer text,
    decision_notes text,
    PRIMARY KEY (week_start),
    FOREIGN KEY (params_version_used) REFERENCES public.model_params_timevarying(params_version)
);

-- Add indexes for common queries
CREATE INDEX idx_weekly_snapshot_params_version ON public.weekly_coaching_snapshot(params_version_used);
CREATE INDEX idx_weekly_snapshot_decision ON public.weekly_coaching_snapshot(decision);
CREATE INDEX idx_weekly_snapshot_data_freeze ON public.weekly_coaching_snapshot(data_freeze_ts);

-- Add comments
COMMENT ON TABLE public.weekly_coaching_snapshot IS 'immutable weekly review snapshot Mon to Sun';
COMMENT ON COLUMN public.weekly_coaching_snapshot.week_start IS 'Monday (local)';
COMMENT ON COLUMN public.weekly_coaching_snapshot.week_end IS 'Sunday (local)';
COMMENT ON COLUMN public.weekly_coaching_snapshot.avg_net_kcal IS 'average net kcal over the week';
COMMENT ON COLUMN public.weekly_coaching_snapshot.days_on_target IS 'count of days with net <= -500';
COMMENT ON COLUMN public.weekly_coaching_snapshot.predicted_delta_fm_kg IS 'predicted fat mass change for the week';
COMMENT ON COLUMN public.weekly_coaching_snapshot.uncertainty_kg IS 'uncertainty band (±) for predicted change';
COMMENT ON COLUMN public.weekly_coaching_snapshot.observed_delta_fm_kg IS 'observed fat mass change (EMA Sun vs prior Sun)';
COMMENT ON COLUMN public.weekly_coaching_snapshot.within_expected_range IS 'true if observed within expected band';
COMMENT ON COLUMN public.weekly_coaching_snapshot.decision IS 'Approve | Within Noise | Investigate';
COMMENT ON COLUMN public.weekly_coaching_snapshot.completeness_pct IS 'percent of days with sufficient data';
COMMENT ON COLUMN public.weekly_coaching_snapshot.data_freeze_ts IS 'when this snapshot was computed';
