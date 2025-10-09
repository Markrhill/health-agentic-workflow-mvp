-- Migration 010: Add HAE last updated tracking
-- Purpose: Track when HAE data was last successfully refreshed to enable incremental updates
-- Date: 2025-10-07

-- Create table to track last successful HAE refresh
CREATE TABLE IF NOT EXISTS hae_last_updated (
    id INTEGER PRIMARY KEY DEFAULT 1,
    last_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_by VARCHAR(50) NOT NULL, -- 'cron', 'manual_refresh', 'backfill'
    notes TEXT,
    CONSTRAINT single_row CHECK (id = 1)
);

-- Initialize with a reasonable default (e.g., Oct 5 when we know data was good)
INSERT INTO hae_last_updated (id, last_updated_at, updated_by, notes)
VALUES (1, '2025-10-05 00:00:00-07', 'migration', 'Initial value set by migration 010')
ON CONFLICT (id) DO NOTHING;

-- Add index for quick lookups (though there's only 1 row)
CREATE INDEX IF NOT EXISTS idx_hae_last_updated_at ON hae_last_updated(last_updated_at);

COMMENT ON TABLE hae_last_updated IS 'Tracks when HAE data was last successfully refreshed. Single row table (id=1) acting as a global watermark for incremental updates.';
COMMENT ON COLUMN hae_last_updated.last_updated_at IS 'Timestamp of last successful HAE refresh';
COMMENT ON COLUMN hae_last_updated.updated_by IS 'Source of update: cron, manual_refresh, or backfill';
COMMENT ON COLUMN hae_last_updated.notes IS 'Optional notes about the update';

