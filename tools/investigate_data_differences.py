#!/usr/bin/env python3
"""
Investigate Data Differences

This script compares the CSV data used by Gemini with our database data
to understand why parameter estimates are so different.
"""

import os
import sys
import pandas as pd
import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def robust_clean(series: pd.Series, window: int = 7, k: float = 3.0) -> pd.Series:
    """Robustly clean BIA sensor data using rolling median and MAD-based outlier detection."""
    s = series.copy()
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    mad = mad.replace(0, np.nan).ffill().bfill()
    mask = (s - med).abs() > k * mad
    s[mask] = np.nan
    return s

def build_windows(data: pd.DataFrame, window_days: int = 14) -> pd.DataFrame:
    """Build analysis windows with eligibility criteria."""
    rows = []
    for i in range(len(data) - window_days + 1):
        w = data.iloc[i:i+window_days]
        
        # Eligibility criteria
        if (pd.notna(w.iloc[0]['fat_mass_kg']) and
            pd.notna(w.iloc[-1]['fat_mass_kg']) and
            w['fat_mass_kg'].notna().sum() >= 10 and
            w['fat_free_mass_kg'].notna().sum() >= 10):
            
            rows.append({
                'delta_fm_kg': float(w.iloc[-1]['fat_mass_kg'] - w.iloc[0]['fat_mass_kg']),
                'intake_sum': float(w['intake_kcal'].sum()),
                'workout_sum': float(w['workout_kcal'].sum()),
                'mean_lbm': float(w['fat_free_mass_kg'].mean()),
                'days': int(window_days),
                'start_date': w.iloc[0]['fact_date'],
                'end_date': w.iloc[-1]['fact_date']
            })
    
    return pd.DataFrame(rows)

def load_database_data(engine, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Load daily facts data from database."""
    query = """
        SELECT 
            fact_date,
            intake_kcal,
            workout_kcal,
            fat_mass_kg,
            fat_free_mass_kg,
            weight_kg
        FROM daily_facts
        WHERE fat_mass_kg IS NOT NULL
    """
    
    params = {}
    if start_date:
        query += " AND fact_date >= :start_date"
        params['start_date'] = start_date
    if end_date:
        query += " AND fact_date <= :end_date"
        params['end_date'] = end_date
    
    query += " ORDER BY fact_date"
    
    with engine.connect() as conn:
        if params:
            df = pd.read_sql(text(query), conn, params=params)
        else:
            df = pd.read_sql(text(query), conn)
    
    df['fact_date'] = pd.to_datetime(df['fact_date'])
    df['workout_kcal'] = df['workout_kcal'].fillna(0)
    
    return df

def load_csv_data(csv_path: str) -> pd.DataFrame:
    """Load data from CSV file (Gemini's approach)."""
    df = pd.read_csv(csv_path)
    df['workout_kcal'] = df['workout_kcal'].fillna(0)
    df['fact_date'] = pd.to_datetime(df['fact_date'])
    df = df.sort_values('fact_date').reset_index(drop=True)
    return df

def fit_gemini_model(windows: pd.DataFrame) -> dict:
    """Fit the original Gemini model."""
    y = windows['delta_fm_kg'].values
    X = np.column_stack([
        windows['days'].values,
        (windows['days'] * windows['mean_lbm']).values,
        windows['workout_sum'].values,
        windows['intake_sum'].values
    ])
    
    scaler = StandardScaler(with_mean=True, with_std=True)
    Xs = scaler.fit_transform(X)
    
    huber = HuberRegressor(epsilon=1.35, max_iter=500, alpha=1e-3, fit_intercept=False)
    huber.fit(Xs, y)
    
    # Unscale coefficients
    beta_scaled = huber.coef_
    std_X = scaler.scale_
    beta = beta_scaled / std_X
    
    beta_days, beta_days_lbm, beta_workout, beta_intake = beta
    
    # Convert to interpretable parameters
    alpha = 1.0 / beta_intake
    c = 1.0 + alpha * beta_workout
    BMR0 = -alpha * beta_days
    k_lbm = -alpha * beta_days_lbm
    
    y_pred = huber.predict(Xs)
    r2 = r2_score(y, y_pred)
    mae = mean_absolute_error(y, y_pred)
    
    return {
        'alpha': alpha,
        'c': c,
        'BMR0': BMR0,
        'k_lbm': k_lbm,
        'r2': r2,
        'mae': mae,
        'n_windows': len(windows)
    }

def compare_datasets(db_df: pd.DataFrame, csv_df: pd.DataFrame):
    """Compare database and CSV datasets."""
    print("📊 DATASET COMPARISON")
    print("=" * 60)
    
    print(f"Database records: {len(db_df):,}")
    print(f"CSV records: {len(csv_df):,}")
    print(f"Difference: {len(csv_df) - len(db_df):,}")
    
    # Date ranges
    db_start = db_df['fact_date'].min()
    db_end = db_df['fact_date'].max()
    csv_start = csv_df['fact_date'].min()
    csv_end = csv_df['fact_date'].max()
    
    print(f"\nDatabase date range: {db_start.date()} to {db_end.date()}")
    print(f"CSV date range: {csv_start.date()} to {csv_end.date()}")
    
    # Data quality
    print(f"\nDatabase data quality:")
    print(f"  fat_mass_kg nulls: {db_df['fat_mass_kg'].isnull().sum()}")
    print(f"  fat_free_mass_kg nulls: {db_df['fat_free_mass_kg'].isnull().sum()}")
    print(f"  intake_kcal nulls: {db_df['intake_kcal'].isnull().sum()}")
    print(f"  workout_kcal nulls: {db_df['workout_kcal'].isnull().sum()}")
    
    print(f"\nCSV data quality:")
    print(f"  fat_mass_kg nulls: {csv_df['fat_mass_kg'].isnull().sum()}")
    print(f"  fat_free_mass_kg nulls: {csv_df['fat_free_mass_kg'].isnull().sum()}")
    print(f"  intake_kcal nulls: {csv_df['intake_kcal'].isnull().sum()}")
    print(f"  workout_kcal nulls: {csv_df['workout_kcal'].isnull().sum()}")
    
    # Statistical summaries
    print(f"\nDatabase statistics:")
    print(f"  fat_mass_kg: {db_df['fat_mass_kg'].mean():.2f} ± {db_df['fat_mass_kg'].std():.2f}")
    print(f"  fat_free_mass_kg: {db_df['fat_free_mass_kg'].mean():.2f} ± {db_df['fat_free_mass_kg'].std():.2f}")
    print(f"  intake_kcal: {db_df['intake_kcal'].mean():.0f} ± {db_df['intake_kcal'].std():.0f}")
    print(f"  workout_kcal: {db_df['workout_kcal'].mean():.0f} ± {db_df['workout_kcal'].std():.0f}")
    
    print(f"\nCSV statistics:")
    print(f"  fat_mass_kg: {csv_df['fat_mass_kg'].mean():.2f} ± {csv_df['fat_mass_kg'].std():.2f}")
    print(f"  fat_free_mass_kg: {csv_df['fat_free_mass_kg'].mean():.2f} ± {csv_df['fat_free_mass_kg'].std():.2f}")
    print(f"  intake_kcal: {csv_df['intake_kcal'].mean():.0f} ± {csv_df['intake_kcal'].std():.0f}")
    print(f"  workout_kcal: {csv_df['workout_kcal'].mean():.0f} ± {csv_df['workout_kcal'].std():.0f}")

def analyze_window_differences(db_windows: pd.DataFrame, csv_windows: pd.DataFrame):
    """Analyze differences in window-level data."""
    print("\n📊 WINDOW-LEVEL COMPARISON")
    print("=" * 60)
    
    print(f"Database windows: {len(db_windows)}")
    print(f"CSV windows: {len(csv_windows)}")
    
    # Statistical comparison
    print(f"\nDelta fat mass (kg):")
    print(f"  Database: {db_windows['delta_fm_kg'].mean():.3f} ± {db_windows['delta_fm_kg'].std():.3f}")
    print(f"  CSV: {csv_windows['delta_fm_kg'].mean():.3f} ± {csv_windows['delta_fm_kg'].std():.3f}")
    
    print(f"\nIntake sum (kcal):")
    print(f"  Database: {db_windows['intake_sum'].mean():.0f} ± {db_windows['intake_sum'].std():.0f}")
    print(f"  CSV: {csv_windows['intake_sum'].mean():.0f} ± {csv_windows['intake_sum'].std():.0f}")
    
    print(f"\nWorkout sum (kcal):")
    print(f"  Database: {db_windows['workout_sum'].mean():.0f} ± {db_windows['workout_sum'].std():.0f}")
    print(f"  CSV: {csv_windows['workout_sum'].mean():.0f} ± {csv_windows['workout_sum'].std():.0f}")
    
    print(f"\nMean LBM (kg):")
    print(f"  Database: {db_windows['mean_lbm'].mean():.2f} ± {db_windows['mean_lbm'].std():.2f}")
    print(f"  CSV: {csv_windows['mean_lbm'].mean():.2f} ± {csv_windows['mean_lbm'].std():.2f}")
    
    # Check for constant days
    print(f"\nDays feature:")
    print(f"  Database unique values: {db_windows['days'].nunique()}")
    print(f"  CSV unique values: {csv_windows['days'].nunique()}")
    if db_windows['days'].nunique() == 1:
        print(f"  Database days: {db_windows['days'].iloc[0]} (constant)")
    if csv_windows['days'].nunique() == 1:
        print(f"  CSV days: {csv_windows['days'].iloc[0]} (constant)")

def main():
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    print("🔍 Data Differences Investigation")
    print("=" * 60)
    
    # Load database data
    print("Loading database data...")
    db_df = load_database_data(engine)
    print(f"Loaded {len(db_df)} database records")
    
    # Look for CSV file
    csv_paths = [
        'daily_facts_no_NULL (1).csv',
        'data/daily_facts_no_NULL (1).csv',
        '../daily_facts_no_NULL (1).csv'
    ]
    
    csv_df = None
    for path in csv_paths:
        if os.path.exists(path):
            print(f"Found CSV file: {path}")
            csv_df = load_csv_data(path)
            break
    
    if csv_df is None:
        print("❌ CSV file not found. Please provide the path to 'daily_facts_no_NULL (1).csv'")
        print("Expected locations:")
        for path in csv_paths:
            print(f"  - {path}")
        sys.exit(1)
    
    print(f"Loaded {len(csv_df)} CSV records")
    
    # Compare datasets
    compare_datasets(db_df, csv_df)
    
    # Apply robust cleaning to both
    print("\n🧹 Applying robust cleaning...")
    db_df['fat_mass_kg'] = robust_clean(db_df['fat_mass_kg'])
    db_df['fat_free_mass_kg'] = robust_clean(db_df['fat_free_mass_kg'])
    csv_df['fat_mass_kg'] = robust_clean(csv_df['fat_mass_kg'])
    csv_df['fat_free_mass_kg'] = robust_clean(csv_df['fat_free_mass_kg'])
    
    # Build windows
    print("Building 14-day analysis windows...")
    db_windows = build_windows(db_df, window_days=14)
    csv_windows = build_windows(csv_df, window_days=14)
    
    print(f"Database windows: {len(db_windows)}")
    print(f"CSV windows: {len(csv_windows)}")
    
    # Analyze window differences
    analyze_window_differences(db_windows, csv_windows)
    
    # Fit models on both datasets
    print("\n🔬 PARAMETER ESTIMATION COMPARISON")
    print("=" * 60)
    
    if len(db_windows) >= 10:
        print("Fitting model on database data...")
        db_results = fit_gemini_model(db_windows)
        print(f"Database results:")
        print(f"  α = {db_results['alpha']:,.0f} kcal/kg")
        print(f"  C = {db_results['c']:.3f}")
        print(f"  BMR₀ = {db_results['BMR0']:,.0f} kcal/day")
        print(f"  k_LBM = {db_results['k_lbm']:.1f} kcal/day/kg")
        print(f"  R² = {db_results['r2']:.3f}")
        print(f"  MAE = {db_results['mae']:.3f} kg")
        print(f"  Windows = {db_results['n_windows']}")
    
    if len(csv_windows) >= 10:
        print("\nFitting model on CSV data...")
        csv_results = fit_gemini_model(csv_windows)
        print(f"CSV results:")
        print(f"  α = {csv_results['alpha']:,.0f} kcal/kg")
        print(f"  C = {csv_results['c']:.3f}")
        print(f"  BMR₀ = {csv_results['BMR0']:,.0f} kcal/day")
        print(f"  k_LBM = {csv_results['k_lbm']:.1f} kcal/day/kg")
        print(f"  R² = {csv_results['r2']:.3f}")
        print(f"  MAE = {csv_results['mae']:.3f} kg")
        print(f"  Windows = {csv_results['n_windows']}")
    
    # Summary
    print("\n📋 SUMMARY")
    print("=" * 30)
    print("Key differences to investigate:")
    print("1. Data volume (records and windows)")
    print("2. Date ranges")
    print("3. Data quality (nulls, outliers)")
    print("4. Statistical distributions")
    print("5. Window eligibility criteria")
    print("6. Robust cleaning effects")

if __name__ == '__main__':
    main()
