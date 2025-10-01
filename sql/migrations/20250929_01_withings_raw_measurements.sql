-- Migration: Create withings_raw_measurements table
-- Date: 2025-09-29
-- Purpose: Store raw Withings weight measurements with standardized timestamps

-- Create the withings_raw_measurements table
CREATE TABLE IF NOT EXISTS withings_raw_measurements (
    id SERIAL PRIMARY KEY,
    measurement_id VARCHAR(50) UNIQUE NOT NULL,
    weight_kg DECIMAL(5,2) NOT NULL,
    timestamp_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    timestamp_user TIMESTAMP WITH TIME ZONE NOT NULL,
    original_timezone VARCHAR(50),
    user_timezone VARCHAR(50),
    source_format VARCHAR(30) DEFAULT 'withings_api',
    raw_value INTEGER,  -- Original API value for audit
    raw_unit INTEGER,   -- Original API unit for audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_withings_timestamp_utc ON withings_raw_measurements(timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_withings_timestamp_user ON withings_raw_measurements(timestamp_user);
CREATE INDEX IF NOT EXISTS idx_withings_measurement_id ON withings_raw_measurements(measurement_id);
CREATE INDEX IF NOT EXISTS idx_withings_created_at ON withings_raw_measurements(created_at);

-- Add comments for documentation
COMMENT ON TABLE withings_raw_measurements IS 'Raw weight measurements from Withings API with standardized timestamps';
COMMENT ON COLUMN withings_raw_measurements.measurement_id IS 'Unique Withings measurement group ID';
COMMENT ON COLUMN withings_raw_measurements.weight_kg IS 'Weight in kilograms (converted from API units)';
COMMENT ON COLUMN withings_raw_measurements.timestamp_utc IS 'Measurement timestamp in UTC';
COMMENT ON COLUMN withings_raw_measurements.timestamp_user IS 'Measurement timestamp in user timezone';
COMMENT ON COLUMN withings_raw_measurements.original_timezone IS 'Original timezone from Withings API';
COMMENT ON COLUMN withings_raw_measurements.user_timezone IS 'User-configured timezone for display';
COMMENT ON COLUMN withings_raw_measurements.source_format IS 'Data source format identifier';
COMMENT ON COLUMN withings_raw_measurements.raw_value IS 'Original API value before conversion';
COMMENT ON COLUMN withings_raw_measurements.raw_unit IS 'Original API unit before conversion';

-- Create a view for recent measurements (last 30 days)
CREATE OR REPLACE VIEW withings_recent_measurements AS
SELECT 
    measurement_id,
    weight_kg,
    timestamp_utc,
    timestamp_user,
    original_timezone,
    user_timezone,
    raw_value,
    raw_unit,
    created_at
FROM withings_raw_measurements
WHERE timestamp_utc >= NOW() - INTERVAL '30 days'
ORDER BY timestamp_utc DESC;

COMMENT ON VIEW withings_recent_measurements IS 'Recent Withings measurements from the last 30 days';

-- Create a function to get latest measurement timestamp
CREATE OR REPLACE FUNCTION get_latest_withings_timestamp()
RETURNS TIMESTAMP WITH TIME ZONE AS $$
BEGIN
    RETURN (
        SELECT MAX(timestamp_utc)
        FROM withings_raw_measurements
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_latest_withings_timestamp() IS 'Returns the timestamp of the most recent Withings measurement';

-- Create a function to get measurement statistics
CREATE OR REPLACE FUNCTION get_withings_stats()
RETURNS TABLE(
    total_count BIGINT,
    latest_measurement TIMESTAMP WITH TIME ZONE,
    earliest_measurement TIMESTAMP WITH TIME ZONE,
    min_weight DECIMAL(5,2),
    max_weight DECIMAL(5,2),
    avg_weight DECIMAL(5,2),
    unique_measurements BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*) as total_count,
        MAX(timestamp_utc) as latest_measurement,
        MIN(timestamp_utc) as earliest_measurement,
        MIN(weight_kg) as min_weight,
        MAX(weight_kg) as max_weight,
        AVG(weight_kg) as avg_weight,
        COUNT(DISTINCT measurement_id) as unique_measurements
    FROM withings_raw_measurements;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_withings_stats() IS 'Returns statistics about Withings measurements';

-- Insert sample data for testing (optional)
-- INSERT INTO withings_raw_measurements (
--     measurement_id, weight_kg, timestamp_utc, timestamp_user,
--     original_timezone, user_timezone, source_format,
--     raw_value, raw_unit
-- ) VALUES (
--     'test_123', 75.5, '2024-09-29T19:49:00.000Z', '2024-09-29T12:49:00.000-07:00',
--     'UTC', 'America/Los_Angeles', 'withings_api',
--     75500, -3
-- );
