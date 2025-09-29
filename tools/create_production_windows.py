#!/usr/bin/env python3
"""
Create production rolling windows from prod_train_daily and prod_test_daily.

Replicates P1 windowing methodology using production splits.
Creates prod_train_windows and prod_test_windows with 7-day rolling windows.
"""

import os
import argparse
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# Database connection
DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

parser = argparse.ArgumentParser(description="Create production rolling windows from splits")
parser.add_argument("--rebuild", action="store_true", help="Drop and recreate views")
parser.add_argument("--validate", action="store_true", help="Show row counts and validation")
parser.add_argument("--lookback-days", type=int, default=3, help="Maximum lookback days for fat mass endpoints")
parser.add_argument("--max-daily-change", type=float, default=0.12, help="Maximum daily fat mass change (kg/day)")
args = parser.parse_args()

def create_production_windows():
    """Create production rolling window views from prod_train_daily and prod_test_daily."""
    
    # Drop views if rebuilding
    if args.rebuild:
        print("Dropping existing views...")
        with eng.connect() as conn:
            conn.execute(text("DROP VIEW IF EXISTS prod_train_windows CASCADE"))
            conn.execute(text("DROP VIEW IF EXISTS prod_test_windows CASCADE"))
            conn.commit()
    
    # Create prod_train_windows view
    print("Creating prod_train_windows view...")
    train_windows_sql = text(f"""
        CREATE OR REPLACE VIEW prod_train_windows AS
        WITH params AS (
            SELECT {args.lookback_days} AS lookback_days
        ), 
        sundays AS (
            SELECT generate_series(
                '2021-01-10'::date::timestamp with time zone, 
                '2024-12-31'::timestamp with time zone, 
                '7 days'::interval
            )::date AS week_end
        ), 
        candidates AS (
            SELECT s.week_end,
                k.k,
                s.week_end - (k.k - 1) AS start_date
            FROM sundays s
            CROSS JOIN (VALUES (7), (14), (21), (28)) k(k)
        ), 
        with_endpoints AS (
            SELECT c.week_end,
                c.k,
                c.start_date,
                e.fm_end_date,
                e.fm_end_kg,
                b.fm_start_date,
                b.fm_start_kg
            FROM candidates c
            LEFT JOIN LATERAL (
                SELECT ptd.fact_date AS fm_end_date,
                    ptd.fat_mass_kg AS fm_end_kg
                FROM prod_train_daily ptd, params p
                WHERE ptd.fat_mass_kg IS NOT NULL 
                    AND ptd.fact_date >= (c.week_end - p.lookback_days) 
                    AND ptd.fact_date <= c.week_end
                ORDER BY ptd.fact_date DESC
                LIMIT 1
            ) e ON true
            LEFT JOIN LATERAL (
                SELECT ptd.fact_date AS fm_start_date,
                    ptd.fat_mass_kg AS fm_start_kg
                FROM prod_train_daily ptd, params p
                WHERE ptd.fat_mass_kg IS NOT NULL 
                    AND ptd.fact_date >= (c.start_date - p.lookback_days) 
                    AND ptd.fact_date <= c.start_date
                ORDER BY ptd.fact_date DESC
                LIMIT 1
            ) b ON true
        ), 
        valid_candidates AS (
            SELECT with_endpoints.week_end,
                with_endpoints.k,
                with_endpoints.start_date,
                with_endpoints.fm_end_date,
                with_endpoints.fm_end_kg,
                with_endpoints.fm_start_date,
                with_endpoints.fm_start_kg
            FROM with_endpoints
            WHERE with_endpoints.fm_end_date IS NOT NULL 
                AND with_endpoints.fm_start_date IS NOT NULL
        ), 
        accepted AS (
            SELECT valid_candidates.week_end AS end_date,
                valid_candidates.start_date,
                valid_candidates.k,
                valid_candidates.fm_start_date,
                valid_candidates.fm_end_date,
                valid_candidates.fm_start_kg,
                valid_candidates.fm_end_kg,
                row_number() OVER (
                    PARTITION BY valid_candidates.week_end 
                    ORDER BY valid_candidates.k
                ) AS rn
            FROM valid_candidates
        )
        SELECT a.start_date,
            a.end_date,
            a.k AS days,
            a.fm_start_date,
            a.fm_end_date,
            a.fm_start_kg,
            a.fm_end_kg,
            a.fm_end_kg - a.fm_start_kg AS delta_fm_kg,
            ((
                SELECT sum(ptd.intake_kcal)
                FROM prod_train_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS intake_kcal_sum,
            ((
                SELECT sum(COALESCE(ptd.workout_kcal, 0))
                FROM prod_train_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS workout_kcal_sum,
            ((
                SELECT sum(ptd.intake_kcal - COALESCE(ptd.workout_kcal, 0))
                FROM prod_train_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS net_kcal_sum,
            a.k = 7 AS is_7d,
            a.k = 8 AS is_8d,
            a.k = 9 AS is_9d,
            a.end_date - a.fm_end_date AS end_lookback_days,
            a.start_date - a.fm_start_date AS start_lookback_days
        FROM accepted a
        WHERE a.rn = 1
            AND (abs(a.fm_end_kg - a.fm_start_kg) / NULLIF(a.k, 0)::numeric) <= {args.max_daily_change}
            AND (a.end_date - a.fm_end_date) <= {args.lookback_days}
            AND (a.start_date - a.fm_start_date) <= {args.lookback_days}
        ORDER BY a.end_date;
    """)
    
    with eng.connect() as conn:
        conn.execute(train_windows_sql)
        conn.commit()
    
    # Create prod_test_windows view
    print("Creating prod_test_windows view...")
    test_windows_sql = text(f"""
        CREATE OR REPLACE VIEW prod_test_windows AS
        WITH params AS (
            SELECT {args.lookback_days} AS lookback_days
        ), 
        sundays AS (
            SELECT generate_series(
                '2025-01-12'::date::timestamp with time zone, 
                CURRENT_DATE::timestamp with time zone, 
                '7 days'::interval
            )::date AS week_end
        ), 
        candidates AS (
            SELECT s.week_end,
                k.k,
                s.week_end - (k.k - 1) AS start_date
            FROM sundays s
            CROSS JOIN (VALUES (7), (14), (21), (28)) k(k)
        ), 
        with_endpoints AS (
            SELECT c.week_end,
                c.k,
                c.start_date,
                e.fm_end_date,
                e.fm_end_kg,
                b.fm_start_date,
                b.fm_start_kg
            FROM candidates c
            LEFT JOIN LATERAL (
                SELECT ptd.fact_date AS fm_end_date,
                    ptd.fat_mass_kg AS fm_end_kg
                FROM prod_test_daily ptd, params p
                WHERE ptd.fat_mass_kg IS NOT NULL 
                    AND ptd.fact_date >= (c.week_end - p.lookback_days) 
                    AND ptd.fact_date <= c.week_end
                ORDER BY ptd.fact_date DESC
                LIMIT 1
            ) e ON true
            LEFT JOIN LATERAL (
                SELECT ptd.fact_date AS fm_start_date,
                    ptd.fat_mass_kg AS fm_start_kg
                FROM prod_test_daily ptd, params p
                WHERE ptd.fat_mass_kg IS NOT NULL 
                    AND ptd.fact_date >= (c.start_date - p.lookback_days) 
                    AND ptd.fact_date <= c.start_date
                ORDER BY ptd.fact_date DESC
                LIMIT 1
            ) b ON true
        ), 
        valid_candidates AS (
            SELECT with_endpoints.week_end,
                with_endpoints.k,
                with_endpoints.start_date,
                with_endpoints.fm_end_date,
                with_endpoints.fm_end_kg,
                with_endpoints.fm_start_date,
                with_endpoints.fm_start_kg
            FROM with_endpoints
            WHERE with_endpoints.fm_end_date IS NOT NULL 
                AND with_endpoints.fm_start_date IS NOT NULL
        ), 
        accepted AS (
            SELECT valid_candidates.week_end AS end_date,
                valid_candidates.start_date,
                valid_candidates.k,
                valid_candidates.fm_start_date,
                valid_candidates.fm_end_date,
                valid_candidates.fm_start_kg,
                valid_candidates.fm_end_kg,
                row_number() OVER (
                    PARTITION BY valid_candidates.week_end 
                    ORDER BY valid_candidates.k
                ) AS rn
            FROM valid_candidates
        )
        SELECT a.start_date,
            a.end_date,
            a.k AS days,
            a.fm_start_date,
            a.fm_end_date,
            a.fm_start_kg,
            a.fm_end_kg,
            a.fm_end_kg - a.fm_start_kg AS delta_fm_kg,
            ((
                SELECT sum(ptd.intake_kcal)
                FROM prod_test_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS intake_kcal_sum,
            ((
                SELECT sum(COALESCE(ptd.workout_kcal, 0))
                FROM prod_test_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS workout_kcal_sum,
            ((
                SELECT sum(ptd.intake_kcal - COALESCE(ptd.workout_kcal, 0))
                FROM prod_test_daily ptd
                WHERE ptd.fact_date > a.start_date 
                    AND ptd.fact_date < a.end_date
            ))::bigint AS net_kcal_sum,
            a.k = 7 AS is_7d,
            a.k = 8 AS is_8d,
            a.k = 9 AS is_9d,
            a.end_date - a.fm_end_date AS end_lookback_days,
            a.start_date - a.fm_start_date AS start_lookback_days
        FROM accepted a
        WHERE a.rn = 1
            AND (abs(a.fm_end_kg - a.fm_start_kg) / NULLIF(a.k, 0)::numeric) <= {args.max_daily_change}
            AND (a.end_date - a.fm_end_date) <= {args.lookback_days}
            AND (a.start_date - a.fm_start_date) <= {args.lookback_days}
        ORDER BY a.end_date;
    """)
    
    with eng.connect() as conn:
        conn.execute(test_windows_sql)
        conn.commit()
    
    print("✅ Production windows created successfully!")

def validate_windows():
    """Validate the created windows with row counts and basic checks."""
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)
    
    with eng.connect() as conn:
        # Train windows validation
        train_count = conn.execute(text("SELECT COUNT(*) FROM prod_train_windows")).scalar()
        train_dates = conn.execute(text("""
            SELECT MIN(start_date), MAX(end_date) 
            FROM prod_train_windows
        """)).fetchone()
        
        print(f"📊 Train Windows (prod_train_windows):")
        print(f"   Windows: {train_count:,}")
        print(f"   Date range: {train_dates[0]} to {train_dates[1]}")
        
        # Test windows validation
        test_count = conn.execute(text("SELECT COUNT(*) FROM prod_test_windows")).scalar()
        test_dates = conn.execute(text("""
            SELECT MIN(start_date), MAX(end_date) 
            FROM prod_test_windows
        """)).fetchone()
        
        print(f"📊 Test Windows (prod_test_windows):")
        print(f"   Windows: {test_count:,}")
        print(f"   Date range: {test_dates[0]} to {test_dates[1]}")
        
        # Window length distribution
        print(f"\n📈 Window Length Distribution:")
        train_lengths = conn.execute(text("""
            SELECT days, COUNT(*) 
            FROM prod_train_windows 
            GROUP BY days 
            ORDER BY days
        """)).fetchall()
        
        test_lengths = conn.execute(text("""
            SELECT days, COUNT(*) 
            FROM prod_test_windows 
            GROUP BY days 
            ORDER BY days
        """)).fetchall()
        
        print(f"   Train - Lengths: {dict(train_lengths)}")
        print(f"   Test  - Lengths: {dict(test_lengths)}")
        
        # 7-day window counts
        train_7d = conn.execute(text("SELECT COUNT(*) FROM prod_train_windows WHERE is_7d = true")).scalar()
        test_7d = conn.execute(text("SELECT COUNT(*) FROM prod_test_windows WHERE is_7d = true")).scalar()
        
        print(f"\n🎯 7-Day Windows:")
        print(f"   Train: {train_7d:,} windows")
        print(f"   Test:  {test_7d:,} windows")
        
        # Fat mass change statistics
        print(f"\n📊 Fat Mass Change Statistics:")
        train_delta_stats = conn.execute(text("""
            SELECT 
                MIN(delta_fm_kg), MAX(delta_fm_kg),
                AVG(delta_fm_kg), STDDEV(delta_fm_kg)
            FROM prod_train_windows
        """)).fetchone()
        
        test_delta_stats = conn.execute(text("""
            SELECT 
                MIN(delta_fm_kg), MAX(delta_fm_kg),
                AVG(delta_fm_kg), STDDEV(delta_fm_kg)
            FROM prod_test_windows
        """)).fetchone()
        
        print(f"   Train - Min: {train_delta_stats[0]:.3f}, Max: {train_delta_stats[1]:.3f}, Avg: {train_delta_stats[2]:.3f}, Std: {train_delta_stats[3]:.3f} kg")
        print(f"   Test  - Min: {test_delta_stats[0]:.3f}, Max: {test_delta_stats[1]:.3f}, Avg: {test_delta_stats[2]:.3f}, Std: {test_delta_stats[3]:.3f} kg")
        
        # Lookback statistics
        print(f"\n🔍 Lookback Statistics:")
        train_lookback = conn.execute(text("""
            SELECT 
                MAX(start_lookback_days), MAX(end_lookback_days)
            FROM prod_train_windows
        """)).fetchone()
        
        test_lookback = conn.execute(text("""
            SELECT 
                MAX(start_lookback_days), MAX(end_lookback_days)
            FROM prod_test_windows
        """)).fetchone()
        
        print(f"   Train - Max start lookback: {train_lookback[0]}, Max end lookback: {train_lookback[1]} days")
        print(f"   Test  - Max start lookback: {test_lookback[0]}, Max end lookback: {test_lookback[1]} days")
        
        # Sample windows
        print(f"\n📋 Sample Windows (Train):")
        sample_train = conn.execute(text("""
            SELECT start_date, end_date, days, delta_fm_kg, intake_kcal_sum, workout_kcal_sum
            FROM prod_train_windows 
            WHERE is_7d = true
            ORDER BY end_date 
            LIMIT 5
        """)).fetchall()
        
        for row in sample_train:
            print(f"   {row[0]} to {row[1]} ({row[2]}d): ΔFM={row[3]:.3f}kg, Intake={row[4]:,}kcal, Workout={row[5]:,}kcal")
        
        print(f"\n📋 Sample Windows (Test):")
        sample_test = conn.execute(text("""
            SELECT start_date, end_date, days, delta_fm_kg, intake_kcal_sum, workout_kcal_sum
            FROM prod_test_windows 
            WHERE is_7d = true
            ORDER BY end_date 
            LIMIT 5
        """)).fetchall()
        
        for row in sample_test:
            print(f"   {row[0]} to {row[1]} ({row[2]}d): ΔFM={row[3]:.3f}kg, Intake={row[4]:,}kcal, Workout={row[5]:,}kcal")
        
        print(f"\n✅ Validation complete!")

def main():
    """Main function."""
    print("🚀 Creating Production Rolling Windows")
    print("="*50)
    print(f"Parameters: lookback_days={args.lookback_days}, max_daily_change={args.max_daily_change} kg/day")
    
    try:
        create_production_windows()
        
        if args.validate:
            validate_windows()
        else:
            print("\n💡 Run with --validate to see detailed statistics")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
