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

# Load environment variables
load_dotenv()

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
    
    # Extract date range from filename
    filename = Path(file_path).name
    parts = filename.replace('HealthAutoExport-', '').replace('.json', '').split('-')
    start_date = f"{parts[0]}-{parts[1]}-{parts[2]}"
    end_date = f"{parts[3]}-{parts[4]}-{parts[5]}"
    
    cur = conn.cursor()
    
    # Check if already imported
    cur.execute("SELECT import_id FROM hae_raw WHERE file_name = %s", (filename,))
    existing = cur.fetchone()
    if existing:
        print(f"File {filename} already imported as import_id {existing[0]}")
        return existing[0]
    
    # Insert raw
    cur.execute("""
        INSERT INTO hae_raw (file_name, date_range_start, date_range_end, raw_json)
        VALUES (%s, %s, %s, %s)
        RETURNING import_id
    """, (filename, start_date, end_date, json.dumps(data)))
    
    import_id = cur.fetchone()[0]
    
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
            elif metric_name in ['protein', 'carbohydrates', 'total_fat']:
                value = round(entry.get('qty'), 1)  # Macros to 1 decimal
            elif metric_name in ['weight_body_mass', 'lean_body_mass']:
                value = round(entry.get('qty'), 2)  # Weight to 2 decimals
            else:
                value = entry.get('qty')
            
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
            workout_kcal = EXCLUDED.workout_kcal,
            weight_kg = EXCLUDED.weight_kg,
            fat_mass_kg = EXCLUDED.fat_mass_kg,
            fat_free_mass_kg = EXCLUDED.fat_free_mass_kg
        """
    else:  # skip_existing
        conflict_clause = "ON CONFLICT (fact_date) DO NOTHING"
    
    # Update daily_facts
    query = f"""
        INSERT INTO daily_facts (
            fact_date, intake_kcal, protein_g, carbs_g, fat_g, 
            workout_kcal, weight_kg, fat_mass_kg, fat_free_mass_kg
        )
        SELECT 
            date,
            ROUND(MAX(CASE WHEN metric_name = 'dietary_energy' THEN value END)) as intake_kcal,
            ROUND(MAX(CASE WHEN metric_name = 'protein' THEN value END), 1) as protein_g,
            ROUND(MAX(CASE WHEN metric_name = 'carbohydrates' THEN value END), 1) as carbs_g,
            ROUND(MAX(CASE WHEN metric_name = 'total_fat' THEN value END), 1) as fat_g,
            ROUND(MAX(CASE WHEN metric_name = 'active_energy' THEN value END)) as workout_kcal,
            ROUND(MAX(CASE WHEN metric_name = 'weight_body_mass' THEN value * 0.453592 END), 2) as weight_kg,
            MAX(CASE WHEN metric_name = 'fat_mass_kg' THEN value END) as fat_mass_kg,
            MAX(CASE WHEN metric_name = 'fat_free_mass_kg' THEN value END) as fat_free_mass_kg
        FROM hae_metrics_parsed
        WHERE import_id = %s
        GROUP BY date
        {conflict_clause}
    """
    cur.execute(query, (import_id,))
    
    # Mark processed
    cur.execute("UPDATE hae_raw SET processed = TRUE WHERE import_id = %s", (import_id,))
    
    conn.commit()
    print(f"Imported {filename} as import_id {import_id}")

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
        import_hae_file(conn, file_path, overwrite_mode)
    finally:
        conn.close()
