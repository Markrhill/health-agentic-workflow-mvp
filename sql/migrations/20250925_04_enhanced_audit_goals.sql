-- sql/migrations/20250925_04_enhanced_audit_goals.sql
-- Enhanced Audit System for Goal Changes
-- Date: 2025-09-25
-- Description: Extend audit system to capture goal version changes and parameter adjustments

-- Add goal tracking columns to existing audit_hil table
ALTER TABLE public.audit_hil 
ADD COLUMN previous_goal_version VARCHAR(20),
ADD COLUMN new_goal_version VARCHAR(20),
ADD COLUMN goal_change_reason TEXT,
ADD COLUMN source_attribution VARCHAR(50); -- 'attia', 'custom', 'coach'

-- Add foreign key constraints for goal versions
ALTER TABLE public.audit_hil 
ADD CONSTRAINT fk_audit_hil_previous_goal_version 
FOREIGN KEY (previous_goal_version) REFERENCES public.performance_goals_timevarying(goal_version);

ALTER TABLE public.audit_hil 
ADD CONSTRAINT fk_audit_hil_new_goal_version 
FOREIGN KEY (new_goal_version) REFERENCES public.performance_goals_timevarying(goal_version);

-- Add indexes for goal-related queries
CREATE INDEX idx_audit_hil_goal_changes ON public.audit_hil(previous_goal_version, new_goal_version);
CREATE INDEX idx_audit_hil_source_attribution ON public.audit_hil(source_attribution);

-- Add comments for new columns
COMMENT ON COLUMN public.audit_hil.previous_goal_version IS 'Goal version before change (FK to performance_goals_timevarying)';
COMMENT ON COLUMN public.audit_hil.new_goal_version IS 'Goal version after change (FK to performance_goals_timevarying)';
COMMENT ON COLUMN public.audit_hil.goal_change_reason IS 'Reason for goal change (e.g., "Attia podcast discussion", "coach recommendation")';
COMMENT ON COLUMN public.audit_hil.source_attribution IS 'Source of goal framework change (attia, custom, coach)';

-- Function to log goal changes
CREATE OR REPLACE FUNCTION log_goal_change(
    p_snapshot_week_start DATE,
    p_actor TEXT,
    p_previous_goal_version VARCHAR(20),
    p_new_goal_version VARCHAR(20),
    p_goal_change_reason TEXT DEFAULT NULL,
    p_source_attribution VARCHAR(50) DEFAULT NULL,
    p_rationale TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO public.audit_hil (
        snapshot_week_start,
        action,
        actor,
        rationale,
        previous_goal_version,
        new_goal_version,
        goal_change_reason,
        source_attribution,
        created_at
    ) VALUES (
        p_snapshot_week_start,
        'ChangeGoals',
        p_actor,
        p_rationale,
        p_previous_goal_version,
        p_new_goal_version,
        p_goal_change_reason,
        p_source_attribution,
        NOW()
    );
END;
$$ LANGUAGE plpgsql;

-- Function to log combined parameter and goal changes
CREATE OR REPLACE FUNCTION log_parameter_and_goal_change(
    p_snapshot_week_start DATE,
    p_actor TEXT,
    p_previous_params_version TEXT,
    p_new_params_version TEXT,
    p_previous_goal_version VARCHAR(20),
    p_new_goal_version VARCHAR(20),
    p_goal_change_reason TEXT DEFAULT NULL,
    p_source_attribution VARCHAR(50) DEFAULT NULL,
    p_rationale TEXT DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO public.audit_hil (
        snapshot_week_start,
        action,
        actor,
        rationale,
        previous_params_version,
        new_params_version,
        previous_goal_version,
        new_goal_version,
        goal_change_reason,
        source_attribution,
        created_at
    ) VALUES (
        p_snapshot_week_start,
        'ChangeParamsAndGoals',
        p_actor,
        p_rationale,
        p_previous_params_version,
        p_new_params_version,
        p_previous_goal_version,
        p_new_goal_version,
        p_goal_change_reason,
        p_source_attribution,
        NOW()
    );
END;
$$ LANGUAGE plpgsql;

-- Update the action constraint to include new actions
ALTER TABLE public.audit_hil 
DROP CONSTRAINT IF EXISTS audit_hil_action_check;

ALTER TABLE public.audit_hil 
ADD CONSTRAINT audit_hil_action_check 
CHECK (action IN ('Approve', 'Defer', 'ChangeParams', 'ChangeGoals', 'ChangeParamsAndGoals'));

-- View to show recent goal changes with details
CREATE VIEW recent_goal_changes AS
SELECT 
    ah.snapshot_week_start,
    ah.created_at,
    ah.actor,
    ah.previous_goal_version,
    ah.new_goal_version,
    ah.goal_change_reason,
    ah.source_attribution,
    ah.rationale,
    -- Previous goal details
    pgv_prev.goal_source as prev_goal_source,
    pgv_prev.priority as prev_priority,
    pgv_prev.protein_g_target as prev_protein_target,
    pgv_prev.body_fat_pct_target as prev_body_fat_target,
    -- New goal details
    pgv_new.goal_source as new_goal_source,
    pgv_new.priority as new_priority,
    pgv_new.protein_g_target as new_protein_target,
    pgv_new.body_fat_pct_target as new_body_fat_target
FROM public.audit_hil ah
LEFT JOIN public.performance_goals_timevarying pgv_prev 
    ON ah.previous_goal_version = pgv_prev.goal_version
LEFT JOIN public.performance_goals_timevarying pgv_new 
    ON ah.new_goal_version = pgv_new.goal_version
WHERE ah.action IN ('ChangeGoals', 'ChangeParamsAndGoals')
    AND ah.created_at > NOW() - INTERVAL '90 days'
ORDER BY ah.created_at DESC;

-- View to show audit trail for a specific week
CREATE VIEW weekly_audit_trail AS
SELECT 
    ah.snapshot_week_start,
    ah.created_at,
    ah.actor,
    ah.action,
    ah.rationale,
    ah.previous_params_version,
    ah.new_params_version,
    ah.previous_goal_version,
    ah.new_goal_version,
    ah.goal_change_reason,
    ah.source_attribution,
    -- Goal change summary
    CASE 
        WHEN ah.previous_goal_version IS DISTINCT FROM ah.new_goal_version THEN
            'Goal changed from ' || COALESCE(ah.previous_goal_version, 'none') || 
            ' to ' || COALESCE(ah.new_goal_version, 'none')
        ELSE NULL
    END as goal_change_summary,
    -- Parameter change summary
    CASE 
        WHEN ah.previous_params_version IS DISTINCT FROM ah.new_params_version THEN
            'Params changed from ' || COALESCE(ah.previous_params_version, 'none') || 
            ' to ' || COALESCE(ah.new_params_version, 'none')
        ELSE NULL
    END as param_change_summary
FROM public.audit_hil ah
ORDER BY ah.snapshot_week_start DESC, ah.created_at DESC;
