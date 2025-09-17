-- Migration: Create audit_hil table
-- Date: 2025-09-16
-- Description: Audit log for human-in-the-loop decisions

CREATE TABLE public.audit_hil (
    snapshot_week_start date NOT NULL,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    action text NOT NULL CHECK (action IN ('Approve', 'Defer', 'ChangeParams')),
    actor text NOT NULL,
    rationale text,
    previous_params_version text,
    new_params_version text,
    PRIMARY KEY (snapshot_week_start, created_at),
    FOREIGN KEY (snapshot_week_start) REFERENCES public.weekly_coaching_snapshot(week_start),
    FOREIGN KEY (previous_params_version) REFERENCES public.model_params_timevarying(params_version),
    FOREIGN KEY (new_params_version) REFERENCES public.model_params_timevarying(params_version)
);

-- Add indexes for common queries
CREATE INDEX idx_audit_hil_action ON public.audit_hil(action);
CREATE INDEX idx_audit_hil_actor ON public.audit_hil(actor);
CREATE INDEX idx_audit_hil_created_at ON public.audit_hil(created_at);

-- Add comments
COMMENT ON TABLE public.audit_hil IS 'audit log for human-in-the-loop decisions';
COMMENT ON COLUMN public.audit_hil.snapshot_week_start IS 'FK to weekly_coaching_snapshot.week_start';
COMMENT ON COLUMN public.audit_hil.action IS 'Approve | Defer | ChangeParams';
COMMENT ON COLUMN public.audit_hil.actor IS 'user id or email';
COMMENT ON COLUMN public.audit_hil.rationale IS 'freeform rationale';
COMMENT ON COLUMN public.audit_hil.previous_params_version IS 'params before change';
COMMENT ON COLUMN public.audit_hil.new_params_version IS 'params after change (if any)';
COMMENT ON COLUMN public.audit_hil.created_at IS 'log timestamp';
