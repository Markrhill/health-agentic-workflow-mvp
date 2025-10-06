#!/usr/bin/env python3
# etl/hae_import.py

import json
import psycopg2
import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
from typing import Dict, List

# Load environment variables from project root
project_root = Path(__file__).parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

def validate_field_mapping(conn, import_id):
    """Factory Rule: Validate field mapping completeness after import"""
    query = """
    SELECT 
        COUNT(DISTINCT date) as total_days,
        COUNT(DISTINCT CASE WHEN metric_name = 'fiber' THEN date END) as fiber_days,
        COUNT(DISTINCT CASE WHEN metric_name = 'protein' THEN date END) as protein_days,
        COUNT(DISTINCT CASE WHEN metric_name = 'dietary_energy' THEN date END) as energy_days,
        COUNT(DISTINCT CASE WHEN metric_name = 'carbohydrates' THEN date END) as carb_days,
        COUNT(DISTINCT CASE WHEN metric_name = 'total_fat' THEN date END) as fat_days
    FROM hae_metrics_parsed 
    WHERE import_id = %s
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (import_id,))
        result = cur.fetchone()
        
    total_days, fiber_days, protein_days, energy_days, carb_days, fat_days = result
    
    print(f"Field mapping validation for import {import_id}:")
    print(f"  Total days: {total_days}")
    print(f"  Fiber coverage: {fiber_days}/{total_days} ({fiber_days/total_days*100:.1f}%)")
    print(f"  Protein coverage: {protein_days}/{total_days} ({protein_days/total_days*100:.1f}%)")
    print(f"  Energy coverage: {energy_days}/{total_days} ({energy_days/total_days*100:.1f}%)")
    print(f"  Carbohydrates coverage: {carb_days}/{total_days} ({carb_days/total_days*100:.1f}%)")
    print(f"  Fat coverage: {fat_days}/{total_days} ({fat_days/total_days*100:.1f}%)")
    
    # Alert if critical fields are missing
    # Note: HAE files often contain 2 days (current + previous day's body comp)
    # Missing nutrition for the previous day is EXPECTED - it's in that day's file
    if total_days > 1 and fiber_days == total_days - 1:
        print(f"ℹ️  Note: 1 day missing nutrition (expected for HAE 2-day file overlap)")
    elif fiber_days < total_days * 0.9:  # 90% threshold
        print(f"⚠️  WARNING: Fiber data missing for {total_days - fiber_days} days")
    if protein_days < total_days * 0.9 and not (total_days > 1 and protein_days == total_days - 1):
        print(f"⚠️  WARNING: Protein data missing for {total_days - protein_days} days")
    if energy_days < total_days * 0.9 and not (total_days > 1 and energy_days == total_days - 1):
        print(f"⚠️  WARNING: Energy data missing for {total_days - energy_days} days")
    if carb_days < total_days * 0.9 and not (total_days > 1 and carb_days == total_days - 1):
        print(f"⚠️  WARNING: Carbohydrates data missing for {total_days - carb_days} days")
    if fat_days < total_days * 0.9 and not (total_days > 1 and fat_days == total_days - 1):
        print(f"⚠️  WARNING: Fat data missing for {total_days - fat_days} days")

def import_hae_file(conn, file_path: str, overwrite_mode='update_nulls'):
    """
    Import HAE file with controlled overwrites
    
    overwrite_mode:
    - 'update_nulls': Only fill in missing data (default)
    - 'overwrite': Replace all data from HAE
    - 'skip_existing': Don't touch existing records
    """
    
    if not Path(file_path).exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    print(f"Loading {file_path}...")
    with open(file_path) as f:
        data = json.load(f)
    
    # Start audit logging
    filename = Path(file_path).name
    cur = conn.cursor()
    
    # Log import start
    cur.execute("SELECT log_import_start(%s, %s, %s)", 
                ('hae', filename, len(data.get('data', {}).get('metrics', []))))
    audit_id = cur.fetchone()[0]
    print(f"Started audit log: audit_id {audit_id}")
    
    # Extract date from filename
    date_str = filename.replace('HealthAutoExport-', '').replace('.json', '')
    parts = date_str.split('-')
    if len(parts) == 3:
        # Single date format: YYYY-MM-DD
        start_date = end_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
    elif len(parts) == 6:
        # Date range format: YYYY-MM-DD-YYYY-MM-DD
        start_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
        end_date = f"{parts[3]}-{parts[4]}-{parts[5]}"
    else:
        raise ValueError(f"Invalid filename format: {filename}")
    
    cur = conn.cursor()
    
    # Get file modification time for timestamp-based freshness
    file_mtime = datetime.fromtimestamp(Path(file_path).stat().st_mtime)
    
    # Check if already imported AND if we have a fresher file
    cur.execute("""
        SELECT import_id, ingested_at 
        FROM hae_raw 
        WHERE file_name = %s
    """, (filename,))
    existing = cur.fetchone()
    
    if existing:
        import_id, ingested_at = existing
        
        # PRINCIPAL: Always use freshest data
        # If file is newer than last import, force overwrite
        # Convert ingested_at to naive datetime for comparison (assumes both are local time)
        ingested_at_naive = ingested_at.replace(tzinfo=None) if ingested_at.tzinfo else ingested_at
        if file_mtime > ingested_at_naive:
            print(f"📁 File {filename} updated since last import (file: {file_mtime}, last import: {ingested_at})")
            print(f"🔄 Forcing overwrite to use freshest data (import_id {import_id})")
            overwrite_mode = 'overwrite'  # Override user's mode
        elif overwrite_mode == 'overwrite':
            print(f"Re-processing {filename} in overwrite mode (import_id {import_id})")
        else:
            print(f"File {filename} already imported as import_id {import_id} (no newer data)")
            return import_id
    
    # Insert or update raw data
    if overwrite_mode == 'overwrite' and existing:
        # Update existing record
        cur.execute("""
            UPDATE hae_raw 
            SET date_range_start = %s, date_range_end = %s, raw_json = %s, ingested_at = CURRENT_TIMESTAMP
            WHERE import_id = %s
        """, (start_date, end_date, json.dumps(data), import_id))
    else:
        # Insert new record
        cur.execute("""
            INSERT INTO hae_raw (file_name, date_range_start, date_range_end, raw_json)
            VALUES (%s, %s, %s, %s)
            RETURNING import_id
        """, (filename, start_date, end_date, json.dumps(data)))
        
        import_id = cur.fetchone()[0]
    
    # Clear existing metrics if in overwrite mode
    if overwrite_mode == 'overwrite' and existing:
        cur.execute("DELETE FROM hae_metrics_parsed WHERE import_id = %s", (import_id,))
        print(f"Cleared existing metrics for import_id {import_id}")
    
    # Proactive field validation - Alert on problems but don't block
    metrics_found = {m['name'] for m in data['data']['metrics']}
    critical_fields = {'dietary_energy', 'protein', 'fiber', 'carbohydrates', 'total_fat'}
    missing_fields = critical_fields - metrics_found
    
    if missing_fields:
        print(f"⚠️  MISSING FIELDS: {missing_fields}")
        print("   Data will be imported but incomplete")
        print("   To fix: Enable these in Apple Health → Sharing → Health Auto Export")
        print("")
        
        # Log missing fields to audit system
        for field in missing_fields:
            cur.execute("SELECT log_validation_issue(%s, %s, %s, %s, %s, %s)",
                       (audit_id, 'missing_field', 'warning', field, 
                        f"Field {field} not found in HAE export", None))
        # Continue processing - don't exit
    
    # Parse metrics with proper rounding and calculations
    body_comp_by_date = {}  # Track for fat mass calculation

    for metric in data['data']['metrics']:
        metric_name = metric['name']
        unit = metric.get('units', '')
        
        for entry in metric.get('data', []):
            date_str = entry['date'].split(' ')[0]
            source = entry.get('source', 'Unknown')
            
            # Store body composition data for calculation
            if metric_name == 'weight_body_mass':
                if date_str not in body_comp_by_date:
                    body_comp_by_date[date_str] = {}
                # Convert lbs to kg and round
                body_comp_by_date[date_str]['weight_kg'] = round(entry.get('qty') * 0.453592, 2)
                
            elif metric_name == 'body_fat_percentage':
                if date_str not in body_comp_by_date:
                    body_comp_by_date[date_str] = {}
                body_comp_by_date[date_str]['body_fat_pct'] = entry.get('qty')
            
            # Round numeric values appropriately
            if metric_name == 'dietary_energy':
                value = round(entry.get('qty'))  # Calories as integers
            elif metric_name in ['protein', 'carbohydrates', 'total_fat', 'fiber']:
                value = round(entry.get('qty'), 1)  # Macros to 1 decimal
            elif metric_name in ['weight_body_mass', 'lean_body_mass']:
                value = round(entry.get('qty'), 2)  # Weight to 2 decimals
            else:
                value = entry.get('qty')
            
            # Factory Rule: Validate critical fields are present
            critical_fields = ['dietary_energy', 'protein', 'fiber', 'carbohydrates', 'total_fat']
            if metric_name in critical_fields and value is None:
                print(f"WARNING: Critical field {metric_name} is NULL for date {date_str}")
            
            # Handle different value fields
            if metric_name == 'heart_rate':
                values = [
                    ('heart_rate_avg', entry.get('Avg')),
                    ('heart_rate_min', entry.get('Min')),
                    ('heart_rate_max', entry.get('Max'))
                ]
            else:
                values = [(metric_name, value)]
            
            for name, val in values:
                if val is not None:
                    cur.execute("""
                        INSERT INTO hae_metrics_parsed (date, metric_name, value, unit, source, import_id)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (date, metric_name, source) 
                        DO UPDATE SET value = EXCLUDED.value, import_id = EXCLUDED.import_id
                    """, (date_str, name, val, unit, source, import_id))
    
    # Calculate fat_mass_kg and fat_free_mass_kg
    for date_str, comp in body_comp_by_date.items():
        if 'weight_kg' in comp and 'body_fat_pct' in comp:
            weight_kg = comp['weight_kg']
            fat_pct = comp['body_fat_pct'] / 100
            fat_mass_kg = round(weight_kg * fat_pct, 2)
            fat_free_mass_kg = round(weight_kg * (1 - fat_pct), 2)
            
            # Insert calculated values
            cur.execute("""
                INSERT INTO hae_metrics_parsed (date, metric_name, value, unit, source, import_id)
                VALUES 
                    (%s, 'fat_mass_kg', %s, 'kg', 'Calculated', %s),
                    (%s, 'fat_free_mass_kg', %s, 'kg', 'Calculated', %s)
                ON CONFLICT (date, metric_name, source) DO UPDATE SET value = EXCLUDED.value
            """, (date_str, fat_mass_kg, import_id, date_str, fat_free_mass_kg, import_id))
    
    # Determine conflict resolution strategy
    if overwrite_mode == 'update_nulls':
        # Only update NULL values in daily_facts
        conflict_clause = """
        ON CONFLICT (fact_date) DO UPDATE SET
            intake_kcal = COALESCE(daily_facts.intake_kcal, EXCLUDED.intake_kcal),
            protein_g = COALESCE(daily_facts.protein_g, EXCLUDED.protein_g),
            carbs_g = COALESCE(daily_facts.carbs_g, EXCLUDED.carbs_g),
            fat_g = COALESCE(daily_facts.fat_g, EXCLUDED.fat_g),
            fiber_g = COALESCE(daily_facts.fiber_g, EXCLUDED.fiber_g),
            workout_kcal = COALESCE(daily_facts.workout_kcal, EXCLUDED.workout_kcal),
            weight_kg = COALESCE(daily_facts.weight_kg, EXCLUDED.weight_kg),
            fat_mass_kg = COALESCE(daily_facts.fat_mass_kg, EXCLUDED.fat_mass_kg),
            fat_free_mass_kg = COALESCE(daily_facts.fat_free_mass_kg, EXCLUDED.fat_free_mass_kg)
        """
    elif overwrite_mode == 'overwrite':
        # Replace with new data
        conflict_clause = """
        ON CONFLICT (fact_date) DO UPDATE SET
            intake_kcal = EXCLUDED.intake_kcal,
            protein_g = EXCLUDED.protein_g,
            carbs_g = EXCLUDED.carbs_g,
            fat_g = EXCLUDED.fat_g,
            fiber_g = EXCLUDED.fiber_g,
            workout_kcal = EXCLUDED.workout_kcal,
            weight_kg = EXCLUDED.weight_kg,
            fat_mass_kg = EXCLUDED.fat_mass_kg,
            fat_free_mass_kg = EXCLUDED.fat_free_mass_kg
        """
    else:  # skip_existing
        conflict_clause = "ON CONFLICT (fact_date) DO NOTHING"
    
    # Update daily_facts
    # CRITICAL FIX: Consolidate ALL metrics for dates in this import, not just this import_id
    # This handles HAE's 2-day file overlap where Oct 5 file contains Oct 4 body comp
    # but Oct 4 nutrition is in Oct 4 file (different import_id)
    query = f"""
        WITH dates_in_import AS (
            SELECT DISTINCT date FROM hae_metrics_parsed WHERE import_id = %s
        )
        INSERT INTO daily_facts (
            fact_date, intake_kcal, protein_g, carbs_g, fat_g, fiber_g,
            workout_kcal, weight_kg, fat_mass_kg, fat_free_mass_kg
        )
        SELECT 
            hmp.date,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'dietary_energy' THEN hmp.value END)) as intake_kcal,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'protein' THEN hmp.value END), 1) as protein_g,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'carbohydrates' THEN hmp.value END), 1) as carbs_g,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'total_fat' THEN hmp.value END), 1) as fat_g,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'fiber' THEN hmp.value END), 1) as fiber_g,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'active_energy' THEN hmp.value END)) as workout_kcal,
            ROUND(MAX(CASE WHEN hmp.metric_name = 'weight_body_mass' THEN hmp.value * 0.453592 END), 2) as weight_kg,
            MAX(CASE WHEN hmp.metric_name = 'fat_mass_kg' THEN hmp.value END) as fat_mass_kg,
            MAX(CASE WHEN hmp.metric_name = 'fat_free_mass_kg' THEN hmp.value END) as fat_free_mass_kg
        FROM hae_metrics_parsed hmp
        INNER JOIN dates_in_import dii ON hmp.date = dii.date
        GROUP BY hmp.date
        {conflict_clause}
    """
    cur.execute(query, (import_id,))
    
    # Mark processed
    cur.execute("UPDATE hae_raw SET processed = TRUE WHERE import_id = %s", (import_id,))
    
    # Complete audit logging
    cur.execute("""
        UPDATE data_import_audit 
        SET import_status = 'success', 
            records_processed = (SELECT COUNT(*) FROM hae_metrics_parsed WHERE import_id = %s),
            hae_import_id = %s
        WHERE audit_id = %s
    """, (import_id, import_id, audit_id))
    
    conn.commit()
    print(f"Imported {filename} as import_id {import_id}")
    print(f"Audit completed: audit_id {audit_id}")
    return import_id

if __name__ == "__main__":
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python hae_import.py <path_to_json> [overwrite_mode]")
        print("overwrite_mode: update_nulls (default), overwrite, skip_existing")
        sys.exit(1)
    
    file_path = sys.argv[1]
    overwrite_mode = sys.argv[2] if len(sys.argv) == 3 else 'update_nulls'
    
    if overwrite_mode not in ['update_nulls', 'overwrite', 'skip_existing']:
        print("Error: overwrite_mode must be one of: update_nulls, overwrite, skip_existing")
        sys.exit(1)
    
    # Get database URL from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("Error: DATABASE_URL not set in .env")
        sys.exit(1)
    
    # Connect and import
    conn = psycopg2.connect(database_url)
    try:
        import_id = import_hae_file(conn, file_path, overwrite_mode)
        
        # Factory Rule: Validate field mapping after import
        validate_field_mapping(conn, import_id)
    finally:
        conn.close()
