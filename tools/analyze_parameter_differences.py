#!/usr/bin/env python3
"""
Analyze Parameter Estimation Differences

This script analyzes why our database-based parameter estimation produces
different results than Gemini's CSV-based approach.
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

def analyze_data_characteristics(df: pd.DataFrame, name: str):
    """Analyze data characteristics."""
    print(f"\n📊 {name.upper()} DATA CHARACTERISTICS")
    print("=" * 50)
    
    print(f"Total records: {len(df):,}")
    print(f"Date range: {df['fact_date'].min().date()} to {df['fact_date'].max().date()}")
    
    # Data quality
    print(f"\nData quality:")
    print(f"  fat_mass_kg nulls: {df['fat_mass_kg'].isnull().sum()}")
    print(f"  fat_free_mass_kg nulls: {df['fat_free_mass_kg'].isnull().sum()}")
    print(f"  intake_kcal nulls: {df['intake_kcal'].isnull().sum()}")
    print(f"  workout_kcal nulls: {df['workout_kcal'].isnull().sum()}")
    
    # Statistical summaries
    print(f"\nStatistical summaries:")
    print(f"  fat_mass_kg: {df['fat_mass_kg'].mean():.2f} ± {df['fat_mass_kg'].std():.2f}")
    print(f"  fat_free_mass_kg: {df['fat_free_mass_kg'].mean():.2f} ± {df['fat_free_mass_kg'].std():.2f}")
    print(f"  intake_kcal: {df['intake_kcal'].mean():.0f} ± {df['intake_kcal'].std():.0f}")
    print(f"  workout_kcal: {df['workout_kcal'].mean():.0f} ± {df['workout_kcal'].std():.0f}")
    
    # Check for outliers
    print(f"\nOutlier analysis (using IQR method):")
    for col in ['fat_mass_kg', 'fat_free_mass_kg', 'intake_kcal', 'workout_kcal']:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        outliers = ((df[col] < lower_bound) | (df[col] > upper_bound)).sum()
        print(f"  {col}: {outliers} outliers ({outliers/len(df)*100:.1f}%)")

def analyze_window_characteristics(windows: pd.DataFrame, name: str):
    """Analyze window characteristics."""
    print(f"\n📊 {name.upper()} WINDOW CHARACTERISTICS")
    print("=" * 50)
    
    print(f"Total windows: {len(windows)}")
    
    # Statistical summaries
    print(f"\nWindow-level statistics:")
    print(f"  delta_fm_kg: {windows['delta_fm_kg'].mean():.3f} ± {windows['delta_fm_kg'].std():.3f}")
    print(f"  intake_sum: {windows['intake_sum'].mean():.0f} ± {windows['intake_sum'].std():.0f}")
    print(f"  workout_sum: {windows['workout_sum'].mean():.0f} ± {windows['workout_sum'].std():.0f}")
    print(f"  mean_lbm: {windows['mean_lbm'].mean():.2f} ± {windows['mean_lbm'].std():.2f}")
    
    # Check for constant days
    print(f"\nDays feature:")
    print(f"  Unique values: {windows['days'].nunique()}")
    if windows['days'].nunique() == 1:
        print(f"  Value: {windows['days'].iloc[0]} (constant)")
        print("  ⚠️  WARNING: Constant days feature causes identifiability issues!")
    
    # Check for extreme values
    print(f"\nExtreme values:")
    print(f"  delta_fm_kg range: {windows['delta_fm_kg'].min():.3f} to {windows['delta_fm_kg'].max():.3f}")
    print(f"  intake_sum range: {windows['intake_sum'].min():.0f} to {windows['intake_sum'].max():.0f}")
    print(f"  workout_sum range: {windows['workout_sum'].min():.0f} to {windows['workout_sum'].max():.0f}")

def simulate_csv_scenario():
    """Simulate what the CSV scenario might look like."""
    print("\n🎯 SIMULATED CSV SCENARIO ANALYSIS")
    print("=" * 50)
    
    print("Based on Gemini's results (113 windows, reasonable parameters):")
    print("  α = 9,710 kcal/kg (reasonable)")
    print("  C = 0.16 (reasonable)")
    print("  BMR₀ = 785 kcal/day (reasonable)")
    print("  k_LBM = 11.5 kcal/day/kg (reasonable)")
    
    print("\nKey differences likely:")
    print("1. **Data Volume**: 113 windows vs 828 windows")
    print("2. **Data Quality**: CSV may have cleaner data")
    print("3. **Date Range**: CSV includes data up to 9/9/25")
    print("4. **Outlier Handling**: Different robust cleaning effects")
    print("5. **Window Eligibility**: Different criteria or data availability")

def main():
    # Database connection
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)
    
    engine = create_engine(database_url)
    
    print("🔍 Parameter Estimation Differences Analysis")
    print("=" * 60)
    
    # Load database data
    print("Loading database data...")
    db_df = load_database_data(engine)
    print(f"Loaded {len(db_df)} database records")
    
    # Analyze database data
    analyze_data_characteristics(db_df, "Database")
    
    # Apply robust cleaning
    print("\n🧹 Applying robust cleaning...")
    db_df_cleaned = db_df.copy()
    db_df_cleaned['fat_mass_kg'] = robust_clean(db_df['fat_mass_kg'])
    db_df_cleaned['fat_free_mass_kg'] = robust_clean(db_df['fat_free_mass_kg'])
    
    # Analyze cleaned data
    analyze_data_characteristics(db_df_cleaned, "Database (Cleaned)")
    
    # Build windows
    print("\nBuilding 14-day analysis windows...")
    db_windows = build_windows(db_df_cleaned, window_days=14)
    print(f"Database windows: {len(db_windows)}")
    
    # Analyze window characteristics
    analyze_window_characteristics(db_windows, "Database")
    
    # Fit model on database data
    if len(db_windows) >= 10:
        print("\n🔬 DATABASE PARAMETER ESTIMATION")
        print("=" * 50)
        db_results = fit_gemini_model(db_windows)
        print(f"α = {db_results['alpha']:,.0f} kcal/kg")
        print(f"C = {db_results['c']:.3f}")
        print(f"BMR₀ = {db_results['BMR0']:,.0f} kcal/day")
        print(f"k_LBM = {db_results['k_lbm']:.1f} kcal/day/kg")
        print(f"R² = {db_results['r2']:.3f}")
        print(f"MAE = {db_results['mae']:.3f} kg")
        print(f"Windows = {db_results['n_windows']}")
    
    # Simulate CSV scenario
    simulate_csv_scenario()
    
    # Key insights
    print("\n💡 KEY INSIGHTS")
    print("=" * 30)
    print("1. **Data Volume**: Our database has 828 windows vs CSV's 113")
    print("2. **Identifiability**: Constant days=14 causes BMR₀ unidentifiability")
    print("3. **Data Quality**: CSV may have better data quality or different cleaning")
    print("4. **Date Range**: CSV includes more recent data (up to 9/9/25)")
    print("5. **Outlier Effects**: Different robust cleaning may affect results")
    
    print("\n🔧 RECOMMENDATIONS")
    print("=" * 30)
    print("1. **Use Variable Window Lengths**: [7, 10, 14, 21, 28] days")
    print("2. **Investigate Data Quality**: Check for measurement errors")
    print("3. **Compare Data Sources**: Ensure database matches CSV exactly")
    print("4. **Validate Cleaning**: Test different robust cleaning parameters")
    print("5. **Check Date Ranges**: Ensure we have the same data period")

if __name__ == '__main__':
    main()
