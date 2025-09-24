-- sql/migrations/20250922_07_hae_integration.sql
-- Add Health Auto Export (HAE) tables for aggregated JSON imports
-- Following established pattern from MFP/TrainingPeaks

BEGIN;

-- Raw HAE exports table
CREATE TABLE IF NOT EXISTS hae_raw (
    import_id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    date_range_start DATE NOT NULL,
    date_range_end DATE NOT NULL,
    raw_json JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    ingested_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Parsed metrics table
CREATE TABLE IF NOT EXISTS hae_metrics_parsed (
    date DATE NOT NULL,
    metric_name TEXT NOT NULL,
    value NUMERIC,
    unit TEXT,
    source TEXT,
    import_id INTEGER NOT NULL REFERENCES hae_raw(import_id),
    PRIMARY KEY (date, metric_name, source)
);

-- Indexes for performance
CREATE INDEX idx_hae_raw_dates ON hae_raw(date_range_start, date_range_end);
CREATE INDEX idx_hae_raw_processed ON hae_raw(processed);
CREATE INDEX idx_hae_metrics_date ON hae_metrics_parsed(date);
CREATE INDEX idx_hae_metrics_import ON hae_metrics_parsed(import_id);

-- Comments for documentation
COMMENT ON TABLE hae_raw IS 'Raw JSON exports from Health Auto Export app';
COMMENT ON TABLE hae_metrics_parsed IS 'Parsed daily metrics from HAE exports';
COMMENT ON COLUMN hae_metrics_parsed.metric_name IS 'e.g., dietary_energy, protein, carbohydrates, total_fat, active_energy, body_fat_percentage';
COMMENT ON COLUMN hae_metrics_parsed.source IS 'e.g., MyFitnessPal, Mark''s Apple Watch, Garmin Connect, Withings';

COMMIT;

-- Rollback instructions:
-- DROP TABLE IF EXISTS hae_metrics_parsed;
-- DROP TABLE IF EXISTS hae_raw CASCADE;
