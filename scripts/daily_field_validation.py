#!/usr/bin/env python3
"""
Daily Field Validation Script
Factory Rule: ETL Field Mapping Completeness Check

This script validates that critical fields are not missing for extended periods
and alerts when data source transitions cause field mapping issues.
"""

import os
import sys
import yaml
import psycopg2
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

def load_config() -> Dict:
    """Load field mapping configuration"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'field_mapping.yaml')
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(os.getenv('DATABASE_URL', 'postgresql://postgres@localhost:5432/health_mvp'))

def check_consecutive_nulls(conn, field: str, threshold: int) -> Tuple[bool, int]:
    """Check for consecutive NULL values in a field"""
    query = f"""
    WITH null_gaps AS (
        SELECT 
            fact_date,
            {field},
            LAG(fact_date) OVER (ORDER BY fact_date) as prev_date,
            CASE 
                WHEN {field} IS NULL THEN 1 
                ELSE 0 
            END as is_null
        FROM daily_facts 
        WHERE fact_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY fact_date
    ),
    null_sequences AS (
        SELECT 
            fact_date,
            {field},
            SUM(is_null) OVER (
                PARTITION BY grp 
                ORDER BY fact_date 
                ROWS UNBOUNDED PRECEDING
            ) as consecutive_nulls
        FROM (
            SELECT 
                fact_date,
                {field},
                is_null,
                SUM(CASE WHEN is_null = 0 THEN 1 ELSE 0 END) 
                    OVER (ORDER BY fact_date) as grp
            FROM null_gaps
        ) t
    )
    SELECT MAX(consecutive_nulls) as max_consecutive
    FROM null_sequences
    WHERE is_null = 1
    """
    
    with conn.cursor() as cur:
        cur.execute(query)
        result = cur.fetchone()
        max_consecutive = result[0] if result[0] else 0
        
    return max_consecutive >= threshold, max_consecutive

def check_field_completeness(conn, source: str, target: str, fields: List[str], tolerance: float) -> Dict:
    """Check field completeness between source and target"""
    results = {}
    
    for field in fields:
        # This is a simplified check - in practice, you'd need to map
        # source fields to target fields based on the mapping config
        query = f"""
        SELECT 
            COUNT(*) as total_days,
            COUNT({field}) as non_null_days,
            ROUND(COUNT({field})::numeric / COUNT(*), 3) as completeness_ratio
        FROM daily_facts 
        WHERE fact_date >= CURRENT_DATE - INTERVAL '30 days'
        """
        
        with conn.cursor() as cur:
            cur.execute(query)
            result = cur.fetchone()
            
        results[field] = {
            'total_days': result[0],
            'non_null_days': result[1],
            'completeness_ratio': float(result[2]),
            'meets_tolerance': float(result[2]) >= tolerance
        }
    
    return results

def log_alert(conn, field: str, message: str, severity: str = 'WARNING'):
    """Log alert to audit_hil table"""
    query = """
    INSERT INTO audit_hil (snapshot_week_start, action, actor, rationale, created_at)
    VALUES (CURRENT_DATE, %s, %s, %s, NOW())
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (f"FIELD_VALIDATION_{severity}", "system", message))

def main():
    """Main validation function"""
    config = load_config()
    conn = get_db_connection()
    
    print(f"Running daily field validation at {datetime.now()}")
    
    # Check consecutive NULL values
    print("\n=== Consecutive NULL Checks ===")
    for check in config['validation_rules']['daily_checks']:
        field = check['field']
        threshold = check['alert_threshold']
        message_template = check['message']
        
        exceeds_threshold, consecutive_count = check_consecutive_nulls(conn, field, threshold)
        
        if exceeds_threshold:
            message = message_template.format(count=consecutive_count)
            print(f"❌ {message}")
            log_alert(conn, field, message, 'ERROR')
        else:
            print(f"✅ {field}: {consecutive_count} consecutive NULLs (threshold: {threshold})")
    
    # Check field completeness
    print("\n=== Field Completeness Checks ===")
    for check in config['validation_rules']['completeness_checks']:
        source = check['source']
        target = check['target']
        fields = check['fields']
        tolerance = check['tolerance']
        
        print(f"\nChecking {source} → {target}:")
        results = check_field_completeness(conn, source, target, fields, tolerance)
        
        for field, result in results.items():
            status = "✅" if result['meets_tolerance'] else "❌"
            print(f"  {status} {field}: {result['completeness_ratio']:.1%} "
                  f"({result['non_null_days']}/{result['total_days']} days)")
            
            if not result['meets_tolerance']:
                message = f"Field {field} completeness {result['completeness_ratio']:.1%} below tolerance {tolerance:.1%}"
                log_alert(conn, field, message, 'WARNING')
    
    conn.commit()
    conn.close()
    print(f"\nValidation complete at {datetime.now()}")

if __name__ == "__main__":
    main()
