#!/usr/bin/env python3
"""
Create production train/test splits from daily_facts table.

Replicates P1 train/test methodology using production daily_facts table.
Creates prod_train_daily and prod_test_daily views with split-aware imputation.
"""

import os
import argparse
from datetime import datetime
from sqlalchemy import create_engine, text

# Database connection
DB = os.environ.get("DATABASE_URL")
assert DB, "Set DATABASE_URL in your .env"

eng = create_engine(DB)

parser = argparse.ArgumentParser(description="Create production train/test splits from daily_facts")
parser.add_argument("--rebuild", action="store_true", help="Drop and recreate views")
parser.add_argument("--validate", action="store_true", help="Show row counts and validation")
args = parser.parse_args()

def create_production_splits():
    """Create production train/test split views from daily_facts."""
    
    # Drop views if rebuilding
    if args.rebuild:
        print("Dropping existing views...")
        with eng.connect() as conn:
            conn.execute(text("DROP VIEW IF EXISTS prod_train_daily CASCADE"))
            conn.execute(text("DROP VIEW IF EXISTS prod_test_daily CASCADE"))
            conn.commit()
    
    # Create prod_train_daily view (2021-2024)
    print("Creating prod_train_daily view (2021-01-01 to 2024-12-31)...")
    train_sql = text("""
        CREATE OR REPLACE VIEW prod_train_daily AS
        WITH train_split AS (
            SELECT 
                fact_date,
                intake_kcal,
                workout_kcal,
                fat_mass_kg,
                fat_free_mass_kg,
                weight_kg,
                -- Split-aware DoW imputation for intake_kcal
                CASE 
                    WHEN intake_kcal IS NULL THEN 
                        (SELECT intake_kcal_median 
                         FROM facts_intake_dow_medians 
                         WHERE day_of_week = TO_CHAR(fact_date, 'Day'))
                    ELSE intake_kcal
                END AS intake_kcal_imputed,
                -- Zero-fill missing workout_kcal
                COALESCE(workout_kcal, 0) AS workout_kcal_imputed
            FROM daily_facts
            WHERE fact_date BETWEEN '2021-01-01' AND '2024-12-31'
        )
        SELECT 
            fact_date,
            intake_kcal_imputed::integer AS intake_kcal,
            workout_kcal_imputed::integer AS workout_kcal,
            (intake_kcal_imputed - workout_kcal_imputed)::integer AS net_kcal,
            fat_mass_kg,
            fat_free_mass_kg,
            weight_kg
        FROM train_split
        WHERE fat_mass_kg IS NOT NULL  -- Never impute fat_mass_kg
        ORDER BY fact_date;
    """)
    
    with eng.connect() as conn:
        conn.execute(train_sql)
        conn.commit()
    
    # Create prod_test_daily view (2025+)
    print("Creating prod_test_daily view (2025-01-01 to current)...")
    test_sql = text("""
        CREATE OR REPLACE VIEW prod_test_daily AS
        WITH test_split AS (
            SELECT 
                fact_date,
                intake_kcal,
                workout_kcal,
                fat_mass_kg,
                fat_free_mass_kg,
                weight_kg,
                -- Split-aware DoW imputation for intake_kcal (using test split only)
                CASE 
                    WHEN intake_kcal IS NULL THEN 
                        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY intake_kcal)
                         FROM daily_facts 
                         WHERE TO_CHAR(fact_date, 'Day') = TO_CHAR(daily_facts.fact_date, 'Day')
                           AND daily_facts.fact_date >= '2025-01-01'
                           AND daily_facts.intake_kcal IS NOT NULL)
                    ELSE intake_kcal
                END AS intake_kcal_imputed,
                -- Zero-fill missing workout_kcal
                COALESCE(workout_kcal, 0) AS workout_kcal_imputed
            FROM daily_facts
            WHERE fact_date >= '2025-01-01'
        )
        SELECT 
            fact_date,
            intake_kcal_imputed::integer AS intake_kcal,
            workout_kcal_imputed::integer AS workout_kcal,
            (intake_kcal_imputed - workout_kcal_imputed)::integer AS net_kcal,
            fat_mass_kg,
            fat_free_mass_kg,
            weight_kg
        FROM test_split
        WHERE fat_mass_kg IS NOT NULL  -- Never impute fat_mass_kg
        ORDER BY fact_date;
    """)
    
    with eng.connect() as conn:
        conn.execute(test_sql)
        conn.commit()
    
    print("✅ Production splits created successfully!")

def validate_splits():
    """Validate the created splits with row counts and basic checks."""
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)
    
    with eng.connect() as conn:
        # Train split validation
        train_count = conn.execute(text("SELECT COUNT(*) FROM prod_train_daily")).scalar()
        train_dates = conn.execute(text("""
            SELECT MIN(fact_date), MAX(fact_date) 
            FROM prod_train_daily
        """)).fetchone()
        
        print(f"📊 Train Split (prod_train_daily):")
        print(f"   Rows: {train_count:,}")
        print(f"   Date range: {train_dates[0]} to {train_dates[1]}")
        
        # Test split validation
        test_count = conn.execute(text("SELECT COUNT(*) FROM prod_test_daily")).scalar()
        test_dates = conn.execute(text("""
            SELECT MIN(fact_date), MAX(fact_date) 
            FROM prod_test_daily
        """)).fetchone()
        
        print(f"📊 Test Split (prod_test_daily):")
        print(f"   Rows: {test_count:,}")
        print(f"   Date range: {test_dates[0]} to {test_dates[1]}")
        
        # Data quality checks
        print(f"\n🔍 Data Quality Checks:")
        
        # Check for NULL values in key columns
        train_nulls = conn.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE intake_kcal IS NULL) as intake_nulls,
                COUNT(*) FILTER (WHERE workout_kcal IS NULL) as workout_nulls,
                COUNT(*) FILTER (WHERE fat_mass_kg IS NULL) as fat_mass_nulls
            FROM prod_train_daily
        """)).fetchone()
        
        test_nulls = conn.execute(text("""
            SELECT 
                COUNT(*) FILTER (WHERE intake_kcal IS NULL) as intake_nulls,
                COUNT(*) FILTER (WHERE workout_kcal IS NULL) as workout_nulls,
                COUNT(*) FILTER (WHERE fat_mass_kg IS NULL) as fat_mass_nulls
            FROM prod_test_daily
        """)).fetchone()
        
        print(f"   Train split NULLs: intake={train_nulls[0]}, workout={train_nulls[1]}, fat_mass={train_nulls[2]}")
        print(f"   Test split NULLs:  intake={test_nulls[0]}, workout={test_nulls[1]}, fat_mass={test_nulls[2]}")
        
        # Check value ranges
        train_ranges = conn.execute(text("""
            SELECT 
                MIN(intake_kcal), MAX(intake_kcal),
                MIN(workout_kcal), MAX(workout_kcal),
                MIN(fat_mass_kg), MAX(fat_mass_kg)
            FROM prod_train_daily
        """)).fetchone()
        
        test_ranges = conn.execute(text("""
            SELECT 
                MIN(intake_kcal), MAX(intake_kcal),
                MIN(workout_kcal), MAX(workout_kcal),
                MIN(fat_mass_kg), MAX(fat_mass_kg)
            FROM prod_test_daily
        """)).fetchone()
        
        print(f"\n📈 Value Ranges:")
        print(f"   Train - Intake: {train_ranges[0]} to {train_ranges[1]} kcal")
        print(f"   Train - Workout: {train_ranges[2]} to {train_ranges[3]} kcal")
        print(f"   Train - Fat Mass: {train_ranges[4]:.1f} to {train_ranges[5]:.1f} kg")
        print(f"   Test  - Intake: {test_ranges[0]} to {test_ranges[1]} kcal")
        print(f"   Test  - Workout: {test_ranges[2]} to {test_ranges[3]} kcal")
        print(f"   Test  - Fat Mass: {test_ranges[4]:.1f} to {test_ranges[5]:.1f} kg")
        
        # Check for date gaps
        train_gaps = conn.execute(text("""
            WITH date_series AS (
                SELECT generate_series(
                    (SELECT MIN(fact_date) FROM prod_train_daily),
                    (SELECT MAX(fact_date) FROM prod_train_daily),
                    '1 day'::interval
                )::date AS expected_date
            )
            SELECT COUNT(*) 
            FROM date_series ds
            LEFT JOIN prod_train_daily ptd ON ds.expected_date = ptd.fact_date
            WHERE ptd.fact_date IS NULL
        """)).scalar()
        
        test_gaps = conn.execute(text("""
            WITH date_series AS (
                SELECT generate_series(
                    (SELECT MIN(fact_date) FROM prod_test_daily),
                    (SELECT MAX(fact_date) FROM prod_test_daily),
                    '1 day'::interval
                )::date AS expected_date
            )
            SELECT COUNT(*) 
            FROM date_series ds
            LEFT JOIN prod_test_daily ptd ON ds.expected_date = ptd.fact_date
            WHERE ptd.fact_date IS NULL
        """)).scalar()
        
        print(f"\n📅 Date Coverage:")
        print(f"   Train split gaps: {train_gaps} missing dates")
        print(f"   Test split gaps:  {test_gaps} missing dates")
        
        print(f"\n✅ Validation complete!")

def main():
    """Main function."""
    print("🚀 Creating Production Train/Test Splits")
    print("="*50)
    
    try:
        create_production_splits()
        
        if args.validate:
            validate_splits()
        else:
            print("\n💡 Run with --validate to see detailed statistics")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
