#!/usr/bin/env python3
"""
Reliable Daily Series Materialization ETL

Factory pattern: reliable, repeatable, observable
- Single responsibility: materialize daily series
- Idempotent operations: always uses UPSERT
- Clear error handling: logs what failed and why
- Atomic transactions: all-or-nothing per date
- Observable state: clear logging of what was processed

Usage:
    python etl/materialize_daily_series.py --date 2025-09-26
    python etl/materialize_daily_series.py --date-range 2025-09-26 2025-09-27
    python etl/materialize_daily_series.py --date yesterday
"""

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import create_engine, text

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/materialize_daily_series.log', mode='a')
    ]
)
log = logging.getLogger(__name__)

def get_current_model_params(engine) -> Optional[Dict]:
    """Get current model parameters for the given date range."""
    query = text("""
        SELECT 
            params_version,
            c_exercise_comp,
            alpha_fm,
            alpha_lbm,
            bmr0_kcal,
            k_lbm_kcal_per_kg,
            kcal_per_kg_fat
        FROM model_params_timevarying
        WHERE effective_start_date <= CURRENT_DATE
          AND (effective_end_date IS NULL OR effective_end_date >= CURRENT_DATE)
        ORDER BY effective_start_date DESC
        LIMIT 1
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query).fetchone()
        if result:
            return {
                'params_version': str(result[0]),
                'c_exercise_comp': float(result[1]),
                'alpha_fm': float(result[2]),
                'alpha_lbm': float(result[3]),
                'bmr0_kcal': float(result[4]),
                'k_lbm_kcal_per_kg': float(result[5]),
                'kcal_per_kg_fat': float(result[6])
            }
    return None

def get_daily_facts(engine, fact_date: date) -> Optional[Dict]:
    """Get daily facts data for a specific date."""
    query = text("""
        SELECT 
            fact_date,
            COALESCE(intake_kcal, 0) as intake_kcal,
            COALESCE(workout_kcal, 0) as workout_kcal,
            fat_mass_kg,
            fat_free_mass_kg
        FROM daily_facts
        WHERE fact_date = :fact_date
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {'fact_date': fact_date}).fetchone()
        if result:
            return {
                'fact_date': result[0],
                'intake_kcal': float(result[1]) if result[1] is not None else None,
                'workout_kcal': float(result[2]) if result[2] is not None else None,
                'fat_mass_kg': float(result[3]) if result[3] is not None else None,
                'fat_free_mass_kg': float(result[4]) if result[4] is not None else None
            }
    return None

def get_previous_ema_values(engine, fact_date: date, params: Dict) -> Tuple[Optional[float], Optional[float]]:
    """Get previous EMA values for fat mass and lean body mass."""
    query = text("""
        SELECT 
            fat_mass_ema_kg,
            lbm_ema_kg_for_bmr
        FROM daily_series_materialized
        WHERE fact_date = (
            SELECT MAX(fact_date) 
            FROM daily_series_materialized 
            WHERE fact_date < :fact_date
        )
        ORDER BY fact_date DESC
        LIMIT 1
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {'fact_date': fact_date}).fetchone()
        if result:
            return float(result[0]) if result[0] is not None else None, float(result[1]) if result[1] is not None else None
    return None, None

def calculate_ema_values(daily_data: Dict, params: Dict, 
                        prev_fat_mass_ema: Optional[float], 
                        prev_lbm_ema: Optional[float]) -> Tuple[float, float]:
    """Calculate EMA values for fat mass and lean body mass."""
    alpha_fm = params['alpha_fm']
    alpha_lbm = params['alpha_lbm']
    
    # Fat mass EMA
    if daily_data['fat_mass_kg'] is not None:
        if prev_fat_mass_ema is not None:
            fat_mass_ema = prev_fat_mass_ema * (1 - alpha_fm) + daily_data['fat_mass_kg'] * alpha_fm
        else:
            fat_mass_ema = daily_data['fat_mass_kg']
    else:
        fat_mass_ema = prev_fat_mass_ema or 0.0
    
    # Lean body mass EMA
    if daily_data['fat_free_mass_kg'] is not None:
        if prev_lbm_ema is not None:
            lbm_ema = prev_lbm_ema * (1 - alpha_lbm) + daily_data['fat_free_mass_kg'] * alpha_lbm
        else:
            lbm_ema = daily_data['fat_free_mass_kg']
    else:
        lbm_ema = prev_lbm_ema or 0.0
    
    return fat_mass_ema, lbm_ema

def upsert_materialized_series(engine, fact_date: date, params: Dict) -> str:
    """Handle missing data gracefully - don't fail entire batch."""
    
    daily_data = get_daily_facts(engine, fact_date)
    
    if not daily_data:
        log.warning(f"⚠️  Skipping {fact_date} - no daily facts data")
        return "skipped"
    
    # Check for critical missing data
    if daily_data['intake_kcal'] is None or daily_data['fat_mass_kg'] is None:
        log.warning(f"⚠️  Skipping {fact_date} - missing critical data (intake_kcal={daily_data['intake_kcal']}, fat_mass_kg={daily_data['fat_mass_kg']})")
        return "skipped"
    
    # Get previous EMA values for continuity
    prev_fat_mass_ema, prev_lbm_ema = get_previous_ema_values(engine, fact_date, params)
    
    # Calculate EMA values
    fat_mass_ema, lbm_ema = calculate_ema_values(daily_data, params, prev_fat_mass_ema, prev_lbm_ema)
    
    # Calculate derived metrics
    bmr_kcal = params['bmr0_kcal'] + params['k_lbm_kcal_per_kg'] * lbm_ema
    adj_exercise_kcal = (1 - params['c_exercise_comp']) * daily_data['workout_kcal']
    net_kcal = daily_data['intake_kcal'] - adj_exercise_kcal - bmr_kcal
    
    # Generate run ID for tracking
    run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # UPSERT query - handles duplicates gracefully
    upsert_query = text("""
        INSERT INTO daily_series_materialized (
            fact_date,
            params_version_used,
            fat_mass_ema_kg,
            lbm_ema_kg_for_bmr,
            bmr_kcal,
            adj_exercise_kcal,
            net_kcal,
            computed_at,
            compute_run_id
        ) VALUES (
            :fact_date,
            :params_version,
            :fat_mass_ema,
            :lbm_ema,
            :bmr_kcal,
            :adj_exercise_kcal,
            :net_kcal,
            NOW(),
            :run_id
        )
        ON CONFLICT (fact_date) DO UPDATE SET
            params_version_used = EXCLUDED.params_version_used,
            fat_mass_ema_kg = EXCLUDED.fat_mass_ema_kg,
            lbm_ema_kg_for_bmr = EXCLUDED.lbm_ema_kg_for_bmr,
            bmr_kcal = EXCLUDED.bmr_kcal,
            adj_exercise_kcal = EXCLUDED.adj_exercise_kcal,
            net_kcal = EXCLUDED.net_kcal,
            computed_at = EXCLUDED.computed_at,
            compute_run_id = EXCLUDED.compute_run_id
    """)
    
    try:
        with engine.begin() as conn:
            conn.execute(upsert_query, {
                'fact_date': fact_date,
                'params_version': params['params_version'],
                'fat_mass_ema': round(fat_mass_ema, 3),
                'lbm_ema': round(lbm_ema, 3),
                'bmr_kcal': round(bmr_kcal),
                'adj_exercise_kcal': round(adj_exercise_kcal),
                'net_kcal': round(net_kcal),
                'run_id': run_id
            })
        
        log.info(f"✅ Materialized {fact_date} - net_kcal={round(net_kcal)}, fat_mass_ema={round(fat_mass_ema, 3)}")
        return "success"
        
    except Exception as e:
        log.error(f"❌ Failed {fact_date}: {e}")
        return "failed"

def date_range(start_date: date, end_date: date):
    """Generate date range iterator."""
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)

def materialize_date_range(start_date: date, end_date: date) -> Tuple[int, int, int]:
    """Factory pattern: reliable, repeatable, observable"""
    
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        log.error("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    # Step 1: Get current parameters (versioned)
    params = get_current_model_params(engine)
    if not params:
        log.error("ERROR: No current model parameters found")
        sys.exit(1)
    
    log.info(f"Using model parameters: {params['params_version']}")
    
    # Step 2: Process each date atomically
    success_count = 0
    failure_count = 0
    skipped_count = 0
    
    for current_date in date_range(start_date, end_date):
        try:
            result = upsert_materialized_series(engine, current_date, params)
            if result == "success":
                success_count += 1
            elif result == "skipped":
                skipped_count += 1
            else:
                failure_count += 1
                
        except Exception as e:
            log.error(f"❌ Unexpected error processing {current_date}: {e}")
            failure_count += 1
    
    return success_count, failure_count, skipped_count

def parse_date_argument(date_str: str) -> date:
    """Parse date argument, handling 'yesterday' special case."""
    if date_str.lower() == 'yesterday':
        return date.today() - timedelta(days=1)
    
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        log.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD or 'yesterday'")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Materialize daily series data')
    parser.add_argument('--date', type=str, help='Single date to process (YYYY-MM-DD or "yesterday")')
    parser.add_argument('--date-range', nargs=2, metavar=('START', 'END'), 
                       help='Date range to process (YYYY-MM-DD YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    if not args.date and not args.date_range:
        log.error("ERROR: Must specify either --date or --date-range")
        sys.exit(1)
    
    if args.date and args.date_range:
        log.error("ERROR: Cannot specify both --date and --date-range")
        sys.exit(1)
    
    # Determine date range
    if args.date:
        start_date = end_date = parse_date_argument(args.date)
    else:
        start_date = parse_date_argument(args.date_range[0])
        end_date = parse_date_argument(args.date_range[1])
    
    log.info(f"Starting materialization for {start_date} to {end_date}")
    
    # Process dates
    success_count, failure_count, skipped_count = materialize_date_range(start_date, end_date)
    
    # Summary
    total_dates = (end_date - start_date).days + 1
    log.info(f"📊 Materialization complete:")
    log.info(f"   Total dates: {total_dates}")
    log.info(f"   ✅ Success: {success_count}")
    log.info(f"   ⚠️  Skipped: {skipped_count}")
    log.info(f"   ❌ Failed: {failure_count}")
    
    if failure_count > 0:
        sys.exit(1)

if __name__ == '__main__':
    main()
