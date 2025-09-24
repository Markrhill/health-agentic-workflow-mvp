-- sql/migrations/20250925_01_audit_system.sql
-- General purpose audit system for all data pipelines

-- 1. Core audit log table (source-agnostic)
CREATE TABLE data_import_audit (
    audit_id SERIAL PRIMARY KEY,
    source_system VARCHAR(50) NOT NULL,  -- 'hae', 'strava', 'withings', 'manual_csv'
    source_file VARCHAR(255),            -- filename or API endpoint
    import_timestamp TIMESTAMP DEFAULT NOW(),
    import_status VARCHAR(20) NOT NULL,  -- 'success', 'partial', 'failed'
    
    -- Metrics
    records_expected INTEGER,
    records_processed INTEGER,
    records_failed INTEGER,
    
    -- Flexible metadata
    import_metadata JSONB DEFAULT '{}',  -- source-specific details
    
    -- Foreign keys to source tables (nullable)
    hae_import_id INTEGER REFERENCES hae_raw(import_id)
    -- future: strava_import_id, withings_import_id, etc
);

-- Create indexes after table creation
CREATE INDEX idx_audit_source_time ON data_import_audit (source_system, import_timestamp DESC);

-- 2. Validation issues table (what went wrong)
CREATE TABLE data_validation_issues (
    issue_id SERIAL PRIMARY KEY,
    audit_id INTEGER REFERENCES data_import_audit(audit_id) ON DELETE CASCADE,
    
    issue_type VARCHAR(50) NOT NULL,     -- 'missing_field', 'invalid_value', 'duplicate_data'
    severity VARCHAR(20) NOT NULL,       -- 'critical', 'warning', 'info'
    field_name VARCHAR(100),             -- which field had the issue
    
    issue_description TEXT NOT NULL,
    affected_dates DATE[],               -- which dates were affected
    affected_count INTEGER,              -- how many records affected
    
    resolution_status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'fixed', 'ignored'
    resolution_notes TEXT,
    resolved_at TIMESTAMP
);

-- Create indexes for validation issues
CREATE INDEX idx_issues_audit ON data_validation_issues (audit_id);
CREATE INDEX idx_issues_status ON data_validation_issues (resolution_status, severity);

-- 3. Field coverage tracking (what percentage of expected data did we get)
CREATE TABLE field_coverage_metrics (
    metric_id SERIAL PRIMARY KEY,
    audit_id INTEGER REFERENCES data_import_audit(audit_id) ON DELETE CASCADE,
    
    field_name VARCHAR(100) NOT NULL,
    expected_count INTEGER,
    actual_count INTEGER,
    null_count INTEGER,
    coverage_percent NUMERIC(5,2) GENERATED ALWAYS AS 
        (CASE WHEN expected_count > 0 
              THEN (actual_count::NUMERIC / expected_count * 100) 
              ELSE 0 END) STORED,
    
    UNIQUE(audit_id, field_name)
);

-- 4. Summary view for recent issues
CREATE VIEW recent_import_health AS
SELECT 
    a.source_system,
    a.import_timestamp::DATE as import_date,
    a.import_status,
    COUNT(DISTINCT i.issue_id) as issue_count,
    COUNT(DISTINCT CASE WHEN i.severity = 'critical' THEN i.issue_id END) as critical_count,
    COUNT(DISTINCT CASE WHEN i.severity = 'warning' THEN i.issue_id END) as warning_count,
    STRING_AGG(DISTINCT i.field_name, ', ') as affected_fields,
    ROUND(AVG(c.coverage_percent), 1) as avg_field_coverage
FROM data_import_audit a
LEFT JOIN data_validation_issues i ON a.audit_id = i.audit_id
LEFT JOIN field_coverage_metrics c ON a.audit_id = c.audit_id
WHERE a.import_timestamp > NOW() - INTERVAL '7 days'
GROUP BY a.source_system, a.import_timestamp::DATE, a.import_status, a.import_timestamp
ORDER BY a.import_timestamp DESC;

-- 5. Helper function to log imports
CREATE OR REPLACE FUNCTION log_import_start(
    p_source VARCHAR,
    p_file VARCHAR,
    p_expected_records INTEGER DEFAULT NULL
) RETURNS INTEGER AS $$
DECLARE
    v_audit_id INTEGER;
BEGIN
    INSERT INTO data_import_audit (
        source_system, source_file, import_status, records_expected
    ) VALUES (
        p_source, p_file, 'in_progress', p_expected_records
    ) RETURNING audit_id INTO v_audit_id;
    
    RETURN v_audit_id;
END;
$$ LANGUAGE plpgsql;

-- 6. Helper function to log issues
CREATE OR REPLACE FUNCTION log_validation_issue(
    p_audit_id INTEGER,
    p_type VARCHAR,
    p_severity VARCHAR,
    p_field VARCHAR,
    p_description TEXT,
    p_affected_count INTEGER DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
    INSERT INTO data_validation_issues (
        audit_id, issue_type, severity, field_name, 
        issue_description, affected_count
    ) VALUES (
        p_audit_id, p_type, p_severity, p_field, 
        p_description, p_affected_count
    );
END;
$$ LANGUAGE plpgsql;

-- 7. Dashboard query examples
COMMENT ON VIEW recent_import_health IS 
'Quick health check: SELECT * FROM recent_import_health WHERE critical_count > 0;';
